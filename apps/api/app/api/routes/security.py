from __future__ import annotations

from pydantic import BaseModel

from fastapi import APIRouter

from app.core.permissions import (
    permissions_for_roles,
)
from app.core.security import CurrentUser


router = APIRouter(
    prefix="/api/v1/security",
    tags=["security"],
)


class CurrentUserResponse(BaseModel):
    subject: str
    username: str
    email: str | None
    roles: list[str]
    permissions: list[str]


@router.get(
    "/me",
    response_model=CurrentUserResponse,
)
async def current_identity(
    current_user: CurrentUser,
) -> CurrentUserResponse:
    permissions = permissions_for_roles(
        current_user.roles
    )

    return CurrentUserResponse(
        subject=current_user.subject,
        username=current_user.username,
        email=current_user.email,
        roles=sorted(
            current_user.roles
        ),
        permissions=sorted(
            permission.value
            for permission in permissions
        ),
    )
