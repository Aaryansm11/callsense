"""Full-pipeline integration tests in MOCK_MODE (rubric §9.2)."""

from sqlalchemy import text

from ingestion.envelope import CallEnvelope, derive_idempotency_key
from ingestion.service import ingest
from pipeline import worker
from pipeline.queue import PostgresJobQueue
from tests.helpers import make_wav, seed_org


def _ingest(db, wav, fixture, ext="AGT-1"):
    audio = wav.read_bytes()
    env = CallEnvelope(
        source="rest",
        idempotency_key=derive_idempotency_key(audio, "rest"),
        audio_uri=str(wav),
        advisor_external_id=ext,
        org_id=1,
        raw_metadata={"fixture": fixture},
    )
    q = PostgresJobQueue()
    result = ingest(db, env, q)
    db.commit()
    return result, q


def test_full_loop_writes_every_table_and_caps(db, tmp_path):
    seed_org(db)
    wav = make_wav(tmp_path / "a.wav")
    _, q = _ingest(db, wav, "over_promiser")
    worker.run_until_idle(q)

    def count(t):
        return db.execute(text(f"SELECT count(*) FROM {t}")).scalar_one()

    assert count("transcripts") == 1
    assert count("segments") == 11
    assert count("scores") == 5
    assert count("flags") >= 1
    assert count("call_scores") == 1

    row = db.execute(
        text("SELECT status FROM calls WHERE id=1")
    ).scalar_one()
    assert row == "done"

    cs = db.execute(
        text("SELECT composite, compliance_capped FROM call_scores WHERE call_id=1")
    ).mappings().one()
    assert cs["composite"] == 40.0 and cs["compliance_capped"] is True

    stages = db.execute(
        text("SELECT status FROM processing_jobs")
    ).scalars().all()
    assert set(stages) == {"done"}


def test_duplicate_delivery_yields_single_call(db, tmp_path):
    seed_org(db)
    wav = make_wav(tmp_path / "dup.wav")
    r1, q = _ingest(db, wav, "good_discovery")
    r2, _ = _ingest(db, wav, "good_discovery")
    assert r1.created is True and r2.created is False
    assert db.execute(text("SELECT count(*) FROM calls")).scalar_one() == 1


def test_non_sales_excluded_from_scoring_and_rollups(db, tmp_path):
    seed_org(db)
    wav = make_wav(tmp_path / "ns.wav")
    _, q = _ingest(db, wav, "non_sales")
    worker.run_until_idle(q)

    assert db.execute(text("SELECT count(*) FROM call_scores")).scalar_one() == 0
    tag = db.execute(text("SELECT tag FROM flags")).scalar_one()
    assert tag == "non_sales_call"

    scored = db.execute(
        text("SELECT scored_calls FROM v_advisor_scores WHERE advisor_id=1")
    ).scalar_one()
    assert scored == 0  # non-sales call not counted
