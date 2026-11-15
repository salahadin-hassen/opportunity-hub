"""Server-side session management service (plan §C.2, M1b)."""
from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import Session as DbSession

from app.models.session import Session as SessionModel
from app.models.user import User

DEFAULT_SESSION_TTL = timedelta(days=30)
TOUCH_INTERVAL = timedelta(minutes=5)


def hash_token(raw_token: str) -> str:
    """Return the SHA-256 digest of a raw session token."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def create_session(
    db: DbSession,
    user_id: uuid.UUID,
    user_agent: str | None = None,
    client_ip: str | None = None,
    ttl: timedelta = DEFAULT_SESSION_TTL,
) -> tuple[SessionModel, str]:
    """Create a new server-side session. Returns the persisted row and the raw token."""
    raw_token = secrets.token_urlsafe(32)
    token_hash = hash_token(raw_token)
    now = datetime.now(timezone.utc)

    session = SessionModel(
        user_id=user_id,
        token_hash=token_hash,
        created_at=now,
        last_seen_at=now,
        expires_at=now + ttl,
        user_agent=user_agent[:255] if user_agent else None,
        client_ip=client_ip[:64] if client_ip else None,
    )
    db.add(session)
    db.flush()
    return session, raw_token


def resolve_session(db: DbSession, raw_token: str) -> User | None:
    """Find the active User corresponding to a raw token, or None if expired/revoked."""
    token_hash = hash_token(raw_token)
    now = datetime.now(timezone.utc)

    stmt = select(SessionModel).where(
        SessionModel.token_hash == token_hash,
        SessionModel.revoked_at.is_(None),
        SessionModel.expires_at > now,
    )
    session = db.scalar(stmt)
    if session is None or session.user is None or not session.user.is_active:
        return None

    # Update last_seen_at periodically without writing on every sub-millisecond request
    if now - session.last_seen_at > TOUCH_INTERVAL:
        session.last_seen_at = now
        db.flush()

    return session.user


def revoke_session_by_token(db: DbSession, raw_token: str) -> bool:
    """Revoke a session matching the raw token."""
    token_hash = hash_token(raw_token)
    now = datetime.now(timezone.utc)
    stmt = (
        update(SessionModel)
        .where(SessionModel.token_hash == token_hash, SessionModel.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    result = db.execute(stmt)
    db.flush()
    return result.rowcount > 0


def revoke_session_by_id(db: DbSession, user_id: uuid.UUID, session_id: uuid.UUID) -> bool:
    """Revoke a specific session owned by user_id."""
    now = datetime.now(timezone.utc)
    stmt = (
        update(SessionModel)
        .where(
            SessionModel.id == session_id,
            SessionModel.user_id == user_id,
            SessionModel.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )
    result = db.execute(stmt)
    db.flush()
    return result.rowcount > 0


def revoke_all_user_sessions(db: DbSession, user_id: uuid.UUID) -> int:
    """Revoke all active sessions for a user."""
    now = datetime.now(timezone.utc)
    stmt = (
        update(SessionModel)
        .where(SessionModel.user_id == user_id, SessionModel.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    result = db.execute(stmt)
    db.flush()
    return result.rowcount


def list_user_sessions(db: DbSession, user_id: uuid.UUID) -> list[SessionModel]:
    """List all active non-expired sessions for user_id."""
    now = datetime.now(timezone.utc)
    stmt = (
        select(SessionModel)
        .where(
            SessionModel.user_id == user_id,
            SessionModel.revoked_at.is_(None),
            SessionModel.expires_at > now,
        )
        .order_by(SessionModel.last_seen_at.desc())
    )
    return list(db.scalars(stmt).all())

