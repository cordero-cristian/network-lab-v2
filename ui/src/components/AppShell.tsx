import { NavLink, Outlet } from "react-router-dom";
import type { SystemHealthSummary } from "../api/types";
import { usePolling } from "../api/usePolling";
import { formatTime } from "../format";
import { Status } from "./Status";

export function AppShell() {
  const health = usePolling<SystemHealthSummary>("/api/health", 15_000);
  const healthIsStale = health.stale || (health.error !== null && health.data !== null);
  return (
    <div className="site-frame">
      <a className="skip-link" href="#main-content">Skip to observations</a>
      <header className="topbar">
        <div className="brandline">
          <span className="brand">Network Automation Lab</span>
          <span className="environment">Local lab</span>
          <span className="observation">{healthIsStale ? "stale" : "observed"} {formatTime(health.data?.observed_at)}</span>
        </div>
        {health.data ? <Status value={healthIsStale ? "degraded" : health.data.overall_status} label={healthIsStale ? "Health stale" : undefined} /> : health.error ? <Status value="unavailable" label="Health unavailable" /> : <span className="observation">Health pending</span>}
      </header>
      <nav className="nav" aria-label="Primary navigation">
        <NavLink to="/" end>Overview</NavLink>
        <NavLink to="/devices">Devices</NavLink>
        <NavLink to="/workflows">Workflows</NavLink>
      </nav>
      <main id="main-content" className="main" tabIndex={-1}><Outlet /></main>
      <footer className="footer"><span>Read-only observation surface</span><span>Nautobot intent · Temporal execution</span></footer>
    </div>
  );
}
