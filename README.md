# Network Automation Lab

A production-shaped local foundation for developing a reusable network automation
framework. Feature 001 supplies supporting services and host-side development
checks. Feature 002 reads Nautobot intent and produces deterministic Nokia SR Linux
configuration artifacts. Feature 003 accepts Kafka render requests and uses Temporal
to durably coordinate that same artifact path. Feature 004 adds an explicit deployment
request that applies the digest-bound artifact to a test-owned SR Linux target over gNMI
and independently validates operational state. Nautobot owns network intent, Kafka
transports events, and Temporal owns durable workflow execution. Feature 006 adds an
optional read-only operator UI over those accepted sources; it does not render, deploy,
retry, cancel, publish, or mutate automation state.

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
| Automation worker | Compose network only; profile `automation` | Temporal history and generated host artifacts |
| Event consumer | Compose network only; profile `automation` | Kafka consumer offsets |
| Control-plane read API | `http://localhost:8001`; profile `ui` | None; artifacts mounted read-only |
| Operator UI | `http://localhost:3000`; profile `ui` | None |

Redis is not durable automation state. Temporal owns workflow durability.

## Prerequisites

Reference acceptance target: Ubuntu 24.04 LTS x86-64, Git, `uv`, Docker Engine,
and Docker Compose v2 supporting health dependencies and `up --wait`. Allocate
approximately 8 vCPU, 16 GiB RAM, and 40 GiB free disk for supporting services.
Docker access is equivalent to privileged host access.

Real-device acceptance additionally requires netlab 26.8.0, containerlab 0.79.0,
`jq`, SSSE3, and `ghcr.io/nokia/srlinux:26.7.2-519`. The validated canonical host reports
netlab `26.08`, which is the release's equivalent display form.

Reference acceptance passed on Ubuntu 24.04.4 LTS x86-64. The supporting stack
was also exercised on macOS ARM64 using Docker Desktop. See `docs/validation.md`.
Network-device prerequisites are separate in `docs/network-lab.md`.

The default loopback ports 8000, 8080, 9092, and 7233 must be free. Ports 8001 and
3000 are additionally required when the `ui` profile is enabled. Override all
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

For access from a development Mac, keep all application ports on VM loopback and
use SSH forwarding:

```sh
ssh \
  -L 8000:localhost:8000 \
  -L 8080:localhost:8080 \
  -L 7233:localhost:7233 \
  -L 9092:localhost:9092 \
  root@24.199.95.39
```

This provides Nautobot at `http://localhost:8000`, Temporal UI at
`http://localhost:8080`, Temporal gRPC at `localhost:7233`, and Kafka at
`localhost:9092` on the Mac without publishing those VM services publicly.

## Develop And Test

```sh
uv sync --locked
uv run python -c "import network_automation"
uv run pytest
uv run pytest tests/integration/test_services.py
uv run pytest tests/integration/test_nautobot_render.py
uv run pytest tests/integration/test_srlinux_deployment.py
```

Default pytest discovery runs unit tests only and requires no Docker services.
Integration tests are explicit and fail when infrastructure is unavailable.

## Observe The Control Plane

The operator console is absent from default startup. After the base services are running,
build the shared automation image once and the UI image, then enable only the optional
profile:

```sh
docker compose --profile automation build automation-worker
docker compose --profile ui build automation-ui
docker compose --profile ui up -d automation-ui-api automation-ui
docker compose --profile ui ps
curl --fail --silent http://127.0.0.1:8001/healthz
```

`automation-ui-api` reuses `network-automation-lab:0.1.0`; Compose does not own a second
Python build. `/healthz` proves only that the API process can answer, so it stays healthy
while an observation source is degraded. Open `http://127.0.0.1:3000`; nginx serves the
static UI and proxies browser `/api` requests to the API on the Compose network. Both host
ports bind only to loopback, no Docker socket is mounted, and the UI adds no database,
cache, queue, event consumer, or durable state.

For a remote lab host, forward both loopback listeners from the workstation:

```sh
ssh -L 3000:localhost:3000 -L 8001:localhost:8001 root@<lab-host>
```

The browser polls only read models: overview every 15 seconds, devices/topology and
device base detail every 30 seconds, workflow/deployment lists every 10 seconds, and a
running workflow detail every 4 seconds until terminal. Opening device detail may issue
one explicitly requested live read with a 15-second budget; automatic refreshes never
repeat that device read. Workflow lists default to 25 and cap at 50, history hydration
uses concurrency four, and overview hydrates at most eight recent executions.

