// Types mirroring the FastAPI responses.

export interface CallListItem {
  id: number;
  status: string;
  called_at: string | null;
  source: string;
  duration_s: number | null;
  advisor_name: string | null;
  advisor_id: number | null;
  composite: number | null;
  compliance_capped: boolean | null;
  flag_count: number;
  critical_count: number;
}

export interface Segment {
  idx: number;
  speaker: string;
  start_s: number;
  end_s: number;
  text: string;
}

export interface Score {
  dimension: string;
  raw_score: number;
  weight: number;
  evidence_quote: string | null;
  evidence_start_s: number | null;
  model: string | null;
  prompt_hash: string | null;
}

export interface Flag {
  id: number;
  tag: string;
  severity: "info" | "warn" | "critical";
  start_s: number | null;
  end_s: number | null;
  quote: string | null;
  reason: string | null;
  confidence: number | null;
  state: "open" | "disputed" | "upheld" | "dismissed";
}

export interface Job {
  stage: string;
  status: "pending" | "running" | "done" | "failed" | "dead";
  attempts: number;
  last_error: string | null;
}

export interface CallDetail {
  call: {
    id: number;
    status: string;
    source: string;
    called_at: string | null;
    duration_s: number | null;
    channels: number | null;
    language_hint: string | null;
    audio_uri: string | null;
    raw_metadata: Record<string, unknown>;
    advisor_id: number | null;
    advisor_name: string | null;
    team_name: string | null;
    composite: number | null;
    compliance_capped: boolean | null;
    rubric_version: string | null;
  };
  transcript: {
    engine: string;
    language: string | null;
    code_switch_ratio: number | null;
    wer_estimate: number | null;
  } | null;
  segments: Segment[];
  scores: Score[];
  flags: Flag[];
  jobs: Job[];
}

export interface OrgSummary {
  org: { org_id: number; org_name: string; avg_composite: number | null; active_teams: number; critical_flags: number };
  kpis: { calls_processed: number; critical_flags_week: number; open_disputes: number };
  teams: TeamRow[];
  trend: { day: string; avg_composite: number }[];
  risk_feed: { flag_id: number; call_id: number; tag: string; quote: string; created_at: string; advisor_name: string | null }[];
}

export interface TeamRow {
  team_id: number;
  org_id: number;
  team_name: string;
  active_advisors: number;
  avg_composite: number | null;
  critical_flags: number;
}

export interface AdvisorRow {
  advisor_id: number;
  team_id: number;
  org_id: number;
  advisor_name: string;
  scored_calls: number;
  avg_composite: number | null;
  critical_flags: number;
}

export interface TeamSummary {
  team: TeamRow;
  leaderboard: AdvisorRow[];
  heatmap: { advisor_id: number; advisor_name: string; dimension: string; avg_score: number }[];
  dispute_inbox: {
    dispute_id: number; flag_id: number; note: string | null; created_at: string;
    call_id: number; tag: string; quote: string; start_s: number | null; advisor_name: string | null;
  }[];
}

export interface AdvisorSummary {
  advisor: AdvisorRow;
  dimensions: { dimension: string; my_avg: number | null; team_avg: number | null }[];
  trend: { day: string; composite: number }[];
}
