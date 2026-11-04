"""Credential rate limiting: client-address selection and the shared PostgreSQL counter store (M1-T3).

Covers forged ``X-Forwarded-For`` values, many accounts from one address,
one account from many addresses, several application instances sharing
counters, persistence across restarts, concurrency at the limit, window
reset, an unreachable store, IPv4/IPv6 buckets and requests through a
trusted proxy. Counters live in the dedicated test database and are
cleared around each test.
"""
from __future__ import annotations

import ipaddress
import logging
import os
import socket
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.core import rate_limit
from app.core import auth_telemetry
from app.core.client_ip import REASONS, ClientIdentity, bucket, parse_address, select_client_identity
from app.core.config import Settings, settings
from app.core.rate_limit import PostgresRateLimiter, RateLimitStoreUnavailable, subject_key
from app.db.session import get_db
from app.main import app

BACKEND_DIR = Path(__file__).resolve().parents[1]
TRUSTED = [ipaddress.ip_network("10.0.0.0/8")]


class FakeClock:
    def __init__(self, start: float = 1_800_000_000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def store():
    """A clean counter table and telemetry, a limiter on a frozen clock, and the module limiter restored afterwards.

    The frozen clock keeps a test from straddling a window boundary, which would reset its counters.
    """
    rate_limit.set_limiter(None)
    rate_limit.reset()
    auth_telemetry.reset()
    rate_limit.set_limiter(PostgresRateLimiter(rate_limit.get_limiter().engine, clock=FakeClock()))
    yield
    rate_limit.set_limiter(None)
    rate_limit.reset()
    auth_telemetry.reset()


@pytest.fixture
def api(db_session: Session, store):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    yield
    app.dependency_overrides.clear()


def _rows() -> list[tuple[str, str, int]]:
    with rate_limit.get_limiter().engine.connect() as connection:
        return list(connection.execute(text("SELECT scope, key, count FROM rate_limit_buckets ORDER BY scope, key")))


async def _login(address: str, email: str, headers: dict | None = None, password: str = "wrong-password") -> int:
    transport = ASGITransport(app=app, client=(address, 40000))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/auth/login", json={"email": email, "password": password}, headers=headers or {})
    return response.status_code


# --- Address parsing and buckets (pure) -------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("203.0.113.7", "203.0.113.7"),
        (" 203.0.113.7:51234 ", "203.0.113.7"),
        ("2001:db8::1", "2001:db8::1"),
        ("[2001:db8::1]:443", "2001:db8::1"),
        ("::ffff:203.0.113.7", "203.0.113.7"),
    ],
)
def test_addresses_are_parsed_as_proxies_write_them(raw, expected):
    assert str(parse_address(raw)) == expected


@pytest.mark.parametrize("raw", ["", None, "unknown", "999.1.1.1", "203.0.113.7, 10.0.0.1", "example.org"])
def test_unparseable_addresses_are_none(raw):
    assert parse_address(raw) is None


def test_ipv4_buckets_are_exact_and_ipv6_buckets_are_slash_64():
    assert bucket(parse_address("203.0.113.7")) == "203.0.113.7"
    assert bucket(parse_address("2001:db8:1:2::1")) == bucket(parse_address("2001:db8:1:2:ffff::9")) == "2001:db8:1:2::/64"
    assert bucket(parse_address("2001:db8:1:3::1")) != bucket(parse_address("2001:db8:1:2::1"))


# --- Strategy selection (pure) --------------------------------------------------------------------------

FORGED = {"x-forwarded-for": "198.51.100.66, 203.0.113.7", "cf-connecting-ip": "203.0.113.9"}


def _identity(strategy: str = "xff_rightmost", peer: str | None = "10.1.2.3", headers=None, **options) -> ClientIdentity:
    options.setdefault("trusted_networks", TRUSTED)
    return select_client_identity(strategy=strategy, peer=peer, headers=headers or {}, **options)


def _unavailable(reason: str, strategy: str = "xff_rightmost", verified: bool = True) -> ClientIdentity:
    return ClientIdentity(None, strategy, reason, verified)


def test_peer_strategy_ignores_every_header():
    assert _identity("peer", peer="203.0.113.5", headers=FORGED) == ClientIdentity("203.0.113.5", "peer")


def test_valid_direct_connection_uses_the_peer_under_every_strategy():
    for strategy in ("peer", "xff_rightmost", "header"):
        identity = _identity(strategy, peer="203.0.113.5", client_ip_header="cf-connecting-ip")
        assert identity == ClientIdentity("203.0.113.5", strategy)


def test_xff_rightmost_uses_the_entry_the_trusted_proxy_appended():
    assert _identity(headers=FORGED) == ClientIdentity("203.0.113.7", "xff_rightmost", None, True)


def test_forged_leftmost_entries_never_matter():
    for forged in ("1.1.1.1", "1.1.1.1, 2.2.2.2", "garbage, 9.9.9.9, 8.8.8.8"):
        assert _identity(headers={"x-forwarded-for": f"{forged}, 203.0.113.7"}).identity == "203.0.113.7"


def test_two_trusted_hops_take_the_second_entry_from_the_right():
    trusted = [*TRUSTED, ipaddress.ip_network("172.70.0.0/16")]
    headers = {"x-forwarded-for": "198.51.100.66, 203.0.113.7, 172.70.1.1"}
    assert _identity(headers=headers, trusted_networks=trusted, trusted_hops=2).identity == "203.0.113.7"


