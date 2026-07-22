#!/usr/bin/env python3
"""Deterministic P6 benchmark contract helpers.

Task 1 deliberately keeps this module independent from product code.  It owns
only the frozen benchmark/report contracts exercised by the P6 harness tests.
"""

from __future__ import annotations

import argparse
from contextlib import nullcontext
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import platform
import re
import shutil
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import threading
import time
from typing import Any, Iterable, Mapping, Sequence
import xml.etree.ElementTree as ET

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_ROOT = ROOT / "docs" / "benchmarks" / "p6" / "schemas"
DEFAULT_WORKLOAD_MANIFEST = (
    ROOT / "tests" / "fixtures" / "p6_performance" / "workload_manifest.json"
)

REQUIRED_SUBCOMMANDS = (
    "generate",
    "run",
    "churn",
    "assemble",
    "paired",
    "decide",
    "tdd-bootstrap",
    "tdd-red",
    "tdd-green",
    "validate",
    "compare",
    "publish",
)

_GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_ABSOLUTE_WINDOWS_RE = re.compile(r"^[A-Za-z]:[\\/]")
_SECRET_RE = re.compile(r"(?i)(api[_-]?key|bearer|password|secret)(?:=|:)")
_SAFE_ENVIRONMENT_KEYS = {
    "python",
    "cst",
    "sqlite",
    "numpy",
    "os",
    "architecture",
    "cpu_count",
    "memory_bytes",
    "local_disk_class",
    "power_state",
    "governor_state",
    "swap_before_bytes",
    "swap_after_bytes",
    "background_cpu_percent",
    "logical_cpu_count",
    "physical_memory_bytes",
    "swap_growth_bytes",
    "dependency_lock_sha256",
}


class _PathContextWorkCounter:
    def __init__(self) -> None:
        self._seen: set[int] = set()
        self.builds = 0
        self.paths_canonicalized = 0

    def observe(self, repository_path_index: Any) -> None:
        identity = id(repository_path_index)
        if identity in self._seen:
            return
        self._seen.add(identity)
        self.builds += 1
        self.paths_canonicalized += len(repository_path_index.active_paths)
_FORBIDDEN_KEYS = {
    "source_body",
    "vector_values",
    "temporary_root",
    "api_key",
    "credential",
    "headers",
    "response_body",
    "process_command_line",
    "provider_url",
    "endpoint",
}

_QUERY_ATTRIBUTION_COUNTERS = frozenset(
    {
        "repo_profile_vm_steps",
        "repo_profile_rows",
        "repo_profile_bytes",
        "active_ids_materialized",
        "deleted_ids_materialized",
        "id_bytes_materialized",
        "lexical_vm_steps",
        "lexical_rows",
        "path_symbol_rows",
        "path_symbol_bytes",
        "direct_text_rows",
        "direct_text_bytes",
        "signal_rows",
        "signal_bytes",
        "relations_read",
        "relations_resolved",
    }
)

_CHECKPOINT_STABLE_ENVIRONMENT_KEYS = (
    "python",
    "cst",
    "sqlite",
    "numpy",
    "os",
    "architecture",
    "cpu_count",
    "memory_bytes",
    "local_disk_class",
    "power_state",
    "governor_state",
)

ENTRY_RAW_EVIDENCE_NAMES = frozenset(
    {
        "entry-full.xml",
        "entry-p5.json",
        "entry-p4.json",
        "entry-p2.json",
        "entry-ci.json",
        "entry-real-a.json",
        "entry-real-b.json",
        "entry-runtime.json",
        "entry-dependencies.txt",
    }
)
FROZEN_ENTRY_SKIP_NODE_IDS = (
    "tests/test_quality_catalog.py::test_investment_assistant_targets_enter_candidate_pool",
    "tests/test_quality_p1.py::test_phase_one_vector_and_hybrid_profiles_close_together",
    "tests/test_quality_p2.py::test_pinned_real_context_case_is_deterministic_bounded_private_and_passing[database-profiles-integration-tests]",
    "tests/test_quality_p2.py::test_pinned_real_context_case_is_deterministic_bounded_private_and_passing[owner-controller-registration-tests]",
    "tests/test_quality_p2.py::test_pinned_real_context_case_is_deterministic_bounded_private_and_passing[owner-details-pets-visits]",
    "tests/test_quality_p2.py::test_pinned_real_context_case_is_deterministic_bounded_private_and_passing[owner-registration-validation-flow]",
    "tests/test_quality_p2.py::test_pinned_real_context_reports_repeat_except_timing_and_runtime_provenance",
    "tests/test_quality_planner.py::test_real_dashboard_planner_supplies_english_bridge",
    "tests/test_quality_planner.py::test_real_requests_planner_is_three_of_three_with_supported_hints",
)

_ENTRY_QUALITY_TOP_LEVEL_KEYS = frozenset(
    {
        "schema_version",
        "generated_at",
        "tool",
        "fixture",
        "profile",
        "command_args",
        "config",
        "planner",
        "repos",
        "cases",
        "aggregate",
    }
)
_ENTRY_QUALITY_AGGREGATE_KEYS = frozenset(
    {
        "total",
        "selected",
        "attempted",
        "executed",
        "passed",
        "failed",
        "skipped",
        "known_gaps",
        "informational",
        "errors",
        "metrics",
    }
)
_ENTRY_QUALITY_COMMON_CASE_KEYS = frozenset(
    {
        "attempted",
        "case_id",
        "expanded_tokens",
        "failures",
        "gate",
        "known_gap_reason",
        "metrics",
        "planner",
        "query",
        "query_variants",
        "repo_key",
        "status",
        "tags",
        "top_results",
        "variant_retrieval_status",
    }
)
_ENTRY_QUALITY_PROFILES = {
    "entry-p5.json": (
        "p5_language_graphs",
        12,
        frozenset(),
        frozenset({"context_pack"}),
    ),
    "entry-p4.json": (
        "p4_exploration",
        4,
        frozenset({"context_pack"}),
        frozenset(),
    ),
    "entry-p2.json": (
        "p2_context_pack",
        5,
        frozenset({"context_pack"}),
        frozenset(),
    ),
    "entry-ci.json": ("ci", 8, frozenset(), frozenset({"legacy"})),
}
_PINNED_REAL_TOP_LEVEL_KEYS = frozenset(
    {
        "schema_version",
        "fixture_sha256",
        "input_manifest_sha256",
        "profile_definition_sha256",
        "effective_config_hash",
        "profile",
        "cases",
        "aggregate",
    }
)
_PINNED_REAL_CASE_KEYS = frozenset(
    {
        "budgets",
        "case_id",
        "failures",
        "final_context_pack_paths",
        "final_context_pack_sha256",
        "initial_context_pack_paths",
        "initial_context_pack_sha256",
        "initial_result_paths",
        "non_timing_metrics",
        "query",
        "repo_key",
        "source",
        "status",
        "trace",
    }
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="P6 benchmark contract harness")
    subparsers = parser.add_subparsers(dest="command", required=True)

    generate = subparsers.add_parser("generate", help="generate a deterministic repo")
    generate.add_argument("--tier", required=True)
    generate.add_argument("--output", type=Path, required=True)
    generate.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_WORKLOAD_MANIFEST,
    )
    generate.add_argument("--max-files", type=int, help=argparse.SUPPRESS)

    run = subparsers.add_parser("run", help="measure one generated-repo operation")
    run.add_argument("--repo", type=Path, required=True)
    run.add_argument("--manifest", type=Path, required=True)
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--operation")
    run.add_argument("--operations")
    run.add_argument("--case-id")
    run.add_argument("--samples", type=int)
    run.add_argument(
        "--measurement-state",
        choices=(
            "cli_process_cold",
            "mcp_resident_warm",
            "filesystem_cold_diagnostic",
        ),
    )
    run.add_argument("--mode", choices=("baseline", "final"), default="baseline")
    run.add_argument("--checkpoint-dir", type=Path)
    run.add_argument("--resume", action="store_true")

    churn = subparsers.add_parser("churn", help="run the frozen 100-step churn")
    churn.add_argument("--repo", type=Path, required=True)
    churn.add_argument("--manifest", type=Path, required=True)
    churn.add_argument("--output", type=Path, required=True)

    assemble = subparsers.add_parser("assemble", help="assemble validated evidence")
    assemble.add_argument(
        "--kind",
        choices=("entry", "environment", "matrix", "performance", "quality"),
        required=True,
    )
    assemble.add_argument("--mode", choices=("baseline", "final"), default="baseline")
    assemble.add_argument("--input", type=Path, action="append", default=[])
    assemble.add_argument("--input-dir", type=Path)
    assemble.add_argument("--evidence-id")
    assemble.add_argument("--output", type=Path, required=True)
    assemble.add_argument("--manifest", type=Path, default=DEFAULT_WORKLOAD_MANIFEST)

    paired = subparsers.add_parser("paired", help="run alternating implementation pairs")
    paired.add_argument("--baseline-root", type=Path, required=True)
    paired.add_argument("--final-root", type=Path, required=True)
    paired.add_argument("--repo", type=Path, required=True)
    paired.add_argument("--manifest", type=Path, required=True)
    paired.add_argument("--output", type=Path, required=True)
    paired.add_argument("--pairs", type=int, default=30)
    paired.add_argument(
        "--operation-set",
        default="protected_small_entry_comparable",
    )

    decide = subparsers.add_parser("decide", help="emit a closed decision record")
    decide.add_argument(
        "--kind",
        choices=("ann", "exact_ann", "service-watch", "service_watch"),
        required=True,
    )
    decide.add_argument("--input", "--report", dest="input", type=Path, required=True)
    decide.add_argument("--paired", type=Path)
    decide.add_argument("--acceptance", type=Path)
    decide.add_argument("--output", type=Path, required=True)
    decide.add_argument("--trigger-crossed", action="store_true")
    decide.add_argument("--reason", action="append", default=[])

    for command in ("tdd-bootstrap", "tdd-red", "tdd-green"):
        tdd = subparsers.add_parser(command, help=f"run {command} evidence phase")
        tdd.add_argument("--task", type=int, required=True)
        tdd.add_argument("--pre-change-commit", required=True)
        tdd.add_argument("--pytest-node", action="append", default=[])
        tdd.add_argument("--output", type=Path, required=True)
        tdd.add_argument("--staged-tree")
        tdd.add_argument("--red-log", type=Path)
        tdd.add_argument("--red-exit-file", type=Path)
        tdd.add_argument("--test-input-hashes", type=Path)
        tdd.add_argument("--pending", type=Path)

    validate = subparsers.add_parser("validate", help="validate one closed report")
    validate.add_argument("--report", type=Path, required=True)
    validate.add_argument("--schema")
    validate.add_argument("--staged-tree")
    validate.add_argument("--manifest", type=Path, default=DEFAULT_WORKLOAD_MANIFEST)

    compare = subparsers.add_parser("compare", help="compare paired benchmark reports")
    compare.add_argument("--baseline", type=Path, required=True)
    compare.add_argument("--final", type=Path, required=True)
    compare.add_argument("--paired", type=Path)
    compare.add_argument("--churn", type=Path)
    compare.add_argument("--require-churn", action="store_true")
    compare.add_argument("--require-scale-5k-10k", action="store_true")
    compare.add_argument("--output", type=Path)
    compare.add_argument("--manifest", type=Path, default=DEFAULT_WORKLOAD_MANIFEST)

    publish = subparsers.add_parser("publish", help="publish canonical validated JSON")
    publish.add_argument("--input", type=Path, required=True)
    publish.add_argument("--output", type=Path, required=True)
    publish.add_argument("--manifest", type=Path, default=DEFAULT_WORKLOAD_MANIFEST)
    return parser


def canonical_json(value: Any) -> str:
    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ) + "\n"
    except (TypeError, ValueError) as exc:
        raise ValueError("value is not canonical finite JSON") from exc


def workload_contract_sha256(contract: Mapping[str, Any]) -> str:
    generator = contract.get("generator")
    if not isinstance(generator, Mapping):
        raise ValueError("workload generator contract is missing")
    projection = {
        "schema_version": contract.get("schema_version"),
        "generator": {
            key: value for key, value in generator.items() if key != "contract_sha256"
        },
        "tiers": contract.get("tiers"),
        "distributions": contract.get("distributions"),
        "selectivity_families": contract.get("selectivity_families"),
        "edit_schedule": contract.get("edit_schedule"),
        "benchmark_registry": contract.get("benchmark_registry"),
        "protected_small_entry_comparable": contract.get(
            "protected_small_entry_comparable"
        ),
        "expected_fingerprints": contract.get("expected_fingerprints"),
    }
    return hashlib.sha256(canonical_json(projection).encode("utf-8")).hexdigest()


def _assert_finite(value: Any) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("non-finite numeric value")
    if isinstance(value, Mapping):
        for child in value.values():
            _assert_finite(child)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for child in value:
            _assert_finite(child)


def validate_private_payload(
    payload: Any,
    *,
    approved_query_ids: set[str] | None = None,
) -> None:
    approved = approved_query_ids or set()

    def visit(value: Any, path: tuple[str, ...]) -> None:
        if isinstance(value, Mapping):
            for raw_key, child in value.items():
                key = str(raw_key)
                if key in _FORBIDDEN_KEYS:
                    raise ValueError(f"private field is forbidden: {key}")
                if key in {"environment", "env"}:
                    if not isinstance(child, Mapping) or not set(child).issubset(
                        _SAFE_ENVIRONMENT_KEYS
                    ):
                        raise ValueError("raw environment data is forbidden")
                if key == "query_text" and child not in approved:
                    raise ValueError("unapproved query text is forbidden")
                visit(child, (*path, key))
            return
        if isinstance(value, Sequence) and not isinstance(
            value, (str, bytes, bytearray)
        ):
            for child in value:
                visit(child, path)
            return
        if isinstance(value, str):
            if value.startswith(("/", "\\", "file://")):
                raise ValueError("absolute or local paths are forbidden")
            if _ABSOLUTE_WINDOWS_RE.search(value):
                raise ValueError("absolute Windows paths are forbidden")
            if "://" in value:
                raise ValueError("URLs are forbidden")
            if _SECRET_RE.search(value):
                raise ValueError("secret-bearing strings are forbidden")
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("non-finite numeric value")

    visit(payload, ())


def _validate_benchmark_sample_semantics(sample: Mapping[str, Any]) -> None:
    duration = float(sample["duration_ms"])
    if not math.isclose(
        float(sample["stage_timings_ms"]["end_to_end"]),
        duration,
        rel_tol=1e-9,
        abs_tol=1e-9,
    ):
        raise ValueError("benchmark end-to-end timing disagrees with duration")
    rss = sample["rss"]
    if rss["extra_peak_bytes"] != max(
        0, rss["peak_bytes"] - rss["empty_harness_peak_bytes"]
    ):
        raise ValueError("benchmark extra RSS does not match raw peaks")
    work = sample["work"]
    if work["source_bytes_hashed"] > work["source_bytes_read"]:
        raise ValueError("source bytes hashed exceed source bytes read")
    if work["vector_bytes_hashed"] > work["vector_bytes_read"]:
        raise ValueError("vector bytes hashed exceed vector bytes read")


def _validate_benchmark_case_semantics(
    case: Mapping[str, Any],
    *,
    mode: str,
) -> None:
    if case["calibration"]["valid"] is not True or case["validity"]["valid"] is not True:
        raise ValueError("benchmark evidence is invalid")
    samples = case["samples"]
    summary = case["summary"]
    if summary["sample_count"] != len(samples):
        raise ValueError("benchmark summary sample count does not match raw samples")
    sample_ids = [sample["sample_id"] for sample in samples]
    if len(sample_ids) != len(set(sample_ids)):
        raise ValueError("benchmark raw sample IDs must be unique")
    for sample in samples:
        _validate_benchmark_sample_semantics(sample)
    _validate_query_work_contract(case, mode=mode)

    durations = sorted(float(sample["duration_ms"]) for sample in samples)
    expected = {
        "median_ms": statistics.median(durations) if durations else 0.0,
        "p50_ms": statistics.median(durations) if durations else 0.0,
        "p95_ms": (
            durations[math.ceil(0.95 * len(durations)) - 1]
            if durations
            else 0.0
        ),
        "max_ms": max(durations) if durations else 0.0,
        "cv_population": (
            statistics.pstdev(durations) / statistics.fmean(durations)
            if len(durations) > 1 and statistics.fmean(durations) > 0
            else 0.0
        ),
    }
    for key, value in expected.items():
        if not math.isclose(
            float(summary[key]), value, rel_tol=1e-9, abs_tol=1e-9
        ):
            raise ValueError(f"benchmark {key} does not match raw samples")
    if samples and float(summary["cv_population"]) > 0.15:
        raise ValueError("benchmark absolute CV exceeds fifteen percent")


def _validate_query_work_contract(
    case: Mapping[str, Any],
    *,
    mode: str,
) -> None:
    operation = case["operation"]
    if (
        mode != "final"
        or operation["outcome"] != "supported"
        or operation["case_family"] not in {"query", "explore"}
    ):
        return

    manifest = _load_json(DEFAULT_WORKLOAD_MANIFEST)
    tier = manifest["tiers"].get(case["workload"]["tier"])
    if not isinstance(tier, Mapping):
        raise ValueError("query work contract has no workload tier")
    chunks = int(tier["chunks"])
    symbols = int(tier["symbols"])
    signals = int(tier["signals"])
    retrieval_passes = 3 if operation["case_family"] == "explore" else 1
    planner_source_passes = 1 + int(bool(operation["planner_enabled"]))
    path_symbol_row_limit = retrieval_passes * (
        chunks + symbols + (chunks * 16 * planner_source_passes)
    )
    direct_text_row_limit = retrieval_passes * chunks
    signal_row_limit = retrieval_passes * signals * planner_source_passes
    vector_payload_pass_limit = retrieval_passes
    vector_normalization_limit = retrieval_passes
    vector_scored_row_limit = retrieval_passes * chunks
    vector_sorted_row_limit = retrieval_passes * min(chunks, 80)

    for sample in case["samples"]:
        work = sample["work"]
        if not operation["planner_enabled"] and any(
            int(work[name]) != 0
            for name in (
                "repo_profile_vm_steps",
                "repo_profile_rows",
                "repo_profile_bytes",
            )
        ):
            raise ValueError("unused repository profile violates query work contract")
        if int(work["path_symbol_rows"]) > path_symbol_row_limit:
            raise ValueError("path/symbol row budget violates query work contract")
        if int(work["direct_text_rows"]) > direct_text_row_limit:
            raise ValueError("direct-text row budget violates query work contract")
        if int(work["signal_rows"]) > signal_row_limit:
            raise ValueError("signal row budget violates query work contract")
        if int(work["vector_payload_passes"]) > vector_payload_pass_limit:
            raise ValueError("vector payload pass budget violates query work contract")
        if int(work["vector_bytes_hashed"]) > 0:
            raise ValueError("vector payload hash violates query work contract")
        if int(work["vector_normalization_count"]) > vector_normalization_limit:
            raise ValueError("vector normalization violates query work contract")
        if int(work["vector_scored_rows"]) > vector_scored_row_limit:
            raise ValueError("vector score pass violates query work contract")
        if int(work["vector_sorted_rows"]) > vector_sorted_row_limit:
            raise ValueError("vector full-score sort violates query work contract")


def validate_report_data(report: Any, schema_name: str | None = None) -> None:
    if not isinstance(report, Mapping):
        raise ValueError("report must be a JSON object")
    _assert_finite(report)
    if schema_name is None and report.get("kind") == "paired":
        validate_paired_report(report)
        validate_private_payload(report)
        return
    if schema_name is None:
        if report.get("report_kind") == "benchmark":
            schema_name = "benchmark-report-v1.json"
        elif report.get("report_kind") == "acceptance":
            schema_name = "acceptance-report-v1.json"
        elif report.get("report_kind") == "matrix":
            schema_name = "matrix-report-v1.json"
        elif report.get("decision_kind") in {"exact_ann", "service_watch"}:
            schema_name = "decision-record-v1.json"
        elif {"entry_commit", "review_commit", "lineage"}.issubset(report):
            schema_name = "entry-record-v1.json"
        elif {"environment", "calibration", "entry_record_sha256"}.issubset(report):
            schema_name = "environment-report-v1.json"
        elif {"full_suite", "profiles"}.issubset(report):
            schema_name = "quality-report-v1.json"
        elif {"red", "green", "final_staged_tree"}.issubset(report):
            schema_name = "tdd-record-v1.json"
        else:
            raise ValueError("report schema cannot be inferred")
    schema_path = SCHEMA_ROOT / schema_name
    if not schema_path.is_file():
        raise ValueError(f"unknown report schema: {schema_name}")
    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        errors = sorted(
            Draft202012Validator(schema).iter_errors(report),
            key=lambda item: tuple(str(part) for part in item.absolute_path),
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"unreadable report schema: {schema_name}") from exc
    if errors:
        raise ValueError(errors[0].message)
    if schema_name == "benchmark-report-v1.json":
        if report["report_scope"] == "tier":
            _validate_benchmark_case_semantics(report, mode=str(report["mode"]))
        elif report["report_scope"] == "performance":
            cases = report["case_reports"]
            for case in cases:
                _validate_benchmark_case_semantics(
                    case,
                    mode=str(report["mode"]),
                )
            identities = [
                (
                    case["workload"]["tier"],
                    case["workload"]["fingerprint_sha256"],
                    case["operation"]["operation_id"],
                    case["operation"]["case_id"],
                    case["operation"]["measurement_state"],
                )
                for case in cases
            ]
            if len(identities) != len(set(identities)):
                raise ValueError("benchmark performance report contains duplicate cases")
    elif schema_name == "matrix-report-v1.json":
        expected_cells = {
            (os_name, python_version)
            for os_name in ("ubuntu-latest", "macos-latest", "windows-latest")
            for python_version in ("3.11", "3.12", "3.13", "3.14")
        }
        actual_cells = {
            (cell["os"], cell["python_version"]) for cell in report["cells"]
        }
        if actual_cells != expected_cells or len(report["cells"]) != 12:
            raise ValueError("matrix report does not contain the exact cell cross product")
        expected_evidence_id = f"p6-acceptance-{report['implementation_commit']}"
        if report["run"]["evidence_id"] != expected_evidence_id:
            raise ValueError("matrix evidence ID does not bind its implementation")
    elif schema_name == "quality-report-v1.json":
        expected_profiles = {
            "p5_language_graphs": 12,
            "p4_exploration": 4,
            "p2_context_pack": 5,
            "ci": 8,
        }
        for profile, count in expected_profiles.items():
            if report["profiles"][profile] != {
                "passed": count,
                "selected": count,
                "trace_coverage": 1,
            }:
                raise ValueError("quality profile aggregate differs from frozen counts")
        if report["profiles"]["pinned_real"] != {
            "passed": 2,
            "selected": 2,
            "byte_identical": True,
        }:
            raise ValueError("pinned-real quality aggregate differs from frozen counts")
        if report["full_suite"]["skip_node_ids"] != sorted(
            FROZEN_ENTRY_SKIP_NODE_IDS
        ):
            raise ValueError("quality skip identities differ from the frozen audit")
        if [record["task"] for record in report["tdd"]] != list(range(1, 11)):
            raise ValueError("quality TDD summaries are not the exact ordered task set")
    elif schema_name == "decision-record-v1.json":
        if report["decision_kind"] == "exact_ann":
            expected = (
                "prototype_requires_amendment"
                if report["trigger_crossed"]
                else "retained"
            )
            if report["decision"] != expected:
                raise ValueError("ANN decision disagrees with its trigger")
        elif (report["decision"] == "eligible_for_separate_design") != (
            report["reason_codes"] == ["eligibility_met"]
        ):
            raise ValueError("service/watch decision disagrees with its reasons")
    identity_pairs = (
        ("implementation_commit", "production_tree"),
        ("entry_commit", "production_tree"),
        ("pre_change_commit", "pre_change_production_tree"),
    )
    for commit_key, tree_key in identity_pairs:
        if commit_key in report and tree_key in report:
            _verify_commit_tree(report[commit_key], report[tree_key])
            break
    nested_identity = report.get("identity")
    if isinstance(nested_identity, Mapping) and {
        "implementation_commit",
        "production_tree",
    }.issubset(nested_identity):
        _verify_commit_tree(
            nested_identity["implementation_commit"],
            nested_identity["production_tree"],
        )
    validate_private_payload(report)


