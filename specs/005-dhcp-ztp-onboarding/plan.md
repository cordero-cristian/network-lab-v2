# Implementation Plan: DHCP/ZTP Bootstrap And Automated Onboarding

**Branch**: `005-dhcp-ztp-onboarding` | **Date**: 2026-09-11 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/005-dhcp-ztp-onboarding/spec.md`

**Status**: DEFERRED — BLOCKED ON ACCESS TO A GENUINE BOOTABLE SR LINUX RUNTIME

**Unblock condition**: Feature 005 may resume only when the owner provides or authorizes a
genuine bootable SR Linux artifact whose provenance and lab use are acceptable and which can
exercise the documented SR Linux auto-boot path. T003-T048 remain deferred and blocked.

## Summary

Preserve the accepted containerized SR Linux path for Features 001-004. Feature 005 may use a
separate, genuine SR Linux firmware/bootloader/storage runtime solely to prove native
auto-boot -> DHCP -> Python provisioning -> minimum operational state before handing the
device to the unchanged deployment request, Feature 002 renderer, Temporal execution, and
Feature 004 gNMI deployment/validation path.

No practical bootable SR Linux VM artifact is currently established. Public Nokia delivery
provides the OCI simulator; documented bootable media target physical systems, and current
netlab/containerlab tooling has no SR Linux VM adapter. The feature is therefore deferred.
If an authorized artifact becomes available, its first action is a new disposable gate.
Virtual identity is redesigned as a deterministic boot-management MAC mapped through core
Nautobot `Interface.mac_address`; its runtime stability must be proved by that gate.

## Technical Context

**Language/Version**: Existing CPython 3.12.13 package; selected-runtime native Python executes
only through the documented SR Linux ZTP process

**Primary Dependencies**: Existing Pydantic v2, httpx, pyGNMI 0.8.15, confluent-kafka, and
Temporal SDK; accepted container SR Linux 26.7.2-519, containerlab 0.79.0, netlab 26.08,
Nautobot 2.4.41, and isolated dnsmasq/static HTTP. Hypervisor and VM dependencies remain
unknown until an authorized artifact supplies supported requirements.

**Storage**: Existing Nautobot Device plus directly owned management Interface, Kafka,
Temporal PostgreSQL, and genuine SR Linux boot/configuration storage; DHCP leases/logs are
disposable and no new application datastore is added

**Testing**: Accepted T001/T002 container evidence; future artifact/provenance gate followed
by disposable boot-console, packet, native-log, guest-reboot, unit/component, and end-to-end
evidence only after explicit approval

**Target Platform**: Canonical Ubuntu 24.04.4 x86-64 with hardware virtualization and
artifact-specific resources; current two-vCPU host capacity may require resizing. macOS ARM64
is not authoritative for the genuine runtime.

**Project Type**: One typed Python package, existing worker/consumer/workflow, one finite
onboarding command, one isolated DHCP/file service, and one separately lifecycle-managed
genuine-runtime validation topology

**Performance Goals**: Bootstrap readiness within 10 minutes and complete correlated
deployment within 15 minutes of blank boot; low-volume two-device lab with no throughput
target

**Constraints**: Genuine boot-path DHCP-discovered native ZTP only; no container emulation,
manual ZTP start, startup injection, unsupported hardware-media emulation, or SR OS/vSIM;
isolated DHCP/HTTP; deterministic MAC identity; runtime-only credentials; bounded retries;
no new event topic, daemon, workflow, renderer, datastore, or generic provisioning layer

**Scale/Scope**: One genuine-runtime onboarding target, one compatible SR Linux BGP peer, one
isolated bootstrap service/link, one deterministic MAC lease and artifact pair, one finite
command, and the accepted deployment event/workflow path

## Constitution Check

*GATE: Passed before research and rechecked after design.*

| Principle | Pre-Design Gate | Post-Design Evidence |
|---|---|---|
| Explicit Architectural Ownership | PASS: Nautobot remains authority; Kafka transports the existing deployment fact; Temporal owns durable work after acceptance. | Core management Interface MAC/name/primary-IP data provide mapping after runtime proof; the existing workflow, renderer, and SR Linux boundary perform all production deployment. Bootstrap services own only disposable state. |
| Small, Explicit Implementation | PASS: retain one package and add only one finite command plus narrow mapping/readiness functions after the gate. | No onboarding daemon/topic/workflow, Nautobot App, identity database, driver hierarchy, callback API, or child workflow. |
| Reproducible Local Infrastructure | PASS: require exact artifact provenance/pin and explicit isolated lifecycle before selection. | No runtime is claimed available; artifact-specific hypervisor/resources remain a gate instead of guessed infrastructure. |
| Evidence Over Process Status | PASS: hardware documentation is not treated as container or VM evidence. | The future gate must observe firmware/GRUB, packets, script, native status/logs, operational state, and guest reboot on the exact artifact. |
| Spec-Driven, Bounded Delivery | PASS: Feature 005 has isolated artifacts and excludes later architecture. | Research, data model, contracts, quickstart, tasks, consistency review, T001 correction gate, and explicit approval all precede source implementation. |

No constitution violation requires complexity justification.

## Redesign Research

### Native Bootstrap Gate - Failed

T001 used the exact pinned image with `suppress-startup-config: true`, no hostname/config
injection, and no `exec` provisioning. Isolated in-band and OOB probes delivered zero DHCP
packets and zero HTTP requests because no native ZTP process/API started. Option 67 URL
handling and artifacts were never reached. The container still generated a broad default
management configuration, so suppressed startup configuration was not a blank native-ZTP
state.

### Genuine Boot Runtime - Unavailable

No Nokia source or supported lab tool establishes an accessible SR Linux VM artifact. The
public OCI image directly starts `sr_linux`; Nokia's `.bin`, SD, and recovery media are
documented for physical platforms; netlab has no SR Linux libvirt provider; and
containerlab/vrnetlab has no SR Linux VM kind. Generic QEMU use of hardware media is not an
approved substitute. T003 remains blocked until the owner provides or authorizes a bootable
artifact with provenance, permitted use, release/digest, and supported runtime requirements.

When available, the artifact must prove actual firmware/GRUB auto-boot and use documented
Options 66+67 or Option 67 alone first. Option 43 remains excluded until its exact encoding is
proved from the selected runtime/vendor material. The script calls native `configure()`, checks
status, and disables auto-boot only after minimum configuration succeeds. The same gate must
prove server-side lab authentication without credentials in served artifacts and successful
gNMI using runtime-only client credentials.

### Identity And Readiness - Redesigned, Runtime Proof Pending

Use the selected runtime's deterministic boot-management EUI-48 MAC. The future gate must
prove one exact MAC in DHCP Option 61/link-layer evidence, stable across guest reboot and
clean recreation, and observable after startup. Nautobot stores it on one directly
Device-owned `mgmt0` Interface with `mgmt_only=true`; no custom field is selected.

The finite `network-onboard-device BOOTSTRAP_MAC` command canonicalizes the MAC, queries all
Nautobot Interfaces by MAC with limit two, requires exactly one result, then validates direct
Device ownership, interface role/name, platform, `primary_ip4`, exact hostname, management
address, authenticated gNMI, the runtime-proven MAC relation, disabled native auto-boot, and
every exact minimum configuration value. Physical use may select a unique chassis serial in a
separate design; virtual acceptance does not.

### Existing Durable Handoff - Not Reached

If a future runtime passes its gate and implementation is approved, the command publishes the existing `DeploymentRequested` v1 event with
source `onboarding-cli`. Producer retry and Kafka redelivery retain one event ID and exact
bytes. The accepted consumer starts the accepted
`deploy-device-config:<event_id>` workflow with separate `USE_EXISTING` and
`REJECT_DUPLICATE` policies. Preparation reads Nautobot, Feature 002 renders, Feature 004
deploys and validates, and existing deployment outcomes provide correlated durable results.

The owner selected this smaller handoff on 2026-09-12 instead of a new identity-carrying event
and workflow branch. The finite command rechecks the complete bootstrap readiness predicate,
including MAC, native completion, hostname, and address, immediately before publication; Feature
004 checks hostname immediately before Set. Delayed-request protection across a replacement
device incarnation is not promised, and replacement/RMA remains excluded.

No onboarding event topics, workflow branch, child workflow, service, renderer, or durable
state are added. Lease/HTTP/native-script observations are diagnostics, never completion;
verified disabled auto-boot prevents guest reboot or lease renewal from producing a new handoff.

### Persistence, Failure, And Security - New Gate Required

The future gate must prove native `configure()` persistence and boot-storage auto-boot state
across a real guest reboot with no lab save. `containerlab save` is prohibited for this path.
After existing deployment, the test lifecycle may invoke native
`tools system configuration save` only if exact-runtime evidence shows later gNMI-applied
intent otherwise remains running-only. T005 determines this with a disposable representative
gNMI change, reboot without save, and repeat with native save if needed. No hypervisor snapshot
is selected.

Pre-handoff failures return one safe command category and no Kafka fact. Post-handoff
failures remain existing deployment outcomes. No credentials, raw bootstrap/production
content, packet bodies, responses, exception text, or stacks enter events, workflow history,
normal logs, or evidence.

## Project Structure

### Documentation (this feature)

```text
specs/005-dhcp-ztp-onboarding/
|-- spec.md
|-- plan.md
|-- research.md
|-- data-model.md
|-- quickstart.md
|-- contracts/
|   |-- bootstrap.md
|   |-- onboarding.md
|   `-- execution.md
|-- checklists/
|   |-- requirements.md
|   `-- review.md
`-- tasks.md
```

