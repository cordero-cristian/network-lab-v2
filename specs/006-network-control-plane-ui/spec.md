# Feature Specification: Network Automation Control Plane UI

**Feature Branch**: `006-network-control-plane-ui`

**Created**: 2026-09-13

**Status**: IMPLEMENTATION AND CANONICAL ACCEPTANCE COMPLETE — 2026-09-15

**Input**: User description: "Build a read-only operator control plane that visualizes the
health, inventory, durable workflows, deployments, live device state, and failures of the
existing Features 001-004 automation system without adding mutation or orchestration."

## Clarifications

### Session 2026-09-14

- Q: How may device live state refresh? → A: Opening device detail performs one bounded read-only
  state/validation query with a 15-second operation budget. Later page polling may refresh only
  Nautobot and Temporal data; it must not repeat the device read automatically.
- Q: How is the API kept structurally read-only? → A: Expose only GET/HEAD behavior, keep API imports
  away from Kafka producers, workflow starts, render/write actions, deployment activities, gNMI Set,
  and Nautobot mutation, and reuse only the narrow existing Feature 004 read/validation path without
  adding a generic driver abstraction.
- Q: How much Temporal history may lists hydrate? → A: Workflow lists use visibility plus shallow
  start/close-event decoding with default 25, maximum 50, and concurrency four. Overview limits
  shallow hydration to eight visible recent executions. Full activity history is fetched only for
  one workflow/deployment detail request.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Assess Platform Health (Priority: P1)

As a lab operator, I can open one overview and quickly determine whether the automation
platform is healthy, what is currently active, and whether recent deployments require
attention.

**Why this priority**: Rapid situational awareness is the primary value of a control-plane
view and remains useful even before deeper drill-downs are available.

**Independent Test**: Open the overview against the canonical lab and verify that real
dependency health, device count, active workflow count, recent deployment outcomes, compact
topology, and recent activity are visible without invoking any automation action.

**Acceptance Scenarios**:

1. **Given** all authoritative dependencies are available, **When** the operator opens the
   overview, **Then** it shows an overall healthy state and current values derived from those
   dependencies.
2. **Given** one read dependency is unavailable, **When** the operator opens or refreshes the
   overview, **Then** unaffected information remains visible and the unavailable section is
   clearly marked degraded or unavailable.
3. **Given** no recent workflows or deployments exist, **When** the overview loads, **Then**
   it displays an accurate empty state rather than fabricated activity or metrics.

---

### User Story 2 - Inspect Device Intent And State (Priority: P2)

As a lab operator, I can browse known devices and inspect one device's intended state, latest
artifact and deployment, and available live operational state in one place.

**Why this priority**: Device-centered diagnosis connects authoritative intent to the latest
automation and validation evidence without replacing the systems that own those facts.

**Independent Test**: Select a real lab device and verify that its identity, role, platform,
location, management address, intended interface and routing summary, latest artifact,
deployment, validation result, and bounded live state are represented accurately.

**Acceptance Scenarios**:

1. **Given** devices exist in authoritative inventory, **When** the operator opens the device
   list, **Then** each device shows identity, role, platform, management address, inventory
   status, and available latest deployment and validation status.
2. **Given** a selected device has intended state and completed validation evidence, **When**
   the operator opens its detail view, **Then** intent, artifact, deployment, and operational
   summaries are grouped by source and time.
3. **Given** bounded live validation is unavailable or times out, **When** device detail is
   requested, **Then** inventory and historical evidence remain visible and live state is
   explicitly marked unavailable without retrying indefinitely.
4. **Given** existing validation identifies an intent/live mismatch, **When** detail is
   displayed, **Then** that existing mismatch is highlighted without calculating a new
   compliance or remediation decision.

---

### User Story 3 - Diagnose Workflow And Deployment Outcomes (Priority: P2)

As a lab operator, I can browse recent durable workflows and inspect the ordered execution
path, timing, retries, deployment outcome, validation result, and safe failure location of one
run.

**Why this priority**: A durable workflow timeline is the strongest diagnostic view for
understanding what the latest automation run did and where a failure occurred.

**Independent Test**: Open one completed successful run and one safely available failed run,
then compare the displayed identifiers, stages, timestamps, duration, retries, artifact
metadata, deployment result, validation result, and failure summary with authoritative
workflow history.

**Acceptance Scenarios**:

1. **Given** recent durable workflow executions exist, **When** the operator opens the
   workflow list, **Then** each row identifies the workflow, event, correlation, device,
   status, timing, and safe failure category where available.
2. **Given** a completed successful workflow, **When** its detail view opens, **Then** an
   ordered timeline distinguishes request receipt, workflow start, intent retrieval, render,
   artifact write, device deployment, operational validation, and result publication using
   only stages supported by history.
