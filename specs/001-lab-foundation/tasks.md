# Tasks: Lab Foundation

**Input**: [spec.md](spec.md), [plan.md](plan.md), [research.md](research.md),
[data-model.md](data-model.md), [developer contract](contracts/developer-interface.md),
[quickstart.md](quickstart.md).

**Status**: APPROVED FOR IMPLEMENTATION on 2026-09-08. Check tasks only after
their implementation and required available verification are complete.
Tests are required by the constitution/spec, not optional template boilerplate.
No automatic commits, pushes, issue creation, or persistent-data reset.

## Phase 1: Setup And Compatibility Gate

- [x] T001 Verify maintained versions and exact image patch tags/platform manifests for all images and Python/tooling; inspect pinned image entrypoints, schema/admin tooling and health support; record selections plus useful tested digests/platforms and limitations in `specs/001-lab-foundation/research.md` and `docs/validation.md`. Do not require Compose digest pins. Resolve compatibility before Compose; request approval for architectural/scope changes. Covers FR-001/009.
- [x] T002 Create the minimal package `src/network_automation/__init__.py`, `pyproject.toml`, `.python-version`, and `uv.lock` with supported Python 3.12 patch, Pydantic v2/settings, pytest and currently needed probe clients. Configure pytest default collection to `tests/unit`; no Jinja/device/event/workflow dependencies. Covers FR-008/013.

## Phase 2: Shared Configuration Boundary

- [x] T003 Write failing tests in `tests/unit/test_settings.py` for documented defaults, environment-over-file precedence, valid host:port/HTTP URLs, invalid/missing settings, secret redaction and import without external access. Covers FR-008/010.
- [x] T004 Implement `src/network_automation/settings.py` per `data-model.md`; create local-only `.env.example` and update `.gitignore`. Document host port/project overrides shared with Compose, including disposable-test isolation; make T003 pass. Covers FR-003/008/010.

## Phase 3: US1 - Healthy Supporting Lab (P1, MVP)

**Independent test**: Clean-volume startup, readiness and real service smoke suite
on the reference host; no device or automation workflow required.

- [x] T005 [P] [US1] Write failing mocked probe tests in `tests/unit/test_health.py`: success, all-service reporting, HTTP auth/RPC/Kafka/Compose failures, one-shot failure, worker/Beat checks, redacted diagnostics, 10-second probe and 120-second aggregate limits. Covers FR-006/013.
- [x] T006 [P] [US1] Write `tests/integration/test_services.py` for real authenticated Nautobot API, targeted worker/Beat checks, unique-topic host/internal Kafka produce-consume, Temporal SERVING/default namespace, and UI backend access. Missing services must fail, not skip; cleanup only test-owned fixtures. Covers FR-007.
- [x] T007 [US1] Add PostgreSQL/Redis Compose services, a PostgreSQL named volume, private ports, health checks, and minimal `scripts/init-postgres.sh` for three databases and isolated non-superuser application roles; use exact patch tags from T001. Redis has no persistence/AOF requirement. Covers FR-002/003/004/005/009.
- [x] T008 [US1] Add single combined Kafka KRaft service in `compose.yaml`, stable cluster/node ID, persistent data path, replication-1 internal settings, distinct host/internal advertised listeners, private controller listener and broker health check. Covers FR-002/003/005/006.
- [x] T009 [US1] Add Temporal server/UI/schema/namespace services to `compose.yaml`, `config/temporal/config.yaml`, and small `scripts/init-temporal.sh` / `scripts/init-temporal-namespace.sh` only where native commands need coordination. Gate server on schema success, namespace on RPC health, and UI only on healthy Temporal. Keep namespace initialization explicit/repeatable; aggregate health and acceptance fail visibly when its one-shot fails or `default` is absent. Support repeated setup without data loss and SQL visibility only. Covers FR-002/003/004/006/009.
- [x] T010 [US1] Add Nautobot web/worker/scheduler/init services to `compose.yaml`, `config/nautobot/nautobot_config.py`, and minimal `scripts/init-nautobot.py`. Use one migration owner, create-if-absent local admin, shared media, skip-init runtime processes, targeted worker health and Beat heartbeat; keep exactly one scheduler. Covers FR-002/003/004/005/006/010.
- [x] T011 [US1] Implement explicit checks/CLI in `src/network_automation/health.py` and entry point `network-lab-check` in `pyproject.toml`; use Pydantic settings, supported image-native probes through bounded argument-array subprocesses where needed, no registry/framework. Make T005 pass. Covers FR-006/013.
- [ ] T012 [US1] Run `docker compose config --quiet`, cold start with `docker compose up -d --wait --wait-timeout 600`, explicit `docker compose --profile init up --no-deps --force-recreate --exit-code-from temporal-namespace temporal-namespace`, `uv run network-lab-check`, and `uv run pytest tests/integration/test_services.py` on the reference host. Prove UI starts from healthy Temporal independently while aggregate health still requires a successful namespace one-shot and existing `default` namespace. Fix real compatibility/networking/init/health failures, record command results and cold-start duration in `docs/validation.md`. Covers FR-001/006/007 and SC-001/002.

**Checkpoint**: All required services are actually usable independently. This is
an MVP checkpoint, not permission to omit remaining Feature 001 acceptance.

## Phase 4: US2 - Retained State And Recovery (P2)

**Independent test**: Explicit isolated lifecycle suite against the US1 stack,
not dependent on optional topology or new automation behavior.

