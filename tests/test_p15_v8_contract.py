from __future__ import annotations

import copy
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any, Callable

import pytest
from jsonschema import Draft202012Validator

import p15_v8_closure_evaluator as closure_evaluator

from context_search_tool.config import DEFAULT_CONFIG
from context_search_tool.graph_contract import (
    MAX_EDGES_EXAMINED_PER_QUERY,
    MAX_FRONTIER_ENTRIES_PER_QUERY,
    MAX_GRAPH_SEED_SIGNALS,
    MAX_RELATION_EXPANDED_CANDIDATES,
    MAX_RESOLVED_GRAPH_HOPS,
    MAX_SIGNALS_POPPED_PER_QUERY,
)
from context_search_tool.query_planner import (
    MAX_IMPORTED_HINT_CODEPOINTS,
    MAX_IMPORTED_MODULE_HINTS,
    MAX_IMPORTED_SYMBOL_HINTS,
    MAX_SOURCE_HINT_CODEPOINTS,
    MAX_SOURCE_MODULE_HINTS,
    MAX_SOURCE_SYMBOL_HINTS,
    PLANNER_JSON_FIELDS,
    PROMPT_VERSION,
    prompt_hash,
)
from context_search_tool.retrieval_core import ranking
from context_search_tool.retrieval_trace import (
    DEPENDENCY_PROMOTION_NO_OP_STATUSES,
)


ROOT = Path(__file__).resolve().parents[1]
CANDIDATE_COMMIT = "c21d4cc039f6298f89d3040a0a6879d6a82eeb32"
CANDIDATE_TREE = "a159d5c4e025c82e12edab0f3343c0f4622a09ea"
FIXTURE_ROOT = ROOT / "tests/fixtures/p15_v8_closure"
CONTRACT_PATH = FIXTURE_ROOT / "attempt-contract.json"
SCHEMA_PATH = FIXTURE_ROOT / "attempt-contract.schema.json"
DESIGN_PATH = (
    ROOT
    / "docs/superpowers/specs/2026-08-05-p15-v8-closure-acceptance-design.md"
)
V7_CONTRACT_PATH = (
    ROOT
    / "tests/fixtures/p15_v7_minimal_online_causal/attempt-contract.json"
)
V7_CONTRACT_SHA256 = (
    "f7fd4711cdc7ed049c2c7cff6dfa8eed871f44d1795ea4fd4b33b30dc0f88fcf"
)
PROJECTION_ALGORITHM = (
    "sha256_of_canonical_json_sorted_path_sha256_entries_compact_ascii"
)

EXPECTED_PROJECTION_PATHS = {
    "product": (
        "src/context_search_tool/config.py",
        "src/context_search_tool/dependency_replay.py",
        "src/context_search_tool/formatters.py",
        "src/context_search_tool/graph_contract.py",
        "src/context_search_tool/models.py",
        "src/context_search_tool/python_graph.py",
        "src/context_search_tool/retrieval.py",
        "src/context_search_tool/retrieval_core/ranking.py",
        "src/context_search_tool/retrieval_core/tracing.py",
        "src/context_search_tool/retrieval_trace/collector.py",
        "src/context_search_tool/retrieval_trace/models.py",
    ),
    "behavior_tests": (
        "tests/test_config_paths.py",
        "tests/test_dependency_replay.py",
        "tests/test_exact_imported_symbol_bonus.py",
        "tests/test_p15_post_acceptance_disposition.py",
        "tests/test_python_graph.py",
        "tests/test_query_planner.py",
        "tests/test_retrieval_trace.py",
        "tests/test_retrieval_trace_pipeline.py",
    ),
    "runner": (
        "tests/p15_metric_replay.py",
        "tests/p15_v8_closure_evaluator.py",
        "tests/test_p15_v8_closure_evaluator.py",
    ),
    "config_docs": (
        ".github/workflows/ci.yml",
        "README.md",
        "docs/superpowers/plans/2026-08-05-p15-post-acceptance-remediation-plan.md",
        "docs/superpowers/specs/2026-08-03-p15-post-acceptance-problem-statement.md",
        "docs/superpowers/specs/2026-08-05-p15-local-efficacy-disposition.md",
        "pyproject.toml",
        "tests/fixtures/p15_post_acceptance/failure-classification.json",
        "tests/fixtures/p15_post_acceptance/local-efficacy-summary.json",
        "uv.lock",
    ),
    "prompt_response_schema": (
        "src/context_search_tool/query_planner.py",
    ),
}

