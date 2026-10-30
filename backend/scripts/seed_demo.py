"""Seed a reproducible demo dataset: real opportunities, a skill catalog and a demo user.

Run from ``backend/`` after ``alembic upgrade head``::

    python -m scripts.seed_demo                       # development: refresh everything
    DEMO_PASSWORD=... python -m scripts.seed_demo --allow-production   # production: insert missing only
    DEMO_PASSWORD=... python -m scripts.seed_demo --allow-production --demo-user-only   # reset the demo account

Every run converges on the same state (idempotent): opportunities and skills
are upserted under stable ids derived from their slug/key, and the demo
user's profile is reset to its starting point so the walkthrough can be
replayed. Nothing outside the rows listed here is touched.

Curation policy
---------------
* Every opportunity is real. Titles, hosts, URLs, dates and every
  ``source_quote`` were copied verbatim from the official page on
  ``RETRIEVED_AT``; descriptions are official sentences, quoted.
* No deadline is invented. Where the page gives no date, ``deadline_at`` is
  empty and the client tells people to check the official page.
* A condition becomes a structured rule only when the official wording maps
  exactly onto a fact the engine reads (degree level, enrolment, GPA on a
  4.0 scale, one citizenship, date of birth). Conditions the profile cannot
  answer (identity, work history, institution lists, ages at a future date)
  are kept as ``unparsed`` rules so the engine reports them as needing
  review instead of guessing.
* "At least N years old" with no reference date is checked against the
  retrieval date, and the label says so.
* Conditions published but not machine-checkable are still recorded as
  ``unparsed`` rules, so a profile is never called "eligible" while an
  official condition went unchecked.
* Quotes taken from a table are stored as ``header | cell`` so the reader can
  see they are two cells, not a sentence. A rule may cite a page other than
  the opportunity's main source; each distinct page becomes its own Source.
* Opportunities whose current cycle has closed are seeded as ``closed``: they
  stay readable by link but are not listed.
* A deadline published as a date without a time is stored at 12:00 UTC so
  its calendar date reads the same from UTC-11 to UTC+11; clients treat
  12:00 UTC as "date only" and show no time of day for it.
"""
from __future__ import annotations

import argparse
import os
import sys
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.models import (  # noqa: E402
    Education,
    Opportunity,
    Profile,
    ProfileSkill,
    Requirement,
    Skill,
    Source,
    TestScore,
    User,
)
from app.schemas import OpportunityCreate, RequirementCreate, SkillCreate  # noqa: E402

DEMO_EMAIL = "demo@example.org"
DEMO_PASSWORD_ENV = "DEMO_PASSWORD"
DEFAULT_DEMO_PASSWORD = "ohub-demo-2026"
RETRIEVED_AT = datetime(2026, 10, 30, 12, 0, tzinfo=timezone.utc)
ID_NAMESPACE = uuid.UUID("8f0d4c1e-3b7a-4c55-9a51-2f3c8b9e6d10")


def stable_id(kind: str, key: str) -> uuid.UUID:
    """Derive the same UUID for the same slug/key on every run."""
    return uuid.uuid5(ID_NAMESPACE, f"{kind}:{key}")


# --- Rule builders ----------------------------------------------------------------------------


def degree_is(level: str) -> dict:
    return {"kind": "equality", "params": {"metric": "degree_level", "operator": "==", "value": level}}


def degree_any(*levels: str) -> dict:
    return {"kind": "any_of", "params": {"any_of": [degree_is(level) for level in levels]}}


def enrolled() -> dict:
    return {"kind": "boolean_flag", "params": {"metric": "is_currently_enrolled", "expected": True}}


def gpa_at_least(value: float) -> dict:
    return {
        "kind": "numeric_threshold",
        "params": {"metric": "gpa", "operator": ">=", "value": value, "scale": 4.0},
    }


def citizen_of(country: str) -> dict:
    return {"kind": "set_membership", "params": {"metric": "citizenship", "operator": "in", "allowed": [country]}}


def citizen_not_of(country: str) -> dict:
    return {"kind": "set_membership", "params": {"metric": "citizenship", "operator": "not_in", "allowed": [country]}}


def born_on_or_before(value: date) -> dict:
    return {"kind": "date_gate", "params": {"metric": "date_of_birth", "operator": "<=", "value": value.isoformat()}}


def born_after(value: date) -> dict:
    return {"kind": "date_gate", "params": {"metric": "date_of_birth", "operator": ">", "value": value.isoformat()}}


def unparsed(reason: str) -> dict:
    return {"kind": "unparsed", "params": {"reason": reason}}


def rule(label: str, condition: dict, quote: str, category: str, source_url: str | None = None) -> dict:
    """One published condition; ``source_url`` defaults to the opportunity's main source."""
    item = {"label": label, **condition, "source_quote": quote, "category": category}
    if source_url:
        item["source_url"] = source_url
    return item


