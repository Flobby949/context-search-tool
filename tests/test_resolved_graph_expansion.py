from __future__ import annotations

import importlib
import logging
import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest

from context_search_tool.config import DEFAULT_CONFIG
from context_search_tool.graph_contract import RELATION_WEIGHTS
from context_search_tool.graph_lifecycle import GRAPH_RESOLUTION_STATE_KEY
from context_search_tool.models import (
    CodeRelation,
    CodeSignal,
    DocumentChunk,
    RetrievalCandidate,
    SymbolRef,
)
from context_search_tool.retrieval_core import expansion, ranking, relation_policy
from context_search_tool.retrieval_trace import RetrievalTraceCollector
from context_search_tool.sqlite_store import SQLiteStore


retrieval = importlib.import_module("context_search_tool.retrieval")


_GRAPH_KEY_BY_KIND = {
    "calls": "graph_calls_match",
    "implements": "graph_implements_match",
    "implements_method": "graph_implements_match",
    "uses_type": "graph_uses_type_match",
    "imports": "graph_imports_match",
    "routes_to": "graph_routes_to_match",
    "mapped_by": "graph_mapped_by_match",
    "tests": "graph_tests_match",
}


def _chunk(chunk_id: str, path: str, content: str | None = None) -> DocumentChunk:
    return DocumentChunk(
        chunk_id=chunk_id,
        file_path=Path(path),
        start_line=1,
        end_line=10,
        content=content or f"content {chunk_id}",
        chunk_type="symbol",
        lexical_tokens=(content or chunk_id).lower().split(),
        embedding_id=chunk_id,
        metadata={"language": "java", "project_root": ""},
    )


def _signal(
    signal_id: str,
    chunk_id: str,
    path: str,
    *,
    kind: str = "method",
    producer: str = "java_ast",
) -> CodeSignal:
    return CodeSignal(
        signal_id=signal_id,
        chunk_id=chunk_id,
        file_path=Path(path),
        kind=kind,
        name=signal_id,
        qualified_name=f"demo.{signal_id}",
        signature="()" if kind == "method" else "",
        arity=0 if kind == "method" else None,
        project_unit_key="",
        producer=producer,
        start_line=2,
        end_line=3,
        start_column=0,
        end_column=4,
        language="java",
        recallable=kind != "module",
        tokens=[signal_id.lower()],
    )


def _module(signal_id: str, chunk_id: str, path: str) -> CodeSignal:
    return _signal(
        signal_id,
        chunk_id,
        path,
        kind="module",
        producer="core_module",
    )


def _relation(
    relation_id: str,
    source: CodeSignal,
    target: CodeSignal,
    kind: str,
    *,
    confidence: float = 0.9,
    resolution: str = "resolved_exact",
) -> CodeRelation:
    resolved = resolution in {"resolved_exact", "resolved_unique"}
    return CodeRelation(
        relation_id=relation_id,
        source_signal_id=source.signal_id,
        target_name=target.name,
        kind=kind,
        confidence=confidence,
        target_kind=target.kind,
        target_qualified_name=target.qualified_name,
        target_signature=target.signature,
        target_arity=target.arity,
        target_project_unit_key=target.project_unit_key,
        target_signal_id=target.signal_id if resolved else "",
        resolution=resolution,
        producer="test_graph",
        producer_confidence=confidence,
        resolution_confidence=1.0 if resolved else None,
    )


def _new_store(tmp_path: Path) -> SQLiteStore:
    store = SQLiteStore(tmp_path / ".context-search" / "index.sqlite")
    store.initialize_v5()
    return store


def _add_node_file(
    store: SQLiteStore,
    *,
    path: str,
    chunk_id: str,
    signal_id: str,
    content: str | None = None,
) -> tuple[DocumentChunk, CodeSignal, CodeSignal]:
    chunk = _chunk(chunk_id, path, content)
    module = _module(f"module-{signal_id}", chunk_id, path)
    signal = _signal(signal_id, chunk_id, path)
    store.replace_chunks(chunk.file_path, [chunk])
    store.replace_graph_facts(chunk.file_path, [module, signal], [])
    return chunk, module, signal


