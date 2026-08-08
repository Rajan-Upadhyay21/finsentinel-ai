import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

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


AgentCallable = Callable[
    [InvestigationRequest, TransactionScore],
    Awaitable[AgentFinding],
]


@dataclass(frozen=True)
class AgentSpec:
    name: str
    handler: AgentCallable
    timeout_seconds: float
    confidence_weight: float
    critical: bool = False


@dataclass
class OrchestrationState:
    request: InvestigationRequest
    score: TransactionScore
    selected_agents: list[AgentSpec] = field(default_factory=list)
    findings: list[AgentFinding] = field(default_factory=list)
    contradictions: list[str] = field(default_factory=list)
    decision: str = "approve"
    final_confidence: float = 0.0


def _select_agents(
    request: InvestigationRequest,
    score: TransactionScore,
) -> list[AgentSpec]:
    """
    Route only the specialist agents needed for the current investigation.

    Fraud, behavior and policy evaluation always run. Graph investigation is
    activated when transaction or model signals justify network traversal.
    """

    agents = [
        AgentSpec(
            name="fraud_agent",
            handler=_fraud_agent,
            timeout_seconds=4.0,
            confidence_weight=1.35,
            critical=True,
        ),
        AgentSpec(
            name="customer_behavior_agent",
            handler=_behavior_agent,
            timeout_seconds=4.0,
            confidence_weight=0.85,
        ),
    ]

    graph_required = (
        score.combined_risk_score >= 0.35
        or not request.transaction.device_known
        or request.transaction.merchant_risk_score >= 0.40
        or request.transaction.ip_risk_score >= 0.40
        or request.transaction.velocity_1h >= 4
    )

    if graph_required:
        agents.append(
            AgentSpec(
                name="graph_investigation_agent",
                handler=_graph_agent,
                timeout_seconds=6.0,
                confidence_weight=1.10,
            )
        )

    agents.append(
        AgentSpec(
            name="policy_compliance_agent",
            handler=_policy_agent,
            timeout_seconds=8.0,
            confidence_weight=1.25,
            critical=True,
        )
    )

    return agents


async def _run_agent_safely(
    spec: AgentSpec,
    request: InvestigationRequest,
    score: TransactionScore,
) -> AgentFinding:
    """
    Execute one specialist with timeout and failure isolation.

    A failed external dependency must not crash the entire banking workflow.
    """

    try:
        return await asyncio.wait_for(
            spec.handler(request, score),
            timeout=spec.timeout_seconds,
        )

    except TimeoutError:
        warning = (
            f"{spec.name} exceeded its "
            f"{spec.timeout_seconds:.1f}s execution timeout."
        )

        return AgentFinding(
            agent=spec.name,
            status="completed",
            conclusion=(
                "Specialist execution timed out; the orchestrator "
                "continued in degraded mode."
            ),
            confidence=0.25 if spec.critical else 0.35,
            evidence=[
                Evidence(
                    source="orchestrator_runtime",
                    category="orchestration",
                    summary=warning,
                    confidence=0.30,
                    reference=str(request.transaction.transaction_id),
                )
            ],
            warnings=[warning],
        )

    except Exception as exc:
        warning = (
            f"{spec.name} failed with "
            f"{type(exc).__name__}; workflow isolation prevented "
            "a full investigation failure."
        )

        return AgentFinding(
            agent=spec.name,
            status="completed",
            conclusion=(
                "Specialist execution failed; the orchestrator "
                "continued using available evidence."
            ),
            confidence=0.20 if spec.critical else 0.30,
            evidence=[
                Evidence(
                    source="orchestrator_runtime",
                    category="orchestration",
                    summary=warning,
                    confidence=0.25,
                    reference=str(request.transaction.transaction_id),
                )
            ],
            warnings=[warning],
        )


def _finding(
    findings: list[AgentFinding],
    agent_name: str,
) -> AgentFinding | None:
    return next(
        (
            finding
            for finding in findings
            if finding.agent == agent_name
        ),
        None,
    )


