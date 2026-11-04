"""Bounded Argon2 capacity and duplicate-email rejection before hashing.

Every password hash and verification passes one per-process gate
(``app.core.security.PasswordHashGate``) that admits a fixed number of
operations and refuses the rest at once with 503: no queue, no Argon2 work
for refused requests, and a slot is freed only when the work itself ends.
Registration looks the email up before hashing, and the unique constraint
still settles concurrent registrations.

Most tests swap Argon2 for a controllable hasher that blocks until the test
lets it go, so concurrency is arranged with semaphores and barriers instead of
sleeps. Every wait has a safety timeout, so a regression fails rather than
hanging the suite.
"""
from __future__ import annotations

import asyncio
import logging
import os
import queue
import socket
import subprocess
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import anyio.to_thread
import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from sqlalchemy import create_engine, delete, event, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.core import auth_telemetry, rate_limit, security
from app.core.config import Settings, settings
from app.core.security import PasswordHashCapacityExceeded, PasswordHashGate, hash_password, verify_password
from app.db.session import get_db
from app.main import app
from app.models import User
from app.schemas import UserCreate
from app.services.users import EmailAlreadyRegisteredError, authenticate_user, create_user

BACKEND_DIR = Path(__file__).resolve().parents[1]
WAIT = 10  # safety timeout in seconds: never an expected duration
PASSWORD = "long-enough-password"


class ControlledHasher:
    """Stands in for argon2's PasswordHasher: counts calls and concurrency, and blocks until allowed."""

    def __init__(self, *, blocking: bool = True) -> None:
        self._lock = threading.Lock()
        self._entered = threading.Semaphore(0)
        self._proceed = threading.Semaphore(0)
        self.blocking = blocking
        self.blocking_ops = {"hash", "verify"}  # which operations park while ``blocking`` is set
        self.calls = 0
        self.calls_by_op = {"hash": 0, "verify": 0}
        self.peak_by_op = {"hash": 0, "verify": 0}
        self._running_by_op = {"hash": 0, "verify": 0}
        self.running = 0
        self.peak = 0
        self.fail = False
        self.barrier: threading.Barrier | None = None

    def _work(self, op: str, result):
        with self._lock:
            self.calls += 1
            self.calls_by_op[op] += 1
            self.running += 1
            self._running_by_op[op] += 1
            self.peak = max(self.peak, self.running)
            self.peak_by_op[op] = max(self.peak_by_op[op], self._running_by_op[op])
            parks = self.blocking and op in self.blocking_ops
        self._entered.release()
        try:
            if self.barrier is not None:
                self.barrier.wait(timeout=WAIT)
            if parks and not self._proceed.acquire(timeout=WAIT):
                raise AssertionError("controlled hasher was never released")
            if self.fail:
                raise RuntimeError("simulated Argon2 failure")
            return result
        finally:
            with self._lock:
                self.running -= 1
                self._running_by_op[op] -= 1

    def hash(self, password: str) -> str:
        return self._work("hash", "$argon2id$v=19$m=65536,t=3,p=4$controlled$controlled")

    def verify(self, password_hash: str, password: str) -> bool:
        return self._work("verify", password == PASSWORD)

    def wait_entered(self, count: int = 1) -> None:
        for _ in range(count):
            assert self._entered.acquire(timeout=WAIT), "no operation entered the hasher"

    def release(self, count: int = 1) -> None:
        for _ in range(count):
            self._proceed.release()

    def open(self) -> None:
        """Let every parked and future operation through, leaving no spare permits behind."""
        self.blocking = False
        with self._lock:
            parked = self.running
        self.release(parked)



@pytest.fixture
def gate(monkeypatch):
    """Install a gate; ``registration`` defaults to the whole capacity (no isolation) unless a test sets it."""

    def install(capacity: int = 2, registration: int | None = None) -> PasswordHashGate:
        installed = PasswordHashGate(capacity, registration)
        monkeypatch.setattr(security, "password_hash_gate", installed)
        return installed

    return install


@pytest.fixture
def hasher(monkeypatch):
    controlled = ControlledHasher()
    monkeypatch.setattr(security, "_password_hasher", controlled)
    yield controlled
    controlled.open()  # never leave a worker thread parked


@pytest.fixture
def api(db_session: Session, monkeypatch):
    monkeypatch.setattr(settings, "AUTH_RATE_LIMIT_PER_MINUTE", None)
    app.dependency_overrides[get_db] = lambda: (yield db_session)
    auth_telemetry.reset()
    yield
    app.dependency_overrides.clear()
    auth_telemetry.reset()


async def _post(path: str, body: dict, address: str = "203.0.113.10") -> httpx.Response:
    transport = ASGITransport(app=app, client=(address, 40000))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        return await asyncio.wait_for(client.post(path, json=body), WAIT)


