# Feature Specification: Event-Driven Durable Execution

**Feature Branch**: `003-event-driven-execution`

**Created**: 2026-09-09

**Status**: Implementation approved 2026-09-09

**Input**: Accept one versioned render-request event, durably coordinate the existing
Nautobot-to-SR-Linux-artifact path, and publish one correlated completion or safe
failure result without device access, deployment, or zero-touch provisioning.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Render From An External Event (Priority: P1)

A network automation developer publishes one valid request naming a Nautobot device
and observes that durable automation produces the same deterministic configuration
artifact as the existing direct rendering path, followed by a correlated completion
event.

**Why this priority**: This is the first complete event-driven execution slice and
proves the intended ownership chain without adding device execution.

**Independent Test**: Publish a uniquely identified request for a uniquely named,
test-owned Nautobot device and observe one durable execution, the expected artifact,
and one completion carrying the original correlation identifier.

**Acceptance Scenarios**:

1. **Given** a valid version-1 request and valid Nautobot intent, **When** the request
   is consumed, **Then** durable execution accepts it before its transport offset is
   acknowledged, produces the deterministic artifact, and publishes a completion.
2. **Given** the same intended state used by the direct rendering path, **When** it is
   rendered through event-driven execution, **Then** the artifact bytes and path are
   identical to direct rendering output.
3. **Given** a completion event, **When** a developer inspects it, **Then** its logical
   event contains a new event identifier, the original correlation identifier and device name, the
   durable execution identifier, artifact path, version, type, and UTC completion time.

---

### User Story 2 - Survive Duplicate And Transient Delivery (Priority: P1)

A duplicate transport delivery or temporary external failure does not create a
second logical render request, lose the request, corrupt an artifact, or rerun
completed rendering merely because result publication must be retried.

**Why this priority**: At-least-once delivery and transient faults are normal. The
path is not durable unless repeated delivery and recovery have explicit behavior.

**Independent Test**: Deliver one request twice and inject a temporary result-publication
failure; observe one logical execution identity, one valid artifact, and eventual
publication without a second render step.

**Acceptance Scenarios**:

1. **Given** the same request event is delivered more than once, **When** each copy is
   handled, **Then** every copy resolves to the same logical execution identity.
2. **Given** durable execution has not accepted a request, **When** coordination is
   temporarily unavailable, **Then** the request offset is not acknowledged and the
   same request remains eligible for handling.
3. **Given** an artifact has been written and completion publication temporarily
   fails, **When** publication is retried, **Then** rendering and artifact writing are
   not unnecessarily repeated.
4. **Given** a transient retrieval, filesystem, or result-publication failure,
   **When** its bounded retry policy applies, **Then** retry attempts are observable
   and permanent validation failures are not retried.

---

### User Story 3 - Report Permanent Failure Safely (Priority: P2)

A developer receives a stable, correlated failure result when accepted automation
cannot render a valid artifact, without secrets, raw external data, or stack traces.
Malformed transport messages are isolated so one poison message does not terminate
the consumer or block later valid requests.

**Why this priority**: Failure must be externally visible and safe, while invalid
untrusted messages must not enter durable execution.

**Independent Test**: Submit one valid request whose intent is permanently invalid,
then one malformed message and one valid request; observe a safe failure result for
the accepted request, an explicit invalid-message record, and continued processing.

**Acceptance Scenarios**:

1. **Given** an accepted request has invalid intent or unsupported rendering state,
   **When** execution reaches that permanent failure, **Then** it publishes one logical
   failure event with stable category, safe message, correlation and execution identifiers.
2. **Given** a malformed, unknown-type, or unsupported-version transport message,
   **When** the consumer validates it, **Then** no workflow starts, the message is
   reported without raw secrets, and the consumer continues to later messages.
3. **Given** failure-result publication is temporarily unavailable, **When** retry is
   possible, **Then** publication is retried without repeating failed render work.

---

### User Story 4 - Run And Verify The Two Processes (Priority: P2)

A developer can run one automation worker and one event consumer reproducibly in the
existing lab, publish a request with one small developer command, and test most event,
consumer, workflow, and retry behavior without the canonical infrastructure.

**Why this priority**: The first durable path must remain understandable and locally
testable while real acceptance still proves all external boundaries.

**Independent Test**: Run isolated model/consumer/workflow tests without the lab;
then start exactly one worker and one consumer in the canonical lab and execute the
full real path.

