from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from context_search_tool.models import RetrievalResult
from context_search_tool.quality.cases import (
    Gate,
    Matcher,
    QualityCase,
    normalize_result_path,
)


@dataclass(frozen=True)
class NormalizedResult:
    rank: int
    path: str
    score: float
    score_parts: dict[str, float]
    reasons: list[str]


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

    expected_top5_count = sum(
        1
        for expected in case.expected_top_k
        if _rank_within(_first_rank(normalized, (expected.matcher,)), 5)
    )
    coverage_top5_count = sum(1 for rank in target_ranks if _rank_within(rank, 5))
    if (
        case.expected_top5_min is not None
        and expected_top5_count < case.expected_top5_min
    ):
        failures.append(
            f"expected_top5_min expected {case.expected_top5_min}, "
            f"found {expected_top5_count}"
        )

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
        for expected_anchor in case.anchor_expected:
            expected_path = normalize_result_path(expected_anchor)
            if expected_path not in normalized_anchors:
                failures.append(f"anchor_expected missing: {expected_path}")

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

    return {
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
    }


def _matcher_label(matcher: Matcher) -> str:
    if matcher.path is not None:
        return matcher.path
    if matcher.glob is not None:
        return matcher.glob
    assert matcher.contains is not None
    return matcher.contains