# --- Dataset ----------------------------------------------------------------------------------

OPPORTUNITIES: list[dict] = [
    {
        "slug": "cern-summer-student-programme",
        "title": "CERN Summer Student Programme",
        "opportunity_type": "internship",
        "host_name": "CERN",
        "official_url": "https://careers.cern/programmes/summer-studentship/",
        "description": (
            "Join CERN for an unforgettable summer! You’ll work on advanced scientific or "
            "technical projects, attend lectures by leading scientists, and immerse yourself in "
            "a vibrant international environment. You will gain hands-on experience that goes "
            "beyond the classroom, making this more than just a summer job—it’s a unique journey "
            "into the heart of scientific discovery."
        ),
        "deadline_type": "fixed",
        "location_mode": "onsite",
        "countries": ["CH"],
        "languages": ["en", "fr"],
        "tags": ["physics", "engineering", "computer science", "summer"],
        "publisher": "CERN Careers",
        "rules": [
            rule(
                "Pursuing a Bachelor’s or Master’s degree (not a PhD)",
                degree_any("bachelor", "master"),
                "By the start of the summer, you are pursuing a Bachelor’s or Master’s degree "
                "(not a PhD) in Physics, Engineering, Computer Science or Mathematics and have "
                "completed at least 6 semesters of full-time university studies in one of these "
                "fields.",
                "academic",
            ),
            rule(
                "Enrolled as a full-time student",
                enrolled(),
                "You remain enrolled as a full-time student at least until the start of the "
                "summer studentship.",
                "academic",
            ),
            rule(
                "At least 6 semesters of full-time study in physics, engineering, CS or maths",
                unparsed("Semesters completed and field of study are not evaluated by the engine."),
                "By the start of the summer, you are pursuing a Bachelor’s or Master’s degree "
                "(not a PhD) in Physics, Engineering, Computer Science or Mathematics and have "
                "completed at least 6 semesters of full-time university studies in one of these "
                "fields.",
                "academic",
            ),
            rule(
                "No previous CERN Summer Student Programme or CERN stint over 3 months",
                unparsed("Past CERN participation is not part of the profile."),
                "You have not worked at CERN for more than 3 months under any other status, and you "
                "have not previously participated in the Summer Student Programme at CERN.",
                "other",
            ),
        ],
    },
    {
        "slug": "kaust-visiting-student-research-program",
        "title": "KAUST Visiting Student Research Program (VSRP)",
        "opportunity_type": "research_program",
        "host_name": "King Abdullah University of Science and Technology",
        "official_url": "https://admissions.kaust.edu.sa/study/internships",
        "description": (
            "The Visiting Student Research Program (VSRP) at KAUST offers internships for 3rd and "
            "4th-year bachelor’s and master’s students in science, technology, engineering, and "
            "mathematics (STEM). With over 100 faculty-led projects, students can choose research "
            "topics that align with their interests for internships lasting 2 to 6 months."
        ),
        "deadline_type": "rolling",
        "location_mode": "onsite",
        "countries": ["SA"],
        "languages": ["en"],
        "tags": ["research", "stem", "stipend"],
        "publisher": "KAUST Admissions",
        "rules": [
            rule(
                "Bachelor’s or master’s student",
                degree_any("bachelor", "master"),
                "Undergraduate students in 3rd year or above and master’s students.",
                "academic",
            ),
            rule(
                "GPA of at least 3.5 on a 4.0 scale",
                gpa_at_least(3.5),
                "Minimum GPA: 3.5 on a 4-point scale (or equivalent).",
                "academic",
            ),
            rule(
                "Not a current KAUST student or KAUST alumnus",
                unparsed("Past or current KAUST enrolment is not part of the profile."),
                "Current PhD candidates, KAUST students or KAUST alumni are not eligible to apply.",
                "academic",
            ),
        ],
    },
    {
        "slug": "github-student-developer-pack",
        "title": "GitHub Student Developer Pack",
        "opportunity_type": "other",
        "host_name": "GitHub Education",
        "official_url": "https://education.github.com/pack",
        "description": (
            "Learn to ship software like a pro. There's no substitute for hands-on experience. "
            "But for most students, real world tools can be cost-prohibitive."
        ),
        "deadline_type": "none",
        "location_mode": "remote",
        "tags": ["developer tools", "software"],
        "publisher": "GitHub Docs",
        "source_url": (
            "https://docs.github.com/en/education/about-github-education/"
            "github-education-for-students/apply-to-github-education-as-a-student"
        ),
        "rules": [
            rule(
                "Enrolled in a degree- or diploma-granting program",
                enrolled(),
                "Are enrolled in a degree- or diploma-granting program, such as a high school, "
                "college, university, or homeschool.",
                "academic",
            ),
            rule(
                "At least 13 years old (checked as of 30 Oct 2026)",
                born_on_or_before(date(2013, 10, 30)),
                "Are at least 13 years old.",
                "demographic",
            ),
        ],
    },
    {
        "slug": "nasa-ostem-internships-summer-2027",
        "title": "NASA OSTEM Internships — Summer 2027",
        "opportunity_type": "internship",
        "host_name": "NASA",
        "official_url": "https://www.nasa.gov/learning-resources/internship-programs/",
        "description": (
            "OSTEM Internships offer short‑term, hands‑on opportunities for students to work on "
            "real NASA projects. These experiences help to build technical and professional "
            "skills while learning from NASA mentors."
        ),
        # "Summer 2027 Application Deadline: March 1, 2027 (11:59 p.m. ET)" — EST is UTC-5.
        "deadline_at": datetime(2027, 3, 2, 4, 59, tzinfo=timezone.utc),
        "deadline_type": "fixed",
        "location_mode": "onsite",
        "countries": ["US"],
        "languages": ["en"],
        "tags": ["aerospace", "space", "stem"],
        "publisher": "NASA",
        "rules": [
            # The first two quotes are a row of the page's requirements table: header | OSTEM cell.
            rule("U.S. citizen", citizen_of("US"), "Citizenship | U.S. Citizen", "demographic"),
            rule("GPA of at least 3.0 on a 4.0 scale", gpa_at_least(3.0), "GPA | 3.0 on a 4.0 scale", "academic"),
            rule(
                # Not a plain enrolment flag: recent high-school and college graduates also qualify.
                "Enrolled in an accredited program, or a recent graduate",
                unparsed("Recent graduates also qualify, and graduation timing is not evaluated."),
                "Unless a recent high school graduate, applicants must be enrolled (full-time or "
                "part-time) in a certificate or degree-granting program that is accredited by a "
                "recognized accrediting organization of the U.S. Department of Education.",
                "academic",
            ),
            rule(
                "18 or older by the session start date",
                unparsed("The session start date is not stated next to this rule."),
                "Must be 18 or older by the published start date of session",
                "demographic",
            ),
        ],
    },
    {
        "slug": "nasa-ostem-internships-fall-2027",
        "title": "NASA OSTEM Internships — Fall 2027",
        "opportunity_type": "internship",
        "host_name": "NASA",
        "official_url": "https://www.nasa.gov/learning-resources/internship-programs/",
        "description": (
            "OSTEM Internships offer short‑term, hands‑on opportunities for students to work on "
            "real NASA projects. These experiences help to build technical and professional "
            "skills while learning from NASA mentors."
        ),
        # "Fall 2027 Application Deadline: May 24, 2027 (11:59 p.m. ET)" — EDT is UTC-4.
        "deadline_at": datetime(2027, 5, 25, 3, 59, tzinfo=timezone.utc),
        "deadline_type": "fixed",
        "location_mode": "onsite",
        "countries": ["US"],
        "languages": ["en"],
        "tags": ["aerospace", "space", "stem"],
        "publisher": "NASA",
        "rules": [
            # The first two quotes are a row of the page's requirements table: header | OSTEM cell.
            rule("U.S. citizen", citizen_of("US"), "Citizenship | U.S. Citizen", "demographic"),
            rule("GPA of at least 3.0 on a 4.0 scale", gpa_at_least(3.0), "GPA | 3.0 on a 4.0 scale", "academic"),
            rule(
                # Not a plain enrolment flag: recent high-school and college graduates also qualify.
                "Enrolled in an accredited program, or a recent graduate",
                unparsed("Recent graduates also qualify, and graduation timing is not evaluated."),
                "Unless a recent high school graduate, applicants must be enrolled (full-time or "
                "part-time) in a certificate or degree-granting program that is accredited by a "
                "recognized accrediting organization of the U.S. Department of Education.",
                "academic",
            ),
            rule(
                "18 or older by the session start date",
                unparsed("The session start date is not stated next to this rule."),
                "Must be 18 or older by the published start date of session",
                "demographic",
            ),
        ],
    },
    {
        "slug": "amelia-earhart-fellowship-2027",
        "title": "Amelia Earhart Fellowship 2027",
        "opportunity_type": "fellowship",
        "host_name": "Zonta International",
        "official_url": "https://www.zonta.org/Web/Programs/Education/Amelia_Earhart_Fellowship",
        "description": (
            "Established in 1938 in honor of famed aviator and Zontian Amelia Earhart, the Amelia "
            "Earhart Fellowship supports women pursuing Ph.D./doctoral degrees in aerospace "
            "engineering and space sciences. Up to 30 Fellows will receive a US$12,000 Amelia "
            "Earhart Fellowship to support their advanced studies at any university or college "
            "offering accredited post-graduate courses and degrees in these fields."
        ),
        # "must be submitted in full by 15 November 2026" — no time of day is given,
        # so store noon UTC: the calendar date then reads 15 Nov from UTC-11 to UTC+11.
        "deadline_at": datetime(2026, 11, 15, 12, 0, tzinfo=timezone.utc),
        "deadline_type": "fixed",
        "location_mode": "unknown",
        "languages": ["en"],
        "tags": ["aerospace", "space science", "doctoral"],
        "publisher": "Zonta International",
        "rules": [
            rule(
                "Pursuing a Ph.D./doctoral degree",
                degree_is("doctorate"),
                "Women of any nationality pursuing a Ph.D./doctoral degree who demonstrate a "
                "superior academic record conducting research applied to aerospace engineering or "
                "space sciences are eligible.",
                "academic",
            ),
            rule(
                "Open to women",
                unparsed("Gender is not part of the profile, so this cannot be checked."),
                "Women of any nationality pursuing a Ph.D./doctoral degree who demonstrate a "
                "superior academic record conducting research applied to aerospace engineering or "
                "space sciences are eligible.",
                "demographic",
            ),
        ],
    },
    {
        "slug": "google-summer-of-code",
        "title": "Google Summer of Code",
        "opportunity_type": "open_source_program",
        "host_name": "Google",
        "official_url": "https://developers.google.com/open-source/gsoc/faq",
        "description": (
            "To be eligible, contributors must be at least 18 years old, reside in a non-embargoed "
            "country, and have limited prior open source experience, while organizations must "
            "have an active open source project and at least two mentors."
        ),
        "deadline_type": "fixed",
        "location_mode": "remote",
        "languages": ["en"],
        "tags": ["open source", "software", "stipend"],
        "publisher": "Google for Developers",
        "rules": [
            rule(
                "18 or older at registration",
                unparsed("The registration date is set by the yearly timeline, not stated here."),
                "18+ years old at registration",
                "demographic",
            ),
        ],
    },
    {
        "slug": "schwarzman-scholars-2028-2029",
        "title": "Schwarzman Scholars — Class of 2028–2029",
        "opportunity_type": "scholarship",
        "host_name": "Schwarzman Scholars",
        "official_url": "https://www.schwarzmanscholars.org/admissions/eligibility/",
        "description": (
            "Schwarzman Scholars are selected from an international pool of distinguished "
            "candidates. Prospective Scholars are expected to demonstrate academic excellence, "
            "exceptional results in their field and outstanding leadership qualities."
        ),
        "deadline_type": "fixed",
        "location_mode": "onsite",
        "countries": ["CN"],
        "languages": ["en"],
        "tags": ["leadership", "master's", "fully funded"],
        "publisher": "Schwarzman Scholars",
        "rules": [
            rule(
                "At least 18 on 1 Aug 2028",
                born_on_or_before(date(2010, 8, 1)),
                "Candidates must be at least 18 but not yet 29 years of age as of August 1 of their "
                "Schwarzman Scholars enrollment year (for the Class of 2028-2029, as of August 1, "
                "2028).",
                "demographic",
            ),
            rule(
                "Not yet 29 on 1 Aug 2028",
                born_after(date(1999, 8, 1)),
                "Candidates must be at least 18 but not yet 29 years of age as of August 1 of their "
                "Schwarzman Scholars enrollment year (for the Class of 2028-2029, as of August 1, "
                "2028).",
                "demographic",
            ),
            rule(
                "Undergraduate degree completed by 1 Aug of the enrollment year",
                unparsed("Expected graduation date is not evaluated by the engine."),
                "Applicants who are currently enrolled in undergraduate degree programs must be on "
                "track to successfully complete all degree requirements before August 1 of their "
                "Schwarzman Scholars enrollment year.",
                "academic",
            ),
        ],
    },
    {
        "slug": "brooke-owens-fellowship-2027",
        # "CLASS OF 2027 APPLICATION NOW CLOSED" on the apply page.
        "status": "closed",
        "title": "Brooke Owens Fellowship — Class of 2027",
        "opportunity_type": "fellowship",
        "host_name": "Brooke Owens Fellowship",
        "official_url": "https://www.brookeowensfellowship.org/apply",
        "description": (
            "The Brooke Owens Fellowship is committed to expanding opportunities for women and "
            "gender minorities in aerospace."
        ),
        "deadline_type": "fixed",
        "location_mode": "unknown",
        "languages": ["en"],
        "tags": ["aerospace", "mentorship", "undergraduate"],
        "publisher": "Brooke Owens Fellowship",
        "rules": [
            rule(
                "Undergraduate working toward a bachelor’s or associate degree",
                degree_any("bachelor", "associate"),
                "I am an undergraduate student who has completed at least one year of coursework "
                "toward a bachelor’s or associate degree.",
                "academic",
            ),
            rule(
                "18 or older (checked as of 30 Oct 2026)",
                born_on_or_before(date(2008, 10, 30)),
                "I am 18 years of age or older.",
                "demographic",
            ),
            rule(
                "Identifies as a woman or gender minority",
                unparsed("Gender identity is not part of the profile, so this cannot be checked."),
                "I identify as a woman or gender minority.",
                "demographic",
            ),
        ],
    },
    {
        "slug": "mitacs-globalink-research-internship-2027",
        # "...call for Summer 2027 student applications has now concluded".
        "status": "closed",
        "title": "Mitacs Globalink Research Internship 2027",
        "opportunity_type": "internship",
        "host_name": "Mitacs",
        "official_url": "https://www.mitacs.ca/our-programs/globalink-research-internship-students/",
        "description": (
            "Mitacs Globalink Research Internship is a competitive initiative for international "
            "undergraduates from the following countries and regions: Austria, Brazil, Chile, "
            "China, Colombia, Finland, France, Germany, Hong Kong, India, Ireland, Jordan, Mexico, "
            "Pakistan, Peru, Singapore, South Korea, Taiwan, Thailand, Tunisia, Ukraine, United "
            "Kingdom and the United States."
        ),
        "deadline_type": "fixed",
        "location_mode": "onsite",
        "countries": ["CA"],
        "languages": ["en", "fr"],
        "tags": ["research", "undergraduate", "canada"],
        "publisher": "Mitacs",
        "rules": [
            rule(
                "Enrolled in a full-time program",
                enrolled(),
                "Be enrolled in a full-time undergraduate or combined undergraduate/master’s "
                "program at an eligible institution (see list of eligible institutions by country)",
                "academic",
            ),
            rule(
                # Combined undergraduate/master's students may record either level.
                "Undergraduate or combined undergraduate/master’s student",
                degree_any("bachelor", "master"),
                "Be enrolled in a full-time undergraduate or combined undergraduate/master’s "
                "program at an eligible institution (see list of eligible institutions by country)",
                "academic",
            ),
            rule(
                "Studying at an eligible partner institution",
                unparsed("Eligibility depends on the institution's country, which the profile does not record."),
                "Be enrolled in a full-time undergraduate or combined undergraduate/master’s "
                "program at an eligible institution (see list of eligible institutions by country)",
                "logistics",
            ),
        ],
    },
    {
        "slug": "gates-cambridge-scholarship",
        "title": "Gates Cambridge Scholarship",
        "opportunity_type": "scholarship",
        "host_name": "Gates Cambridge Trust",
        "official_url": "https://www.gatescambridge.org/apply/eligibility/",
        # The page's eligibility list, one item per line.
        "description": (
            "You can apply for a Gates Cambridge Scholarship if you are:\n"
            "a citizen of any country outside the United Kingdom\n"
            "applying to pursue one of the following courses at the University of Cambridge:\n"
            "PhD (full-time or part-time*)\n"
            "MLitt (full-time)\n"
            "one-year postgraduate course (full-time), with some exceptions – see below."
        ),
        "deadline_type": "fixed",
        "location_mode": "onsite",
        "countries": ["GB"],
        "languages": ["en"],
        "tags": ["postgraduate", "phd", "fully funded"],
        "publisher": "Gates Cambridge Trust",
        "rules": [
            rule(
                "Citizen of a country outside the United Kingdom",
                citizen_not_of("GB"),
                "a citizen of any country outside the United Kingdom",
                "demographic",
            ),
            rule(
                "Applying for a PhD, MLitt or one-year postgraduate course at Cambridge",
                unparsed("The course being applied to is not part of the profile."),
                "applying to pursue one of the following courses at the University of Cambridge:",
                "academic",
            ),
        ],
    },
    {
        "slug": "summer-at-epfl-2027",
        "title": "Summer@EPFL 2027",
        "opportunity_type": "research_program",
        "host_name": "EPFL School of Computer and Communication Sciences",
        "official_url": "https://summer.epfl.ch/",
        "description": (
            "The School of Computer and Communication Sciences of the École polytechnique fédérale "
            "de Lausanne (EPFL) offers summer fellowships to international students. Participants "
            "get the chance to learn new skills and to gain hands-on experience in their chosen "
            "field while collaborating with leading senior scientists."
        ),
        # "Next Deadline: 29th November 2026" (Anywhere on Earth) — no time of day: noon UTC.
        "deadline_at": datetime(2026, 11, 29, 12, 0, tzinfo=timezone.utc),
        "deadline_type": "fixed",
        "location_mode": "onsite",
        "countries": ["CH"],
        "languages": ["en"],
        "tags": ["computer science", "research", "summer"],
        "publisher": "EPFL",
        "rules": [
            rule(
                "Bachelor’s or master’s student",
                degree_any("bachelor", "master"),
                "Fellowships are awarded to students enrolled in BSc, BTech, MSc, MTech, or "
                "equivalent programmes in Computer Science, Computer Engineering, "
                "Telecommunications, or Electrical Engineering.",
                "academic",
            ),
            rule(
                "Studying computer science, computer engineering, telecoms or electrical engineering",
                unparsed("Field of study is not evaluated by the engine."),
                "Fellowships are awarded to students enrolled in BSc, BTech, MSc, MTech, or "
                "equivalent programmes in Computer Science, Computer Engineering, "
                "Telecommunications, or Electrical Engineering.",
                "academic",
            ),
            rule(
                "Currently enrolled",
                enrolled(),
                "At the time of application, applicants must be enrolled in the 2nd year Bachelor or "
                "above (therefore, all applicants must have successfully completed at least their "
                "1st year of the Bachelor's programme).",
                "academic",
            ),
            rule(
                "In the 2nd year of a bachelor’s or above",
                unparsed("Year of study is not evaluated by the engine."),
                "At the time of application, applicants must be enrolled in the 2nd year Bachelor or "
                "above (therefore, all applicants must have successfully completed at least their "
                "1st year of the Bachelor's programme).",
                "academic",
            ),
        ],
    },
    {
        "slug": "eth-student-summer-research-fellowship-2027",
        "title": "ETH Student Summer Research Fellowship 2027",
        "opportunity_type": "research_program",
        "host_name": "ETH Zurich, Department of Computer Science",
        "official_url": "https://inf.ethz.ch/studies/summer-research-fellowship.html",
        "source_url": "https://inf.ethz.ch/studies/summer-research-fellowship/how-to-apply.html",
        "description": (
            "The ETH Student Summer Research Fellowship (ETH SSRF) programme offers undergraduate "
            "and graduate students the opportunity to gain their first research experience in an "
            "area of their choice."
        ),
        # "1st November – 16 December 2026 at 13:00 (Central European Time)" — CET is UTC+1.
        "deadline_at": datetime(2026, 12, 16, 12, 0, tzinfo=timezone.utc),
        "deadline_type": "fixed",
        "location_mode": "onsite",
        "countries": ["CH"],
        "languages": ["en"],
        "tags": ["computer science", "research", "summer"],
        "publisher": "ETH Zurich",
        "rules": [
            rule(
                "Enrolled in a study programme",
                enrolled(),
                "You are enrolled in a study programme (bachelor or master) in computer science or a "
                "closely related field (e.g., electrical engineering, mathematics, physics)",
                "academic",
            ),
            rule(
                "Bachelor’s or master’s student",
                degree_any("bachelor", "master"),
                "You are enrolled in a study programme (bachelor or master) in computer science or a "
                "closely related field (e.g., electrical engineering, mathematics, physics)",
                "academic",
            ),
            rule(
                "Studying computer science or a closely related field",
                unparsed("Field of study is not evaluated by the engine."),
                "You are enrolled in a study programme (bachelor or master) in computer science or a "
                "closely related field (e.g., electrical engineering, mathematics, physics)",
                "academic",
            ),
            rule(
                "Two years of study completed by the programme start",
                unparsed("Years of study completed are not evaluated by the engine."),
                "You will have completed two years of study by start of the programme (master "
                "students naturally satisfy this condition)",
                "academic",
            ),
            rule(
                "Not enrolled at ETH Zurich",
                unparsed("The profile's institution is not evaluated by the engine."),
                "is open to all students worldwide, except for students enrolled at ETH Zurich.",
                "academic",
                source_url="https://inf.ethz.ch/studies/summer-research-fellowship.html",
            ),
        ],
    },
    {
        "slug": "kaust-masters-fellowship-fall-2027",
        "title": "KAUST Master’s Degree with the KAUST Fellowship — Fall 2027",
        "opportunity_type": "scholarship",
        "host_name": "King Abdullah University of Science and Technology",
        "official_url": "https://admissions.kaust.edu.sa/study/master's-degree",
        "source_url": "https://admissions.kaust.edu.sa/how-to-apply/entry-requirements",
        "description": (
            "The cost of our Master’s program reflects the world-class education and advanced "
            "academic environment at KAUST. However, all admitted master’s students* receive the "
            "fully-funded KAUST Fellowship, which covers tuition fees, housing, health insurance, "
            "relocation support, and more.\n"
            "*Some students with external sponsorship or funding may not be eligible for the KAUST "
            "Fellowship"
        ),
        # "Round 2 application deadline 3 January 2027"; the timeline page calls its dates
        # "tentative". No time of day is given, so noon UTC.
        "deadline_at": datetime(2027, 1, 3, 12, 0, tzinfo=timezone.utc),
        "deadline_type": "fixed",
        "location_mode": "onsite",
        "countries": ["SA"],
        "languages": ["en"],
        "tags": ["master's", "fully funded", "stem"],
        "publisher": "KAUST Admissions",
        "rules": [
            rule(
                "Bachelor’s degree in a relevant subject before entry",
                # The profile records current studies, not completed degrees.
                unparsed("Completed degrees and their subject are not evaluated by the engine."),
                "Bachelors degree in a subject relevant the program being applied to, from a "
                "recognized higher education institution for entry into our Masters programs",
                "academic",
            ),
            rule(
                "GPA of at least 3.0 on a 4.0 scale",
                gpa_at_least(3.0),
                "The minimum permitted GPA is 3.0 on a 4-point scale (or equivalent).",
                "academic",
            ),
            rule(
                # "Fall semester starts 29 August 2027" on the admission timeline.
                "At least 18 on entry (29 Aug 2027)",
                born_on_or_before(date(2009, 8, 29)),
                "At least 18 years of age on entry",
                "demographic",
            ),
        ],
    },
]

