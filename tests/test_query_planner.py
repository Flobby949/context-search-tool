import hashlib
import json
from pathlib import Path

import pytest
import requests

from context_search_tool.config import (
    QueryPlannerConfig,
    replace_query_planner_config,
)
from context_search_tool.models import (
    EvidenceAnchor,
    QueryPlan,
    QueryVariant,
    RepoProfile,
    RetrievalCandidate,
    RetrievalResult,
)
from context_search_tool.query_planner import (
    MAX_IMPORTED_HINT_CODEPOINTS,
    MAX_IMPORTED_MODULE_HINTS,
    MAX_IMPORTED_SYMBOL_HINTS,
    OllamaQueryPlanner,
    OpenAICompatibleQueryPlanner,
    PROMPT_VERSION,
    PLANNER_JSON_FIELDS,
    build_query_variants,
    clean_planner_payload,
    disabled_plan,
    expand_query_plan_tokens,
    fallback_plan,
    planner_hint_tokens,
    planner_from_config,
    prompt_hash,
)
from context_search_tool.retrieval_core import ordering, ranking
from context_search_tool.tokenizer import tokenize_query


def test_query_plan_defaults_to_disabled() -> None:
    plan = QueryPlan(original_query="数据看板统计图表功能")

    assert plan.status == "disabled"
    assert plan.rewritten_queries == []
    assert plan.grep_keywords == []
    assert plan.symbol_hints == []
    assert plan.dependency_intent == "none"
    assert plan.imported_symbol_hints == []
    assert plan.imported_module_hints == []
    assert plan.intent == "unknown"


def test_p15_v4_attempt_contract_binds_product_constants_before_fresh() -> None:
    contract_path = (
        Path(__file__).parent
        / "fixtures"
        / "p15_v4_query_dependency_hints"
        / "attempt-contract.json"
    )
    contract = json.loads(contract_path.read_text(encoding="utf-8"))

    assert contract["status"] == "frozen_before_fresh_repository_selection"
    assert contract["fresh_repository"] == {
        "identity_selected": False,
        "queries_disclosed": False,
        "gold_disclosed": False,
    }
    assert contract["online"]["model"] == "Qwen/Qwen2.5-14B-Instruct"
    assert contract["online"]["temperature"] == 0
    assert contract["online"]["seed"] == 0
    assert contract["planner"]["prompt_version"] == PROMPT_VERSION
    assert contract["planner"]["prompt_sha256"] == prompt_hash().removeprefix(
        "sha256:"
    )
    assert set(contract["planner"]["response_fields"]) == PLANNER_JSON_FIELDS
    assert contract["planner"]["max_imported_symbol_hints"] == MAX_IMPORTED_SYMBOL_HINTS
    assert contract["planner"]["max_imported_module_hints"] == MAX_IMPORTED_MODULE_HINTS
    assert contract["planner"]["max_imported_hint_codepoints"] == MAX_IMPORTED_HINT_CODEPOINTS
    assert contract["planner"]["response_envelope"] == (
        "one_complete_json_object_only"
    )
    assert contract["planner"]["missing_response_field"] == "reject_entire_plan"
    assert contract["local_rule"]["maximum_promotions"] == (
        ranking._PLANNER_DEPENDENCY_MAX_PROMOTIONS
    )
    assert contract["local_rule"]["score_bucket_decimals"] == (
        ordering.RERANK_SORT_DECIMALS
    )
    assert contract["local_rule"]["reason"] == "planner exact dependency target"
    assert len(hashlib.sha256(contract_path.read_bytes()).hexdigest()) == 64


def test_query_plan_disabled_default_uses_empty_disabled_plan() -> None:
    plan = QueryPlan.disabled_default()

    assert plan.status == "disabled"
    assert plan.original_query == ""
    assert plan.rewritten_queries == []
    assert plan.grep_keywords == []
    assert plan.symbol_hints == []
    assert plan.intent == "unknown"


