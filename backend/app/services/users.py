"""Account services: registration and credential verification."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import check_password_hash_capacity, hash_password, verify_password
from app.models import User
from app.schemas import UserCreate


class EmailAlreadyRegisteredError(Exception):
    """Raised when registration collides with an existing account email."""


def create_user(db: Session, payload: UserCreate) -> User:
    """Create one account with a salted Argon2id password hash.

    A known email is rejected before any hashing, so repeated conflicts cost
    one indexed lookup instead of an Argon2 run. The lookup compares exactly
    the value the unique constraint compares (``payload.email`` as the schema
    normalised it), and the constraint stays the final authority: two
    concurrent registrations can both pass the lookup, and the loser's insert
    then fails inside the savepoint.

    The caller owns the transaction (``get_db`` commits after the handler,
    tests roll back), so this only flushes — inside a savepoint, so a
    duplicate email surfaces as one clean conflict instead of poisoning the
    request transaction.
    """
    if db.scalar(select(User.id).where(User.email == payload.email)) is not None:
        raise EmailAlreadyRegisteredError
    user = User(
        email=payload.email,
        password_hash=hash_password(payload.password, purpose="registration"),
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

    Before the lookup, login asks whether it *could* get an Argon2 slot, without
    reserving one. A saturated service is therefore refused the same way for
    known and unknown emails
    (:class:`~app.core.security.PasswordHashCapacityExceeded`), and an unknown
    email never holds capacity while its lookup runs. The slot itself is taken
    only around the verification. If the service fills up between the check
    and the verification, a known email can still be refused there; that
    window is a lookup long, and the signal is far weaker than the existing
    timing difference (unknown emails skip Argon2).
    """
    check_password_hash_capacity("login")
    user = db.scalar(select(User).where(User.email == email))
    if user is None or not user.is_active:
        return None
    if not verify_password(password, user.password_hash, purpose="login"):
        return None
    return user