async def _register(email: str, password: str = PASSWORD) -> httpx.Response:
    return await _post("/auth/register", {"email": email, "password": password})


async def _login(email: str, password: str = PASSWORD) -> httpx.Response:
    return await _post("/auth/login", {"email": email, "password": password})


def _free_slots(installed: PasswordHashGate) -> int:
    return installed.capacity - installed.active


def _hold_in_threads(count: int, operation) -> list[threading.Thread]:
    threads = [threading.Thread(target=operation, daemon=True) for _ in range(count)]
    for thread in threads:
        thread.start()
    return threads


# --- The gate itself -----------------------------------------------------------------------------------


def test_the_limit_is_never_exceeded_and_the_rest_are_refused_at_once(gate, hasher):
    installed = gate(3)
    outcomes: queue.Queue[str] = queue.Queue()

    def attempt():
        try:
            hash_password(PASSWORD)
            outcomes.put("hashed")
        except PasswordHashCapacityExceeded:
            outcomes.put("refused")

    threads = _hold_in_threads(10, attempt)
    refused = [outcomes.get(timeout=WAIT) for _ in range(7)]  # arrive while three hashes are still parked
    assert refused == ["refused"] * 7
    assert hasher.calls == 3 and hasher.peak == 3 and installed.active == 3
    hasher.release(3)
    for thread in threads:
        thread.join(WAIT)
    assert sorted(outcomes.get_nowait() for _ in range(3)) == ["hashed"] * 3
    assert installed.active == 0 and _free_slots(installed) == 3


def test_refused_operations_do_no_argon2_work(gate, hasher):
    gate(1)
    holder = _hold_in_threads(1, lambda: hash_password(PASSWORD))
    hasher.wait_entered()
    for _ in range(5):
        with pytest.raises(PasswordHashCapacityExceeded):
            verify_password(PASSWORD, "$argon2id$whatever")
        with pytest.raises(PasswordHashCapacityExceeded):
            hash_password(PASSWORD)
    assert hasher.calls == 1
    hasher.release()
    holder[0].join(WAIT)


def test_a_slot_is_released_after_success_a_wrong_password_and_an_exception(gate):
    installed = gate(1)
    stored = hash_password(PASSWORD)  # real Argon2
    assert installed.active == 0
    assert verify_password(PASSWORD, stored) is True
    assert verify_password("wrong-password", stored) is False
    assert verify_password(PASSWORD, "not-a-hash") is False
    assert installed.active == 0 and _free_slots(installed) == 1


def test_a_slot_is_released_exactly_once_after_an_argon2_exception(gate, hasher):
    installed = gate(1)
    hasher.fail = True
    hasher.open()
    with pytest.raises(RuntimeError):
        hash_password(PASSWORD)
    assert installed.active == 0 and _free_slots(installed) == 1
    hasher.fail = False
    assert hash_password(PASSWORD).startswith("$argon2id$")  # the slot is usable again


def test_a_double_release_is_detected_rather_than_over_admitting(gate):
    installed = gate(1)
    with pytest.raises(RuntimeError):
        with installed.slot("login"):
            installed._active["login"] -= 1  # a stray release from elsewhere while the slot is held
    installed._active["login"] = 0


@pytest.mark.parametrize("dispatch", ["run_in_threadpool", "asyncio.to_thread"])
async def test_a_cancelled_request_keeps_its_slot_until_argon2_actually_ends(gate, hasher, dispatch):
    """FastAPI runs sync handlers via run_in_threadpool; cancelling the awaiting task (measured with
    anyio 4.15) returns at once while the worker thread runs on. The slot must follow the thread."""
    installed = gate(1)
    finished = threading.Event()

    def operation():
        try:
            hash_password(PASSWORD)
        finally:
            finished.set()  # set after the gate's own finally has run

    runner = run_in_threadpool(operation) if dispatch == "run_in_threadpool" else asyncio.to_thread(operation)
    task = asyncio.create_task(runner)
    await asyncio.to_thread(hasher.wait_entered)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, WAIT)
    assert not finished.is_set()  # the request is gone, Argon2 is not
    assert installed.active == 1  # so the slot is still taken...
    with pytest.raises(PasswordHashCapacityExceeded):
        hash_password(PASSWORD)  # ...and nobody else gets it
    hasher.release()
    assert await asyncio.to_thread(finished.wait, WAIT)
    assert installed.active == 0 and _free_slots(installed) == 1  # released once, after the work ended


