# Feature Specification: Nautobot Intent To Deterministic SR Linux Artifact

**Feature Branch**: `002-nautobot-srlinux-artifact`

**Created**: 2026-09-09

**Status**: Approved for implementation on 2026-09-09 with required adjustments

**Input**: Read a small Nokia SR Linux device intent from Nautobot, validate and
normalize it into explicit internal models, render deterministic configuration,
and write a generated artifact without event transport, workflow orchestration,
device access, or zero-touch provisioning.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Produce A Reviewed Device Artifact (Priority: P1)

A network automation developer names a known device whose intended state is held
in Nautobot and receives a complete, reviewable SR Linux configuration artifact.
The developer does not manually translate API data or enter device state twice.

**Why this priority**: This is the first useful intent-to-configuration vertical
slice and proves that Nautobot remains the source of intended state.

**Independent Test**: Render the offline `leaf01` intent and compare it byte-for-byte
with the reviewed expected configuration. Separately create a uniquely named real
Nautobot fixture and prove the same production path without contacting a device.

**Acceptance Scenarios**:

1. **Given** a test-owned SR Linux device with a loopback, two addressed routed
   interfaces, a local ASN, and two BGP neighbors, **When** the developer requests
   its artifact, **Then** one deterministic file contains the expected hostname,
   interfaces, default network instance, and BGP configuration.
2. **Given** the same intended state, **When** the artifact is produced repeatedly,
   **Then** every output is byte-identical and ends with one newline.
3. **Given** existing Nautobot state, **When** a uniquely named and marked integration
   fixture is created and removed, **Then** only objects whose IDs were recorded by
   that test run change.

---

### User Story 2 - Reject Invalid Intent Safely (Priority: P2)

A developer receives a clear failure before rendering when the requested device
state is missing, malformed, ambiguous, internally inconsistent, or unsupported.
An unsuccessful request never leaves a partial or corrupt artifact.

**Why this priority**: A deterministic artifact is useful only when invalid
external state cannot bypass the validated internal boundary.

**Independent Test**: Supply invalid and unsupported sample states without running
Nautobot and verify each fails before template rendering or artifact replacement.

**Acceptance Scenarios**:

1. **Given** a missing platform or loopback, malformed IPv4 value, invalid ASN,
   duplicate interface name, or duplicate neighbor address, **When** conversion is
   attempted, **Then** it fails with an error that identifies the invalid field or
   invariant.
2. **Given** a neighbor address equal to an interface's local host address, **When**
   conversion is attempted, **Then** it is rejected as inconsistent intent.
3. **Given** a valid device for an unsupported platform, **When** rendering is
   requested, **Then** rendering fails explicitly and no artifact is replaced.
4. **Given** any retrieval, validation, or rendering failure, **When** an artifact
   already exists, **Then** that complete prior artifact remains unchanged.

---

### User Story 3 - Develop And Verify Without Infrastructure (Priority: P2)

A Python developer can review and test normalization, validation, ordering,
rendering, and artifact naming without Docker or a live Nautobot instance, while
an explicit integration test proves the real Nautobot-to-artifact boundary.

**Why this priority**: Fast isolated tests are required for safe model and template
changes, but mocks alone are insufficient evidence for the external integration.

**Independent Test**: Run the unit suite with infrastructure stopped, then select
the integration test against Feature 001 Nautobot and observe that missing real
infrastructure fails rather than skips.

**Acceptance Scenarios**:

1. **Given** Docker and Nautobot are unavailable, **When** unit tests run, **Then**
   all model, conversion, rendering, ordering, naming, and atomic-write tests pass.
2. **Given** the healthy canonical Nautobot lab, **When** the integration test runs,
   **Then** it creates identifiable test-owned intent, reads it through the same
   adapter used by the command, validates it, renders a deterministic artifact for
   its unique name, and cleans up only its own objects.
3. **Given** Nautobot is unavailable, **When** the integration test is explicitly
   selected, **Then** it fails visibly rather than reporting success or skipping.

### Edge Cases

- No device or more than one device matches the requested exact name.
- A related platform, role, location, interface, or address is absent or malformed.
- The loopback source name varies, or the virtual loopback is duplicated, absent,
  disabled, management-only, multiply addressed, or not a `/32` host prefix.
- An enabled, non-management physical interface has no address, multiple IPv4
  addresses, only IPv6 state, or a non-physical interface type.
- Interface and neighbor collections arrive in different external orders.
- A name is empty or unsafe for deterministic artifact naming.
- The artifact directory is absent, unwritable, or already contains a valid file;
  staging or atomic replacement fails after a temporary file is created.
- The external request times out or returns an authentication/server error.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST retrieve exactly one requested device and its required
  related intended state from the existing canonical Nautobot instance.
- **FR-002**: The external adapter MUST return raw external data; raw external maps
  MUST NOT be passed directly to configuration templates.
- **FR-003**: The system MUST convert external data into an explicit validated device
  intent containing name, stable platform identifier, optional platform display
  label, role, optional location, one name-independent loopback, addressed routed
  interfaces, local BGP ASN, and neighbors with address, remote ASN, and optional
  description.
- **FR-004**: IPv4 interface/address values and ASNs MUST be validated using their
  actual numeric and address semantics before rendering. Supported ASNs are 1
  through 4294967295.
