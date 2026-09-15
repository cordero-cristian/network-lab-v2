export type AvailabilityStatus = "healthy" | "degraded" | "unavailable" | "unknown";
export type DisplayStatus = AvailabilityStatus | "failed" | "passed" | "running" | "completed" | "canceled" | "cancelled" | "terminated" | "timed_out" | "timeout" | "succeeded" | "queued" | "preparing" | "deploying" | "validating" | "skipped" | "not_reached";

export interface SourceAvailability {
  source: string;
  status: AvailabilityStatus;
  observed_at: string;
  duration_ms: number | null;
  code: string | null;
  message: string | null;
}

export interface SystemHealthSummary {
  overall_status: "healthy" | "degraded" | "unavailable";
  observed_at: string;
  nautobot: SourceAvailability;
  kafka: SourceAvailability;
  temporal: SourceAvailability;
  worker: SourceAvailability;
  consumer: SourceAvailability;
  device_validation: SourceAvailability;
}

export interface ArtifactSummary {
  relative_path: string;
  sha256: string | null;
  byte_count: number | null;
  available: boolean;
}

export interface ValidationSummary {
  status: "passed" | "failed" | "unavailable" | "unknown";
  validated_at: string | null;
  checks_total: number | null;
  checks_failed: number | null;
}

export interface DeploymentSummary {
  workflow_id: string;
  run_id: string;
  device_name: string | null;
  status: "queued" | "preparing" | "deploying" | "validating" | "succeeded" | "failed" | "unknown";
  artifact: ArtifactSummary | null;
  deployed_at: string | null;
  completed_at: string | null;
  duration_ms: number | null;
  validation_status: ValidationSummary["status"];
  failure_stage: "prepare" | "deploy" | "validate" | "publish" | "execution" | null;
  failure_category: string | null;
}

export interface WorkflowSummary {
  workflow_id: string;
  run_id: string;
  kind: "render" | "deployment";
  event_id: string | null;
  correlation_id: string | null;
  device_name: string | null;
  execution_status: "running" | "completed" | "failed" | "canceled" | "terminated" | "timed_out" | "continued_as_new" | "unknown";
  outcome: "running" | "render_succeeded" | "render_failed" | "deployment_succeeded" | "deployment_failed" | "execution_failed" | "execution_canceled" | "execution_terminated" | "execution_timed_out" | "continued_as_new" | "unknown";
  started_at: string;
  completed_at: string | null;
  duration_ms: number | null;
  current_stage: string | null;
  failure_category: string | null;
  data_status: "complete" | "partial" | "unavailable";
}

export interface TopologyNode {
  id: string;
  label: string;
  role: string | null;
  platform: string | null;
  status: "healthy" | "degraded" | "failed" | "unknown";
  status_source: "inventory" | "deployment" | "validation" | null;
}

export interface TopologyLink {
  id: string;
  kind: "physical" | "bgp";
  source_device: string;
  source_interface: string | null;
  target_device: string;
  target_interface: string | null;
  status: "healthy" | "degraded" | "failed" | "unknown";
}

export interface TopologyGraph {
  nodes: TopologyNode[];
  links: TopologyLink[];
  observed_at: string;
  availability: SourceAvailability;
}

export interface OverviewResponse {
  observed_at: string;
  health: SystemHealthSummary;
  devices: { availability: SourceAvailability; total: number | null };
  workflows: { availability: SourceAvailability; active_count: number | null; recent: WorkflowSummary[] };
  deployments: { availability: SourceAvailability; recent_successes: DeploymentSummary[]; recent_failures: DeploymentSummary[] };
  topology: { availability: SourceAvailability; nodes: TopologyNode[]; links: TopologyLink[] };
  activity: { availability: SourceAvailability; items: WorkflowSummary[] };
}

export interface DeviceSummary {
  name: string;
  role: string | null;
  platform: string | null;
  location: string | null;
  management_address: string | null;
  inventory_status: string | null;
  last_deployment: DeploymentSummary | null;
  validation_status: ValidationSummary["status"];
  observed_at: string;
}

export interface DeviceListResponse {
  items: DeviceSummary[];
  count: number;
  observed_at: string;
  availability: SourceAvailability;
}

export interface IntendedInterface { name: string; description?: string | null; ipv4?: string | null; address?: string | null }
export interface IntendedNeighbor { address: string; remote_asn: number; description?: string | null }
export interface IntendedStateSummary {
  hostname: string;
  loopback: string | null;
  routed_interfaces: IntendedInterface[];
  bgp_local_asn: number | null;
  bgp_neighbors: IntendedNeighbor[];
}

export interface ValidationCheck {
  name: string;
  status: "passed" | "failed";
  expected: string | number | boolean;
  observed: string | number | boolean | null;
  message: string | null;
}

export interface LiveStateSummary {
  status: "passed" | "failed" | "unavailable";
  hostname: ValidationCheck | null;
  interfaces: ValidationCheck[];
  bgp: ValidationCheck[];
  mismatch_count: number;
  validated_at: string | null;
}

export interface Envelope<T> { availability: SourceAvailability; data: T | null }
export interface DeviceDetail {
  summary: DeviceSummary;
  intent: Envelope<IntendedStateSummary>;
  latest_artifact: Envelope<ArtifactSummary>;
  latest_deployment: Envelope<DeploymentSummary>;
  historical_validation: Envelope<ValidationSummary>;
  live_state: Envelope<LiveStateSummary>;
}

export interface ExecutionStage {
  sequence: number;
  key: string;
  label: string;
  status: "completed" | "running" | "failed" | "not_reached" | "unknown";
  scheduled_at: string | null;
  started_at: string | null;
  completed_at: string | null;
  duration_ms: number | null;
  attempts: number | null;
  failure_category: string | null;
  failure_message: string | null;
}

export interface SafeFailureSummary { category: string; message: string; stage?: string | null }
export interface WorkflowDetail {
  summary: WorkflowSummary;
  stages: ExecutionStage[];
  artifact: ArtifactSummary | null;
  deployment: DeploymentSummary | null;
  validation: ValidationSummary | null;
  failure: SafeFailureSummary | null;
  history_status: SourceAvailability;
}

export interface WorkflowListResponse {
  items: WorkflowSummary[];
  count: number;
  observed_at: string;
  availability: SourceAvailability;
}

export interface ApiErrorBody { code: string; message: string; request_id?: string }
