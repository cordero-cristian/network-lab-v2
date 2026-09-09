# Feature 001 Validation Evidence

**Date**: 2026-09-08

## Environment

- Host: macOS 26.5.2 ARM64, Darwin 25.5.0
- Docker Desktop 4.81.0, Engine 29.6.1, Linux ARM64 VM
- Docker Compose v5.2.0
- `uv` 0.11.28; managed CPython 3.12.13
- Reference Ubuntu 24.04 LTS x86-64 acceptance: **not available on this host**

An unrelated Kafka container already occupied host port 9092. It was not changed;
the local ignored `.env` uses port 19092 for this validation. The checked-in
`.env.example` retains the standard 9092 default.

## Exact Image Tags And Registry Evidence

Compose pins patch tags, not digests. `docker buildx imagetools inspect` confirmed
native `linux/amd64` and `linux/arm64` manifests for every selected tag.

| Image tag | Manifest-list digest observed 2026-09-08 |
|---|---|
| `networktocode/nautobot:2.4.41-py3.12` | `sha256:f98f84ecd07e97d2f84de92e11f8aa48edd631b209590eb43eb65822ccf0975f` |
| `postgres:16.15-bookworm` | `sha256:bb3e1a57e5407e0a5280b4211980a5e537f4abd234a87014ac979849a78dd825` |
| `redis:7.2.16-bookworm` | `sha256:74566c6910d13ae61e7ce73ebd3127438a1fe805b309b097c323142719ec8a5b` |
| `apache/kafka:4.1.2` | `sha256:5cc2a2fd93fa2687b44015eee04fb2c3edd9e526bd64bf8bec5ff1e268772e0e` |
| `temporalio/server:1.31.0` | `sha256:b021b3b58c3f169634cdbb0451fcc0e69e8190b40454323362c7c52bbd4ff7b9` |
| `temporalio/admin-tools:1.31.0` | `sha256:3e68adcd54195a7c1222e99f2dbc32a4fdbf44ad69e3bb48e21e85c4bf417c2e` |
| `temporalio/ui:2.49.1` | `sha256:a066bdf5c4de689cabaf80cc357871f1db5e6d750a6bcfc42e877b913e31ef24` |

Digests are evidence only and may change if publishers rebuild tags. Compose uses
the exact patch tags above. `uv.lock` records exact Python distributions.

## Executed Checks

| Command / check | Result |
|---|---|
| `docker compose config --quiet` | Passed |
| `uv lock --check` and `uv sync --locked` | Passed; 26 packages resolved, Python 3.12.13 installed |
| `uv run python -m compileall -q src tests` | Passed |
| `uv run python -c "import network_automation"` | Passed |
| `uv run pytest` | Passed, default unit-only collection, 24 tests in 0.39s |
| `docker compose pull` | Passed; all seven exact image tags pulled natively on ARM64 |
| Initial fresh `docker compose up -d --wait --wait-timeout 600` | Failed in 9.8s as expected from two real defects; no error was hidden |
| Corrected `docker compose up -d --wait --wait-timeout 600` | Passed on retained initialized state in 9.5s |
| `docker compose --profile init up --no-deps --force-recreate --exit-code-from temporal-namespace temporal-namespace` | Passed; `SERVING`, initializer exit 0 |
| `uv run network-lab-check` | Passed all 11 named Compose services/initializers and four application boundaries |
| `uv run pytest tests/integration/test_services.py` | Passed, 5 real integration tests in 11.61s |
| `LAB_RUN_LIFECYCLE=1 uv run pytest tests/integration/test_lifecycle.py` | Passed, 1 test in 449.04s |

The first start exposed executable-bit failure on the PostgreSQL init script and
root ownership of a fresh Nautobot media volume. The implementation now checks in
the script executable and has the sole Nautobot initializer fix media ownership
before running migrations as the `nautobot` user. The existing non-destructive
PostgreSQL volume was repaired by executing the corrected first-boot script; it
was not deleted. Temporal and Nautobot then initialized successfully.

The service suite proves authenticated Nautobot API access, Nautobot worker/Beat
container health, Kafka host and internal-listener message round-trips,
Temporal RPC SERVING and `default` namespace description, and Temporal UI HTTP.
The aggregate checker independently requires all long-running health states and
all three one-shot exit codes. Kafka emitted transient IPv6 localhost connection
warnings before using the working IPv4 listener; the round-trip still passed.

The isolated lifecycle suite generated a `network-lab-test-*` project and four
distinct unused loopback ports while the normal lab remained running. It proved
fresh seed state, two consecutive starts, Nautobot tag/Kafka event/Temporal
namespace persistence across `down` and recreation, occupied-port diagnostics,
visible namespace-initializer failure without blocking Temporal UI, named Redis
failure and recovery, and destructive reset of only the disposable project. After
reset, the default namespace existed and all test-owned fixtures were absent.

Temporal's Compose health check now calls the server's HTTP API namespace-list
endpoint on port 7243 rather than treating an open gRPC TCP socket as readiness.
The host checker separately requires gRPC health `SERVING` and the configured
namespace. Unit tests cover boundary failures, shared per-probe deadlines,
redaction, and the 120-second aggregate deadline.

## Resource Snapshot

One `docker stats --no-stream` sample on the macOS Docker Desktop VM showed about
2.37 GiB total container memory: Nautobot worker 1.026 GiB, Kafka 543.9 MiB,
Nautobot web 449.6 MiB, Beat 212 MiB, PostgreSQL 99.18 MiB, Temporal 68.44 MiB,
Temporal UI 18.18 MiB, and Redis 9.44 MiB. Instantaneous CPU was bursty during
concurrent validation, so this is evidence from one sample, not a capacity bound.

## Remaining Checks

- Ubuntu 24.04 LTS x86-64 clean-checkout acceptance, including the reference-host
  cold-start timing and Docker-stopped unit-only proof: not executable on this host.
- `netlab create` with the unverified networklab 26.8, containerlab 0.79.0, and
  SR Linux 26.7.2-519 candidate tuple: not executable on this macOS host and does
  not affect supporting-service health.

Feature 001 is therefore implemented and validated for supporting-service use on
this macOS ARM64 host, but it is not accepted against the required Linux reference
platform. T012, T017, T019, T020, and final T021 remain open for that evidence.
