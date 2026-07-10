# CallSense — Sales-Call Intelligence for FitNova (SkilloVilla)
### 0→1 Build Plan · 48-Hour Take-Home · Aaryan S. Maralihalli

---

## 0. The One-Paragraph Thesis

Every FitNova sales call is automatically ingested from any source, transcribed and diarised,
scored against a 5-dimension rubric by an LLM that must quote its evidence, flagged for
mis-selling risk with timestamps, stored in Postgres, and surfaced on three role-specific
dashboards (Director / Team Leader / Advisor) with a human dispute loop that feeds corrections
back into the system. One `docker compose up`, seeded demo data, one real call through the full
loop live in the video.

**Why this wins:** SkilloVilla is a lean (~70-person) edtech running tele-sales enrollment with
BDAs. Manual call QA doesn't scale, and mis-selling is the #1 reputational risk in Indian edtech.
This project is not a toy — it is the internal tool their sales org actually needs. Build it so a
committee of founders + senior engineers sees: correct architecture, honest trade-offs, real
working loop, and a candidate who understood *their* business, not just the PDF.

---

## 1. Company Research → Design Decisions

| Research finding | Design decision it drives |
|---|---|
| SkilloVilla sells career-upskilling programs via tele-advisors (BDAs); trial session ≈ free counseling call | Rubric weights **needs discovery** and **trial booking** heavily — those drive their conversion |
| Lean team (~70 people, down ~59% YoY), seed-stage, revenue ₹7.77Cr | System must be **cheap to run** (per-call cost matters; local Whisper > paid STT; small LLM where possible) and **low-ops** (docker compose, no Kubernetes cosplay) |
| Indian edtech mis-selling reputation problem ("guaranteed placement", hidden loan/EMI costs) | Compliance tags are **severity-critical** and surfaced first; the dispute loop exists so advisors trust the system instead of gaming it |
| Bangalore sales floor → heavy Hinglish code-switching | Whisper (multilingual) over English-only STT; prompt handles code-switched quotes verbatim |
| CTO is ex-Swiggy tech lead | Expect cross-questioning on **idempotency, queues, failure modes, data modeling** — not on which LLM is trendy. Depth of the boring parts wins |
| Assignment explicitly grades "working prototype in a real database, surfaced" | Ship the loop end-to-end before polishing anything |

---

## 2. Scope

### In scope (MVP — must work end-to-end)
1. **Ingestion**: watch-folder + REST upload endpoint, both normalizing into one canonical
   `CallEnvelope` via a source-adapter interface. One mock CRM adapter to prove source-agnosticism.
2. **Transcription + diarisation**: faster-whisper (local) + speaker separation; advisor/customer
   role assignment heuristic.
3. **Analysis engine**: LLM scoring on 5 rubric dimensions + issue-tag extraction with
   timestamp + verbatim quote + reason + severity + confidence. Structured JSON output,
   schema-validated, quote-verified against the transcript (anti-hallucination gate).
4. **Storage**: Postgres. Full relational model: org → teams → advisors → calls → transcripts →
   segments → scores → flags → disputes → audit log.
5. **Surfacing**: Next.js dashboard, three views by role. Org health, team drill-down, advisor
   call detail with audio-synced transcript and flags.
6. **Feedback loop**: advisor disputes a flag → TL resolves → flag state changes → scores
   recompute → resolved disputes become few-shot calibration examples for the prompt.
7. **Pipeline reliability**: job queue, retries with backoff, idempotency keys, per-stage status,
   dead-letter state.

### Deliberately out of scope (and say so — this earns points)
- Live telephony integration (Exotel/Knowlarity/Twilio) — the adapter interface shows exactly
  where it plugs in; mocked with the folder/REST sources.
- Real-time (during-call) coaching — batch/near-real-time is the right v1.
- Fine-tuned models — prompt + validation gets you 90% at 1% of the effort; note fine-tuning as
  the roadmap once dispute data accumulates.
