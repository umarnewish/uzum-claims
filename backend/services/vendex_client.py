"""HTTP client for vendex's cross-service endpoints.

Forwards the user's JWT in the `Authorization: Bearer …` header so vendex
can decode the same token (shared SECRET_KEY).
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

from backend.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

DEFAULT_TIMEOUT = httpx.Timeout(15.0, connect=5.0)


def _client(jwt: str) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=settings.VENDEX_INTERNAL_URL,
        headers={"Authorization": f"Bearer {jwt}"},
        timeout=DEFAULT_TIMEOUT,
    )


async def get_me(jwt: str) -> dict[str, Any]:
    async with _client(jwt) as c:
        r = await c.get("/api/me")
        r.raise_for_status()
        return r.json()


async def list_uzum_shops(jwt: str) -> list[dict[str, Any]]:
    """[{shop_id, shop_name, token, active}] — token is plaintext, treat
    as a secret. Vendex marks the endpoint internal-only."""
    async with _client(jwt) as c:
        r = await c.get("/api/integrations/uzum/shops")
        r.raise_for_status()
        return r.json()
