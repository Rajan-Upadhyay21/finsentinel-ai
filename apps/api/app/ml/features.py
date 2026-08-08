from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np


FRAUD_FEATURES: list[str] = [
    "log_amount",
    "amount_zscore",
    "velocity_1h",
    "ip_risk_score",
    "merchant_risk_score",
    "device_unknown",
    "cross_border",
    "night_transaction",
    "account_age_days_log",
    "customer_tenure_days_log",
]


@dataclass(frozen=True)
class TransactionFeatureInput:
    amount: float
    amount_zscore: float
    velocity_1h: int
    ip_risk_score: float
    merchant_risk_score: float
    device_known: bool
    is_cross_border: bool
    hour: int
    account_age_days: int
    customer_tenure_days: int


def engineer_feature_row(payload: TransactionFeatureInput) -> dict[str, float]:
    """Transform raw transaction signals into the production fraud feature vector."""

    amount = max(float(payload.amount), 0.0)
    hour = int(payload.hour) % 24

    return {
        "log_amount": float(np.log1p(amount)),
        "amount_zscore": float(payload.amount_zscore),
        "velocity_1h": float(max(payload.velocity_1h, 0)),
        "ip_risk_score": float(np.clip(payload.ip_risk_score, 0.0, 1.0)),
        "merchant_risk_score": float(np.clip(payload.merchant_risk_score, 0.0, 1.0)),
        "device_unknown": 0.0 if payload.device_known else 1.0,
        "cross_border": 1.0 if payload.is_cross_border else 0.0,
        "night_transaction": 1.0 if hour <= 5 or hour >= 23 else 0.0,
        "account_age_days_log": float(np.log1p(max(payload.account_age_days, 0))),
        "customer_tenure_days_log": float(
            np.log1p(max(payload.customer_tenure_days, 0))
        ),
    }


def dataframe_from_feature_rows(rows: Iterable[dict[str, float]]) -> "pd.DataFrame":
    """Create a model-ready frame with deterministic feature ordering."""

    import pandas as pd

    frame = pd.DataFrame(list(rows))

    missing = [name for name in FRAUD_FEATURES if name not in frame.columns]
    if missing:
        raise ValueError(f"Missing fraud features: {missing}")

    return frame[FRAUD_FEATURES].astype(float)
