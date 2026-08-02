from __future__ import annotations

import argparse
import hashlib
import json
import statistics
from pathlib import Path
from typing import Any


EXPECTED_REPOSITORIES = 2
EXPECTED_CASES = 12
EXPECTED_EFFICACY_CASES = 8
EXPECTED_GUARD_CASES = 4
EXPECTED_SAMPLES_PER_CASE = 2
EXPECTED_LOCAL_ARM_REPLAYS = 96
MIN_STABLE_CAUSAL_GAINS = 3
MIN_VALID_PLANS = 22
MAX_PRECISION_DECLINE = 0.02
MAX_TREATMENT_ONLY_IRRELEVANT = 1
SCHEDULE_ORDER_RULE = (
    "repository_rank_then_case_ordinal_then_sample_1_control_1_control_2_"
    "treatment_1_treatment_2_then_sample_2_treatment_1_treatment_2_"
    "control_1_control_2"
)

_CAPTURE_FIELDS = (
    "validated_or_fallback_plan_sha256",
    "embedding_sha256",
    "base_roster_sha256",
    "shared_state_sha256",
)
_WITNESS_FIELDS = (
    "source_signal_id",
    "source_chunk_id",
    "source_file_path",
    "relation_id",
    "target_signal_id",
    "target_chunk_id",
    "target_file_path",
)


