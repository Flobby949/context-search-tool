import json
from pathlib import Path

from typer.testing import CliRunner

from context_search_tool.cli import app


def _write_source_repo(tmp_path: Path) -> Path:
    source = tmp_path / "source"
    source.mkdir()
    (source / "App.java").write_text(
        """
        class App {
            String targetToken() {
                return "targetToken";
            }
        }
        """,
        encoding="utf-8",
    )
    return source


def _write_fixture(
    tmp_path: Path,
    source: Path,
    expected_path: str = "App.java",
) -> Path:
    fixture = tmp_path / "quality.json"
    fixture.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "repos": [
                    {
                        "repo_key": "sample",
                        "snapshot_path": str(source),
                        "profiles": ["ci"],
                        "queries": [
                            {
                                "id": "target",
                                "query": "targetToken",
                                "expected_top_k": [
                                    {"path": expected_path, "top_k": 5}
                                ],
                            }
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return fixture


def _case(case_id: str, status: str) -> dict:
    return {
        "repo_key": "sample",
        "case_id": case_id,
        "status": status,
        "metrics": {},
    }


def _minimal_report(cases: list[dict] | None = None) -> dict:
    return {
        "schema_version": 1,
        "fixture": {"sha256": "sha256:fixture"},
        "profile": "ci",
        "config": {"config_hash": "sha256:config"},
        "repos": [],
        "cases": cases or [],
    }


def test_quality_run_cli_writes_report(tmp_path: Path) -> None:
    source = _write_source_repo(tmp_path)
    fixture = _write_fixture(tmp_path, source)
    output = tmp_path / "quality-report.json"
    runner = CliRunner()

    result = runner.invoke(
        app,
        ["quality", "run", str(fixture), "--profile", "ci", "--output", str(output)],
    )

    assert result.exit_code == 0
    assert output.exists()
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["aggregate"]["passed"] == 1
    assert result.output == (
        "selected=1 executed=1 passed=1 failed=0 errors=0\n"
    )


def test_quality_run_cli_exits_nonzero_when_fixture_fails(tmp_path: Path) -> None:
    source = _write_source_repo(tmp_path)
    fixture = _write_fixture(tmp_path, source, expected_path="Missing.java")
    output = tmp_path / "quality-report.json"
    runner = CliRunner()

    result = runner.invoke(
        app,
        ["quality", "run", str(fixture), "--profile", "ci", "--output", str(output)],
    )

    assert result.exit_code == 1
    assert output.exists()
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["aggregate"]["failed"] == 1
    assert result.output == (
        "selected=1 executed=1 passed=0 failed=1 errors=0\n"
    )


def test_quality_compare_cli_writes_comparison(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.json"
    candidate = tmp_path / "candidate.json"
    output = tmp_path / "comparison.json"
    markdown = tmp_path / "comparison.md"
    baseline.write_text(
        json.dumps(
            _minimal_report(
                [
                    _case("目标", "pass"),
                    _case("recovered", "fail"),
                ]
            )
        ),
        encoding="utf-8",
    )
    candidate.write_text(
        json.dumps(
            _minimal_report(
                [
                    _case("目标", "fail"),
                    _case("recovered", "pass"),
                ]
            )
        ),
        encoding="utf-8",
    )
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "quality",
            "compare",
            "--baseline",
            str(baseline),
            "--candidate",
            str(candidate),
            "--output",
            str(output),
            "--markdown",
            str(markdown),
            "--allow-regressions",
        ],
    )

    assert result.exit_code == 0
    assert output.exists()
    output_text = output.read_text(encoding="utf-8")
    assert output_text.endswith("\n")
    assert output_text.startswith("{\n  ")
    assert "sample/目标" in output_text
    comparison = json.loads(output_text)
    assert comparison["schema_version"] == 2
    assert comparison["aggregate"]["total"] == 2
    assert comparison["aggregate"]["gating_regressions"] == 1
    assert comparison["aggregate"]["improvements"] == 1
    assert comparison["cases"] == [
        {
            "case_key": "sample/recovered",
            "classification": "improved",
            "gating": False,
            "baseline_gate": "required",
            "candidate_gate": "required",
            "baseline_status": "fail",
            "candidate_status": "pass",
            "metric_deltas": {},
            "warnings": [],
        },
        {
            "case_key": "sample/目标",
            "classification": "regressed",
            "gating": True,
            "baseline_gate": "required",
            "candidate_gate": "required",
            "baseline_status": "pass",
            "candidate_status": "fail",
            "metric_deltas": {},
            "warnings": [],
        },
    ]
    assert result.output == (
        "gating_regressions=1 improvements=1 observed_declines=0\n"
    )
    assert markdown.read_text(encoding="utf-8").startswith(
        "# Retrieval Quality Comparison"
    )


def test_quality_run_cli_writes_markdown(tmp_path: Path) -> None:
    source = _write_source_repo(tmp_path)
    fixture = _write_fixture(tmp_path, source)
    output = tmp_path / "quality-report.json"
    markdown = tmp_path / "quality.md"
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "quality",
            "run",
            str(fixture),
            "--profile",
            "ci",
            "--output",
            str(output),
            "--markdown",
            str(markdown),
        ],
    )

    assert result.exit_code == 0
    assert markdown.read_text(encoding="utf-8").startswith(
        "# Retrieval Quality Report"
    )


