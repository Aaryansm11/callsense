import {
  AudioLines,
  BarChart3,
  Database,
  EyeOff,
  FileAudio,
  Gauge,
  GitBranch,
  Languages,
  MessageSquareWarning,
  Quote,
  RefreshCcw,
  Scale,
  ShieldCheck,
  Users,
} from "lucide-react";
import { Card, CardBody } from "@/components/ui";

export const metadata = { title: "How it works · CallSense" };

const PIPELINE = [
  {
    icon: FileAudio,
    name: "1 · Ingest",
    body:
      "Recordings arrive from any source — a watched folder, this dashboard's REST upload, or a CRM/dialer adapter — and are normalised into one canonical envelope. ffprobe rejects non-audio; a sha256 idempotency key means the same recording can never be processed twice.",
  },
  {
    icon: AudioLines,
    name: "2 · Transcribe",
    body:
      "faster-whisper runs locally (no per-minute vendor cost, Hinglish-capable) and produces text with second-level timestamps. Every downstream claim anchors back to these timestamps.",
  },
  {
    icon: Users,
    name: "3 · Diarise",
    body:
      "Who spoke when. True channel-separated stereo splits by channel (zero ML) — and the result is sanity-checked: if one 'speaker' swallows everything, the file is treated as mixed stereo and falls through to voice clustering (spectral envelope + pitch fingerprints, two clusters). Who is the advisor is decided by CONTENT — the classifier reads the opening and flips the labels if they're backwards. If voices aren't separable the page says so instead of pretending.",
  },
  {
    icon: EyeOff,
    name: "4 · Redact",
    body:
      "Phones, card numbers (Luhn-checked), OTPs, Aadhaar, emails and PANs are masked BEFORE any text reaches an external LLM. The privacy boundary is architectural, not a policy note.",
  },
  {
    icon: GitBranch,
    name: "5 · Classify",
    body:
      "A cheap LLM pass answers two questions from the opening turns: is this actually a sales conversation (wrong numbers, support calls and remote-access/money-moving scams are ruled non-sales — tagged, excluded from every average, and never burn analysis tokens), and do the speaker labels match the content (swapped labels get flipped here).",
  },
  {
    icon: Scale,
    name: "6 · Analyse",
    body:
      "The LLM scores five rubric dimensions (discovery, product knowledge, objection handling, compliance, next-step booking) and raises issue flags — but only inside a closed taxonomy, only with verbatim quotes, and only for ADVISOR utterances (a violating line attributed to the customer is downgraded to info for review). Talk-ratio is computed by code from segment durations, never by the model.",
  },
  {
    icon: ShieldCheck,
    name: "7 · Validate & store",
    body:
      "Schema-validated output lands in Postgres: scores, flags, composite (with the compliance cap), all stamped with rubric version + prompt hash so results stay comparable and drift is detectable.",
  },
];

const GUARDRAILS = [
  {
    icon: Quote,
    title: "Quote-or-it-didn't-happen",
    body:
      "Every flag must cite a verbatim quote. Code fuzzy-matches it against the actual transcript (Unicode-aware — works on Devanagari); no match → the flag is dropped and logged. Timestamps are derived from the matched segment, because LLMs are bad at arithmetic.",
  },
  {
    icon: MessageSquareWarning,
    title: "Compliance cap",
    body:
      "One critical compliance flag (guaranteed results, hidden costs, pressure) caps the call score at 40 — charm can't average away mis-selling. The dispute loop is the safety valve for false positives.",
  },
  {
    icon: RefreshCcw,
    title: "Human feedback loop",
    body:
      "Advisors dispute flags; Team Leaders uphold or dismiss with a note. A dismissal recomputes the score (the cap lifts) and mints a calibration example that is injected into future prompts — the system provably learns from its corrections. Every action lands in an append-only audit log.",
  },
  {
    icon: Gauge,
    title: "Reliability engineering",
    body:
      "A Postgres-backed job queue (SELECT … FOR UPDATE SKIP LOCKED) drives six idempotent stages with retries, exponential backoff + jitter, dead-lettering and crash-resume. Kill a worker mid-job and the call still completes — with no duplicate rows.",
  },
  {
    icon: Languages,
    title: "Hinglish-native",
    body:
      "Whisper handles Hindi-English code-switching; quotes stay verbatim in the original script; a code-switch ratio is stored per transcript so heavily mixed calls can be monitored.",
  },
  {
    icon: Database,
    title: "Source-agnostic by design",
    body:
      "New telephony/CRM vendors plug in as one adapter file mapping their payload to the canonical envelope — zero pipeline changes. Raw vendor payloads are preserved in JSONB for later re-mapping.",
  },
];

