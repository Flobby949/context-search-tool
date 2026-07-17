from __future__ import annotations

import json
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any

from context_search_tool.context_pack import (
    CONTEXT_GROUPS,
    ContextPack,
    canonical_context_pack_bytes,
)
from context_search_tool.models import RetrievalResult, SemanticMatch
from context_search_tool.quality.cases import (
    Gate,
    Matcher,
    QualityCase,
    _compile_safe_forbidden_next_query_pattern,
    _normalize_public_subject,
    normalize_result_path,
)

if TYPE_CHECKING:
    from context_search_tool.exploration.models import ExploredContext


@dataclass(frozen=True)
class NormalizedResult:
    rank: int
    path: str
    score: float
    score_parts: dict[str, float]
    reasons: list[str]
    semantic_matches: list[SemanticMatch]


@dataclass(frozen=True)
class CaseEvaluation:
    case_id: str
    status: str
    metrics: dict[str, Any]
    failures: list[str]
    top_results: list[dict[str, Any]]


@dataclass(frozen=True)
class _RelevanceTarget:
    matchers: tuple[Matcher, ...]


_CONFIDENCE_RANK = {"none": 0, "low": 1, "medium": 2, "high": 3}


def normalize_results(results: list[RetrievalResult]) -> list[NormalizedResult]:
    normalized: list[NormalizedResult] = []
    seen_paths: set[str] = set()

    for result in results:
        path = normalize_result_path(result.file_path.as_posix())
        if path in seen_paths:
            continue
        seen_paths.add(path)
        normalized.append(
            NormalizedResult(
                rank=len(normalized) + 1,
                path=path,
                score=result.score,
                score_parts=dict(result.score_parts),
                reasons=list(result.reasons),
                semantic_matches=list(result.semantic_matches),
            )
        )

    return normalized


def evaluate_case(
    case: QualityCase,
    results: list[RetrievalResult],
    latency_ms: int,
    top_result_limit: int = 10,
    anchor_paths: list[str] | None = None,
) -> CaseEvaluation:
    normalized = normalize_results(results)
    failures: list[str] = []

    targets = _relevance_targets(case)
    target_ranks = [_first_rank(normalized, target.matchers) for target in targets]

    for expected in case.expected_top_k:
        rank = _first_rank(normalized, (expected.matcher,))
        if rank is None or rank > expected.top_k:
            failures.append(
                f"expected_top_k missing within top {expected.top_k}: "
                f"{_matcher_label(expected.matcher)}"
            )

    for group in case.expected_any_top_k:
        rank = _first_rank(normalized, group.matchers)
        if rank is None or rank > group.top_k:
            failures.append(f"expected_any_top_k missing within top {group.top_k}")

    for group in case.expected_at_least_top_k:
        match_count = sum(
            1
            for matcher in group.matchers
            if _rank_within(_first_rank(normalized, (matcher,)), group.top_k)
        )
        if match_count < group.min_matches:
            failures.append(
                f"expected_at_least_top_k expected {group.min_matches} "
                f"within top {group.top_k}, found {match_count}"
            )

    coverage_top5_count = sum(1 for rank in target_ranks if _rank_within(rank, 5))

    preferred_rank_pass = True
    entrypoint_rank = None
    for preferred in case.preferred_rank:
        rank = _first_rank(normalized, (preferred.matcher,))
        if preferred.role == "entrypoint" and entrypoint_rank is None:
            entrypoint_rank = rank
        if (
            rank is None
            or rank > preferred.max_rank
            or rank > preferred.top_k
        ):
            preferred_rank_pass = False
            failures.append(
                f"preferred_rank failed top {preferred.top_k}/max rank "
                f"{preferred.max_rank}: "
                f"{_matcher_label(preferred.matcher)}"
            )

    for absent in case.absent_top_k:
        rank = _first_rank(normalized, (absent.matcher,))
        if rank is not None and rank <= absent.top_k:
            failures.append(
                f"absent_top_k present within top {absent.top_k}: "
                f"{_matcher_label(absent.matcher)}"
            )

    _add_outrank_failures("outranks", case.outranks, normalized, failures)
    _add_outrank_failures("forbidden_above", case.forbidden_above, normalized, failures)
    if anchor_paths is not None:
        normalized_anchors = {normalize_result_path(path) for path in anchor_paths}
        ranked_paths = {result.path for result in normalized}
        for expected_anchor in case.anchor_expected:
            expected_path = normalize_result_path(expected_anchor)
            if expected_path not in normalized_anchors:
                failures.append(f"anchor_expected missing: {expected_path}")
            elif expected_path in ranked_paths:
                failures.append(
                    "anchor_expected must remain outside ranked results: "
                    f"{expected_path}"
                )

    metrics = _metrics(
        case=case,
        normalized=normalized,
        target_ranks=target_ranks,
        coverage_top5_count=coverage_top5_count,
        preferred_rank_pass=preferred_rank_pass,
        entrypoint_rank=entrypoint_rank,
        latency_ms=latency_ms,
    )

    return CaseEvaluation(
        case_id=case.case_id,
        status=_status(case.gate, failures),
        metrics=metrics,
        failures=failures,
        top_results=[
            _result_payload(result) for result in normalized[:top_result_limit]
        ],
    )


