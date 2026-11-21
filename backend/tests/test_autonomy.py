"""Autonomous review: the AI reader is held to the evidence standard, and automation acts only when every check passes."""
from __future__ import annotations

import json
import uuid
from datetime import date, timedelta

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.intelligence import ai_review, autonomy, registry
from app.intelligence.definitions import SourceDefinition
from app.models import AuditLog, IngestionCandidate, Opportunity, User
from app.models.enums import OpportunityStatus, PublishMode, RobotsStatus, SourceStatus
from app.models.ingestion import CandidateState

TODAY = date(2026, 11, 20)
PAGE = (
    "The Example Research Fellowship 2027\n"
    "Applicants must be enrolled in a PhD programme at an accredited university.\n"
    "Applicants must  be\nfluent in English.\n"
    "Applications close on 15 March 2027 at midnight.\n"
    "Funding covers travel and a monthly stipend."
)


# ---------------------------------------------------------------------------
# The AI reader: only what the page says survives
# ---------------------------------------------------------------------------


def raw(**overrides):
    base = {
        "is_opportunity_page": True,
        "single_opportunity": True,
        "title": {"value": "Example Research Fellowship", "quote": "The Example Research Fellowship 2027"},
        "opportunity_type": "fellowship",
        "deadline": {"kind": "fixed", "date": "2027-03-15", "quote": "Applications close on 15 March 2027 at midnight."},
        "applications": "open",
        "eligibility": [
            {"quote": "Applicants must be enrolled in a PhD programme at an accredited university."},
            {"quote": "Applicants must be fluent in English."},
        ],
        "concerns": [],
        "confidence": 0.9,
    }
    base.update(overrides)
    return base


def test_verified_fields_are_kept_and_quotes_are_exact_page_text():
    review = ai_review.verify(raw(), PAGE, "test-model", TODAY)
    assert review.title == "Example Research Fellowship"
    assert review.deadline == date(2027, 3, 15) and review.deadline_kind == "fixed"
    assert len(review.statements) == 2
    for statement in review.statements:
        assert statement in PAGE  # exact substring, line breaks included
    assert review.dropped == []


def test_invented_or_unsupported_answers_are_dropped():
    review = ai_review.verify(
        raw(
            title={"value": "Global Leaders Award", "quote": "The Global Leaders Award"},
            deadline={"kind": "fixed", "date": "2027-03-15", "quote": "Applications close on 15 March at midnight."},
            eligibility=[{"quote": "Applicants must be under 30."}, {"quote": "Applicants must be fluent in English."}],
        ),
        PAGE, "m", TODAY,
    )
    assert review.title is None
    assert review.deadline is None  # the quote isn't on the page, and has no year
    assert review.statements == ["Applicants must  be\nfluent in English."]
    assert len(review.dropped) == 3


def test_a_deadline_needs_its_year_in_the_quote():
    page = "Applications close on 15 March. The 2027 cohort starts in June."
    review = ai_review.verify(raw(deadline={"kind": "fixed", "date": "2027-03-15", "quote": "Applications close on 15 March."}), page, "m", TODAY)
    assert review.deadline is None


def test_no_key_means_no_request(monkeypatch):
    monkeypatch.setattr(settings, "GROQ_API_KEY", None)
    called = []
    client = httpx.Client(transport=httpx.MockTransport(lambda request: called.append(1) or httpx.Response(200)))
    assert ai_review.review_page(PAGE, today=TODAY, client=client) is None
    assert called == []


def test_the_call_uses_strict_json_schema_and_retries_once_on_rate_limit(monkeypatch):
    monkeypatch.setattr(settings, "GROQ_API_KEY", "test-key")
    monkeypatch.setattr(ai_review.time, "sleep", lambda seconds: None)
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen.append(body)
        assert request.headers["authorization"] == "Bearer test-key"
        assert body["response_format"]["json_schema"]["strict"] is True
        assert "<page>" in body["messages"][1]["content"]
        if len(seen) == 1:
            return httpx.Response(429, headers={"retry-after": "1"})
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(raw())}}]})

    review = ai_review.review_page(PAGE, today=TODAY, client=httpx.Client(transport=httpx.MockTransport(handler)))
    assert review is not None and review.title == "Example Research Fellowship"
    assert len(seen) == 2


