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
Active feature: `specs/005-dhcp-ztp-onboarding/spec.md`; implementation plan is
`specs/005-dhcp-ztp-onboarding/plan.md`. Read both and `tasks.md` before implementation.
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
<!-- SPECKIT END -->
