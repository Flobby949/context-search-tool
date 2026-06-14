from __future__ import annotations

import logging
import os
from typing import Any

from mcp.server.fastmcp import FastMCP

from context_search_tool.mcp_tools import (
    context_search_explain_tool,
    context_search_index_tool,
    context_search_query_tool,
    context_search_stats_tool,
)

SERVER_NAME = "context-search-tool"
DEFAULT_LOG_FILE = "/tmp/cst-mcp.log"

mcp = FastMCP(SERVER_NAME)


@mcp.tool()
def context_search_index(repo: str) -> dict[str, Any]:
    """Create or update the Context Search index for a local repository."""
    return context_search_index_tool(repo)


@mcp.tool()
def context_search_query(
    repo: str,
    query: str,
    context_lines: int | None = None,
    full_file: bool = False,
    final_top_k: int | None = None,
) -> dict[str, Any]:
    """Search indexed code context in a local repository."""
    return context_search_query_tool(
        repo=repo,
        query=query,
        context_lines=context_lines,
        full_file=full_file,
        final_top_k=final_top_k,
    )


@mcp.tool()
def context_search_stats(repo: str) -> dict[str, Any]:
    """Return index and embedding statistics for a local repository."""
    return context_search_stats_tool(repo)


@mcp.tool()
def context_search_explain(repo: str, location: str) -> dict[str, Any]:
    """Explain which indexed chunk covers a file:line location."""
    return context_search_explain_tool(repo, location)


def main() -> None:
    logging.basicConfig(
        filename=os.environ.get("CST_MCP_LOG_FILE", DEFAULT_LOG_FILE),
        level=logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        force=True,
    )
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
