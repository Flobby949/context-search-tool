from __future__ import annotations

import math

import pytest

from context_search_tool.retrieval_trace import (
    CANONICAL_TRACE_STAGES,
    RetrievalTrace,
    RetrievalTraceCollector,
    RetrievalTraceError,
    SOURCE_COUNT_KEYS,
    TraceAdjustment,
    TraceCandidate,
    TraceLimits,
    TraceQuery,
    TraceQueryVariant,
    TraceRank,
    TraceSelection,
    TraceStage,
    retrieval_trace_payload,
)


def _query() -> TraceQuery:
    return TraceQuery(
        original_token_count=2,
        expanded_token_count=3,
        variant_retrieval_status="hybrid",
        variants=(
            TraceQueryVariant("original", "audit status", "original"),
            TraceQueryVariant("planner:0", "approval state", "planner"),
        ),
        planner_status="ok",
        planner_provider="ollama",
        planner_model="qwen3.5:4b-mlx",
        planner_intent="implementation",
        planner_latency_ms=7,
        discarded_hint_count=0,
    )


def _candidate(rank: int = 1) -> TraceCandidate:
    return TraceCandidate(
        rank=rank,
        chunk_id=f"chunk-{rank}",
        file_path="src/AuditStatus.java",
        start_line=1,
        end_line=20,
        score=0.8,
        sources=("semantic", "direct_text"),
        variant_ids=("original",),
    )


def _source_counts(**values: int) -> tuple[tuple[str, int], ...]:
    return tuple((key, values.get(key, 0)) for key in SOURCE_COUNT_KEYS)


def _selection(rank: int = 1) -> TraceSelection:
    return TraceSelection(
        rank=rank,
        selection_kind="result",
        selection_reason="selected_within_result_limit",
        file_path="src/AuditStatus.java",
        start_line=1,
        end_line=20,
        score=1.1,
        origin_chunk_ids=(f"chunk-{rank}",),
        sources=("semantic", "direct_text"),
        variant_ids=("original",),
        rank_history=(
            TraceRank("ranking", rank, 1.0),
            TraceRank("cohort_rerank", rank, 1.1),
            TraceRank("context_expansion", rank, 1.1),
            TraceRank("final_selection", rank, 1.1),
        ),
        adjustments=(TraceAdjustment("role_boost", 0.2),),
        adjustment_omitted_count=0,
        reasons=("semantic match",),
    )


def test_trace_contract_uses_frozen_tuples_and_exact_limits() -> None:
    limits = TraceLimits()
    assert limits.max_stages == 16
    assert limits.stage_top_k == 5
    assert limits.final_selection_top_k == 20
    assert limits.adjustment_top_k == 24

    stage = TraceStage(
        name="final_selection",
        input_count=2,
        output_count=1,
        unique_output_count=1,
        duration_ms=3,
        source_counts=(("semantic", 1), ("planner_semantic", 0)),
        top_candidates=(_candidate(),),
    )
    selection = _selection()
    trace = RetrievalTrace(
        schema_version=1,
        outcome="complete",
        termination_reason="completed",
        duration_ms=10,
        limits=limits,
        query=_query(),
        source_counts=_source_counts(semantic=1),
        stages=(stage,),
        final_selection_count=1,
        final_selection_omitted_count=0,
        final_selections=(selection,),
    )

    assert trace.final_selections[0].origin_chunk_ids == ("chunk-1",)
    with pytest.raises(AttributeError):
        trace.outcome = "empty"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("factory", "message"),
    [
        (lambda: _candidate(rank=0), "rank must be positive"),
        (
            lambda: TraceCandidate(
                rank=1,
                chunk_id="chunk",
                file_path="/absolute/Secret.java",
                start_line=1,
                end_line=1,
                score=1.0,
                sources=("semantic",),
            ),
            "file_path must be repository-relative",
        ),
        (
            lambda: TraceAdjustment("bad", math.inf),
            "value must be finite",
        ),
        (
            lambda: TraceAdjustment("bad", math.nan),
            "value must be finite",
        ),
        (
            lambda: TraceLimits(stage_top_k=1),
            "schema-v1 limits are fixed",
        ),
        (
            lambda: TraceStage(
                name="semantic_recall",
                input_count=-1,
                output_count=0,
                unique_output_count=0,
                duration_ms=0,
            ),
            "input_count must be non-negative",
        ),
    ],
)
def test_trace_models_reject_invalid_public_values(factory, message: str) -> None:
    with pytest.raises(RetrievalTraceError, match=message):
        factory()


