# Frontend UX Contract

## Routes

| Route | Purpose | Polling |
|---|---|---|
| `/` | Overview health, counts, topology, recent activity | 15 seconds while visible |
| `/devices` | Device inventory and latest outcome | 30 seconds while visible |
| `/devices/:deviceName` | Intent, retained evidence, optional one-shot live state | One `live=true` request when opened; 30-second base refresh uses `live=false` and retains the initial live snapshot |
| `/workflows` | Recent render/deployment workflow list | 10 seconds while visible |
| `/workflows/:workflowId?run_id=` | Ordered workflow/deployment detail | 4 seconds while running; stop when terminal |

There is no separate deployment navigation item. Deployment rows and overview activity drill into
the workflow detail route, which presents deployment-specific content when applicable.

## Global Shell

- Compact top bar: product title, environment label `Local lab`, last observation time, and overall
  text/icon status.
- Primary navigation contains only Overview, Devices, and Workflows.
- No command palette, settings menu, user menu, notification center, or action toolbar.
- Main content uses a maximum readable width but allows topology and tables to use the available
  canvas.

## Overview Layout

Desktop:

```text
+-----------------------------------------------------------------------+
| Network Automation Lab   Local lab    observed 14:32:18       Healthy |
| Overview       Devices       Workflows                                |
+-----------------------------------------------------------------------+
| Devices | Active workflows | Successful deployments | Failed         |
+------------------------------------------+----------------------------+
| Network topology                         | Recent activity            |
| [role-arranged SVG nodes and links]      | time / device / stage      |
+------------------------------------------+----------------------------+
| Dependency health: Nautobot Kafka Temporal Worker Consumer Device     |
+-----------------------------------------------------------------------+
```

Counts are compact diagnostic cells, not oversized marketing cards. Partial source failure keeps
the grid and replaces only affected values with `Unavailable` plus a concise reason.

Narrow viewport: status cells become a two-column grid, topology precedes activity, dependency
health becomes a wrapped list, and identifiers truncate visually with full accessible titles.

## Device List And Detail

Device list uses a dense table on desktop and labeled stacked rows on narrow viewports. Rows show
name, role/platform, management address, inventory state, latest deployment time/outcome, and
validation status.

Device detail:

```text
+-----------------------------------------------------------------------+
| < Devices   f004-leaf01   leaf / SR Linux                  Validated  |
+----------------------------------+------------------------------------+
| Intended state                   | Live state                         |
| hostname / loopback / interfaces | hostname / interfaces / addresses |
| ASN and neighbors                | BGP sessions                       |
|                                  | mismatch markers inline            |
+----------------------------------+------------------------------------+
| Latest deployment: workflow, artifact metadata, time, duration, result|
+-----------------------------------------------------------------------+
```

Intent and live rows align by invariant where existing validation supports comparison. Missing live
access yields one calm unavailable panel; it does not collapse intent/history. Artifact content is
never previewed.

## Workflow And Deployment Detail

Workflow list is newest first with status, kind, device, current/failed stage, start time, duration,
and correlation suffix. Detail is the strongest visual:

```text
+----------------------------------------------+------------------------+
| Execution timeline                           | Run context            |
| [check] Workflow started       14:31:02       | workflow / run         |
|    |                                         | event / correlation    |
| [check] Intent + artifact      14:31:03 1.2s  | device / start / end   |
|    |                                         | artifact digest/bytes  |
| [x] gNMI deployment            Auth failure  | safe failure summary   |
|    |                                                                  |
| [dot] Operational validation   Not reached                          |
+-----------------------------------------------------------------------+
```

Each stage has text state, shape/icon, timestamps, duration, and attempt count when proven. The
failed stage expands inline rather than opening a modal. Unknown activity history appears as an
`Unknown stage` row. Running state uses a restrained pulse only on the small status marker and must
respect reduced-motion preferences.

## Topology Presentation

- Lightweight responsive SVG with deterministic role/name placement.
- Device nodes are compact equipment plates, not bubbles: role stripe, hostname, platform, and
  text/icon status.
- Solid line means authoritative physical endpoint data; dashed line means logical BGP intent.
- Links default to unknown state unless explicit evidence supports another status.
- Selection adds a high-contrast outline and updates a compact detail strip below the SVG; opening
  detail uses a normal link.
- No zoom canvas, force simulation, minimap, drag layout, animated packets, or invented utilization.

## Visual Direction

- **Character**: focused network operations console, not a generic SaaS dashboard.
- **Palette**: deep graphite background, slightly raised ink panels, cool cyan for selection/data
  paths, green for healthy/completed, amber for degraded/running, red for failed, and slate for
  unknown. Color never carries status alone.
- **Typography**: locally bundled IBM Plex Sans for interface text and IBM Plex Mono for device
  names, identifiers, addresses, timestamps, and ASNs.
- **Density**: 12-14px operational detail, compact 32-40px rows, clear section spacing, thin borders,
  and minimal shadow.
- **Hierarchy**: current state first, source/freshness second, identifiers and metadata third.
- **Motion**: no decorative transitions; only subtle running-state feedback with reduced-motion
  fallback.

## Loading, Empty, Partial, And Error States

- Loading uses shape-matched skeleton rows; existing content remains during background refresh.
- Empty states name the authoritative source and say that no records were returned; no sample data
  appears in the product.
- Partial failure uses an inline source banner and section-level unavailable state while preserving
  other sections.
- Stale data is the last successful route-local response retained after a scheduled refresh fails
  or its observation age exceeds twice the route polling interval. It shows observation time and a
  `Stale` label; an initial failure has no stale data.
- Route-level not found and safe service errors provide navigation back to the relevant list, no
  retry/mutation action.
- A browser-network failure may offer `Refresh page`; it must not invoke automation or upstream
  mutation.

## Accessibility And Responsive Rules

- Status has icon/shape plus visible text and accessible name.
- Focus indicators are high contrast; skip navigation and semantic landmarks are present.
- Tables use semantic headers on desktop and preserve labels in stacked mobile rows.
- SVG nodes are keyboard-selectable links with titles; link meaning also appears in a legend.
- At 375px, no page-level horizontal overflow is permitted. Long IDs truncate in layout and remain
  available through accessible title/copy selection, not a modal.
- Minimum pointer target is 40px for navigation and selectable nodes.

## Required State And Viewport Matrix

Each row is verified at desktop and 375-pixel widths. `Partial` means one independent section/source
fails; `stale` means the deterministic retained-response rule above.

| Screen/region | Loading | Empty | Partial | Stale | Unavailable | Safe error | Keyboard drill-down |
|---|---:|---:|---:|---:|---:|---:|---:|
| Overview | Required | Required | Required | Required | Required | Required | Navigation and activity links |
| Device list | Required | Required | Required | Required | Required | Required | Every device row/link |
| Device detail | Required | Required sections | Required | Required | Required sections | Required | Breadcrumb and workflow link |
| Workflow list | Required | Required | Required | Required | Required | Required | Every workflow row/link |
| Workflow detail/timeline | Required | Required history | Required | Required | Required history | Required | Breadcrumb and identifiers |
| Topology | Required | Required links/nodes | Required | Required | Required | Required | Every node and device link |

## Prohibited UI Elements

No deploy, render, retry, rerun, cancel, remediate, edit, configuration preview, ZTP, settings,
users, reports, alerts, notification, or placeholder future-action control appears on any screen.
