"""Curator source API: authorisation, lifecycle rules, approval prerequisites and audit records."""
from __future__ import annotations

import uuid
from collections.abc import Iterable

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.db.session import get_db
from app.intelligence import registry
from app.intelligence.connectors.base import Connector, Lead, PageReader, SourceView, register_connector, unregister_connector
from app.main import app
from app.models import AcquisitionSource, AuditLog, User
from app.models.enums import DiscoveryMethod, RobotsStatus
from app.services import audit


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid")
    urls: list[str] = []


class CurateTestConnector(Connector):
    key = "url_list_curate_test"
    discovery_method = DiscoveryMethod.URL_LIST
    config_model = Config

    def discover(self, source: SourceView, pages: PageReader) -> Iterable[Lead]:
        return []


@pytest.fixture(autouse=True)
def connector():
    register_connector(CurateTestConnector)
    yield
    unregister_connector(CurateTestConnector.key)


@pytest.fixture
async def client(db_session: Session):
    """Each request runs in a savepoint that rolls back on error, like the real ``get_db``."""

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
    return made


def as_(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


def body(**overrides) -> dict:
    values = {
        "name": f"CERN careers {uuid.uuid4().hex[:6]}",
        "base_domain": "careers.cern",
        "allowed_hosts": ["careers.cern"],
        "category": "research_institution",
        "authority_level": "official",
        "provider": {"name": "CERN"},
        "discovery_method": "url_list",
        "connector_key": CurateTestConnector.key,
        "connector_config": {"urls": ["https://careers.cern/programmes/summer-studentship/"]},
    }
    values.update(overrides)
    return values


async def propose(client, users, **overrides) -> dict:
    response = await client.post("/curate/sources", json=body(**overrides), headers=as_(users["curator"]))
    assert response.status_code == 201, response.text
    return response.json()


async def make_approvable(client, db_session, users, source_id: str) -> None:
    """Move a source to testing, review its terms, and record a passing test run (a system action)."""
    assert (await client.post(f"/curate/sources/{source_id}/status", json={"status": "testing"}, headers=as_(users["curator"]))).status_code == 200
    review = await client.post(
        f"/curate/sources/{source_id}/terms-review", json={"status": "acceptable", "notes": "Public pages"},
        headers=as_(users["curator"]),
    )
    assert review.status_code == 200
    source = db_session.get(AcquisitionSource, uuid.UUID(source_id))
    registry.record_test_run(db_session, source, passed=True, robots_status=RobotsStatus.ALLOWED)


async def approve(client, db_session, users, source_id: str) -> dict:
    await make_approvable(client, db_session, users, source_id)
    response = await client.post(
        f"/curate/sources/{source_id}/status", json={"status": "approved"}, headers=as_(users["admin"])
    )
    assert response.status_code == 200, response.text
    return response.json()


def history(db_session: Session, source_id: str) -> list[AuditLog]:
    return list(db_session.scalars(select(AuditLog).where(AuditLog.target_id == source_id).order_by(AuditLog.id)))


# --- Who may call what ------------------------------------------------------------------------------

SOME_ID = "00000000-0000-0000-0000-000000000001"
ROUTES = [
    ("GET", "/curate/sources", None),
    ("POST", "/curate/sources", {}),
    ("GET", f"/curate/sources/{SOME_ID}", None),
    ("PUT", f"/curate/sources/{SOME_ID}", {}),
    ("POST", f"/curate/sources/{SOME_ID}/terms-review", {"status": "acceptable"}),
    ("POST", f"/curate/sources/{SOME_ID}/status", {"status": "testing"}),
    ("POST", f"/curate/sources/{SOME_ID}/publish-mode", {"mode": "shadow"}),
    ("GET", f"/curate/sources/{SOME_ID}/history", None),
    ("GET", "/admin/audit", None),
]


@pytest.mark.parametrize(("method", "path", "payload"), ROUTES)
async def test_anonymous_callers_get_401_everywhere(client, method, path, payload):
    response = await client.request(method, path, json=payload)
    assert response.status_code == 401


@pytest.mark.parametrize(("method", "path", "payload"), ROUTES)
async def test_students_get_403_everywhere_even_for_unknown_ids(client, users, method, path, payload):
    # Authorisation is decided before the body is validated or any source is looked up.
    response = await client.request(method, path, json=payload, headers=as_(users["student"]))
    assert response.status_code == 403
    assert response.json() == {"detail": "You do not have permission for this action."}


async def test_the_audit_log_is_admin_only(client, users):
    assert (await client.get("/admin/audit", headers=as_(users["curator"]))).status_code == 403
    assert (await client.get("/admin/audit", headers=as_(users["admin"]))).status_code == 200


# --- Proposing and editing -------------------------------------------------------------------------


async def test_a_curator_can_propose_and_it_is_audited(client, db_session, users):
    created = await propose(client, users, application_hosts=["apply.example-portal.org"])
    assert created["status"] == "proposed" and created["publish_mode"] == "off"
    assert created["allowed_hosts"] == ["careers.cern"]
    assert created["application_hosts"] == ["apply.example-portal.org"]
    log = history(db_session, created["id"])
    assert [(entry.action, entry.actor_user_id) for entry in log] == [("source.created", users["curator"].id)]


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"allowed_hosts": ["evil.org"]}, 422),
        ({"allowed_hosts": ["127.0.0.1"]}, 422),
        ({"connector_key": "not_registered"}, 422),
        ({"connector_config": {"surprise": True}}, 422),
        ({"role": "admin"}, 422),
    ],
)
async def test_invalid_proposals_are_refused_and_not_audited(client, db_session, users, overrides, expected):
    response = await client.post("/curate/sources", json=body(**overrides), headers=as_(users["curator"]))
    assert response.status_code == expected
    assert db_session.scalar(select(AuditLog).where(AuditLog.action == "source.created")) is None


