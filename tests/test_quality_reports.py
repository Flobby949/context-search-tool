from context_search_tool.quality.reports import (
    render_markdown_comparison,
    render_markdown_report,
)


def test_render_markdown_report_includes_summary_and_prioritized_failures() -> None:
    report = {
        "profile": "ci",
        "aggregate": {
            "selected": 4,
            "attempted": 4,
            "executed": 4,
            "passed": 1,
            "failed": 1,
            "skipped": 0,
            "known_gaps": 1,
            "informational": 0,
            "errors": 1,
            "metrics": {"overall": {}},
        },
        "cases": [
            {
                "repo_key": "sample",
                "case_id": "passes",
                "status": "pass",
                "failures": [],
            },
            {
                "repo_key": "sample",
                "case_id": "gap",
                "status": "known_gap",
                "failures": ["known missing target"],
            },
            {
                "repo_key": "sample",
                "case_id": "fails",
                "status": "fail",
                "failures": ["expected target in top 5"],
            },
            {
                "repo_key": "other",
                "case_id": "errors",
                "status": "error",
                "failures": ["query exploded"],
            },
        ],
    }

    markdown = render_markdown_report(report)

    assert markdown.endswith("\n")
    assert "# Retrieval Quality Report" in markdown
    assert "Profile: `ci`" in markdown
    assert "| selected | 4 |" in markdown
    assert "| executed | 4 |" in markdown
    assert "| known_gaps | 1 |" in markdown
    assert "| total |" not in markdown
    assert "## Failures" in markdown
    assert markdown.index("### sample/fails") < markdown.index("### other/errors")
    assert markdown.index("### sample/fails") < markdown.index("## Known Gaps")
    assert "- expected target in top 5" in markdown
    assert "- query exploded" in markdown
    assert "### sample/gap" in markdown


def test_render_markdown_report_says_when_no_failures_or_known_gaps() -> None:
    markdown = render_markdown_report(
        {
            "profile": "ci",
            "aggregate": {
                "selected": 1,
                "attempted": 1,
                "executed": 1,
                "passed": 1,
                "failed": 0,
                "skipped": 0,
                "known_gaps": 0,
                "informational": 0,
                "errors": 0,
                "metrics": {"overall": {}},
            },
            "cases": [
                {
                    "repo_key": "sample",
                    "case_id": "passes",
                    "status": "pass",
                    "failures": [],
                }
            ],
        }
    )

    assert "No failures." in markdown
    assert "No known gaps." in markdown


def test_markdown_report_renders_metrics_and_reason_only_known_gaps() -> None:
    report = {
        "profile": "ci",
        "aggregate": {
            "selected": 2,
            "attempted": 2,
            "executed": 2,
            "passed": 2,
            "failed": 0,
            "skipped": 0,
            "known_gaps": 0,
            "informational": 0,
            "errors": 0,
            "metrics": {
                "overall": {
                    "mrr": {"count": 2, "mean": 0.75},
                    "hit_at_5": {"successes": 2, "total": 2, "rate": 1.0},
                    "latency_ms": {
                        "count": 2,
                        "mean": 11.5,
                        "p50": 10,
                        "p95": 13,
                    },
                }
            },
        },
        "cases": [
            {
                "repo_key": "sample",
                "case_id": "gap-reason",
                "status": "pass",
                "known_gap_reason": "service chain is incomplete",
                "failures": [],
            }
        ],
    }

    markdown = render_markdown_report(report)

    assert "| executed | 2 |" in markdown
    assert "## Metrics" in markdown
    assert "| mrr.mean | 0.75 |" in markdown
    assert "| hit_at_5.rate | 1.0 |" in markdown
    assert "| latency_ms.p50 | 10 |" in markdown
    assert "### sample/gap-reason" in markdown
    assert "service chain is incomplete" in markdown


