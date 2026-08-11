from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from context_search_tool.models import (
    CodeSignal,
    DocumentChunk,
    ExactImportedSymbolProvenance,
    QueryPlan,
    RetrievalCandidate,
)
from context_search_tool.retrieval_core import (
    candidates,
    context_expansion,
    ranking,
    types as core_types,
)


def _atom(
    *,
    relation_id: str,
    target_chunk_id: str,
    target_file_path: str,
    position: int,
    source_signal_id: str = "source-signal",
    source_file_path: str = "src/source.py",
    source_chunk_id: str = "source-chunk",
    target_signal_id: str | None = None,
    source_owner_qualified_names: tuple[str, ...] = (),
) -> ExactImportedSymbolProvenance:
    return ExactImportedSymbolProvenance(
        relation_id=relation_id,
        source_signal_id=source_signal_id,
        source_file_path=source_file_path,
        source_chunk_id=source_chunk_id,
        target_signal_id=target_signal_id or f"signal-{target_chunk_id}",
        target_file_path=target_file_path,
        target_chunk_id=target_chunk_id,
        relation_kind="imports",
        resolution="resolved_exact",
        producer="python_ast",
        resolution_basis="exact_python_imported_symbol",
        ordered_edge_position=position,
        source_owner_qualified_names=source_owner_qualified_names,
    )


def _ranked(
    chunk_id: str,
    path: str,
    rerank_score: float,
) -> core_types._RankedChunk:
    return core_types._RankedChunk(
        chunk=DocumentChunk(
            chunk_id=chunk_id,
            file_path=Path(path),
            start_line=1,
            end_line=2,
            content=chunk_id,
            chunk_type="symbol",
        ),
        score=rerank_score,
        score_parts={"rerank_score": rerank_score, "role_priority": 0.0},
        reasons=[],
        rank_tier=0,
        rerank_score=rerank_score,
        evidence_class="strong_original_direct",
        evidence_priority=0,
    )


def _candidate(
    chunk_id: str,
    provenance: tuple[ExactImportedSymbolProvenance, ...],
) -> RetrievalCandidate:
    return RetrievalCandidate(
        chunk_id=chunk_id,
        score=0.0,
        source="test",
        exact_imported_symbol_provenance=provenance,
    )


def test_candidate_merge_preserves_sorted_complete_tuple_union() -> None:
    later = _atom(
        relation_id="relation-b",
        target_chunk_id="target",
        target_file_path="pkg/target.py",
        position=2,
    )
    earlier = _atom(
        relation_id="relation-a",
        target_chunk_id="target",
        target_file_path="pkg/target.py",
        position=1,
    )

    merged = candidates.merge_candidates(
        [
            RetrievalCandidate(
                chunk_id="target",
                score=0.4,
                source="relation",
                exact_imported_symbol_provenance=(later,),
            ),
            RetrievalCandidate(
                chunk_id="target",
                score=0.6,
                source="lexical",
                exact_imported_symbol_provenance=(earlier, later),
            ),
        ]
    )["target"]

    assert merged.exact_imported_symbol_provenance == (earlier, later)


def test_bonus_chooses_best_exact_eligible_candidate_once_and_reranks() -> None:
    best_atom = _atom(
        relation_id="best-relation",
        target_chunk_id="best",
        target_file_path="pkg/best.py",
        position=1,
    )
    other_atoms = (
        _atom(
            relation_id="other-relation-a",
            target_chunk_id="other",
            target_file_path="pkg/other.py",
            position=2,
        ),
        _atom(
            relation_id="other-relation-b",
            target_chunk_id="other",
            target_file_path="pkg/other.py",
            position=3,
        ),
    )
    best = _ranked("best", "pkg/best.py", 0.50)
    other = _ranked("other", "pkg/other.py", 0.49)
    mismatched = _ranked("mismatch", "pkg/mismatch.py", 0.80)
    candidate_map = {
        "best": _candidate("best", (best_atom,)),
        "other": _candidate("other", other_atoms),
        "mismatch": _candidate("mismatch", (best_atom,)),
    }

    adjusted = ranking.apply_exact_imported_symbol_bonus(
        [other, mismatched, best],
        candidate_map,
        "query",
    )

    by_id = {item.chunk.chunk_id: item for item in adjusted}
    assert by_id["best"].rerank_score == pytest.approx(0.54)
    assert by_id["best"].score_parts["exact_imported_symbol"] == pytest.approx(0.04)
    assert by_id["best"].score_parts["rerank_score"] == pytest.approx(0.54)
    assert by_id["best"].reasons.count("exact imported symbol dependency") == 1
    assert "exact_imported_symbol" not in by_id["other"].score_parts
    assert "exact_imported_symbol" not in by_id["mismatch"].score_parts
    assert adjusted[0].chunk.chunk_id == "mismatch"
    assert adjusted[1].chunk.chunk_id == "best"


