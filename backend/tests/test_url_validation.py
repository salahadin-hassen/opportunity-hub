"""HTTP URL validation for official opportunity and provenance sources."""
import pytest
from pydantic import ValidationError

from app.schemas import OpportunityCreate, SourceCreate


@pytest.mark.parametrize("url", ["http://example.org/opportunity", "https://example.org/opportunity"])
@pytest.mark.parametrize("schema", [OpportunityCreate, SourceCreate])
def test_official_urls_accept_http_and_https(schema, url):
    if schema is OpportunityCreate:
        result = schema(slug="valid-opportunity", title="Opportunity", official_url=url)
        assert result.model_dump()["official_url"].startswith(url)
    else:
        result = schema(url=url)
        assert result.model_dump()["url"].startswith(url)


@pytest.mark.parametrize("schema", [OpportunityCreate, SourceCreate])
def test_official_urls_require_a_hostname(schema):
    with pytest.raises(ValidationError):
        if schema is OpportunityCreate:
            schema(slug="valid-opportunity", title="Opportunity", official_url="https://")
        else:
            schema(url="https://")


@pytest.mark.parametrize("schema", [OpportunityCreate, SourceCreate])
def test_official_urls_reject_non_http_schemes(schema):
    with pytest.raises(ValidationError):
        if schema is OpportunityCreate:
            schema(slug="valid-opportunity", title="Opportunity", official_url="ftp://example.org/file")
        else:
            schema(url="ftp://example.org/file")
