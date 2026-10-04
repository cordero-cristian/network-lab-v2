import { act, render, screen } from "@testing-library/react";
import { StrictMode } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { deviceDetail } from "../test/fixtures";
import { DeviceDetailPage } from "./DeviceDetailPage";

describe("DeviceDetailPage live-read guardrail", () => {
  afterEach(() => vi.useRealTimers());

  it("shows an accessible loading state while the initial live observation is pending", () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(() => new Promise<Response>(() => {}));
    render(<MemoryRouter initialEntries={["/devices/f004-leaf01"]}><Routes><Route path="/devices/:deviceName" element={<DeviceDetailPage />} /></Routes></MemoryRouter>);
    expect(screen.getByLabelText("Loading")).toBeInTheDocument();
  });

  it("requests live=true exactly once, then refreshes with live=false while retaining live evidence", async () => {
    vi.useFakeTimers();
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify(deviceDetail), { status: 200 }));
    render(<StrictMode><MemoryRouter initialEntries={["/devices/f004-leaf01"]}><Routes><Route path="/devices/:deviceName" element={<DeviceDetailPage />} /></Routes></MemoryRouter></StrictMode>);
    await act(async () => { vi.runAllTicks(); await Promise.resolve(); await Promise.resolve(); });
    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual(["/api/devices/f004-leaf01?live=true"]);
    expect(screen.getByRole("heading", { name: "Configuration Drift" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Operational Health" })).toBeInTheDocument();
    expect(screen.getByText("1 match · 1 mismatch")).toBeInTheDocument();
    await act(() => vi.advanceTimersByTimeAsync(30_000));
    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual(["/api/devices/f004-leaf01?live=true", "/api/devices/f004-leaf01?live=false"]);
    expect(screen.getByText("1 match · 1 mismatch")).toBeInTheDocument();
    expect(screen.getByText("1 healthy · 1 unhealthy · 0 unavailable")).toBeInTheDocument();
  });

  it("falls back immediately to live=false after a request-level live failure without retrying live", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch")
      .mockRejectedValueOnce(new Error("offline"))
      .mockResolvedValue(new Response(JSON.stringify(deviceDetail), { status: 200 }));
    render(<StrictMode><MemoryRouter initialEntries={["/devices/f004-leaf01"]}><Routes><Route path="/devices/:deviceName" element={<DeviceDetailPage />} /></Routes></MemoryRouter></StrictMode>);
    expect(await screen.findByRole("heading", { name: "f004-leaf01" })).toBeInTheDocument();
    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual(["/api/devices/f004-leaf01?live=true", "/api/devices/f004-leaf01?live=false"]);
    expect(screen.getAllByText("The control-plane API is unavailable.").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText("10.0.0.12/32")).toBeInTheDocument();
  });

  it("shows null observed live values as unavailable and exposes artifact existence and source freshness", async () => {
    const detail = {
      ...deviceDetail,
      latest_artifact: { ...deviceDetail.latest_artifact, data: { ...deviceDetail.latest_artifact.data!, available: false } },
      configuration_drift: {
        ...deviceDetail.configuration_drift,
        result: { ...deviceDetail.configuration_drift.result!, checks: [{ ...deviceDetail.configuration_drift.result!.checks[1], observed: null, message: "Missing" }], matches: 0 },
      },
    };
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify(detail), { status: 200 }));
    render(<MemoryRouter initialEntries={["/devices/f004-leaf01"]}><Routes><Route path="/devices/:deviceName" element={<DeviceDetailPage />} /></Routes></MemoryRouter>);
    expect(await screen.findByText("Artifact missing")).toBeInTheDocument();
    expect(screen.getByText("Not available")).toBeInTheDocument();
    expect(screen.getByText("enable")).toBeInTheDocument();
    expect(screen.getAllByText(/observed 14:32:18 UTC/).length).toBeGreaterThanOrEqual(3);
  });

  it("distinguishes unavailable sections from authoritative empty sections", async () => {
    const detail = {
      ...deviceDetail,
      intent: { availability: { ...deviceDetail.intent.availability, status: "unavailable", message: "Nautobot intent unavailable" }, data: null },
      configuration_drift: { ...deviceDetail.configuration_drift, status: "unavailable", sources: { ...deviceDetail.configuration_drift.sources, intent: { ...deviceDetail.configuration_drift.sources.intent, status: "unavailable", message: "Nautobot intent unavailable" }, device: { ...deviceDetail.configuration_drift.sources.device, status: "unknown", code: "not_configured" } }, result: null },
      operational_health: { ...deviceDetail.operational_health, status: "unavailable", sources: { ...deviceDetail.operational_health.sources, intent: { ...deviceDetail.operational_health.sources.intent, status: "unavailable", message: "Nautobot intent unavailable" }, device: { ...deviceDetail.operational_health.sources.device, status: "unknown", code: "not_configured" } }, result: null },
    };
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify(detail), { status: 200 }));
    render(<MemoryRouter initialEntries={["/devices/f004-leaf01"]}><Routes><Route path="/devices/:deviceName" element={<DeviceDetailPage />} /></Routes></MemoryRouter>);
    expect((await screen.findAllByText("Observations unavailable")).length).toBeGreaterThanOrEqual(2);
    expect(screen.queryByText("No records returned")).not.toBeInTheDocument();
  });

  it("shows separate current checks, source provenance, non-color statuses, and historical validation", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify(deviceDetail), { status: 200 }));
    render(<MemoryRouter initialEntries={["/devices/f004-leaf01"]}><Routes><Route path="/devices/:deviceName" element={<DeviceDetailPage />} /></Routes></MemoryRouter>);
    expect(await screen.findByText("interface.ethernet-1/1.admin_state")).toBeInTheDocument();
    expect(screen.getAllByText("Expected").length).toBeGreaterThan(0);
    expect(screen.getByText("enable")).toBeInTheDocument();
    expect(screen.getAllByText("Observed").length).toBeGreaterThan(0);
    expect(screen.getByText("disable")).toBeInTheDocument();
    expect(screen.getByText("Interface administrative state does not match intent.")).toBeInTheDocument();
    expect(screen.getByText("routing.bgp.neighbor.10.46.0.0.session_state")).toBeInTheDocument();
    expect(screen.getByLabelText("Status: Drifted")).toBeInTheDocument();
    expect(screen.getByLabelText("Status: Degraded")).toBeInTheDocument();
    expect(screen.getAllByText("Nautobot intent")).toHaveLength(2);
    expect(screen.getAllByText("Device read")).toHaveLength(2);
    expect(screen.getByText("Historical Validation")).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("keeps matching configuration in sync when operational health is degraded", async () => {
    const configuration = deviceDetail.configuration_drift.result!;
    const detail = {
      ...deviceDetail,
      configuration_drift: {
        ...deviceDetail.configuration_drift,
        status: "in_sync" as const,
        result: { ...configuration, status: "in_sync" as const, checks: [configuration.checks[0]], matches: 1, mismatches: 0 },
      },
    };
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify(detail), { status: 200 }));
    render(<MemoryRouter initialEntries={["/devices/f004-leaf01"]}><Routes><Route path="/devices/:deviceName" element={<DeviceDetailPage />} /></Routes></MemoryRouter>);
    expect(await screen.findByLabelText("Status: In Sync")).toBeInTheDocument();
    expect(screen.getByLabelText("Status: Degraded")).toBeInTheDocument();
    expect(screen.getByText("BGP session is not established.")).toBeInTheDocument();
  });

  it("does not overlap base refreshes when visibility changes during a request", async () => {
    vi.useFakeTimers();
    let resolveRefresh!: (response: Response) => void;
    const fetchMock = vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(new Response(JSON.stringify(deviceDetail), { status: 200 }))
      .mockImplementationOnce(() => new Promise<Response>((resolve) => { resolveRefresh = resolve; }))
      .mockResolvedValue(new Response(JSON.stringify(deviceDetail), { status: 200 }));
    render(<MemoryRouter initialEntries={["/devices/f004-leaf01"]}><Routes><Route path="/devices/:deviceName" element={<DeviceDetailPage />} /></Routes></MemoryRouter>);
    await act(async () => { vi.runAllTicks(); await Promise.resolve(); await Promise.resolve(); });
    await act(() => vi.advanceTimersByTimeAsync(30_000));
    expect(fetchMock).toHaveBeenCalledTimes(2);
    Object.defineProperty(document, "visibilityState", { configurable: true, value: "hidden" });
    Object.defineProperty(document, "visibilityState", { configurable: true, value: "visible" });
    await act(async () => document.dispatchEvent(new Event("visibilitychange")));
    expect(fetchMock).toHaveBeenCalledTimes(2);
    await act(async () => { resolveRefresh(new Response(JSON.stringify(deviceDetail), { status: 200 })); await Promise.resolve(); });
    await act(() => vi.advanceTimersByTimeAsync(30_000));
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });
});
