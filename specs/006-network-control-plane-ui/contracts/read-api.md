# Read API Contract

Base path: `/api`. All feature operations use `GET`. JSON keys are snake_case. Times are UTC RFC
3339. Responses never contain credentials, raw configuration, raw Temporal payloads/failures,
authorization material, or unrestricted filesystem paths.

## Process Liveness

### `GET /healthz`

Returns `200 {"status":"ok"}` when the API event loop can serve requests. It performs no upstream
probe and is the Compose healthcheck target.

## Aggregate Health And Overview

### `GET /api/health`

Returns `SystemHealthSummary` with independent Nautobot, Kafka, Temporal, worker, consumer, and
device-validation capability states. Expected upstream failures still return HTTP 200 with
degraded/unavailable component states.

### `GET /api/overview`

Returns independently available sections:

```text
observed_at
health: SystemHealthSummary
devices: {availability, total}
workflows: {availability, active_count, recent[]}
deployments: {availability, recent_successes[], recent_failures[]}
topology: {availability, nodes[], links[]}
activity: {availability, items[]}
```

No field is synthesized from missing data. Recent sections use the same bounded Temporal projection
as list endpoints.

## Devices

### `GET /api/devices`

Query:

- `limit`: optional integer, default 50, range 1-100.

Returns `items: DeviceSummary[]`, `count`, `observed_at`, and source availability. Results are
sorted by normalized device name. No arbitrary Nautobot query is accepted.

### `GET /api/devices/{device_name}`

Query:

- `live`: optional boolean, default false.

Returns `DeviceDetail`. `live=true` permits exactly one bounded Feature 004 read/comparison. A live
timeout degrades only `live_state`; it does not fail inventory or retained history sections.
Device names use the existing `DeviceName` validation. Unknown names return safe 404.

## Topology

### `GET /api/topology`

Returns `TopologyGraph`. Physical and logical BGP links include `kind`; absent or ambiguous
relationships never become inferred links.

## Workflows

### `GET /api/workflows`

Query:

- `limit`: optional integer, default 25, range 1-50.
- `kind`: optional `render|deployment`.
- `status`: optional allowlisted display outcome.

Returns newest-first `WorkflowSummary[]`, count, observation time, and Temporal availability. The
filters apply only to the bounded admitted result window and are not passed through as arbitrary
Temporal visibility expressions.

### `GET /api/workflows/{workflow_id}`

Query:

- `run_id`: required UUID for UI-generated links; optional only for direct operator lookup of the
  current/latest execution.

Returns `WorkflowDetail`. Workflow ID must match one accepted prefix and UUID suffix. A supplied run
ID pins history to avoid latest-run races. Unknown activities appear as unknown stages. Raw history
is never returned.

## Deployments

### `GET /api/deployments`

Query:

- `limit`: optional integer, default 25, range 1-50.
- `status`: optional allowlisted deployment display status.

Returns the deployment-only projection of admitted Temporal workflows, newest first.

### `GET /api/deployments/{workflow_id}`

Query:

- `run_id`: same semantics as workflow detail.

Requires a `deploy-device-config:` workflow ID and returns `DeploymentDetail`, the deployment-
constrained workflow detail projection.

## Error Semantics

| Condition | HTTP | Body |
|---|---:|---|
| Invalid name, ID, run ID, limit, or filter | 422 | `ApiError(code="invalid_request")` |
| Admitted device/workflow not found | 404 | `ApiError(code="not_found")` |
| Independent upstream section fails | 200 | Section availability plus null/partial data |
| Entire direct detail lookup exceeds its deadline | 504 | `ApiError(code="upstream_timeout")` |
| Unexpected internal error | 500 | `ApiError(code="internal_error")` |

FastAPI validation details are replaced by bounded field/code summaries; raw input and exception
representations are not reflected.

## Cache And Browser Policy

- `/api/*`: `Cache-Control: no-store`.
- Static hashed assets: long immutable cache.
- `index.html`: no-cache/revalidate.
- Same-origin nginx proxy is the normal browser path; no permissive CORS policy is required.
- Only `GET`, `HEAD`, and `OPTIONS` are accepted by the UI server; write methods return 405.
