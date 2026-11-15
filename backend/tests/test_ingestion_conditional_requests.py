"""Conditional requests through the whole pipeline: real database, real fetcher and reader, and a
deterministic origin server (``tests.fake_web``) that answers 304 to a matching validator."""
from __future__ import annotations

from datetime import timedelta

import httpx
from sqlalchemy import select

from app.intelligence import pipeline
from app.models import IngestionCandidate
from app.models.ingestion import CandidateState
from tests.fake_web import FakeWeb
from tests.test_ingestion_pipeline import NOW, make_source, opportunity_page, site

V1 = '"v1-5f3a"'
V2 = '"v2-91bc"'
MODIFIED_1 = "Sun, 15 Nov 2026 08:00:00 GMT"
MODIFIED_2 = "Mon, 16 Nov 2026 09:30:00 GMT"


def _candidate(db, url: str) -> IngestionCandidate:
    return db.scalar(select(IngestionCandidate).where(IngestionCandidate.url == url).execution_options(populate_existing=True))


def _process(db, web: FakeWeb, source, now):
    return pipeline.process_candidates(db, reader_factory=web.reader, now=now, source_id=source.id)


def _snapshot(candidate: IngestionCandidate) -> dict:
    return {
        "page_text": candidate.page_text, "content_hash": candidate.content_hash, "extraction": candidate.extraction,
        "validation": candidate.validation, "quality_score": candidate.quality_score,
        "fetched_at": candidate.fetched_at, "etag": candidate.etag, "last_modified": candidate.last_modified,
    }


def test_200_then_304_then_200_with_new_content_and_validators(db_session, monkeypatch):
    web = FakeWeb(monkeypatch)
    url = f"{site()}/scholarship"
    source = make_source(db_session, [url])
    web.page(url, opportunity_page(deadline="15 January 2027"), etag=V1, last_modified=MODIFIED_1)

    # --- first request: 200 with ETag and Last-Modified, sent without any validator
    pipeline.run_discovery(db_session, source, reader=web.reader(source), now=NOW)
    first = _process(db_session, web, source, NOW)
    candidate = _candidate(db_session, url)
    assert first.by_state == {"needs_review": 1}
    [request] = web.requests_for(url)
    assert (request.status, request.if_none_match, request.if_modified_since) == (200, None, None)
    assert (candidate.etag, candidate.last_modified) == (V1, MODIFIED_1)
    assert candidate.extraction["deadline"]["value"] == "2027-01-15"
    assert candidate.last_seen_at == NOW and candidate.fetched_at == NOW
    stored = _snapshot(candidate)

    # --- second request: the stored validators are sent, the server answers 304
    later = NOW + timedelta(days=1)
    pipeline.requeue_candidate(db_session, candidate.id, actor_id=None, now=later)
    second = _process(db_session, web, source, later)
    candidate = _candidate(db_session, url)
    request = web.requests_for(url)[-1]
    assert (request.status, request.if_none_match, request.if_modified_since) == (304, V1, MODIFIED_1)
    assert second.by_state == {"needs_review": 1}
    # Evidence, hash, extraction and validators are exactly what the first request stored...
    assert _snapshot(candidate) == stored
    # ...only the last-seen time moved, and the candidate is back in review, not left in the queue.
    assert candidate.last_seen_at == later
    assert candidate.state == CandidateState.NEEDS_REVIEW and candidate.resume_state is None
    assert candidate.attempts == 0 and candidate.lease_until is None and candidate.last_error is None
    assert _process(db_session, web, source, later + timedelta(minutes=1)).processed == 0

    # --- third request: the source changed; 200 with new content and new validators
    web.page(url, opportunity_page(deadline="28 February 2027"), etag=V2, last_modified=MODIFIED_2)
    changed_at = NOW + timedelta(days=2)
    pipeline.requeue_candidate(db_session, candidate.id, actor_id=None, now=changed_at)
    third = _process(db_session, web, source, changed_at)
    candidate = _candidate(db_session, url)
    request = web.requests_for(url)[-1]
    assert (request.status, request.if_none_match, request.if_modified_since) == (200, V1, MODIFIED_1)
    assert third.by_state == {"needs_review": 1}
    assert (candidate.etag, candidate.last_modified) == (V2, MODIFIED_2)
    assert candidate.content_hash != stored["content_hash"]
    assert candidate.extraction["deadline"]["value"] == "2027-02-28"
    assert "28 February 2027" in candidate.page_text
    assert candidate.fetched_at == changed_at and candidate.last_seen_at == changed_at
    assert [seen.status for seen in web.requests_for(url)] == [200, 304, 200]


def test_a_failed_request_keeps_the_stored_validators_and_content(db_session, monkeypatch):
    web = FakeWeb(monkeypatch)
    url = f"{site()}/scholarship"
    source = make_source(db_session, [url])
    web.page(url, opportunity_page(), etag=V1, last_modified=MODIFIED_1)
    pipeline.run_discovery(db_session, source, reader=web.reader(source), now=NOW)
    _process(db_session, web, source, NOW)
    stored = _snapshot(_candidate(db_session, url))

    failures = [
        lambda request: httpx.Response(503, headers={"content-type": "text/html"}, content=b"down"),
        lambda request: (_ for _ in ()).throw(httpx.ReadTimeout("The read operation timed out", request=request)),
        lambda request: httpx.Response(429, headers={"content-type": "text/html"}, content=b"slow down"),
    ]
    when = NOW
    for attempt, failure in enumerate(failures, start=1):
        web.respond(url, failure)
        candidate = _candidate(db_session, url)
        when += timedelta(days=1)
        if candidate.state != CandidateState.RETRY:
            pipeline.requeue_candidate(db_session, candidate.id, actor_id=None, now=when)
        else:
            candidate.next_attempt_at = when
            db_session.flush()
        report = _process(db_session, web, source, when)
        candidate = _candidate(db_session, url)
        assert report.by_state == {"retry": 1}
        assert candidate.attempts == attempt and candidate.last_error
        # The validators went out with the request and survived its failure, with everything else.
        assert web.requests_for(url)[-1].if_none_match == V1
        assert _snapshot(candidate) == stored
        assert candidate.resume_state == CandidateState.NEEDS_REVIEW

    # When the server recovers and nothing changed, the retry is a 304 and the candidate is restored.
    web.page(url, opportunity_page(), etag=V1, last_modified=MODIFIED_1)
    candidate.next_attempt_at = when + timedelta(days=1)
    db_session.flush()
    report = _process(db_session, web, source, when + timedelta(days=1))
    candidate = _candidate(db_session, url)
    assert web.requests_for(url)[-1].status == 304
    assert report.by_state == {"needs_review": 1}
    assert _snapshot(candidate) == stored and candidate.attempts == 0 and candidate.last_error is None


