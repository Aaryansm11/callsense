"""POST /flags/{id}/dispute — an advisor disputes a flag (open -> disputed)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.schemas import DisputeCreate
from db.session import get_db
from feedback import DisputeError, raise_dispute

router = APIRouter(tags=["disputes"])


@router.post("/flags/{flag_id}/dispute")
def dispute_flag(
    flag_id: int, body: DisputeCreate, db: Session = Depends(get_db)
) -> dict:
    try:
        dispute_id = raise_dispute(db, flag_id, body.note, body.raised_by)
        db.commit()
    except DisputeError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"dispute_id": dispute_id, "flag_id": flag_id, "state": "disputed"}
