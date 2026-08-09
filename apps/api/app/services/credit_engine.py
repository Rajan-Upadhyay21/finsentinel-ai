from __future__ import annotations

from app.schemas.investigation import CreditRiskScore, LoanFeatures


def score_credit_application(
    loan: LoanFeatures,
) -> CreditRiskScore:
    """
    Produce an explainable underwriting risk score for the portfolio demo.

    This is a synthetic portfolio scoring policy, not a real lender's
    underwriting model.
    """

    risk = 0.10
    reasons: list[str] = []

    dti = float(loan.debt_to_income_ratio)
    amount_to_income = (
        float(loan.requested_amount)
        / max(float(loan.annual_income), 1.0)
    )

    # Debt-to-income risk.
    if dti >= 0.50:
        risk += 0.35
        reasons.append(
            "Debt-to-income ratio is above the high-risk threshold."
        )
    elif dti >= 0.40:
        risk += 0.24
        reasons.append(
            "Debt-to-income ratio is materially elevated."
        )
    elif dti >= 0.30:
        risk += 0.10
        reasons.append(
            "Debt-to-income ratio is moderately elevated."
        )
    else:
        reasons.append(
            "Debt-to-income ratio is within the lower-risk range."
        )

    # Credit history signal.
    if loan.credit_score is None:
        risk += 0.25
        reasons.append(
            "Credit score is unavailable and requires additional review."
        )
    elif loan.credit_score < 580:
        risk += 0.42
        reasons.append(
            "Credit score falls within a high-risk range."
        )
    elif loan.credit_score < 670:
        risk += 0.25
        reasons.append(
            "Credit score indicates elevated underwriting risk."
        )
    elif loan.credit_score < 740:
        risk += 0.10
        reasons.append(
            "Credit score indicates moderate underwriting risk."
        )
    else:
        risk -= 0.05
        reasons.append(
            "Credit score provides a strong positive credit signal."
        )

    # Requested credit relative to stated income.
    if amount_to_income >= 0.60:
        risk += 0.25
        reasons.append(
            "Requested credit is large relative to annual income."
        )
    elif amount_to_income >= 0.40:
        risk += 0.15
        reasons.append(
            "Requested credit is elevated relative to annual income."
        )
    elif amount_to_income >= 0.25:
        risk += 0.07
        reasons.append(
            "Requested credit is moderately sized relative to income."
        )

    # Blend any previously persisted model / underwriting signal.
    existing = float(loan.existing_risk_probability)

    risk = (
        risk * 0.70
        + existing * 0.30
    )

    risk = min(
        1.0,
        max(0.0, risk),
    )

    if risk >= 0.75:
        level = "critical"
    elif risk >= 0.55:
        level = "high"
    elif risk >= 0.30:
        level = "medium"
    else:
        level = "low"

    return CreditRiskScore(
        application_id=loan.application_id,
        risk_probability=round(risk, 4),
        risk_level=level,
        requires_human_review=level in {
            "high",
            "critical",
        },
        reasons=reasons,
    )
