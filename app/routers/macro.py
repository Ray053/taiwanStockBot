from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.macro_snapshot import MacroSnapshot
from app.schemas.macro import MacroSnapshotResponse

router = APIRouter(prefix="/macro", tags=["macro"])


@router.get("/latest", response_model=MacroSnapshotResponse)
def get_latest_macro(db: Session = Depends(get_db)):
    """Get the latest Polymarket macro snapshot."""
    snap = (
        db.query(MacroSnapshot)
        .order_by(MacroSnapshot.snapshot_date.desc())
        .first()
    )
    if not snap:
        raise HTTPException(status_code=404, detail="No macro snapshot found")
    return MacroSnapshotResponse.model_validate(snap)


@router.get("/history", response_model=list[MacroSnapshotResponse])
def get_macro_history(
    days: int = 30,
    db: Session = Depends(get_db),
):
    """Get macro snapshot history for the last N days."""
    since = date.today() - timedelta(days=days)
    snaps = (
        db.query(MacroSnapshot)
        .filter(MacroSnapshot.snapshot_date >= since)
        .order_by(MacroSnapshot.snapshot_date.desc())
        .all()
    )
    return [MacroSnapshotResponse.model_validate(s) for s in snaps]
