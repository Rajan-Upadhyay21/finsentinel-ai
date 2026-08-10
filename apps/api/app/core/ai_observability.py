from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import Any

from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode
from prometheus_client import Counter, Gauge, Histogram


WORKFLOW_EXECUTIONS = Counter(
    "finsentinel_workflow_executions_total",
    "Completed governed banking workflows.",
    ["workflow", "decision"],
)

WORKFLOW_FAILURES = Counter(
    "finsentinel_workflow_failures_total",
    "Banking workflow executions that raised an exception.",
    ["workflow", "exception"],
)

WORKFLOW_DURATION = Histogram(
    "finsentinel_workflow_duration_seconds",
    "End-to-end governed workflow execution latency.",
    ["workflow"],
    buckets=(
        0.01,
        0.025,
        0.05,
        0.1,
        0.25,
        0.5,
        1.0,
        2.5,
        5.0,
        10.0,
        20.0,
        30.0,
    ),
)

WORKFLOW_IN_FLIGHT = Gauge(
    "finsentinel_workflow_in_flight",
    "Currently executing governed workflows.",
    ["workflow"],
)

AGENT_FINDINGS = Counter(
    "finsentinel_agent_findings_total",
    "Specialist-agent findings returned by orchestration.",
    ["workflow", "agent", "status"],
)

AGENT_WARNINGS = Counter(
    "finsentinel_agent_warnings_total",
    "Warnings emitted by specialist agents.",
    ["workflow", "agent"],
)

AGENT_CONFIDENCE = Histogram(
    "finsentinel_agent_confidence",
    "Confidence distribution of specialist-agent findings.",
    ["workflow", "agent"],
    buckets=(
        0.0,
        0.25,
        0.5,
        0.6,
        0.7,
        0.8,
        0.9,
        0.95,
        1.0,
    ),
)

AGENTS_PER_WORKFLOW = Histogram(
    "finsentinel_agents_per_workflow",
    "Number of specialist findings produced per workflow.",
    ["workflow"],
    buckets=(
        1,
        2,
        3,
        4,
        5,
        6,
        8,
        10,
        12,
    ),
)

WORKFLOW_DECISIONS = Counter(
    "finsentinel_workflow_decisions_total",
    "Governed banking decisions.",
    ["workflow", "decision"],
)

HUMAN_REVIEW = Counter(
    "finsentinel_human_review_total",
    "Whether a workflow required human review or escalation.",
    ["workflow", "required"],
)

RISK_LEVELS = Counter(
    "finsentinel_risk_level_total",
    "Observed risk-level classifications.",
    ["workflow", "risk_level"],
)

FRAUD_PROBABILITY = Histogram(
    "finsentinel_fraud_probability",
    "Distribution of fraud model probabilities.",
    ["workflow"],
    buckets=(
        0.0,
        0.1,
        0.2,
        0.3,
        0.4,
        0.5,
        0.6,
        0.7,
        0.8,
        0.9,
        0.95,
        1.0,
    ),
)

ANOMALY_SCORE = Histogram(
    "finsentinel_anomaly_score",
    "Distribution of transaction anomaly scores.",
    ["workflow"],
    buckets=(
        0.0,
        0.1,
        0.2,
        0.3,
        0.4,
        0.5,
        0.6,
        0.7,
        0.8,
        0.9,
        1.0,
    ),
)

COMBINED_RISK_SCORE = Histogram(
    "finsentinel_combined_risk_score",
    "Distribution of combined fraud risk scores.",
    ["workflow"],
    buckets=(
        0.0,
        0.1,
        0.2,
        0.3,
        0.4,
        0.5,
        0.6,
        0.7,
        0.8,
        0.9,
        1.0,
    ),
)

CREDIT_RISK_SCORE = Histogram(
    "finsentinel_credit_risk_score",
    "Distribution of calculated credit-risk values.",
    buckets=(
        0.0,
        0.1,
        0.2,
        0.3,
        0.4,
        0.5,
        0.6,
        0.7,
        0.8,
        0.9,
        1.0,
    ),
)


Runner = Callable[
    [Any],
    Awaitable[Any],
]


def _value(
    value: Any,
) -> str:
    raw = getattr(
        value,
        "value",
        value,
    )

    return str(raw).lower()


def _observe_number(
    histogram: Histogram,
    value: Any,
    **labels: str,
) -> None:
    if value is None:
        return

    try:
        number = float(value)
    except (
        TypeError,
        ValueError,
    ):
        return

    if labels:
        histogram.labels(
            **labels
        ).observe(
            number
        )
    else:
        histogram.observe(
            number
        )


