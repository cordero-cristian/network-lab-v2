# Implementation Plan: SR Linux Deployment And Operational Validation

**Branch**: `004-srlinux-deployment-validation` | **Date**: 2026-09-10 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/004-srlinux-deployment-validation/spec.md`

**Status**: Implementation and canonical acceptance complete 2026-09-11; corrected
implementation and minimal topology-owned hostname bootstrap were approved 2026-09-10

## Summary

Extend the accepted Feature 003 execution with an additive deployment request that uses
the same consumer, workflow class, worker, Feature 002 renderer, and result publisher.
One preparation activity reads Nautobot once and uses Feature 002 to atomically render,
write, digest, and bind target/expected state; Temporal then applies those exact bytes to
Nokia SR Linux through one pyGNMI CLI-origin Set transaction, independently
validates selected native JSON-IETF state, and publishes one safe correlated outcome.

## Technical Context

**Language/Version**: CPython 3.12.13, as already locked

**Primary Dependencies**: Existing Temporal Python SDK, confluent-kafka, Pydantic v2,
httpx, pydantic-settings, and Jinja2; add exact `pygnmi==0.8.15`

**Storage**: Existing Nautobot, Kafka, Temporal PostgreSQL, and ignored deterministic
artifact files. No deployment database, artifact service, new volume, or Redis state.

**Testing**: pytest; mocked gNMI/Nautobot/Kafka boundaries; Temporal time-skipping worker;
real canonical Kafka, Temporal, Nautobot, and two-node SR Linux 26.7.2-519 acceptance

**Target Platform**: Development on macOS ARM64 where supported; authoritative real-device
acceptance on Ubuntu 24.04.4 x86-64 with Docker, netlab, and containerlab

**Project Type**: One typed Python package, one existing worker, one existing consumer,
one finite request command, and a separately managed two-node device topology

**Performance Goals**: One low-volume lab deployment completes within five minutes once
infrastructure and devices are healthy; no throughput target

**Constraints**: gNMI only; unchanged artifact bytes per deployment attempt; no secrets or
raw configuration in events/history/logs; bounded retries; validation retry cannot deploy;
base Compose must work without topology; no rollback or generic driver framework

**Scale/Scope**: Two SR Linux nodes, one point-to-point link, one loopback and one BGP peer
per node, three additive event topics, three additive activities, one SR Linux client module

## Constitution Check

*GATE: Passed before research and rechecked after design.*

| Principle | Pre-Design Gate | Post-Design Evidence |
|---|---|---|
| Explicit Architectural Ownership | PASS: Nautobot supplies target and invariants; Kafka carries facts; Temporal owns sequence/retries; device access is an activity boundary. | One workflow coordinates render, prepare, deploy, validate, and publish. Feature 002 remains the sole renderer; the SR Linux module alone performs gNMI. |
| Small, Explicit Implementation | PASS: extend the existing package, worker, consumer, workflow, and CLI. | One concrete SR Linux client module and three activities; no registry, base driver, extra process, API, or datastore. |
| Reproducible Local Infrastructure | PASS: supporting Compose stays intact and topology lifecycle stays separate. | One optional Compose network override attaches only the worker to a topology-owned network; pinned images/dependency and explicit teardown are documented. |
| Evidence Over Process Status | PASS: real mutation and independent state reads are mandatory. | Unit/time-skipping tests prove boundaries and ordering; canonical acceptance proves Set, convergence, failures, duplicate behavior, state, and cleanup. ARM64 limitations are recorded, not treated as success. |
| Spec-Driven, Bounded Delivery | PASS: Feature 004 has separate artifacts and excludes bootstrap/future scope. | Research, models, contracts, quickstart, tasks, review, and approval gate precede implementation. |

No constitution violation requires complexity justification.

## Design Decisions

### Compatibility And Rendering

Preserve all Feature 003 render request/result contracts and behavior. Add
`network.deployment.requested` v1 so retained render-only events can never begin device
mutation after upgrade. The same consumer starts the same workflow class with a distinct
typed input and ID `deploy-device-config:<event_id>`, retaining independent running-conflict
`USE_EXISTING` and closed-reuse `REJECT_DUPLICATE` policies.

Feature 002 remains the sole renderer. Its SR Linux template is narrowly corrected to
emit deterministic remote-AS peer groups, enable global BGP IPv4 unicast, and attach each
neighbor. This is required by pinned SR Linux and changes no intent ownership, path, writer,
or artifact syntax. Deployment never transforms or rerenders the artifact.

### Preparation And Device Boundary

For a deployment input, `prepare_device_deployment` performs one Nautobot read, follows
same-origin `primary_ip4`, and uses Feature 002's renderer/writer to compute identity from
the rendered bytes before atomic replacement. It validates path/ASCII/full-context/
hostname/size and returns target plus explicit intended checks. This same-activity binding
prevents another request from replacing the path before its digest is first recorded. It
contains no credentials or raw artifact.

`src/network_automation/devices/srlinux.py` contains the sole concrete client. Before every
write it disables pyGNMI client logging, rereads and verifies artifact digest, connects to
the authoritative target, confirms supported platform/current target identity, and calls
`set(update=[("/cli://", artifact)], encoding="ascii")`. The Set is one transaction;
`update` preserves unmentioned management bootstrap state. Repeating keyed declarations
converges but does not remove stale unmentioned configuration.

### Validation And Outcomes

`deploy_device_artifact` returns only safe deployment metadata. A separate
`validate_device_state` activity performs native-origin JSON-IETF leaf Gets for hostname,
interface/subinterface admin and oper state, exact addresses and readiness, local ASN,
peer ASN, and BGP established state. Parsing scans all notifications and optional updates,
normalizes module-qualified paths, preserves native types, and rejects conflicting values.
Valid absent values are convergence failures; invalid paths/malformed responses are
permanent client errors.

Validation returns one bounded typed result. Temporary connectivity or operational
non-convergence retries only validation. Success publishes `network.deployment.completed`;
prepare/deploy/final-validation failure publishes `network.deployment.failed`; preparation
includes render failure. A deployment request never emits `network.render.*`, so existing
render result workflow-ID semantics remain unchanged. Result event UUID/time are created
once with deterministic workflow APIs, so at-least-once Kafka retries represent one logical
result.

### Retry And Safety

- Prepare: 3 attempts, 1s exponential backoff capped at 5s, 60s per attempt.
- Deploy: 3 attempts, 2s exponential backoff capped at 10s, 30s per attempt.
- Validate: 12 attempts, 2s initial, coefficient 1.5, 5s cap, 15s per attempt, 90s bound.
- Publish: existing 5 attempts, 1s exponential backoff capped at 10s, 30s per attempt.
- Workflow: existing 10-minute execution timeout; gNMI connect/RPC timeout is 10 seconds.

Only connectivity/deadline/temporary refusal failures retry deployment.
Authentication, identity/platform, digest, malformed artifact/response, and deterministic
Set rejection are permanent. `FAILED_PRECONDITION` and unknown Set errors are permanent
because no safe structured lock/rejection distinction is available. Validation connectivity and non-convergence retry; final
deterministic mismatch is reported after the bound. Static safe messages are used and raw
pyGNMI exceptions, device responses, artifacts, and credentials are never serialized.

### Runtime And Acceptance

`lab/topology.yml` becomes a fixed two-node Feature 004 topology on test-owned management
network `network-lab-devices-mgmt`. `netlab up ... --no-config` creates only device/link/
management/gNMI bootstrap plus one topology-owned hostname declaration per node; automation
supplies all loopback, routed-interface, BGP, policy, and other intended state. Optional
`compose.device-access.yaml` attaches only the existing worker to that external network.
Topology starts before the override, and the worker container is removed before topology
cleanup. Supporting volumes and unrelated labs are never reset.

Worker-local settings provide username/password, port 57401, 10-second timeout, and the
literal lab TLS mode `insecure`; absence fails only deployment activity and does not break
render-only startup. Existing `network-render-request DEVICE` gains `--deploy`; no direct
mutation/validation CLI, host address map, new worker, proxy, or service is added.
The canonical toolchain is netlab 26.8.0 and containerlab 0.79.0.

## Project Structure

### Documentation (this feature)

```text
specs/004-srlinux-deployment-validation/
|-- spec.md
|-- plan.md
|-- research.md
|-- data-model.md
|-- quickstart.md
|-- contracts/
|   |-- events.md
|   |-- execution.md
|   `-- device-state.md
|-- checklists/
|   |-- requirements.md
|   `-- review.md
`-- tasks.md
```