def _ready(store: SQLiteStore) -> None:
    store.mark_graph_ready(topology_fingerprint="a" * 64)


def _seed(chunk_id: str, score: float = 1.0) -> RetrievalCandidate:
    return RetrievalCandidate(
        chunk_id=chunk_id,
        score=score,
        source="signal",
        score_parts={"signal": score},
    )


@pytest.mark.parametrize(
    ("kind", "allows_outgoing", "allows_incoming"),
    [
        ("calls", True, False),
        ("implements", True, True),
        ("implements_method", True, True),
        ("uses_type", True, False),
        ("imports_type", False, False),
        ("imports", True, False),
        ("routes_to", True, False),
        ("mapped_by", True, True),
    ],
)
def test_ready_resolved_directions_reach_the_correct_neighbor(
    tmp_path: Path,
    kind: str,
    allows_outgoing: bool,
    allows_incoming: bool,
) -> None:
    store = _new_store(tmp_path)
    source_chunk, _source_module, source = _add_node_file(
        store,
        path="src/Source.java",
        chunk_id="source-chunk",
        signal_id="source",
    )
    target_chunk, _target_module, target = _add_node_file(
        store,
        path="src/Target.java",
        chunk_id="target-chunk",
        signal_id="target",
    )
    store.replace_graph_facts(
        source_chunk.file_path,
        [_module("module-source", source.chunk_id, source_chunk.file_path.as_posix()), source],
        [_relation("edge", source, target, kind)],
    )
    _ready(store)

    with store.graph_read_session() as session:
        outgoing = expansion.relation_candidates(
            store,
            [_seed(source_chunk.chunk_id)],
            DEFAULT_CONFIG,
            graph_session=session,
            test_intent=False,
        )
        incoming = expansion.relation_candidates(
            store,
            [_seed(target_chunk.chunk_id)],
            DEFAULT_CONFIG,
            graph_session=session,
            test_intent=False,
        )

    assert [item.chunk_id for item in outgoing] == (
        [target_chunk.chunk_id] if allows_outgoing else []
    )
    assert [item.chunk_id for item in incoming] == (
        [source_chunk.chunk_id] if allows_incoming else []
    )
    for candidate in [*outgoing, *incoming]:
        graph_keys = set(candidate.score_parts).intersection(
            relation_policy.GRAPH_SCORE_KEYS
        )
        assert graph_keys == {_GRAPH_KEY_BY_KIND[kind]}
        assert candidate.score_parts["resolved_relation"] == 1.0
        assert candidate.score_parts["graph_seed_original"] == 1.0
        assert "graph_seed_planner" not in candidate.score_parts
        assert not {"relation", "original_relation", "planner_relation"}.intersection(
            candidate.score_parts
        )
        expected = 0.9 * float(RELATION_WEIGHTS[kind]) * 0.8
        assert candidate.score == pytest.approx(expected)
        assert candidate.score_parts[_GRAPH_KEY_BY_KIND[kind]] == pytest.approx(
            expected
        )


def test_tests_edges_require_exact_test_intent_in_both_directions(
    tmp_path: Path,
) -> None:
    store = _new_store(tmp_path)
    test_chunk, _test_module, test_signal = _add_node_file(
        store,
        path="src/test/OrderTests.java",
        chunk_id="test-chunk",
        signal_id="test-source",
    )
    prod_chunk, _prod_module, prod_signal = _add_node_file(
        store,
        path="src/main/Order.java",
        chunk_id="prod-chunk",
        signal_id="prod-target",
    )
    store.replace_graph_facts(
        test_chunk.file_path,
        [_module("module-test", test_signal.chunk_id, test_chunk.file_path.as_posix()), test_signal],
        [_relation("tests-edge", test_signal, prod_signal, "tests")],
    )
    _ready(store)

    with store.graph_read_session() as session:
        assert expansion.relation_candidates(
            store,
            [_seed(test_chunk.chunk_id)],
            DEFAULT_CONFIG,
            graph_session=session,
            test_intent=False,
        ) == []
        assert expansion.relation_candidates(
            store,
            [_seed(prod_chunk.chunk_id)],
            DEFAULT_CONFIG,
            graph_session=session,
            test_intent=False,
        ) == []
        outgoing = expansion.relation_candidates(
            store,
            [_seed(test_chunk.chunk_id)],
            DEFAULT_CONFIG,
            graph_session=session,
            test_intent=True,
        )
        incoming = expansion.relation_candidates(
            store,
            [_seed(prod_chunk.chunk_id)],
            DEFAULT_CONFIG,
            graph_session=session,
            test_intent=True,
        )

    assert [item.chunk_id for item in outgoing] == [prod_chunk.chunk_id]
    assert [item.chunk_id for item in incoming] == [test_chunk.chunk_id]


