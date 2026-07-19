from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

import pytest

from retrieval_core_characterization import (
    FULL_STAGE_LEDGER_KEYS,
    baseline_projection,
    characterization_input_identity,
    reject_sensitive_manifest,
    runtime_identity,
    serialize_internal_projection,
)


FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "retrieval_core_decomposition"
    / "baseline.json"
)

EXPECTED_CASE_KEYS = (
    ("ci", "program_tool", "watermark-remover"),
    ("ci", "program_tool", "mqtt-tool"),
    ("ci", "program_tool", "qrcode-tool"),
    ("ci", "program_tool", "json-to-entity"),
    ("ci", "program_tool", "app-layout-theme"),
    ("ci", "program_tool", "ai-chat"),
    ("ci", "java_spring_mini", "apply-audit-endpoint"),
    ("ci", "java_spring_mini", "workbench-audit-localized-cjk"),
    ("p2_context_pack", "context_pack_java", "workspace-page-flow"),
    ("p2_context_pack", "context_pack_java", "workspace-test-file"),
    ("p2_context_pack", "context_pack_java", "workspace-service-symbol"),
    ("p2_context_pack", "context_pack_frontend", "qrcode-feature-context"),
    ("p2_context_pack", "context_pack_docs", "program-tool-developer-docs"),
)

EXPECTED_FULL_LEDGER_KEYS = (
    "context_pack_java/workspace-page-flow",
    "context_pack_frontend/qrcode-feature-context",
    "context_pack_docs/program-tool-developer-docs",
    "java_spring_mini/apply-audit-endpoint",
)

EXPECTED_BASELINE_SKIPS = (
    (
        "tests.test_quality_catalog::"
        "test_investment_assistant_targets_enter_candidate_pool",
        "investment assistant repo not configured",
    ),
    (
        "tests.test_quality_p1::"
        "test_phase_one_vector_and_hybrid_profiles_close_together",
        "set CST_RUN_P1_ACCEPTANCE=1 to run local model acceptance",
    ),
    *(
        (
            "tests.test_quality_p2::"
            "test_pinned_real_context_case_is_deterministic_bounded_private_"
            f"and_passing[{case_id}]",
            "set CST_P2_REAL_CONTEXT_REPOS_DIR to a prepared repositories root",
        )
        for case_id in (
            "owner-registration-validation-flow",
            "owner-controller-registration-tests",
            "owner-details-pets-visits",
            "database-profiles-integration-tests",
        )
    ),
    (
        "tests.test_quality_p2::"
        "test_pinned_real_context_reports_repeat_except_timing_and_runtime_"
        "provenance",
        "set CST_P2_REAL_CONTEXT_REPOS_DIR to a prepared repositories root",
    ),
    (
        "tests.test_quality_planner::"
        "test_real_requests_planner_is_three_of_three_with_supported_hints",
        "requests checkout is not configured",
    ),
    (
        "tests.test_quality_planner::"
        "test_real_dashboard_planner_supplies_english_bridge",
        "requests checkout is not configured",
    ),
)


def _load_baseline() -> dict[str, object]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _without_operation_ledgers(value: dict[str, Any]) -> dict[str, object]:
    return {
        "cases": [
            {
                key: item
                for key, item in case.items()
                if key not in {"ordinary_operations", "traced_operations"}
            }
            for case in value["cases"]
        ],
        "full_stage_ledgers": {
            key: {
                field: item
                for field, item in ledger.items()
                if field != "operations"
            }
            for key, ledger in value["full_stage_ledgers"].items()
        },
    }


def _assert_anchor_batch_operation_delta(
    actual: list[dict[str, Any]],
    expected: list[dict[str, Any]],
) -> None:
    prefix = 0
    while prefix < min(len(actual), len(expected)):
        if actual[prefix] != expected[prefix]:
            break
        prefix += 1
    assert prefix < len(actual) and prefix < len(expected)

    io_operations = {"sqlite.chunks_for_file", "sqlite.chunks_in_directory"}
    actual_allowed = {"sqlite.chunks_for_ids", *io_operations}
    expected_allowed = {"sqlite.chunk_for_id", *io_operations}
    suffix = 0
    while suffix < min(len(actual) - prefix, len(expected) - prefix):
        if actual[-suffix - 1] != expected[-suffix - 1]:
            break
        suffix += 1
    actual_end = len(actual) - suffix if suffix else len(actual)
    expected_end = len(expected) - suffix if suffix else len(expected)
    actual_delta = actual[prefix:actual_end]
    expected_delta = expected[prefix:expected_end]
    assert actual[:prefix] == expected[:prefix]
    assert actual[actual_end:] == expected[expected_end:]
    assert {entry["operation"] for entry in actual_delta} <= actual_allowed
    assert {entry["operation"] for entry in expected_delta} <= expected_allowed

    batch = [
        entry
        for entry in actual_delta
        if entry["operation"] == "sqlite.chunks_for_ids"
    ]
    old_lookups = [
        entry
        for entry in expected_delta
        if entry["operation"] == "sqlite.chunk_for_id"
    ]
    assert actual_delta and actual_delta[0]["operation"] == "sqlite.chunks_for_ids"
    assert expected_delta and expected_delta[0]["operation"] == "sqlite.chunk_for_id"
    assert len(batch) == 1
    assert old_lookups

    old_ids = [entry["args"][0] for entry in old_lookups]
    successful_ids = [entry["args"][0] for entry in old_lookups if "result" in entry]
    assert batch[0]["args"] == [old_ids]
    assert batch[0]["result"] == {
        "kind": "mapping",
        "count": len(successful_ids),
        "keys": successful_ids,
    }
    assert {
        key: batch[0][key]
        for key in ("run", "phase")
    } == {
        key: old_lookups[0][key]
        for key in ("run", "phase")
    }

    expected_io: list[dict[str, Any]] = []
    for entry in expected_delta:
        if entry["operation"] in io_operations and entry not in expected_io:
            expected_io.append(entry)
    assert [
        entry for entry in actual_delta if entry["operation"] in io_operations
    ] == expected_io


