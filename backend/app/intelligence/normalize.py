"""Deterministic normalisation: canonical URLs, dates, titles and opportunity categories.

Nothing here guesses. A date without a year, or a numeric date whose day and month could be swapped,
is reported as ambiguous rather than resolved; an unknown category stays ``other``.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from app.intelligence.hosts import InvalidHostError, normalize_host
from app.models.enums import OpportunityType

#: Query parameters that only track the visitor; dropped from canonical URLs.
_TRACKING_PARAMS = re.compile(r"^(utm_[a-z]+|gclid|fbclid|mc_cid|mc_eid|_hsenc|_hsmi)$", re.IGNORECASE)


def canonical_url(url: str) -> str:
    """Lower-case scheme and host, no default port, no fragment, no tracking parameters, no trailing slash."""
    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower()
    try:
        host = normalize_host(parts.hostname or "")
    except InvalidHostError:
        host = (parts.hostname or "").lower()
    port = parts.port
    netloc = host if port in (None, 80 if scheme == "http" else 443) else f"{host}:{port}"
    query = urlencode([(key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True)
                       if not _TRACKING_PARAMS.match(key)])
    path = re.sub(r"/{2,}", "/", parts.path or "/")
    if len(path) > 1:
        path = path.rstrip("/")
    return urlunsplit((scheme, netloc, path, query, ""))


def normalise_title(value: str) -> str:
    """A comparison key for titles: NFKC, case-folded, punctuation and years removed, spaces folded."""
    value = unicodedata.normalize("NFKC", value).casefold()
    value = re.sub(r"\b(19|20)\d{2}\b", " ", value)
    value = re.sub(r"[^\w\s]", " ", value)
    return " ".join(value.split())


_MONTHS = {
    name: index
    for index, names in enumerate(
        (
            ("january", "jan"), ("february", "feb"), ("march", "mar"), ("april", "apr"), ("may",),
            ("june", "jun"), ("july", "jul"), ("august", "aug"), ("september", "sep", "sept"),
            ("october", "oct"), ("november", "nov"), ("december", "dec"),
        ),
        start=1,
    )
    for name in names
}
_MONTH = r"(january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|jun|jul|aug|sept|sep|oct|nov|dec)\.?"
_DAY = r"(\d{1,2})(?:st|nd|rd|th)?"
_YEAR = r"((?:19|20)\d{2})"

#: (pattern, kind) in priority order; every match is reported with its span.
_DATE_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(rf"\b{_YEAR}-(\d{{1,2}})-(\d{{1,2}})\b"), "iso"),
    (re.compile(rf"\b{_DAY}\s+(?:of\s+)?{_MONTH},?\s+{_YEAR}\b", re.IGNORECASE), "dmy"),
    (re.compile(rf"\b{_MONTH}\s+{_DAY},?\s+{_YEAR}\b", re.IGNORECASE), "mdy"),
    (re.compile(rf"\b(\d{{1,2}})[./](\d{{1,2}})[./]{_YEAR}\b"), "numeric"),
    (re.compile(rf"\b{_DAY}\s+{_MONTH}(?!,?\s+(?:19|20)\d{{2}})\b", re.IGNORECASE), "dm_noyear"),
    (re.compile(rf"\b{_MONTH}\s+{_DAY}(?!,?\s+(?:19|20)\d{{2}})(?!\d)\b", re.IGNORECASE), "md_noyear"),
)


@dataclass(frozen=True)
class DateMention:
    """A date found in text: ``value`` is None when it can't be resolved without guessing."""

    text: str
    start: int
    value: date | None
    status: str  # "explicit" or "ambiguous"
    reason: str | None = None


def _safe_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def find_dates(text: str) -> list[DateMention]:
    """Every date mention in ``text``, left to right, without overlaps."""
    found: list[DateMention] = []
    taken: list[tuple[int, int]] = []
    for pattern, kind in _DATE_PATTERNS:
        for match in pattern.finditer(text):
            span = match.span()
            if any(span[0] < end and start < span[1] for start, end in taken):
                continue
            groups = match.groups()
            mention: DateMention | None = None
            if kind == "iso":
                value = _safe_date(int(groups[0]), int(groups[1]), int(groups[2]))
                mention = DateMention(match.group(0), span[0], value, "explicit" if value else "ambiguous",
                                      None if value else "invalid date")
            elif kind == "dmy":
                value = _safe_date(int(groups[2]), _MONTHS[groups[1].lower()], int(groups[0]))
                mention = DateMention(match.group(0), span[0], value, "explicit" if value else "ambiguous",
                                      None if value else "invalid date")
            elif kind == "mdy":
                value = _safe_date(int(groups[2]), _MONTHS[groups[0].lower()], int(groups[1]))
                mention = DateMention(match.group(0), span[0], value, "explicit" if value else "ambiguous",
                                      None if value else "invalid date")
            elif kind == "numeric":
                first, second, year = int(groups[0]), int(groups[1]), int(groups[2])
                if first > 12 and second <= 12:
                    value = _safe_date(year, second, first)
                elif second > 12 and first <= 12:
                    value = _safe_date(year, first, second)
                else:
                    value = None
                mention = DateMention(match.group(0), span[0], value, "explicit" if value else "ambiguous",
                                      None if value else "day and month order unknown")
            else:  # no year: never assume one
                mention = DateMention(match.group(0), span[0], None, "ambiguous", "no year given")
            if mention is not None:
                found.append(mention)
                taken.append(span)
    return sorted(found, key=lambda item: item.start)


_CATEGORY_KEYWORDS: tuple[tuple[OpportunityType, tuple[str, ...]], ...] = (
    (OpportunityType.HACKATHON, ("hackathon",)),
    (OpportunityType.OPEN_SOURCE_PROGRAM, ("summer of code", "open source program", "open-source program")),
    (OpportunityType.FELLOWSHIP, ("fellowship", "fellows programme", "fellows program")),
    (OpportunityType.SCHOLARSHIP, ("scholarship", "bursary", "studentship")),
    (OpportunityType.INTERNSHIP, ("internship", "intern program", "intern programme", "trainee")),
    (OpportunityType.SUMMER_SCHOOL, ("summer school", "winter school")),
    (OpportunityType.RESEARCH_PROGRAM, ("research program", "research programme", "research experience",
                                         "visiting student", "undergraduate research", "summer research")),
    (OpportunityType.COMPETITION, ("competition", "challenge", "olympiad", "contest", "prize")),
    (OpportunityType.GRANT, ("grant", "funding call", "call for proposals")),
    (OpportunityType.CONFERENCE, ("conference", "symposium", "summit")),
)


def infer_category(*texts: str | None) -> OpportunityType | None:
    """The first category whose keywords appear in the given texts (title first), or None."""
    haystack = " ".join(value for value in texts if value).casefold()
    for category, keywords in _CATEGORY_KEYWORDS:
        if any(keyword in haystack for keyword in keywords):
            return category
    return None


__all__ = ["DateMention", "canonical_url", "find_dates", "infer_category", "normalise_title"]
