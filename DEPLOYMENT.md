# Deploying CallSense (live link, REAL Whisper + Gemini, all free)

Your laptop can be off — everything runs in the cloud, in **real mode**:

```
Vercel (Next.js frontend)  →  HF Space (FastAPI + worker, Docker, REAL mode)  →  Neon (Postgres)
        free                    free · 2 vCPU · 16GB RAM · Whisper fits            free
```

Why a Hugging Face Space for the backend: it's the only mainstream free tier
with enough RAM (16GB) to run faster-whisper. Render's free 512MB only fits the
mock loop (kept in `render.yaml` as a fallback).

**API keys never touch GitHub.** The repo is key-free; secrets are set
server-side on the Space via API. The browser talks only to your API.

---

## 1. Neon — cloud Postgres (done ✅)

Project created; migrations applied. The connection string (SQLAlchemy form —
note the `+psycopg`):
`postgresql+psycopg://USER:PASS@HOST/neondb?sslmode=require`

## 2. Hugging Face Space — the API + worker (~5 min)

1. Create a free account at **huggingface.co** (no card).
2. Settings → **Access Tokens** → *Create new token* → type **Write** → copy it.
3. One command from the repo root:
   ```powershell
   ./scripts/deploy_hf_space.ps1 -Token hf_xxx `
       -DatabaseUrl "postgresql+psycopg://...neon.../neondb?sslmode=require" `
       -GeminiKey "your-ai-studio-key"
   ```
   It creates the Space, sets the two secrets server-side, and pushes the code.
   First build ≈ 8–10 min (bakes the Whisper model into the image).
4. Watch the build at `https://huggingface.co/spaces/<you>/callsense`; the API
   base URL is `https://<you>-callsense.hf.space` — check `/health/db`.

Boot sequence per container start: migrations → demo seed (audio regenerated
inside the container, so playback works) → API + inline worker in **real mode**.
Note: the Space's filesystem is ephemeral — a restart reseeds the demo data and
uploaded audio from previous sessions disappears (Neon keeps the rows).
Public Space = source visible there; keep it private instead with `-Private`
(then only you can open the app).

## 3. Vercel — the frontend (~3 min)

1. vercel.com → sign in with GitHub → Add New → Project → import `callsense`.
2. **Root Directory = `frontend`** (critical).
3. Env var: `NEXT_PUBLIC_API_URL = https://<you>-callsense.hf.space`
4. Deploy → your live link.

## 4. Showing interviewers the data

Neon console → **Tables** (browse calls/segments/scores/flags/disputes/audit
live) or its **SQL Editor**: `SELECT * FROM v_team_scores;`. In-app: `/about`
explains the schema; `/ops/jobs` shows the queue.

## Security & limits

| Concern | Handling |
|---|---|
| Secrets | Server-side env only; `.env` gitignored; never in the client bundle |
| SQL injection | Parameterised queries throughout |
| Upload abuse | 200MB cap + 10 uploads/min/IP (429 + Retry-After) |
| LLM quota | 1 rps client throttle + backoff on 429/503 + job retry/dead-letter |
| Double-processing | sha256 idempotency key + idempotent stages |
| PII | Redacted before any external API; raw text restricted |
| Known gaps (scope) | No auth (role switcher by design); open CORS; per-process rate limiter |

## Capacity (measured)

- Whisper small/int8: **~3.3× real-time** on a local CPU (11.5-min call →
  3m32s); on the Space's 2 vCPU expect ~1–2× real-time → a 2-min call ≈ 1–2 min.
- Gemini free tier: **~500+ calls/day** (2 LLM calls per call, throttled).
- Neon free (0.5GB): metadata for hundreds of thousands of calls.
- First bottleneck at 10×: Whisper on CPU → GPU workers → managed STT. No
  schema changes.
