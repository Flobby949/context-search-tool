from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sqlite3

import numpy as np
import pytest

from context_search_tool import indexer as indexer_module
from context_search_tool import sqlite_store as sqlite_store_module
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
from context_search_tool.manifest import (
    ManifestV2,
    load_manifest,
    prepare_manifest_v2,
    publish_manifest_v2,
)
from context_search_tool.models import CodeRelation, CodeSignal
from context_search_tool.mybatis_xml import MyBatisGraphProducer
from context_search_tool.scanner import read_scanned_file_bytes, scan_workspace_v5
from context_search_tool.sqlite_store import SQLiteStore
from context_search_tool.vector_store import (
    NumpyVectorStore,
    PreparedVectorGeneration,
)


class _SignalPlugin:
    def __init__(self, signals: list[CodeSignal], relations: list[CodeRelation]) -> None:
        self.signals = signals
        self.relations = relations

    def supports(self, context) -> bool:
        return context.language == "java"

    def parse(self, context, content: bytes) -> ParsedGraphFacts:
        return ParsedGraphFacts(facts=None)

    def materialize(self, context, parsed, chunks, module_signal) -> MaterializedGraph:
        chunk = chunks[0]
        signals = tuple(
            replace(signal, chunk_id=chunk.chunk_id, file_path=context.file_path)
            for signal in self.signals
        )
        return MaterializedGraph(signals=signals, relations=tuple(self.relations))


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


_BGE_CONFIG_HASH = "ed32afa6f3bfefa7375a51eb47cc65d565d8a5a067d51bda6cb9ac926705b929"
_HASH_CONFIG_HASH = "5ab1cee713aff995519814538508a44cece92c285a746094e1cab8b86c7745be"
_OPENAI_CONFIG_HASH = "f3e4a9a271cd25e4fec4ea9a6a7aa37f6ca9b9ba7d6de52b88da0d1c8d6b79cc"
_BGE_DIGEST = "1111111111111111111111111111111111111111111111111111111111111111"
_BGE_DRIFT_DIGEST = (
    "2222222222222222222222222222222222222222222222222222222222222222"
)
_BGE_VERSION = "0.30.10"
_BGE_IDENTITY = (
    "bge-ollama-v1:"
    "ed32afa6f3bfefa7375a51eb47cc65d565d8a5a067d51bda6cb9ac926705b929:"
    "1111111111111111111111111111111111111111111111111111111111111111:"
    "2a030a0065e54c79d856fc2b0a2b3f4c4cb5f81ed853fe99bccc2bbffe03e503:"
    "bge-input-v2"
)
_BGE_DIGEST_DRIFT_IDENTITY = (
    "bge-ollama-v1:"
    "ed32afa6f3bfefa7375a51eb47cc65d565d8a5a067d51bda6cb9ac926705b929:"
    "2222222222222222222222222222222222222222222222222222222222222222:"
    "2a030a0065e54c79d856fc2b0a2b3f4c4cb5f81ed853fe99bccc2bbffe03e503:"
    "bge-input-v2"
)
_BGE_VERSION_DRIFT_IDENTITY = (
    "bge-ollama-v1:"
    "ed32afa6f3bfefa7375a51eb47cc65d565d8a5a067d51bda6cb9ac926705b929:"
    "1111111111111111111111111111111111111111111111111111111111111111:"
    "e8b0cd5b6a434c25fc264f14215453212e8a2a9f2ee92853edcab28cf3ba369a:"
    "bge-input-v2"
)
_BGE_TRANSFORM_DRIFT_IDENTITY = (
    "bge-ollama-v1:"
    "ed32afa6f3bfefa7375a51eb47cc65d565d8a5a067d51bda6cb9ac926705b929:"
    "1111111111111111111111111111111111111111111111111111111111111111:"
    "2a030a0065e54c79d856fc2b0a2b3f4c4cb5f81ed853fe99bccc2bbffe03e503:"
    "bge-input-v1"
)


def _bge_config() -> ToolConfig:
    return replace(
        DEFAULT_CONFIG,
        embedding=EmbeddingConfig(
            provider="bge",
            model="bge-m3",
            dimensions=3,
            base_url="http://localhost:11434",
        ),
    )


