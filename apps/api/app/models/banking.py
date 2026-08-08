from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDTimestampMixin


# ============================================================
# ENUMS
# ============================================================


class CustomerRiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AccountStatus(StrEnum):
    ACTIVE = "active"
    FROZEN = "frozen"
    CLOSED = "closed"
    REVIEW = "review"


class TransactionStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    BLOCKED = "blocked"
    REVIEW = "review"


class CaseStatus(StrEnum):
    OPEN = "open"
    INVESTIGATING = "investigating"
    PENDING_APPROVAL = "pending_approval"
    ESCALATED = "escalated"
    RESOLVED = "resolved"
    CLOSED = "closed"


class CaseType(StrEnum):
    FRAUD = "fraud"
    AML = "aml"
    CREDIT = "credit"
    COMPLIANCE = "compliance"


class LoanStatus(StrEnum):
    SUBMITTED = "submitted"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    DECLINED = "declined"
    MANUAL_REVIEW = "manual_review"


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


# ============================================================
# CUSTOMER
# ============================================================


class Customer(UUIDTimestampMixin, Base):
    __tablename__ = "customers"

    external_id: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        index=True,
        nullable=False,
    )

    full_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    email: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    phone_token: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )

    country_code: Mapped[str] = mapped_column(
        String(2),
        default="US",
        nullable=False,
    )

    risk_level: Mapped[CustomerRiskLevel] = mapped_column(
        Enum(CustomerRiskLevel),
        default=CustomerRiskLevel.LOW,
        nullable=False,
    )

    kyc_verified: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    is_pep: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    sanctions_match: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    accounts: Mapped[list["Account"]] = relationship(
        back_populates="customer",
        cascade="all, delete-orphan",
    )

    loans: Mapped[list["LoanApplication"]] = relationship(
        back_populates="customer",
        cascade="all, delete-orphan",
    )


# ============================================================
# ACCOUNT
# ============================================================


class Account(UUIDTimestampMixin, Base):
    __tablename__ = "accounts"

    customer_id: Mapped[UUID] = mapped_column(
        ForeignKey("customers.id"),
        index=True,
        nullable=False,
    )

    account_number_token: Mapped[str] = mapped_column(
        String(128),
        unique=True,
        index=True,
        nullable=False,
    )

    account_type: Mapped[str] = mapped_column(
        String(32),
        default="checking",
        nullable=False,
    )

    status: Mapped[AccountStatus] = mapped_column(
        Enum(AccountStatus),
        default=AccountStatus.ACTIVE,
        nullable=False,
    )

    balance: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        default=0,
        nullable=False,
    )

    currency: Mapped[str] = mapped_column(
        String(3),
        default="USD",
        nullable=False,
    )

    customer: Mapped["Customer"] = relationship(
        back_populates="accounts"
    )

    transactions: Mapped[list["Transaction"]] = relationship(
        back_populates="account",
        cascade="all, delete-orphan",
    )


# ============================================================
# TRANSACTION
# ============================================================


class Transaction(UUIDTimestampMixin, Base):
    __tablename__ = "transactions"

    external_id: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        index=True,
        nullable=False,
    )

    account_id: Mapped[UUID] = mapped_column(
        ForeignKey("accounts.id"),
        index=True,
        nullable=False,
    )

    merchant_id: Mapped[str | None] = mapped_column(
        String(128),
        index=True,
        nullable=True,
    )

    amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        nullable=False,
    )

    currency: Mapped[str] = mapped_column(
        String(3),
        default="USD",
        nullable=False,
    )

    transaction_type: Mapped[str] = mapped_column(
        String(64),
        default="card_purchase",
        nullable=False,
    )

    status: Mapped[TransactionStatus] = mapped_column(
        Enum(TransactionStatus),
        default=TransactionStatus.PENDING,
        nullable=False,
    )

    device_id: Mapped[str | None] = mapped_column(
        String(128),
        index=True,
        nullable=True,
    )

    device_known: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    ip_address_token: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )

    ip_risk_score: Mapped[Decimal] = mapped_column(
        Numeric(5, 4),
        default=0,
        nullable=False,
    )

    merchant_risk_score: Mapped[Decimal] = mapped_column(
        Numeric(5, 4),
        default=0,
        nullable=False,
    )

    anomaly_score: Mapped[Decimal] = mapped_column(
        Numeric(5, 4),
        default=0,
        nullable=False,
    )

    fraud_probability: Mapped[Decimal] = mapped_column(
        Numeric(5, 4),
        default=0,
        nullable=False,
    )

    amount_zscore: Mapped[Decimal] = mapped_column(
        Numeric(8, 4),
        default=0,
        nullable=False,
    )

    velocity_1h: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    occurred_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    metadata_json: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
    )

    account: Mapped["Account"] = relationship(
        back_populates="transactions"
    )


