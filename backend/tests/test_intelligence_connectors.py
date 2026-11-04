"""The connector contract and the approved-source policy around it (no network)."""
from __future__ import annotations

import ast
import uuid
from collections.abc import Iterable
from pathlib import Path

import pytest
from pydantic import BaseModel, ConfigDict

import app.intelligence.connectors as connectors_package
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
    unregister_connector,
)
from app.intelligence.definitions import CrawlPolicy
from app.intelligence.discovery import (
    OutOfScopeURLError,
    PageBudgetExceededError,
    check_in_scope,
    collect_leads,
)
from app.models.enums import DiscoveryMethod

HOSTS = frozenset({"careers.cern", "home.cern"})


class ListConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    urls: list[str] = []
    index_urls: list[str] = []


class ScriptedConnector(Connector):
    """Yields whatever the test configures; reads index pages through the reader."""

    key = "scripted_test"
    discovery_method = DiscoveryMethod.URL_LIST
    config_model = ListConfig

    def discover(self, source: SourceView, pages: PageReader) -> Iterable[Lead]:
        for url in source.config.index_urls:
            pages.read(url)
        for url in source.config.urls:
            yield Lead(url=url)


class RecordingReader:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def read(self, url: str) -> PageContent:
        self.calls.append(url)
        return PageContent(url=url, final_url=url, status_code=200, content_type="text/html", body=b"")


def make_view(*, urls=(), index_urls=(), max_pages=50, method=DiscoveryMethod.URL_LIST) -> SourceView:
    return SourceView(
        id=uuid.uuid4(),
        name="CERN careers",
        base_domain="cern",
        allowed_hosts=HOSTS,
        discovery_method=method,
        crawl_policy=CrawlPolicy(max_pages_per_run=max_pages),
        config=ListConfig(urls=list(urls), index_urls=list(index_urls)),
    )


# --- Registration --------------------------------------------------------------------------------


@pytest.fixture
def registered():
    register_connector(ScriptedConnector)
    yield ScriptedConnector
    unregister_connector(ScriptedConnector.key)


def test_registered_connector_is_found(registered):
    assert get_connector("scripted_test") is ScriptedConnector


def test_unknown_connector_raises():
    with pytest.raises(UnknownConnectorError):
        get_connector("no_such_connector")


def test_registering_the_same_class_twice_is_idempotent(registered):
    assert register_connector(ScriptedConnector) is ScriptedConnector


def test_a_second_class_cannot_take_an_existing_key(registered):
    class Impostor(ScriptedConnector):
        pass

    with pytest.raises(ConnectorRegistrationError):
        register_connector(Impostor)


def _connector(**attrs) -> type:
    def discover(self, source, pages):  # pragma: no cover - never called
        return []

    namespace = {"key": "x_test", "discovery_method": DiscoveryMethod.SITEMAP, "config_model": ListConfig}
    namespace.update(attrs)
    namespace["discover"] = discover
    return type("Candidate", (Connector,), namespace)


class LooseConfig(BaseModel):
    urls: list[str] = []


@pytest.mark.parametrize(
    "attrs",
    [
        {"key": "Bad-Key"},
        {"key": ""},
        {"discovery_method": "sitemap"},
        {"config_model": dict},
        {"config_model": LooseConfig},
    ],
)
def test_invalid_connectors_are_refused(attrs):
    with pytest.raises(ConnectorRegistrationError):
        register_connector(_connector(**attrs))


def test_non_connector_classes_are_refused():
    with pytest.raises(ConnectorRegistrationError):
        register_connector(object)  # type: ignore[arg-type]


# --- Scope checks --------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://careers.cern/programmes/", "https://careers.cern/programmes/"),
        ("https://CAREERS.cern/a?b=1#frag", "https://careers.cern/a?b=1"),
        ("https://careers.cern:443/x", "https://careers.cern/x"),
        ("https://home.cern", "https://home.cern/"),
    ],
)
def test_in_scope_urls_are_accepted(url, expected):
    assert check_in_scope(url, HOSTS) == expected


