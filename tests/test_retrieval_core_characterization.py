from __future__ import annotations

from copy import deepcopy
import json
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

EXPECTED_P7_FINAL_TRACE_HASHES = {
    (
        "ci",
        "program_tool",
        "watermark-remover",
    ): "24a0a9eedfc210d2178593baee4b5da15f5da39a6a2ada983889675d9470cb7d",
    (
        "ci",
        "program_tool",
        "mqtt-tool",
    ): "667c385d75079f8bef83bb8f02f61296273ae9be4ada2760217583707592fd7a",
    (
        "ci",
        "program_tool",
        "qrcode-tool",
    ): "694f23aa2037e90902d2155c5acbb676f6e16886a8b96b435e05786e377498f1",
    (
        "ci",
        "program_tool",
        "json-to-entity",
    ): "6b4bb68ac3a371b451a18c60e435ba775d299be7b1fe4234dd5c0f9949d01009",
    (
        "ci",
        "program_tool",
        "app-layout-theme",
    ): "3b3d7dafda7ff4ba2fec9b9ca1dfa6eb36f7b4e84647252cdf559ef410dbac83",
    (
        "ci",
        "program_tool",
        "ai-chat",
    ): "e147d6d87a326ed7b19533b1f9c6cda8f71c9a1a8af02fd19ec06656e3d638a9",
    (
        "ci",
        "java_spring_mini",
        "apply-audit-endpoint",
    ): "7bd5a8bb847fdd120d06b551f667a9e69240e833635f0e9fee0da6bddb3f06c6",
    (
        "ci",
        "java_spring_mini",
        "workbench-audit-localized-cjk",
    ): "9e7fb5cdc9b086f6ab18a0b83513265d26a1814777328c94d5e3b39239fcc798",
    (
        "p2_context_pack",
        "context_pack_java",
        "workspace-page-flow",
    ): "479e2baa8b36caca33d7fba8f4789c04ee9d5a7a38baaec192175b1b00dac57b",
    (
        "p2_context_pack",
        "context_pack_java",
        "workspace-test-file",
    ): "3acda4c6c8134136bb8b7a86bcb90d9b25d7496bd94cf32354b51622b7a606bb",
    (
        "p2_context_pack",
        "context_pack_java",
        "workspace-service-symbol",
    ): "fff1a12a24acaa7e8953db7a244a5515a653402f3ed3b69fb5ac79a2a96f99e7",
    (
        "p2_context_pack",
        "context_pack_frontend",
        "qrcode-feature-context",
    ): "13c0d97a8ad97a34d590f9527f95e50179d2ec164ba234e1d1cc8bf6cc962f9b",
    (
        "p2_context_pack",
        "context_pack_docs",
        "program-tool-developer-docs",
    ): "759232a7d284ffb9ca40f5a935417ffc7d9ba5f67081c9b012ae607563578af0",
}

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

_DISABLED_PROFILE_OPERATIONS = {
    "sqlite.language_counts",
    "sqlite.source_files_for_profile",
    "sqlite.symbol_names_for_profile",
    "sqlite.token_counts_for_profile",
}


def _load_baseline() -> dict[str, object]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


_FOLLOWUP_DELTA_HASH_KEYS = frozenset(
    {"json_sha256", "markdown_sha256", "internal_bundle_sha256"}
)


def _normalize_followup_filter_delta(
    actual: dict[str, object],
    expected: dict[str, object],
) -> dict[str, object]:
    """Reverse the deliberate followup-keyword filtering delta.

    Projected followup_keywords lists must either match the frozen baseline
    exactly (internal, pre-filter surfaces) or equal the production filter
    applied to the frozen list (public surfaces) - any other drift fails.
    Only rendered-output hashes (json/markdown/internal bundle) may then be
    substituted, and at least one must actually differ so the overlay never
    hides an unchanged pipeline. P7 trace hashes contain no followup
    keywords and stay pinned.
    """
    from context_search_tool.retrieval_core import selection as _selection

    normalized = deepcopy(actual)
    delta = {"filtered_lists": 0, "rendered_hashes": 0}

    def walk(live: object, frozen: object) -> None:
        if isinstance(live, dict) and isinstance(frozen, dict):
            for key, live_value in live.items():
                frozen_value = frozen.get(key)
                if (
                    key == "followup_keywords"
                    and isinstance(live_value, list)
                    and isinstance(frozen_value, list)
                ):
                    if live_value != frozen_value:
                        assert live_value == _selection.filter_followup_keywords(
                            [str(token) for token in frozen_value]
                        )
                        delta["filtered_lists"] += 1
                        live[key] = list(frozen_value)
                elif (
                    key in _FOLLOWUP_DELTA_HASH_KEYS
                    and isinstance(live_value, str)
                    and isinstance(frozen_value, str)
                ):
                    if live_value != frozen_value:
                        delta["rendered_hashes"] += 1
                        live[key] = frozen_value
                else:
                    walk(live_value, frozen_value)
        elif isinstance(live, list) and isinstance(frozen, list) and len(
            live
        ) == len(frozen):
            for live_item, frozen_item in zip(live, frozen):
                walk(live_item, frozen_item)

    walk(normalized, expected)
    assert delta["rendered_hashes"] > 0
    return normalized


