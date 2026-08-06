from fastapi import APIRouter

from app.schemas.transaction import TransactionFeatures, TransactionScore
from app.services.risk_engine import score_transaction

router = APIRouter(prefix="/api/v1/transactions", tags=["transactions"])


@router.post("/score", response_model=TransactionScore)
def score(payload: TransactionFeatures) -> TransactionScore:
    return score_transaction(payload)
