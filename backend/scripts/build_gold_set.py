"""Build the versioned gold evaluation set from the hand-curated seed dataset.

Run from ``backend/``::

    python -m scripts.build_gold_set            # write tests/fixtures/gold/v1/opportunities.json
    python -m scripts.build_gold_set --check    # exit 1 if the committed file is out of date

The output is deterministic, so the committed file can be compared with a
fresh build in tests. Nothing here touches a database or the network; the
settings import (via the seed module) only needs the usual environment.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.intelligence.gold import GoldRecord, GoldRequirement, GoldSet, ReviewFlag  # noqa: E402
from app.models.enums import RequirementKind  # noqa: E402
from app.schemas.requirement import validate_params_for_kind  # noqa: E402
from scripts import seed_demo  # noqa: E402

BACKEND_DIR = Path(__file__).resolve().parents[1]
GOLD_PATH = BACKEND_DIR / "tests" / "fixtures" / "gold" / "v1" / "opportunities.json"
DATASET_VERSION = "1.0.0"

PROVENANCE = (
    "Derived from the 14 opportunities curated by hand in backend/scripts/seed_demo.py. Every title, host, URL, "
    "date and quote was copied verbatim from the official page on the retrieval date; rules were structured only "
    "where the wording maps onto a fact the engine reads, otherwise kept as unparsed."
)

LIMITATIONS = (
    "No page snapshots are stored: quote verification against page text cannot be evaluated from this version.",
    "Facts are valid as of the retrieval date; deadlines and statuses on the live pages may have changed since.",
    "Opportunity type, location mode, countries, languages and tags are curator classifications without quotes "
    "and are not scored.",
    "Mandatory classification follows the curated default (all rules mandatory); no page stated an optional rule.",
    "Requirements with review_flags rest on a curator interpretation and are excluded from rule-conversion "
    "scoring until a person resolves them.",
    "Fourteen records from six kinds of provider cannot show statistically reliable accuracy; they show "
    "systematic errors.",
)


def review_flags(rule: dict) -> tuple[ReviewFlag, ...]:
    """Detect the curator interpretations an automated extractor must not be scored against."""
    flags: list[ReviewFlag] = []
    quote = rule["source_quote"]
    if " | " in quote:
        flags.append(ReviewFlag.TABLE_CELLS_QUOTE)
    if rule["kind"] != "unparsed" and "equivalent" in quote.lower():
        flags.append(ReviewFlag.OR_EQUIVALENT_WORDING)
    if rule["kind"] == "date_gate":
        if "checked as of" in rule["label"].lower():
            flags.append(ReviewFlag.RETRIEVAL_DATE_REFERENCE)
        elif rule["params"]["value"][:4] not in quote:
            flags.append(ReviewFlag.DERIVED_REFERENCE_DATE)
    return tuple(flags)


def gold_record(spec: dict) -> GoldRecord:
    official_url = spec["official_url"]
    main_source = spec.get("source_url", official_url)
    rules = spec["rules"]
    source_urls = tuple(dict.fromkeys([main_source, *(rule.get("source_url", main_source) for rule in rules)]))
    requirements = tuple(
        GoldRequirement(
            id=f"{spec['slug']}#{index}",
            label=rule["label"],
            quote=rule["source_quote"],
            quote_form="table_cells" if " | " in rule["source_quote"] else "sentence",
            source_url=rule.get("source_url", main_source),
            category=rule["category"],
            is_mandatory=rule.get("is_mandatory", True),
            is_ambiguous=rule.get("is_ambiguous", False),
            kind=rule["kind"],
            params=validate_params_for_kind(RequirementKind(rule["kind"]), rule["params"]),
            review_flags=review_flags(rule),
        )
        for index, rule in enumerate(rules)
    )
    return GoldRecord(
        id=spec["slug"],
        title=spec["title"],
        provider=spec["host_name"],
        official_url=official_url,
        deadline_at=spec.get("deadline_at"),
        deadline_type=spec.get("deadline_type", "fixed"),
        listing_status=spec.get("status", "published"),
        source_urls=source_urls,
        reference={
            "opportunity_type": spec["opportunity_type"],
            "location_mode": spec.get("location_mode", "unknown"),
            "countries": list(spec.get("countries", [])),
            "languages": list(spec.get("languages", [])),
            "tags": list(spec.get("tags", [])),
            "publisher": spec["publisher"],
            "description": spec.get("description"),
        },
        requirements=requirements,
    )


def build_gold_set() -> GoldSet:
    return GoldSet(
        schema_version=1,
        dataset_version=DATASET_VERSION,
        valid_as_of=seed_demo.RETRIEVED_AT,
        provenance=PROVENANCE,
        limitations=LIMITATIONS,
        records=tuple(gold_record(spec) for spec in seed_demo.OPPORTUNITIES),
    )


def render(gold: GoldSet) -> str:
    return json.dumps(gold.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="fail if the committed gold file is out of date")
    args = parser.parse_args(argv)
    content = render(build_gold_set())
    if args.check:
        current = GOLD_PATH.read_text(encoding="utf-8") if GOLD_PATH.exists() else ""
        if current != content:
            print(f"{GOLD_PATH} is out of date; run python -m scripts.build_gold_set", file=sys.stderr)
            raise SystemExit(1)
        print("gold set is up to date")
        return
    GOLD_PATH.parent.mkdir(parents=True, exist_ok=True)
    GOLD_PATH.write_text(content, encoding="utf-8")
    print(f"wrote {GOLD_PATH}")


if __name__ == "__main__":
    main()
