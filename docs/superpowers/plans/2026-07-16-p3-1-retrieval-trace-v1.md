# P3.1 RetrievalTrace v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (\`- [ ]\`) syntax for tracking.

**Goal:** Add a versioned, bounded RetrievalTrace exposed through independent CLI and MCP operations while preserving ordinary query and ContextPack output exactly.

**Architecture:** Keep retrieval.py as the P3.1 execution owner, add an optional request-local collector, and convert existing intermediate values into immutable trace models after each operation. A new retrieval_trace package owns limits, stage ordering, collection, and exact serialization; P3.2 will move stage implementations behind this protected contract.

**Tech Stack:** Python 3.11, frozen dataclasses, Typer, FastMCP, SQLite-backed retrieval, pytest, offline hash-v1 embeddings.

---

## Source Of Truth And Execution Constraints

The approved source of truth is:

- docs/superpowers/specs/2026-07-16-p3-1-retrieval-trace-v1-design.md

Execution assumptions:

1. Start from a clean worktree based on be03fa73437cd897d112377d80dda5c83370def5 or a descendant containing only reviewed prerequisite changes.
2. P2 is independently complete: the implementation must keep p2_context_pack at 5/5 and raw ci at 8/8.
3. Phase 1 remains 6/7 at the design baseline. Do not change its case, threshold, expected path, or roadmap status in this plan.
4. Do not change any score, sort key, candidate limit, context budget, or ContextPack rule.
5. Do not move retrieval functions into new execution modules. Only the trace package is new in P3.1.
6. Do not add a trace configuration section, persistence, generic event dictionaries, multi-round retrieval, or a quality catalog mode.
7. Every implementation task follows red-green-refactor discipline and ends in a focused commit.

## File Responsibility Map

| file | responsibility |
| --- | --- |
| src/context_search_tool/retrieval_trace/models.py | Frozen schema-v1 contract types and invariant validation |
| src/context_search_tool/retrieval_trace/collector.py | Canonical stages, fixed limits, timing, bounds, and internal rank history |
| src/context_search_tool/retrieval_trace/serialization.py | Exact schema-v1 dictionaries and success envelope |
| src/context_search_tool/retrieval_trace/__init__.py | Supported trace exports |
| src/context_search_tool/retrieval.py | One-pass traced wrapper and instrumentation around existing operations |
| src/context_search_tool/formatters.py | Trace JSON and Markdown rendering |
| src/context_search_tool/cli.py | cst trace command |
| src/context_search_tool/mcp_tools.py | context_search_trace_tool with no feedback persistence |
| src/context_search_tool/mcp_server.py | FastMCP trace registration |
| tests/test_retrieval_trace.py | Model, collector, bounds, timing, and serializer contract tests |
| tests/test_retrieval_trace_pipeline.py | Stage/source/provenance/parity/early-return pipeline tests |
| tests/test_formatters.py | Trace envelope and Markdown rendering tests |
| tests/test_cli_commands.py | CLI option, output, and stable-error tests |
| tests/test_mcp_tools.py | MCP success/error/privacy/one-pass tests |
| tests/test_mcp_server.py | Registered signature and forwarding tests |
| tests/test_quality_p3.py | Offline deterministic TraceCoverage acceptance |
| README.md | User-facing CLI and MCP trace operation |
| docs/retrieval-quality.md | P3.1 acceptance command and TraceCoverage definition |
| roadmap/2026-07-08-fast-context-like-retrieval-roadmap.md | Conditional P3.1 evidence and next P3.2 review |

## Task Dependency Order

1. Contract models.
2. Collector and exact serialization.
3. One-pass traced wrapper and early returns.
4. Query-understanding and recall instrumentation.
5. Expansion, ranking, context, and final-selection instrumentation.
6. Shared JSON and Markdown formatting.
7. CLI surface.
8. MCP surface and persistence isolation.
9. Deterministic P3.1 quality acceptance and documentation.
10. Full verification and conditional roadmap completion.

### Task 1: Define The Immutable Trace Contract

**Files:**

- Create: src/context_search_tool/retrieval_trace/models.py
- Create: src/context_search_tool/retrieval_trace/__init__.py
- Create: tests/test_retrieval_trace.py

- [ ] **Step 1: Write failing model and invariant tests**

Create tests/test_retrieval_trace.py with the following initial tests:

~~~python
from __future__ import annotations

import math

import pytest

from context_search_tool.retrieval_trace import (
    RetrievalTrace,
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
    selection = TraceSelection(
        rank=1,
        selection_kind="result",
        selection_reason="selected_within_result_limit",
        file_path="src/AuditStatus.java",
        start_line=1,
        end_line=20,
        score=1.1,
        origin_chunk_ids=("chunk-1",),
        sources=("semantic", "direct_text"),
        variant_ids=("original",),
        rank_history=(
            TraceRank("ranking", 1, 1.0),
            TraceRank("cohort_rerank", 1, 1.1),
            TraceRank("context_expansion", 1, 1.1),
            TraceRank("final_selection", 1, 1.1),
        ),
        adjustments=(TraceAdjustment("role_boost", 0.2),),
        adjustment_omitted_count=0,
        reasons=("semantic match",),
    )
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
~~~

- [ ] **Step 2: Run the contract tests and verify the import fails**

Run:

~~~bash
PYTHONPATH="$PWD/src" conda run -n base python -m pytest \
  tests/test_retrieval_trace.py -q
~~~

Expected: collection fails because context_search_tool.retrieval_trace does not exist.

- [ ] **Step 3: Implement the complete frozen model set**

Create src/context_search_tool/retrieval_trace/models.py:

~~~python
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
    if (
        not value
        or "\\" in value
        or path.is_absolute()
        or ".." in path.parts
    ):
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
~~~

Create src/context_search_tool/retrieval_trace/__init__.py:

~~~python
from context_search_tool.retrieval_trace.models import (
    RetrievalTrace,
    RetrievalTraceError,
    SOURCE_COUNT_KEYS,
    TraceAdjustment,
    TraceCandidate,
    TraceLimits,
    TraceOutcome,
    TraceQuery,
    TraceQueryVariant,
    TraceRank,
    TraceSelection,
    TraceSelectionKind,
    TraceSelectionReason,
    TraceStage,
    TraceTerminationReason,
)

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
~~~

- [ ] **Step 4: Run the model tests**

Run:

~~~bash
PYTHONPATH="$PWD/src" conda run -n base python -m pytest \
  tests/test_retrieval_trace.py -q
~~~

Expected: all tests pass.

- [ ] **Step 5: Commit the contract models**

~~~bash
git add \
  src/context_search_tool/retrieval_trace/__init__.py \
  src/context_search_tool/retrieval_trace/models.py \
  tests/test_retrieval_trace.py
git commit -m "feat: define retrieval trace contract"
~~~

### Task 2: Add The Bounded Collector And Exact Serializer

**Files:**

- Create: src/context_search_tool/retrieval_trace/collector.py
- Create: src/context_search_tool/retrieval_trace/serialization.py
- Modify: src/context_search_tool/retrieval_trace/__init__.py
- Modify: tests/test_retrieval_trace.py

- [ ] **Step 1: Add failing collector-order, bound, timing, and schema tests**

Append to tests/test_retrieval_trace.py:

~~~python
from context_search_tool.retrieval_trace import (
    CANONICAL_TRACE_STAGES,
    RetrievalTraceCollector,
    SOURCE_COUNT_KEYS,
    retrieval_trace_payload,
    trace_payload,
)


class TickClock:
    def __init__(self, *values: int) -> None:
        self.values = iter(values)

    def __call__(self) -> int:
        return next(self.values)


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
    assert tuple(payload["source_counts"]) == SOURCE_COUNT_KEYS
    assert "content" not in repr(payload)
    assert trace_payload("/repo", "audit status", trace) == {
        "ok": True,
        "repo": "/repo",
        "query": "audit status",
        "trace": payload,
    }
~~~

- [ ] **Step 2: Run the focused tests and verify the new symbols are missing**

Run:

~~~bash
PYTHONPATH="$PWD/src" conda run -n base python -m pytest \
  tests/test_retrieval_trace.py -q
~~~

Expected: collection fails on the collector and serializer imports.

- [ ] **Step 3: Implement canonical stages, counts, timing, and bounds**

Create src/context_search_tool/retrieval_trace/collector.py:

~~~python
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
        for key, count in source_counts:
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
            duration_ms=max(0, (self._clock_ns() - self._started_ns) // 1_000_000),
            limits=self.limits,
            query=self._query,
            source_counts=tuple(self._source_counts.items()),
            stages=tuple(self._stages),
            final_selection_count=len(final_selections),
            final_selection_omitted_count=omitted,
            final_selections=preview,
        )
~~~

The explicit stop operation freezes stage duration before candidate observation
conversion. finish_stage therefore performs no clock read.

- [ ] **Step 4: Implement explicit schema-v1 serialization**

Create src/context_search_tool/retrieval_trace/serialization.py with explicit
converters for every model. Do not use dataclasses.asdict because it makes private
model changes silently public.

~~~python
from __future__ import annotations

from typing import Any

from context_search_tool.retrieval_trace.models import (
    RetrievalTrace,
    TraceAdjustment,
    TraceCandidate,
    TraceOutcome,
    TraceQuery,
    TraceQueryVariant,
    TraceSelection,
    TraceSelectionKind,
    TraceSelectionReason,
    TraceTerminationReason,
    TraceRank,
    TraceSelection,
    TraceStage,
)


def trace_payload(repo: str, query: str, trace: RetrievalTrace) -> dict[str, Any]:
    return {
        "ok": True,
        "repo": repo,
        "query": query,
        "trace": retrieval_trace_payload(trace),
    }


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
            _selection_payload(selection)
            for selection in trace.final_selections
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
            _candidate_payload(candidate)
            for candidate in stage.top_candidates
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
        "rank_history": [
            _rank_payload(rank)
            for rank in selection.rank_history
        ],
        "adjustments": [
            _adjustment_payload(adjustment)
            for adjustment in selection.adjustments
        ],
        "adjustment_omitted_count": selection.adjustment_omitted_count,
        "reasons": list(selection.reasons),
    }


def _rank_payload(rank: TraceRank) -> dict[str, Any]:
    return {"stage": rank.stage, "rank": rank.rank, "score": float(rank.score)}


def _adjustment_payload(adjustment: TraceAdjustment) -> dict[str, Any]:
    return {"name": adjustment.name, "value": float(adjustment.value)}
~~~

Export the collector constants, collector class, and serializer functions from
src/context_search_tool/retrieval_trace/__init__.py:

~~~python
from context_search_tool.retrieval_trace.collector import (
    CANONICAL_TRACE_STAGES,
    RetrievalTraceCollector,
    StageToken,
    StoppedStage,
)
from context_search_tool.retrieval_trace.serialization import (
    retrieval_trace_payload,
    trace_payload,
)
~~~

Add the same names to __all__.

- [ ] **Step 5: Run focused tests and exact JSON safety checks**

Run:

~~~bash
PYTHONPATH="$PWD/src" conda run -n base python -m pytest \
  tests/test_retrieval_trace.py -q
PYTHONPATH="$PWD/src" conda run -n base python - <<'PY'
from context_search_tool.retrieval_trace import (
    RetrievalTraceError,
    TraceAdjustment,
)

try:
    TraceAdjustment("bad", float("nan"))
except RetrievalTraceError:
    print("non-finite adjustment rejected")
else:
    raise SystemExit("non-finite adjustment accepted")
PY
~~~

Expected: all tests pass and the probe prints non-finite adjustment rejected.

- [ ] **Step 6: Commit collector and serializer**

~~~bash
git add \
  src/context_search_tool/retrieval_trace/__init__.py \
  src/context_search_tool/retrieval_trace/collector.py \
  src/context_search_tool/retrieval_trace/serialization.py \
  tests/test_retrieval_trace.py
git commit -m "feat: collect bounded retrieval trace stages"
~~~

### Task 3: Add The One-Pass Traced Execution Wrapper And Early Outcomes

**Files:**

- Modify: src/context_search_tool/retrieval.py
- Modify: src/context_search_tool/retrieval_trace/collector.py
- Create: tests/test_retrieval_trace_pipeline.py

- [ ] **Step 1: Write failing one-pass, parity, null-path, and early-return tests**

Create tests/test_retrieval_trace_pipeline.py:

~~~python
from __future__ import annotations

from pathlib import Path

import pytest

from context_search_tool import retrieval
from context_search_tool.config import RetrievalConfig, ToolConfig
from context_search_tool.context_pack import (
    build_context_pack,
    canonical_context_pack_bytes,
    context_pack_payload,
    resolve_context_pack_options,
)
from context_search_tool.formatters import query_payload
from context_search_tool.indexer import index_repository


def _indexed_repo(tmp_path: Path) -> tuple[Path, ToolConfig]:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "AuditController.py").write_text(
        "def audit_status():\n    return 'INVOLVED_BY_ME'\n",
        encoding="utf-8",
    )
    config = ToolConfig(
        retrieval=RetrievalConfig(
            semantic_top_k=8,
            lexical_top_k=8,
            final_top_k=4,
            context_before_lines=0,
            context_after_lines=0,
        )
    )
    index_repository(repo, config)
    return repo, config


def test_trace_repository_runs_query_once_and_preserves_raw_and_pack_payloads(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, config = _indexed_repo(tmp_path)
    plain = retrieval.query_repository(repo, "INVOLVED_BY_ME", config)
    calls = 0
    original = retrieval._semantic_candidates

    def counted(*args, **kwargs):
        nonlocal calls
        calls += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(retrieval, "_semantic_candidates", counted)
    traced = retrieval.trace_repository(repo, "INVOLVED_BY_ME", config)

    assert calls == 1
    assert query_payload(traced.bundle) == query_payload(plain)
    options = resolve_context_pack_options(
        config,
        context_lines=None,
        max_evidence_anchors=retrieval.evidence_anchor_top_k(
            config.retrieval.final_top_k
        ),
    )
    assert canonical_context_pack_bytes(
        context_pack_payload(build_context_pack(traced.bundle, options))
    ) == canonical_context_pack_bytes(
        context_pack_payload(build_context_pack(plain, options))
    )


def test_plain_query_does_not_construct_or_touch_trace_observations(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, config = _indexed_repo(tmp_path)

    def forbidden(*args, **kwargs):
        raise AssertionError("ordinary query touched trace code")

    monkeypatch.setattr(retrieval, "RetrievalTraceCollector", forbidden)
    monkeypatch.setattr(retrieval, "_trace_candidate_observations", forbidden)

    assert retrieval.query_repository(repo, "audit", config).results


def test_trace_repository_reports_missing_index_without_changing_bundle(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    config = ToolConfig()

    plain = retrieval.query_repository(repo, "audit", config)
    traced = retrieval.trace_repository(repo, "audit", config)

    assert traced.bundle == plain
    assert traced.trace.outcome == "empty"
    assert traced.trace.termination_reason == "missing_index"
    assert traced.trace.stages == ()
~~~

- [ ] **Step 2: Run the new tests and verify trace_repository is missing**

Run:

~~~bash
PYTHONPATH="$PWD/src" conda run -n base python -m pytest \
  tests/test_retrieval_trace_pipeline.py -q
~~~

Expected: failures report that trace_repository and trace helpers do not exist.

- [ ] **Step 3: Add TracedQueryBundle and the wrapper without changing QueryBundle**

Add trace imports near the other retrieval.py imports:

~~~python
from context_search_tool.retrieval_trace import (
    RetrievalTrace,
    RetrievalTraceCollector,
    StageToken,
    TraceCandidate,
    TraceOutcome,
    TraceQuery,
    TraceQueryVariant,
    TraceSelection,
    TraceSelectionKind,
    TraceSelectionReason,
    TraceTerminationReason,
)
~~~

Add immediately after QueryBundle:

~~~python
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
~~~

Add these public one-shot methods to RetrievalTraceCollector:

~~~python
def set_finished_trace(self, trace: RetrievalTrace) -> None:
    if hasattr(self, "_finished_trace"):
        raise RetrievalTraceError("trace collector was already finalized")
    self._finished_trace = trace


def finished_trace(self) -> RetrievalTrace:
    try:
        return self._finished_trace
    except AttributeError as exc:
        raise RetrievalTraceError("trace collector was not finalized") from exc
~~~

Extend query_repository with one keyword-only argument:

~~~text
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
~~~

- [ ] **Step 4: Add query metadata and one finalization helper**

Add these retrieval.py helpers:

~~~python
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
    query: TraceQuery,
    outcome: TraceOutcome,
    termination_reason: TraceTerminationReason,
    final_selections: tuple[TraceSelection, ...] = (),
) -> None:
    if collector is None:
        return
    collector.record_query(query)
    trace = collector.finish(
        outcome=outcome,
        termination_reason=termination_reason,
        final_selections=tuple(final_selections),
    )
    collector.set_finished_trace(trace)


def _trace_candidate_observations(*args, **kwargs) -> tuple[TraceCandidate, ...]:
    return ()
~~~

The final helper intentionally returns an empty tuple only for this red-green
checkpoint. Tasks 4 and 5 replace it with actual observations before any public
surface is added.

- [ ] **Step 5: Finalize each existing early return**

For the missing-index branch, build the same QueryBundle in a local variable,
record original query metadata, and return it:

~~~python
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
        query=_trace_query(
            original_tokens=original_tokens,
            expanded_tokens=tokens,
            variants=query_variants,
            variant_retrieval_status=variant_retrieval_status,
            plan=plan,
        ),
        outcome="empty",
        termination_reason="missing_index",
    )
    return bundle
~~~

Replace the handled deleted_chunk_ids SQLite branch with:

~~~python
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
        query=_trace_query(
            original_tokens=original_tokens,
            expanded_tokens=tokens,
            variants=query_variants,
            variant_retrieval_status=variant_retrieval_status,
            plan=plan,
        ),
        outcome="partial",
        termination_reason="store_read_error",
    )
    return bundle
~~~

Replace the complete empty merged-candidate branch with:

~~~python
if not candidates:
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
        query=_trace_query(
            original_tokens=original_tokens,
            expanded_tokens=tokens,
            variants=query_variants,
            variant_retrieval_status=variant_retrieval_status,
            plan=plan,
        ),
        outcome="empty",
        termination_reason="no_candidates",
    )
    return bundle
~~~

Replace the normal QueryBundle return with this exact assignment, finalization,
and return:

~~~python
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
    query=_trace_query(
        original_tokens=original_tokens,
        expanded_tokens=tokens,
        variants=query_variants,
        variant_retrieval_status=variant_retrieval_status,
        plan=plan,
    ),
    outcome="complete",
    termination_reason="completed",
)
return bundle
~~~

Do not alter the fields or order used to construct any QueryBundle.

- [ ] **Step 6: Run wrapper, existing retrieval, and ContextPack tests**

Run:

~~~bash
PYTHONPATH="$PWD/src" conda run -n base python -m pytest \
  tests/test_retrieval_trace.py \
  tests/test_retrieval_trace_pipeline.py \
  tests/test_retrieval_pipeline.py \
  tests/test_context_pack.py \
  tests/test_context_excerpts.py \
  -q
~~~

Expected: all tests pass. The trace has no stages yet except early outcomes; this
is an internal checkpoint and no CLI/MCP trace surface exists.

- [ ] **Step 7: Commit the wrapper and early outcomes**

~~~bash
git add \
  src/context_search_tool/retrieval.py \
  src/context_search_tool/retrieval_trace/collector.py \
  tests/test_retrieval_trace_pipeline.py
git commit -m "feat: add one-pass traced retrieval wrapper"
~~~

### Task 4: Instrument Query Understanding And Candidate Recall

**Files:**

- Modify: src/context_search_tool/retrieval.py
- Modify: tests/test_retrieval_trace_pipeline.py

- [ ] **Step 1: Write failing canonical-stage and source-count tests**

Append:

~~~python
def test_trace_records_query_understanding_and_all_recall_sources_in_order(
    tmp_path: Path,
) -> None:
    repo, config = _indexed_repo(tmp_path)

    traced = retrieval.trace_repository(repo, "INVOLVED_BY_ME audit", config)
    names = [stage.name for stage in traced.trace.stages]

    assert names[:8] == [
        "query_understanding",
        "semantic_recall",
        "lexical_recall",
        "path_symbol_recall",
        "direct_text_recall",
        "signal_recall",
        "planner_hint_recall",
        "direct_merge",
    ]
    by_name = {stage.name: stage for stage in traced.trace.stages}
    assert by_name["semantic_recall"].source_counts[0][0] == "semantic"
    assert by_name["direct_merge"].unique_output_count <= (
        by_name["semantic_recall"].output_count
        + by_name["lexical_recall"].output_count
        + by_name["path_symbol_recall"].output_count
        + by_name["direct_text_recall"].output_count
        + by_name["signal_recall"].output_count
        + by_name["planner_hint_recall"].output_count
    )
    assert tuple(dict(traced.trace.source_counts)) == (
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
    assert all(
        len(stage.top_candidates) <= traced.trace.limits.stage_top_k
        for stage in traced.trace.stages
    )


def test_recall_previews_have_relative_paths_and_no_content(tmp_path: Path) -> None:
    repo, config = _indexed_repo(tmp_path)
    trace = retrieval.trace_repository(repo, "audit", config).trace

    candidates = [
        candidate
        for stage in trace.stages
        for candidate in stage.top_candidates
    ]
    assert candidates
    assert all(
        not Path(candidate.file_path).is_absolute()
        for candidate in candidates
    )
    assert "INVOLVED_BY_ME" not in repr(trace)
~~~

Add a planner provenance test using the existing QueryPlan model:

~~~python
from context_search_tool.models import QueryPlan


class FixedPlanner:
    def plan(self, query: str, repo_profile=None) -> QueryPlan:
        return QueryPlan(
            original_query=query,
            rewritten_queries=["approval state"],
            grep_keywords=["approval"],
            status="ok",
            provider="test",
            model="fixed",
            intent="implementation",
            latency_ms=3,
        )


def test_trace_preserves_executed_planner_variant_metadata(tmp_path: Path) -> None:
    repo, config = _indexed_repo(tmp_path)
    traced = retrieval.trace_repository(
        repo,
        "audit status",
        config,
        planner=FixedPlanner(),
    )

    assert [item.variant_id for item in traced.trace.query.variants] == [
        "original",
        "planner:0",
    ]
    assert traced.trace.query.planner_status == "ok"
    semantic = next(
        stage
        for stage in traced.trace.stages
        if stage.name == "semantic_recall"
    )
    assert set(dict(semantic.source_counts)) == {
        "semantic",
        "planner_semantic",
    }
~~~

- [ ] **Step 2: Run tests and verify recall stages are absent**

Run:

~~~bash
PYTHONPATH="$PWD/src" conda run -n base python -m pytest \
  tests/test_retrieval_trace_pipeline.py -q
~~~

Expected: the new stage assertions fail because only final outcomes exist.

- [ ] **Step 3: Add trace-only observation conversion helpers**

Add these helpers to retrieval.py. They are called only when collector is not
None.

~~~python
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
    store: SQLiteStore,
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
    store: SQLiteStore,
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
~~~

stop_stage captures the clock before _trace_candidate_observations runs, and
finish_stage accepts the stopped token without reading the clock again.

- [ ] **Step 4: Instrument query understanding**

Immediately before planner/profile work:

~~~python
query_stage = _trace_stage_start(
    trace_collector,
    "query_understanding",
    input_count=len(original_tokens),
)
~~~

Immediately after tokens and initial query variants are built, stop and finish the
stage without candidate observations:

~~~python
if trace_collector is not None and query_stage is not None:
    stopped = trace_collector.stop_stage(query_stage)
    trace_collector.finish_stage(
        stopped,
        output_count=len(tokens),
        unique_output_count=len(set(tokens)),
    )
~~~

Do not record final TraceQuery metadata here. _finish_trace records the executed
variant list and embedding fallback status after semantic recall.

- [ ] **Step 5: Split _initial_candidates locals and record the four stages**

Add trace_collector to the private signature and replace the inline combined
return with explicit locals:

~~~python
def _initial_candidates(
    index_dir: Path,
    store: SQLiteStore,
    query: str,
    original_tokens: list[str],
    query_variants: list[QueryVariant],
    config: ToolConfig,
    deleted_ids: set[str],
    trace_collector: RetrievalTraceCollector | None = None,
) -> tuple[list[RetrievalCandidate], list[QueryVariant], str]:
    token = _trace_stage_start(
        trace_collector,
        "semantic_recall",
        input_count=len(query_variants),
    )
    semantic, executed_variants, status = _semantic_candidates(
        index_dir,
        query_variants,
        config,
        deleted_ids,
    )
    _finish_candidate_stage(
        trace_collector,
        token,
        store=store,
        candidates=semantic,
        source_keys=("semantic", "planner_semantic"),
    )

    token = _trace_stage_start(
        trace_collector,
        "lexical_recall",
        input_count=len(original_tokens),
    )
    lexical = _lexical_candidates(
        store,
        original_tokens,
        config.retrieval.lexical_top_k,
    )
    _finish_candidate_stage(
        trace_collector,
        token,
        store=store,
        candidates=lexical,
        source_keys=("lexical",),
    )

    token = _trace_stage_start(
        trace_collector,
        "path_symbol_recall",
        input_count=len(original_tokens),
    )
    path_symbol = store.path_symbol_search(
        original_tokens,
        config.retrieval.lexical_top_k,
    )
    _finish_candidate_stage(
        trace_collector,
        token,
        store=store,
        candidates=path_symbol,
        source_keys=("path_symbol",),
    )

    probes = _direct_text_probes(query, original_tokens)
    token = _trace_stage_start(
        trace_collector,
        "direct_text_recall",
        input_count=len(probes),
    )
    direct_text = store.direct_text_search(
        probes,
        max(
            config.retrieval.lexical_top_k,
            config.retrieval.final_top_k * _DIRECT_TEXT_TOP_K_MULTIPLIER,
        ),
    )
    _finish_candidate_stage(
        trace_collector,
        token,
        store=store,
        candidates=direct_text,
        source_keys=("direct_text",),
    )
    return [
        *semantic,
        *lexical,
        *path_symbol,
        *direct_text,
    ], executed_variants, status
~~~

Replace the query_repository call with:

~~~python
initial_candidates, query_variants, variant_retrieval_status = (
    _initial_candidates(
        index_dir,
        store,
        query,
        original_tokens,
        query_variants,
        config,
        deleted_ids,
        trace_collector,
    )
)
~~~

Keep _direct_text_candidates unchanged because existing focused tests call it
directly; the new inline branch uses the identical probes, limit formula, and
store method shown above.

- [ ] **Step 6: Instrument signal, planner hint, and direct merge**

Replace the three unobserved calls in query_repository with:

~~~python
token = _trace_stage_start(
    trace_collector,
    "signal_recall",
    input_count=len(original_tokens),
)
signal_candidates = _signal_candidates(store, original_tokens, config)
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
planner_candidates = _planner_hint_candidates(store, hint_tokens, config)
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
direct_candidates = _merge_candidates(raw_direct)
_finish_candidate_stage(
    trace_collector,
    token,
    store=store,
    candidates=list(direct_candidates.values()),
)
~~~

- [ ] **Step 7: Run recall, planner, and raw compatibility tests**

Run:

~~~bash
PYTHONPATH="$PWD/src" conda run -n base python -m pytest \
  tests/test_retrieval_trace.py \
  tests/test_retrieval_trace_pipeline.py \
  tests/test_retrieval_pipeline.py \
  tests/test_formatters.py \
  tests/test_mcp_tools.py \
  -q
~~~

Expected: all tests pass. Inspect one traced payload and verify that no stage
candidate contains content or an absolute path.

- [ ] **Step 8: Commit recall instrumentation**

~~~bash
git add \
  src/context_search_tool/retrieval.py \
  tests/test_retrieval_trace_pipeline.py
git commit -m "feat: trace retrieval candidate sources"
~~~

### Task 5: Trace Expansion, Ranking, Context, And Final Selection

**Files:**

- Modify: src/context_search_tool/retrieval.py
- Modify: src/context_search_tool/retrieval_trace/collector.py
- Modify: src/context_search_tool/retrieval_trace/models.py
- Modify: tests/test_retrieval_trace.py
- Modify: tests/test_retrieval_trace_pipeline.py

- [ ] **Step 1: Add failing full-stage, provenance, rank, adjustment, and decision tests**

Import CANONICAL_TRACE_STAGES from context_search_tool.retrieval_trace, then append
tests that exercise the complete stage sequence on the deterministic indexed
fixture:

~~~python
def test_complete_trace_has_all_canonical_stages_and_final_provenance(
    tmp_path: Path,
) -> None:
    repo, config = _indexed_repo(tmp_path)
    traced = retrieval.trace_repository(repo, "INVOLVED_BY_ME audit", config)

    assert [stage.name for stage in traced.trace.stages] == list(
        CANONICAL_TRACE_STAGES
    )
    assert traced.trace.outcome == "complete"
    assert traced.trace.termination_reason == "completed"
    assert traced.trace.final_selection_count == (
        len(traced.bundle.results) + len(traced.bundle.evidence_anchors)
    )
    assert traced.trace.final_selections
    for selection in traced.trace.final_selections:
        assert selection.origin_chunk_ids
        assert selection.sources
        assert selection.rank_history
        assert selection.selection_reason in {
            "selected_within_result_limit",
            "selected_within_anchor_limit",
        }
        assert all(adjustment.value != 0 for adjustment in selection.adjustments)


def test_final_selection_stage_explains_limits_and_anchor_duplicates(
    tmp_path: Path,
) -> None:
    repo, config = _indexed_repo(tmp_path)
    traced = retrieval.trace_repository(repo, "audit", config)
    selection = traced.trace.stages[-1]

    assert selection.name == "final_selection"
    assert tuple(dict(selection.decision_counts)) == (
        "selected_result",
        "selected_anchor",
        "duplicate_anchor",
        "result_limit",
        "anchor_limit",
    )
    assert sum(dict(selection.decision_counts).values()) == selection.input_count


def test_adjustments_are_strongest_first_and_bounded(tmp_path: Path) -> None:
    repo, config = _indexed_repo(tmp_path)
    traced = retrieval.trace_repository(repo, "audit", config)

    for selection in traced.trace.final_selections:
        assert len(selection.adjustments) <= traced.trace.limits.adjustment_top_k
        assert list(selection.adjustments) == sorted(
            selection.adjustments,
            key=lambda item: (-abs(item.value), item.name),
        )
~~~

Append this final-state invariant test to tests/test_retrieval_trace.py:

~~~python
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
~~~

Add these imports and the focused overlap/ceiling test:

~~~python
from context_search_tool.models import (
    RetrievalCandidate,
    SemanticMatch,
)
from context_search_tool.retrieval_trace import TraceLimits


class FinalSelectionCollector:
    limits = TraceLimits()
    rank_history = {
        "chunk-a": (
            ("ranking", 4, 0.9),
            ("cohort_rerank", 3, 1.0),
            ("context_expansion", 2, 1.0),
        ),
        "chunk-b": (
            ("ranking", 2, 1.1),
            ("cohort_rerank", 5, 0.8),
            ("context_expansion", 2, 0.8),
        ),
    }


def test_merged_final_selection_keeps_origins_best_ranks_and_clamp() -> None:
    item = retrieval._ExpandedResult(
        chunk_ids=["chunk-a", "chunk-b"],
        file_path=Path("src/AuditStatus.java"),
        start_line=1,
        end_line=20,
        content="SOURCE_CONTENT_SENTINEL",
        score=1.2,
        score_parts={
            "semantic": 0.8,
            "combined_score": 1.2,
            "role_boost": 0.2,
            "test_penalty": -0.1,
        },
        reasons=["semantic match", "business role boost"],
        followup_keywords=[],
        rank_tier=0,
        rerank_score=1.0,
        evidence_class="original_direct",
        evidence_priority=0,
        semantic_matches=[],
        pre_ceiling_rerank_score=1.25,
        was_ceiling_clamped=True,
    )
    decisions = retrieval._FinalTraceDecisions(
        selected=(
            retrieval._FinalTraceInput(
                kind="result",
                reason="selected_within_result_limit",
                item=item,
            ),
        ),
        counts=(
            ("selected_result", 1),
            ("selected_anchor", 0),
            ("duplicate_anchor", 0),
            ("result_limit", 0),
            ("anchor_limit", 0),
        ),
    )
    candidates = {
        "chunk-a": RetrievalCandidate(
            chunk_id="chunk-a",
            score=0.8,
            source="semantic",
            score_parts={"semantic": 0.8},
            semantic_matches=[SemanticMatch("original", 0.8)],
        ),
        "chunk-b": RetrievalCandidate(
            chunk_id="chunk-b",
            score=0.7,
            source="relation",
            score_parts={"relation": 0.7},
        ),
    }

    selection = retrieval._trace_final_selections(
        decisions,
        candidates,
        FinalSelectionCollector(),
    )[0]

    assert selection.origin_chunk_ids == ("chunk-a", "chunk-b")
    assert [(item.stage, item.rank) for item in selection.rank_history] == [
        ("ranking", 2),
        ("cohort_rerank", 3),
        ("context_expansion", 2),
        ("final_selection", 1),
    ]
    adjustment_names = [item.name for item in selection.adjustments]
    assert adjustment_names == [
        "planner_ceiling_clamp",
        "role_boost",
        "test_penalty",
    ]
    assert "semantic" not in adjustment_names
    assert "combined_score" not in adjustment_names
    assert "SOURCE_CONTENT_SENTINEL" not in repr(selection)
~~~

- [ ] **Step 2: Run the new tests and verify stages 9-15 are missing**

Run:

~~~bash
PYTHONPATH="$PWD/src" conda run -n base python -m pytest \
  tests/test_retrieval_trace_pipeline.py -q
~~~

Expected: failures identify missing expansion/rank/final stages and selections.

- [ ] **Step 3: Instrument anchor, relation, and candidate merging**

Wrap the existing operations without changing their arguments:

~~~python
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

relation_seed_candidates = _merge_candidates(
    [*direct_candidates.values(), *anchor_candidates]
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
candidates = _merge_candidates(all_candidates)
_finish_candidate_stage(
    trace_collector,
    token,
    store=store,
    candidates=list(candidates.values()),
)
~~~

The _TRACE_PUBLIC_SOURCE_FAMILY mapping counts anchor_expansion,
anchored_relation, same_file_anchor, and directory_anchor as the single public
anchor_expansion family without renaming live candidates.

- [ ] **Step 4: Add ranked and expanded observation converters**

Add:

~~~python
def _trace_ranked_observations(
    ranked: list[_RankedChunk],
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
    expanded: list[_ExpandedResult],
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
        sources = _ordered_unique(
            [
                source
                for candidate in source_candidates
                for source in _trace_sources(candidate)
            ]
        )
        variant_ids = _ordered_unique(
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
~~~

- [ ] **Step 5: Record ranking, cohort, and context stages with full internal rank history**

For each stage, stop timing before observation conversion. Build typed candidate
observations only for stage_top_k, and stream lightweight chunk/rank/score tuples
for all rank-bearing candidates into collector history. This keeps snapshots
bounded without losing final-selection rank history.

~~~python
token = _trace_stage_start(
    trace_collector,
    "ranking",
    input_count=len(candidates),
)
ranked_chunks = _rank_chunks(store, candidates, original_tokens, query)
if trace_collector is not None and token is not None:
    stopped = trace_collector.stop_stage(token)
    observations = _trace_ranked_observations(
        ranked_chunks,
        candidates,
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
ranked_chunks = _apply_frontend_import_cohort_rerank(
    repo,
    ranked_chunks,
    query,
)
if trace_collector is not None and token is not None:
    stopped = trace_collector.stop_stage(token)
    observations = _trace_ranked_observations(
        ranked_chunks,
        candidates,
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
        candidates,
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
~~~

- [ ] **Step 6: Capture final decisions without adding normal-query allocations**

Import Literal and overload from typing. Add internal frozen selection-input
models and a fixed decision-key order:

~~~python
from typing import Literal, overload


@dataclass(frozen=True)
class _FinalTraceInput:
    kind: TraceSelectionKind
    reason: TraceSelectionReason
    item: _ExpandedResult


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
~~~

Extend _split_code_results_and_evidence_anchors with collect_trace: bool = False
and overloads keyed by Literal[False] and Literal[True]. The default overload
keeps the current two-item return exactly; the trace overload returns a third
_FinalTraceDecisions value. Initialize the counter only when collect_trace is
true. For each existing branch:

~~~python
@overload
def _split_code_results_and_evidence_anchors(
    expanded: list[_ExpandedResult],
    *,
    final_top_k: int,
    anchor_top_k: int,
    collect_trace: Literal[False] = False,
) -> tuple[list[_ExpandedResult], list[EvidenceAnchor]]: ...


@overload
def _split_code_results_and_evidence_anchors(
    expanded: list[_ExpandedResult],
    *,
    final_top_k: int,
    anchor_top_k: int,
    collect_trace: Literal[True],
) -> tuple[
    list[_ExpandedResult],
    list[EvidenceAnchor],
    _FinalTraceDecisions,
]: ...


def _split_code_results_and_evidence_anchors(
    expanded: list[_ExpandedResult],
    *,
    final_top_k: int,
    anchor_top_k: int,
    collect_trace: bool = False,
) -> (
    tuple[list[_ExpandedResult], list[EvidenceAnchor]]
    | tuple[
        list[_ExpandedResult],
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
    code_results: list[_ExpandedResult] = []
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
~~~

The default path preserves the current two-item return and code/anchor lists;
existing direct callers and tests remain unchanged. Trace-only lists and counters
are allocated only when collect_trace is true.

- [ ] **Step 7: Build bounded final selections from existing values**

Define the exact materialized-adjustment policy. It intentionally observes
existing named score parts and does not refactor the scorer into a second ledger:

~~~python
_TRACE_ADJUSTMENT_SUFFIXES = ("_boost", "_penalty", "_match")


def _is_trace_adjustment(name: str) -> bool:
    return name.endswith(_TRACE_ADJUSTMENT_SUFFIXES)
~~~

Implement:

~~~python
def _trace_adjustments(
    item: _ExpandedResult,
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
            values.append(TraceAdjustment("planner_ceiling_clamp", float(clamp)))
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
            _ordered_unique(
                [
                    source
                    for candidate in source_candidates
                    for source in _trace_sources(candidate)
                ]
            )
        )
        variant_ids = tuple(
            _ordered_unique(
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
~~~

Add TraceAdjustment and TraceRank to the existing
context_search_tool.retrieval_trace import block:

~~~python
from context_search_tool.retrieval_trace import (
    TraceAdjustment,
    TraceRank,
)
~~~

- [ ] **Step 8: Finish final-selection stage and pass selections to _finish_trace**

Time only _split_code_results_and_evidence_anchors. Stop the stage, build
selections, record exact decision counts, and pass them to finalization:

~~~python
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
final_selections = ()
if trace_collector is not None and token is not None:
    stopped = trace_collector.stop_stage(token)
    assert trace_decisions is not None
    final_selections = _trace_final_selections(
        trace_decisions,
        candidates,
        trace_collector,
    )
    trace_collector.finish_stage(
        stopped,
        output_count=len(trace_decisions.selected),
        unique_output_count=len(trace_decisions.selected),
        candidates=(),
        decision_counts=trace_decisions.counts,
    )
~~~

Replace the Task 3 completed finalization call with:

~~~python
_finish_trace(
    trace_collector,
    query=_trace_query(
        original_tokens=original_tokens,
        expanded_tokens=tokens,
        variants=query_variants,
        variant_retrieval_status=variant_retrieval_status,
        plan=plan,
    ),
    outcome="complete",
    termination_reason="completed",
    final_selections=final_selections,
)
~~~

The QueryBundle construction remains unchanged.

Complete the model invariant only now that the full final-selection stage exists.
Add to RetrievalTrace.__post_init__:

~~~python
if self.outcome == "complete" and (
    not self.stages or self.stages[-1].name != "final_selection"
):
    raise RetrievalTraceError(
        "completed trace must end with final_selection"
    )
~~~

- [ ] **Step 9: Run trace, retrieval, ContextPack, and quality-focused suites**

Run:

~~~bash
PYTHONPATH="$PWD/src" conda run -n base python -m pytest \
  tests/test_retrieval_trace.py \
  tests/test_retrieval_trace_pipeline.py \
  tests/test_retrieval_pipeline.py \
  tests/test_context_pack.py \
  tests/test_context_needs.py \
  tests/test_context_excerpts.py \
  tests/test_quality_p2.py \
  -q
~~~

Expected: all tests pass. Compare the raw and ContextPack parity assertions before
accepting any trace-specific assertion.

- [ ] **Step 10: Commit complete pipeline instrumentation**

~~~bash
git add \
  src/context_search_tool/retrieval.py \
  src/context_search_tool/retrieval_trace/collector.py \
  src/context_search_tool/retrieval_trace/models.py \
  tests/test_retrieval_trace.py \
  tests/test_retrieval_trace_pipeline.py
git commit -m "feat: trace retrieval ranking and selection"
~~~

### Task 6: Add Shared JSON And Markdown Trace Formatting

**Files:**

- Modify: src/context_search_tool/formatters.py
- Modify: src/context_search_tool/retrieval_trace/serialization.py
- Modify: tests/test_formatters.py
- Modify: tests/test_retrieval_trace.py

- [ ] **Step 1: Write failing exact-envelope, JSON, and Markdown tests**

Add these imports and a complete deterministic fixture to
tests/test_formatters.py:

~~~python
from context_search_tool.formatters import (
    TraceFormatError,
    format_trace_json,
    format_trace_markdown,
    trace_payload,
)
from context_search_tool.retrieval_trace import (
    RetrievalTrace,
    TraceAdjustment,
    TraceCandidate,
    TraceLimits,
    TraceQuery,
    TraceQueryVariant,
    TraceRank,
    TraceSelection,
    TraceStage,
)


def _trace() -> RetrievalTrace:
    candidate = TraceCandidate(
        rank=1,
        chunk_id="chunk-audit",
        file_path="src/AuditStatus.java",
        start_line=1,
        end_line=20,
        score=1.1,
        sources=("semantic",),
        variant_ids=("original",),
    )
    selection = TraceSelection(
        rank=1,
        selection_kind="result",
        selection_reason="selected_within_result_limit",
        file_path="src/AuditStatus.java",
        start_line=1,
        end_line=20,
        score=1.1,
        origin_chunk_ids=("chunk-audit",),
        sources=("semantic",),
        variant_ids=("original",),
        rank_history=(
            TraceRank("ranking", 1, 1.0),
            TraceRank("cohort_rerank", 1, 1.1),
            TraceRank("context_expansion", 1, 1.1),
            TraceRank("final_selection", 1, 1.1),
        ),
        adjustments=(TraceAdjustment("role_boost", 0.2),),
        adjustment_omitted_count=0,
        reasons=("semantic match",),
    )
    return RetrievalTrace(
        schema_version=1,
        outcome="complete",
        termination_reason="completed",
        duration_ms=8,
        limits=TraceLimits(),
        query=TraceQuery(
            original_token_count=2,
            expanded_token_count=2,
            variant_retrieval_status="original_only",
            variants=(
                TraceQueryVariant(
                    "original",
                    "audit status",
                    "original",
                ),
            ),
        ),
        source_counts=(
            ("semantic", 1),
            ("planner_semantic", 0),
            ("lexical", 0),
            ("path_symbol", 0),
            ("direct_text", 0),
            ("signal", 0),
            ("planner_lexical", 0),
            ("planner_path_symbol", 0),
            ("planner_signal", 0),
            ("anchor_expansion", 0),
            ("relation", 0),
        ),
        stages=(
            TraceStage(
                name="semantic_recall",
                input_count=1,
                output_count=1,
                unique_output_count=1,
                duration_ms=2,
                source_counts=(
                    ("semantic", 1),
                    ("planner_semantic", 0),
                ),
                top_candidates=(candidate,),
            ),
            TraceStage(
                name="final_selection",
                input_count=1,
                output_count=1,
                unique_output_count=1,
                duration_ms=1,
                decision_counts=(
                    ("selected_result", 1),
                    ("selected_anchor", 0),
                    ("duplicate_anchor", 0),
                    ("result_limit", 0),
                    ("anchor_limit", 0),
                ),
            ),
        ),
        final_selection_count=1,
        final_selection_omitted_count=0,
        final_selections=(selection,),
    )


def test_trace_formatters_share_exact_envelope_and_omit_source_content() -> None:
    envelope = trace_payload(Path("/repo"), "audit status", _trace())
    encoded = format_trace_json(envelope)
    parsed = json.loads(encoded)

    assert tuple(parsed) == ("ok", "repo", "query", "trace")
    assert parsed["trace"]["schema_version"] == 1
    assert "content" not in encoded

    markdown = format_trace_markdown(envelope)
    assert "# Retrieval Trace" in markdown
    assert "## Query Understanding" in markdown
    assert "## Source Counts" in markdown
    assert "## Stages" in markdown
    assert "## Final Selections" in markdown
    assert "semantic_recall" in markdown
    assert "src/AuditStatus.java" in markdown
    assert "Origin chunks: chunk-audit" in markdown
    assert "SOURCE_CONTENT_SENTINEL" not in markdown


def test_trace_markdown_rejects_malformed_envelope_without_leaking_details() -> None:
    malformed = trace_payload(Path("/repo"), "audit", _trace())
    malformed["trace"]["source_counts"]["content"] = (
        "SOURCE_CONTENT_SENTINEL"
    )
    with pytest.raises(
        TraceFormatError,
        match="Retrieval trace formatting failed",
    ) as raised:
        format_trace_markdown(malformed)
    assert "SOURCE_CONTENT_SENTINEL" not in str(raised.value)
~~~

- [ ] **Step 2: Run formatter tests and verify imports fail**

Run:

~~~bash
PYTHONPATH="$PWD/src" conda run -n base python -m pytest \
  tests/test_formatters.py -q
~~~

Expected: failures report missing trace formatter symbols.

- [ ] **Step 3: Add the shared success envelope and JSON formatter**

Import RetrievalTrace, RetrievalTraceError, SOURCE_COUNT_KEYS, and
retrieval_trace_payload, then add:

~~~python
from context_search_tool.retrieval_trace import (
    RetrievalTrace,
    RetrievalTraceError,
    SOURCE_COUNT_KEYS,
    retrieval_trace_payload,
)


class TraceFormatError(RetrievalTraceError):
    pass


def trace_payload(
    repo: Path,
    query: str,
    trace: RetrievalTrace,
) -> dict[str, Any]:
    return {
        "ok": True,
        "repo": str(repo.resolve()),
        "query": query,
        "trace": retrieval_trace_payload(trace),
    }


def format_trace_json(envelope: dict[str, Any]) -> str:
    try:
        return json.dumps(
            envelope,
            ensure_ascii=True,
            indent=2,
            sort_keys=False,
            allow_nan=False,
        )
    except Exception as exc:
        raise TraceFormatError("Retrieval trace formatting failed") from exc
~~~

Remove trace_payload from retrieval_trace/serialization.py so there is one shared
envelope owner, matching the existing ContextPack pattern. Keep only
retrieval_trace_payload in serialization. Remove trace_payload from the
retrieval_trace package exports and from tests/test_retrieval_trace.py; delete the
four-key envelope assertion there because tests/test_formatters.py now owns it.

- [ ] **Step 4: Add bounded Markdown rendering**

Add exact key constants, validation, and rendering:

~~~python
_TRACE_KEYS = {
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
}
_TRACE_LIMIT_KEYS = {
    "max_stages",
    "stage_top_k",
    "final_selection_top_k",
    "adjustment_top_k",
}
_TRACE_QUERY_KEYS = {
    "original_token_count",
    "expanded_token_count",
    "variant_retrieval_status",
    "variants",
    "planner",
}
_TRACE_VARIANT_KEYS = {"variant_id", "text", "source"}
_TRACE_PLANNER_KEYS = {
    "status",
    "provider",
    "model",
    "intent",
    "latency_ms",
    "discarded_hint_count",
}
_TRACE_DECISION_KEYS = (
    "selected_result",
    "selected_anchor",
    "duplicate_anchor",
    "result_limit",
    "anchor_limit",
)
_TRACE_STAGE_KEYS = {
    "name",
    "input_count",
    "output_count",
    "unique_output_count",
    "duration_ms",
    "source_counts",
    "decision_counts",
    "top_candidates",
}
_TRACE_CANDIDATE_KEYS = {
    "rank",
    "chunk_id",
    "file_path",
    "start_line",
    "end_line",
    "score",
    "sources",
    "variant_ids",
}
_TRACE_SELECTION_KEYS = {
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
}


def _validated_trace(envelope: dict[str, Any]) -> dict[str, Any]:
    if type(envelope) is not dict or set(envelope) != {
        "ok",
        "repo",
        "query",
        "trace",
    }:
        raise ValueError("invalid trace envelope")
    trace = envelope["trace"]
    if type(trace) is not dict or set(trace) != _TRACE_KEYS:
        raise ValueError("invalid trace payload")
    if trace["schema_version"] != 1:
        raise ValueError("invalid trace schema")
    if (
        type(trace["limits"]) is not dict
        or set(trace["limits"]) != _TRACE_LIMIT_KEYS
    ):
        raise ValueError("invalid trace limits")
    query = trace["query"]
    if type(query) is not dict or set(query) != _TRACE_QUERY_KEYS:
        raise ValueError("invalid trace query")
    if type(query["variants"]) is not list or any(
        type(item) is not dict or set(item) != _TRACE_VARIANT_KEYS
        for item in query["variants"]
    ):
        raise ValueError("invalid trace variants")
    if (
        type(query["planner"]) is not dict
        or set(query["planner"]) != _TRACE_PLANNER_KEYS
    ):
        raise ValueError("invalid trace planner")
    if (
        type(trace["source_counts"]) is not dict
        or tuple(trace["source_counts"]) != SOURCE_COUNT_KEYS
    ):
        raise ValueError("invalid trace source counts")
    if type(trace["stages"]) is not list:
        raise ValueError("invalid trace stages")
    for stage in trace["stages"]:
        if type(stage) is not dict or set(stage) != _TRACE_STAGE_KEYS:
            raise ValueError("invalid trace stage")
        if (
            type(stage["source_counts"]) is not dict
            or type(stage["decision_counts"]) is not dict
            or type(stage["top_candidates"]) is not list
        ):
            raise ValueError("invalid trace stage details")
        stage_source_keys = tuple(stage["source_counts"])
        if stage_source_keys != tuple(
            key for key in SOURCE_COUNT_KEYS if key in stage["source_counts"]
        ):
            raise ValueError("invalid trace stage source counts")
        if tuple(stage["decision_counts"]) not in (
            (),
            _TRACE_DECISION_KEYS,
        ):
            raise ValueError("invalid trace decision counts")
        for candidate in stage["top_candidates"]:
            if (
                type(candidate) is not dict
                or set(candidate) != _TRACE_CANDIDATE_KEYS
            ):
                raise ValueError("invalid trace candidate")
    if type(trace["final_selections"]) is not list:
        raise ValueError("invalid trace selections")
    for selection in trace["final_selections"]:
        if type(selection) is not dict or set(selection) != _TRACE_SELECTION_KEYS:
            raise ValueError("invalid trace selection")
        if any(
            type(item) is not dict or set(item) != {"stage", "rank", "score"}
            for item in selection["rank_history"]
        ):
            raise ValueError("invalid trace rank history")
        if any(
            type(item) is not dict or set(item) != {"name", "value"}
            for item in selection["adjustments"]
        ):
            raise ValueError("invalid trace adjustments")
    json.dumps(trace, allow_nan=False)
    return trace


def format_trace_markdown(envelope: dict[str, Any]) -> str:
    try:
        trace = _validated_trace(envelope)
        query = trace["query"]
        planner = query["planner"]
        lines = [
            "# Retrieval Trace",
            "",
            f"Repository: {envelope['repo']}",
            f"Query: {envelope['query']}",
            f"Outcome: {trace['outcome']}",
            f"Termination: {trace['termination_reason']}",
            f"Duration: {trace['duration_ms']} ms",
            "",
            "## Query Understanding",
            "",
            (
                "Tokens: "
                f"{query['original_token_count']} original, "
                f"{query['expanded_token_count']} expanded"
            ),
            f"Variant retrieval: {query['variant_retrieval_status']}",
            (
                "Planner: "
                f"status={planner['status']}; "
                f"provider={planner['provider'] or '(none)'}; "
                f"model={planner['model'] or '(none)'}; "
                f"intent={planner['intent']}; "
                f"latency_ms={planner['latency_ms']}"
            ),
            "Variants:",
        ]
        lines.extend(
            (
                f"- {variant['variant_id']} ({variant['source']}): "
                f"{variant['text']}"
            )
            for variant in query["variants"]
        )
        lines.extend(
            [
                "",
                "## Source Counts",
                "",
            ]
        )
        lines.extend(
            f"- {name}: {count}"
            for name, count in trace["source_counts"].items()
        )
        lines.extend(
            [
                "",
                "## Stages",
                "",
                "| stage | input | output | unique | duration ms |",
                "| --- | ---: | ---: | ---: | ---: |",
            ]
        )
        for stage in trace["stages"]:
            lines.append(
                f"| {stage['name']} | {stage['input_count']} | "
                f"{stage['output_count']} | {stage['unique_output_count']} | "
                f"{stage['duration_ms']} |"
            )
        for stage in trace["stages"]:
            lines.extend(["", f"### {stage['name']}"])
            source_counts = ", ".join(
                f"{name}={count}"
                for name, count in stage["source_counts"].items()
            )
            decision_counts = ", ".join(
                f"{name}={count}"
                for name, count in stage["decision_counts"].items()
            )
            lines.append(f"- Source counts: {source_counts or '(none)'}")
            lines.append(f"- Decisions: {decision_counts or '(none)'}")
            for candidate in stage["top_candidates"]:
                sources = ", ".join(candidate["sources"]) or "(none)"
                variants = ", ".join(candidate["variant_ids"]) or "(none)"
                lines.append(
                    f"- {candidate['rank']}. {candidate['file_path']}:"
                    f"{candidate['start_line']}-{candidate['end_line']}; "
                    f"score={candidate['score']}; sources={sources}; "
                    f"variants={variants}"
                )
        lines.extend(
            [
                "",
                "## Final Selections",
                "",
                f"Selected: {trace['final_selection_count']}",
                f"Omitted from preview: {trace['final_selection_omitted_count']}",
            ]
        )
        for selection in trace["final_selections"]:
            lines.extend(
                [
                    "",
                    (
                        f"### {selection['rank']}. {selection['file_path']}:"
                        f"{selection['start_line']}-{selection['end_line']}"
                    ),
                    f"- Kind: {selection['selection_kind']}",
                    f"- Selection: {selection['selection_reason']}",
                    f"- Score: {selection['score']}",
                    (
                        "- Origin chunks: "
                        + ", ".join(selection["origin_chunk_ids"])
                    ),
                    f"- Sources: {', '.join(selection['sources'])}",
                    f"- Variants: {', '.join(selection['variant_ids']) or '(none)'}",
                    "- Rank history: "
                    + ", ".join(
                        f"{item['stage']}#{item['rank']}={item['score']}"
                        for item in selection["rank_history"]
                    ),
                    (
                        "- Adjustments omitted from preview: "
                        f"{selection['adjustment_omitted_count']}"
                    ),
                    "- Adjustments: "
                    + (
                        ", ".join(
                            f"{item['name']}={item['value']}"
                            for item in selection["adjustments"]
                        )
                        or "(none)"
                    ),
                    "- Reasons: " + (", ".join(selection["reasons"]) or "(none)"),
                ]
            )
        return "\n".join(lines) + "\n"
    except TraceFormatError:
        raise
    except Exception as exc:
        raise TraceFormatError("Retrieval trace formatting failed") from exc
~~~

Exact envelope, limit, query, planner, variant, stage, candidate, selection,
rank, and adjustment key checks prevent a source content field from entering
Markdown.

- [ ] **Step 5: Run formatter, context, and raw-query compatibility tests**

Run:

~~~bash
PYTHONPATH="$PWD/src" conda run -n base python -m pytest \
  tests/test_retrieval_trace.py \
  tests/test_formatters.py \
  tests/test_context_pack.py \
  tests/test_mcp_tools.py \
  -q
~~~

Expected: all tests pass and existing query/context formatter snapshots are
unchanged.

- [ ] **Step 6: Commit formatters**

~~~bash
git add \
  src/context_search_tool/formatters.py \
  src/context_search_tool/retrieval_trace/serialization.py \
  tests/test_formatters.py \
  tests/test_retrieval_trace.py
git commit -m "feat: format retrieval trace output"
~~~

### Task 7: Expose The Additive CLI Trace Command

**Files:**

- Modify: src/context_search_tool/cli.py
- Modify: tests/test_cli_commands.py
- Modify: tests/test_cli_import.py

- [ ] **Step 1: Write failing CLI JSON, Markdown, option, and error tests**

Import RetrievalTraceError from context_search_tool.retrieval_trace, then add to
tests/test_cli_commands.py:

~~~python
def test_cli_trace_returns_schema_v1_without_changing_query_output(
    tmp_path: Path,
) -> None:
    repo, runner = _indexed_repo(tmp_path)
    raw_before = runner.invoke(
        app,
        ["query", str(repo), "AppController", "--json"],
    )
    traced = runner.invoke(
        app,
        ["trace", str(repo), "AppController", "--json"],
    )
    raw_after = runner.invoke(
        app,
        ["query", str(repo), "AppController", "--json"],
    )

    assert traced.exit_code == 0
    payload = json.loads(traced.output)
    assert tuple(payload) == ("ok", "repo", "query", "trace")
    assert payload["trace"]["schema_version"] == 1
    assert "content" not in json.dumps(payload["trace"])
    assert json.loads(raw_after.output) == json.loads(raw_before.output)


def test_cli_trace_markdown_and_planner_flags_match_query(
    tmp_path: Path,
) -> None:
    repo, runner = _indexed_repo(tmp_path)
    result = runner.invoke(app, ["trace", str(repo), "AppController"])
    assert result.exit_code == 0
    assert "# Retrieval Trace" in result.output

    invalid = runner.invoke(
        app,
        [
            "trace",
            str(repo),
            "AppController",
            "--planner",
            "--no-planner",
        ],
    )
    assert invalid.exit_code != 0
    assert "cannot be used together" in invalid.output


@pytest.mark.parametrize(
    "error",
    [
        RetrievalTraceError("PRIVATE_TRACE_CONTRACT"),
        RuntimeError("PRIVATE_TRACE_INTERNAL"),
    ],
)
def test_cli_trace_hides_trace_and_unexpected_internal_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
) -> None:
    repo, runner = _indexed_repo(tmp_path)

    def fail(*args, **kwargs):
        raise error

    monkeypatch.setattr(cli, "trace_repository", fail)
    result = runner.invoke(app, ["trace", str(repo), "AppController"])

    assert result.exit_code != 0
    assert "Retrieval trace failed" in result.output
    assert "PRIVATE_TRACE" not in result.output
~~~

Add to tests/test_cli_import.py:

~~~python
from context_search_tool import cli


def test_cli_exports_trace_command_and_runner() -> None:
    assert callable(cli.trace)
    assert callable(cli.trace_repository)
    result = CliRunner().invoke(app, ["--help"])
    assert "trace" in result.output
~~~

- [ ] **Step 2: Run CLI tests and verify the command is absent**

Run:

~~~bash
PYTHONPATH="$PWD/src" conda run -n base python -m pytest \
  tests/test_cli_commands.py \
  tests/test_cli_import.py \
  -q
~~~

Expected: trace command tests fail with unknown command or missing import.

- [ ] **Step 3: Add imports and the command using existing query preparation**

Import RetrievalTraceError, format_trace_json, format_trace_markdown,
trace_payload, and trace_repository. Add:

~~~python
from context_search_tool.formatters import (
    format_trace_json,
    format_trace_markdown,
    trace_payload,
)
from context_search_tool.retrieval import trace_repository
from context_search_tool.retrieval_trace import RetrievalTraceError


@app.command()
def trace(
    repo_or_question: str,
    question: Optional[str] = typer.Argument(None),
    json_output: bool = typer.Option(False, "--json", help="Output JSON."),
    context_lines: Optional[int] = typer.Option(
        None,
        "--context-lines",
        help="Override context lines around each result.",
    ),
    full_file: bool = typer.Option(
        False,
        "--full-file",
        help="Trace full-file result expansion when configured limits allow it.",
    ),
    planner: bool = typer.Option(False, "--planner", help="Force query planner on."),
    no_planner: bool = typer.Option(
        False,
        "--no-planner",
        help="Force query planner off.",
    ),
) -> None:
    repo, query_text, config = _prepare_query_command(
        repo_or_question,
        question,
        planner=planner,
        no_planner=no_planner,
    )
    try:
        traced = trace_repository(
            repo,
            query_text,
            config,
            context_lines=context_lines,
            full_file=full_file,
        )
        envelope = trace_payload(repo, query_text, traced.trace)
        output = (
            format_trace_json(envelope)
            if json_output
            else format_trace_markdown(envelope)
        )
    except RetrievalTraceError:
        typer.echo("Retrieval trace failed", err=True)
        raise typer.Exit(code=1)
    except (ValueError, requests.HTTPError) as exc:
        _exit_with_error(exc)
    except Exception:
        typer.echo("Retrieval trace failed", err=True)
        raise typer.Exit(code=1)
    typer.echo(output)
~~~

Do not call query_repository separately and do not modify query or context.

- [ ] **Step 4: Run CLI and parity tests**

Run:

~~~bash
PYTHONPATH="$PWD/src" conda run -n base python -m pytest \
  tests/test_cli_commands.py \
  tests/test_cli_import.py \
  tests/test_retrieval_trace_pipeline.py \
  -q
~~~

Expected: all tests pass.

- [ ] **Step 5: Commit the CLI surface**

~~~bash
git add \
  src/context_search_tool/cli.py \
  tests/test_cli_commands.py \
  tests/test_cli_import.py
git commit -m "feat: add retrieval trace cli command"
~~~

### Task 8: Expose The MCP Trace Tool Without Feedback Persistence

**Files:**

- Modify: src/context_search_tool/mcp_tools.py
- Modify: src/context_search_tool/mcp_server.py
- Modify: tests/test_mcp_tools.py
- Modify: tests/test_mcp_server.py

- [ ] **Step 1: Write failing MCP success, one-pass, error, and privacy tests**

Import context_search_trace_tool and RetrievalTraceError in
tests/test_mcp_tools.py, then add:

~~~python
def test_mcp_trace_returns_shared_schema_without_source_content(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    _write_java_repo(repo)
    assert context_search_index_tool(str(repo))["ok"] is True

    payload = context_search_trace_tool(
        repo=str(repo),
        query="/apply/audit/pageEs",
        context_lines=0,
        full_file=False,
        final_top_k=1,
    )

    assert tuple(payload) == ("ok", "repo", "query", "trace")
    assert payload["ok"] is True
    assert payload["trace"]["schema_version"] == 1
    assert payload["trace"]["final_selection_count"] >= 1
    assert "content" not in json.dumps(payload["trace"])


def test_mcp_trace_executes_one_retrieval_pass(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    _write_java_repo(repo)
    assert context_search_index_tool(str(repo))["ok"] is True
    calls = 0
    original = mcp_tools.trace_repository

    def counted(*args, **kwargs):
        nonlocal calls
        calls += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(mcp_tools, "trace_repository", counted)
    result = context_search_trace_tool(
        repo=str(repo),
        query="audit",
    )

    assert result["ok"] is True
    assert calls == 1


def test_mcp_trace_never_creates_or_modifies_feedback_log(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    _write_java_repo(repo)
    assert context_search_index_tool(str(repo))["ok"] is True
    log_path = repo / ".context-search" / "mcp_calls.jsonl"
    log_path.write_text("PREEXISTING_FEEDBACK\n", encoding="utf-8")

    payload = context_search_trace_tool(
        repo=str(repo),
        query="TRACE_QUERY_SECRET",
    )

    assert payload["ok"] is True
    assert log_path.read_text(encoding="utf-8") == "PREEXISTING_FEEDBACK\n"


@pytest.mark.parametrize(
    "error",
    [
        RetrievalTraceError("PRIVATE_TRACE_CONTRACT"),
        RuntimeError("PRIVATE_TRACE_INTERNAL"),
    ],
)
def test_mcp_trace_hides_trace_and_unexpected_internal_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
) -> None:
    repo = tmp_path / "repo"
    _write_index_marker(repo)

    def fail(*args, **kwargs):
        raise error

    monkeypatch.setattr(mcp_tools, "trace_repository", fail)
    payload = context_search_trace_tool(repo=str(repo), query="audit")

    assert payload == {
        "ok": False,
        "error": {
            "code": "trace_failed",
            "message": "Retrieval trace failed",
        },
    }
    assert "PRIVATE_TRACE" not in repr(payload)
~~~

Extend tests/test_mcp_server.py:

~~~python
def test_trace_tool_matches_query_arguments_exactly() -> None:
    from context_search_tool import mcp_server

    query_parameters = inspect.signature(
        mcp_server.context_search_query
    ).parameters
    trace_parameters = inspect.signature(
        mcp_server.context_search_trace
    ).parameters
    assert tuple(trace_parameters) == tuple(query_parameters)
    assert "retrieval diagnostics" in (
        mcp_server.context_search_trace.__doc__ or ""
    ).lower()
~~~

- [ ] **Step 2: Run MCP tests and verify the tool is missing**

Run:

~~~bash
PYTHONPATH="$PWD/src" conda run -n base python -m pytest \
  tests/test_mcp_tools.py \
  tests/test_mcp_server.py \
  -q
~~~

Expected: collection fails on context_search_trace_tool and server registration.

- [ ] **Step 3: Implement the MCP tool with existing preflight semantics**

Import RetrievalTraceError, trace_payload, and trace_repository in mcp_tools.py.
Add next to the query and context tools:

~~~python
from context_search_tool.formatters import trace_payload
from context_search_tool.retrieval import trace_repository
from context_search_tool.retrieval_trace import RetrievalTraceError


def context_search_trace_tool(
    repo: str,
    query: str,
    context_lines: int | None = None,
    full_file: bool = False,
    final_top_k: int | None = None,
) -> dict[str, Any]:
    try:
        resolved_repo = find_repo_root(Path(repo))
    except RepositoryNotFoundError as exc:
        return _error("repo_not_found", str(exc))

    index_dir = index_dir_for(resolved_repo)
    if not (index_dir / "index.sqlite").exists():
        return _error(
            "missing_index",
            f"Missing index for {resolved_repo}. Run context_search_index first.",
        )

    try:
        config = _load_query_config(resolved_repo, final_top_k)
        traced = trace_repository(
            resolved_repo,
            query,
            config,
            context_lines=context_lines,
            full_file=full_file,
        )
        return trace_payload(resolved_repo, query, traced.trace)
    except RetrievalTraceError:
        return _error("trace_failed", "Retrieval trace failed")
    except (ValueError, requests.HTTPError) as exc:
        return _error("query_failed", str(exc))
    except Exception:
        return _error("trace_failed", "Retrieval trace failed")
~~~

There is intentionally no call to _try_append_query_feedback in any branch. Do
not add context_search_trace to the generic non-context branch in
_append_query_feedback; the trace tool never invokes that function.

- [ ] **Step 4: Register the exact FastMCP operation**

Import context_search_trace_tool in mcp_server.py and add:

~~~python
from context_search_tool.mcp_tools import context_search_trace_tool


@mcp.tool()
def context_search_trace(
    repo: str,
    query: str,
    context_lines: int | None = None,
    full_file: bool = False,
    final_top_k: int | None = None,
) -> dict[str, Any]:
    """Return bounded retrieval diagnostics without source content."""
    return context_search_trace_tool(
        repo=repo,
        query=query,
        context_lines=context_lines,
        full_file=full_file,
        final_top_k=final_top_k,
    )
~~~

- [ ] **Step 5: Add a CLI/MCP envelope identity test**

Import TracedQueryBundle, RetrievalTraceCollector, and TraceQuery, then add to
tests/test_mcp_tools.py:

~~~python
def test_cli_and_mcp_trace_success_envelopes_are_identical(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    _write_index_marker(repo)
    ticks = iter((0, 1_000_000))
    collector = RetrievalTraceCollector(clock_ns=lambda: next(ticks))
    collector.record_query(
        TraceQuery(
            original_token_count=1,
            expanded_token_count=1,
            variant_retrieval_status="original_only",
        )
    )
    trace = collector.finish(
        outcome="empty",
        termination_reason="no_candidates",
        final_selections=(),
    )
    traced = TracedQueryBundle(
        bundle=_deterministic_bundle(query="audit"),
        trace=trace,
    )
    monkeypatch.setattr(cli, "trace_repository", lambda *args, **kwargs: traced)
    monkeypatch.setattr(
        mcp_tools,
        "trace_repository",
        lambda *args, **kwargs: traced,
    )

    cli_result = CliRunner().invoke(
        app,
        ["trace", str(repo), "audit", "--json"],
    )
    mcp_result = context_search_trace_tool(repo=str(repo), query="audit")

    assert cli_result.exit_code == 0
    assert json.loads(cli_result.output) == mcp_result
~~~

This protects one shared schema owner and catches MCP-only metadata drift.

- [ ] **Step 6: Run all public-surface and feedback tests**

Run:

~~~bash
PYTHONPATH="$PWD/src" conda run -n base python -m pytest \
  tests/test_cli_commands.py \
  tests/test_mcp_tools.py \
  tests/test_mcp_server.py \
  tests/test_quality_feedback.py \
  tests/test_formatters.py \
  -q
~~~

Expected: all tests pass. Verify that the trace privacy test leaves the feedback
sentinel byte-for-byte unchanged.

- [ ] **Step 7: Commit the MCP surface**

~~~bash
git add \
  src/context_search_tool/mcp_tools.py \
  src/context_search_tool/mcp_server.py \
  tests/test_mcp_tools.py \
  tests/test_mcp_server.py
git commit -m "feat: expose retrieval trace mcp tool"
~~~

### Task 9: Add Deterministic TraceCoverage Acceptance And Documentation

**Files:**

- Create: tests/test_quality_p3.py
- Modify: README.md
- Modify: docs/retrieval-quality.md

- [ ] **Step 1: Write the failing offline TraceCoverage acceptance test**

Create tests/test_quality_p3.py:

~~~python
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from context_search_tool.config import RetrievalConfig, ToolConfig
from context_search_tool.formatters import query_payload
from context_search_tool.indexer import index_repository
from context_search_tool.retrieval import query_repository, trace_repository
from context_search_tool.retrieval_trace import CANONICAL_TRACE_STAGES

FIXTURES = Path(__file__).parent / "fixtures"

CASES = (
    (
        "java",
        FIXTURES / "context-pack-java",
        "workspace page flow controller service dto",
    ),
    (
        "frontend",
        FIXTURES / "real_projects" / "program_tool",
        "QRCode page route service type",
    ),
    (
        "docs",
        FIXTURES / "context-pack-docs",
        "Program Tool Developer Setup documentation",
    ),
)


@pytest.mark.parametrize(("name", "source", "query"), CASES)
def test_p3_trace_coverage_is_complete_and_raw_results_are_unchanged(
    tmp_path: Path,
    name: str,
    source: Path,
    query: str,
) -> None:
    repo = tmp_path / name
    shutil.copytree(source, repo)
    config = ToolConfig(
        retrieval=RetrievalConfig(
            semantic_top_k=24,
            lexical_top_k=24,
            final_top_k=8,
            context_before_lines=2,
            context_after_lines=2,
        )
    )
    index_repository(repo, config)

    plain = query_repository(repo, query, config)
    traced = trace_repository(repo, query, config)

    assert query_payload(traced.bundle) == query_payload(plain)
    assert traced.trace.outcome == "complete"
    assert [stage.name for stage in traced.trace.stages] == list(
        CANONICAL_TRACE_STAGES
    )
    assert traced.trace.final_selections
    covered = sum(
        bool(
            selection.sources
            and selection.rank_history
            and selection.selection_reason
        )
        for selection in traced.trace.final_selections
    )
    assert covered / len(traced.trace.final_selections) == 1.0
    assert traced.trace.final_selection_count == (
        len(traced.bundle.results) + len(traced.bundle.evidence_anchors)
    )
~~~

- [ ] **Step 2: Run the acceptance test and diagnose only real contract gaps**

Run:

~~~bash
PYTHONPATH="$PWD/src" conda run -n base python -m pytest \
  tests/test_quality_p3.py -q
~~~

Expected: the three representative existing P2 queries—one per Java, frontend,
and documentation fixture family—pass without weakening the non-empty or
TraceCoverage assertions.

- [ ] **Step 3: Add README operation and schema guidance**

Document:

~~~bash
cst trace /path/to/repo "owner registration validation"
cst trace /path/to/repo "数据看板统计图表功能" --planner --json
~~~

Add context_search_trace(repo, query, context_lines, full_file, final_top_k) to the
MCP list and add this text:

~~~markdown
Retrieval trace is an explicitly requested diagnostic surface. It runs the same
existing retrieval pipeline once and returns schema version 1 without source
content. Each stage previews at most five candidates and the final-selection
preview contains at most twenty entries while full counts remain visible.

Trace responses are request-local: CST does not persist them or append them to MCP
feedback. Existing query and ContextPack response contracts remain unchanged.
~~~

- [ ] **Step 4: Add the P3.1 quality section**

Append a Phase 3.1 Retrieval Trace Acceptance section to
docs/retrieval-quality.md with:

~~~bash
PYTHONPATH="$PWD/src" conda run -n base python -m pytest \
  tests/test_retrieval_trace.py \
  tests/test_retrieval_trace_pipeline.py \
  tests/test_quality_p3.py \
  tests/test_cli_commands.py \
  tests/test_mcp_tools.py \
  tests/test_mcp_server.py \
  -q
~~~

Follow the command with:

~~~markdown
TraceCoverage is the number of serialized final selections with non-empty source
provenance, rank history, and a selection reason divided by all serialized final
selections. Every non-empty committed P3.1 case requires TraceCoverage 1.0.

Stage and selection counts describe uncapped work, not preview length. Timings are
informational in end-to-end tests; collector unit tests use an injected clock. P3.1
does not add a quality-catalog mode. Phase 1 model acceptance remains independent
and pending until its own required 7/7 gate passes.
~~~

- [ ] **Step 5: Run documentation-linked focused tests and check commands**

Run the exact documented command, then:

~~~bash
rg -n \
  "cst trace|context_search_trace|schema version 1|TraceCoverage|feedback" \
  README.md \
  docs/retrieval-quality.md
git diff --check
~~~

Expected: focused tests pass, each documented concept has a match, and diff check
prints nothing.

- [ ] **Step 6: Commit deterministic acceptance and operational docs**

~~~bash
git add \
  tests/test_quality_p3.py \
  README.md \
  docs/retrieval-quality.md
git commit -m "test: add retrieval trace acceptance"
~~~

### Task 10: Verify Compatibility And Close P3.1 Conditionally

**Files:**

- Modify after all gates pass: roadmap/2026-07-08-fast-context-like-retrieval-roadmap.md
- Modify after implementation review: docs/superpowers/specs/2026-07-16-p3-1-retrieval-trace-v1-design.md

- [ ] **Step 1: Run the complete test suite**

~~~bash
PYTHONPATH="$PWD/src" conda run -n base python -m pytest -q
~~~

Expected: every required test passes. Skips must be the same optional dependency
or explicitly guarded integration categories present at the baseline; inspect any
new skip before proceeding.

- [ ] **Step 2: Re-run P2 and raw-result deterministic profiles**

~~~bash
PYTHONPATH="$PWD/src" conda run -n base python -m context_search_tool.quality run \
  tests/fixtures/retrieval_quality/queries.json \
  --profile p2_context_pack \
  --output /tmp/cst-p3-1-p2.json \
  --markdown /tmp/cst-p3-1-p2.md

PYTHONPATH="$PWD/src" conda run -n base python -m context_search_tool.quality run \
  tests/fixtures/retrieval_quality/queries.json \
  --profile ci \
  --output /tmp/cst-p3-1-ci.json \
  --markdown /tmp/cst-p3-1-ci.md

jq '{
  profile,
  selected: .aggregate.selected,
  executed: .aggregate.executed,
  passed: .aggregate.passed,
  failed: .aggregate.failed,
  errors: .aggregate.errors
}' /tmp/cst-p3-1-p2.json /tmp/cst-p3-1-ci.json
~~~

Expected:

- p2_context_pack: selected/executed/passed 5/5/5, failed 0, errors 0;
- ci: selected/executed/passed 8/8/8, failed 0, errors 0.

- [ ] **Step 3: Prove raw query and ContextPack contracts did not gain trace fields**

~~~bash
rg -n '"trace"|RetrievalTrace' \
  src/context_search_tool/formatters.py \
  src/context_search_tool/context_pack \
  src/context_search_tool/quality
~~~

Inspect each match. Allowed matches in formatters.py must belong only to the new
trace functions. There must be no match in context_pack or the quality runner
implementation.

Run:

~~~bash
PYTHONPATH="$PWD/src" conda run -n base python -m pytest \
  tests/test_formatters.py::test_query_payload_matches_the_complete_raw_query_payload \
  tests/test_mcp_tools.py::test_mcp_raw_payload_ignores_private_exact_context_content \
  tests/test_context_pack.py \
  -q
~~~

- [ ] **Step 4: Prove trace data is not persisted**

~~~bash
rg -n \
  "context_search_trace|RetrievalTrace|trace_payload" \
  src/context_search_tool/mcp_tools.py \
  src/context_search_tool/quality \
  tests/test_mcp_tools.py
~~~

Inspect the trace tool call chain. It must have no path to
_try_append_query_feedback, _append_query_feedback, a trace file, or a quality
report field.

- [ ] **Step 5: Exercise both public surfaces manually**

Create a temporary fixture checkout under /tmp, index it, and run:

~~~bash
rm -rf /tmp/cst-p3-1-manual
cp -R tests/fixtures/java-spring-mini /tmp/cst-p3-1-manual
PYTHONPATH="$PWD/src" conda run -n base python -m context_search_tool.cli \
  index /tmp/cst-p3-1-manual

PYTHONPATH="$PWD/src" conda run -n base python -m context_search_tool.cli \
  trace /tmp/cst-p3-1-manual "audit status" --json \
  > /tmp/cst-p3-1-trace.json

jq '{
  ok,
  schema: .trace.schema_version,
  outcome: .trace.outcome,
  stages: [.trace.stages[].name],
  final_selection_count: .trace.final_selection_count
}' /tmp/cst-p3-1-trace.json
~~~

Call the MCP helper against the same repository. Normalize only request and
stage duration values, which legitimately differ across two live executions;
keep every field present and compare the remaining payload exactly:

~~~bash
PYTHONPATH="$PWD/src" conda run -n base python - <<'PY' \
  > /tmp/cst-p3-1-mcp-trace.json
import json
from context_search_tool.mcp_tools import context_search_trace_tool

payload = context_search_trace_tool(
    repo="/tmp/cst-p3-1-manual",
    query="audit status",
)
print(json.dumps(payload, ensure_ascii=True, sort_keys=True))
PY

jq '(.trace.duration_ms = 0) | (.trace.stages |= map(.duration_ms = 0))' \
  /tmp/cst-p3-1-trace.json \
  > /tmp/cst-p3-1-trace-normalized.json
jq '(.trace.duration_ms = 0) | (.trace.stages |= map(.duration_ms = 0))' \
  /tmp/cst-p3-1-mcp-trace.json \
  > /tmp/cst-p3-1-mcp-trace-normalized.json

diff \
  <(jq -S . /tmp/cst-p3-1-trace-normalized.json) \
  <(jq -S . /tmp/cst-p3-1-mcp-trace-normalized.json)
~~~

Expected: diff prints nothing.

- [ ] **Step 6: Run final bounds, privacy, and repository-hygiene checks**

~~~bash
git diff --check
git status --short
rg -n 'TB[D]|TO[D]O|FIXM[E]|XX[X]|implement[[:space:]]+later|fill[[:space:]]+in[[:space:]]+details' \
  src/context_search_tool/retrieval_trace \
  tests/test_retrieval_trace.py \
  tests/test_retrieval_trace_pipeline.py \
  tests/test_quality_p3.py \
  README.md \
  docs/retrieval-quality.md
rg -n \
  "multi-round|graph traversal|watch mode|trace database|trace history" \
  src/context_search_tool \
  tests
~~~

Expected:

- git diff check is empty;
- no placeholders exist;
- no P3.2, P4, or trace-persistence implementation was added;
- only planned files changed;
- generated /tmp reports are untracked.

- [ ] **Step 7: Update written evidence and roadmap only after Steps 1-6 pass**

Update the spec header to:

~~~text
Status: Approved; written review complete; implementation verified
~~~

Under the roadmap P3.1 item record:

- completion date;
- exact implementation commit;
- full-suite pass/skip counts;
- focused P3.1 case count and TraceCoverage 1.0;
- P2 5/5 and CI 8/8 report names/counts;
- statement that P1 remains pending at its independent 6/7 baseline unless a
  separately reviewed P1 change has genuinely closed it;
- next-stage review: P3.2 retrieval-core decomposition design.

Do not mark Phase 3 as a whole complete.

- [ ] **Step 8: Commit verification documentation**

~~~bash
git add \
  docs/superpowers/specs/2026-07-16-p3-1-retrieval-trace-v1-design.md \
  roadmap/2026-07-08-fast-context-like-retrieval-roadmap.md
git commit -m "docs: verify retrieval trace v1"
~~~

- [ ] **Step 9: Confirm the final branch is clean and review commit scope**

~~~bash
git status --short
git log --oneline --decorate -12
git diff --stat be03fa73437cd897d112377d80dda5c83370def5..HEAD
~~~

Expected: status is empty, commits follow the task boundaries above, and every
changed line maps to the approved P3.1 spec.

## Final Verification Matrix

| requirement | focused proof | acceptance proof |
| --- | --- | --- |
| Exact schema version 1 | test_retrieval_trace.py exact-key tests | CLI/MCP envelope identity |
| Fixed stages and source counts | collector order/source unit tests | three offline quality cases |
| Bounded previews and adjustments | collector/model boundary tests | serialized count/omission checks |
| Candidate provenance | planner/original/relation focused tests | TraceCoverage 1.0 |
| Rank movement and adjustments | ranking/cohort/ceiling tests | final selections all have history |
| Final selection reasons | limit/duplicate decision tests | exact result-plus-anchor counts |
| No source content | serializer/formatter sentinels | CLI/MCP payload scans |
| No implicit persistence | MCP feedback sentinel | call-chain grep and unchanged log |
| One retrieval pass | semantic-call counter | CLI/MCP integration |
| Raw query compatibility | complete payload equality | ci 8/8 |
| ContextPack compatibility | canonical byte equality | p2_context_pack 5/5 |
| Ordinary path has no trace work | forbidden-constructor/helper test | full-suite regression |
| P3.1/P3.2 scope | file/diff inspection | roadmap keeps Phase 3 open |

## Stop Point

This plan ends after RetrievalTrace v1, its request-local collector, existing
pipeline instrumentation, independent CLI/MCP operations, offline TraceCoverage
acceptance, documentation, and conditional P3.1 roadmap evidence are implemented
and verified.

Do not split retrieval.py, change ranking, close the independent Phase 1 gate,
persist traces, execute next queries, or begin controlled multi-round retrieval in
this plan.