- Auth/SSO — role switcher in the UI instead; explain that RBAC lives at the API layer stub.
- Kubernetes, Kafka — docker compose + Postgres-backed queue is honest for this scale; document
  the swap path (queue interface → SQS/Kafka).

---

## 3. Architecture

```
                        ┌─────────────────────────────────────────────┐
  SOURCES               │              INGESTION LAYER                │
  ┌──────────┐          │  ┌──────────────┐   ┌────────────────────┐  │
  │ Folder    │─watch──▶│  │ SourceAdapter │──▶│ CallEnvelope       │  │
  │ REST API  │─POST───▶│  │ (ABC)         │   │ (canonical schema) │  │
  │ Mock CRM  │─poll───▶│  │ folder/rest/  │   │ + idempotency key  │  │
  └──────────┘          │  │ crm adapters  │   │ = sha256(audio)+src│  │
                        │  └──────────────┘   └─────────┬──────────┘  │
                        └───────────────────────────────┼─────────────┘
                                                        ▼
                        ┌───────────────────────────────────────────────┐
                        │  PIPELINE (worker + Postgres-backed job queue)│
                        │  stage 1: TRANSCRIBE  (faster-whisper)        │
                        │  stage 2: DIARISE     (speaker turns + roles) │
                        │  stage 3: REDACT      (PII regex+NER pass)    │
                        │  stage 4: CLASSIFY    (sales vs non-sales)    │
                        │  stage 5: ANALYSE     (LLM rubric + tags)     │
                        │  stage 6: VALIDATE    (schema + quote check)  │
                        │  each stage: status row, retry w/ backoff,    │
                        │  idempotent (skip if stage output exists)     │
                        └──────────────────┬────────────────────────────┘
                                           ▼
                        ┌──────────────────────────────┐
                        │  POSTGRES                    │
                        │  orgs teams advisors calls   │
                        │  transcripts segments scores │
                        │  flags disputes audit_log    │
                        │  processing_jobs             │
                        └───────┬──────────────────────┘
                                ▼
                 ┌────────────────────────────┐     ┌───────────────────┐
                 │ FastAPI (REST, role-aware) │◀───▶│ Next.js dashboard │
                 └────────────────────────────┘     │ Director/TL/Advsr │
                                ▲                   └───────────────────┘
                                │ dispute → resolve → recompute →
                                └── few-shot calibration examples ──▶ ANALYSE prompt
```

**The automation-value prioritisation (asked explicitly in section A):**
1. **Transcription + diarisation** — converts 100% of unheard calls into reviewable text.
   Highest leverage: without it nothing else exists. TLs go from hearing ~5% of calls to 100%.
2. **Issue flagging** — mis-selling caught the same day instead of at customer-complaint time.
   Direct revenue/reputation protection.
3. **Scoring/rollups** — makes coaching consistent across TLs and comparable across pods.
4. **Dashboards** — replaces the TL's memory-based coaching with evidence.
5. **Dispute loop** — lowest immediate time-saving, but it's what makes advisors *accept* the
   system; without trust, adoption dies. (Say this in the video — it shows product thinking.)

---

## 4. Tech Stack (with the defense you'll give in the interview)

