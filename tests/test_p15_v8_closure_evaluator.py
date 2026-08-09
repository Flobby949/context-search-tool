from __future__ import annotations

import ast
import copy
import hashlib
import inspect
import json
from pathlib import Path
import subprocess
import sys
from typing import Any

import pytest

import p15_v8_closure_evaluator as evaluator


PROMOTION_MODES = (
    "exact_source_hint",
    "exact_target_hint",
    "semantic_pair_fallback",
)
NO_OP_STATUSES = (
    "disabled",
    "graph_unavailable",
    "planner_not_ok",
    "intent_mismatch",
    "missing_activation_hint",
    "no_eligible_closed_candidate",
)
FRESH_SCHEDULE_SHA256 = (
    "a4f91e62af9c2581294e0e6ddf2dde22d209fa86d5e087e8b2c834d5f38c51b4"
)
HELD_OUT_SCHEDULE_SHA256 = (
    "729d075856570a10587744aa6d3200f059206b1ec7e08557e34b93e45bdd004f"
)
RUNNER_SHA256 = "5" * 64


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _schedule(repository_slots: list[str], case_ordinals: list[int]) -> dict[str, Any]:
    return {
        "repository_slots": repository_slots,
        "case_ordinals": case_ordinals,
        "samples": [
            {
                "ordinal": 1,
                "replay_order": [
                    "control-r1",
                    "control-r2",
                    "treatment-r1",
                    "treatment-r2",
                ],
            },
            {
                "ordinal": 2,
                "replay_order": [
                    "treatment-r1",
                    "treatment-r2",
                    "control-r1",
                    "control-r2",
                ],
            },
        ],
        "expanded_count": len(repository_slots) * len(case_ordinals) * 8,
    }


def _expanded_schedule(schedule: dict[str, Any]) -> list[str]:
    return [
        f"{repository}-c{case_ordinal:02d}-s{sample['ordinal']}-{replay}"
        for repository in schedule["repository_slots"]
        for case_ordinal in schedule["case_ordinals"]
        for sample in schedule["samples"]
        for replay in sample["replay_order"]
    ]


def _contract() -> dict[str, Any]:
    fresh_schedule = _schedule(["fresh-r01", "fresh-r02"], list(range(1, 7)))
    held_out_schedule = _schedule(["heldout-r01"], list(range(1, 5)))
    fresh_schedule["expanded_sha256"] = FRESH_SCHEDULE_SHA256
    held_out_schedule["expanded_sha256"] = HELD_OUT_SCHEDULE_SHA256
    return {
        "attempt_id": "p15-v8-attempt-test",
        "candidate": {"commit": "1" * 40, "tree": "2" * 40},
        "approval_receipt": {
            "received": False,
            "path": "",
            "sha256": "",
            "approved_attempt_id": "",
            "approved_contract_sha256": "",
        },
        "treatment": {
            "only_factor": "consume_dependency_hints",
            "control": False,
            "treatment": True,
            "all_other_inputs_shared": True,
        },
        "behavior": {
            "promotion_modes": list(PROMOTION_MODES),
            "no_op_statuses": list(NO_OP_STATUSES),
            "maximum_promoted_paths": 2,
            "rank_one_protected": True,
            "closed_exact_witness_required": True,
        },
        "online_identity": {
            "planner": {
                "calls_per_case_sample": 1,
                "treatment_additional_calls": 0,
            },
            "embedding": {"treatment_additional_calls": 0},
        },
        "retrieval": {
            "top_k": {"semantic": 80, "lexical": 80, "final": 12},
            "budgets": {
                "max_graph_seed_signals": 512,
                "max_resolved_graph_hops": 4,
                "max_signals_popped_per_query": 4096,
                "max_edges_examined_per_query": 16384,
                "max_frontier_entries_per_query": 8192,
                "max_relation_expanded_candidates": 1000,
            },
            "caps_must_not_increase": True,
        },
        "privacy": {
            "forbidden_in_evidence": [
                "credential",
                "authorization_header",
                "source_body",
                "absolute_local_path",
                "raw_exception",
            ],
            "tracked_leak_count_limit": 0,
        },
        "corpus": {
            "fresh": {
                "repository_count": 2,
                "cases_per_repository": 6,
                "guard_ordinals": [1, 2],
                "efficacy_ordinals": [3, 4, 5, 6],
                "target_recall_denominator": 8,
                "replacement_allowed": False,
            },
            "held_out": {
                "repository_count": 1,
                "cases_per_repository": 4,
                "replacement_allowed": False,
            },
        },
        "schedule": {
            "fresh": fresh_schedule,
            "held_out": held_out_schedule,
            "result_dependent_append_allowed": False,
            "retry_or_replacement_allowed": False,
            "all_cases_complete_before_decision": True,
        },
        "gates": {
            "outcome": {
                "fresh": {
                    "minimum_stable_causal_new_targets": 3,
                    "minimum_distinct_efficacy_cases": 3,
                    "minimum_repositories_with_gain": 2,
                    "required_target_losses": 0,
                    "rank_one_changes": 0,
                    "minimum_valid_plans": 22,
                    "planner_sample_denominator": 24,
                    "maximum_precision_at_12_decline": 0.02,
                    "maximum_treatment_only_irrelevant_case_sample_paths": 1,
                    "target_recall_denominator": 8,
                    "complete_matrix_before_decision": True,
                },
                "held_out": {
                    "minimum_candidate_blind_target_missing_cases": 4,
                    "minimum_stable_causal_new_targets": 2,
                    "minimum_distinct_cases": 2,
                    "required_target_losses": 0,
                    "complete_matrix_before_decision": True,
                },
            },
            "release": {
                "treatment_additional_planner_calls": 0,
                "treatment_additional_embedding_calls": 0,
                "local_treatment_median_max_relative_regression": 0.1,
                "local_treatment_median_max_absolute_increase_ms": 5,
                "tracked_privacy_leaks": 0,
                "topk_caps_or_budgets_increase": 0,
                "focused_tests": "pass",
                "product_full_suite": "pass",
                "ci": "pass",
                "supported_opt_in_config": "pass",
            },
            "governance": {
                "candidate_and_contract_bindings_exact": True,
                "no_tuning_after_seal": True,
                "evidence_complete": True,
                "approval_and_execution_manifest_match": True,
                "outcome_release_governance_separate": True,
            },
            "comparator": {
                "name": "fast-context",
                "policy": "report_only",
                "scope": "fresh_12_cases",
                "expected_reports": 12,
                "post_hoc_policy_change_allowed": False,
                "unavailable_disposition": (
                    "record_INCOMPLETE_without_gate_waiver"
                ),
            },
        },
        "verification": {
            "runner": {
                "path": "tests/p15_v8_closure_evaluator.py",
                "sha256": RUNNER_SHA256,
                "role": "tracked_offline_closure_evaluator_only",
                "online_collection_authorized": False,
            }
        },
    }


