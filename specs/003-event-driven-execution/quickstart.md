# Quickstart And Acceptance Plan

**Implementation and reference acceptance approved on 2026-09-09.**

## Offline Validation

With Docker and all external services unavailable:

```sh
uv sync --locked
uv run pytest
uv run pytest tests/unit/test_event_models.py tests/unit/test_event_producer.py tests/unit/test_event_consumer.py
uv run pytest tests/unit/test_render_workflow.py tests/unit/test_render_activities.py tests/unit/test_render_request_cli.py
```

Expected: existing tests stay green; event models reject type/version/time/extra-field
errors; consumer mocks prove manual commit, duplicate, seek, poison continuation, and
no forbidden calls; supported Temporal time-skipping tests prove activity ordering,
bounded retries, safe failure, stable result identity, and publication retry without
rerendering. No fake workflow engine is used.

## Start Automation Processes

Start/validate Feature 001 infrastructure and its namespace first using the accepted
README procedure. Then:

```sh
docker compose --profile automation build automation-worker event-consumer
docker compose --profile automation up -d --wait automation-worker event-consumer
docker compose --profile automation ps
```

Expected: exactly the two profile services use one image, publish no ports, and become
healthy. Existing infrastructure remains on retained named volumes.

## Component Integration

```sh
uv run pytest tests/integration/test_event_components.py
uv run pytest tests/integration/test_nautobot_render.py
```

Expected: uniquely named temporary Kafka topics prove request/result transport and
are deleted by exact name; a real Temporal worker executes the workflow contract;
Feature 002's uniquely owned Nautobot fixture still renders and cleans successfully.

## Full Path

```sh
uv run pytest tests/integration/test_event_driven_render.py
```

Expected: test-owned Nautobot intent and unique request/correlation IDs traverse
Kafka -> consumer -> Temporal -> Feature 002 -> atomic artifact -> Kafka completion.
Duplicate request delivery resolves to one workflow ID. A test-owned invalid intent
produces a safe failure result. Every recorded Nautobot ID and generated artifact is
removed; shared Kafka topic records remain until normal retention.

## Durability And Absence Checks

Safely stop only the stateless Feature 003 worker, publish a unique request, verify its
workflow remains pending, restart the worker, and observe completion under the same
workflow ID. Explicitly selecting integration while Kafka, Temporal, Nautobot, worker,
or consumer is absent must fail, not skip.

A real shared-service outage is not induced. Record this limitation and the supported
Temporal test-environment evidence for transient render/publication retries.

## Regression And Scope

```sh
uv run network-lab-check
uv run pytest tests/integration/test_services.py
uv run pytest tests/integration/test_nautobot_render.py
uv build
docker compose config --quiet
```

Review source/imports, Compose services, topics, image contents, logs, and artifacts.
There must be one package, one worker, one consumer, one workflow, two activities,
three event types/topics, and no device access, deployment, ZTP, generic framework,
extra infrastructure, or future-feature scaffold.