def _transaction_metrics(
    workflow: str,
    decision: Any,
) -> bool:
    score = getattr(
        decision,
        "transaction_score",
        None,
    )

    if score is None:
        return False

    _observe_number(
        FRAUD_PROBABILITY,
        getattr(
            score,
            "fraud_probability",
            None,
        ),
        workflow=workflow,
    )

    _observe_number(
        ANOMALY_SCORE,
        getattr(
            score,
            "anomaly_score",
            None,
        ),
        workflow=workflow,
    )

    _observe_number(
        COMBINED_RISK_SCORE,
        getattr(
            score,
            "combined_risk_score",
            None,
        ),
        workflow=workflow,
    )

    risk_level = getattr(
        score,
        "risk_level",
        None,
    )

    if risk_level is not None:
        RISK_LEVELS.labels(
            workflow=workflow,
            risk_level=_value(
                risk_level
            ),
        ).inc()

    return bool(
        getattr(
            score,
            "requires_human_review",
            False,
        )
    )


def _credit_metrics(
    decision: Any,
) -> bool:
    score = getattr(
        decision,
        "credit_score",
        None,
    )

    if score is None:
        return False

    candidates = (
        "risk_probability",
        "risk_score",
        "default_probability",
        "calculated_risk",
        "combined_risk_score",
    )

    for name in candidates:
        value = getattr(
            score,
            name,
            None,
        )

        if value is not None:
            _observe_number(
                CREDIT_RISK_SCORE,
                value,
            )
            break

    risk_level = getattr(
        score,
        "risk_level",
        None,
    )

    if risk_level is not None:
        RISK_LEVELS.labels(
            workflow="credit",
            risk_level=_value(
                risk_level
            ),
        ).inc()

    return bool(
        getattr(
            score,
            "requires_human_review",
            False,
        )
    )


def record_investigation_result(
    workflow: str,
    decision: Any,
) -> None:
    decision_name = _value(
        getattr(
            decision,
            "decision",
            "unknown",
        )
    )

    WORKFLOW_EXECUTIONS.labels(
        workflow=workflow,
        decision=decision_name,
    ).inc()

    WORKFLOW_DECISIONS.labels(
        workflow=workflow,
        decision=decision_name,
    ).inc()

    findings = list(
        getattr(
            decision,
            "findings",
            [],
        )
        or []
    )

    AGENTS_PER_WORKFLOW.labels(
        workflow=workflow
    ).observe(
        len(findings)
    )

    for finding in findings:
        agent = str(
            getattr(
                finding,
                "agent",
                "unknown_agent",
            )
        )

        status = _value(
            getattr(
                finding,
                "status",
                "unknown",
            )
        )

        AGENT_FINDINGS.labels(
            workflow=workflow,
            agent=agent,
            status=status,
        ).inc()

        _observe_number(
            AGENT_CONFIDENCE,
            getattr(
                finding,
                "confidence",
                None,
            ),
            workflow=workflow,
            agent=agent,
        )

        warnings = (
            getattr(
                finding,
                "warnings",
                [],
            )
            or []
        )

        if warnings:
            AGENT_WARNINGS.labels(
                workflow=workflow,
                agent=agent,
            ).inc(
                len(warnings)
            )

    human_required = (
        _transaction_metrics(
            workflow,
            decision,
        )
        or _credit_metrics(
            decision
        )
        or decision_name
        in {
            "manual_review",
            "escalate",
        }
    )

    HUMAN_REVIEW.labels(
        workflow=workflow,
        required=(
            "true"
            if human_required
            else "false"
        ),
    ).inc()


async def observe_investigation(
    request: Any,
    runner: Runner,
) -> Any:
    workflow = _value(
        getattr(
            request,
            "workflow",
            "unknown",
        )
    )

    tracer = trace.get_tracer(
        "finsentinel.ai"
    )

    started = time.perf_counter()

    WORKFLOW_IN_FLIGHT.labels(
        workflow=workflow
    ).inc()

    with tracer.start_as_current_span(
        "finsentinel.workflow"
    ) as span:
        span.set_attribute(
            "finsentinel.workflow",
            workflow,
        )

        try:
            decision = await runner(
                request
            )

        except Exception as exc:
            WORKFLOW_FAILURES.labels(
                workflow=workflow,
                exception=type(
                    exc
                ).__name__,
            ).inc()

            span.record_exception(
                exc
            )

            span.set_status(
                Status(
                    StatusCode.ERROR,
                    str(exc),
                )
            )

            raise

        else:
            decision_name = _value(
                getattr(
                    decision,
                    "decision",
                    "unknown",
                )
            )

            span.set_attribute(
                "finsentinel.decision",
                decision_name,
            )

            findings = (
                getattr(
                    decision,
                    "findings",
                    [],
                )
                or []
            )

            span.set_attribute(
                "finsentinel.agent_count",
                len(findings),
            )

            record_investigation_result(
                workflow,
                decision,
            )

            return decision

        finally:
            elapsed = (
                time.perf_counter()
                - started
            )

            WORKFLOW_DURATION.labels(
                workflow=workflow
            ).observe(
                elapsed
            )

            WORKFLOW_IN_FLIGHT.labels(
                workflow=workflow
            ).dec()

            span.set_attribute(
                "finsentinel.duration_seconds",
                elapsed,
            )

# ============================================================
# TRUE AGENT EXECUTION OBSERVABILITY
# ============================================================

