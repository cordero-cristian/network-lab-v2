# Data Model: Network Automation Control Plane UI

All API models are strict Pydantic v2 read models. They are transient projections and are never
persisted by Feature 006. Times are UTC RFC 3339 values; durations are non-negative milliseconds.
Unknown external enum values map to explicit `unknown` values rather than passing through.

## Common Models

### SourceAvailability

| Field | Type | Rules |
|---|---|---|
| `source` | enum | `nautobot`, `kafka`, `temporal`, `worker`, `consumer`, `artifact`, `device` |
| `status` | enum | `healthy`, `degraded`, `unavailable`, `unknown` |
| `observed_at` | datetime | Required UTC observation time |
| `duration_ms` | integer or null | `0..120000`; null when no request began |
| `code` | safe enum or null | Allowlisted diagnostic code only |
| `message` | string or null | Static sanitized summary, maximum 160 characters |

### AvailabilityEnvelope[T]

| Field | Type | Rules |
|---|---|---|
| `availability` | `SourceAvailability` | Required |
| `data` | `T` or null | Null only when unavailable/unknown |

### ApiError

| Field | Type | Rules |
|---|---|---|
| `code` | enum | `invalid_request`, `not_found`, `upstream_timeout`, `temporarily_unavailable`, `internal_error` |
| `message` | string | Static safe text, maximum 160 characters |
| `request_id` | string | Server-generated opaque identifier |

## Health Models

### SystemHealthSummary

| Field | Type | Rules |
|---|---|---|
| `overall_status` | enum | `healthy`, `degraded`, `unavailable` |
| `observed_at` | datetime | Aggregate completion time |
| `nautobot` | `SourceAvailability` | Required independent probe |
| `kafka` | `SourceAvailability` | Required independent probe |
| `temporal` | `SourceAvailability` | Required independent probe |
| `worker` | `SourceAvailability` | Temporal task-queue poller evidence |
| `consumer` | `SourceAvailability` | Kafka consumer-group member evidence |
| `device_validation` | `SourceAvailability` | Capability, not a continuous device probe |

State rule: `healthy` requires all five control-plane components healthy. Any available facts plus
one non-healthy component yields `degraded`. No observable authoritative control-plane source
yields `unavailable`.

## Device Models

### DeviceSummary

| Field | Type | Authority |
|---|---|---|
| `name` | device name | Nautobot Device |
| `role` | string or null | Nautobot Role display |
| `platform` | string or null | Nautobot Platform network driver/display |
| `location` | string or null | Nautobot Location display |
| `management_address` | IPv4 or null | Nautobot Device primary IPv4 relationship |
| `inventory_status` | string or null | Nautobot Device status display |
| `last_deployment` | `DeploymentSummary` or null | Latest retained matching Temporal deployment workflow |
| `validation_status` | enum | Latest retained deployment outcome: `passed`, `failed`, `unavailable`, `unknown` |
| `observed_at` | datetime | Projection time |

### IntendedStateSummary

| Field | Type | Rules |
|---|---|---|
| `hostname` | device name | Existing `DeviceIntent.name` |
| `loopback` | address or null | Existing loopback intent |
| `routed_interfaces` | tuple of `IntendedInterface` | Sorted by natural interface name |
| `bgp_local_asn` | integer or null | Existing BGP intent |
| `bgp_neighbors` | tuple of `IntendedBgpNeighbor` | Sorted by address |

### ArtifactSummary

| Field | Type | Rules |
|---|---|---|
| `relative_path` | string | Relative to approved artifact root; no traversal |
| `sha256` | 64 lowercase hex characters or null | From retained artifact identity |
| `byte_count` | integer or null | `0..1_048_576` |
| `available` | boolean | Metadata-only bounded existence check |

### LiveStateSummary

| Field | Type | Rules |
|---|---|---|
| `status` | enum | `passed`, `failed`, `unavailable` |
| `hostname` | `ValidationCheck` or null | Existing exact check when available |
| `interfaces` | tuple of grouped `ValidationCheck` | Existing expected interfaces only |
| `bgp` | tuple of grouped `ValidationCheck` | Existing expected ASN/neighbors only |
| `mismatch_count` | integer | Count of existing failed checks |
| `validated_at` | datetime or null | Existing validation observation time |

### DeviceDetail

| Field | Type | Rules |
|---|---|---|
| `summary` | `DeviceSummary` | Required when device exists |
| `intent` | `AvailabilityEnvelope[IntendedStateSummary]` | Nautobot normalized intent |
| `latest_artifact` | `AvailabilityEnvelope[ArtifactSummary]` | Retained Temporal history/artifact root |
| `latest_deployment` | `AvailabilityEnvelope[DeploymentSummary]` | Retained Temporal history |
| `historical_validation` | `AvailabilityEnvelope[ValidationSummary]` | Existing terminal workflow result/history |
| `live_state` | `AvailabilityEnvelope[LiveStateSummary]` | Null unless explicitly requested/available |

## Workflow And Deployment Models

### WorkflowSummary

