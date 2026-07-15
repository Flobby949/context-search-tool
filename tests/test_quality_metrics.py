import time
from dataclasses import replace
from pathlib import Path

import pytest

import context_search_tool.quality.cases as quality_cases
import context_search_tool.quality.metrics as quality_metrics
from context_search_tool.config import DEFAULT_CONFIG
from context_search_tool.context_pack import (
    CONTEXT_GROUPS,
    CONTEXT_PACK_SCHEMA_VERSION,
    ContextBudget,
    ContextExcerpt,
    ContextItem,
    ContextPack,
    Omission,
    ReadinessConfidence,
    build_context_pack,
    canonical_context_pack_bytes,
    resolve_context_pack_options,
)
from context_search_tool.models import RetrievalResult, SemanticMatch
from context_search_tool.quality.aggregate import aggregate_cases
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
from context_search_tool.retrieval import QueryBundle, evidence_anchor_top_k
from context_search_tool.quality.metrics import (
    CaseEvaluation,
    evaluate_case,
    normalize_results,
)


def _result(
    path: str,
    score: float = 1.0,
    score_parts: dict[str, float] | None = None,
    reasons: list[str] | None = None,
    *,
    semantic_matches: list[SemanticMatch] | None = None,
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
        semantic_matches=list(semantic_matches or []),
    )


def _expected(path: str, top_k: int = 5) -> TopKMatcher:
    return TopKMatcher(Matcher(path=path), top_k)


def _context_item(item_id: str, path: str, group: str) -> ContextItem:
    index = int(item_id.rsplit(":", 1)[1])
    role = {
        "entrypoints": "entrypoint",
        "implementations": "service",
        "related_types": "data_type",
        "tests": "test",
        "configs_docs": "doc",
        "supporting": "source",
    }[group]
    content = f"public fixture for {path}"
    return ContextItem(
        id=f"item:{index}",
        file_path=path,
        group=group,
        role=role,
        classification_basis="fallback",
        source_kind="result",
        retrieval_rank=index,
        relevance_score=1.0,
        reasons=(),
        matched_need_ids=(),
        excerpts=(
            ContextExcerpt(
                start_line=1,
                end_line=1,
                content=content,
                content_bytes=len(content.encode("utf-8")),
                truncated=False,
            ),
        ),
    )


def _context_pack(
    items: tuple[ContextItem, ...] = (),
    *,
    status: str | None = None,
    confidence: str | None = None,
    truncated: bool = False,
    reported_pack_bytes: int | None = None,
) -> ContextPack:
    if not items and confidence in {"medium", "high"}:
        items = (_context_item("item:0", "src/Fixture.java", "supporting"),)
    if truncated and items:
        first = items[0]
        excerpt = replace(first.excerpts[0], truncated=True)
        items = (replace(first, excerpts=(excerpt,)), *items[1:])
    if status is None:
        status = "ready" if items else "empty"
    omissions: tuple[Omission, ...] = ()
    omitted_count = 0
    budget_exhausted = truncated
    if confidence == "low" and not items:
        status = "partial"
        omissions = (
            Omission(
                file_path="src/Omitted.java",
                group="supporting",
                reason="lower priority than selected evidence under the context budget",
                matched_need_ids=(),
            ),
        )
        omitted_count = 1
        budget_exhausted = True
    if confidence is None:
        confidence = "medium" if items else "none"
    reasons = {
        "none": ("no usable retrieval evidence",),
        "low": ("no evidence item fits the context budget",),
        "medium": (
            "all required evidence is selected",
            "protected original-direct evidence is absent",
        ),
        "high": (
            "all required evidence is selected",
            "protected original-direct evidence is present",
        ),
    }[confidence]
    content_bytes = sum(
        excerpt.content_bytes for item in items for excerpt in item.excerpts
    )
    groups = {
        group: tuple(item.id for item in items if item.group == group)
        for group in CONTEXT_GROUPS
    }
    pack = ContextPack(
        schema_version=CONTEXT_PACK_SCHEMA_VERSION,
        status=status,
        items=items,
        groups=groups,
        reading_order=tuple(item.id for item in items),
        evidence_needs=(),
        missing_evidence=(),
        next_queries=(),
        omissions=omissions,
        confidence=ReadinessConfidence(level=confidence, reasons=reasons),
        budget=ContextBudget(
            max_items=16,
            max_excerpts_per_item=2,
            max_excerpt_bytes=4096,
            max_item_content_bytes=8192,
            max_total_content_bytes=49152,
            max_pack_bytes=65536,
            included_items=len(items),
            included_excerpts=sum(len(item.excerpts) for item in items),
            content_bytes=content_bytes,
            pack_bytes=0,
            truncated_item_count=int(truncated and bool(items)),
            omitted_item_count=omitted_count,
            budget_exhausted=budget_exhausted,
        ),
    )
    canonical_size = len(canonical_context_pack_bytes(pack))
    return replace(
        pack,
        budget=replace(
            pack.budget,
            pack_bytes=(
                canonical_size
                if reported_pack_bytes is None
                else reported_pack_bytes
            ),
        ),
    )


