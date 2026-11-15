"""Create the accounts the Playwright suite needs, in a throwaway end-to-end database only.

    E2E_ADMIN_PASSWORD=... python -m scripts.seed_e2e_fixtures

Run after ``alembic upgrade head`` and ``python -m scripts.seed_demo``. Idempotent: re-running
resets the admin account to the state the specs expect (role ``admin``, a minimal profile so
sign-in lands on the app rather than onboarding).

Refuses to run unless the target is a throwaway local database (``throwaway_database_problems``):

* ``APP_ENV`` is not production;
* the database name contains ``e2e`` or ``test`` as a separate word;
* the host is loopback (``localhost``, ``127.0.0.1``, ``::1``) or a local Unix socket;
* no URL parameter or libpq environment variable can redirect the connection: the check is made on
  the effective parameters libpq would receive, not on the URL's apparent host and path.

There is deliberately no override: a remote database is refused whatever its name, so this script
can't plant a known admin password anywhere real. ``--check-only`` validates and exits (used by
``scripts/e2e.sh`` before it migrates anything).
"""
from __future__ import annotations

import os
import re
import sys
from collections.abc import Mapping
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from psycopg2.extensions import make_dsn, parse_dsn  # noqa: E402
from sqlalchemy import select  # noqa: E402
from sqlalchemy.dialects.postgresql.psycopg2 import PGDialect_psycopg2  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.models import Profile, User  # noqa: E402

ADMIN_EMAIL = "admin@example.org"
ADMIN_PASSWORD_ENV = "E2E_ADMIN_PASSWORD"
#: Matches the Playwright spec's fallback; only ever valid in a database this script accepts.
DEFAULT_ADMIN_PASSWORD = "AdminPass123!"
_THROWAWAY_NAME = re.compile(r"(^|[_-])(e2e|test)([_-]|$)")
_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
#: The project connects through SQLAlchemy's psycopg2 dialect; the guard reproduces exactly that path.
_DRIVERS = frozenset({"postgresql", "postgresql+psycopg2"})
_PSYCOPG2 = PGDialect_psycopg2()
#: URL query parameters that can't change the destination. Everything else is refused.
_ALLOWED_QUERY_KEYS = frozenset({"sslmode", "connect_timeout", "application_name"})
#: libpq parameters that pick the destination other than through host/dbname.
_REDIRECTING_PARAMS = frozenset({"hostaddr", "service", "servicefile"})
#: libpq environment variables that apply even when host and dbname are explicit.
_REDIRECTING_ENV = ("PGHOSTADDR", "PGSERVICE")


def throwaway_database_problems(
    database_url: str, *, production: bool = False, environ: Mapping[str, str] | None = None
) -> list[str]:
    """Why ``database_url`` is not an acceptable e2e target; empty when it is.

    Validates the *effective* destination: the connection parameters SQLAlchemy's psycopg2 dialect
    hands to libpq (URL query parameters are merged over the host and path, after percent-decoding),
    as libpq itself parses them. Query parameters are allow-listed, so nothing in the URL can
    override the host, host address, port, database or service; repeated parameters are refused.
    ``environ`` (default ``os.environ``) is checked for libpq variables that redirect a connection
    even when the host is explicit (``PGHOSTADDR``, ``PGSERVICE``).
    """
    environ = os.environ if environ is None else environ
    problems: list[str] = []
    if production:
        problems.append("APP_ENV is production")
    for name in _REDIRECTING_ENV:
        if environ.get(name):
            problems.append(f"{name} is set in the environment and could redirect the connection; unset it")
    try:
        url = make_url(database_url)
    except Exception:  # noqa: BLE001 - any unparsable URL is simply refused
        return problems + ["the database URL cannot be parsed"]
    if url.drivername not in _DRIVERS:
        return problems + ["the database must be PostgreSQL through psycopg2 (postgresql:// or postgresql+psycopg2://)"]

    for key, value in url.query.items():
        if isinstance(value, tuple):
            problems.append(f"the URL parameter {key!r} is repeated")
        elif key == "host" and not url.host and _is_socket_dir(value):
            continue  # postgresql://user@/db?host=/run/postgresql: a local socket directory
        elif key not in _ALLOWED_QUERY_KEYS:
            problems.append(
                f"the URL parameter {key!r} is not allowed (only {', '.join(sorted(_ALLOWED_QUERY_KEYS))}, "
                "or host=<socket directory> with no host in the URL)"
            )
    if problems:
        return problems

    try:
        _, connect_kwargs = _PSYCOPG2.create_connect_args(url)
        effective = parse_dsn(make_dsn(**connect_kwargs))  # libpq's own reading of the parameters
    except Exception:  # noqa: BLE001 - anything libpq can't parse is refused
        return problems + ["the connection parameters cannot be parsed"]

    redirecting = sorted(_REDIRECTING_PARAMS & effective.keys())
    if redirecting:
        problems.append(f"connection parameter(s) {', '.join(redirecting)} are not allowed")
    host = effective.get("host", "")
    if not host:
        problems.append("the database host must be explicit (loopback or a local socket directory)")
    elif not (host.strip("[]").lower() in _LOCAL_HOSTS or _is_socket_dir(host)):
        problems.append("the database host must be localhost, 127.0.0.1, ::1 or one local socket directory")
    if not effective.get("port", "5432").isdigit():
        problems.append("the database port must be a single number")
    if not _THROWAWAY_NAME.search(effective.get("dbname", "")):
        problems.append("the database name must contain 'e2e' or 'test' as a separate word")
    return problems


def _is_socket_dir(value: str) -> bool:
    return value.startswith("/") and "," not in value


def _refuse_unless_throwaway() -> None:
    problems = throwaway_database_problems(settings.DATABASE_URL, production=settings.is_production)
    if problems:
        raise SystemExit("Refusing e2e fixtures: " + "; ".join(problems) + ".")


def main() -> None:
    _refuse_unless_throwaway()
    if "--check-only" in sys.argv[1:]:
        print("E2E database target accepted: local throwaway database.")
        return
    password = os.environ.get(ADMIN_PASSWORD_ENV) or DEFAULT_ADMIN_PASSWORD
    with SessionLocal() as session:
        user = session.scalar(select(User).where(User.email == ADMIN_EMAIL))
        if user is None:
            user = User(email=ADMIN_EMAIL, password_hash=hash_password(password))
            session.add(user)
        else:
            user.password_hash = hash_password(password)
        user.is_active = True
        user.role = "admin"
        session.flush()
        if session.scalar(select(Profile).where(Profile.user_id == user.id)) is None:
            session.add(Profile(user_id=user.id, full_name="E2E Admin", email=ADMIN_EMAIL, degree_level="bachelor"))
        session.commit()
    print(f"E2E fixtures ready: {ADMIN_EMAIL} (role admin; password from ${ADMIN_PASSWORD_ENV} or the e2e default)")


if __name__ == "__main__":
    main()