def test_an_untrusted_intermediate_hop_is_the_client_the_trusted_proxy_saw():
    # With two hops configured, the outer proxy was bypassed: the entry our trusted proxy appended is
    # the real client, and everything to its left was written by that client.
    headers = {"x-forwarded-for": "198.51.100.66, 203.0.113.7"}
    assert _identity(headers=headers, trusted_hops=2).identity == "203.0.113.7"


def test_trusted_proxy_without_forwarded_for_is_unavailable_not_the_proxy():
    for headers in ({}, {"x-forwarded-for": ""}, {"x-forwarded-for": " , "}):
        identity = _identity(headers=headers)
        assert identity.identity is None and identity.identity != "10.1.2.3"
    assert _identity(headers={}) == _unavailable("trusted_proxy_header_missing")


@pytest.mark.parametrize("value", ["not-an-ip", "203.0.113.7, garbage", "203.0.113.7,", "999.1.1.1"])
def test_trusted_proxy_with_a_malformed_forwarded_for_is_unavailable(value):
    assert _identity(headers={"x-forwarded-for": value}) == _unavailable("trusted_proxy_header_invalid")


@pytest.mark.parametrize(
    ("value", "hops"),
    [("10.9.9.9", 1), ("203.0.113.7, 10.9.9.9", 1), ("10.9.9.8, 10.9.9.9", 2), ("10.9.9.9", 3)],
)
def test_a_proxy_address_in_the_client_position_is_ambiguous_never_a_bucket(value, hops):
    identity = _identity(headers={"x-forwarded-for": value}, trusted_hops=hops)
    assert identity == _unavailable("ambiguous_forwarded_chain")


def test_forwarding_headers_from_an_untrusted_peer_make_the_identity_unavailable():
    for strategy in ("xff_rightmost", "header"):
        identity = _identity(strategy, peer="198.51.100.200", headers=FORGED, client_ip_header="cf-connecting-ip")
        assert identity == _unavailable("untrusted_proxy", strategy, verified=False)
    lone_header = _identity("header", peer="198.51.100.200", headers={"x-real-ip": "1.2.3.4"}, client_ip_header="cf-connecting-ip")
    assert lone_header.reason == "untrusted_proxy"


def test_a_known_proxy_seen_by_the_peer_strategy_is_not_a_bucket():
    assert _identity("peer", peer="10.1.2.3") == _unavailable("client_identity_unavailable", "peer", verified=False)


@pytest.mark.parametrize("peer", [None, "", "garbage", "unknown", "999.1.1.1", "203.0.113.7, 10.0.0.1"])
def test_a_missing_or_unparseable_peer_is_unavailable_under_every_strategy(peer):
    for strategy in ("peer", "xff_rightmost", "header"):
        identity = _identity(strategy, peer=peer, headers=FORGED, client_ip_header="cf-connecting-ip")
        assert identity == _unavailable("client_identity_unavailable", strategy, verified=False)


def test_header_strategy_uses_the_edge_header():
    identity = _identity("header", headers=FORGED, client_ip_header="CF-Connecting-IP")
    assert identity == ClientIdentity("203.0.113.9", "header", None, True)


@pytest.mark.parametrize(
    ("value", "reason"),
    [
        (None, "trusted_proxy_header_missing"),
        ("", "trusted_proxy_header_missing"),
        ("203.0.113.9, 198.51.100.1", "ambiguous_forwarded_chain"),
        ("nonsense", "trusted_proxy_header_invalid"),
        ("10.0.0.7", "trusted_proxy_header_invalid"),
    ],
)
def test_header_strategy_is_unavailable_on_missing_listed_or_bad_values(value, reason):
    headers = {} if value is None else {"cf-connecting-ip": value}
    identity = _identity("header", headers=headers, client_ip_header="cf-connecting-ip")
    assert identity == _unavailable(reason, "header")


def test_header_strategy_buckets_ipv6_clients_by_slash_64():
    identity = _identity("header", headers={"cf-connecting-ip": "2001:db8:5:6::abcd"}, client_ip_header="cf-connecting-ip")
    assert identity.identity == "2001:db8:5:6::/64"


def test_every_reason_is_a_known_telemetry_label():
    assert set(REASONS) == auth_telemetry.LABEL_VALUES["reason"]


def _no_selection_returns_a_shared_identity(select) -> list[str]:
    """Every case where a proxy address or a placeholder would stand in for an unknown client."""
    proxy, offending = "10.1.2.3", []
    cases = [
        ("xff_rightmost", proxy, {}),
        ("xff_rightmost", proxy, {"x-forwarded-for": "not-an-ip"}),
        ("xff_rightmost", proxy, {"x-forwarded-for": "10.9.9.9"}),
        ("header", proxy, {}),
        ("header", proxy, {"cf-connecting-ip": "a, b"}),
        ("header", proxy, {"cf-connecting-ip": "nonsense"}),
        ("peer", None, {}),
        ("peer", "garbage", {}),
        ("peer", proxy, {}),
    ]
    for strategy, peer, headers in cases:
        result = select(
            strategy=strategy, peer=peer, headers=headers, trusted_networks=TRUSTED, client_ip_header="cf-connecting-ip"
        )
        chosen = result.identity if isinstance(result, ClientIdentity) else result
        if chosen is not None:
            offending.append(f"{strategy}:{peer}:{headers}->{chosen}")
    return offending


def test_no_strategy_turns_a_missing_identity_into_a_shared_one():
    assert _no_selection_returns_a_shared_identity(select_client_identity) == []


