"use client";

import { CheckCircle2, FileAudio, Loader2, UploadCloud, X } from "lucide-react";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, uploadCall } from "@/lib/api";
import { Button } from "./ui";

// Mock-mode fixtures the canned analysis maps to (drives the demo result).
// Irrelevant in real mode, where the actual audio is transcribed and judged.
const FIXTURES = [
  { value: "over_promiser", label: "Over-promiser (guaranteed weight loss)" },
  { value: "good_discovery", label: "Great discovery call" },
  { value: "pushy_pressure", label: "Pushy / pressure tactics" },
  { value: "hidden_costs", label: "Hidden costs (registration / auto-renewal)" },
  { value: "non_sales", label: "Non-sales (wrong number)" },
];

function prettySize(bytes: number): string {
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export function UploadCall() {
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [fixture, setFixture] = useState("over_promiser");
  const [language, setLanguage] = useState("hi");
  const [advisors, setAdvisors] = useState<
    { id: number; name: string; team_name: string; external_id: string }[]
  >([]);
  const [advisorExtId, setAdvisorExtId] = useState("AGT-1");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ kind: "info" | "warn" | "error"; text: string } | null>(null);
  // null = unknown (loading); true = canned fixtures; false = real Whisper+LLM
  const [mockMode, setMockMode] = useState<boolean | null>(null);

  useEffect(() => {
    api
      .get<{ mock_mode: boolean }>("/")
      .then((meta) => setMockMode(meta.mock_mode))
      .catch(() => setMockMode(null));
    // The advisor directory drives the picker so uploads aren't hardcoded to
    // one advisor. Falls back to AGT-1 if the endpoint isn't reachable yet.
    api
      .get<typeof advisors>("/advisors")
      .then((list) => {
        if (list?.length) {
          setAdvisors(list);
          setAdvisorExtId(list[0].external_id);
        }
      })
      .catch(() => {});
  }, []);

  const pick = useCallback((f: File | undefined | null) => {
    if (!f) return;
    if (!f.type.startsWith("audio/") && !/\.(wav|mp3|m4a|flac|ogg|opus)$/i.test(f.name)) {
      setMsg({ kind: "error", text: "That doesn't look like an audio file." });
      return;
    }
    setFile(f);
    setMsg(null);
  }, []);

  async function submit() {
    if (!file) {
      setMsg({ kind: "warn", text: "Choose an audio file first." });
      return;
    }
    setBusy(true);
    setMsg({
      kind: "info",
      text: mockMode
        ? "Running the pipeline on canned analysis…"
        : "Uploading — you'll land on the call page and watch each stage run live.",
    });
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("advisor_external_id", advisorExtId);
      if (language) form.append("language_hint", language);
      if (mockMode) {
        form.append("fixture", fixture);
        form.append("process", "true"); // instant with mocks
      }
      const res = await uploadCall(form);
      if (res.call_id && res.created === false) {
        setMsg({
          kind: "warn",
          text:
            `This exact audio was already ingested as call #${res.call_id} — the ` +
            `idempotency guard never processes the same bytes twice. Opening the ` +
            `existing call…`,
        });
        setTimeout(() => router.push(`/calls/${res.call_id}`), 3000);
      } else if (res.call_id) {
        router.push(`/calls/${res.call_id}`);
      } else if (res.accepted === false) {
        setMsg({ kind: "error", text: `Rejected: ${res.reason ?? "invalid audio"}` });
        setBusy(false);
      }
    } catch (e) {
      setMsg({ kind: "error", text: `Upload failed: ${e}` });
      setBusy(false);
    }
  }

  return (
    <div className="space-y-3">
      {/* Mode banner */}
      {mockMode === false ? (
        <div className="flex items-start gap-2 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs leading-relaxed text-emerald-800">
          <CheckCircle2 size={14} className="mt-0.5 shrink-0" />
          <span>
            <b>Real analysis mode.</b> Your audio is transcribed locally by
            faster-whisper and judged by Gemini. Expect 1–3 minutes; the call
            page shows every pipeline stage live.
          </span>
        </div>
      ) : mockMode === true ? (
        <div className="rounded-lg border border-border bg-gray-50 px-3 py-2 text-xs text-muted">
          <b>Demo mode.</b> Any audio runs the full loop with the canned scenario
          you pick below — no API keys needed.
        </div>
      ) : null}

      {/* Dropzone */}
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragOver(false);
          pick(e.dataTransfer.files?.[0]);
        }}
        onClick={() => inputRef.current?.click()}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => e.key === "Enter" && inputRef.current?.click()}
        className={`flex cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed px-4 py-7 text-center transition ${
          dragOver
            ? "border-brand bg-brand-soft"
            : "border-border bg-gray-50/60 hover:border-brand/60 hover:bg-brand-soft/40"
        }`}
      >
        <span className="flex h-10 w-10 items-center justify-center rounded-full bg-brand-soft text-brand">
          <UploadCloud size={20} />
        </span>
        <p className="text-sm font-medium text-ink">
          Drag &amp; drop a call recording
        </p>
        <p className="text-xs text-muted">WAV, MP3, M4A, FLAC, OGG · or</p>
        <Button
          size="sm"
          variant="ghost"
          onClick={() => inputRef.current?.click()}
        >
          Browse files
        </Button>
        <input
          ref={inputRef}
          type="file"
          accept="audio/*,.wav,.mp3,.m4a,.flac,.ogg,.opus"
          className="hidden"
          onChange={(e) => pick(e.target.files?.[0])}
        />
      </div>

      {/* Selected file chip */}
      {file && (
        <div className="flex items-center gap-2 rounded-lg border border-border bg-white px-3 py-2">
          <FileAudio size={16} className="shrink-0 text-brand" />
          <span className="min-w-0 flex-1 truncate text-sm font-medium">{file.name}</span>
          <span className="shrink-0 text-xs text-muted">{prettySize(file.size)}</span>
          <button
            onClick={() => {
              setFile(null);
              if (inputRef.current) inputRef.current.value = "";
            }}
            className="shrink-0 rounded p-0.5 text-muted hover:bg-gray-100 hover:text-ink"
            aria-label="Remove file"
          >
            <X size={14} />
          </button>
        </div>
      )}

      {/* Advisor attribution — in production this comes from the source
          payload's agent ref; here the user picks so it isn't hardcoded. */}
      {advisors.length > 0 && (
        <label className="block text-xs text-muted">
          Attribute to advisor
          <select
            value={advisorExtId}
            onChange={(e) => setAdvisorExtId(e.target.value)}
            className="mt-1 w-full rounded-lg border border-border bg-white px-2.5 py-2 text-xs text-ink"
          >
            {advisors.map((a) => (
              <option key={a.id} value={a.external_id}>
                {a.name} · {a.team_name} ({a.external_id})
              </option>
            ))}
          </select>
        </label>
      )}

      {/* Language hint: keeps Whisper's Hindi output in Devanagari and biases
          decoding; "auto" lets the model guess (may drift scripts). */}
      {mockMode === false && (
        <label className="block text-xs text-muted">
          Call language
          <select
            value={language}
            onChange={(e) => setLanguage(e.target.value)}
            className="mt-1 w-full rounded-lg border border-border bg-white px-2.5 py-2 text-xs text-ink"
          >
            <option value="hi">Hinglish / Hindi (recommended)</option>
            <option value="en">English</option>
            <option value="">Auto-detect</option>
          </select>
        </label>
      )}

      {/* Scenario picker (mock mode only) */}
      {mockMode !== false && (
        <label className="block text-xs text-muted">
          Demo scenario
          <select
            value={fixture}
            onChange={(e) => setFixture(e.target.value)}
            className="mt-1 w-full rounded-lg border border-border bg-white px-2.5 py-2 text-xs text-ink"
          >
            {FIXTURES.map((f) => (
              <option key={f.value} value={f.value}>
                {f.label}
              </option>
            ))}
          </select>
        </label>
      )}

      <Button onClick={submit} disabled={busy || !file} className="w-full">
        {busy ? (
          <>
            <Loader2 size={15} className="animate-spin" /> Processing…
          </>
        ) : (
          "Ingest & analyse call"
        )}
      </Button>

      {msg && (
        <p
          className={`text-xs leading-relaxed ${
            msg.kind === "error"
              ? "text-crit"
              : msg.kind === "warn"
                ? "text-warn"
                : "text-muted"
          }`}
        >
          {msg.text}
        </p>
      )}
    </div>
  );
}
