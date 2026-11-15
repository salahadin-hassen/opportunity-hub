"""The database commit must happen before the response is sent (see ``app.db.session.get_db``).

These tests call the application through raw ASGI with the real ``get_db`` (no dependency override),
recording the order of session events and ASGI messages.
"""
from __future__ import annotations

import json
import re
import uuid
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.db import session as db_session_module
from app.main import app
from app.models import User
from tests.conftest import test_engine

APP_DIR = Path(__file__).resolve().parents[1] / "app"
PASSWORD = "order-password-123"


def test_every_get_db_dependency_is_function_scoped():
    """One request-scoped use would bring back commit-after-response for that route."""
    offenders = []
    for path in APP_DIR.rglob("*.py"):
        for number, line in enumerate(path.read_text().splitlines(), start=1):
            for match in re.finditer(r"Depends\(\s*get_db\b([^)]*)\)", line):
                if 'scope="function"' not in match.group(1):
                    offenders.append(f"{path.relative_to(APP_DIR)}:{number}")
    assert offenders == [], f'Use Depends(get_db, scope="function"): {offenders}'


async def _request(method: str, path: str, events: list[str], *, body: dict | None = None, token: str | None = None) -> bytes:
    """Send one request through the ASGI app; append ASGI message types to ``events``; return the body."""
    payload = json.dumps(body).encode() if body is not None else b""
    chunks: list[bytes] = []

    async def receive():
        return {"type": "http.request", "body": payload, "more_body": False}

    async def send(message):
        events.append(message["type"] + (f":{message['status']}" if "status" in message else ""))
        chunks.append(message.get("body", b""))

    headers = [(b"content-type", b"application/json"), (b"host", b"test")]
    if token:
        headers.append((b"authorization", f"Bearer {token}".encode()))
    scope = {
        "type": "http", "method": method, "path": path, "raw_path": path.encode(), "query_string": b"",
        "headers": headers, "scheme": "http", "server": ("test", 80), "client": ("203.0.113.9", 1234),
        "http_version": "1.1", "root_path": "", "asgi": {"version": "3.0"},
    }
    await app(scope, receive, send)
    return b"".join(chunks)


@pytest.fixture
def real_sessions(monkeypatch):
    """The real ``get_db`` against the test database, with commits, rollbacks and closes recorded."""
    events: list[str] = []

    class Recording(Session):
        fail_commit = False

        def commit(self) -> None:
            if Recording.fail_commit:
                events.append("commit failed")
                raise RuntimeError("commit failed")
            super().commit()
            events.append("commit")

        def rollback(self) -> None:
            super().rollback()
            events.append("rollback")

        def close(self) -> None:
            super().close()
            events.append("close")

    monkeypatch.setattr(db_session_module, "SessionLocal", sessionmaker(bind=test_engine, class_=Recording, autoflush=False))
    created: list[str] = []
    yield events, Recording, created
    Recording.fail_commit = False
    with Session(test_engine) as db, db.begin():
        for email in created:
            user = db.scalar(select(User).where(User.email == email))
            if user is not None:
                db.delete(user)


def _new_email(created: list[str]) -> str:
    email = f"order-{uuid.uuid4().hex[:10]}@example.org"
    created.append(email)
    return email


async def test_the_commit_precedes_the_response(real_sessions):
    events, _, created = real_sessions
    email = _new_email(created)
    await _request("POST", "/auth/register", events, body={"email": email, "password": PASSWORD})
    assert events.index("commit") < events.index("close") < events.index("http.response.start:201")
    with Session(test_engine) as db:  # durable, and visible to another connection, before the client hears back
        assert db.scalar(select(User).where(User.email == email)) is not None


async def test_a_failed_commit_is_rolled_back_and_answered_with_500_never_success(real_sessions):
    events, recording, created = real_sessions
    recording.fail_commit = True
    email = _new_email(created)
    with pytest.raises(RuntimeError, match="commit failed"):  # the server error middleware re-raises after replying
        await _request("POST", "/auth/register", events, body={"email": email, "password": PASSWORD})
    assert "http.response.start:201" not in events
    assert events.index("commit failed") < events.index("rollback") < events.index("close") < events.index("http.response.start:500")
    with Session(test_engine) as db:
        assert db.scalar(select(User).where(User.email == email)) is None


async def test_a_handler_error_rolls_back_without_committing(real_sessions):
    events, _, created = real_sessions
    email = _new_email(created)
    await _request("POST", "/auth/register", events, body={"email": email, "password": PASSWORD})
    events.clear()
    await _request("POST", "/auth/register", events, body={"email": email, "password": PASSWORD})  # duplicate: 409
    assert "commit" not in events
    assert events.index("rollback") < events.index("close") < events.index("http.response.start:409")


async def test_nested_dependencies_share_one_session_and_one_commit(real_sessions):
    """Authentication (``get_current_user``) and the handler use the same session: one commit, before the reply."""
    events, _, created = real_sessions
    email = _new_email(created)
    await _request("POST", "/auth/register", events, body={"email": email, "password": PASSWORD})
    token = json.loads(await _request("POST", "/auth/login", events, body={"email": email, "password": PASSWORD}))["access_token"]
    events.clear()
    await _request("POST", "/auth/logout", events, token=token)
    assert events.count("commit") == 1 and events.count("close") == 1
    assert events.index("commit") < events.index("http.response.start:200")
    events.clear()
    await _request("POST", "/auth/logout", events, token=token)  # the revocation was committed: now rejected
    assert "http.response.start:401" in events


async def test_read_requests_serialise_their_response_before_the_session_closes(real_sessions):
    events, _, _ = real_sessions
    body = await _request("GET", "/opportunities", events)
    assert isinstance(json.loads(body), list)
    assert events.index("close") < events.index("http.response.start:200")