def _legacy_fallback(**arguments) -> str:
    """The pre-remediation behaviour: fall back to the peer's bucket, or the constant 'unknown'."""
    result = select_client_identity(**arguments)
    if result.identity is not None:
        return result.identity
    peer = parse_address(arguments["peer"])
    return bucket(peer) if peer is not None else "unknown"


def test_mutation_reverting_to_the_proxy_fallback_is_caught():
    offending = _no_selection_returns_a_shared_identity(_legacy_fallback)
    assert len(offending) == 9  # every case, including the 'unknown' placeholder, is flagged
    assert any(item.endswith("->unknown") for item in offending)
    assert any(item.endswith("->10.1.2.3") for item in offending)


def _settings(**values) -> Settings:
    return Settings(_env_file=None, DATABASE_URL="postgresql://u@h/db", JWT_SECRET="s" * 40, **values)


def test_header_strategies_require_trusted_proxies():
    with pytest.raises(ValidationError):
        _settings(CLIENT_IP_STRATEGY="xff_rightmost")
    with pytest.raises(ValidationError):
        _settings(CLIENT_IP_STRATEGY="header", CLIENT_IP_HEADER="cf-connecting-ip")
    with pytest.raises(ValidationError):
        _settings(CLIENT_IP_STRATEGY="header", TRUSTED_PROXY_CIDRS="10.0.0.0/8")
    with pytest.raises(ValidationError):
        _settings(CLIENT_IP_STRATEGY="xff_rightmost", TRUSTED_PROXY_CIDRS="not-a-network")
    assert _settings().CLIENT_IP_STRATEGY == "peer"
    assert _settings(CLIENT_IP_STRATEGY="xff_rightmost", TRUSTED_PROXY_CIDRS="10.0.0.0/8, fd00::/8").trusted_proxy_networks


def test_invalid_trusted_proxies_are_rejected_at_startup_under_the_peer_strategy_too():
    # Previously accepted, then raised on every credential request (a 500).
    with pytest.raises(ValidationError):
        _settings(TRUSTED_PROXY_CIDRS="not-a-network")


# --- Store behaviour ---------------------------------------------------------------------------------------


def test_counts_accumulate_and_report_the_reset_time(store):
    clock = FakeClock(1_800_000_000.0 + 15)
    limiter = PostgresRateLimiter(rate_limit.get_limiter().engine, clock=clock, prune_probability=0)
    assert limiter.hit("/auth/login", "a" * 64) == (1, 45)
    assert limiter.hit("/auth/login", "a" * 64) == (2, 45)
    assert limiter.hit("/auth/register", "a" * 64)[0] == 1  # scopes are separate


def test_a_new_window_starts_from_zero(store):
    clock = FakeClock()
    limiter = PostgresRateLimiter(rate_limit.get_limiter().engine, clock=clock, prune_probability=0)
    for _ in range(3):
        limiter.hit("/auth/login", "b" * 64)
    clock.now += 60
    assert limiter.hit("/auth/login", "b" * 64)[0] == 1


def test_expired_windows_are_pruned(store):
    clock = FakeClock()
    limiter = PostgresRateLimiter(rate_limit.get_limiter().engine, clock=clock, prune_probability=0)
    limiter.hit("/auth/login", "c" * 64)
    clock.now += 60
    limiter.hit("/auth/login", "c" * 64)
    assert limiter.prune() == 0  # the previous window is kept until it is two windows old
    clock.now += 60
    assert limiter.prune() == 1


def test_two_application_instances_share_counters(store):
    engines = [create_engine(settings.DATABASE_URL, pool_pre_ping=True) for _ in range(2)]
    try:
        clock = FakeClock()
        first, second = (PostgresRateLimiter(engine, clock=clock, prune_probability=0) for engine in engines)
        assert [first.hit("/auth/login", "d" * 64)[0], second.hit("/auth/login", "d" * 64)[0]] == [1, 2]
        assert first.hit("/auth/login", "d" * 64)[0] == 3
    finally:
        for engine in engines:
            engine.dispose()


def test_counters_survive_a_restart(store):
    clock = FakeClock()
    engine = create_engine(settings.DATABASE_URL)
    PostgresRateLimiter(engine, clock=clock).hit("/auth/login", "e" * 64)
    PostgresRateLimiter(engine, clock=clock).hit("/auth/login", "e" * 64)
    engine.dispose()  # the process "restarts": every pooled connection is gone
    restarted = create_engine(settings.DATABASE_URL)
    try:
        assert PostgresRateLimiter(restarted, clock=clock).hit("/auth/login", "e" * 64)[0] == 3
    finally:
        restarted.dispose()


def test_concurrent_attempts_are_counted_exactly_once_each(store):
    engine = create_engine(settings.DATABASE_URL, pool_size=10, max_overflow=10)
    limiter = PostgresRateLimiter(engine, clock=FakeClock(), prune_probability=0)
    barrier = threading.Barrier(20)

    def attempt(_):
        barrier.wait()
        return limiter.hit("/auth/login", "f" * 64)[0]

    try:
        with ThreadPoolExecutor(max_workers=20) as pool:
            counts = sorted(pool.map(attempt, range(20)))
    finally:
        engine.dispose()
    assert counts == list(range(1, 21))  # no lost or duplicated increments
    assert sum(count <= 5 for count in counts) == 5  # with a limit of 5, exactly five get through


