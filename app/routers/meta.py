from typing import Optional

from fastapi import APIRouter, Depends, Query, Response
from pydantic import TypeAdapter
from sqlalchemy.orm import Session, joinedload

from app import models
from app.database import get_db
from app.deps import get_current_user
from app.services.predictor_service import invalidate_snapshot
from app.services.seat_rules import classify
from app.schemas import CollegeItem, CutoffBrowseRound, CutoffBrowseRow, NamedItem, RoundItem, YearItem

router = APIRouter(tags=["reference data"], dependencies=[Depends(get_current_user)])

# /cutoffs returns every record (~28k rows, ~11 MB of JSON) and takes several
# seconds to build, so the finished JSON is kept in memory and reused. Any
# admin import or conflict resolution clears it (see routers/admin.py), so
# the next request rebuilds it with the new data.
_cutoffs_json: Optional[bytes] = None
_cutoffs_adapter = TypeAdapter(list[CutoffBrowseRow])


def invalidate_cutoffs_cache() -> None:
    global _cutoffs_json
    _cutoffs_json = None
    invalidate_snapshot()


@router.get("/exams", response_model=list[NamedItem])
def list_exams(db: Session = Depends(get_db)):
    return db.query(models.Exam).order_by(models.Exam.name).all()


@router.get("/states", response_model=list[NamedItem])
def list_states(db: Session = Depends(get_db)):
    return db.query(models.State).order_by(models.State.name).all()


@router.get("/authorities", response_model=list[NamedItem])
def list_authorities(db: Session = Depends(get_db)):
    return db.query(models.Authority).order_by(models.Authority.name).all()


@router.get("/courses", response_model=list[NamedItem])
def list_courses(db: Session = Depends(get_db)):
    return db.query(models.Course).order_by(models.Course.name).all()


@router.get("/categories", response_model=list[NamedItem])
def list_categories(db: Session = Depends(get_db)):
    rows = db.query(models.Category).order_by(models.Category.code).all()
    return [NamedItem(id=r.id, name=r.code) for r in rows]


@router.get("/quotas", response_model=list[NamedItem])
def list_quotas(db: Session = Depends(get_db)):
    return db.query(models.Quota).order_by(models.Quota.name).all()


@router.get("/years", response_model=list[YearItem])
def list_years(db: Session = Depends(get_db)):
    rows = db.query(models.RoundResult.year).distinct().order_by(models.RoundResult.year.desc()).all()
    return [YearItem(year=r[0]) for r in rows]


@router.get("/rounds", response_model=list[RoundItem])
def list_rounds(
    year: Optional[int] = Query(default=None, description="Filter round names to a specific year"),
    db: Session = Depends(get_db),
):
    q = db.query(models.RoundResult.round_name).distinct()
    if year is not None:
        q = q.filter(models.RoundResult.year == year)
    rows = q.all()
    # Keep a stable, human-friendly order: R1..R5, then Final.
    order = {f"R{i}": i for i in range(1, 10)}
    order["Final"] = 99
    names = sorted({r[0] for r in rows}, key=lambda n: order.get(n, 50))
    return [RoundItem(round_name=n) for n in names]


@router.get("/colleges", response_model=list[CollegeItem])
def list_colleges(
    state: Optional[str] = Query(default=None),
    search: Optional[str] = Query(default=None, min_length=2, description="Partial, case-insensitive name match"),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    q = db.query(models.College)
    if state:
        q = q.join(models.State).filter(models.State.name == state)
    if search:
        q = q.filter(models.College.name.ilike(f"%{search}%"))
    rows = q.order_by(models.College.name).limit(limit).all()
    return [CollegeItem(id=c.id, name=c.name, state=c.state.name if c.state else None) for c in rows]


@router.get("/cutoffs", response_model=list[CutoffBrowseRow])
def list_cutoffs(db: Session = Depends(get_db)):
    """
    Every cutoff record with its full round-by-round history, shaped
    exactly like the Colleges page's original in-page data model (one row
    per institute+course+category+quota combo, with a `rounds` map keyed
    "<year>-<round>"). This is what makes the Colleges page's state grid
    and cutoff table backend-driven: any admin import (new year/round)
    shows up here immediately, with nothing to change on the frontend.
    """
    global _cutoffs_json
    if _cutoffs_json is not None:
        return Response(content=_cutoffs_json, media_type="application/json")

    records = (
        db.query(models.CutoffRecord)
        .options(
            joinedload(models.CutoffRecord.college),
            joinedload(models.CutoffRecord.state),
            joinedload(models.CutoffRecord.authority),
            joinedload(models.CutoffRecord.exam),
            joinedload(models.CutoffRecord.course),
            joinedload(models.CutoffRecord.category),
            joinedload(models.CutoffRecord.quota),
            joinedload(models.CutoffRecord.rounds),
        )
        .all()
    )

    out: list[CutoffBrowseRow] = []
    for r in records:
        rounds = {
            rr.round_key: CutoffBrowseRound(
                year=rr.year, round=rr.round_name, open=rr.open_rank, close=rr.close_rank
            )
            for rr in r.rounds
        }
        if not rounds:
            continue
        state = r.state.name if r.state else None
        quota = r.quota.name if r.quota else None
        category = r.category.code if r.category else None
        info = classify(state, quota, r.cutoff_quota, category)
        out.append(
            CutoffBrowseRow(
                institute=r.college.name if r.college else "",
                state=r.state.name if r.state else None,
                authority=r.authority.name if r.authority else None,
                exam=r.exam.name if r.exam else None,
                course=r.course.name if r.course else None,
                category=r.category.code if r.category else None,
                quota=r.quota.name if r.quota else None,
                cutoffQuota=r.cutoff_quota,
                fee=r.fee,
                rounds=rounds,
                quotaLabel=info.quota_label,
                seatType=info.seat_type,
                allIndia=info.open_to_all_india,
                categoryGroup=info.category_group,
            )
        )
    _cutoffs_json = _cutoffs_adapter.dump_json(out)
    return Response(content=_cutoffs_json, media_type="application/json")