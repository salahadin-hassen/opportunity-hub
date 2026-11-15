"""``html_index``: listing pages whose links to opportunity pages match registry-configured patterns."""
from __future__ import annotations

import re
from collections.abc import Iterable
from urllib.parse import urljoin

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.intelligence.connectors.base import Connector, Lead, PageReader, SourceView, register_connector
from app.intelligence.text import parse_html
from app.models.enums import DiscoveryMethod


class HtmlIndexConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    index_urls: list[str] = Field(min_length=1, max_length=20)
    #: A link is a lead only if its absolute URL matches one of these. Required: no blind link-following.
    link_patterns: list[str] = Field(min_length=1, max_length=20)

    @field_validator("link_patterns")
    @classmethod
    def compile_patterns(cls, values: list[str]) -> list[str]:
        for value in values:
            re.compile(value)
        return values


@register_connector
class HtmlIndexConnector(Connector):
    key = "html_index"
    discovery_method = DiscoveryMethod.HTML_INDEX
    config_model = HtmlIndexConfig

    def discover(self, source: SourceView, pages: PageReader) -> Iterable[Lead]:
        config: HtmlIndexConfig = source.config  # type: ignore[assignment]
        for index_url in config.index_urls:
            page = pages.read(index_url)
            parsed = parse_html(page.body.decode("utf-8", errors="replace"))
            base = page.final_url or index_url
            for link in parsed.links:
                absolute = urljoin(base, link.href.strip())
                if any(re.search(pattern, absolute) for pattern in config.link_patterns):
                    yield Lead(url=absolute)