def test_capacity_settings_are_validated():
    def make(**values):
        return Settings(_env_file=None, DATABASE_URL="postgresql://u@h/db", JWT_SECRET="s" * 40, **values)

    assert make().ARGON2_MAX_CONCURRENCY == 2
    assert make(ARGON2_MAX_CONCURRENCY=1).ARGON2_MAX_CONCURRENCY == 1
    assert make(ARGON2_MAX_CONCURRENCY=16).ARGON2_MAX_CONCURRENCY == 16
    for bad in (0, -1, 17, "many", 2.5):
        with pytest.raises(ValidationError):
            make(ARGON2_MAX_CONCURRENCY=bad)
    assert make().ARGON2_REGISTRATION_MAX_CONCURRENCY == 1
    assert make(ARGON2_MAX_CONCURRENCY=1, ARGON2_REGISTRATION_MAX_CONCURRENCY=1).ARGON2_REGISTRATION_MAX_CONCURRENCY == 1
    assert make(ARGON2_MAX_CONCURRENCY=8, ARGON2_REGISTRATION_MAX_CONCURRENCY=8).ARGON2_REGISTRATION_MAX_CONCURRENCY == 8
    for bad in (0, -1, 17, "many"):
        with pytest.raises(ValidationError):
            make(ARGON2_REGISTRATION_MAX_CONCURRENCY=bad)
    with pytest.raises(ValidationError):
        make(ARGON2_MAX_CONCURRENCY=2, ARGON2_REGISTRATION_MAX_CONCURRENCY=3)  # can't exceed the total
    with pytest.raises(ValueError):
        PasswordHashGate(0)
    with pytest.raises(ValueError):
        PasswordHashGate(2, 0)
    with pytest.raises(ValueError):
        PasswordHashGate(2, 3)


def test_the_process_gate_uses_the_configured_capacity():
    assert security.password_hash_gate.capacity == settings.ARGON2_MAX_CONCURRENCY == 2
    assert security.password_hash_gate.registration_capacity == settings.ARGON2_REGISTRATION_MAX_CONCURRENCY == 1


def test_every_argon2_call_in_the_application_goes_through_the_gate():
    """Only app/core/security.py may touch the hasher; everything else calls hash_password/verify_password."""
    offenders = []
    for path in (BACKEND_DIR / "app").rglob("*.py"):
        source = path.read_text()
        if path.name == "security.py":
            continue
        for marker in ("PasswordHasher", "_password_hasher", "import argon2", "from argon2"):
            if marker in source:
                offenders.append(f"{path.relative_to(BACKEND_DIR)}: {marker}")
    assert offenders == []


# --- Through the API ---------------------------------------------------------------------------------


async def test_login_and_registration_share_one_capacity(api, gate, hasher):
    installed = gate(1)
    registering = asyncio.create_task(_register("share-a@example.org"))
    await asyncio.to_thread(hasher.wait_entered)  # the registration holds the only slot, inside Argon2
    login = await _login("share-a@example.org")
    other_registration = await _register("share-b@example.org")
    assert (login.status_code, other_registration.status_code) == (503, 503)
    hasher.release()
    assert (await asyncio.wait_for(registering, WAIT)).status_code == 201
    assert hasher.calls == 1 and installed.active == 0

    verifying = asyncio.create_task(_login("share-a@example.org"))
    await asyncio.to_thread(hasher.wait_entered)  # now a login holds it
    assert (await _register("share-c@example.org")).status_code == 503
    hasher.release()
    assert (await asyncio.wait_for(verifying, WAIT)).status_code == 200


async def test_capacity_exhaustion_is_a_generic_503_not_a_credential_failure(api, gate, hasher, caplog):
    gate(1)
    hasher.open()
    assert (await _register("known@example.org")).status_code == 201
    hasher.blocking = True
    holder = _hold_in_threads(1, lambda: hash_password(PASSWORD))
    hasher.wait_entered(2)  # the registration above, then the holder
    with caplog.at_level(logging.WARNING, logger="app.auth_telemetry"):
        known_right = await _login("known@example.org")
        known_wrong = await _login("known@example.org", "wrong-password")
        unknown = await _login("unknown@example.org")
        new_account = await _register("brand-new@example.org")
    for response in (known_right, known_wrong, unknown, new_account):
        assert response.status_code == 503
        assert response.headers["Retry-After"] == "2"
        assert response.json() == {"detail": "The service is busy. Please try again in a moment."}
    # Identical for known and unknown emails, so overload reveals nothing about which accounts exist.
    assert known_right.json() == unknown.json() and known_right.headers["Retry-After"] == unknown.headers["Retry-After"]
    assert hasher.calls == 2  # none of the refused requests reached Argon2 (no dummy hashes either)
    exhausted = {"limit": "total"}
    assert auth_telemetry.count("password_hash_capacity_exhausted", endpoint="/auth/login", operation="verify", **exhausted) == 3
    assert auth_telemetry.count("password_hash_capacity_exhausted", endpoint="/auth/register", operation="hash", **exhausted) == 1
    assert auth_telemetry.count("auth_failure", endpoint="/auth/login") == 0  # not reported as a failure
    logged = " ".join(record.getMessage() for record in caplog.records)
    assert "known@" not in logged and "unknown@" not in logged and "203.0.113" not in logged and PASSWORD not in logged
    hasher.open()
    holder[0].join(WAIT)
    assert (await _login("known@example.org")).status_code == 200  # the correct password works once a slot frees


