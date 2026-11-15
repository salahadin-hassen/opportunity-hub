"""Safe XML parsing for connectors: documents with a DOCTYPE or entity declarations are refused.

Refusing DOCTYPE outright blocks entity-expansion ("billion laughs") and external-entity attacks
without a new dependency; sitemaps and feeds never need one.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET

_DANGEROUS = re.compile(rb"<!\s*(DOCTYPE|ENTITY)", re.IGNORECASE)


class UnsafeXMLError(ValueError):
    """The document declares a DOCTYPE or entities."""


def parse_xml(body: bytes) -> ET.Element:
    if _DANGEROUS.search(body[:200_000]):
        raise UnsafeXMLError("XML with DOCTYPE or ENTITY declarations is not accepted")
    return ET.fromstring(body)


def local_name(tag: str) -> str:
    """``{namespace}loc`` → ``loc``."""
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""
