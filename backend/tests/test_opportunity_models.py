"""Relationship and persistence tests for Opportunity, Source and Requirement.

Each test runs inside the transaction provided by ``db_session`` and is
rolled back afterwards, so the dedicated test database stays clean.
"""
from __future__ import annotations

import uuid
from typing import Any

import pytest
from pydantic import ValidationError
from sqlalchemy import func, insert, select, text
from sqlalchemy.exc import DBAPIError

from app.models import Opportunity, Requirement, Source
from app.schemas import OpportunityCreate, RequirementCreate, SourceCreate


def make_opportunity(**overrides: Any) -> Opportunity:
    """Build an Opportunity through its schema (unique slug per call)."""
    payload: dict[str, Any] = {
        "slug": f"aero-summer-2026-{uuid.uuid4().hex[:10]}",
        "title": "Aerospace Engineering Summer Research Program 2026",
        "opportunity_type": "research_program",
        "description": "A ten-week research placement for undergraduate engineers.",
        "host_name": "ETH Zurich",
        "official_url": "https://example.ethz.ch/summer-research",
        "deadline_at": "2026-12-01T23:59:00+00:00",
        "deadline_type": "fixed",
        "starts_at": "2027-06-15",
        "ends_at": "2027-08-20",
        "location_mode": "onsite",
        "countries": ["CH", "ET"],
        "languages": ["en"],
        "tags": ["engineering", "research"],
        "status": "published",
        "published_at": "2026-09-01T10:00:00+00:00",
    }
    payload.update(overrides)
    return Opportunity(**OpportunityCreate(**payload).model_dump())


def make_requirement(**overrides: Any) -> Requirement:
    """Build a Requirement through its schema."""
    payload: dict[str, Any] = {
        "label": "Minimum cumulative GPA of 3.0 (4.0 scale)",
        "kind": "numeric_threshold",
        "params": {"metric": "gpa", "operator": ">=", "value": 3.0, "scale": 4.0},
        "order_index": 0,
        "category": "academic",
        "source_quote": "Applicants must have a minimum GPA of 3.0 on a 4.0 scale.",
    }
    payload.update(overrides)
    return Requirement(**RequirementCreate(**payload).model_dump())


def make_source(**overrides: Any) -> Source:
    """Build a Source through its schema."""
    payload: dict[str, Any] = {
        "source_type": "official_page",
        "url": "https://example.ethz.ch/summer-research",
        "publisher": "ETH Zurich",
        "is_primary": True,
        "raw_snapshot": {"extracted_text": "Applicants must have a minimum GPA of 3.0."},
    }
    payload.update(overrides)
    return Source(**SourceCreate(**payload).model_dump())


def test_opportunity_can_be_created(db_session):
    opportunity = make_opportunity()
    db_session.add(opportunity)
    db_session.flush()
    db_session.refresh(opportunity)

    assert isinstance(opportunity.id, uuid.UUID)
    assert opportunity.slug.startswith("aero-summer-2026-")
    assert opportunity.title == "Aerospace Engineering Summer Research Program 2026"
    assert opportunity.opportunity_type == "research_program"
    assert opportunity.host_name == "ETH Zurich"
    assert opportunity.deadline_at.year == 2026
    assert opportunity.deadline_type == "fixed"
    assert opportunity.location_mode == "onsite"
    assert opportunity.countries == ["CH", "ET"]
    assert opportunity.languages == ["en"]
    assert opportunity.tags == ["engineering", "research"]
    assert opportunity.status == "published"
    assert opportunity.created_at is not None
    assert opportunity.updated_at is not None
    assert opportunity.published_at is not None


def test_source_belongs_to_opportunity(db_session):
    opportunity = make_opportunity()
    source = make_source()
    opportunity.sources.append(source)
    db_session.add(opportunity)
    db_session.flush()

    assert source.opportunity_id == opportunity.id
    assert source.opportunity is opportunity

    db_session.expire_all()
    reloaded = db_session.get(Opportunity, opportunity.id)
    assert len(reloaded.sources) == 1
    assert reloaded.sources[0].id == source.id
    assert reloaded.sources[0].raw_snapshot == {"extracted_text": "Applicants must have a minimum GPA of 3.0."}
    assert reloaded.sources[0].is_primary is True


