from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Literal


TraceOutcome = Literal["complete", "empty", "partial"]
TraceTerminationReason = Literal[
    "completed",
    "missing_index",
    "store_read_error",
    "no_candidates",
]
TraceSelectionKind = Literal["result", "evidence_anchor"]
TraceSelectionReason = Literal[
    "selected_within_result_limit",
    "selected_within_anchor_limit",
]

SOURCE_COUNT_KEYS = (
    "semantic",
    "planner_semantic",
    "lexical",
    "path_symbol",
    "direct_text",
    "signal",
    "planner_lexical",
    "planner_path_symbol",
    "planner_signal",
    "anchor_expansion",
    "relation",
)


class RetrievalTraceError(RuntimeError):
    """Raised when trace-only state violates the schema-v1 contract."""


def _non_negative_int(name: str, value: int) -> None:
    if type(value) is not int or value < 0:
        raise RetrievalTraceError(f"{name} must be non-negative")


def _positive_int(name: str, value: int) -> None:
    if type(value) is not int or value < 1:
        raise RetrievalTraceError(f"{name} must be positive")


def _finite(name: str, value: float) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RetrievalTraceError(f"{name} must be finite")
    if not math.isfinite(float(value)):
        raise RetrievalTraceError(f"{name} must be finite")


def _relative_path(value: str) -> None:
    path = PurePosixPath(value)
    if not value or "\\" in value or path.is_absolute() or ".." in path.parts:
        raise RetrievalTraceError("file_path must be repository-relative")


@dataclass(frozen=True)
class TraceLimits:
    max_stages: int = 16
    stage_top_k: int = 5
    final_selection_top_k: int = 20
    adjustment_top_k: int = 24

    def __post_init__(self) -> None:
        _positive_int("max_stages", self.max_stages)
        _positive_int("stage_top_k", self.stage_top_k)
        _positive_int("final_selection_top_k", self.final_selection_top_k)
        _positive_int("adjustment_top_k", self.adjustment_top_k)
        if (
            self.max_stages,
            self.stage_top_k,
            self.final_selection_top_k,
            self.adjustment_top_k,
        ) != (16, 5, 20, 24):
            raise RetrievalTraceError("schema-v1 limits are fixed")


@dataclass(frozen=True)
class TraceQueryVariant:
    variant_id: str
    text: str
    source: str

    def __post_init__(self) -> None:
        if not self.variant_id:
            raise RetrievalTraceError("variant_id must not be empty")
        if self.source not in {"original", "planner"}:
            raise RetrievalTraceError("variant source must be original or planner")


@dataclass(frozen=True)
class TraceQuery:
    original_token_count: int
    expanded_token_count: int
    variant_retrieval_status: str
    variants: tuple[TraceQueryVariant, ...] = ()
    planner_status: str = "disabled"
    planner_provider: str = ""
    planner_model: str = ""
    planner_intent: str = "unknown"
    planner_latency_ms: int | None = None
    discarded_hint_count: int = 0

    def __post_init__(self) -> None:
        _non_negative_int("original_token_count", self.original_token_count)
        _non_negative_int("expanded_token_count", self.expanded_token_count)
        _non_negative_int("discarded_hint_count", self.discarded_hint_count)
        if self.planner_latency_ms is not None:
            _non_negative_int("planner_latency_ms", self.planner_latency_ms)
        if self.variant_retrieval_status not in {
            "original_only",
            "hybrid",
            "embedding_fallback",
        }:
            raise RetrievalTraceError("invalid variant_retrieval_status")


@dataclass(frozen=True)
class TraceCandidate:
    rank: int
    chunk_id: str
    file_path: str
    start_line: int
    end_line: int
    score: float
    sources: tuple[str, ...]
    variant_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _positive_int("rank", self.rank)
        _positive_int("start_line", self.start_line)
        _positive_int("end_line", self.end_line)
        if self.end_line < self.start_line:
            raise RetrievalTraceError("end_line must not precede start_line")
        if not self.chunk_id:
            raise RetrievalTraceError("chunk_id must not be empty")
        _relative_path(self.file_path)
        _finite("score", self.score)
        if not self.sources or any(not source for source in self.sources):
            raise RetrievalTraceError("sources must not be empty")
        if any(not variant_id for variant_id in self.variant_ids):
            raise RetrievalTraceError("variant_ids must not contain empty values")


@dataclass(frozen=True)
class TraceStage:
    name: str
    input_count: int
    output_count: int
    unique_output_count: int
    duration_ms: int
    source_counts: tuple[tuple[str, int], ...] = ()
    decision_counts: tuple[tuple[str, int], ...] = ()
    top_candidates: tuple[TraceCandidate, ...] = ()

    def __post_init__(self) -> None:
        if not self.name:
            raise RetrievalTraceError("stage name must not be empty")
        for field_name in (
            "input_count",
            "output_count",
            "unique_output_count",
            "duration_ms",
        ):
            _non_negative_int(field_name, getattr(self, field_name))
        if self.unique_output_count > self.output_count:
            raise RetrievalTraceError(
                "unique_output_count must not exceed output_count"
            )
        for key, value in (*self.source_counts, *self.decision_counts):
            if not key:
                raise RetrievalTraceError("count key must not be empty")
            _non_negative_int(key, value)
        for counts in (self.source_counts, self.decision_counts):
            count_keys = [key for key, _ in counts]
            if len(count_keys) != len(set(count_keys)):
                raise RetrievalTraceError("count keys must be unique")
        expected_ranks = tuple(range(1, len(self.top_candidates) + 1))
        if tuple(item.rank for item in self.top_candidates) != expected_ranks:
            raise RetrievalTraceError("candidate preview ranks must be contiguous")
        if len(self.top_candidates) > self.output_count:
            raise RetrievalTraceError(
                "candidate preview must not exceed output_count"
            )
        if len(self.top_candidates) > 5:
            raise RetrievalTraceError(
                "candidate preview exceeds schema-v1 stage_top_k"
            )