class _AttestedBGEProvider:
    def __init__(
        self,
        config: ToolConfig,
        *,
        identity: str | None = None,
        digest: str = _BGE_DIGEST,
    ) -> None:
        self.config = config
        self.identity = identity or _BGE_IDENTITY
        self.digest = digest
        self.events: list[str] = []
        self.embedded_texts: list[str] = []
        self._egress = "not_attempted"

    def fingerprint(self) -> dict[str, object]:
        return {
            "provider": self.config.embedding.provider,
            "model": self.config.embedding.model,
            "dimensions": self.config.embedding.dimensions,
            "backend": "ollama",
        }

    def runtime_fingerprint(self) -> dict[str, object]:
        self.events.append("preflight")
        self._egress = "performed"
        return {
            "configured_model": self.config.embedding.model,
            "canonical_model": "bge-m3:latest",
            "model_digest": self.digest,
            "ollama_version": _BGE_VERSION,
            "base_url": self.config.embedding.base_url,
            "dimensions": self.config.embedding.dimensions,
            "input_transform_id": "bge-input-v2",
            "embedding_identity": self.identity,
        }

    def embed_texts(self, texts: list[str]) -> list[np.ndarray]:
        self.events.append("embed")
        self._egress = "performed"
        self.embedded_texts.extend(texts)
        vectors: list[np.ndarray] = []
        for text in texts:
            digest = hashlib.sha256(text.encode("utf-8")).digest()
            vector = np.asarray(
                [float(digest[index]) + 1.0 for index in range(3)],
                dtype=np.float32,
            )
            vectors.append(vector / np.linalg.norm(vector))
        return vectors

    def assert_runtime_unchanged(self) -> dict[str, object]:
        self.events.append("postflight")
        self._egress = "performed"
        return self.runtime_mapping()

    def runtime_mapping(self) -> dict[str, object]:
        return {
            "configured_model": self.config.embedding.model,
            "canonical_model": "bge-m3:latest",
            "model_digest": self.digest,
            "ollama_version": _BGE_VERSION,
            "base_url": self.config.embedding.base_url,
            "dimensions": self.config.embedding.dimensions,
            "input_transform_id": "bge-input-v2",
            "embedding_identity": self.identity,
        }

    @property
    def _network_egress_outcome(self) -> str:
        return self._egress


def _build_bge(
    repo: Path,
    provider: _AttestedBGEProvider,
    *,
    fault_hook=None,
):
    return build_v5_index_snapshot(
        repo,
        provider.config,
        graph_plugins=[JavaGraphProducer()],
        scanner=scan_workspace_v5,
        embedding_provider=provider,
        fault_hook=fault_hook,
    )


def _rebind_vector_identity(repo: Path, identity: str) -> None:
    index_dir = repo / ".context-search"
    descriptor = NumpyVectorStore.inspect_published_descriptor(index_dir)
    assert descriptor is not None
    publisher = NumpyVectorStore.fresh(
        index_dir,
        dimensions=descriptor.descriptor.dimensions,
    )
    publisher.publish_generation(
        PreparedVectorGeneration(
            index_dir,
            replace(descriptor.descriptor, embedding_identity=identity),
        )
    )
    rebound_descriptor = NumpyVectorStore.inspect_published_descriptor(index_dir)
    assert rebound_descriptor is not None

    manifest = load_manifest(repo)
    assert isinstance(manifest, ManifestV2)
    prepared_manifest = prepare_manifest_v2(
        replace(
            manifest,
            vector_descriptor_sha256=rebound_descriptor.sha256,
        )
    )
    publish_manifest_v2(repo, prepared_manifest)

    store = SQLiteStore(index_dir / "index.sqlite")
    operational = store.read_operational_snapshot()
    assert operational is not None
    topology = store.get_metadata("project_unit_topology_fingerprint")
    assert topology is not None
    store.commit_operational_ready_v1(
        binding=replace(
            operational.binding,
            manifest_sha256=prepared_manifest.sha256,
            vector_descriptor_sha256=rebound_descriptor.sha256,
        ),
        topology_fingerprint=topology,
        expected_embedding_ids=set(operational.active_embedding_ids),
        expected_source_count=operational.source_count,
        expected_chunk_count=operational.chunk_count,
        external_validator=lambda: None,
        graph_snapshot_unchanged=True,
    )


