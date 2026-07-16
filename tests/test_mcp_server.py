import inspect


def test_mcp_server_imports() -> None:
    from context_search_tool import mcp_server

    assert mcp_server.SERVER_NAME == "context-search-tool"
    assert mcp_server.mcp is not None
    assert callable(mcp_server.main)
    assert callable(mcp_server.context_search_index)
    assert callable(mcp_server.context_search_query)
    assert callable(mcp_server.context_search_trace)
    assert callable(mcp_server.context_search_context)
    assert callable(mcp_server.context_search_stats)
    assert callable(mcp_server.context_search_explain)
    assert "raw ranked search" in mcp_server.context_search_query.__doc__.lower()
    assert "retrieval diagnostics" in mcp_server.context_search_trace.__doc__.lower()
    assert "agent-oriented" in mcp_server.context_search_context.__doc__.lower()


def test_context_tool_adds_only_nullable_v2_budget_overrides() -> None:
    from context_search_tool import mcp_server

    query_parameters = inspect.signature(
        mcp_server.context_search_query
    ).parameters
    trace_parameters = inspect.signature(
        mcp_server.context_search_trace
    ).parameters
    context_parameters = inspect.signature(
        mcp_server.context_search_context
    ).parameters

    assert tuple(query_parameters) == (
        "repo",
        "query",
        "context_lines",
        "full_file",
        "final_top_k",
    )
    assert tuple(trace_parameters) == tuple(query_parameters)
    assert tuple(context_parameters) == (
        *query_parameters,
        "max_items",
        "max_context_bytes",
    )
    assert context_parameters["max_items"].default is None
    assert context_parameters["max_context_bytes"].default is None


def test_trace_tool_matches_query_arguments_exactly() -> None:
    from context_search_tool import mcp_server

    query_parameters = inspect.signature(
        mcp_server.context_search_query
    ).parameters
    trace_parameters = inspect.signature(
        mcp_server.context_search_trace
    ).parameters
    assert tuple(trace_parameters) == tuple(query_parameters)
    assert "retrieval diagnostics" in (
        mcp_server.context_search_trace.__doc__ or ""
    ).lower()
