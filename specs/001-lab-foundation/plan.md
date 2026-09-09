# Implementation Plan: Lab Foundation

**Branch**: `001-lab-foundation` | **Date**: 2026-09-08 | **Spec**: [spec.md](spec.md)
**Status**: Approved for implementation on 2026-09-08 after synchronized simplifications.

## Summary

Build one explicit Compose environment for supporting applications and one
host-managed Python development runtime. Prove applications work independently;
do not connect them into an automation pipeline. Eight long-running supporting
containers and three ordered one-shot initializers are delivered. No automation
worker runs yet, because there is no approved workflow to execute.

## Technical Context

- **Language/Version**: Python 3.12 for the automation package, exact supported patch
  recorded in `.python-version`; supporting apps keep their upstream image runtime.
- **Primary Dependencies**: Pydantic v2, pydantic-settings; `uv` lockfile; pytest and
  small HTTP/Kafka/Temporal clients for probes/tests only. Jinja2 deferred to 002.
- **Storage**: PostgreSQL 16 instance; three databases, two non-superuser application
  roles; disposable Redis 7.2 broker/cache; Kafka local disk; Nautobot media.
- **Testing**: pytest unit tests without infrastructure, opt-in real integration
  tests, explicitly invoked lifecycle tests against a disposable Compose project.
- **Target Platform**: Ubuntu 24.04 LTS x86-64 with Docker Engine/Compose v2. macOS
  Docker Desktop supporting-services path is conditional; Linux required for devices.
- **Project Type**: One Python package and supporting infrastructure, no new API server.
- **Performance Goals**: Ready within 600 seconds after pulls/sync; probe failures
  within 120 seconds. macOS measurements are recorded in `docs/validation.md`;
  reference Linux measurements remain pending.
- **Scale/Scope**: One developer, single Kafka node, single Temporal server, one DB
  server. No HA, production security, device workflows, or throughput benchmark.

## Constitution Check

| Gate | Pre-Design | Post-Design Evidence |
|---|---|---|
| Nautobot/Kafka/Temporal ownership preserved | Pass | Services not linked by new workflow code |
| Validated boundaries; rendering and device access isolated | Pass | Only settings model/probes; rendering/device logic absent |
| One package; no speculative automation service/layers | Pass | Host `uv` runtime; no idle worker or plugin skeleton |
| Reproducible, pinned, persistent, local-only Compose | Pass | Explicit graph/volumes; pin verification task before builds |
| Unit isolation plus real infrastructure proof | Pass | Separate unit/integration/lifecycle commands and failure cases |
| Bounded feature and approval checkpoint | Pass | Feature 001 approved; 002-005 remain deferred |

No constitutional exceptions or complexity waivers requested. These checks assess
the design, not a working deployment. Implementation must repeat them.

## Services And Communication

One Compose bridge network. Services address each other using Compose DNS, not
host loopback. Plaintext is explicitly local-lab-only. No proxy or Kafka dashboard.

| Service | Role / Connections | Host Port | Readiness |
|---|---|---|---|
| `postgres` | Nautobot DB plus Temporal default/visibility DBs | None | `pg_isready`; application/schema checks supplement it |
| `redis` | Disposable Nautobot cache, Celery broker/results; logical DB separation | None | Authenticated PING |
| `kafka` | Single combined KRaft broker/controller | `127.0.0.1:9092` | Broker API/metadata against internal listener |
| `temporal` | Server connects to its two PostgreSQL DBs | `127.0.0.1:7233` | RPC health reports SERVING |
| `temporal-ui` | UI backend connects to and waits only for healthy `temporal:7233` | `127.0.0.1:8080` | HTTP response; acceptance separately requires namespace |
| `nautobot` | Web/API connects to PostgreSQL and Redis | `127.0.0.1:8000` | `/health/` with DB/migration/cache checks |
| `nautobot-worker` | Celery background execution, same image/config as web | None | Targeted ping to this worker, not any worker |
| `nautobot-scheduler` | Exactly one Celery Beat scheduler, same image/config | None | Supported Beat heartbeat freshness |

Use admin tooling only through one-shots/`compose run --rm`, not an idle service.

Three one-shot services:

| Service | Dependency / Responsibility | Success |
|---|---|---|
| `temporal-schema` | Healthy PostgreSQL; version-matched SQL tool sets up/updates both schemas | Exit 0, schemas compatible |
| `temporal-namespace` | Healthy Temporal; admin tool creates `default` if absent | Exit 0, namespace readable |
| `nautobot-init` | Healthy PostgreSQL/Redis; sole owner of `post_upgrade` and create-if-absent local admin | Exit 0, migrations/admin present |

