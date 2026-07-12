from __future__ import annotations

from collections import Counter
from typing import Any


_SUPPORTED_SCHEMAS = {1, 2}
_STATUSES = {"pass", "fail", "known_gap", "informational", "error", "skipped"}
_GATES = {"required", "known_gap", "informational"}
_REQUIRED_STATUSES = {"pass", "fail", "error", "skipped"}
_HIGHER_IS_BETTER = {
    "hit_at_1",
    "hit_at_3",
    "hit_at_5",
    "hit_at_10",
    "recall_at_5",
    "recall_at_10",
    "mrr",
    "cross_language_success",
    "preferred_rank_pass",
}
_LOWER_IS_BETTER_PREFIXES = ("noise_top",)
_LOWER_IS_BETTER = {"entrypoint_rank"}
_NEUTRAL = {"latency_ms", "result_count", "top_score"}
_TOLERANCE = 1e-12

_REQUIRED_STATUS_MATRIX = {
    ("pass", "fail"): ("regressed", True),
    ("pass", "error"): ("regressed", True),
    ("pass", "skipped"): ("regressed", True),
    ("fail", "pass"): ("improved", False),
    ("fail", "fail"): ("unchanged_fail", False),
    ("fail", "error"): ("execution_regressed", True),
    ("fail", "skipped"): ("coverage_lost_required", True),
    ("error", "pass"): ("improved", False),
    ("error", "fail"): ("newly_evaluated_failure", False),
    ("error", "error"): ("unchanged_error", False),
    ("error", "skipped"): ("unchanged_unverified", False),
    ("skipped", "pass"): ("newly_verified", False),
    ("skipped", "fail"): ("newly_evaluated_failure", False),
    ("skipped", "error"): ("unchanged_unverified", False),
    ("skipped", "skipped"): ("skipped", False),
}


def compare_reports(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
) -> dict[str, Any]:
    baseline_cases = _index_cases(baseline)
    candidate_cases = _index_cases(candidate)
    cases = [
        _compare_case(
            case_key,
            baseline_cases.get(case_key),
            candidate_cases.get(case_key),
        )
        for case_key in sorted(baseline_cases.keys() | candidate_cases.keys())
    ]

    counts = Counter(case["classification"] for case in cases)
    aggregate = {
        "total": len(cases),
        "gating_regressions": sum(case["gating"] for case in cases),
        "improvements": sum(
            counts[name]
            for name in ("improved", "newly_verified", "metric_improvement")
        ),
        "observed_declines": counts["metric_decline"],
        "removed_required": counts["removed_required"],
        **{name: counts[name] for name in sorted(counts)},
    }

    return {
        "schema_version": 2,
        "metadata_warnings": _metadata_warnings(baseline, candidate),
        "aggregate": aggregate,
        "metric_deltas": _aggregate_metric_deltas(
            baseline.get("aggregate", {}).get("metrics", {}),
            candidate.get("aggregate", {}).get("metrics", {}),
        ),
        "cases": cases,
    }


