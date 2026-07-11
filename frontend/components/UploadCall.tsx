"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
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

export function UploadCall() {
  const router = useRouter();
  const fileRef = useRef<HTMLInputElement>(null);
  const [fixture, setFixture] = useState("over_promiser");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  // null = unknown (loading); true = canned fixtures; false = real Whisper+LLM
  const [mockMode, setMockMode] = useState<boolean | null>(null);

  useEffect(() => {
    api
      .get<{ mock_mode: boolean }>("/")
      .then((meta) => setMockMode(meta.mock_mode))
      .catch(() => setMockMode(null));
  }, []);

  async function submit() {
    const file = fileRef.current?.files?.[0];
    if (!file) {
      setMsg("Choose an audio file first.");
      return;
    }
    setBusy(true);
    setMsg(
      mockMode
        ? "Ingesting → transcribe → diarise → redact → classify → analyse …"
        : "Uploading… you'll land on the call page and watch the pipeline run."
    );
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("advisor_external_id", "AGT-1");
      if (mockMode) {
        form.append("fixture", fixture);
        form.append("process", "true"); // instant with mocks
      }
      const res = await uploadCall(form);
      if (res.call_id) {
        router.push(`/calls/${res.call_id}`);
      } else {
        setMsg(`Result: ${JSON.stringify(res)}`);
      }
    } catch (e) {
      setMsg(`Upload failed: ${e}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-3">
      {mockMode === false ? (
        <div className="rounded-md border border-green-200 bg-green-50 px-2.5 py-1.5 text-xs text-green-800">
          <b>REAL mode</b> — your audio is transcribed by faster-whisper and
          judged by Gemini. Processing takes a minute or two; the call page
          shows each pipeline stage live.
        </div>
      ) : (
        <p className="text-xs text-muted">
          Drop any audio file — in MOCK_MODE the analysis follows the chosen
          scenario so the full loop runs with no API key.
        </p>
      )}
      <input
        ref={fileRef}
        type="file"
        accept="audio/*"
        className="block w-full text-xs file:mr-3 file:rounded-md file:border-0 file:bg-brand-soft file:px-3 file:py-1.5 file:text-xs file:font-medium file:text-brand"
      />
      {mockMode !== false && (
        <select
          value={fixture}
          onChange={(e) => setFixture(e.target.value)}
          className="w-full rounded-lg border border-border bg-white px-2.5 py-1.5 text-xs"
        >
          {FIXTURES.map((f) => (
            <option key={f.value} value={f.value}>
              {f.label}
            </option>
          ))}
        </select>
      )}
      <Button onClick={submit} disabled={busy}>
        {busy ? "Uploading…" : "Ingest & analyse"}
      </Button>
      {msg && <p className="text-xs text-muted">{msg}</p>}
    </div>
  );
}
