from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from math import sqrt
from threading import Lock
from typing import Any

from prometheus_client import Counter, Gauge

FEATURE_DRIFT_SCORE = Gauge(
    "finsentinel_feature_drift_score",
    "Rolling normalized shift from the online reference baseline.",
    ["feature"],
)

FEATURE_DRIFT_ALERT = Gauge(
    "finsentinel_feature_drift_alert",
    "Whether the rolling feature drift score exceeds its threshold.",
    ["feature"],
)

PREDICTION_SIGNAL = Gauge(
    "finsentinel_prediction_signal",
    "Most recently observed model prediction signal.",
    ["signal"],
)

DRIFT_OBSERVATIONS = Counter(
    "finsentinel_drift_observations_total",
    "Samples processed by the online drift monitor.",
    ["feature"],
)


@dataclass
class FeatureState:
    baseline_values: list[float] = field(
        default_factory=list
    )
    current_values: deque[float] = field(
        default_factory=deque
    )
    baseline_mean: float | None = None
    baseline_std: float | None = None
    last_score: float = 0.0
    alert: bool = False


class RollingDriftMonitor:
    """
    Lightweight label-free online drift detector.

    The first baseline_size observations establish a reference
    distribution. Later observations are compared using normalized
    mean shift.

    This detects data/prediction distribution drift. It does not
    claim accuracy/performance drift because production labels may
    arrive later.
    """

    def __init__(
        self,
        baseline_size: int = 20,
        current_size: int = 20,
        threshold: float = 2.0,
    ) -> None:
        if baseline_size < 2:
            raise ValueError(
                "baseline_size must be >= 2"
            )

        if current_size < 2:
            raise ValueError(
                "current_size must be >= 2"
            )

        self.baseline_size = baseline_size
        self.current_size = current_size
        self.threshold = threshold

        self._states: dict[str, FeatureState] = (
            defaultdict(FeatureState)
        )

        self._lock = Lock()

    @staticmethod
    def _stats(
        values: list[float],
    ) -> tuple[float, float]:
        mean = sum(values) / len(values)

        variance = sum(
            (value - mean) ** 2
            for value in values
        ) / max(
            1,
            len(values) - 1,
        )

        return mean, sqrt(variance)

    def observe(
        self,
        feature: str,
        value: float,
    ) -> tuple[float, bool]:
        numeric = float(value)

        with self._lock:
            state = self._states[feature]

            DRIFT_OBSERVATIONS.labels(
                feature=feature
            ).inc()

            if state.baseline_mean is None:
                state.baseline_values.append(
                    numeric
                )

                if (
                    len(state.baseline_values)
                    >= self.baseline_size
                ):
                    mean, std = self._stats(
                        state.baseline_values
                    )

                    state.baseline_mean = mean
                    state.baseline_std = std

                    state.current_values = deque(
                        maxlen=self.current_size
                    )

                FEATURE_DRIFT_SCORE.labels(
                    feature=feature
                ).set(0.0)

                FEATURE_DRIFT_ALERT.labels(
                    feature=feature
                ).set(0.0)

                return 0.0, False

            state.current_values.append(
                numeric
            )

            if (
                len(state.current_values)
                < self.current_size
            ):
                return (
                    state.last_score,
                    state.alert,
                )

            current = list(
                state.current_values
            )

            current_mean, _ = self._stats(
                current
            )

            baseline_mean = (
                state.baseline_mean
                if state.baseline_mean
                is not None
                else 0.0
            )

            baseline_std = (
                state.baseline_std
                if state.baseline_std
                is not None
                else 0.0
            )

            scale_floor = max(
                0.05
                * max(
                    abs(baseline_mean),
                    1.0,
                ),
                1e-6,
            )

            scale = max(
                baseline_std,
                scale_floor,
            )

            score = abs(
                current_mean
                - baseline_mean
            ) / scale

            alert = (
                score >= self.threshold
            )

            state.last_score = score
            state.alert = alert

            FEATURE_DRIFT_SCORE.labels(
                feature=feature
            ).set(
                score
            )

            FEATURE_DRIFT_ALERT.labels(
                feature=feature
            ).set(
                1.0
                if alert
                else 0.0
            )

            return score, alert

    def snapshot(
        self,
    ) -> dict[str, dict[str, Any]]:
        with self._lock:
            return {
                name: {
                    "baseline_mean": (
                        state.baseline_mean
                    ),
                    "baseline_std": (
                        state.baseline_std
                    ),
                    "score": state.last_score,
                    "alert": state.alert,
                    "current_samples": len(
                        state.current_values
                    ),
                }
                for name, state
                in self._states.items()
            }


_MONITOR = RollingDriftMonitor()


def reset_drift_monitor(
    baseline_size: int = 20,
    current_size: int = 20,
    threshold: float = 2.0,
) -> RollingDriftMonitor:
    global _MONITOR

    _MONITOR = RollingDriftMonitor(
        baseline_size=baseline_size,
        current_size=current_size,
        threshold=threshold,
    )

    return _MONITOR


def observe_model_sample(
    transaction: Any,
    score: Any,
) -> None:
    features = {
        "amount": getattr(
            transaction,
            "amount",
            0.0,
        ),
        "amount_zscore": getattr(
            transaction,
            "amount_zscore",
            0.0,
        ),
        "velocity_1h": getattr(
            transaction,
            "velocity_1h",
            0.0,
        ),
        "ip_risk_score": getattr(
            transaction,
            "ip_risk_score",
            0.0,
        ),
        "merchant_risk_score": getattr(
            transaction,
            "merchant_risk_score",
            0.0,
        ),
        "device_unknown": (
            0.0
            if getattr(
                transaction,
                "device_known",
                True,
            )
            else 1.0
        ),
        "cross_border": (
            1.0
            if getattr(
                transaction,
                "is_cross_border",
                False,
            )
            else 0.0
        ),
    }

    for name, value in features.items():
        try:
            _MONITOR.observe(
                name,
                float(value),
            )
        except (
            TypeError,
            ValueError,
        ):
            continue

    signals = {
        "fraud_probability": getattr(
            score,
            "fraud_probability",
            None,
        ),
        "anomaly_score": getattr(
            score,
            "anomaly_score",
            None,
        ),
        "combined_risk_score": getattr(
            score,
            "combined_risk_score",
            None,
        ),
    }

    for name, value in signals.items():
        if value is None:
            continue

        numeric = float(value)

        PREDICTION_SIGNAL.labels(
            signal=name
        ).set(
            numeric
        )

        _MONITOR.observe(
            f"prediction_{name}",
            numeric,
        )
