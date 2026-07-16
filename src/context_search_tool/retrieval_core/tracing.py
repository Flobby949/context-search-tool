from __future__ import annotations

from typing import TYPE_CHECKING

import context_search_tool.retrieval_trace as retrieval_trace
from context_search_tool.retrieval_core import (
    ordering,
    selection,
    types as core_types,
)

if TYPE_CHECKING:
    from context_search_tool.models import (
        QueryPlan,
        QueryVariant,
        RetrievalCandidate,
    )
    from context_search_tool.sqlite_store import SQLiteStore


_PUBLIC_SOURCE_FAMILY = {
    "anchor_expansion": "anchor_expansion",
    "anchored_relation": "anchor_expansion",
    "same_file_anchor": "anchor_expansion",
    "directory_anchor": "anchor_expansion",
}
_ADJUSTMENT_SUFFIXES = ("_boost", "_penalty", "_match")


def _trace_query(
    *,
    original_tokens: list[str],
    expanded_tokens: list[str],
    variants: list[QueryVariant],
    variant_retrieval_status: str,
    plan: QueryPlan,
) -> retrieval_trace.TraceQuery:
    return retrieval_trace.TraceQuery(
        original_token_count=len(original_tokens),
        expanded_token_count=len(expanded_tokens),
        variant_retrieval_status=variant_retrieval_status,
        variants=tuple(
            retrieval_trace.TraceQueryVariant(item.variant_id, item.text, item.source)
            for item in variants
        ),
        planner_status=plan.status,
        planner_provider=plan.provider,
        planner_model=plan.model,
        planner_intent=plan.intent if plan.status == "ok" else "unknown",
        planner_latency_ms=plan.latency_ms,
        discarded_hint_count=len(plan.discarded_hints),
    )


def _sources(candidate: RetrievalCandidate) -> tuple[str, ...]:
    seen: set[str] = set()
    values: list[str] = []
    for raw in candidate.source.split(","):
        source = raw.strip()
        if source and source not in seen:
            seen.add(source)
            values.append(source)
    return tuple(values)


def _candidate_observations(
    store: SQLiteStore,
    candidates: list[RetrievalCandidate],
    limit: int,
) -> tuple[retrieval_trace.TraceCandidate, ...]:
    preview = candidates[:limit]
    chunks = store.chunks_for_ids([item.chunk_id for item in preview])
    observations: list[retrieval_trace.TraceCandidate] = []
    for candidate in preview:
        chunk = chunks.get(candidate.chunk_id)
        if chunk is None:
            continue
        observations.append(
            retrieval_trace.TraceCandidate(
                rank=len(observations) + 1,
                chunk_id=candidate.chunk_id,
                file_path=chunk.file_path.as_posix(),
                start_line=chunk.start_line,
                end_line=chunk.end_line,
                score=float(candidate.score),
                sources=_sources(candidate),
                variant_ids=tuple(
                    match.variant_id
                    for match in candidate.semantic_matches
                ),
            )
        )
    return tuple(observations)


def _source_counts(
    candidates: list[RetrievalCandidate],
    allowed: tuple[str, ...],
) -> tuple[tuple[str, int], ...]:
    counts = {key: 0 for key in allowed}
    for candidate in candidates:
        for source in _sources(candidate):
            public_source = _PUBLIC_SOURCE_FAMILY.get(source, source)
            if public_source in counts:
                counts[public_source] += 1
    return tuple(counts.items())


def _ranked_observations(
    ranked: list[core_types._RankedChunk],
    candidates: dict[str, RetrievalCandidate],
    limit: int,
) -> tuple[retrieval_trace.TraceCandidate, ...]:
    observations: list[retrieval_trace.TraceCandidate] = []
    for rank, item in enumerate(ranked[:limit], start=1):
        candidate = candidates[item.chunk.chunk_id]
        observations.append(
            retrieval_trace.TraceCandidate(
                rank=rank,
                chunk_id=item.chunk.chunk_id,
                file_path=item.chunk.file_path.as_posix(),
                start_line=item.chunk.start_line,
                end_line=item.chunk.end_line,
                score=float(item.rerank_score),
                sources=_sources(candidate),
                variant_ids=tuple(
                    match.variant_id
                    for match in candidate.semantic_matches
                ),
            )
        )
    return tuple(observations)


