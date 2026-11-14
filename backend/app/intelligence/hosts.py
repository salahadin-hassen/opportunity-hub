"""Exact-hostname validation for the acquisition source registry.

The registry's security model is an allow-list of exact hostnames, so
every hostname is normalised to one canonical spelling (lower-case ASCII,
IDNA-encoded) and anything that is not a plain public DNS name is
rejected: wildcards, IP literals, ports, user info, paths, single-label
names and special-use domains such as ``localhost`` or ``.internal``.

Pure functions only: no DNS lookups and no network access. Resolving a
host and checking the resulting address is the fetcher's job (M2-T7).
"""
from __future__ import annotations

import ipaddress
import re

MAX_HOSTNAME_LENGTH = 253
MAX_LABEL_LENGTH = 63

_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")

#: Special-use and private-network names (RFC 6761, RFC 6762, RFC 8375, common internal suffixes).
#: A hostname equal to one of these, or ending in ``.<suffix>``, is never a valid source host.
RESERVED_SUFFIXES = frozenset(
    {
        "localhost",
        "local",
        "localdomain",
        "internal",
        "intranet",
        "lan",
        "home",
        "corp",
        "home.arpa",
        "arpa",
        "example",
        "invalid",
        "test",
        "onion",
        "example.com",
        "example.net",
        "example.org",
    }
)


class InvalidHostError(ValueError):
    """Raised when a value is not an acceptable exact public hostname."""


def normalize_host(value: str) -> str:
    """Return the canonical spelling of an exact hostname, or raise ``InvalidHostError``."""
    if not isinstance(value, str):
        raise InvalidHostError("Hostname must be a string.")
    candidate = value.strip()
    if not candidate:
        raise InvalidHostError("Hostname is empty.")
    if any(char in candidate for char in "/:@?#[]*\\ \t\r\n"):
        raise InvalidHostError(
            f"{value!r} is not a bare hostname: no scheme, path, port, user info or wildcard allowed."
        )
    if candidate.endswith("."):
        raise InvalidHostError(f"{value!r} must not end with a dot.")
    if _is_ip_literal(candidate):
        raise InvalidHostError(f"{value!r} is an IP address; sources must be named by hostname.")
    try:
        ascii_host = candidate.encode("idna").decode("ascii").lower()
    except UnicodeError as error:
        raise InvalidHostError(f"{value!r} is not a valid internationalised hostname.") from error

    if len(ascii_host) > MAX_HOSTNAME_LENGTH:
        raise InvalidHostError(f"{value!r} is longer than {MAX_HOSTNAME_LENGTH} characters.")
    labels = ascii_host.split(".")
    if len(labels) < 2:
        raise InvalidHostError(f"{value!r} is a single-label name; a public hostname is required.")
    for label in labels:
        if len(label) > MAX_LABEL_LENGTH or not _LABEL.match(label):
            raise InvalidHostError(f"{value!r} contains an invalid label {label!r}.")
    if labels[-1].isdigit():
        raise InvalidHostError(f"{value!r} has a numeric top-level label.")
    if _is_ip_literal(ascii_host):
        raise InvalidHostError(f"{value!r} is an IP address; sources must be named by hostname.")
    for suffix in RESERVED_SUFFIXES:
        if ascii_host == suffix or ascii_host.endswith("." + suffix):
            raise InvalidHostError(f"{value!r} is a special-use or private name ({suffix}).")
    return ascii_host


def is_within_domain(host: str, base_domain: str) -> bool:
    """Whether canonical ``host`` equals ``base_domain`` or is one of its subdomains."""
    return host == base_domain or host.endswith("." + base_domain)


def _is_ip_literal(value: str) -> bool:
    try:
        ipaddress.ip_address(value)
    except ValueError:
        return False
    return True
