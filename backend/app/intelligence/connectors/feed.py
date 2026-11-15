"""``feed``: RSS 2.0 and Atom feeds; each item's link is a lead (its GUID/id kept as the external id)."""
from __future__ import annotations

import re
from collections.abc import Iterable

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.intelligence.connectors._xml import local_name, parse_xml
from app.intelligence.connectors.base import Connector, Lead, PageReader, SourceView, register_connector
from app.models.enums import DiscoveryMethod


class FeedConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    feed_urls: list[str] = Field(min_length=1, max_length=10)
    #: Keep an item only if its title or link matches one of these (case-insensitive). Empty keeps all.
    include_patterns: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("include_patterns")
    @classmethod
    def compile_patterns(cls, values: list[str]) -> list[str]:
        for value in values:
            re.compile(value)
        return values


def _child_text(node, name: str) -> str | None:
    for child in node:
        if local_name(child.tag) == name and child.text:
            return child.text.strip()
    return None


@register_connector
class FeedConnector(Connector):
    key = "feed"
    discovery_method = DiscoveryMethod.FEED
    config_model = FeedConfig

    def discover(self, source: SourceView, pages: PageReader) -> Iterable[Lead]:
        config: FeedConfig = source.config  # type: ignore[assignment]
        for feed_url in config.feed_urls:
            root = parse_xml(pages.read(feed_url).body)
            for item in root.iter():
                name = local_name(item.tag)
                if name == "item":  # RSS
                    link = _child_text(item, "link")
                    external_id = _child_text(item, "guid")
                elif name == "entry":  # Atom
                    link = next(
                        (child.get("href") for child in item
                         if local_name(child.tag) == "link" and child.get("rel", "alternate") == "alternate"),
                        None,
                    )
                    external_id = _child_text(item, "id")
                else:
                    continue
                if not link:
                    continue
                title = _child_text(item, "title") or ""
                if config.include_patterns and not any(
                    re.search(pattern, f"{title} {link}", re.IGNORECASE) for pattern in config.include_patterns
                ):
                    continue
                yield Lead(url=link.strip(), external_id=(external_id or None) and external_id[:255])