def _built_context_pack(query: str, *, matched: bool) -> ContextPack:
    subject = query.removesuffix(" config")
    results = (
        [
            _result(
                f"config/application-{subject}.properties",
                reasons=["fixture"],
            )
        ]
        if matched
        else []
    )
    if results:
        results[0] = replace(
            results[0],
            end_line=1,
            content=f"{subject} datasource config",
        )
    options = resolve_context_pack_options(
        DEFAULT_CONFIG,
        context_lines=None,
        max_evidence_anchors=evidence_anchor_top_k(
            DEFAULT_CONFIG.retrieval.final_top_k
        ),
    )
    return build_context_pack(QueryBundle(query, [], results, []), options)


def _raw_evaluation(
    *,
    status: str = "pass",
    failures: list[str] | None = None,
) -> CaseEvaluation:
    return CaseEvaluation(
        case_id="context",
        status=status,
        metrics={"latency_ms": 11, "result_count": 1},
        failures=list(failures or []),
        top_results=[{"rank": 1, "path": "src/Raw.java"}],
    )


def test_evaluate_context_pack_adds_metrics_and_deterministic_failures() -> None:
    case = QualityCase(
        case_id="context",
        query="controller implementation",
        mode="context_pack",
        expected_context_groups={
            "entrypoints": (
                Matcher(path="src/MissingController.java"),
                Matcher(glob="src/**/*Controller.java"),
            ),
            "implementations": (Matcher(contains="Repository"),),
        },
        expected_pack_status="partial",
        minimum_context_confidence="high",
    )
    pack = _context_pack(
        (
            _context_item("result:0", "src/web/AppController.java", "entrypoints"),
            _context_item(
                "result:1",
                "src/data/UserRepository.java",
                "implementations",
            ),
            _context_item("result:2", "docs/README.md", "configs_docs"),
        ),
    )
    raw = _raw_evaluation()

    evaluation = quality_metrics.evaluate_context_pack(case, pack, raw)

    assert evaluation.metrics["context_completeness"] == pytest.approx(2 / 3)
    assert set(evaluation.metrics) - set(raw.metrics) == {
        "context_completeness",
        "evidence_need_count",
        "required_need_count",
        "matched_required_need_count",
        "evidence_need_completeness",
        "pack_bytes",
        "content_bytes",
        "truncated_item_count",
        "omitted_item_count",
    }
    assert evaluation.metrics["evidence_need_count"] == 0
    assert evaluation.metrics["required_need_count"] == 0
    assert evaluation.metrics["matched_required_need_count"] == 0
    assert evaluation.metrics["evidence_need_completeness"] is None
    assert evaluation.metrics["pack_bytes"] == len(canonical_context_pack_bytes(pack))
    assert evaluation.metrics["content_bytes"] == pack.budget.content_bytes
    assert evaluation.metrics["truncated_item_count"] == 0
    assert evaluation.metrics["omitted_item_count"] == 0
    assert evaluation.metrics["latency_ms"] == 11
    assert evaluation.metrics["result_count"] == 1
    assert evaluation.top_results == raw.top_results
    assert evaluation.failures == [
        "expected_context_groups missing in entrypoints: src/MissingController.java",
        "expected_pack_status expected partial, got ready",
        "minimum_context_confidence expected high, got medium",
    ]
    assert evaluation.status == "fail"


