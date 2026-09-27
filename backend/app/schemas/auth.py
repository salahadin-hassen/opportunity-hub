"""Request and response schemas for the authentication endpoints."""
from __future__ import annotations

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
    """One signed bearer token; carries no user data or secret material."""

    access_token: str
    token_type: str = "bearer"


__all__ = ["UserCreate", "UserLogin", "TokenResponse"]
