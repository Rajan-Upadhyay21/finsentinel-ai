from __future__ import annotations

from pathlib import Path

import pytest

from app.ml.features import TransactionFeatureInput, engineer_feature_row
from app.ml.inference import FraudInferenceEngine
from app.schemas.transaction import TransactionFeatures
from app.services.risk_engine import score_transaction


MODEL_PATH = Path("artifacts/ml/fraud/fraud_bundle.joblib")


def test_feature_engineering_produces_expected_runtime_features() -> None:
    raw = TransactionFeatureInput(
        amount=9750.0,
        amount_zscore=5.1,
        velocity_1h=11,
        ip_risk_score=0.91,
        merchant_risk_score=0.89,
        device_known=False,
        is_cross_border=True,
        hour=2,
        account_age_days=365,
        customer_tenure_days=730,
    )

    features = engineer_feature_row(raw)

    assert features["log_amount"] > 0
    assert features["amount_zscore"] == 5.1
    assert features["velocity_1h"] == 11.0
    assert features["ip_risk_score"] == 0.91
    assert features["merchant_risk_score"] == 0.89
    assert features["device_unknown"] == 1.0
    assert features["cross_border"] == 1.0
    assert features["night_transaction"] == 1.0


@pytest.mark.skipif(
    not MODEL_PATH.exists(),
    reason="Trained fraud model artifact is not available.",
)
def test_trained_model_scores_high_risk_transaction() -> None:
    engine = FraudInferenceEngine(MODEL_PATH)

    features = engineer_feature_row(
        TransactionFeatureInput(
            amount=9750.0,
            amount_zscore=5.1,
            velocity_1h=11,
            ip_risk_score=0.91,
            merchant_risk_score=0.89,
            device_known=False,
            is_cross_border=False,
            hour=17,
            account_age_days=365,
            customer_tenure_days=730,
        )
    )

    prediction = engine.predict(features)

    assert 0.0 <= prediction.fraud_probability <= 1.0
    assert 0.0 <= prediction.anomaly_score <= 1.0
    assert prediction.fraud_probability >= prediction.decision_threshold
    assert prediction.predicted_fraud is True
    assert prediction.risk_level in {"high", "critical"}
    assert prediction.model_version


@pytest.mark.skipif(
    not MODEL_PATH.exists(),
    reason="Trained fraud model artifact is not available.",
)
def test_risk_engine_uses_ml_prediction_and_explanations() -> None:
    tx = TransactionFeatures(
        customer_id="CUST-TEST",
        account_id="ACCT-TEST",
        merchant_id="M-CRYPTO-TEST",
        amount=9750.00,
        currency="USD",
        country_code="US",
        is_cross_border=False,
        account_age_days=365,
        customer_tenure_days=730,
        device_known=False,
        ip_risk_score=0.91,
        merchant_risk_score=0.89,
        amount_zscore=5.1,
        velocity_1h=11,
    )

    score = score_transaction(tx)

    factor_codes = {factor.code for factor in score.risk_factors}

    assert score.fraud_probability >= 0.0
    assert score.anomaly_score >= 0.0
    assert score.combined_risk_score >= 0.0
    assert score.risk_level in {"low", "medium", "high", "critical"}

    assert "ml_fraud_signal" in factor_codes
    assert "high_amount" in factor_codes
    assert "new_device" in factor_codes
    assert "risky_ip" in factor_codes
    assert "risky_merchant" in factor_codes
    assert "extreme_behavioral_outlier" in factor_codes
    assert "high_velocity" in factor_codes
