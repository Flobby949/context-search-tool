import json

import requests

from context_search_tool.config import QueryPlannerConfig
from context_search_tool.models import QueryPlan, RepoProfile
from context_search_tool.query_planner import (
    OllamaQueryPlanner,
    PROMPT_VERSION,
    clean_planner_payload,
    disabled_plan,
    expand_query_plan_tokens,
    fallback_plan,
    planner_hint_tokens,
    planner_from_config,
    prompt_hash,
)
from context_search_tool.tokenizer import tokenize_query


def test_query_plan_defaults_to_disabled() -> None:
    plan = QueryPlan(original_query="数据看板统计图表功能")

    assert plan.status == "disabled"
    assert plan.rewritten_queries == []
    assert plan.grep_keywords == []
    assert plan.symbol_hints == []
    assert plan.intent == "unknown"


def test_query_plan_disabled_default_uses_empty_disabled_plan() -> None:
    plan = QueryPlan.disabled_default()

    assert plan.status == "disabled"
    assert plan.original_query == ""
    assert plan.rewritten_queries == []
    assert plan.grep_keywords == []
    assert plan.symbol_hints == []
    assert plan.intent == "unknown"


def test_expand_query_plan_tokens_keeps_original_tokens_first() -> None:
    query = "数据看板统计图表功能"
    plan = QueryPlan(
        original_query=query,
        rewritten_queries=["数据看板 dashboard statistics chart"],
        grep_keywords=["Dashboard", "Chart"],
        symbol_hints=["DashboardController"],
        status="ok",
    )

    tokens = expand_query_plan_tokens(query, plan)
    original_tokens = tokenize_query(query)

    assert tokens[: len(original_tokens)] == original_tokens
    assert "dashboard" in tokens
    assert "controller" in tokens
    assert "dashboardcontroller" not in tokens
    assert planner_hint_tokens(original_tokens, tokens)


def test_expand_query_plan_tokens_tokenizes_planner_keywords_and_symbol_hints() -> None:
    plan = QueryPlan(
        original_query="targetToken",
        grep_keywords=["auditStatus"],
        symbol_hints=["DashboardController"],
        status="ok",
    )

    tokens = expand_query_plan_tokens("targetToken", plan)

    assert tokens[:2] == ["target", "token"]
    assert "audit" in tokens
    assert "status" in tokens
    assert "dashboard" in tokens
    assert "controller" in tokens
    assert "auditstatus" not in tokens
    assert "dashboardcontroller" not in tokens


def test_expand_query_plan_tokens_non_ok_returns_normal_original_tokens() -> None:
    plan = QueryPlan(
        original_query="targetToken",
        rewritten_queries=["dashboard"],
        grep_keywords=["auditStatus"],
        symbol_hints=["DashboardController"],
        status="fallback",
    )

    tokens = expand_query_plan_tokens("targetToken", plan)

    assert tokens == ["target", "token"]


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


def test_clean_planner_payload_falls_back_on_non_string_list_members() -> None:
    plan = clean_planner_payload(
        original_query="数据看板统计图表功能",
        payload={"grep_keywords": ["Dashboard", 123]},
        config=QueryPlannerConfig(),
        provider="ollama",
        model="qwen3.5:4b-mlx",
        latency_ms=10,
    )

    assert plan.status == "fallback"
    assert "grep_keywords must contain only strings" in (plan.error or "")


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


class FakeResponse:
    def __init__(self, status_code: int, payload: dict[str, object]) -> None:
        self.status_code = status_code
        self._payload = payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def json(self) -> dict[str, object]:
        return self._payload


class FakeSession:
    def __init__(self, response: FakeResponse | Exception) -> None:
        self.response = response
        self.trust_env = True
        self.calls: list[dict[str, object]] = []

    def post(self, url: str, **kwargs: object) -> FakeResponse:
        self.calls.append({"url": url, **kwargs})
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def _python_requests_profile() -> RepoProfile:
    return RepoProfile(
        languages=["python"],
        source_roots=["src/requests"],
        important_files=["src/requests/sessions.py", "src/requests/cookies.py"],
        symbols=[],
        tokens=["requests", "session", "cookies", "cookie", "jar", "merge"],
        profile_hash="sha256:test",
    )


