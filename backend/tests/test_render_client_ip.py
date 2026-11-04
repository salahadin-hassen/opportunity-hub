"""The ``render_cf_connecting_ip`` strategy: synthetic headers on local servers only (no production traffic).

These prove how the application treats ``CF-Connecting-IP``. They can't prove what Render and Cloudflare do: that
the header is always written and can't be forged rests on Render's published statements (see
``docs/architecture/RENDER_CLIENT_IP_VERIFICATION.md``). Tests named ``..._assumption...`` record that limit.
Client addresses are real public ones, because the strategy refuses documentation and private ranges.
"""
from __future__ import annotations

import logging
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.core import auth_telemetry, rate_limit
from app.core.client_ip import ClientIdentity, select_client_identity
from app.core.config import Settings, settings
from app.core.rate_limit import PostgresRateLimiter, subject_key
from app.db.session import get_db
from app.main import app

BACKEND_DIR = Path(__file__).resolve().parents[1]
STRATEGY = "render_cf_connecting_ip"
FORGED_XFF = "1.2.3.4, 5.6.7.8"


def identify(headers: dict[str, str], peer: str | None = "10.0.0.1") -> ClientIdentity:
    return select_client_identity(strategy=STRATEGY, peer=peer, headers=headers)


def unavailable(reason: str) -> ClientIdentity:
    return ClientIdentity(None, STRATEGY, reason, False)


# --- Selection (pure) ------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("8.8.8.8", "8.8.8.8"),
        (" 8.8.8.8 ", "8.8.8.8"),
        ("::ffff:8.8.8.8", "8.8.8.8"),
        ("2606:4700:4700::1111", "2606:4700:4700::/64"),
        ("2606:4700:4700:0:0:0:0:1111", "2606:4700:4700::/64"),
        ("2606:4700:4700:0::ABCD", "2606:4700:4700::/64"),
    ],
)
def test_a_valid_address_is_normalised(value, expected):
    assert identify({"cf-connecting-ip": value}) == ClientIdentity(expected, STRATEGY)


def test_ipv6_clients_in_one_slash_64_share_an_identity():
    first = identify({"cf-connecting-ip": "2606:4700:4700:1::1"}).identity
    assert first == identify({"cf-connecting-ip": "2606:4700:4700:1:ffff::9"}).identity
    assert first != identify({"cf-connecting-ip": "2606:4700:4700:2::1"}).identity


@pytest.mark.parametrize("value", ["", "   "])
def test_a_blank_header_is_missing(value):
    assert identify({"cf-connecting-ip": value}) == unavailable("trusted_proxy_header_missing")


def test_a_missing_header_is_missing_and_never_the_peer_or_forwarded_for():
    for peer in ("8.8.4.4", "10.0.0.1", "garbage", None):
        assert identify({"x-forwarded-for": FORGED_XFF, "x-real-ip": "9.9.9.9"}, peer) == unavailable("trusted_proxy_header_missing")


@pytest.mark.parametrize(
    "value",
    [
        "garbage", "unknown", "999.1.1.1", "8.8.8", "8.8.8.8:443", "[2606:4700:4700::1111]", "[2606:4700:4700::1111]:443",
        "08.8.8.8", "2606:4700:4700::1111%eth0", "8.8.8.8/32", "8.8.8.8 9.9.9.9",
    ],
)
def test_a_malformed_value_is_invalid(value):
    assert identify({"cf-connecting-ip": value}) == unavailable("trusted_proxy_header_invalid")


@pytest.mark.parametrize(
    "value",
    ["10.0.0.1", "127.0.0.1", "169.254.1.1", "192.168.1.1", "100.64.0.1", "0.0.0.0", "203.0.113.7", "::1", "fe80::1", "fd00::1", "2001:db8::1"],
)
def test_an_address_no_internet_client_can_have_is_invalid(value):
    assert identify({"cf-connecting-ip": value}) == unavailable("trusted_proxy_header_invalid")


