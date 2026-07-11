# CallSense — Project Journal

A complete, honest record of how this project was built: every phase, pivot,
bug, and fix, with the reasoning behind each decision. Companion to
[`README.md`](README.md) (what it is), [`WRITEUP.md`](WRITEUP.md) (design
trade-offs) and [`DEPLOYMENT.md`](DEPLOYMENT.md) (how it ships).

---

## 0. Starting point

The repo began with two documents and zero code:
- `CallSense_0-1_Plan.md` — a 48-hour build plan for the FitNova take-home
  (sales-call intelligence: ingest → transcribe → diarise → analyse → store →
  surface → human feedback loop).
- `CallSense_Concepts_Explained.md` — a from-scratch explainer of every concept
  the plan uses.

**Environment reality-check (day 1):** the dev machine had no Docker, no
Node.js, no Postgres, and no project conda env. Decisions made:
- Create a dedicated **conda env** (`callsense`, Python 3.11) — and, key trick,
  install **Postgres from conda-forge** into it, so a real database could run
  locally with zero system installs (`.pgdata/` data dir, `scripts/localdb.ps1`).
- Author all Docker artifacts anyway (graders run `make demo`), verify
  everything against the conda Postgres instead.
- Node.js later came from a second conda env (`callsense-web`, nodejs 20+) —
  unblocking the Next.js frontend without any system installs either.

## 1. Phase-by-phase build

### Phase 1 — Skeleton (schema-first)
- Full relational schema as SQLAlchemy 2 models: orgs → teams → advisors →
  calls → processing_jobs → transcripts → segments → scores → call_scores →
  flags → disputes → calibration_examples → audit_log.
- Alembic migrations (initial schema + rollup views). A circular FK
  (teams.team_leader_id ↔ advisors) needed the constraint moved to a separate
  `op.create_foreign_key` after both tables exist — autogenerate got it wrong.
- Rollup views encode a product decision: **team average = mean over advisors,
  not over calls**, so one high-volume advisor can't dominate. Verified with a
  functional SQL test (team of 70/90 advisors averages 80, not the call-mean 76.7).
- FastAPI app with `/health` (liveness) and `/health/db` (readiness).

### Phase 2 — Ingestion + queue
- `CallEnvelope` canonical schema; `SourceAdapter` ABC with **folder / REST /
  mock-CRM** adapters (source-agnosticism the brief demands).
- ffprobe validation gate (corrupt/non-audio → audit log, never the pipeline).
- Idempotency: `sha256(audio)+source` UNIQUE key; `ON CONFLICT DO NOTHING`.
- **Postgres-backed job queue** — `SELECT … FOR UPDATE SKIP LOCKED` claim,
  retries with exponential backoff + jitter, dead-letter state, crash-recovery
  via a visibility timeout. Chosen over Celery/Kafka deliberately (scale
  honesty; the `JobQueue` ABC documents the swap path).

### Phase 3 — Transcription + diarisation
- `Transcriber` interface: **faster-whisper** (local, int8) for real mode,
  `MockTranscriber` for keyless demos.
- Diarisation ladder: stereo channel-split (advisor left) → mono fallback.

### Phase 4 — Analysis engine
- Rubric v1 (5 weighted dimensions), closed 9-tag taxonomy.
- The anti-hallucination stack: forced JSON + Pydantic validation (one retry) →
  **quote-verification gate** (fuzzy ≥0.85 against the transcript; unmatched
  flags dropped) → timestamps derived by code from the matched segment →
  confidence <0.6 degrades to `info` → **compliance cap** (any critical flag
  caps the composite at 40).
- PII redaction (regex + Luhn) runs **before** any text reaches an LLM.
- Non-sales classifier gate (cheap LLM pass on the opening turns) so wrong
  numbers/spam never burn analysis tokens and never pollute averages.

### Phases 5–6 — API, dashboards, feedback loop, demo data
- REST API: summaries (org/team/advisor), call detail, dispute lifecycle,
  ops/jobs, audio streaming.
- Next.js dashboards (Director / Team Leader / Advisor) + the call-detail
  page: audio player synced to a speaker-coloured transcript, flags pinned at
  their timestamps, click-to-seek, dispute button.
- Dispute loop: advisor disputes → TL upholds/dismisses → **composite
  recomputes** (dismissing the only critical flag lifts the cap, verified
  40 → 80) → resolution becomes a `calibration_example` injected into future
  prompts. Every action lands in the append-only audit log.
