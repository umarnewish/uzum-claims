"""Pydantic schemas — request/response shapes."""
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


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