#: Slugs earlier versions of this script seeded and no longer ship; removed on every run.
#: Chevening's page could not be fetched byte-exact to re-verify its quotes.
RETIRED_SLUGS: list[str] = ["chevening-scholarships"]

SKILLS: list[tuple[str, str]] = [
    ("python", "Python"),
    ("matlab", "MATLAB"),
    ("c", "C"),
    ("cpp", "C++"),
    ("rust", "Rust"),
    ("javascript", "JavaScript"),
    ("typescript", "TypeScript"),
    ("sql", "SQL"),
    ("git", "Git"),
    ("linux", "Linux"),
    ("machine-learning", "Machine learning"),
    ("data-analysis", "Data analysis"),
    ("cad", "CAD"),
    ("solidworks", "SolidWorks"),
    ("cfd", "Computational fluid dynamics"),
    ("finite-element-analysis", "Finite element analysis"),
    ("orbital-mechanics", "Orbital mechanics"),
    ("embedded-systems", "Embedded systems"),
    ("ros", "ROS"),
    ("technical-writing", "Technical writing"),
]

DEMO_SKILLS = ["python", "matlab", "cad", "git"]


# --- Upserts ----------------------------------------------------------------------------------


def upsert_skills(session) -> dict[str, Skill]:
    skills = {}
    for key, name in SKILLS:
        SkillCreate(key=key, name=name)  # validate the key format up front
        skill = session.get(Skill, stable_id("skill", key)) or session.scalar(
            select(Skill).where(Skill.key == key)
        )
        if skill is None:
            skill = Skill(id=stable_id("skill", key), key=key)
            session.add(skill)
        skill.name = name
        skills[key] = skill
    session.flush()
    return skills


