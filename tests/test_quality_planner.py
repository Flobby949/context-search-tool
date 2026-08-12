from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

from context_search_tool.config import QueryPlannerConfig, RetrievalConfig, ToolConfig
from context_search_tool.indexer import index_repository
from context_search_tool.models import QueryPlan, RepoProfile
from context_search_tool.quality.cases import load_quality_fixture
from context_search_tool.quality.runner import run_quality_fixture
from context_search_tool.query_planner import clean_planner_payload
from context_search_tool.retrieval import query_repository
from context_search_tool.retrieval_scope import RetrievalScope
from context_search_tool.tokenizer import tokenize_query


CATALOG = Path(__file__).parent / "fixtures" / "retrieval_quality" / "queries.json"
FORBIDDEN = {"spring", "resttemplate", "httpsession", "restcontroller"}


def _consumed_values(plan: QueryPlan) -> list[str]:
    return [*plan.rewritten_queries, *plan.grep_keywords, *plan.symbol_hints]


def _consumed_tokens(plan: QueryPlan) -> set[str]:
    return {
        token.casefold()
        for value in _consumed_values(plan)
        for token in tokenize_query(value)
    }


def _compacted_consumed_text(plan: QueryPlan) -> str:
    return re.sub(r"[\W_]+", "", "\n".join(_consumed_values(plan)).casefold())


def assert_supported_non_noop_plan(
    plan: QueryPlan,
    original_query: str,
    expanded_tokens: list[str],
) -> None:
    assert plan.status == "ok"
    assert plan.repo_profile_hash
    consumed = _consumed_tokens(plan)
    assert consumed
    compacted = _compacted_consumed_text(plan)
    assert all(term not in compacted for term in FORBIDDEN)
    original = {token.casefold() for token in tokenize_query(original_query)}
    expanded = {token.casefold() for token in expanded_tokens}
    assert (consumed - original) & expanded


def test_canonical_planner_inventory_contains_requests_and_dashboard() -> None:
    fixture = load_quality_fixture(CATALOG)
    planner_cases = {
        f"{repo.repo_key}/{case.case_id}"
        for repo in fixture.repos
        for case in repo.queries
        if "planner" in (case.profiles or repo.profiles)
    }

    assert planner_cases == {
        "psf_requests/cookies-between-calls",
        "psf_requests/retry-proxy-pooling-natural",
        "psf_requests/stream-response-body-natural",
        "cross_language_dashboard/dashboard-cross-language",
    }


def test_supported_non_noop_plan_contract() -> None:
    plan = QueryPlan(
        original_query="数据看板统计图表功能",
        rewritten_queries=["dashboard statistics chart"],
        status="ok",
        repo_profile_hash="sha256:profile",
        discarded_hints=["Spring", "RestTemplate", "HttpSession", "RestController"],
    )

    assert_supported_non_noop_plan(
        plan,
        plan.original_query,
        ["数据看板统计图表功能", "dashboard", "statistics", "chart"],
    )


