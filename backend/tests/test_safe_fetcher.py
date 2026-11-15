"""Adversarial tests for safe HTTP fetcher, connection pinning, and SSRF defenses (M2-T7)."""
from __future__ import annotations

import io
import ipaddress
import socket
import pytest

from app.intelligence.fetcher import (
    BLOCKED_NETWORKS,
    FetchError,
    ResponseTooLargeError,
    SSRFBlockedError,
    SSRFSafeBackend,
    fetch_url,
    is_safe_ip,
    resolve_safe_addresses,
    unmap_ipv6,
    validate_url_scheme_and_host,
)


def test_blocked_networks_coverage():
    """Verify key dangerous ranges are in BLOCKED_NETWORKS."""
    assert any(ipaddress.ip_address("127.0.0.1") in net for net in BLOCKED_NETWORKS)
    assert any(ipaddress.ip_address("169.254.169.254") in net for net in BLOCKED_NETWORKS)
    assert any(ipaddress.ip_address("10.1.2.3") in net for net in BLOCKED_NETWORKS)
    assert any(ipaddress.ip_address("192.168.1.1") in net for net in BLOCKED_NETWORKS)
    assert any(ipaddress.ip_address("172.16.5.5") in net for net in BLOCKED_NETWORKS)
    assert any(ipaddress.ip_address("::1") in net for net in BLOCKED_NETWORKS)
    assert any(ipaddress.ip_address("fc00::1") in net for net in BLOCKED_NETWORKS)


def test_is_safe_ip_rejects_internal_addresses():
    assert not is_safe_ip(ipaddress.ip_address("127.0.0.1"))
    assert not is_safe_ip(ipaddress.ip_address("10.0.0.1"))
    assert not is_safe_ip(ipaddress.ip_address("172.20.0.1"))
    assert not is_safe_ip(ipaddress.ip_address("192.168.0.1"))
    assert not is_safe_ip(ipaddress.ip_address("169.254.169.254"))
    assert not is_safe_ip(ipaddress.ip_address("0.0.0.0"))
    assert not is_safe_ip(ipaddress.ip_address("::1"))


def test_is_safe_ip_rejects_ipv4_mapped_ipv6():
    """Adversarial bypass attempt: embedding internal IPv4 inside IPv6 ::ffff:."""
    mapped_loopback = ipaddress.ip_address("::ffff:127.0.0.1")
    mapped_metadata = ipaddress.ip_address("::ffff:169.254.169.254")
    mapped_private = ipaddress.ip_address("::ffff:10.0.0.1")

    assert not is_safe_ip(mapped_loopback)
    assert not is_safe_ip(mapped_metadata)
    assert not is_safe_ip(mapped_private)


def test_is_safe_ip_accepts_public_addresses():
    assert is_safe_ip(ipaddress.ip_address("8.8.8.8"))
    assert is_safe_ip(ipaddress.ip_address("1.1.1.1"))
    assert is_safe_ip(ipaddress.ip_address("93.184.216.34"))


def test_validate_url_scheme_and_host_rejects_non_http():
    with pytest.raises(SSRFBlockedError, match="Unsupported scheme 'ftp'"):
        validate_url_scheme_and_host("ftp://example.com/file")
    with pytest.raises(SSRFBlockedError, match="Unsupported scheme 'file'"):
        validate_url_scheme_and_host("file:///etc/passwd")
    with pytest.raises(SSRFBlockedError, match="Unsupported scheme 'gopher'"):
        validate_url_scheme_and_host("gopher://127.0.0.1")


def test_resolve_safe_addresses_rejects_localhost(monkeypatch):
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [(2, 1, 6, "", ("127.0.0.1", 80))],
    )
    with pytest.raises(SSRFBlockedError, match="is not a public global IP"):
        resolve_safe_addresses("localhost", 80)


def test_resolve_safe_addresses_rejects_aws_metadata(monkeypatch):
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [(2, 1, 6, "", ("169.254.169.254", 80))],
    )
    with pytest.raises(SSRFBlockedError, match="is not a public global IP"):
        resolve_safe_addresses("instance-data", 80)


def test_resolve_safe_addresses_handles_dns_failure(monkeypatch):
    def mock_gai_error(*args, **kwargs):
        raise socket.gaierror(-2, "Name or service not known")

    monkeypatch.setattr(socket, "getaddrinfo", mock_gai_error)
    with pytest.raises(FetchError, match="DNS resolution failed"):
        resolve_safe_addresses("nonexistent.invalid", 80)


def test_connect_tcp_pins_connection_to_validated_ip(monkeypatch):
    """Verify that SSRFSafeBackend dials the exact resolved public IP, defeating rebinding."""
    dialed_hosts = []

    def fake_connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        dialed_hosts.append(host)
        # return dummy object
        class DummyStream:
            pass
        return DummyStream()

    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [(2, 1, 6, "", ("93.184.216.34", 80))],
    )
    monkeypatch.setattr(
        "httpcore._backends.sync.SyncBackend.connect_tcp",
        fake_connect_tcp,
    )

    backend = SSRFSafeBackend()
    backend.connect_tcp("rebound.attacker.com", 80)

    # Must connect to the resolved IP '93.184.216.34', NEVER 'rebound.attacker.com'
    assert dialed_hosts == ["93.184.216.34"]


