# Research: SR Linux Deployment And Operational Validation

**Date**: 2026-09-10

This research resolves the Feature 004 transport, write, inventory, topology, retry,
compatibility, and runtime decisions. Documentation findings were supplemented by a
disposable real-device probe against the pinned canonical image. No application source
was implemented.

## Python gNMI Client

**Decision**: Pin `pygnmi==0.8.15` and isolate it inside one explicit SR Linux module.

**Rationale**:

- The March 2025 stable release implements Capabilities, Get, Set, and Subscribe, carries
  a BSD-3-Clause license, ships a 35.6 KiB pure-Python wheel, and explicitly lists Nokia
  SR Linux interoperability.
- It supports Python 3.12 in the canonical environment despite older classifiers. A real
  `uvx --from pygnmi==0.8.15` probe installed and imported it successfully.
- Its direct dependencies are `grpcio`, `protobuf`, `cryptography`, and `dictdiffer`; it
  does not bring a network-automation framework, inventory, driver registry, or worker.
- Its path generator represents an empty CLI-origin path with `/cli://`, and
  `set(update=[("/cli://", artifact)], encoding="ascii")` constructs exactly one
  `ascii_val` update containing the complete multiline artifact.

**Required containment**: pyGNMI installs its own stdout handler and includes raw SR Linux
error details in critical logs. A pinned-device rejection probe demonstrated that those
details can contain the submitted configuration. The SR Linux module MUST disable the
`pygnmi.client` logger before any RPC, MUST never enable pyGNMI debug output, and MUST map
exceptions by gRPC code/context to static safe messages without serializing exception
text. Unit and real rejection tests must assert raw artifact and credentials are absent.

**Alternatives considered**:

- Vendoring OpenConfig protobuf output and using `grpcio` directly gives maximum control
  but adds generated code and hand-built RPC/path/value handling with no current benefit.
- `gnmic` is a well-supported Go client but would require shelling out and parsing process
  output, violating the in-process application boundary.
- Nornir, NAPALM, Scrapli, and generic device frameworks add abstractions and transports
  that this single-vendor feature neither needs nor permits.

