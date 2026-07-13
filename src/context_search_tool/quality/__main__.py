from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer

from context_search_tool.quality.compare import compare_reports
from context_search_tool.quality.feedback import summarize_feedback_log
from context_search_tool.quality.reports import render_markdown_comparison
from context_search_tool.quality.runner import (
    _publish_artifacts,
    _validate_artifact_destinations,
    run_quality_fixture,
)

quality_app = typer.Typer(
    help="Retrieval quality evaluation tools",
    no_args_is_help=True,
)


def _ensure_parent(path: Path | None) -> None:
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)


@quality_app.command()
def run(
    fixture: Path = typer.Argument(...),
    profile: str = typer.Option("ci", "--profile"),
    output: Path = typer.Option(..., "--output"),
    markdown: Optional[Path] = typer.Option(None, "--markdown"),
    allow_empty: bool = typer.Option(False, "--allow-empty"),
) -> None:
    report = run_quality_fixture(
        fixture,
        profile=profile,
        output_path=output,
        markdown_path=markdown,
        allow_empty=allow_empty,
    )
    aggregate = report.get("aggregate", {})
    typer.echo(
        "selected={selected} executed={executed} passed={passed} "
        "failed={failed} errors={errors}".format(
            selected=aggregate.get("selected", 0),
            executed=aggregate.get("executed", 0),
            passed=aggregate.get("passed", 0),
            failed=aggregate.get("failed", 0),
            errors=aggregate.get("errors", 0),
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
    allow_regressions: bool = typer.Option(False, "--allow-regressions"),
) -> None:
    baseline_report = json.loads(baseline.read_text(encoding="utf-8"))
    candidate_report = json.loads(candidate.read_text(encoding="utf-8"))
    comparison = compare_reports(baseline_report, candidate_report)
    _validate_artifact_destinations(
        [path for path in (output, markdown) if path is not None]
    )
    _ensure_parent(output)
    _ensure_parent(markdown)
    artifacts = [
        (output, json.dumps(comparison, indent=2, ensure_ascii=False) + "\n")
    ]
    if markdown is not None:
        artifacts.append((markdown, render_markdown_comparison(comparison)))
    _publish_artifacts(artifacts)
    aggregate = comparison.get("aggregate", {})
    typer.echo(
        "gating_regressions={gating} improvements={improvements} "
        "observed_declines={declines}".format(
            gating=aggregate.get("gating_regressions", 0),
            improvements=aggregate.get("improvements", 0),
            declines=aggregate.get("observed_declines", 0),
        )
    )
    if aggregate.get("gating_regressions", 0) > 0 and not allow_regressions:
        raise typer.Exit(code=1)


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
    _ensure_parent(output)
    _publish_artifacts(
        [(output, json.dumps(summary, indent=2, ensure_ascii=False) + "\n")]
    )
    typer.echo(f"Feedback summary complete: total={summary['total_calls']}")


if __name__ == "__main__":
    quality_app()
