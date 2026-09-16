"""
Database schema for the NEET Rank Predictor.

Design notes
------------
The original frontend stored every cutoff as a JS object keyed by:
    State + Authority + Exam + College + Course + Category + Quota + SeatType
with Year/Round living *inside* that record's `rounds` map (not part of
identity). That is exactly what CutoffRecord + RoundResult reproduce here:
one CutoffRecord per unique combination, with one RoundResult child row
per (year, round) that has ever been imported for it. This is what lets a
brand-new year/round for a college that already exists become a new
RoundResult row on the SAME CutoffRecord, instead of a duplicate record.

Lookup tables (State, Authority, Exam, College, Course, Category, Quota)
exist so the various dropdown/API endpoints are simple indexed queries
instead of `SELECT DISTINCT` scans over millions of rows, and so imports
can't silently introduce spelling variants of the same state/course/etc.
"""
import enum

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import relationship

from app.database import Base


# ---------------------------------------------------------------------------
# Lookup / reference tables
# ---------------------------------------------------------------------------
class State(Base):
    __tablename__ = "states"

    id = Column(Integer, primary_key=True)
    name = Column(String(120), unique=True, nullable=False, index=True)

    colleges = relationship("College", back_populates="state")


class Authority(Base):
    __tablename__ = "authorities"

    id = Column(Integer, primary_key=True)
    name = Column(String(150), unique=True, nullable=False, index=True)


class Exam(Base):
    __tablename__ = "exams"

    id = Column(Integer, primary_key=True)
    name = Column(String(50), unique=True, nullable=False, index=True)


class Course(Base):
    __tablename__ = "courses"

    id = Column(Integer, primary_key=True)
    name = Column(String(150), unique=True, nullable=False, index=True)


class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True)
    code = Column(String(50), unique=True, nullable=False, index=True)


class Quota(Base):
    __tablename__ = "quotas"

    id = Column(Integer, primary_key=True)
    name = Column(String(150), unique=True, nullable=False, index=True)


class College(Base):
    __tablename__ = "colleges"

    id = Column(Integer, primary_key=True)
    name = Column(String(300), nullable=False, index=True)
    normalized_name = Column(String(300), nullable=False, index=True)  # for fuzzy/loose matching
    state_id = Column(Integer, ForeignKey("states.id"), nullable=True, index=True)

    state = relationship("State", back_populates="colleges")

    __table_args__ = (
        UniqueConstraint("normalized_name", "state_id", name="uq_college_normname_state"),
    )