CONTRACT_GATE_FILES = (
    "tests/test_p15_v8_contract.py",
    "tests/test_p15_v8_closure_evaluator.py",
    "tests/test_p15_post_acceptance_disposition.py",
    "tests/test_exact_imported_symbol_bonus.py",
    "tests/test_dependency_replay.py",
    "tests/test_query_planner.py",
)
FOCUSED_GATE_FILES = (
    "tests/test_python_graph.py",
    "tests/test_exact_imported_symbol_bonus.py",
    "tests/test_dependency_replay.py",
    "tests/test_p15_post_acceptance_disposition.py",
    "tests/test_query_planner.py",
    "tests/test_retrieval_trace.py",
    "tests/test_retrieval_trace_pipeline.py",
)
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
REAPPROVAL_TRIGGERS = (
    "candidate_identity_or_projection_change",
    "contract_schema_design_or_test_change",
    "treatment_factor_change",
    "promotion_mode_no_op_or_reporting_change",
    "rank_limit_idempotence_witness_or_graph_fault_policy_change",
    "planner_identity_request_or_fallback_change",
    "embedding_identity_request_or_index_change",
    "prompt_or_response_schema_change",
    "topk_or_budget_change",
    "privacy_policy_change",
    "fresh_selection_rule_query_gold_denominator_or_sealed_identity_change",
    "heldout_selection_rule_query_gold_denominator_seal_or_identity_change",
    "schedule_order_cardinality_replay_retry_or_replacement_change",
    "outcome_gate_or_threshold_change",
    "release_gate_or_threshold_change",
    "governance_stop_rule_comparator_or_disposition_change",
    "runner_test_config_document_ci_or_supported_config_change",
    "approval_scope_change",
)


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _git(*args: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ("git", *args),
        cwd=ROOT,
        check=True,
        capture_output=True,
    )


def _candidate_bytes(path: str) -> bytes:
    return _git("show", f"{CANDIDATE_COMMIT}:{path}").stdout


def _candidate_projection(paths: tuple[str, ...]) -> dict[str, object]:
    files = [
        {"path": path, "sha256": _sha256_bytes(_candidate_bytes(path))}
        for path in sorted(paths)
    ]
    return {"files": files, "sha256": _canonical_sha256(files)}


def _projection_map(contract: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        projection["name"]: projection
        for projection in contract["candidate"]["projections"]
    }


def _response_schema_projection() -> dict[str, object]:
    return {
        "fields": sorted(PLANNER_JSON_FIELDS),
        "strict_response_contract": (
            "one_complete_json_object_with_exact_fields_or_fallback"
        ),
        "limits": {
            "max_imported_hint_codepoints": MAX_IMPORTED_HINT_CODEPOINTS,
            "max_imported_module_hints": MAX_IMPORTED_MODULE_HINTS,
            "max_imported_symbol_hints": MAX_IMPORTED_SYMBOL_HINTS,
            "max_source_hint_codepoints": MAX_SOURCE_HINT_CODEPOINTS,
            "max_source_module_hints": MAX_SOURCE_MODULE_HINTS,
            "max_source_symbol_hints": MAX_SOURCE_SYMBOL_HINTS,
        },
    }


def _expand_schedule(schedule: dict[str, Any]) -> list[str]:
    expanded = []
    for repository in schedule["repository_slots"]:
        for case in schedule["case_ordinals"]:
            for sample in schedule["samples"]:
                for replay in sample["replay_order"]:
                    expanded.append(
                        f"{repository}-c{case:02d}-s{sample['ordinal']}-{replay}"
                    )
    return expanded


