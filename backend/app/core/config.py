"""Application configuration using Pydantic Settings."""
from pathlib import Path

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]

#: The placeholder shipped in ``.env.example``; never acceptable in production.
EXAMPLE_JWT_SECRET = "replace-with-a-long-random-secret"
MIN_PRODUCTION_SECRET_LENGTH = 32


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    DATABASE_URL: str
    TEST_DATABASE_URL: str | None = None
    APP_ENV: str = "development"
    LOG_LEVEL: str = "INFO"
    JWT_SECRET: str
    JWT_ALGORITHM: str = "HS256"
    #: Shared secret for curator-only writes such as creating opportunities.
    #: Unset (the default) disables those endpoints entirely.
    ADMIN_API_TOKEN: str | None = None
    #: Comma-separated browser origins allowed to call the API cross-origin,
    #: e.g. ``https://opportunity-hub.onrender.com``. Empty disables CORS
    #: (same-origin or proxied deployments need none). ``*`` is rejected.
    CORS_ORIGINS: str = ""
    #: Comma-separated Host header values to accept. Empty accepts any host.
    ALLOWED_HOSTS: str = ""
    #: Login and registration attempts allowed per client IP per minute.
    #: Unset disables the limit (local development and tests).
    AUTH_RATE_LIMIT_PER_MINUTE: int | None = None

    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    @field_validator("DATABASE_URL", "TEST_DATABASE_URL")
    @classmethod
    def normalize_postgres_scheme(cls, value: str | None) -> str | None:
        """Accept the ``postgres://`` scheme some hosts hand out; SQLAlchemy needs ``postgresql://``."""
        if value and value.startswith("postgres://"):
            return "postgresql://" + value[len("postgres://"):]
        return value

    @field_validator("CORS_ORIGINS")
    @classmethod
    def reject_wildcard_origins(cls, value: str) -> str:
        if "*" in value:
            raise ValueError("CORS_ORIGINS must list explicit origins; '*' is not allowed")
        return value

    @model_validator(mode="after")
    def require_strong_production_secret(self) -> "Settings":
        """Refuse to start a production app with a guessable token-signing secret."""
        if self.is_production and (
            self.JWT_SECRET == EXAMPLE_JWT_SECRET or len(self.JWT_SECRET) < MIN_PRODUCTION_SECRET_LENGTH
        ):
            raise ValueError(
                f"JWT_SECRET must be a random value of at least {MIN_PRODUCTION_SECRET_LENGTH} "
                "characters when APP_ENV is production"
            )
        return self

    @property
    def is_production(self) -> bool:
        return self.APP_ENV.lower() in {"production", "prod"}

    @property
    def cors_origins(self) -> list[str]:
        return _split_csv(self.CORS_ORIGINS)

    @property
    def allowed_hosts(self) -> list[str]:
        return _split_csv(self.ALLOWED_HOSTS)


settings = Settings()
