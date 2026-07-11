"use client";

import Link from "next/link";
import { TeamBars, TrendLine } from "@/components/charts";
import { UploadCall } from "@/components/UploadCall";
import { API_BASE } from "@/lib/api";
import { Badge, Card, CardBody, Empty, KpiCard, SectionTitle, Skeleton } from "@/components/ui";
import { prettyDate, prettyTag, round, scoreColor } from "@/lib/format";
import { useApi } from "@/lib/useApi";
import type { OrgSummary } from "@/lib/types";

export default function DirectorPage() {
  const { data, loading, error } = useApi<OrgSummary>("/orgs/1/summary");

  if (loading) return <LoadingGrid />;
  if (error || !data)
    return (
      <Empty>
        Couldn&apos;t reach the API this build points at: <b>{API_BASE}</b>.
        {API_BASE.includes("localhost") &&
          " (NEXT_PUBLIC_API_URL wasn't set at build time — set it in Vercel and redeploy.)"}{" "}
        {error}
      </Empty>
    );

  const { org, kpis, teams, trend, risk_feed } = data;
  const trendData = trend.map((t) => ({ label: prettyDate(t.day), value: Number(t.avg_composite) }));
  const teamData = teams
    .filter((t) => t.avg_composite != null)
    .map((t) => ({ name: t.team_name.replace("Pod ", ""), value: Number(t.avg_composite) }));

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold">Org health — {org.org_name}</h1>
        <p className="text-sm text-muted">Sales Director view</p>
      </div>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <KpiCard label="Org avg score" value={round(org.avg_composite)} tone={score_tone(org.avg_composite)} sub="mean over teams" />
        <KpiCard label="Calls processed" value={kpis.calls_processed} sub="fully analysed" />
        <KpiCard label="Critical flags" value={kpis.critical_flags_week} tone={kpis.critical_flags_week ? "crit" : "ok"} sub="last 7 days" />
        <KpiCard label="Open disputes" value={kpis.open_disputes} tone={kpis.open_disputes ? "warn" : "default"} sub="awaiting TL" />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardBody>
            <SectionTitle>Org score over time</SectionTitle>
            {trendData.length ? <TrendLine data={trendData} /> : <Empty>No trend yet</Empty>}
          </CardBody>
        </Card>
        <Card>
          <CardBody>
            <SectionTitle>Team comparison</SectionTitle>
            {teamData.length ? <TeamBars data={teamData} /> : <Empty>No teams scored</Empty>}
          </CardBody>
        </Card>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardBody>
            <SectionTitle right={<span className="text-xs text-muted">{risk_feed.length} flagged</span>}>
              Risk feed — latest critical flags
            </SectionTitle>
            {risk_feed.length === 0 ? (
              <Empty>No critical flags 🎉</Empty>
            ) : (
              <ul className="divide-y divide-border">
                {risk_feed.map((r) => (
                  <li key={r.flag_id} className="py-2.5">
                    <Link href={`/calls/${r.call_id}`} className="group flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <Badge className="border-red-200 bg-red-50 text-crit">{prettyTag(r.tag)}</Badge>
                          <span className="text-xs text-muted">{r.advisor_name ?? "unknown"}</span>
                        </div>
                        <p className="mt-1 truncate text-sm text-ink group-hover:text-brand">
                          “{r.quote}”
                        </p>
                      </div>
                      <span className="shrink-0 text-xs text-muted">{prettyDate(r.created_at)}</span>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </CardBody>
        </Card>

        <Card>
          <CardBody>
            <SectionTitle>Ingest a call</SectionTitle>
            <UploadCall />
          </CardBody>
        </Card>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        {teams.map((t) => (
          <Link key={t.team_id} href={`/team?team=${t.team_id}`}>
            <Card className="transition hover:border-brand">
              <CardBody className="flex items-center justify-between">
                <div>
                  <div className="font-medium">{t.team_name}</div>
                  <div className="text-xs text-muted">{t.active_advisors} advisors · {t.critical_flags} critical</div>
                </div>
                <div className={`text-2xl font-semibold ${scoreColor(t.avg_composite)}`}>{round(t.avg_composite)}</div>
              </CardBody>
            </Card>
          </Link>
        ))}
      </div>
    </div>
  );
}

function score_tone(v: number | null): "ok" | "warn" | "crit" | "default" {
  if (v == null) return "default";
  return v >= 70 ? "ok" : v >= 40 ? "warn" : "crit";
}

function LoadingGrid() {
  return (
    <div className="space-y-6">
      <Skeleton className="h-8 w-64" />
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-24" />)}
      </div>
      <Skeleton className="h-64" />
    </div>
  );
}
