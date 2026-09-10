# Validation Evidence

**Dates**: 2026-09-08 through 2026-09-10

## Local Implementation Environment

- Host: macOS 26.5.2 ARM64, Darwin 25.5.0
- Docker Desktop 4.81.0, Engine 29.6.1, Linux ARM64 VM
- Docker Compose v5.2.0
- `uv` 0.11.28; managed CPython 3.12.13
- Reference Ubuntu 24.04 LTS x86-64 acceptance: **not available on this host**

An unrelated Kafka container already occupied host port 9092. It was not changed;
the local ignored `.env` uses port 19092 for this validation. The checked-in
`.env.example` retains the standard 9092 default.

## Reference Linux Environment

- Host: Ubuntu 24.04.4 LTS, kernel 6.8.0-124-generic, x86-64
- CPU: 2 vCPU, Intel Xeon Platinum 8168 with SSSE3
- Memory: 15.62 GiB, no swap
- Disk before image installation: 46 GiB free of 48 GiB
- Docker Engine 29.1.3; Docker Compose 2.40.3
- `uv` 0.11.28; managed CPython 3.12.13
- networklab/netlab 26.08; containerlab 0.79.0

The VM has fewer than the proposed 8 vCPUs but met the 600-second clean-start
criterion after Linux timing fixes. Running two complete stacks concurrently did
not meet that bound; lifecycle acceptance therefore ran alone after the clean
acceptance stack was stopped without deleting its volumes.

## Exact Image Tags And Registry Evidence

Compose pins patch tags, not digests. `docker buildx imagetools inspect` confirmed
native `linux/amd64` and `linux/arm64` manifests for every selected tag.

| Image tag | Manifest-list digest observed and pulled as native amd64 on 2026-09-09 |
|---|---|
| `networktocode/nautobot:2.4.41-py3.12` | `sha256:f98f84ecd07e97d2f84de92e11f8aa48edd631b209590eb43eb65822ccf0975f` |
| `postgres:16.15-bookworm` | `sha256:bb3e1a57e5407e0a5280b4211980a5e537f4abd234a87014ac979849a78dd825` |
| `redis:7.2.16-bookworm` | `sha256:74566c6910d13ae61e7ce73ebd3127438a1fe805b309b097c323142719ec8a5b` |
| `apache/kafka:4.1.2` | `sha256:5cc2a2fd93fa2687b44015eee04fb2c3edd9e526bd64bf8bec5ff1e268772e0e` |
| `temporalio/server:1.31.0` | `sha256:b021b3b58c3f169634cdbb0451fcc0e69e8190b40454323362c7c52bbd4ff7b9` |
| `temporalio/admin-tools:1.31.0` | `sha256:3e68adcd54195a7c1222e99f2dbc32a4fdbf44ad69e3bb48e21e85c4bf417c2e` |
| `temporalio/ui:2.49.1` | `sha256:a066bdf5c4de689cabaf80cc357871f1db5e6d750a6bcfc42e877b913e31ef24` |
| `ghcr.io/nokia/srlinux:26.7.2-519` | `sha256:0096fe3ebcafabb7253492e2060425fe027a168e0e066766d1e85efbb0b48be8` |

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

The reference Linux steady-state snapshot used approximately 2.12 GiB container
memory: Kafka 939.8 MiB, Nautobot web 396.7 MiB, worker 350.9 MiB, Beat 210 MiB,
PostgreSQL 127.3 MiB, Temporal 85.95 MiB, UI 10.07 MiB, and Redis 3.19 MiB.
Kafka showed a transient 57% CPU sample while other services were mostly idle;
this is an observation, not a capacity benchmark.

## Reference Acceptance Commands

The following commands ran on Ubuntu from the normal checkout or the separately
cloned `/root/network-lab-v2-acceptance` checkout as indicated:

