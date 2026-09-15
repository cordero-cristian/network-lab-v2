# Quickstart And Acceptance: Network Automation Control Plane UI

**Status**: IMPLEMENTATION AND CANONICAL ACCEPTANCE COMPLETE — 2026-09-15

Implementation and the separately approved reversible dependency-stop test are authorized. This
guide does not authorize persistent reset, intent/device/workflow mutation for UI fixtures, or
Feature 005 work.

## Prerequisites

- Canonical Ubuntu 24.04.4 x86-64 host with accepted Features 001-004 tooling.
- Existing `.env` with local-lab credentials; do not print or persist device credentials.
- Real existing Nautobot devices and retained Temporal Feature 003/004 histories for observation.
- Existing external device management network and credentials only when bounded live detail is
  included in acceptance.
- Developer workstation with SSH access to the canonical host.

## Static And Unit Validation

Future implementation must run:

```sh
uv lock --check
uv sync --locked
uv run python -m compileall -q src tests
uv run pytest
uv build
npm --prefix ui ci
npm --prefix ui run test -- --run
npm --prefix ui run build
docker compose config --quiet
docker compose --profile ui config --quiet
git diff --check
```

Expected: backend health/device/workflow/safety tests, frontend route/component/state tests,
existing default tests, locked builds, and Compose validation pass. Tests must prove no write route,
raw configuration, raw stack, credential, unrestricted path, arbitrary Temporal query, or direct
browser-upstream URL exists.

## Start Base, Automation, And UI Profiles

From a clean approved checkout on the canonical host:

```sh
docker compose up -d
docker compose --profile init run temporal-namespace
docker compose --profile automation --profile ui build automation-worker automation-ui
docker compose --profile automation --profile ui up -d
```

Expected:

- Default Features 001 services retain accepted health.
- Automation worker and event consumer retain accepted health.
- `automation-ui-api` becomes healthy from `/healthz` even when a read dependency later degrades.
- `automation-ui` serves static assets and proxies `/api` without rewriting API failures to HTML.
- UI services are absent when the `ui` profile is not selected.

If live device detail is explicitly included and the accepted topology is already running, attach
the API through the existing override without persisting credentials:

```sh
docker compose \
  -f compose.yaml \
  -f compose.device-access.yaml \
  --profile automation \
  --profile ui \
  up -d automation-worker automation-ui-api automation-ui
```

This command must not deploy, render, publish, or mutate a device.

## API Acceptance

Use only bounded GET requests:

```sh
curl --fail --silent http://127.0.0.1:8001/healthz
curl --fail --silent http://127.0.0.1:8001/api/health
curl --fail --silent http://127.0.0.1:8001/api/overview
curl --fail --silent http://127.0.0.1:8001/api/devices
curl --fail --silent http://127.0.0.1:8001/api/workflows
curl --fail --silent http://127.0.0.1:8001/api/deployments
curl --fail --silent http://127.0.0.1:8001/api/topology
```

Then select existing names/IDs from list responses and request one device and workflow detail. Add
`live=true` only once when authorized device access is present. Expected mappings are defined in
`contracts/source-map.md`; raw payloads are forbidden by `contracts/read-api.md`.

Run the future real read-only integration suite:

```sh
uv run pytest tests/integration/test_control_plane_api.py
```

The suite observes existing data only. If no retained known failed deployment exists, record that
the failed-detail canonical case is unavailable; do not manufacture one.

## SSH Forwarding And Browser Acceptance

From the developer workstation, substitute the approved host at invocation time:

```sh
ssh \
  -L 3000:localhost:3000 \
  -L 8001:localhost:8001 \
  root@<canonical-host>
```

Open `http://localhost:3000`. Verify:

1. Overview shows real component health, devices, workflows, deployments, topology, and activity.
2. Real Nautobot devices appear and drill down to source-labeled intent and retained outcomes.
3. Real retained Feature 003/004 workflows show correct business outcome despite Temporal execution
   status.
4. Exact durable activity boundaries appear; unsupported illustrative sub-stages do not.
5. Topology distinguishes physical endpoint links from logical BGP intent and does not infer links
   from subnet overlap.
6. Desktop and 375-pixel layouts remain readable with no page-level horizontal overflow.
7. Loading, empty, stale, partial, unavailable, unknown-stage, and safe error states are polished.
8. No deploy, render, retry, rerun, remediate, edit, cancel, publish, configuration preview, or ZTP
   control exists.
9. Browser network responses contain no credentials, raw configurations, raw Temporal failures,
   raw upstream payloads, authorization values, or unrestricted host paths.

Measure and record the user-facing success thresholds rather than judging them informally:

- API `/healthz` response completes in under 1 second and a healthy overview becomes useful in
  under 5 seconds;
- time from initial navigation until overall state and any unhealthy subsystem can be identified
  is at most 10 seconds;
- overview-to-device intent/latest outcome/available live state requires no more than two link
  selections;
- on an already retained failed execution, time from opening detail until failed stage and safe
  category can be identified is at most 15 seconds.

Execute the full screen/state/viewport/keyboard matrix in `contracts/frontend.md`, using mocked
frontend responses for states not naturally present. Canonical data remains real; mocks are only
for deterministic visual-state checks and never populate the running API.

## Partial Failure Acceptance

This is the sole planned exception to the no-mutation acceptance rule: with explicit test approval,
stop only a dependency whose shutdown is reversible, explicitly safe, and preserves all data and
automation state. Do not stop PostgreSQL, reset volumes, or alter Nautobot/device/workflow data. One
directional case is temporarily stopping Nautobot after the UI is loaded:

```sh
docker compose stop nautobot
```

Expected: health and device sections identify Nautobot as unavailable; Temporal workflow and
deployment history remains usable; the UI does not blank or crash. Restore it:

```sh
docker compose start nautobot
```

Repeat with another separately approved read dependency only if safe. Record actual recovery time
and never claim an unexecuted failure case.

## Exposure And Leak Checks

Verify published listeners are loopback only using host tooling and inspect browser/API/container
logs with redacted searches. At minimum assert:

- no API/UI listener on `0.0.0.0` or a public host address;
- no credential values from `.env` occur in responses, built assets, URLs, or logs;
- no `.cfg` content or absolute artifact path occurs in responses;
- no Temporal stack/failure payload or authorization header occurs in responses/logs;
- unsupported HTTP mutation methods return 405 and have no side effects.

Do not print the secret values as part of the check or evidence.

## Existing Regression Evidence

Run the accepted commands applicable to the canonical environment:

```sh
uv run pytest
uv run pytest tests/integration/test_services.py
uv run pytest tests/integration/test_nautobot_render.py
uv run pytest tests/integration/test_event_components.py
uv run pytest tests/integration/test_event_driven_render.py
uv run pytest tests/integration/test_srlinux_deployment.py
uv build
```

Record actual commands, platform, versions, results, retained-data limitations, and safe teardown in
`docs/validation.md`. Do not run destructive lifecycle/reset commands without separate approval.

## Stop And Teardown

Stop only optional UI services without removing shared volumes:

```sh
docker compose --profile ui stop automation-ui automation-ui-api
```

Feature 006 teardown must not stop/reset accepted dependencies, remove artifacts/history, or alter
the deferred Feature 005 state.
