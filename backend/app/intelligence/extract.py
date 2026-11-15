"""Field extraction from one fetched page, with evidence for every claim.

Output contract (``Extraction``): every field is ``{status, value, evidence}`` where ``status`` is
``explicit`` (stated on the page), ``inferred`` (derived from page wording, e.g. a category from the
title), ``ambiguous`` (stated but not resolvable without guessing), ``conflicting`` (the page states
different values) or ``not_found``. Evidence quotes with ``location="text"`` are verbatim substrings of
the page's normalised text; ``validate.py`` re-checks that for any extractor, so an extractor (including
a future model-based one) cannot introduce a claim the page doesn't support.

The default ``DeterministicExtractor`` uses keyword and pattern rules only. It never invents a value:
when nothing matches, the field is ``not_found``.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from app.intelligence.normalize import DateMention, canonical_url, find_dates, infer_category
from app.intelligence.text import ParsedPage, sentences, text_lines

FieldStatus = Literal["explicit", "inferred", "ambiguous", "conflicting", "not_found"]
EXTRACTOR_VERSION = "deterministic-1"
MAX_STATEMENTS = 15
MAX_STATEMENT_CHARS = 500


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    quote: str = Field(min_length=1, max_length=2000)
    #: ``text`` (a substring of the page text), ``meta:<name>``, ``json_ld``, ``url`` or ``source_registry``.
    location: str = Field(min_length=1, max_length=64)


class ExtractedField(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: FieldStatus = "not_found"
    value: Any = None
    evidence: list[Evidence] = Field(default_factory=list)
    note: str | None = None


class Extraction(BaseModel):
    """Everything the extractor claims about one page."""

    model_config = ConfigDict(extra="forbid")

    title: ExtractedField = Field(default_factory=ExtractedField)
    organization: ExtractedField = Field(default_factory=ExtractedField)
    opportunity_type: ExtractedField = Field(default_factory=ExtractedField)
    official_url: ExtractedField = Field(default_factory=ExtractedField)
    description: ExtractedField = Field(default_factory=ExtractedField)
    deadline: ExtractedField = Field(default_factory=ExtractedField)
    deadline_type: ExtractedField = Field(default_factory=ExtractedField)
    opening_date: ExtractedField = Field(default_factory=ExtractedField)
    eligibility: ExtractedField = Field(default_factory=ExtractedField)
    applicant_groups: ExtractedField = Field(default_factory=ExtractedField)
    benefits: ExtractedField = Field(default_factory=ExtractedField)
    application_instructions: ExtractedField = Field(default_factory=ExtractedField)
    #: ``closed`` or ``open`` when the page says so in words ("no longer accepting applications").
    application_status: ExtractedField = Field(default_factory=ExtractedField)
    countries: list[str] = Field(default_factory=list)
    #: Signals that this is an opportunity page at all (not news, staff lists or navigation).
    relevance: int = Field(default=0, ge=0, le=100)
    relevance_signals: list[str] = Field(default_factory=list)


@dataclass(frozen=True)
class PageInput:
    """What an extractor gets: the parsed page plus trusted facts from the source registry."""

    url: str
    page: ParsedPage
    provider_name: str


class Extractor(Protocol):
    version: str

    def extract(self, page: PageInput) -> Extraction: ...


# --- helpers -------------------------------------------------------------------------------------------

_DEADLINE_WORDS = re.compile(
    r"\b(deadline|apply by|applications? (?:close|closes|due|must be (?:received|submitted))|closing date|"
    r"due date|submission deadline|application period ends|last date|apply before|open until|accepted until)\b",
    re.IGNORECASE,
)
_OPENING_WORDS = re.compile(
    r"\b(applications? (?:open|opens|will open|period (?:opens|starts|begins))|opens? on|open from|"
    r"application period: from|call opens)\b",
    re.IGNORECASE,
)
_ROLLING = re.compile(
    r"\brolling (?:basis|admissions?|deadline|applications?)\b|\bon a rolling\b|"
    r"\bapplications? (?:are|is|will be) (?:accepted|reviewed|considered) (?:at )?any ?time\b|"
    r"\b(?:can|may) (?:be submitted|apply) (?:at )?any ?time\b|\baccepted year[- ]round\b",
    re.IGNORECASE,
)
_NO_DEADLINE = re.compile(r"\b(no (?:application )?deadline|open all year|year-round applications?)\b", re.IGNORECASE)
_CLOSED = re.compile(
    r"\b(no longer accepting applications|applications? (?:are|is) (?:now )?closed|"
    r"(?:the )?(?:call|competition|application period|application window) (?:is|has) (?:now )?closed|"
    r"applications? (?:have|has) closed|not (?:currently )?accepting applications|"
    r"applications? (?:for [^.]{0,60})?(?:are|is) (?:now )?closed)\b",
    re.IGNORECASE,
)
_OPEN = re.compile(
    r"\b(applications? (?:are|is) (?:now )?open|(?:the )?call is (?:now )?open|now accepting applications|"
    r"apply now)\b",
    re.IGNORECASE,
)
_ELIGIBILITY_HEADING = re.compile(r"eligib|requirement|who (?:can|may|should) apply|criteria|qualif", re.IGNORECASE)
_ELIGIBILITY_SENTENCE = re.compile(
    r"\b(applicants? (?:must|should|need to|are required)|candidates? (?:must|should)|you must|must (?:be|have|hold)|"
    r"(?:is|are) eligible|eligible (?:applicants|candidates|students)|is open to|are open to|open to (?:all )?(?:students|applicants|candidates|undergraduate|graduate|citizens|nationals)|"
    r"(?:minimum|at least) (?:a )?(?:gpa|grade|cgpa)|currently enrolled|enrolled (?:full[- ]time|in)|"
    r"(?:bachelor|master|phd|doctoral|undergraduate|graduate)(?:'s)? (?:degree|students?) (?:is|are) required|"
    r"not eligible|ineligible|proof of english|english (?:language )?proficiency|ielts|toefl)\b",
    re.IGNORECASE,
)
_GROUP_SENTENCE = re.compile(
    r"\b(citizens? of|nationals? of|nationalit(?:y|ies)|residents? of|international students|all countries|"
    r"developing countries|women|underrepresented|first[- ]generation|refugees?)\b",
    re.IGNORECASE,
)
_BENEFIT_SENTENCE = re.compile(
    r"\b(stipend|allowance|tuition|fees? (?:are|will be) (?:covered|waived)|full(?:y)? funded|funding|"
    r"scholarship (?:covers|of|worth|amount)|travel (?:costs?|expenses|grant)|accommodation|housing|"
    r"health insurance|award(?:ed)? (?:of|up to)|salary|paid (?:internship|position)|per month|monthly)\b"
    r"|(?:[$€£]|USD|EUR|GBP|CHF|SAR)\s?\d",
    re.IGNORECASE,
)
_INSTRUCTION_SENTENCE = re.compile(
    r"\b(how to apply|apply online|application (?:form|portal|system)|submit (?:your|an|the)|"
    r"to apply,|letters? of recommendation|reference letters?|curriculum vitae|\bcv\b|transcripts?|"
    r"motivation letter|personal statement|statement of purpose)\b",
    re.IGNORECASE,
)
#: Lines that belong to another field (deadline, money, how to apply), even under an eligibility heading.
_OTHER_FIELD = re.compile(
    rf"(?:{_DEADLINE_WORDS.pattern})|(?:{_BENEFIT_SENTENCE.pattern})|(?:{_INSTRUCTION_SENTENCE.pattern})|rolling basis",
    re.IGNORECASE,
)
_OPPORTUNITY_WORDS = re.compile(
    r"\b(scholarships?|fellowships?|internships?|bursar(?:y|ies)|grants?|studentships?|summer school|"
    r"research program(?:me)?|visiting student|hackathon|competition|apply|application|eligib)\w*",
    re.IGNORECASE,
)


def _text(quote: str) -> Evidence:
    return Evidence(quote=quote[:2000], location="text")


def _trim(statement: str) -> str:
    return statement if len(statement) <= MAX_STATEMENT_CHARS else statement[:MAX_STATEMENT_CHARS]


def _statements(lines: list[str], pattern: re.Pattern[str], limit: int = MAX_STATEMENTS) -> list[str]:
    found: list[str] = []
    for line in lines:
        for sentence in sentences(line):
            if 15 <= len(sentence) and pattern.search(sentence):
                quote = _trim(sentence)
                if quote not in found:
                    found.append(quote)
                if len(found) >= limit:
                    return found
    return found


_SECTION_STATEMENT = re.compile(
    r"\b(must|should|be|is|are|have|has|hold|holds|need|needs|eligible|enrolled|open|apply|required|"
    r"citizens?|nationals?|students?|applicants?|candidates?)\b",
    re.IGNORECASE,
)


def _looks_like_statement(line: str) -> bool:
    """Skip table headers and cells under an eligibility heading; keep real statements and long bullets."""
    return len(line) >= 40 or (len(line) >= 30 and bool(_SECTION_STATEMENT.search(line)))


def _section_lines(lines: list[str], headings: list[tuple[int, str]], pattern: re.Pattern[str]) -> list[str]:
    """Lines that follow a matching heading, up to the next heading that isn't itself a matching one.

    Any other heading (including a sub-heading) ends the section: pages often nest benefits, deadlines
    or partner details under an eligibility heading, and those are not eligibility statements.
    """
    heading_text = {text for _, text in headings}
    out: list[str] = []
    active = False
    for line in lines:
        if line in heading_text:
            active = bool(pattern.search(line))
            continue
        if active and _looks_like_statement(line) and not _OTHER_FIELD.search(line):
            out.append(line)
            if len(out) >= 10:
                break
    return out


def _dates_after_keyword(line: str, keyword: re.Pattern[str]) -> list[DateMention]:
    match = keyword.search(line)
    if not match:
        return []
    mentions = [mention for mention in find_dates(line) if mention.start >= match.start()]
    return mentions[:1] or []


def _date_field(lines: list[str], keyword: re.Pattern[str]) -> ExtractedField:
    """A single date stated next to ``keyword``; ``conflicting`` if lines disagree, ``ambiguous`` if unresolvable."""
    explicit: dict[date, str] = {}
    ambiguous: list[tuple[str, str]] = []
    for line in lines:
        for sentence in sentences(line):
            for mention in _dates_after_keyword(sentence, keyword):
                if mention.value is not None:
                    explicit.setdefault(mention.value, sentence)
                else:
                    ambiguous.append((sentence, mention.reason or "ambiguous"))
    if len(explicit) == 1:
        (value, quote), = explicit.items()
        return ExtractedField(status="explicit", value=value.isoformat(), evidence=[_text(_trim(quote))])
    if len(explicit) > 1:
        values = sorted(explicit)
        return ExtractedField(
            status="conflicting",
            value=[value.isoformat() for value in values],
            evidence=[_text(_trim(explicit[value])) for value in values][:5],
            note="the page states more than one date here (possibly several rounds or cycles)",
        )
    if ambiguous:
        return ExtractedField(
            status="ambiguous",
            evidence=[_text(_trim(quote)) for quote, _ in ambiguous][:5],
            note="; ".join(sorted({reason for _, reason in ambiguous})),
        )
    return ExtractedField()


def _json_ld_value(items: list[dict[str, Any]], *keys: str) -> str | None:
    for item in items:
        for key in keys:
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def _clean_title(raw: str) -> str:
    for separator in (" | ", " – ", " — ", " - ", " :: "):
        if separator in raw:
            head = raw.split(separator)[0].strip()
            if len(head) >= 5:
                return head
    return raw.strip()


class DeterministicExtractor:
    """Keyword and pattern rules; no network, no model, no guessing."""

    version = EXTRACTOR_VERSION

    def extract(self, page_input: PageInput) -> Extraction:
        page = page_input.page
        lines = text_lines(page.text)
        result = Extraction()

        # Title: the page's first h1 (visible), else og:title, else <title> without the site suffix.
        h1 = next((text for level, text in page.headings if level == 1 and 4 <= len(text) <= 300), None)
        if h1 and h1 in page.text:
            result.title = ExtractedField(status="explicit", value=h1, evidence=[_text(h1)])
        elif page.meta.get("og:title"):
            title = page.meta["og:title"]
            result.title = ExtractedField(status="explicit", value=title,
                                          evidence=[Evidence(quote=title, location="meta:og:title")])
        elif page.title:
            title = _clean_title(page.title)
            result.title = ExtractedField(status="explicit", value=title,
                                          evidence=[Evidence(quote=page.title, location="meta:title")])

        # Organisation: the registry's provider identity (a person approved it), not page wording.
        result.organization = ExtractedField(
            status="explicit", value=page_input.provider_name,
            evidence=[Evidence(quote=page_input.provider_name, location="source_registry")],
        )

        result.official_url = ExtractedField(
            status="explicit", value=canonical_url(page_input.url),
            evidence=[Evidence(quote=page_input.url, location="url")],
        )

        description = page.meta.get("description") or page.meta.get("og:description")
        if description:
            result.description = ExtractedField(
                status="explicit", value=description,
                evidence=[Evidence(quote=description, location="meta:description")],
            )
        else:
            paragraph = next((line for line in lines if len(line) >= 120), None)
            if paragraph:
                quote = _trim(paragraph)
                result.description = ExtractedField(status="explicit", value=quote, evidence=[_text(quote)])

        title_value = result.title.value if isinstance(result.title.value, str) else None
        category = infer_category(title_value, page_input.url)
        if category is not None:
            result.opportunity_type = ExtractedField(
                status="inferred", value=category.value,
                evidence=[Evidence(quote=title_value or page_input.url, location="text" if title_value and title_value in page.text else "url")],
                note="category inferred from the title or URL wording",
            )

        # Deadline: structured data first (it is the provider's own markup), then the visible text.
        json_deadline = _json_ld_value(page.json_ld, "applicationDeadline", "validThrough")
        deadline = _date_field(lines, _DEADLINE_WORDS)
        if json_deadline and deadline.status == "not_found":
            mentions = find_dates(json_deadline)
            if mentions and mentions[0].value is not None:
                deadline = ExtractedField(status="explicit", value=mentions[0].value.isoformat(),
                                          evidence=[Evidence(quote=json_deadline, location="json_ld")])
        mentions = sum(1 for line in lines for sentence in sentences(line) if _DEADLINE_WORDS.search(sentence))
        notes = []
        if deadline.status == "explicit" and mentions > 1:
            notes.append(f"the page mentions deadlines in {mentions} places; check that this date applies to "
                         "the whole programme and this cycle")
        if deadline.status == "explicit" and _statements(lines, _ROLLING, limit=1):
            notes.append("the page also says applications are handled on a rolling basis")
        if notes:
            deadline.note = "; ".join(notes)
        result.deadline = deadline

        rolling = _statements(lines, _ROLLING, limit=2)
        no_deadline = _statements(lines, _NO_DEADLINE, limit=2)
        if deadline.status == "explicit":
            result.deadline_type = ExtractedField(status="explicit", value="fixed", evidence=deadline.evidence)
        elif rolling:
            result.deadline_type = ExtractedField(status="explicit", value="rolling", evidence=[_text(rolling[0])])
        elif no_deadline:
            result.deadline_type = ExtractedField(status="explicit", value="none", evidence=[_text(no_deadline[0])])
        elif deadline.status in ("conflicting", "ambiguous"):
            result.deadline_type = ExtractedField(status="ambiguous", note="a deadline is mentioned but not resolved")

        result.opening_date = _date_field(lines, _OPENING_WORDS)

        section = _section_lines(lines, page.headings, _ELIGIBILITY_HEADING)
        eligibility = _statements(section, re.compile(r".")) if section else []
        for statement in _statements(lines, _ELIGIBILITY_SENTENCE):
            if statement not in eligibility and len(eligibility) < MAX_STATEMENTS:
                eligibility.append(statement)
        if eligibility:
            result.eligibility = ExtractedField(status="explicit", value=eligibility,
                                                evidence=[_text(item) for item in eligibility])

        for name, pattern, limit in (
            ("applicant_groups", _GROUP_SENTENCE, 6),
            ("benefits", _BENEFIT_SENTENCE, 8),
            ("application_instructions", _INSTRUCTION_SENTENCE, 8),
        ):
            found = _statements(lines, pattern, limit=limit)
            if found:
                setattr(result, name, ExtractedField(status="explicit", value=found,
                                                     evidence=[_text(item) for item in found]))

        closed = _statements(lines, _CLOSED, limit=3)
        opened = _statements(lines, _OPEN, limit=3)
        if closed and opened:
            result.application_status = ExtractedField(
                status="conflicting", value=["closed", "open"], evidence=[_text(closed[0]), _text(opened[0])],
                note="the page says both that applications are closed and open (several rounds?)",
            )
        elif closed:
            result.application_status = ExtractedField(status="explicit", value="closed", evidence=[_text(closed[0])])
        elif opened:
            result.application_status = ExtractedField(status="explicit", value="open", evidence=[_text(opened[0])])

        signals: list[str] = []
        score = 0
        if category is not None:
            signals.append("opportunity word in title or URL")
            score += 35
        if result.deadline.status != "not_found" or result.deadline_type.status == "explicit":
            signals.append("deadline information")
            score += 25
        if result.eligibility.status == "explicit":
            signals.append("eligibility statements")
            score += 25
        if result.application_instructions.status == "explicit":
            signals.append("application instructions")
            score += 10
        if len(_OPPORTUNITY_WORDS.findall(page.text[:20000])) >= 5:
            signals.append("opportunity vocabulary")
            score += 5
        result.relevance = min(score, 100)
        result.relevance_signals = signals
        return result


__all__ = [
    "EXTRACTOR_VERSION",
    "DeterministicExtractor",
    "Evidence",
    "ExtractedField",
    "Extraction",
    "Extractor",
    "PageInput",
]