| Command / check | Linux result |
|---|---|
| `uv sync --locked` | Passed from clean checkout; 25 packages installed from the committed lock |
| `uv run pytest tests/unit` | Passed, 24 tests in 0.44s |
| `uv run pytest` | Passed, default unit-only collection, 24 tests in 0.44s |
| `docker compose config --quiet` | Passed with isolated project/endpoint overrides |
| `docker compose pull` | Passed; all exact tags native amd64 |
| `docker compose up -d --wait --wait-timeout 600` | Passed from fresh disposable volumes in 452.13s, excluding pulls |
| `docker compose --profile init up --no-deps --force-recreate --exit-code-from temporal-namespace temporal-namespace` | Passed; bounded retry handled transient CLI interruption, initializer exit 0 |
| `uv run network-lab-check` | Passed every service, initializer, authenticated HTTP, Kafka, Temporal RPC/namespace, and UI check |
| `uv run pytest tests/integration/test_services.py` | Passed, 5 tests in 30.20s |
| `LAB_RUN_LIFECYCLE=1 uv run pytest tests/integration/test_lifecycle.py` | Passed alone on the 2-vCPU host, 1 test in 1227.04s |
| `netlab create topology.yml -p clab` | Passed; generated one-node containerlab artifacts using SR Linux 26.7.2-519; no node launched |

For the Docker-stopped proof, `docker compose --profile init down` removed all
normal-project containers and retained its named volumes. `uv sync --locked`,
`uv run python -c "import network_automation"`, `uv run pytest tests/unit`, and
default `uv run pytest` passed without infrastructure. Explicit service integration
then failed 5/5 with missing containers/refused endpoints rather than skipping.
The normal lab was restored from retained volumes and passed aggregate health.

The clean-checkout run verified `.env` is ignored, `uv.lock` is tracked, image
references use exact patch tags, and only four application ports were published,
all on `127.0.0.1`. The disposable acceptance project and volumes were removed;
normal `network-lab` volumes were never deleted.

## Linux Fixes And Failure Evidence

The first Linux normal-project cold start reached configured health in 566.27s,
but its immediate Temporal namespace command timed out under startup load. The
initializer now retries at most six times with 10-second CLI deadlines and 5-second
delays, retaining visible permanent failure within 120 seconds.

A first clean disposable start exceeded 900 seconds because Nautobot's native
`health_check` took 12.96 seconds on 2 vCPUs while Compose allowed only 10 seconds.
Its Compose timeout and interval are now 30 seconds; the final fresh run passed in
452.13 seconds. An initial concurrent lifecycle run timed out because two full
stacks exceeded the host CPU allocation. The isolated rerun reached final reset
but exposed a live Kafka producer recreating its topic after reset. The test now
creates its topic explicitly, disables producer auto-creation, and releases the
producer before reset; the full rerun passed.

netlab generation also exposed unignored provider outputs and an implicit SR Linux
default tag. The topology now pins `26.7.2-519`, and observed generated artifacts
are ignored. No architectural change or future-feature behavior was required.

## Acceptance Status

All Feature 001 tasks T001 through T021 are complete. Reference Ubuntu x86-64
acceptance passed on 2026-09-09. Remaining limitations: the VM has only 2 vCPUs,
so parallel full-stack cold starts are outside the validated resource envelope;
the topology check proves generation only, not SR Linux node operation; and the
local credentials and plaintext endpoints remain suitable only for this SSH-tunneled
lab.

## Feature 002 Validation Evidence

**Date**: 2026-09-09

Feature 002 adds one host-side Nautobot REST adapter, five frozen Pydantic intent
models, one presentation-only SR Linux Jinja2 template, deterministic rendering,
atomic artifact replacement, and the `network-render` CLI. It adds no service,
worker, device client, Kafka/Temporal application, ZTP behavior, or persistent state.

### Offline Checks

The local Docker stack was stopped. No SSH tunnel or Nautobot endpoint was available
for these commands.

