"""Validated definitions for acquisition sources.

``SourceDefinition`` is everything a curator states about a source; the
registry service persists it. Validation happens here, once, so every
stored source has canonical hostnames, a consistent provider identity and
a bounded crawl policy. Connector-specific configuration is validated by
the connector's own model (see ``app.intelligence.connectors``).
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.intelligence.hosts import InvalidHostError, is_within_domain, normalize_host
from app.models.enums import AuthorityLevel, DiscoveryMethod, SourceCategory

MAX_HOSTS_PER_KIND = 20
MAX_ALIASES = 20


class CrawlPolicy(BaseModel):
    """Politeness and volume bounds for one source.

    The floors are deliberate: no source may be polled more often than
    hourly or faster than one request per second, whatever its config says.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    discovery_interval_hours: int = Field(default=24, ge=1, le=24 * 30)
    max_pages_per_run: int = Field(default=50, ge=1, le=500)
    min_delay_seconds: float = Field(default=5.0, ge=1.0, le=300.0)


class ProviderIdentity(BaseModel):
    """The organisation behind a source, with the other names it publishes under."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1, max_length=255)
    aliases: list[str] = Field(default_factory=list, max_length=MAX_ALIASES)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("provider name is empty")
        return stripped

    @field_validator("aliases")
    @classmethod
    def clean_aliases(cls, values: list[str]) -> list[str]:
        cleaned: list[str] = []
        seen: set[str] = set()
        for value in values:
            alias = value.strip()
            if not alias or len(alias) > 255:
                raise ValueError("each alias must be 1-255 characters")
            if alias.casefold() in seen:
                raise ValueError(f"duplicate alias {alias!r}")
            seen.add(alias.casefold())
            cleaned.append(alias)
        return cleaned

    @model_validator(mode="after")
    def alias_differs_from_name(self) -> ProviderIdentity:
        if self.name.casefold() in {alias.casefold() for alias in self.aliases}:
            raise ValueError("an alias must differ from the provider name")
        return self


class SourceDefinition(BaseModel):
    """What a curator declares when proposing or editing a source."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=255)
    base_domain: str
    allowed_hosts: list[str] = Field(min_length=1, max_length=MAX_HOSTS_PER_KIND)
    application_hosts: list[str] = Field(default_factory=list, max_length=MAX_HOSTS_PER_KIND)
    category: SourceCategory
    authority_level: AuthorityLevel
    provider: ProviderIdentity
    discovery_method: DiscoveryMethod
    connector_key: str = Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_]*$")
    connector_config: dict[str, Any] = Field(default_factory=dict)
    crawl_policy: CrawlPolicy = Field(default_factory=CrawlPolicy)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("name is empty")
        return stripped

    @field_validator("base_domain")
    @classmethod
    def canonical_base_domain(cls, value: str) -> str:
        try:
            return normalize_host(value)
        except InvalidHostError as error:
            raise ValueError(str(error)) from error

    @field_validator("allowed_hosts", "application_hosts")
    @classmethod
    def canonical_hosts(cls, values: list[str]) -> list[str]:
        hosts: list[str] = []
        for value in values:
            try:
                host = normalize_host(value)
            except InvalidHostError as error:
                raise ValueError(str(error)) from error
            if host in hosts:
                raise ValueError(f"duplicate host {host!r}")
            hosts.append(host)
        return hosts

    @model_validator(mode="after")
    def hosts_consistent(self) -> SourceDefinition:
        outside = [host for host in self.allowed_hosts if not is_within_domain(host, self.base_domain)]
        if outside:
            raise ValueError(
                f"allowed hosts must be {self.base_domain} or its subdomains; not: {', '.join(outside)}"
            )
        overlap = set(self.allowed_hosts) & set(self.application_hosts)
        if overlap:
            raise ValueError(f"a host cannot be both allowed and application-only: {', '.join(sorted(overlap))}")
        return self


__all__ = ["CrawlPolicy", "ProviderIdentity", "SourceDefinition"]
