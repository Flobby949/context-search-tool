import json
from dataclasses import replace
from pathlib import Path

import pytest
from typer.testing import CliRunner

from context_search_tool import cli, context_pack
from context_search_tool.cli import app
from context_search_tool.config import (
    IndexConfig,
    QueryPlannerConfig,
    RetrievalConfig,
    ToolConfig,
    render_config,
)
from context_search_tool.context_pack import (
    INVALID_REFERENCE_ERROR,
    UNEXPECTED_CONTEXT_ERROR,
    ContextPackError,
    ContextPackOptions,
)
from context_search_tool.models import RetrievalResult
from context_search_tool.retrieval import QueryBundle
from context_search_tool.sqlite_store import SQLiteStore


def _indexed_repo(tmp_path: Path) -> tuple[Path, CliRunner]:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "AppController.py").write_text(
        "def app():\n    return 'ok'\n",
        encoding="utf-8",
    )
    runner = CliRunner()
    assert runner.invoke(app, ["index", str(repo)]).exit_code == 0
    return repo, runner


def _context_bundle(query: str = "AppController") -> QueryBundle:
    return QueryBundle(
        query=query,
        expanded_tokens=[query.lower()],
        results=[
            RetrievalResult(
                file_path=Path("AppController.py"),
                start_line=1,
                end_line=2,
                content="def app():\n    return 'ok'",
                score=0.9,
                score_parts={"evidence_priority": 0.0, "lexical": 0.8},
                reasons=["lexical match"],
                followup_keywords=["app"],
            )
        ],
        followup_keywords=["app"],
    )


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

    context_result = runner.invoke(
        app,
        ["context", str(repo), "/apply/audit/pageEs", "--json"],
    )
    assert context_result.exit_code == 0
    context_payload = json.loads(context_result.output)
    assert context_payload["context_pack"]["schema_version"] == 1
    assert context_payload["results"] == parsed["results"]

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

    cwd_context_result = runner.invoke(app, ["context", "/apply/audit/pageEs"])
    assert cwd_context_result.exit_code == 0
    assert "# Context Pack" in cwd_context_result.output
    assert "ApplyAuditController.java" in cwd_context_result.output

    clean_result = runner.invoke(app, ["clean", str(repo)])
    assert clean_result.exit_code == 0
    assert not (repo / ".context-search").exists()


def test_query_json_preserves_complete_pre_refactor_payload(
    tmp_path: Path, monkeypatch
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "App.py").write_text("def app():\n    pass\n", encoding="utf-8")
    runner = CliRunner()
    assert runner.invoke(app, ["index", str(repo)]).exit_code == 0
    bundle = QueryBundle(
        query="compatibility",
        expanded_tokens=["compatibility"],
        results=[
            RetrievalResult(
                file_path=Path("App.py"),
                start_line=1,
                end_line=2,
                content="def app():\n    pass",
                score=0.75,
                score_parts={"lexical": 0.5},
                reasons=["lexical match"],
                followup_keywords=["app"],
            )
        ],
        followup_keywords=["app"],
    )
    monkeypatch.setattr(cli, "query_repository", lambda *args, **kwargs: bundle)

    result = runner.invoke(app, ["query", str(repo), "compatibility", "--json"])

    assert result.exit_code == 0
    assert json.loads(result.output) == {
        "evidence_anchors": [],
        "expanded_tokens": ["compatibility"],
        "followup_keywords": ["app"],
        "planner": {
            "enabled": False,
            "latency_ms": None,
            "model": "",
            "prompt_hash": "",
            "prompt_version": "",
            "provider": "",
            "status": "disabled",
        },
        "query": "compatibility",
        "query_variants": [],
        "results": [
            {
                "content": "def app():\n    pass",
                "end_line": 2,
                "file_path": "App.py",
                "followup_keywords": ["app"],
                "reasons": ["lexical match"],
                "score": 0.75,
                "score_parts": {"lexical": 0.5},
                "semantic_matches": [],
                "start_line": 1,
            }
        ],
        "summary": {
            "entry_points": [],
            "implementation": [],
            "possibly_legacy": [],
            "related_types": [],
        },
        "variant_retrieval_status": "original_only",
    }