def upsert_opportunity(session, spec: dict) -> Opportunity:
    """Replace one opportunity wholesale under its stable id.

    Deleting through the ORM removes its matches (and their evidence) before
    the database cascade drops requirements and sources, so re-seeding never
    trips the evidence RESTRICT constraint.
    """
    spec = dict(spec)
    rules = [dict(item) for item in spec.pop("rules")]
    status = spec.pop("status", "published")
    publisher = spec.pop("publisher")
    source_url = spec.pop("source_url", spec["official_url"])
    opportunity_id = stable_id("opportunity", spec["slug"])

    existing = session.get(Opportunity, opportunity_id) or session.scalar(
        select(Opportunity).where(Opportunity.slug == spec["slug"])
    )
    if existing is not None:
        session.delete(existing)
        session.flush()

    payload = OpportunityCreate(status=status, published_at=RETRIEVED_AT, **spec)
    opportunity = Opportunity(id=opportunity_id, **payload.model_dump())
    session.add(opportunity)
    sources: dict[str, Source] = {}
    for url in dict.fromkeys([source_url, *(item.get("source_url", source_url) for item in rules)]):
        sources[url] = Source(
            opportunity=opportunity,
            source_type="official_page",
            url=url,
            publisher=publisher,
            retrieved_at=RETRIEVED_AT,
            is_primary=url == source_url,
            raw_snapshot={
                "quotes": sorted(
                    {item["source_quote"] for item in rules if item.get("source_url", source_url) == url}
                )
            },
            notes="Quotes copied verbatim from the official page on the retrieval date.",
        )
    session.add_all(sources.values())
    session.flush()
    for index, item in enumerate(rules):
        source = sources[item.pop("source_url", source_url)]
        requirement = Requirement(
            **RequirementCreate(order_index=index, source_id=source.id, **item).model_dump()
        )
        requirement.opportunity = opportunity
        session.add(requirement)
    session.flush()
    return opportunity


