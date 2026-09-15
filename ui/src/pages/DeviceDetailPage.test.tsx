import { act, render, screen } from "@testing-library/react";
import { StrictMode } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { deviceDetail } from "../test/fixtures";
import { DeviceDetailPage } from "./DeviceDetailPage";

describe("DeviceDetailPage live-read guardrail", () => {
  afterEach(() => vi.useRealTimers());

  it("requests live=true exactly once, then refreshes with live=false while retaining live evidence", async () => {
    vi.useFakeTimers();
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify(deviceDetail), { status: 200 }));
    render(<StrictMode><MemoryRouter initialEntries={["/devices/f004-leaf01"]}><Routes><Route path="/devices/:deviceName" element={<DeviceDetailPage />} /></Routes></MemoryRouter></StrictMode>);
    await act(async () => { vi.runAllTicks(); await Promise.resolve(); await Promise.resolve(); });
    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual(["/api/devices/f004-leaf01?live=true"]);
    expect(screen.getByText("1 existing mismatch")).toBeInTheDocument();
    await act(() => vi.advanceTimersByTimeAsync(30_000));
    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual(["/api/devices/f004-leaf01?live=true", "/api/devices/f004-leaf01?live=false"]);
    expect(screen.getByText("1 existing mismatch")).toBeInTheDocument();
  });

  it("falls back immediately to live=false after a request-level live failure without retrying live", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch")
      .mockRejectedValueOnce(new Error("offline"))
      .mockResolvedValue(new Response(JSON.stringify(deviceDetail), { status: 200 }));
    render(<StrictMode><MemoryRouter initialEntries={["/devices/f004-leaf01"]}><Routes><Route path="/devices/:deviceName" element={<DeviceDetailPage />} /></Routes></MemoryRouter></StrictMode>);
    expect(await screen.findByRole("heading", { name: "f004-leaf01" })).toBeInTheDocument();
    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual(["/api/devices/f004-leaf01?live=true", "/api/devices/f004-leaf01?live=false"]);
    expect(screen.getAllByText("The control-plane API is unavailable.")).toHaveLength(2);
    expect(screen.getByText("10.0.0.12/32")).toBeInTheDocument();
  });

  it("shows null observed live values as unavailable and exposes artifact existence and source freshness", async () => {
    const detail = {
      ...deviceDetail,
      latest_artifact: { ...deviceDetail.latest_artifact, data: { ...deviceDetail.latest_artifact.data!, available: false } },
      live_state: {
        ...deviceDetail.live_state,
        data: { ...deviceDetail.live_state.data!, interfaces: [{ name: "interface.ethernet-1/1.admin-state", status: "failed", expected: "enable", observed: null, message: "Missing" }] },
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
      live_state: { availability: { ...deviceDetail.live_state.availability, status: "unavailable", message: "Device read timed out" }, data: null },
    };
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify(detail), { status: 200 }));
    render(<MemoryRouter initialEntries={["/devices/f004-leaf01"]}><Routes><Route path="/devices/:deviceName" element={<DeviceDetailPage />} /></Routes></MemoryRouter>);
    expect((await screen.findAllByText("Observations unavailable")).length).toBe(2);
    expect(screen.queryByText("No records returned")).not.toBeInTheDocument();
  });

  it("shows live invariants with expected, observed, and safe mismatch context", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify(deviceDetail), { status: 200 }));
    render(<MemoryRouter initialEntries={["/devices/f004-leaf01"]}><Routes><Route path="/devices/:deviceName" element={<DeviceDetailPage />} /></Routes></MemoryRouter>);
    expect(await screen.findByText("interface.ethernet-1/1.admin-state")).toBeInTheDocument();
    expect(screen.getAllByText("Expected").length).toBeGreaterThan(0);
    expect(screen.getByText("enable")).toBeInTheDocument();
    expect(screen.getAllByText("Observed").length).toBeGreaterThan(0);
    expect(screen.getByText("disable")).toBeInTheDocument();
    expect(screen.getByText("Interface state does not match")).toBeInTheDocument();
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
