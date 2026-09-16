# What changed in the frontend, exactly

**File:** `neet-rank-predictor-api-connected.html` — your original file, with
one targeted change.

## What did NOT change

- Every pixel of layout, every CSS rule, every color, every tab, every
  filter, the state grid, the college browse table, the import wizard UI,
  the backup/restore buttons, the state map graphics — all untouched,
  byte-for-byte identical to your original file.
- The "Import & Master Data" tab still works exactly as before for
  browsing/importing into the browser's own local copy of the data
  (`MASTER`) — that local-only workflow was not touched.
- Element IDs, class names, function names (`populatePredictorFilters`,
  `runRankPredictor`) — kept identical so nothing else on the page that
  calls them needed to change.

## What DID change

Only the **bodies** of two functions, both inside the `<script>` tag:

### 1. `populatePredictorFilters()`

**Before:** read `MASTER.records` (the local, hardcoded array) and derived
each dropdown's options with `[...new Set(recs.map(...))]`.

**After:** fetches `/exams`, `/states`, `/authorities`, `/courses`,
`/categories`, `/quotas` from the backend API in parallel and fills the
exact same dropdowns (`fillSelect(...)` calls are unchanged).

### 2. `runRankPredictor()`

**Before:** filtered `MASTER.records` in-browser, iterated every record's
`rounds` object, sorted, deduped, and rendered.

**After:** sends `{ rank, filters }` to `POST /predict` and renders the
`results` array the backend returns. The rendering logic (the HTML string
built for each result row) is the same shape as before, plus one addition:
a `chance` label (`High Chance` / `Moderate Chance` / `Borderline`) is now
shown alongside each result — additive information, not a change to which
results appear or how they're ordered.

Both functions keep their original two-tier "no data" messaging
(no records match the filters at all, vs. records matched but no round
cleared this rank) — those messages now come from the API response's
`message` field instead of being computed in-browser, but the wording and
the logic behind it are unchanged.

A small loading state ("Checking against the live database…") and a
network-error message were added, since a network call can fail or take a
moment in ways a local array lookup never could — there was nothing to
show there before.

### Configuration

One new top-level constant:

```js
const PREDICTOR_API_BASE_URL = (window.PREDICTOR_API_BASE_URL || "http://localhost:8000/api/v1");
```

Point this at wherever you deploy the backend (edit the file, or set
`window.PREDICTOR_API_BASE_URL` before this script runs — e.g. a small
inline `<script>` tag added just above the existing one, so you never have
to hand-edit the main script again when the API's URL changes).

## Why the admin/import tooling wasn't rewired to hit the backend

Your original "Import & Master Data" tab is a substantial piece of
in-browser tooling — a Web Worker–based CSV/Excel/PDF parser, dry-run
preview, per-file metadata editing, conflict UI, localStorage persistence
— built entirely around the local `MASTER` object. Rewiring all of that to
call the backend instead, while leaving its UI/UX identical, would mean
re-implementing most of its internals rather than "connecting" it.

Since the actual requirement was an **admin API/dashboard** for adding new
data — not necessarily reusing this exact wizard — `admin_dashboard.html`
in this folder is a new, separate, lightweight dashboard that does that
job against the real backend (login, upload CSV/XLSX/JSON, see import
history, resolve conflicts). It doesn't touch or replace your original
file's import tab; it's an additional page for the new backend-driven
workflow. Your original import tab keeps working exactly as it always
did, for local-only browsing/testing if you still want it.

If you'd like the original import wizard itself rewired to hit the
backend end-to-end (same fancy UI, but writing to Postgres instead of
localStorage), that's a well-scoped follow-up — most of the hard part
(the merge engine, conflict detection, endpoints) already exists in this
backend; it would "just" need that wizard's `confirmImport()`-equivalent
to POST to `/admin/import` instead of calling `mergeRecordsInto` locally.
