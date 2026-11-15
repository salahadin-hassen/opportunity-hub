"""Run a connector inside the approved-source policy and validate what it returns.

``collect_leads`` is the only supported way to run a connector:

* the page reader handed to the connector is wrapped so it refuses any URL
  outside the source's exact allowed hosts, and stops after the source's
  per-run page budget;
* every lead the connector yields is checked again (scheme, user info,
  port, exact host) and the accepted leads are capped at the same budget.

Rejected leads are returned with a reason rather than silently dropped, so
a misbehaving connector shows up in run records. No network access happens
here; reading goes through whatever ``PageReader`` the caller supplies (the
safe fetcher of M2-T7 in production, fakes in tests).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import urlsplit, urlunsplit

from app.intelligence.connectors.base import Connector, Lead, PageContent, PageReader, SourceView
from app.intelligence.hosts import InvalidHostError, normalize_host

MAX_URL_LENGTH = 2000


class OutOfScopeURLError(ValueError):
    """Raised when a URL is not an https URL on one of the source's allowed hosts."""


class PageBudgetExceededError(RuntimeError):
    """Raised when a connector tries to read more pages than its crawl policy allows."""


@dataclass(frozen=True)
class RejectedLead:
    url: str
    reason: str


@dataclass
class DiscoveryResult:
    accepted: list[Lead] = field(default_factory=list)
    rejected: list[RejectedLead] = field(default_factory=list)
    pages_read: int = 0


def check_in_scope(url: str, allowed_hosts: frozenset[str]) -> str:
    """Return ``url`` without its fragment if it is an https URL on an allowed host; else raise."""
    if not isinstance(url, str) or not url or len(url) > MAX_URL_LENGTH:
        raise OutOfScopeURLError("URL is empty or longer than allowed.")
    if any(char.isspace() or ord(char) < 0x20 or ord(char) == 0x7F for char in url):
        raise OutOfScopeURLError("URL contains whitespace or control characters.")
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError as error:
        raise OutOfScopeURLError(f"URL cannot be parsed: {error}.") from error
    if parts.scheme != "https":
        raise OutOfScopeURLError("Only https URLs are allowed.")
    if parts.username is not None or parts.password is not None:
        raise OutOfScopeURLError("URLs with user info are not allowed.")
    if port not in (None, 443):
        raise OutOfScopeURLError("Only the default https port is allowed.")
    if not parts.hostname:
        raise OutOfScopeURLError("URL has no host.")
    try:
        host = normalize_host(parts.hostname)
    except InvalidHostError as error:
        raise OutOfScopeURLError(str(error)) from error
    if host not in allowed_hosts:
        raise OutOfScopeURLError(f"Host {host!r} is not an allowed host of this source.")
    return urlunsplit(("https", host, parts.path or "/", parts.query, ""))


class _ScopedPageReader:
    """Wraps a reader so a connector can only reach the source's allowed hosts, within budget."""

    def __init__(self, inner: PageReader, source: SourceView) -> None:
        self._inner = inner
        self._source = source
        self.pages_read = 0

    def read(self, url: str) -> PageContent:
        checked = check_in_scope(url, self._source.allowed_hosts)
        if self.pages_read >= self._source.crawl_policy.max_pages_per_run:
            raise PageBudgetExceededError(
                f"Page budget of {self._source.crawl_policy.max_pages_per_run} reached for {self._source.name}."
            )
        self.pages_read += 1
        return self._inner.read(checked)


def collect_leads(connector: Connector, source: SourceView, reader: PageReader) -> DiscoveryResult:
    """Run ``connector`` for ``source`` and return its validated, de-duplicated, budget-capped leads."""
    if source.discovery_method != connector.discovery_method:
        raise ValueError(
            f"Source {source.name!r} uses {source.discovery_method}, but connector {connector.key!r} "
            f"implements {connector.discovery_method}."
        )
    scoped = _ScopedPageReader(reader, source)
    result = DiscoveryResult()
    seen: set[str] = set()
    budget = source.crawl_policy.max_pages_per_run
    for lead in connector.discover(source, scoped):
        if not isinstance(lead, Lead):
            result.rejected.append(RejectedLead(url=repr(lead)[:200], reason="connector yielded a non-Lead value"))
            continue
        try:
            url = check_in_scope(lead.url, source.allowed_hosts)
        except OutOfScopeURLError as error:
            result.rejected.append(RejectedLead(url=str(lead.url)[:MAX_URL_LENGTH], reason=str(error)))
            continue
        if url in seen:
            continue
        if len(result.accepted) >= budget:
            result.rejected.append(RejectedLead(url=url, reason=f"over the per-run budget of {budget}"))
            continue
        seen.add(url)
        result.accepted.append(Lead(url=url, external_id=lead.external_id))
    result.pages_read = scoped.pages_read
    return result


__all__ = [
    "DiscoveryResult",
    "OutOfScopeURLError",
    "PageBudgetExceededError",
    "RejectedLead",
    "check_in_scope",
    "collect_leads",
]
