"""Bounded counters and throttled log lines for the credential endpoints.

There is no metrics backend, so this keeps per-process counters (for tests
and a future exporter) and writes at most one log line per event and label
set per ``LOG_INTERVAL_SECONDS``, carrying how many occurrences it stands
for. Labels come only from closed sets (event names, endpoint paths,
strategies, reason codes): never an address, an email, a digest or an
account id, so neither the log volume nor the label cardinality depends on
who is calling.
"""
from __future__ import annotations

import logging
import threading
import time
from collections import Counter
from collections.abc import Callable

logger = logging.getLogger("app.auth_telemetry")

LOG_INTERVAL_SECONDS = 60

EVENTS = frozenset(
    {
        "ip_budget_exhausted",
        "account_budget_exhausted",
        "client_identity_degraded",
        "auth_failure",
        "success_after_throttle",
        "password_hash_capacity_exhausted",
    }
)
ENDPOINTS = frozenset({"/auth/login", "/auth/register"})
STRATEGIES = frozenset({"peer", "xff_rightmost", "header"})
#: Values allowed for each label; anything else is recorded as "other".
LABEL_VALUES: dict[str, frozenset[str]] = {
    "endpoint": ENDPOINTS,
    "strategy": STRATEGIES,
    "reason": frozenset(
        {
            "trusted_proxy_header_missing",
            "trusted_proxy_header_invalid",
            "untrusted_proxy",
            "ambiguous_forwarded_chain",
            "client_identity_unavailable",
        }
    ),
    "budget": frozenset({"ip", "account"}),
    "operation": frozenset({"hash", "verify"}),
    "limit": frozenset({"total", "registration"}),
}

_lock = threading.Lock()
_counts: Counter[tuple] = Counter()
_pending: Counter[tuple] = Counter()
_last_logged: dict[tuple, float] = {}
clock: Callable[[], float] = time.monotonic


def _label(name: str, value: str) -> str:
    return value if value in LABEL_VALUES.get(name, frozenset()) else "other"


def record(event: str, *, level: int = logging.INFO, **labels: str) -> None:
    """Count one ``event``; log it unless the same event and labels were logged within the interval."""
    if event not in EVENTS:
        raise ValueError(f"Unknown auth telemetry event {event!r}")
    key = (event, *sorted((name, _label(name, value)) for name, value in labels.items()))
    now = clock()
    with _lock:
        _counts[key] += 1
        _pending[key] += 1
        last = _last_logged.get(key)
        if last is not None and now - last < LOG_INTERVAL_SECONDS:
            return
        occurrences = _pending.pop(key)
        _last_logged[key] = now
    fields = " ".join(f"{name}={value}" for name, value in key[1:])
    logger.log(level, "auth_telemetry event=%s %s occurrences=%d", event, fields, occurrences)


def count(event: str, **labels: str) -> int:
    """Total recorded for ``event`` with exactly these labels, in this process."""
    key = (event, *sorted((name, _label(name, value)) for name, value in labels.items()))
    with _lock:
        return _counts[key]


def snapshot() -> dict[tuple, int]:
    with _lock:
        return dict(_counts)


def reset() -> None:
    with _lock:
        _counts.clear()
        _pending.clear()
        _last_logged.clear()
