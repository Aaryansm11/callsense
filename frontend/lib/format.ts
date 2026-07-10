export function mmss(seconds: number | null | undefined): string {
  if (seconds == null) return "--:--";
  const s = Math.max(0, Math.floor(seconds));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

export function scoreColor(score: number | null | undefined): string {
  if (score == null) return "text-muted";
  if (score >= 70) return "text-ok";
  if (score >= 40) return "text-warn";
  return "text-crit";
}

export function scoreBg(score: number | null | undefined): string {
  if (score == null) return "bg-gray-100 text-muted";
  if (score >= 70) return "bg-green-50 text-ok";
  if (score >= 40) return "bg-amber-50 text-warn";
  return "bg-red-50 text-crit";
}

export const severityStyle: Record<string, string> = {
  critical: "bg-red-50 text-crit border-red-200",
  warn: "bg-amber-50 text-warn border-amber-200",
  info: "bg-gray-100 text-muted border-gray-200",
};

export const stateStyle: Record<string, string> = {
  open: "bg-gray-100 text-gray-600",
  disputed: "bg-indigo-50 text-brand",
  upheld: "bg-red-50 text-crit",
  dismissed: "bg-green-50 text-ok",
};

export function prettyTag(tag: string): string {
  return tag.replace(/_/g, " ");
}

export function prettyDate(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

export function round(n: number | null | undefined, d = 1): string {
  if (n == null) return "—";
  return Number(n).toFixed(d);
}
