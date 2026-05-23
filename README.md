# plato-mcp

PLATO rooms as MCP (Model Context Protocol) tools. Any MCP-compatible agent framework can use PLATO without custom integrations.

## Install

```bash
pip install plato-mcp
```

## Quick Start

```bash
plato-mcp --port 8300
```

That's it. You now have an MCP server exposing PLATO rooms as tools.

```bash
# List all rooms
curl -X POST http://localhost:8300/tools/list_rooms \
  -d '{"prefix": "forgemaster", "limit": 5}'

# Read tiles from a room
curl -X POST http://localhost:8300/tools/read_tiles \
  -d '{"room_id": "forge", "limit": 5}'

# Write a tile
curl -X POST http://localhost:8300/tools/write_tile \
  -d '{"room_id": "my-room", "domain": "test", "agent": "bot",
       "question": "Hello from MCP", "answer": "PLATO speaks MCP!"}'

# Route a query to the cheapest safe model
curl -X POST http://localhost:8300/tools/route_query \
  -d '{"prompt": "What is the Eisenstein norm of 3+2ω?"}'

# Check fleet health
curl -X POST http://localhost:8300/tools/query_health
```

## Tools

| Tool | What It Does |
|------|-------------|
| `list_rooms` | List all PLATO rooms (optional prefix filter) |
| `read_tiles` | Read tiles from a room — frozen computation steps |
| `write_tile` | Write a tile to a room — submit work, findings, moves |
| `query_health` | Fleet structural + behavioral health check |
| `route_query` | Route to cheapest safe model via critical angles |
| `search_tiles` | Search tiles across rooms by keyword |

## Why MCP?

MCP is Anthropic's open standard for agent-to-tool communication. Every major framework supports it: LangGraph, OpenAI Agents SDK, Strands, n8n, Claude Code. By making PLATO an MCP server, any of these can:

- Read and write tiles
- Search knowledge across rooms
- Route queries through the fleet
- Check system health

No custom protocol. No vendor lock-in. Just tools that work.

## Architecture

```
Any MCP Client (LangGraph, OpenAI SDK, Claude Code, ...)
        │
        ▼
   PLATO MCP Server (:8300)
        │
        ├── list_rooms / read_tiles / write_tile ──→ PLATO Server (:8847)
        ├── route_query ──→ Fleet Router (:8100)
        └── query_health ──→ PLATO + Fleet Router
```

## Docker

```bash
docker build -t plato-mcp .
docker run -p 8300:8300 plato-mcp
```

## Testing

```bash
pip install -e ".[test]"
pytest tests/
```

## Related Repos

- **plato-core** — foundation types and mesh registry
- **plato-types** — core tile protocol types
- **plato-training** — training rooms and micro models
