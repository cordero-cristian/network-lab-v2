# Network Automation Lab Constitution

<!-- Sync impact: initial template -> 1.0.0. Replaced placeholder principles with
architecture, engineering, reproducibility, testing, and delivery rules.
Reviewed Spec Kit spec/plan/tasks templates: their existing requirements,
constitution-check, and test sections support these rules without customization.
AGENTS.md and Feature 001 artifacts synchronized. Feature 001 implementation was
approved on 2026-09-08. No deferred placeholders. -->

## Core Principles

### I. Explicit Architectural Ownership

Nautobot MUST own intended network state. Kafka MUST transport events and MUST
NOT orchestrate workflows. Temporal MUST own workflow state, retries, recovery,
and durable execution. Python implements automation. Pydantic v2 models MUST
form validated boundaries between external systems and automation logic.
Jinja2 MUST render configuration, without business logic. Network-device access
MUST be isolated behind explicit activities/interfaces, separate from domain
models. netlab and containerlab own lab topology/device lifecycle; Nokia SR Linux
is the initial network OS. DHCP/ZTP is a later bootstrap capability.

The intended flow is Nautobot intent -> Kafka event -> Temporal workflow -> read
Nautobot -> validate Pydantic models -> render Jinja2 -> deploy -> validate
operational state -> update state/emit result. This describes architecture, not
permission to implement all stages in any one feature.

### II. Small, Explicit Implementation

Prefer one Python package and one Temporal automation worker until a concrete
need justifies splitting. Supporting applications' own workers are not extra
automation services. Prefer simple functions/classes with clear responsibilities,
type hints, explicit code, and the smallest correct solution that can later
scale. MUST NOT introduce speculative microservices, factories, plugin systems,
generic frameworks, abstraction layers, or backward-compatibility mechanisms
without an actual requirement. Do not build functionality merely for future use.

### III. Reproducible Local Infrastructure

Docker Compose MUST reproduce supporting infrastructure from a clean checkout.
Use named volumes for useful persistent state, meaningful health checks, small
explicit initialization steps, and sensible pinned image versions, never
unqualified `latest`. Use a supported modern Python version, `uv`, committed
dependency locks, Pydantic v2, and pytest. Expose only useful local-development
ports, bound to loopback by default. Document host prerequisites, local-only
credentials, startup, diagnostics, persistence, and destructive reset separately.
No giant shell entrypoints or production secret-management system for this lab.

### IV. Evidence Over Process Status

Features MUST be independently testable wherever practical. Mock external
systems for unit tests, but prove important integration paths against real lab
infrastructure. A running container or open TCP socket alone is not evidence of
application health. Define observable acceptance criteria before implementation;
test failure paths and repeatability as well as first startup. Report what was
actually tested, on which platform, and distinguish unverified assumptions.

### V. Spec-Driven, Bounded Delivery

Use GitHub Spec Kit at project level: constitution -> feature specification ->
implementation plan -> tasks -> consistency review -> implementation -> validation.
One bounded feature at a time. Every plan MUST check this constitution before
and after design. Scope, architecture, and justified complexity MUST be explicit.
Core architecture MUST NOT change implicitly during implementation. When a
compatibility issue requires an architectural or scope change, update the plan
and obtain user approval rather than silently substituting technology.

## Feature Boundaries

Feature 001 delivers supporting infrastructure and a Python development runtime,
not automation workflows. Intent/rendering, event-driven execution, device
deployment/validation, and DHCP/ZTP belong to separately specified later features.
Do not create empty future-layer frameworks to anticipate them. Kubernetes,
cloud deployment, high availability, production authentication, and production
secrets management are outside the initial lab foundation.

## Development And Review Gates

Each feature MUST state deliverables, exclusions, service ownership and
communication, persisted data, host requirements, health semantics, developer
commands, tests, and scaffolding versus functional behavior. Tasks MUST map to
requirements/user stories, include relevant tests, and record dependencies.
Passing mocks is not a substitute for real-infrastructure acceptance. No commits,
pushes, destructive data resets, or changes to others' work without authorization.
Feature 001 has an explicit user approval checkpoint after planning: stop there.

## Governance

This constitution supersedes conflicting agent/template defaults. Amendments
require a documented rationale, impact on existing features, user approval, and
synchronized affected specs/plans/tasks and agent guidance. Use semantic versions:
major for incompatible principle changes, minor for added principles, patch for
clarifications. Reviews MUST report violations; do not treat a complexity table
as permission to override non-negotiable architecture. Ratification records the
user-supplied rules; Feature 001 implementation was approved on 2026-09-08.

**Version**: 1.0.0 | **Ratified**: 2026-09-08 | **Last Amended**: 2026-09-08