@pytest.mark.parametrize("value", ["8.8.8.8, 9.9.9.9", "8.8.8.8,8.8.8.8", "8.8.8.8,"])
def test_a_list_is_ambiguous(value):
    assert identify({"cf-connecting-ip": value}) == unavailable("ambiguous_forwarded_chain")


def test_cloudflares_constant_worker_address_is_never_a_bucket():
    assert identify({"cf-connecting-ip": "2a06:98c0:3600::103"}) == unavailable("trusted_proxy_header_invalid")
    assert identify({"cf-connecting-ip": "2A06:98C0:3600:0::103"}) == unavailable("trusted_proxy_header_invalid")


def test_forged_forwarded_for_never_changes_a_valid_identity():
    for forged in (FORGED_XFF, "garbage", "8.8.4.4"):
        assert identify({"cf-connecting-ip": "8.8.8.8", "x-forwarded-for": forged}).identity == "8.8.8.8"


# Pseudo IPv4: "Overwrite Headers" puts a Class E address in CF-Connecting-IP and the real one in CF-Connecting-IPv6.


def test_a_pseudo_ipv4_uses_the_real_ipv6_address():
    headers = {"cf-connecting-ip": "250.1.2.3", "cf-connecting-ipv6": "2606:4700:4700:1::1"}
    assert identify(headers).identity == "2606:4700:4700:1::/64"


@pytest.mark.parametrize("ipv6", [None, "", "garbage", "8.8.8.8", "fd00::1", "2a06:98c0:3600::103", "2606:4700::1, 2606:4701::1"])
def test_a_pseudo_ipv4_without_a_usable_ipv6_is_invalid(ipv6):
    headers = {"cf-connecting-ip": "250.1.2.3"} | ({} if ipv6 is None else {"cf-connecting-ipv6": ipv6})
    assert identify(headers) == unavailable("trusted_proxy_header_invalid")


def test_cf_connecting_ipv6_is_ignored_next_to_a_real_address():
    # Cloudflare documents overwriting it only in pseudo mode, so outside that mode a caller might have set it.
    assert identify({"cf-connecting-ip": "8.8.8.8", "cf-connecting-ipv6": "2606:4700:4700:1::1"}).identity == "8.8.8.8"


def test_private_network_assumption_a_caller_without_the_header_gets_no_identity_but_one_with_it_is_believed():
    """Paid plans can receive private traffic, which skips Cloudflare. The code can't tell: this records the limit."""
    assert identify({}, peer="10.204.1.5").identity is None
    assert identify({"cf-connecting-ip": "8.8.8.8"}, peer="10.204.1.5").identity == "8.8.8.8"


def test_outside_this_strategy_the_header_is_not_trusted():
    for strategy, options in (("peer", {}), ("xff_rightmost", {"trusted_networks": [], "trusted_hops": 1})):
        chosen = select_client_identity(strategy=strategy, peer="8.8.4.4", headers={"cf-connecting-ip": "8.8.8.8"}, **options)
        assert chosen.identity == "8.8.4.4"


# --- Settings ---------------------------------------------------------------------------------------------


def _settings(**values) -> Settings:
    return Settings(_env_file=None, DATABASE_URL="postgresql://u@h/db", JWT_SECRET="s" * 40, **values)


def test_the_strategy_is_opt_in():
    assert _settings().CLIENT_IP_STRATEGY == "peer"
    assert _settings(CLIENT_IP_STRATEGY=STRATEGY).CLIENT_IP_STRATEGY == STRATEGY  # needs no CIDRs and no header name


@pytest.mark.parametrize("extra", [{"TRUSTED_PROXY_CIDRS": "10.0.0.0/8"}, {"CLIENT_IP_HEADER": "cf-connecting-ip"}])
def test_settings_this_strategy_would_ignore_are_refused(extra):
    with pytest.raises(ValidationError):
        _settings(CLIENT_IP_STRATEGY=STRATEGY, **extra)


