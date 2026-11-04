"""Fixed-window limiter for credential endpoints, per client and per account, stored in PostgreSQL.

Every attempt on ``/auth/login`` and ``/auth/register`` is counted twice:
once for the client address bucket (``app.core.client_ip``) and once for
the account email, so neither rotating addresses nor rotating accounts
escapes the budget. Counters live in ``rate_limit_buckets``, shared by
every application instance and kept across restarts.

When no trustworthy client address can be established the address budget
is skipped for that request and the degradation is recorded (reason and
strategy only); the account budget is always enforced. A missing address
is never counted under a proxy address or a placeholder, which would make
one shared bucket that any caller could exhaust for everyone.

Each increment runs in its own short transaction on its own connection
and commits at once: a failed login raises 401, which rolls back the
request's session, and the attempt must still count. If the store cannot
be reached the attempt is refused with 503 (fail closed): the limiter is
never silently switched off. Logs never contain the address, the email or
their digests.

Disabled entirely unless ``AUTH_RATE_LIMIT_PER_MINUTE`` is set.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import math
import random
import time
from collections.abc import Callable
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request, status
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from app.core import auth_telemetry
from app.core.client_ip import ClientIdentity, select_client_identity
from app.core.config import settings

logger = logging.getLogger(__name__)

WINDOW_SECONDS = 60
#: Bound how long a counter write may wait, so a stalled database cannot hang sign-in.
STATEMENT_TIMEOUT_MS = 2000
#: Expired windows are deleted on roughly one write in this many.
PRUNE_ONE_IN = 200
STORE_UNAVAILABLE_RETRY_AFTER = 30

_HIT_SQL = text(
    """
    INSERT INTO rate_limit_buckets (scope, key, window_start, count)
    VALUES (:scope, :key, :window_start, 1)
    ON CONFLICT (scope, key, window_start)
    DO UPDATE SET count = rate_limit_buckets.count + 1
    RETURNING count
    """
)


class RateLimitStoreUnavailable(Exception):
    """The counter store could not be written; callers must refuse the attempt."""


class PostgresRateLimiter:
    """Counts attempts in ``rate_limit_buckets`` through ``engine``."""

    def __init__(
        self,
        engine: Engine,
        *,
        window_seconds: int = WINDOW_SECONDS,
        clock: Callable[[], float] = time.time,
        prune_probability: float = 1 / PRUNE_ONE_IN,
    ) -> None:
        self.engine = engine
        self.window_seconds = window_seconds
        self.clock = clock
        self.prune_probability = prune_probability

    def hit(self, scope: str, key: str) -> tuple[int, int]:
        """Count one attempt; return (attempts in this window, seconds until the window resets)."""
        now = self.clock()
        start = math.floor(now / self.window_seconds) * self.window_seconds
        window_start = datetime.fromtimestamp(start, tz=timezone.utc)
        retry_after = max(1, math.ceil(start + self.window_seconds - now))
        try:
            with self.engine.begin() as connection:
                connection.execute(text(f"SET LOCAL statement_timeout = {STATEMENT_TIMEOUT_MS}"))
                count = connection.execute(
                    _HIT_SQL, {"scope": scope, "key": key, "window_start": window_start}
                ).scalar_one()
                if random.random() < self.prune_probability:
                    self._prune(connection, window_start)
        except SQLAlchemyError as error:
            raise RateLimitStoreUnavailable from error
        return count, retry_after

    def previous_count(self, scope: str, key: str) -> int:
        """Attempts counted for ``key`` in the window before the current one (0 if none or pruned)."""
        start = math.floor(self.clock() / self.window_seconds) * self.window_seconds - self.window_seconds
        try:
            with self.engine.begin() as connection:
                connection.execute(text(f"SET LOCAL statement_timeout = {STATEMENT_TIMEOUT_MS}"))
                value = connection.execute(
                    text("SELECT count FROM rate_limit_buckets WHERE scope = :scope AND key = :key AND window_start = :start"),
                    {"scope": scope, "key": key, "start": datetime.fromtimestamp(start, tz=timezone.utc)},
                ).scalar()
        except SQLAlchemyError as error:
            raise RateLimitStoreUnavailable from error
        return value or 0

    def prune(self) -> int:
        """Delete windows that ended before the current one began; return how many."""
        now = self.clock()
        start = math.floor(now / self.window_seconds) * self.window_seconds
        with self.engine.begin() as connection:
            return self._prune(connection, datetime.fromtimestamp(start, tz=timezone.utc))

    def _prune(self, connection, current_window: datetime) -> int:
        cutoff = current_window - timedelta(seconds=self.window_seconds)
        result = connection.execute(text("DELETE FROM rate_limit_buckets WHERE window_start < :cutoff"), {"cutoff": cutoff})
        return result.rowcount or 0

    def clear(self) -> None:
        with self.engine.begin() as connection:
            connection.execute(text("DELETE FROM rate_limit_buckets"))


_limiter: PostgresRateLimiter | None = None


def get_limiter() -> PostgresRateLimiter:
    global _limiter
    if _limiter is None:
        from app.db.session import engine

        _limiter = PostgresRateLimiter(engine)
    return _limiter


def set_limiter(limiter: PostgresRateLimiter | None) -> None:
    """Swap the limiter (tests: other engines, fake clocks)."""
    global _limiter
    _limiter = limiter


def reset() -> None:
    """Forget all counters (tests and local development only)."""
    if settings.is_production:
        raise RuntimeError("Refusing to clear rate-limit counters in production.")
    get_limiter().clear()


def subject_key(kind: str, value: str) -> str:
    """Keyed digest of one subject, so stored keys reveal neither addresses nor emails."""
    secret = hmac.new(settings.JWT_SECRET.encode(), b"rate-limit-subject-v1", hashlib.sha256).digest()
    return hmac.new(secret, f"{kind}:{value}".encode(), hashlib.sha256).hexdigest()


def client_identity(request: Request) -> ClientIdentity:
    """The client identity for ``request`` under the configured strategy."""
    return select_client_identity(
        strategy=settings.CLIENT_IP_STRATEGY,
        peer=request.client.host if request.client else None,
        headers={name.lower(): value for name, value in request.headers.items()},
        trusted_networks=settings.trusted_proxy_networks,
        trusted_hops=settings.TRUSTED_PROXY_HOPS,
        client_ip_header=settings.CLIENT_IP_HEADER,
    )


def _enforce(scope: str, key: str, budget: str) -> None:
    limit = settings.AUTH_RATE_LIMIT_PER_MINUTE
    if not limit:
        return
    try:
        count, retry_after = get_limiter().hit(scope, key)
    except RateLimitStoreUnavailable:
        logger.warning("Rate-limit store unavailable; refusing credential attempt on %s", scope)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Sign-in is temporarily unavailable. Please try again shortly.",
            headers={"Retry-After": str(STORE_UNAVAILABLE_RETRY_AFTER)},
        ) from None
    if count > limit:
        auth_telemetry.record(f"{budget}_budget_exhausted", endpoint=scope)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many attempts. Wait a minute, then try again.",
            headers={"Retry-After": str(retry_after)},
        )


def limit_auth_attempts(request: Request) -> None:
    """Reject a client that exceeds the per-minute credential attempt budget with a 429.

    Without a trustworthy client identity only this budget is skipped; the
    handler still applies :func:`limit_account_attempts`.
    """
    if not settings.AUTH_RATE_LIMIT_PER_MINUTE:
        return
    identity = client_identity(request)
    if identity.identity is None:
        request.state.rate_limit_client_key = None
        auth_telemetry.record(
            "client_identity_degraded", level=logging.WARNING,
            endpoint=request.url.path, strategy=identity.strategy, reason=identity.reason or "",
        )
        return
    key = subject_key("client", identity.identity)
    request.state.rate_limit_client_key = key
    _enforce(request.url.path, key, "ip")


def limit_account_attempts(path: str, email: str) -> None:
    """Apply the same per-minute budget to one account, whatever address the attempts claim."""
    _enforce(path, _account_key(email), "account")


def _account_key(email: str) -> str:
    return subject_key("account", email.strip().lower())


def record_auth_failure(path: str) -> None:
    """Count a rejected credential attempt (wrong password, unknown account, taken email)."""
    if settings.AUTH_RATE_LIMIT_PER_MINUTE:
        auth_telemetry.record("auth_failure", endpoint=path)


def record_auth_success(request: Request, path: str, email: str) -> None:
    """Count a success whose address or account was over budget in the previous window.

    These are the likeliest false positives of the limit (a shared network,
    a user retrying), which is the evidence needed to tune it. Best effort:
    a store error here never affects the sign-in.
    """
    limit = settings.AUTH_RATE_LIMIT_PER_MINUTE
    if not limit:
        return
    limiter = get_limiter()
    subjects = [("account", _account_key(email))]
    client_key = getattr(request.state, "rate_limit_client_key", None)
    if client_key:
        subjects.append(("ip", client_key))
    for budget, key in subjects:
        try:
            throttled = limiter.previous_count(path, key) > limit
        except RateLimitStoreUnavailable:
            return
        if throttled:
            auth_telemetry.record("success_after_throttle", endpoint=path, budget=budget)
