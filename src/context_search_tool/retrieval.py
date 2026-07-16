from __future__ import annotations

import math
import sqlite3
from collections import Counter
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Literal, overload

from context_search_tool import chunker, sqlite_store, tokenizer
from context_search_tool.config import ToolConfig
from context_search_tool.manifest import assert_manifest_compatible
from context_search_tool.models import (
    CodeSignal,
    DocumentChunk,
    EvidenceAnchor,
    QueryPlan,
    QueryVariant,
    RetrievalCandidate,
    RetrievalResult,
    RetrievalSpan,
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
    evidence_merge,
    expansion,
    ordering,
    ranking,
    relation_policy,
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
    TraceSelectionKind,
    TraceSelectionReason,
    TraceTerminationReason,
)


MAX_EXPANSION_DEPTH = relation_policy.MAX_EXPANSION_DEPTH
MAX_EXPANSION_CANDIDATES = relation_policy.MAX_EXPANSION_CANDIDATES

_SPAN_SOURCE_KEYS = (
    "path_symbol",
    "lexical",
    "semantic",
    "planner_semantic",
    "signal",
    "planner_hint",
    "anchor_expansion",
    "relation",
)
_SPAN_SOURCE_SCORE_KEYS = {
    "path_symbol": ("path_symbol",),
    "lexical": ("lexical",),
    "semantic": ("semantic",),
    "planner_semantic": ("planner_semantic",),
    "signal": ("signal",),
    "planner_hint": (
        "planner_hint",
        "planner_lexical",
        "planner_path_symbol",
        "planner_signal",
    ),
    "anchor_expansion": (
        "anchor_expansion",
        "anchored_relation",
        "same_file_anchor",
        "directory_anchor",
    ),
    "relation": ("relation",),
}


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


@dataclass(frozen=True)
class _FinalTraceInput:
    kind: TraceSelectionKind
    reason: TraceSelectionReason
    item: core_types._ExpandedResult


@dataclass(frozen=True)
class _FinalTraceDecisions:
    selected: tuple[_FinalTraceInput, ...]
    counts: tuple[tuple[str, int], ...]