def test_fresh_v5_build_skips_absent_fts_payload_deletes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    source = repo / "App.java"
    source.write_text("class App { int alpha; }\n", encoding="utf-8")
    statements: list[str] = []
    real_open_connection = sqlite_store_module._open_connection

    def traced_connection(*args, **kwargs):
        connection = real_open_connection(*args, **kwargs)
        connection.set_trace_callback(statements.append)
        return connection

    monkeypatch.setattr(
        sqlite_store_module,
        "_open_connection",
        traced_connection,
    )

    index_repository(repo, DEFAULT_CONFIG)

    fresh_deletes = [
        statement
        for statement in statements
        if statement.lstrip().upper().startswith("DELETE FROM CHUNKS_FTS")
    ]
    assert fresh_deletes == []

    statements.clear()
    source.write_text("class App { int beta; }\n", encoding="utf-8")
    index_repository(repo, DEFAULT_CONFIG)
    changed_deletes = [
        statement
        for statement in statements
        if statement.lstrip().upper().startswith("DELETE FROM CHUNKS_FTS")
    ]
    assert len(changed_deletes) == 1
    store = SQLiteStore(repo / ".context-search" / "index.sqlite")
    results = store.lexical_search(["beta"], 10)
    assert results
    chunks = store.chunks_for_ids([result.chunk_id for result in results])
    assert all("alpha" not in chunks[result.chunk_id].content for result in results)


def _frontend_import_state(
    database: Path,
) -> tuple[str, str, tuple[str, ...]]:
    with sqlite3.connect(database) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            """
            SELECT resolution, target_signal_id, metadata
            FROM code_relations
            WHERE source_file_path = 'src/Importer.ts'
              AND kind = 'imports'
              AND target_name = './Target'
              AND deleted_at IS NULL
            """
        ).fetchone()
    assert row is not None
    metadata = json.loads(row["metadata"])
    return (
        str(row["resolution"]),
        str(row["target_signal_id"]),
        tuple(metadata["candidates"]),
    )


def test_index_repository_creates_expected_index_files(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "App.java").write_text("class App { String canApply; }\n", encoding="utf-8")

    summary = index_repository(repo, DEFAULT_CONFIG)

    assert summary.files_indexed == 1
    assert (repo / ".context-search" / "manifest.json").exists()
    assert (repo / ".context-search" / "index.sqlite").exists()
    assert (repo / ".context-search" / "vector_snapshot.json").exists()
    manifest = load_manifest(repo)
    assert isinstance(manifest, ManifestV2)
    assert manifest.total_chunks >= 1
    assert manifest.operation_mode == "authoritative_index"
    assert manifest.vector_descriptor_schema_version == 2
    operational = SQLiteStore(
        repo / ".context-search" / "index.sqlite"
    ).read_operational_snapshot()
    assert operational is not None
    assert operational.binding.manifest_generation == manifest.manifest_generation


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