def test_build_query_variants_normalizes_dedupes_bounds_and_assigns_stable_ids() -> (
    None
):
    overlong = "x" * 257
    plan = QueryPlan(
        original_query="  Data   Dashboard  ",
        rewritten_queries=[
            overlong,
            "data dashboard",
            "  dashboard   statistics  ",
            "DASHBOARD STATISTICS",
            "chart service",
            "ignored after limit",
        ],
        status="ok",
    )

    variants, discarded = build_query_variants(
        "  Data   Dashboard  ",
        plan,
        max_rewritten_queries=2,
    )

    assert variants == [
        QueryVariant("original", "Data Dashboard", "original"),
        QueryVariant("planner:0", "dashboard statistics", "planner"),
        QueryVariant("planner:1", "chart service", "planner"),
    ]
    assert discarded == [overlong]


@pytest.mark.parametrize("status", ["disabled", "fallback"])
def test_build_query_variants_uses_original_only_unless_plan_is_ok(status: str) -> None:
    plan = QueryPlan(
        original_query="  target   query ",
        rewritten_queries=["ignored rewrite"],
        status=status,
    )

    variants, discarded = build_query_variants(
        "  target   query ",
        plan,
        max_rewritten_queries=2,
    )

    assert variants == [QueryVariant("original", "target query", "original")]
    assert discarded == []


def test_build_query_variants_ok_without_rewrites_is_original_only() -> None:
    plan = QueryPlan(original_query="target query", status="ok")

    variants, discarded = build_query_variants(
        "target query",
        plan,
        max_rewritten_queries=2,
    )

    assert variants == [QueryVariant("original", "target query", "original")]
    assert discarded == []


def test_build_query_variants_accepts_256_code_points_without_truncation() -> None:
    accepted = "界" * 256
    plan = QueryPlan(
        original_query="target query",
        rewritten_queries=[accepted],
        status="ok",
    )

    variants, discarded = build_query_variants(
        "target query",
        plan,
        max_rewritten_queries=1,
    )

    assert variants == [
        QueryVariant("original", "target query", "original"),
        QueryVariant("planner:0", accepted, "planner"),
    ]
    assert discarded == []


def test_semantic_provenance_models_keep_existing_constructors_compatible() -> None:
    candidate = RetrievalCandidate("chunk", 0.4, "lexical")
    result = RetrievalResult(
        Path("App.py"),
        1,
        1,
        "pass",
        0.4,
        {},
        [],
        [],
    )
    anchor = EvidenceAnchor(
        Path("README.md"),
        1,
        1,
        "docs",
        0.1,
        {},
        [],
        "document",
    )

    assert candidate.semantic_matches == []
    assert result.semantic_matches == []
    assert anchor.semantic_matches == []


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


def test_clean_planner_payload_strictly_cleans_dependency_hints() -> None:
    plan = clean_planner_payload(
        original_query="trace Request imports from httpx._models",
        payload={
            "rewritten_queries": [],
            "grep_keywords": [],
            "symbol_hints": [],
            "intent": "data_flow",
            "dependency_intent": "follow_imports",
            "imported_symbol_hints": [" Request ", "request", "URL", "Invalid path"],
            "imported_module_hints": [
                " httpx._models ",
                "HTTPX._MODELS",
                "httpx._urls",
                "src/httpx/_models.py",
            ],
        },
        config=QueryPlannerConfig(),
        provider="openai-compatible",
        model="Qwen/Qwen2.5-14B-Instruct",
        latency_ms=42,
    )

    assert plan.status == "ok"
    assert plan.dependency_intent == "follow_imports"
    assert plan.imported_symbol_hints == ["Request", "URL"]
    assert plan.imported_module_hints == ["httpx._models", "httpx._urls"]


