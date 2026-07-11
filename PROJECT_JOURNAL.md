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

---

## 8. Complete changelog — every commit, with rationale and files

### `402f364` — Initial end-to-end system
**Why:** the whole MVP loop built and verified locally before any polish
(the brief grades a working prototype above all).
**What:** schema + Alembic migrations ([backend/db/models.py](backend/db/models.py),
[backend/db/alembic/versions/](backend/db/alembic/versions/),
[backend/db/views.sql](backend/db/views.sql)); SKIP-LOCKED queue + worker
([backend/pipeline/queue.py](backend/pipeline/queue.py),
[backend/pipeline/worker.py](backend/pipeline/worker.py)); six stages
([backend/pipeline/stages/](backend/pipeline/stages/)); adapters + ffprobe gate +
idempotent ingest ([backend/ingestion/](backend/ingestion/)); Whisper/mock
transcribers + channel-split diarisation ([backend/transcription/](backend/transcription/));
rubric, quote gate, redaction, LLM interface
([backend/analysis/](backend/analysis/)); FastAPI routes
([backend/app/routes/](backend/app/routes/)); dispute→recompute→calibration
([backend/feedback.py](backend/feedback.py),
[backend/analysis/recompute.py](backend/analysis/recompute.py)); Next.js
dashboards ([frontend/app/](frontend/app/)); seed
([demo/seed.py](demo/seed.py)); compose/Makefile; 28 tests
([backend/tests/](backend/tests/)). SkilloVilla logo fetched into
[frontend/public/](frontend/public/).

### `564c1fc` — FitNova reframe
**Why:** the actual PDF brief is about FitNova (fitness), not edtech; graders
grade against their brief. **What:** all fixtures/prompt anchors reworded to
fitness mis-selling ([backend/fixtures.py](backend/fixtures.py),
[backend/analysis/prompts.py](backend/analysis/prompts.py)); dumbbell badge on
the logo ([frontend/components/Header.tsx](frontend/components/Header.tsx));
seed org renamed ([demo/seed.py](demo/seed.py)); the PDF itself committed.

### `a38501e` — Gemini as the real LLM provider
**Why:** no Anthropic key available; user has a Google AI Studio key. Free-tier
reality discovered live: `gemini-2.5-flash` is gated for new keys and flash/pro
quotas 429 quickly → default `gemini-flash-lite-latest`. **What:** `GeminiLLM`
with a process-wide 1 rps throttle + exponential backoff on 429/503, provider
factory ([backend/analysis/llm.py](backend/analysis/llm.py)); provider config
([backend/app/config.py](backend/app/config.py), [.env.example](.env.example));
`google-genai` pinned ([backend/requirements.txt](backend/requirements.txt)).

### `032bb66` — Real-mode frontend testing
**Why (bug):** the quote-gate normaliser was ASCII-only; real Whisper writes
Hinglish in **Devanagari**, so every real flag would have been dropped
silently. Also: inline processing would freeze the browser for minutes, and
the fixture param could mislabel real calls. **What:** Unicode-aware
normalisation + Devanagari tests
([backend/analysis/verify.py](backend/analysis/verify.py),
[backend/tests/unit/test_quote_gate.py](backend/tests/unit/test_quote_gate.py));
real-mode uploads return instantly, worker owns processing, fixture ignored in
real mode ([backend/app/routes/ingest.py](backend/app/routes/ingest.py));
pipeline `jobs` exposed in call detail
([backend/app/routes/calls.py](backend/app/routes/calls.py)); call page polls
every 2.5 s with live stage chips
([frontend/app/calls/[id]/page.tsx](frontend/app/calls/[id]/page.tsx)); seed
forces MOCK_MODE ([demo/seed.py](demo/seed.py)).

### `6906ef2` — Idempotency dedupe UX
**Why (bug):** re-uploading previously-ingested bytes silently opened the old
(mock-era) call — user saw "dummy analysis" and rightly cried foul. **What:**
explicit "already ingested as call #N" banner
([frontend/components/UploadCall.tsx](frontend/components/UploadCall.tsx)).

