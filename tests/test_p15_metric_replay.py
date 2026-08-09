from __future__ import annotations

import copy
import hashlib
import inspect
import json
from pathlib import Path

import pytest

import p15_metric_replay as replay
from context_search_tool.query_planner import (
    PLANNER_JSON_FIELDS,
    PROMPT_VERSION,
    prompt_hash,
)


pytestmark = pytest.mark.archival_acceptance


SCHEDULE_ORDER_RULE = (
    "repository_rank_then_case_ordinal_then_sample_1_control_1_control_2_"
    "treatment_1_treatment_2_then_sample_2_treatment_1_treatment_2_"
    "control_1_control_2"
)


def _capture(plan: str = "plan-a") -> dict[str, str]:
    return {
        "validated_or_fallback_plan_sha256": plan,
        "embedding_sha256": "embedding-a",
        "base_roster_sha256": "roster-a",
        "shared_state_sha256": "state-a",
    }


def _witness(path: str) -> dict[str, str]:
    return {
        "source_signal_id": "source-signal",
        "source_chunk_id": "source-chunk",
        "source_file_path": "src/source.py",
        "relation_id": "relation",
        "target_signal_id": f"signal:{path}",
        "target_chunk_id": f"chunk:{path}",
        "target_file_path": path,
        "relation_kind": "imports",
        "resolution": "resolved_exact",
        "producer": "python_ast",
        "resolution_basis": "exact_python_imported_symbol",
    }


def _row(path: str, *, causal_marker: bool = False) -> dict[str, object]:
    row: dict[str, object] = {"path": path}
    if causal_marker:
        row["planner_dependency_hint_promotion"] = 0.1
        row["closed_exact_witness"] = _witness(path)
    return row


def _arm(
    *,
    consume: bool,
    paths: list[str],
    marked_paths: set[str] | None = None,
    capture: dict[str, str] | None = None,
    latency_ms: float = 1.0,
) -> dict[str, object]:
    marked_paths = marked_paths or set()
    top12 = [_row(path, causal_marker=path in marked_paths) for path in paths]
    projection = {
        "replay_id": "replay-1",
        "top12": top12,
        "rank1_path": paths[0] if paths else None,
        "target_rank": None,
        "score_order_sha256": f"scores:{consume}:{','.join(paths)}",
        "witness_projection_sha256": f"witness:{consume}:{','.join(paths)}",
        "local_latency_ms": latency_ms,
    }
    second_projection = copy.deepcopy(projection)
    second_projection["replay_id"] = "replay-2"
    return {
        "consume_dependency_hints": consume,
        "capture": capture or _capture(),
        "additional_planner_requests": 0,
        "additional_embedding_requests": 0,
        "replays": [projection, second_projection],
    }


def _case(
    *,
    control_paths: list[str],
    treatment_paths: list[str],
    marked_paths: set[str] | None = None,
    cohort: str = "efficacy",
    relevant_paths: list[str] | None = None,
    plan_status: str = "ok",
    treatment_capture: dict[str, str] | None = None,
    control_latency_ms: float = 1.0,
    treatment_latency_ms: float = 1.0,
) -> dict[str, object]:
    control = _arm(
        consume=False,
        paths=control_paths,
        latency_ms=control_latency_ms,
    )
    treatment = _arm(
        consume=True,
        paths=treatment_paths,
        marked_paths=marked_paths,
        capture=treatment_capture,
        latency_ms=treatment_latency_ms,
    )
    return {
        "case_id": "case-a",
        "repository": "repo-a",
        "cohort": cohort,
        "gold_target_path": "src/target.py",
        "relevant_paths": relevant_paths or ["src/source.py", "src/target.py"],
        "samples": [
            {
                "sample_id": "sample-1",
                "plan_status": plan_status,
                "control": control,
                "treatment": treatment,
            }
        ],
    }


