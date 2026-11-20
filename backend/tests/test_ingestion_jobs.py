"""Running the ingestion pipeline from the site: who may, what it may touch, and how jobs behave.

Jobs run inline here (no thread) and the network-facing functions are replaced with fakes, so these
tests never fetch anything.
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.routers import ingestion_jobs as jobs
from app.core.security import create_access_token
from app.db.session import get_db
from app.intelligence import pipeline, registry
from app.main import app
from app.models import AcquisitionSource, AuditLog, User
from app.models.enums import RobotsStatus, SourceStatus


class _KeepOpen:
    """The test session, but ``close`` is a no-op so the job can't close it under the test."""

    def __init__(self, inner: Session) -> None:
        self._inner = inner

    def close(self) -> None:
        pass

    def commit(self) -> None:  # stay inside the test's transaction
        self._inner.flush()

    def rollback(self) -> None:
        pass

    def __getattr__(self, name):
        return getattr(self._inner, name)


@pytest.fixture(autouse=True)
def inline_jobs(monkeypatch, db_session):
    monkeypatch.setattr(jobs, "_spawn", lambda target: target())
    monkeypatch.setattr(jobs, "_session_factory", lambda: _KeepOpen(db_session))
    monkeypatch.setattr(jobs, "_current", None)
    monkeypatch.setattr(jobs, "_recent", jobs.deque(maxlen=10))


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
    return made


