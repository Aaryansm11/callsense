"""Role-scoped rollup views: Director (org), Team Leader (team), Advisor."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from db.session import get_db

router = APIRouter(tags=["summaries"])


@router.get("/advisors")
def list_advisors(db: Session = Depends(get_db)) -> list[dict]:
    """Advisor directory for the upload picker — so a manually uploaded call can
    be attributed to a real advisor (not hardcoded). In production the source
    payload carries the agent ref; this endpoint mirrors that choice in the UI."""
    rows = db.execute(
        text(
            """
            SELECT a.id, a.name, t.name AS team_name,
                   (a.external_ids ->> 0) AS external_id
            FROM advisors a JOIN teams t ON t.id = a.team_id
            ORDER BY a.id
            """
        )
    ).mappings().all()
    return [dict(r) for r in rows]


@router.get("/orgs/{org_id}/summary")
def org_summary(org_id: int, db: Session = Depends(get_db)) -> dict:
    org = db.execute(
        text("SELECT * FROM v_org_scores WHERE org_id = :id"), {"id": org_id}
    ).mappings().first()
    if org is None:
        raise HTTPException(status_code=404, detail="org not found")

    kpis = db.execute(
        text(
            """
            SELECT
              (SELECT count(*) FROM calls c WHERE c.org_id = :id
                 AND c.status = 'done') AS calls_processed,
              (SELECT count(*) FROM flags f JOIN calls c ON c.id = f.call_id
                 WHERE c.org_id = :id AND f.severity = 'critical'
                 AND f.created_at > now() - interval '7 days') AS critical_flags_week,
              (SELECT count(*) FROM flags f JOIN calls c ON c.id = f.call_id
                 WHERE c.org_id = :id AND f.state = 'disputed') AS open_disputes
            """
        ),
        {"id": org_id},
    ).mappings().first()

    teams = db.execute(
        text("SELECT * FROM v_team_scores WHERE org_id = :id ORDER BY avg_composite DESC NULLS LAST"),
        {"id": org_id},
    ).mappings().all()

    trend = db.execute(
        text(
            """
            SELECT date_trunc('day', c.called_at)::date AS day,
                   round(avg(cs.composite)::numeric, 1) AS avg_composite
            FROM calls c JOIN call_scores cs ON cs.call_id = c.id
            WHERE c.org_id = :id AND c.called_at IS NOT NULL
            GROUP BY 1 ORDER BY 1
            """
        ),
        {"id": org_id},
    ).mappings().all()

    risk_feed = db.execute(
        text(
            """
            SELECT f.id AS flag_id, f.call_id, f.tag, f.quote, f.created_at,
                   a.name AS advisor_name
            FROM flags f JOIN calls c ON c.id = f.call_id
            LEFT JOIN advisors a ON a.id = c.advisor_id
            WHERE c.org_id = :id AND f.severity = 'critical'
            ORDER BY f.created_at DESC LIMIT 10
            """
        ),
        {"id": org_id},
    ).mappings().all()

    return {
        "org": dict(org),
        "kpis": dict(kpis),
        "teams": [dict(t) for t in teams],
        "trend": [dict(t) for t in trend],
        "risk_feed": [dict(r) for r in risk_feed],
    }


@router.get("/teams/{team_id}/summary")
def team_summary(team_id: int, db: Session = Depends(get_db)) -> dict:
    team = db.execute(
        text("SELECT * FROM v_team_scores WHERE team_id = :id"), {"id": team_id}
    ).mappings().first()
    if team is None:
        raise HTTPException(status_code=404, detail="team not found")

    leaderboard = db.execute(
        text("SELECT * FROM v_advisor_scores WHERE team_id = :id "
             "ORDER BY avg_composite DESC NULLS LAST"),
        {"id": team_id},
    ).mappings().all()

    # Per-advisor, per-dimension averages for the coaching heatmap.
    heatmap = db.execute(
        text(
            """
            SELECT a.id AS advisor_id, a.name AS advisor_name, s.dimension,
                   round(avg(s.raw_score)::numeric, 2) AS avg_score
            FROM advisors a
            JOIN calls c ON c.advisor_id = a.id
            JOIN scores s ON s.call_id = c.id
            WHERE a.team_id = :id
            GROUP BY a.id, a.name, s.dimension
            ORDER BY a.name, s.dimension
            """
        ),
        {"id": team_id},
    ).mappings().all()

    dispute_inbox = db.execute(
        text(
            """
            SELECT d.id AS dispute_id, d.flag_id, d.note, d.created_at,
                   f.call_id, f.tag, f.quote, f.start_s, a.name AS advisor_name
            FROM disputes d
            JOIN flags f ON f.id = d.flag_id
            JOIN calls c ON c.id = f.call_id
            LEFT JOIN advisors a ON a.id = c.advisor_id
            WHERE a.team_id = :id AND f.state = 'disputed'
            ORDER BY d.created_at
            """
        ),
        {"id": team_id},
    ).mappings().all()

    return {
        "team": dict(team),
        "leaderboard": [dict(r) for r in leaderboard],
        "heatmap": [dict(h) for h in heatmap],
        "dispute_inbox": [dict(d) for d in dispute_inbox],
    }


@router.get("/advisors/{advisor_id}/summary")
def advisor_summary(advisor_id: int, db: Session = Depends(get_db)) -> dict:
    advisor = db.execute(
        text("SELECT * FROM v_advisor_scores WHERE advisor_id = :id"),
        {"id": advisor_id},
    ).mappings().first()
    if advisor is None:
        raise HTTPException(status_code=404, detail="advisor not found")

    # Advisor per-dimension avg vs team per-dimension avg.
    dims = db.execute(
        text(
            """
            WITH me AS (
              SELECT s.dimension, avg(s.raw_score) AS my_avg
              FROM scores s JOIN calls c ON c.id = s.call_id
              WHERE c.advisor_id = :aid GROUP BY s.dimension
            ), team AS (
              SELECT s.dimension, avg(s.raw_score) AS team_avg
              FROM scores s JOIN calls c ON c.id = s.call_id
              JOIN advisors a ON a.id = c.advisor_id
              WHERE a.team_id = (SELECT team_id FROM advisors WHERE id = :aid)
              GROUP BY s.dimension
            )
            SELECT COALESCE(me.dimension, team.dimension) AS dimension,
                   round(me.my_avg::numeric, 2) AS my_avg,
                   round(team.team_avg::numeric, 2) AS team_avg
            FROM me FULL OUTER JOIN team ON me.dimension = team.dimension
            """
        ),
        {"aid": advisor_id},
    ).mappings().all()

    trend = db.execute(
        text(
            """
            SELECT c.called_at::date AS day, cs.composite
            FROM calls c JOIN call_scores cs ON cs.call_id = c.id
            WHERE c.advisor_id = :aid AND c.called_at IS NOT NULL
            ORDER BY c.called_at
            """
        ),
        {"aid": advisor_id},
    ).mappings().all()

    return {
        "advisor": dict(advisor),
        "dimensions": [dict(d) for d in dims],
        "trend": [dict(t) for t in trend],
    }


@router.get("/advisors/{advisor_id}/calls")
def advisor_calls(advisor_id: int, db: Session = Depends(get_db)) -> list[dict]:
    rows = db.execute(
        text(
            """
            SELECT c.id, c.status, c.called_at, c.duration_s,
                   cs.composite, cs.compliance_capped,
                   (SELECT count(*) FROM flags f WHERE f.call_id = c.id
                        AND f.severity = 'critical') AS critical_count
            FROM calls c LEFT JOIN call_scores cs ON cs.call_id = c.id
            WHERE c.advisor_id = :aid
            ORDER BY c.called_at DESC NULLS LAST, c.id DESC
            """
        ),
        {"aid": advisor_id},
    ).mappings().all()
    return [dict(r) for r in rows]
