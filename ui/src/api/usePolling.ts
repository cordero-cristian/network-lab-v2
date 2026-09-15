import { useEffect, useRef, useState } from "react";
import { getJson } from "./client";

export interface PollingState<T> {
  data: T | null;
  error: Error | null;
  loading: boolean;
  refreshing: boolean;
  stale: boolean;
  staleReason: "age" | "refresh" | null;
}

export function usePolling<T>(path: string, intervalMs: number, stopWhen?: (value: T) => boolean): PollingState<T> {
  const [state, setState] = useState<PollingState<T>>({ data: null, error: null, loading: true, refreshing: false, stale: false, staleReason: null });
  const stopWhenRef = useRef(stopWhen);
  stopWhenRef.current = stopWhen;

  useEffect(() => {
    let disposed = false;
    let running = false;
    let stopped = false;
    let timer: number | undefined;
    let staleTimer: number | undefined;
    let controller: AbortController | undefined;

    const observationTime = (value: T): string | undefined => {
      if (typeof value !== "object" || value === null) return undefined;
      const record = value as Record<string, unknown>;
      if (typeof record.observed_at === "string") return record.observed_at;
      const summary = record.summary;
      if (typeof summary === "object" && summary !== null && typeof (summary as Record<string, unknown>).observed_at === "string") return (summary as Record<string, unknown>).observed_at as string;
      const historyStatus = record.history_status;
      if (typeof historyStatus === "object" && historyStatus !== null && typeof (historyStatus as Record<string, unknown>).observed_at === "string") return (historyStatus as Record<string, unknown>).observed_at as string;
      return undefined;
    };
    const scheduleStale = (value: T) => {
      if (staleTimer) window.clearTimeout(staleTimer);
      const observedAt = observationTime(value);
      if (!observedAt) return;
      const delay = Math.max(0, Date.parse(observedAt) + intervalMs * 2 - Date.now());
      staleTimer = window.setTimeout(() => setState((previous) => ({ ...previous, stale: previous.data !== null, staleReason: previous.data !== null ? "age" : null })), delay);
    };

    const schedule = () => {
      if (!disposed && !stopped) timer = window.setTimeout(run, intervalMs);
    };
    const run = async () => {
      if (disposed || stopped || running || document.visibilityState === "hidden") return;
      running = true;
      controller = new AbortController();
      setState((previous) => ({ ...previous, refreshing: previous.data !== null }));
      try {
        const data = await getJson<T>(path, controller.signal);
        if (disposed) return;
        stopped = stopWhenRef.current?.(data) ?? false;
        setState({ data, error: null, loading: false, refreshing: false, stale: false, staleReason: null });
        scheduleStale(data);
      } catch (error) {
        if (disposed) return;
        setState((previous) => ({ ...previous, error: error as Error, loading: false, refreshing: false, stale: previous.data !== null, staleReason: previous.data !== null ? "refresh" : null }));
      } finally {
        running = false;
        if (!disposed && !stopped) schedule();
      }
    };
    const onVisibility = () => {
      if (document.visibilityState === "visible" && !running && !stopped) {
        if (timer) window.clearTimeout(timer);
        void run();
      }
    };
    void run();
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      disposed = true;
      if (timer) window.clearTimeout(timer);
      if (staleTimer) window.clearTimeout(staleTimer);
      controller?.abort();
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [path, intervalMs]);

  return state;
}
