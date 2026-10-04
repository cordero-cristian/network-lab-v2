# Implementation Plan: Nautobot Intent To Deterministic SR Linux Artifact

**Branch**: `002-nautobot-srlinux-artifact` | **Date**: 2026-09-09 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/002-nautobot-srlinux-artifact/spec.md`

**Status**: Approved for implementation on 2026-09-09 with required adjustments.

## Summary

Extend the existing Python package with one explicit Nautobot REST adapter, Pydantic
v2 intent models and conversion, one SR Linux Jinja2 template, an atomic artifact
writer, and a minimal argparse CLI. Read device identity and interface addressing
from Nautobot core objects and BGP values from a namespaced local configuration
context. Follow the Platform relation for stable `network_driver` dispatch. Render
only validated normalized intent to `artifacts/configs/<name>.cfg`.

## Technical Context

**Language/Version**: CPython 3.12.13, as locked by Feature 001

**Primary Dependencies**: Existing Pydantic v2, pydantic-settings, and httpx;
add Jinja2 3.1 exact-compatible lock resolution. argparse, pathlib, ipaddress,
tempfile, and os are standard-library dependencies. No pynautobot or CLI framework.

**Storage**: Existing Nautobot PostgreSQL-owned data plus ignored generated files
under `artifacts/configs/`; no new database, schema, volume, or rendered config in
Nautobot.

**Testing**: pytest unit tests with mocked/raw fixtures and a plain reviewed golden
file; explicit real-Nautobot integration test using uniquely named API fixtures.
Default pytest remains unit-only.

**Target Platform**: Existing Feature 001 developer/runtime platforms; canonical
integration acceptance on Ubuntu 24.04.4 LTS x86-64 against Nautobot 2.4.41.

**Project Type**: One typed Python package with a host-side CLI; no service or worker.

**Performance Goals**: 100 repeated offline renders are byte-identical. External
requests use the existing maximum 10-second per-probe timeout; no throughput target
is justified for one device per command.

**Constraints**: One initial Nokia SR Linux shape; IPv4 only; one address per modeled
interface; default network instance only; bounded HTTP timeout; secrets redacted;
no device, Kafka, Temporal, or ZTP access.

**Scale/Scope**: One device per command, exactly one loopback, any small collection
of addressed routed interfaces and BGP neighbors; offline golden fixture is `leaf01`
with two of each, while real integration uses a unique Device name.

## Constitution Check

*GATE: Passed before research and rechecked after design.*

| Principle | Pre-Design Gate | Post-Design Evidence |
|---|---|---|
| Explicit Architectural Ownership | PASS: Nautobot remains intent owner; typed models separate external data from rendering; Jinja2 only renders. | REST payload is converted before rendering; templates receive only a prepared typed context; artifacts are derived files, not Nautobot records. |
| Small, Explicit Implementation | PASS: one package, no service/framework/plugin/vendor layer. | Four focused modules, one template, one CLI, and direct functions/classes only. |
| Reproducible Local Infrastructure | PASS: Feature 001 Compose is reused without mutation; dependencies stay under `uv`. | Only Jinja2 and lock updates are planned; output is ignored and credentials reuse validated settings. |
| Evidence Over Process Status | PASS: offline behavior and real Nautobot path both have observable acceptance. | Golden comparison, failure/atomicity tests, and API-created integration fixtures cover the complete path. |
| Spec-Driven, Bounded Delivery | PASS: Feature 002 is planned separately and stops for approval. | Spec, research, model, contracts, quickstart, tasks, and consistency review are produced before implementation. |

No constitution violation requires complexity justification.

## Design Decisions

### Nautobot Source Mapping

The adapter uses Nautobot 2.4 REST endpoints and existing token settings:

1. `GET /api/dcim/devices/?name=<exact-name>&limit=2`
2. Follow the Device's `platform.url` and consume `network_driver` plus diagnostic
   `display`
3. Follow `role.url` and optional `location.url` for their display metadata
4. `GET /api/dcim/interfaces/?device_id=<device-uuid>` with pagination
5. Normalize each Interface choice object's `type.value`, then follow each eligible
   interface's `ip_addresses[].url` and consume its `address`

Required device fields are `id`, `name`, `platform.url`, `role.url`, optional
`location.url`, and `local_config_context_data`. Required interface
fields are `id`, `name`, `description`, `type`, `enabled`, `mgmt_only`, and
`ip_addresses[].url`. Required Platform fields are `network_driver` and optional
`display`; Role and Location details supply `display`; required IPAddress field is
`address`. The adapter treats exactly one
enabled, non-management interface of type `virtual` as loopback regardless of name.
Every other enabled, non-management interface is in initial intent only when its
type is not `virtual`, `lag`, `bridge`, or `other`; such non-physical types fail
rather than disappear. Every eligible interface must resolve to exactly one IPv4
address; disabled interfaces are intentionally ignored.

The exact BGP input is the approved Feature 002 namespaced contract, not a permanent
choice for every future intent model:

```yaml
network_automation:
  bgp:
    local_asn: 65001
    neighbors:
      - address: 192.0.2.1
        remote_asn: 65100
        description: spine01
      - address: 192.0.2.3
        remote_asn: 65200
        description: spine02