def test_an_unreachable_store_raises(store):
    dead = create_engine("postgresql://nobody@127.0.0.1:1/none", connect_args={"connect_timeout": 1})
    with pytest.raises(RateLimitStoreUnavailable):
        PostgresRateLimiter(dead).hit("/auth/login", "g" * 64)


def test_reset_refuses_in_production(store, monkeypatch):
    monkeypatch.setattr(settings, "APP_ENV", "production")
    with pytest.raises(RuntimeError):
        rate_limit.reset()


# --- Through the API ------------------------------------------------------------------------------


async def test_many_accounts_from_one_address_hit_the_address_budget(api, monkeypatch):
    monkeypatch.setattr(settings, "AUTH_RATE_LIMIT_PER_MINUTE", 3)
    statuses = [await _login("203.0.113.50", f"user{i}@example.org") for i in range(5)]
    assert statuses == [401, 401, 401, 429, 429]


async def test_one_account_from_many_addresses_hits_the_account_budget(api, monkeypatch):
    monkeypatch.setattr(settings, "AUTH_RATE_LIMIT_PER_MINUTE", 3)
    statuses = [await _login(f"198.51.100.{i}", "target@example.org") for i in range(1, 6)]
    assert statuses == [401, 401, 401, 429, 429]


async def test_forged_forwarded_headers_change_nothing_under_the_default_strategy(api, monkeypatch):
    monkeypatch.setattr(settings, "AUTH_RATE_LIMIT_PER_MINUTE", 2)
    statuses = [
        await _login("203.0.113.60", f"u{i}@example.org", {"X-Forwarded-For": f"192.0.2.{i}"}) for i in range(4)
    ]
    assert statuses == [401, 401, 429, 429]


async def test_forged_entries_cannot_escape_a_trusted_proxy_setup(api, monkeypatch):
    monkeypatch.setattr(settings, "AUTH_RATE_LIMIT_PER_MINUTE", 2)
    monkeypatch.setattr(settings, "CLIENT_IP_STRATEGY", "xff_rightmost")
    monkeypatch.setattr(settings, "TRUSTED_PROXY_CIDRS", "10.0.0.0/8")
    statuses = [
        await _login("10.20.30.40", f"v{i}@example.org", {"X-Forwarded-For": f"192.0.2.{i}, 203.0.113.70"})
        for i in range(4)
    ]
    assert statuses == [401, 401, 429, 429]


async def test_ipv6_clients_in_one_slash_64_share_a_budget(api, monkeypatch):
    monkeypatch.setattr(settings, "AUTH_RATE_LIMIT_PER_MINUTE", 2)
    same_net = [await _login(f"2001:db8:aa:bb::{i}", f"w{i}@example.org") for i in range(1, 4)]
    other_net = await _login("2001:db8:aa:cc::1", "w9@example.org")
    assert same_net == [401, 401, 429]
    assert other_net == 401


async def test_counters_store_only_digests(api, monkeypatch):
    monkeypatch.setattr(settings, "AUTH_RATE_LIMIT_PER_MINUTE", 5)
    await _login("203.0.113.80", "private.person@example.org")
    rows = _rows()
    assert len(rows) == 2  # one address bucket, one account
    for _, key, _ in rows:
        assert len(key) == 64 and all(char in "0123456789abcdef" for char in key)
    stored = " ".join(f"{scope} {key}" for scope, key, _ in rows)
    assert "private.person" not in stored and "203.0.113.80" not in stored
    assert {key for _, key, _ in rows} == {
        subject_key("client", "203.0.113.80"),
        subject_key("account", "private.person@example.org"),
    }


async def test_an_unreachable_store_fails_closed_with_503(api, monkeypatch, caplog):
    monkeypatch.setattr(settings, "AUTH_RATE_LIMIT_PER_MINUTE", 5)
    dead = create_engine("postgresql://nobody@127.0.0.1:1/none", connect_args={"connect_timeout": 1})
    rate_limit.set_limiter(PostgresRateLimiter(dead))
    called = []
    monkeypatch.setattr("app.api.routers.auth.authenticate_user", lambda *args: called.append(args))
    with caplog.at_level(logging.WARNING):
        transport = ASGITransport(app=app, client=("203.0.113.90", 40000))
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/auth/login", json={"email": "victim@example.org", "password": "x"})
    rate_limit.set_limiter(None)
    assert response.status_code == 503
    assert response.headers["Retry-After"] == "30"
    assert called == []  # the credential was never checked
    logged = " ".join(record.getMessage() for record in caplog.records)
    assert "victim" not in logged and "203.0.113.90" not in logged


async def test_limiter_off_means_no_store_access(api, monkeypatch):
    monkeypatch.setattr(settings, "AUTH_RATE_LIMIT_PER_MINUTE", None)
    rate_limit.set_limiter(PostgresRateLimiter(create_engine("postgresql://nobody@127.0.0.1:1/none")))
    assert await _login("203.0.113.91", "x@example.org") == 401
    rate_limit.set_limiter(None)


# --- Degraded identity through the API -------------------------------------------------------------


def _behind_trusted_edge(monkeypatch, limit: int, strategy: str = "header") -> None:
    monkeypatch.setattr(settings, "AUTH_RATE_LIMIT_PER_MINUTE", limit)
    monkeypatch.setattr(settings, "CLIENT_IP_STRATEGY", strategy)
    monkeypatch.setattr(settings, "TRUSTED_PROXY_CIDRS", "10.0.0.0/8")
    monkeypatch.setattr(settings, "CLIENT_IP_HEADER", "cf-connecting-ip")


