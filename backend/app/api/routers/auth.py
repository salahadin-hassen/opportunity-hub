"""Registration and login HTTP endpoints.

Two temporary refusals are distinct from credential outcomes: a 503 when
every Argon2 slot in the process is busy (no hashing is done, nothing about
the account is revealed), and a 503 when the database can't be reached
for the account lookup. Neither is ever reported as a 401 or a 409.
"""
from __future__ import annotations

import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError
from sqlalchemy.orm import Session

from app.api.deps import SESSION_COOKIE_NAME, get_current_user, unauthorized
from app.core import auth_telemetry
from app.core.config import settings
from app.core.rate_limit import (
    STORE_UNAVAILABLE_RETRY_AFTER,
    limit_account_attempts,
    limit_auth_attempts,
    record_auth_failure,
    record_auth_success,
)
from app.core.security import PasswordHashCapacityExceeded, hash_password
from app.db.session import get_db
from app.models import EmailOutbox, EmailToken, Session as SessionModel, User
from app.schemas.auth import (
    ForgotPasswordRequest,
    ResetPasswordRequest,
    SessionRead,
    TokenResponse,
    UserCreate,
    UserLogin,
    VerifyEmailRequest,
)
from app.schemas.user import UserRead
from app.services import audit
from app.services.sessions import (
    create_session,
    hash_token,
    list_user_sessions,
    revoke_all_user_sessions,
    revoke_session_by_id,
    revoke_session_by_token,
)
from app.services.users import (
    EmailAlreadyRegisteredError,
    authenticate_user,
    create_user,
)

router = APIRouter(prefix="/auth", tags=["auth"], dependencies=[Depends(limit_auth_attempts)])
logger = logging.getLogger(__name__)

#: Seconds a client should wait after a capacity refusal; Argon2 runs take well under a second.
HASH_CAPACITY_RETRY_AFTER = 2
#: Database errors that mean "unreachable or too slow", not a bug in the query.
_DATABASE_UNAVAILABLE = (OperationalError, PoolTimeoutError)


def _hash_capacity_exhausted(endpoint: str, operation: str, error: PasswordHashCapacityExceeded) -> HTTPException:
    # ``limit`` says which ceiling refused: the process-wide total, or registration's share of it.
    auth_telemetry.record(
        "password_hash_capacity_exhausted", level=logging.WARNING,
        endpoint=endpoint, operation=operation, limit=error.limit,
    )
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="The service is busy. Please try again in a moment.",
        headers={"Retry-After": str(HASH_CAPACITY_RETRY_AFTER)},
    )


def _database_unavailable(endpoint: str) -> HTTPException:
    logger.warning("Account lookup failed: database unavailable on %s", endpoint)
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Sign-in is temporarily unavailable. Please try again shortly.",
        headers={"Retry-After": str(STORE_UNAVAILABLE_RETRY_AFTER)},
    )


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def register(payload: UserCreate, db: Session = Depends(get_db)) -> UserRead:
    """Create one account, or report the email conflict as a 409."""
    limit_account_attempts("/auth/register", payload.email)
    try:
        user = create_user(db, payload)
    except PasswordHashCapacityExceeded as error:
        raise _hash_capacity_exhausted("/auth/register", "hash", error) from None
    except _DATABASE_UNAVAILABLE:
        raise _database_unavailable("/auth/register") from None
    except EmailAlreadyRegisteredError as error:
        record_auth_failure("/auth/register")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        ) from error
    return user


@router.post("/login", response_model=TokenResponse)
def login(
    payload: UserLogin,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> TokenResponse:
    """Exchange valid credentials for a short-lived bearer access token and session."""
    limit_account_attempts("/auth/login", payload.email)
    try:
        user = authenticate_user(db, payload.email, payload.password)
    except PasswordHashCapacityExceeded as error:
        raise _hash_capacity_exhausted("/auth/login", "verify", error) from None
    except _DATABASE_UNAVAILABLE:
        raise _database_unavailable("/auth/login") from None
    if user is None:
        record_auth_failure("/auth/login")
        raise unauthorized()
    record_auth_success(request, "/auth/login", payload.email)

    session_row, raw_token = create_session(
        db=db,
        user_id=user.id,
        user_agent=request.headers.get("user-agent", "")[:255] or None,
        client_ip=request.client.host if request.client else None,
        ttl=timedelta(minutes=30),
    )

    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=raw_token,
        httponly=True,
        secure=(settings.APP_ENV == "production"),
        samesite="lax",
        max_age=1800,
        path="/",
    )
    return TokenResponse(access_token=raw_token)