def test_bonus_winner_is_independent_of_input_iteration_order() -> None:
    atom_a = _atom(
        relation_id="relation-a",
        target_chunk_id="a",
        target_file_path="pkg/a.py",
        position=1,
    )
    atom_b = _atom(
        relation_id="relation-b",
        target_chunk_id="b",
        target_file_path="pkg/b.py",
        position=2,
    )
    candidate_a = _ranked("a", "pkg/a.py", 0.5)
    candidate_b = _ranked("b", "pkg/b.py", 0.5)
    candidate_map = {
        "a": _candidate("a", (atom_a,)),
        "b": _candidate("b", (atom_b,)),
    }

    canonical = ranking.apply_exact_imported_symbol_bonus(
        [candidate_a, candidate_b],
        candidate_map,
        "query",
    )
    reversed_order = ranking.apply_exact_imported_symbol_bonus(
        [candidate_b, candidate_a],
        candidate_map,
        "query",
    )

    assert [item.chunk.chunk_id for item in canonical] == ["a", "b"]
    assert [item.chunk.chunk_id for item in reversed_order] == ["a", "b"]
    assert canonical[0].score_parts["exact_imported_symbol"] == pytest.approx(0.04)
    assert "exact_imported_symbol" not in canonical[1].score_parts


def test_context_overlap_preserves_exact_imported_symbol_reason() -> None:
    left = core_types._ExpandedResult(
        chunk_ids=["exact"],
        file_path=Path("pkg/target.py"),
        start_line=1,
        end_line=2,
        content="one\ntwo",
        score=0.5,
        score_parts={"exact_imported_symbol": 0.04, "rerank_score": 0.5},
        reasons=["exact imported symbol dependency"],
        followup_keywords=[],
        rank_tier=0,
        rerank_score=0.5,
        evidence_class="original_relation",
        evidence_priority=1,
    )
    right = core_types._ExpandedResult(
        chunk_ids=["winner"],
        file_path=Path("pkg/target.py"),
        start_line=2,
        end_line=3,
        content="two\nthree",
        score=0.6,
        score_parts={"rerank_score": 0.6},
        reasons=["lexical match"],
        followup_keywords=[],
        rank_tier=0,
        rerank_score=0.6,
        evidence_class="original_direct",
        evidence_priority=0,
    )

    merged = context_expansion._merge_expanded_result(left, right)

    assert merged.score_parts["exact_imported_symbol"] == pytest.approx(0.04)
    assert merged.reasons == [
        "lexical match",
        "exact imported symbol dependency",
    ]


def test_context_overlap_preserves_planner_dependency_promotion_reason() -> None:
    left = core_types._ExpandedResult(
        chunk_ids=["promoted"],
        file_path=Path("pkg/target.py"),
        start_line=1,
        end_line=2,
        content="one\ntwo",
        score=0.5,
        score_parts={
            "planner_dependency_hint_promotion": 0.4,
            "rerank_score": 0.5,
        },
        reasons=["planner dependency target promotion"],
        followup_keywords=[],
        rank_tier=0,
        rerank_score=0.5,
        evidence_class="original_relation",
        evidence_priority=1,
    )
    right = core_types._ExpandedResult(
        chunk_ids=["winner"],
        file_path=Path("pkg/target.py"),
        start_line=2,
        end_line=3,
        content="two\nthree",
        score=0.6,
        score_parts={"rerank_score": 0.6},
        reasons=["lexical match"],
        followup_keywords=[],
        rank_tier=0,
        rerank_score=0.6,
        evidence_class="original_direct",
        evidence_priority=0,
    )

    merged = context_expansion._merge_expanded_result(left, right)

    assert merged.score_parts["planner_dependency_hint_promotion"] == pytest.approx(
        0.4
    )
    assert merged.reasons == [
        "lexical match",
        "planner dependency target promotion",
    ]


