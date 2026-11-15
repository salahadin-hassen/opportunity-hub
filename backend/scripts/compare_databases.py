"""Compare two Opportunity Hub databases' identity, users and catalogue, without revealing personal data.

    LIVE_DATABASE_URL=... TARGET_DATABASE_URL=... python -m scripts.compare_databases [--founder EMAIL]

Read-only (every statement runs in a read-only transaction). Prints, for each database: a masked
identity (host, database, PostgreSQL version, schema revision), user and role counts, Google
identities, sessions and per-user product data counts, and the opportunity status counts. Users are
compared by id only, as counts (in both / only in one); no email, name, password hash or token is
printed. With ``--founder``, reports that account's role in each database with the email masked.

Answers one question: would pointing the API at TARGET preserve every user and their data in LIVE?
"""
from __future__ import annotations

import argparse
import os
import sys
from urllib.parse import urlsplit

from sqlalchemy import create_engine, text


def mask_email(email: str) -> str:
    local, _, domain = email.partition("@")
    return f"{local[:1]}***@{domain}" if domain else "***"


def mask_host(url: str) -> str:
    host = urlsplit(url).hostname or ""
    head = host.split(".")[0]
    return (head[:6] + "…" + head[-4:] if len(head) > 12 else head) + host[len(head):]


def scalar(conn, sql: str, **params):
    try:
        return conn.execute(text(sql), params).scalar()
    except Exception:  # noqa: BLE001 - a table that doesn't exist yet (older schema) reads as absent
        conn.rollback()
        conn.execute(text("SET TRANSACTION READ ONLY"))
        return None


def describe(name: str, url: str, founder: str | None) -> dict:
    engine = create_engine(url.replace("postgres://", "postgresql://", 1), pool_pre_ping=True)
    with engine.connect() as conn:
        conn.execute(text("SET TRANSACTION READ ONLY"))
        info = {
            "identity": f"host {mask_host(url)} | database {scalar(conn, 'SELECT current_database()')} | "
                        f"PostgreSQL {scalar(conn, 'SHOW server_version')} | schema {scalar(conn, 'SELECT version_num FROM alembic_version')}",
            "users": scalar(conn, "SELECT count(*) FROM users"),
            "users_active": scalar(conn, "SELECT count(*) FROM users WHERE is_active"),
            "roles": dict(conn.execute(text("SELECT role, count(*) FROM users GROUP BY role")).all()),
            "google_identities": scalar(conn, "SELECT count(*) FROM external_identities"),
            "password_less_users": scalar(conn, "SELECT count(*) FROM users WHERE password_hash IS NULL"),
            "live_sessions": scalar(conn, "SELECT count(*) FROM sessions WHERE revoked_at IS NULL AND expires_at > now()"),
            "profiles": scalar(conn, "SELECT count(*) FROM profiles"),
            "saved_opportunities": scalar(conn, "SELECT count(*) FROM saved_opportunities"),
            "applications": scalar(conn, "SELECT count(*) FROM applications"),
            "opportunities": dict(conn.execute(text("SELECT status, count(*) FROM opportunities GROUP BY status")).all()),
            "user_ids": {str(r[0]) for r in conn.execute(text("SELECT id FROM users"))},
            "demo_role": scalar(conn, "SELECT role FROM users WHERE email = 'demo@example.org'"),
            "admins": [mask_email(e) for (e,) in conn.execute(text("SELECT email FROM users WHERE role = 'admin' ORDER BY email"))],
        }
        if founder:
            info["founder"] = scalar(conn, "SELECT role FROM users WHERE lower(email) = lower(:e)", e=founder)
    engine.dispose()
    print(f"== {name}: {info['identity']}")
    for key in ("users", "users_active", "roles", "google_identities", "password_less_users", "live_sessions", "profiles",
                "saved_opportunities", "applications", "opportunities", "demo_role", "admins"):
        print(f"   {key}: {info[key]}")
    if founder:
        print(f"   founder {mask_email(founder)}: {info['founder'] or 'NOT PRESENT'}")
    return info


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--founder", help="the founder's email (printed masked)")
    args = parser.parse_args()
    urls = {k: os.environ.get(k) for k in ("LIVE_DATABASE_URL", "TARGET_DATABASE_URL")}
    if not all(urls.values()):
        raise SystemExit("Set LIVE_DATABASE_URL (the database the API uses now) and TARGET_DATABASE_URL.")
    live = describe("LIVE (API now)", urls["LIVE_DATABASE_URL"], args.founder)
    target = describe("TARGET", urls["TARGET_DATABASE_URL"], args.founder)
    both = live["user_ids"] & target["user_ids"]
    only_live = live["user_ids"] - target["user_ids"]
    only_target = target["user_ids"] - live["user_ids"]
    print(f"== users by id: in both {len(both)} | only in LIVE {len(only_live)} | only in TARGET {len(only_target)}")
    differences = [k for k in ("profiles", "saved_opportunities", "applications", "google_identities")
                   if live[k] is not None and target[k] is not None and target[k] < live[k]]
    preserved = not only_live and not differences
    print("== switching the API to TARGET would", "PRESERVE every LIVE user and their data"
          if preserved else f"LOSE data: {len(only_live)} users only in LIVE; fewer rows in TARGET for {differences or 'none'}")
    return 0 if preserved else 2


if __name__ == "__main__":
    sys.exit(main())
