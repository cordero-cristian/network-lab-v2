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
Active feature: `specs/003-event-driven-execution/spec.md`.
Read `specs/003-event-driven-execution/plan.md` and `tasks.md` after they are generated.
Feature 003 implementation was approved on 2026-09-09 with separate Temporal running
conflict and closed reuse policies. Implementation and reference acceptance completed
on 2026-09-10. Preserve it and do not create or begin Feature 004.
<!-- SPECKIT END -->
