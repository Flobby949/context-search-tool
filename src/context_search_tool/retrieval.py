from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field, replace
from pathlib import Path

from context_search_tool import sqlite_store, tokenizer
from context_search_tool.config import ToolConfig
from context_search_tool.manifest import assert_manifest_compatible
from context_search_tool.models import (
    EvidenceAnchor,
    QueryPlan,
    QueryVariant,
    RetrievalCandidate,
    RetrievalResult,
    RetrievalSummary,
)
from context_search_tool.paths import index_dir_for
from context_search_tool.query_planner import (
    QueryPlanner,
    build_query_variants,
    expand_query_plan_tokens,
    planner_from_config,
    planner_hint_tokens,
)
from context_search_tool.repo_profile import build_repo_profile
from context_search_tool.retrieval_core import (
    candidates,
    context_expansion,
    expansion,
    ordering,
    ranking,
    relation_policy,
    selection,
    types as core_types,
)
from context_search_tool.retrieval_trace import (
    RetrievalTrace,
    RetrievalTraceCollector,
    StageToken,
    TraceAdjustment,
    TraceCandidate,
    TraceOutcome,
    TraceQuery,
    TraceQueryVariant,
    TraceRank,
    TraceSelection,
    TraceTerminationReason,
)


MAX_EXPANSION_DEPTH = relation_policy.MAX_EXPANSION_DEPTH
MAX_EXPANSION_CANDIDATES = relation_policy.MAX_EXPANSION_CANDIDATES

@dataclass(frozen=True)
class QueryBundle:
    query: str
    expanded_tokens: list[str]
    results: list[RetrievalResult]
    followup_keywords: list[str]
    summary: RetrievalSummary = field(default_factory=RetrievalSummary)
    planner: QueryPlan = field(default_factory=QueryPlan.disabled_default)
    evidence_anchors: list[EvidenceAnchor] = field(default_factory=list)
    query_variants: list[QueryVariant] = field(default_factory=list)
    variant_retrieval_status: str = "original_only"


@dataclass(frozen=True)
class TracedQueryBundle:
    bundle: QueryBundle
    trace: RetrievalTrace


def _trace_query(
    *,
    original_tokens: list[str],
    expanded_tokens: list[str],
    variants: list[QueryVariant],
    variant_retrieval_status: str,
    plan: QueryPlan,
) -> TraceQuery:
    return TraceQuery(
        original_token_count=len(original_tokens),
        expanded_token_count=len(expanded_tokens),
        variant_retrieval_status=variant_retrieval_status,
        variants=tuple(
            TraceQueryVariant(item.variant_id, item.text, item.source)
            for item in variants
        ),
        planner_status=plan.status,
        planner_provider=plan.provider,
        planner_model=plan.model,
        planner_intent=plan.intent if plan.status == "ok" else "unknown",
        planner_latency_ms=plan.latency_ms,
        discarded_hint_count=len(plan.discarded_hints),
    )


def _finish_trace(
    collector: RetrievalTraceCollector | None,
    *,
    original_tokens: list[str],
    expanded_tokens: list[str],
    variants: list[QueryVariant],
    variant_retrieval_status: str,
    plan: QueryPlan,
    outcome: TraceOutcome,
    termination_reason: TraceTerminationReason,
    final_selections: tuple[TraceSelection, ...] = (),
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
        final_selections=final_selections,
    )
    collector.set_finished_trace(trace)


def _trace_stage_start(
    collector: RetrievalTraceCollector | None,
    name: str,
    *,
    input_count: int,
) -> StageToken | None:
    if collector is None:
        return None
    return collector.start_stage(name, input_count=input_count)


def _trace_sources(candidate: RetrievalCandidate) -> tuple[str, ...]:
    seen: set[str] = set()
    values: list[str] = []
    for raw in candidate.source.split(","):
        source = raw.strip()
        if source and source not in seen:
            seen.add(source)
            values.append(source)
    return tuple(values)


def _trace_candidate_observations(
    store: sqlite_store.SQLiteStore,
    candidates: list[RetrievalCandidate],
    limit: int,
) -> tuple[TraceCandidate, ...]:
    preview = candidates[:limit]
    chunks = store.chunks_for_ids([item.chunk_id for item in preview])
    observations: list[TraceCandidate] = []
    for candidate in preview:
        chunk = chunks.get(candidate.chunk_id)
        if chunk is None:
            continue
        observations.append(
            TraceCandidate(
                rank=len(observations) + 1,
                chunk_id=candidate.chunk_id,
                file_path=chunk.file_path.as_posix(),
                start_line=chunk.start_line,
                end_line=chunk.end_line,
                score=float(candidate.score),
                sources=_trace_sources(candidate),
                variant_ids=tuple(
                    match.variant_id
                    for match in candidate.semantic_matches
                ),
            )
        )
    return tuple(observations)


