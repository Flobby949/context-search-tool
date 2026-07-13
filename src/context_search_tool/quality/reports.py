from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any


_REPORT_SUMMARY_KEYS = (
    "selected",
    "attempted",
    "executed",
    "passed",
    "failed",
    "skipped",
    "known_gaps",
    "informational",
    "errors",
)
_COMPARISON_SUMMARY_KEYS = (
    "total",
    "gating_regressions",
    "improvements",
    "observed_declines",
    "removed_required",
)
_MARKDOWN_CONTROL_CHARACTERS = frozenset("\\`*[]<>#|~")


def render_markdown_report(report: dict[str, Any]) -> str:
    lines = [
        "# Retrieval Quality Report",
        "",
        f"Profile: {_markdown_code_span(report.get('profile', ''))}",
        "",
        "## Summary",
        "",
    ]
    aggregate = report.get("aggregate", {})
    lines.extend(_summary_table(aggregate, _REPORT_SUMMARY_KEYS))
    lines.extend(["", "## Metrics", ""])

    metric_rows = _flatten_metric_values(
        aggregate.get("metrics", {}).get("overall", {})
    )
    if metric_rows:
        lines.extend(_value_table(metric_rows))
    else:
        lines.append("No metrics.")

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
        case
        for case in report.get("cases", [])
        if case.get("known_gap_reason") or case.get("status") == "known_gap"
    ]
    if known_gaps:
        for case in sorted(known_gaps, key=_case_key):
            lines.extend(_known_gap_lines(case))
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
    cases = comparison.get("cases", [])
    lines.extend(["", "## Gating Regressions", ""])

    gating = [case for case in cases if case.get("gating")]
    if gating:
        for case in sorted(gating, key=lambda item: item.get("case_key", "")):
            lines.extend(_comparison_case_lines(case))
    else:
        lines.append("No gating regressions.")

    lines.extend(["", "## Observed Declines", ""])
    observed = [
        case for case in cases if case.get("classification") == "metric_decline"
    ]
    if observed:
        for case in sorted(observed, key=lambda item: item.get("case_key", "")):
            lines.extend(_comparison_case_lines(case))
    else:
        lines.append("No observed declines.")

    lines.extend(["", "## Metric Deltas", ""])
    metric_deltas = _flatten_deltas(comparison.get("metric_deltas", {}))
    if metric_deltas:
        lines.extend(_delta_table(metric_deltas))
    else:
        lines.append("No metric deltas.")

    lines.extend(["", "## Metadata Warnings", ""])
    metadata_warnings = comparison.get("metadata_warnings", [])
    if metadata_warnings:
        lines.extend(
            f"- {_escape_markdown_text(warning)}" for warning in metadata_warnings
        )
    else:
        lines.append("No metadata warnings.")

    return "\n".join(lines).rstrip() + "\n"


def _summary_table(aggregate: dict[str, Any], keys: tuple[str, ...]) -> list[str]:
    lines = [
        "| metric | value |",
        "| --- | ---: |",
    ]
    lines.extend(
        f"| {key} | {_escape_markdown_text(aggregate.get(key, 0))} |"
        for key in keys
    )
    return lines


def _value_table(rows: list[tuple[str, Any]]) -> list[str]:
    return [
        "| metric | value |",
        "| --- | ---: |",
        *(
            f"| {_escape_markdown_text(name)} | "
            f"{_escape_markdown_text(value)} |"
            for name, value in rows
        ),
    ]


def _flatten_metric_values(
    node: dict[str, Any],
    prefix: str = "",
) -> list[tuple[str, Any]]:
    rows: list[tuple[str, Any]] = []
    for key in sorted(node):
        value = node[key]
        name = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            rows.extend(_flatten_metric_values(value, name))
        elif key in {"mean", "rate", "p50", "p95"}:
            rows.append((name, value))
    return rows


def _is_json_scalar(value: Any) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))


