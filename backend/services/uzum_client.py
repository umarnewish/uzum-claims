"""Minimal async Uzum API client.

Auth header is the raw token (NO `Bearer ` prefix). Base:
https://api-seller.uzum.uz/api/seller-openapi
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, AsyncIterator, Optional

import httpx

logger = logging.getLogger(__name__)

BASE_URL = "https://api-seller.uzum.uz/api/seller-openapi"
DEFAULT_TIMEOUT = httpx.Timeout(30.0, connect=10.0)
# Uzum's /v1/return + /v1/invoice cap `size` at 50 (HTTP 400 above that).
# Mirror vendex's polite 0.2s inter-page delay.
DEFAULT_PAGE_SIZE = 50
INTER_PAGE_SLEEP = 0.2
MAX_RETRIES = 3


def client(token: str, lang: str = "ru") -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=BASE_URL,
        headers={"Authorization": token, "Accept-Language": lang},
        timeout=DEFAULT_TIMEOUT,
    )


async def _get(c: httpx.AsyncClient, path: str, params: Any = None) -> Any:
    """GET with 429/5xx retry. 4xx errors are surfaced immediately so we
    don't burn time on permanent failures (illegal-argument, missing scope)."""
    for attempt in range(1, MAX_RETRIES + 1):
        r = await c.get(path, params=params)
        if r.status_code == 429 or r.status_code >= 500:
            if attempt == MAX_RETRIES:
                r.raise_for_status()
            wait = float(r.headers.get("Retry-After", 2.0))
            logger.warning("uzum %s → %s, retry %d in %.1fs", path, r.status_code, attempt, wait)
            await asyncio.sleep(wait)
            continue
        r.raise_for_status()
        return r.json()
    raise RuntimeError("unreachable")


async def get_shops(token: str) -> list[dict]:
    """`GET /v1/shops` → [{id, name, ...}]."""
    async with client(token) as c:
        return await _get(c, "/v1/shops")


async def iter_returns(
    token: str, shop_id: int, *, page_size: int = DEFAULT_PAGE_SIZE,
) -> AsyncIterator[dict]:
    """Yield every return for a shop.

    Response shape (verified): bare list of returns; each return has
    `items: [{id, skuId, amount, packedAmount, productTitle, skuTitle,
    purchasePrice, ...}]`. Items lack `barcode`/`sellerPrice`.
    """
    async with client(token) as c:
        page = 0
        while True:
            params = {"shopId": shop_id, "page": page, "size": page_size}
            data = await _get(c, "/v1/return", params=params)
            rows = _unwrap_page(data)
            if not rows:
                return
            for r in rows:
                yield r
            if len(rows) < page_size:
                return
            page += 1
            await asyncio.sleep(INTER_PAGE_SLEEP)


async def get_return_detail(token: str, shop_id: int, return_id: int) -> dict:
    async with client(token) as c:
        return await _get(c, f"/v1/shop/{shop_id}/return/{return_id}")


async def iter_invoices(
    token: str, shop_id: int, *, page_size: int = DEFAULT_PAGE_SIZE,
) -> AsyncIterator[dict]:
    """`GET /v1/invoice?shopId=` — bare list, capped at size=50."""
    async with client(token) as c:
        page = 0
        while True:
            params = {"shopId": shop_id, "page": page, "size": page_size}
            data = await _get(c, "/v1/invoice", params=params)
            rows = _unwrap_page(data)
            if not rows:
                return
            for r in rows:
                yield r
            if len(rows) < page_size:
                return
            page += 1
            await asyncio.sleep(INTER_PAGE_SLEEP)


async def iter_invoice_lines(token: str, shop_id: int, invoice_id: int) -> list[dict]:
    """`GET /v1/shop/{shop}/invoice/products?invoiceId=` returns one entry
    per product; per-SKU breakdown lives under `skuForInvoiceDtoList`.
    Flatten so each yielded row is one SKU with its parent product's title.

    Field names: `quantityToStock` (sent) and `quantityAccepted` (received).
    """
    async with client(token) as c:
        data = await _get(
            c, f"/v1/shop/{shop_id}/invoice/products", params={"invoiceId": invoice_id}
        )
        rows = _unwrap_page(data) or (data if isinstance(data, list) else [])
    flat: list[dict] = []
    for product in rows:
        product_title = product.get("productTitle")
        skus = product.get("skuForInvoiceDtoList") or []
        if not skus:
            flat.append({
                "skuId": None,
                "skuTitle": product.get("skuTitle"),
                "productTitle": product_title,
                "quantityToStock": product.get("quantityToStock"),
                "quantityAccepted": product.get("quantityAccepted"),
                "purchasePrice": product.get("purchasePrice"),
                "id": product.get("id"),
            })
            continue
        for sku in skus:
            flat.append({
                "skuId": sku.get("id"),
                "skuTitle": sku.get("skuTitle"),
                "productTitle": product_title,
                "quantityToStock": sku.get("quantityToStock"),
                "quantityAccepted": sku.get("quantityAccepted"),
                "purchasePrice": sku.get("purchasePrice"),
                "id": sku.get("id"),
            })
    return flat


async def fetch_finance_orders(
    token: str, shop_ids: list[int], *,
    date_from_sec: int, date_to_sec: int,
) -> list[dict]:
    """`GET /v1/finance/orders` — needs `shopIds` repeated, dateFrom/To in
    SECONDS. Response: `{orderItems: [...], totalElements: N}`. Each item
    has status, returnCause, withdrawnProfit, sellerProfit, sellPrice,
    commission, productId, productTitle, skuTitle, etc.
    """
    if not shop_ids:
        return []
    items: list[dict] = []
    async with client(token) as c:
        page = 0
        size = DEFAULT_PAGE_SIZE
        while True:
            params: list[tuple[str, Any]] = [
                ("page", page),
                ("size", size),
                ("group", "false"),
                ("dateFrom", date_from_sec),
                ("dateTo", date_to_sec),
            ]
            for sid in shop_ids:
                params.append(("shopIds", sid))
            data = await _get(c, "/v1/finance/orders", params=params)
            batch = (data.get("orderItems") if isinstance(data, dict) else None) or []
            if not batch:
                return items
            items.extend(batch)
            if len(batch) < size:
                return items
            page += 1
            await asyncio.sleep(INTER_PAGE_SLEEP)


def _unwrap_page(data: Any) -> list[dict]:
    """Uzum responses come in mixed shapes: bare list, {payload:[]},
    {content:[]}, {data:[]}. Normalize."""
    if isinstance(data, list):
        return data
    if not isinstance(data, dict):
        return []
    for key in ("payload", "content", "data", "items", "result"):
        v = data.get(key)
        if isinstance(v, list):
            return v
    return []
