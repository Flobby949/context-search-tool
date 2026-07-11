from __future__ import annotations

import math
from collections import defaultdict
from statistics import mean
from typing import Any, Callable


_EXECUTED_STATUSES = {"pass", "fail", "known_gap", "informational"}
_ALL_STATUSES = _EXECUTED_STATUSES | {"skipped", "error"}
_RESERVED_DERIVED_METRICS = {
    "entrypoint_top1",
    "entrypoint_top3",
    "expected_coverage_top5_ratio",
}
_BOOLEAN_METRICS = {
    "hit_at_1",
    "hit_at_3",
    "hit_at_5",
    "hit_at_10",
    "cross_language_success",
    "preferred_rank_pass",
}


def aggregate_cases(
    cases: list[dict[str, Any]],
    repos: list[dict[str, Any]],
    profile: str,
) -> dict[str, Any]:
    for case in cases:
        case_id = case.get("case_id", "<unknown>")
        status = case.get("status")
        if not isinstance(status, str) or status not in _ALL_STATUSES:
            raise ValueError(f"case {case_id!r} has invalid status {status!r}")
        attempted = case.get("attempted")
        if type(attempted) is not bool:
            raise ValueError(f"case {case_id!r} attempted must be a bool")
        if status in _EXECUTED_STATUSES and not attempted:
            raise ValueError(
                f"case {case_id!r} attempted must be True for status {status!r}"
            )
        if status == "skipped" and attempted:
            raise ValueError(
                f"case {case_id!r} attempted must be False for status {status!r}"
            )
        reserved_metrics = sorted(
            _RESERVED_DERIVED_METRICS.intersection(case.get("metrics", {}))
        )
        if reserved_metrics:
            names = ", ".join(repr(name) for name in reserved_metrics)
            raise ValueError(f"case {case_id!r} uses reserved metric name(s): {names}")

    statuses = [case.get("status") for case in cases]
    executed = [case for case in cases if case.get("status") in _EXECUTED_STATUSES]
    aggregate: dict[str, Any] = {
        "total": len(cases),
        "selected": len(cases),
        "attempted": sum(case["attempted"] for case in cases),
        "executed": len(executed),
        "passed": statuses.count("pass"),
        "failed": statuses.count("fail"),
        "skipped": statuses.count("skipped"),
        "known_gaps": statuses.count("known_gap"),
        "informational": statuses.count("informational"),
        "errors": statuses.count("error"),
    }
    aggregate["metrics"] = _grouped_metrics(executed, repos, profile)
    return aggregate


def _grouped_metrics(
    cases: list[dict[str, Any]],
    repos: list[dict[str, Any]],
    profile: str,
) -> dict[str, Any]:
    repo_embedding: dict[str, str] = {}
    repo_keys: set[str] = set()
    for repo in repos:
        repo_key = repo["repo_key"]
        if repo_key in repo_keys:
            raise ValueError(f"duplicate repo_key {repo_key!r}")
        repo_keys.add(repo_key)
        embedding = repo.get("config", {}).get("embedding", {})
        provider = embedding.get("provider")
        model = embedding.get("model")
        if provider and model:
            repo_embedding[repo_key] = f"{provider}/{model}"
    by_repository = _group(cases, lambda case: [case["repo_key"]])
    by_tag = _group(cases, lambda case: case.get("tags", []))
    by_profile = {profile: _metric_summary(cases)} if profile else {}
    by_embedding = _group(
        cases,
        lambda case: [repo_embedding.get(case["repo_key"], "")],
    )
    return {
        "overall": _metric_summary(cases),
        "by_repository": by_repository,
        "by_tag": by_tag,
        "by_profile": by_profile,
        "by_embedding": by_embedding,
    }


def _group(
    cases: list[dict[str, Any]],
    keys_for_case: Callable[[dict[str, Any]], list[str]],
) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for case in cases:
        for key in dict.fromkeys(keys_for_case(case)):
            if key:
                grouped[key].append(case)
    return {key: _metric_summary(grouped[key]) for key in sorted(grouped)}


def _metric_summary(cases: list[dict[str, Any]]) -> dict[str, Any]:
    values: dict[str, list[Any]] = defaultdict(list)
    entrypoint_ranks: list[int | None] = []
    for case in cases:
        metrics = case.get("metrics", {})
        for name, value in metrics.items():
            if value is None:
                continue
            if name == "expected_coverage_top5" and isinstance(value, dict):
                ratio = value.get("ratio")
                if isinstance(ratio, (int, float)) and not isinstance(ratio, bool):
                    ratio_number = float(ratio)
                    if math.isfinite(ratio_number):
                        values["expected_coverage_top5_ratio"].append(ratio_number)
                continue
            if name == "entrypoint_rank":
                continue
            values[name].append(value)
        if "entrypoint" in case.get("tags", []):
            rank = metrics.get("entrypoint_rank")
            entrypoint_ranks.append(
                rank if type(rank) is int and rank > 0 else None
            )

    summary: dict[str, Any] = {}
    for name in sorted(values):
        items = values[name]
        if name in _BOOLEAN_METRICS:
            booleans = [item for item in items if isinstance(item, bool)]
            if booleans:
                successes = sum(booleans)
                summary[name] = {
                    "successes": successes,
                    "total": len(booleans),
                    "rate": successes / len(booleans),
                }
            continue
        numbers = []
        for item in items:
            if isinstance(item, (int, float)) and not isinstance(item, bool):
                number = float(item)
                if math.isfinite(number):
                    numbers.append(number)
        if not numbers:
            continue
        if name == "latency_ms":
            ordered = sorted(numbers)
            summary[name] = {
                "count": len(ordered),
                "mean": mean(ordered),
                "p50": _nearest_rank(ordered, 0.50),
                "p95": _nearest_rank(ordered, 0.95),
            }
        else:
            summary[name] = {"count": len(numbers), "mean": mean(numbers)}

    if entrypoint_ranks:
        for name, limit in (("entrypoint_top1", 1), ("entrypoint_top3", 3)):
            successes = sum(
                rank is not None and rank <= limit for rank in entrypoint_ranks
            )
            summary[name] = {
                "successes": successes,
                "total": len(entrypoint_ranks),
                "rate": successes / len(entrypoint_ranks),
            }
    return summary


def _nearest_rank(values: list[float], percentile: float) -> float:
    index = max(0, math.ceil(percentile * len(values)) - 1)
    value = values[index]
    return int(value) if value.is_integer() else value
