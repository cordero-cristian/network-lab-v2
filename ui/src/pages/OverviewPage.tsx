import { Link } from "react-router-dom";
import type { OverviewResponse, TopologyGraph } from "../api/types";
import { usePolling } from "../api/usePolling";
import { formatDuration, formatTime, titleCase } from "../format";
import { AvailabilityBanner, EmptyState, Panel, RouteError, SkeletonRows, StaleBanner, UnavailableState } from "../components/AsyncSection";
import { Status } from "../components/Status";
import { Topology } from "../components/Topology";

export function OverviewPage() {
  const state = usePolling<OverviewResponse>("/api/overview", 15_000);
  if (state.loading) return <Page><div className="metrics"><SkeletonRows count={4} /></div><div className="overview-grid"><Panel title="Network topology"><SkeletonRows /></Panel><Panel title="Recent activity"><SkeletonRows /></Panel></div></Page>;
  if (!state.data && state.error) return <Page><RouteError error={state.error} /></Page>;
  if (!state.data) return null;
  const data = state.data;
  const topology: TopologyGraph = { ...data.topology, observed_at: data.observed_at };
  const recent = data.activity.items;
  return (
    <Page observedAt={data.observed_at}>
      {state.stale && <StaleBanner observedAt={data.observed_at} reason={state.staleReason} />}
      <div className="metrics" aria-label="Current counts">
        <Metric label="Devices" value={data.devices.total} note="Nautobot" status={data.devices.availability.status} />
        <Metric label="Active workflows" value={data.workflows.active_count} note="Temporal" status={data.workflows.availability.status} />
        <Metric label="Deployments passed" value={data.deployments.recent_successes.length} note="retained window" status={data.deployments.availability.status} />
        <Metric label="Deployments failed" value={data.deployments.recent_failures.length} note="retained window" status={data.deployments.availability.status} danger={data.deployments.recent_failures.length > 0} />
      </div>
      <div className="overview-grid">
        <Panel title="Network topology" meta={`${topology.nodes.length} nodes · ${topology.links.length} links`}><Topology graph={topology} /></Panel>
        <Panel title="Recent activity" meta="Temporal · newest first">
          <AvailabilityBanner availability={data.activity.availability} />
          {recent.length ? <ul className="activity-list">{recent.map((item) => <li key={`${item.workflow_id}:${item.run_id}`}><Status value={item.outcome === "unknown" ? item.execution_status : item.outcome} compact /><div><Link to={`/workflows/${encodeURIComponent(item.workflow_id)}?run_id=${encodeURIComponent(item.run_id)}`} title={item.workflow_id}>{titleCase(item.kind)} · {item.device_name ?? "Device not retained"}</Link><p className="mono">{item.current_stage ? titleCase(item.current_stage) : "Stage unavailable"} · {formatDuration(item.duration_ms)}</p></div><time dateTime={item.started_at}>{formatTime(item.started_at)}</time></li>)}</ul> : data.activity.availability.status === "unavailable" || data.activity.availability.status === "unknown" ? <UnavailableState source="Temporal visibility" message={data.activity.availability.message} /> : <EmptyState source="Temporal visibility">No admitted workflows were returned in the retained recent window.</EmptyState>}
        </Panel>
      </div>
      <section className="health-strip" aria-label="Dependency health">
        {(["nautobot", "kafka", "temporal", "worker", "consumer", "device_validation"] as const).map((key) => { const source = data.health[key]; return <div className="health-cell" key={key}><div><Status value={source.status} label={key === "device_validation" ? "Live reads" : titleCase(key)} compact /></div><p>{source.duration_ms != null ? `${source.duration_ms} ms` : source.message ?? source.code ?? "No timing"}</p></div>; })}
      </section>
    </Page>
  );
}

function Page({ children, observedAt }: { children: React.ReactNode; observedAt?: string }) {
  return <><header className="page-heading"><div><span className="eyebrow">Control plane</span><h1>Overview</h1><p>Current automation state, durable outcomes, and small-lab topology.</p></div><div className="source-note">Sources: Nautobot · Temporal · native probes{observedAt && <><br />Observed {formatTime(observedAt)}</>}</div></header>{children}</>;
}

function Metric({ label, value, note, status, danger = false }: { label: string; value: number | null; note: string; status: string; danger?: boolean }) {
  const available = status !== "unavailable" && status !== "unknown";
  return <div className="metric"><span>{label}</span><div><strong className={danger ? "danger" : ""}>{available && value != null ? value : "—"}</strong><small>{available ? note : "Unavailable"}</small></div></div>;
}
