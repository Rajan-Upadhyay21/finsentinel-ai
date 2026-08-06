from decimal import Decimal

from app.schemas.transaction import TransactionFeatures
from app.services.risk_engine import score_transaction


def test_high_risk_transaction_requires_review() -> None:
    tx = TransactionFeatures(
        customer_id="C-100",
        account_id="A-100",
        merchant_id="M-900",
        amount=Decimal("9900.00"),
        device_known=False,
        ip_risk_score=0.92,
        merchant_risk_score=0.88,
        amount_zscore=5.2,
        velocity_1h=10,
    )
    result = score_transaction(tx)
    assert result.risk_level in {"high", "critical"}
    assert result.requires_human_review is True
    assert result.combined_risk_score >= 0.65


def test_normal_transaction_is_low_risk() -> None:
    tx = TransactionFeatures(
        customer_id="C-101",
        account_id="A-101",
        merchant_id="M-101",
        amount=Decimal("42.18"),
        device_known=True,
        ip_risk_score=0.05,
        merchant_risk_score=0.03,
        amount_zscore=0.2,
        velocity_1h=1,
    )
    result = score_transaction(tx)
    assert result.risk_level == "low"
    assert result.requires_human_review is False
