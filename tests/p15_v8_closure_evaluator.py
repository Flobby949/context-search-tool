from __future__ import annotations

import argparse
import copy
import hashlib
import json
import statistics
import sys
from pathlib import Path
from typing import Any


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
CAPTURE_FIELDS = (
    "validated_or_fallback_plan_sha256",
    "embedding_sha256",
    "base_roster_sha256",
    "shared_state_sha256",
)
WITNESS_FIELDS = (
    "source_signal_id",
    "source_chunk_id",
    "source_file_path",
    "relation_id",
    "target_signal_id",
    "target_chunk_id",
    "target_file_path",
    "relation_kind",
    "resolution",
    "producer",
    "resolution_basis",
)
RELEASE_EVIDENCE_FIELDS = {
    "treatment_additional_planner_calls",
    "treatment_additional_embedding_calls",
    "tracked_privacy_leaks",
    "topk_caps_or_budgets_increase",
    "focused_tests",
    "product_full_suite",
    "ci",
    "supported_opt_in_config",
}
FROZEN_TOP_K = {"semantic": 80, "lexical": 80, "final": 12}
FROZEN_BUDGETS = {
    "max_graph_seed_signals": 512,
    "max_resolved_graph_hops": 4,
    "max_signals_popped_per_query": 4096,
    "max_edges_examined_per_query": 16384,
    "max_frontier_entries_per_query": 8192,
    "max_relation_expanded_candidates": 1000,
}
FROZEN_SAMPLES = [
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
]
FROZEN_SCHEDULES = {
    "fresh": {
        "repository_slots": ["fresh-r01", "fresh-r02"],
        "case_ordinals": [1, 2, 3, 4, 5, 6],
        "samples": FROZEN_SAMPLES,
        "expanded_count": 96,
        "expanded_sha256": (
            "a4f91e62af9c2581294e0e6ddf2dde22d209fa86d5e087e8b2c834d5f38c51b4"
        ),
    },
    "held_out": {
        "repository_slots": ["heldout-r01"],
        "case_ordinals": [1, 2, 3, 4],
        "samples": FROZEN_SAMPLES,
        "expanded_count": 32,
        "expanded_sha256": (
            "729d075856570a10587744aa6d3200f059206b1ec7e08557e34b93e45bdd004f"
        ),
    },
}
FROZEN_OUTCOME_GATES = {
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
}
FROZEN_RELEASE_GATES = {
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
}
FROZEN_GOVERNANCE_GATES = {
    "candidate_and_contract_bindings_exact": True,
    "no_tuning_after_seal": True,
    "evidence_complete": True,
    "approval_and_execution_manifest_match": True,
    "outcome_release_governance_separate": True,
}
FROZEN_FORBIDDEN_EVIDENCE = [
    "credential",
    "authorization_header",
    "source_body",
    "absolute_local_path",
    "raw_exception",
]


class ValidationError(ValueError):
    pass


def canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def contract_approval_projection(contract: dict[str, Any]) -> dict[str, Any]:
    contract = _mapping(contract, "contract")
    if "contract_sha256" in contract:
        raise ValidationError("contract must not contain a circular self hash")
    embedded_receipt = contract.get("approval_receipt")
    if embedded_receipt is not None:
        embedded_receipt = _mapping(embedded_receipt, "contract approval_receipt")
        if any(value not in (False, "", None) for value in embedded_receipt.values()):
            raise ValidationError("approval receipt must remain external to contract")
    projection = copy.deepcopy(contract)
    projection.pop("approval_receipt", None)
    return projection


def validate_authorization(
    contract: dict[str, Any],
    approval_receipt: dict[str, Any],
    execution_manifest: dict[str, Any],
) -> dict[str, Any]:
    contract = _mapping(contract, "contract")
    approval_receipt = _mapping(approval_receipt, "approval receipt")
    execution_manifest = _mapping(execution_manifest, "execution manifest")
    _validate_contract(contract)

    projection_sha256 = canonical_sha256(contract_approval_projection(contract))
    candidate = _mapping(contract["candidate"], "candidate")
    runner = _mapping(contract["verification"]["runner"], "runner")
    runner_identity = canonical_sha256(runner)

    _exact_keys(
        approval_receipt,
        {
            "schema_version",
            "receipt_id",
            "approved_attempt_id",
            "approved_candidate_commit",
            "approved_candidate_tree",
            "approved_contract_projection_sha256",
            "approved_runner_identity",
        },
        "approval receipt",
    )
    expected_receipt = {
        "schema_version": "p15-v8-approval-receipt-v1",
        "approved_attempt_id": contract["attempt_id"],
        "approved_candidate_commit": candidate["commit"],
        "approved_candidate_tree": candidate["tree"],
        "approved_contract_projection_sha256": projection_sha256,
        "approved_runner_identity": runner_identity,
    }
    for key, expected in expected_receipt.items():
        if approval_receipt.get(key) != expected:
            raise ValidationError(f"approval receipt {key} mismatch")
    _nonempty_string(approval_receipt.get("receipt_id"), "approval receipt receipt_id")

    _exact_keys(
        execution_manifest,
        {
            "schema_version",
            "sealed",
            "attempt_id",
            "candidate_commit",
            "candidate_tree",
            "contract_projection_sha256",
            "approval_receipt_sha256",
            "runner_identity",
            "corpora",
            "schedule_sha256",
        },
        "execution manifest",
    )
    if execution_manifest.get("schema_version") != (
        "p15-v8-sealed-execution-manifest-v1"
    ):
        raise ValidationError("execution manifest schema_version mismatch")
    if execution_manifest.get("sealed") is not True:
        raise ValidationError("execution manifest is not sealed")
    expected_manifest = {
        "attempt_id": contract["attempt_id"],
        "candidate_commit": candidate["commit"],
        "candidate_tree": candidate["tree"],
        "contract_projection_sha256": projection_sha256,
        "approval_receipt_sha256": canonical_sha256(approval_receipt),
        "runner_identity": runner_identity,
        "schedule_sha256": {
            "fresh": contract["schedule"]["fresh"]["expanded_sha256"],
            "held_out": contract["schedule"]["held_out"]["expanded_sha256"],
        },
    }
    for key, expected in expected_manifest.items():
        if execution_manifest.get(key) != expected:
            raise ValidationError(
                f"execution manifest {key.replace('_', ' ')} mismatch"
            )
    corpora = _mapping(
        execution_manifest.get("corpora"), "execution manifest corpora"
    )
    _exact_keys(corpora, {"fresh", "held_out"}, "execution manifest corpora")
    validated_corpora = {
        name: _validate_manifest_corpus(name, corpora.get(name), contract)
        for name in ("fresh", "held_out")
    }
    return {
        "contract_projection_sha256": projection_sha256,
        "approval_receipt_sha256": canonical_sha256(approval_receipt),
        "runner_identity": runner_identity,
        "corpora": validated_corpora,
        "schedule_sha256": copy.deepcopy(expected_manifest["schedule_sha256"]),
    }


