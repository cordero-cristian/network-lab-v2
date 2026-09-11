# Tasks: SR Linux Deployment And Operational Validation

**Input**: Design documents from `specs/004-srlinux-deployment-validation/`

**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`,
`contracts/events.md`, `contracts/execution.md`, `contracts/device-state.md`, `quickstart.md`

**Status**: Implementation and canonical acceptance complete 2026-09-11.

**Tests**: Required by the specification and constitution. Write each stated test before
its implementation and record the expected failure.

## Phase 1: Pinned Behavior And Shared Setup

**Purpose**: Resolve the canonical runtime gate and add only approved dependency/settings
surface before deployment behavior.

- [x] T001 On canonical Ubuntu x86-64, run a disposable two-node `ghcr.io/nokia/srlinux:26.7.2-519` probe with pyGNMI 0.8.15; verify/capture hostname, interface/subinterface, IPv4 prefix/status, ASN/peer-AS/session response paths and native types, valid absence, atomic rejection, same-payload retry, image digest, and exact cleanup in `specs/004-srlinux-deployment-validation/research.md` and `contracts/device-state.md`; stop for approval if behavior materially differs. Covers FR-013/014/016-FR-020/038 and SC-002/004/009.
- [x] T002 Add failing exact pyGNMI pin/import and device topic/credential/port/timeout/TLS setting tests to `tests/unit/test_settings.py`, then pin `pygnmi==0.8.15` in `pyproject.toml`/`uv.lock` and add validated optional settings to `src/network_automation/settings.py` and `.env.example`; preserve render-only startup without credentials and require all six topics distinct. Covers FR-012/024/030/041.
- [x] T003 [P] Add failing static topology and runtime-override cases to `tests/unit/test_device_topology.py` for two pinned nodes, one link, fixed management network/addresses, hostname-only identity bootstrap, no intended-state preload, no new service/volume/port, worker-only external network attachment, and base Compose independence. Covers FR-033/035/036/042 and SC-009/011.
- [x] T004 [P] Add failing exact contract construction/serialization/unknown-field/version/UUID/time/device/path/digest/size/status/category/stage-dependent failure metadata/redaction cases from `contracts/events.md` and `data-model.md` to `tests/unit/test_deployment_models.py` and `tests/unit/test_deployment_events.py`. Covers FR-001/004/005/021/028-FR-030/032.

---

## Phase 2: Foundational Models, Rendering, And Boundaries

**Purpose**: Lock deterministic render output and all typed boundaries before workflow use.

- [x] T005 [P] Add failing SR Linux golden/unit cases for deterministic remote-AS peer groups, global BGP IPv4-unicast enablement, neighbor attachment, mixed/shared ASNs, and an internal write result that hashes the exact rendered bytes before atomic replacement while the accepted public path return remains unchanged in `tests/unit/test_srlinux_render.py`; update `src/network_automation/rendering/srlinux.py`, `src/network_automation/templates/srlinux/config.j2`, and expected artifacts only enough to satisfy pinned BGP and identity requirements. Covers FR-002/003/005/013/020/041 and SC-002/010.
- [x] T006 [P] Add failing Nautobot `primary_ip4` relation tests for exact host extraction, null/malformed/non-IPv4/cross-origin/inconsistent relationships, and unchanged render intent in `tests/unit/test_nautobot_intent.py`; implement the narrow deployment read in `src/network_automation/intent/nautobot.py`. Covers FR-002/009/010/037.
- [x] T007 [P] Add failing native JSON-IETF response normalization tests for module-qualified paths, all notifications, omitted `update`, invalid schema, preserved string/integer values, and duplicate/conflicting updates in `tests/unit/test_srlinux_device.py`. Covers FR-016-FR-021/024/025.
- [x] T008 Implement only the frozen deployment event/activity models, cross-field validation, failure literals, and deployment workflow ID helper in `src/network_automation/events/models.py` with narrow exports in `src/network_automation/events/__init__.py`; make T004 pass without changing existing render model serialization. Covers FR-001/004/005/021/028-FR-030.
- [x] T009 Implement response normalization, explicit native leaf paths, pyGNMI logger disabling, and safe concrete exception types in new `src/network_automation/devices/srlinux.py` and `devices/__init__.py`; make T007 pass without a generic driver/interface hierarchy. Covers FR-006-FR-008/016-FR-021/024/025/032.

**Checkpoint**: Pinned renderer output and strict external/durable boundaries are testable
without Kafka, Temporal, Nautobot, or a network device.

---

## Phase 3: User Story 1 - Deploy And Validate Intended State (Priority: P1) MVP

**Goal**: One deployment request renders, digest-binds, applies, validates, and publishes
success only after every intended invariant passes.

**Independent Test**: Drive one typed deployment request through a supported Temporal test
worker with fake concrete activities, then through mocked gNMI boundaries; prove exact
ordering, Set bytes, independent checks, and one correlated completion.

### Tests For User Story 1

- [x] T010 [P] [US1] Add failing preparation cases to `tests/unit/test_deployment_activities.py` for one Nautobot snapshot, sole-renderer atomic write/identity reuse, exact path, one matching hostname, ASCII/size/complete-line shape, digest/byte count bound before replacement, authoritative target, expected oper applicability/checks, and no raw artifact/credential in returned payload. Covers FR-002-FR-005/009-FR-012/016/019.
- [x] T011 [P] [US1] Add failing device Set/Get tests to `tests/unit/test_srlinux_device.py` for identity/platform precheck, digest reread, exact `set(update=[("/cli://", artifact)], encoding="ascii")`, no replace/delete/fallback/internal retry, deployment metadata, exact address-key/status normalization without `/ip-prefix` leaf reads, and every required native state read. Covers FR-003/006-FR-008/011/013-FR-020.
- [x] T012 [US1] Add failing validation aggregation cases to `tests/unit/test_deployment_activities.py` after T010 for hostname, loopback, physical/subinterface admin/oper, exact prefix/status, local ASN, peer ASN/session, unique bounded checks, and overall status. Covers FR-015-FR-021.
- [x] T013 [P] [US1] Add supported Temporal time-skipping success tests to `tests/unit/test_deployment_workflow.py` for prepare/deploy/validate/publish-deployment order, no render event from deployment input, exact retry policies/timeouts, deterministic result identity/time, artifact metadata, and no external calls in workflow code; separately assert the old render input sequence is unchanged. Covers FR-001-FR-003/008/015/022/023/028-FR-031.
- [x] T014 [P] [US1] Add failing additive producer, exact topic-to-request-model consumer, `--deploy` CLI, broadened `publish_render_result` activity serialization, and worker-registration tests in `tests/unit/test_deployment_events.py`, `tests/unit/test_event_consumer.py`, `tests/unit/test_render_activities.py`, `tests/unit/test_render_request_cli.py`, and `tests/unit/test_worker.py`; assert cross-topic payloads are poison and omitted flag/existing render contracts remain unchanged. Covers FR-001/026/028-FR-034/041.
- [x] T015 [P] [US1] Add representative accepted Feature 003 success/failure workflow histories and Temporal `Replayer` tests to `tests/unit/test_render_workflow_replay.py`, proving the deployment input discriminator and branch addition replay without changing old commands, payloads, or results. Covers FR-026/030/041 and SC-010.

### Implementation For User Story 1

- [x] T016 [US1] Implement `prepare_device_deployment`, `deploy_device_artifact`, and `validate_device_state` in new `src/network_automation/activities/deployment.py`; preparation uses one Nautobot snapshot and Feature 002's atomic render/write identity, while later activities use the concrete SR Linux boundary with safe structured logs. Make T010/T012 pass. Covers FR-002-FR-012/015-FR-021/032.
- [x] T017 [US1] Complete concrete gNMI Capabilities/Get/Set behavior in `src/network_automation/devices/srlinux.py`, including logger containment before every RPC, native model/hostname precheck, exact digest reread, and one-transaction CLI-origin update; make T011 pass. Covers FR-003-FR-008/011-FR-020/032.
- [x] T018 [US1] Extend the existing `RenderDeviceConfigWorkflow` in `src/network_automation/workflows/render_device.py` with discriminator-based deployment preparation/deploy/validate/outcome branch and separate activity exception scopes; preserve the render-only branch exactly and make T013/T015 pass. Covers FR-001-FR-003/015/022/023/026/028-FR-031.
- [x] T019 [US1] Extend only explicit model-topic mappings in `src/network_automation/events/producer.py`, topic-bound two-request decode/start logic in `src/network_automation/events/consumer.py`, deployment result union in `src/network_automation/activities/rendering.py`, `--deploy` selection in `src/network_automation/cli/render_request.py`, and activity registration in `src/network_automation/worker.py`; make T014 pass without a new consumer/workflow/worker/CLI. Covers FR-001/026/028-FR-034.
- [x] T020 [US1] Add the planned two-node `lab/topology.yml`, hostname-only identity bootstrap, optional `compose.device-access.yaml`, and additive worker/topic/device environment in `compose.yaml`; make T003 pass and prove both base and override Compose configuration. Covers FR-011/012/033/035/036/042.
- [x] T021 [US1] Extend `tests/integration/support/nautobot_fixture.py` with exact test-owned two-device management/interface/primary-IP/BGP fixtures and add the healthy real path plus independent native reads to `tests/integration/test_srlinux_deployment.py`, with exact Nautobot/artifact cleanup. Covers FR-009/017-FR-020/028/035-FR-038 and SC-001/002.

**Checkpoint**: The core real request succeeds only after independent operational validation
on the two-node canonical topology.

---

## Phase 4: User Story 2 - Recover Without Duplicate Deployment (Priority: P2)

**Goal**: Duplicate delivery and uncertain Set response converge to one logical execution,
while each retry barrier repeats only its own activity.

**Independent Test**: Duplicate one request, simulate a lost successful Set response and
temporary state non-convergence, and count render/prepare/Set/Get/publication calls.

- [x] T022 [P] [US2] Add time-skipping workflow cases in `tests/unit/test_deployment_workflow.py` for transient deploy retry without rerender/prepare, validation retry without redeploy, publication retry without prior activities, stable outcome ID/payload, and bounded exhaustion. Covers FR-014/022-FR-024/027/028 and SC-004/005.
- [x] T023 [P] [US2] Add consumer tests in `tests/unit/test_event_consumer.py` for deployment running duplicate attach, retained closed rejection, exact `deploy-device-config:<event_id>`, unchanged separate conflict/reuse policies, synchronous commit, and seek on uncertain start/commit. Covers FR-001/026 and SC-003.
- [x] T024 [P] [US2] Add same-artifact repeated Set and changed-digest-before-retry tests to `tests/unit/test_srlinux_device.py` and `tests/unit/test_deployment_activities.py`, proving repeated keyed operations and zero second mutation on replacement. Covers FR-003-FR-005/014/027 and SC-004/007.
- [x] T025 [US2] Complete workflow retry isolation and deployment duplicate semantics in `src/network_automation/workflows/render_device.py` and `src/network_automation/events/consumer.py`; make T022-T023 pass without custom deduplication state or serialization. Covers FR-022/023/026/027/031.
- [x] T026 [US2] Add real duplicate request, retained workflow identity, safely injected lost-response idempotency, and convergence-without-redeploy acceptance to `tests/integration/test_srlinux_deployment.py`; retain Kafka/Temporal evidence and clean only exact mutable fixtures. Covers FR-014/022/023/026/027/038 and SC-003-SC-005.

---

## Phase 5: User Story 3 - Receive Safe Actionable Failure Outcomes (Priority: P3)

**Goal**: Preparation, deployment, and final validation failures are safely categorized,
correctly retried, and never expose credentials, artifact text, or raw device responses.

**Independent Test**: Exercise each classifier with mocked boundaries and isolated real
unreachable/authentication/rejection/mismatch cases; inspect events and normal logs.

- [x] T027 [P] [US3] Add preparation failure/classification tests to `tests/unit/test_deployment_activities.py` for malformed/oversize/non-ASCII/target-mismatched artifact, bad primary IP, unsupported platform, missing settings, transient Nautobot/I/O, and zero mutation. Covers FR-004/006/009/010/012/024/025/029 and SC-006/007.
- [x] T028 [P] [US3] Add gRPC classification/redaction tests to `tests/unit/test_srlinux_device.py` for unavailable/deadline/refusal, authentication/permission, identity/platform mismatch, permanent `ABORTED`/`INVALID_ARGUMENT`/`FAILED_PRECONDITION` and unknown Set errors, malformed response, pre-RPC pyGNMI logger suppression, and raw artifact/credential exclusion. Covers FR-011-FR-014/024/025/032 and SC-006/008.
- [x] T029 [P] [US3] Add time-skipping workflow failure tests to `tests/unit/test_deployment_workflow.py` for every stable stage/category, stage-dependent artifact/deployment metadata, permanent versus bounded retry, final mismatch, one failure publication, stable safe result, and publication exhaustion visibility. Covers FR-024/025/029-FR-032.
- [x] T030 [US3] Complete activity-local safe classification and Temporal application errors in `src/network_automation/activities/deployment.py` and `src/network_automation/devices/srlinux.py`; complete stage-specific failure outcomes in `src/network_automation/workflows/render_device.py`. Make T027-T029 pass. Covers FR-004/010-FR-014/024/025/029/032.
- [x] T031 [US3] Add isolated real unreachable target, bad credential, atomic rejected configuration, and deterministic validation mismatch cases to `tests/integration/test_srlinux_deployment.py`; assert retry counts, one safe failure event, no leaked marker/config/secret, and restoration/cleanup of test-owned state. Covers FR-024/025/029/032/039 and SC-006-SC-008.
- [x] T032 [US3] Audit normal worker/consumer/device logs and all six event payloads in unit and integration assertions for safe event/correlation/workflow/device/activity/target/check/category context with no credential, raw configuration, raw response, or stack content. Covers FR-028/029/032 and SC-006.

---

## Phase 6: User Story 4 - Operate A Minimal Real Device Lab (Priority: P4)

**Goal**: Developers can independently start, inspect, use, and remove only the two-node
test topology without coupling or resetting supporting infrastructure.

**Independent Test**: Follow the quickstart on canonical Ubuntu from no topology through
device connectivity, full acceptance, teardown, and supporting-service recheck.

- [x] T033 [P] [US4] Add static/documented command assertions in `tests/unit/test_device_topology.py` for pinned image, netlab 26.8.0/containerlab 0.79.0, exact two nodes/link/network/addressing, explicit `--no-config`, topology-before-override startup, worker removal before netlab cleanup, and no destructive shared-data command. Covers FR-035/036/042 and SC-009.
- [x] T034 [P] [US4] Add explicit real preflight helpers/tests to `tests/integration/test_srlinux_deployment.py` that fail on wrong tool versions, absent/wrong nodes, addresses, image, capabilities, gNMI port, identity, or worker network and independently confirm both targets before mutation. Covers FR-006/011/035/038.
- [x] T035 [US4] Run documented clean topology startup, status/connectivity, worker override startup, full deployment acceptance, worker endpoint removal, `netlab down --cleanup`, and base worker restoration on canonical Ubuntu; record exact resources/results in `docs/validation.md`. Covers FR-035-FR-039 and SC-001/002/009.
- [x] T036 [US4] Verify cleanup removed only exact test-owned Nautobot records, artifacts, two device containers, link, and `network-lab-devices-mgmt`, while Compose services/volumes, Kafka evidence, Temporal history, and unrelated labs remain intact; record evidence in `docs/validation.md`. Covers FR-036/037/039 and SC-009.

---

## Phase 7: Regression, Documentation, And Scope Gate

- [x] T037 Run Docker-stopped `uv sync --locked`, imports, default/unit/time-skipping/replay tests, explicit absent-integration failures, build, base/override Compose validation, and dependency audit; record actual platform/results in `docs/validation.md`. Covers FR-040-FR-042 and SC-010/011.
- [x] T038 Run canonical `network-lab-check`, Feature 001 service checks, all Feature 002 golden/real Nautobot tests, all Feature 003 unit/component/full-path/replay tests, and Feature 004 real acceptance without persistent reset; record exact results and limitations in `docs/validation.md`. Covers FR-002/026/030/041 and SC-010.
- [x] T039 Document additive contracts, gNMI CLI-origin tradeoff/idempotency limits, target authority, checks, retries, topology/override lifecycle, credentials/TLS, diagnostics, cleanup, evidence, and exclusions in `README.md`, `.env.example`, `docs/validation.md`, and Feature 004 artifacts without rewriting accepted Feature 001-003 semantics. Covers FR-001-FR-042.
- [x] T040 Recheck constitution, dependency/import/source/service/workflow/topic topology, replay safety, logs/events/artifacts, and `git diff` for exact ownership, one package/worker/consumer/workflow/SR Linux boundary, Feature 002 sole renderer, no raw secrets/config, and zero excluded framework/service/bootstrap scope; record final evidence in `specs/004-srlinux-deployment-validation/checklists/review.md`. Covers FR-007/008/030-FR-036/040-FR-042 and SC-011.

## Dependencies And Execution Order

- T001 is a hard canonical behavior gate. A material contract difference requires plan
  update and user approval before source implementation.
- T002-T004 establish settings/runtime/model contracts. T005-T009 are foundational and
  block every user-story implementation.
- US1 T010-T021 is the MVP. Model/boundary/replay tests T010-T015 can proceed in parallel;
  T016-T020 follow their matching tests; T021 requires the complete path and real topology.
- US2 T022-T026 and US3 T027-T032 follow US1. Their unit tests can proceed in parallel, but
  real mutation tests must be serialized against each fixed node and restore test state.
- US4 T033-T036 depends on the complete behavior and owns topology lifecycle evidence.
- T037 then proves offline health, T038 proves canonical regressions, T039 records observed
  behavior, and T040 is the final architecture/scope gate.

## Parallel Opportunities

- T003 and T004 touch separate static/model tests while T002 handles settings/dependency.
- T005-T007 cover independent renderer, Nautobot, and gNMI boundaries before T008-T009.
- T011 and T013-T015 can run in parallel after T010; T012 follows T010 in the same activity test file.
- T022-T024 and T027-T029 can be authored in parallel after the successful flow is stable.
- T033 documentation/static checks and T034 real preflight code are independent until T035.

## Implementation Strategy

The MVP is T001-T021: prove pinned behavior, correct the sole renderer, lock typed
boundaries, and complete one healthy real deployment with independent validation. US2 adds
recovery/duplicate guarantees, US3 adds safe failures, and US4 proves explicit topology
lifecycle. Final tasks preserve all accepted features and enforce the stop before Feature
005 or any DHCP/ZTP/bootstrap work.

**Total: 40 approved tasks.**