3. **Given** a failed workflow, **When** its detail view opens, **Then** the failed stage,
   attempts that can be determined safely, stable category, and sanitized message are clear,
   while raw exception stacks and secrets are absent.
4. **Given** a workflow is still running, **When** its detail view remains open, **Then** its
   state refreshes at a bounded interval and frequent refresh stops after a terminal state.

---

### User Story 4 - Explore The Small Lab Topology (Priority: P3)

As a lab operator, I can understand the current small SR Linux lab at a glance and select a
device from a simple topology view.

**Why this priority**: Topology provides useful network context, but it must remain a focused
view of the present lab rather than becoming a general graph platform.

**Independent Test**: Display the canonical small lab using real device and link data, select
each node, and verify that supported health state and navigation agree with device detail.

**Acceptance Scenarios**:

1. **Given** authoritative device and interface relationship data, **When** topology loads,
   **Then** it shows the current device nodes and deduplicated links with stable labels.
2. **Given** supported health or validation evidence for a node, **When** topology displays
   it, **Then** the node indicates healthy, degraded, failed, or unknown without inventing
   unsupported link health.
3. **Given** the operator selects a node, **When** selection completes, **Then** the
   corresponding device is clearly identified and can be opened through normal navigation.
4. **Given** relationship data is incomplete, **When** topology loads, **Then** known devices
   remain visible and missing links are represented as incomplete data rather than inferred.

### Edge Cases

- One or more upstream systems may time out while others remain healthy.
- An authoritative source may return malformed, incomplete, duplicated, or unexpectedly large
  data; the boundary must fail that section safely and preserve unaffected sections.
- A workflow may have no event or correlation identifier because older retained history does
  not contain one.
- A workflow may be running, canceled externally, terminated, timed out, continued as new, or
  missing detailed history while still having summary metadata.
- Workflow history may contain retries, repeated activity types, failed attempts followed by
  success, or unknown event/activity types from an older release.
- An artifact referenced by workflow history may have been removed or may exist outside the
  approved artifact root.
- A device may have no primary management address, latest artifact, deployment, validation
  evidence, BGP configuration, or live connectivity.
- Inventory relationships may be one-sided, duplicated, incomplete, or contain interfaces not
  relevant to physical topology.
- A dependency may recover between summary and detail requests, so each response must carry
  its own freshness and availability context.
- Browser width may be narrow enough that dense tables and timelines require reflow without
  hiding status or identifiers.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The feature MUST be a read-only observation surface for accepted Features
  001-004 and MUST leave deferred Feature 005 unchanged.
- **FR-002**: Nautobot MUST remain the sole authority for intended device and topology data,
  Temporal MUST remain the authority for durable execution and history, Kafka MUST remain only
  event transport, Feature 002 MUST remain the renderer, Feature 003 MUST remain execution
  owner, and Feature 004 MUST remain deployment and validation owner.
- **FR-003**: The browser MUST obtain all displayed automation data through one bounded
  read-only service and MUST NOT connect directly to internal systems or network devices.
- **FR-004**: The read service MUST expose only retrieval and health operations and MUST NOT
  render, deploy, rerun, retry, remediate, cancel, publish events, or mutate inventory or
  devices.
- **FR-005**: The interface MUST provide Overview, Devices, and Workflows navigation plus
  drill-down views for one device and one workflow/deployment.
- **FR-006**: The overview MUST show overall health, available subsystem health, device count,
  active workflow count, recent successful and failed deployments, compact topology, and
  recent activity using only authoritative available facts.
- **FR-007**: Overall health MUST be computed from explicit dependency states, MUST distinguish
  degraded from unavailable, and MUST not report healthy when a required observation source is
  known unhealthy.
- **FR-008**: Every aggregated response MUST identify observation time and section-level
  availability or freshness where sources can differ.
- **FR-009**: Failure of one upstream read MUST NOT prevent successful independent reads from
  appearing in the same aggregate response.
- **FR-010**: External reads MUST have explicit finite time bounds, and timeout outcomes MUST
  be represented as safe unavailable states rather than unhandled errors.
- **FR-011**: The device list MUST expose name, role, platform, location where available,
  management address, inventory status, latest deployment summary, and validation status.
- **FR-012**: Device detail MUST separate intended state, artifact metadata, deployment
  evidence, historical validation, and requested live state so operators can identify each
  source and observation time.
- **FR-013**: Intended device detail MUST summarize hostname, loopback, routed interfaces, BGP
  autonomous system, and neighbors when those facts exist in authoritative inventory.
