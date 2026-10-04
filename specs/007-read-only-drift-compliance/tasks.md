---

description: "Implementation tasks for read-only drift and compliance detection"
---

# Tasks: Read-only Drift and Compliance Detection

**Input**: Design documents from `specs/007-read-only-drift-compliance/`

**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/`, `quickstart.md`

**Approval Gate**: Implementation was separately approved on 2026-09-22 and completed on 2026-09-23.

**Tests**: Tests are required by FR-030, FR-034, and FR-035 and MUST be written first and observed failing before the corresponding implementation.

**Organization**: Tasks are grouped by user story so configuration drift, operational health, and presentation remain independently testable.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel because it changes different files and has no dependency on another incomplete task in the same phase
- **[Story]**: Maps the task to User Story 1, 2, or 3
- Every task includes exact repository paths

## Phase 1: Setup and Baseline

**Purpose**: Establish actual pre-implementation evidence without changing dependencies or runtime topology.

- [X] T001 Run the existing Python and frontend test suites and record exact baseline commands, counts, failures, platform, and the absence of Feature 007 behavior in `docs/validation.md`

**Checkpoint**: Baseline is recorded; any pre-existing failure is distinguished from Feature 007 work.

---

## Phase 2: Foundational Comparison Boundaries

**Purpose**: Add the strict transient models and observed-leaf validation shared by configuration and operational stories.

**Critical**: Complete this phase before any user-story implementation.

- [X] T002 Add failing strict-model tests for frozen/extra-forbid behavior, safe scalar bounds, unique keys, derived counts, aggregate consistency, UTC timestamps, and cross-result timestamp/device invariants in `tests/unit/test_device_comparison.py`
- [X] T003 Implement `ConfigurationCheck`, `ConfigurationDriftResult`, `OperationalHealthCheck`, `OperationalHealthResult`, and `DeviceComparison` Pydantic v2 models in `src/network_automation/devices/comparison.py` until T002 passes
- [X] T004 Add failing observed-leaf validation tests covering exact integer ASNs, rejection of booleans/string ASNs, non-empty strings of at most 128 characters, absent `None` values, whole-comparison invalidation, and sanitized errors in `tests/unit/test_device_comparison.py`
- [X] T005 Implement the explicit expected-path leaf validation and safe comparison helpers in `src/network_automation/devices/comparison.py` without changing `src/network_automation/devices/srlinux.py` or `src/network_automation/devices/validation.py`

**Checkpoint**: Strict models and canonical leaf validation pass independently; Feature 004 code and behavior remain untouched.

---

## Phase 3: User Story 1 - Identify Expected Configuration Drift (Priority: P1) MVP

**Goal**: Produce an expected-state-only `in_sync|drifted` configuration result from Nautobot-derived expected state and one normalized observation without classifying operational failures as drift.

**Independent Test**: Supply one expected state and controlled observed mappings directly to the pure comparator; verify every supported configuration match/mismatch, stable key/order/count, address-presence rule, expected-only scope, and BGP/session separation without API, UI, or device I/O.

### Tests for User Story 1

- [X] T006 [US1] Add failing configuration comparison tests for hostname, interface/subinterface admin state, exact address presence, local ASN, peer-AS, absent leaves, type-exact equality, deterministic ordering/counts, ignored unexpected keys, non-preferred address readiness, interface oper-down, and BGP-down-not-drift in `tests/unit/test_device_comparison.py`

### Implementation for User Story 1

- [X] T007 [US1] Implement the pure expected-only configuration comparison and `in_sync|drifted` aggregation in `src/network_automation/devices/comparison.py` using existing Feature 004 path helpers and `ExpectedDeviceState`
- [X] T008 [US1] Run and stabilize the User Story 1 slice in `tests/unit/test_device_comparison.py`, proving FR-003, FR-005, FR-007, FR-009-FR-015, FR-022-FR-023, FR-030, and FR-035 without weakening assertions

**Checkpoint**: User Story 1 is independently functional as a pure configuration-drift comparison; no API or UI is required.

---

## Phase 4: User Story 2 - Assess Operational Health Separately (Priority: P1)

**Goal**: Produce a separate `healthy|degraded|unavailable` result for expected interface, address, and BGP operational facts without influencing configuration drift.

**Independent Test**: Supply expected state and controlled normalized observations directly to the pure health comparator; verify healthy, unhealthy, unavailable, mixed aggregate, address-readiness, and BGP-session outcomes independently from the configuration result.

### Tests for User Story 2

- [X] T009 [US2] Add failing operational-health tests for interface/subinterface up/down/absence, address preferred/non-preferred/absence, BGP established/non-established/absence, healthy/degraded/all-unavailable aggregates, deterministic ordering/counts, and ignored unexpected keys in `tests/unit/test_device_comparison.py`

### Implementation for User Story 2

- [X] T010 [US2] Implement the pure expected-object operational-health comparison and `healthy|degraded|unavailable` aggregation in `src/network_automation/devices/comparison.py` without importing configuration status into health decisions
- [X] T011 [US2] Run and stabilize the User Story 2 slice in `tests/unit/test_device_comparison.py`, proving FR-006, FR-008-FR-013, FR-022-FR-023, FR-030, and SC-003-SC-004 without weakening assertions

**Checkpoint**: User Story 2 is independently functional as a pure operational-health comparison; BGP down degrades health while matching configuration remains in sync.

---

## Phase 5: User Story 3 - Inspect Trustworthy Results in Device Detail (Priority: P2)

**Goal**: Expose the two pure results as separately sourced observations through the existing one-shot Feature 006 device-detail route and present them as distinct responsive UI sections.

**Independent Test**: Open device detail with one controlled live observation and verify separate statuses, checks, counts, intent/device provenance, common timestamp, historical-validation labeling, one-read/no-read/no-retry behavior, partial failure, and absence of mutation controls on desktop and 375-pixel layouts.

### Tests for User Story 3

- [X] T012 [US3] Add failing bundle tests for one `DeviceComparison` timestamp/device identity, atomic whole-comparison failure on malformed leaves, and independent configuration/health aggregation in `tests/unit/test_device_comparison.py`
- [X] T013 [P] [US3] Add failing API-model tests for `ComparisonSources`, `ConfigurationDriftObservation`, `OperationalHealthObservation`, nested-result/status invariants, shared timestamps, and forbidden legacy `live_state` fields in `tests/unit/test_api_models.py`
- [X] T014 [P] [US3] Add failing route/service/integration assertions for successful one-read comparison, `live=false` zero reads, unavailable-intent zero reads, timeout/authentication/invalid-response provenance, common timestamps, retained independent sections, removed `live_state`, zero automatic retries, GET/HEAD-only routes, and forbidden mutation/workflow/Kafka/render/deploy imports in `tests/unit/test_api_devices.py`, `tests/unit/test_api_device_detail.py`, `tests/unit/test_api_safety.py`, and `tests/integration/test_control_plane_api.py`
- [X] T015 [P] [US3] Update desired-response fixtures and add failing frontend contract/device-detail/safety tests for separate source-aware drift/health sections, loading/unavailable/partial states, retained historical validation, non-color status cues, no mutation controls, no sensitive data, and no automatic live refresh in `ui/src/test/fixtures.ts`, `ui/src/api/client.test.ts`, `ui/src/pages/DeviceDetailPage.test.tsx`, `ui/src/App.states.test.tsx`, and `ui/src/App.test.tsx`

### Implementation for User Story 3

- [X] T016 [US3] Implement the atomic `compare_device_state` bundle over one expected state, one observed mapping, and one UTC timestamp in `src/network_automation/devices/comparison.py`
- [X] T017 [US3] Replace `LiveStateSummary` with strict comparison source/result/observation response models and update `DeviceDetail` in `src/network_automation/api/models.py`
- [X] T018 [US3] Map Nautobot intent and exactly one `read_srlinux_native_state` call into two source-aware observations, preserve the 15-second budget and independent sections, and return explicit not-requested/source-failure states in `src/network_automation/api/devices.py`
- [X] T019 [US3] Replace legacy live-state TypeScript types and runtime guards with the two explicit observation contracts in `ui/src/api/types.ts` and `ui/src/api/client.ts`
- [X] T020 [US3] Replace the combined Live State panel with separate Configuration Drift and Operational Health panels while preserving one initial `live=true` request and later `live=false` refreshes in `ui/src/pages/DeviceDetailPage.tsx` and `ui/src/styles.css`
- [X] T021 [US3] Complete the API/browser integration wiring required by the already-failing response-shape tests for removed `live_state`, separate observations, source provenance, and common timestamps in `src/network_automation/api/devices.py`, `ui/src/api/client.ts`, and `ui/src/pages/DeviceDetailPage.tsx`
- [X] T022 [US3] Run and stabilize the complete User Story 3 backend/frontend slice in `tests/unit/test_device_comparison.py`, `tests/unit/test_api_models.py`, `tests/unit/test_api_devices.py`, `tests/unit/test_api_device_detail.py`, `tests/unit/test_api_safety.py`, `tests/integration/test_control_plane_api.py`, `ui/src/api/client.test.ts`, `ui/src/pages/DeviceDetailPage.test.tsx`, `ui/src/App.states.test.tsx`, and `ui/src/App.test.tsx`

**Checkpoint**: All three stories are functional; device detail performs at most one explicit live read and never collapses configuration drift into operational health.

---

## Phase 6: Polish, Safety, and Acceptance

**Purpose**: Prove cross-cutting read-only boundaries, regressions, responsive behavior, and real-lab evidence before declaring implementation complete.

- [X] T023 Run and stabilize the structural safety assertions created in T014-T015, inspect for no background device polling, datastore/policy framework, raw secret/config/response exposure, or Feature 005 runtime path, and resolve failures without weakening tests in `tests/unit/test_api_safety.py` and `ui/src/App.test.tsx`
- [X] T024 Run all Python tests, frontend tests, frontend production build, and existing Features 001-004 plus Feature 006 regression suites while keeping deferred Feature 005 unchanged and outside runtime/acceptance; record exact commands, counts, failures, and fixes in `docs/validation.md`
- [X] T025 Execute the read-only canonical Nautobot 3.2.5 and SR Linux comparison scenarios from `specs/007-read-only-drift-compliance/quickstart.md` without manufacturing drift, and record actual source versions, timestamps, natural states, limitations, and one-read evidence in `docs/validation.md`
- [X] T026 Verify device detail at desktop and 375-pixel widths plus API/browser/log security inspection, and time an operator identifying drift-only, health-only, both, and unavailable fixtures within 10 seconds; record timings, overflow, keyboard, non-color status, source-provenance, no-mutation, and no-sensitive-data evidence in `docs/validation.md`
- [X] T027 Run `graphify update .`, inspect the resulting Feature 007 relationships for unintended architecture layers, and retain the refreshed graph artifacts under `graphify-out/`

**Checkpoint**: Feature 007 has unit, integration, frontend, canonical, responsive, security, and Features 001-004 plus Feature 006 regression evidence while deferred Feature 005 remains unchanged. Any unavailable canonical scenario is reported as unverified rather than manufactured.

---

## Dependencies and Execution Order

### Phase Dependencies

- **Phase 1 Setup**: No dependency; records the actual baseline.
- **Phase 2 Foundation**: Depends on T001 and blocks all user-story implementation.
- **User Story 1**: Depends on T002-T005.
- **User Story 2**: Depends on T002-T005 and is logically independent of User Story 1, although both intentionally edit the same narrow comparison files.
- **User Story 3**: Depends on completed User Stories 1 and 2 because it bundles and presents both results.
- **Polish and Acceptance**: Depends on all desired user stories and requires the canonical runtime only for T025-T026.

### User Story Dependency Graph

```text
Setup -> Foundation -> US1 Configuration Drift ---\
                       US2 Operational Health -----+-> US3 Device Detail -> Safety/Acceptance
