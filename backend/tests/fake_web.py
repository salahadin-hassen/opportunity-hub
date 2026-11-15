"""A deterministic web for ingestion tests, plugged in underneath the real fetcher.

``FakeWeb`` replaces only two things: DNS (``socket.getaddrinfo``) and the HTTP transport that
``fetcher.fetch_url`` opens. Everything above them is the production code: URL and scheme checks, the
SSRF address check on the resolved IPs, the host allow-list on every redirect hop, redirect following,
request headers (including ``If-None-Match`` / ``If-Modified-Since``), size and time limits,
``SafePageReader`` with robots.txt, and the pipeline. Nothing reaches the network.

Pages behave like a real origin server: a page registered with an ``ETag`` or ``Last-Modified``
answers ``304 Not Modified`` to a matching conditional request.
"""
from __future__ import annotations

import socket
from collections.abc import Callable
from dataclasses import dataclass, field
from urllib.parse import urlsplit

import httpx

from app.intelligence import fetcher
from app.intelligence.reader import SafePageReader

PUBLIC_IP = "93.184.216.34"


@dataclass
class Page:
    body: bytes
    status: int = 200
    content_type: str = "text/html; charset=utf-8"
    etag: str | None = None
    last_modified: str | None = None
    headers: dict[str, str] = field(default_factory=dict)


@dataclass
class Seen:
    url: str
    if_none_match: str | None
    if_modified_since: str | None
    status: int


class FakeWeb:
    def __init__(self, monkeypatch) -> None:
        self.pages: dict[str, Page | Callable[[httpx.Request], httpx.Response]] = {}
        self.dns: dict[str, str] = {}
        self.requests: list[Seen] = []
        real_getaddrinfo = socket.getaddrinfo

        def getaddrinfo(host, port, *args, **kwargs):
            if host in self.dns:
                return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (self.dns[host], port))]
            try:
                socket.inet_aton(host)
            except OSError:
                raise socket.gaierror(socket.EAI_NONAME, "Name or service not known") from None
            return real_getaddrinfo(host, port, *args, **kwargs)  # an IP literal: no lookup happens

        monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)
        monkeypatch.setattr(fetcher, "SSRFSafeTransport", lambda **kwargs: httpx.MockTransport(self._handle))

    # --- setup ---------------------------------------------------------------------------------------

    def host(self, name: str, ip: str = PUBLIC_IP) -> None:
        self.dns[name] = ip

    def page(self, url: str, body: bytes | str = b"", **kwargs) -> None:
        self.host(urlsplit(url).hostname)
        self.pages[url] = Page(body=body.encode() if isinstance(body, str) else body, **kwargs)

    def respond(self, url: str, handler: Callable[[httpx.Request], httpx.Response]) -> None:
        self.host(urlsplit(url).hostname)
        self.pages[url] = handler

    def robots(self, host: str, text: str | None = None, *, status: int = 200) -> None:
        self.page(f"https://{host}/robots.txt", text or "", status=status, content_type="text/plain")

    def reader(self, source) -> SafePageReader:
        """The production reader for ``source``, without real waiting between requests."""
        from app.intelligence import registry

        return SafePageReader(registry.allowed_hosts(source), min_delay_seconds=0, sleep=lambda seconds: None)

    def requests_for(self, url: str) -> list[Seen]:
        return [seen for seen in self.requests if seen.url == url]

    # --- the server ----------------------------------------------------------------------------------

    def _handle(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        seen = Seen(url, request.headers.get("if-none-match"), request.headers.get("if-modified-since"), 0)
        self.requests.append(seen)
        page = self.pages.get(url)
        if page is None:
            response = httpx.Response(404, headers={"content-type": "text/html"}, content=b"<html>Not found</html>")
        elif callable(page):
            response = page(request)  # may raise an httpx transport error (a timeout, a reset)
        else:
            headers = {"content-type": page.content_type, **page.headers}
            if page.etag:
                headers["etag"] = page.etag
            if page.last_modified:
                headers["last-modified"] = page.last_modified
            not_modified = page.status == 200 and (
                (page.etag is not None and seen.if_none_match == page.etag)
                or (page.etag is None and page.last_modified is not None and seen.if_modified_since == page.last_modified)
            )
            if not_modified:
                response = httpx.Response(304, headers={key: value for key, value in headers.items() if key != "content-type"})
            else:
                response = httpx.Response(page.status, headers=headers, content=page.body)
        seen.status = response.status_code
        return response