| Layer | Choice | Why (your defense) | Rejected alternative & why |
|---|---|---|---|
| Language | Python 3.11 | ML ecosystem; your strongest language; every repo on your GitHub proves it | Node for pipeline — weaker audio/ML libs |
| API | FastAPI | Async, Pydantic validation is *the same mechanism* used to validate LLM output — one validation story end to end; you've shipped it (SDIS) | Flask (no native async/validation), Django (ORM+admin overkill for 48h) |
| STT | **faster-whisper** (`small`/`medium`, int8, CPU-friendly) | Local = ₹0 per call (SkilloVilla is lean), multilingual (Hinglish), word timestamps for flag anchoring | Cloud STT (Deepgram/AssemblyAI/Sarvam) — better diarisation but per-minute cost + vendor lock; expose it as a pluggable `Transcriber` interface and mention Sarvam AI as the India-focused upgrade path |
| Diarisation | pyannote 3.1 if HF token present; **energy/turn-based fallback** otherwise | Graders may not have a HF token — the demo must never depend on a gated model. Fallback = channel split for stereo, pause+embedding turn segmentation for mono | WhisperX — great but heavy install; mention it as the production choice |
| LLM | Claude (Anthropic API) w/ **tool-use/JSON-schema forced output**; `LLM` interface so OpenAI/local Ollama swap in one class | Structured output natively, strong on nuanced judgment (rubrics), long transcripts in one shot | Fine-tuned local model — no training data yet; roadmap item fed by dispute corrections |
| Queue | **Postgres-backed job table** (`SELECT ... FOR UPDATE SKIP LOCKED`) + worker process | One less service; transactional with the data it processes; idempotency and dead-lettering are just columns; honest for hundreds of calls/day | Celery+Redis (more moving parts than the scale justifies), Kafka (you know it — say "Kafka is for when producers/consumers multiply; here it's cosplay"). The `JobQueue` interface documents the SQS/Kafka swap |
| DB | Postgres 16 | Relational fits org hierarchy + rollups; JSONB for raw vendor payloads = source-agnostic without schema churn; window functions for team/org averages | Mongo (rollups & FK integrity worse), SQLite (no concurrent worker+API writes) |
| ORM | SQLAlchemy 2 + Alembic | Migrations prove production thinking | Raw SQL (fine but migrations sell better) |
| Frontend | **Next.js 14 + TypeScript + Tailwind + shadcn/ui + Recharts** | Your portfolio/AlgoScope stack — you can build fast and it looks professional out of the box; shadcn gives the clean SaaS look (think Linear/Vercel dashboards) | Streamlit — faster but reads "intern demo"; the brownie points explicitly reward polished dashboards |
| Audio player sync | wavesurfer.js or plain `<audio>` + timestamp jump | Click a flag → audio seeks to that second. This is the single most impressive demo moment |
| Packaging | Docker Compose (postgres + api + worker + web), `make demo` seeds and runs everything | "Runs from one clear command" is a stated grading criterion |
| Config | `.env` + pydantic-settings; **MOCK_MODE=true** runs the whole loop with a canned LLM response and pre-transcribed fixture | Graders without API keys can still see the full system work — call this out in the README |

---

## 5. Data & Storage Model

```
orgs(id, name)
teams(id, org_id FK, name, team_leader_id)
advisors(id, team_id FK, name, email, external_ids JSONB)   -- maps CRM/dialer IDs → advisor
calls(id, org_id, advisor_id, customer_ref, source, source_call_id,
      idempotency_key UNIQUE, audio_uri, duration_s, called_at,
      channels, language_hint, raw_metadata JSONB, status)
processing_jobs(id, call_id FK, stage, status[pending|running|done|failed|dead],
      attempts, max_attempts, last_error, run_after, created_at, updated_at)
transcripts(id, call_id FK, engine, language, code_switch_ratio, wer_estimate, text)
segments(id, transcript_id FK, idx, speaker[advisor|customer|unknown],
      start_s, end_s, text, redacted_text)
scores(id, call_id FK, rubric_version, dimension, raw_score 0-5, weight,
      evidence_quote, evidence_start_s, model, prompt_hash, created_at)
call_scores(call_id PK, composite 0-100, rubric_version, computed_at)   -- materialized
flags(id, call_id FK, tag, severity[info|warn|critical], start_s, end_s,
      quote, reason, confidence, state[open|disputed|upheld|dismissed], created_at)
disputes(id, flag_id FK, raised_by advisor_id, note, resolved_by, resolution,
      resolution_note, created_at, resolved_at)
calibration_examples(id, tag, quote, verdict[true_positive|false_positive], source_dispute_id)
audit_log(id, actor, action, entity, entity_id, before JSONB, after JSONB, at)
```

Design notes to defend:
- **Org growth without reconfig**: advisors carry `external_ids JSONB` — a new dialer's agent-ID
  maps in with an UPSERT, no code change. Teams/advisors are rows, not config.
