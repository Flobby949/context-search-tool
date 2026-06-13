from pathlib import Path

from context_search_tool.models import DocumentChunk, SourceFile, SymbolRef
from context_search_tool.sqlite_store import SQLiteStore


def test_store_round_trips_files_chunks_symbols_and_fts(tmp_path: Path) -> None:
    db_path = tmp_path / "index.sqlite"
    store = SQLiteStore(db_path)
    store.initialize()

    source = SourceFile(
        path=Path("src/App.java"),
        language="java",
        sha256="a" * 64,
        size=100,
        mtime_ns=123,
        is_generated=False,
        is_test=False,
        metadata={},
    )
    symbol = SymbolRef(
        name="ApplyAuditController",
        kind="class",
        start_line=1,
        end_line=20,
        language="java",
        metadata={"role": "controller"},
    )
    chunk = DocumentChunk(
        chunk_id="chunk-1",
        file_path=Path("src/App.java"),
        start_line=1,
        end_line=20,
        content="@PostMapping(\"/apply/audit/pageEs\")\nclass ApplyAuditController {}",
        chunk_type="symbol",
        symbols=[symbol],
        lexical_tokens=["post", "mapping", "apply", "audit", "page", "es"],
        embedding_id="chunk-1",
        deleted_at=None,
        metadata={"route_path": "/apply/audit/pageEs"},
    )

    store.upsert_source_file(source)
    store.replace_chunks(Path("src/App.java"), [chunk])

    matches = store.lexical_search(["apply", "audit"], limit=5)

    assert matches[0].chunk_id == "chunk-1"
    assert store.chunk_for_line(Path("src/App.java"), 3).chunk_id == "chunk-1"


def test_store_marks_removed_file_chunks_deleted(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize()
    chunk = DocumentChunk(
        chunk_id="chunk-1",
        file_path=Path("src/App.java"),
        start_line=1,
        end_line=2,
        content="class App {}",
        chunk_type="generic",
        symbols=[],
        lexical_tokens=["class", "app"],
        embedding_id="chunk-1",
        deleted_at=None,
        metadata={},
    )
    store.replace_chunks(Path("src/App.java"), [chunk])

    store.mark_file_deleted(Path("src/App.java"))

    assert store.lexical_search(["app"], limit=5) == []
    assert store.deleted_chunk_ids() == {"chunk-1"}


def test_store_exposes_source_file_and_active_indexed_paths(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize()
    source = SourceFile(
        path=Path("src/App.java"),
        language="java",
        sha256="b" * 64,
        size=50,
        mtime_ns=456,
        is_generated=False,
        is_test=True,
        metadata={"role": "fixture"},
    )
    chunk = DocumentChunk(
        chunk_id="chunk-2",
        file_path=Path("src/App.java"),
        start_line=1,
        end_line=1,
        content="class App {}",
        chunk_type="generic",
        symbols=[],
        lexical_tokens=["app"],
        embedding_id="chunk-2",
        deleted_at=None,
        metadata={},
    )

    store.upsert_source_file(source)
    store.replace_chunks(Path("src/App.java"), [chunk])

    assert store.source_file_for_path(Path("src/App.java")) == source
    assert store.source_file_for_path(Path("src/Missing.java")) is None
    assert store.indexed_file_paths() == {Path("src/App.java")}

    store.mark_file_deleted(Path("src/App.java"))

    assert store.indexed_file_paths() == set()
