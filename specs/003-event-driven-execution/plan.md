# Implementation Plan: Event-Driven Durable Execution

**Branch**: `003-event-driven-execution` | **Date**: 2026-09-09 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/003-event-driven-execution/spec.md`

**Status**: Implementation approved 2026-09-09

## Summary

Extend the accepted Python package with three strict version-1 event models, a thin
manual-commit Kafka consumer, one deterministic Temporal workflow, two concrete
activities, one worker process, and one request-publisher command. The render activity
calls Feature 002's existing `render_device()` orchestration unchanged; the workflow
separately publishes completion/failure so publication retries never rerender. Add two
profile-gated Compose services using one application image and no new infrastructure.

## Technical Context

**Language/Version**: CPython 3.12.13, as already locked

**Primary Dependencies**: Existing `confluent-kafka`, `temporalio`, Pydantic v2,
httpx, pydantic-settings, and Jinja2. Use Temporal's shipped Pydantic data converter
and supported test environment. No new Python runtime dependency is planned.

**Storage**: Existing Kafka log, Temporal PostgreSQL persistence, Nautobot-owned
intent, and Feature 002 ignored files under `artifacts/configs/`. No new database,
schema, Redis state, or durable state owned by the application processes.

**Testing**: pytest, mocked Kafka/Temporal clients at process boundaries, Temporal
`WorkflowEnvironment.start_time_skipping()` for workflow semantics/retries, existing
Feature 002 unit/integration coverage, and explicit canonical component/full-path tests.

**Target Platform**: Existing macOS ARM64 development environment and canonical
Ubuntu 24.04.4 x86-64 Docker Compose lab with Kafka 4.1.2, Temporal 1.31.0, Temporal
Python SDK 1.32.0, and Nautobot 2.4.41.

**Project Type**: One typed Python package, two long-running CLI processes, and one
finite request-publisher CLI; no API service.

**Performance Goals**: One low-volume lab request at a time per consumed partition;
no throughput target. Healthy end-to-end acceptance is bounded by explicit workflow,
activity, publication, and test timeouts rather than an unsupported latency claim.

**Constraints**: At-least-once Kafka transport; deterministic workflow code; manual
offset commits; one permanently reserved workflow ID per request event; bounded
retries; atomic Feature 002 artifacts; safe events/logs; no device access, Kafka
choreography, ZTP, generic framework, or extra infrastructure.

**Scale/Scope**: Three event types and topics, one consumer group, one workflow, two
activities, one task queue, one worker process, and one consumer process. Sequential
message handling is sufficient for the canonical lab.

## Constitution Check

*GATE: Passed before research and rechecked after design.*

| Principle | Pre-Design Gate | Post-Design Evidence |
|---|---|---|
| Explicit Architectural Ownership | PASS: Kafka carries request/result facts; Temporal alone chooses work, retries, recovery, and durable ordering; Nautobot and Feature 002 retain intent/render ownership. | Consumer starts/attaches only. Workflow coordinates two activities. Render activity calls the accepted Feature 002 orchestration; result activity alone performs Kafka publication. |
| Small, Explicit Implementation | PASS: one package, one workflow, one worker, one consumer, no framework. | Three concrete event models, two activity functions, direct producer/consumer functions, and three CLIs are sufficient; no registry/factory/plugin/service API. |
| Reproducible Local Infrastructure | PASS: reuse Kafka, Temporal, PostgreSQL, Nautobot, and ignored artifacts. | One pinned application image serves two `automation` profile services; no new database, volume, broker, proxy, or UI. Existing default startup remains unchanged. |
| Evidence Over Process Status | PASS: isolated and real component/full-path tests are required. | Supported Temporal test server proves workflow ordering/retries; real Kafka, Temporal, Nautobot, processes, artifact, and result event prove acceptance. |
| Spec-Driven, Bounded Delivery | PASS: Feature 003 has separate artifacts and an approval stop. | Spec, research, model, contracts, quickstart, tasks, and consistency review precede all implementation. Out-of-scope deployment/bootstrap remains absent. |

No constitution violation requires complexity justification.

## Design Decisions

### Event Contract And Transport

`RenderRequested`, `RenderCompleted`, and `RenderFailed` are frozen Pydantic v2
models with `extra="forbid"`, literal type/version values, UUID fields, reused Feature
002 safe device-name constraints, and UTC-aware timestamps. JSON uses UTF-8 and UTC
`Z` timestamps. A narrow `publish_event()` maps only these three model types to the
three configured topics, uses event ID as the Kafka record key, waits for broker
delivery, and raises a safe typed error.

Kafka delivery remains at least once. Producer delivery uncertainty can duplicate a
physical result record; Temporal constructs one stable result `event_id`, so every
retry publishes the same logical event and consumers can deduplicate by ID. Feature
003 explicitly does not claim Kafka exactly-once semantics.

The consumer uses group `network-automation-render-consumer`, `enable.auto.commit=false`,
and synchronous message commits. It validates only request events. Invalid messages
are logged with safe topic, partition, offset, parseable event ID, and validation/error
category context, without arbitrary full payloads or secrets, then committed as poison
records without a result event. A Temporal start transport failure causes the exact
topic/partition/offset to be sought again; no later offset from that partition may be
committed first. Any synchronous commit failure, including poison-message commit failure,
also seeks and retries the same offset before later records from that partition.

### Workflow Identity And Duplicate Delivery

Workflow ID is exactly `render-device-config:<request-event-id>`. The installed pinned
`temporalio==1.32.0` API exposes the two controls independently. Start uses
`WorkflowIDConflictPolicy.USE_EXISTING` so a duplicate delivered while the ID is running
returns its existing execution. Separately, start uses
`WorkflowIDReusePolicy.REJECT_DUPLICATE` so a duplicate delivered after closure cannot
create a replacement and receives `WorkflowAlreadyStartedError`. Both outcomes permit
offset commit while workflow history remains inside the existing 3-day namespace
retention. After retention expiry, Temporal no longer guarantees ID memory; broad replay
is out of scope. Retrying logical work requires a new request event ID and no custom
deduplication storage is added.

The workflow input is `RenderDeviceConfigRequest(event_id, correlation_id,
device_name)`. Temporal client, worker, and test environment use
`pydantic_data_converter`; no Nautobot mapping or configuration text enters workflow
input/history.

### Workflow And Activity Ordering

`RenderDeviceConfigWorkflow` performs only deterministic coordination:

1. Execute `render_device_artifact` with the small request.
2. On success, construct one `RenderCompleted` using `workflow.uuid4()`,
   `workflow.now()`, workflow ID, and returned artifact metadata.
3. Execute `publish_render_result` with the completion and return it.
4. On classified render activity failure, construct one `RenderFailed` with the same
   deterministic facilities and stable safe category/message.
5. Execute `publish_render_result` with the failure and return it as the handled outcome.

The render exception handler surrounds only step 1. Exhausted result publication is
not mistaken for render failure; it fails the workflow visibly. A known permanent
render failure therefore completes after publishing its failure outcome, while an
unpublishable outcome leaves the workflow failed in Temporal.

`render_device_artifact` is one activity rather than three because splitting retrieval,
rendered text, and writes would place validated intent/configuration payloads in
workflow history and duplicate Feature 002 orchestration. It directly calls existing
`network_automation.cli.render.render_device(device_name, Path("artifacts/configs"))`
and returns only device/path metadata. This deliberately reuses the accepted path
without moving Feature 002 code for directory aesthetics.

`publish_render_result` accepts only a validated completion/failure model and calls
the narrow producer. Keeping it separate means a broker retry cannot invoke rendering.

### Error Categories And Retry Policies

The render activity has one explicit classifier local to the activity module, not a
generic exception framework. It emits safe Temporal application errors:

| Stable `error_type` | Examples | Retryable |
|---|---|---|
| `nautobot_unavailable` | timeout, connection error, HTTP 408/429/5xx | Yes |
| `artifact_unavailable` | transient directory/write/replace `OSError` | Yes |
| `intent_invalid` | missing/malformed Nautobot state, Pydantic validation | No |
| `nautobot_rejected` | HTTP authentication/authorization/other 4xx | No |
| `unsupported_platform` | non-`nokia_srl` intent | No |
| `render_invalid` | deterministic template/render validation failure | No |
| `internal_error` | unclassified programming failure | No |

Messages are static safe summaries plus field/invariant context already sanitized by
Feature 002; raw exception text is never copied blindly to events.

- Render activity: `start_to_close=60s`, initial interval 1s, coefficient 2,
  maximum interval 10s, maximum 3 attempts; permanent application errors are marked
  non-retryable.
- Result publication: `start_to_close=30s`, initial interval 1s, coefficient 2,
  maximum interval 10s, maximum 5 attempts.
- Workflow execution: 10-minute bound; consumer start RPC uses the existing 10-second
  maximum boundary timeout.

If a render activity wrote the artifact but its completion was not recorded, retry may
rerun the complete Feature 002 path. Deterministic bytes and atomic replacement make
that side effect safe. Once the workflow records artifact metadata, only result
publication retries.

### Processes, Settings, And Compose

Add settings defaults for three topics, consumer group, and task queue to the existing
`LabSettings`; validate each as a non-empty Kafka/task-queue-safe name and require the
three topic names to remain distinct. Existing
Nautobot, Kafka, Temporal, timeout, and local credentials remain the connection source.

`network-worker` connects with the Pydantic converter and registers the workflow plus
two synchronous activities on `network-automation`, using one bounded thread-pool
activity executor so Feature 002 HTTP/filesystem and Kafka publication never block the
workflow event loop. `network-event-consumer` connects to Kafka and
Temporal and runs the thin manual-commit loop. `network-render-request DEVICE`
generates request/correlation UUIDs and UTC time outside workflow code, publishes one
request, and prints event, correlation, and deterministic workflow IDs.

One `Dockerfile.automation` builds the existing package on pinned Python 3.12.13 and
uv 0.11.28 images. Compose reuses that image for `automation-worker` and
`event-consumer`, both behind profile `automation`. This preserves Feature 001's
default `up --wait` followed by explicit Temporal namespace initialization; developers
then run `docker compose --profile automation up -d --wait automation-worker
event-consumer`.

Worker receives Nautobot, Kafka, Temporal, and artifact settings. Consumer receives
Kafka/Temporal plus currently required local `LabSettings` values but its code has no
Nautobot/render/filesystem imports. Both expose no ports. Worker bind-mounts
`./artifacts:/app/artifacts`; consumer has no artifact mount. Readiness/heartbeat files
updated by each process support bounded freshness health checks without adding HTTP.

Kafka topics are created by first publication under the lab broker's existing
auto-create behavior; no initializer/service is added. Canonical acceptance verifies
that only the three configured Feature 003 topics exist for this feature.

### Testing And Fixture Safety

Unit tests mock Kafka/Temporal clients only at external boundaries. Workflow tests use
the supported time-skipping Temporal environment and real SDK Worker with fake concrete
activities; they prove order, duplicate IDs, permanent failure, retries, stable result
identity, and no rerender during publication retry.

Component integrations prove Kafka request round-trip, real Temporal worker execution,
existing Feature 002 real Nautobot rendering, and result round-trip independently.
Full integration requires healthy Compose profile services, extracts Feature 002's
REST fixture helper into shared integration-test support without changing fixture
behavior, creates only uniquely suffixed Nautobot objects/device/artifact, publishes
unique request/correlation IDs, and filters results by correlation ID.

Normal shared-topic records are durable Kafka evidence and cannot be individually
deleted safely; tests never delete shared topics or unrelated records. All mutable
Nautobot objects and generated artifacts are exact test-owned resources and are
removed. Isolated transport tests may create and delete only uniquely named topics.

Worker and consumer restart acceptance uses only the stateless profile containers.
Unique workflow IDs/history remain as durable Temporal evidence; tests do not delete
the namespace or workflow history. Stopping canonical Nautobot or Kafka would risk unrelated lab use, so no real transient
outage is planned. Time-skipping Temporal tests prove retry behavior, including a
first-attempt publication failure with exactly one render invocation. Acceptance
documents this allowed limitation.

## Project Structure

### Documentation (this feature)

```text
specs/003-event-driven-execution/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── events.md
│   └── execution.md
├── checklists/
│   ├── requirements.md
│   └── review.md
└── tasks.md
```

### Source Code (repository root)

The 38 task checkpoints are verification granularity, not code architecture. They MUST
NOT cause helper frameworks or additional processes; implementation remains approximately
three event models, one consumer, one workflow, two activities, one worker, one request
CLI, minimal shared settings, and two profile-gated runtime services.

```text
Dockerfile.automation
compose.yaml                         # two profile-gated application services only
.env.example                         # topic/group/task-queue settings
src/network_automation/
├── settings.py                      # narrow shared configuration additions
├── events/
│   ├── __init__.py
│   ├── models.py                    # three event models + workflow request
│   ├── producer.py                  # narrow three-event publisher
│   └── consumer.py                  # request-only manual-commit bridge
├── workflows/
│   ├── __init__.py
│   └── render_device.py             # sole deterministic workflow
├── activities/
│   ├── __init__.py
│   └── rendering.py                 # render + publish activities/classification
├── worker.py
└── cli/
    └── render_request.py
