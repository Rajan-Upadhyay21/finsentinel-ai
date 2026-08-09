from __future__ import annotations

import inspect

from app.api.routes.banking import (
    ApprovalReviewRequest,
    investigate_stored_transaction,
    review_approval,
)
from app.core.audit_identity import (
    principal_audit_details,
)
from app.core.security import (
    AuthenticatedUser,
)


def authenticated_user() -> AuthenticatedUser:
    return AuthenticatedUser(
        subject="kc-subject-123",
        username="fraud.analyst",
        email="fraud@example.test",
        roles=frozenset(
            {
                "fraud_analyst",
                "auditor",
            }
        ),
    )


def test_audit_identity_comes_from_authenticated_principal() -> None:
    details = principal_audit_details(
        authenticated_user()
    )

    assert details["subject"] == (
        "kc-subject-123"
    )

    assert details["username"] == (
        "fraud.analyst"
    )

    assert details["roles"] == [
        "auditor",
        "fraud_analyst",
    ]

    assert details["identity_provider"] == (
        "keycloak"
    )

    assert details["authentication"] == (
        "oidc_jwt"
    )


def test_reviewer_id_is_not_required_from_client() -> None:
    payload = ApprovalReviewRequest(
        approved=True,
        reviewer_comment="Reviewed.",
    )

    assert payload.reviewer_id is None


def test_human_approval_uses_verified_identity() -> None:
    source = inspect.getsource(
        review_approval
    )

    assert (
        "approval.reviewer_id = "
        "current_user.username"
        in source
    )

    assert (
        "actor_id=current_user.subject"
        in source
    )

    assert (
        "authenticated_principal"
        in source
    )


def test_agent_audit_records_authenticated_initiator() -> None:
    source = inspect.getsource(
        investigate_stored_transaction
    )

    assert "initiated_by" in source

    assert (
        "principal_audit_details("
        in source
    )
