# NEET Rank Predictor — Backend

A production backend for the NEET-PG Rank Predictor, replacing the
hardcoded JavaScript dataset in the original frontend with a live
PostgreSQL database and a FastAPI service. The frontend's look, layout,
and filters are unchanged — only where the predictor gets its data from
has changed.

## What this replaces

The original `neet-rank-predictor.html` kept ~28,000 cutoff records as
JS array literals inside the page, and could only be updated by editing
the file and re-uploading it. This backend:

- Stores the same data in Postgres, normalized into proper tables
  (states, authorities, exams, courses, categories, quotas, colleges,
  cutoff records, and per-year/round results).
- Serves predictions through `POST /api/v1/predict`, running the exact
  same matching logic the original `runRankPredictor()` used (closing
  rank ≥ entered rank, sorted, one best match per college+course+category).
- Never sends the whole dataset to the browser — only the rows a given
  rank/filter combination actually matches.
- Lets an admin add a new year/counselling round via API (CSV, Excel, or
  JSON) at any time. The predictor starts serving that data on the very
  next request — no frontend redeploy, no re-downloading an HTML file.
- Never overwrites historical data. A new round for a college that
  already exists is added alongside its history; a disagreement with an
  already-stored number is flagged as a conflict for a human to resolve,
  never applied silently.
- Logs every import with year, round, source, uploader, and timestamp
  (`import_logs` table / `GET /admin/import-logs`).

## Project layout

```
app/
  main.py                FastAPI app, CORS, error handlers
  config.py               Settings (env vars)
  database.py              SQLAlchemy engine/session
  models.py                 ORM schema
  schemas.py                 Pydantic request/response models
  security.py                 Password hashing + JWT
  deps.py                      Admin-auth FastAPI dependency
  routers/
    health.py                   GET /health
    meta.py                      states/courses/categories/quotas/authorities/years/rounds/colleges
    predict.py                    POST /predict
    admin.py                       login, import, import-logs, conflicts
  services/
    normalize.py                   Ports of the frontend's normInst/normField/key functions
    lookups.py                      get-or-create for reference tables
    import_service.py                Strict/loose-key merge engine (the heart of "never duplicate, never overwrite")
    file_parsers.py                   CSV / XLSX / JSON -> normalized rows
    predictor_service.py               Rank prediction + chance classification
alembic/                                DB migrations
scripts/
  create_admin.py                       Bootstrap the first admin user
  seed_database.py                       One-time load of the migrated dataset
  migration/                              How the original hardcoded data was extracted (see its README)
frontend_integration/
  neet-rank-predictor-api-connected.html   Your original file, predictor box rewired to call the API
  admin_dashboard.html                      New minimal dashboard for CSV/XLSX/JSON uploads
  CHANGES.md                                 Exact diff summary of what changed in the HTML and why
```

## Running it

### Option A — Docker Compose (recommended)

```bash
cp .env.example .env
# edit .env: set a real SECRET_KEY and FIRST_ADMIN_PASSWORD
docker compose up --build
```

This starts Postgres, runs migrations, and starts the API on
`http://localhost:8000`. Interactive docs: `http://localhost:8000/docs`.

Then, in a separate shell, create your admin user and load the migrated
dataset:

```bash
docker compose exec api python scripts/create_admin.py --username admin --password "YourStrongPassword123!"
docker compose exec api python scripts/seed_database.py --file scripts/data/master_records.json
```

### Option B — Local Python + local/managed Postgres

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # point DATABASE_URL at your Postgres instance
alembic upgrade head
python scripts/create_admin.py --username admin --password "YourStrongPassword123!"
python scripts/seed_database.py --file scripts/data/master_records.json
uvicorn app.main:app --reload
```

## Adding new cutoff data (the whole point)

Once an admin is logged in (`POST /api/v1/admin/auth/login`, standard
OAuth2 password form — returns a bearer token), upload a file:

```bash
curl -X POST http://localhost:8000/api/v1/admin/import \
  -H "Authorization: Bearer <token>" \
  -F "file=@karnataka_2026_r1.csv" \
  -F "state=Karnataka" \
  -F "authority=KEA" \
  -F "year=2026" \
  -F "round_name=R1" \
  -F "source_label=KEA official round-1 PDF, 2026"
