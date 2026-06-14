from __future__ import annotations

from mcp.server.fastmcp import FastMCP

SERVER_NAME = "context-search-tool"

mcp = FastMCP(SERVER_NAME)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
