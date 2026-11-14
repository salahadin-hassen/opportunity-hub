"""R-4 regression tests: versioned reset-token keys, safe rotation, and concurrent consumption.

Rotation policy under test (see ``app.services.email_tokens``):

* queued emails are rebuilt with the key version they were issued under, while it is configured;
* an email whose key version was removed, or whose rebuilt token doesn't match, is cancelled, not sent;
* links already delivered keep working until they expire or are used (validation never uses the key);
  ``revoke-reset-tokens`` kills them on demand.
"""
from __future__ import annotations

import re
import threading
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr, ValidationError
from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import Session, sessionmaker

from app import cli
from app.core.config import Settings, settings
from app.core.security import hash_password
from app.db.session import get_db
from app.main import app
from app.models import EmailOutbox, EmailToken, User
from app.services import email_tokens
from app.services.email_worker import LocalTestEmailAdapter, process_outbox
from app.services.password_reset import ResetOutcome, request_password_reset

KEY_A = "a1:" + "key-version-a-" + "a" * 30
KEY_B = "b2:" + "key-version-b-" + "b" * 30
TOKEN_IN_BODY = re.compile(r"#token=([A-Za-z0-9_-]+)")


def use_keys(monkeypatch, keys: str, active: str) -> None:
    monkeypatch.setattr(settings, "EMAIL_TOKEN_KEYS", SecretStr(keys))
    monkeypatch.setattr(settings, "EMAIL_TOKEN_ACTIVE_KEY", active)


@pytest.fixture
async def client(db_session: Session, monkeypatch):
    monkeypatch.setattr(settings, "EMAIL_DELIVERY", "memory")

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def user(db_session: Session) -> User:
    row = User(email=f"rotate-{uuid.uuid4().hex[:8]}@example.org", password_hash=hash_password("old-password-1"), is_active=True)
    db_session.add(row)
    db_session.flush()
    return row


def deliver(db_session: Session, email: str) -> str | None:
    mailbox = LocalTestEmailAdapter()
    process_outbox(db_session, adapter=mailbox)
    message = mailbox.latest_for_recipient(email)
    return TOKEN_IN_BODY.search(message.text_content).group(1) if message else None


def outbox_for(db_session: Session, user: User) -> list[EmailOutbox]:
    return list(db_session.scalars(select(EmailOutbox).where(EmailOutbox.user_id == user.id).order_by(EmailOutbox.created_at)))


# --- The rotation sequence -------------------------------------------------------------------------------


async def test_a_message_queued_under_key_a_is_delivered_with_a_working_link_after_rotation_to_b(client, db_session, user, monkeypatch):
    # 1. Queue under version A.
    use_keys(monkeypatch, KEY_A, "a1")
    assert (await client.post("/auth/forgot-password", json={"email": user.email})).status_code == 200
    assert outbox_for(db_session, user)[0].params["key_id"] == "a1"

    # 2. Rotate: B becomes active, A stays listed for queued mail.
    use_keys(monkeypatch, f"{KEY_B},{KEY_A}", "b2")
    assert email_tokens.pending_key_usage(db_session) == {"a1": 1}

    # 3. Process the pending message.
    token = deliver(db_session, user.email)
    assert token is not None and outbox_for(db_session, user)[0].status == "sent"

    # 4. The link works.
    response = await client.post("/auth/reset-password", json={"token": token, "new_password": "new-password-1"})
    assert response.status_code == 200
    assert (await client.post("/auth/login", json={"email": user.email, "password": "new-password-1"})).status_code == 200


async def test_new_requests_after_rotation_use_the_new_key(client, db_session, user, monkeypatch):
    use_keys(monkeypatch, f"{KEY_B},{KEY_A}", "b2")
    await client.post("/auth/forgot-password", json={"email": user.email})
    assert outbox_for(db_session, user)[0].params["key_id"] == "b2"
    assert deliver(db_session, user.email) is not None


