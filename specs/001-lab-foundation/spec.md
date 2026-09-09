# Feature Specification: Lab Foundation

**Feature Branch**: `001-lab-foundation`
**Created**: 2026-09-08
**Status**: Reference acceptance completed on 2026-09-09
**Input**: Establish a reproducible local supporting environment for a reusable
network automation framework, without implementing its automation pipeline.

## User Scenarios & Testing

### User Story 1 - Start A Healthy Supporting Lab (Priority: P1)

A developer follows a clean checkout's prerequisites and startup instructions,
then accesses Nautobot, Temporal/UI, and Kafka without manually fixing schemas,
service ordering, or networking.

**Why this priority**: Later automation cannot be validated on an unreliable base.
**Independent Test**: On the documented reference host, start with fresh named
volumes and run readiness checks plus real service smoke tests.

**Acceptance Scenarios**:

1. **Given** prerequisites and unused local ports, **when** the documented startup
   sequence runs on fresh state, **then** all required services become ready,
   initialization exits successfully, and local application access works.
2. **Given** running services, **when** smoke tests run, **then** an authenticated
   Nautobot API read, Kafka produce/consume, Temporal health/namespace read, UI
   access, and Nautobot background-service checks succeed independently.
3. **Given** a required dependency is stopped or an endpoint is invalid, **when**
   health checks run, **then** they fail within a bounded timeout and identify
   the dependency without exposing secrets or claiming the lab is healthy.

### User Story 2 - Restart And Diagnose Without Losing State (Priority: P2)

A developer stops/restarts services, retains useful data, diagnoses failures,
and can deliberately reset a disposable lab without accidentally resetting it
during routine startup.

**Why this priority**: Repeatability includes subsequent runs, not just first boot.
**Independent Test**: On an existing foundation deployment, create isolated test
fixtures, stop/remove containers without deleting volumes, recreate, and verify
fixtures. Test reset only in a separately named disposable Compose project.

**Acceptance Scenarios**:

1. **Given** a test Nautobot record, Kafka message, and Temporal namespace,
   **when** containers are removed/recreated with volumes retained, **then** those
   fixtures remain and initialization does not reset data or duplicate accounts.
2. **Given** incomplete initialization or a port collision, **when** startup fails,
   **then** diagnostics identify the failing service/step and document safe recovery.
3. **Given** a disposable test project and explicit reset authorization, **when**
   its volumes are deleted and it is started again, **then** only documented seed
   state returns; unrelated Docker projects and volumes are unaffected.

### User Story 3 - Develop Python Without Building Future Features (Priority: P2)

A developer installs one Python package reproducibly, validates local settings,
runs unit tests without containers, and invokes opt-in real-infrastructure tests.
They can understand where later Linux-based network labs will live.

**Why this priority**: This environment exists to develop automation, not merely
to display service dashboards.
**Independent Test**: Synchronize locked dependencies and run unit tests with
Docker stopped. Separately inspect the documented Linux topology validation path.

**Acceptance Scenarios**:

1. **Given** Git and `uv`, **when** the documented development setup runs, **then**
   the package imports, typed Pydantic settings reject invalid values, and unit
   tests pass without contacting external systems.
2. **Given** a healthy lab, **when** the opt-in integration suite runs, **then** it
   uses validated host endpoints and fails, rather than skips, if a service is down.
3. **Given** the network-lab guide, **when** a developer reviews prerequisites and
   the minimal topology, **then** the Linux requirement, SR Linux initial platform,
   validation command, and separation from foundation startup are unambiguous.

### Edge Cases

- Missing Docker daemon/Compose capability, unavailable image, unsupported CPU
  architecture, insufficient memory, or occupied port must not produce false health.
- Database initialization must finish before dependents migrate; multiple Nautobot
  processes must not race migrations; failed one-shots must block startup.
- Kafka must advertise reachable addresses for both host tests and Compose clients.
- Initialization after restart must not rotate Kafka cluster identity, overwrite
  local users, discard data, or require a destructive reset.
- Existing-volume password changes are not silently applied by first-boot scripts;
  document deliberate credential update versus disposable reset.
- Application health and optional network-device availability are distinct.

## Requirements

### Functional Requirements

- **FR-001**: Deliver documented reproducible startup on a declared Linux reference
  host, with required tools, resources, CPU architecture, and local port assumptions.
