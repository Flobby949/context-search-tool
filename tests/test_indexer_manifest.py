from pathlib import Path

import pytest

from context_search_tool.config import (
    DEFAULT_CONFIG,
    EmbeddingConfig,
    ToolConfig,
    load_config,
)
from context_search_tool.indexer import IncompatibleIndexError, index_repository
from context_search_tool.manifest import load_manifest


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
