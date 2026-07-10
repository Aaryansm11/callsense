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

app = FastAPI(
    title=f"{settings.app_name} API",
    version="0.1.0",
    summary="Sales-call intelligence for FitNova (SkilloVilla) — Phase 1 skeleton.",
)

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
