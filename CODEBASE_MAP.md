# CallSense — Codebase Map & Live-System Guide

> "Where is that implemented?" → find it here in seconds. Every file, what happens
> inside it, its functions, and clickable links. Plus: what lives **outside** this repo
> (Neon / Railway / Vercel / GitHub), and how to **inspect the database** live with
> ready-to-run queries.
>
> Companion: [`INTERVIEW_BIBLE.md`](INTERVIEW_BIBLE.md) (why every decision was made) ·
> [`PROJECT_JOURNAL.md`](PROJECT_JOURNAL.md) (chronological build + bug log).

---

## A. The repo in one screen

```
callsense/
├── backend/            FastAPI + pipeline + analysis  (all the logic)
│   ├── app/            HTTP layer: config, routes, rate limiting
│   ├── db/             schema (models), session, migrations, rollup views
│   ├── ingestion/      getting calls IN: envelope, adapters, validation
│   ├── pipeline/       the queue + worker + 6 stages
│   ├── transcription/  Whisper + diarisation (incl. the numpy voice clusterer)
│   ├── analysis/       rubric, prompts, LLM clients, quote gate, redaction
│   ├── feedback.py     the dispute state machine
│   ├── fixtures.py     MOCK_MODE canned transcripts + analyses
│   └── tests/          38 tests (unit / integration / api)
├── frontend/           Next.js dashboards (Director / TL / Advisor + call detail)
├── demo/               seed.py (demo data) + make_test_calls.py (TTS test audio)
├── scripts/            localdb.ps1 (local Postgres), deploy_hf_space.ps1
└── (root)              Dockerfile, docker-compose.yml, render.yaml, CI, docs
```

**Mental model:** `ingestion/` gets a call in → `pipeline/` moves it through stages →
`transcription/` + `analysis/` do the work → `db/` stores it → `app/` serves it →
`frontend/` shows it → `feedback.py` closes the human loop.

---

## B. File-by-file walkthrough

### B1. `backend/app/` — the HTTP layer

| File | What happens inside | Key functions / symbols |
|---|---|---|
| [`app/config.py`](backend/app/config.py) | **Every configuration knob**, loaded from env and validated at boot (pydantic-settings). Fails loud on bad values instead of mid-request. | `class Settings(BaseSettings)` (fields: `mock_mode`, `llm_provider`, `gemini_model`, `whisper_model`, `run_inline_worker`, `job_max_attempts`, `llm_min_interval_s`…), `get_settings()` — `@lru_cache`d so config parses once/process |
| [`app/main.py`](backend/app/main.py) | Builds the FastAPI app, mounts all routers, CORS, health checks, **starts the inline worker thread** when deployed single-container, serves a **custom `/docs`** with a relative openapi URL (so Swagger works through the Vercel proxy). | `app = FastAPI(docs_url=None…)`, `swagger_docs()`, `root()`, `health()`, `health_db()`, `_maybe_start_inline_worker()` |
| [`app/deps.py`](backend/app/deps.py) | Shared FastAPI dependencies. | `get_queue()` (returns the singleton `PostgresJobQueue`), `get_role()` (the **role-switcher stub** — reads `X-Role`; where real RBAC would enforce scope) |
| [`app/schemas.py`](backend/app/schemas.py) | Pydantic request/response models for the API (same validation mechanism as LLM output — "one validation story"). | `IngestResponse`, `DisputeCreate`, `DisputeResolve` |
| [`app/ratelimit.py`](backend/app/ratelimit.py) | Per-IP sliding-window rate limiting, thread-safe, proxy-aware (reads `X-Forwarded-For`). Raises 429 + `Retry-After`. | `class RateLimiter`, `upload_rate_limit = RateLimiter(10, 60.0)` |
| [`app/routes/ingest.py`](backend/app/routes/ingest.py) | **`POST /ingest/upload`** — the front door. Enforces the 200MB cap + rate limit, builds an envelope via `RestAdapter`, calls `ingest()`. Ignores `fixture` and skips inline draining unless in mock mode. | `upload()`, `MAX_UPLOAD_BYTES` |
| [`app/routes/calls.py`](backend/app/routes/calls.py) | `GET /calls` (list), **`GET /calls/{id}`** (the call-detail payload: call+advisor+team+composite, transcript, segments with redacted text, scores, flags, **and pipeline `jobs`** for the live stepper), `GET /calls/{id}/audio` (streams the file). | `list_calls()`, `call_detail()`, `call_audio()`, `_MEDIA` (suffix→MIME) |
| [`app/routes/summaries.py`](backend/app/routes/summaries.py) | **All three dashboards' data**, read from the rollup views. Org: KPIs + team table + daily trend + risk feed. Team: leaderboard + **per-dimension heatmap** + **dispute inbox**. Advisor: my-vs-team dimension averages + trend + my calls. | `org_summary()`, `team_summary()`, `advisor_summary()`, `advisor_calls()` |
| [`app/routes/flags.py`](backend/app/routes/flags.py) | **`POST /flags/{id}/dispute`** — advisor raises a dispute; 409 on illegal transition. | `dispute_flag()` |
| [`app/routes/disputes.py`](backend/app/routes/disputes.py) | **`POST /disputes/{id}/resolve`** — TL upholds/dismisses; returns the **recomputed composite**. | `resolve()` |
| [`app/routes/ops.py`](backend/app/routes/ops.py) | **`GET /ops/jobs`** — queue state (counts by status + recent rows with `last_error`): the "how do I debug a stuck call" answer. `POST /ops/jobs/{id}/requeue` — revive a dead-lettered job. | `list_jobs()`, `requeue()` |

