from __future__ import annotations

from dataclasses import asdict
import sqlite3
from pathlib import Path
from typing import Any

import numpy as np
import pytest

import context_search_tool.mcp_tools as mcp_tools
from context_search_tool import retrieval, sqlite_store
from context_search_tool.config import RetrievalConfig, ToolConfig
from context_search_tool.context_pack import (
    build_context_pack,
    canonical_context_pack_bytes,
    context_pack_payload,
    resolve_context_pack_options,
)
from context_search_tool.embeddings import HashEmbeddingProvider
from context_search_tool.formatters import format_json, format_markdown, query_payload
from context_search_tool.indexer import index_repository
from context_search_tool.models import (
    DocumentChunk,
    QueryPlan,
    QueryVariant,
    RetrievalCandidate,
    SemanticMatch,
)
from context_search_tool.retrieval_trace import (
    CANONICAL_TRACE_STAGES,
    RetrievalTraceCollector,
    TraceLimits,
)
from context_search_tool.retrieval_core import types as core_types
from context_search_tool.sqlite_store import SQLiteStore


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

    for name in (
        "RetrievalTraceCollector",
        "_trace_candidate_observations",
        "_trace_ranked_observations",
        "_trace_expanded_observations",
        "_trace_adjustments",
        "_trace_final_selections",
        "_trace_query",
        "_FinalTraceInput",
        "_FinalTraceDecisions",
    ):
        monkeypatch.setattr(retrieval, name, forbidden)

    assert retrieval.query_repository(repo, "audit", config).results


