from __future__ import annotations

import json
import os
from pathlib import Path
import sqlite3
from typing import Any

import pytest

from context_search_tool import indexer as indexer_module
from context_search_tool.config import DEFAULT_CONFIG
from context_search_tool.graph_lifecycle import GRAPH_RESOLUTION_STATE_KEY
from context_search_tool.graph_plugins import MaterializedGraph, ParsedGraphFacts
from context_search_tool.indexer import build_v5_index_snapshot, index_repository
from context_search_tool.manifest import ManifestV2, load_manifest
from context_search_tool.scanner import (
    observe_workspace,
    read_observed_file,
    scan_workspace_v5,
)
from context_search_tool.sqlite_store import SQLiteStore
from context_search_tool.vector_store import NumpyVectorStore


class _RecordingPlugin:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    def supports(self, context: Any) -> bool:
        return context.language == "java"

    def parse(self, context: Any, content: bytes) -> ParsedGraphFacts:
        self.events.append(f"parse:{context.file_path.as_posix()}")
        return ParsedGraphFacts(facts=None)

    def materialize(
        self,
        context: Any,
        parsed: ParsedGraphFacts,
        chunks: tuple[Any, ...],
        module_signal: Any,
    ) -> MaterializedGraph:
        self.events.append(f"materialize:{context.file_path.as_posix()}")
        return MaterializedGraph()


def _build(
    repo: Path,
    *,
    events: list[str] | None = None,
    **kwargs: Any,
):
    recorded = events if events is not None else []
    return build_v5_index_snapshot(
        repo,
        DEFAULT_CONFIG,
        graph_plugins=[_RecordingPlugin(recorded)],
        scanner=scan_workspace_v5,
        **kwargs,
    )


def _snapshot_bytes(repo: Path) -> tuple[bytes, bytes, bytes]:
    index_dir = repo / ".context-search"
    return (
        (index_dir / "manifest.json").read_bytes(),
        (index_dir / "vector_snapshot.json").read_bytes(),
        (index_dir / "index.sqlite").read_bytes(),
    )


def test_authoritative_prepares_and_closes_inventory_before_stale(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "App.java").write_text("class App {}\n", encoding="utf-8")
    events: list[str] = []
    inventory_calls = 0

    def inventory_reader(repo_path: Path, config: Any):
        nonlocal inventory_calls
        inventory_calls += 1
        events.append("opening_inventory" if inventory_calls == 1 else "closing_inventory")
        return observe_workspace(repo_path, config)

    def source_reader(repo_path: Path, observation: Any, **kwargs: Any):
        events.append(f"hash:{observation.path.as_posix()}")
        return read_observed_file(repo_path, observation, **kwargs)

    def observe_stage(stage: str) -> None:
        events.append(stage)
        if stage == "stale_committed":
            assert events.index("opening_inventory") < events.index("hash:App.java")
            assert events.index("hash:App.java") < events.index("parse:App.java")
            assert events.index("parse:App.java") < events.index("closing_inventory")
            assert events.index("closing_inventory_complete") < events.index(
                "stale_committed"
            )

    _build(
        repo,
        events=events,
        inventory_observer=inventory_reader,
        observed_reader=source_reader,
        fault_hook=observe_stage,
    )

    assert inventory_calls == 2
    assert isinstance(load_manifest(repo), ManifestV2)