def _load_contract() -> dict[str, Any]:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def _load_schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _schema_errors(contract: dict[str, Any]) -> list[Any]:
    return sorted(
        Draft202012Validator(_load_schema()).iter_errors(contract),
        key=lambda error: tuple(str(part) for part in error.absolute_path),
    )


def _assert_contract_semantics(contract: dict[str, Any]) -> None:
    assert not _schema_errors(contract)
    assert contract["attempt_id"] == "p15-v8-attempt-002"
    assert contract["status"] == "DRAFT"
    assert contract["execution_eligible"] is False
    assert contract["disposition"] == "local_efficacy_only"

    candidate = contract["candidate"]
    assert candidate["commit"] == CANDIDATE_COMMIT
    assert candidate["tree"] == CANDIDATE_TREE
    assert candidate["projection_algorithm"] == PROJECTION_ALGORITHM
    projections = _projection_map(contract)
    assert tuple(projections) == tuple(EXPECTED_PROJECTION_PATHS)
    for name, paths in EXPECTED_PROJECTION_PATHS.items():
        expected = _candidate_projection(paths)
        assert projections[name]["files"] == expected["files"]
        assert projections[name]["sha256"] == expected["sha256"]

    treatment = contract["treatment"]
    assert treatment == {
        "only_factor": "consume_dependency_hints",
        "control": False,
        "treatment": True,
        "all_other_inputs_shared": True,
    }

    behavior = contract["behavior"]
    assert tuple(behavior["promotion_modes"]) == PROMOTION_MODES
    assert tuple(behavior["no_op_statuses"]) == NO_OP_STATUSES
    assert behavior["per_query_report"] == {
        "trace_schema_version": 1,
        "stage": "dependency_promotion",
        "exactly_one_status_or_closed_mode_counts": True,
        "includes_promoted_path_count": True,
    }
    assert behavior["rank_one_protected"] is True
    assert behavior["maximum_promoted_paths"] == 2
    assert behavior["idempotent"] is True
    assert behavior["graph_fault_is_no_op"] is True
    assert behavior["target_only_hints_activate_promotion"] is False
    assert behavior["closed_exact_witness_required"] is True
    assert tuple(behavior["witness_fields"]) == WITNESS_FIELDS

    online = contract["online_identity"]
    assert online["planner"] == {
        "provider": "openai-compatible",
        "domain": "api.siliconflow.cn",
        "base_url": "https://api.siliconflow.cn/v1",
        "endpoint": "https://api.siliconflow.cn/v1/chat/completions",
        "model": "Qwen/Qwen2.5-14B-Instruct",
        "temperature": 0,
        "seed": 0,
        "max_tokens": 512,
        "timeout_seconds": 60.0,
        "send_repo_profile": False,
        "calls_per_case_sample": 1,
        "treatment_additional_calls": 0,
    }
    assert online["embedding"] == {
        "provider": "openai-compatible",
        "domain": "api.siliconflow.cn",
        "base_url": "https://api.siliconflow.cn/v1",
        "endpoint": "https://api.siliconflow.cn/v1/embeddings",
        "model": "Pro/BAAI/bge-m3",
        "dimensions": 1024,
        "shared_index_and_query_embedding_between_arms": True,
        "treatment_additional_calls": 0,
    }
    assert online["prompt"] == {
        "version": PROMPT_VERSION,
        "sha256": prompt_hash().removeprefix("sha256:"),
    }
    response_projection = _response_schema_projection()
    assert online["response_schema"]["projection"] == response_projection
    assert online["response_schema"]["sha256"] == _canonical_sha256(
        response_projection
    )

    retrieval = contract["retrieval"]
    assert retrieval["top_k"] == {
        "semantic": DEFAULT_CONFIG.retrieval.semantic_top_k,
        "lexical": DEFAULT_CONFIG.retrieval.lexical_top_k,
        "final": DEFAULT_CONFIG.retrieval.final_top_k,
    }
    assert retrieval["budgets"] == {
        "max_graph_seed_signals": MAX_GRAPH_SEED_SIGNALS,
        "max_resolved_graph_hops": MAX_RESOLVED_GRAPH_HOPS,
        "max_signals_popped_per_query": MAX_SIGNALS_POPPED_PER_QUERY,
        "max_edges_examined_per_query": MAX_EDGES_EXAMINED_PER_QUERY,
        "max_frontier_entries_per_query": MAX_FRONTIER_ENTRIES_PER_QUERY,
        "max_relation_expanded_candidates": MAX_RELATION_EXPANDED_CANDIDATES,
    }
    assert retrieval["caps_must_not_increase"] is True

    privacy = contract["privacy"]
    assert privacy["planner_payload"] == "query_and_frozen_numeric_limits_only"
    assert privacy["embedding_payload"] == "source_chunks_to_frozen_provider_only"
    assert privacy["forbidden_in_evidence"] == [
        "credential",
        "authorization_header",
        "source_body",
        "absolute_local_path",
        "raw_exception",
    ]
    assert privacy["tracked_leak_count_limit"] == 0
    assert privacy["raw_evidence_tracked"] is False

    fresh = contract["corpus"]["fresh"]
    held_out = contract["corpus"]["held_out"]
    assert fresh["identity_state"] == "UNSELECTED"
    assert fresh["repository_count"] == 2
    assert fresh["cases_per_repository"] == 6
    assert fresh["guard_ordinals"] == [1, 2]
    assert fresh["efficacy_ordinals"] == [3, 4, 5, 6]
    assert fresh["target_recall_denominator"] == 8
    assert held_out["identity_state"] == "UNSELECTED_SEALED_INPUT_PENDING"
    assert held_out["repository_count"] == 1
    assert held_out["cases_per_repository"] == 4
    assert held_out["opened"] is False
    for corpus in (fresh, held_out):
        assert corpus["selection_before_online"] is True
        assert corpus["candidate_blind"] is True
        assert corpus["query_policy"] == "source_only_no_target_derived_terms"
        assert corpus["gold_derivation"] == (
            "independent_stdlib_ast_direct_from_import_unique_top_level_owner"
        )
        assert corpus["replacement_allowed"] is False

    for name, expected_count in (("fresh", 96), ("held_out", 32)):
        schedule = contract["schedule"][name]
        expanded = _expand_schedule(schedule)
        assert len(expanded) == expected_count
        assert len(expanded) == len(set(expanded))
        assert schedule["expanded_count"] == expected_count
        assert schedule["expanded_sha256"] == _canonical_sha256(expanded)
    assert contract["schedule"]["result_dependent_append_allowed"] is False
    assert contract["schedule"]["retry_or_replacement_allowed"] is False
    assert contract["schedule"]["all_cases_complete_before_decision"] is True

    gates = contract["gates"]
    assert gates["outcome"]["fresh"]["minimum_stable_causal_new_targets"] == 3
    assert gates["outcome"]["fresh"]["required_target_losses"] == 0
    assert gates["outcome"]["fresh"]["rank_one_changes"] == 0
    assert gates["outcome"]["held_out"]["minimum_stable_causal_new_targets"] == 2
    assert gates["outcome"]["held_out"]["required_target_losses"] == 0
    assert gates["release"]["focused_tests"] == "pass"
    assert gates["release"]["product_full_suite"] == "pass"
    assert gates["release"]["ci"] == "pass"
    assert gates["release"]["supported_opt_in_config"] == "pass"
    assert gates["release"]["topk_caps_or_budgets_increase"] == 0
    assert gates["release"]["tracked_privacy_leaks"] == 0
    assert gates["governance"]["outcome_release_governance_separate"] is True
    assert gates["governance"]["no_tuning_after_seal"] is True
    assert gates["comparator"] == {
        "name": "fast-context",
        "policy": "report_only",
        "scope": "fresh_12_cases",
        "expected_reports": 12,
        "post_hoc_policy_change_allowed": False,
        "unavailable_disposition": "record_INCOMPLETE_without_gate_waiver",
    }
    assert gates["stop_rules"] == [
        "missing_approval_or_execution_manifest_blocks_before_any_access",
        "candidate_or_contract_binding_drift_requires_new_attempt",
        "provider_or_sealed_input_unavailable_is_blocked_without_substitution",
        "incomplete_matrix_is_blocked_without_early_decision",
        "complete_outcome_failure_is_reject",
        "outcome_pass_with_release_or_governance_failure_is_local_efficacy_only",
    ]

    verification = contract["verification"]
    assert verification["runner"] == {
        "path": "tests/p15_v8_closure_evaluator.py",
        "sha256": _sha256_bytes(
            _candidate_bytes("tests/p15_v8_closure_evaluator.py")
        ),
        "role": "tracked_offline_closure_evaluator_only",
        "online_collection_authorized": False,
    }
    assert tuple(verification["contract_gate_files"]) == CONTRACT_GATE_FILES
    assert tuple(verification["focused_gate_files"]) == FOCUSED_GATE_FILES
    assert verification["product_gate_marker"] == (
        "not slow and not archival_acceptance and not runtime_pinned"
    )
    assert verification["ci_workflow"] == ".github/workflows/ci.yml"
    assert verification["supported_opt_in_config"] == {
        "retrieval.consume_dependency_hints": True,
        "embedding.provider": "bge",
        "embedding.model": "bge-m3",
        "embedding.dimensions": 1024,
        "query_planner.enabled": True,
        "query_planner.provider": "ollama",
        "query_planner.model": "qwen3.5:4b-mlx",
        "query_planner.send_repo_profile": True,
    }

    assert contract["decisions"] == {
        "outcome": "NOT_RUN",
        "release": "NOT_EVALUATED",
        "governance": "DRAFT_UNAPPROVED",
        "final_disposition": "local_efficacy_only",
        "allowed_final_dispositions": [
            "ship",
            "local_efficacy_only",
            "reject",
            "blocked",
        ],
    }
    assert contract["approval_receipt"] == {
        "received": False,
        "path": "",
        "sha256": "",
        "approved_attempt_id": "",
        "approved_contract_sha256": "",
    }
    assert contract["approval_policy"]["receipt_count"] == 1
    assert tuple(contract["approval_policy"]["reapproval_triggers"]) == (
        REAPPROVAL_TRIGGERS
    )
    authorization = contract["authorization"]
    assert authorization["task7_authorized"] is False
    assert authorization["execution_manifest_sealed"] is False
    assert authorization["execution_guard"] == (
        "deny_unless_approved_receipt_and_sealed_execution_manifest_match_contract"
    )
    assert set(authorization["forbidden_while_draft"]) == {
        "fresh_identity_resolution",
        "source_access",
        "planner_request",
        "embedding_request",
        "control_execution",
        "treatment_execution",
        "comparator_request",
        "held_out_opening",
        "release_decision",
    }
    assert set(authorization["zero_counters"].values()) == {0}