### B2. `backend/db/` — schema & storage

| File | What happens inside | Key symbols |
|---|---|---|
| [`db/models.py`](backend/db/models.py) | **The entire 13-table schema** as SQLAlchemy 2 models + all closed-taxonomy enums. Read this file when asked "show me your data model." | Enums: `CallStatus, JobStage, JobStatus, SpeakerRole, RubricDimension, FlagTag, FlagSeverity, FlagState, CalibrationVerdict`. Tables: `Org, Team, Advisor, Call, ProcessingJob, Transcript, Segment, Score, CallScore, Flag, Dispute, CalibrationExample, AuditLog`. Helper: `_enum()` (VARCHAR+CHECK rendering) |
| [`db/views.sql`](backend/db/views.sql) | **The averaging policy, physically.** advisor = mean of call composites; **team = mean over advisors**; org = mean over teams. Critical flags counted via a correlated subquery to avoid join fan-out. | `v_advisor_scores`, `v_team_scores`, `v_org_scores` |
| [`db/base.py`](backend/db/base.py) | Declarative base + timestamps mixin. | `Base`, `TimestampMixin` |
| [`db/session.py`](backend/db/session.py) | Engine, session factory, the FastAPI DB dependency, and the readiness ping. | `engine`, `SessionLocal`, `get_db()`, `ping()` |
| [`db/alembic/versions/20260710_1855_initial_schema.py`](backend/db/alembic/versions/20260710_1855_initial_schema.py) | Creates all 13 tables. Contains the hand-fixed **circular FK** (`teams.team_leader_id → advisors`) added via a separate `create_foreign_key` after both tables exist. | `upgrade()`, `downgrade()` |
| [`db/alembic/versions/20260710_1856_rollup_views.py`](backend/db/alembic/versions/20260710_1856_rollup_views.py) | Executes `views.sql` so the views ship with the schema. | `upgrade()` |
| [`db/alembic/env.py`](backend/db/alembic/env.py) | Points Alembic at the app's `DATABASE_URL` + model metadata (so the same migrations run local / compose / Neon). | `run_migrations_online()` |

### B3. `backend/ingestion/` — getting calls in (source-agnostic)

| File | What happens inside | Key functions |
|---|---|---|
| [`ingestion/envelope.py`](backend/ingestion/envelope.py) | The **canonical shape** every source normalises into + the identity function. | `class CallEnvelope`, **`derive_idempotency_key(audio_bytes, source)`** = `sha256(bytes)+":"+source` |
| [`ingestion/adapters/base.py`](backend/ingestion/adapters/base.py) | **The source-agnostic contract** — the one interface the pipeline speaks. Adding Exotel/Twilio = one new file here. | `class SourceAdapter(ABC)` → `fetch_new() -> list[CallEnvelope]` |
| [`ingestion/adapters/folder.py`](backend/ingestion/adapters/folder.py) | Watch-folder (polling) source; reads an optional `<file>.json` sidecar for metadata. The 25 seeded demo calls come through here. | `FolderAdapter.fetch_new()`, `.build(path)` |
| [`ingestion/adapters/rest.py`](backend/ingestion/adapters/rest.py) | Push/webhook source used by the upload endpoint; persists bytes to the audio store. | `RestAdapter.build(filename, content, advisor_external_id, org_id, language_hint, extra)` |
| [`ingestion/adapters/mock_crm.py`](backend/ingestion/adapters/mock_crm.py) | **Proves source-agnosticism**: maps a vendor payload (`agent_ref`, `call_uuid`, `lead_phone`…) into the same envelope, whole row preserved in `raw_metadata`. | `MockCrmAdapter.fetch_new()` |
| [`ingestion/validation.py`](backend/ingestion/validation.py) | The **ffprobe gate**: is this really audio, is duration > 0, how many channels? Rejects never enter the pipeline. | `probe_audio(path) -> AudioInfo`, `AudioValidationError` |
| [`ingestion/service.py`](backend/ingestion/service.py) | **The ingest orchestration**: validate → resolve advisor → idempotent insert → enqueue stage 1. Rejections + creations are audit-logged. | **`ingest(session, env, queue) -> IngestResult`**, `_resolve_advisor()` (`external_ids ? :ext`), `_audit()` |

