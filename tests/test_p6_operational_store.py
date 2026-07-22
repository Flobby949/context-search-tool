from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pytest

from context_search_tool import sqlite_store as sqlite_module
from context_search_tool.graph_lifecycle import GRAPH_RESOLUTION_STATE_KEY
from context_search_tool.models import DocumentChunk, SourceFile
from context_search_tool.sqlite_store import SQLiteStore


def _require(name: str) -> Any:
    assert hasattr(sqlite_module, name), f"P6 operational capability {name} is absent"
    return getattr(sqlite_module, name)


def _v5_store(tmp_path: Path) -> SQLiteStore:
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize()
    store.set_metadata("signal_schema_version", "4")
    store.migrate_signal_schema_v5()
    return store


def _source(path: str = "src/app.py") -> SourceFile:
    return SourceFile(
        path=Path(path),
        language="python",
        sha256="a" * 64,
        size=12,
        mtime_ns=101,
    )


def _observation(module: Any, generation: int = 7) -> Any:
    return module.OperationalSourceObservation(
        path=Path("src/app.py"),
        language="python",
        sha256="a" * 64,
        size=12,
        mtime_ns=101,
        change_token=9,
        change_token_kind="ctime_ns",
        observation_generation=generation,
    )


def _skip(module: Any, path: str, generation: int, *, retryable: bool = True) -> Any:
    return module.OperationalScanSkip(
        path=Path(path),
        reason="unreadable",
        language="python",
        size=3,
        mtime_ns=99,
        change_token="token",
        change_token_kind="stat_fallback",
        retryable=retryable,
        first_observation_generation=generation,
        last_observation_generation=generation,
        last_retry_generation=None,
        metadata=(("errno_class", "permission"),),
    )


def _binding(module: Any, sources: tuple[Any, ...], skips: tuple[Any, ...]) -> Any:
    return module.OperationalReadyBinding(
        index_config_hash="1" * 64,
        source_content_fingerprint=module.operational_content_fingerprint(sources),
        source_observation_fingerprint=module.operational_observation_fingerprint(
            sources, skips
        ),
        observation_generation=7,
        manifest_schema_version=2,
        manifest_generation="manifest-0007",
        manifest_sha256="2" * 64,
        vector_descriptor_schema_version=2,
        vector_generation="vectors-0007",
        vector_descriptor_sha256="3" * 64,
        vector_bytes=128,
        vector_ids_bytes=32,
        indexed_at_epoch_s=1234,
        operation_mode="authoritative_index",
        work_metrics=(("source.bytes_hashed", 12), ("vector.bytes_written", 128)),
    )


def test_additive_operational_ddl_is_not_authoritative_until_final_bind(
    tmp_path: Path,
) -> None:
    assert _require("TARGET_OPERATIONAL_SCHEMA_VERSION") == 1
    OperationalSourceObservation = _require("OperationalSourceObservation")
    OperationalScanSkip = _require("OperationalScanSkip")
    assert OperationalSourceObservation is not None
    assert OperationalScanSkip is not None
    store = _v5_store(tmp_path)

    store.initialize_operational_schema_v1()

    assert store.read_operational_snapshot() is None
    assert store.get_metadata("operational_schema_version") is None
    with sqlite3.connect(store.db_path) as connection:
        source_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(source_files)")
        }
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    assert {"change_token", "change_token_kind", "observation_generation"} <= (
        source_columns
    )
    assert "scan_skips" in tables


def test_operational_replacement_and_retry_selection_are_deterministic(
    tmp_path: Path,
) -> None:
    module = sqlite_module
    _require("OperationalSourceObservation")
    _require("OperationalScanSkip")
    store = _v5_store(tmp_path)
    store.initialize_operational_schema_v1()
    store.upsert_source_file(_source())
    source = _observation(module)
    skips = (
        _skip(module, "src/z.py", 7),
        _skip(module, "src/a.py", 7),
        _skip(module, "src/permanent.py", 7, retryable=False),
    )

    store.replace_operational_observations(
        observation_generation=7,
        source_observations=(source,),
        scan_skips=skips,
    )
    selected = store.select_retryable_scan_skips(limit=1, retry_generation=8)
    selected_again = store.select_retryable_scan_skips(limit=2, retry_generation=9)

    assert [item.path.as_posix() for item in selected] == ["src/a.py"]
    assert [item.path.as_posix() for item in selected_again] == [
        "src/z.py",
        "src/a.py",
    ]
    assert selected_again[0].last_retry_generation == 9
    assert selected_again[1].last_retry_generation == 9
    assert store.read_operational_snapshot() is None