def evaluate_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    cases = manifest.get("cases", [])
    if not isinstance(cases, list):
        raise ValueError("cases must be a list")
    qualification_online_requests = _nonnegative_int(
        manifest.get("qualification_online_requests", 0),
        "qualification_online_requests",
    )

    gains: list[dict[str, Any]] = []
    stable_gain_cases: list[dict[str, str]] = []
    required_losses: list[dict[str, str]] = []
    rank1_changes: list[dict[str, str]] = []
    treatment_only_irrelevant: list[dict[str, str]] = []
    shared_capture_failures: list[dict[str, str]] = []
    replay_failures: list[dict[str, str]] = []
    corpus_qualification_failures: list[dict[str, str]] = []
    valid_plans = 0
    fallback_plans = 0
    control_relevant_hits = 0
    treatment_relevant_hits = 0
    precision_slots = 0
    control_latencies: list[float] = []
    treatment_latencies: list[float] = []
    extra_planner_requests = 0
    extra_embedding_requests = 0
    sample_count = 0
    observed_replay_ids: list[str] = []
    efficacy_case_count = 0
    guard_case_count = 0
    repositories: set[str] = set()
    repository_cohorts: dict[str, dict[str, int]] = {}
    repository_selection: dict[str, list[tuple[object, object, object, object]]] = {}

    for case in cases:
        case_id = _required_string(case, "case_id")
        repository = _required_string(case, "repository")
        cohort = _required_string(case, "cohort")
        gold_path = _required_repo_path(case, "gold_target_path")
        relevant_paths = _repo_path_set(case.get("relevant_paths", []))
        relevant_paths.add(gold_path)
        repositories.add(repository)
        cohort_counts = repository_cohorts.setdefault(
            repository, {"efficacy": 0, "guard": 0}
        )
        repository_selection.setdefault(repository, []).append(
            (
                case.get("structural_index"),
                cohort,
                case.get("selection_origin"),
                case.get("replacement"),
            )
        )
        if cohort == "efficacy":
            efficacy_case_count += 1
            cohort_counts["efficacy"] += 1
        elif cohort == "guard":
            guard_case_count += 1
            cohort_counts["guard"] += 1
        else:
            raise ValueError(f"{case_id}: cohort must be efficacy or guard")

        samples = case.get("samples", [])
        if not isinstance(samples, list):
            raise ValueError(f"{case_id}: samples must be a list")
        causal_samples = 0
        for sample_ordinal, sample in enumerate(samples, start=1):
            sample_count += 1
            sample_id = _required_string(sample, "sample_id")
            plan_status = _required_string(sample, "plan_status")
            if plan_status == "ok":
                valid_plans += 1
            else:
                fallback_plans += 1

            control = _required_object(sample, "control")
            treatment = _required_object(sample, "treatment")
            shared_capture = _same_capture(control, treatment)
            factor_only = (
                control.get("consume_dependency_hints") is False
                and treatment.get("consume_dependency_hints") is True
            )
            if not shared_capture or not factor_only:
                shared_capture_failures.append(
                    {"case_id": case_id, "sample_id": sample_id}
                )

            control_stable, control_projection = _stable_arm(control)
            treatment_stable, treatment_projection = _stable_arm(treatment)
            ordered_arms = (
                (control, treatment)
                if sample_ordinal == 1
                else (treatment, control)
            )
            observed_replay_ids.extend(
                _required_string(item, "replay_id")
                for arm in ordered_arms
                for item in arm["replays"]
            )
            if not control_stable or not treatment_stable:
                replay_failures.append({"case_id": case_id, "sample_id": sample_id})

            control_rows = control_projection["top12"]
            treatment_rows = treatment_projection["top12"]
            control_paths = {row["path"] for row in control_rows}
            treatment_paths = {row["path"] for row in treatment_rows}
            if cohort == "efficacy" and gold_path in control_paths:
                corpus_qualification_failures.append(
                    {"case_id": case_id, "sample_id": sample_id}
                )
            if gold_path in control_paths and gold_path not in treatment_paths:
                required_losses.append({"case_id": case_id, "sample_id": sample_id})
            if control_projection["rank1_path"] != treatment_projection["rank1_path"]:
                rank1_changes.append({"case_id": case_id, "sample_id": sample_id})

            control_relevant_hits += len(control_paths.intersection(relevant_paths))
            treatment_relevant_hits += len(treatment_paths.intersection(relevant_paths))
            precision_slots += 12
            control_latencies.extend(_arm_latencies(control))
            treatment_latencies.extend(_arm_latencies(treatment))
            extra_planner_requests += _nonnegative_int(
                treatment.get("additional_planner_requests", 0),
                "additional_planner_requests",
            )
            extra_embedding_requests += _nonnegative_int(
                treatment.get("additional_embedding_requests", 0),
                "additional_embedding_requests",
            )

            gain_rows = [
                row for row in treatment_rows if row["path"] not in control_paths
            ]
            gold_gain_is_causal = False
            for row in gain_rows:
                path = row["path"]
                marker = row.get("planner_dependency_hint_promotion", 0.0)
                marker_ok = isinstance(marker, (int, float)) and not isinstance(
                    marker, bool
                ) and marker > 0
                witness = row.get("closed_exact_witness")
                witness_ok = _closed_witness(witness, path)
                causal = (
                    shared_capture
                    and factor_only
                    and control_stable
                    and treatment_stable
                    and marker_ok
                    and witness_ok
                )
                relevance = (
                    "gold"
                    if path == gold_path
                    else "secondary_closed_target"
                    if causal and path in relevant_paths
                    else "irrelevant"
                    if path not in relevant_paths
                    else "relevant"
                )
                gain = {
                    "case_id": case_id,
                    "sample_id": sample_id,
                    "path": path,
                    "promotion_marker": marker if marker_ok else None,
                    "closed_witness": witness if witness_ok else None,
                    "same_capture": shared_capture and factor_only,
                    "replay_exact": control_stable and treatment_stable,
                    "causal": causal,
                    "relevance": relevance,
                }
                gains.append(gain)
                if path == gold_path and causal:
                    gold_gain_is_causal = True
                if path not in relevant_paths:
                    treatment_only_irrelevant.append(
                        {"case_id": case_id, "sample_id": sample_id, "path": path}
                    )
            if (
                cohort == "efficacy"
                and gold_path not in control_paths
                and gold_path in treatment_paths
                and gold_gain_is_causal
            ):
                causal_samples += 1

        if cohort == "efficacy" and causal_samples == EXPECTED_SAMPLES_PER_CASE:
            stable_gain_cases.append(
                {"case_id": case_id, "repository": repository}
            )

    control_precision = (
        control_relevant_hits / precision_slots if precision_slots else 0.0
    )
    treatment_precision = (
        treatment_relevant_hits / precision_slots if precision_slots else 0.0
    )
    precision_delta = treatment_precision - control_precision
    gained_repositories = {item["repository"] for item in stable_gain_cases}
    noncausal_gold_gains = [
        gain for gain in gains if gain["relevance"] == "gold" and not gain["causal"]
    ]
    schedule_valid = schedule_contract_is_valid(
        manifest.get("schedule"), observed_replay_ids
    )
    per_repository_complete = (
        len(repository_cohorts) == EXPECTED_REPOSITORIES
        and all(
            counts == {"efficacy": 4, "guard": 2}
            for counts in repository_cohorts.values()
        )
    )
    exact_repository_selection = [
        (1, "guard", "frozen_structural_order", False),
        (2, "guard", "frozen_structural_order", False),
        (3, "efficacy", "frozen_structural_order", False),
        (4, "efficacy", "frozen_structural_order", False),
        (5, "efficacy", "frozen_structural_order", False),
        (6, "efficacy", "frozen_structural_order", False),
    ]
    corpus_manifest_valid = (
        len(repository_selection) == EXPECTED_REPOSITORIES
        and all(
            selection == exact_repository_selection
            for selection in repository_selection.values()
        )
        and qualification_online_requests == 0
    )
    matrix_complete = (
        len(cases) == EXPECTED_CASES
        and len(repositories) == EXPECTED_REPOSITORIES
        and efficacy_case_count == EXPECTED_EFFICACY_CASES
        and guard_case_count == EXPECTED_GUARD_CASES
        and per_repository_complete
        and corpus_manifest_valid
        and sample_count == EXPECTED_CASES * EXPECTED_SAMPLES_PER_CASE
        and len(observed_replay_ids) == EXPECTED_LOCAL_ARM_REPLAYS
        and schedule_valid
        and all(
            isinstance(case.get("samples"), list)
            and len(case["samples"]) == EXPECTED_SAMPLES_PER_CASE
            for case in cases
        )
    )
    outcome_passed = (
        matrix_complete
        and len(stable_gain_cases) >= MIN_STABLE_CAUSAL_GAINS
        and gained_repositories == repositories
        and not required_losses
        and not rank1_changes
        and not noncausal_gold_gains
        and valid_plans >= MIN_VALID_PLANS
        and precision_delta >= -MAX_PRECISION_DECLINE
        and len(treatment_only_irrelevant) <= MAX_TREATMENT_ONLY_IRRELEVANT
        and not shared_capture_failures
        and not replay_failures
        and not corpus_qualification_failures
    )
    control_median = _median(control_latencies)
    treatment_median = _median(treatment_latencies)
    latency_passed = (
        control_median is not None
        and treatment_median is not None
        and (
            treatment_median - control_median <= 5.0
            or treatment_median <= control_median * 1.10
        )
    )
    release_passed = (
        latency_passed
        and extra_planner_requests == 0
        and extra_embedding_requests == 0
    )
    outcome_disposition = (
        "INCONCLUSIVE_CORPUS"
        if not matrix_complete or corpus_qualification_failures
        else "PASS"
        if outcome_passed
        else "REJECT_OUTCOME"
    )
    return {
        "schema_version": "p15-v7-metric-replay-v1",
        "fixed_denominators": {
            "repositories": EXPECTED_REPOSITORIES,
            "cases": EXPECTED_CASES,
            "efficacy_targets": EXPECTED_EFFICACY_CASES,
            "guard_cases": EXPECTED_GUARD_CASES,
            "planner_samples": EXPECTED_CASES * EXPECTED_SAMPLES_PER_CASE,
            "local_arm_replays": EXPECTED_LOCAL_ARM_REPLAYS,
        },
        "observed": {
            "repositories": len(repositories),
            "cases": len(cases),
            "efficacy_cases": efficacy_case_count,
            "guard_cases": guard_case_count,
            "planner_samples": sample_count,
            "local_arm_replays": len(observed_replay_ids),
            "valid_plans": valid_plans,
            "fallback_plans": fallback_plans,
            "qualification_online_requests": qualification_online_requests,
            "per_repository": repository_cohorts,
        },
        "corpus_manifest_valid": corpus_manifest_valid,
        "matrix_complete": matrix_complete,
        "schedule_valid": schedule_valid,
        "stable_causal_gain_cases": stable_gain_cases,
        "gains": gains,
        "noncausal_gold_gains": noncausal_gold_gains,
        "required_losses": required_losses,
        "rank1_changes": rank1_changes,
        "treatment_only_irrelevant": treatment_only_irrelevant,
        "shared_capture_failures": shared_capture_failures,
        "replay_failures": replay_failures,
        "corpus_qualification_failures": corpus_qualification_failures,
        "recall_at_12": {
            "control": 0.0,
            "treatment": len(stable_gain_cases) / EXPECTED_EFFICACY_CASES,
            "delta": len(stable_gain_cases) / EXPECTED_EFFICACY_CASES,
        },
        "precision_at_12": {
            "control": control_precision,
            "treatment": treatment_precision,
            "delta": precision_delta,
        },
        "latency_ms": {
            "control_median": control_median,
            "treatment_median": treatment_median,
            "gate_passed": latency_passed,
        },
        "additional_requests": {
            "planner": extra_planner_requests,
            "embedding": extra_embedding_requests,
        },
        "outcome_passed": outcome_passed,
        "outcome_disposition": outcome_disposition,
        "release_passed": release_passed,
        "accepted": outcome_passed and release_passed,
    }


