"""
Turns an uploaded CSV / Excel / JSON file into a flat list of row dicts
with keys: state, authority, exam, institute, course, category, quota,
seat_type, gender, cutoff_quota, fee, year, round_name, open_rank,
close_rank, source_file.

Two JSON shapes are accepted:
  * "flat"   — a list of objects already in the shape above (one row per
               year/round), the recommended shape for new uploads.
  * "nested" — the original frontend's MASTER.records shape:
               { institute, state, course, quota, category, ..., rounds:
               { "2025-R2": { open, close }, ... } }. Useful for restoring
               a full backup exported from the old tool, or the one-time
               migration of the original hardcoded dataset.
"""
import io
import json
from typing import Any

import pandas as pd

from app.schemas import ImportDefaults
from app.services.normalize import parse_round_key

# Recognized column name variants -> canonical field name. Header matching
# is case-insensitive and ignores surrounding whitespace/underscores, which
# mirrors the flexible header detection in the original import wizard.
COLUMN_ALIASES = {
    "state": "state",
    "authority": "authority",
    "exam": "exam",
    "institute": "institute",
    "college": "institute",
    "institution": "institute",
    "course": "course",
    "category": "category",
    "quota": "quota",
    "seat_type": "seat_type",
    "seattype": "seat_type",
    "gender": "gender",
    "cutoff_quota": "cutoff_quota",
    "cutoffquota": "cutoff_quota",
    "fee": "fee",
    "year": "year",
    "round": "round_name",
    "round_name": "round_name",
    "open_rank": "open_rank",
    "openrank": "open_rank",
    "open": "open_rank",
    "close_rank": "close_rank",
    "closerank": "close_rank",
    "close": "close_rank",
    "closing_rank": "close_rank",
    "source": "source_file",
    "source_file": "source_file",
}


def _canon_header(h: str) -> str:
    return str(h).strip().lower().replace(" ", "_").replace("-", "_")


def _apply_defaults(row: dict, defaults: ImportDefaults) -> dict:
    out = dict(row)
    if not out.get("state") and defaults.state:
        out["state"] = defaults.state
    if not out.get("authority") and defaults.authority:
        out["authority"] = defaults.authority
    if not out.get("exam") and defaults.exam:
        out["exam"] = defaults.exam
    if not out.get("year") and defaults.year:
        out["year"] = defaults.year
    if not out.get("round_name") and defaults.round_name:
        out["round_name"] = defaults.round_name
    if not out.get("source_file") and defaults.source_label:
        out["source_file"] = defaults.source_label
    return out


def parse_tabular(content: bytes, filename: str, defaults: ImportDefaults) -> list[dict]:
    """Parses CSV or XLSX bytes into flat row dicts."""
    lower = filename.lower()
    if lower.endswith(".csv"):
        df = pd.read_csv(io.BytesIO(content), dtype=str, keep_default_na=False)
    elif lower.endswith((".xlsx", ".xls")):
        df = pd.read_excel(io.BytesIO(content), dtype=str)
        df = df.fillna("")
    else:
        raise ValueError("Unsupported file type — expected .csv, .xlsx, .xls, or .json")

    df.columns = [_canon_header(c) for c in df.columns]
    rename_map = {c: COLUMN_ALIASES[c] for c in df.columns if c in COLUMN_ALIASES}
    df = df.rename(columns=rename_map)

    rows: list[dict] = []
    for _, series in df.iterrows():
        row = {k: (v if v != "" else None) for k, v in series.to_dict().items()}
        row = _apply_defaults(row, defaults)
        rows.append(row)
    return rows


def parse_json(content: bytes, defaults: ImportDefaults) -> list[dict]:
    data = json.loads(content.decode("utf-8"))
    if isinstance(data, dict):
        data = data.get("records", data.get("rows", [data]))
    if not isinstance(data, list):
        raise ValueError("JSON file must contain a list of records (optionally under a 'records' key)")

    rows: list[dict] = []
    for item in data:
        if "rounds" in item:
            rows.extend(_flatten_nested_record(item, defaults))
        else:
            rows.append(_apply_defaults(item, defaults))
    return rows


def _flatten_nested_record(item: dict[str, Any], defaults: ImportDefaults) -> list[dict]:
    base = {
        "state": item.get("state"),
        "authority": item.get("authority"),
        "exam": item.get("exam"),
        "institute": item.get("institute"),
        "course": item.get("course"),
        "category": item.get("category"),
        "quota": item.get("quota"),
        "seat_type": item.get("seatType"),
        "gender": item.get("gender"),
        "cutoff_quota": item.get("cutoffQuota"),
        "fee": item.get("fee"),
    }
    rows = []
    for round_key, vals in (item.get("rounds") or {}).items():
        try:
            year, round_name = parse_round_key(round_key)
        except ValueError:
            continue
        row = dict(base)
        row["year"] = year
        row["round_name"] = round_name
        row["open_rank"] = vals.get("open") if isinstance(vals, dict) else None
        row["close_rank"] = vals.get("close") if isinstance(vals, dict) else vals
        row["source_file"] = (vals.get("sourceFile") if isinstance(vals, dict) else None) or ", ".join(
            item.get("sourceFiles") or []
        ) or None
        rows.append(_apply_defaults(row, defaults))
    return rows


def parse_upload(content: bytes, filename: str, defaults: ImportDefaults) -> list[dict]:
    if filename.lower().endswith(".json"):
        return parse_json(content, defaults)
    return parse_tabular(content, filename, defaults)
