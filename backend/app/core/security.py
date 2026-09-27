"""Local password hashing and signed JWT identity tokens.

Only symmetric signing with the configured ``JWT_SECRET`` is used; token
format, claims and verification stay in this module so routers never deal
with token internals directly.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core.config import settings

ACCESS_TOKEN_TTL = timedelta(minutes=30)
SUBJECT_CLAIM = "sub"

_password_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    """Hash a password with Argon2id; the hash is one-way and salted by the library."""
    return _password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Return whether ``password`` matches ``password_hash``."""
    try:
        return _password_hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def create_access_token(user_id: uuid.UUID, *, ttl: timedelta = ACCESS_TOKEN_TTL) -> str:
    """Sign a short-lived bearer token that names exactly one user."""
    issued_at = datetime.now(timezone.utc)
    payload = {
        SUBJECT_CLAIM: str(user_id),
        "iat": issued_at,
        "exp": issued_at + ttl,
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> uuid.UUID | None:
    """Resolve a signed token to its user id.

    Returns ``None`` for any unverifiable input — wrong signature, wrong
    algorithm, expired, missing or malformed subject — so callers can treat
    every failure identically without learning why the token failed.
    """
    try:
        payload = jwt.decode(
            token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM]
        )
    except jwt.PyJWTError:
        return None
    subject = payload.get(SUBJECT_CLAIM)
    if not isinstance(subject, str):
        return None
    try:
        return uuid.UUID(subject)
    except ValueError:
        return None
