"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { Badge, Button, Card, CardBody, Empty, KpiCard, SectionTitle, Skeleton } from "@/components/ui";
import { api } from "@/lib/api";
import { prettyTag, round, scoreBg, scoreColor } from "@/lib/format";
import { useApi } from "@/lib/useApi";
import type { TeamSummary } from "@/lib/types";

const DIMS = ["needs_discovery", "product_knowledge", "objection_handling", "compliance_integrity", "next_step_booking"];
const DIM_SHORT: Record<string, string> = {
  needs_discovery: "Discovery",
  product_knowledge: "Product",
  objection_handling: "Objection",
  compliance_integrity: "Compliance",
  next_step_booking: "Next step",
};

function cellColor(v: number) {
  if (v >= 4) return "bg-green-100 text-green-800";
  if (v >= 2.5) return "bg-amber-100 text-amber-800";
  return "bg-red-100 text-red-800";
}

function TeamInner() {
  const sp = useSearchParams();
  const [teamId, setTeamId] = useState(Number(sp.get("team") ?? 1));
  const { data, loading, error, reload } = useApi<TeamSummary>(`/teams/${teamId}/summary`);
  const [busy, setBusy] = useState<number | null>(null);

  async function resolve(disputeId: number, resolution: "upheld" | "dismissed") {
    setBusy(disputeId);
    try {
      await api.post(`/disputes/${disputeId}/resolve`, { resolution, resolved_by: "tl_meera" });
      reload();
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between">
        <div>
          <h1 className="text-xl font-semibold">Coaching — {data?.team.team_name ?? "…"}</h1>
          <p className="text-sm text-muted">Team Leader view</p>
        </div>
        <select
          value={teamId}
          onChange={(e) => setTeamId(Number(e.target.value))}
          className="rounded-lg border border-border bg-white px-3 py-1.5 text-sm"
        >
          {[1, 2, 3].map((t) => (
            <option key={t} value={t}>Pod {["Alpha", "Beta", "Gamma"][t - 1]}</option>
          ))}
        </select>
      </div>

      {loading && <Skeleton className="h-64" />}
      {error && <Empty>Couldn&apos;t load team. {error}</Empty>}

      {data && (
        <>
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <KpiCard label="Team avg" value={round(data.team.avg_composite)} tone={tone(data.team.avg_composite)} />
            <KpiCard label="Advisors" value={data.team.active_advisors} />
            <KpiCard label="Critical flags" value={data.team.critical_flags} tone={data.team.critical_flags ? "crit" : "ok"} />
            <KpiCard label="Open disputes" value={data.dispute_inbox.length} tone={data.dispute_inbox.length ? "warn" : "default"} />
          </div>

          <Card>
            <CardBody>
              <SectionTitle>Advisor leaderboard</SectionTitle>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border text-left text-xs uppercase text-muted">
                      <th className="py-2 font-medium">Advisor</th>
                      <th className="py-2 font-medium">Score</th>
                      <th className="py-2 font-medium">Calls</th>
                      <th className="py-2 font-medium">Critical</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.leaderboard.map((a) => (
                      <tr key={a.advisor_id} className="border-b border-border/60 hover:bg-gray-50">
                        <td className="py-2.5">
                          <Link href={`/advisor?advisor=${a.advisor_id}`} className="font-medium text-ink hover:text-brand">
                            {a.advisor_name}
                          </Link>
                        </td>
                        <td className="py-2.5">
                          <span className={`inline-flex rounded-md px-2 py-0.5 text-xs font-semibold ${scoreBg(a.avg_composite)}`}>
                            {round(a.avg_composite)}
                          </span>
                        </td>
                        <td className="py-2.5 text-muted">{a.scored_calls}</td>
                        <td className="py-2.5">
                          {a.critical_flags > 0 ? (
                            <span className="text-crit">{a.critical_flags}</span>
                          ) : (
                            <span className="text-muted">0</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </CardBody>
          </Card>

          <Card>
            <CardBody>
              <SectionTitle>Coaching heatmap — what to coach, per advisor</SectionTitle>
              <Heatmap rows={data.leaderboard.map((a) => a.advisor_name)} heatmap={data.heatmap} />
            </CardBody>
          </Card>

          <Card>
            <CardBody>
              <SectionTitle right={<span className="text-xs text-muted">{data.dispute_inbox.length} pending</span>}>
                Dispute inbox
              </SectionTitle>
              {data.dispute_inbox.length === 0 ? (
                <Empty>No open disputes.</Empty>
              ) : (
                <ul className="space-y-3">
                  {data.dispute_inbox.map((d) => (
                    <li key={d.dispute_id} className="rounded-lg border border-border p-3">
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <div className="flex items-center gap-2">
                            <Badge className="border-red-200 bg-red-50 text-crit">{prettyTag(d.tag)}</Badge>
                            <span className="text-xs text-muted">{d.advisor_name}</span>
                          </div>
                          <p className="mt-1 text-sm">“{d.quote}”</p>
                          {d.note && <p className="mt-1 text-xs text-muted">Advisor: {d.note}</p>}
                          <Link href={`/calls/${d.call_id}?t=${Math.floor(d.start_s ?? 0)}`} className="mt-1 inline-block text-xs text-brand hover:underline">
                            ▶ Listen at {Math.floor(d.start_s ?? 0)}s
                          </Link>
                        </div>
                        <div className="flex shrink-0 gap-2">
                          <Button size="sm" variant="danger" disabled={busy === d.dispute_id} onClick={() => resolve(d.dispute_id, "upheld")}>
                            Uphold
                          </Button>
                          <Button size="sm" variant="ok" disabled={busy === d.dispute_id} onClick={() => resolve(d.dispute_id, "dismissed")}>
                            Dismiss
                          </Button>
                        </div>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </CardBody>
          </Card>
        </>
      )}
    </div>
  );
}

function Heatmap({ rows, heatmap }: { rows: string[]; heatmap: TeamSummary["heatmap"] }) {
  const byAdvisor: Record<string, Record<string, number>> = {};
  for (const h of heatmap) {
    byAdvisor[h.advisor_name] ??= {};
    byAdvisor[h.advisor_name][h.dimension] = Number(h.avg_score);
  }
  const names = rows.filter((n) => byAdvisor[n]);
  if (!names.length) return <Empty>No scored calls yet.</Empty>;
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-xs uppercase text-muted">
            <th className="py-2 font-medium">Advisor</th>
            {DIMS.map((d) => <th key={d} className="px-2 py-2 text-center font-medium">{DIM_SHORT[d]}</th>)}
          </tr>
        </thead>
        <tbody>
          {names.map((n) => (
            <tr key={n}>
              <td className="py-1.5 pr-2 font-medium">{n}</td>
              {DIMS.map((d) => {
                const v = byAdvisor[n][d];
                return (
                  <td key={d} className="px-1 py-1 text-center">
                    {v == null ? (
                      <span className="text-muted">—</span>
                    ) : (
                      <span className={`inline-flex w-9 justify-center rounded-md py-1 text-xs font-semibold ${cellColor(v)}`}>
                        {v.toFixed(1)}
                      </span>
                    )}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function tone(v: number | null): "ok" | "warn" | "crit" | "default" {
  if (v == null) return "default";
  return v >= 70 ? "ok" : v >= 40 ? "warn" : "crit";
}

export default function TeamPage() {
  return (
    <Suspense fallback={<Skeleton className="h-64" />}>
      <TeamInner />
    </Suspense>
  );
}
