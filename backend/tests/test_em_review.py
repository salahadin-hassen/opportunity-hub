"""The Erasmus Mundus evidence standard, on real quotes from programme pages (spot-check findings included)."""
from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from app.intelligence.em_review import assess, scholarship_evidence

TODAY = date(2026, 11, 15)


def candidate(text, *, deadline=None, deadline_quote=None, rolling=False, eligibility=()):
    extraction = {"eligibility": {"status": "explicit", "value": list(eligibility)} if eligibility else {"status": "not_found"}}
    if deadline:
        extraction["deadline"] = {"status": "explicit", "value": deadline, "evidence": [{"quote": deadline_quote, "location": "text"}]}
    if rolling:
        extraction["deadline_type"] = {"status": "explicit", "value": "rolling"}
    return SimpleNamespace(id="c1", url="https://example.edu/apply", final_url=None, page_text=text, extraction=extraction)


CYBERSURE = ("CYBERSURE is a prestigious Erasmus Mundus Joint Master Degree programme offering full scholarships and partial "
             "scholarships to exceptional candidates from around the world.\n●Final deadline: January 18, 2027\n"
             "In Computer Science, Information Technology, or related field\nTOEFL, IELTS, or equivalent certification required")


def test_a_page_with_all_three_meets_the_standard():
    a = assess(candidate(CYBERSURE, deadline="2027-01-18", deadline_quote="●Final deadline: January 18, 2027",
                         eligibility=["In Computer Science, Information Technology, or related field",
                                      "TOEFL, IELTS, or equivalent certification required"]), today=TODAY)
    assert a.approvable and a.reasons == []
    assert a.scholarship_quote.startswith("CYBERSURE is a prestigious") and a.deadline == "2027-01-18"


def test_a_document_rule_mentioning_a_scholarship_is_not_availability():
    quote = ("The document must have been issued within 12 months before the submission deadline of applying for "
             "an EMJM student scholarship.")
    assert scholarship_evidence(quote) == (None, None)


def test_funding_not_yet_secured_is_not_availability():
    quote = ("The COASTHazar programme will apply for a grant renewal in 2027 to secure funding for a new set of "
             "Erasmus Mundus scholarships accross 4 cohorts (2028 - 2033).")
    available, negation = scholarship_evidence(quote)
    assert negation == quote


def test_a_deadline_for_self_funded_places_is_not_the_scholarship_deadline():
    text = ("Applicants for Edition 14 can apply for an Erasmus Mundus scholarship, which provides funding to selected students.\n"
            "Applications for fee-paying self-funded study places remain open longer, with a final deadline of: 15 July 2027.\n"
            "Applicants should have a first degree in a relevant field.")
    a = assess(candidate(text, deadline="2027-07-15",
                         deadline_quote="Applications for fee-paying self-funded study places remain open longer, with a final deadline of: 15 July 2027.",
                         eligibility=["Applicants should have a first degree in a relevant field."]), today=TODAY)
    assert not a.approvable and any("without a scholarship" in r for r in a.reasons)


def test_rolling_admission_for_non_scholarship_candidates_does_not_count():
    text = ("Erasmus Mundus Scholarship: A scholarship for eligible candidates that provides financial support.\n"
            "The March to May application period is specifically for European candidates, who can apply on a "
            "non-scholarship basis on a rolling admission procedure.\nApplicants must hold a bachelor's degree.")
    a = assess(candidate(text, rolling=True, eligibility=["Applicants must hold a bachelor's degree."]), today=TODAY)
    assert not a.approvable and any("no specific future deadline" in r for r in a.reasons)


def test_a_programme_description_is_not_an_eligibility_condition():
    text = ("From Septembre 2022, the ChEMoinformaticsPlus program offers about 20 Erasmus Mundus scholarships and 25 places per edition.\n"
            "Applications are open until March 15, 2027 !\n"
            "“Chemicals are at the centre of the economy (energy, materials, agrochemicals, pharmaceuticals...) and ... they must be adapted to achieve a sustainable future.")
    a = assess(candidate(text, deadline="2027-03-15", deadline_quote="Applications are open until March 15, 2027 !",
                         eligibility=["“Chemicals are at the centre of the economy (energy, materials, agrochemicals, pharmaceuticals...) and ... they must be adapted to achieve a sustainable future."]),
               today=TODAY)
    assert not a.approvable and a.reasons == ["no eligibility condition quoted from the page"]


def test_a_passed_deadline_and_a_page_saying_no_scholarships_are_refused():
    text = "There are no Erasmus Mundus scholarships for the 2027 intake.\nDeadline: 15 January 2026\nApplicants must hold a degree."
    a = assess(candidate(text, deadline="2026-01-15", deadline_quote="Deadline: 15 January 2026",
                         eligibility=["Applicants must hold a degree."]), today=TODAY)
    assert not a.approvable
    assert any("not available" in r for r in a.reasons) and any("has passed" in r for r in a.reasons)
