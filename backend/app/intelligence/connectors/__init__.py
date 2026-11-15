"""Discovery connectors.

Each concrete connector lives in its own module here and registers itself
with ``@register_connector``. Importing this package registers the concrete
connectors: ``url_list``, ``sitemap``, ``feed`` (RSS/Atom) and ``html_index``.
"""
from app.intelligence.connectors.base import (
    Connector,
    ConnectorRegistrationError,
    Lead,
    PageContent,
    PageReader,
    SourceView,
    UnknownConnectorError,
    get_connector,
    register_connector,
    registered_connectors,
)
from app.intelligence.connectors import feed, html_index, sitemap, url_list  # noqa: E402,F401  (registration)

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
]
