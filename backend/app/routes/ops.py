"""Ops view: pipeline job status + re-queue a dead-lettered job."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from db.session import get_db

router = APIRouter(prefix="/ops", tags=["ops"])


@router.get("/jobs")
def list_jobs(status: str | None = None, limit: int = 100,
              db: Session = Depends(get_db)) -> dict:
    where = "WHERE status = :status" if status else ""
    rows = db.execute(
        text(
            f"""
            SELECT j.id, j.call_id, j.stage, j.status, j.attempts, j.max_attempts,
                   j.last_error, j.run_after, j.updated_at
            FROM processing_jobs j {where}
            ORDER BY j.updated_at DESC LIMIT :lim
            """
        ),
        {"status": status, "lim": limit} if status else {"lim": limit},
    ).mappings().all()

    summary = db.execute(
        text("SELECT status, count(*) AS n FROM processing_jobs GROUP BY status")
    ).mappings().all()

    return {
        "summary": {r["status"]: r["n"] for r in summary},
        "jobs": [dict(r) for r in rows],
    }


@router.post("/jobs/{job_id}/requeue")
def requeue(job_id: int, db: Session = Depends(get_db)) -> dict:
    row = db.execute(
        text("SELECT status FROM processing_jobs WHERE id = :id"), {"id": job_id}
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="job not found")
    if row.status != "dead":
        raise HTTPException(status_code=409, detail="only dead jobs can be requeued")
    db.execute(
        text(
            "UPDATE processing_jobs SET status='pending', attempts=0, "
            "last_error=NULL, run_after=now(), updated_at=now() WHERE id=:id"
        ),
        {"id": job_id},
    )
    db.commit()
    return {"job_id": job_id, "status": "pending"}
