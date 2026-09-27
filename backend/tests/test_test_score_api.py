"""Integration coverage for authenticated TestScore CRUD under /me/profile.

Every test runs inside the transaction provided by ``db_session`` and is
rolled back afterwards, so the dedicated test database stays clean. The
core flow uses real JWT bearer authentication minted with the test-only
secret — authentication is never mocked.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

import pytest
from app.db.session import get_db
from app.main import app
from app.models import Profile, TestScore as ScoreRecord, User
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from tests.test_auth import TEST_JWT_SECRET, auth_headers, make_profile, make_user

TEST_SCORE_READ_FIELDS = {
    "id",
    "profile_id",
    "test_type",
    "overall_score",
    "sub_scores",
    "test_date",
    "expires_at",
    "report_number",
    "created_at",
}


@pytest.fixture
def auth_secret(monkeypatch) -> str:
    """Point token signing at a test-only secret for one test."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "JWT_SECRET", TEST_JWT_SECRET)
    return TEST_JWT_SECRET


@pytest.fixture
async def client(db_session: Session, auth_secret: str):
    """Use the existing transaction-bound test session for API requests."""
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as test_client:
        yield test_client
    app.dependency_overrides.clear()


def seed_user(db_session: Session) -> User:
    user = make_user()
    db_session.add(user)
    db_session.flush()
    return user


def seed_profile(db_session: Session, user: User) -> Profile:
    profile = make_profile()
    profile.user_id = user.id
    db_session.add(profile)
    db_session.flush()
    return profile


def score_payload(**overrides) -> dict:
    payload = {
        "test_type": "IELTS",
        "overall_score": 7.5,
        "sub_scores": {
            "listening": 8.0,
            "reading": 7.0,
            "writing": 6.5,
            "speaking": 7.5,
        },
        "test_date": "2024-01-15",
        "expires_at": "2026-01-15",
        "report_number": "REPORT-001",
    }
    payload.update(overrides)
    return payload


async def create_score(client: AsyncClient, user: User, **overrides) -> dict:
    """Create one test score through the API and return its body."""
    response = await client.post(
        "/me/profile/test-scores",
        json=score_payload(**overrides),
        headers=auth_headers(user),
    )
    assert response.status_code == 201
    return response.json()


def score_count(db_session: Session, profile: Profile) -> int:
    return db_session.scalar(
        select(func.count())
        .select_from(ScoreRecord)
        .where(ScoreRecord.profile_id == profile.id)
    )


# --- GET /me/profile/test-scores ------------------------------------------------------------

async def test_get_returns_the_owners_scores(
    client: AsyncClient, db_session: Session
):
    user = seed_user(db_session)
    profile = seed_profile(db_session, user)
    created = await create_score(client, user)
    response = await client.get(
        "/me/profile/test-scores", headers=auth_headers(user)
    )
    assert response.status_code == 200
    body = response.json()
    assert [row["id"] for row in body] == [created["id"]]
    assert body[0]["profile_id"] == str(profile.id)
    assert body[0]["test_type"] == "IELTS"


async def test_get_returns_multiple_scores(
    client: AsyncClient, db_session: Session
):
    user = seed_user(db_session)
    seed_profile(db_session, user)
    first = await create_score(client, user, test_date="2023-05-01", expires_at="2025-05-01")
    second = await create_score(client, user, test_type="TOEFL", test_date="2024-06-01", expires_at="2026-06-01")
    response = await client.get(
        "/me/profile/test-scores", headers=auth_headers(user)
    )
    assert response.status_code == 200
    assert {row["id"] for row in response.json()} == {first["id"], second["id"]}


