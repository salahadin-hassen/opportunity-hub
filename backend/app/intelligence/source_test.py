"""Source testing: prove a source can actually be read before it may be approved.

A test run is a dry-run discovery **plus a real fetch of the pages it leads to**, through the same
reader the pipeline uses (robots.txt, the source's host allow-list on every redirect hop, the SSRF
guard, the content-type allow-list, size and time limits). Registration alone proves nothing: a
``url_list`` source reads no page during discovery, so without the fetch a dead link would pass.

A run passes only when:

* discovery finished without an error and produced at least one lead;
* robots.txt for the source's primary host was read and allows us;
* for ``url_list`` (a curated list of exact pages): no listed URL was rejected and **every** listed
  URL returned a readable HTML page;
* for the crawling connectors (sitemap, feed, HTML index): at least one sampled lead returned a
  readable HTML page. Leads that failed are reported, since an index can carry a stale entry.

Nothing is stored except the result on the source (``last_test_*``) and its audit entry.
"""
from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.intelligence import pipeline, registry
from app.intelligence.connectors.base import PageReader
from app.intelligence.discovery import OutOfScopeURLError
from app.intelligence.fetcher import FetchError, OffAllowListError, ResponseTooLargeError, SSRFBlockedError
from app.intelligence.reader import HTTPStatusError, RobotsDisallowedError, UnsupportedContentTypeError
from app.intelligence.text import parse_html
from app.models import AcquisitionSource
from app.models.enums import RobotsStatus, SourceStatus

#: Leads fetched for a crawling connector. A ``url_list`` source has every listed URL fetched.
DEFAULT_SAMPLE = 5
#: Less visible text than this is an empty shell (an error page, or a page built by scripts).
MIN_TEXT_CHARS = 200
MAX_REPORTED_CHECKS = 50
_HTML_TYPES = ("text/html", "application/xhtml+xml")


@dataclass
class LeadCheck:
    url: str
    ok: bool
    #: ``ok`` or why not: dead_link, access_denied, rate_limited, server_error, http_error,
    #: robots_disallowed, redirect_off_allowlist, blocked_address, unsupported_content_type,
    #: response_too_large, timeout, fetch_error, malformed_url, not_html, empty_page.
    result: str
    detail: str | None = None
    status_code: int | None = None
    final_url: str | None = None
    content_type: str | None = None
    text_chars: int | None = None


@dataclass
class SourceTestReport:
    passed: bool = False
    robots_status: str = RobotsStatus.UNKNOWN
    leads: int = 0
    pages_read: int = 0
    fetched_ok: int = 0
    fetched_failed: int = 0
    problems: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    rejected: list[dict[str, str]] = field(default_factory=list)
    checks: list[LeadCheck] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["checks"] = data["checks"][:MAX_REPORTED_CHECKS]
        data["rejected"] = data["rejected"][:MAX_REPORTED_CHECKS]
        return data


def classify_failure(error: Exception) -> tuple[str, int | None]:
    """A stable label for why a fetch failed, and the HTTP status if there was one."""
    if isinstance(error, HTTPStatusError):
        code = error.status_code
        if code in (404, 410):
            return "dead_link", code
        if code in (401, 403):
            return "access_denied", code
        if code == 429:
            return "rate_limited", code
        if code >= 500:
            return "server_error", code
        return "http_error", code
    if isinstance(error, RobotsDisallowedError):
        return "robots_disallowed", None
    if isinstance(error, OffAllowListError):
        return "redirect_off_allowlist", None
    if isinstance(error, SSRFBlockedError):
        return "blocked_address", None
    if isinstance(error, UnsupportedContentTypeError):
        return "unsupported_content_type", None
    if isinstance(error, ResponseTooLargeError):
        return "response_too_large", None
    if isinstance(error, OutOfScopeURLError):
        return "malformed_url", None
    if isinstance(error, FetchError):
        text = str(error).lower()
        return ("timeout" if "timed out" in text or "time limit" in text or "timeout" in text else "fetch_error"), None
    raise error


