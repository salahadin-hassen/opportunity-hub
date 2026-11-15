"""Response hardening headers set by the API itself (Cloudflare and Render add none of these)."""
from __future__ import annotations

from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from app.main import app


async def test_every_response_says_nosniff_and_production_pins_https(monkeypatch):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        dev = await client.get("/health")
        assert dev.headers["x-content-type-options"] == "nosniff"
        assert "strict-transport-security" not in dev.headers  # never on plain-http development
        monkeypatch.setattr(settings, "APP_ENV", "production")
        prod = await client.get("/health")
        assert prod.headers["strict-transport-security"] == "max-age=31536000; includeSubDomains"
        assert prod.headers["x-content-type-options"] == "nosniff"