def test_a_failed_call_is_no_opinion_not_a_crash(monkeypatch):
    monkeypatch.setattr(settings, "GROQ_API_KEY", "test-key")
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(500)))
    assert ai_review.review_page(PAGE, today=TODAY, client=client) is None


# ---------------------------------------------------------------------------
# Decisions
# ---------------------------------------------------------------------------


@pytest.fixture
def admin(db_session: Session) -> User:
    user = User(email=f"admin-{uuid.uuid4().hex[:8]}@example.org", password_hash="x", role="admin")
    db_session.add(user)
    db_session.flush()
    return user


def make_source(db_session: Session, admin: User, mode: PublishMode):
    host = f"site-{uuid.uuid4().hex[:8]}.fellowship-foundation.org"  # each source claims its own host
    definition = SourceDefinition.model_validate({
        "name": f"Example source {uuid.uuid4().hex[:6]}", "base_domain": "fellowship-foundation.org", "allowed_hosts": [host],
        "category": "foundation", "authority_level": "official", "provider": {"name": "Example Foundation"},
        "discovery_method": "url_list", "connector_key": "url_list", "connector_config": {"urls": [f"https://{host}/fellowship"]},
    })
    source = registry.create_source(db_session, definition, actor_id=admin.id)
    registry.change_status(db_session, source, SourceStatus.TESTING, actor_id=admin.id)
    registry.record_test_run(db_session, source, passed=True, robots_status=RobotsStatus.ALLOWED)
    registry.record_terms_review(db_session, source, status="acceptable", reviewer_id=admin.id, notes="CC-BY")
    registry.change_status(db_session, source, SourceStatus.APPROVED, actor_id=admin.id, reason="Test")
    for step in (PublishMode.SHADOW, PublishMode.LISTING_ONLY, PublishMode.FULL):
        if [PublishMode.OFF, PublishMode.SHADOW, PublishMode.LISTING_ONLY, PublishMode.FULL].index(step) > [PublishMode.OFF, PublishMode.SHADOW, PublishMode.LISTING_ONLY, PublishMode.FULL].index(mode):
            break
        registry.set_publish_mode(db_session, source, step, actor_id=admin.id, reason="Test")
    db_session.flush()
    return source


def extraction(title="The Example Research Fellowship 2027", deadline="2027-03-15", statements=None):
    statements = statements if statements is not None else [
        "Applicants must be enrolled in a PhD programme at an accredited university.",
        "Applicants must  be\nfluent in English.",
    ]
    return {
        "title": {"status": "explicit", "value": title, "evidence": [{"quote": title, "location": "text"}]},
        "opportunity_type": {"status": "inferred", "value": "fellowship", "evidence": []},
        "deadline": {"status": "explicit" if deadline else "not_found", "value": deadline, "evidence": []},
        "eligibility": {"status": "explicit" if statements else "not_found", "value": statements, "evidence": []},
    }


def make_candidate(db_session: Session, source, *, quality=70, ex=None, validation=None) -> IngestionCandidate:
    candidate = IngestionCandidate(
        source_id=source.id, candidate_key=uuid.uuid4().hex, url="https://www.fellowship-foundation.org/fellowship", final_url="https://www.fellowship-foundation.org/fellowship",
        state=CandidateState.NEEDS_REVIEW, page_text=PAGE, content_hash=uuid.uuid4().hex, quality_score=quality,
        extraction=ex or extraction(), validation=validation or {"problems": [], "warnings": [], "irrelevant": False, "expired": False},
    )
    db_session.add(candidate)
    db_session.flush()
    return candidate


