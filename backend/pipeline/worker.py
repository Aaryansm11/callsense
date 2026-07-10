"""Worker: claim a job, run its stage, transition it — idempotently.

Transaction boundaries:
1. Claim runs in its own txn and commits immediately (status -> running, lock
   released). Other workers skip it; a crash leaves it re-claimable after the
   visibility timeout.
2. The stage runs in a second txn; on success the job is marked done AND the next
   stage enqueued in the SAME txn (atomic). On failure the whole txn rolls back
   and the job is failed (retry-with-backoff or dead-letter) in a third txn.

`process_one` / `run_until_idle` are exposed for the integration tests; `main`
is the long-running loop the compose `worker` service runs.
"""

from __future__ import annotations

import logging
import time

from app.config import get_settings
from db.session import SessionLocal
from pipeline.queue import JobQueue, PostgresJobQueue
from pipeline.stages import STAGES, next_stage

settings = get_settings()
logging.basicConfig(level=settings.log_level)
log = logging.getLogger("callsense.worker")


def process_one(queue: JobQueue) -> bool:
    """Claim and process at most one job. Returns False if the queue was idle."""
    with SessionLocal() as session:
        job = queue.claim(session)
        session.commit()
    if job is None:
        return False

    try:
        with SessionLocal() as session:
            STAGES[job.stage](session, job.call_id)
            nxt = next_stage(job.stage, session, job.call_id)
            queue.complete(session, job.id, nxt)
            session.commit()
        log.info("stage %s done for call %s", job.stage, job.call_id)
    except Exception as exc:  # noqa: BLE001 - any stage failure -> retry/dead-letter
        with SessionLocal() as session:
            queue.fail(session, job, f"{type(exc).__name__}: {exc}")
            session.commit()
        log.exception("stage %s failed for call %s", job.stage, job.call_id)
    return True


def run_until_idle(queue: JobQueue, max_iterations: int = 1000) -> int:
    """Drain the queue (used by tests/seed). Returns the number of jobs handled."""
    handled = 0
    for _ in range(max_iterations):
        if not process_one(queue):
            break
        handled += 1
    return handled


def main() -> None:
    queue = PostgresJobQueue()
    log.info("worker up (mock_mode=%s)", settings.mock_mode)
    while True:
        if not process_one(queue):
            time.sleep(settings.worker_poll_interval_s)


if __name__ == "__main__":
    main()
