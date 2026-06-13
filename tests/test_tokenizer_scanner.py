from dataclasses import replace
from pathlib import Path

import pytest

from context_search_tool import scanner
from context_search_tool.config import DEFAULT_CONFIG
from context_search_tool.scanner import scan_workspace
from context_search_tool.tokenizer import tokenize_identifier, tokenize_query


def test_identifier_tokenizer_splits_common_code_shapes() -> None:
    assert tokenize_identifier("PageAppCatalogQueryExe") == [
        "page",
        "app",
        "catalog",
        "query",
        "exe",
    ]
    assert tokenize_identifier("canApply") == ["can", "apply"]
    assert tokenize_identifier("app_org_region_code") == ["app", "org", "region", "code"]
    assert tokenize_identifier("/apply/audit/pageEs") == ["apply", "audit", "page", "es"]


def test_query_tokenizer_keeps_code_like_terms() -> None:
    tokens = tokenize_query('/apply/audit/pageEs INVOLVED_BY_ME 为什么跨区域')
    assert "apply" in tokens
    assert "audit" in tokens
    assert "page" in tokens
    assert "es" in tokens
    assert "involved" in tokens
    assert "region" not in tokens


def test_scanner_respects_gitignore_and_context_search(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".gitignore").write_text("ignored.java\n", encoding="utf-8")
    (repo / "A.java").write_text("class A {}\n", encoding="utf-8")
    (repo / "ignored.java").write_text("class Ignored {}\n", encoding="utf-8")
    (repo / ".context-search").mkdir()
    (repo / ".context-search" / "index.sqlite").write_text("x", encoding="utf-8")

    files = scan_workspace(repo, DEFAULT_CONFIG)

    assert [item.path for item in files] == [Path("A.java")]
    assert files[0].language == "java"
    assert files[0].size > 0
    assert len(files[0].sha256) == 64


def test_scanner_returns_files_sorted_by_relative_path(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    nested = repo / "a"
    nested.mkdir()
    (repo / "b.java").write_text("class B {}\n", encoding="utf-8")
    (nested / "c.java").write_text("class C {}\n", encoding="utf-8")

    files = scan_workspace(repo, DEFAULT_CONFIG)

    assert [item.path for item in files] == [Path("a/c.java"), Path("b.java")]


def test_scanner_skips_unreadable_candidate_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    readable = repo / "Readable.java"
    unreadable = repo / "Unreadable.java"
    readable.write_text("class Readable {}\n", encoding="utf-8")
    unreadable.write_text("class Unreadable {}\n", encoding="utf-8")
    original_read_bytes = Path.read_bytes

    def read_bytes(path: Path) -> bytes:
        if path == unreadable:
            raise PermissionError("cannot read")
        return original_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", read_bytes)

    files = scan_workspace(repo, DEFAULT_CONFIG)

    assert [item.path for item in files] == [Path("Readable.java")]


def test_scanner_prunes_ignored_and_excluded_directories(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".gitignore").write_text("ignored/\n", encoding="utf-8")
    (repo / "A.java").write_text("class A {}\n", encoding="utf-8")
    ignored = repo / "ignored"
    ignored.mkdir()
    (ignored / "Ignored.java").write_text("class Ignored {}\n", encoding="utf-8")
    excluded = repo / "excluded"
    excluded.mkdir()
    (excluded / "Excluded.java").write_text("class Excluded {}\n", encoding="utf-8")
    original_walk = scanner.os.walk

    def walk(path: Path):
        for dirpath, dirnames, filenames in original_walk(path):
            if Path(dirpath) in {ignored, excluded}:
                raise AssertionError("ignored or excluded directory was descended into")
            yield dirpath, dirnames, filenames

    monkeypatch.setattr(scanner.os, "walk", walk)
    config = replace(
        DEFAULT_CONFIG,
        index=replace(DEFAULT_CONFIG.index, exclude=["excluded/"]),
    )

    files = scan_workspace(repo, config)

    assert [item.path for item in files] == [Path("A.java")]