def _expanded_observations(
    expanded: list[core_types._ExpandedResult],
    candidates: dict[str, RetrievalCandidate],
    limit: int,
) -> tuple[retrieval_trace.TraceCandidate, ...]:
    observations: list[retrieval_trace.TraceCandidate] = []
    for rank, item in enumerate(expanded[:limit], start=1):
        source_candidates = [
            candidates[chunk_id]
            for chunk_id in item.chunk_ids
            if chunk_id in candidates
        ]
        sources = ordering.ordered_unique_preserving_case(
            [
                source
                for candidate in source_candidates
                for source in _sources(candidate)
            ]
        )
        variant_ids = ordering.ordered_unique_preserving_case(
            [
                match.variant_id
                for candidate in source_candidates
                for match in candidate.semantic_matches
            ]
        )
        observations.append(
            retrieval_trace.TraceCandidate(
                rank=rank,
                chunk_id=item.chunk_ids[0],
                file_path=item.file_path.as_posix(),
                start_line=item.start_line,
                end_line=item.end_line,
                score=float(item.rerank_score),
                sources=tuple(sources),
                variant_ids=tuple(variant_ids),
            )
        )
    return tuple(observations)


def _ranked_positions(
    ranked: list[core_types._RankedChunk],
) -> tuple[tuple[str, int, float], ...]:
    return tuple(
        (item.chunk.chunk_id, rank, float(item.rerank_score))
        for rank, item in enumerate(ranked, start=1)
    )


def _expanded_positions(
    expanded: list[core_types._ExpandedResult],
) -> tuple[tuple[str, int, float], ...]:
    return tuple(
        (chunk_id, rank, float(item.rerank_score))
        for rank, item in enumerate(expanded, start=1)
        for chunk_id in item.chunk_ids
    )


def _is_adjustment(name: str) -> bool:
    return name.endswith(_ADJUSTMENT_SUFFIXES)


def _adjustments(
    item: core_types._ExpandedResult,
    limit: int,
) -> tuple[tuple[retrieval_trace.TraceAdjustment, ...], int]:
    values = [
        retrieval_trace.TraceAdjustment(name, float(value))
        for name, value in item.score_parts.items()
        if _is_adjustment(name) and float(value) != 0.0
    ]
    if item.was_ceiling_clamped:
        clamp = item.rerank_score - item.pre_ceiling_rerank_score
        if clamp:
            values.append(
                retrieval_trace.TraceAdjustment(
                    "planner_ceiling_clamp",
                    float(clamp),
                )
            )
    values.sort(key=lambda adjustment: (-abs(adjustment.value), adjustment.name))
    return tuple(values[:limit]), max(0, len(values) - limit)


def _final_selections(
    decisions: selection._FinalTraceDecisions,
    candidates: dict[str, RetrievalCandidate],
    collector: retrieval_trace.RetrievalTraceCollector,
) -> tuple[retrieval_trace.TraceSelection, ...]:
    history = collector.rank_history
    selections: list[retrieval_trace.TraceSelection] = []
    for rank, selected in enumerate(decisions.selected, start=1):
        item = selected.item
        source_candidates = [
            candidates[chunk_id]
            for chunk_id in item.chunk_ids
            if chunk_id in candidates
        ]
        sources = tuple(
            ordering.ordered_unique_preserving_case(
                [
                    source
                    for candidate in source_candidates
                    for source in _sources(candidate)
                ]
            )
        )
        variant_ids = tuple(
            ordering.ordered_unique_preserving_case(
                [
                    match.variant_id
                    for candidate in source_candidates
                    for match in candidate.semantic_matches
                ]
            )
        )
        ranks: list[retrieval_trace.TraceRank] = []
        for stage in ("ranking", "cohort_rerank", "context_expansion"):
            positions = [
                value
                for chunk_id in item.chunk_ids
                for value in history.get(chunk_id, ())
                if value[0] == stage
            ]
            if positions:
                _, prior_rank, prior_score = min(
                    positions,
                    key=lambda value: (value[1], -value[2]),
                )
                ranks.append(retrieval_trace.TraceRank(stage, prior_rank, prior_score))
        ranks.append(
            retrieval_trace.TraceRank("final_selection", rank, item.rerank_score)
        )
        adjustments, omitted = _adjustments(
            item,
            collector.limits.adjustment_top_k,
        )
        selections.append(
            retrieval_trace.TraceSelection(
                rank=rank,
                selection_kind=selected.kind,
                selection_reason=selected.reason,
                file_path=item.file_path.as_posix(),
                start_line=item.start_line,
                end_line=item.end_line,
                score=float(item.rerank_score),
                origin_chunk_ids=tuple(item.chunk_ids),
                sources=sources,
                variant_ids=variant_ids,
                rank_history=tuple(ranks),
                adjustments=adjustments,
                adjustment_omitted_count=omitted,
                reasons=tuple(item.reasons),
            )
        )
    return tuple(selections)