async def test_a_full_default_thread_pool_still_gets_prompt_refusals(api, gate, hasher):
    """Hashing never holds more worker threads than slots, so a spare thread serves the refusal at once."""
    limiter = anyio.to_thread.current_default_thread_limiter()
    original = limiter.total_tokens
    limiter.total_tokens = 3
    try:
        gate(2)
        first = asyncio.create_task(_register("pool-a@example.org"))
        await asyncio.to_thread(hasher.wait_entered)
        second = asyncio.create_task(_register("pool-b@example.org"))
        await asyncio.to_thread(hasher.wait_entered)
        assert limiter.borrowed_tokens == 2
        assert (await _login("pool-a@example.org")).status_code == 503  # third thread, refused without waiting
        hasher.release()
        done, pending = await asyncio.wait({first, second}, timeout=WAIT, return_when=asyncio.FIRST_COMPLETED)
        hasher.release()
        results = [task.result().status_code for task in done] + [
            (await asyncio.wait_for(task, WAIT)).status_code for task in pending
        ]
        assert sorted(results) == [201, 201]
    finally:
        limiter.total_tokens = original


async def test_a_database_outage_is_503_and_never_hashes(gate, hasher, monkeypatch):
    installed = gate(2)
    hasher.open()
    monkeypatch.setattr(settings, "AUTH_RATE_LIMIT_PER_MINUTE", None)
    dead = Session(bind=create_engine("postgresql://nobody@127.0.0.1:1/none", connect_args={"connect_timeout": 1}))
    app.dependency_overrides[get_db] = lambda: (yield dead)
    try:
        register = await _register("outage@example.org")
        login = await _login("outage@example.org")
    finally:
        app.dependency_overrides.clear()
    for response in (register, login):
        assert response.status_code == 503
        assert response.headers["Retry-After"] == str(rate_limit.STORE_UNAVAILABLE_RETRY_AFTER)
    assert hasher.calls == 0  # the lookup failed, so nothing assumed the email was new
    assert installed.active == 0  # the login's slot was released when the lookup raised


# --- Registration before hashing ------------------------------------------------------------------------


async def test_an_existing_email_is_a_409_without_hashing(api, gate, hasher):
    gate(2)
    hasher.open()
    first = await _register("dup@example.org")
    assert first.status_code == 201 and hasher.calls == 1
    again = await _register("dup@example.org")
    assert again.status_code == 409
    assert again.json() == {"detail": "An account with this email already exists."}
    assert hasher.calls == 1  # exactly one hash in total: the new account's
    assert set(first.json()) == {"id", "email", "is_active", "created_at", "updated_at"}  # UserRead, unchanged


async def test_a_409_is_returned_even_when_capacity_is_exhausted(api, gate, hasher):
    """The duplicate check needs no slot, so known emails get the same 409 as before under load."""
    gate(1)
    hasher.open()
    assert (await _register("dup2@example.org")).status_code == 201
    hasher.blocking = True
    holder = _hold_in_threads(1, lambda: hash_password(PASSWORD))
    hasher.wait_entered(2)
    assert (await _register("dup2@example.org")).status_code == 409
    assert (await _register("fresh2@example.org")).status_code == 503
    assert hasher.calls == 2
    hasher.release()
    holder[0].join(WAIT)


async def test_normalisation_matches_the_unique_constraint(api, gate, hasher, db_session):
    gate(2)
    hasher.open()
    assert (await _register("Mixed.Case@Example.ORG")).status_code == 201
    assert db_session.scalar(select(User.email).where(User.email.ilike("mixed.case@example.org"))) == "Mixed.Case@example.org"
    calls = hasher.calls
    # The schema lower-cases the domain and trims spaces, so these are the stored value: 409, no hash.
    for same in ("Mixed.Case@example.org", "Mixed.Case@EXAMPLE.org", "  Mixed.Case@example.org  "):
        assert (await _register(same)).status_code == 409
    assert hasher.calls == calls
    # The local part keeps its case, and the constraint compares exactly, so this was and stays a new account.
    assert (await _register("mixed.case@example.org")).status_code == 201


