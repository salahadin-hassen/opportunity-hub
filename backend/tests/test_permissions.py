"""Roles and permissions (M2-T1): the matrix, the dependency, and no path to self-elevation."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import cli
from app.api.deps import require_permission
from app.core.config import settings
from app.core.permissions import ROLE_PERMISSIONS, Permission, has_permission
from app.core.security import create_access_token
from app.db.session import get_db
from app.main import app
from app.models import User
from app.models.enums import UserRole

ADMIN_ONLY = {
    Permission.SOURCE_APPROVE,
    Permission.SOURCE_PUBLISH_RAISE,
    Permission.SOURCE_RETIRE,
    Permission.AUDIT_READ,
    Permission.USER_MANAGE,
}


# --- The matrix -----------------------------------------------------------------------------------


def test_every_role_has_an_entry():
    assert set(ROLE_PERMISSIONS) == set(UserRole)


def test_students_have_no_permissions():
    assert not any(has_permission("student", permission) for permission in Permission)


def test_curators_have_everything_except_trust_extending_and_admin_actions():
    assert {p for p in Permission if has_permission("curator", p)} == set(Permission) - ADMIN_ONLY


def test_admins_have_every_permission():
    assert all(has_permission("admin", permission) for permission in Permission)


@pytest.mark.parametrize("role", ["", "superuser", "Admin", "ADMIN", None])
def test_unknown_roles_grant_nothing(role):
    assert not any(has_permission(role, permission) for permission in Permission)


# --- The dependency, through a probe app ------------------------------------------------------------

probe = FastAPI()


@probe.get("/curator-thing")
def curator_thing(user: User = Depends(require_permission(Permission.SOURCE_EDIT))):
    return {"role": user.role}


@probe.get("/admin-thing")
def admin_thing(user: User = Depends(require_permission(Permission.SOURCE_APPROVE))):
    return {"role": user.role}


@pytest.fixture
def client_for(db_session: Session):
    probe.dependency_overrides[get_db] = lambda: (yield db_session)

    async def call(path: str, headers: dict | None = None) -> int:
        async with AsyncClient(transport=ASGITransport(app=probe), base_url="http://test") as client:
            return (await client.get(path, headers=headers or {})).status_code

    yield call
    probe.dependency_overrides.clear()


def make_user(db: Session, role: str = "student", **fields) -> User:
    user = User(email=f"{role}-{uuid.uuid4().hex[:8]}@example.org", password_hash="x", role=role, **fields)
    db.add(user)
    db.flush()
    return user


def bearer(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


@pytest.mark.parametrize(
    ("role", "curator_status", "admin_status"),
    [("student", 403, 403), ("curator", 200, 403), ("admin", 200, 200)],
)
async def test_role_matrix_through_the_dependency(client_for, db_session, role, curator_status, admin_status):
    headers = bearer(make_user(db_session, role))
    assert await client_for("/curator-thing", headers) == curator_status
    assert await client_for("/admin-thing", headers) == admin_status


async def test_unauthenticated_callers_get_401_not_403(client_for):
    assert await client_for("/curator-thing") == 401
    assert await client_for("/curator-thing", {"Authorization": "Bearer not-a-token"}) == 401


async def test_deactivated_admins_get_401(client_for, db_session):
    user = make_user(db_session, "admin", is_active=False)
    assert await client_for("/admin-thing", bearer(user)) == 401


async def test_a_role_claim_in_the_token_is_ignored(client_for, db_session):
    student = make_user(db_session)
    now = datetime.now(timezone.utc)
    forged = jwt.encode(
        {"sub": str(student.id), "role": "admin", "iat": now, "exp": now + timedelta(minutes=5)},
        settings.JWT_SECRET,
        algorithm=settings.JWT_ALGORITHM,
    )
    assert await client_for("/admin-thing", {"Authorization": f"Bearer {forged}"}) == 403


async def test_demotion_takes_effect_on_the_next_request(client_for, db_session):
    user = make_user(db_session, "admin")
    headers = bearer(user)
    assert await client_for("/admin-thing", headers) == 200
    user.role = "student"
    db_session.flush()
    assert await client_for("/admin-thing", headers) == 403


# --- No path to self-elevation through the real API ----------------------------------------------------


@pytest.fixture
async def api_client(db_session: Session):
    app.dependency_overrides[get_db] = lambda: (yield db_session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


async def test_registration_cannot_set_a_role(api_client):
    response = await api_client.post(
        "/auth/register", json={"email": "climber@example.org", "password": "long-enough-password", "role": "admin"}
    )
    assert response.status_code == 422


async def test_registered_accounts_are_students(api_client, db_session):
    response = await api_client.post(
        "/auth/register", json={"email": "newcomer@example.org", "password": "long-enough-password"}
    )
    assert response.status_code == 201
    assert "role" not in response.json()
    assert db_session.get(User, uuid.UUID(response.json()["id"])).role == "student"


async def test_profile_updates_cannot_touch_the_role(api_client, db_session):
    user = make_user(db_session)
    response = await api_client.patch("/me/profile", json={"role": "admin"}, headers=bearer(user))
    assert response.status_code in (404, 422)  # no profile yet, or unknown field: never applied
    assert db_session.get(User, user.id).role == "student"


def test_no_http_route_changes_roles():
    paths = {getattr(route, "path", "") for route in app.routes}
    assert not any("role" in path for path in paths)


# --- Storage -----------------------------------------------------------------------------------------


def test_new_accounts_default_to_student_in_the_database(db_session):
    user_id = uuid.uuid4()
    db_session.execute(
        text("INSERT INTO users (id, email, password_hash) VALUES (:id, :email, 'x')"),
        {"id": user_id, "email": f"raw-{uuid.uuid4().hex[:8]}@example.org"},
    )
    role = db_session.execute(text("SELECT role FROM users WHERE id = :id"), {"id": user_id}).scalar_one()
    assert role == "student"


@pytest.mark.parametrize("role", ["superuser", "Admin", ""])
def test_the_database_rejects_unknown_roles(db_session, role):
    with pytest.raises(IntegrityError):
        with db_session.begin_nested():
            make_user(db_session, role)


# --- Operator CLI --------------------------------------------------------------------------------------


def test_grant_role_changes_the_role_and_reports_the_previous_one(db_session):
    user = make_user(db_session)
    changed, previous = cli.grant_role(db_session, user.email.upper(), "curator")
    assert (changed.id, changed.role, previous) == (user.id, "curator", "student")


def test_grant_role_never_picks_between_accounts_that_differ_only_in_case(db_session):
    """Emails keep their local-part case and are unique exactly, so these are two different people."""
    victim = User(email="case.target@example.org", password_hash="x")
    lookalike = User(email="Case.Target@example.org", password_hash="y")  # e.g. registered by someone else
    db_session.add_all([victim, lookalike])
    db_session.flush()
    changed, _ = cli.grant_role(db_session, "case.target@example.org", "admin")
    assert changed.id == victim.id  # the exact address wins, whichever row the database returns first
    assert db_session.get(User, lookalike.id).role == "student"
    changed, _ = cli.grant_role(db_session, "Case.Target@EXAMPLE.org", "curator")  # domain case is normalised
    assert changed.id == lookalike.id
    with pytest.raises(cli.CliError, match="letter case"):
        cli.grant_role(db_session, "CASE.TARGET@example.org", "admin")  # matches both, exactly neither
    assert db_session.get(User, victim.id).role == "admin" and db_session.get(User, lookalike.id).role == "curator"


def test_grant_role_rejects_unknown_roles_and_accounts(db_session):
    user = make_user(db_session)
    with pytest.raises(cli.CliError):
        cli.grant_role(db_session, user.email, "superuser")
    with pytest.raises(cli.CliError):
        cli.grant_role(db_session, "nobody@example.org", "admin")
    assert db_session.get(User, user.id).role == "student"
