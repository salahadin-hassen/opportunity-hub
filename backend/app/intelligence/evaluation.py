"""Score predicted opportunity records against the gold set (M2-T16).

A prediction is a ``GoldRecord``-shaped record produced by an extractor;
records are paired with gold records by canonical official URL (an
extractor does not know our slugs). Metrics:

* **record coverage**: gold records that received a prediction;
* **field accuracy**: per scored field, exact match after light normalisation;
* **statement recall / precision**: eligibility statements paired by normalised quote;
* **rule conversion**, on unflagged gold requirements whose statement was found:
  correct, *false structured rules* (a structured rule that differs from the
  gold rule, or where gold is ``unparsed``; the headline error because it can
  mislead a student), *missed structure* (prediction left a gold rule
  ``unparsed``; the safe direction), and mandatory/optional mismatches.

Deterministic and pure: no database, no network, no model calls.
"""
from __future__ import annotations

import json
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field
from urllib.parse import urlsplit, urlunsplit

from app.intelligence.gold import SCORED_FIELDS, GoldRecord, GoldRequirement, GoldSet


def normalize_text(value: str | None) -> str:
    """NFKC, collapsed whitespace, case-folded: how quotes and names are compared."""
    if value is None:
        return ""
    return " ".join(unicodedata.normalize("NFKC", value).split()).casefold()


def canonical_url(value: str) -> str:
    """Scheme and host lower-cased, fragment dropped, trailing slash ignored."""
    parts = urlsplit(value.strip())
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), (parts.hostname or "").lower(), path, parts.query, ""))


def _rule_key(item: GoldRequirement) -> str:
    """Comparable identity of a rule: unparsed rules are equal whatever their stated reason."""
    if not item.is_structured:
        return "unparsed"
    return json.dumps({"kind": item.kind, "params": item.params}, sort_keys=True)


def _field_equal(name: str, gold: GoldRecord, predicted: GoldRecord) -> bool:
    expected, actual = getattr(gold, name), getattr(predicted, name)
    if name in ("title", "provider"):
        return normalize_text(expected) == normalize_text(actual)
    if name == "official_url":
        return canonical_url(expected) == canonical_url(actual)
    return expected == actual


@dataclass
class RuleCounts:
    scored: int = 0
    correct: int = 0
    false_structured: int = 0
    missed_structure: int = 0
    mandatory_mismatch: int = 0
    excluded_for_review: int = 0

    @property
    def accuracy(self) -> float | None:
        return self.correct / self.scored if self.scored else None


@dataclass
class EvaluationReport:
    gold_records: int
    matched_records: int
    unmatched_predictions: list[str]
    field_correct: dict[str, int]
    gold_statements: int
    predicted_statements: int
    matched_statements: int
    dropped_statements: list[str] = field(default_factory=list)
    rules: RuleCounts = field(default_factory=RuleCounts)
    false_structured_ids: list[str] = field(default_factory=list)

    @property
    def record_coverage(self) -> float:
        return self.matched_records / self.gold_records if self.gold_records else 0.0

    def field_accuracy(self, name: str) -> float:
        return self.field_correct[name] / self.gold_records if self.gold_records else 0.0

    @property
    def statement_recall(self) -> float:
        return self.matched_statements / self.gold_statements if self.gold_statements else 0.0

    @property
    def statement_precision(self) -> float:
        return self.matched_statements / self.predicted_statements if self.predicted_statements else 0.0

    def summary(self) -> dict:
        return {
            "record_coverage": round(self.record_coverage, 4),
            "field_accuracy": {name: round(self.field_accuracy(name), 4) for name in SCORED_FIELDS},
            "statement_recall": round(self.statement_recall, 4),
            "statement_precision": round(self.statement_precision, 4),
            "rules": {
                "scored": self.rules.scored,
                "correct": self.rules.correct,
                "accuracy": None if self.rules.accuracy is None else round(self.rules.accuracy, 4),
                "false_structured": self.rules.false_structured,
                "missed_structure": self.rules.missed_structure,
                "mandatory_mismatch": self.rules.mandatory_mismatch,
                "excluded_for_review": self.rules.excluded_for_review,
            },
            "dropped_statements": list(self.dropped_statements),
            "false_structured_ids": list(self.false_structured_ids),
            "unmatched_predictions": list(self.unmatched_predictions),
        }


