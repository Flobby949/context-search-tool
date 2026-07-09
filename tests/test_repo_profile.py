from __future__ import annotations

import json
from pathlib import Path

from context_search_tool.models import DocumentChunk, SourceFile, SymbolRef
from context_search_tool.repo_profile import (
    RepoProfileLimits,
    build_repo_profile,
    profile_vocabulary,
    repo_profile_payload,
    rewritten_query_is_repo_supported,
    term_is_repo_supported,
)
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


def test_build_repo_profile_prefers_source_vocabulary_and_hashes_payload(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    store.upsert_source_file(_source("src/requests/sessions.py"))
    store.upsert_source_file(_source("src/requests/cookies.py"))
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
                "RequestsCookieJar",
                ["RequestsCookieJar"],
            )
        ],
    )

    profile = build_repo_profile(
        store,
        limits=RepoProfileLimits(max_files=4, max_symbols=8, max_tokens=8, max_chars=1000),
    )

    assert profile.languages == ["python"]
    assert "src/requests" in profile.source_roots
    assert "src/requests/sessions.py" in profile.important_files
    assert "Session" in profile.symbols
    assert "cookies" in profile.tokens
    assert profile.profile_hash.startswith("sha256:")
    assert profile.truncated is False


def test_profile_respects_character_budget(tmp_path: Path) -> None:
    store = _store(tmp_path)
    for index in range(20):
        path = f"src/pkg/module_{index}.py"
        store.upsert_source_file(_source(path))
        store.replace_chunks(
            Path(path),
            [_chunk(f"c{index}", path, "content", [f"Symbol{index}"])],
        )

    profile = build_repo_profile(
        store,
        limits=RepoProfileLimits(max_files=20, max_symbols=20, max_tokens=20, max_chars=260),
    )

    assert profile.truncated is True
    assert (
        len(json.dumps(repo_profile_payload(profile), ensure_ascii=False, sort_keys=True))
        <= 260
    )


def test_term_support_rejects_unrelated_framework_terms(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.upsert_source_file(_source("src/requests/sessions.py"))
    store.replace_chunks(
        Path("src/requests/sessions.py"),
        [_chunk("c1", "src/requests/sessions.py", "class Session: pass", ["Session"])],
    )
    profile = build_repo_profile(store)
    vocabulary = profile_vocabulary(profile)

    assert (
        rewritten_query_is_repo_supported(
            "persisted client session cookies",
            vocabulary,
            original_tokens=["client", "session", "cookies"],
        )
        == "client session cookies"
    )
    assert term_is_repo_supported("Session cookies", vocabulary)
    assert not term_is_repo_supported("Spring HttpSession cookies", vocabulary)