def test_every_check_passing_publishes_in_full_mode(db_session, admin):
    source = make_source(db_session, admin, PublishMode.FULL)
    decision = autonomy.decide(make_candidate(db_session, source), source, today=TODAY, ai=None, use_ai=False)
    assert decision.outcome == "publish", decision.held_because


@pytest.mark.parametrize(
    "change,reason",
    [
        ({"ex": extraction(title="Home")}, "too generic"),
        ({"ex": extraction(deadline="2026-01-10")}, "has passed"),
        ({"ex": extraction(deadline=None)}, "No deadline"),
        ({"ex": extraction(statements=["Applicants must be fluent in English."])}, "Fewer than 2"),
        ({"quality": 40}, "quality must be at least"),
        ({"validation": {"problems": ["x"], "irrelevant": False, "expired": False}}, "Validation found problems"),
    ],
)
def test_any_failing_check_holds_for_a_person(db_session, admin, change, reason):
    source = make_source(db_session, admin, PublishMode.FULL)
    decision = autonomy.decide(make_candidate(db_session, source, **change), source, today=TODAY, ai=None, use_ai=False)
    assert decision.outcome == "hold"
    assert any(reason in item for item in decision.held_because), decision.held_because


def test_ai_and_rule_deadlines_must_agree(db_session, admin):
    source = make_source(db_session, admin, PublishMode.FULL)
    ai = ai_review.verify(raw(deadline={"kind": "fixed", "date": "2027-03-16", "quote": "Applications close on 15 March 2027 at midnight."}), PAGE, "m", TODAY)
    decision = autonomy.decide(make_candidate(db_session, source), source, today=TODAY, ai=ai, use_ai=True)
    assert decision.outcome == "hold" and any("Two different deadlines" in r for r in decision.held_because)


def test_ai_can_supply_a_title_and_deadline_the_rules_missed(db_session, admin):
    source = make_source(db_session, admin, PublishMode.FULL)
    candidate = make_candidate(db_session, source, quality=30, ex=extraction(title="Home", deadline=None))
    ai = ai_review.verify(raw(), PAGE, "m", TODAY)
    decision = autonomy.decide(candidate, source, today=TODAY, ai=ai, use_ai=True)
    assert decision.outcome == "publish", decision.held_because
    assert decision.title == "Example Research Fellowship" and decision.deadline == date(2027, 3, 15)


@pytest.mark.parametrize("override,reason", [({"applications": "closed"}, "closed"), ({"confidence": 0.4}, "confidence"), ({"single_opportunity": False}, "single opportunity")])
def test_the_ai_can_veto(db_session, admin, override, reason):
    source = make_source(db_session, admin, PublishMode.FULL)
    ai = ai_review.verify(raw(**override), PAGE, "m", TODAY)
    decision = autonomy.decide(make_candidate(db_session, source), source, today=TODAY, ai=ai, use_ai=True)
    assert decision.outcome == "hold" and any(reason in r for r in decision.held_because)


def test_ai_on_but_unavailable_holds(db_session, admin):
    source = make_source(db_session, admin, PublishMode.FULL)
    decision = autonomy.decide(make_candidate(db_session, source), source, today=TODAY, ai=None, use_ai=True)
    assert decision.outcome == "hold"


# ---------------------------------------------------------------------------
# Acting, by publish mode
# ---------------------------------------------------------------------------


@pytest.fixture
def no_ai(monkeypatch):
    monkeypatch.setattr(settings, "GROQ_API_KEY", None)
    monkeypatch.setattr(Session, "commit", Session.flush)  # stay inside the test transaction