```

### Within Each User Story

- Write the listed tests first and observe the intended failure before implementation.
- Implement strict models before comparison functions and comparison functions before API mapping.
- Update backend contract and frontend consumer atomically before removing legacy `live_state` fixtures.
- Do not change Feature 004 `validation_result()` semantics to satisfy Feature 007 tests.
- Stop at each checkpoint and run the focused tests before continuing.

### Parallel Opportunities

- After Foundation, US1 and US2 are logically independent, but simultaneous edits to `src/network_automation/devices/comparison.py` and `tests/unit/test_device_comparison.py` require coordination and are not marked `[P]`.
- T013, T014, and T015 can run in parallel after T012 because they target independent API-model, API-route, and frontend files.
- Canonical runtime acceptance cannot begin until automated regression and build checks pass.

---

## Parallel Examples

### User Stories 1 and 2

```text
Developer A: T006-T008 - configuration checks and aggregation
Developer B: T009-T011 - operational checks and aggregation
Coordination: integrate both branches before T012; resolve only the shared comparison/test files
```

### User Story 3 Tests

```text
Task T013: API observation model tests in tests/unit/test_api_models.py
Task T014: Device-detail one-read/source-failure tests in tests/unit/test_api_devices.py and tests/unit/test_api_device_detail.py
Task T015: Frontend contract/presentation tests in ui/src/api/client.test.ts and UI page/state tests
```

---

## Implementation Strategy

### MVP First

1. Complete Setup and Foundation.
2. Complete User Story 1 to deliver independently testable expected configuration drift.
3. Stop and validate the pure configuration result before adding operational health or presentation.

### Incremental Delivery

1. Foundation establishes strict models and rejects malformed observations.
2. User Story 1 adds expected configuration comparison without I/O.
3. User Story 2 adds operational health without changing configuration status.
4. User Story 3 performs one existing live read and exposes both results through the current API/UI.
5. Final validation proves read-only boundaries and real-lab behavior without manufacturing evidence.

### Scope Guardrails

- Do not enumerate unexpected extra configuration.
- Do not parse rendered artifacts for intent.
- Do not add policy, severity, waiver, scoring, plugin, driver, persistence, workflow, telemetry, or remediation abstractions.
- Do not add a compatibility `live_state` alias without a newly identified external consumer and approved plan change.
- Do not treat BGP/session or interface operational failure as configuration drift.
- Separate owner approval followed task consistency review on 2026-09-22.