def _mutate(path: tuple[str | int, ...], value: object) -> Callable[[dict[str, Any]], None]:
    def apply(contract: dict[str, Any]) -> None:
        target: Any = contract
        for part in path[:-1]:
            target = target[part]
        target[path[-1]] = value

    return apply


def _delete(path: tuple[str | int, ...]) -> Callable[[dict[str, Any]], None]:
    def apply(contract: dict[str, Any]) -> None:
        target: Any = contract
        for part in path[:-1]:
            target = target[part]
        del target[path[-1]]

    return apply


def test_contract_artifacts_exist_and_schema_is_closed_draft_2020_12() -> None:
    assert DESIGN_PATH.is_file()
    contract = _load_contract()
    schema = _load_schema()

    Draft202012Validator.check_schema(schema)
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert not _schema_errors(contract)

    def visit(node: object) -> None:
        if isinstance(node, dict):
            if node.get("type") == "object":
                assert node.get("additionalProperties") is False
            for child in node.values():
                visit(child)
        elif isinstance(node, list):
            for child in node:
                visit(child)

    visit(schema)


def test_contract_binds_clean_candidate_closed_projections_from_commit() -> None:
    contract = _load_contract()
    _assert_contract_semantics(contract)

    assert _git("rev-parse", f"{CANDIDATE_COMMIT}^{{tree}}").stdout.decode().strip() == (
        CANDIDATE_TREE
    )
    bound_paths = {
        entry["path"]
        for projection in contract["candidate"]["projections"]
        for entry in projection["files"]
    }
    assert not any(path.startswith(".quality/") for path in bound_paths)
    for path in bound_paths:
        _git("cat-file", "-e", f"{CANDIDATE_COMMIT}:{path}")
    assert not _git("status", "--short", "--", *sorted(bound_paths)).stdout


