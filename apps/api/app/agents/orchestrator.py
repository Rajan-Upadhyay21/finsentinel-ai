import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from app.agents.workflow_agents import (
    aml_agent,
    compliance_agent,
    credit_underwriting_agent,
    workflow_policy_agent,
)
from app.core.ai_observability import observe_agent_execution, observe_investigation
from app.schemas.investigation import (
    AgentFinding,
    Evidence,
    InvestigationDecision,
    InvestigationRequest,
)
from app.schemas.transaction import TransactionScore
from app.services.credit_engine import score_credit_application
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


async def _run_agent_safely_unobserved(
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

async def _run_agent_safely(
    *args,
    **kwargs,
):
    subject = (
        args[0]
        if args
        else kwargs.get("spec")
    )

    return await observe_agent_execution(
        subject,
        _run_agent_safely_unobserved,
        *args,
        **kwargs,
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


@dataclass(frozen=True)
class WorkflowTask:
    name: str
    factory: Callable[[], Awaitable[AgentFinding]]
    timeout_seconds: float
    confidence_weight: float = 1.0
    critical: bool = False


async def _run_workflow_task_safely_unobserved(
    task: WorkflowTask,
    request: InvestigationRequest,
) -> AgentFinding:
    """
    Run a Day 6 workflow specialist with timeout and failure isolation.
    """

    try:
        return await asyncio.wait_for(
            task.factory(),
            timeout=task.timeout_seconds,
        )

    except TimeoutError:
        warning = (
            f"{task.name} exceeded its "
            f"{task.timeout_seconds:.1f}s execution timeout."
        )

        return AgentFinding(
            agent=task.name,
            status="completed",
            conclusion=(
                "Specialist execution timed out; the governed "
                "workflow continued in degraded mode."
            ),
            confidence=0.20 if task.critical else 0.30,
            evidence=[
                Evidence(
                    source="orchestrator_runtime",
                    category="orchestration",
                    summary=warning,
                    confidence=0.30,
                    reference=str(request.case_id),
                )
            ],
            warnings=[warning],
        )

    except Exception as exc:
        warning = (
            f"{task.name} failed with {type(exc).__name__}; "
            "workflow isolation prevented a full investigation failure."
        )

        return AgentFinding(
            agent=task.name,
            status="completed",
            conclusion=(
                "Specialist execution failed; the governed "
                "workflow continued using available evidence."
            ),
            confidence=0.20 if task.critical else 0.30,
            evidence=[
                Evidence(
                    source="orchestrator_runtime",
                    category="orchestration",
                    summary=warning,
                    confidence=0.25,
                    reference=str(request.case_id),
                )
            ],
            warnings=[warning],
        )

async def _run_workflow_task_safely(
    *args,
    **kwargs,
):
    subject = (
        args[0]
        if args
        else kwargs.get("task")
    )

    return await observe_agent_execution(
        subject,
        _run_workflow_task_safely_unobserved,
        *args,
        **kwargs,
    )


def _workflow_confidence(
    findings: list[AgentFinding],
    tasks: list[WorkflowTask],
) -> float:
    weights = {
        task.name: task.confidence_weight
        for task in tasks
    }

    weighted_total = 0.0
    total_weight = 0.0

    for finding in findings:
        weight = weights.get(
            finding.agent,
            1.0,
        )

        weighted_total += (
            finding.confidence * weight
        )
        total_weight += weight

    if total_weight == 0:
        return 0.0

    confidence = (
        weighted_total / total_weight
    )

    degraded = any(
        evidence.source == "orchestrator_runtime"
        for finding in findings
        for evidence in finding.evidence
    )

    if degraded:
        confidence *= 0.85

    return round(
        min(
            1.0,
            max(0.0, confidence),
        ),
        4,
    )


async def _run_fraud_workflow(
    request: InvestigationRequest,
) -> InvestigationDecision:
    if request.transaction is None:
        raise ValueError(
            "Fraud workflow requires transaction data."
        )

    score = score_transaction(
        request.transaction
    )

    state = OrchestrationState(
        request=request,
        score=score,
    )

    state.selected_agents = _select_agents(
        request,
        score,
    )

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

    state.contradictions = (
        _detect_contradictions(state)
    )

    state.decision = (
        _choose_decision(score)
    )

    state.final_confidence = (
        _aggregate_confidence(state)
    )

    selected_names = [
        spec.name
        for spec in state.selected_agents
    ]

    rationale = (
        "Fraud workflow dynamically routed to "
        f"{len(selected_names)} specialist agents: "
        f"{', '.join(selected_names)}. "
        f"ML combined risk="
        f"{score.combined_risk_score:.2f} "
        f"({score.risk_level}). "
        f"Governed decision={state.decision}. "
        f"Confidence={state.final_confidence:.2f}."
    )

    if state.contradictions:
        rationale += (
            " Contradictions: "
            + " ".join(
                state.contradictions
            )
        )

    return InvestigationDecision(
        case_id=request.case_id,
        workflow="fraud",
        transaction_score=score,
        findings=state.findings,
        contradictions=state.contradictions,
        decision=state.decision,
        final_confidence=(
            state.final_confidence
        ),
        rationale=rationale,
    )


async def _run_aml_workflow(
    request: InvestigationRequest,
) -> InvestigationDecision:
    if request.transaction is None:
        raise ValueError(
            "AML workflow requires transaction data."
        )

    score = score_transaction(
        request.transaction
    )

    tasks: list[WorkflowTask] = [
        WorkflowTask(
            name="fraud_agent",
            factory=lambda: _fraud_agent(
                request,
                score,
            ),
            timeout_seconds=4.0,
            confidence_weight=1.0,
        ),
        WorkflowTask(
            name="customer_behavior_agent",
            factory=lambda: _behavior_agent(
                request,
                score,
            ),
            timeout_seconds=4.0,
            confidence_weight=0.8,
        ),
        WorkflowTask(
            name="graph_investigation_agent",
            factory=lambda: _graph_agent(
                request,
                score,
            ),
            timeout_seconds=6.0,
            confidence_weight=1.2,
        ),
        WorkflowTask(
            name="aml_investigation_agent",
            factory=lambda: aml_agent(
                request,
                score,
            ),
            timeout_seconds=5.0,
            confidence_weight=1.4,
            critical=True,
        ),
    ]

    if request.compliance is not None:
        tasks.append(
            WorkflowTask(
                name="compliance_agent",
                factory=lambda: compliance_agent(
                    request
                ),
                timeout_seconds=4.0,
                confidence_weight=1.3,
                critical=True,
            )
        )

    policy_query = (
        "AML suspicious activity investigation involving "
        f"transaction risk {score.combined_risk_score:.2f}, "
        f"fraud probability {score.fraud_probability:.2f}, "
        f"anomaly score {score.anomaly_score:.2f}, "
        f"velocity {request.transaction.velocity_1h}, "
        f"merchant risk "
        f"{request.transaction.merchant_risk_score:.2f}, "
        f"cross-border="
        f"{request.transaction.is_cross_border}. "
        "Retrieve suspicious activity, network risk, "
        "human review, and AML escalation policies."
    )

    tasks.append(
        WorkflowTask(
            name="workflow_policy_agent",
            factory=lambda: workflow_policy_agent(
                request,
                policy_query,
            ),
            timeout_seconds=8.0,
            confidence_weight=1.2,
            critical=True,
        )
    )

    findings = list(
        await asyncio.gather(
            *(
                _run_workflow_task_safely(
                    task,
                    request,
                )
                for task in tasks
            )
        )
    )

    aml_finding = next(
        (
            finding
            for finding in findings
            if finding.agent
            == "aml_investigation_agent"
        ),
        None,
    )

    compliance_finding = next(
        (
            finding
            for finding in findings
            if finding.agent
            == "compliance_agent"
        ),
        None,
    )

    sanctions_escalation = (
        request.compliance is not None
        and request.compliance.sanctions_match
    )

    aml_escalation = (
        aml_finding is not None
        and "require" in (
            aml_finding.conclusion.lower()
        )
    )

    if sanctions_escalation:
        decision = "escalate"
    elif (
        score.combined_risk_score >= 0.65
        or aml_escalation
    ):
        decision = "manual_review"
    elif score.combined_risk_score >= 0.35:
        decision = "monitor"
    else:
        decision = "approve"

    contradictions: list[str] = []

    if (
        compliance_finding is not None
        and "passes" in (
            compliance_finding.conclusion.lower()
        )
        and aml_escalation
    ):
        contradictions.append(
            "Customer compliance screening is clear "
            "while transaction-level AML signals require escalation."
        )

    confidence = _workflow_confidence(
        findings,
        tasks,
    )

    if contradictions:
        confidence = round(
            confidence * 0.90,
            4,
        )

    return InvestigationDecision(
        case_id=request.case_id,
        workflow="aml",
        transaction_score=score,
        findings=findings,
        contradictions=contradictions,
        decision=decision,
        final_confidence=confidence,
        rationale=(
            f"AML workflow executed {len(tasks)} specialist "
            f"tasks in parallel. Transaction risk="
            f"{score.combined_risk_score:.2f}; "
            f"governed decision={decision}; "
            f"confidence={confidence:.2f}."
        ),
    )


async def _run_credit_workflow(
    request: InvestigationRequest,
) -> InvestigationDecision:
    if request.loan is None:
        raise ValueError(
            "Credit workflow requires loan data."
        )

    credit_score = (
        score_credit_application(
            request.loan
        )
    )

    policy_query = (
        "Credit underwriting decision involving "
        f"risk level {credit_score.risk_level}, "
        f"risk probability "
        f"{credit_score.risk_probability:.2f}, "
        f"debt-to-income ratio "
        f"{request.loan.debt_to_income_ratio:.2f}, "
        f"credit score "
        f"{request.loan.credit_score}, "
        "human underwriting review, adverse decision "
        "governance, and model oversight."
    )

    tasks = [
        WorkflowTask(
            name="credit_underwriting_agent",
            factory=lambda: (
                credit_underwriting_agent(
                    request,
                    credit_score,
                )
            ),
            timeout_seconds=5.0,
            confidence_weight=1.5,
            critical=True,
        ),
        WorkflowTask(
            name="workflow_policy_agent",
            factory=lambda: workflow_policy_agent(
                request,
                policy_query,
            ),
            timeout_seconds=8.0,
            confidence_weight=1.2,
            critical=True,
        ),
    ]

    findings = list(
        await asyncio.gather(
            *(
                _run_workflow_task_safely(
                    task,
                    request,
                )
                for task in tasks
            )
        )
    )

    # High-risk credit outcomes require human oversight rather
    # than an automatically generated adverse lending decision.
    if credit_score.requires_human_review:
        decision = "manual_review"
    elif credit_score.risk_level == "medium":
        decision = "monitor"
    else:
        decision = "approve"

    confidence = _workflow_confidence(
        findings,
        tasks,
    )

    return InvestigationDecision(
        case_id=request.case_id,
        workflow="credit",
        credit_score=credit_score,
        findings=findings,
        contradictions=[],
        decision=decision,
        final_confidence=confidence,
        rationale=(
            "Credit workflow combined explainable "
            "underwriting risk with semantic policy evidence. "
            f"Credit risk="
            f"{credit_score.risk_probability:.2f} "
            f"({credit_score.risk_level}); "
            f"governed decision={decision}; "
            f"confidence={confidence:.2f}."
        ),
    )


async def _run_compliance_workflow(
    request: InvestigationRequest,
) -> InvestigationDecision:
    if request.compliance is None:
        raise ValueError(
            "Compliance workflow requires compliance data."
        )

    compliance = request.compliance

    policy_query = (
        "Customer compliance review involving "
        f"KYC verified={compliance.kyc_verified}, "
        f"PEP={compliance.is_pep}, "
        f"sanctions match={compliance.sanctions_match}, "
        f"customer risk="
        f"{compliance.customer_risk_level}. "
        "Retrieve KYC, sanctions, enhanced due diligence, "
        "human review, and governance policies."
    )

    tasks = [
        WorkflowTask(
            name="compliance_agent",
            factory=lambda: compliance_agent(
                request
            ),
            timeout_seconds=4.0,
            confidence_weight=1.5,
            critical=True,
        ),
        WorkflowTask(
            name="workflow_policy_agent",
            factory=lambda: workflow_policy_agent(
                request,
                policy_query,
            ),
            timeout_seconds=8.0,
            confidence_weight=1.2,
            critical=True,
        ),
    ]

    findings = list(
        await asyncio.gather(
            *(
                _run_workflow_task_safely(
                    task,
                    request,
                )
                for task in tasks
            )
        )
    )

    if compliance.sanctions_match:
        decision = "escalate"
    elif (
        not compliance.kyc_verified
        or compliance.is_pep
        or compliance.customer_risk_level
        in {"high", "critical"}
    ):
        decision = "manual_review"
    else:
        decision = "approve"

    confidence = _workflow_confidence(
        findings,
        tasks,
    )

    return InvestigationDecision(
        case_id=request.case_id,
        workflow="compliance",
        findings=findings,
        contradictions=[],
        decision=decision,
        final_confidence=confidence,
        rationale=(
            "Compliance workflow combined KYC, PEP, "
            "sanctions, customer-risk, and semantic "
            "policy evidence. "
            f"Governed decision={decision}; "
            f"confidence={confidence:.2f}."
        ),
    )


async def _run_investigation_unobserved(
    request: InvestigationRequest,
) -> InvestigationDecision:
    """
    Day 6 governed banking workflow router.
    """

    if request.workflow == "fraud":
        return await _run_fraud_workflow(
            request
        )

    if request.workflow == "aml":
        return await _run_aml_workflow(
            request
        )

    if request.workflow == "credit":
        return await _run_credit_workflow(
            request
        )

    if request.workflow == "compliance":
        return await _run_compliance_workflow(
            request
        )

    raise ValueError(
        f"Unsupported workflow: {request.workflow}"
    )

async def run_investigation(
    request: InvestigationRequest,
) -> InvestigationDecision:
    return await observe_investigation(
        request,
        _run_investigation_unobserved,
    )