def test_trace_repository_reports_missing_index_without_changing_bundle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    config = ToolConfig()

    def forbidden(*args, **kwargs):
        raise AssertionError("missing-index retrieval crossed the preflight boundary")

    monkeypatch.setattr(retrieval, "planner_from_config", forbidden)
    monkeypatch.setattr(sqlite_store, "SQLiteStore", forbidden)
    monkeypatch.setattr(retrieval, "NumpyVectorStore", forbidden)
    monkeypatch.setattr(Path, "read_text", forbidden)
    original_stat = Path.stat
    stat_paths: list[Path] = []

    def preflight_stat(path: Path, *args, **kwargs):
        stat_paths.append(path)
        assert path == repo / ".context-search" / "index.sqlite"
        return original_stat(path, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", preflight_stat)
    expected = retrieval.QueryBundle(
        query="audit",
        expanded_tokens=["audit"],
        results=[],
        followup_keywords=[],
        planner=QueryPlan(original_query="audit"),
        query_variants=[QueryVariant("original", "audit", "original")],
    )
    plain = retrieval.query_repository(repo, "audit", config)
    traced = retrieval.trace_repository(repo, "audit", config)

    assert plain == expected
    assert traced.bundle == plain
    assert format_json(traced.bundle) == format_json(expected)
    assert format_markdown(traced.bundle) == format_markdown(expected)
    assert traced.trace.outcome == "empty"
    assert traced.trace.termination_reason == "missing_index"
    assert traced.trace.stages == ()
    assert stat_paths == [
        repo / ".context-search" / "index.sqlite",
        repo / ".context-search" / "index.sqlite",
    ]


def test_trace_repository_reports_store_read_error_before_stages(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, config = _indexed_repo(tmp_path)

    def fail_store_read(self):
        raise sqlite3.Error("PRIVATE_STORE_ERROR")

    def forbidden(*args, **kwargs):
        raise AssertionError("store-read early return crossed into planning")

    monkeypatch.setattr(sqlite_store.SQLiteStore, "deleted_chunk_ids", fail_store_read)
    monkeypatch.setattr(retrieval, "planner_from_config", forbidden)
    plain = retrieval.query_repository(repo, "audit", config)
    traced = retrieval.trace_repository(repo, "audit", config)

    assert traced.bundle == plain
    assert traced.bundle.results == []
    assert format_json(traced.bundle) == format_json(plain)
    assert format_markdown(traced.bundle) == format_markdown(plain)
    assert traced.trace.outcome == "partial"
    assert traced.trace.termination_reason == "store_read_error"
    assert traced.trace.stages == ()
    assert "PRIVATE_STORE_ERROR" not in repr(traced.trace)


def test_trace_repository_reports_no_candidates_after_candidate_merge(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, config = _indexed_repo(tmp_path)
    monkeypatch.setattr(retrieval, "_merge_candidates", lambda candidates: {})

    def forbidden(*args, **kwargs):
        raise AssertionError("no-candidate retrieval performed downstream work")

    monkeypatch.setattr(retrieval, "_rank_chunks", forbidden)
    monkeypatch.setattr(retrieval, "_expand_ranked_chunks", forbidden)
    monkeypatch.setattr(retrieval, "_summarize_results", forbidden)
    original_read_text = Path.read_text

    def forbid_source_read(path: Path, *args, **kwargs):
        if ".context-search" not in path.parts:
            forbidden()
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", forbid_source_read)

    traced = retrieval.trace_repository(repo, "audit", config)

    assert traced.bundle.results == []
    assert traced.trace.outcome == "empty"
    assert traced.trace.termination_reason == "no_candidates"
    assert [stage.name for stage in traced.trace.stages] == list(
        CANONICAL_TRACE_STAGES[:11]
    )
    assert format_json(traced.bundle) == format_json(
        retrieval.QueryBundle(
            query="audit",
            expanded_tokens=["audit"],
            results=[],
            followup_keywords=[],
            planner=QueryPlan(original_query="audit"),
            query_variants=[QueryVariant("original", "audit", "original")],
        )
    )
    assert format_markdown(traced.bundle) == format_markdown(
        retrieval.QueryBundle(
            query="audit",
            expanded_tokens=["audit"],
            results=[],
            followup_keywords=[],
            planner=QueryPlan(original_query="audit"),
            query_variants=[QueryVariant("original", "audit", "original")],
        )
    )


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
    item = core_types._ExpandedResult(
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
        FinalSelectionCollector(),  # type: ignore[arg-type]
    )[0]

    assert selection.origin_chunk_ids == ("chunk-a", "chunk-b")
    assert [(entry.stage, entry.rank) for entry in selection.rank_history] == [
        ("ranking", 2),
        ("cohort_rerank", 3),
        ("context_expansion", 2),
        ("final_selection", 1),
    ]
    adjustment_names = [entry.name for entry in selection.adjustments]
    assert adjustment_names == [
        "planner_ceiling_clamp",
        "role_boost",
        "test_penalty",
    ]
    assert "semantic" not in adjustment_names
    assert "combined_score" not in adjustment_names
    assert "SOURCE_CONTENT_SENTINEL" not in repr(selection)


@pytest.mark.parametrize("entrypoint", ["plain", "traced"])
def test_deleted_id_handler_does_not_catch_broader_exceptions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    entrypoint: str,
) -> None:
    repo, config = _indexed_repo(tmp_path)

    def fail(self):
        raise RuntimeError("BROAD_ERROR_SENTINEL")

    monkeypatch.setattr(sqlite_store.SQLiteStore, "deleted_chunk_ids", fail)
    target = (
        retrieval.query_repository
        if entrypoint == "plain"
        else retrieval.trace_repository
    )

    with pytest.raises(RuntimeError, match="BROAD_ERROR_SENTINEL"):
        target(repo, "audit", config)


@pytest.mark.parametrize("failure", ["manifest", "planner", "provider"])
def test_manifest_planner_and_provider_failures_propagate_without_partial_trace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    repo, config = _indexed_repo(tmp_path)

    class FailingPlanner:
        def plan(self, query: str, repo_profile=None) -> QueryPlan:
            raise ValueError("PLANNER_FAILURE_SENTINEL")

    class FailingProvider:
        def embed_texts(self, texts: list[str]) -> list[np.ndarray]:
            raise ValueError("PROVIDER_FAILURE_SENTINEL")

    if failure == "manifest":
        monkeypatch.setattr(
            retrieval,
            "assert_manifest_compatible",
            lambda *args, **kwargs: (_ for _ in ()).throw(
                ValueError("MANIFEST_FAILURE_SENTINEL")
            ),
        )
        expected = "MANIFEST_FAILURE_SENTINEL"
        kwargs = {}
    elif failure == "planner":
        expected = "PLANNER_FAILURE_SENTINEL"
        kwargs = {"planner": FailingPlanner()}
    else:
        monkeypatch.setattr(
            retrieval,
            "provider_from_config",
            lambda config: FailingProvider(),
        )
        expected = "PROVIDER_FAILURE_SENTINEL"
        kwargs = {}

    with pytest.raises(ValueError, match=expected):
        retrieval.trace_repository(repo, "audit", config, **kwargs)


def test_embedding_batches_are_single_primary_plus_only_existing_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, config = _indexed_repo(tmp_path)
    delegate = HashEmbeddingProvider(config.embedding)
    batches: list[list[str]] = []

    class FallbackProvider:
        def embed_texts(self, texts: list[str]) -> list[np.ndarray]:
            batches.append(list(texts))
            if len(batches) == 1:
                raise ValueError("primary batch failed")
            return delegate.embed_texts(texts)

    monkeypatch.setattr(
        retrieval,
        "provider_from_config",
        lambda embedding_config: FallbackProvider(),
    )
    traced = retrieval.trace_repository(
        repo,
        "audit status",
        config,
        planner=FixedPlanner(),
    )

    assert traced.trace.query.variant_retrieval_status == "embedding_fallback"
    assert batches == [["audit status", "approval state"], ["audit status"]]


def test_direct_text_probes_are_computed_once_before_stage_timer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, config = _indexed_repo(tmp_path)
    events: list[str] = []
    original_probes = retrieval._direct_text_probes
    original_start = retrieval._trace_stage_start

    def probes(*args, **kwargs):
        events.append("probes")
        return original_probes(*args, **kwargs)

    def start(collector, name, **kwargs):
        events.append(f"start:{name}")
        return original_start(collector, name, **kwargs)

    monkeypatch.setattr(retrieval, "_direct_text_probes", probes)
    monkeypatch.setattr(retrieval, "_trace_stage_start", start)

    retrieval.trace_repository(repo, "INVOLVED_BY_ME", config)

    assert events.count("probes") == 1
    assert events.index("probes") < events.index("start:direct_text_recall")


def test_every_stage_orders_live_operation_stop_clock_and_observation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, config = _indexed_repo(tmp_path)
    events: list[str] = []
    active: dict[str, str | None] = {"stage": None}
    stopped_state: dict[str, str | None] = {"stage": None}
    ticks = 0

    def clock() -> int:
        nonlocal ticks
        ticks += 1_000_000
        events.append(f"clock:{active['stage'] or 'total'}")
        return ticks

    original_start = RetrievalTraceCollector.start_stage
    original_stop = RetrievalTraceCollector.stop_stage
    original_finish_stage = RetrievalTraceCollector.finish_stage
    original_finish = RetrievalTraceCollector.finish

    def start(collector, name, **kwargs):
        token = original_start(collector, name, **kwargs)
        active["stage"] = name
        events.append(f"start:{name}")
        return token

    def stop(collector, token):
        stopped = original_stop(collector, token)
        events.append(f"stop:{token.name}")
        active["stage"] = None
        stopped_state["stage"] = token.name
        return stopped

    def finish_stage(collector, stage, **kwargs):
        events.append(f"observe:{stage.name}")
        result = original_finish_stage(collector, stage, **kwargs)
        stopped_state["stage"] = None
        return result

    def finish(collector, **kwargs):
        events.append("total_finish")
        return original_finish(collector, **kwargs)

    monkeypatch.setattr(RetrievalTraceCollector, "start_stage", start)
    monkeypatch.setattr(RetrievalTraceCollector, "stop_stage", stop)
    monkeypatch.setattr(RetrievalTraceCollector, "finish_stage", finish_stage)
    monkeypatch.setattr(RetrievalTraceCollector, "finish", finish)

    for adapter_name in (
        "_trace_candidate_observations",
        "_trace_ranked_observations",
        "_trace_expanded_observations",
        "_trace_final_selections",
    ):
        original_adapter = getattr(retrieval, adapter_name)

        def make_adapter(name, adapter):
            def wrapped(*args, **kwargs):
                assert active["stage"] is None
                assert stopped_state["stage"] is not None
                events.append(f"adapter:{stopped_state['stage']}")
                return adapter(*args, **kwargs)

            return wrapped

        monkeypatch.setattr(
            retrieval,
            adapter_name,
            make_adapter(adapter_name, original_adapter),
        )

    def mark_operation(target: Any, name: str) -> None:
        original = getattr(target, name)

        def wrapped(*args, **kwargs):
            result = original(*args, **kwargs)
            if active["stage"] is not None:
                events.append(f"operation:{active['stage']}")
            return result

        monkeypatch.setattr(target, name, wrapped)

    for name in (
        "build_query_variants",
        "_semantic_candidates",
        "_lexical_candidates",
        "_signal_candidates",
        "_planner_hint_candidates",
        "_merge_candidates",
        "_anchor_expansion_candidates",
        "_relation_expansion_candidates",
        "_rank_chunks",
        "_apply_frontend_import_cohort_rerank",
        "_expand_ranked_chunks",
        "_split_code_results_and_evidence_anchors",
    ):
        mark_operation(retrieval, name)
    mark_operation(SQLiteStore, "path_symbol_search")
    mark_operation(SQLiteStore, "direct_text_search")

    original_summary = retrieval._summarize_results

    def summarize(*args, **kwargs):
        events.append("output_assembly")
        return original_summary(*args, **kwargs)

    original_bundle = retrieval.QueryBundle

    def bundle(*args, **kwargs):
        events.append("bundle_construction")
        return original_bundle(*args, **kwargs)

    monkeypatch.setattr(retrieval, "_summarize_results", summarize)
    monkeypatch.setattr(retrieval, "QueryBundle", bundle)

    traced = retrieval.trace_repository(
        repo,
        "INVOLVED_BY_ME audit",
        config,
        clock_ns=clock,
    )

    assert [stage.name for stage in traced.trace.stages] == list(
        CANONICAL_TRACE_STAGES
    )
    for stage in CANONICAL_TRACE_STAGES:
        start_index = events.index(f"start:{stage}")
        operation_index = events.index(f"operation:{stage}")
        stop_clock_index = events.index(f"clock:{stage}", operation_index)
        stop_index = events.index(f"stop:{stage}")
        observation_index = events.index(f"observe:{stage}")
        assert start_index < operation_index < stop_clock_index < stop_index
        assert stop_index < observation_index
        if stage != "query_understanding":
            adapter_index = events.index(f"adapter:{stage}")
            assert stop_index < adapter_index < observation_index

    final_stop = events.index("stop:final_selection")
    assert final_stop < events.index("observe:final_selection")
    assert final_stop < events.index("adapter:final_selection")
    assert final_stop < events.index("output_assembly")
    assert final_stop < events.index("bundle_construction")
    assert events.index("bundle_construction") < events.index("total_finish")


def test_trace_adapters_never_read_content_or_private_context_content() -> None:
    class ContentTrap:
        chunk_id = "chunk-a"
        file_path = Path("src/AuditStatus.java")
        start_line = 1
        end_line = 3

        @property
        def content(self):
            raise AssertionError("trace adapter read .content")

        @property
        def _context_content(self):
            raise AssertionError("trace adapter read ._context_content")

    class Store:
        def chunks_for_ids(self, chunk_ids):
            return {"chunk-a": ContentTrap()}

    candidate = RetrievalCandidate(
        chunk_id="chunk-a",
        score=0.8,
        source="semantic",
        score_parts={"semantic": 0.8},
        semantic_matches=[SemanticMatch("original", 0.8)],
    )
    ranked = core_types._RankedChunk(
        chunk=ContentTrap(),  # type: ignore[arg-type]
        score=0.8,
        score_parts={"semantic": 0.8},
        reasons=["semantic match"],
        rank_tier=0,
        rerank_score=0.8,
        evidence_class="original_direct",
        evidence_priority=0,
        semantic_matches=[SemanticMatch("original", 0.8)],
    )

    class ExpandedTrap(ContentTrap):
        chunk_ids = ["chunk-a"]
        score = 0.8
        score_parts = {"semantic": 0.8}
        reasons = ["semantic match"]
        followup_keywords: list[str] = []
        rank_tier = 0
        rerank_score = 0.8
        evidence_class = "original_direct"
        evidence_priority = 0
        semantic_matches = [SemanticMatch("original", 0.8)]
        pre_ceiling_rerank_score = 0.8
        was_ceiling_clamped = False
        spans = ()

    expanded = ExpandedTrap()
    candidates = {"chunk-a": candidate}
    decisions = retrieval._FinalTraceDecisions(
        selected=(
            retrieval._FinalTraceInput(
                kind="result",
                reason="selected_within_result_limit",
                item=expanded,  # type: ignore[arg-type]
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

    assert retrieval._trace_candidate_observations(Store(), [candidate], 5)
    assert retrieval._trace_ranked_observations([ranked], candidates, 5)
    assert retrieval._trace_expanded_observations([expanded], candidates, 5)
    assert retrieval._trace_final_selections(
        decisions,
        candidates,
        FinalSelectionCollector(),  # type: ignore[arg-type]
    )


def _all_strings(value: Any) -> list[str]:
    if isinstance(value, dict):
        return [item for child in value.values() for item in _all_strings(child)]
    if isinstance(value, (list, tuple)):
        return [item for child in value for item in _all_strings(child)]
    return [value] if isinstance(value, str) else []


def test_trace_tree_rejects_source_environment_secret_and_absolute_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, config = _indexed_repo(tmp_path)
    monkeypatch.setenv("PRIVATE_TRACE_SENTINEL", "ENVIRONMENT_SECRET_SENTINEL")

    traced = retrieval.trace_repository(repo, "audit", config)
    strings = _all_strings(asdict(traced.trace))

    assert "INVOLVED_BY_ME" not in "\n".join(strings)
    assert "ENVIRONMENT_SECRET_SENTINEL" not in strings
    assert "Authorization" not in strings
    assert "Bearer" not in strings
    assert all(not Path(value).is_absolute() for value in strings if "/" in value)


def test_mcp_trace_success_early_return_and_error_never_write_feedback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, config = _indexed_repo(tmp_path)

    def forbidden(*args, **kwargs):
        raise AssertionError("trace path attempted feedback persistence")

    monkeypatch.setattr(mcp_tools, "_try_append_query_feedback", forbidden)
    monkeypatch.setattr(mcp_tools, "_append_query_feedback", forbidden)

    success = mcp_tools.context_search_trace_tool(str(repo), "audit")
    assert success["ok"] is True

    missing = tmp_path / "missing-index"
    missing.mkdir()
    early = mcp_tools.context_search_trace_tool(str(missing), "audit")
    assert early["ok"] is False
    assert early["error"]["code"] == "missing_index"
    assert "trace" not in early

    monkeypatch.setattr(
        mcp_tools,
        "trace_repository",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            RuntimeError("PRIVATE_TRACE_ERROR")
        ),
    )
    failed = mcp_tools.context_search_trace_tool(str(repo), "audit")
    assert failed == {
        "ok": False,
        "error": {"code": "trace_failed", "message": "Retrieval trace failed"},
    }
    assert "PRIVATE_TRACE_ERROR" not in repr(failed)