def test_index_repository_persists_canonical_project_unit_test_metadata(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    files = {
        "packages/go/go.mod": "module example.com/go\n",
        "packages/go/upload_test.go": "package service\nfunc TestUpload() {}\n",
        "packages/go/fixture/payment.go": "package service\n",
        "packages/go/fixture/payment_test.go": "package service\n",
        "packages/rust/Cargo.toml": "[package]\nname = 'rust'\nversion = '0.1.0'\n",
        "packages/rust/tests/upload.rs": "#[test]\nfn upload() {}\n",
        "packages/python/pyproject.toml": "[project]\nname = 'python'\n",
        "packages/python/test_upload.py": "def test_upload():\n    pass\n",
        "packages/python/src/generated/payment.py": "def payment():\n    pass\n",
        "packages/python/src/generated/test_payment.py": "def test_payment():\n    pass\n",
        "packages/web/package.json": "{\"name\": \"web\"}\n",
        "packages/web/upload.test.js": "test('upload', () => {})\n",
        "packages/web/upload.spec.ts": "test('upload', () => {})\n",
        "packages/web/testdata/payment.js": "export const payment = () => {}\n",
        "packages/web/testdata/payment.test.js": "test('payment', () => {})\n",
        "packages/java/pom.xml": "<project></project>\n",
        "packages/java/src/test/java/demo/UploadIT.java": "class UploadIT {}\n",
    }
    for relative_path, content in files.items():
        source = repo / relative_path
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(content, encoding="utf-8")

    summary = index_repository(repo, DEFAULT_CONFIG)

    store = SQLiteStore(repo / ".context-search" / "index.sqlite")
    test_paths = {
        "packages/go/upload_test.go",
        "packages/go/fixture/payment_test.go",
        "packages/rust/tests/upload.rs",
        "packages/python/test_upload.py",
        "packages/python/src/generated/test_payment.py",
        "packages/web/upload.test.js",
        "packages/web/upload.spec.ts",
        "packages/web/testdata/payment.test.js",
        "packages/java/src/test/java/demo/UploadIT.java",
    }
    assert summary.files_seen >= len(test_paths)
    for path in test_paths:
        source = store.source_file_for_path(Path(path))
        assert source is not None
        assert source.is_test
        chunk = store.chunk_for_line(Path(path), 1)
        assert chunk.metadata["is_test"]

    for path in (
        "packages/go/fixture/payment.go",
        "packages/python/src/generated/payment.py",
        "packages/web/testdata/payment.js",
    ):
        source = store.source_file_for_path(Path(path))
        assert source is not None
        assert not source.is_test

    with sqlite3.connect(repo / ".context-search" / "index.sqlite") as connection:
        assert connection.execute(
            """
            SELECT COUNT(*) FROM code_relations
            WHERE kind = 'tests' AND deleted_at IS NULL
            """
        ).fetchone()[0] == 0


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
    assert (repo / ".context-search" / "vector_snapshot.json").exists()


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
    with store.graph_read_session() as session:
        stored_signal = session.signal_search(["app"], limit=10)[0]
        stored_signals = session.signals_for_chunk(stored_signal.chunk_id)
    assert stored_signal.signal_id == "sig-app"
    assert stored_signal.chunk_id != "plugin-placeholder"
    assert stored_signal in stored_signals


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
    with store.graph_read_session() as session:
        assert session.signal_search(["old"], limit=10)[0].signal_id == "sig-old"
    store.set_metadata(SIGNAL_SCHEMA_VERSION_KEY, "3")

    monkeypatch.setattr(
        "context_search_tool.indexer.default_plugins",
        lambda: [_SignalPlugin([new_signal], [])],
    )
    summary = index_repository(repo, DEFAULT_CONFIG)

    assert summary.files_indexed == 1
    with store.graph_read_session() as session:
        assert session.signal_search(["old"], limit=10) == []
        assert session.signal_search(["new", "signal"], limit=10)[0].signal_id == "sig-new"
    assert store.get_metadata(SIGNAL_SCHEMA_VERSION_KEY) == "5"


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
    (index_dir / "vector_snapshot.json").write_text("not json", encoding="utf-8")
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


@pytest.mark.parametrize(
    (
        "initial_targets",
        "changed_target",
        "delete_target",
        "expected_before",
        "expected_after",
        "expected_counts",
    ),
    [
        (
            (),
            "Target.ts",
            False,
            ("unresolved", False, ()),
            ("resolved_unique", True, ("src/Target.ts",)),
            (2, 0),
        ),
        (
            ("Target.ts",),
            "Target.js",
            False,
            ("resolved_unique", True, ("src/Target.ts",)),
            ("ambiguous", False, ("src/Target.ts", "src/Target.js")),
            (2, 0),
        ),
        (
            ("Target.ts", "Target.js"),
            "Target.js",
            True,
            ("ambiguous", False, ("src/Target.ts", "src/Target.js")),
            ("resolved_unique", True, ("src/Target.ts",)),
            (1, 1),
        ),
    ],
)
def test_incremental_path_change_rematerializes_frontend_selectors(
    tmp_path: Path,
    initial_targets: tuple[str, ...],
    changed_target: str,
    delete_target: bool,
    expected_before: tuple[str, bool, tuple[str, ...]],
    expected_after: tuple[str, bool, tuple[str, ...]],
    expected_counts: tuple[int, int],
) -> None:
    repo = tmp_path / "repo"
    source_dir = repo / "src"
    source_dir.mkdir(parents=True)
    (source_dir / "Importer.ts").write_text(
        "import value from './Target';\nexport { value };\n",
        encoding="utf-8",
    )
    for index, target in enumerate(initial_targets, start=1):
        (source_dir / target).write_text(
            f"export default {index};\n",
            encoding="utf-8",
        )

    index_repository(repo, DEFAULT_CONFIG)
    database = repo / ".context-search" / "index.sqlite"
    before_resolution, before_target, before_candidates = _frontend_import_state(
        database
    )
    assert (before_resolution, bool(before_target), before_candidates) == expected_before

    changed_path = source_dir / changed_target
    if delete_target:
        changed_path.unlink()
    else:
        changed_path.write_text("export default 3;\n", encoding="utf-8")
    summary = index_repository(repo, DEFAULT_CONFIG)

    after_resolution, after_target, after_candidates = _frontend_import_state(database)
    assert (after_resolution, bool(after_target), after_candidates) == expected_after
    assert (summary.files_indexed, summary.files_deleted) == expected_counts
    assert SQLiteStore(database).graph_integrity().ok
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


def test_quick_refresh_path_addition_rematerializes_persisted_import_sources(
    tmp_path: Path,
) -> None:
    refresh = getattr(indexer_module, "refresh_repository", None)
    assert callable(refresh), "P6 internal quick-refresh entry is absent"
    repo = tmp_path / "repo"
    source_dir = repo / "src"
    source_dir.mkdir(parents=True)
    (source_dir / "Importer.ts").write_text(
        "import value from './Target';\nexport { value };\n",
        encoding="utf-8",
    )
    index_repository(repo, DEFAULT_CONFIG)
    database = repo / ".context-search" / "index.sqlite"
    assert _frontend_import_state(database) == ("unresolved", "", ())

    (source_dir / "Target.ts").write_text(
        "export default 1;\n",
        encoding="utf-8",
    )
    result = refresh(
        repo,
        DEFAULT_CONFIG,
        graph_plugins=[FrontendGraphProducer()],
    )

    assert result.ok is True
    assert result.summary.files.direct_dirty == 1
    assert result.summary.files.content_changed == 1
    assert result.summary.files.dependent_rebuild == 1
    assert [item.to_dict() for item in result.summary.files.dependent_rebuilds] == [
        {"reason": "path_inventory_changed", "files": 1}
    ]
    resolution, target, candidates = _frontend_import_state(database)
    assert (resolution, bool(target), candidates) == (
        "resolved_unique",
        True,
        ("src/Target.ts",),
    )
    assert SQLiteStore(database).graph_integrity().ok


def test_quick_refresh_stale_entry_reason_matrix_never_uses_noop(
    tmp_path: Path,
) -> None:
    refresh = getattr(indexer_module, "refresh_repository", None)
    assert callable(refresh), "P6 internal quick-refresh entry is absent"
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "App.java").write_text("class App {}\n", encoding="utf-8")
    index_repository(repo, DEFAULT_CONFIG)
    store = SQLiteStore(repo / ".context-search" / "index.sqlite")

    store.mark_graph_stale("files_changed")
    recovered = refresh(
        repo,
        DEFAULT_CONFIG,
        graph_plugins=[JavaGraphProducer()],
    )
    assert recovered.ok is True
    assert recovered.summary.files.dependent_rebuild == 1
    assert recovered.summary.files.parsed == 1
    assert recovered.summary.work.vector.descriptor_action == "reused"
    assert store.get_metadata(GRAPH_RESOLUTION_STATE_KEY) == "ready"

    store.mark_graph_stale("integrity_check_failed")
    before = (repo / ".context-search" / "index.sqlite").read_bytes()
    rejected = refresh(
        repo,
        DEFAULT_CONFIG,
        graph_plugins=[JavaGraphProducer()],
    )
    assert rejected.ok is False
    assert rejected.code == "authoritative_index_required"
    assert rejected.network_egress_outcome == "not_attempted"
    assert (repo / ".context-search" / "index.sqlite").read_bytes() == before