def test_the_unique_constraint_is_still_enforced(db_session):
    db_session.add(User(email="constraint@example.org", password_hash="x"))
    db_session.flush()
    with pytest.raises(IntegrityError):
        with db_session.begin_nested():
            db_session.add(User(email="constraint@example.org", password_hash="y"))
            db_session.flush()
    unique = db_session.execute(
        text(
            "SELECT 1 FROM pg_indexes WHERE tablename = 'users' AND indexdef ILIKE '%UNIQUE%' AND indexdef ILIKE '%(email)%'"
        )
    ).first()
    assert unique is not None


def test_concurrent_registrations_of_one_email_give_one_account_and_one_conflict(gate, hasher):
    """Both pass the lookup (held together at a barrier inside Argon2); the constraint picks the winner."""
    gate(2)
    hasher.open()
    hasher.barrier = threading.Barrier(2)
    email = f"race-{uuid.uuid4().hex[:12]}@example.org"
    engine = create_engine(settings.DATABASE_URL)
    payload = UserCreate(email=email, password=PASSWORD)

    def register() -> tuple[str, bool]:
        with Session(engine) as session:
            try:
                create_user(session, payload)
                session.commit()
                return "created", True
            except EmailAlreadyRegisteredError:
                usable = session.execute(text("SELECT 1")).scalar() == 1  # the savepoint left it usable
                session.commit()
                return "conflict", usable

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = sorted(pool.map(lambda _: register(), range(2)))
        assert outcomes == [("conflict", True), ("created", True)]
        assert hasher.calls == 2  # both had passed the lookup, which is why the constraint matters
        with Session(engine) as session:
            assert session.scalar(select(text("count(*)")).select_from(User).where(User.email == email)) == 1
    finally:
        with engine.begin() as connection:
            connection.execute(delete(User).where(User.email == email))
        engine.dispose()


async def test_registration_rate_limit_accounting_is_unchanged(api, gate, hasher, monkeypatch):
    gate(1)
    hasher.open()
    monkeypatch.setattr(settings, "AUTH_RATE_LIMIT_PER_MINUTE", 2)
    rate_limit.set_limiter(None)
    rate_limit.reset()
    rate_limit.set_limiter(rate_limit.PostgresRateLimiter(rate_limit.get_limiter().engine, clock=lambda: 1_800_000_000.0))
    try:
        statuses = [(await _post("/auth/register", {"email": "acct@example.org", "password": PASSWORD}, f"192.0.2.{i}")).status_code for i in (1, 2, 3)]
        assert statuses == [201, 409, 429]  # as before: the conflict still spends the account budget
        hasher.blocking = True
        holder = _hold_in_threads(1, lambda: hash_password(PASSWORD))
        hasher.wait_entered(2)
        busy = await _post("/auth/register", {"email": "acct2@example.org", "password": PASSWORD}, "192.0.2.9")
        assert busy.status_code == 503
        with rate_limit.get_limiter().engine.connect() as connection:
            counted = connection.execute(
                text("SELECT count FROM rate_limit_buckets WHERE key = :key"),
                {"key": rate_limit.subject_key("account", "acct2@example.org")},
            ).scalar()
        assert counted == 1  # a capacity refusal is still an attempt, counted before the handler hashes
        hasher.release()
        holder[0].join(WAIT)
    finally:
        rate_limit.set_limiter(None)
        rate_limit.reset()


# --- Login compatibility ------------------------------------------------------------------------------


async def test_login_responses_are_unchanged(api, gate):
    gate(2)  # real Argon2
    assert (await _register("compat@example.org")).status_code == 201
    ok = await _login("compat@example.org")
    wrong = await _login("compat@example.org", "wrong-password")
    unknown = await _login("nobody-compat@example.org", "wrong-password")
    assert ok.status_code == 200 and set(ok.json()) == {"access_token", "token_type"} and ok.json()["token_type"] == "bearer"
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()
    assert wrong.headers.get("www-authenticate") == unknown.headers.get("www-authenticate")


async def test_unknown_emails_still_do_no_hashing(api, gate, hasher):
    gate(1)
    hasher.open()
    assert (await _login("nobody-hash@example.org")).status_code == 401
    assert hasher.calls == 0  # no dummy hash was introduced


