from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import joblib
import numpy as np

DEFAULT_MODEL_PATH = Path("artifacts/ml/fraud/fraud_bundle.joblib")


@dataclass(frozen=True)
class FraudPrediction:
    fraud_probability: float
    anomaly_score: float
    anomaly_flag: bool
    decision_threshold: float
    predicted_fraud: bool
    risk_level: str
    model_version: str


class FraudInferenceEngine:
    """
    Runtime inference engine for the FinSentinel fraud ML bundle.

    Loads the trained XGBoost fraud classifier and Isolation Forest
    anomaly detector from the versioned model artifact.
    """

    def __init__(self, model_path: str | Path = DEFAULT_MODEL_PATH) -> None:
        self.model_path = Path(model_path)

        if not self.model_path.exists():
            raise FileNotFoundError(
                f"Fraud model artifact not found: {self.model_path}"
            )

        self.bundle: dict[str, Any] = joblib.load(self.model_path)

        self.classifier = self.bundle["fraud_classifier"]
        self.anomaly_detector = self.bundle["anomaly_detector"]
        self.feature_names = list(self.bundle["feature_names"])
        self.threshold = float(self.bundle["decision_threshold"])
        self.version = str(self.bundle["version"])

    def predict(self, features: dict[str, float]) -> FraudPrediction:
        missing = [
            feature
            for feature in self.feature_names
            if feature not in features
        ]

        if missing:
            raise ValueError(f"Missing required ML features: {missing}")

        vector = np.array(
            [[float(features[name]) for name in self.feature_names]],
            dtype=float,
        )

        fraud_probability = float(
            self.classifier.predict_proba(vector)[0, 1]
        )

        isolation_decision = float(
            self.anomaly_detector.decision_function(vector)[0]
        )

        # Isolation Forest:
        # positive decision values = more normal
        # negative decision values = more anomalous.
        #
        # Convert the raw decision score into a bounded 0–1 anomaly
        # indicator for downstream agent orchestration. This is a
        # normalized risk proxy, not a calibrated probability.
        anomaly_score = float(
            1.0 / (1.0 + np.exp(8.0 * isolation_decision))
        )

        anomaly_flag = bool(
            self.anomaly_detector.predict(vector)[0] == -1
        )

        predicted_fraud = fraud_probability >= self.threshold

        risk_level = self._risk_level(
            fraud_probability=fraud_probability,
            anomaly_score=anomaly_score,
        )

        return FraudPrediction(
            fraud_probability=round(fraud_probability, 6),
            anomaly_score=round(anomaly_score, 6),
            anomaly_flag=anomaly_flag,
            decision_threshold=round(self.threshold, 6),
            predicted_fraud=bool(predicted_fraud),
            risk_level=risk_level,
            model_version=self.version,
        )

    @staticmethod
    def _risk_level(
        fraud_probability: float,
        anomaly_score: float,
    ) -> str:
        combined = (0.75 * fraud_probability) + (0.25 * anomaly_score)

        if combined >= 0.80:
            return "critical"

        if combined >= 0.60:
            return "high"

        if combined >= 0.35:
            return "medium"

        return "low"


_engine: FraudInferenceEngine | None = None


def get_fraud_inference_engine(
    model_path: str | Path = DEFAULT_MODEL_PATH,
) -> FraudInferenceEngine:
    global _engine

    if _engine is None:
        _engine = FraudInferenceEngine(model_path=model_path)

    return _engine
