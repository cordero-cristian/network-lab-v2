# Data Model: DHCP/ZTP Bootstrap And Automated Onboarding

**Status**: DEFERRED — BLOCKED ON ACCESS TO A GENUINE BOOTABLE SR LINUX RUNTIME

Feature 005 would add narrow frozen Pydantic v2 boundary models with `extra="forbid"` only
after the runtime gate and explicit approval. Existing Feature 002-004 models remain unchanged.

## Shared Scalars

- Bootstrap identities are EUI-48 MAC addresses parsed strictly and serialized as uppercase
  colon-separated octets; multicast, broadcast, all-zero, and malformed values are rejected.
- Device names reuse Feature 002's `DeviceName` constraint.
- Management targets are normalized IPv4 host addresses and must equal Nautobot
  `primary_ip4` and the deterministic bootstrap lease.
- Artifact URLs are bounded HTTP URLs with a literal test-owned IPv4 host, no userinfo,
  query, fragment, traversal, or public/host endpoint.
- SHA-256 values are exactly 64 lowercase hexadecimal characters; bootstrap files are
  bounded to 64 KiB each.
- Safe stages, categories, and messages are bounded ASCII and never contain credentials,
  raw scripts/configuration, packets, responses, exceptions, or stacks.

## Runtime Gate Evidence

This is retained test evidence, not application state.

| Field | Type | Rule |
|---|---|---|
| `artifact_name` | bounded text | Exact Nokia SR Linux bootable artifact |
| `release` | bounded text | Exact selected release/build |
| `sha256` | SHA-256 | Digest of original artifact |
| `provenance` | URL/reference | Authorized acquisition source without credentials |
| `permitted_use` | bounded text | Lab-use basis without license material |
| `hypervisor` | bounded text | Exact product/version |
| `firmware_machine_nics` | bounded record | Exact boot and interface model |
| `vcpu_memory_disk` | bounded record | Measured minimum allocation |
| `console_evidence` | safe reference | Firmware, GRUB, ZTP, and operational transitions |
| `bootstrap_mac` | EUI-48 | Stable through guest reboot and clean recreation |
| `authentication_source` | literal | `runtime_factory` or gate-proven vendor-native mechanism |
| `result` | literal | `pass` or `defer` |

No VM image, entitlement credential, license file, raw configuration, or unrestricted packet
capture is committed.

## Bootstrap Device Identity

| Field | Type | Rule |
|---|---|---|
| `bootstrap_mac` | EUI-48 | Deterministic boot-management MAC proved by runtime gate |
| `identifier_kind` | literal | `management_mac` |
| `expected_device_name` | DeviceName | Canonical Nautobot name |
| `observed_device_name` | DeviceName | Must equal expected exactly |
| `management_address` | IPv4 | Must equal lease and Nautobot primary IPv4 |

The same canonical MAC must be defined on the VM boot-management adapter, observed in DHCP
Option 61/link-layer evidence, observable through the runtime-proven post-boot relation, and
stored on the Nautobot management Interface. Physical chassis serial identity is a separate
deployment concern and not this virtual acceptance model.

## Bootstrap Lease

| Field | Type | Rule |
|---|---|---|
| `bootstrap_mac` | EUI-48 | Exact static DHCP match and lease key |
| `client_id` | bounded bytes | Runtime-proven Option 61 MAC encoding |
| `management_address` | IPv4 | One static test-owned address |
| `lease_seconds` | literal | Infinite as encoded by dnsmasq |
| `artifact_url` | bootstrap URL | Runtime-proven 66+67 or complete Option 67 form |

This is disposable service state and never enters Kafka or Temporal history.

## Bootstrap Artifact Identity

| Field | Type | Rule |
|---|---|---|
| `script_path` | safe relative path | Fixed basename below bootstrap root |
| `script_sha256` | SHA-256 | Digest of exact served bytes |
| `script_bytes` | integer | 1 through 64 KiB |
| `config_path` | safe relative path | Fixed JSON basename below bootstrap root |
| `config_sha256` | SHA-256 | Digest of exact served bytes |
| `config_bytes` | integer | 1 through 64 KiB |

Validation rejects traversal, symlinks outside the root, malformed Python/JSON, forbidden
intent paths, credentials, unsafe URLs, non-ASCII identity, and oversized content.

## Onboarding Mapping