### B4. `backend/pipeline/` — queue, worker, stages

| File | What happens inside | Key functions |
|---|---|---|
| [`pipeline/queue.py`](backend/pipeline/queue.py) | **The queue.** Atomic claim via `FOR UPDATE SKIP LOCKED`, retries with exponential backoff + jitter, dead-lettering, crash recovery via visibility timeout. All times use `clock_timestamp()`. | `class JobQueue(ABC)` (the swap seam), `PostgresJobQueue.enqueue/claim/complete/fail`, `backoff_seconds(attempt)`, `VISIBILITY_TIMEOUT_S=300`, `JobClaim` |
| [`pipeline/worker.py`](backend/pipeline/worker.py) | **The worker loop + transaction boundaries**: claim (txn 1, commit immediately) → run stage + mark done + enqueue next (txn 2, atomic) → on failure, fail/retry (txn 3). | `process_one(queue)`, `run_until_idle(queue)` (tests/seed), `main()` (the long-running loop) |
| [`pipeline/stages/__init__.py`](backend/pipeline/stages/__init__.py) | The stage registry + **the only branch in the graph** (non-sales terminates after classify). | `STAGE_ORDER`, `STAGES`, **`next_stage(current, session, call_id)`** |
| [`pipeline/stages/base.py`](backend/pipeline/stages/base.py) | Shared stage helpers. | `load_call()` → `CallInfo`, `load_tx_segments(redacted=)`, `set_call_status()`, `merge_raw_metadata()` |
| [`pipeline/stages/transcribe.py`](backend/pipeline/stages/transcribe.py) | Stage 1. Idempotent (skips if a transcript exists). Calls the transcriber with the **language hint**, writes transcript + segments. | `run(session, call_id)` |
| [`pipeline/stages/diarise.py`](backend/pipeline/stages/diarise.py) | Stage 2. Runs the diarisation ladder, writes speaker labels, stores `diarisation_confidence`. | `run()` |
| [`pipeline/stages/redact.py`](backend/pipeline/stages/redact.py) | Stage 3. Masks PII per segment into `redacted_text` **before** anything reaches the LLM. | `run()` |
| [`pipeline/stages/classify.py`](backend/pipeline/stages/classify.py) | Stage 4. Cheap LLM screen on the first 12 turns: sales?, and **is the advisor label correct** (swaps all labels if backwards, guarded against double-swap). Non-sales → tag + finalise (no score). | `run()`, `OPENING_TURNS=12` |
| [`pipeline/stages/analyse.py`](backend/pipeline/stages/analyse.py) | **Stage 5 — the heart.** LLM → schema validation (1 retry) → **quote gate per flag** (drop unmatched) → derive timestamps → confidence + advisor-only downgrades → **talk-ratio metric** → composite with compliance cap → write scores/flags/call_scores stamped with `rubric_version` + `prompt_hash`. | `run()`, `_analyse_with_retry()`, `_speaker_of()`, `_load_calibration()` |
| [`pipeline/stages/validate.py`](backend/pipeline/stages/validate.py) | Stage 6. Invariant gate: composite exists + all 5 dimensions scored → `done`, else `needs_review`. | `run()` |

### B5. `backend/transcription/` — STT + diarisation

