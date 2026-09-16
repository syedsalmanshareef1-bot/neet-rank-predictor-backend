"""
Rank prediction engine — a direct port of runRankPredictor() from the
original frontend, with results now coming from Postgres instead of an
in-browser array.

Original behaviour, preserved exactly:
  1. Filter records by exam/state/authority/course/category/quota (any
     blank filter is ignored, exact match on the others).
  2. Across every (year, round) on file for those records, a "hit" is any
     round whose close_rank is >= the entered rank (i.e. this rank would
     have cleared that round historically).
  3. Hits are sorted by closing rank ascending, then de-duplicated to the
     single tightest (lowest) closing-rank match per
     institute + course + category — exactly as the frontend's
     `dupKey = institute + course + category` de-dup did.
  4. Two distinct "no result" messages are preserved: no records matched
     the filters at all, vs. records matched but none had a close_rank
     reaching this rank.

Added (additive, does not change which rows qualify): a "chance" label
and margin percentage per result, since raw closing-rank numbers alone
don't tell a student how comfortable a match is.
"""
from dataclasses import dataclass

from sqlalchemy.orm import Session
from sqlalchemy import and_

from app import models
from app.schemas import PredictionFilters, PredictionResult


@dataclass
class PredictionOutcome:
    total_matching_records: int
    results: list[PredictionResult]
    message: str | None


def _chance_label(rank: int, close_rank: int) -> tuple[str, float]:
    if close_rank <= 0:
        return "Borderline", 0.0
    margin = (close_rank - rank) / close_rank
    margin_pct = round(margin * 100, 1)
    if margin > 0.20:
        return "High Chance", margin_pct
    if margin > 0.05:
        return "Moderate Chance", margin_pct
    return "Borderline", margin_pct


def _base_query(db: Session, filters: PredictionFilters):
    q = db.query(models.CutoffRecord)
    if filters.exam:
        q = q.join(models.Exam).filter(models.Exam.name == filters.exam)
    if filters.state:
        q = q.join(models.State, models.CutoffRecord.state_id == models.State.id).filter(
            models.State.name == filters.state
        )
    if filters.authority:
        q = q.join(models.Authority).filter(models.Authority.name == filters.authority)
    if filters.course:
        q = q.join(models.Course).filter(models.Course.name == filters.course)
    if filters.category:
        q = q.join(models.Category).filter(models.Category.code == filters.category)
    if filters.quota:
        q = q.join(models.Quota).filter(models.Quota.name == filters.quota)
    return q


def predict(db: Session, rank: int, filters: PredictionFilters, limit: int = 500) -> PredictionOutcome:
    matching_records = _base_query(db, filters).all()

    if not matching_records:
        return PredictionOutcome(
            total_matching_records=0,
            results=[],
            message=(
                "No historical records match these filters at all — insufficient data to predict "
                "anything here. Import more cutoff data for this state/course/category to enable a "
                "prediction."
            ),
        )

    record_ids = [r.id for r in matching_records]
    round_q = (
        db.query(models.RoundResult, models.CutoffRecord)
        .join(models.CutoffRecord, models.RoundResult.cutoff_record_id == models.CutoffRecord.id)
        .filter(
            and_(
                models.RoundResult.cutoff_record_id.in_(record_ids),
                models.RoundResult.close_rank >= rank,
            )
        )
        .order_by(models.RoundResult.close_rank.asc())
    )
    hits = round_q.all()

    if not hits:
        return PredictionOutcome(
            total_matching_records=len(matching_records),
            results=[],
            message=(
                f"{len(matching_records):,} historical record(s) matched your filters, but none had a "
                f"closing rank at or beyond {rank:,} in any year/round on file. Based on actual data, "
                "this rank has not historically closed a seat under these filters — this is not a "
                "guess, just what is (and isn't) in the database yet."
            ),
        )

    seen: set[tuple] = set()
    results: list[PredictionResult] = []
    for round_result, record in hits:
        dedup_key = (record.college_id, record.course_id, record.category_id)
        if dedup_key in seen:
            continue
        seen.add(dedup_key)

        chance, margin_pct = _chance_label(rank, round_result.close_rank)
        results.append(
            PredictionResult(
                institute=record.college.name if record.college else "Unknown",
                state=record.state.name if record.state else None,
                authority=record.authority.name if record.authority else None,
                course=record.course.name if record.course else None,
                category=record.category.code if record.category else None,
                quota=record.quota.name if record.quota else None,
                seat_type=record.seat_type,
                fee=record.fee,
                year=round_result.year,
                round=round_result.round_name,
                open_rank=round_result.open_rank,
                close_rank=round_result.close_rank,
                chance=chance,
                margin_percent=margin_pct,
            )
        )
        if len(results) >= limit:
            break

    return PredictionOutcome(total_matching_records=len(matching_records), results=results, message=None)