def _flatten_deltas(
    node: Mapping[str, Any],
    prefix: str = "",
) -> list[tuple[str, Mapping[str, Any]]]:
    rows: list[tuple[str, Mapping[str, Any]]] = []
    delta_fields = ("baseline", "candidate", "delta")
    if all(field in node for field in delta_fields) and all(
        _is_json_scalar(node[field]) for field in delta_fields
    ):
        return [(prefix, node)]
    for key in sorted(node):
        value = node[key]
        if isinstance(value, Mapping):
            name = f"{prefix}.{key}" if prefix else key
            rows.extend(_flatten_deltas(value, name))
    return rows


def _delta_table(rows: list[tuple[str, Mapping[str, Any]]]) -> list[str]:
    return [
        "| name | baseline | candidate | delta |",
        "| --- | ---: | ---: | ---: |",
        *(
            "| {name} | {baseline} | {candidate} | {delta} |".format(
                name=_escape_markdown_text(name),
                baseline=_escape_markdown_text(values["baseline"]),
                candidate=_escape_markdown_text(values["candidate"]),
                delta=_escape_markdown_text(_signed(values["delta"])),
            )
            for name, values in rows
        ),
    ]


def _signed(value: Any) -> str:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f"{value:+}"
    return str(value)


def _case_key(case: dict[str, Any]) -> str:
    return f"{case.get('repo_key', '')}/{case.get('case_id', '')}"


def _report_case_sort_key(case: dict[str, Any]) -> tuple[int, str]:
    status_order = {"fail": 0, "error": 1}
    return (status_order.get(case.get("status"), 2), _case_key(case))


def _case_failure_lines(case: dict[str, Any]) -> list[str]:
    lines = [f"### {_escape_markdown_text(_case_key(case))}"]
    failures = case.get("failures", [])
    if failures:
        lines.extend(f"- {_escape_markdown_text(failure)}" for failure in failures)
    else:
        lines.append("- No failure messages.")
    lines.append("")
    return lines


def _known_gap_lines(case: dict[str, Any]) -> list[str]:
    lines = [f"### {_escape_markdown_text(_case_key(case))}"]
    reason = case.get("known_gap_reason", "")
    if reason:
        lines.append(f"- {_escape_markdown_text(reason)}")
    lines.extend(
        f"- {_escape_markdown_text(failure)}"
        for failure in case.get("failures", [])
    )
    if len(lines) == 1:
        lines.append("- No known-gap reason supplied.")
    lines.append("")
    return lines


def _comparison_case_lines(case: dict[str, Any]) -> list[str]:
    lines = [f"### {_escape_markdown_text(case.get('case_key', ''))}"]
    warnings = case.get("warnings", [])
    if warnings:
        lines.extend(f"- {_escape_markdown_text(warning)}" for warning in warnings)
    else:
        lines.append("- No case warnings.")
    deltas = _flatten_deltas(case.get("metric_deltas", {}))
    if deltas:
        lines.extend(["", *_delta_table(deltas)])
    lines.append("")
    return lines


def _one_line(value: Any) -> str:
    return re.sub(r"[\r\n]+", " ", str(value))


def _escape_markdown_text(value: Any) -> str:
    text = _one_line(value)
    escaped: list[str] = []
    for index, character in enumerate(text):
        if character == "_":
            previous = text[index - 1] if index else ""
            following = text[index + 1] if index + 1 < len(text) else ""
            should_escape = not (previous.isalnum() and following.isalnum())
        else:
            should_escape = character in _MARKDOWN_CONTROL_CHARACTERS
        escaped.append(f"\\{character}" if should_escape else character)
    return "".join(escaped)


def _markdown_code_span(value: Any) -> str:
    text = _one_line(value)
    longest_run = max((len(run) for run in re.findall(r"`+", text)), default=0)
    delimiter = "`" * (longest_run + 1)
    return f"{delimiter}{text}{delimiter}"
