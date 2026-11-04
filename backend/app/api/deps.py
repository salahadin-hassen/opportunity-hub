"""Reusable authentication and ownership dependencies for protected routes.

Routers compose these building blocks instead of repeating token parsing or
the ``current_user.id == profile.user_id`` comparison themselves.
"""
from __future__ import annotations

import uuid
from collections.abc import Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.permissions import Permission, has_permission
from app.core.security import decode_access_token
from app.db.session import get_db
from app.models import Profile, User
from app.services.profiles import get_profile_for_user

bearer_token = HTTPBearer(auto_error=False)

INVALID_CREDENTIALS_DETAIL = "Could not validate credentials."
PROFILE_FORBIDDEN_DETAIL = "You do not have access to this profile."
PERMISSION_FORBIDDEN_DETAIL = "You do not have permission for this action."


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


def require_permission(permission: Permission) -> Callable[..., User]:
    """Dependency factory: the authenticated user, if their stored role grants ``permission``.

    The role is read from the ``users`` row loaded for this request, never
    from the token or the request, so a demotion takes effect on the next
    request. Unauthenticated callers get the usual 401; authenticated ones
    without the permission get one generic 403.
    """

    def dependency(current_user: User = Depends(get_current_user)) -> User:
        if not has_permission(current_user.role, permission):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=PERMISSION_FORBIDDEN_DETAIL)
        return current_user

    dependency.__name__ = f"require_{permission.value.replace('.', '_')}"
    return dependency


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
