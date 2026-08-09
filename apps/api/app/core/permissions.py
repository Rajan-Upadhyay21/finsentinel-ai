from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from fastapi import Depends, HTTPException, status

from app.core.security import (
    AuthenticatedUser,
    BankingRole,
    get_current_user,
)


class Permission(StrEnum):
    BANKING_READ = "banking:read"
    INVESTIGATION_READ = "investigation:read"

    FRAUD_INVESTIGATE = "fraud:investigate"
    FRAUD_DECIDE = "fraud:decide"

    AML_INVESTIGATE = "aml:investigate"
    AML_DECIDE = "aml:decide"

    CREDIT_INVESTIGATE = "credit:investigate"
    CREDIT_DECIDE = "credit:decide"

    COMPLIANCE_INVESTIGATE = "compliance:investigate"
    COMPLIANCE_DECIDE = "compliance:decide"

    AUDIT_READ = "audit:read"
    PLATFORM_ADMIN = "platform:admin"


ALL_PERMISSIONS = frozenset(Permission)


ROLE_PERMISSIONS: dict[
    BankingRole,
    frozenset[Permission],
] = {
    BankingRole.FRAUD_ANALYST: frozenset(
        {
            Permission.BANKING_READ,
            Permission.INVESTIGATION_READ,
            Permission.FRAUD_INVESTIGATE,
            Permission.FRAUD_DECIDE,
        }
    ),

    BankingRole.AML_INVESTIGATOR: frozenset(
        {
            Permission.BANKING_READ,
            Permission.INVESTIGATION_READ,
            Permission.AML_INVESTIGATE,
            Permission.AML_DECIDE,
        }
    ),

    BankingRole.CREDIT_ANALYST: frozenset(
        {
            Permission.BANKING_READ,
            Permission.INVESTIGATION_READ,
            Permission.CREDIT_INVESTIGATE,
            Permission.CREDIT_DECIDE,
        }
    ),

    BankingRole.COMPLIANCE_OFFICER: frozenset(
        {
            Permission.BANKING_READ,
            Permission.INVESTIGATION_READ,
            Permission.COMPLIANCE_INVESTIGATE,
            Permission.COMPLIANCE_DECIDE,
            Permission.AUDIT_READ,
        }
    ),

    BankingRole.EXECUTIVE: frozenset(
        {
            Permission.BANKING_READ,
            Permission.INVESTIGATION_READ,
            Permission.AUDIT_READ,
        }
    ),

    BankingRole.AUDITOR: frozenset(
        {
            Permission.BANKING_READ,
            Permission.INVESTIGATION_READ,
            Permission.AUDIT_READ,
        }
    ),

    BankingRole.PLATFORM_ADMIN: ALL_PERMISSIONS,
}


def permissions_for_roles(
    roles: frozenset[str],
) -> frozenset[Permission]:
    permissions: set[Permission] = set()

    for raw_role in roles:
        try:
            role = BankingRole(raw_role)
        except ValueError:
            continue

        permissions.update(
            ROLE_PERMISSIONS.get(
                role,
                frozenset(),
            )
        )

    return frozenset(permissions)


def has_permission(
    user: AuthenticatedUser,
    permission: Permission,
) -> bool:
    return permission in permissions_for_roles(
        user.roles
    )


AuthenticatedPrincipal = Annotated[
    AuthenticatedUser,
    Depends(get_current_user),
]


def require_permissions(
    *required_permissions: Permission,
    require_all: bool = True,
):
    required = frozenset(
        required_permissions
    )

    async def dependency(
        user: AuthenticatedPrincipal,
    ) -> AuthenticatedUser:
        granted = permissions_for_roles(
            user.roles
        )

        if require_all:
            authorized = required.issubset(
                granted
            )
        else:
            authorized = bool(
                required & granted
            )

        if not authorized:
            raise HTTPException(
                status_code=(
                    status.HTTP_403_FORBIDDEN
                ),
                detail=(
                    "Authenticated user does not "
                    "have permission to perform "
                    "this operation."
                ),
            )

        return user

    return dependency


# ============================================================
# WORKFLOW-AWARE AUTHORIZATION
# ============================================================

WORKFLOW_INVESTIGATION_PERMISSION: dict[
    str,
    Permission,
] = {
    "fraud": Permission.FRAUD_INVESTIGATE,
    "aml": Permission.AML_INVESTIGATE,
    "credit": Permission.CREDIT_INVESTIGATE,
    "compliance": Permission.COMPLIANCE_INVESTIGATE,
}


WORKFLOW_DECISION_PERMISSION: dict[
    str,
    Permission,
] = {
    "fraud": Permission.FRAUD_DECIDE,
    "aml": Permission.AML_DECIDE,
    "credit": Permission.CREDIT_DECIDE,
    "compliance": Permission.COMPLIANCE_DECIDE,
}


def ensure_permission(
    user: AuthenticatedUser,
    permission: Permission,
) -> None:
    """
    Imperative authorization guard for domain-aware operations.
    """

    if not has_permission(
        user,
        permission,
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Authenticated user does not have "
                f"permission: {permission.value}"
            ),
        )


def _normalize_workflow(
    workflow: object,
) -> str:
    value = getattr(
        workflow,
        "value",
        workflow,
    )

    return str(value).lower()


def ensure_workflow_investigation_permission(
    user: AuthenticatedUser,
    workflow: object,
) -> None:
    workflow_name = _normalize_workflow(
        workflow
    )

    permission = (
        WORKFLOW_INVESTIGATION_PERMISSION.get(
            workflow_name
        )
    )

    if permission is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "No investigation permission mapping "
                f"exists for workflow: {workflow_name}"
            ),
        )

    ensure_permission(
        user,
        permission,
    )


def ensure_workflow_decision_permission(
    user: AuthenticatedUser,
    workflow: object,
) -> None:
    workflow_name = _normalize_workflow(
        workflow
    )

    permission = (
        WORKFLOW_DECISION_PERMISSION.get(
            workflow_name
        )
    )

    if permission is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "No decision permission mapping "
                f"exists for workflow: {workflow_name}"
            ),
        )

    ensure_permission(
        user,
        permission,
    )
