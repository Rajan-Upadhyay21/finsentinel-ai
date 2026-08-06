from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator


class TransactionFeatures(BaseModel):
    transaction_id: UUID = Field(default_factory=uuid4)
    customer_id: str = Field(min_length=1, max_length=128)
    account_id: str = Field(min_length=1, max_length=128)
    merchant_id: str = Field(min_length=1, max_length=128)
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    country_code: str = Field(default="US", min_length=2, max_length=2)
    device_known: bool = True
    ip_risk_score: float = Field(default=0.0, ge=0.0, le=1.0)
    merchant_risk_score: float = Field(default=0.0, ge=0.0, le=1.0)
    amount_zscore: float = Field(default=0.0, ge=-20.0, le=20.0)
    velocity_1h: int = Field(default=1, ge=0, le=1000)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("currency", "country_code")
    @classmethod
    def uppercase_codes(cls, value: str) -> str:
        return value.upper()


class RiskFactor(BaseModel):
    code: str
    weight: float
    explanation: str


class TransactionScore(BaseModel):
    transaction_id: UUID
    fraud_probability: float = Field(ge=0.0, le=1.0)
    anomaly_score: float = Field(ge=0.0, le=1.0)
    combined_risk_score: float = Field(ge=0.0, le=1.0)
    risk_level: Literal["low", "medium", "high", "critical"]
    requires_human_review: bool
    risk_factors: list[RiskFactor]
