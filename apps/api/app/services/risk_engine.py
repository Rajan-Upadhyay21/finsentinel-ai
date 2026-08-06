from math import exp

from app.schemas.transaction import RiskFactor, TransactionFeatures, TransactionScore


def _sigmoid(value: float) -> float:
    return 1.0 / (1.0 + exp(-value))


def score_transaction(tx: TransactionFeatures) -> TransactionScore:
    factors: list[RiskFactor] = []
    raw = -3.25

    def add(code: str, weight: float, explanation: str) -> None:
        nonlocal raw
        raw += weight
        factors.append(RiskFactor(code=code, weight=weight, explanation=explanation))

    amount = float(tx.amount)
    if amount >= 5000:
        add("high_amount", 1.15, "Transaction amount is materially above the retail baseline.")
    elif amount >= 1500:
        add("elevated_amount", 0.55, "Transaction amount is above the typical retail range.")

    if not tx.device_known:
        add("new_device", 1.05, "The transaction originated from an unrecognized device.")

    if tx.ip_risk_score >= 0.7:
        add("risky_ip", 1.30, "The originating IP has a high external risk score.")
    elif tx.ip_risk_score >= 0.4:
        add("moderate_ip_risk", 0.55, "The originating IP has an elevated risk score.")

    if tx.merchant_risk_score >= 0.7:
        add("risky_merchant", 1.10, "The merchant has a high historical risk score.")

    if abs(tx.amount_zscore) >= 4:
        add("extreme_behavioral_outlier", 1.35, "Amount is an extreme customer-level outlier.")
    elif abs(tx.amount_zscore) >= 2.5:
        add("behavioral_outlier", 0.75, "Amount is unusual for this customer.")

    if tx.velocity_1h >= 8:
        add("high_velocity", 1.25, "Unusually many transactions occurred within one hour.")
    elif tx.velocity_1h >= 4:
        add("elevated_velocity", 0.55, "Transaction velocity is elevated.")

    fraud_probability = _sigmoid(raw)
    anomaly_score = min(1.0, max(0.0, (abs(tx.amount_zscore) / 6.0) * 0.55 + tx.ip_risk_score * 0.25 + (0.2 if not tx.device_known else 0.0)))
    combined = min(1.0, fraud_probability * 0.72 + anomaly_score * 0.28)

    if combined >= 0.85:
        level = "critical"
    elif combined >= 0.65:
        level = "high"
    elif combined >= 0.35:
        level = "medium"
    else:
        level = "low"

    return TransactionScore(
        transaction_id=tx.transaction_id,
        fraud_probability=round(fraud_probability, 4),
        anomaly_score=round(anomaly_score, 4),
        combined_risk_score=round(combined, 4),
        risk_level=level,
        requires_human_review=level in {"high", "critical"},
        risk_factors=sorted(factors, key=lambda item: item.weight, reverse=True),
    )
