from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any

from context_search_tool.models import (
    DocumentChunk,
    RetrievalCandidate,
    SourceFile,
    SymbolRef,
)


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

    def mark_file_deleted(self, file_path: Path) -> None:
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

        scores: dict[str, float] = {}
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
                scores[row["chunk_id"]] = sum(
                    1.0 for token in normalized if token in path
                )

            token_rows = connection.execute(
                """
                SELECT chunk_tokens.chunk_id, chunk_tokens.token
                FROM chunk_tokens
                JOIN chunks ON chunks.chunk_id = chunk_tokens.chunk_id
                WHERE chunks.deleted_at IS NULL
                """
            ).fetchall()
            for row in token_rows:
                if row["token"].lower() in normalized:
                    scores[row["chunk_id"]] = scores.get(row["chunk_id"], 0.0) + 1.0

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
                scores[row["chunk_id"]] = scores.get(row["chunk_id"], 0.0) + sum(
                    1.0 for token in normalized if token in name
                )

        ranked = sorted(
            ((chunk_id, score) for chunk_id, score in scores.items() if score > 0),
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

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

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


def _path_key(path: Path) -> str:
    return path.as_posix()


def _now() -> int:
    return int(time.time())


def _to_json(value: dict[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _from_json(value: str) -> dict[str, Any]:
    return json.loads(value)


def _fts_query(tokens: list[str]) -> str:
    quoted = [_quote_fts_token(token) for token in tokens if token]
    return " AND ".join(quoted)


def _quote_fts_token(token: str) -> str:
    escaped = token.replace('"', '""')
    return f'"{escaped}"'


def _in_query(sql: str, values: list[Any]) -> str:
    placeholders = ", ".join("?" for _ in values)
    return sql.format(placeholders=placeholders)