| Field | Type | Rules |
|---|---|---|
| `workflow_id` | string | Accepted render/deploy prefix plus UUID only |
| `run_id` | UUID | Temporal run identity |
| `kind` | enum | `render`, `deployment` |
| `event_id` | UUID or null | Decoded start input; workflow-ID UUID used only as a consistency check |
| `correlation_id` | UUID or null | Decoded start input only |
| `device_name` | device name or null | Decoded start input only |
| `execution_status` | enum | Temporal lifecycle state |
| `outcome` | enum | Decoded business result or execution-level outcome |
| `started_at` | datetime | Temporal visibility/start event |
| `completed_at` | datetime or null | Temporal close time |
| `duration_ms` | integer or null | Completed minus started; current elapsed for detail only |
| `current_stage` | stage enum or null | Latest safely mapped stage |
| `failure_category` | safe enum or null | Existing allowlisted terminal category |
| `data_status` | enum | `complete`, `partial`, `unavailable` |

### ExecutionStage

| Field | Type | Rules |
|---|---|---|
| `sequence` | integer | Stable display order beginning at one |
| `key` | enum/string | Known stage key or `unknown:<safe activity type>` |
| `label` | string | Allowlisted display label |
| `status` | enum | `completed`, `running`, `failed`, `not_reached`, `unknown` |
| `scheduled_at` | datetime or null | History event time |
| `started_at` | datetime or null | History event time |
| `completed_at` | datetime or null | History event time |
| `duration_ms` | integer or null | Non-negative |
| `attempts` | integer or null | Maximum observed safe attempt, `1..100` |
| `failure_category` | safe enum or null | Existing mapped category only |
| `failure_message` | string or null | Static/sanitized, maximum 160 characters |

### ValidationSummary

| Field | Type | Rules |
|---|---|---|
| `status` | enum | `passed`, `failed`, `unavailable`, `unknown` |
| `validated_at` | datetime or null | Existing result/history timestamp |
| `checks_total` | integer or null | Existing retained check count when decoded |
| `checks_failed` | integer or null | Existing failed-check count when decoded |

### WorkflowDetail

| Field | Type | Rules |
|---|---|---|
| `summary` | `WorkflowSummary` | Required |
| `stages` | tuple of `ExecutionStage` | Ordered, maximum 64 |
| `artifact` | `ArtifactSummary` or null | Metadata only |
| `deployment` | `DeploymentSummary` or null | Deployment workflows only |
| `validation` | `ValidationSummary` or null | Deployment workflows only |
| `failure` | `SafeFailureSummary` or null | No stack/raw exception |
| `history_status` | `SourceAvailability` | Decode/freshness state |

### DeploymentSummary

| Field | Type | Rules |
|---|---|---|
| `workflow_id` | string | Deployment prefix only |
| `run_id` | UUID | Temporal run identity |
| `device_name` | device name or null | Decoded start input |
| `status` | enum | `queued`, `preparing`, `deploying`, `validating`, `succeeded`, `failed`, `unknown` |
| `artifact` | `ArtifactSummary` or null | Existing workflow history/outcome |
| `deployed_at` | datetime or null | Existing `DeploymentResult`/terminal result |
| `completed_at` | datetime or null | Temporal close time |
| `duration_ms` | integer or null | Non-negative |
| `validation_status` | enum | `passed`, `failed`, `unavailable`, `unknown` |
| `failure_stage` | enum or null | `prepare`, `deploy`, `validate`, `publish`, `execution` |
| `failure_category` | safe enum or null | Existing allowlisted category |

`DeploymentDetail` is a deployment-constrained `WorkflowDetail`; it does not duplicate history.

## Topology Models

### TopologyNode

| Field | Type | Rules |
|---|---|---|
| `id` | device name | Stable current-lab key |
| `label` | string | Device name |
| `role` | string or null | Nautobot |
| `platform` | string or null | Nautobot |
| `status` | enum | `healthy`, `degraded`, `failed`, `unknown` from supported retained evidence |
| `status_source` | enum or null | `inventory`, `deployment`, `validation` |

### TopologyLink

| Field | Type | Rules |
|---|---|---|
| `id` | string | Deterministic hash/key of type and sorted endpoints |
| `kind` | enum | `physical`, `bgp` |
| `source_device` | device name | Lexically sorted endpoint |
| `source_interface` | interface name or null | Required for physical, available for BGP ownership |
| `target_device` | device name | Opposite endpoint |
| `target_interface` | interface name or null | Required for physical, available for BGP ownership |
| `status` | enum | `healthy`, `degraded`, `failed`, `unknown`; unknown unless evidence supports link state |

Physical links require Nautobot endpoint data. BGP links require an exact BGP neighbor address to
resolve to one IP assigned to another listed device. Subnet overlap alone never creates a link.

### TopologyGraph

| Field | Type | Rules |
|---|---|---|
| `nodes` | tuple of `TopologyNode` | Maximum 100; sorted by role/name |
| `links` | tuple of `TopologyLink` | Maximum 200; deduplicated and sorted |
| `observed_at` | datetime | Projection time |
| `availability` | `SourceAvailability` | Nautobot/source state |

## Relationships And State

- A Device may join zero or one latest retained Deployment by exact normalized device name.
- A Workflow has one Temporal run identity; detail requests pin both workflow ID and run ID.
- A Deployment is a projection of one deployment Workflow, never separately persisted.
- Workflow stages transition only from history evidence; `not_reached` is presentation state for
  known later stages after a terminal failure.
- A TopologyLink references exactly two existing TopologyNodes.
- Availability is per source/section and never converted into false empty data.
