# Data Model: Lab Foundation

No network-intent model, event schema, workflow state model, device inventory
schema, or custom database migration is introduced. Upstream applications own
their own schemas. Nautobot remains the sole intended-network-state authority.

## Lab Settings (Pydantic v2 Boundary)

`LabSettings` is a small host-runtime configuration model, not a domain model.

| Field / Environment Name | Default / Validation |
|---|---|
| `nautobot_url` / `LAB_NAUTOBOT_URL` | `http://localhost:8000`; HTTP(S) URL |
| `temporal_address` / `LAB_TEMPORAL_ADDRESS` | `localhost:7233`; nonempty host and valid port, no URL scheme |
| `temporal_namespace` / `LAB_TEMPORAL_NAMESPACE` | `default`; nonempty |
| `temporal_ui_url` / `LAB_TEMPORAL_UI_URL` | `http://localhost:8080`; HTTP(S) URL |
| `kafka_host_port` / `LAB_KAFKA_HOST_PORT` | 9092; integer 1-65535; also drives Compose publication and Kafka external advertisement |
| `kafka_bootstrap_servers` / `LAB_KAFKA_BOOTSTRAP_SERVERS` | If absent, derive `localhost:<kafka_host_port>`; otherwise validate comma-separated host:port entries |
| `nautobot_username` / `NAUTOBOT_SUPERUSER_NAME` | `admin`; nonempty; canonical bootstrap/check value |
| `nautobot_password` / `NAUTOBOT_SUPERUSER_PASSWORD` | `.env.example` local-only canonical value; required secret, redacted |
| `nautobot_token` / `NAUTOBOT_SUPERUSER_API_TOKEN` | local-only canonical API token; required secret, redacted |
| `probe_timeout_seconds` / `LAB_PROBE_TIMEOUT_SECONDS` | 10; integer 1-10; global 120-second deadline also enforced |
| `compose_project` / `LAB_COMPOSE_PROJECT` | `network-lab`; validate Compose project-name syntax before subprocess use |

Read explicit environment overrides over `.env` over non-secret defaults.
Unknown `.env` keys used by Compose are permitted; invalid defined fields fail
before network calls. Never pass shell-interpolated credentials/arguments.
Nautobot URL uses `LAB_NAUTOBOT_URL`; credentials used by Compose bootstrap and
Python derive from the same canonical `NAUTOBOT_SUPERUSER_*` values.
Only construct models at explicit entry points, not import time.

## Persisted State

PostgreSQL owns Nautobot data and Temporal persistence/visibility; Kafka owns
event logs and KRaft metadata; Nautobot media is a shared volume. Redis cache and
Celery broker/result state is disposable and is not durable automation state.
No ORM, repository pattern, or application storage API
is added. Schema version transitions use upstream tools only.

## Lifecycle And Fixtures

Absent volumes -> DB bootstrap -> application schema/admin initialization ->
ready services -> stopped with retained volumes -> ready services on recreation.
Failed initialization -> visible blocked dependencies -> corrected config and
explicit rerun. Retained state never transitions to empty except explicit reset.

Integration fixtures have a unique test-run prefix: disposable Kafka topics and
messages, Nautobot metadata records, Temporal namespaces. Lifecycle fixture data
is not intended device state. Tests clean up only owned resources where upstream
permits; retained namespace records may expire with the disposable project.
