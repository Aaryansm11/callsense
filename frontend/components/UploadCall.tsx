"use client";

import { useRouter } from "next/navigation";
import { useRef, useState } from "react";
import { uploadCall } from "@/lib/api";
import { Button } from "./ui";

// Mock-mode fixtures the canned analysis maps to (drives the demo result).
const FIXTURES = [
  { value: "over_promiser", label: "Over-promiser (guaranteed placement)" },
  { value: "good_discovery", label: "Great discovery call" },
  { value: "pushy_pressure", label: "Pushy / pressure tactics" },
  { value: "hidden_costs", label: "Hidden costs" },
  { value: "non_sales", label: "Non-sales (wrong number)" },
];

export function UploadCall() {
  const router = useRouter();
  const fileRef = useRef<HTMLInputElement>(null);
  const [fixture, setFixture] = useState("over_promiser");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  async function submit() {
    const file = fileRef.current?.files?.[0];
    if (!file) {
      setMsg("Choose an audio file first.");
      return;
    }
    setBusy(true);
    setMsg("Ingesting → transcribe → diarise → redact → classify → analyse …");
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("advisor_external_id", "AGT-1");
      form.append("fixture", fixture);
      form.append("process", "true"); // drain the pipeline inline for the demo
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
      <p className="text-xs text-muted">
        Drop any audio file — in MOCK_MODE the analysis follows the chosen scenario
        so the full loop runs with no API key.
      </p>
      <input
        ref={fileRef}
        type="file"
        accept="audio/*"
        className="block w-full text-xs file:mr-3 file:rounded-md file:border-0 file:bg-brand-soft file:px-3 file:py-1.5 file:text-xs file:font-medium file:text-brand"
      />
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
      <Button onClick={submit} disabled={busy}>
        {busy ? "Processing…" : "Ingest & analyse"}
      </Button>
      {msg && <p className="text-xs text-muted">{msg}</p>}
    </div>
  );
}
