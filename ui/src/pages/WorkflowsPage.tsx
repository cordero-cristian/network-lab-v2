import { Link } from "react-router-dom";
import type { WorkflowListResponse, WorkflowSummary } from "../api/types";
import { usePolling } from "../api/usePolling";
import { formatDuration, formatTime, shortId, titleCase } from "../format";
import { AvailabilityBanner, EmptyState, RouteError, SkeletonRows, StaleBanner, UnavailableState } from "../components/AsyncSection";
import { Status } from "../components/Status";

export function WorkflowsPage() {
  const state = usePolling<WorkflowListResponse>("/api/workflows?limit=25", 10_000);
  return <><header className="page-heading"><div><span className="eyebrow">Temporal visibility</span><h1>Workflows</h1><p>Newest durable render and deployment executions in the bounded retained window.</p></div>{state.data && <div className="source-note">Showing {state.data.count}<br />Observed {formatTime(state.data.observed_at)}</div>}</header>
    {state.loading && <div className="table-frame"><SkeletonRows count={7} /></div>}
    {!state.data && state.error && <RouteError error={state.error} />}
    {state.data && <>{state.stale && <StaleBanner observedAt={state.data.observed_at} reason={state.staleReason} />}<AvailabilityBanner availability={state.data.availability} />{state.data.items.length ? <WorkflowTable workflows={state.data.items} /> : state.data.availability.status === "unavailable" || state.data.availability.status === "unknown" ? <UnavailableState source="Temporal visibility" message={state.data.availability.message} /> : <EmptyState source="Temporal visibility">No admitted render or deployment workflows were returned.</EmptyState>}</>}
  </>;
}

function WorkflowTable({ workflows }: { workflows: WorkflowSummary[] }) {
  return <div className="table-frame responsive-table"><table><thead><tr><th>Outcome</th><th>Kind / workflow</th><th>Device</th><th>Current stage</th><th>Started</th><th>Duration</th><th>Event</th><th>Correlation</th></tr></thead><tbody>{workflows.map((workflow) => <tr key={`${workflow.workflow_id}:${workflow.run_id}`}><td data-label="Outcome"><Status value={workflow.outcome === "unknown" ? workflow.execution_status : workflow.outcome} compact /></td><td data-label="Kind / workflow"><Link className="primary-link mono" to={`/workflows/${encodeURIComponent(workflow.workflow_id)}?run_id=${encodeURIComponent(workflow.run_id)}`} title={workflow.workflow_id}>{titleCase(workflow.kind)} · {shortId(workflow.workflow_id, 24)}</Link><small>{titleCase(workflow.execution_status)} execution</small></td><td data-label="Device" className="mono">{workflow.device_name ?? "Not retained"}</td><td data-label="Current stage">{titleCase(workflow.current_stage)}{workflow.failure_category && <small className="danger">{titleCase(workflow.failure_category)}</small>}</td><td data-label="Started"><time dateTime={workflow.started_at}>{formatTime(workflow.started_at, true)}</time></td><td data-label="Duration" className="mono">{formatDuration(workflow.duration_ms)}</td><td data-label="Event" className="mono" title={workflow.event_id ?? undefined}>{shortId(workflow.event_id, 8)}</td><td data-label="Correlation" className="mono" title={workflow.correlation_id ?? undefined}>{shortId(workflow.correlation_id, 8)}</td></tr>)}</tbody></table></div>;
}