def test_closing_inventory_drift_preserves_prior_ready_snapshot(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    source = repo / "App.java"
    source.write_text("class App { int oldValue; }\n", encoding="utf-8")
    index_repository(repo, DEFAULT_CONFIG)
    before = _snapshot_bytes(repo)
    calls = 0

    def drifting_inventory(repo_path: Path, config: Any):
        nonlocal calls
        calls += 1
        if calls == 2:
            source.write_text("class App { int newValue; }\n", encoding="utf-8")
        return observe_workspace(repo_path, config)

    error_type = getattr(indexer_module, "WorkspaceChangedError", ValueError)
    with pytest.raises(error_type):
        _build(repo, inventory_observer=drifting_inventory)

    store = SQLiteStore(repo / ".context-search" / "index.sqlite")
    assert store.get_metadata(GRAPH_RESOLUTION_STATE_KEY) == "ready"
    assert _snapshot_bytes(repo) == before


def test_authoritative_noop_hashes_every_source_without_parse_or_embedding(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "App.java").write_text("class App {}\n", encoding="utf-8")
    (repo / "notes.md").write_text("notes\n", encoding="utf-8")
    _build(repo)
    reads: list[Path] = []
    events: list[str] = []

    def source_reader(repo_path: Path, observation: Any, **kwargs: Any):
        reads.append(observation.path)
        return read_observed_file(repo_path, observation, **kwargs)

    class _ForbiddenProvider:
        def fingerprint(self) -> dict[str, object]:
            raise AssertionError("no-op constructed or validated an embedding provider")

        def embed_texts(self, texts: list[str]):
            raise AssertionError("no-op sent unchanged source for embedding")

    summary = _build(
        repo,
        events=events,
        observed_reader=source_reader,
        embedding_provider=_ForbiddenProvider(),
    )

    assert reads == [Path("App.java"), Path("notes.md")]
    assert events == []
    assert summary.files_indexed == 0
    manifest = load_manifest(repo)
    assert isinstance(manifest, ManifestV2)
    work = dict(manifest.work_metrics)
    assert work["source.files_hashed"] == 2
    assert work["source.bytes_hashed"] == len(b"class App {}\nnotes\n")
    assert work["files.parsed"] == 0
    assert work["chunks.embedded"] == 0
    assert work["vector.descriptor_action"] == "reused"


def test_authoritative_hash_detects_same_size_same_mtime_content_edit(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    source = repo / "App.java"
    source.write_text("class App { int aa; }\n", encoding="utf-8")
    index_repository(repo, DEFAULT_CONFIG)
    before = source.stat()
    source.write_text("class App { int bb; }\n", encoding="utf-8")
    os.utime(source, ns=(before.st_atime_ns, before.st_mtime_ns))

    summary = index_repository(repo, DEFAULT_CONFIG)

    assert summary.files_indexed == 1
    stored = SQLiteStore(repo / ".context-search" / "index.sqlite").source_file_for_path(
        Path("App.java")
    )
    assert stored is not None
    assert stored.sha256 != ""
    assert stored.sha256 == __import__("hashlib").sha256(source.read_bytes()).hexdigest()


def test_manifest_v1_upgrade_reuses_the_immutable_vector_payload(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "App.java").write_text("class App {}\n", encoding="utf-8")
    index_repository(repo, DEFAULT_CONFIG)
    index_dir = repo / ".context-search"
    descriptor_path = index_dir / "vector_snapshot.json"
    descriptor = json.loads(descriptor_path.read_text(encoding="utf-8"))
    for key in ("vectors_bytes", "ids_bytes", "normalization"):
        descriptor.pop(key, None)
    descriptor["schema_version"] = 1
    descriptor_path.write_text(
        json.dumps(descriptor, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    vector_path = index_dir / descriptor["vectors_file"]
    ids_path = index_dir / descriptor["ids_file"]
    vector_before = vector_path.read_bytes()
    ids_before = ids_path.read_bytes()
    generation = descriptor["generation"]
    manifest = load_manifest(repo)
    legacy_manifest = {
        "schema_version": 1,
        "embedding_config_hash": manifest.embedding_config_hash,
        "embedding_provider": manifest.embedding_provider,
        "embedding_model": manifest.embedding_model,
        "embedding_dimensions": manifest.embedding_dimensions,
        "total_files": manifest.total_files,
        "total_chunks": manifest.total_chunks,
    }
    (index_dir / "manifest.json").write_text(
        json.dumps(legacy_manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    with sqlite3.connect(index_dir / "index.sqlite") as connection:
        connection.execute("DELETE FROM index_metadata WHERE key LIKE 'operational_%'")

    class _ForbiddenProvider:
        def fingerprint(self) -> dict[str, object]:
            raise AssertionError("v1 upgrade validated an unused provider")

        def embed_texts(self, texts: list[str]):
            raise AssertionError("v1 upgrade re-embedded unchanged source")

    summary = _build(repo, embedding_provider=_ForbiddenProvider())

    upgraded_descriptor = NumpyVectorStore.inspect_published_descriptor(index_dir)
    assert upgraded_descriptor is not None
    assert upgraded_descriptor.descriptor.schema_version == 2
    assert upgraded_descriptor.descriptor.generation == generation
    assert vector_path.read_bytes() == vector_before
    assert ids_path.read_bytes() == ids_before
    assert summary.files_indexed == 0
    assert isinstance(load_manifest(repo), ManifestV2)
    assert SQLiteStore(index_dir / "index.sqlite").read_operational_snapshot() is not None


def test_config_edit_after_closing_fence_is_not_overwritten(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "App.java").write_text("class App {}\n", encoding="utf-8")
    edited = b"[index]\nexclude = [\"App.java\"]\n"

    def edit_after_fence(stage: str) -> None:
        if stage == "closing_inventory_complete":
            (repo / ".context-search" / "config.toml").write_bytes(edited)

    _build(repo, fault_hook=edit_after_fence)

    assert (repo / ".context-search" / "config.toml").read_bytes() == edited