async def test_an_already_delivered_link_follows_the_expiry_policy_not_the_key(client, db_session, user, monkeypatch):
    use_keys(monkeypatch, KEY_A, "a1")
    await client.post("/auth/forgot-password", json={"email": user.email})
    delivered = deliver(db_session, user.email)

    # 5. Rotate and even remove A entirely: the delivered link is still valid until it expires...
    use_keys(monkeypatch, KEY_B, "b2")
    row = db_session.scalar(select(EmailToken).where(EmailToken.user_id == user.id))
    row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db_session.flush()
    assert (await client.post("/auth/reset-password", json={"token": delivered, "new_password": "new-password-1"})).status_code == 400

    row.expires_at = datetime.now(timezone.utc) + timedelta(minutes=30)
    db_session.flush()
    assert (await client.post("/auth/reset-password", json={"token": delivered, "new_password": "new-password-1"})).status_code == 200


async def test_revoking_kills_delivered_links_on_demand(client, db_session, user, monkeypatch):
    use_keys(monkeypatch, KEY_A, "a1")
    await client.post("/auth/forgot-password", json={"email": user.email})
    delivered = deliver(db_session, user.email)

    assert email_tokens.revoke_outstanding(db_session, None, email_tokens.PASSWORD_RESET) >= 1
    db_session.flush()
    assert (await client.post("/auth/reset-password", json={"token": delivered, "new_password": "new-password-1"})).status_code == 400


async def test_a_queued_message_whose_key_was_removed_too_early_is_cancelled_not_sent(client, db_session, user, monkeypatch):
    use_keys(monkeypatch, KEY_A, "a1")
    await client.post("/auth/forgot-password", json={"email": user.email})
    use_keys(monkeypatch, KEY_B, "b2")  # A removed while a message still needs it

    assert deliver(db_session, user.email) is None
    record = outbox_for(db_session, user)[0]
    assert record.status == "cancelled" and "key version" in record.last_error


async def test_a_key_whose_secret_changed_under_the_same_id_never_sends_a_dead_link(client, db_session, user, monkeypatch):
    use_keys(monkeypatch, KEY_A, "a1")
    await client.post("/auth/forgot-password", json={"email": user.email})
    use_keys(monkeypatch, "a1:" + "a-different-secret-" + "z" * 20, "a1")

    assert deliver(db_session, user.email) is None
    assert outbox_for(db_session, user)[0].status == "cancelled"


def test_the_key_usage_command_reports_versions_still_needed(db_session, user, monkeypatch, capsys):
    use_keys(monkeypatch, KEY_A, "a1")
    token, key_id = email_tokens.issue(db_session, user_id=user.id, purpose=email_tokens.PASSWORD_RESET, ttl=timedelta(hours=1))
    db_session.add(EmailOutbox(user_id=user.id, to_address=user.email, template="password_reset",
                               params={"token_id": str(token.id), "key_id": key_id}, dedupe_key=f"t:{uuid.uuid4().hex}"))
    db_session.flush()
    assert email_tokens.pending_key_usage(db_session) == {"a1": 1}
    token.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)  # expired tokens no longer need their key
    db_session.flush()
    assert email_tokens.pending_key_usage(db_session) == {}


def test_the_revoke_command_requires_confirmation(capsys):
    assert cli.main(["revoke-reset-tokens"]) == 1
    assert "--yes" in capsys.readouterr().err


# --- Key configuration -----------------------------------------------------------------------------------


def _settings(**values) -> Settings:
    return Settings(_env_file=None, DATABASE_URL="postgresql://u@h/db", JWT_SECRET="s" * 40, **values)