def _load_json(path: str | Path) -> Any:
    try:
        return json.loads(
            Path(path).read_text(encoding="utf-8"),
            parse_constant=lambda value: (_ for _ in ()).throw(
                ValueError(f"non-finite JSON constant: {value}")
            ),
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("input is not valid JSON") from exc


def _write_new_json(path: str | Path, value: Any) -> None:
    destination = Path(path)
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(destination)
    _assert_finite(value)
    validate_private_payload(value)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(canonical_json(value), encoding="utf-8", newline="\n")


def _write_new_json_atomic(path: str | Path, value: Any) -> None:
    destination = Path(path)
    if os.path.lexists(destination):
        raise FileExistsError(destination)
    _assert_finite(value)
    validate_private_payload(value)
    destination.parent.mkdir(parents=True, exist_ok=True)
    content = canonical_json(value).encode("utf-8")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.",
        suffix=".tmp",
        dir=destination.parent,
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as temporary:
            temporary.write(content)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.link(temporary_path, destination)
    finally:
        temporary_path.unlink(missing_ok=True)


def _sha256_path(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _git_identity(root: Path = ROOT) -> tuple[str, str, bool]:
    commit = validate_git_sha(
        subprocess.check_output(
            ["git", "-C", str(root), "rev-parse", "HEAD"], text=True
        ).strip()
    )
    tree = validate_git_sha(
        subprocess.check_output(
            ["git", "-C", str(root), "rev-parse", "HEAD:src/context_search_tool"],
            text=True,
        ).strip()
    )
    dirty = bool(
        subprocess.check_output(
            [
                "git",
                "-C",
                str(root),
                "status",
                "--porcelain",
                "--",
                "src/context_search_tool",
            ],
            text=True,
        ).strip()
    )
    return commit, tree, dirty


def _production_tree_for_commit(commit: str, root: Path = ROOT) -> str:
    validate_git_sha(commit)
    try:
        value = subprocess.check_output(
            [
                "git",
                "-C",
                str(root),
                "rev-parse",
                f"{commit}:src/context_search_tool",
            ],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except subprocess.CalledProcessError as exc:
        raise ValueError("implementation commit is unavailable") from exc
    return validate_git_sha(value)


def _verify_commit_tree(commit: str, tree: str, root: Path = ROOT) -> None:
    if _production_tree_for_commit(commit, root) != validate_git_sha(tree):
        raise ValueError("production tree does not belong to implementation commit")


def _environment() -> dict[str, Any]:
    try:
        numpy_version = importlib.metadata.version("numpy") or "unavailable"
    except (importlib.metadata.PackageNotFoundError, KeyError):
        numpy_version = "unavailable"
    try:
        cst_version = (
            importlib.metadata.version("context-search-tool") or "0.1.0"
        )
    except (importlib.metadata.PackageNotFoundError, KeyError):
        cst_version = "0.1.0"
    memory_bytes = 1
    swap_bytes = 0
    background_cpu = 100.0
    power_state = "unknown"
    if hasattr(os, "sysconf"):
        try:
            memory_bytes = int(os.sysconf("SC_PAGE_SIZE")) * int(
                os.sysconf("SC_PHYS_PAGES")
            )
        except (OSError, ValueError):
            pass
    try:
        import psutil

        memory_bytes = int(psutil.virtual_memory().total)
        swap_bytes = int(psutil.swap_memory().used)
        background_cpu = float(psutil.cpu_percent(interval=0.1))
        battery = psutil.sensors_battery()
        if battery is None:
            power_state = "external"
        elif battery.power_plugged:
            power_state = "external"
    except (ImportError, OSError, ValueError):
        pass
    system = platform.system().lower()
    if system == "darwin":
        try:
            memory_bytes = int(
                subprocess.check_output(
                    ["/usr/sbin/sysctl", "-n", "hw.memsize"], text=True
                ).strip()
            )
            swap_text = subprocess.check_output(
                ["/usr/sbin/sysctl", "-n", "vm.swapusage"], text=True
            )
            swap_match = re.search(r"used = ([0-9.]+)([MG])", swap_text)
            if swap_match:
                multiplier = 1024**2 if swap_match.group(2) == "M" else 1024**3
                swap_bytes = int(float(swap_match.group(1)) * multiplier)
            power_text = subprocess.check_output(
                ["/usr/bin/pmset", "-g", "batt"], text=True
            )
            if "AC Power" in power_text or "AC attached" in power_text:
                power_state = "external"
            process_cpu = subprocess.check_output(
                ["ps", "-A", "-o", "pid=,%cpu="], text=True
            )
            current_pid = os.getpid()
            total_cpu = 0.0
            for line in process_cpu.splitlines():
                pid_text, cpu_text = line.split()
                if int(pid_text) != current_pid:
                    total_cpu += float(cpu_text)
            background_cpu = min(100.0, total_cpu / max(1, os.cpu_count() or 1))
        except (OSError, ValueError, subprocess.CalledProcessError):
            pass
    if background_cpu == 100.0 and hasattr(os, "getloadavg"):
        try:
            background_cpu = min(
                100.0,
                os.getloadavg()[0] * 100.0 / max(1, os.cpu_count() or 1),
            )
        except OSError:
            pass
    local_disk_class = "unknown"
    if system == "darwin":
        try:
            disk_info = subprocess.check_output(
                ["diskutil", "info", "/"],
                text=True,
                stderr=subprocess.DEVNULL,
            )
            if re.search(r"Solid State:\s+Yes", disk_info):
                local_disk_class = "ssd"
        except (OSError, subprocess.CalledProcessError):
            pass
    governor_state = "not_applicable" if system in {"darwin", "windows"} else "unknown"
    governor = Path("/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor")
    if governor.is_file():
        try:
            governor_state = governor.read_text(encoding="utf-8").strip() or "unknown"
        except OSError:
            pass
    return {
        "python": platform.python_version(),
        "cst": cst_version,
        "sqlite": sqlite3.sqlite_version,
        "numpy": numpy_version,
        "os": {"darwin": "macos"}.get(system, system),
        "architecture": platform.machine() or "unknown",
        "cpu_count": os.cpu_count() or 1,
        "memory_bytes": max(1, memory_bytes),
        "local_disk_class": local_disk_class,
        "power_state": power_state,
        "governor_state": governor_state,
        "swap_before_bytes": swap_bytes,
        "swap_after_bytes": swap_bytes,
        "background_cpu_percent": background_cpu,
    }


def _calibration() -> dict[str, Any]:
    sha256_bytes = 512 * 1024**2
    block = b"p6-calibration\0" * (1024 * 64)
    started = time.perf_counter()
    digest = hashlib.sha256()
    full_blocks, remainder = divmod(sha256_bytes, len(block))
    for _ in range(full_blocks):
        digest.update(block)
    if remainder:
        digest.update(block[:remainder])
    elapsed = max(time.perf_counter() - started, 1e-9)
    mib_per_s = (sha256_bytes / 1024**2) / elapsed

    started = time.perf_counter()
    with sqlite3.connect(":memory:") as connection:
        connection.execute("CREATE TABLE calibration(value INTEGER PRIMARY KEY)")
        connection.executemany(
            "INSERT INTO calibration(value) VALUES (?)", ((i,) for i in range(20000))
        )
        connection.execute(
            "SELECT SUM(value) FROM calibration WHERE value BETWEEN 1000 AND 19000"
        ).fetchone()
    sqlite_ms = max((time.perf_counter() - started) * 1000, 0.001)

    try:
        import numpy as np
    except ImportError as exc:
        raise ValueError("NumPy is required for the frozen P6 calibration") from exc
    matrix = np.ones((80000, 384), dtype=np.float32)
    vector = np.linspace(0.0, 1.0, 384, dtype=np.float32)
    started = time.perf_counter()
    dot_result = matrix @ vector
    if dot_result.shape != (80000,) or not bool(np.isfinite(dot_result).all()):
        raise AssertionError("calibration did not execute")
    numpy_dot_ms = max((time.perf_counter() - started) * 1000, 0.001)
    return {
        "valid": True,
        "sha256_bytes": sha256_bytes,
        "sha256_mib_per_s": mib_per_s,
        "numpy_rows": 80000,
        "numpy_dimensions": 384,
        "numpy_dot_ms": numpy_dot_ms,
        "sqlite_rows": 20000,
        "sqlite_ms": sqlite_ms,
        "within_pair_percent": 0.0,
    }


def _rss_bytes(children: bool = False) -> int:
    try:
        import resource

        who = resource.RUSAGE_CHILDREN if children else resource.RUSAGE_SELF
        value = int(resource.getrusage(who).ru_maxrss)
        return value if sys.platform == "darwin" else value * 1024
    except (ImportError, ValueError):
        return 0


def _disk_components(repo: Path) -> dict[str, int]:
    internal = repo / ".context-search"
    sqlite_bytes = sum(
        path.stat().st_size
        for path in internal.glob("*.sqlite*")
        if path.is_file()
    )
    vector_payload_bytes = sum(
        path.stat().st_size
        for path in internal.glob("*.npy")
        if path.is_file()
    )
    vector_id_bytes = sum(
        path.stat().st_size
        for path in internal.glob("*ids*")
        if path.is_file()
    )
    descriptor_bytes = sum(
        path.stat().st_size
        for path in internal.glob("*descriptor*.json")
        if path.is_file()
    )
    manifest_bytes = (
        (internal / "manifest.json").stat().st_size
        if (internal / "manifest.json").is_file()
        else 0
    )
    total = sum(
        path.stat().st_size for path in internal.rglob("*") if path.is_file()
    ) if internal.exists() else 0
    return {
        "sqlite_bytes": sqlite_bytes,
        "vector_payload_bytes": vector_payload_bytes,
        "vector_id_bytes": vector_id_bytes,
        "descriptor_bytes": descriptor_bytes,
        "manifest_bytes": manifest_bytes,
        "total_bytes": total,
    }


def _storage_work_counters(repo: Path) -> dict[str, int]:
    internal = repo / ".context-search"
    counters = {
        "tombstones": 0,
        "sqlite_pages": 0,
        "sqlite_freelist": 0,
        "generation_count": 0,
    }
    db_path = internal / "index.sqlite"
    if db_path.is_file():
        with sqlite3.connect(db_path) as connection:
            counters["sqlite_pages"] = int(
                connection.execute("PRAGMA page_count").fetchone()[0]
            )
            counters["sqlite_freelist"] = int(
                connection.execute("PRAGMA freelist_count").fetchone()[0]
            )
            table_names = {
                str(row[0])
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
            }
            if "chunks" in table_names:
                deleted = connection.execute(
                    "SELECT COUNT(*) FROM chunks WHERE deleted_at IS NOT NULL"
                ).fetchone()[0]
                counters["tombstones"] = int(deleted or 0)
    counters["generation_count"] = sum(
        path.is_file() for path in internal.glob("vectors.*.npy")
    )
    return counters


def _operation_command(operation: str, repo: Path, case_id: str) -> list[str] | None:
    base = [sys.executable, "-m", "context_search_tool.cli"]
    if operation == "status_quick":
        return [*base, "status", str(repo), "--json"]
    if operation == "status_verified":
        return [*base, "status", str(repo), "--json", "--verify"]
    if operation in {"refresh_noop", "refresh_one_file"}:
        return [*base, "refresh", str(repo), "--json"]
    if operation in {"full_build", "authoritative_noop"}:
        return [*base, "index", str(repo)]
    if operation == "stats":
        return [*base, "stats", str(repo)]
    if operation.startswith("explore"):
        return [*base, "explore", str(repo), case_id, "--no-planner"]
    if operation.startswith("query"):
        return [*base, "query", str(repo), case_id, "--no-planner"]
    raise ValueError(f"unknown benchmark operation: {operation}")


def _operation_cli_args(operation: str, repo: Path, case_id: str) -> list[str]:
    command = _operation_command(operation, repo, case_id)
    if command is None:
        raise ValueError("operation is unsupported by this production tree")
    return command[3:]


def _current_rss_bytes() -> int:
    try:
        import psutil

        return int(psutil.Process().memory_info().rss)
    except (ImportError, OSError):
        pass
    if sys.platform.startswith("linux"):
        try:
            resident_pages = int(Path("/proc/self/statm").read_text().split()[1])
            return resident_pages * int(os.sysconf("SC_PAGE_SIZE"))
        except (OSError, ValueError, IndexError):
            pass
    return _rss_bytes()


def _measurement_output_bytes(operation: str, output: str) -> bytes:
    output = re.sub(
        r"(?m)^direct_text_search slow: [0-9]+(?:\.[0-9]+)?ms "
        r"for ([0-9]+) probes, ([0-9]+) chunks$",
        r"direct_text_search slow: <work-proof-excluded>ms "
        r"for \1 probes, \2 chunks",
        output,
    )
    if operation.startswith("explore"):
        output = re.sub(
            r"(?m)^- Duration: [0-9]+ ms$",
            "- Duration: <work-proof-excluded> ms",
            output,
        )
        output = re.sub(
            r"(?m)^(\| [^\n]+ \| )[0-9]+ \|$",
            r"\1<work-proof-excluded> |",
            output,
        )
    return output.encode("utf-8")


def _legacy_measurement_worker(
    request: Mapping[str, Any],
    *,
    worker_started: float,
    process_start: int,
) -> dict[str, Any]:
    """Measure the frozen pre-P6 product with the current P6 harness."""
    from typer.testing import CliRunner

    import context_search_tool.cli as cli_module
    import context_search_tool.manifest as manifest_module
    import context_search_tool.vector_store as vector_store_module

    operation = str(request.get("operation", ""))
    repo = Path(str(request["repo"])).resolve()
    case_id = str(request.get("case_id", ""))
    original_popen = subprocess.Popen
    original_load_config = cli_module.load_config
    original_manifest_assert = manifest_module.assert_manifest_compatible
    original_load_generation = vector_store_module._load_generation
    child_count = 0
    immutable_state_load_ms = 0.0
    stage_timings = {"config": 0.0, "manifest": 0.0, "semantic": 0.0}

    def counted_popen(*args: Any, **kwargs: Any) -> Any:
        nonlocal child_count
        child_count += 1
        return original_popen(*args, **kwargs)

    def measured_load_config(*args: Any, **kwargs: Any) -> Any:
        nonlocal immutable_state_load_ms
        started = time.perf_counter()
        result = original_load_config(*args, **kwargs)
        elapsed_ms = (time.perf_counter() - started) * 1000
        stage_timings["config"] += elapsed_ms
        immutable_state_load_ms += elapsed_ms
        return result

    def measured_manifest_assert(*args: Any, **kwargs: Any) -> Any:
        nonlocal immutable_state_load_ms
        started = time.perf_counter()
        result = original_manifest_assert(*args, **kwargs)
        elapsed_ms = (time.perf_counter() - started) * 1000
        stage_timings["manifest"] += elapsed_ms
        immutable_state_load_ms += elapsed_ms
        return result

    def measured_load_generation(*args: Any, **kwargs: Any) -> Any:
        nonlocal immutable_state_load_ms
        started = time.perf_counter()
        result = original_load_generation(*args, **kwargs)
        elapsed_ms = (time.perf_counter() - started) * 1000
        stage_timings["semantic"] += elapsed_ms
        immutable_state_load_ms += elapsed_ms
        return result

    subprocess.Popen = counted_popen
    cli_module.load_config = measured_load_config
    manifest_module.assert_manifest_compatible = measured_manifest_assert
    vector_store_module._load_generation = measured_load_generation
    try:
        result = CliRunner().invoke(
            cli_module.app,
            _operation_cli_args(operation, repo, case_id),
        )
    finally:
        subprocess.Popen = original_popen
        cli_module.load_config = original_load_config
        manifest_module.assert_manifest_compatible = original_manifest_assert
        vector_store_module._load_generation = original_load_generation
    duration_ms = (time.perf_counter() - worker_started) * 1000
    if result.exit_code != 0:
        raise ValueError(f"measured operation failed with exit {result.exit_code}")
    peak = _rss_bytes()
    current = _current_rss_bytes()
    benchmark_schema = _load_json(SCHEMA_ROOT / "benchmark-report-v1.json")
    work_names = benchmark_schema["properties"]["samples"]["items"]["properties"][
        "work"
    ]["required"]
    return {
        "duration_ms": duration_ms,
        "rss": {
            "process_start_bytes": process_start,
            "peak_bytes": peak,
            "current_bytes": current,
            "empty_harness_peak_bytes": process_start,
            "extra_peak_bytes": max(0, peak - process_start),
        },
        "attribution": {
            "immutable_state_load_ms": immutable_state_load_ms,
            "trace_duration_ms": 0.0,
            "source_counts": {},
            "stages": [],
            "stage_timings_ms": stage_timings,
            "work": {name: 0 for name in work_names},
        },
        "output_sha256": hashlib.sha256(
            _measurement_output_bytes(operation, result.output)
        ).hexdigest(),
        "product_subprocesses": child_count,
    }


def _measurement_worker(request: Mapping[str, Any]) -> dict[str, Any]:
    worker_started = time.perf_counter()
    worker_kind = str(request.get("kind", "operation"))
    if worker_kind not in {"empty", "operation", "attribution"}:
        raise ValueError("unknown measurement worker kind")
    operation = str(request.get("operation", ""))
    repo = Path(str(request["repo"])).resolve()
    case_id = str(request.get("case_id", ""))
    process_start = _current_rss_bytes()
    if worker_kind == "empty":
        peak = _rss_bytes()
        current = _current_rss_bytes()
        return {
            "duration_ms": 0.0,
            "rss": {
                "process_start_bytes": process_start,
                "peak_bytes": peak,
                "current_bytes": current,
                "empty_harness_peak_bytes": peak,
                "extra_peak_bytes": 0,
            },
            "attribution": None,
            "product_subprocesses": 0,
        }

    from typer.testing import CliRunner

    import context_search_tool.cli as cli_module
    try:
        import context_search_tool.index_health as index_health_module
    except ModuleNotFoundError as exc:
        if exc.name != "context_search_tool.index_health":
            raise
        return _legacy_measurement_worker(
            request,
            worker_started=worker_started,
            process_start=process_start,
        )
    import context_search_tool.indexer as indexer_module
    import context_search_tool.manifest as manifest_module
    import context_search_tool.retrieval as retrieval_module
    import context_search_tool.sqlite_store as sqlite_store_module
    from context_search_tool.embeddings import HashEmbeddingProvider
    from context_search_tool.sqlite_store import GraphReadSession, SQLiteStore
    import context_search_tool.vector_store as vector_store_module
    from context_search_tool.vector_store import NumpyVectorStore

    product_loaded_at = time.perf_counter()
    child_count = 0
    original_popen = subprocess.Popen
    original_query_repository = cli_module.query_repository
    original_load_config = cli_module.load_config
    original_manifest_assert = manifest_module.assert_manifest_compatible
    original_indexer_manifest_assert = indexer_module.assert_manifest_compatible
    original_indexer_load_manifest = indexer_module.load_manifest
    original_indexer_load_manifest_snapshot = indexer_module.load_manifest_snapshot
    original_indexer_write_manifest = indexer_module.write_manifest_v5
    original_indexer_publish_manifest_v2 = indexer_module.publish_manifest_v2
    original_health_observe_workspace = index_health_module.observe_workspace
    original_health_read_observed_file = index_health_module.read_observed_file
    original_health_snapshot_reader = index_health_module.read_committed_index_snapshot
    original_vector_search = NumpyVectorStore.search
    original_scan = indexer_module.scan_workspace_v5
    original_observe_workspace = indexer_module.observe_workspace
    original_read_observed_file = indexer_module.read_observed_file
    original_read_scanned_file_bytes = indexer_module.read_scanned_file_bytes
    original_prepare = indexer_module._prepare_v5_file
    original_embed = HashEmbeddingProvider.embed_texts
    original_resolve = indexer_module.resolve_graph_relations
    original_associate = indexer_module.regenerate_test_associations
    original_prepare_generation = NumpyVectorStore.prepare_generation
    original_freeze_generation_v2 = NumpyVectorStore.freeze_generation_v2
    original_materialize_frozen_generation = (
        NumpyVectorStore.materialize_frozen_generation
    )
    original_publish_generation = NumpyVectorStore.publish_generation
    original_vector_sha256_file = vector_store_module._sha256_file
    original_vector_sha256_file_safe = vector_store_module._sha256_file_safe
    original_load_generation = vector_store_module._load_generation
    original_load_bound_generation = vector_store_module._load_bound_generation
    original_verify_generation_v2_streaming = (
        vector_store_module._verify_generation_v2_streaming
    )
    original_open_connection = sqlite_store_module._open_connection
    original_build_repo_profile = retrieval_module.build_repo_profile
    persistence_names = (
        "begin_v5_file_write",
        "write_v5_file_batch",
        "replace_chunks",
        "replace_signals",
        "replace_relations",
        "finish_v5_file_write",
    )
    original_persistence = {
        name: getattr(SQLiteStore, name) for name in persistence_names
    }
    captured_trace = None
    attributed_stage_timings = {
        "startup": (product_loaded_at - worker_started) * 1000,
        "config": 0.0,
        "manifest": 0.0,
        "inventory": 0.0,
        "source": 0.0,
        "parse": 0.0,
        "embedding": 0.0,
        "persistence": 0.0,
        "graph": 0.0,
        "vector_publication": 0.0,
    }
    immutable_state_load_ms = 0.0
    attributed_work = {
        "inventory_entries": 0,
        "source_bytes_read": 0,
        "source_bytes_hashed": 0,
        "peak_queued_files": 0,
        "peak_queued_chunks": 0,
        "peak_queued_text_bytes": 0,
        "vector_rows_queued": 0,
        "embedding_batch_calls": 0,
        "embedding_batch_inputs": 0,
        "flush_count": 0,
        "repo_profile_vm_steps": 0,
        "repo_profile_rows": 0,
        "repo_profile_bytes": 0,
        "active_ids_materialized": 0,
        "deleted_ids_materialized": 0,
        "id_bytes_materialized": 0,
        "lexical_vm_steps": 0,
        "lexical_rows": 0,
        "path_symbol_rows": 0,
        "path_symbol_bytes": 0,
        "direct_text_rows": 0,
        "direct_text_bytes": 0,
        "signal_rows": 0,
        "signal_bytes": 0,
        "vector_bytes_read": 0,
        "vector_bytes_hashed": 0,
        "vector_bytes_written": 0,
        "vector_payload_passes": 0,
        "vector_normalization_count": 0,
        "vector_scored_rows": 0,
        "vector_sorted_rows": 0,
        "relations_read": 0,
        "relations_resolved": 0,
        "association_writes": 0,
        "path_index_builds": 0,
        "paths_canonicalized": 0,
    }
    path_context_work = _PathContextWorkCounter()

    def traced_query_repository(
        query_repo: Path,
        query: str,
        config: Any,
        context_lines: int | None = None,
        full_file: bool = False,
    ) -> Any:
        nonlocal captured_trace
        traced = retrieval_module.trace_repository(
            query_repo,
            query,
            config,
            context_lines=context_lines,
            full_file=full_file,
        )
        captured_trace = traced.trace
        return traced.bundle

    proof_state: dict[str, str | None] = {"bucket": None, "sql": None}

    def sqlite_value_bytes(value: Any) -> int:
        if value is None:
            return 0
        if isinstance(value, str):
            return len(value.encode("utf-8"))
        if isinstance(value, bytes):
            return len(value)
        if isinstance(value, (int, float)):
            return 8
        raise ValueError("unsupported SQLite work-proof value")

    def row_counter_target(sql: str, bucket: str | None) -> str | None:
        if bucket == "repo_profile" and "select" in sql:
            return "repo_profile"
        if bucket == "lexical" and "chunks_fts" in sql:
            return "lexical"
        if bucket == "path_symbol" and any(
            table in sql
            for table in (
                "from chunks",
                "from chunk_tokens",
                "from chunk_symbols",
                "from symbols",
            )
        ):
            return "path_symbol"
        if bucket == "direct_text" and "from chunks" in sql:
            return "direct_text"
        if bucket == "signal" and "from code_signals" in sql:
            return "signal"
        if "code_relations" in sql and "count(" not in sql:
            return "relations"
        return None

    def proof_open_connection(*args: Any, **kwargs: Any) -> Any:
        connection = original_open_connection(*args, **kwargs)

        def trace_statement(statement: str) -> None:
            proof_state["sql"] = " ".join(statement.lower().split())

        def count_vm_step() -> int:
            bucket = proof_state["bucket"]
            if bucket == "repo_profile":
                attributed_work["repo_profile_vm_steps"] += 1
            elif bucket == "lexical":
                attributed_work["lexical_vm_steps"] += 1
            return 0

        def count_row(cursor: Any, values: tuple[Any, ...]) -> sqlite3.Row:
            row = sqlite3.Row(cursor, values)
            target = row_counter_target(
                str(proof_state["sql"] or ""), proof_state["bucket"]
            )
            if target == "relations":
                keys = set(row.keys())
                if "relation_id" in keys:
                    attributed_work["relations_read"] += 1
                    resolution = row["resolution"] if "resolution" in keys else None
                    target_id = (
                        row["target_signal_id"]
                        if "target_signal_id" in keys
                        else None
                    )
                    if target_id is not None or resolution in {
                        "resolved_exact",
                        "resolved_unique",
                    }:
                        attributed_work["relations_resolved"] += 1
            elif target is not None:
                attributed_work[f"{target}_rows"] += 1
                byte_key = f"{target}_bytes"
                if byte_key in attributed_work:
                    attributed_work[byte_key] += sum(
                        sqlite_value_bytes(value) for value in values
                    )
            return row

        connection.set_trace_callback(trace_statement)
        connection.set_progress_handler(count_vm_step, 1)
        connection.row_factory = count_row
        return connection

    def bucket_wrapper(original: Any, bucket: str) -> Any:
        def counted(*args: Any, **kwargs: Any) -> Any:
            previous = proof_state["bucket"]
            proof_state["bucket"] = bucket
            try:
                return original(*args, **kwargs)
            finally:
                proof_state["bucket"] = previous

        return counted

    def id_wrapper(original: Any, counter: str) -> Any:
        def counted(*args: Any, **kwargs: Any) -> Any:
            values = original(*args, **kwargs)
            attributed_work[counter] += len(values)
            attributed_work["id_bytes_materialized"] += sum(
                len(str(value).encode("utf-8")) for value in values
            )
            return values

        return counted

    def measured_load_config(*args: Any, **kwargs: Any) -> Any:
        nonlocal immutable_state_load_ms
        started = time.perf_counter()
        result = original_load_config(*args, **kwargs)
        elapsed_ms = (time.perf_counter() - started) * 1000
        attributed_stage_timings["config"] += elapsed_ms
        immutable_state_load_ms += elapsed_ms
        return result

    def manifest_wrapper(original: Any) -> Any:
        def measured(*args: Any, **kwargs: Any) -> Any:
            nonlocal immutable_state_load_ms
            started = time.perf_counter()
            result = original(*args, **kwargs)
            elapsed_ms = (time.perf_counter() - started) * 1000
            attributed_stage_timings["manifest"] += elapsed_ms
            immutable_state_load_ms += elapsed_ms
            return result

        return measured

    def measured_vector_search(
        store: Any,
        query_vector: Any,
        top_k: int,
        deleted_ids: set[str],
    ) -> Any:
        row_count = len(store._ids)
        result = original_vector_search(store, query_vector, top_k, deleted_ids)
        attributed_work["vector_normalization_count"] += 1 + (
            row_count if store.normalization != "l2" else 0
        )
        attributed_work["vector_scored_rows"] += row_count
        attributed_work["vector_sorted_rows"] += len(result)
        return result

    def measured_scan(scan_repo: Path, config: Any) -> Any:
        started = time.perf_counter()
        result = original_scan(scan_repo, config)
        attributed_stage_timings["inventory"] += (
            time.perf_counter() - started
        ) * 1000
        attributed_work["inventory_entries"] = len(result)
        return result

    def measured_inventory(scan_repo: Path, config: Any) -> Any:
        started = time.perf_counter()
        result = original_observe_workspace(scan_repo, config)
        attributed_stage_timings["inventory"] += (
            time.perf_counter() - started
        ) * 1000
        attributed_work["inventory_entries"] = len(result.eligible)
        return result

    def measured_observed_read(*args: Any, **kwargs: Any) -> Any:
        started = time.perf_counter()
        result = original_read_observed_file(*args, **kwargs)
        attributed_stage_timings["source"] += (
            time.perf_counter() - started
        ) * 1000
        if result.content is not None:
            attributed_work["source_bytes_read"] += len(result.content)
            attributed_work["source_bytes_hashed"] += len(result.content)
        return result

    def measured_scanned_file_read(*args: Any, **kwargs: Any) -> bytes:
        result = original_read_scanned_file_bytes(*args, **kwargs)
        attributed_work["source_bytes_read"] += len(result)
        return result

    def measured_health_observed_read(*args: Any, **kwargs: Any) -> Any:
        started = time.perf_counter()
        result = original_health_read_observed_file(*args, **kwargs)
        attributed_stage_timings["source"] += (
            time.perf_counter() - started
        ) * 1000
        if result.status == "read" and result.size is not None:
            attributed_work["source_bytes_read"] += int(result.size)
            attributed_work["source_bytes_hashed"] += int(result.size)
        return result

    def measured_health_snapshot(*args: Any, **kwargs: Any) -> Any:
        started = time.perf_counter()
        result = original_health_snapshot_reader(*args, **kwargs)
        attributed_stage_timings["manifest"] += (
            time.perf_counter() - started
        ) * 1000
        return result

    def measured_prepare(*args: Any, **kwargs: Any) -> Any:
        started = time.perf_counter()
        prepared = original_prepare(*args, **kwargs)
        attributed_stage_timings["parse"] += (
            time.perf_counter() - started
        ) * 1000
        attributed_work["peak_queued_files"] += 1
        attributed_work["peak_queued_chunks"] += len(prepared.chunks)
        attributed_work["peak_queued_text_bytes"] += sum(
            len(chunk.content.encode("utf-8")) for chunk in prepared.chunks
        )
        path_context_work.observe(kwargs["repository_path_index"])
        attributed_work["path_index_builds"] = path_context_work.builds
        attributed_work["paths_canonicalized"] = (
            path_context_work.paths_canonicalized
        )
        return prepared

    def measured_embed(provider: Any, texts: list[str]) -> Any:
        started = time.perf_counter()
        result = original_embed(provider, texts)
        attributed_stage_timings["embedding"] += (
            time.perf_counter() - started
        ) * 1000
        attributed_work["embedding_batch_calls"] += 1
        attributed_work["embedding_batch_inputs"] += len(texts)
        attributed_work["vector_rows_queued"] = max(
            attributed_work["vector_rows_queued"],
            len(texts),
        )
        return result

    def persistence_wrapper(name: str) -> Any:
        original = original_persistence[name]

        def measured(store: Any, *args: Any, **kwargs: Any) -> Any:
            started = time.perf_counter()
            result = original(store, *args, **kwargs)
            attributed_stage_timings["persistence"] += (
                time.perf_counter() - started
            ) * 1000
            if name in {"finish_v5_file_write", "write_v5_file_batch"}:
                attributed_work["flush_count"] += 1
            return result

        return measured

    def measured_resolve(*args: Any, **kwargs: Any) -> int:
        started = time.perf_counter()
        count = original_resolve(*args, **kwargs)
        attributed_stage_timings["graph"] += (
            time.perf_counter() - started
        ) * 1000
        attributed_work["relations_read"] += count
        attributed_work["relations_resolved"] += count
        return count

    def measured_associate(*args: Any, **kwargs: Any) -> Any:
        started = time.perf_counter()
        relations = original_associate(*args, **kwargs)
        attributed_stage_timings["graph"] += (
            time.perf_counter() - started
        ) * 1000
        attributed_work["association_writes"] += len(relations)
        return relations

    def measured_prepare_generation(store: Any, *args: Any, **kwargs: Any) -> Any:
        started = time.perf_counter()
        result = original_prepare_generation(store, *args, **kwargs)
        attributed_stage_timings["vector_publication"] += (
            time.perf_counter() - started
        ) * 1000
        descriptor = result.descriptor
        attributed_work["vector_bytes_written"] += (
            (result.index_dir / descriptor.vectors_file).stat().st_size
            + (result.index_dir / descriptor.ids_file).stat().st_size
        )
        return result

    def measured_freeze_generation_v2(
        store: Any,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        started = time.perf_counter()
        result = original_freeze_generation_v2(store, *args, **kwargs)
        attributed_stage_timings["vector_publication"] += (
            time.perf_counter() - started
        ) * 1000
        return result

    def measured_materialize_frozen_generation(
        store: Any,
        frozen: Any,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        started = time.perf_counter()
        result = original_materialize_frozen_generation(
            store,
            frozen,
            *args,
            **kwargs,
        )
        attributed_stage_timings["vector_publication"] += (
            time.perf_counter() - started
        ) * 1000
        attributed_work["vector_bytes_written"] += len(
            frozen.vectors_payload
        ) + len(frozen.ids_payload)
        return result

    def measured_publish_generation(store: Any, *args: Any, **kwargs: Any) -> Any:
        started = time.perf_counter()
        result = original_publish_generation(store, *args, **kwargs)
        attributed_stage_timings["vector_publication"] += (
            time.perf_counter() - started
        ) * 1000
        return result

    def measured_vector_sha256_file(path: Path) -> str:
        size = path.stat().st_size
        attributed_work["vector_bytes_read"] += size
        attributed_work["vector_bytes_hashed"] += size
        if path.name.startswith("vectors.") and path.suffix == ".npy":
            attributed_work["vector_payload_passes"] += 1
        return original_vector_sha256_file(path)

    def measured_load_generation(index_dir: Path, descriptor: Any) -> Any:
        nonlocal immutable_state_load_ms
        vectors_path = index_dir / descriptor.vectors_file
        ids_path = index_dir / descriptor.ids_file
        attributed_work["vector_bytes_read"] += (
            vectors_path.stat().st_size + ids_path.stat().st_size
        )
        attributed_work["vector_payload_passes"] += 1
        started = time.perf_counter()
        result = original_load_generation(index_dir, descriptor)
        immutable_state_load_ms += (time.perf_counter() - started) * 1000
        return result

    def measured_load_bound_generation(index_dir: Path, descriptor: Any) -> Any:
        nonlocal immutable_state_load_ms
        vectors_path = index_dir / descriptor.vectors_file
        ids_path = index_dir / descriptor.ids_file
        attributed_work["vector_bytes_read"] += (
            vectors_path.stat().st_size + ids_path.stat().st_size
        )
        attributed_work["vector_payload_passes"] += 1
        started = time.perf_counter()
        result = original_load_bound_generation(index_dir, descriptor)
        immutable_state_load_ms += (time.perf_counter() - started) * 1000
        return result

    def measured_verify_generation_v2_streaming(
        index_dir: Path,
        descriptor: Any,
    ) -> Any:
        nonlocal immutable_state_load_ms
        vectors_path = index_dir / descriptor.vectors_file
        ids_path = index_dir / descriptor.ids_file
        attributed_work["vector_bytes_read"] += (
            vectors_path.stat().st_size + ids_path.stat().st_size
        )
        attributed_work["vector_bytes_hashed"] += vectors_path.stat().st_size
        attributed_work["vector_payload_passes"] += 1
        started = time.perf_counter()
        result = original_verify_generation_v2_streaming(index_dir, descriptor)
        immutable_state_load_ms += (time.perf_counter() - started) * 1000
        return result

    def counted_popen(*args: Any, **kwargs: Any) -> Any:
        nonlocal child_count
        child_count += 1
        return original_popen(*args, **kwargs)

    query_proof_methods = {
        (SQLiteStore, "lexical_search"): ("lexical", SQLiteStore.lexical_search),
        (SQLiteStore, "path_symbol_search"): (
            "path_symbol",
            SQLiteStore.path_symbol_search,
        ),
        (SQLiteStore, "direct_text_search"): (
            "direct_text",
            SQLiteStore.direct_text_search,
        ),
        (SQLiteStore, "signal_search"): ("signal", SQLiteStore.signal_search),
        (GraphReadSession, "signal_search"): (
            "signal",
            GraphReadSession.signal_search,
        ),
    }
    id_proof_methods = {
        (SQLiteStore, "active_embedding_ids"): (
            "active_ids_materialized",
            SQLiteStore.active_embedding_ids,
        ),
        (GraphReadSession, "active_embedding_ids"): (
            "active_ids_materialized",
            GraphReadSession.active_embedding_ids,
        ),
        (SQLiteStore, "deleted_chunk_ids"): (
            "deleted_ids_materialized",
            SQLiteStore.deleted_chunk_ids,
        ),
        (GraphReadSession, "deleted_chunk_ids"): (
            "deleted_ids_materialized",
            GraphReadSession.deleted_chunk_ids,
        ),
    }
    duration_ms = 0.0
    output_sha256 = ""
    if worker_kind in {"operation", "attribution"}:
        proof_enabled = worker_kind == "attribution"
        if proof_enabled and not operation.startswith(("query", "explore")):
            raise ValueError("attribution worker supports retrieval operations only")
        subprocess.Popen = counted_popen
        cli_module.load_config = measured_load_config
        if operation.startswith("query"):
            cli_module.query_repository = traced_query_repository
            NumpyVectorStore.search = measured_vector_search
            manifest_module.assert_manifest_compatible = manifest_wrapper(
                original_manifest_assert
            )
        if operation.startswith("query") or operation in {
            "full_build",
            "authoritative_noop",
            "status_verified",
            "refresh_noop",
            "refresh_one_file",
        }:
            vector_store_module._sha256_file = measured_vector_sha256_file
            vector_store_module._sha256_file_safe = measured_vector_sha256_file
            vector_store_module._load_generation = measured_load_generation
            vector_store_module._load_bound_generation = (
                measured_load_bound_generation
            )
            vector_store_module._verify_generation_v2_streaming = (
                measured_verify_generation_v2_streaming
            )
        if operation in {
            "full_build",
            "authoritative_noop",
            "refresh_noop",
            "refresh_one_file",
        }:
            indexer_module.scan_workspace_v5 = measured_scan
            indexer_module.observe_workspace = measured_inventory
            indexer_module.read_observed_file = measured_observed_read
            indexer_module.read_scanned_file_bytes = measured_scanned_file_read
            indexer_module._prepare_v5_file = measured_prepare
            indexer_module.assert_manifest_compatible = manifest_wrapper(
                original_indexer_manifest_assert
            )
            indexer_module.load_manifest = manifest_wrapper(
                original_indexer_load_manifest
            )
            indexer_module.load_manifest_snapshot = manifest_wrapper(
                original_indexer_load_manifest_snapshot
            )
            indexer_module.write_manifest_v5 = manifest_wrapper(
                original_indexer_write_manifest
            )
            indexer_module.publish_manifest_v2 = manifest_wrapper(
                original_indexer_publish_manifest_v2
            )
            HashEmbeddingProvider.embed_texts = measured_embed
            indexer_module.resolve_graph_relations = measured_resolve
            indexer_module.regenerate_test_associations = measured_associate
            NumpyVectorStore.prepare_generation = measured_prepare_generation
            NumpyVectorStore.freeze_generation_v2 = measured_freeze_generation_v2
            NumpyVectorStore.materialize_frozen_generation = (
                measured_materialize_frozen_generation
            )
            NumpyVectorStore.publish_generation = measured_publish_generation
            for name in persistence_names:
                setattr(SQLiteStore, name, persistence_wrapper(name))
        if operation in {"status_quick", "status_verified"}:
            index_health_module.observe_workspace = measured_inventory
            index_health_module.read_committed_index_snapshot = (
                measured_health_snapshot
            )
        if operation == "status_verified":
            index_health_module.read_observed_file = measured_health_observed_read
        if proof_enabled:
            sqlite_store_module._open_connection = proof_open_connection
            retrieval_module.build_repo_profile = bucket_wrapper(
                original_build_repo_profile, "repo_profile"
            )
            for (owner, name), (bucket, original) in query_proof_methods.items():
                setattr(owner, name, bucket_wrapper(original, bucket))
            for (owner, name), (counter, original) in id_proof_methods.items():
                setattr(owner, name, id_wrapper(original, counter))
        try:
            result = CliRunner().invoke(
                cli_module.app, _operation_cli_args(operation, repo, case_id)
            )
        finally:
            cli_module.query_repository = original_query_repository
            cli_module.load_config = original_load_config
            manifest_module.assert_manifest_compatible = original_manifest_assert
            indexer_module.assert_manifest_compatible = original_indexer_manifest_assert
            indexer_module.load_manifest = original_indexer_load_manifest
            indexer_module.load_manifest_snapshot = (
                original_indexer_load_manifest_snapshot
            )
            indexer_module.write_manifest_v5 = original_indexer_write_manifest
            indexer_module.publish_manifest_v2 = original_indexer_publish_manifest_v2
            index_health_module.observe_workspace = original_health_observe_workspace
            index_health_module.read_observed_file = original_health_read_observed_file
            index_health_module.read_committed_index_snapshot = (
                original_health_snapshot_reader
            )
            NumpyVectorStore.search = original_vector_search
            indexer_module.scan_workspace_v5 = original_scan
            indexer_module.observe_workspace = original_observe_workspace
            indexer_module.read_observed_file = original_read_observed_file
            indexer_module.read_scanned_file_bytes = original_read_scanned_file_bytes
            indexer_module._prepare_v5_file = original_prepare
            HashEmbeddingProvider.embed_texts = original_embed
            indexer_module.resolve_graph_relations = original_resolve
            indexer_module.regenerate_test_associations = original_associate
            NumpyVectorStore.prepare_generation = original_prepare_generation
            NumpyVectorStore.freeze_generation_v2 = original_freeze_generation_v2
            NumpyVectorStore.materialize_frozen_generation = (
                original_materialize_frozen_generation
            )
            NumpyVectorStore.publish_generation = original_publish_generation
            vector_store_module._sha256_file = original_vector_sha256_file
            vector_store_module._sha256_file_safe = original_vector_sha256_file_safe
            vector_store_module._load_generation = original_load_generation
            vector_store_module._load_bound_generation = (
                original_load_bound_generation
            )
            vector_store_module._verify_generation_v2_streaming = (
                original_verify_generation_v2_streaming
            )
            sqlite_store_module._open_connection = original_open_connection
            retrieval_module.build_repo_profile = original_build_repo_profile
            for (owner, name), (_bucket, original) in query_proof_methods.items():
                setattr(owner, name, original)
            for (owner, name), (_counter, original) in id_proof_methods.items():
                setattr(owner, name, original)
            for name, original in original_persistence.items():
                setattr(SQLiteStore, name, original)
            subprocess.Popen = original_popen
        duration_ms = (time.perf_counter() - worker_started) * 1000
        if result.exit_code != 0:
            raise ValueError(f"measured operation failed with exit {result.exit_code}")
        if operation in {"refresh_noop", "refresh_one_file"}:
            refresh_payload = json.loads(result.output)
            refresh_work = refresh_payload["summary"]["work"]
            attributed_work.update(
                {
                    "inventory_entries": int(refresh_work["inventory"]["entries"]),
                    "inventory_errors": int(refresh_work["inventory"]["errors"]),
                    "source_bytes_read": int(refresh_work["source"]["bytes_read"]),
                    "source_bytes_hashed": int(
                        refresh_work["source"]["bytes_hashed"]
                    ),
                    "path_index_builds": int(refresh_work["path_index"]["builds"]),
                    "paths_canonicalized": int(
                        refresh_work["path_index"]["paths_canonicalized"]
                    ),
                    "relations_read": int(
                        refresh_work["graph"]["relations_scanned"]
                    ),
                    "relations_resolved": int(
                        refresh_work["graph"]["relations_resolved"]
                    ),
                    "association_inputs": int(
                        refresh_work["graph"]["association_inputs"]
                    ),
                    "association_writes": int(
                        refresh_work["graph"]["association_writes"]
                    ),
                    "vector_bytes_read": int(refresh_work["vector"]["bytes_read"]),
                    "vector_bytes_hashed": int(
                        refresh_work["vector"]["bytes_hashed"]
                    ),
                    "vector_bytes_written": int(
                        refresh_work["vector"]["bytes_written"]
                    ),
                    "vector_bytes_copied": int(
                        refresh_work["vector"]["bytes_copied"]
                    ),
                    "vector_payload_passes": int(
                        refresh_work["vector"]["payload_passes"]
                    ),
                    "tombstones": int(
                        refresh_work["maintenance"]["tombstones_after"]
                    ),
                    "sqlite_pages": int(
                        refresh_work["maintenance"]["sqlite_pages_after"]
                    ),
                    "sqlite_freelist": int(
                        refresh_work["maintenance"]["sqlite_freelist_after"]
                    ),
                    "generation_count": int(
                        refresh_work["vector"]["generations_after"]
                    ),
                }
            )
        output_sha256 = hashlib.sha256(
            _measurement_output_bytes(operation, result.output)
        ).hexdigest()
    peak = _rss_bytes()
    current = _current_rss_bytes()
    attribution = {
        "immutable_state_load_ms": immutable_state_load_ms,
        "trace_duration_ms": (
            captured_trace.duration_ms if captured_trace is not None else 0
        ),
        "source_counts": (
            dict(captured_trace.source_counts) if captured_trace is not None else {}
        ),
        "stages": (
            [
                {
                    "name": stage.name,
                    "duration_ms": stage.duration_ms,
                    "input_count": stage.input_count,
                    "output_count": stage.output_count,
                    "unique_output_count": stage.unique_output_count,
                }
                for stage in captured_trace.stages
            ]
            if captured_trace is not None
            else []
        ),
        "stage_timings_ms": attributed_stage_timings,
        "work": attributed_work,
    }
    return {
        "duration_ms": duration_ms,
        "rss": {
            "process_start_bytes": process_start,
            "peak_bytes": peak,
            "current_bytes": current,
            "empty_harness_peak_bytes": process_start,
            "extra_peak_bytes": max(0, peak - process_start),
        },
        "attribution": attribution,
        "output_sha256": output_sha256,
        "product_subprocesses": child_count,
    }


def _measurement_worker_main() -> int:
    try:
        request = json.loads(
            sys.stdin.read(),
            parse_constant=lambda value: (_ for _ in ()).throw(
                ValueError(f"non-finite JSON constant: {value}")
            ),
        )
        sys.stdout.write(canonical_json(_measurement_worker(request)))
        return 0
    except (OSError, ValueError) as exc:
        print(f"p6-measurement-worker: {exc}", file=sys.stderr)
        return 2


def _measurement_resident_worker_main() -> int:
    try:
        for line in sys.stdin:
            request = json.loads(
                line,
                parse_constant=lambda value: (_ for _ in ()).throw(
                    ValueError(f"non-finite JSON constant: {value}")
                ),
            )
            sys.stdout.write(canonical_json(_measurement_worker(request)))
            sys.stdout.flush()
        return 0
    except (OSError, ValueError) as exc:
        print(f"p6-resident-measurement-worker: {exc}", file=sys.stderr)
        return 2


def _invoke_measurement_worker(request: Mapping[str, Any]) -> dict[str, Any]:
    finished = threading.Event()
    started = time.monotonic()
    worker_label = "/".join(
        str(value)
        for value in (request.get("operation"), request.get("kind"))
        if value
    )

    def heartbeat() -> None:
        while not finished.wait(60.0):
            elapsed = int(time.monotonic() - started)
            _benchmark_progress(
                f"worker {worker_label or 'unknown'} still running ({elapsed}s)"
            )

    heartbeat_thread = threading.Thread(target=heartbeat, daemon=True)
    heartbeat_thread.start()
    try:
        completed = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), "__measure"],
            cwd=ROOT,
            input=canonical_json(request),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    finally:
        finished.set()
        heartbeat_thread.join()
    if completed.returncode != 0:
        raise ValueError(
            f"measurement worker failed with exit {completed.returncode}"
        )
    try:
        result = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError("measurement worker returned invalid JSON") from exc
    if result["product_subprocesses"] != 0:
        raise ValueError("product benchmark operation spawned a child process")
    return result


class _ResidentMeasurementWorker:
    def __init__(self) -> None:
        self._process: subprocess.Popen[str] | None = None

    def __enter__(self) -> _ResidentMeasurementWorker:
        self._process = subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve()), "__measure_resident"],
            cwd=ROOT,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
        )
        return self

    def __exit__(self, exc_type: Any, _exc: Any, _traceback: Any) -> None:
        process = self._process
        self._process = None
        if process is None:
            return
        if process.stdin is not None:
            process.stdin.close()
        try:
            return_code = process.wait(timeout=10)
        except subprocess.TimeoutExpired as error:
            process.terminate()
            process.wait(timeout=5)
            if exc_type is None:
                raise ValueError("resident measurement worker did not exit") from error
            return
        if process.stdout is not None:
            process.stdout.close()
        if process.stderr is not None:
            process.stderr.close()
        if return_code != 0 and exc_type is None:
            raise ValueError(
                f"resident measurement worker failed with exit {return_code}"
            )

    def invoke(self, request: Mapping[str, Any]) -> dict[str, Any]:
        process = self._process
        if process is None or process.stdin is None or process.stdout is None:
            raise RuntimeError("resident measurement worker is not running")
        try:
            process.stdin.write(canonical_json(request))
            process.stdin.flush()
            payload = process.stdout.readline()
        except (BrokenPipeError, OSError) as error:
            raise ValueError("resident measurement worker communication failed") from error
        if not payload:
            raise ValueError("resident measurement worker returned no result")
        try:
            result = json.loads(payload)
        except json.JSONDecodeError as error:
            raise ValueError("resident measurement worker returned invalid JSON") from error
        if result["product_subprocesses"] != 0:
            raise ValueError("product benchmark operation spawned a child process")
        return result


