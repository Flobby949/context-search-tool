from pathlib import Path
import sqlite3

import pytest

from context_search_tool.config import (
    DEFAULT_CONFIG,
    EmbeddingConfig,
    ToolConfig,
    load_config,
)
from context_search_tool.indexer import (
    IncompatibleIndexError,
    SIGNAL_SCHEMA_VERSION_KEY,
    build_v5_index_snapshot,
    index_repository,
    read_v5_vector_snapshot,
)
from context_search_tool.graph_lifecycle import (
    FULL_REINDEX_REQUIRED_KEY,
    GRAPH_RESOLUTION_STATE_KEY,
    GRAPH_RESOLUTION_VERSION_KEY,
    GraphIntegrityError,
    IncompatibleSignalSchemaError,
    IndexBusyError,
)
from context_search_tool.graph_plugins import (
    MaterializedGraph,
    ParsedGraphFacts,
)
from context_search_tool.frontend_graph import FrontendGraphProducer
from context_search_tool.java_graph import JavaGraphProducer
from context_search_tool.index_lock import exclusive_index_lock
from context_search_tool.manifest import load_manifest
from context_search_tool.models import CodeRelation, CodeSignal
from context_search_tool.mybatis_xml import MyBatisGraphProducer
from context_search_tool.plugins import PluginExtraction
from context_search_tool.scanner import read_scanned_file_bytes, scan_workspace_v5
from context_search_tool.sqlite_store import SQLiteStore
from context_search_tool.vector_store import NumpyVectorStore


class _SignalPlugin:
    def __init__(self, signals: list[CodeSignal], relations: list[CodeRelation]) -> None:
        self.signals = signals
        self.relations = relations

    def supports(self, path: Path, language: str) -> bool:
        return language == "java"

    def extract(self, path: Path, content: str) -> PluginExtraction:
        return PluginExtraction(signals=self.signals, relations=self.relations)


class _RecordingGraphPlugin:
    def __init__(self, name: str, events: list[str]) -> None:
        self.name = name
        self.events = events

    def supports(self, context) -> bool:
        return context.file_path.suffix == ".java"

    def parse(self, context, content: bytes) -> ParsedGraphFacts:
        self.events.append(f"parse:{self.name}:{context.file_path.as_posix()}")
        return ParsedGraphFacts(facts=None)

    def materialize(
        self,
        context,
        parsed: ParsedGraphFacts,
        chunks,
        module_signal,
    ) -> MaterializedGraph:
        self.events.append(
            f"materialize:{self.name}:{context.file_path.as_posix()}"
        )
        return MaterializedGraph()


def test_index_repository_creates_expected_index_files(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "App.java").write_text("class App { String canApply; }\n", encoding="utf-8")

    summary = index_repository(repo, DEFAULT_CONFIG)

    assert summary.files_indexed == 1
    assert (repo / ".context-search" / "manifest.json").exists()
    assert (repo / ".context-search" / "index.sqlite").exists()
    assert (repo / ".context-search" / "vectors.npy").exists()
    assert (repo / ".context-search" / "vector_ids.json").exists()
    assert load_manifest(repo).total_chunks >= 1


