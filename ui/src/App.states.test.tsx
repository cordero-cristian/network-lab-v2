import { act, cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { Topology } from "./components/Topology";
import { DeviceDetailPage } from "./pages/DeviceDetailPage";
import { DevicesPage } from "./pages/DevicesPage";
import { OverviewPage } from "./pages/OverviewPage";
import { WorkflowDetailPage } from "./pages/WorkflowDetailPage";
import { WorkflowsPage } from "./pages/WorkflowsPage";
import { deviceDetail, devices, health, overview, topology, workflowDetail, workflows } from "./test/fixtures";

const json = (body: unknown) => new Response(JSON.stringify(body), { status: 200 });

function route(element: React.ReactNode, path = "/") {
  return render(<MemoryRouter initialEntries={[path]}><Routes><Route path="*" element={element} /></Routes></MemoryRouter>);
}

describe("frontend screen/state/semantic-responsive matrix", () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
    cleanup();
  });

  it("provides shell landmarks, skip navigation, keyboard navigation, and only approved routes", async () => {
    const user = userEvent.setup();
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => json(String(input).includes("/health") ? health : devices));
    render(<MemoryRouter initialEntries={["/devices"]}><App /></MemoryRouter>);
    expect(await screen.findByRole("heading", { name: "Devices" })).toBeInTheDocument();
    expect(screen.getByRole("main")).toHaveAttribute("id", "main-content");
    expect(screen.getByRole("navigation", { name: "Primary navigation" })).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: /Overview|Devices|Workflows/ })).toHaveLength(3);
    await user.tab();
    expect(screen.getByRole("link", { name: "Skip to observations" })).toHaveFocus();
    await user.tab();
    expect(screen.getByRole("link", { name: "Overview" })).toHaveFocus();
  });

  it("exposes mobile-ready labels and responsive structure without claiming browser layout", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(json(devices));
    let view = route(<DevicesPage />);
    expect(await screen.findByRole("table")).toHaveAccessibleName("");
    expect(screen.getByRole("table").parentElement).toHaveClass("responsive-table");
    expect(screen.getByText("172.31.46.12").closest("td")).toHaveAttribute("data-label", "Management");
    view.unmount();

    vi.restoreAllMocks();
    vi.spyOn(globalThis, "fetch").mockResolvedValue(json(workflows));
    view = route(<WorkflowsPage />);
    expect(await screen.findByRole("table")).toBeInTheDocument();
    expect(screen.getByRole("table").parentElement).toHaveClass("responsive-table");
    expect(screen.getByText(workflows.items[0].event_id!.slice(0, 8) + "…").closest("td")).toHaveAttribute("data-label", "Event");
    view.unmount();

    vi.restoreAllMocks();
    vi.spyOn(globalThis, "fetch").mockResolvedValue(json(deviceDetail));
    view = route(<DeviceDetailPage />, "/devices/f004-leaf01");
    expect(await screen.findByRole("heading", { name: "f004-leaf01" })).toBeInTheDocument();
    expect(document.querySelector(".device-grid")).toBeInTheDocument();
    expect(document.querySelector(".deployment-band")).toBeInTheDocument();
    view.unmount();

    vi.restoreAllMocks();
    vi.spyOn(globalThis, "fetch").mockResolvedValue(json(workflowDetail));
    route(<WorkflowDetailPage />, `/workflows/${encodeURIComponent(workflowDetail.summary.workflow_id)}`);
    expect(await screen.findByRole("list", { name: "Exact workflow history" })).toBeInTheDocument();
    expect(document.querySelector(".workflow-grid")).toBeInTheDocument();
  });

  it("covers overview healthy, empty, partial, unavailable, stale, and keyboard drill-down states", async () => {
    const user = userEvent.setup();
    vi.spyOn(globalThis, "fetch").mockResolvedValue(json(overview));
    let view = route(<OverviewPage />);
    const activity = await screen.findByRole("link", { name: /Deployment.*f004-leaf01/i });
    activity.focus();
    expect(activity).toHaveFocus();
    expect(screen.getByRole("group", { name: /Current lab topology/ })).toBeInTheDocument();
    view.unmount();

    vi.restoreAllMocks();
    const empty = { ...overview, activity: { ...overview.activity, items: [] }, topology: { ...overview.topology, nodes: [], links: [] } };
    vi.spyOn(globalThis, "fetch").mockResolvedValue(json(empty));
    view = route(<OverviewPage />);
    expect((await screen.findAllByText("No records returned")).length).toBe(2);
    view.unmount();

    vi.restoreAllMocks();
    const unavailable = { ...empty, activity: { availability: { ...overview.activity.availability, status: "unavailable", message: "Temporal unavailable" }, items: [] } };
    vi.spyOn(globalThis, "fetch").mockResolvedValue(json(unavailable));
    view = route(<OverviewPage />);
    expect(await screen.findByText("Observations unavailable")).toBeInTheDocument();
    expect(screen.getByText("Devices")).toBeInTheDocument();
    view.unmount();

    vi.restoreAllMocks();
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-09-14T14:32:18Z"));
    vi.spyOn(globalThis, "fetch").mockResolvedValue(json(overview));
    route(<OverviewPage />);
    await act(async () => { await Promise.resolve(); await Promise.resolve(); });
    await act(() => vi.advanceTimersByTimeAsync(30_000));
    expect(screen.getByLabelText("Status: Stale")).toBeInTheDocument();
    void user;
  });

  it.each([
    ["overview", <OverviewPage />],
    ["device list", <DevicesPage />],
    ["workflow list", <WorkflowsPage />],
    ["workflow detail", <WorkflowDetailPage />],
  ])("renders loading and a safe initial error for %s", async (_name, page) => {
    vi.spyOn(globalThis, "fetch").mockImplementation(() => new Promise<Response>(() => {}));
    let view = route(page);
    expect(screen.getAllByLabelText("Loading").length).toBeGreaterThan(0);
    view.unmount();
    vi.restoreAllMocks();
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new Error("unsafe socket detail"));
    view = route(page);
    expect(await screen.findByText("The control-plane API is unavailable.")).toBeInTheDocument();
    expect(screen.queryByText(/unsafe socket detail/)).not.toBeInTheDocument();
    view.unmount();
  });

  it("covers list empty/unavailable distinctions and keyboard row drill-down", async () => {
    const user = userEvent.setup();
    vi.spyOn(globalThis, "fetch").mockResolvedValue(json({ ...devices, items: [], count: 0 }));
    let view = route(<DevicesPage />);
    expect(await screen.findByText("No records returned")).toHaveTextContent("No records returned");
    view.unmount();

    vi.restoreAllMocks();
    vi.spyOn(globalThis, "fetch").mockResolvedValue(json({ ...workflows, availability: { ...workflows.availability, status: "unavailable" }, items: [], count: 0 }));
    view = route(<WorkflowsPage />);
    expect(await screen.findByText("Observations unavailable")).toBeInTheDocument();
    view.unmount();

    vi.restoreAllMocks();
    vi.spyOn(globalThis, "fetch").mockResolvedValue(json(devices));
    route(<DevicesPage />);
    const link = await screen.findByRole("link", { name: "f004-leaf01" });
    link.focus();
    expect(link).toHaveFocus();
    await user.keyboard("{Enter}");
    expect(link).toHaveAttribute("href", "/devices/f004-leaf01");
  });

  it("covers device-detail empty, partial/unavailable, source, mismatch, artifact, and workflow-link states", async () => {
    const detail = {
      ...deviceDetail,
      intent: { ...deviceDetail.intent, data: null },
      live_state: { availability: { ...deviceDetail.live_state.availability, status: "unavailable", message: "Live state unavailable" }, data: null },
    };
    vi.spyOn(globalThis, "fetch").mockResolvedValue(json(detail));
    route(<DeviceDetailPage />, "/devices/f004-leaf01");
    expect(await screen.findByText("No records returned")).toBeInTheDocument();
    expect(screen.getByText("Observations unavailable")).toBeInTheDocument();
    expect(screen.getByText("Artifact available")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /deploy-device-config/i })).toHaveAttribute("href", expect.stringContaining("/workflows/"));
  });

  it("covers workflow success, failure, running, unknown, empty, and unavailable history semantics", async () => {
    const unknownStage = { ...workflowDetail.stages[0], key: "legacy", label: "Unknown stage", status: "unknown" };
    vi.spyOn(globalThis, "fetch").mockResolvedValue(json({ ...workflowDetail, stages: [unknownStage] }));
    let view = route(<WorkflowDetailPage />, `/workflows/${encodeURIComponent(workflowDetail.summary.workflow_id)}`);
    expect(await screen.findByText("Unknown stage")).toBeInTheDocument();
    view.unmount();

    vi.restoreAllMocks();
    vi.spyOn(globalThis, "fetch").mockResolvedValue(json({ ...workflowDetail, stages: [] }));
    view = route(<WorkflowDetailPage />, `/workflows/${encodeURIComponent(workflowDetail.summary.workflow_id)}`);
    expect(await screen.findByText("No records returned")).toBeInTheDocument();
    view.unmount();

    vi.restoreAllMocks();
    vi.spyOn(globalThis, "fetch").mockResolvedValue(json({ ...workflowDetail, stages: [], history_status: { ...workflowDetail.history_status, status: "unavailable" } }));
    route(<WorkflowDetailPage />, `/workflows/${encodeURIComponent(workflowDetail.summary.workflow_id)}`);
    expect(await screen.findByText("Observations unavailable")).toBeInTheDocument();
  });

  it("covers topology node/link empty, partial, incomplete, and keyboard navigation semantics", async () => {
    const user = userEvent.setup();
    let view = render(<MemoryRouter><Topology graph={topology} /></MemoryRouter>);
    const node = screen.getByRole("link", { name: /open f004-leaf01/i });
    node.focus();
    expect(node).toHaveFocus();
    await user.tab();
    expect(screen.getByRole("link", { name: /open device detail/i })).toHaveFocus();
    view.unmount();

    view = render(<MemoryRouter><Topology graph={{ ...topology, links: [] }} /></MemoryRouter>);
    expect(screen.getByText("Relationship data incomplete")).toBeInTheDocument();
    view.unmount();

    render(<MemoryRouter><Topology graph={{ ...topology, nodes: [], links: [], availability: { ...topology.availability, status: "unavailable" } }} /></MemoryRouter>);
    expect(screen.getByText("Observations unavailable")).toBeInTheDocument();
  });
});
