from __future__ import annotations

from dataclasses import replace
import multiprocessing
import os
from pathlib import Path
import sqlite3
import stat
import threading
import time

import numpy as np
import pytest

from context_search_tool.config import DEFAULT_CONFIG, EmbeddingConfig, render_config
from context_search_tool.graph_lifecycle import (
    FULL_REINDEX_REQUIRED_KEY,
    GRAPH_RESOLUTION_STATE_KEY,
    IncompatibleSignalSchemaError,
    IndexBusyError,
    read_graph_capability,
)
from context_search_tool.index_lock import INDEX_LOCK_FILENAME, exclusive_index_lock
from context_search_tool.indexer import build_v5_index_snapshot, refresh_repository
from context_search_tool.java_graph import JavaGraphProducer
from context_search_tool.scanner import observe_workspace, scan_workspace_v5
from context_search_tool.sqlite_store import SQLiteStore
from context_search_tool.vector_store import NumpyVectorStore


class _Metadata:
    def __init__(self, values: dict[str, str]) -> None:
        self.values = values

    def get_metadata(self, key: str) -> str | None:
        return self.values.get(key)


def _try_lock(index_dir: str, queue) -> None:
    try:
        with exclusive_index_lock(Path(index_dir)):
            queue.put("acquired")
    except Exception as error:  # pragma: no cover - asserted in parent process
        queue.put((type(error).__name__, str(error)))


def _v5_store(tmp_path: Path) -> SQLiteStore:
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize()
    store.set_metadata("signal_schema_version", "4")
    store.migrate_signal_schema_v5()
    return store


@pytest.mark.parametrize(
    ("metadata", "status", "structured", "signal_evidence"),
    [
        ({}, "legacy", False, True),
        ({"signal_schema_version": "4"}, "legacy", False, True),
        (
            {"signal_schema_version": "4", "graph_resolution_state": "stale"},
            "stale",
            False,
            False,
        ),
        (
            {"signal_schema_version": "5", "graph_resolution_state": "stale"},
            "stale",
            True,
            False,
        ),
        (
            {
                "signal_schema_version": "5",
                "graph_resolution_state": "ready",
                "graph_resolution_version": "1",
            },
            "ready",
            True,
            True,
        ),
        (
            {"signal_schema_version": "5", "graph_resolution_state": "ready"},
            "stale",
            True,
            False,
        ),
    ],
)
def test_graph_capability_matrix(
    metadata: dict[str, str],
    status: str,
    structured: bool,
    signal_evidence: bool,
) -> None:
    capability = read_graph_capability(_Metadata(metadata))

    assert capability.status == status
    assert capability.structured is structured
    assert capability.signal_evidence_allowed is signal_evidence


def test_graph_capability_rejects_future_or_malformed_versions() -> None:
    with pytest.raises(IncompatibleSignalSchemaError):
        read_graph_capability(_Metadata({"signal_schema_version": "6"}))
    with pytest.raises(IncompatibleSignalSchemaError):
        read_graph_capability(_Metadata({"signal_schema_version": "future"}))


def test_operational_capability_is_independent_and_fails_closed() -> None:
    from context_search_tool import graph_lifecycle as lifecycle

    assert hasattr(lifecycle, "read_operational_capability"), (
        "P6 operational capability reader is absent"
    )
    assert hasattr(lifecycle, "IncompatibleOperationalSchemaError"), (
        "P6 operational compatibility error is absent"
    )

    legacy = lifecycle.read_operational_capability(_Metadata({}))
    current = lifecycle.read_operational_capability(
        _Metadata({"operational_schema_version": "1"})
    )
    assert (legacy.status, legacy.schema_version) == ("legacy", 0)
    assert (current.status, current.schema_version) == ("current", 1)

    error_type = lifecycle.IncompatibleOperationalSchemaError
    for value in ("2", "future", "-1"):
        with pytest.raises(error_type) as caught:
            lifecycle.read_operational_capability(
                _Metadata({"operational_schema_version": value})
            )
        assert caught.value.code == "incompatible_operational_schema"


