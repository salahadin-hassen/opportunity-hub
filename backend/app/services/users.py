"""Account services: registration and credential verification."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import hash_password, verify_password
from app.models import User
from app.schemas import UserCreate


class EmailAlreadyRegisteredError(Exception):
    """Raised when registration collides with an existing account email."""


def create_user(db: Session, payload: UserCreate) -> User:
    """Create one account with a salted Argon2id password hash.

    The caller owns the transaction (``get_db`` commits after the handler,
    tests roll back), so this only flushes — inside a savepoint, so a
    duplicate email surfaces as one clean conflict instead of poisoning the
    request transaction.
    """
    user = User(
        email=payload.email,
        password_hash=hash_password(payload.password),
        is_active=True,
    )
    try:
        with db.begin_nested():
            db.add(user)
            db.flush()
    except IntegrityError as error:
        raise EmailAlreadyRegisteredError from error
    return user


def authenticate_user(db: Session, email: str, password: str) -> User | None:
    """Return the active account whose credentials match, else ``None``.

    Unknown email, wrong password and deactivated account are deliberately
    indistinguishable here, so the HTTP layer maps all three to one generic
    401 without ever learning which check failed.
    """
    user = db.scalar(select(User).where(User.email == email))
    if user is None or not user.is_active:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user
