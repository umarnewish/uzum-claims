"""Loss-detection business logic.

Each detector is idempotent: dedup key on (user_id, source_ref, loss_type).
Re-running a refresh updates `expected_qty`/`unit_price`/etc on existing rows
without creating dupes.
"""
from __future__ import annotations

import logging
from typing import Any

from datetime import date as _date, timedelta as _td

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import LostItem
from backend.services import uzum_client, vendex_client

logger = logging.getLogger(__name__)


def _ret_source_ref(return_id: Any, item_key: Any) -> str:
    return f"return:{return_id}:{item_key}"


def _inv_source_ref(invoice_id: Any, item_key: Any) -> str:
    return f"invoice:{invoice_id}:{item_key}"


def _ord_source_ref(order_id: Any) -> str:
    return f"order:{order_id}"


async def _upsert_lost_item(db: AsyncSession, row: dict[str, Any]) -> None:
    """Insert or update on (user_id, source_ref, loss_type).

    Doesn't touch fields a human may have edited — `received_qty`,
    `confirmed_at`, `claim_id`. Detector is the source of truth for
    detected fields only.
    """
    stmt = pg_insert(LostItem).values(**row)
    stmt = stmt.on_conflict_do_update(
        constraint="uq_lost_item_dedup",
        set_={
            "shop_id": stmt.excluded.shop_id,
            "uzum_sku_id": stmt.excluded.uzum_sku_id,
            "barcode": stmt.excluded.barcode,
            "product_title": stmt.excluded.product_title,
            "expected_qty": stmt.excluded.expected_qty,
            "unit_price": stmt.excluded.unit_price,
            "unit_compensation": stmt.excluded.unit_compensation,
            "raw_data": stmt.excluded.raw_data,
        },
    )
    await db.execute(stmt)


async def detect_return_uzum_short(
    db: AsyncSession, *, user_id: int, shop_id: int, token: str,
) -> int:
    """Scan /v1/return for items where Uzum packed less than expected."""
    found = 0
    async for ret in uzum_client.iter_returns(token, shop_id):
        return_id = ret.get("id") or ret.get("returnId")
        if return_id is None:
            continue
        items = ret.get("items") or ret.get("returnItems") or []
        for it in items:
            amount = _coerce_int(it.get("amount"))
            packed = _coerce_int(it.get("packedAmount"))
            if amount is None or packed is None:
                continue
            if packed >= amount:
                continue
            short = amount - packed
            item_key = it.get("id") or it.get("productId") or it.get("skuId") or "x"
            # Return items lack barcode + sellerPrice fields (verified
            # against real API). Title falls back to skuTitle. Unit price
            # left NULL — enriched in Phase 5/6 from finance/orders.
            row = {
                "user_id": user_id,
                "shop_id": shop_id,
                "loss_type": "return_uzum_short",
                "source_ref": _ret_source_ref(return_id, item_key),
                "uzum_sku_id": it.get("skuId"),
                "barcode": it.get("barcode") or it.get("skuBarcode"),
                "product_title": (it.get("productTitle") or it.get("skuTitle")
                                  or it.get("title") or it.get("name")),
                "expected_qty": short,
                "unit_price": _coerce_int(it.get("sellerPrice"))
                              or _coerce_int(it.get("price"))
                              or _coerce_int(it.get("purchasePrice")),
                "unit_compensation": _coerce_compensation(it),
                "reason": "утеря",
                "raw_data": {"return": _slim(ret), "item": it},
            }
            await _upsert_lost_item(db, row)
            found += 1
    return found


def _parse_dmy(s: str | None) -> _date | None:
    """Uzum's invoice dates are 'DD.MM.YYYY' strings."""
    if not s:
        return None
    try:
        d, m, y = s.split(".")
        return _date(int(y), int(m), int(d))
    except (ValueError, AttributeError):
        return None


