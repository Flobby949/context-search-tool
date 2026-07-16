from __future__ import annotations

from typing import Any

from context_search_tool.retrieval_trace.models import (
    RetrievalTrace,
    TraceAdjustment,
    TraceCandidate,
    TraceQuery,
    TraceQueryVariant,
    TraceRank,
    TraceSelection,
    TraceStage,
)


def retrieval_trace_payload(trace: RetrievalTrace) -> dict[str, Any]:
    return {
        "schema_version": trace.schema_version,
        "outcome": trace.outcome,
        "termination_reason": trace.termination_reason,
        "duration_ms": trace.duration_ms,
        "limits": {
            "max_stages": trace.limits.max_stages,
            "stage_top_k": trace.limits.stage_top_k,
            "final_selection_top_k": trace.limits.final_selection_top_k,
            "adjustment_top_k": trace.limits.adjustment_top_k,
        },
        "query": _query_payload(trace.query),
        "source_counts": dict(trace.source_counts),
        "stages": [_stage_payload(stage) for stage in trace.stages],
        "final_selection_count": trace.final_selection_count,
        "final_selection_omitted_count": trace.final_selection_omitted_count,
        "final_selections": [
            _selection_payload(selection) for selection in trace.final_selections
        ],
    }


def _query_payload(query: TraceQuery) -> dict[str, Any]:
    return {
        "original_token_count": query.original_token_count,
        "expanded_token_count": query.expanded_token_count,
        "variant_retrieval_status": query.variant_retrieval_status,
        "variants": [_variant_payload(variant) for variant in query.variants],
        "planner": {
            "status": query.planner_status,
            "provider": query.planner_provider,
            "model": query.planner_model,
            "intent": query.planner_intent,
            "latency_ms": query.planner_latency_ms,
            "discarded_hint_count": query.discarded_hint_count,
        },
    }


def _variant_payload(variant: TraceQueryVariant) -> dict[str, Any]:
    return {
        "variant_id": variant.variant_id,
        "text": variant.text,
        "source": variant.source,
    }


def _stage_payload(stage: TraceStage) -> dict[str, Any]:
    return {
        "name": stage.name,
        "input_count": stage.input_count,
        "output_count": stage.output_count,
        "unique_output_count": stage.unique_output_count,
        "duration_ms": stage.duration_ms,
        "source_counts": dict(stage.source_counts),
        "decision_counts": dict(stage.decision_counts),
        "top_candidates": [
            _candidate_payload(candidate) for candidate in stage.top_candidates
        ],
    }


def _candidate_payload(candidate: TraceCandidate) -> dict[str, Any]:
    return {
        "rank": candidate.rank,
        "chunk_id": candidate.chunk_id,
        "file_path": candidate.file_path,
        "start_line": candidate.start_line,
        "end_line": candidate.end_line,
        "score": float(candidate.score),
        "sources": list(candidate.sources),
        "variant_ids": list(candidate.variant_ids),
    }


def _selection_payload(selection: TraceSelection) -> dict[str, Any]:
    return {
        "rank": selection.rank,
        "selection_kind": selection.selection_kind,
        "selection_reason": selection.selection_reason,
        "file_path": selection.file_path,
        "start_line": selection.start_line,
        "end_line": selection.end_line,
        "score": float(selection.score),
        "origin_chunk_ids": list(selection.origin_chunk_ids),
        "sources": list(selection.sources),
        "variant_ids": list(selection.variant_ids),
        "rank_history": [_rank_payload(rank) for rank in selection.rank_history],
        "adjustments": [
            _adjustment_payload(adjustment)
            for adjustment in selection.adjustments
        ],
        "adjustment_omitted_count": selection.adjustment_omitted_count,
        "reasons": list(selection.reasons),
    }


def _rank_payload(rank: TraceRank) -> dict[str, Any]:
    return {
        "stage": rank.stage,
        "rank": rank.rank,
        "score": float(rank.score),
    }


def _adjustment_payload(adjustment: TraceAdjustment) -> dict[str, Any]:
    return {
        "name": adjustment.name,
        "value": float(adjustment.value),
    }


__all__ = ["retrieval_trace_payload"]
