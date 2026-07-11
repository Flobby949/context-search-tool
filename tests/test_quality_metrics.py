from pathlib import Path

import pytest

from context_search_tool.models import RetrievalResult
from context_search_tool.quality.cases import (
    AtLeastTopKGroup,
    ExpectedAnyGroup,
    Gate,
    Matcher,
    Outranks,
    PreferredRank,
    QualityCase,
    TopKMatcher,
    adapt_legacy_query_case,
)
from context_search_tool.quality.metrics import evaluate_case, normalize_results


def _result(
    path: str,
    score: float = 1.0,
    score_parts: dict[str, float] | None = None,
    reasons: list[str] | None = None,
) -> RetrievalResult:
    return RetrievalResult(
        file_path=Path(path),
        start_line=1,
        end_line=10,
        content="content",
        score=score,
        score_parts=score_parts or {},
        reasons=reasons or [],
        followup_keywords=[],
    )


def _expected(path: str, top_k: int = 5) -> TopKMatcher:
    return TopKMatcher(Matcher(path=path), top_k)


def test_normalize_results_deduplicates_paths_and_compacts_ranks() -> None:
    results = [
        _result("src\\Controller.java", 0.9, {"vector": 0.7}, ["first"]),
        _result("src/Service.java", 0.8),
        _result("src/Controller.java", 0.7, {"vector": 0.5}, ["duplicate"]),
        _result("src/Repository.java", 0.6),
    ]

    normalized = normalize_results(results)

    assert [(item.rank, item.path) for item in normalized] == [
        (1, "src/Controller.java"),
        (2, "src/Service.java"),
        (3, "src/Repository.java"),
    ]
    assert normalized[0].score == 0.9
    assert normalized[0].score_parts == {"vector": 0.7}
    assert normalized[0].reasons == ["first"]


def test_normalize_results_copies_score_parts_and_reasons() -> None:
    score_parts = {"vector": 0.7}
    reasons = ["first"]
    result = _result("src/Controller.java", 0.9, score_parts, reasons)

    normalized = normalize_results([result])
    score_parts["vector"] = 0.1
    reasons.append("mutated")

    assert normalized[0].score_parts == {"vector": 0.7}
    assert normalized[0].reasons == ["first"]


def test_evaluate_case_calculates_core_metrics_for_expected_top_k() -> None:
    case = QualityCase(
        case_id="controller-flow",
        query="controller service flow",
        expected_top_k=(
            _expected("src/Controller.java", 5),
            _expected("src/Service.java", 5),
        ),
    )
    results = [_result("src/Other.java", 0.9), _result("src/Service.java", 0.8)]

    evaluation = evaluate_case(case, results, latency_ms=12)

    assert evaluation.case_id == "controller-flow"
    assert evaluation.status == "fail"
    assert evaluation.metrics["hit_at_1"] is False
    assert evaluation.metrics["hit_at_3"] is True
    assert evaluation.metrics["recall_at_5"] == pytest.approx(0.5)
    assert evaluation.metrics["mrr"] == pytest.approx(0.5)
    assert evaluation.metrics["latency_ms"] == 12
    assert evaluation.metrics["expected_coverage_top5"] == {
        "count": 1,
        "ratio": pytest.approx(0.5),
    }
    assert evaluation.failures


def test_expected_any_group_counts_as_one_relevance_target() -> None:
    case = QualityCase(
        case_id="service-impl",
        query="service implementation",
        expected_any_top_k=(
            ExpectedAnyGroup(
                matchers=(
                    Matcher(path="src/Service.java"),
                    Matcher(path="src/ServiceImpl.java"),
                ),
                top_k=5,
            ),
        ),
    )

    evaluation = evaluate_case(case, [_result("src/ServiceImpl.java")], latency_ms=7)

    assert evaluation.status == "pass"
    assert evaluation.metrics["hit_at_1"] is True
    assert evaluation.metrics["recall_at_5"] == pytest.approx(1.0)
    assert evaluation.metrics["mrr"] == pytest.approx(1.0)
    assert evaluation.metrics["expected_coverage_top5"] == {
        "count": 1,
        "ratio": pytest.approx(1.0),
    }


