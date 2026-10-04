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
const isSafeText = (value: unknown, maxLength = 128): value is string => isString(value) && value.length <= maxLength && value.trim().length > 0;
const isScalar = (value: unknown): value is string | number | boolean => isSafeText(value) || typeof value === "boolean" || (typeof value === "number" && Number.isInteger(value));
const isCount = (value: unknown): value is number => Number.isInteger(value) && (value as number) >= 0;
const isOneOf = (value: unknown, options: readonly string[]): value is string => isString(value) && options.includes(value);

function isAvailability(value: unknown): boolean {
  return hasFields(value, ["source", "status", "observed_at", "duration_ms", "code", "message"])
    && isString(value.source) && isOneOf(value.status, ["healthy", "degraded", "unavailable", "unknown"]) && isString(value.observed_at)
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

function isComparisonCheck(value: unknown, categories: readonly string[], statuses: readonly string[]): boolean {
  if (!hasFields(value, ["key", "category", "status", "expected", "observed", "message"])
    || !isSafeText(value.key) || !isOneOf(value.category, categories) || !isOneOf(value.status, statuses) || !isScalar(value.expected)
    || (value.observed !== null && !isScalar(value.observed)) || (value.message !== null && !isSafeText(value.message, 256))) return false;
  const matches = value.observed !== null && typeof value.observed === typeof value.expected && value.observed === value.expected;
  if (statuses.includes("match")) return (value.status === "match") === matches && (value.status === "match") === (value.message === null);
  const expectedStatus = value.observed === null ? "unavailable" : matches ? "healthy" : "unhealthy";
  return value.status === expectedStatus && (value.status === "healthy") === (value.message === null);
}

const configurationCategories = ["hostname", "interface_admin", "subinterface_admin", "address_presence", "bgp_local_asn", "bgp_peer_as"] as const;
const operationalCategories = ["interface_oper", "subinterface_oper", "address_readiness", "bgp_session"] as const;

function hasUniqueCheckKeys(checks: unknown[]): boolean {
  const keys = checks.map((check) => (check as Record<string, unknown>).key);
  return new Set(keys).size === keys.length;
}

function isSources(value: unknown): boolean {
  if (!hasFields(value, ["intent", "device"]) || !isAvailability(value.intent) || !isAvailability(value.device)) return false;
  return (value.intent as Record<string, unknown>).source === "nautobot" && (value.device as Record<string, unknown>).source === "device";
}

function isConfigurationResult(value: unknown): boolean {
  if (!hasFields(value, ["device_name", "status", "checks", "matches", "mismatches", "observed_at"])
    || !isString(value.device_name) || !isOneOf(value.status, ["in_sync", "drifted"]) || !isString(value.observed_at)
    || !Array.isArray(value.checks) || !value.checks.every((check) => isComparisonCheck(check, configurationCategories, ["match", "mismatch"]))
    || !hasUniqueCheckKeys(value.checks) || !isCount(value.matches) || !isCount(value.mismatches)) return false;
  const checks = value.checks as unknown[];
  const matches = checks.filter((check) => (check as Record<string, unknown>).status === "match").length;
  const mismatches = checks.length - matches;
  return value.matches === matches && value.mismatches === mismatches && value.status === (mismatches === 0 ? "in_sync" : "drifted");
}

function isOperationalResult(value: unknown): boolean {
  if (!hasFields(value, ["device_name", "status", "checks", "healthy_count", "unhealthy_count", "unavailable_count", "observed_at"])
    || !isString(value.device_name) || !isOneOf(value.status, ["healthy", "degraded", "unavailable"]) || !isString(value.observed_at)
    || !Array.isArray(value.checks) || !value.checks.every((check) => isComparisonCheck(check, operationalCategories, ["healthy", "unhealthy", "unavailable"]))
    || !hasUniqueCheckKeys(value.checks) || !isCount(value.healthy_count) || !isCount(value.unhealthy_count) || !isCount(value.unavailable_count)) return false;
  const checks = value.checks as unknown[];
  const count = (status: string) => checks.filter((check) => (check as Record<string, unknown>).status === status).length;
  const healthy = count("healthy");
  const unhealthy = count("unhealthy");
  const unavailable = count("unavailable");
  const aggregate = healthy + unhealthy === 0 ? "unavailable" : unhealthy + unavailable > 0 ? "degraded" : "healthy";
  return value.healthy_count === healthy && value.unhealthy_count === unhealthy && value.unavailable_count === unavailable && value.status === aggregate;
}

function isConfigurationObservation(value: unknown): boolean {
  if (!hasFields(value, ["status", "sources", "result", "observed_at"]) || !isOneOf(value.status, ["in_sync", "drifted", "unavailable"])
    || !isSources(value.sources) || !isString(value.observed_at)) return false;
  if (value.status === "unavailable") {
    const sources = value.sources as Record<string, Record<string, unknown>>;
    return value.result === null && (sources.intent.status !== "healthy" || sources.device.status !== "healthy");
  }
  if (!isConfigurationResult(value.result)) return false;
  const result = value.result as Record<string, unknown>;
  const sources = value.sources as Record<string, Record<string, unknown>>;
  return result.status === value.status && result.observed_at === value.observed_at
    && sources.intent.status === "healthy" && sources.device.status === "healthy";
}

function isOperationalObservation(value: unknown): boolean {
  if (!hasFields(value, ["status", "sources", "result", "observed_at"]) || !isOneOf(value.status, ["healthy", "degraded", "unavailable"])
    || !isSources(value.sources) || !isString(value.observed_at)) return false;
  if (value.result === null) {
    const sources = value.sources as Record<string, Record<string, unknown>>;
    return value.status === "unavailable" && (sources.intent.status !== "healthy" || sources.device.status !== "healthy");
  }
  if (!isOperationalResult(value.result)) return false;
  const result = value.result as Record<string, unknown>;
  const sources = value.sources as Record<string, Record<string, unknown>>;
  return result.status === value.status && result.observed_at === value.observed_at
    && sources.intent.status === "healthy" && sources.device.status === "healthy";
}

function isDeviceDetail(value: unknown): boolean {
  if (!hasFields(value, ["summary", "intent", "latest_artifact", "latest_deployment", "historical_validation", "configuration_drift", "operational_health"])
    || "live_state" in value || !isDeviceSummary(value.summary) || !isEnvelope(value.intent, isIntent)
    || !isEnvelope(value.latest_artifact, isArtifact) || !isEnvelope(value.latest_deployment, isDeployment)
    || !isEnvelope(value.historical_validation, isValidation)
    || !isConfigurationObservation(value.configuration_drift) || !isOperationalObservation(value.operational_health)) return false;
  const summary = value.summary as Record<string, unknown>;
  const configuration = value.configuration_drift as Record<string, unknown>;
  const operational = value.operational_health as Record<string, unknown>;
  const configurationResult = configuration.result as Record<string, unknown> | null;
  const operationalResult = operational.result as Record<string, unknown> | null;
  return configuration.observed_at === operational.observed_at
    && (configurationResult === null || configurationResult.device_name === summary.name)
    && (operationalResult === null || operationalResult.device_name === summary.name);
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
  if (pathname.startsWith("/api/devices/")) return isDeviceDetail(body);
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
