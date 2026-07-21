from __future__ import annotations

from copy import deepcopy
import hashlib
import importlib.util
import json
import math
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
from typing import Any

import pytest
import yaml
from jsonschema import Draft202012Validator, ValidationError


ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = ROOT / "tests" / "fixtures" / "p6_contracts"
PERFORMANCE = ROOT / "tests" / "fixtures" / "p6_performance"
SCHEMAS = ROOT / "docs" / "benchmarks" / "p6" / "schemas"
HARNESS = ROOT / "scripts" / "p6_benchmark.py"
WORKFLOW = ROOT / ".github" / "workflows" / "p6-functional-matrix.yml"

REPORT_KEYS = [
    "schema_version",
    "health",
    "queryable",
    "queryability_evidence",
    "availability",
    "observation",
    "freshness",
    "coverage",
    "integrity",
    "vectors",
    "indexed_embedding",
    "configured_embedding",
    "embedding_config_match",
    "refresh",
    "writer",
    "diagnostics",
]
STATUS_CODES = {"repo_not_found", "status_failed"}
REFRESH_CODES = {
    "repo_not_found",
    "missing_index",
    "incompatible_manifest_schema",
    "incompatible_operational_schema",
    "incompatible_signal_schema",
    "index_busy",
    "authoritative_index_required",
    "inventory_incomplete",
    "workspace_changed",
    "refresh_failed",
}
HASH = "1" * 64
GIT = "1" * 40
ACTUAL_COMMIT = subprocess.check_output(
    ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True
).strip()
ACTUAL_TREE = subprocess.check_output(
    ["git", "-C", str(ROOT), "rev-parse", "HEAD:src/context_search_tool"],
    text=True,
).strip()
ACTUAL_ROOT_TREE = subprocess.check_output(
    ["git", "-C", str(ROOT), "rev-parse", "HEAD^{tree}"],
    text=True,
).strip()

OBSERVATION_KEYS = [
    "started_at_epoch_ms",
    "completed_at_epoch_ms",
    "inventory_status",
    "unscannable_subtree_count",
    "control_file_error_count",
    "change_token_kind",
    "limitations",
]
FRESHNESS_KEYS = [
    "status",
    "inspection_mode",
    "indexed_at_epoch_s",
    "age_seconds",
    "added",
    "changed",
    "deleted",
    "metadata_unchanged",
    "content_verified",
    "samples",
    "sample_limit",
    "sampled_total",
    "evidence_generation",
]
COVERAGE_KEYS = [
    "status",
    "evidence",
    "indexed_files",
    "coverage_skips",
    "pending_inspection",
    "pending_retry",
    "skip_counts",
    "skip_samples",
    "excluded_counts",
]
INTEGRITY_KEYS = ["status", "manifest", "sqlite", "graph", "graph_stale_reason", "vector"]
VECTOR_KEYS = [
    "generation",
    "eligible_chunks",
    "rows",
    "coverage_ratio",
    "coverage_evidence",
    "missing_ids",
    "orphan_ids",
    "dimensions",
]
EMBEDDING_KEYS = [
    "status",
    "provider",
    "model",
    "dimensions",
    "config_hash",
    "network_egress_capable",
    "network_egress_evidence",
]
REFRESH_KEYS = ["required", "kind", "reasons", "recommended_action"]
WRITER_KEYS = ["active", "state", "evidence"]
SKIP_COUNT_KEYS = [
    "too_large",
    "binary",
    "unreadable",
    "unsafe_path",
    "changed_during_read",
    "unsupported_encoding",
]
EXCLUDED_COUNT_KEYS = [
    "ignored",
    "internal",
    "default_directory",
    "config_excluded",
    "unsupported_language",
    "pruned_directory",
]
REFRESH_REASON_ORDER = [
    "source_changed",
    "path_inventory_changed",
    "coverage_changed",
    "index_config_changed",
    "embedding_config_changed",
    "topology_changed",
    "graph_stale",
    "manifest_upgrade",
    "integrity_failed",
    "inventory_incomplete",
]
DIAGNOSTIC_CODE_ORDER = [
    "legacy_manifest",
    "inventory_incomplete",
    "unscannable_subtree",
    "control_file_error",
    "writer_state_unknown",
    "inspection_interrupted",
    "verification_interrupted",
    "vector_payload_unverified",
    "manifest_identity_mismatch",
    "vector_identity_mismatch",
    "orphan_generation",
    "coverage_pending",
]
DEPENDENT_REASON_ORDER = [
    "content_candidate",
    "added_path",
    "deleted_path",
    "coverage_changed",
    "index_config_changed",
    "embedding_config_changed",
    "project_topology_changed",
    "path_inventory_changed",
    "schema_or_integrity_rebuild",
]


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _validator(name: str) -> Draft202012Validator:
    schema = _load(SCHEMAS / name)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _assert_closed_objects(value: Any) -> None:
    if isinstance(value, dict):
        if value.get("type") == "object" and "properties" in value:
            assert value.get("additionalProperties") is False
        elif value.get("type") == "object":
            assert "propertyNames" in value
            assert isinstance(value.get("additionalProperties"), (bool, dict))
        for child in value.values():
            _assert_closed_objects(child)
    elif isinstance(value, list):
        for child in value:
            _assert_closed_objects(child)


def _assert_keys(value: Any, keys: list[str]) -> dict[str, Any]:
    assert isinstance(value, dict)
    assert list(value) == keys
    return value


def _assert_nonnegative(value: Any, *, nullable: bool = False) -> None:
    if nullable and value is None:
        return
    assert type(value) is int and value >= 0


def _assert_relative_path(value: str) -> None:
    path = PurePosixPath(value)
    assert value == path.as_posix()
    assert value and not path.is_absolute() and ".." not in path.parts


def _assert_embedding_identity(value: Any) -> None:
    identity = _assert_keys(value, EMBEDDING_KEYS)
    assert identity["status"] in {"valid", "missing", "invalid", "not_inspected"}
    assert type(identity["network_egress_capable"]) is bool
    assert identity["network_egress_evidence"] in {
        "built_in_hash",
        "configured_network_provider",
        "unknown_provider",
        "index_missing",
        "config_missing",
        "config_invalid",
        "not_inspected",
    }
    if identity["status"] == "valid":
        assert all(identity[key] is not None for key in ("provider", "model", "dimensions", "config_hash"))
        assert type(identity["dimensions"]) is int and identity["dimensions"] > 0
        if identity["provider"] == "hash":
            assert identity["network_egress_capable"] is False
            assert identity["network_egress_evidence"] == "built_in_hash"
    else:
        assert all(identity[key] is None for key in ("provider", "model", "dimensions", "config_hash"))
        assert identity["network_egress_capable"] is True


