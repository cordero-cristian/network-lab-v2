# Feature Specification: SR Linux Deployment And Operational Validation

**Feature Branch**: `004-srlinux-deployment-validation`

**Created**: 2026-09-10

**Status**: Implementation and canonical acceptance complete 2026-09-11

**Input**: User description: "Extend the accepted event-driven rendering path to deploy
the produced artifact to a real Nokia SR Linux lab target over gNMI, validate explicit
operational invariants, and publish correlated deployment outcomes."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Deploy And Validate Intended State (Priority: P1)

As a lab operator, I trigger a deployment request through the established automation
entry path for an SR Linux device
and receive a successful deployment outcome only after the rendered artifact has been
applied to the intended real device and independently validated against authoritative
intent.

**Why this priority**: This is the feature's core value and completes the accepted path
from intended state through real operational state.

**Independent Test**: On a minimal two-node SR Linux lab, submit one request for a
test-owned device and verify the deterministic artifact, device configuration and state,
required operational checks, and one correlated successful deployment outcome.

**Acceptance Scenarios**:

1. **Given** an SR Linux device represented in intended state with an authoritative
   management address and reachable peer, **When** a deployment request is submitted,
   **Then** the accepted path renders the artifact, deploys it to that exact device,
   validates the required system, interface, address, and routing invariants, and emits
   one correlated deployment-completed outcome.
2. **Given** a successful configuration write, **When** operational state has not yet
   converged, **Then** validation remains pending and retries within a bounded interval
   without redeploying the artifact.
3. **Given** a declared successful deployment, **When** an operator reads device state
   independently, **Then** the same intended hostname, loopback, routed interfaces,
   addresses, local routing identity, peers, and established peer state are observable.

---

### User Story 2 - Recover Without Duplicate Deployment (Priority: P2)

As a lab operator, I can safely redeliver a request or recover from an uncertain activity
response without creating a second logical workflow or contradictory device changes.

**Why this priority**: Device mutation raises the consequence of the duplicate-delivery
and recovery behavior already guaranteed by Feature 003.

**Independent Test**: Submit duplicate records with one request identity and simulate a
lost deployment response after the device accepted the change; verify one logical
workflow/deployment, an idempotent retry, no rerender during deployment retry, and no
redeployment during validation retry.

**Acceptance Scenarios**:

1. **Given** duplicate transport records for one request identity, **When** both are
   consumed, **Then** the existing durable identity policy produces one logical workflow
   and one logical deployment outcome.
2. **Given** the device accepted a configuration operation but the activity response was
   lost, **When** the deployment activity retries, **Then** the repeated declarative
   operation is safe and converges to the same intended state.
3. **Given** deployment completed and validation is retrying for convergence, **When** a
   check remains temporarily unsatisfied, **Then** rendering and deployment are not run
   again.

---

### User Story 3 - Receive Safe Actionable Failure Outcomes (Priority: P3)

As a lab operator, I receive a correlated, safely categorized failure when deployment or
validation cannot complete, so I can distinguish inventory, artifact, connectivity,
authentication, configuration, and operational-state failures without exposing secrets
or raw configuration.

**Why this priority**: A real-device workflow must fail predictably before or after
mutation and must never report a write alone as success.

**Independent Test**: Exercise isolated test-owned cases for an unreachable target,
invalid credentials, malformed or mismatched artifact, rejected configuration, and
validation mismatch; verify retry classification, safe result content, and device
mutation boundaries.

**Acceptance Scenarios**:

1. **Given** a missing, malformed, non-SR Linux, or target-mismatched artifact, **When**
   deployment is attempted, **Then** it fails permanently before any device mutation.
2. **Given** a temporarily unreachable device, **When** deployment begins, **Then**
   connection attempts retry within a bounded policy and eventually succeed or emit a
   safe connection failure.
3. **Given** invalid credentials or a deterministic configuration rejection, **When**
   the device responds, **Then** the failure is not blindly retried and a distinct safe
   deployment-failed outcome is emitted.
4. **Given** a successful write followed by a deterministic state mismatch, **When**
   bounded validation completes, **Then** deployment is not declared successful and a
   distinct validation failure is emitted.

