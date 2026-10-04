# Data Model: Nautobot Intent To Deterministic SR Linux Artifact

## Scalar Types

- **NonEmptyText**: stripped string with at least one character.
- **DeviceName**: `NonEmptyText` matching `^[A-Za-z0-9][A-Za-z0-9._-]*$`; this is
  both the exact Nautobot lookup value and safe artifact stem.
- **ASN**: integer from 1 through 4294967295 inclusive. Booleans are not accepted
  as integers.
- **InterfaceIPv4**: standard IPv4 interface including prefix length.
- **NeighborIPv4**: standard IPv4 host address without prefix length.

## LoopbackIntent

| Field | Type | Required | Validation |
|---|---|---|---|
| `description` | NonEmptyText or null | No | Source metadata; empty external text normalizes to null |
| `ipv4` | InterfaceIPv4 | Yes | Prefix length exactly `/32` |

The loopback is explicit device intent and has no interface-name field. The adapter
identifies one source virtual interface, while the SR Linux renderer owns the
supported platform name `system0`.

## InterfaceIntent

| Field | Type | Required | Validation |
|---|---|---|---|
| `name` | NonEmptyText | Yes | Stripped and unique across routed interfaces |
| `description` | NonEmptyText | Yes | Required for every routed physical interface |
| `ipv4` | InterfaceIPv4 | Yes | Exactly one IPv4 interface value |

The initial model represents subinterface 0 implicitly. VLAN tags, multiple
subinterfaces, secondary addresses, IPv6, MTU, and operational state are absent.

## BgpNeighborIntent

| Field | Type | Required | Validation |
|---|---|---|---|
| `address` | NeighborIPv4 | Yes | Unique within BgpIntent; cannot equal any local interface host address |
| `remote_asn` | ASN | Yes | 1 through 4294967295 |
| `description` | NonEmptyText or null | No | Empty/whitespace-only external values normalize to null |

## BgpIntent

| Field | Type | Required | Validation |
|---|---|---|---|
| `local_asn` | ASN | Yes | 1 through 4294967295 |
| `neighbors` | tuple of BgpNeighborIntent | Yes | At least one; duplicate addresses rejected |

Neighbor ordering in input is not semantically significant. Rendering orders peers
by numeric IPv4 address.

## DeviceIntent

| Field | Type | Required | Validation |
|---|---|---|---|
| `name` | DeviceName | Yes | Exact source name and deterministic artifact stem |
| `platform` | NonEmptyText | Yes | Stable machine identifier; renderer supports exactly `nokia_srl` |
| `platform_display` | NonEmptyText or null | No | Diagnostic label only; never controls dispatch |
| `role` | NonEmptyText | Yes | Source metadata; not rendered in this feature |
| `location` | NonEmptyText or null | No | Source metadata; not rendered in this feature |
| `loopback` | LoopbackIntent | Yes | Exactly one `/32`; no external interface-name dependency |
| `interfaces` | tuple of InterfaceIntent | Yes | At least one; names unique |
| `bgp` | BgpIntent | Yes | Neighbor/local-address collision rejected |

The models are immutable after successful validation. They own no HTTP, template,
filesystem, or device behavior.

## Raw Nautobot Mapping

The adapter returns one external mapping with this directional shape:

```text
device:
  id, name, platform.url, role.display, location.display|null,
  local_config_context_data
platform:
  network_driver, display
interfaces[]:
  id, name, description, type, enabled, mgmt_only
  ip_addresses[]:
    address
```

Conversion rules:

1. Require exactly one exact-name Device result.
2. Follow `platform.url`; require `network_driver` as the machine identifier and
   retain `display` only as optional diagnostics. Require role; retain location.
3. Ignore disabled interfaces. Treat every enabled, non-management interface as
   initial intent that must be classified rather than silently filtered by address.
4. Require exactly one enabled, non-management interface of type `virtual`, regardless
   of source name; convert only its description and `/32` into `LoopbackIntent`.
5. Classify every other enabled, non-management interface as routed only when type
   is not `virtual`, `lag`, `bridge`, or `other`; reject those non-physical types.
6. Resolve all assigned addresses for each eligible interface and require exactly
   one IPv4 value; reject absent, IPv6-only, and multiple-address state.
7. Read only `local_config_context_data.network_automation.bgp` for BGP values.
8. Normalize whitespace-only optional descriptions to null.
9. Construct DeviceIntent and let model validation reject malformed/cross-field data.

No raw mapping crosses the conversion boundary.

## Acceptance Example

```text
DeviceIntent leaf01
  platform: nokia_srl (display: Nokia SR Linux)
  role: leaf
  location: test-site
  loopback: 10.0.0.1/32 -> rendered as system0.0
  ethernet-1/1: 192.0.2.0/31, "to spine01"
  ethernet-1/2: 192.0.2.2/31, "to spine02"
  local ASN: 65001
  192.0.2.1: remote ASN 65100, "spine01"
  192.0.2.3: remote ASN 65200, "spine02"
```

## State And Failure

The feature has no workflow state machine. Processing is linear:

`requested -> retrieved -> validated -> rendered in memory -> atomically written`

Failure at any step terminates processing. Before the final atomic replacement,
the target is either absent or the previous complete artifact remains unchanged.