def _merge_query_work_proof(
    result: dict[str, Any],
    proof: dict[str, Any],
) -> None:
    if proof["output_sha256"] != result["output_sha256"]:
        raise ValueError("query work-proof output differs from measured output")
    measured_attribution = result.get("attribution")
    proof_attribution = proof.get("attribution")
    if not isinstance(measured_attribution, dict) or not isinstance(
        proof_attribution, dict
    ):
        raise ValueError("query attribution worker returned an invalid result")
    measured_work = measured_attribution.get("work")
    proof_work = proof_attribution.get("work")
    if not isinstance(measured_work, dict) or not isinstance(proof_work, dict):
        raise ValueError("query attribution worker returned invalid counters")
    measured_work.update(
        {name: int(proof_work[name]) for name in _QUERY_ATTRIBUTION_COUNTERS}
    )


class _ResidentMeasurementSession:
    def __init__(self, operation: str, repo: Path, case_id: str) -> None:
        if not operation.startswith(("query", "explore")):
            raise ValueError("resident measurements support retrieval operations only")
        self._operation = operation
        self._repo = repo.resolve()
        self._case_id = case_id
        self._worker: _ResidentMeasurementWorker | None = None
        self._empty_peak_bytes = 0
        self._output_sha256 = ""

    def __enter__(self) -> _ResidentMeasurementSession:
        worker = _ResidentMeasurementWorker()
        self._worker = worker.__enter__()
        try:
            empty = self._worker.invoke(self._request("empty"))
            self._empty_peak_bytes = int(empty["rss"]["peak_bytes"])
            for _ in range(3):
                warmed = self._worker.invoke(self._request("operation"))
                output_sha256 = str(warmed["output_sha256"])
                if self._output_sha256 and output_sha256 != self._output_sha256:
                    raise ValueError("resident warmup product output changed")
                self._output_sha256 = output_sha256
        except BaseException:
            worker.__exit__(*sys.exc_info())
            self._worker = None
            raise
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        worker = self._worker
        self._worker = None
        if worker is not None:
            worker.__exit__(exc_type, exc, traceback)

    def measure(self) -> dict[str, Any]:
        worker = self._worker
        if worker is None:
            raise RuntimeError("resident measurement session is not running")
        result = worker.invoke(self._request("operation"))
        if result["output_sha256"] != self._output_sha256:
            raise ValueError("resident measured product output changed")
        proof = worker.invoke(self._request("attribution"))
        _merge_query_work_proof(result, proof)
        result["rss"]["empty_harness_peak_bytes"] = self._empty_peak_bytes
        result["rss"]["extra_peak_bytes"] = max(
            0,
            int(result["rss"]["peak_bytes"]) - self._empty_peak_bytes,
        )
        return result

    def _request(self, kind: str) -> dict[str, Any]:
        request: dict[str, Any] = {
            "schema_version": 1,
            "repo": str(self._repo),
            "kind": kind,
        }
        if kind != "empty":
            request.update(
                {
                    "operation": self._operation,
                    "case_id": self._case_id,
                }
            )
        return request


def _run_measurement_worker(
    operation: str,
    repo: Path,
    case_id: str,
) -> dict[str, Any]:
    common = {
        "schema_version": 1,
        "repo": str(repo.resolve()),
    }
    empty = _invoke_measurement_worker({**common, "kind": "empty"})
    result = _invoke_measurement_worker(
        {
            **common,
            "kind": "operation",
            "operation": operation,
            "case_id": case_id,
        }
    )
    if operation.startswith(("query", "explore")):
        proof = _invoke_measurement_worker(
            {
                **common,
                "kind": "attribution",
                "operation": operation,
                "case_id": case_id,
            }
        )
        _merge_query_work_proof(result, proof)
    empty_peak = int(empty["rss"]["peak_bytes"])
    result["rss"]["empty_harness_peak_bytes"] = empty_peak
    result["rss"]["extra_peak_bytes"] = max(
        0, int(result["rss"]["peak_bytes"]) - empty_peak
    )
    return result


def _measurement_is_supported(
    operation: str,
    measurement_state: str,
    mode: str,
) -> bool:
    if measurement_state == "mcp_resident_warm":
        return mode == "final" and operation.startswith(("query", "explore"))
    if measurement_state == "filesystem_cold_diagnostic":
        return False
    if mode == "baseline" and operation in {
        "status_quick",
        "status_verified",
        "refresh_noop",
        "refresh_one_file",
    }:
        return False
    return _operation_command(operation, Path("."), "case") is not None


def _clone_operation_repo(source: Path, operation: str, parent: Path) -> Path:
    destination = Path(
        tempfile.mkdtemp(prefix="p6-sample-", dir=parent)
    ) / "repo"
    shutil.copytree(source, destination)
    if operation == "full_build":
        index = destination / ".context-search"
        if index.exists():
            shutil.rmtree(index)
    return destination


def _prepare_one_file_refresh(repo: Path, mutation_id: str) -> Path:
    if re.fullmatch(r"[a-z0-9-]+", mutation_id) is None:
        raise ValueError("one-file refresh mutation identity is invalid")
    sources = _generated_source_paths(repo)
    if not sources:
        raise ValueError("one-file refresh requires generated source")
    source = sources[0]
    source.write_bytes(
        source.read_bytes()
        + f"\n// p6-refresh-mutation:{mutation_id}\n".encode("utf-8")
    )
    return source


def _repository_fingerprint(repo: Path) -> str:
    digest = hashlib.sha256()
    generated_paths = _generated_source_paths(repo)

    def generation_order(path: Path) -> tuple[int, str]:
        match = re.fullmatch(r"GeneratedBenchmarkTypeX(\d{7})\.java", path.name)
        return (
            int(match.group(1)) if match is not None else sys.maxsize,
            path.relative_to(repo).as_posix(),
        )

    for path in sorted(generated_paths, key=generation_order):
        relative = path.relative_to(repo).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _tier_for_repo(repo: Path, manifest: Mapping[str, Any]) -> str:
    generated = len(_generated_source_paths(repo))
    matches = [
        name for name, values in manifest["tiers"].items()
        if values["files"] == generated
    ]
    if len(matches) != 1:
        raise ValueError("generated repository does not match exactly one workload tier")
    return matches[0]


def _generated_source_paths(repo: Path) -> list[Path]:
    generated_root = repo / "generated"
    return sorted(
        path for path in generated_root.rglob("*.java") if path.is_file()
    )


def _relation_out_degree(source_index: int, source_count: int) -> int:
    median_boundary = source_count // 2
    p95_index = math.ceil(0.95 * source_count) - 1
    if source_index < median_boundary:
        return 2
    if source_index < p95_index:
        return 4
    if source_index == p95_index:
        return 8
    tail_index = source_index - p95_index - 1
    tail_count = source_count - p95_index - 1
    if tail_index == 0:
        return 16
    if tail_index == 1:
        return 20
    if tail_index == tail_count - 1:
        return 32
    return 24


def _relation_target_name(target_id: int) -> str:
    if not 0 <= target_id < 2**23:
        raise ValueError("relation target identity exceeds the frozen encoding")
    return f"I{target_id}"


def _relation_targets(source_index: int, count: int) -> list[str]:
    fan_in_bands = (1, 5, 10, 20)
    group_space = 2**18
    targets = []
    for ordinal in range(count):
        fan_in = fan_in_bands[ordinal % len(fan_in_bands)]
        group = source_index // fan_in
        targets.append(_relation_target_name(ordinal * group_space + group))
    return targets