---

### User Story 4 - Operate A Minimal Real Device Lab (Priority: P4)

As a developer, I can start, inspect, and stop a small test-owned SR Linux topology
separately from supporting application infrastructure and prove device connectivity
before running end-to-end acceptance.

**Why this priority**: Repeatable real-device evidence is required, while topology
lifecycle must remain separate from Kafka, Temporal, and Nautobot lifecycle.

**Independent Test**: Follow documented topology commands from a clean canonical host,
verify two nodes and their management endpoints, establish independent gNMI connectivity,
run acceptance, and stop only the test-owned topology.

**Acceptance Scenarios**:

1. **Given** the documented host prerequisites, **When** the topology is started,
   **Then** exactly the small required SR Linux test topology becomes reachable without
   changing supporting Compose data or unrelated network labs.
2. **Given** the topology is running, **When** its status and device connectivity are
   checked independently, **Then** both target identity and structured management access
   are confirmed before automation acceptance.
3. **Given** acceptance has completed, **When** the topology is stopped, **Then** only
   test-owned network nodes and resources are removed.

### Edge Cases

- The artifact exists at the deterministic path but its metadata, content identity, or
  device identity does not match the requested device.
- The management address is absent, ambiguous, malformed, or not attached as the target
  device's authoritative primary address.
- The device is reachable but identifies itself as a different host or unsupported NOS.
- The connection fails before a write, during a write, or after a successful write but
  before the activity response is recorded.
- A write is accepted partially or rejected with a structured permanent error.
- The device requires time for interfaces or routing sessions to converge after the
  configuration operation succeeds.
- A physical interface is intentionally down because the minimal topology has no peer;
  acceptance must not misrepresent that state as meaningful operational success.
- The expected routing peer exists in intent but is absent, has the wrong peer identity,
  or remains non-established after the convergence bound.
- A deployment or validation failure message contains credentials, raw configuration,
  or unsafe device response content.
- A duplicate request arrives while the workflow is running or after its retained
  execution has closed.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST add an explicitly versioned deployment request to the
  existing Feature 003 consumer and durable execution path rather than reinterpret a
  retained render-only request or create a parallel orchestration path.
- **FR-002**: The system MUST obtain intended state through Feature 002's accepted
  Nautobot boundary and MUST use Feature 002 as the sole rendering implementation.
- **FR-003**: The deployment preparation activity MUST produce and bind the complete
  deterministic artifact through Feature 002's sole renderer, and later deployment
  attempts MUST consume exactly those digest-identified bytes without rerendering.
- **FR-004**: Before device mutation, the system MUST verify that the artifact exists,
  is complete and supported, and belongs to the requested device.
- **FR-005**: Artifact/deployment identity MUST use the deterministic path, requested
  device identity, and a stable content digest without adding an artifact database or
  service.
- **FR-006**: The target device MUST be Nokia SR Linux; no other network operating
  system is supported by this feature.
- **FR-007**: Device configuration and state access MUST use gNMI as the application
  transport, with no SSH, CLI scraping, container shell, or container-exec fallback.
- **FR-008**: Device access MUST remain isolated from domain models and durable workflow
  logic behind explicit external-operation activities.
- **FR-009**: The target management address MUST come from an authoritative core
  Nautobot device relationship, not workflow code or an environment address map.
- **FR-010**: Missing, ambiguous, or invalid authoritative management addressing MUST
  fail before device mutation with a stable safe category.
- **FR-011**: The system MUST verify the connected device identity matches the requested
  target before applying configuration.
- **FR-012**: Device credentials and required connection policy MUST come from local-lab
  settings or environment and MUST NOT be stored in events, workflow history, artifacts,
  logs, or source defaults containing secrets.
- **FR-013**: Configuration application MUST use the pinned SR Linux release's supported
  structured configuration operation and MUST surface structured rejection distinctly.
- **FR-014**: The selected configuration operation MUST be declarative and safe to repeat
  after an uncertain successful result, with its actual idempotency limits documented.
- **FR-015**: A successful configuration write MUST NOT itself produce a successful
  deployment outcome.