@pytest.mark.parametrize(
    "url",
    [
        "http://careers.cern/",
        "ftp://careers.cern/",
        "file:///etc/passwd",
        "https://evil.org/",
        "https://careers.cern.evil.org/",
        "https://sub.careers.cern/",  # subdomains are not implied: hosts are exact
        "https://user@careers.cern/",
        "https://careers.cern\\@evil.org/",
        "https://careers.cern:8443/",
        "https://127.0.0.1/",
        "https://[::1]/",
        "https://careers.cern/a b",
        "https://careers.cern/\n",
        "",
        "https://careers.cern/" + "a" * 2000,
        "//careers.cern/",
    ],
)
def test_out_of_scope_urls_are_refused(url):
    with pytest.raises(OutOfScopeURLError):
        check_in_scope(url, HOSTS)


# --- collect_leads -------------------------------------------------------------------------------


def test_leads_off_the_allow_list_are_rejected_with_a_reason(registered):
    view = make_view(urls=["https://careers.cern/a", "https://evil.org/b", "http://careers.cern/c"])
    result = collect_leads(ScriptedConnector(), view, RecordingReader())
    assert [lead.url for lead in result.accepted] == ["https://careers.cern/a"]
    assert [item.url for item in result.rejected] == ["https://evil.org/b", "http://careers.cern/c"]
    assert all(item.reason for item in result.rejected)


def test_duplicate_leads_are_collapsed(registered):
    view = make_view(urls=["https://careers.cern/a", "https://careers.cern/a#x", "https://CAREERS.cern/a"])
    result = collect_leads(ScriptedConnector(), view, RecordingReader())
    assert [lead.url for lead in result.accepted] == ["https://careers.cern/a"]
    assert result.rejected == []


def test_leads_beyond_the_budget_are_rejected(registered):
    view = make_view(urls=[f"https://careers.cern/{i}" for i in range(5)], max_pages=3)
    result = collect_leads(ScriptedConnector(), view, RecordingReader())
    assert len(result.accepted) == 3
    assert len(result.rejected) == 2
    assert all("budget" in item.reason for item in result.rejected)


def test_the_reader_refuses_hosts_outside_the_source_before_any_read(registered):
    reader = RecordingReader()
    view = make_view(index_urls=["https://careers.cern/index", "https://evil.org/index"])
    with pytest.raises(OutOfScopeURLError):
        collect_leads(ScriptedConnector(), view, reader)
    assert reader.calls == ["https://careers.cern/index"]


def test_the_reader_stops_at_the_page_budget(registered):
    reader = RecordingReader()
    view = make_view(index_urls=[f"https://careers.cern/{i}" for i in range(3)], max_pages=2)
    with pytest.raises(PageBudgetExceededError):
        collect_leads(ScriptedConnector(), view, reader)
    assert len(reader.calls) == 2


def test_pages_read_are_counted(registered):
    view = make_view(index_urls=["https://careers.cern/i1", "https://home.cern/i2"], urls=["https://careers.cern/a"])
    result = collect_leads(ScriptedConnector(), view, RecordingReader())
    assert result.pages_read == 2


def test_non_lead_values_are_rejected(registered):
    class Sloppy(ScriptedConnector):
        def discover(self, source, pages):
            yield "https://careers.cern/a"
            yield Lead(url="https://careers.cern/b")

    result = collect_leads(Sloppy(), make_view(), RecordingReader())
    assert [lead.url for lead in result.accepted] == ["https://careers.cern/b"]
    assert len(result.rejected) == 1


def test_connector_and_source_must_share_a_discovery_method(registered):
    with pytest.raises(ValueError):
        collect_leads(ScriptedConnector(), make_view(method=DiscoveryMethod.SITEMAP), RecordingReader())


def test_source_view_is_immutable():
    view = make_view()
    with pytest.raises(AttributeError):
        view.allowed_hosts = frozenset({"evil.org"})  # type: ignore[misc]


# --- Architecture guard ----------------------------------------------------------------------------

FORBIDDEN_MODULES = {
    "socket",
    "ssl",
    "http.client",
    "urllib.request",
    "urllib3",
    "httpx",
    "requests",
    "aiohttp",
    "subprocess",
    "sqlalchemy",
    "app.db",
}


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_connector_modules_do_not_import_networking_or_database_code():
    package_dir = Path(connectors_package.__file__).parent
    offenders = {}
    for path in sorted(package_dir.glob("*.py")):
        bad = {
            name
            for name in _imports(path)
            if any(name == forbidden or name.startswith(forbidden + ".") for forbidden in FORBIDDEN_MODULES)
        }
        if bad:
            offenders[path.name] = sorted(bad)
    assert offenders == {}, f"Connectors must read pages only through PageReader: {offenders}"
