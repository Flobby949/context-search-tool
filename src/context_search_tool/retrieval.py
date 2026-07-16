from __future__ import annotations

import logging
import math
import re
import sqlite3
from collections import Counter
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Literal, overload

from context_search_tool import chunker, sqlite_store, tokenizer
from context_search_tool.config import ToolConfig
from context_search_tool.frontend_roles import (
    classify_frontend_role,
    extract_static_imports,
    frontend_candidate_scope_enabled,
    frontend_score_parts,
    resolve_frontend_import,
)
from context_search_tool.identifier_intent import IdentifierIntent, infer_identifier_intent
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
from context_search_tool.path_roles import PathRole, classify_path_role
from context_search_tool.paths import index_dir_for
from context_search_tool.project_scope import (
    QueryScope,
    infer_query_scope,
    project_scope_rerank_adjustment,
    project_scope_score_parts,
    project_units_from_chunk_metadata,
)
from context_search_tool.query_intent import QueryIntent, infer_query_intent
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
    file_roles,
    ordering,
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


logger = logging.getLogger(__name__)

MAX_EXPANSION_DEPTH = relation_policy.MAX_EXPANSION_DEPTH
MAX_EXPANSION_CANDIDATES = relation_policy.MAX_EXPANSION_CANDIDATES
_RELATION_SCORE_DECAY = 0.8

_NON_SOURCE_ARTIFACT_DISPLAY_PENALTIES = {
    "doc": 0.45,
    "test": 0.25,
    "deployment_config": 0.35,
    "config_example": 0.35,
    "runtime_config": 0.25,
    "config": 0.20,
    "generated_output": 0.45,
    "lockfile": 0.35,
}
_ROUTE_EXACT_MATCH_BOOST = 0.35
_ROUTE_PREFIX_MATCH_BOOST = 0.12
_ROUTE_SIBLING_PENALTY = 0.18
_ROUTE_MISMATCH_PENALTY = 0.30
_ROUTE_TAIL_CONTEXT_MATCH_BOOST = 0.22
_JAVA_CONTEXT_MIN_TOKEN_OVERLAP = 2
_JAVA_METHOD_CONTEXT_MATCH_BOOST = 0.14
_JAVA_FIELD_CONTEXT_MATCH_BOOST = 0.12
_JAVA_EXECUTOR_CONTEXT_BOOST = 0.10
_SPRING_PATH_ENDPOINT_BOOST = 0.45
_SPRING_PATH_SERVICE_BOOST = 0.30
_SPRING_PATH_SERVICE_INTERFACE_BOOST = 0.10
_SPRING_PATH_EXECUTOR_BOOST = 0.28
_SPRING_PATH_MAX_DEPTH = 2
_JAVA_CONTEXT_STRUCTURAL_TOKENS = {
    "src",
    "main",
    "test",
    "java",
    "com",
    "org",
    "net",
}
_FRONTEND_ENTRYPOINT_NAMES = {"main.ts", "main.tsx", "main.js", "main.jsx"}
_SEMANTIC_SCORE_WEIGHT = 0.55
_PLANNER_SEMANTIC_WEIGHT = 0.85
_FRONTEND_IMPORT_SCAN_TOP_K = 10
_FRONTEND_IMPORT_SCAN_FILE_LIMIT = 3
_FRONTEND_IMPORT_MAX_FILE_BYTES = 50_000
_FRONTEND_IMPORT_SUPPORT_BOOST = 0.30
_FRONTEND_IMPORT_ANCHOR_EPSILON = 10 ** -ordering.RERANK_SORT_DECIMALS
_FRONTEND_IMPORT_ANCHOR_ROLES = {
    "view_page",
    "layout_component",
    "shared_component",
}
_FRONTEND_IMPORT_SUPPORT_ROLES = {
    "service",
    "utility",
    "store",
    "type_decl",
    "shared_component",
}
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
class _ChunkRole:
    name: str
    priority: int
    boost: float
    penalty: float = 0.0


@dataclass(frozen=True)
class _RelationSeed:
    score: float
    planner_seeded: bool
    original_seeded: bool