- **FR-016**: Operational validation MUST query structured device state independently
  from artifact text and compare explicit intended invariants rather than entire
  datastores or generated configuration dumps.
- **FR-017**: System validation MUST confirm the observed hostname equals the intended
  device name.
- **FR-018**: Loopback validation MUST confirm expected existence, administrative and
  operational state, and expected IPv4 addressing.
- **FR-019**: Routed-interface validation MUST confirm each modeled physical interface
  and subinterface, expected IPv4 addressing, intended administrative state, and
  operational state where the real topology makes it meaningful.
- **FR-020**: Routing validation MUST confirm local autonomous-system identity, expected
  neighbors, each remote autonomous-system identity, and established state when a real
  peer is part of the topology.
- **FR-021**: Validation MUST return one small typed device result containing device
  identity, overall status, and explicit checks with name, status, expected, observed,
  and safe message.
- **FR-022**: Temporary post-change convergence MUST be retried or polled within explicit
  bounds without arbitrary unbounded sleep.
- **FR-023**: Validation retry MUST NOT rerender or redeploy configuration.
- **FR-024**: Transient connection timeout, temporary refusal, and temporary convergence
  failures MUST be distinguishable from permanent failures and use bounded retries.
- **FR-025**: Invalid artifacts, target mismatch, authentication failure, unsupported
  configuration shape, deterministic configuration rejection, and deterministic final
  validation mismatch MUST not be blindly retried.
- **FR-026**: The existing running-conflict and retained closed-execution identity
  policies MUST continue to provide one logical workflow for duplicate request delivery.
- **FR-027**: Deployment activity retry after an uncertain result MUST converge on the
  same intended configuration without creating contradictory or additive changes.
- **FR-028**: A successful execution MUST emit one correlated logical deployment-
  completed outcome containing event, correlation, workflow, device, artifact, deployment
  timestamp, and validation status identifiers.
- **FR-029**: A failed deployment or validation MUST emit one correlated logical
  deployment-failed outcome containing a stable category and safe bounded message.
- **FR-030**: Existing render completion and failure event meanings MUST remain unchanged;
  deployment outcomes MUST use intentionally distinct versioned contracts and topics.
- **FR-031**: Individual validation checks MUST NOT be emitted as separate transport
  events, and deployment MUST NOT introduce event choreography inside the durable
  execution already owning the sequence.
- **FR-032**: Logs for deployment and validation MUST include safe event, correlation,
  workflow, device, activity, target, and check/category context where available and MUST
  exclude credentials and raw configuration.
- **FR-033**: The existing automation worker MUST register the new external-operation
  activities; no deployment-specific worker or API service may be added.
- **FR-034**: The existing consumer MUST remain thin and change only where the intentional
  event contract evolution requires it.
- **FR-035**: The real lab MUST use the smallest practical two-node SR Linux topology that
  can prove routed-interface and established peer state.
- **FR-036**: Network topology lifecycle MUST remain explicit and separate from supporting
  Compose infrastructure lifecycle.
- **FR-037**: Integration setup MUST represent each real test device in Nautobot with its
  authoritative management identity and MUST create, modify, and remove only test-owned
  records and topology resources.
- **FR-038**: Real acceptance MUST independently confirm gNMI connectivity and resulting
  device state in addition to observing the correlated deployment outcome.
- **FR-039**: Real acceptance MUST prove unreachable target, safe authentication failure,
  safe isolated configuration rejection where supported, and operational validation
  mismatch without destabilizing shared infrastructure.
- **FR-040**: Unit tests MUST isolate the gNMI boundary and cover settings, management
  address extraction, artifact and target checks, request construction, error classes,
  typed validation, individual invariants, safe serialization, workflow ordering, and
  retry separation without creating a fake network-operating-system framework.
- **FR-041**: Feature 001 service integration, Feature 002 real rendering, and Feature 003
  execution regressions MUST remain healthy after this feature.
- **FR-042**: The feature MUST NOT add DHCP, ZTP, device discovery/onboarding, rollback,
  approvals, maintenance windows, ticketing, backup, multi-vendor abstractions, generic
  compliance, telemetry platforms, APIs, web interfaces, Kubernetes, cloud orchestration,
  high availability, or production security architecture.

