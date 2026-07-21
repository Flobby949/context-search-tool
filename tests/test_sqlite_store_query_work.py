from __future__ import annotations

import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest

from context_search_tool import sqlite_store as sqlite_store_module
from context_search_tool.models import CodeSignal, DocumentChunk, SymbolRef
from context_search_tool.sqlite_store import SQLiteStore


def _chunk(index: int) -> DocumentChunk:
    chunk_id = f"chunk-{index:02d}"
    return DocumentChunk(
        chunk_id=chunk_id,
        file_path=Path(f"src/File{index:02d}.java"),
        start_line=1,
        end_line=20,
        content=f"class File{index:02d} {{}}",
        chunk_type="symbol",
        symbols=[
            SymbolRef(
                name=f"File{index:02d}",
                kind="class",
                start_line=1,
                end_line=20,
                language="java",
            )
        ],
        lexical_tokens=[f"token-{index:02d}-{token}" for token in range(20)],
        embedding_id=chunk_id,
        deleted_at=None,
        metadata={"index": index},
    )


def test_chunks_for_ids_reads_payload_tables_once_per_batch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize_v5()
    chunks = [_chunk(index) for index in range(8)]
    for chunk in chunks:
        store.replace_chunks(chunk.file_path, [chunk])

    payload_selects = {"tokens": 0, "symbols": 0}
    real_open_connection = sqlite_store_module._open_connection

    def traced_open_connection(*args, **kwargs):
        connection = real_open_connection(*args, **kwargs)

        def trace_statement(statement: str) -> None:
            normalized = " ".join(statement.lower().split())
            if normalized.startswith("select") and " from chunk_tokens " in (
                f" {normalized} "
            ):
                payload_selects["tokens"] += 1
            if normalized.startswith("select") and " join chunk_symbols " in (
                f" {normalized} "
            ):
                payload_selects["symbols"] += 1

        connection.set_trace_callback(trace_statement)
        return connection

    monkeypatch.setattr(
        sqlite_store_module,
        "_open_connection",
        traced_open_connection,
    )

    requested = ["chunk-07", "missing", "chunk-03", "chunk-00", "chunk-07"]
    expected = {
        chunk_id: chunks[int(chunk_id.removeprefix("chunk-"))]
        for chunk_id in ("chunk-07", "chunk-03", "chunk-00")
    }

    direct = store.chunks_for_ids(requested)
    with store.graph_read_session() as session:
        snapshot = session.chunks_for_ids(requested)

    assert direct == expected
    assert snapshot == expected
    assert list(direct) == list(snapshot) == list(expected)
    assert payload_selects == {"tokens": 2, "symbols": 2}


def test_ascii_signal_search_decodes_only_matching_rows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize_v5()
    chunk = _chunk(0)
    store.replace_chunks(chunk.file_path, [chunk])
    signals = [
        CodeSignal(
            signal_id=f"noise-{index:04d}",
            chunk_id=chunk.chunk_id,
            file_path=chunk.file_path,
            kind="method",
            name=f"Noise.method{index}",
            start_line=100 + index,
            end_line=100 + index,
            language="java",
            tokens=[f"noise-{index}"],
            metadata={"nested": {"value": f"irrelevant-{index}"}},
        )
        for index in range(400)
    ]
    matches = [
        CodeSignal(
            signal_id="match-name",
            chunk_id=chunk.chunk_id,
            file_path=chunk.file_path,
            kind="endpoint",
            name="NeedleHandler",
            start_line=30,
            end_line=30,
            language="java",
        ),
        CodeSignal(
            signal_id="match-token",
            chunk_id=chunk.chunk_id,
            file_path=chunk.file_path,
            kind="method",
            name="TokenMatch",
            start_line=10,
            end_line=10,
            language="java",
            tokens=["needle-token"],
        ),
        CodeSignal(
            signal_id="match-metadata",
            chunk_id=chunk.chunk_id,
            file_path=chunk.file_path,
            kind="method",
            name="MetadataMatch",
            start_line=20,
            end_line=20,
            language="java",
            metadata={"nested": {"value": "needle-metadata"}},
        ),
        CodeSignal(
            signal_id="nonrecallable-match",
            chunk_id=chunk.chunk_id,
            file_path=chunk.file_path,
            kind="endpoint",
            name="NeedleHandler",
            start_line=1,
            end_line=1,
            language="java",
            recallable=False,
        ),
    ]
    store.replace_signals(chunk.file_path, [*signals, *matches])

    decoded_signal_rows = 0
    real_open_connection = sqlite_store_module._open_connection

    def traced_open_connection(*args, **kwargs):
        connection = real_open_connection(*args, **kwargs)
        state = {"statement": ""}

        def trace_statement(statement: str) -> None:
            state["statement"] = " ".join(statement.lower().split())

        def count_row(cursor, values):
            nonlocal decoded_signal_rows
            row = sqlite3.Row(cursor, values)
            if (
                state["statement"].startswith("select * from code_signals")
                and "where deleted_at is null" in state["statement"]
            ):
                decoded_signal_rows += 1
            return row

        connection.set_trace_callback(trace_statement)
        connection.row_factory = count_row
        return connection

    monkeypatch.setattr(
        sqlite_store_module,
        "_open_connection",
        traced_open_connection,
    )

    tokens = ["needlehandler", "needle-token", "needle-metadata"]
    expected_ids = ["match-name", "match-token", "match-metadata"]

    direct = store.signal_search(tokens, limit=10)
    with store.graph_read_session() as session:
        session.capability = replace(
            session.capability,
            signal_evidence_allowed=True,
        )
        snapshot = session.signal_search(tokens, limit=10)

    assert [signal.signal_id for signal in direct] == expected_ids
    assert snapshot == direct
    assert decoded_signal_rows == len(expected_ids) * 2