tests/
├── unit/
│   ├── test_event_models.py
│   ├── test_event_producer.py
│   ├── test_event_consumer.py
│   ├── test_render_workflow.py
│   ├── test_render_activities.py
│   └── test_render_request_cli.py
├── integration/
│   ├── support/nautobot_fixture.py
│   ├── test_event_components.py
│   └── test_event_driven_render.py
└── existing Feature 001/002 tests unchanged except fixture-helper import
```

**Structure Decision**: Extend the one package with three concrete responsibility
folders matching actual boundaries. There is no generic event base class, workflow
registry, activity factory, service layer, API, or second package. Existing Feature
002 code stays in place and is called by the render activity.

## Implementation Sequence

1. Lock event/execution contracts and settings without changing Feature 001/002 behavior.
2. Implement/test strict event models and the narrow producer/request CLI.
3. Implement/test the deterministic workflow with supported Temporal test environment.
4. Implement/test two activities reusing Feature 002 and explicit retry classification.
5. Implement/test the thin manual-commit consumer and duplicate start semantics.
6. Add one application image and two `automation` profile services with health checks.
7. Extract only the shared test-owned Nautobot fixture helper and add component/full
   integration tests.
8. Validate Docker-stopped tests, canonical components, duplicate/restart/failure
   behavior, complete real path, retained Feature 001/002 health, and forbidden scope.
9. Update documentation/evidence and stop; do not add device deployment or Feature 004.

## Complexity Tracking

No constitution violation is proposed. Two process entry points are required because
Kafka offset ownership and Temporal task execution have distinct runtime lifecycles;
they share one package and image.
