"""FastAPI application entry point."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api.routers.auth import router as auth_router
from app.api.routers.curate import admin_router
from app.api.routers.curate import router as curate_router
from app.api.routers.education import router as education_router
from app.api.routers.matches import router as matches_router
from app.api.routers.opportunities import router as opportunities_router
from app.api.routers.profiles import me_router, router as profiles_router
from app.api.routers.skills import catalog_router as skills_catalog_router
from app.api.routers.skills import router as skills_router
from app.api.routers.test_scores import router as test_scores_router
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
if settings.allowed_hosts:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)
if settings.cors_origins:
    # Bearer tokens travel in the Authorization header, never cookies, so credentials stay off.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
        max_age=600,
    )

app.include_router(auth_router)
app.include_router(curate_router)
app.include_router(admin_router)
app.include_router(education_router)
app.include_router(opportunities_router)
app.include_router(matches_router)
app.include_router(me_router)
app.include_router(profiles_router)
app.include_router(skills_catalog_router)
app.include_router(skills_router)
app.include_router(test_scores_router)


@app.get("/health", tags=["health"])
def health_check():
    """Report ready only when the database answers; reveals nothing else."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:
        logger.warning("Health check: database unavailable")
        return JSONResponse(status_code=503, content={"status": "unavailable"})
    return {"status": "ok"}