| Command / check | Result |
|---|---|
| `uv sync --locked` | Passed; 28 packages resolved and 27 checked |
| `uv run python -c "from network_automation.intent.models import DeviceIntent; from network_automation.rendering import render_srlinux"` | Passed |
| `uv run pytest` | Passed, default unit-only collection, 93 tests in 0.65s |
| `uv run pytest tests/unit/test_intent_models.py tests/unit/test_nautobot_intent.py tests/unit/test_srlinux_render.py tests/unit/test_render_cli.py` | Passed, 69 Feature 002 tests in 0.43s |
| `uv run python -m compileall -q src tests` | Passed |
| `uv build` | Passed; sdist and wheel built, and the wheel contains `network_automation/templates/srlinux/config.j2` plus the `network-render` entry point |
| `docker compose config --quiet` | Passed |
| `uv run pytest tests/integration/test_nautobot_render.py` without Nautobot | Failed as required with `httpx.ConnectError: [Errno 61] Connection refused`; 1 failed, no skip |

The offline suite covers exact golden bytes, 100 byte-identical renders, natural
interface and numeric neighbor ordering, one final newline, package-resource template
lookup independent of the current directory, strict missing-template data, platform
dispatch independent of display, malformed external data, numeric address coercion,
invalid ASNs, loopback ambiguity, duplicate/colliding intent, credential redaction,
and absent/prior artifact preservation across render, staging, directory, and
replacement failures.

### Canonical Nautobot Integration

The macOS test process reached canonical Nautobot 2.4.41 over a temporary SSH local
forward to the VM loopback port. The forward was removed immediately after testing.

| Command / check | Result |
|---|---|
| `LAB_NAUTOBOT_URL=http://127.0.0.1:18000 uv run pytest tests/integration/test_nautobot_render.py -vv` | Passed, 1 test in 14.16s |
| `/root/.local/bin/uv run --directory /root/network-lab-v2 network-lab-check` | Passed all 11 Compose service/initializer states and four application boundaries |
| `/root/.local/bin/uv run --directory /root/network-lab-v2 pytest tests/integration/test_services.py` | Passed, 5 tests in 29.86s |

The Feature 002 integration generated one suffix and API-created its own Status,
Namespace, Manufacturer, Platform with `network_driver=nokia_srl`, DeviceType, Role,
LocationType, Location, two Prefixes, Device `feature002-leaf-<suffix>` with matching
serial marker, three Interfaces, three IPAddresses, and three assignments. It read
only immutable ContentType metadata plus its own created objects. Every created ID
was recorded, deleted in reverse dependency order in `finally`, and confirmed absent
with a detail GET. It did not reuse, modify, or delete an existing mutable object.

Two preliminary canonical runs failed safely while establishing exact Nautobot 2.4
behavior. The first returned HTTP 400 before any mutable object was created because
ContentType relations require `<app_label>.<model>` natural keys rather than UUIDs.
The second created the full fixture and then exposed Interface `type` as a
`{value, label}` choice object. Both runs executed ID-only cleanup and confirmed every
created object absent. The final adapter also follows Role and optional Location URLs
because Device relation summaries do not carry their display values.

The real integration exercised only Nautobot HTTP plus local model/render/filesystem
code. It made no network-device, Kafka, or Temporal call. The separate Feature 001
checks demonstrate that retained volumes and supporting services remained healthy.

### Clean-Checkout Acceptance

After explicit commit/push authorization, Ubuntu acceptance used the clean
`/root/network-lab-v2-acceptance` checkout at final implementation commit `0c53c1f`.
It reused canonical Nautobot over VM loopback without changing or resetting Feature
001 volumes.