def test_production_refuses_the_strategy_away_from_render(monkeypatch):
    monkeypatch.delenv("RENDER", raising=False)
    with pytest.raises(ValidationError, match="only on Render"):
        _settings(CLIENT_IP_STRATEGY=STRATEGY, APP_ENV="production")
    monkeypatch.setenv("RENDER", "false")
    with pytest.raises(ValidationError, match="only on Render"):
        _settings(CLIENT_IP_STRATEGY=STRATEGY, APP_ENV="production")
    monkeypatch.setenv("RENDER", "true")
    assert _settings(CLIENT_IP_STRATEGY=STRATEGY, APP_ENV="production").is_production


# --- Through the API ------------------------------------------------------------------------------------


class FrozenClock:
    def __call__(self) -> float:
        return 1_800_000_000.0


@pytest.fixture
def api(db_session: Session, monkeypatch):
    monkeypatch.setattr(settings, "AUTH_RATE_LIMIT_PER_MINUTE", 2)
    monkeypatch.setattr(settings, "CLIENT_IP_STRATEGY", STRATEGY)
    rate_limit.set_limiter(None)
    rate_limit.reset()
    auth_telemetry.reset()
    rate_limit.set_limiter(PostgresRateLimiter(rate_limit.get_limiter().engine, clock=FrozenClock()))
    app.dependency_overrides[get_db] = lambda: (yield db_session)
    yield
    app.dependency_overrides.clear()
    rate_limit.set_limiter(None)
    rate_limit.reset()
    auth_telemetry.reset()


async def _login(email: str, headers=None, peer: str = "10.0.0.1") -> int:
    transport = ASGITransport(app=app, client=(peer, 40000))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/auth/login", json={"email": email, "password": "wrong-password"}, headers=headers)
    return response.status_code


def _client_keys() -> set[str]:
    with rate_limit.get_limiter().engine.connect() as connection:
        return {row[0] for row in connection.execute(text("SELECT key FROM rate_limit_buckets"))}


async def test_one_client_is_limited_however_it_rotates_forwarded_for(api):
    statuses = [await _login(f"a{i}@example.org", {"CF-Connecting-IP": "8.8.8.8", "X-Forwarded-For": f"9.9.9.{i}"}) for i in range(4)]
    assert statuses == [401, 401, 429, 429]


async def test_clients_behind_one_proxy_peer_keep_separate_budgets(api):
    for client in ("8.8.8.8", "9.9.9.9", "1.1.1.1"):
        statuses = [await _login(f"{client}-{i}@example.org", {"CF-Connecting-IP": client}) for i in range(3)]
        assert statuses == [401, 401, 429]


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"X-Forwarded-For": FORGED_XFF},
        {"CF-Connecting-IP": "garbage"},
        {"CF-Connecting-IP": "10.0.0.1"},
        {"CF-Connecting-IP": "2a06:98c0:3600::103"},
        [("CF-Connecting-IP", "8.8.8.8"), ("CF-Connecting-IP", "9.9.9.9")],
    ],
)
async def test_without_an_identity_only_the_address_budget_is_skipped(api, headers):
    assert [await _login(f"b{i}@example.org", headers) for i in range(5)] == [401] * 5  # no shared bucket
    account_keys = {subject_key("account", f"b{i}@example.org") for i in range(5)}
    assert _client_keys() == account_keys  # nothing but account rows was written
    for name in ("10.0.0.1", "unknown", "1.2.3.4", "8.8.8.8", "9.9.9.9"):
        assert subject_key("client", name) not in _client_keys()
    assert [await _login("same@example.org", headers) for _ in range(3)] == [401, 401, 429]  # the account budget holds


