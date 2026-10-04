# Research: Read-only Drift and Compliance Detection

## Existing Source Boundaries

### Decision: Compare normalized intent, never rendered artifacts

**Rationale**: `NautobotClient.get_deployment_intent()` returns validated `DeviceIntent` plus the
management target. `expected_state_from_intent()` already turns that intent into the bounded
`ExpectedDeviceState` consumed by Feature 004. This is the shortest authoritative path from
Nautobot to comparison and contains no renderer or artifact dependency.

**Alternatives considered**:

- Parsing the generated configuration was rejected because it makes Jinja output a competing intent
  source and loses normalized source ownership.
- Reading artifact metadata/history was rejected because it describes prior automation evidence,
  not current intended state.
- Adding policy objects in Nautobot was rejected because v1 has a fixed expected-state comparison,
  not a policy system.

### Decision: Preserve Feature 004 deployment validation and add a separate current comparator

**Rationale**: `validation_result()` currently combines deterministic configuration invariants and
convergence-dependent operational invariants into one pass/fail result. Changing it would alter
accepted deployment workflow completion and retry behavior. Feature 007 instead adds a pure current
comparison that consumes the same expected and observed boundaries but returns two explicit results.

**Alternatives considered**:

- Reinterpreting Feature 004 `DeviceValidationResult` was rejected because BGP down currently fails
  deployment validation by design, while Feature 007 must state that it is not configuration drift.
- Replacing historical validation with current drift was rejected because the sources, observation
  times, and meanings differ.

## Native Read Classification

### Decision: Classify existing leaves by semantics, with no second device read

Feature 004 canonical evidence and source verify these native leaves and datatypes:

| Existing leaf | Feature 007 classification | Reason |
|---|---|---|
| Hostname | Configuration | Deterministic configured identity |
| Interface admin state | Configuration | Intended administrative enablement |
| Interface oper state | Operational health | Runtime/link condition |
| Subinterface admin state | Configuration | Intended administrative enablement |
| Subinterface oper state | Operational health | Runtime condition |
| Exact keyed address status, non-null | Configuration presence | Matching response key proves expected address exists |
| Address status value | Operational health | `preferred` is readiness/convergence state |
| Local ASN | Configuration | Deterministic configured value |
| Neighbor peer-AS | Configuration | Deterministic configured value/presence |
| Neighbor session state | Operational health | Runtime protocol state |

**Rationale**: The pinned SR Linux release does not return an `/ip-prefix` leaf for a configured
address. Canonical Feature 004 testing established that the exact `ip-prefix` list key on the
normalized `/status` response proves address identity. A non-null non-`preferred` response therefore
means configured-but-unhealthy, while valid absence means missing expected configuration.

**Alternatives considered**:

- Adding a second config-tree read was rejected because the accepted structured read already proves
  expected address identity and the feature requires one bounded observation.
- Treating `status != preferred` as drift was rejected because it conflates address readiness with
  configuration presence.
- Enumerating parent lists was rejected because that adds unexpected-extra detection and a broader
  response-normalization contract outside v1.

## Models And Aggregation

### Decision: Use explicit typed results rather than generic rules

**Rationale**: Two concrete result types make illegal category/status combinations unrepresentable.
Configuration checks are `match|mismatch`; health checks are `healthy|unhealthy|unavailable`.
Stable category literals cover only hostname, admin state, address presence, ASN/peer-AS,
oper state, address readiness, and BGP session. There is no rule expression, severity, score,
waiver, exception, or evaluator registry.

Configuration aggregation is `in_sync` only when all expected checks match and `drifted` when any
mismatch exists. A source-level failure yields an unavailable observation with a null result. Health
aggregation is healthy when all checks are healthy, degraded when at least one check is unhealthy
or unavailable and at least one is assessable, and unavailable when every health check is
unavailable.

**Alternatives considered**:

- Reusing `ValidationCheck` was rejected because its pass/fail vocabulary cannot represent an
  operational check that is unavailable due to missing expected configuration.
- A common generic compliance-check model was rejected because it weakens the required separation
  and invites policy-framework growth.
- Persisted snapshots/scores were rejected because no history or datastore is required.

## API And Presentation

### Decision: Replace the combined live projection atomically

**Rationale**: Feature 006 currently groups all `DeviceValidationResult` checks into one
`LiveStateSummary(status=passed|failed, mismatch_count=...)`. Keeping that projection alongside the
new results would preserve an ambiguous top-level conclusion and allow the UI to collapse health
into drift. Replace it in the internal API/browser contract with separate two-source observation models.
The existing route, `live=true` trigger, 15-second operation budget, polling behavior, and partial
failure handling remain intact.

No compatibility alias is required: the consumer is the repository's own UI, the value is not
persisted, and both sides will change together. Historical deployment validation remains visible
under its existing explicitly historical label.

**Alternatives considered**:

- Adding a new route was rejected because it could trigger a second read and duplicates device
  detail source handling.
- Retaining `live_state` as an alias was rejected because it perpetuates the semantic error and has
  no concrete external consumer.
- Fleet/list drift badges were rejected because lists and overview must not perform device reads.

## Availability, Timing, And Safety

### Decision: Keep one common observation time, two-source provenance, and existing safety boundaries

**Rationale**: The comparator receives one UTC timestamp after the one-shot read and uses it for
both results. Each API observation reports separate Nautobot-intent and device-read availability,
plus one common request-completion timestamp even when no nested result exists. Intent failure marks
the device source `not_configured` because no read was attempted; device failure preserves healthy
intent provenance while reporting the safe device failure. Valid absent leaves remain domain
evidence. Before classification, Feature 007 validates hostname/admin/oper/status/session leaves as
non-empty bounded strings and ASN leaves as exact integers. A wrong value of the correct type is
valid comparison evidence; any wrong type invalidates the complete current comparison so it cannot
be mislabeled drift or health. Raw payloads, paths beyond stable check keys, exception text, and
credentials are never returned.

The frontend continues to request `live=true` once on route opening, retain that timestamped result,
and use `live=false` for later Nautobot/Temporal refreshes. No workflow, retry loop, subscription,
cache, or background job is introduced.
