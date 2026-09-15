import { afterEach, describe, expect, it, vi } from "vitest";
import { deviceDetail, devices, workflows } from "../test/fixtures";
import { getJson } from "./client";

describe("getJson", () => {
  afterEach(() => vi.useRealTimers());

  it("allows only same-origin API paths and GET requests", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({ ok: true }), { status: 200 }));
    await expect(getJson<{ ok: boolean }>("https://temporal.internal/api")).rejects.toThrow("same-origin");
    await expect(getJson<{ ok: boolean }>("/api/example")).resolves.toEqual({ ok: true });
    expect(fetchMock).toHaveBeenCalledWith("/api/example", expect.objectContaining({ method: "GET", cache: "no-store" }));
  });

  it("surfaces only the safe API error body", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({ code: "not_found", message: "Workflow was not found.", request_id: "opaque" }), { status: 404 }));
    await expect(getJson("/api/workflows/missing")).rejects.toEqual(expect.objectContaining({ status: 404, code: "not_found", message: "Workflow was not found." }));
  });

  it.each([
    ["/api/workflows", { ...workflows, items: [null] }],
    ["/api/devices", { ...devices, items: [{ name: "incomplete" }] }],
    ["/api/devices/f004-leaf01", { summary: null, intent: {}, latest_artifact: {}, latest_deployment: {}, historical_validation: {}, live_state: {} }],
    ["/api/devices/f004-leaf01", { ...deviceDetail, live_state: { ...deviceDetail.live_state, data: { ...deviceDetail.live_state.data, hostname: { ...deviceDetail.live_state.data!.hostname, expected: { unsafe: true } } } } }],
    ["/api/deployments", { items: [null], count: 1, observed_at: devices.observed_at, availability: devices.availability }],
  ])("rejects malformed nested success responses from %s", async (path, body) => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify(body), { status: 200 }));
    await expect(getJson(path)).rejects.toEqual(expect.objectContaining({ code: "internal_error", message: "The API returned an invalid response." }));
  });

  it("aborts when the caller is disposed", async () => {
    const controller = new AbortController();
    vi.spyOn(globalThis, "fetch").mockImplementation((_input, init) => new Promise<Response>((_resolve, reject) => {
      init?.signal?.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")));
    }));
    const request = getJson("/api/example", controller.signal);
    controller.abort();
    await expect(request).rejects.toEqual(expect.objectContaining({ status: 0, code: "upstream_timeout" }));
  });

  it("applies the finite client timeout", async () => {
    vi.useFakeTimers();
    vi.spyOn(globalThis, "fetch").mockImplementation((_input, init) => new Promise<Response>((_resolve, reject) => {
      init?.signal?.addEventListener("abort", () => reject(new DOMException("Timed out", "TimeoutError")));
    }));
    const request = getJson("/api/example", undefined, 10);
    await vi.advanceTimersByTimeAsync(10);
    await expect(request).rejects.toEqual(expect.objectContaining({ status: 0, code: "upstream_timeout" }));
  });
});