def test_ollama_planner_sends_repo_profile_without_java_spring_defaults() -> None:
    session = FakeSession(
        FakeResponse(
            200,
            {
                "message": {
                    "content": json.dumps(
                        {
                            "rewritten_queries": ["session cookies"],
                            "grep_keywords": ["RequestsCookieJar"],
                            "symbol_hints": ["Session"],
                            "intent": "feature_lookup",
                        }
                    )
                }
            },
        )
    )
    planner = OllamaQueryPlanner(QueryPlannerConfig(enabled=True), session=session)

    plan = planner.plan("where are cookies kept", repo_profile=_python_requests_profile())

    assert plan.status == "ok"
    payload = json.loads(session.calls[0]["json"]["messages"][1]["content"])
    assert payload["repo_profile"]["languages"] == ["python"]
    assert payload["repo_profile"]["source_roots"] == ["src/requests"]
    assert "language_hints" not in payload


def test_clean_planner_payload_drops_terms_without_repo_overlap() -> None:
    plan = clean_planner_payload(
        original_query="where are cookies kept",
        payload={
            "rewritten_queries": ["Spring HttpSession cookies", "requests session cookies"],
            "grep_keywords": ["HttpSession", "RequestsCookieJar"],
            "symbol_hints": ["RestTemplate", "Session"],
            "intent": "feature_lookup",
        },
        config=QueryPlannerConfig(),
        provider="ollama",
        model="qwen3.5:4b-mlx",
        latency_ms=10,
        repo_profile=_python_requests_profile(),
    )

    assert plan.rewritten_queries == ["session cookies", "requests session cookies"]
    assert plan.grep_keywords == ["RequestsCookieJar"]
    assert plan.symbol_hints == ["Session"]
    assert "HttpSession" in plan.discarded_hints
    assert "RestTemplate" in plan.discarded_hints
    assert plan.repo_profile_hash == "sha256:test"


def test_ollama_planner_parses_valid_json_and_bypasses_proxy() -> None:
    session = FakeSession(
        FakeResponse(
            200,
            {
                "message": {
                    "content": json.dumps(
                        {
                            "rewritten_queries": ["数据看板 dashboard statistics chart"],
                            "grep_keywords": ["Dashboard", "Statistics", "Chart"],
                            "symbol_hints": ["DashboardController"],
                            "intent": "feature_lookup",
                        }
                    )
                }
            },
        )
    )
    config = QueryPlannerConfig(enabled=True, timeout_seconds=1.5)
    planner = OllamaQueryPlanner(config, session=session)

    plan = planner.plan("数据看板统计图表功能")

    assert plan.status == "ok"
    assert plan.grep_keywords == ["Dashboard", "Statistics", "Chart"]
    assert plan.symbol_hints == ["DashboardController"]
    assert session.trust_env is False
    assert len(session.calls) == 1
    call = session.calls[0]
    assert call["url"] == "http://localhost:11434/api/chat"
    assert call["timeout"] == 1.5
    assert call["json"]["model"] == "qwen3.5:4b-mlx"
    assert call["json"]["stream"] is False
    assert call["json"]["think"] is False
    assert call["json"]["format"] == "json"
    system_prompt = call["json"]["messages"][0]["content"]
    assert "rewritten_queries" in system_prompt
    assert "grep_keywords" in system_prompt
    assert "symbol_hints" in system_prompt
    assert "intent" in system_prompt


def test_ollama_planner_honors_use_system_proxy() -> None:
    session = FakeSession(FakeResponse(200, {"message": {"content": "{}"}}))
    config = QueryPlannerConfig(enabled=True, use_system_proxy=True)
    planner = OllamaQueryPlanner(config, session=session)

    plan = planner.plan("query")

    assert plan.status == "ok"
    assert session.trust_env is True