def evaluate_context_pack(
    case: QualityCase,
    pack: ContextPack,
    evaluation: CaseEvaluation,
) -> CaseEvaluation:
    """Apply context-only expectations and metrics to raw evaluation."""
    failures = list(evaluation.failures)
    matched_count = 0
    expected_count = 0
    canonical_bytes = canonical_context_pack_bytes(
        replace(pack, budget=replace(pack.budget, pack_bytes=0))
    )
    payload = json.loads(canonical_bytes)

    paths_by_group = {
        group: tuple(
            item["file_path"]
            for item in payload["items"]
            if item["group"] == group
        )
        for group in CONTEXT_GROUPS
    }
    for group in CONTEXT_GROUPS:
        for matcher in case.expected_context_groups.get(group, ()):
            expected_count += 1
            if any(matcher.matches(path) for path in paths_by_group[group]):
                matched_count += 1
            else:
                failures.append(
                    "expected_context_groups missing in "
                    f"{group}: {_matcher_label(matcher)}"
                )

    if (
        case.expected_pack_status is not None
        and payload["status"] != case.expected_pack_status
    ):
        failures.append(
            f"expected_pack_status expected {case.expected_pack_status}, "
            f"got {payload['status']}"
        )

    minimum_confidence = case.minimum_context_confidence
    if (
        minimum_confidence is not None
        and _CONFIDENCE_RANK[payload["confidence"]["level"]]
        < _CONFIDENCE_RANK[minimum_confidence]
    ):
        failures.append(
            "minimum_context_confidence expected "
            f"{minimum_confidence}, got {payload['confidence']['level']}"
        )

    actual_need_matches = {
        (
            need["category"].casefold(),
            _normalize_public_subject(
                " ".join(need["subject_terms"])
            ).casefold(),
            need["required"],
            bool(need["matched_item_ids"]),
        )
        for need in payload["evidence_needs"]
    }
    for expected in case.expected_need_matches:
        expected_key = (
            expected.category.casefold(),
            _normalize_public_subject(expected.subject).casefold(),
            expected.required,
            expected.matched,
        )
        if expected_key not in actual_need_matches:
            failures.append(
                "expected_need_matches mismatch for "
                f"{expected.category}: {expected.subject}"
            )

    budget = payload["budget"]
    maximum_pack_bytes = case.maximum_pack_bytes
    if maximum_pack_bytes is not None:
        if pack.budget.pack_bytes > maximum_pack_bytes:
            failures.append(
                "maximum_pack_bytes exceeded by reported pack: "
                f"{pack.budget.pack_bytes} > {maximum_pack_bytes}"
            )
        if len(canonical_bytes) > maximum_pack_bytes:
            failures.append(
                "maximum_pack_bytes exceeded by canonical pack: "
                f"{len(canonical_bytes)} > {maximum_pack_bytes}"
            )

    maximum_truncated_items = case.maximum_truncated_items
    if (
        maximum_truncated_items is not None
        and budget["truncated_item_count"] > maximum_truncated_items
    ):
        failures.append(
            "maximum_truncated_items exceeded: "
            f"{budget['truncated_item_count']} > {maximum_truncated_items}"
        )

    for pattern in case.forbidden_next_query_patterns:
        compiled_pattern = _compile_safe_forbidden_next_query_pattern(pattern)
        if any(
            compiled_pattern.search(query["query"])
            for query in payload["next_queries"]
        ):
            failures.append(
                f"forbidden_next_query_patterns matched: {pattern}"
            )

    needs = payload["evidence_needs"]
    required_need_count = sum(need["required"] for need in needs)
    matched_required_need_count = sum(
        need["required"] and bool(need["matched_item_ids"])
        for need in needs
    )

    metrics = dict(evaluation.metrics)
    metrics.update(
        {
            "context_completeness": (
                matched_count / expected_count if expected_count else None
            ),
            "evidence_need_count": len(needs),
            "required_need_count": required_need_count,
            "matched_required_need_count": matched_required_need_count,
            "evidence_need_completeness": (
                matched_required_need_count / required_need_count
                if required_need_count
                else None
            ),
            "pack_bytes": len(canonical_bytes),
            "content_bytes": budget["content_bytes"],
            "truncated_item_count": budget["truncated_item_count"],
            "omitted_item_count": budget["omitted_item_count"],
        }
    )
    return replace(
        evaluation,
        status=_status(case.gate, failures),
        metrics=metrics,
        failures=failures,
    )