**Acceptance Scenarios**:

1. **Given** no Kafka, workflow service, or Nautobot, **When** unit and supported
   workflow-environment tests run, **Then** event validation, identity, ordering,
   retries, duplicate handling, and safe failures are verified without fake engines.
2. **Given** the healthy canonical lab and two automation processes, **When** the
   developer request command names a valid test-owned device, **Then** it prints the
   request and correlation identifiers and the full path completes.
3. **Given** any required external component or automation process is absent, **When**
   its explicit integration test runs, **Then** the test fails rather than skips or
   reports false success.

### Edge Cases

- A message is not JSON, is not an object, has unknown fields, has the wrong event
  type/version, contains invalid identifiers, a non-UTC timestamp, or an unsafe device name.
- Two deliveries of one event arrive while its execution is running, after it succeeds,
  or after it permanently fails.
- Durable execution accepts a start but the consumer loses the response before offset
  acknowledgement.
- A later message from the same partition must not cause an earlier unaccepted offset
  to be skipped.
- Retrieval or artifact writing fails transiently; validation or platform dispatch
  fails permanently.
- Artifact writing succeeds but the activity response is lost and the activity is retried.
- Artifact writing succeeds and result publication is temporarily unavailable.
- Completion or failure publication exhausts its bounded retry policy.
- Worker or consumer restarts while a request is running.
- Separate event IDs request the same device concurrently and target the same
  deterministic artifact path.
- Logs or failure events receive an exception whose text contains credentials or raw data.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST accept only the three Feature 003 event types
  `network.render.requested`, `network.render.completed`, and `network.render.failed`,
  each at explicit version 1, without introducing a generic event envelope.
- **FR-002**: Every event MUST have a unique UUID event identifier, one UUID
  correlation identifier propagated from request to result, an exact device name,
  and an event-specific UTC timestamp. Unknown fields, types, versions, malformed
  identifiers, unsafe names, and non-UTC timestamps MUST fail validation.
- **FR-003**: A render request MUST contain exactly `event_type`, `event_version`,
  `event_id`, `correlation_id`, `device_name`, `requested_at`, and `source`; source is
  non-empty diagnostic text and does not select behavior.
- **FR-004**: A completion MUST additionally identify the durable execution, exact
  deterministic artifact path, and UTC completion time. A failure MUST instead carry
  the durable execution, stable error category, safe non-empty message, and UTC
  failure time.
- **FR-005**: Request, completion, and failure events MUST NOT contain credentials,
  raw external responses, rendered configuration, or stack traces.
- **FR-006**: The system MUST use only three configurable transport topics matching
  the event types and one explicit configurable consumer group. The three configured
  topic names MUST be distinct. It MUST NOT add per-step topics or use transport
  messages to choreograph workflow steps.
- **FR-007**: The consumer MUST deserialize and validate each request before durable
  execution and MUST NOT query Nautobot, render templates, write artifacts, classify
  workflow retries, access devices, or publish successful workflow results itself.
- **FR-008**: The consumer MUST disable automatic offset acknowledgement and MUST
  acknowledge a valid request only after durable execution is confirmed started or
  already exists under the request's deterministic execution identifier.
- **FR-009**: A failure to durably accept a valid request MUST leave its offset
  unacknowledged and MUST prevent a later acknowledged offset from skipping it.
- **FR-010**: Invalid transport messages MUST start no workflow, be logged with safe
  topic, partition, offset, parseable event ID, and validation/error category context,
  be acknowledged as poison messages, and MUST NOT stop processing later messages.
  Logs MUST NOT include an arbitrary full raw payload or secrets by default. Invalid
  messages do not produce failure events because they have no trusted request or
  execution identity.
- **FR-011**: One request MUST map to the deterministic durable execution identifier
  `render-device-config:<event_id>`. For a running execution, the Temporal workflow-ID
  conflict policy MUST use that existing execution. Separately, for a closed execution,
  the Temporal workflow-ID reuse policy MUST reject a new execution for the configured
  namespace retention period. A new logical request requires a new event identifier.
  Replay after retained workflow history expires is out of scope.
- **FR-012**: Durable execution input MUST contain only request event ID, correlation
  ID, and device name. It MUST NOT contain raw Nautobot responses or rendered text.