def _detect_contradictions(
    state: OrchestrationState,
) -> list[str]:
    contradictions: list[str] = []

    fraud = _finding(state.findings, "fraud_agent")
    graph = _finding(
        state.findings,
        "graph_investigation_agent",
    )
    policy = _finding(
        state.findings,
        "policy_compliance_agent",
    )

    if (
        state.score.requires_human_review
        and graph is not None
        and "No suspicious multi-entity relationships"
        in graph.conclusion
    ):
        contradictions.append(
            "ML risk is high while Neo4j network evidence is weak."
        )

    if (
        not state.score.requires_human_review
        and fraud is not None
        and "require escalation" in fraud.conclusion
    ):
        contradictions.append(
            "Fraud-agent escalation conflicts with the model review threshold."
        )

    if (
        state.score.requires_human_review
        and policy is not None
        and "do not require escalation" in policy.conclusion
    ):
        contradictions.append(
            "Model risk requires review while policy retrieval suggests no escalation."
        )

    degraded_agents = [
        finding.agent
        for finding in state.findings
        if any(
            evidence.source == "orchestrator_runtime"
            for evidence in finding.evidence
        )
    ]

    if degraded_agents:
        contradictions.append(
            "Specialist degradation detected: "
            + ", ".join(degraded_agents)
            + "."
        )

    return contradictions


def _choose_decision(score: TransactionScore) -> str:
    """
    Preserve the governed decision contract used by the banking persistence
    layer and human approval workflow.
    """

    if score.combined_risk_score >= 0.85:
        return "block"

    if score.requires_human_review:
        return "manual_review"

    if score.combined_risk_score >= 0.35:
        return "monitor"

    return "approve"


def _aggregate_confidence(
    state: OrchestrationState,
) -> float:
    """
    Compute weighted confidence instead of a simple arithmetic mean.

    Fraud and policy specialists receive more weight because they directly
    support the governed transaction decision.
    """

    weights = {
        spec.name: spec.confidence_weight
        for spec in state.selected_agents
    }

    weighted_total = 0.0
    total_weight = 0.0

    for finding in state.findings:
        weight = weights.get(finding.agent, 1.0)
        weighted_total += finding.confidence * weight
        total_weight += weight

    if total_weight == 0:
        return 0.0

    confidence = weighted_total / total_weight

    if state.contradictions:
        confidence *= 0.90

    degraded = any(
        evidence.source == "orchestrator_runtime"
        for finding in state.findings
        for evidence in finding.evidence
    )

    if degraded:
        confidence *= 0.85

    return round(
        min(1.0, max(0.0, confidence)),
        4,
    )


async def run_investigation(
    request: InvestigationRequest,
) -> InvestigationDecision:
    score = score_transaction(request.transaction)

    state = OrchestrationState(
        request=request,
        score=score,
    )

    state.selected_agents = _select_agents(
        request,
        score,
    )

    # Specialist agents execute concurrently. Each execution is individually
    # protected by timeout and failure isolation.
    state.findings = list(
        await asyncio.gather(
            *(
                _run_agent_safely(
                    spec,
                    request,
                    score,
                )
                for spec in state.selected_agents
            )
        )
    )

    state.contradictions = _detect_contradictions(state)
    state.decision = _choose_decision(score)
    state.final_confidence = _aggregate_confidence(state)

    selected_names = [
        spec.name
        for spec in state.selected_agents
    ]

    rationale = (
        f"The orchestrator dynamically routed the investigation to "
        f"{len(selected_names)} specialist agents: "
        f"{', '.join(selected_names)}. "
        f"The ML combined risk score is "
        f"{score.combined_risk_score:.2f} ({score.risk_level}). "
        f"The governed decision is {state.decision}. "
        f"Aggregated specialist confidence is "
        f"{state.final_confidence:.2f}."
    )

    if state.contradictions:
        rationale += (
            " Contradictions requiring additional caution: "
            + " ".join(state.contradictions)
        )

    return InvestigationDecision(
        case_id=request.case_id,
        workflow=request.workflow,
        transaction_score=score,
        findings=state.findings,
        contradictions=state.contradictions,
        decision=state.decision,
        final_confidence=state.final_confidence,
        rationale=rationale,
    )
