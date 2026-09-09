# Developer Interface Contract

Implemented Feature 001 command interfaces are listed below. No new REST API,
Kafka event contract, or Temporal workflow API is introduced.

| Interface | Contract |
|---|---|
| `uv sync --locked` | Reproduce locked package/dev dependencies; fail on incompatible lock/project |
| `docker compose config --quiet` | Validate resolved Compose; do not print secret-bearing config |
| `docker compose pull` | Fetch pinned supporting images |
| `docker compose up -d --wait --wait-timeout 600` | Start runtime services plus required DB/schema/Nautobot initializers; fail if unhealthy or dependency initialization unsuccessful |
| `docker compose --profile init up --no-deps --force-recreate --exit-code-from temporal-namespace temporal-namespace` | Recreate and run the explicit repeatable namespace one-shot after Temporal is healthy; propagate and leave its visible exit status |
| `uv run network-lab-check` | Read-only readiness except auth session effects; named pass/fail per required component; exit 0 only when all pass; deadline <=120 seconds; redacted errors |
| `uv run pytest tests/unit` | No external calls; mocks replace HTTP/RPC/Kafka/Compose execution |
| `uv run pytest tests/integration/test_services.py` | Explicit real infrastructure smoke checks; unavailable dependencies fail rather than skip |
| `LAB_RUN_LIFECYCLE=1 uv run pytest tests/integration/test_lifecycle.py` | Explicit opt-in to create/manage/delete only a dedicated disposable project; fail if name/ports overlap ordinary lab |
| `docker compose ps --all` | Display long-running services and completed/failed one-shots |
| `docker compose logs --tail=100 <service>` | Service/initialization diagnostics; application code must not log credentials |
| `docker compose --profile init down` | Stop/remove this project's containers, including the namespace initializer, and network; retain named volumes |
| `docker compose --profile init down --volumes` | Explicitly destructive reset of this project; never normal startup/recovery default |

Default pytest discovery selects `tests/unit` only. Explicit lifecycle selection
without `LAB_RUN_LIFECYCLE=1` must fail with opt-in instructions before side effects.
Lifecycle tests use `-p network-lab-test-<unique-id>`, allocate nonconflicting loopback
ports through documented Compose port overrides, and do not stop the normal lab.
`LAB_KAFKA_HOST_PORT` must set both the published host port and external advertised
port; the Python bootstrap default is derived from it. Test overrides of bootstrap
must match that isolated endpoint. Verify returned broker metadata before creating
fixtures, including when the ordinary lab remains running. Internal Kafka stays
`kafka:29092` on each project's private network.
All subprocesses use argument arrays and bounded timeouts, no shell interpolation.

Default endpoints: Nautobot `http://localhost:8000`, Temporal gRPC
`localhost:7233`, Temporal UI `http://localhost:8080`, Kafka `localhost:9092`.
Internal Kafka metadata advertises `kafka:29092`. No public PostgreSQL, Redis,
controller, Celery, or scheduler port. There is no authentication on Kafka/Temporal
in this local lab; Nautobot has a documented local admin. Never expose to untrusted
networks. Remote Linux users may explicitly SSH-tunnel the loopback endpoints.