@pytest.mark.parametrize(
    "payload",
    [
        {"dependency_intent": "invented"},
        {"dependency_intent": "follow_imports", "imported_symbol_hints": "Request"},
        {"dependency_intent": "follow_imports", "unexpected": []},
    ],
)
def test_clean_planner_payload_rejects_invalid_dependency_schema(
    payload: dict[str, object],
) -> None:
    plan = clean_planner_payload(
        original_query="trace imports",
        payload=payload,
        config=QueryPlannerConfig(),
        provider="openai-compatible",
        model="Qwen/Qwen2.5-14B-Instruct",
        latency_ms=42,
    )

    assert plan.status == "fallback"
    assert plan.dependency_intent == "none"
    assert plan.imported_symbol_hints == []
    assert plan.imported_module_hints == []


@pytest.mark.parametrize(
    ("original_query", "exact_identifier"),
    (
        ("useAuthStore", "useAuthStore"),
        (" AuditStatus ", "AuditStatus"),
        ("apply_dev", "apply_dev"),
        ("INVOLVED_BY_ME", "INVOLVED_BY_ME"),
    ),
)
def test_clean_planner_payload_enforces_original_only_for_exact_identifier(
    original_query: str,
    exact_identifier: str,
) -> None:
    plan = clean_planner_payload(
        original_query=original_query,
        payload={
            "rewritten_queries": ["involved by me", "can apply"],
            "grep_keywords": ["canApply", "findByStatus"],
            "symbol_hints": ["canApply", "AuditStatus"],
            "intent": "symbol_lookup",
        },
        config=QueryPlannerConfig(
            max_rewritten_queries=4,
            max_keywords=2,
            max_symbol_hints=2,
        ),
        provider="openai-compatible",
        model="Qwen/Qwen2.5-14B-Instruct",
        latency_ms=42,
    )

    assert plan.status == "ok"
    assert plan.rewritten_queries == []
    assert plan.grep_keywords == [exact_identifier, "canApply"]
    assert plan.symbol_hints == [exact_identifier, "canApply"]
    assert plan.discarded_hints == ["involved by me", "can apply"]


@pytest.mark.parametrize(
    "original_query",
    (
        "`INVOLVED_BY_ME`",
        "(AuditStatus)",
        "apply_dev!",
        "find useAuthStore",
        "AuditStatus apply_dev",
    ),
)
def test_clean_planner_payload_preserves_hints_for_non_exact_identifier_queries(
    original_query: str,
) -> None:
    plan = clean_planner_payload(
        original_query=original_query,
        payload={
            "rewritten_queries": ["related behavior"],
            "grep_keywords": ["canApply"],
            "symbol_hints": ["AuditStatus"],
            "intent": "symbol_lookup",
        },
        config=QueryPlannerConfig(),
        provider="openai-compatible",
        model="Qwen/Qwen2.5-14B-Instruct",
        latency_ms=42,
    )

    assert plan.status == "ok"
    assert plan.rewritten_queries == ["related behavior"]
    assert plan.grep_keywords == ["canApply"]
    assert plan.symbol_hints == ["AuditStatus"]
    assert plan.discarded_hints == []


def test_clean_planner_payload_discards_overlong_rewrite_before_count_limit() -> None:
    overlong = "x" * 257

    plan = clean_planner_payload(
        original_query="target",
        payload={
            "rewritten_queries": [
                overlong,
                "target",
                "first valid",
                "second valid",
                "third valid",
            ]
        },
        config=QueryPlannerConfig(max_rewritten_queries=2),
        provider="ollama",
        model="qwen3.5:4b-mlx",
        latency_ms=10,
    )

    assert plan.status == "ok"
    assert plan.rewritten_queries == ["first valid", "second valid"]
    assert plan.discarded_hints == [overlong]


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


