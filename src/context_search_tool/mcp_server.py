from __future__ import annotations

import logging
import os
from typing import Any

from mcp.server.fastmcp import FastMCP

from context_search_tool.mcp_tools import (
    context_search_context_tool,
    context_search_explain_tool,
    context_search_explore_tool,
    context_search_index_tool,
    context_search_query_tool,
    context_search_stats_tool,
    context_search_trace_tool,
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
    """Return raw ranked search results from a local repository index."""
    return context_search_query_tool(
        repo=repo,
        query=query,
        context_lines=context_lines,
        full_file=full_file,
        final_top_k=final_top_k,
    )


@mcp.tool()
def context_search_trace(
    repo: str,
    query: str,
    context_lines: int | None = None,
    full_file: bool = False,
    final_top_k: int | None = None,
) -> dict[str, Any]:
    """Return bounded retrieval diagnostics without source content."""
    return context_search_trace_tool(
        repo=repo,
        query=query,
        context_lines=context_lines,
        full_file=full_file,
        final_top_k=final_top_k,
    )


@mcp.tool()
def context_search_context(
    repo: str,
    query: str,
    context_lines: int | None = None,
    full_file: bool = False,
    final_top_k: int | None = None,
    max_items: int | None = None,
    max_context_bytes: int | None = None,
) -> dict[str, Any]:
    """Return an agent-oriented ContextPack from one bounded retrieval pass."""
    return context_search_context_tool(
        repo=repo,
        query=query,
        context_lines=context_lines,
        full_file=full_file,
        final_top_k=final_top_k,
        max_items=max_items,
        max_context_bytes=max_context_bytes,
    )


@mcp.tool()
def context_search_explore(
    repo: str,
    query: str,
    context_lines: int | None = None,
    full_file: bool = False,
    final_top_k: int | None = None,
    max_items: int | None = None,
    max_context_bytes: int | None = None,
) -> dict[str, Any]:
    """Return a bounded controlled exploration and final ContextPack."""
    return context_search_explore_tool(
        repo=repo,
        query=query,
        context_lines=context_lines,
        full_file=full_file,
        final_top_k=final_top_k,
        max_items=max_items,
        max_context_bytes=max_context_bytes,
    )


@mcp.tool()
def context_search_stats(repo: str) -> dict[str, Any]:
    """Return index and embedding statistics for a local repository."""
    return context_search_stats_tool(repo)


@mcp.tool()
def context_search_explain(repo: str, location: str) -> dict[str, Any]:
    """Return the indexed chunk and bounded graph projection for a file:line location."""
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
