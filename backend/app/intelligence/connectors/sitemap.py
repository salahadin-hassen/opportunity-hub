"""``sitemap``: XML sitemaps (and sitemap indexes, one level deep), filtered by URL patterns."""
from __future__ import annotations

import re
from collections.abc import Iterable

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.intelligence.connectors._xml import local_name, parse_xml
from app.intelligence.connectors.base import Connector, Lead, PageReader, SourceView, register_connector
from app.models.enums import DiscoveryMethod

MAX_CHILD_SITEMAPS = 10


class SitemapConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sitemap_urls: list[str] = Field(min_length=1, max_length=10)
    #: Regular expressions; a page URL is kept if it matches any. Empty keeps every URL.
    include_patterns: list[str] = Field(default_factory=list, max_length=20)
    exclude_patterns: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("include_patterns", "exclude_patterns")
    @classmethod
    def compile_patterns(cls, values: list[str]) -> list[str]:
        for value in values:
            re.compile(value)
        return values


def _wanted(url: str, config: SitemapConfig) -> bool:
    if config.exclude_patterns and any(re.search(pattern, url) for pattern in config.exclude_patterns):
        return False
    return not config.include_patterns or any(re.search(pattern, url) for pattern in config.include_patterns)


@register_connector
class SitemapConnector(Connector):
    key = "sitemap"
    discovery_method = DiscoveryMethod.SITEMAP
    config_model = SitemapConfig

    def discover(self, source: SourceView, pages: PageReader) -> Iterable[Lead]:
        config: SitemapConfig = source.config  # type: ignore[assignment]
        queue = list(config.sitemap_urls)
        children_read = 0
        while queue:
            root = parse_xml(pages.read(queue.pop(0)).body)
            kind = local_name(root.tag)
            for node in root:
                loc = next((child.text for child in node if local_name(child.tag) == "loc" and child.text), None)
                if not loc:
                    continue
                loc = loc.strip()
                if kind == "sitemapindex":
                    if children_read < MAX_CHILD_SITEMAPS and _wanted_child(loc):
                        queue.append(loc)
                        children_read += 1
                elif _wanted(loc, config):
                    yield Lead(url=loc)


def _wanted_child(url: str) -> bool:
    return url.lower().endswith(".xml") or "sitemap" in url.lower()