def _client_rows() -> list:
    accounts = {subject_key("account", f"{prefix}{i}@example.org") for prefix in "abcdefgh" for i in range(12)}
    return [row for row in _rows() if row[1] not in accounts]


async def _proxy_without_client_header(count: int, prefix: str = "a") -> list[int]:
    """Different real clients, all relayed by one trusted proxy that omitted the client header."""
    return [await _login("10.20.30.40", f"{prefix}{i}@example.org") for i in range(count)]


async def test_a_missing_client_header_never_buckets_everyone_under_the_proxy(api, monkeypatch):
    _behind_trusted_edge(monkeypatch, limit=2)
    assert await _proxy_without_client_header(6) == [401] * 6
    assert _client_rows() == []  # no address bucket was written at all


async def test_three_identified_students_behind_one_proxy_get_separate_budgets(api, monkeypatch):
    _behind_trusted_edge(monkeypatch, limit=2)
    statuses = {
        student: [await _login("10.20.30.40", f"{student}{i}@example.org", {"cf-connecting-ip": f"203.0.113.{n}"}) for i in range(3)]
        for n, student in ((11, "a"), (12, "b"), (13, "c"))
    }
    assert statuses == {"a": [401, 401, 429], "b": [401, 401, 429], "c": [401, 401, 429]}


@pytest.mark.parametrize(
    ("strategy", "header", "values"),
    [
        ("header", "cf-connecting-ip", ["nonsense", "203.0.113.1, 203.0.113.2", "10.0.0.9"]),
        ("xff_rightmost", "x-forwarded-for", ["not-an-ip", "203.0.113.1,", "10.0.0.9"]),
    ],
)
async def test_three_students_with_malformed_headers_share_no_bucket(api, monkeypatch, strategy, header, values):
    _behind_trusted_edge(monkeypatch, limit=1, strategy=strategy)
    statuses = [await _login("10.20.30.40", f"{prefix}{i}@example.org", {header: value})
                for prefix, value in zip("def", values) for i in range(2)]
    assert statuses == [401] * 6
    assert _client_rows() == []


async def test_normal_requests_record_no_degraded_events(api, monkeypatch):
    monkeypatch.setattr(settings, "AUTH_RATE_LIMIT_PER_MINUTE", 50)
    for i in range(3):
        await _login(f"203.0.113.{i + 1}", f"e{i}@example.org")
    _behind_trusted_edge(monkeypatch, limit=50)
    await _login("10.20.30.40", "e9@example.org", {"cf-connecting-ip": "203.0.113.9"})
    assert not [key for key in auth_telemetry.snapshot() if key[0] == "client_identity_degraded"]


async def test_degraded_requests_still_hit_the_account_budget(api, monkeypatch):
    _behind_trusted_edge(monkeypatch, limit=2)
    statuses = [await _login("10.20.30.40", "b1@example.org") for _ in range(4)]
    assert statuses == [401, 401, 429, 429]


async def test_one_degraded_client_cannot_lock_out_identified_clients(api, monkeypatch):
    _behind_trusted_edge(monkeypatch, limit=2)
    await _proxy_without_client_header(8, prefix="c")
    identified = [await _login("10.20.30.40", f"d{i}@example.org", {"cf-connecting-ip": "203.0.113.20"}) for i in range(3)]
    other = await _login("10.20.30.40", "d9@example.org", {"cf-connecting-ip": "203.0.113.21"})
    assert identified == [401, 401, 429]  # the identified client keeps its own, enforced budget
    assert other == 401


async def test_an_untrusted_peer_sending_forwarding_headers_gets_no_shared_bucket(api, monkeypatch):
    _behind_trusted_edge(monkeypatch, limit=2, strategy="xff_rightmost")
    statuses = [await _login("198.51.100.40", f"e{i}@example.org", {"X-Forwarded-For": "203.0.113.1"}) for i in range(5)]
    assert statuses == [401] * 5
    assert _client_rows() == []


async def test_a_direct_connection_without_forwarding_headers_keeps_its_address_budget(api, monkeypatch):
    _behind_trusted_edge(monkeypatch, limit=2, strategy="xff_rightmost")
    statuses = [await _login("198.51.100.41", f"f{i}@example.org") for i in range(3)]
    assert statuses == [401, 401, 429]


async def test_an_unparseable_peer_is_never_the_unknown_bucket(api, monkeypatch):
    # uvicorn --proxy-headers copies X-Forwarded-For into the peer without validating it.
    monkeypatch.setattr(settings, "AUTH_RATE_LIMIT_PER_MINUTE", 2)
    statuses = [await _login(peer, f"g{i}@example.org") for i, peer in enumerate(["garbage", "unknown", "x", "", "y"])]
    assert statuses == [401] * 5
    assert _client_rows() == []


async def test_a_degraded_request_still_fails_closed_when_the_store_is_down(api, monkeypatch):
    _behind_trusted_edge(monkeypatch, limit=5)
    rate_limit.set_limiter(PostgresRateLimiter(create_engine("postgresql://nobody@127.0.0.1:1/none", connect_args={"connect_timeout": 1})))
    called = []
    monkeypatch.setattr("app.api.routers.auth.authenticate_user", lambda *args: called.append(args))
    assert await _login("10.20.30.40", "h1@example.org") == 503
    rate_limit.set_limiter(None)
    assert called == []