class _SignalLookup:
    graph_fault = None

    def __init__(self, signals: dict[str, CodeSignal]) -> None:
        self.signals = signals

    def signal_for_id(self, signal_id: str) -> CodeSignal | None:
        return self.signals.get(signal_id)


def _dependency_ranked(index: int) -> core_types._RankedChunk:
    return _ranked(
        f"chunk-{index:02d}",
        f"src/module_{index:02d}.py",
        1.0 - (index * 0.05),
    )


def _dependency_candidate(
    index: int,
    *,
    source_index: int | None = None,
    source_signal_id: str | None = None,
    source_owner_qualified_names: tuple[str, ...] = (),
) -> RetrievalCandidate:
    resolved_source_index = index if source_index is None else source_index
    return _candidate(
        f"chunk-{index:02d}",
        (
            _atom(
                relation_id=f"relation-{index}",
                target_chunk_id=f"chunk-{index:02d}",
                target_file_path=f"src/module_{index:02d}.py",
                position=index,
                source_signal_id=source_signal_id
                or f"source-signal-{resolved_source_index:02d}",
                source_file_path=f"src/source_{resolved_source_index:02d}.py",
                source_chunk_id=f"source-chunk-{resolved_source_index:02d}",
                source_owner_qualified_names=source_owner_qualified_names,
            ),
        ),
    )


def _dependency_signal(index: int) -> CodeSignal:
    return CodeSignal(
        signal_id=f"signal-chunk-{index:02d}",
        chunk_id=f"chunk-{index:02d}",
        file_path=Path(f"src/module_{index:02d}.py"),
        kind="type",
        name=f"Target{index}",
        start_line=1,
        end_line=2,
        language="python",
        producer="python_ast",
    )


def _dependency_source_signal(index: int) -> CodeSignal:
    path = Path(f"src/source_{index:02d}.py")
    return CodeSignal(
        signal_id=f"source-signal-{index:02d}",
        chunk_id=f"source-chunk-{index:02d}",
        file_path=path,
        kind="module",
        name=path.as_posix(),
        qualified_name=path.as_posix(),
        start_line=1,
        end_line=2,
        language="python",
        project_unit_key="src",
        producer="core_module",
        recallable=False,
    )


def _dependency_signals(*indices: int) -> dict[str, CodeSignal]:
    signals = [
        signal
        for index in indices
        for signal in (_dependency_source_signal(index), _dependency_signal(index))
    ]
    return {signal.signal_id: signal for signal in signals}


def _promotion_observation(
    status: str,
    *,
    exact_source: int = 0,
    exact_target: int = 0,
    semantic_pair: int = 0,
    path_count: int = 0,
) -> dict[str, object]:
    return {
        "status": status,
        "exact_source_hint_promoted": exact_source,
        "exact_target_hint_promoted": exact_target,
        "semantic_pair_fallback_promoted": semantic_pair,
        "promoted_path_count": path_count,
    }


_DEFAULT_GRAPH_SESSION = object()


def _observe_dependency_promotion_no_op(
    plan: QueryPlan,
    *,
    graph_session: object = _DEFAULT_GRAPH_SESSION,
    final_top_k: int = 12,
) -> dict[str, object]:
    ranked = [_dependency_ranked(index) for index in range(13)]
    observations: list[dict[str, object]] = []
    resolved_graph_session = (
        _SignalLookup(_dependency_signals(12))
        if graph_session is _DEFAULT_GRAPH_SESSION
        else graph_session
    )

    unchanged = ranking.apply_planner_dependency_hint_promotions(
        ranked,
        {"chunk-12": _dependency_candidate(12)},
        plan,
        "trace imports",
        resolved_graph_session,
        final_top_k=final_top_k,
        observation_callback=observations.append,
    )

    assert unchanged == ranked
    assert len(observations) == 1
    return observations[0]