def evaluate_exploration(
    case: QualityCase,
    explored: ExploredContext,
    evaluation: CaseEvaluation,
) -> CaseEvaluation:
    trace = explored.trace
    if trace.retrieval_call_count != 1 + trace.executed_probe_count:
        raise ValueError(
            "exploration retrieval_call_count must equal 1 + executed_probe_count"
        )
    if not (
        0
        <= trace.initial_satisfied_goal_count
        <= trace.final_satisfied_goal_count
        <= trace.retained_goal_count
    ):
        raise ValueError("exploration goal counts are inconsistent")

    followup_probes = tuple(
        probe
        for round_record in trace.rounds[1:]
        for probe in round_record.probes
    )
    if len(followup_probes) != trace.executed_probe_count:
        raise ValueError("exploration executed_probe_count is inconsistent")

    preview_valid_count = sum(
        _valid_final_evidence_origin(item) for item in trace.final_evidence
    )
    if preview_valid_count != len(trace.final_evidence):
        raise ValueError("exploration final evidence contains an invalid origin")
    complete_valid_origin_count = (
        preview_valid_count + trace.final_evidence_omitted_count
    )
    if complete_valid_origin_count != trace.final_evidence_count:
        raise ValueError("exploration final_evidence_count is inconsistent")

    initial_paths = _bundle_path_union(explored.initial_bundle)
    fused_paths = _bundle_path_union(explored.fused_bundle)
    initial_pack_paths = _pack_paths(explored.initial_pack)
    final_pack_paths = _pack_paths(explored.final_pack)
    if trace.final_evidence_count != len(final_pack_paths):
        raise ValueError(
            "exploration final_evidence_count must equal final pack item count"
        )

    retained_goal_count = trace.retained_goal_count
    duplicate_path_count = sum(
        probe.duplicate_path_count for probe in followup_probes
    )
    returned_path_count = sum(
        probe.unique_path_count for probe in followup_probes
    )
    efficient_probe_count = sum(
        bool(probe.novel_path_count or probe.newly_satisfied_goal_ids)
        for probe in followup_probes
    )
    final_noise_paths = {
        path
        for path in final_pack_paths
        if any(matcher.matches(path) for matcher in case.final_noise_matchers)
    }

    exploration_metrics = {
        "exploration_goal_coverage_initial": (
            trace.initial_satisfied_goal_count / retained_goal_count
            if retained_goal_count
            else None
        ),
        "exploration_goal_coverage_final": (
            trace.final_satisfied_goal_count / retained_goal_count
            if retained_goal_count
            else None
        ),
        "exploration_goal_gain": (
            trace.final_satisfied_goal_count
            - trace.initial_satisfied_goal_count
        ),
        "novel_path_count": len(fused_paths - initial_paths),
        "duplicate_path_ratio": (
            duplicate_path_count / returned_path_count
            if returned_path_count
            else None
        ),
        "executed_probe_count": trace.executed_probe_count,
        "probe_efficiency": (
            efficient_probe_count / trace.executed_probe_count
            if trace.executed_probe_count
            else None
        ),
        "retrieval_call_count": trace.retrieval_call_count,
        "exploration_trace_coverage": (
            complete_valid_origin_count / len(final_pack_paths)
            if final_pack_paths
            else None
        ),
        "final_pack_noise_count": len(final_noise_paths),
        "final_pack_noise_ratio": (
            len(final_noise_paths) / len(final_pack_paths)
            if final_pack_paths
            else None
        ),
        "exploration_latency_ms": trace.duration_ms,
    }

    failures = list(evaluation.failures)
    for matcher in case.initial_absent:
        if any(matcher.matches(path) for path in initial_pack_paths):
            failures.append(
                f"initial_absent present: {_matcher_label(matcher)}"
            )
    for matcher in case.final_present:
        if not any(matcher.matches(path) for path in final_pack_paths):
            failures.append(
                f"final_present missing: {_matcher_label(matcher)}"
            )
    if case.final_at_least is not None:
        match_count = sum(
            any(matcher.matches(path) for path in final_pack_paths)
            for matcher in case.final_at_least.matchers
        )
        if match_count < case.final_at_least.min_matches:
            failures.append(
                "final_at_least expected "
                f"{case.final_at_least.min_matches}, found {match_count}"
            )
    for matcher in case.final_forbidden:
        if any(matcher.matches(path) for path in final_pack_paths):
            failures.append(
                f"final_forbidden present: {_matcher_label(matcher)}"
            )

    if (
        case.expected_termination_reason is not None
        and trace.termination_reason != case.expected_termination_reason
    ):
        failures.append(
            "expected_termination_reason expected "
            f"{case.expected_termination_reason}, got {trace.termination_reason}"
        )
    if (
        case.expected_retrieval_call_count is not None
        and trace.retrieval_call_count != case.expected_retrieval_call_count
    ):
        failures.append(
            "expected_retrieval_call_count expected "
            f"{case.expected_retrieval_call_count}, got "
            f"{trace.retrieval_call_count}"
        )
    if (
        case.maximum_retrieval_call_count is not None
        and trace.retrieval_call_count > case.maximum_retrieval_call_count
    ):
        failures.append(
            "maximum_retrieval_call_count exceeded: "
            f"{trace.retrieval_call_count} > "
            f"{case.maximum_retrieval_call_count}"
        )
    goal_gain = exploration_metrics["exploration_goal_gain"]
    if case.minimum_goal_gain is not None and goal_gain < case.minimum_goal_gain:
        failures.append(
            f"minimum_goal_gain expected {case.minimum_goal_gain}, got {goal_gain}"
        )
    noise_count = exploration_metrics["final_pack_noise_count"]
    if (
        case.maximum_final_noise_items is not None
        and noise_count > case.maximum_final_noise_items
    ):
        failures.append(
            "maximum_final_noise_items exceeded: "
            f"{noise_count} > {case.maximum_final_noise_items}"
        )
    trace_coverage = exploration_metrics["exploration_trace_coverage"]
    if final_pack_paths and trace_coverage != 1.0:
        failures.append(
            f"exploration_trace_coverage expected 1.0, got {trace_coverage}"
        )

    metrics = dict(evaluation.metrics)
    metrics.update(exploration_metrics)
    return replace(
        evaluation,
        status=_status(case.gate, failures),
        metrics=metrics,
        failures=failures,
    )


