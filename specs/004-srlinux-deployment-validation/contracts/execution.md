# Deployment Execution Contract

## Configured Names

| Purpose | Default |
|---|---|
| Deployment request topic | `network.deployment.requested` |
| Deployment completion topic | `network.deployment.completed` |
| Deployment failure topic | `network.deployment.failed` |
| Existing consumer group | `network-automation-render-consumer` |
| Existing task queue | `network-automation` |
| gNMI port | `57401` |
| gNMI timeout | `10` seconds |
| TLS mode | `insecure` |

All six render/deployment topic names must be distinct. Device username/password are
worker-local secrets with no source-code defaults.

## Request Command And Consumer

```text
uv run network-render-request --deploy DEVICE
```

The flag selects `DeploymentRequested` and `deploy-device-config:<event_id>`; omission
retains Feature 003 exactly. The thin consumer validates either request model and starts
the same `RenderDeviceConfigWorkflow` class with its matching typed input. Deployment uses
the same task queue, 10-minute execution timeout,
`WorkflowIDConflictPolicy.USE_EXISTING`, and
`WorkflowIDReusePolicy.REJECT_DUPLICATE`. Accepted/already-retained starts permit synchronous
offset commit; uncertain starts/commit failures seek the same partition offset. Poison
records are safely logged and committed without a workflow. Topic and `event_type` must
match exactly; cross-topic valid payloads are poison and can never trigger mutation.

## Workflow Ordering

```text
prepare_device_deployment (one intent read + Feature 002 render/write/digest/target bind)
  -> deploy_device_artifact
  -> validate_device_state
  -> DeploymentCompleted -> publish_render_result
```

The existing render input retains its exact Feature 003 sequence. A deployment input is
discriminated by literal `operation="deploy"` and never publishes `network.render.*`.
Prepare (including render), deploy, or validate failure creates one `DeploymentFailed` and
calls the existing named publication activity with its explicitly broadened result union.
The exception scope around each activity excludes result publication, so an
unpublishable outcome fails visibly rather than being misclassified.

Activity signatures:

```text
prepare_device_deployment(DeployDeviceConfigRequest) -> PreparedDeployment
deploy_device_artifact(PreparedDeployment) -> DeploymentResult
validate_device_state(PreparedDeployment) -> DeviceValidationResult
```

The workflow performs no HTTP, filesystem, gNMI, Kafka, ordinary UUID, or wall-clock work.
It constructs stable result identity/time with Temporal deterministic APIs.

## Device Operation

Before every mutation attempt, deployment rereads the exact path and verifies byte count
and SHA-256. It verifies the connected target/platform, then sends exactly:

```python
gNMIclient.set(update=[("/cli://", artifact)], encoding="ascii")
```

No replace, delete, SSH, shell, container exec, deployment-side rendering, or internal
retry helper is allowed. Temporal owns all retries. Validation performs independent native
JSON-IETF Gets and does not infer success from Set output or artifact text.

## Error And Retry Contract

Prepare retries Nautobot transport/server and transient artifact I/O only. Deploy retries
gRPC `UNAVAILABLE`, `DEADLINE_EXCEEDED`, and temporary connection refusal.
Authentication/permission, identity/platform mismatch, digest mismatch, and deterministic
`ABORTED`/`INVALID_ARGUMENT`/`FAILED_PRECONDITION` rejection are permanent; unknown Set
statuses are also permanent. Validation retries read connectivity
and operational non-convergence; authentication, malformed responses, and deterministic
configuration mismatches are permanent/final.

Validation retries cannot rerender, prepare, or deploy. Deployment retries cannot rerender
or prepare. Publication retries cannot repeat any prior operation.

Changing the workflow requires Temporal `Replayer` tests against representative accepted
Feature 003 success and failure histories before worker rollout.
