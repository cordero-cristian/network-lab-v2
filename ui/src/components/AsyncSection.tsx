import type { ReactNode } from "react";
import type { SourceAvailability } from "../api/types";
import { formatTime, titleCase } from "../format";
import { Status } from "./Status";

export function SkeletonRows({ count = 4 }: { count?: number }) {
  return <div className="skeleton-list" aria-label="Loading"><span className="sr-only">Loading observations</span>{Array.from({ length: count }, (_, index) => <span className="skeleton-row" key={index} />)}</div>;
}

export function RouteError({ title = "Observation unavailable", error, back }: { title?: string; error: Error; back?: ReactNode }) {
  return (
    <section className="message-panel message-panel--error" role="alert">
      <span className="eyebrow">Safe error</span>
      <h2>{title}</h2>
      <p>{error.message}</p>
      {back}
    </section>
  );
}

export function EmptyState({ source, children }: { source: string; children: ReactNode }) {
  return <div className="empty-state"><span className="empty-state__mark" aria-hidden="true">0</span><div><strong>No records returned</strong><p>{children}</p><small>Authoritative source: {source}</small></div></div>;
}

export function UnavailableState({ source, message }: { source: string; message?: string | null }) {
  return <div className="empty-state"><span className="empty-state__mark" aria-hidden="true">!</span><div><strong>Observations unavailable</strong><p>{message ?? `${source} did not provide this section.`}</p><small>Authoritative source: {source}</small></div></div>;
}

export function AvailabilityBanner({ availability }: { availability: SourceAvailability }) {
  if (availability.status === "healthy") return null;
  return (
    <div className="source-banner" role="status">
      <Status value={availability.status} compact />
      <span>{availability.message ?? `${titleCase(availability.source)} observations are ${availability.status}.`}</span>
      <time dateTime={availability.observed_at}>{formatTime(availability.observed_at)}</time>
    </div>
  );
}

export function StaleBanner({ observedAt, reason = "refresh" }: { observedAt?: string; reason?: "age" | "refresh" | null }) {
  const message = reason === "age" ? "Observation age exceeded the freshness window." : "Latest refresh failed.";
  return <div className="stale-banner" role="status"><Status value="degraded" label="Stale" compact /><span>{message} Retaining the observation from {formatTime(observedAt)}.</span></div>;
}

export function Panel({ title, meta, children, className = "" }: { title: string; meta?: ReactNode; children: ReactNode; className?: string }) {
  return <section className={`panel ${className}`}><header className="panel__head"><h2>{title}</h2>{meta && <div className="panel__meta">{meta}</div>}</header>{children}</section>;
}