def _sample_anchor_operation_ledgers() -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    def operation(
        name: str,
        args: list[object],
        result: dict[str, object],
    ) -> dict[str, Any]:
        return {
            "run": "ordinary",
            "phase": "live",
            "operation": name,
            "args": args,
            "result": result,
        }

    prefix = operation(
        "sqlite.signal_search",
        [["anchor"], 80],
        {"kind": "sequence", "count": 2},
    )
    suffix = operation(
        "sqlite.signals_for_chunks",
        [["a", "b"]],
        {"kind": "mapping", "count": 2, "keys": ["a", "b"]},
    )
    file_read = operation(
        "sqlite.chunks_for_file",
        ["src/A.py", 36],
        {"kind": "sequence", "count": 2},
    )
    expected = [
        prefix,
        operation("sqlite.chunk_for_id", ["a"], {"kind": "DocumentChunk"}),
        file_read,
        operation("sqlite.chunk_for_id", ["b"], {"kind": "DocumentChunk"}),
        file_read,
        suffix,
    ]
    actual = [
        prefix,
        operation(
            "sqlite.chunks_for_ids",
            [["a", "b"]],
            {"kind": "mapping", "count": 2, "keys": ["a", "b"]},
        ),
        file_read,
        suffix,
    ]
    return actual, expected


def assert_final_junit_evidence_matches_baseline(path: Path) -> dict[str, int]:
    baseline = _load_baseline()["test_evidence"]
    root = ElementTree.parse(path).getroot()
    suite = next(root.iter("testsuite"))
    failures = int(suite.attrib.get("failures", "0"))
    errors = int(suite.attrib.get("errors", "0"))
    skipped = int(suite.attrib.get("skipped", "0"))
    skips: list[dict[str, str]] = []
    xfails: list[dict[str, str]] = []
    for testcase in root.iter("testcase"):
        skipped_node = testcase.find("skipped")
        if skipped_node is None:
            continue
        entry = {
            "node_id": f"{testcase.attrib['classname']}::{testcase.attrib['name']}",
            "reason": skipped_node.attrib.get("message", ""),
        }
        if skipped_node.attrib.get("type") == "pytest.xfail":
            xfails.append(entry)
        else:
            skips.append(entry)

    assert failures == 0
    assert errors == 0
    assert skipped == baseline["skipped"]
    assert skips == baseline["skips"]
    assert xfails == baseline["xfails"]
    tests = int(suite.attrib["tests"])
    return {
        "passed": tests - failures - errors - skipped,
        "skipped": skipped,
        "xfails": len(xfails),
    }


def test_immutable_manifest_has_exact_case_and_evidence_universe() -> None:
    baseline = _load_baseline()

    assert baseline["schema_version"] == 1
    assert tuple(
        (case["profile"], case["repo_key"], case["case_id"])
        for case in baseline["cases"]
    ) == EXPECTED_CASE_KEYS
    assert tuple(baseline["full_stage_ledgers"]) == EXPECTED_FULL_LEDGER_KEYS
    assert tuple(
        (entry["node_id"], entry["reason"])
        for entry in baseline["test_evidence"]["skips"]
    ) == EXPECTED_BASELINE_SKIPS
    assert baseline["test_evidence"]["passed"] == 1884
    assert baseline["test_evidence"]["failed"] == 0
    assert baseline["test_evidence"]["errors"] == 0
    assert baseline["test_evidence"]["skipped"] == len(EXPECTED_BASELINE_SKIPS)
    assert baseline["test_evidence"]["xfails"] == []


def test_characterization_inputs_match_frozen_identity() -> None:
    baseline = _load_baseline()

    assert characterization_input_identity() == baseline["characterization_inputs"]


def test_runtime_identity_matches_frozen_platform() -> None:
    baseline = _load_baseline()

    assert runtime_identity() == baseline["runtime"]