| File | What happens inside | Key functions |
|---|---|---|
| [`transcription/base.py`](backend/transcription/base.py) | The **Transcriber interface** + data shapes. The `language` param is what keeps Hinglish in Devanagari. | `TxSegment`, `TranscriptResult`, `class Transcriber(ABC).transcribe(audio_uri, channels, language)` |
| [`transcription/factory.py`](backend/transcription/factory.py) | Picks Mock vs real Whisper from config. | `get_transcriber(fixture)` |
| [`transcription/faster_whisper_tx.py`](backend/transcription/faster_whisper_tx.py) | Real STT. Lazy-loads the model (so mock mode never pays for it), `vad_filter=True`, `beam_size=5`, passes the language hint, and derives a **no-reference quality estimate**. | `FasterWhisperTranscriber._load()`, `.transcribe()`, `_wer_estimate(logprobs)` |
| [`transcription/mock.py`](backend/transcription/mock.py) | Returns a canned fixture transcript (keyless demos). | `MockTranscriber.transcribe()` |
| [`transcription/diarize.py`](backend/transcription/diarize.py) | **The diarisation ladder**: already-labelled → stereo channel-split (**with the one-sided self-audit**) → acoustic voice clustering → turn-alternation at low confidence. | **`diarise(audio_uri, channels, segments)`**, `_channel_split()`, `_turn_fallback()`, `_STEREO_SEPARATION_MIN=0.15` |
| [`transcription/acoustic.py`](backend/transcription/acoustic.py) | **The algorithm you wrote** — mono diarisation with numpy only. Per-segment voice fingerprint (40-band log-mel envelope + pitch), z-scored, deterministic 2-means, separation score gates honesty. | **`acoustic_diarise()`**, `_mel_filterbank()`, `_frames()`, `_pitch_hz()` (autocorrelation F0), `_fingerprint()`, `_two_means()`, `MIN_SEPARATION=1.15`, `MIN_SEG_S=0.4` |
| [`transcription/textutils.py`](backend/transcription/textutils.py) | Crude code-switch ratio (monitoring signal stored per transcript). | `estimate_code_switch(text)` |

### B6. `backend/analysis/` — the judgment layer

| File | What happens inside | Key symbols |
|---|---|---|
| [`analysis/rubric.py`](backend/analysis/rubric.py) | **The scoring policy**: dimension weights, tag→severity map, the cap, the confidence threshold, and the composite math. | `RUBRIC_VERSION`, `DIMENSION_WEIGHTS`, `TAG_SEVERITY`, `CRITICAL_TAGS`, `COMPLIANCE_CAP=40.0`, `CONFIDENCE_THRESHOLD=0.6`, **`compute_composite(scores, has_critical) -> (composite, capped)`** |
| [`analysis/schema.py`](backend/analysis/schema.py) | The **closed-taxonomy** Pydantic models the LLM must fill. Enum fields = the model can't invent a tag. | `DimensionScore`, `RawFlag`, `AnalysisResult` |
| [`analysis/prompts.py`](backend/analysis/prompts.py) | **All prompt text**: the analyst role frame, the rubric with 0/5 anchors, the closed tag list, the rules (advisor-only flags, verbatim quotes, no invented timestamps), and **calibration few-shot injection**. | `SYSTEM`, `_ANCHORS`, `_TAGS`, **`build_analysis_user_prompt(transcript, calibration)`**, **`build_classify_prompt(opening)`** |
| [`analysis/verify.py`](backend/analysis/verify.py) | **The quote-verification gate** — the anti-hallucination core. Unicode-aware normalisation (works on Devanagari), sliding word-window fuzzy match. | **`verify_quote(quote, segments, threshold=0.85)`**, `QuoteMatch`, `_normalise()` |
| [`analysis/redaction.py`](backend/analysis/redaction.py) | **PII masking** with ordered patterns and a Luhn check so random digits aren't masked. | **`redact(text) -> (redacted, [types])`**, `_luhn_ok()`, `EMAIL/CARD/AADHAAR/OTP_CTX/PHONE/PAN` |
| [`analysis/metrics.py`](backend/analysis/metrics.py) | Deterministic conversation metrics — **computed by code, never the LLM**. | **`talk_ratio(segments)`**, `TALK_RATIO_THRESHOLD=0.75` |
| [`analysis/llm.py`](backend/analysis/llm.py) | **The LLM swap seam** + rate limiting + retries. | `class LLM(ABC)` (`analyse`, `classify`), `MockLLM`, **`GeminiLLM`** (`_generate` with throttle + backoff), `AnthropicLLM`, **`get_llm(fixture)`**, `_throttle()`, `_is_retryable()`, `_parse_classify()`, `_extract_json()` |
| [`analysis/recompute.py`](backend/analysis/recompute.py) | Recomputes a call's composite after a dispute — a **dismissed** critical flag no longer caps. | **`recompute_call_score(session, call_id)`** |

### B7. Loop + fixtures + demo