Sources: [pyGNMI 0.8.15 on PyPI](https://pypi.org/project/pygnmi/0.8.15/),
[pyGNMI source](https://github.com/akarneliuk/pygnmi), and
[release v0.8.15](https://github.com/akarneliuk/pygnmi/releases/tag/v0.8.15).

## Exact Configuration Write

**Decision**: Send the unchanged Feature 002 artifact as one gNMI Set `update` with path
origin `cli`, no path elements, and `ascii_val` containing all `set / ...` lines. Do not
use gNMI `replace`.

**Rationale**:

- Feature 002's accepted artifact is deterministic full-context SR Linux `set / ...`
  text. SR Linux explicitly supports this format through the gNMI `cli`/`srlinux_cli`
  origin and commits the supplied commands through its private candidate.
- Every operation in one SetRequest is one transaction. If any command fails, SR Linux
  rolls back all changes and returns an error.
- `update` changes only explicitly supplied paths and preserves containerlab's management,
  credential, and gNMI bootstrap configuration. CLI-origin `replace` would replace the
  whole device configuration from blank state and could remove management access.
- Sending the artifact through the documented gNMI origin consumes Feature 002 bytes
  directly. Producing native JSON-IETF would require a second renderer or a CLI parser,
  either duplicating accepted rendering logic or creating a new configuration compiler.

**Pinned-release verification**: A disposable `ghcr.io/nokia/srlinux:26.7.2-519` node on
the Ubuntu reference host negotiated JSON-IETF and ASCII. pyGNMI 0.8.15 applied a
two-line multiline CLI-origin update twice. Both SetResponses reported `UPDATE`, and
independent native Get before/after returned hostname `probe01`. This proves the selected
call shape and same-payload retry on the pinned build.

A separate request included one valid marker command followed by an invalid command.
SR Linux returned gRPC `ABORTED`, and independent native state confirmed the marker was
absent before and after. This proves atomic rejection and also means Set `ABORTED` is a
permanent configuration rejection, not a generic transient error.

**Idempotency guarantee**: Repeating the same keyed `set / ...` declarations converges to
the same values and creates no duplicate list entries. The operation does not remove
unmentioned stale configuration and is not a full desired-state replacement. Concurrent
independent requests for one device are not serialized; digest checks prevent one request
from deploying bytes overwritten at its deterministic path, but cross-request ordering is
otherwise outside this feature.

**Approval point**: Although the application transport is gNMI and no SSH/CLI process is
used, the gNMI value uses SR Linux's documented CLI origin because that is the only clean
way to consume the accepted artifact unchanged. This explicit tradeoff requires approval.

Source: [SR Linux 26.3 gNMI Set and CLI-origin documentation](https://documentation.nokia.com/srlinux/26-3/books/system-mgmt/gnmi.html).
Exact behavior was verified on the pinned 26.7.2-519 image.

## Artifact And Deployment Identity

**Decision**: For a deployment request, one preparation activity performs one Nautobot
read, invokes Feature 002's sole renderer/writer, computes SHA-256 and byte count from the
exact rendered bytes before atomic replacement, and returns the artifact identity, target,
and expected checks together. It validates bounded ASCII full-context `set / ...` shape
with exactly one requested hostname command. The deploy activity rereads the path and
requires the same digest before every mutation attempt.

**Rationale**: Binding digest, target, and expected state in the same activity that renders
eliminates a race in which another request could overwrite the deterministic path before a
later activity first identifies it. A digest in workflow history is the smallest immutable
link between rendered bytes and later retry; no raw artifact enters history. If another
request overwrites the path after preparation, deployment fails before mutation.

**Alternatives considered**: An artifact database/service is prohibited. Path alone does
not detect replacement. Adding a sidecar manifest adds another file without improving on
the small typed preparation result. Passing raw configuration through Temporal exposes
configuration in history and increases payload size.

## Management Address Authority

**Decision**: Require the exact Nautobot Device `primary_ip4` relationship, follow its
related IPAddress URL, parse the host portion, and use it as the gNMI target. The IP must
be assigned to the device, which Nautobot itself enforces when setting a primary address.

**Rationale**: `primary_ip4` is a core authoritative device relationship in Nautobot
2.4.41. It avoids custom fields, custom Apps, environment address maps, container-name
assumptions, and workflow hardcoding. The existing adapter can add one deployment-specific
read/conversion without changing `DeviceIntent` or Feature 002 rendering.

**Failure**: Null, malformed, non-IPv4, unsafe relation URL, or inconsistent relation data
is permanent `management_address_invalid` before device mutation.

Source: [Nautobot 2.4 Device model](https://github.com/nautobot/nautobot/blob/ltm-2.4/nautobot/dcim/models/devices.py).

## Native Operational Reads

**Decision**: Use native-origin, JSON-IETF, leaf-level gNMI Get requests. Iterate every
notification and optional update, normalize module-qualified response paths to semantic
path elements, preserve native value types, and require exactly one matching value.

| Invariant | Native path | Expected |
|---|---|---|
| Hostname | `/system/name/host-name` | requested device name |
| Interface admin | `/interface[name=NAME]/admin-state` | `enable` |
| Interface oper | `/interface[name=NAME]/oper-state` | `up` |
| Subinterface admin | `/interface[name=NAME]/subinterface[index=0]/admin-state` | `enable` |
| Subinterface oper | `/interface[name=NAME]/subinterface[index=0]/oper-state` | `up` |
| IPv4 address/readiness | `/interface[name=NAME]/subinterface[index=0]/ipv4/address[ip-prefix=PREFIX]/status` | response key exact prefix; value `preferred` |
| Local ASN | `/network-instance[name=default]/protocols/bgp/autonomous-system` | intended integer |
| Peer ASN | `/network-instance[name=default]/protocols/bgp/neighbor[peer-address=ADDRESS]/peer-as` | intended integer |
| Peer session | same neighbor path plus `/session-state` | `established` |

Hostname, admin states, address presence, local ASN, neighbor presence, and peer ASN are
deterministic configuration invariants. Interface/subinterface oper state, address
`preferred`, and BGP `established` are convergence-dependent operational invariants.

Sources: Nokia's official
[SR Linux v26.7.2 YANG tag](https://github.com/nokia/srlinux-yang-models/tree/v26.7.2),
[26.3 gNMI guide](https://documentation.nokia.com/srlinux/26-3/books/system-mgmt/gnmi.html),
and [26.3 BGP guide](https://documentation.nokia.com/srlinux/26-3/books/routing-protocols/bgp.html).
**Pinned ARM64 probe**: pyGNMI 0.8.15 returned a dictionary containing a
`notification` list. Each present leaf was an `update` item with string `path` and native
`val`; hostname and state enums were Python strings. Returned paths were module-qualified,
for example `srl_nokia-system:system/srl_nokia-system-name:name/host-name`, rather than
echoing the unqualified request. A valid but absent leaf returned a successful notification
with the `update` key omitted. An invalid schema path raised gRPC `INVALID_ARGUMENT`.
Therefore parsing MUST use `notification.get("update", [])`, distinguish absence from an
invalid path, reject duplicate/conflicting values, and never select the first update
silently.

The ARM64 preview image encountered an `sr_net_inst_mgr` namespace assertion under Docker
Desktop, so it could not verify complete state. Canonical T001 then ran on Ubuntu 24.04
x86-64 with Docker 29.1.3, containerlab 0.79.0, netlab 26.08, pyGNMI 0.8.15, and native
amd64 image digest `sha256:0096fe3ebcafabb7253492e2060425fe027a168e0e066766d1e85efbb0b48be8`.

The canonical two-node probe confirmed hostname/admin/oper/status/session values as Python
strings; local and peer ASNs as Python integers; physical and loopback state `up`; address
status `preferred`; and BGP `established`. The requested address-list `/ip-prefix` leaf was
valid but absent even for configured addresses. Address existence MUST therefore be proven
by requiring exactly one `/status` update whose normalized response path contains the exact
requested `ip-prefix` list key, with value `preferred`; no separate `/ip-prefix` leaf Get is
used. The same full multiline Set succeeded twice on both nodes. A valid marker plus invalid
command returned `ABORTED` and left the marker absent; an invalid schema path returned
`INVALID_ARGUMENT`.

Both disposable nodes, link, lab directory, host entries, SSH fragment, and
`f004-t001-mgmt` network were removed. Existing supporting containers remained healthy.

## Renderer Compatibility Correction

**Decision**: Narrowly extend Feature 002's sole SR Linux renderer so global BGP enables
IPv4 unicast, each deterministic remote-AS peer group sets its peer AS, and each neighbor
references its group. Keep the same intent model, rendering entry point, deterministic
artifact path, atomic write, and `set / ...` artifact format.

The pinned image rejected the currently accepted BGP output with `FAILED_PRECONDITION`:
one address family must be enabled and every neighbor must reference a peer group. A
deployable artifact therefore requires declarations equivalent to:

```text
set / network-instance default protocols bgp afi-safi ipv4-unicast admin-state enable
set / network-instance default protocols bgp group peer-as-65001 peer-as 65001
set / network-instance default protocols bgp neighbor 192.0.2.1 peer-group peer-as-65001
```

This is a compatibility fix inside the accepted renderer, not a second renderer or a
deployment-side transformation. Existing golden tests must be deliberately updated and
Feature 002 real Nautobot rendering rerun.

The first canonical full transaction using the initially planned per-group address-family
path was rejected. Replacing it with the global `bgp afi-safi` path succeeded twice on
both nodes and formed the eBGP session. This material T001 correction was made before any
source implementation and requires renewed approval.

## Request And Workflow Compatibility

**Decision**: Add `network.deployment.requested` v1 rather than reinterpret
`network.render.requested` v1. The existing consumer subscribes to both request topics and
starts the same `RenderDeviceConfigWorkflow` class with a distinct typed input. Existing
render requests retain their exact activity sequence, result, topic semantics, workflow
ID `render-device-config:<event_id>`, and conflict/reuse policies. Deployment requests use
`deploy-device-config:<event_id>` with the same policies.

**Rationale**: A retained or delayed render-only record must not begin mutating a device
after a software upgrade. A v2 payload on the old topic would be committed as poison by an
older consumer. A dedicated request topic is an additive entry contract, not event
choreography between render and deploy; Temporal still owns the entire internal sequence.

The new durable input includes `operation="deploy"`; the existing render input has no such
field, so Pydantic/Temporal union decoding is unambiguous. Existing inputs execute the
original path, so no Temporal patch marker is necessary. Replay tests with Temporal
`Replayer` against representative accepted Feature 003 success/failure histories are
mandatory. Existing render workflow/activity names and external payloads remain unchanged.

**Alternatives considered**: Silently extending v1 requires Temporal patching and violates
event meaning. A separate deployment workflow duplicates orchestration. A render-completed
consumer creates choreography and splits durable ownership.

## Event Semantics

**Decision**: Preserve all three Feature 003 events unchanged and add three v1 events:
`network.deployment.requested`, `network.deployment.completed`, and
`network.deployment.failed`. A deployment request emits exactly one logical deployment
outcome; it never emits an existing render result with an incompatible deployment workflow
ID. Rendering failure inside preparation is reported as `DeploymentFailed` at stage
`prepare`, leaving every `network.render.*` meaning and sequence unchanged.

Deployment result event IDs and timestamps are created once by deterministic workflow
APIs. Kafka publication may be physically at least once under uncertainty, while stable
event identity provides one logical outcome. Validation checks remain in workflow result
data and logs; they are not emitted individually.

## Retry And Error Classification

**Decision**:

| Activity | Attempts/bound | Retryable | Permanent |
|---|---|---|---|
| Prepare | 3 attempts; 1s exponential to 5s; 60s each | Nautobot transport/server and transient artifact I/O | invalid artifact, target/address/intent mismatch, unsupported shape |
| Deploy | 3 attempts; 2s exponential to 10s; 30s each | `UNAVAILABLE`, `DEADLINE_EXCEEDED`, temporary connection refusal | authentication/permission, identity/platform mismatch, Set `ABORTED`/`INVALID_ARGUMENT`/`FAILED_PRECONDITION`, digest mismatch |
| Validate | 12 attempts; 2s coefficient 1.5 to 5s; 15s each; 90s schedule bound | read connectivity and operational non-convergence | authentication, deterministic config mismatch, unsupported/malformed response |
| Publish | Existing 5 attempts; 1s exponential to 10s; 30s each | result transport failures | none added |

Unknown and `FAILED_PRECONDITION` Set failures are permanent because pyGNMI does not expose
a safe structured distinction between a temporary candidate lock and the pinned image's
observed deterministic precondition rejection. The workflow retains the 10-minute
execution timeout. The device client uses a 10-second
RPC/connect timeout and never uses pyGNMI's internal sleep/retry helper; Temporal is the
only retry owner. Validation retries only the validation activity. Deployment retry does
not rerender or prepare again; validation retry does not redeploy.

## Credentials And TLS

**Decision**: Add optional worker settings for username/password, global port `57401`,
10-second timeout, and literal local-lab TLS mode `insecure`. Deployment fails permanently
as `device_settings_missing` when credentials are absent, allowing Feature 003 render-only
startup to remain compatible. `.env.example` documents containerlab's development values;
Compose passes them only to the worker. Credentials never enter models, events, history,
artifact, command output, or logs.

**Rationale**: Containerlab explicitly supplies an isolated lab-only insecure gNMI server
on 57401. Supporting generated-CA distribution or production TLS policy is outside scope.
No gNMI port is published to the public host interface.

Source: [containerlab SR Linux management, credentials, TLS, and gRPC](https://containerlab.dev/manual/kinds/srl/).

## Topology And Worker Connectivity

**Decision**: Replace the create-only one-node scaffold with one dedicated two-node
point-to-point topology named `feature004`, using fixed test-owned identities:

- `f004-spine01`: management `172.31.46.11/24`, loopback `10.0.0.1/32`,
  `ethernet-1/1` `192.0.2.0/31`, ASN 65000, peer 192.0.2.1 ASN 65001.
- `f004-leaf01`: management `172.31.46.12/24`, loopback `10.0.0.2/32`,
  `ethernet-1/1` `192.0.2.1/31`, ASN 65001, peer 192.0.2.0 ASN 65000.

Run with netlab 26.8.0 and containerlab 0.79.0 from `lab/` using
`netlab up topology.yml -p clab --no-config`, so netlab/containerlab create only
nodes, link, management, and default gNMI bootstrap; the application supplies intended
device configuration. Use dedicated topology-owned Docker network
`network-lab-devices-mgmt`. Keeping generated netlab files below `lab/` prevents its
cleanup from colliding with the repository's checked-in root `config/` directory.

Add a small `compose.device-access.yaml` override that attaches the existing
`automation-worker` to both Compose `default` and the topology-created external management
network. Base Compose and Feature 003 startup remain valid without a device topology.
Acceptance starts topology before the override and removes the worker container before
`netlab down --cleanup`; a stopped container still owns a network endpoint. The consumer
remains only on the default network.

Fresh containerlab default configuration leaves `/system/name/host-name` absent. Because
the approved pre-write identity gate must reject absence and require exact equality before
Set, the owner approved a narrow correction on 2026-09-10: each topology node references a
one-line partial CLI startup file containing only its expected hostname. Containerlab still
owns management reachability and gNMI access; Nautobot/automation own loopback, routed
interfaces, BGP, policy, rendering, deployment, and validation. This is identity bootstrap,
not DHCP/ZTP, discovery, onboarding, or preloading acceptance intent.

Canonical execution confirmed both one-line hostname overlays were applied. Initial
`datatype=state` probes reported valid absence because hostname is a configuration leaf;
`datatype=all` returned each exact expected hostname. Canonical happy-path validation then
confirmed admin state, local ASN, and peer ASN are likewise configuration leaves. The
concrete client uses `all` for those configuration invariants and `state` for oper state,
address status, and BGP session state.

A canonical probe showed containerlab removes even a matching pre-created network during
destroy, so Compose MUST NOT own or pre-create the topology network. The explicit override
and teardown order avoid hidden lifecycle coupling and prevent network removal failure.

**Alternatives considered**: A host-side worker risks competing task-queue pollers. Host
port forwarding needs per-device ports and makes environment configuration compete with
inventory. Imperative `docker network connect` is drift-prone. A new proxy/service or
worker is prohibited.

## Direct CLI

**Decision**: Add no direct deployment or diagnostic CLI. Extend
`network-render-request DEVICE` with an explicit `--deploy` flag that publishes the new
deployment request and prints the deployment workflow ID; omission retains exact Feature
003 render behavior. Real integration performs independent client reads directly. A
direct mutation CLI would bypass the canonical workflow and a read-only CLI would duplicate
validation activity logic without sufficient additional value.