def test_ollama_planner_falls_back_on_timeout_without_retry() -> None:
    session = FakeSession(requests.Timeout("slow"))
    config = QueryPlannerConfig(enabled=True, timeout_seconds=0.01)
    planner = OllamaQueryPlanner(config, session=session)

    plan = planner.plan("query")

    assert plan.status == "fallback"
    assert "planner timed out" in (plan.error or "")
    assert len(session.calls) == 1


def test_ollama_planner_falls_back_on_invalid_json_content() -> None:
    session = FakeSession(FakeResponse(200, {"message": {"content": "not json"}}))
    planner = OllamaQueryPlanner(QueryPlannerConfig(enabled=True), session=session)

    plan = planner.plan("query")

    assert plan.status == "fallback"
    assert "invalid planner JSON" in (plan.error or "")


def test_ollama_planner_parses_fenced_json_content() -> None:
    session = FakeSession(
        FakeResponse(
            200,
            {
                "message": {
                    "content": """```json
{
  "rewritten_queries": ["station device list"],
  "grep_keywords": ["StationDevice"],
  "symbol_hints": [],
  "intent": "feature_lookup"
}
```"""
                }
            },
        )
    )
    planner = OllamaQueryPlanner(QueryPlannerConfig(enabled=True), session=session)

    plan = planner.plan("驿站设备列表")

    assert plan.status == "ok"
    assert plan.rewritten_queries == ["station device list"]
    assert plan.grep_keywords == ["StationDevice"]
    assert plan.intent == "feature_lookup"


def test_ollama_planner_prefers_embedded_planner_json_over_example_json() -> None:
    session = FakeSession(
        FakeResponse(
            200,
            {
                "message": {
                    "content": """example: {"foo": "bar"}
{
  "rewritten_queries": ["station device list"],
  "grep_keywords": ["StationDevice"],
  "symbol_hints": [],
  "intent": "feature_lookup"
}"""
                }
            },
        )
    )
    planner = OllamaQueryPlanner(QueryPlannerConfig(enabled=True), session=session)

    plan = planner.plan("驿站设备列表")

    assert plan.status == "ok"
    assert plan.rewritten_queries == ["station device list"]


def test_ollama_planner_falls_back_on_top_level_array_json() -> None:
    session = FakeSession(
        FakeResponse(
            200,
            {
                "message": {
                    "content": json.dumps(
                        [
                            {
                                "rewritten_queries": ["station device list"],
                                "grep_keywords": ["StationDevice"],
                                "symbol_hints": [],
                                "intent": "feature_lookup",
                            }
                        ]
                    )
                }
            },
        )
    )
    planner = OllamaQueryPlanner(QueryPlannerConfig(enabled=True), session=session)

    plan = planner.plan("驿站设备列表")

    assert plan.status == "fallback"
    assert "invalid planner JSON" in (plan.error or "")


def test_ollama_planner_falls_back_on_malformed_response_message() -> None:
    session = FakeSession(FakeResponse(200, {"message": None}))
    planner = OllamaQueryPlanner(QueryPlannerConfig(enabled=True), session=session)

    plan = planner.plan("query")

    assert plan.status == "fallback"
    assert "planner response message must be an object" in (plan.error or "")


def test_ollama_planner_falls_back_on_http_error_without_retry() -> None:
    session = FakeSession(FakeResponse(500, {"message": {"content": "{}"}}))
    planner = OllamaQueryPlanner(QueryPlannerConfig(enabled=True), session=session)

    plan = planner.plan("query")

    assert plan.status == "fallback"
    assert "planner HTTP error" in (plan.error or "")
    assert len(session.calls) == 1


def test_planner_from_config_returns_disabled_planner_when_disabled() -> None:
    planner = planner_from_config(QueryPlannerConfig(enabled=False))

    assert planner.plan("query").status == "disabled"