def test_compare_cli_fails_on_gating_regression_unless_allowed(
    tmp_path: Path,
) -> None:
    baseline = tmp_path / "baseline.json"
    candidate = tmp_path / "candidate.json"
    baseline.write_text(
        json.dumps(_minimal_report([_case("target", "pass")])),
        encoding="utf-8",
    )
    candidate.write_text(
        json.dumps(_minimal_report([_case("target", "fail")])),
        encoding="utf-8",
    )
    output = tmp_path / "nested" / "comparison" / "report.json"
    markdown = tmp_path / "nested" / "comparison" / "report.md"
    runner = CliRunner()

    failed = runner.invoke(
        app,
        [
            "quality",
            "compare",
            "--baseline",
            str(baseline),
            "--candidate",
            str(candidate),
            "--output",
            str(output),
            "--markdown",
            str(markdown),
        ],
    )
    allowed = runner.invoke(
        app,
        [
            "quality",
            "compare",
            "--baseline",
            str(baseline),
            "--candidate",
            str(candidate),
            "--output",
            str(output),
            "--markdown",
            str(markdown),
            "--allow-regressions",
        ],
    )

    assert failed.exit_code == 1
    assert output.exists()
    assert markdown.exists()
    assert allowed.exit_code == 0


def test_feedback_cli_creates_nested_output_parent(tmp_path: Path) -> None:
    log = tmp_path / "mcp_calls.jsonl"
    log.write_text('{"ok": true, "result_count": 1}\n', encoding="utf-8")
    output = tmp_path / "nested" / "feedback" / "summary.json"

    result = CliRunner().invoke(
        app,
        ["quality", "feedback", str(log), "--output", str(output)],
    )

    assert result.exit_code == 0
    assert output.exists()


def test_run_cli_rejects_all_skipped_unless_allowed(tmp_path: Path) -> None:
    fixture = tmp_path / "all-skipped.json"
    fixture.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "profile_configs": {
                    "smoke": {
                        "embedding": {
                            "provider": "hash",
                            "model": "hash-v1",
                            "dimensions": 384,
                        },
                        "query_planner": {"enabled": False},
                    }
                },
                "repos": [
                    {
                        "repo_key": "missing",
                        "repo_dir_name": "missing",
                        "profiles": ["smoke"],
                        "queries": [{"id": "q", "query": "q"}],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "nested" / "run" / "report.json"
    runner = CliRunner()

    failed = runner.invoke(
        app,
        [
            "quality",
            "run",
            str(fixture),
            "--profile",
            "smoke",
            "--output",
            str(output),
        ],
    )
    allowed = runner.invoke(
        app,
        [
            "quality",
            "run",
            str(fixture),
            "--profile",
            "smoke",
            "--output",
            str(output),
            "--allow-empty",
        ],
    )

    assert failed.exit_code == 1
    assert output.exists()
    assert json.loads(output.read_text(encoding="utf-8"))["aggregate"][
        "executed"
    ] == 0
    assert allowed.exit_code == 0
    assert allowed.output == (
        "selected=1 executed=0 passed=0 failed=0 errors=0\n"
    )