def _validate_manifest_corpus(
    name: str, value: object, contract: dict[str, Any]
) -> dict[str, Any]:
    binding = _mapping(value, f"execution manifest {name} corpus")
    _exact_keys(
        binding,
        {
            "repository_universe",
            "repository_universe_sha256",
            "case_projections",
            "case_projection_sha256",
            "payload_sha256",
            "public_seal_sha256",
        },
        f"execution manifest {name} corpus",
    )
    schedule = contract["schedule"][name]
    universe = binding.get("repository_universe")
    if not isinstance(universe, list):
        raise ValidationError(f"execution manifest {name} repository universe must be a list")
    expected_slots = schedule["repository_slots"]
    if [item.get("repository_slot") for item in universe if isinstance(item, dict)] != (
        expected_slots
    ):
        raise ValidationError(f"execution manifest {name} repository universe order mismatch")
    identities: dict[str, str] = {}
    for item in universe:
        item = _mapping(item, f"execution manifest {name} repository identity")
        _exact_keys(
            item,
            {"repository_slot", "repository_identity_sha256"},
            f"execution manifest {name} repository identity",
        )
        slot = _nonempty_string(item["repository_slot"], "repository slot")
        identities[slot] = _sha256_string(
            item["repository_identity_sha256"], "repository identity"
        )
    universe_sha256 = canonical_sha256(universe)
    if binding.get("repository_universe_sha256") != universe_sha256:
        raise ValidationError(f"execution manifest {name} repository universe digest mismatch")

    projections = binding.get("case_projections")
    if not isinstance(projections, list):
        raise ValidationError(f"execution manifest {name} case projections must be a list")
    expected_cases = [
        (slot, ordinal)
        for slot in expected_slots
        for ordinal in schedule["case_ordinals"]
    ]
    if len(projections) != len(expected_cases):
        raise ValidationError(f"execution manifest {name} case projection count mismatch")
    for projection, (slot, ordinal) in zip(projections, expected_cases, strict=True):
        projection = _mapping(projection, f"execution manifest {name} case projection")
        _exact_keys(
            projection,
            {
                "repository_slot",
                "repository_identity_sha256",
                "case_ordinal",
                "case_id",
                "query_sha256",
                "gold_sha256",
                "relevant_sha256",
                "required_sha256",
                "projection_sha256",
            },
            f"execution manifest {name} case projection",
        )
        expected_identity = identities[slot]
        expected_id = f"{slot}-case-{ordinal}"
        if (
            projection.get("repository_slot") != slot
            or projection.get("repository_identity_sha256") != expected_identity
            or projection.get("case_ordinal") != ordinal
            or projection.get("case_id") != expected_id
        ):
            raise ValidationError(f"execution manifest {name} case projection order mismatch")
        for field in (
            "query_sha256",
            "gold_sha256",
            "relevant_sha256",
            "required_sha256",
        ):
            _sha256_string(projection.get(field), f"case projection {field}")
        core = {key: projection[key] for key in projection if key != "projection_sha256"}
        if projection.get("projection_sha256") != canonical_sha256(core):
            raise ValidationError(f"execution manifest {name} case projection digest mismatch")
    case_projection_sha256 = canonical_sha256(projections)
    if binding.get("case_projection_sha256") != case_projection_sha256:
        raise ValidationError(f"execution manifest {name} case projection set mismatch")
    payload_sha256 = canonical_sha256(
        {
            "repository_universe_sha256": universe_sha256,
            "case_projection_sha256": case_projection_sha256,
        }
    )
    if binding.get("payload_sha256") != payload_sha256:
        raise ValidationError(f"execution manifest {name} payload digest mismatch")
    public_seal_sha256 = canonical_sha256(
        {
            "corpus": name,
            "payload_sha256": payload_sha256,
            "schedule_sha256": schedule["expanded_sha256"],
        }
    )
    if binding.get("public_seal_sha256") != public_seal_sha256:
        raise ValidationError(f"execution manifest {name} public seal mismatch")
    return copy.deepcopy(binding)


