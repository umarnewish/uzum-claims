"""Claims — group lost items into a draft, generate docx, download files."""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth import get_current_user_id
from backend.config import get_settings
from backend.db import get_db
from backend.models import Claim, LostItem, SellerProfile
from backend.schemas import ClaimCreateIn, ClaimOut, ClaimPatchIn, ClaimWithItemsOut
from backend.services import docx_filler

logger = logging.getLogger(__name__)
settings = get_settings()
router = APIRouter()

TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent / "templates"


@router.post("/claims", response_model=ClaimOut, status_code=status.HTTP_201_CREATED)
async def create_claim(
    payload: ClaimCreateIn,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    if not payload.lost_item_ids:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "lost_item_ids is empty")

    rows = (await db.scalars(
        select(LostItem).where(
            LostItem.id.in_(payload.lost_item_ids), LostItem.user_id == user_id
        )
    )).all()
    if len(rows) != len(set(payload.lost_item_ids)):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Some lost items not found")
    already_claimed = [r.id for r in rows if r.claim_id is not None]
    if already_claimed:
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"Already in another claim: {already_claimed}"
        )
    shop_ids = {r.shop_id for r in rows}
    if len(shop_ids) > 1:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Mixed shops in one claim ({sorted(shop_ids)}); claims are per-shop",
        )

    total_qty = sum(_outstanding_qty(r) for r in rows)
    total_amount = sum((r.unit_compensation or 0) * _outstanding_qty(r) for r in rows)

    claim = Claim(
        user_id=user_id,
        shop_id=rows[0].shop_id,
        status="draft",
        total_amount=total_amount,
        total_qty=total_qty,
    )
    db.add(claim)
    await db.flush()
    for r in rows:
        r.claim_id = claim.id
    await db.flush()
    await db.refresh(claim)
    return claim


@router.post("/claims/{claim_id}/generate", response_model=ClaimOut)
async def generate_docx(
    claim_id: int,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    claim = await db.scalar(
        select(Claim).where(Claim.id == claim_id, Claim.user_id == user_id)
    )
    if claim is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Claim not found")
    profile = await db.scalar(
        select(SellerProfile).where(SellerProfile.user_id == user_id)
    )
    if profile is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Profile not set — fill /profile before generating docx",
        )
    items_rows = (await db.scalars(
        select(LostItem).where(LostItem.claim_id == claim.id).order_by(LostItem.id)
    )).all()
    if not items_rows:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Claim has no items")

    today = date.today()
    ctx = {
        "fio": profile.fio,
        "legal_form": profile.legal_form,
        "legal_name": profile.legal_name,
        "inn": profile.inn,
        "bank_account": profile.bank_account,
        "mfo": profile.mfo,
        "bank_name": profile.bank_name,
        "address": profile.address,
        "oked": profile.oked or "",
        "base_contract_no": profile.base_contract_no or "",
        "base_contract_date": profile.base_contract_date.strftime("%d.%m.%Y") if profile.base_contract_date else "",
        "claim_no": str(claim.id),
        "claim_date": today.strftime("«%d» %m %y"),
        "total_amount": _fmt_money(claim.total_amount),
        "total_qty": str(claim.total_qty or 0),
    }
    items = [_item_ctx(r) for r in items_rows]

    out_dir = Path(settings.GENERATED_DIR) / str(user_id) / str(claim.id)
    claim_path = docx_filler.fill(TEMPLATES_DIR / "claim_ru.docx", out_dir / "claim_ru.docx", ctx, items)
    agreement_path = docx_filler.fill(TEMPLATES_DIR / "agreement_ru.docx", out_dir / "agreement_ru.docx", ctx)

    claim.generated_docx_path = str(claim_path)
    claim.generated_agreement_path = str(agreement_path)
    if claim.status == "draft":
        claim.status = "generated"
    await db.flush()
    await db.refresh(claim)
    return claim


@router.get("/claims/{claim_id}/download/{kind}")
async def download(
    claim_id: int,
    kind: str,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    if kind not in ("claim", "agreement"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "kind must be claim|agreement")
    claim = await db.scalar(
        select(Claim).where(Claim.id == claim_id, Claim.user_id == user_id)
    )
    if claim is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Claim not found")
    path = claim.generated_docx_path if kind == "claim" else claim.generated_agreement_path
    if not path or not Path(path).is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File not generated yet")
    download_name = f"{kind}_{claim.id}.docx"
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=download_name,
    )


VALID_STATUSES = {"draft", "generated", "submitted", "paid", "rejected"}


@router.get("/claims", response_model=list[ClaimOut])
async def list_claims(
    status_filter: str | None = Query(default=None, alias="status"),
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    q = select(Claim).where(Claim.user_id == user_id)
    if status_filter:
        q = q.where(Claim.status == status_filter)
    q = q.order_by(Claim.created_at.desc())
    return (await db.scalars(q)).all()


@router.patch("/claims/{claim_id}", response_model=ClaimOut)
async def patch_claim(
    claim_id: int,
    payload: ClaimPatchIn,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    claim = await db.scalar(
        select(Claim).where(Claim.id == claim_id, Claim.user_id == user_id)
    )
    if claim is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Claim not found")
    if payload.status is not None:
        if payload.status not in VALID_STATUSES:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"status must be one of {sorted(VALID_STATUSES)}",
            )
        claim.status = payload.status
        # Auto-stamp transition timestamps if not supplied
        now = datetime.now(timezone.utc)
        if payload.status == "submitted" and claim.submitted_at is None and payload.submitted_at is None:
            claim.submitted_at = now
        if payload.status == "paid" and claim.paid_at is None and payload.paid_at is None:
            claim.paid_at = now
    if payload.submitted_at is not None:
        claim.submitted_at = payload.submitted_at
    if payload.paid_at is not None:
        claim.paid_at = payload.paid_at
    if payload.paid_amount is not None:
        claim.paid_amount = payload.paid_amount
    if payload.notes is not None:
        claim.notes = payload.notes
    await db.flush()
    await db.refresh(claim)
    return claim


@router.get("/claims/{claim_id}", response_model=ClaimWithItemsOut)
async def get_claim(
    claim_id: int,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    claim = await db.scalar(
        select(Claim).where(Claim.id == claim_id, Claim.user_id == user_id)
    )
    if claim is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Claim not found")
    items = (await db.scalars(
        select(LostItem).where(LostItem.claim_id == claim.id).order_by(LostItem.id)
    )).all()
    out = ClaimWithItemsOut.model_validate(claim, from_attributes=True)
    out.items = items
    return out


def _outstanding_qty(r: LostItem) -> int:
    if r.received_qty is None:
        return r.expected_qty
    return max(r.expected_qty - r.received_qty, 0)


def _fmt_money(v: int | None) -> str:
    if v is None:
        return "0"
    s = f"{v:,}".replace(",", " ")
    return s


def _item_ctx(r: LostItem) -> dict:
    qty = _outstanding_qty(r)
    unit = r.unit_compensation or 0
    return {
        "product_title": r.product_title or "",
        "barcode": r.barcode or "",
        "reason": r.reason or "утеря",
        "expected_qty": qty,
        "received_qty": r.received_qty if r.received_qty is not None else "",
        "unit_compensation": _fmt_money(unit),
        "line_total": _fmt_money(unit * qty),
    }