def _single_source_dependency_promotion_inputs() -> tuple[
    list[core_types._RankedChunk],
    dict[str, RetrievalCandidate],
    QueryPlan,
    _SignalLookup,
]:
    return (
        [_dependency_ranked(index) for index in range(13)],
        {"chunk-12": _dependency_candidate(12)},
        QueryPlan(
            original_query="trace imports",
            status="ok",
            dependency_intent="follow_imports",
            source_module_hints=["source_12"],
        ),
        _SignalLookup(_dependency_signals(12)),
    )


def test_source_hints_promote_at_most_two_actual_admissible_targets_into_top12() -> None:
    ranked = [_dependency_ranked(index) for index in range(16)]
    candidates = {
        f"chunk-{index:02d}": _dependency_candidate(index)
        for index in (12, 13, 14, 15)
    }
    candidates["chunk-12"] = _candidate(
        "chunk-12",
        (
            replace(
                candidates["chunk-12"].exact_imported_symbol_provenance[0],
                target_signal_id="wrong-target-signal",
            ),
        ),
    )
    plan = QueryPlan(
        original_query="trace source modules",
        status="ok",
        dependency_intent="follow_imports",
        source_module_hints=["source_12", "source_13", "source_14", "source_15"],
    )
    observations: list[dict[str, object]] = []

    promoted = ranking.apply_planner_dependency_hint_promotions(
        list(reversed(ranked)),
        dict(reversed(list(candidates.items()))),
        plan,
        "trace source modules",
        _SignalLookup(_dependency_signals(12, 13, 14, 15)),
        final_top_k=12,
        observation_callback=observations.append,
    )

    promoted_paths = [item.chunk.file_path.as_posix() for item in promoted[:12]]
    assert promoted_paths[0] == "src/module_00.py"
    assert "src/module_13.py" in promoted_paths
    assert "src/module_14.py" in promoted_paths
    assert "src/module_12.py" not in promoted_paths
    assert "src/module_15.py" not in promoted_paths
    assert "src/module_10.py" not in promoted_paths
    assert "src/module_11.py" not in promoted_paths
    by_path = {item.chunk.file_path.as_posix(): item for item in promoted}
    for path in ("src/module_13.py", "src/module_14.py"):
        assert by_path[path].score_parts["planner_dependency_hint_promotion"] > 0
        assert by_path[path].reasons.count(
            "planner dependency target promotion"
        ) == 1
    assert observations == [
        _promotion_observation("promoted", exact_source=2, path_count=2)
    ]


def test_dependency_promotions_do_not_evict_the_matched_source_path() -> None:
    ranked = [
        *(_dependency_ranked(index) for index in range(10)),
        _ranked("source-chunk-12", "src/source_12.py", 0.49),
        _dependency_ranked(11),
        _dependency_ranked(12),
        _dependency_ranked(13),
    ]
    candidates = {
        f"chunk-{index:02d}": _dependency_candidate(
            index,
            source_index=12,
            source_owner_qualified_names=("Owner",),
        )
        for index in (12, 13)
    }
    plan = QueryPlan(
        original_query="trace Owner imports",
        status="ok",
        dependency_intent="follow_imports",
        source_symbol_hints=["Owner"],
        source_module_hints=["source_12"],
    )
    observations: list[dict[str, object]] = []

    promoted = ranking.apply_planner_dependency_hint_promotions(
        ranked,
        candidates,
        plan,
        "trace Owner imports",
        _SignalLookup(_dependency_signals(12, 13)),
        final_top_k=12,
        observation_callback=observations.append,
    )

    promoted_paths = [item.chunk.file_path.as_posix() for item in promoted[:12]]
    assert "src/source_12.py" in promoted_paths
    assert "src/module_12.py" in promoted_paths
    assert "src/module_13.py" not in promoted_paths
    assert "src/module_11.py" not in promoted_paths
    assert observations == [
        _promotion_observation("promoted", exact_source=1, path_count=1)
    ]


