# Quickstart And Acceptance Plan

**Status**: Validated on canonical Ubuntu x86-64 on 2026-09-11.

## Host Prerequisites

Use the canonical Ubuntu 24.04.4 x86-64 host with Docker, netlab 26.8.0, containerlab
0.79.0, `uv`, `jq`, and access to `ghcr.io/nokia/srlinux:26.7.2-519`. Configure `.env`
from `.env.example`; inject local-only gNMI credentials from generated inventory as shown
below rather than persisting them. Do not use this acceptance topology on shared devices.

## Offline Validation

```sh
uv sync --locked
uv run pytest
uv run pytest tests/unit/test_srlinux_device.py tests/unit/test_deployment_models.py
uv run pytest tests/unit/test_deployment_activities.py tests/unit/test_deployment_workflow.py tests/unit/test_deployment_events.py
uv build
docker compose config --quiet
docker compose -f compose.yaml -f compose.device-access.yaml config --quiet
```

Expected: strict contracts, target/artifact safety, response normalization, redaction,
classification, activity ordering, retry separation, stable results, and all existing tests
pass without real infrastructure. Explicit integration selection with dependencies absent
must fail rather than skip.

## Start Supporting Services And Topology

Start Feature 001 infrastructure and initialize Temporal with the accepted README commands.
Then create devices separately:

```sh
cd lab
netlab up topology.yml -p clab --no-config
netlab status
cd ..
export LAB_DEVICE_USERNAME="$(jq -r .ansible_user lab/group_vars/srlinux/topology.json)"
export LAB_DEVICE_PASSWORD="$(jq -r .ansible_ssh_pass lab/group_vars/srlinux/topology.json)"
docker compose -f compose.yaml -f compose.device-access.yaml --profile automation build automation-worker event-consumer
docker compose -f compose.yaml -f compose.device-access.yaml --profile automation up -d --no-deps --wait automation-worker event-consumer
```

Expected: exactly `f004-spine01` and `f004-leaf01`, one point-to-point link, fixed
test-owned management addresses, hostname-only identity bootstrap, and healthy existing
automation processes. Before deployment, no loopback, routed-interface addressing, BGP, or
policy intent is preloaded. Base Compose still validates and starts without the
override/topology. Running netlab from `lab/` ensures its generated files remain under
`lab/`; this prevents `netlab down --cleanup` from targeting the repository's checked-in
root `config/` directory.

## Pre-Mutation Device Probe

Use an independent pinned pyGNMI client from the canonical host and worker network to prove
both targets on port 57401, capabilities, native JSON-IETF response packing, exact leaf
types, exact address list keys through `/status`, and valid-absent behavior. Record image
digest and platform. Do not proceed if the device identity, target addresses, or pinned
behavior differs from the contracts.

## Real End-To-End Acceptance

```sh
uv run pytest tests/integration/test_nautobot_render.py
uv run pytest tests/integration/test_srlinux_deployment.py
```

The test creates only exact test-owned Nautobot records for both fixed nodes, including
primary IPv4 management relationships; publishes unique deployment requests; and proves:

- Renderer output contains required peer groups/address families and remains deterministic.
- Kafka -> Temporal -> Nautobot -> render -> digest -> gNMI Set -> native Get -> result.
- Both nodes reach intended hostname, loopback, physical/subinterface up, exact address,
  local/peer ASN, and BGP established state.
- Independent gNMI reads observe the same state after the successful event.
- Duplicate request and simulated lost Set response produce one logical deployment.
- Validation convergence retry does not redeploy, and deployment retry does not rerender.
- Unreachable, bad-credential, isolated rejected-config, artifact mismatch, and final state
  mismatch produce safe categories without raw configuration or secrets.

Exact fixture records/artifacts are removed. Shared Kafka records and Temporal history are
retained as durable evidence. No shared topic, namespace, volume, or unrelated lab is reset.

## Regression

```sh
uv run network-lab-check
uv run pytest tests/integration/test_services.py
uv run pytest tests/integration/test_nautobot_render.py
uv run pytest tests/integration/test_event_components.py
uv run pytest tests/integration/test_event_driven_render.py
```

Record actual commands, platform limitations, counts, health, and cleanup in
`docs/validation.md`. Review for one package/worker/consumer/workflow, one SR Linux module,
Feature 002 sole rendering, and absence of excluded services/frameworks/features.

## Safe Teardown

Remove only the worker endpoint attached to the topology network before netlab cleanup:

```sh
docker compose -f compose.yaml -f compose.device-access.yaml --profile automation rm -sf automation-worker
cd lab
netlab down --cleanup
cd ..
unset LAB_DEVICE_USERNAME LAB_DEVICE_PASSWORD
docker compose --profile automation up -d --no-deps --wait automation-worker event-consumer
```

Verify only test-owned device containers and `network-lab-devices-mgmt` were removed.
Supporting named volumes and services remain intact.
