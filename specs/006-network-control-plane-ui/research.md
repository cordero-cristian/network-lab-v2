# Research: Network Automation Control Plane UI

## Existing Boundaries

### Decision: Add one read-only API inside the existing Python package

**Rationale**: The browser cannot safely hold Nautobot, Temporal, Kafka, or device credentials.
One FastAPI application under `network_automation.api` can reuse the existing settings,
Pydantic models, Nautobot adapter, Temporal converter, health probes, and SR Linux boundary
without becoming another automation service. It aggregates read models only; workflows and
activities remain unchanged.

**Alternatives considered**:

- Browser-to-upstream calls were rejected because they expose internal protocols and secrets.
- A standalone backend package was rejected because no independent domain or lifecycle requires
  it.
- GraphQL and generic CRUD infrastructure were rejected because the required reads are small and
  explicit.

### Decision: Keep Feature 005 entirely outside the UI execution path

**Rationale**: Feature 005 is intentionally deferred and has no accepted runtime or execution
state. Feature 006 may show only accepted Features 001-004 data and must not imply ZTP health,
readiness, or controls.

**Alternatives considered**: A deferred-feature status panel was rejected as product-scope noise;
the planning documentation remains the authority for Feature 005 status.

## Health Aggregation

### Decision: Probe services through their native read interfaces, never Docker control

**Rationale**:

- Nautobot health comes from its bounded HTTP health endpoint.
- Kafka health reuses/refactors the existing bounded metadata probe in
  `network_automation.health`.
- Temporal health uses a bounded namespace/service RPC with the existing Temporal settings.
- Worker health is the presence of workflow and activity pollers on the configured Temporal task
  queue, queried through Temporal's `DescribeTaskQueue` API.
- Consumer health is configured consumer-group existence with at least one active member, queried
  through the Kafka Admin API.
- Device validation is a capability state based on server-side credentials/network reachability;
  it is not required for core API liveness.

The API process must not mount `/var/run/docker.sock`, shell out to Compose, or rely on another
container's private `/tmp` heartbeat files. Each component reports `healthy`, `degraded`,
`unavailable`, or `unknown`, observation time, and a safe code. Overall state is `healthy` only
when Nautobot, Kafka, Temporal, worker, and consumer are healthy; it is `degraded` when the API
can serve useful information but one or more required components is not healthy; it is
`unavailable` only when no authoritative control-plane source can be observed.

**Alternatives considered**:

- Sharing process heartbeat files would couple containers through new ephemeral storage and still
  prove less than native registration.
- Calling `network-lab-check` would require Docker access and couples request latency to a
  120-second host diagnostic.
- Inferring worker/consumer health from recent workflows would report idle healthy processes as
  failed and stale failed processes as healthy.

## Nautobot Device Reads

### Decision: Extend the concrete Nautobot adapter with explicit list/topology projections

**Rationale**: `NautobotClient.get_deployment_intent()` remains the authoritative exact-device
normalization path for render/deploy/live comparison. A device list cannot efficiently call that
strict path once per row, and topology relationships are not currently read. Add narrow methods
that retrieve only approved Device, Interface, IPAddress, cable/endpoint, and namespaced BGP
context fields, then map them into API read models. Do not expose incidental raw serializer fields.

Device detail reuses `get_deployment_intent()` for intended loopback/interface/BGP values. Device
status, role, platform display, location, and primary IP remain direct Nautobot facts. Unsupported
or incomplete devices remain listable with their unavailable intent section rather than being
dropped.

**Alternatives considered**:

- Serializing raw Nautobot payloads leaks unstable external schemas.
- Calling exact deployment intent for every device creates an avoidable request fan-out and hides
  incomplete inventory.
- A generic Nautobot repository abstraction adds indirection without another implementation.

## Artifact And Live State

### Decision: Expose artifact identity only when history proves it

**Rationale**: Existing `ArtifactIdentity` already provides device, approved path, digest, and byte
count. API mapping returns a path relative to the configured artifact root, digest, and size; it
never reads or returns configuration content. Paths are resolved under the configured root before
metadata is accepted. Missing files remain historical metadata with `available=false`.

**Alternatives considered**: Filesystem scans cannot establish workflow association or latest
deployment and were rejected as an authority.

### Decision: Refactor validation preparation, not validation semantics

**Rationale**: Existing `SRLinuxClient.read_native_state()`, expected-state models,
`ValidationCheck`, and `DeviceValidationResult` are the accepted Feature 004 boundaries. The
current preparation activity writes an artifact, so it cannot be called from a read-only request.
Extract/reuse the pure expected-state and validation-result mapping needed to compare one
Nautobot deployment intent with one bounded read. Do not invoke `deploy()` and do not add a second
SR Linux client.

Live reads occur only when `GET /api/devices/{device_name}?live=true` explicitly requests them.
They have one API-level deadline, no Temporal retries, no background continuation, no cache, and
no overview/list polling. Existing validation checks are reported; Feature 006 does not inspect
extra configuration or calculate broad drift.

