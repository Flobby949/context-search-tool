from __future__ import annotations

import math
from collections import Counter
from typing import Any


_SUPPORTED_SCHEMAS = {1, 2}
_STATUSES = {"pass", "fail", "known_gap", "informational", "error", "skipped"}
_GATES = {"required", "known_gap", "informational"}
_REQUIRED_STATUSES = {"pass", "fail", "error", "skipped"}
_BOOLEAN_METRICS = {"cross_language_success", "preferred_rank_pass"}
_RATE_METRICS = {"mrr"}
_NONNEGATIVE_METRICS = {
    "entrypoint_rank",
    "latency_ms",
    "result_count",
}
_UNBOUNDED_NUMERIC_METRICS = {"top_score"}
_AGGREGATE_LEAVES = {"count", "mean", "p50", "p95", "rate", "successes", "total"}
_AGGREGATE_GROUPS = {
    "overall",
    "by_repository",
    "by_tag",
    "by_profile",
    "by_embedding",
}
_AGGREGATE_RATE_METRICS = {
    "hit_at_1",
    "hit_at_3",
    "hit_at_5",
    "hit_at_10",
    "cross_language_success",
    "preferred_rank_pass",
    "entrypoint_top1",
    "entrypoint_top3",
}
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
    identities = baseline_cases.keys() | candidate_cases.keys()
    _validate_unambiguous_case_keys(identities)
    cases = [
        _compare_case(
            _format_case_key(identity),
            baseline_cases.get(identity),
            candidate_cases.get(identity),
        )
        for identity in sorted(identities)
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
            _aggregate_metrics(baseline),
            _aggregate_metrics(candidate),
        ),
        "cases": cases,
    }


def _index_cases(
    report: dict[str, Any],
) -> dict[tuple[str, str], dict[str, Any]]:
    if not isinstance(report, dict):
        raise ValueError("report must be an object")

    schema = report.get("schema_version")
    if type(schema) is not int or schema not in _SUPPORTED_SCHEMAS:
        raise ValueError(f"unsupported report schema: {schema}")

    _validate_report_containers(report, schema)
    cases = report.get("cases")
    if not isinstance(cases, list):
        raise ValueError("report cases must be a list")

    indexed: dict[tuple[str, str], dict[str, Any]] = {}
    for case in cases:
        if not isinstance(case, dict):
            raise ValueError("report case must be an object")
        repo_key = case.get("repo_key")
        if not isinstance(repo_key, str) or not repo_key.strip():
            raise ValueError("case repo_key must be a non-empty string")
        case_id = case.get("case_id")
        if not isinstance(case_id, str) or not case_id.strip():
            raise ValueError("case case_id must be a non-empty string")

        identity = (repo_key, case_id)
        key = _format_case_key(identity)
        if identity in indexed:
            raise ValueError(f"duplicate case key: {key}")

        status = case.get("status")
        if not isinstance(status, str) or not status.strip():
            raise ValueError(f"status must be a non-empty string for case {key}")
        if status not in _STATUSES:
            raise ValueError(f"unknown status for case {key}: {status}")
        if schema == 1 and "gate" not in case:
            gate = "required"
        else:
            gate = case.get("gate")
        if not isinstance(gate, str) or not gate.strip():
            raise ValueError(f"gate must be a non-empty string for case {key}")
        if gate not in _GATES:
            raise ValueError(f"unknown gate for case {key}: {gate}")
        if gate == "required" and status not in _REQUIRED_STATUSES:
            raise ValueError(
                f"inconsistent required gate/status for case {key}: {status}"
            )
        metrics = case.get("metrics")
        if not isinstance(metrics, dict) and (
            schema == 2 or metrics is not None or status == "pass"
        ):
            if status == "pass":
                raise ValueError(f"pass case missing metrics: {key}")
            raise ValueError(f"case {key} metrics must be an object")
        if status == "pass" and not isinstance(metrics, dict):
            raise ValueError(f"pass case missing metrics: {key}")
        if isinstance(metrics, dict):
            _validate_case_metrics(metrics, key, schema)
        indexed[identity] = case
    return indexed


def _validate_unambiguous_case_keys(
    identities: set[tuple[str, str]],
) -> None:
    formatted: dict[str, tuple[str, str]] = {}
    for identity in identities:
        key = _format_case_key(identity)
        previous = formatted.get(key)
        if previous is not None and previous != identity:
            raise ValueError(f"ambiguous case key: {key}")
        formatted[key] = identity


