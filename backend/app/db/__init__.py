"""Database package exports.

``Base`` (the models' metadata) is imported eagerly. The engine and sessions are loaded on first use,
so data-only tools that bring their own connection can import the models without application
settings (no JWT secret needed to read or migrate data).
"""
from app.db.base import Base

__all__ = ["Base", "engine", "SessionLocal", "get_db", "get_db_context"]


def __getattr__(name: str):
    if name in ("engine", "SessionLocal", "get_db", "get_db_context"):
        from app.db import session

        return getattr(session, name)
    raise AttributeError(name)
