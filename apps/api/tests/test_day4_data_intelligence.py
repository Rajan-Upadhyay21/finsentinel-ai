from __future__ import annotations

from app.services.graph_intelligence import _calculate_graph_risk
from app.services.policy_knowledge import POLICIES


def test_graph_risk_detects_cross_customer_network() -> None:
    score, indicators = _calculate_graph_risk(
        shared_device_transactions=1,
        linked_accounts=1,
        linked_customers=1,
        risky_merchant_transactions=1,
        prior_high_risk_transactions=1,
    )

    assert score > 0.0
    assert len(indicators) == 5
    assert any("shared" in item.lower() for item in indicators)
    assert any("customer" in item.lower() for item in indicators)
    assert any("merchant" in item.lower() for item in indicators)


def test_graph_risk_is_zero_without_relationships() -> None:
    score, indicators = _calculate_graph_risk(
        shared_device_transactions=0,
        linked_accounts=0,
        linked_customers=0,
        risky_merchant_transactions=0,
        prior_high_risk_transactions=0,
    )

    assert score == 0.0
    assert indicators == []


def test_policy_corpus_contains_fraud_network_governance_rules() -> None:
    policy_ids = {
        policy["policy_id"]
        for policy in POLICIES
    }

    assert "FRD-001" in policy_ids
    assert "FRD-002" in policy_ids
    assert "AML-002" in policy_ids
    assert "GOV-001" in policy_ids


def test_policy_ids_are_unique() -> None:
    policy_ids = [
        policy["policy_id"]
        for policy in POLICIES
    ]

    assert len(policy_ids) == len(set(policy_ids))
    assert len(policy_ids) >= 8
