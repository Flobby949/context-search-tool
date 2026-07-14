import inspect


def test_mcp_server_imports() -> None:
    from context_search_tool import mcp_server

    assert mcp_server.SERVER_NAME == "context-search-tool"
    assert mcp_server.mcp is not None
    assert callable(mcp_server.main)
    assert callable(mcp_server.context_search_index)
    assert callable(mcp_server.context_search_query)
    assert callable(mcp_server.context_search_context)
    assert callable(mcp_server.context_search_stats)
    assert callable(mcp_server.context_search_explain)
    assert inspect.signature(mcp_server.context_search_context) == inspect.signature(
        mcp_server.context_search_query
    )
    assert "raw ranked search" in mcp_server.context_search_query.__doc__.lower()
    assert "agent-oriented" in mcp_server.context_search_context.__doc__.lower()
