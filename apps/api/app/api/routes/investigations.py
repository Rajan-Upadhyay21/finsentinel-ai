from fastapi import APIRouter

from app.agents.orchestrator import run_investigation
from app.schemas.investigation import InvestigationDecision, InvestigationRequest

router = APIRouter(prefix="/api/v1/investigations", tags=["investigations"])


@router.post("/run", response_model=InvestigationDecision)
async def investigate(payload: InvestigationRequest) -> InvestigationDecision:
    return await run_investigation(payload)
