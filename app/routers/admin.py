from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app import models
from app.database import get_db
from app.deps import get_current_admin
from app.schemas import (
    ConflictItem,
    ConflictResolution,
    ImportDefaults,
    ImportLogItem,
    ImportSummary,
    Token,
)
from app.security import create_access_token, verify_password
from app.services.file_parsers import parse_upload
from app.services.import_service import import_rows
from app.routers.meta import invalidate_cutoffs_cache

router = APIRouter(prefix="/admin", tags=["admin"])


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
@router.post("/auth/login", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(models.AdminUser).filter(models.AdminUser.username == form_data.username).one_or_none()
    if not user or not user.is_active or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = create_access_token(subject=user.username, role=user.role)
    return Token(access_token=token)


# ---------------------------------------------------------------------------
# Data import
# ---------------------------------------------------------------------------
@router.post("/import", response_model=ImportSummary)
async def import_file(
    file: UploadFile = File(..., description="CSV, XLSX, or JSON cutoff data file"),
    state: Optional[str] = Form(default=None, description="Default state applied to rows that omit one"),
    authority: Optional[str] = Form(default=None),
    exam: Optional[str] = Form(default="NEET-PG"),
    year: Optional[int] = Form(default=None, description="Default year for rows that omit one"),
    round_name: Optional[str] = Form(default=None, description="Default round (R1, R2, ... or Final)"),
    source_label: Optional[str] = Form(default=None, description="Human-readable source, e.g. 'KEA official PDF'"),
    db: Session = Depends(get_db),
    admin: models.AdminUser = Depends(get_current_admin),
):
    """
    Upload a new year/round of cutoff data. Accepts CSV, XLSX, or JSON.
    Existing historical data is never overwritten: new rows for a
    college/course/category combination that already exists are added as
    new rounds; disagreements with existing numbers are flagged as
    conflicts for review rather than applied automatically; exact repeats
    are silently skipped and counted.
    """
    filename = file.filename or "upload"
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    if ext not in ("csv", "xlsx", "xls", "json"):
        raise HTTPException(status_code=400, detail="Unsupported file type. Upload a .csv, .xlsx, .xls, or .json file.")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    defaults = ImportDefaults(
        state=state, authority=authority, exam=exam, year=year, round=round_name, source_label=source_label
    )

    import_log = models.ImportLog(
        filename=filename,
        file_format=ext,
        source_label=source_label,
        year=year,
        round_name=round_name,
        uploaded_by=admin.username,
        status=models.ImportStatus.pending,
    )
    db.add(import_log)
    db.flush()

    try:
        rows = parse_upload(content, filename, defaults)
    except Exception as exc:  # noqa: BLE001
        import_log.status = models.ImportStatus.failed
        import_log.error_message = str(exc)
        import_log.finished_at = datetime.now(timezone.utc)
        db.commit()
        raise HTTPException(status_code=400, detail=f"Could not parse file: {exc}") from exc

    if not rows:
        import_log.status = models.ImportStatus.failed
        import_log.error_message = "No rows found in file."
        import_log.finished_at = datetime.now(timezone.utc)
        db.commit()
        raise HTTPException(status_code=400, detail="No rows found in the uploaded file.")

    try:
        stats = import_rows(db, rows, import_log, uploaded_by=admin.username)
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        import_log.status = models.ImportStatus.failed
        import_log.error_message = str(exc)
        import_log.finished_at = datetime.now(timezone.utc)
        db.add(import_log)
        db.commit()
        raise HTTPException(status_code=500, detail=f"Import failed: {exc}") from exc

    import_log.rows_total = stats.rows_total
    import_log.records_added = stats.records_added
    import_log.records_updated = stats.records_updated
    import_log.duplicates_skipped = stats.duplicates_skipped
    import_log.conflicts_flagged = stats.conflicts_flagged
    import_log.rows_rejected = stats.rows_rejected
    import_log.status = (
        models.ImportStatus.success
        if stats.rows_rejected == 0
        else (models.ImportStatus.partial if (stats.records_added or stats.records_updated) else models.ImportStatus.failed)
    )
    import_log.finished_at = datetime.now(timezone.utc)
    db.commit()
    invalidate_cutoffs_cache()
    db.refresh(import_log)

    return ImportSummary(
        import_log_id=import_log.id,
        filename=import_log.filename,
        status=import_log.status.value,
        rows_total=stats.rows_total,
        records_added=stats.records_added,
        records_updated=stats.records_updated,
        duplicates_skipped=stats.duplicates_skipped,
        conflicts_flagged=stats.conflicts_flagged,
        rows_rejected=stats.rows_rejected,
        rejected_samples=stats.rejected_samples,
        started_at=import_log.started_at,
        finished_at=import_log.finished_at,
    )


# ---------------------------------------------------------------------------
# Import logs (audit trail)
# ---------------------------------------------------------------------------
@router.get("/import-logs", response_model=list[ImportLogItem])
def list_import_logs(
    limit: int = 50,
    db: Session = Depends(get_db),
    admin: models.AdminUser = Depends(get_current_admin),
):
    logs = db.query(models.ImportLog).order_by(models.ImportLog.started_at.desc()).limit(limit).all()
    return [
        ImportLogItem(
            id=log.id,
            filename=log.filename,
            file_format=log.file_format,
            source_label=log.source_label,
            year=log.year,
            round_name=log.round_name,
            uploaded_by=log.uploaded_by,
            status=log.status.value,
            rows_total=log.rows_total,
            records_added=log.records_added,
            records_updated=log.records_updated,
            duplicates_skipped=log.duplicates_skipped,
            conflicts_flagged=log.conflicts_flagged,
            rows_rejected=log.rows_rejected,
            started_at=log.started_at,
            finished_at=log.finished_at,
        )
        for log in logs
    ]


# ---------------------------------------------------------------------------
# Conflicts requiring manual review
# ---------------------------------------------------------------------------
@router.get("/conflicts", response_model=list[ConflictItem])
def list_conflicts(
    unresolved_only: bool = True,
    db: Session = Depends(get_db),
    admin: models.AdminUser = Depends(get_current_admin),
):
    q = db.query(models.ImportConflict)
    if unresolved_only:
        q = q.filter(models.ImportConflict.resolved.is_(False))
    conflicts = q.order_by(models.ImportConflict.created_at.desc()).limit(200).all()
    out = []
    for c in conflicts:
        rec = c.cutoff_record
        out.append(
            ConflictItem(
                id=c.id,
                cutoff_record_id=c.cutoff_record_id,
                round_key=c.round_key,
                existing_open=c.existing_open,
                existing_close=c.existing_close,
                incoming_open=c.incoming_open,
                incoming_close=c.incoming_close,
                resolved=c.resolved,
                resolution=c.resolution,
                college=rec.college.name if rec and rec.college else None,
                course=rec.course.name if rec and rec.course else None,
                category=rec.category.code if rec and rec.category else None,
            )
        )
    return out


@router.post("/conflicts/{conflict_id}/resolve")
def resolve_conflict(
    conflict_id: int,
    body: ConflictResolution,
    db: Session = Depends(get_db),
    admin: models.AdminUser = Depends(get_current_admin),
):
    conflict = db.query(models.ImportConflict).filter(models.ImportConflict.id == conflict_id).one_or_none()
    if not conflict:
        raise HTTPException(status_code=404, detail="Conflict not found")
    if conflict.resolved:
        raise HTTPException(status_code=400, detail="Conflict already resolved")

    if body.use_incoming:
        round_result = (
            db.query(models.RoundResult)
            .filter(
                models.RoundResult.cutoff_record_id == conflict.cutoff_record_id,
                models.RoundResult.round_key == conflict.round_key,
            )
            .one_or_none()
        )
        if round_result:
            round_result.open_rank = conflict.incoming_open
            round_result.close_rank = conflict.incoming_close
        conflict.resolution = "used_incoming"
    else:
        conflict.resolution = "kept_existing"

    conflict.resolved = True
    conflict.resolved_by = admin.username
    conflict.resolved_at = datetime.now(timezone.utc)
    db.commit()
    invalidate_cutoffs_cache()
    return {"status": "resolved", "resolution": conflict.resolution}