def test_stale_and_nonresolved_graph_rows_admit_nothing(tmp_path: Path) -> None:
    store = _new_store(tmp_path)
    source_chunk, _source_module, source = _add_node_file(
        store,
        path="src/Source.java",
        chunk_id="source-chunk",
        signal_id="source",
    )
    _target_chunk, _target_module, target = _add_node_file(
        store,
        path="src/Target.java",
        chunk_id="target-chunk",
        signal_id="target",
    )
    store.replace_graph_facts(
        source_chunk.file_path,
        [_module("module-source", source.chunk_id, source_chunk.file_path.as_posix()), source],
        [_relation("edge", source, target, "calls", resolution="ambiguous")],
    )
    _ready(store)

    with store.graph_read_session() as session:
        assert expansion.relation_candidates(
            store,
            [_seed(source_chunk.chunk_id)],
            DEFAULT_CONFIG,
            graph_session=session,
            test_intent=False,
        ) == []

    store.mark_graph_stale("stale_on_entry")
    with store.graph_read_session() as session:
        assert expansion.relation_candidates(
            store,
            [_seed(source_chunk.chunk_id)],
            DEFAULT_CONFIG,
            graph_session=session,
            test_intent=False,
        ) == []


def test_ready_explicit_legacy_row_uses_only_name_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _new_store(tmp_path)
    source_chunk, source_module, source = _add_node_file(
        store,
        path="src/Source.java",
        chunk_id="source-chunk",
        signal_id="source",
    )
    target_chunk = replace(
        _chunk("target-chunk", "src/LegacyTarget.java"),
        symbols=[
            SymbolRef(
                name="LegacyTarget",
                kind="class",
                start_line=1,
                end_line=10,
                language="java",
            )
        ],
    )
    target_module = _module(
        "target-module",
        target_chunk.chunk_id,
        target_chunk.file_path.as_posix(),
    )
    target = _signal(
        "LegacyTarget",
        target_chunk.chunk_id,
        target_chunk.file_path.as_posix(),
    )
    store.replace_chunks(target_chunk.file_path, [target_chunk])
    store.replace_graph_facts(target_chunk.file_path, [target_module, target], [])
    store.replace_graph_facts(
        source_chunk.file_path,
        [source_module, source],
        [_relation("legacy-edge", source, target, "uses", resolution="legacy")],
    )
    _ready(store)

    def forbidden(*_args, **_kwargs):
        raise AssertionError("ready legacy fallback reopened SQLiteStore")

    monkeypatch.setattr(SQLiteStore, "signals_for_chunks", forbidden)
    monkeypatch.setattr(SQLiteStore, "relations_for_sources", forbidden)
    monkeypatch.setattr(
        SQLiteStore,
        "chunks_matching_signal_or_symbols",
        forbidden,
    )

    with store.graph_read_session() as session:
        expanded = expansion.relation_candidates(
            store,
            [_seed(source_chunk.chunk_id)],
            DEFAULT_CONFIG,
            graph_session=session,
        )

    assert [candidate.chunk_id for candidate in expanded] == [
        target_chunk.chunk_id
    ]
    assert expanded[0].score_parts == {
        "relation": pytest.approx(0.72),
        "original_relation": pytest.approx(0.72),
    }
    assert not set(expanded[0].score_parts).intersection(
        relation_policy.GRAPH_SCORE_KEYS
    )


