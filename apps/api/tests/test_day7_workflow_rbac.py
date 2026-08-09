from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.core.permissions import (
    ensure_workflow_decision_permission,
    ensure_workflow_investigation_permission,
)
from app.core.security import (
    AuthenticatedUser,
)


def user(
    *roles: str,
) -> AuthenticatedUser:
    return AuthenticatedUser(
        subject="rbac-test-user",
        username="rbac-test",
        roles=frozenset(roles),
    )


@pytest.mark.parametrize(
    ("role", "workflow"),
    [
        ("fraud_analyst", "fraud"),
        ("aml_investigator", "aml"),
        ("credit_analyst", "credit"),
        (
            "compliance_officer",
            "compliance",
        ),
    ],
)
def test_specialist_can_investigate_own_workflow(
    role: str,
    workflow: str,
) -> None:
    ensure_workflow_investigation_permission(
        user(role),
        workflow,
    )


@pytest.mark.parametrize(
    ("role", "workflow"),
    [
        ("fraud_analyst", "credit"),
        ("fraud_analyst", "aml"),
        ("credit_analyst", "fraud"),
        ("aml_investigator", "credit"),
        (
            "compliance_officer",
            "fraud",
        ),
    ],
)
def test_specialist_cannot_cross_workflow_boundary(
    role: str,
    workflow: str,
) -> None:
    with pytest.raises(
        HTTPException
    ) as exc:
        ensure_workflow_investigation_permission(
            user(role),
            workflow,
        )

    assert exc.value.status_code == 403


def test_fraud_analyst_cannot_approve_credit_case() -> None:
    with pytest.raises(
        HTTPException
    ) as exc:
        ensure_workflow_decision_permission(
            user("fraud_analyst"),
            "credit",
        )

    assert exc.value.status_code == 403


def test_credit_analyst_can_decide_credit_case() -> None:
    ensure_workflow_decision_permission(
        user("credit_analyst"),
        "credit",
    )


@pytest.mark.parametrize(
    "workflow",
    [
        "fraud",
        "aml",
        "credit",
        "compliance",
    ],
)
def test_platform_admin_can_access_every_workflow(
    workflow: str,
) -> None:
    admin = user(
        "platform_admin"
    )

    ensure_workflow_investigation_permission(
        admin,
        workflow,
    )

    ensure_workflow_decision_permission(
        admin,
        workflow,
    )
