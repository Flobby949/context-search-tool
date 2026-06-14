import json
from pathlib import Path

from typer.testing import CliRunner

from context_search_tool.cli import app
from context_search_tool.sqlite_store import SQLiteStore


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


def test_query_warns_when_signal_schema_is_stale(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "App.java").write_text("class App {}\n", encoding="utf-8")
    runner = CliRunner()
    index_result = runner.invoke(app, ["index", str(repo)])
    assert index_result.exit_code == 0
    store = SQLiteStore(repo / ".context-search" / "index.sqlite")
    store.set_metadata("signal_schema_version", "1")

    result = runner.invoke(app, ["query", str(repo), "App"])

    assert result.exit_code == 0
    assert "Warning: index signal schema is older than this version" in result.output


def test_query_rejects_conflicting_planner_flags(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "App.java").write_text("class App {}\n", encoding="utf-8")
    runner = CliRunner()
    assert runner.invoke(app, ["index", str(repo)]).exit_code == 0

    result = runner.invoke(
        app,
        ["query", str(repo), "App", "--planner", "--no-planner"],
    )

    assert result.exit_code == 1
    assert "Error: --planner and --no-planner cannot be used together" in result.output


def test_query_no_planner_overrides_enabled_config(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "App.java").write_text("class App {}\n", encoding="utf-8")
    runner = CliRunner()
    assert runner.invoke(app, ["index", str(repo)]).exit_code == 0
    config_path = repo / ".context-search" / "config.toml"
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace(
            "enabled = false",
            "enabled = true",
        ),
        encoding="utf-8",
    )

    result = runner.invoke(app, ["query", str(repo), "App", "--json", "--no-planner"])

    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["planner"]["status"] == "disabled"


def test_index_reports_embedding_config_errors_without_traceback(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "Service.java").write_text("class Service {}\n", encoding="utf-8")
    config_dir = repo / ".context-search"
    config_dir.mkdir()
    (config_dir / "config.toml").write_text(
        """
[index]
include = []
exclude = []
max_file_bytes = 500000
max_full_file_bytes = 200000

[retrieval]
semantic_top_k = 80
lexical_top_k = 80
final_top_k = 12
context_before_lines = 8
context_after_lines = 12

[embedding]
provider = "openai-compatible"
model = "text-embedding"
dimensions = 3
""".lstrip(),
        encoding="utf-8",
    )
    runner = CliRunner()

    result = runner.invoke(app, ["index", str(repo)])

    assert result.exit_code == 1
    assert "Error: base_url is required" in result.output
    assert "Traceback" not in result.output


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