def _create_layout_v1_index(db_path: Path) -> None:
    with sqlite3.connect(db_path) as connection:
        connection.executescript(
            """
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
            CREATE TABLE chunk_tokens (
                chunk_id TEXT NOT NULL,
                token TEXT NOT NULL
            );
            CREATE TABLE index_metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at INTEGER NOT NULL
            );
            INSERT INTO chunks VALUES
                ('old-1', 'App.java', 1, 5, 'class App {}',
                 'symbol', 'old-1', NULL, '{}');
            INSERT INTO chunk_tokens VALUES ('old-1', 'app');
            """
        )


def test_index_repository_resets_and_rebuilds_layout_v1_index(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "App.java").write_text("class App { String canApply; }\n", encoding="utf-8")
    index_dir = repo / ".context-search"
    index_dir.mkdir()
    _create_layout_v1_index(index_dir / "index.sqlite")
    (index_dir / "manifest.json").write_text("{}", encoding="utf-8")
    (index_dir / "vectors.npy").write_bytes(b"stale")
    (index_dir / "vector_ids.deadbeef.json").write_text("[]", encoding="utf-8")
    (index_dir / "mcp_calls.jsonl").write_text('{"kept": true}\n', encoding="utf-8")

    summary = index_repository(repo, DEFAULT_CONFIG)

    assert summary.files_indexed == 1
    store = SQLiteStore(index_dir / "index.sqlite")
    store.require_current_storage_layout()
    with sqlite3.connect(index_dir / "index.sqlite") as connection:
        columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(chunk_tokens)")
        }
        chunk_count = connection.execute(
            "SELECT COUNT(*) FROM chunks WHERE deleted_at IS NULL"
        ).fetchone()[0]
    assert columns == {"chunk_ref", "token"}
    assert chunk_count >= 1
    assert json.loads((index_dir / "manifest.json").read_text()) != {}
    stale_vectors = index_dir / "vectors.npy"
    assert not stale_vectors.exists() or stale_vectors.read_bytes() != b"stale"
    assert not (index_dir / "vector_ids.deadbeef.json").exists()
    assert (index_dir / "mcp_calls.jsonl").read_text() == '{"kept": true}\n'


