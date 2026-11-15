"""Sign in with Google, end to end through the API, against the test database.

Google itself is never contacted. Only its two network edges are replaced: the token endpoint
(``exchange_code`` returns an ID token we mint) and the key download (``signing_key`` returns our
test public key). Everything else is the production code path: the state and binding cookie, PKCE
parameters, the RS256 signature check, issuer/audience/expiry/nonce/email_verified validation, account
resolution by subject, the single-use handoff and session issuance. A real Google sign-in is not
simulated or claimed here.
"""
from __future__ import annotations

import time
import uuid
from urllib.parse import parse_qs, urlsplit

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.main import app
from app.models import AuditLog, ExternalIdentity, OAuthState, User
from app.services import google_oauth
from tests.test_auth import TEST_PASSWORD, make_user

FRONTEND = "https://app.example.test"
CLIENT_ID = "test-client.apps.googleusercontent.com"
ORIGIN = {"Origin": FRONTEND}
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


class FakeGoogle:
    """Stands in for Google's token endpoint: returns an ID token for the next ``user``."""

    def __init__(self) -> None:
        self.claims: dict = {}
        self.key = KEY
        self.overrides: dict = {}
        self.codes: list[tuple[str, str]] = []

    def user(self, sub: str | None = None, email: str | None = None, _no_subject: bool = False, **overrides) -> None:
        self.claims = {"sub": sub or f"g-{uuid.uuid4().hex}", "email": email or f"g-{uuid.uuid4().hex[:8]}@gmail.com",
                       "email_verified": True, "name": "Test Person"}
        self.overrides = {**overrides, **({"sub": None} if _no_subject else {})}

    def exchange_code(self, code: str, verifier: str) -> str:
        self.codes.append((code, verifier))
        now = int(time.time())
        payload = {"iss": "https://accounts.google.com", "aud": CLIENT_ID, "azp": CLIENT_ID, "iat": now,
                   "exp": now + 3600, "nonce": self.nonce, **self.claims}
        payload.update(self.overrides)
        payload = {k: v for k, v in payload.items() if v is not None}
        return jwt.encode(payload, self.key, algorithm="RS256", headers={"kid": "test"})


@pytest.fixture
def google(monkeypatch) -> FakeGoogle:
    fake = FakeGoogle()
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_ID", CLIENT_ID)
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_SECRET", "test-secret")
    monkeypatch.setattr(settings, "GOOGLE_REDIRECT_URI", "https://api.example.test/auth/google/callback")
    monkeypatch.setattr(settings, "CORS_ORIGINS", FRONTEND)
    monkeypatch.setattr(settings, "FRONTEND_URL", None)
    monkeypatch.setattr(google_oauth, "exchange_code", fake.exchange_code)
    monkeypatch.setattr(google_oauth, "signing_key", lambda token: KEY.public_key())
    return fake


