"""Unit tests for the Erasmus Mundus review and evidence standard."""
from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace

from app.intelligence.em_review import (
    REVIEW_BASIS,
    STANDARD,
    assess,
    evidence_record,
    page_mentions_programme,
    scholarship_evidence,
)


def test_scholarship_evidence_detection():
    # Availability quote detected
    text = (
        "Welcome to the Master programme. "
        "Selected applicants can receive an Erasmus Mundus scholarship covering all study fees. "
        "Classes begin in October."
    )
    avail, neg = scholarship_evidence(text)
    assert avail is not None
    assert "Erasmus Mundus scholarship" in avail
    assert neg is None

    # Negation detected
    neg_text = (
        "Welcome to the programme. "
        "There are no Erasmus Mundus scholarships available for this intake. "
        "Self-funded students only."
    )
    avail, neg = scholarship_evidence(neg_text)
    assert neg is not None
    assert "no Erasmus Mundus scholarships" in neg


def test_assess_approvable_candidate():
    today = date(2026, 11, 15)
    page_text = (
        "The International Master in AI is an Erasmus Mundus Joint Master. "
        "Candidates can apply for an Erasmus Mundus scholarship to fund their studies. "
        "Applications close on 2027-03-31 for the next intake. "
        "Applicants must hold a Bachelor of Science in Computer Science or equivalent."
    )
    cand = SimpleNamespace(
        id="c1",
        url="https://master-ai.eu/apply",
        final_url="https://master-ai.eu/apply",
        page_text=page_text,
        extraction={
            "deadline": {
                "status": "explicit",
                "value": "2027-03-31T23:59:00",
                "evidence": [{"quote": "Applications close on 2027-03-31 for the next intake.", "location": "text"}],
            },
            "deadline_type": {"value": "fixed"},
            "eligibility": {
                "status": "explicit",
                "value": ["Applicants must hold a Bachelor of Science in Computer Science or equivalent."],
            },
        },
    )
    assessment = assess(cand, today=today)
    assert assessment.approvable is True
    assert assessment.deadline == "2027-03-31"
    assert assessment.deadline_type == "fixed"
    assert assessment.scholarship_quote is not None
    assert len(assessment.eligibility_quotes) == 1

    rec = evidence_record(assessment, catalogue_title="International Master in AI", checked_at=datetime.now(timezone.utc))
    assert rec["standard"] == STANDARD
    assert rec["review_basis"] == REVIEW_BASIS
    assert rec["catalogue_title"] == "International Master in AI"
    assert rec["deadline"] == "2027-03-31"


def test_assess_rejects_expired_deadline():
    today = date(2026, 11, 15)
    page_text = (
        "Erasmus Mundus scholarships are available for successful applicants. "
        "Application deadline was 2026-01-15. "
        "Must hold an undergraduate degree."
    )
    cand = SimpleNamespace(
        id="c2",
        url="https://example.eu",
        final_url="https://example.eu",
        page_text=page_text,
        extraction={
            "deadline": {
                "status": "explicit",
                "value": "2026-01-15T23:59:00",
                "evidence": [{"quote": "Application deadline was 2026-01-15.", "location": "text"}],
            },
            "deadline_type": {"value": "fixed"},
            "eligibility": {"status": "explicit", "value": ["Must hold an undergraduate degree."]},
        },
    )
    assessment = assess(cand, today=today)
    assert assessment.approvable is False
    assert any("passed" in r for r in assessment.reasons)


def test_page_mentions_programme():
    assert page_mentions_programme("Welcome to the Master in Marine Biology website", "Master in Marine Biology")
    assert not page_mentions_programme("Welcome to the Master in Marine Biology website", "Master in Robotics")