def test_render_markdown_comparison_includes_warnings_and_regressions() -> None:
    comparison = {
        "metadata_warnings": ["fixture sha256 differs"],
        "aggregate": {
            "total": 2,
            "gating_regressions": 1,
            "improvements": 0,
            "observed_declines": 0,
            "removed_required": 0,
        },
        "cases": [
            {
                "case_key": "sample/regressed",
                "classification": "regressed",
                "gating": True,
                "baseline_status": "pass",
                "candidate_status": "fail",
                "metric_deltas": {},
                "warnings": ["latency increased by more than 50%"],
            },
            {
                "case_key": "sample/skipped",
                "classification": "skipped",
                "gating": False,
                "baseline_status": "skipped",
                "candidate_status": "skipped",
                "metric_deltas": {},
                "warnings": [],
            },
        ],
        "metric_deltas": {},
    }

    markdown = render_markdown_comparison(comparison)

    assert markdown.endswith("\n")
    assert "# Retrieval Quality Comparison" in markdown
    assert "| gating_regressions | 1 |" in markdown
    assert "## Metadata Warnings" in markdown
    assert "- fixture sha256 differs" in markdown
    assert "## Gating Regressions" in markdown
    assert "### sample/regressed" in markdown
    assert "- latency increased by more than 50%" in markdown


def test_render_markdown_comparison_says_when_no_warnings_or_regressions() -> None:
    markdown = render_markdown_comparison(
        {
            "metadata_warnings": [],
            "aggregate": {
                "total": 1,
                "gating_regressions": 0,
                "improvements": 0,
                "observed_declines": 0,
                "removed_required": 0,
            },
            "cases": [
                {
                    "case_key": "sample/skipped",
                    "classification": "skipped",
                    "gating": False,
                    "baseline_status": "skipped",
                    "candidate_status": "skipped",
                    "metric_deltas": {},
                    "warnings": [],
                }
            ],
            "metric_deltas": {},
        }
    )

    assert "No metadata warnings." in markdown
    assert "No gating regressions." in markdown
    assert "No observed declines." in markdown
    assert "No metric deltas." in markdown


def test_markdown_comparison_orders_gates_declines_deltas_and_warnings() -> None:
    comparison = {
        "aggregate": {
            "total": 2,
            "gating_regressions": 1,
            "improvements": 0,
            "observed_declines": 1,
            "removed_required": 0,
        },
        "cases": [
            {
                "case_key": "sample/weakened",
                "classification": "gate_weakened",
                "gating": True,
                "baseline_status": "pass",
                "candidate_status": "informational",
                "metric_deltas": {},
                "warnings": [],
            },
            {
                "case_key": "sample/observation",
                "classification": "metric_decline",
                "gating": False,
                "baseline_status": "informational",
                "candidate_status": "informational",
                "metric_deltas": {
                    "noise_top12": {"baseline": 1, "candidate": 2, "delta": 1},
                    "latency": {
                        "p95": {"baseline": 10, "candidate": 12, "delta": 2}
                    },
                },
                "warnings": [],
            },
        ],
        "metric_deltas": {
            "overall": {
                "mrr": {"baseline": 0.5, "candidate": 0.4, "delta": -0.1},
                "latency_ms": {
                    "p95": {"baseline": 10, "candidate": 13, "delta": 3}
                },
            }
        },
        "metadata_warnings": ["fixture sha256 differs"],
    }

    markdown = render_markdown_comparison(comparison)

    headings = [
        "## Summary",
        "## Gating Regressions",
        "## Observed Declines",
        "## Metric Deltas",
        "## Metadata Warnings",
    ]
    assert all(heading in markdown for heading in headings)
    assert [markdown.index(heading) for heading in headings] == sorted(
        markdown.index(heading) for heading in headings
    )
    assert "### sample/weakened" in markdown
    assert "### sample/observation" in markdown
    assert "| name | baseline | candidate | delta |" in markdown
    assert "| noise_top12 | 1 | 2 | +1 |" in markdown
    assert "| latency.p95 | 10 | 12 | +2 |" in markdown
    assert "| overall.mrr | 0.5 | 0.4 | -0.1 |" in markdown
    assert "| overall.latency_ms.p95 | 10 | 13 | +3 |" in markdown
    assert markdown.endswith("\n")
