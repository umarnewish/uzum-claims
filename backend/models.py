"""SQLAlchemy models for the `claims` schema.

Schema is set globally via the Base class in backend.db (DB_SCHEMA setting).
"""
from datetime import date, datetime

from sqlalchemy import BigInteger, Date, DateTime, String, Text, func
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
