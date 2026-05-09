"""Lost items — list, refresh, manual receipt confirmation."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth import get_current_user_id
from backend.db import get_db
from backend.models import LostItem
from backend.schemas import ConfirmReceiptIn, LossOut, RefreshSummary
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


@router.post("/losses/{loss_id}/confirm", response_model=LossOut)
async def confirm_receipt(
    loss_id: int,
    payload: ConfirmReceiptIn,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Mark physical receipt qty. If less than expected and the source is a
    return/supply, create a sibling `return_transit` row for the gap so it
    can be claimed separately.
    """
    row = await db.scalar(
        select(LostItem).where(LostItem.id == loss_id, LostItem.user_id == user_id)
    )
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Loss not found")
    if payload.received_qty > row.expected_qty:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"received_qty {payload.received_qty} > expected_qty {row.expected_qty}",
        )

    row.received_qty = payload.received_qty
    row.confirmed_at = datetime.now(timezone.utc)

    gap = row.expected_qty - payload.received_qty
    if gap > 0 and row.loss_type in {"return_uzum_short", "fbo_supply_reject"}:
        sibling_ref = f"{row.source_ref}:transit"
        existing = await db.scalar(
            select(LostItem).where(
                LostItem.user_id == user_id,
                LostItem.source_ref == sibling_ref,
                LostItem.loss_type == "return_transit",
            )
        )
        if existing is None:
            stmt = pg_insert(LostItem).values(
                user_id=user_id,
                shop_id=row.shop_id,
                loss_type="return_transit",
                source_ref=sibling_ref,
                uzum_sku_id=row.uzum_sku_id,
                barcode=row.barcode,
                product_title=row.product_title,
                expected_qty=gap,
                unit_price=row.unit_price,
                unit_compensation=row.unit_compensation,
                reason="утеря в транзите",
                raw_data={"parent_id": row.id, "parent_loss_type": row.loss_type},
            ).on_conflict_do_nothing(constraint="uq_lost_item_dedup")
            await db.execute(stmt)
        else:
            existing.expected_qty = gap

    await db.flush()
    await db.refresh(row)
    return row
