"""The gold evaluation set (M2-T16): integrity, provenance flags and the scoring harness."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.intelligence.evaluation import canonical_url, evaluate, normalize_text
from app.intelligence.gold import SCORED_FIELDS, GoldRecord, GoldSet, ReviewFlag, load_gold_set
from app.models.enums import RequirementKind
from app.schemas.requirement import validate_params_for_kind
from scripts import build_gold_set, seed_demo

GOLD_PATH = Path(__file__).parent / "fixtures" / "gold" / "v1" / "opportunities.json"


@pytest.fixture(scope="module")
def gold() -> GoldSet:
    return load_gold_set(GOLD_PATH)


# --- Integrity -------------------------------------------------------------------------------------


def test_committed_file_matches_a_fresh_build_from_the_seed():
    assert GOLD_PATH.read_text(encoding="utf-8") == build_gold_set.render(build_gold_set.build_gold_set()), (
        "The gold set is stale; run python -m scripts.build_gold_set"
    )


def test_one_record_per_curated_opportunity(gold):
    assert gold.schema_version == 1
    assert [record.id for record in gold.records] == [spec["slug"] for spec in seed_demo.OPPORTUNITIES]
    assert gold.valid_as_of == seed_demo.RETRIEVED_AT


def test_every_requirement_keeps_its_verbatim_quote_and_source(gold):
    for record in gold.records:
        spec = next(item for item in seed_demo.OPPORTUNITIES if item["slug"] == record.id)
        assert [item.quote for item in record.requirements] == [rule["source_quote"] for rule in spec["rules"]]
        for item in record.requirements:
            assert item.quote.strip() == item.quote and item.quote
            assert item.source_url in record.source_urls
            assert item.source_url.startswith("https://")


def test_every_gold_rule_is_valid_for_the_current_engine_schema(gold):
    for record in gold.records:
        for item in record.requirements:
            assert validate_params_for_kind(RequirementKind(item.kind), item.params) == item.params


def test_only_page_stated_fields_are_scored(gold):
    assert SCORED_FIELDS == ("title", "provider", "official_url", "deadline_at", "deadline_type", "listing_status")
    for record in gold.records:
        assert set(record.reference) >= {"opportunity_type", "location_mode", "countries", "languages", "tags"}


def test_deadlines_are_timezone_aware(gold):
    for record in gold.records:
        if record.deadline_at is not None:
            assert record.deadline_at.tzinfo is not None


# --- Review flags ----------------------------------------------------------------------------------


def test_expected_requirements_are_flagged_for_manual_review(gold):
    flagged = dict(gold.manual_review_items())
    assert flagged == {
        "kaust-visiting-student-research-program#1": (ReviewFlag.OR_EQUIVALENT_WORDING,),
        "github-student-developer-pack#1": (ReviewFlag.RETRIEVAL_DATE_REFERENCE,),
        "nasa-ostem-internships-summer-2027#0": (ReviewFlag.TABLE_CELLS_QUOTE,),
        "nasa-ostem-internships-summer-2027#1": (ReviewFlag.TABLE_CELLS_QUOTE,),
        "nasa-ostem-internships-fall-2027#0": (ReviewFlag.TABLE_CELLS_QUOTE,),
        "nasa-ostem-internships-fall-2027#1": (ReviewFlag.TABLE_CELLS_QUOTE,),
        "schwarzman-scholars-2028-2029#0": (ReviewFlag.DERIVED_REFERENCE_DATE,),
        "schwarzman-scholars-2028-2029#1": (ReviewFlag.DERIVED_REFERENCE_DATE,),
        "brooke-owens-fellowship-2027#1": (ReviewFlag.RETRIEVAL_DATE_REFERENCE,),
        "summer-at-epfl-2027#0": (ReviewFlag.OR_EQUIVALENT_WORDING,),
        "kaust-masters-fellowship-fall-2027#1": (ReviewFlag.OR_EQUIVALENT_WORDING,),
        "kaust-masters-fellowship-fall-2027#2": (ReviewFlag.DERIVED_REFERENCE_DATE,),
    }


def test_every_age_rule_is_flagged_because_its_reference_date_is_not_quoted(gold):
    age_rules = [item for record in gold.records for item in record.requirements if item.kind == "date_gate"]
    assert age_rules and all(item.review_flags for item in age_rules)


def test_table_cell_quotes_are_marked(gold):
    for record in gold.records:
        for item in record.requirements:
            assert (item.quote_form == "table_cells") == (" | " in item.quote)


def test_scored_rules_include_structured_and_unparsed_cases(gold):
    scored = [item for record in gold.records for item in record.requirements if item.rule_scored]
    assert sum(item.is_structured for item in scored) == 12
    assert sum(not item.is_structured for item in scored) == 19


# --- Harness: perfect prediction ------------------------------------------------------------------


def predictions_from(gold: GoldSet) -> list[GoldRecord]:
    return [record.model_copy(deep=True) for record in gold.records]


def test_the_gold_set_scores_perfectly_against_itself(gold):
    report = evaluate(gold, predictions_from(gold))
    summary = report.summary()
    assert summary["record_coverage"] == 1.0
    assert set(summary["field_accuracy"].values()) == {1.0}
    assert summary["statement_recall"] == 1.0 and summary["statement_precision"] == 1.0
    assert summary["rules"]["scored"] == 31
    assert summary["rules"]["correct"] == 31
    assert summary["rules"]["false_structured"] == 0
    assert summary["rules"]["missed_structure"] == 0
    assert summary["rules"]["excluded_for_review"] == 12
    assert summary["dropped_statements"] == []


# --- Harness: each kind of error moves the right metric -----------------------------------------


def _replace(records, record_id, **changes):
    return [record.model_copy(update=changes) if record.id == record_id else record for record in records]


def _replace_requirement(records, record_id, index, **changes):
    out = []
    for record in records:
        if record.id == record_id:
            items = list(record.requirements)
            items[index] = items[index].model_copy(update=changes)
            record = record.model_copy(update={"requirements": tuple(items)})
        out.append(record)
    return out


def test_a_wrong_deadline_costs_one_field(gold):
    predicted = _replace(
        predictions_from(gold), "summer-at-epfl-2027", deadline_at=datetime(2026, 12, 1, 12, tzinfo=timezone.utc)
    )
    report = evaluate(gold, predicted)
    assert report.field_correct["deadline_at"] == 13
    assert report.field_correct["title"] == 14


def test_url_and_text_normalisation_do_not_count_as_errors(gold):
    record = gold.records[0]
    predicted = _replace(
        predictions_from(gold),
        record.id,
        # Host case, a missing trailing slash and a fragment don't change the page; path case would.
        official_url=record.official_url.replace("careers.cern", "CAREERS.Cern").rstrip("/") + "#apply",
        title="  " + record.title.upper() + " ",
    )
    report = evaluate(gold, predicted)
    assert report.matched_records == 14
    assert report.field_correct["title"] == 14


def test_a_missing_record_drops_coverage_fields_and_statements(gold):
    predicted = [record for record in predictions_from(gold) if record.id != "gates-cambridge-scholarship"]
    report = evaluate(gold, predicted)
    missing = next(record for record in gold.records if record.id == "gates-cambridge-scholarship")
    assert report.matched_records == 13
    assert all(count == 13 for count in report.field_correct.values())
    assert report.dropped_statements == [item.id for item in missing.requirements]


def test_two_cycles_on_one_page_pair_by_title_whatever_their_order(gold):
    summer, fall = (
        next(record for record in gold.records if record.id == f"nasa-ostem-internships-{season}-2027")
        for season in ("summer", "fall")
    )
    assert summer.official_url == fall.official_url
    others = [record for record in predictions_from(gold) if record.id not in (summer.id, fall.id)]
    report = evaluate(gold, [*others, fall, summer])
    assert report.matched_records == 14
    assert set(report.field_correct.values()) == {14}
    assert report.unmatched_predictions == []


def test_a_prediction_for_an_unknown_page_is_reported(gold):
    stray = gold.records[0].model_copy(update={"official_url": "https://careers.cern/other/"})
    report = evaluate(gold, [*predictions_from(gold), stray])
    assert report.unmatched_predictions == ["https://careers.cern/other/"]


def test_structuring_an_unparsed_statement_is_a_false_structured_rule(gold):
    # CERN #3 ("not previously participated") is unparsed in gold.
    predicted = _replace_requirement(
        predictions_from(gold),
        "cern-summer-student-programme",
        3,
        kind="boolean_flag",
        params={"metric": "is_currently_enrolled", "expected": False},
    )
    report = evaluate(gold, predicted)
    assert report.rules.false_structured == 1
    assert report.false_structured_ids == ["cern-summer-student-programme#3"]
    assert report.rules.correct == 30


def _cern_enrolment_rule(gold):
    # CERN #1 ("remain enrolled as a full-time student") is structured and unflagged.
    record = next(record for record in gold.records if record.id == "cern-summer-student-programme")
    item = record.requirements[1]
    assert item.kind == "boolean_flag" and item.rule_scored
    return item


def test_a_wrong_structured_rule_is_a_false_structured_rule(gold):
    original = _cern_enrolment_rule(gold)
    wrong = {"metric": "is_currently_enrolled", "expected": False}
    assert original.params != wrong
    predicted = _replace_requirement(predictions_from(gold), "cern-summer-student-programme", 1, params=wrong)
    report = evaluate(gold, predicted)
    assert report.rules.false_structured == 1
    assert report.false_structured_ids == ["cern-summer-student-programme#1"]


def test_leaving_a_structured_rule_unparsed_is_a_missed_structure_not_a_false_rule(gold):
    _cern_enrolment_rule(gold)
    predicted = _replace_requirement(
        predictions_from(gold), "cern-summer-student-programme", 1, kind="unparsed", params={"reason": "not sure"}
    )
    report = evaluate(gold, predicted)
    assert report.rules.missed_structure == 1
    assert report.rules.false_structured == 0


def test_unparsed_reasons_do_not_matter(gold):
    predicted = _replace_requirement(
        predictions_from(gold), "cern-summer-student-programme", 3, params={"reason": "a different reason"}
    )
    assert evaluate(gold, predicted).rules.correct == 31


def test_flagged_requirements_are_never_scored(gold):
    predicted = _replace_requirement(
        predictions_from(gold), "kaust-visiting-student-research-program", 1, kind="unparsed", params={"reason": "x"}
    )
    report = evaluate(gold, predicted)
    assert report.rules.scored == 31
    assert report.rules.missed_structure == 0


def test_mandatory_flips_are_counted(gold):
    predicted = _replace_requirement(predictions_from(gold), "cern-summer-student-programme", 1, is_mandatory=False)
    assert evaluate(gold, predicted).rules.mandatory_mismatch == 1


def test_a_dropped_statement_lowers_recall(gold):
    record = next(record for record in gold.records if record.id == "summer-at-epfl-2027")
    predicted = _replace(predictions_from(gold), record.id, requirements=record.requirements[:-1])
    report = evaluate(gold, predicted)
    assert report.dropped_statements == [record.requirements[-1].id]
    assert report.statement_recall == pytest.approx(42 / 43)


def test_an_invented_statement_lowers_precision(gold):
    record = gold.records[0]
    invented = record.requirements[0].model_copy(update={"id": "x#99", "quote": "Applicants must love physics."})
    predicted = _replace(predictions_from(gold), record.id, requirements=(*record.requirements, invented))
    report = evaluate(gold, predicted)
    assert report.statement_recall == 1.0
    assert report.statement_precision == pytest.approx(43 / 44)


def test_shared_quotes_pair_identical_rules_first(gold):
    # CERN #0 and #2 quote the same sentence with different rules; swapping their order must not matter.
    record = next(record for record in gold.records if record.id == "cern-summer-student-programme")
    assert record.requirements[0].quote == record.requirements[2].quote
    items = list(record.requirements)
    items[0], items[2] = items[2], items[0]
    predicted = _replace(predictions_from(gold), record.id, requirements=tuple(items))
    assert evaluate(gold, predicted).rules.correct == 31


# --- Normalisers ------------------------------------------------------------------------------------


def test_normalize_text_folds_case_width_and_whitespace():
    assert normalize_text("  Ｍinimum   GPA\n3.5 ") == "minimum gpa 3.5"
    assert normalize_text(None) == ""


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("https://Careers.CERN/programmes/", "https://careers.cern/programmes"),
        ("https://careers.cern/x#top", "https://careers.cern/x"),
        ("https://careers.cern", "https://careers.cern/"),
    ],
)
def test_canonical_url_equivalences(a, b):
    assert canonical_url(a) == canonical_url(b)


def test_canonical_url_keeps_queries_distinct():
    assert canonical_url("https://a.edu/p?id=1") != canonical_url("https://a.edu/p?id=2")
