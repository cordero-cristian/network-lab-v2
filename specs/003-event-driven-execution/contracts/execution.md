# Execution Contracts

## Configured Names

| Purpose | Default |
|---|---|
| Request topic | `network.render.requested` |
| Completion topic | `network.render.completed` |
| Failure topic | `network.render.failed` |
| Consumer group | `network-automation-render-consumer` |
| Temporal task queue | `network-automation` |

Only the values are configurable; the three event model types remain fixed.

## Developer Command

```text
uv run network-render-request DEVICE
```

Success waits for request broker delivery, prints `event_id`, `correlation_id`, and
`workflow_id`, and returns 0. Failure prints one credential-safe error to stderr and
returns nonzero. It does not start Temporal directly or contact Nautobot/devices.

## Consumer Contract

```text
validated RenderRequested
  -> RenderDeviceConfigRequest
  -> Client.start_workflow(
       RenderDeviceConfigWorkflow.run,
       id="render-device-config:<event_id>",
       task_queue="network-automation",
        id_conflict_policy=WorkflowIDConflictPolicy.USE_EXISTING,
        id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE)
  -> synchronous offset commit
```

`USE_EXISTING` is the running-execution conflict policy and returns the existing handle.
Separately, `REJECT_DUPLICATE` is the closed-execution reuse policy.
`WorkflowAlreadyStartedError` for a retained closed ID means the same logical request
was already durably accepted and also permits commit. Other start failures do not permit
commit; the exact partition position is sought again before later records are handled.
The same seek/retry rule applies to any synchronous commit failure. Reuse rejection is
bounded by the existing Temporal namespace retention; replay after expiry is out of scope.

Malformed messages start no workflow and are synchronously committed only after a
safe validation log containing topic, partition, offset, parseable event ID, and an
error category where available. It does not log arbitrary raw payloads or secrets by
default. The consumer never imports/calls Nautobot, rendering, artifact, or
result-producer behavior.

## Workflow Contract

Input:

```text
RenderDeviceConfigRequest(event_id, correlation_id, device_name)
```

Ordering:

```text
render_device_artifact
  -> RenderCompleted -> publish_render_result -> return completion
  OR
  -> classified failure -> RenderFailed -> publish_render_result -> return failure
```

Workflow code may use only Temporal-safe UUID/time facilities and deterministic model
construction. It performs no external or filesystem operation.

## Activity Contracts

```text
render_device_artifact(RenderDeviceConfigRequest) -> ArtifactMetadata
publish_render_result(RenderCompleted | RenderFailed) -> None
```

The first calls Feature 002 `render_device()` with default `artifacts/configs` and
returns no intent/configuration payload. The second selects only completion/failure
topic and waits for delivery. Publication retry cannot call the first activity.

## Runtime Commands

```text
uv run network-worker
uv run network-event-consumer
docker compose --profile automation up -d --wait automation-worker event-consumer
```

Both processes use the same package/image and no published port. Missing dependencies
produce visible nonzero startup or unhealthy service state. Graceful termination closes
the Temporal worker or Kafka consumer and does not acknowledge an unaccepted request.