EXPECTED_P9_FINAL_TRACE_HASHES: dict[tuple[str, str, str], str] = {
    (
        "ci",
        "java_spring_mini",
        "apply-audit-endpoint",
    ): "e870f3b7710cb664f82d02fb13326c4f7dcb9d78284f96b41a245c62db143dee",
    (
        "ci",
        "java_spring_mini",
        "workbench-audit-localized-cjk",
    ): "b7aef9dc530563f52e1656d4333dbca4e75c1330affcb56a147ce5b352c957b6",
    (
        "ci",
        "program_tool",
        "ai-chat",
    ): "67ee7008bb46cbdbdc103203068bd8f1909227648bc7b1ddee9aa3ee3454e68e",
    (
        "ci",
        "program_tool",
        "app-layout-theme",
    ): "547bfedec6423a8765c0d5dd8a7ae7ea5084ca33ca0503249b65bbc81f20d36c",
    (
        "ci",
        "program_tool",
        "json-to-entity",
    ): "96a7b7afc82ce2dd760657324aa7e09831439a051534d5bd2217d66ff8535edf",
    (
        "ci",
        "program_tool",
        "mqtt-tool",
    ): "6b891df66793ff7f7cf3bb2e2421c786e79f1dadba31ec90e1e2303d200494e4",
    (
        "ci",
        "program_tool",
        "qrcode-tool",
    ): "4c878d048e24ac3c5fcbda16b7080d5b883b2bb9a9a0f96232c3d023e50d4a1d",
    (
        "ci",
        "program_tool",
        "watermark-remover",
    ): "f7855be219c721d61cf40abdc6347f3c0c44ec253ab4e6e450d6a5d18d051c68",
    (
        "p2_context_pack",
        "context_pack_docs",
        "program-tool-developer-docs",
    ): "e1e23ecb9838736707aafe9d6d6f45c72b7355dda21dba759654ef7761bf601b",
    (
        "p2_context_pack",
        "context_pack_frontend",
        "qrcode-feature-context",
    ): "1d9993aaf846f39243f2cf91e169c8112cb7c5b3078830be9551d35ec92fa304",
    (
        "p2_context_pack",
        "context_pack_java",
        "workspace-page-flow",
    ): "c8449ef9f64c01dfaa23ced3bf1d60c2ae01e292a9ac65ad4e98741525aedb5e",
    (
        "p2_context_pack",
        "context_pack_java",
        "workspace-service-symbol",
    ): "655552533fb7c30387b4d6382b60e7adc53c00311604a042062491bd49d66908",
    (
        "p2_context_pack",
        "context_pack_java",
        "workspace-test-file",
    ): "9c2f45cafef740f2e3913e48e822c4cdc9b667ba88201e66da2a9f609299aae5",
}


def _normalize_p9_final_trace_delta(
    actual: dict[str, object],
    expected: dict[str, object],
) -> dict[str, object]:
    """Reverse the reviewed P9 relation-slot delta.

    The relation_slot_selected decision counter is present (value 0
    included) in every final-selection trace, so every case's
    trace_json_sha256 moves off its P7 pin. This overlay pins the new
    hashes for all cases, asserts the structural zero-activity invariant
    on the protected fixtures (the quota must not fire there), strips the
    counter the same way the P7 normalizer strips duplicate_result_path,
    and substitutes the P7-pinned hashes so the untouched P7 normalizer
    keeps validating its own delta chain against the immutable baseline.
    """
    normalized = deepcopy(actual)
    expected_cases = {
        (case["profile"], case["repo_key"], case["case_id"]): case
        for case in expected["cases"]
    }
    mismatches: dict[tuple[str, str, str], str] = {}
    for case in normalized["cases"]:
        key = (case["profile"], case["repo_key"], case["case_id"])
        actual_hash = case["hashes"]["trace_json_sha256"]
        if EXPECTED_P9_FINAL_TRACE_HASHES.get(key) != actual_hash:
            mismatches[key] = actual_hash
        case["hashes"]["trace_json_sha256"] = EXPECTED_P7_FINAL_TRACE_HASHES[
            key
        ]
    if mismatches:
        raise AssertionError(
            "P9 trace hashes changed:\n"
            + "\n".join(
                f"    {key}: \"{value}\","
                for key, value in sorted(mismatches.items())
            )
        )
    for ledger in normalized["full_stage_ledgers"].values():
        final_stage = next(
            stage
            for stage in ledger["stages"]
            if stage["name"] == "final_selection"
        )
        for counts in (
            final_stage["decision_counts"],
            final_stage["live_output"]["decision_counts"],
        ):
            entry_index = next(
                index
                for index, entry in enumerate(counts)
                if entry[0] == "relation_slot_selected"
            )
            assert counts[entry_index][1] == 0, (
                "protected fixture case activated the relation quota"
            )
            counts.pop(entry_index)
    return normalized


