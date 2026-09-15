import { act, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { health } from "../test/fixtures";
import { AppShell } from "./AppShell";

describe("AppShell health state", () => {
  afterEach(() => vi.useRealTimers());

  it("downgrades retained healthy data when its refresh fails", async () => {
    vi.useFakeTimers();
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(new Response(JSON.stringify(health), { status: 200 })).mockRejectedValue(new Error("offline"));
    render(<MemoryRouter><Routes><Route element={<AppShell />}><Route index element={<div>Overview content</div>} /></Route></Routes></MemoryRouter>);
    await act(async () => { await Promise.resolve(); await Promise.resolve(); });
    expect(screen.getByLabelText("Status: Healthy")).toBeInTheDocument();
    await act(() => vi.advanceTimersByTimeAsync(15_000));
    expect(screen.getByLabelText("Status: Health stale")).toBeInTheDocument();
    expect(screen.queryByLabelText("Status: Healthy")).not.toBeInTheDocument();
  });

  it("shows unavailable rather than pending after an initial health error", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new Error("offline"));
    render(<MemoryRouter><Routes><Route element={<AppShell />}><Route index element={<div />} /></Route></Routes></MemoryRouter>);
    expect(await screen.findByLabelText("Status: Health unavailable")).toBeInTheDocument();
  });
});
