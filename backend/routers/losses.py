"""Lost items — list, refresh, manual receipt confirmation."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth import get_current_user_id
from backend.db import get_db
from backend.models import LostItem
from backend.schemas import LossOut, RefreshSummary
from backend.services import loss_detector

router = APIRouter()


def _bearer(request: Request) -> str:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth.split(" ", 1)[1]
    cookie = request.cookies.get("vendex_token")
    if cookie:
        return cookie
    raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing JWT")


@router.get("/losses", response_model=list[LossOut])
async def list_losses(
    shop_id: Optional[int] = None,
    type: Optional[str] = None,
    claim_status: Optional[str] = None,  # 'unclaimed' | 'claimed'
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    q = select(LostItem).where(LostItem.user_id == user_id)
    if shop_id is not None:
        q = q.where(LostItem.shop_id == shop_id)
    if type is not None:
        q = q.where(LostItem.loss_type == type)
    if claim_status == "unclaimed":
        q = q.where(LostItem.claim_id.is_(None))
    elif claim_status == "claimed":
        q = q.where(LostItem.claim_id.is_not(None))
    q = q.order_by(LostItem.detected_at.desc())
    rows = (await db.scalars(q)).all()
    return rows


@router.post("/losses/refresh", response_model=RefreshSummary)
async def refresh_losses(
    request: Request,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    jwt = _bearer(request)
    summary = await loss_detector.refresh_user(db, user_id=user_id, jwt=jwt)
    return summary