def _normalize_p7_final_trace_delta(
    actual: dict[str, object],
    expected: dict[str, object],
) -> dict[str, object]:
    normalized = deepcopy(actual)
    expected_cases = {
        (case["profile"], case["repo_key"], case["case_id"]): case
        for case in expected["cases"]
    }
    assert set(EXPECTED_P7_FINAL_TRACE_HASHES) == set(expected_cases)

    for case in normalized["cases"]:
        key = (case["profile"], case["repo_key"], case["case_id"])
        hashes = case["hashes"]
        expected_hashes = expected_cases[key]["hashes"]
        actual_trace_hash = hashes["trace_json_sha256"]
        assert actual_trace_hash == EXPECTED_P7_FINAL_TRACE_HASHES[key]
        assert actual_trace_hash != expected_hashes["trace_json_sha256"]
        hashes["trace_json_sha256"] = expected_hashes["trace_json_sha256"]

    for ledger in normalized["full_stage_ledgers"].values():
        final_stage = next(
            stage for stage in ledger["stages"] if stage["name"] == "final_selection"
        )
        for counts in (
            final_stage["decision_counts"],
            final_stage["live_output"]["decision_counts"],
        ):
            assert counts[2] == ["duplicate_result_path", 0]
            counts.pop(2)
    return normalized


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


def _without_disabled_profile_work(
    projection: dict[str, object],
) -> dict[str, object]:
    normalized = deepcopy(projection)
    cases = normalized["cases"]
    assert isinstance(cases, list)
    disabled_ledger_keys: set[str] = set()

    def normalize_operations(operations: list[dict[str, object]]) -> None:
        operations[:] = [
            operation
            for operation in operations
            if operation["operation"] not in _DISABLED_PROFILE_OPERATIONS
        ]
        for operation in operations:
            if operation["operation"] != "planner.plan":
                continue
            args = operation["args"]
            assert isinstance(args, dict)
            args.pop("repo_profile", None)

    for case in cases:
        assert isinstance(case, dict)
        planner = case["effective_config"]["query_planner"]
        if planner["enabled"]:
            continue
        disabled_ledger_keys.add(f"{case['repo_key']}/{case['case_id']}")
        normalize_operations(case["ordinary_operations"])
        normalize_operations(case["traced_operations"])

    ledgers = normalized["full_stage_ledgers"]
    assert isinstance(ledgers, dict)
    for key in disabled_ledger_keys & set(ledgers):
        normalize_operations(ledgers[key]["operations"])
    return normalized


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

    for case in actual["cases"]:
        if case["effective_config"]["query_planner"]["enabled"]:
            continue
        for operations in (
            case["ordinary_operations"],
            case["traced_operations"],
        ):
            assert not any(
                operation["operation"] in _DISABLED_PROFILE_OPERATIONS
                for operation in operations
            )
            planner_call = next(
                operation
                for operation in operations
                if operation["operation"] == "planner.plan"
            )
            assert planner_call["args"].get("repo_profile") is None

    normalized_actual = _without_disabled_profile_work(
        _normalize_followup_filter_delta(
            _normalize_p7_final_trace_delta(
                _normalize_p9_final_trace_delta(actual, expected),
                expected,
            ),
            expected,
        )
    )
    normalized_expected = _without_disabled_profile_work(expected)
    assert _without_operation_ledgers(normalized_actual) == _without_operation_ledgers(
        normalized_expected
    )
    for actual_case, expected_case in zip(
        normalized_actual["cases"],
        normalized_expected["cases"],
    ):
        for field in ("ordinary_operations", "traced_operations"):
            _assert_anchor_batch_operation_delta(
                actual_case[field],
                expected_case[field],
            )
    for key, expected_ledger in normalized_expected["full_stage_ledgers"].items():
        _assert_anchor_batch_operation_delta(
            normalized_actual["full_stage_ledgers"][key]["operations"],
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
