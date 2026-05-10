# SHIPPED — uzum-claims

End-state of Phases 0–8 (commits `59cc33c` … head). All work committed
to `master`; no remote push, no production deploy.

## Phases done

| Phase | Commit | Deliverable |
|-------|--------|-------------|
| 0+1 | `59cc33c` | Bootstrap (FastAPI, Docker, JWT auth shim, 4 docx templates) + seller_profile schema, model, CRUD, profile UI |
| 2 | `8978330` | Returns short-pick detector, lost-items page, refresh button |
| 3 | `b03e3b6` | Manual physical-receipt confirmation, return_transit sibling rows |
| 4 | `3b19f11` | Re-authored docx templates with `{{token}}` placeholders, `docx_filler` engine, claim creation + generation + downloads, new-claim UI |
| 5 | `c9fb8b0` | FBO supply-reject detector |
| 6 | `4ca3c02` | Order-lost-delivery detector |
| 7 | `3b21aa7` | Claims history list, status PATCH endpoint, status updater UI |
| 8 | this commit | Vendex CSS fork, sidebar shell on every page, a11y form fields, mobile hamburger, this file |

## Stack

FastAPI 0.115 · async SQLAlchemy 2.0 · asyncpg · Alembic · python-docx 1.1 ·
PyJWT · vanilla JS (no build step) · forked vendex CSS for visual identity

## Endpoints (`/claims/api` in prod via nginx; `/api` direct in container)

| Method | Path | Phase |
|--------|------|-------|
| GET    | `/api/health` | 0 |
| GET    | `/api/whoami` | 0 |
| GET    | `/api/profile` | 1 |
| PUT    | `/api/profile` | 1 |
| GET    | `/api/losses?shop_id&type&claim_status` | 2 |
| POST   | `/api/losses/refresh` | 2 |
| POST   | `/api/losses/{id}/confirm` | 3 |
| POST   | `/api/claims` | 4 |
| GET    | `/api/claims/{id}` | 4 |
| POST   | `/api/claims/{id}/generate` | 4 |
| GET    | `/api/claims/{id}/download/{claim\|agreement}` | 4 |
| GET    | `/api/claims?status=` | 7 |
| PATCH  | `/api/claims/{id}` | 7 |

## Schema (Postgres, schema `claims`)

- `claims.seller_profile` — per-user legal profile (BIGINT user_id PK,
  fio, legal_form, legal_name, inn, bank_account, mfo, bank_name, address,
  oked, base_contract_no, base_contract_date, updated_at)
- `claims.claim` — id, user_id, shop_id, status (`draft|generated|submitted|paid|rejected`),
  total_amount, total_qty, generated_docx_path, generated_agreement_path,
  submitted_at, paid_at, paid_amount, notes, created_at
- `claims.lost_item` — id, user_id, shop_id, loss_type
  (`return_uzum_short|return_transit|fbo_supply_reject|fbo_warehouse|order_lost_delivery`),
  source_ref, uzum_sku_id, barcode, product_title, expected_qty, received_qty,
  unit_price, unit_compensation, reason, detected_at, confirmed_at,
  claim_id (FK → claim.id), raw_data (JSONB).
  Unique constraint `(user_id, source_ref, loss_type)` for idempotency.
- `claims.poll_state` — (user_id, shop_id, source) PK; reserved for
  per-source pagination cursors (currently unused — detectors do full scan).

Migrations: `0001_seller_profile`, `0002_lost_item_claim_poll`.

## Frontend pages

| Path | File | Purpose |
|------|------|---------|
| `/`            | `index.html`     | Landing + onboarding |
| `/profile`     | `profile.html`   | Seller legal form |
| `/losses`      | `losses.html`    | Detected lost items, group by shop+loss_type, refresh, inline receipt confirm, multi-select → create claim |
| `/new-claim`   | `new-claim.html` | Single claim view: summary, items, generate, download, status updater |
| `/claims`      | `claims.html`    | History list with status badges |

Shared: `js/api.js` (fetch + auth wrapper), `js/shell.js` (mobile
hamburger + slide-in sidebar), `css/styles.css` (forked vendex CSS +
claims-specific extensions appended).

## Auth

