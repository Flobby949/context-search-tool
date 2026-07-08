import json
from pathlib import Path

from typer.testing import CliRunner

from context_search_tool.quality.__main__ import quality_app
from context_search_tool.quality.feedback import summarize_feedback_log


def _write_jsonl(path: Path, events: list[dict]) -> None:
    path.write_text(
        "\n".join(json.dumps(event) for event in events) + "\n",
        encoding="utf-8",
    )


def test_feedback_summary_redacts_queries_by_default(tmp_path: Path) -> None:
    log = tmp_path / "feedback.jsonl"
    _write_jsonl(
        log,
        [
            {
                "ok": True,
                "query": "secret customer endpoint",
                "result_count": 2,
                "top_score": 3.0,
            },
            {
                "ok": False,
                "query": "another secret",
                "error_code": "boom",
                "result_count": 0,
            },
        ],
    )

    summary = summarize_feedback_log(log)

    assert summary["total_calls"] == 2
    assert summary["ok_calls"] == 1
    assert summary["error_calls"] == 1
    assert summary["empty_result_calls"] == 1
    assert "queries" not in summary
    assert "query_terms" not in summary


def test_feedback_summary_can_include_terms_when_explicit(tmp_path: Path) -> None:
    log = tmp_path / "feedback.jsonl"
    _write_jsonl(log, [{"ok": True, "query": "alpha alpha beta"}])

    summary = summarize_feedback_log(log, include_query_terms=True)

    assert summary["query_terms"]["alpha"] == 2
    assert summary["query_terms"]["beta"] == 1


def test_feedback_cli_writes_redacted_summary(tmp_path: Path) -> None:
    log = tmp_path / "feedback.jsonl"
    output = tmp_path / "summary.json"
    _write_jsonl(
        log,
        [
            {
                "ok": True,
                "query": "secret customer endpoint",
                "result_count": 2,
            }
        ],
    )
    runner = CliRunner()

    result = runner.invoke(
        quality_app,
        ["feedback", str(log), "--output", str(output)],
    )

    assert result.exit_code == 0
    output_text = output.read_text(encoding="utf-8")
    assert output_text.endswith("\n")
    summary = json.loads(output_text)
    assert summary["total_calls"] == 1
    assert "queries" not in summary
    assert "query_terms" not in summary
    assert "Feedback summary complete: total=1" in result.output
