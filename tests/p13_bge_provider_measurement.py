"""Tracked P13 controller for paired BGE and hash measurements."""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib
import json
import math
import os
import re
import subprocess
import sys
import tempfile
import time
from contextlib import ExitStack, contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator


ENVELOPE_SCHEMA = "p13-bge-provider-measurement-v1"
BASELINE_COMMIT = "122ed052284fa488943cb4464301a391bd2e7e24"
LEGACY_RUNNER_SHA256 = (
    "c768f3d5474ffe664654962fc22033af05bfaeeb4100b7afb0324b1d718a4809"
)
BGE_CONFIG_IDENTITY = (
    "c1cc02373a3d92d32afefaf6fcfb1cb8ba8e6cdbdd3f0298484965b94ca0896b"
)
HASH_CONFIG_IDENTITY = (
    "5ab1cee713aff995519814538508a44cece92c285a746094e1cab8b86c7745be"
)
QUALITY_RUNNER = {
    "path": "src/context_search_tool/quality/runner.py",
    "sha256": (
        "47dc3cfd6b1daa2d65f86b54fc9d72596edf5b3d8915d4025f43af76f72ea724"
    ),
}
P1_QUALITY_INPUTS = {
    "fixture_catalog_gold": {
        "path": "tests/fixtures/retrieval_quality/queries.json",
        "blob_oid": "8bbe4d560fec1499aa1f436af929b8a6bb6f3eac",
        "sha256": (
            "ac7a9789098d088a22b8ddc78fed3128695cbb257923de8686c41fbcfa5824c5"
        ),
    },
    "acceptance_oracle": {
        "path": "tests/test_quality_p1.py",
        "blob_oid": "6dbbad2cb07b85f3f802b481655a4d8874cd9879",
        "sha256": (
            "a80d6e0183c76c05dc2284ab7b3f8791102bce9d26f454f4f94efa66d1bf0f67"
        ),
    },
    "committed_fixtures": {
        "tests/fixtures/java-spring-mini": {
            "file_count": 16,
            "tree_oid": "f005cb94bac1fd2e81705d0f9454803ea9ab7030",
            "tracked_listing_sha256": (
                "064c37bded5e5f6408d1e953a2a7be1dfd4854275b9eeb4365d575ddce2024e3"
            ),
        },
        "tests/fixtures/real_projects/cross_language_dashboard": {
            "file_count": 3,
            "tree_oid": "1001e3c929c9005d8c6d745e43fe4d8b93f32d3f",
            "tracked_listing_sha256": (
                "9c5165ea693159a779eae08d765351541c121f578fc6a38bf41e7b622996f7c7"
            ),
        },
        "tests/fixtures/real_projects/embedding_ab": {
            "file_count": 5,
            "tree_oid": "0f3d3d4419318bdd06633243015162fbb9eb6d6c",
            "tracked_listing_sha256": (
                "d973d364f36cd0ef6ba7fb86787cc8be77b7e1238e01adea07246a5602aad598"
            ),
        },
    },
}
P1_CASES = (
    ("java_spring_mini", "apply-audit-endpoint"),
    ("java_spring_mini", "audit-status-literal"),
    ("cross_language_dashboard", "dashboard-cross-language"),
    ("cross_language_dashboard", "dashboard-controller-path"),
    ("embedding_ab", "access-validation-cross-language"),
    ("embedding_ab", "blacklist-management-cross-language"),
    ("embedding_ab", "order-service-symbol"),
)
P1_CONFIG_HASHES = {
    "p1_vector_bge": (
        "sha256:b218204f3f064665e0aec7b4a9247c7949e8625e9e47f477a692e4fcb44cd6a4"
    ),
    "p1_hybrid_bge": (
        "sha256:47719ba626fb3c6bda4fc05c810d5d8db8eb975f1512c4a27dbed99adf3303c8"
    ),
}
BGE_MODEL = "bge-m3"
BGE_CANONICAL_MODEL = "bge-m3:latest"
BGE_DIMENSIONS = 1024
BGE_TRANSFORM = "bge-input-v1"
LEGACY_TRANSFORM = "p11-runner-head-4000"
BGE_DIGEST = (
    "7907646426070047a77226ac3e684fbbe8410524f7b4a74d02837e43f2146bab"
)
OLLAMA_VERSION = "0.30.10"

_ROOT = Path(__file__).resolve().parents[1]
_HARNESS_PATH = Path(__file__).resolve()
_GIT_OID_RE = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})")
_SHA256_RE = re.compile(r"[0-9a-f]{64}")
_ENVELOPE_KEYS = {
    "schema_version",
    "mode",
    "provider",
    "harness",
    "runner",
    "implementation",
    "module_origins",
    "transform_id",
    "attestation",
    "embedding_requests",
    "timing",
    "capture",
    "protected_inputs",
}
_ORIGIN_KEYS = {
    "context_search_tool",
    "context_search_tool.embeddings_bge",
    "p8_real_python_graphs_acceptance",
}
_IMPLEMENTATION_KEYS = {
    "base_commit",
    "tracked_diff_sha256",
    "untracked_files",
    "dirty",
}
_ATTESTATION_KEYS = {
    "configured_model",
    "canonical_model",
    "model_digest",
    "ollama_version",
    "base_url",
    "dimensions",
    "input_transform_id",
    "embedding_identity",
}
_REQUEST_KEYS = {"redink", "daily", "total"}
_TIMING_KEYS = {
    "index_seconds",
    "query_case_min_seconds",
    "query_p50_seconds",
    "query_p95_seconds",
}
_NATIVE_CAPTURE_KEYS = {
    "schema_version",
    "implementation",
    "environment",
    "manifest_sha256",
    "embedding_identity",
    "repositories",
    "cases",
    "witnesses",
    "embedding_requests",
    "timing",
}
_NATIVE_IDENTITY_KEYS = {
    "provider",
    "configured_model",
    "dimensions",
    "static_config_identity",
    "descriptor_identity",
    "canonical_model",
    "model_digest",
    "ollama_version",
    "input_transform_id",
    "pre_attestation",
    "post_attestation",
}
_REPOSITORY_KEYS = {"selected_files", "structure", "index_sqlite_bytes"}
_STRUCTURE_KEYS = {
    "active_chunks",
    "signals_by_producer",
    "relations_by_kind_resolution",
}
_CASE_KEYS = {
    "repo",
    "selected",
    "required",
    "contextual",
    "unique_selected_paths",
}
_SELECTED_KEYS = {
    "rank",
    "path",
    "graph_origin",
    "relation_slot",
    "relation_witness",
}
_REQUIRED_KEYS = {"path", "role", "rank", "state"}
_P1_WRAPPER_KEYS = {
    "schema_version",
    "implementation",
    "quality_runner",
    "quality_inputs",
    "profiles",
}
_P1_PROFILE_KEYS = {
    "profile",
    "config_hash",
    "provider",
    "embedding_identity",
    "attestation",
    "cases",
    "summary",
    "raw_report",
}
_P1_CASE_KEYS = {"repo_key", "case_id", "status", "required_miss"}
_P1_RAW_ROOT_KEYS = {
    "schema_version",
    "generated_at",
    "command_args",
    "tool",
    "fixture",
    "profile",
    "config",
    "planner",
    "aggregate",
    "repos",
    "cases",
}
_P1_RAW_CASE_KEYS = {
    "repo_key",
    "case_id",
    "query",
    "tags",
    "gate",
    "attempted",
    "known_gap_reason",
    "expanded_tokens",
    "planner",
    "query_variants",
    "variant_retrieval_status",
    "status",
    "metrics",
    "top_results",
    "failures",
}
_P1_RAW_CASE_PLANNER_KEYS = {
    "status",
    "rewritten_queries",
    "grep_keywords",
    "symbol_hints",
    "discarded_hints",
    "provider",
    "model",
    "prompt_version",
    "prompt_hash",
    "latency_ms",
    "repo_profile_hash",
    "repo_profile_truncated",
}
_P1_RAW_AGGREGATE_KEYS = {
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
_GATE_KEYS = {
    "raw_values",
    "numerator",
    "denominator",
    "ratio",
    "threshold",
    "passed",
    "input_capture_sha256",
    "evidence_path",
}
_ENGINEERING_GATE_KEYS = {
    "baseline_index_stability_redink",
    "baseline_index_stability_daily",
    "baseline_query_p95_stability",
    "candidate_index_ratio_redink",
    "candidate_index_ratio_daily",
    "candidate_index_ratio_total",
    "candidate_query_p95_ratio",
    "requests_non_increasing_redink",
    "requests_non_increasing_daily",
    "requests_strictly_lower_total",
    "same_side_non_timing",
}
_PRODUCT_GATE_KEYS = {
    "recall_non_decreasing",
    "zero_required_loss",
    "new_required",
    "noise_non_increasing",
    "p1_continuity",
    "query_p95_ratio",
    "per_repository_index_ratio",
    "same_provider_non_timing",
}
_FROZEN_INPUTS = {
    "tests/fixtures/p8_python_graphs/input_manifest.json": {
        "bytes": 13539,
        "sha256": (
            "56071dfc281f9947b989de26ddd1d07ff4e35666d8314686d0ffbb16cd92a013"
        ),
    },
    "tests/fixtures/p8_python_graphs/structural_expected.json": {
        "bytes": 58147,
        "sha256": (
            "37336cfaa701370cb7ad9855bdec15d2f2b512a2c11f1dc1463a7f564d2f561f"
        ),
    },
    "tests/fixtures/retrieval_quality/p8_python_graphs.json": {
        "bytes": 13415,
        "sha256": (
            "34442cbae318a7874a1d789dddec78ca135be42b4bd5e9b11089d0cad78963da"
        ),
    },
    "tests/fixtures/retrieval_quality/queries.json": {
        "bytes": 61830,
        "sha256": (
            "ac7a9789098d088a22b8ddc78fed3128695cbb257923de8686c41fbcfa5824c5"
        ),
    },
    "tests/generate_p8_python_graph_manifest.py": {
        "bytes": 19862,
        "sha256": (
            "d9c34b60148d66125c6608b3c050608986aa4e682467eff33b06c7465691eb14"
        ),
    },
    "tests/p8_python_graph_identity.py": {
        "bytes": 3581,
        "sha256": (
            "c17859916b59ba752184a3807d15c63bb2825d933f3a2aa70305b30f6fd475d8"
        ),
    },
}
_P1_PROFILES = {
    name: {
        "passed": 6,
        "total": 7,
        "only_known_miss": "audit-status-literal",
    }
    for name in ("p1_vector_bge", "p1_hybrid_bge")
}
_FLOAT_COMPARISON_EPSILON = 1e-12
_DEFAULT_TIMING_REPETITIONS = 3
_OLLAMA_ROOT = "http://localhost:11434"


def _canonical(payload: object) -> str:
    return json.dumps(
        payload, ensure_ascii=False, sort_keys=True, indent=1
    ) + "\n"


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_path(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _capture_sha256(payload: dict[str, object]) -> str:
    return _sha256_bytes(_canonical(payload).encode("utf-8"))


def _require_keys(value: object, expected: set[str], label: str) -> dict:
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError(f"{label} mapping is not closed")
    return value


def _require_sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise ValueError(f"{label} is not a SHA-256 value")
    return value


def _require_number(value: object, label: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or float(value) < 0.0
    ):
        raise ValueError(f"{label} is not a finite non-negative number")
    return float(value)


def _privacy_failure(value: object) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).lower() in {
                "body",
                "content",
                "credential",
                "query",
                "raw_payload",
                "snippet",
                "source",
                "source_body",
            }:
                return True
            if _privacy_failure(item):
                return True
        return False
    if isinstance(value, list):
        return any(_privacy_failure(item) for item in value)
    if not isinstance(value, str):
        return False
    return bool(
        value.startswith(("/", "\\\\"))
        or re.match(r"^[A-Za-z]:[\\/]", value)
        or re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://[^/@]+@", value)
        or "P13_RAW_" in value
        or "P13_CREDENTIAL_" in value
    )


def _git(root: Path, *arguments: str, check: bool = True) -> str:
    completed = subprocess.run(
        ("git", "-C", str(root), *arguments),
        check=check,
        text=True,
        capture_output=True,
    )
    return completed.stdout.strip()


def _implementation_identity(root: Path) -> dict[str, object]:
    diff = _git(root, "diff", "--binary", "HEAD", "--", "src", "tests")
    listed = _git(
        root,
        "ls-files",
        "--others",
        "--exclude-standard",
        "--",
        "src",
        "tests",
    )
    untracked = {
        relative: _sha256_path(root / relative)
        for relative in sorted(filter(None, listed.splitlines()))
    }
    return {
        "base_commit": _git(root, "rev-parse", "HEAD"),
        "tracked_diff_sha256": _sha256_bytes(diff.encode("utf-8")),
        "untracked_files": untracked,
        "dirty": bool(diff) or bool(untracked),
    }


def _require_expected_candidate_commit(value: object) -> str:
    if not isinstance(value, str) or _GIT_OID_RE.fullmatch(value) is None:
        raise ValueError("expected candidate commit is required")
    return value


def _verify_native_candidate(
    implementation_root: Path,
    expected_candidate_commit: object,
) -> dict[str, object]:
    expected = _require_expected_candidate_commit(
        expected_candidate_commit
    )
    root = implementation_root.resolve()
    actual = _implementation_identity(root)
    if actual["base_commit"] != expected:
        raise ValueError("native candidate commit mismatch")
    dirty = _git(
        root,
        "status",
        "--porcelain",
        "--untracked-files=all",
    )
    if dirty:
        raise ValueError("native candidate must be clean")
    return actual


def _validate_implementation(value: object) -> dict:
    implementation = _require_keys(
        value, _IMPLEMENTATION_KEYS, "implementation"
    )
    if (
        not isinstance(implementation["base_commit"], str)
        or not implementation["base_commit"]
        or not isinstance(implementation["dirty"], bool)
        or not isinstance(implementation["untracked_files"], dict)
    ):
        raise ValueError("implementation identity is invalid")
    _require_sha256(
        implementation["tracked_diff_sha256"],
        "implementation tracked diff",
    )
    for relative, sha256 in implementation["untracked_files"].items():
        path = Path(relative)
        if (
            not isinstance(relative, str)
            or path.is_absolute()
            or ".." in path.parts
        ):
            raise ValueError("implementation identity is invalid")
        _require_sha256(sha256, "implementation untracked file")
    return implementation


def _validate_attestation(value: object) -> dict:
    attestation = _require_keys(value, _ATTESTATION_KEYS, "attestation")
    for field in (
        "configured_model",
        "canonical_model",
        "model_digest",
        "ollama_version",
        "base_url",
        "input_transform_id",
        "embedding_identity",
    ):
        if not isinstance(attestation[field], str) or not attestation[field]:
            raise ValueError("attestation is invalid")
    _require_sha256(attestation["model_digest"], "model digest")
    if (
        isinstance(attestation["dimensions"], bool)
        or not isinstance(attestation["dimensions"], int)
        or attestation["dimensions"] <= 0
    ):
        raise ValueError("attestation is invalid")
    expected_identity = (
        f"bge-ollama-v1:{BGE_CONFIG_IDENTITY}:"
        f"{attestation['model_digest']}:"
        f"{hashlib.sha256(attestation['ollama_version'].encode('utf-8')).hexdigest()}:"
        f"{attestation['input_transform_id']}"
    )
    if (
        attestation["configured_model"] != BGE_MODEL
        or attestation["canonical_model"] != BGE_CANONICAL_MODEL
        or attestation["model_digest"] != BGE_DIGEST
        or attestation["ollama_version"] != OLLAMA_VERSION
        or attestation["base_url"] != _OLLAMA_ROOT
        or attestation["dimensions"] != BGE_DIMENSIONS
        or attestation["input_transform_id"] != BGE_TRANSFORM
        or attestation["embedding_identity"] != expected_identity
    ):
        raise ValueError("attestation identity mismatch")
    return attestation


def _validate_file_record(value: object, label: str) -> dict:
    record = _require_keys(value, {"path", "sha256"}, label)
    relative = Path(record["path"])
    if (
        not isinstance(record["path"], str)
        or relative.is_absolute()
        or ".." in relative.parts
    ):
        raise ValueError(f"{label} path is outside the implementation root")
    _require_sha256(record["sha256"], f"{label} SHA")
    return record


def _validate_requests(value: object) -> dict:
    requests = _require_keys(value, _REQUEST_KEYS, "embedding requests")
    if any(
        isinstance(requests[key], bool)
        or not isinstance(requests[key], int)
        or requests[key] < 0
        for key in _REQUEST_KEYS
    ) or requests["total"] != requests["redink"] + requests["daily"]:
        raise ValueError("embedding request counts are invalid")
    return requests


def _nearest_rank(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(percentile * len(ordered)) - 1)]