def evaluate_closure(
    *,
    contract: dict[str, Any],
    approval_receipt: dict[str, Any],
    execution_manifest: dict[str, Any],
    fresh_evidence: dict[str, Any],
    held_out_evidence: dict[str, Any],
    comparator_reports: list[dict[str, Any]],
    release_evidence: dict[str, Any],
    governance_evidence: dict[str, Any],
) -> dict[str, Any]:
    authorization = validate_authorization(
        contract, approval_receipt, execution_manifest
    )
    fresh_reports = {
        "fresh_evidence": fresh_evidence,
        "comparator_reports": comparator_reports,
    }
    _validate_privacy(fresh_reports, contract["privacy"])

    fresh = _evaluate_corpus(
        "fresh",
        fresh_evidence,
        contract,
        authorization["corpora"]["fresh"],
    )
    comparator = _evaluate_comparator(
        comparator_reports, contract, contract["gates"]["comparator"]
    )
    if fresh["blocking_reasons"]:
        _validate_unopened_held_out(held_out_evidence)
        return {
            "schema_version": "p15-v8-closure-evaluation-v1",
            "authorization": authorization,
            "outcome": {
                "status": "BLOCKED",
                "blocking_reasons": fresh["blocking_reasons"],
                "fresh": _public_corpus_result(fresh),
                "held_out": {"status": "NOT_EVALUATED"},
            },
            "release": {"status": "NOT_EVALUATED", "failures": []},
            "governance": {"status": "NOT_EVALUATED", "failures": []},
            "comparator": comparator,
            "final_disposition": "blocked",
        }

    fresh_failures = _fresh_outcome_failures(
        fresh, contract["gates"]["outcome"]["fresh"]
    )
    if fresh_failures:
        _validate_unopened_held_out(held_out_evidence)
        return {
            "schema_version": "p15-v8-closure-evaluation-v1",
            "authorization": authorization,
            "outcome": {
                "status": "FAIL",
                "failures": fresh_failures,
                "fresh": _public_corpus_result(fresh),
                "held_out": {"status": "NOT_EVALUATED"},
            },
            "release": {"status": "NOT_EVALUATED", "failures": []},
            "governance": {"status": "NOT_EVALUATED", "failures": []},
            "comparator": comparator,
            "final_disposition": "reject",
        }

    _validate_privacy(
        {
            "held_out_evidence": held_out_evidence,
            "release_evidence": release_evidence,
            "governance_evidence": governance_evidence,
        },
        contract["privacy"],
    )
    held_out = _evaluate_corpus(
        "held_out",
        held_out_evidence,
        contract,
        authorization["corpora"]["held_out"],
    )
    if held_out["blocking_reasons"]:
        return {
            "schema_version": "p15-v8-closure-evaluation-v1",
            "authorization": authorization,
            "outcome": {
                "status": "BLOCKED",
                "blocking_reasons": held_out["blocking_reasons"],
                "fresh": _public_corpus_result(fresh),
                "held_out": _public_corpus_result(held_out),
            },
            "release": {"status": "NOT_EVALUATED", "failures": []},
            "governance": {"status": "NOT_EVALUATED", "failures": []},
            "comparator": comparator,
            "final_disposition": "blocked",
        }

    outcome_failures = _held_out_outcome_failures(
        held_out, contract["gates"]["outcome"]["held_out"]
    )
    release = _release_decision(
        fresh, held_out, release_evidence, contract["gates"]["release"]
    )
    governance = _governance_decision(
        governance_evidence, contract["gates"]["governance"]
    )
    outcome_status = "FAIL" if outcome_failures else "PASS"
    if outcome_status == "FAIL":
        disposition = "reject"
    elif release["status"] == "FAIL" or governance["status"] == "FAIL":
        disposition = "local_efficacy_only"
    else:
        disposition = "ship"
    return {
        "schema_version": "p15-v8-closure-evaluation-v1",
        "authorization": authorization,
        "outcome": {
            "status": outcome_status,
            "failures": outcome_failures,
            "fresh": _public_corpus_result(fresh),
            "held_out": _public_corpus_result(held_out),
        },
        "release": release,
        "governance": governance,
        "comparator": comparator,
        "final_disposition": disposition,
    }


def _validate_contract(contract: dict[str, Any]) -> None:
    _nonempty_string(contract.get("attempt_id"), "contract attempt_id")
    candidate = _mapping(contract.get("candidate"), "contract candidate")
    _sha1_string(candidate.get("commit"), "candidate commit")
    _sha1_string(candidate.get("tree"), "candidate tree")
    if contract.get("treatment") != {
        "only_factor": "consume_dependency_hints",
        "control": False,
        "treatment": True,
        "all_other_inputs_shared": True,
    }:
        raise ValidationError("contract treatment factor is not the frozen v8 factor")
    behavior = _mapping(contract.get("behavior"), "contract behavior")
    if behavior.get("promotion_modes") != list(PROMOTION_MODES):
        raise ValidationError("contract promotion modes mismatch")
    if behavior.get("no_op_statuses") != list(NO_OP_STATUSES):
        raise ValidationError("contract no-op statuses mismatch")
    if behavior.get("maximum_promoted_paths") != 2:
        raise ValidationError("contract maximum promoted paths mismatch")
    if behavior.get("rank_one_protected") is not True:
        raise ValidationError("contract must protect rank one")
    if behavior.get("closed_exact_witness_required") is not True:
        raise ValidationError("contract must require closed exact witnesses")

    retrieval = _mapping(contract.get("retrieval"), "contract retrieval")
    top_k = _mapping(retrieval.get("top_k"), "contract top_k")
    if top_k != FROZEN_TOP_K:
        raise ValidationError("contract TopK values mismatch")
    budgets = _mapping(retrieval.get("budgets"), "contract budgets")
    if budgets != FROZEN_BUDGETS:
        raise ValidationError("contract retrieval budgets mismatch")
    if retrieval.get("caps_must_not_increase") is not True:
        raise ValidationError("contract must freeze retrieval caps")

    schedules = _mapping(contract.get("schedule"), "contract schedule")
    for name in ("fresh", "held_out"):
        schedule = _mapping(schedules.get(name), f"contract {name} schedule")
        if schedule != FROZEN_SCHEDULES[name]:
            raise ValidationError(f"contract {name} frozen schedule mismatch")
        expanded = _expand_schedule(schedule)
        if len(expanded) != schedule.get("expanded_count") or len(expanded) != len(
            set(expanded)
        ):
            raise ValidationError(f"contract {name} schedule cardinality mismatch")
        if canonical_sha256(expanded) != schedule.get("expanded_sha256"):
            raise ValidationError(f"contract {name} schedule digest mismatch")
    if schedules.get("result_dependent_append_allowed") is not False:
        raise ValidationError("contract allows result-dependent append")
    if schedules.get("retry_or_replacement_allowed") is not False:
        raise ValidationError("contract allows retry or replacement")
    if schedules.get("all_cases_complete_before_decision") is not True:
        raise ValidationError("contract permits an early decision")

    online_identity = _mapping(
        contract.get("online_identity"), "contract online identity"
    )
    planner = _mapping(online_identity.get("planner"), "contract planner identity")
    embedding = _mapping(
        online_identity.get("embedding"), "contract embedding identity"
    )
    if planner.get("calls_per_case_sample") != 1:
        raise ValidationError("contract planner request policy mismatch")
    if planner.get("treatment_additional_calls") != 0:
        raise ValidationError("contract planner request policy mismatch")
    if embedding.get("treatment_additional_calls") != 0:
        raise ValidationError("contract embedding request policy mismatch")

    privacy = _mapping(contract.get("privacy"), "contract privacy")
    if privacy.get("forbidden_in_evidence") != FROZEN_FORBIDDEN_EVIDENCE:
        raise ValidationError("contract privacy fields mismatch")
    if privacy.get("tracked_leak_count_limit") != 0:
        raise ValidationError("contract privacy leak limit mismatch")

    gates = _mapping(contract.get("gates"), "contract gates")
    outcome_gates = _mapping(gates.get("outcome"), "contract outcome gates")
    for name, expected in FROZEN_OUTCOME_GATES.items():
        _require_fields(
            _mapping(outcome_gates.get(name), f"contract {name} outcome gate"),
            expected,
            f"contract {name} outcome gate",
        )
    _require_fields(
        _mapping(gates.get("release"), "contract release gates"),
        FROZEN_RELEASE_GATES,
        "contract release gates",
    )
    _require_fields(
        _mapping(gates.get("governance"), "contract governance gates"),
        FROZEN_GOVERNANCE_GATES,
        "contract governance gates",
    )

    comparator = _mapping(
        gates.get("comparator"), "contract comparator"
    )
    if comparator != {
        "name": "fast-context",
        "policy": "report_only",
        "scope": "fresh_12_cases",
        "expected_reports": 12,
        "post_hoc_policy_change_allowed": False,
        "unavailable_disposition": "record_INCOMPLETE_without_gate_waiver",
    }:
        raise ValidationError("contract comparator policy mismatch")
    runner = _mapping(
        contract.get("verification", {}).get("runner"), "contract runner"
    )
    _exact_keys(
        runner,
        {"path", "sha256", "role", "online_collection_authorized"},
        "contract runner",
    )
    if runner.get("path") != "tests/p15_v8_closure_evaluator.py":
        raise ValidationError("contract runner path mismatch")
    if runner.get("role") != "tracked_offline_closure_evaluator_only":
        raise ValidationError("contract runner role mismatch")
    if runner.get("online_collection_authorized") is not False:
        raise ValidationError("contract runner cannot authorize online collection")
    _sha256_string(runner.get("sha256"), "contract runner sha256")
    contract_approval_projection(contract)


