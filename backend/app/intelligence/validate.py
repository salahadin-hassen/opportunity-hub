"""Deterministic validation of an extraction against the page it came from.

Produces ``problems`` (what a curator must resolve before the record could be published),
``warnings`` (worth a look) and a 0-100 ``quality_score`` that only orders the review queue. Nothing
here approves or publishes anything, and a high score is not verification.

Evidence check: every quote whose location is ``text`` must occur verbatim in the page's normalised
text. A field whose evidence fails is downgraded to ``not_found`` (its value is dropped), so an
extractor bug, or a future model-based extractor that paraphrases or invents, can't carry an
unsupported claim forward.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from urllib.parse import urlsplit

from app.intelligence.extract import ExtractedField, Extraction

VALIDATOR_VERSION = "validate-1"
#: Below this relevance the page is treated as "not an opportunity page" and rejected by the pipeline.
MIN_RELEVANCE = 35

_FIELDS = (
    "title", "organization", "opportunity_type", "official_url", "description", "deadline", "deadline_type",
    "opening_date", "eligibility", "applicant_groups", "benefits", "application_instructions", "application_status",
)


@dataclass
class ValidationResult:
    problems: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    unsupported_fields: list[str] = field(default_factory=list)
    expired: bool = False
    irrelevant: bool = False
    quality_score: int = 0

    def as_dict(self) -> dict:
        return {
            "validator_version": VALIDATOR_VERSION,
            "problems": self.problems,
            "warnings": self.warnings,
            "unsupported_fields": self.unsupported_fields,
            "expired": self.expired,
            "irrelevant": self.irrelevant,
        }


def enforce_evidence(extraction: Extraction, page_text: str) -> list[str]:
    """Drop every field whose ``text`` evidence is not verbatim in ``page_text``; return their names."""
    unsupported: list[str] = []
    for name in _FIELDS:
        item: ExtractedField = getattr(extraction, name)
        if item.status == "not_found":
            continue
        quotes = [evidence.quote for evidence in item.evidence if evidence.location == "text"]
        if any(quote not in page_text for quote in quotes) or (item.status != "not_found" and not item.evidence):
            setattr(extraction, name, ExtractedField(note="dropped: evidence not found verbatim on the page"))
            unsupported.append(name)
    return unsupported


def _future(value: str | None, today: date) -> bool | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value) >= today
    except ValueError:
        return None


def validate(extraction: Extraction, page_text: str, *, allowed_hosts: frozenset[str], today: date) -> ValidationResult:
    result = ValidationResult()
    result.unsupported_fields = enforce_evidence(extraction, page_text)
    for name in result.unsupported_fields:
        result.problems.append(f"{name}: extracted evidence does not appear on the page; field dropped")

    if extraction.relevance < MIN_RELEVANCE:
        result.irrelevant = True
        result.problems.append(
            f"does not look like an opportunity page (relevance {extraction.relevance}; "
            f"signals: {', '.join(extraction.relevance_signals) or 'none'})"
        )

    if extraction.title.status == "not_found" or not str(extraction.title.value or "").strip():
        result.problems.append("title not found")

    url = str(extraction.official_url.value or "")
    parts = urlsplit(url)
    if parts.scheme != "https":
        result.problems.append("official URL is not https")
    if (parts.hostname or "") not in allowed_hosts:
        result.problems.append("official URL is not on one of the source's approved hosts")

    deadline = extraction.deadline
    deadline_type = extraction.deadline_type
    if deadline.status == "explicit":
        if deadline.note:
            result.warnings.append(f"deadline: {deadline.note}")
        upcoming = _future(deadline.value, today)
        if upcoming is False:
            result.expired = True
            result.warnings.append(f"deadline {deadline.value} has passed")
    elif deadline.status == "conflicting":
        dates = [value for value in (deadline.value or []) if _future(value, today)]
        result.problems.append(
            "the page states several deadlines; a curator must choose the one for this cycle"
            + ("" if dates else " (all of them have passed)")
        )
        if not dates:
            result.expired = True
    elif deadline.status == "ambiguous":
        result.problems.append(f"deadline is ambiguous ({deadline.note or 'unresolved'}); not guessed")
    elif deadline_type.status == "explicit" and deadline_type.value in ("rolling", "none"):
        pass
    else:
        result.problems.append("no deadline or rolling/no-deadline statement found")

    status = extraction.application_status
    if status.status == "explicit" and status.value == "closed":
        result.expired = True
        result.warnings.append(f"the page says applications are closed: {status.evidence[0].quote!r}")
    elif status.status == "conflicting":
        result.warnings.append("the page says both that applications are closed and that they are open")

    opening = extraction.opening_date
    if opening.status == "explicit" and deadline.status == "explicit":
        if str(opening.value) > str(deadline.value):
            result.problems.append(f"opening date {opening.value} is after the deadline {deadline.value}")

    if extraction.eligibility.status != "explicit" or not extraction.eligibility.value:
        result.problems.append("no eligibility statement found (publication needs at least one quoted rule)")

    if extraction.benefits.status == "not_found":
        result.warnings.append("no funding or benefit statement found")
    if extraction.opportunity_type.status == "not_found":
        result.warnings.append("category not recognised; a curator must choose one")
    elif extraction.opportunity_type.status == "inferred":
        result.warnings.append(f"category {extraction.opportunity_type.value!r} inferred from wording")
    if extraction.description.status == "not_found":
        result.warnings.append("no description found")

    score = 0
    score += 20 if extraction.title.status == "explicit" else 0
    score += 25 if deadline.status == "explicit" and not result.expired else 0
    score += 10 if deadline_type.status == "explicit" and deadline.status != "explicit" else 0
    score += min(25, 5 * len(extraction.eligibility.value or [])) if extraction.eligibility.status == "explicit" else 0
    score += 10 if extraction.benefits.status == "explicit" else 0
    score += 10 if extraction.application_instructions.status == "explicit" else 0
    score += 5 if extraction.description.status == "explicit" else 0
    score -= 10 * len(result.problems) + 5 * len(result.warnings)
    result.quality_score = max(0, min(100, score))
    return result


__all__ = ["MIN_RELEVANCE", "VALIDATOR_VERSION", "ValidationResult", "enforce_evidence", "validate"]