def test_context_matchers_use_path_glob_and_contains_in_declared_group() -> None:
    case = QualityCase(
        case_id="matcher-semantics",
        query="service",
        mode="context_pack",
        expected_context_groups={
            "implementations": (
                Matcher(path="src/Exact.py"),
                Matcher(glob="src/**/Service*.py"),
                Matcher(contains="Repository"),
            )
        },
    )
    pack = _context_pack(
        (
            _context_item("result:0", "src/Exact.py", "implementations"),
            _context_item("result:1", "src/pkg/ServiceImpl.py", "implementations"),
            _context_item("result:2", "src/data/Repository.py", "implementations"),
        )
    )

    evaluation = quality_metrics.evaluate_context_pack(
        case,
        pack,
        _raw_evaluation(),
    )

    assert evaluation.metrics["context_completeness"] == 1.0
    assert evaluation.failures == []


def test_context_item_in_wrong_group_does_not_satisfy_expected_pair() -> None:
    case = QualityCase(
        case_id="wrong-group",
        query="controller",
        mode="context_pack",
        expected_context_groups={
            "entrypoints": (Matcher(path="src/AppController.java"),)
        },
    )
    pack = _context_pack(
        (
            _context_item(
                "result:0",
                "src/AppController.java",
                "implementations",
            ),
        )
    )

    evaluation = quality_metrics.evaluate_context_pack(
        case,
        pack,
        _raw_evaluation(),
    )

    assert evaluation.metrics["context_completeness"] == 0.0
    assert evaluation.failures == [
        "expected_context_groups missing in entrypoints: src/AppController.java"
    ]


def test_multiple_matching_pack_paths_do_not_overcount_expected_pair() -> None:
    case = QualityCase(
        case_id="duplicates",
        query="controller",
        mode="context_pack",
        expected_context_groups={
            "entrypoints": (Matcher(glob="src/*Controller.java"),)
        },
    )
    pack = _context_pack(
        (
            _context_item("result:0", "src/AppController.java", "entrypoints"),
            _context_item("result:1", "src/AdminController.java", "entrypoints"),
        )
    )

    evaluation = quality_metrics.evaluate_context_pack(
        case,
        pack,
        _raw_evaluation(),
    )

    assert evaluation.metrics["context_completeness"] == 1.0


def test_no_expected_context_pairs_records_null_completeness() -> None:
    case = QualityCase(
        case_id="no-pairs",
        query="context",
        mode="context_pack",
    )

    evaluation = quality_metrics.evaluate_context_pack(
        case,
        _context_pack(),
        _raw_evaluation(),
    )

    assert evaluation.metrics["context_completeness"] is None


@pytest.mark.parametrize(
    ("gate", "expected_status"),
    [
        (Gate.REQUIRED, "fail"),
        (Gate.KNOWN_GAP, "known_gap"),
        (Gate.INFORMATIONAL, "informational"),
    ],
)
def test_context_failures_retain_gate_status_semantics(
    gate: Gate,
    expected_status: str,
) -> None:
    case = QualityCase(
        case_id="gated-context",
        query="controller",
        mode="context_pack",
        gate=gate,
        expected_context_groups={
            "entrypoints": (Matcher(path="src/AppController.java"),)
        },
    )
    raw = evaluate_case(case, [], latency_ms=1)

    evaluation = quality_metrics.evaluate_context_pack(
        case,
        _context_pack(),
        raw,
    )

    assert evaluation.status == expected_status
    assert evaluation.failures == [
        "expected_context_groups missing in entrypoints: src/AppController.java"
    ]


@pytest.mark.parametrize(
    ("actual", "fails"),
    [("none", True), ("low", True), ("medium", False), ("high", False)],
)
def test_minimum_context_confidence_uses_declared_rank(
    actual: str,
    fails: bool,
) -> None:
    case = QualityCase(
        case_id="confidence",
        query="confidence",
        mode="context_pack",
        minimum_context_confidence="medium",
    )

    evaluation = quality_metrics.evaluate_context_pack(
        case,
        _context_pack(confidence=actual),
        _raw_evaluation(),
    )

    assert bool(evaluation.failures) is fails


