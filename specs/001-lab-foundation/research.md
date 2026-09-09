# Research: Lab Foundation

**Date**: 2026-09-08. Documentation research only; no image pulls, running services,
or compatibility claims based on tests. Exact release verification remains T001.

## Decisions

### One PostgreSQL Server, Isolated Databases

Decision: PostgreSQL 16 candidate, Nautobot role/database and Temporal role with
`temporal`/`temporal_visibility`. Temporal's `postgres12` schema family supports
PostgreSQL 12+, not just version 12. Nautobot 2.4 docs require PostgreSQL 12+;
newer Nautobot docs raise that minimum. 16 is a conservative shared candidate.
Rationale: small local footprint while preserving application ownership.
Rejected: separate DB servers without a current isolation/load need; SQLite or
Temporal dev-server persistence as a substitute for the intended server setup.

Sources: [Nautobot dependencies](https://docs.nautobot.com/projects/core/en/stable/user-guide/administration/installation/),
[Nautobot 2.4 dependencies](https://github.com/nautobot/nautobot/blob/ltm-2.4/nautobot/docs/user-guide/administration/installation/index.md),
[Temporal PostgreSQL visibility](https://docs.temporal.io/self-hosted-guide/visibility/postgresql).

### Temporal Server With SQL Visibility

Decision: dedicated schema one-shot, real Temporal server, UI, namespace one-shot.
Candidate upstream example pins: `temporalio/server:1.31.0`,
`temporalio/admin-tools:1.31.0`, `temporalio/ui:2.49.1`; these are example references,
not pulled/approved implementation pins. PostgreSQL supports advanced visibility
with server 1.20+; Elasticsearch is unnecessary for this lab.
Rationale: durable server-shaped foundation without unrelated infrastructure.
Rejected: Elasticsearch, old archived Compose snippets, idle admin-tools container,
and a dummy application workflow solely for startup verification.
Check RPC SERVING plus namespace and UI access, not just an open port.

Sources: [Current Compose sample](https://github.com/temporalio/samples-server/blob/main/compose/docker-compose-postgres.yml),
[Sample pins](https://github.com/temporalio/samples-server/blob/main/compose/.env),
[Visibility support](https://docs.temporal.io/self-hosted-guide/visibility).

### Nautobot Web, Worker, And One Scheduler

Decision: same pinned image/config for web, Celery worker, Beat, and initializer.
Candidate Nautobot 2.4 LTM, contingent on current maintenance verification;
candidate Redis 7.2 subject to supported patch/client compatibility.
Rationale: workers handle native background functions; Beat enables normal
periodic/scheduled functions. These are not a custom automation runtime.
Use one migration/admin initialization owner and skip image initialization in
other processes. `/health/` proves more than process presence; worker and Beat
need separate targeted/freshness checks supported by the pinned release.
Rejected: migration races, omitting background-service health, custom Nautobot
Apps/jobs, or introducing HA Redis/cache/broker clusters.
Logical Redis DBs separate cache and broker use. Redis has no volume or AOF
durability requirement; its contents may be recreated and MUST NOT be treated as
durable automation state. Temporal owns durable workflow execution.

Sources: [Nautobot services](https://docs.nautobot.com/projects/core/en/stable/user-guide/administration/installation/services/),
[Docker guide](https://docs.nautobot.com/projects/core/en/stable/user-guide/administration/guides/docker/),
[Health checks](https://docs.nautobot.com/projects/core/en/stable/user-guide/administration/guides/health-checks/),
[Image entrypoint](https://github.com/nautobot/nautobot/blob/main/docker/docker-entrypoint.sh).

### One Kafka KRaft Node

Decision: Apache JVM image, combined broker/controller, stable cluster identity,
replication 1. Kafka docs explicitly show `apache/kafka:4.1.2`; verify maintenance,
manifest and release-specific settings before selecting the implementation pin.
Rationale: upstream-supported development shape, no fault-tolerance claim.
Rejected: ZooKeeper, a multi-broker cluster, Schema Registry, Kafka UI, and any
consumer implementation in 001. Host and Compose need distinct advertised listeners.

Sources: [Apache Docker image](https://kafka.apache.org/41/getting-started/docker/),
[KRaft combined mode](https://kafka.apache.org/41/operations/kraft/).

### Host Runtime And Separate Network Scaffolding

Decision: Python 3.12 managed by `uv`, Pydantic v2 settings, pytest, one package.
Only dependencies with current settings/probe/test uses are installed; no Jinja
or deployment clients yet. No worker that only sleeps and no framework skeleton.
Linux x86-64 is the reference acceptance platform. macOS supporting-services
convenience is separate from device-host support. netlab/containerlab/SR Linux
versions are a documented optional tested tuple, not added to automation deps.
One-node topology may be validated with netlab's create-only command; no node
launch needed in 001, and generating configs is not proof of device operation.

Nautobot ARM64 is alpha; SR Linux ARM64 (multi-arch images since 24.10.1) is preview,
not equivalently qualified. x86 SR Linux needs SSSE3. containerlab depends on
Linux networking primitives; use a suitable Linux VM/host rather than treating
Docker Desktop Compose support as proof of network-lab compatibility.
Rejected: Docker-in-Docker, privileged network lifecycle as a supporting service,
automatic host modification, amd64 emulation silently forced on Apple Silicon.

Sources: [uv projects](https://docs.astral.sh/uv/guides/projects/),
[netlab installation](https://netlab.tools/install/),
[netlab platforms](https://netlab.tools/platforms/),
[containerlab macOS](https://containerlab.dev/macos/),
[SR Linux requirements](https://containerlab.dev/manual/kinds/srl/).

## Verified Implementation Pins

Registry/release checks on 2026-09-08 selected exact patch tags:
`networktocode/nautobot:2.4.41-py3.12`, `postgres:16.15-bookworm`,
`redis:7.2.16-bookworm`, `apache/kafka:4.1.2`,
`temporalio/server:1.31.0`, `temporalio/admin-tools:1.31.0`, and
`temporalio/ui:2.49.1`. All expose native Linux amd64 and arm64 manifests.
Nautobot 2.4.41 is an LTM-branch security release dated 2026-08-31. Temporal's
server/admin pair and UI match the current upstream sample set. Exact observed
manifest-list digests are recorded as evidence in `docs/validation.md`; Compose
does not pin digests. Python uses CPython 3.12.13 and committed `uv.lock`.

## Remaining Verification, Not Open Architecture

Image-specific commands, schema paths, health tooling and ARM64 manifests were
verified during implementation; exact tags and evidence are recorded above.
Implementation acceptance must demonstrate first boot, non-destructive repeated
initialization, internal/host Kafka access, targeted Celery/Beat checks, UI backend
access, credential bootstrap without leaks, and real retained-state recovery.
If unavailable on the current macOS ARM64 machine, report Linux acceptance blocked;
never substitute mocked success or declare cross-platform support untested.

For optional topology validation, current-release research on 2026-09-08 selected
an explicitly unverified candidate tuple: networklab 26.8 (Python 3.12 supported),
containerlab 0.79.0, and Nokia SR Linux 26.7.2-519. Installation and
`netlab create topology.yml -p clab` remain Linux-host acceptance work.