- **FR-013**: One deterministic workflow MUST coordinate rendering and result
  publication. It MUST perform no direct HTTP, transport I/O, filesystem I/O,
  ordinary wall-clock read, ordinary random UUID generation, Nautobot access, or
  template rendering.
- **FR-014**: One rendering activity MUST invoke the existing Feature 002
  Nautobot-to-validated-intent-to-render-to-atomic-artifact path rather than duplicate
  adapter, model, renderer, template, or writer behavior, and return only artifact metadata.
- **FR-015**: Completion publication MUST be a separate activity after successful
  artifact creation so its retry does not repeat rendering. Permanent rendering
  failure MUST similarly invoke a separate failure-publication activity.
- **FR-016**: Workflow-created result event identifiers and timestamps MUST use
  deterministic workflow-safe facilities and remain unchanged across publication retries.
- **FR-017**: Retry policies MUST be explicit and bounded. Temporary connection,
  server throttling/unavailability, filesystem, and result-publication failures are
  retryable; malformed event/intent, authentication/authorization, unsupported
  platform, and deterministic rendering failures are non-retryable.
- **FR-018**: A rendering activity retry after an uncertain completion MAY atomically
  rewrite the same deterministic artifact, but MUST NOT produce a partial artifact.
  Separate result-publication retries MUST never invoke rendering again.
- **FR-019**: Exhausted or non-retryable render failure MUST produce a failure event
  with one documented stable category and safe message derived without raw stack data.
  If failure-event publication exhausts retries, the workflow MUST visibly fail.
- **FR-020**: Result transport is at least once. Publication uncertainty MAY produce
  duplicate physical result records, but all copies for one workflow outcome MUST use
  the same result event ID and payload; Kafka exactly-once guarantees are not claimed.
- **FR-021**: Structured process logs MUST include available event ID, correlation ID,
  durable execution ID, and device name, while excluding credentials and raw payloads.
- **FR-022**: One worker process MUST register the sole render workflow and required
  activities on one configurable task queue. One separate consumer process MUST
  bridge request transport to durable workflow starts. Both MUST use the existing
  Python package and runtime.
- **FR-023**: A developer command MUST construct a valid request using new UUIDs and
  current UTC time, publish it durably, print event/correlation/execution identifiers,
  and return nonzero with a safe message when publication fails.
- **FR-024**: The existing lab MAY add only `automation-worker` and `event-consumer`
  application services plus the minimum single shared application image/build and
  artifact mount required to run them reproducibly. No new database, broker, proxy,
  UI, supervisor, gateway, or monitoring service is permitted.
- **FR-025**: Unit tests MUST cover all event models, strict version/type/time
  validation, deterministic execution identity, safe error categories, consumer
  acknowledgement and duplicate behavior, poison-message continuation, workflow
  activity ordering, result correlation, and publication retry isolation using the
  supported workflow test environment rather than a fake workflow engine.
- **FR-026**: Explicit integration tests MUST independently prove request transport,
  real worker execution, the real Feature 002 Nautobot-backed rendering path, and
  result transport before proving the complete end-to-end chain.
- **FR-027**: Full integration MUST use unique request/correlation identifiers,
  uniquely suffixed test-owned Nautobot fixtures and artifact targets, delete only
  recorded test-owned resources, and fail rather than skip when any required external
  component or process is unavailable.
- **FR-028**: At least one real safe transient failure MUST be proven when practical.
  If no isolated transient can be induced without risking persistent lab state, the
  limitation MUST be documented and retry behavior MUST instead be proven with the
  supported workflow test environment and mocked external boundaries.
- **FR-029**: Feature 001 service checks and tests and all Feature 002 model, adapter,
  rendering, artifact, CLI, and real Nautobot integration tests MUST remain healthy.
- **FR-030**: The feature MUST remain one Python package with one worker and one
  consumer process and MUST NOT add device access, deployment, rollback, operational
  validation, DHCP/ZTP, multi-vendor behavior, generic event/workflow abstractions,
  an API/web service, schema registry, replay tooling, or future-feature scaffolding.
- **FR-031**: Task granularity MUST NOT produce implementation layers. The resulting
  code MUST stay approximately three event models, one consumer, one workflow, two
  activities, one worker, one small request CLI, minimal shared configuration, and two
  profile-gated runtime services, with no registries, factories, base event classes,
  generic workflow abstractions, repositories, service layers, or additional processes.

