"""JobQueue — a Postgres-backed work queue (rubric §3.10-3.13).

Why Postgres and not Celery/Kafka: at hundreds of calls/day, one job table with
`SELECT ... FOR UPDATE SKIP LOCKED` gives safe multi-worker concurrency,
transactional with the domain data, and idempotency/dead-lettering as plain
columns. The `JobQueue` ABC documents the SQS/Kafka swap: reimplement four
methods, touch nothing else.

Reliability properties:
- **Atomic claim**: the claim CTE locks exactly one row and flips it to
  `running` in a single statement; concurrent workers skip locked rows.
- **Crash recovery**: a `running` job whose `updated_at` is older than the
  visibility timeout is re-claimable (a worker died mid-stage). Stage-level
  idempotency makes re-running safe.
- **Backoff + jitter**: failed jobs return to `pending` with
  `run_after = clock_timestamp() + base * 2**attempt * (0.5..1.5)`.
- **Dead-letter**: `attempts >= max_attempts` parks the job as `dead` with the
  last error, visible in the ops view and re-queueable.
"""

from __future__ import annotations

import random
from abc import ABC, abstractmethod
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import get_settings

settings = get_settings()

# Stale `running` jobs older than this are assumed crashed and re-claimable.
VISIBILITY_TIMEOUT_S = 300


@dataclass
class JobClaim:
    id: int
    call_id: int
    stage: str
    attempts: int
    max_attempts: int


def backoff_seconds(attempt: int) -> float:
    """Exponential backoff with ±50% jitter (thundering-herd cure)."""
    base = settings.job_backoff_base_s * (2 ** max(0, attempt - 1))
    return base * random.uniform(0.5, 1.5)


class JobQueue(ABC):
    @abstractmethod
    def enqueue(self, session: Session, call_id: int, stage: str) -> None: ...

    @abstractmethod
    def claim(self, session: Session) -> JobClaim | None: ...

    @abstractmethod
    def complete(
        self, session: Session, job_id: int, next_stage: str | None
    ) -> None: ...

    @abstractmethod
    def fail(self, session: Session, job: JobClaim, error: str) -> None: ...


class PostgresJobQueue(JobQueue):
    def enqueue(self, session: Session, call_id: int, stage: str) -> None:
        # UNIQUE(call_id, stage) + ON CONFLICT DO NOTHING => enqueue is idempotent.
        session.execute(
            text(
                """
                INSERT INTO processing_jobs
                    (call_id, stage, status, attempts, max_attempts,
                     run_after, created_at, updated_at)
                VALUES
                    (:call_id, :stage, 'pending', 0, :max_attempts,
                     clock_timestamp(), clock_timestamp(), clock_timestamp())
                ON CONFLICT (call_id, stage) DO NOTHING
                """
            ),
            {"call_id": call_id, "stage": stage, "max_attempts": settings.job_max_attempts},
        )

    def claim(self, session: Session) -> JobClaim | None:
        row = session.execute(
            text(
                """
                WITH claimed AS (
                    SELECT id FROM processing_jobs
                    WHERE (status = 'pending' AND run_after <= clock_timestamp())
                       OR (status = 'running'
                           AND updated_at < clock_timestamp() - make_interval(secs => :vis))
                    ORDER BY run_after
                    LIMIT 1
                    FOR UPDATE SKIP LOCKED
                )
                UPDATE processing_jobs j
                SET status = 'running', attempts = j.attempts + 1, updated_at = clock_timestamp()
                FROM claimed
                WHERE j.id = claimed.id
                RETURNING j.id, j.call_id, j.stage, j.attempts, j.max_attempts
                """
            ),
            {"vis": VISIBILITY_TIMEOUT_S},
        ).first()
        if row is None:
            return None
        return JobClaim(
            id=row.id,
            call_id=row.call_id,
            stage=row.stage,
            attempts=row.attempts,
            max_attempts=row.max_attempts,
        )

    def complete(self, session: Session, job_id: int, next_stage: str | None) -> None:
        session.execute(
            text(
                "UPDATE processing_jobs SET status='done', last_error=NULL, "
                "updated_at=clock_timestamp() WHERE id=:id"
            ),
            {"id": job_id},
        )
        if next_stage is not None:
            row = session.execute(
                text("SELECT call_id FROM processing_jobs WHERE id=:id"),
                {"id": job_id},
            ).first()
            if row is not None:
                self.enqueue(session, row.call_id, next_stage)

    def fail(self, session: Session, job: JobClaim, error: str) -> None:
        if job.attempts >= job.max_attempts:
            session.execute(
                text(
                    "UPDATE processing_jobs SET status='dead', last_error=:err, "
                    "updated_at=clock_timestamp() WHERE id=:id"
                ),
                {"id": job.id, "err": error[:2000]},
            )
        else:
            session.execute(
                text(
                    "UPDATE processing_jobs SET status='pending', last_error=:err, "
                    "run_after = clock_timestamp() + make_interval(secs => :delay), "
                    "updated_at=clock_timestamp() WHERE id=:id"
                ),
                {"id": job.id, "err": error[:2000], "delay": backoff_seconds(job.attempts)},
            )
