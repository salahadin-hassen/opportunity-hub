"""Source testing actually fetches: real database, real fetcher and reader, deterministic origin server.

A source is never reported as working because it is registered. Each test registers a source the way
an operator would and runs ``run_source_test`` (what ``ingest-source-test`` calls)."""
from __future__ import annotations

import argparse
import uuid

import httpx
import pytest
from sqlalchemy import select

from app.intelligence import registry
from app.intelligence.definitions import SourceDefinition
from app.intelligence.health import source_health
from app.intelligence.source_test import run_source_test
from app.models import AcquisitionSource, AuditLog, IngestionCandidate, User
from app.models.enums import SourceStatus, TermsStatus
from tests.fake_web import FakeWeb
from tests.test_ingestion_pipeline import as_, client, make_source, opportunity_page, site  # noqa: F401 (fixture)

PAGE = opportunity_page()


def _one(db, web: FakeWeb, url: str):
    """Register a url_list source for ``url`` and test it."""
    source = make_source(db, [url])
    return source, run_source_test(db, source, reader=web.reader(source))


def _failed(source: AcquisitionSource, report, result: str, status_code: int | None = None) -> None:
    [check] = report.checks
    assert not report.passed and not check.ok
    assert (check.result, check.status_code) == (result, status_code)
    assert check.detail and report.problems
    assert source.last_test_passed is False and source.last_test_at is not None
    # Approval depends on this field: a failed test never leaves it set.
    assert source.test_run_passed_at is None
    assert source.last_test_report["checks"][0]["result"] == result


def test_a_successful_fetch_passes_and_records_what_was_read(db_session, monkeypatch):
    web = FakeWeb(monkeypatch)
    url = f"{site()}/scholarship"
    web.page(url, PAGE)
    source, report = _one(db_session, web, url)
    [check] = report.checks
    assert report.passed and report.problems == [] and report.robots_status == "allowed"
    assert (check.ok, check.result, check.status_code, check.final_url) == (True, "ok", 200, url)
    assert check.text_chars > 200 and check.content_type == "text/html"
    assert (report.leads, report.fetched_ok, report.fetched_failed) == (1, 1, 0)
    assert source.last_test_passed is True and source.test_run_passed_at is not None
    # The page and robots.txt were really requested; nothing was stored as a candidate.
    assert [seen.url for seen in web.requests] == [f"https://{source.base_domain and url.split('/')[2]}/robots.txt", url]
    assert db_session.scalar(select(IngestionCandidate).where(IngestionCandidate.source_id == source.id)) is None
    entry = db_session.scalar(
        select(AuditLog).where(AuditLog.action == "source.test_run_recorded", AuditLog.target_id == str(source.id))
    )
    assert entry.changes["passed"] is True and entry.changes["fetched_ok"] == 1


@pytest.mark.parametrize(
    ("status", "result"),
    [(404, "dead_link"), (410, "dead_link"), (403, "access_denied"), (401, "access_denied"),
     (429, "rate_limited"), (500, "server_error"), (503, "server_error")],
)
def test_http_errors_fail_the_test_with_a_specific_reason(db_session, monkeypatch, status, result):
    web = FakeWeb(monkeypatch)
    url = f"{site()}/scholarship"
    web.page(url, b"<html>error</html>", status=status)
    source, report = _one(db_session, web, url)
    _failed(source, report, result, status)
    assert f"HTTP {status}" in report.problems[0] and url in report.problems[0]


def test_a_url_that_is_registered_but_does_not_exist_fails(db_session, monkeypatch):
    """The regression: a url_list source used to pass without its page ever being requested."""
    web = FakeWeb(monkeypatch)
    base = site()
    web.host(base.split("/")[2])  # the host exists; the page was never published
    source, report = _one(db_session, web, f"{base}/no-such-page")
    _failed(source, report, "dead_link", 404)
    with pytest.raises(registry.SourceStateError, match="no passing test run"):
        registry.record_terms_review(db_session, source, status=TermsStatus.ACCEPTABLE, reviewer_id=None, notes="ok")
        registry.change_status(db_session, source, SourceStatus.APPROVED)
    assert source.status == SourceStatus.TESTING


