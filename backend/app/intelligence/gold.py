"""The gold evaluation set: hand-verified records the pipeline is measured against (M2-T16).

Version 1 is derived from the 14 opportunities curated by hand in
``scripts/seed_demo.py`` (every quote copied verbatim from the official
page on 2026-10-30). It records only what that curation actually
established:

* fields stated on the page (title, provider, official URL, deadline,
  deadline type, listing status) are **scored**;
* curator classifications without a supporting quote (type, location mode,
  countries, languages, tags) are kept for reference but **not scored**;
* each eligibility statement keeps its verbatim quote and curated rule, and
  carries ``review_flags`` where the curated rule rests on an
  interpretation the automated pipeline must not reproduce. Flagged rules
  are excluded from rule-conversion scoring until a person resolves them.

No page snapshots exist yet (they need the fetcher, M2-T7/T8), so quote
verification against page text cannot be evaluated from this version.
"""
from __future__ import annotations

import json
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

GOLD_SCHEMA_VERSION = 1

#: Fields every prediction is scored on, in report order.
SCORED_FIELDS: tuple[str, ...] = ("title", "provider", "official_url", "deadline_at", "deadline_type", "listing_status")

#: Curator classifications kept for reference only.
UNSCORED_FIELDS: tuple[str, ...] = ("opportunity_type", "location_mode", "countries", "languages", "tags")


class ReviewFlag(StrEnum):
    """Why a curated rule is not automatic ground truth."""

    #: The quote joins two table cells as ``header | cell``; it never occurs verbatim in page text.
    TABLE_CELLS_QUOTE = "table_cells_quote"
    #: The wording says "or equivalent" but the curated rule is structured; policy treats this as ambiguous.
    OR_EQUIVALENT_WORDING = "or_equivalent_wording"
    #: An age rule checked against the retrieval date because the page gives no reference date.
    RETRIEVAL_DATE_REFERENCE = "retrieval_date_reference"
    #: An age rule whose reference date was worked out by the curator, not stated in the quote.
    DERIVED_REFERENCE_DATE = "derived_reference_date"


class GoldRequirement(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    label: str
    quote: str = Field(min_length=1)
    quote_form: Literal["sentence", "table_cells"]
    source_url: str
    category: str
    is_mandatory: bool
    is_ambiguous: bool
    kind: str
    params: dict[str, Any]
    review_flags: tuple[ReviewFlag, ...] = ()

    @property
    def rule_scored(self) -> bool:
        return not self.review_flags

    @property
    def is_structured(self) -> bool:
        return self.kind != "unparsed"


class GoldRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    title: str
    provider: str
    official_url: str
    deadline_at: datetime | None
    deadline_type: str
    listing_status: Literal["published", "closed"]
    source_urls: tuple[str, ...]
    reference: dict[str, Any] = Field(default_factory=dict)
    requirements: tuple[GoldRequirement, ...]

    @model_validator(mode="after")
    def requirements_cite_record_sources(self) -> GoldRecord:
        unknown = {item.source_url for item in self.requirements} - set(self.source_urls)
        if unknown:
            raise ValueError(f"{self.id}: requirements cite unlisted sources {sorted(unknown)}")
        return self


class GoldSet(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1]
    dataset_version: str
    valid_as_of: datetime
    provenance: str
    limitations: tuple[str, ...]
    records: tuple[GoldRecord, ...]

    @model_validator(mode="after")
    def unique_ids(self) -> GoldSet:
        record_ids = [record.id for record in self.records]
        requirement_ids = [item.id for record in self.records for item in record.requirements]
        if len(set(record_ids)) != len(record_ids) or len(set(requirement_ids)) != len(requirement_ids):
            raise ValueError("record and requirement ids must be unique")
        return self

    def manual_review_items(self) -> list[tuple[str, tuple[ReviewFlag, ...]]]:
        """Every requirement a person still has to resolve, with its reasons."""
        return [
            (item.id, item.review_flags)
            for record in self.records
            for item in record.requirements
            if item.review_flags
        ]


def load_gold_set(path: Path) -> GoldSet:
    return GoldSet.model_validate(json.loads(path.read_text(encoding="utf-8")))


__all__ = [
    "GOLD_SCHEMA_VERSION",
    "GoldRecord",
    "GoldRequirement",
    "GoldSet",
    "ReviewFlag",
    "SCORED_FIELDS",
    "UNSCORED_FIELDS",
    "load_gold_set",
]