def _pair_statements(
    gold: tuple[GoldRequirement, ...], predicted: tuple[GoldRequirement, ...]
) -> tuple[list[tuple[GoldRequirement, GoldRequirement]], list[GoldRequirement], int]:
    """Pair by normalised quote; within one quote, identical rules pair first.

    Returns the pairs, the unpaired gold statements and the number of unpaired predictions.
    """
    by_quote: dict[str, list[GoldRequirement]] = defaultdict(list)
    for item in predicted:
        by_quote[normalize_text(item.quote)].append(item)
    pairs: list[tuple[GoldRequirement, GoldRequirement]] = []
    unpaired: list[GoldRequirement] = []
    pending: list[GoldRequirement] = []
    for item in gold:
        candidates = by_quote.get(normalize_text(item.quote), [])
        same_rule = next((c for c in candidates if _rule_key(c) == _rule_key(item)), None)
        if same_rule is not None:
            candidates.remove(same_rule)
            pairs.append((item, same_rule))
        else:
            pending.append(item)
    for item in pending:
        candidates = by_quote.get(normalize_text(item.quote), [])
        if candidates:
            pairs.append((item, candidates.pop(0)))
        else:
            unpaired.append(item)
    leftover = sum(len(items) for items in by_quote.values())
    return pairs, unpaired, leftover


def _pair_records(
    gold: tuple[GoldRecord, ...], predictions: list[GoldRecord]
) -> tuple[dict[str, GoldRecord], list[str]]:
    """Pair predictions with gold records by canonical official URL.

    One official page can publish several cycles (the NASA OSTEM page lists
    Summer and Fall), so within one URL identical normalised titles pair
    first and the rest pair in order. Returns gold id → prediction and the
    URLs of predictions left unpaired.
    """
    by_url: dict[str, list[GoldRecord]] = defaultdict(list)
    for record in predictions:
        by_url[canonical_url(record.official_url)].append(record)
    paired: dict[str, GoldRecord] = {}
    pending: list[GoldRecord] = []
    for record in gold:
        candidates = by_url.get(canonical_url(record.official_url), [])
        same_title = next((c for c in candidates if normalize_text(c.title) == normalize_text(record.title)), None)
        if same_title is not None:
            candidates.remove(same_title)
            paired[record.id] = same_title
        else:
            pending.append(record)
    for record in pending:
        candidates = by_url.get(canonical_url(record.official_url), [])
        if candidates:
            paired[record.id] = candidates.pop(0)
    unmatched = [record.official_url for items in by_url.values() for record in items]
    return paired, unmatched


def evaluate(gold: GoldSet, predictions: list[GoldRecord]) -> EvaluationReport:
    """Score ``predictions`` against ``gold``."""
    paired, unmatched = _pair_records(gold.records, predictions)
    report = EvaluationReport(
        gold_records=len(gold.records),
        matched_records=0,
        unmatched_predictions=unmatched,
        field_correct={name: 0 for name in SCORED_FIELDS},
        gold_statements=sum(len(record.requirements) for record in gold.records),
        predicted_statements=sum(len(record.requirements) for record in paired.values()),
        matched_statements=0,
    )
    for gold_record in gold.records:
        predicted = paired.get(gold_record.id)
        if predicted is None:
            report.dropped_statements.extend(item.id for item in gold_record.requirements)
            report.rules.excluded_for_review += sum(1 for item in gold_record.requirements if not item.rule_scored)
            continue
        report.matched_records += 1
        for name in SCORED_FIELDS:
            report.field_correct[name] += _field_equal(name, gold_record, predicted)

        pairs, unpaired, _ = _pair_statements(gold_record.requirements, predicted.requirements)
        report.matched_statements += len(pairs)
        report.dropped_statements.extend(item.id for item in unpaired)
        report.rules.excluded_for_review += sum(1 for item in gold_record.requirements if not item.rule_scored)
        for expected, actual in pairs:
            if not expected.rule_scored:
                continue
            report.rules.scored += 1
            if expected.is_mandatory != actual.is_mandatory:
                report.rules.mandatory_mismatch += 1
            if _rule_key(expected) == _rule_key(actual):
                report.rules.correct += 1
            elif actual.is_structured:
                report.rules.false_structured += 1
                report.false_structured_ids.append(expected.id)
            else:
                report.rules.missed_structure += 1
    return report


__all__ = ["EvaluationReport", "RuleCounts", "canonical_url", "evaluate", "normalize_text"]