async def test_mutation_restoring_the_proxy_fallback_locks_everyone_out(api, monkeypatch):
    """Guards the guard: with the old fallback the regression above must fail."""
    _behind_trusted_edge(monkeypatch, limit=2)

    def legacy_identity(request):
        chosen = _legacy_fallback(
            strategy=settings.CLIENT_IP_STRATEGY, peer=request.client.host, headers={k.lower(): v for k, v in request.headers.items()},
            trusted_networks=settings.trusted_proxy_networks, client_ip_header=settings.CLIENT_IP_HEADER,
        )
        return ClientIdentity(chosen, settings.CLIENT_IP_STRATEGY)

    monkeypatch.setattr(rate_limit, "client_identity", legacy_identity)
    statuses = await _proxy_without_client_header(6)
    assert statuses == [401, 401, 429, 429, 429, 429]  # one proxy bucket shared by six different people
    assert statuses != [401] * 6


# --- Telemetry ---------------------------------------------------------------------------------------


async def test_degraded_mode_is_recorded_with_bounded_labels_and_throttled_logs(api, monkeypatch, caplog):
    _behind_trusted_edge(monkeypatch, limit=50)
    with caplog.at_level(logging.INFO, logger="app.auth_telemetry"):
        await _proxy_without_client_header(12, prefix="a")
    assert auth_telemetry.count(
        "client_identity_degraded", endpoint="/auth/login", strategy="header", reason="trusted_proxy_header_missing"
    ) == 12
    degraded = [r for r in caplog.records if "client_identity_degraded" in r.getMessage()]
    assert len(degraded) == 1  # one line per interval, not one per request
    message = degraded[0].getMessage()
    assert degraded[0].levelno == logging.WARNING
    assert "reason=trusted_proxy_header_missing" in message and "strategy=header" in message
    assert "10.20.30.40" not in message and "example.org" not in message


async def test_budget_exhaustion_and_failures_are_counted_without_identities(api, monkeypatch, caplog):
    monkeypatch.setattr(settings, "AUTH_RATE_LIMIT_PER_MINUTE", 2)
    with caplog.at_level(logging.INFO, logger="app.auth_telemetry"):
        for i in range(4):
            await _login("203.0.113.30", f"a{i}@example.org")  # one address, many accounts
        for i in range(4):
            await _login(f"198.51.100.{i + 1}", "b1@example.org")  # one account, many addresses
    assert auth_telemetry.count("ip_budget_exhausted", endpoint="/auth/login") == 2
    assert auth_telemetry.count("account_budget_exhausted", endpoint="/auth/login") == 2
    assert auth_telemetry.count("auth_failure", endpoint="/auth/login") == 4
    logged = " ".join(r.getMessage() for r in caplog.records)
    for secret in ("203.0.113.30", "198.51.100", "example.org", subject_key("account", "b1@example.org")):
        assert secret not in logged
    labels = {label for key in auth_telemetry.snapshot() for label in key[1:]}
    assert labels <= {("endpoint", "/auth/login"), ("endpoint", "/auth/register"), ("budget", "ip"), ("budget", "account")}


async def test_a_success_after_throttling_is_counted(api, monkeypatch, db_session):
    monkeypatch.setattr(settings, "AUTH_RATE_LIMIT_PER_MINUTE", 2)
    clock = FakeClock()
    rate_limit.set_limiter(PostgresRateLimiter(rate_limit.get_limiter().engine, clock=clock, prune_probability=0))
    transport = ASGITransport(app=app, client=("203.0.113.40", 40000))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        assert (await client.post("/auth/register", json={"email": "c1@example.org", "password": "long-enough-password"})).status_code == 201
    statuses = [await _login(f"198.51.100.{i}", "c1@example.org") for i in range(1, 4)]
    assert statuses == [401, 401, 429]
    clock.now += 60
    assert await _login("198.51.100.9", "c1@example.org", password="long-enough-password") == 200
    assert auth_telemetry.count("success_after_throttle", endpoint="/auth/login", budget="account") == 1
    assert auth_telemetry.count("success_after_throttle", endpoint="/auth/login", budget="ip") == 0


def test_unknown_labels_collapse_to_other():
    auth_telemetry.reset()
    auth_telemetry.record("auth_failure", endpoint="203.0.113.1")
    assert auth_telemetry.count("auth_failure", endpoint="other") == 1
    with pytest.raises(ValueError):
        auth_telemetry.record("not-an-event")
    auth_telemetry.reset()


# --- Account lockout (characterisation of current behaviour, not endorsement) ---------------------------


async def _register(email: str, password: str = "long-enough-password", address: str = "203.0.113.200") -> int:
    transport = ASGITransport(app=app, client=(address, 40000))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        return (await client.post("/auth/register", json={"email": email, "password": password})).status_code


async def test_lockout_successful_logins_also_spend_the_account_budget(api, monkeypatch):
    assert await _register("k1@example.org") == 201
    monkeypatch.setattr(settings, "AUTH_RATE_LIMIT_PER_MINUTE", 2)
    statuses = [await _login(f"198.51.100.{i}", "k1@example.org", password="long-enough-password") for i in range(1, 4)]
    assert statuses == [200, 200, 429]


