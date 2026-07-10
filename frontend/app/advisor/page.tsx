"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { DimensionRadar } from "@/components/charts";
import { Badge, Card, CardBody, Empty, KpiCard, SectionTitle, Skeleton } from "@/components/ui";
import { prettyDate, round, scoreBg } from "@/lib/format";
import { useApi } from "@/lib/useApi";
import type { AdvisorSummary, CallListItem } from "@/lib/types";

const ADVISORS = [
  "Arjun Rao", "Priya Nair", "Rohit Sharma", "Sneha Iyer", "Karan Mehta",
  "Meera Das", "Vikram Singh", "Anjali Gupta", "Dev Kapoor",
];
const DIM_SHORT: Record<string, string> = {
  needs_discovery: "Discovery",
  product_knowledge: "Product",
  objection_handling: "Objection",
  compliance_integrity: "Compliance",
  next_step_booking: "Next step",
};

function AdvisorInner() {
  const sp = useSearchParams();
  const [advisorId, setAdvisorId] = useState(Number(sp.get("advisor") ?? 1));
  const summary = useApi<AdvisorSummary>(`/advisors/${advisorId}/summary`);
  const calls = useApi<CallListItem[]>(`/advisors/${advisorId}/calls`);

  const radar =
    summary.data?.dimensions.map((d) => ({
      dimension: DIM_SHORT[d.dimension] ?? d.dimension,
      my: Number(d.my_avg ?? 0),
      team: Number(d.team_avg ?? 0),
    })) ?? [];

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between">
        <div>
          <h1 className="text-xl font-semibold">My calls — {summary.data?.advisor.advisor_name ?? "…"}</h1>
          <p className="text-sm text-muted">Advisor view</p>
        </div>
        <select
          value={advisorId}
          onChange={(e) => setAdvisorId(Number(e.target.value))}
          className="rounded-lg border border-border bg-white px-3 py-1.5 text-sm"
        >
          {ADVISORS.map((n, i) => (
            <option key={i} value={i + 1}>{n}</option>
          ))}
        </select>
      </div>

      {summary.error && <Empty>Couldn&apos;t load advisor. {summary.error}</Empty>}

      {summary.data && (
        <>
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-3">
            <KpiCard label="My avg score" value={round(summary.data.advisor.avg_composite)} tone={tone(summary.data.advisor.avg_composite)} />
            <KpiCard label="Scored calls" value={summary.data.advisor.scored_calls} />
            <KpiCard label="Critical flags" value={summary.data.advisor.critical_flags} tone={summary.data.advisor.critical_flags ? "crit" : "ok"} />
          </div>

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <Card>
              <CardBody>
                <SectionTitle>My dimensions vs team average</SectionTitle>
                {radar.length ? <DimensionRadar data={radar} /> : <Empty>No scores yet</Empty>}
              </CardBody>
            </Card>
            <Card>
              <CardBody>
                <SectionTitle>Where I stand</SectionTitle>
                <ul className="space-y-2 text-sm">
                  {summary.data.dimensions.map((d) => {
                    const my = Number(d.my_avg ?? 0);
                    const team = Number(d.team_avg ?? 0);
                    const delta = my - team;
                    return (
                      <li key={d.dimension} className="flex items-center justify-between">
                        <span>{DIM_SHORT[d.dimension] ?? d.dimension}</span>
                        <span className="flex items-center gap-2">
                          <span className="font-medium">{my.toFixed(1)}</span>
                          <span className={`text-xs ${delta >= 0 ? "text-ok" : "text-crit"}`}>
                            {delta >= 0 ? "▲" : "▼"} {Math.abs(delta).toFixed(1)} vs team
                          </span>
                        </span>
                      </li>
                    );
                  })}
                </ul>
              </CardBody>
            </Card>
          </div>
        </>
      )}

      <Card>
        <CardBody>
          <SectionTitle>My calls</SectionTitle>
          {calls.loading && <Skeleton className="h-32" />}
          {calls.data && calls.data.length === 0 && <Empty>No calls yet.</Empty>}
          {calls.data && calls.data.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border text-left text-xs uppercase text-muted">
                    <th className="py-2 font-medium">Call</th>
                    <th className="py-2 font-medium">Date</th>
                    <th className="py-2 font-medium">Score</th>
                    <th className="py-2 font-medium">Flags</th>
                    <th className="py-2 font-medium">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {calls.data.map((c) => (
                    <tr key={c.id} className="border-b border-border/60 hover:bg-gray-50">
                      <td className="py-2.5">
                        <Link href={`/calls/${c.id}`} className="font-medium text-brand hover:underline">
                          Call #{c.id}
                        </Link>
                      </td>
                      <td className="py-2.5 text-muted">{prettyDate(c.called_at)}</td>
                      <td className="py-2.5">
                        {c.composite == null ? (
                          <span className="text-muted">—</span>
                        ) : (
                          <span className={`inline-flex rounded-md px-2 py-0.5 text-xs font-semibold ${scoreBg(c.composite)}`}>
                            {round(c.composite)}
                            {c.compliance_capped && <span className="ml-1" title="capped by compliance flag">⚠</span>}
                          </span>
                        )}
                      </td>
                      <td className="py-2.5">
                        {c.critical_count > 0 && <Badge className="border-red-200 bg-red-50 text-crit">{c.critical_count} critical</Badge>}
                        {c.critical_count === 0 && <span className="text-muted">{c.flag_count}</span>}
                      </td>
                      <td className="py-2.5 text-xs text-muted">{c.status}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardBody>
      </Card>
    </div>
  );
}

function tone(v: number | null): "ok" | "warn" | "crit" | "default" {
  if (v == null) return "default";
  return v >= 70 ? "ok" : v >= 40 ? "warn" : "crit";
}

export default function AdvisorPage() {
  return (
    <Suspense fallback={<Skeleton className="h-64" />}>
      <AdvisorInner />
    </Suspense>
  );
}