def test_context_evaluation_appends_after_raw_failures() -> None:
    case = QualityCase(
        case_id="raw-and-context",
        query="controller",
        mode="context_pack",
        expected_top_k=(_expected("src/RawExpected.java", 5),),
        expected_context_groups={
            "entrypoints": (Matcher(path="src/ContextExpected.java"),)
        },
    )
    raw = evaluate_case(case, [], latency_ms=5)

    evaluation = quality_metrics.evaluate_context_pack(
        case,
        _context_pack(),
        raw,
    )

    assert evaluation.failures == [
        "expected_top_k missing within top 5: src/RawExpected.java",
        "expected_context_groups missing in entrypoints: src/ContextExpected.java",
    ]
    assert evaluation.metrics["latency_ms"] == raw.metrics["latency_ms"]
    assert evaluation.top_results == raw.top_results


@pytest.mark.parametrize(
    ("matched", "expected_completeness"),
    [(True, 1.0), (False, 0.0)],
)
def test_expected_need_match_uses_public_subject_and_matched_item_ids(
    matched: bool,
    expected_completeness: float,
) -> None:
    pack = _built_context_pack("postgresql config", matched=matched)
    case = QualityCase(
        case_id="need-match",
        query="postgresql config",
        mode="context_pack",
        expected_need_matches=(
            quality_cases.ExpectedNeedMatch(
                category="configs_docs",
                subject="POSTGRESQL",
                required=True,
                matched=matched,
            ),
        ),
    )

    evaluation = quality_metrics.evaluate_context_pack(
        case,
        pack,
        _raw_evaluation(),
    )

    assert evaluation.failures == []
    assert evaluation.metrics["evidence_need_count"] == 1
    assert evaluation.metrics["required_need_count"] == 1
    assert evaluation.metrics["matched_required_need_count"] == int(matched)
    assert evaluation.metrics["evidence_need_completeness"] == expected_completeness


def test_expected_need_match_uses_nfc_canonical_equivalence() -> None:
    evaluation = quality_metrics.evaluate_context_pack(
        QualityCase(
            case_id="unicode-need-match",
            query="café config",
            mode="context_pack",
            expected_need_matches=(
                quality_cases.ExpectedNeedMatch(
                    category="configs_docs",
                    subject="cafe\u0301",
                    required=True,
                    matched=True,
                ),
            ),
        ),
        _built_context_pack("café config", matched=True),
        _raw_evaluation(),
    )

    assert evaluation.failures == []


def test_programmatic_unsafe_regex_is_rejected_before_runtime_search() -> None:
    started = time.perf_counter()

    with pytest.raises(
        ValueError,
        match="unsupported or unsafe regular expression syntax",
    ):
        quality_metrics.evaluate_context_pack(
            QualityCase(
                case_id="unsafe-runtime-regex",
                query="postgresql config",
                mode="context_pack",
                forbidden_next_query_patterns=("(a+)+$",),
            ),
            _built_context_pack("postgresql config", matched=False),
            _raw_evaluation(),
        )

    assert time.perf_counter() - started < 0.5


def test_v2_numeric_metrics_aggregate_while_null_context_completeness_is_excluded() -> None:
    evaluation = quality_metrics.evaluate_context_pack(
        QualityCase(
            case_id="aggregate-v2",
            query="postgresql config",
            mode="context_pack",
        ),
        _built_context_pack("postgresql config", matched=True),
        _raw_evaluation(),
    )

    aggregate = aggregate_cases(
        [
            {
                "repo_key": "repo",
                "case_id": "aggregate-v2",
                "tags": [],
                "status": evaluation.status,
                "attempted": True,
                "metrics": evaluation.metrics,
            }
        ],
        [{"repo_key": "repo", "config": {}}],
        "p2_context_pack",
    )
    overall = aggregate["metrics"]["overall"]

    assert "context_completeness" not in overall
    for metric_name in (
        "evidence_need_count",
        "required_need_count",
        "matched_required_need_count",
        "evidence_need_completeness",
        "pack_bytes",
        "content_bytes",
        "truncated_item_count",
        "omitted_item_count",
    ):
        assert overall[metric_name]["count"] == 1