| File | What happens inside | Key functions |
|---|---|---|
| [`backend/feedback.py`](backend/feedback.py) | **The dispute state machine** (`open → disputed → upheld\|dismissed`), enforced. Resolution mints a **calibration example**, triggers recompute, and audit-logs the human action. | **`raise_dispute()`**, **`resolve_dispute()`**, `DisputeError`, `ResolveResult`, `_audit()` |
| [`backend/fixtures.py`](backend/fixtures.py) | The 5 MOCK_MODE scenarios (transcript **and** matching analysis, quotes verbatim so the gate passes). | `FIXTURES`, `DEFAULT_FIXTURE`, `get_fixture(name)` |
| [`demo/seed.py`](demo/seed.py) | Seeds 1 org / 3 teams / 9 advisors / 25 calls through the real pipeline; leaves one dispute open for the TL inbox. `SEED_MODE=if-empty` protects live data. | `reset_and_seed_org()`, `seed_calls()`, `make_wav()`, **`regenerate_seed_audio()`**, `_should_seed()` |
| [`demo/make_test_calls.py`](demo/make_test_calls.py) | Renders Hinglish test calls with two TTS voices (stereo advisor-left/customer-right + mono). | `build()`, `_synth()`, `CALLS` |

### B8. Frontend

| File | What happens inside |
|---|---|
| [`frontend/lib/api.ts`](frontend/lib/api.ts) | `API_BASE` resolution — **uses the `/api/backend` same-origin proxy on `*.vercel.app`** (the ISP-block fix), env/localhost otherwise. `uploadCall()`. |
| [`frontend/next.config.mjs`](frontend/next.config.mjs) | **The edge proxy**: `rewrites()` maps `/api/backend/:path*` → Railway. Also `output: "standalone"`. |
| [`frontend/lib/useApi.ts`](frontend/lib/useApi.ts) | Fetch hook with `reload()` (used after disputes) — powers the live polling. |
| [`frontend/components/UploadCall.tsx`](frontend/components/UploadCall.tsx) | The dropzone + Browse button + language selector + REAL/DEMO banner + **idempotency-dedupe message**. |
| [`frontend/components/PipelineStepper.tsx`](frontend/components/PipelineStepper.tsx) | The six-stage live progress strip (running spinner, retries, errors, skipped). |
| [`frontend/app/calls/[id]/page.tsx`](frontend/app/calls/%5Bid%5D/page.tsx) | **The money screen**: audio player, speaker-coloured transcript, flags pinned at timestamps, **click-flag-to-seek**, dispute button, polls every 2.5s while processing. |
| [`frontend/app/director/page.tsx`](frontend/app/director/page.tsx) · [`team`](frontend/app/team/page.tsx) · [`advisor`](frontend/app/advisor/page.tsx) | The three role dashboards (org health / leaderboard+heatmap+dispute inbox / advisor detail). |
| [`frontend/app/about/page.tsx`](frontend/app/about/page.tsx) | The in-app "How it works" explainer — **open this if an interviewer wants the tour**. |
| [`frontend/components/ui.tsx`](frontend/components/ui.tsx) · [`charts.tsx`](frontend/components/charts.tsx) · [`Header.tsx`](frontend/components/Header.tsx) | Design system, Recharts wrappers, header + role switcher. |

### B9. Infra & tests

| File | What it does |
|---|---|
| [`Dockerfile`](Dockerfile) (root) | The **deployed real-mode image**: ffmpeg, bakes the Whisper model at build, boots `alembic upgrade head → seed.py → uvicorn` with the inline worker. |
| [`docker-compose.yml`](docker-compose.yml) | Local 4-service stack (postgres, api, worker, web) — the `make demo` path. |
| [`render.yaml`](render.yaml) · [`scripts/deploy_hf_space.ps1`](scripts/deploy_hf_space.ps1) | The two deployment routes that were tried and rejected (kept as documented fallbacks). |
| [`.github/workflows/ci.yml`](.github/workflows/ci.yml) | CI: backend tests against a real `postgres:16` service + frontend build, on every push. |
| [`scripts/localdb.ps1`](scripts/localdb.ps1) | Start/stop the conda-provided local Postgres (`.pgdata`). |
| [`backend/tests/unit/test_quote_gate.py`](backend/tests/unit/test_quote_gate.py) | Proves the gate: exact / STT-noisy / absent / **Devanagari** quotes. |
| [`backend/tests/unit/test_acoustic_diarise.py`](backend/tests/unit/test_acoustic_diarise.py) | Proves voice clustering + the **mixed-stereo regression**. |
| [`backend/tests/unit/test_rubric.py`](backend/tests/unit/test_rubric.py) | Proves the compliance cap math. |
| [`backend/tests/integration/test_pipeline.py`](backend/tests/integration/test_pipeline.py) · [`test_queue.py`](backend/tests/integration/test_queue.py) | Full loop writes every table; duplicate→one call; non-sales excluded; retry→dead-letter; idempotent resume. |
| [`backend/tests/api/test_disputes.py`](backend/tests/api/test_disputes.py) | Dispute lifecycle + recompute + the 409 guard. |

