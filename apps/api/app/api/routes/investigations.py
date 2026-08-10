from fastapi import APIRouter

from app.agents.orchestrator import run_investigation
from app.core.permissions import (
    ensure_workflow_investigation_permission,
)
from app.core.security import CurrentUser
from app.schemas.investigation import (
    InvestigationDecision,
    InvestigationRequest,
)

router = APIRouter(
    prefix="/api/v1/investigations",
    tags=["investigations"],
)


@router.post(
    "/run",
    response_model=InvestigationDecision,
)
async def investigate(
    payload: InvestigationRequest,
    current_user: CurrentUser,
) -> InvestigationDecision:
    """
    Run a governed banking investigation.

    Authorization is workflow-specific:
    fraud, AML, credit, and compliance investigators are
    isolated from one another unless a user holds multiple roles.
    """

    ensure_workflow_investigation_permission(
        current_user,
        payload.workflow,
    )

    return await run_investigation(
        payload
    )
