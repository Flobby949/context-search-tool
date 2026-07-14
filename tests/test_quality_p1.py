from __future__ import annotations

import os
from pathlib import Path

import pytest

from context_search_tool.quality.runner import run_quality_fixture


CATALOG = (
    Path(__file__).parent
    / "fixtures"
    / "retrieval_quality"
    / "queries.json"
)
P1_PROFILES = ("p1_vector_bge", "p1_hybrid_bge")
RUN_P1_ACCEPTANCE = os.environ.get("CST_RUN_P1_ACCEPTANCE") == "1"


def _case_index(report: dict) -> dict[tuple[str, str], dict]:
    return {
        (case["repo_key"], case["case_id"]): case
        for case in report["cases"]
    }


def _metric(report: dict, name: str, field: str) -> float:
    value = report["aggregate"]["metrics"]["overall"][name][field]
    assert isinstance(value, int | float)
    return float(value)


@pytest.fixture(scope="module")
def p1_reports() -> dict[str, dict]:
    if not RUN_P1_ACCEPTANCE:
        pytest.skip("set CST_RUN_P1_ACCEPTANCE=1 to run local model acceptance")
    return {
        profile: run_quality_fixture(CATALOG, profile, None, None)
        for profile in P1_PROFILES
    }


@pytest.mark.slow
@pytest.mark.integration
def test_phase_one_vector_and_hybrid_profiles_close_together(
    p1_reports: dict[str, dict],
) -> None:
    vector = p1_reports["p1_vector_bge"]
    hybrid = p1_reports["p1_hybrid_bge"]
    vector_cases = _case_index(vector)
    hybrid_cases = _case_index(hybrid)

    assert set(vector_cases) == set(hybrid_cases)
    assert {
        key: case["gate"] for key, case in vector_cases.items()
    } == {
        key: case["gate"] for key, case in hybrid_cases.items()
    }
    assert len(vector_cases) == 7
    assert all(case["gate"] == "required" for case in vector_cases.values())
    assert all(case["status"] == "pass" for case in vector_cases.values())
    assert all(case["status"] == "pass" for case in hybrid_cases.values())

    for case in vector_cases.values():
        assert case["planner"]["status"] == "disabled"
        assert case["variant_retrieval_status"] == "original_only"
        assert case["query_variants"][0]["variant_id"] == "original"

    cross_language = [
        case
        for case in hybrid_cases.values()
        if "cross_language" in case["tags"]
    ]
    assert len(cross_language) == 3
    assert all(case["planner"]["status"] == "ok" for case in cross_language)
    assert all(
        case["variant_retrieval_status"] == "hybrid"
        for case in cross_language
    )
    dashboard = hybrid_cases[
        ("cross_language_dashboard", "dashboard-cross-language")
    ]
    assert dashboard["top_results"]
    assert any(
        match["variant_id"].startswith("planner:")
        for match in dashboard["top_results"][0]["semantic_matches"]
    )

    assert _metric(hybrid, "mrr", "mean") >= _metric(
        vector,
        "mrr",
        "mean",
    )
    assert _metric(hybrid, "recall_at_5", "mean") >= _metric(
        vector,
        "recall_at_5",
        "mean",
    )
    assert _metric(hybrid, "entrypoint_top3", "rate") >= _metric(
        vector,
        "entrypoint_top3",
        "rate",
    )
