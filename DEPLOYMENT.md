# Deploying CallSense (live link, REAL Whisper + Gemini)

The deployed stack — laptop can be off, everything cloud-side, **real mode**:

```
Vercel (Next.js frontend)  →  Railway (FastAPI + inline worker, Docker)  →  Neon (Postgres)
        free                    trial: $5 one-time credit, no card              free
```

**API keys never touch GitHub.** The repo is key-free; secrets live in Railway
service variables. The browser talks only to the API.

> Provider notes (July 2026): HF Spaces was the original free pick (16GB) but
> free Docker Spaces now require PRO — `scripts/deploy_hf_space.ps1` still works
> on a PRO account. Render free (512MB) can't fit Whisper; `render.yaml` remains
> as a mock-mode fallback. Railway's trial is 1GB RAM → `WHISPER_MODEL=base`
> in the cloud; local/video demos use `small`.

---

## 1. Neon — cloud Postgres ✅

Project `callsense`; migrations applied. Connection string in SQLAlchemy form
(**`postgresql+psycopg://`** prefix): `postgresql+psycopg://USER:PASS@HOST/neondb?sslmode=require`

## 2. Railway — API + worker ✅

Driven via CLI with an **account-scoped** token (railway.com/account/tokens →
workspace = "No workspace"):

```powershell
$env:RAILWAY_API_TOKEN = "..."
railway init -n callsense
railway add --service callsense
railway variables --service callsense `
  --set "DATABASE_URL=postgresql+psycopg://...neon.../neondb?sslmode=require" `
  --set "GEMINI_API_KEY=..." `
  --set "WHISPER_MODEL=base"
railway up --service callsense --detach     # uploads + builds the root Dockerfile
railway domain --service callsense --port 7860
```

Live at: **https://callsense-production-d0b3.up.railway.app** (`/health/db`,
`/docs`). Boot sequence per deploy: migrations → in-container demo seed (audio
playable in the cloud) → API + inline worker, `MOCK_MODE=false`.

Notes: `.railwayignore` keeps `.env`/junk out of uploads; the container disk is
ephemeral (each deploy reseeds the demo; Neon rows persist); trial credit
(~$5 ≈ 2 weeks always-on) simply stops when exhausted — no surprise billing.

## 3. Vercel — the frontend (~3 min)

1. vercel.com → sign in with GitHub → Add New → Project → import `callsense`.
2. **Root Directory = `frontend`** (critical).
3. Env var: `NEXT_PUBLIC_API_URL = https://callsense-production-d0b3.up.railway.app`
4. Deploy → your live link.

## 4. Showing interviewers the data

Neon console → **Tables** (browse calls/segments/scores/flags/disputes/audit
live) or its **SQL Editor**: `SELECT * FROM v_team_scores;`. In-app: `/about`
explains the schema; `/ops/jobs` shows the queue.

## Security & limits

| Concern | Handling |
|---|---|
| Secrets | Server-side env only; `.env` gitignored + `.railwayignore`d |
| SQL injection | Parameterised queries throughout |
| Upload abuse | 200MB cap + 10 uploads/min/IP (429 + Retry-After) |
| LLM quota | 1 rps client throttle + backoff on 429/503 + job retry/dead-letter |
| Double-processing | sha256 idempotency key + idempotent stages |
| PII | Redacted before any external API; raw text restricted |
| Known gaps (scope) | No auth (role switcher by design); open CORS; per-process rate limiter |

## Capacity (measured)

- Whisper small/int8 local: **~3.3× real-time** (11.5-min call → 3m32s). Cloud
  trial runs `base` on shared vCPU: expect ~1× real-time.
- Gemini free tier: **~500+ calls/day** (2 LLM calls per call, throttled).
- Neon free (0.5GB): metadata for hundreds of thousands of calls.
- First bottleneck at 10×: Whisper on CPU → GPU workers → managed STT. No
  schema changes.
