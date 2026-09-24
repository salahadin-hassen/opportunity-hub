"""Persistence and validation coverage for Slice 2 profile models."""
from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models import Education, Profile, TestScore as ScoreRecord
from app.schemas import EducationCreate, ProfileCreate, TestScoreCreate as ScoreCreate


def make_profile(**overrides):
    payload = {
        "full_name": "Mekdes Tadesse",
        "email": f"mekdes-{uuid.uuid4().hex[:10]}@example.org",
        "citizenships": ["ET"],
        "country_of_residence": "ET",
        "degree_level": "bachelor",
        "is_currently_enrolled": True,
        "languages": ["am", "en"],
        "links": {"github": "https://github.com/mekdes"},
        "interests": ["aerospace", "software engineering"],
        "bio": "Aerospace engineering student building flight software.",
    }
    payload.update(overrides)
    return Profile(**ProfileCreate(**payload).model_dump())


def make_education(**overrides):
    payload = {
        "institution_name": "Addis Ababa University",
        "degree_level": "bachelor",
        "field_of_study": "Aerospace Engineering",
        "country": "ET",
        "start_date": "2023-10-01",
        "is_current": True,
        "gpa": 3.72,
        "gpa_scale": 4.0,
        "is_primary": True,
    }
    payload.update(overrides)
    return Education(**EducationCreate(**payload).model_dump())


def make_test_score(**overrides):
    payload = {
        "test_type": "ielts",
        "overall_score": 7.5,
        "sub_scores": {"listening": 8.0, "reading": 7.5, "writing": 7.0, "speaking": 7.5},
        "test_date": "2025-06-14",
        "expires_at": "2027-06-14",
    }
    payload.update(overrides)
    return ScoreRecord(**ScoreCreate(**payload).model_dump())


def test_profile_can_be_created(db_session):
    profile = make_profile()
    db_session.add(profile)
    db_session.flush()
    db_session.refresh(profile)
    assert profile.id is not None
    assert profile.email.endswith("@example.org")
    assert profile.citizenships == ["ET"]
    assert profile.updated_at is not None


def test_education_belongs_to_profile(db_session):
    profile = make_profile()
    education = make_education()
    profile.education.append(education)
    db_session.add(profile)
    db_session.flush()
    assert education.profile_id == profile.id
    assert education.profile is profile


def test_profile_can_have_multiple_education_records(db_session):
    profile = make_profile()
    profile.education.extend([
        make_education(),
        make_education(institution_name="Bole Secondary School", degree_level="high_school", field_of_study="Science", gpa=None, gpa_scale=None, is_primary=False),
    ])
    db_session.add(profile)
    db_session.flush()
    assert len(db_session.scalars(select(Education).where(Education.profile_id == profile.id)).all()) == 2


def test_only_one_primary_education_per_profile(db_session):
    profile = make_profile()
    profile.education.append(make_education())
    db_session.add(profile)
    db_session.flush()
    with pytest.raises(IntegrityError):
        with db_session.begin_nested():
            db_session.add(Education(
                profile_id=profile.id,
                institution_name="Another University",
                degree_level="bachelor",
                field_of_study="Physics",
                is_primary=True,
            ))
            db_session.flush()


def test_gpa_and_scale_persist_as_pair(db_session):
    profile = make_profile()
    education = make_education(gpa=8.7, gpa_scale=10.0)
    profile.education.append(education)
    db_session.add(profile)
    db_session.flush()
    db_session.refresh(education)
    assert float(education.gpa) == 8.7
    assert float(education.gpa_scale) == 10.0


def test_profile_test_score_relationship(db_session):
    profile = make_profile()
    score = make_test_score()
    profile.test_scores.append(score)
    db_session.add(profile)
    db_session.flush()
    assert score.profile_id == profile.id
    assert score.profile is profile


def test_profile_can_have_multiple_test_scores(db_session):
    profile = make_profile()
    profile.test_scores.extend([make_test_score(), make_test_score(test_type="toefl", overall_score=105, sub_scores={"reading": 27, "listening": 28, "speaking": 24, "writing": 26})])
    db_session.add(profile)
    db_session.flush()
    assert len(profile.test_scores) == 2


def test_jsonb_sub_scores_persist(db_session):
    profile = make_profile()
    profile.test_scores.append(make_test_score())
    db_session.add(profile)
    db_session.flush()
    db_session.expire_all()
    score = db_session.scalar(select(ScoreRecord).where(ScoreRecord.profile_id == profile.id))
    assert score.sub_scores == {"listening": 8.0, "reading": 7.5, "writing": 7.0, "speaking": 7.5}


def test_deleting_profile_cascades_to_education_and_scores(db_session):
    profile = make_profile()
    profile.education.append(make_education())
    profile.test_scores.append(make_test_score())
    db_session.add(profile)
    db_session.flush()
    profile_id = profile.id
    db_session.delete(profile)
    db_session.flush()
    assert db_session.scalars(select(Education).where(Education.profile_id == profile_id)).all() == []
    assert db_session.scalars(select(ScoreRecord).where(ScoreRecord.profile_id == profile_id)).all() == []


def test_profile_schema_rejects_invalid_email():
    with pytest.raises(ValidationError):
        ProfileCreate(full_name="Student", email="not-an-email", degree_level="bachelor")


@pytest.mark.parametrize("gpa", [-0.1, 4.1])
def test_education_schema_rejects_invalid_gpa(gpa):
    with pytest.raises(ValidationError):
        EducationCreate(institution_name="AAU", degree_level="bachelor", field_of_study="Physics", gpa=gpa, gpa_scale=4.0)


def test_education_schema_rejects_gpa_without_scale():
    with pytest.raises(ValidationError):
        EducationCreate(institution_name="AAU", degree_level="bachelor", field_of_study="Physics", gpa=3.5)


def test_education_schema_rejects_scale_without_gpa():
    with pytest.raises(ValidationError):
        EducationCreate(institution_name="AAU", degree_level="bachelor", field_of_study="Physics", gpa_scale=4.0)


def test_test_score_schema_rejects_negative_score_and_invalid_dates():
    with pytest.raises(ValidationError):
        ScoreCreate(test_type="ielts", overall_score=-1)
    with pytest.raises(ValidationError):
        ScoreCreate(test_type="ielts", overall_score=7, test_date="2025-05-01", expires_at="2024-05-01")