@dataclass(frozen=True)
class TraceAdjustment:
    name: str
    value: float

    def __post_init__(self) -> None:
        if not self.name:
            raise RetrievalTraceError("adjustment name must not be empty")
        _finite("value", self.value)
        if float(self.value) == 0.0:
            raise RetrievalTraceError("adjustment value must be non-zero")


@dataclass(frozen=True)
class TraceRank:
    stage: str
    rank: int
    score: float

    def __post_init__(self) -> None:
        if not self.stage:
            raise RetrievalTraceError("rank stage must not be empty")
        _positive_int("rank", self.rank)
        _finite("score", self.score)


@dataclass(frozen=True)
class TraceSelection:
    rank: int
    selection_kind: TraceSelectionKind
    selection_reason: TraceSelectionReason
    file_path: str
    start_line: int
    end_line: int
    score: float
    origin_chunk_ids: tuple[str, ...]
    sources: tuple[str, ...]
    variant_ids: tuple[str, ...]
    rank_history: tuple[TraceRank, ...]
    adjustments: tuple[TraceAdjustment, ...]
    adjustment_omitted_count: int
    reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        _positive_int("rank", self.rank)
        _positive_int("start_line", self.start_line)
        _positive_int("end_line", self.end_line)
        _non_negative_int(
            "adjustment_omitted_count",
            self.adjustment_omitted_count,
        )
        if self.end_line < self.start_line:
            raise RetrievalTraceError("end_line must not precede start_line")
        if self.selection_kind not in {"result", "evidence_anchor"}:
            raise RetrievalTraceError("invalid selection_kind")
        if self.selection_reason not in {
            "selected_within_result_limit",
            "selected_within_anchor_limit",
        }:
            raise RetrievalTraceError("invalid selection_reason")
        _relative_path(self.file_path)
        _finite("score", self.score)
        if not self.origin_chunk_ids or any(
            not chunk_id for chunk_id in self.origin_chunk_ids
        ):
            raise RetrievalTraceError("origin_chunk_ids must not be empty")
        if not self.sources or any(not source for source in self.sources):
            raise RetrievalTraceError("sources must not be empty")
        if not self.rank_history:
            raise RetrievalTraceError("rank_history must not be empty")
        if tuple(item.stage for item in self.rank_history) != (
            "ranking",
            "cohort_rerank",
            "context_expansion",
            "final_selection",
        ):
            raise RetrievalTraceError(
                "rank_history stages must match canonical order"
            )


@dataclass(frozen=True)
class RetrievalTrace:
    schema_version: int
    outcome: TraceOutcome
    termination_reason: TraceTerminationReason
    duration_ms: int
    limits: TraceLimits
    query: TraceQuery
    source_counts: tuple[tuple[str, int], ...]
    stages: tuple[TraceStage, ...] = ()
    final_selection_count: int = 0
    final_selection_omitted_count: int = 0
    final_selections: tuple[TraceSelection, ...] = ()

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise RetrievalTraceError("schema_version must be 1")
        valid_outcomes = {
            ("complete", "completed"),
            ("empty", "missing_index"),
            ("empty", "no_candidates"),
            ("partial", "store_read_error"),
        }
        if (self.outcome, self.termination_reason) not in valid_outcomes:
            raise RetrievalTraceError("invalid outcome and termination_reason")
        if self.outcome == "complete" and (
            not self.stages or self.stages[-1].name != "final_selection"
        ):
            raise RetrievalTraceError(
                "completed trace must end with final_selection"
            )
        _non_negative_int("duration_ms", self.duration_ms)
        _non_negative_int("final_selection_count", self.final_selection_count)
        _non_negative_int(
            "final_selection_omitted_count",
            self.final_selection_omitted_count,
        )
        if len(self.stages) > self.limits.max_stages:
            raise RetrievalTraceError("stage count exceeds max_stages")
        if len(self.final_selections) > self.limits.final_selection_top_k:
            raise RetrievalTraceError("final selection preview exceeds limit")
        if tuple(item.rank for item in self.final_selections) != tuple(
            range(1, len(self.final_selections) + 1)
        ):
            raise RetrievalTraceError(
                "final selection preview ranks must be contiguous"
            )
        if any(
            len(item.adjustments) > self.limits.adjustment_top_k
            for item in self.final_selections
        ):
            raise RetrievalTraceError("selection adjustment preview exceeds limit")
        if (
            self.final_selection_count
            != len(self.final_selections) + self.final_selection_omitted_count
        ):
            raise RetrievalTraceError("final selection counts are inconsistent")
        source_keys = tuple(key for key, _ in self.source_counts)
        if source_keys != SOURCE_COUNT_KEYS:
            raise RetrievalTraceError("source keys must match canonical order")
        for key, value in self.source_counts:
            if not key:
                raise RetrievalTraceError("source key must not be empty")
            _non_negative_int(key, value)


__all__ = [
    "RetrievalTrace",
    "RetrievalTraceError",
    "SOURCE_COUNT_KEYS",
    "TraceAdjustment",
    "TraceCandidate",
    "TraceLimits",
    "TraceOutcome",
    "TraceQuery",
    "TraceQueryVariant",
    "TraceRank",
    "TraceSelection",
    "TraceSelectionKind",
    "TraceSelectionReason",
    "TraceStage",
    "TraceTerminationReason",
]