- [x] T013 [US2] Write `tests/integration/test_lifecycle.py` with explicit `LAB_RUN_LIFECYCLE=1` guard, unique Compose project/loopback ports, fresh seed-state checks, test-owned Nautobot/Kafka/Temporal fixtures, repeated startup and retained-volume recreation assertions. Use `LAB_KAFKA_HOST_PORT` consistently for publication, advertisement and host bootstrap; assert isolated broker metadata before creating fixtures while the normal lab also runs. Prove test teardown cannot target the normal lab. Covers FR-005/010/012.
- [x] T014 [US2] Extend `tests/integration/test_lifecycle.py` with failed initialization (including namespace-init failure remaining visible and making aggregate health fail without blocking UI startup), dependency-stop, occupied-port and recovery cases, bounded named health failure, and destructive reset of that isolated project only. Unit-test safety checks in `tests/unit/test_health.py` if shared helpers are necessary; no general test orchestration framework. Covers FR-004/006/012.
- [x] T015 [US2] Run `LAB_RUN_LIFECYCLE=1 uv run pytest tests/integration/test_lifecycle.py`; fix repeatability/recovery issues in existing `compose.yaml`/initializers/checks without data-dropping workarounds. Record fixture persistence, second-start behavior, failure detection, isolated reset and limitations in `docs/validation.md`. Covers FR-012 and SC-002/003.
- [x] T016 [US2] Document ordinary stop/restart, logs/one-shot diagnostics, volume ownership, first-boot credential changes, safe reruns, and separately warned destructive reset in `README.md`; keep `specs/001-lab-foundation/quickstart.md` synchronized. Covers FR-005/010 and SC-005.

## Phase 5: US3 - Developer Runtime And Network Scaffolding (P2)

**Independent test**: Locked install/import/unit tests with Docker stopped; network
topology validation separately on a suitable Linux host, without node launch.

- [ ] T017 [US3] With Docker stopped, run `uv sync --locked`, `uv run python -c "import network_automation"`, and `uv run pytest tests/unit`; ensure default `uv run pytest` is unit-only and explicit integration selection fails for missing infrastructure. Record evidence and developer commands in `README.md` / `docs/validation.md`. Covers FR-008 and SC-004.
- [x] T018 [P] [US3] Add a minimal single SR Linux node using netlab's containerlab provider in `lab/topology.yml`; document Linux/tools/image/CPU/privilege requirements, tested or unverified version tuple, macOS/ARM64 caveats, and create-only validation in `docs/network-lab.md`. Ignore generated netlab/containerlab artifacts in `.gitignore`. No startup hooks or device configuration. Covers FR-001/011/013.
- [ ] T019 [US3] Verify `netlab create topology.yml -p clab` from `lab/` on the selected Linux/tool tuple; record what was validated in `docs/validation.md`, without claiming device operation. If unavailable, record the limitation explicitly; do not block supporting-service health on optional node operation. Covers FR-011 and SC-005.

## Phase 6: Final Acceptance And Scope Review

- [ ] T020 Follow `specs/001-lab-foundation/quickstart.md` from a separate clean source checkout/copy and fresh disposable project on the reference Linux host; rerun all required unit/service/lifecycle checks, verify only loopback application ports are published, local secrets ignored, all pins/lock present, no undocumented steps, and update `README.md` / `docs/validation.md`. Do not claim acceptance while required Linux checks remain unrun. Covers FR-001/003/009/010/012 and SC-001 through SC-005.
- [ ] T021 Recheck constitution and absence of future-feature behavior, remove unnecessary wrappers/dependencies, synchronize spec/plan/tasks/agent context and record final evidence in `specs/001-lab-foundation/checklists/review.md`. Mark implementation tasks complete only with their verification evidence; report remaining platform limitations. Covers FR-013 and SC-006.

## Dependencies And Parallel Opportunities

T001 -> T002 -> T003 -> T004 precede US1. After T004, T005 and T006 can run in
parallel (different files). T007 -> T008 -> T009 -> T010 edit shared Compose and
must be serialized; they may proceed alongside the test-writing tasks. T011
depends on T005 and the concrete T007-T010 interfaces. T012 depends on T006-T011.
T013 -> T014 -> T015 -> T016 follow US1. T017 follows T012 and uses a window with
Docker stopped; do not run it alongside real infrastructure tests. T018 can run
independently after T001/T004 without shared-file edits in progress; T019 follows
T018. T020 follows all story tasks; T021 is last.

Example parallel batch: T005 mocked probe tests plus T006 real service tests.
Do not parallelize Compose edits merely because services are logically independent.
US2 requires the US1 infrastructure, but its tests can be invoked independently;
US3 unit tests do not require a running US1 environment.

## Requirement Coverage

| Requirement | Tasks |
|---|---|
| FR-001 prerequisites/reproducible host | T001, T012, T018, T020 |
| FR-002 required services | T007-T010 |
| FR-003 communications/local ports | T004, T007-T010, T020 |
| FR-004 initialization | T007, T009, T010, T014 |
| FR-005 persistence | T007, T008, T010, T013, T016 |
| FR-006 health/failure | T005, T008-T012, T014 |
| FR-007 real service integration | T006, T012 |
| FR-008 Python development | T002-T004, T017 |
| FR-009 pins/compatibility | T001, T007, T009, T020 |
| FR-010 credentials/lifecycle | T003, T004, T010, T013, T016, T020 |
| FR-011 topology prerequisites | T018, T019 |
| FR-012 lifecycle acceptance | T013-T015, T020 |
| FR-013 simplicity/boundaries | T002, T005, T011, T018, T021 |

**Total: 21 approved tasks. Implement and validate in dependency order.**