def _comment_for_metadata_size(
    class_name: str,
    base_text: str,
    target_size: int,
) -> str:
    metadata = {
        "owner_kind": "type",
        "owner_qualified_name": class_name,
        "text": base_text,
    }
    current_size = len(
        json.dumps(metadata, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )
    if current_size > target_size:
        raise ValueError("comment metadata target is too small")
    return base_text + "-" * (target_size - current_size)


def _generated_java_bytes(
    index: int,
    target_size: int,
    file_count: int,
) -> bytes:
    source_count = file_count * 4
    class_names = [
        f"GeneratedBenchmarkTypeX{index * 4 + slot:07d}" for slot in range(4)
    ]
    extra_token_files = file_count * 7 // 20 + 19
    words = [f"benchword{word_index}" for word_index in range(28)]
    final_comment_base = " ".join(words[18:])
    if index < extra_token_files:
        final_comment_base += " bonusmarker"
    final_comment = _comment_for_metadata_size(
        class_names[0],
        final_comment_base,
        4096 if index % 100 == 0 else 512,
    )
    semantic_lines = [
        "package generated;",
        "// " + " ".join(words[:9]),
        "// " + " ".join(words[9:18]),
        "// " + final_comment,
    ]
    for slot, class_name in enumerate(class_names):
        source_index = index * 4 + slot
        targets = _relation_targets(
            source_index,
            _relation_out_degree(source_index, source_count),
        )
        semantic_lines.extend(
            (
                f"class {class_name} implements " + ", ".join(targets) + " {",
                f"    private Object field{'ABCD'[slot]};",
                "}",
            )
        )
    blank_count = 320 - len(semantic_lines)
    if blank_count < 1:
        raise AssertionError("generated Java template has no padding lines")
    lines = [*semantic_lines, *([" "] * blank_count)]
    base = ("\n".join(lines) + "\n").encode("utf-8")
    padding = target_size - len(base)
    if padding < 0:
        raise ValueError("workload file byte target is too small")
    per_line, remainder = divmod(padding, blank_count)
    first_blank = len(semantic_lines)
    for blank_index in range(blank_count):
        lines[first_blank + blank_index] += " " * (
            per_line + (1 if blank_index < remainder else 0)
        )
    result = ("\n".join(lines) + "\n").encode("utf-8")
    if len(lines) != 320 or len(result) != target_size:
        raise AssertionError("generated Java byte/line contract drifted")
    return result


def _tier_file_sizes(
    file_count: int,
    source_bytes: int,
    distribution: Mapping[str, Any],
) -> list[int]:
    p50 = int(distribution["p50"])
    p95 = int(distribution["p95"])
    maximum = int(distribution["max"])
    p50_rank = math.ceil(0.50 * file_count)
    p95_rank = math.ceil(0.95 * file_count)
    low_count = p50_rank - 1
    sizes = [4096] * low_count
    sizes.extend([p50] * (p95_rank - p50_rank))
    sizes.extend([p95] * (file_count - p95_rank))
    sizes.append(maximum)
    remainder = source_bytes - sum(sizes)
    if remainder < 0 or low_count == 0:
        raise ValueError("tier bytes cannot realize the frozen file-size distribution")
    allocation_bands = (
        (range(0, low_count), p50),
        (range(p50_rank, p95_rank - 1), p95),
        (range(p95_rank, file_count - 1), maximum),
    )
    for indices, ceiling in allocation_bands:
        positions = list(indices)
        if not positions or remainder == 0:
            continue
        capacity_per_file = ceiling - sizes[positions[0]]
        allocated = min(remainder, capacity_per_file * len(positions))
        per_file, extra = divmod(allocated, len(positions))
        for offset, index in enumerate(positions):
            sizes[index] += per_file + (1 if offset < extra else 0)
        remainder -= allocated
    if remainder:
        raise ValueError("tier bytes exceed the frozen file-size distribution")
    if sum(sizes) != source_bytes:
        raise AssertionError("tier byte allocation drifted")
    return sizes


def _generated_relative_path(index: int, file_count: int) -> Path:
    p50_rank = math.ceil(0.50 * file_count)
    p95_rank = math.ceil(0.95 * file_count)
    if index < p50_rank - 1:
        depth = 3
    elif index < p95_rank - 1:
        depth = 4
    elif index < file_count - 1:
        depth = 8
    else:
        depth = 16
    role = "test" if index % 5 == 4 else "source"
    directories = ["generated", role, *(["generated"] * (depth - 3))]
    class_name = f"GeneratedBenchmarkTypeX{index * 4:07d}"
    return Path(*directories, f"{class_name}.java")


def _schedule_payload_sha256(
    version: str,
    seed: int,
    step: int,
    operation: str,
) -> str:
    identity = f"{version}\0{seed}\0{step}\0{operation}".encode("utf-8")
    return hashlib.sha256(identity).hexdigest()


def _repository_relative_schedule_path(value: Any) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise ValueError("edit-schedule targets must be repository-relative paths")
    path = Path(value)
    if path.is_absolute() or _ABSOLUTE_WINDOWS_RE.match(value) or ".." in path.parts:
        raise ValueError("edit-schedule targets must be repository-relative paths")
    return path.as_posix()


def _edit_schedule_actions(
    schedule: Mapping[str, Any],
    *,
    seed: int,
    file_count: int,
) -> list[dict[str, Any]]:
    version = str(schedule["version"])
    steps = int(schedule["steps"])
    cycle_length = int(schedule["cycle_length"])
    sample_every = int(schedule["sample_every_steps"])
    target_stride = int(schedule["base_target_stride"])
    failure_variants = list(schedule["failure_variants"])
    if (
        steps != 100
        or cycle_length != 10
        or sample_every != 10
        or target_stride < 6
        or failure_variants != ["directory_failure", "control_file_failure"]
    ):
        raise ValueError("invalid frozen P6 edit-schedule shape")
    cycle_count = steps // cycle_length
    if cycle_count * cycle_length != steps:
        raise ValueError("edit-schedule steps must contain complete cycles")
    highest_target_index = (cycle_count - 1) * target_stride + 5
    if highest_target_index >= file_count:
        raise ValueError("workload tier has too few files for the edit schedule")

    actions: list[dict[str, Any]] = []
    for cycle in range(cycle_count):
        first_step = cycle * cycle_length + 1
        targets = [
            _generated_relative_path(cycle * target_stride + offset, file_count)
            .as_posix()
            for offset in range(6)
        ]
        addition_target = f"generated/churn/AddedBenchmarkTypeX{cycle:02d}.java"
        failure_operation = failure_variants[cycle % len(failure_variants)]
        failure_target = (
            _repository_relative_schedule_path(schedule["directory_failure_target"])
            if failure_operation == "directory_failure"
            else _repository_relative_schedule_path(schedule["control_file"])
        )

        actions.extend(
            [
                {
                    "step": first_step,
                    "operation": "modify",
                    "target": targets[0],
                    "sample_after": False,
                    "expected_outcome": "applied",
                    "payload_sha256": _schedule_payload_sha256(
                        version, seed, first_step, "modify"
                    ),
                },
                {
                    "step": first_step + 1,
                    "operation": "delete",
                    "target": targets[1],
                    "sample_after": False,
                    "expected_outcome": "applied",
                },
                {
                    "step": first_step + 2,
                    "operation": "restore",
                    "target": targets[1],
                    "sample_after": False,
                    "expected_outcome": "applied",
                    "source_step": first_step + 1,
                },
                {
                    "step": first_step + 3,
                    "operation": "add",
                    "target": addition_target,
                    "sample_after": False,
                    "expected_outcome": "applied",
                    "payload_sha256": _schedule_payload_sha256(
                        version, seed, first_step + 3, "add"
                    ),
                },
                {
                    "step": first_step + 4,
                    "operation": "delete_added",
                    "target": addition_target,
                    "sample_after": False,
                    "expected_outcome": "applied",
                    "source_step": first_step + 3,
                },
                {
                    "step": first_step + 5,
                    "operation": "equal_content_touch",
                    "target": targets[2],
                    "sample_after": False,
                    "expected_outcome": "applied",
                    "preserve_content": True,
                },
                {
                    "step": first_step + 6,
                    "operation": "same_metadata_content_edit",
                    "target": targets[3],
                    "sample_after": False,
                    "expected_outcome": "applied",
                    "observer": "no_ctime",
                    "preserve_size": True,
                    "preserve_mtime": True,
                    "payload_sha256": _schedule_payload_sha256(
                        version,
                        seed,
                        first_step + 6,
                        "same_metadata_content_edit",
                    ),
                },
                {
                    "step": first_step + 7,
                    "operation": "stable_skip",
                    "target": targets[4],
                    "sample_after": False,
                    "expected_outcome": "stable_skip",
                },
                {
                    "step": first_step + 8,
                    "operation": "retryable_skip",
                    "target": targets[5],
                    "sample_after": False,
                    "expected_outcome": "retryable_skip",
                },
                {
                    "step": first_step + 9,
                    "operation": failure_operation,
                    "target": failure_target,
                    "sample_after": True,
                    "expected_outcome": "injected_failure",
                },
            ]
        )
    return actions


def generate_edit_schedule(
    contract: Mapping[str, Any],
    tier: str,
) -> dict[str, Any]:
    schedule = contract["edit_schedule"]
    expected_keys = {
        "version",
        "steps",
        "sample_every_steps",
        "sample_operations",
        "cycle_length",
        "base_target_stride",
        "failure_variants",
        "control_file",
        "directory_failure_target",
        "operation_counts",
        "expected_trace_sha256",
    }
    if set(schedule) != expected_keys:
        raise ValueError("edit schedule must use the closed P6 contract")
    if schedule["sample_operations"] != ["status", "query"]:
        raise ValueError("edit schedule must sample status and query")
    if tier not in contract["tiers"]:
        raise ValueError(f"unknown workload tier: {tier}")
    seed = contract["generator"]["seed"]
    if not isinstance(seed, int):
        raise ValueError("generator seed must be an integer")
    actions = _edit_schedule_actions(
        schedule,
        seed=seed,
        file_count=int(contract["tiers"][tier]["files"]),
    )
    counts: dict[str, int] = {}
    for action in actions:
        operation = action["operation"]
        counts[operation] = counts.get(operation, 0) + 1
    if counts != schedule["operation_counts"]:
        raise ValueError("edit-schedule operation counts do not match the trace")
    trace_sha256 = hashlib.sha256(canonical_json(actions).encode("utf-8")).hexdigest()
    if trace_sha256 != schedule["expected_trace_sha256"]:
        raise ValueError("edit-schedule fingerprint does not match the manifest")
    return {
        "schema_version": 1,
        "version": schedule["version"],
        "seed": seed,
        "steps": schedule["steps"],
        "sample_every_steps": schedule["sample_every_steps"],
        "sample_operations": schedule["sample_operations"],
        "trace_sha256": trace_sha256,
        "actions": actions,
    }


def _churn_query_durations(repo: Path, config: Any, *, sample_count: int) -> list[float]:
    from context_search_tool.retrieval import query_repository

    def query_once() -> float:
        started = time.perf_counter()
        bundle = query_repository(repo, "benchword1", config)
        duration_ms = (time.perf_counter() - started) * 1000
        if not bundle.results:
            raise ValueError("churn query returned no results")
        return duration_ms

    for _ in range(3):
        query_once()
    return [query_once() for _ in range(sample_count)]


def _churn_p95(values: Sequence[float]) -> float:
    if not values:
        raise ValueError("churn timing samples are required")
    ordered = sorted(float(value) for value in values)
    return ordered[math.ceil(0.95 * len(ordered)) - 1]


def _run_churn_refresh_action(
    repo: Path,
    action: Mapping[str, Any],
    *,
    config: Any,
    deleted_payloads: dict[int, bytes],
) -> Any:
    from dataclasses import replace

    from context_search_tool.indexer import refresh_repository
    from context_search_tool.scanner import (
        InventoryDiagnostic,
        ObservedFileRead,
        observe_workspace,
        read_observed_file,
    )

    operation = str(action["operation"])
    relative = Path(str(action["target"]))
    target = repo / relative
    inventory_observer = None
    observed_reader = None

    if operation == "modify":
        target.write_bytes(
            target.read_bytes()
            + f"\n// p6-churn:{action['payload_sha256']}\n".encode("utf-8")
        )
    elif operation == "delete":
        deleted_payloads[int(action["step"])] = target.read_bytes()
        target.unlink()
    elif operation == "restore":
        source_step = int(action["source_step"])
        payload = deleted_payloads.get(source_step)
        if payload is None or target.exists():
            raise ValueError("churn restore source is unavailable")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
    elif operation == "add":
        if target.exists():
            raise ValueError("churn addition target already exists")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            (
                f"package generated.churn; class {target.stem} {{\n"
                f"  String marker() {{ return \"{action['payload_sha256']}\"; }}\n"
                "}\n"
            ),
            encoding="utf-8",
        )
    elif operation == "delete_added":
        target.unlink()
    elif operation == "equal_content_touch":
        metadata = target.stat()
        os.utime(
            target,
            ns=(metadata.st_atime_ns, metadata.st_mtime_ns + 1_000_000),
        )
    elif operation == "same_metadata_content_edit":
        metadata = target.stat()
        payload = target.read_bytes()
        changed = payload.replace(b"benchword", b"BENCHword", 1)
        if changed == payload or len(changed) != len(payload):
            raise ValueError("churn same-metadata edit could not preserve size")
        target.write_bytes(changed)
        os.utime(target, ns=(metadata.st_atime_ns, metadata.st_mtime_ns))
    elif operation in {"stable_skip", "retryable_skip"}:
        target.write_bytes(
            target.read_bytes()
            + f"\n// p6-churn-skip:{action['step']}\n".encode("utf-8")
        )
        reason = "too_large" if operation == "stable_skip" else "unreadable"
        retryable = operation == "retryable_skip"

        def skipped_reader(
            repo_path: Path,
            observation: Any,
            **kwargs: Any,
        ) -> Any:
            if observation.path == relative:
                return ObservedFileRead(
                    status="skipped",
                    path=observation.path,
                    content=None,
                    sha256=None,
                    size=observation.size,
                    reason=reason,
                    retryable=retryable,
                    metadata=observation.metadata,
                )
            return read_observed_file(repo_path, observation, **kwargs)

        observed_reader = skipped_reader
    elif operation in {"directory_failure", "control_file_failure"}:
        diagnostic = (
            InventoryDiagnostic(
                code="unscannable_subtree",
                scope="directory",
                path=relative.as_posix(),
            )
            if operation == "directory_failure"
            else InventoryDiagnostic(
                code="control_file_error",
                scope="control",
                path=relative.as_posix(),
            )
        )

        def failed_inventory(repo_path: Path, effective_config: Any) -> Any:
            inventory = observe_workspace(repo_path, effective_config)
            return replace(
                inventory,
                complete=False,
                unscannable_subtrees=(
                    (relative.as_posix(),)
                    if operation == "directory_failure"
                    else inventory.unscannable_subtrees
                ),
                control_file_errors=(
                    (diagnostic,)
                    if operation == "control_file_failure"
                    else inventory.control_file_errors
                ),
                diagnostics=tuple((*inventory.diagnostics, diagnostic)),
            )

        inventory_observer = failed_inventory
    else:
        raise ValueError(f"unknown churn operation: {operation}")

    kwargs: dict[str, Any] = {"config": config}
    if inventory_observer is not None:
        kwargs["inventory_observer"] = inventory_observer
    if observed_reader is not None:
        kwargs["observed_reader"] = observed_reader
    return refresh_repository(repo, **kwargs)


def _run_churn_refresh_with_cleanup_fault(
    repo: Path,
    action: Mapping[str, Any],
    *,
    config: Any,
    deleted_payloads: dict[int, bytes],
    vector_store_type: type[Any],
) -> Any:
    original_cleanup = vector_store_type.__dict__["cleanup_unreferenced_generations"]
    cleanup_calls = 0

    def fail_cleanup(cls: type[Any], *_args: Any, **_kwargs: Any) -> int:
        nonlocal cleanup_calls
        cleanup_calls += 1
        raise OSError("injected churn cleanup failure")

    setattr(
        vector_store_type,
        "cleanup_unreferenced_generations",
        classmethod(fail_cleanup),
    )
    try:
        result = _run_churn_refresh_action(
            repo,
            action,
            config=config,
            deleted_payloads=deleted_payloads,
        )
    finally:
        setattr(
            vector_store_type,
            "cleanup_unreferenced_generations",
            original_cleanup,
        )
    if cleanup_calls != 1:
        raise ValueError("churn cleanup fault was not exercised exactly once")
    return result


def run_churn(
    repo: str | Path,
    manifest: str | Path,
) -> dict[str, Any]:
    from context_search_tool import index_health
    from context_search_tool.config import load_config
    from context_search_tool.retrieval import query_repository
    from context_search_tool.sqlite_store import SQLiteStore
    from context_search_tool.vector_store import NumpyVectorStore

    repo_path = Path(repo).resolve()
    manifest_path = Path(manifest).resolve()
    if not repo_path.is_dir() or (repo_path / ".context-search").exists():
        raise ValueError("churn requires a pristine generated repository")
    contract = _load_json(manifest_path)
    tier = _tier_for_repo(repo_path, contract)
    fingerprint = _repository_fingerprint(repo_path)
    if fingerprint != contract.get("expected_fingerprints", {}).get(tier):
        raise ValueError("churn repository fingerprint differs from workload contract")
    schedule = generate_edit_schedule(contract, tier)
    commit, tree, dirty = _git_identity()
    if dirty:
        raise ValueError("churn refuses dirty production source")
    harness_sha256 = _sha256_path(__file__)
    workload_sha256 = _sha256_path(manifest_path)

    _benchmark_progress("churn ready snapshot build started")
    _run_measurement_worker("full_build", repo_path, "default")
    config = load_config(repo_path)
    baseline_disk = _disk_components(repo_path)
    baseline_storage = _storage_work_counters(repo_path)
    baseline_durations = _churn_query_durations(
        repo_path,
        config,
        sample_count=20,
    )

    deleted_payloads: dict[int, bytes] = {}
    generation_count_after_failure = 0
    cleanup_failure_recovered = False
    sampled_steps = 0
    for action in schedule["actions"]:
        step = int(action["step"])
        operation = str(action["operation"])
        _benchmark_progress(f"churn step {step}/100 {operation} started")
        if step == 1:
            result = _run_churn_refresh_with_cleanup_fault(
                repo_path,
                action,
                config=config,
                deleted_payloads=deleted_payloads,
                vector_store_type=NumpyVectorStore,
            )
            cleanup_failure_generations = NumpyVectorStore.generation_pair_count(
                repo_path / ".context-search"
            )
            if cleanup_failure_generations != 2:
                raise ValueError(
                    "churn cleanup fault did not retain exactly two generations"
                )
            generation_count_after_failure = max(
                generation_count_after_failure,
                cleanup_failure_generations,
            )
        else:
            result = _run_churn_refresh_action(
                repo_path,
                action,
                config=config,
                deleted_payloads=deleted_payloads,
            )
        injected_failure = action["expected_outcome"] == "injected_failure"
        if injected_failure:
            if getattr(result, "ok", True) or getattr(result, "code", "") != (
                "inventory_incomplete"
            ):
                raise ValueError("churn injected failure did not fail closed")
            generation_count_after_failure = max(
                generation_count_after_failure,
                NumpyVectorStore.generation_pair_count(
                    repo_path / ".context-search"
                ),
            )
        elif not getattr(result, "ok", False):
            raise ValueError(f"churn step failed: {operation}")

        if step == 2:
            if NumpyVectorStore.generation_pair_count(
                repo_path / ".context-search"
            ) != 1:
                raise ValueError(
                    "churn cleanup fault was not recovered by the next writer"
                )
            cleanup_failure_recovered = True

        if action["sample_after"]:
            sampled_steps += 1
            health = index_health.inspect_repository_health(
                repo_path,
                mode="quick",
            )
            if not health.queryable:
                raise ValueError("churn checkpoint is not queryable")
            if not query_repository(repo_path, "benchword1", config).results:
                raise ValueError("churn checkpoint query returned no results")
            store = SQLiteStore(repo_path / ".context-search" / "index.sqlite")
            NumpyVectorStore.verify_published_snapshot(
                repo_path / ".context-search",
                expected_ids=store.active_embedding_ids(),
            )
        _benchmark_progress(f"churn step {step}/100 complete")

    if sampled_steps != 10:
        raise ValueError("churn did not sample every frozen cycle")
    if not cleanup_failure_recovered:
        raise ValueError("churn cleanup recovery was not exercised")
    final_durations = _churn_query_durations(
        repo_path,
        config,
        sample_count=20,
    )
    baseline_p95 = _churn_p95(baseline_durations)
    final_p95 = _churn_p95(final_durations)
    if baseline_p95 <= 0:
        raise ValueError("churn baseline query timing is invalid")
    final_disk = _disk_components(repo_path)
    final_storage = _storage_work_counters(repo_path)
    disk_ratio = final_disk["total_bytes"] / max(1, baseline_disk["total_bytes"])
    page_ratio = final_storage["sqlite_pages"] / max(
        1,
        baseline_storage["sqlite_pages"],
    )
    store = SQLiteStore(repo_path / ".context-search" / "index.sqlite")

    final_commit, final_tree, final_dirty = _git_identity()
    if (final_commit, final_tree, final_dirty) != (commit, tree, False):
        raise ValueError("churn implementation identity changed during the run")
    report = {
        "schema_version": 1,
        "report_kind": "benchmark",
        "report_scope": "churn",
        "mode": "final",
        "identity": {
            "implementation_commit": commit,
            "production_tree": tree,
            "harness_sha256": harness_sha256,
            "workload_sha256": workload_sha256,
            "dirty_production_source": False,
        },
        "workload": {
            "schema_version": 1,
            "generator_version": contract["generator"]["version"],
            "generator_sha256": contract["generator"]["contract_sha256"],
            "seed": contract["generator"]["seed"],
            "tier": tier,
            "fingerprint_sha256": fingerprint,
        },
        "churn": {
            "steps": int(schedule["steps"]),
            "disk_page_ratio": max(disk_ratio, page_ratio),
            "tombstones_within_threshold": not store.maintenance_required(),
            "query_p95_drift_ratio": max(
                0.0,
                (final_p95 / baseline_p95) - 1.0,
            ),
            "generation_count_after_failure": generation_count_after_failure,
        },
    }
    validate_report_data(report, "benchmark-report-v1.json")
    return report


_BENCHMARK_REGISTRY_KEYS = {"version", "measurement_states", "cases"}
_BENCHMARK_STATE_KEYS = {"id", "acceptance_evidence", "informational_only"}
_BENCHMARK_CASE_KEYS = {
    "operation_id",
    "case_id",
    "protected_operation_id",
    "case_family",
    "tiers",
    "planner_enabled",
    "query_case_id",
    "measurements",
}
_BENCHMARK_MEASUREMENT_KEYS = {"state", "sample_count", "baseline_outcome"}
_BENCHMARK_MEASUREMENT_STATES = {
    "cli_process_cold",
    "mcp_resident_warm",
    "filesystem_cold_diagnostic",
}


def _benchmark_request(
    contract: Mapping[str, Any],
    manifest: str | Path,
    *,
    tier: str,
    operation: str,
    case_id: str,
    sample_count: int,
    measurement_state: str,
) -> dict[str, Any]:
    registry = contract.get("benchmark_registry")
    if not isinstance(registry, dict) or set(registry) != _BENCHMARK_REGISTRY_KEYS:
        raise ValueError("benchmark registry must use the closed P6 contract")
    if registry["version"] != "p6-benchmark-registry-v1":
        raise ValueError("unknown benchmark registry version")

    states = registry["measurement_states"]
    if not isinstance(states, list):
        raise ValueError("benchmark measurement states must be a list")
    by_state: dict[str, Mapping[str, Any]] = {}
    for state in states:
        if not isinstance(state, dict) or set(state) != _BENCHMARK_STATE_KEYS:
            raise ValueError("benchmark measurement-state contract is not closed")
        state_id = state["id"]
        if (
            not isinstance(state_id, str)
            or state_id in by_state
            or not isinstance(state["acceptance_evidence"], bool)
            or not isinstance(state["informational_only"], bool)
            or state["acceptance_evidence"] == state["informational_only"]
        ):
            raise ValueError("benchmark measurement-state definition is invalid")
        by_state[state_id] = state
    if set(by_state) != _BENCHMARK_MEASUREMENT_STATES:
        raise ValueError("benchmark registry must freeze all measurement states")
    if by_state["filesystem_cold_diagnostic"]["acceptance_evidence"]:
        raise ValueError("filesystem-cold diagnostics are never acceptance evidence")

    query_cases = _paired_query_cases(Path(manifest))
    cases = registry["cases"]
    if not isinstance(cases, list) or not cases:
        raise ValueError("benchmark registry requires cases")
    by_case: dict[tuple[str, str], Mapping[str, Any]] = {}
    protected_ids: list[str] = []
    mapped_query_ids: list[str] = []
    for case in cases:
        if not isinstance(case, dict) or set(case) != _BENCHMARK_CASE_KEYS:
            raise ValueError("benchmark case contract is not closed")
        operation_id = case["operation_id"]
        frozen_case_id = case["case_id"]
        identity = (operation_id, frozen_case_id)
        tiers = case["tiers"]
        if (
            not isinstance(operation_id, str)
            or not operation_id
            or not isinstance(frozen_case_id, str)
            or not frozen_case_id
            or identity in by_case
            or not isinstance(tiers, list)
            or not tiers
            or len(set(tiers)) != len(tiers)
            or not set(tiers) <= set(contract["tiers"])
            or case["planner_enabled"] is not False
        ):
            raise ValueError("benchmark case identity or tier projection is invalid")
        query_case_id = case["query_case_id"]
        is_retrieval = operation_id in {"query", "explore"}
        if is_retrieval:
            if query_case_id != frozen_case_id or query_case_id not in query_cases:
                raise ValueError("benchmark query-case mapping is not closed")
            mapped_query_ids.append(query_case_id)
        elif query_case_id is not None or frozen_case_id != "default":
            raise ValueError("non-retrieval benchmark cases must use default identity")
        protected_operation_id = case["protected_operation_id"]
        if protected_operation_id is not None:
            if not isinstance(protected_operation_id, str) or not protected_operation_id:
                raise ValueError("protected operation identity is invalid")
            protected_ids.append(protected_operation_id)

        measurements = case["measurements"]
        if not isinstance(measurements, list) or not measurements:
            raise ValueError("benchmark case requires measurement definitions")
        seen_measurements: set[str] = set()
        for measurement in measurements:
            if (
                not isinstance(measurement, dict)
                or set(measurement) != _BENCHMARK_MEASUREMENT_KEYS
            ):
                raise ValueError("benchmark measurement contract is not closed")
            state_id = measurement["state"]
            count = measurement["sample_count"]
            if (
                state_id not in by_state
                or state_id in seen_measurements
                or not isinstance(count, int)
                or isinstance(count, bool)
                or count < 1
                or measurement["baseline_outcome"] not in {"supported", "unsupported"}
            ):
                raise ValueError("benchmark case measurement is invalid")
            seen_measurements.add(state_id)
        by_case[identity] = case

    if protected_ids != contract.get("protected_small_entry_comparable"):
        raise ValueError("protected operation registry differs from workload contract")
    if mapped_query_ids != list(query_cases):
        raise ValueError("benchmark registry must map every approved query case once")

    selected = by_case.get((operation, case_id))
    if selected is None or tier not in selected["tiers"]:
        raise ValueError("operation/case is not registered for this workload tier")
    measurements = {
        value["state"]: value for value in selected["measurements"]
    }
    measurement = measurements.get(measurement_state)
    if measurement is None:
        raise ValueError("measurement state is not registered for this operation/case")
    if sample_count != measurement["sample_count"]:
        raise ValueError(
            "sample count must exactly match the frozen operation/case/state registry"
        )
    query_case_id = selected["query_case_id"]
    execution_case = (
        str(query_cases[query_case_id]["query_token"])
        if query_case_id is not None
        else "default"
    )
    return {
        "case": selected,
        "measurement": measurement,
        "execution_case": execution_case,
    }


def _benchmark_repo_state_sha256(repo: Path, operation: str) -> str:
    digest = hashlib.sha256()
    digest.update(_repository_fingerprint(repo).encode("ascii"))
    digest.update(b"\0")
    paths = [
        path
        for path in (repo / ".gitignore", repo / ".context-search.toml")
        if path.is_file()
    ]
    if operation != "full_build":
        internal = repo / ".context-search"
        if internal.is_dir():
            paths.extend(path for path in internal.rglob("*") if path.is_file())
    for path in sorted(paths, key=lambda value: value.relative_to(repo).as_posix()):
        relative = path.relative_to(repo).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        with path.open("rb") as source:
            while chunk := source.read(1024 * 1024):
                digest.update(chunk)
        digest.update(b"\0")
    return digest.hexdigest()


def _checkpoint_stable_environment(
    environment: Mapping[str, Any],
) -> dict[str, Any]:
    return {key: environment[key] for key in _CHECKPOINT_STABLE_ENVIRONMENT_KEYS}


def _benchmark_checkpoint_metadata(
    *,
    repo: Path,
    manifest: Path,
    tier: str,
    operation: str,
    case_id: str,
    sample_count: int,
    measurement_state: str,
    mode: str,
    execution_case: str,
    supported: bool,
    environment: Mapping[str, Any],
) -> dict[str, Any]:
    commit, tree, dirty = _git_identity()
    if dirty:
        raise ValueError("benchmark checkpoint refuses dirty production source")
    query_cases = manifest.resolve().with_name("query_cases.json")
    identity = {
        "implementation_commit": commit,
        "production_tree": tree,
        "harness_sha256": _sha256_path(__file__),
        "workload_sha256": _sha256_path(manifest),
        "query_cases_sha256": _sha256_path(query_cases),
        "repository_state_sha256": _benchmark_repo_state_sha256(repo, operation),
        "stable_environment_sha256": hashlib.sha256(
            canonical_json(_checkpoint_stable_environment(environment)).encode("utf-8")
        ).hexdigest(),
    }
    request = {
        "tier": tier,
        "operation_id": operation,
        "case_id": case_id,
        "sample_count": sample_count,
        "measurement_state": measurement_state,
        "mode": mode,
        "execution_case_sha256": hashlib.sha256(
            execution_case.encode("utf-8")
        ).hexdigest(),
        "outcome": "supported" if supported else "unsupported",
    }
    return {
        "schema_version": 1,
        "checkpoint_kind": "p6-benchmark-run-v1",
        "identity": identity,
        "request": request,
        "environment": dict(environment),
    }


def _checkpoint_identity_sha256(metadata: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        canonical_json(
            {
                "identity": metadata["identity"],
                "request": metadata["request"],
            }
        ).encode("utf-8")
    ).hexdigest()


def _validate_checkpoint_sample(
    value: Any,
    *,
    index: int,
    identity_sha256: str,
    sample_schema: Mapping[str, Any],
) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {
        "schema_version",
        "checkpoint_kind",
        "checkpoint_identity_sha256",
        "sample_index",
        "sample",
    }:
        raise ValueError("benchmark checkpoint sample is not closed")
    if (
        value["schema_version"] != 1
        or value["checkpoint_kind"] != "p6-benchmark-sample-v1"
        or value["checkpoint_identity_sha256"] != identity_sha256
        or value["sample_index"] != index
    ):
        raise ValueError("benchmark checkpoint sample identity differs")
    sample = value["sample"]
    errors = sorted(
        Draft202012Validator(sample_schema).iter_errors(sample),
        key=lambda item: tuple(str(part) for part in item.absolute_path),
    )
    if errors:
        raise ValueError(f"invalid benchmark checkpoint sample: {errors[0].message}")
    if sample["sample_id"] != f"sample-{index:03d}":
        raise ValueError("benchmark checkpoint sample ID differs")
    _assert_finite(sample)
    validate_private_payload(sample)
    _validate_benchmark_sample_semantics(sample)
    return dict(sample)


