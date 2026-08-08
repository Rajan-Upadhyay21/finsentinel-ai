from __future__ import annotations

from datetime import datetime, timezone

from app.ml.features import TransactionFeatureInput, engineer_feature_row
from app.ml.inference import FraudPrediction, get_fraud_inference_engine
from app.models.banking import Account, Customer, Transaction


def _days_since(value: datetime | None) -> int:
    """Return non-negative age in days for a persisted banking entity."""

    if value is None:
        return 0

    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)

    now = datetime.now(timezone.utc)
    return max((now - value).days, 0)


def score_banking_transaction(
    transaction: Transaction,
    account: Account,
    customer: Customer,
) -> FraudPrediction:
    """
    Convert persisted banking entities into the exact feature vector
    expected by the trained FinSentinel fraud model.
    """

    metadata = transaction.metadata_json or {}

    occurred_at = (
        transaction.occurred_at
        or transaction.created_at
        or datetime.now(timezone.utc)
    )

    transaction_country = str(
        metadata.get("country", customer.country_code)
    ).upper()

    customer_country = str(customer.country_code).upper()

    is_cross_border = bool(
        metadata.get(
            "is_cross_border",
            transaction_country != customer_country,
        )
    )

    raw_features = TransactionFeatureInput(
        amount=float(transaction.amount),
        amount_zscore=float(transaction.amount_zscore),
        velocity_1h=int(transaction.velocity_1h),
        ip_risk_score=float(transaction.ip_risk_score),
        merchant_risk_score=float(transaction.merchant_risk_score),
        device_known=bool(transaction.device_known),
        is_cross_border=is_cross_border,
        hour=occurred_at.hour,
        account_age_days=_days_since(account.created_at),
        customer_tenure_days=_days_since(customer.created_at),
    )

    engineered_features = engineer_feature_row(raw_features)

    engine = get_fraud_inference_engine()

    return engine.predict(engineered_features)