| Field | Type | Rule |
|---|---|---|
| `bootstrap_mac` | EUI-48 | Exact query and post-query equality |
| `nautobot_interface_id` | UUID | Exactly one core Interface result |
| `nautobot_device_id` | UUID | Exactly one core Device |
| `interface_name` | literal | `mgmt0` |
| `mgmt_only` | literal | `true` |
| `module` | null | Interface is directly Device-owned |
| `device_name` | DeviceName | Passed to existing deployment request |
| `platform` | literal | `nokia_srl` |
| `primary_ip4` | IPv4 | Authoritative gNMI target and exact lease address |

The query is `/api/dcim/interfaces/?mac_address=<canonical-MAC>&limit=2&depth=0` with a token
that can view all candidate Interfaces and Devices. Require API count and returned length one,
then revalidate MAC and ownership before following the same-origin Device relation. Nautobot
2.4.41 does not enforce MAC uniqueness, so application cardinality checks are mandatory. No
custom field, DeviceIntent extension, App, mapping table, or management-IP identity is added.

## Bootstrap Readiness Result

| Field | Type | Rule |
|---|---|---|
| `identity` | Bootstrap Device Identity | Fully matched identity |
| `platform_model_present` | literal | `true` after Capabilities |
| `gnmi_authenticated` | literal | `true` only after authenticated reads |
| `native_autoboot_disabled` | literal | `true` from runtime-gate-proven state read |
| `minimum_config_present` | literal | `true` only when every exact bootstrap value matches |
| `bootstrap_status` | literal | `ready` |
| `checked_at` | UTC timestamp | Boundary observation time |

Only a `ready` result with both native completion booleans true can create the existing
`DeploymentRequested` event. Credentials and raw gNMI data are not fields.

## Onboarding Failure

| Field | Type | Rule |
|---|---|---|
| `correlation_id` | UUID | One command invocation |
| `bootstrap_mac` | EUI-48 or null | Safe input if validated |
| `device_name` | DeviceName or null | Present only after exact mapping |
| `failure_stage` | literal | `mapping`, `readiness`, `identity`, or `handoff` |
| `error_type` | stable literal | Category below |
| `error_message` | safe text | Static bounded message |
| `status` | literal | `failed` |
| `failed_at` | UTC timestamp | Command boundary observation time |

This is a command result/log boundary, not a new Kafka event.

Stable categories are `nautobot_unavailable`, `device_not_found`, `device_ambiguous`,
`identifier_invalid`, `unsupported_platform`, `management_address_invalid`,
`device_unavailable`, `device_authentication_failed`, `device_platform_mismatch`,
`device_identity_mismatch`, `device_response_invalid`, and `handoff_failed`.

## Onboarding Accepted Result

| Field | Type | Rule |
|---|---|---|
| `correlation_id` | UUID | Same value published in the deployment request |
| `request_event_id` | UUID | Existing deployment request identity |
| `workflow_id` | bounded text | `deploy-device-config:<request_event_id>` |
| `device_name` | DeviceName | Exact mapped Nautobot name |
| `bootstrap_mac` | EUI-48 | Exact validated identity |
| `status` | literal | `accepted` |
| `accepted_at` | UTC timestamp | Command boundary publication time |

## Existing Handoff

Successful readiness creates the accepted `DeploymentRequested` v1 shape containing a new
UUID event ID, correlation UUID, canonical device name, UTC request time, and source
`onboarding-cli`. The exact serialized event is reused for Kafka producer retries and
redelivery. It contains no bootstrap MAC or management address because those have been
validated before this existing boundary. It cannot protect a delayed request across a
replacement device incarnation; replacement/RMA is outside scope.

## State Transitions

```text
Blank device
  -> genuine firmware/GRUB auto-boot -> isolated MAC-keyed DHCP
  -> Python script -> native configure succeeds -> native auto-boot disabled
  -> authenticated gNMI not ready -> bounded retry or safe failure
  -> exact MAC/hostname/address/Nautobot Interface match -> ready
  -> DeploymentRequested published -> existing durable deployment workflow
  -> existing DeploymentCompleted or DeploymentFailed
  -> reboot -> persisted intended state and no destructive bootstrap replay
```

Lease and HTTP observations never transition the device to `ready`. Unknown, duplicate, or
inconsistent identity transitions directly to permanent failure before deployment.
