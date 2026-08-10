from __future__ import annotations

from types import SimpleNamespace

from prometheus_client import generate_latest

from app.core.drift_monitor import (
    RollingDriftMonitor,
    observe_model_sample,
    reset_drift_monitor,
)


def test_distribution_shift_is_detected() -> None:
    monitor = RollingDriftMonitor(
        baseline_size=5,
        current_size=5,
        threshold=2.0,
    )

    for value in [
        1.0,
        1.1,
        0.9,
        1.05,
        0.95,
    ]:
        monitor.observe(
            "amount_zscore",
            value,
        )

    result = None

    for value in [
        5.0,
        5.1,
        4.9,
        5.2,
        5.0,
    ]:
        result = monitor.observe(
            "amount_zscore",
            value,
        )

    assert result is not None

    score, alert = result

    assert score >= 2.0
    assert alert is True


def test_model_sample_metrics() -> None:
    reset_drift_monitor(
        baseline_size=2,
        current_size=2,
        threshold=2.0,
    )

    transaction = SimpleNamespace(
        amount=100.0,
        amount_zscore=0.2,
        velocity_1h=1,
        ip_risk_score=0.1,
        merchant_risk_score=0.2,
        device_known=True,
        is_cross_border=False,
    )

    score = SimpleNamespace(
        fraud_probability=0.1,
        anomaly_score=0.2,
        combined_risk_score=0.125,
    )

    observe_model_sample(
        transaction,
        score,
    )

    observe_model_sample(
        transaction,
        score,
    )

    metrics = generate_latest().decode()

    assert (
        "finsentinel_feature_drift_score"
        in metrics
    )

    assert (
        "finsentinel_prediction_signal"
        in metrics
    )
