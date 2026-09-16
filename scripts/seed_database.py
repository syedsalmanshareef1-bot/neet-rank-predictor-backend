"""
One-time migration: loads the dataset extracted from the original
hardcoded frontend (master_records.json — see
scripts/extract_master_from_html.md for how it was produced) into
Postgres through the exact same import/merge engine the admin API uses.

Usage:
    python scripts/seed_database.py --file scripts/data/master_records.json

Safe to re-run: it goes through the same strict/loose-key matching and
duplicate/conflict detection as any other import, so re-running it a
second time will report everything as duplicates rather than doubling
the data.
"""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import SessionLocal
from app.models import ImportLog, ImportStatus
from app.schemas import ImportDefaults
from app.services.file_parsers import parse_json
from app.services.import_service import import_rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", required=True, help="Path to master_records.json")
    parser.add_argument("--uploaded-by", default="seed_script")
    args = parser.parse_args()

    path = Path(args.file)
    if not path.exists():
        print(f"File not found: {path}", file=sys.stderr)
        sys.exit(1)

    content = path.read_bytes()
    print(f"Parsing {path} ...")
    t0 = time.time()
    rows = parse_json(content, ImportDefaults(exam="NEET-PG"))
    print(f"Parsed {len(rows):,} flat (year/round) rows in {time.time() - t0:.1f}s")

    db = SessionLocal()
    try:
        log = ImportLog(
            filename=path.name,
            file_format="json",
            source_label="Migrated from original frontend hardcoded dataset",
            uploaded_by=args.uploaded_by,
            status=ImportStatus.pending,
        )
        db.add(log)
        db.flush()

        print("Importing (this walks the same strict/loose-key merge logic as the admin API)...")
        t0 = time.time()
        stats = import_rows(db, rows, log, uploaded_by=args.uploaded_by)
        elapsed = time.time() - t0

        log.rows_total = stats.rows_total
        log.records_added = stats.records_added
        log.records_updated = stats.records_updated
        log.duplicates_skipped = stats.duplicates_skipped
        log.conflicts_flagged = stats.conflicts_flagged
        log.rows_rejected = stats.rows_rejected
        log.status = ImportStatus.success if stats.rows_rejected == 0 else ImportStatus.partial
        db.commit()

        print(f"Done in {elapsed:.1f}s")
        print(f"  rows total:          {stats.rows_total:,}")
        print(f"  new records added:   {stats.records_added:,}")
        print(f"  records updated:     {stats.records_updated:,}")
        print(f"  exact duplicates:    {stats.duplicates_skipped:,}")
        print(f"  conflicts flagged:   {stats.conflicts_flagged:,}")
        print(f"  rows rejected:       {stats.rows_rejected:,}")
        if stats.rejected_samples:
            print("  sample rejected rows:")
            for s in stats.rejected_samples[:5]:
                print(f"    - {s['error']}")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
