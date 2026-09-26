"""
Rank prediction engine.

A student describes themselves (rank, home/domicile state, category, PwD,
gender) and where they want to be counselled (a state, or "any state I'm
eligible for") and optionally a course. For every cutoff record we decide,
using app/services/seat_rules.py, whether that student could actually be
allotted that seat — e.g. a Karnataka student looking at Maharashtra only
sees Maharashtra seats that are open to all-India candidates, and competes
there as General.

Each eligible record is then compared with its historical closing ranks:

  * it qualifies if the rank is within the closing rank of ANY year/round
    on file (i.e. this rank has actually got that seat before);
  * the chance label is based on the MOST RECENT year on file:
      High      – rank is within that year's first-round closing rank, or
                  at least 20% inside that year's final closing rank
      Moderate  – rank is within that year's final (last round) closing rank
      Borderline– rank only cleared an older year, or is within 5% of the edge

Results are one card per institute + course. When a student qualifies for
the same institute + course through several quotas/categories, the best
route (best chance; government before private at equal chance) is shown
and the rest are counted in `other_routes`.

Nothing is estimated or interpolated: every number shown is a closing rank
that exists in the database.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field

from sqlalchemy.orm import Session, joinedload

from app import models
from app.schemas import PredictionFilters, PredictionResult
from app.services import seat_rules as rules

CHANCE_ORDER = {"High Chance": 0, "Moderate Chance": 1, "Borderline": 2}
# When one institute+course is reachable through several seats with the same
# chance, prefer the cheaper / less restrictive route.
ROUTE_PREFERENCE = {
    rules.GOVERNMENT: 0, rules.IN_SERVICE: 1, rules.INSTITUTIONAL: 1, rules.SPECIAL: 1,
    rules.MINORITY: 2, rules.PRIVATE: 3, rules.NRI: 4,
}


# ---------------------------------------------------------------------------
# In-memory snapshot of every record (rebuilt after any admin import)
# ---------------------------------------------------------------------------
@dataclass
class SnapRecord:
    id: int
    institute: str
    state: str | None
    authority: str | None
    exam: str | None
    course: str | None
    category: str | None
    quota: str | None
    cutoff_quota: str | None
    seat_type_raw: str | None
    fee: float | None
    info: rules.SeatInfo
    # (year, round_name, open, close), sorted by year then round
    rounds: list[tuple[int, str, int | None, int]] = field(default_factory=list)


_snapshot: list[SnapRecord] | None = None
_lock = threading.Lock()


def invalidate_snapshot() -> None:
    global _snapshot
    _snapshot = None


def _round_sort_key(name: str) -> int:
    if name == "Final":
        return 99
    digits = "".join(ch for ch in name if ch.isdigit())
    return int(digits) if digits else 50


def _load_snapshot(db: Session) -> list[SnapRecord]:
    global _snapshot
    if _snapshot is not None:
        return _snapshot
    with _lock:
        if _snapshot is not None:
            return _snapshot
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
        out: list[SnapRecord] = []
        for r in records:
            if not r.rounds:
                continue
            state = r.state.name if r.state else None
            quota = r.quota.name if r.quota else None
            category = r.category.code if r.category else None
            rounds = sorted(
                ((rr.year, rr.round_name, rr.open_rank, rr.close_rank) for rr in r.rounds),
                key=lambda t: (t[0], _round_sort_key(t[1])),
            )
            out.append(
                SnapRecord(
                    id=r.id,
                    institute=r.college.name if r.college else "Unknown",
                    state=state,
                    authority=r.authority.name if r.authority else None,
                    exam=r.exam.name if r.exam else None,
                    course=r.course.name if r.course else None,
                    category=category,
                    quota=quota,
                    cutoff_quota=r.cutoff_quota,
                    seat_type_raw=r.seat_type,
                    fee=r.fee,
                    info=rules.classify(state, quota, r.cutoff_quota, category),
                    rounds=rounds,
                )
            )
        _snapshot = out
        return out


def snapshot(db: Session) -> list[SnapRecord]:
    return _load_snapshot(db)


# ---------------------------------------------------------------------------
# Prediction
# ---------------------------------------------------------------------------
@dataclass
class PredictionOutcome:
    total_matching_records: int
    total_eligible_records: int
    results: list[PredictionResult]
    message: str | None
    summary: dict


def _evaluate(rank: int, rec: SnapRecord):
    """Returns (chance, margin_pct, ref_round, cleared, latest_rounds) or None."""
    cleared = [(y, rn, c) for (y, rn, _o, c) in rec.rounds if c >= rank]
    if not cleared:
        return None
    latest_year = rec.rounds[-1][0]
    latest = [t for t in rec.rounds if t[0] == latest_year]
    first_close = latest[0][3]
    final = latest[-1]
    final_close = final[3]
    margin = (final_close - rank) / final_close if final_close > 0 else 0.0

    if rank <= final_close:
        if rank <= first_close or margin > 0.20:
            chance = "High Chance"
        elif margin > 0.05:
            chance = "Moderate Chance"
        else:
            chance = "Borderline"
        ref = final
    else:
        chance = "Borderline"
        # the most recent round that this rank did clear
        y, rn, c = cleared[-1]
        ref = next(t for t in rec.rounds if t[0] == y and t[1] == rn)
        margin = (c - rank) / c if c > 0 else 0.0
    return chance, round(margin * 100, 1), ref, cleared, latest


def predict(db: Session, rank: int, filters: PredictionFilters, limit: int = 500) -> PredictionOutcome:
    data = _load_snapshot(db)

    home_state = filters.home_state or None
    target_state = filters.state or None
    seat_types = set(filters.seat_types or rules.DEFAULT_SEAT_TYPES)
    student_cat = (filters.student_category or "").lower() or None
    is_female = (filters.gender or "").lower() == "female"

    # 1) plain filters (exact match on anything the caller set)
    def base_ok(r: SnapRecord) -> bool:
        if filters.exam and r.exam != filters.exam:
            return False
        if target_state and r.state != target_state:
            return False
        if filters.authority and r.authority != filters.authority:
            return False
        if filters.course and r.course != filters.course:
            return False
        if filters.category and r.category != filters.category:
            return False
        if filters.quota and filters.quota not in (r.quota, r.cutoff_quota, r.info.quota_label):
            return False
        return True

    matching = [r for r in data if base_ok(r)]
    if not matching:
        return PredictionOutcome(
            0, 0, [],
            "No cutoff records exist for this state/course combination yet, so there is nothing to "
            "predict from. Try a different course or counselling state.",
            {},
        )

    # 2) eligibility for this student
    use_profile = bool(home_state or student_cat or filters.seat_types or filters.is_pwd or filters.gender)
    if use_profile:
        eligible = [
            r for r in matching
            if rules.student_can_take(
                r.info,
                seat_state=r.state,
                home_state=home_state,
                student_category=student_cat,
                is_pwd=bool(filters.is_pwd),
                is_female=is_female,
                seat_types=seat_types,
            )
        ]
    else:
        eligible = matching

    if not eligible:
        where = target_state or "the selected states"
        msg = (
            f"There are {len(matching):,} seat record(s) in {where} for these filters, but none that a "
            f"student with your profile is eligible for."
        )
        if home_state and target_state and home_state != target_state:
            msg += (
                f" As a {home_state} candidate you can only take {target_state} seats that are open to "
                f"all-India candidates (usually private/management), and you compete there as General. "
                f"Try adding the NRI or other seat types, or a different course."
            )
        return PredictionOutcome(len(matching), 0, [], msg, {})

    # 3) compare the rank with history; keep the best route per institute+course
    best: dict[tuple, tuple] = {}
    routes: dict[tuple, int] = {}
    for r in eligible:
        ev = _evaluate(rank, r)
        if ev is None:
            continue
        chance, margin_pct, ref, cleared, latest = ev
        key = (r.state, r.institute, r.course)
        routes[key] = routes.get(key, 0) + 1
        score = (CHANCE_ORDER[chance], ROUTE_PREFERENCE.get(r.info.seat_type, 5), -margin_pct)
        cur = best.get(key)
        if cur is None or score < cur[0]:
            best[key] = (score, r, chance, margin_pct, ref, cleared, latest)

    if not best:
        return PredictionOutcome(
            len(matching), len(eligible), [],
            f"You are eligible for {len(eligible):,} seat record(s) under these filters, but a rank of "
            f"{rank:,} has not got any of them in the years/rounds on file. Try a different course, "
            f"add more seat types, or widen the counselling state.",
            {},
        )

    ordered = sorted(best.values(), key=lambda t: (t[0][0], t[4][3]))
    summary = {"High Chance": 0, "Moderate Chance": 0, "Borderline": 0}
    for t in ordered:
        summary[t[2]] += 1

    results: list[PredictionResult] = []
    for score, r, chance, margin_pct, ref, cleared, latest in ordered[:limit]:
        key = (r.state, r.institute, r.course)
        info = r.info
        results.append(
            PredictionResult(
                institute=r.institute,
                state=r.state,
                authority=r.authority,
                course=r.course,
                category=r.category,
                quota=info.quota_label,
                seat_type=rules.SEAT_TYPE_LABELS.get(info.seat_type, info.seat_type),
                fee=r.fee,
                year=ref[0],
                round=ref[1],
                open_rank=ref[2],
                close_rank=ref[3],
                chance=chance,
                margin_percent=margin_pct,
                open_to_all_india=info.open_to_all_india,
                category_group=info.category_group,
                latest_year=latest[0][0],
                latest_year_rounds={rn: c for (_y, rn, _o, c) in latest},
                cleared_in=[f"{y} {rn}" for (y, rn, _c) in cleared],
                other_routes=routes[key] - 1,
            )
        )

    return PredictionOutcome(len(matching), len(eligible), results, None, summary)