# ============================================================
# INVESTIGATION CASE
# ============================================================


class InvestigationCase(UUIDTimestampMixin, Base):
    __tablename__ = "investigation_cases"

    case_type: Mapped[CaseType] = mapped_column(
        Enum(CaseType),
        index=True,
        nullable=False,
    )

    subject_id: Mapped[str] = mapped_column(
        String(128),
        index=True,
        nullable=False,
    )

    status: Mapped[CaseStatus] = mapped_column(
        Enum(CaseStatus),
        default=CaseStatus.OPEN,
        nullable=False,
    )

    risk_score: Mapped[Decimal] = mapped_column(
        Numeric(5, 4),
        default=0,
        nullable=False,
    )

    confidence_score: Mapped[Decimal] = mapped_column(
        Numeric(5, 4),
        default=0,
        nullable=False,
    )

    assigned_role: Mapped[str] = mapped_column(
        String(64),
        default="fraud_analyst",
        nullable=False,
    )

    recommended_action: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )

    summary: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    evidence: Mapped[list | None] = mapped_column(
        JSON,
        nullable=True,
    )

    agent_findings: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
    )


# ============================================================
# LOAN APPLICATION
# ============================================================


class LoanApplication(UUIDTimestampMixin, Base):
    __tablename__ = "loan_applications"

    external_id: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        index=True,
        nullable=False,
    )

    customer_id: Mapped[UUID] = mapped_column(
        ForeignKey("customers.id"),
        index=True,
        nullable=False,
    )

    requested_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        nullable=False,
    )

    annual_income: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        nullable=False,
    )

    debt_to_income_ratio: Mapped[Decimal] = mapped_column(
        Numeric(6, 4),
        default=0,
        nullable=False,
    )

    credit_score: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    risk_probability: Mapped[Decimal] = mapped_column(
        Numeric(5, 4),
        default=0,
        nullable=False,
    )

    status: Mapped[LoanStatus] = mapped_column(
        Enum(LoanStatus),
        default=LoanStatus.SUBMITTED,
        nullable=False,
    )

    decision_reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    customer: Mapped["Customer"] = relationship(
        back_populates="loans"
    )


# ============================================================
# HUMAN APPROVAL
# ============================================================


class Approval(UUIDTimestampMixin, Base):
    __tablename__ = "approvals"

    case_id: Mapped[UUID] = mapped_column(
        ForeignKey("investigation_cases.id"),
        index=True,
        nullable=False,
    )

    requested_role: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    requested_by_agent: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
    )

    status: Mapped[ApprovalStatus] = mapped_column(
        Enum(ApprovalStatus),
        default=ApprovalStatus.PENDING,
        nullable=False,
    )

    reviewer_id: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )

    reviewer_comment: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


# ============================================================
# AUDIT LOG
# ============================================================


class AuditLog(UUIDTimestampMixin, Base):
    __tablename__ = "audit_logs"

    actor_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )

    actor_id: Mapped[str] = mapped_column(
        String(128),
        index=True,
        nullable=False,
    )

    action: Mapped[str] = mapped_column(
        String(128),
        index=True,
        nullable=False,
    )

    resource_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    resource_id: Mapped[str | None] = mapped_column(
        String(128),
        index=True,
        nullable=True,
    )

    outcome: Mapped[str] = mapped_column(
        String(32),
        default="success",
        nullable=False,
    )

    trace_id: Mapped[str | None] = mapped_column(
        String(128),
        index=True,
        nullable=True,
    )

    details: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
    )