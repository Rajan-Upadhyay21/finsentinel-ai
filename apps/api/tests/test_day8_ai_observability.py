from __future__ import annotations

import asyncio
from types import SimpleNamespace

from prometheus_client import generate_latest

from app.core.ai_observability import (
    observe_agent_execution,
    observe_investigation,
)


def _decision():
    return SimpleNamespace(
        decision="manual_review",
        transaction_score=SimpleNamespace(
            fraud_probability=0.91,
            anomaly_score=0.84,
            combined_risk_score=0.89,
            risk_level="critical",
            requires_human_review=True,
        ),
        credit_score=None,
        findings=[
            SimpleNamespace(
                agent="fraud_agent",
                status="completed",
                confidence=0.94,
                warnings=[],
            )
        ],
    )


def test_workflow_observation() -> None:
    request = SimpleNamespace(
        workflow="fraud"
    )

    async def runner(_request):
        return _decision()

    result = asyncio.run(
        observe_investigation(
            request,
            runner,
        )
    )

    assert result.decision == "manual_review"

    metrics = generate_latest().decode()

    assert (
        "finsentinel_workflow_duration_seconds"
        in metrics
    )


def test_agent_execution_latency() -> None:
    spec = SimpleNamespace(
        name="fraud_agent"
    )

    request = SimpleNamespace(
        workflow="fraud"
    )

    async def runner(_spec, _request):
        return SimpleNamespace(
            agent="fraud_agent",
            status="completed",
            warnings=[],
        )

    asyncio.run(
        observe_agent_execution(
            spec,
            runner,
            spec,
            request,
        )
    )

    metrics = generate_latest().decode()

    assert (
        "finsentinel_agent_execution_duration_seconds"
        in metrics
    )

    assert (
        "finsentinel_agent_executions_total"
        in metrics
    )


def test_agent_timeout_metric() -> None:
    spec = SimpleNamespace(
        name="policy_agent"
    )

    request = SimpleNamespace(
        workflow="fraud"
    )

    async def runner(_spec, _request):
        return SimpleNamespace(
            agent="policy_agent",
            status="completed",
            warnings=[
                "8.0s execution timeout."
            ],
        )

    asyncio.run(
        observe_agent_execution(
            spec,
            runner,
            spec,
            request,
        )
    )

    metrics = generate_latest().decode()

    assert (
        "finsentinel_agent_timeouts_total"
        in metrics
    )
