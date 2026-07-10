"""Engine + session factory + FastAPI dependency + a DB health ping.

Sync SQLAlchemy 2.0 is used deliberately: the API's hot path is light reads,
and heavy CPU work (Whisper) lives in a separate worker process, never in the
event loop. FastAPI runs sync path handlers in a threadpool, so this stays
non-blocking at the request level. An async engine can be added later without
touching call sites.
"""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings

_settings = get_settings()

engine = create_engine(
    _settings.database_url,
    pool_pre_ping=True,  # transparently recycle stale connections
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """FastAPI dependency yielding a request-scoped session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def ping() -> bool:
    """Return True if the database answers a trivial query."""
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return True
