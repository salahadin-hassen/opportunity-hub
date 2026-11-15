"""Take unverified catalogue records out of public view, restore the genuine records they displaced,
and close published opportunities whose deadline has passed.

    REMEDIATION_DATABASE_URL=... python -m scripts.remediate_unverified_catalogue            # dry run
    REMEDIATION_DATABASE_URL=... python -m scripts.remediate_unverified_catalogue --commit   # apply

Data-only: needs no application secrets. The connection comes from REMEDIATION_DATABASE_URL (never a
command-line argument, so it stays out of shell history and process lists); only a masked identity of
the target is printed.

Why: 317 records from a bulk catalogue import were published with "page snapshots" that are one
synthetic template ("Title: ... Hosting Institution: ... Programme Summary: ..."), not fetched pages; a
live check of their URLs found 92 returning 404 and none of their 385 quoted statements on the real
pages. Separately, five of six rule-approved Erasmus Mundus programmes fail the evidence standard.

Changes (status only; nothing is deleted or edited; every change has an audit entry):
1. PUBLISHED records whose primary source snapshot is the synthetic template → ARCHIVED.
2. PUBLISHED Erasmus Mundus records whose stored evidence fails ``erasmus-mundus-evidence-v1`` → ARCHIVED.
3. The six genuine records the catalogue migration archived as "duplicates" (KNOWN_DISPLACED, by id) →
   PUBLISHED, only if their snapshot is genuine and they pass the publication checks, and only once
   (a record this script restored before is never restored again, so a later deliberate archive stands).
4. PUBLISHED records with a fixed deadline in the past → CLOSED (still public, shown as closed).

Repeatable: every rule selects by current state, so a second run finds nothing to do. Transactional:
all changes commit together or not at all. Before committing, the status of every opportunity is
written to a local JSON snapshot so statuses can be restored exactly.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session, selectinload

from app.intelligence.em_review import STANDARD, recheck_evidence
from app.models import AuditLog, Opportunity, Source
from app.models.enums import OpportunityStatus
from app.services import audit
from app.services.opportunities import publication_problems

TEMPLATE_SIGNS = ("Title: ", "Hosting Institution:")
#: The genuine baseline records the catalogue migration archived as "duplicates" of synthetic records
#: (DUPLICATE_BASELINE_IDS in that migration). Restoration is limited to these ids.
KNOWN_DISPLACED = {
    "89977454-caaa-519b-b7eb-6256b19398c5",  # KAUST Visiting Student Research Program (VSRP)
    "c1f5932b-d450-5e43-9879-a10d65ecb760",  # CERN Summer Student Programme
    "4c5ad172-ca5c-5dad-b37a-e67f49b91fee",  # Schwarzman Scholars
    "3deb873c-4727-59f2-86e3-2fb3abe08fb4",  # Gates Cambridge Scholarship
    "1724320f-fad5-55cd-b286-f19ad4ff4d88",  # ETH Student Summer Research Fellowship 2027
    "6379573e-845d-5d17-9efe-570e0640fa48",  # Summer@EPFL 2027
}
SYNTHETIC_REASON = ("unverified bulk import: page snapshot is a synthetic template, not a fetched official page; "
                    "quotes not found on live pages")


def database_url() -> str:
    url = os.environ.get("REMEDIATION_DATABASE_URL")
    if not url:
        raise SystemExit("Set REMEDIATION_DATABASE_URL to the target database (it is never printed).")
    return url.replace("postgres://", "postgresql://", 1)


def masked_identity(db: Session, url: str) -> str:
    parts = urlsplit(url)
    host = parts.hostname or ""
    head = host.split(".")[0]
    masked_host = (head[:6] + "…" + head[-4:] if len(head) > 12 else head) + host[len(head):]
    version = db.execute(text("SHOW server_version")).scalar()
    revision = db.execute(text("SELECT version_num FROM alembic_version")).scalar()
    database = db.execute(text("SELECT current_database()")).scalar()
    return f"host {masked_host} | database {database} | PostgreSQL {version} | schema {revision}"


def is_template(snapshot) -> bool:
    body = snapshot.get("text") if isinstance(snapshot, dict) else snapshot if isinstance(snapshot, str) else None
    return isinstance(body, str) and body.startswith(TEMPLATE_SIGNS[0]) and TEMPLATE_SIGNS[1] in body[:400]


def primary(opportunity: Opportunity) -> Source | None:
    return next((s for s in opportunity.sources if s.is_primary), opportunity.sources[0] if opportunity.sources else None)


def plan(db: Session, now: datetime) -> dict:
    opportunities = list(db.scalars(select(Opportunity).options(
        selectinload(Opportunity.sources), selectinload(Opportunity.requirements))))
    restored_before = set(db.scalars(select(AuditLog.target_id).where(AuditLog.action == "opportunity.restored_genuine")))

    synthetic, em_failing, em_meeting, restore, keep_archived, close = [], [], [], [], [], []
    for o in opportunities:
        src = primary(o)
        snapshot = src.raw_snapshot if src else None
        evidence = snapshot.get("evidence") if isinstance(snapshot, dict) else None
        if o.status == OpportunityStatus.PUBLISHED and src is not None and is_template(snapshot):
            synthetic.append(o)
        elif o.status == OpportunityStatus.PUBLISHED and isinstance(evidence, dict) and evidence.get("standard") == STANDARD:
            problems = recheck_evidence(evidence, snapshot.get("text") or "")
            (em_failing if problems else em_meeting).append((o, problems))
        elif o.status == OpportunityStatus.ARCHIVED and str(o.id) in KNOWN_DISPLACED:
            if str(o.id) in restored_before:
                keep_archived.append((o, ["restored once already; a later archive is respected"]))
            elif src is None or is_template(snapshot):
                keep_archived.append((o, ["no genuine source snapshot"]))
            elif problems := publication_problems(o):
                keep_archived.append((o, problems))
            else:
                restore.append(o)

    def expired(o: Opportunity) -> bool:
        return o.deadline_type == "fixed" and o.deadline_at is not None and o.deadline_at < now

    leaving = {o.id for o in synthetic} | {o.id for o, _ in em_failing}
    close = [o for o in opportunities if o.status == OpportunityStatus.PUBLISHED and o.id not in leaving and expired(o)]
    return {"opportunities": opportunities, "synthetic": synthetic, "em_failing": em_failing, "em_meeting": em_meeting,
            "restore": restore, "restore_closed": [o for o in restore if expired(o)], "keep_archived": keep_archived,
            "close": close}


def counts(db: Session) -> dict[str, int]:
    return dict(sorted(db.execute(select(Opportunity.status, func.count()).group_by(Opportunity.status)).all()))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--commit", action="store_true", help="apply (default: dry run, nothing written)")
    parser.add_argument("--snapshot-dir", type=Path, default=Path("."), help="where the pre-commit status snapshot goes")
    args = parser.parse_args()
    url = database_url()
    now = datetime.now(timezone.utc)
    engine = create_engine(url, pool_pre_ping=True)
    with Session(engine) as db:
        print("target:", masked_identity(db, url))
        print("mode:", "COMMIT" if args.commit else "dry run")
        print("before:", counts(db))
        p = plan(db, now)
        print(f"1. synthetic-template records to archive: {len(p['synthetic'])}")
        print(f"2. Erasmus Mundus ({STANDARD}): {len(p['em_meeting'])} meet the standard, {len(p['em_failing'])} to archive")
        for o, _ in p["em_meeting"]:
            print(f"     meets: {o.title}")
        for o, problems in p["em_failing"]:
            print(f"     fails: {o.title} — {'; '.join(problems)}")
        print(f"3. displaced genuine records to restore: {len(p['restore'])} "
              f"({len(p['restore_closed'])} of them as closed: deadline passed)")
        for o in p["restore"]:
            print(f"     restore: {o.title} (deadline {o.deadline_at.date() if o.deadline_at else o.deadline_type})")
        for o, why in p["keep_archived"]:
            print(f"     stays archived: {o.title} — {'; '.join(why)}")
        print(f"4. published records past their fixed deadline, to close: {len(p['close'])}")
        for o in p["close"]:
            print(f"     close: {o.title} (deadline {o.deadline_at.date()})")

        if args.commit:
            args.snapshot_dir.mkdir(parents=True, exist_ok=True)
            snapshot = args.snapshot_dir / f"opportunity_status_before_{now:%Y%m%dT%H%M%SZ}.json"
            snapshot.write_text(json.dumps({"taken_at": now.isoformat(),
                                            "statuses": {str(o.id): o.status for o in p["opportunities"]}}, indent=0))
            print("status snapshot written:", snapshot)

        def change(o: Opportunity, to: str, action: str, reason: str, extra: dict | None = None) -> None:
            before = o.status
            o.status = to
            audit.record(db, action=action, target_type="opportunity", target_id=o.id, actor_kind="system",
                         changes={"status": {"from": str(before), "to": to}, **(extra or {})}, reason=reason)

        for o in p["synthetic"]:
            change(o, OpportunityStatus.ARCHIVED, "opportunity.archived_unverified", SYNTHETIC_REASON)
        for o, problems in p["em_failing"]:
            change(o, OpportunityStatus.ARCHIVED, "opportunity.archived_below_standard",
                   f"{STANDARD} re-check: the stored evidence does not meet the standard", {"unmet": problems})
        for o in p["restore"]:
            to = OpportunityStatus.CLOSED if o in p["restore_closed"] else OpportunityStatus.PUBLISHED
            change(o, to, "opportunity.restored_genuine",
                   "genuine record restored after its unverified replacement was archived")
        for o in p["close"]:
            change(o, OpportunityStatus.CLOSED, "opportunity.closed_expired", "fixed application deadline has passed")
        db.flush()
        print("after:", counts(db))
        published = db.scalar(select(func.count()).select_from(Opportunity).where(Opportunity.status == OpportunityStatus.PUBLISHED))
        print("published after:", published)
        if args.commit:
            db.commit()
            print("COMMITTED")
        else:
            db.rollback()
            print("dry run: nothing changed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