---

## C. Reverse index — "where is *that* implemented?"

| If they ask about… | Point here |
|---|---|
| Source-agnostic ingestion | [`ingestion/adapters/base.py`](backend/ingestion/adapters/base.py) (the ABC) + the 3 adapters |
| Idempotency / no double-processing | `derive_idempotency_key` in [`envelope.py`](backend/ingestion/envelope.py); `ON CONFLICT` in [`service.py`](backend/ingestion/service.py); `UNIQUE` in [`models.py`](backend/db/models.py) |
| The queue / SKIP LOCKED | `PostgresJobQueue.claim` in [`queue.py`](backend/pipeline/queue.py) |
| Retries / backoff / dead-letter | `backoff_seconds` + `fail` in [`queue.py`](backend/pipeline/queue.py) |
| Crash recovery | the visibility-timeout clause in `claim`; `process_one` txn boundaries in [`worker.py`](backend/pipeline/worker.py) |
| Transcription / Whisper | [`faster_whisper_tx.py`](backend/transcription/faster_whisper_tx.py) |
| Diarisation (who spoke when) | [`diarize.py`](backend/transcription/diarize.py) (ladder) + [`acoustic.py`](backend/transcription/acoustic.py) (the algorithm) |
| PII redaction | `redact()` in [`redaction.py`](backend/analysis/redaction.py); applied in [`stages/redact.py`](backend/pipeline/stages/redact.py) |
| **Stopping hallucinated flags** | `verify_quote` in [`verify.py`](backend/analysis/verify.py); enforced in the flag loop of [`stages/analyse.py`](backend/pipeline/stages/analyse.py) |
| Closed taxonomy | enums in [`schema.py`](backend/analysis/schema.py) + [`models.py`](backend/db/models.py) |
| Prompts / few-shot calibration | [`prompts.py`](backend/analysis/prompts.py) (`build_analysis_user_prompt`) |
| The rubric / weights / cap | [`rubric.py`](backend/analysis/rubric.py) (`compute_composite`) |
| Talk-ratio (computed by code) | [`metrics.py`](backend/analysis/metrics.py) |
| Non-sales filtering | [`stages/classify.py`](backend/pipeline/stages/classify.py) |
| Speaker-role correction | the swap block in [`stages/classify.py`](backend/pipeline/stages/classify.py) |
| Dispute → recompute → calibration | [`feedback.py`](backend/feedback.py) + [`recompute.py`](backend/analysis/recompute.py) |
| Audit trail | `_audit()` in [`feedback.py`](backend/feedback.py) and [`service.py`](backend/ingestion/service.py); `AuditLog` in [`models.py`](backend/db/models.py) |
| Team/org averaging policy | [`views.sql`](backend/db/views.sql) |
| Dashboard queries | [`routes/summaries.py`](backend/app/routes/summaries.py) |
| Rate limiting / upload caps | [`ratelimit.py`](backend/app/ratelimit.py) + `MAX_UPLOAD_BYTES` in [`routes/ingest.py`](backend/app/routes/ingest.py) |
| LLM provider swap / retries | [`llm.py`](backend/analysis/llm.py) (`get_llm`, `GeminiLLM._generate`) |
| Mock mode | `mock_mode` in [`config.py`](backend/app/config.py); [`fixtures.py`](backend/fixtures.py); `get_llm`/`get_transcriber` factories |
| Click-flag-to-seek-audio | [`app/calls/[id]/page.tsx`](frontend/app/calls/%5Bid%5D/page.tsx) |
| The ISP-block proxy | `rewrites()` in [`next.config.mjs`](frontend/next.config.mjs) + `API_BASE` in [`lib/api.ts`](frontend/lib/api.ts) |

---

## D. What lives **outside** this repo

Four external systems. Nothing secret is in git — [`.env`](.env.example) is gitignored;
the real values live in each provider's dashboard.

