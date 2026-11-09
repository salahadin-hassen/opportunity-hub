"""Tests for curator opportunity lifecycle management, validations, and auditing."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import create_access_token, hash_password
from app.db.session import get_db
from app.main import app
from app.models import AuditLog, Opportunity, OpportunityStatus, OpportunityType, Requirement, RequirementCategory, RequirementKind, Source, SourceType, User
from app.models.enums import UserRole


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
def make_user_with_role(db_session: Session):
    def _make(role: UserRole) -> tuple[User, dict[str, str]]:
        user = User(
            email=f"user_{role.value}_{uuid.uuid4().hex[:8]}@example.org",
            password_hash=hash_password("Password123!"),
            is_active=True,
            role=role.value,
        )
        db_session.add(user)
        db_session.flush()
        token = create_access_token(user.id)
        return user, {"Authorization": f"Bearer {token}"}
    return _make


@pytest.mark.asyncio
async def test_get_me_returns_user_role(client: AsyncClient, make_user_with_role):
    curator, headers = make_user_with_role(UserRole.CURATOR)
    res = await client.get("/me", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["id"] == str(curator.id)
    assert data["email"] == curator.email
    assert data["role"] == "curator"


@pytest.mark.asyncio
async def test_student_forbidden_from_curator_endpoints(client: AsyncClient, make_user_with_role):
    _, student_headers = make_user_with_role(UserRole.STUDENT)

    # 1. List curator opportunities -> 403
    res = await client.get("/curate/opportunities", headers=student_headers)
    assert res.status_code == 403

    # 2. Patch opportunity -> 403
    fake_id = uuid.uuid4()
    res = await client.patch(f"/curate/opportunities/{fake_id}", headers=student_headers, json={"title": "Hack"})
    assert res.status_code == 403

    # 3. Publish opportunity -> 403
    res = await client.post(f"/curate/opportunities/{fake_id}/publish", headers=student_headers)
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_curator_opportunity_lifecycle(client: AsyncClient, db_session: Session, make_user_with_role):
    curator, curator_headers = make_user_with_role(UserRole.CURATOR)

    # 1. Create a draft opportunity
    slug = f"test-opp-{uuid.uuid4().hex[:8]}"
    create_payload = {
        "slug": slug,
        "title": "Initial Draft Fellowship",
        "opportunity_type": "fellowship",
        "description": "Fellowship description",
        "status": "draft",
    }
    create_res = await client.post("/opportunities", headers=curator_headers, json=create_payload)
    assert create_res.status_code == 201
    opp_id = create_res.json()["id"]

    # 2. Curator can list opportunities across statuses
    list_res = await client.get("/curate/opportunities", headers=curator_headers)
    assert list_res.status_code == 200
    ids = [o["id"] for o in list_res.json()]
    assert opp_id in ids

    # 3. Incomplete opportunity cannot be published (fails guard: missing sources and rules)
    pub_res = await client.post(f"/curate/opportunities/{opp_id}/publish", headers=curator_headers)
    assert pub_res.status_code == 400
    assert "at least one verified source" in pub_res.json()["detail"]

    # 4. Attach verified source and quoted requirement
    source = Source(
        opportunity_id=uuid.UUID(opp_id),
        source_type=SourceType.OFFICIAL_PAGE,
        url="https://example.org/fellowship",
        retrieved_at=datetime.now(timezone.utc),
        is_primary=True,
    )
    req = Requirement(
        opportunity_id=uuid.UUID(opp_id),
        order_index=1,
        label="Bachelor degree required",
        kind=RequirementKind.EQUALITY,
        params={"metric": "degree_level", "expected": "bachelor"},
        is_mandatory=True,
        category=RequirementCategory.ACADEMIC,
        source_quote="Applicants must hold a Bachelor degree or equivalent.",
    )
    db_session.add_all([source, req])
    db_session.flush()

    # 5. Update opportunity metadata
    patch_res = await client.patch(
        f"/curate/opportunities/{opp_id}",
        headers=curator_headers,
        json={"title": "Updated Production Fellowship 2026"},
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["title"] == "Updated Production Fellowship 2026"

    # 6. Now publish succeeds
    pub_res = await client.post(f"/curate/opportunities/{opp_id}/publish", headers=curator_headers)
    assert pub_res.status_code == 200
    assert pub_res.json()["status"] == "published"
    assert pub_res.json()["published_at"] is not None

    # 7. Close opportunity
    close_res = await client.post(f"/curate/opportunities/{opp_id}/close", headers=curator_headers)
    assert close_res.status_code == 200
    assert close_res.json()["status"] == "closed"

    # 8. Verify audit log captured every action
    audit_entries = list(
        db_session.scalars(
            select(AuditLog)
            .where(AuditLog.target_type == "opportunity", AuditLog.target_id == opp_id)
            .order_by(AuditLog.id.asc())
        ).all()
    )
    actions = [e.action for e in audit_entries]
    assert "opportunity.created" in actions
    assert "opportunity.updated" in actions
    assert "opportunity.published" in actions
    assert "opportunity.closed" in actions