async def test_lockout_budget_is_checked_before_the_password_and_no_hash_runs_when_over(api, monkeypatch):
    monkeypatch.setattr(settings, "AUTH_RATE_LIMIT_PER_MINUTE", 1)
    calls = []
    import app.services.users as users

    real_verify = users.verify_password
    monkeypatch.setattr(users, "verify_password", lambda *a, **kw: calls.append(1) or real_verify(*a, **kw))
    assert await _register("k2@example.org") == 201
    await _login("198.51.100.1", "k2@example.org")
    assert await _login("198.51.100.2", "k2@example.org", password="long-enough-password") == 429
    assert len(calls) == 1  # only the first attempt reached Argon2


async def test_lockout_a_stranger_without_the_password_locks_the_owner_out_for_the_window(api, monkeypatch):
    assert await _register("k3@example.org") == 201
    monkeypatch.setattr(settings, "AUTH_RATE_LIMIT_PER_MINUTE", 2)
    clock = FakeClock()
    rate_limit.set_limiter(PostgresRateLimiter(rate_limit.get_limiter().engine, clock=clock, prune_probability=0))
    for i in range(3):
        await _login(f"192.0.2.{i + 1}", "k3@example.org")  # attacker: wrong password, rotating addresses
    owner = await _login("203.0.113.250", "k3@example.org", password="long-enough-password")
    assert owner == 429  # the right password from the owner's own address is refused
    clock.now += 60
    assert await _login("203.0.113.250", "k3@example.org", password="long-enough-password") == 200


async def test_lockout_responses_do_not_reveal_whether_the_account_exists(api, monkeypatch):
    assert await _register("k4@example.org") == 201
    monkeypatch.setattr(settings, "AUTH_RATE_LIMIT_PER_MINUTE", 2)

    async def sequence(email: str, first_octet: int) -> list[tuple[int, str]]:
        out = []
        for i in range(3):
            transport = ASGITransport(app=app, client=(f"198.51.{first_octet}.{i + 1}", 40000))
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post("/auth/login", json={"email": email, "password": "wrong-password"})
            out.append((response.status_code, response.json()["detail"]))
        return out

    assert await sequence("k4@example.org", 100) == await sequence("nobody-k4@example.org", 101)


async def test_lockout_registration_and_login_budgets_are_separate(api, monkeypatch):
    assert await _register("k5@example.org") == 201
    monkeypatch.setattr(settings, "AUTH_RATE_LIMIT_PER_MINUTE", 1)
    assert [await _register("k5@example.org", address=f"192.0.2.{i}") for i in (10, 11)] == [409, 429]
    assert await _login("203.0.113.251", "k5@example.org", password="long-enough-password") == 200


async def test_lockout_a_registration_conflict_counts_but_runs_no_argon2(api, monkeypatch):
    import app.services.users as users

    hashes = []
    real_hash = users.hash_password
    monkeypatch.setattr(users, "hash_password", lambda password, **kw: hashes.append(1) or real_hash(password, **kw))
    monkeypatch.setattr(settings, "AUTH_RATE_LIMIT_PER_MINUTE", 2)
    assert [await _register("k6@example.org", address=f"192.0.2.{i}") for i in (20, 21, 22)] == [201, 409, 429]
    assert len(hashes) == 1  # only the new account was hashed: the 409 is found before hashing, the 429 earlier still


async def test_lockout_unknown_accounts_skip_argon2(api, monkeypatch):
    # Characterises the pre-existing timing difference: an unknown email returns 401 without hashing.
    import app.services.users as users

    calls = []
    monkeypatch.setattr(users, "verify_password", lambda *a, **kw: calls.append(1) or False)
    monkeypatch.setattr(settings, "AUTH_RATE_LIMIT_PER_MINUTE", 5)
    assert await _register("k7@example.org") == 201
    assert await _login("198.51.100.70", "nobody-k7@example.org") == 401
    assert calls == []
    assert await _login("198.51.100.71", "k7@example.org") == 401
    assert calls == [1]


async def test_malformed_bodies_spend_the_address_budget_but_not_any_account(api, monkeypatch):
    monkeypatch.setattr(settings, "AUTH_RATE_LIMIT_PER_MINUTE", 2)
    transport = ASGITransport(app=app, client=("203.0.113.75", 40000))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        codes = [(await client.post("/auth/login", json={"email": "not-an-email", "password": "x"})).status_code for _ in range(3)]
    assert codes == [422, 422, 429]
    assert [scope for scope, *_ in _rows()] == ["/auth/login"]  # one address row, no account row
    assert await _login("198.51.100.75", "k8@example.org") == 401  # accounts are untouched


async def test_lockout_an_account_counter_failure_fails_closed_after_the_address_passed(api, monkeypatch):
    monkeypatch.setattr(settings, "AUTH_RATE_LIMIT_PER_MINUTE", 5)
    account = subject_key("account", "k9@example.org")

    class AccountStoreDown(PostgresRateLimiter):
        def hit(self, scope, key):
            if key == account:
                raise RateLimitStoreUnavailable
            return super().hit(scope, key)

    rate_limit.set_limiter(AccountStoreDown(rate_limit.get_limiter().engine, prune_probability=0))
    called = []
    monkeypatch.setattr("app.api.routers.auth.authenticate_user", lambda *args: called.append(args))
    assert await _login("203.0.113.76", "k9@example.org") == 503
    rate_limit.set_limiter(None)
    assert called == []
    assert len(_rows()) == 1  # the address attempt was still counted


# --- uvicorn with the production start flags -----------------------------------------------------------