def test_at_least_group_gates_n_of_m_but_counts_each_relevance_target() -> None:
    group = AtLeastTopKGroup(
        matchers=tuple(Matcher(path=f"src/{name}.java") for name in "ABCDE"),
        top_k=5,
        min_matches=2,
    )
    case = QualityCase(
        case_id="two-of-five",
        query="auth",
        expected_at_least_top_k=(group,),
    )
    passes = evaluate_case(
        case, [_result("src/A.java"), _result("src/C.java")], latency_ms=1
    )
    fails = evaluate_case(case, [_result("src/A.java")], latency_ms=1)
    assert passes.status == "pass"
    assert passes.failures == []
    assert passes.metrics["recall_at_5"] == pytest.approx(2 / 5)
    assert fails.status == "fail"
    assert fails.failures == [
        "expected_at_least_top_k expected 2 within top 5, found 1"
    ]


def test_zero_minimum_records_relevance_without_failure() -> None:
    case = QualityCase(
        case_id="zero-minimum",
        query="alarm",
        expected_at_least_top_k=(
            AtLeastTopKGroup(
                matchers=(Matcher(path="src/AlarmService.java"),),
                top_k=5,
                min_matches=0,
            ),
        ),
    )
    evaluation = evaluate_case(case, [], latency_ms=1)
    assert evaluation.status == "pass"
    assert evaluation.metrics["recall_at_5"] == 0.0


def test_known_gap_status_preserves_failures() -> None:
    case = QualityCase(
        case_id="known-gap",
        query="missing target",
        gate=Gate.KNOWN_GAP,
        expected_top_k=(_expected("src/Missing.java", 5),),
    )

    evaluation = evaluate_case(case, [], latency_ms=1)

    assert evaluation.status == "known_gap"
    assert evaluation.failures


def test_preferred_rank_entrypoint_and_absent_noise_metrics_fail_case() -> None:
    case = QualityCase(
        case_id="entrypoint-rank",
        query="entrypoint",
        preferred_rank=(
            PreferredRank(
                matcher=Matcher(path="src/Entrypoint.java"),
                top_k=5,
                max_rank=1,
                role="entrypoint",
            ),
        ),
        absent_top_k=(_expected("src/Generated.java", 5),),
    )
    results = [
        _result("src/Other.java"),
        _result("src/Entrypoint.java"),
        _result("src/Generated.java"),
    ]

    evaluation = evaluate_case(case, results, latency_ms=3)

    assert evaluation.status == "fail"
    assert evaluation.metrics["entrypoint_rank"] == 2
    assert evaluation.metrics["preferred_rank_pass"] is False
    assert evaluation.metrics["noise_top5"] == 1


def test_preferred_rank_fails_when_target_is_outside_top_k() -> None:
    case = QualityCase(
        case_id="preferred-top-k",
        query="preferred",
        preferred_rank=(
            PreferredRank(
                matcher=Matcher(path="src/Preferred.java"),
                top_k=3,
                max_rank=5,
            ),
        ),
    )
    results = [
        _result("src/A.java"),
        _result("src/B.java"),
        _result("src/C.java"),
        _result("src/Preferred.java"),
    ]

    evaluation = evaluate_case(case, results, latency_ms=3)

    assert evaluation.status == "fail"
    assert evaluation.metrics["preferred_rank_pass"] is False
    assert evaluation.failures


def test_noise_metrics_count_unique_paths_matched_by_eligible_absent_assertions() -> None:
    case = QualityCase(
        case_id="noise-glob",
        query="noise",
        absent_top_k=(
            TopKMatcher(Matcher(glob="generated/*.java"), 5),
            TopKMatcher(Matcher(glob="legacy/*.java"), 10),
        ),
    )
    results = [
        _result("generated/A.java"),
        _result("generated/B.java"),
        _result("generated\\A.java"),
        _result("src/Real.java"),
        _result("legacy/A.java"),
        _result("legacy/B.java"),
    ]

    evaluation = evaluate_case(case, results, latency_ms=3)

    assert evaluation.metrics["noise_top5"] == 2
    assert evaluation.metrics["noise_top10"] == 4


