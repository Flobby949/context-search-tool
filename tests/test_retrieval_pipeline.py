from pathlib import Path

from context_search_tool.config import DEFAULT_CONFIG
from context_search_tool.indexer import index_repository
from context_search_tool.retrieval import query_repository


def test_query_combines_route_tokens_and_ranking_reasons(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "ApplyAuditController.java").write_text(
        '''
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;

@RequestMapping("/apply/audit")
class ApplyAuditController {
  @PostMapping("/pageEs")
  String pageEs() { return "ok"; }
}
'''.strip(),
        encoding="utf-8",
    )
    index_repository(repo, DEFAULT_CONFIG)

    bundle = query_repository(repo, "/apply/audit/pageEs INVOLVED_BY_ME", DEFAULT_CONFIG)

    assert bundle.results
    assert bundle.results[0].file_path == Path("ApplyAuditController.java")
    assert any("route" in reason.lower() or "lexical" in reason.lower() for reason in bundle.results[0].reasons)
    assert "apply" in bundle.followup_keywords


def test_query_context_lines_override_expands_result(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "Service.java").write_text(
        "line1\nline2\nline3 targetToken\nline4\nline5\n",
        encoding="utf-8",
    )
    index_repository(repo, DEFAULT_CONFIG)

    bundle = query_repository(repo, "targetToken", DEFAULT_CONFIG, context_lines=1)

    assert "line2" in bundle.results[0].content
    assert "line4" in bundle.results[0].content


def test_full_file_respects_size_limit(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "Small.java").write_text("class Small { String targetToken; }\n", encoding="utf-8")
    index_repository(repo, DEFAULT_CONFIG)

    bundle = query_repository(repo, "targetToken", DEFAULT_CONFIG, full_file=True)

    assert bundle.results[0].content.startswith("class Small")
