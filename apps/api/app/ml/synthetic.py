from __future__ import annotations

import numpy as np
import pandas as pd


def generate_synthetic_fraud_dataset(
    n_rows: int = 12000,
    random_state: int = 42,
) -> pd.DataFrame:
    """
    Generate a reproducible, intentionally imbalanced banking fraud dataset.

    Fraud labels are generated from a noisy latent-risk process rather than from
    one deterministic rule so that the model must learn interactions between
    transaction, device, network, merchant, and behavioral signals.
    """

    if n_rows < 2000:
        raise ValueError("n_rows must be at least 2000 for stable train/validation/test splits.")

    rng = np.random.default_rng(random_state)

    amount = np.exp(rng.normal(4.2, 1.15, n_rows)).clip(1, 30000)
    amount_zscore = rng.normal(0.0, 1.25, n_rows).clip(-4, 8)

    velocity_1h = rng.poisson(1.8, n_rows).clip(0, 25)
    ip_risk_score = rng.beta(1.4, 5.5, n_rows)
    merchant_risk_score = rng.beta(1.6, 6.0, n_rows)

    device_unknown = rng.binomial(1, 0.12, n_rows)
    cross_border = rng.binomial(1, 0.09, n_rows)

    hour = rng.integers(0, 24, n_rows)
    night_transaction = ((hour <= 5) | (hour >= 23)).astype(int)

    account_age_days = rng.integers(1, 3650, n_rows)
    customer_tenure_days = rng.integers(1, 5000, n_rows)

    # Hidden high-risk regimes.
    risky_ip = rng.binomial(1, 0.035, n_rows)
    ip_risk_score = np.where(
        risky_ip == 1,
        rng.uniform(0.72, 1.0, n_rows),
        ip_risk_score,
    )

    risky_merchant = rng.binomial(1, 0.04, n_rows)
    merchant_risk_score = np.where(
        risky_merchant == 1,
        rng.uniform(0.68, 1.0, n_rows),
        merchant_risk_score,
    )

    burst_activity = rng.binomial(1, 0.045, n_rows)
    velocity_1h = np.where(
        burst_activity == 1,
        rng.integers(7, 22, n_rows),
        velocity_1h,
    )

    behavioral_outlier = rng.binomial(1, 0.05, n_rows)
    amount_zscore = np.where(
        behavioral_outlier == 1,
        rng.uniform(3.0, 7.0, n_rows),
        amount_zscore,
    )

    # Latent fraud logit with interactions and random noise.
    logit = (
        -6.2
        + 2.9 * ip_risk_score
        + 2.5 * merchant_risk_score
        + 1.15 * device_unknown
        + 0.75 * cross_border
        + 0.60 * night_transaction
        + 0.19 * velocity_1h
        + 0.42 * np.maximum(amount_zscore, 0)
        + 0.28 * (amount > 3500)
        + 0.75 * ((device_unknown == 1) & (ip_risk_score > 0.65))
        + 0.85 * ((merchant_risk_score > 0.65) & (velocity_1h >= 6))
        + 0.60 * ((cross_border == 1) & (amount_zscore > 2.5))
        + rng.normal(0.0, 0.45, n_rows)
    )

    probability = 1.0 / (1.0 + np.exp(-logit))
    is_fraud = rng.binomial(1, probability)

    frame = pd.DataFrame(
        {
            "amount": amount.round(2),
            "log_amount": np.log1p(amount),
            "amount_zscore": amount_zscore,
            "velocity_1h": velocity_1h.astype(int),
            "ip_risk_score": ip_risk_score,
            "merchant_risk_score": merchant_risk_score,
            "device_unknown": device_unknown.astype(int),
            "cross_border": cross_border.astype(int),
            "night_transaction": night_transaction.astype(int),
            "account_age_days_log": np.log1p(account_age_days),
            "customer_tenure_days_log": np.log1p(customer_tenure_days),
            "is_fraud": is_fraud.astype(int),
        }
    )

    return frame