def test_requirement_belongs_to_opportunity(db_session):
    opportunity = make_opportunity()
    requirement = make_requirement()
    opportunity.requirements.append(requirement)
    db_session.add(opportunity)
    db_session.flush()

    assert requirement.opportunity_id == opportunity.id
    assert requirement.opportunity is opportunity

    db_session.expire_all()
    reloaded = db_session.get(Opportunity, opportunity.id)
    assert len(reloaded.requirements) == 1
    assert reloaded.requirements[0].id == requirement.id
    assert reloaded.requirements[0].label == "Minimum cumulative GPA of 3.0 (4.0 scale)"
    assert reloaded.requirements[0].kind == "numeric_threshold"
    assert reloaded.requirements[0].is_mandatory is True


def test_requirement_can_reference_source(db_session):
    opportunity = make_opportunity()
    source = make_source()
    requirement = make_requirement()
    opportunity.sources.append(source)
    opportunity.requirements.append(requirement)
    requirement.source = source
    db_session.add(opportunity)
    db_session.flush()
    quote = requirement.source_quote

    assert requirement.source is source
    assert source.requirements == [requirement]

    db_session.expire_all()
    reloaded = db_session.get(Requirement, requirement.id)
    assert reloaded.source_id == source.id
    assert reloaded.source_quote == quote
    assert reloaded.source.url == "https://example.ethz.ch/summer-research"
    assert reloaded.source.publisher == "ETH Zurich"
    assert reloaded.source.requirements == [reloaded]


def test_multiple_requirements_belong_to_one_opportunity(db_session):
    opportunity = make_opportunity()
    requirements = [
        make_requirement(
            order_index=2,
            label="Currently enrolled at a university",
            kind="boolean_flag",
            params={"metric": "is_currently_enrolled", "expected": True},
            category="academic",
        ),
        make_requirement(
            order_index=0,
            label="IELTS overall score of at least 6.5",
            kind="numeric_threshold",
            params={"metric": "ielts_overall", "operator": ">=", "value": 6.5},
            category="language",
            source_quote="IELTS 6.5 or equivalent is required.",
        ),
        make_requirement(
            order_index=1,
            label="Open to engineering students",
            kind="set_membership",
            params={"metric": "field_of_study", "operator": "within_taxonomy", "allowed": ["engineering"]},
            category="academic",
        ),
    ]
    for requirement in requirements:
        opportunity.requirements.append(requirement)
    db_session.add(opportunity)
    db_session.flush()

    db_session.expire_all()
    reloaded = db_session.get(Opportunity, opportunity.id)
    assert len(reloaded.requirements) == 3
    assert [item.order_index for item in reloaded.requirements] == [0, 1, 2]
    assert {item.kind for item in reloaded.requirements} == {
        "numeric_threshold",
        "boolean_flag",
        "set_membership",
    }


def test_jsonb_params_are_persisted(db_session):
    opportunity = make_opportunity()
    gpa_requirement = make_requirement()
    any_of_requirement = make_requirement(
        label="Strong GPA or strong IELTS score",
        kind="any_of",
        params={
            "any_of": [
                {"kind": "numeric_threshold", "params": {"metric": "gpa", "operator": ">=", "value": 3.5}},
                {"kind": "numeric_threshold", "params": {"metric": "ielts_overall", "operator": ">=", "value": 7.0}},
            ]
        },
        category="academic",
        source_quote="Strong candidates hold a 3.5 GPA or IELTS 7.0.",
    )
    opportunity.requirements.append(gpa_requirement)
    opportunity.requirements.append(any_of_requirement)
    db_session.add(opportunity)
    db_session.flush()
    gpa_id = gpa_requirement.id
    any_of_id = any_of_requirement.id

    db_session.expire_all()
    reloaded_gpa = db_session.get(Requirement, gpa_id)
    assert reloaded_gpa.params == {
        "metric": "gpa",
        "operator": ">=",
        "value": 3.0,
        "scale": 4.0,
    }

    jsonb_row = db_session.execute(
        text(
            "SELECT jsonb_typeof(params) AS value_type, "
            "params->>'metric' AS metric, "
            "(params->>'value')::float AS threshold "
            "FROM requirements WHERE id = :id"
        ),
        {"id": gpa_id},
    ).one()
    assert jsonb_row.value_type == "object"
    assert jsonb_row.metric == "gpa"
    assert jsonb_row.threshold == 3.0

    reloaded_any_of = db_session.get(Requirement, any_of_id)
    children = reloaded_any_of.params["any_of"]
    assert len(children) == 2
    assert children[0]["kind"] == "numeric_threshold"
    assert children[0]["params"] == {"metric": "gpa", "operator": ">=", "value": 3.5}
    assert children[1]["params"] == {"metric": "ielts_overall", "operator": ">=", "value": 7.0}


