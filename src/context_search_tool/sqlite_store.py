from __future__ import annotations

import json
import logging
import re
import sqlite3
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

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
            rows = connection.execute(
                """
                SELECT *
                FROM code_signals
                WHERE chunk_id = ?
                  AND deleted_at IS NULL
                ORDER BY start_line, end_line, kind, name, signal_id
                """,
                (chunk_id,),
            ).fetchall()
        return [_signal_from_row(row) for row in rows]

    def signal_search(self, tokens: list[str], limit: int) -> list[CodeSignal]:
        normalized = [token.lower() for token in tokens if token]
        if not normalized or limit <= 0:
            return []

        matches: list[tuple[CodeSignal, float]] = []
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM code_signals
                WHERE deleted_at IS NULL
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
            rows = connection.execute(
                """
                SELECT *
                FROM code_relations
                WHERE source_signal_id = ?
                  AND deleted_at IS NULL
                ORDER BY kind, target_name, relation_id
                """,
                (source_signal_id,),
            ).fetchall()
        return [_relation_from_row(row) for row in rows]

    def relations_targeting(self, target_name: str) -> list[CodeRelation]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM code_relations
                WHERE target_name = ?
                  AND deleted_at IS NULL
                ORDER BY kind, source_signal_id, relation_id
                """,
                (target_name,),
            ).fetchall()
        return [_relation_from_row(row) for row in rows]

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
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            with connection:
                yield connection
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


def _chunks_matching_name(
    connection: sqlite3.Connection,
    target_name: str,
    limit: int,
) -> list[sqlite3.Row]:
    return connection.execute(
        """
        SELECT DISTINCT chunks.*
        FROM chunks
        LEFT JOIN code_signals
          ON code_signals.chunk_id = chunks.chunk_id
         AND code_signals.deleted_at IS NULL
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
    return connection.execute(
        _in_query(
            """
        SELECT DISTINCT chunks.*
        FROM chunks
        LEFT JOIN code_signals
          ON code_signals.chunk_id = chunks.chunk_id
         AND code_signals.deleted_at IS NULL
        LEFT JOIN chunk_symbols
          ON chunk_symbols.chunk_id = chunks.chunk_id
        LEFT JOIN symbols
          ON symbols.symbol_id = chunk_symbols.symbol_id
        WHERE chunks.deleted_at IS NULL
          AND (
            code_signals.name IN ({placeholders})
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
    )


def _relation_from_row(row: sqlite3.Row) -> CodeRelation:
    return CodeRelation(
        relation_id=row["relation_id"],
        source_signal_id=row["source_signal_id"],
        target_name=row["target_name"],
        kind=row["kind"],
        confidence=float(row["confidence"]),
        metadata=_from_json(row["metadata"]),
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
