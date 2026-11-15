"""Take unverified catalogue records out of public view, and restore genuine records they displaced.

    DATABASE_URL=... python -m scripts.remediate_unverified_catalogue            # dry run: report only
    DATABASE_URL=... python -m scripts.remediate_unverified_catalogue --commit   # apply, in one transaction

Why: 317 records from a bulk catalogue import were published with "page snapshots" that are one
synthetic template ("Title: ... Hosting Institution: ... Programme Summary: ..."), not fetched pages. A
live check of their URLs found 92 returning 404, and none of their 385 quoted eligibility statements on
the real pages. They do not meet the publication standard, so they must not be public.

What it changes (status only; nothing is deleted; every change is audited and reversible):
1. every PUBLISHED opportunity whose primary source snapshot is that synthetic template → ARCHIVED;
2. opportunities that were ARCHIVED as "duplicates" of those records, whose own evidence is genuine
   (their source snapshot is not the template and their rules carry quotes) → PUBLISHED again, if they
   pass the normal publication checks.

What it never touches: Erasmus Mundus records approved under ``erasmus-mundus-evidence-v1`` (reported,
with their evidence checked), user accounts, roles, sessions, candidates, sources or requirements.
Reads the target from DATABASE_URL and prints only its host; never a credential.
"""
from __future__ import annotations

import argparse
import sys
from urllib.parse import urlsplit

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.models import Opportunity, Source
from app.models.enums import OpportunityStatus
from app.services import audit
from app.services.opportunities import publication_problems

TEMPLATE_SIGNS = ("Title: ", "Hosting Institution:")
#: The genuine baseline records the catalogue migration archived as "duplicates" of synthetic records
#: (scripts/migrate_catalogue_to_production.py, DUPLICATE_BASELINE_IDS).
KNOWN_DISPLACED = {
    "89977454-caaa-519b-b7eb-6256b19398c5", "c1f5932b-d450-5e43-9879-a10d65ecb760", "4c5ad172-ca5c-5dad-b37a-e67f49b91fee",
    "3deb873c-4727-59f2-86e3-2fb3abe08fb4", "1724320f-fad5-55cd-b286-f19ad4ff4d88", "6379573e-845d-5d17-9efe-570e0640fa48",
}
REASON = ("unverified bulk import: page snapshot is a synthetic template, not a fetched official page; "
          "quotes not found on live pages")


def is_template(snapshot) -> bool:
    text = snapshot.get("text") if isinstance(snapshot, dict) else snapshot if isinstance(snapshot, str) else None
    return isinstance(text, str) and text.startswith(TEMPLATE_SIGNS[0]) and TEMPLATE_SIGNS[1] in text[:400]


def primary(opportunity: Opportunity) -> Source | None:
    return next((s for s in opportunity.sources if s.is_primary), opportunity.sources[0] if opportunity.sources else None)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--commit", action="store_true")
    args = parser.parse_args()
    url = settings.DATABASE_URL
    print(f"target host: {urlsplit(url).hostname}  (mode: {'COMMIT' if args.commit else 'dry run'})")
    engine = create_engine(url, pool_pre_ping=True)
    with Session(engine) as db:
        opportunities = list(db.scalars(select(Opportunity).options(
            selectinload(Opportunity.sources), selectinload(Opportunity.requirements))))
        before = {s: n for s, n in db.execute(select(Opportunity.status, func.count()).group_by(Opportunity.status))}
        print("before:", dict(sorted(before.items())))

        synthetic = [o for o in opportunities if o.status == OpportunityStatus.PUBLISHED and primary(o) and is_template(primary(o).raw_snapshot)]
        synthetic_titles = {o.title.casefold() for o in synthetic}
        restorable = []
        for o in opportunities:
            src = primary(o)
            if o.status != OpportunityStatus.ARCHIVED or src is None or is_template(src.raw_snapshot):
                continue
            # only records displaced by a synthetic "replacement" of the same programme
            if str(o.id) not in KNOWN_DISPLACED and not any(
                    o.title.casefold() in t or t in o.title.casefold() for t in synthetic_titles):
                continue
            problems = publication_problems(o)
            restorable.append((o, problems))

        em = [o for o in opportunities if o.status == OpportunityStatus.PUBLISHED and primary(o)
              and isinstance(primary(o).raw_snapshot, dict) and (primary(o).raw_snapshot.get("evidence") or {}).get("standard") == "erasmus-mundus-evidence-v1"]
        print(f"published with a synthetic-template snapshot (to archive): {len(synthetic)}")
        print(f"archived genuine records displaced by them: {len(restorable)}")
        for o, problems in restorable:
            print(f"  {'restore' if not problems else 'KEEP ARCHIVED'}: {o.title} (deadline {o.deadline_at and o.deadline_at.date()})"
                  + (f"  ({'; '.join(problems)})" if problems else ""))
        print(f"Erasmus Mundus records under erasmus-mundus-evidence-v1: {len(em)}")
        for o in em:
            ev = primary(o).raw_snapshot["evidence"]
            ok = all([ev.get("scholarship_quote"), ev.get("deadline_quote") or ev.get("deadline_type") == "rolling", ev.get("eligibility_quotes")])
            text = primary(o).raw_snapshot.get("text") or ""
            on_page = all(q in text for q in [ev.get("scholarship_quote"), ev.get("deadline_quote")] + list(ev.get("eligibility_quotes") or []) if q)
            print(f"  {'OK ' if ok and on_page else 'BAD'} {o.title} | deadline {ev.get('deadline')} | checked {str(ev.get('checked_at'))[:10]} | quotes on stored page: {on_page}")

        from app.intelligence.em_review import recheck_evidence

        em_failing = []
        for o in em:
            snap = primary(o).raw_snapshot
            problems = recheck_evidence(snap["evidence"], snap.get("text") or "")
            print(f"  standard re-check: {'MEETS' if not problems else 'FAILS'} {o.title}" + (f" — {'; '.join(problems)}" if problems else ""))
            if problems:
                em_failing.append((o, problems))
        for o, problems in em_failing:
            o.status = OpportunityStatus.ARCHIVED
            audit.record(db, action="opportunity.archived_below_standard", target_type="opportunity", target_id=o.id,
                         actor_kind="system", changes={"status": {"from": "published", "to": "archived"},
                                                       "unmet": problems},
                         reason="erasmus-mundus-evidence-v1 re-check: the stored evidence does not meet the standard")
        for o in synthetic:
            o.status = OpportunityStatus.ARCHIVED
            audit.record(db, action="opportunity.archived_unverified", target_type="opportunity", target_id=o.id,
                         actor_kind="system", changes={"status": {"from": "published", "to": "archived"}}, reason=REASON)
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        for o, problems in restorable:
            if problems:
                continue
            # a fixed deadline that has passed is restored as closed (public, shown closed), never as open
            expired = o.deadline_type == "fixed" and o.deadline_at is not None and o.deadline_at < now
            o.status = OpportunityStatus.CLOSED if expired else OpportunityStatus.PUBLISHED
            audit.record(db, action="opportunity.restored_genuine", target_type="opportunity", target_id=o.id,
                         actor_kind="system", changes={"status": {"from": "archived", "to": str(o.status)}},
                         reason="genuine record restored after its unverified replacement was archived")
        db.flush()
        after = {s: n for s, n in db.execute(select(Opportunity.status, func.count()).group_by(Opportunity.status))}
        print("after:", dict(sorted(after.items())))
        if args.commit:
            db.commit()
            print("COMMITTED")
        else:
            db.rollback()
            print("dry run: nothing changed")


if __name__ == "__main__":
    sys.exit(main())