Shared HS256 JWT with vendex (`SECRET_KEY` matches). Token can arrive
via `Authorization: Bearer …` header (UI default, reads from
`localStorage.vendex_token`) or `vendex_token` cookie (prod path via
shared domain `/claims/`). The auth shim only decodes — no callback
into vendex `/api/me` for session validation (the upgrade is sketched
in `auth.py` docstring; deferred until a session is revoked in prod).

## Local dev

```bash
# Postgres + vendex stack must be up first (provides the shared db).
docker compose up -d --build
docker compose run --rm uzum-claims alembic upgrade head

# Mint a JWT with the shared secret to test:
python -c "import jwt,time; print(jwt.encode({'sub':'42','iat':int(time.time()),'exp':int(time.time())+86400}, '<vendex SECRET_KEY>', algorithm='HS256'))"
# Paste into browser localStorage.vendex_token, navigate to http://localhost:8100/.
```

## Templates

Originals from real Uzum compensation flow are backed up under
`templates/.original/`. Re-authored versions in `templates/` carry
`{{token}}` placeholders. To re-run the re-authoring (idempotent —
restores from backup first):

```bash
python scripts/reauthor_templates.py
```

Templates use scalars (`{{fio}}`, `{{legal_name}}`, `{{inn}}`,
`{{bank_account}}`, `{{mfo}}`, `{{bank_name}}`, `{{address}}`,
`{{base_contract_no}}`, `{{base_contract_date}}`, `{{claim_no}}`,
`{{claim_date}}`, `{{total_amount}}`, `{{total_qty}}`) and one items
template row with `{{item.product_title}}`, `{{item.barcode}}`,
`{{item.reason}}`, `{{item.expected_qty}}`, `{{item.received_qty}}`,
`{{item.unit_compensation}}`, `{{item.line_total}}`.

## Known follow-ups

- **Live Uzum smoke test** — backend code paths (returns / invoices /
  orders) compile and pass static checks; no shop has been pointed at
  Uzum yet. Once `UZUM_TEST_TOKEN` is provided, `POST /api/losses/refresh`
  with a real vendex integration row should populate real data.
- **`order_lost_delivery` cancelReason whitelist** — current set
  (`LOST_BY_CARRIER`, `DAMAGED_IN_TRANSIT`, …) is a guess. Tune after
  observing real Uzum cancelReason values.
- **`fbo_warehouse` detector** — not implemented; Uzum API doesn't expose
  FBO warehouse stock. Per PLAN §7, this likely needs manual entry or
  a dashboard scrape — out of scope for this run.
- **Auth: vendex `/api/me` callback** — only JWT decode today. To honour
  vendex session revocation, add a server-side validate hop in
  `backend/auth.py` once needed.
- **Uzbek docx output** — only Russian (`claim_ru`, `agreement_ru`) is
  generated end-to-end. UI lacks a language toggle. Templates were
  re-authored anyway; flipping a flag in the claims router would emit
  the UZ pair.
- **Cosmetic in re-authored docx** — leftover `_` characters from the
  original Uzum templates appear around tokens (e.g. `_{{inn}}__`,
  `____{{mfo}}`). Functional but ugly; refine templates by hand
  in Word/LibreOffice if desired.
- **Vendex side**: nginx route `/claims/`, docker-compose `uzum-claims`
  service, "Компенсации" nav link — all in vendex's workstream
  (PLAN §10), not in this repo.
- **Prod deploy** — not done. Requires the vendex-side nginx/compose
  patches to land first.

## Smoke artefacts

Verified during this run:
- `alembic upgrade head` → both migrations apply, 5 tables in `claims`
- `PUT /api/profile` round-trip with a forged JWT
- `POST /api/claims` then `POST /api/claims/{id}/generate` produced
  valid `claim_ru.docx` + `agreement_ru.docx` (parsed back via
  python-docx; tokens substituted, items table cloned)
- `PATCH /api/claims/{id}` transitions auto-stamp `submitted_at` /
  `paid_at`, persist `paid_amount` and `notes`
- All 5 frontend pages render with no JS console errors at desktop
  (1920×1080) and mobile (375×812); mobile hamburger + slide-in
  sidebar verified via Chrome DevTools MCP
