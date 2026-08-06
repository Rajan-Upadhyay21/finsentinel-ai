import asyncio
from collections.abc import Awaitable, Callable

from app.schemas.investigation import (
    AgentFinding,
    Evidence,
    InvestigationDecision,
    InvestigationRequest,
)
from app.schemas.transaction import TransactionScore
from app.services.risk_engine import score_transaction


async def _fraud_agent(request: InvestigationRequest, score: TransactionScore) -> AgentFinding:
    await asyncio.sleep(0)
    evidence = [
        Evidence(
            source="fraud_model",
            category="model",
            summary=f"Combined risk score is {score.combined_risk_score:.2f} ({score.risk_level}).",
            confidence=min(0.97, 0.60 + score.combined_risk_score * 0.35),
            reference=str(request.transaction.transaction_id),
        )
    ]
    evidence.extend(
        Evidence(
            source="risk_engine",
            category="feature",
            summary=factor.explanation,
            confidence=min(0.95, 0.55 + factor.weight * 0.20),
            reference=factor.code,
        )
        for factor in score.risk_factors[:4]
    )
    return AgentFinding(
        agent="fraud_agent",
        status="completed",
        conclusion="Fraud indicators require escalation." if score.requires_human_review else "No strong fraud pattern detected.",
        confidence=min(0.96, 0.58 + score.combined_risk_score * 0.38),
        evidence=evidence,
    )


async def _behavior_agent(request: InvestigationRequest, score: TransactionScore) -> AgentFinding:
    await asyncio.sleep(0)
    z = abs(request.transaction.amount_zscore)
    abnormal = z >= 2.5 or request.transaction.velocity_1h >= 4
    return AgentFinding(
        agent="customer_behavior_agent",
        status="completed",
        conclusion="Behavior deviates from the customer baseline." if abnormal else "Behavior is consistent with the customer baseline.",
        confidence=min(0.94, 0.64 + min(z, 5.0) * 0.05),
        evidence=[
            Evidence(
                source="behavior_profile",
                category="analytics",
                summary=f"Amount z-score={request.transaction.amount_zscore:.2f}; one-hour velocity={request.transaction.velocity_1h}.",
                confidence=0.88,
            )
        ],
    )


async def _graph_agent(request: InvestigationRequest, score: TransactionScore) -> AgentFinding:
    await asyncio.sleep(0)
    # Day-1 deterministic placeholder. Day 4 replaces this with Neo4j queries.
    suspicious = request.transaction.merchant_risk_score >= 0.7 or request.transaction.ip_risk_score >= 0.7
    return AgentFinding(
        agent="graph_investigation_agent",
        status="completed",
        conclusion="Potential risky entity relationship identified." if suspicious else "No risky relationship found in the current local graph signal.",
        confidence=0.76 if suspicious else 0.66,
        evidence=[
            Evidence(
                source="neo4j_adapter",
                category="graph",
                summary="Day-1 graph adapter evaluated merchant and IP relationship signals.",
                confidence=0.72,
                reference=request.transaction.merchant_id,
            )
        ],
        warnings=["Neo4j live relationship queries are enabled in Day 4."],
    )


async def _policy_agent(request: InvestigationRequest, score: TransactionScore) -> AgentFinding:
    await asyncio.sleep(0)
    threshold = 0.65
    breached = score.combined_risk_score >= threshold
    return AgentFinding(
        agent="policy_compliance_agent",
        status="completed",
        conclusion="Manual-review policy threshold is met." if breached else "Manual-review policy threshold is not met.",
        confidence=0.95,
        evidence=[
            Evidence(
                source="policy_engine",
                category="policy",
                summary=f"Policy FRD-001 requires review at combined risk >= {threshold:.2f}.",
                confidence=0.99,
                reference="FRD-001",
            )
        ],
        warnings=["Qdrant semantic policy citations are enabled in Day 4."],
    )


AgentCallable = Callable[[InvestigationRequest, TransactionScore], Awaitable[AgentFinding]]


async def run_investigation(request: InvestigationRequest) -> InvestigationDecision:
    score = score_transaction(request.transaction)

    selected_agents: list[AgentCallable] = [
        _fraud_agent,
        _behavior_agent,
        _graph_agent,
        _policy_agent,
    ]
    findings = list(await asyncio.gather(*(agent(request, score) for agent in selected_agents)))

    contradictions: list[str] = []
    fraud_finding = next(item for item in findings if item.agent == "fraud_agent")
    graph_finding = next(item for item in findings if item.agent == "graph_investigation_agent")
    if score.requires_human_review and "No risky relationship" in graph_finding.conclusion:
        contradictions.append("Model risk is high, but the current graph signal is weak.")
    if not score.requires_human_review and "escalation" in fraud_finding.conclusion:
        contradictions.append("Fraud conclusion conflicts with the configured review threshold.")

    if score.combined_risk_score >= 0.85:
        decision = "block"
    elif score.requires_human_review:
        decision = "manual_review"
    elif score.combined_risk_score >= 0.35:
        decision = "monitor"
    else:
        decision = "approve"

    confidence_values = [finding.confidence for finding in findings]
    final_confidence = sum(confidence_values) / len(confidence_values)
    if contradictions:
        final_confidence *= 0.88

    rationale = (
        f"The orchestrator selected {len(selected_agents)} specialist agents. "
        f"The combined risk score is {score.combined_risk_score:.2f}; "
        f"the governed decision is {decision}."
    )

    return InvestigationDecision(
        case_id=request.case_id,
        workflow=request.workflow,
        transaction_score=score,
        findings=findings,
        contradictions=contradictions,
        decision=decision,
        final_confidence=round(final_confidence, 4),
        rationale=rationale,
    )