### `ff234a7` — Voice-based mono diarisation + honest timings
**Why:** the mono fallback alternated speakers at pauses — mislabels anyone who
talks twice in a row; user demanded voice-based separation. Also job timings
looked impossible (Postgres `now()` freezes at transaction start while stages
run inside the txn). **What:** numpy-only acoustic diariser — per-segment
log-mel + pitch fingerprints, deterministic 2-means, separation-based
confidence, honest `None` when voices aren't separable
([backend/transcription/acoustic.py](backend/transcription/acoustic.py),
wired in [backend/transcription/diarize.py](backend/transcription/diarize.py),
tests [backend/tests/unit/test_acoustic_diarise.py](backend/tests/unit/test_acoustic_diarise.py));
queue timestamps switched to `clock_timestamp()`
([backend/pipeline/queue.py](backend/pipeline/queue.py)).

### `a494de0` — Test calls, talk-ratio, CI, packaging
**Why:** user needed uploadable recordings; `talk_over_customer` existed as a
tag but nothing measured it (LLMs shouldn't do arithmetic); CI was promised in
the plan; `numpy`/`soundfile` were imported but never pinned (Docker/CI would
crash). **What:** TTS test-call generator, stereo+mono variants
([demo/make_test_calls.py](demo/make_test_calls.py)); deterministic talk-ratio
flag ([backend/analysis/metrics.py](backend/analysis/metrics.py), wired in
[backend/pipeline/stages/analyse.py](backend/pipeline/stages/analyse.py));
GitHub Actions with a postgres:16 service
([.github/workflows/ci.yml](.github/workflows/ci.yml)); requirements fixed +
real-mode extras split ([backend/requirements.txt](backend/requirements.txt),
[backend/requirements-real.txt](backend/requirements-real.txt)).

### `987eb28` — UI revamp, About page, hardening, deployment blueprint
**Why:** upload had no explicit button ("you just randomly click"), progress UI
was weak, the app "looked like a school project"; the public endpoint needed
abuse protection; deployment needed a paved path. **What:** drag-&-drop upload
with Browse button/file chip/status banners
([frontend/components/UploadCall.tsx](frontend/components/UploadCall.tsx));
professional pipeline stepper
([frontend/components/PipelineStepper.tsx](frontend/components/PipelineStepper.tsx));
"How it works" explainer page ([frontend/app/about/page.tsx](frontend/app/about/page.tsx));
header nav ([frontend/components/Header.tsx](frontend/components/Header.tsx));
200 MB upload cap + 10/min/IP sliding-window rate limiter
([backend/app/ratelimit.py](backend/app/ratelimit.py),
[backend/app/routes/ingest.py](backend/app/routes/ingest.py)); inline-worker
mode for single-container hosts ([backend/app/main.py](backend/app/main.py),
[backend/app/config.py](backend/app/config.py)); Render blueprint
([render.yaml](render.yaml)); [DEPLOYMENT.md](DEPLOYMENT.md).

### `f30ca53` — HF Space attempt + CI fix
**Why (CI bug):** `python-multipart` was installed locally but never pinned —
first CI run red. **Why (deploy):** HF Spaces free tier (16 GB) was the pick
for real-mode cloud… and turned out to be PRO-gated for Docker at deploy time.
**What:** requirement pinned ([backend/requirements.txt](backend/requirements.txt));
Space image with baked Whisper model ([Dockerfile](Dockerfile)); `SEED_MODE`
always/if-empty ([demo/seed.py](demo/seed.py)); one-command Space deploy script
([scripts/deploy_hf_space.ps1](scripts/deploy_hf_space.ps1)) — kept for anyone
with HF PRO.

### `86941b6` — Railway deployment
**Why:** the free host that actually worked (trial: $5 credit, no card;
1 GB RAM → cloud runs Whisper `base`, local keeps `small`). **What:**
[.railwayignore](.railwayignore) (keeps `.env`/audio/junk out of CLI uploads);
[DEPLOYMENT.md](DEPLOYMENT.md) rewritten to the deployed reality.

### `6f86eca` — Diagnostic error state
**Why:** the deployed frontend said "Is the API running on :8000?" — useless in
prod; the real cause was `NEXT_PUBLIC_API_URL` not baked at build time.
**What:** the error now prints exactly which API base the build contains
([frontend/app/director/page.tsx](frontend/app/director/page.tsx)).

### `2c1e90f` — Empty commit, corrected author
**Why:** Vercel Hobby **blocks** deployments from commit authors who aren't
project members on private repos; commits were authored with an email not
registered to the GitHub account. Author switched to
`Aaryansm11@users.noreply.github.com` for all future commits.

### `7aabf3d` — Live links in README ([README.md](README.md)).

### `3853635` — Same-origin API proxy (the ISP fix)
**Why (bug):** the live site failed on the user's networks (desktop *and*
mobile). Diagnosis: Google/Cloudflare/Quad9/OpenDNS all resolve the API domain;
the user's ISP resolver returns **REFUSED** — Indian ISPs block
`*.up.railway.app` DNS wholesale. **What:** Next.js rewrite
`/api/backend/:path* → Railway` so browsers only ever resolve `vercel.app` and
Vercel's edge (outside Indian ISPs) relays to Railway
([frontend/next.config.mjs](frontend/next.config.mjs)); the client auto-uses
the proxy on `*.vercel.app` ([frontend/lib/api.ts](frontend/lib/api.ts)).
**Consequence documented below:** uploads through the proxy inherit Vercel's
~4.5 MB body limit.

