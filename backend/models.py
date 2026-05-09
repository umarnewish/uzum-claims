"""SQLAlchemy models for the `claims` schema.

Schema is set globally via the Base class in backend.db (DB_SCHEMA setting).
"""
from datetime import date, datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.db import Base


class SellerProfile(Base):
    __tablename__ = "seller_profile"

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    fio: Mapped[str] = mapped_column(Text, nullable=False)
    legal_form: Mapped[str] = mapped_column(Text, nullable=False)
    legal_name: Mapped[str] = mapped_column(Text, nullable=False)
    inn: Mapped[str] = mapped_column(Text, nullable=False)
    bank_account: Mapped[str] = mapped_column(Text, nullable=False)
    mfo: Mapped[str] = mapped_column(Text, nullable=False)
    bank_name: Mapped[str] = mapped_column(Text, nullable=False)
    address: Mapped[str] = mapped_column(Text, nullable=False)
    oked: Mapped[str | None] = mapped_column(Text, nullable=True)
    base_contract_no: Mapped[str | None] = mapped_column(Text, nullable=True)
    base_contract_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class Claim(Base):
    __tablename__ = "claim"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    shop_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    total_amount: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    total_qty: Mapped[int | None] = mapped_column(Integer, nullable=True)
    generated_docx_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    generated_agreement_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    paid_amount: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class LostItem(Base):
    __tablename__ = "lost_item"
    __table_args__ = (
        Index("ix_lost_item_user_claim", "user_id", "claim_id"),
        UniqueConstraint("user_id", "source_ref", "loss_type", name="uq_lost_item_dedup"),
        {"schema": Base.__table_args__["schema"]},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    shop_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    loss_type: Mapped[str] = mapped_column(Text, nullable=False)
    source_ref: Mapped[str] = mapped_column(Text, nullable=False)
    uzum_sku_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    barcode: Mapped[str | None] = mapped_column(Text, nullable=True)
    product_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    expected_qty: Mapped[int] = mapped_column(Integer, nullable=False)
    received_qty: Mapped[int | None] = mapped_column(Integer, nullable=True)
    unit_price: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    unit_compensation: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    claim_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey(f"{Base.__table_args__['schema']}.claim.id", ondelete="SET NULL"),
        nullable=True,
    )
    raw_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class PollState(Base):
    __tablename__ = "poll_state"

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    shop_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    source: Mapped[str] = mapped_column(Text, primary_key=True)
    last_polled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_cursor: Mapped[str | None] = mapped_column(Text, nullable=True)
