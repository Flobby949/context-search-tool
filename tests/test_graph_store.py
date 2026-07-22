from __future__ import annotations

import hashlib
import importlib
import importlib.util
import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from context_search_tool.graph_lifecycle import (
    GRAPH_RESOLUTION_STATE_KEY,
    GRAPH_RESOLUTION_VERSION_KEY,
    GRAPH_STALE_REASON_KEY,
    FULL_REINDEX_REQUIRED_KEY,
    IncompatibleSignalSchemaError,
    SIGNAL_SCHEMA_VERSION_KEY,
)
from context_search_tool.models import (
    CodeRelation,
    CodeSignal,
    DocumentChunk,
    SourceFile,
)
from context_search_tool.sqlite_store import (
    PRODUCER_RESOLUTION_GENERATION_KEY,
    TEST_ASSOCIATION_SOURCE_GENERATION_KEY,
    SQLiteStore,
)
from context_search_tool.test_association import regenerate_test_associations


def _health_module() -> Any:
    spec = importlib.util.find_spec("context_search_tool.index_health")
    assert spec is not None, "P6 raw index capability probe is absent"
    return importlib.import_module("context_search_tool.index_health")


def _raw_tree(root: Path) -> dict[str, tuple[int, int, str]]:
    return {
        path.relative_to(root).as_posix(): (
            path.stat().st_size,
            path.stat().st_mtime_ns,
            hashlib.sha256(path.read_bytes()).hexdigest(),
        )
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _literal_raw_index(
    repo: Path,
    *,
    manifest_version: object = 2,
    operational_version: object | None = 1,
    graph_version: object | None = 5,
) -> None:
    internal = repo / ".context-search"
    internal.mkdir()
    (internal / "manifest.json").write_text(
        json.dumps({"schema_version": manifest_version}),
        encoding="utf-8",
    )
    with sqlite3.connect(internal / "index.sqlite") as connection:
        connection.execute(
            "CREATE TABLE index_metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        if operational_version is not None:
            connection.execute(
                "INSERT INTO index_metadata VALUES (?, ?)",
                ("operational_schema_version", str(operational_version)),
            )
        if graph_version is not None:
            connection.execute(
                "INSERT INTO index_metadata VALUES (?, ?)",
                (SIGNAL_SCHEMA_VERSION_KEY, str(graph_version)),
            )


def test_p6_raw_probe_is_missing_without_creating_index_state(tmp_path: Path) -> None:
    module = _health_module()
    repo = tmp_path / "repo"
    repo.mkdir()
    before = _raw_tree(repo)

    capability = module.probe_raw_index_capability(repo)

    assert capability.status == "missing"
    assert capability.index_exists is False
    assert capability.error_code == "missing_index"
    assert capability.manifest_version is None
    assert capability.operational_version is None
    assert capability.graph_version is None
    assert _raw_tree(repo) == before
    assert not (repo / ".context-search").exists()


def test_p6_future_manifest_stops_before_sqlite_or_normal_readers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _health_module()
    repo = tmp_path / "repo"
    repo.mkdir()
    _literal_raw_index(repo, manifest_version=3)

    def forbidden(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("future manifest crossed schema-first preflight")

    monkeypatch.setattr(module, "inspect_raw_sqlite_schema_versions", forbidden)
    before = _raw_tree(repo)
    capability = module.probe_raw_index_capability(repo)

    assert capability.status == "incompatible"
    assert capability.error_code == "future_manifest_schema"
    assert capability.manifest_version == 3
    assert capability.operational_version is None
    assert capability.graph_version is None
    assert _raw_tree(repo) == before


@pytest.mark.parametrize(
    ("operational", "graph", "error_code"),
    [
        (2, 5, "future_operational_schema"),
        (1, 6, "future_graph_schema"),
        ("not-an-int", 5, "invalid_operational_schema"),
        (1, "not-an-int", "invalid_graph_schema"),
    ],
)
def test_p6_raw_probe_classifies_future_and_malformed_known_metadata_only(
    tmp_path: Path,
    operational: object,
    graph: object,
    error_code: str,
) -> None:
    module = _health_module()
    repo = tmp_path / "repo"
    repo.mkdir()
    _literal_raw_index(
        repo,
        operational_version=operational,
        graph_version=graph,
    )
    before = _raw_tree(repo)

    capability = module.probe_raw_index_capability(repo)

    expected_status = "incompatible" if error_code.startswith("future") else "corrupt"
    assert capability.status == expected_status
    assert capability.error_code == error_code
    assert capability.manifest_version == 2
    assert _raw_tree(repo) == before
    assert not list((repo / ".context-search").glob("*-journal"))
    assert not list((repo / ".context-search").glob("*-wal"))


def test_p6_raw_probe_reads_literal_legacy_and_current_versions_read_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _health_module()

    def forbidden(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("raw probe used a normal mutable store API")

    monkeypatch.setattr(SQLiteStore, "get_metadata", forbidden)
    for name, manifest_version, operational_version in (
        ("legacy", 1, None),
        ("current", 2, 1),
    ):
        repo = tmp_path / name
        repo.mkdir()
        _literal_raw_index(
            repo,
            manifest_version=manifest_version,
            operational_version=operational_version,
            graph_version=5,
        )
        before = _raw_tree(repo)

        capability = module.probe_raw_index_capability(repo)

        assert capability.status == "compatible"
        assert capability.manifest_version == manifest_version
        assert capability.operational_version == operational_version
        assert capability.graph_version == 5
        assert capability.error_code is None
        assert _raw_tree(repo) == before


V5_SIGNAL_COLUMNS = {
    "signal_id",
    "chunk_id",
    "file_path",
    "kind",
    "name",
    "qualified_name",
    "signature",
    "arity",
    "project_unit_key",
    "producer",
    "start_line",
    "end_line",
    "start_column",
    "end_column",
    "language",
    "recallable",
    "tokens",
    "metadata",
    "deleted_at",
}
V5_RELATION_COLUMNS = {
    "relation_id",
    "source_signal_id",
    "source_chunk_id",
    "source_file_path",
    "target_name",
    "kind",
    "confidence",
    "target_kind",
    "target_qualified_name",
    "target_signature",
    "target_arity",
    "target_project_unit_key",
    "target_signal_id",
    "resolution",
    "producer",
    "producer_confidence",
    "resolution_confidence",
    "metadata",
    "deleted_at",
}
V5_INDEXES = {
    "idx_chunks_embedding_active",
    "idx_code_signals_chunk_active",
    "idx_code_signals_file_active",
    "idx_code_signals_selector_active",
    "idx_code_signals_arity_active",
    "idx_code_signals_recallable_active",
    "idx_code_relations_source_active",
    "idx_code_relations_target_signal_active",
    "idx_code_relations_resolution_active",
    "idx_code_relations_target_active",
}


def _literal_v4_database(path: Path, *, version: int = 4) -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE source_files (
                path TEXT PRIMARY KEY,
                language TEXT NOT NULL,
                sha256 TEXT NOT NULL,
                size INTEGER NOT NULL,
                mtime_ns INTEGER NOT NULL,
                is_generated INTEGER NOT NULL,
                is_test INTEGER NOT NULL,
                metadata TEXT NOT NULL
            );
            CREATE TABLE chunks (
                chunk_id TEXT PRIMARY KEY,
                file_path TEXT NOT NULL,
                start_line INTEGER NOT NULL,
                end_line INTEGER NOT NULL,
                content TEXT NOT NULL,
                chunk_type TEXT NOT NULL,
                embedding_id TEXT,
                deleted_at INTEGER,
                metadata TEXT NOT NULL
            );
            CREATE TABLE index_metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at INTEGER NOT NULL
            );
            CREATE TABLE code_signals (
                signal_id TEXT PRIMARY KEY,
                chunk_id TEXT NOT NULL,
                file_path TEXT NOT NULL,
                kind TEXT NOT NULL,
                name TEXT NOT NULL,
                start_line INTEGER NOT NULL,
                end_line INTEGER NOT NULL,
                language TEXT NOT NULL,
                tokens TEXT NOT NULL,
                metadata TEXT NOT NULL,
                deleted_at INTEGER
            );
            CREATE INDEX idx_code_signals_chunk_active
            ON code_signals(chunk_id, deleted_at);
            CREATE INDEX idx_code_signals_file_active
            ON code_signals(file_path, deleted_at);
            CREATE TABLE code_relations (
                relation_id TEXT PRIMARY KEY,
                source_signal_id TEXT NOT NULL,
                source_chunk_id TEXT NOT NULL,
                source_file_path TEXT NOT NULL,
                target_name TEXT NOT NULL,
                kind TEXT NOT NULL,
                confidence REAL NOT NULL,
                metadata TEXT NOT NULL,
                deleted_at INTEGER
            );
            CREATE INDEX idx_code_relations_source_active
            ON code_relations(source_signal_id, deleted_at);
            CREATE INDEX idx_code_relations_target_active
            ON code_relations(target_name, deleted_at);
            """
        )
        connection.execute(
            "INSERT INTO index_metadata VALUES (?, ?, 1)",
            (SIGNAL_SCHEMA_VERSION_KEY, str(version)),
        )
        connection.execute(
            """
            INSERT INTO code_signals VALUES (
                'legacy-signal', 'legacy-chunk', 'src/Legacy.java', 'method',
                'Legacy.run', 3, 4, 'java', '["legacy"]', '{"old":true}', NULL
            )
            """
        )
        connection.execute(
            """
            INSERT INTO code_relations VALUES (
                'legacy-relation', 'legacy-signal', 'legacy-chunk',
                'src/Legacy.java', 'Target.run', 'uses', 0.75,
                '{"old":true}', NULL
            )
            """
        )


def _chunk(chunk_id: str, file_path: str) -> DocumentChunk:
    return DocumentChunk(
        chunk_id=chunk_id,
        file_path=Path(file_path),
        start_line=1,
        end_line=20,
        content=f"content {chunk_id}",
        chunk_type="symbol",
        lexical_tokens=[chunk_id],
        embedding_id=chunk_id,
    )


def _signal(
    signal_id: str,
    chunk_id: str,
    file_path: str,
    *,
    kind: str = "method",
    qualified_name: str = "demo.Target.run",
    signature: str = "()",
    arity: int | None = 0,
    project_unit_key: str = "",
    producer: str = "java_ast",
    recallable: bool = True,
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
        project_unit_key=project_unit_key,
        producer=producer,
        start_line=3,
        end_line=4,
        start_column=2,
        end_column=8,
        language="java",
        recallable=recallable,
        tokens=["target", "run"],
        metadata={"structured": True},
    )


def _module(signal_id: str, chunk_id: str, file_path: str, unit: str = "") -> CodeSignal:
    return _signal(
        signal_id,
        chunk_id,
        file_path,
        kind="module",
        qualified_name=file_path,
        signature="",
        arity=None,
        project_unit_key=unit,
        producer="core_module",
        recallable=False,
    )


def _schema_projection(path: Path) -> tuple[tuple[tuple[object, ...], ...], ...]:
    with sqlite3.connect(path) as connection:
        tables = tuple(
            connection.execute(
                "SELECT type, name, sql FROM sqlite_master ORDER BY type, name"
            ).fetchall()
        )
        metadata = tuple(
            connection.execute(
                "SELECT key, value, updated_at FROM index_metadata ORDER BY key"
            ).fetchall()
        )
        signal_info = tuple(connection.execute("PRAGMA table_info(code_signals)"))
        relation_info = tuple(connection.execute("PRAGMA table_info(code_relations)"))
    return tables, metadata, signal_info, relation_info


def _v5_store(tmp_path: Path) -> SQLiteStore:
    path = tmp_path / "index.sqlite"
    _literal_v4_database(path)
    store = SQLiteStore(path)
    store.initialize()
    store.migrate_signal_schema_v5()
    return store


def test_literal_v4_rows_decode_through_introspected_defaults(tmp_path: Path) -> None:
    path = tmp_path / "v4.sqlite"
    _literal_v4_database(path)
    store = SQLiteStore(path)

    [signal] = store.signals_for_chunk("legacy-chunk")
    [relation] = store.relations_for_source("legacy-signal")

    assert signal.qualified_name == ""
    assert signal.signature == ""
    assert signal.project_unit_key == ""
    assert signal.producer == "legacy"
    assert signal.recallable is True
    assert relation.resolution == "legacy"
    assert relation.target_signal_id == ""
    assert relation.producer_confidence == 1.0
    assert relation.resolution_confidence is None
    with store.graph_read_session() as session:
        [adapted] = session.legacy_relations_for_source("legacy-signal")
    assert adapted.producer_confidence == 0.75


def test_future_schema_refusal_precedes_unknown_queries_or_ddl(tmp_path: Path) -> None:
    path = tmp_path / "future.sqlite"
    _literal_v4_database(path, version=6)
    before = _schema_projection(path)

    with pytest.raises(
        IncompatibleSignalSchemaError,
        match="incompatible signal schema 6",
    ):
        SQLiteStore(path).migrate_signal_schema_v5()

    assert _schema_projection(path) == before
    with pytest.raises(
        IncompatibleSignalSchemaError,
        match="incompatible signal schema 6",
    ):
        SQLiteStore(path).initialize_v5()
    assert _schema_projection(path) == before


def test_atomic_v4_to_v5_migration_creates_exact_empty_schema_and_metadata(
    tmp_path: Path,
) -> None:
    path = tmp_path / "migrate.sqlite"
    _literal_v4_database(path)
    store = SQLiteStore(path)

    store.migrate_signal_schema_v5()

    with sqlite3.connect(path) as connection:
        signal_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(code_signals)")
        }
        relation_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(code_relations)")
        }
        indexes = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index'"
            )
            if not row[0].startswith("sqlite_autoindex")
        }
        metadata = dict(
            connection.execute("SELECT key, value FROM index_metadata")
        )
        counts = (
            connection.execute("SELECT COUNT(*) FROM code_signals").fetchone()[0],
            connection.execute("SELECT COUNT(*) FROM code_relations").fetchone()[0],
        )

    assert signal_columns == V5_SIGNAL_COLUMNS
    assert relation_columns == V5_RELATION_COLUMNS
    assert V5_INDEXES <= indexes
    assert metadata[SIGNAL_SCHEMA_VERSION_KEY] == "5"
    assert metadata[GRAPH_RESOLUTION_VERSION_KEY] == "1"
    assert metadata[GRAPH_RESOLUTION_STATE_KEY] == "stale"
    assert metadata[GRAPH_STALE_REASON_KEY] == "schema_migration"
    assert metadata[FULL_REINDEX_REQUIRED_KEY] == "1"
    assert counts == (0, 0)


def test_fresh_store_initializes_directly_as_complete_v5_stale(
    tmp_path: Path,
) -> None:
    path = tmp_path / "fresh.sqlite"
    store = SQLiteStore(path)

    store.initialize_v5()

    assert store.inspect_signal_schema_version() == 5
    assert store.get_metadata(GRAPH_RESOLUTION_STATE_KEY) == "stale"
    assert store.get_metadata(GRAPH_STALE_REASON_KEY) == "full_reindex"
    assert store.get_metadata(FULL_REINDEX_REQUIRED_KEY) == "1"
    with sqlite3.connect(path) as connection:
        assert {
            row[1] for row in connection.execute("PRAGMA table_info(code_signals)")
        } == V5_SIGNAL_COLUMNS
        assert {
            row[1]
            for row in connection.execute("PRAGMA table_info(code_relations)")
        } == V5_RELATION_COLUMNS


def test_migration_fault_rolls_back_to_complete_v4(tmp_path: Path) -> None:
    path = tmp_path / "rollback.sqlite"
    _literal_v4_database(path)
    before = _schema_projection(path)

    def fail() -> None:
        raise RuntimeError("ddl fault")

    with pytest.raises(RuntimeError, match="ddl fault"):
        SQLiteStore(path).migrate_signal_schema_v5(before_commit=fail)

    assert _schema_projection(path) == before


def test_operational_additive_ddl_fault_rolls_back_to_exact_v5(
    tmp_path: Path,
) -> None:
    store = _v5_store(tmp_path)

    def operational_projection() -> tuple[object, ...]:
        with sqlite3.connect(store.db_path) as connection:
            return (
                tuple(
                    connection.execute(
                        "SELECT type, name, sql FROM sqlite_master ORDER BY type, name"
                    )
                ),
                tuple(connection.execute("PRAGMA table_info(source_files)")),
                tuple(
                    connection.execute(
                        "SELECT key, value, updated_at FROM index_metadata ORDER BY key"
                    )
                ),
            )

    before = operational_projection()

    def fail() -> None:
        raise RuntimeError("operational ddl fault")

    with pytest.raises(RuntimeError, match="operational ddl fault"):
        store.initialize_operational_schema_v1(before_commit=fail)

    assert operational_projection() == before
    assert store.get_metadata("operational_schema_version") is None


def test_v5_codecs_root_unit_recallable_filter_and_legacy_view(tmp_path: Path) -> None:
    store = _v5_store(tmp_path)
    chunk = _chunk("chunk", "src/Target.java")
    module = _module("module", "chunk", "src/Target.java")
    method = _signal("method", "chunk", "src/Target.java")
    legacy = CodeRelation(
        relation_id="legacy",
        source_signal_id="method",
        target_name="Legacy.target",
        kind="uses",
        confidence=0.5,
    )
    structured = CodeRelation(
        relation_id="structured",
        source_signal_id="method",
        target_name="demo.Target.run",
        kind="calls",
        confidence=0.8,
        target_kind="method",
        target_qualified_name="demo.Target.run",
        target_signature="()",
        target_arity=0,
        target_project_unit_key="",
        target_signal_id="method",
        resolution="resolved_exact",
        producer="java_ast",
        producer_confidence=0.8,
        resolution_confidence=1.0,
        metadata={
            "first_source_line": 10,
            "first_source_column": 4,
            "occurrence_count": 2,
        },
    )
    store.replace_chunks(chunk.file_path, [chunk])
    store.replace_graph_facts(chunk.file_path, [module, method], [legacy, structured])

    assert store.signal_search(["Target"], limit=10) == []
    [legacy_view] = store.relations_for_source("method")
    assert legacy_view.relation_id == "legacy"
    assert legacy_view.producer_confidence == 0.5
    assert store.graph_signal_for_id("module") == module
    assert store.graph_signal_for_id("method") == method
    assert store.graph_relation_for_id("structured") == structured


def test_sqlite_test_association_session_records_producer_generation(
    tmp_path: Path,
) -> None:
    store = SQLiteStore(tmp_path / "association.sqlite")
    store.initialize_v5()
    production_path = Path("src/main/java/demo/Service.java")
    test_path = Path("src/test/java/demo/ServiceTest.java")
    for path, chunk_id, module_id, is_test in (
        (production_path, "production-chunk", "production-module", False),
        (test_path, "test-chunk", "test-module", True),
    ):
        store.replace_chunks(path, [_chunk(chunk_id, path.as_posix())])
        store.replace_graph_facts(
            path,
            [_module(module_id, chunk_id, path.as_posix())],
            [],
        )
        store.upsert_source_file(
            SourceFile(
                path=path,
                language="java",
                sha256=module_id,
                size=1,
                mtime_ns=1,
                is_test=is_test,
            )
        )

    generation = store.advance_producer_resolution_generation()
    relations = regenerate_test_associations(
        store,
        producer_resolution_generation=generation,
    )

    assert len(relations) == 1
    assert relations[0].kind == "tests"
    assert store.get_metadata(PRODUCER_RESOLUTION_GENERATION_KEY) == "1"
    assert store.get_metadata(TEST_ASSOCIATION_SOURCE_GENERATION_KEY) == "1"


def test_graph_session_reads_ready_snapshot_with_bounded_canonical_adjacency(
    tmp_path: Path,
) -> None:
    store = _v5_store(tmp_path)
    source_chunk = _chunk("source-chunk", "src/Source.java")
    source_module = _module("source-module", "source-chunk", "src/Source.java")
    source = _signal(
        "source",
        "source-chunk",
        "src/Source.java",
        qualified_name="demo.Source.run",
    )
    store.replace_chunks(source_chunk.file_path, [source_chunk])
    store.replace_graph_facts(source_chunk.file_path, [source_module, source], [])

    for index in range(66):
        file_path = f"src/Target{index:02d}.java"
        chunk = _chunk(f"chunk-{index:02d}", file_path)
        module = _module(f"module-{index:02d}", chunk.chunk_id, file_path)
        target = _signal(
            f"target-{index:02d}",
            chunk.chunk_id,
            file_path,
            qualified_name=f"demo.Target{index:02d}.run",
        )
        relation = CodeRelation(
            relation_id=f"relation-{index:02d}",
            source_signal_id="source",
            target_name=target.qualified_name,
            kind="calls",
            confidence=0.8,
            target_kind="method",
            target_qualified_name=target.qualified_name,
            target_signature="()",
            target_arity=0,
            target_project_unit_key="",
            target_signal_id=target.signal_id,
            resolution="resolved_exact",
            producer="java_ast",
            producer_confidence=0.8,
            resolution_confidence=1.0,
        )
        store.replace_chunks(chunk.file_path, [chunk])
        store.replace_graph_facts(chunk.file_path, [module, target], [])
        store.append_graph_relations([relation])

    store.mark_graph_ready(topology_fingerprint="a" * 64)

    with store.graph_read_session() as session:
        assert session.capability.status == "ready"
        assert session.module_for_path(Path("src/Source.java")) == source_module
        outgoing = session.outgoing_relations("source")
        incoming = session.incoming_relations("target-00")

    assert len(outgoing) == 65
    assert [item.relation_id for item in outgoing] == [
        f"relation-{index:02d}" for index in range(65)
    ]
    assert [item.relation_id for item in incoming] == ["relation-00"]


def test_ready_transition_rejects_dangling_targets_and_keeps_stale_flag(
    tmp_path: Path,
) -> None:
    store = _v5_store(tmp_path)
    chunk = _chunk("chunk", "src/Source.java")
    module = _module("module", "chunk", "src/Source.java")
    source = _signal("source", "chunk", "src/Source.java")
    dangling = CodeRelation(
        relation_id="dangling",
        source_signal_id="source",
        target_name="missing",
        kind="calls",
        confidence=0.8,
        target_kind="method",
        target_qualified_name="missing",
        target_signal_id="missing",
        resolution="resolved_exact",
        producer="java_ast",
        producer_confidence=0.8,
        resolution_confidence=1.0,
    )
    store.replace_chunks(chunk.file_path, [chunk])
    store.replace_graph_facts(chunk.file_path, [module, source], [dangling])

    integrity = store.graph_integrity()
    assert integrity.ok is False
    assert integrity.dangling_targets == 1
    with pytest.raises(ValueError, match="graph integrity"):
        store.mark_graph_ready(topology_fingerprint="b" * 64)

    assert store.get_metadata(GRAPH_RESOLUTION_STATE_KEY) == "stale"
    assert store.get_metadata(FULL_REINDEX_REQUIRED_KEY) == "1"


def test_v5_snapshot_validation_rejects_signal_without_owning_chunk(
    tmp_path: Path,
) -> None:
    store = _v5_store(tmp_path)
    file_path = Path("src/Source.java")
    chunk = _chunk("chunk", file_path.as_posix())
    module = _module("module", "chunk", file_path.as_posix())
    store.upsert_source_file(
        SourceFile(
            path=file_path,
            language="java",
            sha256="a" * 64,
            size=1,
            mtime_ns=1,
            is_generated=False,
            is_test=False,
        )
    )
    store.replace_chunks(file_path, [chunk])
    store.replace_graph_facts(file_path, [module], [])
    with sqlite3.connect(store.db_path) as connection:
        connection.execute(
            "UPDATE code_signals SET chunk_id = 'missing' WHERE signal_id = 'module'"
        )

    with pytest.raises(ValueError, match="active signal has no owning source chunk"):
        store.mark_graph_ready(
            topology_fingerprint="c" * 64,
            expected_embedding_ids={"chunk"},
            expected_source_count=1,
            expected_chunk_count=1,
        )

    assert store.get_metadata(GRAPH_RESOLUTION_STATE_KEY) == "stale"
