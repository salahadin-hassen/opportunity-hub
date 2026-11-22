"""``python -m app.cli ingest-*``: operator commands for the ingestion pipeline.

Sources::

    ingest-source-load FILE.json          propose sources from a JSON list of SourceDefinition objects
    ingest-source-test NAME [--sample N]  dry-run discovery, then fetch the pages it leads to (every URL of a
                                          url_list source, N leads otherwise); records the result on the source
    ingest-source-health [--json] [--failed]   what is actually known about each source, from recorded evidence
    ingest-source-terms NAME acceptable|restricted --actor EMAIL [--notes ...]
    ingest-source-status NAME testing|approved|paused|retired --actor EMAIL [--reason ...]
    ingest-sources                        list sources with status and health

Pipeline::

    ingest-discover [--source NAME] [--dry-run]   approved sources (or the named testing source)
    ingest-process [--limit N] [--source NAME]    fetch → extract → validate → de-duplicate the due candidates
    ingest-preview --source NAME URL              fetch and extract one page; print it; store nothing
    ingest-expire [--close-published --yes]       expire past-deadline candidates; optionally close published
                                                  opportunities whose deadline has passed (dry run by default)

Refresh of published opportunities (never edits an opportunity; findings wait for a curator)::

    ingest-refresh [--limit N] [--opportunity ID] [--min-interval-hours H]
    ingest-refresh-checks [--state pending|acknowledged|dismissed|none] [--outcome O] [--limit N]
    ingest-refresh-show ID
    ingest-refresh-resolve ID acknowledge|dismiss --actor EMAIL [--notes ...]

Review and inspection::

    ingest-candidates [--state S] [--limit N]
    ingest-show ID
    ingest-review ID approve|reject|request_changes --actor EMAIL [--notes ...] [--title ...] [--type ...]
                  [--deadline YYYY-MM-DD] [--deadline-type fixed|rolling|none] [--statements 0,2] [--force]
    ingest-requeue ID | --state failed|retry|changes_requested
    ingest-runs [--limit N]
    ingest-stats

Approval creates a *draft* opportunity only. Publishing stays a separate, checked curator action
(``POST /curate/opportunities/{id}/publish`` or the curator UI's "Check & publish").
"""
from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.enums import OpportunityStatus, SourceStatus, TermsStatus


class IngestCliError(Exception):
    """Safe-to-print failure."""


