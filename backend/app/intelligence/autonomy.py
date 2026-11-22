"""Autonomous review: approve and publish candidates without a person, when nothing needs one.

How far automation goes is the source's publish mode, a trust ladder an admin raises one step at a
time (see ``lifecycle``; leaving ``approved`` drops it back to ``off``, so automation fails closed):

- ``off``           nothing automatic; every candidate waits for a curator (the default);
- ``shadow``        the decision is computed and recorded on the candidate, nothing else happens,
                    so an admin can see what automation would do before trusting it;
- ``listing_only``  candidates that pass every check become drafts automatically;
- ``full``          candidates that pass every check are drafted and published automatically.

Every check must pass, or the candidate is held for a person with the reasons listed. The checks
are deliberately conservative: an explicit future deadline (or an explicit rolling one), a title
taken from the page, at least two eligibility rules quoted verbatim from the page, a trusted
official source, a clean validation, and, when AI review is on, the model agreeing that the page is
one open opportunity, with any deadline it found agreeing with the rule-based one. Without AI the
rule-based extraction alone must clear a higher bar. Automatic actions go through the same code as a
curator's (``approve_candidate``, ``publish_opportunity`` with its publication checks) and are
audited as system actions.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.intelligence import ai_review
from app.intelligence.extract import Extraction
from app.models import AcquisitionSource, IngestionCandidate, Opportunity
from app.models.enums import AuthorityLevel, OpportunityStatus, PublishMode, SourceStatus, TermsStatus
from app.models.ingestion import CandidateState
from app.services import audit

logger = logging.getLogger(__name__)

POLICY_VERSION = "autonomy-5"
#: Validation problems that only say the rule-based reader found nothing. The AI may fill these gaps, and
#: the deadline and quoted-rules checks below still demand verified evidence; any other problem holds.
FILLABLE_PROBLEM = re.compile(
    r"^no deadline|^deadline is ambiguous|^no eligibility statement|^deadline(_type)?: extracted evidence does not appear", re.IGNORECASE
)
MIN_STATEMENTS = 2
MIN_QUALITY_WITHOUT_AI = 60
MIN_AI_CONFIDENCE = 0.7
GENERIC_TITLE = re.compile(
    r"^(home|homepage|welcome|overview|about|eligibility( criteria)?|selection criteria|criteria|apply( now)?|how to apply|"
    r"application( process| timeline)?|applications?|admissions?|scholarships?|programmes?|programs?|faqs?|apply for scholarship|"
    r"check eligibility criteria|criteria & scholarship programs)$",
    re.IGNORECASE,
)


@dataclass
class Check:
    name: str
    passed: bool
    detail: str


@dataclass
class Decision:
    outcome: str  # "publish" | "draft" | "hold"
    mode: str
    checks: list[Check] = field(default_factory=list)
    title: str | None = None
    opportunity_type: str | None = None
    deadline: date | None = None
    deadline_type: str | None = None
    deadline_unannounced: bool = False
    statements: list[str] = field(default_factory=list)
    ai: dict[str, Any] | None = None

    @property
    def held_because(self) -> list[str]:
        return [check.detail for check in self.checks if not check.passed]

    def as_dict(self, content_hash: str | None, acted: str) -> dict[str, Any]:
        return {
            "policy": POLICY_VERSION,
            "decided_at": datetime.now(timezone.utc).isoformat(),
            "mode": self.mode,
            "outcome": self.outcome,
            "acted": acted,
            "content_hash": content_hash,
            "checks": [check.__dict__ for check in self.checks],
            "title": self.title,
            "opportunity_type": self.opportunity_type,
            "deadline": self.deadline.isoformat() if self.deadline else None,
            "deadline_type": self.deadline_type,
            "deadline_unannounced": self.deadline_unannounced,
            "statements": self.statements,
            "ai": self.ai,
            # Held only because the AI was out of quota or failed: decide again on the next run.
            "retry": any(check.name == "AI review" and not check.passed and "unavailable" in check.detail for check in self.checks),
        }


def _field(extraction: Extraction, name: str):
    item = getattr(extraction, name)
    return item.value if item.status in ("explicit", "inferred") else None


def _hard_problems(validation: dict[str, Any]) -> list[str]:
    return [str(p) for p in validation.get("problems") or [] if not FILLABLE_PROBLEM.search(str(p))]


def decide(
    candidate: IngestionCandidate, source: AcquisitionSource, *, today: date, ai: ai_review.AIReview | None, use_ai: bool, ai_asked: bool = True
) -> Decision:
    """Pure decision (no writes): which checks pass, and what an automatic action would use."""
    mode = str(source.publish_mode)
    decision = Decision(outcome="hold", mode=mode, ai=ai.as_dict() if ai else None)
    checks = decision.checks
    extraction = Extraction.model_validate(candidate.extraction or {})
    validation = candidate.validation or {}
    page = candidate.page_text or ""

    trusted = source.status == SourceStatus.APPROVED and source.authority_level == AuthorityLevel.OFFICIAL and source.terms_status == TermsStatus.ACCEPTABLE
    checks.append(Check("trusted source", trusted, "The source must be approved, official, with acceptable terms."))
    hard = _hard_problems(validation)
    clean = not hard and not validation.get("irrelevant") and not validation.get("expired") and not candidate.duplicate_of_candidate_id and not candidate.duplicate_of_opportunity_id
    detail = f"Validation found problems: {'; '.join(hard[:3])}" if hard else "The page is irrelevant, expired or a duplicate."
    checks.append(Check("clean validation", clean, detail))
    warnings = [str(w).lower() for w in validation.get("warnings") or []]
    new_cycle = any("possible new cycle" in w for w in warnings)
    checks.append(Check("not a new cycle", not new_cycle, "This may be a new cycle of an existing opportunity; a person links it to the earlier record."))
    several_deadlines = any("mentions deadlines in" in w or "several deadlines" in w for w in warnings)
    open_and_closed = any("both that applications are closed and that they are open" in w for w in warnings)

    # Title: the model's verified title, else a non-generic rule-based one.
    rule_title = extraction.title.value if extraction.title.status == "explicit" else None
    title = (ai.title if ai and ai.title else None) or rule_title
    good_title = bool(title) and not GENERIC_TITLE.match((title or "").strip())
    checks.append(Check("specific title", good_title, f"The title “{title or ''}” is missing or too generic (e.g. “Home”, “Eligibility”)."))
    decision.title = title

    decision.opportunity_type = (ai.opportunity_type if ai and ai.opportunity_type else None) or _field(extraction, "opportunity_type")
    checks.append(Check("type", bool(decision.opportunity_type), "No opportunity type was recognised."))

    # Deadline: explicit and in the future, or explicitly rolling. Rule-based and AI must agree when both exist.
    rule_deadline = None
    if extraction.deadline.status == "explicit" and extraction.deadline.value:
        try:
            rule_deadline = date.fromisoformat(str(extraction.deadline.value))
        except ValueError:
            rule_deadline = None
    rule_rolling = extraction.deadline_type.status == "explicit" and extraction.deadline_type.value in ("rolling", "none")
    ai_deadline = ai.deadline if ai and ai.deadline_kind == "fixed" else None
    ai_rolling = bool(ai and ai.deadline_kind in ("rolling", "none") and ai.deadline_quote)
    if several_deadlines:
        # The page gives several dates: trust the rule-based one only when the AI independently reads the same.
        agreed = bool(rule_deadline and ai_deadline and rule_deadline == ai_deadline)
        checks.append(Check("one clear deadline", agreed, "The page mentions several deadlines; the AI must independently read the same one."))
    if open_and_closed:
        resolved = bool(ai and ai.applications in ("open", "upcoming"))
        checks.append(Check("open or closed", resolved, "The page says both that applications are open and that they are closed."))
    if rule_deadline and ai_deadline and rule_deadline != ai_deadline:
        checks.append(Check("deadline", False, f"Two different deadlines were read ({rule_deadline} and {ai_deadline}); a person should check."))
    else:
        deadline = rule_deadline or ai_deadline
        if deadline:
            future = deadline > today
            checks.append(Check("deadline", future, f"The deadline {deadline} has passed."))
            decision.deadline, decision.deadline_type = deadline, "fixed"
        elif (rule_rolling or ai_rolling) and (not use_ai or ai_rolling):
            # "No deadline" is a strong claim: with AI on, the model must read it independently too.
            checks.append(Check("deadline", True, "Rolling or no deadline, as the page states."))
            decision.deadline_type = (extraction.deadline_type.value if rule_rolling else ai.deadline_kind) if (rule_rolling or ai) else None
        elif rule_rolling:
            checks.append(Check("deadline", False, "Only the rule-based reader saw a rolling deadline; the AI did not confirm it."))
        elif use_ai and ai is not None and ai.applications != "closed" and ai.deadline_kind == "unknown" and not validation.get("expired"):
            # The page gives no date for this cycle and doesn't say applications are closed: list it as
            # "deadline not announced, check the official page" (never an invented date).
            checks.append(Check("deadline", True, "No date announced on the page; listed as “check the official page”."))
            decision.deadline_type, decision.deadline_unannounced = "fixed", True
        else:
            checks.append(Check("deadline", False, "No deadline with a year (and no explicit rolling deadline) was found."))

    # Eligibility: rule-based statements plus the model's verified ones, each an exact substring of the page.
    statements: list[str] = []
    for statement in list(_field(extraction, "eligibility") or []) + (ai.statements if ai else []):
        if isinstance(statement, str) and statement in page and statement not in statements:
            statements.append(statement)
    decision.statements = statements[:15]
    checks.append(Check("quoted rules", len(decision.statements) >= MIN_STATEMENTS, f"Fewer than {MIN_STATEMENTS} eligibility rules were quoted from the page."))

    if use_ai:
        if ai is None and not ai_asked:
            checks.append(Check("AI review", False, "Not asked: the checks above already fail."))
        elif ai is None:
            checks.append(Check("AI review", False, "The AI review was unavailable (rate limit or error); held for a person."))
        else:
            checks.append(Check("AI: opportunity page", ai.is_opportunity_page and ai.single_opportunity, "The AI read this as not one single opportunity."))
            checks.append(Check("AI: open", ai.applications != "closed", "The AI read applications as closed."))
            checks.append(Check("AI: confidence", ai.confidence >= MIN_AI_CONFIDENCE, f"The AI's confidence ({ai.confidence:.2f}) is below {MIN_AI_CONFIDENCE}."))
    else:
        quality = candidate.quality_score or 0
        checks.append(Check("quality (no AI)", quality >= MIN_QUALITY_WITHOUT_AI, f"Without AI review, quality must be at least {MIN_QUALITY_WITHOUT_AI} (it is {quality})."))
        checks.append(Check("rule-based deadline (no AI)", bool(rule_deadline or rule_rolling), "Without AI review, the deadline must come from the rule-based reader."))

    if all(check.passed for check in checks):
        # Shadow reports what full automation would do; listing_only stops at a draft.
        decision.outcome = "draft" if mode == PublishMode.LISTING_ONLY else "publish"
    return decision


def _cheap_gates_pass(candidate: IngestionCandidate, source: AcquisitionSource) -> bool:
    """The checks that need no AI: skip the model (and the free-tier quota) when these already fail."""
    validation = candidate.validation or {}
    return (
        source.status == SourceStatus.APPROVED
        and source.authority_level == AuthorityLevel.OFFICIAL
        and source.terms_status == TermsStatus.ACCEPTABLE
        and not _hard_problems(validation)
        and not validation.get("irrelevant")
        and not validation.get("expired")
        and not candidate.duplicate_of_candidate_id
        and not candidate.duplicate_of_opportunity_id
    )


def run(db: Session, *, today: date | None = None, limit: int = 50) -> dict[str, int]:
    """Decide every reviewable candidate of a source above ``off``; act as its mode allows. Commits per candidate."""
    from app.intelligence import pipeline
    from app.services.opportunities import IncompleteOpportunityError, publish_opportunity

    today = today or datetime.now(timezone.utc).date()
    use_ai = ai_review.enabled()
    counts = {"published": 0, "drafted": 0, "shadow": 0, "held": 0, "skipped": 0}
    rows = db.execute(
        select(IngestionCandidate, AcquisitionSource)
        .join(AcquisitionSource, AcquisitionSource.id == IngestionCandidate.source_id)
        .where(IngestionCandidate.state == CandidateState.NEEDS_REVIEW, AcquisitionSource.publish_mode != PublishMode.OFF)
        .order_by(IngestionCandidate.quality_score.desc().nulls_last())
    ).all()
    decided = 0
    for candidate, source in rows:
        if decided >= limit:  # the limit counts decisions, not already-decided candidates skipped on the way
            break
        previous = (candidate.validation or {}).get("autonomy") or {}
        if (previous.get("content_hash") == candidate.content_hash and previous.get("mode") == source.publish_mode
                and previous.get("policy") == POLICY_VERSION and not previous.get("retry")):
            counts["skipped"] += 1  # already decided for this content and mode
            continue
        asked = use_ai and _cheap_gates_pass(candidate, source)
        # The page hasn't changed since the AI last read it: reuse that verified reading (saves the free quota).
        stored = ai_review.from_dict(previous.get("ai")) if previous.get("content_hash") == candidate.content_hash else None
        ai = (stored or ai_review.review_page(candidate.page_text or "", today=today)) if asked else None
        decision = decide(candidate, source, today=today, ai=ai, use_ai=use_ai, ai_asked=asked)
        acted = "held"
        if decision.outcome != "hold" and source.publish_mode == PublishMode.SHADOW:
            acted = "would " + decision.outcome
        elif decision.outcome in ("draft", "publish"):
            # Put the verified statements where approval reads them, then approve exactly as a curator would.
            extraction = dict(candidate.extraction or {})
            extraction["eligibility"] = {"status": "explicit", "value": decision.statements, "evidence": [{"quote": s, "location": "text"} for s in decision.statements], "note": "Verified quotes (rule-based and AI)."}
            if ai and ai.deadline_quote and (extraction.get("deadline") or {}).get("status") != "explicit":
                # The deadline came from the AI: keep its verified quote as the evidence, as the rule-based reader would.
                extraction["deadline"] = {"status": "explicit", "value": decision.deadline.isoformat() if decision.deadline else None,
                                          "evidence": [{"quote": ai.deadline_quote, "location": "text"}], "note": f"Read by {ai.model}; quote verified on the page."}
            candidate.extraction = extraction
            db.flush()
            try:
                opportunity = pipeline.approve_candidate(
                    db, candidate.id, actor_id=None,  # type: ignore[arg-type]  # a system action
                    decision=pipeline.ApprovalInput(
                        title=decision.title, opportunity_type=decision.opportunity_type, deadline=decision.deadline,
                        deadline_type=decision.deadline_type, deadline_unannounced=decision.deadline_unannounced,
                        notes="Automatic approval: every autonomy check passed.",
                    ),
                )
                acted = "drafted"
                if decision.outcome == "publish":
                    try:
                        publish_opportunity(db, opportunity.id)
                        audit.record(db, action="opportunity.auto_published", target_type="opportunity", target_id=opportunity.id,
                                     changes={"candidate_id": str(candidate.id), "source": source.name, "policy": POLICY_VERSION},
                                     reason="Every autonomy check passed.")
                        acted = "published"
                    except IncompleteOpportunityError as error:
                        decision.checks.append(Check("publication checks", False, f"Drafted, not published: {error}"))
            except pipeline.PipelineError as error:
                decision.checks.append(Check("approval", False, f"Approval refused: {error}"))
                acted = "held"
        candidate = db.get(IngestionCandidate, candidate.id)  # approve_candidate re-locked it
        candidate.validation = {**(candidate.validation or {}), "autonomy": decision.as_dict(candidate.content_hash, acted)}
        db.commit()
        key = {"published": "published", "drafted": "drafted", "held": "held"}.get(acted, "shadow")
        counts[key] += 1
        decided += 1
    return counts


def close_past_deadline(db: Session, *, now: datetime | None = None) -> int:
    """Close published opportunities whose fixed deadline has passed (they stay visible, marked closed)."""
    from app.services.opportunities import close_opportunity

    now = now or datetime.now(timezone.utc)
    past = list(db.scalars(select(Opportunity.id).where(Opportunity.status == OpportunityStatus.PUBLISHED, Opportunity.deadline_at.is_not(None), Opportunity.deadline_at < now)))
    for opportunity_id in past:
        close_opportunity(db, opportunity_id)
        audit.record(db, action="opportunity.auto_closed", target_type="opportunity", target_id=opportunity_id, reason="The deadline passed.")
    db.commit()
    return len(past)


__all__ = ["Decision", "POLICY_VERSION", "close_past_deadline", "decide", "run"]
