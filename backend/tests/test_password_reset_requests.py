"""R-6 regression tests: password-reset requests can't flood an inbox or the outbound queue.

Concurrent requests for one account are covered in ``test_email_token_rotation.py`` (committed rows).
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_password
from app.db.session import get_db
from app.main import app
from app.models import EmailOutbox, EmailToken, User
from app.services.email_worker import LocalTestEmailAdapter, process_outbox
from app.services.password_reset import ResetOutcome, request_password_reset

TOKEN_IN_BODY = re.compile(r"#token=([A-Za-z0-9_-]+)")


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
    row = User(email=f"flood-{uuid.uuid4().hex[:8]}@example.org", password_hash=hash_password("old-password-1"), is_active=True)
    db_session.add(row)
    db_session.flush()
    return row


def queued(db_session: Session, user: User) -> int:
    return db_session.scalar(select(func.count()).select_from(EmailOutbox).where(EmailOutbox.user_id == user.id))


async def test_a_normal_request_queues_one_email_whose_link_works(client, db_session, user):
    response = await client.post("/auth/forgot-password", json={"email": user.email})
    assert response.status_code == 200 and queued(db_session, user) == 1
    mailbox = LocalTestEmailAdapter()
    process_outbox(db_session, adapter=mailbox)
    token = TOKEN_IN_BODY.search(mailbox.latest_for_recipient(user.email).text_content).group(1)
    assert (await client.post("/auth/reset-password", json={"token": token, "new_password": "new-password-1"})).status_code == 200


async def test_repeated_requests_within_the_cooldown_queue_nothing_more_and_answer_identically(client, db_session, user):
    responses = [await client.post("/auth/forgot-password", json={"email": user.email}) for _ in range(6)]
    assert {r.status_code for r in responses} == {200}
    assert len({r.text for r in responses}) == 1
    assert queued(db_session, user) == 1
    assert db_session.scalar(select(func.count()).select_from(EmailToken).where(EmailToken.user_id == user.id)) == 1


async def test_the_answer_is_the_same_for_unknown_inactive_throttled_and_new_requests(client, db_session, user):
    inactive = User(email=f"inactive-{uuid.uuid4().hex[:6]}@example.org", password_hash="x", is_active=False)
    db_session.add(inactive)
    db_session.flush()
    bodies = {
        "new": (await client.post("/auth/forgot-password", json={"email": user.email})).json(),
        "throttled": (await client.post("/auth/forgot-password", json={"email": user.email})).json(),
        "unknown": (await client.post("/auth/forgot-password", json={"email": f"nobody-{uuid.uuid4().hex[:6]}@example.org"})).json(),
        "inactive": (await client.post("/auth/forgot-password", json={"email": inactive.email})).json(),
    }
    assert len({str(body) for body in bodies.values()}) == 1
    assert queued(db_session, inactive) == 0


def test_after_the_cooldown_a_new_email_can_be_queued(db_session, user):
    now = datetime.now(timezone.utc)
    cooldown = timedelta(seconds=settings.PASSWORD_RESET_COOLDOWN_SECONDS)
    assert request_password_reset(db_session, user.email, now=now) == ResetOutcome.QUEUED
    assert request_password_reset(db_session, user.email, now=now + cooldown - timedelta(seconds=1)) == ResetOutcome.COOLDOWN
    assert request_password_reset(db_session, user.email, now=now + cooldown + timedelta(seconds=1)) == ResetOutcome.QUEUED
    assert queued(db_session, user) == 2


def test_the_daily_cap_holds_even_across_cooldown_windows(db_session, user):
    start = datetime.now(timezone.utc)
    step = timedelta(seconds=settings.PASSWORD_RESET_COOLDOWN_SECONDS + 1)
    outcomes = [request_password_reset(db_session, user.email, now=start + step * i) for i in range(settings.PASSWORD_RESET_DAILY_LIMIT + 2)]
    assert outcomes.count(ResetOutcome.QUEUED) == settings.PASSWORD_RESET_DAILY_LIMIT
    assert outcomes[-1] == ResetOutcome.DAILY_LIMIT
    # A day after the first request the oldest one ages out of the rolling window.
    assert request_password_reset(db_session, user.email, now=start + timedelta(days=1, minutes=1) + step * 6) == ResetOutcome.QUEUED


def test_a_full_queue_stops_new_reset_emails(db_session, user, monkeypatch):
    monkeypatch.setattr(settings, "PASSWORD_RESET_MAX_PENDING", 3)
    baseline = db_session.scalar(select(func.count()).select_from(EmailOutbox).where(
        EmailOutbox.template == "password_reset", EmailOutbox.status == "pending"))
    for i in range(max(0, 3 - baseline)):
        db_session.add(EmailOutbox(to_address=f"q{i}@example.org", template="password_reset", params={},
                                   status="pending", dedupe_key=f"fill:{uuid.uuid4().hex}"))
    db_session.flush()
    assert request_password_reset(db_session, user.email) == ResetOutcome.QUEUE_FULL
    assert queued(db_session, user) == 0


async def test_an_attacker_spamming_a_victims_address_leaves_the_victim_one_working_link(client, db_session, user):
    """UX under abuse: the victim gets one email per window, and its link still works when they use it."""
    for _ in range(10):
        await client.post("/auth/forgot-password", json={"email": user.email})
    mailbox = LocalTestEmailAdapter()
    process_outbox(db_session, adapter=mailbox)
    assert len(mailbox.get_for_recipient(user.email)) == 1
    # The victim asks too (still in the window): nothing new is sent, but the earlier link works.
    assert (await client.post("/auth/forgot-password", json={"email": user.email})).status_code == 200
    token = TOKEN_IN_BODY.search(mailbox.latest_for_recipient(user.email).text_content).group(1)
    assert (await client.post("/auth/reset-password", json={"token": token, "new_password": "new-password-1"})).status_code == 200


async def test_disabled_delivery_still_refuses_before_any_throttling_state_is_written(db_session, user, monkeypatch):
    monkeypatch.setattr(settings, "EMAIL_DELIVERY", "disabled")

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as plain:
            response = await plain.post("/auth/forgot-password", json={"email": user.email})
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 503 and queued(db_session, user) == 0


async def test_case_variants_of_one_address_share_the_cooldown(client, db_session, user):
    await client.post("/auth/forgot-password", json={"email": user.email})
    await client.post("/auth/forgot-password", json={"email": user.email.upper()})
    assert queued(db_session, user) == 1
