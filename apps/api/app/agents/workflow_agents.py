from __future__ import annotations

import asyncio

from app.schemas.investigation import (
    AgentFinding,
    CreditRiskScore,
    Evidence,
    InvestigationRequest,
)
from app.schemas.transaction import TransactionScore
from app.services.policy_knowledge import search_policies


async def aml_agent(
    request: InvestigationRequest,
    score: TransactionScore,
) -> AgentFinding:
    """
    AML specialist evaluating transactional and customer-risk signals.
    """

    if request.transaction is None:
        raise ValueError("AML workflow requires transaction data.")

    tx = request.transaction

    indicators: list[str] = []

    if tx.velocity_1h >= 8:
        indicators.append("High transaction velocity.")

    if abs(tx.amount_zscore) >= 4:
        indicators.append("Extreme behavioral amount deviation.")

    if tx.is_cross_border:
        indicators.append("Cross-border transaction activity.")

    if tx.merchant_risk_score >= 0.7:
        indicators.append("High-risk merchant exposure.")

    if tx.ip_risk_score >= 0.7:
        indicators.append("High-risk network origin.")

    if request.compliance is not None:
        if request.compliance.is_pep:
            indicators.append("Customer has PEP exposure.")

        if request.compliance.sanctions_match:
            indicators.append("Potential sanctions match.")

        if not request.compliance.kyc_verified:
            indicators.append("KYC verification is incomplete.")

    escalated = (
        score.combined_risk_score >= 0.65
        or len(indicators) >= 3
        or (
            request.compliance is not None
            and request.compliance.sanctions_match
        )
    )

    return AgentFinding(
        agent="aml_investigation_agent",
        status="completed",
        conclusion=(
            "AML indicators require enhanced investigation and escalation."
            if escalated
            else "No strong AML escalation pattern was identified."
        ),
        confidence=0.91 if escalated else 0.78,
        evidence=[
            Evidence(
                source="aml_rule_engine",
                category="aml",
                summary=(
                    "AML indicators: "
                    + (
                        " ".join(indicators)
                        if indicators
                        else "No material AML indicators detected."
                    )
                ),
                confidence=0.90,
                reference=str(tx.transaction_id),
            )
        ],
        warnings=[],
    )


async def credit_underwriting_agent(
    request: InvestigationRequest,
    credit_score: CreditRiskScore,
) -> AgentFinding:
    """
    Credit-underwriting specialist consuming the explainable credit engine.
    """

    if request.loan is None:
        raise ValueError("Credit workflow requires loan data.")

    loan = request.loan

    evidence = [
        Evidence(
            source="credit_risk_engine",
            category="credit",
            summary=reason,
            confidence=0.88,
            reference=loan.application_id,
        )
        for reason in credit_score.reasons
    ]

    return AgentFinding(
        agent="credit_underwriting_agent",
        status="completed",
        conclusion=(
            "Application requires manual underwriting review."
            if credit_score.requires_human_review
            else "Application risk is within the automated review range."
        ),
        confidence=0.92,
        evidence=evidence,
        warnings=[],
    )


async def compliance_agent(
    request: InvestigationRequest,
) -> AgentFinding:
    """
    KYC, sanctions, PEP, and customer-governance specialist.
    """

    if request.compliance is None:
        raise ValueError(
            "Compliance workflow requires compliance data."
        )

    compliance = request.compliance
    violations: list[str] = []

    if not compliance.kyc_verified:
        violations.append(
            "Customer KYC verification is incomplete."
        )

    if compliance.is_pep:
        violations.append(
            "Customer requires enhanced PEP due diligence."
        )

    if compliance.sanctions_match:
        violations.append(
            "Potential sanctions match requires immediate escalation."
        )

    if compliance.customer_risk_level in {
        "high",
        "critical",
    }:
        violations.append(
            "Customer profile is classified as high risk."
        )

    escalation_required = bool(violations)

    return AgentFinding(
        agent="compliance_agent",
        status="completed",
        conclusion=(
            "Compliance controls require enhanced review."
            if escalation_required
            else "Customer passes the current compliance screening."
        ),
        confidence=0.97,
        evidence=[
            Evidence(
                source="compliance_screening",
                category="compliance",
                summary=(
                    " ".join(violations)
                    if violations
                    else (
                        "KYC verified; no PEP or sanctions "
                        "flags are present."
                    )
                ),
                confidence=0.97,
                reference=compliance.customer_id,
            )
        ],
        warnings=[],
    )


async def workflow_policy_agent(
    request: InvestigationRequest,
    query: str,
) -> AgentFinding:
    """
    Reusable semantic-policy specialist for AML, credit, and compliance.
    """

    try:
        matches = await asyncio.to_thread(
            search_policies,
            query,
            4,
        )

    except Exception as exc:
        warning = (
            "Qdrant workflow policy retrieval unavailable: "
            f"{type(exc).__name__}"
        )

        return AgentFinding(
            agent="workflow_policy_agent",
            status="completed",
            conclusion=(
                "Semantic policy retrieval was unavailable; "
                "manual governance review is recommended."
            ),
            confidence=0.60,
            evidence=[
                Evidence(
                    source="policy_fallback",
                    category="policy",
                    summary=warning,
                    confidence=0.60,
                )
            ],
            warnings=[warning],
        )

    evidence = [
        Evidence(
            source="qdrant_semantic_policy",
            category="policy",
            summary=(
                f"{match.title}: {match.document} "
                f"Semantic similarity="
                f"{match.similarity_score:.4f}."
            ),
            confidence=min(
                0.99,
                max(0.50, match.similarity_score),
            ),
            reference=match.policy_id,
        )
        for match in matches
    ]

    return AgentFinding(
        agent="workflow_policy_agent",
        status="completed",
        conclusion=(
            f"Retrieved {len(matches)} relevant "
            f"{request.workflow} policy document(s)."
        ),
        confidence=0.93 if matches else 0.70,
        evidence=evidence,
        warnings=[],
    )
