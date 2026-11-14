"""P0-1 regression tests: forged forwarding headers cannot evade, or weaponise, the login limits.

Production runs uvicorn with ``--proxy-headers --forwarded-allow-ips="*"``, which makes the ASGI client
address the leftmost, client-chosen ``X-Forwarded-For`` entry. These tests pin down that:

* the ``peer`` strategy (which reads that address) can no longer be deployed on Render;
* under the deployable ``none`` strategy, forged headers buy neither a fresh budget nor the power to
  exhaust somebody else's, and the per-account budget still stops guessing on one account;
* the committed ``render.yaml`` produces settings that pass validation for every Python service.

What they cannot show is what Render and Cloudflare do on the live service; see
``docs/architecture/RENDER_CLIENT_IP_VERIFICATION.md``.
"""
from __future__ import annotations

import time
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError
from sqlalchemy import create_engine, text

from app.core import rate_limit
from app.core.client_ip import select_client_identity
from app.core.config import Settings, settings
from app.core.rate_limit import subject_key
from tests.test_render_client_ip import CURRENT_FLAGS, _post, _serve

REPO_ROOT = Path(__file__).resolve().parents[2]


def _settings(**values) -> Settings:
    return Settings(_env_file=None, DATABASE_URL="postgresql://u@h/db", JWT_SECRET="s" * 40, **values)


# --- Configuration ---------------------------------------------------------------------------------------


def test_peer_is_refused_in_production_on_render(monkeypatch):
    monkeypatch.setenv("RENDER", "true")
    with pytest.raises(ValidationError, match="peer is refused in production on Render"):
        _settings(APP_ENV="production")  # peer is the default, so forgetting the variable is refused too


def test_peer_stays_available_off_render_and_outside_production(monkeypatch):
    monkeypatch.delenv("RENDER", raising=False)
    assert _settings(APP_ENV="production").CLIENT_IP_STRATEGY == "peer"  # e.g. a directly exposed host
    monkeypatch.setenv("RENDER", "true")
    assert _settings(APP_ENV="development").CLIENT_IP_STRATEGY == "peer"  # development (APP_ENV explicit on Render)


def test_none_is_valid_on_render_and_takes_no_proxy_settings(monkeypatch):
    monkeypatch.setenv("RENDER", "true")
    assert _settings(APP_ENV="production", CLIENT_IP_STRATEGY="none").CLIENT_IP_STRATEGY == "none"
    for extra in ({"TRUSTED_PROXY_CIDRS": "10.0.0.0/8"}, {"CLIENT_IP_HEADER": "x-real-ip"}):
        with pytest.raises(ValidationError, match="none ignores"):
            _settings(APP_ENV="development", CLIENT_IP_STRATEGY="none", **extra)


def test_none_never_yields_an_identity_whatever_the_headers_say():
    identity = select_client_identity(
        strategy="none", peer="203.0.113.9",
        headers={"x-forwarded-for": "8.8.8.8", "cf-connecting-ip": "8.8.4.4", "x-real-ip": "1.1.1.1"},
    )
    assert identity.identity is None and identity.reason == "address_budget_disabled"


def _render_env(service: dict) -> dict[str, str]:
    """Literal values from render.yaml, with placeholders for secrets Render supplies."""
    env: dict[str, str] = {}
    for item in service.get("envVars", []):
        if "value" in item:
            env[item["key"]] = str(item["value"])
        elif item["key"] == "JWT_SECRET":
            env[item["key"]] = "g" * 64  # generateValue / fromService on Render
        elif item["key"] == "DATABASE_URL":
            env[item["key"]] = "postgresql://u@h/db"
    return env


@pytest.mark.parametrize("name", ["opportunity-hub-api", "opportunity-hub-email-worker", "opportunity-hub-account-purge"])
def test_render_yaml_settings_boot_in_production_on_render(monkeypatch, name):
    blueprint = yaml.safe_load((REPO_ROOT / "render.yaml").read_text())
    service = next(item for item in blueprint["services"] if item["name"] == name)
    keys = {item["key"] for item in service["envVars"]}
    assert "JWT_SECRET" in keys, f"{name} would fail production settings validation"
    env = _render_env(service)
    assert env.get("CLIENT_IP_STRATEGY") in ("none", "render_cf_connecting_ip")

    monkeypatch.setenv("RENDER", "true")
    configured = Settings(_env_file=None, **{key: value for key, value in env.items() if key in Settings.model_fields})
    assert configured.is_production
    assert configured.CLIENT_IP_STRATEGY != "peer"


# --- A real server with the production start flags -------------------------------------------------------


@pytest.fixture
def clean():
    rate_limit.set_limiter(None)
    rate_limit.reset()
    remaining = rate_limit.WINDOW_SECONDS - time.time() % rate_limit.WINDOW_SECONDS
    if remaining < 10:  # real servers count on the wall clock: don't straddle a window edge
        time.sleep(remaining + 0.1)
    yield
    rate_limit.reset()


@pytest.fixture(scope="module")
def production_flags_none(tmp_path_factory):
    process, log, base = _serve(CURRENT_FLAGS, tmp_path_factory.mktemp("none") / "server.log", strategy="none")
    yield base
    process.terminate()
    process.wait(timeout=10)
    log.close()


def _bucket_keys() -> set[str]:
    engine = create_engine(settings.DATABASE_URL)
    try:
        with engine.connect() as connection:
            return set(connection.execute(text("SELECT key FROM rate_limit_buckets")).scalars())
    finally:
        engine.dispose()


def test_rotating_forged_forwarded_for_cannot_reset_the_account_budget(production_flags_none, clean):
    statuses = [_post(production_flags_none, "victim@example.org", {"X-Forwarded-For": f"9.9.9.{i}"}) for i in range(6)]
    assert statuses == [401, 401, 401, 429, 429, 429]  # limit 3 per account per minute


def test_forged_addresses_create_no_address_buckets(production_flags_none, clean):
    forged = [f"9.9.8.{i}" for i in range(5)]
    for i, address in enumerate(forged):
        _post(production_flags_none, f"spray{i}@example.org", {"X-Forwarded-For": address})
    keys = _bucket_keys()
    assert keys, "the account budget should have written rows"
    assert not keys & {subject_key("client", address) for address in forged}
    assert subject_key("client", "127.0.0.1") not in keys  # nor one shared bucket for the proxy


def test_a_forged_victim_address_cannot_lock_the_victim_out(production_flags_none, clean):
    victim_ip = "8.8.8.8"
    attacker = [_post(production_flags_none, f"x{i}@example.org", {"X-Forwarded-For": victim_ip}) for i in range(6)]
    assert attacker == [401] * 6  # no address budget to exhaust
    assert _post(production_flags_none, "real-user@example.org", {"X-Forwarded-For": victim_ip}) == 401  # not 429


def test_under_peer_the_same_flags_let_a_forged_address_lock_out_its_owner(tmp_path, clean):
    """Characterises why peer is refused on Render: a stranger can spend the victim's address budget."""
    process, log, base = _serve(CURRENT_FLAGS, tmp_path / "peer.log", strategy="peer")
    try:
        victim_ip = "8.8.8.8"
        assert [_post(base, f"y{i}@example.org", {"X-Forwarded-For": victim_ip}) for i in range(3)] == [401] * 3
        assert _post(base, "real-user@example.org", {"X-Forwarded-For": victim_ip}) == 429
    finally:
        process.terminate()
        process.wait(timeout=10)
        log.close()