@dataclass(frozen=True)
class _SpringPathImplementor:
    interface_name: str
    simple_name: str
    is_qualified: bool
    chunk_id: str


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
    anchor_candidates = _anchor_expansion_candidates(
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
    relation_candidates = _relation_expansion_candidates(
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
    ranked_chunks = _rank_chunks(store, merged_candidates, original_tokens, query)
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
    ranked_chunks = _apply_frontend_import_cohort_rerank(repo, ranked_chunks, query)
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


def _anchor_expansion_candidates(
    store: sqlite_store.SQLiteStore,
    seed_candidates: list[RetrievalCandidate],
    config: ToolConfig,
    query: str = "",
    tokens: list[str] | None = None,
) -> list[RetrievalCandidate]:
    direct_seeds = [
        candidate
        for candidate in seed_candidates
        if candidate.score_parts.get("direct_text", 0.0) > 0
    ]
    if not direct_seeds:
        return []

    limit = max(config.retrieval.final_top_k * 3, config.retrieval.final_top_k)
    expanded: dict[str, RetrievalCandidate] = {}
    seed_ids = {candidate.chunk_id for candidate in direct_seeds}
    query_tokens = tokens or []

    for candidate in sorted(
        direct_seeds,
        key=lambda item: (
            -item.score_parts.get("direct_text", item.score),
            item.chunk_id,
        ),
    ):
        try:
            anchor_chunk = store.chunk_for_id(candidate.chunk_id)
        except KeyError:
            continue
        anchor_score = evidence_merge.bounded_score(
            candidate.score_parts.get("direct_text", candidate.score)
        )
        _add_same_file_anchor_candidates(
            store,
            expanded,
            seed_ids,
            anchor_chunk,
            anchor_score,
            limit,
            query,
            query_tokens,
        )
        if _is_document_or_config_anchor(anchor_chunk.file_path):
            _add_directory_anchor_candidates(
                store,
                expanded,
                seed_ids,
                anchor_chunk,
                anchor_score,
                limit,
            )
        if len(expanded) >= limit:
            break

    return list(expanded.values())


def _add_same_file_anchor_candidates(
    store: sqlite_store.SQLiteStore,
    expanded: dict[str, RetrievalCandidate],
    seed_ids: set[str],
    anchor_chunk: DocumentChunk,
    anchor_score: float,
    limit: int,
    query: str,
    tokens: list[str],
) -> None:
    score = anchor_score * 0.80
    for chunk in store.chunks_for_file(anchor_chunk.file_path, limit):
        if chunk.chunk_id in seed_ids:
            continue
        if _should_skip_same_file_anchor_candidate(chunk, query, tokens):
            continue
        _put_anchor_candidate(
            expanded,
            chunk.chunk_id,
            score,
            "same_file_anchor",
        )
        if len(expanded) >= limit:
            return


def _should_skip_same_file_anchor_candidate(
    chunk: DocumentChunk,
    query: str,
    tokens: list[str],
) -> bool:
    role = file_roles._generic_file_role(chunk, query, tokens)
    return role.name == "generated_schema" or (
        role.name == "template" and role.penalty > 0
    )


def _add_directory_anchor_candidates(
    store: sqlite_store.SQLiteStore,
    expanded: dict[str, RetrievalCandidate],
    seed_ids: set[str],
    anchor_chunk: DocumentChunk,
    anchor_score: float,
    limit: int,
) -> None:
    score = anchor_score * 0.55
    for chunk in store.chunks_in_directory(anchor_chunk.file_path.parent, limit):
        if chunk.chunk_id in seed_ids:
            continue
        if _is_document_or_config_anchor(chunk.file_path):
            continue
        _put_anchor_candidate(
            expanded,
            chunk.chunk_id,
            score,
            "directory_anchor",
        )
        if len(expanded) >= limit:
            return


def _put_anchor_candidate(
    expanded: dict[str, RetrievalCandidate],
    chunk_id: str,
    score: float,
    anchor_key: str,
) -> None:
    existing = expanded.get(chunk_id)
    if existing is not None and existing.score >= score:
        return
    score_parts = {
        "anchored_relation": score,
        "original_relation": score,
        anchor_key: score,
    }
    expanded[chunk_id] = RetrievalCandidate(
        chunk_id=chunk_id,
        score=score,
        source="anchored_relation",
        score_parts=score_parts,
    )


def _is_document_or_config_anchor(path: Path) -> bool:
    suffix = path.suffix.lower()
    return suffix in {".md", ".yml", ".yaml", ".json", ".properties"}


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


def _relation_expansion_candidates(
    store: sqlite_store.SQLiteStore,
    seed_candidates: list[RetrievalCandidate],
    config: ToolConfig,
) -> list[RetrievalCandidate]:
    if not seed_candidates:
        return []

    source_limit = max(
        config.retrieval.semantic_top_k
        + config.retrieval.lexical_top_k
        + config.retrieval.final_top_k,
        config.retrieval.final_top_k,
    )
    if source_limit <= 0:
        return []

    expanded_by_chunk: dict[str, RetrievalCandidate] = {}
    seen_chunks = {candidate.chunk_id for candidate in seed_candidates}
    seed_scores = {
        candidate.chunk_id: _candidate_relation_seed(candidate)
        for candidate in seed_candidates
    }
    visited_signals: set[str] = set()
    frontier: list[tuple[str, float, int, bool, bool]] = []
    ordered_seed_candidates = sorted(
        seed_candidates,
        key=lambda item: (
            _relation_seed_source_priority(item.score_parts),
            -seed_scores[item.chunk_id].score,
            item.chunk_id,
        ),
    )[:source_limit]
    seed_chunk_ids = [
        candidate.chunk_id
        for candidate in ordered_seed_candidates
        if seed_scores[candidate.chunk_id].score > 0
    ]
    seed_signals_by_chunk = store.signals_for_chunks(seed_chunk_ids)

    for candidate in ordered_seed_candidates:
        relation_seed = seed_scores[candidate.chunk_id]
        if relation_seed.score <= 0:
            continue
        for signal in seed_signals_by_chunk.get(candidate.chunk_id, []):
            if signal.signal_id in visited_signals:
                continue
            visited_signals.add(signal.signal_id)
            frontier.append(
                (
                    signal.signal_id,
                    relation_seed.score,
                    0,
                    relation_seed.planner_seeded,
                    relation_seed.original_seeded,
                )
            )

    while frontier:
        active_frontier = [
            source
            for source in frontier
            if source[2] < relation_policy.MAX_EXPANSION_DEPTH
        ]
        if not active_frontier:
            break

        relations_by_source = store.relations_for_sources(
            [source_signal_id for source_signal_id, *_ in active_frontier]
        )
        relation_steps: list[tuple[str, float, int, bool, bool]] = []
        target_names: list[str] = []
        for (
            source_signal_id,
            current_score,
            depth,
            planner_seeded,
            original_seeded,
        ) in active_frontier:
            next_depth = depth + 1
            for relation in relations_by_source.get(source_signal_id, []):
                if relation.confidence < relation_policy._MIN_RELATION_CONFIDENCE:
                    continue
                next_score = (
                    current_score * relation.confidence * _RELATION_SCORE_DECAY
                )
                relation_steps.append(
                    (
                        relation.target_name,
                        next_score,
                        next_depth,
                        planner_seeded,
                        original_seeded,
                    )
                )
                target_names.append(relation.target_name)

        if not relation_steps:
            break

        remaining = relation_policy.MAX_EXPANSION_CANDIDATES - len(expanded_by_chunk)
        if remaining <= 0:
            _log_expansion_limit()
            return sorted(
                expanded_by_chunk.values(),
                key=lambda candidate: (-candidate.score, candidate.chunk_id),
            )
        chunks_by_target = store.chunks_matching_signal_or_symbols(
            target_names,
            remaining,
        )
        reached_chunk_ids: list[str] = []
        signal_seed_by_chunk: dict[str, tuple[float, int, bool, bool]] = {}
        for (
            target_name,
            next_score,
            next_depth,
            planner_seeded,
            original_seeded,
        ) in relation_steps:
            remaining = (
                relation_policy.MAX_EXPANSION_CANDIDATES - len(expanded_by_chunk)
            )
            if remaining <= 0:
                _log_expansion_limit()
                return sorted(
                    expanded_by_chunk.values(),
                    key=lambda candidate: (-candidate.score, candidate.chunk_id),
                )

            for chunk in chunks_by_target.get(target_name, [])[:remaining]:
                existing = expanded_by_chunk.get(chunk.chunk_id)
                seed_score = seed_scores.get(
                    chunk.chunk_id,
                    _RelationSeed(0.0, False, False),
                ).score
                should_add_relation = (
                    chunk.chunk_id not in seed_scores or next_score > seed_score
                )
                if should_add_relation and (
                    existing is None or next_score > existing.score
                ):
                    score_parts = {"relation": next_score}
                    if planner_seeded:
                        score_parts["planner_relation"] = next_score
                    if original_seeded:
                        score_parts["original_relation"] = next_score
                    expanded_by_chunk[chunk.chunk_id] = RetrievalCandidate(
                        chunk_id=chunk.chunk_id,
                        score=next_score,
                        source="relation",
                        score_parts=score_parts,
                    )

                if chunk.chunk_id not in seen_chunks:
                    seen_chunks.add(chunk.chunk_id)
                    if (
                        len(expanded_by_chunk)
                        >= relation_policy.MAX_EXPANSION_CANDIDATES
                    ):
                        _log_expansion_limit()
                        return sorted(
                            expanded_by_chunk.values(),
                            key=lambda candidate: (
                                -candidate.score,
                                candidate.chunk_id,
                            ),
                        )

                next_signal_seed = (
                    next_score,
                    next_depth,
                    planner_seeded,
                    original_seeded,
                )
                existing_signal_seed = signal_seed_by_chunk.get(chunk.chunk_id)
                if existing_signal_seed is None:
                    signal_seed_by_chunk[chunk.chunk_id] = next_signal_seed
                    reached_chunk_ids.append(chunk.chunk_id)
                elif next_score > existing_signal_seed[0]:
                    signal_seed_by_chunk[chunk.chunk_id] = next_signal_seed

        next_frontier: list[tuple[str, float, int, bool, bool]] = []
        if reached_chunk_ids:
            signals_by_chunk = store.signals_for_chunks(reached_chunk_ids)
            for chunk_id in reached_chunk_ids:
                (
                    next_score,
                    next_depth,
                    planner_seeded,
                    original_seeded,
                ) = signal_seed_by_chunk[chunk_id]
                for signal in signals_by_chunk.get(chunk_id, []):
                    if signal.signal_id in visited_signals:
                        continue
                    visited_signals.add(signal.signal_id)
                    next_frontier.append(
                        (
                            signal.signal_id,
                            next_score,
                            next_depth,
                            planner_seeded,
                            original_seeded,
                        )
                    )
        frontier = next_frontier

    return sorted(
        expanded_by_chunk.values(),
        key=lambda candidate: (-candidate.score, candidate.chunk_id),
    )


def _candidate_base_score(candidate: RetrievalCandidate) -> float:
    return evidence_merge.bounded_score(max(candidate.score, *candidate.score_parts.values(), 0.0))


def _relation_seed_source_priority(score_parts: dict[str, float]) -> int:
    if score_parts.get("relation", 0.0) > 0:
        return 0
    if score_parts.get("signal", 0.0) > 0:
        return 1
    if score_parts.get("direct_text", 0.0) > 0:
        return 2
    if max(
        score_parts.get("anchored_relation", 0.0),
        score_parts.get("same_file_anchor", 0.0),
        score_parts.get("directory_anchor", 0.0),
    ) > 0:
        return 3
    if score_parts.get("planner_signal", 0.0) > 0:
        return 4
    return 5


def _candidate_relation_seed(candidate: RetrievalCandidate) -> _RelationSeed:
    relation_score = candidate.score_parts.get("relation", 0.0)
    if relation_score > 0:
        planner_seeded = candidate.score_parts.get("planner_relation", 0.0) > 0
        original_seeded = candidate.score_parts.get("original_relation", 0.0) > 0
        if not planner_seeded and not original_seeded:
            original_seeded = True
        return _RelationSeed(
            evidence_merge.bounded_score(relation_score),
            planner_seeded,
            original_seeded,
        )

    signal_score = candidate.score_parts.get("signal", 0.0)
    planner_signal_score = candidate.score_parts.get("planner_signal", 0.0)
    if signal_score > 0:
        return _RelationSeed(
            evidence_merge.bounded_score(signal_score),
            planner_signal_score > 0,
            True,
        )

    direct_text_score = candidate.score_parts.get("direct_text", 0.0)
    if direct_text_score > 0:
        return _RelationSeed(
            evidence_merge.bounded_score(direct_text_score),
            False,
            True,
        )

    anchored_score = max(
        candidate.score_parts.get("anchored_relation", 0.0),
        candidate.score_parts.get("same_file_anchor", 0.0),
        candidate.score_parts.get("directory_anchor", 0.0),
    )
    if anchored_score > 0:
        return _RelationSeed(
            evidence_merge.bounded_score(anchored_score),
            False,
            True,
        )

    if planner_signal_score > 0:
        return _RelationSeed(
            evidence_merge.bounded_score(planner_signal_score) * 0.65,
            True,
            False,
        )

    return _RelationSeed(0.0, False, False)


def _log_expansion_limit() -> None:
    logger.warning(
        "relation expansion hit candidate limit (%s); returning partial candidates",
        relation_policy.MAX_EXPANSION_CANDIDATES,
    )


def _rank_chunks(
    store: sqlite_store.SQLiteStore,
    candidates: dict[str, RetrievalCandidate],
    tokens: list[str],
    query: str,
) -> list[core_types._RankedChunk]:
    # First pass: compute scores and build ranked list
    ranked: list[core_types._RankedChunk] = []
    all_combined_scores: list[float] = []
    signal_cache: dict[str, list[CodeSignal]] = {}
    query_route = _query_route(query)
    candidate_chunks = store.chunks_for_ids(list(candidates))
    project_units = project_units_from_chunk_metadata(tuple(candidate_chunks.values()))
    query_scope = infer_query_scope(query, tokens, project_units)
    identifier_intent = infer_identifier_intent(query, tokens)
    query_intent = infer_query_intent(query, tokens)
    frontend_enabled = frontend_candidate_scope_enabled(
        chunk.file_path for chunk in candidate_chunks.values()
    )
    spring_path_parts = _spring_path_score_parts(
        store,
        candidate_chunks,
        query_route,
    )
    java_context_tokens = _java_context_query_tokens(tokens, query_route)

    def signals_for_ranked_chunk(chunk_id: str) -> list[CodeSignal]:
        if chunk_id not in signal_cache:
            try:
                signal_cache[chunk_id] = store.signals_for_chunk(chunk_id)
            except sqlite3.Error:
                signal_cache[chunk_id] = []
        return signal_cache[chunk_id]

    for candidate in candidates.values():
        chunk = candidate_chunks.get(candidate.chunk_id)
        if chunk is None:
            continue
        signals: list[CodeSignal] | None = None

        def get_signals() -> list[CodeSignal]:
            nonlocal signals
            if signals is None:
                signals = signals_for_ranked_chunk(candidate.chunk_id)
            return signals

        score_parts = evidence_merge.merge_score_parts(
            dict(candidate.score_parts),
            spring_path_parts.get(candidate.chunk_id, {}),
        )
        coverage = _token_coverage(tokens, chunk)
        if coverage:
            score_parts["token_coverage"] = coverage

        plugin_boost = _plugin_boost(chunk)
        route_boost = _route_boost(chunk, query, tokens)
        plugin_boost += route_boost
        if plugin_boost:
            score_parts["plugin_boost"] = plugin_boost
        if route_boost:
            score_parts["route_boost"] = route_boost

        score_parts = evidence_merge.merge_score_parts(
            score_parts,
            _generic_noise_score_parts(chunk, query, tokens),
        )
        path_role = classify_path_role(chunk.file_path, chunk.content)
        score_parts = evidence_merge.merge_score_parts(
            score_parts,
            _query_intent_score_parts(path_role, query_intent),
        )
        penalty = abs(min(score_parts.get("penalty", 0.0), 0.0))

        if query_route and _chunk_looks_route_relevant(
            chunk,
            tokens,
            query_route,
            route_boost=route_boost,
        ):
            route_score_parts = _route_score_parts(
                get_signals(),
                query,
                query_route=query_route,
            )
            score_parts.update(route_score_parts)

        role = _chunk_role(chunk)
        if query_route:
            score_parts.update(_route_tail_context_score_parts(chunk, query_route, role))
        if _should_apply_java_context_score(chunk, java_context_tokens, role, penalty):
            score_parts.update(
                _java_context_score_parts(get_signals(), java_context_tokens, role)
            )

        score_parts = evidence_merge.merge_score_parts(
            score_parts,
            project_scope_score_parts(
                chunk,
                query_scope,
                project_unit_count=len(project_units),
            ),
        )
        score_parts = evidence_merge.merge_score_parts(
            score_parts,
            _frontend_entrypoint_scope_score_parts(chunk, query_scope, score_parts),
        )
        score_parts = evidence_merge.merge_score_parts(
            score_parts,
            _identifier_intent_score_parts(chunk, identifier_intent, path_role),
        )
        score_parts = evidence_merge.merge_score_parts(
            score_parts,
            frontend_score_parts(chunk.file_path, query, enabled=frontend_enabled),
        )

        score_parts = _with_effective_semantic(score_parts)
        score = _combined_score(score_parts)
        all_combined_scores.append(score)
        has_signal_evidence = score_parts.get("signal", 0.0) > 0
        rank_tier_signals = get_signals() if has_signal_evidence else None

        # Precompute flags for rerank scoring
        flags = {
            'has_endpoint_signal': has_signal_evidence and any(
                signal.kind == "endpoint" for signal in rank_tier_signals or []
            ),
            'is_controller': penalty == 0 and 'controller' in chunk.file_path.as_posix().lower(),
            'has_relation_support': score_parts.get("original_relation", 0.0) > 0 or score_parts.get("planner_relation", 0.0) > 0,
            'role_name': role.name,
            'role_priority': role.priority,
        }

        ranked.append({
            'chunk': chunk,
            'score': score,
            'score_parts': score_parts,
            'flags': flags,
            'role': role,
            'path_role': path_role,
            'signals': rank_tier_signals,
        })

    # Normalize all combined scores
    normalized_scores = normalize_score(all_combined_scores)

    # Update ranked items with normalized scores and compute unclamped rerank scores
    for i, item in enumerate(ranked):
        normalized_score = normalized_scores[i]
        evidence_class = _evidence_class(item['score_parts'])
        evidence_priority = _evidence_priority(evidence_class)

        # Compute unclamped rerank score
        rerank_score = _rerank_score(
            normalized_score,
            item['score_parts'],
            item['chunk'],
            item['flags'],
            item['role'],
            path_role=item['path_role'],
            query_intent=query_intent,
            planner_ceiling=None,
        )

        item['normalized_score'] = normalized_score
        item['pre_ceiling_rerank_score'] = rerank_score
        item['rerank_score'] = rerank_score
        item['evidence_class'] = evidence_class
        item['evidence_priority'] = evidence_priority

    strong_direct_results = [
        r for r in ranked
        if _has_strong_original_direct_evidence(r['score_parts'])
    ]
    # Prefer business-chain anchors, but preserve exact detail-only queries.
    ceiling_anchor_results = [
        r for r in strong_direct_results
        if r['role'].name not in {"handler", "constant_or_config"}
    ] or strong_direct_results

    # Compute planner_ceiling from strong direct results
    if ceiling_anchor_results:
        planner_ceiling = min(r['rerank_score'] for r in ceiling_anchor_results) * (1.0 - 1e-6)
    else:
        planner_ceiling = None

    # Second pass: apply ceiling clamp to non-strong evidence classes
    for item in ranked:
        item["was_ceiling_clamped"] = (
            item["evidence_class"] in _CLAMPED_EVIDENCE_CLASSES
            and planner_ceiling is not None
            and item["rerank_score"] > planner_ceiling
        )
        if item["was_ceiling_clamped"]:
            item["rerank_score"] = planner_ceiling

        score_parts = item['score_parts']
        score_parts["combined_score"] = float(item['score'])
        score_parts["rerank_score"] = float(item['rerank_score'])
        score_parts["evidence_priority"] = float(item['evidence_priority'])
        score_parts["role_priority"] = float(item['role'].priority)
        score_parts["role_boost"] = (
            0.0
            if _has_project_scope_mismatch(score_parts)
            else float(item['role'].boost)
        )

    # Cohort coherence: in multi-unit repos, demote candidates outside the
    # Top1 anchor's project unit so cross-unit lexical or call-reference
    # matches do not interleave with the anchor's cohort. The anchor is the
    # prerank Top1 by rerank_score; it is never penalized, so Top1 is stable.
    # Conservative: skipped for mixed-scope queries and for chunks lacking
    # explicit project metadata. Does not enter _combined_score.
    if len(project_units) > 1:
        anchor_item = max(ranked, key=lambda item: item['rerank_score'])
        anchor_unit = _chunk_project_unit(anchor_item['chunk'])
        if anchor_unit and not _query_scope_is_mixed(query_scope):
            for item in ranked:
                if item is anchor_item:
                    continue
                candidate_unit = _chunk_project_unit(item['chunk'])
                if candidate_unit and candidate_unit != anchor_unit:
                    item['rerank_score'] -= _COHORT_MISMATCH_PENALTY
                    cohort_parts = item['score_parts']
                    cohort_parts["cohort_mismatch_penalty"] = -_COHORT_MISMATCH_PENALTY
                    cohort_parts["rerank_score"] = float(item['rerank_score'])

    # Build final _RankedChunk objects
    final_ranked = [
        core_types._RankedChunk(
            chunk=item['chunk'],
            score=item['score'],
            score_parts=item['score_parts'],
            reasons=_reasons(item['score_parts'], query),
            rank_tier=_rank_tier(store, item['chunk'], item['score_parts'], item['signals']),
            rerank_score=item['rerank_score'],
            evidence_class=item['evidence_class'],
            evidence_priority=item['evidence_priority'],
            semantic_matches=candidates[item['chunk'].chunk_id].semantic_matches,
            pre_ceiling_rerank_score=item['pre_ceiling_rerank_score'],
            was_ceiling_clamped=item['was_ceiling_clamped'],
        )
        for item in ranked
    ]

    return sorted(
        final_ranked,
        key=_ranked_chunk_sort_key,
    )


def _ranked_chunk_sort_key(
    item: core_types._RankedChunk,
) -> tuple[float, int, int, float, float, float, float, str, int, str]:
    return (
        -round(item.rerank_score, ordering.RERANK_SORT_DECIMALS),
        item.evidence_priority,
        0 if item.was_ceiling_clamped else 1,
        -(item.pre_ceiling_rerank_score if item.was_ceiling_clamped else 0.0),
        item.score_parts.get("role_priority", 99.0),
        -item.rerank_score,
        -item.score,
        item.chunk.file_path.as_posix(),
        item.chunk.start_line,
        item.chunk.chunk_id,
    )


def _apply_frontend_import_cohort_rerank(
    repo: Path,
    ranked_chunks: list[core_types._RankedChunk],
    query: str,
) -> list[core_types._RankedChunk]:
    import_anchor_scores: dict[str, float] = {}
    files_read = 0

    for ranked in ranked_chunks[:_FRONTEND_IMPORT_SCAN_TOP_K]:
        if files_read >= _FRONTEND_IMPORT_SCAN_FILE_LIMIT:
            break
        anchor_role = classify_frontend_role(ranked.chunk.file_path).name
        if anchor_role not in _FRONTEND_IMPORT_ANCHOR_ROLES:
            continue

        try:
            content = _read_frontend_import_anchor(repo / ranked.chunk.file_path)
        except OSError:
            continue

        files_read += 1
        anchor_path = ranked.chunk.file_path.as_posix()
        for specifier in extract_static_imports(content):
            resolved = resolve_frontend_import(repo, ranked.chunk.file_path, specifier)
            if resolved and resolved != anchor_path:
                import_anchor_scores[resolved] = max(
                    ranked.rerank_score,
                    import_anchor_scores.get(resolved, float("-inf")),
                )

    if not import_anchor_scores:
        return ranked_chunks

    adjusted: list[core_types._RankedChunk] = []
    for ranked in ranked_chunks:
        path = ranked.chunk.file_path.as_posix()
        role = classify_frontend_role(ranked.chunk.file_path).name
        if path not in import_anchor_scores or role not in _FRONTEND_IMPORT_SUPPORT_ROLES:
            adjusted.append(ranked)
            continue

        score_parts = dict(ranked.score_parts)
        existing_boost = score_parts.get("frontend_import_support_boost", 0.0)
        boost_delta = max(0.0, _FRONTEND_IMPORT_SUPPORT_BOOST - existing_boost)
        if boost_delta <= 0:
            adjusted.append(ranked)
            continue

        anchor_ceiling = import_anchor_scores[path] - _FRONTEND_IMPORT_ANCHOR_EPSILON
        rerank_score = min(ranked.rerank_score + boost_delta, anchor_ceiling)
        applied_boost = rerank_score - ranked.rerank_score
        if applied_boost <= 0:
            adjusted.append(ranked)
            continue

        score_parts["frontend_import_support_boost"] = applied_boost
        score_parts["rerank_score"] = rerank_score
        adjusted.append(
            core_types._RankedChunk(
                chunk=ranked.chunk,
                score=ranked.score,
                score_parts=score_parts,
                reasons=_reasons(score_parts, query),
                rank_tier=ranked.rank_tier,
                rerank_score=rerank_score,
                evidence_class=ranked.evidence_class,
                evidence_priority=ranked.evidence_priority,
                semantic_matches=ranked.semantic_matches,
                pre_ceiling_rerank_score=ranked.pre_ceiling_rerank_score,
                was_ceiling_clamped=ranked.was_ceiling_clamped,
            )
        )

    return sorted(adjusted, key=_ranked_chunk_sort_key)


def _read_frontend_import_anchor(path: Path) -> str:
    with path.open("rb") as handle:
        return handle.read(_FRONTEND_IMPORT_MAX_FILE_BYTES).decode(
            "utf-8",
            errors="replace",
        )


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


def _chunk_role(chunk: DocumentChunk) -> _ChunkRole:
    path = chunk.file_path.as_posix().lower()
    names = " ".join(symbol.name for symbol in chunk.symbols).lower()
    content = chunk.content.lower()
    haystack = f"{path} {names} {content}"
    path_and_names = f"{path} {names}"

    if file_roles._is_test_path(path):
        return _ChunkRole("generic", 5, 0.0)
    if "controller" in path or "controller" in names:
        return _ChunkRole("entrypoint", 0, 0.18)
    if "/service/impl/" in path or "serviceimpl" in path_and_names:
        return _ChunkRole("service_impl", 1, 0.12)
    class_names = [chunk.file_path.stem.lower(), *(symbol.name.lower() for symbol in chunk.symbols)]
    if any(name.endswith(("queryexe", "qryexe", "executor", "queryexecutor", "exe")) for name in class_names):
        return _ChunkRole("executor", 2, 0.12)
    if any(token in path for token in ("/dto/", "/vo/", "/query/", "/entity/")):
        return _ChunkRole("data_type", 3, 0.04)
    if "/service/" in path and "interface " in content:
        return _ChunkRole("service_interface", 4, 0.06)
    if "/service/" in path:
        return _ChunkRole("service", 2, 0.0)
    if "/mapper/" in path or "mapper" in names:
        return _ChunkRole("mapper", 4, 0.03)
    if any(token in haystack for token in ("handler", "listener", "callback", "connector", "webhook")):
        return _ChunkRole("handler", 5, 0.0, 0.10)
    if any(token in haystack for token in ("constant", "config", "buildermanager", "parambuilder")):
        return _ChunkRole("constant_or_config", 6, 0.0, 0.12)
    return _ChunkRole("generic", 5, 0.0)


def _with_effective_semantic(score_parts: dict[str, float]) -> dict[str, float]:
    updated = dict(score_parts)
    original_exists = "semantic" in updated
    planner_exists = "planner_semantic" in updated
    if not original_exists and not planner_exists:
        return updated

    adjusted_planner: float | None = None
    if planner_exists:
        planner_score = updated["planner_semantic"]
        adjusted_planner = planner_score * _PLANNER_SEMANTIC_WEIGHT if planner_score > 0 else planner_score

    if original_exists and adjusted_planner is not None:
        effective = max(updated["semantic"], adjusted_planner)
    elif original_exists:
        effective = updated["semantic"]
    else:
        assert adjusted_planner is not None
        effective = adjusted_planner
    updated["effective_semantic"] = effective
    return updated


def _combined_score(score_parts: dict[str, float]) -> float:
    return (
        score_parts.get("effective_semantic", score_parts.get("semantic", 0.0))
        * _SEMANTIC_SCORE_WEIGHT
        + (score_parts.get("lexical", 0.0) * 0.25)
        + (min(score_parts.get("path_symbol", 0.0), 5.0) / 5.0 * 0.15)
        + (score_parts.get("planner_lexical", 0.0) * 0.12)
        + (
            min(score_parts.get("planner_path_symbol", 0.0), 5.0)
            / 5.0
            * 0.07
        )
        + evidence_merge.bounded_score(score_parts.get("signal", 0.0))
        + (evidence_merge.bounded_score(score_parts.get("planner_signal", 0.0)) * 0.65)
        + evidence_merge.bounded_score(score_parts.get("relation", 0.0))
        + evidence_merge.bounded_score(score_parts.get("original_relation", 0.0))
        + evidence_merge.bounded_score(score_parts.get("planner_relation", 0.0))
        + (evidence_merge.bounded_score(score_parts.get("anchored_relation", 0.0)) * 0.75)
        + (score_parts.get("token_coverage", 0.0) * 0.20)
        + (evidence_merge.bounded_score(score_parts.get("direct_text", 0.0)) * 0.45)  # High weight for literal text matches in comments/strings
        + score_parts.get("plugin_boost", 0.0)
        + score_parts.get("route_exact_match", 0.0)
        + score_parts.get("route_prefix_match", 0.0)
        + score_parts.get("route_sibling_penalty", 0.0)
        + score_parts.get("route_mismatch_penalty", 0.0)
        + score_parts.get("route_tail_context_match", 0.0)
        + score_parts.get("java_method_context_match", 0.0)
        + score_parts.get("java_field_context_match", 0.0)
        + score_parts.get("java_executor_context_boost", 0.0)
        + score_parts.get("spring_path_endpoint_match", 0.0)
        + score_parts.get("spring_path_service_match", 0.0)
        + score_parts.get("spring_path_service_interface_match", 0.0)
        + score_parts.get("spring_path_executor_match", 0.0)
        + score_parts.get("file_role_source_boost", 0.0)
        + score_parts.get("frontend_entrypoint_boost", 0.0)
        + score_parts.get("frontend_support_boost", 0.0)
        + score_parts.get("frontend_support_name_match_boost", 0.0)
        + score_parts.get("penalty", 0.0)
    )


# Thresholds for strong evidence classification
_STRONG_SEMANTIC_EVIDENCE = 0.35
_STRONG_LEXICAL_EVIDENCE = 0.25
_STRONG_PATH_SYMBOL_EVIDENCE = 1.0
_STRONG_SIGNAL_EVIDENCE = 0.5

_CLAMPED_EVIDENCE_CLASSES = {
    "weak_original_direct",
    "original_relation",
    "planner_direct",
    "planner_relation",
    "weak_or_generic",
}


def _has_original_direct_evidence(score_parts: dict[str, float]) -> bool:
    """
    Check if score_parts contains direct original query evidence.

    This is similar to _has_original_query_evidence but excludes original_relation.
    Used to distinguish direct matches from relation-only expansion results.

    Args:
        score_parts: Dictionary of score components

    Returns:
        True if any direct evidence exists (semantic, lexical, path_symbol, signal, token_coverage, direct_text)
    """
    return any(
        score_parts.get(key, 0.0) > 0
        for key in (
            "semantic",
            "lexical",
            "path_symbol",
            "signal",
            "token_coverage",
            "direct_text",
        )
    )


def _has_planner_direct_evidence(score_parts: dict[str, float]) -> bool:
    """
    Check if score_parts contains direct planner evidence (excluding planner_relation).

    Args:
        score_parts: Dictionary of score components

    Returns:
        True if any planner direct evidence exists
    """
    return any(
        score_parts.get(key, 0.0) > 0
        for key in (
            "planner_semantic",
            "planner_lexical",
            "planner_signal",
            "planner_path_symbol",
        )
    )


def _has_strong_original_direct_evidence(score_parts: dict[str, float]) -> bool:
    """
    Check if score_parts contains strong original direct evidence.

    Used to compute dynamic planner_ceiling. Strong evidence means at least one
    of the direct signals exceeds its threshold.

    Args:
        score_parts: Dictionary of score components

    Returns:
        True if any strong evidence threshold is met
    """
    token_coverage = score_parts.get("token_coverage", 0.0)
    corroborated_text_match = token_coverage >= 0.2 and (
        score_parts.get("semantic", 0.0) >= _STRONG_SEMANTIC_EVIDENCE
        or score_parts.get("lexical", 0.0) >= _STRONG_LEXICAL_EVIDENCE
    )
    return (
        corroborated_text_match
        or score_parts.get("path_symbol", 0.0) >= _STRONG_PATH_SYMBOL_EVIDENCE
        or score_parts.get("signal", 0.0) >= _STRONG_SIGNAL_EVIDENCE
        or token_coverage >= 0.5
        or score_parts.get("direct_text", 0.0) >= 0.60
    )


def _has_weak_original_direct_evidence(score_parts: dict[str, float]) -> bool:
    return (
        _has_original_direct_evidence(score_parts)
        and not _has_strong_original_direct_evidence(score_parts)
    )


def _evidence_class(score_parts: dict[str, float]) -> str:
    """
    Classify evidence type using the established decision order.

    Decision order:
    1. original_direct: has strong direct original evidence
    2. weak_original_direct: has weak direct original evidence
    3. planner_direct: has planner direct evidence
    4. original_relation: has original_relation score only
    5. planner_relation: has planner_relation score only
    6. weak_or_generic: fallback for everything else

    Args:
        score_parts: Dictionary of score components

    Returns:
        Evidence class string
    """
    if _has_strong_original_direct_evidence(score_parts):
        return "original_direct"
    if _has_weak_original_direct_evidence(score_parts):
        return "weak_original_direct"
    if _has_planner_direct_evidence(score_parts):
        return "planner_direct"
    if score_parts.get("original_relation", 0.0) > 0:
        return "original_relation"
    if score_parts.get("planner_relation", 0.0) > 0:
        return "planner_relation"
    return "weak_or_generic"


def _evidence_priority(evidence_class: str) -> int:
    """
    Map evidence class to numeric priority (0 is highest priority).

    Args:
        evidence_class: Evidence class string from _evidence_class

    Returns:
        Priority value 0-4
    """
    priority_map = {
        "original_direct": 0,
        "weak_original_direct": 1,
        "planner_direct": 1,
        "original_relation": 2,
        "planner_relation": 3,
        "weak_or_generic": 4,
    }
    return priority_map.get(evidence_class, 4)


def normalize_score(scores: list[float]) -> list[float]:
    """
    Normalize scores to [0, 1] range using max normalization.

    Args:
        scores: List of raw scores

    Returns:
        List of normalized scores in [0, 1] range
    """
    if not scores:
        return []

    # Handle NaN/inf values by clipping to 0.0
    cleaned_scores = []
    for s in scores:
        if s != s or s == float('inf') or s == float('-inf'):  # NaN or inf check
            cleaned_scores.append(0.0)
        else:
            cleaned_scores.append(s)

    max_score = max(cleaned_scores)

    if max_score <= 0.0:
        return [0.0] * len(cleaned_scores)

    if len(cleaned_scores) == 1:
        return [1.0]

    return [max(s, 0.0) / max_score for s in cleaned_scores]


def _generic_hint_penalty(chunk: DocumentChunk, score_parts: dict[str, float]) -> float:
    """
    Return penalty for generic symbols that match too broadly.

    Generic patterns include: Service, Controller, Manager, message, device.
    These often get weak lexical/path matches but aren't semantically relevant.

    Args:
        chunk: The document chunk to check
        score_parts: Score components (unused but kept for future extension)

    Returns:
        Penalty value (e.g., 0.1 for generic symbols, 0.0 otherwise)
    """
    generic_patterns = [
        "Service",
        "Controller",
        "Manager",
        "message",
        "device",
    ]

    content_lower = chunk.content.lower()
    path_str = str(chunk.file_path).lower()

    for pattern in generic_patterns:
        if pattern.lower() in content_lower or pattern.lower() in path_str:
            return 0.1

    return 0.0


def _rerank_score(
    normalized_score: float,
    score_parts: dict[str, float],
    chunk: DocumentChunk,
    flags: dict,
    role: _ChunkRole,
    *,
    path_role: PathRole | None = None,
    query_intent: QueryIntent = QueryIntent(),
    planner_ceiling: float | None,
) -> float:
    """
    Compute rerank score with boosts, penalties, and ceiling clamp.

    Formula:
        rerank_score = normalized_score
            + original_direct_boost (strong direct +0.2, weak direct +0.05)
            + endpoint_or_controller_boost (if endpoint or controller)
            + implementation_chain_boost (if has relation support)
            + role_boost
            - role_penalty
            - non_source_artifact_penalty
            - planner_only_penalty (if planner-only, no original evidence)
            - relation_only_penalty (if only relation, no direct evidence)
            - generic_hint_penalty

    Then apply ceiling clamp for non-strong evidence classes if planner_ceiling is set.

    Args:
        normalized_score: Normalized combined score
        score_parts: Score components dictionary
        chunk: The document chunk
        flags: Precomputed flags dict with keys:
            - has_endpoint_signal: bool
            - is_controller: bool
            - has_relation_support: bool
        role: Role classification with boost/penalty metadata
        path_role: Optional artifact/source role for display demotion
        query_intent: Inferred query intent used for artifact escapes
        planner_ceiling: Optional ceiling for planner/relation evidence classes

    Returns:
        Final rerank score
    """
    rerank_score = normalized_score
    has_project_scope_mismatch = _has_project_scope_mismatch(score_parts)

    # Boosts
    if score_parts.get("penalty", 0.0) < 0:
        pass
    elif _has_strong_original_direct_evidence(score_parts):
        rerank_score += 0.2
    elif _has_weak_original_direct_evidence(score_parts):
        rerank_score += 0.05

    if (
        not has_project_scope_mismatch
        and (
            flags.get("has_endpoint_signal", False)
            or flags.get("is_controller", False)
        )
    ):
        rerank_score += 0.15

    if not has_project_scope_mismatch and flags.get("has_relation_support", False):
        rerank_score += 0.1

    if not has_project_scope_mismatch:
        rerank_score += role.boost
        if role.boost:
            score_parts["role_boost"] = role.boost
    role_penalty = (
        0.0
        if _has_explicit_handler_path_evidence(role, score_parts)
        else role.penalty
    )
    if role_penalty:
        rerank_score -= role_penalty
        score_parts["role_penalty"] = -role_penalty

    artifact_penalty = _non_source_artifact_display_penalty(
        path_role,
        query_intent,
        score_parts,
    )
    if artifact_penalty:
        rerank_score -= artifact_penalty
        score_parts["non_source_artifact_penalty"] = -artifact_penalty
        score_parts[
            f"artifact_display_{path_role.name}_penalty"
        ] = -artifact_penalty

    role_exact_boost = 0.0
    if not has_project_scope_mismatch:
        role_exact_boost = _role_exact_match_boost(role, score_parts)
    if role_exact_boost:
        rerank_score += role_exact_boost
        score_parts["role_exact_match_boost"] = role_exact_boost

    file_hint_boost = 0.0
    if not has_project_scope_mismatch:
        file_hint_boost = _file_hint_match_boost(score_parts)
    if file_hint_boost:
        rerank_score += file_hint_boost
        score_parts["file_hint_match_boost"] = file_hint_boost

    if not has_project_scope_mismatch:
        if score_parts.get("identifier_exact_match_boost", 0.0) > 0:
            rerank_score += score_parts["identifier_exact_match_boost"]
        if score_parts.get("path_role_hint_boost", 0.0) > 0:
            rerank_score += score_parts["path_role_hint_boost"]
        if score_parts.get("path_role_mismatch_penalty", 0.0) < 0:
            rerank_score += score_parts["path_role_mismatch_penalty"]

    rerank_score += _route_rerank_adjustment(score_parts)
    rerank_score += score_parts.get("route_tail_context_match", 0.0)
    rerank_score += _spring_path_rerank_adjustment(score_parts)
    rerank_score += project_scope_rerank_adjustment(score_parts)
    if not has_project_scope_mismatch:
        rerank_score += _frontend_entrypoint_rerank_adjustment(score_parts)
        rerank_score += _frontend_support_name_rerank_adjustment(score_parts)
    if not has_project_scope_mismatch:
        rerank_score += _query_intent_rerank_adjustment(score_parts)

    if (
        not has_project_scope_mismatch
        and role.name == "service_impl"
        and score_parts.get("path_symbol", 0.0) >= 1.0
        and score_parts.get("token_coverage", 0.0) >= 0.25
    ):
        rerank_score += 0.18
        score_parts["impl_match_boost"] = 0.18

    if (
        not has_project_scope_mismatch
        and flags.get("has_relation_support", False)
        and role.name in {
            "service_impl",
            "executor",
            "data_type",
            "service_interface",
            "mapper",
        }
    ):
        rerank_score += 0.08
        score_parts["relation_role_boost"] = 0.08
    if flags.get("has_relation_support", False) and role.name in {
        "handler",
        "constant_or_config",
    }:
        rerank_score -= 0.06
        score_parts["relation_detail_penalty"] = -0.06

    # Penalties (only apply when there's a ceiling from strong direct evidence)
    if planner_ceiling is not None:
        if _is_planner_hint_only(score_parts):
            rerank_score -= 0.3

        if not _has_original_direct_evidence(score_parts) and (
            score_parts.get("original_relation", 0.0) > 0 or score_parts.get("planner_relation", 0.0) > 0
        ):
            rerank_score -= 0.2

        rerank_score -= _generic_hint_penalty(chunk, score_parts)

    # Apply ceiling clamp for non-strong evidence
    evidence_class = _evidence_class(score_parts)
    if (
        evidence_class in _CLAMPED_EVIDENCE_CLASSES
        and planner_ceiling is not None
    ):
        rerank_score = min(rerank_score, planner_ceiling)

    return rerank_score


def _has_project_scope_mismatch(score_parts: dict[str, float]) -> bool:
    return score_parts.get("project_scope_mismatch_penalty", 0.0) < 0


def _frontend_entrypoint_rerank_adjustment(score_parts: dict[str, float]) -> float:
    boost = score_parts.get("frontend_entrypoint_boost", 0.0)
    if boost <= 0.0:
        return 0.0
    if (
        score_parts.get("token_coverage", 0.0) >= 0.50
        or score_parts.get("path_symbol", 0.0) >= 3.0
        or score_parts.get("direct_text", 0.0) >= 0.75
    ):
        return boost
    return 0.0


def _frontend_support_name_rerank_adjustment(score_parts: dict[str, float]) -> float:
    boost = score_parts.get("frontend_support_name_match_boost", 0.0)
    if boost <= 0.0:
        return 0.0
    if (
        score_parts.get("token_coverage", 0.0) >= 0.50
        or score_parts.get("path_symbol", 0.0) >= 3.0
        or score_parts.get("direct_text", 0.0) >= 0.75
    ):
        return boost
    return 0.0


_COHORT_MISMATCH_PENALTY = 0.05


def _chunk_project_unit(chunk: DocumentChunk) -> str:
    return str(chunk.metadata.get("project_name", ""))


def _query_scope_is_mixed(query_scope: QueryScope) -> bool:
    return (
        len(query_scope.project_names) > 1
        or len(query_scope.kinds) > 1
        or len(query_scope.path_prefixes) > 1
    )


def _role_exact_match_boost(
    role: _ChunkRole,
    score_parts: dict[str, float],
) -> float:
    path_symbol = score_parts.get("path_symbol", 0.0)
    token_coverage = score_parts.get("token_coverage", 0.0)
    if role.name == "entrypoint" and path_symbol >= 4.0 and token_coverage >= 0.5:
        return 0.12
    if role.name == "service_impl" and path_symbol >= 4.0 and token_coverage >= 0.5:
        return 0.35
    if role.name == "service" and path_symbol >= 4.0 and token_coverage >= 0.5:
        return 0.35
    if role.name == "data_type" and path_symbol >= 2.0 and token_coverage >= 0.2:
        return 0.24
    if _has_explicit_handler_path_evidence(role, score_parts):
        return 0.08
    return 0.0


_LOGIC_OPERATION_NAMES = {"save", "update", "delete", "download", "scan", "generate", "retry"}
_LOGIC_PATH_ROLES = {
    "entrypoint",
    "router",
    "service",
    "service_impl",
    "service_interface",
    "executor",
    "handler",
    "middleware",
    "repository",
    "source_adapter",
    "storage",
    "command",
    "engine",
    "scheduler",
    "state_store",
    "composable",
    "view",
    "component",
}
_CONFIG_ARTIFACT_ROLES = {
    "deployment_config",
    "config_example",
    "runtime_config",
    "lockfile",
}
_LOGIC_TARGET_ROLES = {"entrypoint", "implementation", "ui"}


def _query_intent_score_parts(
    path_role: PathRole,
    intent: QueryIntent,
) -> dict[str, float]:
    if intent.confidence == 0:
        return {}

    parts: dict[str, float] = {}
    operation_query = bool(
        intent.operations.intersection(_LOGIC_OPERATION_NAMES)
        and (intent.target_roles or intent.artifact_roles)
    )
    logic_operation_query = bool(
        intent.operations.intersection(_LOGIC_OPERATION_NAMES)
        and intent.target_roles.intersection(_LOGIC_TARGET_ROLES)
    )
    wants_deployment = "deploy" in intent.target_roles and intent.wants_artifact
    wants_docs = "doc" in intent.target_roles and intent.wants_artifact
    wants_tests = "test" in intent.target_roles and intent.wants_artifact

    if logic_operation_query and path_role.name in _LOGIC_PATH_ROLES:
        parts["query_operation_logic_boost"] = 0.10

    if "config" in intent.target_roles and path_role.name in {
        "entrypoint",
        "router",
        "service",
        "service_impl",
        "handler",
        "state_store",
        "composable",
        "view",
        "component",
    }:
        parts["config_logic_boost"] = 0.12

    if wants_deployment and path_role.name == "deployment_config":
        parts["deployment_config_boost"] = 0.18

    if wants_docs and path_role.name == "doc":
        parts["doc_artifact_boost"] = 0.12

    if wants_tests and path_role.name == "test":
        parts["test_artifact_boost"] = 0.12

    if (
        operation_query
        and not intent.wants_artifact
        and path_role.name in _CONFIG_ARTIFACT_ROLES
    ):
        parts["penalty"] = -0.35
        parts["config_artifact_penalty"] = -0.35

    if (
        operation_query
        and not intent.wants_artifact
        and path_role.name == "generated_output"
    ):
        parts["penalty"] = -0.45
        parts["generated_output_penalty"] = -0.45

    if (
        operation_query
        and not intent.wants_artifact
        and path_role.name in {"doc", "test"}
    ):
        parts["penalty"] = -0.20
        parts[f"{path_role.name}_artifact_penalty"] = -0.20

    return parts


def _non_source_artifact_display_penalty(
    path_role: PathRole | None,
    intent: QueryIntent,
    score_parts: dict[str, float],
) -> float:
    if path_role is None:
        return 0.0
    penalty = _NON_SOURCE_ARTIFACT_DISPLAY_PENALTIES.get(path_role.name, 0.0)
    if not penalty:
        return 0.0
    if path_role.name == "config" and score_parts.get("file_role_source_boost", 0.0) > 0:
        return 0.0
    if _artifact_role_is_requested(path_role.name, intent, score_parts):
        return 0.0
    return penalty


def _artifact_role_is_requested(
    path_role_name: str,
    intent: QueryIntent,
    score_parts: dict[str, float],
) -> bool:
    if _has_explicit_artifact_file_hint(score_parts):
        return True
    if path_role_name == "doc":
        return "doc" in intent.target_roles and intent.wants_artifact
    if path_role_name == "test":
        return "test" in intent.target_roles and intent.wants_artifact
    if path_role_name in {
        "config",
        "runtime_config",
        "config_example",
        "deployment_config",
    }:
        return bool(
            intent.wants_artifact
            and intent.target_roles.intersection({"config", "deploy"})
        )
    if path_role_name == "lockfile":
        return bool(
            score_parts.get("explicit_lockfile_query", 0.0) > 0
            or (
                intent.wants_artifact
                and "config_artifact" in intent.artifact_roles
            )
        )
    if path_role_name == "generated_output":
        return bool(
            intent.wants_artifact
            and "generated_artifact" in intent.artifact_roles
        )
    return False


def _has_explicit_artifact_file_hint(score_parts: dict[str, float]) -> bool:
    return any(
        score_parts.get(key, 0.0) > 0
        for key in (
            "explicit_artifact_file_hint",
            "file_hint_match_boost",
            "project_file_hint_boost",
            "project_path_hint_boost",
            "path_role_hint_boost",
        )
    )


def _query_intent_rerank_adjustment(score_parts: dict[str, float]) -> float:
    if not _has_query_intent_rerank_evidence(score_parts):
        return 0.0
    return (
        score_parts.get("query_operation_logic_boost", 0.0)
        + score_parts.get("config_logic_boost", 0.0)
        + score_parts.get("deployment_config_boost", 0.0)
        + score_parts.get("doc_artifact_boost", 0.0)
        + score_parts.get("test_artifact_boost", 0.0)
    )


def _has_query_intent_rerank_evidence(score_parts: dict[str, float]) -> bool:
    return (
        score_parts.get("token_coverage", 0.0) >= 0.35
        or score_parts.get("path_symbol", 0.0) >= 1.5
        or score_parts.get("direct_text", 0.0) >= 0.55
        or score_parts.get("lexical", 0.0) >= 0.35
    )


def _identifier_intent_score_parts(
    chunk: DocumentChunk,
    intent: IdentifierIntent,
    path_role: PathRole,
) -> dict[str, float]:
    parts: dict[str, float] = {}
    identifier_score = _identifier_exact_match_score(chunk, intent)
    if identifier_score:
        parts["identifier_exact_match_boost"] = identifier_score

    explicit_file_hint_score = _explicit_artifact_file_hint_score(chunk, intent)
    if explicit_file_hint_score:
        parts["explicit_artifact_file_hint"] = explicit_file_hint_score

    role_score = _path_role_hint_score(path_role, intent)
    if role_score:
        parts["path_role_hint_boost"] = role_score

    if _strong_role_mismatch(path_role, intent, identifier_score):
        parts["path_role_mismatch_penalty"] = -0.08

    return parts


def _frontend_entrypoint_scope_score_parts(
    chunk: DocumentChunk,
    query_scope,
    score_parts: dict[str, float],
) -> dict[str, float]:
    if "frontend" not in query_scope.kinds:
        return {}
    if _has_project_scope_mismatch(score_parts):
        return {}
    if not any(
        score_parts.get(key, 0.0) > 0
        for key in (
            "project_scope_boost",
            "project_kind_boost",
            "project_language_boost",
            "project_path_hint_boost",
        )
    ):
        return {}

    path = chunk.file_path.as_posix().lower()
    if chunk.file_path.name.lower() not in _FRONTEND_ENTRYPOINT_NAMES:
        return {}
    if not (path.startswith("src/") or "/src/" in path):
        return {}
    if (
        score_parts.get("path_symbol", 0.0) < 1.0
        or score_parts.get("direct_text", 0.0) < 0.60
        or score_parts.get("token_coverage", 0.0) < 0.50
    ):
        return {}

    return {"path_role_hint_boost": 0.14}


def _identifier_exact_match_score(
    chunk: DocumentChunk,
    intent: IdentifierIntent,
) -> float:
    if not intent.identifiers and not intent.file_hints:
        return 0.0

    path_text = chunk.file_path.as_posix().lower()
    stem_text = chunk.file_path.stem.lower()
    content_text = chunk.content.lower()
    symbol_names = {symbol.name.lower() for symbol in chunk.symbols}
    score = 0.0

    for file_hint in intent.file_hints:
        normalized = file_hint.lower()
        if normalized in path_text:
            score = max(score, 0.40)
        elif normalized in content_text:
            score = max(score, 0.30)

    matched_identifiers = 0
    for identifier in intent.identifiers:
        normalized = identifier.lower()
        if normalized in symbol_names or normalized == stem_text or normalized in path_text:
            matched_identifiers += 1
            score = max(score, 0.30)
        elif normalized in content_text:
            matched_identifiers += 1
            score = max(score, 0.20)

    if matched_identifiers > 1:
        repeated_identifier_bonus = 0.05 * (matched_identifiers - 1)
        if matched_identifiers > 2:
            repeated_identifier_bonus += 0.05
        score += min(0.15, repeated_identifier_bonus)

    return min(score, 0.40)


def _explicit_artifact_file_hint_score(
    chunk: DocumentChunk,
    intent: IdentifierIntent,
) -> float:
    for file_hint in intent.file_hints:
        normalized = file_hint.lower()
        if normalized and normalized in chunk.file_path.as_posix().lower():
            return 0.40
    return 0.0


def _path_role_hint_score(path_role: PathRole, intent: IdentifierIntent) -> float:
    if _path_role_matches_intent(path_role, intent.role_hints):
        if path_role.name == "service_interface":
            return 0.08
        return 0.14
    return 0.0


def _path_role_matches_intent(path_role: PathRole, role_hints: tuple[str, ...]) -> bool:
    if path_role.name in role_hints:
        return True
    compatible_hints = {
        "service_impl": {"service"},
        "service_interface": {"service"},
    }
    return bool(compatible_hints.get(path_role.name, set()).intersection(role_hints))


def _strong_role_mismatch(
    path_role: PathRole,
    intent: IdentifierIntent,
    identifier_score: float,
) -> bool:
    if identifier_score > 0:
        return False
    if not intent.role_hints:
        return False
    high_confidence_roles = {
        "state_store",
        "composable",
        "command",
        "engine",
        "handler",
        "middleware",
        "service",
        "repository",
        "source_adapter",
        "storage",
    }
    return (
        bool(set(intent.role_hints).intersection(high_confidence_roles))
        and not _path_role_matches_intent(path_role, intent.role_hints)
    )


def _file_hint_match_boost(score_parts: dict[str, float]) -> float:
    if (
        _has_explicit_file_hint(score_parts)
        and score_parts.get("path_symbol", 0.0) >= 4.0
        and score_parts.get("token_coverage", 0.0) >= 0.5
        and score_parts.get("direct_text", 0.0) >= 0.60
    ):
        return 0.40
    return 0.0


def _has_explicit_file_hint(score_parts: dict[str, float]) -> bool:
    return (
        score_parts.get("project_path_hint_boost", 0.0) > 0
        or score_parts.get("project_file_hint_boost", 0.0) > 0
    )


def _has_explicit_handler_path_evidence(
    role: _ChunkRole,
    score_parts: dict[str, float],
) -> bool:
    return (
        role.name == "handler"
        and _has_explicit_file_hint(score_parts)
        and score_parts.get("path_symbol", 0.0) >= 4.0
        and score_parts.get("token_coverage", 0.0) >= 0.5
        and score_parts.get("direct_text", 0.0) >= 0.60
    )


def _route_rerank_adjustment(score_parts: dict[str, float]) -> float:
    if score_parts.get("route_exact_match", 0.0) > 0:
        return score_parts["route_exact_match"]
    if score_parts.get("route_prefix_match", 0.0) > 0:
        return score_parts["route_prefix_match"]
    if score_parts.get("route_sibling_penalty", 0.0) < 0:
        return score_parts["route_sibling_penalty"]
    if score_parts.get("route_mismatch_penalty", 0.0) < 0:
        return score_parts["route_mismatch_penalty"]
    return 0.0


def _spring_path_rerank_adjustment(score_parts: dict[str, float]) -> float:
    return (
        score_parts.get("spring_path_endpoint_match", 0.0)
        + score_parts.get("spring_path_service_match", 0.0)
        + score_parts.get("spring_path_service_interface_match", 0.0)
        + score_parts.get("spring_path_executor_match", 0.0)
    )


def _rank_tier(
    store: sqlite_store.SQLiteStore,
    chunk: DocumentChunk,
    score_parts: dict[str, float],
    signals: list[CodeSignal] | None = None,
) -> int:
    has_signal_evidence = score_parts.get("signal", 0.0) > 0
    has_endpoint_signal = False
    if has_signal_evidence:
        has_endpoint_signal = (
            any(signal.kind == "endpoint" for signal in signals)
            if signals is not None
            else _chunk_has_signal_kind(store, chunk.chunk_id, "endpoint")
        )

    if has_signal_evidence and has_endpoint_signal:
        base_tier = 0
    elif score_parts.get("relation", 0.0) > 0:
        base_tier = 1
    elif has_signal_evidence:
        base_tier = 2
    elif score_parts.get("direct_text", 0.0) > 0:
        base_tier = 2
    else:
        base_tier = 3

    if _is_planner_hint_only(score_parts):
        return base_tier + 1
    return base_tier


def _has_planner_hint(score_parts: dict[str, float]) -> bool:
    return any(
        score_parts.get(key, 0.0) > 0
        for key in (
            "planner_semantic",
            "planner_lexical",
            "planner_path_symbol",
            "planner_signal",
            "planner_relation",
        )
    )


def _has_original_query_evidence(score_parts: dict[str, float]) -> bool:
    return any(
        score_parts.get(key, 0.0) > 0
        for key in (
            "semantic",
            "lexical",
            "path_symbol",
            "signal",
            "token_coverage",
            "original_relation",
            "direct_text",
        )
    )


def _is_planner_hint_only(score_parts: dict[str, float]) -> bool:
    return _has_planner_hint(score_parts) and not _has_original_query_evidence(
        score_parts
    )


def _chunk_has_signal_kind(store: sqlite_store.SQLiteStore, chunk_id: str, kind: str) -> bool:
    try:
        return any(signal.kind == kind for signal in store.signals_for_chunk(chunk_id))
    except sqlite3.Error:
        return False


def _token_coverage(tokens: list[str], chunk: DocumentChunk) -> float:
    if not tokens:
        return 0.0

    haystack = set(chunk.lexical_tokens)
    haystack.update(tokenizer.tokenize_query(chunk.content))
    matches = sum(1 for token in tokens if token.lower() in haystack)
    return matches / len(tokens)


def _plugin_boost(chunk: DocumentChunk) -> float:
    if chunk.metadata.get("language") == "java":
        return 0.03
    return 0.0


def _query_route(query: str) -> str:
    for part in re.split(r"\s+", query.strip()):
        cleaned = part.strip().strip("`'\".,;:()[]{}")
        if cleaned.startswith("/"):
            return _normalize_route(cleaned)
    return ""


def _normalize_route(value: str) -> str:
    cleaned = value.strip().strip("`'\".,;:()[]{}")
    if not cleaned:
        return ""
    cleaned = "/" + cleaned.strip("/")
    return re.sub(r"/+", "/", cleaned)


def _route_segments(route: str) -> list[str]:
    return [segment for segment in route.strip("/").split("/") if segment]


def _has_route_segment_suffix(endpoint_route: str, query_route: str) -> bool:
    endpoint_segments = _route_segments(endpoint_route)
    query_segments = _route_segments(query_route)
    if len(endpoint_segments) <= len(query_segments):
        return False
    return endpoint_segments[-len(query_segments) :] == query_segments


def _route_token_overlap(route: str, query_tokens: set[str]) -> int:
    route_tokens = {
        token.lower()
        for segment in _route_segments(route)
        for token in tokenizer.tokenize_query(segment)
        if token
    }
    return len(route_tokens.intersection(query_tokens))


def _chunk_local_tokens(chunk: DocumentChunk) -> set[str]:
    tokens = {token.lower() for token in chunk.lexical_tokens if token}
    tokens.update(_chunk_symbolic_tokens(chunk))
    return tokens


def _chunk_symbolic_tokens(chunk: DocumentChunk) -> set[str]:
    tokens: set[str] = set()
    for part in chunk.file_path.parts:
        tokens.update(token.lower() for token in tokenizer.tokenize_query(part) if token)
    for symbol in chunk.symbols:
        tokens.update(token.lower() for token in tokenizer.tokenize_query(symbol.name) if token)
    tokens.update(token.lower() for token in tokenizer.tokenize_query(chunk.content) if token)
    return tokens


def _chunk_declared_name_has_tokens(
    chunk: DocumentChunk,
    required_tokens: set[str],
) -> bool:
    name_tokens = {token.lower() for token in tokenizer.tokenize_query(chunk.file_path.stem) if token}
    if required_tokens.issubset(name_tokens):
        return True
    for symbol in chunk.symbols:
        name_tokens = {
            token.lower() for token in tokenizer.tokenize_query(symbol.name) if token
        }
        if required_tokens.issubset(name_tokens):
            return True
    return False


def _chunk_looks_route_relevant(
    chunk: DocumentChunk,
    query_tokens: list[str],
    query_route: str,
    route_boost: float = 0.0,
) -> bool:
    if route_boost:
        return True

    normalized_query_tokens = {token.lower() for token in query_tokens if token}
    if not normalized_query_tokens:
        return False
    min_overlap = min(2, len(normalized_query_tokens))

    route_values = [
        _normalize_route(token)
        for token in chunk.lexical_tokens
        if token.startswith("/")
    ]
    route_values.extend(_normalize_route(match.group(0)) for match in re.finditer(r"/[A-Za-z0-9_./:@-]+", chunk.content))
    for route in route_values:
        if not route:
            continue
        if (
            route == query_route
            or query_route.startswith(route + "/")
            or route.startswith(query_route + "/")
            or _has_route_segment_suffix(route, query_route)
        ):
            return True
        if _route_token_overlap(route, normalized_query_tokens) >= min_overlap:
            return True

    path = chunk.file_path.as_posix().lower()
    names = " ".join(symbol.name for symbol in chunk.symbols).lower()
    content = chunk.content.lower()
    routeish = (
        "controller" in path
        or "controller" in names
        or "requestmapping" in content
        or "getmapping" in content
        or "postmapping" in content
        or "putmapping" in content
        or "deletemapping" in content
        or "patchmapping" in content
    )
    return routeish and len(_chunk_local_tokens(chunk).intersection(normalized_query_tokens)) >= min_overlap


def _route_score_parts(
    signals: list[CodeSignal],
    query: str,
    query_route: str | None = None,
) -> dict[str, float]:
    if query_route is None:
        query_route = _query_route(query)
    if not query_route:
        return {}

    parts: dict[str, float] = {}
    has_endpoint_route = False
    has_exact_match = False
    has_prefix_match = False
    has_sibling_match = False
    for signal in signals:
        if signal.kind != "endpoint":
            continue
        path = signal.metadata.get("path")
        if not isinstance(path, str):
            continue
        has_endpoint_route = True
        endpoint_route = _normalize_route(path)
        if endpoint_route == query_route:
            has_exact_match = True
            continue
        if _has_route_segment_suffix(endpoint_route, query_route):
            has_sibling_match = True
            continue
        if query_route.startswith(endpoint_route + "/"):
            has_prefix_match = True
    if has_exact_match:
        parts["route_exact_match"] = _ROUTE_EXACT_MATCH_BOOST
    elif has_prefix_match:
        parts["route_prefix_match"] = _ROUTE_PREFIX_MATCH_BOOST
    elif has_sibling_match:
        parts["route_sibling_penalty"] = -_ROUTE_SIBLING_PENALTY
    elif has_endpoint_route:
        parts["route_mismatch_penalty"] = -_ROUTE_MISMATCH_PENALTY
    return parts


def _spring_path_score_parts(
    store: sqlite_store.SQLiteStore,
    candidate_chunks: dict[str, DocumentChunk],
    query_route: str,
) -> dict[str, dict[str, float]]:
    if not query_route or not candidate_chunks:
        return {}

    try:
        signals_by_chunk = store.signals_for_chunks(list(candidate_chunks))
    except sqlite3.Error:
        return {}

    parts_by_chunk: dict[str, dict[str, float]] = {}
    visited_signal_depths: dict[str, int] = {}
    frontier: list[tuple[str, int]] = []
    implementors_by_interface = _spring_path_candidate_implementors_by_interface(
        store,
        candidate_chunks,
        signals_by_chunk,
    )

    for chunk_id, signals in signals_by_chunk.items():
        for signal in signals:
            if signal.kind != "endpoint":
                continue
            path = signal.metadata.get("path")
            if not isinstance(path, str) or _normalize_route(path) != query_route:
                continue
            parts_by_chunk[chunk_id] = evidence_merge.merge_score_parts(
                parts_by_chunk.get(chunk_id, {}),
                {"spring_path_endpoint_match": _SPRING_PATH_ENDPOINT_BOOST},
            )
            existing_depth = visited_signal_depths.get(signal.signal_id)
            if existing_depth is not None and existing_depth <= 0:
                continue
            visited_signal_depths[signal.signal_id] = 0
            frontier.append((signal.signal_id, 0))

    while frontier:
        active_frontier = [
            (source_signal_id, depth)
            for source_signal_id, depth in frontier
            if depth < _SPRING_PATH_MAX_DEPTH
        ]
        if not active_frontier:
            break

        try:
            relations_by_source = store.relations_for_sources(
                [source_signal_id for source_signal_id, _ in active_frontier]
            )
        except sqlite3.Error:
            break

        relation_steps: list[tuple[str, int]] = []
        target_names: list[str] = []
        for source_signal_id, depth in active_frontier:
            next_depth = depth + 1
            for relation in relations_by_source.get(source_signal_id, []):
                if relation.confidence < relation_policy._MIN_RELATION_CONFIDENCE:
                    continue
                relation_steps.append((relation.target_name, next_depth))
                target_names.append(relation.target_name)

        if not relation_steps:
            break

        try:
            chunks_by_target = store.chunks_matching_signal_or_symbols(
                target_names,
                relation_policy.MAX_EXPANSION_CANDIDATES,
            )
        except sqlite3.Error:
            break

        next_signal_depths: dict[str, int] = {}
        for target_name, depth in relation_steps:
            for chunk in _spring_path_direct_chunks_for_target(
                chunks_by_target.get(target_name, []),
                target_name,
                candidate_chunks,
                signals_by_chunk,
            ):
                role = _chunk_role(chunk)
                _add_spring_path_reached_chunk(
                    chunk,
                    depth,
                    parts_by_chunk,
                )
                for signal_id in _spring_path_matching_signal_ids(
                    signals_by_chunk.get(chunk.chunk_id, []),
                    target_name,
                    allow_impl_owner=role.name == "service_impl",
                ):
                    _set_min_signal_depth(next_signal_depths, signal_id, depth)

            for chunk_id in _spring_path_implementor_chunk_ids(
                implementors_by_interface,
                target_name,
            ):
                chunk = candidate_chunks.get(chunk_id)
                if chunk is None:
                    continue
                _add_spring_path_reached_chunk(
                    chunk,
                    depth,
                    parts_by_chunk,
                )
                for signal_id in _spring_path_matching_signal_ids(
                    signals_by_chunk.get(chunk_id, []),
                    target_name,
                    allow_impl_owner=True,
                ):
                    _set_min_signal_depth(next_signal_depths, signal_id, depth)

        next_frontier: list[tuple[str, int]] = []
        for signal_id, depth in next_signal_depths.items():
            if depth >= _SPRING_PATH_MAX_DEPTH:
                continue
            existing_depth = visited_signal_depths.get(signal_id)
            if existing_depth is not None and existing_depth <= depth:
                continue
            visited_signal_depths[signal_id] = depth
            next_frontier.append((signal_id, depth))
        frontier = next_frontier

    return parts_by_chunk


def _spring_path_candidate_implementors_by_interface(
    store: sqlite_store.SQLiteStore,
    candidate_chunks: dict[str, DocumentChunk],
    signals_by_chunk: dict[str, list[CodeSignal]],
) -> list[_SpringPathImplementor]:
    signal_chunk_ids: dict[str, str] = {}
    source_signal_ids: list[str] = []
    for chunk_id, chunk in candidate_chunks.items():
        if _chunk_role(chunk).name != "service_impl":
            continue
        for signal in signals_by_chunk.get(chunk_id, []):
            signal_chunk_ids[signal.signal_id] = chunk_id
            source_signal_ids.append(signal.signal_id)

    if not source_signal_ids:
        return []

    try:
        relations_by_source = store.relations_for_sources(source_signal_ids)
    except sqlite3.Error:
        return []

    implementors: list[_SpringPathImplementor] = []
    seen: set[tuple[str, str]] = set()
    for source_signal_id, relations in relations_by_source.items():
        chunk_id = signal_chunk_ids.get(source_signal_id)
        if chunk_id is None:
            continue
        for relation in relations:
            if (
                relation.kind != "implements"
                or relation.confidence < relation_policy._MIN_RELATION_CONFIDENCE
            ):
                continue
            interface_name = relation.target_name.strip()
            if not interface_name:
                continue
            key = (interface_name, chunk_id)
            if key in seen:
                continue
            seen.add(key)
            implementors.append(
                _SpringPathImplementor(
                    interface_name=interface_name,
                    simple_name=_spring_path_simple_name(interface_name),
                    is_qualified=_spring_path_name_is_qualified(interface_name),
                    chunk_id=chunk_id,
                )
            )
    return implementors


def _spring_path_direct_chunks_for_target(
    reached_chunks: list[DocumentChunk],
    target_name: str,
    candidate_chunks: dict[str, DocumentChunk],
    signals_by_chunk: dict[str, list[CodeSignal]],
) -> list[DocumentChunk]:
    exact_chunks: list[DocumentChunk] = []
    fallback_chunks: list[DocumentChunk] = []
    for reached_chunk in reached_chunks:
        chunk = candidate_chunks.get(reached_chunk.chunk_id)
        if chunk is None:
            continue
        signals = signals_by_chunk.get(chunk.chunk_id, [])
        if _spring_path_chunk_has_exact_target_match(chunk, signals, target_name):
            exact_chunks.append(chunk)
            continue
        if _chunk_role(chunk).name != "service_impl":
            continue
        if _spring_path_matching_signal_ids(
            signals,
            target_name,
            allow_impl_owner=True,
        ):
            fallback_chunks.append(chunk)

    if exact_chunks:
        return _dedupe_chunks(exact_chunks)

    fallback_chunks = _dedupe_chunks(fallback_chunks)
    if len(fallback_chunks) == 1:
        return fallback_chunks
    return []


def _spring_path_chunk_has_exact_target_match(
    chunk: DocumentChunk,
    signals: list[CodeSignal],
    target_name: str,
) -> bool:
    if any(signal.name == target_name for signal in signals):
        return True
    return any(symbol.name == target_name for symbol in chunk.symbols)


def _dedupe_chunks(chunks: list[DocumentChunk]) -> list[DocumentChunk]:
    seen: set[str] = set()
    deduped: list[DocumentChunk] = []
    for chunk in chunks:
        if chunk.chunk_id in seen:
            continue
        seen.add(chunk.chunk_id)
        deduped.append(chunk)
    return deduped


def _add_spring_path_reached_chunk(
    chunk: DocumentChunk,
    depth: int,
    parts_by_chunk: dict[str, dict[str, float]],
) -> None:
    role_parts = _spring_path_role_score_parts(_chunk_role(chunk), depth)
    if role_parts:
        parts_by_chunk[chunk.chunk_id] = evidence_merge.merge_score_parts(
            parts_by_chunk.get(chunk.chunk_id, {}),
            role_parts,
        )


def _spring_path_implementor_chunk_ids(
    implementors: list[_SpringPathImplementor],
    target_name: str,
) -> list[str]:
    owner_name = _spring_path_target_owner_name(target_name)
    if not owner_name:
        return []

    owner_is_qualified = _spring_path_name_is_qualified(owner_name)
    if owner_is_qualified:
        exact_matches = [
            implementor.chunk_id
            for implementor in implementors
            if implementor.is_qualified and implementor.interface_name == owner_name
        ]
        if exact_matches:
            return ordering.dedupe_lowered(exact_matches)

    simple_name = _spring_path_simple_name(owner_name)
    simple_matches = [
        implementor.chunk_id
        for implementor in implementors
        if implementor.simple_name == simple_name
        and (not owner_is_qualified or not implementor.is_qualified)
    ]
    chunk_ids = ordering.dedupe_lowered(simple_matches)
    if len(chunk_ids) == 1:
        return chunk_ids
    return []


def _spring_path_matching_signal_ids(
    signals: list[CodeSignal],
    target_name: str,
    *,
    allow_impl_owner: bool,
) -> list[str]:
    target_member = _spring_path_member_target(target_name)
    matching_signal_ids: list[str] = []
    for signal in signals:
        if not signal.signal_id:
            continue
        if target_member is None:
            if signal.name == target_name:
                matching_signal_ids.append(signal.signal_id)
            continue

        signal_member = _spring_path_member_target(signal.name)
        if signal_member is None:
            continue
        target_owner, target_method = target_member
        signal_owner, signal_method = signal_member
        if signal_method != target_method:
            continue
        if _spring_path_owner_matches(
            signal_owner,
            target_owner,
            allow_impl_owner=allow_impl_owner,
        ):
            matching_signal_ids.append(signal.signal_id)
    return ordering.dedupe_lowered(matching_signal_ids)


def _spring_path_member_target(name: str) -> tuple[str, str] | None:
    stripped = name.strip()
    if "." not in stripped:
        return None
    owner_name, member_name = stripped.rsplit(".", 1)
    if not owner_name or not member_name or member_name[:1].isupper():
        return None
    return owner_name, member_name


def _spring_path_target_owner_name(target_name: str) -> str:
    member_target = _spring_path_member_target(target_name)
    if member_target is not None:
        return member_target[0]
    return target_name.strip()


def _spring_path_owner_matches(
    signal_owner: str,
    target_owner: str,
    *,
    allow_impl_owner: bool,
) -> bool:
    if signal_owner == target_owner:
        return True

    signal_simple = _spring_path_simple_name(signal_owner)
    target_simple = _spring_path_simple_name(target_owner)
    if signal_simple == target_simple:
        return True
    return allow_impl_owner and signal_simple == f"{target_simple}Impl"


def _spring_path_simple_name(name: str) -> str:
    return name.strip().rsplit(".", 1)[-1]


def _spring_path_name_is_qualified(name: str) -> bool:
    return "." in name.strip()


def _set_min_signal_depth(
    signal_depths: dict[str, int],
    signal_id: str,
    depth: int,
) -> None:
    existing_depth = signal_depths.get(signal_id)
    if existing_depth is None or depth < existing_depth:
        signal_depths[signal_id] = depth


def _spring_path_role_score_parts(
    role: _ChunkRole,
    depth: int,
) -> dict[str, float]:
    if depth == 1 and role.name == "service_impl":
        return {"spring_path_service_match": _SPRING_PATH_SERVICE_BOOST}
    if depth == 1 and role.name == "service_interface":
        return {
            "spring_path_service_interface_match": (
                _SPRING_PATH_SERVICE_INTERFACE_BOOST
            )
        }
    if depth in {1, 2} and role.name == "executor":
        return {"spring_path_executor_match": _SPRING_PATH_EXECUTOR_BOOST}
    return {}


def _route_tail_context_score_parts(
    chunk: DocumentChunk,
    query_route: str,
    role: _ChunkRole,
) -> dict[str, float]:
    if role.name != "executor":
        return {}
    segments = _route_segments(query_route)
    if not segments:
        return {}
    tail_tokens = {
        token.lower()
        for token in tokenizer.tokenize_query(segments[-1])
        if token and token.lower() not in _JAVA_CONTEXT_STRUCTURAL_TOKENS
    }
    if len(tail_tokens) < _JAVA_CONTEXT_MIN_TOKEN_OVERLAP:
        return {}
    if _chunk_declared_name_has_tokens(chunk, tail_tokens):
        return {"route_tail_context_match": _ROUTE_TAIL_CONTEXT_MATCH_BOOST}
    return {}


def _java_context_query_tokens(query_tokens: list[str], query_route: str) -> list[str]:
    if not query_route:
        return query_tokens

    route_tokens = {
        token.lower()
        for segment in _route_segments(query_route)
        for token in tokenizer.tokenize_query(segment)
        if token
    }
    if not route_tokens:
        return query_tokens

    non_route_tokens = [
        token for token in query_tokens if token and token.lower() not in route_tokens
    ]
    if len({token.lower() for token in non_route_tokens}) < _JAVA_CONTEXT_MIN_TOKEN_OVERLAP:
        return []
    return non_route_tokens


def _java_context_score_parts(
    signals: list[CodeSignal],
    query_tokens: list[str],
    role: _ChunkRole,
) -> dict[str, float]:
    normalized_query = {token.lower() for token in query_tokens if token}
    if not normalized_query:
        return {}

    parts: dict[str, float] = {}
    for signal in signals:
        if signal.kind not in {"method", "field"}:
            continue
        signal_tokens = {token.lower() for token in signal.tokens if token}
        overlap = normalized_query.intersection(signal_tokens)
        if len(overlap) >= _JAVA_CONTEXT_MIN_TOKEN_OVERLAP:
            if signal.kind == "method":
                parts["java_method_context_match"] = max(
                    parts.get("java_method_context_match", 0.0),
                    _JAVA_METHOD_CONTEXT_MATCH_BOOST,
                )
            if signal.kind == "field":
                parts["java_field_context_match"] = max(
                    parts.get("java_field_context_match", 0.0),
                    _JAVA_FIELD_CONTEXT_MATCH_BOOST,
                )
            if role.name == "executor":
                parts["java_executor_context_boost"] = max(
                    parts.get("java_executor_context_boost", 0.0),
                    _JAVA_EXECUTOR_CONTEXT_BOOST,
                )
    return parts


def _should_apply_java_context_score(
    chunk: DocumentChunk,
    query_tokens: list[str],
    role: _ChunkRole,
    penalty: float,
) -> bool:
    if not query_tokens or penalty:
        return False
    if chunk.metadata.get("language") != "java" and chunk.file_path.suffix.lower() != ".java":
        return False
    if _java_context_local_token_overlap(chunk, query_tokens) < _JAVA_CONTEXT_MIN_TOKEN_OVERLAP:
        return False
    if role.name in {"executor", "data_type"}:
        return True
    if role.name != "generic":
        return False
    return _java_chunk_suggests_helper_or_filter(chunk)


def _java_context_local_token_overlap(
    chunk: DocumentChunk,
    query_tokens: list[str],
) -> int:
    normalized_query = {
        token.lower()
        for token in query_tokens
        if token and token.lower() not in _JAVA_CONTEXT_STRUCTURAL_TOKENS
    }
    if not normalized_query:
        return 0
    return len(normalized_query.intersection(_chunk_local_tokens(chunk)))


def _java_chunk_suggests_helper_or_filter(chunk: DocumentChunk) -> bool:
    path = chunk.file_path.as_posix().lower()
    names = " ".join(symbol.name for symbol in chunk.symbols).lower()
    content = chunk.content.lower()
    haystack = f"{path} {names} {content}"
    return "helper" in haystack or "filter" in haystack


def _route_boost(chunk: DocumentChunk, query: str, tokens: list[str]) -> float:
    if "/" not in query or not tokens:
        return 0.0
    query_route = _query_route(query)
    query_tokens = set(tokens)
    for token in chunk.lexical_tokens:
        if not token.startswith("/"):
            continue
        if query_route:
            route = _normalize_route(token)
            if route == query_route or query_route.startswith(route + "/"):
                return 0.12
            continue
        if query_tokens.intersection(tokenizer.tokenize_query(token)):
            return 0.12
    return 0.0


def _generic_noise_score_parts(
    chunk: DocumentChunk,
    query: str,
    tokens: list[str],
) -> dict[str, float]:
    path = chunk.file_path.as_posix().lower()
    suffix = chunk.file_path.suffix.lower()
    name = chunk.file_path.name.lower()
    parts: dict[str, float] = {}

    legacy_penalty = _generated_or_test_penalty(chunk)
    if legacy_penalty:
        parts["penalty"] = -legacy_penalty
    if file_roles._is_test_path(path) or chunk.metadata.get("is_test"):
        parts = evidence_merge.merge_score_parts(
            parts,
            {"penalty": -0.10, "test_penalty": -0.10},
        )
    if chunk.metadata.get("is_generated") or file_roles._is_generated_schema_path(path, suffix):
        parts = evidence_merge.merge_score_parts(
            parts,
            {"penalty": -0.20, "generated_schema_penalty": -0.20},
        )
    if name in file_roles._INDEXED_LOCKFILE_NAMES:
        if file_roles._has_explicit_lockfile_query(tokens, name):
            parts["explicit_lockfile_query"] = 1.0
        else:
            parts = evidence_merge.merge_score_parts(
                parts,
                {"penalty": -0.20, "lockfile_penalty": -0.20},
            )

    role = file_roles._generic_file_role(chunk, query, tokens)
    role_parts: dict[str, float] = {}
    if role.penalty and role.penalty_key:
        role_parts["penalty"] = -role.penalty
        role_parts[role.penalty_key] = -role.penalty
    if role.source_boost:
        role_parts["file_role_source_boost"] = role.source_boost
    return evidence_merge.merge_score_parts(parts, role_parts)


def _generated_or_test_penalty(chunk: DocumentChunk) -> float:
    path = chunk.file_path.as_posix().lower()
    penalties: list[float] = []
    if chunk.metadata.get("is_generated") or "generated" in path:
        penalties.append(0.20)
    if chunk.metadata.get("is_test") or "/test/" in path or path.endswith("test.java"):
        penalties.append(0.10)
    return max(penalties, default=0.0)


def _reasons(score_parts: dict[str, float], query: str) -> list[str]:
    reasons: list[str] = []
    if score_parts.get("rerank_score"):
        evidence_class = _evidence_class(score_parts)
        reasons.append(f"rerank_score={score_parts['rerank_score']:.2f} ({evidence_class})")
    if score_parts.get("semantic", 0.0) > 0:
        reasons.append("semantic match")
    if score_parts.get("lexical", 0.0) > 0:
        reasons.append("lexical match")
    if score_parts.get("path_symbol", 0.0) > 0:
        reasons.append("path/symbol match")
    if score_parts.get("signal", 0.0) > 0:
        reasons.append("signal match")
    if score_parts.get("relation", 0.0) > 0:
        reasons.append("relation expansion")
    if score_parts.get("direct_text", 0.0) > 0:
        reasons.append("direct text match")
    if score_parts.get("anchored_relation", 0.0) > 0:
        reasons.append("evidence-anchored expansion")
    if score_parts.get("same_file_anchor", 0.0) > 0:
        reasons.append("same-file anchor")
    if score_parts.get("directory_anchor", 0.0) > 0:
        reasons.append("directory anchor")
    if score_parts.get("planner_semantic", 0.0) > 0:
        reasons.append("planner semantic match")
    if _has_planner_hint(score_parts):
        reasons.append("planner hint match")
    if score_parts.get("role_boost", 0.0) > 0:
        reasons.append("business role boost")
    if score_parts.get("role_penalty", 0.0) < 0:
        reasons.append("detail role penalty")
    if score_parts.get("file_hint_match_boost", 0.0) > 0:
        reasons.append("explicit file hint match")
    if score_parts.get("role_exact_match_boost", 0.0) > 0:
        reasons.append("role exact match boost")
    if score_parts.get("identifier_exact_match_boost", 0.0) > 0:
        reasons.append("explicit identifier match")
    if score_parts.get("path_role_hint_boost", 0.0) > 0:
        reasons.append("path role hint match")
    if score_parts.get("path_role_mismatch_penalty", 0.0) < 0:
        reasons.append("path role mismatch penalty")
    if score_parts.get("cohort_mismatch_penalty", 0.0) < 0:
        reasons.append("cross-project cohort mismatch penalty")
    if score_parts.get("impl_match_boost", 0.0) > 0:
        reasons.append("service implementation exact match boost")
    if score_parts.get("relation_role_boost", 0.0) > 0:
        reasons.append("relation chain role boost")
    if score_parts.get("relation_detail_penalty", 0.0) < 0:
        reasons.append("relation detail penalty")
    if score_parts.get("token_coverage", 0.0) > 0:
        reasons.append("token coverage")
    if score_parts.get("route_exact_match", 0.0) > 0:
        reasons.append("exact Spring route match")
    if score_parts.get("route_prefix_match", 0.0) > 0:
        reasons.append("Spring route prefix match")
    if score_parts.get("route_sibling_penalty", 0.0) < 0:
        reasons.append("sibling Spring route penalty")
    if score_parts.get("route_mismatch_penalty", 0.0) < 0:
        reasons.append("non-matching Spring route penalty")
    if score_parts.get("route_tail_context_match", 0.0) > 0:
        reasons.append("Spring route tail context match")
    if score_parts.get("java_method_context_match", 0.0) > 0:
        reasons.append("java method context match")
    if score_parts.get("java_field_context_match", 0.0) > 0:
        reasons.append("java field context match")
    if score_parts.get("java_executor_context_boost", 0.0) > 0:
        reasons.append("java executor context boost")
    if score_parts.get("spring_path_endpoint_match", 0.0) > 0:
        reasons.append("Spring endpoint path graph match")
    if score_parts.get("spring_path_service_match", 0.0) > 0:
        reasons.append("Spring service path graph match")
    if score_parts.get("spring_path_service_interface_match", 0.0) > 0:
        reasons.append("Spring service interface path graph match")
    if score_parts.get("spring_path_executor_match", 0.0) > 0:
        reasons.append("Spring executor path graph match")
    if score_parts.get("project_scope_boost", 0.0) > 0:
        reasons.append("project scope match")
    if score_parts.get("project_kind_boost", 0.0) > 0:
        reasons.append("project kind match")
    if score_parts.get("project_language_boost", 0.0) > 0:
        reasons.append("project language match")
    if score_parts.get("project_path_hint_boost", 0.0) > 0:
        reasons.append("project path hint match")
    if score_parts.get("project_file_hint_boost", 0.0) > 0:
        reasons.append("project file hint match")
    if score_parts.get("project_scope_mismatch_penalty", 0.0) < 0:
        reasons.append("project scope mismatch penalty")
    if "/" in query and score_parts.get("route_boost", 0.0) > 0:
        reasons.append("route token match")
    elif score_parts.get("plugin_boost", 0.0) > 0:
        reasons.append("java plugin boost")
    if score_parts.get("file_role_source_boost", 0.0) > 0:
        reasons.append("source file role boost")
    if score_parts.get("frontend_entrypoint_boost", 0.0) > 0:
        reasons.append("frontend entrypoint boost")
    if score_parts.get("frontend_support_boost", 0.0) > 0:
        reasons.append("frontend support boost")
    if score_parts.get("frontend_support_name_match_boost", 0.0) > 0:
        reasons.append("frontend support name match boost")
    if score_parts.get("frontend_import_support_boost", 0.0) > 0:
        reasons.append("frontend import support boost")
    if score_parts.get("frontend_lockfile_penalty", 0.0) < 0:
        reasons.append("frontend lockfile penalty")
    if score_parts.get("frontend_scratch_temp_penalty", 0.0) < 0:
        reasons.append("frontend scratch temp penalty")
    if score_parts.get("frontend_type_decl_penalty", 0.0) < 0:
        reasons.append("frontend type declaration penalty")
    if score_parts.get("query_operation_logic_boost", 0.0) > 0:
        reasons.append("query operation logic boost")
    if score_parts.get("config_logic_boost", 0.0) > 0:
        reasons.append("config logic boost")
    if score_parts.get("deployment_config_boost", 0.0) > 0:
        reasons.append("deployment config boost")
    if score_parts.get("config_artifact_penalty", 0.0) < 0:
        reasons.append("config artifact penalty")
    if score_parts.get("generated_output_penalty", 0.0) < 0:
        reasons.append("generated output penalty")
    if score_parts.get("doc_artifact_penalty", 0.0) < 0:
        reasons.append("doc artifact penalty")
    if score_parts.get("test_artifact_penalty", 0.0) < 0:
        reasons.append("test artifact penalty")
    if score_parts.get("generated_schema_penalty", 0.0) < 0:
        reasons.append("generated schema penalty")
    if score_parts.get("lockfile_penalty", 0.0) < 0:
        reasons.append("lockfile penalty")
    if score_parts.get("template_penalty", 0.0) < 0:
        reasons.append("template penalty")
    if score_parts.get("config_penalty", 0.0) < 0:
        reasons.append("config penalty")
    if score_parts.get("doc_penalty", 0.0) < 0:
        reasons.append("doc penalty")
    if score_parts.get("test_penalty", 0.0) < 0:
        reasons.append("test penalty")
    if score_parts.get("penalty", 0.0) < 0:
        reasons.append("generated/test penalty")
    return reasons


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