```

The adapter returns a compound raw mapping. `device_intent_from_nautobot()` alone
interprets external field shapes and constructs `DeviceIntent`; Pydantic models
never perform HTTP and Jinja never receives the raw mapping.

### Initial Intent And Rendering

`DeviceIntent` contains name, stable platform identifier, optional display label,
role, optional location, one `LoopbackIntent`, routed interfaces, and BGP.
`LoopbackIntent` contains description and one `/32` `IPv4Interface`, but no name.
`InterfaceIntent` contains routed name, required description, and one
`IPv4Interface`. `BgpIntent` and `BgpNeighborIntent` contain constrained ASNs,
peer address, and optional description.

The renderer supports exactly `platform == "nokia_srl"`; display text cannot dispatch.
Python renders the name-independent loopback as SR Linux `system0`,
sorts interfaces by digit/text natural components followed by case-folded and exact
full-name tie-breakers, and sorts neighbors numerically,
derives router-ID from the `/32` loopback host, builds the complete template context,
and normalizes one final newline. The single template contains presentation loops
only; it does not sort, validate, derive, query, or choose platform behavior.

Rendered sections are:

1. System hostname.
2. Interface and subinterface 0 admin state, descriptions, and IPv4 addresses.
3. Default network-instance attachment for every rendered subinterface.
4. Default network-instance BGP admin state, autonomous system, loopback-derived
   router-ID, neighbor peer-AS, and optional peer descriptions.

No role/location command is emitted; those fields retain source metadata and can
be used in later separately approved requirements.

### Artifact And CLI Contract

Default output is repository-relative `artifacts/configs/<device-name>.cfg`, with
the entire `artifacts/` directory ignored. A safe device-name pattern prevents path
traversal. Rendering completes in memory before a temporary sibling file is flushed
and atomically replaces the target; absent directories are created. Staging or
replacement failure removes its temporary file and preserves any prior complete
artifact. This guarantees process-level replacement atomicity, not crash durability.

The console entry point is `network-render = network_automation.cli.render:main`.
`uv run network-render DEVICE` prints only the resulting relative path on success;
real integration supplies its unique `feature002-leaf-<suffix>` name.
An optional `--output-dir` supports isolated tests and callers while preserving the
deterministic default. Errors go to stderr, redact credentials, and return nonzero.

## Project Structure

### Documentation (this feature)

```text
specs/002-nautobot-srlinux-artifact/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── interfaces.md
├── checklists/
│   └── requirements.md
└── tasks.md
```

### Source Code (repository root)

```text
src/network_automation/
├── __init__.py
├── settings.py
├── health.py
├── intent/
│   ├── __init__.py
│   ├── models.py
│   └── nautobot.py
├── rendering/
│   ├── __init__.py
│   └── srlinux.py
├── templates/
│   └── srlinux/
│       └── config.j2
└── cli/
    ├── __init__.py
    └── render.py
tests/
├── fixtures/
│   ├── nautobot/leaf01.json
│   └── expected/leaf01.cfg
├── unit/
│   ├── test_intent_models.py
│   ├── test_nautobot_intent.py
│   ├── test_srlinux_render.py
│   └── test_render_cli.py
└── integration/
    └── test_nautobot_render.py
artifacts/
└── configs/                 # generated and ignored; absent until rendering
```

**Structure Decision**: Extend the one existing package with only current-feature
boundaries. `intent/nautobot.py` owns both the narrow adapter and external mapping
because no second source exists. The template lives at
`src/network_automation/templates/srlinux/config.j2`, is included as package data,
and is loaded with package resources so the console command does not depend on the
current directory. One template is sufficient; includes, macros, base classes,
factories, and vendor registries are omitted.

## Implementation Sequence

1. Lock Jinja2 and ignore generated artifacts without changing Feature 001 runtime.
2. Write failing model/conversion tests and implement the explicit intent boundary.
3. Add the reviewed golden fixture, failing render/artifact tests, one template, and
   deterministic SR Linux renderer/writer.
4. Add the minimal CLI and its tests.
5. Add API-created fixtures whose mutable object names and serial use one unique
   suffix, including `feature002-leaf-<suffix>`. Create dedicated Status/Namespace
   records, reuse no existing intent object, and clean only exact recorded IDs.
6. Run offline, failure, determinism, integration, scope, and documentation review;
   record actual evidence. Do not implement until this plan receives approval.
