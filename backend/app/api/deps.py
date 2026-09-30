"""Reusable request dependencies for authentication and data access.

Protected endpoints declare `Depends(get_current_user)` (identity) and/or
`Depends(get_user_db)` (RLS-scoped data access) instead of handling tokens
themselves.
"""

import logging

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import Settings, get_settings
from app.core.security import (
    AuthenticatedUser,
    AuthenticationError,
    AuthServiceUnavailable,
    verify_access_token,
)
from app.services.supabase_rest import UserScopedSupabase

logger = logging.getLogger(__name__)

_bearer = HTTPBearer(auto_error=False)

_UNAUTHORIZED_HEADERS = {"WWW-Authenticate": "Bearer"}


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    settings: Settings = Depends(get_settings),
) -> AuthenticatedUser:
    if not settings.supabase_configured:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Authentication is not configured.")

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
            headers=_UNAUTHORIZED_HEADERS,
        )

    try:
        return verify_access_token(credentials.credentials, settings)
    except AuthServiceUnavailable:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Authentication service unavailable."
        ) from None
    except AuthenticationError as exc:
        logger.info("Rejected access token: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Your session is invalid or has expired.",
            headers=_UNAUTHORIZED_HEADERS,
        ) from None


def get_user_db(
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> UserScopedSupabase:
    return UserScopedSupabase(request.app.state.http, settings, user.access_token)
