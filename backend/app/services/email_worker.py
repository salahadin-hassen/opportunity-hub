"""Transactional email delivery worker and provider adapters (plan §C.3).

Implements the transactional outbox pattern:
- Application handlers write to `email_outbox` in the same DB transaction as business logic.
- Background worker polls or is triggered to process pending emails.
- Safe concurrent processing via PostgreSQL `SELECT ... FOR UPDATE SKIP LOCKED`.
- Exponential retry backoff on failure, terminating at max attempts.
- Adapters: SMTP (production, ``EMAIL_DELIVERY=smtp``) and an in-memory mailbox (tests).

Delivery is never faked: with ``EMAIL_DELIVERY=disabled`` the worker raises
``EmailDeliveryNotConfigured`` before it locks a single row, so the queue is left
untouched. Logs carry outbox ids, templates and exception types only: never a
recipient, a body, a link or a token. Outbox rows hold a token id and key version,
never the token (see ``app.services.email_tokens``); the token is rebuilt at send
time with that key version and checked against the stored hash. An email whose
token was used, has expired, or can't be rebuilt is cancelled instead of sent.
"""
from __future__ import annotations

import logging
import smtplib
import ssl
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.config import Settings, settings
from app.models.email_outbox import EmailOutbox
from app.services import email_tokens

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 5
BASE_RETRY_DELAY_SECONDS = 30
#: Where the reset page lives; the token travels in the URL fragment so it never reaches server logs.
RESET_PASSWORD_URL = "https://opportunities.sahelyon.com/reset-password"


class EmailDeliveryNotConfigured(RuntimeError):
    """No real delivery provider is configured; nothing may be marked as sent."""


@dataclass
class OutboundMessage:
    to_address: str
    subject: str
    text_content: str
    html_content: str | None = None


class EmailAdapter(ABC):
    """Abstract interface for transactional email delivery."""

    @abstractmethod
    def send(self, message: OutboundMessage) -> None:
        """Send an email message or raise an exception on failure."""
        ...


class LocalTestEmailAdapter(EmailAdapter):
    """Deterministic in-memory mailbox for automated tests."""

    def __init__(self) -> None:
        self.outbox: list[OutboundMessage] = []

    def send(self, message: OutboundMessage) -> None:
        self.outbox.append(message)

    def clear(self) -> None:
        self.outbox.clear()

    def get_for_recipient(self, email: str) -> list[OutboundMessage]:
        return [m for m in self.outbox if m.to_address.lower() == email.lower()]

    def latest_for_recipient(self, email: str) -> OutboundMessage | None:
        messages = self.get_for_recipient(email)
        return messages[-1] if messages else None


class SmtpEmailAdapter(EmailAdapter):
    """SMTP delivery over verified TLS (STARTTLS or implicit TLS); never plaintext."""

    def __init__(
        self,
        host: str,
        port: int = 587,
        username: str | None = None,
        password: str | None = None,
        from_address: str = "noreply@opportunities.sahelyon.com",
        security: str = "starttls",
        timeout: float = 10,
    ) -> None:
        if security not in ("starttls", "ssl"):
            raise ValueError("SMTP security must be 'starttls' or 'ssl'")
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.from_address = from_address
        self.security = security
        self.timeout = timeout

    @classmethod
    def from_settings(cls, config: Settings) -> "SmtpEmailAdapter":
        return cls(
            host=config.SMTP_HOST or "",
            port=config.SMTP_PORT,
            username=config.SMTP_USERNAME or None,
            password=config.SMTP_PASSWORD.get_secret_value() if config.SMTP_PASSWORD else None,
            from_address=config.SMTP_FROM or "",
            security=config.SMTP_SECURITY,
        )

    def send(self, message: OutboundMessage) -> None:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = message.subject
        msg["From"] = self.from_address
        msg["To"] = message.to_address
        msg.attach(MIMEText(message.text_content, "plain", "utf-8"))
        if message.html_content:
            msg.attach(MIMEText(message.html_content, "html", "utf-8"))

        context = ssl.create_default_context()  # verifies the certificate and hostname
        if self.security == "ssl":
            server: smtplib.SMTP = smtplib.SMTP_SSL(self.host, self.port, timeout=self.timeout, context=context)
        else:
            server = smtplib.SMTP(self.host, self.port, timeout=self.timeout)
        with server:
            if self.security == "starttls":
                server.starttls(context=context)
            if self.username and self.password:
                server.login(self.username, self.password)
            server.sendmail(self.from_address, [message.to_address], msg.as_string())


