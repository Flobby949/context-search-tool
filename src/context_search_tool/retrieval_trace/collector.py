from __future__ import annotations

import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from context_search_tool.retrieval_trace.models import (
    RetrievalTrace,
    RetrievalTraceError,
    SOURCE_COUNT_KEYS,
    TraceCandidate,
    TraceLimits,
    TraceOutcome,
    TraceQuery,
    TraceSelection,
    TraceStage,
    TraceTerminationReason,
)


CANONICAL_TRACE_STAGES = (
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


@dataclass(frozen=True)
class StageToken:
    name: str
    input_count: int
    started_ns: int


@dataclass(frozen=True)
class StoppedStage:
    name: str
    input_count: int
    duration_ms: int


class RetrievalTraceCollector:
    def __init__(
        self,
        *,
        limits: TraceLimits | None = None,
        clock_ns: Callable[[], int] = time.perf_counter_ns,
    ) -> None:
        self.limits = limits or TraceLimits()
        self._clock_ns = clock_ns
        self._started_ns = clock_ns()
        self._query: TraceQuery | None = None
        self._stages: list[TraceStage] = []
        self._source_counts = dict.fromkeys(SOURCE_COUNT_KEYS, 0)
        self._rank_history: dict[str, list[tuple[str, int, float]]] = {}
        self._active_stage: StageToken | None = None
        self._stopped_stage: StoppedStage | None = None

    @property
    def rank_history(self) -> dict[str, tuple[tuple[str, int, float], ...]]:
        return {
            chunk_id: tuple(history)
            for chunk_id, history in self._rank_history.items()
        }

    def record_query(self, query: TraceQuery) -> None:
        self._query = query

    def start_stage(self, name: str, *, input_count: int) -> StageToken:
        if self._active_stage is not None:
            raise RetrievalTraceError("previous trace stage is still active")
        if self._stopped_stage is not None:
            raise RetrievalTraceError("stopped trace stage must be finished")
        if len(self._stages) >= len(CANONICAL_TRACE_STAGES):
            raise RetrievalTraceError("trace stage count exceeds canonical stages")
        expected = CANONICAL_TRACE_STAGES[len(self._stages)]
        if name != expected:
            raise RetrievalTraceError(
                f"trace stage {name!r} is out of canonical order; "
                f"expected {expected!r}"
            )
        token = StageToken(name, input_count, self._clock_ns())
        self._active_stage = token
        return token

    def stop_stage(self, token: StageToken) -> StoppedStage:
        if token is not self._active_stage:
            raise RetrievalTraceError("trace stage token is not active")
        self._active_stage = None
        stopped = StoppedStage(
            name=token.name,
            input_count=token.input_count,
            duration_ms=max(
                0,
                (self._clock_ns() - token.started_ns) // 1_000_000,
            ),
        )
        self._stopped_stage = stopped
        return stopped

    def finish_stage(
        self,
        stage: StoppedStage,
        *,
        output_count: int,
        unique_output_count: int,
        candidates: tuple[TraceCandidate, ...] = (),
        source_counts: tuple[tuple[str, int], ...] = (),
        decision_counts: tuple[tuple[str, int], ...] = (),
        rank_positions: Iterable[tuple[str, int, float]] = (),
    ) -> None:
        if stage is not self._stopped_stage:
            raise RetrievalTraceError("trace stage was not stopped by collector")
        for key, _count in source_counts:
            if key not in self._source_counts:
                raise RetrievalTraceError(
                    f"unknown trace source count key: {key}"
                )
        completed_stage = TraceStage(
            name=stage.name,
            input_count=stage.input_count,
            output_count=output_count,
            unique_output_count=unique_output_count,
            duration_ms=stage.duration_ms,
            source_counts=source_counts,
            decision_counts=decision_counts,
            top_candidates=candidates[: self.limits.stage_top_k],
        )
        for key, count in source_counts:
            self._source_counts[key] += count
        for chunk_id, rank, score in rank_positions:
            self._rank_history.setdefault(chunk_id, []).append(
                (stage.name, rank, score)
            )
        self._stages.append(completed_stage)
        self._stopped_stage = None

    def finish(
        self,
        *,
        outcome: TraceOutcome,
        termination_reason: TraceTerminationReason,
        final_selections: tuple[TraceSelection, ...],
    ) -> RetrievalTrace:
        if self._query is None:
            raise RetrievalTraceError("trace query metadata was not recorded")
        if self._active_stage is not None:
            raise RetrievalTraceError("cannot finish trace with an active stage")
        if self._stopped_stage is not None:
            raise RetrievalTraceError("cannot finish trace with an unfinished stage")
        preview = final_selections[: self.limits.final_selection_top_k]
        omitted = len(final_selections) - len(preview)
        return RetrievalTrace(
            schema_version=1,
            outcome=outcome,
            termination_reason=termination_reason,
            duration_ms=max(
                0,
                (self._clock_ns() - self._started_ns) // 1_000_000,
            ),
            limits=self.limits,
            query=self._query,
            source_counts=tuple(self._source_counts.items()),
            stages=tuple(self._stages),
            final_selection_count=len(final_selections),
            final_selection_omitted_count=omitted,
            final_selections=preview,
        )

    def set_finished_trace(self, trace: RetrievalTrace) -> None:
        if hasattr(self, "_finished_trace"):
            raise RetrievalTraceError("trace collector was already finalized")
        self._finished_trace = trace

    def finished_trace(self) -> RetrievalTrace:
        try:
            return self._finished_trace
        except AttributeError as exc:
            raise RetrievalTraceError("trace collector was not finalized") from exc


__all__ = [
    "CANONICAL_TRACE_STAGES",
    "RetrievalTraceCollector",
    "StageToken",
    "StoppedStage",
]
