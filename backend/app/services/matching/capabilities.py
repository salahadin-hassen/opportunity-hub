"""Single source of truth for deterministic rule capabilities (plan §B.3).

Lists every supported (kind, metric, operators) tuple and the exact profile
fact it inspects. Used for write-time requirement validation (ELIG-002), by
the public capabilities endpoint (`GET /eligibility/capabilities`), and by the
frontend labels to ensure zero divergence between the engine and user display.
"""
from __future__ import annotations

from typing import Any
from pydantic import BaseModel, ConfigDict

from app.models.enums import RequirementKind


class Capability(BaseModel):
    """One supported rule metric and evaluator capability."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: str
    metric: str
    supported_operators: list[str]
    profile_fact: str
    fact_label: str
    value_type: str
    description: str


CAPABILITIES_CATALOG: tuple[Capability, ...] = (
    Capability(
        kind=RequirementKind.NUMERIC_THRESHOLD.value,
        metric="gpa",
        supported_operators=[">=", "<=", ">", "<", "==", "!="],
        profile_fact="gpa",
        fact_label="Primary Education GPA",
        value_type="number",
        description="Compares student's primary education GPA with scale normalization (e.g., 4.0 scale).",
    ),
    Capability(
        kind=RequirementKind.NUMERIC_THRESHOLD.value,
        metric="toefl_total",
        supported_operators=[">=", ">"],
        profile_fact="test_scores",
        fact_label="TOEFL Total Score",
        value_type="number",
        description="Verifies the student has taken TOEFL and achieved at least the required score.",
    ),
    Capability(
        kind=RequirementKind.NUMERIC_THRESHOLD.value,
        metric="ielts_overall",
        supported_operators=[">=", ">"],
        profile_fact="test_scores",
        fact_label="IELTS Overall Band",
        value_type="number",
        description="Verifies the student's IELTS overall band meets the minimum score.",
    ),
    Capability(
        kind=RequirementKind.NUMERIC_THRESHOLD.value,
        metric="gre_quantitative",
        supported_operators=[">=", ">"],
        profile_fact="test_scores",
        fact_label="GRE Quantitative Score",
        value_type="number",
        description="Verifies GRE quantitative reasoning score.",
    ),
    Capability(
        kind=RequirementKind.NUMERIC_THRESHOLD.value,
        metric="gre_verbal",
        supported_operators=[">=", ">"],
        profile_fact="test_scores",
        fact_label="GRE Verbal Score",
        value_type="number",
        description="Verifies GRE verbal reasoning score.",
    ),
    Capability(
        kind=RequirementKind.SET_MEMBERSHIP.value,
        metric="citizenship",
        supported_operators=["in", "not_in"],
        profile_fact="citizenship",
        fact_label="Citizenship",
        value_type="list[string]",
        description="Checks if student's primary or secondary citizenships match the target list.",
    ),
    Capability(
        kind=RequirementKind.SET_MEMBERSHIP.value,
        metric="country_of_residence",
        supported_operators=["in", "not_in"],
        profile_fact="country_of_residence",
        fact_label="Country of Residence",
        value_type="list[string]",
        description="Verifies country of legal residence.",
    ),
    Capability(
        kind=RequirementKind.SET_MEMBERSHIP.value,
        metric="degree_level",
        supported_operators=["in", "not_in"],
        profile_fact="degree_level",
        fact_label="Degree Level",
        value_type="list[string]",
        description="Checks if student's current or target degree level is in the permitted list.",
    ),
    Capability(
        kind=RequirementKind.SET_MEMBERSHIP.value,
        metric="field_of_study",
        supported_operators=["in", "not_in", "within_taxonomy"],
        profile_fact="field_of_study",
        fact_label="Field of Study",
        value_type="list[string]",
        description="Checks primary field of study or major.",
    ),
    Capability(
        kind=RequirementKind.DATE_GATE.value,
        metric="date_of_birth",
        supported_operators=["<=", "<", ">=", ">", "==", "!="],
        profile_fact="date_of_birth",
        fact_label="Date of Birth / Age Gate",
        value_type="date",
        description="Verifies applicant meets age requirements as of program reference date.",
    ),
    Capability(
        kind=RequirementKind.DATE_GATE.value,
        metric="graduation_date",
        supported_operators=["<=", "<", ">=", ">", "==", "!="],
        profile_fact="graduation_date",
        fact_label="Expected or Conferred Graduation Date",
        value_type="date",
        description="Verifies expected graduation or conferral date falls within eligible window.",
    ),
    Capability(
        kind=RequirementKind.SKILL_SET.value,
        metric="skills",
        supported_operators=["contains_any", "contains_all"],
        profile_fact="skills",
        fact_label="Technical & Professional Skills",
        value_type="list[string]",
        description="Evaluates applicant skill tags against required opportunity skillset.",
    ),
    Capability(
        kind=RequirementKind.BOOLEAN_FLAG.value,
        metric="is_currently_enrolled",
        supported_operators=["=="],
        profile_fact="enrollment",
        fact_label="Enrolment Status",
        value_type="boolean",
        description="Checks whether applicant is currently enrolled in degree-granting institution.",
    ),
    Capability(
        kind=RequirementKind.EQUALITY.value,
        metric="*",
        supported_operators=["==", "!="],
        profile_fact="generic",
        fact_label="Exact Match Attribute",
        value_type="scalar",
        description="Generic exact equality against an applicant profile property.",
    ),
    Capability(
        kind=RequirementKind.ANY_OF.value,
        metric="compound",
        supported_operators=["or"],
        profile_fact="composite",
        fact_label="Compound Alternative",
        value_type="composite",
        description="Disjunctive composite requirement satisfied if any branch outcome is MET.",
    ),
)


def get_capabilities() -> list[Capability]:
    """Return the complete immutable capability catalog."""
    return list(CAPABILITIES_CATALOG)


def find_capability(kind: str, metric: str) -> Capability | None:
    """Find a capability matching kind and metric (or wildcard metric)."""
    for cap in CAPABILITIES_CATALOG:
        if cap.kind == kind and (cap.metric == metric or cap.metric == "*"):
            return cap
    return None


def is_supported_rule(kind: str, metric: str, operator: str | None = None) -> bool:
    """Validate whether a rule configuration is supported by the engine."""
    cap = find_capability(kind, metric)
    if not cap:
        return False
    if operator is not None and operator not in cap.supported_operators:
        return False
    return True