def _promotion_report(*, treatment: bool) -> dict[str, Any]:
    modes = {mode: 0 for mode in PROMOTION_MODES}
    statuses = {status: 0 for status in NO_OP_STATUSES}
    if treatment:
        modes["exact_source_hint"] = 1
    else:
        statuses["disabled"] = 1
    return {
        "trace_schema_version": 1,
        "stage": "dependency_promotion",
        "mode_counts": modes,
        "status_counts": statuses,
        "promoted_path_count": 1 if treatment else 0,
    }


def _witness(target_path: str) -> dict[str, str]:
    return {
        "source_signal_id": "source-signal",
        "source_chunk_id": "source-chunk",
        "source_file_path": "src/source.py",
        "relation_id": "relation",
        "target_signal_id": f"signal:{target_path}",
        "target_chunk_id": f"chunk:{target_path}",
        "target_file_path": target_path,
        "relation_kind": "imports",
        "resolution": "resolved_exact",
        "producer": "python_ast",
        "resolution_basis": "exact_python_imported_symbol",
    }


def _rows(slot: str, case_ordinal: int, *, treatment: bool) -> list[dict[str, Any]]:
    shared = [
        {"path": f"src/{slot}/shared-{case_ordinal}-{index}.py"}
        for index in range(11)
    ]
    if not treatment:
        return [*shared, {"path": f"src/{slot}/old-{case_ordinal}.py"}]
    target = f"src/{slot}/target-{case_ordinal}.py"
    return [
        *shared,
        {
            "path": target,
            "planner_dependency_hint_promotion": 0.5,
            "closed_exact_witness": _witness(target),
        },
    ]


def _arm(
    slot: str,
    case_ordinal: int,
    sample_ordinal: int,
    *,
    treatment: bool,
    capture: dict[str, str],
) -> dict[str, Any]:
    arm_name = "treatment" if treatment else "control"
    rows = _rows(slot, case_ordinal, treatment=treatment)
    return {
        "consume_dependency_hints": treatment,
        "capture": copy.deepcopy(capture),
        "additional_planner_requests": 0,
        "additional_embedding_requests": 0,
        "replays": [
            {
                "replay_id": (
                    f"{slot}-c{case_ordinal:02d}-s{sample_ordinal}-"
                    f"{arm_name}-r{replay_ordinal}"
                ),
                "top12": copy.deepcopy(rows),
                "rank1_path": rows[0]["path"],
                "local_latency_ms": 10.5 if treatment else 10.0,
                "promotion_report": _promotion_report(treatment=treatment),
            }
            for replay_ordinal in (1, 2)
        ],
    }


def _repository_universe(schedule: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {
            "repository_slot": slot,
            "repository_identity_sha256": hashlib.sha256(
                f"repository-identity:{slot}".encode("utf-8")
            ).hexdigest(),
        }
        for slot in schedule["repository_slots"]
    ]


def _case_input_projection(
    case: dict[str, Any], repository_identity_sha256: str
) -> dict[str, Any]:
    core = {
        "repository_slot": case["repository_slot"],
        "repository_identity_sha256": repository_identity_sha256,
        "case_ordinal": case["case_ordinal"],
        "case_id": case["case_id"],
        "query_sha256": _sha256(case["query"]),
        "gold_sha256": _sha256(case["gold_target_path"]),
        "relevant_sha256": _sha256(sorted(case["relevant_paths"])),
        "required_sha256": _sha256(sorted(case["required_paths"])),
    }
    return {**core, "projection_sha256": _sha256(core)}


