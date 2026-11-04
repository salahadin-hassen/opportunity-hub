"""Registration and login HTTP endpoints.

Two temporary refusals are distinct from credential outcomes: a 503 when
every Argon2 slot in the process is busy (no hashing is done, nothing about
the account is revealed), and a 503 when the database can't be reached
for the account lookup. Neither is ever reported as a 401 or a 409.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.exc import OperationalError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError
from sqlalchemy.orm import Session

from app.api.deps import unauthorized
from app.core import auth_telemetry
from app.core.rate_limit import (
    STORE_UNAVAILABLE_RETRY_AFTER,
    limit_account_attempts,
    limit_auth_attempts,
    record_auth_failure,
    record_auth_success,
)
from app.core.security import PasswordHashCapacityExceeded, create_access_token
from app.db.session import get_db
from app.schemas import TokenResponse, UserCreate, UserLogin, UserRead
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
def login(payload: UserLogin, request: Request, db: Session = Depends(get_db)) -> TokenResponse:
    """Exchange valid credentials for a short-lived bearer access token."""
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
    return TokenResponse(access_token=create_access_token(user.id))