# ---------------------------------------------------------------------------
# Core fact table
# ---------------------------------------------------------------------------
class CutoffRecord(Base):
    """
    One unique (state, authority, exam, college, course, category, quota,
    seat_type) combination. Historical closing ranks for every year/round
    live in the linked RoundResult rows.
    """

    __tablename__ = "cutoff_records"

    id = Column(Integer, primary_key=True)

    state_id = Column(Integer, ForeignKey("states.id"), nullable=True, index=True)
    authority_id = Column(Integer, ForeignKey("authorities.id"), nullable=True, index=True)
    exam_id = Column(Integer, ForeignKey("exams.id"), nullable=True, index=True)
    college_id = Column(Integer, ForeignKey("colleges.id"), nullable=False, index=True)
    course_id = Column(Integer, ForeignKey("courses.id"), nullable=True, index=True)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=True, index=True)
    quota_id = Column(Integer, ForeignKey("quotas.id"), nullable=True, index=True)

    seat_type = Column(String(100), nullable=True)
    gender = Column(String(30), nullable=True)
    cutoff_quota = Column(String(150), nullable=True)
    fee = Column(Float, nullable=True)

    # Identity keys, precomputed at write time (mirrors strictKey()/looseKey()
    # in the original frontend). Used by the importer to find an existing
    # record to merge into instead of creating a duplicate.
    strict_key = Column(String(600), unique=True, nullable=False, index=True)
    loose_key = Column(String(500), nullable=False, index=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    state = relationship("State")
    authority = relationship("Authority")
    exam = relationship("Exam")
    college = relationship("College")
    course = relationship("Course")
    category = relationship("Category")
    quota = relationship("Quota")

    rounds = relationship(
        "RoundResult", back_populates="cutoff_record", cascade="all, delete-orphan"
    )
    conflicts = relationship(
        "ImportConflict", back_populates="cutoff_record", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index(
            "ix_cutoff_filter_combo",
            "exam_id", "state_id", "authority_id", "course_id", "category_id", "quota_id",
        ),
    )


class RoundResult(Base):
    """
    One (year, round) closing/opening rank for a CutoffRecord. Never
    overwritten in place on conflicting re-import — see ImportConflict.
    """

    __tablename__ = "round_results"

    id = Column(Integer, primary_key=True)
    cutoff_record_id = Column(Integer, ForeignKey("cutoff_records.id"), nullable=False, index=True)

    round_key = Column(String(30), nullable=False)   # e.g. "2025-R2" or "2025-Final"
    year = Column(Integer, nullable=False, index=True)
    round_name = Column(String(20), nullable=False, index=True)  # "R1".."R5" or "Final"

    open_rank = Column(Integer, nullable=True)
    close_rank = Column(Integer, nullable=False, index=True)

    source_file = Column(String(300), nullable=True)
    import_log_id = Column(Integer, ForeignKey("import_logs.id"), nullable=True, index=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    cutoff_record = relationship("CutoffRecord", back_populates="rounds")
    import_log = relationship("ImportLog")

    __table_args__ = (
        UniqueConstraint("cutoff_record_id", "round_key", name="uq_round_per_record"),
        Index("ix_round_close_rank", "close_rank"),
        Index("ix_round_year_round", "year", "round_name"),
    )


class ImportConflict(Base):
    """
    Recorded whenever an incoming row disagrees with an existing round's
    closing/opening rank. Historical data is never silently overwritten;
    an admin must resolve the conflict explicitly.
    """

    __tablename__ = "import_conflicts"

    id = Column(Integer, primary_key=True)
    cutoff_record_id = Column(Integer, ForeignKey("cutoff_records.id"), nullable=False, index=True)
    round_key = Column(String(30), nullable=False)

    existing_open = Column(Integer, nullable=True)
    existing_close = Column(Integer, nullable=True)
    incoming_open = Column(Integer, nullable=True)
    incoming_close = Column(Integer, nullable=True)

    import_log_id = Column(Integer, ForeignKey("import_logs.id"), nullable=True, index=True)
    resolved = Column(Boolean, default=False, nullable=False)
    resolution = Column(String(20), nullable=True)  # "kept_existing" | "used_incoming"
    resolved_by = Column(String(150), nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    cutoff_record = relationship("CutoffRecord", back_populates="conflicts")


# ---------------------------------------------------------------------------
# Admin / import audit
# ---------------------------------------------------------------------------
class ImportStatus(str, enum.Enum):
    pending = "pending"
    success = "success"
    partial = "partial"
    failed = "failed"


class ImportLog(Base):
    """
    One row per admin data upload. Satisfies the requirement that every
    update be logged with year, round, source, and update time.
    """

    __tablename__ = "import_logs"

    id = Column(Integer, primary_key=True)
    filename = Column(String(300), nullable=False)
    file_format = Column(String(10), nullable=False)  # csv | xlsx | json
    source_label = Column(String(300), nullable=True)  # e.g. "KEA official round-wise PDF"
    year = Column(Integer, nullable=True)
    round_name = Column(String(20), nullable=True)

    uploaded_by = Column(String(150), nullable=False)
    status = Column(Enum(ImportStatus), default=ImportStatus.pending, nullable=False)

    rows_total = Column(Integer, default=0)
    records_added = Column(Integer, default=0)
    records_updated = Column(Integer, default=0)
    duplicates_skipped = Column(Integer, default=0)
    conflicts_flagged = Column(Integer, default=0)
    rows_rejected = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)

    started_at = Column(DateTime(timezone=True), server_default=func.now())
    finished_at = Column(DateTime(timezone=True), nullable=True)


class AdminUser(Base):
    __tablename__ = "admin_users"

    id = Column(Integer, primary_key=True)
    username = Column(String(100), unique=True, nullable=False, index=True)
    hashed_password = Column(String(300), nullable=False)
    role = Column(String(30), default="admin", nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