def _corpus_binding(
    contract: dict[str, Any], evidence: dict[str, Any], name: str
) -> dict[str, Any]:
    universe = evidence["repository_universe"]
    identities = {
        item["repository_slot"]: item["repository_identity_sha256"]
        for item in universe
    }
    case_projections = [
        _case_input_projection(case, identities[case["repository_slot"]])
        for case in evidence["cases"]
    ]
    universe_sha256 = _sha256(universe)
    case_projection_sha256 = _sha256(case_projections)
    payload_sha256 = _sha256(
        {
            "repository_universe_sha256": universe_sha256,
            "case_projection_sha256": case_projection_sha256,
        }
    )
    public_seal_sha256 = _sha256(
        {
            "corpus": name,
            "payload_sha256": payload_sha256,
            "schedule_sha256": contract["schedule"][name]["expanded_sha256"],
        }
    )
    return {
        "repository_universe": copy.deepcopy(universe),
        "repository_universe_sha256": universe_sha256,
        "case_projections": case_projections,
        "case_projection_sha256": case_projection_sha256,
        "payload_sha256": payload_sha256,
        "public_seal_sha256": public_seal_sha256,
    }


def _evidence(contract: dict[str, Any], name: str) -> dict[str, Any]:
    schedule = contract["schedule"][name]
    universe = _repository_universe(schedule)
    cases: list[dict[str, Any]] = []
    for slot in schedule["repository_slots"]:
        for case_ordinal in schedule["case_ordinals"]:
            case_id = f"{slot}-case-{case_ordinal}"
            gold = f"src/{slot}/target-{case_ordinal}.py"
            relevant = [
                f"src/{slot}/shared-{case_ordinal}-{index}.py"
                for index in range(11)
            ] + [gold, f"src/{slot}/secondary-{case_ordinal}.py"]
            samples = []
            for sample_ordinal in (1, 2):
                capture = {
                    "validated_or_fallback_plan_sha256": (
                        f"plan-{slot}-{case_ordinal}-{sample_ordinal}"
                    ),
                    "embedding_sha256": f"embedding-{slot}-{case_ordinal}",
                    "base_roster_sha256": f"roster-{slot}-{case_ordinal}",
                    "shared_state_sha256": f"state-{slot}-{case_ordinal}",
                }
                samples.append(
                    {
                        "sample_ordinal": sample_ordinal,
                        "plan_status": "ok",
                        "control": _arm(
                            slot,
                            case_ordinal,
                            sample_ordinal,
                            treatment=False,
                            capture=capture,
                        ),
                        "treatment": _arm(
                            slot,
                            case_ordinal,
                            sample_ordinal,
                            treatment=True,
                            capture=capture,
                        ),
                    }
                )
            cases.append(
                {
                    "case_id": case_id,
                    "repository_slot": slot,
                    "case_ordinal": case_ordinal,
                    "query": f"find dependencies used by source case {case_ordinal}",
                    "cohort": (
                        "held_out"
                        if name == "held_out"
                        else "guard"
                        if case_ordinal <= 2
                        else "efficacy"
                    ),
                    "gold_target_path": gold,
                    "required_paths": [relevant[1]],
                    "relevant_paths": relevant,
                    "candidate_blind_target_missing": True,
                    "replacement": False,
                    "samples": samples,
                }
            )
    expanded = _expanded_schedule(schedule)
    evidence = {
        "corpus": name,
        "repository_universe": universe,
        "provider_status": "complete",
        "sealed_input_complete": True,
        "opened": True,
        "result_dependent_append": False,
        "retry_or_replacement": False,
        "retrieval_limits": {
            "top_k": copy.deepcopy(contract["retrieval"]["top_k"]),
            "budgets": copy.deepcopy(contract["retrieval"]["budgets"]),
        },
        "schedule": {
            "expanded_schedule": expanded,
            "expanded_sha256": _sha256(expanded),
        },
        "cases": cases,
    }
    binding = _corpus_binding(contract, evidence, name)
    evidence["payload_sha256"] = binding["payload_sha256"]
    evidence["corpus_seal_sha256"] = binding["public_seal_sha256"]
    return evidence


def _approval_projection(contract: dict[str, Any]) -> dict[str, Any]:
    projection = copy.deepcopy(contract)
    projection.pop("approval_receipt", None)
    return projection