def add_commands(commands: argparse._SubParsersAction) -> None:
    load = commands.add_parser("ingest-source-load", help="propose acquisition sources from a JSON file")
    load.add_argument("file", type=Path)
    test = commands.add_parser("ingest-source-test", help="discover, fetch the leads, and record the test run")
    test.add_argument("--sample", type=int, default=5, help="leads to fetch for a crawling connector")
    test.add_argument("name")
    terms = commands.add_parser("ingest-source-terms", help="record a terms-of-use review")
    terms.add_argument("name")
    terms.add_argument("status", choices=["acceptable", "restricted"])
    terms.add_argument("--actor", required=True)
    terms.add_argument("--notes")
    status = commands.add_parser("ingest-source-status", help="move a source through its lifecycle")
    status.add_argument("name")
    status.add_argument("status", choices=[item.value for item in SourceStatus])
    status.add_argument("--actor", required=True)
    status.add_argument("--reason")
    commands.add_parser("ingest-sources", help="list acquisition sources")
    sync = commands.add_parser("ingest-starter-sync", help="create or update sources from the shipped starter list")
    sync.add_argument("--actor", required=True)
    automation = commands.add_parser("ingest-source-automation", help="set a source's automation level (raised one step at a time)")
    automation.add_argument("name")
    automation.add_argument("mode", choices=["off", "shadow", "listing_only", "full"])
    automation.add_argument("--actor", required=True)
    automation.add_argument("--reason", required=True)
    autopilot = commands.add_parser("ingest-autopilot", help="run discovery, processing and automatic review in a loop")
    autopilot.add_argument("--hours", type=float, default=1.0, help="stop after this long")
    autopilot.add_argument("--batch", type=int, default=50, help="candidates processed and decided per round")
    autopilot.add_argument("--pause-minutes", type=float, default=10.0, help="wait between rounds that found nothing to do")
    em = commands.add_parser("ingest-em-review",
                             help="apply the Erasmus Mundus evidence standard (rule-based review with spot-checks)")
    em.add_argument("sources", type=Path, help="the Erasmus Mundus source definitions JSON (with catalogue titles)")
    em.add_argument("--actor", required=True, help="the admin or curator account the approvals are recorded under")
    em.add_argument("--apply", action="store_true", help="approve and publish what meets the standard (default: report only)")
    em.add_argument("--report", type=Path, help="write every programme's decision and evidence as JSON")
    health = commands.add_parser("ingest-source-health", help="source counts by what recorded evidence proves")
    health.add_argument("--json", action="store_true")
    health.add_argument("--failed", action="store_true", help="list failed sources with the reason")
    refresh = commands.add_parser("ingest-refresh", help="re-read published opportunities' official pages")
    refresh.add_argument("--limit", type=int, default=20)
    refresh.add_argument("--opportunity", type=uuid.UUID)
    refresh.add_argument("--min-interval-hours", type=float, default=24.0)
    checks = commands.add_parser("ingest-refresh-checks", help="list refresh checks")
    checks.add_argument("--state", choices=["pending", "acknowledged", "dismissed", "none"], default="pending")
    checks.add_argument("--outcome")
    checks.add_argument("--limit", type=int, default=50)
    check_show = commands.add_parser("ingest-refresh-show", help="show one refresh check")
    check_show.add_argument("id", type=uuid.UUID)
    resolve = commands.add_parser("ingest-refresh-resolve", help="acknowledge or dismiss a refresh finding")
    resolve.add_argument("id", type=uuid.UUID)
    resolve.add_argument("decision", choices=["acknowledge", "dismiss"])
    resolve.add_argument("--actor", required=True)
    resolve.add_argument("--notes")

    discover = commands.add_parser("ingest-discover", help="discover candidate pages on approved sources")
    discover.add_argument("--source")
    discover.add_argument("--dry-run", action="store_true")
    process = commands.add_parser("ingest-process", help="fetch, extract and validate due candidates")
    process.add_argument("--limit", type=int, default=20)
    process.add_argument("--source")
    preview = commands.add_parser("ingest-preview", help="fetch and extract one page without storing anything")
    preview.add_argument("--source", required=True)
    preview.add_argument("url")
    expire = commands.add_parser("ingest-expire", help="expire past-deadline candidates (and optionally published opportunities)")
    expire.add_argument("--close-published", action="store_true")
    expire.add_argument("--yes", action="store_true")

    listing = commands.add_parser("ingest-candidates", help="list candidates")
    listing.add_argument("--state")
    listing.add_argument("--limit", type=int, default=50)
    show = commands.add_parser("ingest-show", help="show one candidate's extraction and validation")
    show.add_argument("id", type=uuid.UUID)
    review = commands.add_parser("ingest-review", help="approve, reject or request changes")
    review.add_argument("id", type=uuid.UUID)
    review.add_argument("decision", choices=["approve", "reject", "request_changes"])
    review.add_argument("--actor", required=True)
    review.add_argument("--notes")
    review.add_argument("--title")
    review.add_argument("--type", dest="opportunity_type")
    review.add_argument("--deadline", type=date.fromisoformat)
    review.add_argument("--deadline-type", choices=["fixed", "rolling", "none"])
    review.add_argument("--statements", help="comma-separated indexes of eligibility statements to keep")
    review.add_argument("--countries", help="comma-separated ISO country codes")
    review.add_argument("--force", action="store_true", help="approve an expired or duplicate candidate")
    requeue = commands.add_parser("ingest-requeue", help="re-queue candidates for a fresh fetch")
    requeue.add_argument("id", type=uuid.UUID, nargs="?")
    requeue.add_argument("--state", choices=["failed", "retry", "changes_requested"])
    runs = commands.add_parser("ingest-runs", help="recent discovery and processing runs")
    runs.add_argument("--limit", type=int, default=20)
    commands.add_parser("ingest-stats", help="candidate counts by state, and opportunity counts")


def _autopilot(db: Session, *, hours: float, batch: int, pause_minutes: float) -> int:
    """Rounds of the site's "Run" job until time is up. A round that decided nothing new waits before the next."""
    import time as _time

    from app.api.routers.ingestion_jobs import _pipeline_work

    stop = _time.monotonic() + hours * 3600
    rounds = 0
    while _time.monotonic() < stop:
        rounds += 1
        summary = _pipeline_work(None, batch)(db)
        auto = summary["automatic"]
        print(f"[{datetime.now(timezone.utc):%Y-%m-%d %H:%M}] round {rounds}: new leads {summary['new_leads']}, processed {summary['processed']}, "
              f"published {auto['published']}, drafted {auto['drafted']}, shadow {auto['shadow']}, held {auto['held']}, "
              f"already decided {auto['skipped']}, closed {summary['closed_opportunities']}", flush=True)
        busy = summary["processed"] or auto["published"] or auto["drafted"] or auto["shadow"] or auto["held"]
        if not busy:
            _time.sleep(max(0.0, min(pause_minutes * 60, stop - _time.monotonic())))
    return 0