async def detect_supply_reject(
    db: AsyncSession, *, user_id: int, shop_id: int, token: str,
    days_window: int = 90,
) -> int:
    """Scan /v1/invoice + /v1/shop/{shop}/invoice/products for SKU-level
    shortfalls. Skip invoices that haven't been accepted yet (status
    NEW/IN_PROGRESS — `quantityAccepted` legitimately starts at 0 there
    and would otherwise create a noisy row per SKU per pending supply).

    Field names: `quantityToStock` (sent) vs `quantityAccepted` (received).
    Bounded to invoices created in the last `days_window` days to keep
    the per-invoice line-fetch fan-out tractable. Uzum returns invoices
    sorted DESC by date, so we can early-exit once we cross the window.
    """
    # CREATED/IN_TRANSIT invoices haven't reached the warehouse yet — their
    # quantityAccepted is legitimately 0 and would otherwise produce a
    # noisy row per SKU per pending supply.
    SKIP_STATUSES = {"CREATED", "NEW", "IN_PROGRESS", "DRAFT", "PENDING", "IN_TRANSIT"}
    cutoff = _date.today() - _td(days=days_window)
    found = 0
    async for inv in uzum_client.iter_invoices(token, shop_id):
        invoice_id = inv.get("id") or inv.get("invoiceId")
        if invoice_id is None:
            continue
        created = _parse_dmy(inv.get("dateCreated"))
        if created is not None and created < cutoff:
            return found  # early exit: rest of pages are older
        # `invoiceStatus` is an object: {text, color, value}. Pull `.value`.
        st_obj = inv.get("invoiceStatus") or inv.get("status")
        if isinstance(st_obj, dict):
            status = (st_obj.get("value") or "").upper()
        else:
            status = (st_obj or "").upper()
        if status in SKIP_STATUSES:
            continue
        try:
            lines = await uzum_client.iter_invoice_lines(token, shop_id, invoice_id)
        except Exception as e:
            logger.warning("invoice %s lines failed: %s", invoice_id, e)
            continue
        for line in lines:
            sent = _coerce_int(line.get("quantityToStock"))
            accepted = _coerce_int(line.get("quantityAccepted"))
            if sent is None or accepted is None:
                continue
            short = sent - accepted
            if short <= 0:
                continue
            item_key = line.get("id") or line.get("skuId") or "x"
            row = {
                "user_id": user_id,
                "shop_id": shop_id,
                "loss_type": "fbo_supply_reject",
                "source_ref": _inv_source_ref(invoice_id, item_key),
                "uzum_sku_id": line.get("skuId"),
                "barcode": None,
                "product_title": line.get("productTitle") or line.get("skuTitle"),
                "expected_qty": short,
                "unit_price": _coerce_int(line.get("purchasePrice")),
                "unit_compensation": _coerce_int(line.get("purchasePrice")),
                "reason": "брак при приёмке",
                "raw_data": {"invoice_id": invoice_id, "invoice_status": status, "line": line},
            }
            await _upsert_lost_item(db, row)
            found += 1
    return found


def _is_loss_returncause(rc: str | None) -> bool:
    """Heuristic on Russian Uzum returnCause strings. Matches phrases
    that signal Uzum-side loss / non-delivery (no payout to seller),
    not customer-side cancellations or refunds.

    Curated from observed values — extend as new strings appear.
    """
    if not rc:
        return False
    s = rc.lower()
    # Whitelisted phrases that indicate Uzum/logistics loss.
    POSITIVE = (
        "до получения",     # "Отменён до получения" — never reached customer
        "потер",            # потеряно
        "склад",            # склад / warehouse loss
        "достав",           # доставка / delivery issue
        "поврежд",          # повреждение / damage
        "брак",             # defect found by Uzum
        "не доехал",
    )
    # Phrases that look loss-shaped but are customer-side; explicit deny.
    NEGATIVE = (
        "клиент",           # клиент отказался
        "покупател",        # покупатель отказался
        "передум",          # передумал
        "возврат",          # purchase return — distinct from claims flow
    )
    if any(n in s for n in NEGATIVE):
        return False
    return any(p in s for p in POSITIVE)