def _authorization(
    contract: dict[str, Any], fresh: dict[str, Any], held_out: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    contract_projection_sha256 = _sha256(_approval_projection(contract))
    runner_identity = _sha256(contract["verification"]["runner"])
    receipt = {
        "schema_version": "p15-v8-approval-receipt-v1",
        "receipt_id": "approval-test-001",
        "approved_attempt_id": contract["attempt_id"],
        "approved_candidate_commit": contract["candidate"]["commit"],
        "approved_candidate_tree": contract["candidate"]["tree"],
        "approved_contract_projection_sha256": contract_projection_sha256,
        "approved_runner_identity": runner_identity,
    }
    manifest = {
        "schema_version": "p15-v8-sealed-execution-manifest-v1",
        "sealed": True,
        "attempt_id": contract["attempt_id"],
        "candidate_commit": contract["candidate"]["commit"],
        "candidate_tree": contract["candidate"]["tree"],
        "contract_projection_sha256": contract_projection_sha256,
        "approval_receipt_sha256": _sha256(receipt),
        "runner_identity": runner_identity,
        "corpora": {
            "fresh": _corpus_binding(contract, fresh, "fresh"),
            "held_out": _corpus_binding(contract, held_out, "held_out"),
        },
        "schedule_sha256": {
            "fresh": contract["schedule"]["fresh"]["expanded_sha256"],
            "held_out": contract["schedule"]["held_out"]["expanded_sha256"],
        },
    }
    return receipt, manifest


def _inputs() -> dict[str, Any]:
    contract = _contract()
    fresh = _evidence(contract, "fresh")
    held_out = _evidence(contract, "held_out")
    receipt, manifest = _authorization(contract, fresh, held_out)
    return {
        "contract": contract,
        "approval_receipt": receipt,
        "execution_manifest": manifest,
        "fresh_evidence": fresh,
        "held_out_evidence": held_out,
        "comparator_reports": [
            {"case_id": case["case_id"], "status": "SUCCESS"}
            for case in fresh["cases"]
        ],
        "release_evidence": {
            "treatment_additional_planner_calls": 0,
            "treatment_additional_embedding_calls": 0,
            "tracked_privacy_leaks": 0,
            "topk_caps_or_budgets_increase": 0,
            "focused_tests": "pass",
            "product_full_suite": "pass",
            "ci": "pass",
            "supported_opt_in_config": "pass",
        },
        "governance_evidence": {
            "candidate_and_contract_bindings_exact": True,
            "no_tuning_after_seal": True,
            "evidence_complete": True,
            "approval_and_execution_manifest_match": True,
            "outcome_release_governance_separate": True,
        },
    }


def _unopened_held_out() -> dict[str, Any]:
    return {"corpus": "held_out", "opened": False, "cases": []}


def _remove_fresh_efficacy_gains(inputs: dict[str, Any]) -> None:
    for case in inputs["fresh_evidence"]["cases"]:
        if case["cohort"] != "efficacy":
            continue
        for sample in case["samples"]:
            for replay_ordinal, replay in enumerate(
                sample["treatment"]["replays"], start=1
            ):
                replay["top12"] = copy.deepcopy(
                    sample["control"]["replays"][replay_ordinal - 1]["top12"]
                )
                replay["rank1_path"] = replay["top12"][0]["path"]
                report = _promotion_report(treatment=False)
                report["status_counts"]["disabled"] = 0
                report["status_counts"]["no_eligible_closed_candidate"] = 1
                replay["promotion_report"] = report


def test_complete_all_pass_evidence_ships_with_three_separate_decisions() -> None:
    inputs = _inputs()

    result = evaluator.evaluate_closure(**inputs)

    assert result["outcome"]["status"] == "PASS"
    assert result["release"]["status"] == "PASS"
    assert result["governance"]["status"] == "PASS"
    assert result["final_disposition"] == "ship"
    assert result["outcome"]["fresh"]["observed"] == {
        "repositories": 2,
        "cases": 12,
        "planner_samples": 24,
        "local_arm_replays": 96,
        "valid_plans": 24,
        "fallback_plans": 0,
    }
    assert result["outcome"]["held_out"]["observed"] == {
        "repositories": 1,
        "cases": 4,
        "planner_samples": 8,
        "local_arm_replays": 32,
        "valid_plans": 8,
        "fallback_plans": 0,
    }
    assert result["comparator"] == {
        "policy": "report_only",
        "expected_reports": 12,
        "success_reports": 12,
        "incomplete_reports": 0,
    }
    assert evaluator.canonical_json_bytes(result) == _canonical_bytes(result)


def test_report_only_comparator_incomplete_is_recorded_without_changing_ship() -> None:
    inputs = _inputs()
    inputs["comparator_reports"][4]["status"] = "INCOMPLETE"

    result = evaluator.evaluate_closure(**inputs)

    assert result["comparator"]["success_reports"] == 11
    assert result["comparator"]["incomplete_reports"] == 1
    assert result["outcome"]["status"] == "PASS"
    assert result["release"]["status"] == "PASS"
    assert result["final_disposition"] == "ship"


def test_complete_outcome_failure_rejects() -> None:
    inputs = _inputs()
    _remove_fresh_efficacy_gains(inputs)
    inputs["held_out_evidence"] = _unopened_held_out()

    result = evaluator.evaluate_closure(**inputs)

    assert result["outcome"]["status"] == "FAIL"
    assert "fresh_stable_causal_new_targets" in result["outcome"]["failures"]
    assert result["release"]["status"] == "NOT_EVALUATED"
    assert result["governance"]["status"] == "NOT_EVALUATED"
    assert result["final_disposition"] == "reject"


def test_fresh_failure_with_opened_held_out_fails_closed() -> None:
    inputs = _inputs()
    _remove_fresh_efficacy_gains(inputs)

    with pytest.raises(evaluator.ValidationError, match="held-out.*opened before fresh pass"):
        evaluator.evaluate_closure(**inputs)


@pytest.mark.parametrize(
    "mode_counts",
    [
        {
            "exact_source_hint": 2,
            "exact_target_hint": 0,
            "semantic_pair_fallback": 0,
        },
        {
            "exact_source_hint": 1,
            "exact_target_hint": 1,
            "semantic_pair_fallback": 0,
        },
    ],
)
def test_two_promoted_paths_allow_same_or_mixed_closed_modes(
    mode_counts: dict[str, int],
) -> None:
    inputs = _inputs()
    case = inputs["fresh_evidence"]["cases"][0]
    secondary = "src/fresh-r01/secondary-1.py"
    treatment = case["samples"][0]["treatment"]
    for replay in treatment["replays"]:
        replay["top12"][-2] = {
            "path": secondary,
            "planner_dependency_hint_promotion": 0.25,
            "closed_exact_witness": _witness(secondary),
        }
        replay["promotion_report"]["mode_counts"] = copy.deepcopy(mode_counts)
        replay["promotion_report"]["promoted_path_count"] = 2

    result = evaluator.evaluate_closure(**inputs)

    assert result["outcome"]["status"] == "PASS"
    assert result["final_disposition"] == "ship"


def test_outcome_pass_with_release_failure_stays_local_only() -> None:
    inputs = _inputs()
    inputs["release_evidence"]["focused_tests"] = "fail"

    result = evaluator.evaluate_closure(**inputs)

    assert result["outcome"]["status"] == "PASS"
    assert result["release"] == {
        "status": "FAIL",
        "failures": ["focused_tests"],
        "local_latency_ms": {
            "control_median": 10.0,
            "treatment_median": 10.5,
        },
    }
    assert result["governance"]["status"] == "PASS"
    assert result["final_disposition"] == "local_efficacy_only"


def test_outcome_pass_with_governance_failure_stays_local_only() -> None:
    inputs = _inputs()
    inputs["governance_evidence"]["no_tuning_after_seal"] = False

    result = evaluator.evaluate_closure(**inputs)

    assert result["outcome"]["status"] == "PASS"
    assert result["release"]["status"] == "PASS"
    assert result["governance"] == {
        "status": "FAIL",
        "failures": ["no_tuning_after_seal"],
    }
    assert result["final_disposition"] == "local_efficacy_only"


def test_authorization_projection_is_external_and_manifest_binds_corpora() -> None:
    inputs = _inputs()

    authorization = evaluator.validate_authorization(
        inputs["contract"],
        inputs["approval_receipt"],
        inputs["execution_manifest"],
    )

    assert evaluator.contract_approval_projection(inputs["contract"]) == (
        _approval_projection(inputs["contract"])
    )
    assert authorization["contract_projection_sha256"] == _sha256(
        _approval_projection(inputs["contract"])
    )
    assert "approved_corpus_seals" not in inputs["approval_receipt"]
    assert "approved_schedule_sha256" not in inputs["approval_receipt"]
    assert authorization["corpora"] == inputs["execution_manifest"]["corpora"]


def test_manifest_internal_digests_block_corpus_seal_rebinding() -> None:
    inputs = _inputs()
    rebound_seal = "9" * 64
    inputs["execution_manifest"]["corpora"]["fresh"][
        "public_seal_sha256"
    ] = rebound_seal
    inputs["fresh_evidence"]["corpus_seal_sha256"] = rebound_seal

    with pytest.raises(evaluator.ValidationError, match="public seal"):
        evaluator.evaluate_closure(**inputs)


@pytest.mark.parametrize(
    "mutation",
    [
        "query",
        "gold",
        "relevant",
        "required",
        "repository_slot",
        "case_ordinal",
        "case_id",
        "repository_identity",
    ],
)
def test_same_public_seal_cannot_hide_case_input_tampering(mutation: str) -> None:
    inputs = _inputs()
    fresh = inputs["fresh_evidence"]
    case = fresh["cases"][0]
    if mutation == "query":
        case["query"] = "tampered target-derived query"
    elif mutation == "gold":
        case["gold_target_path"] = "src/tampered-gold.py"
    elif mutation == "relevant":
        case["relevant_paths"].append("src/tampered-relevant.py")
    elif mutation == "required":
        case["required_paths"].append("src/tampered-required.py")
    elif mutation == "repository_slot":
        case["repository_slot"] = "fresh-r02"
    elif mutation == "case_ordinal":
        case["case_ordinal"] = 2
    elif mutation == "case_id":
        case["case_id"] = "fresh-r01-case-2"
    else:
        fresh["repository_universe"][0]["repository_identity_sha256"] = "9" * 64

    with pytest.raises(evaluator.ValidationError, match="case projection|repository universe"):
        evaluator.evaluate_closure(**inputs)


@pytest.mark.parametrize(
    ("target", "path", "value", "message"),
    [
        (
            "approval_receipt",
            ("approved_contract_projection_sha256",),
            "0" * 64,
            "approval receipt.*projection",
        ),
        (
            "approval_receipt",
            ("approved_runner_identity",),
            "0" * 64,
            "approval receipt.*runner",
        ),
        (
            "execution_manifest",
            ("approval_receipt_sha256",),
            "0" * 64,
            "execution manifest.*receipt",
        ),
        (
            "execution_manifest",
            ("candidate_tree",),
            "0" * 40,
            "execution manifest.*candidate tree",
        ),
        (
            "execution_manifest",
            ("runner_identity",),
            "0" * 64,
            "execution manifest.*runner",
        ),
        (
            "execution_manifest",
            ("schedule_sha256", "held_out"),
            "0" * 64,
            "execution manifest.*schedule",
        ),
        (
            "fresh_evidence",
            ("corpus_seal_sha256",),
            "0" * 64,
            "fresh evidence public seal",
        ),
    ],
)
def test_receipt_manifest_hash_runner_seal_and_schedule_tampering_fails_closed(
    target: str, path: tuple[str, ...], value: object, message: str
) -> None:
    inputs = _inputs()
    parent = inputs[target]
    for part in path[:-1]:
        parent = parent[part]
    parent[path[-1]] = value

    with pytest.raises(evaluator.ValidationError, match=message):
        evaluator.evaluate_closure(**inputs)


def test_missing_receipt_fails_before_malformed_evidence_is_examined() -> None:
    inputs = _inputs()
    inputs["approval_receipt"].pop("receipt_id")
    inputs["fresh_evidence"] = {"credential": "must-not-be-inspected-first"}

    with pytest.raises(evaluator.ValidationError, match="approval receipt fields"):
        evaluator.evaluate_closure(**inputs)


@pytest.mark.parametrize("corpus", ["fresh_evidence", "held_out_evidence"])
def test_incomplete_fresh_or_held_out_matrix_is_blocked(corpus: str) -> None:
    inputs = _inputs()
    inputs[corpus]["cases"].pop()
    if corpus == "fresh_evidence":
        inputs["held_out_evidence"] = _unopened_held_out()

    result = evaluator.evaluate_closure(**inputs)

    assert result["outcome"]["status"] == "BLOCKED"
    assert result["release"]["status"] == "NOT_EVALUATED"
    assert result["governance"]["status"] == "NOT_EVALUATED"
    assert result["final_disposition"] == "blocked"


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("duplicate", "duplicates"),
        ("digest", "schedule digest"),
        ("replay_id", "replay id or order"),
    ],
)
def test_duplicate_or_tampered_schedule_is_invalid(
    mutation: str, message: str
) -> None:
    inputs = _inputs()
    fresh = inputs["fresh_evidence"]
    if mutation == "duplicate":
        fresh["schedule"]["expanded_schedule"][-1] = fresh["schedule"][
            "expanded_schedule"
        ][0]
    elif mutation == "digest":
        fresh["schedule"]["expanded_sha256"] = "0" * 64
    else:
        fresh["cases"][0]["samples"][0]["control"]["replays"][0][
            "replay_id"
        ] = "fresh-r01-c01-s1-control-r2"

    with pytest.raises(evaluator.ValidationError, match=message):
        evaluator.evaluate_closure(**inputs)