### `9c39cf6` — Fixes from live real-call testing
**Why (three user-caught issues):** (1) cloud transcript came out in Urdu
script — Hindi/Urdu are one spoken language and un-hinted smaller Whisper
models pick the Perso-Arabic script; (2) "whoever says hello first = advisor"
failed on a call where the victim answered first; (3) a flag was standing on a
customer-labelled line. **What:** `language_hint` flows into Whisper
(`language="hi"` ⇒ Devanagari) ([backend/transcription/base.py](backend/transcription/base.py),
[backend/transcription/faster_whisper_tx.py](backend/transcription/faster_whisper_tx.py),
[backend/pipeline/stages/transcribe.py](backend/pipeline/stages/transcribe.py),
[backend/pipeline/stages/base.py](backend/pipeline/stages/base.py)) + upload
language selector ([frontend/components/UploadCall.tsx](frontend/components/UploadCall.tsx),
[backend/app/routes/ingest.py](backend/app/routes/ingest.py)); classifier
returns a structured verdict incl. `advisor_is` and **swaps speaker labels**
when content shows they're backwards, idempotency-guarded
([backend/analysis/llm.py](backend/analysis/llm.py),
[backend/analysis/prompts.py](backend/analysis/prompts.py),
[backend/pipeline/stages/classify.py](backend/pipeline/stages/classify.py));
scam/support/remote-access calls explicitly NON_SALES (same prompt);
advisor-only flag policy — customer-attributed flags degrade to `info` with an
attribution note ([backend/pipeline/stages/analyse.py](backend/pipeline/stages/analyse.py)).

### `492799b` — This journal ([PROJECT_JOURNAL.md](PROJECT_JOURNAL.md)).

### `95b9165` — Mixed-stereo diarisation trap
**Why (bug, live call 26):** a stereo MP3 with both voices on both channels and
a constant left-bias made *every* segment left-heavier → channel-split labelled
all 30 segments "advisor" with false 0.83 confidence, and voice clustering
never ran. **What:** channel-split now sanity-checks that BOTH speakers
appear; one-sided results are treated as mixing artifacts and fall through to
voice clustering ([backend/transcription/diarize.py](backend/transcription/diarize.py));
regression test recreating the exact failure shape
([backend/tests/unit/test_acoustic_diarise.py](backend/tests/unit/test_acoustic_diarise.py)).
38 tests.

### `193968a` — README correction: the deployed LLM is **Gemini**, not
Anthropic (Anthropic remains a supported swap) ([README.md](README.md)).