def _prepare_benchmark_checkpoints(
    checkpoint_dir: Path,
    *,
    resume: bool,
    expected: Mapping[str, Any],
    sample_schema: Mapping[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    run_path = checkpoint_dir / "run.json"
    if resume:
        if not checkpoint_dir.is_dir() or not run_path.is_file():
            raise ValueError("resume requires an existing benchmark checkpoint")
        actual = _load_json(run_path)
        if not isinstance(actual, dict) or set(actual) != set(expected):
            raise ValueError("benchmark checkpoint metadata is not closed")
        if (
            actual.get("schema_version") != 1
            or actual.get("checkpoint_kind") != "p6-benchmark-run-v1"
            or actual.get("identity") != expected["identity"]
            or actual.get("request") != expected["request"]
        ):
            raise ValueError("benchmark checkpoint identity differs")
        if set(actual.get("environment", {})) != set(expected["environment"]):
            raise ValueError("benchmark checkpoint environment is not closed")
        metadata = actual
    else:
        if os.path.lexists(checkpoint_dir):
            raise FileExistsError(checkpoint_dir)
        checkpoint_dir.mkdir(parents=True)
        _write_new_json_atomic(run_path, expected)
        metadata = dict(expected)

    visible = [path for path in checkpoint_dir.iterdir() if not path.name.startswith(".")]
    unknown = [
        path.name
        for path in visible
        if path.name != "run.json"
        and re.fullmatch(r"sample-(\d{3})\.json", path.name) is None
    ]
    if unknown:
        raise ValueError(f"unknown benchmark checkpoint files: {sorted(unknown)}")
    sample_paths = sorted(
        path
        for path in visible
        if re.fullmatch(r"sample-(\d{3})\.json", path.name) is not None
    )
    if len(sample_paths) > int(expected["request"]["sample_count"]):
        raise ValueError("benchmark checkpoint has too many samples")
    identity_sha256 = _checkpoint_identity_sha256(metadata)
    samples = []
    for index, path in enumerate(sample_paths, start=1):
        if path.name != f"sample-{index:03d}.json":
            raise ValueError("benchmark checkpoint samples are not contiguous")
        samples.append(
            _validate_checkpoint_sample(
                _load_json(path),
                index=index,
                identity_sha256=identity_sha256,
                sample_schema=sample_schema,
            )
        )
    return metadata, samples


def _write_benchmark_sample_checkpoint(
    checkpoint_dir: Path,
    *,
    metadata: Mapping[str, Any],
    index: int,
    sample: Mapping[str, Any],
) -> None:
    _write_new_json_atomic(
        checkpoint_dir / f"sample-{index:03d}.json",
        {
            "schema_version": 1,
            "checkpoint_kind": "p6-benchmark-sample-v1",
            "checkpoint_identity_sha256": _checkpoint_identity_sha256(metadata),
            "sample_index": index,
            "sample": sample,
        },
    )


def _benchmark_progress(message: str) -> None:
    print(f"p6-progress: {message}", file=sys.stderr, flush=True)


def run_benchmark(
    repo: str | Path,
    manifest: str | Path,
    *,
    operation: str,
    case_id: str,
    sample_count: int,
    measurement_state: str,
    mode: str,
    checkpoint_dir: str | Path | None = None,
    resume: bool = False,
) -> dict[str, Any]:
    repo_path = Path(repo).resolve()
    manifest_path = Path(manifest).resolve()
    if not repo_path.is_dir() or sample_count < 1:
        raise ValueError("benchmark repository and positive sample count are required")
    if resume and checkpoint_dir is None:
        raise ValueError("resume requires a checkpoint directory")
    contract = _load_json(manifest_path)
    tier = _tier_for_repo(repo_path, contract)
    request = _benchmark_request(
        contract,
        manifest_path,
        tier=tier,
        operation=operation,
        case_id=case_id,
        sample_count=sample_count,
        measurement_state=measurement_state,
    )
    fingerprint = _repository_fingerprint(repo_path)
    expected_fingerprint = contract.get("expected_fingerprints", {}).get(tier)
    if fingerprint != expected_fingerprint:
        raise ValueError("generated repository fingerprint differs from workload contract")
    supported = _measurement_is_supported(operation, measurement_state, mode)
    if mode == "baseline" and supported != (
        request["measurement"]["baseline_outcome"] == "supported"
    ):
        raise ValueError("baseline product support differs from the frozen registry")
    unsupported = not supported
    current_environment = _environment()

    schema = _load_json(SCHEMA_ROOT / "benchmark-report-v1.json")
    sample_schema = schema["properties"]["samples"]["items"]
    timing_names = sample_schema["properties"]["stage_timings_ms"]["required"]
    counter_names = sample_schema["properties"]["work"]["required"]
    source_paths = _generated_source_paths(repo_path)
    source_bytes = sum(path.stat().st_size for path in source_paths)
    source_files = len(source_paths)
    samples: list[dict[str, Any]] = []
    checkpoint_path = Path(checkpoint_dir).resolve() if checkpoint_dir else None
    checkpoint_metadata: dict[str, Any] | None = None
    if checkpoint_path is not None and supported:
        expected_checkpoint = _benchmark_checkpoint_metadata(
            repo=repo_path,
            manifest=manifest_path,
            tier=tier,
            operation=operation,
            case_id=case_id,
            sample_count=sample_count,
            measurement_state=measurement_state,
            mode=mode,
            execution_case=request["execution_case"],
            supported=supported,
            environment=current_environment,
        )
        checkpoint_metadata, samples = _prepare_benchmark_checkpoints(
            checkpoint_path,
            resume=resume,
            expected=expected_checkpoint,
            sample_schema=sample_schema,
        )
        if resume:
            _benchmark_progress(
                f"resuming with {len(samples)}/{sample_count} completed samples"
            )
    elif resume:
        raise ValueError("unsupported benchmark measurements cannot resume")
    environment_facts = dict(
        checkpoint_metadata["environment"]
        if checkpoint_metadata is not None
        else current_environment
    )
    environment_facts["background_cpu_percent"] = max(
        environment_facts["background_cpu_percent"],
        current_environment["background_cpu_percent"],
    )
    with tempfile.TemporaryDirectory(
        prefix="p6-measurements-",
        dir=repo_path.parent,
    ) as raw_sample_parent:
        sample_parent = Path(raw_sample_parent)
        ready_repo: Path | None = None
        if supported and len(samples) < sample_count and operation != "full_build":
            ready_repo = _clone_operation_repo(
                repo_path,
                operation,
                sample_parent,
            )
            if not (ready_repo / ".context-search").exists():
                _run_measurement_worker("full_build", ready_repo, "default")
        read_only_operation = operation in {
            "stats",
            "status_quick",
            "status_verified",
            "query",
            "explore",
        }
        resident_context = (
            _ResidentMeasurementSession(
                operation,
                ready_repo,
                request["execution_case"],
            )
            if supported
            and measurement_state == "mcp_resident_warm"
            and ready_repo is not None
            else nullcontext()
        )
        with resident_context as resident_session:
            for index in range(len(samples), sample_count if supported else 0):
                sample_number = index + 1
                sample_repo = (
                    ready_repo
                    if read_only_operation
                    else _clone_operation_repo(
                        ready_repo or repo_path,
                        operation,
                        sample_parent,
                    )
                )
                if sample_repo is None:
                    raise AssertionError("supported benchmark has no sample repository")
                sample_index = sample_repo / ".context-search"
                if resident_session is None:
                    # One identical, unmeasured worker warms filesystem/module state.
                    _benchmark_progress(
                        f"sample {sample_number}/{sample_count} warmup started"
                    )
                    if operation == "refresh_one_file":
                        _prepare_one_file_refresh(
                            sample_repo,
                            f"sample-{sample_number:03d}-warmup",
                        )
                    _run_measurement_worker(
                        operation,
                        sample_repo,
                        request["execution_case"],
                    )
                    if operation == "full_build" and sample_index.exists():
                        shutil.rmtree(sample_index)
                    if operation == "refresh_one_file":
                        _prepare_one_file_refresh(
                            sample_repo,
                            f"sample-{sample_number:03d}-measured",
                        )
                    _benchmark_progress(
                        f"sample {sample_number}/{sample_count} measured operation started"
                    )
                    measured = _run_measurement_worker(
                        operation,
                        sample_repo,
                        request["execution_case"],
                    )
                else:
                    _benchmark_progress(
                        f"sample {sample_number}/{sample_count} resident operation started"
                    )
                    measured = resident_session.measure()
                _benchmark_progress(f"sample {sample_number}/{sample_count} measured")
                disk = _disk_components(sample_repo)

                duration_ms = float(measured["duration_ms"])
                timings = {name: 0.0 for name in timing_names}
                timings["end_to_end"] = duration_ms
                attribution = measured.get("attribution")
                if attribution is not None:
                    for timing_name, value in attribution.get(
                        "stage_timings_ms", {}
                    ).items():
                        timings[timing_name] += float(value)
                    trace_timing_names = {
                        "query_understanding": "repo_profile",
                        "semantic_recall": "semantic",
                        "lexical_recall": "lexical",
                        "path_symbol_recall": "path_symbol",
                        "direct_text_recall": "direct_text",
                        "signal_recall": "signal",
                        "planner_hint_recall": "signal",
                        "anchor_expansion": "graph",
                        "relation_expansion": "graph",
                    }
                    for stage in attribution["stages"]:
                        timing_name = trace_timing_names.get(stage["name"])
                        if timing_name is not None:
                            timings[timing_name] += float(stage["duration_ms"])
                work = {name: 0 for name in counter_names}
                if attribution is not None:
                    work.update(attribution.get("work", {}))
                work["inventory_entries"] = source_files
                work["inventory_dirs"] = sum(
                    path.is_dir()
                    for path in (sample_repo / "generated").rglob("*")
                ) + 1
                if operation in {
                    "full_build",
                    "authoritative_noop",
                } and not unsupported:
                    work["source_bytes_read"] = max(
                        int(work["source_bytes_read"]), source_bytes
                    )
                    work["source_bytes_hashed"] = source_bytes
                work.update(_storage_work_counters(sample_repo))
                sample = {
                    "sample_id": f"sample-{sample_number:03d}",
                    "pair_id": None,
                    "duration_ms": duration_ms,
                    "stage_timings_ms": timings,
                    "work": work,
                    "rss": measured["rss"],
                    "disk": disk,
                }
                samples.append(sample)
                if checkpoint_path is not None and checkpoint_metadata is not None:
                    _write_benchmark_sample_checkpoint(
                        checkpoint_path,
                        metadata=checkpoint_metadata,
                        index=sample_number,
                        sample=sample,
                    )
                    _benchmark_progress(
                        f"sample {sample_number}/{sample_count} checkpoint complete"
                    )
                if not read_only_operation:
                    shutil.rmtree(sample_repo.parent)
    if checkpoint_metadata is not None:
        current_commit, current_tree, current_dirty = _git_identity()
        current_identity = {
            "implementation_commit": current_commit,
            "production_tree": current_tree,
            "harness_sha256": _sha256_path(__file__),
            "workload_sha256": _sha256_path(manifest_path),
            "query_cases_sha256": _sha256_path(
                manifest_path.with_name("query_cases.json")
            ),
            "repository_state_sha256": _benchmark_repo_state_sha256(
                repo_path, operation
            ),
        }
        frozen_identity = checkpoint_metadata["identity"]
        if any(
            current_identity[key] != frozen_identity[key]
            for key in current_identity
        ) or current_dirty:
            raise ValueError("benchmark checkpoint identity changed during measurement")
        commit = frozen_identity["implementation_commit"]
        tree = frozen_identity["production_tree"]
        dirty = False
        harness_sha256 = frozen_identity["harness_sha256"]
        workload_sha256 = frozen_identity["workload_sha256"]
    else:
        commit, tree, dirty = _git_identity()
        harness_sha256 = _sha256_path(__file__)
        workload_sha256 = _sha256_path(manifest_path)

    durations = sorted(sample["duration_ms"] for sample in samples)
    nearest = (
        durations[math.ceil(0.95 * len(durations)) - 1]
        if durations
        else 0.0
    )
    operation_family = (
        "index" if operation in {"full_build", "authoritative_noop"}
        else "status" if operation.startswith("status") or operation == "stats"
        else "refresh" if operation.startswith("refresh")
        else "explore" if operation.startswith("explore")
        else "query"
    )
    after_environment = _environment()
    environment_facts["swap_after_bytes"] = max(
        environment_facts["swap_after_bytes"],
        after_environment["swap_after_bytes"],
    )
    environment_facts["background_cpu_percent"] = max(
        environment_facts["background_cpu_percent"],
        after_environment["background_cpu_percent"],
    )
    environment_facts["power_state"] = after_environment["power_state"]
    environment_facts["governor_state"] = after_environment["governor_state"]
    calibration = _calibration()
    validity_reasons = []
    if not calibration["valid"]:
        validity_reasons.append("calibration_drift")
    if environment_facts["background_cpu_percent"] > 20.0:
        validity_reasons.append("background_cpu")
    if environment_facts["swap_after_bytes"] > environment_facts["swap_before_bytes"]:
        validity_reasons.append("swap_growth")
    if environment_facts["cpu_count"] < 8:
        validity_reasons.append("host_cpu")
    if environment_facts["memory_bytes"] < 16 * 1024**3:
        validity_reasons.append("host_memory")
    if environment_facts["local_disk_class"] != "ssd":
        validity_reasons.append("disk_class")
    if environment_facts["power_state"] != "external":
        validity_reasons.append("power_state")
    if environment_facts["governor_state"] == "unknown":
        validity_reasons.append("governor_state")
    cv_population = (
        statistics.pstdev(durations) / statistics.fmean(durations)
        if len(durations) > 1 and statistics.fmean(durations) > 0
        else 0.0
    )
    if cv_population > 0.15:
        validity_reasons.append("budget_failed")
    report = {
        "schema_version": 1,
        "report_kind": "benchmark",
        "report_scope": "tier",
        "mode": mode,
        "identity": {
            "implementation_commit": commit,
            "production_tree": tree,
            "harness_sha256": harness_sha256,
            "workload_sha256": workload_sha256,
            "dirty_production_source": dirty,
        },
        "environment": environment_facts,
        "workload": {
            "schema_version": 1,
            "generator_version": contract["generator"]["version"],
            "generator_sha256": contract["generator"]["contract_sha256"],
            "seed": contract["generator"]["seed"],
            "tier": tier,
            "fingerprint_sha256": fingerprint,
        },
        "operation": {
            "operation_id": operation,
            "case_id": case_id,
            "case_family": operation_family,
            "measurement_state": measurement_state,
            "planner_enabled": False,
            "embedding_provider": "hash",
            "embedding_model": "hash-v1",
            "embedding_dimensions": 384,
            "outcome": "unsupported" if unsupported else "supported",
        },
        "calibration": calibration,
        "samples": samples,
        "summary": {
            "sample_count": len(samples),
            "median_ms": statistics.median(durations) if durations else 0.0,
            "p50_ms": statistics.median(durations) if durations else 0.0,
            "p95_ms": nearest,
            "max_ms": max(durations) if durations else 0.0,
            "cv_population": cv_population,
            "units": {
                "duration": "ms",
                "bytes": "bytes",
                "rss": "bytes",
                "throughput": "MiB/s",
                "ratio": "ratio",
                "count": "count",
            },
        },
        "validity": {
            "valid": not validity_reasons,
            "reasons": validity_reasons,
            "child_processes": 0,
        },
    }
    validate_report_data(report, "benchmark-report-v1.json")
    return report


def _benchmark_set_requests(
    contract: Mapping[str, Any],
    tier: str,
    operation_set: str,
) -> list[dict[str, Any]]:
    expected_set = {
        "smoke": "all-smoke",
        "large": "all-large",
        "scale-5k": "all-scale",
        "scale-10k": "all-scale",
        "stress": "capacity-informational",
    }.get(tier)
    if operation_set != expected_set:
        raise ValueError("benchmark operation set does not match repository tier")
    requests = []
    for case in contract["benchmark_registry"]["cases"]:
        if tier not in case["tiers"]:
            continue
        for measurement in case["measurements"]:
            requests.append(
                {
                    "operation": case["operation_id"],
                    "case_id": case["case_id"],
                    "sample_count": measurement["sample_count"],
                    "measurement_state": measurement["state"],
                }
            )
    if not requests:
        raise ValueError("benchmark operation set is empty")
    return requests


def run_benchmark_set(
    repo: str | Path,
    manifest: str | Path,
    *,
    operation_set: str,
    mode: str,
    checkpoint_dir: str | Path,
    resume: bool,
) -> dict[str, Any]:
    repo_path = Path(repo).resolve()
    manifest_path = Path(manifest).resolve()
    contract = _load_json(manifest_path)
    tier = _tier_for_repo(repo_path, contract)
    requests = _benchmark_set_requests(contract, tier, operation_set)
    checkpoint_root = Path(checkpoint_dir).resolve()
    ready_repo = checkpoint_root / "shared-ready"
    if resume:
        if not (ready_repo / ".context-search").is_dir():
            raise ValueError("benchmark resume requires its frozen shared ready root")
    else:
        if os.path.lexists(ready_repo):
            raise FileExistsError(ready_repo)
        checkpoint_root.mkdir(parents=True, exist_ok=True)
        shutil.copytree(repo_path, ready_repo)
        if not (ready_repo / ".context-search").is_dir():
            _benchmark_progress("shared ready-repository setup started")
            _run_measurement_worker("full_build", ready_repo, "default")
    if _repository_fingerprint(ready_repo) != _repository_fingerprint(repo_path):
        raise ValueError("shared benchmark setup changed generated content")
    reports = []
    for index, request in enumerate(requests, start=1):
        operation = request["operation"]
        case_id = request["case_id"]
        state = request["measurement_state"]
        _benchmark_progress(
            f"case {index}/{len(requests)} {operation}/{case_id}/{state} started"
        )
        case_checkpoint = (
            checkpoint_root / f"{index:03d}-{operation}-{case_id}-{state}"
        )
        reports.append(
            run_benchmark(
                repo_path if operation == "full_build" else ready_repo,
                manifest_path,
                operation=operation,
                case_id=case_id,
                sample_count=request["sample_count"],
                measurement_state=state,
                mode=mode,
                checkpoint_dir=case_checkpoint,
                resume=(
                    resume
                    and _measurement_is_supported(operation, state, mode)
                    and (case_checkpoint / "run.json").is_file()
                ),
            )
        )
    with tempfile.TemporaryDirectory(
        prefix="p6-benchmark-set-",
        dir=repo_path.parent,
    ) as raw:
        raw_root = Path(raw)
        paths = []
        for index, report in enumerate(reports, start=1):
            path = raw_root / f"case-{index:03d}.json"
            _write_new_json(path, report)
            paths.append(path)
        return assemble_reports(
            "performance",
            paths,
            mode,
            manifest=manifest_path,
        )


def parse_junit(path: str | Path) -> dict[str, Any]:
    raw = Path(path).read_bytes()
    root = ET.fromstring(raw)
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    cases = [case for suite in suites for case in suite.findall("testcase")]
    skip_nodes: list[str] = []
    xfails = 0
    failures = errors = 0
    for case in cases:
        classname = case.attrib.get("classname", "")
        test_path = (
            classname
            if "/" in classname or classname.endswith(".py")
            else classname.replace(".", "/") + ".py"
        )
        node = f"{test_path}::{case.attrib.get('name', '')}"
        failures += len(case.findall("failure"))
        errors += len(case.findall("error"))
        marker = case.find("skipped")
        if marker is None:
            continue
        marker_text = " ".join(marker.attrib.values()).lower()
        if "xfail" in marker_text:
            xfails += 1
        else:
            skip_nodes.append(node)
    return {
        "sha256": hashlib.sha256(raw).hexdigest(),
        "passed": len(cases) - len(skip_nodes) - xfails - failures - errors,
        "skipped": len(skip_nodes),
        "xfail": xfails,
        "errors": errors,
        "failed": failures,
        "skip_node_ids": sorted(skip_nodes),
    }


def assemble_matrix_report(
    input_dir: str | Path,
    *,
    evidence_id: str,
) -> dict[str, Any]:
    root = Path(input_dir)
    if not root.is_dir():
        raise ValueError("matrix input directory does not exist")
    summaries = sorted(root.rglob("matrix-summary-v1.json"))
    if len(summaries) != 12:
        raise ValueError("matrix assembly requires exactly 12 cell summaries")
    cells = []
    common_keys = (
        "implementation_commit",
        "production_tree",
        "workflow_sha256",
        "dependency_lock_sha256",
        "run",
    )
    common: dict[str, Any] | None = None
    for summary_path in summaries:
        summary = _load_json(summary_path)
        validate_report_data(summary, "matrix-summary-v1.json")
        junit_path = summary_path.with_name("junit.xml")
        if not junit_path.is_file() or _sha256_path(junit_path) != summary[
            "junit_sha256"
        ]:
            raise ValueError("matrix JUnit identity differs from its cell summary")
        projected = {key: summary[key] for key in common_keys}
        if common is None:
            common = projected
        elif canonical_json(projected) != canonical_json(common):
            raise ValueError("matrix cells contain mixed run or implementation identity")
        cells.append(
            {
                "os": summary["os"],
                "architecture": summary["architecture"],
                "python_version": summary["python_version"],
                "tests": summary["tests"],
                "junit_sha256": summary["junit_sha256"],
            }
        )
    if common is None:
        raise AssertionError("matrix common identity is absent")
    expected_cells = {
        (os_name, python_version)
        for os_name in ("ubuntu-latest", "macos-latest", "windows-latest")
        for python_version in ("3.11", "3.12", "3.13", "3.14")
    }
    actual_cells = {(cell["os"], cell["python_version"]) for cell in cells}
    if actual_cells != expected_cells or len(actual_cells) != len(cells):
        raise ValueError("matrix cells do not form the exact OS/Python cross product")
    if common["run"]["evidence_id"] != evidence_id or evidence_id != (
        f"p6-acceptance-{common['implementation_commit']}"
    ):
        raise ValueError("matrix evidence ID does not bind the implementation commit")
    if common["workflow_sha256"] != _sha256_path(
        ROOT / ".github" / "workflows" / "p6-functional-matrix.yml"
    ):
        raise ValueError("matrix workflow identity differs from the local commit")
    if common["dependency_lock_sha256"] != _sha256_path(ROOT / "uv.lock"):
        raise ValueError("matrix dependency lock differs from the local commit")
    report = {
        "schema_version": 1,
        "report_kind": "matrix",
        "implementation_commit": common["implementation_commit"],
        "production_tree": common["production_tree"],
        "workflow_sha256": common["workflow_sha256"],
        "dependency_lock_sha256": common["dependency_lock_sha256"],
        "run": common["run"],
        "cells": sorted(
            cells,
            key=lambda cell: (cell["os"], cell["python_version"]),
        ),
        "conclusion": "success",
    }
    validate_report_data(report, "matrix-report-v1.json")
    return report


def parse_hash_manifest(path: str | Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        digest, separator, raw_path = line.partition("  ")
        if not separator or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError("invalid SHA-256 evidence manifest")
        candidate = Path(raw_path)
        if candidate.is_absolute() or ".." in candidate.parts:
            raise ValueError("evidence manifest paths must be allowlisted relative paths")
        normalized = candidate.as_posix()
        if normalized in values:
            raise ValueError("duplicate evidence manifest path")
        values[normalized] = digest
    return values


def _require_exact_keys(
    value: Any,
    expected: frozenset[str],
    label: str,
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != expected:
        raise ValueError(f"{label} fields do not match the frozen contract")
    return value


def _validate_entry_quality(path: Path, name: str) -> None:
    value = _load_json(path)
    _assert_finite(value)
    report = _require_exact_keys(value, _ENTRY_QUALITY_TOP_LEVEL_KEYS, name)
    profile, expected_count, required_case_keys, optional_case_keys = (
        _ENTRY_QUALITY_PROFILES[name]
    )
    if report["schema_version"] != 2 or report["profile"] != profile:
        raise ValueError(f"{name} identity does not match the frozen contract")
    aggregate = _require_exact_keys(
        report["aggregate"], _ENTRY_QUALITY_AGGREGATE_KEYS, f"{name} aggregate"
    )
    expected_counts = {
        "total": expected_count,
        "selected": expected_count,
        "attempted": expected_count,
        "executed": expected_count,
        "passed": expected_count,
        "failed": 0,
        "skipped": 0,
        "known_gaps": 0,
        "informational": 0,
        "errors": 0,
    }
    if any(aggregate[key] != count for key, count in expected_counts.items()):
        raise ValueError(f"{name} aggregate counts do not match the frozen contract")
    cases = report["cases"]
    if not isinstance(cases, list) or len(cases) != expected_count:
        raise ValueError(f"{name} case count does not match the frozen contract")
    identities: set[tuple[str, str]] = set()
    expected_case_keys = _ENTRY_QUALITY_COMMON_CASE_KEYS | required_case_keys
    for case in cases:
        if not isinstance(case, Mapping) or not (
            expected_case_keys <= set(case)
            and set(case) <= expected_case_keys | optional_case_keys
        ):
            raise ValueError(f"{name} case fields do not match the frozen contract")
        closed_case = case
        identity = (closed_case["repo_key"], closed_case["case_id"])
        if (
            not all(isinstance(part, str) and part for part in identity)
            or identity in identities
            or closed_case["status"] != "pass"
            or closed_case["attempted"] is not True
            or closed_case["failures"] != []
        ):
            raise ValueError(f"{name} cases are inconsistent")
        identities.add(identity)


def _validate_pinned_real(path_a: Path, path_b: Path) -> None:
    raw_a = path_a.read_bytes()
    raw_b = path_b.read_bytes()
    if raw_a != raw_b:
        raise ValueError("pinned-real reports must be byte-identical")
    value_a = _load_json(path_a)
    value_b = _load_json(path_b)
    if value_a != value_b:
        raise ValueError("pinned-real identities disagree")
    _assert_finite(value_a)
    report = _require_exact_keys(
        value_a, _PINNED_REAL_TOP_LEVEL_KEYS, "pinned-real report"
    )
    if report["schema_version"] != 1 or report["profile"] != "p5_real_language_graphs":
        raise ValueError("pinned-real profile does not match the frozen contract")
    for key in (
        "fixture_sha256",
        "input_manifest_sha256",
        "profile_definition_sha256",
        "effective_config_hash",
    ):
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", report[key]):
            raise ValueError(f"pinned-real {key} is invalid")
    aggregate = _require_exact_keys(
        report["aggregate"],
        frozenset({"selected", "executed", "passed", "failed", "skipped", "errors"}),
        "pinned-real aggregate",
    )
    if aggregate != {
        "selected": 2,
        "executed": 2,
        "passed": 2,
        "failed": 0,
        "skipped": 0,
        "errors": 0,
    }:
        raise ValueError("pinned-real aggregate does not match the frozen contract")
    cases = report["cases"]
    if not isinstance(cases, list) or len(cases) != 2:
        raise ValueError("pinned-real case count does not match the frozen contract")
    identities: set[tuple[str, str]] = set()
    for case in cases:
        closed_case = _require_exact_keys(case, _PINNED_REAL_CASE_KEYS, "pinned-real case")
        identity = (closed_case["repo_key"], closed_case["case_id"])
        if (
            not all(isinstance(part, str) and part for part in identity)
            or identity in identities
            or closed_case["status"] != "pass"
            or closed_case["failures"] != []
        ):
            raise ValueError("pinned-real cases are inconsistent")
        identities.add(identity)


def _installed_versions_for_freeze(lines: Iterable[str]) -> dict[str, str]:
    versions: dict[str, str] = {}
    for line in lines:
        stripped = line.rstrip("\r\n")
        if not stripped or stripped.startswith("#"):
            continue
        if " @ " in stripped:
            raw_name = stripped.split(" @ ", 1)[0]
        elif "==" in stripped:
            raw_name = stripped.split("==", 1)[0]
        else:
            raise ValueError("unsupported dependency line")
        name = _normalize_distribution_name(raw_name)
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError as exc:
            raise ValueError(f"installed version unavailable: {name}") from exc
    return versions


def validate_entry_evidence(
    inputs: Mapping[str, Path],
    *,
    installed_versions: Mapping[str, str] | None = None,
    expected_skip_node_ids: Sequence[str] = FROZEN_ENTRY_SKIP_NODE_IDS,
) -> dict[str, Any]:
    expected_inputs = ENTRY_RAW_EVIDENCE_NAMES | {"entry-evidence-hashes.txt"}
    if set(inputs) != expected_inputs:
        missing = sorted(expected_inputs - set(inputs))
        extra = sorted(set(inputs) - expected_inputs)
        raise ValueError(f"entry evidence input set mismatch: missing={missing}, extra={extra}")

    manifest = parse_hash_manifest(inputs["entry-evidence-hashes.txt"])
    manifest_by_name: dict[str, str] = {}
    for raw_path, digest in manifest.items():
        candidate = Path(raw_path)
        name = candidate.name
        if raw_path not in {name, f".quality/p6-artifacts/{name}"}:
            raise ValueError("evidence manifest path is outside the frozen allowlist")
        if name not in ENTRY_RAW_EVIDENCE_NAMES or name in manifest_by_name:
            raise ValueError("evidence manifest set does not match the frozen allowlist")
        manifest_by_name[name] = digest
    if set(manifest_by_name) != ENTRY_RAW_EVIDENCE_NAMES:
        raise ValueError("evidence manifest set does not match the frozen allowlist")
    for name in ENTRY_RAW_EVIDENCE_NAMES:
        if _sha256_path(inputs[name]) != manifest_by_name[name]:
            raise ValueError(f"entry evidence digest mismatch: {name}")

    junit = parse_junit(inputs["entry-full.xml"])
    frozen_skips = sorted(expected_skip_node_ids)
    if (
        junit["passed"] != 2625
        or junit["skipped"] != 9
        or junit["xfail"] != 0
        or junit["errors"] != 0
        or junit["failed"] != 0
        or junit["skip_node_ids"] != frozen_skips
        or len(set(frozen_skips)) != 9
    ):
        raise ValueError("entry JUnit does not match the frozen 2625/9 contract")
    junit.pop("failed")

    dependency_lines = inputs["entry-dependencies.txt"].read_text(
        encoding="utf-8"
    ).splitlines()
    resolved_versions = (
        dict(installed_versions)
        if installed_versions is not None
        else _installed_versions_for_freeze(dependency_lines)
    )
    dependency_projection = normalize_freeze_lines(
        dependency_lines, installed_versions=resolved_versions
    )
    validate_private_payload(dependency_projection)

    runtime = _require_exact_keys(
        _load_json(inputs["entry-runtime.json"]),
        frozenset({"python", "sqlite", "platform", "machine"}),
        "entry runtime",
    )
    if not all(isinstance(value, str) and value for value in runtime.values()):
        raise ValueError("entry runtime fields must be non-empty strings")
    validate_private_payload(runtime)

    for name in _ENTRY_QUALITY_PROFILES:
        _validate_entry_quality(inputs[name], name)
    _validate_pinned_real(inputs["entry-real-a.json"], inputs["entry-real-b.json"])

    return {
        "junit": junit,
        "dependency_projection": dependency_projection,
        "dependency_sha256": hashlib.sha256(
            canonical_json(dependency_projection).encode("utf-8")
        ).hexdigest(),
        "runtime_sha256": _sha256_path(inputs["entry-runtime.json"]),
        "quality": {
            "p5": _sha256_path(inputs["entry-p5.json"]),
            "p4": _sha256_path(inputs["entry-p4.json"]),
            "p2": _sha256_path(inputs["entry-p2.json"]),
            "ci": _sha256_path(inputs["entry-ci.json"]),
            "pinned_real_a": _sha256_path(inputs["entry-real-a.json"]),
            "pinned_real_b": _sha256_path(inputs["entry-real-b.json"]),
            "pinned_real_byte_identical": True,
        },
    }


def validate_performance_registry_coverage(
    report: Mapping[str, Any],
    manifest: str | Path,
) -> None:
    validate_report_data(report, "benchmark-report-v1.json")
    if report["report_scope"] != "performance":
        raise ValueError("registry coverage requires a performance report")
    manifest_path = Path(manifest)
    contract = _load_json(manifest_path)
    if report["identity"]["workload_sha256"] != _sha256_path(manifest_path):
        raise ValueError("performance workload identity differs from the manifest")

    actual = {
        (
            case["workload"]["tier"],
            case["operation"]["operation_id"],
            case["operation"]["case_id"],
            case["operation"]["measurement_state"],
        ): case
        for case in report["case_reports"]
    }
    observed_tiers = {key[0] for key in actual}
    publication_tiers = {"smoke", "large", "scale-5k", "scale-10k"}
    singleton_tiers = publication_tiers | {"stress"}
    if not observed_tiers or not (
        len(observed_tiers) == 1 and observed_tiers <= singleton_tiers
    ) and observed_tiers != publication_tiers:
        raise ValueError(
            "performance report must cover one complete publication tier or all tiers"
        )
    if report["mode"] == "final" and observed_tiers == publication_tiers:
        if "churn" not in report:
            raise ValueError("complete final performance report requires churn")
    elif "churn" in report:
        raise ValueError("churn belongs only to complete final performance")

    expected: dict[tuple[str, str, str, str], tuple[int, str]] = {}
    registry = contract.get("benchmark_registry", {})
    for case in registry.get("cases", []):
        for tier in case.get("tiers", []):
            if tier not in observed_tiers:
                continue
            for measurement in case.get("measurements", []):
                key = (
                    tier,
                    case["operation_id"],
                    case["case_id"],
                    measurement["state"],
                )
                expected[key] = (
                    measurement["sample_count"],
                    measurement["baseline_outcome"],
                )
    if set(actual) != set(expected):
        missing = sorted(set(expected) - set(actual))
        extra = sorted(set(actual) - set(expected))
        raise ValueError(
            f"performance registry coverage mismatch: missing={missing}, extra={extra}"
        )

    fingerprints = contract.get("expected_fingerprints", {})
    for key, case in actual.items():
        expected_samples, baseline_outcome = expected[key]
        tier = key[0]
        if case["workload"]["fingerprint_sha256"] != fingerprints.get(tier):
            raise ValueError("performance repository fingerprint differs from manifest")
        outcome = case["operation"]["outcome"]
        if report["mode"] == "baseline" and outcome != baseline_outcome:
            raise ValueError("baseline outcome differs from benchmark registry")
        actual_samples = case["summary"]["sample_count"]
        required_samples = expected_samples if outcome == "supported" else 0
        if actual_samples != required_samples:
            raise ValueError("performance sample count differs from benchmark registry")


def assemble_quality_report(inputs: Sequence[str | Path]) -> dict[str, Any]:
    paths = [Path(path) for path in inputs]
    by_name = {path.name: path for path in paths}
    expected_names = {
        "final-p5.json",
        "final-p4.json",
        "final-p2.json",
        "final-ci.json",
        "final-real-a.json",
        "final-real-b.json",
        "final-full.xml",
        *(f"tdd-task-{task}.json" for task in range(1, 11)),
    }
    if len(by_name) != len(paths) or set(by_name) != expected_names:
        missing = sorted(expected_names - set(by_name))
        extra = sorted(set(by_name) - expected_names)
        raise ValueError(
            f"quality evidence input set mismatch: missing={missing}, extra={extra}"
        )

    profile_inputs = {
        "final-p5.json": "entry-p5.json",
        "final-p4.json": "entry-p4.json",
        "final-p2.json": "entry-p2.json",
        "final-ci.json": "entry-ci.json",
    }
    profiles: dict[str, Any] = {}
    for final_name, contract_name in profile_inputs.items():
        path = by_name[final_name]
        _validate_entry_quality(path, contract_name)
        value = _load_json(path)
        profile_name, expected_count, _, _ = _ENTRY_QUALITY_PROFILES[contract_name]
        aggregate = value["aggregate"]
        if aggregate["selected"] != expected_count or aggregate["passed"] != expected_count:
            raise ValueError("quality profile aggregate differs from the frozen contract")
        profiles[profile_name] = {
            "passed": aggregate["passed"],
            "selected": aggregate["selected"],
            "trace_coverage": 1,
        }

    _validate_pinned_real(
        by_name["final-real-a.json"], by_name["final-real-b.json"]
    )
    profiles["pinned_real"] = {
        "passed": 2,
        "selected": 2,
        "byte_identical": True,
    }

    junit = parse_junit(by_name["final-full.xml"])
    frozen_skips = sorted(FROZEN_ENTRY_SKIP_NODE_IDS)
    if (
        junit["passed"] < 2625
        or junit["skipped"] != 9
        or junit["xfail"] != 0
        or junit["errors"] != 0
        or junit["failed"] != 0
        or junit["skip_node_ids"] != frozen_skips
    ):
        raise ValueError("final JUnit does not satisfy the frozen quality contract")

    tdd_summaries = []
    for task in range(1, 11):
        record = _load_json(by_name[f"tdd-task-{task}.json"])
        validate_tdd_record_data(record)
        if record["task"] != task:
            raise ValueError("TDD record task differs from its input identity")
        tdd_summaries.append(
            {
                "task": task,
                "pre_change_commit": record["pre_change_commit"],
                "pre_change_production_tree": record[
                    "pre_change_production_tree"
                ],
                "final_staged_tree": record["final_staged_tree"],
                "test_identity_sha256": record["red"]["test_identity_sha256"],
                "red_failed": len(record["red"]["failed_node_ids"]),
                "green_passed": record["green"]["passed"],
            }
        )

    implementation_commit, production_tree, dirty = _git_identity()
    if dirty:
        raise ValueError("quality assembly requires a clean production tree")
    report = {
        "schema_version": 1,
        "implementation_commit": implementation_commit,
        "production_tree": production_tree,
        "full_suite": {
            "passed": junit["passed"],
            "skipped": junit["skipped"],
            "xfail": junit["xfail"],
            "errors": junit["errors"],
            "junit_sha256": junit["sha256"],
            "skip_node_ids": junit["skip_node_ids"],
        },
        "profiles": profiles,
        "tdd": tdd_summaries,
    }
    validate_report_data(report, "quality-report-v1.json")
    validate_private_payload(report)
    return report


def assemble_reports(
    kind: str,
    inputs: Sequence[str | Path],
    mode: str,
    *,
    manifest: str | Path | None = None,
) -> dict[str, Any]:
    if kind == "quality":
        return assemble_quality_report(inputs)
    if not inputs:
        raise ValueError("assemble requires inputs")
    paths = [Path(path) for path in inputs]
    if len(set(path.resolve() for path in paths)) != len(paths):
        raise ValueError("duplicate assemble input")
    json_values: list[tuple[Path, Any]] = []
    for path in paths:
        if path.suffix == ".json":
            json_values.append((path, _load_json(path)))

    if kind == "performance":
        reports = [value for _, value in json_values]
        if not reports:
            raise ValueError("performance assembly requires benchmark JSON")
        for report in reports:
            validate_report_data(report, "benchmark-report-v1.json")
            if report["mode"] != mode:
                raise ValueError(
                    "performance assembly requires same-mode benchmark reports"
                )
        identities = {canonical_json(report["identity"]) for report in reports}
        if len(identities) != 1:
            raise ValueError("performance assembly refuses mixed identity")
        cases: list[Mapping[str, Any]] = []
        for report in reports:
            if report["report_scope"] == "tier":
                cases.append(
                    {
                        key: report[key]
                        for key in (
                            "environment",
                            "workload",
                            "operation",
                            "calibration",
                            "samples",
                            "summary",
                            "validity",
                        )
                    }
                )
            elif report["report_scope"] == "performance":
                cases.extend(report["case_reports"])
        case_keys = [
            (
                case["workload"]["tier"],
                case["workload"]["fingerprint_sha256"],
                case["operation"]["operation_id"],
                case["operation"]["case_id"],
                case["operation"]["measurement_state"],
            )
            for case in cases
        ]
        if len(set(case_keys)) != len(case_keys):
            raise ValueError("performance assembly refuses duplicate cases")
        ordered = sorted(zip(case_keys, cases), key=lambda item: item[0])
        result = {
            "schema_version": 1,
            "report_kind": "benchmark",
            "report_scope": "performance",
            "mode": mode,
            "identity": json.loads(canonical_json(reports[0]["identity"])),
            "case_reports": [
                json.loads(canonical_json(case)) for _, case in ordered
            ],
        }
        churn_values = [report["churn"] for report in reports if "churn" in report]
        observed_tiers = {case["workload"]["tier"] for case in cases}
        publication_tiers = {"smoke", "large", "scale-5k", "scale-10k"}
        if mode == "final" and observed_tiers == publication_tiers:
            if len(churn_values) != 1:
                raise ValueError(
                    "complete final performance assembly requires one churn result"
                )
            result["churn"] = json.loads(canonical_json(churn_values[0]))
        elif churn_values:
            raise ValueError("churn belongs only to complete final performance")
        validate_report_data(result, "benchmark-report-v1.json")
        if manifest is not None:
            validate_performance_registry_coverage(result, manifest)
        return result

    if kind == "entry":
        by_name = {path.name: path for path in paths}
        required = ENTRY_RAW_EVIDENCE_NAMES | {
            "entry-commit.txt",
            "entry-evidence-hashes.txt",
        }
        if len(by_name) != len(paths) or set(by_name) != required:
            missing = sorted(required - set(by_name))
            extra = sorted(set(by_name) - required)
            raise ValueError(
                f"entry evidence input set mismatch: missing={missing}, extra={extra}"
            )
        commit = validate_git_sha(
            by_name["entry-commit.txt"].read_text(encoding="utf-8").strip()
        )
        evidence = validate_entry_evidence(
            {name: by_name[name] for name in required if name != "entry-commit.txt"}
        )
        lineage_text = subprocess.check_output(
            ["git", "-C", str(ROOT), "log", "-3", "--format=%H %s", commit],
            text=True,
        )
        result = {
            "schema_version": 1,
            "entry_commit": commit,
            "review_commit": commit,
            "production_tree": validate_git_sha(
                subprocess.check_output(
                    [
                        "git",
                        "-C",
                        str(ROOT),
                        "rev-parse",
                        f"{commit}:src/context_search_tool",
                    ],
                    text=True,
                ).strip()
            ),
            "dependency_sha256": evidence["dependency_sha256"],
            "runtime_sha256": evidence["runtime_sha256"],
            "junit": evidence["junit"],
            "quality": evidence["quality"],
            "lineage": validate_lineage(lineage_text),
        }
        validate_report_data(result, "entry-record-v1.json")
        return result

    if kind == "environment":
        if len(paths) != 2 or len(json_values) != 2:
            raise ValueError(
                "environment assembly requires exactly entry and benchmark JSON"
            )
        entry_values = [
            value for _, value in json_values if "entry_commit" in value
        ]
        benchmark_values = [
            value for _, value in json_values if value.get("report_kind") == "benchmark"
        ]
        if len(entry_values) != 1 or len(benchmark_values) != 1:
            raise ValueError("environment assembly requires one entry and benchmark")
        entry = entry_values[0]
        benchmark = benchmark_values[0]
        validate_report_data(entry, "entry-record-v1.json")
        validate_report_data(benchmark, "benchmark-report-v1.json")
        if benchmark["mode"] != mode:
            raise ValueError("environment assembly benchmark mode differs from request")
        if benchmark["report_scope"] == "tier":
            cases = [benchmark]
        else:
            if manifest is not None:
                validate_performance_registry_coverage(benchmark, manifest)
            cases = benchmark["case_reports"]
        stable_environment_keys = (
            "python",
            "sqlite",
            "os",
            "architecture",
            "cpu_count",
            "memory_bytes",
            "local_disk_class",
            "power_state",
            "governor_state",
        )
        environment = cases[0]["environment"]
        if any(
            any(case["environment"][key] != environment[key] for key in stable_environment_keys)
            for case in cases[1:]
        ):
            raise ValueError("benchmark cases contain mixed stable environment facts")
        calibrations = [case["calibration"] for case in cases]
        result = {
            "schema_version": 1,
            "implementation_commit": benchmark["identity"][
                "implementation_commit"
            ],
            "production_tree": benchmark["identity"]["production_tree"],
            "environment": {
                "python": environment["python"],
                "sqlite": environment["sqlite"],
                "os": environment["os"],
                "architecture": environment["architecture"],
                "logical_cpu_count": environment["cpu_count"],
                "physical_memory_bytes": environment["memory_bytes"],
                "local_disk_class": environment["local_disk_class"],
                "power_state": environment["power_state"],
                "governor_state": environment["governor_state"],
                "swap_growth_bytes": max(
                    max(
                        0,
                        case["environment"]["swap_after_bytes"]
                        - case["environment"]["swap_before_bytes"],
                    )
                    for case in cases
                ),
                "background_cpu_percent": max(
                    case["environment"]["background_cpu_percent"] for case in cases
                ),
                "dependency_lock_sha256": _sha256_path(ROOT / "uv.lock"),
            },
            "calibration": {
                "sha256_mib_per_s": statistics.median(
                    value["sha256_mib_per_s"] for value in calibrations
                ),
                "numpy_dot_ms": statistics.median(
                    value["numpy_dot_ms"] for value in calibrations
                ),
                "sqlite_ms": statistics.median(
                    value["sqlite_ms"] for value in calibrations
                ),
                "paired_drift_percent": max(
                    value["within_pair_percent"] for value in calibrations
                ),
            },
            "entry_record_sha256": hashlib.sha256(
                canonical_json(entry).encode()
            ).hexdigest(),
        }
        validate_report_data(result, "environment-report-v1.json")
        return result
    raise ValueError(f"unknown assemble kind: {kind}")


def _paired_root_identity(root: Path) -> dict[str, str]:
    resolved = root.resolve()
    if not (resolved / "src" / "context_search_tool").is_dir():
        raise ValueError("paired implementation root is incomplete")
    try:
        status = subprocess.check_output(
            ["git", "-C", str(resolved), "status", "--porcelain"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        if status:
            raise ValueError("paired implementation root is dirty")
        commit, tree, _ = _git_identity(resolved)
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ValueError("paired implementation root is not a Git worktree") from exc
    return {"implementation_commit": commit, "production_tree": tree}


def _paired_query_cases(manifest: Path) -> dict[str, dict[str, Any]]:
    query_contract = _load_json(manifest.resolve().with_name("query_cases.json"))
    cases = query_contract.get("cases")
    approved = query_contract.get("approved_generated_query_ids")
    if not isinstance(cases, list) or not isinstance(approved, list):
        raise ValueError("paired query case contract is incomplete")
    by_id: dict[str, dict[str, Any]] = {}
    required = {
        "id",
        "family",
        "selectivity",
        "query_token",
        "planner_enabled",
        "top_k",
    }
    for value in cases:
        if not isinstance(value, dict) or set(value) != required:
            raise ValueError("paired query case contract is not closed")
        case_id = value["id"]
        query_token = value["query_token"]
        if (
            not isinstance(case_id, str)
            or not case_id
            or not isinstance(query_token, str)
            or not query_token
            or case_id in by_id
        ):
            raise ValueError("paired query case identity is invalid")
        by_id[case_id] = value
    if approved != list(by_id):
        raise ValueError("paired approved query identities differ from frozen cases")
    return by_id


def _paired_operation_case(
    operation_id: str,
    query_cases: Mapping[str, Mapping[str, Any]],
) -> tuple[str, str, str]:
    if operation_id in {
        "full_build",
        "authoritative_noop",
        "status_quick",
        "status_verified",
        "refresh_noop",
        "refresh_one_file",
    }:
        return operation_id, "default", "default"
    query_case_ids = {
        "query_lexical_high": "lexical_high",
        "query_lexical_low": "lexical_low",
        "query_lexical_zero": "lexical_zero",
        "query_path_symbol_ambiguous": "path_symbol_ambiguity",
        "query_direct_ascii": "direct_ascii",
        "query_direct_cjk": "direct_cjk",
        "query_signal": "signal_metadata",
        "query_semantic": "semantic_high",
        "query_planner_off": "planner_off_ordinary",
        "explore_p4_bounded": "p4_explore",
    }
    case_id = query_case_ids.get(operation_id)
    if case_id is None or case_id not in query_cases:
        raise ValueError(f"unknown protected paired operation: {operation_id}")
    operation = "explore" if operation_id.startswith("explore_") else "query"
    return operation, case_id, str(query_cases[case_id]["query_token"])


def _run_paired_worker(
    implementation_root: Path,
    operation: str,
    repo: Path,
    operation_case_id: str,
    question: str,
) -> dict[str, Any]:
    request = {
        "schema_version": 1,
        "kind": "operation",
        "operation": operation,
        "repo": str(repo.resolve()),
        "operation_case_id": operation_case_id,
        "case_id": question,
    }
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(implementation_root.resolve() / "src")
    completed = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), "__measure"],
        cwd=implementation_root,
        env=environment,
        input=canonical_json(request),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0:
        raise ValueError(
            f"paired product operation failed with exit {completed.returncode}"
        )
    try:
        result = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError("paired product operation returned invalid JSON") from exc
    if result.get("product_subprocesses") != 0:
        raise ValueError("paired product operation spawned a child process")
    return result


def _paired_calibration_drift(
    baseline: Mapping[str, Any],
    final: Mapping[str, Any],
) -> float:
    values = []
    for key in ("sha256_mib_per_s", "numpy_dot_ms", "sqlite_ms"):
        left = float(baseline[key])
        right = float(final[key])
        denominator = min(left, right)
        if denominator <= 0:
            raise ValueError("paired calibration values must be positive")
        values.append(abs(right - left) * 100.0 / denominator)
    return max(values)


def _paired_summaries(
    samples: Sequence[Mapping[str, Any]],
    operations: Sequence[str],
) -> list[dict[str, Any]]:
    summaries = []
    for operation_id in operations:
        sides: dict[str, dict[str, float]] = {}
        for side in ("baseline", "final"):
            durations = [
                float(sample["duration_ms"])
                for sample in samples
                if sample["operation_id"] == operation_id
                and sample["side"] == side
                and sample["outcome"] == "supported"
            ]
            if not durations:
                sides[side] = {
                    "outcome": "unsupported",
                    "median_ms": None,
                    "cv_population": None,
                }
            else:
                mean = statistics.fmean(durations)
                sides[side] = {
                    "outcome": "supported",
                    "median_ms": statistics.median(durations),
                    "cv_population": (
                        statistics.pstdev(durations) / mean
                        if len(durations) > 1
                        else 0.0
                    ),
                }
        baseline_median = sides["baseline"]["median_ms"]
        final_median = sides["final"]["median_ms"]
        summaries.append(
            {
                "operation_id": operation_id,
                "baseline": sides["baseline"],
                "final": sides["final"],
                "median_ratio": (
                    final_median / baseline_median
                    if baseline_median is not None
                    and final_median is not None
                    and baseline_median > 0
                    else None
                ),
            }
        )
    return summaries


def validate_paired_report(report: Mapping[str, Any]) -> None:
    top_keys = {
        "schema_version",
        "kind",
        "operation_set",
        "pair_count",
        "workload",
        "harness_sha256",
        "implementations",
        "calibrations",
        "protected_operation_ids",
        "samples",
        "summaries",
    }
    if set(report) != top_keys or report.get("schema_version") != 1:
        raise ValueError("paired report fields do not match the closed contract")
    if (
        report.get("kind") != "paired"
        or report.get("operation_set") != "protected_small_entry_comparable"
    ):
        raise ValueError("paired report identity is invalid")
    pair_count = report["pair_count"]
    if not isinstance(pair_count, int) or isinstance(pair_count, bool) or pair_count < 1:
        raise ValueError("paired report pair count is invalid")
    workload = report["workload"]
    if not isinstance(workload, Mapping) or set(workload) != {
        "manifest_sha256",
        "generator_version",
        "generator_sha256",
        "seed",
        "tier",
        "pristine_fingerprint_sha256",
    }:
        raise ValueError("paired workload identity is not closed")
    for key in ("manifest_sha256", "generator_sha256", "pristine_fingerprint_sha256"):
        if not re.fullmatch(r"[0-9a-f]{64}", str(workload[key])):
            raise ValueError("paired workload digest is invalid")
    if not re.fullmatch(r"[0-9a-f]{64}", str(report["harness_sha256"])):
        raise ValueError("paired harness digest is invalid")
    implementations = report["implementations"]
    if not isinstance(implementations, Mapping) or set(implementations) != {
        "baseline",
        "final",
    }:
        raise ValueError("paired implementation identities are invalid")
    for identity in implementations.values():
        if not isinstance(identity, Mapping) or set(identity) != {
            "implementation_commit",
            "production_tree",
        }:
            raise ValueError("paired implementation identity is not closed")
        validate_git_sha(str(identity["implementation_commit"]))
        validate_git_sha(str(identity["production_tree"]))
    calibrations = report["calibrations"]
    if not isinstance(calibrations, Mapping) or set(calibrations) != {
        "baseline",
        "final",
        "maximum_drift_percent",
        "within_ten_percent",
    }:
        raise ValueError("paired calibration identity is not closed")
    if calibrations["within_ten_percent"] is not True or not (
        0 <= float(calibrations["maximum_drift_percent"]) <= 10
    ):
        raise ValueError("paired calibration drift exceeds the frozen limit")
    operations = report["protected_operation_ids"]
    if (
        not isinstance(operations, list)
        or not operations
        or len(operations) != len(set(operations))
        or not all(isinstance(value, str) and value for value in operations)
    ):
        raise ValueError("paired protected operations are invalid")
    samples = report["samples"]
    if not isinstance(samples, list) or len(samples) != len(operations) * pair_count * 2:
        raise ValueError("paired report sample cardinality is invalid")
    sample_keys = {
        "pair_id",
        "order_index",
        "side",
        "operation_id",
        "case_id",
        "repository_fingerprint_sha256",
        "outcome",
        "duration_ms",
        "immutable_state_load_ms",
        "rss",
        "vector_payload_bytes",
        "product_subprocesses",
    }
    expected_pair_orders = {
        pair_id: [side for candidate, side in alternating_pairs(pair_count) if candidate == pair_id]
        for pair_id in {candidate for candidate, _ in alternating_pairs(pair_count)}
    }
    for operation_id in operations:
        operation_samples = [
            sample for sample in samples if sample.get("operation_id") == operation_id
        ]
        if len(operation_samples) != pair_count * 2:
            raise ValueError("paired operation sample cardinality is invalid")
        for pair_index in range(1, pair_count + 1):
            pair_id = f"pair-{pair_index:03d}"
            paired = [
                sample for sample in operation_samples if sample.get("pair_id") == pair_id
            ]
            if [sample.get("side") for sample in paired] != expected_pair_orders[pair_id]:
                raise ValueError("paired execution order is not alternating")
            if [sample.get("order_index") for sample in paired] != [1, 2]:
                raise ValueError("paired execution order index is invalid")
            for sample in paired:
                if not isinstance(sample, Mapping) or set(sample) != sample_keys:
                    raise ValueError("paired sample fields are not closed")
                if (
                    sample["repository_fingerprint_sha256"]
                    != workload["pristine_fingerprint_sha256"]
                    or sample["product_subprocesses"] != 0
                    or sample["outcome"] not in {"supported", "unsupported"}
                ):
                    raise ValueError("paired sample identity is invalid")
                if sample["outcome"] == "unsupported":
                    if any(
                        sample[key] is not None
                        for key in (
                            "duration_ms",
                            "immutable_state_load_ms",
                            "rss",
                            "vector_payload_bytes",
                        )
                    ):
                        raise ValueError("unsupported paired sample contains measurements")
                elif (
                    not isinstance(sample["duration_ms"], (int, float))
                    or float(sample["duration_ms"]) <= 0
                    or not isinstance(
                        sample["immutable_state_load_ms"], (int, float)
                    )
                    or float(sample["immutable_state_load_ms"]) < 0
                    or not isinstance(sample["rss"], Mapping)
                    or not isinstance(sample["vector_payload_bytes"], int)
                    or isinstance(sample["vector_payload_bytes"], bool)
                    or sample["vector_payload_bytes"] < 0
                ):
                    raise ValueError("supported paired sample is incomplete")
    expected_summaries = _paired_summaries(samples, operations)
    if canonical_json(report["summaries"]) != canonical_json(expected_summaries):
        raise ValueError("paired summaries differ from raw samples")


def paired_runs(
    baseline_root: Path,
    final_root: Path,
    repo: Path,
    manifest: Path,
    *,
    pair_count: int,
    operation_set: str,
) -> dict[str, Any]:
    if pair_count < 1:
        raise ValueError("pair count must be positive")
    roots = {"baseline": baseline_root.resolve(), "final": final_root.resolve()}
    if roots["baseline"] == roots["final"]:
        raise ValueError("paired implementation roots must be distinct")
    identities = {side: _paired_root_identity(root) for side, root in roots.items()}

    pristine = repo.resolve()
    if not pristine.is_dir() or (pristine / ".context-search").exists():
        raise ValueError("paired repository must be a pristine generated root")
    contract = _load_json(manifest)
    if operation_set != "protected_small_entry_comparable":
        raise ValueError("unknown paired operation set")
    operations = contract.get(operation_set)
    if (
        not isinstance(operations, list)
        or not operations
        or len(set(operations)) != len(operations)
        or not all(isinstance(value, str) and value for value in operations)
    ):
        raise ValueError("paired operation set must be a unique non-empty string list")
    tier = _tier_for_repo(pristine, contract)
    pristine_fingerprint = _repository_fingerprint(pristine)
    expected_fingerprint = contract.get("expected_fingerprints", {}).get(tier)
    if pristine_fingerprint != expected_fingerprint:
        raise ValueError("pristine repository fingerprint differs from frozen manifest")
    query_cases = _paired_query_cases(manifest)

    baseline_calibration = _calibration()
    final_calibration = _calibration()
    calibration_drift = _paired_calibration_drift(
        baseline_calibration, final_calibration
    )
    baseline_calibration = dict(baseline_calibration)
    final_calibration = dict(final_calibration)
    baseline_calibration["within_pair_percent"] = calibration_drift
    final_calibration["within_pair_percent"] = calibration_drift

    samples: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="p6-paired-", dir=pristine.parent) as raw:
        temporary_root = Path(raw)
        for operation_id in operations:
            measured_operation, case_id, question = _paired_operation_case(
                operation_id, query_cases
            )
            ordered_pairs = alternating_pairs(pair_count)
            for offset in range(0, len(ordered_pairs), 2):
                pair_entries = ordered_pairs[offset : offset + 2]
                pair_id = pair_entries[0][0]
                pair_root = temporary_root / operation_id / pair_id
                clones: dict[str, Path] = {}
                for _, side in pair_entries:
                    clone = pair_root / side
                    shutil.copytree(pristine, clone)
                    clones[side] = clone
                    _run_paired_worker(
                        roots[side], "full_build", clone, "default", "default"
                    )
                    if _repository_fingerprint(clone) != pristine_fingerprint:
                        raise ValueError("paired setup changed generated repository content")
                if measured_operation == "full_build":
                    for clone in clones.values():
                        index = clone / ".context-search"
                        if index.exists():
                            shutil.rmtree(index)
                for order_index, (_, side) in enumerate(pair_entries, start=1):
                    supported = not (
                        side == "baseline"
                        and measured_operation
                        in {
                            "status_quick",
                            "status_verified",
                            "refresh_noop",
                            "refresh_one_file",
                        }
                    ) and _operation_command(
                        measured_operation, clones[side], question
                    ) is not None
                    if supported and measured_operation == "refresh_one_file":
                        _prepare_one_file_refresh(
                            clones[side],
                            f"{pair_id}-{side}-measured",
                        )
                    measured = (
                        _run_paired_worker(
                            roots[side],
                            measured_operation,
                            clones[side],
                            case_id,
                            question,
                        )
                        if supported
                        else None
                    )
                    attribution = (
                        measured.get("attribution")
                        if isinstance(measured, Mapping)
                        else None
                    )
                    if measured is not None and not isinstance(attribution, Mapping):
                        raise ValueError("paired sample lacks measured attribution")
                    immutable_state_load_ms = (
                        attribution.get("immutable_state_load_ms")
                        if attribution is not None
                        else None
                    )
                    if measured is not None and not isinstance(
                        immutable_state_load_ms, (int, float)
                    ):
                        raise ValueError("paired sample lacks immutable-state timing")
                    samples.append(
                        {
                            "pair_id": pair_id,
                            "order_index": order_index,
                            "side": side,
                            "operation_id": operation_id,
                            "case_id": case_id,
                            "repository_fingerprint_sha256": pristine_fingerprint,
                            "outcome": "supported" if supported else "unsupported",
                            "duration_ms": (
                                float(measured["duration_ms"])
                                if measured is not None
                                else None
                            ),
                            "immutable_state_load_ms": (
                                float(immutable_state_load_ms)
                                if immutable_state_load_ms is not None
                                else None
                            ),
                            "rss": measured["rss"] if measured is not None else None,
                            "vector_payload_bytes": (
                                _disk_components(clones[side])["vector_payload_bytes"]
                                if measured is not None
                                else None
                            ),
                            "product_subprocesses": (
                                measured["product_subprocesses"]
                                if measured is not None
                                else 0
                            ),
                        }
                    )

    result = {
        "schema_version": 1,
        "kind": "paired",
        "operation_set": operation_set,
        "pair_count": pair_count,
        "workload": {
            "manifest_sha256": _sha256_path(manifest),
            "generator_version": contract["generator"]["version"],
            "generator_sha256": contract["generator"]["contract_sha256"],
            "seed": contract["generator"]["seed"],
            "tier": tier,
            "pristine_fingerprint_sha256": pristine_fingerprint,
        },
        "harness_sha256": _sha256_path(__file__),
        "implementations": identities,
        "calibrations": {
            "baseline": baseline_calibration,
            "final": final_calibration,
            "maximum_drift_percent": calibration_drift,
            "within_ten_percent": calibration_drift <= 10.0,
        },
        "protected_operation_ids": list(operations),
        "samples": samples,
        "summaries": _paired_summaries(samples, operations),
    }
    _assert_finite(result)
    validate_paired_report(result)
    validate_private_payload(result)
    return result


def compare_reports(baseline: Any, final: Any) -> dict[str, Any]:
    for report in (baseline, final):
        validate_report_data(report, "benchmark-report-v1.json")
    for key in ("workload", "operation"):
        if baseline[key] != final[key]:
            raise ValueError(f"cannot compare mixed {key}")
    baseline_ms = baseline["summary"]["median_ms"]
    final_ms = final["summary"]["median_ms"]
    return {
        "schema_version": 1,
        "kind": "comparison",
        "operation_id": baseline["operation"]["operation_id"],
        "case_id": baseline["operation"]["case_id"],
        "baseline_median_ms": baseline_ms,
        "final_median_ms": final_ms,
        "median_ratio": final_ms / baseline_ms if baseline_ms else 0.0,
        "valid": baseline["validity"]["valid"] and final["validity"]["valid"],
    }


def _acceptance_case(
    report: Mapping[str, Any],
    tier: str,
    operation_id: str,
    case_id: str,
    measurement_state: str,
) -> Mapping[str, Any]:
    matches = [
        case
        for case in report["case_reports"]
        if (
            case["workload"]["tier"],
            case["operation"]["operation_id"],
            case["operation"]["case_id"],
            case["operation"]["measurement_state"],
        )
        == (tier, operation_id, case_id, measurement_state)
    ]
    if len(matches) != 1:
        raise ValueError("P6 acceptance case identity is missing or ambiguous")
    case = matches[0]
    if case["operation"]["outcome"] != "supported" or not case["validity"][
        "valid"
    ]:
        raise ValueError("P6 acceptance case is unsupported or invalid")
    return case


def _nearest_rank_p95(values: Sequence[float]) -> float:
    if not values:
        raise ValueError("P6 acceptance distribution is empty")
    ordered = sorted(float(value) for value in values)
    return ordered[math.ceil(0.95 * len(ordered)) - 1]


def _acceptance_ratio(numerator: float, denominator: float, label: str) -> float:
    if denominator <= 0:
        raise ValueError(f"P6 acceptance denominator is invalid: {label}")
    return numerator / denominator


def _require_acceptance(condition: bool, label: str) -> None:
    if not condition:
        raise ValueError(f"P6 acceptance gate failed: {label}")


def _max_sample_value(case: Mapping[str, Any], *keys: str) -> float:
    values = []
    for sample in case["samples"]:
        value: Any = sample
        for key in keys:
            value = value[key]
        values.append(float(value))
    if not values:
        raise ValueError("P6 acceptance case has no samples")
    return max(values)


def _large_acceptance_gates(final: Mapping[str, Any]) -> None:
    mib = 1024**2
    gib = 1024**3
    large_source_bytes = 512 * mib
    cold = "cli_process_cold"
    warm = "mcp_resident_warm"

    full = _acceptance_case(final, "large", "full_build", "default", cold)
    _require_acceptance(full["summary"]["median_ms"] <= 300_000, "large full-build median")
    _require_acceptance(full["summary"]["max_ms"] <= 420_000, "large full-build maximum")
    _require_acceptance(_max_sample_value(full, "rss", "peak_bytes") <= 2 * gib, "large full-build RSS")
    _require_acceptance(_max_sample_value(full, "disk", "total_bytes") <= 2.5 * gib, "large full-build disk")
    for sample in full["samples"]:
        generation_bytes = sample["disk"]["vector_payload_bytes"] + sample["disk"]["vector_id_bytes"]
        published_bytes = generation_bytes + sample["disk"]["descriptor_bytes"]
        _require_acceptance(
            published_bytes <= max(1, generation_bytes) * 2.10,
            "vector publication disk",
        )
        _require_acceptance(sample["work"]["generation_count"] == 1, "vector generation count")

    authoritative = _acceptance_case(
        final, "large", "authoritative_noop", "default", cold
    )
    _require_acceptance(authoritative["summary"]["median_ms"] <= 15_000, "large authoritative no-op median")
    _require_acceptance(authoritative["summary"]["max_ms"] <= 25_000, "large authoritative no-op maximum")
    _require_acceptance(_max_sample_value(authoritative, "rss", "extra_peak_bytes") <= 512 * mib, "large authoritative no-op RSS")
    for sample in authoritative["samples"]:
        work = sample["work"]
        _require_acceptance(work["source_bytes_hashed"] == large_source_bytes, "authoritative source hash bytes")
        _require_acceptance(
            all(
                work[name] == 0
                for name in (
                    "peak_queued_files",
                    "peak_queued_chunks",
                    "peak_queued_text_bytes",
                    "vector_rows_queued",
                    "embedding_batch_calls",
                    "embedding_batch_inputs",
                )
            ),
            "authoritative no-op parse/embed work",
        )

    quick = _acceptance_case(final, "large", "status_quick", "default", cold)
    _require_acceptance(quick["summary"]["p95_ms"] <= 2_000, "quick status p95")
    _require_acceptance(_max_sample_value(quick, "rss", "extra_peak_bytes") <= 256 * mib, "quick status RSS")
    for sample in quick["samples"]:
        work = sample["work"]
        _require_acceptance(
            all(
                work[name] == 0
                for name in (
                    "source_bytes_read",
                    "source_bytes_hashed",
                    "vector_bytes_read",
                    "vector_bytes_hashed",
                )
            ),
            "quick status body/vector reads",
        )

    verified = _acceptance_case(
        final, "large", "status_verified", "default", cold
    )
    _require_acceptance(verified["summary"]["max_ms"] <= 12_000, "verified status maximum")
    _require_acceptance(_max_sample_value(verified, "rss", "extra_peak_bytes") <= 256 * mib, "verified status RSS")
    throughputs = []
    for sample in verified["samples"]:
        source_ms = float(sample["stage_timings_ms"]["source"])
        _require_acceptance(source_ms > 0, "verified status source timing")
        throughputs.append(
            float(sample["work"]["source_bytes_hashed"]) * 1000 / source_ms / mib
        )
    _require_acceptance(statistics.median(throughputs) >= 75, "verified status source throughput")

    refresh_noop = _acceptance_case(
        final, "large", "refresh_noop", "default", cold
    )
    _require_acceptance(refresh_noop["summary"]["p95_ms"] <= 2_500, "no-op refresh p95")
    zero_refresh_work = (
        "source_bytes_read",
        "source_bytes_hashed",
        "peak_queued_files",
        "peak_queued_chunks",
        "peak_queued_text_bytes",
        "vector_rows_queued",
        "embedding_batch_calls",
        "embedding_batch_inputs",
        "flush_count",
        "vector_bytes_written",
        "vector_bytes_copied",
        "association_writes",
    )
    for sample in refresh_noop["samples"]:
        _require_acceptance(
            all(sample["work"][name] == 0 for name in zero_refresh_work),
            "no-op refresh zero work",
        )

    refresh_one = _acceptance_case(
        final, "large", "refresh_one_file", "default", cold
    )
    _require_acceptance(refresh_one["summary"]["p95_ms"] <= 5_000, "one-file refresh p95")
    for sample in refresh_one["samples"]:
        work = sample["work"]
        generation_bytes = sample["disk"]["vector_payload_bytes"] + sample["disk"]["vector_id_bytes"]
        _require_acceptance(
            sample["rss"]["extra_peak_bytes"]
            <= sample["disk"]["vector_payload_bytes"] * 2.2 + 256 * mib,
            "one-file refresh RSS",
        )
        _require_acceptance(work["vector_bytes_read"] <= generation_bytes * 1.10, "one-file vector reads")
        _require_acceptance(work["vector_bytes_written"] <= generation_bytes * 1.10, "one-file vector writes")
        _require_acceptance(work["vector_payload_passes"] <= 2, "one-file prior vector passes")
        _require_acceptance(work["path_index_builds"] <= 1, "one-file declared path fan-out")
        _require_acceptance(work["inventory_errors"] == 0, "one-file inventory completeness")

    query_cases = [
        case
        for case in final["case_reports"]
        if case["workload"]["tier"] == "large"
        and case["operation"]["operation_id"] == "query"
        and case["operation"]["measurement_state"] in {cold, warm}
    ]
    _require_acceptance(len(query_cases) == 18, "large ordinary query coverage")
    for case in query_cases:
        state = case["operation"]["measurement_state"]
        _require_acceptance(case["operation"]["outcome"] == "supported", "ordinary query support")
        limit = 750 if state == warm else 2_000
        _require_acceptance(case["summary"]["p95_ms"] <= limit, "ordinary query p95")
        if state == warm:
            semantic_p95 = _nearest_rank_p95(
                [sample["stage_timings_ms"]["semantic"] for sample in case["samples"]]
            )
            _require_acceptance(semantic_p95 <= 300, "semantic stage p95")
        for sample in case["samples"]:
            _require_acceptance(
                sample["rss"]["extra_peak_bytes"]
                <= sample["disk"]["vector_payload_bytes"] * 1.35 + 256 * mib,
                "ordinary query RSS",
            )

    explore = _acceptance_case(final, "large", "explore", "p4_explore", warm)
    _require_acceptance(explore["summary"]["p95_ms"] <= 2_500, "bounded explore p95")
    for sample in explore["samples"]:
        _require_acceptance(sample["work"]["vector_payload_passes"] <= 3, "bounded explore retrieval calls")
        _require_acceptance(
            sample["rss"]["extra_peak_bytes"]
            <= sample["disk"]["vector_payload_bytes"] * 1.35 + 256 * mib,
            "bounded explore RSS",
        )


def _scale_acceptance_gates(final: Mapping[str, Any]) -> None:
    cold = "cli_process_cold"

    def cases(operation: str) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
        return (
            _acceptance_case(final, "scale-5k", operation, "default", cold),
            _acceptance_case(final, "scale-10k", operation, "default", cold),
        )

    full_5k, full_10k = cases("full_build")
    _require_acceptance(
        _acceptance_ratio(full_10k["summary"]["median_ms"], full_5k["summary"]["median_ms"], "full-build time") <= 2.7,
        "5k-to-10k full-build time",
    )
    _require_acceptance(
        _acceptance_ratio(_max_sample_value(full_10k, "rss", "peak_bytes"), _max_sample_value(full_5k, "rss", "peak_bytes"), "full-build RSS") <= 2.7,
        "5k-to-10k full-build RSS",
    )

    noop_5k, noop_10k = cases("authoritative_noop")
    _require_acceptance(
        _acceptance_ratio(noop_10k["summary"]["median_ms"], noop_5k["summary"]["median_ms"], "authoritative time") <= 2.4,
        "5k-to-10k authoritative time",
    )
    _require_acceptance(
        _acceptance_ratio(_max_sample_value(noop_10k, "work", "source_bytes_hashed"), _max_sample_value(noop_5k, "work", "source_bytes_hashed"), "authoritative source work") <= 2.4,
        "5k-to-10k authoritative source work",
    )

    for operation in ("status_quick", "status_verified", "refresh_noop"):
        lower, upper = cases(operation)
        _require_acceptance(
            _acceptance_ratio(upper["summary"]["median_ms"], lower["summary"]["median_ms"], f"{operation} time") <= 2.4,
            f"5k-to-10k {operation} time",
        )
        _require_acceptance(
            _acceptance_ratio(_max_sample_value(upper, "work", "inventory_entries"), _max_sample_value(lower, "work", "inventory_entries"), f"{operation} entries") <= 2.4,
            f"5k-to-10k {operation} entry work",
        )

    one_5k, one_10k = cases("refresh_one_file")
    _require_acceptance(
        _acceptance_ratio(one_10k["summary"]["median_ms"], one_5k["summary"]["median_ms"], "one-file time") <= 2.4,
        "5k-to-10k one-file time",
    )
    for counter in ("vector_bytes_read", "vector_bytes_written"):
        _require_acceptance(
            _acceptance_ratio(_max_sample_value(one_10k, "work", counter), _max_sample_value(one_5k, "work", counter), f"one-file {counter}") <= 2.4,
            f"5k-to-10k one-file {counter}",
        )
    _require_acceptance(
        _acceptance_ratio(_max_sample_value(one_10k, "rss", "extra_peak_bytes"), _max_sample_value(one_5k, "rss", "extra_peak_bytes"), "one-file RSS") <= 2.4,
        "5k-to-10k one-file RSS",
    )


def compare_acceptance_reports(
    baseline: Mapping[str, Any],
    final: Mapping[str, Any],
    paired: Mapping[str, Any],
    churn: Mapping[str, Any],
    *,
    manifest: str | Path,
    input_sha256: Mapping[str, str],
) -> dict[str, Any]:
    validate_report_data(baseline, "benchmark-report-v1.json")
    validate_report_data(final, "benchmark-report-v1.json")
    validate_paired_report(paired)
    validate_report_data(churn, "benchmark-report-v1.json")
    validate_performance_registry_coverage(baseline, manifest)
    validate_performance_registry_coverage(final, manifest)
    _require_acceptance(baseline["mode"] == "baseline", "baseline mode")
    _require_acceptance(final["mode"] == "final", "final mode")
    _require_acceptance(churn["mode"] == "final" and churn["report_scope"] == "churn", "churn identity")
    _require_acceptance(
        baseline["identity"]["workload_sha256"]
        == final["identity"]["workload_sha256"]
        == churn["identity"]["workload_sha256"],
        "workload identity",
    )
    _require_acceptance(
        final["identity"]["implementation_commit"]
        == churn["identity"]["implementation_commit"]
        == paired["implementations"]["final"]["implementation_commit"],
        "final implementation identity",
    )
    _require_acceptance(
        final["identity"]["production_tree"]
        == churn["identity"]["production_tree"]
        == paired["implementations"]["final"]["production_tree"],
        "final production identity",
    )
    _require_acceptance(
        baseline["identity"]["implementation_commit"]
        == paired["implementations"]["baseline"]["implementation_commit"],
        "baseline implementation identity",
    )
    _require_acceptance(final.get("churn") == churn["churn"], "embedded churn evidence")

    baseline_cases = {
        (
            case["workload"]["tier"],
            case["operation"]["operation_id"],
            case["operation"]["case_id"],
            case["operation"]["measurement_state"],
        ): case
        for case in baseline["case_reports"]
    }
    for case in final["case_reports"]:
        key = (
            case["workload"]["tier"],
            case["operation"]["operation_id"],
            case["operation"]["case_id"],
            case["operation"]["measurement_state"],
        )
        baseline_case = baseline_cases[key]
        for metric in ("sha256_mib_per_s", "numpy_dot_ms", "sqlite_ms"):
            drift = abs(
                float(case["calibration"][metric])
                - float(baseline_case["calibration"][metric])
            ) / min(
                float(case["calibration"][metric]),
                float(baseline_case["calibration"][metric]),
            )
            _require_acceptance(drift <= 0.10, f"calibration drift {metric}")

    _large_acceptance_gates(final)
    _scale_acceptance_gates(final)
    _require_acceptance(paired["pair_count"] >= 30, "paired sample count")
    expected_operations = _load_json(manifest)["protected_small_entry_comparable"]
    _require_acceptance(
        paired["protected_operation_ids"] == expected_operations,
        "protected paired operation coverage",
    )
    entry_unsupported = {
        "status_quick",
        "status_verified",
        "refresh_noop",
        "refresh_one_file",
    }
    for summary in paired["summaries"]:
        operation_id = summary["operation_id"]
        _require_acceptance(summary["final"]["outcome"] == "supported", "final paired support")
        if operation_id in entry_unsupported:
            _require_acceptance(summary["baseline"]["outcome"] == "unsupported", "entry unsupported identity")
            continue
        _require_acceptance(summary["baseline"]["outcome"] == "supported", "entry paired support")
        _require_acceptance(summary["baseline"]["cv_population"] <= 0.08, "baseline paired CV")
        _require_acceptance(summary["final"]["cv_population"] <= 0.08, "final paired CV")
        _require_acceptance(summary["median_ratio"] <= 1.10, "protected latency regression")

    if set(input_sha256) != {"baseline", "final", "paired", "churn"} or any(
        re.fullmatch(r"[0-9a-f]{64}", str(value)) is None
        for value in input_sha256.values()
    ):
        raise ValueError("P6 acceptance input digests are invalid")
    report = {
        "schema_version": 1,
        "report_kind": "acceptance",
        "implementation_commit": final["identity"]["implementation_commit"],
        "production_tree": final["identity"]["production_tree"],
        "inputs": dict(input_sha256),
        "gates": {
            "registry_coverage": True,
            "absolute_large_budgets": True,
            "scale_budgets": True,
            "churn": True,
            "protected_regression": True,
        },
        "conclusion": "success",
    }
    validate_report_data(report, "acceptance-report-v1.json")
    validate_private_payload(report)
    return report


def generate_repository(
    tier: str,
    output: str | Path,
    manifest: str | Path,
    *,
    max_files: int | None = None,
) -> dict[str, Any]:
    output_path = Path(output).resolve()
    try:
        relative_output = output_path.relative_to(ROOT)
    except ValueError:
        relative_output = None
    if relative_output is not None and (
        not relative_output.parts or relative_output.parts[0] != ".quality"
    ):
        raise ValueError(
            "generated repositories must be external or under the ignored .quality root"
        )
    if output_path.exists():
        raise FileExistsError(output_path)

    manifest_path = Path(manifest)
    try:
        contract = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("invalid workload manifest") from exc
    if workload_contract_sha256(contract) != contract.get("generator", {}).get(
        "contract_sha256"
    ):
        raise ValueError("workload manifest contract fingerprint does not match")
    tiers = contract.get("tiers", {})
    if tier not in tiers:
        raise ValueError(f"unknown workload tier: {tier}")
    requested_files = tiers[tier]["files"]
    requested_bytes = tiers[tier]["source_bytes"]
    edit_schedule = generate_edit_schedule(contract, tier)
    file_count = requested_files if max_files is None else min(requested_files, max_files)
    if not isinstance(file_count, int) or file_count < 0:
        raise ValueError("max_files must be a non-negative integer")

    output_path.mkdir(parents=True)
    fingerprint = hashlib.sha256()
    if max_files is None:
        file_sizes = _tier_file_sizes(
            requested_files,
            requested_bytes,
            contract["distributions"]["file_size_bytes"],
        )
    else:
        base_size, remainder = divmod(requested_bytes, requested_files)
        file_sizes = [
            base_size + (1 if index < remainder else 0)
            for index in range(file_count)
        ]
    for index in range(file_count):
        relative = _generated_relative_path(index, requested_files)
        target_size = file_sizes[index]
        body = _generated_java_bytes(index, target_size, requested_files)
        destination = output_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(body)
        fingerprint.update(relative.as_posix().encode("utf-8"))
        fingerprint.update(b"\0")
        fingerprint.update(body)
        fingerprint.update(b"\0")

    return {
        "fingerprint_sha256": fingerprint.hexdigest(),
        "generator_sha256": contract["generator"]["contract_sha256"],
        "root": "external",
        "tier": tier,
        "files_generated": file_count,
        "edit_schedule": edit_schedule,
    }


_EXACT_SOURCE_FILES = {
    "src/main/java/com/example/api/CheckoutController.java": """\
package com.example.api;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CheckoutController {
    @GetMapping("/signal-route")
    public String signalroute() {
        return "checkout service flow";
    }
}
""",
    "src/main/java/com/example/service/CheckoutService.java": """\
package com.example.service;

public class CheckoutService {
    public String processCheckout() {
        return "checkout service flow implementation";
    }
}
""",
    "src/main/java/com/example/gateway/AmbiguousGateway.java": """\
package com.example.gateway;

public class AmbiguousGateway {
    public String invoke() { return "primary"; }
}
""",
    "src/test/java/com/example/gateway/AmbiguousGatewayTest.java": """\
package com.example.gateway;

public class AmbiguousGatewayTest {
    public void verifiesAmbiguousGateway() { }
}
""",
    "src/main/java/com/example/text/DirectEvidence.java": """\
package com.example.text;

public class DirectEvidence {
    public static final String ASCII = "invoice/reference:ASCII-9000";
    public static final String CJK = "支付订单状态";
}
""",
    "src/main/java/com/example/search/LexicalCorpus.java": """\
package com.example.search;

public class LexicalCorpus {
    public String frequent() {
        return "lexicalburst lexicalburst lexicalburst lexicalburst lexicalburst";
    }

    public String rare() {
        return "raretoken";
    }
}
""",
    "src/main/java/com/example/semantic/SemanticConcept.java": """\
package com.example.semantic;

public class SemanticConcept {
    public String coordinate() {
        return "distributed idempotency saga coordinator";
    }
}
""",
    "README.md": "Generated P6 exact-candidate snapshot.\n",
}

_SOURCE_PART_KEYS = (
    "lexical",
    "path_symbol",
    "direct_text",
    "signal",
    "semantic",
)


def compute_exact_candidate_baseline(
    snapshot_a: str | Path,
    snapshot_b: str | Path,
    query_manifest: str | Path,
) -> dict[str, Any]:
    manifest_path = Path(query_manifest)
    query_contract = json.loads(manifest_path.read_text(encoding="utf-8"))
    first = _build_exact_snapshot(Path(snapshot_a), query_contract)
    second = _build_exact_snapshot(Path(snapshot_b), query_contract)
    if first != second:
        raise ValueError("independent exact candidate snapshots differ")

    frozen_baseline = manifest_path.with_name("exact_candidate_baseline.json")
    if frozen_baseline.is_file():
        frozen_identity = _load_json(frozen_baseline)
        implementation_commit = validate_git_sha(
            frozen_identity.get("implementation_commit")
        )
        production_tree = validate_git_sha(frozen_identity.get("production_tree"))
        _verify_commit_tree(implementation_commit, production_tree)
    else:
        implementation_commit = subprocess.check_output(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
            text=True,
        ).strip()
        production_tree = subprocess.check_output(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD:src/context_search_tool"],
            text=True,
        ).strip()
    return {
        "schema_version": 1,
        "implementation_commit": validate_git_sha(implementation_commit),
        "production_tree": validate_git_sha(production_tree),
        "query_manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "cases": [
            {
                "case_id": case["case_id"],
                "snapshot_a": case["projection"],
                "snapshot_b": case["projection"],
            }
            for case in first
        ],
    }


def _build_exact_snapshot(
    repo: Path,
    query_contract: Mapping[str, Any],
) -> list[dict[str, Any]]:
    if repo.exists():
        raise FileExistsError(repo)
    for relative, content in _EXACT_SOURCE_FILES.items():
        destination = repo / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content, encoding="utf-8", newline="\n")

    from context_search_tool.config import RetrievalConfig, ToolConfig
    from context_search_tool.exploration.runner import explore_repository
    from context_search_tool.indexer import index_repository
    from context_search_tool.paths import index_dir_for
    from context_search_tool.retrieval import (
        evidence_anchor_top_k,
        query_repository,
    )
    from context_search_tool.context_pack import resolve_context_pack_options
    from context_search_tool.sqlite_store import SQLiteStore

    index_config = ToolConfig(
        retrieval=RetrievalConfig(
            semantic_top_k=12,
            lexical_top_k=24,
            final_top_k=12,
            context_before_lines=0,
            context_after_lines=0,
        )
    )
    index_repository(repo, index_config)
    store = SQLiteStore(index_dir_for(repo) / "index.sqlite")
    projections: list[dict[str, Any]] = []
    for case in query_contract["cases"]:
        family = case["family"]
        semantic_top_k = 12 if family == "semantic" else 0
        final_top_k = case["top_k"]
        query_config = ToolConfig(
            retrieval=RetrievalConfig(
                semantic_top_k=semantic_top_k,
                lexical_top_k=24,
                final_top_k=final_top_k,
                context_before_lines=0,
                context_after_lines=0,
            )
        )
        query = case["query_token"]
        if family == "explore":
            pack_options = resolve_context_pack_options(
                query_config,
                context_lines=None,
                max_evidence_anchors=evidence_anchor_top_k(final_top_k),
            )
            explored = explore_repository(
                repo,
                query,
                query_config,
                pack_options,
            )
            results = explored.fused_bundle.results
        else:
            results = query_repository(repo, query, query_config).results
        projections.append(
            {
                "case_id": case["id"],
                "projection": _exact_result_projection(store, results),
            }
        )
    return projections


def _exact_result_projection(store: Any, results: Sequence[Any]) -> dict[str, Any]:
    result_values: list[dict[str, Any]] = []
    ordered_candidates: list[dict[str, Any]] = []
    for result in results:
        chunk = store.chunk_for_line(result.file_path, result.start_line)
        if chunk is None:
            raise ValueError(
                f"result has no persisted chunk: {result.file_path}:{result.start_line}"
            )
        score_parts = {
            key: float(result.score_parts.get(key, 0.0))
            for key in _SOURCE_PART_KEYS
        }
        ordered_candidates.append(
            {
                "candidate_id": chunk.chunk_id,
                "score": float(result.score),
                "source_parts": score_parts,
            }
        )
        result_values.append(
            {
                "candidate_id": chunk.chunk_id,
                "file_path": result.file_path.as_posix(),
                "start_line": result.start_line,
                "end_line": result.end_line,
                "score": float(result.score),
                "score_parts": {
                    key: float(value)
                    for key, value in sorted(result.score_parts.items())
                },
                "reasons": list(result.reasons),
                "followup_keywords": list(result.followup_keywords),
                "semantic_matches": [
                    {
                        "variant_id": match.variant_id,
                        "score": float(match.score),
                    }
                    for match in result.semantic_matches
                ],
            }
        )
    fingerprint = hashlib.sha256(canonical_json(result_values).encode()).hexdigest()
    return {
        "ordered_candidates": ordered_candidates,
        "final_result_sha256": fingerprint,
    }


def _normalize_distribution_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name.strip()).lower()