Temporal's three-day retention can leave older workflows, event/correlation fields,
artifacts, validation results, and failed outcomes unavailable. Kafka poison records and
transport coordinates are intentionally not reconstructed. Missing Nautobot cable data
produces nodes without invented physical links. These are reported as source gaps, not
zero values or synthetic status.

Optional live device detail requires the existing device-management network and
runtime-only `LAB_DEVICE_USERNAME` and `LAB_DEVICE_PASSWORD`; follow
`docs/network-lab.md`. Stop the optional surface without touching shared services or
volumes:

```sh
docker compose --profile ui stop automation-ui automation-ui-api
```

The lifecycle suite automatically creates and destroys only a uniquely named
Compose project on unused loopback ports:

```sh
LAB_RUN_LIFECYCLE=1 uv run pytest tests/integration/test_lifecycle.py
```

This opt-in test removes that disposable project's volumes. It refuses the normal
`network-lab` project name. Advanced callers may provide a `network-lab-test-*`
project and endpoint overrides; the test keeps the endpoints synchronized with
their host-port overrides.

## Render Nautobot Intent

Render one exact Nautobot Device name to the default ignored artifact directory:

```sh
uv run network-render DEVICE
```

Use `--output-dir DIRECTORY` to select another output directory. Success atomically
writes `<DIRECTORY>/<DEVICE>.cfg`, prints that path, and returns zero. Retrieval,
validation, unsupported platform, rendering, or filesystem failure returns nonzero
without replacing a prior complete artifact or printing credentials.

The adapter reads the Device, follows its Platform, Role, optional Location, and
assigned IPAddress relations, and paginates its Interfaces. Platform dispatch uses
only `network_driver=nokia_srl`; display labels are diagnostic. Exactly one enabled,
non-management `virtual` `/32` becomes SR Linux `system0`, while addressed physical
interfaces retain their names. BGP input is currently limited to
`local_config_context_data.network_automation.bgp`.

Generated configuration contains hostname, loopback and routed interface state and
IPv4 addressing, default network-instance attachments, and BGP ASN/router-ID/peers.
It contains no credentials or operational data. Rendering never contacts a network
device, Kafka, or Temporal. `leaf01` under `tests/fixtures/` is offline golden data,
not a required Nautobot object.

## Event-Driven Rendering

After the default stack and Temporal namespace initializer are healthy, build and start
the two application processes:

```sh
docker compose --profile automation build automation-worker event-consumer
docker compose --profile automation up -d --wait automation-worker event-consumer
uv run network-render-request DEVICE
```

The request command waits for Kafka delivery, then prints its event, correlation, and
deterministic workflow IDs. The consumer validates only `network.render.requested`
version-1 events and starts `render-device-config:<event_id>`. For a running ID, Temporal's
conflict policy uses the existing execution; for a retained closed ID, its separate reuse
policy rejects replacement. Kafka offsets commit synchronously only after Temporal accepts
or recognizes the workflow. Start or commit uncertainty seeks the exact offset for retry.

The workflow passes only event ID, correlation ID, and device name to one render activity.
That activity calls the complete Feature 002 path. A second activity publishes either a
strict `network.render.completed` or `network.render.failed` event. Render attempts are
limited to three and result publication attempts to five, both with one-second exponential
backoff capped at ten seconds. Result delivery is at least once; duplicate physical records
for one outcome retain the same event ID and payload.

Malformed messages are logged with safe topic, partition, offset, parseable event ID, and
error category context, then committed so the partition can continue. Full raw payloads and
secrets are not logged by default. Inspect process state with:

```sh
docker compose --profile automation ps
docker compose --profile automation logs --tail=100 automation-worker event-consumer
uv run pytest tests/integration/test_event_components.py
uv run pytest tests/integration/test_event_driven_render.py
```

Both services publish no ports and use ready/fresh-heartbeat file health checks. The worker
alone mounts `./artifacts`; the consumer has no Nautobot, rendering, filesystem, or result-
publication responsibility.

## Deploy And Validate SR Linux

Use the separate test-owned topology only on the canonical Linux device host. Follow
`specs/004-srlinux-deployment-validation/quickstart.md` for the complete lifecycle. Run
netlab from `lab/` so generated files and `netlab down --cleanup` remain isolated from the
repository's root `config/` directory. The optional Compose override attaches only the
existing worker to `network-lab-devices-mgmt`; start it with `--no-deps` so shared services
are not recreated.

