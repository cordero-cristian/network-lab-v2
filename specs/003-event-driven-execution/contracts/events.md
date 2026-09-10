# Event Contracts

All payloads are UTF-8 JSON objects, reject unknown fields, and use UTC `Z` timestamps.
The examples are directional; UUIDs and times are unique per logical event.

## Request Topic

Topic: `network.render.requested`

```json
{
  "event_type": "network.render.requested",
  "event_version": 1,
  "event_id": "77ee1844-cd3a-4c45-8de7-3dd76fc7da2d",
  "correlation_id": "fb2b2b84-a0e2-45c1-a870-59c636c34a80",
  "device_name": "leaf01",
  "requested_at": "2026-09-09T18:00:00Z",
  "source": "cli"
}
```

## Completion Topic

Topic: `network.render.completed`

```json
{
  "event_type": "network.render.completed",
  "event_version": 1,
  "event_id": "895c05a7-8486-48b1-9a7b-0bce533a92b8",
  "correlation_id": "fb2b2b84-a0e2-45c1-a870-59c636c34a80",
  "device_name": "leaf01",
  "workflow_id": "render-device-config:77ee1844-cd3a-4c45-8de7-3dd76fc7da2d",
  "artifact_path": "artifacts/configs/leaf01.cfg",
  "completed_at": "2026-09-09T18:00:03Z"
}
```

## Failure Topic

Topic: `network.render.failed`

```json
{
  "event_type": "network.render.failed",
  "event_version": 1,
  "event_id": "dd26263d-4701-47be-943c-8b843f9e7881",
  "correlation_id": "fb2b2b84-a0e2-45c1-a870-59c636c34a80",
  "device_name": "leaf01",
  "workflow_id": "render-device-config:77ee1844-cd3a-4c45-8de7-3dd76fc7da2d",
  "error_type": "intent_invalid",
  "error_message": "device intent validation failed",
  "failed_at": "2026-09-09T18:00:03Z"
}
```

Allowed `error_type` values are `nautobot_unavailable`, `artifact_unavailable`,
`intent_invalid`, `nautobot_rejected`, `unsupported_platform`, `render_invalid`, and
`internal_error`.

## Serialization And Safety

- UUIDs serialize in canonical hyphenated form.
- Timestamps must have zero UTC offset and serialize with `Z`.
- Result correlation/device values equal the accepted request.
- Completion artifact path equals `artifacts/configs/<device_name>.cfg`.
- Events contain no credentials, raw requests/responses, configuration text, or stack traces.
- Kafka record key is the event's canonical UUID `event_id` string.
- Broker retries reuse the same result payload and event ID. Duplicate physical
  records are possible under at-least-once delivery and represent one logical event.
