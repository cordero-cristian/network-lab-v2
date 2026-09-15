import { Link, useParams, useSearchParams } from "react-router-dom";
import type { WorkflowDetail } from "../api/types";
import { usePolling } from "../api/usePolling";
import { formatDuration, formatTime, shortId, titleCase } from "../format";
import { AvailabilityBanner, Panel, RouteError, SkeletonRows, StaleBanner, UnavailableState } from "../components/AsyncSection";
import { Status } from "../components/Status";
import { WorkflowTimeline } from "../components/WorkflowTimeline";

export function isTerminalWorkflow(detail: WorkflowDetail): boolean {
  return detail.summary.execution_status.toLowerCase() !== "running";
}

export function WorkflowDetailPage() {
  const { workflowId = "" } = useParams();
  const [search] = useSearchParams();
  const runId = search.get("run_id");
  const path = `/api/workflows/${encodeURIComponent(workflowId)}${runId ? `?run_id=${encodeURIComponent(runId)}` : ""}`;
  const state = usePolling<WorkflowDetail>(path, 4_000, isTerminalWorkflow);
  if (state.loading) return <><Breadcrumb /><SkeletonRows count={8} /></>;
  if (!state.data && state.error) return <><Breadcrumb /><RouteError title="Workflow observation unavailable" error={state.error} back={<Link className="text-link" to="/workflows">Back to workflows</Link>} /></>;
  if (!state.data) return null;
  const detail = state.data; const summary = detail.summary; const displayStatus = summary.outcome === "unknown" ? summary.execution_status : summary.outcome;
  return <><Breadcrumb /><header className="page-heading page-heading--detail"><div><span className="eyebrow">{titleCase(summary.kind)} execution · {summary.device_name ?? "Device not retained"}</span><h1>{titleCase(displayStatus)}</h1><p className="mono" title={summary.workflow_id}>{summary.workflow_id}</p></div><Status value={displayStatus} label={summary.failure_category ? titleCase(summary.failure_category) : undefined} /></header>
    {state.stale && <StaleBanner observedAt={detail.history_status.observed_at} reason={state.staleReason} />}
    <AvailabilityBanner availability={detail.history_status} />
    <div className="workflow-grid">
      <Panel title="Execution timeline" meta="Temporal history · exact boundaries">{!detail.stages.length && (detail.history_status.status === "unavailable" || detail.history_status.status === "unknown") ? <UnavailableState source="Temporal history" message={detail.history_status.message} /> : <WorkflowTimeline stages={detail.stages} />}</Panel>
      <Panel title="Run context" meta="Safe fields" className="run-context"><dl><Context label="Workflow" value={summary.workflow_id} /><Context label="Run" value={summary.run_id} /><Context label="Event" value={summary.event_id} /><Context label="Correlation" value={summary.correlation_id} /><Context label="Device" value={summary.device_name} /><Context label="Temporal state" value={`${titleCase(summary.execution_status)}${summary.outcome !== summary.execution_status ? ` · business ${titleCase(summary.outcome)}` : ""}`} /><Context label="Started" value={formatTime(summary.started_at, true)} /><Context label="Completed" value={formatTime(summary.completed_at, true)} /><Context label="Duration" value={formatDuration(summary.duration_ms)} />{detail.artifact && <Context label="Artifact" value={`${detail.artifact.relative_path} · ${detail.artifact.byte_count ?? "?"} bytes · sha256 ${shortId(detail.artifact.sha256, 16)}`} />}{detail.validation && <Context label="Validation" value={`${titleCase(detail.validation.status)} · ${detail.validation.checks_failed ?? "?"}/${detail.validation.checks_total ?? "?"} failed`} />}</dl>{detail.failure && <div className="failure-summary" role="alert"><span className="eyebrow">Safe failure summary</span><strong>{titleCase(detail.failure.category)}</strong><p>{detail.failure.message}</p></div>}</Panel>
    </div>
  </>;
}

function Breadcrumb() { return <nav className="breadcrumb" aria-label="Breadcrumb"><Link to="/workflows">Workflows</Link><span aria-hidden="true">/</span><span>Execution detail</span></nav>; }
function Context({ label, value }: { label: string; value: string | null }) { return <div><dt>{label}</dt><dd className="mono" title={value ?? undefined}>{value ?? "Not retained"}</dd></div>; }