def _required_object(value: dict[str, Any], key: str) -> dict[str, Any]:
    result = value.get(key)
    if not isinstance(result, dict):
        raise ValueError(f"{key} must be an object")
    return result


def _required_string(value: dict[str, Any], key: str) -> str:
    result = value.get(key)
    if not isinstance(result, str) or not result:
        raise ValueError(f"{key} must be a non-empty string")
    return result


def _required_repo_path(value: dict[str, Any], key: str) -> str:
    result = _required_string(value, key)
    if Path(result).is_absolute() or ".." in Path(result).parts:
        raise ValueError(f"{key} must be repository-relative")
    return Path(result).as_posix()


def _repo_path_set(values: object) -> set[str]:
    if not isinstance(values, list):
        raise ValueError("relevant_paths must be a list")
    return {_required_repo_path({"path": value}, "path") for value in values}


def _same_capture(control: dict[str, Any], treatment: dict[str, Any]) -> bool:
    control_capture = control.get("capture")
    treatment_capture = treatment.get("capture")
    if not isinstance(control_capture, dict) or not isinstance(treatment_capture, dict):
        return False
    return (
        set(control_capture) == set(_CAPTURE_FIELDS)
        and set(treatment_capture) == set(_CAPTURE_FIELDS)
        and all(
            isinstance(control_capture.get(field), str)
            and bool(control_capture[field])
            and control_capture.get(field) == treatment_capture.get(field)
            for field in _CAPTURE_FIELDS
        )
        and control_capture == treatment_capture
    )


