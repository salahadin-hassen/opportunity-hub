"""R-2 regression tests: the per-account credential limit is mandatory in production.

With ``CLIENT_IP_STRATEGY=none`` it is the only credential limit, so production must refuse to start
without a valid one, and an unset variable must mean the secure default (10/min), not "off".
This gives no per-address protection (review R-3).
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError

from app.core import rate_limit
from app.core.config import Settings, settings

BACKEND_DIR = Path(__file__).resolve().parents[1]


def _settings(**values) -> Settings:
    return Settings(_env_file=None, DATABASE_URL="postgresql://u@h/db", JWT_SECRET="s" * 40, **values)


@pytest.mark.parametrize("app_env", ["production", "development"])
def test_unset_means_the_secure_default_not_off(app_env):
    configured = _settings(APP_ENV=app_env)
    assert configured.AUTH_RATE_LIMIT_PER_MINUTE == 10 and configured.auth_rate_limit == 10


@pytest.mark.parametrize("value", ["0", "-1", "-10", "abc", "", "  ", "1.5", "1001", "True", 0, -3, 1001])
@pytest.mark.parametrize("app_env", ["production", "development"])
def test_invalid_values_are_refused_everywhere(value, app_env):
    with pytest.raises(ValidationError, match="AUTH_RATE_LIMIT_PER_MINUTE"):
        _settings(APP_ENV=app_env, AUTH_RATE_LIMIT_PER_MINUTE=value)


def test_disabled_is_refused_in_production_only():
    with pytest.raises(ValidationError, match="refused in production"):
        _settings(APP_ENV="production", AUTH_RATE_LIMIT_PER_MINUTE="disabled")
    assert _settings(APP_ENV="development", AUTH_RATE_LIMIT_PER_MINUTE="disabled").auth_rate_limit is None


@pytest.mark.parametrize("value, expected", [("1", 1), ("10", 10), (" 25 ", 25), ("1000", 1000), (7, 7)])
def test_valid_values_are_used(value, expected):
    assert _settings(APP_ENV="production", AUTH_RATE_LIMIT_PER_MINUTE=value).auth_rate_limit == expected


# --- A real production-mode server -----------------------------------------------------------------------


def _start(extra_env: dict[str, str], log_path: Path):
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    env = {**os.environ, "APP_ENV": "production", "RENDER": "true", "CLIENT_IP_STRATEGY": "none",
           "DATABASE_URL": settings.DATABASE_URL, "JWT_SECRET": "p" * 48, "ALLOWED_HOSTS": "127.0.0.1"}
    env.pop("AUTH_RATE_LIMIT_PER_MINUTE", None)
    env["APP_ENV_FILE"] = ""  # never read a developer's backend/.env: "unset" must really be unset
    env.update(extra_env)
    log = log_path.open("wb")
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port),
         "--proxy-headers", "--forwarded-allow-ips=*"],
        cwd=BACKEND_DIR, env=env, stdout=log, stderr=subprocess.STDOUT,
    )
    return process, log, f"http://127.0.0.1:{port}"


def _wait_healthy(process, base) -> bool:
    for _ in range(150):
        if process.poll() is not None:
            return False
        try:
            if httpx.get(f"{base}/health", timeout=1).status_code == 200:
                return True
        except httpx.HTTPError:
            time.sleep(0.1)
    return False


@pytest.fixture
def clean():
    rate_limit.set_limiter(None)
    rate_limit.reset()
    remaining = rate_limit.WINDOW_SECONDS - time.time() % rate_limit.WINDOW_SECONDS
    if remaining < 15:
        time.sleep(remaining + 0.1)
    yield
    rate_limit.reset()


def test_production_with_the_variable_unset_enforces_ten_per_minute_per_account(tmp_path, clean):
    process, log, base = _start({}, tmp_path / "server.log")
    try:
        assert _wait_healthy(process, base), "production server did not start"
        statuses = [
            httpx.post(f"{base}/auth/login", json={"email": "target@example.org", "password": "wrong-password"},
                       headers={"X-Forwarded-For": f"9.9.9.{i}"}, timeout=10).status_code
            for i in range(12)
        ]
        assert statuses == [401] * 10 + [429, 429]  # forged addresses don't help: account budget only
    finally:
        process.terminate()
        process.wait(timeout=10)
        log.close()


@pytest.mark.parametrize("value", ["0", "-1", "abc", "", "disabled"])
def test_production_refuses_to_start_with_an_invalid_or_disabled_limit(tmp_path, value):
    process, log, base = _start({"AUTH_RATE_LIMIT_PER_MINUTE": value}, tmp_path / "server.log")
    try:
        assert not _wait_healthy(process, base)
        assert process.wait(timeout=20) != 0
        assert "AUTH_RATE_LIMIT_PER_MINUTE" in (tmp_path / "server.log").read_text()
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=10)
        log.close()
