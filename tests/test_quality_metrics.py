from pathlib import Path

import pytest

from context_search_tool.models import RetrievalResult
from context_search_tool.quality.cases import (
    ExpectedAnyGroup,
    Gate,
    Matcher,
    Outranks,
    PreferredRank,
    QualityCase,
    TopKMatcher,
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


def test_expected_top5_min_informational_and_cross_language_metrics() -> None:
    case = QualityCase(
        case_id="edge-metrics",
        query="edge",
        tags=("cross_language",),
        gate=Gate.INFORMATIONAL,
        expected_top_k=(
            _expected("src/A.java", 5),
            _expected("src/B.java", 5),
        ),
        expected_top5_min=2,
    )

    evaluation = evaluate_case(case, [_result("src/A.java")], latency_ms=3)

    assert evaluation.status == "informational"
    assert evaluation.metrics["cross_language_success"] is True
    assert any("expected_top5_min" in failure for failure in evaluation.failures)


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
