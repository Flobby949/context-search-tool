from __future__ import annotations

import hashlib
import json
import logging
import re
import sqlite3
import stat
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Literal

from context_search_tool.graph_contract import (
    EDGE_QUERY_LIMIT,
    MAX_EDGES_PER_SIGNAL_DIRECTION,
    MAX_EXPLAIN_INCOMING,
    MAX_EXPLAIN_OUTGOING,
    MAX_EXPLAIN_SIGNALS,
    MAX_GRAPH_SEED_SIGNALS,
    MAX_SIGNALS_PER_FILE,
    RESOLUTION_STATES,
    effective_relation_confidence,
)
from context_search_tool.graph_lifecycle import (
    FULL_REINDEX_REQUIRED_KEY,
    GRAPH_RESOLUTION_STATE_KEY,
    GRAPH_RESOLUTION_VERSION_KEY,
    GRAPH_STALE_REASON_KEY,
    OPERATIONAL_SCHEMA_VERSION_KEY,
    PROJECT_UNIT_TOPOLOGY_FINGERPRINT_KEY,
    SIGNAL_SCHEMA_VERSION_KEY,
    GraphCapability,
    GraphIntegrityError,
    GraphIntegrityResult,
    IncompatibleOperationalSchemaError,
    IncompatibleSignalSchemaError,
    IndexBusyError,
    OperationalIntegrityError,
    TARGET_OPERATIONAL_SCHEMA_VERSION,
    TARGET_GRAPH_RESOLUTION_VERSION,
    TARGET_SIGNAL_SCHEMA_VERSION,
    read_graph_capability,
    read_operational_capability,
)
from context_search_tool.models import (
    CodeRelation,
    CodeSignal,
    DocumentChunk,
    RetrievalCandidate,
    SourceFile,
    SymbolRef,
)

logger = logging.getLogger(__name__)
_DIRECT_TEXT_CJK_SEQUENCE_RE = re.compile(r"[㐀-鿿]{2,}")
_SIGNAL_SQL_SAFE_TOKEN_RE = re.compile(r"[a-z0-9_./:$-]+")
_DEFAULT_BUSY_TIMEOUT_MS = 5_000
_RESOLVED_STATES = ("resolved_exact", "resolved_unique")
PRODUCER_RESOLUTION_GENERATION_KEY = "graph_producer_resolution_generation"
TEST_ASSOCIATION_SOURCE_GENERATION_KEY = (
    "graph_test_association_source_generation"
)
FILE_WRITE_IN_PROGRESS_KEY = "graph_file_write_in_progress"
_OPERATIONAL_INDEX_CONFIG_HASH_KEY = "operational_index_config_hash"
_OPERATIONAL_CONTENT_FINGERPRINT_KEY = "operational_content_fingerprint"
_OPERATIONAL_OBSERVATION_FINGERPRINT_KEY = "operational_observation_fingerprint"
_OPERATIONAL_OBSERVATION_GENERATION_KEY = "operational_observation_generation"
_OPERATIONAL_MANIFEST_SCHEMA_KEY = "operational_manifest_schema_version"
_OPERATIONAL_MANIFEST_GENERATION_KEY = "operational_manifest_generation"
_OPERATIONAL_MANIFEST_SHA256_KEY = "operational_manifest_sha256"
_OPERATIONAL_DESCRIPTOR_SCHEMA_KEY = "operational_descriptor_schema_version"
_OPERATIONAL_VECTOR_GENERATION_KEY = "operational_vector_generation"
_OPERATIONAL_DESCRIPTOR_SHA256_KEY = "operational_descriptor_sha256"
_OPERATIONAL_VECTOR_BYTES_KEY = "operational_vector_bytes"
_OPERATIONAL_VECTOR_IDS_BYTES_KEY = "operational_vector_ids_bytes"
_OPERATIONAL_INDEXED_AT_KEY = "operational_indexed_at_epoch_s"
_OPERATIONAL_MODE_KEY = "operational_operation_mode"
_OPERATIONAL_WORK_METRICS_KEY = "operational_work_metrics"
_OPERATIONAL_SOURCE_COUNT_KEY = "operational_source_count"
_OPERATIONAL_CHUNK_COUNT_KEY = "operational_chunk_count"
_OPERATIONAL_EMBEDDING_IDS_SHA256_KEY = "operational_embedding_ids_sha256"
_OPERATION_MODES = frozenset({"index", "authoritative_index", "quick_refresh"})
_WORK_STRING_METRICS = {
    "vector.descriptor_action": frozenset({"reused", "published"}),
}
_SCAN_SKIP_REASONS = frozenset(
    {
        "too_large",
        "binary",
        "unreadable",
        "unsafe_path",
        "changed_during_read",
        "unsupported_encoding",
    }
)
_CHANGE_TOKEN_KINDS = frozenset(
    {
        "ctime_ns",
        "stat_fallback",
        "unavailable",
        "mtime_ns+ctime_ns",
        "mtime_ns",
        "platform_specific",
    }
)
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_GENERATION_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*\Z")
_WORK_METRIC_RE = re.compile(r"[a-z][a-z0-9_.]*\Z")
_MAX_WORK_METRICS = 128
_TOMBSTONE_THRESHOLD_MINIMUM = 5_000


@dataclass(frozen=True)
class RawSQLiteSchemaVersions:
    status: Literal["missing", "valid", "invalid"]
    operational_version: int | None
    graph_version: int | None
    error_code: str | None


@dataclass(frozen=True)
class OperationalSourceObservation:
    path: Path
    language: str
    sha256: str
    size: int
    mtime_ns: int
    change_token: int | str | None
    change_token_kind: str
    observation_generation: int


@dataclass(frozen=True)
class OperationalScanSkip:
    path: Path
    reason: str
    language: str | None
    size: int | None
    mtime_ns: int | None
    change_token: int | str | None
    change_token_kind: str
    retryable: bool
    first_observation_generation: int
    last_observation_generation: int
    last_retry_generation: int | None
    metadata: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class OperationalControlObservation:
    path: Path
    sha256: str
    size: int
    mtime_ns: int
    change_token: int | str | None
    change_token_kind: str
    observation_generation: int


@dataclass(frozen=True)
class OperationalReadyBinding:
    index_config_hash: str
    source_content_fingerprint: str
    source_observation_fingerprint: str
    observation_generation: int
    manifest_schema_version: int
    manifest_generation: str
    manifest_sha256: str
    vector_descriptor_schema_version: int
    vector_generation: str
    vector_descriptor_sha256: str
    vector_bytes: int
    vector_ids_bytes: int
    indexed_at_epoch_s: int
    operation_mode: str
    work_metrics: tuple[tuple[str, int | str], ...]


@dataclass(frozen=True)
class ReadyVectorBinding:
    descriptor_schema_version: int
    generation: str
    descriptor_sha256: str
    vector_bytes: int
    vector_ids_bytes: int
    row_count: int


@dataclass(frozen=True)
class OperationalSnapshot:
    operational_version: int
    graph_version: int
    graph_status: str
    graph_stale_reason: str
    binding: OperationalReadyBinding
    source_observations: tuple[OperationalSourceObservation, ...]
    scan_skips: tuple[OperationalScanSkip, ...]
    control_observations: tuple[OperationalControlObservation, ...]
    active_embedding_ids: tuple[str, ...]
    source_count: int
    chunk_count: int
    tombstone_count: int


def inspect_raw_sqlite_schema_versions(
    db_path: Path,
) -> RawSQLiteSchemaVersions:
    if db_path.is_symlink():
        return RawSQLiteSchemaVersions("invalid", None, None, "unsafe_sqlite")
    if not db_path.exists():
        return RawSQLiteSchemaVersions("missing", None, None, "missing_index")
    try:
        path_stat = db_path.lstat()
    except OSError:
        return RawSQLiteSchemaVersions("invalid", None, None, "unreadable_sqlite")
    if not stat.S_ISREG(path_stat.st_mode):
        return RawSQLiteSchemaVersions("invalid", None, None, "unsafe_sqlite")

    connection: sqlite3.Connection | None = None
    try:
        uri = f"{db_path.resolve(strict=True).as_uri()}?mode=ro"
        connection = sqlite3.connect(uri, uri=True, timeout=0)
        connection.execute("PRAGMA query_only = ON")
        table = connection.execute(
            """
            SELECT 1
            FROM sqlite_master
            WHERE type = 'table' AND name = 'index_metadata'
            """
        ).fetchone()
        if table is None:
            return RawSQLiteSchemaVersions("valid", None, None, None)
        rows = connection.execute(
            """
            SELECT key, value
            FROM index_metadata
            WHERE key IN (?, ?)
            """,
            (OPERATIONAL_SCHEMA_VERSION_KEY, SIGNAL_SCHEMA_VERSION_KEY),
        ).fetchall()
    except (OSError, sqlite3.DatabaseError):
        return RawSQLiteSchemaVersions("invalid", None, None, "malformed_sqlite")
    finally:
        if connection is not None:
            connection.close()
    values = {str(key): value for key, value in rows}
    operational, operational_error = _parse_raw_schema_version(
        values.get(OPERATIONAL_SCHEMA_VERSION_KEY),
        "invalid_operational_schema",
    )
    if operational_error is not None:
        return RawSQLiteSchemaVersions("invalid", None, None, operational_error)
    graph, graph_error = _parse_raw_schema_version(
        values.get(SIGNAL_SCHEMA_VERSION_KEY),
        "invalid_graph_schema",
    )
    if graph_error is not None:
        return RawSQLiteSchemaVersions("invalid", operational, None, graph_error)
    return RawSQLiteSchemaVersions("valid", operational, graph, None)


def _parse_raw_schema_version(
    raw: object,
    error_code: str,
) -> tuple[int | None, str | None]:
    if raw is None or raw == "":
        return None, None
    try:
        version = int(raw)
    except (TypeError, ValueError):
        return None, error_code
    if version < 0 or str(version) != str(raw):
        return None, error_code
    return version, None


class SQLiteStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    def initialize(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            for statement in (
                *_common_schema_statements(),
                *_v4_graph_schema_statements(),
            ):
                connection.execute(statement)

    def initialize_operational_schema_v1(
        self,
        *,
        before_commit: Callable[[], None] | None = None,
        busy_timeout_ms: int = _DEFAULT_BUSY_TIMEOUT_MS,
    ) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        connection = _open_connection(self.db_path, busy_timeout_ms)
        try:
            capability = read_operational_capability(
                _ConnectionMetadataReader(connection)
            )
            if capability.status == "current":
                connection.execute("BEGIN IMMEDIATE")
                for statement in _operational_schema_v1_statements():
                    connection.execute(statement)
                connection.commit()
                _require_operational_schema_v1(connection)
                return
            connection.execute("BEGIN IMMEDIATE")
            capability = read_operational_capability(
                _ConnectionMetadataReader(connection)
            )
            if capability.status == "current":
                for statement in _operational_schema_v1_statements():
                    connection.execute(statement)
                connection.commit()
                _require_operational_schema_v1(connection)
                return
            for statement in _common_schema_statements():
                connection.execute(statement)
            _add_column_if_missing(
                connection,
                "source_files",
                "change_token",
                "TEXT",
            )
            _add_column_if_missing(
                connection,
                "source_files",
                "change_token_kind",
                "TEXT NOT NULL DEFAULT 'unavailable'",
            )
            _add_column_if_missing(
                connection,
                "source_files",
                "observation_generation",
                "INTEGER NOT NULL DEFAULT 0",
            )
            for statement in _operational_schema_v1_statements():
                connection.execute(statement)
            if before_commit is not None:
                before_commit()
            connection.commit()
        except BaseException as error:
            if connection.in_transaction:
                connection.rollback()
            _raise_if_busy(error)
            raise
        finally:
            connection.close()

    def replace_operational_observations(
        self,
        *,
        observation_generation: int,
        source_observations: tuple[OperationalSourceObservation, ...],
        scan_skips: tuple[OperationalScanSkip, ...],
        control_observations: tuple[OperationalControlObservation, ...] = (),
        busy_timeout_ms: int = _DEFAULT_BUSY_TIMEOUT_MS,
    ) -> None:
        if type(observation_generation) is not int or observation_generation < 0:
            raise ValueError("observation generation must be non-negative")
        sources = _validate_source_observations(
            source_observations,
            observation_generation,
        )
        skips = _validate_scan_skips(scan_skips, observation_generation)
        controls = _validate_control_observations(
            control_observations,
            observation_generation,
        )
        source_paths = {_path_key(item.path) for item in sources}
        if source_paths & {_path_key(item.path) for item in skips}:
            raise ValueError("source and scan-skip paths must not overlap")
        connection = _open_connection(self.db_path, busy_timeout_ms)
        try:
            read_operational_capability(_ConnectionMetadataReader(connection))
            _require_operational_schema_v1(connection)
            connection.execute("BEGIN IMMEDIATE")
            read_operational_capability(_ConnectionMetadataReader(connection))
            _require_operational_schema_v1(connection)
            persisted_paths = {
                str(row["path"])
                for row in connection.execute(
                    "SELECT path FROM source_files ORDER BY path"
                ).fetchall()
            }
            if persisted_paths != source_paths:
                raise OperationalIntegrityError(
                    "operational source observations do not match source files"
                )
            for item in sources:
                connection.execute(
                    """
                    UPDATE source_files
                    SET language = ?, sha256 = ?, size = ?, mtime_ns = ?,
                        change_token = ?, change_token_kind = ?,
                        observation_generation = ?
                    WHERE path = ?
                    """,
                    (
                        item.language,
                        item.sha256,
                        item.size,
                        item.mtime_ns,
                        _encode_change_token(item.change_token),
                        item.change_token_kind,
                        item.observation_generation,
                        _path_key(item.path),
                    ),
                )
            connection.execute("DELETE FROM scan_skips")
            for item in skips:
                connection.execute(
                    """
                    INSERT INTO scan_skips (
                        path, reason, language, size, mtime_ns, change_token,
                        change_token_kind, retryable, metadata,
                        first_observation_generation,
                        last_observation_generation, last_retry_generation
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        _path_key(item.path),
                        item.reason,
                        item.language,
                        item.size,
                        item.mtime_ns,
                        _encode_change_token(item.change_token),
                        item.change_token_kind,
                        int(item.retryable),
                        _canonical_json(dict(item.metadata)),
                        item.first_observation_generation,
                        item.last_observation_generation,
                        item.last_retry_generation,
                    ),
                )
            connection.execute("DELETE FROM operational_controls")
            for item in controls:
                connection.execute(
                    """
                    INSERT INTO operational_controls (
                        path, sha256, size, mtime_ns, change_token,
                        change_token_kind, observation_generation
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        _path_key(item.path),
                        item.sha256,
                        item.size,
                        item.mtime_ns,
                        _encode_change_token(item.change_token),
                        item.change_token_kind,
                        item.observation_generation,
                    ),
                )
            connection.commit()
        except BaseException as error:
            if connection.in_transaction:
                connection.rollback()
            _raise_if_busy(error)
            raise
        finally:
            connection.close()

    def select_retryable_scan_skips(
        self,
        *,
        limit: int,
        retry_generation: int,
        busy_timeout_ms: int = _DEFAULT_BUSY_TIMEOUT_MS,
    ) -> tuple[OperationalScanSkip, ...]:
        if type(limit) is not int or limit < 0:
            raise ValueError("retry limit must be non-negative")
        if type(retry_generation) is not int or retry_generation < 0:
            raise ValueError("retry generation must be non-negative")
        connection = _open_connection(self.db_path, busy_timeout_ms)
        try:
            read_operational_capability(_ConnectionMetadataReader(connection))
            _require_operational_schema_v1(connection)
            if limit == 0:
                return ()
            connection.execute("BEGIN IMMEDIATE")
            read_operational_capability(_ConnectionMetadataReader(connection))
            _require_operational_schema_v1(connection)
            rows = connection.execute(
                """
                SELECT path, reason, language, size, mtime_ns, change_token,
                       change_token_kind, retryable, metadata,
                       first_observation_generation,
                       last_observation_generation, last_retry_generation
                FROM scan_skips
                WHERE retryable = 1
                ORDER BY
                    CASE WHEN last_retry_generation IS NULL THEN 0 ELSE 1 END,
                    last_retry_generation,
                    first_observation_generation,
                    path
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            paths = [str(row["path"]) for row in rows]
            if paths:
                connection.executemany(
                    """
                    UPDATE scan_skips
                    SET last_retry_generation = ?
                    WHERE path = ?
                    """,
                    [(retry_generation, path) for path in paths],
                )
            connection.commit()
            return tuple(
                _scan_skip_from_row(row, retry_generation=retry_generation)
                for row in rows
            )
        except BaseException as error:
            if connection.in_transaction:
                connection.rollback()
            _raise_if_busy(error)
            raise
        finally:
            connection.close()

    def read_operational_snapshot(self) -> OperationalSnapshot | None:
        if not self.db_path.exists():
            return None
        connection = _open_connection(self.db_path, _DEFAULT_BUSY_TIMEOUT_MS)
        try:
            connection.execute("BEGIN")
            capability = read_operational_capability(
                _ConnectionMetadataReader(connection)
            )
            if capability.status == "legacy":
                return None
            _require_operational_schema_v1(connection)
            binding = _read_operational_binding(connection)
            sources, skips, controls = _read_operational_observations(connection)
            _validate_bound_operational_observations(
                binding,
                sources,
                skips,
                controls,
            )
            graph = read_graph_capability(_ConnectionMetadataReader(connection))
            source_count = int(
                connection.execute(
                    "SELECT COUNT(*) AS count FROM source_files"
                ).fetchone()["count"]
            )
            chunk_count = int(
                connection.execute(
                    "SELECT COUNT(*) AS count FROM chunks WHERE deleted_at IS NULL"
                ).fetchone()["count"]
            )
            tombstone_count = int(
                connection.execute(
                    "SELECT COUNT(*) AS count FROM chunks WHERE deleted_at IS NOT NULL"
                ).fetchone()["count"]
            )
            embedding_ids = tuple(
                sorted(
                    str(row["embedding_id"])
                    for row in connection.execute(
                        """
                        SELECT embedding_id
                        FROM chunks
                        WHERE deleted_at IS NULL AND embedding_id IS NOT NULL
                        ORDER BY embedding_id
                        """
                    ).fetchall()
                )
            )
            _validate_bound_counts(
                connection,
                source_count=source_count,
                chunk_count=chunk_count,
                embedding_ids=embedding_ids,
            )
            return OperationalSnapshot(
                operational_version=capability.schema_version,
                graph_version=graph.schema_version,
                graph_status=graph.status,
                graph_stale_reason=graph.stale_reason,
                binding=binding,
                source_observations=sources,
                scan_skips=skips,
                control_observations=controls,
                active_embedding_ids=embedding_ids,
                source_count=source_count,
                chunk_count=chunk_count,
                tombstone_count=tombstone_count,
            )
        finally:
            if connection.in_transaction:
                connection.rollback()
            connection.close()

    def commit_operational_ready_v1(
        self,
        *,
        binding: OperationalReadyBinding,
        topology_fingerprint: str,
        expected_embedding_ids: set[str],
        expected_source_count: int,
        expected_chunk_count: int,
        external_validator: Callable[[], None],
        tombstone_purge_limit: int = 0,
        before_commit: Callable[[], None] | None = None,
        busy_timeout_ms: int = _DEFAULT_BUSY_TIMEOUT_MS,
    ) -> GraphIntegrityResult:
        normalized_binding = _validate_operational_binding(binding)
        if normalized_binding != binding:
            raise ValueError("operational work metrics must be canonical")
        if not re.fullmatch(r"[0-9a-f]{64}", topology_fingerprint):
            raise ValueError("topology fingerprint must be a full SHA-256")
        if type(tombstone_purge_limit) is not int or tombstone_purge_limit < 0:
            raise ValueError("tombstone purge limit must be non-negative")
        if type(expected_source_count) is not int or expected_source_count < 0:
            raise ValueError("expected source count must be non-negative")
        if type(expected_chunk_count) is not int or expected_chunk_count < 0:
            raise ValueError("expected chunk count must be non-negative")
        connection = _open_connection(self.db_path, busy_timeout_ms)
        try:
            read_operational_capability(_ConnectionMetadataReader(connection))
            _require_target_schema(connection)
            _require_operational_schema_v1(connection)
            connection.execute("BEGIN IMMEDIATE")
            read_operational_capability(_ConnectionMetadataReader(connection))
            _require_target_schema(connection)
            _require_operational_schema_v1(connection)
            integrity = _graph_integrity(connection)
            if not integrity.ok:
                raise GraphIntegrityError("graph integrity check failed")
            _validate_v5_snapshot(
                connection,
                expected_embedding_ids=expected_embedding_ids,
                expected_source_count=expected_source_count,
                expected_chunk_count=expected_chunk_count,
                expected_producer_resolution_generation=None,
            )
            sources, skips, controls = _read_operational_observations(connection)
            _validate_bound_operational_observations(
                binding,
                sources,
                skips,
                controls,
            )
            external_validator()
            if tombstone_purge_limit:
                self._purge_tombstones(connection, tombstone_purge_limit)
            now = _now()
            _write_operational_binding(
                connection,
                binding,
                source_count=expected_source_count,
                chunk_count=expected_chunk_count,
                embedding_ids=tuple(sorted(expected_embedding_ids)),
                now=now,
            )
            _set_metadata_row(
                connection,
                PROJECT_UNIT_TOPOLOGY_FINGERPRINT_KEY,
                topology_fingerprint,
                now,
            )
            _set_metadata_row(
                connection,
                GRAPH_RESOLUTION_VERSION_KEY,
                str(TARGET_GRAPH_RESOLUTION_VERSION),
                now,
            )
            _set_metadata_row(connection, GRAPH_STALE_REASON_KEY, "", now)
            _set_metadata_row(connection, FULL_REINDEX_REQUIRED_KEY, "0", now)
            _set_metadata_row(connection, "indexed_at", str(binding.indexed_at_epoch_s), now)
            _set_metadata_row(
                connection,
                OPERATIONAL_SCHEMA_VERSION_KEY,
                str(TARGET_OPERATIONAL_SCHEMA_VERSION),
                now,
            )
            _set_metadata_row(connection, GRAPH_RESOLUTION_STATE_KEY, "ready", now)
            if before_commit is not None:
                before_commit()
            connection.commit()
            return integrity
        except BaseException as error:
            if connection.in_transaction:
                connection.rollback()
            _raise_if_busy(error)
            raise
        finally:
            connection.close()

    def _purge_tombstones(
        self,
        connection: sqlite3.Connection,
        limit: int,
    ) -> int:
        if limit <= 0:
            return 0
        changes_before = connection.total_changes
        relation_budget = limit

        counts = _maintenance_counts(connection)
        association_limit = _maintenance_purge_count(
            active_rows=counts["active_associations"],
            deleted_rows=counts["orphan_associations"],
            limit=relation_budget,
        )
        if association_limit:
            association_rows = connection.execute(
                """
                SELECT relation_id
                FROM code_relations
                WHERE producer = 'test_association'
                  AND deleted_at IS NOT NULL
                ORDER BY deleted_at, relation_id
                LIMIT ?
                """,
                (association_limit,),
            ).fetchall()
            association_ids = [
                str(row["relation_id"]) for row in association_rows
            ]
            if association_ids:
                connection.execute(
                    _in_query(
                        "DELETE FROM code_relations "
                        "WHERE relation_id IN ({placeholders})",
                        association_ids,
                    ),
                    association_ids,
                )
                relation_budget -= len(association_ids)

        counts = _maintenance_counts(connection)
        relation_limit = _maintenance_purge_count(
            active_rows=counts["active_relations"],
            deleted_rows=counts["deleted_relations"],
            limit=relation_budget,
        )
        if relation_limit:
            relation_rows = connection.execute(
                """
                SELECT relation_id
                FROM code_relations
                WHERE deleted_at IS NOT NULL
                ORDER BY deleted_at, relation_id
                LIMIT ?
                """,
                (relation_limit,),
            ).fetchall()
            relation_ids = [str(row["relation_id"]) for row in relation_rows]
            if relation_ids:
                connection.execute(
                    _in_query(
                        "DELETE FROM code_relations "
                        "WHERE relation_id IN ({placeholders})",
                        relation_ids,
                    ),
                    relation_ids,
                )

        counts = _maintenance_counts(connection)
        signal_limit = _maintenance_purge_count(
            active_rows=counts["active_signals"],
            deleted_rows=counts["deleted_signals"],
            limit=limit,
        )
        if signal_limit:
            signal_rows = connection.execute(
                """
                SELECT signal_id
                FROM code_signals
                WHERE deleted_at IS NOT NULL
                ORDER BY deleted_at, signal_id
                LIMIT ?
                """,
                (signal_limit,),
            ).fetchall()
            signal_ids = [str(row["signal_id"]) for row in signal_rows]
            if signal_ids:
                placeholders = ", ".join("?" for _ in signal_ids)
                connection.execute(
                    f"""
                        DELETE FROM code_relations
                        WHERE deleted_at IS NOT NULL
                          AND (
                            source_signal_id IN ({placeholders})
                            OR target_signal_id IN ({placeholders})
                          )
                        """,
                    (*signal_ids, *signal_ids),
                )
                connection.execute(
                    _in_query(
                        "DELETE FROM code_signals "
                        "WHERE signal_id IN ({placeholders})",
                        signal_ids,
                    ),
                    signal_ids,
                )

        counts = _maintenance_counts(connection)
        chunk_limit = _maintenance_purge_count(
            active_rows=counts["active_chunks"],
            deleted_rows=counts["deleted_chunks"],
            limit=limit,
        )
        if chunk_limit:
            rows = connection.execute(
                """
                SELECT chunk_id
                FROM chunks
                WHERE deleted_at IS NOT NULL
                ORDER BY deleted_at, chunk_id
                LIMIT ?
                """,
                (chunk_limit,),
            ).fetchall()
            chunk_ids = [str(row["chunk_id"]) for row in rows]
            if chunk_ids:
                signal_rows = connection.execute(
                    _in_query(
                        """
                        SELECT signal_id FROM code_signals
                        WHERE chunk_id IN ({placeholders})
                        """,
                        chunk_ids,
                    ),
                    chunk_ids,
                ).fetchall()
                signal_ids = [str(row["signal_id"]) for row in signal_rows]
                self._delete_search_payloads(connection, chunk_ids)
                connection.execute(
                    _in_query(
                        "DELETE FROM code_relations "
                        "WHERE deleted_at IS NOT NULL "
                        "AND source_chunk_id IN ({placeholders})",
                        chunk_ids,
                    ),
                    chunk_ids,
                )
                if signal_ids:
                    connection.execute(
                        _in_query(
                            "DELETE FROM code_relations "
                            "WHERE deleted_at IS NOT NULL "
                            "AND target_signal_id IN ({placeholders})",
                            signal_ids,
                        ),
                        signal_ids,
                    )
                connection.execute(
                    _in_query(
                        "DELETE FROM code_signals "
                        "WHERE deleted_at IS NOT NULL "
                        "AND chunk_id IN ({placeholders})",
                        chunk_ids,
                    ),
                    chunk_ids,
                )
                connection.execute(
                    _in_query(
                        "DELETE FROM chunks WHERE chunk_id IN ({placeholders})",
                        chunk_ids,
                    ),
                    chunk_ids,
                )

        counts = _maintenance_counts(connection)
        symbol_limit = _maintenance_purge_count(
            active_rows=counts["active_symbols"],
            deleted_rows=counts["orphan_symbols"],
            limit=limit,
        )
        if symbol_limit:
            symbol_rows = connection.execute(
                """
                SELECT symbols.symbol_id
                FROM symbols
                LEFT JOIN chunk_symbols
                  ON chunk_symbols.symbol_id = symbols.symbol_id
                WHERE chunk_symbols.symbol_id IS NULL
                ORDER BY symbols.symbol_id
                LIMIT ?
                """,
                (symbol_limit,),
            ).fetchall()
            symbol_ids = [int(row["symbol_id"]) for row in symbol_rows]
            if symbol_ids:
                connection.execute(
                    _in_query(
                        "DELETE FROM symbols WHERE symbol_id IN ({placeholders})",
                        symbol_ids,
                    ),
                    symbol_ids,
                )

        return connection.total_changes - changes_before

    def inspect_signal_schema_version(self) -> int:
        if not self.db_path.exists():
            return 0
        with self._connect() as connection:
            return _stored_signal_schema_version(connection)

    def initialize_v5(
        self,
        *,
        stale_reason: str = "full_reindex",
        before_commit: Callable[[], None] | None = None,
        busy_timeout_ms: int = _DEFAULT_BUSY_TIMEOUT_MS,
    ) -> None:
        if not stale_reason:
            raise ValueError("graph stale reason must not be empty")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        connection = _open_connection(self.db_path, busy_timeout_ms)
        try:
            stored_version = _stored_signal_schema_version(connection)
            if stored_version > TARGET_SIGNAL_SCHEMA_VERSION:
                raise IncompatibleSignalSchemaError(stored_version)
            if stored_version == TARGET_SIGNAL_SCHEMA_VERSION:
                _require_v5_tables(connection)
                return

            connection.execute("BEGIN IMMEDIATE")
            stored_version = _stored_signal_schema_version(connection)
            if stored_version > TARGET_SIGNAL_SCHEMA_VERSION:
                raise IncompatibleSignalSchemaError(stored_version)
            for statement in _common_schema_statements():
                connection.execute(statement)
            connection.execute("DROP TABLE IF EXISTS code_relations")
            connection.execute("DROP TABLE IF EXISTS code_signals")
            for statement in _v5_schema_statements():
                connection.execute(statement)
            now = _now()
            reason = "schema_migration" if stored_version else stale_reason
            for key, value in (
                (SIGNAL_SCHEMA_VERSION_KEY, str(TARGET_SIGNAL_SCHEMA_VERSION)),
                (
                    GRAPH_RESOLUTION_VERSION_KEY,
                    str(TARGET_GRAPH_RESOLUTION_VERSION),
                ),
                (GRAPH_RESOLUTION_STATE_KEY, "stale"),
                (GRAPH_STALE_REASON_KEY, reason),
                (FULL_REINDEX_REQUIRED_KEY, "1"),
                (PRODUCER_RESOLUTION_GENERATION_KEY, "0"),
                (TEST_ASSOCIATION_SOURCE_GENERATION_KEY, "-1"),
                (FILE_WRITE_IN_PROGRESS_KEY, ""),
            ):
                _set_metadata_row(connection, key, value, now)
            if before_commit is not None:
                before_commit()
            connection.commit()
        except BaseException as error:
            if connection.in_transaction:
                connection.rollback()
            _raise_if_busy(error)
            raise
        finally:
            connection.close()

    def migrate_signal_schema_v5(
        self,
        *,
        before_commit: Callable[[], None] | None = None,
        busy_timeout_ms: int = _DEFAULT_BUSY_TIMEOUT_MS,
    ) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        connection = _open_connection(self.db_path, busy_timeout_ms)
        try:
            stored_version = _stored_signal_schema_version(connection)
            if stored_version > TARGET_SIGNAL_SCHEMA_VERSION:
                raise IncompatibleSignalSchemaError(stored_version)
            if stored_version == TARGET_SIGNAL_SCHEMA_VERSION:
                _require_v5_tables(connection)
                return

            connection.execute("BEGIN IMMEDIATE")
            stored_version = _stored_signal_schema_version(connection)
            if stored_version > TARGET_SIGNAL_SCHEMA_VERSION:
                raise IncompatibleSignalSchemaError(stored_version)
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS index_metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at INTEGER NOT NULL
                )
                """
            )
            connection.execute("DROP TABLE IF EXISTS code_relations")
            connection.execute("DROP TABLE IF EXISTS code_signals")
            for statement in _v5_schema_statements():
                connection.execute(statement)
            now = _now()
            _set_metadata_row(
                connection,
                SIGNAL_SCHEMA_VERSION_KEY,
                str(TARGET_SIGNAL_SCHEMA_VERSION),
                now,
            )
            _set_metadata_row(
                connection,
                GRAPH_RESOLUTION_VERSION_KEY,
                str(TARGET_GRAPH_RESOLUTION_VERSION),
                now,
            )
            _set_metadata_row(
                connection,
                GRAPH_RESOLUTION_STATE_KEY,
                "stale",
                now,
            )
            _set_metadata_row(
                connection,
                GRAPH_STALE_REASON_KEY,
                "schema_migration",
                now,
            )
            _set_metadata_row(
                connection,
                FULL_REINDEX_REQUIRED_KEY,
                "1",
                now,
            )
            _set_metadata_row(
                connection,
                PRODUCER_RESOLUTION_GENERATION_KEY,
                "0",
                now,
            )
            _set_metadata_row(
                connection,
                TEST_ASSOCIATION_SOURCE_GENERATION_KEY,
                "-1",
                now,
            )
            _set_metadata_row(
                connection,
                FILE_WRITE_IN_PROGRESS_KEY,
                "",
                now,
            )
            if before_commit is not None:
                before_commit()
            connection.commit()
        except BaseException as error:
            if connection.in_transaction:
                connection.rollback()
            _raise_if_busy(error)
            raise
        finally:
            connection.close()

    def replace_graph_facts(
        self,
        file_path: Path,
        signals: list[CodeSignal],
        relations: list[CodeRelation],
    ) -> None:
        path = _path_key(file_path)
        deleted_at = _now()
        with self._connect() as connection:
            _require_v5_tables(connection)
            _replace_signals_v5(
                connection,
                path,
                signals,
                deleted_at,
            )
            _replace_relations_v5(
                connection,
                path,
                relations,
                deleted_at,
            )

    def append_graph_relations(self, relations: list[CodeRelation]) -> None:
        if not relations:
            return
        with self._connect() as connection:
            _require_v5_tables(connection)
            for relation in relations:
                _upsert_relation_v5(connection, relation)

    def graph_signal_for_id(self, signal_id: str) -> CodeSignal | None:
        with self._connect() as connection:
            _require_v5_tables(connection)
            row = connection.execute(
                """
                SELECT *
                FROM code_signals
                WHERE signal_id = ?
                  AND deleted_at IS NULL
                """,
                (signal_id,),
            ).fetchone()
        return _signal_from_row(row) if row is not None else None

    def graph_relation_for_id(self, relation_id: str) -> CodeRelation | None:
        with self._connect() as connection:
            _require_v5_tables(connection)
            row = connection.execute(
                """
                SELECT *
                FROM code_relations
                WHERE relation_id = ?
                  AND deleted_at IS NULL
                """,
                (relation_id,),
            ).fetchone()
        return _relation_from_row(row) if row is not None else None

    def graph_integrity(self) -> GraphIntegrityResult:
        with self._connect() as connection:
            _require_v5_tables(connection)
            return _graph_integrity(connection)

    def active_relation_source_paths(self, kinds: tuple[str, ...]) -> set[Path]:
        normalized = _dedupe_values(list(kinds))
        if not normalized:
            return set()
        with self._connect() as connection:
            _require_v5_tables(connection)
            rows = connection.execute(
                _in_query(
                    """
                    SELECT DISTINCT source_file_path
                    FROM code_relations
                    WHERE kind IN ({placeholders})
                      AND deleted_at IS NULL
                    ORDER BY source_file_path
                    """,
                    normalized,
                ),
                normalized,
            ).fetchall()
        return {Path(str(row["source_file_path"])) for row in rows}

    def mark_graph_stale(
        self,
        reason: str,
        *,
        full_reindex_required: bool | None = None,
        before_commit: Callable[[], None] | None = None,
        busy_timeout_ms: int = _DEFAULT_BUSY_TIMEOUT_MS,
    ) -> None:
        if not reason:
            raise ValueError("graph stale reason must not be empty")
        connection = _open_connection(self.db_path, busy_timeout_ms)
        try:
            _require_target_schema(connection)
            connection.execute("BEGIN IMMEDIATE")
            now = _now()
            _set_metadata_row(
                connection,
                GRAPH_RESOLUTION_STATE_KEY,
                "stale",
                now,
            )
            _set_metadata_row(
                connection,
                GRAPH_STALE_REASON_KEY,
                reason,
                now,
            )
            if full_reindex_required:
                _set_metadata_row(
                    connection,
                    FULL_REINDEX_REQUIRED_KEY,
                    "1",
                    now,
                )
            if before_commit is not None:
                before_commit()
            connection.commit()
        except BaseException as error:
            if connection.in_transaction:
                connection.rollback()
            _raise_if_busy(error)
            raise
        finally:
            connection.close()

    def mark_graph_ready(
        self,
        *,
        topology_fingerprint: str,
        expected_embedding_ids: set[str] | None = None,
        expected_source_count: int | None = None,
        expected_chunk_count: int | None = None,
        expected_producer_resolution_generation: int | None = None,
        external_validator: Callable[[], None] | None = None,
        indexed_at: int | None = None,
        before_commit: Callable[[], None] | None = None,
        busy_timeout_ms: int = _DEFAULT_BUSY_TIMEOUT_MS,
    ) -> GraphIntegrityResult:
        if not re.fullmatch(r"[0-9a-f]{64}", topology_fingerprint):
            raise ValueError("topology fingerprint must be a full SHA-256")
        connection = _open_connection(self.db_path, busy_timeout_ms)
        try:
            _require_target_schema(connection)
            connection.execute("BEGIN IMMEDIATE")
            integrity = _graph_integrity(connection)
            if not integrity.ok:
                raise GraphIntegrityError("graph integrity check failed")
            if any(
                value is not None
                for value in (
                    expected_embedding_ids,
                    expected_source_count,
                    expected_chunk_count,
                    expected_producer_resolution_generation,
                )
            ):
                _validate_v5_snapshot(
                    connection,
                    expected_embedding_ids=expected_embedding_ids,
                    expected_source_count=expected_source_count,
                    expected_chunk_count=expected_chunk_count,
                    expected_producer_resolution_generation=(
                        expected_producer_resolution_generation
                    ),
                )
            if external_validator is not None:
                external_validator()
            now = _now()
            _set_metadata_row(
                connection,
                PROJECT_UNIT_TOPOLOGY_FINGERPRINT_KEY,
                topology_fingerprint,
                now,
            )
            _set_metadata_row(
                connection,
                GRAPH_RESOLUTION_VERSION_KEY,
                str(TARGET_GRAPH_RESOLUTION_VERSION),
                now,
            )
            _set_metadata_row(
                connection,
                GRAPH_STALE_REASON_KEY,
                "",
                now,
            )
            _set_metadata_row(
                connection,
                FULL_REINDEX_REQUIRED_KEY,
                "0",
                now,
            )
            _set_metadata_row(
                connection,
                GRAPH_RESOLUTION_STATE_KEY,
                "ready",
                now,
            )
            if indexed_at is not None:
                _set_metadata_row(
                    connection,
                    "indexed_at",
                    str(indexed_at),
                    now,
                )
            if before_commit is not None:
                before_commit()
            connection.commit()
            return integrity
        except BaseException as error:
            if connection.in_transaction:
                connection.rollback()
            _raise_if_busy(error)
            raise
        finally:
            connection.close()

    def validate_ready_v5_snapshot(
        self,
        *,
        topology_fingerprint: str,
        expected_embedding_ids: set[str],
        expected_source_count: int,
        expected_chunk_count: int,
        external_validator: Callable[[], None] | None = None,
    ) -> GraphIntegrityResult:
        connection = _open_connection(self.db_path, _DEFAULT_BUSY_TIMEOUT_MS)
        try:
            _require_target_schema(connection)
            connection.execute("BEGIN")
            capability = read_graph_capability(
                _ConnectionMetadataReader(connection)
            )
            if capability.status != "ready":
                raise GraphIntegrityError("graph snapshot is not ready")
            if (
                _metadata_value(
                    connection,
                    PROJECT_UNIT_TOPOLOGY_FINGERPRINT_KEY,
                )
                != topology_fingerprint
            ):
                raise GraphIntegrityError("project topology fingerprint mismatch")
            integrity = _graph_integrity(connection)
            if not integrity.ok:
                raise GraphIntegrityError("graph integrity check failed")
            producer_generation = _integer_metadata(
                connection,
                PRODUCER_RESOLUTION_GENERATION_KEY,
            )
            _validate_v5_snapshot(
                connection,
                expected_embedding_ids=expected_embedding_ids,
                expected_source_count=expected_source_count,
                expected_chunk_count=expected_chunk_count,
                expected_producer_resolution_generation=producer_generation,
            )
            if external_validator is not None:
                external_validator()
            return integrity
        finally:
            if connection.in_transaction:
                connection.rollback()
            connection.close()

    @contextmanager
    def graph_read_session(
        self,
        *,
        busy_timeout_ms: int = _DEFAULT_BUSY_TIMEOUT_MS,
    ) -> Iterator[GraphReadSession]:
        session = GraphReadSession(self.db_path, busy_timeout_ms=busy_timeout_ms)
        with session:
            yield session

    @contextmanager
    def graph_resolution_session(
        self,
        *,
        busy_timeout_ms: int = _DEFAULT_BUSY_TIMEOUT_MS,
    ) -> Iterator[Any]:
        connection = _open_connection(self.db_path, busy_timeout_ms)
        try:
            _require_target_schema(connection)
            connection.execute("BEGIN IMMEDIATE")
            session = _SQLiteResolutionSession(connection)
            yield session
            connection.commit()
        except BaseException as error:
            if connection.in_transaction:
                connection.rollback()
            _raise_if_busy(error)
            raise
        finally:
            connection.close()

    @contextmanager
    def test_association_session(
        self,
        *,
        busy_timeout_ms: int = _DEFAULT_BUSY_TIMEOUT_MS,
    ) -> Iterator[Any]:
        connection = _open_connection(self.db_path, busy_timeout_ms)
        try:
            _require_target_schema(connection)
            connection.execute("BEGIN IMMEDIATE")
            session = _SQLiteTestAssociationSession(connection)
            yield session
            connection.commit()
        except BaseException as error:
            if connection.in_transaction:
                connection.rollback()
            _raise_if_busy(error)
            raise
        finally:
            connection.close()

    def advance_producer_resolution_generation(self) -> int:
        with self._connect() as connection:
            _require_target_schema(connection)
            raw = _metadata_value(
                connection,
                PRODUCER_RESOLUTION_GENERATION_KEY,
            )
            try:
                generation = int(raw or "0") + 1
            except ValueError as error:
                raise GraphIntegrityError(
                    "invalid producer resolution generation"
                ) from error
            _set_metadata_row(
                connection,
                PRODUCER_RESOLUTION_GENERATION_KEY,
                str(generation),
                _now(),
            )
        return generation

    def begin_v5_file_write(self, file_path: Path) -> None:
        self.set_metadata(FILE_WRITE_IN_PROGRESS_KEY, _path_key(file_path))

    def finish_v5_file_write(self, file: SourceFile) -> None:
        with self._connect() as connection:
            _require_target_schema(connection)
            current = _metadata_value(connection, FILE_WRITE_IN_PROGRESS_KEY)
            if current != _path_key(file.path):
                raise GraphIntegrityError("file write marker mismatch")
            connection.execute(
                """
                INSERT INTO source_files (
                    path, language, sha256, size, mtime_ns,
                    is_generated, is_test, metadata
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(path) DO UPDATE SET
                    language = excluded.language,
                    sha256 = excluded.sha256,
                    size = excluded.size,
                    mtime_ns = excluded.mtime_ns,
                    is_generated = excluded.is_generated,
                    is_test = excluded.is_test,
                    metadata = excluded.metadata
                """,
                (
                    _path_key(file.path),
                    file.language,
                    file.sha256,
                    file.size,
                    file.mtime_ns,
                    int(file.is_generated),
                    int(file.is_test),
                    _to_json(file.metadata),
                ),
            )
            _set_metadata_row(
                connection,
                FILE_WRITE_IN_PROGRESS_KEY,
                "",
                _now(),
            )

    def upsert_source_file(self, file: SourceFile) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO source_files (
                    path, language, sha256, size, mtime_ns,
                    is_generated, is_test, metadata
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(path) DO UPDATE SET
                    language = excluded.language,
                    sha256 = excluded.sha256,
                    size = excluded.size,
                    mtime_ns = excluded.mtime_ns,
                    is_generated = excluded.is_generated,
                    is_test = excluded.is_test,
                    metadata = excluded.metadata
                """,
                (
                    _path_key(file.path),
                    file.language,
                    file.sha256,
                    file.size,
                    file.mtime_ns,
                    int(file.is_generated),
                    int(file.is_test),
                    _to_json(file.metadata),
                ),
            )

    def source_file_for_path(self, path: Path) -> SourceFile | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT *
                FROM source_files
                WHERE path = ?
                """,
                (_path_key(path),),
            ).fetchone()
        if row is None:
            return None
        return _source_file_from_row(row)

    def source_file_paths(self) -> set[Path]:
        with self._connect() as connection:
            rows = connection.execute("SELECT path FROM source_files").fetchall()
        return {Path(row["path"]) for row in rows}

    def source_files_snapshot(self) -> tuple[SourceFile, ...]:
        if not self.db_path.exists():
            return ()
        with self._connect() as connection:
            if not _table_exists(connection, "source_files"):
                return ()
            rows = connection.execute(
                "SELECT * FROM source_files ORDER BY path"
            ).fetchall()
        return tuple(_source_file_from_row(row) for row in rows)

    def persisted_file_paths_snapshot(self) -> set[Path]:
        if not self.db_path.exists():
            return set()
        paths: set[Path] = set()
        with self._connect() as connection:
            if _table_exists(connection, "source_files"):
                paths.update(
                    Path(row["path"])
                    for row in connection.execute(
                        "SELECT path FROM source_files"
                    )
                )
            if _table_exists(connection, "chunks"):
                paths.update(
                    Path(row["file_path"])
                    for row in connection.execute(
                        """
                        SELECT DISTINCT file_path FROM chunks
                        WHERE deleted_at IS NULL
                        """
                    )
                )
            if _table_exists(connection, "code_signals"):
                paths.update(
                    Path(row["file_path"])
                    for row in connection.execute(
                        """
                        SELECT DISTINCT file_path FROM code_signals
                        WHERE deleted_at IS NULL
                        """
                    )
                )
        return paths

    def indexed_file_paths(self) -> set[Path]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT DISTINCT file_path
                FROM chunks
                WHERE deleted_at IS NULL
                """
            ).fetchall()
        return {Path(row["file_path"]) for row in rows}

    def replace_chunks(self, file_path: Path, chunks: list[DocumentChunk]) -> None:
        path = _path_key(file_path)
        deleted_at = _now()
        with self._connect() as connection:
            active_ids = self._active_chunk_ids_for_file(connection, path)
            self._delete_search_payloads(connection, active_ids)
            if active_ids:
                connection.executemany(
                    "UPDATE chunks SET deleted_at = ? WHERE chunk_id = ?",
                    [(deleted_at, chunk_id) for chunk_id in active_ids],
                )

            incoming_ids = [chunk.chunk_id for chunk in chunks]
            active_id_set = set(active_ids)
            unchecked_incoming_ids = [
                chunk_id
                for chunk_id in incoming_ids
                if chunk_id not in active_id_set
            ]
            existing_incoming_ids = self._existing_chunk_ids(
                connection,
                unchecked_incoming_ids,
            )
            self._delete_search_payloads(
                connection,
                [
                    chunk_id
                    for chunk_id in unchecked_incoming_ids
                    if chunk_id in existing_incoming_ids
                ],
            )

            for chunk in chunks:
                self._insert_chunk(connection, chunk)

    def replace_signals(self, file_path: Path, signals: list[CodeSignal]) -> None:
        path = _path_key(file_path)
        deleted_at = _now()
        with self._connect() as connection:
            if _has_column(connection, "code_signals", "qualified_name"):
                _replace_signals_v5(
                    connection,
                    path,
                    signals,
                    deleted_at,
                )
                return
            connection.execute(
                """
                UPDATE code_signals
                SET deleted_at = ?
                WHERE file_path = ?
                  AND deleted_at IS NULL
                """,
                (deleted_at, path),
            )
            for signal in signals:
                connection.execute(
                    """
                    INSERT INTO code_signals (
                        signal_id, chunk_id, file_path, kind, name,
                        start_line, end_line, language, tokens, metadata, deleted_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
                    ON CONFLICT(signal_id) DO UPDATE SET
                        chunk_id = excluded.chunk_id,
                        file_path = excluded.file_path,
                        kind = excluded.kind,
                        name = excluded.name,
                        start_line = excluded.start_line,
                        end_line = excluded.end_line,
                        language = excluded.language,
                        tokens = excluded.tokens,
                        metadata = excluded.metadata,
                        deleted_at = excluded.deleted_at
                    """,
                    (
                        signal.signal_id,
                        signal.chunk_id,
                        _path_key(signal.file_path),
                        signal.kind,
                        signal.name,
                        signal.start_line,
                        signal.end_line,
                        signal.language,
                        _to_json_list(signal.tokens),
                        _to_json(signal.metadata),
                    ),
                )

    def replace_relations(
        self, file_path: Path, relations: list[CodeRelation]
    ) -> None:
        path = _path_key(file_path)
        deleted_at = _now()
        with self._connect() as connection:
            if _has_column(connection, "code_relations", "resolution"):
                _replace_relations_v5(
                    connection,
                    path,
                    relations,
                    deleted_at,
                )
                return
            connection.execute(
                """
                UPDATE code_relations
                SET deleted_at = ?
                WHERE source_file_path = ?
                  AND deleted_at IS NULL
                """,
                (deleted_at, path),
            )
            for relation in relations:
                source = connection.execute(
                    """
                    SELECT chunk_id, file_path
                    FROM code_signals
                    WHERE signal_id = ?
                      AND deleted_at IS NULL
                    """,
                    (relation.source_signal_id,),
                ).fetchone()
                if source is None:
                    continue
                connection.execute(
                    """
                    INSERT INTO code_relations (
                        relation_id, source_signal_id, source_chunk_id,
                        source_file_path, target_name, kind, confidence,
                        metadata, deleted_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL)
                    ON CONFLICT(relation_id) DO UPDATE SET
                        source_signal_id = excluded.source_signal_id,
                        source_chunk_id = excluded.source_chunk_id,
                        source_file_path = excluded.source_file_path,
                        target_name = excluded.target_name,
                        kind = excluded.kind,
                        confidence = excluded.confidence,
                        metadata = excluded.metadata,
                        deleted_at = excluded.deleted_at
                    """,
                    (
                        relation.relation_id,
                        relation.source_signal_id,
                        source["chunk_id"],
                        source["file_path"],
                        relation.target_name,
                        relation.kind,
                        relation.confidence,
                        _to_json(relation.metadata),
                    ),
                )

    def signals_for_chunk(self, chunk_id: str) -> list[CodeSignal]:
        with self._connect() as connection:
            legacy_filter = (
                "AND producer = 'legacy'"
                if _has_column(connection, "code_signals", "producer")
                else ""
            )
            rows = connection.execute(
                f"""
                SELECT *
                FROM code_signals
                WHERE chunk_id = ?
                  AND deleted_at IS NULL
                  {legacy_filter}
                ORDER BY start_line, end_line, kind, name, signal_id
                """,
                (chunk_id,),
            ).fetchall()
        return [_signal_from_row(row) for row in rows]

    def signals_for_chunks(self, chunk_ids: list[str]) -> dict[str, list[CodeSignal]]:
        chunk_ids = _dedupe_values(chunk_ids)
        grouped: dict[str, list[CodeSignal]] = {chunk_id: [] for chunk_id in chunk_ids}
        if not chunk_ids:
            return grouped

        with self._connect() as connection:
            legacy_filter = (
                "AND producer = 'legacy'"
                if _has_column(connection, "code_signals", "producer")
                else ""
            )
            rows = connection.execute(
                _in_query(
                    f"""
                SELECT *
                FROM code_signals
                WHERE chunk_id IN ({{placeholders}})
                  AND deleted_at IS NULL
                  {legacy_filter}
                ORDER BY chunk_id, start_line, end_line, kind, name, signal_id
                """,
                    chunk_ids,
                ),
                chunk_ids,
            ).fetchall()

        for row in rows:
            grouped[row["chunk_id"]].append(_signal_from_row(row))
        return grouped

    def signal_search(self, tokens: list[str], limit: int) -> list[CodeSignal]:
        normalized = [token.lower() for token in tokens if token]
        if not normalized or limit <= 0:
            return []

        matches: list[tuple[CodeSignal, float]] = []
        with self._connect() as connection:
            legacy_filter = (
                "AND recallable = 1 AND producer = 'legacy'"
                if _has_column(connection, "code_signals", "recallable")
                else ""
            )
            row_filter, row_filter_values = _signal_row_prefilter(normalized)
            rows = connection.execute(
                f"""
                SELECT *
                FROM code_signals
                WHERE deleted_at IS NULL
                  {legacy_filter}
                  {row_filter}
                """,
                row_filter_values,
            ).fetchall()

        for row in rows:
            signal = _signal_from_row(row)
            haystack = " ".join(
                [
                    signal.name,
                    " ".join(signal.tokens),
                    _metadata_search_text(signal.metadata),
                ]
            ).lower()
            score = sum(1.0 for token in normalized if token in haystack)
            if score > 0:
                matches.append((signal, score))

        matches.sort(
            key=lambda item: (
                -item[1],
                0 if item[0].kind == "endpoint" else 1,
                item[0].start_line,
                item[0].end_line,
                item[0].kind,
                item[0].name,
                item[0].signal_id,
            )
        )
        return [signal for signal, _score in matches[:limit]]

    def relations_for_source(self, source_signal_id: str) -> list[CodeRelation]:
        with self._connect() as connection:
            legacy_filter = (
                "AND resolution = 'legacy'"
                if _has_column(connection, "code_relations", "resolution")
                else ""
            )
            rows = connection.execute(
                f"""
                SELECT *
                FROM code_relations
                WHERE source_signal_id = ?
                  AND deleted_at IS NULL
                  {legacy_filter}
                ORDER BY kind, target_name, relation_id
                """,
                (source_signal_id,),
            ).fetchall()
        return [
            _relation_from_row(
                row,
                v4_confidence_from_effective=False,
            )
            for row in rows
        ]

    def relations_for_sources(
        self, source_signal_ids: list[str]
    ) -> dict[str, list[CodeRelation]]:
        source_signal_ids = _dedupe_values(source_signal_ids)
        grouped: dict[str, list[CodeRelation]] = {
            source_signal_id: [] for source_signal_id in source_signal_ids
        }
        if not source_signal_ids:
            return grouped

        with self._connect() as connection:
            legacy_filter = (
                "AND resolution = 'legacy'"
                if _has_column(connection, "code_relations", "resolution")
                else ""
            )
            rows = connection.execute(
                _in_query(
                    f"""
                SELECT *
                FROM code_relations
                WHERE source_signal_id IN ({{placeholders}})
                  AND deleted_at IS NULL
                  {legacy_filter}
                ORDER BY source_signal_id, kind, target_name, relation_id
                """,
                    source_signal_ids,
                ),
                source_signal_ids,
            ).fetchall()

        for row in rows:
            grouped[row["source_signal_id"]].append(
                _relation_from_row(
                    row,
                    v4_confidence_from_effective=False,
                )
            )
        return grouped

    def relations_targeting(self, target_name: str) -> list[CodeRelation]:
        with self._connect() as connection:
            legacy_filter = (
                "AND resolution = 'legacy'"
                if _has_column(connection, "code_relations", "resolution")
                else ""
            )
            rows = connection.execute(
                f"""
                SELECT *
                FROM code_relations
                WHERE target_name = ?
                  AND deleted_at IS NULL
                  {legacy_filter}
                ORDER BY kind, source_signal_id, relation_id
                """,
                (target_name,),
            ).fetchall()
        return [
            _relation_from_row(
                row,
                v4_confidence_from_effective=False,
            )
            for row in rows
        ]

    def chunks_matching_signal_or_symbol(
        self, target_name: str, limit: int
    ) -> list[DocumentChunk]:
        if not target_name or limit <= 0:
            return []

        with self._connect() as connection:
            rows = _chunks_matching_name(connection, target_name, limit)
            if not rows and "." in target_name:
                owner_name, member_name = target_name.rsplit(".", 1)
                rows = _chunks_matching_member_name(
                    connection,
                    owner_name,
                    member_name,
                    limit,
                )
            chunks_by_id = self._chunks_from_rows(connection, rows)
            return [chunks_by_id[row["chunk_id"]] for row in rows]

    def chunks_matching_signal_or_symbols(
        self, target_names: list[str], limit_per_target: int
    ) -> dict[str, list[DocumentChunk]]:
        target_names = _dedupe_values(target_names)
        grouped: dict[str, list[DocumentChunk]] = {
            target_name: [] for target_name in target_names
        }
        if limit_per_target <= 0:
            return grouped

        with self._connect() as connection:
            rows_by_target: dict[str, list[sqlite3.Row]] = {}
            unique_rows: dict[str, sqlite3.Row] = {}
            for target_name in target_names:
                if not target_name:
                    continue
                rows = _chunks_matching_name(connection, target_name, limit_per_target)
                if not rows and "." in target_name:
                    owner_name, member_name = target_name.rsplit(".", 1)
                    rows = _chunks_matching_member_name(
                        connection,
                        owner_name,
                        member_name,
                        limit_per_target,
                    )
                rows_by_target[target_name] = rows
                unique_rows.update((row["chunk_id"], row) for row in rows)
            chunks_by_id = self._chunks_from_rows(
                connection,
                list(unique_rows.values()),
            )
            for target_name, rows in rows_by_target.items():
                grouped[target_name] = [
                    chunks_by_id[row["chunk_id"]] for row in rows
                ]
        return grouped

    def get_metadata(self, key: str) -> str | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT value
                FROM index_metadata
                WHERE key = ?
                """,
                (key,),
            ).fetchone()
        if row is None:
            return None
        return str(row["value"])

    def set_metadata(self, key: str, value: str) -> None:
        with self._connect() as connection:
            if (
                key == FULL_REINDEX_REQUIRED_KEY
                and value == "0"
                and _stored_signal_schema_version(connection)
                == TARGET_SIGNAL_SCHEMA_VERSION
            ):
                raise ValueError(
                    "full reindex flag clears only with the ready transaction"
                )
            connection.execute(
                """
                INSERT INTO index_metadata (key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = excluded.updated_at
                """,
                (key, value, _now()),
            )

    def clear_signal_data(self) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM code_relations")
            connection.execute("DELETE FROM code_signals")

    def mark_file_deleted(self, file_path: Path) -> None:
        path = _path_key(file_path)
        deleted_at = _now()
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE code_relations
                SET deleted_at = ?
                WHERE source_file_path = ?
                  AND deleted_at IS NULL
                """,
                (deleted_at, path),
            )
            connection.execute(
                """
                UPDATE code_signals
                SET deleted_at = ?
                WHERE file_path = ?
                  AND deleted_at IS NULL
                """,
                (deleted_at, path),
            )
            active_ids = self._active_chunk_ids_for_file(connection, path)
            self._delete_search_payloads(connection, active_ids)
            if active_ids:
                connection.executemany(
                    "UPDATE chunks SET deleted_at = ? WHERE chunk_id = ?",
                    [(deleted_at, chunk_id) for chunk_id in active_ids],
                )
            connection.execute("DELETE FROM source_files WHERE path = ?", (path,))

    def deleted_chunk_ids(self) -> set[str]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT chunk_id FROM chunks WHERE deleted_at IS NOT NULL"
            ).fetchall()
        return {row["chunk_id"] for row in rows}

    def lexical_search(self, tokens: list[str], limit: int) -> list[RetrievalCandidate]:
        query = _fts_query(tokens)
        if not query or limit <= 0:
            return []
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT chunks.chunk_id, bm25(chunks_fts) AS rank
                FROM chunks_fts
                JOIN chunks ON chunks.chunk_id = chunks_fts.chunk_id
                WHERE chunks_fts MATCH ?
                  AND chunks.deleted_at IS NULL
                ORDER BY rank
                LIMIT ?
                """,
                (query, limit),
            ).fetchall()

        return [
            RetrievalCandidate(
                chunk_id=row["chunk_id"],
                score=1.0 / (1.0 + abs(float(row["rank"]))),
                source="lexical",
                score_parts={"fts": 1.0 / (1.0 + abs(float(row["rank"])))},
            )
            for row in rows
        ]

    def path_symbol_search(
        self, tokens: list[str], limit: int
    ) -> list[RetrievalCandidate]:
        normalized = [token.lower() for token in tokens if token]
        if not normalized or limit <= 0:
            return []

        scores: dict[str, dict[str, float]] = {}
        def add_token_score(chunk_id: str, token: str, score: float) -> None:
            chunk_scores = scores.setdefault(chunk_id, {})
            chunk_scores[token] = max(chunk_scores.get(token, 0.0), score)

        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT chunk_id, file_path
                FROM chunks
                WHERE deleted_at IS NULL
                """
            ).fetchall()
            for row in rows:
                path = row["file_path"].lower()
                for token in normalized:
                    if token in path:
                        add_token_score(row["chunk_id"], token, 1.0)

            token_rows = connection.execute(
                _in_query(
                    """
                SELECT chunk_tokens.chunk_id, chunk_tokens.token
                FROM chunk_tokens
                JOIN chunks ON chunks.chunk_id = chunk_tokens.chunk_id
                WHERE chunks.deleted_at IS NULL
                  AND chunk_tokens.token IN ({placeholders})
                """,
                    normalized,
                ),
                normalized,
            ).fetchall()
            for row in token_rows:
                token = row["token"].lower()
                if token in normalized:
                    add_token_score(row["chunk_id"], token, 0.25)

            symbol_rows = connection.execute(
                """
                SELECT chunk_symbols.chunk_id, symbols.name
                FROM chunk_symbols
                JOIN symbols ON symbols.symbol_id = chunk_symbols.symbol_id
                JOIN chunks ON chunks.chunk_id = chunk_symbols.chunk_id
                WHERE chunks.deleted_at IS NULL
                """
            ).fetchall()
            for row in symbol_rows:
                name = row["name"].lower()
                for token in normalized:
                    if token in name:
                        add_token_score(row["chunk_id"], token, 1.0)

        ranked = sorted(
            (
                (chunk_id, sum(token_scores.values()))
                for chunk_id, token_scores in scores.items()
                if token_scores
            ),
            key=lambda item: (-item[1], item[0]),
        )
        return [
            RetrievalCandidate(
                chunk_id=chunk_id,
                score=score,
                source="path_symbol",
                score_parts={"path_symbol": score},
            )
            for chunk_id, score in ranked[:limit]
        ]

    def direct_text_search(
        self,
        probes: list[str],
        limit: int,
    ) -> list[RetrievalCandidate]:
        normalized = _dedupe_search_probes(probes)
        if not normalized or limit <= 0:
            return []

        start = time.perf_counter()
        matches: list[RetrievalCandidate] = []

        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT chunk_id, file_path, content
                FROM chunks
                WHERE deleted_at IS NULL
                """
            ).fetchall()

        for row in rows:
            haystack = f"{row['file_path']}\n{row['content']}"
            matched = _matched_direct_text_probes(haystack, normalized)
            if not matched:
                continue
            hit_count = float(len(matched))
            score = _direct_text_score(matched, normalized)
            matches.append(
                RetrievalCandidate(
                    chunk_id=row["chunk_id"],
                    score=score,
                    source="direct_text",
                    score_parts={
                        "direct_text": score,
                        "direct_text_hits": hit_count,
                    },
                )
            )

        matches.sort(
            key=lambda item: (
                -item.score,
                -item.score_parts.get("direct_text_hits", 0.0),
                item.chunk_id,
            )
        )

        elapsed_ms = (time.perf_counter() - start) * 1000
        if elapsed_ms > 50:
            logger.warning(
                "direct_text_search slow: %.1fms for %s probes, %s chunks",
                elapsed_ms,
                len(normalized),
                len(rows),
            )

        return matches[:limit]

    def chunk_for_id(self, chunk_id: str) -> DocumentChunk:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT *
                FROM chunks
                WHERE chunk_id = ?
                  AND deleted_at IS NULL
                """,
                (chunk_id,),
            ).fetchone()
            if row is None:
                raise KeyError(chunk_id)
            return self._chunk_from_row(connection, row)

    def chunks_for_ids(self, chunk_ids: list[str]) -> dict[str, DocumentChunk]:
        chunk_ids = _dedupe_values(chunk_ids)
        if not chunk_ids:
            return {}

        with self._connect() as connection:
            rows = connection.execute(
                _in_query(
                    """
                SELECT *
                FROM chunks
                WHERE chunk_id IN ({placeholders})
                  AND deleted_at IS NULL
                """,
                    chunk_ids,
                ),
                chunk_ids,
            ).fetchall()
            chunks_by_id = self._chunks_from_rows(connection, rows)

        return {
            chunk_id: chunks_by_id[chunk_id]
            for chunk_id in chunk_ids
            if chunk_id in chunks_by_id
        }

    def chunks_for_file(self, file_path: Path, limit: int) -> list[DocumentChunk]:
        if limit <= 0:
            return []
        path = _path_key(file_path)
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM chunks
                WHERE file_path = ?
                  AND deleted_at IS NULL
                ORDER BY start_line, end_line, chunk_id
                LIMIT ?
                """,
                (path, limit),
            ).fetchall()
            chunks_by_id = self._chunks_from_rows(connection, rows)
            return [chunks_by_id[row["chunk_id"]] for row in rows]

    def chunks_in_directory(self, directory: Path, limit: int) -> list[DocumentChunk]:
        if limit <= 0:
            return []
        directory_key = directory.as_posix().strip("/")
        with self._connect() as connection:
            if directory_key in {"", "."}:
                rows = connection.execute(
                    """
                    SELECT *
                    FROM chunks
                    WHERE instr(file_path, '/') = 0
                      AND deleted_at IS NULL
                    ORDER BY file_path, start_line, end_line, chunk_id
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT *
                    FROM chunks
                    WHERE file_path LIKE ?
                      AND deleted_at IS NULL
                    ORDER BY file_path, start_line, end_line, chunk_id
                    LIMIT ?
                    """,
                    (f"{directory_key}/%", limit),
                ).fetchall()
            chunks_by_id = self._chunks_from_rows(connection, rows)
            return [chunks_by_id[row["chunk_id"]] for row in rows]

    def chunk_for_line(self, file_path: Path, line: int) -> DocumentChunk:
        path = _path_key(file_path)
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT *
                FROM chunks
                WHERE file_path = ?
                  AND start_line <= ?
                  AND end_line >= ?
                  AND deleted_at IS NULL
                ORDER BY start_line DESC, end_line ASC
                LIMIT 1
                """,
                (path, line, line),
            ).fetchone()
            if row is None:
                raise KeyError(f"{path}:{line}")
            return self._chunk_from_row(connection, row)

    def active_chunk_ids(self) -> set[str]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT chunk_id FROM chunks WHERE deleted_at IS NULL"
            ).fetchall()
        return {row["chunk_id"] for row in rows}

    def active_embedding_ids(self) -> set[str]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT embedding_id
                FROM chunks
                WHERE deleted_at IS NULL
                  AND embedding_id IS NOT NULL
                """
            ).fetchall()
        return {str(row["embedding_id"]) for row in rows}

    def active_embedding_ids_for_files(
        self,
        file_paths: set[Path],
    ) -> set[str]:
        paths = sorted({_path_key(path) for path in file_paths})
        if not paths:
            return set()
        placeholders = ", ".join("?" for _ in paths)
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT embedding_id
                FROM chunks
                WHERE file_path IN ({placeholders})
                  AND deleted_at IS NULL
                  AND embedding_id IS NOT NULL
                """,
                paths,
            ).fetchall()
        return {str(row["embedding_id"]) for row in rows}

    def language_counts(self) -> list[tuple[str, int]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT language, COUNT(*) AS count
                FROM source_files
                GROUP BY language
                ORDER BY
                  CASE
                    WHEN language IN (
                      'python', 'java', 'kotlin', 'go', 'rust', 'typescript',
                      'typescriptreact', 'javascript', 'javascriptreact', 'vue',
                      'svelte', 'c', 'cpp', 'csharp', 'swift', 'php', 'ruby',
                      'lua', 'dart'
                    ) THEN 0
                    ELSE 1
                  END,
                  count DESC,
                  language
                """
            ).fetchall()
        return [(str(row["language"]), int(row["count"])) for row in rows]

    def source_files_for_profile(self, limit: int) -> list[Path]:
        if limit <= 0:
            return []
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT source_files.path
                FROM source_files
                LEFT JOIN (
                  SELECT file_path, COUNT(*) AS active_chunks
                  FROM chunks
                  WHERE deleted_at IS NULL
                  GROUP BY file_path
                ) AS chunk_counts
                  ON chunk_counts.file_path = source_files.path
                ORDER BY
                  source_files.is_generated ASC,
                  source_files.is_test ASC,
                  CASE
                    WHEN source_files.path LIKE 'src/%'
                      OR source_files.path LIKE 'lib/%'
                      OR source_files.path LIKE 'app/%'
                      OR source_files.path LIKE 'packages/%'
                    THEN 0
                    WHEN source_files.path LIKE 'docs/%'
                      OR source_files.path LIKE 'doc/%'
                    THEN 2
                    ELSE 1
                  END,
                  CASE
                    WHEN source_files.language IN (
                      'python', 'java', 'kotlin', 'go', 'rust', 'typescript',
                      'typescriptreact', 'javascript', 'javascriptreact', 'vue',
                      'svelte', 'c', 'cpp', 'csharp', 'swift', 'php', 'ruby',
                      'lua', 'dart'
                    ) THEN 0
                    ELSE 1
                  END,
                  COALESCE(chunk_counts.active_chunks, 0) DESC,
                  source_files.path
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [Path(row["path"]) for row in rows]

    def symbol_names_for_profile(self, limit: int) -> list[str]:
        if limit <= 0:
            return []
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT symbols.name, COUNT(*) AS count
                FROM symbols
                JOIN chunk_symbols ON chunk_symbols.symbol_id = symbols.symbol_id
                JOIN chunks ON chunks.chunk_id = chunk_symbols.chunk_id
                WHERE chunks.deleted_at IS NULL
                GROUP BY symbols.name
                ORDER BY count DESC, symbols.name
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [str(row["name"]) for row in rows]

    def token_counts_for_profile(self, limit: int) -> list[str]:
        if limit <= 0:
            return []
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT chunk_tokens.token, COUNT(*) AS count
                FROM chunk_tokens
                JOIN chunks ON chunks.chunk_id = chunk_tokens.chunk_id
                WHERE chunks.deleted_at IS NULL
                GROUP BY chunk_tokens.token
                ORDER BY count DESC, chunk_tokens.token
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [str(row["token"]) for row in rows]

    def stats(self) -> dict[str, int]:
        with self._connect() as connection:
            source_files = connection.execute(
                "SELECT COUNT(*) AS count FROM source_files"
            ).fetchone()["count"]
            active_chunks = connection.execute(
                "SELECT COUNT(*) AS count FROM chunks WHERE deleted_at IS NULL"
            ).fetchone()["count"]
            deleted_chunks = connection.execute(
                "SELECT COUNT(*) AS count FROM chunks WHERE deleted_at IS NOT NULL"
            ).fetchone()["count"]
            symbols = connection.execute(
                "SELECT COUNT(*) AS count FROM symbols"
            ).fetchone()["count"]
            tokens = connection.execute(
                "SELECT COUNT(*) AS count FROM chunk_tokens"
            ).fetchone()["count"]
        return {
            "source_files": int(source_files),
            "active_chunks": int(active_chunks),
            "deleted_chunks": int(deleted_chunks),
            "symbols": int(symbols),
            "tokens": int(tokens),
        }

    def storage_page_metrics(self) -> tuple[int, int]:
        """Return read-only SQLite page and freelist counters."""
        if not self.db_path.exists():
            return (0, 0)
        with self._connect() as connection:
            page_count = int(connection.execute("PRAGMA page_count").fetchone()[0])
            freelist_count = int(
                connection.execute("PRAGMA freelist_count").fetchone()[0]
            )
        return page_count, freelist_count

    def journal_mode(self) -> str:
        """Return the current SQLite journal mode without changing it."""
        if not self.db_path.exists():
            return "UNKNOWN"
        connection = _open_connection(self.db_path, _DEFAULT_BUSY_TIMEOUT_MS)
        try:
            row = connection.execute("PRAGMA journal_mode").fetchone()
        finally:
            connection.close()
        if row is None or row[0] is None:
            return "UNKNOWN"
        return str(row[0]).upper()

    def maintenance_counts(self) -> dict[str, int]:
        if not self.db_path.exists():
            return {
                "active_chunks": 0,
                "deleted_chunks": 0,
                "active_signals": 0,
                "deleted_signals": 0,
                "active_relations": 0,
                "deleted_relations": 0,
                "active_symbols": 0,
                "orphan_symbols": 0,
                "active_associations": 0,
                "orphan_associations": 0,
            }
        connection = _open_connection(self.db_path, _DEFAULT_BUSY_TIMEOUT_MS)
        try:
            return _maintenance_counts(connection)
        finally:
            connection.close()

    def maintenance_required(self) -> bool:
        counts = self.maintenance_counts()
        return any(
            deleted > _maintenance_threshold(active)
            for active, deleted in (
                (counts["active_chunks"], counts["deleted_chunks"]),
                (counts["active_signals"], counts["deleted_signals"]),
                (counts["active_relations"], counts["deleted_relations"]),
                (counts["active_symbols"], counts["orphan_symbols"]),
                (
                    counts["active_associations"],
                    counts["orphan_associations"],
                ),
            )
        )

    def tombstone_count(self) -> int:
        if not self.db_path.exists():
            return 0
        with self._connect() as connection:
            counts = _maintenance_counts(connection)
        return sum(
            counts[key]
            for key in (
                "deleted_chunks",
                "deleted_signals",
                "deleted_relations",
                "orphan_symbols",
            )
        )

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = _open_connection(self.db_path, _DEFAULT_BUSY_TIMEOUT_MS)
        try:
            with connection:
                yield connection
        except BaseException as error:
            _raise_if_busy(error)
            raise
        finally:
            connection.close()

    def _active_chunk_ids_for_file(
        self, connection: sqlite3.Connection, path: str
    ) -> list[str]:
        rows = connection.execute(
            """
            SELECT chunk_id
            FROM chunks
            WHERE file_path = ?
              AND deleted_at IS NULL
            """,
            (path,),
        ).fetchall()
        return [row["chunk_id"] for row in rows]

    def _existing_chunk_ids(
        self,
        connection: sqlite3.Connection,
        chunk_ids: list[str],
    ) -> set[str]:
        if not chunk_ids:
            return set()
        rows = connection.execute(
            _in_query(
                "SELECT chunk_id FROM chunks "
                "WHERE chunk_id IN ({placeholders})",
                chunk_ids,
            ),
            chunk_ids,
        ).fetchall()
        return {str(row["chunk_id"]) for row in rows}

    def _delete_search_payloads(
        self, connection: sqlite3.Connection, chunk_ids: list[str]
    ) -> None:
        if not chunk_ids:
            return

        symbol_rows = connection.execute(
            _in_query(
                """
                SELECT symbol_id
                FROM chunk_symbols
                WHERE chunk_id IN ({placeholders})
                """,
                chunk_ids,
            ),
            chunk_ids,
        ).fetchall()
        symbol_ids = [row["symbol_id"] for row in symbol_rows]

        connection.execute(
            _in_query(
                "DELETE FROM chunk_symbols WHERE chunk_id IN ({placeholders})",
                chunk_ids,
            ),
            chunk_ids,
        )
        connection.execute(
            _in_query(
                "DELETE FROM chunk_tokens WHERE chunk_id IN ({placeholders})",
                chunk_ids,
            ),
            chunk_ids,
        )
        connection.execute(
            _in_query(
                "DELETE FROM chunks_fts WHERE chunk_id IN ({placeholders})",
                chunk_ids,
            ),
            chunk_ids,
        )
        if symbol_ids:
            connection.execute(
                _in_query(
                    "DELETE FROM symbols WHERE symbol_id IN ({placeholders})",
                    symbol_ids,
                ),
                symbol_ids,
            )

    def _insert_chunk(self, connection: sqlite3.Connection, chunk: DocumentChunk) -> None:
        connection.execute(
            """
            INSERT INTO chunks (
                chunk_id, file_path, start_line, end_line, content,
                chunk_type, embedding_id, deleted_at, metadata
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(chunk_id) DO UPDATE SET
                file_path = excluded.file_path,
                start_line = excluded.start_line,
                end_line = excluded.end_line,
                content = excluded.content,
                chunk_type = excluded.chunk_type,
                embedding_id = excluded.embedding_id,
                deleted_at = excluded.deleted_at,
                metadata = excluded.metadata
            """,
            (
                chunk.chunk_id,
                _path_key(chunk.file_path),
                chunk.start_line,
                chunk.end_line,
                chunk.content,
                chunk.chunk_type,
                chunk.embedding_id,
                chunk.deleted_at,
                _to_json(chunk.metadata),
            ),
        )

        for symbol in chunk.symbols:
            cursor = connection.execute(
                """
                INSERT INTO symbols (
                    name, kind, start_line, end_line, language, metadata
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    symbol.name,
                    symbol.kind,
                    symbol.start_line,
                    symbol.end_line,
                    symbol.language,
                    _to_json(symbol.metadata),
                ),
            )
            connection.execute(
                """
                INSERT INTO chunk_symbols (chunk_id, symbol_id)
                VALUES (?, ?)
                """,
                (chunk.chunk_id, cursor.lastrowid),
            )

        connection.executemany(
            """
            INSERT INTO chunk_tokens (chunk_id, token)
            VALUES (?, ?)
            """,
            [(chunk.chunk_id, token) for token in chunk.lexical_tokens],
        )
        if chunk.deleted_at is None:
            connection.execute(
                """
                INSERT INTO chunks_fts (chunk_id, file_path, content, tokens)
                VALUES (?, ?, ?, ?)
                """,
                (
                    chunk.chunk_id,
                    _path_key(chunk.file_path),
                    chunk.content,
                    " ".join(chunk.lexical_tokens),
                ),
            )

    def _chunk_from_row(
        self, connection: sqlite3.Connection, row: sqlite3.Row
    ) -> DocumentChunk:
        token_rows = connection.execute(
            """
            SELECT token
            FROM chunk_tokens
            WHERE chunk_id = ?
            ORDER BY rowid
            """,
            (row["chunk_id"],),
        ).fetchall()
        symbol_rows = connection.execute(
            """
            SELECT symbols.*
            FROM symbols
            JOIN chunk_symbols ON chunk_symbols.symbol_id = symbols.symbol_id
            WHERE chunk_symbols.chunk_id = ?
            ORDER BY symbols.start_line, symbols.end_line, symbols.name
            """,
            (row["chunk_id"],),
        ).fetchall()
        return self._decode_chunk_row(row, token_rows, symbol_rows)

    def _chunks_from_rows(
        self,
        connection: sqlite3.Connection,
        rows: list[sqlite3.Row],
    ) -> dict[str, DocumentChunk]:
        if not rows:
            return {}

        rows_by_id = {str(row["chunk_id"]): row for row in rows}
        chunk_ids = list(rows_by_id)
        token_rows = connection.execute(
            _in_query(
                """
            SELECT chunk_id, token
            FROM chunk_tokens
            WHERE chunk_id IN ({placeholders})
            ORDER BY rowid
            """,
                chunk_ids,
            ),
            chunk_ids,
        ).fetchall()
        symbol_rows = connection.execute(
            _in_query(
                """
            SELECT chunk_symbols.chunk_id, symbols.*
            FROM symbols
            JOIN chunk_symbols ON chunk_symbols.symbol_id = symbols.symbol_id
            WHERE chunk_symbols.chunk_id IN ({placeholders})
            ORDER BY chunk_symbols.chunk_id,
                     symbols.start_line,
                     symbols.end_line,
                     symbols.name
            """,
                chunk_ids,
            ),
            chunk_ids,
        ).fetchall()
        tokens_by_id: dict[str, list[sqlite3.Row]] = {
            chunk_id: [] for chunk_id in chunk_ids
        }
        symbols_by_id: dict[str, list[sqlite3.Row]] = {
            chunk_id: [] for chunk_id in chunk_ids
        }
        for token_row in token_rows:
            tokens_by_id[str(token_row["chunk_id"])].append(token_row)
        for symbol_row in symbol_rows:
            symbols_by_id[str(symbol_row["chunk_id"])].append(symbol_row)

        return {
            chunk_id: self._decode_chunk_row(
                row,
                tokens_by_id[chunk_id],
                symbols_by_id[chunk_id],
            )
            for chunk_id, row in rows_by_id.items()
        }

    def _decode_chunk_row(
        self,
        row: sqlite3.Row,
        token_rows: list[sqlite3.Row],
        symbol_rows: list[sqlite3.Row],
    ) -> DocumentChunk:
        return DocumentChunk(
            chunk_id=row["chunk_id"],
            file_path=Path(row["file_path"]),
            start_line=row["start_line"],
            end_line=row["end_line"],
            content=row["content"],
            chunk_type=row["chunk_type"],
            symbols=[
                SymbolRef(
                    name=symbol_row["name"],
                    kind=symbol_row["kind"],
                    start_line=symbol_row["start_line"],
                    end_line=symbol_row["end_line"],
                    language=symbol_row["language"],
                    metadata=_from_json(symbol_row["metadata"]),
                )
                for symbol_row in symbol_rows
            ],
            lexical_tokens=[token_row["token"] for token_row in token_rows],
            embedding_id=row["embedding_id"],
            deleted_at=row["deleted_at"],
            metadata=_from_json(row["metadata"]),
        )


class GraphReadSession:
    def __init__(self, db_path: Path, *, busy_timeout_ms: int) -> None:
        self.db_path = db_path
        self.busy_timeout_ms = busy_timeout_ms
        self._connection: sqlite3.Connection | None = None
        self._close_callbacks: list[Callable[[], None]] = []
        self.capability: GraphCapability
        self.graph_fault: str | None = None
        self.graph_truncated = False

    def __enter__(self) -> GraphReadSession:
        connection = _open_connection(self.db_path, self.busy_timeout_ms)
        try:
            connection.execute("BEGIN")
            self._connection = connection
            self._close_callbacks.clear()
            self.capability = read_graph_capability(self)
            return self
        except BaseException:
            if connection.in_transaction:
                connection.rollback()
            connection.close()
            self._connection = None
            raise

    def __exit__(self, *_exc_info: object) -> None:
        connection = self._connection
        close_error: BaseException | None = None
        try:
            while self._close_callbacks:
                try:
                    self._close_callbacks.pop()()
                except BaseException as error:
                    if close_error is None:
                        close_error = error
        finally:
            self._connection = None
            if connection is not None:
                if connection.in_transaction:
                    connection.rollback()
                connection.close()
        if close_error is not None:
            raise close_error

    def register_close_callback(self, callback: Callable[[], None]) -> None:
        self._require_connection()
        self._close_callbacks.append(callback)

    def get_metadata(self, key: str) -> str | None:
        connection = self._require_connection()
        return _metadata_value(connection, key)

    def record_graph_fault(self, reason: str) -> None:
        if self.graph_fault is None:
            self.graph_fault = reason

    def record_graph_truncation(self) -> None:
        self.graph_truncated = True

    def validate_ready_targets(self) -> bool:
        if self.capability.status != "ready" or not self.capability.structured:
            return True
        row = self._require_connection().execute(
            """
            SELECT 1
            FROM code_relations AS relations
            LEFT JOIN code_signals AS targets
              ON targets.signal_id = relations.target_signal_id
             AND targets.deleted_at IS NULL
            LEFT JOIN chunks AS target_chunks
              ON target_chunks.chunk_id = targets.chunk_id
             AND target_chunks.deleted_at IS NULL
            WHERE relations.deleted_at IS NULL
              AND relations.resolution IN ('resolved_exact', 'resolved_unique')
              AND (
                targets.signal_id IS NULL
                OR target_chunks.chunk_id IS NULL
              )
            LIMIT 1
            """
        ).fetchone()
        if row is None:
            return True
        self.record_graph_fault("dangling_target")
        return False

    def chunks_for_ids(self, chunk_ids: list[str]) -> dict[str, DocumentChunk]:
        chunk_ids = _dedupe_values(chunk_ids)
        if not chunk_ids:
            return {}
        connection = self._require_connection()
        rows = connection.execute(
            _in_query(
                """
                SELECT *
                FROM chunks
                WHERE chunk_id IN ({placeholders})
                  AND deleted_at IS NULL
                ORDER BY file_path, start_line, chunk_id
                """,
                chunk_ids,
            ),
            chunk_ids,
        ).fetchall()
        decoder = SQLiteStore(self.db_path)
        chunks_by_id = decoder._chunks_from_rows(connection, rows)
        return {
            chunk_id: chunks_by_id[chunk_id]
            for chunk_id in chunk_ids
            if chunk_id in chunks_by_id
        }

    def chunk_for_id(self, chunk_id: str) -> DocumentChunk | None:
        return self.chunks_for_ids([chunk_id]).get(chunk_id)

    def chunk_for_line(self, file_path: Path, line: int) -> DocumentChunk | None:
        row = self._require_connection().execute(
            """
            SELECT *
            FROM chunks
            WHERE file_path = ?
              AND start_line <= ?
              AND end_line >= ?
              AND deleted_at IS NULL
            ORDER BY start_line, end_line, chunk_id
            LIMIT 1
            """,
            (_path_key(file_path), line, line),
        ).fetchone()
        if row is None:
            return None
        return SQLiteStore(self.db_path)._chunk_from_row(self._require_connection(), row)

    def deleted_chunk_ids(self) -> set[str]:
        rows = self._require_connection().execute(
            "SELECT chunk_id FROM chunks WHERE deleted_at IS NOT NULL"
        ).fetchall()
        return {str(row["chunk_id"]) for row in rows}

    def source_file_for_path(self, path: Path) -> SourceFile | None:
        row = self._require_connection().execute(
            """
            SELECT *
            FROM source_files
            WHERE path = ?
            """,
            (_path_key(path),),
        ).fetchone()
        return _source_file_from_row(row) if row is not None else None

    def signal_search(self, tokens: list[str], limit: int) -> list[CodeSignal]:
        normalized = [token.lower() for token in tokens if token]
        if (
            not normalized
            or limit <= 0
            or not self.capability.signal_evidence_allowed
            or self.graph_fault is not None
        ):
            return []
        connection = self._require_connection()
        if self.capability.structured:
            legal_filter = "AND recallable = 1"
        elif _has_column(connection, "code_signals", "producer"):
            legal_filter = "AND recallable = 1 AND producer = 'legacy'"
        else:
            legal_filter = ""
        row_filter, row_filter_values = _signal_row_prefilter(normalized)
        rows = connection.execute(
            f"""
            SELECT *
            FROM code_signals
            WHERE deleted_at IS NULL
              {legal_filter}
              {row_filter}
            """,
            row_filter_values,
        ).fetchall()
        matches: list[tuple[CodeSignal, float]] = []
        for row in rows:
            signal = _signal_from_row(row)
            haystack = " ".join(
                (
                    signal.name,
                    " ".join(signal.tokens),
                    _metadata_search_text(signal.metadata),
                )
            ).lower()
            score = sum(1.0 for token in normalized if token in haystack)
            if score > 0:
                matches.append((signal, score))
        matches.sort(
            key=lambda item: (
                -item[1],
                0 if item[0].kind == "endpoint" else 1,
                item[0].start_line,
                item[0].end_line,
                item[0].kind,
                item[0].name,
                item[0].signal_id,
            )
        )
        return [signal for signal, _score in matches[:limit]]

    def signals_for_chunks(
        self,
        chunk_ids: list[str],
    ) -> dict[str, list[CodeSignal]]:
        chunk_ids = _dedupe_values(chunk_ids)
        grouped: dict[str, list[CodeSignal]] = {
            chunk_id: [] for chunk_id in chunk_ids
        }
        if (
            not chunk_ids
            or not self.capability.signal_evidence_allowed
            or self.graph_fault is not None
        ):
            return grouped
        connection = self._require_connection()
        legacy_filter = (
            "AND producer = 'legacy'"
            if not self.capability.structured
            and _has_column(connection, "code_signals", "producer")
            else ""
        )
        rows = connection.execute(
            _in_query(
                f"""
                SELECT *
                FROM code_signals
                WHERE chunk_id IN ({{placeholders}})
                  AND deleted_at IS NULL
                  {legacy_filter}
                ORDER BY chunk_id, start_line, end_line, kind, name, signal_id
                """,
                chunk_ids,
            ),
            chunk_ids,
        ).fetchall()
        for row in rows:
            grouped[str(row["chunk_id"])].append(_signal_from_row(row))
        return grouped

    def relations_for_sources(
        self,
        source_signal_ids: list[str],
    ) -> dict[str, list[CodeRelation]]:
        grouped: dict[str, list[CodeRelation]] = {}
        if (
            not self.capability.relation_evidence_allowed
            or self.graph_fault is not None
        ):
            return grouped
        for signal_id in _dedupe_values(source_signal_ids):
            relations = self.legacy_relations_for_source(
                signal_id,
                limit=EDGE_QUERY_LIMIT,
            )
            if len(relations) > MAX_EDGES_PER_SIGNAL_DIRECTION:
                self.record_graph_truncation()
                relations = relations[:MAX_EDGES_PER_SIGNAL_DIRECTION]
            if relations:
                grouped[signal_id] = relations
        return grouped

    def chunks_matching_signal_or_symbols(
        self,
        target_names: list[str],
        limit_per_target: int,
    ) -> dict[str, list[DocumentChunk]]:
        target_names = _dedupe_values(target_names)
        grouped: dict[str, list[DocumentChunk]] = {
            target_name: [] for target_name in target_names
        }
        if (
            not self.capability.relation_evidence_allowed
            or self.graph_fault is not None
            or limit_per_target <= 0
        ):
            return grouped
        connection = self._require_connection()
        decoder = SQLiteStore(self.db_path)
        rows_by_target: dict[str, list[sqlite3.Row]] = {}
        unique_rows: dict[str, sqlite3.Row] = {}
        for target_name in target_names:
            if not target_name:
                continue
            rows = _chunks_matching_name(connection, target_name, limit_per_target)
            if not rows and "." in target_name:
                owner_name, member_name = target_name.rsplit(".", 1)
                rows = _chunks_matching_member_name(
                    connection,
                    owner_name,
                    member_name,
                    limit_per_target,
                )
            rows_by_target[target_name] = rows
            unique_rows.update((row["chunk_id"], row) for row in rows)
        chunks_by_id = decoder._chunks_from_rows(
            connection,
            list(unique_rows.values()),
        )
        for target_name, rows in rows_by_target.items():
            grouped[target_name] = [
                chunks_by_id[row["chunk_id"]] for row in rows
            ]
        return grouped

    def module_for_path(self, file_path: Path) -> CodeSignal | None:
        if (
            self.graph_fault is not None
            or self.capability.status != "ready"
            or not self.capability.structured
        ):
            return None
        row = self._require_connection().execute(
            """
            SELECT *
            FROM code_signals
            WHERE kind = 'module'
              AND producer = 'core_module'
              AND qualified_name = ?
              AND deleted_at IS NULL
            ORDER BY signal_id
            LIMIT 2
            """,
            (_path_key(file_path),),
        ).fetchall()
        return _signal_from_row(row[0]) if len(row) == 1 else None

    def signal_for_id(self, signal_id: str) -> CodeSignal | None:
        if (
            self.graph_fault is not None
            or self.capability.status != "ready"
            or not self.capability.structured
        ):
            return None
        row = self._require_connection().execute(
            """
            SELECT *
            FROM code_signals
            WHERE signal_id = ?
              AND deleted_at IS NULL
            """,
            (signal_id,),
        ).fetchone()
        return _signal_from_row(row) if row is not None else None

    def signals_for_chunk(
        self,
        chunk_id: str,
        *,
        limit: int = MAX_SIGNALS_PER_FILE + 1,
    ) -> list[CodeSignal]:
        if (
            self.graph_fault is not None
            or not self.capability.signal_evidence_allowed
        ):
            return []
        connection = self._require_connection()
        legal_filter = ""
        if not self.capability.structured and _has_column(
            connection,
            "code_signals",
            "producer",
        ):
            legal_filter = "AND producer = 'legacy'"
        signal_order = (
            "file_path, start_line, start_column, end_line, end_column, signal_id"
            if self.capability.structured
            else "file_path, start_line, end_line, kind, name, signal_id"
        )
        rows = connection.execute(
            f"""
            SELECT *
            FROM code_signals
            WHERE chunk_id = ?
              AND deleted_at IS NULL
              {legal_filter}
            ORDER BY {signal_order}
            LIMIT ?
            """,
            (chunk_id, min(max(limit, 0), MAX_SIGNALS_PER_FILE + 1)),
        ).fetchall()
        return [_signal_from_row(row) for row in rows]

    def type_signals_for_file(
        self,
        file_path: Path,
        *,
        limit: int = MAX_SIGNALS_PER_FILE + 1,
    ) -> list[CodeSignal]:
        if (
            self.graph_fault is not None
            or self.capability.status != "ready"
            or not self.capability.structured
        ):
            return []
        rows = self._require_connection().execute(
            """
            SELECT *
            FROM code_signals
            WHERE file_path = ?
              AND kind = 'type'
              AND deleted_at IS NULL
            ORDER BY start_line, start_column, end_line, end_column, signal_id
            LIMIT ?
            """,
            (
                _path_key(file_path),
                min(max(limit, 0), MAX_SIGNALS_PER_FILE + 1),
            ),
        ).fetchall()
        return [_signal_from_row(row) for row in rows]

    def signals_for_chunks_with_modules(
        self,
        chunk_ids: list[str],
        *,
        limit: int = EDGE_QUERY_LIMIT,
    ) -> list[CodeSignal]:
        if (
            self.graph_fault is not None
            or self.capability.status != "ready"
            or not self.capability.structured
            or not chunk_ids
            or limit <= 0
        ):
            return []
        chunk_ids = _dedupe_values(chunk_ids)
        bounded_limit = min(limit, MAX_GRAPH_SEED_SIGNALS + 1)
        connection = self._require_connection()
        placeholders = ", ".join("?" for _ in chunk_ids)
        rows = connection.execute(
            f"""
                SELECT DISTINCT code_signals.*
                FROM code_signals
                LEFT JOIN chunks attached
                  ON attached.chunk_id IN ({placeholders})
                 AND attached.deleted_at IS NULL
                WHERE code_signals.deleted_at IS NULL
                  AND (
                    code_signals.chunk_id IN ({placeholders})
                    OR (
                      code_signals.kind = 'module'
                      AND code_signals.producer = 'core_module'
                      AND code_signals.file_path = attached.file_path
                    )
                  )
                ORDER BY code_signals.file_path, code_signals.start_line,
                         code_signals.start_column, code_signals.kind,
                         code_signals.signal_id
                LIMIT ?
                """,
            (*chunk_ids, *chunk_ids, bounded_limit),
        ).fetchall()
        return [_signal_from_row(row) for row in rows]

    def has_accepted_mybatis_statement(self, file_path: Path) -> bool:
        if (
            self.graph_fault is not None
            or self.capability.status != "ready"
            or not self.capability.structured
        ):
            return False
        row = self._require_connection().execute(
            """
            SELECT 1
            FROM code_signals
            WHERE file_path = ?
              AND kind = 'mybatis_statement'
              AND producer = 'mybatis_xml'
              AND deleted_at IS NULL
            LIMIT 1
            """,
            (_path_key(file_path),),
        ).fetchone()
        return row is not None

    def explain_projection(self, chunk: DocumentChunk) -> dict[str, object]:
        capability = self.capability
        projection: dict[str, object] = {
            "status": capability.status,
            "schema_version": capability.schema_version,
            "signals": [],
            "outgoing": [],
            "incoming": [],
            "omitted_signal_count": 0,
            "omitted_outgoing_count": 0,
            "omitted_incoming_count": 0,
        }
        if capability.status != "ready" or not capability.structured:
            return projection

        connection = self._require_connection()
        membership = """
            deleted_at IS NULL
            AND (
              chunk_id = ?
              OR (
                kind = 'module'
                AND producer = 'core_module'
                AND file_path = ?
              )
            )
        """
        parameters = (chunk.chunk_id, _path_key(chunk.file_path))
        signal_count = int(
            connection.execute(
                f"SELECT COUNT(DISTINCT signal_id) AS count "
                f"FROM code_signals WHERE {membership}",
                parameters,
            ).fetchone()["count"]
        )
        signal_rows = connection.execute(
            f"""
            SELECT *
            FROM code_signals
            WHERE {membership}
            ORDER BY start_line, end_line, kind, signal_id
            LIMIT ?
            """,
            (*parameters, MAX_EXPLAIN_SIGNALS),
        ).fetchall()
        projection["signals"] = [
            _explain_signal(_signal_from_row(row)) for row in signal_rows
        ]
        projection["omitted_signal_count"] = max(
            0,
            signal_count - MAX_EXPLAIN_SIGNALS,
        )
        if signal_count == 0:
            return projection

        member_cte = f"""
            WITH member_signals AS (
              SELECT DISTINCT signal_id
              FROM code_signals
              WHERE {membership}
            )
        """
        outgoing_count = int(
            connection.execute(
                f"""
                {member_cte}
                SELECT COUNT(DISTINCT relations.relation_id) AS count
                FROM code_relations AS relations
                JOIN member_signals
                  ON member_signals.signal_id = relations.source_signal_id
                JOIN code_signals AS sources
                  ON sources.signal_id = relations.source_signal_id
                 AND sources.deleted_at IS NULL
                WHERE relations.deleted_at IS NULL
                """,
                parameters,
            ).fetchone()["count"]
        )
        incoming_count = int(
            connection.execute(
                f"""
                {member_cte}
                SELECT COUNT(DISTINCT relations.relation_id) AS count
                FROM code_relations AS relations
                JOIN member_signals
                  ON member_signals.signal_id = relations.target_signal_id
                JOIN code_signals AS sources
                  ON sources.signal_id = relations.source_signal_id
                 AND sources.deleted_at IS NULL
                JOIN code_signals AS targets
                  ON targets.signal_id = relations.target_signal_id
                 AND targets.deleted_at IS NULL
                WHERE relations.deleted_at IS NULL
                  AND relations.resolution IN ('resolved_exact', 'resolved_unique')
                """,
                parameters,
            ).fetchone()["count"]
        )
        outgoing_rows = connection.execute(
            f"""
            {member_cte}
            SELECT relations.*, sources.name AS source_name,
                   targets.name AS target_signal_name,
                   targets.file_path AS target_path
            FROM code_relations AS relations
            JOIN member_signals
              ON member_signals.signal_id = relations.source_signal_id
            JOIN code_signals AS sources
              ON sources.signal_id = relations.source_signal_id
             AND sources.deleted_at IS NULL
            LEFT JOIN code_signals AS targets
              ON targets.signal_id = relations.target_signal_id
             AND targets.deleted_at IS NULL
            WHERE relations.deleted_at IS NULL
            ORDER BY relations.kind, relations.source_signal_id,
                     relations.target_signal_id, relations.relation_id
            LIMIT ?
            """,
            (*parameters, MAX_EXPLAIN_OUTGOING),
        ).fetchall()
        incoming_rows = connection.execute(
            f"""
            {member_cte}
            SELECT relations.*, sources.name AS source_name,
                   targets.name AS target_signal_name,
                   targets.file_path AS target_path
            FROM code_relations AS relations
            JOIN member_signals
              ON member_signals.signal_id = relations.target_signal_id
            JOIN code_signals AS sources
              ON sources.signal_id = relations.source_signal_id
             AND sources.deleted_at IS NULL
            JOIN code_signals AS targets
              ON targets.signal_id = relations.target_signal_id
             AND targets.deleted_at IS NULL
            WHERE relations.deleted_at IS NULL
              AND relations.resolution IN ('resolved_exact', 'resolved_unique')
            ORDER BY relations.kind, relations.source_signal_id,
                     relations.target_signal_id, relations.relation_id
            LIMIT ?
            """,
            (*parameters, MAX_EXPLAIN_INCOMING),
        ).fetchall()
        outgoing = [_explain_relation(row, "outgoing") for row in outgoing_rows]
        incoming = [_explain_relation(row, "incoming") for row in incoming_rows]
        projection["outgoing"] = outgoing
        projection["incoming"] = incoming
        projection["omitted_outgoing_count"] = max(
            0,
            outgoing_count - MAX_EXPLAIN_OUTGOING,
        )
        projection["omitted_incoming_count"] = max(
            0,
            incoming_count - MAX_EXPLAIN_INCOMING,
        )
        return projection

    def initial_graph_signals(
        self,
        seeds: list[tuple[str, int, int]],
        *,
        limit: int = MAX_GRAPH_SEED_SIGNALS + 1,
    ) -> list[tuple[CodeSignal, int, int]]:
        if (
            self.graph_fault is not None
            or self.capability.status != "ready"
            or not self.capability.structured
            or not seeds
            or limit <= 0
        ):
            return []
        values = ", ".join("(?, ?, ?)" for _ in seeds)
        parameters: list[object] = []
        for chunk_id, seed_rank, source_priority in seeds:
            parameters.extend((chunk_id, seed_rank, source_priority))
        rows = self._require_connection().execute(
            f"""
            WITH seed_chunks(chunk_id, seed_rank, source_priority) AS (
                VALUES {values}
            ), matching AS (
                SELECT signals.*, seed_chunks.seed_rank AS graph_seed_rank,
                       seed_chunks.source_priority AS graph_source_priority
                FROM seed_chunks
                JOIN code_signals AS signals
                  ON signals.chunk_id = seed_chunks.chunk_id
                 AND signals.deleted_at IS NULL
                JOIN chunks AS owners
                  ON owners.chunk_id = signals.chunk_id
                 AND owners.deleted_at IS NULL
                UNION ALL
                SELECT signals.*, seed_chunks.seed_rank AS graph_seed_rank,
                       seed_chunks.source_priority AS graph_source_priority
                FROM seed_chunks
                JOIN chunks AS selected
                  ON selected.chunk_id = seed_chunks.chunk_id
                 AND selected.deleted_at IS NULL
                JOIN code_signals AS signals
                  ON signals.kind = 'module'
                 AND signals.producer = 'core_module'
                 AND signals.file_path = selected.file_path
                 AND signals.deleted_at IS NULL
                JOIN chunks AS owners
                  ON owners.chunk_id = signals.chunk_id
                 AND owners.deleted_at IS NULL
            ), ordered AS (
                SELECT matching.*,
                       ROW_NUMBER() OVER (
                           PARTITION BY signal_id
                           ORDER BY graph_seed_rank, graph_source_priority
                       ) AS graph_row
                FROM matching
            )
            SELECT *
            FROM ordered
            WHERE graph_row = 1
            ORDER BY graph_seed_rank, graph_source_priority, file_path,
                     start_line, start_column, end_line, end_column, signal_id
            LIMIT ?
            """,
            (*parameters, min(limit, MAX_GRAPH_SEED_SIGNALS + 1)),
        ).fetchall()
        return [
            (
                _signal_from_row(row),
                int(row["graph_seed_rank"]),
                int(row["graph_source_priority"]),
            )
            for row in rows
        ]

    def outgoing_relations(
        self,
        source_signal_id: str,
        *,
        limit: int = EDGE_QUERY_LIMIT,
    ) -> list[CodeRelation]:
        if (
            self.graph_fault is not None
            or self.capability.status != "ready"
            or not self.capability.structured
        ):
            return []
        rows = self._require_connection().execute(
            """
            SELECT relations.*
            FROM code_relations AS relations
            LEFT JOIN code_signals AS targets
              ON targets.signal_id = relations.target_signal_id
             AND targets.deleted_at IS NULL
            WHERE relations.source_signal_id = ?
              AND relations.resolution IN ('resolved_exact', 'resolved_unique')
              AND relations.deleted_at IS NULL
            ORDER BY
              MIN(relations.producer_confidence, relations.resolution_confidence)
              * CASE relations.kind
                  WHEN 'calls' THEN 1.0
                  WHEN 'implements' THEN 0.95
                  WHEN 'implements_method' THEN 0.95
                  WHEN 'uses_type' THEN 0.75
                  WHEN 'imports' THEN 0.85
                  WHEN 'routes_to' THEN 1.0
                  WHEN 'mapped_by' THEN 0.95
                  WHEN 'tests' THEN 0.8
                  ELSE 0.0
                END DESC,
              MIN(relations.producer_confidence, relations.resolution_confidence) DESC,
              CASE relations.kind
                WHEN 'calls' THEN 0
                WHEN 'implements' THEN 1
                WHEN 'implements_method' THEN 2
                WHEN 'uses_type' THEN 3
                WHEN 'imports_type' THEN 4
                WHEN 'imports' THEN 5
                WHEN 'routes_to' THEN 6
                WHEN 'mapped_by' THEN 7
                WHEN 'tests' THEN 8
                ELSE 9
              END,
              relations.source_signal_id, relations.target_signal_id,
              COALESCE(targets.chunk_id, ''), relations.relation_id
            LIMIT ?
            """,
            (source_signal_id, min(max(limit, 0), EDGE_QUERY_LIMIT)),
        ).fetchall()
        return [_relation_from_row(row) for row in rows]

    def legacy_relations_for_source(
        self,
        source_signal_id: str,
        *,
        limit: int = EDGE_QUERY_LIMIT,
    ) -> list[CodeRelation]:
        if (
            not self.capability.relation_evidence_allowed
            or self.graph_fault is not None
        ):
            return []
        connection = self._require_connection()
        legacy_filter = (
            "AND resolution = 'legacy'"
            if _has_column(connection, "code_relations", "resolution")
            else ""
        )
        rows = connection.execute(
            f"""
            SELECT *
            FROM code_relations
            WHERE source_signal_id = ?
              AND deleted_at IS NULL
              {legacy_filter}
            ORDER BY kind, target_name, relation_id
            LIMIT ?
            """,
            (source_signal_id, min(max(limit, 0), EDGE_QUERY_LIMIT)),
        ).fetchall()
        return [
            _relation_from_row(
                row,
                v4_confidence_from_effective=True,
            )
            for row in rows
        ]

    def legacy_relations_targeting(
        self,
        target_name: str,
        *,
        limit: int = EDGE_QUERY_LIMIT,
    ) -> list[CodeRelation]:
        if (
            not self.capability.relation_evidence_allowed
            or self.graph_fault is not None
            or not target_name
        ):
            return []
        connection = self._require_connection()
        legacy_filter = (
            "AND resolution = 'legacy'"
            if _has_column(connection, "code_relations", "resolution")
            else ""
        )
        rows = connection.execute(
            f"""
            SELECT *
            FROM code_relations
            WHERE target_name = ?
              AND deleted_at IS NULL
              {legacy_filter}
            ORDER BY kind, source_signal_id, relation_id
            LIMIT ?
            """,
            (target_name, min(max(limit, 0), EDGE_QUERY_LIMIT)),
        ).fetchall()
        return [
            _relation_from_row(
                row,
                v4_confidence_from_effective=False,
            )
            for row in rows
        ]

    def incoming_relations(
        self,
        target_signal_id: str,
        *,
        limit: int = EDGE_QUERY_LIMIT,
    ) -> list[CodeRelation]:
        if (
            self.graph_fault is not None
            or self.capability.status != "ready"
            or not self.capability.structured
        ):
            return []
        rows = self._require_connection().execute(
            """
            SELECT relations.*
            FROM code_relations AS relations
            WHERE relations.target_signal_id = ?
              AND relations.resolution IN ('resolved_exact', 'resolved_unique')
              AND relations.deleted_at IS NULL
            ORDER BY
              MIN(relations.producer_confidence, relations.resolution_confidence)
              * CASE relations.kind
                  WHEN 'implements' THEN 0.95
                  WHEN 'implements_method' THEN 0.95
                  WHEN 'mapped_by' THEN 0.95
                  WHEN 'tests' THEN 0.8
                  ELSE 0.0
                END DESC,
              MIN(relations.producer_confidence, relations.resolution_confidence) DESC,
              CASE relations.kind
                WHEN 'calls' THEN 0
                WHEN 'implements' THEN 1
                WHEN 'implements_method' THEN 2
                WHEN 'uses_type' THEN 3
                WHEN 'imports_type' THEN 4
                WHEN 'imports' THEN 5
                WHEN 'routes_to' THEN 6
                WHEN 'mapped_by' THEN 7
                WHEN 'tests' THEN 8
                ELSE 9
              END,
              relations.source_signal_id, relations.target_signal_id,
              relations.source_chunk_id, relations.relation_id
            LIMIT ?
            """,
            (target_signal_id, min(max(limit, 0), EDGE_QUERY_LIMIT)),
        ).fetchall()
        return [_relation_from_row(row) for row in rows]

    def active_embedding_ids(self) -> set[str]:
        rows = self._require_connection().execute(
            """
            SELECT embedding_id
            FROM chunks
            WHERE deleted_at IS NULL
              AND embedding_id IS NOT NULL
            """
        ).fetchall()
        return {str(row["embedding_id"]) for row in rows}

    def source_chunk_counts(self) -> tuple[int, int]:
        connection = self._require_connection()
        source_count = int(
            connection.execute(
                "SELECT COUNT(*) AS count FROM source_files"
            ).fetchone()["count"]
        )
        chunk_count = int(
            connection.execute(
                """
                SELECT COUNT(*) AS count
                FROM chunks
                WHERE deleted_at IS NULL
                """
            ).fetchone()["count"]
        )
        return source_count, chunk_count

    def ready_vector_binding(self) -> ReadyVectorBinding:
        if self.capability.status != "ready" or not self.capability.structured:
            raise OperationalIntegrityError("ready vector binding is unavailable")
        connection = self._require_connection()
        binding = _read_operational_binding(connection)
        return ReadyVectorBinding(
            descriptor_schema_version=binding.vector_descriptor_schema_version,
            generation=binding.vector_generation,
            descriptor_sha256=binding.vector_descriptor_sha256,
            vector_bytes=binding.vector_bytes,
            vector_ids_bytes=binding.vector_ids_bytes,
            row_count=_metadata_int_value(
                _required_metadata(connection, _OPERATIONAL_CHUNK_COUNT_KEY)
            ),
        )

    def _require_connection(self) -> sqlite3.Connection:
        if self._connection is None:
            raise RuntimeError("graph read session is closed")
        return self._connection


class _SQLiteTestAssociationSession:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def snapshot(self) -> Any:
        from context_search_tool.test_association import TestAssociationSnapshot

        source_rows = self.connection.execute(
            "SELECT * FROM source_files ORDER BY path"
        ).fetchall()
        signal_rows = self.connection.execute(
            """
            SELECT *
            FROM code_signals
            WHERE deleted_at IS NULL
            ORDER BY project_unit_key, file_path, start_line, start_column,
                     kind, qualified_name, signature, signal_id
            """
        ).fetchall()
        relation_rows = self.connection.execute(
            """
            SELECT *
            FROM code_relations
            WHERE deleted_at IS NULL
              AND kind IN ('imports', 'imports_type')
              AND resolution IN ('resolved_exact', 'resolved_unique')
            ORDER BY source_file_path, source_signal_id, kind,
                     target_project_unit_key, target_qualified_name,
                     relation_id
            """
        ).fetchall()
        return TestAssociationSnapshot(
            source_files=tuple(
                _source_file_from_row(row) for row in source_rows
            ),
            signals=tuple(_signal_from_row(row) for row in signal_rows),
            resolved_relations=tuple(
                _relation_from_row(row) for row in relation_rows
            ),
        )

    def replace_test_associations(
        self,
        relations: tuple[CodeRelation, ...],
        *,
        producer_resolution_generation: int,
    ) -> None:
        if producer_resolution_generation < 0:
            raise ValueError("producer resolution generation must be non-negative")
        deleted_at = _now()
        self.connection.execute(
            """
            UPDATE code_relations
            SET deleted_at = ?
            WHERE producer = 'test_association'
              AND deleted_at IS NULL
            """,
            (deleted_at,),
        )
        for relation in relations:
            if relation.kind != "tests" or relation.producer != "test_association":
                raise ValueError("invalid test association relation")
            _upsert_relation_v5(self.connection, relation)
        _set_metadata_row(
            self.connection,
            TEST_ASSOCIATION_SOURCE_GENERATION_KEY,
            str(producer_resolution_generation),
            deleted_at,
        )


class _SQLiteResolutionSession:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def relations(
        self,
        *,
        association_only: bool,
    ) -> Iterator[tuple[CodeRelation, CodeSignal]]:
        association_filter = (
            "AND relations.kind = 'tests'"
            if association_only
            else "AND relations.kind <> 'tests'"
        )
        cursor = self.connection.execute(
            f"""
            SELECT relations.relation_id
            FROM code_relations relations
            JOIN code_signals sources
              ON sources.signal_id = relations.source_signal_id
             AND sources.deleted_at IS NULL
            WHERE relations.resolution <> 'legacy'
              AND relations.deleted_at IS NULL
              {association_filter}
            ORDER BY sources.project_unit_key, sources.file_path,
                     sources.start_line, sources.start_column,
                     relations.kind, relations.target_kind,
                     relations.target_qualified_name,
                     relations.target_signature,
                     COALESCE(relations.target_arity, -1),
                     relations.target_project_unit_key,
                     relations.relation_id
            """
        )
        while True:
            batch = cursor.fetchmany(128)
            if not batch:
                break
            for id_row in batch:
                relation_row = self.connection.execute(
                    "SELECT * FROM code_relations WHERE relation_id = ?",
                    (id_row["relation_id"],),
                ).fetchone()
                if relation_row is None:
                    continue
                source_row = self.connection.execute(
                    "SELECT * FROM code_signals WHERE signal_id = ?",
                    (relation_row["source_signal_id"],),
                ).fetchone()
                if source_row is not None:
                    yield (
                        _relation_from_row(relation_row),
                        _signal_from_row(source_row),
                    )

    def find_modules(
        self,
        candidates: tuple[str, ...],
        project_unit_key: str,
    ) -> tuple[CodeSignal, ...]:
        candidates = tuple(dict.fromkeys(candidates))
        if not candidates:
            return ()
        rows = self.connection.execute(
            _in_query(
                """
                SELECT *
                FROM code_signals
                WHERE qualified_name IN ({placeholders})
                  AND project_unit_key = ?
                  AND kind = 'module'
                  AND producer = 'core_module'
                  AND deleted_at IS NULL
                ORDER BY qualified_name, signal_id
                LIMIT 2
                """,
                list(candidates),
            ),
            (*candidates, project_unit_key),
        ).fetchall()
        return tuple(_signal_from_row(row) for row in rows)

    def find_signals(
        self,
        *,
        project_unit_key: str,
        kind: str,
        qualified_name: str,
        signature: str | None,
        arity: int | None,
        language: str | None,
    ) -> tuple[CodeSignal, ...]:
        clauses = [
            "project_unit_key = ?",
            "kind = ?",
            "qualified_name = ?",
            "deleted_at IS NULL",
        ]
        values: list[object] = [project_unit_key, kind, qualified_name]
        if signature is not None:
            clauses.append("signature = ?")
            values.append(signature)
        elif arity is not None:
            clauses.append("arity = ?")
            values.append(arity)
        if language:
            clauses.append("language = ?")
            values.append(language)
        rows = self.connection.execute(
            f"""
            SELECT *
            FROM code_signals
            WHERE {' AND '.join(clauses)}
            ORDER BY file_path, start_line, start_column, signal_id
            LIMIT 2
            """,
            values,
        ).fetchall()
        return tuple(_signal_from_row(row) for row in rows)

    def update_relation(self, relation: CodeRelation) -> None:
        self.connection.execute(
            """
            UPDATE code_relations
            SET target_qualified_name = ?,
                target_signal_id = ?,
                resolution = ?,
                confidence = ?,
                producer_confidence = ?,
                resolution_confidence = ?
            WHERE relation_id = ?
              AND deleted_at IS NULL
            """,
            (
                relation.target_qualified_name,
                relation.target_signal_id,
                relation.resolution,
                relation.confidence,
                relation.producer_confidence,
                relation.resolution_confidence,
                relation.relation_id,
            ),
        )


def _chunks_matching_name(
    connection: sqlite3.Connection,
    target_name: str,
    limit: int,
) -> list[sqlite3.Row]:
    legacy_filter = (
        "AND code_signals.producer = 'legacy'"
        if _has_column(connection, "code_signals", "producer")
        else ""
    )
    return connection.execute(
        f"""
        SELECT DISTINCT chunks.*
        FROM chunks
        LEFT JOIN code_signals
          ON code_signals.chunk_id = chunks.chunk_id
         AND code_signals.deleted_at IS NULL
         {legacy_filter}
        LEFT JOIN chunk_symbols
          ON chunk_symbols.chunk_id = chunks.chunk_id
        LEFT JOIN symbols
          ON symbols.symbol_id = chunk_symbols.symbol_id
        WHERE chunks.deleted_at IS NULL
          AND (
            code_signals.name = ?
            OR symbols.name = ?
          )
        ORDER BY chunks.file_path, chunks.start_line, chunks.chunk_id
        LIMIT ?
        """,
        (target_name, target_name, limit),
    ).fetchall()


def _chunks_matching_member_name(
    connection: sqlite3.Connection,
    owner_name: str,
    member_name: str,
    limit: int,
) -> list[sqlite3.Row]:
    owner_variants = [owner_name, f"{owner_name}Impl"]
    signal_names = [f"{owner}.{member_name}" for owner in owner_variants]
    path_patterns = [f"%{owner}.java" for owner in owner_variants]
    legacy_filter = (
        "AND code_signals.producer = 'legacy'"
        if _has_column(connection, "code_signals", "producer")
        else ""
    )
    return connection.execute(
        _in_query(
            f"""
        SELECT DISTINCT chunks.*
        FROM chunks
        LEFT JOIN code_signals
          ON code_signals.chunk_id = chunks.chunk_id
         AND code_signals.deleted_at IS NULL
         {legacy_filter}
        LEFT JOIN chunk_symbols
          ON chunk_symbols.chunk_id = chunks.chunk_id
        LEFT JOIN symbols
          ON symbols.symbol_id = chunk_symbols.symbol_id
        WHERE chunks.deleted_at IS NULL
          AND (
            code_signals.name IN ({{placeholders}})
            OR (
              symbols.name = ?
              AND (
                chunks.file_path LIKE ?
                OR chunks.file_path LIKE ?
              )
            )
          )
        ORDER BY chunks.file_path, chunks.start_line, chunks.chunk_id
        LIMIT ?
        """,
            signal_names,
        ),
        (*signal_names, member_name, *path_patterns, limit),
    ).fetchall()


def operational_content_fingerprint(
    sources: tuple[OperationalSourceObservation, ...],
) -> str:
    rows = []
    seen: set[str] = set()
    for item in sorted(sources, key=lambda value: _path_key(value.path)):
        _validate_source_observation(item)
        path = _operational_path(item.path)
        if path in seen:
            raise ValueError("duplicate operational source path")
        seen.add(path)
        rows.append(
            {
                "path": path,
                "language": item.language,
                "sha256": item.sha256,
            }
        )
    return _sha256_canonical({"sources": rows})


def operational_observation_fingerprint(
    sources: tuple[OperationalSourceObservation, ...],
    skips: tuple[OperationalScanSkip, ...],
    controls: tuple[OperationalControlObservation, ...] = (),
) -> str:
    source_rows = []
    seen: set[str] = set()
    for item in sorted(sources, key=lambda value: _path_key(value.path)):
        _validate_source_observation(item)
        path = _operational_path(item.path)
        if path in seen:
            raise ValueError("duplicate operational observation path")
        seen.add(path)
        source_rows.append(
            {
                "path": path,
                "language": item.language,
                "size": item.size,
                "mtime_ns": item.mtime_ns,
                "change_token": item.change_token,
                "change_token_kind": item.change_token_kind,
            }
        )
    skip_rows = []
    for item in sorted(skips, key=lambda value: _path_key(value.path)):
        normalized = _validate_scan_skip(item)
        path = _operational_path(normalized.path)
        if path in seen:
            raise ValueError("duplicate operational observation path")
        seen.add(path)
        skip_rows.append(
            {
                "path": path,
                "reason": normalized.reason,
                "language": normalized.language,
                "size": normalized.size,
                "mtime_ns": normalized.mtime_ns,
                "change_token": normalized.change_token,
                "change_token_kind": normalized.change_token_kind,
                "retryable": normalized.retryable,
                "metadata": dict(normalized.metadata),
            }
        )
    control_rows = []
    for item in _validate_control_observations(
        controls,
        controls[0].observation_generation if controls else 0,
    ):
        path = _operational_path(item.path)
        control_rows.append(
            {
                "path": path,
                "sha256": item.sha256,
                "size": item.size,
                "mtime_ns": item.mtime_ns,
                "change_token": item.change_token,
                "change_token_kind": item.change_token_kind,
            }
        )
    return _sha256_canonical(
        {
            "sources": source_rows,
            "scan_skips": skip_rows,
            "controls": control_rows,
        }
    )


def _operational_schema_v1_statements() -> tuple[str, ...]:
    return (
        """
        CREATE TABLE IF NOT EXISTS scan_skips (
            path TEXT PRIMARY KEY,
            reason TEXT NOT NULL CHECK (
                reason IN (
                    'too_large', 'binary', 'unreadable', 'unsafe_path',
                    'changed_during_read', 'unsupported_encoding'
                )
            ),
            language TEXT,
            size INTEGER,
            mtime_ns INTEGER,
            change_token TEXT,
            change_token_kind TEXT NOT NULL,
            retryable INTEGER NOT NULL CHECK (retryable IN (0, 1)),
            metadata TEXT NOT NULL,
            first_observation_generation INTEGER NOT NULL,
            last_observation_generation INTEGER NOT NULL,
            last_retry_generation INTEGER
        )
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_scan_skips_retry
        ON scan_skips(retryable, last_retry_generation, path)
        """,
        """
        CREATE TABLE IF NOT EXISTS operational_controls (
            path TEXT PRIMARY KEY,
            sha256 TEXT NOT NULL,
            size INTEGER NOT NULL,
            mtime_ns INTEGER NOT NULL,
            change_token TEXT,
            change_token_kind TEXT NOT NULL,
            observation_generation INTEGER NOT NULL
        )
        """,
    )


def _add_column_if_missing(
    connection: sqlite3.Connection,
    table: str,
    column: str,
    declaration: str,
) -> None:
    if not re.fullmatch(r"[a-z_]+", table) or not re.fullmatch(
        r"[a-z_]+", column
    ):
        raise ValueError("invalid operational schema identifier")
    if not _has_column(connection, table, column):
        connection.execute(
            f"ALTER TABLE {table} ADD COLUMN {column} {declaration}"
        )


def _require_operational_schema_v1(connection: sqlite3.Connection) -> None:
    required_source_columns = {
        "path",
        "language",
        "sha256",
        "size",
        "mtime_ns",
        "change_token",
        "change_token_kind",
        "observation_generation",
    }
    required_skip_columns = {
        "path",
        "reason",
        "language",
        "size",
        "mtime_ns",
        "change_token",
        "change_token_kind",
        "retryable",
        "metadata",
        "first_observation_generation",
        "last_observation_generation",
        "last_retry_generation",
    }
    required_control_columns = {
        "path",
        "sha256",
        "size",
        "mtime_ns",
        "change_token",
        "change_token_kind",
        "observation_generation",
    }
    if (
        not _table_exists(connection, "source_files")
        or not _table_exists(connection, "scan_skips")
        or not _table_exists(connection, "operational_controls")
        or not required_source_columns <= _table_columns(connection, "source_files")
        or not required_skip_columns <= _table_columns(connection, "scan_skips")
        or not required_control_columns
        <= _table_columns(connection, "operational_controls")
    ):
        raise OperationalIntegrityError("operational schema v1 is incomplete")


def _validate_source_observations(
    sources: tuple[OperationalSourceObservation, ...],
    generation: int,
) -> tuple[OperationalSourceObservation, ...]:
    if not isinstance(sources, tuple):
        raise ValueError("source observations must be an immutable tuple")
    normalized = tuple(sorted(sources, key=lambda item: _path_key(item.path)))
    seen: set[str] = set()
    for item in normalized:
        _validate_source_observation(item)
        path = _operational_path(item.path)
        if path in seen:
            raise ValueError("duplicate operational source path")
        if item.observation_generation != generation:
            raise ValueError("source observation generation mismatch")
        seen.add(path)
    return normalized


def _validate_source_observation(item: OperationalSourceObservation) -> None:
    if not isinstance(item, OperationalSourceObservation):
        raise ValueError("invalid source observation")
    _operational_path(item.path)
    if not item.language or not _SHA256_RE.fullmatch(item.sha256):
        raise ValueError("invalid source observation identity")
    for value in (item.size, item.mtime_ns, item.observation_generation):
        if type(value) is not int or value < 0:
            raise ValueError("invalid source observation metadata")
    _validate_change_token(item.change_token, item.change_token_kind)


def _validate_control_observations(
    controls: tuple[OperationalControlObservation, ...],
    generation: int,
) -> tuple[OperationalControlObservation, ...]:
    if not isinstance(controls, tuple):
        raise ValueError("control observations must be an immutable tuple")
    normalized = tuple(sorted(controls, key=lambda item: _path_key(item.path)))
    seen: set[str] = set()
    for item in normalized:
        if not isinstance(item, OperationalControlObservation):
            raise ValueError("invalid control observation")
        path = _operational_path(item.path)
        if path in seen:
            raise ValueError("duplicate operational control path")
        if not _SHA256_RE.fullmatch(item.sha256):
            raise ValueError("invalid control observation identity")
        for value in (item.size, item.mtime_ns, item.observation_generation):
            if type(value) is not int or value < 0:
                raise ValueError("invalid control observation metadata")
        if item.observation_generation != generation:
            raise ValueError("control observation generation mismatch")
        _validate_change_token(item.change_token, item.change_token_kind)
        seen.add(path)
    return normalized


def _validate_scan_skips(
    skips: tuple[OperationalScanSkip, ...],
    generation: int,
) -> tuple[OperationalScanSkip, ...]:
    if not isinstance(skips, tuple):
        raise ValueError("scan skips must be an immutable tuple")
    normalized = tuple(
        _validate_scan_skip(item)
        for item in sorted(skips, key=lambda value: _path_key(value.path))
    )
    seen: set[str] = set()
    for item in normalized:
        path = _operational_path(item.path)
        if path in seen:
            raise ValueError("duplicate scan-skip path")
        if item.last_observation_generation != generation:
            raise ValueError("scan-skip observation generation mismatch")
        seen.add(path)
    return normalized


def _validate_scan_skip(item: OperationalScanSkip) -> OperationalScanSkip:
    if not isinstance(item, OperationalScanSkip):
        raise ValueError("invalid scan skip")
    _operational_path(item.path)
    if item.reason not in _SCAN_SKIP_REASONS:
        raise ValueError("invalid scan-skip reason")
    if item.language is not None and not item.language:
        raise ValueError("invalid scan-skip language")
    for value in (item.size, item.mtime_ns, item.last_retry_generation):
        if value is not None and (type(value) is not int or value < 0):
            raise ValueError("invalid scan-skip metadata")
    for value in (
        item.first_observation_generation,
        item.last_observation_generation,
    ):
        if type(value) is not int or value < 0:
            raise ValueError("invalid scan-skip generation")
    if item.first_observation_generation > item.last_observation_generation:
        raise ValueError("invalid scan-skip generation range")
    if type(item.retryable) is not bool:
        raise ValueError("invalid scan-skip retryability")
    _validate_change_token(item.change_token, item.change_token_kind)
    metadata = _normalize_skip_metadata(item.metadata)
    return OperationalScanSkip(
        path=item.path,
        reason=item.reason,
        language=item.language,
        size=item.size,
        mtime_ns=item.mtime_ns,
        change_token=item.change_token,
        change_token_kind=item.change_token_kind,
        retryable=item.retryable,
        first_observation_generation=item.first_observation_generation,
        last_observation_generation=item.last_observation_generation,
        last_retry_generation=item.last_retry_generation,
        metadata=metadata,
    )


def _normalize_skip_metadata(
    metadata: tuple[tuple[str, str], ...],
) -> tuple[tuple[str, str], ...]:
    if not isinstance(metadata, tuple) or len(metadata) > 16:
        raise ValueError("invalid scan-skip metadata")
    normalized: dict[str, str] = {}
    for item in metadata:
        if not isinstance(item, tuple) or len(item) != 2:
            raise ValueError("invalid scan-skip metadata")
        key, value = item
        if (
            not isinstance(key, str)
            or not key
            or len(key) > 64
            or not isinstance(value, str)
            or len(value) > 128
            or key in normalized
        ):
            raise ValueError("invalid scan-skip metadata")
        normalized[key] = value
    return tuple(sorted(normalized.items()))


def _validate_change_token(token: object, kind: str) -> None:
    if kind not in _CHANGE_TOKEN_KINDS:
        raise ValueError("invalid change-token kind")
    if token is not None and type(token) not in {int, str}:
        raise ValueError("invalid change token")


def _encode_change_token(token: int | str | None) -> str | None:
    if token is None:
        return None
    return _canonical_json(token)


def _decode_change_token(raw: object) -> int | str | None:
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise OperationalIntegrityError("invalid persisted change token")
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as error:
        raise OperationalIntegrityError("invalid persisted change token") from error
    if value is not None and type(value) not in {int, str}:
        raise OperationalIntegrityError("invalid persisted change token")
    return value


def _read_operational_observations(
    connection: sqlite3.Connection,
) -> tuple[
    tuple[OperationalSourceObservation, ...],
    tuple[OperationalScanSkip, ...],
    tuple[OperationalControlObservation, ...],
]:
    source_rows = connection.execute(
        """
        SELECT path, language, sha256, size, mtime_ns, change_token,
               change_token_kind, observation_generation
        FROM source_files
        ORDER BY path
        """
    ).fetchall()
    skip_rows = connection.execute(
        """
        SELECT path, reason, language, size, mtime_ns, change_token,
               change_token_kind, retryable, metadata,
               first_observation_generation, last_observation_generation,
               last_retry_generation
        FROM scan_skips
        ORDER BY path
        """
    ).fetchall()
    control_rows = connection.execute(
        """
        SELECT path, sha256, size, mtime_ns, change_token,
               change_token_kind, observation_generation
        FROM operational_controls
        ORDER BY path
        """
    ).fetchall()
    try:
        sources = tuple(_source_observation_from_row(row) for row in source_rows)
        skips = tuple(_scan_skip_from_row(row) for row in skip_rows)
        controls = tuple(
            _control_observation_from_row(row) for row in control_rows
        )
        generation = (
            sources[0].observation_generation
            if sources
            else controls[0].observation_generation
            if controls
            else None
        )
        if generation is not None:
            _validate_source_observations(sources, generation)
            _validate_control_observations(controls, generation)
        for item in skips:
            _validate_scan_skip(item)
    except (TypeError, ValueError) as error:
        if isinstance(error, OperationalIntegrityError):
            raise
        raise OperationalIntegrityError("invalid operational observations") from error
    return sources, skips, controls


def _source_observation_from_row(row: sqlite3.Row) -> OperationalSourceObservation:
    return OperationalSourceObservation(
        path=Path(str(row["path"])),
        language=str(row["language"]),
        sha256=str(row["sha256"]),
        size=_row_int(row, "size"),
        mtime_ns=_row_int(row, "mtime_ns"),
        change_token=_decode_change_token(row["change_token"]),
        change_token_kind=str(row["change_token_kind"]),
        observation_generation=_row_int(row, "observation_generation"),
    )


def _control_observation_from_row(
    row: sqlite3.Row,
) -> OperationalControlObservation:
    return OperationalControlObservation(
        path=Path(str(row["path"])),
        sha256=str(row["sha256"]),
        size=_row_int(row, "size"),
        mtime_ns=_row_int(row, "mtime_ns"),
        change_token=_decode_change_token(row["change_token"]),
        change_token_kind=str(row["change_token_kind"]),
        observation_generation=_row_int(row, "observation_generation"),
    )


def _scan_skip_from_row(
    row: sqlite3.Row,
    *,
    retry_generation: int | None = None,
) -> OperationalScanSkip:
    try:
        metadata_raw = json.loads(str(row["metadata"]))
    except json.JSONDecodeError as error:
        raise OperationalIntegrityError("invalid scan-skip metadata") from error
    if not isinstance(metadata_raw, dict) or not all(
        isinstance(key, str) and isinstance(value, str)
        for key, value in metadata_raw.items()
    ):
        raise OperationalIntegrityError("invalid scan-skip metadata")
    return _validate_scan_skip(
        OperationalScanSkip(
            path=Path(str(row["path"])),
            reason=str(row["reason"]),
            language=(str(row["language"]) if row["language"] is not None else None),
            size=_optional_row_int(row, "size"),
            mtime_ns=_optional_row_int(row, "mtime_ns"),
            change_token=_decode_change_token(row["change_token"]),
            change_token_kind=str(row["change_token_kind"]),
            retryable=_row_bool(row, "retryable"),
            first_observation_generation=_row_int(
                row, "first_observation_generation"
            ),
            last_observation_generation=_row_int(
                row, "last_observation_generation"
            ),
            last_retry_generation=(
                retry_generation
                if retry_generation is not None
                else _optional_row_int(row, "last_retry_generation")
            ),
            metadata=tuple(sorted(metadata_raw.items())),
        )
    )


def _row_int(row: sqlite3.Row, key: str) -> int:
    value = row[key]
    if type(value) is not int:
        raise OperationalIntegrityError(f"invalid operational integer: {key}")
    return value


def _optional_row_int(row: sqlite3.Row, key: str) -> int | None:
    return None if row[key] is None else _row_int(row, key)


def _row_bool(row: sqlite3.Row, key: str) -> bool:
    value = _row_int(row, key)
    if value not in {0, 1}:
        raise OperationalIntegrityError(f"invalid operational boolean: {key}")
    return bool(value)


def _validate_bound_operational_observations(
    binding: OperationalReadyBinding,
    sources: tuple[OperationalSourceObservation, ...],
    skips: tuple[OperationalScanSkip, ...],
    controls: tuple[OperationalControlObservation, ...],
) -> None:
    if any(
        item.observation_generation != binding.observation_generation
        for item in sources
    ) or any(
        item.last_observation_generation != binding.observation_generation
        for item in skips
    ) or any(
        item.observation_generation != binding.observation_generation
        for item in controls
    ):
        raise OperationalIntegrityError("observation generation mismatch")
    try:
        content_fingerprint = operational_content_fingerprint(sources)
        observation_fingerprint = operational_observation_fingerprint(
            sources,
            skips,
            controls,
        )
    except ValueError as error:
        raise OperationalIntegrityError(
            "invalid bound operational observations"
        ) from error
    if content_fingerprint != binding.source_content_fingerprint:
        raise OperationalIntegrityError("source content fingerprint mismatch")
    if observation_fingerprint != binding.source_observation_fingerprint:
        raise OperationalIntegrityError("source observation fingerprint mismatch")


def _validate_operational_binding(
    binding: OperationalReadyBinding,
) -> OperationalReadyBinding:
    if not isinstance(binding, OperationalReadyBinding):
        raise ValueError("invalid operational ready binding")
    for value in (
        binding.index_config_hash,
        binding.source_content_fingerprint,
        binding.source_observation_fingerprint,
        binding.manifest_sha256,
        binding.vector_descriptor_sha256,
    ):
        if not _SHA256_RE.fullmatch(value):
            raise ValueError("invalid operational binding digest")
    if binding.manifest_schema_version != 2:
        raise ValueError("invalid bound manifest schema")
    if binding.vector_descriptor_schema_version != 2:
        raise ValueError("invalid bound vector descriptor schema")
    if not _GENERATION_RE.fullmatch(binding.manifest_generation):
        raise ValueError("invalid bound manifest generation")
    if not _GENERATION_RE.fullmatch(binding.vector_generation):
        raise ValueError("invalid bound vector generation")
    for value in (
        binding.observation_generation,
        binding.vector_bytes,
        binding.vector_ids_bytes,
        binding.indexed_at_epoch_s,
    ):
        if type(value) is not int or value < 0:
            raise ValueError("invalid operational binding count")
    if binding.operation_mode not in _OPERATION_MODES:
        raise ValueError("invalid operational operation mode")
    return OperationalReadyBinding(
        **{
            **binding.__dict__,
            "work_metrics": _normalize_work_metrics(binding.work_metrics),
        }
    )


def _normalize_work_metrics(
    metrics: tuple[tuple[str, int | str], ...],
) -> tuple[tuple[str, int | str], ...]:
    if not isinstance(metrics, tuple) or len(metrics) > _MAX_WORK_METRICS:
        raise ValueError("invalid operational work metrics")
    normalized: dict[str, int | str] = {}
    for item in metrics:
        if not isinstance(item, tuple) or len(item) != 2:
            raise ValueError("invalid operational work metrics")
        key, value = item
        if (
            not isinstance(key, str)
            or len(key) > 128
            or not _WORK_METRIC_RE.fullmatch(key)
            or key in normalized
        ):
            raise ValueError("invalid operational work metrics")
        if type(value) is int:
            if value < 0:
                raise ValueError("invalid operational work metrics")
        elif (
            not isinstance(value, str)
            or value not in _WORK_STRING_METRICS.get(key, frozenset())
        ):
            raise ValueError("invalid operational work metrics")
        normalized[key] = value
    return tuple(sorted(normalized.items()))


_OPERATIONAL_BINDING_KEYS = (
    _OPERATIONAL_INDEX_CONFIG_HASH_KEY,
    _OPERATIONAL_CONTENT_FINGERPRINT_KEY,
    _OPERATIONAL_OBSERVATION_FINGERPRINT_KEY,
    _OPERATIONAL_OBSERVATION_GENERATION_KEY,
    _OPERATIONAL_MANIFEST_SCHEMA_KEY,
    _OPERATIONAL_MANIFEST_GENERATION_KEY,
    _OPERATIONAL_MANIFEST_SHA256_KEY,
    _OPERATIONAL_DESCRIPTOR_SCHEMA_KEY,
    _OPERATIONAL_VECTOR_GENERATION_KEY,
    _OPERATIONAL_DESCRIPTOR_SHA256_KEY,
    _OPERATIONAL_VECTOR_BYTES_KEY,
    _OPERATIONAL_VECTOR_IDS_BYTES_KEY,
    _OPERATIONAL_INDEXED_AT_KEY,
    _OPERATIONAL_MODE_KEY,
    _OPERATIONAL_WORK_METRICS_KEY,
)


def _write_operational_binding(
    connection: sqlite3.Connection,
    binding: OperationalReadyBinding,
    *,
    source_count: int,
    chunk_count: int,
    embedding_ids: tuple[str, ...],
    now: int,
) -> None:
    values = {
        _OPERATIONAL_INDEX_CONFIG_HASH_KEY: binding.index_config_hash,
        _OPERATIONAL_CONTENT_FINGERPRINT_KEY: binding.source_content_fingerprint,
        _OPERATIONAL_OBSERVATION_FINGERPRINT_KEY: (
            binding.source_observation_fingerprint
        ),
        _OPERATIONAL_OBSERVATION_GENERATION_KEY: str(
            binding.observation_generation
        ),
        _OPERATIONAL_MANIFEST_SCHEMA_KEY: str(binding.manifest_schema_version),
        _OPERATIONAL_MANIFEST_GENERATION_KEY: binding.manifest_generation,
        _OPERATIONAL_MANIFEST_SHA256_KEY: binding.manifest_sha256,
        _OPERATIONAL_DESCRIPTOR_SCHEMA_KEY: str(
            binding.vector_descriptor_schema_version
        ),
        _OPERATIONAL_VECTOR_GENERATION_KEY: binding.vector_generation,
        _OPERATIONAL_DESCRIPTOR_SHA256_KEY: binding.vector_descriptor_sha256,
        _OPERATIONAL_VECTOR_BYTES_KEY: str(binding.vector_bytes),
        _OPERATIONAL_VECTOR_IDS_BYTES_KEY: str(binding.vector_ids_bytes),
        _OPERATIONAL_INDEXED_AT_KEY: str(binding.indexed_at_epoch_s),
        _OPERATIONAL_MODE_KEY: binding.operation_mode,
        _OPERATIONAL_WORK_METRICS_KEY: _canonical_json(dict(binding.work_metrics)),
        _OPERATIONAL_SOURCE_COUNT_KEY: str(source_count),
        _OPERATIONAL_CHUNK_COUNT_KEY: str(chunk_count),
        _OPERATIONAL_EMBEDDING_IDS_SHA256_KEY: _embedding_ids_digest(embedding_ids),
    }
    for key, value in values.items():
        _set_metadata_row(connection, key, value, now)


def _read_operational_binding(
    connection: sqlite3.Connection,
) -> OperationalReadyBinding:
    values = {
        key: _required_metadata(connection, key) for key in _OPERATIONAL_BINDING_KEYS
    }
    try:
        raw_metrics = json.loads(values[_OPERATIONAL_WORK_METRICS_KEY])
    except json.JSONDecodeError as error:
        raise OperationalIntegrityError("invalid operational work metrics") from error
    if not isinstance(raw_metrics, dict):
        raise OperationalIntegrityError("invalid operational work metrics")
    try:
        binding = OperationalReadyBinding(
            index_config_hash=values[_OPERATIONAL_INDEX_CONFIG_HASH_KEY],
            source_content_fingerprint=values[_OPERATIONAL_CONTENT_FINGERPRINT_KEY],
            source_observation_fingerprint=values[
                _OPERATIONAL_OBSERVATION_FINGERPRINT_KEY
            ],
            observation_generation=_metadata_int_value(
                values[_OPERATIONAL_OBSERVATION_GENERATION_KEY]
            ),
            manifest_schema_version=_metadata_int_value(
                values[_OPERATIONAL_MANIFEST_SCHEMA_KEY]
            ),
            manifest_generation=values[_OPERATIONAL_MANIFEST_GENERATION_KEY],
            manifest_sha256=values[_OPERATIONAL_MANIFEST_SHA256_KEY],
            vector_descriptor_schema_version=_metadata_int_value(
                values[_OPERATIONAL_DESCRIPTOR_SCHEMA_KEY]
            ),
            vector_generation=values[_OPERATIONAL_VECTOR_GENERATION_KEY],
            vector_descriptor_sha256=values[_OPERATIONAL_DESCRIPTOR_SHA256_KEY],
            vector_bytes=_metadata_int_value(values[_OPERATIONAL_VECTOR_BYTES_KEY]),
            vector_ids_bytes=_metadata_int_value(
                values[_OPERATIONAL_VECTOR_IDS_BYTES_KEY]
            ),
            indexed_at_epoch_s=_metadata_int_value(
                values[_OPERATIONAL_INDEXED_AT_KEY]
            ),
            operation_mode=values[_OPERATIONAL_MODE_KEY],
            work_metrics=tuple(raw_metrics.items()),
        )
        return _validate_operational_binding(binding)
    except (TypeError, ValueError) as error:
        if isinstance(error, OperationalIntegrityError):
            raise
        raise OperationalIntegrityError("invalid operational ready binding") from error


def _validate_bound_counts(
    connection: sqlite3.Connection,
    *,
    source_count: int,
    chunk_count: int,
    embedding_ids: tuple[str, ...],
) -> None:
    if _metadata_int_value(
        _required_metadata(connection, _OPERATIONAL_SOURCE_COUNT_KEY)
    ) != source_count:
        raise OperationalIntegrityError("bound source count mismatch")
    if _metadata_int_value(
        _required_metadata(connection, _OPERATIONAL_CHUNK_COUNT_KEY)
    ) != chunk_count:
        raise OperationalIntegrityError("bound chunk count mismatch")
    if _required_metadata(
        connection, _OPERATIONAL_EMBEDDING_IDS_SHA256_KEY
    ) != _embedding_ids_digest(embedding_ids):
        raise OperationalIntegrityError("bound embedding IDs mismatch")


def _required_metadata(connection: sqlite3.Connection, key: str) -> str:
    value = _metadata_value(connection, key)
    if value is None or value == "":
        raise OperationalIntegrityError(f"missing operational binding: {key}")
    return value


def _metadata_int_value(raw: str) -> int:
    try:
        value = int(raw)
    except ValueError as error:
        raise OperationalIntegrityError("invalid operational integer") from error
    if value < 0 or str(value) != raw:
        raise OperationalIntegrityError("invalid operational integer")
    return value


def _embedding_ids_digest(ids: tuple[str, ...]) -> str:
    return _sha256_canonical(list(ids))


def _operational_path(path: Path) -> str:
    if not isinstance(path, Path):
        raise ValueError("operational path must be a Path")
    rendered = path.as_posix()
    if (
        path.is_absolute()
        or rendered in {"", "."}
        or ".." in path.parts
        or "\\" in rendered
    ):
        raise ValueError("operational path must be repository-relative POSIX")
    return rendered


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _sha256_canonical(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _common_schema_statements() -> tuple[str, ...]:
    return (
        """
        CREATE TABLE IF NOT EXISTS source_files (
            path TEXT PRIMARY KEY,
            language TEXT NOT NULL,
            sha256 TEXT NOT NULL,
            size INTEGER NOT NULL,
            mtime_ns INTEGER NOT NULL,
            is_generated INTEGER NOT NULL,
            is_test INTEGER NOT NULL,
            metadata TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS chunks (
            chunk_id TEXT PRIMARY KEY,
            file_path TEXT NOT NULL,
            start_line INTEGER NOT NULL,
            end_line INTEGER NOT NULL,
            content TEXT NOT NULL,
            chunk_type TEXT NOT NULL,
            embedding_id TEXT,
            deleted_at INTEGER,
            metadata TEXT NOT NULL
        )
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_chunks_file_active
        ON chunks(file_path, deleted_at)
        """,
        """
        CREATE TABLE IF NOT EXISTS symbols (
            symbol_id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            kind TEXT NOT NULL,
            start_line INTEGER NOT NULL,
            end_line INTEGER NOT NULL,
            language TEXT NOT NULL,
            metadata TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS chunk_symbols (
            chunk_id TEXT NOT NULL,
            symbol_id INTEGER NOT NULL,
            PRIMARY KEY (chunk_id, symbol_id),
            FOREIGN KEY (chunk_id) REFERENCES chunks(chunk_id),
            FOREIGN KEY (symbol_id) REFERENCES symbols(symbol_id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS chunk_tokens (
            chunk_id TEXT NOT NULL,
            token TEXT NOT NULL,
            FOREIGN KEY (chunk_id) REFERENCES chunks(chunk_id)
        )
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_chunk_tokens_token
        ON chunk_tokens(token)
        """,
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts
        USING fts5(chunk_id UNINDEXED, file_path, content, tokens)
        """,
        """
        CREATE TABLE IF NOT EXISTS index_metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at INTEGER NOT NULL
        )
        """,
    )


def _v4_graph_schema_statements() -> tuple[str, ...]:
    return (
        """
        CREATE TABLE IF NOT EXISTS code_signals (
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
        )
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_code_signals_chunk_active
        ON code_signals(chunk_id, deleted_at)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_code_signals_file_active
        ON code_signals(file_path, deleted_at)
        """,
        """
        CREATE TABLE IF NOT EXISTS code_relations (
            relation_id TEXT PRIMARY KEY,
            source_signal_id TEXT NOT NULL,
            source_chunk_id TEXT NOT NULL,
            source_file_path TEXT NOT NULL,
            target_name TEXT NOT NULL,
            kind TEXT NOT NULL,
            confidence REAL NOT NULL,
            metadata TEXT NOT NULL,
            deleted_at INTEGER
        )
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_code_relations_source_active
        ON code_relations(source_signal_id, deleted_at)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_code_relations_target_active
        ON code_relations(target_name, deleted_at)
        """,
    )


def _v5_schema_statements() -> tuple[str, ...]:
    return (
        """
        CREATE TABLE code_signals (
            signal_id TEXT PRIMARY KEY,
            chunk_id TEXT NOT NULL,
            file_path TEXT NOT NULL,
            kind TEXT NOT NULL,
            name TEXT NOT NULL,
            qualified_name TEXT NOT NULL,
            signature TEXT NOT NULL,
            arity INTEGER,
            project_unit_key TEXT NOT NULL,
            producer TEXT NOT NULL,
            start_line INTEGER NOT NULL,
            end_line INTEGER NOT NULL,
            start_column INTEGER NOT NULL,
            end_column INTEGER NOT NULL,
            language TEXT NOT NULL,
            recallable INTEGER NOT NULL,
            tokens TEXT NOT NULL,
            metadata TEXT NOT NULL,
            deleted_at INTEGER
        )
        """,
        """
        CREATE INDEX idx_code_signals_chunk_active
        ON code_signals(chunk_id, deleted_at)
        """,
        """
        CREATE INDEX idx_code_signals_file_active
        ON code_signals(file_path, deleted_at)
        """,
        """
        CREATE INDEX idx_code_signals_selector_active
        ON code_signals(
            project_unit_key, language, kind, qualified_name, deleted_at
        )
        """,
        """
        CREATE INDEX idx_code_signals_arity_active
        ON code_signals(
            project_unit_key, language, kind, qualified_name, arity, deleted_at
        )
        """,
        """
        CREATE INDEX idx_code_signals_recallable_active
        ON code_signals(recallable, deleted_at)
        """,
        """
        CREATE TABLE code_relations (
            relation_id TEXT PRIMARY KEY,
            source_signal_id TEXT NOT NULL,
            source_chunk_id TEXT NOT NULL,
            source_file_path TEXT NOT NULL,
            target_name TEXT NOT NULL,
            kind TEXT NOT NULL,
            confidence REAL NOT NULL,
            target_kind TEXT NOT NULL,
            target_qualified_name TEXT NOT NULL,
            target_signature TEXT NOT NULL,
            target_arity INTEGER,
            target_project_unit_key TEXT NOT NULL,
            target_signal_id TEXT NOT NULL,
            resolution TEXT NOT NULL,
            producer TEXT NOT NULL,
            producer_confidence REAL NOT NULL,
            resolution_confidence REAL,
            metadata TEXT NOT NULL,
            deleted_at INTEGER
        )
        """,
        """
        CREATE INDEX idx_code_relations_source_active
        ON code_relations(source_signal_id, deleted_at)
        """,
        """
        CREATE INDEX idx_code_relations_target_signal_active
        ON code_relations(target_signal_id, deleted_at)
        """,
        """
        CREATE INDEX idx_code_relations_resolution_active
        ON code_relations(resolution, deleted_at)
        """,
        """
        CREATE INDEX idx_code_relations_target_active
        ON code_relations(target_name, deleted_at)
        WHERE resolution = 'legacy'
        """,
    )


def _replace_signals_v5(
    connection: sqlite3.Connection,
    path: str,
    signals: list[CodeSignal],
    deleted_at: int,
) -> None:
    connection.execute(
        """
        UPDATE code_signals
        SET deleted_at = ?
        WHERE file_path = ?
          AND deleted_at IS NULL
        """,
        (deleted_at, path),
    )
    for signal in signals:
        connection.execute(
            """
            INSERT INTO code_signals (
                signal_id, chunk_id, file_path, kind, name,
                qualified_name, signature, arity, project_unit_key,
                producer, start_line, end_line, start_column, end_column,
                language, recallable, tokens, metadata, deleted_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
            ON CONFLICT(signal_id) DO UPDATE SET
                chunk_id = excluded.chunk_id,
                file_path = excluded.file_path,
                kind = excluded.kind,
                name = excluded.name,
                qualified_name = excluded.qualified_name,
                signature = excluded.signature,
                arity = excluded.arity,
                project_unit_key = excluded.project_unit_key,
                producer = excluded.producer,
                start_line = excluded.start_line,
                end_line = excluded.end_line,
                start_column = excluded.start_column,
                end_column = excluded.end_column,
                language = excluded.language,
                recallable = excluded.recallable,
                tokens = excluded.tokens,
                metadata = excluded.metadata,
                deleted_at = NULL
            """,
            (
                signal.signal_id,
                signal.chunk_id,
                _path_key(signal.file_path),
                signal.kind,
                signal.name,
                signal.qualified_name,
                signal.signature,
                signal.arity,
                signal.project_unit_key,
                signal.producer,
                signal.start_line,
                signal.end_line,
                signal.start_column,
                signal.end_column,
                signal.language,
                int(signal.recallable),
                _to_json_list(signal.tokens),
                _to_json(signal.metadata),
            ),
        )


def _replace_relations_v5(
    connection: sqlite3.Connection,
    path: str,
    relations: list[CodeRelation],
    deleted_at: int,
) -> None:
    connection.execute(
        """
        UPDATE code_relations
        SET deleted_at = ?
        WHERE source_file_path = ?
          AND deleted_at IS NULL
        """,
        (deleted_at, path),
    )
    for relation in relations:
        _upsert_relation_v5(connection, relation)


def _upsert_relation_v5(
    connection: sqlite3.Connection,
    relation: CodeRelation,
) -> None:
    if relation.resolution not in RESOLUTION_STATES:
        raise ValueError(f"unknown resolution state: {relation.resolution!r}")
    source = connection.execute(
        """
        SELECT chunk_id, file_path
        FROM code_signals
        WHERE signal_id = ?
          AND deleted_at IS NULL
        """,
        (relation.source_signal_id,),
    ).fetchone()
    if source is None:
        raise ValueError(
            f"relation source signal is not active: {relation.source_signal_id}"
        )
    producer_confidence = (
        relation.confidence
        if relation.resolution == "legacy"
        else relation.producer_confidence
    )
    connection.execute(
        """
        INSERT INTO code_relations (
            relation_id, source_signal_id, source_chunk_id,
            source_file_path, target_name, kind, confidence,
            target_kind, target_qualified_name, target_signature,
            target_arity, target_project_unit_key, target_signal_id,
            resolution, producer, producer_confidence,
            resolution_confidence, metadata, deleted_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
        ON CONFLICT(relation_id) DO UPDATE SET
            source_signal_id = excluded.source_signal_id,
            source_chunk_id = excluded.source_chunk_id,
            source_file_path = excluded.source_file_path,
            target_name = excluded.target_name,
            kind = excluded.kind,
            confidence = excluded.confidence,
            target_kind = excluded.target_kind,
            target_qualified_name = excluded.target_qualified_name,
            target_signature = excluded.target_signature,
            target_arity = excluded.target_arity,
            target_project_unit_key = excluded.target_project_unit_key,
            target_signal_id = excluded.target_signal_id,
            resolution = excluded.resolution,
            producer = excluded.producer,
            producer_confidence = excluded.producer_confidence,
            resolution_confidence = excluded.resolution_confidence,
            metadata = excluded.metadata,
            deleted_at = NULL
        """,
        (
            relation.relation_id,
            relation.source_signal_id,
            source["chunk_id"],
            source["file_path"],
            relation.target_name,
            relation.kind,
            relation.confidence,
            relation.target_kind,
            relation.target_qualified_name,
            relation.target_signature,
            relation.target_arity,
            relation.target_project_unit_key,
            relation.target_signal_id,
            relation.resolution,
            relation.producer,
            producer_confidence,
            relation.resolution_confidence,
            _to_json(relation.metadata),
        ),
    )


def _graph_integrity(connection: sqlite3.Connection) -> GraphIntegrityResult:
    dangling_targets = int(
        connection.execute(
            """
            SELECT COUNT(*) AS count
            FROM code_relations relations
            LEFT JOIN code_signals targets
              ON targets.signal_id = relations.target_signal_id
             AND targets.deleted_at IS NULL
            WHERE relations.deleted_at IS NULL
              AND relations.resolution IN ('resolved_exact', 'resolved_unique')
              AND (
                relations.target_signal_id = ''
                OR targets.signal_id IS NULL
              )
            """
        ).fetchone()["count"]
    )
    valid_states = ", ".join("?" for _ in RESOLUTION_STATES)
    invalid_resolution_rows = int(
        connection.execute(
            f"""
            SELECT COUNT(*) AS count
            FROM code_relations
            WHERE deleted_at IS NULL
              AND (
                resolution NOT IN ({valid_states})
                OR (
                  resolution IN ('resolved_exact', 'resolved_unique')
                  AND (
                    target_signal_id = ''
                    OR resolution_confidence IS NULL
                    OR ABS(
                      confidence - MIN(producer_confidence, resolution_confidence)
                    ) > 0.000000001
                  )
                )
                OR (
                  resolution NOT IN ('resolved_exact', 'resolved_unique')
                  AND (
                    target_signal_id <> ''
                    OR resolution_confidence IS NOT NULL
                    OR ABS(confidence - producer_confidence) > 0.000000001
                  )
                )
              )
            """,
            RESOLUTION_STATES,
        ).fetchone()["count"]
    )
    invalid_resolution_rows += int(
        connection.execute(
            """
            SELECT COUNT(*) AS count
            FROM code_relations relations
            JOIN code_signals sources
              ON sources.signal_id = relations.source_signal_id
             AND sources.deleted_at IS NULL
            LEFT JOIN code_signals targets
              ON targets.signal_id = relations.target_signal_id
             AND targets.deleted_at IS NULL
            WHERE relations.deleted_at IS NULL
              AND (
                (
                  relations.resolution <> 'legacy'
                  AND relations.kind IN (
                    'calls', 'implements', 'implements_method', 'uses_type',
                    'imports_type', 'mapped_by', 'tests'
                  )
                  AND relations.target_project_unit_key
                      <> sources.project_unit_key
                )
                OR (
                  relations.resolution IN ('resolved_exact', 'resolved_unique')
                  AND targets.signal_id IS NOT NULL
                  AND (
                    targets.project_unit_key
                        <> relations.target_project_unit_key
                    OR targets.kind <> relations.target_kind
                    OR (
                      relations.target_kind <> 'module'
                      AND targets.qualified_name
                          <> relations.target_qualified_name
                    )
                    OR (
                      relations.target_signature <> ''
                      AND targets.signature <> relations.target_signature
                    )
                    OR (
                      relations.target_arity IS NOT NULL
                      AND (
                        targets.arity IS NULL
                        OR targets.arity <> relations.target_arity
                      )
                    )
                  )
                )
              )
            """
        ).fetchone()["count"]
    )
    orphan_sources = int(
        connection.execute(
            """
            SELECT COUNT(*) AS count
            FROM code_relations relations
            LEFT JOIN code_signals sources
              ON sources.signal_id = relations.source_signal_id
             AND sources.deleted_at IS NULL
            WHERE relations.deleted_at IS NULL
              AND sources.signal_id IS NULL
            """
        ).fetchone()["count"]
    )
    module_count_mismatches = int(
        connection.execute(
            """
            SELECT COUNT(*) AS count
            FROM (
                SELECT active_files.file_path
                FROM (
                    SELECT DISTINCT file_path
                    FROM chunks
                    WHERE deleted_at IS NULL
                ) active_files
                LEFT JOIN code_signals modules
                  ON modules.file_path = active_files.file_path
                 AND modules.kind = 'module'
                 AND modules.producer = 'core_module'
                 AND modules.deleted_at IS NULL
                GROUP BY active_files.file_path
                HAVING COUNT(modules.signal_id) <> 1
            ) mismatches
            """
        ).fetchone()["count"]
    )
    return GraphIntegrityResult(
        dangling_targets=dangling_targets,
        invalid_resolution_rows=invalid_resolution_rows,
        orphan_sources=orphan_sources,
        module_count_mismatches=module_count_mismatches,
    )


def _validate_v5_snapshot(
    connection: sqlite3.Connection,
    *,
    expected_embedding_ids: set[str] | None,
    expected_source_count: int | None,
    expected_chunk_count: int | None,
    expected_producer_resolution_generation: int | None,
) -> None:
    unfinished = _metadata_value(connection, FILE_WRITE_IN_PROGRESS_KEY) or ""
    if unfinished:
        raise GraphIntegrityError("unfinished file write")
    orphan_chunks = int(
        connection.execute(
            """
            SELECT COUNT(*) AS count
            FROM chunks
            LEFT JOIN source_files
              ON source_files.path = chunks.file_path
            WHERE chunks.deleted_at IS NULL
              AND source_files.path IS NULL
            """
        ).fetchone()["count"]
    )
    if orphan_chunks:
        raise GraphIntegrityError("active chunk has no source file")
    orphan_signals = int(
        connection.execute(
            """
            SELECT COUNT(*) AS count
            FROM code_signals signals
            LEFT JOIN chunks
              ON chunks.chunk_id = signals.chunk_id
             AND chunks.deleted_at IS NULL
            LEFT JOIN source_files
              ON source_files.path = signals.file_path
            WHERE signals.deleted_at IS NULL
              AND (
                chunks.chunk_id IS NULL
                OR chunks.file_path <> signals.file_path
                OR source_files.path IS NULL
              )
            """
        ).fetchone()["count"]
    )
    if orphan_signals:
        raise GraphIntegrityError("active signal has no owning source chunk")
    mismatched_relation_sources = int(
        connection.execute(
            """
            SELECT COUNT(*) AS count
            FROM code_relations relations
            JOIN code_signals sources
              ON sources.signal_id = relations.source_signal_id
             AND sources.deleted_at IS NULL
            WHERE relations.deleted_at IS NULL
              AND (
                relations.source_chunk_id <> sources.chunk_id
                OR relations.source_file_path <> sources.file_path
              )
            """
        ).fetchone()["count"]
    )
    if mismatched_relation_sources:
        raise GraphIntegrityError("relation source ownership mismatch")
    if expected_source_count is not None:
        source_count = int(
            connection.execute(
                "SELECT COUNT(*) AS count FROM source_files"
            ).fetchone()["count"]
        )
        if source_count != expected_source_count:
            raise GraphIntegrityError("source file count mismatch")
    if expected_chunk_count is not None:
        chunk_count = int(
            connection.execute(
                """
                SELECT COUNT(*) AS count
                FROM chunks
                WHERE deleted_at IS NULL
                """
            ).fetchone()["count"]
        )
        if chunk_count != expected_chunk_count:
            raise GraphIntegrityError("active chunk count mismatch")
    if expected_embedding_ids is not None:
        rows = connection.execute(
            """
            SELECT embedding_id
            FROM chunks
            WHERE deleted_at IS NULL
              AND embedding_id IS NOT NULL
            """
        ).fetchall()
        actual_ids = {str(row["embedding_id"]) for row in rows}
        if actual_ids != expected_embedding_ids:
            raise GraphIntegrityError("active embedding ID mismatch")
    if expected_producer_resolution_generation is not None:
        producer_generation = _integer_metadata(
            connection,
            PRODUCER_RESOLUTION_GENERATION_KEY,
        )
        association_generation = _integer_metadata(
            connection,
            TEST_ASSOCIATION_SOURCE_GENERATION_KEY,
        )
        if (
            producer_generation != expected_producer_resolution_generation
            or association_generation != producer_generation
        ):
            raise GraphIntegrityError("test association generation mismatch")


class _ConnectionMetadataReader:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def get_metadata(self, key: str) -> str | None:
        return _metadata_value(self.connection, key)


def _explain_signal(signal: CodeSignal) -> dict[str, object]:
    return {
        "signal_id": signal.signal_id,
        "kind": signal.kind,
        "name": signal.name,
        "qualified_name": signal.qualified_name,
        "producer": signal.producer,
        "start_line": signal.start_line,
        "end_line": signal.end_line,
        "recallable": signal.recallable,
    }


def _explain_relation(row: sqlite3.Row, direction: str) -> dict[str, object]:
    relation = _relation_from_row(row)
    confidence = effective_relation_confidence(
        resolution=relation.resolution,
        target_signal_id=relation.target_signal_id,
        producer_confidence=relation.producer_confidence,
        resolution_confidence=relation.resolution_confidence,
    )
    target_signal_name = row["target_signal_name"]
    target_path = row["target_path"]
    return {
        "relation_id": relation.relation_id,
        "kind": relation.kind,
        "direction": direction,
        "confidence": confidence,
        "producer_confidence": relation.producer_confidence,
        "resolution_confidence": relation.resolution_confidence,
        "resolution": relation.resolution,
        "source_signal_id": relation.source_signal_id,
        "source_name": str(row["source_name"]),
        "target_signal_id": relation.target_signal_id,
        "target_name": (
            str(target_signal_name)
            if target_signal_name is not None
            else relation.target_name
        ),
        "target_path": str(target_path) if target_path is not None else "",
    }


def _integer_metadata(connection: sqlite3.Connection, key: str) -> int:
    raw = _metadata_value(connection, key)
    try:
        return int(raw) if raw is not None else 0
    except ValueError as error:
        raise GraphIntegrityError(f"invalid graph metadata: {key}") from error


def _open_connection(
    db_path: Path,
    busy_timeout_ms: int,
) -> sqlite3.Connection:
    if busy_timeout_ms < 0:
        raise ValueError("busy timeout must be non-negative")
    connection = sqlite3.connect(
        db_path,
        timeout=busy_timeout_ms / 1_000,
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute(f"PRAGMA busy_timeout = {busy_timeout_ms}")
    return connection


def _stored_signal_schema_version(connection: sqlite3.Connection) -> int:
    raw = _metadata_value(connection, SIGNAL_SCHEMA_VERSION_KEY)
    if raw is None or raw == "":
        return 0
    try:
        version = int(raw)
    except (TypeError, ValueError) as error:
        raise IncompatibleSignalSchemaError(raw) from error
    if version < 0:
        raise IncompatibleSignalSchemaError(raw)
    return version


def _require_target_schema(connection: sqlite3.Connection) -> None:
    version = _stored_signal_schema_version(connection)
    if version != TARGET_SIGNAL_SCHEMA_VERSION:
        raise IncompatibleSignalSchemaError(version)
    _require_v5_tables(connection)


def _require_v5_tables(connection: sqlite3.Connection) -> None:
    if not _has_column(connection, "code_signals", "qualified_name"):
        raise ValueError("v5 signal schema is required")
    if not _has_column(connection, "code_relations", "resolution"):
        raise ValueError("v5 relation schema is required")


def _metadata_value(
    connection: sqlite3.Connection,
    key: str,
) -> str | None:
    if not _table_exists(connection, "index_metadata"):
        return None
    row = connection.execute(
        "SELECT value FROM index_metadata WHERE key = ?",
        (key,),
    ).fetchone()
    return str(row["value"]) if row is not None else None


def _table_exists(connection: sqlite3.Connection, table: str) -> bool:
    return (
        connection.execute(
            """
            SELECT 1
            FROM sqlite_master
            WHERE type IN ('table', 'view')
              AND name = ?
            """,
            (table,),
        ).fetchone()
        is not None
    )


def _set_metadata_row(
    connection: sqlite3.Connection,
    key: str,
    value: str,
    updated_at: int,
) -> None:
    connection.execute(
        """
        INSERT INTO index_metadata (key, value, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET
            value = excluded.value,
            updated_at = excluded.updated_at
        """,
        (key, value, updated_at),
    )


def _table_columns(
    connection: sqlite3.Connection,
    table: str,
) -> frozenset[str]:
    if table not in {
        "code_signals",
        "code_relations",
        "source_files",
        "scan_skips",
        "operational_controls",
    }:
        raise ValueError("unsupported schema table")
    return frozenset(
        str(row["name"])
        for row in connection.execute(f"PRAGMA table_info({table})")
    )


def _has_column(
    connection: sqlite3.Connection,
    table: str,
    column: str,
) -> bool:
    return column in _table_columns(connection, table)


def _raise_if_busy(error: BaseException) -> None:
    if isinstance(error, sqlite3.OperationalError) and any(
        marker in str(error).lower()
        for marker in ("database is locked", "database is busy")
    ):
        raise IndexBusyError() from error


def _row_value(row: sqlite3.Row, key: str, default: Any) -> Any:
    return row[key] if key in row.keys() else default


def _path_key(path: Path) -> str:
    return path.as_posix()


def _now() -> int:
    return int(time.time())


def _to_json(value: dict[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _to_json_list(value: list[str]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _from_json(value: str) -> dict[str, Any]:
    return json.loads(value)


def _from_json_list(value: str) -> list[str]:
    return list(json.loads(value))


def _dedupe_search_probes(probes: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for probe in probes:
        normalized = probe.strip()
        if not normalized:
            continue
        key = normalized.casefold()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(normalized)
    # Limit total probes to prevent performance issues with CJK n-gram explosion
    # Prioritize longer probes (more information density)
    if len(deduped) > 30:
        deduped = sorted(deduped, key=len, reverse=True)[:30]
    return deduped


def _dedupe_values(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped


def _matched_direct_text_probes(haystack: str, probes: list[str]) -> list[str]:
    folded_haystack = haystack.casefold()
    matched: list[str] = []
    for probe in probes:
        if probe.casefold() in folded_haystack:
            matched.append(probe)
    return matched


def _direct_text_score(matched: list[str], probes: list[str]) -> float:
    if not matched or not probes:
        return 0.0
    # Distinguish CJK and ASCII information density
    # CJK: 4+ chars = high confidence; ASCII: 8+ chars = high confidence
    has_strong_match = any(
        (len(probe) >= 4 and _DIRECT_TEXT_CJK_SEQUENCE_RE.search(probe)) or len(probe) >= 8
        for probe in matched
    )
    if not has_strong_match:
        return min(0.50, len(matched) / min(len(probes), 6))
    coverage = len(matched) / min(len(probes), 6)
    return min(1.0, max(0.60, coverage))


def _metadata_search_text(metadata: dict[str, Any]) -> str:
    values: list[str] = []
    for key, value in metadata.items():
        values.append(key)
        if isinstance(value, str):
            values.append(value)
        elif isinstance(value, (int, float, bool)):
            values.append(str(value))
        elif value is not None:
            values.append(str(value))
    return " ".join(values)


def _signal_row_prefilter(tokens: list[str]) -> tuple[str, tuple[str, ...]]:
    if not all(
        token.isascii() and _SIGNAL_SQL_SAFE_TOKEN_RE.fullmatch(token)
        for token in tokens
    ):
        return "", ()

    clauses: list[str] = []
    values: list[str] = []
    for token in tokens:
        clauses.append(
            "instr(lower(name || ' ' || tokens || ' ' || metadata), ?) > 0"
        )
        values.append(token)

    clauses.extend(
        (
            "name GLOB '*[^ -~]*'",
            "instr(tokens, ?) > 0",
            "instr(metadata, ?) > 0",
        )
    )
    values.extend((r"\u", r"\u"))
    if any(token in "none" for token in tokens):
        clauses.append("instr(metadata, 'null') > 0")
    return f"AND ({' OR '.join(clauses)})", tuple(values)


def _signal_from_row(row: sqlite3.Row) -> CodeSignal:
    return CodeSignal(
        signal_id=row["signal_id"],
        chunk_id=row["chunk_id"],
        file_path=Path(row["file_path"]),
        kind=row["kind"],
        name=row["name"],
        start_line=row["start_line"],
        end_line=row["end_line"],
        language=row["language"],
        tokens=_from_json_list(row["tokens"]),
        metadata=_from_json(row["metadata"]),
        qualified_name=_row_value(row, "qualified_name", ""),
        signature=_row_value(row, "signature", ""),
        arity=_row_value(row, "arity", None),
        project_unit_key=_row_value(row, "project_unit_key", ""),
        producer=_row_value(row, "producer", "legacy"),
        start_column=int(_row_value(row, "start_column", 0)),
        end_column=int(_row_value(row, "end_column", 0)),
        recallable=bool(_row_value(row, "recallable", 1)),
    )


def _relation_from_row(
    row: sqlite3.Row,
    *,
    v4_confidence_from_effective: bool = True,
) -> CodeRelation:
    confidence = float(row["confidence"])
    return CodeRelation(
        relation_id=row["relation_id"],
        source_signal_id=row["source_signal_id"],
        target_name=row["target_name"],
        kind=row["kind"],
        confidence=confidence,
        metadata=_from_json(row["metadata"]),
        target_kind=_row_value(row, "target_kind", ""),
        target_qualified_name=_row_value(
            row,
            "target_qualified_name",
            "",
        ),
        target_signature=_row_value(row, "target_signature", ""),
        target_arity=_row_value(row, "target_arity", None),
        target_project_unit_key=_row_value(
            row,
            "target_project_unit_key",
            "",
        ),
        target_signal_id=_row_value(row, "target_signal_id", ""),
        resolution=_row_value(row, "resolution", "legacy"),
        producer=_row_value(row, "producer", "legacy"),
        producer_confidence=float(
            _row_value(
                row,
                "producer_confidence",
                confidence if v4_confidence_from_effective else 1.0,
            )
        ),
        resolution_confidence=_row_value(
            row,
            "resolution_confidence",
            None,
        ),
    )


def _source_file_from_row(row: sqlite3.Row) -> SourceFile:
    return SourceFile(
        path=Path(row["path"]),
        language=row["language"],
        sha256=row["sha256"],
        size=row["size"],
        mtime_ns=row["mtime_ns"],
        is_generated=bool(row["is_generated"]),
        is_test=bool(row["is_test"]),
        metadata=_from_json(row["metadata"]),
    )


def _fts_query(tokens: list[str]) -> str:
    quoted = [_quote_fts_token(token) for token in tokens if token]
    return " AND ".join(quoted)


def _quote_fts_token(token: str) -> str:
    escaped = token.replace('"', '""')
    return f'"{escaped}"'


def _maintenance_threshold(active_rows: int) -> int:
    return max(_TOMBSTONE_THRESHOLD_MINIMUM, (active_rows + 19) // 20)


def _bounded_purge_count(deleted_rows: int, limit: int) -> int:
    return min(limit, deleted_rows)


def _maintenance_purge_count(
    *,
    active_rows: int,
    deleted_rows: int,
    limit: int,
) -> int:
    if deleted_rows <= _maintenance_threshold(active_rows):
        return 0
    return _bounded_purge_count(deleted_rows, limit)


def _maintenance_counts(connection: sqlite3.Connection) -> dict[str, int]:
    def count(sql: str) -> int:
        return int(connection.execute(sql).fetchone()[0])

    active_chunks = count("SELECT COUNT(*) FROM chunks WHERE deleted_at IS NULL")
    deleted_chunks = count(
        "SELECT COUNT(*) FROM chunks WHERE deleted_at IS NOT NULL"
    )
    active_signals = count(
        "SELECT COUNT(*) FROM code_signals WHERE deleted_at IS NULL"
    )
    deleted_signals = count(
        "SELECT COUNT(*) FROM code_signals WHERE deleted_at IS NOT NULL"
    )
    active_relations = count(
        "SELECT COUNT(*) FROM code_relations WHERE deleted_at IS NULL"
    )
    deleted_relations = count(
        "SELECT COUNT(*) FROM code_relations WHERE deleted_at IS NOT NULL"
    )
    active_symbols = count(
        """
        SELECT COUNT(DISTINCT symbols.symbol_id)
        FROM symbols
        JOIN chunk_symbols ON chunk_symbols.symbol_id = symbols.symbol_id
        """
    )
    orphan_symbols = count(
        """
        SELECT COUNT(*)
        FROM symbols
        LEFT JOIN chunk_symbols ON chunk_symbols.symbol_id = symbols.symbol_id
        WHERE chunk_symbols.symbol_id IS NULL
        """
    )
    active_associations = count(
        """
        SELECT COUNT(*)
        FROM code_relations
        WHERE producer = 'test_association' AND deleted_at IS NULL
        """
    )
    orphan_associations = count(
        """
        SELECT COUNT(*)
        FROM code_relations
        WHERE producer = 'test_association' AND deleted_at IS NOT NULL
        """
    )
    return {
        "active_chunks": active_chunks,
        "deleted_chunks": deleted_chunks,
        "active_signals": active_signals,
        "deleted_signals": deleted_signals,
        "active_relations": active_relations,
        "deleted_relations": deleted_relations,
        "active_symbols": active_symbols,
        "orphan_symbols": orphan_symbols,
        "active_associations": active_associations,
        "orphan_associations": orphan_associations,
    }


def _in_query(sql: str, values: list[Any]) -> str:
    placeholders = ", ".join("?" for _ in values)
    return sql.format(placeholders=placeholders)
