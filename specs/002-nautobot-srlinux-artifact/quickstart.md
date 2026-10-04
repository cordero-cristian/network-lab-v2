# Quickstart And Acceptance Plan

This is the approved Feature 002 implementation validation procedure.

## Prerequisites

- Feature 001 Python environment synchronized with `uv sync --locked`.
- For integration only, the canonical Feature 001 Nautobot 2.4.41 instance healthy
  and `.env` providing its URL/token.
- No SR Linux node, Kafka application, or Temporal application is required.

## Offline Validation

With Docker/Nautobot stopped:

```sh
uv sync --locked
uv run python -c "from network_automation.intent.models import DeviceIntent"
uv run pytest tests/unit/test_intent_models.py tests/unit/test_nautobot_intent.py tests/unit/test_srlinux_render.py
uv run pytest
```

Expected: model/conversion/render/artifact tests pass, the reviewed
`tests/fixtures/expected/leaf01.cfg` matches exactly, 100 renders are byte-identical,
and default pytest remains unit-only.

## Real Nautobot Acceptance

With canonical Nautobot healthy:

```sh
uv run pytest tests/integration/test_nautobot_render.py
```

Expected: the test creates only uniquely suffixed test-owned API fixtures, exercises
Nautobot -> raw adapter data -> DeviceIntent -> SR Linux renderer -> temporary
artifact, validates dynamic hostname/path and repeated bytes, and removes only its
recorded fixture IDs. For an ordinary existing
Nautobot device, the user-facing form is `uv run network-render DEVICE`. Neither
path contacts a network device.

## Failure Acceptance

Run unit cases for malformed IPs/ASNs, duplicate interfaces/neighbors, missing or
ambiguous loopback, local-address neighbor collision, unsupported platform, template
failure, and unwritable output. Existing complete target bytes must remain unchanged.

Stop Nautobot and explicitly select the integration test. Expected: a bounded,
named connection failure and nonzero pytest status, never a skip or false success.

## Scope Review

Before acceptance, inspect dependencies, imports, source paths, and generated output.
There must be one Python package, one Jinja2 dependency, one SR Linux template, and
no device client, Kafka producer/consumer, Temporal worker/workflow/activity, custom
Nautobot App, ZTP, vendor framework, or empty future-feature module.