def _validate_report_containers(report: dict[str, Any], schema: int) -> None:
    for field in ("fixture", "config", "planner"):
        if field in report and not isinstance(report[field], dict):
            raise ValueError(f"report {field} must be an object")

    config = report.get("config", {})
    if "embedding" in config and not isinstance(config["embedding"], dict):
        raise ValueError("report config embedding must be an object")

    repos = report.get("repos", [])
    if not isinstance(repos, list):
        raise ValueError("report repos must be a list")
    repo_keys: set[str] = set()
    for repo in repos:
        if not isinstance(repo, dict):
            raise ValueError("report repo must be an object")
        repo_key = repo.get("repo_key")
        if not isinstance(repo_key, str) or not repo_key.strip():
            raise ValueError("report repo_key must be a non-empty string")
        if repo_key in repo_keys:
            raise ValueError(f"duplicate report repo_key: {repo_key}")
        repo_keys.add(repo_key)
        for field in ("source", "config"):
            if field in repo and not isinstance(repo[field], dict):
                raise ValueError(f"repo {field} must be an object")
        if schema == 2:
            repo_config = repo.get("config")
            if not isinstance(repo_config, dict):
                raise ValueError("repo config must be an object")
            config_hash = repo_config.get("config_hash")
            if not isinstance(config_hash, str) or not config_hash.strip():
                raise ValueError("repo config_hash must be a non-empty string")

    if schema == 2 and "aggregate" not in report:
        raise ValueError("report aggregate must be an object")
    aggregate = report.get("aggregate", {})
    if not isinstance(aggregate, dict):
        raise ValueError("report aggregate must be an object")
    if schema == 2 and "metrics" not in aggregate:
        raise ValueError("aggregate metrics must be an object")
    metrics = aggregate.get("metrics", {})
    if not isinstance(metrics, dict):
        raise ValueError("aggregate metrics must be an object")
    if schema == 2:
        _validate_v2_aggregate_metrics(metrics)
    else:
        _validate_aggregate_metrics(metrics, ())


def _validate_case_metrics(
    metrics: dict[str, Any],
    case_key: str,
    schema: int,
) -> None:
    for name, value in metrics.items():
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"case {case_key} metric name must be a non-empty string")
        owner = f"case {case_key} metric {name}"
        if name == "expected_coverage_top5":
            _validate_expected_coverage(value, owner, strict=schema == 2)
        elif name.startswith("hit_at_") or name in _BOOLEAN_METRICS:
            if value is not None and type(value) is not bool:
                raise ValueError(f"{owner} must be a bool or null")
        elif schema == 2 and name == "entrypoint_rank":
            if value is not None and (type(value) is not int or value <= 0):
                raise ValueError(f"{owner} must be a positive integer or null")
        elif schema == 2 and (
            name in {"latency_ms", "result_count"} or name.startswith("noise_top")
        ):
            _require_nonnegative_integer(value, owner)
        elif _is_known_numeric_metric(name):
            if value is not None:
                number = _finite_number(value, owner)
                _validate_metric_bounds(name, number, owner)
        elif value is not None and type(value) is not bool:
            _finite_number(value, owner)


def _validate_expected_coverage(
    value: Any,
    owner: str,
    *,
    strict: bool,
) -> None:
    if not isinstance(value, dict):
        raise ValueError(f"{owner} must be an object")
    if strict and set(value) != {"count", "ratio"}:
        raise ValueError(f"{owner} must contain exactly count and ratio")
    unknown = set(value) - {"count", "ratio"}
    if unknown:
        field = sorted(repr(item) for item in unknown)[0]
        raise ValueError(f"{owner} has unknown field {field}")
    if strict:
        _require_nonnegative_integer(value.get("count"), f"{owner}.count")
    elif value.get("count") is not None:
        count = _finite_number(value["count"], f"{owner}.count")
        if count < 0:
            raise ValueError(f"{owner}.count must be nonnegative")
    if value.get("ratio") is not None:
        ratio = _finite_number(value["ratio"], f"{owner}.ratio")
        if not 0 <= ratio <= 1:
            raise ValueError(f"{owner}.ratio must be between 0 and 1")