async def test_a_claimed_host_cannot_be_claimed_again(client, users):
    await propose(client, users)
    response = await client.post("/curate/sources", json=body(), headers=as_(users["curator"]))
    assert response.status_code == 409


async def test_unknown_sources_are_404_for_curators(client, users):
    assert (await client.get(f"/curate/sources/{uuid.uuid4()}", headers=as_(users["curator"]))).status_code == 404


async def test_list_filters_by_status(client, users):
    created = await propose(client, users)
    listed = await client.get("/curate/sources", params={"status": "proposed"}, headers=as_(users["curator"]))
    assert created["id"] in {item["id"] for item in listed.json()}
    other = await client.get("/curate/sources", params={"status": "approved"}, headers=as_(users["curator"]))
    assert created["id"] not in {item["id"] for item in other.json()}


async def test_editing_an_approved_source_sends_it_back_to_testing(client, db_session, users):
    created = await propose(client, users)
    await approve(client, db_session, users, created["id"])
    await client.post(f"/curate/sources/{created['id']}/publish-mode", json={"mode": "shadow"}, headers=as_(users["admin"]))
    edited = await client.put(
        f"/curate/sources/{created['id']}",
        json=body(name=created["name"], allowed_hosts=["careers.cern", "jobs.careers.cern"]),
        headers=as_(users["curator"]),
    )
    assert edited.status_code == 200
    assert (edited.json()["status"], edited.json()["publish_mode"]) == ("testing", "off")
    assert history(db_session, created["id"])[-1].changes["allowed_hosts"]["to"] == ["careers.cern", "jobs.careers.cern"]


# --- Lifecycle and approval -------------------------------------------------------------------------


async def test_curators_cannot_approve(client, db_session, users):
    created = await propose(client, users)
    await make_approvable(client, db_session, users, created["id"])
    response = await client.post(
        f"/curate/sources/{created['id']}/status", json={"status": "approved"}, headers=as_(users["curator"])
    )
    assert response.status_code == 403


async def test_approval_requires_terms_robots_and_a_passing_test_run(client, users):
    created = await propose(client, users)
    await client.post(f"/curate/sources/{created['id']}/status", json={"status": "testing"}, headers=as_(users["curator"]))
    response = await client.post(
        f"/curate/sources/{created['id']}/status", json={"status": "approved"}, headers=as_(users["admin"])
    )
    assert response.status_code == 409
    detail = response.json()["detail"]
    assert "terms" in detail and "robots" in detail and "test run" in detail


async def test_there_is_no_route_to_record_a_test_run(client, users):
    created = await propose(client, users)
    response = await client.post(f"/curate/sources/{created['id']}/test-run", json={"passed": True}, headers=as_(users["admin"]))
    assert response.status_code in (404, 405)


async def test_an_admin_approves_once_everything_is_in_place(client, db_session, users):
    created = await propose(client, users)
    approved = await approve(client, db_session, users, created["id"])
    assert (approved["status"], approved["publish_mode"]) == ("approved", "off")
    approval = history(db_session, created["id"])[-1]
    assert (approval.action, approval.actor_user_id) == ("source.approved", users["admin"].id)


async def test_invalid_transitions_are_409(client, users):
    created = await propose(client, users)
    response = await client.post(
        f"/curate/sources/{created['id']}/status", json={"status": "paused"}, headers=as_(users["curator"])
    )
    assert response.status_code == 409


async def test_rejection_needs_a_reason_which_is_audited(client, db_session, users):
    created = await propose(client, users)
    await client.post(f"/curate/sources/{created['id']}/status", json={"status": "testing"}, headers=as_(users["curator"]))
    missing = await client.post(
        f"/curate/sources/{created['id']}/status", json={"status": "proposed"}, headers=as_(users["curator"])
    )
    assert missing.status_code == 409
    rejected = await client.post(
        f"/curate/sources/{created['id']}/status",
        json={"status": "proposed", "reason": "Listing pages need a login"},
        headers=as_(users["curator"]),
    )
    assert rejected.status_code == 200
    assert history(db_session, created["id"])[-1].reason == "Listing pages need a login"