- **Rollups**: org/team/advisor averages are SQL views over `call_scores` (window functions),
  not stored aggregates — always consistent, cheap at this scale; note "materialize when calls
  > ~1M/quarter."
- **`rubric_version` + `prompt_hash` on every score**: scores are only comparable within a
  version; when the rubric changes you can re-run and A/B. This one column impresses senior
  engineers disproportionately.
- **Idempotency**: `idempotency_key = sha256(audio_bytes) + source_id`, UNIQUE constraint.
  Re-delivery from any vendor → insert conflict → no double processing. Each pipeline stage
  also checks "output already exists" before running, so a crashed worker resumes safely.
- **Raw payload preserved** in `raw_metadata JSONB` — you can re-map when a vendor changes fields.

### Where the recordings come from (demo data strategy)
1. **Synthetic calls (primary)**: write 8–10 scripted Hinglish sales-call dialogues covering the
   rubric spectrum (great discovery call, pushy over-promiser, price-dump call, wrong number,
   missed trial booking, heavy code-switching, one with fake "guaranteed placement" claims).
   Render to audio with two distinct TTS voices (edge-tts / Coqui — free), advisor on left channel,
   customer on right → stereo files that also test the mono-fallback path when down-mixed.
2. **1–2 real-style recordings**: record yourself + a friend playing advisor/customer for
   authenticity in the demo video.
3. Seed script loads: 1 org, 3 teams, 9 advisors, ~25 calls (the synthetic audio + pre-computed
   fixtures for bulk history so dashboards have trend lines without hours of processing).

This answers "where do we take the recording from" honestly: production would pull from the
telephony vendor's webhook/S3 export via an adapter; the demo proves the adapter contract with
folder + REST + mock-CRM sources.

---

## 6. Analysis Engine

### 6.1 Scoring rubric (rubric_version = "v1")

| Dimension | Weight | 0 looks like | 5 looks like |
|---|---|---|---|
| Needs discovery | 25% | No questions about goals/background/budget | Open questions, paraphrases customer's goal, tailors pitch to it |
| Product knowledge | 15% | Vague/incorrect program details | Accurate curriculum, mentorship, placement-support specifics |
| Objection handling | 20% | Ignores or bulldozes concerns | Acknowledges, clarifies, resolves with evidence, checks satisfaction |
| Compliance & integrity | 25% | Guarantees, hidden costs, pressure | Honest expectations, full cost disclosure incl. EMI/loan terms |
| Next-step / trial booking | 15% | Call ends with nothing scheduled | Concrete trial slot booked and confirmed |

`composite = Σ(dimension_score/5 × weight) × 100`. Advisor avg = mean of composites over window;
team = mean over advisors (not calls, so one chatty advisor doesn't dominate); org = mean over
teams. All as SQL views. Compliance-critical flags cap the composite at 40 regardless of other
scores — mis-selling can't be averaged away (defend this hard in the interview; it's a product
opinion, and a correct one for edtech).

### 6.2 Issue-tag taxonomy

| Tag | Severity | Trigger example |
|---|---|---|
| `no_needs_discovery` | warn | Pitch begins < 60s in with zero discovery questions |
| `over_promising` | **critical** | "guaranteed job/placement/results", fabricated stats |
| `pressure_tactics` | **critical** | False scarcity, "offer expires tonight", repeated closing after a clear no |
| `price_before_value` | warn | Price stated before any needs/value framing |
| `undisclosed_costs` | **critical** | EMI/loan/registration fees omitted or misrepresented |
| `weak_trial_booking` | warn | No attempt, or vague "I'll call you" |
| `talk_over_customer` | info | Advisor interrupts / talk-ratio > 75% |
| `pii_exposure` | warn | Advisor solicits card/OTP/Aadhaar on the call |
| `non_sales_call` | info | Wrong number / internal — excluded from scoring |

### 6.3 Reliable tagging (the anti-hallucination design — biggest cross-question area)

1. **One analysis call, forced JSON schema** (tool-use / response schema): the model cannot return
   free text. Pydantic re-validates on receipt; invalid → one retry with the validation error in
   the prompt → else stage fails to dead-letter, never partial writes.
