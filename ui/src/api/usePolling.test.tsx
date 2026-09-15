import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { usePolling } from "./usePolling";

function Harness({ stop = false }: { stop?: boolean }) {
  const state = usePolling<{ value: number }>("/api/value", 1_000, stop ? () => true : undefined);
  return <div>{state.loading ? "loading" : state.data?.value}{state.stale ? " stale" : ""}</div>;
}

describe("usePolling", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("does not overlap requests and retains stale data after refresh failure", async () => {
    let resolveFirst!: (response: Response) => void;
    const fetchMock = vi.spyOn(globalThis, "fetch")
      .mockImplementationOnce(() => new Promise<Response>((resolve) => { resolveFirst = resolve; }))
      .mockRejectedValueOnce(new Error("offline"));
    render(<Harness />);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    await act(() => vi.advanceTimersByTimeAsync(5_000));
    expect(fetchMock).toHaveBeenCalledTimes(1);
    await act(async () => { resolveFirst(new Response(JSON.stringify({ value: 7 }), { status: 200 })); await Promise.resolve(); await Promise.resolve(); });
    expect(screen.getByText("7")).toBeInTheDocument();
    await act(() => vi.advanceTimersByTimeAsync(1_000));
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(screen.getByText("7 stale")).toBeInTheDocument();
  });

  it("pauses while the document is hidden", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({ value: 1 }), { status: 200 }));
    render(<Harness />);
    await act(async () => { await Promise.resolve(); await Promise.resolve(); });
    Object.defineProperty(document, "visibilityState", { configurable: true, value: "hidden" });
    await act(() => vi.advanceTimersByTimeAsync(2_000));
    expect(fetchMock).toHaveBeenCalledTimes(1);
    Object.defineProperty(document, "visibilityState", { configurable: true, value: "visible" });
    await act(async () => document.dispatchEvent(new Event("visibilitychange")));
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("stops polling terminal resources but still ages the retained response stale", async () => {
    vi.setSystemTime(new Date("2026-09-14T14:32:18Z"));
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({ value: 1, observed_at: "2026-09-14T14:32:18Z" }), { status: 200 }));
    render(<Harness stop />);
    await act(async () => { await Promise.resolve(); await Promise.resolve(); });
    await act(() => vi.advanceTimersByTimeAsync(2_000));
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(screen.getByText("1 stale")).toBeInTheDocument();
  });

  it("aborts an in-flight request on navigation cleanup", () => {
    let signal: AbortSignal | null = null;
    vi.spyOn(globalThis, "fetch").mockImplementation((_input, init) => {
      signal = init?.signal ?? null;
      return new Promise<Response>(() => {});
    });
    const view = render(<Harness />);
    expect((signal as unknown as AbortSignal).aborted).toBe(false);
    view.unmount();
    expect((signal as unknown as AbortSignal).aborted).toBe(true);
  });
});