PostgreSQL's small first-volume initialization script creates `nautobot`,
`temporal`, and `temporal_visibility` databases. Role `nautobot` owns its database;
role `temporal` owns the other two. Do not give application roles superuser access.
The bootstrap PostgreSQL superuser is used only for initialization/administration.
Application roles must not be granted access to the other application's database;
revoke default public database access where necessary.

Nautobot web/worker/scheduler use `NAUTOBOT_DOCKER_SKIP_INIT=true` and wait for
`nautobot-init` successful completion. Worker/scheduler commands and heartbeat
checks must match the pinned release. Include Beat because normal scheduled
Nautobot maintenance/jobs should work; this is not a new automation scheduler.

Temporal waits for successful schema initialization; namespace initialization
waits for Temporal health. UI depends only on healthy Temporal and can start while
the explicit repeatable namespace one-shot is pending or failed. Aggregate health
and integration acceptance MUST inspect the one-shot result and required `default`
namespace, failing visibly without conflating that failure with UI process health.
Schema setup must distinguish
absent versus existing schemas and apply supported versioned updates without
dropping data. Compose ordering gates initial startup, not automatic dependency
recovery. Application reconnect behavior and explicit restart procedures are tested.

Kafka has stable configured KRaft cluster ID/node ID, replication factor 1 and
single-node internal topic settings. Advertised listeners: host `localhost:9092` by default,
internal `kafka:29092`; controller `kafka:29093` stays private. Bind listeners inside
the container appropriately; never advertise `0.0.0.0` or host-only `localhost`
to Compose clients. `LAB_KAFKA_HOST_PORT` (default 9092) must drive the loopback
published port, external advertised port, and default host-runtime bootstrap
address together. The container-side external listener remains port 9092;
internal `kafka:29092` does not change. Explicit bootstrap overrides remain valid
for external endpoints; lifecycle tests must supply their isolated endpoint.
Acceptance tests verify both client paths and returned broker metadata while
the ordinary lab and disposable project run simultaneously.

There is **no** Kafka -> Temporal or Nautobot -> Kafka integration in 001. The
host runtime connects to `localhost:8000`, `localhost:9092`, `localhost:7233`, and
`localhost:8080` for probes. DB and Redis probes run inside Compose.

## Persistence And Initialization

| Named Volume | Contents | Policy |
|---|---|---|
| `postgres-data` | All three application DBs, users, schemas, Temporal state | Retain on ordinary down/recreate |
| `kafka-data` | Topic logs and KRaft metadata/identity | Retain; no automatic reformat |
| `nautobot-media` | Uploaded/user-generated media shared by Nautobot processes | Retain; static assets remain image-managed |

Redis has no named volume or AOF durability requirement. Its cache and Celery
broker/result data may be recreated and MUST NOT carry durable workflow semantics;
Temporal remains the durable execution owner.

Use a fixed documented Compose project name (`network-lab`) with `-p` override
for isolated tests. No explicit global volume names that break project isolation.
Initialization is explicit, bounded, repeatable, and visibly failing; no broad
`|| true` hiding migrations or connectivity errors. Ordinary `down` retains data.
`down --volumes` is a separately documented, explicitly destructive operation.
Credentials set at first boot are not silently changed on existing volumes.

## Version Selection

Planning candidates, **not a certified or pull-tested matrix**: Nautobot 2.4 LTM
subject to maintained-release check, PostgreSQL 16, Redis 7.2, Apache Kafka 4.1,
Temporal server/admin tooling 1.31, UI 2.49. See [research.md](research.md).
T001 checks maintenance/security, exact patch tags, manifests, health tooling, and
compatibility; then records exact patch tags before writing Compose. Compose does
not require digest pins; tested image digests/platforms are validation evidence.
If a family is no longer maintained, select a supported compatible release and
update this record; architectural/scope changes require new user approval.
Do not silently force amd64 emulation on ARM or substitute Temporal dev-server.

## Host Prerequisites

Reference host: Ubuntu 24.04 LTS x86-64, Git, `uv`, Docker Engine and Compose v2
supporting health/completed dependencies, `up --wait`, and `--wait-timeout`.
Record exact tested tool versions during implementation. User must have Docker
access (equivalent to privileged host access), internet, and unused listed ports.
Proposed supporting-services budget: 8 vCPU, 16 GiB RAM allocated to Docker,
40 GiB free disk; measure rather than label these vendor-certified minimums.
For later nodes, recommend 32 GiB RAM and 100 GiB disk, adjusted per topology.

