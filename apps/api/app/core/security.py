from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import (
    HTTPAuthorizationCredentials,
    HTTPBearer,
)
from jwt import PyJWKClient
from jwt.exceptions import (
    InvalidTokenError,
    PyJWTError,
)
from pydantic import BaseModel, Field

from app.core.config import get_settings


class BankingRole(StrEnum):
    FRAUD_ANALYST = "fraud_analyst"
    AML_INVESTIGATOR = "aml_investigator"
    CREDIT_ANALYST = "credit_analyst"
    COMPLIANCE_OFFICER = "compliance_officer"
    EXECUTIVE = "executive"
    PLATFORM_ADMIN = "platform_admin"
    AUDITOR = "auditor"


class AuthenticatedUser(BaseModel):
    subject: str
    username: str
    email: str | None = None

    roles: frozenset[str] = Field(
        default_factory=frozenset,
    )

    def has_role(
        self,
        role: str | BankingRole,
    ) -> bool:
        return str(role) in self.roles


bearer_scheme = HTTPBearer(
    auto_error=False,
    scheme_name="KeycloakBearer",
    description=(
        "Keycloak OIDC access token for FinSentinel AI."
    ),
)


@lru_cache
def get_jwk_client() -> PyJWKClient:
    settings = get_settings()

    return PyJWKClient(
        settings.oidc_jwks_url,
        cache_keys=True,
    )


def decode_access_token(
    token: str,
) -> dict:
    """
    Validate signature, issuer, audience, and token lifetime.
    """

    settings = get_settings()

    try:
        signing_key = (
            get_jwk_client()
            .get_signing_key_from_jwt(token)
        )

        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=settings.jwt_audience,
            issuer=settings.oidc_issuer,
            options={
                "require": [
                    "exp",
                    "iat",
                    "iss",
                    "sub",
                ]
            },
        )

    except (
        InvalidTokenError,
        PyJWTError,
        ValueError,
    ) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token.",
            headers={
                "WWW-Authenticate": "Bearer"
            },
        ) from exc

    return claims


def _extract_roles(
    claims: dict,
) -> frozenset[str]:
    roles: set[str] = set()

    realm_access = claims.get(
        "realm_access",
        {},
    )

    if isinstance(realm_access, dict):
        realm_roles = realm_access.get(
            "roles",
            [],
        )

        if isinstance(realm_roles, list):
            roles.update(
                str(role)
                for role in realm_roles
            )

    resource_access = claims.get(
        "resource_access",
        {},
    )

    if isinstance(resource_access, dict):
        for resource in (
            resource_access.values()
        ):
            if not isinstance(
                resource,
                dict,
            ):
                continue

            client_roles = resource.get(
                "roles",
                [],
            )

            if isinstance(
                client_roles,
                list,
            ):
                roles.update(
                    str(role)
                    for role in client_roles
                )

    return frozenset(roles)


async def get_current_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(bearer_scheme),
    ],
) -> AuthenticatedUser:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
            headers={
                "WWW-Authenticate": "Bearer"
            },
        )

    if (
        credentials.scheme.lower()
        != "bearer"
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer authentication required.",
            headers={
                "WWW-Authenticate": "Bearer"
            },
        )

    claims = decode_access_token(
        credentials.credentials
    )

    username = (
        claims.get("preferred_username")
        or claims.get("email")
        or claims.get("sub")
    )

    return AuthenticatedUser(
        subject=str(claims["sub"]),
        username=str(username),
        email=claims.get("email"),
        roles=_extract_roles(claims),
    )


CurrentUser = Annotated[
    AuthenticatedUser,
    Depends(get_current_user),
]


def require_roles(
    *allowed_roles: BankingRole | str,
):
    """
    Authorize when the authenticated principal has at least
    one of the permitted roles.
    """

    required = frozenset(
        str(role)
        for role in allowed_roles
    )

    async def dependency(
        user: CurrentUser,
    ) -> AuthenticatedUser:
        if not (
            user.roles
            & required
        ):
            raise HTTPException(
                status_code=(
                    status.HTTP_403_FORBIDDEN
                ),
                detail=(
                    "Insufficient permissions for "
                    "this banking operation."
                ),
            )

        return user

    return dependency