def test_expected_need_mismatch_names_only_bounded_expected_subject() -> None:
    pack = _built_context_pack("postgresql config", matched=True)
    case = QualityCase(
        case_id="need-mismatch",
        query="postgresql config",
        mode="context_pack",
        expected_need_matches=(
            quality_cases.ExpectedNeedMatch(
                category="configs_docs",
                subject="postgresql",
                required=True,
                matched=False,
            ),
        ),
    )

    evaluation = quality_metrics.evaluate_context_pack(
        case,
        pack,
        _raw_evaluation(),
    )

    assert evaluation.status == "fail"
    assert evaluation.failures == [
        "expected_need_matches mismatch for configs_docs: postgresql"
    ]
    assert "datasource" not in " ".join(evaluation.failures)


def test_pack_limits_check_reported_and_fresh_canonical_bytes() -> None:
    pack = _context_pack(
        (_context_item("item:0", "src/Fixture.java", "supporting"),)
    )
    canonical_size = len(canonical_context_pack_bytes(pack))
    stale_low = replace(pack, budget=replace(pack.budget, pack_bytes=1))
    stale_high = replace(
        pack,
        budget=replace(pack.budget, pack_bytes=canonical_size + 1),
    )

    canonical_failure = quality_metrics.evaluate_context_pack(
        QualityCase(
            case_id="canonical-size",
            query="fixture",
            mode="context_pack",
            maximum_pack_bytes=canonical_size - 1,
        ),
        stale_low,
        _raw_evaluation(),
    )
    reported_failure = quality_metrics.evaluate_context_pack(
        QualityCase(
            case_id="reported-size",
            query="fixture",
            mode="context_pack",
            maximum_pack_bytes=canonical_size,
        ),
        stale_high,
        _raw_evaluation(),
    )

    assert canonical_failure.failures == [
        f"maximum_pack_bytes exceeded by canonical pack: {canonical_size} > {canonical_size - 1}"
    ]
    assert reported_failure.failures == [
        f"maximum_pack_bytes exceeded by reported pack: {canonical_size + 1} > {canonical_size}"
    ]


def test_truncation_limit_and_forbidden_patterns_gate_only_next_query_text() -> None:
    truncated = _context_pack(
        (_context_item("item:0", "src/Fixture.java", "supporting"),),
        truncated=True,
    )
    truncation_evaluation = quality_metrics.evaluate_context_pack(
        QualityCase(
            case_id="truncated",
            query="fixture",
            mode="context_pack",
            maximum_truncated_items=0,
        ),
        truncated,
        _raw_evaluation(),
    )
    missing = _built_context_pack("postgresql config", matched=False)
    purpose_only = quality_metrics.evaluate_context_pack(
        QualityCase(
            case_id="purpose-only",
            query="postgresql config",
            mode="context_pack",
            forbidden_next_query_patterns=("missing",),
        ),
        missing,
        _raw_evaluation(),
    )
    forbidden_query = quality_metrics.evaluate_context_pack(
        QualityCase(
            case_id="forbidden-query",
            query="postgresql config",
            mode="context_pack",
            forbidden_next_query_patterns=(r"POSTGRESQL\s+CONFIGURATION",),
        ),
        missing,
        _raw_evaluation(),
    )

    assert truncation_evaluation.failures == [
        "maximum_truncated_items exceeded: 1 > 0"
    ]
    assert purpose_only.failures == []
    assert forbidden_query.failures == [
        r"forbidden_next_query_patterns matched: POSTGRESQL\s+CONFIGURATION"
    ]