@pytest.fixture
async def client(db_session: Session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


async def start(client: AsyncClient, google: FakeGoogle, *, path="/auth/google/start", headers=None, next=None) -> str:
    response = await client.post(path, json={"next": next} if next else {}, headers={**ORIGIN, **(headers or {})})
    assert response.status_code == 200, response.text
    url = urlsplit(response.json()["authorization_url"])
    query = {k: v[0] for k, v in parse_qs(url.query).items()}
    assert url.netloc == "accounts.google.com"
    assert query["client_id"] == CLIENT_ID and query["response_type"] == "code"
    assert query["code_challenge_method"] == "S256" and len(query["code_challenge"]) == 43
    assert query["scope"] == "openid email profile" and query["nonce"] and query["state"]
    assert "oh_oauth_binding" in client.cookies
    google.nonce = query["nonce"]
    return query["state"]


async def callback(client: AsyncClient, state: str, code: str = "auth-code-123", **extra) -> str:
    response = await client.get("/auth/google/callback", params={"state": state, "code": code, **extra})
    assert response.status_code == 303
    return response.headers["location"]


async def sign_in(client, google, **kw) -> dict:
    state = await start(client, google, **kw)
    location = await callback(client, state)
    assert location.startswith(f"{FRONTEND}/auth/google/complete#code="), location
    code = location.split("#code=")[1]
    response = await client.post("/auth/google/exchange", json={"code": code}, headers=ORIGIN)
    assert response.status_code == 200, response.text
    return response.json()


def binding_of(client: AsyncClient) -> str:
    return next(c.value for c in client.cookies.jar if c.name == "oh_oauth_binding")


def set_binding(client: AsyncClient, value: str) -> None:
    """Replace the browser's binding cookie, as another browser (or an attacker) would present it."""
    for c in list(client.cookies.jar):
        if c.name == "oh_oauth_binding":
            client.cookies.jar.clear(c.domain, c.path, c.name)
    client.cookies.set("oh_oauth_binding", value, domain="test.local", path="/")


def error_of(location: str) -> str:
    return parse_qs(urlsplit(location).query)["google_error"][0]


# --- success -----------------------------------------------------------------------------------------


async def test_a_new_google_user_gets_an_account_and_a_working_session(client, google, db_session):
    google.user(email="new.person@gmail.com")
    body = await sign_in(client, google, next="/opportunities")
    assert body["outcome"] == "signed_in" and body["is_new_user"] is True
    assert body["email"] == "new.person@gmail.com" and body["next"] == "/opportunities"
    user = db_session.scalar(select(User).where(User.email == "new.person@gmail.com"))
    assert user.password_hash is None and user.email_verified_at is not None and user.role == "student"
    identity = db_session.scalar(select(ExternalIdentity).where(ExternalIdentity.user_id == user.id))
    assert (identity.provider, identity.subject) == ("google", google.claims["sub"])
    assert db_session.scalar(select(AuditLog).where(AuditLog.action == "auth.account_created_with_google",
                                                    AuditLog.target_id == str(user.id))) is not None
    # The session works with the rest of the product, like a password sign-in's.
    token = body["access_token"]
    me = await client.get("/auth/identities", headers={"Authorization": f"Bearer {token}"})
    assert me.json() == {"has_password": False, "google_available": True, "google_linked": True,
                         "google_email": "new.person@gmail.com"}
    profile = await client.post("/me/profile", headers={"Authorization": f"Bearer {token}"},
                                json={"full_name": "New Person", "email": "new.person@gmail.com", "citizenships": ["KE"],
                                      "degree_level": "bachelor"})
    assert profile.status_code == 201, profile.text
    saved = await client.get("/me/saved-opportunities", headers={"Authorization": f"Bearer {token}"})
    assert saved.status_code == 200 and saved.json() == []
    # The PKCE verifier sent to the token endpoint is the one whose challenge went to Google.
    assert len(google.codes) == 1 and len(google.codes[0][1]) >= 43


async def test_an_existing_google_user_signs_in_to_the_same_account(client, google, db_session):
    google.user()
    first = await sign_in(client, google)
    sub, email = google.claims["sub"], google.claims["email"]
    google.user(sub=sub, email=email)
    second = await sign_in(client, google)
    assert first["is_new_user"] is True and second["is_new_user"] is False
    assert db_session.scalar(select(func.count()).select_from(User).where(User.email == email)) == 1
    assert first["access_token"] != second["access_token"]


async def test_the_subject_decides_the_account_not_a_changed_email(client, google, db_session):
    google.user(email="before@gmail.com")
    await sign_in(client, google)
    sub = google.claims["sub"]
    google.user(sub=sub, email="after@gmail.com")
    body = await sign_in(client, google)
    assert body["email"] == "before@gmail.com" and body["is_new_user"] is False


# --- account collisions and linking ------------------------------------------------------------------


async def test_an_existing_password_account_is_never_linked_by_email(client, google, db_session):
    user = make_user(email="Owner@Example.org")
    db_session.add(user)
    db_session.flush()
    google.user(email="owner@example.org")  # same address, different case
    location = await callback(client, await start(client, google))
    assert error_of(location) == "link_required" and location.startswith(f"{FRONTEND}/login?")
    assert db_session.scalar(select(ExternalIdentity).where(ExternalIdentity.user_id == user.id)) is None
    assert db_session.scalar(select(func.count()).select_from(User).where(func.lower(User.email) == "owner@example.org")) == 1


async def login(client, user_email) -> str:
    response = await client.post("/auth/login", json={"email": user_email, "password": TEST_PASSWORD})
    assert response.status_code == 200
    return response.json()["access_token"]


async def test_a_signed_in_owner_can_connect_google_and_then_sign_in_with_it(client, google, db_session):
    user = make_user()
    db_session.add(user)
    db_session.flush()
    token = await login(client, user.email)
    google.user(email=user.email)
    state = await start(client, google, path="/auth/google/link/start", headers={"Authorization": f"Bearer {token}"})
    location = await callback(client, state)
    code = location.split("#code=")[1]
    linked = await client.post("/auth/google/exchange", json={"code": code}, headers=ORIGIN)
    assert linked.json() == {"outcome": "linked", "access_token": None, "token_type": "bearer", "email": None,
                             "is_new_user": False, "next": "/profile"}
    assert db_session.scalar(select(AuditLog).where(AuditLog.action == "auth.identity_linked",
                                                    AuditLog.target_id == str(user.id))) is not None
    google.user(sub=google.claims["sub"], email=user.email)
    body = await sign_in(client, google)
    assert body["email"] == user.email and body["is_new_user"] is False


async def test_linking_needs_a_signed_in_user_and_a_trusted_origin(client, google, db_session):
    assert (await client.post("/auth/google/link/start", json={}, headers=ORIGIN)).status_code == 401
    user = make_user()
    db_session.add(user)
    db_session.flush()
    token = await login(client, user.email)
    evil = await client.post("/auth/google/link/start", json={},
                             headers={"Origin": "https://evil.example", "Authorization": f"Bearer {token}"})
    assert evil.status_code == 403


async def test_a_google_account_already_linked_elsewhere_is_refused(client, google, db_session):
    google.user()
    await sign_in(client, google)  # the Google account now belongs to a new user
    taken_sub = google.claims["sub"]
    other = make_user()
    db_session.add(other)
    db_session.flush()
    token = await login(client, other.email)
    google.user(sub=taken_sub, email=google.claims["email"])
    state = await start(client, google, path="/auth/google/link/start", headers={"Authorization": f"Bearer {token}"})
    location = await callback(client, state)
    assert error_of(location) == "identity_in_use" and location.startswith(f"{FRONTEND}/profile?")
    assert db_session.scalar(select(ExternalIdentity).where(ExternalIdentity.user_id == other.id)) is None


async def test_a_second_google_account_cannot_be_linked_while_one_is_connected(client, google, db_session):
    user = make_user()
    db_session.add(user)
    db_session.flush()
    token = await login(client, user.email)
    for expected in (None, "already_linked"):
        google.user()
        state = await start(client, google, path="/auth/google/link/start", headers={"Authorization": f"Bearer {token}"})
        location = await callback(client, state)
        if expected:
            assert error_of(location) == expected
        else:
            await client.post("/auth/google/exchange", json={"code": location.split("#code=")[1]}, headers=ORIGIN)


async def test_a_disconnected_google_account_must_be_linked_again_explicitly(client, google, db_session):
    user = make_user()
    db_session.add(user)
    db_session.flush()
    token = await login(client, user.email)
    auth = {"Authorization": f"Bearer {token}"}
    google.user(email=user.email)
    state = await start(client, google, path="/auth/google/link/start", headers=auth)
    await client.post("/auth/google/exchange", json={"code": (await callback(client, state)).split("#code=")[1]}, headers=ORIGIN)
    sub = google.claims["sub"]
    assert (await client.delete("/auth/google/link", headers=auth)).status_code == 204
    assert db_session.scalar(select(AuditLog).where(AuditLog.action == "auth.identity_unlinked",
                                                    AuditLog.target_id == str(user.id))) is not None
    google.user(sub=sub, email=user.email)
    location = await callback(client, await start(client, google))
    assert error_of(location) == "link_required"


async def test_google_cannot_be_disconnected_from_an_account_with_no_password(client, google):
    google.user()
    body = await sign_in(client, google)
    response = await client.delete("/auth/google/link", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert response.status_code == 409


# --- token validation --------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        ({"aud": "someone-else.apps.googleusercontent.com"}, "token_invalid"),
        ({"azp": "someone-else.apps.googleusercontent.com"}, "token_invalid"),
        ({"iss": "https://evil.example"}, "token_invalid"),
        ({"exp": int(time.time()) - 3600, "iat": int(time.time()) - 7200}, "token_invalid"),
        ({"nonce": "not-the-nonce"}, "token_invalid"),
        ({"email_verified": False}, "email_unverified"),
        ({"email_verified": None}, "email_unverified"),
        ({"_no_subject": True}, "token_invalid"),
    ],
)
async def test_tokens_that_fail_validation_never_sign_anyone_in(client, google, db_session, change, expected):
    google.user(**change)
    before = db_session.scalar(select(func.count()).select_from(User))
    location = await callback(client, await start(client, google))
    assert error_of(location) == expected
    assert db_session.scalar(select(func.count()).select_from(User)) == before


