"""Application configuration using Pydantic Settings."""
import ipaddress
import os
import re
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]

#: The placeholder shipped in ``.env.example``; never acceptable in production.
EXAMPLE_JWT_SECRET = "replace-with-a-long-random-secret"
MIN_PRODUCTION_SECRET_LENGTH = 32


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


_APP_ENVS = frozenset({"development", "test", "production"})
_APP_ENV_ALIASES = {"dev": "development", "prod": "production"}
#: The optional dotenv file. ``APP_ENV_FILE`` overrides the path; an empty value disables it, which
#: tests use to check behaviour with a variable genuinely unset (no developer ``backend/.env``).
_ENV_FILE = os.environ.get("APP_ENV_FILE", str(BACKEND_DIR / ".env")) or None


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    DATABASE_URL: str
    TEST_DATABASE_URL: str | None = None
    #: ``development`` (default), ``test`` or ``production``; ``dev`` and ``prod`` are accepted aliases.
    #: Whitespace and case are normalised; anything else (``staging``, typos) is refused at startup
    #: rather than silently treated as development. On Render (``RENDER=true``) it must be set
    #: explicitly, so a missing variable can't downgrade production to development behaviour.
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
    #: Credential attempts (login, registration, password-reset requests) allowed per minute,
    #: per account email and, when the client-IP strategy yields an identity, per client address.
    #: Defaults to 10. Must be an integer from 1 to 1000. The literal ``disabled`` turns the
    #: limiter off and is accepted **only outside production** (the test suite sets it
    #: explicitly). Production refuses to start with it disabled, zero, negative or unparseable:
    #: with ``CLIENT_IP_STRATEGY=none`` the account budget is the only credential limit.
    AUTH_RATE_LIMIT_PER_MINUTE: int | Literal["disabled"] = 10
    #: Where the rate limiter takes the client address from (see ``app.core.client_ip``):
    #:
    #: * ``peer`` (default): the address the ASGI server reports. Behind a proxy
    #:   with ``--proxy-headers --forwarded-allow-ips="*"`` that is the
    #:   *leftmost*, client-controlled ``X-Forwarded-For`` entry, so it can be forged.
    #: * ``xff_rightmost``: walking ``X-Forwarded-For`` from the right through at
    #:   most ``TRUSTED_PROXY_HOPS`` entries, the first that is not a trusted proxy.
    #: * ``header``: a single-address header set by the trusted edge (``CLIENT_IP_HEADER``).
    #: * ``render_cf_connecting_ip``: the ``CF-Connecting-IP`` value on a public Render web
    #:   service, whatever the peer or ``X-Forwarded-For`` say. **Only** valid there: see
    #:   ``docs/architecture/RENDER_CLIENT_IP_VERIFICATION.md`` for its assumptions.
    #: * ``none``: no per-address budget at all; only the per-account budget applies.
    #:
    #: In production on Render ``peer`` is refused: there the peer is either Render's proxy
    #: (one bucket shared by every student) or, under ``--forwarded-allow-ips="*"``, the
    #: client-chosen leftmost ``X-Forwarded-For`` entry. Choose ``none`` until the
    #: ``CF-Connecting-IP`` black-box check passes, then ``render_cf_connecting_ip``.
    #:
    #: The two header strategies are honoured only when the immediate peer is in
    #: ``TRUSTED_PROXY_CIDRS``, which requires running the server **without**
    #: ``--proxy-headers`` so the peer is the real TCP peer. When no trustworthy
    #: address can be established (header missing or malformed, an untrusted
    #: peer sending forwarding headers, a proxy address under ``peer``) the
    #: address budget is skipped for that request; the account budget still
    #: applies. Don't pair ``peer`` with ``--no-proxy-headers`` behind an unlisted
    #: proxy: the proxy's own address would become every client's bucket.
    CLIENT_IP_STRATEGY: Literal["peer", "xff_rightmost", "header", "render_cf_connecting_ip", "none"] = "peer"
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

    #: How transactional email (password reset, verification) is delivered:
    #:
    #: * ``disabled`` (default): nothing is sent. ``/auth/forgot-password`` refuses every
    #:   request with the same 503 (no token is minted), and the outbox worker exits
    #:   without touching the queue. Nothing ever pretends an email went out.
    #: * ``smtp``: deliver through ``SMTP_HOST`` with TLS (``SMTP_SECURITY``). Requires
    #:   ``SMTP_HOST`` and ``SMTP_FROM``; set it on the API *and* the worker.
    #: * ``memory``: an in-process mailbox for tests only; refused in production.
    EMAIL_DELIVERY: Literal["disabled", "smtp", "memory"] = "disabled"
    SMTP_HOST: str | None = None
    SMTP_PORT: int = Field(default=587, ge=1, le=65535)
    #: ``starttls`` (usually port 587) or ``ssl`` (implicit TLS, usually port 465). There is
    #: deliberately no plaintext option: credentials and reset links never cross the wire unencrypted.
    SMTP_SECURITY: Literal["starttls", "ssl"] = "starttls"
    SMTP_USERNAME: str | None = None
    SMTP_PASSWORD: SecretStr | None = None
    SMTP_FROM: str | None = None
    #: Versioned keys for password-reset/verification token derivation, independent of JWT_SECRET:
    #: ``id:secret[,id:secret...]``. Ids are 1-16 lower-case letters/digits; each secret at least
    #: 32 characters (e.g. ``openssl rand -base64 48``). Required whenever email delivery is on.
    #: Keep a retired key listed until ``python -m app.cli email-token-key-usage`` shows no live
    #: queued email still uses it (at most 1 hour after rotation, the token lifetime).
    EMAIL_TOKEN_KEYS: SecretStr | None = None
    #: The key id new tokens are issued under; must be listed in EMAIL_TOKEN_KEYS.
    EMAIL_TOKEN_ACTIVE_KEY: str | None = None
    #: Password-reset request protection, per account: at most one new reset email per cooldown
    #: window and per-day cap; past either, requests are answered identically but send nothing new.
    PASSWORD_RESET_COOLDOWN_SECONDS: int = Field(default=900, ge=60, le=86400)
    PASSWORD_RESET_DAILY_LIMIT: int = Field(default=5, ge=1, le=50)
    #: Queue ceiling: with this many reset emails already pending, new requests queue nothing.
    PASSWORD_RESET_MAX_PENDING: int = Field(default=1000, ge=10, le=100000)

    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    @field_validator("APP_ENV", mode="before")
    @classmethod
    def normalise_app_env(cls, value: object) -> str:
        normalised = str(value).strip().lower() if value is not None else ""
        normalised = _APP_ENV_ALIASES.get(normalised, normalised)
        if normalised not in _APP_ENVS:
            raise ValueError(f"APP_ENV must be one of {', '.join(sorted(_APP_ENVS))} (aliases: dev, prod)")
        return normalised

    @model_validator(mode="after")
    def require_explicit_app_env_on_render(self) -> "Settings":
        """On Render a missing APP_ENV would otherwise mean development (insecure cookies, optional limits)."""
        if os.environ.get("RENDER") == "true" and "APP_ENV" not in self.model_fields_set:
            raise ValueError("APP_ENV must be set explicitly on Render")
        return self

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
        if self.CLIENT_IP_STRATEGY == "none":
            if networks or (self.CLIENT_IP_HEADER or "").strip():
                raise ValueError("CLIENT_IP_STRATEGY=none ignores TRUSTED_PROXY_CIDRS and CLIENT_IP_HEADER; unset them")
            return self
        if self.CLIENT_IP_STRATEGY == "peer" and self.is_production and os.environ.get("RENDER") == "true":
            raise ValueError(
                "CLIENT_IP_STRATEGY=peer is refused in production on Render: the peer is Render's proxy or a "
                "client-forged X-Forwarded-For entry. Set CLIENT_IP_STRATEGY=none (account budget only) or, once "
                "verified, render_cf_connecting_ip"
            )
        if self.CLIENT_IP_STRATEGY == "render_cf_connecting_ip":
            # This strategy doesn't consult them, so setting them would only suggest a check that isn't made.
            if networks or (self.CLIENT_IP_HEADER or "").strip():
                raise ValueError("CLIENT_IP_STRATEGY=render_cf_connecting_ip ignores TRUSTED_PROXY_CIDRS and CLIENT_IP_HEADER; unset them")
            # Render documents RENDER=true on every service. Anywhere else, callers could forge the header.
            if self.is_production and os.environ.get("RENDER") != "true":
                raise ValueError("CLIENT_IP_STRATEGY=render_cf_connecting_ip is valid in production only on Render")
            return self
        if self.CLIENT_IP_STRATEGY != "peer":
            if not networks:
                raise ValueError(f"CLIENT_IP_STRATEGY={self.CLIENT_IP_STRATEGY} requires TRUSTED_PROXY_CIDRS")
        if self.CLIENT_IP_STRATEGY == "header" and not (self.CLIENT_IP_HEADER or "").strip():
            raise ValueError("CLIENT_IP_STRATEGY=header requires CLIENT_IP_HEADER")
        return self

    @field_validator("AUTH_RATE_LIMIT_PER_MINUTE", mode="before")
    @classmethod
    def parse_auth_rate_limit(cls, value: object) -> object:
        """Accept an integer or the word ``disabled``; anything else (including blank) is an error."""
        if isinstance(value, str):
            stripped = value.strip()
            if stripped.lower() == "disabled":
                return "disabled"
            if not stripped.lstrip("-").isdigit():
                raise ValueError("AUTH_RATE_LIMIT_PER_MINUTE must be an integer from 1 to 1000, or 'disabled' outside production")
            return int(stripped)
        if isinstance(value, bool):
            raise ValueError("AUTH_RATE_LIMIT_PER_MINUTE must be an integer")
        return value

    @model_validator(mode="after")
    def require_a_credential_rate_limit(self) -> "Settings":
        """Never run production without the per-account credential budget."""
        value = self.AUTH_RATE_LIMIT_PER_MINUTE
        if value == "disabled":
            if self.is_production:
                raise ValueError("AUTH_RATE_LIMIT_PER_MINUTE=disabled is refused in production")
            return self
        if not 1 <= value <= 1000:
            raise ValueError("AUTH_RATE_LIMIT_PER_MINUTE must be an integer from 1 to 1000")
        return self

    @property
    def auth_rate_limit(self) -> int | None:
        """The effective per-minute budget, or None when explicitly disabled (never in production).

        ``None`` is also tolerated here because tests assign it directly to switch the limiter off.
        """
        value = self.AUTH_RATE_LIMIT_PER_MINUTE
        if value in (None, "disabled"):
            return None
        return int(value)

    @model_validator(mode="after")
    def require_complete_email_delivery_settings(self) -> "Settings":
        """Refuse a delivery mode that would silently drop or fake email."""
        if self.EMAIL_DELIVERY == "memory" and self.is_production:
            raise ValueError("EMAIL_DELIVERY=memory is for tests only and is refused in production")
        if self.EMAIL_DELIVERY == "smtp":
            missing = [name for name in ("SMTP_HOST", "SMTP_FROM") if not (getattr(self, name) or "").strip()]
            if missing:
                raise ValueError(f"EMAIL_DELIVERY=smtp requires {', '.join(missing)}")
            if "@" not in (self.SMTP_FROM or ""):
                raise ValueError("SMTP_FROM must be an email address")
        if bool((self.SMTP_USERNAME or "").strip()) != bool(self.SMTP_PASSWORD and self.SMTP_PASSWORD.get_secret_value()):
            raise ValueError("SMTP_USERNAME and SMTP_PASSWORD must be set together")
        keys = self.email_token_keys  # validates the format whenever it is set
        if keys or (self.EMAIL_TOKEN_ACTIVE_KEY or "").strip():
            if (self.EMAIL_TOKEN_ACTIVE_KEY or "").strip() not in keys:
                raise ValueError("EMAIL_TOKEN_ACTIVE_KEY must name one of the ids in EMAIL_TOKEN_KEYS")
        if self.EMAIL_DELIVERY != "disabled" and not keys:
            raise ValueError("Email delivery requires EMAIL_TOKEN_KEYS and EMAIL_TOKEN_ACTIVE_KEY")
        return self

    @property
    def email_token_keys(self) -> dict[str, bytes]:
        """``{key_id: secret}`` parsed from EMAIL_TOKEN_KEYS; empty when unset. Raises ValueError if malformed."""
        raw = self.EMAIL_TOKEN_KEYS.get_secret_value() if self.EMAIL_TOKEN_KEYS else ""
        keys: dict[str, bytes] = {}
        for entry in filter(None, (part.strip() for part in raw.split(","))):
            key_id, sep, secret = entry.partition(":")
            if not sep or not re.fullmatch(r"[a-z0-9]{1,16}", key_id):
                raise ValueError("EMAIL_TOKEN_KEYS entries must look like id:secret with a 1-16 character [a-z0-9] id")
            if len(secret) < 32:
                raise ValueError("Each EMAIL_TOKEN_KEYS secret must be at least 32 characters")
            if key_id in keys:
                raise ValueError("EMAIL_TOKEN_KEYS ids must be unique")
            keys[key_id] = secret.encode()
        return keys

    @property
    def email_delivery_enabled(self) -> bool:
        return self.EMAIL_DELIVERY != "disabled"

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
        return self.APP_ENV == "production"  # normalised at load time

    @property
    def cors_origins(self) -> list[str]:
        return _split_csv(self.CORS_ORIGINS)

    @property
    def allowed_hosts(self) -> list[str]:
        return _split_csv(self.ALLOWED_HOSTS)


settings = Settings()
