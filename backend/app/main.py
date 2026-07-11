"""CallSense API — FastAPI application entrypoint.

Phase 1 exposes only health/readiness endpoints and app metadata. Domain routes
(ingest, orgs, teams, advisors, calls, flags, disputes, ops) land in later phases
and will be mounted here via `app.include_router(...)`.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.routes import calls, disputes, flags, ingest, ops, summaries
from db.session import ping

settings = get_settings()

logging.basicConfig(
    level=settings.log_level,
    format='{"level":"%(levelname)s","logger":"%(name)s","msg":"%(message)s"}',
)
log = logging.getLogger("callsense.api")

# docs_url=None: we serve Swagger ourselves with a RELATIVE openapi URL so the
# docs work both on the direct domain (/docs) and through the Vercel edge proxy
# (/api/backend/docs) — FastAPI's default hardcodes /openapi.json at the domain
# root, which a path-prefixed proxy can't satisfy.
app = FastAPI(
    title=f"{settings.app_name} API",
    version="0.1.0",
    summary="Sales-call intelligence for FitNova (SkilloVilla) — Phase 1 skeleton.",
    docs_url=None,
    redoc_url=None,
)


@app.get("/docs", include_in_schema=False)
def swagger_docs():
    from fastapi.openapi.docs import get_swagger_ui_html

    # Relative URL: resolves against the page's own path, wherever it's mounted.
    return get_swagger_ui_html(openapi_url="openapi.json", title=f"{settings.app_name} API — docs")

# The Next.js dashboard is a browser client of this API. Wide-open CORS is fine
# for a single-host demo; tighten to the web origin in prod.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


for _router in (ingest.router, calls.router, summaries.router,
                flags.router, disputes.router, ops.router):
    app.include_router(_router)


@app.on_event("startup")
def _maybe_start_inline_worker() -> None:
    """Single-container deployments (Render free tier) run the worker as a
    daemon thread. Local/compose keep a dedicated worker process instead."""
    if not settings.run_inline_worker:
        return
    import threading

    from pipeline import worker as pipeline_worker

    t = threading.Thread(target=pipeline_worker.main, name="inline-worker", daemon=True)
    t.start()
    log.info("inline worker thread started")


@app.get("/", tags=["meta"])
def root() -> dict:
    return {
        "service": settings.app_name,
        "version": app.version,
        "environment": settings.environment,
        "mock_mode": settings.mock_mode,
        "docs": "/docs",
    }


@app.get("/health", tags=["meta"])
def health() -> dict:
    """Liveness: the process is up and serving. No dependencies checked."""
    return {"status": "ok"}


@app.get("/health/db", tags=["meta"])
def health_db() -> JSONResponse:
    """Readiness: can we actually reach Postgres? Used by compose healthchecks."""
    try:
        ping()
    except Exception as exc:  # noqa: BLE001 - report any driver/connection error
        log.warning("db healthcheck failed: %s", exc)
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "unavailable", "db": "down"},
        )
    return JSONResponse(content={"status": "ok", "db": "up"})