**Alternatives considered**:

- Calling `prepare_device_deployment()` was rejected because it writes an artifact.
- Starting a validation workflow was rejected because it moves orchestration into an observation
  request.
- A new gNMI implementation was rejected because Feature 004 owns device access.

## Temporal Visibility And History

### Decision: Treat Temporal metadata and decoded history as the workflow authority

**Rationale**: The application currently sets no memo or custom search attributes. Visibility can
list workflow ID, run ID, workflow type, status, and timing, but device/event/correlation and
business outcomes are available only in the workflow start input and terminal result. For the
small lab, list at most 25 recent executions by default (hard maximum 50). Use a semaphore of four
to fetch only the first start event and filtered close event needed by each visible list row. The
overview performs these shallow reads for at most eight recent visible executions, not all 25.
Fetch complete activity history only for one exact detail request. Entries that cannot be shallow-
hydrated remain visible with explicit unavailable fields.

Only workflow IDs beginning with `render-device-config:` or `deploy-device-config:` and workflow
type `RenderDeviceConfigWorkflow` are admitted. The Pydantic data converter and exact existing
request/result models decode allowlisted payloads. Arbitrary Temporal visibility queries are never
accepted from the browser.

**Alternatives considered**:

- Adding search attributes to existing workflow starts would alter accepted execution behavior and
  would not backfill retained history.
- Kafka consumption would create another ingestion subsystem and still would not own durable
  execution state.
- A UI database would duplicate Temporal and violate scope.

### Decision: Decode business outcome separately from Temporal execution status

**Rationale**: Accepted `RenderFailed` and `DeploymentFailed` values are handled workflow results,
so Temporal normally marks those executions `COMPLETED`. Terminal mapping is:

| Temporal state/result | Display outcome |
|---|---|
| Running metadata | `running` with current known/pending stage |
| `COMPLETED` + `RenderCompleted` | `render_succeeded` |
| `COMPLETED` + `RenderFailed` | `render_failed` |
| `COMPLETED` + `DeploymentCompleted` | `deployment_succeeded` |
| `COMPLETED` + `DeploymentFailed` | `deployment_failed` |
| Temporal failed/timed out/canceled/terminated | matching `execution_*` outcome |
| Undecodable/unknown | `unknown` with no success claim |

Safe category and stage may come from the existing terminal failure model. Arbitrary Temporal
failure messages and stacks are discarded.

### Decision: Map only durable, observable stage boundaries

**Rationale**: Intent retrieval, render, and artifact writing occur inside one activity and cannot
be represented as separate proven timestamps. The UI uses these exact stages:

| History evidence | Deployment label | Render label |
|---|---|---|
| Workflow execution started | Workflow started | Workflow started |
| `prepare_device_deployment` | Intent prepared and artifact written | N/A |
| `render_device_artifact` | N/A | Intent rendered and artifact written |
| `deploy_device_artifact` | gNMI deployment | N/A |
| `validate_device_state` | Operational validation | N/A |
| `publish_render_result` | Result published | Result published |
| Unknown activity | Unknown stage | Unknown stage |

Activity scheduled/started/completed/failed/timed-out/canceled events are correlated by scheduled
event ID. Attempt count is the maximum safe `ActivityTaskStarted.attempt`, supplemented for running
work by pending activity metadata. A history gap after validation but before publication is
`finalizing`, never inferred success. Unknown stages remain visible and do not break ordering.

**Alternatives considered**: The requested eight-step illustrative timeline was not adopted
literally because current history does not prove separate intent retrieval, render, and write
timestamps.

### Decision: Project deployments from deployment workflow history

**Rationale**: A deployment is a `deploy-device-config:` execution, not a new record. Deployment
list/detail endpoints filter the same bounded Temporal projection and decode existing
`DeploymentCompleted` or `DeploymentFailed` outcomes. Retention remains the existing three days;
Feature 006 does not claim long-term history.

## Topology

### Decision: Show explicit physical links first and validated logical BGP links second

**Rationale**: Nautobot cable/connected-endpoint relationships, when present, produce
`physical` links. The current accepted fixtures do not create cables, but Nautobot intent does
contain BGP neighbor addresses and interface IP ownership. A `bgp` logical link is created only
when a local neighbor address resolves to exactly one interface IP owned by another listed device;
ambiguous, self, missing, or one-sided facts do not create a link. Physical and BGP links are
visually and textually distinct and deduplicated by kind plus sorted endpoint/interface identity.
No physical adjacency is inferred from subnet overlap, descriptions, ASNs, or topology files.

The current lab is laid out deterministically by role/name in a lightweight responsive SVG.
Unknown roles use a stable simple grid. There is no force simulation or general graph engine.

**Alternatives considered**:

- Reading `lab/topology.yml` would make local lifecycle configuration a competing inventory
  source.
