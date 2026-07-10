from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer

from context_search_tool.quality.compare import compare_reports
from context_search_tool.quality.feedback import summarize_feedback_log
from context_search_tool.quality.reports import render_markdown_comparison
from context_search_tool.quality.runner import run_quality_fixture

quality_app = typer.Typer(
    help="Retrieval quality evaluation tools",
    no_args_is_help=True,
)


@quality_app.command()
def run(
    fixture: Path = typer.Argument(...),
    profile: str = typer.Option("ci", "--profile"),
    output: Path = typer.Option(..., "--output"),
    markdown: Optional[Path] = typer.Option(None, "--markdown"),
) -> None:
    report = run_quality_fixture(
        fixture,
        profile=profile,
        output_path=output,
        markdown_path=markdown,
    )
    aggregate = report.get("aggregate", {})
    typer.echo(
        "total={total} passed={passed} failed={failed}".format(
            total=aggregate.get("total", 0),
            passed=aggregate.get("passed", 0),
            failed=aggregate.get("failed", 0),
        )
    )
    if aggregate.get("failed", 0) > 0 or aggregate.get("errors", 0) > 0:
        raise typer.Exit(code=1)


@quality_app.command()
def compare(
    baseline: Path = typer.Option(..., "--baseline"),
    candidate: Path = typer.Option(..., "--candidate"),
    output: Path = typer.Option(..., "--output"),
    markdown: Optional[Path] = typer.Option(None, "--markdown"),
) -> None:
    baseline_report = json.loads(baseline.read_text(encoding="utf-8"))
    candidate_report = json.loads(candidate.read_text(encoding="utf-8"))
    comparison = compare_reports(baseline_report, candidate_report)
    output.write_text(
        json.dumps(comparison, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    if markdown is not None:
        markdown.write_text(
            render_markdown_comparison(comparison),
            encoding="utf-8",
        )
    aggregate = comparison.get("aggregate", {})
    typer.echo(
        "regressed={regressed} improved={improved}".format(
            regressed=aggregate.get("regressed", 0),
            improved=aggregate.get("improved", 0),
        )
    )


@quality_app.command("feedback")
def feedback(
    log_path: Path = typer.Argument(...),
    output: Path = typer.Option(..., "--output"),
    include_query_terms: bool = typer.Option(False, "--include-query-terms"),
    include_query_examples: bool = typer.Option(False, "--include-query-examples"),
) -> None:
    summary = summarize_feedback_log(
        log_path,
        include_query_terms=include_query_terms,
        include_query_examples=include_query_examples,
    )
    output.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    typer.echo(f"Feedback summary complete: total={summary['total_calls']}")


if __name__ == "__main__":
    quality_app()
