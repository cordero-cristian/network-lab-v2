# Deployment Event Contracts

These three UTF-8 JSON v1 events are additive. Unknown fields are rejected, UTC timestamps
serialize with `Z`, and Kafka record keys equal canonical `event_id`. Existing
`network.render.*` contracts are unchanged.

## Request

Topic: `network.deployment.requested`

```json
{
  "event_type": "network.deployment.requested",
  "event_version": 1,
  "event_id": "08660568-3d4c-4901-9a77-8a4fb0e68072",
  "correlation_id": "eaf41a9d-9cb8-4de0-bd68-32bbc47e5030",
  "device_name": "f004-leaf01",
  "requested_at": "2026-09-10T18:00:00Z",
  "source": "cli"
}
```

## Completion

Topic: `network.deployment.completed`

```json
{
  "event_type": "network.deployment.completed",
  "event_version": 1,
  "event_id": "577e85e8-f2ed-4c28-80ca-20d6e78c9df8",
  "correlation_id": "eaf41a9d-9cb8-4de0-bd68-32bbc47e5030",
  "device_name": "f004-leaf01",
  "workflow_id": "deploy-device-config:08660568-3d4c-4901-9a77-8a4fb0e68072",
  "artifact_path": "artifacts/configs/f004-leaf01.cfg",
  "artifact_sha256": "cf3dbb569d2083452c9d9ccf13d5e72668bcf059cba7c27a10e7c7c3b5cf7887",
  "artifact_bytes": 1248,
  "deployed_at": "2026-09-10T18:00:04Z",
  "validation_status": "passed",
  "completed_at": "2026-09-10T18:00:12Z"
}
```

## Failure

Topic: `network.deployment.failed`

```json
{
  "event_type": "network.deployment.failed",
  "event_version": 1,
  "event_id": "06a31ce0-d0e3-41fd-9079-2d52b26f23c3",
  "correlation_id": "eaf41a9d-9cb8-4de0-bd68-32bbc47e5030",
  "device_name": "f004-leaf01",
  "workflow_id": "deploy-device-config:08660568-3d4c-4901-9a77-8a4fb0e68072",
  "failure_stage": "validate",
  "error_type": "validation_failed",
  "error_message": "device state did not match intended invariants",
  "failed_at": "2026-09-10T18:01:34Z",
  "artifact_sha256": "cf3dbb569d2083452c9d9ccf13d5e72668bcf059cba7c27a10e7c7c3b5cf7887",
  "artifact_bytes": 1248,
  "deployed_at": "2026-09-10T18:00:04Z"
}
```

Events never contain credentials, management addresses, raw configuration, device
responses, individual checks, exception text, or stack traces. Physical duplicate result
records may occur after uncertain Kafka delivery; retries reuse one logical event ID and
payload.

Request topic and `event_type` must match exactly. A valid payload on the wrong request
topic is poison, starts no workflow, and is committed only after safe logging.
