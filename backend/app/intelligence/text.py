"""HTML → normalised visible text plus the metadata extraction needs (standard library only).

The text produced here is what every evidence quote must be a substring of, so it is built once,
deterministically: scripts, styles and other non-content elements are dropped; block elements end a
line; whitespace is folded; Unicode is NFKC-normalised. Fetched HTML is never rendered or served.
"""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Any

#: Elements whose content is never visible text.
_SKIP = {"script", "style", "noscript", "template", "svg", "iframe", "object", "canvas"}
#: Elements that start a new line.
_BLOCK = {
    "address", "article", "aside", "blockquote", "br", "dd", "details", "div", "dl", "dt", "fieldset",
    "figcaption", "figure", "footer", "form", "h1", "h2", "h3", "h4", "h5", "h6", "header", "hr", "li",
    "main", "nav", "ol", "p", "pre", "section", "summary", "table", "tbody", "td", "tfoot", "th", "thead",
    "tr", "ul",
}
_HEADINGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
_VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
MAX_TEXT_CHARS = 300_000
MAX_LINKS = 2000


def normalise_text(value: str) -> str:
    """NFKC, non-breaking spaces to spaces, whitespace folded within lines, blank lines dropped."""
    value = unicodedata.normalize("NFKC", value).replace("­", "")
    lines = (" ".join(line.split()) for line in value.splitlines())
    return "\n".join(line for line in lines if line)


@dataclass
class Link:
    href: str
    text: str


@dataclass
class ParsedPage:
    """Visible text and the structured hints the extractor may use."""

    text: str
    title: str | None = None
    meta: dict[str, str] = field(default_factory=dict)
    canonical: str | None = None
    headings: list[tuple[int, str]] = field(default_factory=list)
    links: list[Link] = field(default_factory=list)
    json_ld: list[dict[str, Any]] = field(default_factory=list)


class _Parser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip_depth = 0
        self.in_title = False
        self.title_parts: list[str] = []
        self.meta: dict[str, str] = {}
        self.canonical: str | None = None
        self.heading: tuple[int, list[str]] | None = None
        self.headings: list[tuple[int, str]] = []
        self.link: tuple[str, list[str]] | None = None
        self.links: list[Link] = []
        self.in_json_ld = False
        self.json_ld_parts: list[str] = []
        self.json_ld: list[dict[str, Any]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {name.lower(): (value or "") for name, value in attrs}
        if tag == "title":
            self.in_title = True
        elif tag == "meta":
            key = (attributes.get("property") or attributes.get("name") or "").strip().lower()
            if key and "content" in attributes and key not in self.meta:
                self.meta[key] = " ".join(attributes["content"].split())[:2000]
        elif tag == "link" and "canonical" in attributes.get("rel", "").lower().split():
            self.canonical = attributes.get("href") or None
        elif tag == "script" and attributes.get("type", "").lower() == "application/ld+json":
            self.in_json_ld = True
            self.json_ld_parts = []
        if tag in _SKIP and tag not in _VOID:
            self.skip_depth += 1
            return
        if self.skip_depth:
            return
        if tag in _BLOCK:
            self.parts.append("\n")
        if tag in _HEADINGS:
            self.heading = (int(tag[1]), [])
        elif tag == "a" and attributes.get("href") and len(self.links) < MAX_LINKS:
            self.link = (attributes["href"], [])

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self.in_title = False
        if tag == "script" and self.in_json_ld:
            self.in_json_ld = False
            self._keep_json_ld("".join(self.json_ld_parts))
        if tag in _SKIP and tag not in _VOID:
            self.skip_depth = max(0, self.skip_depth - 1)
            return
        if self.skip_depth:
            return
        if tag in _HEADINGS and self.heading is not None:
            level, parts = self.heading
            text = " ".join("".join(parts).split())
            if text:
                self.headings.append((level, text))
            self.heading = None
        elif tag == "a" and self.link is not None:
            href, parts = self.link
            self.links.append(Link(href=href, text=" ".join("".join(parts).split())))
            self.link = None
        if tag in _BLOCK:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self.in_title:
            self.title_parts.append(data)
            return
        if self.in_json_ld:
            self.json_ld_parts.append(data)
            return
        if self.skip_depth:
            return
        self.parts.append(data)
        if self.heading is not None:
            self.heading[1].append(data)
        if self.link is not None:
            self.link[1].append(data)

    def _keep_json_ld(self, raw: str) -> None:
        try:
            data = json.loads(raw)
        except (ValueError, RecursionError):
            return
        items = data if isinstance(data, list) else [data]
        for item in items:
            if isinstance(item, dict):
                graph = item.get("@graph")
                if isinstance(graph, list):
                    self.json_ld.extend(node for node in graph if isinstance(node, dict))
                else:
                    self.json_ld.append(item)


def parse_html(html: str) -> ParsedPage:
    """Parse ``html`` leniently; malformed markup never raises."""
    parser = _Parser()
    try:
        parser.feed(html)
        parser.close()
    except Exception:  # noqa: BLE001 - html.parser is lenient; anything else keeps what was parsed
        pass
    text = normalise_text("".join(parser.parts))[:MAX_TEXT_CHARS]
    title = " ".join("".join(parser.title_parts).split()) or None
    return ParsedPage(
        text=text,
        title=title,
        meta=parser.meta,
        canonical=parser.canonical,
        headings=[(level, unicodedata.normalize("NFKC", heading)) for level, heading in parser.headings],
        links=parser.links,
        json_ld=parser.json_ld[:20],
    )


def text_lines(text: str) -> list[str]:
    return [line for line in text.split("\n") if line]


_SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"“(])")


def sentences(line: str) -> list[str]:
    """Split one line into sentences (conservatively; never loses characters other than the gap)."""
    return [part for part in _SENTENCE_END.split(line) if part]


__all__ = ["Link", "ParsedPage", "normalise_text", "parse_html", "sentences", "text_lines"]