| Command / check | Ubuntu result |
|---|---|
| `/root/.local/bin/uv sync --locked --directory /root/network-lab-v2-acceptance` | Passed; Jinja2 3.1.6 and MarkupSafe 3.0.3 installed from the committed lock |
| `/root/.local/bin/uv run --directory /root/network-lab-v2-acceptance pytest` | Passed, 93 tests in 3.13s |
| `/root/.local/bin/uv run --directory /root/network-lab-v2-acceptance pytest tests/unit/test_intent_models.py tests/unit/test_nautobot_intent.py tests/unit/test_srlinux_render.py tests/unit/test_render_cli.py` | Passed, 69 tests in 2.52s |
| `LAB_NAUTOBOT_URL=http://127.0.0.1:8000 /root/.local/bin/uv run --directory /root/network-lab-v2-acceptance pytest tests/integration/test_nautobot_render.py -vv` | Passed, 1 test in 10.43s; all created IDs confirmed absent |
| `/root/.local/bin/uv build --directory /root/network-lab-v2-acceptance` | Passed; sdist and wheel built |
| `git check-ignore -v artifacts/configs/probe.cfg` | Passed with root rule `.gitignore:12:/artifacts/` |
| `git status --short --branch` | Clean at `0c53c1f`, tracking the pushed Feature 002 branch |

Final review found no Feature 002 import or source change for device access, Kafka,
Temporal, ZTP, DHCP, Compose, Feature 001 health/settings/tests, or network-lab files.
The wheel contains the one Python package, one SR Linux template, and both existing
console entry points. Post-fix code review found no remaining concrete bug or scope
violation. All Feature 002 tasks T001 through T020 are complete, and reference
Ubuntu x86-64 acceptance passed on 2026-09-09.

## Feature 003 Validation Evidence

**Date**: 2026-09-09

Feature 003 adds three strict event models, one manual-commit Kafka consumer, one
deterministic Temporal workflow, two activities, one worker, one request CLI, and two
profile-gated Compose services sharing `network-automation-lab:0.1.0`. The lock resolved
`temporalio==1.32.0`; direct SDK introspection confirmed independent
`id_conflict_policy` and `id_reuse_policy` start arguments and the exact
`WorkflowIDConflictPolicy.USE_EXISTING` and `WorkflowIDReusePolicy.REJECT_DUPLICATE`
members.

### Local Offline And Component Checks

| Command / check | Result |
|---|---|
| `uv lock --check` | Passed; 28 packages resolved |
| Final `uv run pytest` | Passed, 150 default unit tests in 1.96s |
| Feature 003 focused unit/Temporal tests | Passed; final workflow suite includes a safe unknown/timeout-class fallback result and the consumer suite includes runtime health lifecycle |
| `uv run python -m compileall -q src tests` | Passed |
| `uv build` | Passed; sdist and wheel built |
| `docker compose config --quiet` | Passed |
| `docker compose --profile automation build automation-worker event-consumer` | Passed; shared ARM64 image ID `sha256:c3afdf356beb6a9a16d528e987b627032f3ab86a102c6b9af91f8672126df8b7` observed before the final standalone-model rebuild |
| `uv run pytest tests/integration/test_event_components.py -vv` | Passed, 2 real Kafka/Temporal component tests in 1.86s |
| `uv run pytest tests/integration/test_nautobot_render.py -vv` | Passed, existing Feature 002 real integration in 4.77s |
| `uv run pytest tests/integration/test_event_driven_render.py -vv` | Passed, strengthened full valid/duplicate/poison/permanent-failure/worker-restart/uncommitted-consumer-restart test in 80.82s |
| Full integration with `event-consumer` stopped | Failed immediately at the required-service preflight, 1 failed and no skip; service was restored healthy without touching persistent data |
| `uv run network-lab-check` after acceptance | Passed all 11 supporting container/initializer checks and four application boundaries |

The full path created only uniquely marked Nautobot resources and exact ignored artifact
paths, then removed and verified those owned resources in `finally`. It published a poison
record followed by valid duplicated input, observed one retained workflow identity and one
logical completion, compared event-driven artifact bytes with direct Feature 002 rendering,
and observed a safe `unsupported_platform` failure. It stopped and restarted only the two
stateless Feature 003 processes: accepted work completed after worker restart, and an
uncommitted request started after consumer restart under its deterministic workflow ID.
No Kafka, Temporal, Nautobot, volume, or persistent namespace was stopped or reset.