def start_stage(
    collector: retrieval_trace.RetrievalTraceCollector | None,
    name: str,
    *,
    input_count: int,
) -> retrieval_trace.StageToken | None:
    if collector is None:
        return None
    return collector.start_stage(name, input_count=input_count)


def stop_stage(
    collector: retrieval_trace.RetrievalTraceCollector | None,
    token: retrieval_trace.StageToken | None,
) -> retrieval_trace.StoppedStage | None:
    if collector is None or token is None:
        return None
    return collector.stop_stage(token)


def finish_count_stage(
    collector: retrieval_trace.RetrievalTraceCollector | None,
    stopped: retrieval_trace.StoppedStage | None,
    *,
    output_count: int,
    unique_output_count: int,
) -> None:
    if collector is None or stopped is None:
        return
    collector.finish_stage(
        stopped,
        output_count=output_count,
        unique_output_count=unique_output_count,
    )


def finish_candidate_stage(
    collector: retrieval_trace.RetrievalTraceCollector | None,
    stopped: retrieval_trace.StoppedStage | None,
    *,
    store: SQLiteStore,
    candidates: list[RetrievalCandidate],
    source_keys: tuple[str, ...] = (),
) -> None:
    if collector is None or stopped is None:
        return
    observations = _candidate_observations(
        store,
        candidates,
        collector.limits.stage_top_k,
    )
    collector.finish_stage(
        stopped,
        output_count=len(candidates),
        unique_output_count=len({item.chunk_id for item in candidates}),
        candidates=observations,
        source_counts=_source_counts(candidates, source_keys),
    )


def finish_ranked_stage(
    collector: retrieval_trace.RetrievalTraceCollector | None,
    stopped: retrieval_trace.StoppedStage | None,
    *,
    ranked: list[core_types._RankedChunk],
    candidates: dict[str, RetrievalCandidate],
) -> None:
    if collector is None or stopped is None:
        return
    observations = _ranked_observations(
        ranked,
        candidates,
        collector.limits.stage_top_k,
    )
    collector.finish_stage(
        stopped,
        output_count=len(ranked),
        unique_output_count=len(ranked),
        candidates=observations,
        rank_positions=_ranked_positions(ranked),
    )


def finish_expanded_stage(
    collector: retrieval_trace.RetrievalTraceCollector | None,
    stopped: retrieval_trace.StoppedStage | None,
    *,
    expanded: list[core_types._ExpandedResult],
    candidates: dict[str, RetrievalCandidate],
) -> None:
    if collector is None or stopped is None:
        return
    observations = _expanded_observations(
        expanded,
        candidates,
        collector.limits.stage_top_k,
    )
    collector.finish_stage(
        stopped,
        output_count=sum(len(item.chunk_ids) for item in expanded),
        unique_output_count=len(expanded),
        candidates=observations,
        rank_positions=_expanded_positions(expanded),
    )


def finish_selection_stage(
    collector: retrieval_trace.RetrievalTraceCollector | None,
    stopped: retrieval_trace.StoppedStage | None,
    *,
    decisions: selection._FinalTraceDecisions | None,
    candidates: dict[str, RetrievalCandidate],
) -> tuple[retrieval_trace.TraceSelection, ...]:
    if collector is None or stopped is None:
        return ()
    assert decisions is not None
    final_selections = _final_selections(decisions, candidates, collector)
    collector.finish_stage(
        stopped,
        output_count=len(decisions.selected),
        unique_output_count=len(decisions.selected),
        candidates=(),
        decision_counts=decisions.counts,
    )
    return final_selections


def finish_trace(
    collector: retrieval_trace.RetrievalTraceCollector | None,
    *,
    original_tokens: list[str],
    expanded_tokens: list[str],
    variants: list[QueryVariant],
    variant_retrieval_status: str,
    plan: QueryPlan,
    outcome: retrieval_trace.TraceOutcome,
    termination_reason: retrieval_trace.TraceTerminationReason,
    selections: tuple[retrieval_trace.TraceSelection, ...] = (),
) -> None:
    if collector is None:
        return
    collector.record_query(
        _trace_query(
            original_tokens=original_tokens,
            expanded_tokens=expanded_tokens,
            variants=variants,
            variant_retrieval_status=variant_retrieval_status,
            plan=plan,
        )
    )
    trace = collector.finish(
        outcome=outcome,
        termination_reason=termination_reason,
        final_selections=selections,
    )
    collector.set_finished_trace(trace)