2. **Evidence-or-it-didn't-happen**: every flag and every dimension score must include a verbatim
   `quote`. Post-validation does fuzzy substring matching (normalized, ≥0.85 ratio to tolerate
   STT noise) against the actual transcript. **Quote not found → flag dropped and logged.** This
   single mechanism is your answer to "how do you stop the model inventing flags."
3. **Timestamps derived, not generated**: the model returns the quote; *your code* locates it in
   the segments and attaches start/end seconds. LLMs are bad at arithmetic; don't let them do it.
4. **Confidence + threshold**: model emits 0–1 confidence per flag; below 0.6 → flag stored as
   `info` for review rather than surfaced as violation.
5. **Closed taxonomy**: the schema's `tag` field is an enum. The model literally cannot invent a
   new tag.
6. **Calibration few-shots**: upheld/dismissed disputes become labeled examples injected into the
   prompt for that tag — the human feedback loop measurably tightens precision over time.
7. **Determinism hygiene**: temperature 0, `prompt_hash` stored, golden-transcript regression
   tests (below) catch prompt drift.

### 6.4 Edge cases (build the handler or the graceful degradation — never silence)

| Edge case | Handling |
|---|---|
| Mono recording / diarisation fails | Detect channels on ingest; mono → turn-based fallback; if speaker confidence < threshold, mark segments `unknown`, still score what's scoreable, banner "low diarisation confidence" on the call page |
| Hinglish / other languages | Whisper multilingual; store `language` + `code_switch_ratio`; prompt instructed to quote verbatim in original language and reason in English; unsupported language → call marked `needs_review`, not fake-scored |
| Non-sales call | Cheap classifier stage (short LLM call on first ~40 turns) before full analysis; tagged `non_sales_call`, excluded from averages — saves tokens too |
| PII | Redaction stage before the LLM ever sees text: regex (phones, cards, OTP, Aadhaar, emails, PANs) + spaCy NER for names/addresses → `redacted_text` used everywhere downstream; raw text kept in a restricted column. (Your SDIS project did exactly this — say so.) |
| Hallucinated flags | Quote-verification gate (6.3.2) + closed enum + confidence threshold |
| Vendor API failure (STT/LLM) | Retry w/ exponential backoff + jitter, max 3; then `dead` status visible in an ops view; re-queue button; stage-level idempotency means retries never duplicate output |
| Double delivery | UNIQUE idempotency key at ingest; ON CONFLICT DO NOTHING |
| Corrupt / zero-length / non-audio file | ffprobe validation at ingest → rejected with reason into audit log, never enters pipeline |
| Very long calls | Chunked transcription; analysis on full transcript up to context limit, else map-reduce summarize-then-score (documented, not built — say why: 99% of sales calls < 30 min) |

---

## 7. Surfacing — the Dashboard

**Look**: clean SaaS — shadcn/ui, neutral background, one accent color, Inter font, generous
whitespace, skeleton loaders. Think Linear/Vercel, not Grafana. Dark-on-light default.
Follow your frontend-design instincts from the portfolio but *restrained* — this is an ops tool.

**Role switcher** (top-right dropdown, since auth is out of scope) → three views:

1. **Sales Director — Org Health**
   - KPI cards: org avg score (w/ 7-day delta), calls processed, critical flags this week, open disputes
   - Trend line (org score over time), team comparison bar chart
   - "Risk feed": latest critical flags org-wide, each linking to the call
2. **Team Leader — Coaching View**
   - Advisor leaderboard (score, volume, flag count, sparkline)
   - Per-dimension radar/heatmap per advisor → tells the TL *what* to coach, not just who
   - Dispute inbox: listen at timestamp → uphold/dismiss with a note (this closes the loop on camera)
3. **Advisor — My Calls**
   - My calls list w/ scores, my dimension trends vs team average
   - **Call detail page (the money screen)**: audio player + transcript with speaker colors,
     flags pinned inline at their timestamps; click flag → audio seeks there; "Dispute" button
     with a note field

