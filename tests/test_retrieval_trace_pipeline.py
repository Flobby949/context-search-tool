from __future__ import annotations

import sqlite3
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
from context_search_tool.models import (
    QueryPlan,
    RetrievalCandidate,
    SemanticMatch,
)
from context_search_tool.retrieval_trace import (
    CANONICAL_TRACE_STAGES,
    TraceLimits,
)


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
    monkeypatch.setattr(retrieval, "_trace_query", forbidden)

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


def test_trace_repository_reports_store_read_error_before_stages(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, config = _indexed_repo(tmp_path)

    def fail_store_read(self):
        raise sqlite3.Error("PRIVATE_STORE_ERROR")

    monkeypatch.setattr(retrieval.SQLiteStore, "deleted_chunk_ids", fail_store_read)
    traced = retrieval.trace_repository(repo, "audit", config)

    assert traced.bundle.results == []
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

    traced = retrieval.trace_repository(repo, "audit", config)

    assert traced.bundle.results == []
    assert traced.trace.outcome == "empty"
    assert traced.trace.termination_reason == "no_candidates"
    assert [stage.name for stage in traced.trace.stages] == list(
        CANONICAL_TRACE_STAGES[:11]
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