def test_contract_fields_correspond_to_candidate_behavior_config_ci_and_docs() -> None:
    contract = _load_contract()
    _assert_contract_semantics(contract)

    assert DEFAULT_CONFIG.retrieval.consume_dependency_hints is False
    assert DEFAULT_CONFIG.query_planner.enabled is False
    assert DEFAULT_CONFIG.embedding.model == "hash-v1"
    assert ranking._PLANNER_DEPENDENCY_MAX_PROMOTIONS == 2
    assert tuple(DEPENDENCY_PROMOTION_NO_OP_STATUSES) == NO_OP_STATUSES

    behavior_source = _candidate_bytes(
        "tests/test_exact_imported_symbol_bonus.py"
    ).decode("utf-8")
    for test_name in (
        "test_dedicated_source_module_hints_activate_dependency_promotion",
        "test_exact_target_hint_recovers_from_misclassified_source_hint",
        "test_semantic_import_hint_uses_strong_direct_source_target_pair_fallback",
        "test_semantic_import_hint_fallback_rejects_weak_source_target_pair",
        "test_source_hint_promotion_is_input_order_independent_and_idempotent",
    ):
        assert test_name in behavior_source
    assert "graph-fault" in behavior_source
    assert "no_eligible_closed_candidate" in behavior_source

    trace_source = _candidate_bytes("tests/test_retrieval_trace_pipeline.py").decode(
        "utf-8"
    )
    assert "test_dependency_promotion_stage_is_visible_when_feature_is_disabled" in (
        trace_source
    )
    for value in (*PROMOTION_MODES, *NO_OP_STATUSES):
        assert value in trace_source

    ci = _candidate_bytes(".github/workflows/ci.yml").decode("utf-8")
    assert contract["verification"]["product_gate_marker"] in ci
    for path in FOCUSED_GATE_FILES:
        assert path in ci
    readme = _candidate_bytes("README.md").decode("utf-8")
    for value in (
        "local_efficacy_only",
        "consume_dependency_hints = true",
        'provider = "bge"',
        'model = "qwen3.5:4b-mlx"',
    ):
        assert value in readme
    summary = json.loads(
        _candidate_bytes(
            "tests/fixtures/p15_post_acceptance/local-efficacy-summary.json"
        )
    )
    assert summary["disposition"] == contract["disposition"]