def _validate_evidence_case_projections(
    name: str,
    cases: list[dict[str, Any]],
    binding: dict[str, Any],
) -> None:
    identities = {
        item["repository_slot"]: item["repository_identity_sha256"]
        for item in binding["repository_universe"]
    }
    expected = {
        (item["repository_slot"], item["case_ordinal"]): item
        for item in binding["case_projections"]
    }
    for raw_case in cases:
        case = _mapping(raw_case, f"{name} case")
        slot = _nonempty_string(case.get("repository_slot"), "case repository slot")
        ordinal = _positive_int(case.get("case_ordinal"), "case ordinal")
        if slot not in identities or (slot, ordinal) not in expected:
            raise ValidationError(f"{name} evidence case projection is outside manifest")
        case_id = _nonempty_string(case.get("case_id"), "case_id")
        if case_id != f"{slot}-case-{ordinal}":
            raise ValidationError(f"{name} evidence case projection case_id mismatch")
        relevant = sorted(
            _repo_path_set(case.get("relevant_paths"), "case relevant paths")
        )
        required = sorted(
            _repo_path_set(case.get("required_paths"), "case required paths")
        )
        core = {
            "repository_slot": slot,
            "repository_identity_sha256": identities[slot],
            "case_ordinal": ordinal,
            "case_id": case_id,
            "query_sha256": canonical_sha256(
                _nonempty_string(case.get("query"), "case query")
            ),
            "gold_sha256": canonical_sha256(
                _repo_path(case.get("gold_target_path"), "case gold target")
            ),
            "relevant_sha256": canonical_sha256(relevant),
            "required_sha256": canonical_sha256(required),
        }
        observed = {**core, "projection_sha256": canonical_sha256(core)}
        if observed != expected[(slot, ordinal)]:
            raise ValidationError(f"{name} evidence case projection mismatch")


