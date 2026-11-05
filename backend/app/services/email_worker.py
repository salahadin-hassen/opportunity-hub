"""Transactional email delivery worker and provider adapters (plan §C.3).

Implements the transactional outbox pattern:
- Application handlers write to `email_outbox` in the same DB transaction as business logic.
- Background worker polls or is triggered to process pending emails.
- Safe concurrent processing via PostgreSQL `SELECT ... FOR UPDATE SKIP LOCKED`.
- Exponential retry backoff on failure, terminating at max attempts.
- Pluggable adapters: local in-memory (tests), console (dev), SMTP (production).
"""
from __future__ import annotations

import logging
import smtplib
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.email_outbox import EmailOutbox

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 5
BASE_RETRY_DELAY_SECONDS = 30


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


class ConsoleEmailAdapter(EmailAdapter):
    """Prints outbound email to standard output/logs (local development)."""

    def send(self, message: OutboundMessage) -> None:
        logger.info(
            "EMAIL OUTBOX: To: %s | Subject: %s | Body: %s",
            message.to_address,
            message.subject,
            message.text_content[:200],
        )


class SmtpEmailAdapter(EmailAdapter):
    """SMTP delivery adapter for production environments."""

    def __init__(
        self,
        host: str,
        port: int = 587,
        username: str | None = None,
        password: str | None = None,
        from_address: str = "noreply@opportunities.sahelyon.com",
        use_tls: bool = True,
    ) -> None:
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.from_address = from_address
        self.use_tls = use_tls

    def send(self, message: OutboundMessage) -> None:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = message.subject
        msg["From"] = self.from_address
        msg["To"] = message.to_address

        part1 = MIMEText(message.text_content, "plain", "utf-8")
        msg.attach(part1)
        if message.html_content:
            part2 = MIMEText(message.html_content, "html", "utf-8")
            msg.attach(part2)

        with smtplib.SMTP(self.host, self.port, timeout=10) as server:
            if self.use_tls:
                server.starttls()
            if self.username and self.password:
                server.login(self.username, self.password)
            server.sendmail(self.from_address, [message.to_address], msg.as_string())


# Global default adapter (defaults to console; tests inject LocalTestEmailAdapter)
_default_adapter: EmailAdapter = ConsoleEmailAdapter()


def get_default_email_adapter() -> EmailAdapter:
    return _default_adapter


def set_default_email_adapter(adapter: EmailAdapter) -> None:
    global _default_adapter
    _default_adapter = adapter


def render_template(template: str, params: dict[str, Any]) -> tuple[str, str]:
    """Render subject and body text for an email template."""
    token = params.get("token", "")
    if template == "password_reset":
        subject = "Opportunity Hub — Reset Your Password"
        body = (
            "Hello,\n\n"
            "We received a request to reset your password on Opportunity Hub.\n"
            f"Use the following secure token to complete the reset:\n\n"
            f"{token}\n\n"
            "Or navigate to: https://opportunities.sahelyon.com/reset-password\n\n"
            "If you did not make this request, you can safely ignore this email.\n"
            "This token will expire in 1 hour."
        )
        return subject, body
    elif template == "email_verification":
        subject = "Opportunity Hub — Verify Your Email"
        body = (
            "Hello,\n\n"
            "Welcome to Opportunity Hub. Please verify your email with this token:\n\n"
            f"{token}\n\n"
            "This token will expire in 24 hours."
        )
        return subject, body
    else:
        subject = f"Opportunity Hub Notification: {template}"
        body = f"Notification params: {params}"
        return subject, body


def process_outbox(
    db: Session,
    *,
    batch_size: int = 50,
    adapter: EmailAdapter | None = None,
) -> int:
    """Deliver a batch of pending emails from the outbox with safe concurrency.
    
    Returns the count of successfully delivered messages in this batch.
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
        subject, text_content = render_template(record.template, record.params or {})
        msg = OutboundMessage(
            to_address=record.to_address,
            subject=subject,
            text_content=text_content,
        )

        try:
            effective_adapter.send(msg)
            record.status = "sent"
            record.sent_at = datetime.now(timezone.utc)
            record.last_error = None
            success_count += 1
            logger.info("Successfully delivered email %s to %s", record.id, record.to_address)
        except Exception as exc:
            record.attempts += 1
            record.last_error = f"{type(exc).__name__}: {str(exc)[:500]}"
            if record.attempts >= MAX_ATTEMPTS:
                record.status = "failed"
                logger.error("Email %s permanently failed after %d attempts: %s", record.id, record.attempts, exc)
            else:
                delay = BASE_RETRY_DELAY_SECONDS * (2 ** (record.attempts - 1))
                record.send_after = now + timedelta(seconds=delay)
                logger.warning("Email %s failed attempt %d, retrying in %ds: %s", record.id, record.attempts, delay, exc)

    db.flush()
    return success_count

