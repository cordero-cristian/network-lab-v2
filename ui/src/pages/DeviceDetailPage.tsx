import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getJson } from "../api/client";
import type { ComparisonSources, ConfigurationCheck, ConfigurationDriftObservation, DeviceDetail, OperationalHealthCheck, OperationalHealthObservation, SourceAvailability } from "../api/types";
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
          const failed = liveFailure ? failedComparison(updated, liveFailure) : null;
          setState((previous) => ({
            data: {
              ...updated,
              configuration_drift: failed?.configuration_drift ?? previous.data?.configuration_drift ?? updated.configuration_drift,
              operational_health: failed?.operational_health ?? previous.data?.operational_health ?? updated.operational_health,
            },
            error: null,
            loading: false,
            stale: false,
            staleReason: null,
          }));
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

function failedComparison(detail: DeviceDetail, error: Error): Pick<DeviceDetail, "configuration_drift" | "operational_health"> {
  const observedAt = detail.summary.observed_at;
  const device: SourceAvailability = {
      source: "device",
      status: "unavailable",
      observed_at: observedAt,
      duration_ms: null,
      code: "unreachable",
      message: error.message || "Current comparison request failed; base observations were retained.",
  };
  const unavailable = <T extends ConfigurationDriftObservation | OperationalHealthObservation>(observation: T): T => ({
    ...observation,
    status: "unavailable",
    sources: { intent: observation.sources.intent, device },
    result: null,
    observed_at: observedAt,
  }) as T;
  return {
    configuration_drift: unavailable(detail.configuration_drift),
    operational_health: unavailable(detail.operational_health),
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
      <ComparisonPanel title="Configuration Drift" observation={detail.configuration_drift} kind="configuration" />
      <ComparisonPanel title="Operational Health" observation={detail.operational_health} kind="operational" />
    </div>
    <section className="deployment-band" aria-label="Latest deployment evidence">
      <EvidenceCell label="Latest deployment" availability={detail.latest_deployment.availability}>{deployment ? <Link className="text-link mono" to={`/workflows/${encodeURIComponent(deployment.workflow_id)}?run_id=${encodeURIComponent(deployment.run_id)}`} title={deployment.workflow_id}>{shortId(deployment.workflow_id, 28)}</Link> : "No retained deployment"}</EvidenceCell>
      <EvidenceCell label="Artifact" availability={detail.latest_artifact.availability}>{detail.latest_artifact.data ? <><span className="mono" title={detail.latest_artifact.data.relative_path}>{detail.latest_artifact.data.relative_path}</span><small>{detail.latest_artifact.data.sha256 ? `sha256 ${shortId(detail.latest_artifact.data.sha256, 16)}` : "Digest unavailable"} · {detail.latest_artifact.data.byte_count ?? "?"} bytes</small><Status value={detail.latest_artifact.data.available ? "healthy" : "unavailable"} label={detail.latest_artifact.data.available ? "Artifact available" : "Artifact missing"} compact /></> : "Metadata unavailable"}</EvidenceCell>
      <EvidenceCell label="Completed" availability={detail.latest_deployment.availability}>{deployment ? <>{formatTime(deployment.completed_at ?? deployment.deployed_at)}<small>{formatDuration(deployment.duration_ms)}</small></> : "Not available"}</EvidenceCell>
      <EvidenceCell label="Historical Validation" availability={detail.historical_validation.availability}><Status value={detail.historical_validation.data?.status ?? detail.historical_validation.availability.status} compact /></EvidenceCell>
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

type CurrentObservation = ConfigurationDriftObservation | OperationalHealthObservation;
type CurrentCheck = ConfigurationCheck | OperationalHealthCheck;

function ComparisonPanel({ title, observation, kind }: { title: string; observation: CurrentObservation; kind: "configuration" | "operational" }) {
  const result = observation.result;
  const unavailableMessage = observation.sources.device.message ?? observation.sources.intent.message ?? "No current comparison was requested. Intent and retained history remain available; no automatic device retry will occur.";
  return <Panel title={title} meta={`One observation · ${formatTime(observation.observed_at)}`}>
    <div className="comparison-summary"><Status value={observation.status} label={titleCase(observation.status)} compact /><span>{result ? resultCounts(result) : "No conclusion"}</span></div>
    <SourceEvidence sources={observation.sources} />
    {result ? <CheckRows checks={result.checks} /> : <UnavailableState source={kind === "configuration" ? "Configuration comparison" : "Operational observation"} message={unavailableMessage} />}
  </Panel>;
}

function resultCounts(result: NonNullable<CurrentObservation["result"]>): string {
  if ("matches" in result) return `${result.matches} ${result.matches === 1 ? "match" : "matches"} · ${result.mismatches} ${result.mismatches === 1 ? "mismatch" : "mismatches"}`;
  return `${result.healthy_count} healthy · ${result.unhealthy_count} unhealthy · ${result.unavailable_count} unavailable`;
}

function SourceEvidence({ sources }: { sources: ComparisonSources }) {
  return <dl className="comparison-sources">
    <SourceRow label="Nautobot intent" availability={sources.intent} />
    <SourceRow label="Device read" availability={sources.device} />
  </dl>;
}

function SourceRow({ label, availability }: { label: string; availability: SourceAvailability }) {
  return <div><dt>{label}</dt><dd><Status value={availability.status} compact /><small>{formatTime(availability.observed_at)}</small>{availability.message && <small>{availability.message}</small>}</dd></div>;
}

function CheckRows({ checks }: { checks: CurrentCheck[] }) {
  return <div className="validation-list">{checks.map((check) => {
    const failed = check.status === "mismatch" || check.status === "unhealthy" || check.status === "unavailable";
    return <div className={`validation-row${failed ? " validation-row--failed" : ""}`} key={check.key}>
      <div className="validation-row__head"><strong className="mono">{check.key}</strong><Status value={check.status} compact /></div>
      <dl><div><dt>Expected</dt><dd className="mono">{valueText(check.expected)}</dd></div><div><dt>Observed</dt><dd className="mono">{valueText(check.observed)}</dd></div></dl>
      {check.message && <p>{check.message}</p>}
    </div>;
  })}</div>;
}
function StateRow({ label, value, tag, failed = false }: { label: string; value: unknown; tag: string; failed?: boolean }) { return <div className={`state-row${failed ? " state-row--failed" : ""}`}><span>{label}</span><strong className="mono">{valueText(value)}</strong><small>{tag}</small></div>; }
