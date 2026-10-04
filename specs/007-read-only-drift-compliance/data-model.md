# Data Model: Read-only Drift and Compliance Detection

All Feature 007 comparison models are strict, frozen Pydantic v2 models with forbidden extra fields.
They are transient domain projections and are never persisted or used as events/activity payloads.
Times are timezone-aware UTC. Expected and observed values are bounded safe scalars only.

## Configuration Models

### ConfigurationCheck

| Field | Type | Rules |
|---|---|---|
| `key` | bounded string | Unique stable semantic identity |
| `category` | literal | `hostname`, `interface_admin`, `subinterface_admin`, `address_presence`, `bgp_local_asn`, `bgp_peer_as` |
| `status` | literal | `match` or `mismatch` |
| `expected` | safe scalar | Expected hostname/state/value or `true` for address presence |
| `observed` | safe scalar or null | Exact normalized value; address presence is boolean |
| `message` | bounded safe text or null | Static explanation only on mismatch |

Stable key forms:

- `system.hostname`
- `interface.<name>.admin_state`
- `subinterface.<name>.0.admin_state`
- `address.<name>.<prefix>.presence`
- `routing.bgp.local_asn`
- `routing.bgp.neighbor.<address>.peer_as`

### ConfigurationDriftResult

| Field | Type | Rules |
|---|---|---|
| `device_name` | device name | Must equal expected-state device |
| `status` | literal | `in_sync` iff every check matches; otherwise `drifted` |
| `checks` | tuple of `ConfigurationCheck` | Unique keys; expected-state-only; bounded by existing native-read limit |
| `matches` | integer | Derived count |
| `mismatches` | integer | Derived count; consistent with status |
| `observed_at` | UTC datetime | Shared comparison observation time |

Source-level inability to compare is represented by the operator-facing observation with a null
result, not by a third check status or an empty check set.

## Operational Models

### OperationalHealthCheck

| Field | Type | Rules |
|---|---|---|
| `key` | bounded string | Unique stable semantic identity |
| `category` | literal | `interface_oper`, `subinterface_oper`, `address_readiness`, `bgp_session` |
| `status` | literal | `healthy`, `unhealthy`, or `unavailable` |
| `expected` | safe scalar | Desired `up`, `preferred`, or `established` value |
| `observed` | safe scalar or null | Exact normalized observed value when available |
| `message` | bounded safe text or null | Static explanation for non-healthy state |

Stable key forms:

- `interface.<name>.oper_state`
- `subinterface.<name>.0.oper_state`
- `address.<name>.<prefix>.readiness`
- `routing.bgp.neighbor.<address>.session_state`

### OperationalHealthResult

| Field | Type | Rules |
|---|---|---|
| `device_name` | device name | Must equal expected-state device |
| `status` | literal | `healthy`, `degraded`, or `unavailable` |
| `checks` | tuple of `OperationalHealthCheck` | Unique keys; expected objects only |
| `healthy_count` | integer | Derived count |
| `unhealthy_count` | integer | Derived count |
| `unavailable_count` | integer | Derived count |
| `observed_at` | UTC datetime | Same timestamp as configuration result |

Aggregate transition rules:

```text
all checks healthy                         -> healthy
at least one assessable + any non-healthy  -> degraded
all checks unavailable                     -> unavailable
```

## Comparison Bundle

### DeviceComparison

| Field | Type | Rules |
|---|---|---|
| `device_name` | device name | Exact expected device |
| `configuration` | `ConfigurationDriftResult` | Required after successful source reads |
| `operational` | `OperationalHealthResult` | Required after successful source reads |
| `observed_at` | UTC datetime | Equal to both nested result timestamps |

This internal return type enforces that both conclusions use one expected state, one observed-state
mapping, and one observation time.

## API Observation Models

### ComparisonSources

| Field | Type | Rules |
|---|---|---|
| `intent` | `SourceAvailability` | Nautobot normalization outcome |
| `device` | `SourceAvailability` | Device-read outcome or explicit `not_configured` when not attempted |

### ConfigurationDriftObservation

| Field | Type | Rules |
|---|---|---|
| `status` | literal | `in_sync`, `drifted`, or `unavailable` |
| `sources` | `ComparisonSources` | Both source states are always present |
| `result` | `ConfigurationDriftResult` or null | Required for `in_sync|drifted`; null for source-level unavailable |
| `observed_at` | UTC datetime | Common comparison completion time |

### OperationalHealthObservation

| Field | Type | Rules |
|---|---|---|
| `status` | literal | `healthy`, `degraded`, or `unavailable` |
| `sources` | `ComparisonSources` | Both source states are always present |
| `result` | `OperationalHealthResult` or null | Required after a successful read, including all-checks-unavailable; null for source failure |
| `observed_at` | UTC datetime | Equal to the sibling configuration observation timestamp |

For successful comparison, both sources are healthy and both nested results share the two
observation models' timestamp. On intent failure, intent is unavailable and device is
`unknown/not_configured` because no read occurred. On device failure, intent remains healthy and
device is unavailable. `live=false` reports the available intent state and device
`unknown/not_configured`; both nested results are null.

## Relationships And Invariants

- One normalized `DeviceIntent` produces one `ExpectedDeviceState`; one expected state and one
  observed mapping produce one `DeviceComparison`.
- Hostname, admin, local ASN, and peer-AS leaves create configuration checks only.
- Oper state and BGP session leaves create health checks only.
- One exact address-status leaf creates address-presence configuration evidence and address-readiness
  health evidence without another read.
- A null address status produces `address_presence=mismatch` and `address_readiness=unavailable`.
- A non-null non-`preferred` address status produces `address_presence=match` and
  `address_readiness=unhealthy`.
- Extra observed configuration cannot produce a check because read paths are generated only from
  expected state.
- Before any checks are constructed, hostname/admin/oper/address-status/session values must be
  non-empty strings of at most 128 characters and local/peer ASNs must be exact integers. Any type/shape violation
  invalidates the whole `DeviceComparison`; a correct-type unequal value remains drift/unhealthy.
- Existing Feature 004 `ValidationCheck` and `DeviceValidationResult` remain unchanged and are not
  aliases for these models.