def _complete_planner_payload(**changes: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "rewritten_queries": [],
        "grep_keywords": [],
        "symbol_hints": [],
        "intent": "unknown",
        "dependency_intent": "none",
        "imported_symbol_hints": [],
        "imported_module_hints": [],
    }
    payload.update(changes)
    return payload


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
                        _complete_planner_payload(
                            rewritten_queries=["session cookies"],
                            grep_keywords=["RequestsCookieJar"],
                            symbol_hints=["Session"],
                            intent="feature_lookup",
                        )
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
                        _complete_planner_payload(
                            rewritten_queries=["数据看板 dashboard statistics chart"],
                            grep_keywords=["Dashboard", "Statistics", "Chart"],
                            symbol_hints=["DashboardController"],
                            intent="feature_lookup",
                        )
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
    session = FakeSession(
        FakeResponse(
            200,
            {
                "message": {
                    "content": json.dumps(_complete_planner_payload())
                }
            },
        )
    )
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


def test_ollama_planner_rejects_fenced_json_content() -> None:
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
  "intent": "feature_lookup",
  "dependency_intent": "none",
  "imported_symbol_hints": [],
  "imported_module_hints": []
}
```"""
                }
            },
        )
    )
    planner = OllamaQueryPlanner(QueryPlannerConfig(enabled=True), session=session)

    plan = planner.plan("驿站设备列表")

    assert plan.status == "fallback"
    assert "invalid planner JSON" in (plan.error or "")


def test_ollama_planner_rejects_prefixed_or_multiple_json_objects() -> None:
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
  "intent": "feature_lookup",
  "dependency_intent": "none",
  "imported_symbol_hints": [],
  "imported_module_hints": []
}"""
                }
            },
        )
    )
    planner = OllamaQueryPlanner(QueryPlannerConfig(enabled=True), session=session)

    plan = planner.plan("驿站设备列表")

    assert plan.status == "fallback"
    assert "invalid planner JSON" in (plan.error or "")


def test_ollama_planner_rejects_json_object_with_missing_schema_field() -> None:
    incomplete = _complete_planner_payload()
    incomplete.pop("imported_module_hints")
    session = FakeSession(
        FakeResponse(
            200,
            {"message": {"content": json.dumps(incomplete)}},
        )
    )

    plan = OllamaQueryPlanner(QueryPlannerConfig(enabled=True), session=session).plan(
        "query"
    )

    assert plan.status == "fallback"
    assert "invalid planner JSON" in (plan.error or "")


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


def test_openai_compatible_planner_uses_chat_completions_protocol(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "ignored-environment-key")
    session = FakeSession(
        FakeResponse(
            200,
            {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": json.dumps(
                                _complete_planner_payload(
                                    rewritten_queries=["session cookies"],
                                    grep_keywords=["RequestsCookieJar"],
                                    symbol_hints=["Session"],
                                    intent="feature_lookup",
                                )
                            ),
                        }
                    }
                ]
            },
        )
    )
    config = replace_query_planner_config(
        QueryPlannerConfig(
            enabled=True,
            provider="openai-compatible",
            model="Qwen/Qwen2.5-7B-Instruct",
            base_url="https://api.siliconflow.cn/v1",
            timeout_seconds=12.0,
        ),
        api_key="configured-api-key",
    )
    planner = OpenAICompatibleQueryPlanner(config, session=session)

    plan = planner.plan(
        "where are cookies kept",
        repo_profile=_python_requests_profile(),
    )

    assert plan.status == "ok"
    assert plan.provider == "openai-compatible"
    assert plan.model == "Qwen/Qwen2.5-7B-Instruct"
    assert plan.grep_keywords == ["RequestsCookieJar"]
    assert session.trust_env is False
    call = session.calls[0]
    assert call["url"] == "https://api.siliconflow.cn/v1/chat/completions"
    assert call["headers"] == {"Authorization": "Bearer configured-api-key"}
    assert call["timeout"] == 12.0
    assert set(call["json"]) == {
        "max_tokens",
        "messages",
        "model",
        "response_format",
        "stream",
        "temperature",
        "seed",
    }
    assert call["json"]["model"] == "Qwen/Qwen2.5-7B-Instruct"
    assert call["json"]["stream"] is False
    assert call["json"]["max_tokens"] == 512
    assert call["json"]["response_format"] == {"type": "json_object"}
    assert call["json"]["temperature"] == 0
    assert call["json"]["seed"] == 0
    system_prompt = call["json"]["messages"][0]["content"]
    assert "complete query is already one code identifier" in system_prompt
    assert "rewritten_queries as an empty array" in system_prompt
    user_payload = json.loads(call["json"]["messages"][1]["content"])
    assert user_payload["repo_profile"]["languages"] == ["python"]


def test_openai_compatible_planner_query_only_mode_sends_no_repo_metadata() -> None:
    session = FakeSession(
        FakeResponse(
            200,
            {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "rewritten_queries": [],
                                    "grep_keywords": [],
                                    "symbol_hints": [],
                                    "intent": "data_flow",
                                    "dependency_intent": "follow_imports",
                                    "imported_symbol_hints": ["Request"],
                                    "imported_module_hints": ["httpx._models"],
                                }
                            )
                        }
                    }
                ]
            },
        )
    )
    config = replace_query_planner_config(
        QueryPlannerConfig(
            enabled=True,
            provider="openai-compatible",
            model="Qwen/Qwen2.5-14B-Instruct",
            base_url="https://api.siliconflow.cn/v1",
            send_repo_profile=False,
        ),
        api_key="configured-api-key",
    )

    plan = OpenAICompatibleQueryPlanner(config, session=session).plan(
        "trace Request imports",
        repo_profile=_python_requests_profile(),
    )

    assert plan.status == "ok"
    assert plan.imported_symbol_hints == ["Request"]
    call = session.calls[0]
    user_payload = json.loads(call["json"]["messages"][1]["content"])
    assert set(user_payload) == {
        "query",
        "max_rewritten_queries",
        "max_keywords",
        "max_symbol_hints",
        "max_imported_symbol_hints",
        "max_imported_module_hints",
    }
    serialized_user_payload = call["json"]["messages"][1]["content"]
    assert "repo_profile" not in serialized_user_payload
    assert "important_files" not in serialized_user_payload
    assert "configured-api-key" not in json.dumps(call["json"], ensure_ascii=False)


def test_openai_compatible_planner_allows_authless_local_endpoint() -> None:
    session = FakeSession(
        FakeResponse(
            200,
            {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": json.dumps(_complete_planner_payload()),
                        }
                    }
                ]
            },
        )
    )
    config = QueryPlannerConfig(
        enabled=True,
        provider="openai-compatible",
        base_url="http://127.0.0.1:8000/v1/",
    )
    planner = OpenAICompatibleQueryPlanner(config, session=session)

    plan = planner.plan("query")

    assert plan.status == "ok"
    assert session.calls[0]["url"] == "http://127.0.0.1:8000/v1/chat/completions"
    assert "headers" not in session.calls[0]


@pytest.mark.parametrize(
    ("payload", "error"),
    [
        ({}, "planner response choices must be a non-empty list"),
        ({"choices": [None]}, "planner response choice must be an object"),
        (
            {"choices": [{"message": None}]},
            "planner response message must be an object",
        ),
    ],
)
def test_openai_compatible_planner_falls_back_on_malformed_response(
    payload: dict[str, object],
    error: str,
) -> None:
    session = FakeSession(FakeResponse(200, payload))
    config = QueryPlannerConfig(enabled=True, provider="openai-compatible")
    planner = OpenAICompatibleQueryPlanner(config, session=session)

    plan = planner.plan("query")

    assert plan.status == "fallback"
    assert error in (plan.error or "")


def test_planner_from_config_builds_openai_compatible_planner() -> None:
    planner = planner_from_config(
        QueryPlannerConfig(enabled=True, provider="openai-compatible")
    )

    assert isinstance(planner, OpenAICompatibleQueryPlanner)


def test_planner_from_config_returns_disabled_planner_when_disabled() -> None:
    planner = planner_from_config(QueryPlannerConfig(enabled=False))

    assert planner.plan("query").status == "disabled"