async def test_get_order_is_deterministic(
    client: AsyncClient, db_session: Session
):
    user = seed_user(db_session)
    profile = seed_profile(db_session, user)

    def seed_row(
        name: str, *, created_at: datetime, test_date: date | None
    ) -> ScoreRecord:
        score = ScoreRecord(
            profile_id=profile.id,
            test_type=name,
            overall_score=7.0,
            test_date=test_date,
            created_at=created_at,
        )
        db_session.add(score)
        return score

    dated_old = seed_row(
        "Old", created_at=datetime(2024, 5, 1, tzinfo=timezone.utc),
        test_date=date(2024, 1, 15),
    )
    dated_new_a = seed_row(
        "New A", created_at=datetime(2024, 4, 1, tzinfo=timezone.utc),
        test_date=date(2024, 6, 1),
    )
    undated = seed_row(
        "Undated", created_at=datetime(2024, 3, 1, tzinfo=timezone.utc),
        test_date=None,
    )
    dated_new_b = seed_row(
        "New B", created_at=datetime(2024, 6, 1, tzinfo=timezone.utc),
        test_date=date(2024, 6, 1),
    )
    db_session.flush()

    # test_date DESC (undated first under PostgreSQL DESC semantics),
    # then created_at ASC, then id ASC.
    expected = [
        str(undated.id),
        str(dated_new_a.id),
        str(dated_new_b.id),
        str(dated_old.id),
    ]
    first = await client.get("/me/profile/test-scores", headers=auth_headers(user))
    second = await client.get("/me/profile/test-scores", headers=auth_headers(user))
    assert [row["id"] for row in first.json()] == expected
    assert [row["id"] for row in second.json()] == expected


async def test_get_returns_empty_list_when_profile_has_none(
    client: AsyncClient, db_session: Session
):
    user = seed_user(db_session)
    seed_profile(db_session, user)
    response = await client.get(
        "/me/profile/test-scores", headers=auth_headers(user)
    )
    assert response.status_code == 200
    assert response.json() == []