#: Explicit override (tests); otherwise the adapter comes from settings on each call.
_override_adapter: EmailAdapter | None = None
_memory_adapter = LocalTestEmailAdapter()


def get_default_email_adapter() -> EmailAdapter:
    """The configured adapter, or ``EmailDeliveryNotConfigured`` when delivery is disabled."""
    if _override_adapter is not None:
        return _override_adapter
    if settings.EMAIL_DELIVERY == "smtp":
        return SmtpEmailAdapter.from_settings(settings)
    if settings.EMAIL_DELIVERY == "memory":
        return _memory_adapter
    raise EmailDeliveryNotConfigured("EMAIL_DELIVERY is disabled; set EMAIL_DELIVERY=smtp and the SMTP_* variables")


def set_default_email_adapter(adapter: EmailAdapter | None) -> None:
    """Override the adapter (tests). ``None`` returns to the settings-based choice."""
    global _override_adapter
    _override_adapter = adapter


def render_template(template: str, token: str) -> tuple[str, str] | None:
    """Subject and body for a known template, or None for an unknown one (never dump params)."""
    if template == "password_reset":
        subject = "Opportunity Hub — Reset Your Password"
        body = (
            "Hello,\n\n"
            "We received a request to reset your password on Opportunity Hub.\n"
            "Open this link to choose a new password:\n\n"
            f"{RESET_PASSWORD_URL}#token={token}\n\n"
            "If the link doesn't open, paste this token on the reset page:\n\n"
            f"{token}\n\n"
            "If you did not make this request, you can safely ignore this email.\n"
            "This link expires in 1 hour and works once."
        )
        return subject, body
    if template == "email_verification":
        subject = "Opportunity Hub — Verify Your Email"
        body = (
            "Hello,\n\n"
            "Welcome to Opportunity Hub. Please verify your email with this token:\n\n"
            f"{token}\n\n"
            "This token will expire in 24 hours."
        )
        return subject, body
    return None


#: ``last_error`` written when a pre-hardening (raw-token) message is cancelled.
LEGACY_CANCEL_REASON = "legacy raw-token message cancelled; never sent"


def is_legacy(params: dict | None) -> bool:
    """Queued by pre-hardening code: carries a raw ``token`` and no ``token_id``."""
    return bool(params) and "token" in params and "token_id" not in params


def legacy_outbox_report(db: Session) -> list[tuple[str, str, int, datetime | None, datetime | None]]:
    """``(status, template, count, oldest, newest)`` for outbox rows still holding a raw token.

    Selects only metadata; ``params`` (the token) is never read into Python.
    """
    rows = db.execute(
        select(
            EmailOutbox.status, EmailOutbox.template, func.count(),
            func.min(EmailOutbox.created_at), func.max(EmailOutbox.created_at),
        )
        .where(EmailOutbox.params.has_key("token"))
        .group_by(EmailOutbox.status, EmailOutbox.template)
        .order_by(EmailOutbox.status, EmailOutbox.template)
    ).all()
    return [tuple(row) for row in rows]