@pytest.mark.parametrize(
    "keys, active, message",
    [
        ("a1:short", "a1", "at least 32"),
        ("A1:" + "x" * 40, "A1", "id:secret"),
        ("no-separator" + "x" * 40, "a1", "id:secret"),
        ("a1:" + "x" * 40 + ",a1:" + "y" * 40, "a1", "unique"),
        ("a1:" + "x" * 40, "zz", "must name one of the ids"),
        ("a1:" + "x" * 40, None, "must name one of the ids"),
    ],
)
def test_malformed_key_configuration_is_refused(keys, active, message):
    with pytest.raises(ValidationError, match=message):
        _settings(EMAIL_TOKEN_KEYS=keys, EMAIL_TOKEN_ACTIVE_KEY=active)


def test_keys_are_independent_of_jwt_secret(user, monkeypatch):
    use_keys(monkeypatch, KEY_A, "a1")
    token_id = uuid.uuid4()
    before = email_tokens.derive_token(token_id, email_tokens.PASSWORD_RESET, "a1")
    monkeypatch.setattr(settings, "JWT_SECRET", "rotated-" + "j" * 40)
    assert email_tokens.derive_token(token_id, email_tokens.PASSWORD_RESET, "a1") == before


def test_no_keys_means_no_tokens(monkeypatch, db_session, user):
    monkeypatch.setattr(settings, "EMAIL_TOKEN_KEYS", None)
    monkeypatch.setattr(settings, "EMAIL_TOKEN_ACTIVE_KEY", None)
    with pytest.raises(email_tokens.EmailTokenKeyUnavailable):
        email_tokens.issue(db_session, user_id=user.id, purpose=email_tokens.PASSWORD_RESET, ttl=timedelta(hours=1))


# --- Concurrent consumption (committed rows, separate connections) ---------------------------------------


@pytest.fixture
def committed_user():
    engine = create_engine(settings.DATABASE_URL)
    factory = sessionmaker(engine)
    with factory.begin() as db:
        row = User(email=f"race-{uuid.uuid4().hex[:8]}@example.org", password_hash=hash_password("old-password-1"), is_active=True)
        db.add(row)
        db.flush()
        user_id, email = row.id, row.email
    yield factory, user_id, email
    with factory.begin() as db:
        db.execute(delete(EmailOutbox).where(EmailOutbox.user_id == user_id))
        db.execute(delete(EmailToken).where(EmailToken.user_id == user_id))
        db.execute(delete(User).where(User.id == user_id))
    engine.dispose()


def test_concurrent_consumption_of_one_token_succeeds_exactly_once(committed_user):
    factory, user_id, _ = committed_user
    with factory.begin() as db:
        row, key_id = email_tokens.issue(db, user_id=user_id, purpose=email_tokens.PASSWORD_RESET, ttl=timedelta(hours=1))
        db.flush()
        raw = email_tokens.derive_token(row.id, email_tokens.PASSWORD_RESET, key_id)

    attempts, barrier, results = 4, threading.Barrier(4), []

    def attempt():
        with factory() as db:
            barrier.wait()
            token = email_tokens.consume(db, raw, email_tokens.PASSWORD_RESET)
            if token is not None:
                threading.Event().wait(0.3)  # hold the row lock so the others must queue behind it
                token.used_at = datetime.now(timezone.utc)
            db.commit()
            results.append(token is not None)

    threads = [threading.Thread(target=attempt) for _ in range(attempts)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    assert sorted(results) == [False, False, False, True]


def test_concurrent_reset_requests_for_one_account_queue_one_email(committed_user, monkeypatch):
    factory, user_id, email = committed_user
    barrier, outcomes = threading.Barrier(5), []

    def request():
        with factory() as db:
            barrier.wait()
            outcomes.append(request_password_reset(db, email))
            db.commit()

    threads = [threading.Thread(target=request) for _ in range(5)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    assert outcomes.count(ResetOutcome.QUEUED) == 1
    with factory() as db:
        assert len(db.scalars(select(EmailOutbox.id).where(EmailOutbox.user_id == user_id)).all()) == 1
        assert len(db.scalars(select(EmailToken.id).where(EmailToken.user_id == user_id)).all()) == 1