def test_trace_stage_rejects_preview_above_schema_v1_limit() -> None:
    with pytest.raises(
        RetrievalTraceError,
        match="candidate preview exceeds schema-v1 stage_top_k",
    ):
        TraceStage(
            name="semantic_recall",
            input_count=1,
            output_count=6,
            unique_output_count=6,
            duration_ms=0,
            top_candidates=tuple(_candidate(rank) for rank in range(1, 7)),
        )


class TickClock:
    def __init__(self, *values: int) -> None:
        self.values = iter(values)

    def __call__(self) -> int:
        return next(self.values)


def test_canonical_trace_stage_order_is_exact() -> None:
    assert CANONICAL_TRACE_STAGES == (
        "query_understanding",
        "semantic_recall",
        "lexical_recall",
        "path_symbol_recall",
        "direct_text_recall",
        "signal_recall",
        "planner_hint_recall",
        "direct_merge",
        "anchor_expansion",
        "relation_expansion",
        "candidate_merge",
        "ranking",
        "cohort_rerank",
        "context_expansion",
        "final_selection",
    )


def test_collector_enforces_stage_order_and_bounds_candidate_previews() -> None:
    clock = TickClock(
        0,
        0,
        1_000_000,
        2_000_000,
        6_000_000,
        10_000_000,
    )
    collector = RetrievalTraceCollector(clock_ns=clock)
    token = collector.start_stage("query_understanding", input_count=2)
    stopped = collector.stop_stage(token)
    collector.finish_stage(
        stopped,
        output_count=3,
        unique_output_count=3,
    )
    candidates = tuple(_candidate(rank=index) for index in range(1, 8))
    token = collector.start_stage("semantic_recall", input_count=1)
    stopped = collector.stop_stage(token)
    collector.finish_stage(
        stopped,
        output_count=7,
        unique_output_count=7,
        candidates=candidates,
        source_counts=(("semantic", 7), ("planner_semantic", 0)),
    )
    collector.record_query(_query())
    trace = collector.finish(
        outcome="empty",
        termination_reason="no_candidates",
        final_selections=(),
    )

    assert [stage.name for stage in trace.stages] == [
        "query_understanding",
        "semantic_recall",
    ]
    assert trace.stages[0].duration_ms == 1
    assert trace.stages[1].duration_ms == 4
    assert [item.rank for item in trace.stages[1].top_candidates] == [1, 2, 3, 4, 5]
    assert trace.duration_ms == 10


def test_collector_rejects_duplicate_or_out_of_order_stages() -> None:
    collector = RetrievalTraceCollector(clock_ns=TickClock(0, 1))
    with pytest.raises(RetrievalTraceError, match="out of canonical order"):
        collector.start_stage("semantic_recall", input_count=1)


def test_collector_requires_stopped_stage_to_finish_before_next_start() -> None:
    collector = RetrievalTraceCollector(
        clock_ns=TickClock(0, 0, 1_000_000)
    )
    token = collector.start_stage("query_understanding", input_count=1)
    collector.stop_stage(token)

    with pytest.raises(RetrievalTraceError, match="must be finished"):
        collector.start_stage("query_understanding", input_count=1)


def test_collector_bounds_final_selection_previews() -> None:
    collector = RetrievalTraceCollector(clock_ns=lambda: 0)
    collector.record_query(_query())
    for name in CANONICAL_TRACE_STAGES:
        token = collector.start_stage(name, input_count=0)
        stopped = collector.stop_stage(token)
        collector.finish_stage(
            stopped,
            output_count=0,
            unique_output_count=0,
        )
    selections = tuple(_selection(rank) for rank in range(1, 23))

    trace = collector.finish(
        outcome="complete",
        termination_reason="completed",
        final_selections=selections,
    )

    assert trace.final_selection_count == 22
    assert trace.final_selection_omitted_count == 2
    assert len(trace.final_selections) == 20


