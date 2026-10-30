"""Reusable authentication and ownership dependencies for protected routes.

Routers compose these building blocks instead of repeating token parsing or
the ``current_user.id == profile.user_id`` comparison themselves.
"""
from __future__ import annotations

import secrets
import uuid

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import decode_access_token
from app.db.session import get_db
from app.models import Profile, User
from app.services.profiles import get_profile_for_user

bearer_token = HTTPBearer(auto_error=False)

INVALID_CREDENTIALS_DETAIL = "Could not validate credentials."
PROFILE_FORBIDDEN_DETAIL = "You do not have access to this profile."
ADMIN_FORBIDDEN_DETAIL = "Curator access is required."


def require_admin_token(
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
) -> None:
    """Allow curator-only writes when the shared ``ADMIN_API_TOKEN`` matches.

    With no token configured the endpoint is disabled for everyone. Missing,
    wrong and disabled cases share one 403 so callers learn nothing about
    which check failed; the comparison is constant-time.
    """
    expected = settings.ADMIN_API_TOKEN
    if (
        not expected
        or x_admin_token is None
        or not secrets.compare_digest(x_admin_token.encode(), expected.encode())
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=ADMIN_FORBIDDEN_DETAIL
        )


def unauthorized() -> HTTPException:
    """The single 401 shape: generic detail, no token internals.

    Shared by the bearer dependency and the login endpoint so every
    authentication failure is byte-for-byte identical.
    """
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=INVALID_CREDENTIALS_DETAIL,
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_token),
    db: Session = Depends(get_db),
) -> User:
    """Resolve the bearer token to the active User it names.

    Missing, malformed, expired, forged or unknown tokens and deactivated
    accounts all fail with the same 401, so responses never reveal which
    check failed or anything about the submitted token.
    """
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise unauthorized()
    user_id = decode_access_token(credentials.credentials)
    if user_id is None:
        raise unauthorized()
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise unauthorized()
    return user


def get_my_profile(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Profile:
    """Resolve the authenticated user's own profile, or 404 when none exists yet.

    Shared by the ``/me/profile`` child routes so the ownership chain
    ``current_user -> owned Profile`` is expressed exactly once.
    """
    profile = get_profile_for_user(db, current_user.id)
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found."
        )
    return profile


def get_owned_profile(
    profile_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Profile:
    """Load a profile only when the authenticated user owns it.

    Knowing a profile UUID is never sufficient authorization: the single
    ownership comparison lives here, so every router gets it for free.
    Profiles without an owner (legacy rows) are not accessible to anyone
    until they are claimed.
    """
    profile = db.get(Profile, profile_id)
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found."
        )
    if profile.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=PROFILE_FORBIDDEN_DETAIL,
        )
    return profile
