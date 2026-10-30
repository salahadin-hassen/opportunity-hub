"""A small per-client fixed-window limiter for credential endpoints.

In-memory and per process, which suits the single-instance deployment;
behind a reverse proxy the client address comes from uvicorn's
``--proxy-headers``. Disabled unless ``AUTH_RATE_LIMIT_PER_MINUTE`` is set.
"""
from __future__ import annotations

import threading
import time

from fastapi import HTTPException, Request, status

from app.core.config import settings

WINDOW_SECONDS = 60.0

_lock = threading.Lock()
_hits: dict[tuple[str, str], tuple[float, int]] = {}


def reset() -> None:
    """Forget all counters (tests)."""
    with _lock:
        _hits.clear()


def limit_auth_attempts(request: Request) -> None:
    """Reject a client that exceeds the per-minute credential attempt budget with a 429."""
    limit = settings.AUTH_RATE_LIMIT_PER_MINUTE
    if not limit:
        return
    client = request.client.host if request.client else "unknown"
    key = (request.url.path, client)
    now = time.monotonic()
    with _lock:
        started, count = _hits.get(key, (now, 0))
        if now - started >= WINDOW_SECONDS:
            started, count = now, 0
        count += 1
        _hits[key] = (started, count)
        # Bound memory: drop windows that have already expired.
        if len(_hits) > 10_000:
            for stale in [k for k, (t, _) in _hits.items() if now - t >= WINDOW_SECONDS]:
                del _hits[stale]
    if count > limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many attempts. Wait a minute, then try again.",
            headers={"Retry-After": str(int(WINDOW_SECONDS - (now - started)) + 1)},
        )
