"""FastAPI application entry point."""
from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from sqlalchemy import text
from app.api.routers.opportunities import router as opportunities_router
from app.core.config import settings
from app.db.session import engine


logging.basicConfig(level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO))
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Startup: test database connection
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("Database connection successful")
    except Exception:
        logger.error("Database connection failed")
        raise
    yield
    # Shutdown
    engine.dispose()


app = FastAPI(
    title="Opportunity Hub API",
    description="Personalized opportunity discovery platform",
    version="0.1.0",
    lifespan=lifespan,
)
app.include_router(opportunities_router)


@app.get("/health", tags=["health"])
async def health_check() -> dict:
    """Health check endpoint."""
    return {"status": "ok"}