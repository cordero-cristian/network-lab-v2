# Onboarding Boundary Contract

**Status**: DEFERRED — BLOCKED ON ACCESS TO A GENUINE BOOTABLE SR LINUX RUNTIME

Feature 005 may resume only when the owner provides or authorizes a genuine bootable SR Linux
artifact whose provenance and lab use are acceptable and which can exercise the documented
SR Linux auto-boot path. The core `Interface.mac_address` mapping remains planned; its custom-
field fallback is unapproved.

## Command

```text
uv run network-onboard-device BOOTSTRAP_MAC
```

The finite command uses existing Nautobot, Kafka, and worker-local device settings. It does
not run as a daemon, receive callbacks, mutate the device, render configuration, or start a
Temporal workflow directly.

## Mapping

1. Parse EUI-48 input and canonicalize it to uppercase colon notation.
2. Query `/api/dcim/interfaces/` by MAC alone with `limit=2&depth=0`.
3. Require API count and result length exactly one and recheck exact canonical MAC.
4. Require direct Device ownership, `module=null`, `name=mgmt0`, and `mgmt_only=true`.
5. Follow the Device relation using existing same-origin and object-ID validation.
6. Require platform network driver `nokia_srl` and a valid `primary_ip4`.
7. Require `primary_ip4` to equal the deterministic bootstrap lease address.

The Nautobot token must see all candidate Interfaces and Devices so permissions cannot hide a
duplicate. Missing, duplicate, module-owned, wrong-name/role, malformed, or inconsistent data
fails before Kafka publication. No Device custom field, App, or mapping database is added.

## Bounded Readiness

The command attempts readiness at most 12 times over no more than 90 seconds, starting at
2 seconds with coefficient 1.5 and a 5-second cap. Only Nautobot transport/server failure
and gNMI unavailability retry. Authentication, platform, malformed response, hostname, MAC,
and address mismatch are permanent.

Each proposed attempt disables pyGNMI logging, authenticates using runtime-only settings,
checks Capabilities, reads hostname with datatype `all`, validates the exact
runtime-gate-proven post-boot MAC relation, reads the gate-proven native auto-boot state, and
reads every exact minimum configuration value. It requires auto-boot disabled and all minimum
values present before readiness. Because the script disables auto-boot only after checked
`configure()` success, those per-device reads prove native completion. Raw responses and
exceptions never cross the device boundary.

## Existing Handoff

After readiness, publish exactly one existing `network.deployment.requested` v1 event with
the canonical device name and source `onboarding-cli`. Producer retries retain byte-identical
payload and event ID. The existing consumer starts
`deploy-device-config:<request-event-id>` with `USE_EXISTING` and `REJECT_DUPLICATE`.

No `network.onboarding.*` topic or event is added. The stable identifier is intentionally
absent from the existing deployment contract after it has served its boundary-validation
purpose. Existing `network.deployment.completed` or `.failed` is the correlated durable
outcome. Correction after a failed accepted deployment uses the existing explicit
deployment request command rather than inventing onboarding replay state.

The unchanged event cannot distinguish a delayed request from a replacement device with the
same name, address, and hostname. The command's immediate MAC identity check
and Feature 004's pre-Set hostname guard are the proposed protections; replacement/RMA and
cross-incarnation protection remain out of scope.

## Safe Output

Success output contains correlation ID, request event ID, deployment workflow ID, canonical
device name, bootstrap MAC, status `accepted`, and UTC `accepted_at`. Pre-handoff failure
contains correlation, status `failed`, UTC `failed_at`, safe stage/category, and any
already-validated device/identifier fields. Credentials, lease packet bodies, raw bootstrap
files, production artifacts, raw responses, exception text, and stacks are prohibited.
