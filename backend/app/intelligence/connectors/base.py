"""The connector contract: how a discovery method plugs into the pipeline.

A connector turns one approved source into *leads* (candidate page URLs).
It is deliberately powerless:

* it receives a frozen ``SourceView`` (never an ORM row or a database session);
* it may read pages only through the ``PageReader`` it is handed, which the
  pipeline scopes to the source's exact allowed hosts;
* everything it returns is re-validated by ``app.intelligence.discovery``
  before anything else sees it.

Connectors must not open network connections themselves; an architecture
test fails the build if a connector module imports a networking library.
"""
from __future__ import annotations

import re
import uuid
from abc import ABC, abstractmethod
from collections.abc import Iterable
from dataclasses import dataclass
from typing import ClassVar, Protocol

from pydantic import BaseModel

from app.intelligence.definitions import CrawlPolicy
from app.models.enums import DiscoveryMethod

_CONNECTOR_KEY = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


@dataclass(frozen=True)
class SourceView:
    """The read-only facts about one source that a connector may use."""

    id: uuid.UUID
    name: str
    base_domain: str
    allowed_hosts: frozenset[str]
    discovery_method: DiscoveryMethod
    crawl_policy: CrawlPolicy
    config: BaseModel


@dataclass(frozen=True)
class Lead:
    """One candidate page a connector found; only a claim until validated."""

    url: str
    #: Identifier the source itself assigns (feed GUID, API id), if any.
    external_id: str | None = None


@dataclass(frozen=True)
class PageContent:
    """A page as returned by the pipeline's fetcher (implemented in M2-T7)."""

    url: str
    final_url: str
    status_code: int
    content_type: str
    body: bytes


class PageReader(Protocol):
    """The only way a connector can read a page; the pipeline supplies a source-scoped implementation."""

    def read(self, url: str) -> PageContent: ...


class Connector(ABC):
    """Base class every discovery connector extends.

    Subclasses declare their ``key``, the ``discovery_method`` they implement
    and a Pydantic ``config_model`` (with ``extra="forbid"``) describing
    their per-source configuration, then register with ``@register_connector``.
    """

    key: ClassVar[str]
    discovery_method: ClassVar[DiscoveryMethod]
    config_model: ClassVar[type[BaseModel]]

    @abstractmethod
    def discover(self, source: SourceView, pages: PageReader) -> Iterable[Lead]:
        """Yield leads for ``source``, reading pages only through ``pages``."""


class ConnectorRegistrationError(ValueError):
    """Raised when a connector class does not satisfy the contract."""


class UnknownConnectorError(KeyError):
    """Raised when a source names a connector that is not registered."""


_REGISTRY: dict[str, type[Connector]] = {}


def register_connector(cls: type[Connector]) -> type[Connector]:
    """Class decorator that validates and registers a connector under its ``key``."""
    if not (isinstance(cls, type) and issubclass(cls, Connector)):
        raise ConnectorRegistrationError(f"{cls!r} does not extend Connector.")
    key = getattr(cls, "key", None)
    if not isinstance(key, str) or not _CONNECTOR_KEY.match(key):
        raise ConnectorRegistrationError(f"{cls.__name__} needs a lower-case snake_case `key`.")
    if key in _REGISTRY and _REGISTRY[key] is not cls:
        raise ConnectorRegistrationError(f"A connector is already registered under {key!r}.")
    if not isinstance(getattr(cls, "discovery_method", None), DiscoveryMethod):
        raise ConnectorRegistrationError(f"{cls.__name__} must declare a DiscoveryMethod.")
    config_model = getattr(cls, "config_model", None)
    if not (isinstance(config_model, type) and issubclass(config_model, BaseModel)):
        raise ConnectorRegistrationError(f"{cls.__name__} must declare a Pydantic `config_model`.")
    if config_model.model_config.get("extra") != "forbid":
        raise ConnectorRegistrationError(
            f"{cls.__name__}.config_model must set extra='forbid' so unknown settings are rejected."
        )
    _REGISTRY[key] = cls
    return cls


def get_connector(key: str) -> type[Connector]:
    """Return the connector class registered under ``key``."""
    try:
        return _REGISTRY[key]
    except KeyError:
        raise UnknownConnectorError(key) from None


def registered_connectors() -> dict[str, type[Connector]]:
    """A copy of the registry (for listings and tests)."""
    return dict(_REGISTRY)


def unregister_connector(key: str) -> None:
    """Remove a registration (tests only)."""
    _REGISTRY.pop(key, None)


__all__ = [
    "Connector",
    "ConnectorRegistrationError",
    "Lead",
    "PageContent",
    "PageReader",
    "SourceView",
    "UnknownConnectorError",
    "get_connector",
    "register_connector",
    "registered_connectors",
    "unregister_connector",
]
