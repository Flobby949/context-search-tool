from __future__ import annotations

from typing import Any


_REPORT_SUMMARY_KEYS = (
    "total",
    "passed",
    "failed",
    "skipped",
    "known_gaps",
    "errors",
)
_COMPARISON_SUMMARY_KEYS = (
    "total",
    "improved",
    "regressed",
    "new_case",
    "removed_case",
    "skipped",
)


def render_markdown_report(report: dict[str, Any]) -> str:
    lines = [
        "# Retrieval Quality Report",
        "",
        f"Profile: `{report.get('profile', '')}`",
        "",
        "## Summary",
        "",
    ]
    lines.extend(_summary_table(report.get("aggregate", {}), _REPORT_SUMMARY_KEYS))
    lines.extend(["", "## Failures", ""])

    failures = [
        case
        for case in report.get("cases", [])
        if case.get("status") in {"fail", "error"}
    ]
    if failures:
        for case in sorted(failures, key=_report_case_sort_key):
            lines.extend(_case_failure_lines(case))
    else:
        lines.append("No failures.")

    lines.extend(["", "## Known Gaps", ""])
    known_gaps = [
        case for case in report.get("cases", []) if case.get("status") == "known_gap"
    ]
    if known_gaps:
        for case in sorted(known_gaps, key=_case_key):
            lines.extend(_case_failure_lines(case))
    else:
        lines.append("No known gaps.")

    return "\n".join(lines).rstrip() + "\n"


def render_markdown_comparison(comparison: dict[str, Any]) -> str:
    lines = [
        "# Retrieval Quality Comparison",
        "",
        "## Summary",
        "",
    ]
    lines.extend(
        _summary_table(comparison.get("aggregate", {}), _COMPARISON_SUMMARY_KEYS)
    )
    lines.extend(["", "## Metadata Warnings", ""])

    metadata_warnings = comparison.get("metadata_warnings", [])
    if metadata_warnings:
        lines.extend(f"- {warning}" for warning in metadata_warnings)
    else:
        lines.append("No metadata warnings.")

    lines.extend(["", "## Regressions", ""])
    regressions = [
        case
        for case in comparison.get("cases", [])
        if case.get("classification") == "regressed"
    ]
    if regressions:
        for case in sorted(regressions, key=lambda item: item.get("case_key", "")):
            lines.append(f"### {case.get('case_key', '')}")
            warnings = case.get("warnings", [])
            if warnings:
                lines.extend(f"- {warning}" for warning in warnings)
            else:
                lines.append("- No case warnings.")
            lines.append("")
    else:
        lines.append("No regressions.")

    return "\n".join(lines).rstrip() + "\n"


def _summary_table(aggregate: dict[str, Any], keys: tuple[str, ...]) -> list[str]:
    lines = [
        "| metric | value |",
        "| --- | ---: |",
    ]
    lines.extend(f"| {key} | {aggregate.get(key, 0)} |" for key in keys)
    return lines


def _case_key(case: dict[str, Any]) -> str:
    return f"{case.get('repo_key', '')}/{case.get('case_id', '')}"


def _report_case_sort_key(case: dict[str, Any]) -> tuple[int, str]:
    status_order = {"fail": 0, "error": 1}
    return (status_order.get(case.get("status"), 2), _case_key(case))


def _case_failure_lines(case: dict[str, Any]) -> list[str]:
    lines = [f"### {_case_key(case)}"]
    failures = case.get("failures", [])
    if failures:
        lines.extend(f"- {failure}" for failure in failures)
    else:
        lines.append("- No failure messages.")
    lines.append("")
    return lines
