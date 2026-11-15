"""Local password hashing and signed JWT identity tokens.

Only symmetric signing with the configured ``JWT_SECRET`` is used; token
format, claims and verification stay in this module so routers never deal
with token internals directly.
"""
from __future__ import annotations

import threading
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Literal

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core.config import settings

ACCESS_TOKEN_TTL = timedelta(minutes=30)
SUBJECT_CLAIM = "sub"

#: argon2-cffi defaults: Argon2id, m=64 MiB, t=3, p=4. Each running operation holds its 64 MiB.
_password_hasher = PasswordHasher()


#: Which admission policy an Argon2 operation is charged to. Hashing serves registration (and the offline
#: seed script); verification serves login.
Purpose = Literal["login", "registration"]
#: Why an operation was refused. A closed set, safe as a telemetry label.
RefusalLimit = Literal["total", "registration"]


class PasswordHashCapacityExceeded(Exception):
    """No Argon2 slot is available for this purpose; the caller must refuse the attempt (503), not fail it."""

    def __init__(self, limit: RefusalLimit) -> None:
        super().__init__(limit)
        self.limit: RefusalLimit = limit


class PasswordHashGate:
    """One process-wide ceiling on concurrent Argon2 work, with a smaller ceiling for registration.

    At most ``capacity`` operations run at once, whatever their purpose: that
    is the memory bound (64 MiB each). Registration hashing may hold at most
    ``registration_capacity`` of them, so ``capacity - registration_capacity``
    slots can only ever go to login verification, and a flood of registrations
    can't refuse sign-in. Login may use every free slot, including ones
    registration isn't using. Registration never borrows past its ceiling.

    There is no queue: an operation that can't be admitted is refused at once
    and does no Argon2 work. A slot is held only around the Argon2 call itself,
    by the thread doing it, and freed in ``finally`` when that call returns or
    raises. Cancelling the request can't stop a running Argon2 call: anyio may
    stop waiting and leave the worker thread running, and the slot stays taken
    until that thread's call ends, so the bound covers abandoned work too.
    """

    def __init__(self, capacity: int, registration_capacity: int | None = None) -> None:
        registration_capacity = capacity if registration_capacity is None else registration_capacity
        if capacity < 1:
            raise ValueError("password hash capacity must be at least 1")
        if not 1 <= registration_capacity <= capacity:
            raise ValueError("registration capacity must be between 1 and the total capacity")
        self.capacity = capacity
        self.registration_capacity = registration_capacity
        self._lock = threading.Lock()
        self._active: dict[str, int] = {"login": 0, "registration": 0}

    @property
    def active(self) -> int:
        """Argon2 operations running in this process right now."""
        with self._lock:
            return sum(self._active.values())

    def active_for(self, purpose: Purpose) -> int:
        with self._lock:
            return self._active[purpose]

    def _refusal(self, purpose: Purpose) -> RefusalLimit | None:  # caller holds the lock
        if sum(self._active.values()) >= self.capacity:
            return "total"
        if purpose == "registration" and self._active["registration"] >= self.registration_capacity:
            return "registration"
        return None

    def check(self, purpose: Purpose) -> None:
        """Raise :class:`PasswordHashCapacityExceeded` if ``purpose`` couldn't be admitted now; reserves nothing.

        Lets login refuse a saturated service *before* it learns whether the
        account exists, so known and unknown emails get the same 503 without
        unknown ones ever holding a slot.
        """
        with self._lock:
            refusal = self._refusal(purpose)
        if refusal is not None:
            raise PasswordHashCapacityExceeded(refusal)

    @contextmanager
    def slot(self, purpose: Purpose) -> Iterator[None]:
        with self._lock:
            refusal = self._refusal(purpose)
            if refusal is None:
                self._active[purpose] += 1
        if refusal is not None:
            raise PasswordHashCapacityExceeded(refusal)
        try:
            yield
        finally:
            with self._lock:
                self._active[purpose] -= 1
                if self._active[purpose] < 0:  # would mean a double release; never over-admit
                    raise RuntimeError("password hash slot released twice")


password_hash_gate = PasswordHashGate(settings.ARGON2_MAX_CONCURRENCY, settings.ARGON2_REGISTRATION_MAX_CONCURRENCY)


def check_password_hash_capacity(purpose: Purpose) -> None:
    """Refuse early if ``purpose`` couldn't get an Argon2 slot now (see :meth:`PasswordHashGate.check`)."""
    password_hash_gate.check(purpose)


def password_hash_slot(purpose: Purpose):
    """Hold one Argon2 slot for ``purpose`` around the enclosed work (raises :class:`PasswordHashCapacityExceeded`)."""
    return password_hash_gate.slot(purpose)


def hash_password(password: str, *, purpose: Purpose = "registration") -> str:
    """Hash a password with Argon2id; the hash is one-way and salted by the library."""
    with password_hash_slot(purpose):
        return _password_hasher.hash(password)


def verify_password(password: str, password_hash: str, *, purpose: Purpose = "login") -> bool:
    """Return whether ``password`` matches ``password_hash``."""
    with password_hash_slot(purpose):
        try:
            return _password_hasher.verify(password_hash, password)
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            return False


def create_access_token(user_id: uuid.UUID, *, ttl: timedelta = ACCESS_TOKEN_TTL) -> str:
    """Sign a short-lived bearer token that names exactly one user."""
    issued_at = datetime.now(timezone.utc)
    payload = {
        SUBJECT_CLAIM: str(user_id),
        "iat": issued_at,
        "exp": issued_at + ttl,
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> uuid.UUID | None:
    """Resolve a signed token to its user id.

    Returns ``None`` for any unverifiable input — wrong signature, wrong
    algorithm, expired, missing or malformed subject — so callers can treat
    every failure identically without learning why the token failed.
    """
    try:
        payload = jwt.decode(
            token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM]
        )
    except jwt.PyJWTError:
        return None
    subject = payload.get(SUBJECT_CLAIM)
    if not isinstance(subject, str):
        return None
    try:
        return uuid.UUID(subject)
    except ValueError:
        return None