def test_a_page_without_validators_is_fetched_in_full_every_time_and_clears_old_ones(db_session, monkeypatch):
    web = FakeWeb(monkeypatch)
    url = f"{site()}/scholarship"
    source = make_source(db_session, [url])
    web.page(url, opportunity_page(), etag=V1)
    pipeline.run_discovery(db_session, source, reader=web.reader(source), now=NOW)
    _process(db_session, web, source, NOW)
    assert _candidate(db_session, url).etag == V1

    # The server stops sending validators: ours no longer describe what it serves, so they are dropped.
    web.page(url, opportunity_page(extra="<p>Updated.</p>"))
    candidate = _candidate(db_session, url)
    pipeline.requeue_candidate(db_session, candidate.id, actor_id=None, now=NOW + timedelta(days=1))
    _process(db_session, web, source, NOW + timedelta(days=1))
    candidate = _candidate(db_session, url)
    assert (candidate.etag, candidate.last_modified) == (None, None)

    pipeline.requeue_candidate(db_session, candidate.id, actor_id=None, now=NOW + timedelta(days=2))
    _process(db_session, web, source, NOW + timedelta(days=2))
    last = web.requests_for(url)[-1]
    assert (last.status, last.if_none_match, last.if_modified_since) == (200, None, None)


def test_last_modified_alone_makes_the_request_conditional(db_session, monkeypatch):
    web = FakeWeb(monkeypatch)
    url = f"{site()}/scholarship"
    source = make_source(db_session, [url])
    web.page(url, opportunity_page(), last_modified=MODIFIED_1)
    pipeline.run_discovery(db_session, source, reader=web.reader(source), now=NOW)
    _process(db_session, web, source, NOW)
    candidate = _candidate(db_session, url)
    assert (candidate.etag, candidate.last_modified) == (None, MODIFIED_1)
    pipeline.requeue_candidate(db_session, candidate.id, actor_id=None, now=NOW + timedelta(days=1))
    _process(db_session, web, source, NOW + timedelta(days=1))
    last = web.requests_for(url)[-1]
    assert (last.status, last.if_none_match, last.if_modified_since) == (304, None, MODIFIED_1)
    assert _candidate(db_session, url).state == CandidateState.NEEDS_REVIEW


def test_a_304_never_stands_in_for_content_that_was_not_stored(db_session, monkeypatch):
    """A server that answers 304 to an unconditional request is misbehaving: retry, never 'unchanged'."""
    web = FakeWeb(monkeypatch)
    url = f"{site()}/scholarship"
    source = make_source(db_session, [url])
    web.respond(url, lambda request: httpx.Response(304))
    pipeline.run_discovery(db_session, source, reader=web.reader(source), now=NOW)
    report = _process(db_session, web, source, NOW)
    candidate = _candidate(db_session, url)
    assert report.by_state == {"retry": 1}
    assert candidate.page_text is None and candidate.content_hash is None and "304" in candidate.last_error


def test_a_304_keeps_an_earlier_rejection_or_duplicate_and_applies_a_passed_deadline(db_session, monkeypatch):
    web = FakeWeb(monkeypatch)
    base = site()
    rejected_url, expiring_url = f"{base}/rejected", f"{base}/expiring"
    source = make_source(db_session, [rejected_url, expiring_url])
    web.page(rejected_url, opportunity_page(title="Winter Research Scholarship 2027"), etag=V1)
    web.page(expiring_url, opportunity_page(title="Spring Research Scholarship 2027", deadline="20 November 2026"), etag=V2)
    pipeline.run_discovery(db_session, source, reader=web.reader(source), now=NOW)
    assert _process(db_session, web, source, NOW).by_state == {"needs_review": 2}

    # A curator rejected one; both are re-queued later and neither page has changed.
    from app.models import User

    curator = User(email="conditional-curator@example.org", password_hash="x", role="curator")
    db_session.add(curator)
    db_session.flush()
    rejected = _candidate(db_session, rejected_url)
    pipeline.decide_candidate(db_session, rejected.id, actor_id=curator.id, decision="reject", notes="not for students")
    later = NOW + timedelta(days=30)  # past 20 November 2026
    for url in (rejected_url, expiring_url):
        pipeline.requeue_candidate(db_session, _candidate(db_session, url).id, actor_id=None, now=later)
    report = _process(db_session, web, source, later)
    assert [web.requests_for(url)[-1].status for url in (rejected_url, expiring_url)] == [304, 304]
    assert report.by_state == {"rejected": 1, "expired": 1}
    assert _candidate(db_session, rejected_url).state == CandidateState.REJECTED
    assert _candidate(db_session, expiring_url).state == CandidateState.EXPIRED