def test_p0_grounding_restores_local_rare_and_mixed_hints_only(
    tmp_path: Path,
) -> None:
    fixture_source = (
        Path(__file__).parent
        / "fixtures"
        / "p0-effects-monorepo"
        / "apps"
        / "billing"
        / "src"
        / "billing_flow.py"
    )
    fixture_text = fixture_source.read_text(encoding="utf-8")
    assert "class QuasarBridge" in fixture_text
    repo = tmp_path / "repo"
    included = repo / "apps" / "billing" / "src"
    excluded = repo / "apps" / "shipping" / "src"
    included.mkdir(parents=True)
    excluded.mkdir(parents=True)
    (included / "billing_flow.py").write_text(fixture_text, encoding="utf-8")
    (excluded / "scope_only.py").write_text(
        "class ScopeOnlyBridge:\n    pass\n",
        encoding="utf-8",
    )
    planner_config = QueryPlannerConfig(
        max_rewritten_queries=1,
        max_keywords=4,
        max_symbol_hints=4,
    )
    config = ToolConfig(
        retrieval=RetrievalConfig(
            semantic_top_k=0,
            lexical_top_k=20,
            final_top_k=5,
            context_before_lines=0,
            context_after_lines=0,
        ),
        query_planner=planner_config,
    )
    index_repository(repo, config)
    plan = clean_planner_payload(
        original_query="定位结算桥接逻辑",
        payload={
            "rewritten_queries": ["settlement flow QuasarBridge"],
            "grep_keywords": [
                "QuasarBridge",
                "QuasarBridge InventedBridge",
                "InventedBridge",
                "ScopeOnlyBridge",
            ],
            "symbol_hints": [
                "QuasarBridge",
                "QuasarBridge InventedBridge",
                "InventedBridge",
                "ScopeOnlyBridge",
            ],
        },
        config=planner_config,
        provider="fixture",
        model="fixture",
        latency_ms=0,
        repo_profile=RepoProfile(tokens=["settlement", "flow"]),
    )

    assert plan.rewritten_queries == ["settlement flow"]
    assert plan.grep_keywords == []
    assert plan.symbol_hints == []

    class FixedPlanner:
        def plan(self, query: str, repo_profile=None) -> QueryPlan:
            assert query == plan.original_query
            assert repo_profile is not None
            return plan

    bundle = query_repository(
        repo,
        plan.original_query,
        config,
        planner=FixedPlanner(),
        scope=RetrievalScope(include_paths=("apps/billing/**",)),
    )
    restored = bundle.planner

    assert restored.rewritten_queries == ["settlement flow QuasarBridge"]
    assert restored.grep_keywords == ["QuasarBridge"]
    assert restored.symbol_hints == ["QuasarBridge"]
    assert "InventedBridge" in restored.discarded_hints
    assert "ScopeOnlyBridge" in restored.discarded_hints
    assert restored.discarded_hint_sources == (
        ("grep_keywords", "QuasarBridge InventedBridge"),
        ("grep_keywords", "InventedBridge"),
        ("grep_keywords", "ScopeOnlyBridge"),
        ("symbol_hints", "QuasarBridge InventedBridge"),
        ("symbol_hints", "InventedBridge"),
        ("symbol_hints", "ScopeOnlyBridge"),
    )
    consumed = _consumed_values(restored)
    assert all("InventedBridge" not in value for value in consumed)
    assert all("ScopeOnlyBridge" not in value for value in consumed)
    assert {result.file_path.as_posix() for result in bundle.results} == {
        "apps/billing/src/billing_flow.py"
    }


@pytest.mark.parametrize(
    "plan,original_query,expanded_tokens",
    [
        (
            QueryPlan(
                original_query="target",
                rewritten_queries=["target helper"],
                status="fallback",
                repo_profile_hash="sha256:profile",
            ),
            "target",
            ["target", "helper"],
        ),
        (
            QueryPlan(
                original_query="target",
                status="ok",
                repo_profile_hash="sha256:profile",
            ),
            "target",
            ["target"],
        ),
        (
            QueryPlan(
                original_query="target query",
                rewritten_queries=["target query"],
                status="ok",
                repo_profile_hash="sha256:profile",
            ),
            "target query",
            ["target", "query"],
        ),
        (
            QueryPlan(
                original_query="target",
                grep_keywords=["RestTemplate"],
                status="ok",
                repo_profile_hash="sha256:profile",
            ),
            "target",
            ["target", "resttemplate"],
        ),
    ],
    ids=["fallback", "empty-hints", "no-op-hints", "unsupported-consumed"],
)
def test_supported_non_noop_plan_rejects_invalid_diagnostics(
    plan: QueryPlan,
    original_query: str,
    expanded_tokens: list[str],
) -> None:
    with pytest.raises(AssertionError):
        assert_supported_non_noop_plan(plan, original_query, expanded_tokens)


def _plan_from_record(case: dict) -> QueryPlan:
    return QueryPlan(
        original_query=case["query"],
        **{
            key: value
            for key, value in case["planner"].items()
            if key in QueryPlan.__dataclass_fields__ and key != "original_query"
        },
    )