- **FR-014**: Live device detail MUST reuse accepted read-only validation behavior where
  practical and MUST summarize hostname, interface state and addresses, BGP neighbor state,
  and existing mismatch evidence without implementing a second device client.
- **FR-015**: A device-detail request MAY perform one bounded live validation read; the system
  MUST NOT continuously poll devices or perform device reads for overview/list requests.
- **FR-016**: Artifact presentation MUST be metadata-only by default, MUST constrain paths to
  the approved artifact root, and MUST NOT return raw rendered configuration content.
- **FR-017**: The workflow list MUST expose workflow, event, correlation, and device identity;
  execution status; start and completion time; duration; and safe failure category where each
  value is authoritatively available.
- **FR-018**: Workflow detail MUST derive execution status, timing, retry/failure information,
  and ordered stages from durable workflow metadata and history rather than reconstructing
  state from event transport.
- **FR-019**: Workflow stage presentation MUST distinguish completed, running, failed,
  skipped/not reached, and unknown stages without claiming a stage occurred when history does
  not prove it.
- **FR-020**: Workflow detail MUST associate existing artifact metadata, deployment outcome,
  and validation outcome where authoritative identifiers permit an unambiguous association.
- **FR-021**: Unknown historical event or activity types MUST remain visible as safe unknown
  stages and MUST NOT crash or silently rewrite the timeline.
- **FR-022**: Failure presentation MUST use stable safe categories and sanitized messages and
  MUST exclude raw stacks, exception object serialization, credentials, and raw upstream
  responses.
- **FR-023**: The feature MUST document unavailable event metadata as a gap rather than add a
  continuously running event consumer or new event-ingestion state.
- **FR-024**: Topology MUST use authoritative device and interface relationship data, support
  the current small lab, show selectable labeled nodes and deduplicated links, and avoid
  inferring unsupported relationships.
- **FR-025**: Topology status MUST be based on available real health, deployment, or validation
  evidence and MUST show unknown when no supported status exists.
- **FR-026**: The interface MUST provide polished loading, empty, partial, stale, unavailable,
  and error states for every main screen. Stale means a previously successful response retained
  after the latest scheduled refresh fails or ages beyond twice that screen's polling interval;
  an initial failure with no prior response is unavailable/error, not stale.
- **FR-027**: Dense identifiers, status, tables, topology, and timelines MUST remain readable
  and navigable on desktop and narrow browser widths without horizontal page overflow.
- **FR-028**: Status MUST be communicated with text and shape/icon as well as color, and core
  navigation and drill-downs MUST be keyboard accessible.
- **FR-029**: The visual language MUST prioritize operator state, hierarchy, diagnostic context,
  and low visual noise over decorative effects or generic administrative-dashboard patterns.
- **FR-030**: The interface MUST contain no mutation controls, including deploy, render, rerun,
  retry, remediate, edit, publish, cancel, or ZTP controls; future-action placeholders MUST
  also be absent.
- **FR-031**: Overview data MUST refresh at a bounded low-frequency interval while visible;
  running workflow detail MAY refresh more frequently and MUST reduce or stop frequent refresh
  after terminal completion.
- **FR-032**: The initial feature MUST NOT require bidirectional live-update infrastructure,
  continuously running browser sessions, or a client-side global state platform.
- **FR-033**: The services MUST be separately enabled, bound to host loopback, usable through
  documented SSH forwarding, and absent from default supporting-service startup.
- **FR-034**: The interface and read service MUST NOT be publicly exposed by the canonical
  runtime configuration and MUST NOT hardcode a canonical host address.
- **FR-035**: The feature MUST add no persistent database, cache, queue, event consumer,
  message broker, analytics warehouse, or durable user-interface state.
- **FR-036**: Credentials MUST remain in server-side runtime settings and MUST never appear in
  browser responses, generated assets, URLs, client logs, server logs, or test evidence.
- **FR-037**: Responses and logs MUST exclude raw configuration, raw workflow stack traces,
  unrestricted artifact paths, authorization headers, tokens, passwords, and raw external
  payloads.
- **FR-038**: Resource identifiers accepted through routes or filters MUST be validated and
  bounded before use in upstream queries or local artifact lookup.
- **FR-039**: Integration and acceptance testing MUST observe existing canonical data and MUST
  NOT mutate Nautobot intent, devices, workflows, events, artifacts, or persistent infrastructure
  merely to create interface fixtures or outcome evidence. One explicitly authorized, reversible
  stop/start of a safe read dependency MAY test partial availability when it preserves all data and
  automation state and is restored immediately.
- **FR-040**: Existing Features 001-004 unit, replay, component, integration, and canonical
  behavior MUST remain healthy.