def test_characterization_matches_immutable_baseline(tmp_path: Path) -> None:
    baseline = _load_baseline()
    expected = {
        "cases": baseline["cases"],
        "full_stage_ledgers": baseline["full_stage_ledgers"],
    }
    actual = baseline_projection(tmp_path, expected_cases=baseline["cases"])

    assert _without_operation_ledgers(actual) == _without_operation_ledgers(expected)
    for actual_case, expected_case in zip(actual["cases"], expected["cases"]):
        for field in ("ordinary_operations", "traced_operations"):
            _assert_anchor_batch_operation_delta(
                actual_case[field],
                expected_case[field],
            )
    for key, expected_ledger in expected["full_stage_ledgers"].items():
        _assert_anchor_batch_operation_delta(
            actual["full_stage_ledgers"][key]["operations"],
            expected_ledger["operations"],
        )


def test_anchor_batch_delta_rejects_unrelated_operation_change() -> None:
    actual, expected = _sample_anchor_operation_ledgers()
    actual.insert(-1, deepcopy(actual[0]))

    with pytest.raises(AssertionError):
        _assert_anchor_batch_operation_delta(actual, expected)


@pytest.mark.parametrize("malformation", ("batch_order", "duplicate_file"))
def test_anchor_batch_delta_rejects_malformed_batch_or_dedupe(
    malformation: str,
) -> None:
    actual, expected = _sample_anchor_operation_ledgers()
    if malformation == "batch_order":
        actual[1]["args"] = [["b", "a"]]
    else:
        actual.insert(-1, deepcopy(actual[2]))
        actual.insert(-1, deepcopy(actual[2]))

    with pytest.raises(AssertionError):
        _assert_anchor_batch_operation_delta(actual, expected)


def test_operation_and_full_stage_ledgers_are_complete() -> None:
    baseline = _load_baseline()

    for case in baseline["cases"]:
        ordinary = case["ordinary_operations"]
        traced = case["traced_operations"]
        assert ordinary
        assert traced
        assert {entry["run"] for entry in ordinary} == {"ordinary"}
        assert {entry["run"] for entry in traced} == {"traced"}
        assert {entry["phase"] for entry in ordinary} == {"live"}
        assert {entry["phase"] for entry in traced} == {"live", "observation"}
        for operations in (ordinary, traced):
            assert sum(
                entry["operation"] == "embedding.embed_texts"
                for entry in operations
            ) == 1
            assert sum(
                entry["operation"] == "direct_text.probes"
                for entry in operations
            ) == 1
            assert any(entry["operation"] == "vector.search" for entry in operations)
            assert any(
                entry["operation"] == "sqlite.deleted_chunk_ids"
                for entry in operations
            )

    assert tuple(baseline["full_stage_ledgers"]) == FULL_STAGE_LEDGER_KEYS
    for ledger in baseline["full_stage_ledgers"].values():
        assert [stage["name"] for stage in ledger["stages"]] == [
            "query_understanding",
            "semantic_recall",
            "lexical_recall",
            "path_symbol_recall",
            "direct_text_recall",
            "signal_recall",
            "planner_hint_recall",
            "direct_merge",
            "anchor_expansion",
            "relation_expansion",
            "candidate_merge",
            "ranking",
            "cohort_rerank",
            "context_expansion",
            "final_selection",
        ]
        assert ledger["trace_contract"]["trace_coverage"] == 1.0
        assert ledger["operations"]


def test_p2_cases_freeze_complete_context_pack_options() -> None:
    baseline = _load_baseline()
    p2_cases = [
        case for case in baseline["cases"] if case["profile"] == "p2_context_pack"
    ]

    assert len(p2_cases) == 5
    for case in p2_cases:
        assert tuple(case["context_pack"]["resolved_options"]) == (
            "max_items",
            "max_excerpts_per_item",
            "max_excerpt_bytes",
            "max_item_content_bytes",
            "max_total_content_bytes",
            "max_pack_bytes",
            "context_before_lines",
            "context_after_lines",
        )
        assert case["context_pack"]["maximum_pack_bytes"] == 65536
        assert case["context_pack"]["maximum_truncated_items"] == 4


def test_internal_projection_serializer_is_fixed_order_and_compact() -> None:
    value = {"z": 1, "a": ["中", 2]}

    assert serialize_internal_projection(value) == b'{"z":1,"a":["\\u4e2d",2]}'


def test_manifest_privacy_rejects_paths_content_environment_and_secrets(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(RuntimeError, match="absolute repository/temp path"):
        reject_sensitive_manifest({"path": str(tmp_path / "repo")}, temporary_roots=(tmp_path,))
    with pytest.raises(RuntimeError, match="unhashed source content"):
        reject_sensitive_manifest({"content": "private source"})
    environment_value = "PRIVATE_ENVIRONMENT_VALUE_7f30d102"
    monkeypatch.setenv("CST_PRIVATE_MANIFEST_SENTINEL", environment_value)
    with pytest.raises(RuntimeError, match="environment value"):
        reject_sensitive_manifest({"value": environment_value})
    with pytest.raises(RuntimeError, match="sensitive field"):
        reject_sensitive_manifest({"headers": {"Authorization": "secret"}})
