from __future__ import annotations

from pathlib import Path

from context_search_tool.models import DocumentChunk, SourceFile, SymbolRef
from context_search_tool.sqlite_store import SQLiteStore


def _store(tmp_path: Path) -> SQLiteStore:
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize()
    return store


def _source(path: str, language: str = "python", is_test: bool = False) -> SourceFile:
    return SourceFile(
        path=Path(path),
        language=language,
        sha256=path,
        size=100,
        mtime_ns=1,
        is_test=is_test,
    )


def _chunk(chunk_id: str, path: str, content: str, symbols: list[str]) -> DocumentChunk:
    return DocumentChunk(
        chunk_id=chunk_id,
        file_path=Path(path),
        start_line=1,
        end_line=20,
        content=content,
        chunk_type="code",
        symbols=[
            SymbolRef(
                name=name,
                kind="function",
                start_line=1,
                end_line=5,
                language="python",
            )
            for name in symbols
        ],
        lexical_tokens=["session", "cookies", "cookiejar", "response"],
    )


def test_store_exposes_language_file_symbol_and_token_inputs(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.upsert_source_file(_source("src/requests/sessions.py"))
    store.upsert_source_file(_source("src/requests/cookies.py"))
    store.upsert_source_file(_source("tests/test_requests.py", is_test=True))
    store.replace_chunks(
        Path("src/requests/sessions.py"),
        [_chunk("c1", "src/requests/sessions.py", "class Session: pass", ["Session"])],
    )
    store.replace_chunks(
        Path("src/requests/cookies.py"),
        [
            _chunk(
                "c2",
                "src/requests/cookies.py",
                "class RequestsCookieJar: pass",
                ["RequestsCookieJar"],
            )
        ],
    )

    assert store.language_counts() == [("python", 3)]
    assert Path("src/requests/sessions.py") in store.source_files_for_profile(limit=10)
    assert "Session" in store.symbol_names_for_profile(limit=10)
    assert "cookies" in store.token_counts_for_profile(limit=10)