def _assert_index_health_report(value: Any) -> None:
    report = _assert_keys(value, REPORT_KEYS)
    assert report["schema_version"] == 1
    assert report["health"] in {
        "missing",
        "incompatible",
        "corrupt",
        "stale",
        "degraded",
        "healthy_verified",
        "healthy_metadata",
    }
    assert type(report["queryable"]) is bool
    assert report["queryability_evidence"] in {
        "none",
        "committed_snapshot_quick",
        "committed_snapshot_verified",
        "unknown",
    }
    assert report["availability"] in {"missing", "present", "incompatible", "corrupt"}

    observation = _assert_keys(report["observation"], OBSERVATION_KEYS)
    assert observation["inventory_status"] in {"not_inspected", "complete", "incomplete"}
    for key in ("started_at_epoch_ms", "completed_at_epoch_ms", "unscannable_subtree_count", "control_file_error_count"):
        _assert_nonnegative(observation[key], nullable=True)
    if observation["started_at_epoch_ms"] is not None:
        assert observation["completed_at_epoch_ms"] >= observation["started_at_epoch_ms"]
    assert observation["change_token_kind"] in {
        None,
        "mtime_ns+ctime_ns",
        "mtime_ns",
        "platform_specific",
    }
    assert observation["limitations"] is None or (
        isinstance(observation["limitations"], list)
        and len(observation["limitations"]) == len(set(observation["limitations"]))
        and set(observation["limitations"]) <= {
            "metadata_not_content_proof",
            "vector_payload_content_not_verified",
        }
    )

    freshness = _assert_keys(report["freshness"], FRESHNESS_KEYS)
    assert freshness["status"] in {"unknown", "stale", "metadata_fresh", "verified_fresh"}
    assert freshness["inspection_mode"] in {"none", "quick", "verified"}
    for key in ("indexed_at_epoch_s", "age_seconds", "added", "changed", "deleted", "metadata_unchanged", "content_verified", "sampled_total"):
        _assert_nonnegative(freshness[key], nullable=True)
    assert freshness["sample_limit"] == 20
    assert freshness["evidence_generation"] is None or (
        isinstance(freshness["evidence_generation"], str)
        and freshness["evidence_generation"]
    )
    if freshness["samples"] is not None:
        assert isinstance(freshness["samples"], list)
        assert len(freshness["samples"]) <= freshness["sample_limit"]
        assert freshness["sampled_total"] >= len(freshness["samples"])
        for sample in freshness["samples"]:
            _assert_keys(sample, ["category", "path", "reason"])
            assert sample["category"] in {"added", "changed", "deleted", "metadata_only", "pending_inspection"}
            _assert_relative_path(sample["path"])
            assert sample["reason"] in set(REFRESH_REASON_ORDER)
        category_order = ["added", "changed", "deleted", "metadata_only", "pending_inspection"]
        assert freshness["samples"] == sorted(
            freshness["samples"],
            key=lambda item: (category_order.index(item["category"]), item["path"]),
        )

    coverage = _assert_keys(report["coverage"], COVERAGE_KEYS)
    assert coverage["status"] in {"unknown", "complete", "degraded"}
    assert coverage["evidence"] in {"not_inspected", "ready_snapshot", "verified_workspace"}
    for key in ("indexed_files", "coverage_skips", "pending_inspection", "pending_retry"):
        _assert_nonnegative(coverage[key], nullable=True)
    if coverage["skip_counts"] is not None:
        _assert_keys(coverage["skip_counts"], SKIP_COUNT_KEYS)
        for count in coverage["skip_counts"].values():
            _assert_nonnegative(count)
        assert coverage["coverage_skips"] == sum(coverage["skip_counts"].values())
    if coverage["excluded_counts"] is not None:
        _assert_keys(coverage["excluded_counts"], EXCLUDED_COUNT_KEYS)
        for count in coverage["excluded_counts"].values():
            _assert_nonnegative(count)
    if coverage["skip_samples"] is not None:
        assert isinstance(coverage["skip_samples"], list)
        assert len(coverage["skip_samples"]) <= freshness["sample_limit"]
        assert len(coverage["skip_samples"]) <= coverage["coverage_skips"]
        for sample in coverage["skip_samples"]:
            _assert_keys(sample, ["path", "reason", "retryable"])
            _assert_relative_path(sample["path"])
            assert sample["reason"] in set(SKIP_COUNT_KEYS)
            assert type(sample["retryable"]) is bool
        assert coverage["skip_samples"] == sorted(
            coverage["skip_samples"], key=lambda item: (SKIP_COUNT_KEYS.index(item["reason"]), item["path"])
        )

    integrity = _assert_keys(report["integrity"], INTEGRITY_KEYS)
    assert integrity["status"] in {"unchecked", "valid_quick", "valid_verified", "invalid"}
    assert integrity["manifest"] in {"missing", "not_inspected", "valid", "incompatible", "invalid"}
    assert integrity["sqlite"] in {"missing", "not_inspected", "valid_quick", "valid_verified", "incompatible", "invalid"}
    assert integrity["graph"] in {"missing", "not_inspected", "ready", "stale", "unfinished", "incompatible", "invalid"}
    assert integrity["vector"] in {"missing", "not_inspected", "valid_identity_and_size", "valid_exact", "incompatible", "invalid"}
    assert integrity["graph_stale_reason"] is None or isinstance(integrity["graph_stale_reason"], str)

    vectors = _assert_keys(report["vectors"], VECTOR_KEYS)
    assert vectors["coverage_evidence"] in {"not_inspected", "count_only", "exact_ids"}
    for key in ("eligible_chunks", "rows", "dimensions"):
        _assert_nonnegative(vectors[key], nullable=True)
    for key in ("missing_ids", "orphan_ids"):
        assert vectors[key] is None or (
            isinstance(vectors[key], list)
            and len(vectors[key]) == len(set(vectors[key]))
            and all(isinstance(item, str) and item for item in vectors[key])
        )
    assert vectors["coverage_ratio"] is None or 0 <= vectors["coverage_ratio"] <= 1
    assert vectors["generation"] is None or isinstance(vectors["generation"], str)

    _assert_embedding_identity(report["indexed_embedding"])
    _assert_embedding_identity(report["configured_embedding"])
    if report["indexed_embedding"]["status"] != "valid" or report["configured_embedding"]["status"] != "valid":
        assert report["embedding_config_match"] is None
    else:
        assert type(report["embedding_config_match"]) is bool
        if report["embedding_config_match"]:
            assert all(
                report["indexed_embedding"][key]
                == report["configured_embedding"][key]
                for key in ("provider", "model", "dimensions", "config_hash")
            )

    refresh = _assert_keys(report["refresh"], REFRESH_KEYS)
    assert type(refresh["required"]) is bool
    assert refresh["kind"] in {"none", "quick", "authoritative"}
    assert len(refresh["reasons"]) == len(set(refresh["reasons"]))
    assert set(refresh["reasons"]) <= set(REFRESH_REASON_ORDER)
    assert refresh["reasons"] == sorted(refresh["reasons"], key=REFRESH_REASON_ORDER.index)
    assert refresh["recommended_action"] in {
        "query",
        "refresh",
        "index",
        "retry_inspection",
        "use_compatible_version",
    }

    writer = _assert_keys(report["writer"], WRITER_KEYS)
    assert writer["active"] is None or type(writer["active"]) is bool
    assert writer["state"] in {"idle", "active", "unknown", "not_inspected"}
    assert writer["evidence"] in {"lock_probe", "lock_probe_unavailable", "generation_drift", "not_inspected"}

    if report["diagnostics"] is not None:
        assert isinstance(report["diagnostics"], list)
        for diagnostic in report["diagnostics"]:
            assert list(diagnostic) in (["code", "scope"], ["code", "scope", "path"])
            assert diagnostic["code"] in set(DIAGNOSTIC_CODE_ORDER)
            assert re.fullmatch(r"[a-z][a-z0-9_]*", diagnostic["scope"])
            if diagnostic.get("path") is not None:
                _assert_relative_path(diagnostic["path"])
        assert report["diagnostics"] == sorted(
            report["diagnostics"],
            key=lambda item: (DIAGNOSTIC_CODE_ORDER.index(item["code"]), item.get("path") or ""),
        )

    if freshness["inspection_mode"] == "none":
        assert observation["inventory_status"] == "not_inspected"
        assert all(
            observation[key] is None
            for key in OBSERVATION_KEYS
            if key != "inventory_status"
        )
        assert all(
            freshness[key] is None
            for key in (
                "indexed_at_epoch_s",
                "age_seconds",
                "added",
                "changed",
                "deleted",
                "metadata_unchanged",
                "content_verified",
                "samples",
                "sampled_total",
                "evidence_generation",
            )
        )
        assert coverage["status"] == "unknown"
        assert coverage["evidence"] == "not_inspected"
        assert all(
            coverage[key] is None
            for key in COVERAGE_KEYS
            if key not in {"status", "evidence"}
        )
        assert vectors["coverage_evidence"] == "not_inspected"
        assert all(
            vectors[key] is None
            for key in VECTOR_KEYS
            if key != "coverage_evidence"
        )
        assert freshness["samples"] is None
        assert report["diagnostics"] is None
        assert writer == {
            "active": None,
            "state": "not_inspected",
            "evidence": "not_inspected",
        }
    if report["health"] in {"missing", "incompatible", "corrupt"}:
        assert report["queryable"] is False
    expected_availability = {
        "missing": "missing",
        "incompatible": "incompatible",
        "corrupt": "corrupt",
    }.get(report["health"], "present")
    assert report["availability"] == expected_availability
    if report["health"] == "healthy_metadata":
        assert freshness["status"] == "metadata_fresh" and integrity["status"] == "valid_quick"
    if report["health"] == "healthy_verified":
        assert freshness["status"] == "verified_fresh" and integrity["status"] == "valid_verified"


def _assert_refresh_success(value: Any) -> None:
    envelope = _assert_keys(
        value,
        ["schema_version", "ok", "repo", "summary", "embedding", "index_health"],
    )
    assert envelope["schema_version"] == 1 and envelope["ok"] is True
    assert isinstance(envelope["repo"], str) and envelope["repo"]
    summary = _assert_keys(
        envelope["summary"],
        ["operation", "outcome", "verification", "observation_generation", "files", "chunks", "work"],
    )
    assert summary["operation"] == "quick_refresh"
    assert summary["outcome"] == "ready"
    assert summary["verification"] == "metadata"
    assert isinstance(summary["observation_generation"], str)
    files = _assert_keys(
        summary["files"],
        [
            "direct_dirty",
            "content_changed",
            "metadata_only",
            "dependent_rebuild",
            "dependent_rebuilds",
            "deleted",
            "coverage_skips",
            "parsed",
        ],
    )
    for key, count in files.items():
        if key != "dependent_rebuilds":
            _assert_nonnegative(count)
    assert isinstance(files["dependent_rebuilds"], list)
    assert len({item["reason"] for item in files["dependent_rebuilds"]}) == len(files["dependent_rebuilds"])
    for item in files["dependent_rebuilds"]:
        _assert_keys(item, ["reason", "files"])
        assert item["reason"] in set(DEPENDENT_REASON_ORDER)
        _assert_nonnegative(item["files"])
    assert files["dependent_rebuilds"] == sorted(
        files["dependent_rebuilds"], key=lambda item: DEPENDENT_REASON_ORDER.index(item["reason"])
    )
    assert files["dependent_rebuild"] == sum(item["files"] for item in files["dependent_rebuilds"])

    chunks = _assert_keys(summary["chunks"], ["embedded"])
    _assert_nonnegative(chunks["embedded"])
    work = _assert_keys(
        summary["work"],
        ["inventory", "source", "path_index", "graph", "vector", "maintenance"],
    )
    work_shapes = {
        "inventory": ["passes", "entries", "errors", "retryable_skip_attempts"],
        "source": ["bytes_read", "bytes_hashed"],
        "path_index": ["builds", "paths_canonicalized"],
        "graph": ["relations_scanned", "relations_resolved", "association_inputs", "association_writes"],
        "vector": [
            "bytes_read",
            "bytes_copied",
            "bytes_written",
            "bytes_hashed",
            "payload_passes",
            "prior_payload_passes",
            "prepared_payload_passes",
            "generations_before",
            "generations_after",
            "descriptor_action",
        ],
        "maintenance": [
            "tombstones_before",
            "tombstones_purged",
            "tombstones_after",
            "sqlite_pages_before",
            "sqlite_pages_after",
            "sqlite_freelist_before",
            "sqlite_freelist_after",
        ],
    }
    for group, keys in work_shapes.items():
        values = _assert_keys(work[group], keys)
        for key, count in values.items():
            if key != "descriptor_action":
                _assert_nonnegative(count)
    assert work["inventory"]["passes"] == 2
    assert work["vector"]["descriptor_action"] in {"reused", "published"}
    assert work["vector"]["payload_passes"] == (
        work["vector"]["prior_payload_passes"]
        + work["vector"]["prepared_payload_passes"]
    )

    embedding = _assert_keys(
        envelope["embedding"],
        ["indexed_before", "configured", "network_egress_performed", "embedded_chunks"],
    )
    _assert_embedding_identity(embedding["indexed_before"])
    _assert_embedding_identity(embedding["configured"])
    assert embedding["indexed_before"]["status"] == "valid"
    assert embedding["configured"]["status"] == "valid"
    assert all(
        embedding["indexed_before"][key] == embedding["configured"][key]
        for key in ("provider", "model", "dimensions", "config_hash")
    )
    assert type(embedding["network_egress_performed"]) is bool
    if embedding["configured"]["provider"] == "hash":
        assert embedding["network_egress_performed"] is False
    _assert_nonnegative(embedding["embedded_chunks"])
    assert embedding["embedded_chunks"] == chunks["embedded"]
    _assert_index_health_report(envelope["index_health"])
    assert summary["observation_generation"] == envelope["index_health"]["freshness"]["evidence_generation"]


def _benchmark_report() -> dict[str, Any]:
    counter_names = _load(
        SCHEMAS / "benchmark-report-v1.json"
    )["properties"]["samples"]["items"]["properties"]["work"]["required"]
    timing_names = _load(
        SCHEMAS / "benchmark-report-v1.json"
    )["properties"]["samples"]["items"]["properties"]["stage_timings_ms"]["required"]
    timings = {name: 0.0 for name in timing_names}
    timings["end_to_end"] = 10.0
    return {
        "schema_version": 1,
        "report_kind": "benchmark",
        "report_scope": "tier",
        "mode": "baseline",
        "identity": {
            "implementation_commit": ACTUAL_COMMIT,
            "production_tree": ACTUAL_TREE,
            "harness_sha256": HASH,
            "workload_sha256": HASH,
            "dirty_production_source": False,
        },
        "environment": {
            "python": "3.13.12",
            "cst": "0.1.0",
            "sqlite": "3.51.2",
            "numpy": "2.3.4",
            "os": "macos",
            "architecture": "arm64",
            "cpu_count": 14,
            "memory_bytes": 36 * 1024**3,
            "local_disk_class": "ssd",
            "power_state": "external",
            "governor_state": "not_applicable",
            "swap_before_bytes": 0,
            "swap_after_bytes": 0,
            "background_cpu_percent": 1.0,
        },
        "workload": {
            "schema_version": 1,
            "generator_version": "p6-generator-v1",
            "generator_sha256": HASH,
            "seed": 20260718,
            "tier": "smoke",
            "fingerprint_sha256": HASH,
        },
        "operation": {
            "operation_id": "query",
            "case_id": "lexical_high",
            "case_family": "query",
            "measurement_state": "cli_process_cold",
            "planner_enabled": False,
            "embedding_provider": "hash",
            "embedding_model": "hash-v1",
            "embedding_dimensions": 384,
            "outcome": "supported",
        },
        "calibration": {
            "valid": True,
            "sha256_bytes": 512 * 1024**2,
            "sha256_mib_per_s": 900.0,
            "numpy_rows": 80000,
            "numpy_dimensions": 384,
            "numpy_dot_ms": 25.0,
            "sqlite_rows": 20000,
            "sqlite_ms": 10.0,
            "within_pair_percent": 1.0,
        },
        "samples": [
            {
                "sample_id": "sample-01",
                "pair_id": None,
                "duration_ms": 10.0,
                "stage_timings_ms": timings,
                "work": {name: 0 for name in counter_names},
                "rss": {
                    "process_start_bytes": 1,
                    "peak_bytes": 2,
                    "current_bytes": None,
                    "empty_harness_peak_bytes": 1,
                    "extra_peak_bytes": 1,
                },
                "disk": {
                    "sqlite_bytes": 1,
                    "vector_payload_bytes": 1,
                    "vector_id_bytes": 1,
                    "descriptor_bytes": 1,
                    "manifest_bytes": 1,
                    "total_bytes": 5,
                },
            }
        ],
        "summary": {
            "sample_count": 1,
            "median_ms": 10.0,
            "p50_ms": 10.0,
            "p95_ms": 10.0,
            "max_ms": 10.0,
            "cv_population": 0.0,
            "units": {
                "duration": "ms",
                "bytes": "bytes",
                "rss": "bytes",
                "throughput": "MiB/s",
                "ratio": "ratio",
                "count": "count",
            },
        },
        "validity": {"valid": True, "reasons": [], "child_processes": 0},
    }


