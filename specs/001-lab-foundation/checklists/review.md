# Planning Review: Lab Foundation

**Reviewed**: 2026-09-08
**Status**: Approved for implementation on 2026-09-08 after required simplifications.
Checked items below describe document review, NOT completed implementation tasks.

## Specification Quality

- [x] Deliverables, exclusions, assumptions, prioritized stories and measurable outcomes defined.
- [x] Each of FR-001 through FR-013 maps to tasks; SC-001 through SC-006 have explicit verification.
- [x] Service graph, eight long-running services, three one-shots, endpoints and named volumes enumerated.
- [x] Host prerequisites and Linux reference acceptance distinguished from unverified macOS/ARM64 support.
- [x] Health is application-level and separate from process presence, integration smoke tests and device readiness.
- [x] Unit mocks, real service tests, persistence/failure/reset tests and clean-checkout evidence specified.
- [x] Local-only credentials, loopback exposure, role isolation and destructive reset warnings specified.
- [x] At the planning checkpoint, future commands and files were explicitly labeled
  proposed rather than presented as already runnable or delivered.
- [x] All 21 tasks retain their implementation/evidence completion gates after approval.

## Architecture And Simplicity

- [x] Nautobot owns intent; Kafka only transports; Temporal owns durable workflows in later features.
- [x] One Python package and host-managed `uv` runtime; no idle automation worker/container.
- [x] No speculative domain/event/workflow/activity/rendering layers, plugin system, or custom App.
- [x] Shared PostgreSQL uses application-isolated DBs/roles; Temporal SQL visibility avoids Elasticsearch.
- [x] Nautobot worker/Beat and one-shots have current upstream responsibilities, not speculative services.
- [x] Topology is optional scaffolding, not device provisioning or a competing intent authority.

## Independent Review And Resolutions

An independent read-only review found two material design issues, corrected before
this checkpoint:

1. A prior review proposed gating UI on namespace completion. Approval explicitly
   supersedes that: UI now waits only for healthy Temporal, while aggregate health
   and integration acceptance require visible one-shot success plus `default`.
2. Disposable Kafka ports could diverge from advertised metadata and direct tests
   to the ordinary broker. `LAB_KAFKA_HOST_PORT` now drives publication,
   advertisement and default Python bootstrap. T013 verifies isolated metadata
   before fixtures while the ordinary lab remains running.

Both corrections preserve the architecture and avoid new services/abstractions.
No further material design issue identified in the final local consistency check.

## Tooling And Actual Evidence

- Initial directory read: zero entries; `git rev-parse --show-toplevel` confirmed
  no Git repository. There was no prior project state to preserve.
- `specify version`: installed CLI 0.9.5, Darwin ARM64. Initialized bundled sh
  assets and OpenCode integration with `--no-git`; installed Codex skills alongside
  OpenCode using native multi-install override. No global tool upgrade.
- `git init -b main` plus native create-feature script established unborn
  `001-lab-foundation`; no commits, staging, remote or pushes.
- `specify integration list`: Codex installed, OpenCode installed/default.
  Checked generated paths: `.agents/skills/` and `.opencode/commands/`.
- Native `setup-plan.sh` initially failed on unborn-HEAD detection; succeeded with
  `SPECIFY_FEATURE=001-lab-foundation`. Workaround documented; no dummy commit.
- `SPECIFY_FEATURE=001-lab-foundation bash .specify/scripts/bash/check-prerequisites.sh --json --require-tasks --include-tasks`
  succeeded and discovered research, data-model, contracts, quickstart and tasks.
- Reviewed native spec/plan/tasks templates and workflow instructions. Optional
  agent-context hooks were handled by directly updating the generated AGENTS plan
  reference; no mandatory extension hook applies.
- No Compose/application files, package implementation, tests, image pulls,
  service startup, network nodes or destructive resets were performed.

## Residual Verification Gates

Exact maintained image patch tags/platforms, release-specific startup/schema and
health commands, aggregate resource budget, Compose one-shot semantics, and
optional netlab/containerlab tuple require implementation-time verification.
All real Linux acceptance remains unrun. Candidate version families are not a
tested matrix. These are explicit T001/T012/T015/T019/T020 gates, not reasons to
claim success or silently change the architecture.

## Approved Simplifications

- [x] Redis has no named volume/AOF durability acceptance; only PostgreSQL,
  Kafka/KRaft, and Nautobot media persist. Temporal remains durable execution owner.
- [x] Compose uses exact supported patch tags without mandatory digest pins;
  `uv.lock` remains committed and useful tested digests/platforms become evidence.
- [x] Temporal UI is decoupled from namespace initialization; aggregate health,
  not UI container startup, enforces initializer success and `default` existence.

**APPROVED: Implementation may proceed, limited to Feature 001.**

## Implementation Review

**Reviewed**: 2026-09-08

- [x] No Kafka consumer, Temporal automation worker/workflow, intent model, Jinja
  rendering, device access, deployment, or DHCP/ZTP behavior was introduced.
- [x] Compose retains one explicit stack, three durable named volumes, disposable
  Redis, loopback-only application ports, exact patch tags, and small initializers.
- [x] Pydantic settings validate host boundaries and canonical Nautobot credentials;
  external systems remain isolated from domain logic because no domain layer exists.
- [x] Temporal Compose readiness uses its HTTP application API; aggregate health
  separately proves gRPC SERVING, namespace presence, UI backend access, Kafka
  metadata, authenticated Nautobot access, and every service/initializer state.
- [x] Unit, real-service, repeated-start, persistence, failure/recovery, occupied-port,
  and disposable-reset checks passed on the recorded macOS ARM64 environment.
- [x] Review findings for canonical credential precedence, internal Kafka round-trip,
  endpoint isolation, bounded probes, stale artifacts, and lifecycle command safety
  were corrected and revalidated.
- [ ] Ubuntu 24.04 x86-64 clean-checkout acceptance and Docker-stopped developer
  validation remain unavailable on the current host.
- [ ] The optional netlab/containerlab/SR Linux create-only check remains unavailable
  on macOS and must be run on the documented Linux tuple.

No architectural or future-feature scope violation was found. Feature 001 cannot
be declared fully accepted until the remaining reference-platform gates complete.
