"""API dispute-lifecycle tests (rubric §9 API): open -> dismissed -> recompute."""

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.main import app

client = TestClient(app)


def _seed_scored_call(db):
    db.execute(text("INSERT INTO orgs(id,name) VALUES (1,'O')"))
    db.execute(text("INSERT INTO teams(id,org_id,name) VALUES (1,1,'T')"))
    db.execute(text(
        "INSERT INTO advisors(id,team_id,name,external_ids) "
        "VALUES (1,1,'Arjun', CAST('[\"AGT-1\"]' AS jsonb))"
    ))
    db.execute(text(
        "INSERT INTO calls(id,org_id,advisor_id,source,idempotency_key,status) "
        "VALUES (1,1,1,'rest','k1','done')"
    ))
    for dim in ["needs_discovery", "product_knowledge", "objection_handling",
                "compliance_integrity", "next_step_booking"]:
        db.execute(text(
            "INSERT INTO scores(call_id,rubric_version,dimension,raw_score,weight) "
            "VALUES (1,'v1',:d,4,0.2)"
        ), {"d": dim})
    db.execute(text(
        "INSERT INTO call_scores(call_id,composite,rubric_version,compliance_capped) "
        "VALUES (1,40,'v1',true)"
    ))
    db.execute(text(
        "INSERT INTO flags(call_id,tag,severity,quote,reason,confidence,state) "
        "VALUES (1,'over_promising','critical','placement guaranteed','g',0.95,'open') "
        "RETURNING id"
    ))
    db.commit()
    return db.execute(text("SELECT id FROM flags")).scalar_one()


def test_dispute_dismiss_recomputes_and_calibrates(db):
    flag_id = _seed_scored_call(db)

    r = client.post(f"/flags/{flag_id}/dispute", json={"note": "context", "raised_by": 1})
    assert r.status_code == 200 and r.json()["state"] == "disputed"
    dispute_id = r.json()["dispute_id"]

    r2 = client.post(f"/disputes/{dispute_id}/resolve",
                     json={"resolution": "dismissed", "resolved_by": "tl_meera"})
    assert r2.status_code == 200
    body = r2.json()
    # Dismissing the only critical flag lifts the cap: 40 -> 80.
    assert body["compliance_capped"] is False and body["composite"] == 80.0

    cal = db.execute(text("SELECT verdict FROM calibration_examples")).scalar_one()
    assert cal == "false_positive"


def test_cannot_dispute_a_non_open_flag(db):
    flag_id = _seed_scored_call(db)
    client.post(f"/flags/{flag_id}/dispute", json={})
    again = client.post(f"/flags/{flag_id}/dispute", json={})
    assert again.status_code == 409


def test_call_detail_and_ops_endpoints(db):
    _seed_scored_call(db)
    detail = client.get("/calls/1").json()
    assert detail["call"]["composite"] == 40.0
    assert len(detail["scores"]) == 5 and len(detail["flags"]) == 1

    ops = client.get("/ops/jobs").json()
    assert "summary" in ops
