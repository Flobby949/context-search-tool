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
_SYNTHETIC_CASES = (
    ("java_spring_mini", "apply-audit-endpoint", ()),
    ("java_spring_mini", "audit-status-literal", ()),
    (
        "cross_language_dashboard",
        "dashboard-cross-language",
        ("cross_language",),
    ),
    ("cross_language_dashboard", "dashboard-controller-path", ()),
    (
        "embedding_ab",
        "access-validation-cross-language",
        ("cross_language",),
    ),
    (
        "embedding_ab",
        "blacklist-management-cross-language",
        ("cross_language",),
    ),
    ("embedding_ab", "order-service-symbol", ()),
)


def _case_index(report: dict) -> dict[tuple[str, str], dict]:
    return {
        (case["repo_key"], case["case_id"]): case
        for case in report["cases"]
    }


def _metric(report: dict, name: str, field: str) -> float:
    value = report["aggregate"]["metrics"]["overall"][name][field]
    assert isinstance(value, int | float)
    return float(value)


def _synthetic_report(profile: str) -> dict:
    is_hybrid = profile == "p1_hybrid_bge"
    cases = []
    for repo_key, case_id, tags in _SYNTHETIC_CASES:
        uses_hybrid = is_hybrid and "cross_language" in tags
        cases.append(
            {
                "repo_key": repo_key,
                "case_id": case_id,
                "gate": "required",
                "status": "pass",
                "planner": {"status": "ok" if is_hybrid else "disabled"},
                "variant_retrieval_status": (
                    "hybrid" if uses_hybrid else "original_only"
                ),
                "query_variants": [
                    {"variant_id": variant_id}
                    for variant_id in (
                        ("original", "planner:0")
                        if uses_hybrid
                        else ("original",)
                    )
                ],
                "tags": list(tags),
                "top_results": (
                    [
                        {
                            "semantic_matches": [
                                {"variant_id": "planner:0"}
                            ]
                        }
                    ]
                    if is_hybrid and case_id == "dashboard-cross-language"
                    else []
                ),
            }
        )
    return {
        "cases": cases,
        "aggregate": {
            "metrics": {
                "overall": {
                    "mrr": {"mean": 1.0},
                    "recall_at_5": {"mean": 1.0},
                    "entrypoint_top3": {"rate": 1.0},
                }
            }
        },
    }


def _synthetic_reports() -> dict[str, dict]:
    return {profile: _synthetic_report(profile) for profile in P1_PROFILES}


def _assert_phase_one_pair(vector: dict, hybrid: dict) -> None:
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
    assert all(
        case["variant_retrieval_status"] != "embedding_fallback"
        for case in hybrid_cases.values()
    ), "p1_hybrid_bge cannot use embedding fallback"

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
    _assert_phase_one_pair(
        p1_reports["p1_vector_bge"],
        p1_reports["p1_hybrid_bge"],
    )


def test_phase_one_pair_gate_accepts_valid_synthetic_reports() -> None:
    reports = _synthetic_reports()
    _assert_phase_one_pair(
        reports["p1_vector_bge"],
        reports["p1_hybrid_bge"],
    )


def test_phase_one_pair_gate_rejects_non_cross_language_embedding_fallback(
) -> None:
    reports = _synthetic_reports()
    hybrid_cases = _case_index(reports["p1_hybrid_bge"])
    hybrid_cases[("embedding_ab", "order-service-symbol")][
        "variant_retrieval_status"
    ] = "embedding_fallback"

    with pytest.raises(AssertionError, match="cannot use embedding fallback"):
        _assert_phase_one_pair(
            reports["p1_vector_bge"],
            reports["p1_hybrid_bge"],
        )
