"""Request and response schemas for the authentication endpoints."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 128


class UserCreate(BaseModel):
    """Registration payload: exactly the fields an account needs.

    Unknown fields are rejected rather than silently dropped, so nothing a
    client sends (ids, password hashes, flags) can ever end up in a response.
    """

    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str = Field(min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH)


class UserLogin(BaseModel):
    """Credential payload for token exchange.

    The password is unconstrained on purpose: any wrong password must fail
    with the same generic 401 as an unknown email, never with a 422 that
    would reveal the registration policy.
    """

    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    """One signed bearer token or opaque session token."""

    access_token: str
    token_type: str = "bearer"


class SessionRead(BaseModel):
    """Active server session details."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
    last_seen_at: datetime
    user_agent: str | None = None
    is_current: bool = False


class ForgotPasswordRequest(BaseModel):
    """Password reset request."""

    model_config = ConfigDict(extra="forbid")

    email: EmailStr


class ResetPasswordRequest(BaseModel):
    """Password reset completion."""

    model_config = ConfigDict(extra="forbid")

    token: str
    new_password: str = Field(min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH)


class VerifyEmailRequest(BaseModel):
    """Email verification token submission."""

    model_config = ConfigDict(extra="forbid")

    token: str


__all__ = [
    "UserCreate",
    "UserLogin",
    "TokenResponse",
    "SessionRead",
    "ForgotPasswordRequest",
    "ResetPasswordRequest",
    "VerifyEmailRequest",
]
