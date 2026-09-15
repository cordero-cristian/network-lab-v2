import { act, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { workflowDetail } from "../test/fixtures";
import { WorkflowDetailPage } from "./WorkflowDetailPage";

describe("WorkflowDetailPage polling", () => {
  afterEach(() => vi.useRealTimers());

  it("stops four-second polling after a terminal response", async () => {
    vi.useFakeTimers();
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify(workflowDetail), { status: 200 }));
    render(<MemoryRouter initialEntries={[`/workflows/${encodeURIComponent(workflowDetail.summary.workflow_id)}?run_id=${workflowDetail.summary.run_id}`]}><Routes><Route path="/workflows/:workflowId" element={<WorkflowDetailPage />} /></Routes></MemoryRouter>);
    await act(async () => { await Promise.resolve(); await Promise.resolve(); });
    expect(screen.getByRole("heading", { name: "Deployment Failed" })).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    await act(() => vi.advanceTimersByTimeAsync(12_000));
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("refreshes a running execution at four seconds and stops on its terminal response", async () => {
    vi.useFakeTimers();
    const running = { ...workflowDetail, summary: { ...workflowDetail.summary, execution_status: "running", outcome: "running", completed_at: null } };
    const fetchMock = vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(new Response(JSON.stringify(running), { status: 200 }))
      .mockResolvedValue(new Response(JSON.stringify(workflowDetail), { status: 200 }));
    render(<MemoryRouter initialEntries={[`/workflows/${encodeURIComponent(workflowDetail.summary.workflow_id)}?run_id=${workflowDetail.summary.run_id}`]}><Routes><Route path="/workflows/:workflowId" element={<WorkflowDetailPage />} /></Routes></MemoryRouter>);
    await act(async () => { await Promise.resolve(); await Promise.resolve(); });
    expect(screen.getByRole("heading", { name: "Running" })).toBeInTheDocument();
    await act(() => vi.advanceTimersByTimeAsync(4_000));
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(screen.getByRole("heading", { name: "Deployment Failed" })).toBeInTheDocument();
    await act(() => vi.advanceTimersByTimeAsync(8_000));
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("uses the history observation time when retained detail becomes stale", async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-09-14T15:45:01Z"));
    const running = {
      ...workflowDetail,
      summary: { ...workflowDetail.summary, execution_status: "running", outcome: "running", completed_at: null },
      history_status: { ...workflowDetail.history_status, observed_at: "2026-09-14T15:45:00Z" },
    };
    vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(new Response(JSON.stringify(running), { status: 200 }))
      .mockRejectedValue(new Error("offline"));
    render(<MemoryRouter initialEntries={[`/workflows/${encodeURIComponent(workflowDetail.summary.workflow_id)}?run_id=${workflowDetail.summary.run_id}`]}><Routes><Route path="/workflows/:workflowId" element={<WorkflowDetailPage />} /></Routes></MemoryRouter>);
    await act(async () => { await Promise.resolve(); await Promise.resolve(); });
    await act(() => vi.advanceTimersByTimeAsync(4_000));
    expect(screen.getByText(/Retaining the observation from 15:45:00 UTC/)).toBeInTheDocument();
  });

  it("ages a terminal detail stale without restarting polling", async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-09-14T14:32:18Z"));
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify(workflowDetail), { status: 200 }));
    render(<MemoryRouter initialEntries={[`/workflows/${encodeURIComponent(workflowDetail.summary.workflow_id)}`]}><Routes><Route path="/workflows/:workflowId" element={<WorkflowDetailPage />} /></Routes></MemoryRouter>);
    await act(async () => { await Promise.resolve(); await Promise.resolve(); });
    await act(() => vi.advanceTimersByTimeAsync(8_000));
    expect(screen.getByText(/Observation age exceeded the freshness window/)).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("distinguishes unavailable history from empty retained history", async () => {
    const unavailable = { ...workflowDetail, stages: [], history_status: { ...workflowDetail.history_status, status: "unavailable", message: "History unavailable" } };
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify(unavailable), { status: 200 }));
    render(<MemoryRouter initialEntries={[`/workflows/${encodeURIComponent(workflowDetail.summary.workflow_id)}`]}><Routes><Route path="/workflows/:workflowId" element={<WorkflowDetailPage />} /></Routes></MemoryRouter>);
    expect(await screen.findByText("Observations unavailable")).toBeInTheDocument();
    expect(screen.queryByText("No records returned")).not.toBeInTheDocument();
  });
});
