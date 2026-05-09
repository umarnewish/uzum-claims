# uzum-claims — Standalone Project Plan

## 1. Goal

Track lost items + lost orders (FBS & FBO) and auto-generate Uzum compensation claim docx files. Standalone codebase to keep token cost low when iterating, but deployed on the same DigitalOcean droplet as vendex and accessed seamlessly via a new tab inside vendex UI.

## 2. Architecture

```
Internet ──► nginx (existing on vendex droplet) ──┬──► vendex container          (port 8000)
                                                  └──► uzum-claims container     (port 8100)
                                                       │
                                                       ▼
                                                  shared Postgres (own schema)
```

- Same droplet: `root@159.89.19.29`
- Same nginx: add `location /claims/ { proxy_pass http://uzum-claims:8100/; }`
- Same Postgres instance, separate **schema** `claims` to keep tables logically isolated
- Same JWT secret → vendex auth works in claims service automatically
- Vendex frontend gets a new top-nav tab "Компенсации" linking to `/claims/`

## 3. Tech stack

| Layer | Choice | Reason |
|-------|--------|--------|
| Backend | FastAPI (Python 3.11) | Same as vendex, smallest learning cost |
| DB | PostgreSQL (shared instance, own schema) | One Postgres to manage |
| ORM | SQLAlchemy + Alembic | Same as vendex |
| Docx generation | `python-docx` | Standard, reads Word templates with placeholders |
| Frontend | Vanilla JS + same CSS as vendex | Identical look-and-feel |
| Auth | JWT (HS256), shared secret with vendex | Seamless SSO |
| Container | Docker, joined to vendex's docker network | Reuses existing infra |

## 4. Repo layout

```
/home/umar/Desktop/uzum-claims/
├── backend/
│   ├── main.py
│   ├── auth.py                 # validates vendex JWT
│   ├── routers/
│   │   ├── losses.py           # list/confirm lost items
│   │   ├── claims.py           # CRUD claims, generate docx
│   │   └── profile.py          # seller legal profile
│   ├── services/
│   │   ├── vendex_client.py    # HTTP client → vendex read API
│   │   ├── uzum_client.py      # minimal Uzum client (returns/invoices/finance only)
│   │   ├── loss_detector.py    # business logic for each loss type
│   │   └── docx_filler.py      # template fill engine
│   ├── models.py               # SQLAlchemy
│   ├── schemas.py              # Pydantic
│   └── db.py
├── templates/                  # the 4 docx files (copied from vendex/)
│   ├── claim_ru.docx
│   ├── claim_uz.docx
│   ├── agreement_ru.docx
│   └── agreement_uz.docx
├── frontend/
│   ├── index.html
│   ├── losses.html
│   ├── claims.html
│   ├── profile.html
│   ├── shared/
│   │   └── styles.css          # symlink or copy of vendex/frontend/styles.css
│   └── js/
├── alembic/
├── Dockerfile
├── docker-compose.yml          # for local dev
├── requirements.txt
└── README.md
```

## 5. Data model (schema `claims`)