def test_closed_exact_witness_literal_tamper_is_invalid() -> None:
    inputs = _inputs()
    treatment = inputs["fresh_evidence"]["cases"][0]["samples"][0]["treatment"]
    for replay in treatment["replays"]:
        replay["top12"][-1]["closed_exact_witness"]["relation_kind"] = "calls"

    with pytest.raises(evaluator.ValidationError, match="witness relation_kind"):
        evaluator.evaluate_closure(**inputs)


def test_mode_status_report_is_closed_and_mutually_exclusive() -> None:
    inputs = _inputs()
    report = inputs["fresh_evidence"]["cases"][0]["samples"][0]["treatment"][
        "replays"
    ][0]["promotion_report"]
    report["mode_counts"]["unfrozen_mode"] = 1

    with pytest.raises(evaluator.ValidationError, match="mode counts.*fields"):
        evaluator.evaluate_closure(**inputs)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("capture", "shared capture"),
        ("control_factor", "treatment factor"),
        ("treatment_factor", "treatment factor"),
    ],
)
def test_shared_capture_and_sole_treatment_factor_are_exact(
    mutation: str, message: str
) -> None:
    inputs = _inputs()
    sample = inputs["fresh_evidence"]["cases"][0]["samples"][0]
    if mutation == "capture":
        sample["treatment"]["capture"]["embedding_sha256"] = "different"
    elif mutation == "control_factor":
        sample["control"]["consume_dependency_hints"] = True
    else:
        sample["treatment"]["consume_dependency_hints"] = False

    with pytest.raises(evaluator.ValidationError, match=message):
        evaluator.evaluate_closure(**inputs)


