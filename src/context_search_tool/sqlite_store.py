from __future__ import annotations

import json
import logging
import re
import sqlite3
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable

from context_search_tool.graph_contract import EDGE_QUERY_LIMIT, RESOLUTION_STATES
from context_search_tool.graph_lifecycle import (
    FULL_REINDEX_REQUIRED_KEY,
    GRAPH_RESOLUTION_STATE_KEY,
    GRAPH_RESOLUTION_VERSION_KEY,
    GRAPH_STALE_REASON_KEY,
    PROJECT_UNIT_TOPOLOGY_FINGERPRINT_KEY,
    SIGNAL_SCHEMA_VERSION_KEY,
    GraphCapability,
    GraphIntegrityError,
    GraphIntegrityResult,
    IncompatibleSignalSchemaError,
    IndexBusyError,
    TARGET_GRAPH_RESOLUTION_VERSION,
    TARGET_SIGNAL_SCHEMA_VERSION,
    read_graph_capability,
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
_DEFAULT_BUSY_TIMEOUT_MS = 5_000
_RESOLVED_STATES = ("resolved_exact", "resolved_unique")


class SQLiteStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    def initialize(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
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
                );

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
                );

                CREATE INDEX IF NOT EXISTS idx_chunks_file_active
                ON chunks(file_path, deleted_at);

                CREATE TABLE IF NOT EXISTS symbols (
                    symbol_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    start_line INTEGER NOT NULL,
                    end_line INTEGER NOT NULL,
                    language TEXT NOT NULL,
                    metadata TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS chunk_symbols (
                    chunk_id TEXT NOT NULL,
                    symbol_id INTEGER NOT NULL,
                    PRIMARY KEY (chunk_id, symbol_id),
                    FOREIGN KEY (chunk_id) REFERENCES chunks(chunk_id),
                    FOREIGN KEY (symbol_id) REFERENCES symbols(symbol_id)
                );

                CREATE TABLE IF NOT EXISTS chunk_tokens (
                    chunk_id TEXT NOT NULL,
                    token TEXT NOT NULL,
                    FOREIGN KEY (chunk_id) REFERENCES chunks(chunk_id)
                );

                CREATE INDEX IF NOT EXISTS idx_chunk_tokens_token
                ON chunk_tokens(token);

                CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts
                USING fts5(chunk_id UNINDEXED, file_path, content, tokens);

                CREATE TABLE IF NOT EXISTS index_metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at INTEGER NOT NULL
                );

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
                );

                CREATE INDEX IF NOT EXISTS idx_code_signals_chunk_active
                ON code_signals(chunk_id, deleted_at);

                CREATE INDEX IF NOT EXISTS idx_code_signals_file_active
                ON code_signals(file_path, deleted_at);

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
                );

                CREATE INDEX IF NOT EXISTS idx_code_relations_source_active
                ON code_relations(source_signal_id, deleted_at);

                CREATE INDEX IF NOT EXISTS idx_code_relations_target_active
                ON code_relations(target_name, deleted_at);
                """
            )

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
            self._delete_search_payloads(connection, incoming_ids)

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
            recallable_filter = (
                "AND recallable = 1"
                if _has_column(connection, "code_signals", "recallable")
                else ""
            )
            rows = connection.execute(
                f"""
                SELECT *
                FROM code_signals
                WHERE deleted_at IS NULL
                  {recallable_filter}
                """
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
            return [self._chunk_from_row(connection, row) for row in rows]

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
                grouped[target_name] = [
                    self._chunk_from_row(connection, row) for row in rows
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
                """
                SELECT chunk_tokens.chunk_id, chunk_tokens.token
                FROM chunk_tokens
                JOIN chunks ON chunks.chunk_id = chunk_tokens.chunk_id
                WHERE chunks.deleted_at IS NULL
                """
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
            chunks_by_id = {
                row["chunk_id"]: self._chunk_from_row(connection, row) for row in rows
            }

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
            return [self._chunk_from_row(connection, row) for row in rows]

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
            return [self._chunk_from_row(connection, row) for row in rows]

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
        self.capability: GraphCapability

    def __enter__(self) -> GraphReadSession:
        connection = _open_connection(self.db_path, self.busy_timeout_ms)
        try:
            connection.execute("BEGIN")
            self._connection = connection
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
        self._connection = None
        if connection is not None:
            if connection.in_transaction:
                connection.rollback()
            connection.close()

    def get_metadata(self, key: str) -> str | None:
        connection = self._require_connection()
        return _metadata_value(connection, key)

    def module_for_path(self, file_path: Path) -> CodeSignal | None:
        if self.capability.status != "ready" or not self.capability.structured:
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
        if self.capability.status != "ready" or not self.capability.structured:
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

    def signals_for_chunks_with_modules(
        self,
        chunk_ids: list[str],
        *,
        limit: int = EDGE_QUERY_LIMIT,
    ) -> list[CodeSignal]:
        if (
            self.capability.status != "ready"
            or not self.capability.structured
            or not chunk_ids
            or limit <= 0
        ):
            return []
        chunk_ids = _dedupe_values(chunk_ids)
        bounded_limit = min(limit, EDGE_QUERY_LIMIT)
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

    def outgoing_relations(
        self,
        source_signal_id: str,
        *,
        limit: int = EDGE_QUERY_LIMIT,
    ) -> list[CodeRelation]:
        if self.capability.status != "ready" or not self.capability.structured:
            return []
        rows = self._require_connection().execute(
            """
            SELECT *
            FROM code_relations
            WHERE source_signal_id = ?
              AND resolution IN ('resolved_exact', 'resolved_unique')
              AND deleted_at IS NULL
            ORDER BY kind, target_project_unit_key, target_kind,
                     target_qualified_name, target_signature,
                     COALESCE(target_arity, -1), relation_id
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
        if self.capability.status != "legacy":
            return []
        rows = self._require_connection().execute(
            """
            SELECT *
            FROM code_relations
            WHERE source_signal_id = ?
              AND deleted_at IS NULL
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

    def incoming_relations(
        self,
        target_signal_id: str,
        *,
        limit: int = EDGE_QUERY_LIMIT,
    ) -> list[CodeRelation]:
        if self.capability.status != "ready" or not self.capability.structured:
            return []
        rows = self._require_connection().execute(
            """
            SELECT *
            FROM code_relations
            WHERE target_signal_id = ?
              AND resolution IN ('resolved_exact', 'resolved_unique')
              AND deleted_at IS NULL
            ORDER BY kind, source_file_path, source_signal_id, relation_id
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

    def _require_connection(self) -> sqlite3.Connection:
        if self._connection is None:
            raise RuntimeError("graph read session is closed")
        return self._connection


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
            SET target_signal_id = ?,
                resolution = ?,
                confidence = ?,
                producer_confidence = ?,
                resolution_confidence = ?
            WHERE relation_id = ?
              AND deleted_at IS NULL
            """,
            (
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
    table = connection.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type = 'table'
          AND name = 'index_metadata'
        """
    ).fetchone()
    if table is None:
        return None
    row = connection.execute(
        "SELECT value FROM index_metadata WHERE key = ?",
        (key,),
    ).fetchone()
    return str(row["value"]) if row is not None else None


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
    if table not in {"code_signals", "code_relations"}:
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


def _in_query(sql: str, values: list[Any]) -> str:
    placeholders = ", ".join("?" for _ in values)
    return sql.format(placeholders=placeholders)
