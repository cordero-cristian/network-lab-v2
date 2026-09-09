# Agent Instructions

- Read `.specify/memory/constitution.md` and the active feature's spec, plan,
  and tasks before changing code. Use the Spec Kit workflow; preserve its artifacts.
- Feature 001 implementation was approved on 2026-09-08 with the synchronized
  simplifications in its planning artifacts. Implement only its existing tasks.
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
Active feature: `specs/001-lab-foundation/spec.md`.
Read `specs/001-lab-foundation/plan.md` and `tasks.md` in that directory for the
approved structure, decisions, commands, and implementation sequence.
<!-- SPECKIT END -->