def test_exclusive_index_lock_is_retained_and_contended_process_fails_closed(
    tmp_path: Path,
) -> None:
    index_dir = tmp_path / "index"
    index_dir.mkdir()
    context = multiprocessing.get_context("spawn")
    queue = context.Queue()

    with exclusive_index_lock(index_dir):
        process = context.Process(target=_try_lock, args=(str(index_dir), queue))
        process.start()
        result = queue.get(timeout=10)
        process.join(timeout=10)

    assert result == (
        "IndexBusyError",
        "index already in progress for repository",
    )
    assert process.exitcode == 0
    lock_path = index_dir / INDEX_LOCK_FILENAME
    assert lock_path.is_file()
    with exclusive_index_lock(index_dir):
        pass
    assert lock_path.is_file()


@pytest.mark.skipif(os.name == "nt", reason="POSIX ownership and mode contract")
def test_index_lock_rejects_symlink_or_permissive_existing_file(
    tmp_path: Path,
) -> None:
    index_dir = tmp_path / "index"
    index_dir.mkdir()
    target = tmp_path / "outside.lock"
    target.write_text("outside", encoding="utf-8")
    lock_path = index_dir / INDEX_LOCK_FILENAME
    lock_path.symlink_to(target)
    with pytest.raises(ValueError, match="regular non-symlink"):
        with exclusive_index_lock(index_dir):
            pass

    lock_path.unlink()
    lock_path.write_text("", encoding="utf-8")
    lock_path.chmod(0o644)
    with pytest.raises(ValueError, match="permissions"):
        with exclusive_index_lock(index_dir):
            pass
    assert stat.S_IMODE(lock_path.stat().st_mode) == 0o644


def test_final_ready_transaction_cannot_clear_full_flag_on_fault(
    tmp_path: Path,
) -> None:
    store = _v5_store(tmp_path)

    with pytest.raises(ValueError, match="clears only with the ready transaction"):
        store.set_metadata(FULL_REINDEX_REQUIRED_KEY, "0")

    def fail() -> None:
        raise RuntimeError("before ready")

    with pytest.raises(RuntimeError, match="before ready"):
        store.mark_graph_ready(
            topology_fingerprint="a" * 64,
            before_commit=fail,
        )

    assert store.get_metadata(GRAPH_RESOLUTION_STATE_KEY) == "stale"
    assert store.get_metadata(FULL_REINDEX_REQUIRED_KEY) == "1"


def test_graph_read_session_keeps_one_ready_snapshot_until_close(
    tmp_path: Path,
) -> None:
    store = _v5_store(tmp_path)
    store.mark_graph_ready(topology_fingerprint="b" * 64)
    writer_at_commit = threading.Event()
    writer_done = threading.Event()
    errors: list[BaseException] = []

    def writer() -> None:
        try:
            store.mark_graph_stale(
                "changed_files",
                before_commit=writer_at_commit.set,
            )
        except BaseException as error:  # pragma: no cover - asserted below
            errors.append(error)
        finally:
            writer_done.set()

    with store.graph_read_session() as session:
        assert session.capability.status == "ready"
        thread = threading.Thread(target=writer)
        thread.start()
        assert writer_at_commit.wait(timeout=5)
        time.sleep(0.05)
        assert not writer_done.is_set()
        assert session.capability.status == "ready"

    assert writer_done.wait(timeout=5)
    thread.join(timeout=5)
    assert errors == []
    with store.graph_read_session() as later:
        assert later.capability.status == "stale"


def test_writer_busy_timeout_uses_stable_internal_error(tmp_path: Path) -> None:
    store = _v5_store(tmp_path)
    store.mark_graph_ready(topology_fingerprint="c" * 64)

    with store.graph_read_session():
        with pytest.raises(
            IndexBusyError,
            match="index already in progress for repository",
        ):
            store.mark_graph_stale(
                "changed_files",
                busy_timeout_ms=25,
            )

    assert store.get_metadata(GRAPH_RESOLUTION_STATE_KEY) == "ready"