def test_dedicated_source_module_hints_activate_dependency_promotion() -> None:
    ranked, candidates, plan, signals = _single_source_dependency_promotion_inputs()
    observations: list[dict[str, object]] = []

    promoted = ranking.apply_planner_dependency_hint_promotions(
        ranked,
        candidates,
        plan,
        "trace imports",
        signals,
        final_top_k=12,
        observation_callback=observations.append,
    )

    promoted_target = next(
        item for item in promoted if item.chunk.file_path == Path("src/module_12.py")
    )
    assert promoted_target in promoted[:12]
    assert promoted_target.score_parts["planner_dependency_hint_promotion"] > 0
    assert observations == [
        _promotion_observation("promoted", exact_source=1, path_count=1)
    ]


def test_observation_callback_is_optional_and_failure_is_isolated() -> None:
    ranked, candidates, plan, signals = _single_source_dependency_promotion_inputs()
    unobserved = ranking.apply_planner_dependency_hint_promotions(
        ranked,
        candidates,
        plan,
        "trace imports",
        signals,
        final_top_k=12,
    )

    def fail_observation(_observation: dict[str, object]) -> None:
        raise RuntimeError("observer failed")

    assert ranking.apply_planner_dependency_hint_promotions(
        ranked,
        candidates,
        plan,
        "trace imports",
        signals,
        final_top_k=12,
        observation_callback=fail_observation,
    ) == unobserved


@pytest.mark.parametrize(
    (
        "plan_changes",
        "graph_state",
        "final_top_k",
        "expected_status",
    ),
    [
        pytest.param(
            {
                "source_module_hints": [],
                "symbol_hints": ["source_12"],
                "grep_keywords": ["src.source_12"],
            },
            "available",
            12,
            "missing_activation_hint",
            id="generic-hints",
        ),
        pytest.param(
            {
                "source_module_hints": [],
                "imported_module_hints": ["module_12"],
            },
            "available",
            12,
            "missing_activation_hint",
            id="imported-module-only",
        ),
        pytest.param({}, "fault", 12, "graph_unavailable", id="graph-fault"),
        pytest.param(
            {"status": "fallback"},
            "available",
            12,
            "planner_not_ok",
            id="planner-fallback",
        ),
        pytest.param(
            {"dependency_intent": "none"},
            "available",
            12,
            "intent_mismatch",
            id="intent-mismatch",
        ),
        pytest.param({}, "available", 0, "disabled", id="nonpositive-top-k"),
    ],
)
def test_dependency_promotion_no_op_reports_status(
    plan_changes: dict[str, object],
    graph_state: str,
    final_top_k: int,
    expected_status: str,
) -> None:
    plan = replace(
        QueryPlan(
            original_query="trace imports",
            status="ok",
            dependency_intent="follow_imports",
            source_module_hints=["source_12"],
        ),
        **plan_changes,
    )
    graph_session = _SignalLookup(_dependency_signals(12))
    graph_session.graph_fault = (
        "graph read failed" if graph_state == "fault" else None
    )

    observation = _observe_dependency_promotion_no_op(
        plan,
        graph_session=graph_session,
        final_top_k=final_top_k,
    )

    assert observation == _promotion_observation(expected_status)


def test_source_hint_matching_is_exact_and_does_not_use_substrings() -> None:
    ranked = [_dependency_ranked(index) for index in range(13)]
    candidate = _dependency_candidate(12)
    plan = QueryPlan(
        original_query="trace imports",
        status="ok",
        dependency_intent="follow_imports",
        source_module_hints=["source_1", "source_120"],
    )

    unchanged = ranking.apply_planner_dependency_hint_promotions(
        ranked,
        {"chunk-12": candidate},
        plan,
        "trace imports",
        _SignalLookup(_dependency_signals(12)),
        final_top_k=12,
    )

    assert unchanged == ranked


