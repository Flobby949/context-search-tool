from pathlib import Path

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
    index_repository,
)
from context_search_tool.manifest import load_manifest
from context_search_tool.models import CodeRelation, CodeSignal
from context_search_tool.plugins import PluginExtraction
from context_search_tool.sqlite_store import SQLiteStore


class _SignalPlugin:
    def __init__(self, signals: list[CodeSignal], relations: list[CodeRelation]) -> None:
        self.signals = signals
        self.relations = relations

    def supports(self, path: Path, language: str) -> bool:
        return language == "java"

    def extract(self, path: Path, content: str) -> PluginExtraction:
        return PluginExtraction(signals=self.signals, relations=self.relations)


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
