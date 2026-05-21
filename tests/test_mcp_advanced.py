"""Advanced tests for plato-mcp — MCP protocol handling, routing, error cases, format helpers."""

import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from plato_mcp.server import (
    app, MCP_TOOLS, TOOL_HANDLERS,
    tool_route_query, tool_query_health,
    _ttt_board_from_moves, _format_ttt_result, _format_checkers_result,
    _format_c4_result, _format_othello_result,
    PLATO_URL,
)
from httpx import AsyncClient, ASGITransport


# ─── MCP Tool Schema Validation ───────────────────────────────────────────────

def test_all_tools_have_descriptions():
    """Every tool must have a non-empty description."""
    for name, tool in MCP_TOOLS.items():
        assert len(tool.get("description", "")) > 20, f"{name} has short/missing description"


def test_all_tool_schemas_are_valid_json_schema():
    """Every inputSchema must have type=object."""
    for name, tool in MCP_TOOLS.items():
        schema = tool["inputSchema"]
        assert schema["type"] == "object"
        assert "properties" in schema


def test_write_tile_all_params_typed():
    """Write tile schema has proper types."""
    props = MCP_TOOLS["write_tile"]["inputSchema"]["properties"]
    assert props["room_id"]["type"] == "string"
    assert props["domain"]["type"] == "string"
    assert props["agent"]["type"] == "string"
    assert props["question"]["type"] == "string"
    assert props["answer"]["type"] == "string"


def test_read_tiles_required_room_id():
    """Read tiles requires room_id."""
    schema = MCP_TOOLS["read_tiles"]["inputSchema"]
    assert "room_id" in schema.get("required", [])


def test_search_tiles_requires_query():
    """Search tiles requires query."""
    schema = MCP_TOOLS["search_tiles"]["inputSchema"]
    assert "query" in schema.get("required", [])


def test_route_query_schema():
    """Route query requires prompt."""
    schema = MCP_TOOLS["route_query"]["inputSchema"]
    assert "prompt" in schema.get("required", [])


def test_conservation_check_schema():
    """Conservation check requires gamma, H, V."""
    schema = MCP_TOOLS["conservation_check"]["inputSchema"]
    required = schema.get("required", [])
    assert "gamma" in required
    assert "H" in required
    assert "V" in required


def test_game_play_schema():
    """Game play requires game_name."""
    schema = MCP_TOOLS["game_play"]["inputSchema"]
    assert "game_name" in schema.get("required", [])
    assert "strategy1" in schema["properties"]
    assert "strategy2" in schema["properties"]


def test_memory_remember_schema():
    """Memory remember requires content."""
    schema = MCP_TOOLS["memory_remember"]["inputSchema"]
    assert "content" in schema.get("required", [])
    assert "valence" in schema["properties"]


def test_memory_recall_schema():
    """Memory recall requires memory_id."""
    schema = MCP_TOOLS["memory_recall"]["inputSchema"]
    assert "memory_id" in schema.get("required", [])


# ─── Route Query Logic ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_route_query_arithmetic_keywords():
    """Arithmetic keywords route to seed-2.0-mini."""
    for prompt in ["compute 2+2", "calculate 10*5", "what is the answer", "solve x=1", "sum of 3 and 5"]:
        result = await tool_route_query({"prompt": prompt})
        assert result["model"] == "seed-2.0-mini", f"Failed for: {prompt}"


@pytest.mark.asyncio
async def test_route_query_reasoning_keywords():
    """Reasoning keywords route to gemini-flash-lite."""
    for prompt in ["why is the sky blue", "explain quantum mechanics", "analyze this data", "compare A and B"]:
        result = await tool_route_query({"prompt": prompt})
        assert result["model"] == "gemini-flash-lite", f"Failed for: {prompt}"


@pytest.mark.asyncio
async def test_route_query_design_keywords():
    """Design keywords route with higher temperature."""
    result = await tool_route_query({"prompt": "design the new system"})
    assert result["temperature"] == 0.7


@pytest.mark.asyncio
async def test_route_query_default_fallback():
    """Unknown prompts get default routing."""
    result = await tool_route_query({"prompt": "random text here"})
    assert "model" in result
    assert "temperature" in result
    assert "cost_per_1k" in result


