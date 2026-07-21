from __future__ import annotations

import json
import os
from dataclasses import replace
from pathlib import Path
import sqlite3
from typing import Any

import pytest

from context_search_tool import indexer as indexer_module
from context_search_tool.config import DEFAULT_CONFIG, EmbeddingConfig
from context_search_tool.graph_lifecycle import (
    GRAPH_RESOLUTION_STATE_KEY,
    OPERATIONAL_SCHEMA_VERSION_KEY,
)
from context_search_tool.graph_plugins import MaterializedGraph, ParsedGraphFacts
from context_search_tool.index_lock import exclusive_index_lock
from context_search_tool.indexer import build_v5_index_snapshot, index_repository
from context_search_tool.manifest import Manifest, ManifestV2, load_manifest, write_manifest
from context_search_tool.scanner import (
    ObservedFileRead,
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


def _refresh(
    repo: Path,
    config: Any = DEFAULT_CONFIG,
    *,
    events: list[str] | None = None,
    **kwargs: Any,
):
    refresh = getattr(indexer_module, "refresh_repository", None)
    assert callable(refresh), "P6 internal quick-refresh entry is absent"
    recorded = events if events is not None else []
    return refresh(
        repo,
        config,
        graph_plugins=[_RecordingPlugin(recorded)],
        **kwargs,
    )


def test_repository_path_index_built_once_per_operation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    index_type = getattr(indexer_module, "RepositoryPathIndex", None)
    assert index_type is not None, "shared repository path index is absent"

    repo = tmp_path / "repo"
    repo.mkdir()
    for name in ("Alpha.java", "Beta.java", "Gamma.java"):
        (repo / name).write_text(f"class {name[:-5]} {{}}\n", encoding="utf-8")

    built_indexes: list[Any] = []
    real_index_type = index_type

    def tracked_index(*args: Any, **kwargs: Any) -> Any:
        index = real_index_type(*args, **kwargs)
        built_indexes.append(index)
        return index

    monkeypatch.setattr(indexer_module, "RepositoryPathIndex", tracked_index)
    contexts: list[Any] = []

    class RecordingPathPlugin(_RecordingPlugin):
        def parse(self, context: Any, content: bytes) -> ParsedGraphFacts:
            contexts.append(context)
            return super().parse(context, content)

    plugin = RecordingPathPlugin([])
    build_v5_index_snapshot(
        repo,
        DEFAULT_CONFIG,
        graph_plugins=[plugin],
        scanner=scan_workspace_v5,
    )

    assert len(built_indexes) == 1
    assert len(contexts) == 3
    assert all(
        context.repository_path_index is built_indexes[0] for context in contexts
    )

    contexts.clear()
    (repo / "Alpha.java").write_text("class Alpha { int changed; }\n", encoding="utf-8")
    refresh = getattr(indexer_module, "refresh_repository", None)
    assert callable(refresh)
    result = refresh(
        repo,
        DEFAULT_CONFIG,
        graph_plugins=[plugin],
    )

    assert result.ok is True
    assert len(built_indexes) == 2
    assert contexts
    assert all(
        context.repository_path_index is built_indexes[1] for context in contexts
    )
    assert result.summary.work.path_index.builds == 1
    assert result.summary.work.path_index.paths_canonicalized == 3


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


def test_quick_refresh_missing_legacy_and_busy_are_non_mutating(
    tmp_path: Path,
) -> None:
    missing = tmp_path / "missing"
    missing.mkdir()
    missing_result = _refresh(missing)
    assert missing_result.ok is False
    assert missing_result.code == "missing_index"
    assert missing_result.network_egress_outcome == "not_attempted"
    assert not (missing / ".context-search").exists()

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "App.java").write_text("class App {}\n", encoding="utf-8")
    index_repository(repo, DEFAULT_CONFIG)
    current = load_manifest(repo)
    assert isinstance(current, ManifestV2)
    write_manifest(
        repo,
        Manifest(
            embedding_config_hash=current.embedding_config_hash,
            embedding_provider=current.embedding_provider,
            embedding_model=current.embedding_model,
            embedding_dimensions=current.embedding_dimensions,
            total_files=current.total_files,
            total_chunks=current.total_chunks,
        ),
    )
    before_legacy = _snapshot_bytes(repo)
    legacy_result = _refresh(repo)
    assert legacy_result.ok is False
    assert legacy_result.code == "authoritative_index_required"
    assert _snapshot_bytes(repo) == before_legacy

    index_repository(repo, DEFAULT_CONFIG)
    before_busy = _snapshot_bytes(repo)
    with exclusive_index_lock(repo / ".context-search"):
        busy_result = _refresh(
            repo,
            inventory_observer=lambda *_args: pytest.fail(
                "busy refresh performed an inventory"
            ),
        )
    assert busy_result.ok is False
    assert busy_result.code == "index_busy"
    assert busy_result.network_egress_outcome == "not_attempted"
    assert _snapshot_bytes(repo) == before_busy


