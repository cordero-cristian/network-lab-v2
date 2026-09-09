# Research: Nautobot Intent To Deterministic SR Linux Artifact

**Date**: 2026-09-09

## Direct Nautobot REST Adapter

**Decision**: Use the existing `httpx` dependency and `LabSettings` Nautobot URL/token
to make narrow REST calls. Fetch one exact-name Device, follow its Platform URL for
stable `network_driver`, fetch Interfaces by `device_id`, and follow selected
IPAddress URLs. Return a compound raw mapping, then call one conversion function.

**Rationale**: Nautobot 2.4.41 serializer/filter introspection on the canonical host
confirmed Device fields `name`, `platform`, `role`, `location`, and
`local_config_context_data`; Interface fields `name`, `description`, `type`,
`mgmt_only`, `enabled`, and `ip_addresses`; IPAddress field `address`; and exact
`name`/`device_id` filters. Platform exposes stable `network_driver` plus diagnostic
`display`. Existing bounded HTTP and secret handling are sufficient.

**Alternatives considered**: pynautobot adds a dependency and broader object layer
without value for three endpoint shapes. GraphQL could reduce calls but adds query
schema complexity. Embedding HTTP in models or passing payloads to Jinja violates
the required boundary.

## Core Objects Plus Namespaced BGP Context

**Decision**: Use core Device/Interface/IPAddress objects for identity and addressing.
Store only local ASN and neighbors under
`Device.local_config_context_data.network_automation.bgp`.

**Rationale**: Nautobot core has no BGP neighbor entity in this installation. Local
configuration context is structured intended metadata attached to the Device and
does not require a custom App. Namespacing prevents collision with unrelated context;
the values are intent inputs, never rendered configuration.

**Alternatives considered**: Interface/device custom fields cannot represent a small
neighbor list cleanly. A custom App is explicitly excluded. A repository YAML intent
file would create a second intent authority. Storing rendered config in Nautobot
would reverse ownership.

This representation is the approved Feature 002 contract only. It does not commit
future intent features to Device local configuration context.

## Small Typed Model

**Decision**: Use five frozen Pydantic v2 models with standard `IPv4Interface` and
`IPv4Address`, constrained 32-bit ASNs, explicit non-empty strings, a safe artifact
name, and model-level duplicate/cross-field checks. `LoopbackIntent` has a `/32` and
optional description but no name; the adapter selects exactly one eligible virtual
source interface and the renderer maps it to SR Linux `system0`.

**Rationale**: These types express the initial supported shape and reject invalid
external data before rendering. Cross-field checks belong at the aggregate model,
not in templates or a generic validation framework.

**Alternatives considered**: Loose dictionaries defer errors into rendering.
Per-vendor inheritance and generic capability models are speculative. Supporting
multiple interface addresses, IPv6, or multiple loopbacks expands the feature
without acceptance value.

## One Presentation-Only Template

**Decision**: Add Jinja2 and one package-data template at
`src/network_automation/templates/srlinux/config.j2`. Python validates,
sorts, derives the router-ID, quotes values safely for the initial grammar, and
builds ordered rows. Jinja emits those rows with simple loops/conditionals.

**Rationale**: The target config is short enough that includes and macros would
obscure rather than clarify. A StrictUndefined environment, fixed newline settings,
and final newline normalization make missing fields and whitespace deterministic.
Package-resource lookup keeps installed CLI behavior independent of current directory.

**Alternatives considered**: Python string concatenation does not prove the intended
Jinja boundary. Three template files add indirection at this scale. Sorting and
derivation in Jinja would be hidden business logic.

## Atomic Generated Artifact

**Decision**: Write `artifacts/configs/<safe-device-name>.cfg` by rendering fully in
memory, creating a temporary sibling, flushing it, and atomically replacing the
target. Create missing directories and remove temporary files after staging or
replacement failure. Ignore `artifacts/`. Permit `--output-dir` for isolated tests.
Require process-level atomicity; do not claim crash-durable persistence.

**Rationale**: The path is obvious, deterministic, and separate from netlab's `lab/`
generated files. Same-directory replacement avoids partial target contents. A prior
valid artifact remains available when retrieval, validation, rendering, or staging
fails.

**Alternatives considered**: `.srl-lab/` suggests topology runtime state. Direct
writes can corrupt a previous artifact. Timestamped paths violate determinism.

## API-Owned Integration Fixtures

**Decision**: The integration test creates every mutable fixture through REST with
one run suffix, including dedicated Status/Namespace and Device
`feature002-leaf-<suffix>` with matching serial marker. It reads immutable ContentType
IDs only for API schemas, records every created ID, and deletes those IDs in reverse
order in `finally` cleanup. The dynamic artifact is asserted semantically and for
repeatability; `leaf01.cfg` remains an offline golden concern.

**Rationale**: The fixture exercises the external contract, avoids UI state, and
cannot delete unrelated records by name or broad filters. It requires no Compose
or Nautobot bootstrap change.

**Alternatives considered**: A permanent seed device pollutes ordinary lab state.
Direct database/Django fixture insertion bypasses the API under test. A custom App
is excluded.