### Key Entities

- **Deployment Target**: Requested SR Linux device identity plus the authoritative
  management address and connection policy needed to reach exactly that device.
- **Artifact Identity**: Deterministic path, requested device identity, and content digest
  identifying the complete Feature 002 output supplied to deployment.
- **Deployment Request**: Internal activity input containing only safe identifiers,
  target address, artifact identity, and required intended invariants; credentials remain
  worker-local settings.
- **Deployment Result**: Safe record of target, artifact identity, write completion time,
  and information needed to begin independent validation.
- **Validation Check**: One named intended invariant with pass/fail status, expected and
  observed safe values, and an optional bounded safe message.
- **Device Validation Result**: Device identity, overall pass/fail status, and the bounded
  set of explicit validation checks.
- **Deployment Outcome Event**: One versioned completed or failed fact correlated to the
  original request and durable workflow, without credentials or raw configuration.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A request for a healthy test-owned device completes the full accepted path
  and produces one correlated successful deployment outcome within 5 minutes after the
  two-node lab and supporting services are healthy.
- **SC-002**: Independent post-execution inspection confirms 100% of specified hostname,
  loopback, routed-interface, address, local routing identity, neighbor identity, and
  established-session invariants on the minimal real topology.
- **SC-003**: Two deliveries of the same request identity result in exactly one logical
  workflow, one logical deployment, and one logical deployment outcome.
- **SC-004**: Retrying a deployment after a simulated lost successful response leaves the
  device in the same intended state and does not create duplicate or additive
  configuration.
- **SC-005**: Temporary validation non-convergence retries for no more than the documented
  bound and never causes an additional render or deployment operation.
- **SC-006**: Each required failure case produces the correct stable category and no
  credential or raw configuration appears in emitted outcomes or normal logs.
- **SC-007**: Missing, malformed, unsupported, or target-mismatched artifacts cause zero
  device mutation attempts in 100% of tested cases.
- **SC-008**: A deterministic device rejection is attempted once per workflow activity
  execution and is not repeated by the durable retry policy.
- **SC-009**: A developer can start, inspect, and stop the minimal topology using the
  documented separate lifecycle commands without resetting any supporting persistent
  volume or unrelated lab resource.
- **SC-010**: All existing default tests and the real acceptance paths for Features
  001-003 continue to pass after the deployment capability is added.
- **SC-011**: Repository review finds one SR Linux-specific device boundary and no generic
  vendor registry, driver hierarchy, plugin loader, new worker service, DHCP/ZTP code, or
  other excluded framework or service.

## Assumptions

- The pinned SR Linux release exposes supported gNMI configuration and structured state
  operations sufficient for the required invariants; planning research will verify exact
  paths, encoding, transaction behavior, and error semantics before implementation.
- A two-node point-to-point SR Linux topology is the smallest topology that can prove a
  meaningful established routing session and both ends' physical operational state.
- Nautobot core primary-IP relationships can authoritatively identify management
  addresses without a custom application; planning research will define the exact
  extraction rule and integration fixture behavior.
- Local-lab credentials may be shared across the two disposable test nodes and supplied
  through environment settings; production credential lifecycle is outside scope.
- Feature 003's render request topic, workflow input, identity, activity sequence, and
  result semantics remain compatible. A distinct deployment request is additive and uses
  the same consumer, workflow class, worker, sole Feature 002 renderer, and durable identity
  policies, but a deployment-specific preparation activity and outcomes.
- Topology creation and destructive failure tests use isolated, test-owned resources on
  the canonical Ubuntu host and do not reset Kafka, Temporal, Nautobot, or Compose volumes.
- The topology layer bootstraps only each node's expected hostname identity plus the
  management and gNMI access supplied by containerlab. Nautobot and automation remain
  authoritative for loopback, routed-interface, BGP, policy, and all other intended state.
  This narrow identity bootstrap is not DHCP, ZTP, discovery, or onboarding.
- The accepted three-day Temporal history retention continues to bound duplicate
  protection after a workflow closes.
