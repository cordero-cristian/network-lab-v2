import { Link } from "react-router-dom";
import type { DeviceListResponse, DeviceSummary } from "../api/types";
import { usePolling } from "../api/usePolling";
import { formatTime, titleCase } from "../format";
import { AvailabilityBanner, EmptyState, RouteError, SkeletonRows, StaleBanner, UnavailableState } from "../components/AsyncSection";
import { Status } from "../components/Status";

export function DevicesPage() {
  const state = usePolling<DeviceListResponse>("/api/devices?limit=100", 30_000);
  return <><header className="page-heading"><div><span className="eyebrow">Nautobot inventory</span><h1>Devices</h1><p>Intent-owned identity joined to the latest retained automation evidence.</p></div>{state.data && <div className="source-note">{state.data.count} devices<br />Observed {formatTime(state.data.observed_at)}</div>}</header>
    {state.loading && <div className="table-frame"><SkeletonRows count={6} /></div>}
    {!state.data && state.error && <RouteError error={state.error} />}
    {state.data && <>{state.stale && <StaleBanner observedAt={state.data.observed_at} reason={state.staleReason} />}<AvailabilityBanner availability={state.data.availability} />{state.data.items.length ? <DeviceTable devices={state.data.items} /> : state.data.availability.status === "unavailable" || state.data.availability.status === "unknown" ? <UnavailableState source="Nautobot" message={state.data.availability.message} /> : <EmptyState source="Nautobot">No devices were returned from authoritative inventory.</EmptyState>}</>}
  </>;
}

function DeviceTable({ devices }: { devices: DeviceSummary[] }) {
  return <div className="table-frame responsive-table"><table><thead><tr><th>Device</th><th>Role / platform</th><th>Management</th><th>Inventory</th><th>Latest deployment</th><th>Validation</th></tr></thead><tbody>{devices.map((device) => <tr key={device.name}><td data-label="Device"><Link className="primary-link mono" to={`/devices/${encodeURIComponent(device.name)}`} title={device.name}>{device.name}</Link><small>{device.location ?? "Location unavailable"}</small></td><td data-label="Role / platform"><span>{device.role ?? "Unknown role"}</span><small>{device.platform ?? "Platform unavailable"}</small></td><td data-label="Management" className="mono">{device.management_address ?? "Not assigned"}</td><td data-label="Inventory"><span>{device.inventory_status ?? "Unknown"}</span></td><td data-label="Latest deployment">{device.last_deployment ? <><Status value={device.last_deployment.status} compact /><small>{formatTime(device.last_deployment.completed_at ?? device.last_deployment.deployed_at, true)}</small></> : <span className="muted">No retained deployment</span>}</td><td data-label="Validation"><Status value={device.validation_status} label={titleCase(device.validation_status)} compact /></td></tr>)}</tbody></table></div>;
}