async def test_a_token_signed_by_another_key_is_rejected(client, google, db_session):
    google.user()
    google.key = OTHER_KEY
    assert error_of(await callback(client, await start(client, google))) == "token_invalid"


async def test_a_token_the_provider_failed_to_issue_is_reported_as_a_provider_error(client, google, monkeypatch):
    google.user()

    def broken(code, verifier):
        raise google_oauth.GoogleSignInError("provider_error", "token endpoint answered 400")

    monkeypatch.setattr(google_oauth, "exchange_code", broken)
    assert error_of(await callback(client, await start(client, google))) == "provider_error"


# --- state, binding and replay -----------------------------------------------------------------------


async def test_an_unknown_or_missing_state_is_refused(client, google):
    google.user()
    await start(client, google)
    assert error_of(await callback(client, "not-a-state")) == "state_invalid"
    response = await client.get("/auth/google/callback", params={"code": "x"})
    assert error_of(response.headers["location"]) == "state_invalid"


async def test_a_state_from_another_browser_is_refused(client, google, db_session):
    google.user()
    state = await start(client, google)
    set_binding(client, "someone-elses-binding")
    assert error_of(await callback(client, state)) == "state_invalid"
    # and it is spent: the real browser can't use it afterwards either
    assert db_session.scalar(select(OAuthState.consumed_at).where(OAuthState.state_hash == google_oauth._hash(state))) is not None


