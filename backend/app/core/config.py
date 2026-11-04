"""Application configuration using Pydantic Settings."""
import ipaddress
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, model_validator
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
    #: Comma-separated browser origins allowed to call the API cross-origin,
    #: e.g. ``https://opportunity-hub.onrender.com``. Empty disables CORS
    #: (same-origin or proxied deployments need none). ``*`` is rejected.
    CORS_ORIGINS: str = ""
    #: Comma-separated Host header values to accept. Empty accepts any host.
    ALLOWED_HOSTS: str = ""
    #: Login and registration attempts allowed per minute, separately per client
    #: address bucket and per account email. Unset disables the limit (local
    #: development and tests).
    AUTH_RATE_LIMIT_PER_MINUTE: int | None = None
    #: Where the rate limiter takes the client address from (see ``app.core.client_ip``):
    #:
    #: * ``peer`` (default): the address the ASGI server reports. Behind a proxy
    #:   with ``--proxy-headers --forwarded-allow-ips="*"`` that is the
    #:   *leftmost*, client-controlled ``X-Forwarded-For`` entry, so it can be forged.
    #: * ``xff_rightmost``: walking ``X-Forwarded-For`` from the right through at
    #:   most ``TRUSTED_PROXY_HOPS`` entries, the first that is not a trusted proxy.
    #: * ``header``: a single-address header set by the trusted edge (``CLIENT_IP_HEADER``).
    #:
    #: The two header strategies are honoured only when the immediate peer is in
    #: ``TRUSTED_PROXY_CIDRS``, which requires running the server **without**
    #: ``--proxy-headers`` so the peer is the real TCP peer. When no trustworthy
    #: address can be established (header missing or malformed, an untrusted
    #: peer sending forwarding headers, a proxy address under ``peer``) the
    #: address budget is skipped for that request; the account budget still
    #: applies. Which strategy is right for Render is not yet verified; until it
    #: is, keep ``peer``. Don't pair ``peer`` with ``--no-proxy-headers`` behind
    #: an unlisted proxy: the proxy's own address would become every client's bucket.
    CLIENT_IP_STRATEGY: Literal["peer", "xff_rightmost", "header"] = "peer"
    CLIENT_IP_HEADER: str | None = None
    TRUSTED_PROXY_HOPS: int = Field(default=1, ge=1, le=10)
    TRUSTED_PROXY_CIDRS: str = ""
    #: Argon2 operations (login verification, registration hashing) allowed to
    #: run at once in one process; further attempts are refused with 503 rather
    #: than queued. Each operation holds 64 MiB, so the default keeps hashing
    #: under 128 MiB per process. Total capacity is this times the uvicorn
    #: worker count (``--workers`` or ``WEB_CONCURRENCY``) times the instances.
    ARGON2_MAX_CONCURRENCY: int = Field(default=2, ge=1, le=16)
    #: How many of those slots registration hashing may hold at once. The rest
    #: (``ARGON2_MAX_CONCURRENCY`` minus this) can only be used by login, so a
    #: registration flood can't refuse sign-in. It must not exceed the total.
    #: With a total of 1 no slot can be reserved, and login and registration share it.
    ARGON2_REGISTRATION_MAX_CONCURRENCY: int = Field(default=1, ge=1, le=16)

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

    @model_validator(mode="after")
    def require_trusted_proxies_for_header_strategies(self) -> "Settings":
        """Never read client addresses from headers without knowing which peers may set them."""
        networks = self.trusted_proxy_networks  # validates every entry, whatever the strategy
        if self.CLIENT_IP_STRATEGY != "peer":
            if not networks:
                raise ValueError(f"CLIENT_IP_STRATEGY={self.CLIENT_IP_STRATEGY} requires TRUSTED_PROXY_CIDRS")
        if self.CLIENT_IP_STRATEGY == "header" and not (self.CLIENT_IP_HEADER or "").strip():
            raise ValueError("CLIENT_IP_STRATEGY=header requires CLIENT_IP_HEADER")
        return self

    @model_validator(mode="after")
    def registration_share_fits_the_argon2_ceiling(self) -> "Settings":
        if self.ARGON2_REGISTRATION_MAX_CONCURRENCY > self.ARGON2_MAX_CONCURRENCY:
            raise ValueError("ARGON2_REGISTRATION_MAX_CONCURRENCY must not exceed ARGON2_MAX_CONCURRENCY")
        return self

    @property
    def trusted_proxy_networks(self) -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
        return [ipaddress.ip_network(item, strict=False) for item in _split_csv(self.TRUSTED_PROXY_CIDRS)]

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