@pytest.mark.parametrize("command", ["query", "context"])
def test_query_and_context_missing_index_do_not_create_artifacts(
    tmp_path: Path,
    command: str,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    runner = CliRunner()

    result = runner.invoke(app, [command, str(repo), "anything"])

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


@pytest.mark.parametrize("command", ["query", "context"])
def test_query_and_context_reject_conflicting_planner_flags(
    tmp_path: Path,
    command: str,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "App.java").write_text("class App {}\n", encoding="utf-8")
    runner = CliRunner()
    assert runner.invoke(app, ["index", str(repo)]).exit_code == 0

    result = runner.invoke(
        app,
        [command, str(repo), "App", "--planner", "--no-planner"],
    )

    assert result.exit_code == 1
    assert result.output == (
        "Error: --planner and --no-planner cannot be used together\n"
    )


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


@pytest.mark.parametrize(
    ("flag", "configured_enabled", "expected_enabled"),
    [
        ("--planner", False, True),
        ("--no-planner", True, False),
    ],
)
def test_context_passes_query_flags_and_resolves_pack_options(
    tmp_path: Path,
    monkeypatch,
    flag: str,
    configured_enabled: bool,
    expected_enabled: bool,
) -> None:
    repo, runner = _indexed_repo(tmp_path)
    config = ToolConfig(
        index=IndexConfig(max_full_file_bytes=123_456),
        retrieval=RetrievalConfig(
            final_top_k=6,
            context_before_lines=8,
            context_after_lines=12,
        ),
        query_planner=QueryPlannerConfig(enabled=configured_enabled),
    )
    (repo / ".context-search" / "config.toml").write_text(
        render_config(config),
        encoding="utf-8",
    )
    captured: dict[str, object] = {}

    def fake_query(repo_arg, query_text, config_arg, **kwargs):
        captured["query"] = (repo_arg, query_text, config_arg, kwargs)
        return _context_bundle(query_text)

    def fake_build(bundle, options):
        captured["bundle"] = bundle
        captured["options"] = options
        return context_pack.build_context_pack(bundle, options)

    monkeypatch.setattr(cli, "query_repository", fake_query)
    monkeypatch.setattr(cli, "build_context_pack", fake_build, raising=False)

    result = runner.invoke(
        app,
        [
            "context",
            str(repo),
            "AppController",
            "--json",
            "--context-lines",
            "5",
            "--full-file",
            flag,
        ],
    )

    assert result.exit_code == 0
    repo_arg, query_text, effective_config, query_kwargs = captured["query"]
    assert repo_arg == repo
    assert query_text == "AppController"
    assert effective_config.query_planner.enabled is expected_enabled
    assert query_kwargs == {"context_lines": 5, "full_file": True}
    assert captured["bundle"].query == "AppController"
    assert captured["options"] == ContextPackOptions(
        max_results=6,
        max_evidence_anchors=2,
        context_before_lines=5,
        context_after_lines=5,
        full_file=True,
        max_full_file_bytes=123_456,
    )


def test_context_calls_query_and_builder_once_while_query_never_builds(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo, runner = _indexed_repo(tmp_path)
    counts = {"query": 0, "build": 0}

    def fake_query(*args, **kwargs):
        counts["query"] += 1
        return _context_bundle()

    def fake_build(bundle, options):
        counts["build"] += 1
        return context_pack.build_context_pack(bundle, options)

    monkeypatch.setattr(cli, "query_repository", fake_query)
    monkeypatch.setattr(cli, "build_context_pack", fake_build, raising=False)

    context_result = runner.invoke(
        app,
        ["context", str(repo), "AppController", "--json"],
    )

    assert context_result.exit_code == 0
    assert counts == {"query": 1, "build": 1}

    query_result = runner.invoke(
        app,
        ["query", str(repo), "AppController", "--json"],
    )

    assert query_result.exit_code == 0
    assert counts == {"query": 2, "build": 1}


def test_context_defaults_to_markdown_and_json_is_structured(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo, runner = _indexed_repo(tmp_path)
    monkeypatch.setattr(
        cli,
        "query_repository",
        lambda *args, **kwargs: _context_bundle(),
    )

    markdown_result = runner.invoke(app, ["context", str(repo), "AppController"])
    json_result = runner.invoke(
        app,
        ["context", str(repo), "AppController", "--json"],
    )

    assert markdown_result.exit_code == 0
    assert markdown_result.output.startswith("# Context Pack\n")
    assert "AppController.py:1-2" in markdown_result.output
    assert json_result.exit_code == 0
    payload = json.loads(json_result.output)
    assert payload["results"][0]["file_path"] == "AppController.py"
    assert payload["context_pack"]["schema_version"] == 1
    assert payload["context_pack"]["reading_order"] == ["result:0"]


def test_context_empty_bundle_succeeds_in_json_and_markdown(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo, runner = _indexed_repo(tmp_path)
    empty_bundle = QueryBundle(
        query="missing",
        expanded_tokens=[],
        results=[],
        followup_keywords=[],
    )
    monkeypatch.setattr(
        cli,
        "query_repository",
        lambda *args, **kwargs: empty_bundle,
    )

    json_result = runner.invoke(
        app,
        ["context", str(repo), "missing", "--json"],
    )
    markdown_result = runner.invoke(app, ["context", str(repo), "missing"])

    assert json_result.exit_code == 0
    payload = json.loads(json_result.output)
    assert payload["results"] == []
    assert payload["context_pack"]["status"] == "empty"
    assert payload["context_pack"]["missing_evidence"] == [
        {
            "category": "results",
            "required": True,
            "reason": (
                "no result or evidence anchor is present in the bounded result set"
            ),
        }
    ]
    assert payload["context_pack"]["next_queries"] == []
    assert markdown_result.exit_code == 0
    assert "Status: empty" in markdown_result.output
    assert "## Read First\n- (none)" in markdown_result.output


@pytest.mark.parametrize(
    ("error", "expected_message"),
    [
        (
            ContextPackError("invalid ContextPack classification"),
            "invalid ContextPack classification",
        ),
        (ValueError("secret"), UNEXPECTED_CONTEXT_ERROR),
        (RuntimeError("secret"), UNEXPECTED_CONTEXT_ERROR),
    ],
)
def test_context_maps_builder_failures_to_bounded_errors(
    tmp_path: Path,
    monkeypatch,
    error: Exception,
    expected_message: str,
) -> None:
    repo, runner = _indexed_repo(tmp_path)
    monkeypatch.setattr(
        cli,
        "query_repository",
        lambda *args, **kwargs: _context_bundle(),
    )

    def failing_builder(*args, **kwargs):
        raise error

    monkeypatch.setattr(cli, "build_context_pack", failing_builder, raising=False)

    result = runner.invoke(
        app,
        ["context", str(repo), "AppController", "--json"],
    )

    assert result.exit_code == 1
    assert result.output == f"Error: context_failed: {expected_message}\n"
    assert "secret" not in result.output


def test_context_maps_invalid_markdown_reference_to_exact_error(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo, runner = _indexed_repo(tmp_path)
    bundle = _context_bundle()
    monkeypatch.setattr(cli, "query_repository", lambda *args, **kwargs: bundle)

    def invalid_builder(bundle_arg, options):
        pack = context_pack.build_context_pack(bundle_arg, options)
        return replace(pack, reading_order=(*pack.reading_order, "result:999"))

    monkeypatch.setattr(cli, "build_context_pack", invalid_builder, raising=False)

    result = runner.invoke(app, ["context", str(repo), "AppController"])

    assert result.exit_code == 1
    assert result.output == f"Error: context_failed: {INVALID_REFERENCE_ERROR}\n"


def test_context_hides_json_encoding_error_details(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo, runner = _indexed_repo(tmp_path)
    monkeypatch.setattr(
        cli,
        "query_repository",
        lambda *args, **kwargs: _context_bundle(),
    )

    def failing_formatter(*args, **kwargs):
        raise TypeError("secret")

    monkeypatch.setattr(cli, "format_context_json", failing_formatter, raising=False)

    result = runner.invoke(
        app,
        ["context", str(repo), "AppController", "--json"],
    )

    assert result.exit_code == 1
    assert result.output == (
        f"Error: context_failed: {UNEXPECTED_CONTEXT_ERROR}\n"
    )
    assert "secret" not in result.output


def test_context_query_phase_value_error_keeps_existing_error_contract(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo, runner = _indexed_repo(tmp_path)

    def failing_query(*args, **kwargs):
        raise ValueError("invalid query input")

    monkeypatch.setattr(cli, "query_repository", failing_query)

    result = runner.invoke(
        app,
        ["context", str(repo), "AppController", "--json"],
    )

    assert result.exit_code == 1
    assert result.output == "Error: invalid query input\n"
    assert "context_failed" not in result.output


def test_context_help_has_query_output_controls_without_tuning_flags() -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["context", "--help"])

    assert result.exit_code == 0
    for option in (
        "--json",
        "--context-lines",
        "--full-file",
        "--planner",
        "--no-planner",
    ):
        assert option in result.output
    assert "--final-top-k" not in result.output
    assert "--context-top-k" not in result.output


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