def _bundle_path_union(bundle: Any) -> set[str]:
    return {
        normalize_result_path(item.file_path.as_posix())
        for item in (*bundle.results, *bundle.evidence_anchors)
    }


def _pack_paths(pack: ContextPack) -> tuple[str, ...]:
    return tuple(normalize_result_path(item.file_path) for item in pack.items)


def _valid_final_evidence_origin(item: Any) -> bool:
    return bool(
        type(getattr(item, "source_round", None)) is int
        and item.source_round >= 0
        and isinstance(getattr(item, "probe_id", None), str)
        and item.probe_id
        and type(getattr(item, "probe_rank", None)) is int
        and item.probe_rank > 0
        and isinstance(getattr(item, "selection_reason", None), str)
        and item.selection_reason
    )


def _metrics(
    case: QualityCase,
    normalized: list[NormalizedResult],
    target_ranks: list[int | None],
    coverage_top5_count: int,
    preferred_rank_pass: bool,
    entrypoint_rank: int | None,
    latency_ms: int,
) -> dict[str, Any]:
    has_targets = bool(target_ranks)
    hit_at_5 = _hit_at(target_ranks, 5) if has_targets else None
    target_count = len(target_ranks)

    metrics = {
        "hit_at_1": _hit_at(target_ranks, 1) if has_targets else None,
        "hit_at_3": _hit_at(target_ranks, 3) if has_targets else None,
        "hit_at_5": hit_at_5,
        "hit_at_10": _hit_at(target_ranks, 10) if has_targets else None,
        "recall_at_5": _recall_at(target_ranks, 5) if has_targets else None,
        "recall_at_10": _recall_at(target_ranks, 10) if has_targets else None,
        "mrr": _mrr(target_ranks),
        "expected_coverage_top5": {
            "count": coverage_top5_count,
            "ratio": (
                coverage_top5_count / target_count if target_count else None
            ),
        },
        "preferred_rank_pass": preferred_rank_pass,
        "noise_top5": _noise_count(case, normalized, 5),
        "noise_top10": _noise_count(case, normalized, 10),
        "entrypoint_rank": entrypoint_rank,
        "cross_language_success": hit_at_5
        if "cross_language" in case.tags
        else None,
        "latency_ms": latency_ms,
        "result_count": len(normalized),
        "top_score": normalized[0].score if normalized else None,
    }
    metrics.update(_measurement_metrics(case, normalized))
    return metrics