```sql
-- Mirrors vendex.user_id; not a FK, just reference
CREATE TABLE claims.seller_profile (
  user_id        BIGINT PRIMARY KEY,
  fio            TEXT NOT NULL,           -- Абдурахимов Фозил Тошкулович
  legal_form     TEXT NOT NULL,           -- "ООО"
  legal_name     TEXT NOT NULL,           -- "ALFA POLIMER LINE"
  inn            TEXT NOT NULL,
  bank_account   TEXT NOT NULL,
  mfo            TEXT NOT NULL,
  bank_name      TEXT NOT NULL,
  address        TEXT NOT NULL,
  oked           TEXT,
  base_contract_no TEXT,                  -- referenced in agreement docx
  base_contract_date DATE,
  updated_at     TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE claims.lost_item (
  id             BIGSERIAL PRIMARY KEY,
  user_id        BIGINT NOT NULL,
  shop_id        BIGINT NOT NULL,
  loss_type      TEXT NOT NULL,           -- 'return_uzum_short', 'return_transit',
                                          -- 'fbo_warehouse', 'fbo_supply_reject',
                                          -- 'order_lost_delivery'
  source_ref     TEXT NOT NULL,           -- return_id / invoice_id / order_id
  uzum_sku_id    BIGINT,
  barcode        TEXT,
  product_title  TEXT,
  expected_qty   INT NOT NULL,
  received_qty   INT,                     -- NULL until user confirms physical receipt
  unit_price     BIGINT,                  -- sellerPrice from finance
  unit_compensation BIGINT,               -- sellerPrice − commission (per Uzum rule 6.8)
  reason         TEXT,                    -- 'утеря' | 'повреждение'
  detected_at    TIMESTAMPTZ DEFAULT now(),
  confirmed_at   TIMESTAMPTZ,
  claim_id       BIGINT REFERENCES claims.claim(id),
  raw_data       JSONB                    -- full source record
);
CREATE INDEX ON claims.lost_item(user_id, claim_id);

CREATE TABLE claims.claim (
  id             BIGSERIAL PRIMARY KEY,
  user_id        BIGINT NOT NULL,
  shop_id        BIGINT NOT NULL,
  status         TEXT NOT NULL,           -- 'draft', 'generated', 'submitted', 'paid', 'rejected'
  total_amount   BIGINT,
  total_qty      INT,
  generated_docx_path TEXT,
  generated_agreement_path TEXT,
  submitted_at   TIMESTAMPTZ,
  paid_at        TIMESTAMPTZ,
  paid_amount    BIGINT,
  notes          TEXT,
  created_at     TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE claims.poll_state (
  user_id        BIGINT NOT NULL,
  shop_id        BIGINT NOT NULL,
  source         TEXT NOT NULL,           -- 'returns', 'invoices', 'finance', 'orders'
  last_polled_at TIMESTAMPTZ,
  last_cursor    TEXT,
  PRIMARY KEY (user_id, shop_id, source)
);
```

## 6. Endpoints

### uzum-claims (own API, prefix `/claims/api`)

| Method | Path | Purpose |
|--------|------|---------|
| GET    | `/profile` | Get seller legal profile |
| PUT    | `/profile` | Update legal profile |
| GET    | `/losses?shop_id=&type=&claim_status=` | List detected lost items |
| POST   | `/losses/{id}/confirm` | Mark physical receipt qty |
| POST   | `/losses/refresh` | Trigger poll-and-detect for current user |
| POST   | `/claims` | Create claim from selected lost_item ids |
| GET    | `/claims` | List user's claims |
| GET    | `/claims/{id}` | Claim detail + items |
| POST   | `/claims/{id}/generate` | Generate docx + agreement, return file paths |
| GET    | `/claims/{id}/download/claim` | Stream claim docx |
| GET    | `/claims/{id}/download/agreement` | Stream agreement docx |
| PATCH  | `/claims/{id}` | Update status (submitted/paid/rejected), add notes |

### vendex (new endpoints to support claims service)

| Method | Path | Purpose |
|--------|------|---------|
| GET    | `/api/integrations/shops` | List user's connected Uzum shops + tokens (encrypted, internal-only) |
| GET    | `/api/me` | Current user info (JWT validation reuse) |

(Claims service holds its own Uzum poll loop using shop tokens fetched from vendex; alternative: vendex proxies Uzum calls. Direct token fetch is simpler.)

## 7. Loss detection logic

| `loss_type` | Detection |
|-------------|-----------|
| `return_uzum_short` | Poll `/v1/return` → for each item, `expected_qty = amount`, `received_qty_uzum = packedAmount`. If `packedAmount < amount` → record |
| `return_transit` | Manual: user marks `received_qty < packedAmount` in UI |
| `fbo_supply_reject` | Poll `/v1/invoice` → for each invoice, `totalToStock − totalAccepted` per line item via `/v1/shop/{shopId}/invoice/products` |
| `fbo_warehouse` | Reconcile periodically: `Σ totalAccepted − Σ sold (finance/orders) − Σ returns` ≠ exposed warehouse stock. **NOTE:** API doesn't expose FBO warehouse stock → may require manual entry or Uzum dashboard scrape |
| `order_lost_delivery` | Poll `/v2/fbs/orders` for `status=CANCELED`/`RETURNED` w/ specific cancelReason values + cross-check no payout in `/v1/finance/orders` |

Each detected item gets `unit_compensation = sellerPrice − commission` (from finance/orders, fallback: configurable per-SKU).

## 8. Docx generation

