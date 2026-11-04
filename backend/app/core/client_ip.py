"""Decide which client identity, if any, the rate limiter may count against.

``X-Forwarded-For`` is a list anyone can start: a client may send its own
value and each proxy appends to it, so the leftmost entry proves nothing.
Only entries added by proxies we trust are evidence. Strategies (see
``Settings.CLIENT_IP_STRATEGY``):

* ``peer``: the address the ASGI server reports (today's behaviour);
* ``xff_rightmost``: walking ``X-Forwarded-For`` from the right through at
  most ``TRUSTED_PROXY_HOPS`` entries, the first one that is not a trusted proxy;
* ``header``: one address from a header the trusted edge sets.

The result is a :class:`ClientIdentity`. When no trustworthy client address
can be established its ``identity`` is ``None`` and ``reason`` says why; the
caller then skips the per-address budget (the per-account budget still
applies). A missing identity is never replaced by the proxy's address or by a
constant placeholder: either would put every client behind that proxy, or
every unidentified client, into one shared bucket that a single caller could
exhaust for everyone.

Addresses are reduced to a *bucket*: an IPv4 address, or the /64 of an IPv6
address (one subscriber usually controls a whole /64, so per-address IPv6
buckets would be free to rotate).
"""
from __future__ import annotations

import ipaddress
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

IPv4or6Address = ipaddress.IPv4Address | ipaddress.IPv6Address
IPv4or6Network = ipaddress.IPv4Network | ipaddress.IPv6Network

IPV6_BUCKET_PREFIX = 64

#: Why no (or no forwarded) client identity was used. A closed set, safe as a log field or metric label.
Reason = Literal[
    "trusted_proxy_header_missing",
    "trusted_proxy_header_invalid",
    "untrusted_proxy",
    "ambiguous_forwarded_chain",
    "client_identity_unavailable",
]
REASONS: tuple[Reason, ...] = Reason.__args__  # type: ignore[attr-defined]

#: Headers whose presence on a direct connection suggests a proxy we were not told to trust.
FORWARDING_HEADERS = ("x-forwarded-for", "forwarded", "x-real-ip")


@dataclass(frozen=True)
class ClientIdentity:
    """The outcome of client-address selection for one request.

    ``identity`` is the bucket to count against, or ``None`` when no
    trustworthy one exists. ``trusted_proxy_verified`` is true when the
    identity (or the attempt to find one) came through a peer in the trusted
    proxy list. ``reason`` is set whenever ``identity`` is ``None``.
    """

    identity: str | None
    strategy: str
    reason: Reason | None = None
    trusted_proxy_verified: bool = False

    @property
    def degraded(self) -> bool:
        return self.identity is None


def parse_address(value: str | None) -> IPv4or6Address | None:
    """Parse one address as proxies write it (``1.2.3.4``, ``[::1]``, ``1.2.3.4:5678``); None if invalid."""
    if not value:
        return None
    candidate = value.strip()
    if candidate.startswith("[") and "]" in candidate:  # [IPv6] or [IPv6]:port
        candidate = candidate[1 : candidate.index("]")]
    elif candidate.count(":") == 1:  # IPv4:port
        candidate = candidate.split(":", 1)[0]
    try:
        address = ipaddress.ip_address(candidate)
    except ValueError:
        return None
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        return address.ipv4_mapped
    return address


def bucket(address: IPv4or6Address) -> str:
    """The rate-limit bucket for an address."""
    if isinstance(address, ipaddress.IPv6Address):
        return str(ipaddress.ip_network(f"{address}/{IPV6_BUCKET_PREFIX}", strict=False))
    return str(address)


def _is_trusted(address: IPv4or6Address | None, networks: Sequence[IPv4or6Network]) -> bool:
    return address is not None and any(address in network for network in networks)


def select_client_identity(
    *,
    strategy: str,
    peer: str | None,
    headers: Mapping[str, str],
    trusted_networks: Sequence[IPv4or6Network] = (),
    trusted_hops: int = 1,
    client_ip_header: str | None = None,
) -> ClientIdentity:
    """Return the client identity for one request under ``strategy`` (``headers`` keys lower-case)."""
    if strategy not in ("peer", "xff_rightmost", "header"):
        raise ValueError(f"Unknown client IP strategy {strategy!r}")

    def unavailable(reason: Reason, *, verified: bool = False) -> ClientIdentity:
        return ClientIdentity(None, strategy, reason, verified)

    peer_address = parse_address(peer)
    if peer_address is None:
        return unavailable("client_identity_unavailable")
    if _is_trusted(peer_address, trusted_networks):
        if strategy == "peer":
            # A known proxy is talking to us, and this strategy cannot see past it.
            return unavailable("client_identity_unavailable")
    else:
        if strategy != "peer" and any(name in headers for name in (*FORWARDING_HEADERS, (client_ip_header or "").lower())):
            # Either a client bypassing the edge with forged headers or a proxy missing from
            # TRUSTED_PROXY_CIDRS. In the second case the peer is shared by many clients.
            return unavailable("untrusted_proxy")
        return ClientIdentity(bucket(peer_address), strategy)

    if strategy == "header":
        value = headers.get((client_ip_header or "").lower())
        if value is None or not value.strip():
            return unavailable("trusted_proxy_header_missing", verified=True)
        # A list here means someone else wrote to the header: don't guess which entry is real.
        if "," in value:
            return unavailable("ambiguous_forwarded_chain", verified=True)
        chosen = parse_address(value)
        if chosen is None or _is_trusted(chosen, trusted_networks):
            return unavailable("trusted_proxy_header_invalid", verified=True)
        return ClientIdentity(bucket(chosen), strategy, None, True)

    # xff_rightmost: each entry was appended by the hop to its right, starting with the trusted peer.
    raw = headers.get("x-forwarded-for")
    entries = [item.strip() for item in (raw or "").split(",")]
    if raw is None or not any(entries):
        return unavailable("trusted_proxy_header_missing", verified=True)
    for position in range(1, trusted_hops + 1):
        if position > len(entries):
            break
        address = parse_address(entries[-position])
        if address is None:
            return unavailable("trusted_proxy_header_invalid", verified=True)
        if not _is_trusted(address, trusted_networks):
            return ClientIdentity(bucket(address), strategy, None, True)
    # Every entry inside the trusted hop count is itself a proxy: the chain is shorter or longer than configured.
    return unavailable("ambiguous_forwarded_chain", verified=True)


__all__ = [
    "FORWARDING_HEADERS",
    "REASONS",
    "ClientIdentity",
    "Reason",
    "bucket",
    "parse_address",
    "select_client_identity",
]
