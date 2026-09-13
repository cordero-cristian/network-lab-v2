# Feature Specification: DHCP/ZTP Bootstrap And Automated Onboarding

**Feature Branch**: `005-dhcp-ztp-onboarding`

**Created**: 2026-09-11

**Status**: DEFERRED — BLOCKED ON ACCESS TO A GENUINE BOOTABLE SR LINUX RUNTIME

**Unblock condition**: Feature 005 may resume only when the owner provides or authorizes a
genuine bootable SR Linux artifact whose provenance and lab use are acceptable and which can
exercise the documented SR Linux auto-boot path.

**Input**: User description: "Replace the lab-only hostname bootstrap with a real,
isolated DHCP/ZTP path that establishes only identity, management reachability, and gNMI,
then feeds the identified device into the existing durable render, deployment, and
validation path."

## Clarifications

### Session 2026-09-12

- Q: How should Feature 005 preserve stable physical identity across the durable handoff? → A: Relax the specification: publish only the existing deployment request after exact boundary checks; do not add onboarding events/workflows or promise replacement-incarnation protection.
- Q: Does the exact pinned container satisfy the mandatory native-ZTP and chassis-serial gate? → A: No. It emitted no DHCP discovery or HTTP request and exposed one non-unique synthetic chassis serial across two nodes; FR-006 stops implementation.
- Q: May Feature 005 emulate native ZTP inside the canonical container after the failed gate? → A: No. Preserve that container for Features 001-004; native-ZTP acceptance requires a separate genuine SR Linux boot path that actually executes documented auto-boot.
- Q: What identity should virtual acceptance use? → A: Prefer a deterministic boot-management MAC mapped through a directly device-owned core Nautobot Interface; a narrow Device custom field remains unapproved and may be considered only with separate owner approval if runtime evidence proves core modeling unusable.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Bootstrap A Blank Device Safely (Priority: P1)

As a lab operator, I can start a new SR Linux node without preloaded intended network
configuration and have it acquire only the identity and management capability needed for
the automation framework to manage it.

**Why this priority**: A real minimum bootstrap is the feature's defining value and must be
proven before onboarding or full deployment can be trusted.

**Independent Test**: Start one test-owned node from the closest supported unprovisioned
state, observe isolated address and bootstrap discovery, and independently verify expected
hostname, management reachability, authentication, and gNMI while proving loopback, fabric
addressing, BGP, policy, and service intent remain absent.

**Acceptance Scenarios**:

1. **Given** a known blank SR Linux node on the isolated bootstrap network, **When** it
   boots, **Then** it obtains a deterministic management lease and discovers one approved
   minimal bootstrap artifact.
2. **Given** the approved artifact, **When** bootstrap succeeds, **Then** the device has the
   expected hostname, management path, and authenticated gNMI access and no intended fabric
   configuration.
3. **Given** bootstrap infrastructure, **When** the normal supporting stack starts without
   the explicit bootstrap Compose overlay, **Then** no DHCP or bootstrap-file service runs or reaches a host
   or physical network.

---

### User Story 2 - Onboard Through The Existing Automation Path (Priority: P2)

As a lab operator, I receive a correlated result after a newly manageable device is mapped
unambiguously to Nautobot and passed through the existing durable render, deployment, and
operational validation behavior.

**Why this priority**: Bootstrap is useful only when it hands control to authoritative
intent instead of becoming a second configuration system.

**Independent Test**: Bootstrap a known device, prove gNMI identity and authoritative
Nautobot mapping, submit one verified deployment handoff, and observe the existing Feature 002,
003, and 004 path produce a correlated successful deployment with independent BGP and
device-state verification.

**Acceptance Scenarios**:

1. **Given** a bootstrap-complete device with one stable identifier, **When** handoff is
   evaluated, **Then** it maps to exactly one expected Nautobot Device before any deployment
   request is accepted.
2. **Given** a verified mapping and exact hostname, **When** the existing deployment request enters
   the automation path, **Then** the existing durable deployment behavior renders from
   Nautobot, applies through gNMI, validates operational state, and emits one correlated
   result.