def as_(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


def _approve(db_session: Session, source: AcquisitionSource, admin: User) -> None:
    registry.change_status(db_session, source, SourceStatus.TESTING, actor_id=admin.id)
    registry.record_test_run(db_session, source, passed=True, robots_status=RobotsStatus.ALLOWED)
    registry.record_terms_review(db_session, source, status="acceptable", reviewer_id=admin.id, notes="Read the terms page")
    registry.change_status(db_session, source, SourceStatus.APPROVED, actor_id=admin.id, reason="Test")
    db_session.flush()


async def test_only_admins_start_jobs_and_curators_can_watch(client, users):
    for path in ("/curate/ingestion/jobs/pipeline", f"/curate/ingestion/jobs/source-test/{uuid.uuid4()}", "/curate/ingestion/jobs/starter-sources"):
        assert (await client.post(path, json={}, headers=as_(users["student"]))).status_code == 403, path
        assert (await client.post(path, json={}, headers=as_(users["curator"]))).status_code == 403, path
    assert (await client.get("/curate/ingestion/jobs", headers=as_(users["curator"]))).status_code == 200
    assert (await client.get("/curate/ingestion/jobs", headers=as_(users["student"]))).status_code == 403


async def test_starter_import_proposes_the_shipped_list_once_and_is_audited(client, db_session, users):
    first = (await client.post("/curate/ingestion/jobs/starter-sources", headers=as_(users["admin"]))).json()
    assert len(first["created"]) >= 10 and first["skipped"] == []
    statuses = set(db_session.scalars(select(AcquisitionSource.status).where(AcquisitionSource.name.in_(first["created"]))))
    assert statuses == {SourceStatus.PROPOSED}
    second = (await client.post("/curate/ingestion/jobs/starter-sources", headers=as_(users["admin"]))).json()
    assert second["created"] == [] and sorted(second["skipped"]) == sorted(first["created"])
    assert db_session.scalar(select(AuditLog).where(AuditLog.action == "ingestion.starter_imported", AuditLog.actor_user_id == users["admin"].id))


async def test_a_run_needs_an_approved_source(client, db_session, users):
    for source in db_session.scalars(select(AcquisitionSource).where(AcquisitionSource.status == SourceStatus.APPROVED)):
        source.status = SourceStatus.PAUSED
    db_session.flush()
    response = await client.post("/curate/ingestion/jobs/pipeline", json={}, headers=as_(users["admin"]))
    assert response.status_code == 409


async def test_pipeline_job_runs_discovery_then_processing(client, db_session, users, monkeypatch):
    await client.post("/curate/ingestion/jobs/starter-sources", headers=as_(users["admin"]))
    source = db_session.scalar(select(AcquisitionSource).where(AcquisitionSource.name == "Outreachy internships"))
    _approve(db_session, source, users["admin"])
    seen = {}
    monkeypatch.setattr(pipeline, "run_discovery", lambda db, src: seen.setdefault("discovered", []).append(src.name) or SimpleNamespace(new=1, seen_again=0, rejected=[], error=None))
    monkeypatch.setattr(pipeline, "process_candidates", lambda db, limit, source_id: seen.update(limit=limit, source_id=source_id) or SimpleNamespace(processed=1, by_state={"needs_review": 1}, errors=[]))
    response = await client.post("/curate/ingestion/jobs/pipeline", json={"source_id": str(source.id), "limit": 20}, headers=as_(users["admin"]))
    assert response.status_code == 202
    assert seen == {"discovered": ["Outreachy internships"], "limit": 20, "source_id": source.id}
    state = (await client.get("/curate/ingestion/jobs", headers=as_(users["curator"]))).json()
    assert state["current"] is None
    job = state["recent"][0]
    assert job["status"] == "succeeded" and job["summary"]["new_leads"] == 1 and job["summary"]["by_state"] == {"needs_review": 1}
    assert job["started_by"] == users["admin"].email
    assert db_session.scalar(select(AuditLog).where(AuditLog.action == "ingestion.run_started", AuditLog.actor_user_id == users["admin"].id))


async def test_a_single_source_run_must_be_approved(client, db_session, users):
    await client.post("/curate/ingestion/jobs/starter-sources", headers=as_(users["admin"]))
    source = db_session.scalar(select(AcquisitionSource).where(AcquisitionSource.name == "Rhodes Scholarship"))
    response = await client.post("/curate/ingestion/jobs/pipeline", json={"source_id": str(source.id)}, headers=as_(users["admin"]))
    assert response.status_code == 409


async def test_one_job_at_a_time(client, users, monkeypatch):
    monkeypatch.setattr(jobs, "_current", jobs.Job(id="x", kind="pipeline", label="Pipeline run: all approved sources", started_by="a", started_at=jobs.datetime.now(jobs.timezone.utc)))
    await client.post("/curate/ingestion/jobs/starter-sources", headers=as_(users["admin"]))
    response = await client.post(f"/curate/ingestion/jobs/source-test/{uuid.uuid4()}", headers=as_(users["admin"]))
    assert response.status_code in (404, 409)  # unknown id is checked first
    response = await client.post("/curate/ingestion/jobs/pipeline", json={}, headers=as_(users["admin"]))
    assert response.status_code == 409


async def test_source_test_job_moves_a_proposed_source_to_testing(client, db_session, users, monkeypatch):
    from app.intelligence import source_test

    await client.post("/curate/ingestion/jobs/starter-sources", headers=as_(users["admin"]))
    source = db_session.scalar(select(AcquisitionSource).where(AcquisitionSource.name == "Stipendium Hungaricum"))
    monkeypatch.setattr(source_test, "run_source_test", lambda db, src: SimpleNamespace(passed=True, robots_status="allowed", leads=1, fetched_ok=1, fetched_failed=0, problems=[], warnings=[]))
    response = await client.post(f"/curate/ingestion/jobs/source-test/{source.id}", headers=as_(users["admin"]))
    assert response.status_code == 202
    db_session.refresh(source)
    assert source.status == SourceStatus.TESTING
    job = (await client.get("/curate/ingestion/jobs", headers=as_(users["admin"]))).json()["recent"][0]
    assert job["status"] == "succeeded" and job["summary"]["passed"] is True


async def test_a_failing_job_is_reported_not_raised(client, db_session, users, monkeypatch):
    from app.intelligence import source_test

    await client.post("/curate/ingestion/jobs/starter-sources", headers=as_(users["admin"]))
    source = db_session.scalar(select(AcquisitionSource).where(AcquisitionSource.name == "Türkiye Scholarships"))

    def boom(db, src):
        raise RuntimeError("network down")

    monkeypatch.setattr(source_test, "run_source_test", boom)
    assert (await client.post(f"/curate/ingestion/jobs/source-test/{source.id}", headers=as_(users["admin"]))).status_code == 202
    job = (await client.get("/curate/ingestion/jobs", headers=as_(users["admin"]))).json()["recent"][0]
    assert job["status"] == "failed" and "network down" in job["error"]