def test_informational_cross_language_metrics_without_legacy_minimum() -> None:
    case = QualityCase(
        case_id="cross-language-info",
        query="数据看板",
        tags=("cross_language",),
        gate=Gate.INFORMATIONAL,
        expected_top_k=(TopKMatcher(Matcher(path="src/Dashboard.java"), 5),),
    )

    evaluation = evaluate_case(case, [_result("src/Dashboard.java")], latency_ms=1)

    assert evaluation.status == "informational"
    assert evaluation.metrics["cross_language_success"] is True


def test_anchor_expected_passes_when_anchor_path_is_present() -> None:
    case = QualityCase(
        case_id="anchor-pass",
        query="anchor",
        anchor_expected=("src/Controller.java",),
    )

    evaluation = evaluate_case(
        case,
        [],
        latency_ms=1,
        anchor_paths=["./src\\Controller.java"],
    )

    assert evaluation.status == "pass"
    assert evaluation.failures == []


def test_anchor_expected_fails_when_anchor_path_is_missing() -> None:
    case = QualityCase(
        case_id="anchor-fail",
        query="anchor",
        anchor_expected=("src/Controller.java",),
    )

    evaluation = evaluate_case(
        case,
        [],
        latency_ms=1,
        anchor_paths=["src/Service.java"],
    )

    assert evaluation.status == "fail"
    assert evaluation.failures == ["anchor_expected missing: src/Controller.java"]


def test_anchor_expected_is_ignored_without_anchor_paths() -> None:
    case = QualityCase(
        case_id="anchor-direct-unit",
        query="anchor",
        anchor_expected=("src/Controller.java",),
    )

    evaluation = evaluate_case(case, [], latency_ms=1)

    assert evaluation.status == "pass"


def test_expected_anchor_must_remain_outside_ranked_results() -> None:
    case = QualityCase(
        case_id="anchor-separation",
        query="readme",
        anchor_expected=("README.md",),
    )
    evaluation = evaluate_case(
        case,
        [_result("README.md")],
        latency_ms=1,
        anchor_paths=["README.md"],
    )
    assert evaluation.status == "fail"
    assert evaluation.failures == [
        "anchor_expected must remain outside ranked results: README.md"
    ]


def test_legacy_forbidden_window_matches_absolute_rank_semantics() -> None:
    case = adapt_legacy_query_case(
        {
            "id": "legacy-window",
            "query": "fund service",
            "expected_top_k": [{"path": "src/FundService.go", "top_k": 5}],
            "forbidden_above": [
                {"glob": "legacy/**/*.java", "top_k": 5, "max_rank": 2}
            ],
        }
    )
    fails = evaluate_case(
        case,
        [_result("src/FundService.go"), _result("legacy/pkg/Old.java")],
        latency_ms=1,
    )
    passes = evaluate_case(
        case,
        [
            _result("src/FundService.go"),
            _result("src/Other.go"),
            _result("legacy/pkg/Old.java"),
        ],
        latency_ms=1,
    )
    assert fails.status == "fail"
    assert fails.failures == [
        "absent_top_k present within top 2: legacy/**/*.java"
    ]
    assert passes.status == "pass"


def test_outranks_and_forbidden_above_fail_when_noise_appears_first() -> None:
    source = Matcher(path="src/Real.java")
    noise = Matcher(path="src/Generated.java")
    case = QualityCase(
        case_id="noise-above-source",
        query="real implementation",
        outranks=(Outranks(source=source, noise=noise, top_k=5),),
        forbidden_above=(Outranks(source=source, noise=noise, top_k=5),),
    )
    results = [_result("src/Generated.java"), _result("src/Real.java")]

    evaluation = evaluate_case(case, results, latency_ms=2)

    assert evaluation.status == "fail"
    assert len(evaluation.failures) == 2


def test_top_results_payload_respects_limit() -> None:
    case = QualityCase(case_id="payload", query="payload")
    results = [
        _result("src/A.java", 0.9, {"semantic": 0.8}, ["best"]),
        _result("src/B.java", 0.7),
    ]

    evaluation = evaluate_case(case, results, latency_ms=4, top_result_limit=1)

    assert evaluation.top_results == [
        {
            "rank": 1,
            "path": "src/A.java",
            "score": 0.9,
            "score_parts": {"semantic": 0.8},
            "reasons": ["best"],
        }
    ]
