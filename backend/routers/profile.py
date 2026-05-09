"""Seller legal profile — CRUD for the per-user data that fills docx templates."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth import get_current_user_id
from backend.db import get_db
from backend.models import SellerProfile
from backend.schemas import SellerProfileIn, SellerProfileOut

router = APIRouter()


@router.get("/profile", response_model=SellerProfileOut)
async def get_profile(
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    row = await db.scalar(select(SellerProfile).where(SellerProfile.user_id == user_id))
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not set")
    return row


@router.put("/profile", response_model=SellerProfileOut)
async def upsert_profile(
    payload: SellerProfileIn,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    row = await db.scalar(select(SellerProfile).where(SellerProfile.user_id == user_id))
    if row is None:
        row = SellerProfile(user_id=user_id, **payload.model_dump())
        db.add(row)
    else:
        for k, v in payload.model_dump().items():
            setattr(row, k, v)
    await db.flush()
    await db.refresh(row)
    return row
