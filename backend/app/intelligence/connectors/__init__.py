"""Discovery connectors.

Each concrete connector lives in its own module here and registers itself
with ``@register_connector``. No concrete connectors exist yet; the first
ones (sitemap, feed, HTML index, URL list) arrive with M2-T10.
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
