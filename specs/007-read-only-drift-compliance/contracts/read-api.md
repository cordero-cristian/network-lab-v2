# Feature 007 Read API Delta

This contract narrows the Feature 006 [read API](../../006-network-control-plane-ui/contracts/read-api.md).
All existing route, method, validation, no-store, error, and browser-boundary rules remain in force
unless explicitly changed here.

## Device Detail

### `GET /api/devices/{device_name}`

Query remains:

- `live`: optional boolean, default false.

`DeviceDetail` replaces:

```text
live_state: AvailabilityEnvelope[LiveStateSummary]
```

with:

```text
configuration_drift: ConfigurationDriftObservation
operational_health: OperationalHealthObservation
```

No compatibility `live_state` alias is returned.

### `live=false`

- Performs no device read.
- Returns both observations with operator-visible status `unavailable`, the current Nautobot intent
  availability, device status `unknown`/code `not_configured`, one shared completion timestamp, and
  null nested results.
- Preserves independent intent, inventory, artifact, deployment, and historical-validation data.

### `live=true`

- Reads normalized Nautobot intent through the existing exact-device path.
- Performs exactly one existing structured SR Linux read within the accepted 15-second operation
  budget.
- Produces both observations from the same expected state, observed mapping, and UTC timestamp. Both
  source fields are healthy and nested results are present.
- A device timeout/unreachable/authentication/invalid-response outcome makes both observations
  unavailable with healthy intent provenance, safe unavailable device provenance, one shared
  completion timestamp, and null results; other device-detail sections remain available.
- An unavailable/invalid Nautobot intent prevents the live device comparison rather than reading a
  device without authoritative expected state. Both observations report unavailable intent,
  device `unknown`/`not_configured`, one shared completion timestamp, and null results.

## Response Models

### ConfigurationDriftResult

```text
device_name
status: in_sync | drifted
checks[]: ConfigurationCheck
matches
mismatches
observed_at
```

### OperationalHealthResult

```text
device_name
status: healthy | degraded | unavailable
checks[]: OperationalHealthCheck
healthy_count
unhealthy_count
unavailable_count
observed_at
```

### ComparisonSources

```text
intent: SourceAvailability
device: SourceAvailability
```

The observation status, not `ConfigurationDriftResult`, represents source-level `unavailable`.
This avoids constructing an empty comparison result when intent or live evidence was not obtained.
Both observation models always include both source states and a common `observed_at`, including
failure and not-requested cases.

## Presentation Contract

- Device detail displays Configuration Drift and Operational Health as separate peer sections.
- Neither section supplies an overall status for the other.
- Each section displays aggregate status, counts, per-check expected/observed evidence, source
  availability, and observation time.
- Intended State remains Nautobot-labeled. Historical Validation remains explicitly historical
  deployment evidence and is not renamed current compliance.
- Opening the route issues one `live=true` request. Scheduled detail refreshes continue to use
  `live=false` and retain the original timestamped current-comparison observations without another
  device read.
- No mutation or policy-management control is added.