async def test_get_without_profile_returns_404(
    client: AsyncClient, db_session: Session
):
    user = seed_user(db_session)
    response = await client.get(
        "/me/profile/test-scores", headers=auth_headers(user)
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Profile not found."


async def test_endpoints_require_authentication(client: AsyncClient):
    score_id = str(uuid.uuid4())
    assert (await client.get("/me/profile/test-scores")).status_code == 401
    assert (
        await client.post("/me/profile/test-scores", json=score_payload())
    ).status_code == 401
    assert (
        await client.patch(
            f"/me/profile/test-scores/{score_id}", json={"test_type": "x"}
        )
    ).status_code == 401
    assert (
        await client.delete(f"/me/profile/test-scores/{score_id}")
    ).status_code == 401


# --- POST /me/profile/test-scores -----------------------------------------------------------

async def test_owner_can_create_score(
    client: AsyncClient, db_session: Session
):
    user = seed_user(db_session)
    seed_profile(db_session, user)
    response = await client.post(
        "/me/profile/test-scores",
        json=score_payload(),
        headers=auth_headers(user),
    )
    assert response.status_code == 201
    body = response.json()
    assert body["test_type"] == "IELTS"
    assert body["overall_score"] == 7.5
    # test_type is a flexible string, not a closed vocabulary.
    custom = await create_score(client, user, test_type="Company Aptitude Screen v2")
    assert custom["test_type"] == "Company Aptitude Screen v2"


async def test_profile_ownership_is_server_derived(
    client: AsyncClient, db_session: Session
):
    user = seed_user(db_session)
    profile = seed_profile(db_session, user)
    body = await create_score(client, user)
    assert body["profile_id"] == str(profile.id)
    row = db_session.get(ScoreRecord, uuid.UUID(body["id"]))
    assert row.profile_id == profile.id


async def test_client_cannot_submit_profile_id(
    client: AsyncClient, db_session: Session
):
    user = seed_user(db_session)
    profile = seed_profile(db_session, user)
    other = seed_user(db_session)
    other_profile = seed_profile(db_session, other)
    response = await client.post(
        "/me/profile/test-scores",
        json=score_payload(profile_id=str(other_profile.id)),
        headers=auth_headers(user),
    )
    assert response.status_code == 422
    assert score_count(db_session, profile) == 0
    assert score_count(db_session, other_profile) == 0


async def test_client_cannot_control_id(
    client: AsyncClient, db_session: Session
):
    user = seed_user(db_session)
    profile = seed_profile(db_session, user)
    response = await client.post(
        "/me/profile/test-scores",
        json=score_payload(id=str(uuid.uuid4())),
        headers=auth_headers(user),
    )
    assert response.status_code == 422
    assert score_count(db_session, profile) == 0


async def test_create_validation_errors_return_422(
    client: AsyncClient, db_session: Session
):
    user = seed_user(db_session)
    profile = seed_profile(db_session, user)
    empty_type = await client.post(
        "/me/profile/test-scores",
        json=score_payload(test_type=""),
        headers=auth_headers(user),
    )
    negative = await client.post(
        "/me/profile/test-scores",
        json=score_payload(overall_score=-1),
        headers=auth_headers(user),
    )
    bad_range = await client.post(
        "/me/profile/test-scores",
        json=score_payload(test_date="2024-06-01", expires_at="2023-01-01"),
        headers=auth_headers(user),
    )
    assert empty_type.status_code == 422
    assert negative.status_code == 422
    assert bad_range.status_code == 422
    assert score_count(db_session, profile) == 0


async def test_date_fields_persist_correctly(
    client: AsyncClient, db_session: Session
):
    user = seed_user(db_session)
    seed_profile(db_session, user)
    body = await create_score(client, user)
    row = db_session.get(ScoreRecord, uuid.UUID(body["id"]))
    assert type(row.test_date) is date
    assert row.test_date == date(2024, 1, 15)
    assert type(row.expires_at) is date
    assert row.expires_at == date(2026, 1, 15)
    assert body["test_date"] == "2024-01-15"
    assert body["expires_at"] == "2026-01-15"


async def test_overall_score_persists(
    client: AsyncClient, db_session: Session
):
    user = seed_user(db_session)
    seed_profile(db_session, user)
    body = await create_score(client, user, overall_score=8.25)
    row = db_session.get(ScoreRecord, uuid.UUID(body["id"]))
    assert float(row.overall_score) == 8.25
    assert body["overall_score"] == 8.25


async def test_sub_scores_json_persists(
    client: AsyncClient, db_session: Session
):
    user = seed_user(db_session)
    seed_profile(db_session, user)
    payload_value = {"listening": 8.0, "sections": [{"name": "writing", "score": 6.5}]}
    body = await create_score(client, user, sub_scores=payload_value)
    row = db_session.get(ScoreRecord, uuid.UUID(body["id"]))
    assert row.sub_scores == payload_value
    assert body["sub_scores"] == payload_value


async def test_report_number_persists(
    client: AsyncClient, db_session: Session
):
    user = seed_user(db_session)
    seed_profile(db_session, user)
    body = await create_score(client, user, report_number="REPORT-99X")
    row = db_session.get(ScoreRecord, uuid.UUID(body["id"]))
    assert row.report_number == "REPORT-99X"
    assert body["report_number"] == "REPORT-99X"
    without = await create_score(client, user, report_number=None, test_type="TOEFL")
    assert without["report_number"] is None


async def test_create_response_contains_no_auth_material(
    client: AsyncClient, db_session: Session
):
    user = seed_user(db_session)
    seed_profile(db_session, user)
    response = await client.post(
        "/me/profile/test-scores",
        json=score_payload(),
        headers=auth_headers(user),
    )
    assert response.status_code == 201
    assert set(response.json()) == TEST_SCORE_READ_FIELDS
    assert "password" not in response.text
    assert "password_hash" not in response.text
    assert TEST_JWT_SECRET not in response.text


# --- PATCH /me/profile/test-scores/{test_score_id} ------------------------------------------

async def test_owner_can_update_score(
    client: AsyncClient, db_session: Session
):
    user = seed_user(db_session)
    seed_profile(db_session, user)
    created = await create_score(client, user)
    response = await client.patch(
        f"/me/profile/test-scores/{created['id']}",
        json={"test_type": "TOEFL iBT"},
        headers=auth_headers(user),
    )
    assert response.status_code == 200
    assert response.json()["test_type"] == "TOEFL iBT"


async def test_partial_update_preserves_omitted_fields(
    client: AsyncClient, db_session: Session
):
    user = seed_user(db_session)
    seed_profile(db_session, user)
    before = await create_score(client, user)
    response = await client.patch(
        f"/me/profile/test-scores/{before['id']}",
        json={"overall_score": 8.25},
        headers=auth_headers(user),
    )
    assert response.status_code == 200
    after = response.json()
    assert after["overall_score"] == 8.25
    for field in TEST_SCORE_READ_FIELDS - {"overall_score"}:
        assert after[field] == before[field], field


async def test_profile_ownership_cannot_change(
    client: AsyncClient, db_session: Session
):
    user = seed_user(db_session)
    profile = seed_profile(db_session, user)
    other = seed_user(db_session)
    other_profile = seed_profile(db_session, other)
    created = await create_score(client, user)
    response = await client.patch(
        f"/me/profile/test-scores/{created['id']}",
        json={"profile_id": str(other_profile.id)},
        headers=auth_headers(user),
    )
    assert response.status_code == 422
    row = db_session.get(ScoreRecord, uuid.UUID(created["id"]))
    assert row.profile_id == profile.id
    assert score_count(db_session, other_profile) == 0


async def test_id_cannot_change(client: AsyncClient, db_session: Session):
    user = seed_user(db_session)
    seed_profile(db_session, user)
    created = await create_score(client, user)
    response = await client.patch(
        f"/me/profile/test-scores/{created['id']}",
        json={"id": str(uuid.uuid4())},
        headers=auth_headers(user),
    )
    assert response.status_code == 422
    row = db_session.get(ScoreRecord, uuid.UUID(created["id"]))
    assert str(row.id) == created["id"]


async def test_patch_validation_errors_return_422(
    client: AsyncClient, db_session: Session
):
    user = seed_user(db_session)
    seed_profile(db_session, user)
    created = await create_score(client, user, test_date="2024-01-15", expires_at="2026-01-15")
    negative = await client.patch(
        f"/me/profile/test-scores/{created['id']}",
        json={"overall_score": -2},
        headers=auth_headers(user),
    )
    empty_type = await client.patch(
        f"/me/profile/test-scores/{created['id']}",
        json={"test_type": ""},
        headers=auth_headers(user),
    )
    broken_range = await client.patch(
        f"/me/profile/test-scores/{created['id']}",
        json={"expires_at": "2023-06-01"},
        headers=auth_headers(user),
    )
    assert negative.status_code == 422
    assert empty_type.status_code == 422
    assert broken_range.status_code == 422
    row = db_session.get(ScoreRecord, uuid.UUID(created["id"]))
    assert float(row.overall_score) == 7.5
    assert row.test_type == "IELTS"
    assert row.expires_at == date(2026, 1, 15)


async def test_another_users_score_cannot_be_modified(
    client: AsyncClient, db_session: Session
):
    victim = seed_user(db_session)
    victim_profile = seed_profile(db_session, victim)
    attacker = seed_user(db_session)
    seed_profile(db_session, attacker)
    target = await create_score(client, victim)
    response = await client.patch(
        f"/me/profile/test-scores/{target['id']}",
        json={"test_type": "Hijacked"},
        headers=auth_headers(attacker),
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Test score not found."
    row = db_session.get(ScoreRecord, uuid.UUID(target["id"]))
    assert row.test_type == "IELTS"
    assert row.profile_id == victim_profile.id


# --- DELETE /me/profile/test-scores/{test_score_id} -----------------------------------------

async def test_owner_can_delete_score(
    client: AsyncClient, db_session: Session
):
    user = seed_user(db_session)
    profile = seed_profile(db_session, user)
    created = await create_score(client, user)
    response = await client.delete(
        f"/me/profile/test-scores/{created['id']}", headers=auth_headers(user)
    )
    assert response.status_code == 204
    assert response.content == b""
    assert score_count(db_session, profile) == 0


async def test_another_users_score_cannot_be_deleted(
    client: AsyncClient, db_session: Session
):
    victim = seed_user(db_session)
    victim_profile = seed_profile(db_session, victim)
    attacker = seed_user(db_session)
    seed_profile(db_session, attacker)
    target = await create_score(client, victim)
    response = await client.delete(
        f"/me/profile/test-scores/{target['id']}", headers=auth_headers(attacker)
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Test score not found."
    assert score_count(db_session, victim_profile) == 1


async def test_delete_leaves_other_scores_untouched(
    client: AsyncClient, db_session: Session
):
    user = seed_user(db_session)
    profile = seed_profile(db_session, user)
    first = await create_score(client, user, test_date="2023-05-01", expires_at="2025-05-01")
    second = await create_score(client, user, test_type="TOEFL", test_date="2024-06-01", expires_at="2026-06-01")
    third = await create_score(client, user, test_type="GRE", test_date="2024-09-01", expires_at="2029-09-01")
    response = await client.delete(
        f"/me/profile/test-scores/{second['id']}", headers=auth_headers(user)
    )
    assert response.status_code == 204
    assert score_count(db_session, profile) == 2
    remaining = {
        row["id"]
        for row in (
            await client.get("/me/profile/test-scores", headers=auth_headers(user))
        ).json()
    }
    assert remaining == {first["id"], third["id"]}


async def test_deleted_row_is_gone_from_the_database(
    client: AsyncClient, db_session: Session
):
    user = seed_user(db_session)
    seed_profile(db_session, user)
    created = await create_score(client, user)
    response = await client.delete(
        f"/me/profile/test-scores/{created['id']}", headers=auth_headers(user)
    )
    assert response.status_code == 204
    assert db_session.get(ScoreRecord, uuid.UUID(created["id"])) is None


# --- Dates / domain -------------------------------------------------------------------------

async def test_test_date_follows_domain_schema(
    client: AsyncClient, db_session: Session
):
    user = seed_user(db_session)
    seed_profile(db_session, user)
    with_date = await create_score(client, user, test_date="2024-03-10")
    without_date = await create_score(client, user, test_date=None, expires_at=None, test_type="TOEFL")
    row = db_session.get(ScoreRecord, uuid.UUID(with_date["id"]))
    assert type(row.test_date) is date
    assert row.test_date == date(2024, 3, 10)
    assert without_date["test_date"] is None
    assert without_date["expires_at"] is None


async def test_expires_at_follows_domain_schema(
    client: AsyncClient, db_session: Session
):
    user = seed_user(db_session)
    seed_profile(db_session, user)
    created = await create_score(client, user, expires_at="2027-12-31")
    row = db_session.get(ScoreRecord, uuid.UUID(created["id"]))
    assert type(row.expires_at) is date
    assert row.expires_at == date(2027, 12, 31)
    assert created["expires_at"] == "2027-12-31"


async def test_no_automatic_expiry_logic_is_applied(
    client: AsyncClient, db_session: Session
):
    user = seed_user(db_session)
    seed_profile(db_session, user)
    already_expired = await create_score(
        client, user, test_date="2019-01-01", expires_at="2020-01-01"
    )
    response = await client.get(
        "/me/profile/test-scores", headers=auth_headers(user)
    )
    assert response.status_code == 200
    listed = [row["id"] for row in response.json()]
    assert already_expired["id"] in listed
    fetched = next(row for row in response.json() if row["id"] == already_expired["id"])
    assert fetched["expires_at"] == "2020-01-01"
    assert fetched == already_expired


async def test_sub_scores_round_trip_exactly(
    client: AsyncClient, db_session: Session
):
    user = seed_user(db_session)
    seed_profile(db_session, user)
    nested = {
        "listening": 8.0,
        "sections": [{"name": "writing", "score": 6.5}, {"name": "reading", "score": 7.0}],
        "meta": {"attempt": 2, "verified": True},
    }
    created = await create_score(client, user, sub_scores=nested)
    assert created["sub_scores"] == nested
    fetched = (
        await client.get("/me/profile/test-scores", headers=auth_headers(user))
    ).json()
    assert fetched[0]["sub_scores"] == nested
    untouched = await client.patch(
        f"/me/profile/test-scores/{created['id']}",
        json={"overall_score": 8.0},
        headers=auth_headers(user),
    )
    assert untouched.json()["sub_scores"] == nested
    fetched_again = (
        await client.get("/me/profile/test-scores", headers=auth_headers(user))
    ).json()
    assert fetched_again[0]["sub_scores"] == nested


# --- Security / ownership -------------------------------------------------------------------

async def test_user_a_cannot_patch_user_b_score(
    client: AsyncClient, db_session: Session
):
    victim = seed_user(db_session)
    seed_profile(db_session, victim)
    attacker = seed_user(db_session)
    seed_profile(db_session, attacker)
    target = await create_score(client, victim)
    response = await client.patch(
        f"/me/profile/test-scores/{target['id']}",
        json={"overall_score": 1.0},
        headers=auth_headers(attacker),
    )
    assert response.status_code == 404
    row = db_session.get(ScoreRecord, uuid.UUID(target["id"]))
    assert float(row.overall_score) == 7.5


async def test_user_a_cannot_delete_user_b_score(
    client: AsyncClient, db_session: Session
):
    victim = seed_user(db_session)
    victim_profile = seed_profile(db_session, victim)
    attacker = seed_user(db_session)
    seed_profile(db_session, attacker)
    target = await create_score(client, victim)
    response = await client.delete(
        f"/me/profile/test-scores/{target['id']}", headers=auth_headers(attacker)
    )
    assert response.status_code == 404
    assert score_count(db_session, victim_profile) == 1


async def test_user_a_cannot_create_on_user_b_profile(
    client: AsyncClient, db_session: Session
):
    victim = seed_user(db_session)
    victim_profile = seed_profile(db_session, victim)
    attacker = seed_user(db_session)
    attacker_profile = seed_profile(db_session, attacker)
    response = await client.post(
        "/me/profile/test-scores",
        json=score_payload(profile_id=str(victim_profile.id)),
        headers=auth_headers(attacker),
    )
    assert response.status_code == 422
    assert score_count(db_session, victim_profile) == 0
    assert score_count(db_session, attacker_profile) == 0


async def test_arbitrary_profile_id_cannot_change_ownership(
    client: AsyncClient, db_session: Session
):
    user = seed_user(db_session)
    profile = seed_profile(db_session, user)
    other = seed_user(db_session)
    other_profile = seed_profile(db_session, other)
    created = await create_score(client, user)
    patch_attempt = await client.patch(
        f"/me/profile/test-scores/{created['id']}",
        json={"profile_id": str(other_profile.id)},
        headers=auth_headers(user),
    )
    post_attempt = await client.post(
        "/me/profile/test-scores",
        json=score_payload(profile_id=str(other_profile.id)),
        headers=auth_headers(user),
    )
    assert patch_attempt.status_code == 422
    assert post_attempt.status_code == 422
    row = db_session.get(ScoreRecord, uuid.UUID(created["id"]))
    assert row.profile_id == profile.id
    assert score_count(db_session, other_profile) == 0