@pytest.mark.parametrize(
    ("corpus", "field", "value", "reason"),
    [
        ("fresh_evidence", "provider_status", "INCOMPLETE", "fresh_provider_incomplete"),
        ("held_out_evidence", "opened", False, "held_out_unopened"),
        (
            "held_out_evidence",
            "sealed_input_complete",
            False,
            "held_out_sealed_input_incomplete",
        ),
    ],
)
def test_provider_or_sealed_input_incomplete_is_blocked(
    corpus: str, field: str, value: object, reason: str
) -> None:
    inputs = _inputs()
    inputs[corpus][field] = value
    if corpus == "fresh_evidence":
        inputs["held_out_evidence"] = _unopened_held_out()

    result = evaluator.evaluate_closure(**inputs)

    assert reason in result["outcome"]["blocking_reasons"]
    assert result["final_disposition"] == "blocked"


def test_missing_comparator_report_is_invalid_evidence() -> None:
    inputs = _inputs()
    inputs["comparator_reports"].pop()

    with pytest.raises(evaluator.ValidationError, match="comparator report matrix"):
        evaluator.evaluate_closure(**inputs)


def test_added_removed_mode_and_no_op_counts_are_reported() -> None:
    result = evaluator.evaluate_closure(**_inputs())

    fresh = result["outcome"]["fresh"]
    held_out = result["outcome"]["held_out"]
    assert len(fresh["added_paths"]) == 24
    assert len(fresh["removed_paths"]) == 24
    assert len(held_out["added_paths"]) == 8
    assert len(held_out["removed_paths"]) == 8
    assert fresh["mode_counts"] == {
        "exact_source_hint": 48,
        "exact_target_hint": 0,
        "semantic_pair_fallback": 0,
    }
    assert fresh["status_counts"] == {
        "disabled": 48,
        "graph_unavailable": 0,
        "planner_not_ok": 0,
        "intent_mismatch": 0,
        "missing_activation_hint": 0,
        "no_eligible_closed_candidate": 0,
    }