_TRACE_PUBLIC_SOURCE_FAMILY = {
    "anchor_expansion": "anchor_expansion",
    "anchored_relation": "anchor_expansion",
    "same_file_anchor": "anchor_expansion",
    "directory_anchor": "anchor_expansion",
}


def _trace_source_counts(
    candidates: list[RetrievalCandidate],
    allowed: tuple[str, ...],
) -> tuple[tuple[str, int], ...]:
    counts = {key: 0 for key in allowed}
    for candidate in candidates:
        for source in _trace_sources(candidate):
            public_source = _TRACE_PUBLIC_SOURCE_FAMILY.get(source, source)
            if public_source in counts:
                counts[public_source] += 1
    return tuple(counts.items())


def _finish_candidate_stage(
    collector: RetrievalTraceCollector | None,
    token: StageToken | None,
    *,
    store: sqlite_store.SQLiteStore,
    candidates: list[RetrievalCandidate],
    source_keys: tuple[str, ...] = (),
) -> None:
    if collector is None or token is None:
        return
    stopped = collector.stop_stage(token)
    observations = _trace_candidate_observations(
        store,
        candidates,
        collector.limits.stage_top_k,
    )
    collector.finish_stage(
        stopped,
        output_count=len(candidates),
        unique_output_count=len({item.chunk_id for item in candidates}),
        candidates=observations,
        source_counts=_trace_source_counts(candidates, source_keys),
    )


def _trace_ranked_observations(
    ranked: list[core_types._RankedChunk],
    candidates: dict[str, RetrievalCandidate],
    limit: int,
) -> tuple[TraceCandidate, ...]:
    observations: list[TraceCandidate] = []
    for rank, item in enumerate(ranked[:limit], start=1):
        candidate = candidates[item.chunk.chunk_id]
        observations.append(
            TraceCandidate(
                rank=rank,
                chunk_id=item.chunk.chunk_id,
                file_path=item.chunk.file_path.as_posix(),
                start_line=item.chunk.start_line,
                end_line=item.chunk.end_line,
                score=float(item.rerank_score),
                sources=_trace_sources(candidate),
                variant_ids=tuple(
                    match.variant_id
                    for match in candidate.semantic_matches
                ),
            )
        )
    return tuple(observations)


