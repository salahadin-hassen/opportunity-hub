"""Database configuration and session management."""
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Session:
    """FastAPI dependency for database session.

    Always declare it as ``Depends(get_db, scope="function")``. With the default (request) scope
    FastAPI runs the code after ``yield`` only once the response has been sent, so the commit would
    happen after the client was told the request succeeded: a failed commit would be reported as
    success, and an immediate follow-up request could miss the data. Function scope runs it after
    the response body has been serialised and before anything is sent, so a failed commit is rolled
    back and becomes a 500. Consequence: the session is closed by the time a response is sent, so a
    streaming response or background task must open its own session rather than reuse this one.
    ``tests/test_commit_before_response.py`` enforces the declaration and the ordering.
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@contextmanager
def get_db_context() -> Session:
    """Context manager for database session (non-FastAPI usage)."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()