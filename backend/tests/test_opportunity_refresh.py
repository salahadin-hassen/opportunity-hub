"""Refreshing published opportunities: real database, real fetcher and reader, deterministic server.

Every test publishes an opportunity the way the product does (source test → approval → discovery →
processing → curator approval → publication), changes what the official page serves, runs a refresh,
and checks two things: the outcome, and that the opportunity itself was not touched."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from sqlalchemy import func, select

from app.intelligence import pipeline, refresh, registry
from app.intelligence.source_test import run_source_test
from app.models import (
    AuditLog,
    IngestionCandidate,
    IngestionRun,
    Opportunity,
    OpportunityRefreshCheck,
    Requirement,
    Source,
    User,
)
from app.models.enums import OpportunityStatus, SourceStatus, TermsStatus
from app.models.ingestion import CandidateState
from app.services.opportunities import close_opportunity, publish_opportunity
from tests.fake_web import FakeWeb
from tests.test_ingestion_pipeline import NOW, as_, client, make_source, opportunity_page, site  # noqa: F401 (fixture)

V1, V2, V3 = '"v1"', '"v2"', '"v3"'
NO_WAIT = timedelta(0)
NEWS = "<html><body><h1>Campus news</h1><p>" + "The cafeteria has a new menu this week. " * 12 + "</p></body></html>"


@pytest.fixture
def curator(db_session) -> User:
    user = User(email=f"curator-{uuid.uuid4().hex[:8]}@example.org", password_hash="x", role="admin")
    db_session.add(user)
    db_session.flush()
    return user


class Published:
    """One published opportunity with its page, source and an untouched copy of what was approved."""

    def __init__(
        self, db, web: FakeWeb, curator: User, *, deadline: str = "15 January 2027", publish: bool = True,
        title: str = "Summer Research Scholarship 2027",
    ) -> None:
        self.db, self.web = db, web
        self.url = f"{site()}/scholarship"
        web.page(self.url, opportunity_page(title=title, deadline=deadline), etag=V1)
        self.source = make_source(db, [self.url])
        registry.record_terms_review(db, self.source, status=TermsStatus.ACCEPTABLE, reviewer_id=curator.id, notes="ok")
        assert run_source_test(db, self.source, reader=web.reader(self.source)).passed
        registry.change_status(db, self.source, SourceStatus.APPROVED, actor_id=curator.id)
        pipeline.run_discovery(db, self.source, reader=web.reader(self.source), now=NOW)
        pipeline.process_candidates(db, reader_factory=web.reader, now=NOW, source_id=self.source.id)
        candidate = db.scalar(select(IngestionCandidate).where(IngestionCandidate.url == self.url))
        self.opportunity = pipeline.approve_candidate(
            db, candidate.id, actor_id=curator.id, decision=pipeline.ApprovalInput(notes="checked against the page"))
        if publish:
            publish_opportunity(db, self.opportunity.id)
        self.id = self.opportunity.id
        self.approved = self.frozen()
        web.requests.clear()

    def frozen(self) -> dict:
        """Everything a curator approved, as stored now."""
        opportunity = self.db.scalar(select(Opportunity).where(Opportunity.id == self.id).execution_options(populate_existing=True))
        primary = self.db.scalar(select(Source).where(Source.opportunity_id == self.id, Source.is_primary).execution_options(populate_existing=True))
        requirements = self.db.execute(
            select(Requirement.label, Requirement.source_quote, Requirement.kind, Requirement.is_mandatory)
            .where(Requirement.opportunity_id == self.id).order_by(Requirement.order_index)
        ).all()
        return {
            "title": opportunity.title, "status": opportunity.status, "deadline_at": opportunity.deadline_at,
            "deadline_type": opportunity.deadline_type, "description": opportunity.description,
            "official_url": opportunity.official_url, "updated_at": opportunity.updated_at,
            "snapshot": primary.raw_snapshot, "snapshot_hash": primary.content_hash, "retrieved_at": primary.retrieved_at,
            "requirements": [tuple(row) for row in requirements],
        }

    def serve(self, body: bytes | str, *, etag: str | None = None, **kwargs) -> None:
        self.web.page(self.url, body, etag=etag, **kwargs)

    def refresh(self, now: datetime) -> refresh.RefreshResult:
        report = refresh.refresh_opportunities(
            self.db, reader_factory=self.web.reader, now=now, opportunity_id=self.id, min_interval=NO_WAIT)
        assert report.errors == [] and report.skipped == [] and not report.busy
        [result] = report.results
        # The rule every refresh must keep: the approved opportunity is exactly as it was.
        assert self.frozen() == self.approved
        return result

    def check(self, result: refresh.RefreshResult) -> OpportunityRefreshCheck:
        return self.db.get(OpportunityRefreshCheck, result.check_id)

    def checks(self) -> list[OpportunityRefreshCheck]:
        return list(self.db.scalars(
            select(OpportunityRefreshCheck).where(OpportunityRefreshCheck.opportunity_id == self.id)
            .order_by(OpportunityRefreshCheck.checked_at)
        ))

    def pending(self) -> int:
        return self.db.scalar(
            select(func.count()).select_from(OpportunityRefreshCheck).where(
                OpportunityRefreshCheck.opportunity_id == self.id, OpportunityRefreshCheck.review_state == "pending")
        )


def day(number: int) -> datetime:
    return NOW + timedelta(days=number)


# --- unchanged -------------------------------------------------------------------------------------------


def test_unchanged_source_first_a_full_read_then_a_304(db_session, monkeypatch, curator):
    item = Published(db_session, FakeWeb(monkeypatch), curator)

    first = item.refresh(day(1))  # nothing held yet for a conditional request: a full read, same content
    second = item.refresh(day(2))  # now conditional: 304
    assert (first.outcome, first.review_state) == ("unchanged", "none")
    assert (second.outcome, second.review_state) == ("unchanged", "none")
    requests = item.web.requests_for(item.url)
    assert [(seen.status, seen.if_none_match) for seen in requests] == [(200, None), (304, V1)]
    one, two = item.checks()
    assert (one.http_status, one.content_changed, one.etag, one.page_text) == (200, False, V1, None)
    assert (two.http_status, two.content_changed, two.etag, two.page_text) == (304, False, V1, None)
    assert one.content_hash == two.content_hash == item.approved["snapshot_hash"]
    assert item.pending() == 0


def test_a_change_that_touches_nothing_approved_is_unchanged_but_kept_as_history(db_session, monkeypatch, curator):
    item = Published(db_session, FakeWeb(monkeypatch), curator)
    item.serve(opportunity_page(extra="<p>Page last updated 20 November 2026.</p>"), etag=V2)
    result = item.refresh(day(1))
    check = item.check(result)
    assert (result.outcome, result.review_state) == ("unchanged", "none")
    assert check.content_changed and "Page last updated 20 November 2026." in check.page_text
    assert check.content_hash != item.approved["snapshot_hash"] and check.etag == V2


# --- deadline --------------------------------------------------------------------------------------------


def test_deadline_changed_is_reported_once_and_never_written_to_the_opportunity(db_session, monkeypatch, curator):
    item = Published(db_session, FakeWeb(monkeypatch), curator)
    item.serve(opportunity_page(deadline="31 January 2027"), etag=V2)

    result = item.refresh(day(1))
    check = item.check(result)
    assert (result.outcome, result.review_state) == ("deadline_changed", "pending")
    assert check.findings["deadline"] | {"quote": None} == {
        "approved": "2027-01-15", "page_states": "2027-01-31", "days_later": 16, "quote": None}
    assert "31 January 2027" in check.findings["deadline"]["quote"]
    assert "31 January 2027" in check.page_text  # the changed page is kept as evidence
    assert item.frozen()["deadline_at"] == datetime(2027, 1, 15, 23, 59, tzinfo=timezone.utc)
    audit = db_session.scalar(select(AuditLog).where(AuditLog.action == "opportunity.refresh_finding", AuditLog.target_id == str(item.id)))
    assert audit.changes == {"check_id": str(check.id), "outcome": "deadline_changed"} and audit.actor_kind == "system"

    # The next check is a 304: the source has not changed again and the finding is still waiting.
    again = item.refresh(day(2))
    assert (again.outcome, again.review_state) == ("unchanged", "none") and item.pending() == 1

    # The page changes cosmetically while still stating the same different deadline: not raised twice.
    item.serve(opportunity_page(deadline="31 January 2027", extra="<p>New banner.</p>"), etag=V3)
    third = item.refresh(day(3))
    assert (third.outcome, third.review_state) == ("deadline_changed", "none") and item.pending() == 1


def test_a_deadline_appearing_on_a_rolling_opportunity_is_a_deadline_change(db_session, monkeypatch, curator):
    web = FakeWeb(monkeypatch)
    item = Published(db_session, web, curator, publish=False)
    opportunity = db_session.get(Opportunity, item.id)
    opportunity.deadline_type, opportunity.deadline_at = "rolling", None
    db_session.flush()
    publish_opportunity(db_session, item.id)
    item.approved = item.frozen()
    item.serve(opportunity_page(deadline="31 March 2027"), etag=V2)
    result = item.refresh(day(1))
    assert (result.outcome, result.review_state) == ("deadline_changed", "pending")
    assert item.check(result).findings["deadline"]["page_states"] == "2027-03-31"


# --- material update -------------------------------------------------------------------------------------


def test_material_update_when_an_approved_eligibility_quote_is_gone(db_session, monkeypatch, curator):
    item = Published(db_session, FakeWeb(monkeypatch), curator)
    changed = opportunity_page().replace(
        b"Applicants must have completed at least two years of study by June 2027.",
        b"Applicants must have completed at least three years of study and hold a GPA of 3.5 or higher.",
    )
    item.serve(changed, etag=V2)
    result = item.refresh(day(1))
    findings = item.check(result).findings
    assert (result.outcome, result.review_state) == ("material_update", "pending")
    assert findings["eligibility"]["approved_quotes_missing"] == [
        "Applicants must have completed at least two years of study by June 2027."]
    assert findings["eligibility"]["new_statements"] == [
        "Applicants must have completed at least three years of study and hold a GPA of 3.5 or higher."]
    # The approved rule and the snapshot it was quoted from are still what the opportunity shows.
    assert any("two years of study" in quote for _, quote, _, _ in item.frozen()["requirements"])
    assert "two years of study" in item.frozen()["snapshot"]["text"]


# --- closed ----------------------------------------------------------------------------------------------


def test_closed_when_the_page_says_applications_are_closed(db_session, monkeypatch, curator):
    item = Published(db_session, FakeWeb(monkeypatch), curator)
    item.serve(opportunity_page(extra="<p>Applications are now closed.</p>"), etag=V2)
    result = item.refresh(day(1))
    assert (result.outcome, result.review_state) == ("closed", "pending")
    assert "closed" in item.check(result).findings["closed_on_page"]["quote"].lower()
    assert item.frozen()["status"] == OpportunityStatus.PUBLISHED  # closing stays a curator action


def test_closed_when_the_approved_deadline_has_passed_even_on_a_304(db_session, monkeypatch, curator):
    item = Published(db_session, FakeWeb(monkeypatch), curator)
    assert item.refresh(day(1)).outcome == "unchanged"
    after = datetime(2027, 1, 20, 12, 0, tzinfo=timezone.utc)
    result = item.refresh(after)
    check = item.check(result)
    assert item.web.requests_for(item.url)[-1].status == 304
    assert (result.outcome, result.review_state) == ("closed", "pending")
    assert check.findings == {"deadline_passed": {"approved": "2027-01-15", "today": "2027-01-20"}}
    # Asked once; the same expired cycle on later checks is recorded without a new review item.
    later = item.refresh(after + timedelta(days=7))
    assert (later.outcome, later.review_state) == ("closed", "none") and item.pending() == 1


# --- new cycle -------------------------------------------------------------------------------------------


def test_new_cycle_goes_to_the_candidate_queue_once_and_never_duplicates(db_session, monkeypatch, curator):
    item = Published(db_session, FakeWeb(monkeypatch), curator)
    next_year = opportunity_page(title="Summer Research Scholarship 2028", deadline="15 January 2028").replace(b"June 2027", b"June 2028")
    item.serve(next_year, etag=V2)
    after = datetime(2027, 9, 1, 12, 0, tzinfo=timezone.utc)

    result = item.refresh(after)
    check = item.check(result)
    assert (result.outcome, result.review_state) == ("new_cycle", "pending")
    assert check.findings["new_cycle"] | {"quote": None} == {
        "approved": "2027-01-15", "page_states": "2028-01-15", "days_later": 365, "quote": None}
    candidate = db_session.get(IngestionCandidate, check.candidate_id)
    assert candidate.state == CandidateState.NEEDS_REVIEW and candidate.duplicate_of_opportunity_id == item.id
    assert candidate.extraction["deadline"]["value"] == "2028-01-15" and "2028" in candidate.page_text
    assert any("possible new cycle" in warning for warning in candidate.validation["warnings"])

    # A later check of the same new cycle (the page changed again) reuses that candidate.
    item.serve(next_year.replace(b"</main>", b"<p>Apply early.</p></main>"), etag=V3)
    again = item.refresh(after + timedelta(days=1))
    assert (again.outcome, again.review_state) == ("new_cycle", "none")
    assert item.check(again).candidate_id == candidate.id
    candidates = db_session.scalars(select(IngestionCandidate).where(IngestionCandidate.source_id == item.source.id)).all()
    assert len(candidates) == 2  # the one that was approved, and the one new cycle

    # Approving it creates a separate draft for 2028; the 2027 opportunity is not rewritten.
    draft = pipeline.approve_candidate(db_session, candidate.id, actor_id=curator.id, decision=pipeline.ApprovalInput(notes="2028 cycle"))
    assert draft.id != item.id and draft.status == OpportunityStatus.DRAFT
    assert draft.deadline_at.year == 2028 and item.frozen() == item.approved

    # With the 2028 cycle listed separately, the old opportunity is simply an expired cycle.
    item.serve(next_year, etag='"v4"')
    final = item.refresh(after + timedelta(days=2))
    final_check = item.check(final)
    assert final.outcome == "closed" and final_check.candidate_id is None
    assert "new_cycle_already_listed" in final_check.findings and "deadline_passed" in final_check.findings


def test_a_closed_opportunity_asks_for_review_only_for_a_new_cycle(db_session, monkeypatch, curator):
    item = Published(db_session, FakeWeb(monkeypatch), curator)
    close_opportunity(db_session, item.id)
    item.approved = item.frozen()

    item.serve(opportunity_page(deadline="31 January 2027"), etag=V2)
    moved = item.refresh(day(1))
    assert (moved.outcome, moved.review_state) == ("deadline_changed", "none")

    item.serve(opportunity_page(title="Summer Research Scholarship 2028", deadline="15 January 2028"), etag=V3)
    cycle = item.refresh(datetime(2027, 9, 1, 12, 0, tzinfo=timezone.utc))
    assert (cycle.outcome, cycle.review_state) == ("new_cycle", "pending")
    assert item.check(cycle).candidate_id is not None and item.frozen()["status"] == OpportunityStatus.CLOSED


# --- source unavailable ----------------------------------------------------------------------------------


def test_a_dead_link_is_source_unavailable_and_asks_for_review_at_once(db_session, monkeypatch, curator):
    item = Published(db_session, FakeWeb(monkeypatch), curator)
    assert item.refresh(day(1)).outcome == "unchanged"
    held = item.checks()[-1]
    item.serve(b"gone", status=404)
    result = item.refresh(day(2))
    check = item.check(result)
    assert (result.outcome, result.review_state) == ("source_unavailable", "pending")
    assert check.http_status == 404 and check.error.startswith("dead_link") and check.consecutive_failures == 1
    assert check.findings["source_unavailable"] == {"kind": "dead_link", "permanent": True, "failures_in_a_row": 1}
    # The failed request destroyed nothing: validators and content hash are carried forward.
    assert (check.etag, check.content_hash) == (held.etag, held.content_hash) == (V1, item.approved["snapshot_hash"])


def test_transient_failures_keep_validators_and_ask_for_review_only_when_they_persist(db_session, monkeypatch, curator):
    item = Published(db_session, FakeWeb(monkeypatch), curator)
    assert item.refresh(day(1)).outcome == "unchanged"

    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("The read operation timed out", request=request)

    failures = [
        (lambda request: httpx.Response(503, content=b"down"), "server_error", 503),
        (timeout, "timeout", None),
        (lambda request: httpx.Response(429, content=b"slow down"), "rate_limited", 429),
        (lambda request: httpx.Response(403, content=b"no"), "access_denied", 403),
    ]
    states = []
    for number, (handler, kind, status) in enumerate(failures, start=1):
        item.web.respond(item.url, handler)
        result = item.refresh(day(1 + number))
        check = item.check(result)
        assert result.outcome == "source_unavailable" and check.http_status == status
        assert check.findings["source_unavailable"] == {"kind": kind, "permanent": False, "failures_in_a_row": number}
        assert item.web.requests_for(item.url)[-1].if_none_match == V1  # validators still being sent
        assert (check.etag, check.content_hash) == (V1, item.approved["snapshot_hash"])
        states.append(result.review_state)
    assert states == ["none", "none", "pending", "none"]  # raised on the third failure in a row, once

    # The server recovers with the same content: the stored validator still earns a 304.
    item.serve(opportunity_page(), etag=V1)
    recovered = item.refresh(day(10))
    assert recovered.outcome == "unchanged" and item.web.requests_for(item.url)[-1].status == 304
    assert item.check(recovered).consecutive_failures == 0


def test_refresh_obeys_robots_and_does_not_request_a_disallowed_page(db_session, monkeypatch, curator):
    item = Published(db_session, FakeWeb(monkeypatch), curator)
    item.web.robots(item.url.split("/")[2], "User-agent: *\nDisallow: /\n")
    result = item.refresh(day(1))
    assert result.outcome == "source_unavailable"
    assert item.check(result).findings["source_unavailable"]["kind"] == "robots_disallowed"
    assert item.web.requests_for(item.url) == []


def test_a_redirect_off_the_allow_list_is_source_unavailable(db_session, monkeypatch, curator):
    item = Published(db_session, FakeWeb(monkeypatch), curator)
    item.web.respond(item.url, lambda request: httpx.Response(302, headers={"location": "https://elsewhere.example.org/x"}))
    result = item.refresh(day(1))
    assert result.outcome == "source_unavailable"
    assert item.check(result).findings["source_unavailable"]["kind"] == "redirect_off_allowlist"
    assert item.web.requests_for("https://elsewhere.example.org/x") == []


# --- review required -------------------------------------------------------------------------------------


def test_review_required_when_the_page_is_no_longer_an_opportunity_page(db_session, monkeypatch, curator):
    item = Published(db_session, FakeWeb(monkeypatch), curator)
    item.serve(NEWS, etag=V2)
    result = item.refresh(day(1))
    assert (result.outcome, result.review_state) == ("review_required", "pending")
    # The URL still contains "scholarship", which alone keeps the page "relevant"; what decides is
    # that nothing approved is on it and it states no deadline or eligibility of its own.
    assert item.check(result).findings["opportunity_content_missing"] == {"approved_quotes_missing": 2}


def test_review_required_when_the_approved_deadline_can_no_longer_be_found(db_session, monkeypatch, curator):
    item = Published(db_session, FakeWeb(monkeypatch), curator)
    item.serve(opportunity_page().replace(b"<p>Application deadline: 15 January 2027.</p>", b"<p>The deadline will be announced soon.</p>"), etag=V2)
    result = item.refresh(day(1))
    findings = item.check(result).findings
    assert (result.outcome, result.review_state) == ("review_required", "pending")
    assert findings["deadline_not_found"]["approved"] == "2027-01-15"


def test_review_required_when_the_page_shows_a_much_earlier_deadline(db_session, monkeypatch, curator):
    item = Published(db_session, FakeWeb(monkeypatch), curator)
    item.serve(opportunity_page(deadline="15 January 2026"), etag=V2)
    result = item.refresh(day(1))
    assert (result.outcome, result.review_state) == ("review_required", "pending")
    assert item.check(result).findings["earlier_deadline"]["page_states"] == "2026-01-15"


# --- what is and is not refreshed ------------------------------------------------------------------------


def test_only_pages_under_an_approved_source_are_fetched(db_session, monkeypatch, curator):
    web = FakeWeb(monkeypatch)
    item = Published(db_session, web, curator)
    registry.change_status(db_session, item.source, SourceStatus.PAUSED, actor_id=curator.id)
    report = refresh.refresh_opportunities(db_session, reader_factory=web.reader, now=day(1), opportunity_id=item.id, min_interval=NO_WAIT)
    assert report.checked == 0 and web.requests == [] and item.checks() == []
    [skipped] = report.skipped
    assert skipped.opportunity_id == item.id and "is paused, not approved" in skipped.reason

    # A draft is never refreshed either.
    draft = Published(db_session, web, curator, publish=False, title="Autumn Research Scholarship 2027")
    report = refresh.refresh_opportunities(db_session, reader_factory=web.reader, now=day(1), opportunity_id=draft.id, min_interval=NO_WAIT)
    assert report.checked == 0 and report.skipped == [] and web.requests == []


def test_a_run_checks_the_least_recently_checked_first_and_respects_the_interval(db_session, monkeypatch, curator):
    web = FakeWeb(monkeypatch)
    one = Published(db_session, web, curator)
    two = Published(db_session, web, curator, title="Winter Research Scholarship 2027")
    ours = {one.id, two.id}

    def run(now, **kwargs):
        report = refresh.refresh_opportunities(db_session, reader_factory=web.reader, now=now, limit=500, **kwargs)
        return [result.opportunity_id for result in report.results if result.opportunity_id in ours], report

    checked, report = run(day(1))
    assert set(checked) == ours
    run_row = db_session.get(IngestionRun, report.run_id)
    assert (run_row.kind, run_row.status) == ("refresh", "succeeded") and run_row.stats["checked"] == report.checked
    assert run(day(1) + timedelta(hours=2))[0] == []  # inside the default 24 hours: nothing is due
    assert set(run(day(2) + timedelta(hours=1))[0]) == ours


def test_a_second_run_while_one_is_in_progress_checks_nothing(db_session, monkeypatch, curator):
    web = FakeWeb(monkeypatch)
    item = Published(db_session, web, curator)
    db_session.add(IngestionRun(kind="refresh", status="running", started_at=datetime.now(timezone.utc) - timedelta(minutes=5)))
    db_session.flush()
    report = refresh.refresh_opportunities(db_session, reader_factory=web.reader, now=day(1), opportunity_id=item.id, min_interval=NO_WAIT)
    assert report.busy and report.checked == 0 and web.requests == [] and item.checks() == []
    assert db_session.get(IngestionRun, report.run_id).status == "failed"

    # A run that died long ago does not block refreshing forever.
    stale = db_session.scalar(select(IngestionRun).where(IngestionRun.kind == "refresh", IngestionRun.status == "running"))
    stale.started_at = datetime.now(timezone.utc) - timedelta(hours=3)
    db_session.flush()
    assert item.refresh(day(1)).outcome == "unchanged"


# --- curator review of findings --------------------------------------------------------------------------


def test_resolving_a_finding_records_the_decision_and_changes_nothing_else(db_session, monkeypatch, curator):
    item = Published(db_session, FakeWeb(monkeypatch), curator)
    item.serve(opportunity_page(deadline="31 January 2027"), etag=V2)
    check_id = item.refresh(day(1)).check_id

    with pytest.raises(refresh.RefreshError, match="Say why"):
        refresh.resolve_check(db_session, check_id, actor_id=curator.id, decision="dismiss", notes=" ")
    with pytest.raises(refresh.RefreshError, match="acknowledge or dismiss"):
        refresh.resolve_check(db_session, check_id, actor_id=curator.id, decision="apply", notes=None)
    check = refresh.resolve_check(db_session, check_id, actor_id=curator.id, decision="dismiss", notes="date is for a side event")
    assert (check.review_state, check.reviewed_by, check.review_notes) == ("dismissed", curator.id, "date is for a side event")
    assert item.frozen() == item.approved and item.pending() == 0
    with pytest.raises(refresh.RefreshError, match="only a pending finding"):
        refresh.resolve_check(db_session, check_id, actor_id=curator.id, decision="acknowledge", notes=None)
    with pytest.raises(refresh.RefreshError, match="not found"):
        refresh.resolve_check(db_session, uuid.uuid4(), actor_id=curator.id, decision="acknowledge", notes=None)
    assert db_session.scalar(select(AuditLog).where(
        AuditLog.action == "opportunity.refresh_finding_dismissed", AuditLog.target_id == str(item.id))) is not None

    # A dismissed finding is not raised again when the page changes without changing the finding.
    item.serve(opportunity_page(deadline="31 January 2027", extra="<p>Banner.</p>"), etag=V3)
    assert item.refresh(day(2)).review_state == "none"


async def test_refresh_findings_api_is_for_curators_and_never_edits_the_opportunity(client, db_session, monkeypatch, curator):  # noqa: F811
    item = Published(db_session, FakeWeb(monkeypatch), curator)
    item.serve(opportunity_page(deadline="31 January 2027"), etag=V2)
    check_id = item.refresh(day(1)).check_id
    student = User(email=f"student-{uuid.uuid4().hex[:8]}@example.org", password_hash="x", role="student")
    db_session.add(student)
    db_session.flush()
    base = "/curate/ingestion/refresh-checks"

    assert (await client.get(base)).status_code == 401
    assert (await client.get(base, headers=as_(student))).status_code == 403
    resolve = {"decision": "acknowledge", "notes": "deadline corrected"}
    assert (await client.post(f"{base}/{check_id}/resolve", json=resolve, headers=as_(student))).status_code == 403

    listing = await client.get(f"{base}?opportunity_id={item.id}", headers=as_(curator))
    assert listing.status_code == 200
    [row] = listing.json()
    assert (row["id"], row["outcome"], row["review_state"]) == (str(check_id), "deadline_changed", "pending")
    assert row["opportunity_title"] == item.approved["title"] and "page_text" not in row
    detail = (await client.get(f"{base}/{check_id}", headers=as_(curator))).json()
    assert detail["findings"]["deadline"]["page_states"] == "2027-01-31" and detail["etag"] == V2

    done = await client.post(f"{base}/{check_id}/resolve", json=resolve, headers=as_(curator))
    assert done.status_code == 200 and done.json()["review_state"] == "acknowledged"
    assert (await client.post(f"{base}/{check_id}/resolve", json=resolve, headers=as_(curator))).status_code == 409
    assert (await client.post(f"{base}/{uuid.uuid4()}/resolve", json=resolve, headers=as_(curator))).status_code == 404
    assert (await client.get(f"{base}?opportunity_id={item.id}", headers=as_(curator))).json() == []
    assert item.frozen() == item.approved