@router.post("/logout", status_code=status.HTTP_200_OK)
def logout(
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    """Revoke the current session and clear session cookies."""
    raw_token: str | None = None
    auth_header = request.headers.get("authorization")
    if auth_header and auth_header.lower().startswith("bearer "):
        raw_token = auth_header[7:].strip()
    elif SESSION_COOKIE_NAME in request.cookies:
        raw_token = request.cookies[SESSION_COOKIE_NAME]

    if raw_token:
        revoke_session_by_token(db, raw_token)

    response.delete_cookie(key=SESSION_COOKIE_NAME, path="/")
    return {"status": "ok"}


@router.get("/sessions", response_model=list[SessionRead])
def list_sessions(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[SessionRead]:
    """List active sessions for the current user."""
    sessions = list_user_sessions(db, current_user.id)
    current_raw = None
    auth_header = request.headers.get("authorization")
    if auth_header and auth_header.lower().startswith("bearer "):
        current_raw = auth_header[7:].strip()
    elif SESSION_COOKIE_NAME in request.cookies:
        current_raw = request.cookies[SESSION_COOKIE_NAME]
    current_hash = hash_token(current_raw) if current_raw else None

    return [
        SessionRead(
            id=s.id,
            created_at=s.created_at,
            last_seen_at=s.last_seen_at,
            user_agent=s.user_agent,
            is_current=(s.token_hash == current_hash),
        )
        for s in sessions
    ]


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_session(
    session_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    """Revoke a specific active session."""
    revoked = revoke_session_by_id(db, current_user.id, session_id)
    if not revoked:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/forgot-password", status_code=status.HTTP_200_OK)
def forgot_password(
    payload: ForgotPasswordRequest,
    db: Session = Depends(get_db),
) -> dict[str, str]:
    """Initiate a password reset flow.
    
    Always returns success to prevent user email enumeration.
    """
    limit_account_attempts("/auth/forgot-password", payload.email)
    user = db.scalar(select(User).where(func.lower(User.email) == payload.email.lower()))
    if user is not None and user.is_active:
        token = secrets.token_urlsafe(32)
        now = datetime.now(timezone.utc)
        email_token = EmailToken(
            user_id=user.id,
            purpose="reset_password",
            token_hash=hash_token(token),
            created_at=now,
            expires_at=now + timedelta(hours=1),
        )
        db.add(email_token)
        outbox = EmailOutbox(
            user_id=user.id,
            to_address=user.email,
            template="password_reset",
            params={"token": token},
            dedupe_key=f"reset:{user.id}:{int(now.timestamp())}",
            created_at=now,
        )
        db.add(outbox)
        db.flush()

    return {"status": "ok", "message": "If this email is registered, instructions have been sent."}


@router.post("/reset-password", status_code=status.HTTP_200_OK)
def reset_password(
    payload: ResetPasswordRequest,
    db: Session = Depends(get_db),
) -> dict[str, str]:
    """Complete a password reset with a valid token."""
    now = datetime.now(timezone.utc)
    token_digest = hash_token(payload.token)
    stmt = select(EmailToken).where(
        EmailToken.purpose == "reset_password",
        EmailToken.token_hash == token_digest,
        EmailToken.used_at.is_(None),
        EmailToken.expires_at > now,
    )
    email_token = db.scalar(stmt)
    if email_token is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired password reset token.",
        )

    user = db.get(User, email_token.user_id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired password reset token.",
        )

    try:
        user.password_hash = hash_password(payload.new_password)
    except PasswordHashCapacityExceeded as error:
        raise _hash_capacity_exhausted("/auth/reset-password", "hash", error) from None

    email_token.used_at = now
    revoke_all_user_sessions(db, user.id)
    audit.record(
        db,
        action="user.password_reset",
        target_type="user",
        target_id=user.id,
        actor_id=user.id,
    )
    db.flush()
    return {"status": "ok", "message": "Password has been successfully reset."}


@router.post("/verify-email", status_code=status.HTTP_200_OK)
def verify_email(
    payload: VerifyEmailRequest,
    db: Session = Depends(get_db),
) -> dict[str, str]:
    """Verify an email address with a single-use token."""
    now = datetime.now(timezone.utc)
    token_digest = hash_token(payload.token)
    stmt = select(EmailToken).where(
        EmailToken.purpose == "verify_email",
        EmailToken.token_hash == token_digest,
        EmailToken.used_at.is_(None),
        EmailToken.expires_at > now,
    )
    email_token = db.scalar(stmt)
    if email_token is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification token.",
        )

    user = db.get(User, email_token.user_id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification token.",
        )

    user.email_verified_at = now
    email_token.used_at = now
    audit.record(
        db,
        action="user.email_verified",
        target_type="user",
        target_id=user.id,
        actor_id=user.id,
    )
    db.flush()
    return {"status": "ok", "message": "Email has been successfully verified."}
