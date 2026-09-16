# START HERE

This is the only file you need to read first. Follow it top to bottom.

---

## What's in this folder

| Folder / file | What it's for |
|---|---|
| `app/` | The backend itself (FastAPI). You won't need to edit this to get started. |
| `alembic/` | Database migrations — run automatically, nothing to do here. |
| `scripts/create_admin.py` | Creates your admin login. |
| `scripts/seed_database.py` + `scripts/data/master_records.json` | Loads your original 27,936 cutoff records into the database. |
| `frontend_integration/neet-rank-predictor-api-connected.html` | Your original predictor page, reconnected to the live backend. |
| `frontend_integration/admin_dashboard.html` | New page for uploading future years/rounds of data. |
| `frontend_integration/CHANGES.md` | Exactly what changed in the HTML, and why. |
| `README.md` | Full reference docs (API endpoints, security notes, etc). |
| `RAILWAY.md` | Railway-specific deployment reference. |
| `docker-compose.yml`, `Dockerfile` | How the backend runs locally / on a server. |
| `.env.example` | Settings template — copy to `.env` and fill in. |

You're deploying via **GitHub + Railway**, so follow Path B below.

---

## Path B: GitHub + Railway (what you're doing)

### Step 1 — Push this folder to GitHub
```bash
cd neet-predictor-backend
git init
git add .
git commit -m "Initial backend"
git branch -M main
git remote add origin <your-empty-github-repo-url>
git push -u origin main
```
(Create the empty repo on github.com first — no README/license, just empty.)

### Step 2 — Deploy on Railway
1. railway.app → sign in with GitHub → **New Project** → **Deploy from GitHub repo** → pick your repo. It will fail to build at first — that's expected, no database yet.
2. Same project → **New** → **Database** → **PostgreSQL**.
3. Click your **api** service → **Variables** → add:
   - `DATABASE_URL` — as a **reference variable** to `Postgres.DATABASE_URL` (use "Add Reference" in the variable editor, don't type it by hand)
   - `SECRET_KEY` — any long random string (`python -c "import secrets; print(secrets.token_urlsafe(48))"`)
   - `CORS_ORIGINS` — set to `*` for now, narrow it later (Step 5)
4. **Settings** → **Networking** → **Generate Domain**. This gives you a public URL like `https://yourapp.up.railway.app`.
5. Wait for the service to redeploy — it should come up healthy.

### Step 3 — Create your admin login and load your data
On your own machine:
```bash
npm i -g @railway/cli
railway login
railway link              # pick this project
railway run python scripts/create_admin.py --username admin --password "YourStrongPassword123!"
railway run python scripts/seed_database.py --file scripts/data/master_records.json
```
The second command takes a couple of minutes — it's loading 27,936 records.

### Step 4 — Verify it's live
Visit `https://yourapp.up.railway.app/api/v1/health` — you should see
`"total_cutoff_records": 27936`. Visit `/docs` on the same domain to try
any endpoint interactively.

### Step 5 — Connect and host the frontend
1. Open `frontend_integration/neet-rank-predictor-api-connected.html`, find
   `PREDICTOR_API_BASE_URL` near the bottom, set it to
   `https://yourapp.up.railway.app/api/v1`.
2. Do the same for the API base logic at the top of
   `frontend_integration/admin_dashboard.html`.
3. Push both HTML files to GitHub Pages, Netlify, or Vercel — any static
   host works, they're just plain files.
4. Back on Railway, change `CORS_ORIGINS` from `*` to your frontend's
   exact URL (e.g. `https://yourname.github.io`).

### Step 6 — You're live
- Predictor page: your static host's URL.
- Admin dashboard: same host, `/admin_dashboard.html` — log in with the
  username/password from Step 3, upload a CSV/XLSX/JSON whenever a new
  year or round comes out. The predictor updates immediately, no
  redeploy needed.

---

## If something breaks

Paste the exact error — from Railway's build/deploy logs, or your
browser's console (F12 → Console tab) — and it can be diagnosed from
that. `RAILWAY.md` has the same checklist above plus the full variable
reference table if you need to double back on any step.