async def test_a_replayed_callback_is_refused(client, google, db_session):
    google.user()
    state = await start(client, google)
    first = await callback(client, state)
    assert "#code=" in first
    assert error_of(await callback(client, state)) == "state_invalid"
    assert len(google.codes) == 1  # the replay never reached the token endpoint


async def test_an_expired_state_is_refused(client, google, db_session):
    google.user()
    state = await start(client, google)
    row = db_session.scalar(select(OAuthState).where(OAuthState.state_hash == google_oauth._hash(state)))
    row.expires_at = row.created_at
    db_session.flush()
    assert error_of(await callback(client, state)) == "state_invalid"


async def test_a_cancelled_consent_is_reported_and_spends_the_state(client, google):
    state = await start(client, google)
    response = await client.get("/auth/google/callback", params={"state": state, "error": "access_denied"})
    assert error_of(response.headers["location"]) == "cancelled"
    assert error_of(await callback(client, state)) == "state_invalid"


async def test_the_handoff_code_works_once_and_only_in_the_same_browser(client, google):
    google.user()
    location = await callback(client, await start(client, google))
    code = location.split("#code=")[1]
    binding = binding_of(client)
    client.cookies.clear()
    # Without the browser's binding cookie the code is useless (and not spent: it was never usable here).
    stolen = await client.post("/auth/google/exchange", json={"code": code}, headers=ORIGIN)
    assert stolen.status_code == 401
    set_binding(client, binding)
    assert (await client.post("/auth/google/exchange", json={"code": code}, headers=ORIGIN)).status_code == 200
    # Single use: the same code again is refused.
    assert (await client.post("/auth/google/exchange", json={"code": code}, headers=ORIGIN)).status_code == 401
    # A present but wrong binding cookie spends the code, so it can't then be used even by its own browser.
    google.user()
    location = await callback(client, await start(client, google))
    code, binding = location.split("#code=")[1], binding_of(client)
    set_binding(client, "an-attackers-binding")
    assert (await client.post("/auth/google/exchange", json={"code": code}, headers=ORIGIN)).status_code == 401
    set_binding(client, binding)
    assert (await client.post("/auth/google/exchange", json={"code": code}, headers=ORIGIN)).status_code == 401


async def test_starting_and_exchanging_need_a_trusted_origin(client, google):
    assert (await client.post("/auth/google/start", json={})).status_code == 403
    assert (await client.post("/auth/google/start", json={}, headers={"Origin": "https://evil.example"})).status_code == 403
    assert (await client.post("/auth/google/exchange", json={"code": "x" * 20})).status_code == 403


async def test_only_same_site_paths_are_kept_as_the_destination(client, google, db_session):
    for bad in ("https://evil.example/x", "//evil.example", "/\\evil.example", "javascript:alert(1)"):
        state = await start(client, google, next=bad)
        row = db_session.scalar(select(OAuthState).where(OAuthState.state_hash == google_oauth._hash(state)))
        assert row.next_path is None


# --- configuration and regression ----------------------------------------------------------------------


async def test_without_configuration_google_is_hidden_and_its_endpoints_are_absent(client, monkeypatch):
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_ID", None)
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_SECRET", None)
    monkeypatch.setattr(settings, "GOOGLE_REDIRECT_URI", None)
    assert (await client.get("/auth/providers")).json() == {"password": True, "google": False}
    assert (await client.post("/auth/google/start", json={}, headers=ORIGIN)).status_code == 404
    assert (await client.get("/auth/google/callback", params={"state": "x", "code": "y"})).status_code == 404


async def test_password_sign_in_is_unchanged_and_refuses_password_less_accounts(client, google, db_session):
    user = make_user()
    db_session.add(user)
    db_session.flush()
    assert (await client.post("/auth/login", json={"email": user.email, "password": TEST_PASSWORD})).status_code == 200
    assert (await client.post("/auth/login", json={"email": user.email, "password": "wrong-password-1"})).status_code == 401
    google.user()
    await sign_in(client, google)
    email = google.claims["email"]
    assert (await client.post("/auth/login", json={"email": email, "password": "anything-at-all-1"})).status_code == 401
    # registering the address again is a conflict, as for any existing account
    assert (await client.post("/auth/register", json={"email": email, "password": TEST_PASSWORD})).status_code == 409


def test_half_a_google_configuration_is_rejected_at_startup():
    from app.core.config import Settings

    with pytest.raises(ValueError, match="together"):
        Settings(DATABASE_URL="postgresql://x@localhost/y", JWT_SECRET="x" * 40, GOOGLE_CLIENT_ID="only-this")