def test_quick_refresh_noop_has_exact_zero_work_and_never_rewrites_ready(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "App.java").write_text("class App {}\n", encoding="utf-8")
    index_repository(repo, DEFAULT_CONFIG)
    before = _snapshot_bytes(repo)
    before_manifest = load_manifest(repo)
    assert isinstance(before_manifest, ManifestV2)
    inventory_calls = 0

    def inventory_reader(repo_path: Path, config: Any):
        nonlocal inventory_calls
        inventory_calls += 1
        return observe_workspace(repo_path, config)

    def forbidden(*_args: Any, **_kwargs: Any):
        raise AssertionError("zero-work refresh crossed a mutation/body seam")

    for name in (
        "mark_graph_stale",
        "replace_chunks",
        "replace_signals",
        "replace_relations",
        "replace_operational_observations",
        "upsert_source_file",
        "mark_file_deleted",
        "commit_operational_ready_v1",
    ):
        monkeypatch.setattr(SQLiteStore, name, forbidden)
    for name in (
        "freeze_generation_v2",
        "materialize_frozen_generation",
        "publish_generation",
    ):
        monkeypatch.setattr(NumpyVectorStore, name, forbidden)

    result = _refresh(
        repo,
        inventory_observer=inventory_reader,
        observed_reader=forbidden,
        embedding_provider=forbidden,
    )

    assert result.ok is True
    assert result.freshness == "metadata_fresh"
    assert result.network_egress_performed is False
    assert inventory_calls == 2
    assert _snapshot_bytes(repo) == before
    summary = result.summary.to_dict()
    assert summary["operation"] == "quick_refresh"
    assert summary["outcome"] == "ready"
    assert summary["verification"] == "metadata"
    assert summary["observation_generation"] == before_manifest.manifest_generation
    assert summary["files"] == {
        "direct_dirty": 0,
        "content_changed": 0,
        "metadata_only": 0,
        "dependent_rebuild": 0,
        "dependent_rebuilds": [],
        "deleted": 0,
        "coverage_skips": 0,
        "parsed": 0,
    }
    assert summary["chunks"] == {"embedded": 0}
    assert summary["work"]["inventory"] == {
        "passes": 2,
        "entries": 2,
        "errors": 0,
        "retryable_skip_attempts": 0,
    }
    assert summary["work"]["source"] == {
        "bytes_read": 0,
        "bytes_hashed": 0,
    }
    assert summary["work"]["path_index"] == {
        "builds": 0,
        "paths_canonicalized": 0,
    }
    assert summary["work"]["graph"] == {
        "relations_scanned": 0,
        "relations_resolved": 0,
        "association_inputs": 0,
        "association_writes": 0,
    }
    assert summary["work"]["vector"] == {
        "bytes_read": 0,
        "bytes_copied": 0,
        "bytes_written": 0,
        "bytes_hashed": 0,
        "payload_passes": 0,
        "prior_payload_passes": 0,
        "prepared_payload_passes": 0,
        "generations_before": 1,
        "generations_after": 1,
        "descriptor_action": "reused",
    }
    maintenance = summary["work"]["maintenance"]
    assert maintenance["tombstones_before"] == 0
    assert maintenance["tombstones_purged"] == 0
    assert maintenance["tombstones_after"] == 0
    assert maintenance["sqlite_pages_before"] > 0
    assert maintenance["sqlite_pages_after"] == maintenance["sqlite_pages_before"]
    assert maintenance["sqlite_freelist_after"] == maintenance["sqlite_freelist_before"]