def test_fetch_url_enforces_streaming_byte_limits(monkeypatch):
    """Verify that oversized responses are aborted mid-stream without buffering in memory."""
    class FakeResponse:
        status_code = 200
        headers = {"content-type": "text/html"}
        encoding = "utf-8"
        url = "https://example.org/large"

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def iter_bytes(self, chunk_size=16384):
            # Yield 10 chunks of 1000 bytes = 10,000 bytes
            for _ in range(10):
                yield b"A" * 1000

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def stream(self, method, url):
            return FakeResponse()

    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [(2, 1, 6, "", ("93.184.216.34", 443))],
    )
    monkeypatch.setattr("httpx.Client", FakeClient)

    # Set max_bytes to 5000: stream should raise ResponseTooLargeError after 5 chunks
    with pytest.raises(ResponseTooLargeError, match="exceeded limit of 5000 bytes"):
        fetch_url("https://example.org/large", max_bytes=5000)


def test_public_fetch_url_pins_socket_to_validated_ip(monkeypatch):
    """Evidence: verify through public fetch_url that the outbound socket receives pinned IP."""
    dialed_addresses = []

    def mock_getaddrinfo(host, port, *args, **kwargs):
        # Resolve to verified public IP
        return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("93.184.216.34", port))]

    def mock_connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        dialed_addresses.append((host, port))
        # Return a mock SyncStream that provides a minimal valid HTTP response
        class MockStream:
            def __init__(self):
                self._sent = False

            def read(self, max_bytes=4096, timeout=None):
                if not self._sent:
                    self._sent = True
                    return b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: 13\r\n\r\nHello, world!"
                return b""

            def write(self, buffer: bytes, timeout=None):
                pass

            def close(self):
                pass

            def get_extra_info(self, info: str):
                return None

        return MockStream()

    monkeypatch.setattr(socket, "getaddrinfo", mock_getaddrinfo)
    monkeypatch.setattr("httpcore._backends.sync.SyncBackend.connect_tcp", mock_connect_tcp)

    # Call the public interface
    doc = fetch_url("http://vulnerable-domain.org/admissions")

    # The actual socket dial MUST be to the pinned IP '93.184.216.34', NEVER 'vulnerable-domain.org'
    assert dialed_addresses == [("93.184.216.34", 80)]
    assert doc.status_code == 200
    assert "Hello, world!" in doc.body


def test_public_fetch_url_blocks_redirect_to_metadata(monkeypatch):
    """Evidence: public fetch_url detects and aborts redirects targeting internal/cloud metadata."""
    responses = [
        # First hop response: 302 Redirect to cloud metadata
        b"HTTP/1.1 302 Found\r\nLocation: http://169.254.169.254/latest/meta-data\r\nContent-Length: 0\r\n\r\n",
    ]

    def mock_getaddrinfo(host, port, *args, **kwargs):
        if host == "public-site.org":
            return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("93.184.216.34", port))]
        elif host == "169.254.169.254":
            return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("169.254.169.254", port))]
        return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (host, port))]

    def mock_connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        class MockStream:
            def read(self, max_bytes=4096, timeout=None):
                if responses:
                    return responses.pop(0)
                return b""

            def write(self, buffer: bytes, timeout=None):
                pass

            def close(self):
                pass

            def get_extra_info(self, info: str):
                return None

        return MockStream()

    monkeypatch.setattr(socket, "getaddrinfo", mock_getaddrinfo)
    monkeypatch.setattr("httpcore._backends.sync.SyncBackend.connect_tcp", mock_connect_tcp)

    # Second hop to 169.254.169.254 must be blocked with SSRFBlockedError
    with pytest.raises(SSRFBlockedError, match="is not a public global IP"):
        fetch_url("http://public-site.org/redirect")


def test_public_fetch_url_blocks_redirect_to_file_scheme(monkeypatch):
    """Evidence: public fetch_url detects and aborts redirects targeting non-HTTP schemes."""
    def mock_getaddrinfo(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("93.184.216.34", port))]

    def mock_connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        class MockStream:
            def read(self, max_bytes=4096, timeout=None):
                return b"HTTP/1.1 302 Found\r\nLocation: file:///etc/passwd\r\nContent-Length: 0\r\n\r\n"

            def write(self, buffer: bytes, timeout=None):
                pass

            def close(self):
                pass

            def get_extra_info(self, info: str):
                return None

        return MockStream()

    monkeypatch.setattr(socket, "getaddrinfo", mock_getaddrinfo)
    monkeypatch.setattr("httpcore._backends.sync.SyncBackend.connect_tcp", mock_connect_tcp)

    with pytest.raises(SSRFBlockedError, match="Redirect to non-HTTP scheme 'file' blocked"):
        fetch_url("http://public-site.org/redirect-file")