def normalize_freeze_lines(
    lines: Iterable[str],
    *,
    installed_versions: Mapping[str, str],
) -> dict[str, Any]:
    raw_lines = [line.rstrip("\r\n") for line in lines]
    raw_bytes = ("\n".join(raw_lines) + "\n").encode("utf-8")
    versions = {
        _normalize_distribution_name(name): version
        for name, version in installed_versions.items()
    }
    packages: dict[str, str] = {}
    for line in raw_lines:
        if not line or line.startswith("#"):
            continue
        if " @ " in line:
            raw_name = line.split(" @ ", 1)[0]
        elif "==" in line:
            raw_name = line.split("==", 1)[0]
        else:
            raise ValueError("unsupported dependency line")
        name = _normalize_distribution_name(raw_name)
        version = versions.get(name)
        if version is None:
            raise ValueError(f"installed version unavailable: {name}")
        if name in packages:
            raise ValueError(f"duplicate dependency: {name}")
        packages[name] = f"{name}=={version}"
    return {
        "packages": [packages[name] for name in sorted(packages)],
        "raw_sha256": hashlib.sha256(raw_bytes).hexdigest(),
    }


def validate_git_sha(value: str) -> str:
    if not _GIT_SHA_RE.fullmatch(value):
        raise ValueError("git SHA must be one lowercase 40-character object ID")
    return value


