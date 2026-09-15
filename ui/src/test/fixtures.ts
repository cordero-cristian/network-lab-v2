import type { DeviceDetail, DeviceListResponse, OverviewResponse, SourceAvailability, SystemHealthSummary, TopologyGraph, WorkflowDetail, WorkflowListResponse, WorkflowSummary } from "../api/types";

export const observedAt = "2026-09-14T14:32:18Z";
export const available: SourceAvailability = { source: "temporal", status: "healthy", observed_at: observedAt, duration_ms: 12, code: null, message: null };
export const health: SystemHealthSummary = { overall_status: "healthy", observed_at: observedAt, nautobot: { ...available, source: "nautobot" }, kafka: { ...available, source: "kafka" }, temporal: available, worker: { ...available, source: "worker" }, consumer: { ...available, source: "consumer" }, device_validation: { ...available, source: "device" } };

export const workflow: WorkflowSummary = {
  workflow_id: "deploy-device-config:67bd4f6e-2d33-4ed1-8bc1-0123456789ab",
  run_id: "93186e15-b883-4dfa-b7b5-abcdef123456",
  kind: "deployment",
  event_id: "67bd4f6e-2d33-4ed1-8bc1-0123456789ab",
  correlation_id: "44ab6201-52ef-4ae7-9d34-fedcba987654",
  device_name: "f004-leaf01",
  execution_status: "completed",
  outcome: "deployment_failed",
  started_at: "2026-09-14T14:31:02Z",
  completed_at: observedAt,
  duration_ms: 76_000,
  current_stage: "deploy",
  failure_category: "device_authentication_failed",
  data_status: "complete",
};

export const topology: TopologyGraph = {
  observed_at: observedAt,
  availability: { ...available, source: "nautobot" },
  nodes: [
    { id: "f004-spine01", label: "f004-spine01", role: "spine", platform: "SR Linux", status: "healthy", status_source: "validation" },
    { id: "f004-leaf01", label: "f004-leaf01", role: "leaf", platform: "SR Linux", status: "degraded", status_source: "deployment" },
  ],
  links: [{ id: "bgp:leaf:spine", kind: "bgp", source_device: "f004-leaf01", source_interface: "ethernet-1/1", target_device: "f004-spine01", target_interface: "ethernet-1/1", status: "unknown" }],
};

export const overview: OverviewResponse = {
  observed_at: observedAt,
  health,
  devices: { availability: { ...available, source: "nautobot" }, total: 2 },
  workflows: { availability: available, active_count: 0, recent: [workflow] },
  deployments: { availability: available, recent_successes: [], recent_failures: [{ workflow_id: workflow.workflow_id, run_id: workflow.run_id, device_name: workflow.device_name, status: "failed", artifact: null, deployed_at: null, completed_at: workflow.completed_at, duration_ms: workflow.duration_ms, validation_status: "unavailable", failure_stage: "deploy", failure_category: workflow.failure_category }] },
  topology: { availability: topology.availability, nodes: topology.nodes, links: topology.links },
  activity: { availability: available, items: [workflow] },
};

export const deviceDetail: DeviceDetail = {
  summary: { name: "f004-leaf01", role: "leaf", platform: "SR Linux", location: "Feature 004 Lab", management_address: "172.31.46.12", inventory_status: "Active", last_deployment: overview.deployments.recent_failures[0], validation_status: "failed", observed_at: observedAt },
  intent: { availability: { ...available, source: "nautobot" }, data: { hostname: "f004-leaf01", loopback: "10.0.0.12/32", routed_interfaces: [{ name: "ethernet-1/1", ipv4: "10.46.0.1/31" }], bgp_local_asn: 65102, bgp_neighbors: [{ address: "10.46.0.0", remote_asn: 65101 }] } },
  latest_artifact: { availability: { ...available, source: "artifact" }, data: { relative_path: "configs/f004-leaf01.cfg", sha256: "a".repeat(64), byte_count: 2300, available: true } },
  latest_deployment: { availability: available, data: overview.deployments.recent_failures[0] },
  historical_validation: { availability: available, data: { status: "failed", validated_at: observedAt, checks_total: 5, checks_failed: 1 } },
  live_state: { availability: { ...available, source: "device" }, data: { status: "failed", hostname: { name: "system.hostname", status: "passed", expected: "f004-leaf01", observed: "f004-leaf01", message: null }, interfaces: [{ name: "interface.ethernet-1/1.admin-state", status: "failed", expected: "enable", observed: "disable", message: "Interface state does not match" }], bgp: [], mismatch_count: 1, validated_at: "2026-09-14T14:32:17Z" } },
};

export const devices: DeviceListResponse = { items: [deviceDetail.summary], count: 1, observed_at: observedAt, availability: { ...available, source: "nautobot" } };
export const workflows: WorkflowListResponse = { items: [workflow], count: 1, observed_at: observedAt, availability: available };
export const workflowDetail: WorkflowDetail = {
  summary: workflow,
  stages: [
    { sequence: 1, key: "workflow", label: "Workflow started", status: "completed", scheduled_at: null, started_at: workflow.started_at, completed_at: null, duration_ms: null, attempts: null, failure_category: null, failure_message: null },
    { sequence: 2, key: "deploy", label: "gNMI deployment", status: "failed", scheduled_at: workflow.started_at, started_at: workflow.started_at, completed_at: workflow.completed_at, duration_ms: 810, attempts: 1, failure_category: "activity_failed", failure_message: "Activity did not complete" },
    { sequence: 3, key: "validate", label: "Operational validation", status: "not_reached", scheduled_at: null, started_at: null, completed_at: null, duration_ms: null, attempts: null, failure_category: null, failure_message: null },
  ],
  artifact: deviceDetail.latest_artifact.data,
  deployment: deviceDetail.latest_deployment.data,
  validation: deviceDetail.historical_validation.data,
  failure: { category: "device_authentication_failed", message: "Device authentication failed", stage: "deploy" },
  history_status: available,
};
