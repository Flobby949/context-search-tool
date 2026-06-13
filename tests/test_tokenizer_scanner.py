from pathlib import Path

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
