from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import models
from app.database import get_db
from app.deps import get_current_user
from app.schemas import PredictionRequest, PredictionResponse
from app.services.predictor_service import predict

router = APIRouter(tags=["predictor"])


@router.post("/predict", response_model=PredictionResponse)
def predict_rank(
    payload: PredictionRequest,
    db: Session = Depends(get_db),
    user: models.AdminUser = Depends(get_current_user),
):
    """
    Given a rank and optional filters (exam, state, authority, course,
    category, quota), returns every college/course combination whose
    historical closing rank the entered rank would have cleared — sorted
    by closing rank, one best (tightest) match per college+course+category,
    exactly as the original in-browser predictor behaved.
    """
    outcome = predict(db, rank=payload.rank, filters=payload.filters, limit=payload.limit)
    return PredictionResponse(
        rank_checked=payload.rank,
        filters_applied=payload.filters.model_dump(exclude_none=True, by_alias=True),
        total_matching_records=outcome.total_matching_records,
        total_results=len(outcome.results),
        results=outcome.results,
        message=outcome.message,
    )