def schedule_contract_is_valid(
    schedule: object,
    observed_replay_ids: list[str],
) -> bool:
    if not isinstance(schedule, dict):
        return False
    if schedule.get("order_rule") != SCHEDULE_ORDER_RULE:
        return False
    if schedule.get("schedule_frozen_before_treatment") is not True:
        return False
    expanded_schedule = schedule.get("expanded_schedule")
    if not isinstance(expanded_schedule, list):
        return False
    if not expanded_schedule and not observed_replay_ids:
        return True
    return (
        len(expanded_schedule) == EXPECTED_LOCAL_ARM_REPLAYS
        and all(isinstance(replay_id, str) for replay_id in expanded_schedule)
        and len(set(expanded_schedule)) == EXPECTED_LOCAL_ARM_REPLAYS
        and expanded_schedule == observed_replay_ids
        and isinstance(schedule.get("schedule_sha256"), str)
        and schedule["schedule_sha256"]
        == hashlib.sha256(
            json.dumps(
                expanded_schedule,
                ensure_ascii=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
    )


def _stable_arm(arm: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    replays = arm.get("replays")
    if not isinstance(replays, list) or len(replays) != 2:
        raise ValueError("each arm must contain exactly two replays")
    normalized = [_normalize_replay(replay) for replay in replays]
    projection = normalized[0]
    comparable = {
        "top12": projection["top12"],
        "rank1_path": projection["rank1_path"],
        "target_rank": projection["target_rank"],
        "score_order_sha256": projection["score_order_sha256"],
        "witness_projection_sha256": projection["witness_projection_sha256"],
    }
    return all(
        {
            "top12": item["top12"],
            "rank1_path": item["rank1_path"],
            "target_rank": item["target_rank"],
            "score_order_sha256": item["score_order_sha256"],
            "witness_projection_sha256": item["witness_projection_sha256"],
        }
        == comparable
        for item in normalized[1:]
    ), projection


def _normalize_replay(replay: object) -> dict[str, Any]:
    if not isinstance(replay, dict):
        raise ValueError("replay must be an object")
    rows = replay.get("top12")
    if not isinstance(rows, list) or len(rows) > 12:
        raise ValueError("top12 must be a list with at most twelve rows")
    normalized_rows: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("top12 rows must be objects")
        normalized_row = dict(row)
        normalized_row["path"] = _required_repo_path(row, "path")
        normalized_rows.append(normalized_row)
    rank1_path = replay.get("rank1_path")
    if rank1_path is not None:
        rank1_path = _required_repo_path({"path": rank1_path}, "path")
    target_rank = replay.get("target_rank")
    if target_rank is not None and (
        not isinstance(target_rank, int)
        or isinstance(target_rank, bool)
        or target_rank < 1
    ):
        raise ValueError("target_rank must be null or a positive integer")
    return {
        "replay_id": _required_string(replay, "replay_id"),
        "top12": normalized_rows,
        "rank1_path": rank1_path,
        "target_rank": target_rank,
        "score_order_sha256": _required_string(replay, "score_order_sha256"),
        "witness_projection_sha256": _required_string(
            replay, "witness_projection_sha256"
        ),
        "local_latency_ms": _nonnegative_number(
            replay.get("local_latency_ms"), "local_latency_ms"
        ),
    }


def _closed_witness(witness: object, path: str) -> bool:
    return (
        isinstance(witness, dict)
        and all(
            isinstance(witness.get(field), str) and witness[field]
            for field in _WITNESS_FIELDS
        )
        and witness.get("target_file_path") == path
        and witness.get("relation_kind") == "imports"
        and witness.get("resolution") == "resolved_exact"
        and witness.get("producer") == "python_ast"
        and witness.get("resolution_basis") == "exact_python_imported_symbol"
    )


def _arm_latencies(arm: dict[str, Any]) -> list[float]:
    return [
        _nonnegative_number(replay.get("local_latency_ms"), "local_latency_ms")
        for replay in arm["replays"]
    ]


def _nonnegative_number(value: object, key: str) -> float:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or value < 0
    ):
        raise ValueError(f"{key} must be a non-negative number")
    return float(value)


def _nonnegative_int(value: object, key: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{key} must be a non-negative integer")
    return value


def _median(values: list[float]) -> float | None:
    return statistics.median(values) if values else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Replay frozen P15-v7 paired metrics")
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    result = evaluate_manifest(manifest)
    serialized = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        print(serialized, end="")
    else:
        args.output.write_text(serialized, encoding="utf-8")
    return 0 if result["accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