3. **Given** a DHCP lease or successful file fetch without authenticated gNMI and identity
   agreement, **When** handoff is evaluated, **Then** the device is not declared
   bootstrap-complete and no deployment begins.

---

### User Story 3 - Repeat Bootstrap And Reboot Without Damage (Priority: P3)

As a lab operator, I can tolerate lease renewal, repeated artifact fetches, duplicate
deployment-request redelivery, and a device reboot without duplicate workflows, destructive
re-onboarding, or regression to bootstrap-only state.

**Why this priority**: Repeatability is required before a zero-touch path can safely own
first boot.

**Independent Test**: Redeliver one accepted deployment request, refetch the artifact, renew
the lease, and reboot an onboarded node; verify one retained deployment event/workflow
identity, retained full configuration, no destructive bootstrap replay, and successful
existing validation.

**Acceptance Scenarios**:

1. **Given** repeated delivery of the same accepted deployment request, **When** records
   are consumed concurrently or after closure, **Then** they retain one existing deployment
   workflow execution and one logical downstream deployment result.
2. **Given** an already-onboarded device, **When** it renews DHCP or fetches the same
   bootstrap artifact, **Then** the operation is harmless and does not overwrite intended
   configuration.
3. **Given** a fully deployed device, **When** it reboots, **Then** intended configuration
   and manageability persist, bootstrap does not destructively restart, and the existing
   validator still passes.

---

### User Story 4 - Diagnose Bootstrap Failure Safely (Priority: P4)

As a lab operator, I receive bounded, correlated, actionable failure information when a
device cannot be identified, bootstrapped, reached, or matched, without exposing credentials
or raw artifacts.

**Why this priority**: DHCP and first-boot failures otherwise appear as ambiguous silence and
can create unsafe retry loops.

**Independent Test**: Exercise unknown and ambiguous identifiers, missing Nautobot intent,
bootstrap outage, gNMI readiness timeout, hostname mismatch, and failed reboot behavior;
verify stable categories, retry boundaries, no downstream mutation where identity is
untrusted, and safe logs/events.

**Acceptance Scenarios**:

1. **Given** an unknown or ambiguously mapped stable identifier, **When** onboarding is
   attempted, **Then** it fails permanently before downstream deployment.
2. **Given** a temporary bootstrap service or gNMI readiness outage, **When** the device is
   expected to become manageable, **Then** retries remain bounded and produce a clear final
   failure if readiness never arrives.
3. **Given** a hostname that differs from the mapped Nautobot device, **When** identity is
   checked, **Then** exact equality fails permanently and Feature 004 never writes.
4. **Given** any required failure, **When** logs and outcomes are inspected, **Then** they
   contain safe correlation, stage, identifier, and category context without credentials,
   raw bootstrap content, production configuration, arbitrary packet dumps, or stacks.

### Edge Cases

- No practical bootable SR Linux VM artifact may be accessible to this project; in that case
  native ZTP cannot be honestly validated and the feature remains deferred.
- A candidate hardware-targeted disk image may fail to represent a supported virtual platform,
  firmware, NIC, storage, identity, or licensing contract and therefore cannot qualify.
- The genuine boot runtime may require more CPU, memory, disk, or acceleration than the
  canonical host currently provides.
- The DHCP client identifier may be absent, unstable, or different from the identifier
  exposed after gNMI becomes available.
- More than one Nautobot Device may carry the same proposed identifier.
- A device may receive a lease and fetch a script but fail before applying or saving config.
- Applying startup configuration may release or replace the temporary DHCP address.
- Bootstrap may succeed while gNMI is still starting or authentication is not ready.
- Nautobot may become unavailable during the finite pre-handoff readiness check.
- A delayed existing deployment request does not carry bootstrap identity; replacement/RMA
  and protection across a different device incarnation are explicitly outside this feature.