async def test_a_duplicated_header_line_is_ambiguous_not_last_wins(api):
    await _login("c@example.org", [("CF-Connecting-IP", "8.8.8.8"), ("CF-Connecting-IP", "9.9.9.9")])
    assert auth_telemetry.count(
        "client_identity_degraded", endpoint="/auth/login", strategy=STRATEGY, reason="ambiguous_forwarded_chain"
    ) == 1


async def test_a_store_failure_still_fails_closed(api):
    rate_limit.set_limiter(PostgresRateLimiter(create_engine("postgresql://nobody@127.0.0.1:1/none", connect_args={"connect_timeout": 1})))
    assert await _login("d@example.org", {"CF-Connecting-IP": "8.8.8.8"}) == 503
    assert await _login("d@example.org") == 503  # with no identity, the account write fails the same way


async def test_logs_hold_no_client_address_and_labels_stay_bounded(api, caplog):
    with caplog.at_level(logging.INFO):
        for headers in ({"CF-Connecting-IP": "8.8.8.8"}, {"CF-Connecting-IP": "9.9.9.9, 1.1.1.1"}, {"CF-Connecting-IP": "garbage-value"}, {}):
            for i in range(4):
                await _login(f"private{i}@example.org", {**headers, "X-Forwarded-For": "4.4.4.4"})
    logged = " ".join(record.getMessage() for record in caplog.records)
    for secret in ("8.8.8.8", "9.9.9.9", "1.1.1.1", "4.4.4.4", "garbage-value", "private0", "example.org"):
        assert secret not in logged
    assert "client_identity_degraded" in logged
    labels = {label for key in auth_telemetry.snapshot() for label in key[1:]}
    assert ("strategy", STRATEGY) in labels
    assert all(value != "other" for _, value in labels)


# --- Real uvicorn, under both start commands ---------------------------------------------------------------

# The first release keeps CURRENT_FLAGS; the identity must hold under both. NO_PROXY_HEADERS is a later change: the
# redirect test below shows why it can't simply be switched on.
CURRENT_FLAGS = ["--proxy-headers", "--forwarded-allow-ips=*"]
NO_PROXY_HEADERS = ["--no-proxy-headers"]


def _serve(flags: list[str], log_path: Path, strategy: str = STRATEGY):
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    env = {**os.environ, "APP_ENV": "development", "DATABASE_URL": settings.DATABASE_URL, "JWT_SECRET": "t" * 40,
           "AUTH_RATE_LIMIT_PER_MINUTE": "3", "CLIENT_IP_STRATEGY": strategy, "TRUSTED_PROXY_CIDRS": "", "RENDER": "true"}
    log = log_path.open("wb")
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port), *flags],
        cwd=BACKEND_DIR, env=env, stdout=log, stderr=subprocess.STDOUT,
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
        pytest.fail("server did not become healthy")
    return process, log, base


@pytest.fixture(scope="module", params=["current", "no_proxy_headers"])
def server(request, tmp_path_factory):
    flags = CURRENT_FLAGS if request.param == "current" else NO_PROXY_HEADERS
    log_path = tmp_path_factory.mktemp("uvicorn") / "server.log"
    process, log, base = _serve(flags, log_path)
    yield request.param, base, log_path
    process.terminate()
    process.wait(timeout=10)
    log.close()


@pytest.fixture
def clean():
    rate_limit.set_limiter(None)
    rate_limit.reset()
    remaining = rate_limit.WINDOW_SECONDS - time.time() % rate_limit.WINDOW_SECONDS
    if remaining < 8:  # real servers count on the wall clock: don't straddle a window edge
        time.sleep(remaining + 0.1)
    yield
    rate_limit.reset()


def _post(base: str, email: str, headers=None) -> int:
    return httpx.post(f"{base}/auth/login", json={"email": email, "password": "wrong-password"}, headers=headers, timeout=10).status_code


