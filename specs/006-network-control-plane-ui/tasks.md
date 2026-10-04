---

description: "Implementation tasks for the read-only network automation control plane UI"
---

# Tasks: Network Automation Control Plane UI

**Input**: Design documents from `specs/006-network-control-plane-ui/`

**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/`, approved
Lavish direction, and explicit owner implementation approval

**Tests**: Required. Backend unit tests mock external boundaries; frontend tests use lightweight
component/route tests; integration and acceptance observe real canonical services without mutation.

**Status**: IMPLEMENTATION AND CANONICAL ACCEPTANCE COMPLETE — 2026-09-15

Implementation was approved on 2026-09-14 with on-demand live reads, a structurally read-only API,
and bounded shallow-list/full-detail Temporal hydration. Feature 005 remains deferred and outside
this task list.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel only when its phase dependencies are complete and files do not overlap
- **[Story]**: User story traceability label
- Every task names the files it creates or changes

## Phase 1: Setup (Shared Tooling)

**Purpose**: Add only the required Python/frontend build dependencies and project scaffolding

- [x] T001 Add bounded FastAPI and Uvicorn runtime dependencies and test support in `pyproject.toml` and regenerate `uv.lock`
- [x] T002 [P] Initialize the locked React/TypeScript/Vite/Tailwind/Vitest/Testing Library project and scripts in `ui/package.json`, `ui/package-lock.json`, `ui/tsconfig.json`, `ui/vite.config.ts`, and `ui/index.html`
- [x] T003 [P] Add the patch-pinned Node build and nginx static runtime stages in `Dockerfile.ui` and same-origin SPA/API behavior in `ui/nginx.conf`
- [x] T004 [P] Add the frontend entry point and locally bundled IBM Plex font/Tailwind base tokens matching the approved Lavish direction in `ui/src/main.tsx`, `ui/src/App.tsx`, and `ui/src/styles.css`
- [x] T005 Add validated UI/API ports, API deadlines, history limits/concurrency, artifact root, and live-read settings without credential defaults in `src/network_automation/settings.py` and `.env.example`
- [x] T006 Run `uv lock --check`, `npm --prefix ui ci`, frontend type checking, and static build setup; correct only setup files in `pyproject.toml`, `uv.lock`, and `ui/`

---

## Phase 2: Foundational Read Boundaries

**Purpose**: Establish strict models, safe API behavior, and browser-only API access before stories

**CRITICAL**: No story endpoint may return raw upstream data or bypass these boundaries.

- [x] T007 [P] Write strict serialization, unknown-enum, bounds, UTC timestamp, relative artifact path, and secret/config exclusion tests in `tests/unit/test_api_models.py`
- [x] T008 [P] Write route validation, safe 404/422/500 body, GET/HEAD-only and prohibited-import structure, no permissive CORS, no-store, request deadline, and redacted logging tests in `tests/unit/test_api_safety.py`
- [x] T009 Implement `SourceAvailability`, envelopes, health, device, workflow, deployment, topology, validation, artifact, and safe error read models from `data-model.md` in `src/network_automation/api/models.py`
- [x] T010 Implement FastAPI lifespan client ownership, request IDs/deadlines, sanitized exception handling, cache headers, and read-only router registration in `src/network_automation/api/app.py` and `src/network_automation/api/__init__.py`
- [x] T011 [P] Write frontend API decoding, abort, timeout, non-overlap, visibility pause, terminal-stop, and safe-error tests in `ui/src/api/client.test.ts` and `ui/src/api/usePolling.test.tsx`
- [x] T012 Implement typed same-origin fetch, runtime response guards, AbortController deadlines, and visibility-aware bounded polling without global state in `ui/src/api/client.ts`, `ui/src/api/types.ts`, and `ui/src/api/usePolling.ts`
- [x] T013 Run foundational backend/frontend tests and inspect generated browser assets for internal URLs, credentials, and configuration content in `tests/unit/test_api_models.py`, `tests/unit/test_api_safety.py`, and `ui/src/api/`

**Checkpoint**: Strict safe read boundaries exist; no authoritative source adapter or product screen is yet required

---

## Phase 3: User Story 1 - Assess Platform Health (Priority: P1) MVP

**Goal**: Show useful real overview and component health with graceful partial failure

**Independent Test**: Open the overview against canonical services, verify authoritative counts and
health, stop one safe read dependency, and confirm unaffected sections remain usable without any
automation action.

### Tests For User Story 1

- [x] T014 [P] [US1] Write Nautobot, Kafka, Temporal, worker-poller, consumer-group, timeout, unknown, and overall health aggregation unit tests in `tests/unit/test_api_health.py`
- [x] T015 [P] [US1] Write overview partial aggregation, authoritative count, retained-window, empty-state, and no-fabricated-metric API tests in `tests/unit/test_api_overview.py`
- [x] T016 [P] [US1] Write keyboard-accessible AppShell navigation/status/freshness and overview healthy/loading/empty/partial/stale/unavailable/error desktop/375-pixel rendering tests in `ui/src/components/AppShell.test.tsx` and `ui/src/pages/OverviewPage.test.tsx`

### Implementation For User Story 1

- [x] T017 [US1] Refactor existing bounded Nautobot/Kafka/Temporal probes into reusable redacted functions without changing `network-lab-check` behavior in `src/network_automation/health.py`
- [x] T018 [US1] Implement concurrent health aggregation, Temporal workflow/activity poller checks, Kafka consumer-group member checks, capability state, and `GET /api/health` in `src/network_automation/api/health.py`
- [x] T019 [US1] Implement visibility-first workflow/deployment summaries with at most eight shallow start/close hydrations for overview, exact Nautobot interface/cable/BGP-ownership topology reads, independent section deadlines, and `GET /api/overview` in `src/network_automation/intent/nautobot.py`, `src/network_automation/api/workflows.py`, `src/network_automation/api/devices.py`, and `src/network_automation/api/app.py`
- [x] T020 [P] [US1] Implement text/icon status, section availability, freshness, and shared empty/loading/error surfaces in `ui/src/components/Status.tsx` and `ui/src/components/AsyncSection.tsx`
- [x] T021 [US1] Implement the compact operator shell with only Overview, Devices, and Workflows routes in `ui/src/components/AppShell.tsx` and `ui/src/App.tsx`
- [x] T022 [US1] Implement health strip, compact real counts, topology/activity regions, 15-second visible polling, and partial/empty states in `ui/src/pages/OverviewPage.tsx`
- [x] T023 [US1] Run US1 backend/frontend tests and prove the overview remains useful under mocked independent source failures in `tests/unit/test_api_health.py`, `tests/unit/test_api_overview.py`, and `ui/src/pages/OverviewPage.test.tsx`

**Checkpoint**: US1 independently provides a read-only health and overview MVP

---

## Phase 4: User Story 2 - Inspect Device Intent And State (Priority: P2)

**Goal**: Browse real Nautobot devices and inspect source-separated intent, retained outcomes, and
one optional bounded Feature 004 live validation

**Independent Test**: Select a canonical device and verify inventory/intent, latest retained
deployment/artifact/validation, and one bounded live read while proving no render/write/deploy call.

### Tests For User Story 2

- [x] T024 [P] [US2] Write device list/status/role/platform/location/primary-IP, incomplete-device, pagination/bounds, and raw-payload exclusion tests in `tests/unit/test_api_devices.py`
- [x] T025 [P] [US2] Write artifact-root confinement, retained latest-outcome join, missing-history, live timeout, existing-check mapping, and no artifact/deploy mutation tests in `tests/unit/test_api_device_detail.py`
- [x] T026 [P] [US2] Write keyboard drill-down and loading/empty/partial/stale/unavailable/error desktop/375-pixel device list/detail, source/freshness, mismatch, live state, and metadata-only artifact tests in `ui/src/pages/DevicesPage.test.tsx` and `ui/src/pages/DeviceDetailPage.test.tsx`

### Implementation For User Story 2

- [x] T027 [US2] Add explicit bounded Device/Status/Role/Platform/Location/primary-IP list reads while preserving exact deployment-intent normalization in `src/network_automation/intent/nautobot.py`
- [x] T028 [US2] Extract pure expected-state construction and existing validation-result comparison for read reuse without changing Feature 004 workflow/activity behavior in `src/network_automation/activities/deployment.py`
- [x] T029 [US2] Implement DeviceSummary projection, retained latest-deployment join, safe artifact metadata, and `GET /api/devices` in `src/network_automation/api/devices.py`
- [x] T030 [US2] Implement source-separated DeviceDetail and one 15-second-budget `live=true` read through the existing Feature 004 SR Linux read/validation path, with no producer/workflow/render/write/deploy/Set imports in `src/network_automation/api/devices.py`
- [x] T031 [P] [US2] Implement dense responsive device inventory rows and 30-second visible polling in `ui/src/pages/DevicesPage.tsx`
- [x] T032 [US2] Implement aligned intent/live checks, inline existing mismatches, retained deployment band, metadata-only artifact, one initial `live=true` request, and 30-second `live=false` Nautobot/Temporal refresh that never repeats or discards the timestamped live snapshot in `ui/src/pages/DeviceDetailPage.tsx`
- [x] T033 [US2] Run US2 tests and prove device list/detail retain useful sections across missing intent, history, artifact, credentials, and device timeout cases in `tests/unit/test_api_devices.py`, `tests/unit/test_api_device_detail.py`, and `ui/src/pages/DeviceDetailPage.test.tsx`

**Checkpoint**: US2 independently provides truthful device-centered intent and observation

---

## Phase 5: User Story 3 - Diagnose Workflow And Deployment Outcomes (Priority: P2)

**Goal**: Browse recent durable executions and diagnose exact history-supported stages and safe
business outcomes

**Independent Test**: Compare one retained success and available failure with Temporal metadata and
history, including a handled domain failure whose Temporal execution status is completed.

### Tests For User Story 3

- [x] T034 [P] [US3] Write admitted-prefix/type, default-25/max-50 visibility lists, concurrency-four shallow start/close hydration, overview-eight bound, detail-only full history, deadline, retention-gap, and unknown-payload tests in `tests/unit/test_api_workflows.py`
- [x] T035 [P] [US3] Write activity correlation/attempt/timing, pending/finalizing/unknown stage, business-versus-execution failure, and raw failure/stack exclusion tests in `tests/unit/test_api_workflow_history.py`
- [x] T036 [P] [US3] Write keyboard drill-down and loading/empty/partial/stale/unavailable/error desktop/375-pixel workflow/deployment list/detail, successful/failed/running timeline, terminal polling stop, unknown stage, and safe failure tests in `ui/src/pages/WorkflowsPage.test.tsx` and `ui/src/pages/WorkflowDetailPage.test.tsx`

### Implementation For User Story 3

- [x] T037 [US3] Reuse the US1 visibility, shallow start/close, limit, semaphore-four, and deadline primitives to add exact run pinning and full activity-history fetch only for one detail request through the lifespan-provided Temporal client in `src/network_automation/api/workflows.py`
- [x] T038 [US3] Implement allowlisted Pydantic start/terminal decoding and map Temporal execution state separately from render/deployment business outcome in `src/network_automation/api/workflows.py`
- [x] T039 [US3] Implement scheduled-event correlation, attempt/timing mapping, pending/finalizing/unknown stages, and safe failures without raw payloads in `src/network_automation/api/workflows.py`
- [x] T040 [US3] Implement workflow/deployment list/detail GET routes and deployment-only projections with validated IDs, filters, limits, and run pins in `src/network_automation/api/workflows.py`
- [x] T041 [P] [US3] Implement dense newest-first workflow list, status/kind/stage/device/timing columns, empty/partial states, and 10-second visible polling in `ui/src/pages/WorkflowsPage.tsx`
- [x] T042 [US3] Implement the approved durable-stage timeline, run-context panel, inline safe failure, unknown/not-reached stages, and 4-second running-only polling in `ui/src/components/WorkflowTimeline.tsx` and `ui/src/pages/WorkflowDetailPage.tsx`
- [x] T043 [US3] Run US3 mapping/frontend tests and accepted Feature 003 history replay to prove old histories remain valid in `tests/unit/test_api_workflows.py`, `tests/unit/test_api_workflow_history.py`, `tests/unit/test_render_workflow_replay.py`, and `ui/src/pages/WorkflowDetailPage.test.tsx`

**Checkpoint**: US3 independently diagnoses render and deployment runs without Kafka ingestion

---

## Phase 6: User Story 4 - Explore The Small Lab Topology (Priority: P3)

**Goal**: Show selectable real lab nodes and only supported physical or logical BGP links

**Independent Test**: Display canonical devices, exact cable relationships where present, and
unambiguous address-resolved BGP intent; verify incomplete/ambiguous data creates no invented link.

### Tests For User Story 4

- [x] T044 [P] [US4] Write physical endpoint, exact BGP neighbor IP ownership, ambiguity/self/one-sided exclusion, deduplication, node status-source, limit, and stable ordering tests in `tests/unit/test_api_topology.py`
- [x] T045 [P] [US4] Write SVG node/link semantics, physical/logical legend, keyboard selection/detail navigation, and loading/empty/partial/stale/unavailable/error desktop/375-pixel tests in `ui/src/components/Topology.test.tsx`

### Implementation For User Story 4

- [x] T046 [US4] Expose the shared US1 deterministic physical/BGP topology projection through bounded `GET /api/topology` availability/error semantics in `src/network_automation/api/devices.py`
- [x] T047 [US4] Implement keyboard node selection, selected-device summary, normal device-detail links, and physical/logical source legend in `ui/src/components/Topology.tsx`
- [x] T048 [US4] Complete the lightweight role/name-arranged responsive SVG, text/icon status, unknown/incomplete states, and no-overflow behavior in `ui/src/components/Topology.tsx`
- [x] T049 [US4] Integrate real topology selection and partial/incomplete states into overview without adding graph libraries in `ui/src/pages/OverviewPage.tsx` and run `tests/unit/test_api_topology.py` plus `ui/src/components/Topology.test.tsx`

**Checkpoint**: US4 independently provides an honest small-lab topology

---

## Phase 7: Runtime, Documentation, And Cross-Cutting Validation

**Purpose**: Profile-gate the services, prove safety and regressions, and record canonical evidence

- [x] T050 [P] Write exact default/init/automation/ui service-set, one build-owner, loopback port, no volume/store/socket, read-only artifact mount, liveness, and nginx proxy contract tests in `tests/unit/test_automation_compose.py`
- [x] T051 Add `automation-ui-api` and `automation-ui` only under the `ui` profile with existing-image reuse, API liveness, static health, loopback ports, read-only artifacts, and no upstream-health startup block in `compose.yaml`
- [x] T052 Add optional `automation-ui-api` attachment to the existing external device management network with runtime-only credentials in `compose.device-access.yaml`
- [x] T053 [P] Document UI profile startup, health, polling, data limits, source gaps, SSH forwarding, diagnostics, safe stop, and no mutation in `README.md` and `docs/network-lab.md`
- [x] T054 [P] Add backend integration coverage for real Nautobot lists/details, retained Temporal history, completed deployment, available retained failure, topology, and safe partial failure without intent/device/workflow fixture mutation in `tests/integration/test_control_plane_api.py`
- [x] T055 [P] Add the complete `contracts/frontend.md` screen/state/desktop/375-pixel/keyboard matrix across shell, lists, details, timeline, and topology in `ui/src/App.states.test.tsx`
- [x] T056 Run locked backend/frontend unit, type, build, Compose, API serialization/leak, and accepted Temporal replay checks from `specs/006-network-control-plane-ui/quickstart.md`; constrain any corrections to `src/network_automation/api/`, `ui/`, `Dockerfile.ui`, `compose.yaml`, `compose.device-access.yaml`, `.env.example`, `pyproject.toml`, `uv.lock`, and Feature 006 test files
- [x] T057 Run canonical read-only API/UI acceptance through SSH forwarding; measure API liveness under 1 second, useful healthy overview under 5 seconds, SC-001 10-second health diagnosis, SC-003 two-selection device path, and SC-005 15-second failure diagnosis; execute desktop/375-pixel views and one authorized bounded live device read; record actual evidence in `docs/validation.md`
- [x] T058 Under explicit test approval, stop/start one reversible safe read dependency, prove section-level degradation and recovery without changing or resetting data/automation state, and record actual evidence in `docs/validation.md`
- [x] T059 Run accepted Features 001-004 unit/component/integration/canonical commands applicable to the host and record actual results and platform limits in `docs/validation.md`
- [x] T060 Inspect API responses, browser network/assets, and API/UI logs for credentials, raw configuration, stacks, upstream payloads, internal URLs, absolute artifact paths, mutation routes, and non-loopback listeners; record redacted results in `docs/validation.md`
- [x] T061 Run `uv build`, frontend production build, Compose validation, `git diff --check`, Spec Kit analysis, and both Feature 006 checklists in `specs/006-network-control-plane-ui/checklists/`

## Dependencies And Execution Order

- Phase 1 has no implementation dependency but requires explicit owner approval.
- Phase 2 depends on Phase 1 and blocks all user stories.
- US1 depends on Phase 2 and implements the shared real workflow/deployment and topology summary
  projections required for its complete overview; its checkpoint cannot use injected empty data in
  place of available authoritative data.
- US2-US4 depend on US1's shared summary projections. US2 consumes the latest-deployment join, US3
  extends Temporal summaries with detailed history, and US4 extends the topology summary with the
  dedicated route and selection UX. Each later story remains independently testable against the
  accepted US1 boundary.
- Phase 7 requires all selected stories and performs the only canonical runtime acceptance.
- Device live acceptance requires existing authorized topology/network access; absence degrades the
  section and does not authorize topology creation or deployment.

## Parallel Opportunities

- T002-T004 can proceed in parallel after T001 is not required because they touch frontend/runtime
  files only; T005 remains the settings owner.
- T007, T008, and T011 are separate foundational test files and can proceed in parallel.
- Within each story, backend and frontend tests marked `[P]` can be written concurrently before
  implementation.
- T020 and backend US1 implementation can proceed in parallel; T031 and backend US2 implementation
  can proceed in parallel; T041 and backend US3 implementation can proceed in parallel.
- T044/T045 and T050/T053/T054/T055 operate on distinct files after their phase gates.

## Parallel Examples

### User Story 1

```text
Task T014: backend native health aggregation tests
Task T015: backend overview partial aggregation tests
Task T016: frontend shell and overview state tests
```

### User Story 2

```text
Task T024: inventory mapping tests
Task T025: detail/artifact/live safety tests
Task T026: frontend device list/detail tests
```

### User Story 3

```text
Task T034: bounded Temporal list/decode tests
Task T035: history/stage/failure tests
Task T036: frontend workflow/timeline tests
```

### User Story 4

```text
Task T044: topology source and deduplication tests
Task T045: responsive SVG interaction tests
```

## Implementation Strategy

1. Preserve source ownership and establish strict safe boundaries first.
2. Deliver US1 as the health/overview MVP with honest empty/partial sections.
3. Add US2 device intent and optional one-shot live validation without writes.
4. Add US3 bounded durable-history diagnosis without changing workflow starts or consuming Kafka.
5. Add US4 deterministic small-lab topology without physical inference or graph infrastructure.
6. Add the optional runtime only after all source and browser safety tests pass.
7. Treat real canonical evidence and accepted Features 001-004 regressions as completion gates.

## Explicit Exclusions

No deploy/render/rerun/retry/remediate/edit/cancel/publish/ZTP controls; no Nautobot/device mutation;
no authentication/RBAC/users/settings/reports/alerts/notifications; no WebSockets/SSE; no UI store,
cache, queue, Kafka consumer, analytics warehouse, API gateway, public exposure, raw config/history,
general topology engine, Next.js, SSR, SEO, or mobile app.

## Approval Gate Satisfied

The owner explicitly approved the Feature 006 scope, read API/source map, Temporal strategy,
topology semantics, Lavish visual direction, polling, runtime, test plan, and approval decisions in
`plan.md` on 2026-09-14 before T001 began.
