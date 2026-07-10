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
    assert "total=" in result.output
    assert "passed=" in result.output
    assert "failed=" in result.output


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
    assert "total=1" in result.output
    assert "passed=0" in result.output
    assert "failed=1" in result.output


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
        ],
    )

    assert result.exit_code == 0
    assert output.exists()
    output_text = output.read_text(encoding="utf-8")
    assert output_text.endswith("\n")
    assert output_text.startswith("{\n  ")
    assert "sample/目标" in output_text
    comparison = json.loads(output_text)
    assert comparison["schema_version"] == 1
    assert comparison["aggregate"]["total"] == 2
    assert comparison["aggregate"]["regressed"] == 1
    assert comparison["aggregate"]["improved"] == 1
    assert comparison["cases"][0] == {
        "case_key": "sample/recovered",
        "classification": "improved",
        "baseline_status": "fail",
        "candidate_status": "pass",
        "warnings": [],
    }
    assert comparison["cases"][1] == {
        "case_key": "sample/目标",
        "classification": "regressed",
        "baseline_status": "pass",
        "candidate_status": "fail",
        "warnings": [],
    }
    assert "regressed=" in result.output
    assert "improved=" in result.output
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
