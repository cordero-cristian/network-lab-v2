# Onboarding Execution Contract

**Status**: DEFERRED — BLOCKED ON ACCESS TO A GENUINE BOOTABLE SR LINUX RUNTIME

Feature 005 may resume only when the owner provides or authorizes a genuine bootable SR Linux
artifact whose provenance and lab use are acceptable and which can exercise the documented
SR Linux auto-boot path. Existing Feature 004 execution remains unchanged.

## Ownership

```text
genuine SR Linux firmware/GRUB auto-boot -> isolated DHCP/HTTP -> minimum bootstrap
finite onboarding boundary -> existing DeploymentRequested
existing consumer -> existing RenderDeviceConfigWorkflow deployment branch
prepare -> deploy -> validate -> existing correlated deployment outcome
```

Nautobot owns mapping and intended state. DHCP/HTTP observations are disposable. Kafka
transports only the accepted deployment request and result. Temporal owns durable retries
after request acceptance. Feature 002 remains the sole production renderer and Feature 004
remains the sole deployment/validation path.

## Retry Boundaries

| Operation | Bound | Retryable | Permanent |
|---|---|---|---|
| Native discovery | Selected-runtime duration/attempt values proved by gate | Temporary discovery/download failures | Invalid script/config or exhausted native attempts |
| Nautobot mapping/readiness | 12 attempts, 90 seconds total | Transport/server failure | Invalid, absent, duplicate, or inconsistent mapping |
| gNMI readiness | Same 12-attempt shared bound | Unavailable/deadline/refusal | Authentication, platform, identity, malformed response |
| Kafka handoff | Existing producer bound | Transport/delivery uncertainty with same bytes | Invalid request construction |
| Deployment | Accepted Feature 004 policies | Unchanged | Unchanged |

The finite boundary never retries deployment. The accepted workflow never reruns native
bootstrap or onboarding readiness. No operation maintains a second durable state machine.

## Duplicate And Reboot Semantics

- Physical redelivery of the same request retains one event ID, workflow ID, and logical result.
- Concurrent delivery uses `USE_EXISTING`; delivery after closure uses
  `REJECT_DUPLICATE` within Temporal retention.
- Repeated DHCP lease renewal or artifact retrieval must leave intended state unchanged and
  cannot publish a deployment request by itself.
- Guest reboot must use native persistent configuration with auto-boot disabled; no
  `containerlab save` or snapshot may manufacture success.

Independently generated requests are separate deployments. The unchanged request has no
bootstrap MAC, so this contract provides no replacement-incarnation guarantee.

## Failure Visibility

Before Kafka acceptance, the command returns one safe categorized failure and nonzero exit;
Kafka publication exhaustion is `handoff_failed` and creates no workflow or Temporal history.
After acceptance, existing `DeploymentFailed` stages and categories remain authoritative.
DHCP logs, HTTP logs, native ZTP status, and packet captures are bounded test evidence only
and are never events or workflow payloads.

Changing the accepted workflow or device client requires Temporal replay and Feature 004
regression tests. The exact Feature 004 pre-Set hostname equality guard remains unchanged.