def test_v4_reader_observes_complete_old_schema_until_migration_commit(
    tmp_path: Path,
) -> None:
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize()
    store.set_metadata("signal_schema_version", "4")
    with sqlite3.connect(store.db_path) as connection:
        connection.execute(
            """
            INSERT INTO code_signals VALUES (
                'old', 'chunk', 'src/Old.java', 'method', 'Old.run',
                1, 1, 'java', '[]', '{}', NULL
            )
            """
        )

    reader = sqlite3.connect(store.db_path)
    reader.execute("BEGIN")
    assert reader.execute("SELECT COUNT(*) FROM code_signals").fetchone()[0] == 1
    writer_at_commit = threading.Event()
    writer_done = threading.Event()
    errors: list[BaseException] = []

    def migrate() -> None:
        try:
            store.migrate_signal_schema_v5(before_commit=writer_at_commit.set)
        except BaseException as error:  # pragma: no cover - asserted below
            errors.append(error)
        finally:
            writer_done.set()

    thread = threading.Thread(target=migrate)
    thread.start()
    assert writer_at_commit.wait(timeout=5)
    time.sleep(0.05)
    assert not writer_done.is_set()
    assert {
        row[1] for row in reader.execute("PRAGMA table_info(code_signals)")
    } == {
        "signal_id",
        "chunk_id",
        "file_path",
        "kind",
        "name",
        "start_line",
        "end_line",
        "language",
        "tokens",
        "metadata",
        "deleted_at",
    }
    assert reader.execute(
        "SELECT value FROM index_metadata WHERE key = 'signal_schema_version'"
    ).fetchone()[0] == "4"
    reader.rollback()
    reader.close()

    assert writer_done.wait(timeout=5)
    thread.join(timeout=5)
    assert errors == []
    with sqlite3.connect(store.db_path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM code_signals"
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT value FROM index_metadata WHERE key = 'signal_schema_version'"
        ).fetchone()[0] == "5"


@pytest.mark.parametrize(
    "failure_stage",
    [
        "stale_committed",
        "vectors_temp_write",
        "vectors_file_fsync",
        "vectors_rename",
        "vectors_directory_fsync",
        "ids_temp_write",
        "ids_file_fsync",
        "ids_rename",
        "ids_directory_fsync",
        "vectors_prepared",
        "file_write_started",
        "chunks_persisted",
        "signals_persisted",
        "producer_relations_persisted",
        "source_hash_persisted",
        "producer_resolver_complete",
        "associations_complete",
        "association_resolver_complete",
        "descriptor_temp_write",
        "descriptor_file_fsync",
        "descriptor_rename",
        "descriptor_directory_fsync",
        "vector_descriptor_published",
        "config_temp_write",
        "config_file_fsync",
        "config_rename",
        "config_directory_fsync",
        "manifest_temp_write",
        "manifest_file_fsync",
        "manifest_rename",
        "manifest_directory_fsync",
        "external_artifacts_validated",
        "final_validation",
        "before_ready_commit",
    ],
)
def test_v5_index_failure_seams_recover_without_partial_ready(
    tmp_path: Path,
    failure_stage: str,
) -> None:
    repo = tmp_path / failure_stage
    repo.mkdir()
    (repo / "App.java").write_text("class App {}\n", encoding="utf-8")

    def fail(stage: str) -> None:
        if stage == failure_stage:
            raise RuntimeError(f"fault:{stage}")

    with pytest.raises(RuntimeError, match=f"fault:{failure_stage}"):
        build_v5_index_snapshot(
            repo,
            DEFAULT_CONFIG,
            graph_plugins=[JavaGraphProducer()],
            scanner=scan_workspace_v5,
            fault_hook=fail,
        )

    store = SQLiteStore(repo / ".context-search" / "index.sqlite")
    assert store.get_metadata(GRAPH_RESOLUTION_STATE_KEY) == "stale"
    assert store.get_metadata(FULL_REINDEX_REQUIRED_KEY) == "1"

    build_v5_index_snapshot(
        repo,
        DEFAULT_CONFIG,
        graph_plugins=[JavaGraphProducer()],
        scanner=scan_workspace_v5,
    )

    assert store.get_metadata(GRAPH_RESOLUTION_STATE_KEY) == "ready"
    assert store.get_metadata(FULL_REINDEX_REQUIRED_KEY) == "0"


