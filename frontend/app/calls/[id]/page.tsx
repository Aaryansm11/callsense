"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import { PipelineStepper } from "@/components/PipelineStepper";
import { Badge, Button, Card, CardBody, Empty, SectionTitle, Skeleton } from "@/components/ui";
import { API_BASE, api } from "@/lib/api";
import { mmss, prettyTag, round, scoreBg, severityStyle, stateStyle } from "@/lib/format";
import { useApi } from "@/lib/useApi";
import type { CallDetail, Flag } from "@/lib/types";

const DIM_LABEL: Record<string, string> = {
  needs_discovery: "Needs discovery",
  product_knowledge: "Product knowledge",
  objection_handling: "Objection handling",
  compliance_integrity: "Compliance & integrity",
  next_step_booking: "Next-step / trial booking",
};

function CallInner({ id }: { id: number }) {
  const sp = useSearchParams();
  const seekParam = Number(sp.get("t") ?? 0);
  const { data, loading, error, reload } = useApi<CallDetail>(`/calls/${id}`);
  const audioRef = useRef<HTMLAudioElement>(null);
  const [now, setNow] = useState(0);
  const [disputing, setDisputing] = useState<number | null>(null);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const seeked = useRef(false);

  // While the pipeline is still working on this call, poll so the page fills
  // in live (transcript appears, then scores/flags, stage chips tick over).
  const processing =
    data != null &&
    (data.call.status === "received" || data.call.status === "processing");
  useEffect(() => {
    if (!processing) return;
    const t = setInterval(reload, 2500);
    return () => clearInterval(t);
  }, [processing, reload]);

  const flagsBySeg = useMemo(() => {
    const m: Record<number, Flag[]> = {};
    if (!data) return m;
    for (const f of data.flags) {
      const seg = data.segments.find(
        (s) => f.start_s != null && f.start_s >= s.start_s && f.start_s < s.end_s
      );
      if (seg) (m[seg.idx] ??= []).push(f);
    }
    return m;
  }, [data]);

  function seek(t: number) {
    const a = audioRef.current;
    if (a) {
      a.currentTime = t;
      a.play().catch(() => {});
    }
  }

  async function submitDispute(flagId: number) {
    setBusy(true);
    try {
      await api.post(`/flags/${flagId}/dispute`, {
        note: note || "Disputed by advisor",
        raised_by: data?.call.advisor_id ?? null,
      });
      setDisputing(null);
      setNote("");
      reload();
    } finally {
      setBusy(false);
    }
  }

  if (loading && !data) return <Skeleton className="h-96" />;
  if (error || !data) return <Empty>Couldn&apos;t load call. {error}</Empty>;

  const { call, transcript, segments, scores, flags } = data;
  const diar = Number(call.raw_metadata?.["diarisation_confidence"] ?? 1);

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <Link href="/director" className="text-xs text-muted hover:text-brand">← back</Link>
          <h1 className="text-xl font-semibold">Call #{call.id}</h1>
          <p className="text-sm text-muted">
            {call.advisor_name ?? "Unknown advisor"} · {call.team_name ?? "—"} ·{" "}
            {call.language_hint ?? transcript?.language ?? "—"} · {call.source}
          </p>
        </div>
        <div className="text-right">
          <div className="text-xs uppercase text-muted">Composite</div>
          <div className={`inline-flex rounded-lg px-3 py-1 text-2xl font-semibold ${scoreBg(call.composite)}`}>
            {round(call.composite)}
          </div>
          {call.compliance_capped && (
            <div className="mt-1 text-xs font-medium text-crit">⚠ capped at 40 by a critical flag</div>
          )}
        </div>
      </div>

      {(processing ||
        data.jobs.some((j) => j.status === "failed" || j.status === "dead") ||
        (data.call.composite == null && data.jobs.length > 0)) && (
        <PipelineStepper
          jobs={data.jobs}
          processing={processing}
          callDone={data.call.status === "done"}
        />
      )}

      {diar < 0.7 && !processing && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-2 text-sm text-warn">
          ⚠ Low diarisation confidence ({diar.toFixed(2)}) — speaker labels are best-effort (mono fallback).
        </div>
      )}

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
        {/* Transcript + audio */}
        <div className="lg:col-span-2 space-y-4">
          <Card>
            <CardBody>
              <audio
                ref={audioRef}
                src={`${API_BASE}/calls/${id}/audio`}
                controls
                className="w-full"
                onTimeUpdate={(e) => setNow(e.currentTarget.currentTime)}
                onLoadedMetadata={() => {
                  if (seekParam > 0 && !seeked.current) {
                    seeked.current = true;
                    seek(seekParam);
                  }
                }}
              />
              <p className="mt-2 text-xs text-muted">
                Click any flag or timestamp to jump the audio to that moment.
              </p>
            </CardBody>
          </Card>

          <Card>
            <CardBody>
              <SectionTitle>Transcript</SectionTitle>
              {segments.length === 0 && (
                <Empty>
                  {processing
                    ? "Transcribing with faster-whisper… this panel fills in as soon as the transcript lands."
                    : "No transcript."}
                </Empty>
              )}
              <div className="scroll-thin max-h-[520px] space-y-1.5 overflow-y-auto pr-1">
                {segments.map((s) => {
                  const active = now >= s.start_s && now < s.end_s;
                  const advisor = s.speaker === "advisor";
                  return (
                    <div key={s.idx}>
                      <div
                        onClick={() => seek(s.start_s)}
                        className={`cursor-pointer rounded-lg border-l-2 px-3 py-2 transition ${
                          advisor ? "border-l-brand bg-brand-soft/50" : "border-l-gray-300 bg-gray-50"
                        } ${active ? "ring-2 ring-brand/40" : ""}`}
                      >
                        <div className="flex items-center justify-between">
                          <span className={`text-[11px] font-semibold uppercase ${advisor ? "text-brand" : "text-muted"}`}>
                            {s.speaker}
                          </span>
                          <span className="text-[11px] text-muted">{mmss(s.start_s)}</span>
                        </div>
                        <p className="text-sm text-ink">{s.text}</p>
                      </div>
                      {flagsBySeg[s.idx]?.map((f) => (
                        <div
                          key={f.id}
                          className={`ml-4 mt-1 rounded-md border px-2 py-1 text-xs ${severityStyle[f.severity]}`}
                        >
                          🚩 <b>{prettyTag(f.tag)}</b> — {f.reason}
                        </div>
                      ))}
                    </div>
                  );
                })}
              </div>
            </CardBody>
          </Card>
        </div>

        {/* Scores + flags */}
        <div className="space-y-4">
          <Card>
            <CardBody>
              <SectionTitle>Rubric scores</SectionTitle>
              <ul className="space-y-3">
                {scores.map((sc) => (
                  <li key={sc.dimension}>
                    <div className="flex items-center justify-between text-sm">
                      <span>{DIM_LABEL[sc.dimension] ?? sc.dimension}</span>
                      <span className="font-semibold">{sc.raw_score}/5</span>
                    </div>
                    <div className="mt-1 h-1.5 w-full rounded-full bg-gray-100">
                      <div className="h-1.5 rounded-full bg-brand" style={{ width: `${(sc.raw_score / 5) * 100}%` }} />
                    </div>
                    {sc.evidence_quote && (
                      <button
                        onClick={() => sc.evidence_start_s != null && seek(sc.evidence_start_s)}
                        className="mt-1 text-left text-[11px] text-muted hover:text-brand"
                      >
                        “{sc.evidence_quote}”
                      </button>
                    )}
                  </li>
                ))}
              </ul>
              {scores[0]?.prompt_hash && (
                <p className="mt-3 text-[10px] text-muted">
                  {call.rubric_version} · {scores[0].model} · prompt {scores[0].prompt_hash.slice(0, 8)}
                </p>
              )}
            </CardBody>
          </Card>

          <Card>
            <CardBody>
              <SectionTitle right={<span className="text-xs text-muted">{flags.length}</span>}>Flags</SectionTitle>
              {flags.length === 0 ? (
                <Empty>No flags 🎉</Empty>
              ) : (
                <ul className="space-y-2.5">
                  {flags.map((f) => (
                    <li key={f.id} className={`rounded-lg border p-2.5 ${severityStyle[f.severity]}`}>
                      <div className="flex items-center justify-between">
                        <span className="text-sm font-semibold">{prettyTag(f.tag)}</span>
                        <Badge className={stateStyle[f.state]}>{f.state}</Badge>
                      </div>
                      {f.quote && <p className="mt-1 text-xs">“{f.quote}”</p>}
                      <div className="mt-1.5 flex items-center gap-2 text-[11px] text-muted">
                        {f.start_s != null && (
                          <button onClick={() => seek(f.start_s!)} className="font-medium text-brand hover:underline">
                            ▶ {mmss(f.start_s)}
                          </button>
                        )}
                        {f.confidence != null && <span>conf {f.confidence.toFixed(2)}</span>}
                        {f.state === "open" && (
                          <button onClick={() => setDisputing(f.id)} className="ml-auto font-medium text-ink hover:text-brand">
                            Dispute
                          </button>
                        )}
                      </div>
                      {disputing === f.id && (
                        <div className="mt-2 space-y-1.5">
                          <textarea
                            value={note}
                            onChange={(e) => setNote(e.target.value)}
                            placeholder="Why is this flag wrong?"
                            className="w-full rounded-md border border-border p-1.5 text-xs"
                            rows={2}
                          />
                          <div className="flex gap-2">
                            <Button size="sm" disabled={busy} onClick={() => submitDispute(f.id)}>Submit dispute</Button>
                            <Button size="sm" variant="ghost" onClick={() => setDisputing(null)}>Cancel</Button>
                          </div>
                        </div>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </CardBody>
          </Card>
        </div>
      </div>
    </div>
  );
}

export default function CallPage({ params }: { params: { id: string } }) {
  return (
    <Suspense fallback={<Skeleton className="h-96" />}>
      <CallInner id={Number(params.id)} />
    </Suspense>
  );
}
