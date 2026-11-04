"""Audit log (M2-T2): completeness, append-only storage, atomicity and payload hygiene."""
from __future__ import annotations

import uuid
from collections.abc import Iterable

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from app import cli
from app.core.security import create_access_token
from app.db.session import get_db
from app.intelligence import registry
from app.intelligence.connectors.base import Connector, Lead, PageReader, SourceView, register_connector, unregister_connector
from app.intelligence.definitions import SourceDefinition
from app.main import app
from app.models import AuditLog, User
from app.models.audit_log import AuditLogImmutableError
from app.models.enums import DiscoveryMethod, PublishMode, RobotsStatus, SourceStatus, TermsStatus
from app.services import audit


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid")
    urls: list[str] = []


class AuditTestConnector(Connector):
    key = "url_list_audit_test"
    discovery_method = DiscoveryMethod.URL_LIST
    config_model = Config

    def discover(self, source: SourceView, pages: PageReader) -> Iterable[Lead]:
        return []


@pytest.fixture(autouse=True)
def connector():
    register_connector(AuditTestConnector)
    yield
    unregister_connector(AuditTestConnector.key)


def definition(**overrides) -> SourceDefinition:
    values = {
        "name": f"Audit source {uuid.uuid4().hex[:6]}",
        "base_domain": "careers.cern",
        "allowed_hosts": ["careers.cern"],
        "category": "research_institution",
        "authority_level": "official",
        "provider": {"name": "CERN"},
        "discovery_method": "url_list",
        "connector_key": AuditTestConnector.key,
    }
    values.update(overrides)
    return SourceDefinition.model_validate(values)


def make_user(db: Session, role: str = "admin") -> User:
    user = User(email=f"{role}-{uuid.uuid4().hex[:8]}@example.org", password_hash="x", role=role)
    db.add(user)
    db.flush()
    return user


def entries(db: Session, target_id) -> list[AuditLog]:
    return list(
        db.scalars(select(AuditLog).where(AuditLog.target_id == str(target_id)).order_by(AuditLog.id))
    )


# --- Completeness ---------------------------------------------------------------------------------------


def test_the_whole_source_lifecycle_is_recorded_in_order(db_session):
    admin = make_user(db_session)
    source = registry.create_source(db_session, definition(), actor_id=admin.id)
    registry.change_status(db_session, source, SourceStatus.TESTING, actor_id=admin.id)
    registry.record_terms_review(db_session, source, status=TermsStatus.ACCEPTABLE, reviewer_id=admin.id)
    registry.record_test_run(db_session, source, passed=True, robots_status=RobotsStatus.ALLOWED)
    registry.change_status(db_session, source, SourceStatus.APPROVED, actor_id=admin.id)
    registry.set_publish_mode(db_session, source, PublishMode.SHADOW, actor_id=admin.id, reason="gold set ok")
    registry.change_status(db_session, source, SourceStatus.PAUSED, actor_id=admin.id)
    registry.change_status(db_session, source, SourceStatus.RETIRED, actor_id=admin.id, reason="programme ended")

    log = entries(db_session, source.id)
    assert [entry.action for entry in log] == [
        "source.created",
        "source.testing_started",
        "source.terms_reviewed",
        "source.test_run_recorded",
        "source.approved",
        "source.publish_mode_changed",
        "source.paused",
        "source.retired",
    ]
    assert all(entry.target_type == "acquisition_source" for entry in log)
    assert [entry.actor_kind for entry in log].count("system") == 1  # the test run was recorded by the system
    assert log[5].changes == {"publish_mode": {"from": "off", "to": "shadow"}}
    assert log[5].reason == "gold set ok"
    assert log[6].changes["publish_mode"] == {"from": "shadow", "to": "off"}  # pausing turned publication off
    assert log[7].reason == "programme ended"


