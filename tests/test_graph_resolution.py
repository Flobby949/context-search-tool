from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

import context_search_tool.sqlite_store as sqlite_store
from context_search_tool.config import DEFAULT_CONFIG
from context_search_tool.frontend_graph import FrontendGraphProducer
from context_search_tool.graph_resolution import resolve_graph_relations
from context_search_tool.indexer import build_v5_index_snapshot
from context_search_tool.models import CodeRelation, CodeSignal, DocumentChunk
from context_search_tool.scanner import scan_workspace_v5
from context_search_tool.sqlite_store import SQLiteStore


def _store(tmp_path: Path) -> SQLiteStore:
    path = tmp_path / "index.sqlite"
    store = SQLiteStore(path)
    store.initialize()
    store.set_metadata("signal_schema_version", "4")
    store.migrate_signal_schema_v5()
    return store


def _chunk(chunk_id: str, file_path: str) -> DocumentChunk:
    return DocumentChunk(
        chunk_id=chunk_id,
        file_path=Path(file_path),
        start_line=1,
        end_line=20,
        content=chunk_id,
        chunk_type="symbol",
        embedding_id=chunk_id,
    )


def _signal(
    signal_id: str,
    chunk_id: str,
    file_path: str,
    *,
    kind: str,
    qualified_name: str,
    signature: str = "",
    arity: int | None = None,
    unit: str = "",
    language: str = "java",
    producer: str = "java_ast",
) -> CodeSignal:
    return CodeSignal(
        signal_id=signal_id,
        chunk_id=chunk_id,
        file_path=Path(file_path),
        kind=kind,
        name=qualified_name,
        qualified_name=qualified_name,
        signature=signature,
        arity=arity,
        project_unit_key=unit,
        producer=producer,
        start_line=2,
        end_line=3,
        start_column=1,
        end_column=5,
        language=language,
        recallable=kind != "module",
    )


def _add_file(
    store: SQLiteStore,
    file_path: str,
    signals: list[CodeSignal],
    relations: list[CodeRelation] | None = None,
) -> None:
    chunk_id = signals[0].chunk_id
    store.replace_chunks(Path(file_path), [_chunk(chunk_id, file_path)])
    store.replace_graph_facts(Path(file_path), signals, relations or [])


def _module(signal_id: str, chunk_id: str, file_path: str, unit: str = "") -> CodeSignal:
    return _signal(
        signal_id,
        chunk_id,
        file_path,
        kind="module",
        qualified_name=file_path,
        unit=unit,
        producer="core_module",
        language="typescript",
    )


def _source(store: SQLiteStore, *, unit: str = "") -> None:
    _add_file(
        store,
        "src/Source.ts",
        [_module("source", "source-chunk", "src/Source.ts", unit)],
    )