def test_index_repository_rejects_future_storage_layout(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "App.java").write_text("class App {}\n", encoding="utf-8")
    index_dir = repo / ".context-search"
    index_dir.mkdir()
    _create_layout_v1_index(index_dir / "index.sqlite")
    with sqlite3.connect(index_dir / "index.sqlite") as connection:
        connection.execute(
            "INSERT INTO index_metadata VALUES ('storage_layout_version', '3', 0)"
        )

    with pytest.raises(sqlite_store_module.IncompatibleStorageLayoutError):
        index_repository(repo, DEFAULT_CONFIG)


def test_bge_index_binds_runtime_descriptor_without_changing_static_manifest(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "App.java").write_text(
        "class App { int runtimeIdentity; }\n",
        encoding="utf-8",
    )
    config = _bge_config()
    provider = _AttestedBGEProvider(config)

    _build_bge(repo, provider)

    manifest = load_manifest(repo)
    descriptor = NumpyVectorStore.inspect_published_descriptor(
        repo / ".context-search"
    )
    assert isinstance(manifest, ManifestV2)
    assert descriptor is not None
    assert manifest.embedding_config_hash == _BGE_CONFIG_HASH
    assert descriptor.descriptor.embedding_identity == _BGE_IDENTITY
    assert descriptor.sha256 == manifest.vector_descriptor_sha256
    assert provider.events == ["preflight", "embed", "postflight"]
    assert provider.runtime_mapping()["ollama_version"] == _BGE_VERSION

    store = SQLiteStore(repo / ".context-search" / "index.sqlite")
    operational = store.read_operational_snapshot()
    assert operational is not None
    assert operational.graph_status == "ready"
    assert operational.binding.vector_descriptor_sha256 == descriptor.sha256
    with store.graph_read_session() as session:
        loaded = read_v5_vector_snapshot(repo, config, session)
    assert loaded is not None
    assert loaded.embedding_identity == _BGE_IDENTITY


