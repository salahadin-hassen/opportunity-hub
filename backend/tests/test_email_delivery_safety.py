"""P0-2 regression tests: reset tokens are never logged or stored raw, and delivery is never faked."""
from __future__ import annotations

import json
import logging
import re
import ssl
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import cli
from app.core.config import Settings, settings
from app.core.security import hash_password
from app.db.session import get_db
from app.main import app
from app.models import EmailOutbox, EmailToken, User
from app.services import email_tokens, email_worker
from app.services.password_reset import ResetOutcome, request_password_reset
from app.services.email_worker import (
    EmailDeliveryNotConfigured,
    LocalTestEmailAdapter,
    SmtpEmailAdapter,
    process_outbox,
)

TOKEN_IN_BODY = re.compile(r"#token=([A-Za-z0-9_-]+)")


@pytest.fixture
async def client(db_session: Session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def user(db_session: Session) -> User:
    row = User(email=f"reset-{uuid.uuid4().hex[:8]}@example.org", password_hash=hash_password("old-password-1"), is_active=True)
    db_session.add(row)
    db_session.flush()
    return row


@pytest.fixture
def delivery(monkeypatch):
    monkeypatch.setattr(settings, "EMAIL_DELIVERY", "memory")


async def request_and_deliver(client: AsyncClient, db_session: Session, email: str) -> tuple[str, LocalTestEmailAdapter]:
    response = await client.post("/auth/forgot-password", json={"email": email})
    assert response.status_code == 200
    mailbox = LocalTestEmailAdapter()
    process_outbox(db_session, adapter=mailbox)
    message = mailbox.latest_for_recipient(email)
    assert message is not None
    return TOKEN_IN_BODY.search(message.text_content).group(1), mailbox


# --- Without a delivery provider -------------------------------------------------------------------------


async def test_reset_is_refused_identically_for_known_and_unknown_emails_when_delivery_is_off(client, db_session, user):
    assert settings.EMAIL_DELIVERY == "disabled"
    known = await client.post("/auth/forgot-password", json={"email": user.email})
    unknown = await client.post("/auth/forgot-password", json={"email": f"nobody-{uuid.uuid4().hex[:6]}@example.org"})

    assert known.status_code == unknown.status_code == 503
    assert known.json() == unknown.json()
    assert db_session.scalar(select(func.count()).select_from(EmailToken).where(EmailToken.user_id == user.id)) == 0
    assert db_session.scalar(select(func.count()).select_from(EmailOutbox).where(EmailOutbox.user_id == user.id)) == 0


def test_the_worker_refuses_to_run_without_a_provider_and_leaves_the_queue_alone(db_session):
    row = EmailOutbox(to_address="s@example.org", template="password_reset", params={"token_id": str(uuid.uuid4())},
                      status="pending", send_after=datetime.now(timezone.utc), dedupe_key=f"t:{uuid.uuid4().hex}")
    db_session.add(row)
    db_session.flush()

    with pytest.raises(EmailDeliveryNotConfigured):
        process_outbox(db_session)

    assert (row.status, row.attempts, row.sent_at) == ("pending", 0, None)


def test_the_cron_command_exits_non_zero_without_a_provider(capsys):
    assert cli.main(["process-outbox"]) == 2
    assert "not configured" in capsys.readouterr().err


def test_there_is_no_console_adapter_that_fakes_delivery():
    assert not hasattr(email_worker, "ConsoleEmailAdapter")


# --- Storage and logs ------------------------------------------------------------------------------------


async def test_the_raw_token_is_never_stored_or_logged(client, db_session, user, delivery, caplog):
    caplog.set_level(logging.DEBUG)
    token, mailbox = await request_and_deliver(client, db_session, user.email)
    body = mailbox.latest_for_recipient(user.email).text_content

    outbox = db_session.scalar(select(EmailOutbox).where(EmailOutbox.user_id == user.id))
    stored = db_session.scalar(select(EmailToken).where(EmailToken.user_id == user.id))
    assert set(outbox.params) == {"token_id", "key_id"}
    assert token not in json.dumps(outbox.params)
    assert stored.token_hash != token and token not in stored.token_hash
    assert outbox.status == "sent"

    logged = "\n".join(record.getMessage() for record in caplog.records)
    assert token not in logged
    assert user.email not in logged
    assert "reset-password" not in logged and body[:40] not in logged


async def test_a_token_works_once(client, db_session, user, delivery):
    token, _ = await request_and_deliver(client, db_session, user.email)

    first = await client.post("/auth/reset-password", json={"token": token, "new_password": "new-password-1"})
    second = await client.post("/auth/reset-password", json={"token": token, "new_password": "new-password-2"})

    assert first.status_code == 200
    assert second.status_code == 400
    login = await client.post("/auth/login", json={"email": user.email, "password": "new-password-1"})
    assert login.status_code == 200


async def test_an_expired_token_is_refused(client, db_session, user, delivery):
    token, _ = await request_and_deliver(client, db_session, user.email)
    row = db_session.scalar(select(EmailToken).where(EmailToken.user_id == user.id))
    row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db_session.flush()

    response = await client.post("/auth/reset-password", json={"token": token, "new_password": "new-password-1"})
    assert response.status_code == 400


async def test_a_successful_reset_revokes_other_outstanding_reset_links(client, db_session, user, delivery):
    first, _ = await request_and_deliver(client, db_session, user.email)
    # A second, distinct link issued once the request cooldown has passed.
    later = datetime.now(timezone.utc) + timedelta(seconds=settings.PASSWORD_RESET_COOLDOWN_SECONDS + 1)
    assert request_password_reset(db_session, user.email, now=later) == ResetOutcome.QUEUED
    mailbox = LocalTestEmailAdapter()
    process_outbox(db_session, adapter=mailbox)
    second = TOKEN_IN_BODY.search(mailbox.latest_for_recipient(user.email).text_content).group(1)
    assert first != second

    assert (await client.post("/auth/reset-password", json={"token": second, "new_password": "new-password-1"})).status_code == 200
    assert (await client.post("/auth/reset-password", json={"token": first, "new_password": "new-password-2"})).status_code == 400


async def test_an_email_whose_token_expired_before_sending_is_cancelled_not_sent(client, db_session, user, delivery):
    assert (await client.post("/auth/forgot-password", json={"email": user.email})).status_code == 200
    row = db_session.scalar(select(EmailToken).where(EmailToken.user_id == user.id))
    row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db_session.flush()
    mailbox = LocalTestEmailAdapter()

    assert process_outbox(db_session, adapter=mailbox) == 0

    outbox = db_session.scalar(select(EmailOutbox).where(EmailOutbox.user_id == user.id))
    assert outbox.status == "cancelled" and mailbox.outbox == []


def test_an_unknown_template_is_cancelled_and_never_dumps_its_params(db_session):
    row = EmailOutbox(to_address="s@example.org", template="mystery", params={"token": "secret-value"},
                      status="pending", send_after=datetime.now(timezone.utc), dedupe_key=f"t:{uuid.uuid4().hex}")
    db_session.add(row)
    db_session.flush()
    mailbox = LocalTestEmailAdapter()

    assert process_outbox(db_session, adapter=mailbox) == 0
    assert row.status == "cancelled" and mailbox.outbox == [] and "token" not in row.params


def test_a_legacy_raw_token_message_is_cancelled_and_scrubbed_never_sent(db_session):
    row = EmailOutbox(to_address="s@example.org", template="password_reset", params={"token": "legacy-token"},
                      status="pending", send_after=datetime.now(timezone.utc), dedupe_key=f"t:{uuid.uuid4().hex}")
    db_session.add(row)
    db_session.flush()
    mailbox = LocalTestEmailAdapter()

    assert process_outbox(db_session, adapter=mailbox) == 0
    assert row.status == "cancelled" and "token" not in row.params and mailbox.outbox == []


def test_tokens_are_bound_to_their_row_and_purpose():
    token_id = uuid.uuid4()
    reset = email_tokens.derive_token(token_id, email_tokens.PASSWORD_RESET, "t1")
    assert reset != email_tokens.derive_token(token_id, email_tokens.VERIFY_EMAIL, "t1")
    assert reset != email_tokens.derive_token(uuid.uuid4(), email_tokens.PASSWORD_RESET, "t1")
    assert len(reset) == 43


# --- Configuration ---------------------------------------------------------------------------------------


def _settings(**values) -> Settings:
    return Settings(_env_file=None, DATABASE_URL="postgresql://u@h/db", JWT_SECRET="s" * 40, **values)


@pytest.mark.parametrize(
    "values, message",
    [
        ({"EMAIL_DELIVERY": "smtp"}, "SMTP_HOST, SMTP_FROM"),
        ({"EMAIL_DELIVERY": "smtp", "SMTP_HOST": "h", "SMTP_FROM": "a@b.org"}, "EMAIL_TOKEN_KEYS"),
        ({"EMAIL_DELIVERY": "smtp", "SMTP_HOST": "smtp.example.org"}, "SMTP_FROM"),
        ({"EMAIL_DELIVERY": "smtp", "SMTP_HOST": "smtp.example.org", "SMTP_FROM": "not-an-address"}, "email address"),
        ({"SMTP_USERNAME": "user"}, "set together"),
        ({"SMTP_PASSWORD": "pw"}, "set together"),
        ({"EMAIL_DELIVERY": "smtp", "SMTP_HOST": "h", "SMTP_FROM": "a@b.org", "SMTP_SECURITY": "none"}, "SMTP_SECURITY"),
    ],
)
def test_incomplete_or_insecure_smtp_settings_are_refused(values, message):
    with pytest.raises(ValidationError, match=message):
        _settings(**values)


def test_the_test_mailbox_is_refused_in_production():
    with pytest.raises(ValidationError, match="tests only"):
        _settings(EMAIL_DELIVERY="memory", APP_ENV="production")


def test_disabled_is_the_default_and_the_password_is_never_printed():
    assert _settings().EMAIL_DELIVERY == "disabled"
    configured = _settings(EMAIL_DELIVERY="smtp", SMTP_HOST="smtp.example.org", SMTP_FROM="noreply@example.org",
                           SMTP_USERNAME="apikey", SMTP_PASSWORD="hunter2-secret",
                           EMAIL_TOKEN_KEYS="k1:" + "token-key-secret-" + "x" * 20, EMAIL_TOKEN_ACTIVE_KEY="k1")
    for secret in ("hunter2-secret", "token-key-secret-"):
        assert secret not in repr(configured) and secret not in str(configured.model_dump())


class _FakeSMTP:
    instances: list["_FakeSMTP"] = []

    def __init__(self, host, port, timeout=None, context=None):
        self.host, self.port, self.context, self.calls = host, port, context, []
        _FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self, context=None):
        self.calls.append(("starttls", context))

    def login(self, username, password):
        self.calls.append(("login", username))

    def sendmail(self, sender, recipients, message):
        self.calls.append(("sendmail", sender, tuple(recipients)))


