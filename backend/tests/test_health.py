"""Basic smoke tests for the health endpoints."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_root_responds():
    """`GET /` returns the app identity payload."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.get("/")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "running"
    assert "version" in data
    assert data["websocket_endpoint"] == "/ws/session"


@pytest.mark.asyncio
async def test_health_endpoint():
    """`GET /health` returns connection and AI status."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "healthy"
    assert "ai_ready" in data
    assert "connections" in data
