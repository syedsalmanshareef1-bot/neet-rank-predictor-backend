from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Simple lookup schemas (states/courses/categories/quotas/authorities/exams)
# ---------------------------------------------------------------------------
class NamedItem(BaseModel):
    id: int
    name: str

    model_config = {"from_attributes": True}


class YearItem(BaseModel):
    year: int


class RoundItem(BaseModel):
    round_name: str


class CollegeItem(BaseModel):
    id: int
    name: str
    state: Optional[str] = None

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Full cutoff browse (state-wise "PG Closing Rank" table on the Colleges page)
# ---------------------------------------------------------------------------
class CutoffBrowseRound(BaseModel):
    year: int
    round: str
    open: Optional[int] = None
    close: int


class CutoffBrowseRow(BaseModel):
    institute: str
    state: Optional[str] = None
    authority: Optional[str] = None
    exam: Optional[str] = None
    course: Optional[str] = None
    category: Optional[str] = None
    quota: Optional[str] = None
    cutoffQuota: Optional[str] = None
    fee: Optional[float] = None
    rounds: Dict[str, CutoffBrowseRound]
    # Derived by app/services/seat_rules.py
    quotaLabel: Optional[str] = None
    seatType: Optional[str] = None
    allIndia: Optional[bool] = None
    categoryGroup: Optional[str] = None


# ---------------------------------------------------------------------------
# Prediction
# ---------------------------------------------------------------------------
class PredictionFilters(BaseModel):
    # Student profile — decides which seats the student is eligible for.
    home_state: Optional[str] = Field(default=None, description="Student's domicile / home state")
    student_category: Optional[str] = Field(
        default=None, description="general | ews | obc | sc | st (reservation only applies in home state)"
    )
    is_pwd: bool = False
    gender: Optional[str] = Field(default=None, description="male | female")
    seat_types: Optional[List[str]] = Field(
        default=None,
        description="government, private, nri, in_service, minority, institutional, special "
        "(default: government + private)",
    )

    # Where to look. `state` is the counselling state (blank = every state the student is eligible for).
    exam: Optional[str] = None
    state: Optional[str] = None  # counselling state
    authority: Optional[str] = None
    course: Optional[str] = None
    category: Optional[str] = None
    quota: Optional[str] = None
    year: Optional[int] = None
    round_name: Optional[str] = Field(default=None, alias="round")

    model_config = {"populate_by_name": True}


class PredictionRequest(BaseModel):
    rank: int = Field(..., gt=0, description="The candidate's NEET-PG rank")
    filters: PredictionFilters = PredictionFilters()
    limit: int = Field(default=500, ge=1, le=2000)

    @field_validator("rank")
    @classmethod
    def rank_must_be_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("rank must be a positive integer")
        return v


class PredictionResult(BaseModel):
    institute: str
    state: Optional[str] = None
    authority: Optional[str] = None
    course: Optional[str] = None
    category: Optional[str] = None
    quota: Optional[str] = None
    seat_type: Optional[str] = None
    fee: Optional[float] = None
    year: int
    round: str
    open_rank: Optional[int] = None
    close_rank: int
    chance: str  # "High Chance" | "Moderate Chance" | "Borderline"
    margin_percent: float
    open_to_all_india: Optional[bool] = None
    category_group: Optional[str] = None
    latest_year: Optional[int] = None
    latest_year_rounds: Dict[str, int] = {}
    cleared_in: List[str] = []
    other_routes: int = 0


class PredictionResponse(BaseModel):
    rank_checked: int
    filters_applied: Dict[str, Any]
    total_matching_records: int
    total_eligible_records: int = 0
    total_results: int
    summary: Dict[str, int] = {}
    results: List[PredictionResult]
    message: Optional[str] = None


class PredictOptions(BaseModel):
    home_states: List[str]
    counselling_states: List[str]
    courses: List[str]
    courses_by_state: Dict[str, List[str]]
    # quota name -> {seat_type, all_india}, per counselling state
    quotas_by_state: Dict[str, List[Dict[str, Any]]] = {}
    student_categories: List[NamedItem]
    seat_types: List[Dict[str, Any]]


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TokenPayload(BaseModel):
    sub: Optional[str] = None
    role: Optional[str] = None
    exp: Optional[int] = None


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=100)
    password: str = Field(..., min_length=8, max_length=200)


class LoginRequest(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    username: str
    role: str

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Admin / import
# ---------------------------------------------------------------------------
class ImportDefaults(BaseModel):
    """Fallback values applied to rows in the uploaded file that omit them."""
    state: Optional[str] = None
    authority: Optional[str] = None
    exam: Optional[str] = "NEET-PG"
    year: Optional[int] = None
    round_name: Optional[str] = Field(default=None, alias="round")
    source_label: Optional[str] = None

    model_config = {"populate_by_name": True}


class ImportSummary(BaseModel):
    import_log_id: int
    filename: str
    status: str
    rows_total: int
    records_added: int
    records_updated: int
    duplicates_skipped: int
    conflicts_flagged: int
    rows_rejected: int
    rejected_samples: List[Dict[str, Any]] = []
    started_at: datetime
    finished_at: Optional[datetime] = None


class ImportLogItem(BaseModel):
    id: int
    filename: str
    file_format: str
    source_label: Optional[str] = None
    year: Optional[int] = None
    round_name: Optional[str] = None
    uploaded_by: str
    status: str
    rows_total: int
    records_added: int
    records_updated: int
    duplicates_skipped: int
    conflicts_flagged: int
    rows_rejected: int
    started_at: datetime
    finished_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ConflictItem(BaseModel):
    id: int
    cutoff_record_id: int
    round_key: str
    existing_open: Optional[int] = None
    existing_close: Optional[int] = None
    incoming_open: Optional[int] = None
    incoming_close: Optional[int] = None
    resolved: bool
    resolution: Optional[str] = None
    college: Optional[str] = None
    course: Optional[str] = None
    category: Optional[str] = None

    model_config = {"from_attributes": True}


class ConflictResolution(BaseModel):
    use_incoming: bool


class HealthResponse(BaseModel):
    status: str
    database: str
    total_cutoff_records: Optional[int] = None
    total_round_results: Optional[int] = None