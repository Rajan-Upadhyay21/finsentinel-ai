from __future__ import annotations

import asyncio
from decimal import Decimal

import pytest

from app.agents.orchestrator import AgentSpec, _run_agent_safely
from app.schemas.investigation import InvestigationRequest
from app.schemas.transaction import (
    TransactionFeatures,
    TransactionScore,
)


def build_request() -> InvestigationRequest:
    return InvestigationRequest(
        workflow="fraud",
        transaction=TransactionFeatures(
            customer_id="CUST-FAILURE-TEST",
            account_id="ACCT-FAILURE-TEST",
            merchant_id="MERCHANT-FAILURE-TEST",
            amount=Decimal("5000.00"),
            currency="USD",
            country_code="US",
            device_known=False,
            ip_risk_score=0.80,
            merchant_risk_score=0.80,
            amount_zscore=4.0,
            velocity_1h=8,
        ),
    )


def build_score(
    transaction_id,
) -> TransactionScore:
    return TransactionScore(
        transaction_id=transaction_id,
        fraud_probability=0.90,
        anomaly_score=0.80,
        combined_risk_score=0.875,
        risk_level="critical",
        requires_human_review=True,
        risk_factors=[],
    )


@pytest.mark.asyncio
async def test_agent_failure_is_isolated() -> None:
    request = build_request()
    score = build_score(
        request.transaction.transaction_id
    )

    async def failing_agent(request, score):
        raise RuntimeError("simulated specialist failure")

    spec = AgentSpec(
        name="simulated_failure_agent",
        handler=failing_agent,
        timeout_seconds=1.0,
        confidence_weight=1.0,
        critical=False,
    )

    finding = await _run_agent_safely(
        spec,
        request,
        score,
    )

    assert finding.agent == "simulated_failure_agent"
    assert finding.status == "completed"
    assert finding.confidence < 0.5

    sources = {
        evidence.source
        for evidence in finding.evidence
    }

    assert "orchestrator_runtime" in sources
    assert finding.warnings
    assert "RuntimeError" in finding.warnings[0]


@pytest.mark.asyncio
async def test_agent_timeout_is_isolated() -> None:
    request = build_request()
    score = build_score(
        request.transaction.transaction_id
    )

    async def slow_agent(request, score):
        await asyncio.sleep(0.20)
        raise AssertionError("should have timed out first")

    spec = AgentSpec(
        name="simulated_timeout_agent",
        handler=slow_agent,
        timeout_seconds=0.01,
        confidence_weight=1.0,
        critical=True,
    )

    finding = await _run_agent_safely(
        spec,
        request,
        score,
    )

    assert finding.agent == "simulated_timeout_agent"
    assert finding.status == "completed"
    assert finding.confidence < 0.5

    sources = {
        evidence.source
        for evidence in finding.evidence
    }

    assert "orchestrator_runtime" in sources
    assert finding.warnings
    assert "timeout" in finding.warnings[0].lower()
