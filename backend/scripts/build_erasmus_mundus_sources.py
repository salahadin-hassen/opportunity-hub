"""Build acquisition-source definitions for the Erasmus Mundus Joint Masters in the EU's official catalogue.

    python -m scripts.build_erasmus_mundus_sources OUT.json

Reads the European Education and Culture Executive Agency's Erasmus Mundus Catalogue
(https://www.eacea.ec.europa.eu/scholarships/erasmus-mundus-catalogue_en, all pages) through the
pipeline's own reader (robots.txt honoured, polite delay), and writes one ``html_index`` source per
programme website host. Each source discovers only pages on its own host whose URL suggests admission,
application, scholarship or eligibility information, plus the programme's home page.

The catalogue is the authority for *which* programmes exist and are EU-supported; every opportunity
that results is still extracted from, and quoted from, the programme's own official site, and reviewed.
Nothing about a programme is taken from this script's output other than where to look.
"""
from __future__ import annotations

import json
import re
import sys
from collections import OrderedDict
from datetime import datetime, timezone
from urllib.parse import urljoin, urlsplit

from app.intelligence.hosts import InvalidHostError, normalize_host
from app.intelligence.reader import SafePageReader
from app.intelligence.text import parse_html

CATALOGUE = "https://www.eacea.ec.europa.eu/scholarships/erasmus-mundus-catalogue_en"
PROJECT = re.compile(r"^https://erasmus-plus\.ec\.europa\.eu/projects/search/details/\d+$")
KEYWORDS = (r"admission|admissions|apply|application|applicants|scholarship|scholarships|funding|eligib|"
            r"requirement|how-to|call-for|candidat|entry|deadline|fees|selection")
MAX_PAGES = 30


def catalogue_entries() -> list[dict]:
    reader = SafePageReader(frozenset({"www.eacea.ec.europa.eu"}), min_delay_seconds=3.0)
    entries: list[dict] = []
    for page_no in range(MAX_PAGES):
        url = CATALOGUE if page_no == 0 else f"{CATALOGUE}?page={page_no}"
        page = parse_html(reader.read(url).body.decode("utf-8", errors="replace"))
        found = 0
        links = page.links
        for i, link in enumerate(links[:-1]):
            nxt = links[i + 1]
            href = link.href.strip()
            if PROJECT.match(nxt.href.strip()) and href.startswith("http") and "europa.eu" not in href:
                entries.append({"title": " ".join(link.text.split()), "website": href, "project": nxt.href.strip(),
                                "catalogue_page": url})
                found += 1
        print(f"catalogue page {page_no + 1}: {found} programmes", file=sys.stderr)
        if not any(l.href.strip() == f"?page={page_no + 1}" for l in links):
            break
    return entries


def definitions(entries: list[dict]) -> list[dict]:
    by_host: "OrderedDict[str, list[dict]]" = OrderedDict()
    for entry in entries:
        if entry["website"].startswith("http://"):
            # The pipeline reads https only. Most of these sites also serve https; the source test decides.
            entry["website"] = "https://" + entry["website"][len("http://"):]
            entry["upgraded"] = True
        parts = urlsplit(entry["website"])
        try:
            host = normalize_host(parts.hostname or "")
        except InvalidHostError:
            continue
        by_host.setdefault(host, []).append(entry)
    out = []
    for host, group in by_host.items():
        index_urls = list(dict.fromkeys(e["website"] for e in group))[:20]
        home_patterns = [rf"^{re.escape(u.rstrip('/'))}/?$" for u in index_urls]
        name = group[0]["title"] if len(group) == 1 else f"{host} (Erasmus Mundus programmes)"
        out.append({
            "name": f"Erasmus Mundus — {name}"[:255],
            "base_domain": host.removeprefix("www."),
            "allowed_hosts": [host],
            "category": "university",
            "authority_level": "official",
            "provider": {"name": (group[0]["title"] if len(group) == 1 else host)[:255], "aliases": []},
            "discovery_method": "html_index",
            "connector_key": "html_index",
            "connector_config": {
                "index_urls": index_urls,
                "link_patterns": [rf"^https://{re.escape(host)}/.*(?i:{KEYWORDS})"] + home_patterns,
            },
            "crawl_policy": {"discovery_interval_hours": 168, "max_pages_per_run": 10, "min_delay_seconds": 5.0},
            "_catalogue": [{"title": e["title"], "project": e["project"]} for e in group],
        })
    return out


def main() -> None:
    entries = catalogue_entries()
    defs = definitions(entries)
    skipped = [e for e in entries if not e["website"].startswith("https://")]  # after http→https: none expected
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": CATALOGUE,
        "programmes_listed": len(entries),
        "programmes_skipped_not_https": [e["website"] for e in skipped],
        "programmes_upgraded_to_https": sum(1 for e in entries if e.get("upgraded")),
        "sources": defs,
    }
    with open(sys.argv[1], "w") as fh:
        json.dump(payload, fh, indent=1, ensure_ascii=False)
    print(f"{len(entries)} programmes listed, {len(defs)} sources written, {len(skipped)} skipped (not https)",
          file=sys.stderr)


if __name__ == "__main__":
    main()