| Where | What it holds | How to open it | What to say |
|---|---|---|---|
| **Neon** (console.neon.tech) | **The database.** All 13 tables + 3 views, all rows, forever. Project `callsense`, region Singapore. | Sign in with GitHub → project `callsense` → **Tables** (browser) or **SQL Editor** | "Managed serverless Postgres — the only stateful component. Everything else is stateless and disposable." |
| **Railway** (railway.com) | **The backend**: Docker container running FastAPI + the inline worker + Whisper. Also holds the **secrets** (`DATABASE_URL`, `GEMINI_API_KEY`, `WHISPER_MODEL=base`, `PORT=7860`, `MOCK_MODE=false`, `RUN_INLINE_WORKER=true`, `SEED_MODE=if-empty`). | Project `callsense` → service `callsense` → **Variables** / **Deployments** / **Logs** | "Secrets are server-side env vars, never in the repo or the client bundle. The container disk is ephemeral — that's why audio is regenerated and why S3 is the production fix." |
| **Vercel** (vercel.com) | **The frontend** (Next.js) + the **edge proxy** that forwards `/api/backend/*` to Railway. Holds `NEXT_PUBLIC_API_URL` (baked at build time). Root Directory = `frontend`. | Project `callsense` → Settings → Environment Variables / Deployments | "The proxy exists because Indian ISPs refuse DNS for `*.up.railway.app` — the browser only ever resolves vercel.app." |
| **GitHub** (Aaryansm11/callsense) | Source + **CI** (tests on every push). Public. | Actions tab for CI runs | "CI runs the suite against a real Postgres service container on every push." |
| *(Google AI Studio)* | Issues the Gemini API key. No data stored there. | aistudio.google.com/usage for quota | "Only redacted transcript text is ever sent." |

**Config → where it's set:** local dev = `backend/.env` (gitignored) · Docker = env in
[`docker-compose.yml`](docker-compose.yml) · deployed backend = Railway Variables ·
deployed frontend = Vercel Environment Variables. The defaults for every key live in
[`app/config.py`](backend/app/config.py) and are documented in [`.env.example`](.env.example).

---

## E. The database — tables, what they do, how to check

### E1. The 13 tables + 3 views

| Table | Holds | Key columns worth naming |
|---|---|---|
| `orgs` | The company (FitNova). | `id, name` |
| `teams` | Pods under an org. | `org_id`, `team_leader_id` (→ advisors, the circular FK) |
| `advisors` | Tele-advisors. | `team_id`, **`external_ids` (JSONB array of dialer agent-IDs)** |
| `calls` | One row per call. | **`idempotency_key` (UNIQUE)**, `source`, `audio_uri`, `duration_s`, `channels`, `called_at`, `language_hint`, **`raw_metadata` JSONB** (fixture, diarisation_confidence, talk_ratio, roles_swapped, pii_redacted), `status` |
| `processing_jobs` | **The queue.** One row per (call, stage). | `stage`, `status(pending/running/done/failed/dead)`, `attempts`, `max_attempts`, `last_error`, `run_after` |
| `transcripts` | One per call. | `engine` (e.g. `faster-whisper:base`), `language`, `code_switch_ratio`, `wer_estimate`, `text` |
| `segments` | Timestamped utterances. | `idx`, **`speaker`**, `start_s`, `end_s`, `text`, **`redacted_text`** |
| `scores` | One row per rubric dimension per call. | `dimension`, `raw_score(0-5)`, `weight`, `evidence_quote`, `evidence_start_s`, **`model`, `prompt_hash`, `rubric_version`** |
| `call_scores` | **Materialised composite**, one per call. | `composite(0-100)`, **`compliance_capped`**, `rubric_version` |
| `flags` | Issues raised. | `tag`, `severity(info/warn/critical)`, `start_s`, `quote`, `reason`, `confidence`, **`state(open/disputed/upheld/dismissed)`** |
| `disputes` | Advisor appeals. | `flag_id`, `raised_by`, `note`, `resolved_by`, `resolution`, `resolved_at` |
| `calibration_examples` | **The learning-loop memory** — injected into future prompts. | `tag`, `quote`, **`verdict(true_positive/false_positive)`**, `source_dispute_id` |
| `audit_log` | Append-only human/system actions. | `actor`, `action`, `entity`, `entity_id`, `before` / `after` JSONB, `at` |
| **`v_advisor_scores`** (view) | advisor avg + scored_calls + critical_flags | |
| **`v_team_scores`** (view) | **mean over advisors** | |
| **`v_org_scores`** (view) | mean over teams | |

### E2. Three ways to inspect it

**1. Neon console (best for the interview — visual + live).** console.neon.tech → project
`callsense` → **Tables** to browse, or **SQL Editor** to run anything in E3.

