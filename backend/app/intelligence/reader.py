"""The production ``PageReader``: the safe fetcher plus robots.txt, politeness and content rules.

* Every fetch goes through ``fetcher.fetch_url`` with the source's exact allowed hosts, so redirects
  can't leave them and private or internal addresses are refused at the socket.
* robots.txt (RFC 9309) is read once per host per run. A missing file (4xx) allows everything; an
  unreachable or 5xx file means "disallow everything" for this run, as the RFC requires. The user
  agent is ``OpportunityHub-Bot``; a stated ``Crawl-delay`` raises the delay, never lowers it.
* Requests to one host are spaced by at least the source's ``min_delay_seconds``.
* Only HTML, XML/feeds, JSON and plain text are accepted; anything else is an error.
* Non-2xx responses raise ``HTTPStatusError`` (404/410 are marked permanent).
* A request is conditional when the caller passes the validators of a page it already holds; a 304
  comes back as a ``PageContent`` with ``status_code == 304`` and an empty body. A 304 to a request
  that sent no validator is an error, never "unchanged".
"""
from __future__ import annotations

import inspect
import time
from collections.abc import Callable
from urllib import robotparser
from urllib.parse import urlsplit

from app.intelligence.connectors.base import PageContent
from app.intelligence.fetcher import FetchedDocument, FetchError, fetch_url
from app.models.enums import RobotsStatus

USER_AGENT_TOKEN = "OpportunityHub-Bot"
ALLOWED_CONTENT_TYPES = (
    "text/html", "application/xhtml+xml", "application/xml", "text/xml", "application/rss+xml",
    "application/atom+xml", "application/json", "application/ld+json", "text/plain",
)


class RobotsDisallowedError(FetchError):
    """robots.txt does not allow this URL for our user agent."""


class UnsupportedContentTypeError(FetchError):
    """The response is not a type the pipeline processes."""


class HTTPStatusError(FetchError):
    def __init__(self, status_code: int, url: str) -> None:
        super().__init__(f"HTTP {status_code} for {url}")
        self.status_code = status_code
        #: 404 and 410 won't fix themselves; retrying is pointless.
        self.permanent = status_code in (404, 410)


FetchFunction = Callable[..., FetchedDocument]

MAX_VALIDATOR_LENGTH = 512


def _accepts_validators(function: Callable[..., object]) -> bool:
    """Whether ``function`` takes ``etag`` and ``last_modified`` keyword arguments."""
    try:
        parameters = inspect.signature(function).parameters
    except (TypeError, ValueError):
        return False
    if any(parameter.kind is inspect.Parameter.VAR_KEYWORD for parameter in parameters.values()):
        return True
    return "etag" in parameters and "last_modified" in parameters


def _header(headers: dict[str, str] | None, name: str) -> str | None:
    """A response header by case-insensitive name; None when absent, empty or implausibly long."""
    for key, value in (headers or {}).items():
        if key.lower() == name:
            value = (value or "").strip()
            return value if value and len(value) <= MAX_VALIDATOR_LENGTH else None
    return None


def read_page(reader: object, url: str, *, etag: str | None = None, last_modified: str | None = None) -> PageContent:
    """Read ``url``, conditionally when validators are given and ``reader`` supports them.

    A reader that only implements ``read(url)`` gets a plain request, so it can never return a 304.
    """
    read = reader.read  # type: ignore[attr-defined]
    if (etag or last_modified) and _accepts_validators(read):
        return read(url, etag=etag, last_modified=last_modified)
    return read(url)


