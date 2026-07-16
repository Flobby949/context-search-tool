from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import TYPE_CHECKING

import context_search_tool.retrieval_trace as retrieval_trace
from context_search_tool import manifest, query_planner, sqlite_store, tokenizer
from context_search_tool.config import ToolConfig
from context_search_tool.models import (
    EvidenceAnchor,
    QueryPlan,
    QueryVariant,
    RetrievalResult,
    RetrievalSummary,
)
from context_search_tool.paths import index_dir_for
from context_search_tool.repo_profile import build_repo_profile
from context_search_tool.retrieval_core import (
    candidates,
    context_expansion,
    expansion,
    ordering,
    ranking,
    relation_policy,
    selection,
    tracing,
)
from context_search_tool.retrieval_trace import RetrievalTrace

if TYPE_CHECKING:
    from context_search_tool.query_planner import QueryPlanner
    from context_search_tool.retrieval_trace import RetrievalTraceCollector


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
    collector = retrieval_trace.RetrievalTraceCollector(**collector_kwargs)
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
        tracing.finish_trace(
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

    manifest.assert_manifest_compatible(repo, config)

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
        tracing.finish_trace(
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

    query_stage = tracing.start_stage(
        trace_collector,
        "query_understanding",
        input_count=len(original_tokens),
    )
    planner_instance = planner or query_planner.planner_from_config(
        config.query_planner
    )
    repo_profile = build_repo_profile(store)
    plan = planner_instance.plan(query, repo_profile=repo_profile)
    query_variants, discarded_variants = query_planner.build_query_variants(
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
    tokens = query_planner.expand_query_plan_tokens(query, plan)
    hint_tokens = (
        query_planner.planner_hint_tokens(original_tokens, tokens)
        if plan.status == "ok"
        else []
    )
    stopped = tracing.stop_stage(trace_collector, query_stage)
    tracing.finish_count_stage(
        trace_collector,
        stopped,
        output_count=len(tokens),
        unique_output_count=len(set(tokens)),
    )
    token = tracing.start_stage(
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
    stopped = tracing.stop_stage(trace_collector, token)
    tracing.finish_candidate_stage(
        trace_collector,
        stopped,
        store=store,
        candidates=semantic_candidates,
        source_keys=("semantic", "planner_semantic"),
    )

    token = tracing.start_stage(
        trace_collector,
        "lexical_recall",
        input_count=len(original_tokens),
    )
    lexical_candidates = candidates.lexical_candidates(
        store,
        original_tokens,
        config.retrieval.lexical_top_k,
    )
    stopped = tracing.stop_stage(trace_collector, token)
    tracing.finish_candidate_stage(
        trace_collector,
        stopped,
        store=store,
        candidates=lexical_candidates,
        source_keys=("lexical",),
    )

    token = tracing.start_stage(
        trace_collector,
        "path_symbol_recall",
        input_count=len(original_tokens),
    )
    path_symbol_candidates = candidates.path_symbol_candidates(
        store,
        original_tokens,
        config.retrieval.lexical_top_k,
    )
    stopped = tracing.stop_stage(trace_collector, token)
    tracing.finish_candidate_stage(
        trace_collector,
        stopped,
        store=store,
        candidates=path_symbol_candidates,
        source_keys=("path_symbol",),
    )

    probes = candidates.direct_text_probes(query, original_tokens)
    token = tracing.start_stage(
        trace_collector,
        "direct_text_recall",
        input_count=len(probes),
    )
    direct_text_candidates = candidates.direct_text_candidates(
        store,
        probes,
        config,
    )
    stopped = tracing.stop_stage(trace_collector, token)
    tracing.finish_candidate_stage(
        trace_collector,
        stopped,
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

    token = tracing.start_stage(
        trace_collector,
        "signal_recall",
        input_count=len(original_tokens),
    )
    signal_candidates = candidates.signal_candidates(store, original_tokens, config)
    stopped = tracing.stop_stage(trace_collector, token)
    tracing.finish_candidate_stage(
        trace_collector,
        stopped,
        store=store,
        candidates=signal_candidates,
        source_keys=("signal",),
    )

    token = tracing.start_stage(
        trace_collector,
        "planner_hint_recall",
        input_count=len(hint_tokens),
    )
    planner_candidates = candidates.planner_hint_candidates(store, hint_tokens, config)
    stopped = tracing.stop_stage(trace_collector, token)
    tracing.finish_candidate_stage(
        trace_collector,
        stopped,
        store=store,
        candidates=planner_candidates,
        source_keys=(
            "planner_lexical",
            "planner_path_symbol",
            "planner_signal",
        ),
    )

    raw_direct = [*initial_candidates, *signal_candidates, *planner_candidates]
    token = tracing.start_stage(
        trace_collector,
        "direct_merge",
        input_count=len(raw_direct),
    )
    direct_candidates = candidates.merge_candidates(raw_direct)
    stopped = tracing.stop_stage(trace_collector, token)
    tracing.finish_candidate_stage(
        trace_collector,
        stopped,
        store=store,
        candidates=list(direct_candidates.values()),
    )

    token = tracing.start_stage(
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
    stopped = tracing.stop_stage(trace_collector, token)
    tracing.finish_candidate_stage(
        trace_collector,
        stopped,
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
    token = tracing.start_stage(
        trace_collector,
        "relation_expansion",
        input_count=len(relation_seed_candidates),
    )
    relation_candidates = expansion.relation_candidates(
        store,
        list(relation_seed_candidates.values()),
        config,
    )
    stopped = tracing.stop_stage(trace_collector, token)
    tracing.finish_candidate_stage(
        trace_collector,
        stopped,
        store=store,
        candidates=relation_candidates,
        source_keys=("relation",),
    )

    all_candidates = [
        *direct_candidates.values(),
        *anchor_candidates,
        *relation_candidates,
    ]
    token = tracing.start_stage(
        trace_collector,
        "candidate_merge",
        input_count=len(all_candidates),
    )
    merged_candidates = candidates.merge_candidates(all_candidates)
    stopped = tracing.stop_stage(trace_collector, token)
    tracing.finish_candidate_stage(
        trace_collector,
        stopped,
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
        tracing.finish_trace(
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

    token = tracing.start_stage(
        trace_collector,
        "ranking",
        input_count=len(merged_candidates),
    )
    ranked_chunks = ranking.rank_chunks(
        store, merged_candidates, original_tokens, query
    )
    stopped = tracing.stop_stage(trace_collector, token)
    tracing.finish_ranked_stage(
        trace_collector,
        stopped,
        ranked=ranked_chunks,
        candidates=merged_candidates,
    )

    token = tracing.start_stage(
        trace_collector,
        "cohort_rerank",
        input_count=len(ranked_chunks),
    )
    ranked_chunks = ranking.apply_frontend_import_cohort_rerank(
        repo, ranked_chunks, query
    )
    stopped = tracing.stop_stage(trace_collector, token)
    tracing.finish_ranked_stage(
        trace_collector,
        stopped,
        ranked=ranked_chunks,
        candidates=merged_candidates,
    )

    token = tracing.start_stage(
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
    stopped = tracing.stop_stage(trace_collector, token)
    tracing.finish_expanded_stage(
        trace_collector,
        stopped,
        expanded=expanded,
        candidates=merged_candidates,
    )

    token = tracing.start_stage(
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
    stopped = tracing.stop_stage(trace_collector, token)
    final_selections = tracing.finish_selection_stage(
        trace_collector,
        stopped,
        decisions=trace_decisions,
        candidates=merged_candidates,
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
    tracing.finish_trace(
        trace_collector,
        original_tokens=original_tokens,
        expanded_tokens=tokens,
        variants=query_variants,
        variant_retrieval_status=variant_retrieval_status,
        plan=plan,
        outcome="complete",
        termination_reason="completed",
        selections=final_selections,
    )
    return bundle


def evidence_anchor_top_k(max_results: int) -> int:
    if max_results <= 0:
        return 0
    return max(1, min(5, max_results // 3))


def normalize_score(scores: list[float]) -> list[float]:
    return ranking.normalize_score(scores)