`python-docx` approach:
- Templates use **placeholder tokens**: `{{fio}}`, `{{legal_name}}`, `{{inn}}`, etc.
- For tables: pre-existing template table with one example row tagged `{{#items}}`...`{{/items}}`; engine clones the row per item.
- We will **re-author the 4 existing templates once** to embed these tokens (keep the original layout pixel-perfect; just swap blank lines for `{{tokens}}`).
- Output file: `claim_<shop>_<date>.docx` saved to `/var/uzum-claims/generated/<user_id>/`.

## 9. Frontend (in claims service)

Pages, all reusing vendex CSS:
- **Lost Items** — table grouped by shop and loss type. Each row: select checkbox, product, barcode, expected/received qty, compensation/unit, total. "Confirm received" inline editor.
- **New Claim** — pick selected lost items → preview total → "Generate" → download both docx (claim + agreement).
- **Claims History** — list of past claims with status (draft/generated/submitted/paid). Update status + paid_amount.
- **Profile** — seller legal info form (one-time setup, edit anytime).

Top nav matches vendex: same logo strip, same color scheme, links back to `/`.

## 10. Vendex changes (minimal)

- `frontend/index.html` (or wherever nav lives): add `<a href="/claims/">Компенсации</a>`
- `backend/routers/integrations.py` (new or extend): add `GET /api/integrations/shops` returning shop list + decrypted tokens for the authenticated user (internal call, response only flows to claims service running on same network)
- `backend/routers/me.py` (likely already exists): ensure exposed for cross-service auth check
- `nginx/conf.d/vendex.conf`: add `location /claims/ { proxy_pass http://uzum-claims:8100/; ... }`
- `docker-compose.prod.yml`: add `uzum-claims` service entry on same network

That is the entirety of vendex-side work — keeps token cost low.

## 11. Auth flow

1. User logs into vendex (existing Telegram-bot 6-digit flow) → vendex sets JWT cookie
2. User clicks "Компенсации" → browser navigates to `/claims/`
3. Same cookie sent (same domain) → uzum-claims FastAPI middleware decodes JWT with shared secret → user_id available
4. uzum-claims calls vendex `/api/me` and `/api/integrations/shops` server-side using forwarded JWT, fetches what it needs

No new login. No iframe. Pure SSO via shared cookie.

## 12. Deployment

`docker-compose.prod.yml` additions:
```yaml
  uzum-claims:
    build: ../uzum-claims
    restart: unless-stopped
    env_file: ../uzum-claims/.env
    environment:
      - JWT_SECRET=${JWT_SECRET}             # SAME as vendex
      - DATABASE_URL=postgresql://.../vendex # same DB, schema=claims
      - VENDEX_INTERNAL_URL=http://app:8000
    volumes:
      - claims_generated:/var/uzum-claims/generated
    networks: [vendex_net]

volumes:
  claims_generated:
```

`nginx/conf.d/vendex.conf` addition:
```nginx
location /claims/ {
    proxy_pass http://uzum-claims:8100/;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header Cookie $http_cookie;
}
```

Deploy command (mirrors vendex):
```bash
ssh root@159.89.19.29
cd /opt/vendex && git pull
cd /opt/uzum-claims && git pull          # separate clone
cd /opt/vendex && docker compose -f docker-compose.prod.yml up -d --build
```

## 13. Build phases

| Phase | Deliverable | Effort |
|-------|-------------|--------|
| **0** | Bootstrap: repo, Dockerfile, FastAPI skeleton, JWT auth middleware, vendex client stub, "hello world" served at `/claims/` on prod | 0.5 day |
| **1** | Schema + Alembic, seller profile CRUD UI | 0.5 day |
| **2** | Returns poller + `return_uzum_short` detection, lost-items list UI | 1 day |
| **3** | Manual physical-receipt confirmation (`return_transit`) | 0.5 day |
| **4** | Docx generation (re-author 4 templates with placeholders, build filler, claim creation flow) | 1 day |
| **5** | FBO supply detection (`fbo_supply_reject`) | 0.5 day |
| **6** | Lost orders detection (`order_lost_delivery`) | 0.5 day |
| **7** | Claims history, status tracking, paid_amount | 0.5 day |
| **8** | Polish UI, vendex nav link, prod deploy | 0.5 day |

Total: ~5 working days end-to-end. Ph 0–4 alone unlocks first real claim file — ~3.5 days to value.

## 14. Open questions to resolve before phase 0

- Confirm shared Postgres + own schema (vs separate DB) — recommended: shared+schema
- Phase ordering OK?
- Initial seed for SKU mapping (still unanswered for vendex multi-store work — separate from this plan but related)
