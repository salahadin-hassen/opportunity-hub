"""Reusable authentication and ownership dependencies for protected routes.

Routers compose these building blocks instead of repeating token parsing or
the ``current_user.id == profile.user_id`` comparison themselves.
"""
from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any
from urllib.parse import urlsplit

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.permissions import Permission, has_permission
from app.core.security import decode_access_token
from app.db.session import get_db
from app.models import Profile, User
from app.services.profiles import get_profile_for_user
from app.services.sessions import resolve_session

SESSION_COOKIE_NAME = "oh_session"

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


def _origin_of(value: str) -> str | None:
    """``scheme://host[:port]`` of an Origin or Referer value, or None if it isn't a plain web origin.

    Lower-cases the scheme and host and drops the scheme's default port, so equivalent spellings
    compare equal. Values with user info, a non-http(s) scheme, no host or an invalid port give None.
    """
    try:
        parts = urlsplit(value.strip())
        port = parts.port
    except ValueError:
        return None
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return None
    if parts.username is not None or parts.password is not None:
        return None
    default = 443 if parts.scheme == "https" else 80
    return f"{parts.scheme}://{parts.hostname.lower()}" + ("" if port in (None, default) else f":{port}")


class _DummyRequest:
    cookies: dict[str, str] = {}
    method: str = "GET"
    headers: dict[str, str] = {}


_DEFAULT_REQUEST: Any = _DummyRequest()


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_token),
    db: Session = Depends(get_db, scope="function"),
    request: Request = _DEFAULT_REQUEST,
) -> User:
    """Resolve the active User from bearer credentials or a secure session cookie.

    Missing, malformed, expired, forged or unknown tokens and deactivated
    accounts all fail with the same 401, so responses never reveal which
    check failed or anything about the submitted token.
    """
    raw_token: str | None = None
    is_cookie_auth = False

    if credentials is not None and getattr(credentials, "scheme", "").lower() == "bearer":
        raw_token = credentials.credentials
    elif hasattr(request, "cookies") and SESSION_COOKIE_NAME in request.cookies:
        raw_token = request.cookies[SESSION_COOKIE_NAME]
        is_cookie_auth = True

    if not raw_token:
        raise unauthorized()

    # CSRF protection for cookie-authenticated mutating requests.
    # Ambient cookie authority requires an explicit, trusted origin. Always execute for
    # cookie-authenticated mutating requests, rejecting when:
    # - Origin and Referer are both missing
    # - The supplied origin cannot be parsed
    # - The configured allowlist is empty or contains no valid origins
    # - The supplied origin does not match an allowed origin
    if is_cookie_auth and getattr(request, "method", "") in ("POST", "PUT", "PATCH", "DELETE"):
        origin = request.headers.get("origin") or request.headers.get("referer")
        request_origin = _origin_of(origin) if origin else None
        allowed = {_origin_of(item) for item in settings.cors_origins} - {None}
        if not allowed or request_origin is None or request_origin not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="CSRF validation failed.",
            )

    # 1. Check opaque server session first
    user = resolve_session(db, raw_token)
    if user is not None:
        return user

    # Browser authentication strictly requires an active opaque session.
    # Obsolete browser JWT fallback is disabled to ensure sessions are revocable server-side.
    if is_cookie_auth:
        raise unauthorized()

    # 2. Check if this token was recorded as a session and explicitly revoked
    from app.services.sessions import hash_token
    from app.models.session import Session as SessionModel
    from sqlalchemy import select

    token_hash = hash_token(raw_token)
    revoked_session = db.scalar(
        select(SessionModel).where(
            SessionModel.token_hash == token_hash,
            SessionModel.revoked_at.is_not(None),
        )
    )
    if revoked_session is not None:
        raise unauthorized()

    # 3. Fall back to signed JWT access token for backwards compatibility
    user_id = decode_access_token(raw_token)
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
    db: Session = Depends(get_db, scope="function"),
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
    db: Session = Depends(get_db, scope="function"),
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
