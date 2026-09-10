# Research: Event-Driven Durable Execution

## Deterministic Workflow Identity

**Decision**: With pinned `temporalio==1.32.0`, use
`WorkflowIDConflictPolicy.USE_EXISTING` for an already-running
`render-device-config:<event_id>` execution. Separately use
`WorkflowIDReusePolicy.REJECT_DUPLICATE` for a closed execution and treat its
`WorkflowAlreadyStartedError` as prior durable acceptance, not permission to replace it.

**Rationale**: The installed SDK exposes both independent keyword arguments and enum
members on `Client.start_workflow`. Running duplicates attach;
closed duplicates cannot create a second logical execution while history remains within
the existing 3-day namespace retention. A new event ID is the explicit operator action
for new work; replay after retention is deliberately outside this feature.

**Alternatives considered**: `ALLOW_DUPLICATE_FAILED_ONLY` would let one request event
create a second execution after failure. Device-name IDs would incorrectly merge
separate requests and block later legitimate renders. An indefinite deduplication store
would add persistence and broad replay behavior outside scope.

## Pydantic Temporal Payloads

**Decision**: Use the SDK's `temporalio.contrib.pydantic.pydantic_data_converter` for
client, worker, and test environment. Workflow input and results are explicit frozen
Pydantic models.

**Rationale**: This preserves the constitutional typed boundary and avoids ad hoc
dictionaries. The installed SDK supports the converter and the time-skipping test
environment accepts a data converter.

**Alternatives considered**: Plain dictionaries defer errors. A custom converter is
unnecessary. Passing raw Nautobot data or rendered text expands history and scope.

## Workflow-Safe Result Identity And Time

**Decision**: Build result IDs and timestamps with `workflow.uuid4()` and
`workflow.now()` exactly once before the publication activity.

**Rationale**: Both APIs are available and deterministic under replay. The validated
event remains stable across publication retries.

**Alternatives considered**: Normal `uuid4()`/wall-clock reads violate replay
determinism. Generating values in each publication attempt changes logical identity.

## Activity Granularity

**Decision**: Use `render_device_artifact` and `publish_render_result`. The first calls
Feature 002's existing `render_device()` and returns only artifact metadata.

**Rationale**: This reuses the accepted complete behavior and keeps intent/rendered
text out of workflow history. Separate publication provides the required retry barrier.

**Alternatives considered**: Separate get/render/write activities expose larger
payloads in history and recreate orchestration already owned by Feature 002. One
all-in-one activity would rerender whenever result publication retries.

## Retry Classification

**Decision**: Keep one explicit activity-local mapping for seven stable categories.
Retry only transport timeout/connection/408/429/5xx, filesystem errors, and Kafka
delivery failures. Mark validation, 4xx rejection, unsupported platform, deterministic
render errors, and unknown programming errors non-retryable.

**Rationale**: Temporal owns retries while predictable bad intent fails quickly.
Feature 002 preserves underlying HTTP causes, allowing narrow status classification
without changing its external behavior.

**Alternatives considered**: Retrying every exception wastes attempts and obscures
bad intent. A generic classifier/plugin system is forbidden. No retry would fail the
durability objective.

## Kafka Offset And Duplicate Semantics

**Decision**: Disable auto commit. Commit synchronously only after workflow start,
attachment, or known prior closure. Seek the exact offset after a Temporal start or
synchronous commit failure. Commit invalid poison messages after safe logging, and
seek/retry them if that commit itself fails.

**Rationale**: This prevents acknowledged loss and prevents later commits from
skipping an earlier unaccepted message. Invalid messages cannot be made valid by
retry and must not block a partition forever.

**Alternatives considered**: Auto commit can lose requests. Continuing after a failed
start can advance and later commit beyond it. A dead-letter topic would add a fourth
topic and unsupported contract.

## Result Delivery Semantics

**Decision**: Wait for broker delivery and retry in Temporal. Reuse one result event
ID across attempts; permit duplicate physical records under an uncertain broker
acknowledgement.

**Rationale**: This is honest at-least-once behavior and supports deduplication without
the explicitly excluded exactly-once architecture work.

**Alternatives considered**: Claiming exactly once is unsupported. Persisting an
outbox adds a database/schema and a second durable owner.

## Compose Runtime

**Decision**: Build one pinned application image and add only `automation-worker` and
`event-consumer`, both under profile `automation`, with no ports and file freshness
health checks.

**Rationale**: Feature 001 initializes the Temporal namespace after default
`up --wait`; profile gating avoids a startup dependency cycle and preserves accepted
default/lifecycle behavior. One image serves both process commands.

**Alternatives considered**: Default-enabled services would wait on a namespace not
yet initialized. Bind-mounted `uv run` mutates the checkout and downloads at startup.
An API/supervisor or separate images add unjustified components.

## Topic Creation And Test Records

**Decision**: Rely on existing lab auto-creation at first publish for the three normal
topics. Delete only uniquely named topics created by isolated transport tests; retain
normal-topic integration records until Kafka retention removes them.

**Rationale**: Kafka records cannot be individually deleted safely. A topic initializer
would be a third application service/process and broad shared-topic deletion could
destroy unrelated evidence.

**Alternatives considered**: A schema registry/topic manager is out of scope. Creating
per-run full-path topics would not prove the configured canonical process path.

## Real Transient Acceptance

**Decision**: Do not stop shared canonical Nautobot or Kafka. Prove retries with the
supported time-skipping Temporal environment and document the absence of a safe real
outage test.

**Rationale**: The specification permits this when an isolated transient is
impractical. Intentionally disrupting shared persistent lab services risks unrelated
work and violates the non-destructive constraint.

**Alternatives considered**: Adding a fault proxy is forbidden extra infrastructure.
Stopping normal services is operationally unsafe.