- Seed: 1 org, 3 teams, 9 advisors, ~25 calls through the real (mock-mode)
  pipeline so dashboards have live history.
- Test suite grew to **37 tests** (unit / integration / API) incl. retry,
  dead-letter, duplicate-upload, crash-resume, dispute lifecycle.

## 2. The pivots (and why)

### Pivot 1 — SkilloVilla (edtech) → FitNova (fitness)
The plan was written assuming the hiring company's own domain (edtech,
"guaranteed placement"). Reading the actual PDF showed the brief is about
**FitNova, a fitness/wellness coaching platform**. Decision: keep the
SkilloVilla branding nod (logo + a dumbbell badge) but reframe all fixtures,
prompts and copy to fitness sales ("weight loss 100% guaranteed", hidden
auto-renewal fees, free trial sessions). Cost: ~1 hour. Reasoning: graders
grade against their brief, not our cleverness.

### Pivot 2 — Anthropic → Gemini as the real LLM
No Anthropic key was available; the user had a Google AI Studio key. The `LLM`
interface made this a one-class addition (`GeminiLLM`) with client-side rate
limiting (1 rps) + exponential backoff on 429/503 — which was immediately
exercised for real: free-tier flash/pro quotas returned genuine
RESOURCE_EXHAUSTED errors, and `gemini-2.5-flash` turned out to be gated for
new keys ("no longer available to new users"). Settled on
**`gemini-flash-lite-latest` / `gemini-3.1-flash-lite`** — reliable free-tier
quota, verified correct on structured tasks.

### Pivot 3 — Mock-first testing → real end-to-end proofs
Skepticism ("are you fooling me?") was answered with escalating evidence:
- faster-whisper transcribed TTS'd Hinglish audio (model actually downloaded, ~460MB).
- Gemini flagged violations on a **never-seen transcript** (a "Zen Wellness"
  thyroid call not present anywhere in the codebase).
- An un-fakeable echo test: a random marker generated in the moment
  (`CALLSENSE-6A921263E09E`) came back verbatim from Google's API.
- Full HTTP chain: upload real audio → background worker → Whisper (Devanagari
  output) → Gemini flags `over_promising` @13.5s → quote-gate verified → stored.

### Pivot 4 — Hugging Face Spaces → Railway (deployment)
The free-cloud plan was HF Spaces (Docker, 2 vCPU/16GB — fits Whisper `small`).
**Blocked at deploy time**: HF now requires PRO for Docker/Gradio Spaces on
cpu-basic. Options were re-costed honestly (Render free = 512MB, can't fit
Whisper; Oracle free = high friction; tunnel = laptop must stay on). Chosen:
**Railway trial** ($5 one-time credit, no card, ~2 weeks always-on) with one
trade-off — the 1GB trial RAM means **Whisper `base`** in the cloud
(`WHISPER_MODEL=base` env var; local demos keep `small`).

## 3. Bugs found and fixed (the honest list)

