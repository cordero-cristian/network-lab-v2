import type { ApiErrorBody } from "./types";

export class ApiError extends Error {
  constructor(public readonly status: number, public readonly code: string, message: string) {
    super(message);
    this.name = "ApiError";
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function hasFields(value: unknown, fields: string[]): value is Record<string, unknown> {
  return isRecord(value) && fields.every((field) => field in value);
}

const isString = (value: unknown): value is string => typeof value === "string";
const isNullableString = (value: unknown): value is string | null => value === null || isString(value);
const isNullableNumber = (value: unknown): value is number | null => value === null || typeof value === "number";
const isScalar = (value: unknown): value is string | number | boolean => ["string", "number", "boolean"].includes(typeof value);

function isAvailability(value: unknown): boolean {
  return hasFields(value, ["source", "status", "observed_at", "duration_ms", "code", "message"])
    && isString(value.source) && isString(value.status) && isString(value.observed_at)
    && isNullableNumber(value.duration_ms) && isNullableString(value.code) && isNullableString(value.message);
}

function isArtifact(value: unknown): boolean {
  return hasFields(value, ["relative_path", "sha256", "byte_count", "available"])
    && isString(value.relative_path) && isNullableString(value.sha256)
    && isNullableNumber(value.byte_count) && typeof value.available === "boolean";
}

function isValidation(value: unknown): boolean {
  return hasFields(value, ["status", "validated_at", "checks_total", "checks_failed"])
    && isString(value.status) && isNullableString(value.validated_at)
    && isNullableNumber(value.checks_total) && isNullableNumber(value.checks_failed);
}

function isDeployment(value: unknown): boolean {
  return hasFields(value, ["workflow_id", "run_id", "device_name", "status", "artifact", "deployed_at", "completed_at", "duration_ms", "validation_status", "failure_stage", "failure_category"])
    && isString(value.workflow_id) && isString(value.run_id) && isNullableString(value.device_name)
    && isString(value.status) && (value.artifact === null || isArtifact(value.artifact))
    && isNullableString(value.deployed_at) && isNullableString(value.completed_at)
    && isNullableNumber(value.duration_ms) && isString(value.validation_status)
    && isNullableString(value.failure_stage) && isNullableString(value.failure_category);
}

function isWorkflow(value: unknown): boolean {
  return hasFields(value, ["workflow_id", "run_id", "kind", "event_id", "correlation_id", "device_name", "execution_status", "outcome", "started_at", "completed_at", "duration_ms", "current_stage", "failure_category", "data_status"])
    && isString(value.workflow_id) && isString(value.run_id) && isString(value.kind)
    && isNullableString(value.event_id) && isNullableString(value.correlation_id) && isNullableString(value.device_name)
    && isString(value.execution_status) && isString(value.outcome) && isString(value.started_at)
    && isNullableString(value.completed_at) && isNullableNumber(value.duration_ms)
    && isNullableString(value.current_stage) && isNullableString(value.failure_category) && isString(value.data_status);
}

function isTopologyNode(value: unknown): boolean {
  return hasFields(value, ["id", "label", "role", "platform", "status", "status_source"])
    && isString(value.id) && isString(value.label) && isNullableString(value.role)
    && isNullableString(value.platform) && isString(value.status) && isNullableString(value.status_source);
}

function isTopologyLink(value: unknown): boolean {
  return hasFields(value, ["id", "kind", "source_device", "source_interface", "target_device", "target_interface", "status"])
    && isString(value.id) && isString(value.kind) && isString(value.source_device)
    && isNullableString(value.source_interface) && isString(value.target_device)
    && isNullableString(value.target_interface) && isString(value.status);
}

function isTopology(value: unknown): value is Record<string, unknown> {
  return hasFields(value, ["nodes", "links", "availability"])
    && Array.isArray(value.nodes) && value.nodes.every(isTopologyNode)
    && Array.isArray(value.links) && value.links.every(isTopologyLink)
    && isAvailability(value.availability);
}

function isDeviceSummary(value: unknown): boolean {
  return hasFields(value, ["name", "role", "platform", "location", "management_address", "inventory_status", "last_deployment", "validation_status", "observed_at"])
    && isString(value.name) && isNullableString(value.role) && isNullableString(value.platform)
    && isNullableString(value.location) && isNullableString(value.management_address)
    && isNullableString(value.inventory_status) && (value.last_deployment === null || isDeployment(value.last_deployment))
    && isString(value.validation_status) && isString(value.observed_at);
}

function isEnvelope(value: unknown, validateData: (data: unknown) => boolean): boolean {
  return hasFields(value, ["availability", "data"])
    && isAvailability(value.availability) && (value.data === null || validateData(value.data));
}

function isIntent(value: unknown): boolean {
  return hasFields(value, ["hostname", "loopback", "routed_interfaces", "bgp_local_asn", "bgp_neighbors"])
    && isString(value.hostname) && isNullableString(value.loopback)
    && Array.isArray(value.routed_interfaces) && value.routed_interfaces.every((item) => hasFields(item, ["name", "ipv4"]) && isString(item.name) && isString(item.ipv4) && (!("description" in item) || isNullableString(item.description)))
    && isNullableNumber(value.bgp_local_asn)
    && Array.isArray(value.bgp_neighbors) && value.bgp_neighbors.every((item) => hasFields(item, ["address", "remote_asn"]) && isString(item.address) && typeof item.remote_asn === "number" && (!("description" in item) || isNullableString(item.description)));
}

function isCheck(value: unknown): boolean {
  return hasFields(value, ["name", "status", "expected", "observed", "message"])
    && isString(value.name) && isString(value.status) && isScalar(value.expected)
    && (value.observed === null || isScalar(value.observed)) && isNullableString(value.message);
}

function isLiveState(value: unknown): boolean {
  return hasFields(value, ["status", "hostname", "interfaces", "bgp", "mismatch_count", "validated_at"])
    && isString(value.status) && (value.hostname === null || isCheck(value.hostname))
    && Array.isArray(value.interfaces) && value.interfaces.every(isCheck)
    && Array.isArray(value.bgp) && value.bgp.every(isCheck)
    && typeof value.mismatch_count === "number" && isNullableString(value.validated_at);
}

function isHealth(value: unknown): boolean {
  return hasFields(value, ["overall_status", "observed_at", "nautobot", "kafka", "temporal", "worker", "consumer", "device_validation"])
    && isString(value.overall_status) && isString(value.observed_at)
    && [value.nautobot, value.kafka, value.temporal, value.worker, value.consumer, value.device_validation].every(isAvailability);
}

function isStage(value: unknown): boolean {
  return hasFields(value, ["sequence", "key", "label", "status", "scheduled_at", "started_at", "completed_at", "duration_ms", "attempts", "failure_category", "failure_message"])
    && typeof value.sequence === "number" && isString(value.key) && isString(value.label) && isString(value.status)
    && isNullableString(value.scheduled_at) && isNullableString(value.started_at) && isNullableString(value.completed_at)
    && isNullableNumber(value.duration_ms) && isNullableNumber(value.attempts)
    && isNullableString(value.failure_category) && isNullableString(value.failure_message);
}

function matchesContract(path: string, body: unknown): boolean {
  const pathname = path.split("?", 1)[0];
  if (pathname === "/api/health") return isHealth(body);
  if (pathname === "/api/overview") return hasFields(body, ["observed_at", "health", "devices", "workflows", "deployments", "topology", "activity"])
    && isString(body.observed_at) && isHealth(body.health)
    && hasFields(body.devices, ["availability", "total"]) && isAvailability(body.devices.availability) && isNullableNumber(body.devices.total)
    && hasFields(body.workflows, ["availability", "active_count", "recent"]) && isAvailability(body.workflows.availability) && isNullableNumber(body.workflows.active_count) && Array.isArray(body.workflows.recent) && body.workflows.recent.every(isWorkflow)
    && hasFields(body.deployments, ["availability", "recent_successes", "recent_failures"]) && isAvailability(body.deployments.availability) && Array.isArray(body.deployments.recent_successes) && body.deployments.recent_successes.every(isDeployment) && Array.isArray(body.deployments.recent_failures) && body.deployments.recent_failures.every(isDeployment)
    && isTopology(body.topology)
    && hasFields(body.activity, ["availability", "items"]) && isAvailability(body.activity.availability) && Array.isArray(body.activity.items) && body.activity.items.every(isWorkflow);
  if (pathname === "/api/topology") return isTopology(body) && isString(body.observed_at);
  if (pathname === "/api/devices") return hasFields(body, ["items", "count", "observed_at", "availability"])
    && Array.isArray(body.items) && body.items.every(isDeviceSummary) && typeof body.count === "number"
    && isString(body.observed_at) && isAvailability(body.availability);
  if (pathname.startsWith("/api/devices/")) return hasFields(body, ["summary", "intent", "latest_artifact", "latest_deployment", "historical_validation", "live_state"])
    && isDeviceSummary(body.summary) && isEnvelope(body.intent, isIntent)
    && isEnvelope(body.latest_artifact, isArtifact) && isEnvelope(body.latest_deployment, isDeployment)
    && isEnvelope(body.historical_validation, isValidation) && isEnvelope(body.live_state, isLiveState);
  if (pathname === "/api/workflows") return hasFields(body, ["items", "count", "observed_at", "availability"])
    && Array.isArray(body.items) && body.items.every(isWorkflow) && typeof body.count === "number"
    && isString(body.observed_at) && isAvailability(body.availability);
  if (pathname.startsWith("/api/workflows/")) return hasFields(body, ["summary", "stages", "artifact", "deployment", "validation", "failure", "history_status"])
    && isWorkflow(body.summary) && Array.isArray(body.stages) && body.stages.every(isStage)
    && (body.artifact === null || isArtifact(body.artifact)) && (body.deployment === null || isDeployment(body.deployment))
    && (body.validation === null || isValidation(body.validation))
    && (body.failure === null || (hasFields(body.failure, ["category", "message"]) && isString(body.failure.category) && isString(body.failure.message)))
    && isAvailability(body.history_status);
  if (pathname === "/api/deployments") return hasFields(body, ["items", "count", "observed_at", "availability"])
    && Array.isArray(body.items) && body.items.every(isDeployment) && typeof body.count === "number"
    && isString(body.observed_at) && isAvailability(body.availability);
  if (pathname.startsWith("/api/deployments/")) return hasFields(body, ["summary", "stages", "artifact", "deployment", "validation", "failure", "history_status"])
    && isRecord(body.summary) && isWorkflow(body.summary) && body.summary.kind === "deployment"
    && Array.isArray(body.stages) && body.stages.every(isStage)
    && (body.artifact === null || isArtifact(body.artifact)) && (body.deployment === null || isDeployment(body.deployment))
    && (body.validation === null || isValidation(body.validation))
    && (body.failure === null || (hasFields(body.failure, ["category", "message"]) && isString(body.failure.category) && isString(body.failure.message)))
    && isAvailability(body.history_status);
  return isRecord(body);
}

export async function getJson<T>(path: string, signal?: AbortSignal, timeoutMs = 12_000): Promise<T> {
  if (!path.startsWith("/api/")) throw new Error("API requests must use a same-origin /api path");
  const timeout = AbortSignal.timeout(timeoutMs);
  const combined = signal ? AbortSignal.any([signal, timeout]) : timeout;
  let response: Response;
  try {
    response = await fetch(path, { method: "GET", headers: { Accept: "application/json" }, cache: "no-store", signal: combined });
  } catch (error) {
    if (combined.aborted) throw new ApiError(0, "upstream_timeout", "The observation request timed out.");
    throw new ApiError(0, "temporarily_unavailable", "The control-plane API is unavailable.");
  }
  let body: unknown;
  try { body = await response.json(); } catch { throw new ApiError(response.status, "internal_error", "The API returned an invalid response."); }
  if (!response.ok) {
    const safe = isRecord(body) ? body as Partial<ApiErrorBody> : {};
    throw new ApiError(response.status, typeof safe.code === "string" ? safe.code : "internal_error", typeof safe.message === "string" ? safe.message : "The request could not be completed.");
  }
  if (!matchesContract(path, body)) throw new ApiError(response.status, "internal_error", "The API returned an invalid response.");
  return body as T;
}
