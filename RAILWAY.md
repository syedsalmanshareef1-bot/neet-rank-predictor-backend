# Deploying to Railway

Quick reference — see the numbered steps Claude walked through in chat for
the full first-time flow. This file is here for whenever you need to
re-check a command later.

## Services in the Railway project

- **Postgres** — Railway's own plugin, provisions `DATABASE_URL` automatically.
- **api** — this repo, built from the `Dockerfile`. Reads `DATABASE_URL`
  from the Postgres service via a reference variable.

## Required variables on the `api` service

| Variable | Value |
|---|---|
| `DATABASE_URL` | `${{Postgres.DATABASE_URL}}` (reference variable — click "Add Reference" in Railway's variable editor, don't type it by hand) |
| `SECRET_KEY` | A long random string — generate with `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `CORS_ORIGINS` | Your deployed frontend's exact origin, e.g. `https://yourname.github.io` (comma-separate if more than one) |
| `FIRST_ADMIN_USERNAME` / `FIRST_ADMIN_PASSWORD` | Only needed transiently for `railway run python scripts/create_admin.py` — fine to remove after |

Railway sets `PORT` itself — don't add it manually, the Dockerfile already
reads it (`${PORT:-8000}`).

## First deploy checklist

1. Push this repo to GitHub.
2. Railway → New Project → Deploy from GitHub repo → pick it.
3. Add a Postgres service to the same project (New → Database → PostgreSQL).
4. On the `api` service → Variables → add the table above.
5. Settings → Networking → **Generate Domain** (services aren't public by default).
6. Once the first deploy is green, from your machine:
   ```bash
   npm i -g @railway/cli   # one-time
   railway login
   railway link            # pick this project
   railway run python scripts/create_admin.py --username admin --password "YourStrongPassword123!"
   railway run python scripts/seed_database.py --file scripts/data/master_records.json
   ```
7. Visit `https://<your-api>.up.railway.app/api/v1/health` — should show
   `total_cutoff_records: 27936`.
8. Update `PREDICTOR_API_BASE_URL` in the frontend HTML files to
   `https://<your-api>.up.railway.app/api/v1`, then deploy the frontend
   (GitHub Pages, Netlify, Vercel — any static host).
9. Narrow `CORS_ORIGINS` on the `api` service to that frontend's exact URL.

## Redeploying after future code changes

Just `git push` — Railway auto-builds and redeploys on push to the linked
branch. Migrations run automatically on every container start (part of the
Dockerfile's `CMD`), so a new Alembic revision takes effect on the next
deploy with no manual step.
