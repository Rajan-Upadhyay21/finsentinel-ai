from __future__ import annotations

from app.core.security import AuthenticatedUser


def principal_audit_details(
    user: AuthenticatedUser,
) -> dict[str, object]:
    """
    Return security-safe identity metadata derived from the
    already-verified Keycloak access token.

    Never trust caller-provided reviewer identity for audit attribution.
    """

    return {
        "subject": user.subject,
        "username": user.username,
        "email": user.email,
        "roles": sorted(user.roles),
        "identity_provider": "keycloak",
        "authentication": "oidc_jwt",
    }