@pytest.mark.parametrize(
    ("file_path", "hint"),
    [
        ("src/anyio/_core/_fileio.py", "anyio._core._fileio"),
        ("multidict/__init__.py", "multidict"),
    ],
)
def test_source_hint_matching_uses_python_module_identity(
    file_path: str,
    hint: str,
) -> None:
    signal = replace(
        _dependency_source_signal(12),
        file_path=Path(file_path),
        project_unit_key="",
    )

    assert ranking._dependency_source_signal_matches(signal, {hint}) is True


@pytest.mark.parametrize(
    "source_signal",
    [
        replace(_dependency_source_signal(12), signal_id="wrong-source-signal"),
        replace(_dependency_source_signal(12), kind="type"),
        replace(_dependency_source_signal(12), producer="python_ast"),
        replace(_dependency_source_signal(12), chunk_id="wrong-source-chunk"),
        replace(_dependency_source_signal(12), file_path=Path("src/wrong_source.py")),
    ],
)
def test_corrupt_source_identity_fails_closed(source_signal: CodeSignal) -> None:
    ranked = [_dependency_ranked(index) for index in range(13)]
    target_signal = _dependency_signal(12)
    plan = QueryPlan(
        original_query="trace imports",
        status="ok",
        dependency_intent="follow_imports",
        source_module_hints=["source_12"],
    )
    observations: list[dict[str, object]] = []

    unchanged = ranking.apply_planner_dependency_hint_promotions(
        ranked,
        {"chunk-12": _dependency_candidate(12)},
        plan,
        "trace imports",
        _SignalLookup(
            {
                source_signal.signal_id: source_signal,
                target_signal.signal_id: target_signal,
            }
        ),
        final_top_k=12,
        observation_callback=observations.append,
    )

    assert unchanged == ranked
    assert observations == [
        _promotion_observation("no_eligible_closed_candidate")
    ]


@pytest.mark.parametrize(
    "target_signal",
    [
        replace(_dependency_signal(12), signal_id="wrong-target-signal"),
        replace(_dependency_signal(12), chunk_id="wrong-target-chunk"),
        replace(_dependency_signal(12), file_path=Path("src/wrong_target.py")),
        replace(_dependency_signal(12), producer="core_module"),
    ],
)
def test_corrupt_target_identity_fails_closed(target_signal: CodeSignal) -> None:
    ranked = [_dependency_ranked(index) for index in range(13)]
    source_signal = _dependency_source_signal(12)
    plan = QueryPlan(
        original_query="trace imports",
        status="ok",
        dependency_intent="follow_imports",
        source_module_hints=["source_12"],
    )

    unchanged = ranking.apply_planner_dependency_hint_promotions(
        ranked,
        {"chunk-12": _dependency_candidate(12)},
        plan,
        "trace imports",
        _SignalLookup(
            {
                source_signal.signal_id: source_signal,
                target_signal.signal_id: target_signal,
            }
        ),
        final_top_k=12,
    )

    assert unchanged == ranked


def test_target_only_dependency_hints_do_not_trigger_promotion() -> None:
    ranked = [_dependency_ranked(index) for index in range(13)]
    plan = QueryPlan(
        original_query="trace imports",
        status="ok",
        dependency_intent="follow_imports",
        imported_symbol_hints=["Target12"],
        imported_module_hints=["module_12"],
    )

    unchanged = ranking.apply_planner_dependency_hint_promotions(
        ranked,
        {"chunk-12": _dependency_candidate(12)},
        plan,
        "trace imports",
        _SignalLookup(_dependency_signals(12)),
        final_top_k=12,
    )

    assert unchanged == ranked


def test_exact_target_hint_recovers_from_misclassified_source_hint() -> None:
    source = _ranked("source-chunk-12", "src/source_12.py", 0.80)
    ranked = [source, *[_dependency_ranked(index) for index in range(13)]]
    plan = QueryPlan(
        original_query="trace exact imported target",
        status="ok",
        dependency_intent="follow_imports",
        source_module_hints=["wrong_source"],
        imported_symbol_hints=["Target12"],
    )
    observations: list[dict[str, object]] = []

    promoted = ranking.apply_planner_dependency_hint_promotions(
        ranked,
        {"chunk-12": _dependency_candidate(12)},
        plan,
        "trace exact imported target",
        _SignalLookup(_dependency_signals(12)),
        final_top_k=12,
        observation_callback=observations.append,
    )

    target = next(item for item in promoted if item.chunk.chunk_id == "chunk-12")
    assert target in promoted[:12]
    assert target.score_parts["planner_dependency_hint_promotion"] > 0
    assert observations == [
        _promotion_observation("promoted", exact_target=1, path_count=1)
    ]