def _evaluate_corpus(
    name: str,
    evidence: dict[str, Any],
    contract: dict[str, Any],
    binding: dict[str, Any],
) -> dict[str, Any]:
    evidence = _mapping(evidence, f"{name} evidence")
    if evidence.get("corpus") != name:
        raise ValidationError(f"{name} evidence corpus label mismatch")
    if evidence.get("corpus_seal_sha256") != binding["public_seal_sha256"]:
        raise ValidationError(f"{name} evidence public seal mismatch")
    if evidence.get("payload_sha256") != binding["payload_sha256"]:
        raise ValidationError(f"{name} evidence payload digest mismatch")
    if evidence.get("repository_universe") != binding["repository_universe"]:
        raise ValidationError(f"{name} evidence repository universe mismatch")
    if evidence.get("result_dependent_append") is not False:
        raise ValidationError(f"{name} evidence contains result-dependent append")
    if evidence.get("retry_or_replacement") is not False:
        raise ValidationError(f"{name} evidence contains retry or replacement")
    if evidence.get("retrieval_limits") != {
        "top_k": contract["retrieval"]["top_k"],
        "budgets": contract["retrieval"]["budgets"],
    }:
        raise ValidationError(f"{name} evidence TopK or budget mismatch")
    _validate_evidence_schedule(name, evidence, contract)

    cases = evidence.get("cases")
    if not isinstance(cases, list):
        raise ValidationError(f"{name} evidence cases must be a list")
    _validate_evidence_case_projections(name, cases, binding)
    expected_schedule = contract["schedule"][name]
    expected_keys = [
        (slot, ordinal)
        for slot in expected_schedule["repository_slots"]
        for ordinal in expected_schedule["case_ordinals"]
    ]
    observed_keys = []
    for case in cases:
        case = _mapping(case, f"{name} case")
        observed_keys.append((case.get("repository_slot"), case.get("case_ordinal")))
    if len(observed_keys) != len(set(observed_keys)):
        raise ValidationError(f"{name} evidence has duplicate cases")
    if any(key not in expected_keys for key in observed_keys):
        raise ValidationError(f"{name} evidence has an unexpected case")
    if observed_keys != [key for key in expected_keys if key in set(observed_keys)]:
        raise ValidationError(f"{name} evidence case order mismatch")

    provider_complete = evidence.get("provider_status") == "complete"
    sealed_complete = evidence.get("sealed_input_complete") is True
    opened = evidence.get("opened") is True
    structurally_complete = observed_keys == expected_keys
    for case in cases:
        samples = case.get("samples")
        if not isinstance(samples, list) or [
            sample.get("sample_ordinal") for sample in samples if isinstance(sample, dict)
        ] != [1, 2]:
            structurally_complete = False
            continue
        if any(
            not isinstance(sample.get(arm), dict)
            or not isinstance(sample[arm].get("replays"), list)
            or len(sample[arm]["replays"]) != 2
            for sample in samples
            for arm in ("control", "treatment")
        ):
            structurally_complete = False

    blocking_reasons = []
    if not provider_complete:
        blocking_reasons.append(f"{name}_provider_incomplete")
    if not sealed_complete:
        blocking_reasons.append(f"{name}_sealed_input_incomplete")
    if name == "held_out" and not opened:
        blocking_reasons.append("held_out_unopened")
    if not structurally_complete:
        blocking_reasons.append(f"{name}_matrix_incomplete")
    observed = {
        "repositories": len({key[0] for key in observed_keys}),
        "cases": len(cases),
        "planner_samples": sum(
            len(case.get("samples", []))
            for case in cases
            if isinstance(case.get("samples"), list)
        ),
        "local_arm_replays": sum(
            len(sample.get(arm, {}).get("replays", []))
            for case in cases
            for sample in case.get("samples", [])
            if isinstance(sample, dict)
            for arm in ("control", "treatment")
        ),
        "valid_plans": 0,
        "fallback_plans": 0,
    }
    base = {
        "observed": observed,
        "blocking_reasons": blocking_reasons,
        "stable_causal_new_targets": [],
        "required_losses": [],
        "rank1_changes": [],
        "added_paths": [],
        "removed_paths": [],
        "treatment_only_irrelevant": [],
        "candidate_blind_target_missing_cases": 0,
        "precision_at_12_delta": 0.0,
        "repositories_with_gain": [],
        "latencies": {"control": [], "treatment": []},
        "additional_requests": {"planner": 0, "embedding": 0},
        "mode_counts": {mode: 0 for mode in PROMOTION_MODES},
        "status_counts": {status: 0 for status in NO_OP_STATUSES},
    }
    if blocking_reasons:
        return {**base, "matrix_complete": False}

    relevant_control_hits = 0
    relevant_treatment_hits = 0
    precision_slots = 0
    repositories_with_gain: set[str] = set()
    for case in cases:
        case_id = _nonempty_string(case.get("case_id"), f"{name} case_id")
        slot = _nonempty_string(case.get("repository_slot"), f"{case_id} repository_slot")
        ordinal = _positive_int(case.get("case_ordinal"), f"{case_id} case_ordinal")
        expected_cohort = (
            "held_out"
            if name == "held_out"
            else "guard"
            if ordinal in contract["corpus"]["fresh"]["guard_ordinals"]
            else "efficacy"
        )
        if case.get("cohort") != expected_cohort:
            raise ValidationError(f"{case_id} cohort mismatch")
        if case.get("replacement") is not False:
            raise ValidationError(f"{case_id} replacement is forbidden")
        gold = _repo_path(case.get("gold_target_path"), f"{case_id} gold target")
        relevant = _repo_path_set(case.get("relevant_paths"), f"{case_id} relevant paths")
        relevant.add(gold)
        required = _repo_path_set(case.get("required_paths"), f"{case_id} required paths")
        if name == "held_out" and case.get("candidate_blind_target_missing") is True:
            base["candidate_blind_target_missing_cases"] += 1
        sample_gold_gains = []
        for sample in case["samples"]:
            sample_ordinal = sample["sample_ordinal"]
            plan_status = sample.get("plan_status")
            if plan_status not in {"ok", "fallback"}:
                raise ValidationError(f"{case_id} sample plan status is invalid")
            observed["valid_plans" if plan_status == "ok" else "fallback_plans"] += 1
            control = _validate_arm(
                case_id, sample_ordinal, "control", sample["control"], contract
            )
            treatment = _validate_arm(
                case_id, sample_ordinal, "treatment", sample["treatment"], contract
            )
            if control["capture"] != treatment["capture"]:
                raise ValidationError(f"{case_id} sample {sample_ordinal} shared capture mismatch")
            control_paths = set(control["paths"])
            treatment_paths = set(treatment["paths"])
            added = sorted(treatment_paths - control_paths)
            removed = sorted(control_paths - treatment_paths)
            if treatment["promoted_path_count"] != len(added):
                raise ValidationError(f"{case_id} sample {sample_ordinal} promotion count mismatch")
            if added and treatment["report_kind"] != "mode":
                raise ValidationError(f"{case_id} sample {sample_ordinal} added path lacks mode report")
            if not added and (
                treatment["report_kind"] != "status"
                or treatment["promoted_path_count"] != 0
            ):
                raise ValidationError(f"{case_id} sample {sample_ordinal} no-op report mismatch")
            treatment_rows = {row["path"]: row for row in treatment["rows"]}
            for path in added:
                _validate_added_row(treatment_rows[path], path)
                base["added_paths"].append(
                    {"case_id": case_id, "sample_ordinal": sample_ordinal, "path": path}
                )
            for path in removed:
                base["removed_paths"].append(
                    {"case_id": case_id, "sample_ordinal": sample_ordinal, "path": path}
                )
            for path in sorted(required.intersection(control_paths) - treatment_paths):
                base["required_losses"].append(
                    {"case_id": case_id, "sample_ordinal": sample_ordinal, "path": path}
                )
            if control["rank1_path"] != treatment["rank1_path"]:
                base["rank1_changes"].append(
                    {"case_id": case_id, "sample_ordinal": sample_ordinal}
                )
            for path in added:
                if path not in relevant:
                    base["treatment_only_irrelevant"].append(
                        {"case_id": case_id, "sample_ordinal": sample_ordinal, "path": path}
                    )
            sample_gold_gains.append(gold in added)
            relevant_control_hits += len(control_paths.intersection(relevant))
            relevant_treatment_hits += len(treatment_paths.intersection(relevant))
            precision_slots += contract["retrieval"]["top_k"]["final"]
            base["latencies"]["control"].extend(control["latencies"])
            base["latencies"]["treatment"].extend(treatment["latencies"])
            base["additional_requests"]["planner"] += treatment[
                "additional_planner_requests"
            ]
            base["additional_requests"]["embedding"] += treatment[
                "additional_embedding_requests"
            ]
            for mode, count in control["mode_counts"].items():
                base["mode_counts"][mode] += count
            for mode, count in treatment["mode_counts"].items():
                base["mode_counts"][mode] += count
            for status, count in control["status_counts"].items():
                base["status_counts"][status] += count
            for status, count in treatment["status_counts"].items():
                base["status_counts"][status] += count
        if all(sample_gold_gains):
            base["stable_causal_new_targets"].append(
                {
                    "case_id": case_id,
                    "repository_slot": slot,
                    "cohort": expected_cohort,
                    "path": gold,
                }
            )
            if expected_cohort == "efficacy":
                repositories_with_gain.add(slot)
    base["repositories_with_gain"] = sorted(repositories_with_gain)
    base["precision_at_12_delta"] = (
        (relevant_treatment_hits - relevant_control_hits) / precision_slots
        if precision_slots
        else 0.0
    )
    return {**base, "matrix_complete": True}