def test_legacy_session_keeps_three_hop_outgoing_behavior(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / ".context-search" / "index.sqlite")
    store.initialize()
    chunks = [
        replace(
            _chunk(f"chunk-{index}", f"src/Node{index}.java"),
            symbols=[
                SymbolRef(
                    name=f"Node{index}",
                    kind="class",
                    start_line=1,
                    end_line=10,
                    language="java",
                )
            ],
        )
        for index in range(5)
    ]
    signals = [
        _signal(
            f"Node{index}",
            chunk.chunk_id,
            chunk.file_path.as_posix(),
            producer="legacy",
        )
        for index, chunk in enumerate(chunks)
    ]
    for chunk, signal in zip(chunks, signals):
        store.replace_chunks(chunk.file_path, [chunk])
        store.replace_signals(chunk.file_path, [signal])
    for index in range(4):
        store.replace_relations(
            chunks[index].file_path,
            [
                _relation(
                    f"legacy-{index}",
                    signals[index],
                    signals[index + 1],
                    "uses",
                    resolution="legacy",
                )
            ],
        )

    with store.graph_read_session() as session:
        expanded = expansion.relation_candidates(
            store,
            [_seed(chunks[0].chunk_id)],
            DEFAULT_CONFIG,
            graph_session=session,
        )

    assert [candidate.chunk_id for candidate in expanded] == [
        "chunk-1",
        "chunk-2",
        "chunk-3",
    ]


def test_later_chunk_promotes_its_file_module_into_the_frontier(
    tmp_path: Path,
) -> None:
    store = _new_store(tmp_path)
    first = _chunk("first", "src/Long.java", "first chunk")
    second = _chunk("second", "src/Long.java", "needle second chunk")
    module = _module("long-module", first.chunk_id, first.file_path.as_posix())
    local = _signal("local", second.chunk_id, second.file_path.as_posix())
    target_chunk, _target_module, target = _add_node_file(
        store,
        path="src/Target.java",
        chunk_id="target",
        signal_id="target-signal",
    )
    store.replace_chunks(first.file_path, [first, second])
    store.replace_graph_facts(
        first.file_path,
        [module, local],
        [_relation("module-import", module, target, "imports")],
    )
    _ready(store)

    with store.graph_read_session() as session:
        expanded = expansion.relation_candidates(
            store,
            [_seed(second.chunk_id)],
            DEFAULT_CONFIG,
            graph_session=session,
            test_intent=False,
        )

    assert [item.chunk_id for item in expanded] == [target_chunk.chunk_id]
    assert expanded[0].score_parts["graph_imports_match"] > 0


def test_graph_merge_does_not_mutate_a_protected_direct_candidate(
    tmp_path: Path,
) -> None:
    store = _new_store(tmp_path)
    source_chunk, _source_module, source = _add_node_file(
        store,
        path="src/Source.java",
        chunk_id="source",
        signal_id="source-signal",
    )
    target_chunk, _target_module, target = _add_node_file(
        store,
        path="src/Target.java",
        chunk_id="target",
        signal_id="target-signal",
    )
    store.replace_graph_facts(
        source_chunk.file_path,
        [_module("module-source", source.chunk_id, source_chunk.file_path.as_posix()), source],
        [_relation("edge", source, target, "calls")],
    )
    _ready(store)
    protected = RetrievalCandidate(
        chunk_id=target_chunk.chunk_id,
        score=0.8,
        source="direct_text",
        score_parts={"direct_text": 0.8},
    )
    seeds = [_seed(source_chunk.chunk_id), protected]
    protected_ids = ranking.protected_direct_chunk_ids(store, seeds, [])

    with store.graph_read_session() as session:
        graph = expansion.relation_candidates(
            store,
            seeds,
            DEFAULT_CONFIG,
            graph_session=session,
            test_intent=False,
            protected_chunk_ids=protected_ids,
        )

    merged = retrieval.candidates.merge_candidates([protected, *graph])
    assert target_chunk.chunk_id not in {item.chunk_id for item in graph}
    assert merged[target_chunk.chunk_id] == protected