def retire_opportunities(session) -> None:
    """Delete opportunities that earlier runs seeded but the dataset no longer contains."""
    for slug in RETIRED_SLUGS:
        existing = session.get(Opportunity, stable_id("opportunity", slug))
        if existing is not None:
            session.delete(existing)
    session.flush()


def reset_demo_user(session, skills: dict[str, Skill], password: str) -> User:
    """Create or reset the demo account to the walkthrough's starting point.

    The profile deliberately lacks a date of birth and a GPA, so the first
    eligibility check leaves some opportunities undecided and the demo can
    show those facts being added.
    """
    user = session.scalar(select(User).where(User.email == DEMO_EMAIL))
    if user is None:
        user = User(email=DEMO_EMAIL, password_hash=hash_password(password))
        session.add(user)
    else:
        user.password_hash = hash_password(password)
        user.is_active = True
    session.flush()

    existing = session.scalar(select(Profile).where(Profile.user_id == user.id))
    if existing is not None:
        session.delete(existing)
        session.flush()

    profile = Profile(
        user_id=user.id,
        full_name="Mekdes Tadesse",
        email=DEMO_EMAIL,
        citizenships=["ET"],
        country_of_residence="ET",
        degree_level="bachelor",
        is_currently_enrolled=True,
        languages=["am", "en"],
        interests=["aerospace engineering", "flight software", "open source", "robotics"],
        bio=(
            "Aerospace engineering student interested in satellite systems and reliable "
            "software for flight projects."
        ),
    )
    profile.education.append(
        Education(
            institution_name="Addis Ababa University",
            degree_level="bachelor",
            field_of_study="Aerospace Engineering",
            country="ET",
            start_date=date(2023, 10, 1),
            is_current=True,
            is_primary=True,
        )
    )
    profile.test_scores.append(
        TestScore(test_type="IELTS Academic", overall_score=7.5, test_date=date(2025, 6, 14))
    )
    session.add(profile)
    session.flush()
    for key in DEMO_SKILLS:
        session.add(ProfileSkill(profile_id=profile.id, skill_id=skills[key].id))
    session.flush()
    return user