- The same device may renew, reboot, or fetch the same artifact multiple times.
- Auto-boot may remain enabled after partial failure and repeatedly restart discovery.
- Guest reboot persistence may differ from VM destroy/recreate and from container restart.
- The BGP peer may not yet be ready after onboarding even though bootstrap itself succeeded.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST preserve Nautobot as intended-state authority, Kafka as event
  transport, Temporal as durable orchestrator, Feature 002 as sole production renderer,
  Feature 003 execution semantics, and Feature 004 deployment/validation behavior.
- **FR-002**: The feature MUST own only first-boot bootstrap, deterministic device mapping,
  and handoff into the existing automation path.
- **FR-003**: Bootstrap MUST be limited to hostname identity, management addressing and
  required route/name resolution, authenticated gNMI reachability, lab authentication, and
  the minimum metadata needed to identify the device.
- **FR-004**: Bootstrap MUST NOT configure loopbacks, fabric interface addressing, BGP,
  routing policy, production services, or any invariant rendered and validated by Features
  002 and 004.
- **FR-005**: An exact pinned SR Linux runtime MUST be verified from firmware/bootloader and
  persistent boot storage through documented auto-boot, DHCP, script execution, operational
  startup, and guest reboot before implementation proceeds beyond the runtime gate.
- **FR-006**: The canonical container MUST NOT be made to emulate native ZTP through manual
  service startup, command override, startup configuration, bind mount, or process injection.
- **FR-007**: A genuine-runtime blank test node MUST start without topology-injected hostname
  or intended production configuration; the canonical Features 001-004 container topology
  remains unchanged.
- **FR-008**: DHCP MUST answer only on a dedicated test-owned bootstrap network and MUST NOT
  bind to host, physical, default Compose, or unrelated lab networks.
- **FR-009**: Bootstrap file delivery MUST be reachable only from the dedicated lab path and
  MUST expose no host/public listener unless canonical behavior proves one narrowly required.
- **FR-010**: Address assignment and bootstrap selection MUST use the runtime-proven
  deterministic boot-management MAC and be observable through bounded lease/service diagnostics.
- **FR-011**: DHCP lease acquisition or file retrieval alone MUST NOT count as successful
  bootstrap.
- **FR-012**: Bootstrap completion MUST require successful native script/configuration status,
  disabled auto-boot, authenticated gNMI connectivity, exact expected hostname, management
  address agreement, stable boot-management MAC agreement, and one unambiguous Nautobot match.
  The finite handoff boundary MUST re-read the runtime-gate-proven auto-boot and exact minimum
  configuration state; gate evidence alone is not per-device completion.
- **FR-013**: The exact Feature 004 pre-Set hostname equality guard MUST remain unchanged.
- **FR-014**: Virtual-lab mapping MUST use the deterministic boot-management EUI-48 MAC,
  independent of management address; physical deployments MAY use a unique chassis serial.
- **FR-015**: The normalized MAC MUST map through exactly one core Nautobot Interface to one
  Device; ambiguous, missing, indirect-module, wrong-interface, or inconsistent mappings MUST
  fail before deployment.
- **FR-016**: Nautobot 2.4.41 MUST represent the lab identity as core
  `Interface.mac_address` on directly Device-owned `mgmt0` with `mgmt_only=true`. A Device
  custom field requires separate owner approval only if a selected runtime cannot satisfy this
  model; no App, identity database, external inventory, or generic abstraction is permitted.
- **FR-017**: Any onboarding state marker MUST use existing Nautobot Device status semantics
  and MUST NOT create a parallel source of durable state.
- **FR-018**: The feature MUST add no onboarding event topic or contract; after all bootstrap
  checks pass, the finite boundary MUST publish only the existing versioned deployment
  request. Lease, packet, HTTP-request, and per-step events MUST NOT be added.
- **FR-019**: Pre-handoff failure MUST remain a finite command result with stable safe
  stage/category and correlation metadata; it MUST NOT create an onboarding failure event.
