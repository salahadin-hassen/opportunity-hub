"""Single-use email tokens (password reset, email verification) that are never stored in the clear.

Storage:

* ``email_tokens.token_hash`` holds ``sha256(token)``; requests are validated against it alone.
* ``email_outbox.params`` holds ``{"token_id": <row id>, "key_id": <key version>}``, never the token.

The raw token is ``HMAC(key[key_id], purpose:token_id)``. Keys come from ``EMAIL_TOKEN_KEYS``, a
dedicated, versioned setting independent of ``JWT_SECRET``. New tokens use
``EMAIL_TOKEN_ACTIVE_KEY``; the worker rebuilds each queued token with the key version recorded in
the outbox row, and sends it only if it hashes to the stored ``token_hash``. Otherwise (key version
removed, or a mismatch), the email is cancelled, never sent with a dead link.

Rotation policy:

* Add the new key, make it active, keep the old one listed. Queued emails still use the old one.
* Remove the old key once ``python -m app.cli email-token-key-usage`` reports no live pending email
  under it (at most the token lifetime, 1 hour, after rotation).
* **Already-delivered links are not affected by rotation**: validation never uses the key, so a
  delivered link keeps working until it expires (1 hour) or is used. To kill outstanding links
  (e.g. a mailbox or database compromise), run ``python -m app.cli revoke-reset-tokens``.

A read-only copy of the database alone yields no usable token; reconstructing one also needs the key.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import uuid
from collections import Counter
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import EmailOutbox, EmailToken
from app.services.sessions import hash_token

PASSWORD_RESET = "reset_password"
VERIFY_EMAIL = "verify_email"
#: Outbox templates whose token is rebuilt from ``params`` at delivery time.
TEMPLATE_PURPOSES = {"password_reset": PASSWORD_RESET, "email_verification": VERIFY_EMAIL}
_DERIVATION_LABEL = b"opportunity-hub/email-token/v2"


class EmailTokenKeyUnavailable(RuntimeError):
    """No usable key: delivery is misconfigured or the key version was removed."""


def _key(key_id: str) -> bytes:
    secret = settings.email_token_keys.get(key_id)
    if secret is None:
        raise EmailTokenKeyUnavailable(f"email token key {key_id!r} is not configured")
    return hmac.new(secret, _DERIVATION_LABEL, hashlib.sha256).digest()


def active_key_id() -> str:
    key_id = (settings.EMAIL_TOKEN_ACTIVE_KEY or "").strip()
    if not key_id or key_id not in settings.email_token_keys:
        raise EmailTokenKeyUnavailable("EMAIL_TOKEN_ACTIVE_KEY is not configured")
    return key_id


def derive_token(token_id: uuid.UUID, purpose: str, key_id: str) -> str:
    """The raw token for one ``email_tokens`` row under one key version (43 URL-safe characters)."""
    digest = hmac.new(_key(key_id), f"{purpose}:{token_id}".encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def issue(
    db: Session, *, user_id: uuid.UUID, purpose: str, ttl: timedelta, now: datetime | None = None
) -> tuple[EmailToken, str]:
    """Add a token row (hash only) under the active key; return it and the key id to queue with it."""
    now = now or datetime.now(timezone.utc)
    key_id = active_key_id()
    token_id = uuid.uuid4()
    row = EmailToken(
        id=token_id,
        user_id=user_id,
        purpose=purpose,
        token_hash=hash_token(derive_token(token_id, purpose, key_id)),
        created_at=now,
        expires_at=now + ttl,
    )
    db.add(row)
    return row, key_id


def consume(db: Session, raw_token: str, purpose: str, *, now: datetime | None = None) -> EmailToken | None:
    """Lock and return the live token matching ``raw_token``, or None if unknown, used or expired.

    ``FOR UPDATE`` serialises concurrent attempts on the same token: the second one waits, then
    re-checks ``used_at`` (set by the first) and gets None. The caller marks it used.
    """
    now = now or datetime.now(timezone.utc)
    return db.scalar(
        select(EmailToken)
        .where(
            EmailToken.purpose == purpose,
            EmailToken.token_hash == hash_token(raw_token),
            EmailToken.used_at.is_(None),
            EmailToken.expires_at > now,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )


def revoke_outstanding(db: Session, user_id: uuid.UUID | None, purpose: str, *, now: datetime | None = None) -> int:
    """Mark unused tokens of this purpose as used, for one user or (``user_id=None``) everyone."""
    now = now or datetime.now(timezone.utc)
    statement = update(EmailToken).where(EmailToken.purpose == purpose, EmailToken.used_at.is_(None))
    if user_id is not None:
        statement = statement.where(EmailToken.user_id == user_id)
    result = db.execute(statement.values(used_at=now).execution_options(synchronize_session=False))
    return result.rowcount or 0


def deliverable_token(
    db: Session, token_id: str, purpose: str, key_id: str | None, *, now: datetime | None = None
) -> str | None:
    """The raw token to put in an email, or None if it must not be sent.

    None when the row is gone, used or expired, when its key version is no longer configured,
    or when the rebuilt token does not hash to the stored value (never send a dead link).
    """
    now = now or datetime.now(timezone.utc)
    try:
        parsed = uuid.UUID(str(token_id))
    except ValueError:
        return None
    row = db.get(EmailToken, parsed)
    if row is None or row.purpose != purpose or row.used_at is not None or row.expires_at <= now or not key_id:
        return None
    try:
        token = derive_token(row.id, purpose, str(key_id))
    except EmailTokenKeyUnavailable:
        return None
    if not hmac.compare_digest(hash_token(token), row.token_hash):
        return None
    return token


def pending_key_usage(db: Session, *, now: datetime | None = None) -> Counter[str]:
    """Key ids still needed by pending emails whose token is live: ``{key_id: count}``."""
    now = now or datetime.now(timezone.utc)
    rows = db.execute(
        select(EmailOutbox.params)
        .join(EmailToken, EmailToken.id == EmailOutbox.params["token_id"].astext.cast(EmailToken.id.type))
        .where(EmailOutbox.status == "pending", EmailToken.used_at.is_(None), EmailToken.expires_at > now)
    ).scalars()
    return Counter(str((params or {}).get("key_id") or "unversioned") for params in rows)
