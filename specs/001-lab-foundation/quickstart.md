# Quickstart And Validation

**Implemented contract.** Root README carries the tested commands and
`docs/validation.md` records actual evidence and platform limitations.

## Prerequisites

Ubuntu 24.04 LTS x86-64 reference host, Git, `uv`, Docker Engine, Compose v2 with
`up --wait --wait-timeout` and completed/healthy dependency support. Proposed budget:
8 vCPU, 16 GiB RAM, 40 GiB free disk for supporting services. Exact tested tool/image
versions and measured usage must be recorded. Network access for downloads;
loopback ports 8000, 8080, 9092, 7233 available; permission to use Docker.

macOS Docker Desktop supporting services are conditional on verified manifests
and runtime compatibility, especially ARM64. netlab/containerlab devices require
a documented Linux host/VM and are not part of this startup sequence.

## Clean Start

From a clean checkout at repository root:

```sh
cp .env.example .env
uv sync --locked
uv run pytest tests/unit
docker compose config --quiet
docker compose pull
docker compose up -d --wait --wait-timeout 600
docker compose --profile init up --no-deps --force-recreate --exit-code-from temporal-namespace temporal-namespace
uv run network-lab-check
uv run pytest tests/integration/test_services.py
```

`.env.example` contains clearly labeled local-only DB/Redis/admin passwords,
Nautobot secret key, fixed KRaft cluster ID, connection defaults, and host port
overrides. `.env` is ignored. Do not copy these defaults into production or bind
the services to a public interface. Initialization creates databases/schemas,
the Nautobot admin and Temporal default namespace; no manual UI repair step.

Open Nautobot at `http://localhost:8000` with the documented local admin; open
Temporal UI at `http://localhost:8080` and verify the default namespace is accessible.
An empty workflow list is expected; it is not an automation-worker health failure.

## Daily Lifecycle

```sh
docker compose ps --all
docker compose logs --tail=100 nautobot-init
docker compose logs --tail=100 temporal-schema
docker compose logs --tail=100 kafka
docker compose down
docker compose up -d --wait --wait-timeout 600
docker compose --profile init up --no-deps --force-recreate --exit-code-from temporal-namespace temporal-namespace
uv run network-lab-check
```

Expected: same data, no duplicate users, no Kafka reformat, no migration races.
Use targeted service logs after failure; do not delete volumes to mask a startup
bug. Fix port allocation, resource allocation or config and rerun failed
initialization explicitly as documented for the pinned image. Startup scripts
do not apply changed first-boot database passwords to existing data.

## Acceptance Walkthrough

1. With Docker stopped, prove locked install/package import/unit tests. No fixture
   may contact real infrastructure during unit collection or execution.
2. On the reference Linux host, pull images, time cold startup on fresh disposable
   volumes, run readiness and smoke tests. Record time <=600 seconds excluding pulls.
3. Verify host and internal Kafka message round-trips, authenticated Nautobot API,
   web/worker/Beat checks, Temporal SERVING/default namespace and UI backend access.
4. In a dedicated disposable project, create test-prefixed Nautobot/Kafka/Temporal
   fixtures; run repeated startup and `down`/recreate; verify fixtures persist.
5. In that project only, stop dependencies and confirm named health failures within
   120 seconds; restore and demonstrate recovery. Exercise failed initialization
   and occupied-port diagnostics without modifying the user's existing lab.
6. With explicit disposable-reset opt-in, remove that project's volumes and confirm
   a fresh boot has seed state but no old fixtures. Never run global Docker prune.
7. Record exact commands/results, patch tags, useful tested digests/platforms,
   host/tool versions, resource usage, and remaining limitations in
   `docs/validation.md`. All required Linux checks
   must pass before calling Feature 001 accepted.

Automated lifecycle entry point (it owns only a separately named project and
isolated ports): `LAB_RUN_LIFECYCLE=1 uv run pytest tests/integration/test_lifecycle.py`.

## Destructive Reset

Only after explicit authorization, `docker compose down --volumes` deletes the
current project's DBs, events, and media. Redis is disposable regardless and is
not durable automation state. Rerunning the startup
sequence recreates seed state, not the lost data. This is not a backup/restore tool.
Destructive reset has been exercised only against disposable lifecycle projects.

## Optional Network Scaffolding

After installing the separately documented/pinned Linux netlab/containerlab tuple,
the create-only check from `lab/` is:

```sh
netlab create topology.yml -p clab
```

It validates topology/generates provider artifacts without starting devices.
Validate the syntax against the selected netlab release. Ignore generated outputs;
do not commit generated inventories/configs. Node startup, Jinja network rendering,
deployment, and operational tests are later features. Do not equate this check
with a running SR Linux node or complete automation pipeline.
