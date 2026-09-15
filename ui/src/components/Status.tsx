import { titleCase } from "../format";

const failed = new Set(["failed", "unavailable", "terminated", "timed_out", "timeout"]);
const healthy = new Set(["healthy", "passed", "succeeded", "completed"]);
const active = new Set(["degraded", "running", "queued", "preparing", "deploying", "validating"]);

export function statusTone(status: string): "good" | "warn" | "bad" | "neutral" {
  const normalized = status.toLowerCase();
  if (failed.has(normalized) || normalized.endsWith("_failed") || normalized.endsWith("_timed_out")) return "bad";
  if (healthy.has(normalized) || normalized.endsWith("_succeeded")) return "good";
  if (active.has(normalized)) return "warn";
  return "neutral";
}

export function Status({ value, label, compact = false }: { value: string; label?: string; compact?: boolean }) {
  const tone = statusTone(value);
  const text = label ?? titleCase(value);
  return (
    <span className={`status status--${tone}${compact ? " status--compact" : ""}`} aria-label={`Status: ${text}`}>
      <span className="status__mark" aria-hidden="true" />
      <span>{text}</span>
    </span>
  );
}
