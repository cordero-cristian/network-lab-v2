# Tasks: Nautobot Intent To Deterministic SR Linux Artifact

**Input**: Design documents from `specs/002-nautobot-srlinux-artifact/`

**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`,
`contracts/interfaces.md`, `quickstart.md`

**Status**: APPROVED FOR IMPLEMENTATION on 2026-09-09 after required platform,
fixture-isolation, and loopback-model adjustments.

**Tests**: Required by the specification and constitution. Write the stated tests
first and confirm relevant failures before implementation.

## Phase 1: Setup And Contract Lock

**Purpose**: Add only the dependency/output conventions required by this feature.

- [x] T001 Add Jinja2 3.1-compatible dependency bounds and the `network-render` console entry point to `pyproject.toml`, regenerate `uv.lock`, and verify Hatch's existing package target includes `src/network_automation/templates/srlinux/config.j2` without duplicate force-inclusion or unrelated dependencies/services. Covers FR-007/012/015.
- [x] T002 [P] Ignore `/artifacts/` in `.gitignore` and add the exact raw acceptance sample at `tests/fixtures/nautobot/leaf01.json` using the Device/Interface/IPAddress and namespaced BGP contract. Covers FR-001/003/010.

---

## Phase 2: User Story 1 - Produce A Reviewed Device Artifact (Priority: P1) MVP

**Goal**: Prove reviewed offline `leaf01` output and transform a uniquely named real
Nautobot intent into its own deterministic artifact without device access.

**Independent Test**: Compare offline `leaf01` bytes with
`tests/fixtures/expected/leaf01.cfg`; separately API-create a uniquely named Device
and verify the production adapter/converter/renderer/writer output semantically and
for repeated byte identity.

### Tests For User Story 1

- [x] T003 [P] [US1] Write failing valid-construction, stable Platform `network_driver` plus diagnostic-display conversion, supported driver with absent/arbitrary display, unsupported driver with SR Linux-looking display, name-independent LoopbackIntent, zero/multiple Device, pagination, non-JSON/non-2xx/auth/server/timeout, related Platform/IP failure, malformed relation/type/boolean, and credential-redaction tests in `tests/unit/test_intent_models.py` and `tests/unit/test_nautobot_intent.py` using `tests/fixtures/nautobot/leaf01.json`. Covers FR-001-FR-004/006/013.
- [x] T004 [P] [US1] Add reviewed `tests/fixtures/expected/leaf01.cfg` and failing render, natural-interface-order with numeric-padding tie/reversed input, numeric-neighbor-order, final-newline, 100-repeat byte-identity, package-resource template lookup outside repository root, deterministic-path, missing-directory, and successful atomic-write tests in `tests/unit/test_srlinux_render.py`. Covers FR-007-FR-011 and SC-002.

### Implementation For User Story 1

- [x] T005 [US1] Implement frozen `LoopbackIntent`, `InterfaceIntent`, `BgpNeighborIntent`, `BgpIntent`, and `DeviceIntent` with stable platform identifier/diagnostic display, typed scalars, and aggregate invariants in `src/network_automation/intent/models.py`; add only required exports in `src/network_automation/intent/__init__.py`. Make T003 model cases pass. Covers FR-003-FR-005.
- [x] T006 [US1] Implement the bounded token-authenticated `NautobotClient`, exact-name Device lookup, related Platform `network_driver`, Role/optional Location metadata, paginated `device_id` Interface lookup, related IPAddress reads, raw compound mapping, and `device_intent_from_nautobot()` conversion that selects one virtual loopback without retaining its source name in `src/network_automation/intent/nautobot.py`. Make T003 pass offline. Covers FR-001-FR-003.
- [x] T007 [US1] Implement the single presentation-only package template in `src/network_automation/templates/srlinux/config.j2` and package-resource-loaded strict deterministic rendering, `nokia_srl` identifier gate, `system0` loopback output, total natural/full-name and numeric ordering, loopback router-ID derivation, artifact path, directory creation, and atomic writer in `src/network_automation/rendering/srlinux.py` with exports in `src/network_automation/rendering/__init__.py`. Make T004 pass exactly. Covers FR-006-FR-011.
- [x] T008 [US1] Write failing CLI success/error/redaction/output-path tests, then implement minimal argparse orchestration in `tests/unit/test_render_cli.py`, `src/network_automation/cli/render.py`, and `src/network_automation/cli/__init__.py`; print the path only after a complete write. Covers FR-012.
- [x] T009 [US1] Write `tests/integration/test_nautobot_render.py` to create a per-run suffixed Status, Namespace, Manufacturer, Platform with `network_driver=nokia_srl`, DeviceType, Role, LocationType, Location, Prefixes, Device `feature002-leaf-<suffix>` with matching serial, three Interfaces, and three IPAddress assignments. Read only immutable ContentType metadata, record every created object ID, exercise the production adapter/converter/renderer/writer for the unique Device, assert dynamic hostname/path and repeated bytes without golden comparison, and in `finally` delete only recorded IDs in reverse order even after assertion/adapter failure. Missing Nautobot must fail, not skip. Covers FR-001/012/014 and SC-001/005.
- [x] T010 [US1] Run US1 unit files and the real integration test against canonical Feature 001 Nautobot; confirm offline `leaf01` matches golden bytes while the unique real fixture produces its own deterministic artifact, makes no device/Kafka/Temporal call, and leaves none of its recorded objects after cleanup. Record results in `docs/validation.md`. Covers SC-001/002/005.

**Checkpoint**: The first complete Nautobot-to-artifact slice works for valid
`leaf01` intent and can be reviewed independently.

---

## Phase 3: User Story 2 - Reject Invalid Intent Safely (Priority: P2)

**Goal**: Reject malformed, ambiguous, inconsistent, and unsupported state before
artifact replacement and preserve any prior complete artifact.

**Independent Test**: Run only invalid raw/model/render/write cases with no external
services and verify every failure is named and leaves the target absent or unchanged.

### Tests For User Story 2

- [x] T011 [P] [US2] Add failing malformed IPv4, invalid/bool ASN, empty/unsafe name, missing stable platform/role, missing/disabled/management/multiple virtual loopback, duplicate routed interface, duplicate neighbor, local-address neighbor collision, unsupported physical type, IPv6-only, missing routed description/address, and multiple-address cases plus source-loopback-name independence and optional-description-to-null cases to `tests/unit/test_intent_models.py` and `tests/unit/test_nautobot_intent.py`. Covers FR-004/005 and SC-003.
- [x] T012 [P] [US2] Add failing unsupported `network_driver` despite SR Linux-looking display, supported `nokia_srl` with absent/arbitrary display, StrictUndefined/template failure, unwritable directory, staging-write failure, `os.replace` failure, temporary-file cleanup, and absent/prior-target preservation cases to `tests/unit/test_srlinux_render.py`; add CLI nonzero/redaction/orchestration-failure cases to `tests/unit/test_render_cli.py`. Covers FR-006/011/012 and SC-003.

### Implementation For User Story 2

- [x] T013 [US2] Complete only the explicit field/cross-field validators and external-shape errors required by T011 in `src/network_automation/intent/models.py` and `src/network_automation/intent/nautobot.py`; do not add a validation framework. Covers FR-004/005.
- [x] T014 [US2] Complete platform/template/filesystem failure handling and atomic replacement required by T012 in `src/network_automation/rendering/srlinux.py` and `src/network_automation/cli/render.py`; preserve credential-safe errors and prior artifact bytes. Covers FR-006/011/012.
- [x] T015 [US2] Run the US2 unit cases with Docker stopped and verify zero failure cases create/replace a corrupt artifact; record results in `docs/validation.md`. Covers SC-003/004.

**Checkpoint**: Valid artifacts still match exactly and every specified invalid state
fails before unsafe output.

---

## Phase 4: User Story 3 - Develop And Verify Without Infrastructure (Priority: P2)

**Goal**: Keep ordinary development fully offline while retaining explicit real
integration evidence.

**Independent Test**: With Docker stopped, locked sync/import/default unit tests pass
and explicit integration fails; after restoring canonical Nautobot, integration passes.

### Tests And Validation For User Story 3

- [x] T016 [US3] With Docker stopped, run `uv sync --locked`, import `network_automation.intent` and `network_automation.rendering`, run `uv run pytest` and all Feature 002 unit files, then explicitly select `tests/integration/test_nautobot_render.py` and prove dependency absence fails rather than skips. Record commands/results in `docs/validation.md`. Covers FR-013/014 and SC-004.
- [x] T017 [US3] Restore canonical Feature 001 Nautobot without resetting its volumes, rerun `uv run network-lab-check`, Feature 001 service integrations, and Feature 002 real integration; verify fixture cleanup leaves unrelated Nautobot state unchanged. Record results in `docs/validation.md`. Covers FR-001/014 and SC-005.
- [x] T018 [US3] After T016 and T017, document the implemented command, exact Nautobot source mapping, artifact ownership/path, failure behavior, integration fixture safety, and explicit boundaries in `README.md` and `docs/validation.md`; keep Feature 001 operational guidance unchanged except legitimate shared command references. Covers FR-010/012/014/015.

**Checkpoint**: Offline and real-infrastructure paths are both independently proven.

---

## Phase 5: Final Acceptance And Scope Review

**Purpose**: Execute the planned walkthrough and reject architectural drift.

- [ ] T019 Follow `specs/002-nautobot-srlinux-artifact/quickstart.md` from a clean checkout on the canonical host; verify golden bytes, 100-repeat determinism, deterministic path, atomic failure safety, real Nautobot data flow, ignored output, and no device access. Update `docs/validation.md`. Covers FR-001-FR-014 and SC-001-SC-005.
- [ ] T020 Recheck `.specify/memory/constitution.md`, all Feature 002 artifacts, dependencies/imports/source tree, and `git diff` for Nautobot ownership, typed boundary, presentation-only Jinja, one package, and absence of device/Kafka/Temporal/ZTP/custom-App/vendor-framework/future scaffolding. Record final evidence in `specs/002-nautobot-srlinux-artifact/checklists/review.md` and mark tasks complete only with evidence. Covers FR-015 and SC-006.

## Dependencies And Execution Order

- T001 and T002 establish dependency and fixture contracts.
- T003 and T004 can run in parallel after setup; both must fail before implementation.
- T005 -> T006 completes the typed external boundary; T007 depends on T005 and T004.
- T008 depends on T006/T007. T009 depends on T006-T008. T010 completes US1.
- T011 and T012 can run in parallel after US1; T013 and T014 implement their narrow
  failure behavior, then T015 completes US2.
- T016 -> T017 -> T018 serialize evidence and documentation updates to
  `docs/validation.md`.
- T019 follows all stories. T020 is the final task and approval/scope gate.

## Parallel Examples

- US1: T003 model/conversion tests and T004 rendering/golden tests touch separate files.
- US2: T011 intent failures and T012 rendering/write failures touch separate concerns.
- US3 has no safe file-level parallel task because T016-T018 all update
  `docs/validation.md`; execute them in order.

## Implementation Strategy

The MVP is Phase 1 plus US1: one valid real Nautobot device to one reviewed artifact.
US2 adds fail-closed behavior without expanding intent scope. US3 proves the same
code remains locally testable and genuinely integrated. Final acceptance then checks
determinism and forbidden-scope absence. No phase permits device deployment, events,
workflows, ZTP, extra vendors, or additional network features.

**Total: 20 approved tasks. Implement and validate in dependency order.**