def cancel_legacy_outbox(db: Session) -> tuple[int, int]:
    """Cancel pending legacy rows and strip the raw token from every legacy row, whatever its status.

    Returns ``(cancelled, scrubbed)``. Runs in the caller's transaction; nothing is printed.
    """
    legacy = EmailOutbox.params.has_key("token")
    cancelled = db.execute(
        update(EmailOutbox)
        .where(legacy, EmailOutbox.status == "pending")
        .values(status="cancelled", last_error=LEGACY_CANCEL_REASON)
        .execution_options(synchronize_session=False)
    ).rowcount or 0
    scrubbed = db.execute(
        update(EmailOutbox)
        .where(legacy)
        .values(params=EmailOutbox.params.op("-")("token"))
        .execution_options(synchronize_session=False)
    ).rowcount or 0
    return cancelled, scrubbed


def _error_label(exc: BaseException) -> str:
    """Exception type plus an SMTP status code if any; never the message (it may echo addresses)."""
    code = getattr(exc, "smtp_code", None)
    return f"{type(exc).__name__}" + (f" (SMTP {code})" if code else "")


def _cancel(record: EmailOutbox, reason: str) -> None:
    record.status = "cancelled"
    record.last_error = reason
    record.params = {k: v for k, v in (record.params or {}).items() if k != "token"}
    logger.info("Email %s (%s) cancelled: %s", record.id, record.template, reason)

def process_outbox(
    db: Session,
    *,
    batch_size: int = 50,
    adapter: EmailAdapter | None = None,
) -> int:
    """Deliver a batch of pending emails from the outbox with safe concurrency.

    Returns the count of successfully delivered messages in this batch. Raises
    ``EmailDeliveryNotConfigured`` (before reading the queue) when delivery is disabled.
    """
    effective_adapter = adapter or get_default_email_adapter()
    now = datetime.now(timezone.utc)

    # Use FOR UPDATE SKIP LOCKED to allow safe parallel worker execution without lock contention
    stmt = (
        select(EmailOutbox)
        .where(
            EmailOutbox.status == "pending",
            EmailOutbox.send_after <= now,
        )
        .order_by(EmailOutbox.send_after.asc())
        .limit(batch_size)
        .with_for_update(skip_locked=True)
    )

    batch = list(db.scalars(stmt).all())
    if not batch:
        return 0

    success_count = 0
    for record in batch:
        params = record.params or {}
        purpose = email_tokens.TEMPLATE_PURPOSES.get(record.template)
        if purpose is None:
            _cancel(record, "unknown template")
            continue
        if is_legacy(params):
            # Queued by pre-hardening code with the raw token in params. Never sent: its state can't be
            # trusted, and the user can simply request a new link. The raw token is scrubbed.
            _cancel(record, LEGACY_CANCEL_REASON)
            continue
        token = email_tokens.deliverable_token(db, params.get("token_id", ""), purpose, params.get("key_id"), now=now)
        if not token:
            _cancel(record, "token expired, used, missing or its key version is unavailable")
            continue

        rendered = render_template(record.template, token)
        assert rendered is not None  # every TEMPLATE_PURPOSES key renders
        subject, text_content = rendered
        msg = OutboundMessage(to_address=record.to_address, subject=subject, text_content=text_content)

        try:
            effective_adapter.send(msg)
        except Exception as exc:
            record.attempts += 1
            record.last_error = _error_label(exc)
            if record.attempts >= MAX_ATTEMPTS:
                record.status = "failed"
                record.params = {k: v for k, v in params.items() if k != "token"}
                logger.error("Email %s (%s) permanently failed after %d attempts: %s", record.id, record.template, record.attempts, record.last_error)
            else:
                delay = BASE_RETRY_DELAY_SECONDS * (2 ** (record.attempts - 1))
                record.send_after = now + timedelta(seconds=delay)
                logger.warning("Email %s (%s) failed attempt %d, retrying in %ds: %s", record.id, record.template, record.attempts, delay, record.last_error)
            continue

        record.status = "sent"
        record.sent_at = datetime.now(timezone.utc)
        record.last_error = None
        # A legacy raw token is no longer needed once delivered; token ids are harmless to keep.
        record.params = {k: v for k, v in params.items() if k != "token"}
        success_count += 1
        logger.info("Delivered email %s (%s)", record.id, record.template)

    db.flush()
    return success_count
