"""Exact-hostname validation for the acquisition source registry (pure, no network)."""
from __future__ import annotations

import pytest

from app.intelligence.hosts import InvalidHostError, is_within_domain, normalize_host


@pytest.mark.parametrize(
    ("raw", "canonical"),
    [
        ("careers.cern", "careers.cern"),
        ("  Admissions.KAUST.edu.sa ", "admissions.kaust.edu.sa"),
        ("www.aau.edu.et", "www.aau.edu.et"),
        ("bücher.de", "xn--bcher-kva.de"),
        ("a-b.example-uni.ac.uk", "a-b.example-uni.ac.uk"),
    ],
)
def test_valid_hosts_are_normalised(raw, canonical):
    assert normalize_host(raw) == canonical


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "   ",
        "*.cern",
        "https://careers.cern",
        "careers.cern/programmes",
        "careers.cern:443",
        "user@careers.cern",
        "careers.cern.",
        "careers cern",
        "localhost",
        "intranet",
        "app.localhost",
        "printer.local",
        "db.internal",
        "router.home.arpa",
        "anything.example.com",
        "site.test",
        "hidden.onion",
        "1.1.1.1",
        "127.0.0.1",
        "169.254.169.254",
        "::1",
        "[::1]",
        "2130706433",
        "-bad.example-uni.edu",
        "bad-.example-uni.edu",
        "under_score.example-uni.edu",
        "a" * 64 + ".edu",
        ".".join(["abcdefgh"] * 32) + ".edu",
        "host.123",
    ],
)
def test_invalid_hosts_are_rejected(raw):
    with pytest.raises(InvalidHostError):
        normalize_host(raw)


def test_non_string_is_rejected():
    with pytest.raises(InvalidHostError):
        normalize_host(None)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("host", "base", "inside"),
    [
        ("careers.cern", "careers.cern", True),
        ("www.careers.cern", "careers.cern", True),
        ("evilcareers.cern", "careers.cern", False),
        ("careers.cern.evil.org", "careers.cern", False),
        ("cern", "careers.cern", False),
    ],
)
def test_is_within_domain_requires_a_label_boundary(host, base, inside):
    assert is_within_domain(host, base) is inside
