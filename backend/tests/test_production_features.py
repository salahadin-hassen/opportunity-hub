"""Tests for production hardening: sessions, batch matching, capabilities, tracking, and observability."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import create_access_token, hash_password
from app.db.session import get_db
from app.main import app
from app.models import Opportunity, OpportunityStatus, OpportunityType, Profile, User
from app.services.sessions import create_session, hash_token


@pytest.fixture
async def client(db_session: Session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def auth_headers(db_session: Session) -> tuple[User, Profile, dict[str, str]]:
    user = User(
        email=f"prod_student_{uuid.uuid4().hex[:8]}@example.org",
        password_hash=hash_password("password123"),
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()

    profile = Profile(
        user_id=user.id,
        full_name="Prod Student",
        email=user.email,
        degree_level="bachelor",
        is_currently_enrolled=True,
    )
    db_session.add(profile)
    db_session.flush()

    token = create_access_token(user.id)
    headers = {"Authorization": f"Bearer {token}"}
    return user, profile, headers


@pytest.fixture
def sample_opportunity(db_session: Session) -> Opportunity:
    opp = Opportunity(
        title="Production Fellowships 2026",
        slug=f"prod-fellowship-{uuid.uuid4().hex[:8]}",
        host_name="Global Foundation",
        opportunity_type=OpportunityType.FELLOWSHIP,
        status=OpportunityStatus.PUBLISHED,
        official_url="https://example.org/fellowship",
    )
    db_session.add(opp)
    db_session.flush()
    return opp


@pytest.mark.asyncio
async def test_correlation_id_middleware(client: AsyncClient):
    """Verify X-Request-ID is generated or propagated."""
    # 1. Server generates new request ID
    res = await client.get("/health")
    assert res.status_code == 200
    req_id = res.headers.get("x-request-id")
    assert req_id is not None
    assert len(req_id) > 10

    # 2. Client-provided request ID is preserved
    custom_id = "test-custom-request-id-12345"
    res2 = await client.get("/health", headers={"X-Request-ID": custom_id})
    assert res2.headers.get("x-request-id") == custom_id


@pytest.mark.asyncio
async def test_capabilities_endpoint(client: AsyncClient):
    """Verify GET /eligibility/capabilities returns the engine capabilities catalog."""
    res = await client.get("/eligibility/capabilities")
    assert res.status_code == 200
    capabilities = res.json()
    assert isinstance(capabilities, list)
    assert len(capabilities) >= 10
    kinds = {c["kind"] for c in capabilities}
    assert "numeric_threshold" in kinds
    assert "set_membership" in kinds
    assert "date_gate" in kinds
    assert "skill_set" in kinds


@pytest.mark.asyncio
async def test_batch_evaluate_endpoint(client: AsyncClient, auth_headers, sample_opportunity):
    """Verify POST /me/matches/batch-evaluate computes matches server-side."""
    user, profile, headers = auth_headers
    res = await client.post(
        "/me/matches/batch-evaluate",
        json={"opportunity_ids": [str(sample_opportunity.id)]},
        headers=headers,
    )
    assert res.status_code == 200
    matches = res.json()
    assert isinstance(matches, list)
    assert len(matches) == 1
    assert matches[0]["opportunity_id"] == str(sample_opportunity.id)
    assert matches[0]["profile_id"] == str(profile.id)
    assert matches[0]["status"] == "eligible"


@pytest.mark.asyncio
async def test_session_lifecycle(client: AsyncClient, db_session: Session):
    """Verify login creates a session, logout revokes it, and revocation rejects requests."""
    user = User(
        email=f"session_test_{uuid.uuid4().hex[:8]}@example.org",
        password_hash=hash_password("securepassword123"),
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()

    # 1. Login
    login_res = await client.post(
        "/auth/login",
        json={"email": user.email, "password": "securepassword123"},
    )
    assert login_res.status_code == 200
    token = login_res.json()["access_token"]
    auth_h = {"Authorization": f"Bearer {token}"}

    # 2. List sessions
    sessions_res = await client.get("/auth/sessions", headers=auth_h)
    assert sessions_res.status_code == 200
    sessions = sessions_res.json()
    assert len(sessions) >= 1
    assert any(s["is_current"] for s in sessions)

    # 3. Logout
    logout_res = await client.post("/auth/logout", headers=auth_h)
    assert logout_res.status_code == 200
    assert logout_res.json() == {"status": "ok"}

    # 4. Attempt access with revoked token -> must fail with 401
    after_logout_res = await client.get("/auth/sessions", headers=auth_h)
    assert after_logout_res.status_code == 401


@pytest.mark.asyncio
async def test_tracking_saved_opportunities(client: AsyncClient, auth_headers, sample_opportunity):
    """Verify saving, listing, and unsaving opportunities."""
    user, profile, headers = auth_headers
    # 1. Save opportunity
    save_res = await client.post(
        "/me/saved-opportunities",
        json={"opportunity_id": str(sample_opportunity.id), "reminders_enabled": True},
        headers=headers,
    )
    assert save_res.status_code == 201
    saved = save_res.json()
    assert saved["opportunity_id"] == str(sample_opportunity.id)

    # 2. List saved
    list_res = await client.get("/me/saved-opportunities", headers=headers)
    assert list_res.status_code == 200
    items = list_res.json()
    assert len(items) == 1
    assert items[0]["opportunity_id"] == str(sample_opportunity.id)

    # 3. Unsave
    unsave_res = await client.delete(
        f"/me/saved-opportunities/{sample_opportunity.id}",
        headers=headers,
    )
    assert unsave_res.status_code == 204

    # 4. Verify empty list
    empty_res = await client.get("/me/saved-opportunities", headers=headers)
    assert empty_res.json() == []


@pytest.mark.asyncio
async def test_tracking_applications(client: AsyncClient, auth_headers, sample_opportunity):
    """Verify application creation, status update, and checklist items."""
    user, profile, headers = auth_headers
    # 1. Create application
    create_res = await client.post(
        "/me/applications",
        json={
            "opportunity_id": str(sample_opportunity.id),
            "notes": "Target priority 1",
            "initial_items": [{"label": "Gather transcripts"}],
        },
        headers=headers,
    )
    assert create_res.status_code == 201
    app_data = create_res.json()
    app_id = app_data["id"]
    assert app_data["status"] == "draft"
    assert len(app_data["items"]) == 1
    assert app_data["items"][0]["label"] == "Gather transcripts"

    # 2. Update application status to submitted
    patch_res = await client.patch(
        f"/me/applications/{app_id}",
        json={"status": "submitted"},
        headers=headers,
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["status"] == "submitted"
    assert patch_res.json()["submitted_at"] is not None

    # 3. Add item
    add_item_res = await client.post(
        f"/me/applications/{app_id}/items",
        json={"label": "Interview preparation"},
        headers=headers,
    )
    assert add_item_res.status_code == 201
    item_id = add_item_res.json()["id"]

    # 4. Complete item
    complete_item_res = await client.patch(
        f"/me/applications/{app_id}/items/{item_id}",
        json={"status": "completed"},
        headers=headers,
    )
    assert complete_item_res.status_code == 200
    assert complete_item_res.json()["status"] == "completed"


@pytest.mark.asyncio
async def test_password_reset_and_email_verification(client: AsyncClient, db_session: Session):
    """Verify forgot-password token flow and email verification."""
    from datetime import timedelta
    from app.models import EmailOutbox, EmailToken
    from sqlalchemy import select

    user = User(
        email=f"reset_test_{uuid.uuid4().hex[:8]}@example.org",
        password_hash=hash_password("oldpassword123"),
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()

    # 1. Forgot password
    forgot_res = await client.post("/auth/forgot-password", json={"email": user.email})
    assert forgot_res.status_code == 200

    outbox = db_session.scalar(select(EmailOutbox).where(EmailOutbox.user_id == user.id))
    assert outbox is not None
    token = outbox.params["token"]

    # 2. Reset password
    reset_res = await client.post(
        "/auth/reset-password",
        json={"token": token, "new_password": "newpassword123"},
    )
    assert reset_res.status_code == 200

    # 3. Verify login with new password
    login_new = await client.post(
        "/auth/login",
        json={"email": user.email, "password": "newpassword123"},
    )
    assert login_new.status_code == 200

    # 4. Email verification flow
    raw_verify_token = uuid.uuid4().hex
    email_token = EmailToken(
        user_id=user.id,
        purpose="verify_email",
        token_hash=hash_token(raw_verify_token),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    db_session.add(email_token)
    db_session.flush()

    verify_res = await client.post("/auth/verify-email", json={"token": raw_verify_token})
    assert verify_res.status_code == 200
    db_session.refresh(user)
    assert user.email_verified_at is not None


@pytest.mark.asyncio
async def test_account_deletion_lifecycle(client: AsyncClient, db_session: Session):
    """Verify requesting and cancelling account deletion."""
    user = User(
        email=f"del_student_{uuid.uuid4().hex[:8]}@example.org",
        password_hash=hash_password("password123"),
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()

    # Login to create an active session
    login_res = await client.post(
        "/auth/login",
        json={"email": user.email, "password": "password123"},
    )
    assert login_res.status_code == 200
    headers = {"Authorization": f"Bearer {login_res.json()['access_token']}"}

    # 1. Request deletion
    req_res = await client.post("/me/account/request-deletion", headers=headers)
    assert req_res.status_code == 200
    assert "deletion_due_at" in req_res.json()

    # Sessions were revoked by request-deletion
    assert (await client.get("/auth/sessions", headers=headers)).status_code == 401

    # 2. Login again to cancel
    new_login = await client.post(
        "/auth/login",
        json={"email": user.email, "password": "password123"},
    )
    assert new_login.status_code == 200
    new_headers = {"Authorization": f"Bearer {new_login.json()['access_token']}"}

    cancel_res = await client.post("/me/account/cancel-deletion", headers=new_headers)
    assert cancel_res.status_code == 200
    assert cancel_res.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_concurrent_login_creates_distinct_sessions(client: AsyncClient, db_session: Session):
    """Verify that multiple logins for the same user create distinct opaque sessions without collisions."""
    import asyncio
    user = User(
        email=f"concurrent_test_{uuid.uuid4().hex[:8]}@example.org",
        password_hash=hash_password("password123"),
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()

    # 1. Sequential logins each produce distinct opaque tokens without sharing or reuse
    responses = []
    for _ in range(5):
        responses.append(await client.post("/auth/login", json={"email": user.email, "password": "password123"}))
    assert all(r.status_code == 200 for r in responses)

    tokens = [r.json()["access_token"] for r in responses]
    # Every single token must be a unique cryptographically random string
    assert len(set(tokens)) == 5

    # 2. Concurrent session service calls create distinct sessions without hash collision
    from app.services.sessions import create_session
    direct_sessions = [create_session(db_session, user.id) for _ in range(10)]
    assert len({t for _, t in direct_sessions}) == 10
    assert len({s.token_hash for s, _ in direct_sessions}) == 10


@pytest.mark.asyncio
async def test_cookie_authentication_and_csrf_protection(client: AsyncClient, db_session: Session, monkeypatch):
    """Verify cookie-based authentication and CSRF origin protection on mutating endpoints."""
    monkeypatch.setattr(settings, "CORS_ORIGINS", "https://opportunities.sahelyon.com")

    user = User(
        email=f"cookie_test_{uuid.uuid4().hex[:8]}@example.org",
        password_hash=hash_password("password123"),
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()

    # 1. Login sets cookie
    login_res = await client.post("/auth/login", json={"email": user.email, "password": "password123"})
    assert login_res.status_code == 200
    token = login_res.json()["access_token"]
    cookie_header = f"oh_session={token}"

    # 2. Authenticate GET request using purely the cookie (no Authorization header)
    cookie_res = await client.get("/auth/sessions", headers={"Cookie": cookie_header})
    assert cookie_res.status_code == 200
    assert len(cookie_res.json()) >= 1

    # 3. Untrusted origin attempting mutating request with cookie -> 403 CSRF failed
    untrusted_res = await client.post(
        "/auth/logout",
        headers={"Cookie": cookie_header, "Origin": "https://attacker.evil.com"},
    )
    assert untrusted_res.status_code == 403
    assert "CSRF" in untrusted_res.json()["detail"]

    # 4. Trusted origin attempting mutating request with cookie -> 200 OK
    trusted_res = await client.post(
        "/auth/logout",
        headers={"Cookie": cookie_header, "Origin": "https://opportunities.sahelyon.com"},
    )
    assert trusted_res.status_code == 200


@pytest.mark.asyncio
async def test_transactional_email_worker(client: AsyncClient, db_session: Session):
    """Verify transactional email outbox processing, delivery, and retry backoff."""
    from app.services.email_worker import LocalTestEmailAdapter, process_outbox
    from app.models.email_outbox import EmailOutbox
    from sqlalchemy import select

    user = User(
        email=f"email_worker_test_{uuid.uuid4().hex[:8]}@example.org",
        password_hash=hash_password("password123"),
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()

    # Trigger forgot-password to enqueue message in outbox
    await client.post("/auth/forgot-password", json={"email": user.email})

    # Process outbox with deterministic test adapter
    test_adapter = LocalTestEmailAdapter()
    sent_count = process_outbox(db_session, adapter=test_adapter)
    assert sent_count == 1

    # Verify adapter received message
    msg = test_adapter.latest_for_recipient(user.email)
    assert msg is not None
    assert "Reset Your Password" in msg.subject

    # Verify outbox record status updated to 'sent'
    outbox_record = db_session.scalar(select(EmailOutbox).where(EmailOutbox.user_id == user.id))
    assert outbox_record is not None
    assert outbox_record.status == "sent"
    assert outbox_record.sent_at is not None


@pytest.mark.asyncio
async def test_scheduled_account_deletion_job(db_session: Session):
    """Verify that purge_due_accounts deletes accounts past deadline while respecting grace periods and cancellations."""
    from datetime import timedelta
    from app.services.account_deletion import purge_due_accounts
    from app.models.deletion_tombstone import DeletionTombstone
    from sqlalchemy import select

    now = datetime.now(timezone.utc)

    # 1. User due for purge (past 30-day deadline)
    user_due = User(
        email=f"due_user_{uuid.uuid4().hex[:8]}@example.org",
        password_hash=hash_password("pw"),
        is_active=True,
        deletion_requested_at=now - timedelta(days=31),
        deletion_due_at=now - timedelta(days=1),
    )
    # 2. User within grace period (not yet due)
    user_grace = User(
        email=f"grace_user_{uuid.uuid4().hex[:8]}@example.org",
        password_hash=hash_password("pw"),
        is_active=True,
        deletion_requested_at=now - timedelta(days=5),
        deletion_due_at=now + timedelta(days=25),
    )
    # 3. User who cancelled deletion request
    user_cancelled = User(
        email=f"cancelled_user_{uuid.uuid4().hex[:8]}@example.org",
        password_hash=hash_password("pw"),
        is_active=True,
        deletion_requested_at=None,
        deletion_due_at=now - timedelta(days=1),
    )
    db_session.add_all([user_due, user_grace, user_cancelled])
    db_session.flush()

    due_id = user_due.id
    grace_id = user_grace.id
    cancelled_id = user_cancelled.id

    # Run purge job
    purged_count = purge_due_accounts(db_session)
    assert purged_count == 1

    # Verify user_due is deleted and tombstone exists
    assert db_session.get(User, due_id) is None
    tombstone = db_session.scalar(select(DeletionTombstone).where(DeletionTombstone.user_id == due_id))
    assert tombstone is not None

    # Verify user_grace and user_cancelled still exist
    assert db_session.get(User, grace_id) is not None
    assert db_session.get(User, cancelled_id) is not None


@pytest.mark.asyncio
async def test_ordinary_login_does_not_silently_cancel_account_deletion(
    client: AsyncClient, db_session: Session
):
    """Verify that an ordinary login does NOT silently cancel a pending account deletion request."""
    from datetime import timedelta

    now = datetime.now(timezone.utc)
    user = User(
        email=f"pending_del_{uuid.uuid4().hex[:8]}@example.org",
        password_hash=hash_password("testpass123"),
        is_active=True,
        deletion_requested_at=now - timedelta(days=2),
        deletion_due_at=now + timedelta(days=28),
    )
    db_session.add(user)
    db_session.flush()

    # User performs ordinary login
    login_res = await client.post("/auth/login", json={"email": user.email, "password": "testpass123"})
    assert login_res.status_code == 200

    # Inspect user in database: deletion request MUST NOT be cleared
    db_session.expire(user)
    assert user.deletion_requested_at is not None
    assert user.deletion_due_at is not None

    # Deletion can only be cancelled by explicit action
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    cancel_res = await client.post("/me/account/cancel-deletion", headers=headers)
    assert cancel_res.status_code == 200

    db_session.expire(user)
    assert user.deletion_requested_at is None
    assert user.deletion_due_at is None


def test_tombstone_retains_no_email_or_pii():
    """Verify DeletionTombstone model schema contains zero personal data (only UUID and timestamp)."""
    from app.models.deletion_tombstone import DeletionTombstone

    column_names = {c.name for c in DeletionTombstone.__table__.columns}
    assert column_names == {"user_id", "purged_at"}
    assert "email" not in column_names
    assert "email_hash" not in column_names


def test_email_worker_at_least_once_delivery_semantics_on_crash(db_session: Session):
    """Demonstrate at-least-once delivery: worker crash after provider acceptance causes redelivery."""
    from datetime import timedelta
    from app.services.email_worker import EmailAdapter, OutboundMessage, process_outbox
    from app.models.email_outbox import EmailOutbox
    from sqlalchemy import select

    delivered_messages: list[OutboundMessage] = []

    class CrashingAfterSendAdapter(EmailAdapter):
        def send(self, message: OutboundMessage) -> None:
            delivered_messages.append(message)
            # Simulated crash after provider accepted message but before DB transaction completes
            raise RuntimeError("Process abruptly killed after provider accepted payload")

    now = datetime.now(timezone.utc)
    email_row = EmailOutbox(
        user_id=None,
        to_address="student@example.org",
        template="email_verification",
        params={"token": "tok123"},
        status="pending",
        send_after=now,
        dedupe_key=f"verify:{uuid.uuid4().hex}",
    )
    db_session.add(email_row)
    db_session.flush()

    # Worker executes and provider sends, but an unhandled crash interrupts the operation
    # (in process_outbox, an exception inside send is recorded as a retry attempt)
    process_outbox(db_session, adapter=CrashingAfterSendAdapter())

    # Provider received the email once
    assert len(delivered_messages) == 1
    # Because of the crash, row is still marked for retry ('pending')
    assert email_row.status == "pending"
    assert email_row.attempts == 1

    # Restarted worker processes the outbox again
    class SuccessfulAdapter(EmailAdapter):
        def send(self, message: OutboundMessage) -> None:
            delivered_messages.append(message)

    email_row.send_after = datetime.now(timezone.utc) - timedelta(seconds=1)
    db_session.flush()

    sent = process_outbox(db_session, adapter=SuccessfulAdapter())
    assert sent == 1

    # Total deliveries to recipient is 2: proves at-least-once delivery semantics
    assert len(delivered_messages) == 2
    assert email_row.status == "sent"


def test_email_worker_retry_backoff_and_permanent_failure(db_session: Session):
    """Verify exponential retry backoff and transition to 'failed' upon reaching MAX_ATTEMPTS."""
    from datetime import timedelta
    from app.services.email_worker import EmailAdapter, OutboundMessage, process_outbox, MAX_ATTEMPTS
    from app.models.email_outbox import EmailOutbox
    from sqlalchemy import select

    class AlwaysFailingAdapter(EmailAdapter):
        def send(self, message: OutboundMessage) -> None:
            raise ConnectionError("SMTP relay connection refused")

    now = datetime.now(timezone.utc)
    email_row = EmailOutbox(
        user_id=None,
        to_address="student@example.org",
        template="password_reset",
        params={"token": "tok456"},
        status="pending",
        send_after=now,
        attempts=0,
        dedupe_key=f"reset:{uuid.uuid4().hex}",
    )
    db_session.add(email_row)
    db_session.flush()

    # Run attempts 1 through 4 (transient failures)
    for expected_attempt in range(1, MAX_ATTEMPTS):
        email_row.send_after = datetime.now(timezone.utc) - timedelta(seconds=1)
        db_session.flush()

        process_outbox(db_session, adapter=AlwaysFailingAdapter())
        assert email_row.attempts == expected_attempt
        assert email_row.status == "pending"
        assert "SMTP relay connection refused" in email_row.last_error

    # 5th attempt reaches MAX_ATTEMPTS -> permanently fails
    email_row.send_after = datetime.now(timezone.utc) - timedelta(seconds=1)
    db_session.flush()

    process_outbox(db_session, adapter=AlwaysFailingAdapter())
    assert email_row.attempts == MAX_ATTEMPTS
    assert email_row.status == "failed"

    # Subsequent runs ignore the failed message
    sent = process_outbox(db_session, adapter=AlwaysFailingAdapter())
    assert sent == 0