def validate_lineage(text: str) -> list[dict[str, str]]:
    lines = text.splitlines()
    if not lines:
        raise ValueError("lineage is empty")
    result: list[dict[str, str]] = []
    for line in lines:
        commit, separator, subject = line.partition(" ")
        if not separator or not subject or "\t" in subject:
            raise ValueError("invalid lineage record")
        result.append({"commit": validate_git_sha(commit), "subject": subject})
    return result


def alternating_pairs(count: int) -> list[tuple[str, str]]:
    if count < 1:
        raise ValueError("pair count must be positive")
    result: list[tuple[str, str]] = []
    for index in range(1, count + 1):
        pair_id = f"pair-{index:03d}"
        sides = ("baseline", "final") if index % 2 else ("final", "baseline")
        result.extend((pair_id, side) for side in sides)
    return result


def make_decision(
    decision_kind: str,
    *,
    implementation_commit: str,
    production_tree: str,
    evidence_report_sha256: str,
    reason_codes: list[str],
    trigger_crossed: bool | None = None,
) -> dict[str, Any]:
    validate_git_sha(implementation_commit)
    validate_git_sha(production_tree)
    if not re.fullmatch(r"[0-9a-f]{64}", evidence_report_sha256):
        raise ValueError("invalid evidence report digest")
    if decision_kind == "exact_ann":
        if trigger_crossed is None:
            raise ValueError("ANN decisions require trigger_crossed")
        decision = {
            "schema_version": 1,
            "decision_kind": "exact_ann",
            "implementation_commit": implementation_commit,
            "production_tree": production_tree,
            "decision": (
                "prototype_requires_amendment" if trigger_crossed else "retained"
            ),
            "trigger_crossed": trigger_crossed,
            "evidence_report_sha256": evidence_report_sha256,
            "reason_codes": reason_codes,
        }
    elif decision_kind == "service_watch":
        decision = {
            "schema_version": 1,
            "decision_kind": "service_watch",
            "implementation_commit": implementation_commit,
            "production_tree": production_tree,
            "decision": (
                "eligible_for_separate_design" if trigger_crossed else "deferred"
            ),
            "evidence_report_sha256": evidence_report_sha256,
            "reason_codes": reason_codes,
        }
    else:
        raise ValueError(f"unknown decision kind: {decision_kind}")
    validate_report_data(decision, "decision-record-v1.json")
    return decision


