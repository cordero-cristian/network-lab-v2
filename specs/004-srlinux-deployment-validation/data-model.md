# Data Model: SR Linux Deployment And Operational Validation

All models are frozen Pydantic v2 boundaries with `extra="forbid"`. Existing Feature 003
render models remain compatible.

## Shared Scalars

- IDs are UUIDs; timestamps are timezone-aware UTC and serialize with `Z`.
- Device names reuse Feature 002's safe `DeviceName` constraint.
- Artifact paths equal `artifacts/configs/<device_name>.cfg`.
- SHA-256 is exactly 64 lowercase hexadecimal characters; byte count is 1 through 1 MiB.
- Management targets are normalized IPv4 host addresses. Port is 1 through 65535.
- Expected/observed/check messages are safe bounded scalars, never raw config/responses.
- Validation results contain at most 64 checks; safe messages are at most 256 characters.

## Additive Events

### DeploymentRequested

| Field | Type | Rule |
|---|---|---|
| `event_type` | literal | `network.deployment.requested` |
| `event_version` | literal integer | `1` |
| `event_id` | UUID | Logical deployment identity |
| `correlation_id` | UUID | Propagated unchanged |
| `device_name` | DeviceName | Exact Nautobot target |
| `requested_at` | UTC timestamp | Caller generated |
| `source` | bounded text | Diagnostic only |

### DeploymentCompleted

| Field | Type | Rule |
|---|---|---|
| `event_type` | literal | `network.deployment.completed` |
| `event_version` | literal integer | `1` |
| `event_id` | UUID | Stable across publication retries |
| `correlation_id` | UUID | Original request value |
| `device_name` | DeviceName | Original request value |
| `workflow_id` | bounded text | `deploy-device-config:<request event_id>` |
| `artifact_path` | artifact path | Device-bound deterministic path |
| `artifact_sha256` | SHA-256 | Exact deployed bytes |
| `artifact_bytes` | integer | Exact deployed byte count |
| `deployed_at` | UTC timestamp | Recorded deployment completion |
| `validation_status` | literal | `passed` |
| `completed_at` | UTC timestamp | Workflow-safe result time |

### DeploymentFailed

| Field | Type | Rule |
|---|---|---|
| `event_type` | literal | `network.deployment.failed` |
| `event_version` | literal integer | `1` |
| `event_id` | UUID | Stable across publication retries |
| `correlation_id` | UUID | Original request value |
| `device_name` | DeviceName | Original request value |
| `workflow_id` | bounded text | Deterministic deployment workflow ID |
| `failure_stage` | literal | `prepare`, `deploy`, or `validate` |
| `error_type` | stable literal | Category from the execution contract |
| `error_message` | safe text | Static/bounded; no raw exception |
| `failed_at` | UTC timestamp | Workflow-safe result time |
| `artifact_sha256` | SHA-256 or null | Required for deploy/validate; null for prepare |
| `artifact_bytes` | integer or null | Required for deploy/validate; null for prepare |
| `deployed_at` | UTC timestamp or null | Required only for validate failure after Set |

## Durable Activity Payloads

### DeployDeviceConfigRequest

Contains literal `operation="deploy"` plus request `event_id`, `correlation_id`, and
`device_name`. The discriminator makes its Temporal union with the existing render input
unambiguous. Derived workflow ID is `deploy-device-config:<event_id>`. No credentials,
address, artifact, or intent enters through Kafka.

### ArtifactIdentity

Contains `device_name`, `artifact_path`, `sha256`, and `byte_count`. It identifies bytes but
does not contain them.

### DeploymentTarget

Contains `device_name`, normalized `management_address`, `platform="nokia_srl"`, gNMI port,
and TLS mode `insecure`. Credentials remain worker-local settings and are never fields.

### ExpectedDeviceState

Contains requested hostname, loopback name/prefix, ordered routed interface name/prefix
pairs with explicit `require_oper_up` booleans, local ASN, and ordered BGP neighbor
address/remote-AS pairs. The Feature 004 topology requires oper-up for every modeled
interface. It is validated intent needed for comparison, not rendered configuration.

### PreparedDeployment

Contains `ArtifactIdentity`, `DeploymentTarget`, and `ExpectedDeviceState`. Cross-field
validation requires every nested device name to equal the workflow request target.

### DeploymentResult

Contains artifact identity, target device name/address, and UTC `deployed_at`. It confirms
only that Set returned success and cannot represent overall workflow success.

### ValidationCheck

| Field | Type | Rule |
|---|---|---|
| `name` | stable bounded string | Unique check identity |
| `status` | literal | `passed` or `failed` |
| `expected` | `str`, `int`, or `bool` | Strings are 1 through 128 chars |
| `observed` | same scalar types or null | Null only when absent |
| `message` | bounded safe text or null | Static context only |

### DeviceValidationResult

Contains `device_name`, overall `status` (`passed` or `failed`), 1 through 64 uniquely named
checks, and UTC `validated_at`. Overall status is `passed` only when every check passed.

## Stable Failure Categories

Preparation: `nautobot_unavailable`, `nautobot_rejected`, `intent_invalid`,
`unsupported_platform`, `management_address_invalid`, `artifact_unavailable`,
`artifact_invalid`, `artifact_mismatch`, `device_settings_missing`.

Deployment: `device_unavailable`, `device_authentication_failed`, `device_identity_mismatch`,
`device_platform_mismatch`, `configuration_rejected`, `artifact_mismatch`, `internal_error`.

Validation: `device_unavailable`, `device_authentication_failed`, `device_state_invalid`,
`validation_not_converged`, `validation_failed`, `internal_error`.

## State Transitions

```text
Deployment request uncommitted
  -> invalid -> safe poison log -> offset committed
  -> valid -> start/attach deploy-device-config:<event_id> -> offset committed

Deployment workflow
  -> prepare (read intent + render/write/digest/bind) retries
       -> permanent/exhausted -> DeploymentFailed(prepare)
  -> deploy retries -> permanent/exhausted -> DeploymentFailed(deploy)
  -> validate retries only itself
       -> all checks pass -> DeploymentCompleted
       -> permanent/exhausted mismatch -> DeploymentFailed(validate)
  -> outcome publication exhausted -> workflow visibly failed
```

Deployment request topic and `event_type` must match exactly or the record is poison.
Duplicate records use the accepted Temporal conflict/reuse policies. Digest mismatch on a
later deployment attempt transitions to permanent failure before another mutation.