### Source Code (repository root)

```text
pyproject.toml                          # finite onboarding command entry point
.env.example                           # existing runtime-only credentials/settings
compose.bootstrap.yaml                 # isolated DHCP/HTTP service only
compose.device-access.yaml             # existing worker device access retained
lab/topology.yml                       # accepted Features 001-004 topology unchanged
lab/ztp-topology.yml                   # future genuine-runtime validation topology
lab/bootstrap/
|-- Dockerfile                         # patch-pinned DHCP/HTTP image
|-- dnsmasq.conf                        # isolated MAC-static DHCP
|-- ztp.py                              # deterministic native provisioning script
`-- bootstrap.json                     # minimum identity/manageability state
lab/ztp-runtime/README.md              # artifact provenance and host requirements; no image committed
src/network_automation/
|-- settings.py                        # bounded onboarding settings only if required
|-- onboarding.py                      # exact mapping/readiness models and finite boundary
|-- cli/onboard.py                     # finite map/readiness/handoff command
|-- intent/nautobot.py                 # core management Interface MAC mapping
|-- devices/srlinux.py                 # additive safe identity/readiness reads
`-- events/producer.py                 # reuse existing deployment publication
tests/
|-- unit/
|   |-- test_bootstrap_contract.py
|   |-- test_onboarding_models.py
|   |-- test_onboarding_cli.py
|   |-- test_nautobot_onboarding.py
|   |-- test_srlinux_device.py
|   `-- existing Compose/topology/event/replay regressions
`-- integration/
    |-- test_srlinux_ztp_boot.py        # genuine boot-path gate
    `-- test_srlinux_onboarding.py      # canonical lifecycle/failures/reboot
```

**Structure Decision**: Keep the accepted container topology unchanged and add a separate
Feature 005 topology only after a genuine artifact passes its gate. Extend the accepted package
with one finite command and narrow concrete boundaries. The VM image is never committed; its
exact acquisition, pin, permitted use, and host requirements are documented locally without
credentials. Existing deployment source is reused, not generalized or copied.

## Blocked Implementation Sequence

1. T001/T002 container evidence is accepted.
2. Redesign research found no accessible genuine bootable SR Linux artifact; defer.
3. BLOCKED T003: owner supplies or authorizes an exact artifact and its permitted use.
4. BLOCKED T004-T006: prove firmware/GRUB auto-boot, MAC/DHCP/options/script, operational state,
   persistence, guest reboot, resources, integration, and cleanup; reconcile and obtain approval.
5. BLOCKED T007 onward: implement only the proven runtime/constants, core Interface MAC mapping,
   finite handoff, isolated services, tests, regressions, and evidence.

## Complexity Tracking

No constitution violation is proposed. A separate genuine-runtime topology is justified only
for Feature 005 native boot validation and does not replace the accepted container runtime.
The isolated DHCP/static-file service owns no durable state. The finite command is an operator
boundary, not another service or orchestrator.
