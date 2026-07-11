# Deploying CallSense (live link, no local machine needed)

Three free-tier pieces. Your laptop can be **off** — everything runs in the cloud.

```
Vercel (Next.js frontend)  →  Render (FastAPI + inline worker, Docker)  →  Neon (Postgres)
        free                          free (mock) / ~$7 (real mode)            free
```

**API keys never touch GitHub.** The repo is key-free (`.env` is gitignored);
the Gemini key is pasted once into Render's dashboard as a server-side
environment variable. The browser talks only to your API — the key never
reaches the client.

---

## 0. Prerequisites (one-time, ~10 min)

Accounts (all free, sign in with GitHub): [neon.tech](https://neon.tech) ·
[render.com](https://render.com) · [vercel.com](https://vercel.com), and the
repo pushed to GitHub.

## 1. Neon — cloud Postgres (~3 min)

1. New project → name `callsense` → region Singapore (closest to India).
2. Copy the connection string and adapt it for SQLAlchemy/psycopg — prefix
   `postgresql+psycopg://` instead of `postgresql://`:
   `postgresql+psycopg://USER:PASSWORD@HOST/callsense?sslmode=require`
3. Seed the demo data **from your machine** (one-off):
   ```powershell
   $env:DATABASE_URL = "postgresql+psycopg://...neon.../callsense?sslmode=require"
   cd backend; conda run -n callsense alembic upgrade head; cd ..
   conda run -n callsense python demo/seed.py
   ```
   (Migrations also run automatically on every API boot, so step 3's alembic
   part is belt-and-braces.)

## 2. Render — the API + worker (~5 min)

1. New → **Blueprint** → pick your GitHub repo (it reads `render.yaml`).
2. When prompted, fill the two secrets:
   - `DATABASE_URL` = the Neon string from step 1
   - `GEMINI_API_KEY` = your AI Studio key (used only if you enable real mode)
3. Deploy. First build ~5 min. Verify: `https://callsense-api.onrender.com/health/db`
   → `{"status":"ok","db":"up"}`.

Notes:
- Free tier = 512MB RAM → ships with `MOCK_MODE=true`: the full loop (upload →
  queue → stages → dashboards → disputes) runs on canned analyses. This is the
  honest fit for 512MB — Whisper needs ~2GB.
- **Real mode in the cloud**: upgrade the service to Starter (2GB), set
  `MOCK_MODE=false`, add `pip install -r requirements-real.txt` to the
  Dockerfile (or bake a real-mode image), redeploy.
- Free services sleep after 15 min idle; first request takes ~40s to wake.

## 3. Vercel — the frontend (~3 min)

1. New Project → import the repo → **Root Directory: `frontend`** (Vercel
   auto-detects Next.js).
2. Environment variable: `NEXT_PUBLIC_API_URL = https://callsense-api.onrender.com`
3. Deploy → `https://callsense-<something>.vercel.app` is your live link.

## 4. Show interviewers the data

- **Neon console → Tables** — every table (calls, segments, scores, flags,
  disputes, audit_log, processing_jobs) browsable with row contents, plus a
  built-in SQL editor for live queries (`SELECT * FROM v_team_scores;`).
- The app itself surfaces pipeline state at `/ops/jobs` and the About page
  explains the schema in prose.

## Security & limits (what's already handled)

| Concern | Handling |
|---|---|
| Secrets | Env vars only; `.env` gitignored; keys server-side, never in the client bundle |
| SQL injection | All queries parameterised (SQLAlchemy `text()` binds) |
| Upload abuse | 200MB size cap + 10 uploads/min/IP rate limit (429 + Retry-After) |
| LLM quota | Client-side throttle (1 rps) + exponential backoff on 429/503, then job-level retry/dead-letter |
| Double-processing | sha256 idempotency key + idempotent stages |
| PII | Redacted before any external API; raw text in a restricted column |
| XSS | React auto-escaping; no `dangerouslySetInnerHTML` |
| Known gaps (scope) | No auth (role switcher by design), open CORS for the demo, in-memory rate limiter is per-process |

## Capacity (measured / derived)

- **Transcription**: ~3.3× real-time per CPU worker (11.5-min call → 3m32s,
  Whisper small/int8). ≈ **300–400 five-minute calls/day per worker**; workers
  are stateless → scale horizontally.
- **LLM**: 2 calls per analysed call. Free-tier Gemini flash-lite sustains
  ≈ **500+ calls/day**; paid tier removes the ceiling.
- **Postgres/queue**: trivially fine to ~10k jobs/day (Neon free: 0.5GB ≈
  hundreds of thousands of calls' metadata).
- **First bottleneck at 10×**: Whisper on CPU → GPU worker pool → managed STT
  overflow → materialise rollup views. No schema changes.
