# Implementation Plan: Read-only Drift and Compliance Detection

**Branch**: `007-read-only-drift-compliance` | **Date**: 2026-09-22 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/007-read-only-drift-compliance/spec.md`

**Status**: IMPLEMENTED AND CANONICALLY ACCEPTED ON 2026-09-23

## Summary

Split the existing one-shot device validation projection into explicit current configuration-drift
and operational-health results. Nautobot's normalized `DeviceIntent` remains the only expected-state
source. The existing Feature 004 `ExpectedDeviceState` conversion and one structured SR Linux read
remain the live evidence path. A new pure comparison module classifies configuration and operational
leaves independently and returns strict transient Pydantic models to the existing Feature 006 device
detail API and UI. The feature does not alter Feature 004 deployment-time validation, enumerate extra
configuration, persist results, poll devices, or remediate findings.

## Technical Context

**Language/Version**: Existing CPython 3.12.13 package; existing React 19 and TypeScript 5 frontend

**Primary Dependencies**: Existing Pydantic v2, FastAPI, pyGNMI, React, and Feature 002/004/006 boundaries; no new dependency

**Storage**: None; comparison results are request-scoped transient projections

**Testing**: Existing pytest/pytest-asyncio and Vitest/React Testing Library; real read-only canonical Nautobot, API, UI, and SR Linux acceptance

**Target Platform**: Existing canonical Ubuntu 24.04.4 x86-64 lab runtime and desktop/375-pixel browser viewports

**Project Type**: Existing typed Python package plus existing static frontend application

**Performance Goals**: Preserve one on-demand live device operation within the accepted 15-second budget; pure comparison adds no external calls; no overview/list latency increase

**Constraints**: Read-only; expected-state-only; no generic policy framework; no datastore; no continuous telemetry; no artifact-derived intent; no remediation; separate drift and health; BGP down is not drift

**Scale/Scope**: One selected device per explicit detail request, at most 64 existing bounded native checks, current small SR Linux lab, one existing UI route changed

## Constitution Check

*GATE: Passed before research and rechecked after design.*

| Principle | Pre-Design Gate | Post-Design Evidence |
|---|---|---|
| Explicit Architectural Ownership | PASS: Nautobot remains intended-state authority; no Kafka or Temporal role is added; device access remains behind Feature 004. | `DeviceIntent` is converted directly to accepted expected state, one existing SR Linux read supplies evidence, and strict comparison/API models preserve boundaries. |
| Small, Explicit Implementation | PASS: one pure comparison module and narrow changes to the existing detail API/UI are sufficient. | No service, policy engine, driver abstraction, compatibility layer, datastore, workflow, or generic rule framework is designed. |
| Reproducible Local Infrastructure | PASS: no infrastructure or dependency addition is needed. | Existing API/UI runtime, settings, loopback ports, and device-access overlay are reused unchanged. |
| Evidence Over Process Status | PASS: unit tests cover separation rules and acceptance uses real read-only intent/device evidence. | Contracts define exact leaves, result states, source failures, BGP-down behavior, address presence/readiness, and non-mutating canonical validation. |
| Spec-Driven, Bounded Delivery | PASS: Feature 007 has independent specification and planning artifacts and an explicit architecture stop. | Research, data model, contracts, and quickstart are complete; no tasks or implementation are created before owner review. |

No constitution violation requires complexity justification. Post-design review remains PASS.

## Design Decisions

### Domain Boundary

1. Add `devices/comparison.py` as a pure domain module containing the explicit comparison models
   and comparison function. It accepts `ExpectedDeviceState`, normalized observed leaf values, and
   one UTC observation time. It performs no I/O and imports no API, workflow, renderer, or activity.
2. Reuse `expected_state_from_intent()` so Feature 002 normalized intent, not rendered configuration,
   supplies expected values. Do not broaden `ExpectedDeviceState` in v1.
3. Leave Feature 004 `validation_result()` and its deployment workflow behavior unchanged. That
   historical result proves accepted post-deployment invariants; Feature 007 supplies a distinct
   current read projection.
4. Keep comparison models transient and outside `events.models`; they are neither durable activity
   payloads nor events.

### Classification Rules

The normative matrix is [contracts/comparison.md](contracts/comparison.md). Configuration drift
uses hostname, interface/subinterface admin state, exact expected address presence, local ASN, and
expected neighbor peer-AS. Operational health uses interface/subinterface oper state, address
`preferred`, and neighbor `established`.

The exact keyed address `/status` response is deliberately interpreted twice without duplicating
the read: non-null proves expected-address presence for configuration, while its value determines
readiness health. Therefore a non-`preferred` value is not drift. A null value means the expected
address is absent, so configuration mismatches and the corresponding health check is unavailable.

Configuration checks use only `match|mismatch`. Health checks use only
`healthy|unhealthy|unavailable`. BGP session state and interface oper state never participate in
configuration aggregation. No extra device object is queried or classified.

### API And UI Contract

The normative API delta is [contracts/read-api.md](contracts/read-api.md). Replace the ambiguous
current `live_state` member of `DeviceDetail` with sibling `configuration_drift` and
`operational_health` observation models. Each carries separate intent/device source availability;
both derive from the same one-shot read and timestamp.
This is an internal browser/API contract updated atomically; no backward-compatibility alias is
added because there is no external or persisted consumer and retaining the combined field would
contradict the required separation.

The existing `GET /api/devices/{device_name}?live=true` trigger, outer request bound, no-store
policy, safe availability handling, and frontend one-shot behavior remain unchanged. `live=false`
returns both new observations as `unavailable` with device source `not_configured` without a device
call. Device detail replaces one
Live State panel with separate Configuration Drift and Operational Health panels. Intended state
and historical deployment validation remain separately labeled.

### Failure And Safety Rules

- Failure to obtain normalized Nautobot intent or the live read yields unavailable observations
  with null nested results and explicit state for both sources, not empty checks or a false domain
  conclusion. Intent failure records that no device read was attempted.
- Valid absence of an expected configuration leaf is comparison evidence and produces mismatch;
  malformed/ambiguous device responses remain boundary failures and expose no raw payload.
- The comparison boundary validates canonical leaf types before classifying any check. Wrong-type,
  empty, or unbounded leaf values invalidate the complete current comparison; correct-type unequal
  values remain legitimate drift or unhealthy evidence.
- Per-object operational absence is `unavailable`; aggregate health is degraded when any other
  health check remains assessable and unavailable only when none are assessable.
- Existing static safe messages, credentials containment, 15-second live-operation budget, and one
  read per explicit route opening are preserved.

## Implementation Sequence And Review Gate

1. After explicit owner approval, begin with comparison-model and pure-rule tests.
2. Add the pure comparator without changing Feature 004 validation behavior.
3. Replace the API read models and map the existing one-shot live read into the two observations.
4. Update the existing device-detail frontend and runtime contract validators atomically.
5. Run Python and frontend regression suites, then read-only canonical acceptance and responsive
   browser/security inspection.

The owner approved proceeding to task generation on 2026-09-22 and separately approved
implementation on 2026-09-22. Implementation and canonical acceptance completed on 2026-09-23.

## Project Structure

### Documentation (this feature)

```text
specs/007-read-only-drift-compliance/
|-- spec.md
|-- plan.md
|-- research.md
|-- data-model.md
|-- quickstart.md
|-- contracts/
|   |-- comparison.md
|   `-- read-api.md
`-- checklists/
    `-- requirements.md
```

### Source Code (repository root)

```text
src/network_automation/
|-- devices/
|   |-- comparison.py                  # new pure models and comparison logic
|   |-- validation.py                  # unchanged Feature 004 behavior
|   |-- read_state.py                  # existing one-shot read wrapper
|   `-- srlinux.py                     # existing native paths/client
`-- api/
    |-- models.py                      # replace combined live projection
    `-- devices.py                     # map one observation into two results

ui/src/
|-- api/
|   |-- types.ts                       # explicit result contracts
|   `-- client.ts                      # runtime response checks
`-- pages/
    `-- DeviceDetailPage.tsx           # separate drift and health panels

tests/
|-- unit/
|   |-- test_device_comparison.py
|   `-- test_api_devices.py
`-- integration/
    `-- test_control_plane_api.py
```

**Structure Decision**: Extend only the existing Python package and Feature 006 frontend. One pure
comparison module prevents API presentation concerns from entering device-domain logic while
avoiding a service, repository, policy, or plugin layer.

## Complexity Tracking

No constitution violations are proposed.
