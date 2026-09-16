# How the original hardcoded dataset was migrated

Your original `neet-rank-predictor.html` built its entire dataset (27,936
college/course/category/quota records covering 29 states, 86 courses, 333
category codes) as JavaScript array literals and a `seedBaselineMaster()`
function that assembled them into an in-memory `MASTER` object at page
load. None of that lived in a database — it was baked into the page.

To move it into Postgres without retyping or re-deriving a single number,
we extracted it mechanically instead of by hand:

1. **`extract_master_from_html.js`** is the *exact* data-construction
   portion of your original `<script>` tag (every `const X = mk([...])`,
   every raw state array, `mergeRows`, `normInst`/`normField`,
   `mergeRecordsInto`, every `seedX()` function, and `seedBaselineMaster()`
   itself) — copied verbatim, with only the DOM-dependent code (rendering,
   file upload UI, localStorage persistence) left out, since none of that
   is needed to *build* the dataset, only to display or persist it in a
   browser.

2. Two lines were appended to call `seedBaselineMaster()` and dump the
   resulting `MASTER.records` array as JSON:

   ```js
   seedBaselineMaster();
   const fs = require('fs');
   fs.writeFileSync(outPath, JSON.stringify(MASTER.records));
   ```

3. Running it with plain Node reproduces `master_records.json` byte-for-byte
   from your original file, any time:

   ```bash
   node scripts/migration/extract_master_from_html.js ./master_records.json
   ```

4. `scripts/seed_database.py` then loads that JSON through the exact same
   import/merge engine (`app/services/import_service.py`) that the live
   admin API uses — so the one-time migration and every future CSV/XLSX/JSON
   upload all go through identical strict/loose-key matching, duplicate
   detection, and conflict flagging. Nothing about the historical data was
   hand-edited or re-derived; it was carried straight from your file into
   the database with full audit logging (`import_logs` row `#1`, source
   label "Migrated from original frontend hardcoded dataset").

We verified the result matches the original exactly: 27,936 cutoff
records, 76,257 individual year/round entries, 29 states, 757 colleges,
86 courses, 331 categories, 19 quotas, 29 authorities — zero rows
rejected, zero spurious conflicts.

If you ever need to re-run this (e.g. you have a newer copy of the old
HTML file with data the database doesn't have yet), just re-run steps 3
and 4 — the merge engine will add anything new and flag anything that
disagrees with what's already in the database, rather than overwriting it.