def test_quick_refresh_hashes_only_dirty_metadata_and_reuses_equal_content(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    source = repo / "App.java"
    source.write_text("class App {}\n", encoding="utf-8")
    (repo / "notes.md").write_text("notes\n", encoding="utf-8")
    index_repository(repo, DEFAULT_CONFIG)
    before = source.stat()
    os.utime(source, ns=(before.st_atime_ns, before.st_mtime_ns + 1_000_000_000))
    reads: list[Path] = []
    events: list[str] = []

    def source_reader(repo_path: Path, observation: Any, **kwargs: Any):
        reads.append(observation.path)
        return read_observed_file(repo_path, observation, **kwargs)

    result = _refresh(
        repo,
        events=events,
        observed_reader=source_reader,
    )

    assert result.ok is True
    assert reads == [Path("App.java")]
    assert events == []
    summary = result.summary.to_dict()
    assert summary["files"]["direct_dirty"] == 1
    assert summary["files"]["content_changed"] == 0
    assert summary["files"]["metadata_only"] == 1
    assert summary["files"]["parsed"] == 0
    assert summary["chunks"]["embedded"] == 0
    assert summary["work"]["source"] == {
        "bytes_read": len(b"class App {}\n"),
        "bytes_hashed": len(b"class App {}\n"),
    }
    assert summary["work"]["vector"]["descriptor_action"] == "reused"
    manifest = load_manifest(repo)
    assert isinstance(manifest, ManifestV2)
    assert manifest.operation_mode == "quick_refresh"


def test_quick_refresh_closing_drift_and_incomplete_inventory_preserve_ready(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    source = repo / "App.java"
    source.write_text("class App { int oldValue; }\n", encoding="utf-8")
    index_repository(repo, DEFAULT_CONFIG)
    source.write_text("class App { int changed; }\n", encoding="utf-8")
    before = _snapshot_bytes(repo)
    calls = 0

    def drifting_inventory(repo_path: Path, config: Any):
        nonlocal calls
        calls += 1
        if calls == 2:
            source.write_text("class App { int drifted; }\n", encoding="utf-8")
        return observe_workspace(repo_path, config)

    drifted = _refresh(repo, inventory_observer=drifting_inventory)
    assert drifted.ok is False
    assert drifted.code == "workspace_changed"
    assert drifted.network_egress_outcome == "not_attempted"
    assert _snapshot_bytes(repo) == before

    complete = observe_workspace(repo, DEFAULT_CONFIG)
    incomplete = replace(
        complete,
        complete=False,
        unscannable_subtrees=("blocked",),
    )
    before_incomplete = _snapshot_bytes(repo)
    failed = _refresh(repo, inventory_observer=lambda *_args: incomplete)
    assert failed.ok is False
    assert failed.code == "inventory_incomplete"
    assert failed.network_egress_outcome == "not_attempted"
    assert _snapshot_bytes(repo) == before_incomplete


def test_quick_refresh_configuration_legality_matrix(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "App.java").write_text("class App {}\n", encoding="utf-8")
    index_repository(repo, DEFAULT_CONFIG)
    before = _snapshot_bytes(repo)
    before_manifest = load_manifest(repo)
    assert isinstance(before_manifest, ManifestV2)

    retrieval_only = replace(
        DEFAULT_CONFIG,
        retrieval=replace(
            DEFAULT_CONFIG.retrieval,
            final_top_k=DEFAULT_CONFIG.retrieval.final_top_k + 1,
        ),
    )
    no_index_work = _refresh(repo, retrieval_only)
    assert no_index_work.ok is True
    assert no_index_work.summary.observation_generation == (
        before_manifest.manifest_generation
    )
    assert _snapshot_bytes(repo) == before

    incompatible = replace(
        DEFAULT_CONFIG,
        embedding=EmbeddingConfig(
            provider="hash",
            model="hash-v1",
            dimensions=DEFAULT_CONFIG.embedding.dimensions + 1,
        ),
    )
    rejected = _refresh(repo, incompatible)
    assert rejected.ok is False
    assert rejected.code == "authoritative_index_required"
    assert rejected.network_egress_outcome == "not_attempted"
    assert _snapshot_bytes(repo) == before

    scanner_changed = replace(
        DEFAULT_CONFIG,
        index=replace(DEFAULT_CONFIG.index, exclude=["App.java"]),
    )
    refreshed = _refresh(repo, scanner_changed)
    assert refreshed.ok is True
    assert refreshed.summary.files.deleted == 1
    assert refreshed.summary.work.vector.descriptor_action == "published"
    assert SQLiteStore(repo / ".context-search" / "index.sqlite").stats()[
        "source_files"
    ] == 0


def test_quick_refresh_future_schemas_and_stable_corruption_are_exact(
    tmp_path: Path,
) -> None:
    def indexed_repo(name: str) -> Path:
        repo = tmp_path / name
        repo.mkdir()
        (repo / "App.java").write_text("class App {}\n", encoding="utf-8")
        index_repository(repo, DEFAULT_CONFIG)
        return repo

    future_manifest = indexed_repo("future-manifest")
    manifest_path = future_manifest / ".context-search" / "manifest.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["schema_version"] = 99
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    before = _snapshot_bytes(future_manifest)
    result = _refresh(future_manifest)
    assert result.ok is False and result.code == "incompatible_manifest_schema"
    assert _snapshot_bytes(future_manifest) == before

    future_operational = indexed_repo("future-operational")
    store = SQLiteStore(future_operational / ".context-search" / "index.sqlite")
    store.set_metadata(OPERATIONAL_SCHEMA_VERSION_KEY, "99")
    before = _snapshot_bytes(future_operational)
    result = _refresh(future_operational)
    assert result.ok is False and result.code == "incompatible_operational_schema"
    assert _snapshot_bytes(future_operational) == before

    future_graph = indexed_repo("future-graph")
    SQLiteStore(future_graph / ".context-search" / "index.sqlite").set_metadata(
        "signal_schema_version", "99"
    )
    before = _snapshot_bytes(future_graph)
    result = _refresh(future_graph)
    assert result.ok is False and result.code == "incompatible_signal_schema"
    assert _snapshot_bytes(future_graph) == before

    corrupt = indexed_repo("corrupt")
    descriptor_path = corrupt / ".context-search" / "vector_snapshot.json"
    descriptor = json.loads(descriptor_path.read_text(encoding="utf-8"))
    descriptor["row_count"] += 1
    descriptor_path.write_text(json.dumps(descriptor), encoding="utf-8")
    before = _snapshot_bytes(corrupt)
    result = _refresh(corrupt)
    assert result.ok is False
    assert result.code == "authoritative_index_required"
    assert result.network_egress_outcome == "not_attempted"
    assert _snapshot_bytes(corrupt) == before


def test_quick_refresh_retries_confirmed_orphans_before_preparing_a_third_generation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from context_search_tool import index_health

    repo = tmp_path / "repo"
    repo.mkdir()
    source = repo / "App.java"
    source.write_text("class App { int generationOne; }\n", encoding="utf-8")
    index_repository(repo, DEFAULT_CONFIG)
    index_dir = repo / ".context-search"
    original_cleanup = NumpyVectorStore.cleanup_unreferenced_generations

    def cleanup_failure(cls, *_args: Any, **_kwargs: Any) -> int:
        raise OSError("injected cleanup failure")

    monkeypatch.setattr(
        NumpyVectorStore,
        "cleanup_unreferenced_generations",
        classmethod(cleanup_failure),
    )
    source.write_text("class App { int generationTwo; }\n", encoding="utf-8")
    first = _refresh(repo)

    assert first.ok is True
    assert NumpyVectorStore.generation_pair_count(index_dir) == 2
    report = index_health.inspect_repository_health(repo, mode="quick")
    assert report.diagnostics is not None
    assert any(item.code == "orphan_generation" for item in report.diagnostics)

    source.write_text("class App { int generationThree; }\n", encoding="utf-8")
    retry_failed = _refresh(repo)

    assert retry_failed.ok is False
    assert retry_failed.code == "refresh_failed"
    assert retry_failed.network_egress_outcome == "not_attempted"
    assert NumpyVectorStore.generation_pair_count(index_dir) == 2

    monkeypatch.setattr(
        NumpyVectorStore,
        "cleanup_unreferenced_generations",
        original_cleanup,
    )

    def fail_after_prepare(stage: str) -> None:
        if stage == "vectors_prepared":
            raise RuntimeError("post-prepare fault")

    prepared_failure = _refresh(repo, fault_hook=fail_after_prepare)
    assert prepared_failure.ok is False
    assert NumpyVectorStore.generation_pair_count(index_dir) == 2

    recovered = _refresh(repo)
    assert recovered.ok is True
    assert NumpyVectorStore.generation_pair_count(index_dir) == 1
    assert index_health.inspect_repository_health(repo, mode="quick").health == (
        "healthy_metadata"
    )


def test_authoritative_v1_migration_cleans_safe_historical_generations(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "App.java").write_text("class App {}\n", encoding="utf-8")
    index_repository(repo, DEFAULT_CONFIG)
    current = load_manifest(repo)
    assert isinstance(current, ManifestV2)
    index_dir = repo / ".context-search"
    _descriptor, vector_store = NumpyVectorStore.load_published_snapshot(
        index_dir,
        expected_embedding_identity=current.embedding_config_hash,
    )
    vector_store.prepare_generation_v2(
        generation="historical-p5",
        embedding_identity=current.embedding_config_hash,
        normalization="none",
    )
    write_manifest(
        repo,
        Manifest(
            embedding_config_hash=current.embedding_config_hash,
            embedding_provider=current.embedding_provider,
            embedding_model=current.embedding_model,
            embedding_dimensions=current.embedding_dimensions,
            total_files=current.total_files,
            total_chunks=current.total_chunks,
        ),
    )
    assert NumpyVectorStore.generation_pair_count(index_dir) == 2

    summary = index_repository(repo, DEFAULT_CONFIG)

    assert summary.files_seen == 1
    assert isinstance(load_manifest(repo), ManifestV2)
    assert NumpyVectorStore.generation_pair_count(index_dir) == 1
    NumpyVectorStore.verify_published_snapshot(
        index_dir,
        expected_ids=SQLiteStore(index_dir / "index.sqlite").active_embedding_ids(),
    )


def test_quick_refresh_maintenance_purges_each_table_and_orphan_symbols(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    source = repo / "App.java"
    source.write_text("class App { int before; }\n", encoding="utf-8")
    index_repository(repo, DEFAULT_CONFIG)
    db_path = repo / ".context-search" / "index.sqlite"
    row_count = 5_001

    with sqlite3.connect(db_path) as connection:
        connection.executemany(
            """
            INSERT INTO code_signals (
                signal_id, chunk_id, file_path, kind, name, qualified_name,
                signature, arity, project_unit_key, producer, start_line,
                end_line, start_column, end_column, language, recallable,
                tokens, metadata, deleted_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                (
                    f"deleted-signal-{index}",
                    f"deleted-chunk-{index}",
                    "deleted.java",
                    "method",
                    "deleted",
                    "Deleted.deleted",
                    "deleted()",
                    0,
                    ".",
                    "fixture",
                    1,
                    1,
                    0,
                    1,
                    "java",
                    0,
                    "[]",
                    "{}",
                    1,
                )
                for index in range(row_count)
            ),
        )
        connection.executemany(
            """
            INSERT INTO code_relations (
                relation_id, source_signal_id, source_chunk_id,
                source_file_path, target_name, kind, confidence, target_kind,
                target_qualified_name, target_signature, target_arity,
                target_project_unit_key, target_signal_id, resolution,
                producer, producer_confidence, resolution_confidence,
                metadata, deleted_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                (
                    f"deleted-relation-{index}",
                    f"deleted-signal-{index}",
                    f"deleted-chunk-{index}",
                    "deleted.java",
                    "Deleted.target",
                    "tests",
                    1.0,
                    "method",
                    "Deleted.target",
                    "target()",
                    0,
                    ".",
                    "",
                    "unresolved",
                    "test_association",
                    1.0,
                    None,
                    "{}",
                    1,
                )
                for index in range(row_count)
            ),
        )
        connection.executemany(
            """
            INSERT INTO symbols (
                name, kind, start_line, end_line, language, metadata
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                (f"orphan-{index}", "field", 1, 1, "java", "{}")
                for index in range(row_count)
            ),
        )
        connection.commit()

    source.write_text("class App { int after; }\n", encoding="utf-8")
    result = _refresh(repo)

    assert result.ok is True
    assert result.summary.work.maintenance.tombstones_purged > 0
    with sqlite3.connect(db_path) as connection:
        deleted_signals = connection.execute(
            "SELECT COUNT(*) FROM code_signals WHERE deleted_at IS NOT NULL"
        ).fetchone()[0]
        deleted_relations = connection.execute(
            "SELECT COUNT(*) FROM code_relations WHERE deleted_at IS NOT NULL"
        ).fetchone()[0]
        orphan_symbols = connection.execute(
            """
            SELECT COUNT(*)
            FROM symbols
            LEFT JOIN chunk_symbols USING (symbol_id)
            WHERE chunk_symbols.symbol_id IS NULL
            """
        ).fetchone()[0]
    assert deleted_signals <= 5_000
    assert deleted_relations <= 5_000
    assert orphan_symbols <= 5_000
    assert NumpyVectorStore.verify_published_snapshot(
        repo / ".context-search",
        expected_ids=SQLiteStore(db_path).active_embedding_ids(),
    )


def test_quick_refresh_100_step_scaled_churn_preserves_exact_ready_state(
    tmp_path: Path,
) -> None:
    from context_search_tool import index_health
    from context_search_tool.retrieval import query_repository

    schedule = json.loads(
        (
            Path(__file__).parent
            / "fixtures"
            / "p6_performance"
            / "workload_manifest.json"
        ).read_text(encoding="utf-8")
    )["edit_schedule"]
    assert schedule["steps"] == 100
    assert schedule["cycle_length"] == 10
    assert schedule["sample_every_steps"] == 10

    repo = tmp_path / "repo"
    repo.mkdir()
    base_paths = [repo / f"Type{index}.java" for index in range(6)]
    for index, path in enumerate(base_paths):
        path.write_text(
            f'class Type{index} {{ String stableToken() {{ return "stableToken"; }} }}\n',
            encoding="utf-8",
        )
    index_repository(repo, DEFAULT_CONFIG)
    original_second = base_paths[1].read_bytes()

    sampled_generations: list[int] = []
    for cycle in range(10):
        added = repo / f"Added{cycle}.java"
        actions = (
            "modify",
            "delete",
            "restore",
            "add",
            "delete_added",
            "equal_content_touch",
            "same_metadata_content_edit",
            "stable_skip",
            "retryable_skip",
            "injected_failure",
        )
        for offset, operation in enumerate(actions):
            if operation == "modify":
                base_paths[0].write_text(
                    f'class Type0 {{ int cycle{cycle}; String stableToken() {{ return "stableToken"; }} }}\n',
                    encoding="utf-8",
                )
                result = _refresh(repo)
            elif operation == "delete":
                base_paths[1].unlink()
                result = _refresh(repo)
            elif operation == "restore":
                base_paths[1].write_bytes(original_second)
                result = _refresh(repo)
            elif operation == "add":
                added.write_text(
                    f"class Added{cycle} {{}}\n",
                    encoding="utf-8",
                )
                result = _refresh(repo)
            elif operation == "delete_added":
                added.unlink()
                result = _refresh(repo)
            elif operation == "equal_content_touch":
                before = base_paths[2].stat()
                os.utime(
                    base_paths[2],
                    ns=(before.st_atime_ns, before.st_mtime_ns + 1_000_000),
                )
                result = _refresh(repo)
            elif operation == "same_metadata_content_edit":
                before = base_paths[3].stat()
                payload = base_paths[3].read_text(encoding="utf-8")
                base_paths[3].write_text(
                    payload.replace("Type3", "TyPe3"),
                    encoding="utf-8",
                )
                os.utime(
                    base_paths[3],
                    ns=(before.st_atime_ns, before.st_mtime_ns),
                )
                result = _refresh(repo)
            elif operation in {"stable_skip", "retryable_skip"}:
                target = base_paths[4 if operation == "stable_skip" else 5]
                target.write_text(
                    f"class {target.stem} {{ int skipped{cycle}; }}\n",
                    encoding="utf-8",
                )

                def skipped_reader(
                    repo_path: Path,
                    observation: Any,
                    **kwargs: Any,
                ) -> ObservedFileRead:
                    if observation.path == target.relative_to(repo):
                        return ObservedFileRead(
                            status="skipped",
                            path=observation.path,
                            content=None,
                            sha256=None,
                            size=observation.size,
                            reason=(
                                "too_large"
                                if operation == "stable_skip"
                                else "unreadable"
                            ),
                            retryable=operation == "retryable_skip",
                            metadata=observation.metadata,
                        )
                    return read_observed_file(repo_path, observation, **kwargs)

                result = _refresh(repo, observed_reader=skipped_reader)
            else:
                complete = observe_workspace(repo, DEFAULT_CONFIG)
                incomplete = replace(
                    complete,
                    complete=False,
                    unscannable_subtrees=("injected",),
                )
                result = _refresh(
                    repo,
                    inventory_observer=lambda *_args: incomplete,
                )

            step = cycle * 10 + offset + 1
            if operation == "injected_failure":
                assert result.ok is False
                assert result.code == "inventory_incomplete"
            else:
                assert result.ok is True
            if step % schedule["sample_every_steps"] == 0:
                report = index_health.inspect_repository_health(repo, mode="quick")
                assert report.queryable is True
                bundle = query_repository(repo, "stableToken", DEFAULT_CONFIG)
                assert bundle.results
                store = SQLiteStore(repo / ".context-search" / "index.sqlite")
                NumpyVectorStore.verify_published_snapshot(
                    repo / ".context-search",
                    expected_ids=store.active_embedding_ids(),
                )
                sampled_generations.append(
                    NumpyVectorStore.generation_pair_count(repo / ".context-search")
                )

    assert len(sampled_generations) == 10
    assert max(sampled_generations) == 1
    store = SQLiteStore(repo / ".context-search" / "index.sqlite")
    assert store.tombstone_count() <= 5_000
