# Display Field Source Map

This map is normative. A missing source yields unavailable/unknown display state, never an inferred
fact.

## Overview And Health

| Displayed field | Exact source | Mapping |
|---|---|---|
| Overall status | API aggregation of component probes | Healthy only when required components are healthy |
| Nautobot status | Nautobot bounded `/health/` HTTP probe | HTTP/application result to safe component state |
| Kafka status | Existing/refactored Kafka Admin metadata probe | Broker metadata available within timeout |
| Temporal status | Temporal namespace/service RPC | Namespace responds within timeout |
| Worker status | Temporal `DescribeTaskQueue` for configured workflow and activity queue | Required poller types have current pollers |
| Consumer status | Kafka Admin `describe_consumer_groups` for configured group | Group has an active member and safe state |
| Device validation capability | Server runtime settings and optional management-network reachability state | Capability only; no overview device read |
| Device count | Nautobot Device list count | Count of returned authoritative devices |
| Active workflows | Temporal visibility lifecycle status | Count admitted running executions |
| Recent successes/failures | Decoded terminal Temporal workflow results | Business result, not Temporal `COMPLETED` alone |
| Recent activity | Newest admitted workflow start/terminal projection | No Kafka reconstruction |

## Device List And Detail

| Displayed field | Exact source | Mapping |
|---|---|---|
| Name | Nautobot Device `name` | Existing device-name validation |
| Role | Nautobot Device Role `display` | Null if absent |
| Platform | Nautobot Platform `network_driver` and `display` | Stable key plus display label |
| Location | Nautobot Location `display` | Null if absent |
| Management address | Nautobot Device `primary_ip4` -> exact IPAddress | Prefix stripped using existing deployment-intent rule |
| Inventory status | Nautobot Device Status `display` | No operational inference |
| Intended hostname | Existing `DeviceIntent.name` | From `get_deployment_intent()` |
| Loopback | Existing `DeviceIntent.loopback.ipv4` | Nautobot normalized intent |
| Routed interfaces | Existing `DeviceIntent.interfaces` | Name, description, IPv4; sorted for display |
| Local ASN | Existing `DeviceIntent.bgp.local_asn` | Namespaced Nautobot config context |
| BGP neighbors | Existing `DeviceIntent.bgp.neighbors` | Address, remote ASN, description |
| Latest deployment | Newest retained matching deploy workflow in Temporal | Exact decoded device name |
| Artifact path/digest/size | Existing `ArtifactIdentity` in Temporal history/result | Root-relative metadata only |
| Artifact availability | Read-only existence check under configured artifact root | No content read/return |
| Historical validation | Existing `DeviceValidationResult`/terminal result in Temporal history | Summary/check counts only |
| Live hostname | Existing SR Linux native read and `ValidationCheck` mapping | Requested device detail only |
| Live interfaces/addresses | Existing expected paths and validation checks | Expected interfaces only |
| Live BGP state | Existing expected paths and validation checks | Expected neighbors only |
| Intent/live mismatch | Existing failed `ValidationCheck` values | No extra drift/compliance calculation |

## Workflow And Deployment

| Displayed field | Exact source | Mapping |
|---|---|---|
| Workflow ID | Temporal visibility/history | Accepted prefixes only |
| Run ID | Temporal visibility | Exact run pin |
| Workflow kind | Trusted workflow-ID prefix plus decoded input consistency | Render or deployment |
| Event ID | Decoded existing workflow start input | Null if unavailable; suffix is consistency check only |
| Correlation ID | Decoded existing workflow start input | Null if unavailable |
| Device name | Decoded existing workflow start input | Null if unavailable |
| Execution status | Temporal visibility/description | Raw enum mapped to safe enum |
| Business outcome | Decoded existing terminal workflow result | Domain failure differs from Temporal failure |
| Start/end/duration | Temporal visibility/history timestamps | Duration computed only from those timestamps |
| Current stage | Pending activity plus latest known history event | Allowlisted activity map |
| Stage timestamps | Temporal activity history events | Correlated by scheduled event ID |
| Retry count | Maximum `ActivityTaskStarted.attempt` or pending activity attempt | Null when unsafe/unavailable |
| Failure stage/category | Existing `DeploymentFailed`/`RenderFailed`; execution status for orchestration failure | Allowlisted only |
| Failure message | Static API category text or existing known-safe domain summary | Raw Temporal failure text excluded |
| Deployment time | Existing `DeploymentResult.deployed_at`/terminal deployment result | Null before successful Set |
| Validation status | Existing `DeviceValidationResult` or terminal deployment result | Never inferred from workflow completion alone |
| Result publication | Completed `publish_render_result` activity | Indicates activity return, not Kafka coordinates |

## Topology

| Displayed field | Exact source | Mapping |
|---|---|---|
| Node identity/role/platform | Nautobot Device relationships | One node per exact device name |
| Node status | Latest retained validation/deployment outcome, else inventory status where safely mapped | Source is shown; unsupported becomes unknown |
| Physical link endpoints | Nautobot cable/connected endpoint relationships | Exact endpoints only |
| Logical BGP link endpoints | Nautobot BGP neighbor address plus exact unique Nautobot interface-IP ownership | Marked `bgp`; never called physical |
| Link status | Explicit endpoint/validation evidence only | Unknown by default |

## Intentionally Unavailable

- Kafka topic, partition, offset, request source, and request time are not retained in Temporal.
- Poison messages that never start Temporal are not represented.
- Full historical analytics beyond Temporal retention are unavailable.
- Raw rendered configuration, raw history, raw stack traces, and raw external responses are never
  display sources.
- Physical links are unavailable when Nautobot has no cable/endpoint relationship; BGP logical
  intent is not relabeled as physical connectivity.