def test_private_v5_query_keeps_a_protected_direct_result_graph_free(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    source_path = repo / "src" / "Source.java"
    target_path = repo / "src" / "TargetServiceImpl.java"
    source_path.parent.mkdir()
    source_path.write_text("NeedleTarget source\n", encoding="utf-8")
    target_path.write_text(
        "NeedleTarget TargetServiceImpl direct body\n",
        encoding="utf-8",
    )
    store = SQLiteStore(repo / ".context-search" / "index.sqlite")
    store.initialize_v5()
    source_chunk = _chunk(
        "source",
        "src/Source.java",
        "NeedleTarget source",
    )
    source_module = _module("module-source", "source", "src/Source.java")
    source = _signal("NeedleTarget", "source", "src/Source.java")
    target_chunk = _chunk(
        "target",
        "src/TargetServiceImpl.java",
        "NeedleTarget TargetServiceImpl direct body",
    )
    target_module = _module(
        "module-target",
        "target",
        "src/TargetServiceImpl.java",
    )
    target = _signal(
        "TargetServiceImpl",
        "target",
        "src/TargetServiceImpl.java",
    )
    store.replace_chunks(source_chunk.file_path, [source_chunk])
    store.replace_graph_facts(
        source_chunk.file_path,
        [source_module, source],
        [_relation("call", source, target, "calls")],
    )
    store.replace_chunks(target_chunk.file_path, [target_chunk])
    store.replace_graph_facts(target_chunk.file_path, [target_module, target], [])
    _ready(store)

    bundle = retrieval._query_repository_v5(
        repo,
        "NeedleTarget",
        DEFAULT_CONFIG,
        vector_snapshot_loader=lambda _repo, _config, _session: None,
    )

    result = next(
        item for item in bundle.results if item.file_path == target_chunk.file_path
    )
    assert result.score_parts["evidence_priority"] == 0.0
    assert "resolved_relation" not in result.score_parts
    assert not set(result.score_parts).intersection(relation_policy.GRAPH_SCORE_KEYS)
    assert not set(result.reasons).intersection(
        relation_policy.GRAPH_REASON_BY_SCORE_KEY.values()
    )
    assert "implementation chain match" not in result.reasons


def test_private_v5_query_uses_one_session_and_persists_dangling_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    source_path = repo / "src" / "Source.java"
    target_path = repo / "src" / "Target.java"
    source_path.parent.mkdir()
    source_path.write_text("needle source\n", encoding="utf-8")
    target_path.write_text("target body\n", encoding="utf-8")
    store = SQLiteStore(repo / ".context-search" / "index.sqlite")
    store.initialize_v5()
    source_chunk = _chunk("source", "src/Source.java", "needle source")
    source_module = _module("module-source", "source", "src/Source.java")
    source = _signal("needle", "source", "src/Source.java")
    target_chunk = _chunk("target", "src/Target.java", "target body")
    target_module = _module("module-target", "target", "src/Target.java")
    target = _signal("target-signal", "target", "src/Target.java")
    store.replace_chunks(source_chunk.file_path, [source_chunk])
    store.replace_graph_facts(
        source_chunk.file_path,
        [source_module, source],
        [_relation("dangling", source, target, "calls")],
    )
    store.replace_chunks(target_chunk.file_path, [target_chunk])
    store.replace_graph_facts(target_chunk.file_path, [target_module, target], [])
    _ready(store)
    with sqlite3.connect(store.db_path) as connection:
        connection.execute(
            "UPDATE code_signals SET deleted_at = 1 WHERE signal_id = ?",
            (target.signal_id,),
        )

    sessions: list[object] = []

    def session_factory():
        session = store.graph_read_session()
        sessions.append(session)
        return session

    bundle = retrieval._query_repository_v5(
        repo,
        "needle",
        DEFAULT_CONFIG,
        graph_session_factory=session_factory,
        vector_snapshot_loader=lambda _repo, _config, _session: None,
    )

    assert len(sessions) == 1
    assert bundle.results
    assert all(
        not set(result.score_parts).intersection(relation_policy.GRAPH_SCORE_KEYS)
        for result in bundle.results
    )
    assert all(result.score_parts.get("signal", 0.0) == 0 for result in bundle.results)
    assert store.get_metadata(GRAPH_RESOLUTION_STATE_KEY) == "stale"

    store.set_metadata(GRAPH_RESOLUTION_STATE_KEY, "ready")

    def read_only_write(*_args, **_kwargs):
        raise sqlite3.OperationalError("read only")

    monkeypatch.setattr(SQLiteStore, "mark_graph_stale", read_only_write)
    with caplog.at_level(logging.WARNING, logger="context_search_tool.retrieval"):
        fallback_bundle = retrieval._query_repository_v5(
            repo,
            "needle",
            DEFAULT_CONFIG,
            vector_snapshot_loader=lambda _repo, _config, _session: None,
        )

    assert fallback_bundle.results
    assert "dangling_target" in caplog.text


def test_private_v5_query_exposes_one_resolved_adjustment_and_reason(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    source_path = repo / "src" / "Source.java"
    target_path = repo / "src" / "Target.java"
    source_path.parent.mkdir()
    source_path.write_text("needle source\n", encoding="utf-8")
    target_path.write_text("target implementation\n", encoding="utf-8")
    store = SQLiteStore(repo / ".context-search" / "index.sqlite")
    store.initialize_v5()
    source_chunk = _chunk("source", "src/Source.java", "needle source")
    source_module = _module("module-source", "source", "src/Source.java")
    source = _signal("needle", "source", "src/Source.java")
    target_chunk = _chunk("target", "src/Target.java", "target implementation")
    target_module = _module("module-target", "target", "src/Target.java")
    target = _signal("target-signal", "target", "src/Target.java")
    store.replace_chunks(source_chunk.file_path, [source_chunk])
    store.replace_graph_facts(
        source_chunk.file_path,
        [source_module, source],
        [_relation("call", source, target, "calls")],
    )
    store.replace_chunks(target_chunk.file_path, [target_chunk])
    store.replace_graph_facts(target_chunk.file_path, [target_module, target], [])
    _ready(store)
    collector = RetrievalTraceCollector()

    bundle = retrieval._query_repository_v5(
        repo,
        "needle",
        DEFAULT_CONFIG,
        trace_collector=collector,
        vector_snapshot_loader=lambda _repo, _config, _session: None,
    )

    result = next(item for item in bundle.results if item.file_path == target_chunk.file_path)
    assert result.score_parts["resolved_relation"] == 1.0
    assert result.score_parts["graph_seed_original"] == 1.0
    assert "graph_seed_planner" not in result.score_parts
    assert {
        key for key in relation_policy.GRAPH_SCORE_KEYS if key in result.score_parts
    } == {"graph_calls_match"}
    assert "resolved Java method call" in result.reasons
    assert any("relation" in span.sources for span in result.spans)
    trace_selection = next(
        item
        for item in collector.finished_trace().final_selections
        if item.file_path == target_chunk.file_path.as_posix()
    )
    adjustment_names = [item.name for item in trace_selection.adjustments]
    assert adjustment_names.count("graph_calls_match") == 1
    assert "resolved_relation" not in adjustment_names
    assert "graph_seed_original" not in adjustment_names


def test_planner_only_seed_sets_only_planner_graph_provenance(
    tmp_path: Path,
) -> None:
    store = _new_store(tmp_path)
    source_chunk, source_module, source = _add_node_file(
        store,
        path="src/Source.java",
        chunk_id="source",
        signal_id="source-signal",
    )
    target_chunk, _target_module, target = _add_node_file(
        store,
        path="src/Target.java",
        chunk_id="target",
        signal_id="target-signal",
    )
    store.replace_graph_facts(
        source_chunk.file_path,
        [source_module, source],
        [_relation("call", source, target, "calls")],
    )
    _ready(store)
    planner_seed = RetrievalCandidate(
        source_chunk.chunk_id,
        0.8,
        "planner_signal",
        {"planner_signal": 0.8},
    )

    with store.graph_read_session() as session:
        [expanded] = expansion.relation_candidates(
            store,
            [planner_seed],
            DEFAULT_CONFIG,
            graph_session=session,
        )

    assert expanded.chunk_id == target_chunk.chunk_id
    assert expanded.score_parts["graph_seed_planner"] == 1.0
    assert "graph_seed_original" not in expanded.score_parts
    assert "planner_relation" not in expanded.score_parts


def test_resolved_graph_stops_after_four_hops_and_handles_cycles(
    tmp_path: Path,
) -> None:
    store = _new_store(tmp_path)
    nodes = [
        _add_node_file(
            store,
            path=f"src/Node{index}.java",
            chunk_id=f"chunk-{index}",
            signal_id=f"signal-{index}",
        )
        for index in range(6)
    ]
    for index, (chunk, module, signal) in enumerate(nodes[:-1]):
        next_signal = nodes[index + 1][2]
        relations = [_relation(f"edge-{index}", signal, next_signal, "calls")]
        if index == 1:
            relations.append(_relation("cycle", signal, nodes[0][2], "calls"))
        store.replace_graph_facts(chunk.file_path, [module, signal], relations)
    _ready(store)

    with store.graph_read_session() as session:
        expanded = expansion.relation_candidates(
            store,
            [_seed(nodes[0][0].chunk_id)],
            DEFAULT_CONFIG,
            graph_session=session,
        )

    assert [candidate.chunk_id for candidate in expanded] == [
        "chunk-1",
        "chunk-2",
        "chunk-3",
        "chunk-4",
    ]
    assert not session.graph_truncated


def test_equal_score_fewer_hops_wins_complete_tuple_dominance(
    tmp_path: Path,
) -> None:
    store = _new_store(tmp_path)
    nodes = {
        name: _add_node_file(
            store,
            path=f"src/{name}.java",
            chunk_id=f"chunk-{name}",
            signal_id=f"signal-{name}",
        )
        for name in ("A", "B", "T", "U", "V", "W")
    }
    a_chunk, a_module, a_signal = nodes["A"]
    store.replace_graph_facts(
        a_chunk.file_path,
        [a_module, a_signal],
        [
            _relation("direct", a_signal, nodes["T"][2], "calls", confidence=0.5),
            _relation("via-b", a_signal, nodes["B"][2], "calls", confidence=0.625),
        ],
    )
    b_chunk, b_module, b_signal = nodes["B"]
    store.replace_graph_facts(
        b_chunk.file_path,
        [b_module, b_signal],
        [_relation("b-to-t", b_signal, nodes["T"][2], "calls", confidence=1.0)],
    )
    for source_name, target_name in (("T", "U"), ("U", "V"), ("V", "W")):
        chunk, module, signal = nodes[source_name]
        store.replace_graph_facts(
            chunk.file_path,
            [module, signal],
            [_relation(f"{source_name}-{target_name}", signal, nodes[target_name][2], "calls")],
        )
    _ready(store)

    with store.graph_read_session() as session:
        expanded = expansion.relation_candidates(
            store,
            [_seed(a_chunk.chunk_id)],
            DEFAULT_CONFIG,
            graph_session=session,
        )

    assert "chunk-W" in {candidate.chunk_id for candidate in expanded}
    target = next(candidate for candidate in expanded if candidate.chunk_id == "chunk-T")
    assert target.score == pytest.approx(0.5 * 0.8)


def test_per_direction_limit_retains_canonical_best_64(
    tmp_path: Path,
) -> None:
    store = _new_store(tmp_path)
    source_chunk, source_module, source = _add_node_file(
        store,
        path="src/Source.java",
        chunk_id="source",
        signal_id="source-signal",
    )
    targets = [
        _add_node_file(
            store,
            path=f"src/Target{index:02d}.java",
            chunk_id=f"target-{index:02d}",
            signal_id=f"target-signal-{index:02d}",
        )
        for index in range(66)
    ]
    relations = [
        _relation(
            f"edge-{index:02d}",
            source,
            target[2],
            "calls",
            confidence=0.5 + index / 200,
        )
        for index, target in reversed(list(enumerate(targets)))
    ]
    store.replace_graph_facts(
        source_chunk.file_path,
        [source_module, source],
        relations,
    )
    _ready(store)

    with store.graph_read_session() as session:
        expanded = expansion.relation_candidates(
            store,
            [_seed(source_chunk.chunk_id)],
            DEFAULT_CONFIG,
            graph_session=session,
        )

    assert len(expanded) == 64
    assert [candidate.chunk_id for candidate in expanded] == [
        f"target-{index:02d}" for index in range(65, 1, -1)
    ]
    assert session.graph_truncated


@pytest.mark.parametrize(
    "budget_name",
    ["MAX_SIGNALS_POPPED_PER_QUERY", "MAX_FRONTIER_ENTRIES_PER_QUERY"],
)
def test_global_signal_and_frontier_caps_stop_at_the_canonical_prefix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    budget_name: str,
) -> None:
    store = _new_store(tmp_path)
    chunks = [
        _chunk(f"chunk-{index}", f"src/Node{index}.java")
        for index in range(3)
    ]
    modules = [
        _module(
            f"module-{index}",
            chunk.chunk_id,
            chunk.file_path.as_posix(),
        )
        for index, chunk in enumerate(chunks)
    ]
    for index, (chunk, module) in enumerate(zip(chunks, modules)):
        store.replace_chunks(chunk.file_path, [chunk])
        relations = (
            [_relation(f"edge-{index}", module, modules[index + 1], "calls")]
            if index < 2
            else []
        )
        store.replace_graph_facts(chunk.file_path, [module], relations)
    _ready(store)
    monkeypatch.setattr(relation_policy, budget_name, 1)

    with store.graph_read_session() as session:
        expanded = expansion.relation_candidates(
            store,
            [_seed(chunks[0].chunk_id)],
            DEFAULT_CONFIG,
            graph_session=session,
        )

    assert [candidate.chunk_id for candidate in expanded] == ["chunk-1"]
    assert session.graph_truncated


def test_global_edge_cap_counts_and_retains_the_best_edge(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _new_store(tmp_path)
    source_chunk = _chunk("source", "src/Source.java")
    source = _module("source-module", "source", "src/Source.java")
    targets = [
        _add_node_file(
            store,
            path=f"src/Target{index}.java",
            chunk_id=f"target-{index}",
            signal_id=f"target-{index}-signal",
        )
        for index in range(2)
    ]
    store.replace_chunks(source_chunk.file_path, [source_chunk])
    store.replace_graph_facts(
        source_chunk.file_path,
        [source],
        [
            _relation("lower", source, targets[0][2], "calls", confidence=0.8),
            _relation("higher", source, targets[1][2], "calls", confidence=0.9),
        ],
    )
    _ready(store)
    monkeypatch.setattr(relation_policy, "MAX_EDGES_EXAMINED_PER_QUERY", 1)

    with store.graph_read_session() as session:
        expanded = expansion.relation_candidates(
            store,
            [_seed(source_chunk.chunk_id)],
            DEFAULT_CONFIG,
            graph_session=session,
        )

    assert [candidate.chunk_id for candidate in expanded] == ["target-1"]
    assert session.graph_truncated


def test_seed_and_candidate_caps_return_the_canonical_prefix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _new_store(tmp_path)
    source = _chunk("source", "src/Source.java")
    module = replace(
        _module("module", source.chunk_id, source.file_path.as_posix()),
        start_line=1,
        end_line=1,
    )
    source_signals = [
        replace(
            _signal(
                f"source-{index}",
                source.chunk_id,
                source.file_path.as_posix(),
            ),
            start_line=index + 2,
            end_line=index + 2,
        )
        for index in range(4)
    ]
    targets = [
        _add_node_file(
            store,
            path=f"src/Target{index}.java",
            chunk_id=f"target-{index}",
            signal_id=f"target-{index}-signal",
        )
        for index in range(5)
    ]
    store.replace_chunks(source.file_path, [source])
    store.replace_graph_facts(
        source.file_path,
        [module, *source_signals],
        [
            _relation("module-edge", module, targets[0][2], "imports"),
            *[
                _relation(
                    f"source-edge-{index}",
                    signal,
                    targets[index + 1][2],
                    "calls",
                )
                for index, signal in enumerate(source_signals)
            ],
        ],
    )
    _ready(store)
    monkeypatch.setattr(relation_policy, "MAX_GRAPH_SEED_SIGNALS", 2)
    monkeypatch.setattr(relation_policy, "MAX_RELATION_EXPANDED_CANDIDATES", 2)

    with store.graph_read_session() as session:
        expanded = expansion.relation_candidates(
            store,
            [_seed(source.chunk_id)],
            DEFAULT_CONFIG,
            graph_session=session,
        )

    assert [candidate.chunk_id for candidate in expanded] == [
        "target-1",
        "target-0",
    ]
    assert session.graph_truncated