def _validate_timing(value: object) -> dict:
    timing = _require_keys(value, _TIMING_KEYS, "timing")
    index_seconds = _require_keys(
        timing["index_seconds"], {"redink", "daily"}, "index timing"
    )
    for repository, seconds in index_seconds.items():
        _require_number(seconds, f"{repository} index timing")
    minima = timing["query_case_min_seconds"]
    if not isinstance(minima, dict) or len(minima) != 18:
        raise ValueError("timing must contain 18 query case minima")
    ordered = [
        _require_number(minima[case_id], "query case timing")
        for case_id in sorted(minima)
    ]
    if (
        _require_number(timing["query_p50_seconds"], "query p50")
        != _nearest_rank(ordered, 0.50)
        or _require_number(timing["query_p95_seconds"], "query p95")
        != _nearest_rank(ordered, 0.95)
    ):
        raise ValueError("query timing percentiles are invalid")
    return timing


def _require_nonnegative_integer(value: object, label: str) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < 0
    ):
        raise ValueError(f"{label} is not a non-negative integer")
    return value


def _validate_native_repositories(value: object) -> None:
    repositories = _require_keys(
        value,
        {"redink", "daily"},
        "native repositories",
    )
    for repository in repositories.values():
        record = _require_keys(
            repository,
            _REPOSITORY_KEYS,
            "native repository",
        )
        _require_nonnegative_integer(
            record["selected_files"],
            "selected file count",
        )
        _require_nonnegative_integer(
            record["index_sqlite_bytes"],
            "index SQLite size",
        )
        structure = _require_keys(
            record["structure"],
            _STRUCTURE_KEYS,
            "native repository structure",
        )
        _require_nonnegative_integer(
            structure["active_chunks"],
            "active chunk count",
        )
        for field in (
            "signals_by_producer",
            "relations_by_kind_resolution",
        ):
            counts = structure[field]
            if not isinstance(counts, dict) or any(
                not isinstance(name, str)
                or not name
                or _require_nonnegative_integer(count, field) < 0
                for name, count in counts.items()
            ):
                raise ValueError("native repository structure is invalid")


def _validate_native_cases(value: object) -> set[str]:
    if not isinstance(value, dict) or len(value) != 18:
        raise ValueError("native capture requires 18 cases")
    for case_id, raw_case in value.items():
        if not isinstance(case_id, str) or not case_id:
            raise ValueError("native case ID is invalid")
        case = _require_keys(raw_case, _CASE_KEYS, "native case")
        if case["repo"] not in ("redink", "daily"):
            raise ValueError("native case repository is invalid")
        if not isinstance(case["contextual"], list) or not all(
            isinstance(path, str) for path in case["contextual"]
        ):
            raise ValueError("native case contextual paths are invalid")
        _require_nonnegative_integer(
            case["unique_selected_paths"],
            "native unique selected path count",
        )
        if not isinstance(case["selected"], list):
            raise ValueError("native case selections are invalid")
        for raw_selected in case["selected"]:
            selected = _require_keys(
                raw_selected,
                _SELECTED_KEYS,
                "native selected entry",
            )
            if (
                _require_nonnegative_integer(
                    selected["rank"],
                    "native selected rank",
                )
                <= 0
                or not isinstance(selected["path"], str)
                or not selected["path"]
                or not isinstance(selected["graph_origin"], bool)
                or not isinstance(selected["relation_slot"], bool)
            ):
                raise ValueError("native selected entry is invalid")
            witness = selected["relation_witness"]
            if witness is not None:
                witness = _require_keys(
                    witness,
                    {"relation_id", "target_path"},
                    "native relation witness",
                )
                if not all(
                    isinstance(item, str) and item
                    for item in witness.values()
                ):
                    raise ValueError("native relation witness is invalid")
        if not isinstance(case["required"], list):
            raise ValueError("native required entries are invalid")
        for raw_required in case["required"]:
            required = _require_keys(
                raw_required,
                _REQUIRED_KEYS,
                "native required entry",
            )
            rank = required["rank"]
            if (
                not isinstance(required["path"], str)
                or not required["path"]
                or not isinstance(required["role"], str)
                or not required["role"]
                or required["state"] not in ("selected", "not_selected")
                or (
                    rank is not None
                    and _require_nonnegative_integer(
                        rank,
                        "native required rank",
                    )
                    <= 0
                )
                or (rank is None) != (
                    required["state"] == "not_selected"
                )
            ):
                raise ValueError("native required entry is invalid")
    return set(value)


def _validate_native_witnesses(
    value: object,
    case_ids: set[str],
) -> None:
    if not isinstance(value, dict):
        raise ValueError("native witnesses are invalid")
    for raw_witness in value.values():
        if not isinstance(raw_witness, dict):
            raise ValueError("native witness is invalid")
        mode = raw_witness.get("mode")
        expected = (
            {"mode", "case", "covered_required", "item_count"}
            if mode == "context_pack"
            else {
                "mode",
                "case",
                "covered_required",
                "retrieval_calls",
                "final_unique_paths",
            }
        )
        witness = _require_keys(
            raw_witness,
            expected,
            "native witness",
        )
        if (
            mode not in ("context_pack", "exploration")
            or witness["case"] not in case_ids
            or not isinstance(witness["covered_required"], list)
            or not all(
                isinstance(path, str)
                for path in witness["covered_required"]
            )
        ):
            raise ValueError("native witness is invalid")
        for field in expected - {
            "mode",
            "case",
            "covered_required",
        }:
            _require_nonnegative_integer(
                witness[field],
                "native witness count",
            )