def test_exact_module_and_complete_candidate_set_resolution(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _source(store)
    _add_file(
        store,
        "src/Page.ts",
        [_module("page", "page-chunk", "src/Page.ts")],
    )
    relations = [
        CodeRelation(
            relation_id="exact",
            source_signal_id="source",
            target_name="src/Page.ts",
            kind="imports",
            confidence=0.85,
            target_kind="module",
            target_qualified_name="src/Page.ts",
            target_project_unit_key="",
            resolution="unresolved",
            producer="frontend_ast",
            producer_confidence=0.85,
            metadata={
                "selector_state": "exact",
                "candidates": ["src/Page.ts"],
            },
        ),
        CodeRelation(
            relation_id="candidate",
            source_signal_id="source",
            target_name="src/Page",
            kind="imports",
            confidence=0.85,
            target_kind="module",
            target_qualified_name="src/Page",
            target_project_unit_key="",
            resolution="unresolved",
            producer="frontend_ast",
            producer_confidence=0.85,
            metadata={
                "selector_state": "candidates",
                "candidates": ["src/Page", "src/Page.ts", "src/Page.js"],
            },
        ),
    ]
    store.append_graph_relations(relations)

    assert resolve_graph_relations(store) == 2

    exact = store.graph_relation_for_id("exact")
    candidate = store.graph_relation_for_id("candidate")
    assert exact is not None
    assert exact.resolution == "resolved_exact"
    assert exact.target_signal_id == "page"
    assert exact.resolution_confidence == 1.0
    assert exact.confidence == 0.85
    assert candidate is not None
    assert candidate.resolution == "resolved_unique"
    assert candidate.target_signal_id == "page"
    assert candidate.resolution_confidence == 0.9


def test_empty_scanned_module_candidate_inventory_never_uses_stale_target(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    _source(store)
    _add_file(
        store,
        "src/Page.ts",
        [_module("page", "page-chunk", "src/Page.ts")],
    )
    store.append_graph_relations(
        [
            CodeRelation(
                relation_id="inactive-exact",
                source_signal_id="source",
                target_name="src/Page.ts",
                kind="imports",
                confidence=1.0,
                target_kind="module",
                target_qualified_name="src/Page.ts",
                resolution="unresolved",
                producer="frontend_graph",
                producer_confidence=1.0,
                metadata={"selector_state": "exact", "candidates": []},
            )
        ]
    )

    resolve_graph_relations(store)

    relation = store.graph_relation_for_id("inactive-exact")
    assert relation is not None
    assert relation.resolution == "unresolved"
    assert relation.target_signal_id == ""


def test_candidate_tie_is_ambiguous_independent_of_insertion_order(
    tmp_path: Path,
) -> None:
    states: list[tuple[str, str, float | None]] = []
    for case, paths in enumerate(
        [
            ("src/View.ts", "src/View.js"),
            ("src/View.js", "src/View.ts"),
        ]
    ):
        case_dir = tmp_path / str(case)
        case_dir.mkdir()
        store = _store(case_dir)
        _source(store)
        for index, path in enumerate(paths):
            _add_file(
                store,
                path,
                [_module(f"target-{index}", f"chunk-{index}", path)],
            )
        store.append_graph_relations(
            [
                CodeRelation(
                    relation_id="tie",
                    source_signal_id="source",
                    target_name="src/View",
                    kind="imports",
                    confidence=0.85,
                    target_kind="module",
                    target_qualified_name="src/View",
                    resolution="unresolved",
                    producer="frontend_ast",
                    producer_confidence=0.85,
                    metadata={
                        "selector_state": "candidates",
                        "candidates": ["src/View", "src/View.ts", "src/View.js"],
                    },
                )
            ]
        )

        resolve_graph_relations(store)
        relation = store.graph_relation_for_id("tie")
        assert relation is not None
        states.append(
            (
                relation.resolution,
                relation.target_signal_id,
                relation.resolution_confidence,
            )
        )

    assert states == [("ambiguous", "", None), ("ambiguous", "", None)]


def test_exact_signature_and_unique_arity_stay_inside_source_unit(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    _source(store, unit="app")
    app_path = "app/src/Service.java"
    other_path = "other/src/Service.java"
    app_module = _module("app-module", "app-chunk", app_path, "app")
    app_exact = _signal(
        "app-exact",
        "app-chunk",
        app_path,
        kind="method",
        qualified_name="demo.Service.run",
        signature="(java.lang.String)",
        arity=1,
        unit="app",
    )
    app_other_arity = _signal(
        "app-zero",
        "app-chunk",
        app_path,
        kind="method",
        qualified_name="demo.Service.run",
        signature="()",
        arity=0,
        unit="app",
    )
    _add_file(store, app_path, [app_module, app_exact, app_other_arity])
    _add_file(
        store,
        other_path,
        [
            _module("other-module", "other-chunk", other_path, "other"),
            _signal(
                "other-exact",
                "other-chunk",
                other_path,
                kind="method",
                qualified_name="demo.Service.run",
                signature="(java.lang.String)",
                arity=1,
                unit="other",
            ),
        ],
    )
    store.append_graph_relations(
        [
            CodeRelation(
                relation_id="signature",
                source_signal_id="source",
                target_name="demo.Service.run",
                kind="calls",
                confidence=0.7,
                target_kind="method",
                target_qualified_name="demo.Service.run",
                target_signature="(java.lang.String)",
                target_arity=1,
                target_project_unit_key="app",
                resolution="unresolved",
                producer="java_ast",
                producer_confidence=0.7,
            ),
            CodeRelation(
                relation_id="arity",
                source_signal_id="source",
                target_name="demo.Service.run",
                kind="calls",
                confidence=0.8,
                target_kind="method",
                target_qualified_name="demo.Service.run",
                target_arity=0,
                target_project_unit_key="app",
                resolution="unresolved",
                producer="java_ast",
                producer_confidence=0.8,
            ),
            CodeRelation(
                relation_id="cross-unit",
                source_signal_id="source",
                target_name="demo.Service.run",
                kind="calls",
                confidence=0.8,
                target_kind="method",
                target_qualified_name="demo.Service.run",
                target_signature="(java.lang.String)",
                target_arity=1,
                target_project_unit_key="other",
                resolution="unresolved",
                producer="java_ast",
                producer_confidence=0.8,
            ),
        ]
    )

    resolve_graph_relations(store)

    signature = store.graph_relation_for_id("signature")
    arity = store.graph_relation_for_id("arity")
    assert signature is not None and signature.target_signal_id == "app-exact"
    assert signature.resolution == "resolved_exact"
    assert signature.confidence == 0.7
    assert arity is not None and arity.target_signal_id == "app-zero"
    assert arity.resolution == "resolved_unique"
    assert arity.confidence == 0.8
    cross_unit = store.graph_relation_for_id("cross-unit")
    assert cross_unit is not None
    assert cross_unit.resolution == "unresolved"
    assert cross_unit.target_signal_id == ""


def test_external_unresolved_and_escape_states_never_gain_target_ids(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    _source(store)
    selectors = [
        ("external", "external"),
        ("escape", "unresolved"),
        ("missing", "unresolved"),
    ]
    store.append_graph_relations(
        [
            CodeRelation(
                relation_id=relation_id,
                source_signal_id="source",
                target_name=relation_id,
                kind="imports",
                confidence=0.85,
                target_kind="module",
                target_qualified_name=relation_id,
                resolution="resolved_exact",
                target_signal_id="old-target",
                resolution_confidence=0.1,
                producer="frontend_ast",
                producer_confidence=0.85,
                metadata={"selector_state": selector_state, "candidates": []},
            )
            for relation_id, selector_state in selectors
        ]
    )

    resolve_graph_relations(store)

    assert [
        (
            store.graph_relation_for_id(relation_id).resolution,
            store.graph_relation_for_id(relation_id).target_signal_id,
            store.graph_relation_for_id(relation_id).resolution_confidence,
        )
        for relation_id, _state in selectors
    ] == [
        ("external", "", None),
        ("unresolved", "", None),
        ("unresolved", "", None),
    ]


def test_reresolution_clears_prior_target_without_confidence_compounding(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    _source(store)
    path = "src/Page.ts"
    _add_file(store, path, [_module("page", "page-chunk", path)])
    store.append_graph_relations(
        [
            CodeRelation(
                relation_id="route",
                source_signal_id="source",
                target_name=path,
                kind="routes_to",
                confidence=0.2,
                target_kind="module",
                target_qualified_name=path,
                target_signal_id="stale-target",
                resolution="resolved_unique",
                producer="frontend_ast",
                producer_confidence=0.6,
                resolution_confidence=0.3,
                metadata={"selector_state": "exact", "candidates": [path]},
            )
        ]
    )

    resolve_graph_relations(store)
    first = store.graph_relation_for_id("route")
    assert first is not None
    assert first.target_signal_id == "page"
    assert first.confidence == 0.6

    with sqlite3.connect(store.db_path) as connection:
        connection.execute(
            "UPDATE code_signals SET deleted_at = 1 WHERE signal_id = 'page'"
        )
    resolve_graph_relations(store)
    second = store.graph_relation_for_id("route")
    assert second is not None
    assert second.resolution == "unresolved"
    assert second.target_signal_id == ""
    assert second.resolution_confidence is None
    assert second.confidence == 0.6


def test_resolver_failure_rolls_back_every_update(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _store(tmp_path)
    _source(store)
    _add_file(
        store,
        "src/Page.ts",
        [_module("page", "page-chunk", "src/Page.ts")],
    )
    relations = [
        CodeRelation(
            relation_id=f"relation-{index}",
            source_signal_id="source",
            target_name="src/Page.ts",
            kind="imports",
            confidence=0.85,
            target_kind="module",
            target_qualified_name="src/Page.ts",
            resolution="unresolved",
            producer="frontend_ast",
            producer_confidence=0.85,
            metadata={
                "selector_state": "exact",
                "candidates": ["src/Page.ts"],
            },
        )
        for index in range(2)
    ]
    store.append_graph_relations(relations)
    original = sqlite_store._SQLiteResolutionSession.update_relation
    calls = 0

    def fail_second(session, relation):
        nonlocal calls
        calls += 1
        original(session, relation)
        if calls == 2:
            raise RuntimeError("resolver fault")

    monkeypatch.setattr(
        sqlite_store._SQLiteResolutionSession,
        "update_relation",
        fail_second,
    )

    with pytest.raises(RuntimeError, match="resolver fault"):
        resolve_graph_relations(store)

    assert [
        store.graph_relation_for_id(relation.relation_id).resolution
        for relation in relations
    ] == ["unresolved", "unresolved"]


def test_java_complete_candidate_set_is_unique_or_ambiguous(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    _source(store, unit="app")
    first_path = "app/src/First.java"
    second_path = "app/src/Second.java"
    _add_file(
        store,
        first_path,
        [
            _module("first-module", "first-chunk", first_path, "app"),
            _signal(
                "first-method",
                "first-chunk",
                first_path,
                kind="method",
                qualified_name="one.Api.run",
                signature="(demo.Dto)",
                arity=1,
                unit="app",
            ),
        ],
    )
    relations = [
        CodeRelation(
            relation_id="candidate-method",
            source_signal_id="source",
            target_name="Api.run",
            kind="implements_method",
            confidence=1.0,
            target_kind="method",
            target_qualified_name="",
            target_signature="(demo.Dto)",
            target_arity=1,
            target_project_unit_key="app",
            resolution="unresolved",
            producer="java_ast",
            producer_confidence=1.0,
            metadata={
                "selector_state": "candidates",
                "candidates": ["one.Api.run", "two.Api.run"],
            },
        )
    ]
    store.append_graph_relations(relations)

    resolve_graph_relations(store)
    unique = store.graph_relation_for_id("candidate-method")
    assert unique is not None
    assert unique.resolution == "resolved_unique"
    assert unique.target_signal_id == "first-method"
    assert unique.resolution_confidence == 0.9

    _add_file(
        store,
        second_path,
        [
            _module("second-module", "second-chunk", second_path, "app"),
            _signal(
                "second-method",
                "second-chunk",
                second_path,
                kind="method",
                qualified_name="two.Api.run",
                signature="(demo.Dto)",
                arity=1,
                unit="app",
            ),
        ],
    )
    resolve_graph_relations(store)
    ambiguous = store.graph_relation_for_id("candidate-method")
    assert ambiguous is not None
    assert ambiguous.resolution == "ambiguous"
    assert ambiguous.target_signal_id == ""


@pytest.mark.parametrize(
    ("basis", "expected_confidence"),
    [
        ("exact_test_import", 1.0),
        ("exact_test_path", 0.95),
    ],
)
def test_test_association_resolution_confidence_depends_on_exact_basis(
    tmp_path: Path,
    basis: str,
    expected_confidence: float,
) -> None:
    store = _store(tmp_path)
    source_path = "app/tests/ServiceTest.java"
    target_path = "app/src/Service.java"
    _add_file(
        store,
        source_path,
        [_module("test-module", "test-chunk", source_path, "app")],
    )
    _add_file(
        store,
        target_path,
        [_module("production-module", "production-chunk", target_path, "app")],
    )
    store.append_graph_relations(
        [
            CodeRelation(
                relation_id="tests",
                source_signal_id="test-module",
                target_name=target_path,
                kind="tests",
                confidence=1.0,
                target_kind="module",
                target_qualified_name=target_path,
                target_project_unit_key="app",
                resolution="unresolved",
                producer="test_association",
                producer_confidence=1.0,
                metadata={
                    "selector_state": "exact",
                    "candidates": [target_path],
                    "resolution_basis": basis,
                },
            )
        ]
    )

    resolve_graph_relations(store, association_only=True)
    relation = store.graph_relation_for_id("tests")
    assert relation is not None
    assert relation.resolution == "resolved_exact"
    assert relation.resolution_confidence == expected_confidence
    assert relation.confidence == expected_confidence


def test_changed_ready_index_reresolves_every_active_structured_relation(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "entry.ts").write_text(
        'import Target from "./target";\nexport { Target };\n',
        encoding="utf-8",
    )
    (repo / "target.ts").write_text(
        "export default class Target {}\n",
        encoding="utf-8",
    )
    note = repo / "note.md"
    note.write_text("first\n", encoding="utf-8")
    build_v5_index_snapshot(
        repo,
        DEFAULT_CONFIG,
        graph_plugins=[FrontendGraphProducer()],
        scanner=scan_workspace_v5,
    )
    database = repo / ".context-search" / "index.sqlite"
    with sqlite3.connect(database) as connection:
        relation_id = connection.execute(
            """
            SELECT relation_id FROM code_relations
            WHERE kind = 'imports' AND deleted_at IS NULL
            """
        ).fetchone()[0]
        connection.execute(
            """
            UPDATE code_relations
            SET target_signal_id = '', resolution = 'unresolved',
                confidence = producer_confidence,
                resolution_confidence = NULL
            WHERE relation_id = ?
            """,
            (relation_id,),
        )
    note.write_text("second\n", encoding="utf-8")

    build_v5_index_snapshot(
        repo,
        DEFAULT_CONFIG,
        graph_plugins=[FrontendGraphProducer()],
        scanner=scan_workspace_v5,
    )

    relation = SQLiteStore(database).graph_relation_for_id(relation_id)
    assert relation is not None
    assert relation.resolution in {"resolved_exact", "resolved_unique"}
    assert relation.target_signal_id