def _validate_arm(
    case_id: str,
    sample_ordinal: int,
    arm_name: str,
    arm: dict[str, Any],
    contract: dict[str, Any],
) -> dict[str, Any]:
    arm = _mapping(arm, f"{case_id} sample {sample_ordinal} {arm_name}")
    _exact_keys(
        arm,
        {
            "consume_dependency_hints",
            "capture",
            "additional_planner_requests",
            "additional_embedding_requests",
            "replays",
        },
        f"{case_id} sample {sample_ordinal} arm",
    )
    expected_factor = arm_name == "treatment"
    if arm.get("consume_dependency_hints") is not expected_factor:
        raise ValidationError(f"{case_id} sample {sample_ordinal} treatment factor mismatch")
    capture = _mapping(arm.get("capture"), f"{case_id} sample capture")
    _exact_keys(capture, set(CAPTURE_FIELDS), f"{case_id} sample capture")
    for field, value in capture.items():
        _nonempty_string(value, f"{case_id} capture {field}")
    additional_planner = _nonnegative_int(
        arm.get("additional_planner_requests"), "additional planner requests"
    )
    additional_embedding = _nonnegative_int(
        arm.get("additional_embedding_requests"), "additional embedding requests"
    )
    replays = arm.get("replays")
    if not isinstance(replays, list) or len(replays) != 2:
        raise ValidationError(f"{case_id} sample {sample_ordinal} arm needs two replays")
    projections = []
    latencies = []
    aggregate_modes = {mode: 0 for mode in PROMOTION_MODES}
    aggregate_statuses = {status: 0 for status in NO_OP_STATUSES}
    slot, case_ordinal_text = case_id.rsplit("-case-", 1)
    for replay_ordinal, replay in enumerate(replays, start=1):
        replay = _mapping(replay, f"{case_id} replay")
        expected_id = (
            f"{slot}-c{int(case_ordinal_text):02d}-s{sample_ordinal}-"
            f"{arm_name}-r{replay_ordinal}"
        )
        if replay.get("replay_id") != expected_id:
            raise ValidationError(f"{case_id} replay id or order mismatch")
        rows = replay.get("top12")
        final_top_k = contract["retrieval"]["top_k"]["final"]
        if not isinstance(rows, list) or len(rows) != final_top_k:
            raise ValidationError(f"{case_id} replay TopK cardinality mismatch")
        paths = [_repo_path(row.get("path"), f"{case_id} result path") for row in rows]
        if len(paths) != len(set(paths)):
            raise ValidationError(f"{case_id} replay contains duplicate result paths")
        if replay.get("rank1_path") != paths[0]:
            raise ValidationError(f"{case_id} replay rank1 projection mismatch")
        latency = replay.get("local_latency_ms")
        if not _is_nonnegative_number(latency):
            raise ValidationError(f"{case_id} replay latency is invalid")
        report = _validate_promotion_report(
            replay.get("promotion_report"), contract["behavior"]
        )
        if arm_name == "control" and (
            report["kind"] != "status"
            or report["promoted_path_count"] != 0
            or report["status_counts"]
            != {
                status: 1 if status == "disabled" else 0
                for status in NO_OP_STATUSES
            }
        ):
            raise ValidationError("disabled control promotion report mismatch")
        for mode, count in report["mode_counts"].items():
            aggregate_modes[mode] += count
        for status, count in report["status_counts"].items():
            aggregate_statuses[status] += count
        projections.append(
            {
                "rows": rows,
                "rank1_path": replay["rank1_path"],
                "promotion_report": replay["promotion_report"],
            }
        )
        latencies.append(float(latency))
    if projections[0] != projections[1]:
        raise ValidationError(f"{case_id} sample {sample_ordinal} replay is unstable")
    report = _validate_promotion_report(
        replays[0]["promotion_report"], contract["behavior"]
    )
    return {
        "capture": capture,
        "rows": replays[0]["top12"],
        "paths": [row["path"] for row in replays[0]["top12"]],
        "rank1_path": replays[0]["rank1_path"],
        "latencies": latencies,
        "additional_planner_requests": additional_planner,
        "additional_embedding_requests": additional_embedding,
        "report_kind": report["kind"],
        "promoted_path_count": report["promoted_path_count"],
        "mode_counts": aggregate_modes,
        "status_counts": aggregate_statuses,
    }


def _validate_promotion_report(
    report: dict[str, Any], behavior: dict[str, Any]
) -> dict[str, Any]:
    report = _mapping(report, "promotion report")
    _exact_keys(
        report,
        {
            "trace_schema_version",
            "stage",
            "mode_counts",
            "status_counts",
            "promoted_path_count",
        },
        "promotion report",
    )
    if report.get("trace_schema_version") != 1 or report.get("stage") != (
        "dependency_promotion"
    ):
        raise ValidationError("promotion report identity mismatch")
    modes = _mapping(report.get("mode_counts"), "promotion mode counts")
    statuses = _mapping(report.get("status_counts"), "promotion status counts")
    _exact_keys(modes, set(PROMOTION_MODES), "promotion mode counts")
    _exact_keys(statuses, set(NO_OP_STATUSES), "promotion status counts")
    if not all(_is_nonnegative_int(value) for value in (*modes.values(), *statuses.values())):
        raise ValidationError("promotion mode/status counts must be nonnegative integers")
    mode_total = sum(modes.values())
    status_total = sum(statuses.values())
    promoted = _nonnegative_int(
        report.get("promoted_path_count"), "promoted path count"
    )
    no_op = status_total == 1 and mode_total == 0 and promoted == 0
    promotion = (
        status_total == 0
        and mode_total == promoted
        and 1 <= promoted <= behavior["maximum_promoted_paths"]
    )
    if not (no_op or promotion):
        raise ValidationError("promotion report mode/status/promoted counts mismatch")
    return {
        "kind": "mode" if promotion else "status",
        "mode_counts": modes,
        "status_counts": statuses,
        "promoted_path_count": promoted,
    }


def _validate_added_row(row: dict[str, Any], path: str) -> None:
    marker = row.get("planner_dependency_hint_promotion")
    if not _is_positive_number(marker):
        raise ValidationError(f"added path {path} lacks a positive promotion marker")
    witness = _mapping(row.get("closed_exact_witness"), f"added path {path} witness")
    _exact_keys(witness, set(WITNESS_FIELDS), f"added path {path} witness")
    for field in WITNESS_FIELDS:
        _nonempty_string(witness.get(field), f"added path {path} witness {field}")
    expected = {
        "target_file_path": path,
        "relation_kind": "imports",
        "resolution": "resolved_exact",
        "producer": "python_ast",
        "resolution_basis": "exact_python_imported_symbol",
    }
    for field, value in expected.items():
        if witness.get(field) != value:
            raise ValidationError(f"added path {path} witness {field} mismatch")
    _repo_path(witness["source_file_path"], "witness source_file_path")
    _repo_path(witness["target_file_path"], "witness target_file_path")