def _validate_native_capture(
    capture: object,
    provider: str,
    requests: dict,
    timing: dict,
) -> None:
    capture = _require_keys(
        capture,
        _NATIVE_CAPTURE_KEYS,
        "native capture",
    )
    if capture["schema_version"] != 4:
        raise ValueError("native envelope requires schema-v4 capture")
    _validate_implementation(capture["implementation"])
    environment = _require_keys(
        capture["environment"],
        {"python_version", "sqlite_version", "numpy_version"},
        "native environment",
    )
    if not all(
        isinstance(version, str) and version
        for version in environment.values()
    ):
        raise ValueError("native environment is invalid")
    _require_sha256(capture["manifest_sha256"], "native manifest SHA")
    identity = _require_keys(
        capture["embedding_identity"],
        _NATIVE_IDENTITY_KEYS,
        "native embedding identity",
    )
    if identity["provider"] != provider:
        raise ValueError("native capture provider mismatch")
    if provider == "hash":
        if (
            identity.get("configured_model") != "hash-v1"
            or identity.get("dimensions") != 384
            or identity.get("static_config_identity")
            != HASH_CONFIG_IDENTITY
            or identity.get("descriptor_identity")
            != HASH_CONFIG_IDENTITY
            or any(
                identity.get(field) is not None
                for field in (
                    "canonical_model",
                    "model_digest",
                    "ollama_version",
                    "input_transform_id",
                    "pre_attestation",
                    "post_attestation",
                )
            )
        ):
            raise ValueError("native hash embedding identity mismatch")
    else:
        pre = _validate_attestation(identity.get("pre_attestation"))
        post = _validate_attestation(identity.get("post_attestation"))
        if (
            pre != post
            or identity.get("configured_model") != BGE_MODEL
            or identity.get("dimensions") != BGE_DIMENSIONS
            or identity.get("static_config_identity")
            != BGE_CONFIG_IDENTITY
            or identity.get("descriptor_identity")
            != pre["embedding_identity"]
            or identity.get("canonical_model")
            != pre["canonical_model"]
            or identity.get("model_digest") != pre["model_digest"]
            or identity.get("ollama_version") != pre["ollama_version"]
            or identity.get("input_transform_id")
            != pre["input_transform_id"]
            or any(requests[repo] <= 0 for repo in ("redink", "daily"))
        ):
            raise ValueError("native BGE embedding identity mismatch")
    if capture.get("embedding_requests") != requests:
        raise ValueError("native capture request counts mismatch")
    if capture.get("timing") != timing:
        raise ValueError("native capture timing mismatch")
    _validate_native_repositories(capture["repositories"])
    case_ids = _validate_native_cases(capture["cases"])
    if set(timing["query_case_min_seconds"]) != case_ids:
        raise ValueError("native timing cases do not match capture cases")
    _validate_native_witnesses(capture["witnesses"], case_ids)


def _validate_protected_inputs(value: object) -> dict:
    protected = _require_keys(
        value, set(_FROZEN_INPUTS), "protected inputs"
    )
    for relative, expected in _FROZEN_INPUTS.items():
        record = _require_keys(
            protected[relative], {"bytes", "sha256"}, "protected input"
        )
        if record != expected:
            raise ValueError("protected input mismatch")
    return protected


def _verify_implementation_root(
    payload: dict,
    implementation_root: Path,
    expected_candidate_commit: str | None,
) -> None:
    root = implementation_root.resolve()
    runner = payload["runner"]
    runner_path = root / runner["path"]
    if not runner_path.is_file() or _sha256_path(runner_path) != runner["sha256"]:
        raise ValueError("runner mismatch")
    for name, record in payload["module_origins"].items():
        origin = root / record["path"]
        if not origin.is_file() or _sha256_path(origin) != record["sha256"]:
            raise ValueError(f"module origin mismatch: {name}")

    if payload["mode"] == "legacy-baseline":
        head = _git(root, "rev-parse", "HEAD")
        branch = _git(root, "symbolic-ref", "-q", "HEAD", check=False)
        dirty = _git(root, "status", "--porcelain", "--untracked-files=all")
        if (
            head != BASELINE_COMMIT
            or branch
            or dirty
            or runner["sha256"] != LEGACY_RUNNER_SHA256
        ):
            raise ValueError("legacy mode requires a clean detached baseline")
        return

    actual = _verify_native_candidate(
        root,
        expected_candidate_commit,
    )
    capture_implementation = payload["capture"].get("implementation")
    if (
        payload["implementation"]["pre"] != actual
        or payload["implementation"]["post"] != actual
        or capture_implementation != actual
    ):
        raise ValueError("native implementation identity mismatch")

    for relative, expected in _FROZEN_INPUTS.items():
        path = root / relative
        if (
            not path.is_file()
            or len(path.read_bytes()) != expected["bytes"]
            or _sha256_path(path) != expected["sha256"]
        ):
            raise ValueError("protected input mismatch")


def validate_capture_envelope(
    payload: dict[str, object],
    implementation_root: Path | None = None,
    *,
    expected_candidate_commit: str | None = None,
) -> None:
    envelope = _require_keys(payload, _ENVELOPE_KEYS, "capture envelope")
    if _privacy_failure(envelope):
        raise ValueError("capture envelope violates privacy contract")
    if envelope["schema_version"] != ENVELOPE_SCHEMA:
        raise ValueError("unsupported measurement envelope")
    if envelope["mode"] not in ("legacy-baseline", "native"):
        raise ValueError("unsupported measurement mode")
    if envelope["provider"] not in ("hash", "bge"):
        raise ValueError("unsupported measurement provider")

    harness = _validate_file_record(envelope["harness"], "harness")
    runner = _validate_file_record(envelope["runner"], "runner")
    if harness["path"] != "tests/p13_bge_provider_measurement.py":
        raise ValueError("harness path mismatch")
    if harness["sha256"] != _sha256_path(_HARNESS_PATH):
        raise ValueError("harness SHA mismatch")
    if runner["path"] != "tests/p8_real_python_graphs_acceptance.py":
        raise ValueError("runner path mismatch")

    implementation = _require_keys(
        envelope["implementation"], {"pre", "post"}, "implementation phases"
    )
    pre_implementation = _validate_implementation(implementation["pre"])
    post_implementation = _validate_implementation(implementation["post"])
    if pre_implementation != post_implementation:
        raise ValueError("implementation changed during capture")

    origins = _require_keys(
        envelope["module_origins"], _ORIGIN_KEYS, "module origins"
    )
    for name, record in origins.items():
        _validate_file_record(record, f"module origin {name}")
    requests = _validate_requests(envelope["embedding_requests"])
    timing = _validate_timing(envelope["timing"])
    _validate_protected_inputs(envelope["protected_inputs"])

    provider = envelope["provider"]
    mode = envelope["mode"]
    attestation = _require_keys(
        envelope["attestation"], {"pre", "post"}, "attestation phases"
    )
    if provider == "hash":
        if (
            mode != "native"
            or envelope["transform_id"] is not None
            or attestation != {"pre": None, "post": None}
            or any(requests[key] != 0 for key in _REQUEST_KEYS)
        ):
            raise ValueError("hash envelope must be offline")
    else:
        pre_attestation = _validate_attestation(attestation["pre"])
        post_attestation = _validate_attestation(attestation["post"])
        if pre_attestation != post_attestation:
            raise ValueError("runtime attestation changed during capture")
        expected_transform = (
            LEGACY_TRANSFORM if mode == "legacy-baseline" else BGE_TRANSFORM
        )
        if envelope["transform_id"] != expected_transform:
            raise ValueError("capture transform mismatch")

    capture = envelope["capture"]
    if mode == "legacy-baseline":
        if (
            provider != "bge"
            or not isinstance(capture, dict)
            or capture.get("schema_version") != 3
            or pre_implementation["base_commit"] != BASELINE_COMMIT
            or pre_implementation["dirty"]
            or runner["sha256"] != LEGACY_RUNNER_SHA256
        ):
            raise ValueError("legacy envelope is invalid")
    else:
        _validate_native_capture(capture, provider, requests, timing)
        if capture.get("implementation") != pre_implementation:
            raise ValueError("native implementation identity mismatch")
        if envelope["transform_id"] == LEGACY_TRANSFORM:
            raise ValueError("native capture retained the legacy transform")

    if implementation_root is not None:
        _verify_implementation_root(
            envelope,
            implementation_root,
            expected_candidate_commit,
        )


@contextmanager
def legacy_query_timing_wrapper(
    target_module: object,
    measured_call_count: int,
) -> Iterator[list[float]]:
    original = getattr(target_module, "query_repository")
    samples: list[float] = []

    def measured(*args: object, **kwargs: object) -> object:
        if len(samples) >= measured_call_count:
            return original(*args, **kwargs)
        started = time.perf_counter()
        try:
            return original(*args, **kwargs)
        finally:
            samples.append(time.perf_counter() - started)

    setattr(target_module, "query_repository", measured)
    try:
        yield samples
    finally:
        setattr(target_module, "query_repository", original)


@contextmanager
def embedding_request_wrapper(
    provider_class: type,
    *,
    repository: Callable[[], str],
    counts: dict[str, int],
) -> Iterator[None]:
    original = provider_class._embed_batch

    def counted(*args: object, **kwargs: object) -> object:
        current = repository()
        if current not in ("redink", "daily"):
            raise ValueError("embedding request has no repository attribution")
        counts[current] += 1
        counts["total"] += 1
        return original(*args, **kwargs)

    provider_class._embed_batch = counted
    try:
        yield
    finally:
        provider_class._embed_batch = original


@contextmanager
def _temporary_attribute(
    target: object,
    name: str,
    replacement: object,
) -> Iterator[None]:
    original = getattr(target, name)
    setattr(target, name, replacement)
    try:
        yield
    finally:
        setattr(target, name, original)


@contextmanager
def _preserve_primary_during_cleanup(
    cleanup: Callable[[], object],
    label: str,
) -> Iterator[None]:
    primary_error: BaseException | None = None
    try:
        yield
    except BaseException as error:
        primary_error = error
        raise
    finally:
        try:
            cleanup()
        except BaseException as cleanup_error:
            if primary_error is None:
                raise
            primary_error.add_note(
                f"{label} also failed ({type(cleanup_error).__name__})"
            )


def _runtime_attestation() -> dict[str, object]:
    import requests

    session = requests.Session()
    with _preserve_primary_during_cleanup(
        session.close,
        "HTTP session cleanup",
    ):
        session.trust_env = False
        version_response = session.get(
            f"{_OLLAMA_ROOT}/api/version",
            timeout=5,
        )
        version_response.raise_for_status()
        tags_response = session.get(
            f"{_OLLAMA_ROOT}/api/tags",
            timeout=5,
        )
        tags_response.raise_for_status()
        version_payload = version_response.json()
        tags_payload = tags_response.json()
        raw_version = version_payload.get("version")
        models = tags_payload.get("models")
        if not isinstance(raw_version, str) or not raw_version:
            raise ValueError("Ollama version response is invalid")
        if not isinstance(models, list):
            raise ValueError("Ollama model response is invalid")
        matches = [
            model
            for model in models
            if isinstance(model, dict)
            and (
                model.get("name") == BGE_CANONICAL_MODEL
                or model.get("model") == BGE_CANONICAL_MODEL
            )
        ]
        if len(matches) != 1:
            raise ValueError("exactly one canonical BGE model is required")
        digest = _require_sha256(matches[0].get("digest"), "model digest")
        version_sha256 = hashlib.sha256(
            raw_version.encode("utf-8")
        ).hexdigest()
        attestation = {
            "configured_model": BGE_MODEL,
            "canonical_model": BGE_CANONICAL_MODEL,
            "model_digest": digest,
            "ollama_version": raw_version,
            "base_url": _OLLAMA_ROOT,
            "dimensions": BGE_DIMENSIONS,
            "input_transform_id": BGE_TRANSFORM,
            "embedding_identity": (
                f"bge-ollama-v1:{BGE_CONFIG_IDENTITY}:{digest}:"
                f"{version_sha256}:{BGE_TRANSFORM}"
            ),
        }
        _validate_attestation(attestation)
        return attestation