def _measurement_matches(matcher: Matcher, path: str) -> bool:
    assert matcher.contains is not None
    return matcher.contains.casefold() in normalize_result_path(path).casefold()


def _measurement_metrics(
    case: QualityCase,
    results: list[NormalizedResult],
) -> dict[str, Any]:
    if case.metric_k is None:
        return {}
    top = results[: case.metric_k]
    relevant = [
        result
        for result in top
        if any(
            _measurement_matches(matcher, result.path)
            for matcher in case.relevance_matchers
        )
    ]
    noise = [
        result
        for result in top
        if any(
            _measurement_matches(matcher, result.path)
            for matcher in case.noise_matchers
        )
    ]
    first_rank = next(
        (
            result.rank
            for result in results
            if any(
                _measurement_matches(matcher, result.path)
                for matcher in case.relevance_matchers
            )
        ),
        None,
    )
    noise_metric_key = f"noise_top{case.metric_k}"
    if case.metric_k in (5, 10):
        noise_metric_key += "_measurement"
    return {
        f"precision_at_{case.metric_k}": len(relevant) / case.metric_k,
        noise_metric_key: len(noise),
        "mrr": 0.0 if first_rank is None else 1.0 / first_rank,
    }


def _relevance_targets(case: QualityCase) -> list[_RelevanceTarget]:
    targets = [
        _RelevanceTarget(
            matchers=(expected.matcher,),
        )
        for expected in case.expected_top_k
    ]
    targets.extend(
        _RelevanceTarget(
            matchers=group.matchers,
        )
        for group in case.expected_any_top_k
    )
    targets.extend(
        _RelevanceTarget(matchers=(matcher,))
        for group in case.expected_at_least_top_k
        for matcher in group.matchers
    )
    return targets


def _first_rank(
    results: list[NormalizedResult],
    matchers: tuple[Matcher, ...],
) -> int | None:
    for result in results:
        if any(matcher.matches(result.path) for matcher in matchers):
            return result.rank
    return None


def _hit_at(ranks: list[int | None], top_k: int) -> bool:
    return any(_rank_within(rank, top_k) for rank in ranks)


def _recall_at(ranks: list[int | None], top_k: int) -> float:
    return sum(1 for rank in ranks if _rank_within(rank, top_k)) / len(ranks)


def _mrr(ranks: list[int | None]) -> float:
    present_ranks = [rank for rank in ranks if rank is not None]
    if not present_ranks:
        return 0.0
    return 1.0 / min(present_ranks)


def _rank_within(rank: int | None, top_k: int) -> bool:
    return rank is not None and rank <= top_k


def _noise_count(
    case: QualityCase,
    results: list[NormalizedResult],
    top_k: int,
) -> int:
    eligible_absent = [
        absent for absent in case.absent_top_k if absent.top_k <= top_k
    ]
    return sum(
        1
        for result in results
        if result.rank <= top_k
        and any(absent.matcher.matches(result.path) for absent in eligible_absent)
    )


def _add_outrank_failures(
    label: str,
    assertions: tuple[Any, ...],
    results: list[NormalizedResult],
    failures: list[str],
) -> None:
    for assertion in assertions:
        noise_rank = _first_rank(results, (assertion.noise,))
        if noise_rank is None or noise_rank > assertion.top_k:
            continue
        source_rank = _first_rank(results, (assertion.source,))
        if source_rank is None or source_rank > noise_rank:
            failures.append(
                f"{label} failed within top {assertion.top_k}: "
                f"{_matcher_label(assertion.source)} below "
                f"{_matcher_label(assertion.noise)}"
            )


def _status(gate: Gate, failures: list[str]) -> str:
    if gate is Gate.KNOWN_GAP:
        return "known_gap"
    if gate is Gate.INFORMATIONAL:
        return "informational"
    return "fail" if failures else "pass"


def _result_payload(result: NormalizedResult) -> dict[str, Any]:
    return {
        "rank": result.rank,
        "path": result.path,
        "score": result.score,
        "score_parts": result.score_parts,
        "reasons": result.reasons,
        "semantic_matches": [
            {
                "variant_id": match.variant_id,
                "score": match.score,
            }
            for match in result.semantic_matches
        ],
    }


def _matcher_label(matcher: Matcher) -> str:
    if matcher.path is not None:
        return matcher.path
    if matcher.glob is not None:
        return matcher.glob
    assert matcher.contains is not None
    return matcher.contains
