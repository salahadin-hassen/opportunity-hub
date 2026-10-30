"""The demo seed is valid, idempotent and tells the walkthrough's story."""
from __future__ import annotations

from collections import Counter
from datetime import date
from decimal import Decimal

from app.models import Opportunity, Profile, Requirement, Skill, User
from app.services.matches import evaluate_and_persist_match_for_user
from scripts import seed_demo
from sqlalchemy import func, select
from sqlalchemy.orm import Session


def run_seed(db_session: Session) -> User:
    skills = seed_demo.upsert_skills(db_session)
    for spec in seed_demo.OPPORTUNITIES:
        seed_demo.upsert_opportunity(db_session, spec)
    seed_demo.retire_opportunities(db_session)
    return seed_demo.reset_demo_user(db_session, skills, "test-only-demo-password")


def demo_profile(db_session: Session, user: User) -> Profile:
    return db_session.scalar(select(Profile).where(Profile.user_id == user.id))


def verdicts(db_session: Session, profile: Profile) -> dict[str, str]:
    """Verdicts for the opportunities the demo lists (published ones)."""
    slugs = [spec["slug"] for spec in seed_demo.OPPORTUNITIES if spec.get("status", "published") == "published"]
    rows = db_session.scalars(select(Opportunity).where(Opportunity.slug.in_(slugs))).all()
    return {
        row.slug: str(evaluate_and_persist_match_for_user(db_session, profile, row.id).status)
        for row in rows
    }


def count(db_session: Session, model) -> int:
    return db_session.scalar(select(func.count()).select_from(model))


def test_every_rule_carries_a_verbatim_quote_from_its_source(db_session):
    run_seed(db_session)

    for spec in seed_demo.OPPORTUNITIES:
        opportunity = db_session.get(Opportunity, seed_demo.stable_id("opportunity", spec["slug"]))
        assert opportunity.status == spec.get("status", "published")
        sources = {source.id: source for source in opportunity.sources}
        assert [source.is_primary for source in opportunity.sources].count(True) == 1
        assert all(source.source_type == "official_page" for source in sources.values())
        assert opportunity.requirements, spec["slug"]
        for requirement in opportunity.requirements:
            source = sources[requirement.source_id]
            assert requirement.source_quote
            assert requirement.source_quote in source.raw_snapshot["quotes"]


def test_rule_sources_follow_the_page_they_quote(db_session):
    run_seed(db_session)
    eth = db_session.get(
        Opportunity, seed_demo.stable_id("opportunity", "eth-student-summer-research-fellowship-2027")
    )

    by_label = {requirement.label: requirement for requirement in eth.requirements}
    excluded = next(source for source in eth.sources if source.id == by_label["Not enrolled at ETH Zurich"].source_id)
    assert not excluded.is_primary
    assert excluded.url.endswith("/summer-research-fellowship.html")


def test_retired_opportunities_are_removed(db_session):
    seed_demo.upsert_opportunity(
        db_session,
        {**seed_demo.OPPORTUNITIES[0], "slug": "chevening-scholarships", "title": "Retired row"},
    )

    run_seed(db_session)

    assert db_session.get(Opportunity, seed_demo.stable_id("opportunity", "chevening-scholarships")) is None


def test_seed_is_idempotent_and_keeps_stable_ids(db_session):
    run_seed(db_session)
    before = {
        model: count(db_session, model) for model in (Opportunity, Requirement, Skill, User, Profile)
    }

    user = run_seed(db_session)

    after = {
        model: count(db_session, model) for model in (Opportunity, Requirement, Skill, User, Profile)
    }
    assert after == before
    assert db_session.scalar(
        select(func.count()).select_from(User).where(User.email == seed_demo.DEMO_EMAIL)
    ) == 1
    assert demo_profile(db_session, user).date_of_birth is None


def test_reseeding_replaces_existing_matches(db_session):
    user = run_seed(db_session)
    verdicts(db_session, demo_profile(db_session, user))

    user = run_seed(db_session)

    assert demo_profile(db_session, user).matches == []


def test_demo_story_covers_all_four_verdicts_then_resolves_unknowns(db_session):
    user = run_seed(db_session)
    profile = demo_profile(db_session, user)

    first = verdicts(db_session, profile)

    assert set(first.values()) == {"potential_match", "not_eligible", "needs_review"}
    assert first["github-student-developer-pack"] == "potential_match"
    assert first["nasa-ostem-internships-summer-2027"] == "not_eligible"
    # A published condition the engine cannot check keeps the verdict honest.
    assert first["cern-summer-student-programme"] == "needs_review"
    assert first["kaust-visiting-student-research-program"] == "needs_review"

    profile.date_of_birth = date(2003, 4, 18)
    profile.education[0].gpa = Decimal("3.72")
    profile.education[0].gpa_scale = Decimal("4")
    db_session.flush()
    second = verdicts(db_session, profile)

    assert second["github-student-developer-pack"] == "eligible"
    assert set(first.values()) | set(second.values()) == {
        "eligible",
        "potential_match",
        "not_eligible",
        "needs_review",
    }
    assert Counter(second.values())["potential_match"] == 0
    # Settling facts never hides a hard "no": citizenship still decides NASA.
    assert second["nasa-ostem-internships-summer-2027"] == "not_eligible"


def test_gpa_on_another_scale_is_reviewed_not_compared(db_session):
    user = run_seed(db_session)
    profile = demo_profile(db_session, user)
    profile.education[0].gpa = Decimal("8.40")
    profile.education[0].gpa_scale = Decimal("10")
    db_session.flush()
    kaust = db_session.get(
        Opportunity, seed_demo.stable_id("opportunity", "kaust-visiting-student-research-program")
    )

    match = evaluate_and_persist_match_for_user(db_session, profile, kaust.id)

    gpa_row = next(row for row in match.requirement_results if row.requirement.kind == "numeric_threshold")
    assert gpa_row.outcome == "needs_review"
    assert gpa_row.reason_code == "gpa_scale_mismatch"