def _trace_expanded_observations(
    expanded: list[core_types._ExpandedResult],
    candidates: dict[str, RetrievalCandidate],
    limit: int,
) -> tuple[TraceCandidate, ...]:
    observations: list[TraceCandidate] = []
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
                for source in _trace_sources(candidate)
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
            TraceCandidate(
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


_TRACE_ADJUSTMENT_SUFFIXES = ("_boost", "_penalty", "_match")


def _is_trace_adjustment(name: str) -> bool:
    return name.endswith(_TRACE_ADJUSTMENT_SUFFIXES)


def _trace_adjustments(
    item: core_types._ExpandedResult,
    limit: int,
) -> tuple[tuple[TraceAdjustment, ...], int]:
    values = [
        TraceAdjustment(name, float(value))
        for name, value in item.score_parts.items()
        if _is_trace_adjustment(name) and float(value) != 0.0
    ]
    if item.was_ceiling_clamped:
        clamp = item.rerank_score - item.pre_ceiling_rerank_score
        if clamp:
            values.append(
                TraceAdjustment("planner_ceiling_clamp", float(clamp))
            )
    values.sort(key=lambda adjustment: (-abs(adjustment.value), adjustment.name))
    return tuple(values[:limit]), max(0, len(values) - limit)


def _trace_final_selections(
    decisions: selection._FinalTraceDecisions,
    candidates: dict[str, RetrievalCandidate],
    collector: RetrievalTraceCollector,
) -> tuple[TraceSelection, ...]:
    history = collector.rank_history
    selections: list[TraceSelection] = []
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
                    for source in _trace_sources(candidate)
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
        ranks: list[TraceRank] = []
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
                ranks.append(TraceRank(stage, prior_rank, prior_score))
        ranks.append(TraceRank("final_selection", rank, item.rerank_score))
        adjustments, omitted = _trace_adjustments(
            item,
            collector.limits.adjustment_top_k,
        )
        selections.append(
            TraceSelection(
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


def trace_repository(
    repo: Path,
    query: str,
    config: ToolConfig,
    context_lines: int | None = None,
    full_file: bool = False,
    planner: QueryPlanner | None = None,
    *,
    clock_ns=None,
) -> TracedQueryBundle:
    collector_kwargs = {} if clock_ns is None else {"clock_ns": clock_ns}
    collector = RetrievalTraceCollector(**collector_kwargs)
    bundle = query_repository(
        repo,
        query,
        config,
        context_lines=context_lines,
        full_file=full_file,
        planner=planner,
        trace_collector=collector,
    )
    return TracedQueryBundle(
        bundle=bundle,
        trace=collector.finished_trace(),
    )


def query_repository(
    repo: Path,
    query: str,
    config: ToolConfig,
    context_lines: int | None = None,
    full_file: bool = False,
    planner: QueryPlanner | None = None,
    *,
    trace_collector: RetrievalTraceCollector | None = None,
) -> QueryBundle:
    repo = repo.resolve()
    original_tokens = ordering.dedupe_lowered(tokenizer.tokenize_query(query))
    tokens = original_tokens
    plan = QueryPlan(original_query=query)
    query_variants = [QueryVariant("original", " ".join(query.split()), "original")]
    variant_retrieval_status = "original_only"
    index_dir = index_dir_for(repo)
    db_path = index_dir / "index.sqlite"
    if not db_path.exists():
        bundle = QueryBundle(
            query=query,
            expanded_tokens=tokens,
            results=[],
            followup_keywords=[],
            planner=plan,
            query_variants=query_variants,
            variant_retrieval_status=variant_retrieval_status,
        )
        _finish_trace(
            trace_collector,
            original_tokens=original_tokens,
            expanded_tokens=tokens,
            variants=query_variants,
            variant_retrieval_status=variant_retrieval_status,
            plan=plan,
            outcome="empty",
            termination_reason="missing_index",
        )
        return bundle

    assert_manifest_compatible(repo, config)

    store = sqlite_store.SQLiteStore(db_path)
    try:
        deleted_ids = store.deleted_chunk_ids()
    except sqlite3.Error:
        bundle = QueryBundle(
            query=query,
            expanded_tokens=tokens,
            results=[],
            followup_keywords=[],
            planner=plan,
            query_variants=query_variants,
            variant_retrieval_status=variant_retrieval_status,
        )
        _finish_trace(
            trace_collector,
            original_tokens=original_tokens,
            expanded_tokens=tokens,
            variants=query_variants,
            variant_retrieval_status=variant_retrieval_status,
            plan=plan,
            outcome="partial",
            termination_reason="store_read_error",
        )
        return bundle

    query_stage = _trace_stage_start(
        trace_collector,
        "query_understanding",
        input_count=len(original_tokens),
    )
    query_planner = planner or planner_from_config(config.query_planner)
    repo_profile = build_repo_profile(store)
    plan = query_planner.plan(query, repo_profile=repo_profile)
    query_variants, discarded_variants = build_query_variants(
        query,
        plan,
        config.query_planner.max_rewritten_queries,
    )
    if discarded_variants:
        plan = replace(
            plan,
            discarded_hints=ordering.ordered_unique_preserving_case(
                [*plan.discarded_hints, *discarded_variants]
            ),
        )
    tokens = expand_query_plan_tokens(query, plan)
    hint_tokens = (
        planner_hint_tokens(original_tokens, tokens) if plan.status == "ok" else []
    )
    if trace_collector is not None and query_stage is not None:
        stopped = trace_collector.stop_stage(query_stage)
        trace_collector.finish_stage(
            stopped,
            output_count=len(tokens),
            unique_output_count=len(set(tokens)),
        )
    token = _trace_stage_start(
        trace_collector,
        "semantic_recall",
        input_count=len(query_variants),
    )
    semantic_candidates, query_variants, variant_retrieval_status = (
        candidates.semantic_candidates(
            index_dir,
            query_variants,
            config,
            deleted_ids,
        )
    )
    _finish_candidate_stage(
        trace_collector,
        token,
        store=store,
        candidates=semantic_candidates,
        source_keys=("semantic", "planner_semantic"),
    )

    token = _trace_stage_start(
        trace_collector,
        "lexical_recall",
        input_count=len(original_tokens),
    )
    lexical_candidates = candidates.lexical_candidates(
        store,
        original_tokens,
        config.retrieval.lexical_top_k,
    )
    _finish_candidate_stage(
        trace_collector,
        token,
        store=store,
        candidates=lexical_candidates,
        source_keys=("lexical",),
    )

    token = _trace_stage_start(
        trace_collector,
        "path_symbol_recall",
        input_count=len(original_tokens),
    )
    path_symbol_candidates = candidates.path_symbol_candidates(
        store,
        original_tokens,
        config.retrieval.lexical_top_k,
    )
    _finish_candidate_stage(
        trace_collector,
        token,
        store=store,
        candidates=path_symbol_candidates,
        source_keys=("path_symbol",),
    )

    probes = candidates.direct_text_probes(query, original_tokens)
    token = _trace_stage_start(
        trace_collector,
        "direct_text_recall",
        input_count=len(probes),
    )
    direct_text_candidates = candidates.direct_text_candidates(
        store,
        probes,
        config,
    )
    _finish_candidate_stage(
        trace_collector,
        token,
        store=store,
        candidates=direct_text_candidates,
        source_keys=("direct_text",),
    )

    initial_candidates = [
        *semantic_candidates,
        *lexical_candidates,
        *path_symbol_candidates,
        *direct_text_candidates,
    ]

    token = _trace_stage_start(
        trace_collector,
        "signal_recall",
        input_count=len(original_tokens),
    )
    signal_candidates = candidates.signal_candidates(store, original_tokens, config)
    _finish_candidate_stage(
        trace_collector,
        token,
        store=store,
        candidates=signal_candidates,
        source_keys=("signal",),
    )

    token = _trace_stage_start(
        trace_collector,
        "planner_hint_recall",
        input_count=len(hint_tokens),
    )
    planner_candidates = candidates.planner_hint_candidates(store, hint_tokens, config)
    _finish_candidate_stage(
        trace_collector,
        token,
        store=store,
        candidates=planner_candidates,
        source_keys=(
            "planner_lexical",
            "planner_path_symbol",
            "planner_signal",
        ),
    )

    raw_direct = [*initial_candidates, *signal_candidates, *planner_candidates]
    token = _trace_stage_start(
        trace_collector,
        "direct_merge",
        input_count=len(raw_direct),
    )
    direct_candidates = candidates.merge_candidates(raw_direct)
    _finish_candidate_stage(
        trace_collector,
        token,
        store=store,
        candidates=list(direct_candidates.values()),
    )

    token = _trace_stage_start(
        trace_collector,
        "anchor_expansion",
        input_count=len(direct_candidates),
    )
    anchor_candidates = expansion.anchor_candidates(
        store,
        list(direct_candidates.values()),
        config,
        query=query,
        tokens=original_tokens,
    )
    _finish_candidate_stage(
        trace_collector,
        token,
        store=store,
        candidates=anchor_candidates,
        source_keys=("anchor_expansion",),
    )

    relation_seed_candidates = candidates.merge_candidates(
        [
            *direct_candidates.values(),
            *anchor_candidates,
        ]
    )
    token = _trace_stage_start(
        trace_collector,
        "relation_expansion",
        input_count=len(relation_seed_candidates),
    )
    relation_candidates = expansion.relation_candidates(
        store,
        list(relation_seed_candidates.values()),
        config,
    )
    _finish_candidate_stage(
        trace_collector,
        token,
        store=store,
        candidates=relation_candidates,
        source_keys=("relation",),
    )

    all_candidates = [
        *direct_candidates.values(),
        *anchor_candidates,
        *relation_candidates,
    ]
    token = _trace_stage_start(
        trace_collector,
        "candidate_merge",
        input_count=len(all_candidates),
    )
    merged_candidates = candidates.merge_candidates(all_candidates)
    _finish_candidate_stage(
        trace_collector,
        token,
        store=store,
        candidates=list(merged_candidates.values()),
    )
    if not merged_candidates:
        bundle = QueryBundle(
            query=query,
            expanded_tokens=tokens,
            results=[],
            followup_keywords=[],
            planner=plan,
            query_variants=query_variants,
            variant_retrieval_status=variant_retrieval_status,
        )
        _finish_trace(
            trace_collector,
            original_tokens=original_tokens,
            expanded_tokens=tokens,
            variants=query_variants,
            variant_retrieval_status=variant_retrieval_status,
            plan=plan,
            outcome="empty",
            termination_reason="no_candidates",
        )
        return bundle

    token = _trace_stage_start(
        trace_collector,
        "ranking",
        input_count=len(merged_candidates),
    )
    ranked_chunks = ranking.rank_chunks(
        store, merged_candidates, original_tokens, query
    )
    if trace_collector is not None and token is not None:
        stopped = trace_collector.stop_stage(token)
        observations = _trace_ranked_observations(
            ranked_chunks,
            merged_candidates,
            trace_collector.limits.stage_top_k,
        )
        trace_collector.finish_stage(
            stopped,
            output_count=len(ranked_chunks),
            unique_output_count=len(ranked_chunks),
            candidates=observations,
            rank_positions=(
                (item.chunk.chunk_id, rank, float(item.rerank_score))
                for rank, item in enumerate(ranked_chunks, start=1)
            ),
        )

    token = _trace_stage_start(
        trace_collector,
        "cohort_rerank",
        input_count=len(ranked_chunks),
    )
    ranked_chunks = ranking.apply_frontend_import_cohort_rerank(
        repo, ranked_chunks, query
    )
    if trace_collector is not None and token is not None:
        stopped = trace_collector.stop_stage(token)
        observations = _trace_ranked_observations(
            ranked_chunks,
            merged_candidates,
            trace_collector.limits.stage_top_k,
        )
        trace_collector.finish_stage(
            stopped,
            output_count=len(ranked_chunks),
            unique_output_count=len(ranked_chunks),
            candidates=observations,
            rank_positions=(
                (item.chunk.chunk_id, rank, float(item.rerank_score))
                for rank, item in enumerate(ranked_chunks, start=1)
            ),
        )

    token = _trace_stage_start(
        trace_collector,
        "context_expansion",
        input_count=len(ranked_chunks),
    )
    expanded = context_expansion.expand_ranked_chunks(
        repo,
        ranked_chunks,
        config,
        context_lines,
        full_file,
    )
    if trace_collector is not None and token is not None:
        stopped = trace_collector.stop_stage(token)
        observations = _trace_expanded_observations(
            expanded,
            merged_candidates,
            trace_collector.limits.stage_top_k,
        )
        trace_collector.finish_stage(
            stopped,
            output_count=sum(len(item.chunk_ids) for item in expanded),
            unique_output_count=len(expanded),
            candidates=observations,
            rank_positions=(
                (chunk_id, rank, float(item.rerank_score))
                for rank, item in enumerate(expanded, start=1)
                for chunk_id in item.chunk_ids
            ),
        )

    token = _trace_stage_start(
        trace_collector,
        "final_selection",
        input_count=len(expanded),
    )
    trace_decisions = None
    if trace_collector is None:
        visible_results, evidence_anchors = (
            selection.split_results_and_anchors(
                expanded,
                final_top_k=config.retrieval.final_top_k,
                anchor_top_k=evidence_anchor_top_k(config.retrieval.final_top_k),
            )
        )
    else:
        visible_results, evidence_anchors, trace_decisions = (
            selection.split_results_and_anchors(
                expanded,
                final_top_k=config.retrieval.final_top_k,
                anchor_top_k=evidence_anchor_top_k(config.retrieval.final_top_k),
                collect_trace=True,
            )
        )
    final_selections: tuple[TraceSelection, ...] = ()
    if trace_collector is not None and token is not None:
        stopped = trace_collector.stop_stage(token)
        assert trace_decisions is not None
        final_selections = _trace_final_selections(
            trace_decisions,
            merged_candidates,
            trace_collector,
        )
        trace_collector.finish_stage(
            stopped,
            output_count=len(trace_decisions.selected),
            unique_output_count=len(trace_decisions.selected),
            candidates=(),
            decision_counts=trace_decisions.counts,
        )

    summary, results, followup_keywords = selection.assemble_query_output(
        store,
        visible_results,
    )
    bundle = QueryBundle(
        query=query,
        expanded_tokens=tokens,
        results=results,
        followup_keywords=followup_keywords,
        summary=summary,
        planner=plan,
        evidence_anchors=evidence_anchors,
        query_variants=query_variants,
        variant_retrieval_status=variant_retrieval_status,
    )
    _finish_trace(
        trace_collector,
        original_tokens=original_tokens,
        expanded_tokens=tokens,
        variants=query_variants,
        variant_retrieval_status=variant_retrieval_status,
        plan=plan,
        outcome="complete",
        termination_reason="completed",
        final_selections=final_selections,
    )
    return bundle


def evidence_anchor_top_k(max_results: int) -> int:
    if max_results <= 0:
        return 0
    return max(1, min(5, max_results // 3))


def normalize_score(scores: list[float]) -> list[float]:
    return ranking.normalize_score(scores)
