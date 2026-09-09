# Interface Contracts

## Nautobot Read Contract

The adapter authenticates with the existing API token and sends bounded JSON REST
requests. It accepts an exact Device name and returns raw external data only.

| Resource | Selection | Consumed fields |
|---|---|---|
| `/api/dcim/devices/` | `name=<exact-name>`, `limit=2` | `id`, `name`, `platform.url`, `role.url`, optional `location.url`, `local_config_context_data` |
| URL from `platform.url` | exact related Platform | `network_driver`, optional `display` for diagnostics |
| URL from `role.url` | exact related Role | `display` |
| URL from optional `location.url` | exact related Location | `display` |
| `/api/dcim/interfaces/` | `device_id=<device-uuid>`, paginated | `id`, `name`, `description`, `type.value`, `enabled`, `mgmt_only`, `ip_addresses[].url` |
| URL from `ip_addresses[].url` | exact related object | `address` |

Responses outside these shapes, non-2xx status, invalid JSON, timeout, zero Device
matches, and multiple Device matches are explicit retrieval/conversion failures.
The adapter never returns credentials in errors.

Interface classification is exact: disabled interfaces are ignored; exactly one
interface, under any source name, must be enabled, non-management, type `virtual`,
and resolve to one IPv4 `/32`. Its name is discarded when constructing LoopbackIntent.
Every other enabled, non-management interface must have a type other than `virtual`,
`lag`, `bridge`, or `other` and resolve to exactly one IPv4 address. Missing,
IPv6-only, multiple-address, and non-physical state fail rather than being omitted.

The only BGP-specific source path is:

```text
device.local_config_context_data.network_automation.bgp.local_asn
device.local_config_context_data.network_automation.bgp.neighbors[]
device.local_config_context_data.network_automation.bgp.neighbors[].address
device.local_config_context_data.network_automation.bgp.neighbors[].remote_asn
device.local_config_context_data.network_automation.bgp.neighbors[].description
```

## Python Boundary Contract

```text
NautobotClient.get_device_data(name: str) -> dict[str, object]
device_intent_from_nautobot(raw: Mapping[str, object]) -> DeviceIntent
render_srlinux(intent: DeviceIntent) -> str
artifact_path(intent: DeviceIntent, output_dir: Path) -> Path
write_srlinux_artifact(intent: DeviceIntent, output_dir: Path) -> Path
```

`render_srlinux` rejects unsupported platforms before loading/rendering a template.
It dispatches only on `DeviceIntent.platform == "nokia_srl"`; display labels are
diagnostic and cannot select a renderer. LoopbackIntent renders as `system0.0`.
`write_srlinux_artifact` renders fully before touching the target and atomically
replaces only the deterministic path returned by `artifact_path`.

## CLI Contract

```text
uv run network-render DEVICE [--output-dir DIRECTORY]
```

| Input | Default | Meaning |
|---|---|---|
| `DEVICE` | Required | Exact Nautobot Device name |
| `--output-dir` | `artifacts/configs` | Directory containing the deterministic `<DEVICE>.cfg` target |

Success writes one complete file, prints its path to stdout, and returns 0. Retrieval,
validation, unsupported platform, rendering, or filesystem failure prints one
credential-safe message to stderr and returns nonzero. The CLI does not contact a
network device or invoke Kafka/Temporal.

## Expected SR Linux Sections

For offline `leaf01`, the reviewed golden file contains stable flat `set /`
commands in this order:

1. `system name host-name`.
2. `interface system0` and subinterface 0 state/address, followed by naturally
   sorted routed interface descriptions, state, and addresses.
3. `network-instance default interface <name>.0` attachments in the same order.
4. `network-instance default protocols bgp` admin state, autonomous system,
   router-ID, then numerically sorted neighbor peer-AS and optional descriptions.

The file contains no timestamps, source URLs, credentials, role/location comments,
operational data, or commands for excluded features.

## Integration Fixture Contract

The explicit integration test generates one suffix and uses it in every mutable
fixture name. Through REST it creates a Status, Namespace, Manufacturer, Platform
with `network_driver=nokia_srl`, DeviceType, Role, LocationType, Location, Prefixes,
Device named `feature002-leaf-<suffix>` with corresponding serial marker, three
Interfaces, and three IPAddress assignments. It reads immutable ContentType records
and submits their required `<app_label>.<model>` natural keys to Nautobot creation
schemas. It does not reuse, modify, or delete existing
Status, Namespace, or intent objects. The Device's local context contains only the
namespaced BGP shape documented above.

Every created object ID is recorded at creation time. The production adapter,
converter, renderer, and writer are invoked for the unique Device and checked for
dynamic hostname/path plus deterministic repeated bytes, not against `leaf01.cfg`.
Cleanup deletes only recorded IDs in reverse dependency order inside `finally`; no
broad name/filter deletion is allowed. The test must fail, not skip, when Nautobot
is unavailable.
