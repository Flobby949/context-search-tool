from context_search_tool.config import QueryPlannerConfig
from context_search_tool.models import QueryPlan
from context_search_tool.query_planner import (
    PROMPT_VERSION,
    clean_planner_payload,
    disabled_plan,
    fallback_plan,
    prompt_hash,
)


def test_query_plan_defaults_to_disabled() -> None:
    plan = QueryPlan(original_query="数据看板统计图表功能")

    assert plan.status == "disabled"
    assert plan.rewritten_queries == []
    assert plan.grep_keywords == []
    assert plan.symbol_hints == []
    assert plan.intent == "unknown"


def test_clean_planner_payload_strips_dedupes_truncates_and_validates_intent() -> None:
    config = QueryPlannerConfig(
        max_rewritten_queries=2,
        max_keywords=3,
        max_symbol_hints=1,
    )

    plan = clean_planner_payload(
        original_query="数据看板统计图表功能",
        payload={
            "rewritten_queries": [
                " dashboard chart ",
                "Dashboard chart",
                "extra query",
            ],
            "grep_keywords": ["Dashboard", " dashboard ", "", "Chart"],
            "symbol_hints": ["DashboardService", "dashboardservice", "Ignored"],
            "intent": "feature_lookup",
        },
        config=config,
        provider="ollama",
        model="qwen3.5:4b-mlx",
        latency_ms=42,
    )

    assert plan.status == "ok"
    assert plan.provider == "ollama"
    assert plan.model == "qwen3.5:4b-mlx"
    assert plan.prompt_version == PROMPT_VERSION
    assert plan.prompt_hash == prompt_hash()
    assert plan.latency_ms == 42
    assert plan.rewritten_queries == ["dashboard chart", "extra query"]
    assert plan.grep_keywords == ["Dashboard", "Chart"]
    assert plan.symbol_hints == ["DashboardService"]
    assert plan.intent == "feature_lookup"


def test_clean_planner_payload_falls_back_on_wrong_field_types() -> None:
    plan = clean_planner_payload(
        original_query="数据看板统计图表功能",
        payload={"grep_keywords": "Dashboard"},
        config=QueryPlannerConfig(),
        provider="ollama",
        model="qwen3.5:4b-mlx",
        latency_ms=10,
    )

    assert plan.status == "fallback"
    assert "grep_keywords must be a list" in (plan.error or "")


def test_clean_planner_payload_uses_unknown_for_unknown_intent() -> None:
    plan = clean_planner_payload(
        original_query="数据看板统计图表功能",
        payload={"intent": "invented"},
        config=QueryPlannerConfig(),
        provider="ollama",
        model="qwen3.5:4b-mlx",
        latency_ms=10,
    )

    assert plan.status == "ok"
    assert plan.intent == "unknown"


def test_clean_planner_payload_uses_unknown_for_non_string_intent() -> None:
    plan = clean_planner_payload(
        original_query="数据看板统计图表功能",
        payload={"intent": 123},
        config=QueryPlannerConfig(),
        provider="ollama",
        model="qwen3.5:4b-mlx",
        latency_ms=10,
    )

    assert plan.status == "ok"
    assert plan.intent == "unknown"


def test_clean_planner_payload_returns_empty_lists_when_limits_are_not_positive() -> None:
    plan = clean_planner_payload(
        original_query="query",
        payload={
            "rewritten_queries": ["one", "two"],
            "grep_keywords": ["A", "B"],
            "symbol_hints": ["Service", "Controller"],
        },
        config=QueryPlannerConfig(
            max_rewritten_queries=0,
            max_keywords=0,
            max_symbol_hints=-1,
        ),
        provider="ollama",
        model="qwen3.5:4b-mlx",
        latency_ms=10,
    )

    assert plan.status == "ok"
    assert plan.rewritten_queries == []
    assert plan.grep_keywords == []
    assert plan.symbol_hints == []


def test_disabled_and_fallback_helpers_include_diagnostics() -> None:
    disabled = disabled_plan("query")
    fallback = fallback_plan(
        "query",
        provider="ollama",
        model="qwen3.5:4b-mlx",
        latency_ms=8,
        error="planner timed out after 8 seconds",
    )

    assert disabled.status == "disabled"
    assert fallback.status == "fallback"
    assert fallback.latency_ms == 8
    assert fallback.error == "planner timed out after 8 seconds"
