#!/usr/bin/env python3
"""plato_mcp.cli — Start the PLATO MCP server."""
import argparse, uvicorn

def main():
    p = argparse.ArgumentParser(description="PLATO MCP Server")
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=8300)
    p.add_argument("--reload", action="store_true")
    args = p.parse_args()
    uvicorn.run("plato_mcp.server:app", host=args.host, port=args.port, reload=args.reload)

if __name__ == "__main__":
    main()