def test_failure_after_acknowledged_ready_commit_exposes_complete_noop(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "App.java").write_text("class App {}\n", encoding="utf-8")

    def fail(stage: str) -> None:
        if stage == "after_ready_commit":
            raise RuntimeError("acknowledged ready")

    with pytest.raises(RuntimeError, match="acknowledged ready"):
        build_v5_index_snapshot(
            repo,
            DEFAULT_CONFIG,
            graph_plugins=[JavaGraphProducer()],
            scanner=scan_workspace_v5,
            fault_hook=fail,
        )

    store = SQLiteStore(repo / ".context-search" / "index.sqlite")
    assert store.get_metadata(GRAPH_RESOLUTION_STATE_KEY) == "ready"
    assert store.get_metadata(FULL_REINDEX_REQUIRED_KEY) == "0"
    summary = build_v5_index_snapshot(
        repo,
        DEFAULT_CONFIG,
        graph_plugins=[JavaGraphProducer()],
        scanner=scan_workspace_v5,
    )
    assert summary.files_indexed == 0


def test_failure_at_closing_fence_keeps_prior_ready_generation(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo-closing-fence"
    repo.mkdir()
    source = repo / "App.java"
    source.write_text("class App { int oldValue; }\n", encoding="utf-8")
    build_v5_index_snapshot(
        repo,
        DEFAULT_CONFIG,
        graph_plugins=[JavaGraphProducer()],
        scanner=scan_workspace_v5,
    )
    store = SQLiteStore(repo / ".context-search" / "index.sqlite")
    old_hash = store.source_file_for_path(Path("App.java")).sha256
    old_manifest = (repo / ".context-search" / "manifest.json").read_bytes()
    source.write_text("class App { int newValue; }\n", encoding="utf-8")

    def fail(stage: str) -> None:
        if stage == "closing_inventory_complete":
            raise RuntimeError("closing fence fault")

    with pytest.raises(RuntimeError, match="closing fence fault"):
        build_v5_index_snapshot(
            repo,
            DEFAULT_CONFIG,
            graph_plugins=[JavaGraphProducer()],
            scanner=scan_workspace_v5,
            fault_hook=fail,
        )

    assert store.get_metadata(GRAPH_RESOLUTION_STATE_KEY) == "ready"
    assert store.source_file_for_path(Path("App.java")).sha256 == old_hash
    assert (repo / ".context-search" / "manifest.json").read_bytes() == old_manifest


def test_incremental_failure_after_source_hash_cannot_skip_recovery(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    source = repo / "App.java"
    source.write_text("class App {}\n", encoding="utf-8")
    build_v5_index_snapshot(
        repo,
        DEFAULT_CONFIG,
        graph_plugins=[JavaGraphProducer()],
        scanner=scan_workspace_v5,
    )
    source.write_text("class App { int changed; }\n", encoding="utf-8")

    def fail(stage: str) -> None:
        if stage == "source_hash_persisted":
            raise RuntimeError("after source hash")

    with pytest.raises(RuntimeError, match="after source hash"):
        build_v5_index_snapshot(
            repo,
            DEFAULT_CONFIG,
            graph_plugins=[JavaGraphProducer()],
            scanner=scan_workspace_v5,
            fault_hook=fail,
        )

    store = SQLiteStore(repo / ".context-search" / "index.sqlite")
    assert store.get_metadata(GRAPH_RESOLUTION_STATE_KEY) == "stale"
    assert store.get_metadata(FULL_REINDEX_REQUIRED_KEY) == "0"
    summary = build_v5_index_snapshot(
        repo,
        DEFAULT_CONFIG,
        graph_plugins=[JavaGraphProducer()],
        scanner=scan_workspace_v5,
    )
    assert summary.files_indexed == 1
    assert store.get_metadata(GRAPH_RESOLUTION_STATE_KEY) == "ready"


def test_incremental_failure_after_deletion_recovers_vectors_and_graph(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "Keep.java").write_text("class Keep {}\n", encoding="utf-8")
    removed = repo / "Remove.java"
    removed.write_text("class Remove {}\n", encoding="utf-8")
    build_v5_index_snapshot(
        repo,
        DEFAULT_CONFIG,
        graph_plugins=[JavaGraphProducer()],
        scanner=scan_workspace_v5,
    )
    removed.unlink()

    def fail(stage: str) -> None:
        if stage == "deletion_persisted":
            raise RuntimeError("after deletion")

    with pytest.raises(RuntimeError, match="after deletion"):
        build_v5_index_snapshot(
            repo,
            DEFAULT_CONFIG,
            graph_plugins=[JavaGraphProducer()],
            scanner=scan_workspace_v5,
            fault_hook=fail,
        )

    store = SQLiteStore(repo / ".context-search" / "index.sqlite")
    assert store.get_metadata(GRAPH_RESOLUTION_STATE_KEY) == "stale"
    summary = build_v5_index_snapshot(
        repo,
        DEFAULT_CONFIG,
        graph_plugins=[JavaGraphProducer()],
        scanner=scan_workspace_v5,
    )
    assert summary.files_indexed == 1
    assert store.source_file_for_path(Path("Remove.java")) is None
    assert store.get_metadata(GRAPH_RESOLUTION_STATE_KEY) == "ready"


def test_public_query_and_index_use_complete_rollback_journal_snapshots(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from concurrent.futures import ThreadPoolExecutor

    from context_search_tool.indexer import index_repository
    from context_search_tool.retrieval import query_repository
    from context_search_tool.retrieval_core import candidates, selection
    from context_search_tool.sqlite_store import FILE_WRITE_IN_PROGRESS_KEY

    repo = tmp_path / "repo"
    repo.mkdir()
    source = repo / "SnapshotService.java"
    source.write_text(
        'class SnapshotService { String oldSnapshotToken() { return "oldSnapshotToken"; } }\n',
        encoding="utf-8",
    )
    index_repository(repo, DEFAULT_CONFIG)
    store = SQLiteStore(repo / ".context-search" / "index.sqlite")
    old_embedding_ids = store.active_embedding_ids()
    assert len(old_embedding_ids) == 1

    ready_query_at_end = threading.Event()
    release_ready_query = threading.Event()
    stale_before_commit = threading.Event()
    stale_committed = threading.Event()
    first_v5_write = threading.Event()
    allow_v5_writes = threading.Event()

    original_assemble = selection.assemble_query_output

    def hold_first_query_snapshot(*args, **kwargs):
        if not ready_query_at_end.is_set():
            ready_query_at_end.set()
            if not release_ready_query.wait(timeout=5):
                raise AssertionError("timed out holding the ready query snapshot")
        return original_assemble(*args, **kwargs)

    monkeypatch.setattr(selection, "assemble_query_output", hold_first_query_snapshot)
    original_mark_stale = SQLiteStore.mark_graph_stale

    def observe_stale_commit(self, reason: str, **kwargs) -> None:
        def before_commit() -> None:
            stale_before_commit.set()

        original_mark_stale(self, reason, before_commit=before_commit, **kwargs)
        stale_committed.set()

    monkeypatch.setattr(SQLiteStore, "mark_graph_stale", observe_stale_commit)
    original_set_metadata = SQLiteStore.set_metadata

    def pause_before_first_v5_write(self, key: str, value: str) -> None:
        if key == FILE_WRITE_IN_PROGRESS_KEY and not first_v5_write.is_set():
            assert stale_committed.is_set()
            first_v5_write.set()
            if not allow_v5_writes.wait(timeout=5):
                raise AssertionError("timed out holding the first v5 write")
        original_set_metadata(self, key, value)

    monkeypatch.setattr(SQLiteStore, "set_metadata", pause_before_first_v5_write)
    stale_semantic_ids: set[str] = set()
    stale_lexical_ids: set[str] = set()
    original_semantic = candidates.semantic_candidates_from_snapshot
    original_lexical = candidates.lexical_candidates

    def capture_stale_semantic(vector_store, *args, **kwargs):
        result = original_semantic(vector_store, *args, **kwargs)
        if first_v5_write.is_set() and not allow_v5_writes.is_set():
            stale_semantic_ids.update(item.chunk_id for item in result[0])
        return result

    def capture_stale_lexical(*args, **kwargs):
        result = original_lexical(*args, **kwargs)
        if first_v5_write.is_set() and not allow_v5_writes.is_set():
            stale_lexical_ids.update(item.chunk_id for item in result)
        return result

    monkeypatch.setattr(
        candidates,
        "semantic_candidates_from_snapshot",
        capture_stale_semantic,
    )
    monkeypatch.setattr(candidates, "lexical_candidates", capture_stale_lexical)

    with ThreadPoolExecutor(max_workers=2) as executor:
        ready_future = executor.submit(
            query_repository,
            repo,
            "oldSnapshotToken",
            DEFAULT_CONFIG,
        )
        index_future = None
        try:
            assert ready_query_at_end.wait(timeout=5)
            source.write_text(
                'class SnapshotService { String newSnapshotToken() { return "newSnapshotToken"; } }\n',
                encoding="utf-8",
            )
            index_future = executor.submit(index_repository, repo, DEFAULT_CONFIG)
            assert stale_before_commit.wait(timeout=5)
            assert not stale_committed.wait(timeout=0.05)
            assert not first_v5_write.is_set()

            release_ready_query.set()
            ready_bundle = ready_future.result(timeout=5)
            assert "oldSnapshotToken" in ready_bundle.results[0].content
            assert stale_committed.wait(timeout=5)
            assert first_v5_write.wait(timeout=5)
            assert read_graph_capability(store).status == "stale"
            assert store.active_embedding_ids() == old_embedding_ids

            stale_bundle = query_repository(repo, "oldSnapshotToken", DEFAULT_CONFIG)
            assert stale_bundle.results
            stale_result = stale_bundle.results[0]
            assert stale_semantic_ids == old_embedding_ids
            assert stale_lexical_ids == old_embedding_ids
            assert {"semantic", "lexical"} <= stale_result.score_parts.keys()
            assert "signal" not in stale_result.score_parts
            assert not any(
                key.startswith("graph_")
                or key in {"relation", "resolved_relation"}
                for key in stale_result.score_parts
            )

            allow_v5_writes.set()
            assert index_future.result(timeout=5).files_indexed == 1
        finally:
            release_ready_query.set()
            allow_v5_writes.set()

    assert read_graph_capability(store).status == "ready"
    assert store.active_embedding_ids() != old_embedding_ids
    final_bundle = query_repository(repo, "newSnapshotToken", DEFAULT_CONFIG)
    assert final_bundle.results
    assert "newSnapshotToken" in final_bundle.results[0].content


def test_public_index_uses_stable_error_at_shortened_busy_timeout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from context_search_tool.indexer import index_repository

    repo = tmp_path / "repo"
    repo.mkdir()
    source = repo / "App.java"
    source.write_text("class App {}\n", encoding="utf-8")
    index_repository(repo, DEFAULT_CONFIG)
    source.write_text("class App { int changed; }\n", encoding="utf-8")

    store = SQLiteStore(repo / ".context-search" / "index.sqlite")
    original_mark_stale = SQLiteStore.mark_graph_stale

    def mark_stale_with_short_timeout(self, reason: str, **kwargs) -> None:
        kwargs["busy_timeout_ms"] = 25
        original_mark_stale(self, reason, **kwargs)

    monkeypatch.setattr(
        SQLiteStore,
        "mark_graph_stale",
        mark_stale_with_short_timeout,
    )

    with store.graph_read_session():
        with pytest.raises(IndexBusyError) as caught:
            index_repository(repo, DEFAULT_CONFIG)

    assert str(caught.value) == "index already in progress for repository"
    assert read_graph_capability(store).status == "ready"
    assert index_repository(repo, DEFAULT_CONFIG).files_indexed == 1
    assert read_graph_capability(store).status == "ready"


@pytest.mark.parametrize("damage", ["missing", "invalid", "wrong_type"])
def test_stale_query_treats_persisted_config_damage_as_vector_mismatch(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    damage: str,
) -> None:
    from context_search_tool.indexer import index_repository
    from context_search_tool.retrieval import query_repository

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "SearchService.java").write_text(
        "class SearchService { void stableLexicalToken() {} }\n",
        encoding="utf-8",
    )
    index_repository(repo, DEFAULT_CONFIG)
    store = SQLiteStore(repo / ".context-search" / "index.sqlite")
    store.mark_graph_stale("test_config_damage")
    config_path = repo / ".context-search" / "config.toml"
    if damage == "missing":
        config_path.unlink()
        expected_bytes = None
    elif damage == "invalid":
        config_path.write_bytes(b"invalid = [")
        expected_bytes = config_path.read_bytes()
    else:
        config_path.write_bytes(b"embedding = []\n")
        expected_bytes = config_path.read_bytes()

    caplog.set_level("WARNING")
    bundle = query_repository(repo, "stableLexicalToken", DEFAULT_CONFIG)

    assert bundle.results
    assert "lexical" in bundle.results[0].score_parts
    assert all("semantic" not in result.score_parts for result in bundle.results)
    assert [record.message for record in caplog.records].count(
        "vector_snapshot_mismatch"
    ) == 1
    if expected_bytes is None:
        assert not config_path.exists()
    else:
        assert config_path.read_bytes() == expected_bytes


@pytest.mark.parametrize("damage", ["missing", "invalid", "wrong_type"])
def test_ready_query_rejects_persisted_config_damage_without_mutation(
    tmp_path: Path,
    damage: str,
) -> None:
    from context_search_tool.graph_lifecycle import GraphIntegrityError
    from context_search_tool.indexer import index_repository
    from context_search_tool.retrieval import query_repository

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "SearchService.java").write_text(
        "class SearchService {}\n",
        encoding="utf-8",
    )
    index_repository(repo, DEFAULT_CONFIG)
    config_path = repo / ".context-search" / "config.toml"
    if damage == "missing":
        config_path.unlink()
        expected_bytes = None
    elif damage == "invalid":
        config_path.write_bytes(b"invalid = [")
        expected_bytes = config_path.read_bytes()
    else:
        config_path.write_bytes(b"embedding = []\n")
        expected_bytes = config_path.read_bytes()

    with pytest.raises(GraphIntegrityError, match="vector_snapshot_mismatch"):
        query_repository(repo, "SearchService", DEFAULT_CONFIG)

    if expected_bytes is None:
        assert not config_path.exists()
    else:
        assert config_path.read_bytes() == expected_bytes


def test_quick_refresh_post_provider_drift_reports_performed_and_preserves_ready(
    tmp_path: Path,
) -> None:
    config = replace(
        DEFAULT_CONFIG,
        embedding=EmbeddingConfig(
            provider="openai-compatible",
            model="fixture-embedding",
            dimensions=3,
            base_url="https://example.test/v1",
        ),
    )

    class _Provider:
        def __init__(self) -> None:
            self.calls = 0

        def fingerprint(self) -> dict[str, object]:
            return {
                "provider": "openai-compatible",
                "model": "fixture-embedding",
                "dimensions": 3,
                "base_url": "https://example.test/v1",
            }

        def embed_texts(self, texts: list[str]) -> list[np.ndarray]:
            self.calls += 1
            return [np.asarray([1.0, 0.0, 0.0], dtype=np.float32) for _ in texts]

    repo = tmp_path / "repo"
    repo.mkdir()
    source = repo / "App.java"
    source.write_text("class App { int oldValue; }\n", encoding="utf-8")
    provider = _Provider()
    build_v5_index_snapshot(
        repo,
        config,
        graph_plugins=[JavaGraphProducer()],
        scanner=scan_workspace_v5,
        embedding_provider=provider,
    )
    provider.calls = 0
    source.write_text("class App { int newValue; }\n", encoding="utf-8")
    index_dir = repo / ".context-search"
    before = tuple(
        (index_dir / name).read_bytes()
        for name in ("manifest.json", "vector_snapshot.json", "index.sqlite")
    )
    inventories = 0

    def drifting_inventory(repo_path: Path, effective_config):
        nonlocal inventories
        inventories += 1
        if inventories == 2:
            source.write_text("class App { int drifted; }\n", encoding="utf-8")
        return observe_workspace(repo_path, effective_config)

    result = refresh_repository(
        repo,
        config,
        graph_plugins=[JavaGraphProducer()],
        inventory_observer=drifting_inventory,
        embedding_provider=provider,
    )

    assert result.ok is False
    assert result.code == "workspace_changed"
    assert result.network_egress_outcome == "performed"
    assert provider.calls == 1
    assert tuple(
        (index_dir / name).read_bytes()
        for name in ("manifest.json", "vector_snapshot.json", "index.sqlite")
    ) == before


def test_quick_refresh_retrieval_only_config_edit_is_a_true_noop(
    tmp_path: Path,
) -> None:
    from context_search_tool.indexer import index_repository
    from context_search_tool.manifest import ManifestV2, load_manifest

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "App.java").write_text("class App {}\n", encoding="utf-8")
    index_repository(repo, DEFAULT_CONFIG)
    retrieval_only = replace(
        DEFAULT_CONFIG,
        retrieval=replace(
            DEFAULT_CONFIG.retrieval,
            final_top_k=DEFAULT_CONFIG.retrieval.final_top_k + 1,
        ),
    )
    (repo / ".context-search" / "config.toml").write_text(
        render_config(retrieval_only),
        encoding="utf-8",
    )
    manifest = load_manifest(repo)
    assert isinstance(manifest, ManifestV2)
    index_dir = repo / ".context-search"
    before = tuple(
        (index_dir / name).read_bytes()
        for name in ("manifest.json", "vector_snapshot.json", "index.sqlite")
    )

    result = refresh_repository(repo, graph_plugins=[JavaGraphProducer()])

    assert result.ok is True
    assert result.summary.observation_generation == manifest.manifest_generation
    assert result.summary.files.direct_dirty == 0
    assert tuple(
        (index_dir / name).read_bytes()
        for name in ("manifest.json", "vector_snapshot.json", "index.sqlite")
    ) == before