AGENT_EXECUTION_DURATION = Histogram(
    "finsentinel_agent_execution_duration_seconds",
    "Actual specialist execution latency measured around the "
    "orchestrator's safe execution boundary.",
    ["workflow", "agent"],
    buckets=(
        0.001,
        0.005,
        0.01,
        0.025,
        0.05,
        0.1,
        0.25,
        0.5,
        1.0,
        2.5,
        5.0,
        8.0,
        10.0,
        20.0,
    ),
)

AGENT_EXECUTIONS = Counter(
    "finsentinel_agent_executions_total",
    "Actual specialist execution outcomes.",
    ["workflow", "agent", "outcome"],
)

AGENT_TIMEOUTS = Counter(
    "finsentinel_agent_timeouts_total",
    "Specialist executions isolated by an execution timeout.",
    ["workflow", "agent"],
)

AGENT_FAILURES = Counter(
    "finsentinel_agent_failures_total",
    "Specialist executions isolated after an execution failure.",
    ["workflow", "agent", "exception"],
)


def _agent_identity(
    subject: Any,
) -> str:
    for attribute in (
        "name",
        "agent_name",
        "agent",
        "label",
    ):
        value = getattr(
            subject,
            attribute,
            None,
        )

        if value:
            return str(value)

    for attribute in (
        "callable",
        "runner",
        "handler",
        "function",
        "func",
    ):
        value = getattr(
            subject,
            attribute,
            None,
        )

        name = getattr(
            value,
            "__name__",
            None,
        )

        if name:
            return str(name)

    return type(
        subject
    ).__name__.lower()


def _workflow_from_call(
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> str:
    candidates = [
        *args,
        *kwargs.values(),
    ]

    for candidate in candidates:
        workflow = getattr(
            candidate,
            "workflow",
            None,
        )

        if workflow is not None:
            return _value(
                workflow
            )

    return "unknown"


def _execution_outcome(
    result: Any,
) -> str:
    status = _value(
        getattr(
            result,
            "status",
            "completed",
        )
    )

    warnings = " ".join(
        str(item).lower()
        for item in (
            getattr(
                result,
                "warnings",
                [],
            )
            or []
        )
    )

    combined = (
        f"{status} {warnings}"
    )

    if "timeout" in combined:
        return "timeout"

    if (
        status
        in {
            "failed",
            "failure",
            "error",
        }
        or "exception" in combined
        or "failed" in combined
    ):
        return "failed"

    return "completed"


AgentRunner = Callable[
    ...,
    Awaitable[Any],
]


async def observe_agent_execution(
    subject: Any,
    runner: AgentRunner,
    *args: Any,
    **kwargs: Any,
) -> Any:
    workflow = _workflow_from_call(
        args,
        kwargs,
    )

    agent = _agent_identity(
        subject
    )

    tracer = trace.get_tracer(
        "finsentinel.agents"
    )

    started = time.perf_counter()

    with tracer.start_as_current_span(
        "finsentinel.agent"
    ) as span:
        span.set_attribute(
            "finsentinel.workflow",
            workflow,
        )

        span.set_attribute(
            "finsentinel.agent",
            agent,
        )

        try:
            result = await runner(
                *args,
                **kwargs,
            )

        except Exception as exc:
            elapsed = (
                time.perf_counter()
                - started
            )

            AGENT_EXECUTION_DURATION.labels(
                workflow=workflow,
                agent=agent,
            ).observe(
                elapsed
            )

            AGENT_EXECUTIONS.labels(
                workflow=workflow,
                agent=agent,
                outcome="failed",
            ).inc()

            AGENT_FAILURES.labels(
                workflow=workflow,
                agent=agent,
                exception=type(
                    exc
                ).__name__,
            ).inc()

            span.record_exception(
                exc
            )

            span.set_status(
                Status(
                    StatusCode.ERROR,
                    str(exc),
                )
            )

            raise

        elapsed = (
            time.perf_counter()
            - started
        )

        result_agent = getattr(
            result,
            "agent",
            None,
        )

        if result_agent:
            agent = str(
                result_agent
            )

        outcome = _execution_outcome(
            result
        )

        AGENT_EXECUTION_DURATION.labels(
            workflow=workflow,
            agent=agent,
        ).observe(
            elapsed
        )

        AGENT_EXECUTIONS.labels(
            workflow=workflow,
            agent=agent,
            outcome=outcome,
        ).inc()

        if outcome == "timeout":
            AGENT_TIMEOUTS.labels(
                workflow=workflow,
                agent=agent,
            ).inc()

        elif outcome == "failed":
            AGENT_FAILURES.labels(
                workflow=workflow,
                agent=agent,
                exception="isolated_failure",
            ).inc()

        span.set_attribute(
            "finsentinel.agent",
            agent,
        )

        span.set_attribute(
            "finsentinel.agent.outcome",
            outcome,
        )

        span.set_attribute(
            "finsentinel.agent.duration_seconds",
            elapsed,
        )

        return result