def _warm_bge() -> None:
    import requests

    session = requests.Session()
    with _preserve_primary_during_cleanup(
        session.close,
        "HTTP session cleanup",
    ):
        session.trust_env = False
        response = session.post(
            f"{_OLLAMA_ROOT}/api/embed",
            json={
                "model": BGE_CANONICAL_MODEL,
                "input": ["p13-bge-provider-warmup"],
                "truncate": False,
            },
            timeout=60,
        )
        response.raise_for_status()
        payload = response.json()
        embeddings = payload.get("embeddings")
        if (
            not isinstance(embeddings, list)
            or len(embeddings) != 1
            or not isinstance(embeddings[0], list)
            or len(embeddings[0]) != BGE_DIMENSIONS
            or any(
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
                for value in embeddings[0]
            )
            or not any(float(value) != 0.0 for value in embeddings[0])
        ):
            raise ValueError("BGE warmup response is invalid")


def _module_origins(
    implementation_root: Path,
    *,
    package: object,
    bge_module: object,
    runner: object,
) -> dict[str, dict[str, str]]:
    root = implementation_root.resolve()
    expected = {
        "context_search_tool": (
            package,
            Path("src/context_search_tool/__init__.py"),
        ),
        "context_search_tool.embeddings_bge": (
            bge_module,
            Path("src/context_search_tool/embeddings_bge.py"),
        ),
        "p8_real_python_graphs_acceptance": (
            runner,
            Path("tests/p8_real_python_graphs_acceptance.py"),
        ),
    }
    records: dict[str, dict[str, str]] = {}
    for name, (module, relative) in expected.items():
        origin = Path(getattr(module, "__file__", "")).resolve()
        target = (root / relative).resolve()
        if origin != target or not target.is_file():
            raise ValueError("capture module did not resolve inside target")
        records[name] = {
            "path": relative.as_posix(),
            "sha256": _sha256_path(target),
        }
    return records


def _legacy_timing(
    capture: dict[str, object],
    samples: list[float],
    repetitions: int,
) -> dict[str, object]:
    repetitions = max(1, repetitions)
    if len(samples) != 18 * repetitions:
        raise ValueError("legacy query timing sample count is invalid")
    case_ids = list(capture["cases"])
    minima = {
        case_id: round(
            min(
                samples[
                    index * repetitions : (index + 1) * repetitions
                ]
            ),
            9,
        )
        for index, case_id in enumerate(case_ids)
    }
    ordered = [minima[case_id] for case_id in case_ids]
    return {
        "index_seconds": {
            repository: float(
                capture["timing"][f"index_seconds_{repository}"]
            )
            for repository in ("redink", "daily")
        },
        "query_case_min_seconds": minima,
        "query_p50_seconds": _nearest_rank(ordered, 0.50),
        "query_p95_seconds": _nearest_rank(ordered, 0.95),
    }


def _capture_legacy(
    runner: object,
    implementation_root: Path,
    sources: Path,
    raw_output: Path,
    repetitions: int,
) -> tuple[dict[str, object], dict[str, int], dict[str, object]]:
    retrieval = importlib.import_module("context_search_tool.retrieval")
    bge_module = importlib.import_module(
        "context_search_tool.embeddings_bge"
    )
    provider_class = bge_module.BGEEmbeddingProvider
    identity = runner.identity
    current = {"repository": None}
    counts = {"redink": 0, "daily": 0, "total": 0}
    original_validate = identity.validate_protected_source
    original_query = retrieval.query_repository

    def attributed_validate(
        source_root: Path,
        *args: object,
        **kwargs: object,
    ) -> object:
        by_name = {
            "RedInk": "redink",
            "daily_stock_analysis": "daily",
        }
        current["repository"] = by_name.get(Path(source_root).name)
        if current["repository"] is None:
            raise ValueError("protected source has no repository attribution")
        return original_validate(source_root, *args, **kwargs)

    def attributed_query(
        workspace: Path,
        *args: object,
        **kwargs: object,
    ) -> object:
        by_name = {
            "RedInk": "redink",
            "daily_stock_analysis": "daily",
        }
        current["repository"] = by_name.get(Path(workspace).name)
        if current["repository"] is None:
            raise ValueError("query has no repository attribution")
        return original_query(workspace, *args, **kwargs)

    with ExitStack() as stack:
        stack.enter_context(
            _temporary_attribute(
                identity,
                "validate_protected_source",
                attributed_validate,
            )
        )
        stack.enter_context(
            _temporary_attribute(
                retrieval,
                "query_repository",
                attributed_query,
            )
        )
        stack.enter_context(
            embedding_request_wrapper(
                provider_class,
                repository=lambda: str(current["repository"]),
                counts=counts,
            )
        )
        samples = stack.enter_context(
            legacy_query_timing_wrapper(
                retrieval,
                measured_call_count=18 * max(1, repetitions),
            )
        )
        capture = runner.capture(
            implementation_root,
            sources,
            raw_output,
            timing_reps=repetitions,
            embedding="bge",
        )
    return capture, counts, _legacy_timing(
        capture,
        samples,
        repetitions,
    )


