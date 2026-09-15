import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getJson } from "../api/client";
import type { DeviceDetail, Envelope, LiveStateSummary, SourceAvailability, ValidationCheck } from "../api/types";
import { formatDuration, formatTime, shortId, titleCase, valueText } from "../format";
import { AvailabilityBanner, EmptyState, Panel, RouteError, SkeletonRows, StaleBanner, UnavailableState } from "../components/AsyncSection";
import { Status } from "../components/Status";

interface DetailState { data: DeviceDetail | null; error: Error | null; loading: boolean; stale: boolean; staleReason: "age" | "refresh" | null }

function useDeviceDetail(deviceName: string): DetailState {
  const [state, setState] = useState<DetailState>({ data: null, error: null, loading: true, stale: false, staleReason: null });
  const liveRequestedFor = useRef<string | null>(null);
  useEffect(() => {
    let disposed = false;
    let running = false;
    let timer: number | undefined;
    let staleTimer: number | undefined;
    let controller: AbortController | undefined;
    setState({ data: null, error: null, loading: true, stale: false, staleReason: null });
    const path = `/api/devices/${encodeURIComponent(deviceName)}`;
    const scheduleStale = (observedAt: string) => {
      if (staleTimer) window.clearTimeout(staleTimer);
      staleTimer = window.setTimeout(() => setState((previous) => ({ ...previous, stale: previous.data !== null, staleReason: previous.data !== null ? "age" : null })), Math.max(0, Date.parse(observedAt) + 60_000 - Date.now()));
    };
    const schedule = () => {
      if (timer) window.clearTimeout(timer);
      if (!disposed) timer = window.setTimeout(() => void refresh(), 30_000);
    };
    const refresh = async (liveFailure?: Error, force = false) => {
      timer = undefined;
      if (disposed || running || (!force && document.visibilityState === "hidden")) return;
      running = true;
      controller = new AbortController();
      try {
        const updated = await getJson<DeviceDetail>(`${path}?live=false`, controller.signal);
        if (!disposed) {
          const liveState = liveFailure ? failedLiveState(updated, liveFailure) : null;
          setState((previous) => ({ data: { ...updated, live_state: liveState ?? previous.data?.live_state ?? updated.live_state }, error: null, loading: false, stale: false, staleReason: null }));
          scheduleStale(updated.summary.observed_at);
        }
      } catch (error) {
        if (!disposed) setState((previous) => ({ ...previous, error: error as Error, loading: false, stale: previous.data !== null, staleReason: previous.data !== null ? "refresh" : null }));
      } finally {
        running = false;
        schedule();
      }
    };
    queueMicrotask(async () => {
      if (disposed || liveRequestedFor.current === deviceName) return;
      liveRequestedFor.current = deviceName;
      running = true;
      controller = new AbortController();
      try {
        const data = await getJson<DeviceDetail>(`${path}?live=true`, controller.signal, 17_000);
        if (!disposed) {
          setState({ data, error: null, loading: false, stale: false, staleReason: null });
          scheduleStale(data.summary.observed_at);
        }
      } catch (error) {
        running = false;
        if (!disposed) await refresh(error as Error, true);
        return;
      }
      running = false;
      schedule();
    });
    const onVisibility = () => {
      if (document.visibilityState === "visible" && !running) {
        if (timer) window.clearTimeout(timer);
        void refresh();
      }
    };
    document.addEventListener("visibilitychange", onVisibility);
    return () => { disposed = true; if (timer) window.clearTimeout(timer); if (staleTimer) window.clearTimeout(staleTimer); controller?.abort(); document.removeEventListener("visibilitychange", onVisibility); };
  }, [deviceName]);
  return state;
}

function failedLiveState(detail: DeviceDetail, error: Error): DeviceDetail["live_state"] {
  return {
    availability: {
      source: "device",
      status: "unavailable",
      observed_at: detail.summary.observed_at,
      duration_ms: null,
      code: "unreachable",
      message: error.message || "Live state request failed; base observations were retained.",
    },
    data: null,
  };
}