API surface (FastAPI): `POST /ingest/upload`, `GET /orgs/{id}/summary`, `GET /teams/{id}/summary`,
`GET /advisors/{id}/calls`, `GET /calls/{id}` (transcript+segments+flags+scores),
`POST /flags/{id}/dispute`, `POST /disputes/{id}/resolve`, `GET /ops/jobs` (pipeline status).

---

## 8. Implementation Flow — 48-Hour Schedule

**Hours 0–2 · Skeleton**: repo, docker-compose (postgres+api+worker+web), Alembic migration with
full schema, health checks, Makefile (`make demo`).
**Hours 2–6 · Pipeline spine**: job queue table + worker loop (SKIP LOCKED, retries, idempotency),
ingestion adapters (folder + REST + mock CRM → CallEnvelope), ffprobe validation.
**Hours 6–10 · STT + diarisation**: faster-whisper integration, stereo channel-split diarisation,
mono fallback, segments persisted with timestamps.
**Hours 10–14 · Analysis**: redaction stage, non-sales classifier, rubric prompt + JSON schema,
quote-verification gate, scores/flags persisted, MOCK_MODE fixtures.
**Hours 14–16 · Demo data**: write the 8–10 scripts, TTS render, seed script with org/teams/advisors
+ historical fixture calls.
**Hours 16–26 · Frontend**: Next.js app, the three views, call-detail page with audio-synced
transcript (spend the most time here — it's the demo).
**Hours 26–30 · Feedback loop**: dispute endpoints + UI, resolution → flag state + score recompute
+ calibration example row.
**Hours 30–34 · Tests** (see §9) and hardening: kill the worker mid-job and prove resume; upload
the same file twice and prove no dupe.
**Hours 34–38 · README + writeup**: architecture diagram (Mermaid), what's real vs mocked table,
trade-offs section (steal from §4's table), scaling section.
**Hours 38–42 · Video**: script below, record, 2 takes max.
**Hours 42–48 · Buffer** (you will need it — TTS voices, wavesurfer quirks, Whisper model download
size in Docker are the likely fires). If burning: cut wavesurfer → plain audio element with seek;
cut mock-CRM adapter → keep folder+REST; never cut the dispute loop or the call-detail page.

---

## 9. Testing Strategy

What committees actually check on prototypes: does it run first try, does the happy path work,
and did you test the *failure* paths you claim to handle. Target **~30–40 tests**, pytest, run in CI
(GitHub Actions) and via `make test`. Breakdown:

1. **Unit (~15)**: envelope normalization per adapter; idempotency-key derivation; redaction
   (phone/OTP/Aadhaar/card fixtures — include Hinglish-formatted numbers); quote-verification
   fuzzy matcher (exact, STT-noisy, absent → dropped); composite-score math incl. the
   compliance cap; rollup views (advisor/team/org means).
2. **Pipeline/integration (~10)**: full loop on a fixture WAV in MOCK_MODE (no external calls) —
   assert rows land in every table; retry path (transcriber stubbed to fail twice, succeed third);
   dead-letter after max attempts; duplicate upload → single call row; worker crash/resume
   (stage output exists → skipped); mono file → fallback path taken; non-sales fixture → excluded
   from averages.
3. **LLM contract/golden (~8)**: schema-invalid model response → retried then failed cleanly;
   enum violation rejected; **golden transcripts** — 5 hand-labeled fixtures with expected
   flags/score-bands; run against the live model behind a flag (`make eval`) and report
   precision/recall on flags in the writeup. Even a tiny eval set signals real ML-engineering
   maturity.
4. **API (~5)**: dispute lifecycle (open→disputed→upheld/dismissed), score recompute after
   dismissal, ops job listing, 404/validation errors.
5. **Manual smoke checklist** in the README (graders follow it): `make demo` → open dashboard →
   upload provided sample call → watch it appear → click flag → audio seeks → dispute → resolve.

"Deployable?" gates you can honestly claim: clean `docker compose up` on a fresh machine,
health endpoints, structured logs per stage, idempotent everything, secrets via env, no test
depends on network unless flagged, and a documented rollback (it's stateless workers + one DB).

---

## 10. Interview Cross-Question Prep (know these cold)

- **"Why not Kafka/Celery?"** → Scale honesty. Hundreds of calls/day = one Postgres queue table,
  transactional with the domain data, SKIP LOCKED gives safe concurrency. The `JobQueue` interface
  is 40 lines; swapping to SQS/Kafka touches one class. Premature infra is a liability in a
  70-person company.
- **"Why local Whisper over Deepgram/Sarvam?"** → Unit economics for a lean org (₹0/call vs
  per-minute), Hinglish support, and it's behind a `Transcriber` interface — cloud STT is a config
  change when accuracy demands it. Trade-off owned: cloud diarisation is better; that's the first
  thing I'd A/B with real call data.
- **"How do you know the LLM scores are right?"** → I don't assume; I constrain and measure:
  closed schema, evidence quotes verified against the transcript, confidence thresholds, golden-set
  eval with precision/recall, and the dispute loop as continuous human labeling. Rubric_version
  means we can re-score history when the rubric improves.
- **"What breaks first at 10× scale?"** → Whisper on CPU. Fix order: GPU worker pool → managed STT
  for overflow → then queue (Postgres holds well past 10k jobs/day). DB rollup views →
  materialized. Nothing in the schema changes.
- **"What did you not build and why?"** → §2's out-of-scope list, verbatim.
- **"Why can advisors dispute?"** → Adoption. A QA system advisors distrust gets gamed or ignored;
  disputes give due process *and* free labeled data. It converts the org from policing to coaching.
- **"Security/PII?"** → Redact before any third-party API sees text; raw transcript in a
  restricted column; audit log on every human action; (reference your SDIS RBAC/redaction work).

---

## 11. Video Script (2:00)

0:00–0:15 — Problem in one breath: hundreds of calls, ~5% reviewed, mis-selling found only after
complaints. 0:15–0:35 — Architecture diagram: source-agnostic ingest → staged pipeline →
Postgres → three dashboards → dispute loop. 0:35–1:20 — **Live**: drop an audio file in, watch
job stages tick, open the call: transcript, score, a critical `over_promising` flag; click it,
audio jumps to the quote. 1:20–1:40 — Dispute it as the advisor, resolve as the TL, show the
score recompute. 1:40–2:00 — Trade-offs (local Whisper, Postgres queue, no fine-tuning yet) and
where it fails (noisy mono audio, sarcasm, languages beyond Whisper). Confidence, not salesmanship.

---

## 12. Repo Layout

```
callsense/
├─ docker-compose.yml  Makefile  README.md  WRITEUP.md  .env.example
├─ backend/
│  ├─ app/ (api routes, deps)          ├─ pipeline/ (stages/, worker.py, queue.py)
│  ├─ ingestion/ (adapters/, envelope) ├─ analysis/ (prompts/, schema.py, verify.py, rubric.py)
│  ├─ db/ (models.py, views.sql, alembic/)  └─ tests/ (unit/ integration/ golden/)
├─ frontend/ (next-app: app/, components/, lib/)
├─ demo/ (scripts/, audio/, seed.py, fixtures/)
```

README must contain: 60-second quickstart, **"real vs mocked" table**, the smoke checklist,
architecture diagram, and a short "if I had a week more" section.

---

## 13. What Scores the 9/10

The committee sees dozens of "I called an API and made a Streamlit page" submissions. Yours is
different on exactly five axes: (1) the loop genuinely runs end-to-end from one command including
the human feedback stage; (2) hallucination is *engineered away* (quote gate), not prompted away;
(3) reliability is demonstrated, not claimed — killed-worker resume and duplicate-upload tests
exist; (4) the dashboards look like a product because you already build products in this stack;
(5) every choice has a named alternative and a reason, calibrated to *SkilloVilla's* actual size
and business. That last one — showing you understood the company behind "FitNova" — is what turns
a good submission into an offer conversation.
