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
DEFAULT_PAGE_SIZE = 100
MAX_RETRIES = 4


def client(token: str, lang: str = "ru") -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=BASE_URL,
        headers={"Authorization": token, "Accept-Language": lang},
        timeout=DEFAULT_TIMEOUT,
    )


async def _get(c: httpx.AsyncClient, path: str, params: dict[str, Any] | None = None) -> Any:
    """GET with 429/5xx retry + exponential backoff."""
    delay = 0.5
    for attempt in range(1, MAX_RETRIES + 1):
        r = await c.get(path, params=params)
        if r.status_code == 429 or r.status_code >= 500:
            if attempt == MAX_RETRIES:
                r.raise_for_status()
            wait = float(r.headers.get("Retry-After", delay))
            logger.warning("uzum %s %s → %s, retry %d in %.1fs", path, params, r.status_code, attempt, wait)
            await asyncio.sleep(wait)
            delay *= 2
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
    """Yield every return for a shop. `/v1/return` is paginated.

    Each return has shape: {id, status, items: [{productId, skuId, amount,
    packedAmount, ...}], ...}.
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


async def get_return_detail(token: str, shop_id: int, return_id: int) -> dict:
    async with client(token) as c:
        return await _get(c, f"/v1/shop/{shop_id}/return/{return_id}")


async def iter_invoices(
    token: str, shop_id: int, *, page_size: int = DEFAULT_PAGE_SIZE,
) -> AsyncIterator[dict]:
    async with client(token) as c:
        page = 0
        while True:
            params = {"shopId": shop_id, "page": page, "size": page_size}
            data = await _get(c, f"/v1/shop/{shop_id}/invoice", params=params)
            rows = _unwrap_page(data)
            if not rows:
                return
            for r in rows:
                yield r
            if len(rows) < page_size:
                return
            page += 1


async def iter_invoice_lines(token: str, shop_id: int, invoice_id: int) -> list[dict]:
    async with client(token) as c:
        data = await _get(
            c, f"/v1/shop/{shop_id}/invoice/products", params={"invoiceId": invoice_id}
        )
        return _unwrap_page(data) or (data if isinstance(data, list) else [])


async def iter_orders(
    token: str, shop_id: int, *, since_ms: Optional[int] = None,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> AsyncIterator[dict]:
    """`GET /v2/fbs/orders`. Emits raw order dicts."""
    async with client(token) as c:
        page = 0
        while True:
            params: dict[str, Any] = {"shopId": shop_id, "page": page, "size": page_size}
            if since_ms is not None:
                params["dateFrom"] = since_ms
            data = await _get(c, "/v2/fbs/orders", params=params)
            rows = _unwrap_page(data)
            if not rows:
                return
            for r in rows:
                yield r
            if len(rows) < page_size:
                return
            page += 1


async def fetch_finance_orders(
    token: str, shop_ids: list[int], *, date_from_ms: int, date_to_ms: int,
) -> list[dict]:
    """`GET /v1/finance/orders` — paginated, no shopId filter; needs shopIds[]."""
    if not shop_ids:
        return []
    items: list[dict] = []
    async with client(token) as c:
        page = 0
        size = DEFAULT_PAGE_SIZE
        while True:
            params: list[tuple[str, Any]] = [
                ("dateFrom", date_from_ms),
                ("dateTo", date_to_ms),
                ("page", page),
                ("size", size),
            ]
            for sid in shop_ids:
                params.append(("shopIds", sid))
            data = await _get(c, "/v1/finance/orders", params=params)
            rows = _unwrap_page(data)
            if not rows:
                return items
            items.extend(rows)
            if len(rows) < size:
                return items
            page += 1


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