def test_quick_refresh_retry_recovers_fault_immediately_after_stale(
    tmp_path: Path,
) -> None:
    from context_search_tool.indexer import index_repository

    repo = tmp_path / "repo"
    repo.mkdir()
    source = repo / "App.java"
    source.write_text("class App { int oldValue; }\n", encoding="utf-8")
    index_repository(repo, DEFAULT_CONFIG)
    source.write_text("class App { int newValue; }\n", encoding="utf-8")

    def fail_after_stale(stage: str) -> None:
        if stage == "stale_committed":
            raise RuntimeError("injected")

    failed = refresh_repository(
        repo,
        DEFAULT_CONFIG,
        graph_plugins=[JavaGraphProducer()],
        fault_hook=fail_after_stale,
    )
    store = SQLiteStore(repo / ".context-search" / "index.sqlite")
    assert failed.ok is False
    assert failed.code == "refresh_failed"
    assert failed.network_egress_outcome == "not_attempted"
    assert read_graph_capability(store).status == "stale"

    recovered = refresh_repository(
        repo,
        DEFAULT_CONFIG,
        graph_plugins=[JavaGraphProducer()],
    )

    assert recovered.ok is True
    assert recovered.summary.files.content_changed == 1
    assert read_graph_capability(store).status == "ready"
    assert NumpyVectorStore.generation_pair_count(repo / ".context-search") == 1