- **FR-041**: Frontend visual design and implementation MUST follow the approved Lavish design
  direction while Lavish MUST NOT alter backend ownership, data authority, or feature scope.
- **FR-042**: The feature MUST NOT add authentication, authorization, user administration,
  alerts, notifications, reports, settings, public exposure, ZTP control, or generalized
  topology capabilities.

### Key Entities

- **System Health Summary**: Overall observation state plus independent status, latency or
  timing, freshness, and safe diagnostic context for each observable subsystem.
- **Device Summary**: Inventory-owned device identity and classification joined to optional
  latest deployment and validation summaries without becoming a new source of truth.
- **Device Detail**: Device summary plus separated intended-state, artifact, deployment,
  historical validation, and bounded live-state sections with source/freshness context.
- **Workflow Summary**: Durable execution identity, correlation metadata where available,
  device, lifecycle status, timing, duration, and optional safe failure category.
- **Workflow Detail**: Workflow summary plus ordered history-derived stages, safe attempts,
  artifact metadata, deployment/validation outcomes, and sanitized failure summary.
- **Execution Stage**: One safely mapped durable-history milestone with order, state,
  timestamps, duration, attempts where supported, and optional safe failure information.
- **Deployment Summary**: Existing deployment and validation outcome associated with a durable
  workflow; it is a projection, not a new durable deployment record.
- **Topology Node**: Inventory device identity plus supported current display status and
  navigation target.
- **Topology Link**: Deduplicated relationship between two device interfaces supported by
  authoritative inventory data.
- **Availability Envelope**: Observation timestamp, source state, freshness, and safe error
  category used to preserve partial results.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On the canonical lab, an operator can identify overall platform state and any
  unhealthy observed subsystem within 10 seconds of opening the overview.
- **SC-002**: The overview displays 100% of real inventoried lab devices and all recent durable
  workflows within the configured bounded result window, with zero fabricated metrics.
- **SC-003**: An operator can navigate from overview to one device's intended state, latest
  automation outcome, and available live state in no more than two selections.
- **SC-004**: For every accepted visible workflow, displayed lifecycle status and timing agree
  with durable execution metadata; every displayed stage is traceable to durable history or is
  explicitly marked unknown/unavailable.
- **SC-005**: For a known failed execution, an operator can identify the failed stage and safe
  failure category within 15 seconds without access to a raw stack trace.
- **SC-006**: Stopping one safe-to-stop read dependency leaves all independent sections usable
  and marks 100% of affected sections degraded or unavailable rather than blanking the
  application.
- **SC-007**: Device-detail live reads terminate within their configured bound in 100% of
  timeout tests and never trigger repeated device polling after the request completes.
- **SC-008**: The topology displays every authoritative current-lab device and relationship
  exactly once, and every selectable node resolves to the matching device detail.
- **SC-009**: Automated response and browser inspection finds zero credentials, raw rendered
  configurations, raw workflow stacks, authorization material, or unrestricted local paths.
- **SC-010**: Inspection of all routes and screens finds zero mutation operations or actionable
  mutation controls.
- **SC-011**: Overview, device list/detail, workflow list/detail, topology selection, and all
  loading/empty/error states remain usable at desktop and 375-pixel viewport widths without
  horizontal page overflow.
- **SC-012**: The interface is reachable through documented SSH forwarding while both services
  remain inaccessible through the canonical host's non-loopback interfaces.
- **SC-013**: All accepted Features 001-004 regression and durable-history replay checks pass
  after the feature is added.
- **SC-014**: Repository and runtime inspection finds zero added databases, caches, brokers,
  continuous event consumers, bidirectional live-update services, or generic graph engines.
- **SC-015**: Planning records one Lavish-produced, owner-reviewable operator UX artifact that
  covers all main screens, responsive behavior, and non-happy states before implementation.

## Assumptions

- The target user is a trusted lab operator reaching the canonical host through SSH forwarding;
  an authentication platform is intentionally outside this feature.
- The current lab is small enough for bounded recent-result queries and a deliberately arranged
  topology; large-fleet pagination and automatic graph layout are not required.
- Existing retained Temporal history is the preferred source for workflow visibility, but some
  older executions may lack event or correlation metadata and must show that gap honestly.
- Existing Feature 004 validation can supply bounded read-only live summaries without changing
  device state; if canonical investigation disproves this, live state remains unavailable
  rather than introducing another client.
- Deployment and validation results are retained in current workflow history and/or accepted
  artifact/result models sufficiently to project recent outcomes without a new store; planning
  must document any field-level gaps.
- Polling occurs only while relevant pages are visible and is not intended to provide real-time
  guarantees.
- Feature 005 artifacts and runtime gate remain deferred and are neither displayed as an active
  control path nor changed by this feature.