def test_a_timeout_fails_the_test(db_session, monkeypatch):
    web = FakeWeb(monkeypatch)
    url = f"{site()}/scholarship"

    def slow(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("The read operation timed out", request=request)

    web.respond(url, slow)
    source, report = _one(db_session, web, url)
    _failed(source, report, "timeout")


def test_an_unresolvable_host_fails_the_test(db_session, monkeypatch):
    web = FakeWeb(monkeypatch)
    source, report = _one(db_session, web, f"{site()}/scholarship")  # no DNS record at all
    assert not report.passed and report.fetched_ok == 0
    assert report.robots_status == "unreachable"
    assert any("robots.txt status is unreachable" in problem for problem in report.problems)
    # robots.txt could not be read, so the lead was refused before any page request.
    assert report.leads == 0 and report.checks == [] and len(report.rejected) == 1
    assert web.requests == [] and source.test_run_passed_at is None


def test_a_redirect_within_the_allow_list_is_followed(db_session, monkeypatch):
    web = FakeWeb(monkeypatch)
    base = site()
    old, new = f"{base}/old", f"{base}/scholarships/2027"
    web.respond(old, lambda request: httpx.Response(301, headers={"location": "/scholarships/2027"}))
    web.page(new, PAGE)
    source, report = _one(db_session, web, old)
    [check] = report.checks
    assert report.passed and (check.result, check.final_url) == ("ok", new)


def test_a_redirect_to_a_host_outside_the_allow_list_is_refused(db_session, monkeypatch):
    web = FakeWeb(monkeypatch)
    url = f"{site()}/scholarship"
    web.page("https://elsewhere.example.org/landing", PAGE)
    web.respond(url, lambda request: httpx.Response(302, headers={"location": "https://elsewhere.example.org/landing"}))
    source, report = _one(db_session, web, url)
    _failed(source, report, "redirect_off_allowlist")
    assert web.requests_for("https://elsewhere.example.org/landing") == []  # never requested


@pytest.mark.parametrize("target", ["http://169.254.169.254/latest/meta-data/", "http://127.0.0.1:8000/admin", "file:///etc/passwd"])
def test_a_redirect_to_an_internal_address_is_refused(db_session, monkeypatch, target):
    web = FakeWeb(monkeypatch)
    url = f"{site()}/scholarship"
    web.respond(url, lambda request: httpx.Response(302, headers={"location": target}))
    source, report = _one(db_session, web, url)
    [check] = report.checks
    assert not report.passed and check.result in ("redirect_off_allowlist", "blocked_address")
    assert [seen.url for seen in web.requests if seen.url == target] == []


def test_an_allowed_host_that_resolves_to_a_private_address_is_refused(db_session, monkeypatch):
    """The SSRF guard checks the resolved address even for a host the source lists."""
    web = FakeWeb(monkeypatch)
    url = f"{site()}/scholarship"
    web.page(url, PAGE)
    web.host(url.split("/")[2], "10.0.0.7")
    source, report = _one(db_session, web, url)
    assert not report.passed and report.fetched_ok == 0
    assert web.requests == []  # refused before any request was sent
    assert source.test_run_passed_at is None


def test_robots_denial_fails_the_test(db_session, monkeypatch):
    web = FakeWeb(monkeypatch)
    base = site()
    url = f"{base}/private/scholarship"
    web.page(url, PAGE)
    web.robots(base.split("/")[2], "User-agent: *\nDisallow: /private/\n")
    source, report = _one(db_session, web, url)
    assert not report.passed and report.leads == 0
    assert report.rejected == [{"url": url, "reason": "disallowed by robots.txt (or robots.txt unreachable)"}]
    assert web.requests_for(url) == []  # the page was not requested
    assert source.test_run_passed_at is None and source.last_test_passed is False


def test_robots_that_disallows_the_whole_site_fails_the_test(db_session, monkeypatch):
    web = FakeWeb(monkeypatch)
    base = site()
    url = f"{base}/scholarship"
    web.page(url, PAGE)
    web.robots(base.split("/")[2], "User-agent: OpportunityHub-Bot\nDisallow: /\n")
    source, report = _one(db_session, web, url)
    assert not report.passed and report.robots_status == "disallowed"
    assert web.requests_for(url) == [] and source.robots_status == "disallowed"


def test_an_unreadable_robots_file_fails_the_test(db_session, monkeypatch):
    web = FakeWeb(monkeypatch)
    base = site()
    url = f"{base}/scholarship"
    web.page(url, PAGE)
    web.robots(base.split("/")[2], "", status=503)
    source, report = _one(db_session, web, url)
    assert not report.passed and report.robots_status == "unreachable"
    assert web.requests_for(url) == []


@pytest.mark.parametrize(
    ("bad", "reason"),
    [
        ("http://{host}/scholarship", "Only https URLs are allowed."),
        ("https://user:secret@{host}/scholarship", "URLs with user info are not allowed."),
        ("https://{host}:8443/scholarship", "Only the default https port is allowed."),
        ("https://{host}/has space", "URL contains whitespace or control characters."),
        ("https://other-{host}/scholarship", "is not an allowed host of this source."),
        ("not a url", "URL contains whitespace or control characters."),
        ("https:///scholarship", "URL has no host."),
    ],
)
def test_malformed_and_out_of_scope_urls_fail_the_test(db_session, monkeypatch, bad, reason):
    web = FakeWeb(monkeypatch)
    base = site()
    host = base.split("/")[2]
    good = f"{base}/scholarship"
    web.page(good, PAGE)
    source = make_source(db_session, [good])
    # Written straight into the stored configuration, as an edit that slipped past review would be.
    source.connector_config = {"urls": [good, bad.format(host=host)]}
    db_session.flush()
    report = run_source_test(db_session, source, reader=web.reader(source))
    assert not report.passed and report.fetched_ok == 1  # the good page still read; the source still fails
    assert len(report.rejected) == 1 and reason in report.rejected[0]["reason"]
    assert any("rejected" in problem for problem in report.problems)
    assert source.test_run_passed_at is None


@pytest.mark.parametrize(
    ("body", "content_type", "result"),
    [
        (b"%PDF-1.7 ...", "application/pdf", "unsupported_content_type"),
        (b'{"title": "Scholarship"}', "application/json", "not_html"),
        (b"<html><body><div id='root'></div><script>render()</script></body></html>", "text/html", "empty_page"),
    ],
)
def test_a_response_that_is_not_a_readable_html_page_fails_the_test(db_session, monkeypatch, body, content_type, result):
    web = FakeWeb(monkeypatch)
    url = f"{site()}/scholarship"
    web.page(url, body, content_type=content_type)
    source, report = _one(db_session, web, url)
    _failed(source, report, result, None if result == "unsupported_content_type" else 200)


def test_every_url_of_a_curated_list_must_be_readable(db_session, monkeypatch):
    web = FakeWeb(monkeypatch)
    base = site()
    urls = [f"{base}/a", f"{base}/b", f"{base}/c"]
    web.page(urls[0], PAGE)
    web.page(urls[1], b"gone", status=404)
    web.page(urls[2], PAGE)
    source = make_source(db_session, urls)
    report = run_source_test(db_session, source, reader=web.reader(source))
    assert not report.passed and (report.fetched_ok, report.fetched_failed) == (2, 1)
    assert [check.result for check in report.checks] == ["ok", "dead_link", "ok"]
    assert "1 of 3 page(s) could not be read" in report.problems[0]


def test_a_crawled_source_passes_when_its_index_and_a_sampled_page_are_readable(db_session, monkeypatch):
    web = FakeWeb(monkeypatch)
    base = site()
    host = base.split("/")[2]
    pages = [f"{base}/calls/{index}" for index in range(4)]
    sitemap = "<urlset>" + "".join(f"<url><loc>{url}</loc></url>" for url in pages) + "</urlset>"
    web.page(f"{base}/sitemap.xml", sitemap, content_type="application/xml")
    for url in pages[:2]:
        web.page(url, PAGE)  # the other two are stale entries: 404
    source = registry.create_source(db_session, SourceDefinition.model_validate({
        "name": f"Sitemap University {uuid.uuid4().hex[:6]}", "base_domain": host.removeprefix("www."),
        "allowed_hosts": [host], "category": "university", "authority_level": "official",
        "provider": {"name": "Sitemap University"}, "discovery_method": "sitemap", "connector_key": "sitemap",
        "connector_config": {"sitemap_urls": [f"{base}/sitemap.xml"]},
    }))
    registry.change_status(db_session, source, SourceStatus.TESTING)
    report = run_source_test(db_session, source, reader=web.reader(source), sample=3)
    assert report.passed and (report.leads, report.pages_read) == (4, 1)
    assert [check.result for check in report.checks] == ["ok", "ok", "dead_link"]
    assert report.problems == [] and "1 of 3 sampled page(s) could not be read" in report.warnings[0]

    # With every sampled page dead, the index alone does not make the source operational.
    for url in pages[:2]:
        web.page(url, b"gone", status=404)
    again = run_source_test(db_session, source, reader=web.reader(source), sample=3)
    assert not again.passed and again.fetched_ok == 0 and source.test_run_passed_at is None


def test_a_source_is_tested_only_while_in_testing(db_session, monkeypatch):
    web = FakeWeb(monkeypatch)
    url = f"{site()}/scholarship"
    web.page(url, PAGE)
    source = make_source(db_session, [url], status=SourceStatus.PROPOSED)
    with pytest.raises(registry.SourceStateError):
        run_source_test(db_session, source, reader=web.reader(source))
    assert web.requests == [] and source.last_test_at is None


def test_the_cli_reports_each_failure_and_exits_non_zero(db_session, monkeypatch, capsys):
    from app import ingest_cli
    from app.intelligence import pipeline

    web = FakeWeb(monkeypatch)
    base = site()
    web.page(f"{base}/live", PAGE)
    web.page(f"{base}/dead", b"gone", status=404)
    monkeypatch.setattr(pipeline, "default_reader", web.reader)
    monkeypatch.setattr(db_session, "commit", db_session.flush)
    source = make_source(db_session, [f"{base}/live", f"{base}/dead"], status=SourceStatus.PROPOSED)
    code = ingest_cli.run(db_session, argparse.Namespace(command="ingest-source-test", name=source.name, sample=5))
    output = capsys.readouterr().out
    assert code == 2 and "test run FAILED" in output
    assert f"ok HTTP 200 {base}/live" in output and f"FAILED dead_link HTTP 404 {base}/dead" in output

    web.page(f"{base}/dead", PAGE)
    code = ingest_cli.run(db_session, argparse.Namespace(command="ingest-source-test", name=source.name, sample=5))
    assert code == 0 and "test run PASSED" in capsys.readouterr().out


async def test_the_curator_api_shows_why_a_source_test_failed(client, db_session, monkeypatch):  # noqa: F811
    web = FakeWeb(monkeypatch)
    url = f"{site()}/scholarship"
    web.page(url, b"forbidden", status=403)
    source, _ = _one(db_session, web, url)
    curator = User(email=f"curator-{uuid.uuid4().hex[:8]}@example.org", password_hash="x", role="curator")
    db_session.add(curator)
    db_session.flush()
    body = (await client.get(f"/curate/sources/{source.id}", headers=as_(curator))).json()
    assert body["last_test_passed"] is False and body["test_run_passed_at"] is None
    check = body["last_test_report"]["checks"][0]
    assert (check["url"], check["result"], check["status_code"]) == (url, "access_denied", 403)


# --- source health ---------------------------------------------------------------------------------------


def test_source_health_counts_only_what_recorded_evidence_proves(db_session, monkeypatch):
    from app.intelligence import pipeline

    before = source_health(db_session)
    web = FakeWeb(monkeypatch)
    base = site()

    registered = make_source(db_session, [f"{site()}/never-tested"], status=SourceStatus.PROPOSED)

    dead = make_source(db_session, [f"{site()}/dead"])
    web.host(dead.base_domain if dead.base_domain.startswith("www.") else f"www.{dead.base_domain}")
    run_source_test(db_session, dead, reader=web.reader(dead))

    tested_url = f"{site()}/tested"
    web.page(tested_url, PAGE)
    tested = make_source(db_session, [tested_url])
    run_source_test(db_session, tested, reader=web.reader(tested))

    good_url, news_url = f"{base}/scholarship", f"{base}/news"
    web.page(good_url, PAGE)
    web.page(news_url, "<html><body><h1>Campus news</h1><p>" + "The cafeteria has a new menu this week. " * 12 + "</p></body></html>")
    producing = make_source(db_session, [good_url, news_url])
    run_source_test(db_session, producing, reader=web.reader(producing))
    pipeline.run_discovery(db_session, producing, reader=web.reader(producing))
    pipeline.process_candidates(db_session, reader_factory=web.reader, source_id=producing.id)

    # Rows written straight into the table (no discovery run) prove nothing about the source.
    forged = make_source(db_session, [f"{site()}/forged"])
    db_session.add(IngestionCandidate(
        source_id=forged.id, candidate_key=uuid.uuid4().hex, url=f"{site()}/forged", state="needs_review",
        http_status=200, fetched_at=pipeline.now_utc(), page_text="Title: ...", extraction={"title": {}}, validation={},
    ))
    db_session.flush()

    report = source_health(db_session)
    by_id = {item.id: item for item in report.sources}
    assert by_id[registered.id].stage == "registered" and not by_id[registered.id].tested
    assert by_id[dead.id].stage == "failed" and "dead_link" in by_id[dead.id].problem
    assert by_id[tested.id].stage == "fetchable" and by_id[tested.id].test_passed and not by_id[tested.id].parsed
    item = by_id[producing.id]
    assert (item.stage, item.candidates, item.fetched, item.valid, item.awaiting_review) == ("producing", 2, 2, 1, 1)
    assert item.parsed and item.needs_review and not item.failed
    assert by_id[forged.id].stage == "registered" and by_id[forged.id].untraceable_candidates == 1
    assert not by_id[forged.id].fetchable and not by_id[forged.id].producing

    def delta(name: str) -> int:
        return getattr(report, name) - getattr(before, name)

    assert {name: delta(name) for name in
            ("registered", "tested", "test_passed", "never_tested", "fetchable", "parsed", "producing", "failed", "needs_review")} == {
        "registered": 5, "tested": 3, "test_passed": 2, "never_tested": 2, "fetchable": 2, "parsed": 1,
        "producing": 1, "failed": 1, "needs_review": 1,
    }


async def test_source_health_api_is_for_curators(client, db_session):  # noqa: F811
    student = User(email=f"student-{uuid.uuid4().hex[:8]}@example.org", password_hash="x", role="student")
    curator = User(email=f"curator-{uuid.uuid4().hex[:8]}@example.org", password_hash="x", role="curator")
    db_session.add_all([student, curator])
    db_session.flush()
    source = make_source(db_session, [f"{site()}/x"], status=SourceStatus.PROPOSED)
    assert (await client.get("/curate/ingestion/source-health")).status_code == 401
    assert (await client.get("/curate/ingestion/source-health", headers=as_(student))).status_code == 403
    response = await client.get("/curate/ingestion/source-health", headers=as_(curator))
    assert response.status_code == 200
    body = response.json()
    mine = next(item for item in body["sources"] if item["id"] == str(source.id))
    assert mine["stage"] == "registered" and mine["tested"] is False and body["registered"] >= 1
