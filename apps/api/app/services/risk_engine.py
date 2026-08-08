from __future__ import annotations

from app.ml.features import TransactionFeatureInput, engineer_feature_row
from app.ml.inference import get_fraud_inference_engine
from app.schemas.transaction import (
    RiskFactor,
    TransactionFeatures,
    TransactionScore,
)


def _build_risk_factors(tx: TransactionFeatures) -> list[RiskFactor]:
    """
    Build human-readable contextual risk indicators.

    These rules explain notable transaction characteristics but DO NOT
    determine the ML fraud probability or anomaly score.
    """

    factors: list[RiskFactor] = []
    amount = float(tx.amount)

    def add(code: str, weight: float, explanation: str) -> None:
        factors.append(
            RiskFactor(
                code=code,
                weight=weight,
                explanation=explanation,
            )
        )

    if amount >= 5000:
        add(
            "high_amount",
            1.15,
            "Transaction amount is materially above the retail baseline.",
        )
    elif amount >= 1500:
        add(
            "elevated_amount",
            0.55,
            "Transaction amount is above the typical retail range.",
        )

    if not tx.device_known:
        add(
            "new_device",
            1.05,
            "The transaction originated from an unrecognized device.",
        )

    if tx.ip_risk_score >= 0.7:
        add(
            "risky_ip",
            1.30,
            "The originating IP has a high external risk score.",
        )
    elif tx.ip_risk_score >= 0.4:
        add(
            "moderate_ip_risk",
            0.55,
            "The originating IP has an elevated risk score.",
        )

    if tx.merchant_risk_score >= 0.7:
        add(
            "risky_merchant",
            1.10,
            "The merchant has a high historical risk score.",
        )

    if abs(tx.amount_zscore) >= 4:
        add(
            "extreme_behavioral_outlier",
            1.35,
            "Amount is an extreme customer-level behavioral outlier.",
        )
    elif abs(tx.amount_zscore) >= 2.5:
        add(
            "behavioral_outlier",
            0.75,
            "Amount is unusual relative to customer behavior.",
        )

    if tx.velocity_1h >= 8:
        add(
            "high_velocity",
            1.25,
            "Unusually many transactions occurred within one hour.",
        )
    elif tx.velocity_1h >= 4:
        add(
            "elevated_velocity",
            0.55,
            "Transaction velocity is elevated.",
        )

    if tx.is_cross_border:
        add(
            "cross_border",
            0.65,
            "Transaction occurred across the customer's home-country boundary.",
        )

    if tx.timestamp.hour <= 5 or tx.timestamp.hour >= 23:
        add(
            "night_transaction",
            0.40,
            "Transaction occurred during an elevated-risk overnight period.",
        )

    return sorted(
        factors,
        key=lambda item: item.weight,
        reverse=True,
    )


def score_transaction(tx: TransactionFeatures) -> TransactionScore:
    """
    Score a transaction using the trained FinSentinel ML fraud bundle.

    XGBoost produces the fraud probability.
    Isolation Forest produces the anomaly signal.

    Human-readable rule indicators are retained strictly as contextual
    evidence for agents and reviewers.
    """

    raw_features = TransactionFeatureInput(
        amount=float(tx.amount),
        amount_zscore=float(tx.amount_zscore),
        velocity_1h=int(tx.velocity_1h),
        ip_risk_score=float(tx.ip_risk_score),
        merchant_risk_score=float(tx.merchant_risk_score),
        device_known=bool(tx.device_known),
        is_cross_border=bool(tx.is_cross_border),
        hour=tx.timestamp.hour,
        account_age_days=int(tx.account_age_days),
        customer_tenure_days=int(tx.customer_tenure_days),
    )

    engineered_features = engineer_feature_row(raw_features)

    engine = get_fraud_inference_engine()
    prediction = engine.predict(engineered_features)

    fraud_probability = prediction.fraud_probability
    anomaly_score = prediction.anomaly_score

    combined = min(
        1.0,
        max(
            0.0,
            (fraud_probability * 0.75)
            + (anomaly_score * 0.25),
        ),
    )

    if combined >= 0.80:
        risk_level = "critical"
    elif combined >= 0.60:
        risk_level = "high"
    elif combined >= 0.35:
        risk_level = "medium"
    else:
        risk_level = "low"

    risk_factors = _build_risk_factors(tx)

    if prediction.predicted_fraud:
        risk_factors.insert(
            0,
            RiskFactor(
                code="ml_fraud_signal",
                weight=round(fraud_probability, 4),
                explanation=(
                    "The trained fraud classifier exceeded its "
                    f"{prediction.decision_threshold:.3f} decision threshold."
                ),
            ),
        )

    if prediction.anomaly_flag:
        risk_factors.insert(
            0,
            RiskFactor(
                code="ml_anomaly_signal",
                weight=round(anomaly_score, 4),
                explanation=(
                    "Isolation Forest identified the transaction as "
                    "behaviorally anomalous."
                ),
            ),
        )

    return TransactionScore(
        transaction_id=tx.transaction_id,
        fraud_probability=round(fraud_probability, 4),
        anomaly_score=round(anomaly_score, 4),
        combined_risk_score=round(combined, 4),
        risk_level=risk_level,
        requires_human_review=risk_level in {"high", "critical"},
        risk_factors=risk_factors,
    )