def _performance_report(*, mode: str = "baseline") -> dict[str, Any]:
    tier = _benchmark_report()
    tier["mode"] = mode
    return {
        "schema_version": 1,
        "report_kind": "benchmark",
        "report_scope": "performance",
        "mode": mode,
        "identity": deepcopy(tier["identity"]),
        "case_reports": [
            {
                key: deepcopy(tier[key])
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
        ],
    }


def _entry_record(module: Any) -> dict[str, Any]:
    lineage = []
    for line in subprocess.check_output(
        ["git", "-C", str(ROOT), "log", "-3", "--format=%H %s", ACTUAL_COMMIT],
        text=True,
    ).splitlines():
        commit, subject = line.split(" ", 1)
        lineage.append({"commit": commit, "subject": subject})
    return {
        "schema_version": 1,
        "entry_commit": ACTUAL_COMMIT,
        "review_commit": ACTUAL_COMMIT,
        "production_tree": ACTUAL_TREE,
        "dependency_sha256": HASH,
        "runtime_sha256": HASH,
        "junit": {
            "sha256": HASH,
            "passed": 2625,
            "skipped": 9,
            "xfail": 0,
            "errors": 0,
            "skip_node_ids": list(module.FROZEN_ENTRY_SKIP_NODE_IDS),
        },
        "quality": {
            "p5": HASH,
            "p4": HASH,
            "p2": HASH,
            "ci": HASH,
            "pinned_real_a": HASH,
            "pinned_real_b": HASH,
            "pinned_real_byte_identical": True,
        },
        "lineage": lineage,
    }


@pytest.mark.parametrize(
    "name",
    [
        "benchmark-report-v1.json",
        "acceptance-report-v1.json",
        "decision-record-v1.json",
        "matrix-summary-v1.json",
        "matrix-report-v1.json",
        "entry-record-v1.json",
        "environment-report-v1.json",
        "quality-report-v1.json",
        "tdd-record-v1.json",
    ],
)
def test_report_schema_family_is_draft_2020_12_and_closed(name: str) -> None:
    schema = _load(SCHEMAS / name)
    Draft202012Validator.check_schema(schema)
    _assert_closed_objects(schema)


def test_benchmark_schema_requires_raw_samples_identity_units_and_work() -> None:
    validator = _validator("benchmark-report-v1.json")
    report = _benchmark_report()
    validator.validate(report)
    for mutation in (
        lambda value: value["samples"].clear(),
        lambda value: value["identity"].pop("production_tree"),
        lambda value: value["summary"]["units"].__setitem__("duration", "seconds"),
        lambda value: value["samples"][0].pop("work"),
        lambda value: value["identity"].__setitem__("dirty_production_source", True),
    ):
        candidate = deepcopy(report)
        mutation(candidate)
        with pytest.raises(ValidationError):
            validator.validate(candidate)


@pytest.mark.parametrize(
    ("field", "invalid"),
    [
        ("disk_page_ratio", 1.250001),
        ("tombstones_within_threshold", False),
        ("query_p95_drift_ratio", 0.100001),
        ("generation_count_after_failure", 3),
    ],
)
def test_final_churn_gate_fails_independently(field: str, invalid: Any) -> None:
    validator = _validator("benchmark-report-v1.json")
    report = _performance_report(mode="final")
    report["churn"] = {
        "steps": 100,
        "disk_page_ratio": 1.25,
        "tombstones_within_threshold": True,
        "query_p95_drift_ratio": 0.10,
        "generation_count_after_failure": 2,
    }
    validator.validate(report)
    report["churn"][field] = invalid
    with pytest.raises(ValidationError):
        validator.validate(report)


def test_final_single_tier_may_omit_churn_but_churn_scope_must_be_final() -> None:
    validator = _validator("benchmark-report-v1.json")
    report = _performance_report()
    validator.validate(report)
    report["mode"] = "final"
    validator.validate(report)
    report["report_scope"] = "churn"
    report.pop("case_reports")
    report["workload"] = deepcopy(_benchmark_report()["workload"])
    report["churn"] = {
        "steps": 100,
        "disk_page_ratio": 1.0,
        "tombstones_within_threshold": True,
        "query_p95_drift_ratio": 0.0,
        "generation_count_after_failure": 1,
    }
    validator.validate(report)
    report["mode"] = "baseline"
    with pytest.raises(ValidationError):
        validator.validate(report)


def test_standalone_churn_report_is_closed_and_assembles_without_fake_case(
    tmp_path: Path,
) -> None:
    module = _load_harness()
    tier = _benchmark_report()
    tier["mode"] = "final"
    churn = {
        "schema_version": 1,
        "report_kind": "benchmark",
        "report_scope": "churn",
        "mode": "final",
        "identity": deepcopy(tier["identity"]),
        "workload": deepcopy(tier["workload"]),
        "churn": {
            "steps": 100,
            "disk_page_ratio": 1.0,
            "tombstones_within_threshold": True,
            "query_p95_drift_ratio": 0.0,
            "generation_count_after_failure": 1,
        },
    }

    module.validate_report_data(churn, "benchmark-report-v1.json")
    churn_path = tmp_path / "churn.json"
    churn_path.write_text(json.dumps(churn), encoding="utf-8")
    tier_paths = []
    for tier_name in ("smoke", "large", "scale-5k", "scale-10k"):
        candidate = deepcopy(tier)
        candidate["workload"]["tier"] = tier_name
        path = tmp_path / f"{tier_name}.json"
        path.write_text(json.dumps(candidate), encoding="utf-8")
        tier_paths.append(path)

    single = module.assemble_reports(
        "performance",
        [tier_paths[0]],
        "final",
    )
    assert "churn" not in single
    with pytest.raises(ValueError, match="requires one churn"):
        module.assemble_reports("performance", tier_paths, "final")

    combined = module.assemble_reports(
        "performance",
        [*tier_paths, churn_path],
        "final",
    )

    assert combined["churn"] == churn["churn"]
    assert len(combined["case_reports"]) == 4
    assert all(
        case["operation"] == tier["operation"]
        for case in combined["case_reports"]
    )


def test_matrix_assembler_requires_exact_unique_12_cell_cross_product(
    tmp_path: Path,
) -> None:
    module = _load_harness()
    input_dir = tmp_path / "cells"
    evidence_id = f"p6-acceptance-{ACTUAL_COMMIT}"
    workflow_sha256 = hashlib.sha256(WORKFLOW.read_bytes()).hexdigest()
    lock_sha256 = hashlib.sha256((ROOT / "uv.lock").read_bytes()).hexdigest()
    for os_name in ("ubuntu-latest", "macos-latest", "windows-latest"):
        for python_version in ("3.11", "3.12", "3.13", "3.14"):
            cell = input_dir / f"{os_name}-py{python_version}"
            cell.mkdir(parents=True)
            junit = b'<testsuite tests="1"><testcase name="ok"/></testsuite>\n'
            (cell / "junit.xml").write_bytes(junit)
            summary = {
                "schema_version": 1,
                "implementation_commit": ACTUAL_COMMIT,
                "production_tree": ACTUAL_TREE,
                "workflow_sha256": workflow_sha256,
                "os": os_name,
                "architecture": "arm64" if os_name == "macos-latest" else "x86_64",
                "python_version": python_version,
                "dependency_lock_sha256": lock_sha256,
                "tests": {
                    "passed": 1,
                    "failed": 0,
                    "errors": 0,
                    "skipped": 0,
                    "xfail": 0,
                    "skip_node_ids": [],
                },
                "junit_sha256": hashlib.sha256(junit).hexdigest(),
                "run": {
                    "evidence_id": evidence_id,
                    "run_id": "123",
                    "run_attempt": 1,
                },
                "conclusion": "success",
            }
            (cell / "matrix-summary-v1.json").write_text(
                json.dumps(summary),
                encoding="utf-8",
            )

    report = module.assemble_matrix_report(input_dir, evidence_id=evidence_id)

    module.validate_report_data(report, "matrix-report-v1.json")
    assert report["report_kind"] == "matrix"
    assert len(report["cells"]) == 12
    assert {
        (cell["os"], cell["python_version"])
        for cell in report["cells"]
    } == {
        (os_name, python_version)
        for os_name in ("ubuntu-latest", "macos-latest", "windows-latest")
        for python_version in ("3.11", "3.12", "3.13", "3.14")
    }

    missing = next(input_dir.rglob("matrix-summary-v1.json"))
    missing.unlink()
    with pytest.raises(ValueError, match="exactly 12"):
        module.assemble_matrix_report(input_dir, evidence_id=evidence_id)


def test_final_batch_operation_sets_expand_to_complete_tier_registries() -> None:
    module = _load_harness()
    contract = _load(PERFORMANCE / "workload_manifest.json")
    expected = {
        ("smoke", "all-smoke"): 38,
        ("large", "all-large"): 38,
        ("scale-5k", "all-scale"): 9,
        ("scale-10k", "all-scale"): 9,
        ("stress", "capacity-informational"): 5,
    }
    for (tier, operation_set), count in expected.items():
        requests = module._benchmark_set_requests(contract, tier, operation_set)
        assert len(requests) == count
        assert len(
            {
                (
                    request["operation"],
                    request["case_id"],
                    request["measurement_state"],
                )
                for request in requests
            }
        ) == count

    with pytest.raises(ValueError, match="does not match"):
        module._benchmark_set_requests(contract, "large", "all-scale")


def test_final_environment_uses_final_benchmark_identity_and_raw_lock_hash(
    tmp_path: Path,
) -> None:
    module = _load_harness()
    entry = _entry_record(module)
    parent = subprocess.check_output(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD^"],
        text=True,
    ).strip()
    entry["entry_commit"] = parent
    entry["review_commit"] = parent
    entry["production_tree"] = subprocess.check_output(
        ["git", "-C", str(ROOT), "rev-parse", f"{parent}:src/context_search_tool"],
        text=True,
    ).strip()
    benchmark = _performance_report(mode="final")
    entry_path = tmp_path / "entry.json"
    benchmark_path = tmp_path / "benchmark.json"
    entry_path.write_text(json.dumps(entry), encoding="utf-8")
    benchmark_path.write_text(json.dumps(benchmark), encoding="utf-8")

    report = module.assemble_reports(
        "environment",
        [entry_path, benchmark_path],
        "final",
    )

    assert report["implementation_commit"] == benchmark["identity"][
        "implementation_commit"
    ]
    assert report["production_tree"] == benchmark["identity"]["production_tree"]
    assert report["environment"]["dependency_lock_sha256"] == hashlib.sha256(
        (ROOT / "uv.lock").read_bytes()
    ).hexdigest()
    with pytest.raises(ValueError, match="mode differs"):
        module.assemble_reports(
            "environment",
            [entry_path, benchmark_path],
            "baseline",
        )


def test_quality_assembler_emits_only_closed_aggregate_and_tdd_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_harness()
    profiles = {
        "final-p5.json": ("p5_language_graphs", 12),
        "final-p4.json": ("p4_exploration", 4),
        "final-p2.json": ("p2_context_pack", 5),
        "final-ci.json": ("ci", 8),
    }
    inputs = []
    for name, (profile, passed) in profiles.items():
        path = tmp_path / name
        path.write_text(
            json.dumps(
                {
                    "profile": profile,
                    "aggregate": {"selected": passed, "passed": passed},
                }
            ),
            encoding="utf-8",
        )
        inputs.append(path)
    for name in ("final-real-a.json", "final-real-b.json"):
        path = tmp_path / name
        path.write_text(json.dumps({"aggregate": {"passed": 2}}), encoding="utf-8")
        inputs.append(path)
    full = tmp_path / "final-full.xml"
    full.write_text("<testsuite/>", encoding="utf-8")
    inputs.append(full)
    for task in range(1, 11):
        path = tmp_path / f"tdd-task-{task}.json"
        path.write_text(
            json.dumps(
                {
                    "task": task,
                    "pre_change_commit": GIT,
                    "pre_change_production_tree": GIT,
                    "final_staged_tree": GIT,
                    "red": {
                        "failed_node_ids": [f"tests/test_task_{task}.py::test_red"],
                        "test_identity_sha256": HASH,
                    },
                    "green": {"passed": task},
                }
            ),
            encoding="utf-8",
        )
        inputs.append(path)

    monkeypatch.setattr(module, "_validate_entry_quality", lambda *_args: None)
    monkeypatch.setattr(module, "_validate_pinned_real", lambda *_args: None)
    monkeypatch.setattr(module, "validate_tdd_record_data", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        module,
        "parse_junit",
        lambda _path: {
            "sha256": HASH,
            "passed": 2835,
            "skipped": 9,
            "xfail": 0,
            "errors": 0,
            "failed": 0,
            "skip_node_ids": list(module.FROZEN_ENTRY_SKIP_NODE_IDS),
        },
    )
    monkeypatch.setattr(
        module,
        "_git_identity",
        lambda _root=module.ROOT: (ACTUAL_COMMIT, ACTUAL_TREE, False),
    )

    report = module.assemble_quality_report(inputs)

    module.validate_report_data(report, "quality-report-v1.json")
    assert report["full_suite"]["passed"] == 2835
    assert report["profiles"]["p5_language_graphs"] == {
        "passed": 12,
        "selected": 12,
        "trace_coverage": 1,
    }
    assert [record["task"] for record in report["tdd"]] == list(range(1, 11))
    assert "failed_node_ids" not in json.dumps(report)


def _walk(value: Any, path: tuple[str, ...] = ()) -> None:
    forbidden_keys = {
        "source_body",
        "vector_values",
        "environment",
        "env",
        "api_key",
        "credential",
        "headers",
        "response_body",
        "process_command_line",
        "provider_url",
    }
    if isinstance(value, dict):
        for key, child in value.items():
            assert key not in forbidden_keys
            _walk(child, (*path, key))
    elif isinstance(value, list):
        for child in value:
            _walk(child, path)
    elif isinstance(value, str):
        assert not value.startswith(("/", "\\", "file://"))
        assert not re.search(r"[A-Za-z]:[\\/]", value)
        assert "://" not in value
        assert not re.search(r"(?i)(api[_-]?key|bearer|password|secret)=", value)
    elif path and path[-1] in {"vector", "vectors", "vector_values"}:
        assert not isinstance(value, float)
    elif isinstance(value, float):
        assert math.isfinite(value)


def test_committed_fixtures_are_private_and_finite() -> None:
    for root in (CONTRACTS, PERFORMANCE):
        for path in sorted(root.glob("*.json")):
            value = _load(path)
            _walk(value)


def test_decision_records_are_closed_and_do_not_authorize_implementation() -> None:
    validator = _validator("decision-record-v1.json")
    exact = {
        "schema_version": 1,
        "decision_kind": "exact_ann",
        "implementation_commit": GIT,
        "production_tree": GIT,
        "decision": "retained",
        "trigger_crossed": False,
        "evidence_report_sha256": HASH,
        "reason_codes": ["semantic_within_budget", "rss_within_budget"],
    }
    service = {
        "schema_version": 1,
        "decision_kind": "service_watch",
        "implementation_commit": GIT,
        "production_tree": GIT,
        "decision": "deferred",
        "evidence_report_sha256": HASH,
        "reason_codes": ["load_not_dominant"],
    }
    validator.validate(exact)
    validator.validate(service)
    exact["implementation_authorized"] = True
    with pytest.raises(ValidationError):
        validator.validate(exact)


def test_ann_decision_is_derived_from_same_sample_stage_and_rss_evidence() -> None:
    module = _load_harness()
    report = _benchmark_report()
    report["mode"] = "final"
    report["workload"]["tier"] = "large"
    report["operation"].update(
        {
            "operation_id": "query",
            "case_id": "semantic_high",
            "case_family": "query",
            "measurement_state": "mcp_resident_warm",
            "outcome": "supported",
        }
    )
    sample = report["samples"][0]
    sample["duration_ms"] = 500.0
    sample["stage_timings_ms"]["end_to_end"] = 500.0
    sample["stage_timings_ms"]["semantic"] = 200.0
    report["summary"].update(
        {
            "median_ms": 500.0,
            "p50_ms": 500.0,
            "p95_ms": 500.0,
            "max_ms": 500.0,
        }
    )

    retained = module.decide_ann(report, evidence_report_sha256=HASH)
    assert retained["decision"] == "retained"
    assert retained["reason_codes"] == [
        "semantic_within_budget",
        "rss_within_budget",
        "semantic_dominant",
    ]

    sample["stage_timings_ms"]["semantic"] = 400.0
    triggered = module.decide_ann(report, evidence_report_sha256=HASH)
    assert triggered["decision"] == "prototype_requires_amendment"
    assert triggered["trigger_crossed"] is True


def test_service_watch_decision_uses_per_sample_load_counterfactual_and_closed_gates() -> None:
    module = _load_harness()
    performance = _performance_report(mode="final")
    identity = performance["identity"]
    operation = "query_planner_off"
    samples = []
    for pair_id, side in module.alternating_pairs(30):
        order_index = 1 if not any(
            sample["pair_id"] == pair_id for sample in samples[-1:]
        ) else 2
        samples.append(
            {
                "pair_id": pair_id,
                "order_index": order_index,
                "side": side,
                "operation_id": operation,
                "case_id": "planner_off_ordinary",
                "repository_fingerprint_sha256": HASH,
                "outcome": "supported",
                "duration_ms": 1000.0,
                "immutable_state_load_ms": 500.0,
                "rss": {"extra_peak_bytes": 1},
                "vector_payload_bytes": 1,
                "product_subprocesses": 0,
            }
        )
    calibration = {
        "valid": True,
        "sha256_bytes": 536870912,
        "sha256_mib_per_s": 100.0,
        "numpy_rows": 80000,
        "numpy_dimensions": 384,
        "numpy_dot_ms": 10.0,
        "sqlite_rows": 20000,
        "sqlite_ms": 5.0,
        "within_pair_percent": 0.0,
    }
    paired = {
        "schema_version": 1,
        "kind": "paired",
        "operation_set": "protected_small_entry_comparable",
        "pair_count": 30,
        "workload": {
            "manifest_sha256": HASH,
            "generator_version": "p6-generator-v1",
            "generator_sha256": HASH,
            "seed": 20260718,
            "tier": "smoke",
            "pristine_fingerprint_sha256": HASH,
        },
        "harness_sha256": HASH,
        "implementations": {
            "baseline": {
                "implementation_commit": GIT,
                "production_tree": GIT,
            },
            "final": {
                "implementation_commit": identity["implementation_commit"],
                "production_tree": identity["production_tree"],
            },
        },
        "calibrations": {
            "baseline": calibration,
            "final": calibration,
            "maximum_drift_percent": 0.0,
            "within_ten_percent": True,
        },
        "protected_operation_ids": [operation],
        "samples": samples,
        "summaries": module._paired_summaries(samples, [operation]),
    }
    acceptance = {
        "schema_version": 1,
        "report_kind": "acceptance",
        "implementation_commit": identity["implementation_commit"],
        "production_tree": identity["production_tree"],
        "inputs": {
            "baseline": HASH,
            "final": HASH,
            "paired": HASH,
            "churn": HASH,
        },
        "gates": {
            "registry_coverage": True,
            "absolute_large_budgets": True,
            "scale_budgets": True,
            "churn": True,
            "protected_regression": True,
        },
        "conclusion": "success",
    }

    eligible = module.decide_service_watch(
        performance,
        paired,
        acceptance,
        evidence_report_sha256=HASH,
    )
    assert eligible["decision"] == "eligible_for_separate_design"
    assert eligible["reason_codes"] == ["eligibility_met"]

    for sample in paired["samples"]:
        sample["immutable_state_load_ms"] = 100.0
    paired["summaries"] = module._paired_summaries(samples, [operation])
    deferred = module.decide_service_watch(
        performance,
        paired,
        acceptance,
        evidence_report_sha256=HASH,
    )
    assert deferred["decision"] == "deferred"
    assert set(deferred["reason_codes"]) == {
        "load_not_dominant",
        "counterfactual_insufficient",
    }


def test_absolute_and_scale_acceptance_gates_reject_forbidden_status_reads() -> None:
    module = _load_harness()

    def gate_case(
        tier: str,
        operation_id: str,
        case_id: str = "default",
        state: str = "cli_process_cold",
        *,
        duration_ms: float = 100.0,
    ) -> dict[str, Any]:
        case = _benchmark_report()
        case["workload"]["tier"] = tier
        case["operation"].update(
            {
                "operation_id": operation_id,
                "case_id": case_id,
                "measurement_state": state,
                "outcome": "supported",
            }
        )
        sample = case["samples"][0]
        sample["duration_ms"] = duration_ms
        sample["stage_timings_ms"]["end_to_end"] = duration_ms
        sample["work"]["inventory_entries"] = {
            "scale-5k": 5000,
            "scale-10k": 10000,
        }.get(tier, 20000)
        sample["disk"].update(
            {
                "vector_payload_bytes": 100,
                "vector_id_bytes": 1,
                "descriptor_bytes": 1,
                "total_bytes": 200,
            }
        )
        case["summary"].update(
            {
                "median_ms": duration_ms,
                "p50_ms": duration_ms,
                "p95_ms": duration_ms,
                "max_ms": duration_ms,
            }
        )
        return case

    cases = []
    full = gate_case("large", "full_build")
    full["samples"][0]["work"]["generation_count"] = 1
    cases.append(full)
    authoritative = gate_case("large", "authoritative_noop")
    authoritative["samples"][0]["work"]["source_bytes_hashed"] = 512 * 1024**2
    authoritative["samples"][0]["work"]["source_bytes_read"] = 512 * 1024**2
    cases.append(authoritative)
    quick = gate_case("large", "status_quick")
    cases.append(quick)
    verified = gate_case("large", "status_verified")
    verified["samples"][0]["work"]["source_bytes_hashed"] = 512 * 1024**2
    verified["samples"][0]["work"]["source_bytes_read"] = 512 * 1024**2
    verified["samples"][0]["stage_timings_ms"]["source"] = 1000.0
    cases.append(verified)
    cases.append(gate_case("large", "refresh_noop"))
    one_file = gate_case("large", "refresh_one_file")
    one_file["samples"][0]["work"].update(
        {
            "vector_bytes_read": 100,
            "vector_bytes_written": 100,
            "vector_payload_passes": 2,
            "path_index_builds": 1,
        }
    )
    cases.append(one_file)
    query_ids = [
        "lexical_high",
        "lexical_low",
        "lexical_zero",
        "path_symbol_ambiguity",
        "direct_ascii",
        "direct_cjk",
        "signal_metadata",
        "semantic_high",
        "planner_off_ordinary",
    ]
    for query_id in query_ids:
        for state in ("cli_process_cold", "mcp_resident_warm"):
            query = gate_case("large", "query", query_id, state)
            query["operation"]["case_family"] = "query"
            query["samples"][0]["stage_timings_ms"]["semantic"] = 10.0
            cases.append(query)
    explore = gate_case(
        "large",
        "explore",
        "p4_explore",
        "mcp_resident_warm",
    )
    explore["operation"]["case_family"] = "explore"
    explore["samples"][0]["work"]["vector_payload_passes"] = 3
    cases.append(explore)

    for tier, multiplier in (("scale-5k", 1), ("scale-10k", 2)):
        for operation_id in (
            "full_build",
            "authoritative_noop",
            "status_quick",
            "status_verified",
            "refresh_noop",
            "refresh_one_file",
        ):
            case = gate_case(
                tier,
                operation_id,
                duration_ms=100.0 * multiplier,
            )
            work = case["samples"][0]["work"]
            if operation_id == "full_build":
                work["generation_count"] = 1
            if operation_id == "authoritative_noop":
                work["source_bytes_read"] = 100 * multiplier
                work["source_bytes_hashed"] = 100 * multiplier
            if operation_id == "refresh_one_file":
                work["vector_bytes_read"] = 10 * multiplier
                work["vector_bytes_written"] = 10 * multiplier
            cases.append(case)

    final = {"case_reports": cases}
    module._large_acceptance_gates(final)
    module._scale_acceptance_gates(final)

    quick["samples"][0]["work"]["source_bytes_read"] = 1
    with pytest.raises(ValueError, match="quick status body/vector reads"):
        module._large_acceptance_gates(final)


def test_acceptance_compare_binds_all_inputs_and_emits_only_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_harness()
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps({"protected_small_entry_comparable": ["full_build"]}),
        encoding="utf-8",
    )
    calibration = {
        "sha256_mib_per_s": 100.0,
        "numpy_dot_ms": 10.0,
        "sqlite_ms": 5.0,
    }
    case = {
        "workload": {"tier": "large"},
        "operation": {
            "operation_id": "full_build",
            "case_id": "default",
            "measurement_state": "cli_process_cold",
        },
        "calibration": calibration,
    }
    baseline = {
        "mode": "baseline",
        "identity": {
            "implementation_commit": GIT,
            "production_tree": GIT,
            "workload_sha256": HASH,
        },
        "case_reports": [deepcopy(case)],
    }
    final_identity = {
        "implementation_commit": ACTUAL_COMMIT,
        "production_tree": ACTUAL_TREE,
        "workload_sha256": HASH,
    }
    final = {
        "mode": "final",
        "identity": final_identity,
        "case_reports": [deepcopy(case)],
        "churn": {"steps": 100},
    }
    churn = {
        "mode": "final",
        "report_scope": "churn",
        "identity": final_identity,
        "churn": {"steps": 100},
    }
    paired = {
        "pair_count": 30,
        "implementations": {
            "baseline": {"implementation_commit": GIT},
            "final": {
                "implementation_commit": ACTUAL_COMMIT,
                "production_tree": ACTUAL_TREE,
            },
        },
        "protected_operation_ids": ["full_build"],
        "summaries": [
            {
                "operation_id": "full_build",
                "baseline": {"outcome": "supported", "cv_population": 0.01},
                "final": {"outcome": "supported", "cv_population": 0.01},
                "median_ratio": 1.05,
            }
        ],
    }
    monkeypatch.setattr(module, "validate_report_data", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(module, "validate_paired_report", lambda *_args: None)
    monkeypatch.setattr(
        module,
        "validate_performance_registry_coverage",
        lambda *_args: None,
    )
    monkeypatch.setattr(module, "_large_acceptance_gates", lambda *_args: None)
    monkeypatch.setattr(module, "_scale_acceptance_gates", lambda *_args: None)

    report = module.compare_acceptance_reports(
        baseline,
        final,
        paired,
        churn,
        manifest=manifest,
        input_sha256={
            "baseline": HASH,
            "final": HASH,
            "paired": HASH,
            "churn": HASH,
        },
    )

    assert report["conclusion"] == "success"
    assert all(report["gates"].values())
    assert report["inputs"] == {
        "baseline": HASH,
        "final": HASH,
        "paired": HASH,
        "churn": HASH,
    }


def test_index_health_goldens_have_exact_required_order_and_states() -> None:
    fixture = _load(CONTRACTS / "index_health_v1.json")
    assert fixture["canonical_report_keys"] == REPORT_KEYS
    cases = {case["id"]: case["report"] for case in fixture["cases"]}
    assert {
        "missing",
        "future_manifest",
        "future_operational",
        "future_graph",
        "legacy_manifest_v1",
        "healthy_metadata",
        "healthy_verified",
        "stale",
        "writer_interrupted",
        "generation_interrupted",
        "degraded_coverage",
        "stable_corruption",
    } == set(cases)
    for report in cases.values():
        _assert_index_health_report(report)
    for case_id in ("missing", "future_manifest", "future_operational", "future_graph"):
        report = cases[case_id]
        assert report["freshness"]["inspection_mode"] == "none"
        assert report["freshness"]["samples"] is None
        assert report["coverage"]["skip_counts"] is None
        assert report["writer"] == {
            "active": None,
            "state": "not_inspected",
            "evidence": "not_inspected",
        }
        assert report["embedding_config_match"] is None
        for identity in ("indexed_embedding", "configured_embedding"):
            if report[identity]["status"] != "valid":
                assert all(
                    report[identity][key] is None
                    for key in ("provider", "model", "dimensions", "config_hash")
                )
                assert report[identity]["network_egress_capable"] is True


def test_status_and_refresh_envelopes_are_closed_ordered_goldens() -> None:
    status = _load(CONTRACTS / "status_envelopes_v1.json")
    assert list(status["success"]) == ["schema_version", "ok", "repo", "index_health"]
    assert status["success"]["schema_version"] == 1
    assert status["success"]["ok"] is True
    _assert_index_health_report(status["success"]["index_health"])
    assert {item["error"]["code"] for item in status["errors"]} == STATUS_CODES
    for item in status["errors"]:
        assert list(item) == ["schema_version", "ok", "error"]
        assert list(item["error"]) == ["code", "message"]
        assert item["schema_version"] == 1 and item["ok"] is False
        assert isinstance(item["error"]["message"], str) and item["error"]["message"]

    refresh = _load(CONTRACTS / "refresh_envelopes_v1.json")
    _assert_refresh_success(refresh["success"])
    assert {item["error"]["code"] for item in refresh["errors"]} == REFRESH_CODES
    for item in refresh["errors"]:
        assert list(item) == ["schema_version", "ok", "error"]
        assert list(item["error"]) == [
            "code",
            "message",
            "network_egress_outcome",
        ]
        assert item["error"]["network_egress_outcome"] in {
            "not_attempted",
            "possible",
            "performed",
        }
        assert item["schema_version"] == 1 and item["ok"] is False
        assert isinstance(item["error"]["message"], str) and item["error"]["message"]
        if item["error"]["code"] != "refresh_failed":
            assert item["error"]["network_egress_outcome"] == "not_attempted"
    assert {
        item["error"]["network_egress_outcome"]
        for item in refresh["errors"]
        if item["error"]["code"] == "refresh_failed"
    } == {"not_attempted", "possible", "performed"}


def test_operation_outcomes_match_the_complete_design_matrix() -> None:
    fixture = _load(CONTRACTS / "operation_outcomes_v1.json")
    assert fixture == {
        "fixture_schema_version": 1,
        "operations": ["cli_status", "cli_stats", "mcp_status", "mcp_stats", "refresh"],
        "states": [
            {
                "state": "missing_index",
                "cli_status": "report_missing",
                "cli_stats": "missing_index",
                "mcp_status": "ok_missing",
                "mcp_stats": "missing_index",
                "refresh": "missing_index",
            },
            {
                "state": "manifest_v1",
                "cli_status": "report_degraded",
                "cli_stats": "success",
                "mcp_status": "ok_degraded",
                "mcp_stats": "success_with_health",
                "refresh": "authoritative_index_required",
            },
            {
                "state": "v2_ready_or_stale",
                "cli_status": "report",
                "cli_stats": "success",
                "mcp_status": "ok",
                "mcp_stats": "success_with_health",
                "refresh": "success_or_authoritative",
            },
            {
                "state": "future_manifest",
                "cli_status": "report_incompatible",
                "cli_stats": "incompatible_manifest_schema",
                "mcp_status": "ok_incompatible",
                "mcp_stats": "incompatible_manifest_schema",
                "refresh": "incompatible_manifest_schema",
            },
            {
                "state": "future_operational",
                "cli_status": "report_incompatible",
                "cli_stats": "incompatible_operational_schema",
                "mcp_status": "ok_incompatible",
                "mcp_stats": "incompatible_operational_schema",
                "refresh": "incompatible_operational_schema",
            },
            {
                "state": "future_graph",
                "cli_status": "report_incompatible",
                "cli_stats": "incompatible_signal_schema",
                "mcp_status": "ok_incompatible",
                "mcp_stats": "incompatible_signal_schema",
                "refresh": "incompatible_signal_schema",
            },
            {
                "state": "stable_corruption",
                "cli_status": "report_corrupt",
                "cli_stats": "index_corrupt",
                "mcp_status": "ok_corrupt",
                "mcp_stats": "index_corrupt",
                "refresh": "authoritative_index_required",
            },
            {
                "state": "ready_writer_or_generation_drift",
                "cli_status": "report_degraded_retry",
                "cli_stats": "success_with_health",
                "mcp_status": "ok_degraded_retry",
                "mcp_stats": "success_with_health",
                "refresh": "index_busy_or_workspace_changed",
            },
            {
                "state": "stale_writer_or_generation_drift",
                "cli_status": "report_stale_retry",
                "cli_stats": "success_with_health",
                "mcp_status": "ok_stale_retry",
                "mcp_stats": "success_with_health",
                "refresh": "index_busy_or_workspace_changed",
            },
        ],
    }


def test_workload_manifest_freezes_tiers_generator_and_churn() -> None:
    manifest = _load(PERFORMANCE / "workload_manifest.json")
    assert manifest["generator"] == {
        "version": "p6-generator-v1",
        "contract_sha256": manifest["generator"]["contract_sha256"],
        "seed": 20260718,
        "network_allowed": False,
        "real_source_allowed": False,
    }
    assert re.fullmatch(r"[0-9a-f]{64}", manifest["generator"]["contract_sha256"])
    module = _load_harness()
    assert module.workload_contract_sha256(manifest) == manifest["generator"][
        "contract_sha256"
    ]
    expected = {
        "smoke": (1000, 24, 4000, 12),
        "large": (20000, 512, 80000, 256),
        "scale-5k": (5000, 128, 20000, 64),
        "scale-10k": (10000, 256, 40000, 128),
        "stress": (50000, 1280, 200000, 640),
    }
    for tier, (files, source_mib, chunks, text_mib) in expected.items():
        value = manifest["tiers"][tier]
        assert (
            value["files"],
            value["source_bytes"],
            value["chunks"],
            value["chunk_text_bytes"],
        ) == (files, source_mib * 1024**2, chunks, text_mib * 1024**2)
    schedule = manifest["edit_schedule"]
    assert schedule["version"] == "p6-churn-v1"
    assert schedule["steps"] == 100
    assert schedule["sample_every_steps"] == 10
    assert schedule["sample_operations"] == ["status", "query"]
    assert schedule["cycle_length"] == 10
    assert schedule["base_target_stride"] == 7
    assert schedule["failure_variants"] == [
        "directory_failure",
        "control_file_failure",
    ]
    assert schedule["operation_counts"] == {
        "add": 10,
        "control_file_failure": 5,
        "delete": 10,
        "delete_added": 10,
        "directory_failure": 5,
        "equal_content_touch": 10,
        "modify": 10,
        "restore": 10,
        "retryable_skip": 10,
        "same_metadata_content_edit": 10,
        "stable_skip": 10,
    }
    assert re.fullmatch(r"[0-9a-f]{64}", schedule["expected_trace_sha256"])
    assert len(manifest["protected_small_entry_comparable"]) == len(
        set(manifest["protected_small_entry_comparable"])
    )


def test_query_cases_and_exact_candidate_baseline_are_complete() -> None:
    queries = _load(PERFORMANCE / "query_cases.json")
    baseline = _load(PERFORMANCE / "exact_candidate_baseline.json")
    expected_ids = set(queries["approved_generated_query_ids"])
    assert all(case["planner_enabled"] is False for case in queries["cases"])
    assert expected_ids == {case["id"] for case in queries["cases"]}
    assert expected_ids == {case["case_id"] for case in baseline["cases"]}
    for case in baseline["cases"]:
        assert case["snapshot_a"] == case["snapshot_b"]
        for candidate in case["snapshot_a"]["ordered_candidates"]:
            assert math.isfinite(candidate["score"])
            assert list(candidate) == ["candidate_id", "score", "source_parts"]
            assert set(candidate["source_parts"]) == {
                "lexical",
                "path_symbol",
                "direct_text",
                "signal",
                "semantic",
            }


def test_exact_candidate_baseline_matches_two_real_generated_snapshots(
    tmp_path: Path,
) -> None:
    module = _load_harness()
    assert hasattr(module, "compute_exact_candidate_baseline"), (
        "P6 exact baseline generator capability is absent"
    )
    generated = module.compute_exact_candidate_baseline(
        tmp_path / "snapshot-a",
        tmp_path / "snapshot-b",
        PERFORMANCE / "query_cases.json",
    )
    expected = _load(PERFORMANCE / "exact_candidate_baseline.json")
    assert generated == expected
    cases = {case["case_id"]: case for case in generated["cases"]}
    assert cases["lexical_zero"]["snapshot_a"]["ordered_candidates"] == []
    fingerprints = {
        case["snapshot_a"]["final_result_sha256"] for case in generated["cases"]
    }
    assert len(fingerprints) == len(generated["cases"])
    assert all(len(set(fingerprint)) > 1 for fingerprint in fingerprints)


def _load_harness() -> Any:
    assert HARNESS.is_file(), (
        "P6 benchmark harness capability is absent: "
        "scripts/p6_benchmark.py must implement the reviewed Task 1 subcommands"
    )
    spec = importlib.util.spec_from_file_location("p6_benchmark", HARNESS)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_path_context_work_scales_linearly() -> None:
    module = _load_harness()
    counter_type = getattr(module, "_PathContextWorkCounter", None)
    assert counter_type is not None, "path-context work counter is absent"

    def projection(repository_paths: int) -> tuple[int, int]:
        path_index = type(
            "PathIndexFixture",
            (),
            {"active_paths": tuple(range(repository_paths))},
        )()
        counter = counter_type()
        for _ in range(repository_paths):
            counter.observe(path_index)
        return counter.builds, counter.paths_canonicalized

    scale_5k = projection(5_000)
    scale_10k = projection(10_000)

    assert scale_5k == (1, 5_000)
    assert scale_10k == (1, 10_000)
    assert scale_10k[0] / scale_5k[0] <= 2.4
    assert scale_10k[1] / scale_5k[1] <= 2.4


def test_query_work_contract_rejects_full_scan_amplification() -> None:
    module = _load_harness()
    report = _benchmark_report()
    report["mode"] = "final"

    module.validate_report_data(report, "benchmark-report-v1.json")

    unused_profile = deepcopy(report)
    unused_profile["samples"][0]["work"]["repo_profile_vm_steps"] = 1
    with pytest.raises(ValueError, match="unused repository profile"):
        module.validate_report_data(unused_profile, "benchmark-report-v1.json")

    token_full_scan = deepcopy(report)
    token_full_scan["samples"][0]["work"]["path_symbol_rows"] = 92_000
    with pytest.raises(ValueError, match="path/symbol row budget"):
        module.validate_report_data(token_full_scan, "benchmark-report-v1.json")

    repeated_direct_text = deepcopy(report)
    repeated_direct_text["samples"][0]["work"]["direct_text_rows"] = 4_001
    with pytest.raises(ValueError, match="direct-text row budget"):
        module.validate_report_data(repeated_direct_text, "benchmark-report-v1.json")

    nonrecallable_signals = deepcopy(report)
    nonrecallable_signals["samples"][0]["work"]["signal_rows"] = 12_001
    with pytest.raises(ValueError, match="signal row budget"):
        module.validate_report_data(nonrecallable_signals, "benchmark-report-v1.json")


def test_vector_work_contract_requires_one_score_pass() -> None:
    module = _load_harness()
    report = _benchmark_report()
    report["mode"] = "final"
    work = report["samples"][0]["work"]
    work.update(
        {
            "vector_bytes_read": 1,
            "vector_bytes_hashed": 0,
            "vector_payload_passes": 1,
            "vector_normalization_count": 1,
            "vector_scored_rows": 4_000,
            "vector_sorted_rows": 80,
        }
    )

    module.validate_report_data(report, "benchmark-report-v1.json")

    violations = (
        ("vector_payload_passes", 2, "payload pass"),
        ("vector_bytes_hashed", 1, "payload hash"),
        ("vector_normalization_count", 4_000, "normalization"),
        ("vector_scored_rows", 8_000, "score pass"),
        ("vector_sorted_rows", 4_000, "full-score sort"),
    )
    for key, value, message in violations:
        invalid = deepcopy(report)
        invalid["samples"][0]["work"][key] = value
        with pytest.raises(ValueError, match=message):
            module.validate_report_data(invalid, "benchmark-report-v1.json")


def test_required_benchmark_subcommands_are_registered() -> None:
    module = _load_harness()
    required = {
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
    }
    assert set(module.REQUIRED_SUBCOMMANDS) == required
    result = subprocess.run(
        [sys.executable, str(HARNESS), "--help"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0
    assert all(name in result.stdout for name in required)


def test_harness_validation_is_closed_finite_and_private() -> None:
    module = _load_harness()
    report = _benchmark_report()
    module.validate_report_data(report, "benchmark-report-v1.json")

    unsupported = deepcopy(report)
    unsupported["operation"]["outcome"] = "unsupported"
    unsupported["samples"] = []
    unsupported["summary"].update(
        {
            "sample_count": 0,
            "median_ms": 0.0,
            "p50_ms": 0.0,
            "p95_ms": 0.0,
            "max_ms": 0.0,
            "cv_population": 0.0,
        }
    )
    module.validate_report_data(unsupported, "benchmark-report-v1.json")
    unsupported_with_sample = deepcopy(unsupported)
    unsupported_with_sample["samples"] = deepcopy(report["samples"])
    with pytest.raises(ValueError):
        module.validate_report_data(
            unsupported_with_sample, "benchmark-report-v1.json"
        )
    supported_without_samples = deepcopy(unsupported)
    supported_without_samples["operation"]["outcome"] = "supported"
    with pytest.raises(ValueError):
        module.validate_report_data(
            supported_without_samples, "benchmark-report-v1.json"
        )

    invalid_reports = []
    unknown = deepcopy(report)
    unknown["unknown"] = True
    invalid_reports.append(unknown)
    nonfinite = deepcopy(report)
    nonfinite["samples"][0]["duration_ms"] = math.nan
    invalid_reports.append(nonfinite)
    bad_unit = deepcopy(report)
    bad_unit["summary"]["units"]["duration"] = "seconds"
    invalid_reports.append(bad_unit)
    dirty = deepcopy(report)
    dirty["identity"]["dirty_production_source"] = True
    invalid_reports.append(dirty)
    mismatched_tree = deepcopy(report)
    mismatched_tree["identity"]["production_tree"] = "2" * 40
    invalid_reports.append(mismatched_tree)
    for candidate in invalid_reports:
        with pytest.raises(ValueError):
            module.validate_report_data(candidate, "benchmark-report-v1.json")

    for private in (
        {"source_body": "class Secret {}"},
        {"vector_values": [0.1, 0.2]},
        {"temporary_root": "/Users/private/work"},
        {"temporary_root": r"C:\\private\\work"},
        {"api_key": "secret"},
        {"query_text": "unapproved real query"},
        {"endpoint": "https://token@example.invalid"},
        {"environment": {"HOME": "/private"}},
    ):
        with pytest.raises(ValueError):
            module.validate_private_payload(private, approved_query_ids=set())


def test_performance_assembly_preserves_distinct_case_identity(tmp_path: Path) -> None:
    module = _load_harness()
    smoke = _benchmark_report()
    large = deepcopy(smoke)
    large["workload"]["tier"] = "large"
    large["workload"]["fingerprint_sha256"] = "2" * 64
    large["operation"].update(
        {
            "operation_id": "full_build",
            "case_id": "default",
            "case_family": "index",
        }
    )
    paths = []
    for name, report in (("smoke.json", smoke), ("large.json", large)):
        path = tmp_path / name
        path.write_text(json.dumps(report), encoding="utf-8")
        paths.append(path)

    assembled = module.assemble_reports("performance", paths, "baseline")
    _validator("benchmark-report-v1.json").validate(assembled)
    assert "workload" not in assembled and "samples" not in assembled
    assert [case["workload"]["tier"] for case in assembled["case_reports"]] == [
        "large",
        "smoke",
    ]
    assert [
        (case["operation"]["operation_id"], case["operation"]["case_id"])
        for case in assembled["case_reports"]
    ] == [("full_build", "default"), ("query", "lexical_high")]

    nested_paths = []
    for name, source_path in (("smoke-suite.json", paths[0]), ("large-suite.json", paths[1])):
        suite = module.assemble_reports("performance", [source_path], "baseline")
        suite_path = tmp_path / name
        suite_path.write_text(json.dumps(suite), encoding="utf-8")
        nested_paths.append(suite_path)
    assert module.assemble_reports(
        "performance", nested_paths, "baseline"
    ) == assembled

    duplicate_path = tmp_path / "duplicate.json"
    duplicate_path.write_text(json.dumps(smoke), encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate cases"):
        module.assemble_reports(
            "performance", [paths[0], duplicate_path], "baseline"
        )

    mixed = deepcopy(large)
    other_commit = subprocess.check_output(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD^"], text=True
    ).strip()
    other_tree = subprocess.check_output(
        [
            "git",
            "-C",
            str(ROOT),
            "rev-parse",
            f"{other_commit}:src/context_search_tool",
        ],
        text=True,
    ).strip()
    mixed["identity"]["implementation_commit"] = other_commit
    mixed["identity"]["production_tree"] = other_tree
    mixed_path = tmp_path / "mixed.json"
    mixed_path.write_text(json.dumps(mixed), encoding="utf-8")
    with pytest.raises(ValueError, match="mixed identity"):
        module.assemble_reports("performance", [paths[0], mixed_path], "baseline")


def test_performance_registry_coverage_rejects_partial_tier(tmp_path: Path) -> None:
    module = _load_harness()
    manifest = tmp_path / "workload_manifest.json"
    contract = {
        "expected_fingerprints": {"smoke": HASH},
        "benchmark_registry": {
            "cases": [
                {
                    "operation_id": "query",
                    "case_id": "lexical_high",
                    "tiers": ["smoke"],
                    "measurements": [
                        {
                            "state": "cli_process_cold",
                            "sample_count": 1,
                            "baseline_outcome": "supported",
                        }
                    ],
                },
                {
                    "operation_id": "full_build",
                    "case_id": "default",
                    "tiers": ["smoke"],
                    "measurements": [
                        {
                            "state": "cli_process_cold",
                            "sample_count": 1,
                            "baseline_outcome": "supported",
                        }
                    ],
                },
            ]
        },
    }
    manifest.write_text(json.dumps(contract), encoding="utf-8")
    workload_sha256 = hashlib.sha256(manifest.read_bytes()).hexdigest()

    query = _benchmark_report()
    query["identity"]["workload_sha256"] = workload_sha256
    full_build = deepcopy(query)
    full_build["operation"].update(
        {
            "operation_id": "full_build",
            "case_id": "default",
            "case_family": "index",
        }
    )
    query_path = tmp_path / "query.json"
    full_build_path = tmp_path / "full-build.json"
    query_path.write_text(json.dumps(query), encoding="utf-8")
    full_build_path.write_text(json.dumps(full_build), encoding="utf-8")

    with pytest.raises(ValueError, match="coverage mismatch"):
        module.assemble_reports(
            "performance", [query_path], "baseline", manifest=manifest
        )
    assembled = module.assemble_reports(
        "performance",
        [query_path, full_build_path],
        "baseline",
        manifest=manifest,
    )
    module.validate_performance_registry_coverage(assembled, manifest)


def test_environment_assembly_aggregates_per_case_facts(tmp_path: Path) -> None:
    module = _load_harness()
    entry = _entry_record(module)
    performance = _performance_report()
    second = deepcopy(performance["case_reports"][0])
    second["operation"]["case_id"] = "direct_ascii"
    second["environment"]["background_cpu_percent"] = 3.0
    second["calibration"].update(
        {
            "sha256_mib_per_s": 700.0,
            "numpy_dot_ms": 35.0,
            "sqlite_ms": 14.0,
            "within_pair_percent": 2.0,
        }
    )
    performance["case_reports"].append(second)
    entry_path = tmp_path / "entry-record.json"
    performance_path = tmp_path / "entry-performance.json"
    entry_path.write_text(json.dumps(entry), encoding="utf-8")
    performance_path.write_text(json.dumps(performance), encoding="utf-8")

    result = module.assemble_reports(
        "environment", [entry_path, performance_path], "baseline"
    )

    assert result["environment"]["swap_growth_bytes"] == 0
    assert result["environment"]["background_cpu_percent"] == 3.0
    assert result["calibration"] == {
        "sha256_mib_per_s": 800.0,
        "numpy_dot_ms": 30.0,
        "sqlite_ms": 12.0,
        "paired_drift_percent": 2.0,
    }


def test_generate_is_deterministic_external_and_source_free(tmp_path: Path) -> None:
    module = _load_harness()
    first = tmp_path / "first"
    second = tmp_path / "second"
    manifest = PERFORMANCE / "workload_manifest.json"
    first_result = module.generate_repository("smoke", first, manifest)
    second_result = module.generate_repository("smoke", second, manifest)
    contract = _load(manifest)
    assert first_result["fingerprint_sha256"] == second_result["fingerprint_sha256"]
    assert first_result["fingerprint_sha256"] == module._repository_fingerprint(first)
    assert second_result["fingerprint_sha256"] == module._repository_fingerprint(second)
    assert first_result["generator_sha256"] == second_result["generator_sha256"]
    assert first_result["fingerprint_sha256"] == contract["expected_fingerprints"]["smoke"]
    assert len(set(first_result["fingerprint_sha256"])) > 1
    assert first_result["files_generated"] == contract["tiers"]["smoke"]["files"]
    assert sum(path.stat().st_size for path in first.rglob("*") if path.is_file()) == (
        contract["tiers"]["smoke"]["source_bytes"]
    )
    assert first_result["root"] == "external"
    assert second_result["root"] == "external"
    assert first_result["edit_schedule"] == second_result["edit_schedule"]
    schedule = first_result["edit_schedule"]
    assert schedule["trace_sha256"] == contract["edit_schedule"][
        "expected_trace_sha256"
    ]
    assert schedule["sample_operations"] == ["status", "query"]
    assert len(schedule["actions"]) == 100
    assert [
        action["step"]
        for action in schedule["actions"]
        if action["sample_after"]
    ] == list(range(10, 101, 10))
    counts: dict[str, int] = {}
    for action in schedule["actions"]:
        counts[action["operation"]] = counts.get(action["operation"], 0) + 1
        target = Path(action["target"])
        assert not target.is_absolute() and ".." not in target.parts
    assert counts == contract["edit_schedule"]["operation_counts"]

    for cycle in range(10):
        actions = schedule["actions"][cycle * 10 : (cycle + 1) * 10]
        assert actions[1]["operation"] == "delete"
        assert actions[2] == {
            "step": cycle * 10 + 3,
            "operation": "restore",
            "target": actions[1]["target"],
            "sample_after": False,
            "expected_outcome": "applied",
            "source_step": actions[1]["step"],
        }
        assert actions[3]["operation"] == "add"
        assert actions[4]["operation"] == "delete_added"
        assert actions[4]["target"] == actions[3]["target"]
        assert actions[4]["source_step"] == actions[3]["step"]
        assert actions[5]["operation"] == "equal_content_touch"
        assert actions[5]["preserve_content"] is True
        assert actions[6]["operation"] == "same_metadata_content_edit"
        assert actions[6]["observer"] == "no_ctime"
        assert actions[6]["preserve_size"] is True
        assert actions[6]["preserve_mtime"] is True
        assert actions[7]["expected_outcome"] == "stable_skip"
        assert actions[8]["expected_outcome"] == "retryable_skip"
        assert actions[9]["operation"] == contract["edit_schedule"][
            "failure_variants"
        ][cycle % 2]
        assert actions[9]["expected_outcome"] == "injected_failure"
    serialized = json.dumps(first_result, allow_nan=False, sort_keys=True)
    assert "source_body" not in serialized
    assert str(first) not in serialized
    assert sorted(path.relative_to(first).as_posix() for path in first.rglob("*")) == sorted(
        path.relative_to(second).as_posix() for path in second.rglob("*")
    )

    files = sorted(first.rglob("*.java"))
    sizes = sorted(path.stat().st_size for path in files)
    depths = sorted(len(path.relative_to(first).parts) for path in files)
    nearest_rank = lambda values, ratio: values[math.ceil(ratio * len(values)) - 1]
    distributions = contract["distributions"]
    assert (
        nearest_rank(sizes, 0.50),
        nearest_rank(sizes, 0.95),
        max(sizes),
    ) == tuple(distributions["file_size_bytes"][key] for key in ("p50", "p95", "max"))
    assert (
        nearest_rank(depths, 0.50),
        nearest_rank(depths, 0.95),
        max(depths),
    ) == tuple(distributions["path_depth"][key] for key in ("p50", "p95", "max"))
    test_files = sum("test" in path.relative_to(first).parts for path in files)
    assert len(files) - test_files == 4 * test_files

    implements = re.compile(r"\bimplements\s+([^\{]+)")
    relation_degrees: list[int] = []
    target_fan_in: dict[str, int] = {}
    from context_search_tool.chunker import chunk_text

    token_count = 0
    for path in files:
        content = path.read_text(encoding="utf-8")
        token_count += sum(
            len(chunk.lexical_tokens)
            for chunk in chunk_text(path.relative_to(first), content, "java", [])
        )
        for declaration in implements.findall(content):
            targets = [target.strip() for target in declaration.split(",")]
            relation_degrees.append(len(targets))
            for target in targets:
                target_fan_in[target] = target_fan_in.get(target, 0) + 1
    relation_degrees.sort()
    relation_distribution = distributions["relation_out_degree"]
    assert len(relation_degrees) == 4 * len(files)
    assert sum(relation_degrees) == contract["tiers"]["smoke"]["relations"]
    assert token_count == contract["tiers"]["smoke"]["tokens"]
    assert 8 * len(files) == contract["tiers"]["smoke"]["symbols"]
    assert 12 * len(files) == contract["tiers"]["smoke"]["signals"]
    assert (
        nearest_rank(relation_degrees, 0.50),
        nearest_rank(relation_degrees, 0.95),
        max(relation_degrees),
    ) == tuple(relation_distribution[key] for key in ("p50", "p95", "max"))
    assert max(target_fan_in.values()) == distributions["relation_target_fan_in"]["max"]
    assert set(distributions["relation_target_fan_in"]["designed_ordinal_cycle"]).issubset(
        set(target_fan_in.values())
    )

    from context_search_tool.graph_contract import generate_core_module_signal_id
    from context_search_tool.graph_plugins import PluginContext
    from context_search_tool.java_graph import JavaGraphProducer
    from context_search_tool.models import CodeSignal

    metadata_sizes: dict[int, list[int]] = {}
    for index in (0, 1, 950):
        filename = f"GeneratedBenchmarkTypeX{index * 4:07d}.java"
        path = next(first.rglob(filename))
        relative = path.relative_to(first)
        source = (
            module._generated_java_bytes(index, 8192, len(files))
            if index == 950
            else path.read_bytes()
        )
        context = PluginContext(relative, "java", "", {}, (relative,))
        producer = JavaGraphProducer()
        parsed = producer.parse(context, source)
        chunks = chunk_text(
            relative,
            source.decode("utf-8"),
            "java",
            list(parsed.symbols),
        )
        module_signal = CodeSignal(
            signal_id=generate_core_module_signal_id(
                file_path=relative.as_posix(),
                start_line=1,
                start_column=0,
                end_line=320,
                end_column=0,
            ),
            chunk_id=chunks[0].chunk_id,
            file_path=relative,
            kind="module",
            name=relative.as_posix(),
            start_line=1,
            end_line=320,
            language="java",
            qualified_name=relative.as_posix(),
            project_unit_key="",
            producer="core_module",
            recallable=False,
        )
        graph = producer.materialize(context, parsed, tuple(chunks), module_signal)
        assert parsed.fallback_required is False
        assert len(source.decode("utf-8").splitlines()) == 320
        assert len(chunks) == 4
        assert len(parsed.symbols) == 8
        assert 1 + len(graph.signals) == 12
        assert len(graph.relations) == sum(
            len(declaration.split(","))
            for declaration in implements.findall(source.decode("utf-8"))
        )
        metadata_sizes[index] = sorted(
            len(
                json.dumps(
                    dict(signal.metadata),
                    separators=(",", ":"),
                    sort_keys=True,
                ).encode("utf-8")
            )
            for signal in (module_signal, *graph.signals)
        )
    signal_distribution = distributions["signal_metadata_bytes"]
    assert nearest_rank(metadata_sizes[1], 0.50) == signal_distribution["p50"]
    assert nearest_rank(metadata_sizes[1], 0.95) == signal_distribution["p95"]
    assert max(metadata_sizes[0]) == signal_distribution["max"]


def test_edit_schedule_rejects_unsafe_fault_targets() -> None:
    module = _load_harness()
    contract = _load(PERFORMANCE / "workload_manifest.json")
    for key, value in (
        ("control_file", "../private"),
        ("directory_failure_target", "/private"),
    ):
        invalid = deepcopy(contract)
        invalid["edit_schedule"][key] = value
        with pytest.raises(ValueError, match="repository-relative"):
            module.generate_edit_schedule(invalid, "smoke")


def test_closed_raw_adapters_remove_paths_urls_and_credentials() -> None:
    module = _load_harness()
    raw = [
        "jsonschema==4.26.0",
        "context-search-tool @ file:///Users/private/context-search-tool",
        "demo @ git+https://token@example.invalid/org/repo.git@deadbeef",
    ]
    normalized = module.normalize_freeze_lines(
        raw,
        installed_versions={
            "jsonschema": "4.26.0",
            "context-search-tool": "0.1.0",
            "demo": "1.2.3",
        },
    )
    assert normalized["packages"] == [
        "context-search-tool==0.1.0",
        "demo==1.2.3",
        "jsonschema==4.26.0",
    ]
    assert normalized["raw_sha256"] == hashlib.sha256(
        ("\n".join(raw) + "\n").encode()
    ).hexdigest()
    assert "file://" not in json.dumps(normalized)
    assert "token@" not in json.dumps(normalized)
    assert module.validate_git_sha("1" * 40) == "1" * 40
    with pytest.raises(ValueError):
        module.validate_git_sha("HEAD")
    assert module.validate_lineage("1" * 40 + " reviewed subject\n") == [
        {"commit": "1" * 40, "subject": "reviewed subject"}
    ]
    with pytest.raises(ValueError):
        module.validate_lineage("1" * 40 + " subject\nprivate extra\n")


def test_tdd_red_log_requires_exact_ordinary_assertion_nodes() -> None:
    module = _load_harness()
    node = "tests/test_p6_benchmark.py::test_expected_red"
    failed_nodes, assertions = module._red_log_evidence(
        "\n".join(
            [
                "E   AssertionError: expected RED capability failure",
                f"FAILED {node} - AssertionError: expected RED capability failure",
                "1 failed, 3 passed in 0.10s",
            ]
        )
    )
    assert failed_nodes == [node]
    assert assertions == ["AssertionError: expected RED capability failure"]

    with pytest.raises(ValueError, match="collection"):
        module._red_log_evidence(
            "ERROR collecting tests/test_p6_benchmark.py\n1 error in 0.10s"
        )
    with pytest.raises(ValueError, match="ordinary assertion"):
        module._red_log_evidence("1 failed in 0.10s")


def test_pair_decision_publish_and_tdd_invariants(tmp_path: Path) -> None:
    module = _load_harness()
    assert module.alternating_pairs(3) == [
        ("pair-001", "baseline"),
        ("pair-001", "final"),
        ("pair-002", "final"),
        ("pair-002", "baseline"),
        ("pair-003", "baseline"),
        ("pair-003", "final"),
    ]
    decision = module.make_decision(
        "exact_ann",
        implementation_commit=ACTUAL_COMMIT,
        production_tree=ACTUAL_TREE,
        evidence_report_sha256=HASH,
        trigger_crossed=False,
        reason_codes=["semantic_within_budget", "rss_within_budget"],
    )
    _validator("decision-record-v1.json").validate(decision)
    assert "implementation_authorized" not in decision

    node_id = "tests/test_query_intent.py::test_query_intent"
    arguments = ["-q", node_id]
    identity, test_hashes = module._test_identity([node_id], arguments)
    record = {
        "schema_version": 1,
        "producer_version": "p6-benchmark-v1",
        "task": 1,
        "pre_change_commit": ACTUAL_COMMIT,
        "pre_change_production_tree": ACTUAL_TREE,
        "production_file_hashes": {"src/a.py": HASH},
        "test_file_hashes": test_hashes,
        "pytest": {"arguments": arguments, "node_ids": [node_id]},
        "red": {
            "exit_code": 1,
            "failed_node_ids": [node_id],
            "assertion_summaries": ["AssertionError: expected RED"],
            "started_at_epoch_ms": 1,
            "completed_at_epoch_ms": 2,
            "test_identity_sha256": identity,
        },
        "green": {
            "exit_code": 0,
            "passed": 1,
            "failed": 0,
            "errors": 0,
            "started_at_epoch_ms": 3,
            "completed_at_epoch_ms": 4,
            "test_identity_sha256": identity,
        },
        "final_staged_tree": ACTUAL_ROOT_TREE,
    }
    module.validate_tdd_record_data(record, staged_tree=ACTUAL_ROOT_TREE)
    changed = deepcopy(record)
    changed["green"]["test_identity_sha256"] = "2" * 64
    with pytest.raises(ValueError):
        module.validate_tdd_record_data(changed, staged_tree=ACTUAL_ROOT_TREE)
    with pytest.raises(ValueError):
        module.validate_tdd_record_data(record, staged_tree="2" * 40)
    changed_arguments = deepcopy(record)
    changed_arguments["pytest"]["arguments"] = ["-vv", node_id]
    with pytest.raises(ValueError, match="does not bind"):
        module.validate_tdd_record_data(
            changed_arguments,
            staged_tree=ACTUAL_ROOT_TREE,
        )
    changed_nodes = deepcopy(record)
    changed_nodes["pytest"]["node_ids"] = [
        "tests/test_query_intent.py::test_changed_node"
    ]
    with pytest.raises(ValueError, match="does not bind"):
        module.validate_tdd_record_data(
            changed_nodes,
            staged_tree=ACTUAL_ROOT_TREE,
        )

    source = tmp_path / "decision.json"
    source.write_text(json.dumps(decision), encoding="utf-8")
    destination = tmp_path / "published.json"
    module.publish_report(source, destination, publication_root=tmp_path)
    assert json.loads(destination.read_text(encoding="utf-8")) == decision
    with pytest.raises(FileExistsError):
        module.publish_report(source, destination, publication_root=tmp_path)


def test_functional_matrix_is_exact_tag_bound_contract() -> None:
    assert WORKFLOW.is_file(), "P6 functional matrix workflow capability is absent"
    text = WORKFLOW.read_text(encoding="utf-8")
    workflow = yaml.load(text, Loader=yaml.BaseLoader)
    assert workflow["run-name"] == "P6 evidence ${{ github.ref_name }}"
    assert workflow["on"] == {"push": {"tags": ["p6-acceptance-*"]}}
    assert list(workflow["jobs"]) == ["functional"]
    job = workflow["jobs"]["functional"]
    assert job["strategy"] == {
        "fail-fast": "false",
        "matrix": {
            "os": ["ubuntu-latest", "macos-latest", "windows-latest"],
            "python-version": ["3.11", "3.12", "3.13", "3.14"],
        },
    }
    assert job["env"] == {
        "EVIDENCE_ID": "${{ github.ref_name }}",
        "IMPLEMENTATION_COMMIT": "${{ github.sha }}",
        "RUN_ID": "${{ github.run_id }}",
        "RUN_ATTEMPT": "${{ github.run_attempt }}",
        "MATRIX_OS": "${{ matrix.os }}",
        "MATRIX_PYTHON": "${{ matrix.python-version }}",
    }
    named_steps = {step["name"]: step for step in job["steps"] if "name" in step}
    assert set(named_steps) == {
        "Install frozen functional dependencies",
        "Run P6 focused and protected contracts",
        "Audit skip and xfail nodes and emit matrix summary",
        "Upload schema-valid P6 evidence",
    }
    install_command = named_steps["Install frozen functional dependencies"]["run"]
    assert install_command.splitlines() == [
        "python -m pip install uv==0.9.14",
        "uv sync --frozen --extra dev",
    ]
    assert (ROOT / "uv.lock").is_file()
    run_command = named_steps["Run P6 focused and protected contracts"]["run"]
    assert "uv run --frozen --extra dev" in run_command
    assert "-o xfail_strict=true" in run_command
    assert "--junitxml=.quality/p6-matrix/junit.xml" in run_command
    expected_test_files = {
        "tests/test_index_health.py",
        "tests/test_manifest_v2.py",
        "tests/test_p6_operational_store.py",
        "tests/test_incremental_refresh.py",
        "tests/test_tokenizer_scanner.py",
        "tests/test_indexer_manifest.py",
        "tests/test_graph_lifecycle.py",
        "tests/test_graph_store.py",
        "tests/test_embeddings_vector_store.py",
        "tests/test_cli_commands.py",
        "tests/test_mcp_tools.py",
        "tests/test_mcp_server.py",
        "tests/test_p6_benchmark.py",
        "tests/test_sqlite_store.py",
        "tests/test_repo_profile.py",
        "tests/test_p5_inputs.py",
        "tests/test_p5_graph_contract.py",
        "tests/test_quality_p5.py",
        "tests/test_p5_protected_direct.py",
        "tests/test_resolved_graph_expansion.py",
        "tests/test_p5_explain.py",
        "tests/test_retrieval_core_characterization.py",
        "tests/test_retrieval_core_boundaries.py",
        "tests/test_retrieval_trace.py",
        "tests/test_retrieval_trace_pipeline.py",
        "tests/test_context_pack.py",
        "tests/test_exploration_boundaries.py",
        "tests/test_exploration_contracts.py",
        "tests/test_exploration_runner.py",
        "tests/test_quality_p3.py",
        "tests/test_quality_p4.py",
    }
    assert set(re.findall(r"tests/[A-Za-z0-9_/-]+\.py", run_command)) == expected_test_files
    audit_command = named_steps[
        "Audit skip and xfail nodes and emit matrix summary"
    ]["run"]
    assert "tests/path.py" not in audit_command
    assert 'terminal_nodes = {"SKIPPED": [], "XFAIL": [], "XPASS": []}' in audit_command
    assert "pytest/JUnit skip counts disagree" in audit_command
    assert "P6 functional matrix forbids XPASS nodes" in audit_command
    assert '(root / "uv.lock").read_bytes()' in audit_command
    assert 'hashlib.sha256(dependency_lock).hexdigest()' in audit_command
    upload = named_steps["Upload schema-valid P6 evidence"]
    assert upload["with"]["path"].splitlines() == [
        ".quality/p6-matrix/junit.xml",
        ".quality/p6-matrix/matrix-summary-v1.json",
    ]