def test_creation_records_every_declared_fact(db_session):
    source = registry.create_source(db_session, definition(application_hosts=["apply.example-portal.org"]))
    created = entries(db_session, source.id)[0]
    assert created.actor_kind == "system"
    assert created.changes["allowed_hosts"] == {"from": None, "to": ["careers.cern"]}
    assert created.changes["application_hosts"] == {"from": None, "to": ["apply.example-portal.org"]}
    assert created.changes["status"]["to"] == "proposed"
    assert created.changes["publish_mode"]["to"] == "off"


def test_allow_list_changes_are_recorded_with_before_and_after(db_session):
    curator = make_user(db_session, "curator")
    source = registry.create_source(db_session, definition(), actor_id=curator.id)
    registry.update_definition(
        db_session, source, definition(name=source.name, allowed_hosts=["careers.cern", "jobs.careers.cern"]),
        actor_id=curator.id,
    )
    updated = entries(db_session, source.id)[-1]
    assert updated.action == "source.updated"
    assert updated.actor_user_id == curator.id
    assert updated.changes == {
        "allowed_hosts": {"from": ["careers.cern"], "to": ["careers.cern", "jobs.careers.cern"]}
    }


def test_rejection_is_recorded_with_its_reason(db_session):
    source = registry.create_source(db_session, definition())
    registry.change_status(db_session, source, SourceStatus.TESTING)
    registry.change_status(db_session, source, SourceStatus.PROPOSED, reason="robots.txt blocks the listing pages")
    rejected = entries(db_session, source.id)[-1]
    assert (rejected.action, rejected.reason) == ("source.rejected", "robots.txt blocks the listing pages")


def test_automatic_pauses_are_recorded_as_system_actions(db_session):
    source = registry.create_source(db_session, definition())
    registry.change_status(db_session, source, SourceStatus.TESTING)
    registry.record_terms_review(db_session, source, status=TermsStatus.ACCEPTABLE, reviewer_id=None)
    registry.record_test_run(db_session, source, passed=True, robots_status=RobotsStatus.ALLOWED)
    registry.change_status(db_session, source, SourceStatus.APPROVED)
    for _ in range(2):
        registry.record_run_failure(db_session, source, "timeout", pause_after=2)
    paused = entries(db_session, source.id)[-1]
    assert paused.action == "source.auto_paused"
    assert paused.actor_kind == "system"
    assert paused.reason == "2 consecutive failed runs"
    assert paused.changes["status"] == {"from": "approved", "to": "paused"}


def test_robots_changes_are_recorded_only_when_something_changed(db_session):
    source = registry.create_source(db_session, definition())
    before = len(entries(db_session, source.id))
    registry.record_robots_status(db_session, source, RobotsStatus.UNKNOWN)  # unchanged
    assert len(entries(db_session, source.id)) == before
    registry.record_robots_status(db_session, source, RobotsStatus.ALLOWED)
    assert entries(db_session, source.id)[-1].action == "source.robots_status_changed"


def test_refused_or_no_op_operations_write_nothing(db_session):
    source = registry.create_source(db_session, definition())
    count = len(entries(db_session, source.id))
    with pytest.raises(registry.SourceStateError):
        registry.change_status(db_session, source, SourceStatus.APPROVED)
    with pytest.raises(registry.SourceStateError):
        registry.set_publish_mode(db_session, source, PublishMode.SHADOW)
    registry.set_publish_mode(db_session, source, PublishMode.OFF)  # already off
    registry.record_run_success(db_session, source)
    registry.record_run_failure(db_session, source, "not approved, so no pause")
    assert len(entries(db_session, source.id)) == count


def test_role_changes_are_recorded_without_personal_data(db_session):
    user = make_user(db_session, "student")
    cli.grant_role(db_session, user.email, "curator")
    cli.grant_role(db_session, user.email, "curator")  # no-op: no second entry
    log = entries(db_session, user.id)
    assert len(log) == 1
    assert (log[0].action, log[0].actor_kind) == ("user.role_changed", "cli")
    assert log[0].changes == {"role": {"from": "student", "to": "curator"}}
    assert user.email not in str(log[0].changes)


