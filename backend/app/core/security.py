"""Verification of Supabase Auth access tokens.

Supabase is the only identity provider. The backend never issues tokens; it
only verifies the ones Supabase issued and extracts the caller's identity.
"""

import logging
import uuid
from dataclasses import dataclass
from functools import lru_cache

import jwt
from jwt import PyJWKClient

from app.core.config import Settings

logger = logging.getLogger(__name__)

AUDIENCE = "authenticated"
ASYMMETRIC_ALGORITHMS = ["ES256", "RS256"]
# Tolerates small clock differences with Supabase; without it a token issued a
# fraction of a second "in the future" fails the iat check and logs the user out.
CLOCK_SKEW_LEEWAY_SECONDS = 30


class AuthenticationError(Exception):
    """The request carries no usable identity (maps to 401)."""


class AuthServiceUnavailable(Exception):
    """Token keys could not be fetched from Supabase (maps to 503)."""


@dataclass(frozen=True)
class AuthenticatedUser:
    id: uuid.UUID
    email: str | None
    access_token: str


@lru_cache
def _jwks_client(jwks_url: str) -> PyJWKClient:
    return PyJWKClient(jwks_url, cache_keys=True, lifespan=600)


def _signing_key(token: str, algorithm: str, settings: Settings):
    if algorithm == "HS256":
        if not settings.supabase_jwt_secret:
            raise AuthenticationError("HS256 tokens are not accepted by this deployment.")
        return settings.supabase_jwt_secret

    if algorithm not in ASYMMETRIC_ALGORITHMS:
        raise AuthenticationError(f"Unsupported token algorithm: {algorithm}")

    try:
        return _jwks_client(f"{settings.supabase_auth_issuer}/.well-known/jwks.json").get_signing_key_from_jwt(token).key
    except jwt.PyJWKClientConnectionError as exc:
        raise AuthServiceUnavailable() from exc
    except jwt.PyJWKClientError as exc:
        raise AuthenticationError("Token signing key not recognised.") from exc


def verify_access_token(token: str, settings: Settings) -> AuthenticatedUser:
    try:
        algorithm = jwt.get_unverified_header(token).get("alg", "")
    except jwt.PyJWTError as exc:
        raise AuthenticationError("Malformed token.") from exc

    key = _signing_key(token, algorithm, settings)

    try:
        claims = jwt.decode(
            token,
            key,
            algorithms=[algorithm],
            audience=AUDIENCE,
            issuer=settings.supabase_auth_issuer,
            leeway=CLOCK_SKEW_LEEWAY_SECONDS,
            options={"require": ["exp", "sub", "aud", "iss"]},
        )
    except jwt.PyJWTError as exc:
        raise AuthenticationError(f"Token rejected: {exc}") from exc

    if claims.get("role") != AUDIENCE:
        raise AuthenticationError("Token does not belong to an authenticated user.")

    try:
        user_id = uuid.UUID(claims["sub"])
    except ValueError as exc:
        raise AuthenticationError("Token subject is not a user id.") from exc

    return AuthenticatedUser(id=user_id, email=claims.get("email"), access_token=token)
