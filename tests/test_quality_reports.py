from context_search_tool.quality.reports import (
    render_markdown_comparison,
    render_markdown_report,
)


def test_render_markdown_report_includes_summary_and_prioritized_failures() -> None:
    report = {
        "profile": "ci",
        "aggregate": {
            "total": 4,
            "passed": 1,
            "failed": 1,
            "skipped": 0,
            "known_gaps": 1,
            "errors": 1,
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
    assert "| total | 4 |" in markdown
    assert "| known_gaps | 1 |" in markdown
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
                "total": 1,
                "passed": 1,
                "failed": 0,
                "skipped": 0,
                "known_gaps": 0,
                "errors": 0,
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


def test_render_markdown_comparison_includes_warnings_and_regressions() -> None:
    comparison = {
        "metadata_warnings": ["fixture sha256 differs"],
        "aggregate": {
            "total": 2,
            "improved": 0,
            "regressed": 1,
            "new_case": 0,
            "removed_case": 0,
            "skipped": 1,
        },
        "cases": [
            {
                "case_key": "sample/regressed",
                "classification": "regressed",
                "baseline_status": "pass",
                "candidate_status": "fail",
                "warnings": ["latency increased by more than 50%"],
            },
            {
                "case_key": "sample/skipped",
                "classification": "skipped",
                "baseline_status": "skipped",
                "candidate_status": "skipped",
                "warnings": [],
            },
        ],
    }

    markdown = render_markdown_comparison(comparison)

    assert markdown.endswith("\n")
    assert "# Retrieval Quality Comparison" in markdown
    assert "| regressed | 1 |" in markdown
    assert "## Metadata Warnings" in markdown
    assert "- fixture sha256 differs" in markdown
    assert "## Regressions" in markdown
    assert "### sample/regressed" in markdown
    assert "- latency increased by more than 50%" in markdown


def test_render_markdown_comparison_says_when_no_warnings_or_regressions() -> None:
    markdown = render_markdown_comparison(
        {
            "metadata_warnings": [],
            "aggregate": {
                "total": 1,
                "improved": 0,
                "regressed": 0,
                "new_case": 0,
                "removed_case": 0,
                "skipped": 1,
            },
            "cases": [
                {
                    "case_key": "sample/skipped",
                    "classification": "skipped",
                    "baseline_status": "skipped",
                    "candidate_status": "skipped",
                    "warnings": [],
                }
            ],
        }
    )

    assert "No metadata warnings." in markdown
    assert "No regressions." in markdown