def _requests_source() -> Path | None:
    raw_direct = os.environ.get("CST_PLANNER_REQUESTS_REPO")
    if raw_direct:
        direct = Path(raw_direct).expanduser().resolve()
        if direct.is_dir():
            return direct

    raw_smoke_root = os.environ.get("CST_SMOKE_REPOS_DIR")
    if raw_smoke_root:
        smoke_root = Path(raw_smoke_root).expanduser().resolve()
        if smoke_root.is_dir():
            fallback = (smoke_root / "requests").resolve()
            if fallback.is_dir():
                return fallback
    return None


def test_plan_from_record_uses_only_query_plan_fields() -> None:
    plan = _plan_from_record(
        {
            "query": "target",
            "planner": {
                "original_query": "ignored",
                "rewritten_queries": ["target helper"],
                "status": "ok",
                "repo_profile_hash": "sha256:profile",
                "unknown": "ignored",
            },
        }
    )

    assert plan.original_query == "target"
    assert plan.rewritten_queries == ["target helper"]
    assert plan.status == "ok"
    assert plan.repo_profile_hash == "sha256:profile"


def test_requests_source_prefers_valid_direct_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    direct_source = tmp_path / "direct"
    direct_source.mkdir()
    smoke_source = tmp_path / "smoke" / "requests"
    smoke_source.mkdir(parents=True)
    monkeypatch.setenv("CST_PLANNER_REQUESTS_REPO", str(direct_source))
    monkeypatch.setenv("CST_SMOKE_REPOS_DIR", str(smoke_source.parent))

    assert _requests_source() == direct_source


def test_requests_source_uses_smoke_root_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    smoke_source = tmp_path / "smoke" / "requests"
    smoke_source.mkdir(parents=True)
    monkeypatch.delenv("CST_PLANNER_REQUESTS_REPO", raising=False)
    monkeypatch.setenv("CST_SMOKE_REPOS_DIR", str(smoke_source.parent))

    assert _requests_source() == smoke_source


def test_requests_source_falls_back_from_stale_direct_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    smoke_source = tmp_path / "smoke" / "requests"
    smoke_source.mkdir(parents=True)
    monkeypatch.setenv(
        "CST_PLANNER_REQUESTS_REPO",
        str(tmp_path / "missing-direct"),
    )
    monkeypatch.setenv("CST_SMOKE_REPOS_DIR", str(smoke_source.parent))

    assert _requests_source() == smoke_source


def test_requests_source_returns_none_when_neither_source_exists(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "CST_PLANNER_REQUESTS_REPO",
        str(tmp_path / "missing-direct"),
    )
    monkeypatch.setenv("CST_SMOKE_REPOS_DIR", str(tmp_path / "missing-root"))

    assert _requests_source() is None


@pytest.fixture(scope="module")
def real_planner_report() -> dict:
    if _requests_source() is None:
        pytest.skip("requests checkout is not configured")
    return run_quality_fixture(CATALOG, "planner", None, None)


@pytest.mark.slow
@pytest.mark.integration
def test_real_requests_planner_is_three_of_three_with_supported_hints(
    real_planner_report: dict,
) -> None:
    request_cases = [
        case
        for case in real_planner_report["cases"]
        if case["repo_key"] == "psf_requests"
    ]

    assert {case["case_id"] for case in request_cases} == {
        "cookies-between-calls",
        "retry-proxy-pooling-natural",
        "stream-response-body-natural",
    }
    assert all(case["status"] == "pass" for case in request_cases)
    for case in request_cases:
        planner = _plan_from_record(case)
        assert_supported_non_noop_plan(
            planner,
            case["query"],
            case["expanded_tokens"],
        )


@pytest.mark.slow
@pytest.mark.integration
def test_real_dashboard_planner_supplies_english_bridge(
    real_planner_report: dict,
) -> None:
    case = next(
        case
        for case in real_planner_report["cases"]
        if case["repo_key"] == "cross_language_dashboard"
        and case["case_id"] == "dashboard-cross-language"
    )
    planner = _plan_from_record(case)

    assert case["status"] == "pass"
    assert_supported_non_noop_plan(
        planner,
        case["query"],
        case["expanded_tokens"],
    )
    bridge = {"dashboard", "statistics", "chart"}
    expanded = {token.casefold() for token in case["expanded_tokens"]}
    assert bridge & _consumed_tokens(planner) & expanded
