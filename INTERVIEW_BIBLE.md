# CallSense — The Interview Bible

> Everything about this project, dense enough that you (or any AI you paste it into)
> can explain and defend every decision, file, function, and variable. Read top to
> bottom once; then drill the Q&A in §9–§11. Companion docs: [`README.md`](README.md)
> (what it is), [`WRITEUP.md`](WRITEUP.md) (the submitted design writeup),
> [`PROJECT_JOURNAL.md`](PROJECT_JOURNAL.md) (chronological build+bug log),
> [`DEPLOYMENT.md`](DEPLOYMENT.md) (how it's hosted).

**Live:** https://callsense-aaryan-s-maralihallis-projects.vercel.app ·
**API:** https://callsense-production-d0b3.up.railway.app/docs ·
**Repo:** https://github.com/Aaryansm11/callsense

---

## §0. How to use this in the interview

The HR said: *the round is about the project — how deep you go, how you justify choices
and trade-offs; then fundamentals and AI-solutioning scenarios.* So your job is to
demonstrate **ownership**. Three rules:

1. **Every "what" must come with a "why" and a "why not the alternative."** They're not
   testing whether you used Postgres; they're testing whether you know *why Postgres and
   not Kafka*, and what breaks if you're wrong. This doc pairs every decision with its
   rejected alternative.
2. **Lead with the constraint.** Almost every choice traces to one of three constraints:
   *lean org → cheap & low-ops*, *zero labelled data on day one*, *48-hour build then
   hardened*. Name the constraint, then the choice falls out naturally.
3. **Be honest about failure.** The strongest signal you can send is knowing exactly
   where your own system breaks (§11). Confidence without candour reads as naïveté.

---

## §1. The pitch (memorise both)

**15-second version:** "FitNova's team leaders can only manually review about 5% of
sales calls, so mis-selling — fake guarantees, hidden costs, pressure tactics — surfaces
only when a customer complains. CallSense reviews 100%: it transcribes every call,
separates the speakers, scores it on a 5-dimension rubric with an LLM that must quote its
evidence, flags mis-selling with timestamps, and surfaces it on role dashboards — with a
dispute loop so advisors trust it."

**90-second version:** add the *how*: "Calls arrive through source-agnostic adapters —
folder, REST, or CRM — behind one canonical envelope. They go into a Postgres-backed job
queue using `SELECT … FOR UPDATE SKIP LOCKED`, then six idempotent stages: local Whisper
transcription, voice-based diarisation, PII redaction *before* anything leaves the box, a
cheap non-sales classifier, LLM rubric analysis, and a validation gate. The anti-
hallucination design is the core: the model can only pick from a closed tag list, must
attach a verbatim quote, and every quote is fuzzy-matched back to the transcript — if it
doesn't match, the flag is dropped, and timestamps are computed by code, not the model.
One critical compliance flag caps the score at 40, so a smooth talker can't average away
mis-selling. When a team leader dismisses a flag, that decision becomes a calibration
example injected into future prompts — the product's human workflow manufactures the
labelled data that improves the model, with zero retraining. It's deployed live: Vercel →
Railway → Neon Postgres, running real Whisper and real Gemini."

---

## §2. Business context — know the company, not just the code

- **FitNova** (the case study's fictional company): a Bangalore **fitness & wellness
  coaching** platform. People discover programs online but **enrol over the phone** — a
  tele-advisor calls the lead, understands goals/budget, books a free trial session,
  recommends a plan. **Choosing a coaching program runs on trust** (people fear wasted
  money, unrealistic promises, pushy sales), so the advisor conversation directly drives
  both **conversion and reputation**.
- **The org shape:** hundreds of advisors in **pods**, each led by a **Team Leader (TL)**,
  who roll up to a **Sales Director**. Three audiences, three needs → three dashboards.
- **The pain:** QA is manual. A TL listens to a handful of calls per advisor per week and
  coaches from memory. It doesn't scale, it's inconsistent between leaders, and most calls
  are never reviewed — so mis-selling, weak discovery, and missed follow-ups go unnoticed
  until a customer complains.
- **Branding note:** the UI is branded **SkilloVilla** (the real company this was built
  for) with a **dumbbell badge** for the fitness domain; the *data and rubric* are FitNova
  fitness (weight-loss guarantees, auto-renewal costs, trial sessions). If asked "why two
  names": the brief is FitNova; you branded it for SkilloVilla as a business-understanding
  nod. This was a deliberate mid-build **pivot** (you initially framed it as edtech, then
  re-read the PDF and corrected to fitness — see §7).

**Why this framing matters in the interview:** the compliance cap, the "team = mean over
advisors" choice, and the dispute loop are all *product opinions* that only make sense once
you've internalised "this business runs on trust and coaching, not policing." Say that
sentence and the design decisions defend themselves.

---

## §3. Architecture — the full request lifecycle

```
                 folder / REST / mock-CRM  ──(SourceAdapter)──►  CallEnvelope
                                                                     │  sha256(audio)+source = idempotency_key
                                                                     ▼
   ffprobe validation ──reject──► audit_log        ingest.service.ingest()
        (corrupt/0-length)                              │ ON CONFLICT(idempotency_key) DO NOTHING
                                                        │ resolve advisor via external_ids ? agent_ref
                                                        ▼
                                          processing_jobs  (Postgres queue)
                                          stage='transcribe', status='pending'
                                                        │  worker: SELECT … FOR UPDATE SKIP LOCKED
                                                        ▼
   ┌──────────── one worker, six stages, each idempotent, each its own DB transaction ───────────┐
   │ 1 TRANSCRIBE  faster-whisper (local, int8) → transcript + timestamped segments               │
   │ 2 DIARISE     stereo channel-split → else acoustic voice-clustering → else turn-alternation   │
   │ 3 REDACT      regex+Luhn PII → redacted_text  (LLM never sees raw)                            │
   │ 4 CLASSIFY    cheap LLM: sales? + is the advisor label correct? (swap if not); non-sales ends │
   │ 5 ANALYSE     LLM rubric+flags → quote-gate → timestamps-by-code → compliance cap → scores    │
   │ 6 VALIDATE    invariants hold? → status=done, else needs_review                               │
   └──────────────────────────────────────────────────────────────────────────────────────────────┘
                                                        ▼
             Postgres: orgs→teams→advisors→calls→transcripts→segments→scores→call_scores
                       →flags→disputes→calibration_examples→audit_log ; v_advisor/team/org_scores (views)
                                                        ▼
                 FastAPI (REST)  ◄──────────────►  Next.js (Director / TL / Advisor + call detail)
                       ▲                                    │ advisor disputes a flag → TL resolves
                       └──── recompute composite + mint calibration_example (→ future prompts) ────┘
```

**The one-sentence data-flow you must be able to recite:** *audio bytes → validated & deduped
call row → queue → transcript+segments → speaker-labelled segments → redacted segments →
(sales?) → scores+flags (quote-verified) → materialised composite → dashboards → human
dispute → recompute + calibration.*

**Two storage locations (say this precisely — a favourite probe):** the **database (Neon
Postgres)** is durable and holds every row forever; the **container's local disk** is
ephemeral (wiped on every deploy/restart) and holds only audio *files*. The DB stores a
*path* to each audio file, not the audio. That split is why demo audio is regenerated on
boot and why user-uploaded audio loses playback after a restart (rows persist; the file
doesn't). Production fix: object storage (S3/MinIO).

---

## §4. Full codebase tour — every file, why it exists, key functions & variables

Monorepo: `backend/` (FastAPI + pipeline + analysis), `frontend/` (Next.js), `demo/`
(seed + test-call generator), `scripts/`, plus infra files at the root. ~165 files in the
zip. Below is every file that carries logic; trivial `__init__.py` package markers are
omitted.

### 4.1 `backend/app/` — the API layer

- **`config.py`** — the single source of truth for configuration, via `pydantic-settings`
  (12-factor: read from env, validated at startup so a bad value fails loud at boot, not
  mid-request). `class Settings(BaseSettings)` with `model_config` `extra="ignore"`,
  `case_sensitive=False`. Every knob and *why it exists*:
  - `app_name`, `environment` (`local|docker|ci|prod`), `log_level`.
  - `database_url` — default localhost; compose/Neon override via env.
  - `worker_poll_interval_s=2.0` (how often an idle worker re-checks the queue),
    `job_max_attempts=3` (retries before dead-letter), `job_backoff_base_s=2.0`.
  - `run_inline_worker=False` — **critical for deployment**: when true the worker loop runs
    as a daemon **thread inside the API process** (single-container hosts like Railway free
    have no separate worker service); local/compose keep a dedicated worker process.
  - `mock_mode=False` — when true the whole loop uses canned fixtures, zero network (keyless
    graders). **This is the master switch** between demo-safe and real.
  - `llm_provider="gemini"` (`mock|gemini|anthropic`), `llm_temperature=0.0` (determinism —
    same call must score the same, and it's auditable).
  - `gemini_api_key`, `gemini_model="gemini-flash-lite-latest"`,
    `gemini_classifier_model="gemini-flash-lite-latest"`. **Why flash-lite:** free-tier
    flash/pro quotas 429 fast and `gemini-2.5-flash` is gated for new keys; lite has ample
    quota and handled the structured task correctly in testing. `-latest` alias so it never
    goes stale/gated.
  - `anthropic_api_key`, `llm_model="claude-sonnet-5"`, `classifier_model` — the alternative
    provider, wired but unused in the deployment.
  - `llm_min_interval_s=1.0` (process-global throttle between LLM calls — protects free
    quota), `llm_max_retries=4` (429/503 backoff attempts).
  - `whisper_model="small"`, `whisper_compute_type="int8"`, `hf_token` (optional; would
    enable pyannote). **Cloud overrides `whisper_model=base`** (Railway 1GB RAM can't hold
    small). This is the single most-asked "why base not small" — RAM, not accuracy choice.
  - `watch_folder`, `audio_storage_dir` — ingestion paths.
  - `get_settings()` is `@lru_cache`d so config parses once per process (and so tests can
    set env before first import and have it stick).

- **`main.py`** — builds the `FastAPI` app. Mounts routers (`ingest, calls, summaries,
  flags, disputes, ops`). Wide-open CORS (single-host demo; tighten to the web origin in
  prod — a known, deliberate gap). `GET /` returns metadata incl. `mock_mode` (the frontend
  reads this to decide whether to show the fixture picker). `GET /health` (liveness),
  `GET /health/db` (readiness — actually pings Postgres; used by compose/Railway health
  checks). **`@app.on_event("startup") _maybe_start_inline_worker()`** — if
  `run_inline_worker`, spawns `pipeline.worker.main` as a daemon thread. **Custom `/docs`**:
  we set `docs_url=None` and serve Swagger ourselves with a **relative** `openapi.json` URL
  so docs work both on the direct domain and through the Vercel edge proxy (FastAPI's
  default hardcodes `/openapi.json` at the domain root, which a path-prefixed proxy can't
  satisfy — see the ISP-block bug in §7).

- **`deps.py`** — FastAPI dependency providers (`get_queue()` returns a `PostgresJobQueue`);
  keeps route handlers thin and swappable/testable.

- **`schemas.py`** — Pydantic request/response models for the API (e.g. `IngestResponse`
  with `accepted, created, call_id, reason, processed_inline`). Same validation mechanism
  as the LLM-output models — *one validation story* end to end (a line worth saying).

- **`ratelimit.py`** — `class RateLimiter` (per-IP sliding window, in-memory, thread-safe
  with a `Lock`). Reads `X-Forwarded-For` first (behind Railway/Vercel proxies the real
  client is there). `upload_rate_limit = RateLimiter(max_requests=10, window_s=60)`. Raises
  429 with a `Retry-After` header. Honest scope note baked into the docstring: in-memory =
  per-process; at scale this moves to nginx `limit_req` or Redis — *the interface (a FastAPI
  dependency) stays the same.*

- **`routes/ingest.py`** — `POST /ingest/upload` (multipart). Depends on `upload_rate_limit`.
  `MAX_UPLOAD_BYTES = 200MB` (a 3-hour WAV; larger = mistake/abuse and would tie a CPU
  worker up for an hour → 413). Builds a `CallEnvelope` via `RestAdapter`, calls
  `ingest(...)`. **Two mode-aware behaviours:** (1) the `fixture` form field is ignored
  unless `mock_mode` (so a stale UI param can't mislabel a real call); (2) inline draining
  (`process=true`) only happens in mock mode — with real Whisper+LLM that would block the
  HTTP request for minutes, so the background worker owns it. Accepts `language_hint`
  (forwarded to Whisper).

- **`routes/calls.py`** — `GET /calls/{id}/audio` (streams the file with a suffix→MIME map),
  `GET /calls` (recent list with composite + flag counts), `GET /calls/{id}` (the big one:
  call meta + advisor/team join + composite, transcript row, segments with
  `COALESCE(redacted_text, text)`, scores, flags ordered by `start_s`, **and `jobs`** so the
  UI can show the pipeline stepper ticking live).

- **`routes/summaries.py`** — the dashboard data. Org/team/advisor summaries built from the
  **rollup views** (`v_org_scores`, `v_team_scores`, `v_advisor_scores`) plus KPIs (calls
  processed, critical flags this week, open disputes), trend series, risk feed, and the
  per-dimension heatmap. This is where "team = mean over advisors" physically lives (in the
  view, §4.2).

- **`routes/flags.py`** — `POST /flags/{id}/dispute` → calls `feedback.raise_dispute`; 409 on
  illegal transition (disputing a non-open flag). `routes/disputes.py` — `POST
  /disputes/{id}/resolve` → `feedback.resolve_dispute`; returns the recomputed composite.
  `routes/ops.py` — `GET /ops/jobs`: the queue's state (pending/running/done/failed/dead
  counts + recent rows) — the "how would you debug a stuck call" answer.

### 4.2 `backend/db/` — schema, session, migrations, views

- **`models.py`** — the whole relational schema (SQLAlchemy 2 `Mapped[...]` style). **13
  tables**: `orgs → teams → advisors → calls → processing_jobs → transcripts → segments →
  scores → call_scores → flags → disputes → calibration_examples → audit_log`. Things to be
  able to defend:
  - **Closed taxonomies as Python enums** rendered `VARCHAR + CHECK` via
    `_enum(py_enum) = Enum(py_enum, native_enum=False, ...)`. *Why not native PG ENUM:*
    app-side type safety **and** DB integrity, without the `ALTER TYPE` pain when a taxonomy
    grows. Enums: `CallStatus, JobStage, JobStatus, SpeakerRole, RubricDimension, FlagTag,
    FlagSeverity, FlagState, CalibrationVerdict`.
  - **`calls.idempotency_key`** — `UNIQUE`, `= sha256(audio_bytes)+source`. The double-
    delivery guard, at the DB layer (not app logic that can race).
  - **`calls.raw_metadata JSONB`** (default `{}`) — preserves the untouched vendor payload
    so a mapping bug is re-mappable without re-fetching. Also carries runtime flags:
    `fixture`, `diarisation_confidence`, `talk_ratio`, `roles_swapped`, `pii_redacted`.
    "Relational columns for what you query/join/aggregate; JSONB for what you merely
    preserve."
  - **`advisors.external_ids JSONB` array** (default `[]`) — a new dialer's agent-IDs
    UPSERT in; resolution is `external_ids ? :agent_ref`. **This is the "org grows without
    reconfiguration" requirement**, physically.
  - **`teams.team_leader_id`** → `advisors.id` with `use_alter=True` — a **circular FK**
    (a TL is themselves an advisor). `use_alter` breaks the migration ordering cycle. (This
    caused a real migration bug; §7.)
  - **`processing_jobs`**: `UNIQUE(call_id, stage)` (enqueue is idempotent), `Index(status,
    run_after)` (the exact columns the claim query filters — indexed on purpose), `attempts`,
    `max_attempts`, `last_error`, `run_after` (backoff scheduling).
  - **`scores`** carries `rubric_version` + `prompt_hash` + `model` on **every row** — scores
    are only comparable within a prompt/rubric version; prompt drift is detectable
    ("senior-engineer catnip"). `CHECK raw_score 0..5`.
  - **`call_scores`** — the *materialised* composite (one row per call, PK = call_id). *Why
    materialise:* dashboards don't recompute a weighted sum on every read; rollups above it
    are cheap views. `compliance_capped` boolean surfaces the cap in the UI.
  - **`flags`** — `tag, severity, start_s/end_s, quote, reason, confidence, state`; `CHECK
    confidence 0..1`; indexes on `call_id` and `state`.
  - **`disputes`** — `flag_id, raised_by, note, resolved_by, resolution, resolution_note,
    resolved_at`. The state-machine columns.
  - **`calibration_examples`** — `tag, quote, verdict(true/false_positive),
    source_dispute_id`. The learning-loop memory.
  - **`audit_log`** — append-only (`actor, action, entity, entity_id, before JSONB, after
    JSONB, at`). Never UPDATE/DELETE. The compliance/answerability story ("who dismissed
    this mis-selling flag and when").
- **`base.py`** — `Base` (declarative base) + `TimestampMixin` (`created_at/updated_at` with
  DB-side `func.now()`).
- **`session.py`** — engine + `SessionLocal` + `get_db()` FastAPI dependency + a `ping()`
  used by the readiness check. Sync SQLAlchemy deliberately (the API's hot path is light
  reads; heavy CPU work is in the worker, never the event loop; FastAPI runs sync handlers
  in a threadpool).
- **`views.sql`** — the three rollup views; the **source of truth** for the averaging
  policy. Key defensible details: advisor = `AVG(cs.composite)`; **critical flags counted in
  a correlated subquery, not a JOIN**, to avoid the join fan-out that would inflate the
  average when a call has multiple flags; team = `AVG(vs.avg_composite)` = **mean over
  advisors** (NULLs — advisors with no scored calls — ignored by AVG, i.e. "mean over active
  advisors"); org = mean over teams. Non-sales calls have no `call_scores` row → excluded
  from every average automatically.
- **`alembic/`** — migrations. `0001_initial_schema` (autogenerated then hand-fixed for the
  circular FK), `0002_rollup_views` (executes `views.sql`). Alembic = "schema can evolve in
  prod without hand-run SQL."

### 4.3 `backend/ingestion/` — getting calls in, source-agnostically

- **`envelope.py`** — `CallEnvelope` (Pydantic): the **canonical shape** every source
  normalises into (`source, source_call_id, advisor_external_id, org_id, customer_ref,
  audio_uri, idempotency_key, channels, duration_s, language_hint, called_at,
  raw_metadata`). `derive_idempotency_key(audio_bytes, source)` = `sha256(bytes)+":"+source`.
  Content-derived identity — same recording under two filenames still collides.
- **`validation.py`** — `probe_audio(path)` shells out to **ffprobe** (`-show_streams
  -show_format -of json`), returns `AudioInfo(channels, duration_s, codec, sample_rate)`, or
  raises `AudioValidationError` (no audio stream / zero-or-unknown duration / not
  decodable). The gate that keeps corrupt files out of the pipeline.
- **`adapters/base.py`** — `class SourceAdapter(ABC)` with the one method the pipeline
  speaks: `fetch_new() -> list[CallEnvelope]`. **This ABC is the "source-agnostic"
  requirement.** Adding Exotel/Twilio = one new file implementing this; zero pipeline
  changes.
- **`adapters/folder.py`** — polls a watch directory; optional `<file>.json` sidecar carries
  metadata; dedup handled downstream by the idempotency key. (The 25 seeded demo calls are
  `source=folder`.)
- **`adapters/rest.py`** — push/webhook style. `build(filename, content, advisor_external_id,
  org_id, language_hint, extra)` persists bytes to the store and returns an envelope.
  `fetch_new()` returns `[]` (REST is push, not polled). The upload endpoint uses this.
- **`adapters/mock_crm.py`** — proves the contract: maps a vendor-shaped payload
  (`agent_ref`, `call_uuid`, `lead_phone`, `started_at`, …) into the *same* envelope, the
  whole vendor row preserved in `raw_metadata`. Exercised in tests.
- **`service.py`** — `ingest(session, env, queue) -> IngestResult`. The four steps: (1)
  `probe_audio` → reject to `audit_log` on failure; (2) `_resolve_advisor` via `external_ids
  ? :ext` (unknown agents still ingest with `advisor_id=NULL` — never silently dropped); (3)
  `INSERT … ON CONFLICT(idempotency_key) DO NOTHING RETURNING id` (`row is None` ⇒ duplicate
  ⇒ report the existing id, don't reprocess); (4) `queue.enqueue(call_id, 'transcribe')`
  **only for a newly-created call**. `called_at` uses `COALESCE(:called_at, now())` — the
  fix for manual uploads showing a blank date.

### 4.4 `backend/pipeline/` — the queue and the worker

- **`queue.py`** — the crown jewel. `class JobQueue(ABC)` (4 methods: `enqueue, claim,
  complete, fail`) documents the SQS/Kafka swap seam. `PostgresJobQueue`:
  - `enqueue`: `INSERT … ON CONFLICT (call_id, stage) DO NOTHING` — idempotent.
  - **`claim`**: the money query — a CTE selecting one eligible job `FOR UPDATE SKIP LOCKED`
    then `UPDATE … status='running', attempts=attempts+1 … RETURNING`. Eligible = `pending
    AND run_after <= clock_timestamp()` **OR** `running AND updated_at < now - visibility
    timeout` (the second clause is **crash recovery** — a worker that died mid-stage). All in
    one atomic statement.
  - `complete`: mark `done`, then enqueue the next stage in the **same transaction** (atomic
    hand-off).
  - `fail`: if `attempts >= max_attempts` → `dead` (+`last_error`); else → `pending` with
    `run_after = clock_timestamp() + backoff_seconds(attempt)`.
  - `backoff_seconds(attempt)` = `base * 2**(attempt-1) * uniform(0.5,1.5)` — **exponential
    backoff + jitter** (jitter = thundering-herd cure).
  - `VISIBILITY_TIMEOUT_S = 300`. **All timestamps use `clock_timestamp()` not `now()`** —
    Postgres `now()` freezes at transaction start, and a stage runs *inside* the job
    transaction, so `now()` would backdate a 3-minute Whisper stage's completion (this was a
    real bug; §7).
- **`worker.py`** — `process_one(queue)`: (1) claim in its own txn, commit immediately
  (status→running, lock released — other workers skip it, a crash leaves it re-claimable);
  (2) run the stage in a second txn; on success mark done **and** enqueue next in the *same*
  txn (atomic); on any exception, roll back and `fail()` in a third txn. `run_until_idle`
  (drains the queue — used by tests and seed). `main()` — the long-running loop
  (poll+sleep). **Transaction boundaries are the thing to be able to draw.**
- **`stages/__init__.py`** — `STAGE_ORDER` (the linear happy path), `STAGES` (name→`run`
  dict), and `next_stage(current, session, call_id)` — the only branch: after `classify`, a
  non-sales call is already `done` so it terminates instead of going to `analyse`.
- **`stages/base.py`** — helpers: `load_call` (→ `CallInfo` incl. `language_hint`, `fixture`
  from raw_metadata), `load_tx_segments(redacted=?)` (→ `list[TxSegment]`, uses
  `COALESCE(redacted_text, text)` when redacted), `set_call_status`, `merge_raw_metadata`
  (JSONB `||` merge).
- **`stages/transcribe.py`** — idempotent (skip if a transcript row exists). Sets status
  `processing`, calls `get_transcriber(fixture).transcribe(audio_uri, channels,
  language=language_hint)`, writes the transcript row + all segments.
- **`stages/diarise.py`** — calls `transcription.diarize.diarise(...)`, writes speaker labels
  back, stores `diarisation_confidence` in raw_metadata (drives the low-confidence banner).
- **`stages/redact.py`** — per segment, `analysis.redaction.redact(text)` → `redacted_text`;
  aggregates the PII types found into raw_metadata.
- **`stages/classify.py`** — builds the opening (`OPENING_TURNS = 12` turns), calls
  `llm.classify(opening)` → `{sales, advisor_is}`. **Role-swap:** if `advisor_is ==
  "customer"` and not already swapped, flips all segment speakers (guarded by
  `roles_swapped` so a retry can't double-swap). If not sales → insert a `non_sales_call`
  info flag, set status `done` (terminates the pipeline).
- **`stages/analyse.py`** — the heaviest. Idempotent (skip if `call_scores` exists). Loads
  **redacted** segments, builds the transcript, loads the last-5 calibration examples, calls
  `_analyse_with_retry` (parse `AnalysisResult`; on `ValidationError` retry once then let it
  fail to dead-letter). Computes `prompt_hash = sha256(SYSTEM + user_prompt)` and the
  `model_name`. For each **dimension**: `verify_quote` → store score row (+ derived
  `evidence_start_s`). For each **flag**: `verify_quote`; **not found → drop + log** (the
  anti-hallucination gate in action); severity from `TAG_SEVERITY`; `confidence <
  CONFIDENCE_THRESHOLD (0.6)` → downgrade to `info`; **quote on a customer-labelled segment →
  downgrade to info** with an attribution note (advisor-only-flags policy); `critical` sets
  `has_critical`. Then the **deterministic talk-ratio** metric (`talk_ratio(segments)`; store
  in raw_metadata; `> 0.75` → a code-generated `talk_over_customer` info flag). Finally
  `compute_composite(dim_scores, has_critical)` → insert `call_scores`.
- **`worker.py`/stages are each their own transaction** — remember this for "how do you
  guarantee a call isn't left half-analysed?"

### 4.5 `backend/transcription/` — STT + diarisation

- **`base.py`** — `TxSegment(idx, start_s, end_s, text, speaker)` dataclass, `TranscriptResult`,
  and `class Transcriber(ABC).transcribe(audio_uri, channels, language)`. The `language`
  param docstring says it: `hi` biases decoding **and the output script** (Hindi/Urdu are
  one spoken language, two scripts — `hi` keeps output in Devanagari).
- **`factory.py`** — `get_transcriber(fixture)`: `MockTranscriber` in mock mode, else
  `FasterWhisperTranscriber(whisper_model, compute_type)`.
- **`mock.py`** — returns a canned fixture transcript (keyless demo).
- **`faster_whisper_tx.py`** — lazy-loads `WhisperModel(size, device="cpu",
  compute_type="int8")` (heavy import only when real). `transcribe`: `vad_filter=True`
  (skip silence/hold-music — faster, no lyric hallucinations), `beam_size=5`, `language=lang`
  (only if a 2-letter hint). Computes `code_switch_ratio` and a `wer_estimate` from mean
  token logprob (`1 - exp(mean_logprob)`) — a no-reference quality proxy stored per
  transcript.
- **`diarize.py`** — `diarise(audio_uri, channels, segments)`, the **cheapest-correct-first
  ladder**: (1) already-labelled? pass through; (2) stereo? `_channel_split` — per-segment
  L/R RMS energy, `left=advisor`; **with a self-audit**: if the "separation" is below
  `_STEREO_SEPARATION_MIN=0.15` OR one label swallowed nearly everything (mixed-stereo trap,
  §7), return None; (3) `acoustic_diarise` (voice clustering); (4) `_turn_fallback`
  (alternate speakers, confidence 0.5).
- **`acoustic.py`** — **the numpy-only mono diariser you built** (no gated models). Per
  segment: a **fingerprint** = 40-band mean log-mel spectral envelope (timbre/vocal-tract) +
  median F0 pitch (autocorrelation). Z-score the features, **deterministic 2-means**
  (seeded by the two most-distant points), advisor = cluster owning the call opener.
  `separation = between-centroid / within-cluster spread`; `< MIN_SEPARATION=1.15` → return
  None (voices not separable — degrade honestly, don't pretend). Reads audio `dtype=float32`
  (halves memory next to the Whisper model). **This is your best "I built a real algorithm,
  not just called an API" story — know it cold** (§8 has the concept primer).
- **`textutils.py`** — `estimate_code_switch(text)` (rough non-English token fraction).

### 4.6 `backend/analysis/` — the judgment layer

- **`rubric.py`** — `RUBRIC_VERSION="v1"`; `DIMENSION_WEIGHTS` (discovery .25, product .15,
  objection .20, **compliance .25**, next-step .15 — discovery+compliance = 50% because they
  drive FitNova's conversion+risk); `TAG_SEVERITY` (over_promising/pressure_tactics/
  undisclosed_costs = **critical**); `CRITICAL_TAGS`; `COMPLIANCE_CAP=40.0`;
  `CONFIDENCE_THRESHOLD=0.6`. **`compute_composite(scores, has_critical) -> (composite,
  capped)`**: `raw = Σ(score/5 × weight) × 100`; if `has_critical`, return `min(raw, 40)` and
  `capped = raw > 40`.
- **`schema.py`** — the LLM's forced-output Pydantic models: `DimensionScore(dimension:
  RubricDimension, score: 0..5, evidence_quote)`, `RawFlag(tag: FlagTag, quote, reason,
  confidence: 0..1)`, `AnalysisResult(dimensions, flags)`. **Enums = closed taxonomy the
  model cannot escape; Pydantic re-validates = trust-but-verify.**
- **`prompts.py`** — `SYSTEM` (role frame: meticulous sales-QA analyst for FitNova, Hinglish,
  "precise not punitive, omit if ambiguous, return ONLY JSON"). `build_analysis_user_prompt`
  inlines the rubric with **0/5 anchors**, the closed tag list, the **rules** (flags =
  advisor utterances only; quote verbatim in original language; confidence bands; don't
  invent timestamps), and **injects the last-5 calibration examples** as few-shots.
  `build_classify_prompt` returns `{sales, advisor_is}` and explicitly rules
  support/tech-support/remote-access/money-moving **scam** calls as non-sales.
- **`verify.py`** — **the quote-verification gate.** `verify_quote(quote, segments,
  threshold=0.85)`: normalise (Unicode-aware `\w` — must match Devanagari; an ASCII-only
  normaliser was the bug that dropped every real flag, §7), then a **sliding word-window**
  `difflib.SequenceMatcher` ratio over each segment; returns `QuoteMatch(found, ratio,
  segment_idx, start_s, end_s)`. Found ⇒ the flag stands and its timestamp is *this segment's*
  start (derived, not model-generated). Not found ⇒ dropped.
- **`redaction.py`** — regex PII, **order matters** (card before Aadhaar before phone so
  longer patterns win): `EMAIL`, `CARD` (13–16 digits, **Luhn-checked** so random digit runs
  aren't masked), `AADHAAR` (4-4-4), `OTP_CTX` (the word otp/code/password near 4–8 digits),
  `PHONE` (Indian 10-digit, optional +91), `PAN`. `redact(text) -> (redacted, [types])`.
  spaCy NER for names is available but gated off (avoids a model download). **Runs before
  the LLM — the privacy boundary is architectural, not policy.**
- **`metrics.py`** — `talk_ratio(segments)` = advisor speaking-time / total (None if unknown
  speakers); `TALK_RATIO_THRESHOLD=0.75`. **Computed by code, never the LLM** (rubric rule:
  arithmetic is derived, not generated).
- **`llm.py`** — `class LLM(ABC)` (`analyse`, `classify`). `MockLLM` (fixtures). `GeminiLLM`
  (google-genai `response_mime_type="application/json"` = native JSON mode; `_generate` wraps
  a **process-global throttle** (`_throttle`, `min_interval_s`) + **retry on
  429/503/RESOURCE_EXHAUSTED/overload** with exponential backoff + jitter). `AnthropicLLM`
  (forced-JSON via prompt). `get_llm(fixture)` picks by config: mock_mode wins, else
  provider, else whatever key exists, else Mock. `_parse_classify` has **safe defaults** —
  an unparseable verdict counts as *sales* (a real call is never silently unscored).
  `_extract_json` strips markdown fences.
- **`recompute.py`** — `recompute_call_score(session, call_id)`: reloads the stored dimension
  scores, checks for a **non-dismissed** critical flag (a dismissed one no longer caps),
  recomputes and updates `call_scores`. Called after a dispute resolves.

### 4.7 `backend/feedback.py` — the dispute state machine

- `raise_dispute(flag_id, note, raised_by)` — enforces `open → disputed` (409 otherwise via
  `DisputeError`), inserts a dispute row, audits.
- `resolve_dispute(dispute_id, resolution, resolved_by, note)` — enforces `disputed → upheld
  | dismissed`; updates flag state; **mints a `calibration_example`** (`upheld →
  true_positive`, `dismissed → false_positive`); calls `recompute_call_score`; audits.
  Returns the new composite so the UI updates instantly. **This function is the "how humans
  correct the system and how that loops back" requirement, literally.**

### 4.8 `backend/fixtures.py` — MOCK_MODE canned data

Five fitness scenarios (`over_promiser, good_discovery, pushy_pressure, hidden_costs,
non_sales`), each a scripted Hinglish transcript **plus** a matching analysis whose quotes
are verbatim substrings of the transcript (so the quote-gate passes in mock mode too). Both
`MockTranscriber` and `MockLLM` read these — keeping demo transcript and demo analysis
consistent. `over_promiser` is the default: it demonstrates the quote gate, PII redaction,
and the compliance cap (dimensions compute to ~68 but a critical guarantee caps to 40).

### 4.9 `frontend/` — Next.js 14 (App Router) + Tailwind + Recharts

- **`lib/api.ts`** — `API_BASE` resolver: on a `*.vercel.app` host it uses **`/api/backend`**
  (the same-origin edge proxy — the ISP-block fix); locally it uses `NEXT_PUBLIC_API_URL` or
  localhost. `uploadCall(form)` posts multipart.
- **`next.config.mjs`** — `output: "standalone"` + the **`rewrites()`** that proxy
  `/api/backend/:path*` → the Railway backend. `NEXT_PUBLIC_*` are **baked at build time**
  (a Vercel gotcha, §6).
- **`lib/useApi.ts`** — a tiny fetch hook with a `reload()` (used to refetch after a dispute)
  and polling.
- **`lib/types.ts`**, **`lib/format.ts`** — shared TS types + formatters.
- **`components/UploadCall.tsx`** — the mode-aware upload: real dropzone (drag+drop, Browse
  button, file chip), reads `mock_mode` from `GET /`, shows a language selector + REAL/DEMO
  banner, and an idempotency-dedupe banner ("already ingested as call #N"). Sends
  `language_hint`; only sends `fixture`+`process` in mock mode.
- **`components/PipelineStepper.tsx`** — the six-stage progress strip (numbered, spinner on
  running, check/skip/error, retry counts) that the call page polls into.
- **`app/director/page.tsx`, `app/team/page.tsx`, `app/advisor/page.tsx`** — the three role
  views (org health / coaching leaderboard + heatmap + dispute inbox / advisor detail).
  **The role switcher is the "authorization model without authentication" answer.**
- **`app/calls/[id]/page.tsx`** — the money screen: audio player, speaker-coloured transcript,
  flags pinned at timestamps, **click-a-flag-to-seek-the-audio**, dispute button; polls every
  2.5s while `status` is `processing` so the transcript/scores fill in live.
- **`app/about/page.tsx`** — the "How it works" explainer (pipeline, guardrails, role views,
  persistence model, upload limits) — your interviewer-facing narration, in the app.
- **`components/ui.tsx`, `Header.tsx`, `charts.tsx`, `globals.css`** — design system (cards,
  buttons with `stopPropagation` so buttons inside the dropzone don't re-trigger it, tabular
  numerals for metrics, the SkilloVilla mark + dumbbell badge).

### 4.10 `demo/`, `scripts/`, infra

- **`demo/seed.py`** — seeds 1 org / 3 teams / 9 advisors / 25 calls through the real
  (mock-mode) pipeline. `SEED_MODE` = `always` (truncate + reseed) or **`if-empty`** (only
  seed a blank DB — the deployment setting, so disputes/calibration/uploads persist).
  `regenerate_seed_audio()` — rebuilds just the 25 synthesized WAVs on a fresh container
  disk without touching rows (so demo play-buttons survive restarts). Synthetic audio =
  tiny stereo sine WAVs (distinct freqs) so idempotency keys differ.
- **`demo/make_test_calls.py`** — renders Hinglish FitNova dialogues with two neural TTS
  voices (edge-tts), stereo (advisor left / customer right) + mono variants, for uploading.
- **`scripts/localdb.ps1`** — starts the conda-provided local Postgres (`.pgdata`).
- **`Dockerfile`** (root) — the Railway/real-mode image: installs ffmpeg, bakes the Whisper
  model at build, boots `alembic upgrade head` → `seed.py` → uvicorn with the inline worker,
  `MOCK_MODE=false`. **`docker-compose.yml`** — the local 4-service stack (postgres/api/
  worker/web). **`render.yaml`** — a Render blueprint (kept as a mock-mode fallback).
  **`.github/workflows/ci.yml`** — backend tests against a `postgres:16` service + frontend
  build, every push. **`.railwayignore`, `.dockerignore`, `.gitignore`** — keep secrets/
  audio/`node_modules` out.

### 4.11 Tests (38, all green in CI)

`tests/unit/` — redaction (incl. Hinglish numbers + Luhn), quote-gate (exact / STT-noisy /
absent / **Devanagari**), rubric+compliance-cap math, idempotency-key derivation, adapter
mapping, **acoustic diarisation** (two-voice separation, single-voice→None, mixed-stereo
trap→voice-clustering), talk-ratio. `tests/integration/` — full loop writes every table,
duplicate→one call, non-sales excluded, retry→dead-letter, idempotent resume.
`tests/api/` — dispute lifecycle + recompute + the 409 state-machine guard. Conftest spins
an isolated `callsense_test` DB.

---

## §5. Every design decision + the rejected alternative (defend all of these)

| # | Decision | Why (the constraint) | Rejected alternative & why | If they push back |
|---|---|---|---|---|
| 1 | **Postgres job table + `SKIP LOCKED`** as the queue | Lean org, hundreds of calls/day; the queue is *transactional with the domain data*; idempotency + dead-letter are just columns | **Celery+Redis** (a broker service + serialization + its own failure modes; a task can fire for a rolled-back insert — not transactional). **Kafka** (a log for many producers/consumers at high volume + replay — one producer→one consumer at hundreds/day is "cosplay") | "The `JobQueue` ABC is 4 methods — swapping to SQS/Kafka touches one class. Premature infra is a liability in a 70-person company." |
| 2 | **Local faster-whisper** behind a `Transcriber` iface | ₹0/call unit economics; multilingual Hinglish; word timestamps to anchor flags; PII never leaves the box | **Cloud STT (Deepgram/AssemblyAI/Sarvam)** — better diarisation, but per-minute cost + data egress + vendor lock | "Cloud STT is a config change when accuracy demands it; **Sarvam** is my India-focused upgrade. The interface is the hedge; I'd A/B on real calls." |
| 3 | **Gemini flash-lite** as the deployed judge | Reliable free-tier quota, native JSON mode; correct on the structured task in testing | Anthropic (no key available); OpenAI; local Ollama (free but a heavy install) | "One class implements `LLM`; provider is an env var. flash/pro give higher judgment quality when quota allows." |
| 4 | **Prompting + validation, not fine-tuning** | **Zero labelled data on day one**; prompting reaches high quality immediately | Fine-tune a model — no training set exists yet | "The dispute loop *manufactures* the labelled set. The correct order is prompt → collect labels via the product → fine-tune in month 3. I never train on data I don't have." |
| 5 | **Quote-verification gate** (fuzzy match) | Engineer hallucination *away*, don't prompt it away | Trust the model; or exact-string match (STT noise breaks it) | "Prompting *reduces* hallucination; verification *eliminates its impact*. A flag whose quote isn't in the transcript is dropped — this is my answer to 'how do you stop the model inventing flags.'" |
| 6 | **Compliance cap at 40** | Averaging lets charm launder a fake guarantee to 80; in edtech/fitness one mis-sold customer costs more than ten mediocre calls | No cap (pure weighted average) | "It's a product opinion, and a correct one — it makes the org's values legible in the math. The dispute loop is the safety valve for false positives." |
| 7 | **Team avg = mean over advisors, not calls** | One high-volume advisor shouldn't dominate a team's number; the fair unit for coaching is the person | Mean over all team calls (simpler) | "Both are defensible; defending the choice matters more than the choice. Coaching compares people." |
| 8 | **Timestamps derived by code, not the model** | LLMs are bad at arithmetic; timestamps must be trustworthy | Let the model emit timestamps | "The model returns the quote; my code locates it in the segments and attaches the seconds." |
| 9 | **Confidence threshold → info** (`<0.6`) | Precision over recall: a false accusation destroys advisor trust faster than a miss destroys QA value | Surface everything | "Every ambiguous case degrades to `info` for review, never to a surfaced `critical`." |
| 10 | **VARCHAR+CHECK enums, not PG ENUM** | App-side type safety + DB integrity **without `ALTER TYPE` pain** as taxonomies evolve | Native PG ENUM (stronger, but rigid) | "Taxonomies grow; I don't want a migration to add a tag value." |
| 11 | **Materialised `call_scores` + rollup views** | Dashboards read a number, not recompute a weighted sum; rollups are consistent by construction | Store aggregates (drift); or compute everything on read (slow at scale) | "Views are always consistent and cheap here; materialise the *rollups* past ~1M calls/quarter — documented, not built." |
| 12 | **Role switcher, not auth** | Auth/SSO is out of scope for a take-home; the switcher shows the *authorization model* (what each role sees) | Build real sessions/SSO | "RBAC lives at the API layer via role-scoped queries; authentication is the plumbing I skipped, deliberately." |
| 13 | **Sync SQLAlchemy** | The API's hot path is light reads; heavy CPU (Whisper) is in the worker, never the event loop | Async everywhere | "FastAPI runs sync handlers in a threadpool; async adds complexity for a health-check-shaped read path. Async engine can drop in later." |
| 14 | **Inline worker thread option** | Free single-container hosts (Railway) have no separate worker service | Always a separate worker | "`RUN_INLINE_WORKER` — compose/local run a real worker process; one flag." |

**Out of scope, said out loud (this earns points):** live telephony (the adapter interface
shows exactly where Exotel/Twilio plug in); real-time during-call coaching (batch/near-real-
time is the right v1); fine-tuned models; auth/SSO; Kubernetes/Kafka; pyannote diarisation
(HF-gated — the numpy clusterer + documented upgrade path instead); a golden-set `make eval`
(documented roadmap); object storage for audio (S3 — the ephemeral-disk fix).

---

## §6. The deployment story — every service, limit, and gotcha

**Topology:** `Browser → Vercel (Next.js, edge-proxies /api/backend/*) → Railway (Docker:
FastAPI + inline worker, Whisper base, Gemini) → Neon (Postgres)`. Laptop can be off.

**Why this exact stack (and the graveyard of what didn't work):**
- **Neon** = free serverless Postgres (Singapore region). Connection string needs the
  `postgresql+psycopg://` prefix (SQLAlchemy driver). Migrations applied from the laptop;
  they also run on every boot.
- **Railway** for the backend, chosen after two dead ends:
  - **Hugging Face Spaces** was the first pick (free 16GB fits Whisper `small`) — **blocked
    at deploy: HF now requires PRO for Docker Spaces on cpu-basic.**
  - **Render** free tier is **512MB** — can't hold Whisper (needs ~2GB); it would only run
    mock mode, which you (rightly) rejected as "not the real thing."
  - **Railway trial**: **$5 one-time credit, no credit card**, ~2 weeks always-on, then just
    *stops* (no surprise billing). Trial RAM is **1GB** → **Whisper `base`** in the cloud
    (`WHISPER_MODEL=base`; local/video keep `small`). This is the single most likely "why is
    the cloud transcription worse" question — **RAM limit, not a quality decision.**
- **Vercel** for the frontend. Root Directory = `frontend`. `NEXT_PUBLIC_API_URL` baked at
  build time.

**The gotchas you personally hit and fixed (great "tell me about a hard bug" material):**
1. **Railway `PORT`**: Railway injects `PORT=8080` but the public domain targeted 7860 →
   502s. Fixed by pinning `PORT=7860`.
2. **Vercel build "Blocked"**: Hobby plan refuses deploys whose commit author isn't a
   project member; your commits were authored with an email not on your GitHub account →
   switched author to `Aaryansm11@users.noreply.github.com`.
3. **Vercel login wall**: Deployment Protection defaults to protecting production → disabled
   it for the public demo.
4. **`NEXT_PUBLIC_*` not applied**: they're inlined at *build* time — setting the var then
   *redeploying* is required; just saving it does nothing. (Added a diagnostic error state
   that prints which API base the build actually contains.)
5. **The big one — Indian ISPs block Railway DNS.** The live site died on your desktop
   *and* mobile. Diagnosis: Google/Cloudflare/Quad9/OpenDNS all resolve
   `callsense-production-….up.railway.app`; your ISP's resolver returns **REFUSED** — Jio/
   Airtel block `*.up.railway.app` wholesale. **Fix: a same-origin proxy** — a Next.js
   `rewrite` sends `/api/backend/*` to Railway *from Vercel's edge* (which sits outside
   Indian ISPs), so the browser only ever resolves `vercel.app`. **Consequence:** uploads now
   ride the proxy, which caps request bodies at **~4.5MB** (≈4 min of MP3). Direct-to-API is
   still 200MB.
6. **Swagger through the proxy**: FastAPI's default `/docs` hardcodes `/openapi.json` at the
   domain root, which the path-prefixed proxy can't serve → custom `/docs` with a **relative**
   openapi URL.
7. **Ephemeral disk vs the learning loop**: the container reseeded with a full TRUNCATE on
   every deploy — which would erase disputes and calibration examples (the loop's memory).
   Fixed with `SEED_MODE=if-empty` (persist everything) + `regenerate_seed_audio()` (rebuild
   only the demo WAVs so play-buttons survive). **Say this one — it shows you caught a
   correctness bug in your own persistence model.**

**Local dev without installs (worth mentioning as resourcefulness):** no Docker/Node/
Postgres were installed on the machine — **Postgres runs from a conda env**, Node from a
second conda env. That's how the whole thing was built and verified.

---

## §7. Every bug we hit and fixed — root cause → fix → the lesson

These are gold for "tell me about a bug" and for proving the system was *actually run*, not
just written.

1. **Circular-FK migration** — `teams.team_leader_id → advisors` and `advisors → teams` is a
   cycle; Alembic autogenerate emitted an inline FK that referenced a not-yet-created table.
   *Fix:* `use_alter=True` + a separate `op.create_foreign_key` after both tables exist.
   *Lesson:* autogenerated migrations need review; circular FKs are real.
2. **Quote-gate dropped every real flag (Devanagari)** — the normaliser was ASCII-only
   (`[^a-z0-9 ]`), so a Hinglish quote in **Devanagari** normalised to empty and never
   matched → every real-mode flag silently dropped. *Fix:* Unicode-aware `\w` normalisation +
   Devanagari regression tests. *Lesson:* i18n assumptions hide in "harmless" regexes; the
   mock path (Latin text) masked it.
3. **"Dummy analysis" on re-upload** — re-uploading identical bytes hit the idempotency guard
   and silently opened the *old* (mock-era) call. *Fix:* an explicit "already ingested as
   call #N" banner. *Lesson:* idempotency is correct, but *silent* dedupe confuses users;
   surface it.
4. **Impossible stage timings** — Postgres `now()` freezes at transaction start; a stage runs
   inside the job txn, so a 3-min Whisper stage recorded ~0s. *Fix:* `clock_timestamp()`
   throughout the queue. *Lesson:* know your DB's time-function semantics.
5. **`scores.model` mislabelled** — the stored model name came from the wrong config field
   (said `claude-…` when Gemini scored). *Fix:* provider-aware model stamping.
6. **CI red** — `python-multipart` (FastAPI's form parser) was installed locally but never
   pinned. *Fix:* pin it. *Lesson:* "works on my machine" ≠ pinned; CI caught it.
7. **numpy/soundfile unpinned** — the diariser imported them but requirements didn't list
   them → Docker/CI would crash at import. *Fix:* pin + split real-mode extras into
   `requirements-real.txt`.
8. **"Hello-first = advisor" heuristic failed** — a real scam call where the *victim*
   answered first mislabelled everyone. *Fix:* the classifier now returns `advisor_is` from
   *content* and the pipeline swaps labels if they're backwards. *Lesson:* positional
   heuristics break on real data; use content.
9. **Customer got flagged for the advisor's over-promise** — on single-voice test audio the
   diariser had nothing to separate, so a violating line landed on a "customer" segment.
   *Fix (two layers):* prompt rule (flags = advisor utterances only) + code guard (a flag on
   a customer-labelled segment degrades to `info` with an attribution note).
10. **Scam call scored as sales** — a messy `base` transcript flipped a borderline
    classification. *Fix:* the classifier prompt explicitly rules support/remote-access/
    money-moving calls non-sales.
11. **Urdu-script transcript** — `base` Whisper, un-hinted, rendered Hinglish in Perso-Arabic
    script. *Fix:* `language_hint` flows into Whisper (`language="hi"` ⇒ Devanagari) + an
    upload language selector.
12. **Mixed-stereo diarisation trap (live call 26)** — a stereo MP3 with *both* voices on
    *both* channels and a constant left-bias made every segment "left-heavier" → channel-
    split labelled all 30 segments "advisor" with false 0.83 confidence, and voice clustering
    never ran. *Fix:* channel-split now self-audits — a genuine two-party split must yield
    **both** speakers; a one-sided result is treated as mixed stereo and falls through to
    voice clustering. Regression test recreates the exact failure. *Lesson:* a confident
    wrong answer is worse than a humble "I'm not sure" — sanity-check your own outputs.
13. **Blank call date** — manual uploads carry no vendor `called_at` → "—" in the list.
    *Fix:* `COALESCE(:called_at, now())` at ingest.
14. **README said Anthropic** — stale after the Gemini pivot. *Fix:* corrected to Gemini
    (Anthropic behind the same interface). *Lesson:* docs drift; keep them honest.
15. **Committed upload audio** — uploads land under `backend/` when the API runs from there;
    the root `.gitignore` didn't cover it. *Fix:* untrack + ignore. *Lesson:* path-relative
    ignores.

---

## §8. Fundamentals cheat-sheet (the concepts they'll probe)

Be able to explain each in 2–3 sentences, then go one level deeper if pushed.

- **`SELECT … FOR UPDATE SKIP LOCKED`** — `FOR UPDATE` row-locks the selected rows inside a
  transaction; `SKIP LOCKED` means "don't wait for rows another worker holds — skip them and
  take the next free one." Result: N workers each atomically claim a *distinct* job with no
  Redis/Celery. Without `SKIP LOCKED` they'd serialize (block on the same row); without `FOR
  UPDATE` two workers could grab the same job.
- **Idempotency** — an operation that's safe to do twice. Two levels here: (1) ingest —
  `sha256(audio)+source` UNIQUE, so re-delivery = one row; (2) each stage skips if its output
  exists, so a crashed-then-resumed worker doesn't duplicate. Critical because in distributed
  systems retries and re-deliveries are *normal*, not exceptional.
- **Exponential backoff + jitter** — retry wait grows `base·2ⁿ` (gives a struggling vendor
  room to recover); jitter (±50% randomness) prevents the "thundering herd" where 100 failed
  jobs all retry at the same instant and re-overload the service. Implemented via a
  `run_after` timestamp the claim query respects.
- **Dead-letter** — after `max_attempts`, a job parks as `dead` with its last error instead
  of retrying forever or vanishing. Visible + re-queueable. "Failure is visible and
  recoverable, never silent — that's the difference between a demo and a system."
- **Visibility timeout / crash recovery** — a `running` job whose `updated_at` is older than
  the timeout is assumed crashed and re-claimable. Stage idempotency makes the re-run safe.
- **Transactions / ACID** — "write flags + write scores + mark job done + enqueue next" is
  one transaction: a crash between them can't leave a call half-analysed. Atomicity is the
  property; the SKIP-LOCKED lock also lives inside a transaction.
- **Whisper / ASR** — an encoder-decoder Transformer: audio → mel-spectrogram → the encoder
  ingests 30s chunks, the decoder generates text tokens like an LLM. Trained on 680k hours
  incl. many languages + code-switched speech → handles Hinglish. Sizes tiny→large trade
  accuracy for speed/RAM. **`base` vs `small`:** smaller model, less RAM (why the cloud uses
  it), lower accuracy — a dial, not a ceiling.
- **int8 quantisation** — store weights as 8-bit ints instead of 32-bit floats: 4× smaller,
  faster on CPU (SIMD integer math + less memory bandwidth), ~negligible accuracy loss.
- **VAD (voice activity detection)** — classify frames as speech/not-speech; skip silence and
  hold-music so Whisper is faster and doesn't hallucinate lyrics over music.
- **Diarisation** — "who spoke when." Pipeline: VAD → **speaker embeddings** (a vector per
  speech chunk capturing pitch/timbre so the same voice → nearby vectors) → cluster. Your
  numpy version: the "embedding" is a **log-mel spectral envelope + pitch** fingerprint;
  clustering is **2-means**; separation score gates honesty.
- **Embeddings / cosine similarity** — a learned map from a complex object (voice clip, word,
  sentence) to a vector, arranged so similar things get nearby vectors; similarity = the
  cosine of the angle between vectors (length-invariant, so a loud and quiet clip of the same
  voice still match). Same idea powers semantic search.
- **Mel spectrogram** — a 2D image of audio (x=time, y=frequency warped to human hearing,
  brightness=loudness). What audio models actually "see."
- **Structured output / forced JSON / tool use** — the API constrains sampling so only
  schema-valid tokens can be produced (an enum field literally can't emit an out-of-set
  value). Gemini's `response_mime_type=application/json` is this. Then Pydantic re-validates
  on your side (trust but verify).
- **Temperature 0** — always pick the most-likely next token: deterministic, so the same call
  scores the same and results are auditable. High temperature = creative but useless for a QA
  system that must be consistent.
- **Fuzzy string matching / Levenshtein / SequenceMatcher** — approximate equality tolerant
  of small edits; a 0–1 ratio. Needed because STT is noisy — the model quotes "guaranteed
  placement hai" and the transcript says "guranteed placment hai"; exact match fails, fuzzy
  (≥0.85) passes.
- **Luhn checksum** — the mod-10 digit check valid card numbers satisfy; lets the card regex
  reject random 16-digit strings (fewer false redactions).
- **In-context learning / few-shot** — putting labelled examples in the prompt so the model
  imitates the pattern, no weight change. The calibration loop injects
  `(quote, verdict)` pairs — the system improves precision from human feedback with zero
  training.
- **Fine-tuning vs prompting** — fine-tuning updates the model's weights on labelled data
  (needs thousands of examples); prompting changes only the input, model frozen. You chose
  prompting because there's no data on day one; the dispute loop generates the future
  fine-tuning set.
- **Precision vs recall** — precision = of the flags raised, how many are correct
  (TP/(TP+FP), "when it accuses, is it right?"); recall = of the real violations, how many
  were caught (TP/(TP+FN), "does it miss things?"). Stricter thresholds raise precision, lower
  recall. You chose **precision** (a false accusation costs trust; a miss costs one data
  point).
- **WER** — word error rate = (subs+ins+dels)/reference words; you store a per-transcript
  `wer_estimate` from Whisper's own token confidence since there's no reference in
  production.
- **Materialised view** — a view whose result is physically stored + refreshed on demand
  (vs a plain view, recomputed every read). Your rollups are plain views now; materialise
  past ~1M calls/quarter.
- **Window functions** — compute over a window of related rows without collapsing them
  (unlike GROUP BY); powers per-advisor rolling averages/rank for sparklines.
- **JSONB** — binary JSON in Postgres, indexable and queryable; the `?` operator tests key/
  element existence (`external_ids ? :agent_ref`). "Relational columns for what you query;
  JSONB for what you preserve."
- **12-factor config** — config from the environment, validated at boot; same image runs in
  demo/prod with different env; secrets never in git.

---

## §9. Anticipated project questions + model answers

**"Walk me through what happens when a call comes in."** → recite the §3 lifecycle: envelope
→ validate+dedupe → queue → 6 stages (name each + one clause) → DB → dashboards → dispute →
recompute. 45 seconds, no notes.

**"How do you stop the LLM from inventing flags?"** (the #1 question) → "Five layers:
(1) closed enum — it can't emit a tag that isn't in the set; (2) forced JSON + Pydantic
re-validation, one retry then dead-letter; (3) the quote gate — every flag must carry a
verbatim quote that fuzzy-matches the transcript ≥0.85, else it's dropped and logged;
(4) timestamps derived by my code from the matched segment, not the model; (5) a confidence
threshold that degrades shaky flags to info. Prompting reduces hallucination; verification
eliminates its impact."

**"Why Postgres for the queue and not Kafka/Celery?"** → decision #1 in §5 verbatim. End with
"the interface is 4 methods; the swap is one class."

**"How do you know the scores are right?"** → "I don't assume; I constrain and measure.
Closed schema, quote-verified evidence, confidence thresholds, `rubric_version`+`prompt_hash`
on every score so I can re-score history and detect prompt drift, and the roadmap is a
golden-set eval reporting per-tag precision/recall. And the dispute loop is continuous human
labelling."

**"What breaks first at 10× scale, and your fix order?"** → "Whisper on CPU. Fix order: GPU
worker pool → managed STT (Sarvam) for overflow → then the queue (Postgres holds well past
10k jobs/day) → materialise the rollup views. **No schema change** in any of these — that's
the point of the design."

**"Why does the cloud transcription look worse than local?"** → "RAM. The Railway trial is
1GB; Whisper `small` needs ~2GB, so the cloud runs `base`. It's `WHISPER_MODEL=base` — one
env var from `small` on a paid instance, and the plan's production answer is managed Hinglish
STT. Quality is a dial behind the `Transcriber` interface, not a rewrite."

**"How is the composite computed?"** → "Two LLM steps and one code step: the model scores five
weighted dimensions 0–5 each with an evidence quote; my code computes `Σ(score/5 × weight) ×
100`; then a compliance cap — any critical flag caps it at 40. Discovery and compliance are
25% each because they drive FitNova's conversion and risk."

**"Why cap at 40? Isn't that harsh?"** → "That's the point. Averaging lets a smooth talker who
promises a fake guarantee still score 80. In a trust business, one mis-sold customer costs
more than ten mediocre calls, so the cap makes the org's values legible in the math. The
dispute loop is the safety valve — dismiss the flag and the cap lifts on recompute."

**"How does human feedback change the model without retraining?"** → the calibration-loop
answer: dismiss → `false_positive` calibration example → injected as a few-shot into the next
analysis prompt for that tag → precision tightens. "The product's human workflow manufactures
the labelled data; it's in-context learning, not training."

**"Source-agnostic — prove it."** → "One `SourceAdapter` ABC (`fetch_new → CallEnvelope`),
three implementations (folder/REST/mock-CRM), the vendor payload preserved in `raw_metadata
JSONB`, and advisor IDs resolved via `external_ids ? agent_ref` so a new dialer UPSERTs its
agent IDs with no code change. Exotel is one new file."

**"Where's the data stored?"** → "Neon Postgres (durable, all rows). The container disk is
ephemeral and holds only audio files; the DB stores paths. That's why I regenerate demo audio
on boot and why object storage (S3) is the production fix for user-upload playback."

**"Your diariser — is that a library?"** → "No, I wrote it: per-segment voice fingerprints —
a 40-band log-mel spectral envelope plus median pitch from autocorrelation — z-scored and
2-means clustered, advisor = the cluster owning the call opener, with a separation score that
returns 'not separable' rather than guessing. pyannote is the production upgrade but it's
HF-gated, so a demo can't depend on it."

**"Tell me about a hard bug."** → pick the **ISP DNS block** (§6.5) or the **mixed-stereo
diarisation trap** (§7.12) — both show real debugging with a diagnosis step, not a guess.

---

## §10. AI-solutioning / scenario questions (how you'd build X)

They'll pose a new problem and watch how you decompose it. Use a consistent frame:
**clarify the goal → data & sources → pipeline stages → where AI fits vs plain code →
reliability/guardrails → how you'd measure it → what you'd cut for v1.** Practice on:

- **"Automate resume screening for a recruiter."** Ingest (ATS/email/upload adapters) →
  parse (layout-aware extraction, not naive PDF-to-text) → **structured extraction with a
  closed schema** (skills/years/titles as enums; verify each claim against a span in the doc,
  same as your quote gate) → score against a role rubric → rank with explanations →
  human-in-the-loop override that becomes calibration data. Guardrails: bias auditing, never
  auto-reject, keep the evidence span. Measure: precision@k vs recruiter decisions.
- **"Detect fraud in support-chat transcripts."** Cheap classifier cascade first (most chats
  aren't fraud — don't burn tokens), then a scored analysis with **quote-anchored** signals,
  a confidence threshold, and a human review queue whose decisions retrain the cascade.
  Emphasise precision (false fraud accusations are costly) and an audit log.
- **"Summarise 2-hour meetings."** This is where you say **map-reduce**: chunk with overlap →
  per-chunk extraction → a reduce step that dedupes/merges; note the trade-off (cross-chunk
  context loss — a decision reversed in chunk 6). For sales calls you *didn't* need it (99%
  are <30 min, fit one context window) — knowing *when* to reach for it is the signal.
- **"Build a RAG assistant over company docs."** Chunk → embed → vector store (pgvector/HNSW)
  → retrieve top-k → generate **with citations** → verify the answer's claims against the
  retrieved spans (again: quote-or-it-didn't-happen). Failure modes: stale index, retrieval
  miss, hallucinated citation — mitigations for each.
- **General principle to voice:** "Cheap model filters, expensive model runs only when it's
  worth it (the cascade); the LLM proposes, code verifies; every AI output that reaches a
  human decision carries its evidence; and the human's correction is captured as future
  training data." That's the CallSense philosophy, transferable to any of these.

---

## §11. Where it fails — say these before they find them

- **Same-pitch, same-gender voices on mono audio** defeat the lightweight clusterer; it
  degrades to low-confidence turn-alternation (banner shown) and the content check re-orients
  roles, but labels can still be wrong. Fix: pyannote / diarising cloud STT.
- **Noisy/accented audio on `base` Whisper** mishears more; Hinglish code-switching, telecom-
  band audio, and brand words are exactly where small ASR degrades. Fix: bigger model /
  Sarvam.
- **Implicit mis-selling** — sarcasm, soft pressure spread across turns, violations with no
  single quotable line — can slip a quote-anchored rubric. The confidence threshold + dispute
  loop bound the damage; the golden-set eval would measure the gap.
- **Borderline classification** — a scam call reads structurally like a sales call; a cheap
  classifier will sometimes be wrong both ways.
- **Ephemeral audio in the cloud** — rows persist, uploaded audio files don't survive a
  restart. S3 is the answer, out of demo scope.
- **No auth, open CORS, in-memory rate limiter** — deliberate take-home scope; each has a
  named production upgrade.

---

## §12. Numbers to have on the tip of your tongue

- **~5%** of calls reviewed manually today → **100%** with CallSense.
- **13** tables; **6** pipeline stages; **5** rubric dimensions; **9** issue tags; **3**
  critical tags; **38** tests.
- Weights: discovery **.25**, product **.15**, objection **.20**, compliance **.25**,
  next-step **.15**. Compliance cap **40**. Confidence threshold **0.6**. Quote-gate **0.85**.
  Talk-ratio **0.75**. Job max-attempts **3**. Visibility timeout **300s**. LLM throttle
  **1 rps**.
- Whisper `small` int8 ≈ **3.3× real-time** on CPU (an 11.5-min call → **3m32s**); cloud
  `base` ≈ **1× real-time**. **~300–400** five-minute calls/day/worker; **~500+** calls/day
  inside the free LLM quota.
- Upload limits: **~4.5MB** via the live site (Vercel proxy) · **200MB** direct API ·
  **10 uploads/min/IP**.
- Deploy: Vercel (free) → Railway (**$5** trial credit, **1GB** RAM) → Neon (free, 0.5GB).

---

## §13. The prep plan (what to do before the interview)

**Day-by-day (compress if you have less time):**
1. **Read this doc twice.** First pass for coverage, second pass drilling §5 (say each "why
   not" aloud) and §9 (answer each question out loud, timed).
2. **Re-run the loop yourself once, end to end**, on the live site *and* locally — upload,
   watch stages tick, click a flag to seek, dispute it, dismiss as TL, watch the recompute.
   Muscle memory beats recall.
3. **Trace one file per subsystem in the editor** while narrating: `queue.py` (the claim
   query), `analyse.py` (the quote-gate loop), `acoustic.py` (the fingerprint→2-means),
   `feedback.py` (the state machine), `views.sql` (the averaging). If you can narrate these
   five, you can defend the whole system.
4. **Whiteboard the architecture from memory** (the §3 diagram) — twice, until it's automatic.
   Then whiteboard the **worker's three transaction boundaries** and the **SKIP-LOCKED claim**.
5. **Drill fundamentals (§8) as flashcards** — especially SKIP LOCKED, idempotency,
   diarisation/embeddings, structured output, precision/recall, fine-tuning vs prompting.
6. **Prepare your "hard bug" story** (ISP DNS block or mixed-stereo trap): situation → how you
   diagnosed (the evidence step — 4 resolvers vs local REFUSED; 30-of-30 "advisor" with false
   confidence) → the fix → the lesson.
7. **Prepare 3 questions to ask them** (shows seniority): "What does your call-QA stack look
   like today?"; "Where does the current system's precision hurt the most — false accusations
   or misses?"; "How do you think about the build-vs-buy line for STT and LLM providers?"

**Mock-question rapid-fire (answer each in ≤30s, out loud):** Why SKIP LOCKED? · Why not
Kafka? · How do you dedupe? · What if a worker crashes mid-stage? · How do timestamps get
onto flags? · Why cap at 40? · Team-average over what? · Why base not small? · How does a
dismissed flag change future scores? · Where does the LLM run and what does it never see? ·
What breaks at 10×? · Where does the system fail?

**The meta-message to leave them with:** *"Every hard part is boring on purpose — idempotency,
queue semantics, the quote gate, the compliance cap. The AI is one swappable stage behind an
interface; the engineering is making its output trustworthy and the failure modes visible.
And every quality ceiling is a config change, not a rewrite."*

Good luck — you built this, you can defend it.