async def test_only_admins_retire(client, users):
    created = await propose(client, users)
    payload = {"status": "retired", "reason": "Duplicate of another source"}
    assert (await client.post(f"/curate/sources/{created['id']}/status", json=payload, headers=as_(users["curator"]))).status_code == 403
    assert (await client.post(f"/curate/sources/{created['id']}/status", json=payload, headers=as_(users["admin"]))).status_code == 200


async def test_curators_can_pause_and_publication_turns_off(client, db_session, users):
    created = await propose(client, users)
    await approve(client, db_session, users, created["id"])
    await client.post(f"/curate/sources/{created['id']}/publish-mode", json={"mode": "shadow"}, headers=as_(users["admin"]))
    paused = await client.post(
        f"/curate/sources/{created['id']}/status", json={"status": "paused"}, headers=as_(users["curator"])
    )
    assert paused.status_code == 200
    assert (paused.json()["status"], paused.json()["publish_mode"]) == ("paused", "off")


# --- Publication mode ------------------------------------------------------------------------------


async def test_an_unapproved_source_cannot_publish(client, users):
    created = await propose(client, users)
    response = await client.post(
        f"/curate/sources/{created['id']}/publish-mode", json={"mode": "shadow"}, headers=as_(users["admin"])
    )
    assert response.status_code == 409


async def test_a_non_official_source_cannot_publish(client, db_session, users):
    created = await propose(client, users, authority_level="secondary", category="aggregator")
    await approve(client, db_session, users, created["id"])
    response = await client.post(
        f"/curate/sources/{created['id']}/publish-mode", json={"mode": "shadow"}, headers=as_(users["admin"])
    )
    assert response.status_code == 409


async def test_raising_is_admin_only_and_one_step_at_a_time(client, db_session, users):
    created = await propose(client, users)
    await approve(client, db_session, users, created["id"])
    url = f"/curate/sources/{created['id']}/publish-mode"
    assert (await client.post(url, json={"mode": "shadow"}, headers=as_(users["curator"]))).status_code == 403
    assert (await client.post(url, json={"mode": "full"}, headers=as_(users["admin"]))).status_code == 409
    raised = await client.post(url, json={"mode": "shadow", "reason": "start shadow run"}, headers=as_(users["admin"]))
    assert raised.status_code == 200 and raised.json()["publish_mode"] == "shadow"
    entry = history(db_session, created["id"])[-1]
    assert (entry.action, entry.reason, entry.changes) == (
        "source.publish_mode_changed", "start shadow run", {"publish_mode": {"from": "off", "to": "shadow"}},
    )


async def test_curators_may_lower_publication(client, db_session, users):
    created = await propose(client, users)
    await approve(client, db_session, users, created["id"])
    url = f"/curate/sources/{created['id']}/publish-mode"
    await client.post(url, json={"mode": "shadow"}, headers=as_(users["admin"]))
    lowered = await client.post(url, json={"mode": "off", "reason": "odd results"}, headers=as_(users["curator"]))
    assert lowered.status_code == 200 and lowered.json()["publish_mode"] == "off"


# --- History and audit reads ------------------------------------------------------------------------


async def test_history_shows_the_source_trail_to_curators(client, db_session, users):
    created = await propose(client, users)
    await client.post(f"/curate/sources/{created['id']}/status", json={"status": "testing"}, headers=as_(users["curator"]))
    trail = await client.get(f"/curate/sources/{created['id']}/history", headers=as_(users["curator"]))
    assert trail.status_code == 200
    assert [entry["action"] for entry in trail.json()] == ["source.created", "source.testing_started"]
    assert all("email" not in str(entry["changes"]) for entry in trail.json())


async def test_admin_audit_read_filters_newest_first(client, users):
    first = await propose(client, users)
    await propose(client, users, base_domain="kaust.edu.sa", allowed_hosts=["kaust.edu.sa"])
    everything = (await client.get("/admin/audit", params={"action": "source.created"}, headers=as_(users["admin"]))).json()
    assert len(everything) >= 2 and everything[0]["id"] > everything[1]["id"]
    one = (await client.get("/admin/audit", params={"target_id": first["id"]}, headers=as_(users["admin"]))).json()
    assert [entry["target_id"] for entry in one] == [first["id"]]


# --- Atomicity through the API ----------------------------------------------------------------------


async def test_a_failing_audit_write_leaves_the_source_unchanged(client, db_session, users, monkeypatch):
    created = await propose(client, users)

    def broken(*args, **kwargs):
        raise RuntimeError("audit store unavailable")

    monkeypatch.setattr(audit, "record", broken)
    with pytest.raises(RuntimeError):
        await client.post(f"/curate/sources/{created['id']}/status", json={"status": "testing"}, headers=as_(users["curator"]))
    source = db_session.get(AcquisitionSource, uuid.UUID(created["id"]))
    db_session.refresh(source)
    assert source.status == "proposed"
