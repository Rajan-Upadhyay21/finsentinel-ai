from decimal import Decimal
from enum import StrEnum

from sqlalchemy import Boolean, Enum, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDTimestampMixin


class CaseStatus(StrEnum):
    OPEN = "open"
    INVESTIGATING = "investigating"
    PENDING_APPROVAL = "pending_approval"
    CLOSED = "closed"


class Customer(UUIDTimestampMixin, Base):
    __tablename__ = "customers"

    external_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(255))
    country_code: Mapped[str] = mapped_column(String(2), default="US")
    is_pep: Mapped[bool] = mapped_column(Boolean, default=False)

    accounts: Mapped[list["Account"]] = relationship(back_populates="customer")


class Account(UUIDTimestampMixin, Base):
    __tablename__ = "accounts"

    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"), index=True)
    account_number_token: Mapped[str] = mapped_column(String(128), unique=True)
    account_type: Mapped[str] = mapped_column(String(32), default="checking")
    balance: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)

    customer: Mapped[Customer] = relationship(back_populates="accounts")


class InvestigationCase(UUIDTimestampMixin, Base):
    __tablename__ = "investigation_cases"

    case_type: Mapped[str] = mapped_column(String(32), index=True)
    subject_id: Mapped[str] = mapped_column(String(128), index=True)
    status: Mapped[CaseStatus] = mapped_column(Enum(CaseStatus), default=CaseStatus.OPEN)
    risk_score: Mapped[Decimal] = mapped_column(Numeric(5, 4), default=0)
    assigned_role: Mapped[str] = mapped_column(String(64), default="fraud_analyst")
