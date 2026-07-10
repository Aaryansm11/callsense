"""POST /disputes/{id}/resolve — a TL upholds/dismisses; score recomputes."""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.schemas import DisputeResolve
from db.session import get_db
from feedback import DisputeError, resolve_dispute

router = APIRouter(tags=["disputes"])


@router.post("/disputes/{dispute_id}/resolve")
def resolve(
    dispute_id: int, body: DisputeResolve, db: Session = Depends(get_db)
) -> dict:
    try:
        result = resolve_dispute(
            db, dispute_id, body.resolution, body.resolved_by, body.resolution_note
        )
        db.commit()
    except DisputeError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return asdict(result)
