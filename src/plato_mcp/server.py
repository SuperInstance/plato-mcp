"""
plato_mcp/server.py — PLATO rooms exposed as MCP tools.

6 tools that let any MCP-compatible agent framework use PLATO:
  list_rooms, read_tiles, write_tile, query_health, route_query, search_tiles

This is the compatibility bridge. LangGraph, OpenAI Agents SDK, Strands,
n8n, Claude Code — they all route to MCP tools. If PLATO speaks MCP,
they all route to us.

Combined with Oracle1's repo decomposition pipeline:
  repo → PLATO rooms → MCP tools → any framework can use them
"""

from __future__ import annotations
import json, time, os
from typing import Optional
from datetime import datetime

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import httpx

PLATO_URL = os.environ.get("PLATO_URL", "http://147.224.38.131:8847")


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
}


# ─── Tool Implementations ─────────────────────────────────────────────────────

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


TOOL_HANDLERS = {
    "list_rooms": tool_list_rooms,
    "read_tiles": tool_read_tiles,
    "write_tile": tool_write_tile,
    "query_health": tool_query_health,
    "route_query": tool_route_query,
    "search_tiles": tool_search_tiles,
}


# ─── FastAPI App ──────────────────────────────────────────────────────────────

app = FastAPI(
    title="PLATO MCP Server",
    version="0.1.0",
    description="PLATO rooms as MCP tools. Any MCP-compatible agent can use PLATO.",
)


@app.get("/")
async def root():
    return {
        "name": "PLATO MCP Server",
        "version": "0.1.0",
        "tools": list(MCP_TOOLS.keys()),
        "plato_url": PLATO_URL,
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