#: A production demo password must be set explicitly and be at least this long.
MIN_PRODUCTION_DEMO_PASSWORD = 12


def seed(session, *, password: str, production: bool = False, demo_user_only: bool = False) -> dict[str, int]:
    """Apply the demo dataset; returns counts of what changed.

    Development refreshes every seeded opportunity in place (replacing it
    wholesale, which also drops matches made against it) so the walkthrough
    always starts from the curated rules. Production never deletes anything a
    real user created: it only inserts opportunities and skills that don't
    exist yet, and resets the demo account itself. ``demo_user_only`` touches
    nothing but the demo account (the recovery path).
    """
    counts = {"opportunities_created": 0, "opportunities_refreshed": 0}
    skills = upsert_skills(session)
    if not demo_user_only:
        for spec in OPPORTUNITIES:
            exists = session.get(Opportunity, stable_id("opportunity", spec["slug"])) is not None
            if production and exists:
                continue
            upsert_opportunity(session, spec)
            counts["opportunities_refreshed" if exists else "opportunities_created"] += 1
        if not production:
            retire_opportunities(session)
    reset_demo_user(session, skills, password)
    return counts


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Seed the Opportunity Hub demo dataset.")
    parser.add_argument(
        "--allow-production",
        action="store_true",
        help="Required when APP_ENV is production. Inserts missing records only and needs $DEMO_PASSWORD.",
    )
    parser.add_argument(
        "--demo-user-only",
        action="store_true",
        help="Reset only the demo account (profile, education, skills, matches) to its starting point.",
    )
    args = parser.parse_args(argv)

    production = settings.is_production
    if production and not args.allow_production:
        raise SystemExit("Refusing to seed when APP_ENV is production without --allow-production.")
    password = os.environ.get(DEMO_PASSWORD_ENV)
    if production and (not password or password == DEFAULT_DEMO_PASSWORD or len(password) < MIN_PRODUCTION_DEMO_PASSWORD):
        raise SystemExit(
            f"Set ${DEMO_PASSWORD_ENV} to a private value of at least {MIN_PRODUCTION_DEMO_PASSWORD} characters "
            "(not the development default) to seed production."
        )

    with SessionLocal.begin() as session:
        counts = seed(session, password=password or DEFAULT_DEMO_PASSWORD, production=production, demo_user_only=args.demo_user_only)

    listed = sum(1 for spec in OPPORTUNITIES if spec.get("status", "published") == "published")
    if args.demo_user_only:
        print("Reset the demo account only.")
    else:
        print(
            f"Opportunities: {counts['opportunities_created']} created, {counts['opportunities_refreshed']} refreshed "
            f"({len(OPPORTUNITIES)} in the dataset, {listed} listed). Skills: {len(SKILLS)}."
        )
    print(f"Demo account: {DEMO_EMAIL} (password from ${DEMO_PASSWORD_ENV}{'' if production else ' or the development default'})")


if __name__ == "__main__":
    main()