def test_contract_is_accepted_by_bound_closure_evaluator() -> None:
    closure_evaluator._validate_contract(_load_contract())


def test_contract_is_a_later_layer_without_self_hash_or_raw_evidence_dependency() -> None:
    contract = _load_contract()
    _assert_contract_semantics(contract)

    layer = contract["contract_layer"]
    assert layer["commit_semantics"] == (
        "subsequent_contract_commit_not_candidate"
    )
    assert layer["candidate_contains_contract_artifacts"] is False
    assert layer["contract_self_hash_forbidden"] is True
    artifact_paths = {artifact["path"] for artifact in layer["artifacts"]}
    assert artifact_paths == {
        DESIGN_PATH.relative_to(ROOT).as_posix(),
        SCHEMA_PATH.relative_to(ROOT).as_posix(),
        Path(__file__).relative_to(ROOT).as_posix(),
    }
    for artifact in layer["artifacts"]:
        assert artifact["sha256"] == _sha256_bytes(
            (ROOT / artifact["path"]).read_bytes()
        )
    assert "contract_sha256" not in contract

    assert _sha256_bytes(V7_CONTRACT_PATH.read_bytes()) == V7_CONTRACT_SHA256
    for reference in contract["historical_raw_evidence"]:
        assert reference["required_for_contract_test"] is False
        assert reference["path"].startswith(".quality/")
        assert len(reference["sha256"]) == 64


