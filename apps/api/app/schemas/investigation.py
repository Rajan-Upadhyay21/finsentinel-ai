from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from app.schemas.transaction import TransactionFeatures, TransactionScore


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


class InvestigationRequest(BaseModel):
    case_id: UUID = Field(default_factory=uuid4)
    workflow: Literal["fraud", "aml", "credit"] = "fraud"
    transaction: TransactionFeatures


class InvestigationDecision(BaseModel):
    case_id: UUID
    workflow: str
    transaction_score: TransactionScore
    findings: list[AgentFinding]
    contradictions: list[str]
    decision: Literal["approve", "monitor", "manual_review", "block"]
    final_confidence: float = Field(ge=0.0, le=1.0)
    rationale: str
    audit_id: UUID = Field(default_factory=uuid4)