def check_lead(reader: PageReader, url: str) -> LeadCheck:
    """Fetch one lead and say whether it is a readable HTML page."""
    try:
        page = reader.read(url)
    except (FetchError, OutOfScopeURLError) as error:
        result, status_code = classify_failure(error)
        return LeadCheck(url=url, ok=False, result=result, status_code=status_code,
                         detail=registry.sanitize_error(str(error))[:300])
    check = LeadCheck(url=url, ok=False, result="not_html", status_code=page.status_code,
                      final_url=page.final_url, content_type=page.content_type)
    if page.content_type not in _HTML_TYPES:
        check.detail = f"content type {page.content_type!r} is not an HTML page"
        return check
    text = parse_html(page.body.decode("utf-8", errors="replace")).text
    check.text_chars = len(text)
    if len(text) < MIN_TEXT_CHARS:
        check.result = "empty_page"
        check.detail = f"only {len(text)} characters of visible text (an error page, or content built by scripts)"
        return check
    check.ok, check.result = True, "ok"
    return check


def run_source_test(
    db: Session,
    source: AcquisitionSource,
    *,
    reader: PageReader | None = None,
    sample: int = DEFAULT_SAMPLE,
    actor_id: uuid.UUID | None = None,
    now: datetime | None = None,
) -> SourceTestReport:
    """Test ``source`` (it must be ``testing``) and record the result on it. Stores no candidates."""
    if SourceStatus(source.status) != SourceStatus.TESTING:
        raise registry.SourceStateError("A source is tested only while it is in testing.")
    reader = reader or pipeline.default_reader(source)
    report = SourceTestReport()
    discovery = pipeline.run_discovery(db, source, reader=reader, dry_run=True, now=now)
    report.leads = len(discovery.accepted)
    report.pages_read = discovery.pages_read
    report.rejected = [{"url": url, "reason": reason} for url, reason in discovery.rejected]
    curated = source.connector_key == "url_list"

    if discovery.error:
        report.problems.append(f"discovery failed: {discovery.error}")
    elif not discovery.accepted:
        report.problems.append("discovery produced no usable lead")
    if discovery.rejected:
        summary = f"{len(discovery.rejected)} lead(s) rejected, e.g. {discovery.rejected[0][0]}: {discovery.rejected[0][1]}"
        (report.problems if curated else report.warnings).append(summary)

    leads = discovery.accepted if curated else discovery.accepted[: max(1, sample)]
    if len(leads) > 20:
        # A long fetch loop must not hold a database connection: hosted Postgres closes idle ones. Nothing
        # is pending here (discovery ran as a dry run), so release it; the result is recorded afterwards.
        db.commit()
    for url in leads:
        report.checks.append(check_lead(reader, url))
    report.fetched_ok = sum(1 for check in report.checks if check.ok)
    report.fetched_failed = len(report.checks) - report.fetched_ok
    failed = [check for check in report.checks if not check.ok]
    if failed:
        summary = "; ".join(f"{check.url}: {check.result}" + (f" (HTTP {check.status_code})" if check.status_code else "")
                            for check in failed[:5])
        if curated or report.fetched_ok == 0:
            report.problems.append(f"{len(failed)} of {len(report.checks)} page(s) could not be read: {summary}")
        else:
            report.warnings.append(f"{len(failed)} of {len(report.checks)} sampled page(s) could not be read: {summary}")
    if leads and report.fetched_ok == 0 and not failed:
        report.problems.append("no page was fetched")

    robots = pipeline.robots_status_for(source, reader) or RobotsStatus.UNKNOWN
    report.robots_status = str(robots)
    if robots != RobotsStatus.ALLOWED:
        report.problems.append(f"robots.txt status is {robots}, not allowed")

    report.passed = not report.problems and report.fetched_ok > 0
    registry.record_test_run(
        db, source, passed=report.passed, robots_status=RobotsStatus(robots), actor_id=actor_id, report=report.as_dict(),
    )
    return report


__all__ = [
    "DEFAULT_SAMPLE",
    "LeadCheck",
    "MIN_TEXT_CHARS",
    "SourceTestReport",
    "check_lead",
    "classify_failure",
    "run_source_test",
]
