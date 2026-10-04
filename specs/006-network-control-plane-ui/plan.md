# Implementation Plan: Network Automation Control Plane UI

**Branch**: `006-network-control-plane-ui` | **Date**: 2026-09-13 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/006-network-control-plane-ui/spec.md`

**Status**: IMPLEMENTATION AND CANONICAL ACCEPTANCE COMPLETE — 2026-09-15

## Summary

Add a read-only operator control plane over accepted Features 001-004. A FastAPI application in
the existing `network_automation` package aggregates bounded, sanitized read models from Nautobot,
Temporal, native Kafka/Temporal process-health evidence, retained artifact metadata, and optional
Feature 004 live validation. A React/TypeScript/Vite/Tailwind frontend consumes only that API and
is served as static assets through nginx. Two loopback-only Compose services are gated by the `ui`
profile. No database, Kafka consumer, orchestration, mutation, or Feature 005 path is added.

## Technical Context

**Language/Version**: Existing CPython 3.12.13 package; React 19 with TypeScript 5 on a pinned Node
22 LTS build image

**Primary Dependencies**: Existing Pydantic v2, httpx, confluent-kafka, Temporal SDK with Pydantic
converter, and pyGNMI; add FastAPI, Uvicorn, React, React Router, Vite, Tailwind CSS, Vitest, React
Testing Library, jsdom, locally bundled IBM Plex fonts, and patch-pinned nginx

**Storage**: Existing Nautobot, Kafka, Temporal PostgreSQL history, and read-only artifact directory;
no new durable or disposable application store

**Testing**: Existing pytest/pytest-asyncio plus FastAPI ASGI tests; Vitest, React Testing Library,
and jsdom; real read-only Nautobot/Temporal/API/UI acceptance on canonical infrastructure

**Target Platform**: Canonical Ubuntu 24.04.4 x86-64 VM with Docker Engine/Compose; browser reached
through SSH forwarding from the developer workstation; responsive desktop and 375-pixel viewport

**Project Type**: One existing typed Python package plus one static frontend application and two
profile-gated runtime services

**Performance Goals**: API liveness under 1 second; overview useful within 5 seconds when healthy;
individual healthy upstream probes bounded to 3 seconds; overview aggregate deadline 8 seconds;
device live read deadline 15 seconds; default list windows 25 workflows/50 devices; current small
lab only

**Constraints**: Strictly read-only; browser talks only to API; partial upstream failure; no raw
configuration/history/stacks/secrets; no Kafka consumption; no workflow changes/search attributes;
no background device polling; no WebSockets/SSE; loopback-only; Feature 005 untouched

**Scale/Scope**: Current two-device SR Linux lab, at most 100 displayed devices, 50 recent workflow
executions, 200 topology links, five application routes, and ten explicit GET endpoints

## Constitution Check

*GATE: Passed before research and rechecked after design.*

| Principle | Pre-Design Gate | Post-Design Evidence |
|---|---|---|
| Explicit Architectural Ownership | PASS: UI is observation only; Nautobot remains intent authority, Kafka transport, Temporal durable execution, Feature 002 renderer, Feature 003 executor, and Feature 004 deployment/validation owner. | Browser reaches only the API. Source map assigns every field to an accepted authority. Temporal history, not Kafka, supplies workflow state; live reads reuse Feature 004. |
| Small, Explicit Implementation | PASS: one required read API and one required static frontend; no generic CRUD or orchestration. | Five narrow backend modules, five routes, explicit models, lightweight SVG, native fetch/local state, no framework/store/graph abstraction. |
| Reproducible Local Infrastructure | PASS: optional services use pinned images, loopback ports, meaningful liveness, and no storage. | One `ui` profile, existing Python image reuse, static nginx image, read-only artifact mount, no Docker socket, and documented SSH forwarding. |
| Evidence Over Process Status | PASS: acceptance requires real Nautobot/Temporal data and partial dependency failure, not container state alone. | API maps native health evidence and retained history; unit mocks boundaries while canonical tests remain read-only and inspect browser/network output for leaks. |
| Spec-Driven, Bounded Delivery | PASS: Feature 006 has its own branch/artifacts and explicit stop before implementation. | Research, data model, API/source/frontend contracts, Lavish mockup, quickstart, tasks, and analysis precede a separate implementation approval. |

No constitution violation requires complexity justification. The additional frontend ecosystem and
two optional services are direct requirements of this bounded UI feature, not speculative layers.

## Design Decisions

### Backend Read Boundaries

1. FastAPI lifespan in `api/app.py` exclusively creates and closes shared bounded Nautobot and
   Temporal clients; source modules receive those clients and never own a second lifecycle.
2. Existing health probes are refactored into reusable safe functions. Worker health comes from
   Temporal task-queue pollers; consumer health comes from Kafka group membership. No Docker socket
   or shared heartbeat volume is introduced.
3. Nautobot client gains explicit bounded inventory and relationship reads while
   `get_deployment_intent()` remains the normalized exact-device intent path.
4. Temporal visibility admits only existing workflow type/ID prefixes. Workflow lists return 25 by
   default and at most 50; bounded shallow reads decode only start and close events with concurrency
   four. Overview shallow-hydrates at most eight visible recent executions. Full activity history is
   fetched only for the exact workflow/deployment detail screen.
5. Terminal workflow result, not Temporal `COMPLETED`, determines business success/failure.
6. History activity names map through an allowlist to exact durable stages. Unknown activities are
   represented safely; raw payloads and failures never leave the adapter.
7. Deployment endpoints project `deploy-device-config:` workflows; no separate record is stored.
8. Opening device detail performs one 15-second-budget live read using extracted pure Feature 004
   expected-state and validation mapping plus the existing SR Linux read path. Thirty-second detail
   polling refreshes only Nautobot/Temporal sections and preserves the prior timestamped live
   snapshot without issuing another device request. It never prepares/writes an artifact or invokes
   deployment.
9. API modules do not import Kafka producers, workflow start code, rendering/artifact writers,
   deployment actions, gNMI Set paths, or Nautobot mutation helpers. Structural tests enforce the
   route/method and import boundary without introducing a generic read/write driver layer.

### Source And Topology Rules

The normative field map is [contracts/source-map.md](contracts/source-map.md). Physical topology
requires exact Nautobot cable/connected-endpoint relationships. A logical BGP link may be shown only
when a Nautobot neighbor address resolves to exactly one interface IP owned by another listed
device. It remains labeled logical; subnet overlap, ASN, descriptions, and `lab/topology.yml` never
manufacture physical relationships. Nodes remain useful when no link source exists.

### API And Error Rules

The normative API is [contracts/read-api.md](contracts/read-api.md). Upstream-dependent aggregate
sections carry availability/freshness and return useful HTTP 200 partial data. Invalid IDs/limits
are rejected before upstream use. Raw FastAPI validation, exceptions, responses, history, artifact
contents, and paths are sanitized. API responses use `no-store`; nginx does not transform `/api`
errors into SPA responses.

### Frontend UX

The normative route/layout/state contract is [contracts/frontend.md](contracts/frontend.md). The
Lavish design source is the user's operator-control-plane direction, implemented with custom
portable CSS because the repository has no existing product design system. The generated review
artifact is [ux/control-plane-direction.html](ux/control-plane-direction.html).

The shell has only Overview, Devices, and Workflows. Overview uses compact diagnostic cells,
role-arranged SVG topology, recent activity, and component health. Device detail aligns intended
and existing validated live state and shows metadata-only latest deployment. Workflow detail uses
an inline vertical durable-stage timeline with a safe failure panel and run context. No mutation or
future-action controls appear.

### Polling

Overview polls every 15 seconds; devices/topology and the Nautobot/Temporal portions of device detail
every 30; workflow/deployment lists every 10; running detail every 4 and stops when terminal.
Polling pauses when the page is hidden, aborts on navigation, and never overlaps the same resource.
Live device validation is one explicit `live=true` read when device detail opens; subsequent timed
requests use `live=false` and preserve the timestamped initial live result. The 15 seconds is an
operation timeout budget, never a refresh interval. No WebSockets or SSE.

## Project Structure

### Documentation (this feature)

```text
specs/006-network-control-plane-ui/
|-- spec.md
|-- plan.md
|-- research.md
|-- data-model.md
|-- quickstart.md
|-- contracts/
|   |-- read-api.md
|   |-- source-map.md
|   `-- frontend.md
|-- ux/
|   `-- control-plane-direction.html
|-- checklists/
|   |-- requirements.md
|   `-- review.md
`-- tasks.md
```

### Source Code (repository root)

```text
pyproject.toml                         # FastAPI/Uvicorn dependencies and API command
uv.lock                               # locked Python dependency graph
compose.yaml                          # ui-profile API/static services and loopback ports
compose.device-access.yaml            # optional API device-management attachment
.env.example                          # UI/API ports and bounded read settings
Dockerfile.ui                         # pinned Node build and nginx runtime stages
ui/
|-- package.json
|-- package-lock.json
|-- tsconfig.json
|-- vite.config.ts
|-- index.html
|-- nginx.conf
`-- src/
    |-- main.tsx
    |-- App.tsx
    |-- styles.css
    |-- api/
    |   |-- client.ts
    |   `-- types.ts
    |-- components/
    |   |-- AppShell.tsx
    |   |-- AsyncSection.tsx
    |   |-- Status.tsx
    |   |-- Topology.tsx
    |   `-- WorkflowTimeline.tsx
    `-- pages/
        |-- OverviewPage.tsx
        |-- DevicesPage.tsx
        |-- DeviceDetailPage.tsx
        |-- WorkflowsPage.tsx
        `-- WorkflowDetailPage.tsx
src/network_automation/
|-- settings.py                       # bounded API/history/device settings
|-- health.py                         # reusable safe native probes
|-- intent/nautobot.py                # explicit list/relationship reads retained here
|-- activities/deployment.py          # pure expected/live comparison extraction
`-- api/
    |-- __init__.py
    |-- app.py                         # lifespan, middleware, routes, overview
    |-- models.py                      # strict frontend read models
    |-- health.py                      # aggregate health endpoint
    |-- devices.py                     # device/detail/topology projections
    `-- workflows.py                   # Temporal listing/history/stage/deployment mapping
tests/
|-- unit/
|   |-- test_api_health.py
|   |-- test_api_devices.py
|   |-- test_api_workflows.py
|   |-- test_api_safety.py
|   |-- test_automation_compose.py
|   `-- existing Features 001-004 tests
`-- integration/
    |-- test_control_plane_api.py
    `-- existing Features 001-004 acceptance tests