async def detect_order_lost_delivery(
    db: AsyncSession, *, user_id: int, shop_id: int, token: str,
    days_window: int = 90,
) -> int:
    """Scan /v1/finance/orders for CANCELED/PARTIALLY_CANCELLED items
    with no payout (`withdrawnProfit == 0`) and a loss-shaped returnCause.

    Pivoted from /v2/fbs/orders (which 403s on regular seller tokens) to
    finance/orders (verified working in vendex). Date window defaults to
    last 90 days to keep the scan bounded.
    """
    import time

    LOSS_STATUSES = {"CANCELED", "CANCELLED", "PARTIALLY_CANCELLED"}
    now_sec = int(time.time())
    date_from_sec = now_sec - days_window * 86400

    items = await uzum_client.fetch_finance_orders(
        token, [shop_id], date_from_sec=date_from_sec, date_to_sec=now_sec
    )
    found = 0
    for it in items:
        st = (it.get("status") or "").upper()
        if st not in LOSS_STATUSES:
            continue
        # If the seller already got paid, this is not a loss.
        withdrawn = _coerce_int(it.get("withdrawnProfit")) or 0
        if withdrawn > 0:
            continue
        rc = it.get("returnCause") or it.get("cancelReason")
        if not _is_loss_returncause(rc):
            continue
        order_id = it.get("orderId") or it.get("id")
        item_key = it.get("id") or it.get("productId") or "x"
        qty = _coerce_int(it.get("amount") or it.get("quantity")) or 1
        seller_price = (_coerce_int(it.get("sellPrice"))
                        or _coerce_int(it.get("sellerPrice")))
        commission = _coerce_int(it.get("commission")) or 0
        comp = max((seller_price or 0) - commission, 0) if seller_price is not None else None
        row = {
            "user_id": user_id,
            "shop_id": shop_id,
            "loss_type": "order_lost_delivery",
            "source_ref": f"{_ord_source_ref(order_id)}:{item_key}",
            "uzum_sku_id": it.get("skuId") or it.get("productId"),
            "barcode": None,
            "product_title": it.get("productTitle") or it.get("skuTitle"),
            "expected_qty": qty,
            "unit_price": seller_price,
            "unit_compensation": comp,
            "reason": "потерян при доставке",
            "raw_data": {"finance_item": it},
        }
        await _upsert_lost_item(db, row)
        found += 1
    return found


async def refresh_user(db: AsyncSession, *, user_id: int, jwt: str) -> dict[str, Any]:
    """Run every detector for every shop the user has connected in vendex."""
    shops = await vendex_client.list_uzum_shops(jwt)
    summary: dict[str, Any] = {
        "shops": 0,
        "return_uzum_short": 0,
        "fbo_supply_reject": 0,
        "order_lost_delivery": 0,
        "errors": [],
    }
    for shop in shops:
        if not shop.get("active") or not shop.get("token"):
            continue
        token = shop["token"]
        shop_id = shop.get("shop_id")
        sids: list[int] = []
        if shop_id is None:
            try:
                uzum_shops = await uzum_client.get_shops(token)
                sids = [int(s["id"]) for s in uzum_shops]
            except Exception as e:
                summary["errors"].append(f"get_shops: {e}")
                continue
        else:
            sids = [int(shop_id)]
        for sid in sids:
            summary["shops"] += 1
            for name, fn in (
                ("return_uzum_short", detect_return_uzum_short),
                ("fbo_supply_reject", detect_supply_reject),
                ("order_lost_delivery", detect_order_lost_delivery),
            ):
                try:
                    n = await fn(db, user_id=user_id, shop_id=sid, token=token)
                    summary[name] += n
                except Exception as e:
                    summary["errors"].append(f"shop {sid}/{name}: {e}")
    return summary


def _coerce_int(v: Any) -> int | None:
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _coerce_compensation(item: dict[str, Any]) -> int | None:
    """unit_compensation = sellerPrice − commission (Uzum rule 6.8).

    Return items don't always carry commission — fall back to sellerPrice
    or None. Phase 5/6 enrich via /v1/finance/orders.
    """
    seller = _coerce_int(item.get("sellerPrice"))
    commission = _coerce_int(item.get("commission"))
    if seller is None:
        return None
    if commission is None:
        return seller
    return max(seller - commission, 0)


def _slim(d: dict) -> dict:
    """Drop bulky nested fields from raw_data for storage sanity."""
    return {k: v for k, v in d.items() if k not in ("items", "returnItems")}