def test_misclassified_source_module_hint_recovers_exact_source_identity() -> None:
    source = _ranked("source-chunk-12", "src/source_12.py", 0.80)
    ranked = [source, *[_dependency_ranked(index) for index in range(13)]]
    plan = QueryPlan(
        original_query="trace runtime fallback",
        status="ok",
        dependency_intent="follow_imports",
        imported_symbol_hints=["runtime_fallback"],
        imported_module_hints=["source_12"],
    )
    observations: list[dict[str, object]] = []

    promoted = ranking.apply_planner_dependency_hint_promotions(
        ranked,
        {"chunk-12": _dependency_candidate(12)},
        plan,
        "trace runtime fallback",
        _SignalLookup(_dependency_signals(12)),
        final_top_k=12,
        observation_callback=observations.append,
    )

    target = next(item for item in promoted if item.chunk.chunk_id == "chunk-12")
    assert target in promoted[:12]
    assert target.score_parts["planner_dependency_hint_promotion"] > 0
    assert observations == [
        _promotion_observation("promoted", exact_source=1, path_count=1)
    ]


def test_source_owner_hint_selects_only_edges_used_by_that_declaration() -> None:
    source = _ranked("source-chunk-12", "src/source_12.py", 0.80)
    ranked = [source, *[_dependency_ranked(index) for index in range(14)]]
    candidates = {
        "chunk-12": _dependency_candidate(
            12,
            source_owner_qualified_names=("unrelated",),
        ),
        "chunk-13": _dependency_candidate(
            13,
            source_index=12,
            source_owner_qualified_names=("plain_traceback",),
        ),
    }
    plan = QueryPlan(
        original_query="trace plain_traceback imports",
        status="ok",
        dependency_intent="follow_imports",
        source_symbol_hints=["plain_traceback"],
        source_module_hints=["source_12"],
    )

    promoted = ranking.apply_planner_dependency_hint_promotions(
        ranked,
        candidates,
        plan,
        "trace plain_traceback imports",
        _SignalLookup(_dependency_signals(12, 13)),
        final_top_k=12,
    )

    promoted_paths = {
        item.chunk.file_path.as_posix()
        for item in promoted[:12]
        if item.score_parts.get("planner_dependency_hint_promotion", 0.0) > 0
    }
    assert promoted_paths == {"src/module_13.py"}


def test_source_owner_hint_does_not_degrade_to_same_named_module() -> None:
    source_signal = replace(
        _dependency_source_signal(12),
        file_path=Path("src/code.py"),
        name="src/code.py",
        qualified_name="src/code.py",
    )
    source = _ranked("source-chunk-12", "src/code.py", 0.80)
    ranked = [source, *[_dependency_ranked(index) for index in range(13)]]
    candidate = _dependency_candidate(
        12,
        source_owner_qualified_names=("ExceptionInfo",),
    )
    candidate = _candidate(
        "chunk-12",
        (
            replace(
                candidate.exact_imported_symbol_provenance[0],
                source_file_path="src/code.py",
            ),
        ),
    )
    plan = QueryPlan(
        original_query="trace Code imports",
        status="ok",
        dependency_intent="follow_imports",
        source_symbol_hints=["Code"],
        source_module_hints=["code"],
    )
    observations: list[dict[str, object]] = []

    unchanged = ranking.apply_planner_dependency_hint_promotions(
        ranked,
        {"chunk-12": candidate},
        plan,
        "trace Code imports",
        _SignalLookup(
            {
                source_signal.signal_id: source_signal,
                _dependency_signal(12).signal_id: _dependency_signal(12),
            }
        ),
        final_top_k=12,
        observation_callback=observations.append,
    )

    assert unchanged == sorted(ranked, key=ranking._ranked_chunk_sort_key)
    assert observations == [
        _promotion_observation("no_eligible_closed_candidate")
    ]