- **FR-020**: The finite command result MUST include correlation, device, bootstrap MAC,
  and bounded time/status context without credentials or artifacts. The existing deployment
  event contracts MUST remain unchanged and therefore do not carry the bootstrap MAC.
- **FR-021**: A verified onboarding handoff MUST enter the existing durable deployment path
  without duplicating intent read, rendering, artifact writing, gNMI deployment, or validation.
- **FR-022**: A new workflow or activity MAY be introduced only when a concrete bootstrap
  orchestration responsibility cannot be expressed by a narrow extension of existing
  execution; child-workflow choreography is excluded unless separately justified.
- **FR-023**: Temporal MUST own all retries and durable state after the existing deployment
  request is accepted into automation.
- **FR-024**: Bootstrap-native retries MUST remain finite and MUST not become a second
  orchestration state machine.
- **FR-025**: Temporary service/readiness/Nautobot transport failures MUST be distinguishable
  from permanent MAC, mapping, artifact, and identity failures.
- **FR-026**: The feature MUST add no onboarding workflow. The existing deployment workflow
  identity MUST remain derived from its request event ID and retain the separate running-
  conflict and closed-reuse policy semantics.
- **FR-027**: Redelivery of the same accepted deployment request MUST result in one logical
  downstream deployment result without a deduplication database; independently generated
  requests and replacement-device incarnation protection are outside this guarantee.
- **FR-028**: Repeated delivery or retrieval of the same bootstrap material MUST be
  byte-stable and harmless.
- **FR-029**: A fully onboarded device MUST not be destructively returned to bootstrap-only
  state by lease renewal, same-request redelivery, or reboot.
- **FR-030**: The provisioning script MUST disable native auto-boot only after checked
  successful minimum configuration, and acceptance MUST verify the boot-storage flag and no
  ZTP re-entry on a real guest reboot.
- **FR-031**: Reboot acceptance MUST independently verify persisted manageability, intended
  configuration, absence of destructive re-onboarding, and successful existing validation.
- **FR-032**: Bootstrap artifacts MUST be deterministic, separate from Feature 002 production
  artifacts, and contain only the approved minimum bootstrap state.
- **FR-033**: Bootstrap artifact validation MUST reject forbidden intended-state content,
  malformed identity, unsafe paths, unsupported format, and content exceeding explicit bounds.
- **FR-034**: Credentials MUST come from local runtime settings, MUST NOT be hardcoded, and
  MUST NOT appear in source defaults, artifacts, events, workflow history, logs, or evidence.
- **FR-035**: The initial lab may use username/password authentication and ordinary bootstrap
  transport only within the isolated lab; production PKI and secret lifecycle are excluded.
- **FR-036**: Runtime additions MUST be limited to one separately lifecycle-managed genuine
  SR Linux boot target plus isolated DHCP/static-file services and MUST add no datastore, API,
  broker, cache, or monitoring service.
- **FR-037**: Bootstrap services MUST exist only in an explicit optional Compose overlay and
  be independently startable/stoppable without changing normal Feature 001 service startup.
- **FR-038**: Topology, bootstrap services, automation endpoints, and teardown MUST have an
  explicit order that removes only test-owned resources and never resets shared volumes.
- **FR-039**: Component tests MUST prove network binding, deterministic MAC lease/bootstrap
  content, static retrieval, repeated retrieval, service health, and absence of DHCP on host,
  physical, default, or unrelated networks.
- **FR-040**: Canonical acceptance MUST prove the complete blank-device-to-correlated-result
  lifecycle and independently inspect both bootstrap-only and final operational state.
- **FR-041**: Canonical failure acceptance MUST cover unknown/ambiguous identity, missing
  Nautobot device, bootstrap outage, readiness exhaustion, hostname mismatch, same-request
  redelivery, and already-provisioned reboot without destabilizing shared infrastructure.
- **FR-042**: Logs MUST include safe event, correlation, workflow, device, bootstrap MAC,
  bootstrap stage, and category context where available and exclude credentials, raw
  bootstrap/production configuration, arbitrary packet dumps, raw responses, and stacks.
