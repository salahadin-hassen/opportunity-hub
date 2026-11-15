"""Erasmus Mundus Joint Masters: the evidence standard, applied by rule, with recorded quotes.

A programme may be approved only when ONE of its own official programme pages (a candidate the
pipeline fetched from the programme's registered site) provides quotable evidence of all three:

1. scholarship availability: a sentence on the page saying Erasmus Mundus scholarships are
   available/offered/awarded for the programme, and no sentence on the page saying they are not;
2. deadline: a specific future deadline for the current intake (the extractor's explicit date, quoted,
   after today and within 18 months), or an explicit statement that admission is rolling;
3. eligibility: at least one eligibility statement, verbatim on the page.

Title is the programme name exactly as listed in the EU Erasmus Mundus Catalogue; type is
``scholarship`` (criterion 1 is the explicit support for it). If anything is missing the programme
stays unapproved. Nothing is inferred: every value approved is a quote on the fetched page.

This is **rule-based review with spot-checks**, not human curation; the recorded evidence says so.
The same evaluation runs again in production on production's own fetches before anything is applied
there (``ingest-apply-decisions``), so a decision is never taken on trust from another database.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any

from app.intelligence.text import sentences, text_lines

STANDARD = "erasmus-mundus-evidence-v1"
REVIEW_BASIS = "rule-based review with spot-checks (not human curation)"
MAX_HORIZON = timedelta(days=548)  # a deadline beyond ~18 months is not "the current intake"

_EM = re.compile(r"erasmus\s+mundus|\bEMJM\b|\bEM\s+scholarship", re.IGNORECASE)
_SCHOLARSHIP = re.compile(r"scholarships?|grants?\b|fellowships?", re.IGNORECASE)
_AVAILABLE = re.compile(
    r"\b(available|offer(s|ed|ing)?|award(s|ed|ing)?|grant(s|ed)?|provid(es|ed|ing)|fund(s|ed|ing)?|"
    r"apply for|applying for|eligible for|receive|benefit from|will be (?:given|allocated)|cover(s|ing)?)\b",
    re.IGNORECASE,
)
_NEGATION = re.compile(
    r"\b(no|not|without|neither|nor|cannot|can't|won't|unavailable|discontinued|ended|no longer|"
    r"self-funded only|does not offer|do not offer|is not offering|are not offering)\b[^.]{0,60}"
    r"(erasmus\s+mundus\s+)?scholarships?",
    re.IGNORECASE,
)
_ROLLING = re.compile(r"\b(rolling (?:admission|basis|applications?)|applications? (?:are )?accepted (?:all year|year-round))\b",
                      re.IGNORECASE)


@dataclass
class Assessment:
    candidate_id: str
    url: str
    approvable: bool
    reasons: list[str] = field(default_factory=list)
    scholarship_quote: str | None = None
    deadline: str | None = None
    deadline_type: str | None = None
    deadline_quote: str | None = None
    eligibility_quotes: list[str] = field(default_factory=list)
    eligibility_indexes: list[int] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _sentences(text: str) -> list[str]:
    out: list[str] = []
    for line in text_lines(text):
        out.extend(s.strip() for s in sentences(line) if s.strip())
    return out


def scholarship_evidence(text: str) -> tuple[str | None, str | None]:
    """(quote of availability, quote of unavailability), each a verbatim sentence of the page or None.

    A statement anywhere on the page that Erasmus Mundus scholarships are not available outweighs any
    availability statement: such a page is never approved by rule.
    """
    available = negation = None
    for sentence in _sentences(text):
        if len(sentence) > 600 or not _EM.search(sentence):
            continue
        if negation is None and _NEGATION.search(sentence):
            negation = sentence
        elif available is None and _SCHOLARSHIP.search(sentence) and _AVAILABLE.search(sentence):
            available = sentence
    return available, negation


def assess(candidate: Any, *, today: date) -> Assessment:
    """Apply the standard to one fetched candidate page. ``candidate`` is an IngestionCandidate."""
    text = candidate.page_text or ""
    extraction = candidate.extraction or {}
    result = Assessment(candidate_id=str(candidate.id), url=candidate.final_url or candidate.url, approvable=False)
    if not text:
        result.reasons.append("no fetched page text")
        return result

    # 1. scholarship availability
    quote, negation = scholarship_evidence(text)
    if negation:
        result.reasons.append(f"page states scholarships are not available: {negation[:160]!r}")
    elif not quote:
        result.reasons.append("no quotable statement that Erasmus Mundus scholarships are available")
    else:
        result.scholarship_quote = quote

    # 2. deadline (future, current intake) or explicit rolling admission
    deadline = extraction.get("deadline") or {}
    deadline_type = extraction.get("deadline_type") or {}
    if deadline.get("status") == "explicit" and isinstance(deadline.get("value"), str):
        try:
            when = date.fromisoformat(deadline["value"][:10])
        except ValueError:
            when = None
        evidence = [e.get("quote") for e in deadline.get("evidence") or [] if e.get("location") == "text"]
        dq = next((q for q in evidence if q and q in text), None)
        if when is None or dq is None:
            result.reasons.append("deadline has no verbatim quote on the page")
        elif when < today:
            result.reasons.append(f"deadline {when} has passed (not the current intake)")
        elif when - today > MAX_HORIZON:
            result.reasons.append(f"deadline {when} is too far ahead to be the current intake")
        else:
            result.deadline, result.deadline_type, result.deadline_quote = when.isoformat(), "fixed", dq
    elif deadline.get("status") in ("conflicting", "ambiguous"):
        result.reasons.append(f"deadline is {deadline.get('status')} on the page; needs a person to choose")
    else:
        rolling = next((s for s in _sentences(text) if _ROLLING.search(s)), None)
        if rolling and deadline_type.get("value") == "rolling":
            result.deadline_type, result.deadline_quote = "rolling", rolling
        else:
            result.reasons.append("no specific future deadline and no explicit rolling-admission statement")

    # 3. eligibility
    eligibility = extraction.get("eligibility") or {}
    statements = eligibility.get("value") if eligibility.get("status") == "explicit" else None
    if statements:
        kept = [(i, s) for i, s in enumerate(statements) if isinstance(s, str) and s in text]
        result.eligibility_indexes = [i for i, _ in kept]
        result.eligibility_quotes = [s for _, s in kept]
    if not result.eligibility_quotes:
        result.reasons.append("no eligibility statement quoted from the page")

    result.approvable = not result.reasons
    return result


def evidence_record(assessment: Assessment, *, catalogue_title: str, checked_at: datetime) -> dict[str, Any]:
    """What is stored with an approval (source snapshot, audit entry, decisions manifest)."""
    return {
        "standard": STANDARD,
        "review_basis": REVIEW_BASIS,
        "catalogue_title": catalogue_title,
        "programme_page": assessment.url,
        "checked_at": checked_at.astimezone(timezone.utc).isoformat(),
        "scholarship_quote": assessment.scholarship_quote,
        "deadline": assessment.deadline,
        "deadline_type": assessment.deadline_type,
        "deadline_quote": assessment.deadline_quote,
        "eligibility_quotes": assessment.eligibility_quotes,
    }


def page_mentions_programme(text: str, title: str) -> bool:
    """For a host shared by several programmes: the page must name this programme."""
    return title.casefold() in (text or "").casefold()


# --- running the review over a batch ---------------------------------------------------------------

@dataclass
class ProgrammeDecision:
    source: str
    catalogue_title: str
    decision: str  # approved | not_approved | no_pages
    reasons: list[str] = field(default_factory=list)
    candidate_id: str | None = None
    opportunity_id: str | None = None
    evidence: dict[str, Any] | None = None
    pages_checked: int = 0


def run_review(db: Any, sources_payload: dict, *, actor_id: Any, today: date, apply: bool) -> list[ProgrammeDecision]:
    """Evaluate every catalogue programme's fetched pages; with ``apply``, approve and publish the ones
    that meet the standard (one record per programme), storing the evidence. Others stay unapproved."""
    from sqlalchemy import select

    from app.intelligence import pipeline
    from app.models import AcquisitionSource, IngestionCandidate, Opportunity, Source
    from app.models.ingestion import CandidateState
    from app.services import audit
    from app.services.opportunities import publish_opportunity

    decisions: list[ProgrammeDecision] = []
    existing_titles = {t.casefold() for t in db.scalars(select(Opportunity.title))}
    for raw in sources_payload["sources"]:
        source = db.scalar(select(AcquisitionSource).where(AcquisitionSource.name == raw["name"]))
        programmes = raw.get("_catalogue") or []
        for programme in programmes:
            title = programme["title"]
            decision = ProgrammeDecision(source=raw["name"], catalogue_title=title, decision="not_approved")
            decisions.append(decision)
            if source is None:
                decision.decision, decision.reasons = "no_pages", ["source not registered"]
                continue
            if title.casefold() in existing_titles:
                decision.reasons = ["already in the catalogue under this title (duplicate)"]
                continue
            candidates = list(db.scalars(select(IngestionCandidate).where(
                IngestionCandidate.source_id == source.id, IngestionCandidate.page_text.is_not(None))))
            if len(programmes) > 1:
                candidates = [c for c in candidates if page_mentions_programme(c.page_text, title)]
            decision.pages_checked = len(candidates)
            if not candidates:
                decision.decision = "no_pages"
                decision.reasons = ["no fetched page from this programme's site" if len(programmes) == 1
                                    else "no fetched page names this programme"]
                continue
            assessed = [(c, assess(c, today=today)) for c in candidates]
            good = [(c, a) for c, a in assessed
                    if a.approvable and c.state == CandidateState.NEEDS_REVIEW]
            if not good:
                # report the closest page's reasons (fewest missing criteria)
                c, a = min(assessed, key=lambda pair: len(pair[1].reasons))
                decision.candidate_id = str(c.id)
                decision.reasons = a.reasons or [f"candidate is {c.state}, not reviewable"]
                continue
            c, a = max(good, key=lambda pair: (pair[0].quality_score or 0, -len(pair[1].url)))
            checked_at = c.fetched_at or datetime.now(timezone.utc)
            record = evidence_record(a, catalogue_title=title, checked_at=checked_at)
            decision.decision, decision.candidate_id, decision.evidence = "approved", str(c.id), record
            if not apply:
                continue
            opportunity = pipeline.approve_candidate(db, c.id, actor_id=actor_id, decision=pipeline.ApprovalInput(
                title=title, opportunity_type="scholarship",
                deadline=date.fromisoformat(a.deadline) if a.deadline else None,
                deadline_type=a.deadline_type, statements=a.eligibility_indexes, countries=[],
                notes=f"{STANDARD}: {REVIEW_BASIS}",
            ))
            snapshot = db.scalar(select(Source).where(Source.opportunity_id == opportunity.id, Source.is_primary))
            snapshot.raw_snapshot = {**(snapshot.raw_snapshot or {}), "evidence": record}
            db.flush()
            publish_opportunity(db, opportunity.id)
            audit.record(db, action="opportunity.published_by_rule", target_type="opportunity", target_id=opportunity.id,
                         actor_id=actor_id, changes={"standard": STANDARD, "review_basis": REVIEW_BASIS,
                                                     "candidate_id": str(c.id), "evidence": record},
                         reason=f"{STANDARD}: {REVIEW_BASIS}")
            decision.opportunity_id = str(opportunity.id)
            existing_titles.add(title.casefold())
    return decisions


__all__ = ["Assessment", "ProgrammeDecision", "run_review", "REVIEW_BASIS", "STANDARD", "assess", "evidence_record", "page_mentions_programme",
           "scholarship_evidence"]