@pytest.mark.asyncio
async def test_route_query_domain_hint():
    """Domain hint is returned."""
    result = await tool_route_query({"prompt": "test", "domain": "code"})
    assert result["domain_detected"] == "code"


# ─── Health Check ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_health_structure():
    """Health check returns expected structure."""
    result = await tool_query_health({})
    assert "status" in result
    assert result["status"] in ("healthy", "degraded")
    assert "structural" in result
    assert "behavioral" in result
    behavioral = result["behavioral"]
    assert "fleet_champion" in behavioral
    assert "champion_accuracy" in behavioral
    assert isinstance(behavioral["champion_accuracy"], float)


# ─── Format Helpers ───────────────────────────────────────────────────────────

def test_ttt_board_from_moves_empty():
    """Empty moves → empty board."""
    board = _ttt_board_from_moves([])
    assert len(board) == 3
    assert all(cell == " " for row in board for cell in row)


def test_ttt_board_from_moves_with_moves():
    """Reconstruct board from move dicts."""
    moves = [
        {"move": 0, "player": "X"},
        {"move": 4, "player": "O"},
        {"move": 8, "player": "X"},
    ]
    board = _ttt_board_from_moves(moves)
    assert board[0][0] == "X"
    assert board[1][1] == "O"
    assert board[2][2] == "X"


def test_ttt_board_from_moves_alt_keys():
    """Moves with 'to' and 'p' keys."""
    moves = [{"to": 0, "p": "X"}, {"col": 4, "player": "O"}]
    board = _ttt_board_from_moves(moves)
    assert board[0][0] == "X"


def test_format_ttt_result_empty():
    """Format result with no moves."""
    result = _format_ttt_result({"result": "draw", "moves": [], "id": 1})
    assert result["game"] == "tic_tac_toe"
    assert result["total_moves"] == 0
    assert result["moves_returned"] == 0


def test_format_ttt_result_with_move_limit():
    """Move count limiting."""
    moves = [{"move": i, "player": "X"} for i in range(5)]
    result = _format_ttt_result({"result": "win", "moves": moves, "id": 1}, max_moves=3)
    assert result["moves_returned"] == 3
    assert result["total_moves"] == 5


def test_format_checkers_result():
    """Checkers result formatting."""
    result = _format_checkers_result({
        "result": "black_wins", "reason": "no red pieces",
        "moves": [{"from": 0, "to": 1}], "pieces": {"black": 3, "red": 0}, "id": 5,
    })
    assert result["game"] == "checkers"
    assert result["reason"] == "no red pieces"
    assert result["pieces_remaining"]["black"] == 3


def test_format_c4_result():
    """Connect four result formatting."""
    result = _format_c4_result({
        "result": "p1_wins", "moves": [{"col": 0}], "id": 2,
    })
    assert result["game"] == "connect_four"
    assert result["result"] == "p1_wins"


def test_format_othello_result():
    """Othello result formatting."""
    result = _format_othello_result({
        "result": "black_wins", "moves": [], "id": 3,
    })
    assert result["game"] == "othello"


# ─── FastAPI Endpoint Tests ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_root_endpoint_fields():
    """Root endpoint has all expected fields."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/")
    data = r.json()
    assert "version" in data
    assert "plato_url" in data
    assert "cross_pollinated_from" in data
    assert isinstance(data["cross_pollinated_from"], list)


@pytest.mark.asyncio
async def test_health_endpoint_structure():
    """Health endpoint returns valid structure."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/health")
    data = r.json()
    assert "status" in data


@pytest.mark.asyncio
async def test_call_route_via_endpoint():
    """Route query via HTTP endpoint."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post("/tools/route_query", json={"prompt": "calculate 5*3"})
    assert r.status_code == 200
    data = r.json()
    assert "timestamp" in data
    assert "tool" in data
    assert data["tool"] == "route_query"


@pytest.mark.asyncio
async def test_call_tool_returns_timestamp():
    """Every tool response includes timestamp."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post("/tools/route_query", json={"prompt": "test"})
    assert "timestamp" in r.json()


# ─── PLATO URL Config ─────────────────────────────────────────────────────────

def test_plato_url_default():
    """Default PLATO URL."""
    assert PLATO_URL == "http://147.224.38.131:8847"
