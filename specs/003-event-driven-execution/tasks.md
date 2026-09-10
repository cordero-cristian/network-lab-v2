# Tasks: Event-Driven Durable Execution

**Input**: Design documents from `specs/003-event-driven-execution/`

**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`,
`contracts/events.md`, `contracts/execution.md`, `quickstart.md`

**Status**: Implementation approved 2026-09-09.

**Tests**: Required by the specification and constitution. Write each stated test
before its implementation and record the expected failure.

## Phase 1: Setup And Contract Lock

**Purpose**: Add only shared names and entry-point declarations required by this feature.

- [x] T001 Add failing topic/group/task-queue default, override, invalid-name, and duplicate-topic cases to `tests/unit/test_settings.py`, then add the five narrow validated settings to `src/network_automation/settings.py` and `.env.example` without changing existing defaults or secret behavior. Covers FR-006/022/024.
- [x] T002 Add `network-render-request`, `network-worker`, and `network-event-consumer` entry points to `pyproject.toml`; run `uv lock --check` and verify no new Python dependency or second package is introduced. Covers FR-022/023/030.

---

## Phase 2: Foundational Event And Execution Models

**Purpose**: Lock strict typed payloads before any transport or workflow behavior.

- [x] T003 [P] Add failing request/completion/failure/workflow-input/artifact-metadata construction, JSON round-trip, unknown-field, wrong-type/version, malformed UUID, unsafe device, non-UTC timestamp, text-bound, artifact-path mismatch, and allowed-error-category cases to `tests/unit/test_event_models.py`. Covers FR-001-FR-005/011/012/020/025.
- [x] T004 [P] Add contract examples from `contracts/events.md` as exact decode/encode cases in `tests/unit/test_event_models.py`, including stable result payload identity across repeated serialization. Covers FR-001-FR-005/020.
- [x] T005 Implement only frozen Pydantic v2 `RenderRequested`, `RenderCompleted`, `RenderFailed`, `RenderDeviceConfigRequest`, `ArtifactMetadata`, stable error literals, UTC validation, cross-field artifact path, and deterministic `workflow_id_for()` in `src/network_automation/events/models.py` with required exports in `src/network_automation/events/__init__.py`. Make T003-T004 pass. Covers FR-001-FR-005/011/012/016/020.

**Checkpoint**: All external and durable payloads are strict, versioned, safe, and
testable without Kafka or Temporal.

---

## Phase 3: User Story 1 - Render From An External Event (Priority: P1) MVP

**Goal**: A valid request is durably accepted, invokes the existing Feature 002 path,
and publishes one correlated logical completion.

**Independent Test**: Use mocked Kafka/Temporal boundaries plus the supported Temporal
test environment to drive one valid request through consumer start, workflow render,
and completion publication, asserting Feature 002 orchestration is called once.

### Tests For User Story 1

- [x] T006 [P] [US1] Add failing delivery-confirmed request/completion/failure publish, topic selection, event-ID record key, serialization, timeout/error redaction, and stable retry-payload tests using a mocked Confluent producer in `tests/unit/test_event_producer.py`. Covers FR-005/006/015/020/023.
- [x] T007 [P] [US1] Add failing valid-consumer decode/start/input/workflow-ID tests that independently assert `WorkflowIDConflictPolicy.USE_EXISTING` for running executions and `WorkflowIDReusePolicy.REJECT_DUPLICATE` for closed executions, plus the 10-minute execution timeout and synchronous commit, with mocked Confluent consumer and Temporal client in `tests/unit/test_event_consumer.py`; assert zero Nautobot/render/filesystem/result-publication calls. Covers FR-007-FR-009/011/012.
- [x] T008 [P] [US1] Add a supported time-skipping Temporal environment test for success activity order, deterministic completion fields, correlation/path preservation, and workflow result in `tests/unit/test_render_workflow.py`. Covers FR-012-FR-016/025 and SC-001.
- [x] T009 [P] [US1] Add failing render-activity delegation/metadata and publish-activity delivery tests in `tests/unit/test_render_activities.py`, mocking only `render_device()` and the narrow producer. Covers FR-014/015.
- [x] T010 [P] [US1] Add failing request CLI identifier/time/source/output and publication-failure/nonzero/redaction tests in `tests/unit/test_render_request_cli.py`. Covers FR-002/003/005/023.

### Implementation For User Story 1

- [x] T011 [US1] Implement the three-event-only `publish_event()` and `EventPublishError` with broker delivery confirmation in `src/network_automation/events/producer.py`; make T006 pass without a generic bus abstraction. Covers FR-005/006/015/020.
- [x] T012 [US1] Implement `render_device_artifact` by calling existing Feature 002 `network_automation.cli.render.render_device()` and implement `publish_render_result` in `src/network_automation/activities/rendering.py` with exports in `src/network_automation/activities/__init__.py`; return only `ArtifactMetadata`. Make T009 success cases pass. Covers FR-014/015/018.
- [x] T013 [US1] Implement deterministic `RenderDeviceConfigWorkflow` success ordering, Temporal-safe UUID/time, explicit render/publication retry policies, and validated result in `src/network_automation/workflows/render_device.py` with exports in `src/network_automation/workflows/__init__.py`; make T008 success pass. Covers FR-013-FR-018.
- [x] T014 [US1] Implement request validation, Pydantic-converted Temporal start with separate `WorkflowIDConflictPolicy.USE_EXISTING` running-conflict and `WorkflowIDReusePolicy.REJECT_DUPLICATE` closed-reuse arguments, the 10-minute execution timeout, and synchronous post-accept commit in `src/network_automation/events/consumer.py`; make T007 valid path pass. Covers FR-007-FR-012.
- [x] T015 [US1] Implement `network-render-request` orchestration in `src/network_automation/cli/render_request.py` and print event/correlation/workflow IDs only after delivery; make T010 pass. Covers FR-003/005/023.

**Checkpoint**: The core valid path is complete with mocked external boundaries and a
real supported Temporal test server; no Compose or network device is required.

---

## Phase 4: User Story 2 - Survive Duplicate And Transient Delivery (Priority: P1)

**Goal**: Duplicate requests resolve to one workflow, unaccepted offsets cannot be
skipped, and result publication retries without rerendering.

**Independent Test**: Deliver one event twice, fail workflow start once, and fail
completion publication once in deterministic tests; observe one workflow ID, correct
seek/commit order, one render call, and eventual completion.

### Tests For User Story 2

- [x] T016 [P] [US2] Add running/closed duplicate, uncertain-start exact seek, no-later-offset-commit, synchronous commit failure, and safe retry-log tests to `tests/unit/test_event_consumer.py`. Covers FR-008-FR-011/021 and SC-002.
- [x] T017 [P] [US2] Add time-skipping workflow tests for bounded transient render retry, first-attempt completion-publication failure, stable result event ID/payload, exhausted publication workflow failure, and exactly one render invocation during publication retry in `tests/unit/test_render_workflow.py`. Covers FR-015-FR-020/025 and SC-003.
- [x] T018 [P] [US2] Add activity classification cases for timeout/connection/408/429/5xx, filesystem error, broker failure, and uncertain completed write to `tests/unit/test_render_activities.py`. Covers FR-017-FR-019.

### Implementation For User Story 2

- [x] T019 [US2] Complete retention-bounded duplicate attach/already-closed handling and exact offset seek-before-retry behavior after start or commit failure in `src/network_automation/events/consumer.py`; never process/commit beyond an unaccepted partition offset. Make T016 pass. Covers FR-008-FR-011.
- [x] T020 [US2] Add the explicit seven-category activity-local classifier and safe retryable/non-retryable Temporal application errors in `src/network_automation/activities/rendering.py`; complete bounded policies and publication-isolation behavior in `src/network_automation/workflows/render_device.py`. Make T017-T018 pass. Covers FR-015-FR-020.

**Checkpoint**: At-least-once delivery, duplicate identity, and retry barriers are
proved without a fake workflow engine or external infrastructure.

---

## Phase 5: User Story 3 - Report Permanent Failure Safely (Priority: P2)

**Goal**: Accepted permanent failures publish a safe correlated result; malformed
messages are isolated without terminating or poisoning the consumer loop.

**Independent Test**: Feed invalid JSON/type/version followed by a valid request and
run a workflow with invalid intent; assert safe poison commit/continuation and one
logical failure outcome with no secret/raw payload/stack text.

### Tests For User Story 3

- [x] T021 [P] [US3] Add malformed bytes/JSON/object/type/version/extra-field, safe topic/partition/offset/parseable-event-ID/error-category logging without full payloads or secrets, poison synchronous commit, continuation, commit-error, and no-workflow-start cases to `tests/unit/test_event_consumer.py`. Covers FR-005/007/010/021 and SC-005.
- [x] T022 [P] [US3] Add time-skipping workflow cases for all permanent render categories, correlation/workflow identity, Temporal-safe failure ID/time, safe messages, one failure publication, and exhausted failure-publication visibility to `tests/unit/test_render_workflow.py`. Covers FR-004/005/015-FR-021 and SC-004.
- [x] T023 [P] [US3] Add credential/raw-payload/stack redaction and unknown-exception non-retry cases to `tests/unit/test_render_activities.py` and structured-log context/redaction assertions to consumer/worker tests. Covers FR-005/017/019/021.

### Implementation For User Story 3

- [x] T024 [US3] Complete poison-message validation/log/commit/continuation with safe topic/partition/offset/parseable-event-ID/error-category context and no arbitrary raw payload in `src/network_automation/events/consumer.py`; make T021 pass without a dead-letter topic. Covers FR-005/007/010/021.
- [x] T025 [US3] Complete workflow failure-result construction/publication and safe activity messages/categories in `src/network_automation/workflows/render_device.py` and `src/network_automation/activities/rendering.py`; make T022-T023 pass. Covers FR-004/005/015-FR-021.

**Checkpoint**: Every specified invalid input or permanent render condition is safe,
visible, and does not become blind retry or consumer-process failure.

---

## Phase 6: User Story 4 - Run And Verify The Two Processes (Priority: P2)

**Goal**: Run one healthy worker and one healthy consumer reproducibly and prove the
real component and full event-driven path on canonical Ubuntu.

**Independent Test**: Start the `automation` Compose profile, publish a request for a
unique test-owned device, consume its correlated result/artifact, and repeat duplicate,
failure, and stateless worker-restart cases with exact cleanup.

### Tests For User Story 4

- [x] T026 [P] [US4] Add worker registration, Pydantic converter, bounded thread-pool activity executor, task queue, graceful shutdown, readiness/heartbeat, safe startup failure, and structured context tests in `tests/unit/test_worker.py`; add consumer process lifecycle/health cases in `tests/unit/test_event_consumer.py`. Covers FR-021/022/025.
- [x] T027 [P] [US4] Add static Compose/application-image tests for exact two profile services, one shared pinned image, no ports/new infrastructure/consumer artifact mount, internal endpoints, commands, dependencies, health checks, and root artifact bind in `tests/unit/test_automation_compose.py`. Covers FR-024/029/030 and SC-010.
- [x] T028 [P] [US4] Add explicit Kafka request/result round-trip and real Temporal workflow-worker component tests with uniquely named exact-cleaned Kafka topics and retained unique workflow IDs in `tests/integration/test_event_components.py`; missing infrastructure must fail, not skip. Covers FR-006/013/015/026/027.
- [x] T029 [US4] Extract Feature 002's unchanged uniquely owned REST fixture helper to `tests/integration/support/nautobot_fixture.py`, update `tests/integration/test_nautobot_render.py` to import it, and prove its existing integration still passes before adding Feature 003 use. Covers FR-014/027/029.
- [x] T030 [US4] Add full valid, duplicate, permanent-failure, and consumer/worker-required assertions in `tests/integration/test_event_driven_render.py` using unique event/correlation IDs, the shared test-owned Nautobot fixture, correlation-filtered results, deterministic artifact comparison/path, and exact Nautobot/artifact cleanup. Covers FR-001-FR-020/022/026/027 and SC-001/002/004/005/007.
- [x] T031 [US4] Add separate stateless worker stop/request-pending/restart and consumer stop/redelivery/restart acceptance cases to `tests/integration/test_event_driven_render.py`, asserting same-workflow completion within Temporal retention; do not stop Kafka, Temporal, Nautobot, or reset persistent data. Covers FR-008/011/013/017/022 and SC-008.

### Implementation For User Story 4

- [x] T032 [US4] Implement `network-worker` client/Worker registration, Pydantic converter, one bounded thread-pool activity executor, one task queue, signal-safe shutdown, and health files in `src/network_automation/worker.py`; add consumer process entry/main and health files in `src/network_automation/events/consumer.py`. Make T026 pass. Covers FR-021/022.
- [x] T033 [US4] Add pinned minimal `Dockerfile.automation`, `.dockerignore`, and only profile-gated `automation-worker`/`event-consumer` services plus internal settings/artifact mount/health checks to `compose.yaml`; make T027 pass and preserve default Feature 001 startup. Covers FR-024/029/030.
- [x] T034 [US4] Build/start the `automation` profile after existing namespace initialization; run T028-T031 against canonical Ubuntu, verify only three normal Feature 003 topics, retain shared event records, remove exact test-owned Nautobot/artifact/topic resources, and record the no-real-outage limitation in `docs/validation.md`. Covers FR-026-FR-029 and SC-001-SC-008.

**Checkpoint**: The full Kafka-to-Temporal-to-Nautobot-to-artifact-to-Kafka path and
both process models are proven against real infrastructure.

---

## Phase 7: Final Regression, Documentation, And Scope Gate

**Purpose**: Preserve accepted features and reject architecture/scope drift.

- [x] T035 Run Docker-stopped `uv sync --locked`, imports, default/unit/Temporal-environment tests, explicit absent-dependency integrations, build, and Compose validation; record actual platform/results in `docs/validation.md`. Covers FR-025-FR-030 and SC-006/007.
- [x] T036 Run canonical `network-lab-check`, Feature 001 service/lifecycle regressions as practical, every Feature 002 unit/golden/real Nautobot test, Feature 003 component/full integrations, image health/restart checks, and clean-checkout acceptance without volume reset; record exact results/limitations in `docs/validation.md`. Covers FR-028/029 and SC-007/009.
- [x] T037 Document event contracts, at-least-once/poison/duplicate semantics, retry categories, workflow/result ordering, process/profile commands, artifact/event ownership, diagnostics, cleanup, implementation simplicity, and explicit exclusions in `README.md`, `docs/validation.md`, and Feature 003 artifacts without rewriting Feature 001/002 guidance. Covers FR-001-FR-031.
- [x] T038 Recheck `.specify/memory/constitution.md`, dependencies, imports, image/Compose services, source tree, topics, workflow sandbox behavior, and `git diff` for Kafka-only transport, Temporal-only orchestration/retries, exact Feature 002 reuse, one package/worker/consumer/workflow, three explicit event models, two activities, no task-driven helper layers, presentation-only Jinja, and zero device/ZTP/generic/future scope; record final evidence in `specs/003-event-driven-execution/checklists/review.md`. Covers FR-030/031 and SC-010.

## Dependencies And Execution Order

- T001-T002 establish shared settings and entry-point contracts.
- T003-T005 are foundational and block every user story.
- US1 T006-T015 is the MVP and blocks US2/US3 behavior.
- US2 T016-T020 and US3 T021-T025 can proceed in parallel after US1 because their
  primary tests/changes concern duplicate/transient and permanent/poison paths.
- US4 T026-T034 depends on US1-US3 contracts and completed process behavior.
- T029 must preserve and pass Feature 002 integration before T030 uses the helper.
- T034 requires T028-T033 and canonical infrastructure; T035 then proves offline
  independence, T036 proves regressions/acceptance, T037 documents observed behavior,
  and T038 is the final scope gate.

## Parallel Examples

- Foundational: T003 event validation and T004 contract serialization can be authored
  in parallel before T005.
- US1: T006-T010 touch independent producer, consumer, workflow, activity, and CLI tests.
- US2/US3: T016-T018 can run alongside T021-T023 after the successful flow is stable.
- US4: T026 and T027 are independent unit/static tests; T028 component integration can
  be authored while T029 safely extracts the test fixture helper.

## Implementation Strategy

The MVP is setup, foundational models, and US1 through T015: one valid request reaches
one durable workflow and correlated completion with mocked external boundaries plus a
supported Temporal test server. US2 adds duplicate/retry durability; US3 adds safe
failure/poison behavior; US4 adds exactly two reproducible runtime processes and real
integration. Final tasks preserve accepted behavior and enforce the stop before any
device deployment or bootstrap feature.

**Total: 38 proposed tasks. Implementation requires explicit approval after analysis.**
