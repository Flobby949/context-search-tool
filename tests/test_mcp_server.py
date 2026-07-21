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
    assert callable(mcp_server.context_search_refresh)
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


def test_p6_status_and_stats_public_signatures_are_frozen() -> None:
    from context_search_tool import mcp_server

    assert hasattr(mcp_server, "context_search_status"), (
        "P6 MCP status server tool is absent"
    )
    assert callable(mcp_server.context_search_status)

    status_parameters = inspect.signature(
        mcp_server.context_search_status
    ).parameters
    stats_parameters = inspect.signature(mcp_server.context_search_stats).parameters

    assert tuple(status_parameters) == ("repo", "verify")
    assert status_parameters["verify"].default is False
    assert tuple(stats_parameters) == ("repo", "verify")
    assert stats_parameters["verify"].default is False

    refresh_parameters = inspect.signature(
        mcp_server.context_search_refresh
    ).parameters
    assert tuple(refresh_parameters) == ("repo",)


def test_p6_status_description_promises_read_only_provider_free_inspection() -> None:
    from context_search_tool import mcp_server

    assert hasattr(mcp_server, "context_search_status"), (
        "P6 MCP status server tool is absent"
    )
    description = (mcp_server.context_search_status.__doc__ or "").lower()

    assert "read-only" in description
    assert "provider" in description
    assert "without" in description


def test_p6_refresh_description_discloses_mutation_and_remote_source_text() -> None:
    from context_search_tool import mcp_server

    description = (mcp_server.context_search_refresh.__doc__ or "").lower()

    assert "mutat" in description
    assert "new/content-changed" in description
    assert "remote" in description
