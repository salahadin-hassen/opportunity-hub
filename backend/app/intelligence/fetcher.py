"""Safe HTTP fetcher with connection pinning, SSRF prevention, and content snapshotting (plan §O, M2-T7).

Guarantees:
- Protocol whitelist: strictly http and https.
- Pre-connection & connection-level IP validation against all private, loopback,
  link-local, cloud metadata (169.254.169.254), and IPv4-mapped IPv6 addresses.
- Socket-level connection pinning via a custom HTTPCore network backend: connects
  directly to the validated IP to defeat DNS rebinding and TOCTOU races while preserving
  SNI and TLS hostname verification.
- Manual per-hop redirect following with scheme and target validation.
- True streaming byte-budget enforcement to prevent decompression bombs and memory exhaustion.
- Immutable SHA-256 content hashing for extraction provenance.
"""
from __future__ import annotations

import hashlib
import ipaddress
import socket
import urllib.parse
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable

import httpcore
import httpcore._backends.sync as sync_backend
import httpx

MAX_RESPONSE_BYTES = 5 * 1024 * 1024  # 5 MiB
DEFAULT_TIMEOUT_SECONDS = 10.0
MAX_REDIRECTS = 5

#: Deny-listed IP networks that must never be dialed.
BLOCKED_NETWORKS = (
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("100.64.0.0/10"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.0.0.0/24"),
    ipaddress.ip_network("192.0.2.0/24"),
    ipaddress.ip_network("192.88.99.0/24"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("198.18.0.0/15"),
    ipaddress.ip_network("198.51.100.0/24"),
    ipaddress.ip_network("203.0.113.0/24"),
    ipaddress.ip_network("224.0.0.0/4"),
    ipaddress.ip_network("240.0.0.0/4"),
    ipaddress.ip_network("255.255.255.255/32"),
    # IPv6
    ipaddress.ip_network("::/128"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("::ffff:0:0/96"),  # IPv4-mapped IPv6
    ipaddress.ip_network("100::/64"),
    ipaddress.ip_network("2001:db8::/32"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
    ipaddress.ip_network("ff00::/8"),
)


class FetchError(Exception):
    """Base error for fetch failures."""


class SSRFBlockedError(FetchError):
    """Raised when an address resolves to a restricted or non-public network."""


class ResponseTooLargeError(FetchError):
    """Raised when the fetched payload exceeds the size limit."""


@dataclass(frozen=True)
class FetchedDocument:
    url: str
    status_code: int
    content_type: str
    headers: dict[str, str]
    body: str
    sha256_hash: str
    fetched_at: datetime


def unmap_ipv6(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
    """Extract the underlying IPv4 address from an IPv4-mapped IPv6 address."""
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        return ip.ipv4_mapped
    return ip


def is_safe_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Verify an IP address is a globally routable public address."""
    effective_ip = unmap_ipv6(ip)
    if not effective_ip.is_global or effective_ip.is_private or effective_ip.is_loopback or effective_ip.is_link_local or effective_ip.is_multicast or effective_ip.is_reserved:
        return False
    for blocked in BLOCKED_NETWORKS:
        if effective_ip in blocked or ip in blocked:
            return False
    return True


def resolve_safe_addresses(host: str, port: int) -> list[str]:
    """Resolve a host to IP addresses and assert every returned IP is public and safe.
    
    Returns the list of validated public IP strings.
    """
    try:
        resolved = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror as error:
        raise FetchError(f"DNS resolution failed for {host!r}: {error}") from error

    if not resolved:
        raise FetchError(f"No DNS records found for {host!r}.")

    safe_ips: list[str] = []
    for entry in resolved:
        sockaddr = entry[4]
        ip_str = sockaddr[0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError as err:
            raise SSRFBlockedError(f"Invalid resolved IP address: {ip_str!r}") from err

        if not is_safe_ip(ip):
            raise SSRFBlockedError(f"Address {ip_str} for host {host!r} is not a public global IP.")
        safe_ips.append(ip_str)

    return safe_ips


class SSRFSafeBackend(sync_backend.SyncBackend):
    """Network backend that enforces SSRF checks at the TCP socket layer and pins the connection."""

    def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Any = None,
    ) -> sync_backend.SyncStream:
        # Validate all resolved IPs and pin to the first verified public IP
        safe_ips = resolve_safe_addresses(host, port)
        pinned_ip = safe_ips[0]

        # Dial the pinned IP directly: defeats DNS rebinding and TOCTOU races
        return super().connect_tcp(
            pinned_ip,
            port,
            timeout=timeout,
            local_address=local_address,
            socket_options=socket_options,
        )


class SSRFSafeTransport(httpx.HTTPTransport):
    """HTTP transport configured with the SSRF-safe connection backend."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._pool = httpcore.ConnectionPool(network_backend=SSRFSafeBackend())


def validate_url_scheme_and_host(url: str) -> tuple[str, str, int]:
    """Validate URL scheme and format before connection."""
    parsed = urllib.parse.urlparse(url)
    scheme = parsed.scheme.lower()
    if scheme not in ("http", "https"):
        raise SSRFBlockedError(f"Unsupported scheme {scheme!r}; only http/https allowed.")

    hostname = parsed.hostname
    if not hostname:
        raise SSRFBlockedError("URL lacks a valid hostname.")

    port = parsed.port or (443 if scheme == "https" else 80)
    return scheme, hostname, port


def fetch_url(
    url: str,
    *,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    max_bytes: int = MAX_RESPONSE_BYTES,
) -> FetchedDocument:
    """Safely retrieve a web resource with socket-level SSRF defense and byte budgeting."""
    current_url = url
    headers = {
        "User-Agent": "OpportunityHub-Bot/1.0 (+https://opportunities.sahelyon.com/bot)",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    client_timeout = httpx.Timeout(timeout, connect=5.0)

    for hop in range(MAX_REDIRECTS + 1):
        scheme, hostname, port = validate_url_scheme_and_host(current_url)

        # Pre-validate hostname resolution before opening the transport
        resolve_safe_addresses(hostname, port)

        transport = SSRFSafeTransport()
        with httpx.Client(
            transport=transport,
            follow_redirects=False,
            timeout=client_timeout,
            headers=headers,
        ) as client:
            try:
                with client.stream("GET", current_url) as response:
                    # Handle redirects: validate destination scheme & hop count
                    if response.status_code in (301, 302, 303, 307, 308):
                        location = response.headers.get("location")
                        if not location:
                            raise FetchError("Redirect response missing Location header.")
                        next_url = urllib.parse.urljoin(current_url, location)
                        # Verify next scheme immediately
                        next_parsed = urllib.parse.urlparse(next_url)
                        if next_parsed.scheme.lower() not in ("http", "https"):
                            raise SSRFBlockedError(f"Redirect to non-HTTP scheme {next_parsed.scheme!r} blocked.")
                        current_url = next_url
                        continue

                    # Stream payload chunk-by-chunk to enforce max_bytes without buffering bombs
                    chunks: list[bytes] = []
                    total_bytes = 0
                    for chunk in response.iter_bytes(chunk_size=16384):
                        total_bytes += len(chunk)
                        if total_bytes > max_bytes:
                            raise ResponseTooLargeError(
                                f"Response payload exceeded limit of {max_bytes} bytes."
                            )
                        chunks.append(chunk)

                    raw_content = b"".join(chunks)
                    encoding = response.encoding or "utf-8"
                    try:
                        body_text = raw_content.decode(encoding)
                    except (UnicodeDecodeError, LookupError):
                        body_text = raw_content.decode("utf-8", errors="replace")

                    sha256 = hashlib.sha256(raw_content).hexdigest()
                    now = datetime.now(timezone.utc)

                    return FetchedDocument(
                        url=str(response.url),
                        status_code=response.status_code,
                        content_type=response.headers.get("content-type", "application/octet-stream"),
                        headers=dict(response.headers),
                        body=body_text,
                        sha256_hash=sha256,
                        fetched_at=now,
                    )
            except (SSRFBlockedError, ResponseTooLargeError):
                raise
            except httpx.RequestError as exc:
                raise FetchError(f"HTTP request failed: {exc}") from exc

    raise FetchError(f"Exceeded maximum redirect limit of {MAX_REDIRECTS} hops.")
