# uzum-claims — context for Claude

## What this project is

Standalone companion service to **vendex** (warehouse management for Uzum Market sellers, lives at `/home/umar/Desktop/vendex/`). Tracks lost items + lost orders across FBS and FBO, and auto-generates Uzum compensation claim docx files for the user to submit.

Deployed alongside vendex on the same DigitalOcean droplet (`root@159.89.19.29`), accessed seamlessly via a new tab in vendex UI at `/claims/` (nginx proxy route).

## Read this first

[PLAN.md](PLAN.md) — full architectural plan, schema, endpoints, phases, deployment. Source of truth for what is being built and why. Read it cover-to-cover before starting.

## Templates

Four `.docx` templates from real Uzum compensation flow are in [templates/](templates/):

- `claim_ru.docx` — Russian claim (sample is filled with real seller data: ALFA POLIMER LINE, 24 SKUs, 3.4M sum)
- `claim_uz.docx` — Uzbek claim (blank)
- `agreement_ru.docx` — Russian additional agreement
- `agreement_uz.docx` — Uzbek additional agreement

These are real Uzum-issued templates. Phase 4 of PLAN.md is to re-author them with `{{token}}` placeholders for `python-docx` filling — keep visual layout pixel-identical, just swap blank lines / data cells for placeholders.

## Bootstrap state (Phase 0 done — local boot verified)

Phase 0 complete. App boots, serves `/`, `/api/health` returns 200, and
`/api/whoami` decodes a vendex-issued JWT (verified locally with a
forged token signed with the shared `SECRET_KEY`).

Files:
- `backend/{main,config,db,auth}.py`
- `backend/routers/{__init__,health}.py`
- `backend/services/__init__.py`
- `frontend/index.html` (placeholder Phase 0 page)
- `docker-compose.yml`, `Dockerfile`, `requirements.txt`, `.env.example`, `.gitignore`
- `README.md`, `PLAN.md`, this `CLAUDE.md`
- `templates/` — four real Uzum docx

Phase 0 boot caveat: `GENERATED_DIR=/var/uzum-claims/generated` is not
writable for non-root local dev. Lifespan logs a warning and continues —
docx generation only matters in Phase 4. For local dev, override in
`.env`: `GENERATED_DIR=/tmp/uzum-claims/generated`.

Phase 1 next: Alembic init + create schema `claims` + `seller_profile`
table + CRUD UI. The auth shim should also gain a vendex `/api/me`
session check once vendex exposes it.

Decisions already made (see PLAN.md §14 for context — all confirmed by user):
- Shared Postgres with vendex, own schema `claims` (logical separation)
- Phase order locked
- Manual SKU linking on vendex side (separate workstream, but related)
- Wizard with barcode-match suggestions for new shop seed (vendex side)
- Option B for integration: nginx route `/claims/` on same domain, shared JWT cookie, no iframe

## Vendex things you need to know

- Stack: FastAPI + PostgreSQL + vanilla JS, async SQLAlchemy w/ asyncpg
- Auth: Telegram bot 6-digit code → JWT (HS256, stateful — validates against `sessions` table)
- Tables: `users`, `auth_codes`, `sessions`, `user_settings`, `integrations`, `products`, `stock_logs`
- `integrations.encrypted_token` decrypted via `backend.services.encryption.decrypt_token()` — this is the Uzum API token per shop
- Uzum API base: `https://api-seller.uzum.uz/api/seller-openapi`
  - Auth header: `Authorization: <token>` (NO Bearer prefix)
- Vendex location: `/home/umar/Desktop/vendex/` — read freely if you need to mirror conventions, but DO NOT modify (separate workstream)

## Vendex endpoints to be added by separate work (DO NOT WAIT)

PLAN.md §6 lists endpoints vendex needs to expose for this service:
- `GET /api/me` — current user info
- `GET /api/integrations/shops` — user's connected Uzum shops + tokens

These don't exist yet. For Phase 0–1 you can stub them client-side. Real integration in Phase 2 when polling starts.

## Key Uzum API endpoints used by this service

| Endpoint | Purpose | Phase |
|----------|---------|-------|
| `GET /v1/return` | Returns list — has `amount` (expected) and `packedAmount` (actually packed) per item → `amount − packedAmount` = Uzum-side leak | 2 |
| `GET /v1/shop/{shopId}/return/{returnId}` | Return detail | 2 |
| `GET /v1/invoice` and `/v1/shop/{shopId}/invoice` | Supply invoices — `totalToStock` (sent) vs `totalAccepted` (warehouse received) | 5 |
| `GET /v1/shop/{shopId}/invoice/products?invoiceId=` | Invoice line items for SKU attribution | 5 |
| `GET /v2/fbs/orders` | Orders w/ status (CANCELED, RETURNED, etc.) | 6 |
| `GET /v1/finance/orders` | Per-item financials: `sellerPrice`, `commission`, `sellerProfit`, `purchasePrice`, `logisticDeliveryFee`, `amount`, `amountReturns` | 2+ |

Compensation amount per Uzum rule 6.8: `unit_compensation = sellerPrice − commission`.

## How to work in this codebase

- Vanilla JS frontend (no build step), matches vendex style. Copy or symlink vendex CSS for visual identity.
- Async-first backend. Mirror vendex conventions where reasonable.
- Keep this codebase **small and focused** — that is the whole reason it is split out. Resist scope creep into vendex territory (multi-store sync, finances tab, etc. — those belong in vendex).
