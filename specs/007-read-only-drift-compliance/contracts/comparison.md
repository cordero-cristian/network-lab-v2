# Configuration Drift and Operational Health Contract

## Input Contract

The pure comparison accepts:

1. One accepted `ExpectedDeviceState` derived directly from normalized Nautobot `DeviceIntent`.
2. One normalized observed mapping returned by the existing structured SR Linux read.
3. One timezone-aware UTC `observed_at` value.

It performs no I/O, rendering, artifact access, policy lookup, persistence, or remediation.

## Classification Matrix

| Expected object/fact | Native observed path | Configuration check | Operational check |
|---|---|---|---|
| Device hostname | `/system/name/host-name` | equals intended device name | none |
| Loopback/routed interface | `/interface[name=N]/admin-state` | equals `enable` | none |
| Loopback/routed interface | `/interface[name=N]/oper-state` | none | equals `up`; null is unavailable |
| Loopback/routed subinterface 0 | `/interface[name=N]/subinterface[index=0]/admin-state` | equals `enable` | none |
| Loopback/routed subinterface 0 | `/interface[name=N]/subinterface[index=0]/oper-state` | none | equals `up`; null is unavailable |
| Expected IPv4 prefix | `/interface[name=N]/subinterface[index=0]/ipv4/address[ip-prefix=P]/status` | non-null means present; null means mismatch | `preferred` is healthy; non-null other value unhealthy; null unavailable |
| BGP process | `/network-instance[name=default]/protocols/bgp/autonomous-system` | exact intended integer | none |
| Expected BGP neighbor | neighbor `/peer-as` | exact intended integer; null mismatches | none |
| Expected BGP neighbor | neighbor `/session-state` | none | `established` is healthy; non-null other value unhealthy; null unavailable |

Configuration scalar equality is both value- and type-exact. In particular, an ASN string does not
match an intended integer. Before constructing any checks, hostname/admin/oper/address-status/session
leaves must be non-empty strings of at most 128 characters and ASN/peer-AS leaves must be exact integers (not booleans).
Any present leaf with the wrong scalar type, empty text, or over-bound text invalidates the entire
current comparison. Correctly typed unequal configuration values are drift; correctly typed
non-target operational strings are unhealthy.

## Ordering

Configuration checks are deterministic:

1. Hostname.
2. For `system0`, admin, subinterface admin, and address presence.
3. For each routed interface in expected-state order, admin, subinterface admin, and address presence.
4. Local ASN.
5. Peer-AS for each neighbor in expected-state order.

Operational checks are deterministic:

1. For `system0`, interface oper, subinterface oper, and address readiness.
2. For each routed interface in expected-state order, interface oper, subinterface oper, and address readiness.
3. Session state for each neighbor in expected-state order.

No check is created for an unexpected extra object because no extra-object enumeration occurs.

## Aggregate Rules

Configuration:

```text
all checks match -> in_sync
one or more mismatches -> drifted
intent/read boundary unavailable -> no result; API observation unavailable
```

Operational health:

```text
all checks healthy -> healthy
at least one healthy/unhealthy check and any unhealthy/unavailable -> degraded
all checks unavailable -> unavailable
```

Examples:

| Observed condition | Configuration | Operational health |
|---|---|---|
| Matching peer-AS, session idle | `in_sync` for neighbor config | `degraded` for session |
| Expected address present, status duplicate | `match` for presence | `unhealthy` for readiness |
| Expected address absent | `mismatch` for presence | `unavailable` for readiness |
| Wrong peer-AS, session established | `drifted` for peer-AS | `healthy` for session |
| Device read fails | unavailable observation | unavailable observation |

## Safety Contract

- Messages are static and bounded; raw response values are exposed only as already normalized safe
  scalar evidence.
- Raw gNMI payloads, exceptions, credentials, rendered configuration, and artifact contents are
  never accepted or returned by this comparison.
- Duplicate/conflicting response paths and invalid response structures fail at the existing device
  boundary before comparison.
- Feature 007 leaf-type validation occurs in the pure comparison boundary and does not change
  Feature 004 response normalization or deployment validation behavior.
