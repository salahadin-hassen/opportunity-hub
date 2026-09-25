"""Integration tests for the Opportunity HTTP API."""
from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.main import app
from app.schemas import OpportunityRead


def opportunity_payload(slug: str | None = None) -> dict[str, object]:
    """Return a valid request payload with an optionally supplied slug."""
    return {
        "slug": slug or f"api-opportunity-{uuid.uuid4().hex[:10]}",
        "title": "API Research Opportunity",
        "opportunity_type": "research_program",
        "description": "A research opportunity created through the API.",
        "host_name": "Opportunity Hub",
        "official_url": "https://example.org/opportunity",
        "deadline_at": "2026-12-01T23:59:00Z",
        "deadline_type": "fixed",
        "starts_at": "2027-06-15",
        "ends_at": "2027-08-20",
        "location_mode": "remote",
        "countries": ["US"],
        "languages": ["en"],
        "tags": ["research"],
        "status": "published",
        "published_at": "2026-09-01T10:00:00Z",
    }


@pytest.fixture
async def client(db_session: Session):
    """Use the existing transaction-bound test session for API requests."""
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_create_opportunity_returns_read_schema_and_uuid(client: AsyncClient):
    response = await client.post("/opportunities", json=opportunity_payload())

    assert response.status_code == 201
    body = response.json()
    assert uuid.UUID(body["id"])
    assert OpportunityRead.model_validate(body).slug == body["slug"]


@pytest.mark.asyncio
async def test_list_opportunities_returns_created_opportunity(client: AsyncClient):
    payload = opportunity_payload()
    created = await client.post("/opportunities", json=payload)

    response = await client.get("/opportunities")

    assert response.status_code == 200
    assert any(item["id"] == created.json()["id"] for item in response.json())


@pytest.mark.asyncio
async def test_list_opportunities_supports_pagination(client: AsyncClient):
    for _ in range(3):
        assert (await client.post("/opportunities", json=opportunity_payload())).status_code == 201

    response = await client.get("/opportunities", params={"limit": 2, "offset": 1})

    assert response.status_code == 200
    assert len(response.json()) == 2


@pytest.mark.asyncio
async def test_get_opportunity_by_id(client: AsyncClient):
    created = await client.post("/opportunities", json=opportunity_payload())
    opportunity_id = created.json()["id"]

    response = await client.get(f"/opportunities/{opportunity_id}")

    assert response.status_code == 200
    assert response.json()["id"] == opportunity_id


@pytest.mark.asyncio
async def test_get_missing_opportunity_returns_not_found(client: AsyncClient):
    response = await client.get(f"/opportunities/{uuid.uuid4()}")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_duplicate_slug_returns_conflict(client: AsyncClient):
    payload = opportunity_payload("duplicate-api-slug")
    assert (await client.post("/opportunities", json=payload)).status_code == 201

    response = await client.post("/opportunities", json=payload)

    assert response.status_code == 409


@pytest.mark.asyncio
async def test_invalid_opportunity_data_returns_unprocessable_entity(client: AsyncClient):
    payload = opportunity_payload()
    payload["ends_at"] = "2027-01-01"

    response = await client.post("/opportunities", json=payload)

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_health_endpoint_remains_available(client: AsyncClient):
    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}