def test_source_owner_hint_is_anchored_to_the_source_module() -> None:
    sources = [
        _ranked("source-chunk-12", "src/source_12.py", 0.82),
        _ranked("source-chunk-13", "src/source_13.py", 0.81),
    ]
    ranked = [*sources, *[_dependency_ranked(index) for index in range(14)]]
    candidates = {
        f"chunk-{index:02d}": _dependency_candidate(
            index,
            source_owner_qualified_names=("pytest_addoption",),
        )
        for index in (12, 13)
    }
    plan = QueryPlan(
        original_query="trace pytest_addoption imports",
        status="ok",
        dependency_intent="follow_imports",
        source_symbol_hints=["pytest_addoption"],
        source_module_hints=["source_12"],
    )

    promoted = ranking.apply_planner_dependency_hint_promotions(
        ranked,
        candidates,
        plan,
        "trace pytest_addoption imports",
        _SignalLookup(_dependency_signals(12, 13)),
        final_top_k=12,
    )

    promoted_paths = {
        item.chunk.file_path.as_posix()
        for item in promoted[:12]
        if item.score_parts.get("planner_dependency_hint_promotion", 0.0) > 0
    }
    assert promoted_paths == {"src/module_12.py"}


def test_semantic_import_hint_fallback_rejects_unanchored_source_identity() -> None:
    source = _ranked("source-chunk-12", "src/source_12.py", 0.80)
    ranked = [source, *[_dependency_ranked(index) for index in range(13)]]
    plan = QueryPlan(
        original_query="trace runtime fallback",
        status="ok",
        dependency_intent="follow_imports",
        imported_symbol_hints=["runtime_fallback"],
    )
    observations: list[dict[str, object]] = []

    unchanged = ranking.apply_planner_dependency_hint_promotions(
        ranked,
        {"chunk-12": _dependency_candidate(12)},
        plan,
        "trace runtime fallback",
        _SignalLookup(_dependency_signals(12)),
        final_top_k=12,
        observation_callback=observations.append,
    )

    assert unchanged == sorted(ranked, key=ranking._ranked_chunk_sort_key)
    assert observations == [
        _promotion_observation("no_eligible_closed_candidate")
    ]


def test_source_hint_promotion_is_input_order_independent_and_idempotent() -> None:
    ranked = [_dependency_ranked(index) for index in range(16)]
    candidate_items = [
        (f"chunk-{index:02d}", _dependency_candidate(index))
        for index in (12, 13, 14, 15)
    ]
    plan = QueryPlan(
        original_query="trace imports",
        status="ok",
        dependency_intent="follow_imports",
        source_module_hints=["SOURCE_12", "source_13", "source_14", "source_15"],
    )
    signal_lookup = _SignalLookup(_dependency_signals(12, 13, 14, 15))
    repeated_observations: list[dict[str, object]] = []

    canonical = ranking.apply_planner_dependency_hint_promotions(
        ranked,
        dict(candidate_items),
        plan,
        "trace imports",
        signal_lookup,
        final_top_k=12,
    )
    reversed_order = ranking.apply_planner_dependency_hint_promotions(
        list(reversed(ranked)),
        dict(reversed(candidate_items)),
        plan,
        "trace imports",
        signal_lookup,
        final_top_k=12,
    )
    repeated = ranking.apply_planner_dependency_hint_promotions(
        canonical,
        dict(candidate_items),
        plan,
        "trace imports",
        signal_lookup,
        final_top_k=12,
        observation_callback=repeated_observations.append,
    )

    expected_paths = [item.chunk.file_path for item in canonical]
    assert [item.chunk.file_path for item in reversed_order] == expected_paths
    assert repeated == canonical
    assert repeated_observations == [
        _promotion_observation("no_eligible_closed_candidate")
    ]
    promoted_paths = {
        item.chunk.file_path.as_posix()
        for item in canonical
        if item.score_parts.get("planner_dependency_hint_promotion", 0.0) > 0
    }
    assert promoted_paths == {"src/module_12.py", "src/module_13.py"}