- **FR-043**: Features 001 through 004 default, replay, component, real integration, and
  canonical acceptance behavior MUST remain healthy.
- **FR-044**: The implementation MUST retain one Python package and Nokia SR Linux as the only
  NOS and MUST NOT introduce provisioning interfaces, provider/driver classes, vendor
  registries, plugin loaders, generic event abstractions, or future-feature scaffolding.
- **FR-045**: The feature MUST NOT add production DHCP/IPAM, external synchronization, PKI,
  secret management, replacement/RMA, rollback, approvals, ticketing, server provisioning,
  API/UI, monitoring, Kubernetes, HA, cloud, or production deployment architecture.
- **FR-046**: Features 001-004 MUST retain `ghcr.io/nokia/srlinux:26.7.2-519` and their
  accepted netlab/containerlab behavior; the separate genuine runtime is Feature 005
  validation infrastructure only.
- **FR-047**: Before the future runtime gate, the owner MUST provide or authorize an accessible
  bootable SR Linux artifact with documented provenance, permitted lab use, exact release and
  digest, virtualization requirements, and evidence that its platform supports native ZTP.
- **FR-048**: If no such artifact is practically available, Feature 005 MUST remain deferred;
  Nokia SR OS/vSIM, the OCI container, generic startup mounts, and unsupported hardware-image
  emulation MUST NOT be substituted.
- **FR-049**: The selected runtime gate MUST capture firmware/bootloader console, DHCP packets,
  vendor-supported auto-boot client-ID selection, Option 61 and boot-management MAC, script
  retrieval/execution, native status/logs, configuration result, auto-boot state, operational
  startup, and guest reboot behavior. Before T007 it MUST also prove how authenticated gNMI
  becomes available without placing credentials in served artifacts: either selected-runtime
  factory lab authentication or another vendor-supported native mechanism using runtime-only
  client credentials; otherwise the gate fails.
- **FR-050**: Reboot acceptance MUST NOT use `containerlab save`. It MAY use the native SR Linux
  configuration-save command after successful existing deployment only if selected-runtime
  evidence proves that later intended configuration otherwise does not persist. A VM snapshot
  MUST NOT manufacture native-ZTP success.
- **FR-051**: The runtime gate MUST identify authenticated post-boot reads that prove disabled
  auto-boot and exact minimum configuration on the specific device. If those states cannot be
  read safely before handoff, the gate fails.
- **FR-052**: Before selecting a post-deployment persistence strategy, the runtime gate MUST
  apply one test-owned representative gNMI change after operational startup, reboot without a
  save, record whether it persists, and if needed repeat with native
  `tools system configuration save`; the change MUST be removed with gate teardown.

### Key Entities

- **Bootstrap Device Identity**: Deterministic boot-management EUI-48 MAC observed during
  discovery and confirmed against the runtime and Nautobot Interface, plus expected name/address.
- **Bootstrap Lease**: Test-owned management assignment and bounded diagnostics; disposable,
  not durable automation state.
- **Bootstrap Artifact**: Deterministic minimal startup content distinct from production
  intent artifacts, with identity and content digest.
- **Onboarding Mapping**: One bootstrap MAC through exactly one core Nautobot Interface to one
  Device and expected hostname, without management IP as durable identity.
- **Runtime Gate Evidence**: Artifact provenance/pin, permitted use, virtualization profile,
  console/packet/native observations, MAC stability, persistence, reboot, and cleanup result.
- **Bootstrap Readiness Result**: Safe result proving gNMI authentication, identity, address,
  and authoritative mapping before handoff.
- **Onboarding Command Result**: One finite correlated accepted or failed result containing
  safe stable identity context; acceptance publishes the unchanged deployment request.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: One blank selected genuine-runtime test node becomes identified and automation-reachable
  through isolated bootstrap within 10 minutes of healthy topology and services.
- **SC-002**: Independent inspection finds 100% of approved bootstrap capabilities present
  and 0 forbidden loopback, fabric, BGP, policy, or production-service settings preloaded.