def test_required_path_loss_fails_outcome() -> None:
    inputs = _inputs()
    inputs["held_out_evidence"] = _unopened_held_out()
    case = inputs["fresh_evidence"]["cases"][0]
    required = case["required_paths"][0]
    old_row = copy.deepcopy(case["samples"][0]["control"]["replays"][0]["top12"][-1])
    for replay in case["samples"][0]["treatment"]["replays"]:
        index = next(
            index for index, row in enumerate(replay["top12"]) if row["path"] == required
        )
        replay["top12"][index] = copy.deepcopy(old_row)

    result = evaluator.evaluate_closure(**inputs)

    assert result["outcome"]["status"] == "FAIL"
    assert result["outcome"]["fresh"]["required_losses"] == [
        {
            "case_id": case["case_id"],
            "sample_ordinal": 1,
            "path": required,
        }
    ]
    assert "fresh_required_target_losses" in result["outcome"]["failures"]
    assert result["final_disposition"] == "reject"


def test_rank_one_change_fails_outcome() -> None:
    inputs = _inputs()
    inputs["held_out_evidence"] = _unopened_held_out()
    sample = inputs["fresh_evidence"]["cases"][0]["samples"][0]
    for replay in sample["treatment"]["replays"]:
        replay["top12"][0], replay["top12"][1] = (
            replay["top12"][1],
            replay["top12"][0],
        )
        replay["rank1_path"] = replay["top12"][0]["path"]

    result = evaluator.evaluate_closure(**inputs)

    assert result["outcome"]["status"] == "FAIL"
    assert result["outcome"]["fresh"]["rank1_changes"] == [
        {"case_id": "fresh-r01-case-1", "sample_ordinal": 1}
    ]
    assert "fresh_rank_one_changes" in result["outcome"]["failures"]


def test_treatment_only_irrelevant_case_sample_paths_are_bounded() -> None:
    inputs = _inputs()
    inputs["held_out_evidence"] = _unopened_held_out()
    case = inputs["fresh_evidence"]["cases"][0]
    for sample in case["samples"]:
        noise = f"src/fresh-r01/noise-{sample['sample_ordinal']}.py"
        for replay in sample["treatment"]["replays"]:
            replay["top12"][-1] = {
                "path": noise,
                "planner_dependency_hint_promotion": 0.5,
                "closed_exact_witness": _witness(noise),
            }

    result = evaluator.evaluate_closure(**inputs)

    assert len(result["outcome"]["fresh"]["treatment_only_irrelevant"]) == 2
    assert "fresh_treatment_only_irrelevant" in result["outcome"]["failures"]
    assert result["final_disposition"] == "reject"


def test_fallbacks_remain_in_the_frozen_planner_denominator() -> None:
    inputs = _inputs()
    inputs["held_out_evidence"] = _unopened_held_out()
    samples = [
        sample
        for case in inputs["fresh_evidence"]["cases"]
        for sample in case["samples"]
    ]
    for sample in samples[:3]:
        sample["plan_status"] = "fallback"

    result = evaluator.evaluate_closure(**inputs)

    observed = result["outcome"]["fresh"]["observed"]
    assert observed["planner_samples"] == 24
    assert observed["valid_plans"] == 21
    assert observed["fallback_plans"] == 3
    assert "fresh_valid_plans" in result["outcome"]["failures"]


def test_additional_request_count_fails_release_without_changing_outcome() -> None:
    inputs = _inputs()
    inputs["fresh_evidence"]["cases"][0]["samples"][0]["treatment"][
        "additional_planner_requests"
    ] = 1
    inputs["release_evidence"]["treatment_additional_planner_calls"] = 1

    result = evaluator.evaluate_closure(**inputs)

    assert result["outcome"]["status"] == "PASS"
    assert result["release"]["status"] == "FAIL"
    assert "treatment_additional_planner_calls" in result["release"]["failures"]
    assert result["final_disposition"] == "local_efficacy_only"


def test_local_latency_budget_fails_release_without_changing_outcome() -> None:
    inputs = _inputs()
    for corpus in ("fresh_evidence", "held_out_evidence"):
        for case in inputs[corpus]["cases"]:
            for sample in case["samples"]:
                for replay in sample["treatment"]["replays"]:
                    replay["local_latency_ms"] = 20.0

    result = evaluator.evaluate_closure(**inputs)

    assert result["outcome"]["status"] == "PASS"
    assert result["release"]["failures"] == ["local_treatment_latency"]
    assert result["final_disposition"] == "local_efficacy_only"