def _index_cases(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    schema = report.get("schema_version")
    if type(schema) is not int or schema not in _SUPPORTED_SCHEMAS:
        raise ValueError(f"unsupported report schema: {schema}")

    indexed: dict[str, dict[str, Any]] = {}
    for case in report.get("cases", []):
        key = _case_key(case)
        if key in indexed:
            raise ValueError(f"duplicate case key: {key}")

        status = case.get("status")
        if status not in _STATUSES:
            raise ValueError(f"unknown status for case {key}: {status}")
        gate = case.get("gate", "required")
        if gate not in _GATES:
            raise ValueError(f"unknown gate for case {key}: {gate}")
        if gate == "required" and status not in _REQUIRED_STATUSES:
            raise ValueError(
                f"inconsistent required gate/status for case {key}: {status}"
            )
        if status == "pass" and not isinstance(case.get("metrics"), dict):
            raise ValueError(f"pass case missing metrics: {key}")
        indexed[key] = case
    return indexed


def _compare_case(
    case_key: str,
    baseline: dict[str, Any] | None,
    candidate: dict[str, Any] | None,
) -> dict[str, Any]:
    if baseline is None:
        return _payload(case_key, "new_case", False, baseline, candidate)
    if candidate is None:
        required = baseline.get("gate", "required") == "required"
        return _payload(
            case_key,
            "removed_required" if required else "removed_observation",
            required,
            baseline,
            candidate,
        )

    baseline_gate = baseline.get("gate", "required")
    candidate_gate = candidate.get("gate", "required")
    if baseline_gate == "required" and candidate_gate != "required":
        return _payload(case_key, "gate_weakened", True, baseline, candidate)
    if baseline_gate != "required" and candidate_gate == "required":
        return _payload(case_key, "gate_strengthened", False, baseline, candidate)
    if baseline_gate != candidate_gate:
        return _payload(
            case_key, "gate_changed_observation", False, baseline, candidate
        )

    metric_deltas = _scalar_metric_deltas(
        _case_metrics(baseline),
        _case_metrics(candidate),
    )
    if baseline_gate == "required":
        classification, gating = _classify_required(
            baseline["status"], candidate["status"], metric_deltas
        )
    else:
        classification, gating = _classify_observation(
            baseline["status"], candidate["status"], metric_deltas
        )
    return _payload(
        case_key,
        classification,
        gating,
        baseline,
        candidate,
        metric_deltas=metric_deltas,
    )


def _classify_required(
    baseline_status: str,
    candidate_status: str,
    deltas: dict[str, dict[str, Any]],
) -> tuple[str, bool]:
    if baseline_status == candidate_status == "pass":
        decline = (
            _bool_transition(deltas, "hit_at_5", True, False)
            or _numeric_drop(deltas, "mrr") > 0.25
            or _numeric_gain(deltas, "noise_top5") >= 2
        )
        improvement = (
            _bool_transition(deltas, "hit_at_5", False, True)
            or _numeric_gain(deltas, "mrr") > 0.25
            or _numeric_drop(deltas, "noise_top5") >= 2
        )
        if decline:
            return "regressed", True
        if improvement:
            return "improved", False
        return "unchanged_pass", False
    return _REQUIRED_STATUS_MATRIX[(baseline_status, candidate_status)]


def _classify_observation(
    baseline_status: str,
    candidate_status: str,
    deltas: dict[str, dict[str, Any]],
) -> tuple[str, bool]:
    if baseline_status in {"error", "skipped"} or candidate_status in {
        "error",
        "skipped",
    }:
        return "observation_unavailable", False
    directions = {
        _direction(name, float(item["delta"]))
        for name, item in deltas.items()
        if _metric_delta_has_valid_type(name, item)
    }
    if "decline" in directions:
        return "metric_decline", False
    if "improvement" in directions:
        return "metric_improvement", False
    return "unchanged_observation", False


def _payload(
    case_key: str,
    classification: str,
    gating: bool,
    baseline: dict[str, Any] | None,
    candidate: dict[str, Any] | None,
    *,
    metric_deltas: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "case_key": case_key,
        "classification": classification,
        "gating": gating,
        "baseline_gate": baseline.get("gate", "required") if baseline else None,
        "candidate_gate": candidate.get("gate", "required") if candidate else None,
        "baseline_status": baseline.get("status") if baseline else None,
        "candidate_status": candidate.get("status") if candidate else None,
        "metric_deltas": metric_deltas or {},
        "warnings": _case_warnings(baseline, candidate),
    }


def _flatten_case_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    flattened = {
        name: value for name, value in metrics.items() if not isinstance(value, dict)
    }
    coverage = metrics.get("expected_coverage_top5")
    if isinstance(coverage, dict):
        flattened["expected_coverage_top5_ratio"] = coverage.get("ratio")
    return flattened


def _scalar_metric_deltas(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
) -> dict[str, dict[str, float | bool]]:
    baseline = _flatten_case_metrics(baseline)
    candidate = _flatten_case_metrics(candidate)
    deltas: dict[str, dict[str, float | bool]] = {}
    for name in sorted(set(baseline) & set(candidate)):
        before = baseline[name]
        after = candidate[name]
        if isinstance(before, bool) and isinstance(after, bool):
            deltas[name] = {
                "baseline": before,
                "candidate": after,
                "delta": int(after) - int(before),
            }
        elif (
            isinstance(before, (int, float))
            and not isinstance(before, bool)
            and isinstance(after, (int, float))
            and not isinstance(after, bool)
        ):
            deltas[name] = {
                "baseline": before,
                "candidate": after,
                "delta": after - before,
            }
    return deltas


def _direction(name: str, delta: float) -> str:
    if abs(delta) <= _TOLERANCE or name in _NEUTRAL:
        return "tie"
    higher_is_better = (
        name in _HIGHER_IS_BETTER
        or name.startswith("precision_at_")
        or name.startswith("expected_coverage_")
    )
    lower_is_better = name in _LOWER_IS_BETTER or name.startswith(
        _LOWER_IS_BETTER_PREFIXES
    )
    if higher_is_better:
        return "improvement" if delta > 0 else "decline"
    if lower_is_better:
        return "decline" if delta > 0 else "improvement"
    return "neutral"


def _bool_transition(
    deltas: dict[str, dict[str, Any]],
    name: str,
    before: bool,
    after: bool,
) -> bool:
    item = deltas.get(name, {})
    return item.get("baseline") is before and item.get("candidate") is after


def _numeric_gain(deltas: dict[str, dict[str, Any]], name: str) -> float:
    item = deltas.get(name, {})
    if not _numeric_delta(item):
        return 0.0
    return max(float(item["delta"]), 0.0)


def _numeric_drop(deltas: dict[str, dict[str, Any]], name: str) -> float:
    item = deltas.get(name, {})
    if not _numeric_delta(item):
        return 0.0
    return max(-float(item["delta"]), 0.0)


def _numeric_delta(item: dict[str, Any]) -> bool:
    return all(
        isinstance(item.get(field), (int, float))
        and not isinstance(item.get(field), bool)
        for field in ("baseline", "candidate", "delta")
    )


def _metric_delta_has_valid_type(name: str, item: dict[str, Any]) -> bool:
    if name.startswith("hit_at_") or name in {
        "cross_language_success",
        "preferred_rank_pass",
    }:
        return (
            isinstance(item.get("baseline"), bool)
            and isinstance(item.get("candidate"), bool)
        )
    return _numeric_delta(item)


def _delta_payload(before: Any, after: Any) -> dict[str, float] | None:
    if (
        isinstance(before, (int, float))
        and not isinstance(before, bool)
        and isinstance(after, (int, float))
        and not isinstance(after, bool)
    ):
        return {
            "baseline": float(before),
            "candidate": float(after),
            "delta": float(after) - float(before),
        }
    return None


def _aggregate_metric_deltas(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key in sorted(set(baseline) & set(candidate)):
        before = baseline[key]
        after = candidate[key]
        if not isinstance(before, dict) or not isinstance(after, dict):
            continue
        leaves = {
            field: payload
            for field in ("rate", "mean", "p50", "p95")
            if (payload := _delta_payload(before.get(field), after.get(field)))
            is not None
        }
        if set(leaves) in ({"rate"}, {"mean"}):
            output[key] = next(iter(leaves.values()))
            continue
        if leaves:
            output[key] = leaves
            continue
        nested = _aggregate_metric_deltas(before, after)
        if nested:
            output[key] = nested
    return output


def _case_warnings(
    baseline: dict[str, Any] | None,
    candidate: dict[str, Any] | None,
) -> list[str]:
    if baseline is None or candidate is None:
        return []

    baseline_latency = _case_metrics(baseline).get("latency_ms")
    candidate_latency = _case_metrics(candidate).get("latency_ms")
    if (
        isinstance(baseline_latency, (int, float))
        and not isinstance(baseline_latency, bool)
        and isinstance(candidate_latency, (int, float))
        and not isinstance(candidate_latency, bool)
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
    if baseline.get("fixture", {}).get("sha256") != candidate.get(
        "fixture", {}
    ).get("sha256"):
        warnings.append("fixture sha256 differs")
    if baseline.get("profile") != candidate.get("profile"):
        warnings.append("profile differs")
    if baseline.get("config", {}).get("config_hash") != candidate.get(
        "config", {}
    ).get("config_hash"):
        warnings.append("config hash differs")
    if baseline.get("config", {}).get("embedding") != candidate.get(
        "config", {}
    ).get("embedding"):
        warnings.append("embedding config differs")
    if baseline.get("planner") != candidate.get("planner"):
        warnings.append("planner config differs")
    if _repo_config_identity(baseline) != _repo_config_identity(candidate):
        warnings.append("repo effective config differs")
    if _repo_identity(baseline) != _repo_identity(candidate):
        warnings.append("repo identity differs")
    return warnings


def _repo_config_identity(report: dict[str, Any]) -> dict[str, Any]:
    return {
        repo.get("repo_key", ""): repo.get("config", {}).get("config_hash")
        for repo in report.get("repos", [])
    }


def _repo_identity(report: dict[str, Any]) -> dict[str, Any]:
    return {
        repo.get("repo_key", ""): repo.get("source", {}).get("content_hash")
        for repo in report.get("repos", [])
    }


def _case_metrics(case: dict[str, Any]) -> dict[str, Any]:
    metrics = case.get("metrics")
    return metrics if isinstance(metrics, dict) else {}


def _case_key(case: dict[str, Any]) -> str:
    return f"{case.get('repo_key', '')}/{case.get('case_id', '')}"