Set `LAB_DEVICE_USERNAME` and `LAB_DEVICE_PASSWORD` only in the worker process environment.
The canonical lab obtains them directly from generated netlab inventory; `.env.example`
intentionally leaves both blank so render-only startup remains valid. Feature 004 supports
only local-lab `LAB_DEVICE_GNMI_TLS_MODE=insecure`, port 57401, and a ten-second RPC timeout.
Do not expose these credentials or endpoints outside the isolated lab.

```sh
cd lab
netlab up topology.yml -p clab --no-config
cd ..
export LAB_DEVICE_USERNAME="$(jq -r .ansible_user lab/group_vars/srlinux/topology.json)"
export LAB_DEVICE_PASSWORD="$(jq -r .ansible_ssh_pass lab/group_vars/srlinux/topology.json)"
docker compose -f compose.yaml -f compose.device-access.yaml --profile automation build automation-worker
docker compose -f compose.yaml -f compose.device-access.yaml --profile automation up -d --no-deps --wait automation-worker event-consumer
uv run network-render-request DEVICE --deploy
uv run pytest tests/integration/test_srlinux_deployment.py
```

The request uses `network.deployment.requested` and workflow ID
`deploy-device-config:<event_id>`. Preparation reads Nautobot once, follows the Device's
authoritative `primary_ip4`, invokes the sole Feature 002 renderer, and binds path, byte
count, and SHA-256 before deployment. The SR Linux boundary verifies native model and exact
hostname, rereads the digest, then sends the unchanged ASCII artifact as one CLI-origin
gNMI `update` transaction. Repeating the same keyed declarations is safe after an uncertain
response, but this update preserves stale unmentioned configuration and is not rollback.

Success requires separate native reads for hostname; loopback, physical interface, and
subinterface admin/oper state; exact IPv4 address status; local ASN; peer ASN; and established
BGP state. Prepare and deploy have three attempts, validation has twelve bounded attempts,
and publication has five. Validation retries never rerender or redeploy. Outcomes use
`network.deployment.completed` or `network.deployment.failed` with stable safe categories;
logs and events exclude credentials, raw configuration, raw responses, and stack traces.

Inspect failures with Temporal UI and safe worker/consumer logs. Confirm the target's
authoritative Nautobot primary IPv4, hostname bootstrap, worker network attachment, and
gNMI reachability before retrying. Remove the override worker before topology cleanup, run
`netlab down --cleanup` from `lab/`, then restore the base worker with `--no-deps`. Never
delete Compose volumes or shared topics as part of device cleanup.

## Operations

```sh
docker compose ps --all
docker compose logs --tail=100 <service>
docker compose --profile init down
docker compose up -d --wait --wait-timeout 600
docker compose --profile init up --no-deps --force-recreate --exit-code-from temporal-namespace temporal-namespace
uv run network-lab-check
```

Ordinary `--profile init down` also removes the profiled namespace container and
retains PostgreSQL, Kafka/KRaft, and Nautobot media. Startup re-runs supported
schema/migration initialization without rotating the Kafka cluster identity or
changing an existing Nautobot admin password/token.

If startup fails, inspect `postgres`, `temporal-schema`, `nautobot-init`, and the
named failing service. Correct ports, resources, or configuration and rerun; do
not delete volumes to hide an initialization defect. Changing first-boot database
passwords in `.env` does not alter credentials already stored in PostgreSQL.

Only when deletion of this lab's data is explicitly intended:

```sh
docker compose --profile init down --volumes
```

This irreversibly deletes this project's databases, Kafka events/metadata, and
Nautobot media. It is not a backup operation and does not affect Redis semantics,
which are disposable already. Never use a global Docker prune for lab recovery.

## Scope And Specifications

Feature 004 extends the same package, consumer, workflow class, worker, publisher, and
request CLI with three deployment events and three external activities. It adds one concrete
SR Linux boundary and a separately managed two-node topology. It adds no Nautobot event
producer, generic device hierarchy, new worker/service/API, rollback, DHCP/ZTP, discovery,
Kubernetes, cloud orchestration, or production security architecture.
Feature artifacts are under `specs/`; permanent agent instructions are in `AGENTS.md`.

Spec Kit 0.9.5 initialized OpenCode commands in `.opencode/commands/` and Codex
skills in `.agents/skills/`. The active branch is `004-srlinux-deployment-validation`.