The first full-path attempt failed because a result consumer subscribed before Kafka had
auto-created the failure topic and retained the stale assignment. The test now uses bounded
metadata refresh with a unique earliest-offset group and correlation filtering; production
topic creation and process architecture were unchanged. A later first complete attempt
passed. Shared Kafka/Nautobot outages were deliberately not induced. Bounded transient
render and result-publication retries are instead proven with Temporal's supported
time-skipping environment and mocked external failures.

### Reference Ubuntu Acceptance

Reference acceptance used a synchronized, non-Git working copy at
`/root/network-lab-v2-feature003` because commit and push were not authorized. It reused
the canonical `network-lab` project, `.env`, named volumes, Kafka log, Temporal namespace,
and Nautobot database; no volume or persistent state was reset.

| Command / check | Ubuntu result |
|---|---|
| `/root/.local/bin/uv sync --locked --directory /root/network-lab-v2-feature003` | Passed; 28 packages resolved and 27 installed with CPython 3.12.13 |
| `/root/.local/bin/uv run --directory /root/network-lab-v2-feature003 pytest` | Passed, 150 unit/Temporal tests in 4.93s |
| Final synchronized-copy `uv run ... pytest` | Passed, 150 unit/Temporal tests in 2.93s; application-service preflight also passed |
| compileall and `/root/.local/bin/uv build --directory /root/network-lab-v2-feature003` | Passed; sdist and wheel built |
| `docker compose ... config --quiet` | Passed |
| First two-service image build | Failed visibly because Compose 2.40 without buildx concurrently exported two identical build declarations to `network-automation-lab:0.1.0` |
| Corrected profile build/start | Passed after assigning the sole build declaration to `automation-worker`; `event-consumer` reuses the exact image |
| `uv run ... pytest tests/integration/test_event_components.py -vv` | Passed, 2 real Kafka/Temporal tests in 3.15s |
| `uv run ... pytest tests/integration/test_nautobot_render.py -vv` | Passed, Feature 002 real Nautobot test in 18.23s |
| `uv run ... network-lab-check` | Passed all 11 supporting service/initializer states and four application boundaries |
| `uv run ... pytest tests/integration/test_services.py -vv` | Passed, 5 Feature 001 real-service tests in 34.34s |
| `uv run ... pytest tests/integration/test_event_driven_render.py -vv` | Passed full Feature 003 acceptance in 119.72s |
| Final profile `ps --all` | Both Feature 003 services and all supporting services healthy; all three initializers exited zero |
| Kafka topic listing | Exactly `network.render.requested`, `network.render.completed`, `network.render.failed`, and Kafka internal `__consumer_offsets` |
| Application image | `sha256:9015e447fc12b55d5d5795fccc5803b092e936281cd619835fbf441a22c7f27a`, native amd64 |

The corrected Compose project was run from the synchronized project directory under the
existing project name. Compose therefore recreated PostgreSQL, Temporal schema/server,
and Nautobot initialization containers while retaining their named volumes. This was an
acceptance orchestration deviation from the intended stateless-service-only start, not a
data reset: all supporting services recovered healthy, the namespace remained present,
the Feature 001 suite passed, and the Feature 002 integration passed. No outage was
deliberately induced for retry testing.

Canonical logs showed duplicate offsets for the same request event ID mapped to one
workflow ID, a poison record with topic/partition/offset/event ID/category and no payload
secret, a safe `unsupported_platform` failure, worker shutdown/recovery, consumer restart,
and correlated completion publication. The full test verified the poison offset was
committed, no poison workflow existed, the interrupted exact request record remained
uncommitted and was processed after restart, direct and event-driven artifact bytes were
identical, and all test-owned Nautobot objects/artifacts were removed.

### Feature 003 Acceptance Status

All Feature 003 tasks T001 through T038 are complete. Local macOS ARM64 and reference
Ubuntu 24.04.4 x86-64 acceptance passed on 2026-09-09/10. Remaining limitations are the
approved absence of a deliberately induced shared Kafka/Nautobot outage and the absence
of clean Git-checkout evidence until commit/push is separately authorized. No network
device, deployment, validation, DHCP/ZTP, Feature 004, or generic framework was added.