def _source(db: Session, name: str):
    from app.models import AcquisitionSource

    source = db.scalar(select(AcquisitionSource).where(AcquisitionSource.name == name))
    if source is None:
        raise IngestCliError(f"No source named {name!r}.")
    return source


def _actor(db: Session, email: str, permission):
    """The acting account, which must hold the permission the API requires for the same action."""
    from app.cli import CliError, find_user
    from app.core.permissions import has_permission

    try:
        user = find_user(db, email)
    except CliError as error:
        raise IngestCliError(str(error)) from None
    if not user.is_active or not has_permission(user.role, permission):
        raise IngestCliError(f"That account is not allowed to do this (needs {permission.value}).")
    return user


def _print_json(value) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False, default=str))


def run(db: Session, args: argparse.Namespace) -> int:
    from app.core.permissions import Permission
    from app.intelligence import pipeline, registry
    from app.intelligence.definitions import SourceDefinition
    from app.intelligence.extract import DeterministicExtractor
    from app.models import AcquisitionSource, IngestionCandidate, IngestionRun, Opportunity
    from app.models.ingestion import CandidateState

    command = args.command
    try:
        if command == "ingest-em-review":
            from dataclasses import asdict

            from app.intelligence import em_review

            actor = _actor(db, args.actor, Permission.OPPORTUNITY_PUBLISH if args.apply else Permission.SOURCE_READ)
            payload = json.loads(args.sources.read_text())
            today = datetime.now(timezone.utc).date()
            decisions = em_review.run_review(db, payload, actor_id=actor.id, today=today, apply=args.apply)
            if args.apply:
                db.commit()
            else:
                db.rollback()
            counts: dict[str, int] = {}
            reasons: dict[str, int] = {}
            for d in decisions:
                counts[d.decision] = counts.get(d.decision, 0) + 1
                for r in d.reasons[:1]:
                    key = r.split(":")[0][:70]
                    reasons[key] = reasons.get(key, 0) + 1
            print(f"{em_review.STANDARD} ({em_review.REVIEW_BASIS}); {'APPLIED' if args.apply else 'report only'}")
            print(f"programmes: {len(decisions)}; by decision: {counts}")
            for r, n in sorted(reasons.items(), key=lambda kv: -kv[1]):
                print(f"  first unmet reason: {n:4d}  {r}")
            if args.report:
                args.report.write_text(json.dumps({"standard": em_review.STANDARD, "review_basis": em_review.REVIEW_BASIS,
                                                   "evaluated_on": today.isoformat(), "applied": args.apply,
                                                   "decisions": [asdict(d) for d in decisions]}, indent=1, ensure_ascii=False))
        elif command == "ingest-source-load":
            definitions = json.loads(args.file.read_text())
            created = 0
            for raw in definitions:
                definition = SourceDefinition.model_validate(raw)
                if db.scalar(select(AcquisitionSource.id).where(AcquisitionSource.name == definition.name)):
                    print(f"exists, skipped: {definition.name}")
                    continue
                registry.create_source(db, definition)
                created += 1
                print(f"proposed: {definition.name}")
            db.commit()
            print(f"{created} source(s) proposed.")
        elif command == "ingest-source-test":
            from app.intelligence.source_test import run_source_test

            source = _source(db, args.name)
            if source.status == SourceStatus.PROPOSED:
                registry.change_status(db, source, SourceStatus.TESTING)
                db.commit()
            report = run_source_test(db, source, sample=getattr(args, "sample", 5))
            db.commit()
            print(f"robots.txt: {report.robots_status}; leads: {report.leads}; index pages read: {report.pages_read}; "
                  f"pages fetched: {report.fetched_ok} ok, {report.fetched_failed} failed")
            for check in report.checks[:50]:
                status_code = f" HTTP {check.status_code}" if check.status_code else ""
                if check.ok:
                    print(f"  ok{status_code} {check.url} ({check.text_chars} characters of text)")
                else:
                    print(f"  FAILED {check.result}{status_code} {check.url}: {check.detail}")
            for item in report.rejected[:10]:
                print(f"  rejected {item['url']}: {item['reason']}")
            for warning in report.warnings:
                print(f"  warning: {warning}")
            for problem in report.problems:
                print(f"  problem: {problem}")
            print("test run PASSED" if report.passed else "test run FAILED")
            return 0 if report.passed else 2
        elif command == "ingest-source-terms":
            source = _source(db, args.name)
            actor = _actor(db, args.actor, Permission.SOURCE_REVIEW)
            registry.record_terms_review(db, source, status=TermsStatus(args.status), reviewer_id=actor.id, notes=args.notes)
            db.commit()
            print(f"{source.name}: terms {source.terms_status}")
        elif command == "ingest-source-status":
            source = _source(db, args.name)
            from app.api.routers.curate import STATUS_PERMISSIONS

            actor = _actor(db, args.actor, STATUS_PERMISSIONS[SourceStatus(args.status)])
            registry.change_status(db, source, SourceStatus(args.status), actor_id=actor.id, reason=args.reason)
            db.commit()
            print(f"{source.name}: {source.status}")
        elif command == "ingest-starter-sync":
            from app.api.routers.ingestion_jobs import sync_starter_sources

            actor = _actor(db, args.actor, Permission.SOURCE_APPROVE)
            created, updated, skipped = sync_starter_sources(db, actor_id=actor.id)
            db.commit()
            print(f"created {len(created)}, updated {len(updated)} (back to testing), unchanged {len(skipped)}")
            for name in updated:
                print(f"  updated: {name}")
        elif command == "ingest-source-automation":
            from app.intelligence.lifecycle import PUBLISH_ORDER
            from app.models.enums import PublishMode

            source = _source(db, args.name)
            actor = _actor(db, args.actor, Permission.SOURCE_PUBLISH_RAISE)
            target = PublishMode(args.mode)
            order = list(PUBLISH_ORDER)
            while order.index(PublishMode(source.publish_mode)) < order.index(target):
                registry.set_publish_mode(db, source, order[order.index(PublishMode(source.publish_mode)) + 1], actor_id=actor.id, reason=args.reason)
            if order.index(PublishMode(source.publish_mode)) > order.index(target):
                registry.set_publish_mode(db, source, target, actor_id=actor.id, reason=args.reason)
            db.commit()
            print(f"{source.name}: automation {source.publish_mode}")
        elif command == "ingest-autopilot":
            return _autopilot(db, hours=args.hours, batch=args.batch, pause_minutes=args.pause_minutes)
        elif command == "ingest-sources":
            for source in db.scalars(select(AcquisitionSource).order_by(AcquisitionSource.name)):
                print(f"{source.name}\t{source.status}\t{source.connector_key}\trobots={source.robots_status}\t"
                      f"terms={source.terms_status}\tfailures={source.consecutive_failures}\tlast_ok={source.last_success_at}")
        elif command == "ingest-source-health":
            from app.intelligence.health import source_health

            report = source_health(db)
            if args.json:
                _print_json(report.as_dict())
            else:
                print(f"registered                      {report.registered}")
                print(f"tested (a source test ran)      {report.tested}")
                print(f"  test passed                   {report.test_passed}")
                print(f"never tested                    {report.never_tested}")
                print(f"fetchable (proved by a fetch)   {report.fetchable}")
                print(f"parsed (opportunity page read)  {report.parsed}")
                print(f"producing valid candidates      {report.producing}")
                print(f"failed                          {report.failed}")
                print(f"candidates awaiting review      {report.needs_review} source(s)")
                print(f"furthest stage: {report.by_stage}")
                print(f"status: {report.by_status}; connector: {report.by_connector}")
                if report.untraceable_candidates:
                    print(f"ignored: {report.untraceable_candidates} candidate(s) with no discovery run (not fetched by the pipeline)")
                if args.failed:
                    for item in report.sources:
                        if item.failed:
                            print(f"  FAILED {item.name}: {item.problem}")
        elif command == "ingest-refresh":
            from datetime import timedelta

            from app.intelligence import refresh

            report = refresh.refresh_opportunities(
                db, limit=args.limit, opportunity_id=args.opportunity,
                min_interval=timedelta(hours=args.min_interval_hours),
            )
            if report.busy:
                print("Another refresh run is in progress; nothing checked.")
                return 2
            for result in report.results:
                flag = " [REVIEW]" if result.review_state == "pending" else ""
                print(f"{result.outcome}{flag}\t{result.title}\t{result.summary}\t{result.check_id}")
            for skipped in report.skipped:
                print(f"skipped\t{skipped.title}\t{skipped.reason}")
            for error in report.errors:
                print(f"error\t{error}")
            print(f"checked={report.checked} by_outcome={report.by_outcome} pending_review={report.pending_review} "
                  f"skipped={len(report.skipped)} errors={len(report.errors)}")
        elif command == "ingest-refresh-checks":
            from app.models import OpportunityRefreshCheck

            statement = (
                select(OpportunityRefreshCheck, Opportunity.title)
                .join(Opportunity, Opportunity.id == OpportunityRefreshCheck.opportunity_id)
                .where(OpportunityRefreshCheck.review_state == args.state)
                .order_by(OpportunityRefreshCheck.checked_at.desc()).limit(args.limit)
            )
            if args.outcome:
                statement = statement.where(OpportunityRefreshCheck.outcome == args.outcome)
            for check, title in db.execute(statement).all():
                print(f"{check.id}\t{check.checked_at:%Y-%m-%d %H:%M}\t{check.outcome}\t{check.review_state}\t{title}")
        elif command == "ingest-refresh-show":
            from app.models import OpportunityRefreshCheck

            check = db.get(OpportunityRefreshCheck, args.id)
            if check is None:
                raise IngestCliError("Refresh check not found.")
            _print_json({
                "opportunity_id": check.opportunity_id, "url": check.url, "checked_at": check.checked_at,
                "outcome": check.outcome, "review_state": check.review_state, "http_status": check.http_status,
                "content_changed": check.content_changed, "content_hash": check.content_hash, "etag": check.etag,
                "last_modified": check.last_modified, "findings": check.findings, "error": check.error,
                "consecutive_failures": check.consecutive_failures, "candidate_id": check.candidate_id,
                "review_notes": check.review_notes,
            })
        elif command == "ingest-refresh-resolve":
            from app.intelligence import refresh

            actor = _actor(db, args.actor, Permission.OPPORTUNITY_EDIT)
            try:
                check = refresh.resolve_check(db, args.id, actor_id=actor.id, decision=args.decision, notes=args.notes)
            except refresh.RefreshError as error:
                raise IngestCliError(str(error)) from None
            db.commit()
            print(f"Refresh check {check.id}: {check.review_state}")
        elif command == "ingest-discover":
            if args.source:
                sources = [_source(db, args.source)]
            else:
                sources = list(db.scalars(select(AcquisitionSource).where(AcquisitionSource.status == SourceStatus.APPROVED)))
            if not sources:
                print("No approved sources.")
            for source in sources:
                report = pipeline.run_discovery(db, source, dry_run=args.dry_run)
                label = "DRY RUN " if args.dry_run else ""
                print(f"{label}{source.name}: leads={len(report.accepted)} new={report.new} seen_again={report.seen_again} "
                      f"rejected={len(report.rejected)} pages={report.pages_read} error={report.error}")
                if args.dry_run:
                    for url in report.accepted[:50]:
                        print(f"  {url}")
        elif command == "ingest-process":
            source_id = _source(db, args.source).id if args.source else None
            report = pipeline.process_candidates(db, limit=args.limit, source_id=source_id)
            print(f"processed={report.processed} by_state={report.by_state} errors={len(report.errors)}")
        elif command == "ingest-preview":
            from app.intelligence.discovery import check_in_scope

            source = _source(db, args.source)
            url = check_in_scope(args.url, registry.allowed_hosts(source))
            page = pipeline.default_reader(source).read(url)
            text, extraction, validation = pipeline.analyse_page(source, page, DeterministicExtractor(), date.today())
            _print_json({"url": url, "final_url": page.final_url, "text_chars": len(text),
                         "extraction": extraction.model_dump(mode="json"), "validation": validation.as_dict(),
                         "quality_score": validation.quality_score})
            db.rollback()
        elif command == "ingest-expire":
            today = datetime.now(timezone.utc).date()
            expired = pipeline.expire_candidates(db, today=today)
            db.commit()
            print(f"{expired} candidate(s) moved to expired.")
            past = list(db.scalars(select(Opportunity).where(
                Opportunity.status == OpportunityStatus.PUBLISHED,
                Opportunity.deadline_at.is_not(None),
                Opportunity.deadline_at < datetime.now(timezone.utc),
            )))
            for opportunity in past:
                print(f"  past deadline, still published: {opportunity.title} ({opportunity.deadline_at:%Y-%m-%d})")
            if args.close_published:
                if not args.yes:
                    raise IngestCliError("Refusing without --yes: this closes published opportunities.")
                from app.services import audit
                from app.services.opportunities import close_opportunity

                for opportunity in past:
                    close_opportunity(db, opportunity.id)
                    audit.record(db, action="opportunity.closed", target_type="opportunity", target_id=opportunity.id,
                                 actor_kind="system", changes={"reason": "deadline passed"})
                db.commit()
                print(f"Closed {len(past)} opportunity(ies) whose deadline has passed.")
            elif past:
                print("Dry run: re-run with --close-published --yes to close them.")
        elif command == "ingest-candidates":
            statement = select(IngestionCandidate).order_by(IngestionCandidate.quality_score.desc().nulls_last()).limit(args.limit)
            if args.state:
                statement = statement.where(IngestionCandidate.state == CandidateState(args.state))
            for candidate in db.scalars(statement):
                title = ((candidate.extraction or {}).get("title") or {}).get("value")
                deadline = ((candidate.extraction or {}).get("deadline") or {}).get("value")
                print(f"{candidate.id}\t{candidate.state}\tq={candidate.quality_score}\t{deadline}\t{title or '-'}\t{candidate.url}")
        elif command == "ingest-show":
            candidate = db.get(IngestionCandidate, args.id)
            if candidate is None:
                raise IngestCliError("Candidate not found.")
            _print_json({
                "id": candidate.id, "state": candidate.state, "url": candidate.url, "final_url": candidate.final_url,
                "fetched_at": candidate.fetched_at, "content_hash": candidate.content_hash,
                "quality_score": candidate.quality_score, "attempts": candidate.attempts, "last_error": candidate.last_error,
                "duplicate_of_candidate_id": candidate.duplicate_of_candidate_id,
                "duplicate_of_opportunity_id": candidate.duplicate_of_opportunity_id,
                "opportunity_id": candidate.opportunity_id, "review_notes": candidate.review_notes,
                "validation": candidate.validation, "extraction": candidate.extraction,
            })
        elif command == "ingest-review":
            actor = _actor(db, args.actor, Permission.OPPORTUNITY_CREATE)
            if args.decision == "approve":
                statements = [int(item) for item in args.statements.split(",")] if args.statements else None
                countries = [c.strip().upper() for c in args.countries.split(",") if c.strip()] if args.countries else None
                opportunity = pipeline.approve_candidate(db, args.id, actor_id=actor.id, decision=pipeline.ApprovalInput(
                    title=args.title, opportunity_type=args.opportunity_type, deadline=args.deadline,
                    deadline_type=args.deadline_type, statements=statements, countries=countries, notes=args.notes, force=args.force,
                ))
                db.commit()
                print(f"Approved: draft opportunity {opportunity.id} ({opportunity.slug}). Publish it from the curator workspace.")
            else:
                pipeline.decide_candidate(db, args.id, actor_id=actor.id, decision=args.decision, notes=args.notes)
                db.commit()
                print(f"Candidate {args.id}: {args.decision}")
        elif command == "ingest-requeue":
            if args.id is None and args.state is None:
                raise IngestCliError("Give a candidate id or --state.")
            ids = [args.id] if args.id else list(db.scalars(select(IngestionCandidate.id).where(IngestionCandidate.state == args.state)))
            for candidate_id in ids:
                pipeline.requeue_candidate(db, candidate_id, actor_id=None)
            db.commit()
            print(f"Re-queued {len(ids)} candidate(s).")
        elif command == "ingest-runs":
            for run_row in db.scalars(select(IngestionRun).order_by(IngestionRun.started_at.desc()).limit(args.limit)):
                print(f"{run_row.started_at:%Y-%m-%d %H:%M}\t{run_row.kind}\t{run_row.status}\tdry={run_row.dry_run}\t"
                      f"{json.dumps(run_row.stats)}\t{run_row.error or ''}")
        elif command == "ingest-stats":
            _print_json({
                "candidates_by_state": pipeline.stats(db),
                "opportunities_by_status": dict(db.execute(
                    select(Opportunity.status, func.count()).group_by(Opportunity.status)).all()),
            })
        else:
            return -1
    except (IngestCliError, pipeline.PipelineError, ValidationError, ValueError) as error:
        db.rollback()
        print(f"error: {error}", file=sys.stderr)
        return 1
    except registry.SourceRegistryError as error:
        db.rollback()
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0