# --- A real uvicorn process ------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def capacity_server():
    """uvicorn (one worker), 3 Argon2 slots of which registration may use 2, no rate limit, real Argon2."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    env = {**os.environ, "APP_ENV": "development", "DATABASE_URL": settings.DATABASE_URL, "JWT_SECRET": "c" * 40,
           "ARGON2_MAX_CONCURRENCY": "3", "ARGON2_REGISTRATION_MAX_CONCURRENCY": "2"}
    env.pop("AUTH_RATE_LIMIT_PER_MINUTE", None)
    env.pop("WEB_CONCURRENCY", None)
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port), "--no-proxy-headers"],
        cwd=BACKEND_DIR, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    base = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            if httpx.get(f"{base}/health", timeout=1).status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.1)
    else:
        process.terminate()
        pytest.fail("capacity server did not become healthy")
    prefix = f"capacity-{uuid.uuid4().hex[:8]}"
    yield base, prefix
    process.terminate()
    process.wait(timeout=10)
    engine = create_engine(settings.DATABASE_URL)
    with engine.begin() as connection:
        connection.execute(delete(User).where(User.email.like(f"{prefix}-%")))
    engine.dispose()


def _burst(count: int, call) -> list[int]:
    barrier = threading.Barrier(count)

    def one(i):
        barrier.wait(timeout=WAIT)
        return call(i)

    with ThreadPoolExecutor(max_workers=count) as pool:
        return list(pool.map(one, range(count)))


def test_a_real_server_refuses_beyond_its_capacity_and_never_fails_a_correct_password(capacity_server):
    base, prefix = capacity_server
    email = f"{prefix}-login@example.org"
    assert httpx.post(f"{base}/auth/register", json={"email": email, "password": PASSWORD}, timeout=WAIT).status_code == 201
    statuses = _burst(12, lambda _: httpx.post(f"{base}/auth/login", json={"email": email, "password": PASSWORD}, timeout=WAIT).status_code)
    assert set(statuses) <= {200, 503}  # a correct password is never reported as wrong
    assert 503 in statuses and 200 in statuses  # 12 simultaneous verifications, three slots
    assert httpx.post(f"{base}/auth/login", json={"email": email, "password": PASSWORD}, timeout=WAIT).status_code == 200


def test_a_real_server_settles_a_registration_race_with_one_account(capacity_server):
    base, prefix = capacity_server
    email = f"{prefix}-race@example.org"
    statuses = _burst(2, lambda _: httpx.post(f"{base}/auth/register", json={"email": email, "password": PASSWORD}, timeout=WAIT).status_code)
    assert sorted(statuses) == [201, 409]


# --- Login capacity isolated from registration ----------------------------------------------------------
#
# Default: 2 slots in total, registration may hold 1, so 1 can only ever serve sign-in. These reproduce
# the starvation found on 2026-11-03 (two held registrations made a correct-password login get 503) and
# pin the fix.


async def _known_student(hasher: ControlledHasher, email: str = "student@example.org") -> None:
    hasher.open()
    assert (await _register(email)).status_code == 201
    hasher.blocking = True


def _users_lookups(db_session: Session) -> list[str]:
    """Record every statement that reads the users table on the test connection."""
    seen: list[str] = []

    @event.listens_for(db_session.connection(), "before_cursor_execute")
    def record(conn, cursor, statement, params, context, executemany):
        if "FROM users" in statement:
            seen.append(statement)

    return seen


async def test_registration_saturation_can_no_longer_refuse_sign_in(api, gate, hasher):
    installed = gate(2, 1)
    await _known_student(hasher)
    hasher.blocking_ops = {"hash"}  # registrations park inside Argon2; logins run normally
    held = asyncio.create_task(_register("attacker-0@example.org"))
    await asyncio.to_thread(hasher.wait_entered, 2)  # the student's earlier registration, then this one
    assert installed.active_for("registration") == 1
    flood = [await _register(f"attacker-{i}@example.org") for i in range(1, 21)]  # repeated abuse
    assert {response.status_code for response in flood} == {503}
    assert auth_telemetry.count(
        "password_hash_capacity_exhausted", endpoint="/auth/register", operation="hash", limit="registration"
    ) == 20
    for _ in range(3):  # the reserved slot keeps serving sign-in throughout
        assert (await _login("student@example.org")).status_code == 200
    assert installed.active_for("registration") == 1 and hasher.calls_by_op["hash"] == 2
    hasher.release()
    assert (await asyncio.wait_for(held, WAIT)).status_code == 201
    assert installed.active == 0  # recovered
    hasher.open()
    assert (await _register("after-the-flood@example.org")).status_code == 201


async def test_login_may_use_every_free_slot_including_registrations_share(api, gate, hasher):
    installed = gate(2, 1)
    await _known_student(hasher)
    hasher.blocking_ops = {"verify"}
    first = asyncio.create_task(_login("student@example.org"))
    await asyncio.to_thread(hasher.wait_entered, 2)
    second = asyncio.create_task(_login("student@example.org"))
    await asyncio.to_thread(hasher.wait_entered)
    assert installed.active_for("login") == 2  # login borrowed the slot registration wasn't using
    refused = await _register("newcomer@example.org")
    assert refused.status_code == 503
    assert auth_telemetry.count(
        "password_hash_capacity_exhausted", endpoint="/auth/register", operation="hash", limit="total"
    ) == 1
    hasher.release()
    done, pending = await asyncio.wait({first, second}, timeout=WAIT, return_when=asyncio.FIRST_COMPLETED)
    hasher.release()
    statuses = [task.result().status_code for task in done] + [(await asyncio.wait_for(t, WAIT)).status_code for t in pending]
    assert statuses == [200, 200] and installed.active == 0


def test_registration_uses_its_whole_share_but_never_borrows_login_capacity(gate, hasher):
    installed = gate(4, 2)
    outcomes: queue.Queue[str] = queue.Queue()

    def register_hash():
        try:
            hash_password(PASSWORD, purpose="registration")
            outcomes.put("hashed")
        except PasswordHashCapacityExceeded as error:
            outcomes.put(f"refused:{error.limit}")

    threads = _hold_in_threads(5, register_hash)
    refused = sorted(outcomes.get(timeout=WAIT) for _ in range(3))
    assert refused == ["refused:registration"] * 3  # two slots were still free, but they are login's
    assert installed.active_for("registration") == 2 and installed.active == 2
    with security.password_hash_slot("login"), security.password_hash_slot("login"):
        assert installed.active == 4  # login fills the rest
        with pytest.raises(PasswordHashCapacityExceeded) as full:
            with security.password_hash_slot("login"):
                pass
        assert full.value.limit == "total"
    hasher.release(2)
    for thread in threads:
        thread.join(WAIT)
    assert installed.active == 0


def test_mixed_traffic_never_exceeds_the_total_or_registrations_share(gate, hasher):
    installed = gate(3, 1)
    start = threading.Barrier(12)
    outcomes: queue.Queue[str] = queue.Queue()

    def attempt(purpose):
        start.wait(timeout=WAIT)
        try:
            if purpose == "registration":
                hash_password(PASSWORD, purpose="registration")
            else:
                verify_password(PASSWORD, "$argon2id$x", purpose="login")
            outcomes.put(f"ran:{purpose}")
        except PasswordHashCapacityExceeded as error:
            outcomes.put(f"refused:{error.limit}")

    threads = [threading.Thread(target=attempt, args=(purpose,), daemon=True) for purpose in ["registration", "login"] * 6]
    for thread in threads:
        thread.start()
    refusals = [outcomes.get(timeout=WAIT) for _ in range(9)]  # three admitted and parked, nine refused at once
    assert all(item.startswith("refused:") for item in refusals)
    assert installed.active == 3 and installed.active_for("registration") <= 1
    assert hasher.peak == 3 and hasher.peak_by_op["hash"] <= 1 and hasher.calls == 3
    hasher.release(3)
    for thread in threads:
        thread.join(WAIT)
    ran = [outcomes.get_nowait() for _ in range(3)]
    assert all(item.startswith("ran:") for item in ran) and installed.active == 0


def test_a_single_slot_is_shared_without_isolation(gate, hasher):
    """With one slot nothing can be reserved: registration and login take turns, both still bounded."""
    installed = gate(1, 1)
    holder = _hold_in_threads(1, lambda: hash_password(PASSWORD, purpose="registration"))
    hasher.wait_entered()
    with pytest.raises(PasswordHashCapacityExceeded) as refused:
        verify_password(PASSWORD, "$argon2id$x", purpose="login")
    assert refused.value.limit == "total"
    hasher.release()
    holder[0].join(WAIT)
    hasher.open()
    assert verify_password(PASSWORD, "$argon2id$x", purpose="login") is True and installed.active == 0


async def test_a_saturated_service_refuses_known_and_unknown_emails_alike_before_any_lookup(api, gate, hasher, db_session):
    installed = gate(2, 1)
    await _known_student(hasher)
    held = [asyncio.create_task(_register("holder@example.org"))]
    await asyncio.to_thread(hasher.wait_entered, 2)
    held.append(asyncio.create_task(_login("student@example.org")))
    await asyncio.to_thread(hasher.wait_entered)
    assert installed.active == 2  # registration 1 + login 1: full
    lookups = _users_lookups(db_session)
    known = await _login("student@example.org")
    unknown = await _login("nobody-at-all@example.org")
    assert known.status_code == unknown.status_code == 503
    assert known.json() == unknown.json() and known.headers["Retry-After"] == unknown.headers["Retry-After"]
    assert lookups == []  # refused before the account was looked up, so nothing about existence leaks
    existing = await _register("student@example.org")
    fresh = await _register("fresh@example.org")
    assert (existing.status_code, fresh.status_code) == (409, 503)  # 409 needs no slot; a new account does
    assert len(lookups) == 2 and hasher.calls == 3  # two pre-checks; no extra Argon2 for any refusal
    hasher.release()
    first_done, _ = await asyncio.wait(held, timeout=WAIT, return_when=asyncio.FIRST_COMPLETED)
    hasher.release()
    statuses = sorted([(await asyncio.wait_for(task, WAIT)).status_code for task in held])
    assert statuses == [200, 201] and installed.active == 0


def test_unknown_email_lookups_hold_no_capacity(gate, hasher):
    """Scenario 3: lookups parked in the database (as a forged-IP flood of unknown emails would be)
    used to fill every slot without any Argon2 work. Now they hold none."""
    installed = gate(2, 1)
    hasher.open()
    engine = create_engine(settings.DATABASE_URL)
    parked, resume = threading.Semaphore(0), threading.Event()

    @event.listens_for(engine, "before_cursor_execute")
    def park_user_lookups(conn, cursor, statement, params, context, executemany):
        if "FROM users" in statement:
            parked.release()
            resume.wait(WAIT)

    def unknown_login(i):
        with Session(engine) as session:
            return authenticate_user(session, f"nobody-{i}-{uuid.uuid4().hex[:6]}@example.org", "x")

    threads = _hold_in_threads(4, lambda: unknown_login(0))
    try:
        for _ in range(4):
            assert parked.acquire(timeout=WAIT)
        assert installed.active == 0 and hasher.calls == 0
        assert verify_password(PASSWORD, "$argon2id$x", purpose="login") is True  # a real sign-in still fits
    finally:
        resume.set()
        for thread in threads:
            thread.join(WAIT)
        engine.dispose()
    assert installed.active == 0


@pytest.mark.parametrize("point", ["during_lookup", "after_argon2"])
async def test_cancellation_outside_argon2_never_holds_or_leaks_a_slot(gate, hasher, point):
    """Cancel while the database lookup is parked (no slot yet) or just after Argon2 returned (slot freed)."""
    installed = gate(2, 1)
    hasher.open()
    reached, resume = threading.Event(), threading.Event()
    finished = threading.Event()
    engine = create_engine(settings.DATABASE_URL)

    if point == "during_lookup":
        @event.listens_for(engine, "before_cursor_execute")
        def park(conn, cursor, statement, params, context, executemany):
            if "FROM users" in statement:
                reached.set()
                resume.wait(WAIT)

        def operation():
            try:
                with Session(engine) as session:
                    authenticate_user(session, "nobody-cancel@example.org", "x")
            finally:
                finished.set()
    else:
        def operation():
            try:
                verify_password(PASSWORD, "$argon2id$x", purpose="login")
                reached.set()
                resume.wait(WAIT)  # the request's thread is still busy, but Argon2 is done
            finally:
                finished.set()

    task = asyncio.create_task(run_in_threadpool(operation))
    assert await asyncio.to_thread(reached.wait, WAIT)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, WAIT)
    assert installed.active == 0  # nothing held before Argon2, and released as soon as it ended
    resume.set()
    assert await asyncio.to_thread(finished.wait, WAIT)
    assert installed.active == 0 and hasher.calls == (1 if point == "after_argon2" else 0)
    engine.dispose()


def test_capacity_telemetry_labels_come_from_closed_sets(gate):
    auth_telemetry.reset()
    auth_telemetry.record("password_hash_capacity_exhausted", endpoint="/auth/login", operation="verify", limit="total")
    auth_telemetry.record("password_hash_capacity_exhausted", endpoint="/auth/register", operation="hash", limit="registration")
    auth_telemetry.record("password_hash_capacity_exhausted", endpoint="x@example.org", operation="203.0.113.1", limit="anything")
    labels = {label for key in auth_telemetry.snapshot() for label in key[1:]}
    assert labels == {
        ("endpoint", "/auth/login"), ("endpoint", "/auth/register"), ("endpoint", "other"),
        ("operation", "verify"), ("operation", "hash"), ("operation", "other"),
        ("limit", "total"), ("limit", "registration"), ("limit", "other"),
    }
    auth_telemetry.reset()


def test_a_real_server_never_creates_two_accounts_from_three_simultaneous_duplicates(capacity_server):
    """Three duplicates against a share of two: one account; the others get 409 or, past the share, 503."""
    base, prefix = capacity_server
    email = f"{prefix}-share@example.org"
    statuses = _burst(3, lambda _: httpx.post(f"{base}/auth/register", json={"email": email, "password": PASSWORD}, timeout=WAIT).status_code)
    assert statuses.count(201) == 1 and set(statuses) <= {201, 409, 503}