def test_quick_refresh_retries_at_most_32_oldest_retryable_skips(
    tmp_path: Path,
) -> None:
    from context_search_tool.scanner import ObservedFileRead, read_observed_file

    repo = tmp_path / "repo"
    repo.mkdir()
    for index in range(33):
        (repo / f"File{index:02d}.java").write_text(
            f"class File{index:02d} {{}}\n",
            encoding="utf-8",
        )

    def unreadable(_repo: Path, observation, **_kwargs):
        return ObservedFileRead(
            status="skipped",
            path=observation.path,
            content=None,
            sha256=None,
            size=None,
            reason="unreadable",
            retryable=True,
            metadata=observation.metadata,
        )

    build_v5_index_snapshot(
        repo,
        DEFAULT_CONFIG,
        graph_plugins=[JavaGraphProducer()],
        scanner=scan_workspace_v5,
        observed_reader=unreadable,
    )
    reads: list[Path] = []

    def recording_reader(repo_path: Path, observation, **kwargs):
        reads.append(observation.path)
        return read_observed_file(repo_path, observation, **kwargs)

    first = refresh_repository(
        repo,
        DEFAULT_CONFIG,
        graph_plugins=[JavaGraphProducer()],
        observed_reader=recording_reader,
    )

    assert first.ok is True
    assert first.summary.work.inventory.retryable_skip_attempts == 32
    assert first.summary.files.direct_dirty == 32
    assert first.summary.files.coverage_skips == 1
    assert reads == [Path(f"File{index:02d}.java") for index in range(32)]

    reads.clear()
    second = refresh_repository(
        repo,
        DEFAULT_CONFIG,
        graph_plugins=[JavaGraphProducer()],
        observed_reader=recording_reader,
    )

    assert second.ok is True
    assert second.summary.work.inventory.retryable_skip_attempts == 1
    assert second.summary.files.coverage_skips == 0
    assert reads == [Path("File32.java")]
