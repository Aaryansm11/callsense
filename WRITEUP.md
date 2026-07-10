# CallSense — Design Writeup

## The problem, in one breath
FitNova (a Bangalore fitness & wellness coaching platform) runs tele-sales through
advisors; TLs can manually review ~5% of calls, so mis-selling ("weight loss
guaranteed", hidden auto-renewal/registration costs) is usually found only at
customer-complaint time. CallSense converts 100% of calls into scored, flagged,
reviewable records the same day — and gives advisors due process so they trust it.

## What I optimised for
A fast-growing org with hundreds of advisors in pods, where choosing a coaching program
runs on trust. That drives three biases: **cheap to run** (local Whisper = ₹0/call),
**low-ops** (docker compose + one Postgres, no Kubernetes/Kafka cosplay), and **depth in
the boring parts** (idempotency, queue semantics, failure modes, data modelling) over
trendy infra.

## Key design decisions & trade-offs

| Decision | Why | Trade-off owned |
|---|---|---|
| **Postgres-backed queue** (`FOR UPDATE SKIP LOCKED`) | Transactional with the domain data; idempotency + dead-letter are just columns; safe multi-worker concurrency; honest at hundreds/day | Celery/Kafka would scale further — the `JobQueue` interface is the swap seam (4 methods) |
| **Local faster-whisper** behind a `Transcriber` iface | ₹0/call, Hinglish, word timestamps, no vendor lock/PII egress | Cloud STT diarises better; that's the first thing I'd A/B with real calls |
| **LLM scoring, not training** | Zero labelled data on day one; prompting + validation is high-quality immediately | Fine-tuning deferred until the dispute loop accumulates labels (roadmap) |
| **Quote-verification gate** | Engineers hallucination *away* instead of prompting it away — every quote must fuzzy-match the transcript or the flag is dropped | Costs recall on paraphrased-but-real violations; a deliberate precision-over-recall stance |
| **Compliance cap at 40** | Averaging lets a smooth talker launder a fake guarantee to 80; the cap makes the org's values legible in the math | Harsh by design; the dispute loop is the safety valve for false positives |
| **Team avg = mean over advisors, not calls** | One high-volume advisor shouldn't dominate a team's number | Both options are defensible; the choice is the point |
| **Native VARCHAR+CHECK enums** (not PG ENUM) | App-side type safety + DB integrity without `ALTER TYPE` pain as taxonomies grow | Slightly weaker than a DB enum type |
| **Role switcher, not auth** | Auth/SSO is out of scope; the switcher demonstrates the *authorization model* without the plumbing | RBAC is an API-layer stub |

## Anti-hallucination (the biggest cross-question)
Five layers, defence-in-depth: (1) closed `tag`/`dimension` enums — the model *cannot*
invent a tag; (2) forced JSON + Pydantic re-validation, one retry then dead-letter;
(3) **quote gate** — normalized fuzzy match (≥0.85) of every quote against the
transcript, unmatched quotes dropped and logged; (4) timestamps derived by *code* from
the matched segment (LLMs are bad at arithmetic); (5) confidence threshold — below 0.6
a flag degrades to `info` for review, never a surfaced violation. Verified in tests
(exact / STT-noisy / absent quotes) and live (a mismatched quote is dropped).

## Reliability, demonstrated (not claimed)
- **Idempotent ingest**: `sha256(audio)+source` UNIQUE → duplicate delivery is one row
  (test + live).
- **Idempotent stages**: each stage skips if its output exists → a crashed-then-resumed
  worker doesn't duplicate (test).
- **Retry/backoff/dead-letter**: failed jobs return to `pending` with
  `now() + base·2ⁿ·jitter`; `attempts ≥ max` → `dead`, visible in `/ops/jobs`,
  re-queueable (tests).
- **Crash recovery**: a `running` job stale past the visibility timeout is re-claimable.
- Stateless workers + one DB → "rollback" = run the previous image.

## The feedback loop as a data flywheel
A dispute resolution is simultaneously (a) due process, (b) a calibration few-shot
injected into the next analysis prompt for that tag, and (c) the future fine-tuning
label set. Dismissing a critical flag recomputes the composite (cap lifts, e.g.
40 → 64/80). This is the loop the assignment asks for — "how humans correct the system
and how that loops back" — closed literally.

## What breaks first at 10× and the fix order
Whisper on CPU. Fix order: GPU worker pool → managed STT for overflow → then the queue
(Postgres holds well past 10k jobs/day) → materialise the rollup views. **No schema
change** in any of these.

## Scoring the rubric
Every score row carries `rubric_version` + `prompt_hash`, so scores are only compared
within a version and prompt drift is detectable. A golden-set eval (`make eval`,
roadmap) would report per-tag precision/recall on hand-labelled transcripts — the honest
way to say "the LLM scores are right": don't assume, constrain and measure.
