"""Job-queue reliability tests: backoff, dead-letter, idempotent resume (§9.7)."""

from sqlalchemy import text

from pipeline.queue import PostgresJobQueue
from pipeline.stages import transcribe
from tests.helpers import seed_org


def _make_call(db, max_attempts=3, stage="transcribe"):
    db.execute(text("INSERT INTO orgs(id,name) VALUES (1,'O')"))
    db.execute(text(
        "INSERT INTO calls(id,org_id,source,idempotency_key,status,raw_metadata) "
        "VALUES (1,1,'rest','k1','received', CAST('{\"fixture\":\"good_discovery\"}' AS jsonb))"
    ))
    db.execute(text(
        "INSERT INTO processing_jobs(call_id,stage,status,attempts,max_attempts,run_after,created_at,updated_at) "
        "VALUES (1,:stage,'pending',0,:ma,now(),now(),now())"
    ), {"stage": stage, "ma": max_attempts})
    db.commit()


def test_fail_retries_with_future_run_after(db):
    _make_call(db, max_attempts=3)
    q = PostgresJobQueue()
    job = q.claim(db); db.commit()
    assert job is not None and job.attempts == 1
    q.fail(db, job, "boom"); db.commit()
    row = db.execute(text(
        "SELECT status, run_after > now() AS deferred, last_error FROM processing_jobs")
    ).mappings().one()
    assert row["status"] == "pending" and row["deferred"] is True
    assert "boom" in row["last_error"]


def test_dead_letters_at_max_attempts(db):
    _make_call(db, max_attempts=1)
    q = PostgresJobQueue()
    job = q.claim(db); db.commit()  # attempts -> 1, == max
    q.fail(db, job, "still broken"); db.commit()
    status = db.execute(text("SELECT status FROM processing_jobs")).scalar_one()
    assert status == "dead"


def test_claim_skips_jobs_scheduled_for_the_future(db):
    _make_call(db)
    db.execute(text("UPDATE processing_jobs SET run_after = now() + interval '1 hour'"))
    db.commit()
    q = PostgresJobQueue()
    assert q.claim(db) is None


def test_stage_is_idempotent_on_resume(db):
    seed_org(db)
    db.execute(text(
        "INSERT INTO calls(id,org_id,advisor_id,source,idempotency_key,status,raw_metadata) "
        "VALUES (1,1,1,'rest','k9','received', CAST('{\"fixture\":\"good_discovery\"}' AS jsonb))"
    ))
    db.commit()
    # Running transcribe twice (simulating a crashed-then-resumed worker) must not
    # duplicate the transcript/segments.
    transcribe.run(db, 1); db.commit()
    transcribe.run(db, 1); db.commit()
    assert db.execute(text("SELECT count(*) FROM transcripts")).scalar_one() == 1
    assert db.execute(text("SELECT count(*) FROM segments")).scalar_one() == 11