### Key Entities

- **Render request event**: Version-1 instruction naming one device and carrying
  unique event/correlation identifiers, UTC request time, and diagnostic source.
- **Render completion event**: Version-1 correlated result naming the execution and
  deterministic artifact path.
- **Render failure event**: Version-1 correlated safe failure with stable category,
  no raw exception or secret data, and no artifact success claim.
- **Render workflow input**: Small immutable request identity containing only event
  ID, correlation ID, and device name.
- **Render execution**: One durable, duplicate-resistant coordination instance whose
  identifier is derived from the request event ID.
- **Artifact metadata**: Device name and deterministic path returned after the existing
  Feature 002 path has atomically completed.
- **Transport offset**: Topic/partition/offset position acknowledged only after the
  request is invalid-and-isolated or its durable execution is accepted/already present.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: One valid test request completes the full external-event-to-correlated-result
  path and produces artifact bytes identical to direct Feature 002 rendering.
- **SC-002**: Delivering the same request event at least twice creates exactly one
  durable execution identifier and never creates two logical renders.
- **SC-003**: A forced temporary completion-publication failure causes at least one
  publication retry and zero additional render-activity invocations.
- **SC-004**: Every tested permanent render failure produces at least one safe logical
  correlated failure result, any duplicate physical records share one event ID, and
  zero result events or logs expose test credentials, raw payloads, rendered
  configuration, or stack traces.
- **SC-005**: A malformed message followed by a valid request results in zero workflow
  starts for the malformed message and successful processing of the valid request.
- **SC-006**: All event, consumer, workflow, activity-classification, and CLI unit tests
  pass without Kafka, Temporal, Nautobot, the worker process, or consumer process.
- **SC-007**: Explicit component integrations and the end-to-end integration fail when
  required infrastructure is absent and pass on the canonical Ubuntu lab with every
  test-owned Nautobot object and artifact removed afterward.
- **SC-008**: One accepted workflow remains durable across a worker restart and
  completes without a second logical execution; one uncommitted request remains
  available across a consumer restart and is then accepted under its deterministic
  workflow ID within the configured retention period.
- **SC-009**: Existing Feature 001 and Feature 002 test and health commands retain
  their accepted outcomes after Feature 003 is enabled.
- **SC-010**: Repository review finds exactly one automation worker process, one event
  consumer process, three event types/topics, and zero forbidden device, ZTP, generic
  framework, extra infrastructure, or future-feature components.

## Out Of Scope

Network-device access; configuration push, rollback, or post-deployment validation;
DHCP/ZTP and device onboarding; multi-vendor workflows; generic workflow-engine or
event-bus abstractions; API or web servers; web UI; Kubernetes; cloud orchestration;
monitoring stacks; production secrets management; schema registry; Kafka exactly-once
semantics; broad replay tooling; per-step topics; event-driven Nautobot updates; and
any event or workflow type other than the three Feature 003 events and one render flow.

## Assumptions

- Features 001 and 002 are accepted baselines. Feature 003 may call their public
  settings and rendering interfaces but does not move or duplicate their working code.
- Kafka provides at-least-once delivery; deterministic workflow identity and atomic
  artifact replacement provide the required idempotency without claiming exactly once.
- A duplicate request with an event ID whose workflow is retained remains the same
  completed or failed logical request; an operator submits a new event ID to request
  new work. Replay after Temporal's configured 3-day history retention is explicitly
  excluded rather than supported with a new deduplication store.
- Invalid transport payloads are acknowledged after safe logging to avoid a poison
  partition loop. No failure event is emitted because identifiers in invalid input are
  not trusted and the required workflow identifier does not exist.
- Separate valid event IDs for the same device may observe different Nautobot intent.
  Each writes the same deterministic path atomically; serializing requests per device
  or preserving artifact history is not part of this feature.
- Result publication is considered complete only after broker delivery confirmation.
  A workflow whose result event cannot be published after bounded retries fails visibly.
- One isolated application image may serve both processes. Application artifacts are
  shared through the existing ignored `artifacts/` directory, not durable workflow state.
- Temporal remains the sole durable retry/recovery owner. Consumer retries are limited
  to obtaining durable workflow-start acceptance before acknowledging transport.
- Canonical integration uses uniquely suffixed mutable Nautobot fixtures and reads only
  immutable system metadata or objects created by that test, matching Feature 002 safety.
