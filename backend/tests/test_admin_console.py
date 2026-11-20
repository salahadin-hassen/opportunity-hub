"""The admin console: who may use it, what it reveals, and the guards on account actions."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.db.session import get_db
from app.main import app
from app.models import AuditLog, Profile, User
from app.models import Session as UserSession
from app.services.sessions import create_session


@pytest.fixture
async def client(db_session: Session):
    def override_get_db():
        savepoint = db_session.begin_nested()
        try:
            yield db_session
            savepoint.commit()
        except Exception:
            savepoint.rollback()
            raise

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def users(db_session: Session) -> dict[str, User]:
    made = {}
    for role in ("student", "curator", "admin"):
        user = User(email=f"{role}-{uuid.uuid4().hex[:8]}@example.org", password_hash="x", role=role)
        db_session.add(user)
        made[role] = user
    db_session.flush()
    db_session.add(Profile(user_id=made["student"].id, full_name="Ada Student", email=made["student"].email, degree_level="bachelor"))
    db_session.flush()
    return made


def as_(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


ENDPOINTS = [("get", "/admin/overview", None), ("get", "/admin/users", None)]


@pytest.mark.parametrize("method,path,body", ENDPOINTS)
async def test_only_admins_can_open_the_console(client, users, method, path, body):
    assert (await client.request(method, path)).status_code == 401
    assert (await client.request(method, path, headers=as_(users["student"]))).status_code == 403
    assert (await client.request(method, path, headers=as_(users["curator"]))).status_code == 403
    assert (await client.request(method, path, headers=as_(users["admin"]))).status_code == 200


async def test_overview_counts_come_from_the_database(client, users):
    response = await client.get("/admin/overview", headers=as_(users["admin"]))
    data = response.json()
    assert data["users"]["total"] >= 3
    roles = {row["key"]: row["count"] for row in data["users"]["by_role"]}
    assert roles.get("admin", 0) >= 1 and roles.get("curator", 0) >= 1
    assert len(data["activity"]["signups_30d"]) == 30
    assert data["system"]["schema_revision"]


async def test_directory_search_and_filters(client, users):
    admin = as_(users["admin"])
    by_name = (await client.get("/admin/users", params={"q": "Ada Stud"}, headers=admin)).json()
    assert [row["email"] for row in by_name["items"]] == [users["student"].email]
    assert by_name["items"][0]["full_name"] == "Ada Student"
    curators = (await client.get("/admin/users", params={"role": "curator", "q": users["curator"].email}, headers=admin)).json()
    assert curators["total"] == 1
    # LIKE wildcards in the search are literal, not patterns.
    assert (await client.get("/admin/users", params={"q": "%"}, headers=admin)).json()["total"] == 0


async def test_responses_carry_no_secrets_and_only_networks(client, db_session, users):
    student = users["student"]
    _, token = create_session(db_session, student.id, user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/131.0 Safari/537.36", client_ip="203.0.113.77")
    db_session.flush()
    response = await client.get(f"/admin/users/{student.id}", headers=as_(users["admin"]))
    text = response.text
    assert response.status_code == 200
    assert token not in text and "203.0.113.77" not in text and "password_hash" not in text
    session = response.json()["sessions"][0]
    assert session["network"] == "203.0.113.0/24"
    assert session["device"] == "Chrome on macOS"


async def test_role_change_is_audited_with_actor_and_reason(client, db_session, users):
    target = users["student"]
    response = await client.post(f"/admin/users/{target.id}/role", json={"role": "curator", "reason": "Joining the review team"}, headers=as_(users["admin"]))
    assert response.status_code == 200
    assert response.json()["role"] == "curator"
    entry = db_session.scalar(select(AuditLog).where(AuditLog.action == "user.role_changed", AuditLog.target_id == str(target.id)))
    assert entry is not None
    assert entry.actor_user_id == users["admin"].id
    assert entry.reason == "Joining the review team"
    assert entry.changes == {"role": {"from": "student", "to": "curator"}}


async def test_actions_need_a_reason(client, users):
    response = await client.post(f"/admin/users/{users['student'].id}/role", json={"role": "curator", "reason": ""}, headers=as_(users["admin"]))
    assert response.status_code == 422


async def test_admins_cannot_act_on_themselves(client, users):
    admin = users["admin"]
    for path, body in (("role", {"role": "student", "reason": "test"}), ("status", {"active": False, "reason": "test"}), ("sessions/revoke", {"reason": "test"})):
        response = await client.post(f"/admin/users/{admin.id}/{path}", json=body, headers=as_(admin))
        assert response.status_code == 409, path


async def test_an_admin_can_demote_another_admin_and_one_always_remains(client, db_session, users):
    """Self-actions are refused and the actor must be an active admin, so an active admin always remains;
    the last-admin guard in the router is defence in depth on top of that."""
    second = User(email=f"second-{uuid.uuid4().hex[:8]}@example.org", password_hash="x", role="admin")
    db_session.add(second)
    db_session.flush()
    response = await client.post(f"/admin/users/{second.id}/role", json={"role": "curator", "reason": "Rotation"}, headers=as_(users["admin"]))
    assert response.status_code == 200 and response.json()["role"] == "curator"
    assert db_session.get(User, users["admin"].id).role == "admin"


async def test_suspension_signs_the_user_out_and_blocks_access(client, db_session, users):
    student = users["student"]
    _, token = create_session(db_session, student.id)
    db_session.flush()
    assert (await client.get("/me", headers={"Authorization": f"Bearer {token}"})).status_code == 200
    response = await client.post(f"/admin/users/{student.id}/status", json={"active": False, "reason": "Spam account"}, headers=as_(users["admin"]))
    assert response.status_code == 200 and response.json()["is_active"] is False
    assert (await client.get("/me", headers={"Authorization": f"Bearer {token}"})).status_code == 401
    entry = db_session.scalar(select(AuditLog).where(AuditLog.action == "user.suspended", AuditLog.target_id == str(student.id)))
    assert entry is not None and entry.changes["sessions_revoked"] == 1
    back = await client.post(f"/admin/users/{student.id}/status", json={"active": True, "reason": "Appeal accepted"}, headers=as_(users["admin"]))
    assert back.json()["is_active"] is True


async def test_sign_out_everywhere(client, db_session, users):
    student = users["student"]
    create_session(db_session, student.id)
    create_session(db_session, student.id)
    db_session.flush()
    response = await client.post(f"/admin/users/{student.id}/sessions/revoke", json={"reason": "Lost laptop"}, headers=as_(users["admin"]))
    assert response.status_code == 200 and response.json()["sessions"] == []
    open_sessions = db_session.scalars(select(UserSession).where(UserSession.user_id == student.id, UserSession.revoked_at.is_(None), UserSession.expires_at > datetime.now(timezone.utc) - timedelta(seconds=1))).all()
    assert open_sessions == []


async def test_unknown_user_is_404(client, users):
    assert (await client.get(f"/admin/users/{uuid.uuid4()}", headers=as_(users["admin"]))).status_code == 404
