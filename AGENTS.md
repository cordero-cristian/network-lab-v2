# Agent Instructions

- Read `.specify/memory/constitution.md` and the active feature's spec, plan,
  and tasks before changing code. Use the Spec Kit workflow; preserve its artifacts.
- Feature 001 implementation was approved on 2026-09-08 and reference acceptance
  completed on 2026-09-09. Do not begin another feature without its own Spec Kit
  artifacts and explicit approval.
- Feature 002 implementation and reference acceptance completed on 2026-09-09.
  Preserve its Nautobot-to-artifact behavior as the rendering path for later work.
- Nautobot owns intent; Kafka transports events; Temporal orchestrates durable
  execution. Pydantic v2 validates boundaries; Jinja2 only renders. Isolate device
  access and external integrations from domain models. Never silently change this.
- Prefer one typed Python package and, when needed, one Temporal automation worker.
  Use `uv` and pytest. No speculative services, factories, plugins, or future layers.
- Keep Compose explicit, image patch tags pinned (digests are evidence, not required
  pins), durable state in named volumes, ports local, initialization small, and
  health meaningful. Redis is disposable infrastructure, never durable automation
  state. Credentials are local-lab-only.
- Unit tests mock external systems; acceptance must exercise real infrastructure.
  Report actual commands/results and platform limitations, not assumed success.
- Preserve unrelated work. Do not commit, push, or reset persistent data without
  user authorization. Update docs and tests alongside approved implementation.

<!-- SPECKIT START -->
Active feature: `specs/007-read-only-drift-compliance/spec.md`; implementation plan is
`specs/007-read-only-drift-compliance/plan.md`. Feature 007 implementation and canonical acceptance
completed on 2026-09-23. Preserve its expected-only, read-only comparison behavior.
Feature 003 implementation was approved on 2026-09-09 with separate Temporal running
conflict and closed reuse policies. Implementation and reference acceptance completed
on 2026-09-10. Preserve it. Feature 004 implementation was conditionally approved on
2026-09-10. Canonical T001 found material BGP AF and address-read differences; planning
artifacts were corrected. Feature 004 corrected implementation was approved on 2026-09-10
after canonical T001. Implementation and canonical acceptance completed on 2026-09-11.
Preserve Feature 004. Feature 005 T001/T002 evidence was accepted on 2026-09-12: the pinned
container does not execute genuine boot-time ZTP and its serial is unusable. The approved
redesign preserves that container for Features 001-004 and forbids emulating ZTP inside it.
Feature 005 is DEFERRED — BLOCKED ON ACCESS TO A GENUINE BOOTABLE SR LINUX RUNTIME. It may
resume only when the owner provides or authorizes a genuine bootable SR Linux artifact whose
provenance and lab use are acceptable and which can exercise the documented SR Linux
auto-boot path.
Its virtual identity design uses a deterministic boot-management MAC represented by core
Nautobot `Interface.mac_address`, contingent on a future runtime gate. Do not execute T003 or
later without an owner-authorized artifact and explicit approval; T007 onward additionally
requires a passing T003-T006 gate and separate implementation approval.
Feature 006 planning began on 2026-09-13 and implementation was approved on 2026-09-14 with three
guardrails: live device reads are one on-demand detail operation with a 15-second budget and no
device polling; API structure exposes no automation mutation; Temporal lists remain visibility-
first with default 25, maximum 50, concurrency four, overview shallow hydration capped at eight,
and full activity history only for detail. Implementation completed on 2026-09-14; canonical
populated-data, live-device, retained-failure, desktop/375-pixel browser, security, cleanup, and
Features 001-004 regression acceptance completed on 2026-09-15. Preserve Feature 006.
Preserve the approved Lavish operator-console direction, source ownership, browser-to-API boundary,
and no-store/no-WebSocket/no-consumer scope.
Feature 007 planning completed on 2026-09-22. Its implementation derives expected state only from
Nautobot/Feature 002 models, reuses one Feature 004 structured read, and keeps configuration drift
separate from operational health. BGP-down and other operational failures are not drift when
configured values match. V1 does not inspect unexpected extra configuration, persist results,
poll devices, remediate, or add a generic policy/compliance framework. Implementation was separately
approved on 2026-09-22; unit, integration, canonical Nautobot 3.2.5/SR Linux, desktop/375-pixel
browser, security, cleanup, and Features 001-004 plus Feature 006 regression acceptance completed
on 2026-09-23. Preserve Feature 007.
<!-- SPECKIT END -->

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

When the user types `/graphify`, use the installed graphify skill or instructions before doing anything else.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- Dirty graphify-out/ files are expected after hooks or incremental updates; dirty graph files are not a reason to skip graphify. Only skip graphify if the task is about stale or incorrect graph output, or the user explicitly says not to use it.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- When `graphify-out/graph.json` exists, run `graphify update .` after modifying code to keep
  the graph current (AST-only, no API cost). Use the README bootstrap command when it does not.