def _full_manifest(
    *,
    schedule_mode: str,
    skewed_repositories: bool = False,
) -> dict[str, object]:
    if skewed_repositories:
        layouts = (("repo-a", 7, 0), ("repo-b", 1, 4))
    else:
        layouts = (("repo-a", 4, 2), ("repo-b", 4, 2))
    cases: list[dict[str, object]] = []
    ordered_replay_ids: list[str] = []
    for repository, efficacy_count, guard_count in layouts:
        cohorts = ["guard"] * guard_count + ["efficacy"] * efficacy_count
        for case_ordinal, cohort in enumerate(cohorts, start=1):
            case_id = f"{repository}-case-{case_ordinal}"
            samples: list[dict[str, object]] = []
            for sample_ordinal in (1, 2):
                control = _arm(consume=False, paths=[f"src/{case_id}.py"])
                treatment = _arm(consume=True, paths=[f"src/{case_id}.py"])
                for arm_name, arm in (("control", control), ("treatment", treatment)):
                    for replay_ordinal, local_replay in enumerate(
                        arm["replays"], start=1
                    ):
                        local_replay["replay_id"] = (
                            f"{case_id}:sample-{sample_ordinal}:{arm_name}-"
                            f"{replay_ordinal}"
                        )
                arms = (
                    (control, treatment)
                    if schedule_mode == "uniform_control_first" or sample_ordinal == 1
                    else (treatment, control)
                )
                ordered_replay_ids.extend(
                    item["replay_id"]
                    for arm in arms
                    for item in arm["replays"]
                )
                samples.append(
                    {
                        "sample_id": f"sample-{sample_ordinal}",
                        "plan_status": "ok",
                        "control": control,
                        "treatment": treatment,
                    }
                )
            cases.append(
                {
                    "case_id": case_id,
                    "repository": repository,
                    "cohort": cohort,
                    "structural_index": case_ordinal,
                    "selection_origin": "frozen_structural_order",
                    "replacement": False,
                    "gold_target_path": f"src/{case_id}-target.py",
                    "relevant_paths": [f"src/{case_id}.py"],
                    "samples": samples,
                }
            )
    schedule_sha256 = hashlib.sha256(
        json.dumps(
            ordered_replay_ids,
            ensure_ascii=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return {
        "qualification_online_requests": 0,
        "schedule": {
            "order_rule": SCHEDULE_ORDER_RULE,
            "schedule_frozen_before_treatment": True,
            "schedule_sha256": schedule_sha256,
            "expanded_schedule": ordered_replay_ids,
        },
        "cases": cases,
    }


def test_same_capture_gain_records_marker_and_closed_witness() -> None:
    result = replay.evaluate_manifest(
        {
            "cases": [
                _case(
                    control_paths=["src/source.py", "src/old.py"],
                    treatment_paths=["src/source.py", "src/target.py"],
                    marked_paths={"src/target.py"},
                )
            ]
        }
    )

    assert result["shared_capture_failures"] == []
    assert result["gains"] == [
        {
            "case_id": "case-a",
            "sample_id": "sample-1",
            "path": "src/target.py",
            "promotion_marker": 0.1,
            "closed_witness": _witness("src/target.py"),
            "same_capture": True,
            "replay_exact": True,
            "causal": True,
            "relevance": "gold",
        }
    ]


def test_different_plans_cannot_manufacture_causal_gain() -> None:
    result = replay.evaluate_manifest(
        {
            "cases": [
                _case(
                    control_paths=["src/source.py", "src/old.py"],
                    treatment_paths=["src/source.py", "src/target.py"],
                    marked_paths={"src/target.py"},
                    treatment_capture=_capture("plan-b"),
                )
            ]
        }
    )

    assert result["shared_capture_failures"] == [
        {"case_id": "case-a", "sample_id": "sample-1"}
    ]
    assert result["noncausal_gold_gains"][0]["causal"] is False
    assert result["outcome_passed"] is False


def test_v4_style_unique_new_without_promotion_marker_is_rejected() -> None:
    result = replay.evaluate_manifest(
        {
            "cases": [
                _case(
                    control_paths=["src/source.py", "src/old.py"],
                    treatment_paths=["src/source.py", "src/target.py"],
                )
            ]
        }
    )

    gain = result["gains"][0]
    assert gain["promotion_marker"] is None
    assert gain["closed_witness"] is None
    assert gain["causal"] is False
    assert result["noncausal_gold_gains"] == [gain]
    assert result["outcome_passed"] is False


def test_fallback_case_remains_in_fixed_denominator() -> None:
    result = replay.evaluate_manifest(
        {
            "cases": [
                _case(
                    control_paths=["src/source.py", "src/old.py"],
                    treatment_paths=["src/source.py", "src/old.py"],
                    plan_status="fallback",
                )
            ]
        }
    )

    assert result["fixed_denominators"]["efficacy_targets"] == 8
    assert result["fixed_denominators"]["local_arm_replays"] == 96
    assert result["observed"]["efficacy_cases"] == 1
    assert result["observed"]["fallback_plans"] == 1
    assert result["matrix_complete"] is False


def test_secondary_closed_target_is_relevant_not_noise() -> None:
    result = replay.evaluate_manifest(
        {
            "cases": [
                _case(
                    control_paths=["src/source.py", "src/old.py"],
                    treatment_paths=["src/source.py", "src/secondary.py"],
                    marked_paths={"src/secondary.py"},
                    relevant_paths=[
                        "src/source.py",
                        "src/target.py",
                        "src/secondary.py",
                    ],
                )
            ]
        }
    )

    assert result["gains"][0]["relevance"] == "secondary_closed_target"
    assert result["treatment_only_irrelevant"] == []


def test_reports_guard_loss_noise_rank1_and_latency() -> None:
    result = replay.evaluate_manifest(
        {
            "cases": [
                _case(
                    cohort="guard",
                    control_paths=["src/target.py", "src/source.py"],
                    treatment_paths=["src/noise.py", "src/source.py"],
                    control_latency_ms=1.0,
                    treatment_latency_ms=10.0,
                )
            ]
        }
    )

    assert result["required_losses"] == [
        {"case_id": "case-a", "sample_id": "sample-1"}
    ]
    assert result["rank1_changes"] == [
        {"case_id": "case-a", "sample_id": "sample-1"}
    ]
    assert result["treatment_only_irrelevant"] == [
        {"case_id": "case-a", "sample_id": "sample-1", "path": "src/noise.py"}
    ]
    assert result["latency_ms"] == {
        "control_median": 1.0,
        "treatment_median": 10.0,
        "gate_passed": False,
    }


def test_requires_exactly_two_local_replays_per_arm() -> None:
    case = _case(
        control_paths=["src/source.py"],
        treatment_paths=["src/source.py"],
    )
    case["samples"][0]["control"]["replays"].append(
        copy.deepcopy(case["samples"][0]["control"]["replays"][0])
    )

    with pytest.raises(ValueError, match="exactly two replays"):
        replay.evaluate_manifest({"cases": [case]})


def test_schedule_rejects_uniform_control_first_across_both_samples() -> None:
    result = replay.evaluate_manifest(
        _full_manifest(schedule_mode="uniform_control_first")
    )

    assert result["schedule_valid"] is False
    assert result["matrix_complete"] is False


def test_schedule_accepts_frozen_alternating_sample_order() -> None:
    result = replay.evaluate_manifest(_full_manifest(schedule_mode="alternating"))

    assert result["schedule_valid"] is True
    assert result["matrix_complete"] is True


def test_authoritative_shared_plan_field_is_required() -> None:
    case = _case(
        control_paths=["src/source.py"],
        treatment_paths=["src/source.py"],
    )
    for arm_name in ("control", "treatment"):
        capture = case["samples"][0][arm_name]["capture"]
        assert "validated_or_fallback_plan_sha256" in capture

    result = replay.evaluate_manifest({"cases": [case]})

    assert result["shared_capture_failures"] == []


def test_legacy_plan_sha256_shared_capture_field_fails_closed() -> None:
    case = _case(
        control_paths=["src/source.py"],
        treatment_paths=["src/source.py"],
    )
    for arm_name in ("control", "treatment"):
        capture = case["samples"][0][arm_name]["capture"]
        capture["plan_sha256"] = capture.pop(
            "validated_or_fallback_plan_sha256"
        )

    result = replay.evaluate_manifest({"cases": [case]})

    assert result["shared_capture_failures"] == [
        {"case_id": "case-a", "sample_id": "sample-1"}
    ]


def test_matrix_requires_four_efficacy_and_two_guard_cases_per_repository() -> None:
    result = replay.evaluate_manifest(
        _full_manifest(
            schedule_mode="uniform_control_first",
            skewed_repositories=True,
        )
    )

    assert result["observed"]["efficacy_cases"] == 8
    assert result["observed"]["guard_cases"] == 4
    assert result["matrix_complete"] is False
    assert result["outcome_disposition"] == "INCONCLUSIVE_CORPUS"


def test_qualification_online_call_makes_complete_manifest_inconclusive() -> None:
    manifest = _full_manifest(schedule_mode="alternating")
    manifest["qualification_online_requests"] = 1

    result = replay.evaluate_manifest(manifest)

    assert result["observed"]["planner_samples"] == 24
    assert result["observed"]["local_arm_replays"] == 96
    assert result["observed"]["qualification_online_requests"] == 1
    assert result["outcome_disposition"] == "INCONCLUSIVE_CORPUS"


def test_replacement_case_makes_complete_manifest_inconclusive() -> None:
    manifest = _full_manifest(schedule_mode="alternating")
    manifest["cases"][0]["replacement"] = True

    result = replay.evaluate_manifest(manifest)

    assert result["observed"]["planner_samples"] == 24
    assert result["observed"]["local_arm_replays"] == 96
    assert result["outcome_disposition"] == "INCONCLUSIVE_CORPUS"


def test_seventh_structural_candidate_manifest_is_inconclusive() -> None:
    manifest = _full_manifest(schedule_mode="alternating")
    extra_case = copy.deepcopy(manifest["cases"][-1])
    extra_case["case_id"] = "repo-b-case-7"
    extra_case["structural_index"] = 7
    manifest["cases"].append(extra_case)

    result = replay.evaluate_manifest(manifest)

    assert result["observed"]["cases"] == 13
    assert result["outcome_disposition"] == "INCONCLUSIVE_CORPUS"


def test_efficacy_control_hit_is_inconclusive_only_after_complete_matrix() -> None:
    manifest = _full_manifest(schedule_mode="alternating")
    efficacy_case = next(
        case for case in manifest["cases"] if case["cohort"] == "efficacy"
    )
    gold_path = efficacy_case["gold_target_path"]
    control = efficacy_case["samples"][0]["control"]
    for local_replay in control["replays"]:
        local_replay["top12"].append(_row(gold_path))

    result = replay.evaluate_manifest(manifest)

    assert result["observed"]["planner_samples"] == 24
    assert result["observed"]["local_arm_replays"] == 96
    assert result["matrix_complete"] is True
    assert result["corpus_qualification_failures"] == [
        {
            "case_id": efficacy_case["case_id"],
            "sample_id": "sample-1",
        }
    ]
    assert result["outcome_disposition"] == "INCONCLUSIVE_CORPUS"
    assert result["outcome_passed"] is False


def test_replay_runner_has_no_candidate_eligibility_dependency() -> None:
    source = inspect.getsource(replay)

    assert "context_search_tool" not in source
    assert "private helper" not in source
    assert "first_two" not in source


def test_p15_v7_attempt_contract_binds_candidate_runner_tests_and_gates() -> None:
    root = Path(__file__).parents[1]
    contract_path = (
        root
        / "tests"
        / "fixtures"
        / "p15_v7_minimal_online_causal"
        / "attempt-contract.json"
    )
    contract = json.loads(contract_path.read_text(encoding="utf-8"))

    assert contract["attempt_id"] == "p15-v7-attempt-007"
    assert contract["execution_role"] == "two_repository_acceptance_draft"
    assert contract["status"] == "DRAFT"
    assert contract["execution_eligible"] is False
    assert contract["user_approval_required"] is True
    assert contract["documents"] == {
        "design_path": "docs/superpowers/specs/2026-08-02-p15-v7-minimal-online-causal-acceptance-design.md",
        "design_sha256": "cc048396157f58855ed4844f40d489e9063354e04d9bd361457475904e7a6e97",
        "plan_path": "docs/superpowers/plans/2026-08-02-p15-v7-minimal-online-causal-acceptance-plan.md",
        "plan_sha256": "33a9ab58d318e6404acd15aa8872aeccc867ae6e9d064b7d744ab44dcd3e8776",
    }
    assert contract["candidate"]["prompt_version"] == PROMPT_VERSION
    assert contract["candidate"]["prompt_sha256"] == prompt_hash().removeprefix(
        "sha256:"
    )
    schema_projection = json.dumps(
        sorted(PLANNER_JSON_FIELDS),
        ensure_ascii=True,
        separators=(",", ":"),
    ).encode("utf-8")
    assert contract["candidate"]["response_schema_sha256"] == hashlib.sha256(
        schema_projection
    ).hexdigest()
    for section in ("product_files_sha256", "runner_and_tests_sha256"):
        expected = contract["candidate"][section]
        assert expected
        assert expected == {
            path: hashlib.sha256((root / path).read_bytes()).hexdigest()
            for path in expected
        }
    product_projection = json.dumps(
        contract["candidate"]["product_files_sha256"],
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    assert contract["candidate"]["product_projection_sha256"] == hashlib.sha256(
        product_projection
    ).hexdigest()
    gate_projection = json.dumps(
        contract["gates"],
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    assert contract["gate_projection_sha256"] == hashlib.sha256(
        gate_projection
    ).hexdigest()
    assert contract["corpus"]["fresh_repositories"] == []
    assert contract["corpus"]["fresh_cases"] == []
    assert contract["corpus"]["selection_contract"] == {
        "stage": "before_any_online_request",
        "repository_order": "resolved_canonical_prefix2",
        "structural_order": "frozen_independent_ast_order",
        "per_repository_indices": [1, 2, 3, 4, 5, 6],
        "guard_indices": [1, 2],
        "efficacy_candidate_indices": [3, 4, 5, 6],
        "cases_per_repository": 6,
        "repository_count": 2,
        "total_cases": 12,
        "scan_beyond_index_6_allowed": False,
        "case_replacement_allowed": False,
        "repository_replacement_allowed": False,
        "qualification_online_requests": 0,
        "efficacy_control_requirement": (
            "gold_missing_in_both_complete_frozen_samples_else_"
            "INCONCLUSIVE_CORPUS"
        ),
    }
    assert contract["sampling"]["expanded_schedule"] == []
    assert contract["sampling"]["order_rule"] == replay.SCHEDULE_ORDER_RULE
    assert replay.schedule_contract_is_valid(contract["sampling"], []) is True
    assert tuple(contract["sampling"]["same_sample_shared_capture_fields"]) == (
        replay._CAPTURE_FIELDS
    )
    assert contract["governance"]["fresh_identity_selected"] is False
    assert contract["governance"]["fresh_source_accessed"] is False
    assert contract["governance"]["held_out_opened"] is False
