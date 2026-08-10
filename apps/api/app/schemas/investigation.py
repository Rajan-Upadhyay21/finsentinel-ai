from __future__ import annotations

from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, model_validator

from app.schemas.transaction import TransactionFeatures, TransactionScore

WorkflowType = Literal[
    "fraud",
    "aml",
    "credit",
    "compliance",
]


class Evidence(BaseModel):
    source: str
    category: str
    summary: str
    confidence: float = Field(ge=0.0, le=1.0)
    reference: str | None = None


class AgentFinding(BaseModel):
    agent: str
    status: Literal["completed", "skipped", "failed"]
    conclusion: str
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: list[Evidence] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class LoanFeatures(BaseModel):
    """
    Credit-underwriting inputs used by the governed credit workflow.
    """

    application_id: str = Field(min_length=1, max_length=128)
    customer_id: str = Field(min_length=1, max_length=128)

    requested_amount: float = Field(gt=0)
    annual_income: float = Field(gt=0)

    debt_to_income_ratio: float = Field(
        ge=0.0,
        le=5.0,
    )

    credit_score: int | None = Field(
        default=None,
        ge=300,
        le=850,
    )

    existing_risk_probability: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
    )


class ComplianceFeatures(BaseModel):
    """
    Customer-level KYC / sanctions / governance context.

    This can enrich AML investigations and is required by the dedicated
    compliance workflow.
    """

    customer_id: str = Field(min_length=1, max_length=128)

    country_code: str = Field(
        default="US",
        min_length=2,
        max_length=2,
    )

    customer_risk_level: Literal[
        "low",
        "medium",
        "high",
        "critical",
    ] = "low"

    kyc_verified: bool = False
    is_pep: bool = False
    sanctions_match: bool = False


class CreditRiskScore(BaseModel):
    application_id: str

    risk_probability: float = Field(
        ge=0.0,
        le=1.0,
    )

    risk_level: Literal[
        "low",
        "medium",
        "high",
        "critical",
    ]

    requires_human_review: bool

    reasons: list[str] = Field(
        default_factory=list,
    )


class InvestigationRequest(BaseModel):
    case_id: UUID = Field(default_factory=uuid4)

    workflow: WorkflowType = "fraud"

    # Fraud and AML workflows.
    transaction: TransactionFeatures | None = None

    # Credit workflow.
    loan: LoanFeatures | None = None

    # Compliance workflow, and optional AML enrichment.
    compliance: ComplianceFeatures | None = None

    @model_validator(mode="after")
    def validate_workflow_payload(
        self,
    ) -> "InvestigationRequest":
        if (
            self.workflow in {"fraud", "aml"}
            and self.transaction is None
        ):
            raise ValueError(
                f"{self.workflow} workflow requires transaction data."
            )

        if (
            self.workflow == "credit"
            and self.loan is None
        ):
            raise ValueError(
                "credit workflow requires loan data."
            )

        if (
            self.workflow == "compliance"
            and self.compliance is None
        ):
            raise ValueError(
                "compliance workflow requires compliance data."
            )

        return self


class InvestigationDecision(BaseModel):
    case_id: UUID
    workflow: str

    # Fraud / AML workflows continue using the existing transaction score.
    transaction_score: TransactionScore | None = None

    # Credit workflow receives a dedicated underwriting risk result.
    credit_score: CreditRiskScore | None = None

    findings: list[AgentFinding]
    contradictions: list[str]

    decision: Literal[
        "approve",
        "monitor",
        "manual_review",
        "block",
        "decline",
        "escalate",
    ]

    final_confidence: float = Field(
        ge=0.0,
        le=1.0,
    )

    rationale: str

    audit_id: UUID = Field(
        default_factory=uuid4,
    )
