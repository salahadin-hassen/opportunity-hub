"""Copy verified opportunities into the live production database, leaving everything else untouched.

    SOURCE_DATABASE_URL=... LIVE_DATABASE_URL=... python -m scripts.import_verified_opportunities            # dry run
    SOURCE_DATABASE_URL=... LIVE_DATABASE_URL=... python -m scripts.import_verified_opportunities --commit

The safer alternative to repointing the API at another database: users, sessions, profiles and every
existing record in LIVE stay exactly as they are; only qualifying opportunities are added.

What qualifies: a PUBLISHED opportunity in SOURCE whose primary source snapshot carries Erasmus Mundus
evidence that passes ``erasmus-mundus-evidence-v1`` today (``recheck_evidence``), whose quotes are all
on its stored page, and whose deadline is not past. Each is copied with its source records (the page
snapshot and the evidence) and its quoted requirements, keeping their ids. An opportunity whose id or
title already exists in LIVE is skipped (idempotent). Everything is inserted in one transaction, with an
audit entry per opportunity; the dry run (default) writes nothing. Connections come from the
environment and only masked hosts are printed. Data-only: no application secrets needed.
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from urllib.parse import urlsplit

from sqlalchemy import MetaData, Table, create_engine, func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.intelligence.em_review import STANDARD, recheck_evidence
from app.models import Opportunity
from app.services import audit


def _url(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise SystemExit(f"Set {name} (it is never printed).")
    return value.replace("postgres://", "postgresql://", 1)


def _host(url: str) -> str:
    host = urlsplit(url).hostname or ""
    head = host.split(".")[0]
    return (head[:6] + "…" + head[-4:] if len(head) > 12 else head) + host[len(head):]


def _rows(conn, table: str, column: str, ids: list) -> list[dict]:
    return [dict(r._mapping) for r in conn.execute(text(f"SELECT * FROM {table} WHERE {column} = ANY(:ids)"), {"ids": ids})]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--commit", action="store_true")
    args = parser.parse_args()
    source_url, live_url = _url("SOURCE_DATABASE_URL"), _url("LIVE_DATABASE_URL")
    now = datetime.now(timezone.utc)
    source = create_engine(source_url)
    live = create_engine(live_url, pool_pre_ping=True)
    print(f"source {_host(source_url)} → live {_host(live_url)}  (mode: {'COMMIT' if args.commit else 'dry run'})")

    with source.connect() as src:
        src.execute(text("SET TRANSACTION READ ONLY"))
        candidates = src.execute(text(
            "SELECT o.id, o.title, o.deadline_at, s.raw_snapshot FROM opportunities o "
            "JOIN sources s ON s.opportunity_id = o.id AND s.is_primary "
            "WHERE o.status = 'published' AND s.raw_snapshot ? 'evidence'")).all()
        qualifying = []
        for row in candidates:
            snapshot = row.raw_snapshot or {}
            evidence = snapshot.get("evidence") or {}
            problems = [] if evidence.get("standard") == STANDARD else ["not under the evidence standard"]
            problems += recheck_evidence(evidence, snapshot.get("text") or "")
            if row.deadline_at is not None and row.deadline_at < now:
                problems.append("deadline has passed")
            print(f"  {'QUALIFIES' if not problems else 'excluded '}: {row.title}" + (f" — {'; '.join(problems)}" if problems else ""))
            if not problems:
                qualifying.append(row.id)
        payload = {table: _rows(src, table, column, qualifying)
                   for table, column in (("opportunities", "id"), ("sources", "opportunity_id"), ("requirements", "opportunity_id"))}

    with Session(live) as db:
        existing_ids = {str(i) for i in db.scalars(select(Opportunity.id))}
        existing_titles = {t.casefold() for t in db.scalars(select(Opportunity.title))}
        before = db.scalar(select(func.count()).select_from(Opportunity).where(Opportunity.status == "published"))
        new = [o for o in payload["opportunities"]
               if str(o["id"]) not in existing_ids and o["title"].casefold() not in existing_titles]
        skipped = len(payload["opportunities"]) - len(new)
        new_ids = {o["id"] for o in new}
        print(f"live published before: {before}; to import: {len(new)}; already present (skipped): {skipped}")
        live_tables = MetaData()
        for table in ("opportunities", "sources", "requirements"):
            # Reflect LIVE's own columns so values are bound with LIVE's types (jsonb, arrays, enums), and
            # copy only the columns LIVE has; refuse if SOURCE has data in a column LIVE lacks.
            target = Table(table, live_tables, autoload_with=db.connection())
            rows = [r for r in payload[table] if (r["id"] if table == "opportunities" else r["opportunity_id"]) in new_ids]
            missing = {c for r in rows for c, v in r.items() if c not in target.c and v is not None}
            if missing:
                raise SystemExit(f"LIVE {table} lacks columns {sorted(missing)}: migrate LIVE first; nothing written")
            for row in rows:
                db.execute(pg_insert(target).values({c: v for c, v in row.items() if c in target.c})
                           .on_conflict_do_nothing(index_elements=["id"]))
        for o in new:
            audit.record(db, action="opportunity.imported_verified", target_type="opportunity", target_id=o["id"],
                         actor_kind="system", changes={"standard": STANDARD, "status": o["status"]},
                         reason=f"imported after passing the {STANDARD} re-check")
        db.flush()
        after = db.scalar(select(func.count()).select_from(Opportunity).where(Opportunity.status == "published"))
        print(f"live published after: {after}")
        if args.commit:
            db.commit()
            print("COMMITTED")
        else:
            db.rollback()
            print("dry run: nothing changed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
