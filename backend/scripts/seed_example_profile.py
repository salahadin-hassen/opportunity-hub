"""Persist one realistic development profile and related Slice 2 records."""
from datetime import date

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import Education, Profile, TestScore

EXAMPLE_EMAIL = "mekdes.tadesse@example.test"


def main() -> None:
    with SessionLocal.begin() as session:
        existing = session.scalar(select(Profile).where(Profile.email == EXAMPLE_EMAIL))
        if existing:
            print(f"Example profile already exists: {EXAMPLE_EMAIL}")
            return

        profile = Profile(
            full_name="Mekdes Tadesse",
            email=EXAMPLE_EMAIL,
            date_of_birth=date(2003, 4, 18),
            citizenships=["ET"],
            country_of_residence="ET",
            degree_level="bachelor",
            is_currently_enrolled=True,
            languages=["am", "en"],
            links={"github": "https://github.com/mekdes-tadesse", "linkedin": "https://www.linkedin.com/in/mekdes-tadesse"},
            interests=["aerospace engineering", "flight software", "open source", "robotics"],
            bio="Aerospace engineering student interested in satellite systems and reliable software for flight projects.",
        )
        profile.education.append(Education(
            institution_name="Addis Ababa University",
            degree_level="bachelor",
            field_of_study="Aerospace Engineering",
            country="ET",
            start_date=date(2023, 10, 1),
            is_current=True,
            gpa=3.72,
            gpa_scale=4.0,
            is_primary=True,
        ))
        profile.test_scores.append(TestScore(
            test_type="ielts",
            overall_score=7.5,
            sub_scores={"listening": 8.0, "reading": 7.5, "writing": 7.0, "speaking": 7.5},
            test_date=date(2025, 6, 14),
            expires_at=date(2027, 6, 14),
        ))
        session.add(profile)
        print(f"Persisted example profile: {EXAMPLE_EMAIL}")


if __name__ == "__main__":
    main()