def _validate_evidence_schedule(
    name: str, evidence: dict[str, Any], contract: dict[str, Any]
) -> None:
    observed = _mapping(evidence.get("schedule"), f"{name} evidence schedule")
    _exact_keys(observed, {"expanded_schedule", "expanded_sha256"}, f"{name} schedule")
    expanded = observed.get("expanded_schedule")
    if not isinstance(expanded, list) or not all(isinstance(item, str) for item in expanded):
        raise ValidationError(f"{name} expanded schedule must be a string list")
    if len(expanded) != len(set(expanded)):
        raise ValidationError(f"{name} expanded schedule contains duplicates")
    expected = _expand_schedule(contract["schedule"][name])
    if expanded != expected:
        raise ValidationError(f"{name} expanded schedule order mismatch")
    digest = canonical_sha256(expanded)
    if observed.get("expanded_sha256") != digest:
        raise ValidationError(f"{name} evidence schedule digest mismatch")
    if digest != contract["schedule"][name]["expanded_sha256"]:
        raise ValidationError(f"{name} schedule does not bind the contract")


def _evaluate_comparator(
    reports: list[dict[str, Any]],
    contract: dict[str, Any],
    gate: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(reports, list):
        raise ValidationError("comparator reports must be a list")
    expected_count = gate["expected_reports"]
    if len(reports) != expected_count:
        raise ValidationError("comparator report matrix is incomplete")
    schedule = contract["schedule"]["fresh"]
    expected_cases = [
        f"{repository}-case-{case_ordinal}"
        for repository in schedule["repository_slots"]
        for case_ordinal in schedule["case_ordinals"]
    ]
    case_ids = []
    statuses = []
    for report in reports:
        report = _mapping(report, "comparator report")
        _exact_keys(report, {"case_id", "status"}, "comparator report")
        case_ids.append(_nonempty_string(report.get("case_id"), "comparator case_id"))
        status = report.get("status")
        if status not in {"SUCCESS", "INCOMPLETE"}:
            raise ValidationError("comparator status must be SUCCESS or INCOMPLETE")
        statuses.append(status)
    if len(case_ids) != len(set(case_ids)) or case_ids != expected_cases:
        raise ValidationError("comparator reports do not match the fresh case order")
    return {
        "policy": "report_only",
        "expected_reports": expected_count,
        "success_reports": statuses.count("SUCCESS"),
        "incomplete_reports": statuses.count("INCOMPLETE"),
    }


def _fresh_outcome_failures(
    fresh: dict[str, Any], fresh_gate: dict[str, Any]
) -> list[str]:
    efficacy_case_ids = {
        item["case_id"]
        for item in fresh["stable_causal_new_targets"]
        if item["cohort"] == "efficacy"
    }
    failures = []
    if len(efficacy_case_ids) < fresh_gate["minimum_stable_causal_new_targets"]:
        failures.append("fresh_stable_causal_new_targets")
    if len(efficacy_case_ids) < fresh_gate["minimum_distinct_efficacy_cases"]:
        failures.append("fresh_distinct_efficacy_cases")
    if len(fresh["repositories_with_gain"]) < fresh_gate["minimum_repositories_with_gain"]:
        failures.append("fresh_repositories_with_gain")
    if len(fresh["required_losses"]) > fresh_gate["required_target_losses"]:
        failures.append("fresh_required_target_losses")
    if len(fresh["rank1_changes"]) > fresh_gate["rank_one_changes"]:
        failures.append("fresh_rank_one_changes")
    if fresh["observed"]["valid_plans"] < fresh_gate["minimum_valid_plans"]:
        failures.append("fresh_valid_plans")
    if fresh["observed"]["planner_samples"] != fresh_gate["planner_sample_denominator"]:
        failures.append("fresh_planner_sample_denominator")
    if fresh["precision_at_12_delta"] < -fresh_gate["maximum_precision_at_12_decline"]:
        failures.append("fresh_precision_at_12")
    if len(fresh["treatment_only_irrelevant"]) > fresh_gate[
        "maximum_treatment_only_irrelevant_case_sample_paths"
    ]:
        failures.append("fresh_treatment_only_irrelevant")
    return failures


def _held_out_outcome_failures(
    held_out: dict[str, Any], held_gate: dict[str, Any]
) -> list[str]:
    failures = []
    held_stable = len(held_out["stable_causal_new_targets"])
    if held_out["candidate_blind_target_missing_cases"] < held_gate[
        "minimum_candidate_blind_target_missing_cases"
    ]:
        failures.append("held_out_candidate_blind_target_missing_cases")
    if held_stable < held_gate["minimum_stable_causal_new_targets"]:
        failures.append("held_out_stable_causal_new_targets")
    if held_stable < held_gate["minimum_distinct_cases"]:
        failures.append("held_out_distinct_cases")
    if len(held_out["required_losses"]) > held_gate["required_target_losses"]:
        failures.append("held_out_required_target_losses")
    return failures


def _validate_unopened_held_out(evidence: dict[str, Any]) -> None:
    evidence = _mapping(evidence, "held-out unopened evidence")
    if evidence.get("opened") is True:
        raise ValidationError("held-out was opened before fresh pass")
    if evidence != {"corpus": "held_out", "opened": False, "cases": []}:
        raise ValidationError("held-out unopened evidence must be an empty envelope")


def _release_decision(
    fresh: dict[str, Any],
    held_out: dict[str, Any],
    evidence: dict[str, Any],
    gate: dict[str, Any],
) -> dict[str, Any]:
    evidence = _mapping(evidence, "release evidence")
    _exact_keys(evidence, RELEASE_EVIDENCE_FIELDS, "release evidence")
    computed_planner = (
        fresh["additional_requests"]["planner"]
        + held_out["additional_requests"]["planner"]
    )
    computed_embedding = (
        fresh["additional_requests"]["embedding"]
        + held_out["additional_requests"]["embedding"]
    )
    if evidence["treatment_additional_planner_calls"] != computed_planner:
        raise ValidationError("release planner request count does not match evidence")
    if evidence["treatment_additional_embedding_calls"] != computed_embedding:
        raise ValidationError("release embedding request count does not match evidence")
    failures = []
    for key in (
        "treatment_additional_planner_calls",
        "treatment_additional_embedding_calls",
        "tracked_privacy_leaks",
        "topk_caps_or_budgets_increase",
        "focused_tests",
        "product_full_suite",
        "ci",
        "supported_opt_in_config",
    ):
        if evidence.get(key) != gate[key]:
            failures.append(key)
    control_latencies = fresh["latencies"]["control"] + held_out["latencies"]["control"]
    treatment_latencies = (
        fresh["latencies"]["treatment"] + held_out["latencies"]["treatment"]
    )
    control_median = statistics.median(control_latencies)
    treatment_median = statistics.median(treatment_latencies)
    latency_passed = (
        treatment_median - control_median
        <= gate["local_treatment_median_max_absolute_increase_ms"]
        or treatment_median
        <= control_median
        * (1 + gate["local_treatment_median_max_relative_regression"])
    )
    if not latency_passed:
        failures.append("local_treatment_latency")
    return {
        "status": "FAIL" if failures else "PASS",
        "failures": failures,
        "local_latency_ms": {
            "control_median": control_median,
            "treatment_median": treatment_median,
        },
    }


def _governance_decision(
    evidence: dict[str, Any], gate: dict[str, Any]
) -> dict[str, Any]:
    evidence = _mapping(evidence, "governance evidence")
    _exact_keys(evidence, set(gate), "governance evidence")
    failures = [key for key, expected in gate.items() if evidence.get(key) != expected]
    return {"status": "FAIL" if failures else "PASS", "failures": failures}


def _public_corpus_result(result: dict[str, Any]) -> dict[str, Any]:
    return {
        key: copy.deepcopy(value)
        for key, value in result.items()
        if key not in {"blocking_reasons", "latencies", "additional_requests"}
    }


def _validate_privacy(value: object, privacy: dict[str, Any]) -> None:
    forbidden = set(privacy.get("forbidden_in_evidence", []))

    def visit(item: object) -> None:
        if isinstance(item, dict):
            for key, child in item.items():
                normalized = key.casefold().replace("-", "_")
                if normalized in forbidden:
                    raise ValidationError(f"tracked evidence contains forbidden field {key}")
                visit(child)
        elif isinstance(item, list):
            for child in item:
                visit(child)
        elif isinstance(item, str) and _looks_like_absolute_path(item):
            raise ValidationError("tracked evidence contains an absolute local path")

    visit(value)


def _expand_schedule(schedule: dict[str, Any]) -> list[str]:
    repositories = schedule.get("repository_slots")
    cases = schedule.get("case_ordinals")
    samples = schedule.get("samples")
    if not isinstance(repositories, list) or not isinstance(cases, list) or not isinstance(samples, list):
        raise ValidationError("schedule dimensions must be lists")
    expanded = []
    for repository in repositories:
        _nonempty_string(repository, "schedule repository slot")
        for case in cases:
            case = _positive_int(case, "schedule case ordinal")
            for sample in samples:
                sample = _mapping(sample, "schedule sample")
                ordinal = _positive_int(sample.get("ordinal"), "schedule sample ordinal")
                replay_order = sample.get("replay_order")
                if not isinstance(replay_order, list) or not all(
                    isinstance(replay, str) and replay for replay in replay_order
                ):
                    raise ValidationError("schedule replay order must be a string list")
                for replay in replay_order:
                    expanded.append(
                        f"{repository}-c{case:02d}-s{ordinal}-{replay}"
                    )
    return expanded


def _mapping(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValidationError(f"{label} must be an object")
    return value


def _exact_keys(value: dict[str, Any], expected: set[str], label: str) -> None:
    if set(value) != expected:
        raise ValidationError(f"{label} fields mismatch")


def _require_fields(
    value: dict[str, Any], expected: dict[str, Any], label: str
) -> None:
    if any(value.get(key) != expected_value for key, expected_value in expected.items()):
        raise ValidationError(f"{label} mismatch")


def _nonempty_string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValidationError(f"{label} must be a non-empty string")
    return value


def _sha1_string(value: object, label: str) -> str:
    value = _nonempty_string(value, label)
    if len(value) != 40 or any(character not in "0123456789abcdef" for character in value):
        raise ValidationError(f"{label} must be a lowercase 40-character hex digest")
    return value


def _sha256_string(value: object, label: str) -> str:
    value = _nonempty_string(value, label)
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValidationError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _positive_int(value: object, label: str) -> int:
    if not _is_positive_int(value):
        raise ValidationError(f"{label} must be a positive integer")
    return value


def _nonnegative_int(value: object, label: str) -> int:
    if not _is_nonnegative_int(value):
        raise ValidationError(f"{label} must be a nonnegative integer")
    return value


def _is_positive_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _is_nonnegative_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _is_positive_number(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and value > 0
    )


def _is_nonnegative_number(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and value >= 0
    )


def _repo_path(value: object, label: str) -> str:
    value = _nonempty_string(value, label)
    if _looks_like_absolute_path(value) or ".." in Path(value).parts:
        raise ValidationError(f"{label} must be a repository-relative path")
    return value


def _repo_path_set(value: object, label: str) -> set[str]:
    if not isinstance(value, list):
        raise ValidationError(f"{label} must be a list")
    paths = {_repo_path(path, label) for path in value}
    if len(paths) != len(value):
        raise ValidationError(f"{label} contains duplicate paths")
    return paths


def _looks_like_absolute_path(value: str) -> bool:
    return value.startswith(("/", "\\\\")) or (
        len(value) >= 3
        and value[0].isalpha()
        and value[1] == ":"
        and value[2] in {"/", "\\"}
    )


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate sealed P15 v8 evidence offline")
    for name in (
        "contract",
        "approval-receipt",
        "execution-manifest",
        "fresh-evidence",
        "held-out-evidence",
        "comparator-reports",
        "release-evidence",
        "governance-evidence",
    ):
        parser.add_argument(f"--{name}", type=Path, required=True)
    args = parser.parse_args(argv)
    result = evaluate_closure(
        contract=_load_json(args.contract),
        approval_receipt=_load_json(args.approval_receipt),
        execution_manifest=_load_json(args.execution_manifest),
        fresh_evidence=_load_json(args.fresh_evidence),
        held_out_evidence=_load_json(args.held_out_evidence),
        comparator_reports=_load_json(args.comparator_reports),
        release_evidence=_load_json(args.release_evidence),
        governance_evidence=_load_json(args.governance_evidence),
    )
    sys.stdout.buffer.write(canonical_json_bytes(result) + b"\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