- **SC-003**: The bootstrap MAC maps through exactly one Interface to one intended Device in 100% of successful
  onboarding runs; unknown or duplicate mappings cause zero downstream writes.
- **SC-004**: A successful onboarding run traverses the accepted intent, render, deployment,
  and validation path and emits one correlated result within 15 minutes of blank boot.
- **SC-005**: Independent final inspection confirms every Feature 004 hostname, interface,
  address, routing identity, peer identity, and established-session invariant.
- **SC-006**: Two or more deliveries of the same accepted deployment request create exactly
  one logical downstream deployment result.
- **SC-007**: Lease renewal and repeated bootstrap retrieval alter no production intent and
  create no duplicate deployment in 100% of tested repetitions.
- **SC-008**: After one successful reboot, the device remains manageable, retains or restores
  100% of intended state, passes existing validation, and performs no destructive re-bootstrap.
- **SC-009**: Every temporary native-bootstrap failure exhausts only its pinned native bound;
  permanent native artifact/configuration failure never reaches handoff; each permanent
  finite-command mapping or identity failure stops on its first command attempt; and existing
  durable deployment activities retain their accepted retry policies.
- **SC-010**: No tested credential, raw bootstrap/production configuration, raw response, or
  stack content appears in normal events, workflow-safe data, logs, or evidence.
- **SC-011**: Teardown removes 100% of test-owned DHCP/bootstrap/topology resources while the
  supporting service/volume set, durable event/history evidence, and unrelated labs remain intact.
- **SC-012**: All accepted Feature 001 through 004 regression and replay suites pass, and
  repository review finds no generic provisioning framework or excluded service/scope.
- **SC-013**: Before any implementation task, evidence identifies one accessible supported
  bootable SR Linux artifact and records 100% of required provenance, pin, licensing,
  hypervisor, firmware, CPU, memory, disk, NIC, console, and cleanup fields; otherwise the
  feature records deferral and performs zero implementation.
- **SC-014**: On the selected runtime, the handoff boundary can read 100% of required native
  completion state, and evidence determines whether a representative post-operational gNMI
  change persists through guest reboot without save or requires the native save command.

## Assumptions

- Nokia R26.7 hardware documentation describes ordinary ZTP through DHCP options 66/67,
  Option 67 alone, or Option 43, but canonical T001 disproved automatic native-ZTP startup in
  the pinned container.
- Option 67 was configured as a complete HTTP URL but never delivered because the container
  emitted no DHCP discovery. Its URL acceptance, retrieval failure, malformed-artifact
  behavior, and native persistence remain unverified rather than failed individually.
- Native `/platform/chassis/serial-number` returned the same synthetic value on two nodes;
  generated chassis/card serial fields were empty. The preferred serial contract is
  unsuitable. T001 selected no fallback; the redesign selects boot-management MAC contingent
  on proof by the future genuine-runtime gate.
- The redesigned virtual identity is the selected runtime's deterministic boot-management
  MAC represented by core Nautobot `Interface.mac_address`; runtime stability is not yet proven.
- DHCP produced no lease in the isolated probes. Temporal remains the only planned durable
  execution state, but no deployment handoff was attempted.
- The second Feature 004 node may retain its existing hostname-only topology bootstrap only
  as a final BGP peer; the onboarding target itself may not use that shortcut.
- Later committed container configuration did not survive restart until `containerlab save`,
  but that mechanism does not apply to genuine-runtime acceptance. Native ZTP and later
  intended-state persistence remain runtime-gate measurements.
- No accessible supported SR Linux VM artifact, VM format, hypervisor profile, or resource
  requirement was established from public Nokia or current lab-tooling sources. The public
  simulator remains OCI-only; physical boot/recovery media are not assumed VM-compatible.
- Ordinary lab HTTP and username/password remain permitted only on an isolated bootstrap
  network; secure ZTP, certificate lifecycle, and production security are outside scope.
