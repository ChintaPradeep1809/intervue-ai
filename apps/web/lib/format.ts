export function formatDate(
  d: string | Date | null | undefined,
  opts: Intl.DateTimeFormatOptions = { dateStyle: "medium" },
): string {
  if (!d) return "—";
  const date = typeof d === "string" ? new Date(d) : d;
  return new Intl.DateTimeFormat(undefined, opts).format(date);
}

export function formatDateTime(d: string | Date | null | undefined): string {
  return formatDate(d, { dateStyle: "medium", timeStyle: "short" });
}

export function formatDuration(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds));
  const m = Math.floor(s / 60);
  const r = s % 60;
  return `${String(m).padStart(2, "0")}:${String(r).padStart(2, "0")}`;
}

export function titleCase(s: string): string {
  return s.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export type Tone = "success" | "warning" | "destructive" | "muted";

export function scoreTone(score: number | null | undefined): Tone {
  if (score === null || score === undefined) return "muted";
  if (score >= 75) return "success";
  if (score >= 55) return "warning";
  return "destructive";
}

export function pct(n: number): string {
  return `${Math.round(n * 100)}%`;
}

export function money(usd: number, digits = 4): string {
  return `$${usd.toFixed(digits)}`;
}