def test_index_repository_indexes_go_source_with_generic_chunks(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    source = repo / "handler" / "upload.go"
    source.parent.mkdir(parents=True)
    source.write_text(
        """
package handler

type UploadHandler struct {}

func (h *UploadHandler) Upload() string {
    return "upload"
}

func (h *UploadHandler) MultiUpload() string {
    return "multi"
}
""".strip()
        + "\n",
        encoding="utf-8",
    )

    summary = index_repository(repo, DEFAULT_CONFIG)

    assert summary.files_seen == 1
    assert summary.files_indexed == 1
    store = SQLiteStore(repo / ".context-search" / "index.sqlite")
    stats = store.stats()
    assert stats["source_files"] == 1
    assert stats["active_chunks"] >= 1
    chunk = store.chunk_for_line(Path("handler/upload.go"), 5)
    assert chunk.chunk_type == "generic"
    assert chunk.metadata["language"] == "go"
    assert "upload" in chunk.lexical_tokens
    assert "handler" in chunk.lexical_tokens


def test_index_repository_indexes_rust_source_with_generic_chunks(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    source = repo / "src" / "lib.rs"
    source.parent.mkdir(parents=True)
    source.write_text(
        """
pub struct ImageStore;

impl ImageStore {
    pub fn delete_by_filename(&self, filename: &str) -> bool {
        !filename.is_empty()
    }
}
""".strip()
        + "\n",
        encoding="utf-8",
    )

    summary = index_repository(repo, DEFAULT_CONFIG)

    assert summary.files_seen == 1
    store = SQLiteStore(repo / ".context-search" / "index.sqlite")
    chunk = store.chunk_for_line(Path("src/lib.rs"), 4)
    assert chunk.metadata["language"] == "rust"
    assert "delete" in chunk.lexical_tokens
    assert "filename" in chunk.lexical_tokens


def test_index_repository_propagates_scanner_test_metadata_to_chunks(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    source = repo / "service" / "upload_test.go"
    source.parent.mkdir(parents=True)
    source.write_text(
        "package service\nfunc TestUpload() {}\n",
        encoding="utf-8",
    )

    summary = index_repository(repo, DEFAULT_CONFIG)

    assert summary.files_seen == 1
    store = SQLiteStore(repo / ".context-search" / "index.sqlite")
    chunk = store.chunk_for_line(Path("service/upload_test.go"), 2)
    assert chunk.metadata["language"] == "go"
    assert chunk.metadata["is_test"]


def test_index_repository_skips_unchanged_files(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "App.java").write_text("class App {}\n", encoding="utf-8")

    first = index_repository(repo, DEFAULT_CONFIG)
    second = index_repository(repo, DEFAULT_CONFIG)

    assert first.files_indexed == 1
    assert second.files_indexed == 0


def test_index_repository_rejects_incompatible_embedding_config(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "App.java").write_text("class App {}\n", encoding="utf-8")
    index_repository(repo, DEFAULT_CONFIG)

    incompatible = ToolConfig(
        embedding=EmbeddingConfig(provider="hash", model="hash-v2", dimensions=384)
    )

    with pytest.raises(IncompatibleIndexError):
        index_repository(repo, incompatible)


def test_index_repository_persists_passed_config_when_creating_config_file(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "App.java").write_text("class App {}\n", encoding="utf-8")
    custom = ToolConfig(
        embedding=EmbeddingConfig(provider="hash", model="hash-v2", dimensions=128)
    )

    index_repository(repo, custom)
    loaded = load_config(repo)

    assert loaded.embedding.model == "hash-v2"
    assert loaded.embedding.dimensions == 128
    summary = index_repository(repo, loaded)
    assert summary.files_indexed == 0


def test_index_repository_retries_file_when_previous_vector_write_failed(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "App.java").write_text("class App {}\n", encoding="utf-8")
    bad_config = ToolConfig(embedding=EmbeddingConfig(provider="unsupported"))

    with pytest.raises(ValueError):
        index_repository(repo, bad_config)

    summary = index_repository(repo, DEFAULT_CONFIG)

    assert summary.files_indexed == 1
    assert (repo / ".context-search" / "vectors.npy").exists()
    assert (repo / ".context-search" / "vector_ids.json").exists()


def test_index_repository_skips_unchanged_empty_file(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "Empty.java").write_text("", encoding="utf-8")

    first = index_repository(repo, DEFAULT_CONFIG)
    second = index_repository(repo, DEFAULT_CONFIG)

    assert first.files_indexed == 1
    assert second.files_indexed == 0


def test_index_repository_persists_plugin_signals_and_relations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "App.java").write_text("class App {}\n", encoding="utf-8")
    signal = CodeSignal(
        signal_id="sig-app",
        chunk_id="plugin-placeholder",
        file_path=Path("App.java"),
        kind="endpoint",
        name="GET /app",
        start_line=1,
        end_line=1,
        language="java",
        tokens=["app"],
        metadata={},
    )
    relation = CodeRelation(
        relation_id="rel-app-service",
        source_signal_id="sig-app",
        target_name="AppService.handle",
        kind="calls",
        confidence=0.8,
        metadata={},
    )
    monkeypatch.setattr(
        "context_search_tool.indexer.default_plugins",
        lambda: [_SignalPlugin([signal], [relation])],
    )

    index_repository(repo, DEFAULT_CONFIG)

    store = SQLiteStore(repo / ".context-search" / "index.sqlite")
    stored_signal = store.signal_search(["app"], limit=10)[0]
    assert stored_signal.signal_id == "sig-app"
    assert stored_signal.chunk_id != "plugin-placeholder"
    assert store.signals_for_chunk(stored_signal.chunk_id) == [stored_signal]
    assert store.relations_for_source("sig-app") == [relation]


def test_index_repository_rebuilds_previous_signal_schema_for_unchanged_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "App.java").write_text("class App {}\n", encoding="utf-8")
    old_signal = CodeSignal(
        signal_id="sig-old",
        chunk_id="plugin-placeholder",
        file_path=Path("App.java"),
        kind="endpoint",
        name="old",
        start_line=1,
        end_line=1,
        language="java",
        tokens=["old"],
        metadata={},
    )
    new_signal = CodeSignal(
        signal_id="sig-new",
        chunk_id="plugin-placeholder",
        file_path=Path("App.java"),
        kind="field",
        name="App.newSignal",
        start_line=1,
        end_line=1,
        language="java",
        tokens=["new", "signal"],
        metadata={},
    )
    monkeypatch.setattr(
        "context_search_tool.indexer.default_plugins",
        lambda: [_SignalPlugin([old_signal], [])],
    )
    index_repository(repo, DEFAULT_CONFIG)
    store = SQLiteStore(repo / ".context-search" / "index.sqlite")
    assert store.signal_search(["old"], limit=10)[0].signal_id == "sig-old"
    store.set_metadata(SIGNAL_SCHEMA_VERSION_KEY, "3")

    monkeypatch.setattr(
        "context_search_tool.indexer.default_plugins",
        lambda: [_SignalPlugin([new_signal], [])],
    )
    summary = index_repository(repo, DEFAULT_CONFIG)

    assert summary.files_indexed == 1
    assert store.signal_search(["old"], limit=10) == []
    assert store.signal_search(["new", "signal"], limit=10)[0].signal_id == "sig-new"
    assert store.get_metadata(SIGNAL_SCHEMA_VERSION_KEY) == "4"


def test_internal_v5_builder_creates_ready_snapshot_and_verified_noop(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "App.java").write_text("class App {}\n", encoding="utf-8")
    (repo / "Empty.java").write_text("", encoding="utf-8")
    events: list[str] = []
    plugins = [
        _RecordingGraphPlugin("zeta", events),
        _RecordingGraphPlugin("alpha", events),
        _RecordingGraphPlugin("middle", events),
    ]

    first = build_v5_index_snapshot(
        repo,
        DEFAULT_CONFIG,
        graph_plugins=plugins,
        scanner=scan_workspace_v5,
    )

    store = SQLiteStore(repo / ".context-search" / "index.sqlite")
    assert first.files_seen == 2
    assert first.files_indexed == 2
    assert store.get_metadata(SIGNAL_SCHEMA_VERSION_KEY) == "5"
    assert store.get_metadata(GRAPH_RESOLUTION_VERSION_KEY) == "1"
    assert store.get_metadata(GRAPH_RESOLUTION_STATE_KEY) == "ready"
    assert store.get_metadata(FULL_REINDEX_REQUIRED_KEY) == "0"
    assert store.source_file_for_path(Path("Empty.java")) is not None
    with sqlite3.connect(store.db_path) as connection:
        assert connection.execute(
            """
            SELECT COUNT(*) FROM code_signals
            WHERE producer = 'core_module' AND deleted_at IS NULL
            """
        ).fetchone()[0] == 1
        assert connection.execute(
            """
            SELECT COUNT(*) FROM chunks
            WHERE file_path = 'Empty.java' AND deleted_at IS NULL
            """
        ).fetchone()[0] == 0
    assert events == [
        "parse:alpha:App.java",
        "parse:middle:App.java",
        "parse:zeta:App.java",
        "materialize:alpha:App.java",
        "materialize:middle:App.java",
        "materialize:zeta:App.java",
    ]

    events.clear()
    stages: list[str] = []
    second = build_v5_index_snapshot(
        repo,
        DEFAULT_CONFIG,
        graph_plugins=plugins,
        scanner=scan_workspace_v5,
        fault_hook=stages.append,
    )

    assert second.files_indexed == 0
    assert second.files_skipped == 2
    assert events == []
    assert stages == []


def test_internal_v5_builder_keeps_source_hash_last_and_recovers(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "App.java").write_text("class App {}\n", encoding="utf-8")
    plugin = _RecordingGraphPlugin("java", [])

    def fail_after_relations(stage: str) -> None:
        if stage == "producer_relations_persisted":
            raise RuntimeError("relation fault")

    with pytest.raises(RuntimeError, match="relation fault"):
        build_v5_index_snapshot(
            repo,
            DEFAULT_CONFIG,
            graph_plugins=[plugin],
            scanner=scan_workspace_v5,
            fault_hook=fail_after_relations,
        )

    store = SQLiteStore(repo / ".context-search" / "index.sqlite")
    assert store.get_metadata(GRAPH_RESOLUTION_STATE_KEY) == "stale"
    assert store.get_metadata(FULL_REINDEX_REQUIRED_KEY) == "1"
    assert store.source_file_for_path(Path("App.java")) is None

    summary = build_v5_index_snapshot(
        repo,
        DEFAULT_CONFIG,
        graph_plugins=[plugin],
        scanner=scan_workspace_v5,
    )

    assert summary.files_indexed == 1
    assert store.source_file_for_path(Path("App.java")) is not None
    assert store.get_metadata(GRAPH_RESOLUTION_STATE_KEY) == "ready"


def test_internal_v5_builder_full_rebuild_ignores_legacy_hashes_and_vectors(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "App.java").write_text("class App {}\n", encoding="utf-8")
    index_repository(repo, DEFAULT_CONFIG)
    index_dir = repo / ".context-search"
    (index_dir / "vectors.npy").write_bytes(b"corrupt")
    (index_dir / "vector_ids.json").write_text("not json", encoding="utf-8")
    events: list[str] = []

    summary = build_v5_index_snapshot(
        repo,
        DEFAULT_CONFIG,
        graph_plugins=[_RecordingGraphPlugin("java", events)],
        scanner=scan_workspace_v5,
    )

    store = SQLiteStore(index_dir / "index.sqlite")
    assert summary.files_indexed == 1
    assert events[0] == "parse:java:App.java"
    assert store.get_metadata(SIGNAL_SCHEMA_VERSION_KEY) == "5"
    assert store.get_metadata(GRAPH_RESOLUTION_STATE_KEY) == "ready"
    assert NumpyVectorStore.load_published(index_dir).ids == tuple(
        sorted(store.active_embedding_ids())
    )


def test_internal_v5_builder_recovers_an_unreadable_ready_manifest(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "App.java").write_text("class App {}\n", encoding="utf-8")
    plugin = _RecordingGraphPlugin("java", [])
    build_v5_index_snapshot(
        repo,
        DEFAULT_CONFIG,
        graph_plugins=[plugin],
        scanner=scan_workspace_v5,
    )
    index_dir = repo / ".context-search"
    (index_dir / "manifest.json").write_text("not json\n", encoding="utf-8")

    summary = build_v5_index_snapshot(
        repo,
        DEFAULT_CONFIG,
        graph_plugins=[plugin],
        scanner=scan_workspace_v5,
    )

    store = SQLiteStore(index_dir / "index.sqlite")
    assert summary.files_indexed == 1
    assert store.get_metadata(GRAPH_RESOLUTION_STATE_KEY) == "ready"
    assert load_manifest(repo).total_files == 1


def test_internal_v5_builder_runs_all_explicit_graph_adapters(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "App.java").write_text(
        "package demo; class App { void run() {} }\n",
        encoding="utf-8",
    )
    (repo / "src" / "routes.ts").write_text(
        'import View from "./View";\nexport { View };\n',
        encoding="utf-8",
    )
    (repo / "src" / "View.ts").write_text(
        "export default function View() {}\n",
        encoding="utf-8",
    )
    (repo / "src" / "Mapper.xml").write_text(
        '<mapper namespace="demo.Mapper">\n'
        '  <select id="find">select 1</select>\n'
        "</mapper>\n",
        encoding="utf-8",
    )

    build_v5_index_snapshot(
        repo,
        DEFAULT_CONFIG,
        graph_plugins=[
            MyBatisGraphProducer(),
            JavaGraphProducer(),
            FrontendGraphProducer(),
        ],
        scanner=scan_workspace_v5,
    )

    with sqlite3.connect(repo / ".context-search" / "index.sqlite") as connection:
        producers = {
            row[0]
            for row in connection.execute(
                """
                SELECT DISTINCT producer FROM code_signals
                WHERE deleted_at IS NULL
                UNION
                SELECT DISTINCT producer FROM code_relations
                WHERE deleted_at IS NULL
                """
            )
        }
    assert {"core_module", "java_ast", "frontend_graph", "mybatis_xml"} <= producers


def test_internal_v5_malformed_java_keeps_only_fallback_marker(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "Broken.java").write_text(
        "package ; class Broken {\n",
        encoding="utf-8",
    )

    build_v5_index_snapshot(
        repo,
        DEFAULT_CONFIG,
        graph_plugins=[JavaGraphProducer()],
        scanner=scan_workspace_v5,
    )

    store = SQLiteStore(repo / ".context-search" / "index.sqlite")
    source = store.source_file_for_path(Path("Broken.java"))
    assert source is not None
    [plugin_metadata] = source.metadata["graph_plugins"].values()
    assert plugin_metadata["fallback_required"] is True
    with sqlite3.connect(store.db_path) as connection:
        assert connection.execute(
            """
            SELECT COUNT(*) FROM code_signals
            WHERE producer <> 'core_module' AND deleted_at IS NULL
            """
        ).fetchone()[0] == 0


def test_internal_v5_builder_refuses_future_schema_before_scanning_or_writes(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    index_dir = repo / ".context-search"
    index_dir.mkdir(parents=True)
    database = index_dir / "index.sqlite"
    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            CREATE TABLE index_metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at INTEGER NOT NULL
            )
            """
        )
        connection.execute(
            "INSERT INTO index_metadata VALUES ('signal_schema_version', '6', 1)"
        )
    before = database.read_bytes()
    scans: list[Path] = []

    def scanner(repo_path: Path, _config: ToolConfig):
        scans.append(repo_path)
        return []

    with pytest.raises(IncompatibleSignalSchemaError):
        build_v5_index_snapshot(
            repo,
            DEFAULT_CONFIG,
            graph_plugins=[],
            scanner=scanner,
        )

    assert scans == []
    assert database.read_bytes() == before
    assert not (repo / ".gitignore").exists()
    assert not (index_dir / "config.toml").exists()
    assert not (index_dir / "manifest.json").exists()


def test_internal_v5_builder_lock_contention_precedes_scan_and_embedding(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    index_dir = repo / ".context-search"
    index_dir.mkdir(parents=True)
    scans: list[Path] = []

    def scanner(repo_path: Path, _config: ToolConfig):
        scans.append(repo_path)
        return []

    with exclusive_index_lock(index_dir):
        with pytest.raises(IndexBusyError):
            build_v5_index_snapshot(
                repo,
                DEFAULT_CONFIG,
                graph_plugins=[],
                scanner=scanner,
            )

    assert scans == []
    assert not (repo / ".gitignore").exists()
    assert not (index_dir / "index.sqlite").exists()


def test_internal_v5_stale_and_full_recovery_choose_exact_rebuild_scope(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "App.java").write_text("class App {}\n", encoding="utf-8")
    (repo / "notes.md").write_text("", encoding="utf-8")
    reads: list[Path] = []

    def reader(repo_path, scanned_file, *, max_file_bytes):
        reads.append(scanned_file.path)
        return read_scanned_file_bytes(
            repo_path,
            scanned_file,
            max_file_bytes=max_file_bytes,
        )

    plugin = _RecordingGraphPlugin("java", [])
    build_v5_index_snapshot(
        repo,
        DEFAULT_CONFIG,
        graph_plugins=[plugin],
        scanner=scan_workspace_v5,
        file_reader=reader,
    )
    store = SQLiteStore(repo / ".context-search" / "index.sqlite")

    reads.clear()
    store.mark_graph_stale("stale_on_entry")
    stale = build_v5_index_snapshot(
        repo,
        DEFAULT_CONFIG,
        graph_plugins=[plugin],
        scanner=scan_workspace_v5,
        file_reader=reader,
    )
    assert stale.files_indexed == 1
    assert reads == [Path("App.java")]

    reads.clear()
    store.mark_graph_stale("full_reindex", full_reindex_required=True)
    full = build_v5_index_snapshot(
        repo,
        DEFAULT_CONFIG,
        graph_plugins=[plugin],
        scanner=scan_workspace_v5,
        file_reader=reader,
    )
    assert full.files_indexed == 2
    assert reads == [Path("App.java"), Path("notes.md")]


def test_internal_v5_changed_snapshot_is_stale_before_first_file_write(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    source_path = repo / "App.java"
    source_path.write_text("class App {}\n", encoding="utf-8")
    plugin = _RecordingGraphPlugin("java", [])
    build_v5_index_snapshot(
        repo,
        DEFAULT_CONFIG,
        graph_plugins=[plugin],
        scanner=scan_workspace_v5,
    )
    store = SQLiteStore(repo / ".context-search" / "index.sqlite")
    old_hash = store.source_file_for_path(Path("App.java")).sha256
    source_path.write_text("class App { int changed; }\n", encoding="utf-8")
    observed: list[tuple[str | None, str]] = []

    def stop_at_first_write(stage: str) -> None:
        if stage == "file_write_started":
            source = store.source_file_for_path(Path("App.java"))
            assert source is not None
            observed.append(
                (store.get_metadata(GRAPH_RESOLUTION_STATE_KEY), source.sha256)
            )
            raise RuntimeError("stop before file payload")

    with pytest.raises(RuntimeError, match="stop before file payload"):
        build_v5_index_snapshot(
            repo,
            DEFAULT_CONFIG,
            graph_plugins=[plugin],
            scanner=scan_workspace_v5,
            fault_hook=stop_at_first_write,
        )

    assert observed == [("stale", old_hash)]


def test_internal_v5_deletion_regenerates_unchanged_test_associations(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    production = repo / "src" / "main" / "java" / "demo" / "Service.java"
    test = repo / "src" / "test" / "java" / "demo" / "ServiceTest.java"
    production.parent.mkdir(parents=True)
    test.parent.mkdir(parents=True)
    production.write_text("package demo; class Service {}\n", encoding="utf-8")
    test.write_text("package demo; class ServiceTest {}\n", encoding="utf-8")

    build_v5_index_snapshot(
        repo,
        DEFAULT_CONFIG,
        graph_plugins=[JavaGraphProducer()],
        scanner=scan_workspace_v5,
    )
    database = repo / ".context-search" / "index.sqlite"
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            """
            SELECT COUNT(*) FROM code_relations
            WHERE kind = 'tests' AND deleted_at IS NULL
            """
        ).fetchone()[0] == 1

    production.unlink()
    summary = build_v5_index_snapshot(
        repo,
        DEFAULT_CONFIG,
        graph_plugins=[JavaGraphProducer()],
        scanner=scan_workspace_v5,
    )

    assert summary.files_deleted == 1
    assert summary.files_indexed == 0
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            """
            SELECT COUNT(*) FROM code_relations
            WHERE kind = 'tests' AND deleted_at IS NULL
            """
        ).fetchone()[0] == 0
    assert SQLiteStore(database).get_metadata(GRAPH_RESOLUTION_STATE_KEY) == "ready"


def test_internal_v5_topology_change_reextracts_unchanged_graph_files(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "App.java").write_text("class App {}\n", encoding="utf-8")
    (repo / "notes.md").write_text("notes\n", encoding="utf-8")
    reads: list[Path] = []

    def reader(repo_path, scanned_file, *, max_file_bytes):
        reads.append(scanned_file.path)
        return read_scanned_file_bytes(
            repo_path,
            scanned_file,
            max_file_bytes=max_file_bytes,
        )

    plugin = _RecordingGraphPlugin("java", [])
    build_v5_index_snapshot(
        repo,
        DEFAULT_CONFIG,
        graph_plugins=[plugin],
        scanner=scan_workspace_v5,
        file_reader=reader,
    )
    reads.clear()
    (repo / "pom.xml").write_text("<project/>\n", encoding="utf-8")

    summary = build_v5_index_snapshot(
        repo,
        DEFAULT_CONFIG,
        graph_plugins=[plugin],
        scanner=scan_workspace_v5,
        file_reader=reader,
    )

    assert summary.files_indexed == 3
    assert reads == [Path("App.java"), Path("notes.md"), Path("pom.xml")]


def test_internal_v5_vector_reader_fails_ready_and_skips_stale_mismatch(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "App.java").write_text("class App {}\n", encoding="utf-8")
    build_v5_index_snapshot(
        repo,
        DEFAULT_CONFIG,
        graph_plugins=[JavaGraphProducer()],
        scanner=scan_workspace_v5,
    )
    store = SQLiteStore(repo / ".context-search" / "index.sqlite")
    with store.graph_read_session() as session:
        snapshot = read_v5_vector_snapshot(repo, DEFAULT_CONFIG, session)
        assert snapshot is not None
        assert set(snapshot.ids) == session.active_embedding_ids()

    descriptor = NumpyVectorStore.published_descriptor(repo / ".context-search")
    assert descriptor is not None
    (repo / ".context-search" / descriptor.ids_file).write_text(
        '["tampered"]\n',
        encoding="utf-8",
    )
    with store.graph_read_session() as session:
        with pytest.raises(GraphIntegrityError, match="vector_snapshot_mismatch"):
            read_v5_vector_snapshot(repo, DEFAULT_CONFIG, session)

    store.mark_graph_stale("integrity_check_failed")
    caplog.clear()
    with store.graph_read_session() as session:
        assert read_v5_vector_snapshot(repo, DEFAULT_CONFIG, session) is None
    assert [record.message for record in caplog.records] == [
        "vector_snapshot_mismatch"
    ]