- **FR-002**: Run Kafka in single-node KRaft mode, Temporal and UI, PostgreSQL,
  Nautobot web and required background processes, and Redis. No ZooKeeper.
- **FR-003**: Document service communication and host/container endpoints. Publish
  only useful developer ports on loopback; databases and Redis stay private.
- **FR-004**: Provision required isolated application databases, schemas, local
  Nautobot admin access, and a Temporal `default` namespace automatically using
  ordered, repeatable initialization with visible failure status.
- **FR-005**: Persist PostgreSQL data, Kafka data/identity, and Nautobot media in
  named volumes. Redis cache/Celery state is disposable and need not survive
  recreation; it MUST NOT be treated as durable automation state.
- **FR-006**: Supply meaningful per-service checks and an aggregate readiness
  command, with bounded timeouts and nonzero failure status. Readiness excludes
  optional network nodes and nonexistent automation workflows.
- **FR-007**: Prove real Kafka message round-trip from the host and advertised
  internal-listener reachability, authenticated Nautobot API access/background
  readiness, and Temporal RPC/namespace/UI access. No automation workflow required.
- **FR-008**: Provide one typed Python package, supported Python, `uv` lockfile,
  Pydantic v2 settings, pytest unit tests, and separately selected integration tests.
- **FR-009**: Pin exact supported image patch tags and Python dependency versions;
  commit `uv.lock`, document tested image digests/platforms where useful, and
  document rebuild/sync commands. Compose digest pins are not required. Never
  ship `latest`.
- **FR-010**: Document local-only credentials, defaults, ignored local overrides,
  normal lifecycle, logs, safe recovery, and explicitly destructive project reset.
- **FR-011**: Provide minimal netlab/containerlab/SR Linux topology structure and
  Linux prerequisites/validation instructions, separate from Compose startup.
  Launching devices and configuring their network is not required for acceptance.
- **FR-012**: Verify cold start, repeat startup, retained-state recreation, dependency
  failure, and isolated reset against real supporting infrastructure; document evidence.
- **FR-013**: Keep initialization and probes explicit and small. No new orchestration
  service, generic health framework, event consumer, or always-idle automation worker.

### Key Entities

- **Lab settings**: Validated local endpoints, credentials, and bounded probe timeout;
  environment-specific connection data, never a competing source of network intent.
- **Service state**: Upstream application-owned data in named volumes, plus disposable
  smoke-test fixtures; no new application database schema in this feature.

## Success Criteria

- **SC-001**: A fresh-checkout walkthrough on the reference host needs no undocumented
  manual database/application repair and reaches readiness within 10 minutes after
  images are pulled and dependencies installed. Record actual time/resources.
- **SC-002**: Every required application-level probe and real integration smoke test
  passes; simulated dependency failure returns a named failure within 120 seconds.
- **SC-003**: All three retained-state fixtures survive container recreation; a second
  startup is successful without duplicates; isolated reset restores only seed state.
- **SC-004**: Locked install and all unit tests work with Docker stopped; integration
  tests run only when explicitly selected and never turn missing infrastructure green.
- **SC-005**: Documentation identifies all services, ports, volumes, credentials,
  supported/untested host paths, lifecycle commands, and scaffolding boundaries.
- **SC-006**: Delivered code contains no Kafka-to-Temporal consumer, network workflow,
  device access, intent schema, configuration template, or ZTP service.

## Out Of Scope

Production configuration deployment, provisioning workflows, Kafka-to-Temporal
automation, full Nautobot intent modeling, Jinja configuration generation, device
deployment/operational validation, DHCP/ZTP, production auth/secrets, Kubernetes,
cloud, HA, monitoring platforms, backup/restore systems, and custom Nautobot Apps.
No placeholder domain/events/workflows/activities/rendering package hierarchy.

## Assumptions

- One developer and one local Compose project; no availability or throughput SLA.
- Reference acceptance: Ubuntu 24.04 LTS x86-64; macOS supporting-services use is
  conditional on verified image compatibility, not a network-lab support promise.
- Internet is available for initial tool/dependency/image downloads. No offline build.
- Host-managed `uv` runtime satisfies the requested development container OR runtime.
- Exact image patch-tag selection is an implementation verification gate, not an
  architectural open question. Tested digests/platforms are validation evidence,
  not required Compose pins. Architecture changes still require approval.