def test_configured_bge_rejects_provider_without_runtime_attestation(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "App.java").write_text("class App {}\n", encoding="utf-8")
    config = _bge_config()

    class StaticOnlyProvider:
        embed_calls = 0

        def fingerprint(self) -> dict[str, object]:
            return {
                "provider": "bge",
                "model": "bge-m3",
                "dimensions": 3,
            }

        def embed_texts(self, texts: list[str]) -> list[np.ndarray]:
            self.embed_calls += 1
            return [
                np.asarray([1.0, 0.0, 0.0], dtype=np.float32)
                for _ in texts
            ]

    provider = StaticOnlyProvider()
    with pytest.raises(ValueError) as caught:
        build_v5_index_snapshot(
            repo,
            config,
            graph_plugins=[JavaGraphProducer()],
            scanner=scan_workspace_v5,
            embedding_provider=provider,
        )

    assert type(caught.value) is ValueError
    assert provider.embed_calls == 0


def test_bge_exact_runtime_identity_reuses_ready_vectors_and_validators(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "App.java").write_text(
        "class App { int exactIdentity; }\n",
        encoding="utf-8",
    )
    config = _bge_config()
    _build_bge(repo, _AttestedBGEProvider(config))
    before = NumpyVectorStore.inspect_published_descriptor(
        repo / ".context-search"
    )
    assert before is not None
    provider = _AttestedBGEProvider(config)

    summary = _build_bge(repo, provider)

    after = NumpyVectorStore.inspect_published_descriptor(
        repo / ".context-search"
    )
    assert after is not None
    assert summary.files_indexed == 0
    assert summary.chunks_indexed == 0
    assert after == before
    assert provider.events == ["preflight"]

    store = SQLiteStore(repo / ".context-search" / "index.sqlite")
    with store.graph_read_session() as session:
        loaded = read_v5_vector_snapshot(repo, config, session)
    assert loaded is not None
    assert loaded.embedding_identity == _BGE_IDENTITY


