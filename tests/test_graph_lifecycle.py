from __future__ import annotations

import multiprocessing
import os
from pathlib import Path
import sqlite3
import stat
import threading
import time

import pytest

from context_search_tool.config import DEFAULT_CONFIG
from context_search_tool.graph_lifecycle import (
    FULL_REINDEX_REQUIRED_KEY,
    GRAPH_RESOLUTION_STATE_KEY,
    IncompatibleSignalSchemaError,
    IndexBusyError,
    read_graph_capability,
)
from context_search_tool.index_lock import INDEX_LOCK_FILENAME, exclusive_index_lock
from context_search_tool.indexer import build_v5_index_snapshot
from context_search_tool.java_graph import JavaGraphProducer
from context_search_tool.scanner import scan_workspace_v5
from context_search_tool.sqlite_store import SQLiteStore


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