def test_real_server_forged_forwarded_for_cannot_evade_the_address_budget(server, clean):
    _, base, _ = server
    statuses = [_post(base, f"e{i}@example.org", {"CF-Connecting-IP": "8.8.8.8", "X-Forwarded-For": f"9.9.9.{i}"}) for i in range(5)]
    assert statuses == [401, 401, 401, 429, 429]
    assert _post(base, "e9@example.org", {"CF-Connecting-IP": "1.1.1.1", "X-Forwarded-For": "9.9.9.1"}) == 401  # someone else


def test_real_server_without_the_header_forged_forwarded_for_buys_no_identity(server, clean):
    _, base, _ = server
    assert [_post(base, f"f{i}@example.org", {"X-Forwarded-For": f"9.9.9.{i}"}) for i in range(6)] == [401] * 6
    assert [_post(base, "f-same@example.org", {"X-Forwarded-For": f"9.9.8.{i}"}) for i in range(5)] == [401, 401, 401, 429, 429]


def test_real_server_duplicate_header_lines_get_no_identity(server, clean):
    _, base, _ = server
    headers = [("CF-Connecting-IP", "8.8.8.8"), ("CF-Connecting-IP", "9.9.9.9")]
    assert [_post(base, f"g{i}@example.org", headers) for i in range(6)] == [401] * 6


def test_ingress_assumption_custom_domain_and_onrender_hostnames_are_treated_alike(server, clean):
    """Only the Host header differs locally: this shows the code doesn't vary by hostname, not how Render routes them."""
    _, base, _ = server
    hosts = ["api.opportunities.sahelyon.com", "opportunity-hub-api.onrender.com"] * 3
    statuses = [_post(base, f"h{i}@example.org", {"Host": host, "CF-Connecting-IP": "8.8.8.8"}) for i, host in enumerate(hosts)]
    assert statuses == [401, 401, 401, 429, 429, 429]


def test_trust_assumption_a_direct_connection_can_forge_the_header(server, clean):
    """Why this is Render-only: anything that reaches the process directly picks its own identity."""
    _, base, _ = server
    statuses = [_post(base, f"i{i}@example.org", {"CF-Connecting-IP": f"9.9.6.{i}"}) for i in range(6)]
    assert statuses == [401] * 6  # each forged value got its own budget


def test_uvicorn_flags_and_the_access_log(server, clean):
    """Under the current flags uvicorn believes a forged X-Forwarded-For and logs it; --no-proxy-headers doesn't."""
    name, base, log_path = server
    _post(base, "j@example.org", {"CF-Connecting-IP": "8.8.8.8", "X-Forwarded-For": "4.3.2.1"})
    for _ in range(100):  # wait for the access-log line to reach the file
        log = log_path.read_text()
        if "POST /auth/login" in log:
            break
        time.sleep(0.05)
    assert "POST /auth/login" in log
    if name == "current":
        assert "4.3.2.1" in log
    else:
        assert "4.3.2.1" not in log and "127.0.0.1" in log
    assert "8.8.8.8" not in log  # CF-Connecting-IP is never logged under either


def test_uvicorn_flags_and_the_redirect_scheme(server, clean):
    """A trailing-slash redirect keeps https only while uvicorn trusts X-Forwarded-Proto."""
    name, base, _ = server
    response = httpx.get(f"{base}/opportunities/", headers={"X-Forwarded-Proto": "https", "Host": "api.example.org"}, timeout=10)
    assert response.status_code == 307
    expected = "https" if name == "current" else "http"
    assert response.headers["location"].startswith(f"{expected}://api.example.org/opportunities")


def test_the_peer_strategy_with_the_current_flags_stays_forgeable(tmp_path, clean):
    """Characterises today's production: this is what moving to the new strategy removes."""
    process, log, base = _serve(CURRENT_FLAGS, tmp_path / "peer.log", strategy="peer")
    try:
        assert [_post(base, f"k{i}@example.org", {"X-Forwarded-For": f"9.9.5.{i}"}) for i in range(6)] == [401] * 6
    finally:
        process.terminate()
        process.wait(timeout=10)
        log.close()
