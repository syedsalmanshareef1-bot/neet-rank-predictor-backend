"""
get_or_create helpers for the small reference/lookup tables. Centralizing
these means every import path (CSV, XLSX, JSON, the seed script) creates
lookup rows the exact same way, so "Uttar Pradesh" typed two different ways
in two different files still resolves to one State row.
"""
from functools import lru_cache

from sqlalchemy.orm import Session

from app import models
from app.services.normalize import norm_field, norm_inst


class LookupCache:
    """
    Per-import in-memory cache of lookup rows, keyed by normalized name.
    Avoids a round trip to the DB for every single row in a 27,000-row file
    while still being correct: cache is seeded lazily and always writes
    through to the DB on a miss.
    """

    def __init__(self, db: Session):
        self.db = db
        self._states: dict[str, models.State] = {}
        self._authorities: dict[str, models.Authority] = {}
        self._exams: dict[str, models.Exam] = {}
        self._courses: dict[str, models.Course] = {}
        self._categories: dict[str, models.Category] = {}
        self._quotas: dict[str, models.Quota] = {}
        self._colleges: dict[tuple[str, int | None], models.College] = {}

    def state(self, name: str | None) -> models.State | None:
        if not name:
            return None
        key = norm_field(name)
        if key in self._states:
            return self._states[key]
        obj = self.db.query(models.State).filter(models.State.name == name).one_or_none()
        if not obj:
            existing_all = self.db.query(models.State).all()
            obj = next((s for s in existing_all if norm_field(s.name) == key), None)
        if not obj:
            obj = models.State(name=name)
            self.db.add(obj)
            self.db.flush()
        self._states[key] = obj
        return obj

    def authority(self, name: str | None) -> models.Authority | None:
        if not name:
            return None
        key = norm_field(name)
        if key in self._authorities:
            return self._authorities[key]
        obj = self.db.query(models.Authority).filter(models.Authority.name == name).one_or_none()
        if not obj:
            existing_all = self.db.query(models.Authority).all()
            obj = next((a for a in existing_all if norm_field(a.name) == key), None)
        if not obj:
            obj = models.Authority(name=name)
            self.db.add(obj)
            self.db.flush()
        self._authorities[key] = obj
        return obj

    def exam(self, name: str | None) -> models.Exam | None:
        if not name:
            return None
        key = norm_field(name)
        if key in self._exams:
            return self._exams[key]
        obj = self.db.query(models.Exam).filter(models.Exam.name == name).one_or_none()
        if not obj:
            existing_all = self.db.query(models.Exam).all()
            obj = next((e for e in existing_all if norm_field(e.name) == key), None)
        if not obj:
            obj = models.Exam(name=name)
            self.db.add(obj)
            self.db.flush()
        self._exams[key] = obj
        return obj

    def course(self, name: str | None) -> models.Course | None:
        if not name:
            return None
        key = norm_field(name)
        if key in self._courses:
            return self._courses[key]
        obj = self.db.query(models.Course).filter(models.Course.name == name).one_or_none()
        if not obj:
            existing_all = self.db.query(models.Course).all()
            obj = next((c for c in existing_all if norm_field(c.name) == key), None)
        if not obj:
            obj = models.Course(name=name)
            self.db.add(obj)
            self.db.flush()
        self._courses[key] = obj
        return obj

    def category(self, code: str | None) -> models.Category | None:
        if not code:
            return None
        key = norm_field(code)
        if key in self._categories:
            return self._categories[key]
        obj = self.db.query(models.Category).filter(models.Category.code == code).one_or_none()
        if not obj:
            existing_all = self.db.query(models.Category).all()
            obj = next((c for c in existing_all if norm_field(c.code) == key), None)
        if not obj:
            obj = models.Category(code=code)
            self.db.add(obj)
            self.db.flush()
        self._categories[key] = obj
        return obj

    def quota(self, name: str | None) -> models.Quota | None:
        if not name:
            return None
        key = norm_field(name)
        if key in self._quotas:
            return self._quotas[key]
        obj = self.db.query(models.Quota).filter(models.Quota.name == name).one_or_none()
        if not obj:
            existing_all = self.db.query(models.Quota).all()
            obj = next((q for q in existing_all if norm_field(q.name) == key), None)
        if not obj:
            obj = models.Quota(name=name)
            self.db.add(obj)
            self.db.flush()
        self._quotas[key] = obj
        return obj

    def college(self, name: str | None, state: models.State | None) -> models.College | None:
        if not name:
            return None
        norm_name = norm_inst(name)
        state_id = state.id if state else None
        cache_key = (norm_name, state_id)
        if cache_key in self._colleges:
            return self._colleges[cache_key]
        obj = (
            self.db.query(models.College)
            .filter(models.College.normalized_name == norm_name, models.College.state_id == state_id)
            .one_or_none()
        )
        if not obj:
            obj = models.College(name=name, normalized_name=norm_name, state_id=state_id)
            self.db.add(obj)
            self.db.flush()
        self._colleges[cache_key] = obj
        return obj