@pytest.mark.parametrize(
    ("target", "key", "value"),
    [
        ("release_evidence", "credential", "secret"),
        ("governance_evidence", "Authorization-Header", "Bearer secret"),
        ("comparator_reports", "source_body", "private source"),
        ("release_evidence", "raw_exception", "traceback"),
        ("release_evidence", "note", "/Users/example/private/repo"),
    ],
)
def test_tracked_reports_reject_private_fields_and_absolute_local_paths(
    target: str, key: str, value: str
) -> None:
    inputs = _inputs()
    if target == "comparator_reports":
        inputs[target][0][key] = value
    else:
        inputs[target][key] = value

    with pytest.raises(evaluator.ValidationError, match="forbidden field|absolute local path"):
        evaluator.evaluate_closure(**inputs)


@pytest.mark.parametrize("mutation", ["limits", "top12"])
def test_topk_and_budget_caps_are_exact(mutation: str) -> None:
    inputs = _inputs()
    if mutation == "limits":
        inputs["fresh_evidence"]["retrieval_limits"]["budgets"][
            "max_graph_seed_signals"
        ] += 1
    else:
        inputs["fresh_evidence"]["cases"][0]["samples"][0]["control"][
            "replays"
        ][0]["top12"].pop()

    with pytest.raises(evaluator.ValidationError, match="TopK|budget"):
        evaluator.evaluate_closure(**inputs)


def test_reported_cap_increase_fails_release() -> None:
    inputs = _inputs()
    inputs["release_evidence"]["topk_caps_or_budgets_increase"] = 1

    result = evaluator.evaluate_closure(**inputs)

    assert result["release"]["status"] == "FAIL"
    assert result["release"]["failures"] == ["topk_caps_or_budgets_increase"]
    assert result["final_disposition"] == "local_efficacy_only"


def test_cli_reads_only_explicit_json_paths_and_writes_canonical_json(
    tmp_path: Path,
) -> None:
    inputs = _inputs()
    argument_names = {
        "contract": "contract",
        "approval-receipt": "approval_receipt",
        "execution-manifest": "execution_manifest",
        "fresh-evidence": "fresh_evidence",
        "held-out-evidence": "held_out_evidence",
        "comparator-reports": "comparator_reports",
        "release-evidence": "release_evidence",
        "governance-evidence": "governance_evidence",
    }
    command = [sys.executable, evaluator.__file__]
    for argument, key in argument_names.items():
        path = tmp_path / f"{argument}.json"
        path.write_bytes(_canonical_bytes(inputs[key]))
        command.extend((f"--{argument}", str(path)))

    completed = subprocess.run(command, check=True, capture_output=True)

    expected = evaluator.evaluate_closure(**inputs)
    assert completed.stdout == _canonical_bytes(expected) + b"\n"
    assert completed.stderr == b""


def test_evaluator_is_offline_and_has_no_implicit_evidence_discovery() -> None:
    source = inspect.getsource(evaluator)
    imported_roots = {
        alias.name.split(".", 1)[0]
        for node in ast.walk(ast.parse(source))
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in (
            node.names
            if isinstance(node, ast.Import)
            else [ast.alias(name=node.module or "")]
        )
    }

    assert imported_roots.isdisjoint(
        {"context_search_tool", "requests", "urllib", "httpx", "socket"}
    )
    for forbidden in (".quality", ".glob(", ".rglob(", "os.walk"):
        assert forbidden not in source


@pytest.mark.parametrize(
    "mutation",
    ["schedule", "budget", "outcome_gate", "privacy", "request_policy"],
)
def test_reapproval_cannot_change_frozen_v8_rules(mutation: str) -> None:
    contract = _contract()
    if mutation == "schedule":
        sample = contract["schedule"]["fresh"]["samples"][0]
        sample["replay_order"][0], sample["replay_order"][1] = (
            sample["replay_order"][1],
            sample["replay_order"][0],
        )
        contract["schedule"]["fresh"]["expanded_sha256"] = _sha256(
            _expanded_schedule(contract["schedule"]["fresh"])
        )
    elif mutation == "budget":
        contract["retrieval"]["budgets"]["max_graph_seed_signals"] = 513
    elif mutation == "outcome_gate":
        contract["gates"]["outcome"]["fresh"][
            "minimum_stable_causal_new_targets"
        ] = 0
    elif mutation == "privacy":
        contract["privacy"]["forbidden_in_evidence"].remove("credential")
    else:
        contract["online_identity"]["planner"]["treatment_additional_calls"] = 1
    fresh = _evidence(contract, "fresh")
    held_out = _evidence(contract, "held_out")
    receipt, manifest = _authorization(contract, fresh, held_out)

    with pytest.raises(evaluator.ValidationError, match="contract"):
        evaluator.validate_authorization(contract, receipt, manifest)


def test_arm_cannot_hide_a_second_treatment_input() -> None:
    inputs = _inputs()
    sample = inputs["fresh_evidence"]["cases"][0]["samples"][0]
    sample["control"]["query_sha256"] = "control-query"
    sample["treatment"]["query_sha256"] = "treatment-query"

    with pytest.raises(evaluator.ValidationError, match="arm fields"):
        evaluator.evaluate_closure(**inputs)


def test_disabled_control_cannot_report_a_promotion_mode() -> None:
    inputs = _inputs()
    control = inputs["fresh_evidence"]["cases"][0]["samples"][0]["control"]
    for replay in control["replays"]:
        replay["promotion_report"] = _promotion_report(treatment=True)

    with pytest.raises(evaluator.ValidationError, match="disabled control"):
        evaluator.evaluate_closure(**inputs)