const ROLES = [
  {
    name: "Sales Director",
    view: "Org health",
    sees: [
      "Org-wide average score and trend line",
      "Team-vs-team comparison",
      "KPI cards: calls processed, critical flags, open disputes",
      "Risk feed: latest critical flags, each linking to the exact second of audio",
    ],
  },
  {
    name: "Team Leader",
    view: "Coaching",
    sees: [
      "Advisor leaderboard (score, volume, critical flags)",
      "Per-dimension heatmap — what to coach, not just who",
      "Dispute inbox: listen at the flagged timestamp, uphold or dismiss",
    ],
  },
  {
    name: "Advisor",
    view: "My calls",
    sees: [
      "My scores and dimension radar vs team average",
      "Call detail: audio-synced transcript with flags pinned at their timestamps",
      "One-click dispute on any flag I believe is unfair",
    ],
  },
];

export default function AboutPage() {
  return (
    <div className="mx-auto max-w-4xl space-y-10">
      {/* Hero */}
      <div className="space-y-3 pt-2 text-center">
        <h1 className="text-2xl font-semibold tracking-tight">
          How CallSense works
        </h1>
        <p className="mx-auto max-w-2xl text-sm leading-relaxed text-muted">
          FitNova's advisors make hundreds of sales calls; team leaders can
          manually review ~5%. CallSense listens to <b>100%</b>: every call is
          transcribed, speaker-separated, scored against a five-dimension rubric,
          and checked for mis-selling — with evidence, timestamps, and a human
          appeal process. Same-day coaching instead of complaint-day surprises.
        </p>
      </div>

      {/* Pipeline */}
      <section>
        <h2 className="mb-4 text-sm font-semibold uppercase tracking-wide text-muted">
          The pipeline — from raw audio to reviewed insight
        </h2>
        <div className="space-y-3">
          {PIPELINE.map((step) => (
            <Card key={step.name}>
              <CardBody className="flex gap-4 py-4">
                <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-brand-soft text-brand">
                  <step.icon size={19} />
                </span>
                <div>
                  <h3 className="text-sm font-semibold">{step.name}</h3>
                  <p className="mt-1 text-sm leading-relaxed text-muted">{step.body}</p>
                </div>
              </CardBody>
            </Card>
          ))}
        </div>
      </section>

      {/* Guardrails */}
      <section>
        <h2 className="mb-4 text-sm font-semibold uppercase tracking-wide text-muted">
          Why the numbers can be trusted
        </h2>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {GUARDRAILS.map((g) => (
            <Card key={g.title}>
              <CardBody className="py-4">
                <div className="flex items-center gap-2">
                  <g.icon size={16} className="text-brand" />
                  <h3 className="text-sm font-semibold">{g.title}</h3>
                </div>
                <p className="mt-1.5 text-[13px] leading-relaxed text-muted">{g.body}</p>
              </CardBody>
            </Card>
          ))}
        </div>
      </section>

      {/* Roles */}
      <section>
        <h2 className="mb-4 text-sm font-semibold uppercase tracking-wide text-muted">
          One system, three audiences
        </h2>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
          {ROLES.map((r) => (
            <Card key={r.name}>
              <CardBody className="py-4">
                <h3 className="text-sm font-semibold">{r.name}</h3>
                <p className="text-xs font-medium text-brand">{r.view} view</p>
                <ul className="mt-2 space-y-1.5 text-[13px] leading-snug text-muted">
                  {r.sees.map((s) => (
                    <li key={s} className="flex gap-1.5">
                      <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-brand" />
                      {s}
                    </li>
                  ))}
                </ul>
              </CardBody>
            </Card>
          ))}
        </div>
        <p className="mt-2 text-xs text-muted">
          Authentication is out of scope for this prototype — the role switcher in
          the header demonstrates the authorization model without the SSO plumbing.
        </p>
      </section>

      {/* Data & storage */}
      <section>
        <h2 className="mb-4 text-sm font-semibold uppercase tracking-wide text-muted">
          Where everything lives
        </h2>
        <Card>
          <CardBody className="space-y-3 py-4 text-sm leading-relaxed text-muted">
            <p>
              <b className="text-ink">Postgres is the single source of truth.</b>{" "}
              A fully relational model — orgs → teams → advisors → calls →
              transcripts → segments → scores → flags → disputes →
              calibration examples → audit log — plus the job queue itself, so
              processing state is transactional with the data it produces. Org,
              team and advisor averages are SQL views computed live from call
              scores (team average = mean over advisors, so one high-volume
              advisor can't dominate).
            </p>
            <p>
              <b className="text-ink">Audio files</b> stay on disk/object
              storage; the database stores their URI, duration and channel
              layout. <b className="text-ink">Raw transcripts</b> live in a
              restricted column; everything downstream — including the LLM —
              sees only the redacted text.
            </p>
            <p>
              <b className="text-ink">What leaves the system:</b> only the
              PII-redacted transcript text, sent to the LLM API for scoring.
              Transcription is local. In demo (mock) mode, nothing leaves at all.
            </p>
            <p>
              <b className="text-ink">What persists:</b> every database row —
              calls, transcripts, scores, flags, disputes, and the calibration
              examples the dispute loop generates — lives in managed Postgres
              and survives every deploy. The hosted server&apos;s disk is
              ephemeral: demo-call audio is regenerated on boot (it&apos;s
              synthesized), while audio of user uploads from previous server
              lives keeps its data but loses playback — durable object storage
              (S3) is the documented production answer.
            </p>
          </CardBody>
        </Card>
      </section>

      {/* Capacity */}
      <section>
        <h2 className="mb-4 text-sm font-semibold uppercase tracking-wide text-muted">
          Measured capacity (single CPU worker, free-tier LLM)
        </h2>
        <Card>
          <CardBody className="py-4">
            <div className="grid grid-cols-1 gap-4 text-sm sm:grid-cols-3">
              <div>
                <p className="text-2xl font-semibold text-ink">~3.3×</p>
                <p className="text-xs leading-snug text-muted">
                  faster than real-time transcription (Whisper small/int8 on CPU
                  — an 11.5-min call processed in 3m32s, measured)
                </p>
              </div>
              <div>
                <p className="text-2xl font-semibold text-ink">~300–400</p>
                <p className="text-xs leading-snug text-muted">
                  five-minute calls per day per worker, CPU-bound by Whisper;
                  workers are stateless so capacity scales by adding workers
                </p>
              </div>
              <div>
                <p className="text-2xl font-semibold text-ink">2 LLM calls</p>
                <p className="text-xs leading-snug text-muted">
                  per analysed call (classify + analyse), throttled client-side
                  with backoff — free-tier Gemini sustains roughly 500+ calls/day
                </p>
              </div>
            </div>
            <p className="mt-3 text-xs text-muted">
              First bottleneck at 10× scale: Whisper on CPU. Fix order: GPU
              worker pool → managed STT for overflow → materialise the rollup
              views. Nothing in the schema changes.
            </p>
            <p className="mt-2 text-xs text-muted">
              Upload limits: ~4.5 MB per file on this hosted demo (uploads ride
              the site&apos;s edge proxy) · 200 MB when talking to the API
              directly · 10 uploads/min per IP. The hosted transcriber runs
              Whisper <i>base</i> (free-tier RAM); local runs <i>small</i> —
              one env var apart.
            </p>
          </CardBody>
        </Card>
      </section>

      <section className="pb-6">
        <h2 className="mb-4 text-sm font-semibold uppercase tracking-wide text-muted">
          Demo vs real mode
        </h2>
        <Card>
          <CardBody className="py-4 text-sm leading-relaxed text-muted">
            <p>
              With <code className="rounded bg-gray-100 px-1 py-0.5 text-xs">MOCK_MODE=true</code>{" "}
              the entire loop — ingestion, queue, redaction, storage, dashboards,
              disputes — runs on canned transcripts and analyses, so the system
              works with zero API keys. Flip it off and the same pipeline runs
              faster-whisper locally and a real LLM (Gemini or Anthropic behind
              one interface) on your actual audio. The only things that change
              are the two model calls; every guardrail stays identical.
            </p>
          </CardBody>
        </Card>
      </section>
    </div>
  );
}
