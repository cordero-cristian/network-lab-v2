# Network Automation Lab

A production-shaped local foundation for developing a reusable network automation
framework. Feature 001 supplies supporting services and host-side development
checks only. Nautobot owns network intent, Kafka transports events, and Temporal
owns durable workflow execution. No automation workflow is implemented yet.

## Services

| Service | Local endpoint | Persistence |
|---|---|---|
| Nautobot 2.4.41 | `http://localhost:8000` | PostgreSQL and `nautobot-media` |
| Kafka 4.1.2 (single-node KRaft) | `localhost:9092` | `kafka-data` |
| Temporal 1.31.0 | `localhost:7233` | PostgreSQL |
| Temporal UI 2.49.1 | `http://localhost:8080` | None |
| PostgreSQL 16.15 | Compose network only | `postgres-data` |
| Redis 7.2.16 | Compose network only | None; disposable cache/Celery broker |
| Nautobot worker and Beat | Compose network only | Application state in PostgreSQL |

Redis is not durable automation state. Temporal owns workflow durability.

## Prerequisites

Reference acceptance target: Ubuntu 24.04 LTS x86-64, Git, `uv`, Docker Engine,
and Docker Compose v2 supporting health dependencies and `up --wait`. Allocate
approximately 8 vCPU, 16 GiB RAM, and 40 GiB free disk for supporting services.
Docker access is equivalent to privileged host access.

The supporting stack has also been exercised on macOS ARM64 using Docker Desktop,
but this is not a substitute for Linux x86-64 acceptance. See
`docs/validation.md`. Network-device prerequisites are separate in
`docs/network-lab.md`.

The default loopback ports 8000, 8080, 9092, and 7233 must be free. Override all
matching `LAB_*_HOST_PORT` and host-side URL/address values in `.env` when needed.
Kafka's host port override automatically controls its advertised host listener.
If changing the Compose project, keep `COMPOSE_PROJECT_NAME` and
`LAB_COMPOSE_PROJECT` identical so startup and host-side checks target the same lab.

## Start

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

The sample credentials are strictly local-lab defaults. All published ports bind
to `127.0.0.1`; do not expose this stack to an untrusted network. Open Nautobot
with `admin` / `admin`, and use Temporal UI directly. The admin API token is in
`.env.example`; `.env` is ignored.

The namespace initializer is explicit and repeatable. Temporal UI depends only on
healthy Temporal, while `network-lab-check` requires the initializer to have exited
zero and the `default` namespace to exist.

## Develop And Test

```sh
uv sync --locked
uv run python -c "import network_automation"
uv run pytest
uv run pytest tests/integration/test_services.py
```

Default pytest discovery runs unit tests only and requires no Docker services.
Integration tests are explicit and fail when infrastructure is unavailable.

The lifecycle suite automatically creates and destroys only a uniquely named
Compose project on unused loopback ports:

```sh
LAB_RUN_LIFECYCLE=1 uv run pytest tests/integration/test_lifecycle.py
```

This opt-in test removes that disposable project's volumes. It refuses the normal
`network-lab` project name. Advanced callers may provide a `network-lab-test-*`
project and endpoint overrides; the test keeps the endpoints synchronized with
their host-port overrides.

## Operations

```sh
docker compose ps --all
docker compose logs --tail=100 <service>
docker compose down
docker compose up -d --wait --wait-timeout 600
docker compose --profile init up --no-deps --force-recreate --exit-code-from temporal-namespace temporal-namespace
uv run network-lab-check
```

Ordinary `down` retains PostgreSQL, Kafka/KRaft, and Nautobot media. Startup
re-runs supported schema/migration initialization without rotating the Kafka
cluster identity or changing an existing Nautobot admin password/token.

If startup fails, inspect `postgres`, `temporal-schema`, `nautobot-init`, and the
named failing service. Correct ports, resources, or configuration and rerun; do
not delete volumes to hide an initialization defect. Changing first-boot database
passwords in `.env` does not alter credentials already stored in PostgreSQL.

Only when deletion of this lab's data is explicitly intended:

```sh
docker compose down --volumes
```

This irreversibly deletes this project's databases, Kafka events/metadata, and
Nautobot media. It is not a backup operation and does not affect Redis semantics,
which are disposable already. Never use a global Docker prune for lab recovery.

## Scope And Specifications

Feature 001 contains no Kafka consumer, Temporal automation workflow/worker,
network intent model, Jinja rendering, device deployment, or DHCP/ZTP. Planning
and validation artifacts are under `specs/001-lab-foundation/`; permanent agent
instructions are in `AGENTS.md`.

Spec Kit 0.9.5 initialized OpenCode commands in `.opencode/commands/` and Codex
skills in `.agents/skills/`. The active branch is `001-lab-foundation`.
