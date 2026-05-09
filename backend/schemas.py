"""Pydantic schemas — request/response shapes."""
from datetime import date, datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


# ───── seller profile ─────

class SellerProfileBase(BaseModel):
    fio: str = Field(min_length=1, description="ФИО владельца / директора")
    legal_form: str = Field(min_length=1, description='Юр. форма, напр. "ООО"')
    legal_name: str = Field(min_length=1, description="Название юр. лица")
    inn: str = Field(min_length=1)
    bank_account: str = Field(min_length=1)
    mfo: str = Field(min_length=1)
    bank_name: str = Field(min_length=1)
    address: str = Field(min_length=1)
    oked: Optional[str] = None
    base_contract_no: Optional[str] = None
    base_contract_date: Optional[date] = None


class SellerProfileIn(SellerProfileBase):
    """Payload for PUT /profile (full upsert)."""


class SellerProfileOut(SellerProfileBase):
    user_id: int
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


# ───── lost items ─────

class LossOut(BaseModel):
    id: int
    shop_id: int
    loss_type: str
    source_ref: str
    uzum_sku_id: Optional[int]
    barcode: Optional[str]
    product_title: Optional[str]
    expected_qty: int
    received_qty: Optional[int]
    unit_price: Optional[int]
    unit_compensation: Optional[int]
    reason: Optional[str]
    detected_at: datetime
    confirmed_at: Optional[datetime]
    claim_id: Optional[int]
    model_config = ConfigDict(from_attributes=True)


class ConfirmReceiptIn(BaseModel):
    received_qty: int = Field(ge=0)


class RefreshSummary(BaseModel):
    shops: int
    return_uzum_short: int = 0
    fbo_supply_reject: int = 0
    order_lost_delivery: int = 0
    errors: list[str] = []
