# SR Linux Device State Contract

## Configuration Application

- Image: `ghcr.io/nokia/srlinux:26.7.2-519`.
- Transport: gNMI; CLI origin with ASCII for Set, native origin with JSON-IETF for Get.
- Set payload: complete digest-verified Feature 002 artifact in one update transaction.
- Repeatability: keyed declarations converge to the same values; unmentioned stale state is
  not removed and concurrent different device requests are not serialized by this feature.

Before any Capabilities/Get/Set RPC, disable pyGNMI's installed client logger/debug output.
Pre-write identity requires Capabilities to advertise the native `srl_nokia-system` model
and native hostname `/system/name/host-name` to equal the requested/bootstrap node name.
The topology may bootstrap only that hostname identity plus containerlab's management and
gNMI access. An absent or different hostname remains a permanent pre-write failure.
Hostname, interface/subinterface admin state, local ASN, and peer ASN are read with gNMI
datatype `all` because the pinned release exposes them as configuration data. Interface
oper state, address status, and BGP session state use datatype `state`.
Nautobot platform must be exactly `nokia_srl`; any mismatch is permanent before Set.

## Required Reads

| Check | Native path | Required value |
|---|---|---|
| Hostname | `/system/name/host-name` | requested name |
| Interface admin/oper | `/interface[name=N]/admin-state`, `/oper-state` | `enable`, `up` |
| Subinterface admin/oper | `/interface[name=N]/subinterface[index=0]/admin-state`, `/oper-state` | `enable`, `up` |
| Address existence/readiness | `/interface[name=N]/subinterface[index=0]/ipv4/address[ip-prefix=P]/status` | response path has exact key `P`; value `preferred` |
| Local ASN | `/network-instance[name=default]/protocols/bgp/autonomous-system` | intended integer |
| Peer ASN | `/network-instance[name=default]/protocols/bgp/neighbor[peer-address=A]/peer-as` | intended integer |
| Peer session | same neighbor plus `/session-state` | `established` |

Apply interface checks to `system0` and every modeled routed interface; physical oper and
BGP established checks are required in the two-node acceptance topology.

## Response Normalization

- Iterate all `response["notification"]` entries and `notification.get("update", [])`.
- Returned paths may contain YANG module prefixes and must be semantically normalized.
- A valid absent value is a successful notification with no `update`; it is not `None` or
  gRPC `NOT_FOUND`.
- An invalid schema path is a permanent `INVALID_ARGUMENT` response.
- Preserve native JSON-IETF types. Do not coerce ASN integers to arbitrary strings.
- Require exactly one matching value; reject malformed, duplicate, or conflicting updates.
- Never expose raw response or exception text outside the device boundary.

Canonical Ubuntu x86-64 T001 confirmed all listed paths and values on the pinned image.
Hostname/admin/oper/address-status/session values are strings; local and peer ASNs are
integers. The configured address list's `/ip-prefix` leaf returns no update, so it is not a
validation path; exact address identity comes from the normalized `/status` response path's
`ip-prefix` key. Same-payload Set repetition, atomic `ABORTED` rejection, and valid-absent
versus invalid-path behavior were also confirmed.
