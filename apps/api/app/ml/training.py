from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split
from xgboost import XGBClassifier

from app.ml.features import FRAUD_FEATURES
from app.ml.synthetic import generate_synthetic_fraud_dataset


@dataclass(frozen=True)
class ModelMetrics:
    pr_auc: float
    roc_auc: float
    precision: float
    recall: float
    f1: float
    brier_score: float
    threshold: float
    true_negative: int
    false_positive: int
    false_negative: int
    true_positive: int


def choose_cost_sensitive_threshold(
    y_true: np.ndarray,
    probabilities: np.ndarray,
    false_negative_cost: float = 12.0,
    false_positive_cost: float = 1.0,
) -> float:
    """Choose the validation threshold minimizing a simple fraud business cost."""

    best_threshold = 0.5
    best_cost = float("inf")

    for threshold in np.linspace(0.05, 0.95, 181):
        predictions = (probabilities >= threshold).astype(int)

        false_negative = int(((y_true == 1) & (predictions == 0)).sum())
        false_positive = int(((y_true == 0) & (predictions == 1)).sum())

        cost = false_negative_cost * false_negative + false_positive_cost * false_positive

        if cost < best_cost:
            best_cost = cost
            best_threshold = float(threshold)

    return best_threshold


def evaluate_classifier(
    y_true: np.ndarray,
    probabilities: np.ndarray,
    threshold: float,
) -> ModelMetrics:
    predictions = (probabilities >= threshold).astype(int)
    tn, fp, fn, tp = confusion_matrix(y_true, predictions, labels=[0, 1]).ravel()

    return ModelMetrics(
        pr_auc=float(average_precision_score(y_true, probabilities)),
        roc_auc=float(roc_auc_score(y_true, probabilities)),
        precision=float(precision_score(y_true, predictions, zero_division=0)),
        recall=float(recall_score(y_true, predictions, zero_division=0)),
        f1=float(f1_score(y_true, predictions, zero_division=0)),
        brier_score=float(brier_score_loss(y_true, probabilities)),
        threshold=float(threshold),
        true_negative=int(tn),
        false_positive=int(fp),
        false_negative=int(fn),
        true_positive=int(tp),
    )


def _build_classifier(random_state: int) -> XGBClassifier:
    return XGBClassifier(
        n_estimators=320,
        max_depth=5,
        learning_rate=0.045,
        subsample=0.90,
        colsample_bytree=0.90,
        min_child_weight=3,
        reg_alpha=0.05,
        reg_lambda=1.20,
        objective="binary:logistic",
        eval_metric="logloss",
        random_state=random_state,
        n_jobs=2,
        tree_method="hist",
    )


def train_fraud_bundle(
    output_dir: str | Path,
    n_rows: int = 12000,
    random_state: int = 42,
) -> dict[str, Any]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    frame = generate_synthetic_fraud_dataset(
        n_rows=n_rows,
        random_state=random_state,
    )

    X = frame[FRAUD_FEATURES]
    y = frame["is_fraud"].to_numpy()

    # 70 / 15 / 15 stratified split.
    X_train, X_temp, y_train, y_temp = train_test_split(
        X,
        y,
        test_size=0.30,
        stratify=y,
        random_state=random_state,
    )

    X_validation, X_test, y_validation, y_test = train_test_split(
        X_temp,
        y_temp,
        test_size=0.50,
        stratify=y_temp,
        random_state=random_state,
    )

    fraud_rate = float(y_train.mean())
    positive_weight = float((len(y_train) - y_train.sum()) / max(y_train.sum(), 1))

    classifier = _build_classifier(random_state=random_state)
    classifier.set_params(scale_pos_weight=max(1.0, positive_weight))
    classifier.fit(X_train, y_train)

    validation_probability = classifier.predict_proba(X_validation)[:, 1]

    threshold = choose_cost_sensitive_threshold(
        y_validation,
        validation_probability,
        false_negative_cost=12.0,
        false_positive_cost=1.0,
    )

    test_probability = classifier.predict_proba(X_test)[:, 1]
    metrics = evaluate_classifier(
        y_true=y_test,
        probabilities=test_probability,
        threshold=threshold,
    )

    # Fit anomaly detector only on legitimate training behavior.
    legitimate_train = X_train[y_train == 0].to_numpy(dtype=float)

    anomaly_detector = IsolationForest(
        n_estimators=250,
        contamination="auto",
        max_samples="auto",
        random_state=random_state,
        n_jobs=2,
    )
    anomaly_detector.fit(legitimate_train)

    version = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    bundle = {
        "version": version,
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "feature_names": FRAUD_FEATURES,
        "fraud_classifier": classifier,
        "anomaly_detector": anomaly_detector,
        "decision_threshold": threshold,
        "metrics": asdict(metrics),
        "training": {
            "n_rows": int(n_rows),
            "fraud_rate_train": fraud_rate,
            "scale_pos_weight": positive_weight,
            "random_state": random_state,
        },
    }

    bundle_path = output_path / "fraud_bundle.joblib"
    metrics_path = output_path / "metrics.json"
    sample_path = output_path / "synthetic_sample.csv"

    joblib.dump(bundle, bundle_path)

    metrics_payload = {
        "version": version,
        "trained_at": bundle["trained_at"],
        "metrics": asdict(metrics),
        "training": bundle["training"],
    }

    metrics_path.write_text(
        json.dumps(metrics_payload, indent=2),
        encoding="utf-8",
    )

    frame.sample(
        n=min(500, len(frame)),
        random_state=random_state,
    ).to_csv(sample_path, index=False)

    _log_to_mlflow_if_available(
        bundle_path=bundle_path,
        metrics_path=metrics_path,
        metrics=metrics,
        n_rows=n_rows,
        random_state=random_state,
    )

    return {
        "bundle_path": str(bundle_path),
        "metrics_path": str(metrics_path),
        "sample_path": str(sample_path),
        "version": version,
        "fraud_rate": float(frame["is_fraud"].mean()),
        "metrics": asdict(metrics),
    }


def _log_to_mlflow_if_available(
    *,
    bundle_path: Path,
    metrics_path: Path,
    metrics: ModelMetrics,
    n_rows: int,
    random_state: int,
) -> None:
    """Log locally when MLflow is installed; training still works without it."""

    try:
        import mlflow
    except ImportError:
        return

    mlflow.set_experiment("finsentinel-fraud-intelligence")

    with mlflow.start_run():
        mlflow.log_param("n_rows", n_rows)
        mlflow.log_param("random_state", random_state)
        mlflow.log_param("model", "XGBClassifier")
        mlflow.log_param("anomaly_model", "IsolationForest")
        mlflow.log_param("threshold_strategy", "cost_sensitive")

        for key, value in asdict(metrics).items():
            if isinstance(value, (int, float)):
                mlflow.log_metric(key, float(value))

        mlflow.log_artifact(str(bundle_path))
        mlflow.log_artifact(str(metrics_path))
