"""Loss-detection business logic.

Each detector is idempotent: dedup key on (user_id, source_ref, loss_type).
Re-running a refresh updates `expected_qty`/`unit_price`/etc on existing rows
without creating dupes.
"""
from __future__ import annotations

import logging
from typing import Any

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
    """Scan /v1/return for items where Uzum packed less than expected.

    Returns count of detected/updated rows.
    """
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
            row = {
                "user_id": user_id,
                "shop_id": shop_id,
                "loss_type": "return_uzum_short",
                "source_ref": _ret_source_ref(return_id, item_key),
                "uzum_sku_id": it.get("skuId"),
                "barcode": it.get("barcode") or it.get("skuBarcode"),
                "product_title": it.get("productTitle") or it.get("title") or it.get("name"),
                "expected_qty": short,
                "unit_price": _coerce_int(it.get("sellerPrice")) or _coerce_int(it.get("price")),
                "unit_compensation": _coerce_compensation(it),
                "reason": "утеря",
                "raw_data": {"return": _slim(ret), "item": it},
            }
            await _upsert_lost_item(db, row)
            found += 1
    return found


async def detect_supply_reject(
    db: AsyncSession, *, user_id: int, shop_id: int, token: str,
) -> int:
    """Scan /v1/invoice for FBO supply lines where Uzum accepted less than
    we sent (totalToStock − totalAccepted > 0). Each shortfall is a row
    of loss_type='fbo_supply_reject'.
    """
    found = 0
    async for inv in uzum_client.iter_invoices(token, shop_id):
        invoice_id = inv.get("id") or inv.get("invoiceId")
        if invoice_id is None:
            continue
        try:
            lines = await uzum_client.iter_invoice_lines(token, shop_id, invoice_id)
        except Exception as e:
            logger.warning("invoice %s lines failed: %s", invoice_id, e)
            continue
        for line in lines:
            sent = _coerce_int(line.get("totalToStock"))
            accepted = _coerce_int(line.get("totalAccepted"))
            if sent is None or accepted is None:
                continue
            short = sent - accepted
            if short <= 0:
                continue
            item_key = line.get("id") or line.get("productId") or line.get("skuId") or "x"
            row = {
                "user_id": user_id,
                "shop_id": shop_id,
                "loss_type": "fbo_supply_reject",
                "source_ref": _inv_source_ref(invoice_id, item_key),
                "uzum_sku_id": line.get("skuId"),
                "barcode": line.get("barcode") or line.get("skuBarcode"),
                "product_title": line.get("productTitle") or line.get("title") or line.get("name"),
                "expected_qty": short,
                "unit_price": _coerce_int(line.get("sellerPrice")) or _coerce_int(line.get("price")),
                "unit_compensation": _coerce_compensation(line),
                "reason": "брак при приёмке",
                "raw_data": {"invoice": _slim(inv), "line": line},
            }
            await _upsert_lost_item(db, row)
            found += 1
    return found


async def detect_order_lost_delivery(
    db: AsyncSession, *, user_id: int, shop_id: int, token: str,
) -> int:
    """Scan /v2/fbs/orders for CANCELED/RETURNED orders whose cancelReason
    looks loss-shaped (carrier/storage loss, damage in transit). Each such
    order item is one lost_item row.

    Conservative: an order with status=CANCELED but a non-loss cancelReason
    (customer cancellation, return-by-customer) is skipped. Tune
    LOSS_CANCEL_REASONS after seeing real production data; until then,
    a missing reason means we accept the order if status alone matches.
    """
    LOSS_STATUSES = {"CANCELED", "CANCELLED", "RETURNED"}
    LOSS_CANCEL_REASONS = {
        "LOST_BY_CARRIER", "LOST_IN_DELIVERY", "DAMAGED_IN_TRANSIT",
        "LOST_IN_TRANSIT", "WAREHOUSE_LOSS", "COURIER_LOST",
    }
    found = 0
    async for order in uzum_client.iter_orders(token, shop_id):
        st = (order.get("status") or "").upper()
        if st not in LOSS_STATUSES:
            continue
        reason = (order.get("cancelReason") or order.get("reason") or "").upper()
        if reason and reason not in LOSS_CANCEL_REASONS:
            continue
        order_id = order.get("id") or order.get("orderId")
        if order_id is None:
            continue
        items = order.get("items") or order.get("orderItems") or []
        for it in items:
            qty = _coerce_int(it.get("amount") or it.get("quantity")) or 1
            item_key = it.get("id") or it.get("productId") or it.get("skuId") or "x"
            row = {
                "user_id": user_id,
                "shop_id": shop_id,
                "loss_type": "order_lost_delivery",
                "source_ref": f"{_ord_source_ref(order_id)}:{item_key}",
                "uzum_sku_id": it.get("skuId"),
                "barcode": it.get("barcode") or it.get("skuBarcode"),
                "product_title": it.get("productTitle") or it.get("title") or it.get("name"),
                "expected_qty": qty,
                "unit_price": _coerce_int(it.get("sellerPrice")) or _coerce_int(it.get("price")),
                "unit_compensation": _coerce_compensation(it),
                "reason": "потерян при доставке",
                "raw_data": {"order": _slim(order), "item": it, "cancelReason": reason},
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