`uv` installs/manages Python 3.12; no globally installed app dependencies needed.
Docker Desktop on macOS may run supporting services if all selected image
architectures work. This session's macOS ARM64 host is not evidence of Linux
acceptance. Nautobot ARM64 is upstream alpha; SR Linux ARM64 is preview. Document
untested paths and use a suitable Linux host/VM rather than claim transparent parity.
Network scaffolding documents Linux, netlab/containerlab install, Docker privileges,
SR Linux image access/resources and x86 SSSE3; no privileged Compose service,
Docker-in-Docker, or host network change in foundation startup.

## Health And Verification

`docker compose up -d --wait --wait-timeout 600` must wait for configured runtime
health and dependency initializers. The namespace initializer uses the explicit
`init` profile and runs next with `docker compose --profile init up --no-deps
--force-recreate --exit-code-from temporal-namespace temporal-namespace`, because
it is deliberately not a UI dependency and successful
one-shot exit is not a long-running service health state. Its status remains visible.
`uv run network-lab-check`
then checks initializer success and actual host-facing
HTTP/API, Temporal RPC/default namespace, plus internal broker/background probes
using narrow explicit Compose commands. It reports every required service and
one-shot status, returns nonzero on failure, redacts credentials, bounds each
probe to 10 seconds and total runtime to 120 seconds. Use simple functions, not
a plugin/probe framework. No retries that mask permanent configuration failures.

Integration tests exercise Kafka unique-topic produce/consume (host and internal
listener), authenticated read of Nautobot API using local admin session/token
bootstrap supported by the pinned release, Temporal health/namespace read, UI
backend accessibility, and targeted worker/Beat health. Readiness is non-mutating
apart from login/session effects; write smoke fixtures belong to tests.
No test workflow/task queue is introduced merely to prove Temporal RPC works.

Lifecycle tests create uniquely named Nautobot metadata, Kafka topic/message,
and Temporal namespace fixtures; verify retained-state restart then remove only
their own fixtures where upstream permits (otherwise let retention expire in the
disposable project). Explicit lifecycle test opt-in is allowed to remove only
its dedicated project's volumes. No reset or `docker system prune` on the user's
ordinary lab. Failure tests stop dependencies in that disposable project and
verify bounded named failures and recovery. Record commands, tool versions,
image digests/platforms where useful, durations, results and limitations in `docs/validation.md`.

## Project Structure

The implementation uses the following delivered structure. Planned wrapper files
were omitted where pinned upstream commands directly satisfy their role.

```text
.
|-- AGENTS.md
|-- README.md
|-- compose.yaml
|-- .env.example
|-- .python-version
|-- .gitignore
|-- pyproject.toml
|-- uv.lock
|-- .specify/
|-- .opencode/commands/
|-- .agents/skills/
|-- specs/001-lab-foundation/
|   |-- spec.md
|   |-- plan.md
|   |-- research.md
|   |-- data-model.md
|   |-- quickstart.md
|   |-- contracts/developer-interface.md
|   |-- tasks.md
|   `-- checklists/review.md
|-- config/temporal/dynamicconfig/development-sql.yaml
|-- src/network_automation/
|   |-- __init__.py
|   |-- settings.py
|   `-- health.py
|-- tests/
|   |-- unit/test_settings.py
|   |-- unit/test_health.py
|   |-- integration/test_services.py
|   `-- integration/test_lifecycle.py
|-- scripts/
|   |-- init-postgres.sh
|   |-- init-temporal.sh
|   `-- init-nautobot.py
|-- docs/
|   |-- network-lab.md
|   `-- validation.md
`-- lab/topology.yml
```

Files may be omitted if a pinned upstream command directly satisfies their role;
do not add wrappers for wrappers. `health.py` provides current operational checks,
not domain automation interfaces. No automation Dockerfile, workflow worker,
Celery job implementation, domain model, or Jinja template is justified here.
Topology is a minimal one-node netlab `srlinux`/containerlab input with no custom
configuration; generated containerlab files are not a competing source of truth.

## Delivery Sequence And Complexity

Verify pins -> establish package/settings/tests -> supporting stack and real
smoke checks (US1) -> retained-state/failure/recovery verification (US2) -> finish
developer and topology guidance (US3) -> clean-checkout acceptance and scope review.
See [tasks.md](tasks.md) for paths, dependencies, and requirement coverage.
Shared PostgreSQL avoids an extra DB server; host `uv` avoids an idle dev container;
SQL visibility avoids Elasticsearch; no monitoring stack, broker UI, generic
framework, or premature custom App. Supporting schedulers/initializers have
concrete upstream lifecycle responsibilities, not future automation responsibilities.

**APPROVED: Implement only the bounded Feature 001 task sequence.**