@pytest.fixture(scope="module")
def production_flags_server():
    """uvicorn --proxy-headers --forwarded-allow-ips="*" (as render.yaml), peer strategy, limit 3."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    env = {
        **os.environ, "APP_ENV": "development", "DATABASE_URL": settings.DATABASE_URL, "JWT_SECRET": "t" * 40,
        "AUTH_RATE_LIMIT_PER_MINUTE": "3", "CLIENT_IP_STRATEGY": "peer", "TRUSTED_PROXY_CIDRS": "",
    }
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port),
         "--proxy-headers", "--forwarded-allow-ips=*"],
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
        pytest.fail("production-flags server did not become healthy")
    yield base
    process.terminate()
    process.wait(timeout=10)


def test_production_flags_garbage_forwarded_for_creates_no_global_bucket(store, production_flags_server):
    _start_in_a_fresh_window()
    statuses = [_proxied_login(production_flags_server, "garbage", f"s{i}@example.org") for i in range(6)]
    assert statuses == [401] * 6


def test_production_flags_forged_addresses_still_evade_the_address_budget_but_not_the_account(store, production_flags_server):
    _start_in_a_fresh_window()
    # Characterises the unfixed production exposure: under "*" the leftmost entry is the peer.
    many_accounts = [_proxied_login(production_flags_server, f"192.0.2.{i}", f"t{i}@example.org") for i in range(6)]
    one_account = [_proxied_login(production_flags_server, f"192.0.2.{i + 50}", "u@example.org") for i in range(5)]
    assert many_accounts == [401] * 6  # the address budget is forgeable under the current start command
    assert one_account == [401, 401, 401, 429, 429]  # the account budget is not


# --- A real server behind a trusted proxy ---------------------------------------------------------------


@pytest.fixture(scope="module")
def proxied_server():
    """uvicorn WITHOUT --proxy-headers, trusting only loopback as the proxy and the rightmost XFF entry."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    env = {
        **os.environ,
        "APP_ENV": "development",
        "DATABASE_URL": settings.DATABASE_URL,
        "JWT_SECRET": "t" * 40,
        "AUTH_RATE_LIMIT_PER_MINUTE": "3",
        "CLIENT_IP_STRATEGY": "xff_rightmost",
        "TRUSTED_PROXY_CIDRS": "127.0.0.1/32",
        "TRUSTED_PROXY_HOPS": "1",
    }
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port), "--no-proxy-headers"],
        cwd=BACKEND_DIR,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
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
        pytest.fail("proxied server did not become healthy")
    yield base
    process.terminate()
    process.wait(timeout=10)


def _start_in_a_fresh_window(margin: float = 8.0) -> None:
    """Real servers count on the wall clock: wait out a window edge so a test cannot straddle it."""
    remaining = rate_limit.WINDOW_SECONDS - time.time() % rate_limit.WINDOW_SECONDS
    if remaining < margin:
        time.sleep(remaining + 0.1)


def _proxied_login(base: str, forwarded_for: str, email: str) -> int:
    return httpx.post(
        f"{base}/auth/login", json={"email": email, "password": "wrong-password"},
        headers={"X-Forwarded-For": forwarded_for}, timeout=10,
    ).status_code


def test_through_a_trusted_proxy_each_real_client_gets_its_own_budget(store, proxied_server):
    _start_in_a_fresh_window()
    first = [_proxied_login(proxied_server, f"192.0.2.{i}, 203.0.113.101", f"p{i}@example.org") for i in range(4)]
    second = _proxied_login(proxied_server, "203.0.113.102", "q@example.org")
    assert first == [401, 401, 401, 429]  # rotating forged prefixes did not help the first client
    assert second == 401  # a different real client is unaffected


def test_through_a_real_server_the_proxy_itself_is_never_a_client_identity(store, proxied_server):
    _start_in_a_fresh_window()
    # The trusted proxy (loopback here) relays without X-Forwarded-For: with the old fallback every
    # student would land in the proxy's bucket and the fourth would be refused.
    statuses = [
        httpx.post(f"{proxied_server}/auth/login", json={"email": f"z{i}@example.org", "password": "wrong-password"}, timeout=10).status_code
        for i in range(6)
    ]
    assert statuses == [401] * 6
    assert len(_rows()) == 6  # six account buckets, no address bucket


def test_through_a_trusted_proxy_an_ipv6_client_is_bucketed(store, proxied_server):
    _start_in_a_fresh_window()
    statuses = [_proxied_login(proxied_server, f"2001:db8:7:8::{i}", f"r{i}@example.org") for i in range(1, 5)]
    assert statuses == [401, 401, 401, 429]


# --- The account budget across real processes ---------------------------------------------------------


def test_concurrent_attempts_on_one_account_cannot_overshoot_the_budget(store, production_flags_server):
    _start_in_a_fresh_window()
    barrier = threading.Barrier(20)

    def attempt(i):
        barrier.wait()
        return _proxied_login(production_flags_server, f"192.0.2.{100 + i}", "concurrent@example.org")

    with ThreadPoolExecutor(max_workers=20) as pool:
        statuses = list(pool.map(attempt, range(20)))
    assert sorted(statuses) == [401] * 3 + [429] * 17  # limit 3: exactly three reach the password check


def test_the_account_budget_is_shared_by_separate_application_processes(store, production_flags_server, proxied_server):
    _start_in_a_fresh_window()
    first = [_proxied_login(production_flags_server, f"192.0.2.{150 + i}", "shared@example.org") for i in range(3)]
    second = _proxied_login(proxied_server, "203.0.113.150", "shared@example.org")
    assert first == [401, 401, 401]
    assert second == 429  # a different process, a different address, the same account counter
