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


async def _graph_agent(
    request: InvestigationRequest,
    score: TransactionScore,
) -> AgentFinding:
    from app.services.graph_intelligence import investigate_transaction_graph

    graph = await investigate_transaction_graph(
        str(request.transaction.transaction_id)
    )

    if not graph.available:
        warning = (
            graph.warning
            or "Neo4j graph intelligence is temporarily unavailable."
        )

        return AgentFinding(
            agent="graph_investigation_agent",
            status="completed",
            conclusion=(
                "Graph intelligence was unavailable; the investigation "
                "continued using the remaining specialist agents."
            ),
            confidence=0.50,
            evidence=[
                Evidence(
                    source="neo4j_live",
                    category="graph",
                    summary=warning,
                    confidence=0.50,
                    reference=str(request.transaction.transaction_id),
                )
            ],
            warnings=[warning],
        )

    if not graph.transaction_found:
        warning = (
            graph.warning
            or "Transaction was not present in the Neo4j banking graph."
        )

        return AgentFinding(
            agent="graph_investigation_agent",
            status="completed",
            conclusion=(
                "No graph relationships could be evaluated because the "
                "transaction was not found in Neo4j."
            ),
            confidence=0.55,
            evidence=[
                Evidence(
                    source="neo4j_live",
                    category="graph",
                    summary=warning,
                    confidence=0.55,
                    reference=str(request.transaction.transaction_id),
                )
            ],
            warnings=[warning],
        )

    suspicious = bool(graph.indicators) or graph.graph_risk_score >= 0.20

    summary = (
        f"Neo4j graph risk={graph.graph_risk_score:.2f}; "
        f"shared-device transactions={graph.shared_device_transactions}; "
        f"linked accounts={graph.linked_accounts}; "
        f"linked customers={graph.linked_customers}; "
        f"risky merchant transactions={graph.risky_merchant_transactions}; "
        f"prior high-risk account transactions="
        f"{graph.prior_high_risk_transactions}."
    )

    if graph.indicators:
        summary += " Indicators: " + " ".join(graph.indicators)

    confidence = (
        min(0.95, 0.78 + (graph.graph_risk_score * 0.17))
        if suspicious
        else 0.82
    )

    return AgentFinding(
        agent="graph_investigation_agent",
        status="completed",
        conclusion=(
            "Suspicious network relationships were identified in Neo4j."
            if suspicious
            else "No suspicious multi-entity relationships were identified in Neo4j."
        ),
        confidence=round(confidence, 4),
        evidence=[
            Evidence(
                source="neo4j_live",
                category="graph",
                summary=summary,
                confidence=round(confidence, 4),
                reference=str(request.transaction.transaction_id),
            )
        ],
        warnings=[],
    )


async def _policy_agent(
    request: InvestigationRequest,
    score: TransactionScore,
) -> AgentFinding:
    from app.services.policy_knowledge import search_policies

    threshold = 0.65
    breached = score.combined_risk_score >= threshold

    context_parts = [
        (
            f"Banking fraud investigation with combined risk "
            f"{score.combined_risk_score:.2f} and risk level "
            f"{score.risk_level}."
        ),
        (
            f"Fraud probability is {score.fraud_probability:.2f}; "
            f"anomaly score is {score.anomaly_score:.2f}."
        ),
    ]

    if not request.transaction.device_known:
        context_parts.append(
            "The transaction originated from an unrecognized device."
        )

    if request.transaction.merchant_risk_score >= 0.7:
        context_parts.append(
            "The merchant has elevated historical fraud risk."
        )

    if request.transaction.velocity_1h >= 4:
        context_parts.append(
            "Transaction velocity is unusually elevated."
        )

    if abs(request.transaction.amount_zscore) >= 2.5:
        context_parts.append(
            "The transaction amount is a customer behavioral outlier."
        )

    if request.transaction.is_cross_border:
        context_parts.append(
            "The transaction is cross-border."
        )

    if breached:
        context_parts.append(
            "The transaction requires human fraud review and governed oversight."
        )

    policy_query = " ".join(context_parts)

    try:
        matches = await asyncio.to_thread(
            search_policies,
            policy_query,
            4,
        )
    except Exception as exc:
        warning = (
            "Qdrant policy retrieval unavailable: "
            f"{type(exc).__name__}"
        )

        return AgentFinding(
            agent="policy_compliance_agent",
            status="completed",
            conclusion=(
                "Policy retrieval was unavailable; the configured "
                "manual-review threshold was still enforced."
            ),
            confidence=0.65,
            evidence=[
                Evidence(
                    source="policy_fallback",
                    category="policy",
                    summary=(
                        f"Fallback governance rule requires review at "
                        f"combined risk >= {threshold:.2f}."
                    ),
                    confidence=0.80,
                    reference="FRD-001",
                )
            ],
            warnings=[warning],
        )

    evidence = []

    for match in matches:
        evidence.append(
            Evidence(
                source="qdrant_semantic_policy",
                category="policy",
                summary=(
                    f"{match.title}: {match.document} "
                    f"Semantic similarity={match.similarity_score:.4f}."
                ),
                confidence=min(
                    0.99,
                    max(0.50, match.similarity_score),
                ),
                reference=match.policy_id,
            )
        )

    if not evidence:
        evidence.append(
            Evidence(
                source="policy_fallback",
                category="policy",
                summary=(
                    f"Configured governance threshold requires review "
                    f"at combined risk >= {threshold:.2f}."
                ),
                confidence=0.80,
                reference="FRD-001",
            )
        )

    retrieved_ids = [
        match.policy_id
        for match in matches
    ]

    return AgentFinding(
        agent="policy_compliance_agent",
        status="completed",
        conclusion=(
            "Retrieved policies support escalation to governed human review."
            if breached
            else "Retrieved policies do not require escalation under the current risk level."
        ),
        confidence=0.94 if matches else 0.80,
        evidence=evidence,
        warnings=[],
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