def _require_nonnegative_integer(value: Any, owner: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(f"{owner} must be a nonnegative integer")
    return value


def _is_known_numeric_metric(name: str) -> bool:
    return (
        name in _RATE_METRICS
        or name in _NONNEGATIVE_METRICS
        or name in _UNBOUNDED_NUMERIC_METRICS
        or name.startswith("recall_at_")
        or name.startswith("precision_at_")
        or name.startswith("noise_top")
        or name.startswith("expected_coverage_")
    )


def _finite_number(value: Any, owner: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"{owner} must be a finite number or null")
    try:
        number = float(value)
    except OverflowError as error:
        raise ValueError(f"{owner} must be a finite number or null") from error
    if not math.isfinite(number):
        raise ValueError(f"{owner} must be a finite number or null")
    return number


def _validate_metric_bounds(name: str, number: float, owner: str) -> None:
    if (
        name in _RATE_METRICS
        or name.startswith("recall_at_")
        or name.startswith("precision_at_")
        or name.startswith("expected_coverage_")
    ) and not 0 <= number <= 1:
        raise ValueError(f"{owner} must be between 0 and 1")
    if (
        name in _NONNEGATIVE_METRICS or name.startswith("noise_top")
    ) and number < 0:
        raise ValueError(f"{owner} must be nonnegative")


def _validate_aggregate_metrics(
    metrics: dict[str, Any],
    path: tuple[str, ...],
) -> None:
    for name, value in metrics.items():
        if not isinstance(name, str) or not name.strip():
            raise ValueError("aggregate metrics keys must be non-empty strings")
        current_path = (*path, name)
        label = ".".join(current_path)
        if not isinstance(value, dict):
            raise ValueError(f"aggregate metrics {label} must be an object")
        leaves = {
            field
            for field in _AGGREGATE_LEAVES
            if field in value and not isinstance(value[field], dict)
        }
        if not leaves:
            _validate_aggregate_metrics(value, current_path)
            continue
        unknown = set(value) - _AGGREGATE_LEAVES
        if unknown:
            field = sorted(repr(item) for item in unknown)[0]
            raise ValueError(
                f"aggregate metrics {label} has unknown summary field "
                f"{field}"
            )
        _validate_aggregate_summary(name, value, label)


def _validate_v2_aggregate_metrics(metrics: dict[str, Any]) -> None:
    if set(metrics) != _AGGREGATE_GROUPS:
        raise ValueError(
            "aggregate metrics must contain exactly "
            f"{', '.join(sorted(_AGGREGATE_GROUPS))}"
        )
    for grouping, grouped in metrics.items():
        if not isinstance(grouping, str) or not grouping.strip():
            raise ValueError("aggregate metrics keys must be non-empty strings")
        if grouping not in _AGGREGATE_GROUPS:
            raise ValueError(f"unknown aggregate metrics grouping: {grouping}")
        if not isinstance(grouped, dict):
            raise ValueError(f"aggregate metrics {grouping} must be an object")
        if grouping == "overall":
            _validate_v2_metric_map(grouped, (grouping,))
            continue
        for group_name, metric_map in grouped.items():
            if not isinstance(group_name, str) or not group_name.strip():
                raise ValueError(
                    f"aggregate metrics {grouping} keys must be non-empty strings"
                )
            if not isinstance(metric_map, dict):
                raise ValueError(
                    f"aggregate metrics {grouping}.{group_name} must be an object"
                )
            _validate_v2_metric_map(metric_map, (grouping, group_name))


def _validate_v2_metric_map(
    metrics: dict[str, Any],
    path: tuple[str, ...],
) -> None:
    for metric_name, summary in metrics.items():
        if not isinstance(metric_name, str) or not metric_name.strip():
            raise ValueError("aggregate metric names must be non-empty strings")
        label = ".".join((*path, metric_name))
        if not isinstance(summary, dict):
            raise ValueError(f"aggregate metrics {label} must be an object")
        _validate_v2_aggregate_summary(metric_name, summary, label)


def _validate_v2_aggregate_summary(
    metric_name: str,
    summary: dict[str, Any],
    label: str,
) -> None:
    if metric_name in _AGGREGATE_RATE_METRICS:
        expected_fields = {"successes", "total", "rate"}
    elif metric_name == "latency_ms":
        expected_fields = {"count", "mean", "p50", "p95"}
    else:
        expected_fields = {"count", "mean"}
    if set(summary) != expected_fields:
        raise ValueError(
            f"aggregate metrics {label} must contain exactly "
            f"{', '.join(sorted(expected_fields))}"
        )

    if "successes" in summary:
        successes = _require_nonnegative_integer(
            summary["successes"],
            f"aggregate metrics {label}.successes",
        )
        total = summary["total"]
        if type(total) is not int or total <= 0:
            raise ValueError(
                f"aggregate metrics {label}.total must be a positive integer"
            )
        if successes > total:
            raise ValueError(
                f"aggregate metrics {label}.successes cannot exceed total"
            )
        rate = _finite_number(
            summary["rate"],
            f"aggregate metrics {label}.rate",
        )
        if not 0 <= rate <= 1:
            raise ValueError(
                f"aggregate metrics {label}.rate must be between 0 and 1"
            )
        if not math.isclose(
            rate,
            successes / total,
            rel_tol=_TOLERANCE,
            abs_tol=_TOLERANCE,
        ):
            raise ValueError(
                f"aggregate metrics {label}.rate is inconsistent with "
                "successes and total"
            )
        return

    count = summary["count"]
    if type(count) is not int or count <= 0:
        raise ValueError(
            f"aggregate metrics {label}.count must be a positive integer"
        )
    if metric_name == "latency_ms":
        mean_owner = f"aggregate metrics {label}.mean"
        mean = _finite_number(summary["mean"], mean_owner)
        _validate_metric_bounds(metric_name, mean, mean_owner)
        p50 = _require_nonnegative_integer(
            summary["p50"],
            f"aggregate metrics {label}.p50",
        )
        p95 = _require_nonnegative_integer(
            summary["p95"],
            f"aggregate metrics {label}.p95",
        )
        if p50 > p95:
            raise ValueError(
                f"aggregate metrics {label}.p50 cannot exceed p95"
            )
        return
    for field in expected_fields - {"count"}:
        owner = f"aggregate metrics {label}.{field}"
        number = _finite_number(summary[field], owner)
        _validate_metric_bounds(metric_name, number, owner)


def _validate_aggregate_summary(
    metric_name: str,
    summary: dict[str, Any],
    label: str,
) -> None:
    for field, value in summary.items():
        owner = f"aggregate metrics {label}.{field}"
        number = _finite_number(value, owner)
        if field in {"count", "successes", "total"} and number < 0:
            raise ValueError(f"{owner} must be nonnegative")
        if field == "rate" and not 0 <= number <= 1:
            raise ValueError(f"{owner} must be between 0 and 1")
        if field in {"mean", "p50", "p95"}:
            _validate_metric_bounds(metric_name, number, owner)


def _aggregate_metrics(report: dict[str, Any]) -> dict[str, Any]:
    return report.get("aggregate", {}).get("metrics", {})


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
        case_key,
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
    case_key: str,
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
            delta = after - before
            try:
                delta_is_finite = math.isfinite(float(delta))
            except OverflowError:
                delta_is_finite = False
            if not delta_is_finite:
                raise ValueError(
                    f"case {case_key} metric {name} delta must be finite"
                )
            deltas[name] = {
                "baseline": before,
                "candidate": after,
                "delta": delta,
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
        before_number = float(before)
        after_number = float(after)
        delta = after_number - before_number
        if not all(
            math.isfinite(number)
            for number in (before_number, after_number, delta)
        ):
            raise ValueError("aggregate metric delta must be finite")
        return {
            "baseline": before_number,
            "candidate": after_number,
            "delta": delta,
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
        if key != "latency_ms" and set(leaves) in ({"rate"}, {"mean"}):
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
    if (
        _should_compare_repo_configs(baseline, candidate)
        and _repo_config_identity(baseline) != _repo_config_identity(candidate)
    ):
        warnings.append("repo effective config differs")
    if _repo_identity(baseline) != _repo_identity(candidate):
        warnings.append("repo identity differs")
    return warnings


def _repo_config_identity(report: dict[str, Any]) -> dict[str, Any]:
    return {
        repo.get("repo_key", ""): repo.get("config", {}).get("config_hash")
        for repo in report.get("repos", [])
    }


def _should_compare_repo_configs(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
) -> bool:
    if baseline["schema_version"] == candidate["schema_version"] == 2:
        return True
    return _repo_config_hashes_available(baseline) and _repo_config_hashes_available(
        candidate
    )


def _repo_config_hashes_available(report: dict[str, Any]) -> bool:
    repos = report.get("repos", [])
    return bool(repos) and all(
        isinstance(repo.get("config", {}).get("config_hash"), str)
        and bool(repo["config"]["config_hash"])
        for repo in repos
    )


def _repo_identity(report: dict[str, Any]) -> dict[str, Any]:
    return {
        repo.get("repo_key", ""): repo.get("source", {}).get("content_hash")
        for repo in report.get("repos", [])
    }


def _case_metrics(case: dict[str, Any]) -> dict[str, Any]:
    metrics = case.get("metrics")
    return metrics if isinstance(metrics, dict) else {}


def _format_case_key(identity: tuple[str, str]) -> str:
    return f"{identity[0]}/{identity[1]}"
