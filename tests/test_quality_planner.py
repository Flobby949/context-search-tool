from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

from context_search_tool.models import QueryPlan
from context_search_tool.quality.cases import load_quality_fixture
from context_search_tool.quality.runner import run_quality_fixture
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


@pytest.fixture(scope="module")
def real_planner_report() -> dict:
    raw_repo = os.environ.get("CST_PLANNER_REQUESTS_REPO")
    if not raw_repo or not Path(raw_repo).is_dir():
        pytest.skip("CST_PLANNER_REQUESTS_REPO is not configured")
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