@pytest.mark.parametrize("security", ["starttls", "ssl"])
def test_smtp_always_uses_certificate_verified_tls(monkeypatch, security):
    _FakeSMTP.instances.clear()
    monkeypatch.setattr(email_worker.smtplib, "SMTP", _FakeSMTP)
    monkeypatch.setattr(email_worker.smtplib, "SMTP_SSL", _FakeSMTP)
    adapter = SmtpEmailAdapter("smtp.example.org", 587, "user", "pw", "noreply@example.org", security=security)

    adapter.send(email_worker.OutboundMessage("to@example.org", "s", "b"))

    server = _FakeSMTP.instances[-1]
    context = server.context if security == "ssl" else server.calls[0][1]
    assert isinstance(context, ssl.SSLContext)
    assert context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname
    assert [call[0] for call in server.calls][-2:] == ["login", "sendmail"]
    if security == "starttls":
        assert server.calls[0][0] == "starttls"  # TLS before credentials


def test_the_adapter_follows_settings(monkeypatch):
    monkeypatch.setattr(settings, "EMAIL_DELIVERY", "smtp")
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.example.org")
    monkeypatch.setattr(settings, "SMTP_FROM", "noreply@example.org")
    assert isinstance(email_worker.get_default_email_adapter(), SmtpEmailAdapter)
    monkeypatch.setattr(settings, "EMAIL_DELIVERY", "disabled")
    with pytest.raises(EmailDeliveryNotConfigured):
        email_worker.get_default_email_adapter()
