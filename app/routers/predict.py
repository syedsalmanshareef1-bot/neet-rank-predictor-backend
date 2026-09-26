from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import models
from app.database import get_db
from app.deps import get_current_user
from app.schemas import NamedItem, PredictionRequest, PredictionResponse, PredictOptions
from app.services import seat_rules as rules
from app.services.predictor_service import predict, snapshot

router = APIRouter(tags=["predictor"])

ALL_STATES = [
    "Andaman & Nicobar", "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chandigarh",
    "Chhattisgarh", "Dadra & Nagar Haveli", "Delhi", "Goa", "Gujarat", "Haryana", "Himachal Pradesh",
    "Jammu & Kashmir", "Jharkhand", "Karnataka", "Kerala", "Ladakh", "Lakshadweep", "Madhya Pradesh",
    "Maharashtra", "Manipur", "Meghalaya", "Mizoram", "Nagaland", "Odisha", "Puducherry", "Punjab",
    "Rajasthan", "Sikkim", "Tamil Nadu", "Telangana", "Tripura", "Uttar Pradesh", "Uttarakhand",
    "West Bengal",
]


@router.get("/predict/options", response_model=PredictOptions)
def predict_options(db: Session = Depends(get_db), user: models.AdminUser = Depends(get_current_user)):
    """Everything the predictor form needs: states, courses (overall and per
    counselling state), student categories and seat types."""
    data = snapshot(db)
    by_state: dict[str, set[str]] = {}
    quotas: dict[str, dict[str, dict]] = {}
    for r in data:
        if r.state and r.course:
            by_state.setdefault(r.state, set()).add(r.course)
        if r.state:
            q = quotas.setdefault(r.state, {}).setdefault(
                r.info.quota_label, {"name": r.info.quota_label, "seat_type": r.info.seat_type, "all_india": False}
            )
            q["all_india"] = q["all_india"] or r.info.open_to_all_india
    all_courses = sorted({c for cs in by_state.values() for c in cs})
    home = sorted(set(ALL_STATES) | set(by_state))
    return PredictOptions(
        home_states=home,
        counselling_states=sorted(by_state),
        courses=all_courses,
        courses_by_state={s: sorted(cs) for s, cs in by_state.items()},
        quotas_by_state={s: sorted(qs.values(), key=lambda q: q["name"]) for s, qs in quotas.items()},
        student_categories=[
            NamedItem(id=i, name=c) for i, c in enumerate(rules.STUDENT_CATEGORIES, start=1)
        ],
        seat_types=[
            {"id": k, "label": v, "default": k in rules.DEFAULT_SEAT_TYPES}
            for k, v in rules.SEAT_TYPE_LABELS.items()
        ],
    )


@router.post("/predict", response_model=PredictionResponse)
def predict_rank(
    payload: PredictionRequest,
    db: Session = Depends(get_db),
    user: models.AdminUser = Depends(get_current_user),
):
    """
    Given a rank and the student's profile (home state, category, PwD,
    gender, seat types) plus where to look (counselling state, course),
    returns every institute + course the student is eligible for whose
    historical closing rank this rank has reached — one result per
    institute + course, best route first.
    """
    outcome = predict(db, rank=payload.rank, filters=payload.filters, limit=payload.limit)
    return PredictionResponse(
        rank_checked=payload.rank,
        filters_applied=payload.filters.model_dump(exclude_none=True, by_alias=True),
        total_matching_records=outcome.total_matching_records,
        total_eligible_records=outcome.total_eligible_records,
        total_results=len(outcome.results),
        summary=outcome.summary,
        results=outcome.results,
        message=outcome.message,
    )