def test_draft_contract_is_fail_closed_and_has_one_future_receipt() -> None:
    contract = _load_contract()
    _assert_contract_semantics(contract)

    receipt_keys = []

    def visit(value: object, path: tuple[str, ...] = ()) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                child_path = (*path, key)
                if key == "approval_receipt":
                    receipt_keys.append(child_path)
                visit(child, child_path)
        elif isinstance(value, list):
            for child in value:
                visit(child, path)

    visit(contract)
    assert receipt_keys == [("approval_receipt",)]
    assert contract["approval_receipt"]["received"] is False
    assert contract["execution_eligible"] is False
    assert contract["authorization"]["task7_authorized"] is False
    assert contract["decisions"]["outcome"] == "NOT_RUN"
    assert contract["decisions"]["release"] == "NOT_EVALUATED"


@pytest.mark.parametrize(
    "mutation",
    [
        pytest.param(
            _mutate(("candidate", "commit"), "0" * 40),
            id="candidate-identity",
        ),
        pytest.param(
            _mutate(("candidate", "projections", 0, "sha256"), "0" * 64),
            id="projection-digest",
        ),
        pytest.param(
            _mutate(
                ("candidate", "projections", 0, "files", 0, "path"),
                "missing/untracked.py",
            ),
            id="required-path-tracked",
        ),
        pytest.param(
            _mutate(("treatment", "control"), True),
            id="only-treatment-factor",
        ),
        pytest.param(
            _mutate(("behavior", "promotion_modes", 2), "future_mode"),
            id="promotion-mode",
        ),
        pytest.param(
            _mutate(("behavior", "no_op_statuses", 0), "future_status"),
            id="no-op-status",
        ),
        pytest.param(
            _mutate(
                ("behavior", "per_query_report", "includes_promoted_path_count"),
                False,
            ),
            id="per-query-report",
        ),
        pytest.param(
            _mutate(("behavior", "maximum_promoted_paths"), 3),
            id="promotion-limit",
        ),
        pytest.param(
            _mutate(("privacy", "tracked_leak_count_limit"), 1),
            id="privacy",
        ),
        pytest.param(
            _mutate(("schedule", "fresh", "expanded_count"), 95),
            id="schedule",
        ),
        pytest.param(
            _mutate(
                (
                    "gates",
                    "outcome",
                    "fresh",
                    "minimum_stable_causal_new_targets",
                ),
                2,
            ),
            id="outcome-gate",
        ),
        pytest.param(
            _mutate(("gates", "comparator", "policy"), "hard_gate"),
            id="comparator-policy",
        ),
        pytest.param(
            _mutate(("approval_receipt", "received"), True),
            id="approval-receipt",
        ),
        pytest.param(
            _delete(("approval_policy", "reapproval_triggers", 0)),
            id="reapproval-trigger",
        ),
        pytest.param(_mutate(("status",), "APPROVED"), id="draft-status"),
        pytest.param(
            _mutate(("execution_eligible",), True),
            id="execution-eligible",
        ),
        pytest.param(
            _mutate(("authorization", "task7_authorized"), True),
            id="task7-authorization",
        ),
        pytest.param(
            _mutate(("disposition",), "ship"),
            id="disposition",
        ),
    ],
)
def test_contract_mutations_fail_closed(
    mutation: Callable[[dict[str, Any]], None],
) -> None:
    mutant = copy.deepcopy(_load_contract())
    mutation(mutant)

    with pytest.raises((AssertionError, subprocess.CalledProcessError)):
        _assert_contract_semantics(mutant)