def test_bge_zero_row_digest_drift_publishes_new_attested_generation(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    config = _bge_config()
    initial_provider = _AttestedBGEProvider(config)

    initial_summary = _build_bge(repo, initial_provider)

    index_dir = repo / ".context-search"
    before = NumpyVectorStore.inspect_published_descriptor(index_dir)
    assert before is not None
    assert initial_summary.files_seen == 0
    assert initial_summary.files_indexed == 0
    assert initial_summary.chunks_indexed == 0
    assert initial_provider.events == ["preflight"]
    assert initial_provider.embedded_texts == []
    assert before.descriptor.row_count == 0
    assert before.descriptor.dimensions == 3
    assert before.descriptor.embedding_identity == _BGE_IDENTITY

    drifted_provider = _AttestedBGEProvider(
        config,
        identity=_BGE_DIGEST_DRIFT_IDENTITY,
        digest=_BGE_DRIFT_DIGEST,
    )

    drifted_summary = _build_bge(repo, drifted_provider)

    after = NumpyVectorStore.inspect_published_descriptor(index_dir)
    assert after is not None
    assert drifted_summary.files_seen == 0
    assert drifted_summary.files_indexed == 0
    assert drifted_summary.chunks_indexed == 0
    assert drifted_provider.events == ["preflight"]
    assert drifted_provider.embedded_texts == []
    assert after.descriptor.generation != before.descriptor.generation
    assert after.descriptor.row_count == 0
    assert after.descriptor.dimensions == 3
    assert after.descriptor.embedding_identity == _BGE_DIGEST_DRIFT_IDENTITY
    assert (index_dir / after.descriptor.vectors_file).is_file()
    assert (index_dir / after.descriptor.ids_file).is_file()

    manifest = load_manifest(repo)
    operational = SQLiteStore(
        index_dir / "index.sqlite"
    ).read_operational_snapshot()
    assert isinstance(manifest, ManifestV2)
    assert operational is not None
    assert manifest.vector_descriptor_sha256 == after.sha256
    assert operational.graph_status == "ready"
    assert operational.binding.vector_descriptor_sha256 == after.sha256
    assert (
        operational.binding.vector_generation
        == after.descriptor.generation
    )
    with SQLiteStore(index_dir / "index.sqlite").graph_read_session() as session:
        loaded = read_v5_vector_snapshot(repo, config, session)
    assert loaded is not None
    assert loaded.ids == ()
    assert loaded.embedding_identity == _BGE_DIGEST_DRIFT_IDENTITY


@pytest.mark.parametrize(
    "stored_identity_kind",
    ["legacy", "digest", "version", "transform", "malformed"],
)
def test_bge_unattested_or_drifted_identity_forces_complete_vector_rebuild(
    tmp_path: Path,
    stored_identity_kind: str,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "Alpha.java").write_text(
        "class Alpha { int alphaRuntime; }\n",
        encoding="utf-8",
    )
    (repo / "Beta.java").write_text(
        "class Beta { int betaRuntime; }\n",
        encoding="utf-8",
    )
    config = _bge_config()
    live_identity = _BGE_IDENTITY
    _build_bge(repo, _AttestedBGEProvider(config))
    stale_identities = {
        "legacy": _BGE_CONFIG_HASH,
        "digest": _BGE_DIGEST_DRIFT_IDENTITY,
        "version": _BGE_VERSION_DRIFT_IDENTITY,
        "transform": _BGE_TRANSFORM_DRIFT_IDENTITY,
        "malformed": "bge-ollama-v1:malformed",
    }
    _rebind_vector_identity(repo, stale_identities[stored_identity_kind])
    before = NumpyVectorStore.inspect_published_descriptor(
        repo / ".context-search"
    )
    assert before is not None
    provider = _AttestedBGEProvider(config)

    summary = _build_bge(repo, provider)

    after = NumpyVectorStore.inspect_published_descriptor(
        repo / ".context-search"
    )
    assert after is not None
    assert summary.files_indexed == summary.files_seen == 2
    assert summary.chunks_indexed == after.descriptor.row_count
    assert provider.events == ["preflight", "embed", "postflight"]
    assert after.descriptor.generation != before.descriptor.generation
    assert after.descriptor.embedding_identity == live_identity


def test_bge_stale_graph_reuses_actual_descriptor_identity(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "App.java").write_text(
        "class App { int staleGraph; }\n",
        encoding="utf-8",
    )
    config = _bge_config()
    _build_bge(repo, _AttestedBGEProvider(config))
    before = NumpyVectorStore.inspect_published_descriptor(
        repo / ".context-search"
    )
    assert before is not None
    store = SQLiteStore(repo / ".context-search" / "index.sqlite")
    store.mark_graph_stale("files_changed")
    provider = _AttestedBGEProvider(config)

    summary = _build_bge(repo, provider)

    after = NumpyVectorStore.inspect_published_descriptor(
        repo / ".context-search"
    )
    assert after is not None
    assert summary.files_indexed == 1
    assert summary.chunks_indexed == 0
    assert provider.events == ["preflight"]
    assert after == before
    assert store.get_metadata(GRAPH_RESOLUTION_STATE_KEY) == "ready"


@pytest.mark.parametrize("provider_name", ["hash", "openai-compatible"])
def test_non_bge_descriptor_identity_remains_the_static_config_hash(
    tmp_path: Path,
    provider_name: str,
) -> None:
    repo = tmp_path / provider_name
    repo.mkdir()
    (repo / "App.java").write_text("class App {}\n", encoding="utf-8")
    if provider_name == "hash":
        config = DEFAULT_CONFIG
        provider = None
    else:
        config = replace(
            DEFAULT_CONFIG,
            embedding=EmbeddingConfig(
                provider="openai-compatible",
                model="fixture-embedding",
                dimensions=3,
                base_url="https://example.test/v1",
            ),
        )

        class StaticProvider:
            def fingerprint(self) -> dict[str, object]:
                return {
                    "provider": "openai-compatible",
                    "model": "fixture-embedding",
                    "dimensions": 3,
                }

            def embed_texts(self, texts: list[str]) -> list[np.ndarray]:
                return [
                    np.asarray([1.0, 0.0, 0.0], dtype=np.float32)
                    for _ in texts
                ]

        provider = StaticProvider()

    build_v5_index_snapshot(
        repo,
        config,
        graph_plugins=[JavaGraphProducer()],
        scanner=scan_workspace_v5,
        embedding_provider=provider,
    )

    manifest = load_manifest(repo)
    descriptor = NumpyVectorStore.inspect_published_descriptor(
        repo / ".context-search"
    )
    assert isinstance(manifest, ManifestV2)
    assert descriptor is not None
    expected = (
        _HASH_CONFIG_HASH
        if provider_name == "hash"
        else _OPENAI_CONFIG_HASH
    )
    assert manifest.embedding_config_hash == expected
    assert descriptor.descriptor.embedding_identity == expected
