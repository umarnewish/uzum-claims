# uzum-claims

Companion service to [vendex](../vendex). Tracks lost items and lost orders
for Uzum Market sellers across FBS/FBO and auto-generates the docx
compensation claim packets the seller has to submit.

See [PLAN.md](PLAN.md) for the full architecture, schema, endpoints, and
phase plan, and [CLAUDE.md](CLAUDE.md) for the working notes.

## Quick start (local)

```bash
cp .env.example .env
# edit .env: set SECRET_KEY to match vendex, point DATABASE_URL at the same Postgres

python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python -m uvicorn backend.main:app --host 0.0.0.0 --port 8100 --reload
```

Then visit:

- <http://localhost:8100/> — landing page
- <http://localhost:8100/api/health> — health probe
- <http://localhost:8100/docs> — OpenAPI docs

## Docker (local)

```bash
docker compose up --build
```

## Production

Deployed on the same DigitalOcean droplet as vendex, behind nginx at
`/claims/`, sharing Postgres (schema `claims`) and the JWT secret. See
[PLAN.md §12](PLAN.md) for the compose + nginx snippets.

## Layout

```
backend/
  main.py          FastAPI app
  config.py        Pydantic settings
  db.py            async SQLAlchemy session
  auth.py          stateless JWT decode (Phase 0)
  routers/         HTTP endpoints
  services/        business logic (loss detection, docx, Uzum + vendex clients)
frontend/          vanilla JS, no build step
templates/         four real Uzum docx templates
alembic/           migrations (Phase 1+)
```

## Phase status

Phase 0 — bootstrap. App boots, serves `/`, exposes `/api/health` and a
JWT-validated `/api/whoami`. No DB tables yet.