**2. Through the API (no login, works on a shared screen):**
`…/docs` (Swagger, click *Try it out*) · `GET /calls` · `GET /calls/{id}` ·
`GET /orgs/1/summary` · **`GET /ops/jobs`** (queue state). Through the live site use the
proxy prefix, e.g. `…vercel.app/api/backend/ops/jobs`.

**3. Local Postgres (psql):**
```powershell
./scripts/localdb.ps1 start        # if not running
conda run -n callsense psql -U callsense -h localhost -d callsense
# \dt        list tables      \d calls     describe a table      \q  quit
```
Or connect a GUI (DBeaver/TablePlus): host `localhost`, port `5432`, db/user/pass all
`callsense`. For **Neon**, paste its connection string into the same GUI.

### E3. Query cookbook (paste-ready — rehearse 4–5 of these)

```sql
-- 1. The dashboard, in one query (the "entire Director view" line)
SELECT * FROM v_org_scores;
SELECT * FROM v_team_scores ORDER BY avg_composite DESC;

-- 2. Recent calls with score + flag counts
SELECT c.id, c.status, c.source, round(c.duration_s) AS secs,
       cs.composite, cs.compliance_capped,
       (SELECT count(*) FROM flags f WHERE f.call_id = c.id) AS flags
FROM calls c LEFT JOIN call_scores cs ON cs.call_id = c.id
ORDER BY c.id DESC LIMIT 10;

-- 3. Show the anti-hallucination gate's output: every flag WITH its evidence + timestamp
SELECT call_id, tag, severity, state, round(start_s::numeric,1) AS at_sec,
       left(quote, 60) AS evidence, confidence
FROM flags ORDER BY call_id DESC, start_s;

-- 4. Prove the compliance cap on a specific call (dimensions vs final composite)
SELECT dimension, raw_score, weight FROM scores WHERE call_id = 1 ORDER BY id;
SELECT composite, compliance_capped FROM call_scores WHERE call_id = 1;

-- 5. Provenance / reproducibility: which model + prompt produced these scores?
SELECT DISTINCT rubric_version, model, left(prompt_hash, 12) AS prompt
FROM scores WHERE call_id = 1;

-- 6. The transcript with speakers (diarisation output) + redaction
SELECT s.idx, s.speaker, round(s.start_s::numeric,1) AS t,
       left(COALESCE(s.redacted_text, s.text), 70) AS line
FROM segments s JOIN transcripts t ON t.id = s.transcript_id
WHERE t.call_id = 1 ORDER BY s.idx LIMIT 15;

-- 7. The queue: how the pipeline ran (and any failures)
SELECT stage, status, attempts, last_error,
       round(EXTRACT(EPOCH FROM (updated_at - created_at))::numeric,1) AS secs
FROM processing_jobs WHERE call_id = 1 ORDER BY id;
SELECT status, count(*) FROM processing_jobs GROUP BY status;   -- fleet health

-- 8. The human feedback loop end to end
SELECT f.id AS flag, f.tag, f.state, d.note, d.resolution, d.resolved_by
FROM flags f LEFT JOIN disputes d ON d.flag_id = f.id
WHERE f.state <> 'open';
SELECT * FROM calibration_examples;        -- what the system LEARNED from humans

-- 9. Audit trail: who did what
SELECT actor, action, entity, entity_id, before, after, at
FROM audit_log ORDER BY at DESC LIMIT 10;

-- 10. Non-sales calls are excluded from averages (proof)
SELECT c.id, c.status, cs.composite            -- composite is NULL for non-sales
FROM calls c LEFT JOIN call_scores cs ON cs.call_id = c.id
WHERE EXISTS (SELECT 1 FROM flags f WHERE f.call_id = c.id AND f.tag='non_sales_call');

-- 11. Source-agnosticism: calls arrived from multiple sources
SELECT source, count(*) FROM calls GROUP BY source;

-- 12. Advisor-ID mapping (how a new dialer plugs in)
SELECT id, name, external_ids FROM advisors LIMIT 5;
```

### E4. Live-demo hygiene

- **Re-testing the same audio?** The idempotency guard blocks it. Either change the bytes,
  or `DELETE FROM calls WHERE id = <n>;` (cascades remove its transcript/segments/scores/
  flags/disputes).
- **Site shows 502 right after a deploy?** Normal — the container rebuilds + reseeds
  (~4 min); single container = no zero-downtime deploys.
- **Free-tier notes:** Railway trial credit is finite; Whisper is `base` in the cloud
  (1GB RAM) vs `small` locally.