- **FR-005**: Validation MUST reject empty required names, unsafe device names,
  duplicate interface names, duplicate neighbor addresses, absent/ambiguous
  loopback data, and neighbor addresses equal to local interface host addresses.
  Exactly one source interface MUST be enabled, non-management, type `virtual`, and
  `/32`; its external name MUST NOT become an internal loopback identity. Every other
  enabled, non-management interface MUST have a physical type and exactly one IPv4
  address; disabled interfaces are outside this initial intent.
- **FR-006**: The rendering entry point MUST reject every platform except the one
  explicitly supported stable Nokia SR Linux identifier. Display labels MUST NOT
  control dispatch.
- **FR-007**: Rendering MUST consume only validated normalized intent and MUST keep
  ordering and configuration decisions outside templates.
- **FR-008**: The generated SR Linux configuration MUST include system hostname,
  the supported SR Linux `system0` loopback and routed interface addressing/
  descriptions, attachment of those
  subinterfaces to the default network instance, and BGP autonomous-system,
  router-ID, neighbor peer-AS, and available peer descriptions.
- **FR-009**: Output MUST have stable interface and neighbor ordering, stable
  whitespace, no volatile values, and exactly one trailing newline so identical
  intent produces byte-identical content. Ordering MUST include a full-name
  tie-breaker independent of external collection order.
- **FR-010**: The system MUST derive a deterministic generated artifact path from
  the validated device name and MUST not commit generated artifacts by default.
- **FR-011**: Artifact replacement MUST be atomic and occur only after successful
  retrieval, validation, and rendering; a failed run MUST NOT create a partial file
  or replace a prior complete artifact. Missing output directories MUST be created;
  failed staging/replacement MUST remove temporary files. Process-level atomicity,
  not crash-durable filesystem persistence, is required.
- **FR-012**: A simple command MUST accept a device name, run the complete
  Nautobot-to-artifact path, print the resulting path on success, avoid printing
  credentials, and return nonzero with a useful error on failure.
- **FR-013**: Unit tests MUST cover valid and invalid intent, deterministic ordering,
  reviewed expected output, repeated byte identity, unsupported platform, artifact
  naming, failed-write safety, and zero/multiple lookup, pagination, malformed/error
  response, timeout, and related-address retrieval failures without infrastructure.
- **FR-014**: An explicitly selected integration test MUST create identifiable,
  repeatable Nautobot fixtures, exercise the same production adapter/conversion/
  rendering/artifact path, perform no device access, and clean only test-owned state.
- **FR-015**: The feature MUST remain within one Python package and MUST NOT add an
  event producer/consumer, workflow/activity, device-access code, custom Nautobot
  App, zero-touch provisioning, vendor abstraction framework, or future-feature
  scaffolding.

### Key Entities

- **Device intent**: Validated intended state for one device, including identity,
  platform/role/location metadata, loopback, routed interfaces, and BGP intent.
- **Interface intent**: One named interface with a non-empty description where
  required and exactly one IPv4 interface address for this initial slice.
- **BGP intent**: One valid local ASN and an ordered collection of unique neighbors.
- **BGP neighbor intent**: Unique peer IPv4 address, valid remote ASN, and optional
  non-empty peer description.
- **Raw Nautobot device data**: External device, interface, address, metadata, and
  BGP-specific values prior to validation; never a rendering input.
- **Configuration artifact**: Complete generated text for one validated device at
  a deterministic path; it is derived output, not Nautobot-owned intent.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The documented offline `leaf01` intent produces the reviewed expected
  configuration, and a uniquely named real Nautobot fixture produces its own complete
  artifact with no manual transformation or network-device connection.
- **SC-002**: One hundred repeated renders of the same normalized intent are
  byte-identical, including ordering, whitespace, and final newline.
- **SC-003**: Every required invalid/unsupported case fails before artifact
  replacement, and zero tested failures leave a new partial or corrupt file.
- **SC-004**: All feature unit tests pass with Docker and Nautobot stopped, while
  explicitly selected integration tests fail when their real dependency is absent.
- **SC-005**: The real integration test proves all four boundaries in order:
  Nautobot data, validated internal intent, rendering, and generated artifact.
- **SC-006**: Repository review finds zero device-access, Kafka application,
  Temporal application, ZTP, custom Nautobot App, or speculative plugin/framework
  components introduced by Feature 002.

## Out Of Scope

Device deployment or operational validation; Kafka production/consumption;
Temporal workflows/activities/workers; DHCP/ZTP; custom Nautobot Apps; rendered
configuration storage in Nautobot; generic vendor abstractions; VLANs, EVPN, VXLAN,
MPLS, ISIS, routing policy, ACLs, QoS, services, and non-default VRFs/network
instances; a complete leaf/spine topology; IPv6; multiple addresses per interface;
and production authentication or secrets management.

## Assumptions

- Feature 001 and its canonical Nautobot instance remain unchanged and available
  for explicitly selected integration testing.
- Offline `leaf01` has one virtual `/32` loopback source interface, two addressed
  routed interfaces, and two BGP neighbors. Its golden output uses SR Linux `system0`.
- Role and location are intent metadata. They need not produce SR Linux commands in
  this slice unless a direct initial configuration requirement is identified.
- The loopback host address is the BGP router identifier.
- One IPv4 address per modeled interface is sufficient for the initial slice.
- Every integration object is API-created with a per-run suffix, including the
  Device name `feature002-leaf-<suffix>`, serial marker, Status, Namespace, and
  dependencies. No existing intent object is reused or mutated; cleanup addresses
  only IDs recorded by that run. Immutable ContentType identifiers may be read only
  as required by Nautobot's object-creation schema.
- The approved namespaced BGP context is a Feature 002 contract, not a permanent
  architecture decision for future intent models.