def test_normalize_results_deduplicates_paths_and_compacts_ranks() -> None:
    results = [
        _result(
            "src\\Controller.java",
            0.9,
            {"vector": 0.7},
            ["first"],
            semantic_matches=[SemanticMatch("planner:0", 0.9)],
        ),
        _result("src/Service.java", 0.8),
        _result(
            "src/Controller.java",
            0.7,
            {"vector": 0.5},
            ["duplicate"],
            semantic_matches=[SemanticMatch("planner:1", 0.7)],
        ),
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
    assert normalized[0].semantic_matches == [SemanticMatch("planner:0", 0.9)]


def test_normalize_results_copies_mutable_provenance() -> None:
    score_parts = {"vector": 0.7}
    reasons = ["first"]
    result = _result(
        "src/Controller.java",
        0.9,
        score_parts,
        reasons,
        semantic_matches=[SemanticMatch("planner:0", 0.9)],
    )

    normalized = normalize_results([result])
    score_parts["vector"] = 0.1
    reasons.append("mutated")
    result.semantic_matches.append(SemanticMatch("planner:1", 0.8))

    assert normalized[0].score_parts == {"vector": 0.7}
    assert normalized[0].reasons == ["first"]
    assert normalized[0].semantic_matches == [SemanticMatch("planner:0", 0.9)]


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


def test_informational_metrics_are_casefolded_unique_and_fixed_denominator() -> None:
    case = QualityCase(
        case_id="embedding-ab",
        query="黑白名单管理",
        gate=Gate.INFORMATIONAL,
        metric_k=12,
        relevance_matchers=(
            Matcher(contains="whitelist"),
            Matcher(contains="blacklist"),
        ),
        noise_matchers=(Matcher(contains="region"),),
    )
    results = [
        _result("src/WhitelistManager.java"),
        _result("src/WhitelistManager.java"),
        _result("src/BLACKLISTService.java"),
        _result("src/RegionService.java"),
    ]
    evaluation = evaluate_case(case, results, latency_ms=4)
    assert evaluation.status == "informational"
    assert evaluation.metrics["precision_at_12"] == pytest.approx(2 / 12)
    assert evaluation.metrics["noise_top12"] == 1
    assert "noise_top12_measurement" not in evaluation.metrics
    assert evaluation.metrics["mrr"] == 1.0
    assert evaluation.failures == []


def test_informational_mrr_uses_full_result_list_beyond_metric_k() -> None:
    case = QualityCase(
        case_id="full-list-mrr",
        query="relevant service",
        gate=Gate.INFORMATIONAL,
        metric_k=2,
        relevance_matchers=(Matcher(contains="relevant"),),
    )
    results = [
        _result("src/Alpha.java"),
        _result("src/Beta.java"),
        _result("src/RelevantService.java"),
    ]

    evaluation = evaluate_case(case, results, latency_ms=4)

    assert evaluation.metrics["precision_at_2"] == 0.0
    assert evaluation.metrics["mrr"] == pytest.approx(1 / 3)
    assert evaluation.status == "informational"
    assert evaluation.failures == []


@pytest.mark.parametrize(
    ("metric_k", "measurement_noise_key"),
    [(5, "noise_top5_measurement"), (10, "noise_top10_measurement")],
)
def test_measurement_noise_does_not_overwrite_gate_noise(
    metric_k: int,
    measurement_noise_key: str,
) -> None:
    case = QualityCase(
        case_id=f"measurement-noise-{metric_k}",
        query="noise collision",
        gate=Gate.INFORMATIONAL,
        metric_k=metric_k,
        relevance_matchers=(Matcher(contains="relevant"),),
        noise_matchers=(Matcher(contains="measurement-noise"),),
        absent_top_k=(
            TopKMatcher(Matcher(path="src/GateNoise.java"), metric_k),
        ),
    )
    results = [
        _result("src/RelevantMeasurement-Noise.java"),
        _result("src/Measurement-Noise.java"),
        _result("src/GateNoise.java"),
    ]

    evaluation = evaluate_case(case, results, latency_ms=4)

    assert evaluation.metrics[f"noise_top{metric_k}"] == 1
    assert evaluation.metrics[measurement_noise_key] == 2
    assert evaluation.metrics[f"precision_at_{metric_k}"] == pytest.approx(
        1 / metric_k
    )


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
            "semantic_matches": [],
        }
    ]


def test_normalized_top_results_preserve_semantic_matches() -> None:
    evaluation = evaluate_case(
        QualityCase(
            case_id="semantic",
            query="query",
            expected_top_k=(_expected("src/App.java", 1),),
        ),
        [
            _result(
                "src/App.java",
                semantic_matches=[SemanticMatch("planner:0", 0.84)],
            )
        ],
        latency_ms=10,
    )

    assert evaluation.top_results[0]["semantic_matches"] == [
        {"variant_id": "planner:0", "score": 0.84}
    ]
