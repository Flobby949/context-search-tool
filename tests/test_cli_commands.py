import json
from pathlib import Path

from typer.testing import CliRunner

from context_search_tool.cli import app


def test_cli_index_query_stats_explain_and_clean(
    tmp_path: Path, monkeypatch
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    source = repo / "ApplyAuditController.java"
    source.write_text(
        '''
import org.springframework.web.bind.annotation.PostMapping;

class ApplyAuditController {
  @PostMapping("/apply/audit/pageEs")
  String pageEs() { return "ok"; }
}
'''.strip(),
        encoding="utf-8",
    )
    runner = CliRunner()

    index_result = runner.invoke(app, ["index", str(repo)])
    assert index_result.exit_code == 0
    assert "indexed" in index_result.output.lower()

    query_result = runner.invoke(app, ["query", str(repo), "/apply/audit/pageEs", "--json"])
    assert query_result.exit_code == 0
    parsed = json.loads(query_result.output)
    assert parsed["results"]

    stats_result = runner.invoke(app, ["stats", str(repo)])
    assert stats_result.exit_code == 0
    assert "Total chunks" in stats_result.output

    explain_result = runner.invoke(
        app, ["explain", str(repo), "ApplyAuditController.java:4"]
    )
    assert explain_result.exit_code == 0
    assert "ApplyAuditController.java" in explain_result.output

    monkeypatch.chdir(repo)
    cwd_query_result = runner.invoke(app, ["query", "/apply/audit/pageEs"])
    assert cwd_query_result.exit_code == 0
    assert "ApplyAuditController.java" in cwd_query_result.output

    clean_result = runner.invoke(app, ["clean", str(repo)])
    assert clean_result.exit_code == 0
    assert not (repo / ".context-search").exists()


def test_query_missing_index_does_not_create_artifacts(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    runner = CliRunner()

    result = runner.invoke(app, ["query", str(repo), "anything"])

    _assert_missing_index_error(result.output, result.exit_code, repo)


def test_stats_missing_index_does_not_create_artifacts(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    runner = CliRunner()

    result = runner.invoke(app, ["stats", str(repo)])

    _assert_missing_index_error(result.output, result.exit_code, repo)


def test_explain_missing_index_does_not_create_artifacts(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    runner = CliRunner()

    result = runner.invoke(app, ["explain", str(repo), "Missing.java:1"])

    _assert_missing_index_error(result.output, result.exit_code, repo)


def _assert_missing_index_error(output: str, exit_code: int, repo: Path) -> None:
    assert exit_code != 0
    lowered = output.lower()
    assert "missing index" in lowered or "not indexed" in lowered
    assert not (repo / ".context-search").exists()
