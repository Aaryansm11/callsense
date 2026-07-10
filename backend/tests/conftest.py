"""Pytest fixtures.

Tests run against an isolated `callsense_test` database (created on demand) so
they never touch the demo/dev data. The schema is built from the ORM models +
views.sql once per session; each test starts from truncated tables.
"""

from __future__ import annotations

import os

# Point every import that reads config at the test DB, BEFORE importing db/app.
os.environ["DATABASE_URL"] = (
    "postgresql+psycopg://callsense:callsense@localhost:5432/callsense_test"
)
os.environ["MOCK_MODE"] = "true"

from pathlib import Path  # noqa: E402

import psycopg  # noqa: E402
import pytest  # noqa: E402
from sqlalchemy import text  # noqa: E402

TEST_DB = "callsense_test"
ALL_TABLES = [
    "calls", "processing_jobs", "transcripts", "segments", "scores",
    "call_scores", "flags", "disputes", "calibration_examples", "audit_log",
    "advisors", "teams", "orgs",
]


def _ensure_test_db() -> None:
    with psycopg.connect(
        "host=localhost port=5432 dbname=callsense user=callsense password=callsense",
        autocommit=True,
    ) as conn:
        exists = conn.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", (TEST_DB,)
        ).fetchone()
        if not exists:
            conn.execute(f"CREATE DATABASE {TEST_DB}")


_ensure_test_db()

from db.base import Base  # noqa: E402
from db.session import SessionLocal, engine  # noqa: E402

_VIEWS = (Path(__file__).resolve().parents[1] / "db" / "views.sql").read_text(
    encoding="utf-8"
)


@pytest.fixture(scope="session", autouse=True)
def _schema():
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        # Execute the whole file at once (psycopg3 supports multi-statement);
        # splitting on ';' would break comments that contain semicolons.
        conn.exec_driver_sql(_VIEWS)
    yield


@pytest.fixture()
def db():
    with SessionLocal() as session:
        session.execute(
            text("TRUNCATE " + ", ".join(ALL_TABLES) + " RESTART IDENTITY CASCADE")
        )
        session.commit()
        yield session
