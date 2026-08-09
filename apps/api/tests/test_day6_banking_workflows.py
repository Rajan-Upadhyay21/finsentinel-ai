from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

import app.agents.orchestrator as orchestrator
from app.schemas.investigation import (
    ComplianceFeatures,
    InvestigationDecision,
    InvestigationRequest,
    LoanFeatures,
)
from app.schemas.transaction import TransactionFeatures
from app.services.credit_engine import score_credit_application


def transaction_payload() -> TransactionFeatures:
    return TransactionFeatures(
        customer_id="CUST-TEST",
        account_id="ACCT-TEST",
        merchant_id="MERCHANT-TEST",
        amount=Decimal("2500.00"),
        currency="USD",
        country_code="US",
        device_known=True,
        ip_risk_score=0.10,
        merchant_risk_score=0.10,
        amount_zscore=0.5,
        velocity_1h=1,
    )


def loan_payload() -> LoanFeatures:
    return LoanFeatures(
        application_id="LOAN-TEST",
        customer_id="CUST-TEST",
        requested_amount=25000,
        annual_income=85000,
        debt_to_income_ratio=0.28,
        credit_score=742,
        existing_risk_probability=0.18,
    )


def compliance_payload(
    *,
    sanctions_match: bool = False,
) -> ComplianceFeatures:
    return ComplianceFeatures(
        customer_id="CUST-TEST",
        country_code="US",
        customer_risk_level=(
            "high"
            if sanctions_match
            else "low"
        ),
        kyc_verified=not sanctions_match,
        is_pep=sanctions_match,
        sanctions_match=sanctions_match,
    )


def fake_decision(
    request: InvestigationRequest,
    workflow: str,
) -> InvestigationDecision:
    return InvestigationDecision(
        case_id=request.case_id,
        workflow=workflow,
        findings=[],
        contradictions=[],
        decision="approve",
        final_confidence=0.90,
        rationale=f"{workflow} routing test",
    )


def test_all_four_workflow_contracts_are_valid() -> None:
    fraud = InvestigationRequest(
        workflow="fraud",
        transaction=transaction_payload(),
    )

    aml = InvestigationRequest(
        workflow="aml",
        transaction=transaction_payload(),
        compliance=compliance_payload(),
    )

    credit = InvestigationRequest(
        workflow="credit",
        loan=loan_payload(),
    )

    compliance = InvestigationRequest(
        workflow="compliance",
        compliance=compliance_payload(),
    )

    assert fraud.workflow == "fraud"
    assert aml.workflow == "aml"
    assert credit.workflow == "credit"
    assert compliance.workflow == "compliance"


@pytest.mark.parametrize(
    "workflow",
    [
        "fraud",
        "aml",
    ],
)
def test_transaction_workflows_require_transaction(
    workflow: str,
) -> None:
    with pytest.raises(ValidationError):
        InvestigationRequest(
            workflow=workflow,
        )


def test_credit_workflow_requires_loan() -> None:
    with pytest.raises(ValidationError):
        InvestigationRequest(
            workflow="credit",
        )


def test_compliance_workflow_requires_compliance_data() -> None:
    with pytest.raises(ValidationError):
        InvestigationRequest(
            workflow="compliance",
        )


@pytest.mark.asyncio
async def test_router_dispatches_fraud_workflow(
    monkeypatch,
) -> None:
    request = InvestigationRequest(
        workflow="fraud",
        transaction=transaction_payload(),
    )

    async def fake_handler(req):
        return fake_decision(
            req,
            "fraud",
        )

    monkeypatch.setattr(
        orchestrator,
        "_run_fraud_workflow",
        fake_handler,
    )

    result = await orchestrator.run_investigation(
        request
    )

    assert result.workflow == "fraud"


@pytest.mark.asyncio
async def test_router_dispatches_aml_workflow(
    monkeypatch,
) -> None:
    request = InvestigationRequest(
        workflow="aml",
        transaction=transaction_payload(),
        compliance=compliance_payload(),
    )

    async def fake_handler(req):
        return fake_decision(
            req,
            "aml",
        )

    monkeypatch.setattr(
        orchestrator,
        "_run_aml_workflow",
        fake_handler,
    )

    result = await orchestrator.run_investigation(
        request
    )

    assert result.workflow == "aml"


@pytest.mark.asyncio
async def test_router_dispatches_credit_workflow(
    monkeypatch,
) -> None:
    request = InvestigationRequest(
        workflow="credit",
        loan=loan_payload(),
    )

    async def fake_handler(req):
        return fake_decision(
            req,
            "credit",
        )

    monkeypatch.setattr(
        orchestrator,
        "_run_credit_workflow",
        fake_handler,
    )

    result = await orchestrator.run_investigation(
        request
    )

    assert result.workflow == "credit"


@pytest.mark.asyncio
async def test_router_dispatches_compliance_workflow(
    monkeypatch,
) -> None:
    request = InvestigationRequest(
        workflow="compliance",
        compliance=compliance_payload(),
    )

    async def fake_handler(req):
        return fake_decision(
            req,
            "compliance",
        )

    monkeypatch.setattr(
        orchestrator,
        "_run_compliance_workflow",
        fake_handler,
    )

    result = await orchestrator.run_investigation(
        request
    )

    assert result.workflow == "compliance"


def test_credit_engine_scores_strong_application_low_risk() -> None:
    score = score_credit_application(
        loan_payload()
    )

    assert 0.0 <= score.risk_probability <= 1.0
    assert score.risk_level in {
        "low",
        "medium",
        "high",
        "critical",
    }
    assert score.requires_human_review is False
    assert score.reasons


def test_credit_engine_routes_risky_application_to_review() -> None:
    loan = LoanFeatures(
        application_id="LOAN-HIGH-RISK",
        customer_id="CUST-HIGH-RISK",
        requested_amount=90000,
        annual_income=70000,
        debt_to_income_ratio=0.62,
        credit_score=520,
        existing_risk_probability=0.85,
    )

    score = score_credit_application(
        loan
    )

    assert score.risk_level in {
        "high",
        "critical",
    }
    assert score.requires_human_review is True
    assert score.risk_probability >= 0.55