### `de1f1df` — Journal expansion + repo hygiene
Untracked accidentally-committed upload audio (`backend/demo/audio/store/*.mp3`
— uploads land under `backend/` when the API runs from that directory, which
the root ignore didn't cover) and ignored the path going forward
([.gitignore](.gitignore)).

### `8009419` — Cloud persistence for the learning loop
**Why (user-caught design conflict):** the container reseeded with a full
TRUNCATE on every deploy — pristine demos, but it would have erased disputes
and the calibration examples that make the prompt improve, i.e. the learning
loop had amnesia. **What:** `SEED_MODE=if-empty` set on the deployment — the
seed only writes into an empty database, so uploads, disputes and calibration
rows now persist across every deploy; plus a files-only
`regenerate_seed_audio()` path that redraws the 25 synthesized demo WAVs on
the fresh container disk **without touching rows**, keeping demo play buttons
alive ([demo/seed.py](demo/seed.py)). Accepted residual: audio of user uploads
from a previous container life keeps its rows but loses playback (S3/object
storage is the documented production fix). Consequence for testing: identical
bytes now dedupe forever — retest = change the bytes, delete the row, or ask.

### `2bd321f` — Default `called_at` to ingestion time
**Why (user-caught):** the calls list showed "—" for manually uploaded calls.
`called_at` is the vendor-supplied "when did this call happen" timestamp;
manual uploads carry none. **What:** ingest now falls back to `now()` when the
source provides no call time ([backend/ingestion/service.py](backend/ingestion/service.py));
existing NULL rows backfilled from `created_at` directly on Neon.

### (this commit) — About-page refresh + this journal update
**Why:** the "How it works" page predated the diarisation sanity-check,
content-based role assignment, scam classification, advisor-only flag policy,
persistence model and upload limits — stale explainers erode trust. **What:**
[frontend/app/about/page.tsx](frontend/app/about/page.tsx) updated (Diarise,
Classify, Analyse steps; a new "What persists" paragraph; upload limits +
cloud-vs-local Whisper note) and this changelog extended.

---

## 9. Infrastructure & ops decisions that live outside commits

- **Local dev without installs:** Postgres runs from the `callsense` conda env
  (data dir `.pgdata/`, helper [scripts/localdb.ps1](scripts/localdb.ps1));
  Node from a second env. No Docker/Node/Postgres system installs were ever
  made on the dev machine.
- **Neon (cloud Postgres):** project `callsense`, Singapore; migrations applied
  from the dev machine; connection string uses the `postgresql+psycopg://`
  prefix. Demo data is seeded **by the container at boot** — audio files are
  regenerated on the container's own disk so playback works in the cloud (rows
  seeded from a laptop would point at that laptop's paths).
- **Railway:** project `callsense`, deployed via `railway up` (code upload —
  no GitHub app needed). Gotchas hit and fixed: CLI requires an
  **account-scoped** token (workspace tokens are rejected); Railway injects
  `PORT=8080` while the domain targeted 7860 → pinned `PORT=7860` variable;
  each deploy has a ~3–5 min 502 window (build + boot-seed; no zero-downtime
  on a single container).
- **Vercel:** Root Directory must be `frontend`; `NEXT_PUBLIC_*` vars are baked
  at **build** time (set-then-redeploy); Deployment Protection had to be
  disabled for production (it was serving a Vercel login wall); Hobby blocks
  non-member commit authors on private repos (fixed via the noreply author).
- **Upload size limits (layered):** the API accepts **200 MB**; but the live
  site routes uploads through the **Vercel edge proxy** (the ISP-block fix),
  which caps request bodies at **~4.5 MB** — so the practical live-demo limit
  is ~4 minutes of MP3. Local/direct-API use keeps the full 200 MB. Rate
  limit: 10 uploads/min/IP either way.
- **Whisper model by environment:** cloud = `base` (Railway trial is 1 GB RAM),
  local/video = `small` (~3.3× real-time on CPU). One env var
  (`WHISPER_MODEL`) switches.
- **DNS reality:** `*.up.railway.app` resolves on every major public resolver
  but is REFUSED by some Indian ISP resolvers (desktop and mobile carriers) —
  the reason the same-origin proxy exists at all.
- **Repo visibility:** flipped to public (portfolio links to it); verified no
  secrets in the tree before and after (`.env` gitignored + `.railwayignore`).
- **Related repos updated:** portfolio
  (`portfolio-site/src/lib/data/projects.ts` — CallSense as newest featured
  project with GitHub + live links) and `workspace-archive`
  (`Resumes/00-Master-Profile.md` — full CallSense entry).
- **Secrets hygiene:** the Gemini key, Neon password, Railway tokens and an HF
  token all transited the working chat and are scheduled for rotation; none
  are in git. Deleted cloud rows: call 26 twice (once mock-era mislabel, once
  the all-advisor diarisation case) so identical bytes could re-process after
  fixes.
