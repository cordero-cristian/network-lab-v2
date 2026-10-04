import { Link, Route, Routes } from "react-router-dom";
import { AppShell } from "./components/AppShell";
import { DeviceDetailPage } from "./pages/DeviceDetailPage";
import { DevicesPage } from "./pages/DevicesPage";
import { OverviewPage } from "./pages/OverviewPage";
import { WorkflowDetailPage } from "./pages/WorkflowDetailPage";
import { WorkflowsPage } from "./pages/WorkflowsPage";

export default function App() {
  return <Routes><Route element={<AppShell />}><Route index element={<OverviewPage />} /><Route path="devices" element={<DevicesPage />} /><Route path="devices/:deviceName" element={<DeviceDetailPage />} /><Route path="workflows" element={<WorkflowsPage />} /><Route path="workflows/:workflowId" element={<WorkflowDetailPage />} /><Route path="*" element={<section className="message-panel"><span className="eyebrow">404 · route unavailable</span><h1>Observation route not found</h1><p>The requested control-plane view does not exist.</p><Link className="text-link" to="/">Back to overview</Link></section>} /></Route></Routes>;
}