class SafePageReader:
    """Reads pages for one source, politely, through the SSRF-safe fetcher."""

    def __init__(
        self,
        allowed_hosts: frozenset[str],
        *,
        min_delay_seconds: float,
        fetch: FetchFunction = fetch_url,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._allowed = allowed_hosts
        self._min_delay = min_delay_seconds
        self._fetch = fetch
        self._sleep = sleep
        self._clock = clock
        self._last_request: dict[str, float] = {}
        self._robots: dict[str, robotparser.RobotFileParser | None] = {}
        self.robots_status: dict[str, RobotsStatus] = {}
        self.requests_made = 0

    def _wait_turn(self, host: str, delay: float) -> None:
        last = self._last_request.get(host)
        if last is not None:
            remaining = last + delay - self._clock()
            if remaining > 0:
                self._sleep(remaining)
        self._last_request[host] = self._clock()

    def _robots_for(self, host: str) -> robotparser.RobotFileParser | None:
        """The parsed robots.txt for ``host``; None means everything is disallowed this run."""
        if host in self._robots:
            return self._robots[host]
        parser = robotparser.RobotFileParser()
        self._wait_turn(host, self._min_delay)
        self.requests_made += 1
        try:
            document = self._fetch(f"https://{host}/robots.txt", allowed_hosts=self._allowed)
        except FetchError:
            self._robots[host] = None
            self.robots_status[host] = RobotsStatus.UNREACHABLE
            return None
        if 400 <= document.status_code < 500:
            parser.parse([])  # no robots.txt: everything allowed
        elif document.status_code >= 500 or document.status_code < 200:
            self._robots[host] = None
            self.robots_status[host] = RobotsStatus.UNREACHABLE
            return None
        else:
            parser.parse(document.body.splitlines())
        self._robots[host] = parser
        allowed_root = parser.can_fetch(USER_AGENT_TOKEN, f"https://{host}/")
        self.robots_status[host] = RobotsStatus.ALLOWED if allowed_root else RobotsStatus.DISALLOWED
        return parser

    def allowed_by_robots(self, url: str) -> bool:
        host = (urlsplit(url).hostname or "").lower()
        parser = self._robots_for(host)
        return parser is not None and parser.can_fetch(USER_AGENT_TOKEN, url)

    def read(self, url: str, *, etag: str | None = None, last_modified: str | None = None) -> PageContent:
        host = (urlsplit(url).hostname or "").lower()
        parser = self._robots_for(host)
        if parser is None:
            raise RobotsDisallowedError(f"robots.txt for {host} could not be read; not fetching")
        if not parser.can_fetch(USER_AGENT_TOKEN, url):
            raise RobotsDisallowedError(f"robots.txt disallows {url}")
        delay = self._min_delay
        crawl_delay = parser.crawl_delay(USER_AGENT_TOKEN)
        if crawl_delay:
            delay = max(delay, float(crawl_delay))
        self._wait_turn(host, delay)
        self.requests_made += 1
        conditional = bool(etag or last_modified) and _accepts_validators(self._fetch)
        if conditional:
            document = self._fetch(url, allowed_hosts=self._allowed, etag=etag, last_modified=last_modified)
        else:
            document = self._fetch(url, allowed_hosts=self._allowed)
        headers = getattr(document, "headers", None)
        if document.status_code == 304:
            if not conditional:
                # Nothing we hold corresponds to this response, so it cannot mean "unchanged".
                raise HTTPStatusError(304, url)
            return PageContent(
                url=url,
                final_url=document.url,
                status_code=304,
                content_type="text/html",
                body=b"",
                etag=_header(headers, "etag"),
                last_modified=_header(headers, "last-modified"),
            )
        if not 200 <= document.status_code < 300:
            raise HTTPStatusError(document.status_code, url)
        content_type = document.content_type.split(";")[0].strip().lower()
        if content_type not in ALLOWED_CONTENT_TYPES:
            raise UnsupportedContentTypeError(f"content type {content_type!r} is not processed")
        return PageContent(
            url=url,
            final_url=document.url,
            status_code=document.status_code,
            content_type=content_type,
            body=document.body.encode("utf-8"),
            etag=_header(headers, "etag"),
            last_modified=_header(headers, "last-modified"),
        )


__all__ = [
    "ALLOWED_CONTENT_TYPES",
    "HTTPStatusError",
    "RobotsDisallowedError",
    "SafePageReader",
    "USER_AGENT_TOKEN",
    "UnsupportedContentTypeError",
    "read_page",
]
