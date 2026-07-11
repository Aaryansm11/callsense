"use client";

import { AlertTriangle, Check, Loader2 } from "lucide-react";
import type { Job } from "@/lib/types";

const STAGES: { key: string; label: string; blurb: string }[] = [
  { key: "transcribe", label: "Transcribe", blurb: "faster-whisper → timestamped text" },
  { key: "diarise", label: "Diarise", blurb: "who spoke when (voice-based)" },
  { key: "redact", label: "Redact", blurb: "mask PII before any LLM" },
  { key: "classify", label: "Classify", blurb: "sales vs non-sales gate" },
  { key: "analyse", label: "Analyse", blurb: "rubric scores + flags (LLM)" },
  { key: "validate", label: "Validate", blurb: "invariants, finalise" },
];

type StepState = "done" | "running" | "failed" | "pending" | "skipped";

function stateOf(job: Job | undefined, callDone: boolean): StepState {
  if (!job) return callDone ? "skipped" : "pending";
  if (job.status === "done") return "done";
  if (job.status === "running") return "running";
  if (job.status === "failed" || job.status === "dead") return "failed";
  return "pending";
}

export function PipelineStepper({
  jobs,
  processing,
  callDone,
}: {
  jobs: Job[];
  processing: boolean;
  callDone: boolean;
}) {
  const byStage: Record<string, Job> = {};
  for (const j of jobs) byStage[j.stage] = j;
  const failed = jobs.find((j) => j.status === "failed" || j.status === "dead");

  return (
    <div className="rounded-xl border border-border bg-card p-4 shadow-card">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted">
          Processing pipeline
        </h2>
        {processing && (
          <span className="inline-flex items-center gap-1.5 rounded-full bg-brand-soft px-2.5 py-1 text-xs font-medium text-brand">
            <Loader2 size={12} className="animate-spin" /> live · refreshes every 2.5s
          </span>
        )}
      </div>

      <ol className="flex overflow-x-auto pb-1">
        {STAGES.map((stage, i) => {
          const st = stateOf(byStage[stage.key], callDone);
          const isLast = i === STAGES.length - 1;
          return (
            <li key={stage.key} className="flex min-w-[7.5rem] flex-1 flex-col">
              <div className="flex items-center">
                <StepIcon state={st} index={i + 1} />
                {!isLast && (
                  <span
                    className={`mx-1.5 h-0.5 flex-1 rounded ${
                      st === "done" ? "bg-emerald-400" : "bg-border"
                    }`}
                  />
                )}
              </div>
              <p
                className={`mt-1.5 text-xs font-semibold ${
                  st === "running"
                    ? "text-brand"
                    : st === "failed"
                      ? "text-crit"
                      : st === "done"
                        ? "text-ink"
                        : "text-muted"
                }`}
              >
                {stage.label}
                {st === "skipped" && <span className="font-normal text-muted"> · skipped</span>}
                {byStage[stage.key] && byStage[stage.key].attempts > 1 && (
                  <span className="font-normal text-muted"> · try {byStage[stage.key].attempts}</span>
                )}
              </p>
              <p className="pr-3 text-[11px] leading-snug text-muted">{stage.blurb}</p>
            </li>
          );
        })}
      </ol>

      {failed && (
        <div className="mt-3 flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-crit">
          <AlertTriangle size={14} className="mt-0.5 shrink-0" />
          <span>
            <b>{failed.stage}</b> {failed.status}
            {failed.last_error ? ` — ${failed.last_error.slice(0, 220)}` : ""}
            {failed.status === "pending" ? " (retrying with backoff)" : ""}
          </span>
        </div>
      )}
    </div>
  );
}

function StepIcon({ state, index }: { state: StepState; index: number }) {
  const base =
    "flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-xs font-bold";
  switch (state) {
    case "done":
      return (
        <span className={`${base} bg-emerald-100 text-emerald-700`}>
          <Check size={15} strokeWidth={3} />
        </span>
      );
    case "running":
      return (
        <span className={`${base} bg-brand text-white shadow-sm`}>
          <Loader2 size={15} className="animate-spin" />
        </span>
      );
    case "failed":
      return (
        <span className={`${base} bg-red-100 text-crit`}>
          <AlertTriangle size={14} />
        </span>
      );
    case "skipped":
      return <span className={`${base} bg-gray-100 text-muted line-through`}>{index}</span>;
    default:
      return (
        <span className={`${base} border-2 border-border bg-white text-muted`}>{index}</span>
      );
  }
}
