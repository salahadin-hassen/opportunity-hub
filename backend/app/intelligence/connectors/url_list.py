"""``url_list``: a curator-maintained list of exact opportunity page URLs (no page reads)."""
from __future__ import annotations

from collections.abc import Iterable

from pydantic import BaseModel, ConfigDict, Field

from app.intelligence.connectors.base import Connector, Lead, PageReader, SourceView, register_connector
from app.models.enums import DiscoveryMethod


class UrlListConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    urls: list[str] = Field(min_length=1, max_length=500)


@register_connector
class UrlListConnector(Connector):
    key = "url_list"
    discovery_method = DiscoveryMethod.URL_LIST
    config_model = UrlListConfig

    def discover(self, source: SourceView, pages: PageReader) -> Iterable[Lead]:
        for url in source.config.urls:  # type: ignore[attr-defined]
            yield Lead(url=url)