def test_final_ready_binds_one_typed_snapshot_without_purging_below_threshold(
    tmp_path: Path,
) -> None:
    module = sqlite_module
    _require("OperationalReadyBinding")
    store = _v5_store(tmp_path)
    store.initialize_operational_schema_v1()
    source_file = _source()
    store.upsert_source_file(source_file)
    chunks = [
        DocumentChunk(
            chunk_id=f"chunk-{index}",
            file_path=source_file.path,
            start_line=index + 1,
            end_line=index + 1,
            content="value = 1",
            chunk_type="symbol",
            embedding_id=f"embedding-{index}",
        )
        for index in range(2)
    ]
    store.replace_chunks(source_file.path, chunks)
    store.replace_chunks(source_file.path, [])
    sources = (_observation(module),)
    skips: tuple[Any, ...] = ()
    store.replace_operational_observations(
        observation_generation=7,
        source_observations=sources,
        scan_skips=skips,
    )
    binding = _binding(module, sources, skips)
    validator_calls: list[str] = []

    store.commit_operational_ready_v1(
        binding=binding,
        topology_fingerprint="4" * 64,
        expected_embedding_ids=set(),
        expected_source_count=1,
        expected_chunk_count=0,
        external_validator=lambda: validator_calls.append("validated"),
        tombstone_purge_limit=1,
    )
    snapshot = store.read_operational_snapshot()

    assert snapshot is not None
    assert snapshot.operational_version == 1
    assert snapshot.graph_status == "ready"
    assert snapshot.binding == binding
    assert snapshot.source_observations == sources
    assert snapshot.scan_skips == ()
    assert snapshot.active_embedding_ids == ()
    assert snapshot.source_count == 1
    assert snapshot.chunk_count == 0
    assert snapshot.tombstone_count == 2
    assert validator_calls == ["validated"]
    assert store.get_metadata(GRAPH_RESOLUTION_STATE_KEY) == "ready"


def test_final_ready_failure_rolls_back_binding_purge_and_graph_ready(
    tmp_path: Path,
) -> None:
    module = sqlite_module
    _require("OperationalReadyBinding")
    store = _v5_store(tmp_path)
    store.initialize_operational_schema_v1()
    store.replace_operational_observations(
        observation_generation=7,
        source_observations=(),
        scan_skips=(),
    )
    binding = _binding(module, (), ())

    def fail() -> None:
        raise RuntimeError("ready fault")

    with pytest.raises(RuntimeError, match="ready fault"):
        store.commit_operational_ready_v1(
            binding=binding,
            topology_fingerprint="4" * 64,
            expected_embedding_ids=set(),
            expected_source_count=0,
            expected_chunk_count=0,
            external_validator=lambda: None,
            before_commit=fail,
        )

    assert store.read_operational_snapshot() is None
    assert store.get_metadata("operational_schema_version") is None
    assert store.get_metadata(GRAPH_RESOLUTION_STATE_KEY) == "stale"


def test_future_operational_schema_is_refused_before_additive_ddl(
    tmp_path: Path,
) -> None:
    error_type = _require("IncompatibleOperationalSchemaError")
    store = _v5_store(tmp_path)
    store.set_metadata("operational_schema_version", "2")
    with sqlite3.connect(store.db_path) as connection:
        before = tuple(
            connection.execute(
                "SELECT name, sql FROM sqlite_master ORDER BY name"
            ).fetchall()
        )

    with pytest.raises(error_type) as caught:
        store.initialize_operational_schema_v1()

    with sqlite3.connect(store.db_path) as connection:
        after = tuple(
            connection.execute(
                "SELECT name, sql FROM sqlite_master ORDER BY name"
            ).fetchall()
        )
    assert caught.value.code == "incompatible_operational_schema"
    assert before == after