```

**Structure Decision**: Preserve one Python package and extend only existing concrete source
boundaries. Keep the required frontend isolated under `ui/` with no backend logic. Use one API
module per source/read concern rather than repositories, services, plugins, or generic clients.

## Implementation Sequence And Gates

1. Add strict read models, settings, and pure safe mapping tests.
2. Add/refactor native health, Nautobot inventory/topology reads, and bounded Temporal summary
   projections needed by the complete overview without changing accepted render/deploy behavior.
3. Deliver the complete health/overview slice, including real workflow/deployment and topology
   summaries.
4. Add device list/detail by consuming the overview's shared latest-deployment projection.
5. Extend the shared Temporal projection with full history stages and workflow/deployment detail.
6. Add interactive topology detail by consuming the overview's shared topology projection.
7. Build every frontend screen/state/viewport combination from the approved Lavish contract.
8. Add `ui` profile runtime, nginx same-origin proxy, loopback ports, health, and read-only mounts.
9. Run unit/build/Compose tests and Features 001-004 replay/regressions.
10. Run read-only canonical acceptance and record actual evidence and limitations.

Implementation was approved by the owner on 2026-09-14 with the on-demand live-read, structurally
read-only API, and bounded Temporal hydration guardrails recorded above. Canonical testing must not
create a failed deployment or mutate Nautobot/device state merely to populate the UI.

## Approved Decisions

Implementation approval explicitly accepted:

1. Bounded Temporal visibility plus shallow list hydration (default 25, maximum 50, concurrency
   four), overview shallow hydration of at most eight visible executions, and full history only for
   one detail request instead of search attributes or another store.
2. Topology distinction between authoritative physical links and address-resolved logical BGP
   intent; no physical inference when Nautobot cable data is absent.
3. One optional 15-second live validation read on device detail, with no automatic live polling.
4. Reuse of the existing Python image for the API and addition of FastAPI/Uvicorn to the shared
   package lock.
5. The dark, dense IBM Plex operator-console visual direction in the Lavish artifact.
6. Read-only acceptance against whatever workflow/deployment evidence is retained; a failed outcome
   is verified only if it already exists.
7. One explicitly authorized reversible stop/start of a safe read dependency may prove partial
   availability; it must preserve data and automation state and be restored immediately.

All seven decisions and the three implementation guardrails were approved on 2026-09-14.

## Complexity Tracking

No constitution violations are proposed.
