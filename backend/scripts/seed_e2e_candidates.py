"""Ingestion candidates for the Playwright curator spec, in a throwaway end-to-end database only.

Called by ``scripts.seed_e2e_fixtures`` after its target check. Nothing is fetched: the pages are the
strings below, served by an in-memory reader, and they go through the real code path a production
source takes (register → test → terms review → approve → discover → process), so the candidates,
their evidence quotes, hashes and validation are exactly what the pipeline produces.

Every run starts clean: the fixture source, its candidates and any opportunity a previous run created
from them are removed first. Deadlines are relative to today so the fixtures do not go stale.
"""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.intelligence import pipeline, registry
from app.intelligence.connectors.base import PageContent
from app.intelligence.definitions import SourceDefinition
from app.intelligence.reader import HTTPStatusError
from app.intelligence.source_test import run_source_test
from app.models import AcquisitionSource, IngestionCandidate, Opportunity, User
from app.models.enums import RobotsStatus, SourceStatus, TermsStatus

SOURCE_NAME = "E2E Fixture Institute"
HOST = "www.e2e-fixture-institute.edu"
BASE = f"https://{HOST}"
FELLOWSHIP = "E2E Marine Science Fellowship"
SUMMER_SCHOOL = "E2E Robotics Summer School"
SCHOLARSHIP = "E2E Heritage Scholarship"


def _long(day: date) -> str:
    return f"{day.day} {day:%B %Y}"


def _page(title: str, deadline: date, rules: list[str], *, about: str) -> bytes:
    items = "".join(f"<li>{rule}</li>" for rule in rules)
    return f"""<html><head><title>{title} | E2E Fixture Institute</title></head><body><main>
    <h1>{title}</h1>
    <p>The E2E Fixture Institute {title} {about}</p>
    <h2>Eligibility</h2><ul>{items}</ul>
    <h2>Funding</h2><p>Participants receive a stipend of EUR 4,000 and free accommodation.</p>
    <h2>How to apply</h2><p>Submit your CV and transcripts through the application portal.</p>
    <p>Application deadline: {_long(deadline)}.</p></main></body></html>""".encode()


def pages(today: date) -> dict[str, bytes]:
    upcoming, later, past = today + timedelta(days=120), today + timedelta(days=150), today - timedelta(days=45)
    fellowship = _page(
        FELLOWSHIP, upcoming,
        ["Applicants must hold a bachelor's degree in marine biology, oceanography or a related field.",
         "Applicants must be available for the full twelve months of the fellowship."],
        about="supports early-career researchers for twelve months of supervised research at sea.",
    )
    return {
        f"{BASE}/fellowships/marine-science": fellowship,
        # The same call published a second time under another address: the pipeline marks it duplicate.
        f"{BASE}/news/marine-science-fellowship-call": fellowship,
        f"{BASE}/summer-schools/robotics": _page(
            SUMMER_SCHOOL, later,
            ["Applicants must be enrolled in a master's programme in engineering or computer science.",
             "Applicants must have completed an introductory course in control systems."],
            about="brings forty students together for three weeks of hands-on robotics.",
        ),
        f"{BASE}/scholarships/heritage": _page(
            SCHOLARSHIP, past,
            ["Applicants must be enrolled in a bachelor's programme in history or archaeology."],
            about="supports undergraduates studying cultural heritage for one academic year.",
        ),
    }


class _FixtureReader:
    """An in-memory ``PageReader``: serves only the fixture pages; anything else is a 404."""

    def __init__(self, served: dict[str, bytes]) -> None:
        self._served = served
        self.robots_status = {HOST: RobotsStatus.ALLOWED}

    def allowed_by_robots(self, url: str) -> bool:
        return True

    def read(self, url: str) -> PageContent:
        body = self._served.get(url)
        if body is None:
            raise HTTPStatusError(404, url)
        return PageContent(url=url, final_url=url, status_code=200, content_type="text/html", body=body)


def _remove_previous(session: Session) -> None:
    source = session.scalar(select(AcquisitionSource).where(AcquisitionSource.name == SOURCE_NAME))
    stale = list(session.scalars(select(Opportunity).where(Opportunity.official_url.like(f"{BASE}/%"))))
    for opportunity in stale:
        session.delete(opportunity)
    if source is not None:
        session.execute(delete(IngestionCandidate).where(IngestionCandidate.source_id == source.id))
        session.delete(source)
    session.flush()


def seed_candidates(session: Session, admin: User, *, today: date | None = None) -> dict[str, int]:
    """(Re)create the fixture source and its candidates; return candidate counts by state."""
    today = today or date.today()
    served = pages(today)
    _remove_previous(session)
    source = registry.create_source(session, SourceDefinition.model_validate({
        "name": SOURCE_NAME, "base_domain": HOST.removeprefix("www."), "allowed_hosts": [HOST],
        "category": "university", "authority_level": "official", "provider": {"name": SOURCE_NAME},
        "discovery_method": "url_list", "connector_key": "url_list", "connector_config": {"urls": list(served)},
    }), actor_id=admin.id)
    registry.change_status(session, source, SourceStatus.TESTING, actor_id=admin.id)
    registry.record_terms_review(session, source, status=TermsStatus.ACCEPTABLE, reviewer_id=admin.id, notes="e2e fixture")
    report = run_source_test(session, source, reader=_FixtureReader(served), actor_id=admin.id)
    if not report.passed:
        raise SystemExit(f"E2E fixture source failed its test: {report.problems}")
    registry.change_status(session, source, SourceStatus.APPROVED, actor_id=admin.id)
    session.commit()
    reader = _FixtureReader(served)
    pipeline.run_discovery(session, source, reader=reader)
    pipeline.process_candidates(session, reader_factory=lambda _source: reader, source_id=source.id, limit=50)
    states: dict[str, int] = {}
    for state in session.scalars(select(IngestionCandidate.state).where(IngestionCandidate.source_id == source.id)):
        states[state] = states.get(state, 0) + 1
    return states


__all__ = ["FELLOWSHIP", "SCHOLARSHIP", "SOURCE_NAME", "SUMMER_SCHOOL", "pages", "seed_candidates"]
