from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import models
from app.database import get_db
from app.schemas import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health_check(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        db_status = "ok"
        total_records = db.query(models.CutoffRecord).count()
        total_rounds = db.query(models.RoundResult).count()
    except Exception as exc:  # noqa: BLE001 - health check must never itself throw a 500
        return HealthResponse(status="degraded", database=f"error: {exc}")

    return HealthResponse(
        status="ok",
        database=db_status,
        total_cutoff_records=total_records,
        total_round_results=total_rounds,
    )
