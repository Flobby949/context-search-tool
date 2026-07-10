from __future__ import annotations

from typing import Any


_SUMMARY_KEYS = (
    "improved",
    "regressed",
    "new_case",
    "removed_case",
    "skipped",
)


def compare_reports(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
) -> dict[str, Any]:
    cases = []
    baseline_cases = {_case_key(case): case for case in baseline.get("cases", [])}
    candidate_cases = {_case_key(case): case for case in candidate.get("cases", [])}

    for case_key in sorted(baseline_cases.keys() | candidate_cases.keys()):
        baseline_case = baseline_cases.get(case_key)
        candidate_case = candidate_cases.get(case_key)
        cases.append(_compare_case(case_key, baseline_case, candidate_case))

    aggregate = {"total": len(cases), **{key: 0 for key in _SUMMARY_KEYS}}
    for case in cases:
        classification = case["classification"]
        if classification in aggregate:
            aggregate[classification] += 1

    return {
        "schema_version": 1,
        "metadata_warnings": _metadata_warnings(baseline, candidate),
        "aggregate": aggregate,
        "cases": cases,
    }


def _compare_case(
    case_key: str,
    baseline: dict[str, Any] | None,
    candidate: dict[str, Any] | None,
) -> dict[str, Any]:
    classification = _classification(baseline, candidate)
    return {
        "case_key": case_key,
        "classification": classification,
        "baseline_status": baseline.get("status") if baseline else None,
        "candidate_status": candidate.get("status") if candidate else None,
        "warnings": _case_warnings(baseline, candidate),
    }


def _classification(
    baseline: dict[str, Any] | None,
    candidate: dict[str, Any] | None,
) -> str:
    if baseline is None:
        return "new_case"
    if candidate is None:
        return "removed_case"

    baseline_status = baseline.get("status")
    candidate_status = candidate.get("status")
    if baseline_status == "skipped" and candidate_status == "skipped":
        return "skipped"
    if baseline_status == "pass" and candidate_status in {"fail", "error"}:
        return "regressed"
    if baseline_status in {"fail", "error"} and candidate_status == "pass":
        return "improved"

    baseline_metrics = baseline.get("metrics", {})
    candidate_metrics = candidate.get("metrics", {})
    baseline_hit_at_5 = baseline_metrics.get("hit_at_5")
    candidate_hit_at_5 = candidate_metrics.get("hit_at_5")
    if baseline_hit_at_5 is False and candidate_hit_at_5 is True:
        return "improved"
    if baseline_hit_at_5 is True and candidate_hit_at_5 is False:
        return "regressed"

    baseline_mrr = baseline_metrics.get("mrr")
    candidate_mrr = candidate_metrics.get("mrr")
    if (
        isinstance(baseline_mrr, int | float)
        and isinstance(candidate_mrr, int | float)
        and baseline_mrr - candidate_mrr > 0.25
    ):
        return "regressed"

    baseline_noise = baseline_metrics.get("noise_top5")
    candidate_noise = candidate_metrics.get("noise_top5")
    if (
        isinstance(baseline_noise, int | float)
        and isinstance(candidate_noise, int | float)
        and candidate_noise - baseline_noise >= 2
    ):
        return "regressed"

    if candidate_status == "pass":
        return "unchanged_pass"
    return "unchanged_fail"


def _case_warnings(
    baseline: dict[str, Any] | None,
    candidate: dict[str, Any] | None,
) -> list[str]:
    if baseline is None or candidate is None:
        return []

    baseline_latency = baseline.get("metrics", {}).get("latency_ms")
    candidate_latency = candidate.get("metrics", {}).get("latency_ms")
    if (
        isinstance(baseline_latency, int | float)
        and isinstance(candidate_latency, int | float)
        and baseline_latency > 0
        and candidate_latency > baseline_latency * 1.5
    ):
        return ["latency increased by more than 50%"]
    return []


def _metadata_warnings(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
) -> list[str]:
    warnings = []
    if baseline.get("schema_version") != candidate.get("schema_version"):
        warnings.append("report schema_version differs")
    if baseline.get("fixture", {}).get("sha256") != candidate.get("fixture", {}).get(
        "sha256"
    ):
        warnings.append("fixture sha256 differs")
    if baseline.get("profile") != candidate.get("profile"):
        warnings.append("profile differs")
    if baseline.get("config", {}).get("config_hash") != candidate.get(
        "config", {}
    ).get("config_hash"):
        warnings.append("config hash differs")
    if baseline.get("config", {}).get("embedding") != candidate.get("config", {}).get(
        "embedding"
    ):
        warnings.append("embedding config differs")
    if baseline.get("planner") != candidate.get("planner"):
        warnings.append("planner config differs")
    if _repo_identity(baseline) != _repo_identity(candidate):
        warnings.append("repo identity differs")
    return warnings


def _repo_identity(report: dict[str, Any]) -> dict[str, Any]:
    return {
        repo.get("repo_key", ""): repo.get("source", {}).get("content_hash")
        for repo in report.get("repos", [])
    }


def _case_key(case: dict[str, Any]) -> str:
    return f"{case.get('repo_key', '')}/{case.get('case_id', '')}"