- Inferring physical links from `/31` prefixes or neighbor descriptions would overstate the data.
- A large graph library is unnecessary for two to tens of nodes.

## API Shape And Safety

### Decision: Use explicit REST read endpoints and partial-result envelopes

**Rationale**: The selected endpoints are `GET /healthz`, `/api/health`, `/api/overview`,
`/api/devices`, `/api/devices/{device_name}`, `/api/topology`, `/api/workflows`,
`/api/workflows/{workflow_id}`, `/api/deployments`, and
`/api/deployments/{workflow_id}`. Detail links carry `run_id` to pin a specific execution. Limits,
names, workflow IDs, and run IDs are validated and bounded. There are no write verbs, generic
resource routes, passthrough queries, or raw proxy responses.

Independent sections use an availability envelope. Expected upstream absence returns useful
`200` partial responses; invalid input returns `422`, missing admitted resources return `404`, and
unexpected service errors return a static safe `500` body. Logs include route, safe source/code,
duration, and correlation generated by the API but no raw external body or exception text.

**Alternatives considered**: Returning `503` for every partial failure would blank otherwise useful
operator views and make nginx health depend on all upstreams.

## Frontend And Polling

### Decision: Use React, TypeScript, Vite, Tailwind CSS, and small local state

**Rationale**: These are required by the feature. React Router supplies the five routes. Native
`fetch` with `AbortController` and focused query hooks is sufficient; a global state library and
server-state framework are unnecessary at current scale. Vitest, React Testing Library, and jsdom
provide lightweight component and route testing without a full browser-test platform.

IBM Plex Sans and IBM Plex Mono are bundled locally for a network-operations visual language; the
runtime requires no public font service. Status always has text and icon/shape in addition to
color.

**Alternatives considered**:

- Next.js adds server rendering and backend duplication with no requirement.
- A large component framework would push the UI toward a generic admin dashboard.
- End-to-end browser automation is deferred unless component/integration coverage proves
  insufficient during implementation review.

### Decision: Poll only visible read models

**Rationale**:

- Overview: every 15 seconds while visible.
- Device list and topology: every 30 seconds while visible.
- Workflow/deployment lists: every 10 seconds while visible.
- Running workflow/deployment detail: every 4 seconds.
- Terminal workflow/deployment detail: stop automatic polling after the terminal response.
- Device detail inventory/history: every 30 seconds while visible using `live=false`; `live=true` is
  issued once when the route opens and its timestamped result is retained without automatic device
  refresh.

Polling pauses while the document is hidden, aborts on navigation, permits only one request per
resource at a time, and uses a short capped retry delay after network errors. No WebSockets or SSE
are selected.

The component retains its latest successful response during a background refresh. It becomes
`stale` when the latest scheduled refresh fails or the observation age exceeds twice that
resource's polling interval. An initial failure has no retained data and is `unavailable` or
`error`, never stale. This requires only route-local component state, not a global cache.

## Runtime

### Decision: Add two services under the `ui` Compose profile

**Rationale**:

- `automation-ui-api` reuses the existing Python application image and package, starts through a
  new API command, mounts `./artifacts` read-only, and publishes
  `127.0.0.1:${LAB_UI_API_HOST_PORT:-8001}`.
- `automation-ui` is a multi-stage Vite build served by a patch-pinned nginx image, proxies `/api`
  to the API, and publishes `127.0.0.1:${LAB_UI_HOST_PORT:-3000}`.
- Both are under `profiles: ["ui"]`; default and `automation` profile behavior remains unchanged.
- API liveness is independent of upstream health so degraded observations remain available.
- `compose.device-access.yaml` may attach only `automation-ui-api` to the existing external device
  management network and inject runtime-only credentials for explicit live detail.

No volume, database, cache, broker, API gateway, public listener, or Docker socket is added.

**Alternatives considered**:

- A separate Python image was rejected initially because the existing package/image is sufficient;
  implementation may revisit only if measured image/runtime coupling becomes material and receives
  approval.
- Publishing only the API through nginx was simpler externally, but retaining a loopback API port
  supports direct acceptance probes and remains private.

## Resolved Gaps And Limits

- Temporal retention limits visible history to the configured three-day window.
- Poison Kafka records and transport coordinates are not visible because they never become
  Temporal executions or are intentionally discarded.
- Existing histories cannot be efficiently filtered by device/correlation without bounded history
  hydration; no search attributes will be added in this feature.
- Detailed last validation is available only while its workflow history is retained and decodable.
- Canonical data may reference deleted Nautobot fixtures; missing joins remain visible as source
  gaps.
- Known failed deployment acceptance is performed only if persistent evidence already exists; the
  UI feature will not create a failure by mutating infrastructure.
- If neither explicit Nautobot cable data nor unambiguous BGP intent ownership exists, topology
  shows nodes without links and identifies the missing source data.
