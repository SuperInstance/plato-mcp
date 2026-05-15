# PLATO MCP

> PLATO rooms as MCP tools. Any MCP-compatible agent framework can use PLATO.

## What It Does

Exposes PLATO rooms as 6 MCP (Model Context Protocol) tools. Any framework that speaks MCP — LangGraph, OpenAI Agents SDK, Strands, n8n, Claude Code — can read rooms, write tiles, search knowledge, and route queries through our fleet.

Combined with Oracle1's repo decomposition pipeline, any GitHub repo can become PLATO rooms accessible to any MCP client.

## Tools

| Tool | What It Does |
|------|-------------|
| `list_rooms` | List all PLATO rooms (optional prefix filter) |
| `read_tiles` | Read tiles from a room (frozen computation steps) |
| `write_tile` | Write a tile to a room (submit work, findings, moves) |
| `query_health` | Fleet structural + behavioral health |
| `route_query` | Route to cheapest safe model via critical angles |
| `search_tiles` | Search tiles across rooms by keyword |

## Quick Start

```bash
pip install -e .
plato-mcp --port 8300
```

## Test

```bash
# List tools
curl http://localhost:8300/tools

# Query health
curl http://localhost:8300/health

# List rooms
curl -X POST http://localhost:8300/tools/list_rooms \
  -d '{"prefix": "forgemaster", "limit": 5}'

# Read tiles from a room
curl -X POST http://localhost:8300/tools/read_tiles \
  -d '{"room_id": "forge", "limit": 5}'

# Write a tile
curl -X POST http://localhost:8300/tools/write_tile \
  -d '{"room_id": "my-room", "domain": "test", "agent": "my-agent",
       "question": "Hello from MCP", "answer": "PLATO speaks MCP!"}'

# Route a query
curl -X POST http://localhost:8300/tools/route_query \
  -d '{"prompt": "What is the Eisenstein norm of 3+2ω?"}'
```

## Architecture

```
Any MCP Client (LangGraph, OpenAI SDK, Strands, Claude Code)
        │
        ▼
   PLATO MCP Server (:8300)
        │
        ├── list_rooms / read_tiles / write_tile ──→ PLATO Server (:8847)
        ├── route_query ──→ Fleet Router (:8100)
        └── query_health ──→ PLATO + Fleet Router
```

## Why MCP?

MCP is Anthropic's open standard for agent-to-tool communication. Every major framework supports it. By making PLATO an MCP server, we become a drop-in backend for the entire ecosystem. No custom protocol. No vendor lock-in. Just tools that work.