```

Expected CSV/XLSX columns (case-insensitive, a few aliases accepted —
see `app/services/file_parsers.py::COLUMN_ALIASES`):

```
state, authority, exam, institute, course, category, quota,
seat_type, gender, cutoff_quota, fee, year, round, open_rank, close_rank, source
```

Any column you omit falls back to the `state` / `authority` / `year` /
`round_name` / `source_label` form fields above — so a file with one
round's worth of data doesn't need to repeat the year/round/authority on
every row.

JSON uploads also accept your original nested shape
(`{ institute, state, ..., rounds: { "2026-R1": { open, close } } }`) —
useful for restoring a full backup.

The response tells you exactly what happened:

```json
{
  "status": "success",
  "rows_total": 812,
  "records_added": 40,
  "records_updated": 760,
  "duplicates_skipped": 8,
  "conflicts_flagged": 4,
  "rows_rejected": 0
}
```

Any `conflicts_flagged` show up at `GET /api/v1/admin/conflicts` for a
human to resolve via `POST /api/v1/admin/conflicts/{id}/resolve`.

Predictions reflect the new data immediately — verified end-to-end while
building this (see `scripts/migration/README.md` and the test log below).

## API overview

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/api/v1/health` | none | Liveness + DB connectivity + row counts |
| GET | `/api/v1/states` `/courses` `/categories` `/quotas` `/authorities` `/exams` | none | Dropdown data |
| GET | `/api/v1/years` `/rounds?year=` | none | Available years / counselling rounds |
| GET | `/api/v1/colleges?state=&search=` | none | College lookup/autocomplete |
| POST | `/api/v1/predict` | none | Core prediction |
| POST | `/api/v1/admin/auth/login` | — | Get a bearer token |
| POST | `/api/v1/admin/import` | bearer | Upload CSV/XLSX/JSON |
| GET | `/api/v1/admin/import-logs` | bearer | Audit trail |
| GET | `/api/v1/admin/conflicts` | bearer | Unresolved data conflicts |
| POST | `/api/v1/admin/conflicts/{id}/resolve` | bearer | Keep existing or accept incoming value |

Full interactive schema: `/docs` (Swagger) or `/redoc`.

## Security / production notes

- Set a strong, random `SECRET_KEY` in production (never the placeholder
  in `.env.example`).
- `CORS_ORIGINS` should be your actual frontend origin(s), not `*`, once
  you know where the HTML will be hosted.
- Passwords are hashed with `pbkdf2_sha256` (via passlib) — pure Python,
  no native-extension version issues across containers/platforms.
- All admin write endpoints require a valid JWT; predictor/reference-data
  endpoints are public read-only.
- Indexes exist on every column the predictor filters or sorts by
  (`ix_cutoff_filter_combo`, `ix_round_close_rank`, etc.) — verified via
  `EXPLAIN` during testing that filtered predict queries use them.
- Put this behind HTTPS (a reverse proxy like Caddy/Nginx, or your
  platform's managed TLS) — the API itself speaks plain HTTP.
- Back up the Postgres volume (`neet_pg_data` in `docker-compose.yml`)
  the same way you'd back up any production database.

## What was verified while building this

- Alembic migration creates all 13 tables cleanly against Postgres 16.
- The full migrated dataset (27,936 records / 76,257 round entries / 29
  states / 757 colleges / 86 courses / 331 categories / 19 quotas)
  imported with **0 rows rejected and 0 spurious conflicts**.
- `/predict` reproduces the original algorithm's sorting, dedup, and both
  "no data at all" vs. "data exists but rank doesn't clear it" messages.
- A new CSV upload for an existing college added a new round to the
  *same* record (not a duplicate); a genuinely new college created a new
  record; predictions picked up the new 2026 data on the very next
  request with no frontend change.
- Re-uploading a conflicting number for a round that already had a value
  did **not** overwrite it — it was flagged in `import_conflicts` instead.
- Admin endpoints correctly return 401 without a token and accept a
  freshly issued one.