def test_deleting_opportunity_cascades_to_requirements_and_sources(db_session):
    opportunity = make_opportunity()
    source = make_source()
    first = make_requirement()
    second = make_requirement(
        order_index=1,
        label="Currently enrolled at a university",
        kind="boolean_flag",
        params={"metric": "is_currently_enrolled", "expected": True},
    )
    opportunity.sources.append(source)
    opportunity.requirements.extend([first, second])
    first.source = source
    db_session.add(opportunity)
    db_session.flush()
    opportunity_id = opportunity.id

    db_session.expunge_all()
    fresh = db_session.get(Opportunity, opportunity_id)
    assert fresh is not None
    db_session.delete(fresh)
    db_session.flush()
    db_session.expire_all()

    assert db_session.get(Opportunity, opportunity_id) is None
    remaining_requirements = db_session.scalar(
        select(func.count()).select_from(Requirement).where(Requirement.opportunity_id == opportunity_id)
    )
    remaining_sources = db_session.scalar(
        select(func.count()).select_from(Source).where(Source.opportunity_id == opportunity_id)
    )
    assert remaining_requirements == 0
    assert remaining_sources == 0


def test_deleting_source_nulls_requirement_source_id(db_session):
    opportunity = make_opportunity()
    source = make_source()
    requirement = make_requirement()
    opportunity.sources.append(source)
    opportunity.requirements.append(requirement)
    requirement.source = source
    db_session.add(opportunity)
    db_session.flush()
    requirement_id = requirement.id
    source_id = source.id

    db_session.delete(source)
    db_session.flush()
    db_session.expire_all()

    reloaded = db_session.get(Requirement, requirement_id)
    assert reloaded is not None
    assert reloaded.source_id is None
    assert reloaded.source_quote == "Applicants must have a minimum GPA of 3.0 on a 4.0 scale."
    assert db_session.get(Source, source_id) is None


def test_database_check_constraint_rejects_unknown_kind(db_session):
    opportunity = make_opportunity()
    db_session.add(opportunity)
    db_session.flush()

    with pytest.raises(DBAPIError):
        with db_session.begin_nested():
            db_session.execute(
                insert(Requirement).values(
                    id=uuid.uuid4(),
                    opportunity_id=opportunity.id,
                    order_index=0,
                    label="Bogus requirement",
                    kind="not_a_kind",
                    params={},
                )
            )

    assert db_session.execute(text("SELECT 1")).scalar_one() == 1


def test_requirement_schema_rejects_invalid_params():
    with pytest.raises(ValidationError) as missing_value:
        RequirementCreate(
            label="Minimum GPA",
            kind="numeric_threshold",
            params={"metric": "gpa", "operator": ">="},
        )
    assert "value: Field required" in str(missing_value.value)

    with pytest.raises(ValidationError):
        RequirementCreate(label="x", kind="not_a_kind", params={})

    with pytest.raises(ValidationError):
        RequirementCreate(
            label="x",
            kind="any_of",
            params={"any_of": [{"kind": "date_gate", "params": {"metric": "d", "operator": "<=", "value": "nope"}}]},
        )

    with pytest.raises(ValidationError):
        RequirementCreate(
            label="x",
            kind="numeric_threshold",
            params={"metirc": "gpa", "operator": ">=", "value": 3.0},
        )


def test_requirement_schema_normalizes_params():
    numeric = RequirementCreate(
        label="Minimum GPA",
        kind="numeric_threshold",
        params={"metric": "gpa", "operator": ">=", "value": 3},
    )
    assert numeric.params == {"metric": "gpa", "operator": ">=", "value": 3.0}

    date_gate = RequirementCreate(
        label="Deadline",
        kind="date_gate",
        params={"metric": "application_date", "operator": "<=", "value": "2026-12-01"},
    )
    assert date_gate.params == {"metric": "application_date", "operator": "<=", "value": "2026-12-01"}

    skill_set = RequirementCreate(label="Python required", kind="skill_set", params={"required": ["python"]})
    assert skill_set.params == {"metric": "skills", "operator": "contains_any", "required": ["python"]}


def test_opportunity_schema_rejects_invalid_input():
    with pytest.raises(ValidationError):
        OpportunityCreate(slug="Bad Slug!", title="x")

    with pytest.raises(ValidationError):
        OpportunityCreate(slug="valid-slug", title="x", starts_at="2026-10-01", ends_at="2026-09-01")

    with pytest.raises(ValidationError):
        OpportunityCreate(slug="valid-slug", title="x", official_url="ftp://example.org/x")