def test_full_mode_drafts_publishes_and_audits(db_session, admin, no_ai):
    source = make_source(db_session, admin, PublishMode.FULL)
    candidate = make_candidate(db_session, source)
    counts = autonomy.run(db_session, today=TODAY)
    assert counts["published"] == 1
    db_session.refresh(candidate)
    assert candidate.state == CandidateState.APPROVED
    opportunity = db_session.get(Opportunity, candidate.opportunity_id)
    assert opportunity.status == OpportunityStatus.PUBLISHED
    assert {r.source_quote for r in opportunity.requirements} == {
        "Applicants must be enrolled in a PhD programme at an accredited university.", "Applicants must  be\nfluent in English."}
    entry = db_session.scalar(select(AuditLog).where(AuditLog.action == "opportunity.auto_published", AuditLog.target_id == str(opportunity.id)))
    assert entry is not None and entry.actor_kind == "system"
    assert candidate.validation["autonomy"]["acted"] == "published"


def test_listing_only_mode_drafts_but_does_not_publish(db_session, admin, no_ai):
    source = make_source(db_session, admin, PublishMode.LISTING_ONLY)
    candidate = make_candidate(db_session, source)
    assert autonomy.run(db_session, today=TODAY)["drafted"] == 1
    db_session.refresh(candidate)
    assert db_session.get(Opportunity, candidate.opportunity_id).status == OpportunityStatus.DRAFT


def test_shadow_mode_only_records_and_off_mode_is_untouched(db_session, admin, no_ai):
    shadow = make_candidate(db_session, make_source(db_session, admin, PublishMode.SHADOW))
    off = make_candidate(db_session, make_source(db_session, admin, PublishMode.OFF))
    counts = autonomy.run(db_session, today=TODAY)
    assert counts["shadow"] == 1 and counts["published"] == counts["drafted"] == 0
    db_session.refresh(shadow)
    db_session.refresh(off)
    assert shadow.state == CandidateState.NEEDS_REVIEW and shadow.validation["autonomy"]["acted"] == "would publish"
    assert off.state == CandidateState.NEEDS_REVIEW and "autonomy" not in (off.validation or {})


def test_a_held_candidate_is_not_re_decided_until_its_content_or_mode_changes(db_session, admin, no_ai):
    source = make_source(db_session, admin, PublishMode.FULL)
    make_candidate(db_session, source, quality=40)
    assert autonomy.run(db_session, today=TODAY)["held"] == 1
    assert autonomy.run(db_session, today=TODAY)["skipped"] == 1


def test_published_opportunities_close_after_their_deadline(db_session, admin, no_ai):
    source = make_source(db_session, admin, PublishMode.FULL)
    candidate = make_candidate(db_session, source)
    autonomy.run(db_session, today=TODAY)
    db_session.refresh(candidate)
    from datetime import datetime, timezone

    assert autonomy.close_past_deadline(db_session, now=datetime(2027, 3, 17, tzinfo=timezone.utc)) >= 1
    assert db_session.get(Opportunity, candidate.opportunity_id).status == OpportunityStatus.CLOSED


def test_several_deadlines_need_the_ai_to_agree(db_session, admin):
    source = make_source(db_session, admin, PublishMode.FULL)
    validation = {"problems": [], "irrelevant": False, "expired": False, "warnings": ["deadline: the page mentions deadlines in 4 places; check that this date applies to the whole programme and this cycle"]}
    without_ai = autonomy.decide(make_candidate(db_session, source, validation=validation), source, today=TODAY, ai=None, use_ai=False)
    assert without_ai.outcome == "hold" and any("several deadlines" in r for r in without_ai.held_because)
    with_ai = autonomy.decide(make_candidate(db_session, source, validation=validation), source, today=TODAY, ai=ai_review.verify(raw(), PAGE, "m", TODAY), use_ai=True)
    assert with_ai.outcome == "publish", with_ai.held_because


def test_a_possible_new_cycle_is_always_a_person_s_call(db_session, admin):
    source = make_source(db_session, admin, PublishMode.FULL)
    validation = {"problems": [], "irrelevant": False, "expired": False, "warnings": ["possible new cycle of existing opportunity 'X'"]}
    decision = autonomy.decide(make_candidate(db_session, source, validation=validation), source, today=TODAY, ai=ai_review.verify(raw(), PAGE, "m", TODAY), use_ai=True)
    assert decision.outcome == "hold"