def test_completed_trace_requires_final_selection_stage() -> None:
    with pytest.raises(
        RetrievalTraceError,
        match="completed trace must end with final_selection",
    ):
        RetrievalTrace(
            schema_version=1,
            outcome="complete",
            termination_reason="completed",
            duration_ms=0,
            limits=TraceLimits(),
            query=_query(),
            source_counts=_source_counts(),
        )


def test_serializer_emits_exact_schema_and_no_source_content() -> None:
    collector = RetrievalTraceCollector(clock_ns=TickClock(0, 1_000_000))
    collector.record_query(_query())
    trace = collector.finish(
        outcome="empty",
        termination_reason="no_candidates",
        final_selections=(),
    )
    payload = retrieval_trace_payload(trace)

    assert tuple(payload) == (
        "schema_version",
        "outcome",
        "termination_reason",
        "duration_ms",
        "limits",
        "query",
        "source_counts",
        "stages",
        "final_selection_count",
        "final_selection_omitted_count",
        "final_selections",
    )
    assert tuple(payload["limits"]) == (
        "max_stages",
        "stage_top_k",
        "final_selection_top_k",
        "adjustment_top_k",
    )
    assert tuple(payload["query"]) == (
        "original_token_count",
        "expanded_token_count",
        "variant_retrieval_status",
        "variants",
        "planner",
    )
    assert tuple(payload["query"]["variants"][0]) == (
        "variant_id",
        "text",
        "source",
    )
    assert tuple(payload["query"]["planner"]) == (
        "status",
        "provider",
        "model",
        "intent",
        "latency_ms",
        "discarded_hint_count",
    )
    assert tuple(payload["source_counts"]) == SOURCE_COUNT_KEYS
    assert "content" not in repr(payload)


def test_serializer_emits_exact_stage_and_selection_shapes() -> None:
    trace = RetrievalTrace(
        schema_version=1,
        outcome="complete",
        termination_reason="completed",
        duration_ms=10,
        limits=TraceLimits(),
        query=_query(),
        source_counts=_source_counts(semantic=1),
        stages=(
            TraceStage(
                name="final_selection",
                input_count=1,
                output_count=1,
                unique_output_count=1,
                duration_ms=1,
                source_counts=(("semantic", 1),),
                decision_counts=(("selected_result", 1),),
                top_candidates=(_candidate(),),
            ),
        ),
        final_selection_count=1,
        final_selections=(_selection(),),
    )

    payload = retrieval_trace_payload(trace)
    assert tuple(payload["stages"][0]) == (
        "name",
        "input_count",
        "output_count",
        "unique_output_count",
        "duration_ms",
        "source_counts",
        "decision_counts",
        "top_candidates",
    )
    assert tuple(payload["stages"][0]["top_candidates"][0]) == (
        "rank",
        "chunk_id",
        "file_path",
        "start_line",
        "end_line",
        "score",
        "sources",
        "variant_ids",
    )
    assert tuple(payload["final_selections"][0]) == (
        "rank",
        "selection_kind",
        "selection_reason",
        "file_path",
        "start_line",
        "end_line",
        "score",
        "origin_chunk_ids",
        "sources",
        "variant_ids",
        "rank_history",
        "adjustments",
        "adjustment_omitted_count",
        "reasons",
    )
    assert tuple(payload["final_selections"][0]["rank_history"][0]) == (
        "stage",
        "rank",
        "score",
    )
    assert tuple(payload["final_selections"][0]["adjustments"][0]) == (
        "name",
        "value",
    )


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_trace_models_reject_all_non_finite_adjustments(value: float) -> None:
    with pytest.raises(RetrievalTraceError, match="value must be finite"):
        TraceAdjustment("bad", value)
