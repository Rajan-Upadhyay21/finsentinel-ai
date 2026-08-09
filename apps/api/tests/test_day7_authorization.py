from __future__ import annotations

from app.core.permissions import (
    ALL_PERMISSIONS,
    Permission,
    has_permission,
    permissions_for_roles,
)
from app.core.security import AuthenticatedUser


def user_with_roles(
    *roles: str,
) -> AuthenticatedUser:
    return AuthenticatedUser(
        subject="user-test-001",
        username="test-user",
        roles=frozenset(roles),
    )


def test_fraud_analyst_has_fraud_permissions() -> None:
    user = user_with_roles(
        "fraud_analyst"
    )

    assert has_permission(
        user,
        Permission.BANKING_READ,
    )

    assert has_permission(
        user,
        Permission.FRAUD_INVESTIGATE,
    )

    assert has_permission(
        user,
        Permission.FRAUD_DECIDE,
    )


def test_fraud_analyst_cannot_make_credit_decision() -> None:
    user = user_with_roles(
        "fraud_analyst"
    )

    assert not has_permission(
        user,
        Permission.CREDIT_DECIDE,
    )


def test_credit_analyst_cannot_make_fraud_decision() -> None:
    user = user_with_roles(
        "credit_analyst"
    )

    assert has_permission(
        user,
        Permission.CREDIT_INVESTIGATE,
    )

    assert has_permission(
        user,
        Permission.CREDIT_DECIDE,
    )

    assert not has_permission(
        user,
        Permission.FRAUD_DECIDE,
    )


def test_auditor_is_read_only() -> None:
    user = user_with_roles(
        "auditor"
    )

    assert has_permission(
        user,
        Permission.BANKING_READ,
    )

    assert has_permission(
        user,
        Permission.AUDIT_READ,
    )

    assert not has_permission(
        user,
        Permission.FRAUD_DECIDE,
    )

    assert not has_permission(
        user,
        Permission.CREDIT_DECIDE,
    )


def test_executive_has_observability_not_decision_rights() -> None:
    user = user_with_roles(
        "executive"
    )

    assert has_permission(
        user,
        Permission.BANKING_READ,
    )

    assert has_permission(
        user,
        Permission.INVESTIGATION_READ,
    )

    assert not has_permission(
        user,
        Permission.AML_DECIDE,
    )


def test_platform_admin_has_every_permission() -> None:
    user = user_with_roles(
        "platform_admin"
    )

    granted = permissions_for_roles(
        user.roles
    )

    assert granted == ALL_PERMISSIONS


def test_unknown_keycloak_role_grants_nothing() -> None:
    user = user_with_roles(
        "unknown_role"
    )

    assert permissions_for_roles(
        user.roles
    ) == frozenset()


def test_multiple_roles_combine_permissions() -> None:
    user = user_with_roles(
        "fraud_analyst",
        "aml_investigator",
    )

    assert has_permission(
        user,
        Permission.FRAUD_INVESTIGATE,
    )

    assert has_permission(
        user,
        Permission.AML_INVESTIGATE,
    )
