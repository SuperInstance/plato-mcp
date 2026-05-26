"""Tests for plato-mcp."""

import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from plato_mcp.server import (
    app, MCP_TOOLS, TOOL_HANDLERS,
    tool_route_query, tool_query_health,
)
from plato_mcp import __version__


# ─── Import & Version ─────────────────────────────────────────────────────────

def test_version():
    assert __version__ == "0.1.0"


def test_app_exists():
    assert app is not None
    assert app.title == "PLATO MCP Server"


# ─── MCP Tool Definitions ─────────────────────────────────────────────────────

def test_mcp_tools_defined():
    expected = {"list_rooms", "read_tiles", "write_tile",
                "query_health", "route_query", "search_tiles",
                "conservation_check", "memory_remember",
                "memory_recall", "game_play"}
    assert set(MCP_TOOLS.keys()) == expected


def test_tool_schemas():
    for name, tool in MCP_TOOLS.items():
        assert "name" in tool
        assert tool["name"] == name
        assert "description" in tool
        assert "inputSchema" in tool
        assert tool["inputSchema"]["type"] == "object"


def test_tool_handlers_match():
    assert set(TOOL_HANDLERS.keys()) == set(MCP_TOOLS.keys())


# ─── Tool Implementations ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_route_query_arithmetic():
    result = await tool_route_query({"prompt": "compute 2+2"})
    assert "model" in result
    assert result["model"] == "seed-2.0-mini"


@pytest.mark.asyncio
async def test_route_query_reasoning():
    result = await tool_route_query({"prompt": "explain why this works"})
    assert "model" in result
    assert result["model"] == "gemini-flash-lite"


@pytest.mark.asyncio
async def test_route_query_design():
    result = await tool_route_query({"prompt": "design the architecture"})
    assert "model" in result


@pytest.mark.asyncio
async def test_query_health():
    result = await tool_query_health({})
    assert "status" in result
    assert "structural" in result
    assert "behavioral" in result
    assert "fleet_champion" in result["behavioral"]


# ─── FastAPI Endpoints ────────────────────────────────────────────────────────

from httpx import AsyncClient, ASGITransport


@pytest.mark.asyncio
async def test_root_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/")
    assert r.status_code == 200
    data = r.json()
    assert data["name"] == "PLATO MCP Server"
    assert "tools" in data


@pytest.mark.asyncio
async def test_tools_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/tools")
    assert r.status_code == 200
    data = r.json()
    assert "tools" in data
    assert len(data["tools"]) == 10


@pytest.mark.asyncio
async def test_health_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/health")
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_unknown_tool_returns_404():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post("/tools/nonexistent", json={})
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_route_tool_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post("/tools/route_query", json={"prompt": "what is 3+5?"})
    assert r.status_code == 200
    data = r.json()
    assert "result" in data
    assert data["result"]["model"] == "seed-2.0-mini"


# ─── Write Tile Validation ────────────────────────────────────────────────────

def test_write_tool_schema_required_fields():
    schema = MCP_TOOLS["write_tile"]["inputSchema"]
    required = schema.get("required", [])
    assert "room_id" in required
    assert "domain" in required
    assert "agent" in required
    assert "question" in required
    assert "answer" in required