_FINAL_TRACE_DECISION_KEYS = (
    "selected_result",
    "selected_anchor",
    "duplicate_anchor",
    "result_limit",
    "anchor_limit",
)


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
    decisions: _FinalTraceDecisions,
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
    expanded = _expand_ranked_chunks(
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
            _split_code_results_and_evidence_anchors(
                expanded,
                final_top_k=config.retrieval.final_top_k,
                anchor_top_k=evidence_anchor_top_k(config.retrieval.final_top_k),
            )
        )
    else:
        visible_results, evidence_anchors, trace_decisions = (
            _split_code_results_and_evidence_anchors(
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

    summary, result_reasons = _summarize_results(store, visible_results)
    results = [
        RetrievalResult(
            file_path=item.file_path,
            start_line=item.start_line,
            end_line=item.end_line,
            content=item.content,
            score=item.rerank_score,
            score_parts={
                **item.score_parts,
                "combined_score": item.score,
                "rerank_score": item.rerank_score,
                "evidence_priority": float(item.evidence_priority),
            },
            reasons=ordering.dedupe_lowered(item.reasons + result_reasons[index]),
            followup_keywords=item.followup_keywords,
            semantic_matches=item.semantic_matches,
            spans=item.spans,
            _context_content=item._context_content,
        )
        for index, item in enumerate(visible_results)
    ]
    bundle = QueryBundle(
        query=query,
        expanded_tokens=tokens,
        results=results,
        followup_keywords=_followup_keywords(results),
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


@overload
def _split_code_results_and_evidence_anchors(
    expanded: list[core_types._ExpandedResult],
    *,
    final_top_k: int,
    anchor_top_k: int,
    collect_trace: Literal[False] = False,
) -> tuple[list[core_types._ExpandedResult], list[EvidenceAnchor]]: ...


@overload
def _split_code_results_and_evidence_anchors(
    expanded: list[core_types._ExpandedResult],
    *,
    final_top_k: int,
    anchor_top_k: int,
    collect_trace: Literal[True],
) -> tuple[
    list[core_types._ExpandedResult],
    list[EvidenceAnchor],
    _FinalTraceDecisions,
]: ...


def _split_code_results_and_evidence_anchors(
    expanded: list[core_types._ExpandedResult],
    *,
    final_top_k: int,
    anchor_top_k: int,
    collect_trace: bool = False,
) -> (
    tuple[list[core_types._ExpandedResult], list[EvidenceAnchor]]
    | tuple[
        list[core_types._ExpandedResult],
        list[EvidenceAnchor],
        _FinalTraceDecisions,
    ]
):
    trace_selected: list[_FinalTraceInput] | None = (
        [] if collect_trace else None
    )
    trace_counts: dict[str, int] | None = (
        dict.fromkeys(_FINAL_TRACE_DECISION_KEYS, 0)
        if collect_trace
        else None
    )
    code_results: list[core_types._ExpandedResult] = []
    evidence_anchors: list[EvidenceAnchor] = []
    seen_anchor_keys: set[tuple[str, Path]] = set()

    for item in expanded:
        anchor_kind = _evidence_anchor_kind(item.file_path)
        if anchor_kind:
            anchor_key = (anchor_kind, item.file_path)
            if anchor_key in seen_anchor_keys:
                if trace_counts is not None:
                    trace_counts["duplicate_anchor"] += 1
                continue
            seen_anchor_keys.add(anchor_key)
            if len(evidence_anchors) < anchor_top_k:
                evidence_anchors.append(
                    _evidence_anchor_from_expanded(item, anchor_kind)
                )
                if trace_selected is not None and trace_counts is not None:
                    trace_selected.append(
                        _FinalTraceInput(
                            kind="evidence_anchor",
                            reason="selected_within_anchor_limit",
                            item=item,
                        )
                    )
                    trace_counts["selected_anchor"] += 1
            elif trace_counts is not None:
                trace_counts["anchor_limit"] += 1
            continue

        if len(code_results) < final_top_k:
            code_results.append(item)
            if trace_selected is not None and trace_counts is not None:
                trace_selected.append(
                    _FinalTraceInput(
                        kind="result",
                        reason="selected_within_result_limit",
                        item=item,
                    )
                )
                trace_counts["selected_result"] += 1
        elif trace_counts is not None:
            trace_counts["result_limit"] += 1

    if trace_selected is not None and trace_counts is not None:
        return (
            code_results,
            evidence_anchors,
            _FinalTraceDecisions(
                selected=tuple(trace_selected),
                counts=tuple(
                    (key, trace_counts[key])
                    for key in _FINAL_TRACE_DECISION_KEYS
                ),
            ),
        )
    return code_results, evidence_anchors


def _evidence_anchor_from_expanded(
    item: core_types._ExpandedResult,
    anchor_kind: str,
) -> EvidenceAnchor:
    return EvidenceAnchor(
        file_path=item.file_path,
        start_line=item.start_line,
        end_line=item.end_line,
        content=item.content,
        score=item.rerank_score,
        score_parts={
            **item.score_parts,
            "combined_score": item.score,
            "rerank_score": item.rerank_score,
            "evidence_priority": float(item.evidence_priority),
        },
        reasons=item.reasons,
        anchor_kind=anchor_kind,
        semantic_matches=item.semantic_matches,
        _context_content=item._context_content,
    )


def evidence_anchor_top_k(max_results: int) -> int:
    if max_results <= 0:
        return 0
    return max(1, min(5, max_results // 3))


def normalize_score(scores: list[float]) -> list[float]:
    return ranking.normalize_score(scores)


def _summarize_results(
    store: sqlite_store.SQLiteStore,
    visible_results: list[core_types._ExpandedResult],
) -> tuple[RetrievalSummary, list[list[str]]]:
    summary = RetrievalSummary()
    result_reasons: list[list[str]] = []

    for item in visible_results:
        entry_points: list[str] = []
        impl: list[str] = []
        related: list[str] = []
        legacy: list[str] = []
        chunk_reasons: list[str] = []

        for chunk_id in item.chunk_ids:
            try:
                chunk = store.chunk_for_id(chunk_id)
            except KeyError:
                continue
            try:
                signals = store.signals_for_chunk(chunk_id)
            except sqlite3.Error:
                signals = []

            has_endpoint_signal = any(signal.kind == "endpoint" for signal in signals)
            has_usage_signal = any(signal.kind == "usage" for signal in signals)
            has_relation_support = _chunk_has_relation_support(store, chunk, signals)

            (
                chunk_entry,
                chunk_impl,
                chunk_related,
                chunk_legacy,
            ) = _summarize_chunk(chunk, signals, has_relation_support)

            chunk_has_support = (
                has_endpoint_signal or has_usage_signal or has_relation_support
            )
            legacy_names = set(chunk_legacy)
            entry_points.extend(chunk_entry)
            impl.extend(chunk_impl)
            if chunk_has_support:
                related.extend(chunk_related)
            else:
                related.extend([name for name in chunk_related if name not in legacy_names])
                legacy.extend(chunk_legacy)
            chunk_reasons.extend(
                _reasons_for_chunk(
                    signals,
                    chunk_impl,
                    chunk_legacy,
                    has_relation_support,
                    has_endpoint_signal,
                    has_usage_signal,
                )
            )

        result_reasons.append(ordering.dedupe_lowered(chunk_reasons))
        summary.entry_points.extend(entry_points)
        summary.implementation.extend(impl)
        summary.related_types.extend(related)
        summary.possibly_legacy.extend(legacy)

    summary.entry_points = ordering.ordered_unique_preserving_case(summary.entry_points)
    summary.implementation = ordering.ordered_unique_preserving_case(summary.implementation)
    summary.related_types = ordering.ordered_unique_preserving_case(summary.related_types)
    summary.possibly_legacy = ordering.ordered_unique_preserving_case(summary.possibly_legacy)
    summary.entry_points.sort()
    summary.implementation.sort()
    summary.related_types.sort()
    summary.possibly_legacy.sort()
    return summary, result_reasons


def _summarize_chunk(
    chunk: DocumentChunk,
    signals: list,
    has_relation_support: bool,
) -> tuple[list[str], list[str], list[str], list[str]]:
    symbol_names = [symbol.name for symbol in chunk.symbols]
    endpoint: list[str] = []
    implementation: list[str] = []
    related_types: list[str] = []
    legacy: list[str] = []

    endpoint_signals = [signal.name for signal in signals if signal.kind == "endpoint"]
    if endpoint_signals:
        endpoint.extend(ordering.ordered_unique_preserving_case(endpoint_signals))
    elif _is_controller_name(chunk.file_path.stem) or any(
        _is_controller_name(name) for name in symbol_names
    ):
        endpoint.append(_primary_chunk_name(chunk))

    names = ordering.ordered_unique_preserving_case(
        [signal.name for signal in signals] + symbol_names + [_primary_chunk_name(chunk)]
    )
    method_impl_names = [
        name for name in names if _is_implementation_name(name) and "." in name
    ]
    if method_impl_names:
        implementation.extend(method_impl_names)
    else:
        implementation.extend(
            [name for name in names if _is_implementation_name(name) and "." not in name]
        )
    related_types.extend([name for name in names if _is_related_type_name(name)])

    if not endpoint and not has_relation_support and not implementation:
        legacy.extend([name for name in related_types if name])
    if has_relation_support and implementation and not any(
        "." in item for item in implementation
    ):
        implementation.extend([_primary_chunk_name(chunk)])

    return (
        ordering.ordered_unique_preserving_case(endpoint),
        ordering.ordered_unique_preserving_case(implementation),
        ordering.ordered_unique_preserving_case(related_types),
        ordering.ordered_unique_preserving_case(legacy),
    )


def _reasons_for_chunk(
    signals: list,
    impl_names: list[str],
    legacy_names: list[str],
    has_relation_support: bool,
    has_endpoint_signal: bool,
    has_usage_signal: bool,
) -> list[str]:
    reasons: list[str] = []
    if any(signal.kind == "endpoint" for signal in signals):
        reasons.append("endpoint signal match")
    if any(signal.kind == "comment" for signal in signals):
        reasons.append("comment signal match")
    if has_relation_support and impl_names:
        reasons.append("implementation chain match")
    if legacy_names and not has_relation_support and not has_usage_signal and not has_endpoint_signal:
        reasons.append("possibly legacy: no active usage signal found")
    return reasons


def _chunk_has_relation_support(
    store: sqlite_store.SQLiteStore,
    chunk: DocumentChunk,
    signals: list[CodeSignal],
) -> bool:
    signal_ids = [signal.signal_id for signal in signals]
    for signal_id in signal_ids:
        try:
            if store.relations_for_source(signal_id):
                return True
        except sqlite3.Error:
            continue

    relation_targets = ordering.ordered_unique_preserving_case(
        [chunk.file_path.stem] + [signal.name for signal in signals]
    )
    for target_name in relation_targets:
        try:
            if store.relations_targeting(target_name):
                return True
        except sqlite3.Error:
            continue

    return False


def _primary_chunk_name(chunk: DocumentChunk) -> str:
    if chunk.file_path.stem:
        return chunk.file_path.stem
    return ""


def _is_controller_name(value: str) -> bool:
    return value.lower().endswith("controller")


def _is_implementation_name(value: str) -> bool:
    lowered = value.lower()
    if "." in lowered:
        owner, _ = lowered.split(".", 1)
        if owner.endswith(("serviceimpl", "service", "impl")):
            return True
        return _is_implementation_name(owner)
    return any(
        lowered.endswith(suffix)
        for suffix in (
            "service",
            "serviceimpl",
            "impl",
            "executor",
            "exe",
            "gateway",
            "mapper",
            "repository",
        )
    )


def _is_related_type_name(value: str) -> bool:
    lowered = value.lower()
    return any(
        lowered.endswith(suffix)
        for suffix in (
            "dto",
            "vo",
            "request",
            "response",
            "query",
            "querytype",
            "domain",
            "type",
            "enum",
            "entity",
            "model",
            "bean",
        )
    ) or "domain" in lowered


def _evidence_anchor_kind(path: Path) -> str:
    name = path.name.lower()
    stem = path.stem.lower()
    if path.suffix.lower() == ".md" and stem.startswith("readme"):
        return "readme"
    if path.suffix.lower() == ".md" and stem.startswith("risks"):
        return "risks"
    if name == "pom.xml":
        return "pom"
    return ""


def _expand_ranked_chunks(
    repo: Path,
    ranked_chunks: list[core_types._RankedChunk],
    config: ToolConfig,
    context_lines: int | None,
    full_file: bool,
) -> list[core_types._ExpandedResult]:
    expanded: list[core_types._ExpandedResult] = []
    for ranked in ranked_chunks:
        source_path = repo / ranked.chunk.file_path
        try:
            file_size = source_path.stat().st_size
            file_content = source_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            file_content = ranked.chunk.content
            file_size = len(file_content.encode("utf-8"))

        lines = file_content.splitlines()
        if full_file and file_size <= config.index.max_full_file_bytes:
            start_line = 1
            end_line = len(lines)
            content = file_content
            context_content = file_content
        else:
            before, after = _context_window(config, context_lines)
            start_line, end_line, content = chunker.expand_lines(
                lines,
                ranked.chunk.start_line,
                ranked.chunk.end_line,
                before,
                after,
            )
            context_content = _join_expanded_result_lines(
                lines[start_line - 1 : end_line]
            )
        if full_file:
            end_line, content = _cap_content_bytes(
                content,
                start_line,
                config.index.max_full_file_bytes,
            )
            _, context_content = _cap_content_bytes(
                context_content,
                start_line,
                config.index.max_full_file_bytes,
            )
            context_content = _context_content_for_range(
                context_content,
                start_line,
                end_line,
            )

        expanded.append(
            core_types._ExpandedResult(
                chunk_ids=[ranked.chunk.chunk_id],
                file_path=ranked.chunk.file_path,
                start_line=start_line,
                end_line=end_line,
                content=content,
                score=ranked.score,
                score_parts=ranked.score_parts,
                reasons=ranked.reasons,
                followup_keywords=ranked.chunk.lexical_tokens,
                rank_tier=ranked.rank_tier,
                rerank_score=ranked.rerank_score,
                evidence_class=ranked.evidence_class,
                evidence_priority=ranked.evidence_priority,
                semantic_matches=ranked.semantic_matches,
                pre_ceiling_rerank_score=ranked.pre_ceiling_rerank_score,
                was_ceiling_clamped=ranked.was_ceiling_clamped,
                spans=_normalize_spans(
                    (
                        RetrievalSpan(
                            start_line=ranked.chunk.start_line,
                            end_line=ranked.chunk.end_line,
                            score=(
                                ranked.rerank_score
                                if math.isfinite(ranked.rerank_score)
                                else 0.0
                            ),
                            sources=_span_sources(ranked.score_parts),
                        ),
                    ),
                    start_line,
                    end_line,
                ),
                _context_content=context_content,
            )
        )

    merged = _merge_overlapping_results(expanded)
    if not full_file:
        return merged
    return [
        _cap_expanded_result(result, config.index.max_full_file_bytes)
        for result in merged
    ]


def _cap_content_bytes(
    content: str,
    start_line: int,
    max_bytes: int,
) -> tuple[int, str]:
    encoded = content.encode("utf-8")
    if len(encoded) <= max_bytes:
        return _end_line_for_content(start_line, content), content
    if max_bytes <= 0:
        return start_line, ""

    trimmed = encoded[:max_bytes].decode("utf-8", errors="ignore")
    return _end_line_for_content(start_line, trimmed), trimmed


def _cap_expanded_result(
    result: core_types._ExpandedResult,
    max_bytes: int,
) -> core_types._ExpandedResult:
    end_line, content = _cap_content_bytes(
        result.content,
        result.start_line,
        max_bytes,
    )
    source_context_content = result._context_content
    if source_context_content is None:
        source_context_content = result.content
    _, context_content = _cap_content_bytes(
        source_context_content,
        result.start_line,
        max_bytes,
    )
    context_content = _context_content_for_range(
        context_content,
        result.start_line,
        end_line,
    )
    return core_types._ExpandedResult(
        chunk_ids=result.chunk_ids,
        file_path=result.file_path,
        start_line=result.start_line,
        end_line=end_line,
        content=content,
        score=result.score,
        score_parts=result.score_parts,
        reasons=result.reasons,
        followup_keywords=result.followup_keywords,
        rank_tier=result.rank_tier,
        rerank_score=result.rerank_score,
        evidence_class=result.evidence_class,
        evidence_priority=result.evidence_priority,
        semantic_matches=result.semantic_matches,
        pre_ceiling_rerank_score=result.pre_ceiling_rerank_score,
        was_ceiling_clamped=result.was_ceiling_clamped,
        spans=_normalize_spans(result.spans, result.start_line, end_line),
        _context_content=context_content,
    )


def _end_line_for_content(start_line: int, content: str) -> int:
    if not content:
        return start_line
    return start_line + max(0, len(content.splitlines()) - 1)


def _merge_overlapping_results(results: list[core_types._ExpandedResult]) -> list[core_types._ExpandedResult]:
    by_file: dict[Path, list[core_types._ExpandedResult]] = {}
    for result in results:
        by_file.setdefault(result.file_path, []).append(result)

    merged: list[core_types._ExpandedResult] = []
    for file_path, file_results in by_file.items():
        sorted_results = sorted(
            file_results,
            key=lambda item: (item.start_line, item.end_line, -item.score),
        )
        current: core_types._ExpandedResult | None = None
        for result in sorted_results:
            if current is None:
                current = result
                continue
            if result.start_line <= current.end_line + 1:
                current = _merge_expanded_result(current, result)
                continue
            merged.append(current)
            current = result
        if current is not None:
            merged.append(current)

    return sorted(
        merged,
        key=_expanded_result_sort_key,
    )


def _expanded_result_sort_key(
    item: core_types._ExpandedResult,
) -> tuple[float, int, int, float, float, float, float, str, int]:
    return (
        -round(item.rerank_score, ordering.RERANK_SORT_DECIMALS),
        item.evidence_priority,
        0 if item.was_ceiling_clamped else 1,
        -(item.pre_ceiling_rerank_score if item.was_ceiling_clamped else 0.0),
        item.score_parts.get("role_priority", 99.0),
        -item.rerank_score,
        -item.score,
        item.file_path.as_posix(),
        item.start_line,
    )


def _merge_expanded_result(
    left: core_types._ExpandedResult,
    right: core_types._ExpandedResult,
) -> core_types._ExpandedResult:
    left_lines = left.content.splitlines()
    right_lines = right.content.splitlines()
    overlap = max(0, left.end_line - right.start_line + 1)
    content_lines = [*left_lines, *right_lines[overlap:]]
    left_context_lines = _expanded_result_lines(left)
    right_context_lines = _expanded_result_lines(right)
    context_lines = [*left_context_lines, *right_context_lines[overlap:]]

    winner = min(left, right, key=_expanded_result_sort_key)

    # Merge score_parts: max for most fields, winner value for rerank-related fields
    merged_score_parts = evidence_merge.merge_score_parts(left.score_parts, right.score_parts)
    merged_score_parts["rerank_score"] = winner.rerank_score
    # evidence_priority is smaller-is-better, so use winner's value
    merged_score_parts["evidence_priority"] = float(winner.evidence_priority)
    for key in (
        "role_priority",
        "role_boost",
        "role_penalty",
        "file_hint_match_boost",
        "role_exact_match_boost",
        "identifier_exact_match_boost",
        "path_role_hint_boost",
        "path_role_mismatch_penalty",
        "impl_match_boost",
        "relation_role_boost",
        "relation_detail_penalty",
        "frontend_import_support_boost",
    ):
        if key in winner.score_parts:
            merged_score_parts[key] = winner.score_parts[key]
        else:
            merged_score_parts.pop(key, None)

    start_line = min(left.start_line, right.start_line)
    end_line = max(left.end_line, right.end_line)
    return core_types._ExpandedResult(
        chunk_ids=ordering.dedupe_lowered([*left.chunk_ids, *right.chunk_ids]),
        file_path=left.file_path,
        start_line=start_line,
        end_line=end_line,
        content="\n".join(content_lines),
        score=max(left.score, right.score),
        score_parts=merged_score_parts,
        reasons=winner.reasons,
        followup_keywords=ordering.dedupe_lowered([*left.followup_keywords, *right.followup_keywords]),
        rank_tier=min(left.rank_tier, right.rank_tier),
        rerank_score=winner.rerank_score,
        evidence_class=winner.evidence_class,
        evidence_priority=winner.evidence_priority,
        semantic_matches=evidence_merge.merge_semantic_matches(
            left.semantic_matches,
            right.semantic_matches,
        ),
        pre_ceiling_rerank_score=winner.pre_ceiling_rerank_score,
        was_ceiling_clamped=winner.was_ceiling_clamped,
        spans=_normalize_spans(
            (*left.spans, *right.spans),
            start_line,
            end_line,
        ),
        _context_content=_join_expanded_result_lines(context_lines),
    )


def _expanded_result_lines(result: core_types._ExpandedResult) -> list[str]:
    expected_count = result.end_line - result.start_line + 1
    content = result._context_content
    if content is None:
        content = result.content
    lines = content.splitlines()
    if not lines:
        lines = [""]
    if len(lines) != expected_count:
        raise ValueError("expanded result content does not match its line range")
    return lines


def _context_content_for_range(content: str, start_line: int, end_line: int) -> str:
    lines = content.splitlines()
    if not lines:
        lines = [""]
    return _join_expanded_result_lines(lines[: end_line - start_line + 1])


def _join_expanded_result_lines(lines: list[str]) -> str:
    content = "\n".join(lines)
    if len(lines) > 1 and lines[-1] == "":
        content += "\n"
    if max(1, len(content.splitlines(keepends=True))) != len(lines):
        raise ValueError("expanded result lines cannot be represented exactly")
    return content


def _span_sources(score_parts: dict[str, float]) -> tuple[str, ...]:
    sources = tuple(
        source
        for source in _SPAN_SOURCE_KEYS
        if any(
            score_parts.get(score_key, 0.0) > 0.0
            for score_key in _SPAN_SOURCE_SCORE_KEYS[source]
        )
    )
    return sources or ("ranked",)


def _normalize_spans(
    spans: tuple[RetrievalSpan, ...],
    start_line: int,
    end_line: int,
) -> tuple[RetrievalSpan, ...]:
    visible_end = max(start_line, end_line)
    normalized: list[RetrievalSpan] = []
    for span in spans:
        span_start = min(max(span.start_line, start_line), visible_end)
        span_end = min(max(span.end_line, span_start), visible_end)
        normalized.append(
            RetrievalSpan(
                start_line=span_start,
                end_line=span_end,
                score=span.score if math.isfinite(span.score) else 0.0,
                sources=span.sources or ("ranked",),
            )
        )

    ordered = sorted(
        normalized,
        key=lambda span: (
            span.start_line,
            span.end_line,
            -span.score,
            span.sources,
        ),
    )
    deduplicated: list[RetrievalSpan] = []
    seen_windows: set[tuple[int, int]] = set()
    for span in ordered:
        window = (span.start_line, span.end_line)
        if window in seen_windows:
            continue
        seen_windows.add(window)
        deduplicated.append(span)
    return tuple(deduplicated)


def _context_window(
    config: ToolConfig,
    context_lines: int | None,
) -> tuple[int, int]:
    if context_lines is not None:
        bounded = max(0, context_lines)
        return bounded, bounded
    return (
        max(0, config.retrieval.context_before_lines),
        max(0, config.retrieval.context_after_lines),
    )


def _followup_keywords(results: list[RetrievalResult]) -> list[str]:
    counts: Counter[str] = Counter()
    for result in results:
        counts.update(token for token in result.followup_keywords if token)
    return [
        token
        for token, _count in sorted(
            counts.items(),
            key=lambda item: (-item[1], item[0]),
        )[:12]
    ]