def _decision_benchmark_cases(report: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    validate_report_data(report, "benchmark-report-v1.json")
    if report["mode"] != "final":
        raise ValueError("P6 decisions require final benchmark evidence")
    if report["report_scope"] == "tier":
        return [report]
    if report["report_scope"] == "performance":
        return list(report["case_reports"])
    raise ValueError("P6 decisions require tier or performance evidence")


def decide_ann(
    report: Mapping[str, Any],
    *,
    evidence_report_sha256: str,
) -> dict[str, Any]:
    cases = _decision_benchmark_cases(report)
    semantic_cases = [
        case
        for case in cases
        if case["workload"]["tier"] == "large"
        and case["operation"]["operation_id"] == "query"
        and case["operation"]["case_id"] == "semantic_high"
        and case["operation"]["measurement_state"] == "mcp_resident_warm"
        and case["operation"]["outcome"] == "supported"
    ]
    if len(semantic_cases) != 1:
        raise ValueError("ANN decision requires one large resident semantic case")
    case = semantic_cases[0]
    samples = case["samples"]
    semantic_p95 = _nearest_rank_p95(
        [sample["stage_timings_ms"]["semantic"] for sample in samples]
    )
    semantic_ratios = [
        float(sample["stage_timings_ms"]["semantic"])
        / float(sample["stage_timings_ms"]["end_to_end"])
        for sample in samples
        if float(sample["stage_timings_ms"]["end_to_end"]) > 0
    ]
    if len(semantic_ratios) != len(samples):
        raise ValueError("ANN decision contains invalid end-to-end timing")
    semantic_over = semantic_p95 > 300
    semantic_dominant = statistics.median(semantic_ratios) >= 0.40
    rss_over = any(
        sample["rss"]["extra_peak_bytes"]
        > sample["disk"]["vector_payload_bytes"] * 1.35 + 256 * 1024**2
        for sample in samples
    )
    rss_dominant = rss_over and statistics.median(
        [
            _acceptance_ratio(
                float(sample["disk"]["vector_payload_bytes"]),
                max(1.0, float(sample["rss"]["extra_peak_bytes"])),
                "ANN RSS attribution",
            )
            for sample in samples
        ]
    ) >= 0.40
    trigger_crossed = (semantic_over or rss_over) and (
        semantic_dominant or rss_dominant
    )
    reason_codes = [
        "semantic_over_budget" if semantic_over else "semantic_within_budget",
        "rss_over_budget" if rss_over else "rss_within_budget",
    ]
    if semantic_dominant:
        reason_codes.append("semantic_dominant")
    if rss_dominant:
        reason_codes.append("rss_dominant")
    return make_decision(
        "exact_ann",
        implementation_commit=report["identity"]["implementation_commit"],
        production_tree=report["identity"]["production_tree"],
        evidence_report_sha256=evidence_report_sha256,
        reason_codes=reason_codes,
        trigger_crossed=trigger_crossed,
    )


def decide_service_watch(
    report: Mapping[str, Any],
    paired: Mapping[str, Any],
    acceptance: Mapping[str, Any],
    *,
    evidence_report_sha256: str,
) -> dict[str, Any]:
    _decision_benchmark_cases(report)
    validate_paired_report(paired)
    validate_report_data(acceptance, "acceptance-report-v1.json")
    final_identity = paired["implementations"]["final"]
    if (
        acceptance["conclusion"] != "success"
        or acceptance["implementation_commit"]
        != report["identity"]["implementation_commit"]
        or acceptance["production_tree"] != report["identity"]["production_tree"]
        or final_identity["implementation_commit"]
        != report["identity"]["implementation_commit"]
        or final_identity["production_tree"] != report["identity"]["production_tree"]
    ):
        raise ValueError("service/watch evidence identities disagree")
    samples = [
        sample
        for sample in paired["samples"]
        if sample["operation_id"] == "query_planner_off"
        and sample["side"] == "final"
        and sample["outcome"] == "supported"
    ]
    if len(samples) < 30:
        raise ValueError("service/watch decision requires 30 final paired samples")
    ratios = []
    counterfactual = []
    durations = []
    rss_within = True
    for sample in samples:
        duration = float(sample["duration_ms"])
        load = float(sample["immutable_state_load_ms"])
        if duration <= 0 or load < 0 or load > duration:
            raise ValueError("service/watch paired timing is invalid")
        durations.append(duration)
        ratios.append(load / duration)
        counterfactual.append(max(0.0, duration - load))
        rss_within = rss_within and (
            sample["rss"]["extra_peak_bytes"]
            <= sample["vector_payload_bytes"] * 1.35 + 256 * 1024**2
        )
    duration_p95 = _nearest_rank_p95(durations)
    counterfactual_p95 = _nearest_rank_p95(counterfactual)
    counterfactual_sufficient = (
        counterfactual_p95 <= 750
        or _acceptance_ratio(
            duration_p95,
            max(counterfactual_p95, 0.001),
            "service/watch counterfactual",
        )
        >= 2.0
    )
    load_dominant = statistics.median(ratios) >= 0.40 or (
        duration_p95 > 750 and counterfactual_p95 <= 750
    )
    eligible = load_dominant and counterfactual_sufficient and rss_within
    reason_codes = []
    if eligible:
        reason_codes.append("eligibility_met")
    else:
        if not load_dominant:
            reason_codes.append("load_not_dominant")
        if not counterfactual_sufficient:
            reason_codes.append("counterfactual_insufficient")
        if not rss_within:
            reason_codes.append("rss_exceeded")
    return make_decision(
        "service_watch",
        implementation_commit=report["identity"]["implementation_commit"],
        production_tree=report["identity"]["production_tree"],
        evidence_report_sha256=evidence_report_sha256,
        reason_codes=reason_codes,
        trigger_crossed=eligible,
    )


def validate_tdd_record_data(record: Any, *, staged_tree: str | None = None) -> None:
    validate_report_data(record, "tdd-record-v1.json")
    if record["red"]["test_identity_sha256"] != record["green"][
        "test_identity_sha256"
    ]:
        raise ValueError("RED and GREEN test identities differ")
    if staged_tree is not None and record["final_staged_tree"] != staged_tree:
        raise ValueError("TDD record is not bound to the staged tree")
    expected_identity, _ = _test_identity(
        record["pytest"]["node_ids"],
        record["pytest"]["arguments"],
        file_hashes=record["test_file_hashes"],
        tree=record["final_staged_tree"],
    )
    if record["red"]["test_identity_sha256"] != expected_identity:
        raise ValueError("TDD record identity does not bind hashes, arguments, and nodes")
    if not set(record["red"]["failed_node_ids"]).issubset(
        record["pytest"]["node_ids"]
    ):
        raise ValueError("RED failed nodes are absent from the frozen pytest nodes")


def _test_identity(
    node_ids: Sequence[str],
    arguments: Sequence[str],
    *,
    file_hashes: Mapping[str, str] | None = None,
    tree: str | None = None,
) -> tuple[str, dict[str, str]]:
    paths = sorted({node.split("::", 1)[0] for node in node_ids})
    if not paths:
        raise ValueError("at least one pytest node is required")
    if file_hashes is None:
        hashes = {
            path: _sha256_path(ROOT / path)
            for path in paths
            if (ROOT / path).is_file()
        }
        if len(hashes) != len(paths):
            raise ValueError("pytest node path is missing")
    else:
        hashes = dict(sorted(file_hashes.items()))
        if tree is None:
            for path, expected in hashes.items():
                candidate = ROOT / path
                if not candidate.is_file() or _sha256_path(candidate) != expected:
                    raise ValueError(f"frozen TDD input changed: {path}")
        else:
            validate_git_sha(tree)
            try:
                if subprocess.check_output(
                    ["git", "-C", str(ROOT), "cat-file", "-t", tree],
                    text=True,
                    stderr=subprocess.DEVNULL,
                ).strip() != "tree":
                    raise ValueError("final staged object is not a Git tree")
                for path, expected in hashes.items():
                    payload = subprocess.check_output(
                        ["git", "-C", str(ROOT), "show", f"{tree}:{path}"],
                        stderr=subprocess.DEVNULL,
                    )
                    if hashlib.sha256(payload).hexdigest() != expected:
                        raise ValueError(f"frozen TDD tree input changed: {path}")
            except subprocess.CalledProcessError as exc:
                raise ValueError("frozen TDD tree input is unavailable") from exc
        if not set(paths).issubset(hashes):
            raise ValueError("pytest node files are absent from frozen TDD inputs")
    identity_payload = {
        "test_file_hashes": hashes,
        "pytest": {
            "arguments": list(arguments),
            "node_ids": list(node_ids),
        },
    }
    digest = hashlib.sha256(canonical_json(identity_payload).encode()).hexdigest()
    return digest, hashes


def _collect_node_ids(selectors: Sequence[str]) -> list[str]:
    if not selectors:
        raise ValueError("at least one pytest selector is required")
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", *selectors],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if completed.returncode != 0:
        raise ValueError("pytest node collection failed")
    node_ids = [
        line.strip()
        for line in completed.stdout.splitlines()
        if re.fullmatch(r"tests/[A-Za-z0-9._/\[\]-]+::[^\r\n]+", line.strip())
    ]
    if not node_ids or len(node_ids) != len(set(node_ids)):
        raise ValueError("pytest collection returned missing or duplicate node IDs")
    return node_ids


def _failed_node_ids(log: str) -> list[str]:
    nodes = []
    for line in log.splitlines():
        match = re.match(r"^FAILED (tests/[^\r\n]+?::[^\r\n]+?)(?: - |$)", line)
        if match:
            nodes.append(match.group(1).strip())
    return sorted(set(nodes))


def _red_log_evidence(log: str) -> tuple[list[str], list[str]]:
    lowered = log.lower()
    if any(
        marker in lowered
        for marker in (
            "error collecting",
            "syntaxerror",
            "importerror",
            "fixture '",
        )
    ):
        raise ValueError("RED contains collection/import/syntax/fixture failure")
    failed_match = re.search(r"(\d+) failed", log)
    failed_nodes = _failed_node_ids(log)
    if (
        failed_match is None
        or int(failed_match.group(1)) < 1
        or len(failed_nodes) != int(failed_match.group(1))
        or "AssertionError" not in log
    ):
        raise ValueError("RED log must contain exact ordinary assertion failures")
    return failed_nodes, _assertion_summaries(log)


def _pytest_phase(arguments: Sequence[str]) -> tuple[int, str, int, int, list[str]]:
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", *arguments],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    output = completed.stdout
    lowered = output.lower()
    if any(
        marker in lowered
        for marker in (
            "error collecting",
            "syntaxerror",
            "importerror",
            "fixture '",
        )
    ):
        raise ValueError("TDD phase contains collection/import/syntax/fixture failure")
    passed_match = re.search(r"(\d+) passed", output)
    failed_match = re.search(r"(\d+) failed", output)
    return (
        completed.returncode,
        output,
        int(passed_match.group(1)) if passed_match else 0,
        int(failed_match.group(1)) if failed_match else 0,
        _failed_node_ids(output),
    )


def _assertion_summaries(log: str) -> list[str]:
    summaries = []
    for line in log.splitlines():
        stripped = line.strip()
        if "AssertionError:" in stripped:
            summaries.append(
                "AssertionError: " + stripped.split("AssertionError:", 1)[1].strip()
            )
    return sorted(set(summaries)) or ["AssertionError: expected RED assertion failure"]


def tdd_red_record(
    task: int,
    pre_change_commit: str,
    nodes: Sequence[str],
) -> dict[str, Any]:
    validate_git_sha(pre_change_commit)
    arguments = ["-q", *nodes]
    node_ids = _collect_node_ids(nodes)
    identity, hashes = _test_identity(node_ids, arguments)
    started = time.time_ns() // 1_000_000
    exit_code, output, _, failed, failed_nodes = _pytest_phase(arguments)
    completed = time.time_ns() // 1_000_000
    if exit_code != 1 or failed < 1:
        raise ValueError("RED must exit 1 with ordinary assertion failures")
    tree = _production_tree_for_commit(pre_change_commit)
    return {
        "schema_version": 1,
        "producer_version": "p6-benchmark-v1",
        "task": task,
        "pre_change_commit": pre_change_commit,
        "pre_change_production_tree": tree,
        "production_file_hashes": {
            "scripts/p6_benchmark.py": _sha256_path(__file__)
        },
        "test_file_hashes": hashes,
        "pytest": {"arguments": arguments, "node_ids": node_ids},
        "red": {
            "exit_code": 1,
            "failed_node_ids": failed_nodes,
            "assertion_summaries": _assertion_summaries(output),
            "started_at_epoch_ms": started,
            "completed_at_epoch_ms": completed,
            "test_identity_sha256": identity,
        },
    }


def tdd_green_record(
    pending: Mapping[str, Any],
    *,
    staged_tree: str,
) -> dict[str, Any]:
    validate_git_sha(staged_tree)
    node_ids = pending["pytest"]["node_ids"]
    arguments = pending["pytest"]["arguments"]
    identity, hashes = _test_identity(
        node_ids,
        arguments,
        file_hashes=pending["test_file_hashes"],
        tree=staged_tree,
    )
    if identity != pending["red"]["test_identity_sha256"]:
        raise ValueError("test identity changed between RED and GREEN")
    started = time.time_ns() // 1_000_000
    exit_code, output, passed, failed, _ = _pytest_phase(arguments)
    completed = time.time_ns() // 1_000_000
    if exit_code != 0 or failed:
        raise ValueError(f"GREEN failed: {output[-500:]}")
    record = dict(pending)
    record["test_file_hashes"] = hashes
    record["green"] = {
        "exit_code": 0,
        "passed": passed,
        "failed": 0,
        "errors": 0,
        "started_at_epoch_ms": started,
        "completed_at_epoch_ms": completed,
        "test_identity_sha256": identity,
    }
    record["final_staged_tree"] = staged_tree
    validate_tdd_record_data(record, staged_tree=staged_tree)
    return record


def publish_report(
    source: str | Path,
    destination: str | Path,
    *,
    publication_root: str | Path | None = None,
    manifest: str | Path | None = None,
) -> None:
    source_path = Path(source)
    try:
        report = json.loads(source_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("publish input is not valid JSON") from exc
    _assert_finite(report)
    validate_report_data(report)
    if (
        manifest is not None
        and report.get("report_kind") == "benchmark"
        and report.get("report_scope") == "performance"
    ):
        validate_performance_registry_coverage(report, manifest)

    root = Path(publication_root or ROOT / "docs" / "benchmarks" / "p6")
    root.mkdir(parents=True, exist_ok=True)
    resolved_root = root.resolve()
    requested = Path(destination).absolute()
    if requested.suffix != ".json":
        raise ValueError("publish destination must be an explicit JSON target")
    resolved_parent = requested.parent.resolve()
    try:
        resolved_parent.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError("publish destination is outside the publication root") from exc
    resolved_parent.mkdir(parents=True, exist_ok=True)
    resolved_parent = resolved_parent.resolve()
    destination_path = resolved_parent / requested.name
    if os.path.lexists(destination_path):
        raise FileExistsError(destination_path)

    content = canonical_json(report).encode("utf-8")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination_path.name}.",
        suffix=".tmp",
        dir=resolved_parent,
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as temporary:
            temporary.write(content)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.link(temporary_path, destination_path)
    finally:
        temporary_path.unlink(missing_ok=True)


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "generate":
            result = generate_repository(
                args.tier,
                args.output,
                args.manifest,
                max_files=args.max_files,
            )
            sys.stdout.write(canonical_json(result))
        elif args.command == "run":
            if os.path.lexists(args.output):
                raise FileExistsError(args.output)
            checkpoint_dir = args.checkpoint_dir or Path(
                f"{args.output}.checkpoints"
            )
            inferred_operations = args.operations
            if inferred_operations is None and all(
                value is None
                for value in (
                    args.operation,
                    args.case_id,
                    args.samples,
                    args.measurement_state,
                )
            ):
                contract = _load_json(args.manifest)
                tier = _tier_for_repo(args.repo.resolve(), contract)
                inferred_operations = {
                    "smoke": "all-smoke",
                    "large": "all-large",
                    "scale-5k": "all-scale",
                    "scale-10k": "all-scale",
                    "stress": "capacity-informational",
                }[tier]
            if inferred_operations is not None:
                if any(
                    value is not None
                    for value in (
                        args.operation,
                        args.case_id,
                        args.samples,
                        args.measurement_state,
                    )
                ):
                    raise ValueError(
                        "--operations cannot be mixed with one-case arguments"
                    )
                report = run_benchmark_set(
                    args.repo,
                    args.manifest,
                    operation_set=inferred_operations,
                    mode=args.mode,
                    checkpoint_dir=checkpoint_dir,
                    resume=args.resume,
                )
            else:
                if (
                    args.operation is None
                    or args.case_id is None
                    or args.samples is None
                    or args.measurement_state is None
                ):
                    raise ValueError(
                        "one-case run requires operation, case, samples, and state"
                    )
                report = run_benchmark(
                    args.repo,
                    args.manifest,
                    operation=args.operation,
                    case_id=args.case_id,
                    sample_count=args.samples,
                    measurement_state=args.measurement_state,
                    mode=args.mode,
                    checkpoint_dir=checkpoint_dir,
                    resume=args.resume,
                )
            _write_new_json(args.output, report)
        elif args.command == "churn":
            if os.path.lexists(args.output):
                raise FileExistsError(args.output)
            _write_new_json(
                args.output,
                run_churn(args.repo, args.manifest),
            )
        elif args.command == "assemble":
            if args.kind == "matrix":
                if args.input or args.input_dir is None or args.evidence_id is None:
                    raise ValueError(
                        "matrix assembly requires --input-dir and --evidence-id only"
                    )
                assembled = assemble_matrix_report(
                    args.input_dir,
                    evidence_id=args.evidence_id,
                )
            else:
                if args.input_dir is not None or args.evidence_id is not None:
                    raise ValueError(
                        "--input-dir and --evidence-id belong only to matrix assembly"
                    )
                assembled = assemble_reports(
                    args.kind,
                    args.input,
                    args.mode,
                    manifest=args.manifest,
                )
            _write_new_json(
                args.output,
                assembled,
            )
        elif args.command == "paired":
            _write_new_json(
                args.output,
                paired_runs(
                    args.baseline_root,
                    args.final_root,
                    args.repo,
                    args.manifest,
                    pair_count=args.pairs,
                    operation_set=args.operation_set,
                ),
            )
        elif args.command == "decide":
            evidence = _load_json(args.input)
            normalized_kind = args.kind.replace("-", "_")
            if normalized_kind in {"ann", "exact_ann"} and not (
                args.reason or args.trigger_crossed
            ):
                if args.paired is not None or args.acceptance is not None:
                    raise ValueError("ANN decision does not accept service/watch inputs")
                decision = decide_ann(
                    evidence,
                    evidence_report_sha256=_sha256_path(args.input),
                )
            elif normalized_kind in {"ann", "exact_ann"}:
                if args.paired is not None or args.acceptance is not None:
                    raise ValueError("ANN decision does not accept service/watch inputs")
                validate_report_data(evidence)
                decision = make_decision(
                    "exact_ann",
                    implementation_commit=evidence["identity"][
                        "implementation_commit"
                    ],
                    production_tree=evidence["identity"]["production_tree"],
                    evidence_report_sha256=_sha256_path(args.input),
                    trigger_crossed=args.trigger_crossed,
                    reason_codes=args.reason,
                )
            else:
                if (
                    args.paired is None
                    or args.acceptance is None
                    or args.reason
                    or args.trigger_crossed
                ):
                    raise ValueError(
                        "service/watch decision requires paired and acceptance evidence"
                    )
                decision = decide_service_watch(
                    evidence,
                    _load_json(args.paired),
                    _load_json(args.acceptance),
                    evidence_report_sha256=_sha256_path(args.acceptance),
                )
            _write_new_json(args.output, decision)
        elif args.command == "validate":
            report = _load_json(args.report)
            if {"red", "green", "final_staged_tree"}.issubset(report):
                validate_tdd_record_data(report, staged_tree=args.staged_tree)
            else:
                validate_report_data(report, args.schema)
                if (
                    report.get("report_kind") == "benchmark"
                    and report.get("report_scope") == "performance"
                ):
                    validate_performance_registry_coverage(report, args.manifest)
        elif args.command == "compare":
            if (
                args.paired is None
                or args.churn is None
                or not args.require_churn
                or not args.require_scale_5k_10k
            ):
                raise ValueError(
                    "acceptance compare requires paired, churn, and both requirement flags"
                )
            comparison = compare_acceptance_reports(
                _load_json(args.baseline),
                _load_json(args.final),
                _load_json(args.paired),
                _load_json(args.churn),
                manifest=args.manifest,
                input_sha256={
                    "baseline": _sha256_path(args.baseline),
                    "final": _sha256_path(args.final),
                    "paired": _sha256_path(args.paired),
                    "churn": _sha256_path(args.churn),
                },
            )
            if args.output is None:
                sys.stdout.write(canonical_json(comparison))
            else:
                _write_new_json(args.output, comparison)
        elif args.command == "publish":
            publish_report(args.input, args.output, manifest=args.manifest)
        elif args.command == "tdd-red":
            _write_new_json(
                args.output,
                tdd_red_record(args.task, args.pre_change_commit, args.pytest_node),
            )
        elif args.command == "tdd-green":
            if args.pending is None or args.staged_tree is None:
                raise ValueError("tdd-green requires --pending and --staged-tree")
            _write_new_json(
                args.output,
                tdd_green_record(
                    _load_json(args.pending),
                    staged_tree=args.staged_tree,
                ),
            )
        elif args.command == "tdd-bootstrap":
            if not (
                args.red_log
                and args.red_exit_file
                and args.test_input_hashes
                and args.staged_tree
            ):
                raise ValueError(
                    "tdd-bootstrap requires RED log/exit/hashes and staged tree"
                )
            if args.red_exit_file.read_text(encoding="utf-8").strip() != "1":
                raise ValueError("bootstrap RED exit must be 1")
            hash_values = parse_hash_manifest(args.test_input_hashes)
            selectors = args.pytest_node or [
                path for path in hash_values if path.startswith("tests/test_")
            ]
            arguments = ["-q", *selectors]
            node_ids = _collect_node_ids(selectors)
            identity, verified_hashes = _test_identity(
                node_ids,
                arguments,
                file_hashes=hash_values,
                tree=args.staged_tree,
            )
            red_failed_nodes, red_assertions = _red_log_evidence(
                args.red_log.read_text(encoding="utf-8")
            )
            if not set(red_failed_nodes).issubset(node_ids):
                raise ValueError("bootstrap RED failed nodes differ from frozen collection")
            tree = _production_tree_for_commit(args.pre_change_commit)
            pending = {
                "schema_version": 1,
                "producer_version": "p6-benchmark-v1",
                "task": args.task,
                "pre_change_commit": validate_git_sha(args.pre_change_commit),
                "pre_change_production_tree": tree,
                "production_file_hashes": {
                    "scripts/p6_benchmark.py": _sha256_path(__file__)
                },
                "test_file_hashes": verified_hashes,
                "pytest": {"arguments": arguments, "node_ids": node_ids},
                "red": {
                    "exit_code": 1,
                    "failed_node_ids": red_failed_nodes,
                    "assertion_summaries": red_assertions,
                    "started_at_epoch_ms": 0,
                    "completed_at_epoch_ms": 0,
                    "test_identity_sha256": identity,
                },
            }
            _write_new_json(
                args.output,
                tdd_green_record(pending, staged_tree=args.staged_tree),
            )
        return 0
    except (FileExistsError, OSError, ValueError) as exc:
        print(f"p6-benchmark: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "__measure":
        raise SystemExit(_measurement_worker_main())
    if len(sys.argv) == 2 and sys.argv[1] == "__measure_resident":
        raise SystemExit(_measurement_resident_worker_main())
    raise SystemExit(main())
