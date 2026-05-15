"""
plato_mcp/server.py — PLATO rooms exposed as MCP tools.

10 tools that let any MCP-compatible agent framework use PLATO:
  list_rooms, read_tiles, write_tile, query_health, route_query, search_tiles,
  conservation_check, memory_remember, memory_recall, game_play

This is the compatibility bridge. LangGraph, OpenAI Agents SDK, Strands,
n8n, Claude Code — they all route to MCP tools. If PLATO speaks MCP,
they all route to us.

Cross-pollinated from plato-ng: conservation law, memory module, game rooms.
"""

from __future__ import annotations
import importlib.util
import json
import math
import os
import sys
import time
from typing import Any, Optional
from datetime import datetime

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import httpx

PLATO_URL = os.environ.get("PLATO_URL", "http://147.224.38.131:8847")

# ─── plato-ng Integration Path ────────────────────────────────────────────────

_PLATO_NG_DIR = os.environ.get(
    "PLATO_NG_DIR",
    "/tmp/cross-pollinate/plato-ng",
)


def _load_module(module_name: str, file_path: str):
    """Load a Python module from a file path (plato-ng is not a proper package)."""
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    if spec is None:
        raise ImportError(f"Could not load {module_name} from {file_path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


# Lazy-load plato-ng modules on first usage
_conservation = None
_memory_module = None
_games_cache: dict[str, Any] = {}


def _get_conservation():
    global _conservation
    if _conservation is None:
        _conservation = _load_module(
            "plato_conservation",
            os.path.join(_PLATO_NG_DIR, "core", "conservation.py"),
        )
    return _conservation


def _get_memory():
    global _memory_module
    if _memory_module is None:
        _memory_module = _load_module(
            "plato_memory",
            os.path.join(_PLATO_NG_DIR, "services", "memory.py"),
        )
    return _memory_module


def _get_game(game_name: str):
    """Load and return a game module by name."""
    if game_name not in _games_cache:
        game_file = os.path.join(_PLATO_NG_DIR, "games", f"{game_name}_room.py")
        if not os.path.exists(game_file):
            raise ValueError(f"Unknown game: {game_name}. Available: tic_tac_toe, checkers, connect_four, othello")
        _games_cache[game_name] = _load_module(f"plato_game_{game_name}", game_file)
    return _games_cache[game_name]


# Module-level memory crystal singleton
_memory_crystal = None


def _get_crystal():
    global _memory_crystal
    if _memory_crystal is None:
        mem = _get_memory()
        _memory_crystal = mem.MemoryCrystal()
    return _memory_crystal


# ─── PLATO Client ─────────────────────────────────────────────────────────────

async def plato_get(path: str, timeout: float = 5.0) -> Optional[dict]:
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            r = await client.get(f"{PLATO_URL}{path}")
            if r.status_code == 200:
                return r.json()
        except:
            pass
    return None


async def plato_post(path: str, data: dict, timeout: float = 5.0) -> Optional[dict]:
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            r = await client.post(f"{PLATO_URL}{path}", json=data)
            if r.status_code == 200:
                return r.json()
        except:
            pass
    return None


# ─── MCP Tool Definitions ─────────────────────────────────────────────────────

MCP_TOOLS = {
    # ── Original 6 PLATO tools ──
    "list_rooms": {
        "name": "list_rooms",
        "description": "List all PLATO rooms. Rooms are execution contexts — they hold tiles (computation steps) and enforce protocols. Optional prefix filter (e.g. 'forgemaster', 'fleet', 'game').",
        "inputSchema": {"type": "object", "properties": {
            "prefix": {"type": "string", "description": "Filter by room ID prefix"},
            "limit": {"type": "integer", "description": "Max rooms (default 50)", "default": 50},
        }},
    },
    "read_tiles": {
        "name": "read_tiles",
        "description": "Read tiles from a PLATO room. Tiles are frozen computation steps — every agent action, every experiment result, every fleet decision is recorded as tiles.",
        "inputSchema": {"type": "object", "properties": {
            "room_id": {"type": "string", "description": "Room to read from"},
            "limit": {"type": "integer", "description": "Max tiles (default 10)", "default": 10},
            "tile_type": {"type": "string", "description": "Filter by tile type"},
        }, "required": ["room_id"]},
    },
    "write_tile": {
        "name": "write_tile",
        "description": "Write a tile to a PLATO room. This is how agents submit work, findings, game moves, experiment results, or any computation step.",
        "inputSchema": {"type": "object", "properties": {
            "room_id": {"type": "string", "description": "Room to write to"},
            "domain": {"type": "string", "description": "Knowledge domain"},
            "agent": {"type": "string", "description": "Your agent identifier"},
            "question": {"type": "string", "description": "The tile topic/question"},
            "answer": {"type": "string", "description": "The tile content/answer"},
            "tile_type": {"type": "string", "description": "Tile type", "default": "knowledge"},
        }, "required": ["room_id", "domain", "agent", "question", "answer"]},
    },
    "query_health": {
        "name": "query_health",
        "description": "Get fleet health — structural (spectral coupling from fleet-math) and behavioral (critical angles, accuracy from experiments).",
        "inputSchema": {"type": "object", "properties": {}},
    },
    "route_query": {
        "name": "route_query",
        "description": "Route a query to the cheapest AI model that won't break. Uses critical angle analysis from 6000+ empirical trials. Returns model, temperature, cost, and reasoning.",
        "inputSchema": {"type": "object", "properties": {
            "prompt": {"type": "string", "description": "Query to route"},
            "domain": {"type": "string", "description": "Domain hint: arithmetic, reasoning, code, design, analysis", "default": "auto"},
        }, "required": ["prompt"]},
    },
    "search_tiles": {
        "name": "search_tiles",
        "description": "Search PLATO tiles across rooms by keyword. Find experiment results, fleet decisions, agent communications, or any recorded knowledge.",
        "inputSchema": {"type": "object", "properties": {
            "query": {"type": "string", "description": "Search keyword"},
            "agent": {"type": "string", "description": "Filter by agent"},
            "limit": {"type": "integer", "description": "Max results (default 20)", "default": 20},
        }, "required": ["query"]},
    },

    # ── Cross-pollinated: Conservation Law ──
    "conservation_check": {
        "name": "conservation_check",
        "description": "Check if gamma+H obeys the PLATO conservation law: gamma + H = 1.283 - 0.159 * log(V) ± epsilon. Takes gamma (consistency), H (exploration), V (fleet size). Returns expected range and deviation. From core/conservation.py (R²=0.9602).",
        "inputSchema": {"type": "object", "properties": {
            "gamma": {"type": "number", "description": "Consistency parameter (gamma)"},
            "H": {"type": "number", "description": "Exploration parameter (H)"},
            "V": {"type": "integer", "description": "Fleet size (number of agents)"},
            "coupling_type": {"type": "string", "description": "Coupling type: 'style' (default), 'topology', or 'directed'", "default": "style"},
        }, "required": ["gamma", "H", "V"]},
    },

    # ── Cross-pollinated: Memory Module ──
    "memory_remember": {
        "name": "memory_remember",
        "description": "Crystallize content into the PLATO memory module. Creates a lossy, reconstructive MemoryTile with Ebbinghaus forgetting curve decay. Returns a memory ID for later recall.",
        "inputSchema": {"type": "object", "properties": {
            "content": {"type": "string", "description": "Content to remember and crystallize"},
            "valence": {"type": "number", "description": "Emotional salience (0.0-1.0, default 0.5). Higher = longer half-life", "default": 0.5},
        }, "required": ["content"]},
    },
    "memory_recall": {
        "name": "memory_recall",
        "description": "Recall a crystallized memory. Returns reconstruction with confidence based on Ebbinghaus decay retention and constraint count.",
        "inputSchema": {"type": "object", "properties": {
            "memory_id": {"type": "string", "description": "Memory ID returned by memory_remember"},
            "context": {"type": "string", "description": "Optional context to guide reconstruction when retention is low", "default": ""},
        }, "required": ["memory_id"]},
    },

    # ── Cross-pollinated: Game Rooms ──
    "game_play": {
        "name": "game_play",
        "description": "Play a move or full game in one of the PLATO game rooms. Supports tic_tac_toe, checkers, connect_four, and othello. Each game room has algorithmic strategies — no LLM per move. Returns game result, move log, and winner.",
        "inputSchema": {"type": "object", "properties": {
            "game_name": {"type": "string", "description": "Game to play: 'tic_tac_toe', 'checkers', 'connect_four', 'othello'"},
            "strategy1": {"type": "string", "description": "Strategy for first player. Options: tic_tac_toe: aggressive/defensive/random; checkers: aggressive/defensive; connect_four: aggressive/defensive; othello: positional/mobility", "default": "aggressive"},
            "strategy2": {"type": "string", "description": "Strategy for second player", "default": "defensive"},
            "move_count": {"type": "integer", "description": "Max moves to play (-1 = play to completion, default)", "default": -1},
        }, "required": ["game_name"]},
    },
}


# ─── Original Tool Implementations ────────────────────────────────────────────

async def tool_list_rooms(params: dict) -> list:
    data = await plato_get("/rooms")
    if not data:
        return [{"error": "PLATO server unavailable"}]
    rooms = data if isinstance(data, list) else data.get("rooms", [])
    prefix = params.get("prefix", "")
    limit = params.get("limit", 50)
    if prefix:
        rooms = [r for r in rooms if r.get("id", r.get("room_id", "")).startswith(prefix)]
    return [{"room_id": r.get("id", r.get("room_id", "")),
             "tile_count": r.get("tile_count", r.get("count", 0))}
            for r in rooms[:limit]]


async def tool_read_tiles(params: dict) -> list:
    room_id = params.get("room_id", "")
    limit = params.get("limit", 10)
    data = await plato_get(f"/room/{room_id}/history")
    if not data:
        return [{"error": f"Room '{room_id}' not found"}]
    tiles = data.get("tiles", data) if isinstance(data, dict) else data
    tile_type = params.get("tile_type")
    if tile_type:
        tiles = [t for t in tiles if t.get("tile_type") == tile_type]
    return [{"question": t.get("question", "")[:100],
             "answer": t.get("answer", "")[:200],
             "agent": t.get("agent", t.get("source", "")),
             "tile_type": t.get("tile_type", ""),
             "timestamp": t.get("timestamp", t.get("created_at", ""))}
            for t in tiles[:limit]]


async def tool_write_tile(params: dict) -> dict:
    payload = {k: params[k] for k in ("room_id", "domain", "agent", "question", "answer")
               if k in params}
    payload["tile_type"] = params.get("tile_type", "knowledge")
    result = await plato_post("/submit", payload)
    if result:
        return {"status": "submitted", "room_id": params["room_id"],
                "tile_hash": result.get("tile_hash", "")}
    return {"status": "error", "message": "PLATO server unavailable"}


async def tool_query_health(params: dict) -> dict:
    stats = await plato_get("/stats")
    structural = {"total_rooms": 0, "total_tiles": 0}
    if stats:
        structural = {
            "total_rooms": stats.get("total_rooms", 0),
            "total_tiles": stats.get("total_tiles", 0),
            "agents": stats.get("agents", []),
            "domains": stats.get("domains", []),
        }
    behavioral = {
        "fleet_champion": "seed-2.0-mini",
        "champion_accuracy": 0.895,
        "fast_champion": "gemini-flash-lite",
        "fast_accuracy": 0.825,
        "routing_savings": "84%",
        "findings_count": 25,
    }
    return {
        "status": "healthy" if structural["total_rooms"] > 0 else "degraded",
        "structural": structural,
        "behavioral": behavioral,
    }


async def tool_route_query(params: dict) -> dict:
    """Route using fleet-router if available, else local logic."""
    prompt = params.get("prompt", "")
    domain_hint = params.get("domain", "auto")

    # Try fleet-router service first
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.post("http://localhost:8100/v1/route",
                json={"prompt": prompt, "domain": domain_hint})
            if r.status_code == 200:
                return r.json()
    except:
        pass

    # Fallback: local routing
    prompt_lower = prompt.lower()
    if any(t in prompt_lower for t in ["compute", "calculate", "what is", "solve", "sum"]):
        model, temp, cost = "seed-2.0-mini", 0.0, 0.05
    elif any(t in prompt_lower for t in ["why", "explain", "analyze", "compare"]):
        model, temp, cost = "gemini-flash-lite", 0.0, 0.002
    elif any(t in prompt_lower for t in ["design", "architect", "plan"]):
        model, temp, cost = "seed-2.0-mini", 0.7, 0.05
    else:
        model, temp, cost = "seed-2.0-mini", 0.0, 0.05

    return {"model": model, "temperature": temp, "cost_per_1k": cost,
            "domain_detected": domain_hint}


async def tool_search_tiles(params: dict) -> list:
    query = params.get("query", "").lower()
    limit = params.get("limit", 20)
    agent = params.get("agent")
    data = await plato_get("/rooms")
    if not data:
        return [{"error": "PLATO unavailable"}]
    rooms = data if isinstance(data, list) else data.get("rooms", [])
    results = []
    for room in rooms[:30]:
        room_id = room.get("id", room.get("room_id", ""))
        rdata = await plato_get(f"/room/{room_id}/history")
        if not rdata:
            continue
        tiles = rdata.get("tiles", rdata) if isinstance(rdata, dict) else rdata
        for t in tiles:
            q = t.get("question", "").lower()
            a = t.get("answer", "").lower()
            if query in q or query in a:
                if agent and t.get("agent", t.get("source", "")) != agent:
                    continue
                results.append({
                    "room_id": room_id,
                    "question": t.get("question", "")[:100],
                    "answer": t.get("answer", "")[:200],
                    "agent": t.get("agent", t.get("source", "")),
                })
                if len(results) >= limit:
                    return results
    return results


# ─── Cross-pollinated: Conservation Law ──────────────────────────────────────

async def tool_conservation_check(params: dict) -> dict:
    """Check if gamma+H obeys the conservation law."""
    gamma = params.get("gamma", 0)
    H = params.get("H", 0)
    V = params.get("V", 2)
    coupling_type = params.get("coupling_type", "style")

    cons = _get_conservation()

    predicted = cons.predicted_sum(V, coupling_type)
    actual = gamma + H
    dev = cons.deviation(gamma, H, V, coupling_type)
    low, high = cons.expected_range(V, coupling_type)
    conserved = cons.is_conserved(gamma, H, V, coupling_type)

    return {
        "actual_sum": round(actual, 4),
        "predicted_sum": round(predicted, 4),
        "deviation": round(dev, 4),
        "expected_range": {
            "lower": round(low, 4),
            "upper": round(high, 4),
        },
        "is_conserved": conserved,
        "coupling_type": coupling_type,
        "fleet_size": V,
        "law": f"gamma + H = {cons.INTERCEPT} + ({cons.SLOPE}) * log(V)",
    }


# ─── Cross-pollinated: Memory Module ─────────────────────────────────────────

async def tool_memory_remember(params: dict) -> dict:
    """Crystallize content into the memory module. Returns memory ID."""
    content = params.get("content", "")
    valence = params.get("valence", 0.5)

    crystal = _get_crystal()
    mem_id = crystal.crystallize(content, valence)

    return {
        "memory_id": mem_id,
        "valence": valence,
        "constraints": list(_get_crystal().memories[mem_id].constraints.keys()),
        "half_life_seconds": _get_crystal().memories[mem_id].half_life,
        "status": "crystallized",
    }


async def tool_memory_recall(params: dict) -> dict:
    """Recall a memory. Returns reconstruction with confidence."""
    mem_id = params.get("memory_id", "")
    context = params.get("context", "")

    crystal = _get_crystal()
    result = crystal.recall(mem_id, context)

    if result["confidence"] == 0.0:
        return {"memory_id": mem_id, "status": result["reconstruction"]}

    return {
        "memory_id": mem_id,
        "reconstruction": result["reconstruction"],
        "confidence": result["confidence"],
        "retention": result["retention"],
        "status": "recalled",
    }


# ─── Cross-pollinated: Game Rooms ────────────────────────────────────────────

async def tool_game_play(params: dict) -> dict:
    """Play a game between two algorithmic strategies."""
    game_name = params.get("game_name", "").lower()
    strategy1 = params.get("strategy1", "aggressive")
    strategy2 = params.get("strategy2", "defensive")
    move_count = params.get("move_count", -1)

    valid_games = {"tic_tac_toe", "checkers", "connect_four", "othello"}
    if game_name not in valid_games:
        return {"error": f"Unknown game '{game_name}'. Valid: {', '.join(sorted(valid_games))}"}

    game_mod = _get_game(game_name)

    try:
        if game_name == "tic_tac_toe":
            result = game_mod.play_game(strategy1, strategy2, 1)
            return _format_ttt_result(result, move_count)

        elif game_name == "checkers":
            # checkers uses (strat_black, strat_red, game_id)
            result = game_mod.play_game(strategy1, strategy2, 1)
            return _format_checkers_result(result, move_count)

        elif game_name == "connect_four":
            room = game_mod.ConnectFourRoom()
            result = room.play_game(strategy1, strategy2, 1)
            return _format_c4_result(result, move_count)

        elif game_name == "othello":
            # othello uses (strat_b, strat_w, game_id)
            result = game_mod.play_game(strategy1, strategy2, 1)
            return _format_othello_result(result, move_count)

    except Exception as e:
        return {"error": f"Game error: {e}"}


def _format_ttt_result(result: dict, max_moves: int = -1) -> dict:
    """Format tic-tac-toe result."""
    moves = result.get("moves", [])
    if max_moves > 0:
        moves = moves[:max_moves]

    board_display = _ttt_board_from_moves(moves)

    return {
        "game": "tic_tac_toe",
        "result": result.get("result", "unknown"),
        "total_moves": len(result.get("moves", [])),
        "moves_returned": len(moves),
        "move_log": moves,
        "final_board": board_display,
        "game_id": result.get("id", 1),
    }


def _ttt_board_from_moves(moves: list) -> list:
    """Reconstruct final board from move log."""
    board = [" "] * 9
    for m in moves:
        if isinstance(m, dict):
            idx = m.get("move", m.get("to", m.get("col")))
            player = m.get("player", m.get("p"))
            if isinstance(idx, int) and player:
                board[idx] = player
    return [[" " if b == " " else b for b in board[i:i+3]] for i in range(0, 9, 3)]


def _format_checkers_result(result: dict, max_moves: int = -1) -> dict:
    """Format checkers result."""
    moves = result.get("moves", [])
    if max_moves > 0:
        moves = moves[:max_moves]

    return {
        "game": "checkers",
        "result": result.get("result", "unknown"),
        "reason": result.get("reason", ""),
        "total_moves": len(result.get("moves", [])),
        "moves_returned": len(moves),
        "move_log": moves,
        "pieces_remaining": result.get("pieces", {}),
        "game_id": result.get("id", 1),
    }


def _format_c4_result(result: dict, max_moves: int = -1) -> dict:
    """Format connect-four result."""
    moves = result.get("moves", [])
    if max_moves > 0:
        moves = moves[:max_moves]

    return {
        "game": "connect_four",
        "result": result.get("result", "unknown"),
        "total_moves": len(result.get("moves", [])),
        "moves_returned": len(moves),
        "move_log": moves,
        "game_id": result.get("id", 1),
    }


def _format_othello_result(result: dict, max_moves: int = -1) -> dict:
    """Format othello result."""
    moves = result.get("moves", [])
    if max_moves > 0:
        moves = moves[:max_moves]

    return {
        "game": "othello",
        "result": result.get("result", "unknown"),
        "total_moves": len(result.get("moves", [])),
        "moves_returned": len(moves),
        "move_log": moves,
        "game_id": result.get("id", 1),
    }


# ─── Tool Handler Registry ────────────────────────────────────────────────────

TOOL_HANDLERS = {
    "list_rooms": tool_list_rooms,
    "read_tiles": tool_read_tiles,
    "write_tile": tool_write_tile,
    "query_health": tool_query_health,
    "route_query": tool_route_query,
    "search_tiles": tool_search_tiles,
    "conservation_check": tool_conservation_check,
    "memory_remember": tool_memory_remember,
    "memory_recall": tool_memory_recall,
    "game_play": tool_game_play,
}


# ─── FastAPI App ──────────────────────────────────────────────────────────────

app = FastAPI(
    title="PLATO MCP Server",
    version="0.2.0",
    description="PLATO rooms as MCP tools. Any MCP-compatible agent can use PLATO. Cross-pollinated from plato-ng: conservation law, memory module, and game rooms.",
)


@app.get("/")
async def root():
    return {
        "name": "PLATO MCP Server",
        "version": "0.2.0",
        "tools": list(MCP_TOOLS.keys()),
        "plato_url": PLATO_URL,
        "cross_pollinated_from": [
            "core/conservation.py",
            "services/memory.py",
            "games/tic_tac_toe_room.py",
            "games/checkers_room.py",
            "games/connect_four_room.py",
            "games/othello_room.py",
        ],
    }


@app.get("/tools")
async def list_tools():
    return {"tools": list(MCP_TOOLS.values())}


@app.post("/tools/{tool_name}")
async def call_tool(tool_name: str, request: Request):
    if tool_name not in TOOL_HANDLERS:
        return JSONResponse({"error": f"Unknown tool: {tool_name}"}, status_code=404)
    params = await request.json()
    result = await TOOL_HANDLERS[tool_name](params)
    return {"tool": tool_name, "result": result,
            "timestamp": datetime.utcnow().isoformat() + "Z"}


@app.get("/health")
async def health():
    return await tool_query_health({})
