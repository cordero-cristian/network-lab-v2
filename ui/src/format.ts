export function formatTime(value: string | null | undefined, includeDate = false): string {
  if (!value) return "Not available";
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) return "Not available";
  return new Intl.DateTimeFormat("en", {
    ...(includeDate ? { month: "short", day: "numeric" } : {}),
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
    timeZone: "UTC",
  }).format(date) + " UTC";
}

export function formatDuration(milliseconds: number | null | undefined): string {
  if (milliseconds == null) return "Not available";
  if (milliseconds < 1000) return `${milliseconds} ms`;
  if (milliseconds < 60_000) return `${(milliseconds / 1000).toFixed(2)} s`;
  return `${Math.floor(milliseconds / 60_000)}m ${Math.round(milliseconds % 60_000 / 1000)}s`;
}

export function shortId(value: string | null | undefined, length = 13): string {
  if (!value) return "Not retained";
  return value.length > length ? `${value.slice(0, length)}…` : value;
}

export function titleCase(value: string | null | undefined): string {
  if (!value) return "Unknown";
  return value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export function valueText(value: unknown): string {
  if (value == null || value === "") return "Not available";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}