async def test_opportunity_creation_is_recorded_with_the_curator(db_session):
    curator = make_user(db_session, "curator")
    app.dependency_overrides[get_db] = lambda: (yield db_session)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            headers = {"Authorization": f"Bearer {create_access_token(curator.id)}"}
            payload = {"slug": f"audited-{uuid.uuid4().hex[:8]}", "title": "Audited Call"}
            created = await client.post("/opportunities", json=payload, headers=headers)
            conflict = await client.post("/opportunities", json=payload, headers=headers)
    finally:
        app.dependency_overrides.clear()
    assert (created.status_code, conflict.status_code) == (201, 409)
    log = entries(db_session, created.json()["id"])
    assert [(entry.action, entry.actor_user_id) for entry in log] == [("opportunity.created", curator.id)]


# --- Append-only --------------------------------------------------------------------------------------


def test_the_orm_refuses_to_modify_entries(db_session):
    entry = audit.record(db_session, action="test.event", target_type="test", target_id="1")
    with pytest.raises(AuditLogImmutableError):
        with db_session.begin_nested():
            entry.reason = "tampered"
            db_session.flush()


def test_the_orm_refuses_to_delete_entries(db_session):
    entry = audit.record(db_session, action="test.event", target_type="test", target_id="2")
    with pytest.raises(AuditLogImmutableError):
        with db_session.begin_nested():
            db_session.delete(entry)
            db_session.flush()


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE audit_log SET reason = 'tampered' WHERE target_id = :tid",
        "DELETE FROM audit_log WHERE target_id = :tid",
        "TRUNCATE audit_log",
    ],
)
def test_the_database_refuses_to_modify_delete_or_truncate(db_session, statement):
    audit.record(db_session, action="test.event", target_type="test", target_id="raw")
    with pytest.raises(DBAPIError, match="append-only"):
        with db_session.begin_nested():
            db_session.execute(text(statement), {"tid": "raw"})
    assert db_session.scalar(select(AuditLog).where(AuditLog.target_id == "raw")) is not None


def test_a_user_entry_must_name_the_user(db_session):
    with pytest.raises(IntegrityError):
        with db_session.begin_nested():
            audit.record(db_session, action="x", target_type="t", target_id="1", actor_kind="user")


# --- Atomicity ---------------------------------------------------------------------------------------


def test_a_failed_audit_write_undoes_the_change(db_session, monkeypatch):
    source = registry.create_source(db_session, definition())
    registry.change_status(db_session, source, SourceStatus.TESTING)

    def broken(*args, **kwargs):
        raise RuntimeError("audit store unavailable")

    monkeypatch.setattr(audit, "record", broken)
    with pytest.raises(RuntimeError):
        with db_session.begin_nested():
            registry.change_status(db_session, source, SourceStatus.PROPOSED, reason="x")
    db_session.refresh(source)
    assert source.status == SourceStatus.TESTING


def test_a_rolled_back_change_leaves_no_entry(db_session):
    source = registry.create_source(db_session, definition())
    with pytest.raises(RuntimeError):
        with db_session.begin_nested():
            registry.change_status(db_session, source, SourceStatus.TESTING)
            raise RuntimeError("request failed after the change")
    assert [entry.action for entry in entries(db_session, source.id)] == ["source.created"]


# --- Payload hygiene -----------------------------------------------------------------------------------


@pytest.mark.parametrize("key", ["password", "new_password_hash", "api_token", "client_secret", "email", "API_KEY"])
def test_secret_or_personal_keys_are_refused(db_session, key):
    with pytest.raises(audit.AuditPayloadError):
        audit.record(db_session, action="x", target_type="t", target_id="1", changes={key: "value"})


def test_reasons_are_trimmed_and_bounded(db_session):
    entry = audit.record(db_session, action="x", target_type="t", target_id="1", reason="  " + "r" * 2000)
    assert entry.reason == "r" * 1000
    assert audit.record(db_session, action="x", target_type="t", target_id="1", reason="   ").reason is None


def test_diff_lists_only_changed_fields():
    assert audit.diff({"a": 1, "b": 2}, {"a": 1, "b": 3, "c": 4}) == {
        "b": {"from": 2, "to": 3},
        "c": {"from": None, "to": 4},
    }