### Source Code (repository root)

```text
pyproject.toml                         # exact pyGNMI pin
uv.lock
.env.example                          # local device settings/topics
compose.yaml                          # additive topics/settings only
compose.device-access.yaml            # optional worker/device network attachment
lab/topology.yml                      # two-node test-owned topology
lab/bootstrap/*.cli                   # one hostname identity declaration per node
src/network_automation/
|-- settings.py
|-- devices/
|   |-- __init__.py
|   `-- srlinux.py                    # sole gNMI boundary and response normalization
|-- intent/nautobot.py                # authoritative primary_ip4 extraction
|-- rendering/srlinux.py              # deterministic peer-group context
|-- templates/srlinux/config.j2       # required peer-group/address-family lines
|-- events/{models,producer,consumer}.py
|-- workflows/render_device.py        # same workflow class, additive input branch
|-- activities/
|   |-- rendering.py                  # accepted render/publish retained
|   `-- deployment.py                 # prepare/deploy/validate activities
|-- cli/render_request.py             # additive --deploy mode
`-- worker.py                         # register three activities
tests/
|-- unit/
|   |-- test_srlinux_device.py
|   |-- test_deployment_models.py
|   |-- test_deployment_activities.py
|   |-- test_deployment_workflow.py
|   |-- test_deployment_events.py
|   `-- existing focused tests updated narrowly
`-- integration/
    |-- support/nautobot_fixture.py
    `-- test_srlinux_deployment.py
```

**Structure Decision**: Extend the accepted single package and runtime processes. One
SR Linux-specific module isolates transport; one deployment activity module isolates
external operations. No generic device interface hierarchy is justified for one NOS.

## Implementation Sequence

1. Lock additive settings/events/models and correct the sole renderer for pinned BGP.
2. Implement and unit-test atomic render/target/artifact preparation and native response normalization.
3. Implement and unit-test the concrete SR Linux Set/Get boundary, address-key/status
   validation, and safe classification.
4. Extend the existing workflow, consumer, producer, publication activity, CLI, and worker
   without altering the render-only branch or Feature 003 identity semantics; replay
   representative accepted Feature 003 histories.
5. Add the separate topology and optional worker network override.
6. Add real test-owned Nautobot/device fixtures and full success, duplicate, recovery,
   failure, convergence, independent-state, and cleanup acceptance.
7. Run default and Feature 001-003 regressions, document actual canonical evidence, enforce
   excluded scope, and stop without beginning Feature 005.

## Complexity Tracking

No constitution violation is proposed. The optional Compose override is lifecycle glue for
the existing worker, not another service. The Feature 002 template correction is necessary
for the explicitly required real BGP invariant and remains inside the accepted renderer.