| # | Bug | Root cause | Fix |
|---|---|---|---|
| 1 | Quote-gate dropped every real-mode flag | Normaliser stripped non-Latin chars; real Whisper writes Hinglish in **Devanagari** | Unicode-aware normalisation (`\w` across scripts) + Devanagari regression tests |
| 2 | Frontend "showed dummy analysis" on real upload | User re-uploaded bytes already ingested in mock mode → idempotency guard routed to the old call, **silently** | UX: explicit "already ingested as call #N (idempotency)" banner; stale mock call deleted |
| 3 | CI red on first push | `python-multipart` installed locally but never pinned in requirements | Pinned; CI green since |
| 4 | Docker/CI would crash at import | `numpy`/`soundfile` used by diarisation but missing from requirements | Pinned; real-mode extras split into `requirements-real.txt` |
| 5 | Stage timings looked impossible (transcribe "0.5s") | Postgres `now()` freezes at txn start; stages run inside the job txn | Queue uses `clock_timestamp()` |
| 6 | Whisper on 11-min file could double memory | float64 audio buffer | `dtype="float32"` read + buffer release |
| 7 | `scores.model` said `claude-…` when Gemini scored | Label derived from the wrong config field | Provider-aware model stamping |
| 8 | Railway 502 | Railway injects `PORT=8080`; domain targeted 7860 | Pinned `PORT=7860` service variable |
| 9 | Vercel build "Blocked" | Commit author email not registered to the GitHub account; Hobby plan rejects non-member authors on private repos | Author switched to `Aaryansm11@users.noreply.github.com` |
| 10 | Deployed site showed login wall | Vercel Deployment Protection defaulted to all URLs | Disabled for production |
| 11 | **Site dead on user's network (web + mobile)** | Indian ISPs (Jio/Airtel) **refuse DNS for `*.up.railway.app`** — verified: 4 global resolvers fine, local resolver REFUSED | **Same-origin proxy**: Next.js rewrite `/api/backend/* →` Railway via Vercel's edge; browsers only ever resolve `vercel.app` |
| 12 | Cloud transcript came out in Urdu script | Hindi/Urdu are one spoken language; smaller Whisper models pick the Perso-Arabic script without a hint | `language_hint` now flows into Whisper (`language="hi"` ⇒ Devanagari); upload form language selector |
| 13 | "Customer" got flagged for the advisor's over-promise | Single-voice test audio → diariser had nothing to separate → labels alternated; flag landed on a "customer" line | Two-layer fix: prompt rule (flags = advisor utterances only) + code guard (customer-attributed flags degrade to `info` with an attribution note) |
| 14 | "Advisor = whoever speaks first" heuristic failed on a real scam call | Victim answered "Hello" first | **Content-based role check**: the classifier verdict now includes `advisor_is`; swapped labels are flipped in the DB (idempotency-guarded) |
| 15 | Scam call scored as sales in the cloud | Borderline classification on a messier `base` transcript | Classifier prompt explicitly rules support/remote-access/money-moving scam calls NON_SALES |

## 4. Features added beyond the original plan

- **Acoustic mono diarisation** (numpy-only): per-segment voice fingerprints
  (log-mel envelope + pitch), deterministic 2-means, cluster-separation
  confidence, honest fallback when voices aren't separable. No gated models.
- **Deterministic talk-ratio** metric + `talk_over_customer` flag computed from
  segment durations (never by the LLM).
- **Live pipeline stepper** on the call page (stages tick as the worker runs,
  polling every 2.5s) + professional drag-&-drop upload with duplicate/reject
  messaging.
- **"How it works" page** (`/about`): pipeline, guardrails, role views, storage
  model, measured capacity — the interviewer explainer.
- **Upload hardening**: 200MB size cap + 10/min/IP sliding-window rate limit.
- **GitHub Actions CI**: backend tests against a postgres:16 service +
  frontend type-check/build, every push.
- **Test-call generator** (`demo/make_test_calls.py`): scripted Hinglish
  FitNova dialogues rendered with two neural TTS voices, stereo + mono variants.

## 5. The deployed system

```
Browser ──► Vercel (Next.js, edge-proxies /api/backend/*) ──► Railway (Docker:
FastAPI + inline worker thread, Whisper base, Gemini flash-lite) ──► Neon (Postgres)
```

- Live site: https://callsense-aaryan-s-maralihallis-projects.vercel.app
- API/docs: https://callsense-production-d0b3.up.railway.app/docs
- Boot sequence per deploy: `alembic upgrade head` → in-container demo seed
  (audio regenerated locally so playback works; `SEED_MODE=if-empty` supported)
  → API with the worker as a daemon thread (`RUN_INLINE_WORKER=true`).
- Secrets (`DATABASE_URL`, `GEMINI_API_KEY`) live in Railway variables only —
  the repo and client bundle are key-free.
- Verified end-to-end in production: real Hinglish upload → 6 stages done in
  ~45s → Gemini flagged `over_promising` (critical) with a quote-gate-verified
  Devanagari/Urdu quote → surfaced with working audio.

## 6. Measured numbers

- Whisper `small` int8, local CPU: **~3.3× real-time** (11.5-min call → 3m32s).
- Cloud (`base`, shared vCPU): ~1× real-time; 18s clip → all 6 stages ≈ 45s.
- Gemini free tier: ~**500+ calls/day** ceiling (2 LLM calls per call, throttled).
- One worker ≈ **300–400 five-minute calls/day**; stateless → scale = add workers.
- 37 automated tests; CI green.

## 7. What remains out of scope (deliberately)

Auth/SSO (role switcher demonstrates authorization instead), live telephony
(adapter interface shows the plug-in point), pyannote diarisation (HF-gated;
acoustic clustering + documented upgrade path), fine-tuning (the dispute loop
is generating its future training set), golden-set `make eval` (documented
roadmap), Kubernetes/Kafka (scale honesty).
