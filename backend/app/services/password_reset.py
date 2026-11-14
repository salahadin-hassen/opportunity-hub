"""Password-reset requests: issue at most one reset email per account per cooldown window.

Every request gets the same answer from the API whatever happens here (unknown account,
inactive account, cooldown, daily cap, full queue, or a new email queued), so callers can't tell
which applied. Protection is per account and per deployment; it never depends on the client
address, which can't be trusted yet (review R-3).

* **Cooldown** (``PASSWORD_RESET_COOLDOWN_SECONDS``, default 15 min): while a reset token issued
  less than this long ago exists, nothing new is queued. The earlier link stays valid for its
  full hour, so a user whose address an attacker keeps submitting still has a working link and
  receives at most one email per window.
* **Daily cap** (``PASSWORD_RESET_DAILY_LIMIT``, default 5 per rolling 24 h).
* **Queue ceiling** (``PASSWORD_RESET_MAX_PENDING``, default 1000 pending reset emails): bounds
  outbound volume if many accounts are targeted at once or the worker is down. Exact under
  concurrency: the count and insert run under a transaction-scoped advisory lock.
* **Concurrency**: the user row is locked ``FOR UPDATE`` so simultaneous requests for one account
  serialise and see each other's token; the outbox ``dedupe_key`` is per account per cooldown
  window as a second guard.
"""
from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta, timezone
from enum import StrEnum

from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import EmailOutbox, EmailToken, User
from app.services import email_tokens

logger = logging.getLogger(__name__)

RESET_TOKEN_TTL = timedelta(hours=1)
#: Advisory-lock key for the global reset-queue ceiling (any fixed 64-bit value unique to this purpose).
RESET_QUEUE_LOCK_KEY = 0x0E4A11_7E5E7_0001


class ResetOutcome(StrEnum):
    """What happened; for tests and metrics only, never shown to the caller."""

    QUEUED = "queued"
    NO_ACCOUNT = "no_account"
    COOLDOWN = "cooldown"
    DAILY_LIMIT = "daily_limit"
    QUEUE_FULL = "queue_full"


def request_password_reset(db: Session, email: str, *, now: datetime | None = None) -> ResetOutcome:
    """Queue a reset email for ``email`` if its account exists, is active and is not throttled."""
    now = now or datetime.now(timezone.utc)
    user = db.scalar(
        select(User)
        .where(func.lower(User.email) == email.strip().lower(), User.is_active.is_(True))
        .order_by(User.created_at, User.id)
        .limit(1)
        .with_for_update()
    )
    if user is None:
        return ResetOutcome.NO_ACCOUNT

    cooldown = timedelta(seconds=settings.PASSWORD_RESET_COOLDOWN_SECONDS)
    recent = db.scalars(
        select(EmailToken.created_at).where(
            EmailToken.user_id == user.id,
            EmailToken.purpose == email_tokens.PASSWORD_RESET,
            EmailToken.created_at > now - timedelta(days=1),
        )
    ).all()
    if any(created > now - cooldown for created in recent):
        return ResetOutcome.COOLDOWN
    if len(recent) >= settings.PASSWORD_RESET_DAILY_LIMIT:
        return ResetOutcome.DAILY_LIMIT

    # Serialise the check-and-insert of the global ceiling across every worker and instance: a
    # transaction-scoped advisory lock, released when the request's transaction ends. Lock order is
    # always user row, then this lock, so concurrent requests can't deadlock.
    db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": RESET_QUEUE_LOCK_KEY})
    pending = db.scalar(
        select(func.count()).select_from(EmailOutbox).where(
            EmailOutbox.template == "password_reset", EmailOutbox.status == "pending"
        )
    )
    if pending >= settings.PASSWORD_RESET_MAX_PENDING:
        logger.warning("Password reset not queued: %d reset emails already pending", pending)
        return ResetOutcome.QUEUE_FULL

    window = math.floor(now.timestamp() / settings.PASSWORD_RESET_COOLDOWN_SECONDS)
    try:
        with db.begin_nested():
            token, key_id = email_tokens.issue(
                db, user_id=user.id, purpose=email_tokens.PASSWORD_RESET, ttl=RESET_TOKEN_TTL, now=now
            )
            db.add(
                EmailOutbox(
                    user_id=user.id,
                    to_address=user.email,
                    template="password_reset",
                    params={"token_id": str(token.id), "key_id": key_id},  # never the token itself
                    dedupe_key=f"reset:{user.id}:{window}",
                    created_at=now,
                )
            )
            db.flush()
    except IntegrityError:
        return ResetOutcome.COOLDOWN  # another request for this account won the same window
    return ResetOutcome.QUEUED
