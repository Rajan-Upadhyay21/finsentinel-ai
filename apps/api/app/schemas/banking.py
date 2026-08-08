from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.banking import (
    AccountStatus,
    ApprovalStatus,
    CaseStatus,
    CaseType,
    CustomerRiskLevel,
    LoanStatus,
    TransactionStatus,
)


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ============================================================
# CUSTOMER
# ============================================================


class CustomerCreate(BaseModel):
    external_id: str = Field(min_length=1, max_length=64)
    full_name: str = Field(min_length=1, max_length=255)
    email: EmailStr | None = None
    phone_token: str | None = None
    country_code: str = Field(default="US", min_length=2, max_length=2)
    risk_level: CustomerRiskLevel = CustomerRiskLevel.LOW
    kyc_verified: bool = False
    is_pep: bool = False
    sanctions_match: bool = False


class CustomerRead(ORMModel):
    id: UUID
    external_id: str
    full_name: str
    email: str | None
    phone_token: str | None
    country_code: str
    risk_level: CustomerRiskLevel
    kyc_verified: bool
    is_pep: bool
    sanctions_match: bool
    created_at: datetime
    updated_at: datetime


# ============================================================
# ACCOUNT
# ============================================================


class AccountCreate(BaseModel):
    customer_id: UUID
    account_number_token: str = Field(min_length=1, max_length=128)
    account_type: str = Field(default="checking", max_length=32)
    status: AccountStatus = AccountStatus.ACTIVE
    balance: Decimal = Field(default=Decimal("0.00"), ge=0)
    currency: str = Field(default="USD", min_length=3, max_length=3)


class AccountRead(ORMModel):
    id: UUID
    customer_id: UUID
    account_number_token: str
    account_type: str
    status: AccountStatus
    balance: Decimal
    currency: str
    created_at: datetime
    updated_at: datetime


# ============================================================
# TRANSACTION
# ============================================================


class TransactionCreate(BaseModel):
    external_id: str = Field(min_length=1, max_length=64)
    account_id: UUID
    merchant_id: str | None = None
    amount: Decimal = Field(gt=0)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    transaction_type: str = "card_purchase"
    status: TransactionStatus = TransactionStatus.PENDING
    device_id: str | None = None
    device_known: bool = True
    ip_address_token: str | None = None
    ip_risk_score: Decimal = Field(default=Decimal("0"), ge=0, le=1)
    merchant_risk_score: Decimal = Field(default=Decimal("0"), ge=0, le=1)
    anomaly_score: Decimal = Field(default=Decimal("0"), ge=0, le=1)
    fraud_probability: Decimal = Field(default=Decimal("0"), ge=0, le=1)
    amount_zscore: Decimal = Decimal("0")
    velocity_1h: int = Field(default=0, ge=0)
    occurred_at: datetime | None = None
    metadata_json: dict | None = None


class TransactionRead(ORMModel):
    id: UUID
    external_id: str
    account_id: UUID
    merchant_id: str | None
    amount: Decimal
    currency: str
    transaction_type: str
    status: TransactionStatus
    device_id: str | None
    device_known: bool
    ip_address_token: str | None
    ip_risk_score: Decimal
    merchant_risk_score: Decimal
    anomaly_score: Decimal
    fraud_probability: Decimal
    amount_zscore: Decimal
    velocity_1h: int
    occurred_at: datetime | None
    metadata_json: dict | None
    created_at: datetime
    updated_at: datetime


# ============================================================
# INVESTIGATION CASE
# ============================================================


class InvestigationCaseCreate(BaseModel):
    case_type: CaseType
    subject_id: str = Field(min_length=1, max_length=128)
    status: CaseStatus = CaseStatus.OPEN
    risk_score: Decimal = Field(default=Decimal("0"), ge=0, le=1)
    confidence_score: Decimal = Field(default=Decimal("0"), ge=0, le=1)
    assigned_role: str = "fraud_analyst"
    recommended_action: str | None = None
    summary: str | None = None
    evidence: list | None = None
    agent_findings: dict | None = None


class InvestigationCaseRead(ORMModel):
    id: UUID
    case_type: CaseType
    subject_id: str
    status: CaseStatus
    risk_score: Decimal
    confidence_score: Decimal
    assigned_role: str
    recommended_action: str | None
    summary: str | None
    evidence: list | None
    agent_findings: dict | None
    created_at: datetime
    updated_at: datetime


# ============================================================
# LOAN APPLICATION
# ============================================================


class LoanApplicationCreate(BaseModel):
    external_id: str = Field(min_length=1, max_length=64)
    customer_id: UUID
    requested_amount: Decimal = Field(gt=0)
    annual_income: Decimal = Field(gt=0)
    debt_to_income_ratio: Decimal = Field(default=Decimal("0"), ge=0)
    credit_score: int | None = Field(default=None, ge=300, le=850)
    risk_probability: Decimal = Field(default=Decimal("0"), ge=0, le=1)
    status: LoanStatus = LoanStatus.SUBMITTED
    decision_reason: str | None = None


class LoanApplicationRead(ORMModel):
    id: UUID
    external_id: str
    customer_id: UUID
    requested_amount: Decimal
    annual_income: Decimal
    debt_to_income_ratio: Decimal
    credit_score: int | None
    risk_probability: Decimal
    status: LoanStatus
    decision_reason: str | None
    created_at: datetime
    updated_at: datetime


# ============================================================
# APPROVAL
# ============================================================


class ApprovalCreate(BaseModel):
    case_id: UUID
    requested_role: str
    requested_by_agent: str
    status: ApprovalStatus = ApprovalStatus.PENDING
    reviewer_id: str | None = None
    reviewer_comment: str | None = None
    decided_at: datetime | None = None


class ApprovalRead(ORMModel):
    id: UUID
    case_id: UUID
    requested_role: str
    requested_by_agent: str
    status: ApprovalStatus
    reviewer_id: str | None
    reviewer_comment: str | None
    decided_at: datetime | None
    created_at: datetime
    updated_at: datetime


# ============================================================
# AUDIT LOG
# ============================================================


class AuditLogCreate(BaseModel):
    actor_type: str
    actor_id: str
    action: str
    resource_type: str
    resource_id: str | None = None
    outcome: str = "success"
    trace_id: str | None = None
    details: dict | None = None


class AuditLogRead(ORMModel):
    id: UUID
    actor_type: str
    actor_id: str
    action: str
    resource_type: str
    resource_id: str | None
    outcome: str
    trace_id: str | None
    details: dict | None
    created_at: datetime
    updated_at: datetime