export function DeviceDetailPage() {
  const { deviceName = "" } = useParams();
  const state = useDeviceDetail(deviceName);
  if (state.loading) return <><Breadcrumb /><SkeletonRows count={7} /></>;
  if (!state.data && state.error) return <><Breadcrumb /><RouteError title="Device observation unavailable" error={state.error} back={<Link className="text-link" to="/devices">Back to devices</Link>} /></>;
  if (!state.data) return null;
  const detail = state.data;
  const deployment = detail.latest_deployment.data;
  return <><Breadcrumb /><header className="page-heading page-heading--detail"><div><span className="eyebrow">{detail.summary.role ?? "Role unknown"} · {detail.summary.platform ?? "Platform unknown"}</span><h1 className="mono" title={detail.summary.name}>{detail.summary.name}</h1><p>{detail.summary.location ?? "Location unavailable"} · {detail.summary.management_address ?? "No management address"}</p></div><Status value={detail.summary.validation_status} label={titleCase(detail.summary.validation_status)} /></header>
    {state.stale && <StaleBanner observedAt={detail.summary.observed_at} reason={state.staleReason} />}
    <div className="device-grid">
      <Panel title="Intended state" meta={`Nautobot · ${formatTime(detail.intent.availability.observed_at)}`}><AvailabilityBanner availability={detail.intent.availability} />{detail.intent.data ? <IntentRows intent={detail.intent.data} /> : <MissingSection availability={detail.intent.availability} source="Nautobot" />}</Panel>
      <Panel title="Live state" meta={`One on-demand read · ${formatTime(detail.live_state.data?.validated_at ?? detail.live_state.availability.observed_at)}`}><AvailabilityBanner availability={detail.live_state.availability} />{detail.live_state.data ? <LiveRows live={detail.live_state} /> : <MissingSection availability={detail.live_state.availability} source="Device validation">Intent and retained history remain available. No automatic device retry will occur.</MissingSection>}</Panel>
    </div>
    <section className="deployment-band" aria-label="Latest deployment evidence">
      <EvidenceCell label="Latest deployment" availability={detail.latest_deployment.availability}>{deployment ? <Link className="text-link mono" to={`/workflows/${encodeURIComponent(deployment.workflow_id)}?run_id=${encodeURIComponent(deployment.run_id)}`} title={deployment.workflow_id}>{shortId(deployment.workflow_id, 28)}</Link> : "No retained deployment"}</EvidenceCell>
      <EvidenceCell label="Artifact" availability={detail.latest_artifact.availability}>{detail.latest_artifact.data ? <><span className="mono" title={detail.latest_artifact.data.relative_path}>{detail.latest_artifact.data.relative_path}</span><small>{detail.latest_artifact.data.sha256 ? `sha256 ${shortId(detail.latest_artifact.data.sha256, 16)}` : "Digest unavailable"} · {detail.latest_artifact.data.byte_count ?? "?"} bytes</small><Status value={detail.latest_artifact.data.available ? "healthy" : "unavailable"} label={detail.latest_artifact.data.available ? "Artifact available" : "Artifact missing"} compact /></> : "Metadata unavailable"}</EvidenceCell>
      <EvidenceCell label="Completed" availability={detail.latest_deployment.availability}>{deployment ? <>{formatTime(deployment.completed_at ?? deployment.deployed_at)}<small>{formatDuration(deployment.duration_ms)}</small></> : "Not available"}</EvidenceCell>
      <EvidenceCell label="Validation" availability={detail.historical_validation.availability}><Status value={detail.historical_validation.data?.status ?? detail.historical_validation.availability.status} compact /></EvidenceCell>
    </section>
  </>;
}

function Breadcrumb() { return <nav className="breadcrumb" aria-label="Breadcrumb"><Link to="/devices">Devices</Link><span aria-hidden="true">/</span><span>Device detail</span></nav>; }
function SectionEmpty({ source, children = "No data was returned for this section." }: { source: string; children?: React.ReactNode }) { return <EmptyState source={source}>{children}</EmptyState>; }
function MissingSection({ availability, source, children }: { availability: SourceAvailability; source: string; children?: React.ReactNode }) { return availability.status === "unavailable" || availability.status === "unknown" ? <UnavailableState source={source} message={availability.message ?? (typeof children === "string" ? children : undefined)} /> : <SectionEmpty source={source}>{children}</SectionEmpty>; }
function EvidenceCell({ label, availability, children }: { label: string; availability: SourceAvailability; children: React.ReactNode }) { return <div className="evidence-cell"><span className="eyebrow">{label}</span><div>{children}</div><div className="evidence-source"><Status value={availability.status} compact /><small>{titleCase(availability.source)} · observed {formatTime(availability.observed_at)}</small>{availability.message && <small>{availability.message}</small>}</div></div>; }

function IntentRows({ intent }: { intent: NonNullable<DeviceDetail["intent"]["data"]> }) {
  return <div className="state-list"><StateRow label="Hostname" value={intent.hostname} tag="intended" /><StateRow label="Loopback" value={intent.loopback} tag="intended" />{intent.routed_interfaces.map((item) => <StateRow key={item.name} label={item.name} value={item.ipv4 ?? item.address ?? item.description} tag="routed" />)}<StateRow label="Local ASN" value={intent.bgp_local_asn} tag="BGP" />{intent.bgp_neighbors.map((neighbor) => <StateRow key={neighbor.address} label="Neighbor" value={`${neighbor.address} · AS ${neighbor.remote_asn}`} tag="BGP" />)}</div>;
}

function checkValue(check: ValidationCheck): string { return valueText(check.observed); }
function LiveRows({ live }: { live: Envelope<LiveStateSummary> }) {
  const data = live.data!; const checks = [data.hostname, ...data.interfaces, ...data.bgp].filter((item): item is ValidationCheck => item != null);
  return <><div className="live-summary"><Status value={data.status} compact /><span>{data.mismatch_count} existing {data.mismatch_count === 1 ? "mismatch" : "mismatches"}</span></div><div className="validation-list">{checks.map((check, index) => <div className={`validation-row${check.status === "failed" ? " validation-row--failed" : ""}`} key={`${check.name}:${index}`}><div className="validation-row__head"><strong className="mono">{check.name}</strong><span>{check.status === "failed" ? "Mismatch" : "Match"}</span></div><dl><div><dt>Expected</dt><dd className="mono">{valueText(check.expected)}</dd></div><div><dt>Observed</dt><dd className="mono">{checkValue(check)}</dd></div></dl>{check.message && <p>{check.message}</p>}</div>)}</div></>;
}
function StateRow({ label, value, tag, failed = false }: { label: string; value: unknown; tag: string; failed?: boolean }) { return <div className={`state-row${failed ? " state-row--failed" : ""}`}><span>{label}</span><strong className="mono">{valueText(value)}</strong><small>{tag}</small></div>; }