def _capture_child(
    *,
    implementation_root: Path,
    sources: Path,
    output_path: Path,
    mode: str,
    provider: str,
    repetitions: int,
    expected_candidate_commit: str | None = None,
) -> dict[str, object]:
    implementation_root = implementation_root.resolve()
    if mode == "native":
        _verify_native_candidate(
            implementation_root,
            expected_candidate_commit,
        )
    package = importlib.import_module("context_search_tool")
    bge_module = importlib.import_module(
        "context_search_tool.embeddings_bge"
    )
    runner = importlib.import_module("p8_real_python_graphs_acceptance")
    origins = _module_origins(
        implementation_root,
        package=package,
        bge_module=bge_module,
        runner=runner,
    )
    expected_schema = 3 if mode == "legacy-baseline" else 4
    if getattr(runner, "CAPTURE_SCHEMA_VERSION", None) != expected_schema:
        raise ValueError("capture mode does not match target runner")

    pre_implementation = runner.implementation_identity(
        implementation_root
    )
    pre_attestation = _runtime_attestation() if provider == "bge" else None
    raw_output = output_path.with_suffix(".capture.json")
    if mode == "legacy-baseline":
        if provider != "bge":
            raise ValueError("legacy capture requires BGE")
        capture, requests, timing = _capture_legacy(
            runner,
            implementation_root,
            sources,
            raw_output,
            repetitions,
        )
    else:
        capture = runner.capture(
            implementation_root,
            sources,
            raw_output,
            timing_reps=repetitions,
            embedding=provider,
        )
        requests = copy.deepcopy(capture["embedding_requests"])
        timing = copy.deepcopy(capture["timing"])
    post_attestation = (
        _runtime_attestation() if provider == "bge" else None
    )
    if pre_attestation != post_attestation:
        raise ValueError("runtime attestation changed during capture")
    post_implementation = runner.implementation_identity(
        implementation_root
    )
    if pre_implementation != post_implementation:
        raise ValueError("implementation changed during capture")

    if mode == "native" and capture["implementation"] != pre_implementation:
        raise ValueError("native capture implementation mismatch")
    payload: dict[str, object] = {
        "schema_version": ENVELOPE_SCHEMA,
        "mode": mode,
        "provider": provider,
        "harness": {
            "path": "tests/p13_bge_provider_measurement.py",
            "sha256": _sha256_path(_HARNESS_PATH),
        },
        "runner": origins["p8_real_python_graphs_acceptance"],
        "implementation": {
            "pre": pre_implementation,
            "post": post_implementation,
        },
        "module_origins": origins,
        "transform_id": (
            None
            if provider == "hash"
            else (
                LEGACY_TRANSFORM
                if mode == "legacy-baseline"
                else BGE_TRANSFORM
            )
        ),
        "attestation": {
            "pre": pre_attestation,
            "post": post_attestation,
        },
        "embedding_requests": requests,
        "timing": timing,
        "capture": capture,
        "protected_inputs": copy.deepcopy(_FROZEN_INPUTS),
    }
    validate_capture_envelope(
        payload,
        implementation_root=implementation_root,
        expected_candidate_commit=expected_candidate_commit,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(_canonical(payload), encoding="utf-8")
    raw_output.unlink(missing_ok=True)
    return payload


def _run_capture_process(
    *,
    implementation_root: Path,
    sources: Path,
    mode: str,
    provider: str,
    repetitions: int = _DEFAULT_TIMING_REPETITIONS,
    capture_path: Path | None = None,
    expected_candidate_commit: str | None = None,
) -> dict[str, object]:
    if capture_path is None:
        with tempfile.TemporaryDirectory(
            prefix="cst-p13-capture-"
        ) as raw_dir:
            return _run_capture_process(
                implementation_root=implementation_root,
                sources=sources,
                mode=mode,
                provider=provider,
                repetitions=repetitions,
                capture_path=Path(raw_dir) / "capture-envelope.json",
                expected_candidate_commit=expected_candidate_commit,
            )

    if mode == "native":
        _verify_native_candidate(
            implementation_root,
            expected_candidate_commit,
        )
    capture_path.parent.mkdir(parents=True, exist_ok=True)
    pre_attestation = None
    if provider == "bge":
        _warm_bge()
        pre_attestation = _runtime_attestation()
    environment = os.environ.copy()
    environment["PYTHONPATH"] = os.pathsep.join(
        (
            str(implementation_root / "src"),
            str(implementation_root / "tests"),
        )
    )
    command = [
        sys.executable,
        "-P",
        str(_HARNESS_PATH),
        "_capture-child",
        "--implementation-root",
        str(implementation_root),
    ]
    if mode == "native":
        command.extend(
            (
                "--expected-candidate-commit",
                _require_expected_candidate_commit(
                    expected_candidate_commit
                ),
            )
        )
    command.extend(
        (
            "--sources",
            str(sources),
            "--output",
            str(capture_path),
            "--mode",
            mode,
            "--provider",
            provider,
            "--repetitions",
            str(repetitions),
        )
    )
    completed = subprocess.run(
        tuple(command),
        cwd=implementation_root,
        env=environment,
        text=True,
        capture_output=True,
        check=True,
    )
    if capture_path.is_file():
        payload = json.loads(capture_path.read_text(encoding="utf-8"))
    else:
        payload = json.loads(completed.stdout)
    post_attestation = (
        _runtime_attestation() if provider == "bge" else None
    )
    if pre_attestation != post_attestation:
        raise ValueError("runtime attestation changed across capture child")
    payload["attestation"] = {
        "pre": pre_attestation,
        "post": post_attestation,
    }
    if provider == "bge" and mode == "native":
        identity = payload["capture"]["embedding_identity"]
        if (
            identity["pre_attestation"] != pre_attestation
            or identity["post_attestation"] != post_attestation
        ):
            raise ValueError("native runtime identity changed across capture")
    if provider == "bge" and mode == "legacy-baseline":
        if (
            payload["capture"]["embedding_identity"]["digest"]
            != pre_attestation["model_digest"]
        ):
            raise ValueError("legacy model digest changed across capture")
    validate_capture_envelope(
        payload,
        implementation_root=implementation_root,
        expected_candidate_commit=(
            expected_candidate_commit if mode == "native" else None
        ),
    )
    capture_path.write_text(_canonical(payload), encoding="utf-8")
    return payload


def _median(values: list[float | int]) -> float | int:
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


def _non_timing_payload(payload: dict[str, object]) -> dict[str, object]:
    normalized = copy.deepcopy(payload)
    normalized.pop("timing", None)
    normalized.pop("implementation", None)
    capture = normalized.get("capture")
    if isinstance(capture, dict):
        capture.pop("timing", None)
        capture.pop("implementation", None)
    return normalized


def _input_hashes(
    captures: list[dict[str, object]],
    labels: tuple[str, str],
    classifier: Callable[[dict[str, object]], str],
) -> dict[str, list[str]]:
    return {
        label: [
            _capture_sha256(capture)
            for capture in captures
            if classifier(capture) == label
        ]
        for label in labels
    }


def _gate(
    *,
    raw_values: object,
    numerator: int | float,
    denominator: int | float,
    ratio: float | None,
    threshold: int | float,
    passed: bool,
    input_capture_sha256: dict[str, list[str]],
    evidence_path: str,
) -> dict[str, object]:
    result = {
        "raw_values": raw_values,
        "numerator": numerator,
        "denominator": denominator,
        "ratio": ratio,
        "threshold": threshold,
        "passed": bool(passed),
        "input_capture_sha256": copy.deepcopy(input_capture_sha256),
        "evidence_path": evidence_path,
    }
    assert set(result) == _GATE_KEYS
    return result


def _engineering_side(capture: dict[str, object]) -> str:
    return (
        "baseline"
        if capture.get("mode") == "legacy-baseline"
        else "candidate"
    )


def _engineering_statistics(
    captures: list[dict[str, object]],
) -> dict[str, dict[str, object]]:
    statistics: dict[str, dict[str, object]] = {}
    for side in ("baseline", "candidate"):
        selected = [
            capture
            for capture in captures
            if _engineering_side(capture) == side
        ]
        index_redink = [
            capture["timing"]["index_seconds"]["redink"]
            for capture in selected
        ]
        index_daily = [
            capture["timing"]["index_seconds"]["daily"]
            for capture in selected
        ]
        index_total = [
            capture["timing"]["index_seconds"]["redink"]
            + capture["timing"]["index_seconds"]["daily"]
            for capture in selected
        ]
        query_p95 = [
            capture["timing"]["query_p95_seconds"]
            for capture in selected
        ]
        request_redink = [
            capture["embedding_requests"]["redink"]
            for capture in selected
        ]
        request_daily = [
            capture["embedding_requests"]["daily"]
            for capture in selected
        ]
        request_total = [
            capture["embedding_requests"]["total"]
            for capture in selected
        ]
        statistics[side] = {
            "index_seconds": {
                "redink": _median(index_redink),
                "daily": _median(index_daily),
                "total": _median(index_total),
            },
            "query_p95_seconds": _median(query_p95),
            "embedding_requests": {
                "redink": _median(request_redink),
                "daily": _median(request_daily),
                "total": _median(request_total),
            },
        }
    return statistics


def _require_stable_implementation(
    captures: list[dict[str, object]],
    classifier: Callable[[dict[str, object]], str],
) -> None:
    identities: dict[str, dict[str, object]] = {}
    for capture in captures:
        label = classifier(capture)
        current = capture["implementation"]["pre"]
        previous = identities.setdefault(label, current)
        if current != previous:
            raise ValueError("implementation identity changed across captures")


def compare_engineering(
    captures: list[dict[str, object]],
    output_path: Path,
) -> dict[str, object]:
    if len(captures) != 6:
        raise ValueError("engineering comparison requires three capture pairs")
    for capture in captures:
        validate_capture_envelope(capture)
    _require_stable_implementation(captures, _engineering_side)
    sides = [_engineering_side(capture) for capture in captures]
    pair_order = [sides[index : index + 2] for index in range(0, 6, 2)]
    if pair_order != [
        ["baseline", "candidate"],
        ["candidate", "baseline"],
        ["baseline", "candidate"],
    ]:
        raise ValueError("engineering capture pair order is invalid")

    statistics = _engineering_statistics(captures)
    baseline = statistics["baseline"]
    candidate = statistics["candidate"]
    ratios = {
        "index_redink": (
            candidate["index_seconds"]["redink"]
            / baseline["index_seconds"]["redink"]
        ),
        "index_daily": (
            candidate["index_seconds"]["daily"]
            / baseline["index_seconds"]["daily"]
        ),
        "index_total": (
            candidate["index_seconds"]["total"]
            / baseline["index_seconds"]["total"]
        ),
        "query_p95": (
            candidate["query_p95_seconds"]
            / baseline["query_p95_seconds"]
        ),
    }
    baseline_captures = [
        capture
        for capture in captures
        if _engineering_side(capture) == "baseline"
    ]
    stability_values = {
        "index_redink": [
            capture["timing"]["index_seconds"]["redink"]
            for capture in baseline_captures
        ],
        "index_daily": [
            capture["timing"]["index_seconds"]["daily"]
            for capture in baseline_captures
        ],
        "query_p95": [
            capture["timing"]["query_p95_seconds"]
            for capture in baseline_captures
        ],
    }
    baseline_stability = {
        name: max(values) / min(values) - 1.0
        for name, values in stability_values.items()
    }
    capture_hashes = _input_hashes(
        captures,
        ("baseline", "candidate"),
        _engineering_side,
    )
    evidence_path = output_path.name
    gates: dict[str, dict[str, object]] = {}

    for repository in ("redink", "daily"):
        name = f"baseline_index_stability_{repository}"
        values = stability_values[f"index_{repository}"]
        ratio = baseline_stability[f"index_{repository}"]
        gates[name] = _gate(
            raw_values=values,
            numerator=max(values),
            denominator=min(values),
            ratio=ratio,
            threshold=0.10,
            passed=ratio <= 0.10 + _FLOAT_COMPARISON_EPSILON,
            input_capture_sha256=capture_hashes,
            evidence_path=evidence_path,
        )
    query_values = stability_values["query_p95"]
    gates["baseline_query_p95_stability"] = _gate(
        raw_values=query_values,
        numerator=max(query_values),
        denominator=min(query_values),
        ratio=baseline_stability["query_p95"],
        threshold=0.15,
        passed=(
            baseline_stability["query_p95"]
            <= 0.15 + _FLOAT_COMPARISON_EPSILON
        ),
        input_capture_sha256=capture_hashes,
        evidence_path=evidence_path,
    )

    for repository in ("redink", "daily", "total"):
        numerator = candidate["index_seconds"][repository]
        denominator = baseline["index_seconds"][repository]
        ratio = numerator / denominator
        gates[f"candidate_index_ratio_{repository}"] = _gate(
            raw_values={
                "baseline": denominator,
                "candidate": numerator,
            },
            numerator=numerator,
            denominator=denominator,
            ratio=ratio,
            threshold=1.10,
            passed=ratio <= 1.10 + _FLOAT_COMPARISON_EPSILON,
            input_capture_sha256=capture_hashes,
            evidence_path=evidence_path,
        )
    query_numerator = candidate["query_p95_seconds"]
    query_denominator = baseline["query_p95_seconds"]
    gates["candidate_query_p95_ratio"] = _gate(
        raw_values={
            "baseline": query_denominator,
            "candidate": query_numerator,
        },
        numerator=query_numerator,
        denominator=query_denominator,
        ratio=query_numerator / query_denominator,
        threshold=1.15,
        passed=(
            query_numerator / query_denominator
            <= 1.15 + _FLOAT_COMPARISON_EPSILON
        ),
        input_capture_sha256=capture_hashes,
        evidence_path=evidence_path,
    )

    for repository in ("redink", "daily"):
        numerator = candidate["embedding_requests"][repository]
        denominator = baseline["embedding_requests"][repository]
        ratio = numerator / denominator
        gates[f"requests_non_increasing_{repository}"] = _gate(
            raw_values={
                "baseline": denominator,
                "candidate": numerator,
            },
            numerator=numerator,
            denominator=denominator,
            ratio=ratio,
            threshold=1.0,
            passed=ratio <= 1.0 + _FLOAT_COMPARISON_EPSILON,
            input_capture_sha256=capture_hashes,
            evidence_path=evidence_path,
        )
    request_numerator = candidate["embedding_requests"]["total"]
    request_denominator = baseline["embedding_requests"]["total"]
    gates["requests_strictly_lower_total"] = _gate(
        raw_values={
            "baseline": request_denominator,
            "candidate": request_numerator,
        },
        numerator=request_numerator,
        denominator=request_denominator,
        ratio=request_numerator / request_denominator,
        threshold=1.0,
        passed=request_numerator < request_denominator,
        input_capture_sha256=capture_hashes,
        evidence_path=evidence_path,
    )

    mismatched = 0
    for side in ("baseline", "candidate"):
        rows = [
            _non_timing_payload(capture)
            for capture in captures
            if _engineering_side(capture) == side
        ]
        mismatched += sum(row != rows[0] for row in rows[1:])
    gates["same_side_non_timing"] = _gate(
        raw_values={"mismatched_captures": mismatched},
        numerator=mismatched,
        denominator=0,
        ratio=None,
        threshold=0,
        passed=mismatched == 0,
        input_capture_sha256=capture_hashes,
        evidence_path=evidence_path,
    )
    assert set(gates) == _ENGINEERING_GATE_KEYS

    stability_names = {
        "baseline_index_stability_redink",
        "baseline_index_stability_daily",
        "baseline_query_p95_stability",
    }
    if any(not gates[name]["passed"] for name in stability_names):
        disposition = "blocked"
    elif all(gate["passed"] for gate in gates.values()):
        disposition = "pass"
    else:
        disposition = "fail"
    report = {
        "pair_order": pair_order,
        "statistics": statistics,
        "ratios": {"candidate_over_baseline": ratios},
        "baseline_stability": baseline_stability,
        "gates": gates,
        "disposition": disposition,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(_canonical(report), encoding="utf-8")
    return report


def _quality_statistics(capture: dict[str, object]) -> dict[str, object]:
    required: dict[tuple[str, str], bool] = {}
    noise = 0
    selected_total = 0
    for case_id, case in capture["capture"]["cases"].items():
        relevant = {
            required_item["path"] for required_item in case["required"]
        } | set(case["contextual"])
        for required_item in case["required"]:
            rank = required_item["rank"]
            required[(case_id, required_item["path"])] = (
                rank is not None and rank <= 12
            )
        for selected in case["selected"]:
            selected_total += 1
            if selected["path"] not in relevant:
                noise += 1
    return {
        "required": required,
        "recall_at_12": (
            sum(required.values()) / len(required) if required else 0.0
        ),
        "noise_ratio": noise / selected_total if selected_total else 0.0,
    }


def _product_provider(capture: dict[str, object]) -> str:
    return str(capture["provider"])


def _product_candidate_identity(
    captures: list[dict[str, object]],
) -> dict[str, object]:
    expected: dict[str, object] | None = None
    try:
        for capture in captures:
            phases = _require_keys(
                capture["implementation"],
                {"pre", "post"},
                "candidate implementation phases",
            )
            pre = _validate_implementation(phases["pre"])
            post = _validate_implementation(phases["post"])
            native = _validate_implementation(
                capture["capture"]["implementation"]
            )
            if pre != post or pre != native:
                raise ValueError(
                    "candidate implementation identity mismatch"
                )
            if expected is None:
                expected = pre
            elif pre != expected:
                raise ValueError(
                    "candidate implementation identity mismatch"
                )
    except (KeyError, TypeError) as error:
        raise ValueError(
            "candidate implementation identity mismatch"
        ) from error
    if expected is None:
        raise ValueError("candidate implementation identity mismatch")
    return copy.deepcopy(expected)


def compare_product(
    captures: list[dict[str, object]],
    p1_profiles: dict[str, object],
    output_path: Path,
) -> dict[str, object]:
    if (
        len(captures) != 4
        or [_product_provider(capture) for capture in captures]
        != ["hash", "hash", "bge", "bge"]
    ):
        raise ValueError("product comparison requires hash, hash, BGE, BGE")
    for capture in captures:
        validate_capture_envelope(capture)
    _product_candidate_identity(captures)

    grouped = {
        provider: [
            capture
            for capture in captures
            if _product_provider(capture) == provider
        ]
        for provider in ("hash", "bge")
    }
    provider_quality = {
        provider: _quality_statistics(rows[0])
        for provider, rows in grouped.items()
    }
    statistics: dict[str, dict[str, object]] = {}
    for provider, rows in grouped.items():
        statistics[provider] = {
            "index_seconds": {
                repository: _median(
                    [
                        row["timing"]["index_seconds"][repository]
                        for row in rows
                    ]
                )
                for repository in ("redink", "daily")
            },
            "query_p95_seconds": _median(
                [row["timing"]["query_p95_seconds"] for row in rows]
            ),
            "recall_at_12": provider_quality[provider]["recall_at_12"],
            "noise_ratio": provider_quality[provider]["noise_ratio"],
        }

    hash_required = provider_quality["hash"]["required"]
    bge_required = provider_quality["bge"]["required"]
    newly_keys = [
        key
        for key in hash_required
        if not hash_required[key] and bge_required.get(key, False)
    ]
    lost_keys = [
        key
        for key in hash_required
        if hash_required[key] and not bge_required.get(key, False)
    ]
    newly = sorted({path for _case, path in newly_keys})
    lost = sorted({path for _case, path in lost_keys})
    ratios = {
        "index_redink": (
            statistics["bge"]["index_seconds"]["redink"]
            / statistics["hash"]["index_seconds"]["redink"]
        ),
        "index_daily": (
            statistics["bge"]["index_seconds"]["daily"]
            / statistics["hash"]["index_seconds"]["daily"]
        ),
        "query_p95": (
            statistics["bge"]["query_p95_seconds"]
            / statistics["hash"]["query_p95_seconds"]
        ),
    }
    capture_hashes = _input_hashes(
        captures,
        ("hash", "bge"),
        _product_provider,
    )
    evidence_path = output_path.name
    gates: dict[str, dict[str, object]] = {}

    hash_recall = statistics["hash"]["recall_at_12"]
    bge_recall = statistics["bge"]["recall_at_12"]
    gates["recall_non_decreasing"] = _gate(
        raw_values={"hash": hash_recall, "bge": bge_recall},
        numerator=bge_recall,
        denominator=hash_recall,
        ratio=bge_recall / hash_recall,
        threshold=1.0,
        passed=bge_recall >= hash_recall,
        input_capture_sha256=capture_hashes,
        evidence_path=evidence_path,
    )
    gates["zero_required_loss"] = _gate(
        raw_values={"lost": lost},
        numerator=len(lost),
        denominator=0,
        ratio=None,
        threshold=0,
        passed=not lost,
        input_capture_sha256=capture_hashes,
        evidence_path=evidence_path,
    )
    gates["new_required"] = _gate(
        raw_values={"newly_satisfied": newly},
        numerator=len(newly),
        denominator=1,
        ratio=len(newly) / 1,
        threshold=1,
        passed=len(newly) >= 1,
        input_capture_sha256=capture_hashes,
        evidence_path=evidence_path,
    )
    hash_noise = statistics["hash"]["noise_ratio"]
    bge_noise = statistics["bge"]["noise_ratio"]
    gates["noise_non_increasing"] = _gate(
        raw_values={"hash": hash_noise, "bge": bge_noise},
        numerator=bge_noise,
        denominator=hash_noise,
        ratio=bge_noise / hash_noise if hash_noise else None,
        threshold=1.0,
        passed=bge_noise <= hash_noise,
        input_capture_sha256=capture_hashes,
        evidence_path=evidence_path,
    )

    expected_passed = {
        "p1_vector_bge": 6,
        "p1_hybrid_bge": 6,
    }
    actual_passed = {
        name: (
            profile.get("passed")
            if isinstance(profile, dict)
            else None
        )
        for name, profile in p1_profiles.items()
        if name in expected_passed
    }
    p1_passed = (
        set(p1_profiles) == set(_P1_PROFILES)
        and all(p1_profiles[name] == expected for name, expected in _P1_PROFILES.items())
    )
    minimum_actual = min(
        (
            value
            for value in actual_passed.values()
            if isinstance(value, int) and not isinstance(value, bool)
        ),
        default=0,
    )
    gates["p1_continuity"] = _gate(
        raw_values={
            "expected_passed": expected_passed,
            "actual_passed": actual_passed,
        },
        numerator=minimum_actual,
        denominator=6,
        ratio=minimum_actual / 6,
        threshold=1.0,
        passed=p1_passed,
        input_capture_sha256=capture_hashes,
        evidence_path=evidence_path,
    )
    query_numerator = statistics["bge"]["query_p95_seconds"]
    query_denominator = statistics["hash"]["query_p95_seconds"]
    gates["query_p95_ratio"] = _gate(
        raw_values={"hash": query_denominator, "bge": query_numerator},
        numerator=query_numerator,
        denominator=query_denominator,
        ratio=query_numerator / query_denominator,
        threshold=1.50,
        passed=(
            query_numerator / query_denominator
            <= 1.50 + _FLOAT_COMPARISON_EPSILON
        ),
        input_capture_sha256=capture_hashes,
        evidence_path=evidence_path,
    )

    index_raw = {
        repository: {
            "hash": statistics["hash"]["index_seconds"][repository],
            "bge": statistics["bge"]["index_seconds"][repository],
        }
        for repository in ("redink", "daily")
    }
    worst_repository = max(
        index_raw,
        key=lambda repository: (
            index_raw[repository]["bge"]
            / index_raw[repository]["hash"]
        ),
    )
    worst = index_raw[worst_repository]
    worst_ratio = worst["bge"] / worst["hash"]
    gates["per_repository_index_ratio"] = _gate(
        raw_values=index_raw,
        numerator=worst["bge"],
        denominator=worst["hash"],
        ratio=worst_ratio,
        threshold=50.0,
        passed=all(
            row["bge"] / row["hash"]
            <= 50.0 + _FLOAT_COMPARISON_EPSILON
            for row in index_raw.values()
        ),
        input_capture_sha256=capture_hashes,
        evidence_path=evidence_path,
    )

    mismatched_providers = [
        provider
        for provider, rows in grouped.items()
        if _non_timing_payload(rows[0]) != _non_timing_payload(rows[1])
    ]
    gates["same_provider_non_timing"] = _gate(
        raw_values={"mismatched_providers": mismatched_providers},
        numerator=len(mismatched_providers),
        denominator=0,
        ratio=None,
        threshold=0,
        passed=not mismatched_providers,
        input_capture_sha256=capture_hashes,
        evidence_path=evidence_path,
    )
    assert set(gates) == _PRODUCT_GATE_KEYS
    report = {
        "statistics": statistics,
        "required": {
            "newly_satisfied": newly,
            "lost": lost,
        },
        "ratios": {"bge_over_hash": ratios},
        "p1_profiles": copy.deepcopy(p1_profiles),
        "gates": gates,
        "disposition": (
            "pass" if all(gate["passed"] for gate in gates.values()) else "fail"
        ),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(_canonical(report), encoding="utf-8")
    return report


def _p1_expected_planner(profile: str) -> dict[str, object]:
    hybrid = profile == "p1_hybrid_bge"
    return {
        "enabled": hybrid,
        "provider": "ollama",
        "model": "qwen3.5:4b-mlx",
        "base_url": _OLLAMA_ROOT,
        "use_system_proxy": False,
        "timeout_seconds": 30 if hybrid else 8.0,
        "max_rewritten_queries": 4,
        "max_keywords": 12,
        "max_symbol_hints": 8,
    }


def _p1_catalog_queries() -> dict[tuple[str, str], str]:
    record = P1_QUALITY_INPUTS["fixture_catalog_gold"]
    path = (_ROOT / record["path"]).resolve(strict=True)
    try:
        path.relative_to(_ROOT)
    except ValueError as error:
        raise ValueError("P1 catalog query mismatch") from error
    if not path.is_file() or _sha256_path(path) != record["sha256"]:
        raise ValueError("P1 catalog query mismatch")
    catalog = json.loads(path.read_text(encoding="utf-8"))
    selected: list[tuple[str, str]] = []
    queries: dict[tuple[str, str], str] = {}
    required_profiles = {"p1_vector_bge", "p1_hybrid_bge"}
    try:
        for repository in catalog["repos"]:
            for case in repository["queries"]:
                if required_profiles <= set(case.get("profiles", ())):
                    key = (repository["repo_key"], case["id"])
                    if key in queries:
                        raise ValueError("P1 catalog query mismatch")
                    selected.append(key)
                    queries[key] = case["query"]
    except (KeyError, TypeError) as error:
        raise ValueError("P1 catalog query mismatch") from error
    if (
        tuple(selected) != P1_CASES
        or not all(
            isinstance(query, str) and query
            for query in queries.values()
        )
    ):
        raise ValueError("P1 catalog query mismatch")
    return queries


def _p1_bge_attestation(
    captures: list[dict[str, object]],
) -> tuple[dict[str, object], dict[str, object]]:
    if (
        len(captures) != 4
        or [_product_provider(capture) for capture in captures]
        != ["hash", "hash", "bge", "bge"]
    ):
        raise ValueError("P1 evidence requires product captures")
    for capture in captures:
        validate_capture_envelope(capture)
    implementation = _product_candidate_identity(captures)
    attestations: list[dict[str, object]] = []
    descriptors: list[object] = []
    for capture in captures[2:]:
        attestations.extend(
            (
                capture["attestation"]["pre"],
                capture["attestation"]["post"],
                capture["capture"]["embedding_identity"][
                    "pre_attestation"
                ],
                capture["capture"]["embedding_identity"][
                    "post_attestation"
                ],
            )
        )
        descriptors.append(
            capture["capture"]["embedding_identity"][
                "descriptor_identity"
            ]
        )
    expected_attestation = attestations[0]
    if any(
        attestation != expected_attestation
        for attestation in attestations[1:]
    ) or any(
        descriptor != expected_attestation["embedding_identity"]
        for descriptor in descriptors
    ):
        raise ValueError("P1 evidence BGE attestation mismatch")
    return implementation, copy.deepcopy(expected_attestation)


def _p1_raw_report_path(
    wrapper_root: Path,
    record: object,
) -> Path:
    raw_record = _require_keys(
        record,
        {"path", "sha256"},
        "P1 raw report",
    )
    raw_path_value = raw_record["path"]
    if not isinstance(raw_path_value, str):
        raise ValueError("P1 raw report path is invalid")
    relative = Path(raw_path_value)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("P1 raw report is outside the evidence root")
    expected_sha256 = _require_sha256(
        raw_record["sha256"],
        "P1 raw report SHA",
    )
    path = (wrapper_root / relative).resolve(strict=True)
    try:
        path.relative_to(wrapper_root)
    except ValueError as error:
        raise ValueError(
            "P1 raw report is outside the evidence root"
        ) from error
    if path == wrapper_root or not path.is_file():
        raise ValueError("P1 raw report is not a file")
    if _sha256_path(path) != expected_sha256:
        raise ValueError("P1 raw report SHA mismatch")
    return path


def _p1_raw_case_projection(
    value: object,
    expected_case: tuple[str, str],
) -> tuple[dict[str, object], str]:
    case = _require_keys(value, _P1_RAW_CASE_KEYS, "P1 raw case")
    repo_key, case_id = expected_case
    if (
        case["repo_key"] != repo_key
        or case["case_id"] != case_id
        or not isinstance(case["query"], str)
        or not case["query"]
        or not isinstance(case["tags"], list)
        or not all(isinstance(tag, str) for tag in case["tags"])
        or case["gate"] != "required"
        or case["attempted"] is not True
        or case["known_gap_reason"] is not None
        or not isinstance(case["expanded_tokens"], list)
        or not all(
            isinstance(token, str)
            for token in case["expanded_tokens"]
        )
        or case["status"] not in ("pass", "fail")
        or not isinstance(case["metrics"], dict)
        or not isinstance(case["top_results"], list)
        or not isinstance(case["failures"], list)
        or not all(
            isinstance(failure, str)
            for failure in case["failures"]
        )
        or (case["status"] == "pass" and case["failures"])
        or (
            case["status"] == "fail"
            and not case["failures"]
        )
        or not isinstance(case["variant_retrieval_status"], str)
        or not case["variant_retrieval_status"]
    ):
        raise ValueError("P1 raw case is invalid")
    planner = _require_keys(
        case["planner"],
        _P1_RAW_CASE_PLANNER_KEYS,
        "P1 raw case planner",
    )
    for field in (
        "rewritten_queries",
        "grep_keywords",
        "symbol_hints",
        "discarded_hints",
    ):
        if not isinstance(planner[field], list) or not all(
            isinstance(item, str) for item in planner[field]
        ):
            raise ValueError("P1 raw case planner is invalid")
    if (
        not isinstance(planner["status"], str)
        or not planner["status"]
        or (
            planner["provider"] is not None
            and not isinstance(planner["provider"], str)
        )
        or (
            planner["model"] is not None
            and not isinstance(planner["model"], str)
        )
        or (
            planner["prompt_version"] is not None
            and not isinstance(planner["prompt_version"], str)
        )
        or (
            planner["prompt_hash"] is not None
            and not isinstance(planner["prompt_hash"], str)
        )
        or (
            planner["repo_profile_hash"] is not None
            and not isinstance(planner["repo_profile_hash"], str)
        )
        or not isinstance(planner["repo_profile_truncated"], bool)
    ):
        raise ValueError("P1 raw case planner is invalid")
    if planner["latency_ms"] is not None:
        _require_number(planner["latency_ms"], "P1 planner latency")
    variants = case["query_variants"]
    if not isinstance(variants, list):
        raise ValueError("P1 raw query variants are invalid")
    for value in variants:
        variant = _require_keys(
            value,
            {"variant_id", "text", "source"},
            "P1 raw query variant",
        )
        if not all(
            isinstance(item, str) and item
            for item in variant.values()
        ):
            raise ValueError("P1 raw query variant is invalid")
    failed = case["status"] == "fail"
    return {
        "repo_key": repo_key,
        "case_id": case_id,
        "status": case["status"],
        "required_miss": failed,
    }, case["query"]


def _validate_p1_raw_report(
    value: object,
    profile: str,
    implementation: dict[str, object],
    catalog_queries: dict[tuple[str, str], str],
) -> tuple[list[dict[str, object]], list[str]]:
    report = _require_keys(
        value,
        _P1_RAW_ROOT_KEYS,
        "P1 raw report",
    )
    if (
        report["schema_version"] != 2
        or not isinstance(report["generated_at"], str)
        or not report["generated_at"]
        or report["profile"] != profile
    ):
        raise ValueError("P1 raw report is invalid")
    if _require_keys(
        report["command_args"],
        {"fixture_path", "profile"},
        "P1 raw command arguments",
    ) != {
        "fixture_path": "tests/fixtures/retrieval_quality/queries.json",
        "profile": profile,
    }:
        raise ValueError("P1 raw command provenance mismatch")
    if _require_keys(
        report["tool"],
        {"name", "git_commit"},
        "P1 raw tool",
    ) != {
        "name": "context-search-tool",
        "git_commit": implementation["base_commit"],
    }:
        raise ValueError("P1 raw tool provenance mismatch")
    if _require_keys(
        report["fixture"],
        {
            "path",
            "sha256",
            "schema_version",
            "fixture_case_count",
            "run_case_count",
        },
        "P1 raw fixture",
    ) != {
        "path": "tests/fixtures/retrieval_quality/queries.json",
        "sha256": (
            "sha256:"
            + P1_QUALITY_INPUTS["fixture_catalog_gold"]["sha256"]
        ),
        "schema_version": 1,
        "fixture_case_count": 44,
        "run_case_count": 7,
    }:
        raise ValueError("P1 raw fixture provenance mismatch")
    config = _require_keys(
        report["config"],
        {"config_hash", "embedding"},
        "P1 raw config",
    )
    if (
        config["config_hash"] != P1_CONFIG_HASHES[profile]
        or _require_keys(
            config["embedding"],
            {
                "provider",
                "model",
                "dimensions",
                "base_url",
                "api_key_env",
            },
            "P1 raw embedding config",
        )
        != {
            "provider": "bge",
            "model": BGE_MODEL,
            "dimensions": BGE_DIMENSIONS,
            "base_url": None,
            "api_key_env": None,
        }
    ):
        raise ValueError("P1 raw config provenance mismatch")
    if _require_keys(
        report["planner"],
        set(_p1_expected_planner(profile)),
        "P1 raw planner",
    ) != _p1_expected_planner(profile):
        raise ValueError("P1 raw planner provenance mismatch")

    expected_repositories = list(dict.fromkeys(repo for repo, _ in P1_CASES))
    repositories = report["repos"]
    if (
        not isinstance(repositories, list)
        or any(not isinstance(repository, dict) for repository in repositories)
        or [
            repository.get("repo_key")
            for repository in repositories
        ]
        != expected_repositories
    ):
        raise ValueError("P1 raw repositories are invalid")

    raw_cases = report["cases"]
    if not isinstance(raw_cases, list) or len(raw_cases) != len(P1_CASES):
        raise ValueError("P1 raw cases are invalid")
    projections: list[dict[str, object]] = []
    queries: list[str] = []
    for raw_case, expected_case in zip(
        raw_cases,
        P1_CASES,
        strict=True,
    ):
        projection, query = _p1_raw_case_projection(
            raw_case,
            expected_case,
        )
        projections.append(projection)
        queries.append(query)
    if queries != [catalog_queries[key] for key in P1_CASES]:
        raise ValueError("P1 catalog query mismatch")

    aggregate = _require_keys(
        report["aggregate"],
        _P1_RAW_AGGREGATE_KEYS,
        "P1 raw aggregate",
    )
    if not isinstance(aggregate["metrics"], dict):
        raise ValueError("P1 raw aggregate metrics are invalid")
    passed = sum(case["status"] == "pass" for case in projections)
    failed = len(projections) - passed
    expected_counts = {
        "total": len(projections),
        "selected": len(projections),
        "attempted": len(projections),
        "executed": len(projections),
        "passed": passed,
        "failed": failed,
        "skipped": 0,
        "known_gaps": 0,
        "informational": 0,
        "errors": 0,
    }
    for name, expected in expected_counts.items():
        if (
            _require_nonnegative_integer(
                aggregate[name],
                f"P1 raw aggregate {name}",
            )
            != expected
        ):
            raise ValueError("P1 raw aggregate is inconsistent")
    return projections, queries


def load_p1_evidence(
    evidence_path: Path,
    product_captures: list[dict[str, object]],
) -> dict[str, object]:
    implementation, bge_attestation = _p1_bge_attestation(
        product_captures
    )
    path = evidence_path.resolve(strict=True)
    if not path.is_file():
        raise ValueError("P1 evidence is not a file")
    wrapper_root = path.parent
    wrapper = _require_keys(
        json.loads(path.read_text(encoding="utf-8")),
        _P1_WRAPPER_KEYS,
        "P1 evidence wrapper",
    )
    if wrapper["schema_version"] != "p13-p1-continuity-v1":
        raise ValueError("unsupported P1 evidence schema")
    if (
        _validate_implementation(wrapper["implementation"])
        != implementation
    ):
        raise ValueError("P1 evidence candidate identity mismatch")
    if (
        _validate_file_record(
            wrapper["quality_runner"],
            "P1 quality runner",
        )
        != QUALITY_RUNNER
        or wrapper["quality_inputs"] != P1_QUALITY_INPUTS
    ):
        raise ValueError("P1 evidence frozen input mismatch")
    profiles = _require_keys(
        wrapper["profiles"],
        set(_P1_PROFILES),
        "P1 evidence profiles",
    )
    catalog_queries = _p1_catalog_queries()

    normalized: dict[str, object] = {}
    profile_queries: list[list[str]] = []
    for profile_name in ("p1_vector_bge", "p1_hybrid_bge"):
        profile = _require_keys(
            profiles[profile_name],
            _P1_PROFILE_KEYS,
            "P1 profile",
        )
        attestation = _validate_attestation(profile["attestation"])
        if (
            profile["profile"] != profile_name
            or profile["config_hash"] != P1_CONFIG_HASHES[profile_name]
            or profile["provider"] != "bge"
            or profile["embedding_identity"]
            != bge_attestation["embedding_identity"]
            or attestation != bge_attestation
        ):
            raise ValueError("P1 profile provenance mismatch")
        raw_path = _p1_raw_report_path(
            wrapper_root,
            profile["raw_report"],
        )
        raw_projections, queries = _validate_p1_raw_report(
            json.loads(raw_path.read_text(encoding="utf-8")),
            profile_name,
            implementation,
            catalog_queries,
        )
        profile_queries.append(queries)

        outer_cases = profile["cases"]
        if (
            not isinstance(outer_cases, list)
            or len(outer_cases) != len(P1_CASES)
        ):
            raise ValueError("P1 profile cases are invalid")
        validated_outer = [
            _require_keys(case, _P1_CASE_KEYS, "P1 profile case")
            for case in outer_cases
        ]
        if validated_outer != raw_projections:
            raise ValueError("P1 profile cases do not match raw report")
        required_misses = sorted(
            case["case_id"]
            for case in raw_projections
            if case["required_miss"]
        )
        passed = len(raw_projections) - len(required_misses)
        summary = _require_keys(
            profile["summary"],
            {"passed", "total", "required_misses"},
            "P1 profile summary",
        )
        if summary != {
            "passed": passed,
            "total": len(raw_projections),
            "required_misses": required_misses,
        }:
            raise ValueError("P1 profile summary does not match raw report")
        normalized[profile_name] = {
            "passed": passed,
            "total": len(raw_projections),
            "only_known_miss": (
                required_misses[0]
                if len(required_misses) == 1
                else None
            ),
        }
    if profile_queries[0] != profile_queries[1]:
        raise ValueError("P1 profile cases do not share the same queries")
    return normalized


def _p1_evidence_provenance(
    evidence_path: Path,
    evidence_root: Path,
) -> dict[str, str]:
    root = evidence_root.resolve()
    path = evidence_path.resolve(strict=True)
    try:
        relative = path.relative_to(root)
    except ValueError as error:
        raise ValueError(
            "P1 evidence must be inside the evidence root"
        ) from error
    if path == root or not path.is_file():
        raise ValueError("P1 evidence is not a file")
    return {
        "path": relative.as_posix(),
        "sha256": _sha256_path(path),
    }


def _prepare_capture_paths(
    output_path: Path,
    command: str,
    names: list[str],
) -> list[Path]:
    directory = output_path.parent / f"{command}-captures"
    directory.mkdir(parents=True, exist_ok=True)
    if any(directory.iterdir()):
        raise ValueError("capture evidence directory is not empty")
    return [
        directory / f"{index:02d}-{name}.json"
        for index, name in enumerate(names, start=1)
    ]


def _capture_records(
    captures: list[dict[str, object]],
    sides: list[str],
    paths: list[Path],
    evidence_root: Path,
) -> list[dict[str, str]]:
    root = evidence_root.resolve()
    records: list[dict[str, str]] = []
    for capture, side, path in zip(captures, sides, paths, strict=True):
        rendered = _canonical(capture)
        if path.read_text(encoding="utf-8") != rendered:
            raise ValueError("persisted capture bytes do not match input")
        sha256 = _sha256_bytes(rendered.encode("utf-8"))
        if _sha256_path(path) != sha256:
            raise ValueError("persisted capture SHA does not match input")
        records.append(
            {
                "side": side,
                "provider": str(capture["provider"]),
                "sha256": sha256,
                "path": path.resolve().relative_to(root).as_posix(),
            }
        )
    return records


def _attach_capture_evidence(
    report: object,
    records: list[dict[str, str]],
    output_path: Path,
) -> None:
    grouped_sha256: dict[str, list[str]] = {}
    grouped_paths: dict[str, list[str]] = {}
    for record in records:
        grouped_sha256.setdefault(record["side"], []).append(
            record["sha256"]
        )
        grouped_paths.setdefault(record["side"], []).append(record["path"])
    if not isinstance(report, dict):
        raise ValueError("gate evidence report is invalid")
    gates = report.get("gates")
    if not isinstance(gates, dict) or not gates:
        raise ValueError("gate evidence mapping is invalid")
    for gate in gates.values():
        if (
            not isinstance(gate, dict)
            or set(gate) != _GATE_KEYS
            or not isinstance(gate["passed"], bool)
            or gate["evidence_path"] != output_path.name
        ):
            raise ValueError("gate evidence mapping is invalid")
        for field in ("numerator", "denominator", "threshold"):
            _require_number(gate[field], f"gate evidence {field}")
        if gate["ratio"] is not None:
            _require_number(gate["ratio"], "gate evidence ratio")
        if gate["input_capture_sha256"] != grouped_sha256:
            raise ValueError(
                "gate evidence hashes do not match persisted inputs"
            )
        gate["input_capture_paths"] = copy.deepcopy(grouped_paths)
    report["input_captures"] = copy.deepcopy(records)


def _publish_comparison(
    output_path: Path,
    records: list[dict[str, str]],
    compare: Callable[[Path], object],
    enrich: Callable[[dict[str, object]], None] | None = None,
) -> dict[str, object]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, raw_staging_path = tempfile.mkstemp(
        prefix=f".{output_path.name}.",
        suffix=".tmp",
        dir=output_path.parent,
    )
    os.close(descriptor)
    staging_path = Path(raw_staging_path)
    with _preserve_primary_during_cleanup(
        lambda: staging_path.unlink(missing_ok=True),
        "staging cleanup",
    ):
        report = compare(staging_path)
        _attach_capture_evidence(report, records, staging_path)
        if not isinstance(report, dict):
            raise ValueError("gate evidence report is invalid")
        if enrich is not None:
            enrich(report)
        gates = report.get("gates")
        if not isinstance(gates, dict) or not all(
            isinstance(gate, dict) for gate in gates.values()
        ):
            raise ValueError("gate evidence mapping is invalid")
        for gate in gates.values():
            gate["evidence_path"] = output_path.name
        staging_path.write_text(_canonical(report), encoding="utf-8")
        os.replace(staging_path, output_path)
        return report


def _positive_integer(raw: str) -> int:
    value = int(raw)
    if value <= 0:
        raise argparse.ArgumentTypeError("value must be positive")
    return value


def _candidate_commit(raw: str) -> str:
    if _GIT_OID_RE.fullmatch(raw) is None:
        raise argparse.ArgumentTypeError(
            "expected candidate commit must be a lowercase full Git OID"
        )
    return raw


def _argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run frozen P13 paired measurements."
    )
    commands = parser.add_subparsers(dest="command", required=True)

    paired = commands.add_parser(
        "paired",
        help="compare legacy baseline and native candidate",
    )
    paired.add_argument("--baseline-root", type=Path, required=True)
    paired.add_argument("--candidate-root", type=Path, required=True)
    paired.add_argument(
        "--expected-candidate-commit",
        type=_candidate_commit,
        required=True,
    )
    paired.add_argument("--sources", type=Path, required=True)
    paired.add_argument("--output", type=Path, required=True)

    product = commands.add_parser(
        "product-paired",
        help="compare candidate hash and BGE providers",
    )
    product.add_argument("--candidate-root", type=Path, required=True)
    product.add_argument(
        "--expected-candidate-commit",
        type=_candidate_commit,
        required=True,
    )
    product.add_argument("--sources", type=Path, required=True)
    product.add_argument("--output", type=Path, required=True)
    product.add_argument("--p1-evidence", type=Path, required=True)

    child = commands.add_parser("_capture-child")
    child.add_argument("--implementation-root", type=Path, required=True)
    child.add_argument(
        "--expected-candidate-commit",
        type=_candidate_commit,
    )
    child.add_argument("--sources", type=Path, required=True)
    child.add_argument("--output", type=Path, required=True)
    child.add_argument(
        "--mode",
        choices=("legacy-baseline", "native"),
        required=True,
    )
    child.add_argument(
        "--provider",
        choices=("hash", "bge"),
        required=True,
    )
    child.add_argument(
        "--repetitions",
        type=_positive_integer,
        default=_DEFAULT_TIMING_REPETITIONS,
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _argument_parser().parse_args(argv)
    if arguments.command == "_capture-child":
        payload = _capture_child(
            implementation_root=arguments.implementation_root,
            sources=arguments.sources,
            output_path=arguments.output,
            mode=arguments.mode,
            provider=arguments.provider,
            repetitions=arguments.repetitions,
            expected_candidate_commit=arguments.expected_candidate_commit,
        )
        sys.stdout.write(_canonical(payload))
        return 0

    _verify_native_candidate(
        arguments.candidate_root,
        arguments.expected_candidate_commit,
    )

    if arguments.command == "paired":
        captures: list[dict[str, object]] = []
        planned = (
            (
                arguments.baseline_root,
                "legacy-baseline",
            ),
            (
                arguments.candidate_root,
                "native",
            ),
            (
                arguments.candidate_root,
                "native",
            ),
            (
                arguments.baseline_root,
                "legacy-baseline",
            ),
            (
                arguments.baseline_root,
                "legacy-baseline",
            ),
            (
                arguments.candidate_root,
                "native",
            ),
        )
        sides = [
            "baseline" if mode == "legacy-baseline" else "candidate"
            for _implementation_root, mode in planned
        ]
        capture_paths = _prepare_capture_paths(
            arguments.output,
            "engineering",
            [f"{side}-bge" for side in sides],
        )
        for (implementation_root, mode), capture_path in zip(
            planned,
            capture_paths,
            strict=True,
        ):
            captures.append(
                _run_capture_process(
                    implementation_root=implementation_root,
                    sources=arguments.sources,
                    mode=mode,
                    provider="bge",
                    capture_path=capture_path,
                    expected_candidate_commit=(
                        arguments.expected_candidate_commit
                        if mode == "native"
                        else None
                    ),
                )
            )
        records = _capture_records(
            captures,
            sides,
            capture_paths,
            arguments.output.parent,
        )
        _publish_comparison(
            arguments.output,
            records,
            lambda staging_path: compare_engineering(
                captures,
                staging_path,
            ),
        )
        return 0

    providers = ["hash", "hash", "bge", "bge"]
    capture_paths = _prepare_capture_paths(
        arguments.output,
        "product",
        providers,
    )
    captures = [
        _run_capture_process(
            implementation_root=arguments.candidate_root,
            sources=arguments.sources,
            mode="native",
            provider=provider,
            capture_path=capture_path,
            expected_candidate_commit=arguments.expected_candidate_commit,
        )
        for provider, capture_path in zip(
            providers,
            capture_paths,
            strict=True,
        )
    ]
    p1_profiles = load_p1_evidence(
        arguments.p1_evidence,
        captures,
    )
    p1_provenance = _p1_evidence_provenance(
        arguments.p1_evidence,
        arguments.output.parent,
    )
    records = _capture_records(
        captures,
        providers,
        capture_paths,
        arguments.output.parent,
    )

    def enrich_product(report: dict[str, object]) -> None:
        p1_gate = report.get("gates", {}).get("p1_continuity")
        if isinstance(p1_gate, dict):
            raw_values = p1_gate.get("raw_values")
            if isinstance(raw_values, dict):
                raw_values["p1_evidence"] = p1_provenance

    _publish_comparison(
        arguments.output,
        records,
        lambda staging_path: compare_product(
            captures,
            p1_profiles,
            staging_path,
        ),
        enrich_product,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
