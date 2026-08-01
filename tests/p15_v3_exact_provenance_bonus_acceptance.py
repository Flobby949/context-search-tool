#!/usr/bin/env python3
"""Read-only P15-v3 skeleton validator.

This module validates the frozen design boundary.  It has no capture path, does
not import product code, and never reads Click plaintext.
"""

from __future__ import annotations

import argparse
import ast
import ctypes
from copy import deepcopy
from dataclasses import asdict, dataclass, replace
import errno
import fcntl
import fnmatch
import hashlib
import importlib
import json
import os
import re
import secrets
import shutil
import stat
import subprocess
import sys
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "tests/fixtures/p15_v3_exact_provenance_bonus/input_manifest.json"
MANIFEST_SHA256 = "5f94c7e270a7698a7fe7a170ab6a61312c2c86b3ccc6242e962150e5e84eb624"
DESIGN_SHA256 = "86a9ab83d493ccfdb4f3039f2b901d6fc06c1a0bc3d65f5970d8de00f3f972e5"
PLAN_SHA256 = "de565be48c88fee1a7c6f5319bd5069bbcd586ceaaae6129153a17d7a201ff6f"
V2_REJECT_INDEX_SHA256 = "cde8f5baf1aa8b6e96f04fdc24f221b450824563cb5721a59cf40872c3a69dd5"
FRESH_ROSTER_CONTRACT = (
    ".quality/p15-v3-recovery-seal-v2/roster_contract_v2.json",
    "303a08e0e1c18f845abea8e44bb2a074bc58bb6aef30b4448c9111638a039266",
)
FRESH_SEAL_HASHES = (
    ".quality/p15-v3-recovery-seal-v2/seal_hashes_v2.json",
    "0b7f4e3c69857b9fbb0e3e96b67ba1e5d9b84adc84dbff04fe7fb65ec96905de",
)
CLICK_CARRY_FORWARD = (
    ".quality/p15-v3-recovery-seal-v2/click_conditional_carry_forward_disposition_v2.json",
    "9ace5e51975f21fc626556ab99673a7ec66650896e44a37c9618e8dc956be009",
)
FRESH_PUBLIC_CONTRACTS = {
    "httpx": (
        ".quality/p15-v3-recovery-seal-v2/httpx_public_contract_v2.json",
        "89e4a783fbb612c8d2863bae21594976d3467ff87726971c7b178fc0c3e23a59",
    ),
    "poetry_core": (
        ".quality/p15-v3-recovery-seal-v2/poetry_core_public_contract_v2.json",
        "8428aaf2c2b952e579e75ec388031000cb9594b66784ed811e88e24d25903ec7",
    ),
}
FRESH_RELEASE_REVIEW = (
    ".quality/p15-v3-recovery-release-review/independent_recovery_v2_fresh_release_review_disposition.json",
    "1cf0dab5e35fe4b27af805612e72bc88558f988b82baca766fc81b71d9e2a964",
)
FRESH_RELEASED_PAYLOADS = {
    "httpx": (
        ".quality/p15-v3-recovery-seal-v2/httpx_fresh_payload_v2.json",
        "c107d7a744154d93c54041dd9b026d31ed2fe6cc7d53775ccffafa931737ac75",
        15935,
        "p15-v3-recovery-v2-fresh-httpx-b5addb6",
    ),
    "poetry_core": (
        ".quality/p15-v3-recovery-seal-v2/poetry_core_fresh_payload_v2.json",
        "385c15af37c226ac869b3dcdc84f5b4d6750fb1bad83aabab7ea362fdde0f8cf",
        18753,
        "p15-v3-recovery-v2-fresh-poetry-core-5de2411",
    ),
}
FRESH_SEAL_INVENTORY = (
    "click_conditional_carry_forward_disposition_v2.json",
    "httpx_fresh_payload_v2.json",
    "httpx_fresh_payload_v2.json.enc",
    "httpx_public_contract_v2.json",
    "poetry_core_fresh_payload_v2.json",
    "poetry_core_fresh_payload_v2.json.enc",
    "poetry_core_public_contract_v2.json",
    "roster_contract_v2.json",
    "seal_hashes_v2.json",
)
REVOKED_V3_PATH_PREFIXES = (
    ".quality/p15-v3-review-seal/",
    ".quality/p15-v3-rebind-review-seal/",
    ".quality/p15-v3-incident-review/",
)
BASELINE = "5f56de2e1b57ed7f1ec0ee9a513b508461d78233"
BONUS_SCORE_PART = "exact_imported_symbol"
BONUS_REASON = "exact imported symbol dependency"
BONUS_STAGE = "after_owner_ceiling_and_cohort_before_context_expansion_and_final_selection"
CONTROL_DIRECTORY = "task0a-control"
CONTROL_FILENAMES = (
    "control-r1-canonical.json",
    "control-r1-reverse.json",
    "control-r2-canonical.json",
    "control-r2-reverse.json",
)
CONTROL_MARKER_FILENAME = "control-freeze-marker.json"
CONTROL_SEAL_FILENAME = "task0-control-seal-disposition.json"
TREATMENT_FILENAME = "task0b-treatment.json"
CONTROL_INVENTORY = (*CONTROL_FILENAMES, CONTROL_MARKER_FILENAME)

PROVENANCE_FIELDS = (
    "relation_id",
    "source_signal_id",
    "source_file_path",
    "source_chunk_id",
    "target_signal_id",
    "target_file_path",
    "target_chunk_id",
    "relation_kind",
    "resolution",
    "producer",
    "resolution_basis",
    "ordered_edge_position",
)
IDENTITY_PROJECTION_FIELDS = (
    "relation_id",
    "source_signal_id",
    "source_file_path",
    "source_chunk_id",
    "target_signal_id",
    "target_file_path",
    "target_chunk_id",
)
MERGE_ROUTES = ("candidate", "same_chunk", "context_overlap")
EXISTING_TOTAL_ORDER = (
    "-round(rerank_score,3)",
    "evidence_priority",
    "0_if_was_ceiling_clamped_else_1",
    "-pre_ceiling_rerank_score_if_clamped_else_0.0",
    "role_priority",
    "-rerank_score",
    "-combined_score",
    "file_path",
    "start_line",
    "chunk_id",
)
STRUCTURE_TOP_LEVEL_KEYS = {
    "selected_files",
    "non_relation_fields",
    "relation_buckets",
    "module_projection_sha256",
    "non_python_projection_sha256",
}
DAILY_SATURATION_PROJECTION_SHA256 = "c59f96bd2158a16037df322920a2263096413e0bd7a19a4eac9660351942c7f6"

FROZEN_CAPS = {
    "maximum_graph_seed_signals": 512,
    "maximum_resolved_graph_hops": 4,
    "maximum_edges_per_signal_direction": 64,
    "maximum_relation_expanded_candidates": 1000,
    "maximum_python_imports_per_file": 256,
}

EXPECTED_V2_IDENTITIES = {
    "design": {
        "path": "docs/superpowers/specs/2026-08-01-p15-v2-python-exact-imported-symbol-relations-design.md",
        "sha256": "054f44d4a0a7ab53efa13394b2e471afe04eca1eb92581f01a40d0b3c64d15d5",
    },
    "plan": {
        "path": "docs/superpowers/plans/2026-08-01-p15-v2-python-exact-imported-symbol-relations.md",
        "sha256": "c874a8d5bace18aabec54fa94260989bfac3cecf4eadb7e0b6d08275618cbc3b",
    },
    "manifest": {
        "path": "tests/fixtures/p15_v2_python_import_symbols/input_manifest.json",
        "sha256": "a00f374322eb9021143c50a0599b8b2b02c56998d2b0876fbdfe56cb460fb01c",
    },
    "harness": {
        "path": "tests/p15_v2_python_import_symbol_acceptance.py",
        "sha256": "902b572c82ec4c172e49ad1d9ea42d72ffb0384f98faa2100426070a5d382fc1",
    },
    "harness_tests": {
        "path": "tests/test_p15_v2_python_import_symbol_acceptance.py",
        "sha256": "6b416fee329a4745982108fc819676c42dee97f5a9690fb0ae5c5f3bc45cbb7b",
    },
}

EXPECTED_V2_DISPOSITIONS = {
    ".quality/p15-v2-review-seal/independent_plan_harness_disposition.json": "d9113575dfeb04b847cbe4acfe47027ff2a9f2e61467be6d84eaecacdaa0ce18",
    ".quality/p15-v2-review-seal/independent_task0d_engine_disposition.json": "3ec9cecc9e6c8abc435761768e03bc6f103a08438ba93a03bed9be5a735ed480",
    ".quality/p15-v2-review-seal/independent_task0d_runtime_privacy_fix_disposition.json": "029bb607366c2ac3f460f87dedc72f82bfce5fd87933dee95caecdbdd0433764",
    ".quality/p15-v2-review-seal/independent_task0d_signal_name_privacy_fix_disposition.json": "d9e266b670aa1f8406602b7c6b41aa397c4e83f65eda67faa50ff28aa297e4be",
    ".quality/p15-v2-review-seal/independent_task0d_module_metadata_privacy_fix_disposition.json": "c25a0a53c646a61640ef1b41ce86c5e51608868df5b7432baa4c6768350d88dd",
    ".quality/p15-v2-review-seal/independent_task0d_structured_identity_privacy_disposition.json": "c969079ed71b24dcb5ccb36cdca031a99e58d4c7eeb7bdc4be79d1d700d6d68c",
}

EXPECTED_V2_ARTIFACTS = {
    "oracle/hash/development_and_protected/baseline-r1-canonical.json": "3a92319f6ba2de95f1ceed4c73347aa262585ac3be38acce6601509834433955",
    "oracle/hash/development_and_protected/baseline-r1-reverse.json": "99cecc624999039a0e6d798c7d0e8fccfa912137be0ceb1510e46e82898ab25d",
    "oracle/hash/development_and_protected/baseline-r2-canonical.json": "be357929522243a4210c3b7b8294d4043c9cefa2c4704e539590939e7846786e",
    "oracle/hash/development_and_protected/baseline-r2-reverse.json": "2af697034e87a63b64dd87ee81751fda3401b38f300488fccd96aefd3e9c826b",
    "oracle/hash/development_and_protected/oracle-r1-canonical.json": "f60c6f4a2065a1aab65913dbd6aed3662eb9ef22146e9e48aebd9fd1eef64a01",
    "oracle/hash/development_and_protected/oracle-r1-reverse.json": "4327f0a6b36dfe1e34927764a58f05004ea0d985140b4721cdc8142bd7709987",
    "oracle/hash/development_and_protected/oracle-r2-canonical.json": "6adb6ec170a368a9d98285114ebf7a0a8a2c05e2b49db3679823cbac89a1380b",
    "oracle/hash/development_and_protected/oracle-r2-reverse.json": "652179d0aa0c03cd46c1bb189b3e89c5ca32250d44af91ee20d776d1cb4612ff",
    "oracle/hash/development_and_protected/comparison.json": "7e2e5ae900ba770cac0b027bc503ad9212dc97f91c9b4cca47f96492ecfad390",
    "terminal-reject.json": "27b85300c34e5b629fe8ee514e5f657f9f602fc78787e2aa25486e77a532bb3b",
}


class ValidationError(RuntimeError):
    """The closed skeleton contract was violated."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationError(message)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _json_value_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _read_immutable_canonical_json(path: Path, label: str) -> tuple[Any, str]:
    try:
        metadata = path.lstat()
    except FileNotFoundError as exc:
        raise ValidationError(f"{label} is missing") from exc
    _require(stat.S_ISREG(metadata.st_mode), f"{label} is not a regular non-symlink file")
    _require(stat.S_IMODE(metadata.st_mode) == 0o444, f"{label} mode is not 0444")
    _require(metadata.st_nlink == 1, f"{label} link count is not one")
    raw = path.read_bytes()
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValidationError(f"{label} is not canonical JSON") from exc
    _require(raw == _canonical_json_bytes(payload), f"{label} bytes are not canonical JSON")
    return payload, hashlib.sha256(raw).hexdigest()


def _repo_path(relative: str) -> Path:
    _require(isinstance(relative, str) and relative and not Path(relative).is_absolute(), "path must be non-empty and relative")
    resolved = (ROOT / relative).resolve()
    _require(resolved == ROOT or ROOT in resolved.parents, f"path escapes repository: {relative}")
    return resolved


def _validate_file_stat(path: Path, *, mode: int, size: int | None, label: str) -> None:
    try:
        metadata = path.lstat()
    except FileNotFoundError as exc:
        raise ValidationError(f"{label} is missing") from exc
    _require(stat.S_ISREG(metadata.st_mode), f"{label} is not a regular non-symlink file")
    _require(stat.S_IMODE(metadata.st_mode) == mode, f"{label} mode changed")
    _require(metadata.st_nlink == 1, f"{label} link count changed")
    if size is not None:
        _require(metadata.st_size == size, f"{label} size changed")


def _read_public_json_anchor(relative: str, expected_sha256: str, *, mode: int = 0o444) -> Mapping[str, Any]:
    path = _repo_path(relative)
    _validate_file_stat(path, mode=mode, size=None, label=f"public anchor {relative}")
    _require(_sha256(path) == expected_sha256, f"public anchor digest mismatch: {relative}")
    payload = _read_json(path)
    _require(isinstance(payload, Mapping), f"public anchor is not an object: {relative}")
    return payload


def _select_public_source_inventory(
    root: Path,
    include: Sequence[str],
    exclude: Sequence[str],
) -> list[str]:
    selected: list[str] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        if any(fnmatch.fnmatch(relative, pattern) for pattern in include) and not any(
            fnmatch.fnmatch(relative, pattern) for pattern in exclude
        ):
            selected.append(relative)
    return selected


def _source_inventory_sha256(files: Sequence[str]) -> str:
    return hashlib.sha256("\n".join(files).encode("utf-8")).hexdigest()


def _source_content_sha256(root: Path, files: Sequence[str]) -> str:
    digest = hashlib.sha256()
    for relative in files:
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update((root / relative).read_bytes())
    return digest.hexdigest()


def _git_value(root: Path, argument: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(root), "rev-parse", argument],
        text=True,
        capture_output=True,
        check=True,
    )
    return completed.stdout.strip()


def _require_exact_keys(value: Mapping[str, Any], expected: set[str], label: str) -> None:
    _require(set(value) == expected, f"{label} keys are not closed")


def validate_structure_closed(
    baseline: Mapping[str, Any],
    oracle: Mapping[str, Any],
    causal_relation_count: int,
    *,
    expected_relation_buckets: set[str],
    expected_signal_producers: set[str],
) -> None:
    """Validate the complete fixed structural projection, not a sparse sample."""

    _require_exact_keys(baseline, STRUCTURE_TOP_LEVEL_KEYS, "baseline structure")
    _require_exact_keys(oracle, STRUCTURE_TOP_LEVEL_KEYS, "oracle structure")
    _require(isinstance(causal_relation_count, int) and causal_relation_count >= 0, "invalid causal relation count")
    _require(baseline["selected_files"] == oracle["selected_files"], "selected files changed")
    _require_exact_keys(
        baseline["non_relation_fields"],
        {"active_chunks", "signals_by_producer"},
        "baseline non-relation fields",
    )
    _require_exact_keys(
        oracle["non_relation_fields"],
        {"active_chunks", "signals_by_producer"},
        "oracle non-relation fields",
    )
    _require(
        baseline["non_relation_fields"] == oracle["non_relation_fields"],
        "non-relation structure changed",
    )
    baseline_producers = baseline["non_relation_fields"]["signals_by_producer"]
    oracle_producers = oracle["non_relation_fields"]["signals_by_producer"]
    _require(set(baseline_producers) == expected_signal_producers, "baseline producer key set is incomplete")
    _require(set(oracle_producers) == expected_signal_producers, "oracle producer key set is incomplete")
    baseline_relations = baseline["relation_buckets"]
    oracle_relations = oracle["relation_buckets"]
    _require(set(baseline_relations) == expected_relation_buckets, "baseline relation bucket set is incomplete")
    _require(set(oracle_relations) == expected_relation_buckets, "oracle relation bucket set is incomplete")
    field = "imports:resolved_exact"
    _require(field in expected_relation_buckets, "resolved-exact relation bucket is missing")
    for key in expected_relation_buckets:
        if key == field:
            _require(
                oracle_relations[key] == baseline_relations[key] + causal_relation_count,
                "resolved-exact structure equation failed",
            )
        else:
            _require(oracle_relations[key] == baseline_relations[key], f"relation bucket changed: {key}")
    _require(
        baseline["module_projection_sha256"] == oracle["module_projection_sha256"],
        "module projection changed",
    )
    _require(
        baseline["non_python_projection_sha256"] == oracle["non_python_projection_sha256"],
        "non-Python projection changed",
    )


def validate_cap_constants(baseline: Mapping[str, Any], oracle: Mapping[str, Any]) -> None:
    _require(dict(baseline) == FROZEN_CAPS, "baseline cap constants changed")
    _require(dict(oracle) == FROZEN_CAPS, "oracle cap constants changed")


def validate_degree_delta(
    baseline_observed_max_outgoing: int,
    oracle_observed_max_outgoing: int,
    maximum_exact_relations_per_source: int,
) -> None:
    for value in (
        baseline_observed_max_outgoing,
        oracle_observed_max_outgoing,
        maximum_exact_relations_per_source,
    ):
        _require(isinstance(value, int) and value >= 0, "degree values must be non-negative integers")
    delta = oracle_observed_max_outgoing - baseline_observed_max_outgoing
    _require(delta >= 0, "observed exact degree cannot shrink in this proof")
    _require(delta <= maximum_exact_relations_per_source, "degree delta exceeds exact relation bound")


def _validate_edge_positions(rows: Sequence[Mapping[str, Any]]) -> None:
    _require(len(rows) == 64, "saturation proof must contain 64 real edges")
    positions = [row.get("position") for row in rows]
    _require(positions == list(range(1, 65)), "eligible edge positions must be exactly ordered 1..64")
    identities = [row.get("edge_identity") for row in rows]
    _require(all(isinstance(identity, str) and identity for identity in identities), "edge identity is missing")
    _require(len(set(identities)) == 64, "saturation edge identities must be unique")


def _extract_daily_identity_projection(capture: Mapping[str, Any], source_signal_id: str) -> list[dict[str, Any]]:
    projected: list[dict[str, Any]] = []
    relations = capture["index_projections"]["daily"]["causal_relations"]
    for item in relations:
        relation = item["relation"]
        if relation["source_signal_id"] != source_signal_id:
            continue
        metadata = json.loads(relation["metadata_json"])
        _require(relation["kind"] == "imports", "Daily saturation relation kind changed")
        _require(relation["resolution"] == "resolved_exact", "Daily saturation relation is not exact")
        _require(relation["producer"] == "python_ast", "Daily saturation producer changed")
        _require(metadata.get("resolution_basis") == "exact_python_imported_symbol", "Daily saturation basis changed")
        projected.append(
            {
                "relation_id": relation["relation_id"],
                "source_signal_id": relation["source_signal_id"],
                "source_file_path": item["source_signal"]["file_path"],
                "source_chunk_id": item["source_signal"]["chunk_id"],
                "target_signal_id": relation["target_signal_id"],
                "target_file_path": item["target_signal"]["file_path"],
                "target_chunk_id": item["target_signal"]["chunk_id"],
            }
        )
    projected.sort(key=lambda row: tuple(row[field] for field in IDENTITY_PROJECTION_FIELDS))
    return projected


def validate_daily_saturation_snapshot(snapshot: Mapping[str, Any]) -> None:
    _require_exact_keys(
        snapshot,
        {
            "source_capture_path",
            "source_capture_sha256",
            "source_signal_id",
            "source_file_path",
            "source_chunk_id",
            "identity_projection_fields",
            "identity_projection_sha256",
            "ordering",
            "ordered_edges",
            "position_65_negative",
        },
        "Daily saturation snapshot",
    )
    _require(snapshot["source_capture_sha256"] == EXPECTED_V2_ARTIFACTS["oracle/hash/development_and_protected/oracle-r1-canonical.json"], "Daily source capture binding changed")
    capture_path = _repo_path(snapshot["source_capture_path"])
    _require(_sha256(capture_path) == snapshot["source_capture_sha256"], "Daily source capture digest mismatch")
    _require(snapshot["identity_projection_fields"] == list(IDENTITY_PROJECTION_FIELDS), "Daily identity projection fields changed")
    _require(snapshot["ordering"] == "lexicographic_complete_identity_projection", "Daily edge ordering changed")
    projection = _extract_daily_identity_projection(_read_json(capture_path), snapshot["source_signal_id"])
    _require(len(projection) == 64, "Daily immutable evidence does not contain exactly 64 saturated edges")
    _require(_json_value_sha256(projection) == snapshot["identity_projection_sha256"] == DAILY_SATURATION_PROJECTION_SHA256, "Daily complete identity projection digest mismatch")
    _require(all(row["source_file_path"] == snapshot["source_file_path"] for row in projection), "Daily source file binding changed")
    _require(all(row["source_chunk_id"] == snapshot["source_chunk_id"] for row in projection), "Daily source chunk binding changed")
    ordered = snapshot["ordered_edges"]
    _validate_edge_positions(ordered)
    _require([row["edge_identity"] for row in ordered] == [row["relation_id"] for row in projection], "Daily ordered edge identities differ from immutable evidence")

    negative = snapshot["position_65_negative"]
    _require(
        negative
        == {
            "position": 65,
            "edge_identity": projection[-1]["relation_id"],
            "real_source_position": 64,
            "operation": "relocate_real_edge_without_identity_change",
            "expected": "fail_closed_edge_cap",
        },
        "Daily position-65 negative identity changed",
    )
    relocated = [*ordered[:63], {"position": 65, "edge_identity": negative["edge_identity"]}]
    try:
        _validate_edge_positions(relocated)
    except ValidationError:
        pass
    else:
        raise ValidationError("Daily real edge at position 65 did not fail closed")


def _provenance_key(atom: Mapping[str, Any]) -> tuple[Any, ...]:
    return tuple(atom[field] for field in PROVENANCE_FIELDS)


def _validate_direct_atom(atom: Mapping[str, Any]) -> None:
    _require_exact_keys(atom, set(PROVENANCE_FIELDS), "exact provenance tuple")
    _require(atom["relation_kind"] == "imports", "provenance relation is not direct imports")
    _require(atom["resolution"] == "resolved_exact", "provenance relation is not resolved exact")
    _require(atom["producer"] == "python_ast", "provenance producer is not python_ast")
    _require(atom["resolution_basis"] == "exact_python_imported_symbol", "provenance basis is not exact imported symbol")
    _require(isinstance(atom["ordered_edge_position"], int) and 1 <= atom["ordered_edge_position"] <= 64, "provenance ordered edge position exceeds cap")
    for field in PROVENANCE_FIELDS[:-1]:
        _require(isinstance(atom[field], str) and atom[field], f"provenance field is invalid: {field}")


def _provenance_union(atoms: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        dict(zip(PROVENANCE_FIELDS, values))
        for values in sorted({_provenance_key(atom) for atom in atoms})
    ]


def _atoms_for_origins(
    inventory: Sequence[Mapping[str, Any]],
    origin_chunk_ids: Sequence[str],
) -> list[dict[str, Any]]:
    origins = set(origin_chunk_ids)
    return _provenance_union(
        atom for atom in inventory if atom["target_chunk_id"] in origins
    )


def _validate_candidate_projection(value: Mapping[str, Any], label: str) -> None:
    _require_exact_keys(
        value,
        {"chunk_id", "score", "source", "score_parts", "semantic_matches"},
        label,
    )
    _require(isinstance(value["chunk_id"], str) and value["chunk_id"], f"{label} chunk changed")
    _require(isinstance(value["score"], (int, float)) and not isinstance(value["score"], bool), f"{label} score changed")
    _require(isinstance(value["source"], str) and value["source"], f"{label} source changed")
    _require(isinstance(value["score_parts"], Mapping), f"{label} score parts changed")
    matches = value["semantic_matches"]
    _require(isinstance(matches, list), f"{label} semantic matches changed")
    for match in matches:
        _require_exact_keys(match, {"variant_id", "score"}, f"{label} semantic match")


def _validate_provenance_envelope(
    value: Mapping[str, Any],
    inventory: Sequence[Mapping[str, Any]],
    *,
    origins: Sequence[str],
    projection_key: str,
    projection_validator,
    label: str,
) -> None:
    _require_exact_keys(value, {projection_key, "provenance_union"}, label)
    projection_validator(value[projection_key], f"{label} projection")
    _require(
        value["provenance_union"] == _atoms_for_origins(inventory, origins),
        f"{label} provenance union changed",
    )


def _validate_ranked_projection(value: Mapping[str, Any], label: str) -> None:
    _require_exact_keys(
        value,
        {
            "chunk_id", "file_path", "start_line", "end_line", "score",
            "score_parts", "reasons", "rank_tier", "rerank_score",
            "evidence_class", "evidence_priority", "semantic_matches",
            "pre_ceiling_rerank_score", "was_ceiling_clamped",
        },
        label,
    )
    _require(isinstance(value["chunk_id"], str) and value["chunk_id"], f"{label} chunk changed")
    _require(isinstance(value["file_path"], str) and value["file_path"], f"{label} path changed")
    _require(
        isinstance(value["start_line"], int)
        and isinstance(value["end_line"], int)
        and value["start_line"] <= value["end_line"],
        f"{label} range changed",
    )


def _validate_context_projection(value: Mapping[str, Any], label: str) -> None:
    _require_exact_keys(
        value,
        {
            "origin_chunk_ids", "file_path", "start_line", "end_line", "score",
            "score_parts", "reasons", "rank_tier", "rerank_score",
            "evidence_class", "evidence_priority", "semantic_matches",
            "pre_ceiling_rerank_score", "was_ceiling_clamped", "spans",
        },
        label,
    )
    origins = value["origin_chunk_ids"]
    _require(
        isinstance(origins, list)
        and origins
        and all(isinstance(item, str) and item for item in origins)
        and origins == list(dict.fromkeys(item.lower() for item in origins)),
        f"{label} origins changed",
    )
    _require(isinstance(value["file_path"], str) and value["file_path"], f"{label} path changed")
    _require(
        isinstance(value["start_line"], int)
        and isinstance(value["end_line"], int)
        and value["start_line"] <= value["end_line"],
        f"{label} range changed",
    )


def _validate_pipeline_boundaries(
    boundaries: Mapping[str, Any],
    inventory: Sequence[Mapping[str, Any]],
    rows: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, list[str]]]:
    """Rebuild route provenance and real origins from complete call boundaries."""

    _require_exact_keys(
        boundaries,
        {
            "overlay_exact_relation_count",
            "graph_outgoing_call_count", "graph_outgoing_calls",
            "candidate_merge_call_count", "candidate_merge_calls",
            "same_chunk_merge_count", "context_expansion_call_count",
            "context_expansion_calls", "context_overlap_merge_call_count",
            "context_overlap_merge_calls",
        },
        "pipeline boundaries",
    )
    _require(
        isinstance(boundaries["overlay_exact_relation_count"], int)
        and boundaries["overlay_exact_relation_count"] > 0,
        "exact imported-symbol overlay produced no relations",
    )
    graph_calls = boundaries["graph_outgoing_calls"]
    _require(
        isinstance(graph_calls, list)
        and boundaries["graph_outgoing_call_count"] == len(graph_calls)
        and [call.get("call_index") for call in graph_calls] == list(range(len(graph_calls))),
        "graph outgoing call history is incomplete or reordered",
    )
    derived_inventory: list[dict[str, Any]] = []
    seen_relations: dict[str, tuple[Any, ...]] = {}
    for call in graph_calls:
        _require_exact_keys(
            call,
            {"call_index", "source_signal_id", "requested_limit", "returned_relation_ids", "direct_exact_edges"},
            "graph outgoing call",
        )
        returned = call["returned_relation_ids"]
        _require(
            isinstance(returned, list)
            and all(isinstance(item, str) and item for item in returned),
            "graph outgoing return order changed",
        )
        for atom in call["direct_exact_edges"]:
            _validate_direct_atom(atom)
            position = atom["ordered_edge_position"]
            _require(
                atom["source_signal_id"] == call["source_signal_id"]
                and position <= len(returned)
                and returned[position - 1] == atom["relation_id"],
                "direct exact edge was reordered or renumbered",
            )
            key = _provenance_key(atom)
            prior = seen_relations.get(atom["relation_id"])
            _require(prior is None or prior == key, "direct exact relation changed across calls")
            if prior is None:
                seen_relations[atom["relation_id"]] = key
                derived_inventory.append(dict(atom))
    _require(list(inventory) == derived_inventory, "ordered edge inventory differs from actual graph call order")

    candidate_calls = boundaries["candidate_merge_calls"]
    _require(
        isinstance(candidate_calls, list)
        and boundaries["candidate_merge_call_count"] == len(candidate_calls)
        and [call.get("call_index") for call in candidate_calls] == list(range(len(candidate_calls))),
        "candidate merge call history is incomplete or reordered",
    )
    candidate_routes: dict[str, list[dict[str, Any]]] = {}
    same_chunk_routes: dict[str, list[dict[str, Any]]] = {}
    same_chunk_count = 0
    for call in candidate_calls:
        _require_exact_keys(call, {"call_index", "inputs", "outputs", "same_chunk_groups"}, "candidate merge call")
        inputs = call["inputs"]
        outputs = call["outputs"]
        _require(isinstance(inputs, list) and isinstance(outputs, list), "candidate merge boundary changed")
        input_ids: list[str] = []
        for envelope in inputs:
            candidate = envelope.get("candidate", {})
            _validate_provenance_envelope(
                envelope,
                inventory,
                origins=[candidate.get("chunk_id", "")],
                projection_key="candidate",
                projection_validator=_validate_candidate_projection,
                label="candidate merge input",
            )
            input_ids.append(candidate["chunk_id"])
        expected_output_ids = list(dict.fromkeys(input_ids))
        _require(
            [envelope.get("candidate", {}).get("chunk_id") for envelope in outputs]
            == expected_output_ids,
            "candidate merge output inventory changed",
        )
        outputs_by_id: dict[str, Mapping[str, Any]] = {}
        for envelope in outputs:
            candidate = envelope.get("candidate", {})
            chunk_id = candidate.get("chunk_id", "")
            _validate_provenance_envelope(
                envelope,
                inventory,
                origins=[chunk_id],
                projection_key="candidate",
                projection_validator=_validate_candidate_projection,
                label="candidate merge output",
            )
            outputs_by_id[chunk_id] = envelope
            candidate_routes[chunk_id] = _provenance_union(
                [*candidate_routes.get(chunk_id, []), *envelope["provenance_union"]]
            )
        expected_groups = []
        for chunk_id in expected_output_ids:
            indexes = [index for index, value in enumerate(input_ids) if value == chunk_id]
            if len(indexes) > 1:
                expected_groups.append((chunk_id, indexes))
        groups = call["same_chunk_groups"]
        _require(
            isinstance(groups, list)
            and [(group.get("chunk_id"), group.get("input_indexes")) for group in groups]
            == expected_groups,
            "same-chunk merge calls were omitted or forged",
        )
        same_chunk_count += len(groups)
        for group in groups:
            _require_exact_keys(
                group,
                {"chunk_id", "input_indexes", "inputs", "output", "provenance_union"},
                "same-chunk merge call",
            )
            chunk_id = group["chunk_id"]
            indexes = group["input_indexes"]
            _require(group["inputs"] == [inputs[index] for index in indexes], "same-chunk merge inputs changed")
            _require(group["output"] == outputs_by_id[chunk_id], "same-chunk merge output changed")
            expected_union = _atoms_for_origins(inventory, [chunk_id])
            _require(group["provenance_union"] == expected_union, "same-chunk provenance union changed")
            same_chunk_routes[chunk_id] = _provenance_union(
                [*same_chunk_routes.get(chunk_id, []), *expected_union]
            )
    _require(boundaries["same_chunk_merge_count"] == same_chunk_count, "same-chunk merge count changed")

    overlap_calls = boundaries["context_overlap_merge_calls"]
    _require(
        isinstance(overlap_calls, list)
        and boundaries["context_overlap_merge_call_count"] == len(overlap_calls)
        and [call.get("call_index") for call in overlap_calls] == list(range(len(overlap_calls))),
        "context-overlap call history is incomplete or reordered",
    )
    context_routes: dict[str, list[dict[str, Any]]] = {}
    for call in overlap_calls:
        _require_exact_keys(call, {"call_index", "left", "right", "output"}, "context-overlap merge call")
        projections = {}
        for side in ("left", "right", "output"):
            envelope = call[side]
            projection = envelope.get("context", {})
            origins = projection.get("origin_chunk_ids", [])
            _validate_provenance_envelope(
                envelope,
                inventory,
                origins=origins,
                projection_key="context",
                projection_validator=_validate_context_projection,
                label=f"context-overlap {side}",
            )
            projections[side] = projection
        left = projections["left"]
        right = projections["right"]
        output = projections["output"]
        expected_origins = list(
            dict.fromkeys(
                item.lower()
                for item in [*left["origin_chunk_ids"], *right["origin_chunk_ids"]]
            )
        )
        _require(
            left["file_path"] == right["file_path"] == output["file_path"]
            and right["start_line"] <= left["end_line"] + 1
            and output["start_line"] == min(left["start_line"], right["start_line"])
            and output["end_line"] == max(left["end_line"], right["end_line"])
            and output["origin_chunk_ids"] == expected_origins,
            "context-overlap merge input/output changed",
        )
        for chunk_id in output["origin_chunk_ids"]:
            context_routes[chunk_id] = _provenance_union(
                [*context_routes.get(chunk_id, []), *call["output"]["provenance_union"]]
            )

    expansion_calls = boundaries["context_expansion_calls"]
    _require(
        isinstance(expansion_calls, list)
        and boundaries["context_expansion_call_count"] == len(expansion_calls) == 1
        and expansion_calls[0].get("call_index") == 0,
        "context expansion boundary was omitted or duplicated",
    )
    expansion = expansion_calls[0]
    _require_exact_keys(expansion, {"call_index", "inputs", "outputs"}, "context expansion call")
    input_ids: list[str] = []
    for envelope in expansion["inputs"]:
        ranked = envelope.get("ranked", {})
        chunk_id = ranked.get("chunk_id", "")
        _validate_provenance_envelope(
            envelope,
            inventory,
            origins=[chunk_id],
            projection_key="ranked",
            projection_validator=_validate_ranked_projection,
            label="context expansion input",
        )
        input_ids.append(chunk_id)
    _require(
        input_ids == [row["chunk_id"] for row in rows],
        "context expansion input differs from the full prebonus roster",
    )
    origins_by_chunk: dict[str, list[str]] = {}
    output_origin_inventory: list[str] = []
    for envelope in expansion["outputs"]:
        context = envelope.get("context", {})
        origins = context.get("origin_chunk_ids", [])
        _validate_provenance_envelope(
            envelope,
            inventory,
            origins=origins,
            projection_key="context",
            projection_validator=_validate_context_projection,
            label="context expansion output",
        )
        output_origin_inventory.extend(origins)
        for chunk_id in origins:
            _require(chunk_id not in origins_by_chunk, "context expansion origin was duplicated")
            origins_by_chunk[chunk_id] = list(origins)
    _require(
        sorted(output_origin_inventory) == sorted(input_ids),
        "context expansion output omitted or invented an origin",
    )
    routes = {
        "candidate": candidate_routes,
        "same_chunk": same_chunk_routes,
        "context_overlap": context_routes,
    }
    return routes, origins_by_chunk


def _total_order_projection(
    row: Mapping[str, Any], *, rerank_score_override: float | None = None
) -> tuple[Any, ...]:
    rerank_score = row["rerank_score"] if rerank_score_override is None else rerank_score_override
    clamped = row["was_ceiling_clamped"]
    return (
        -round(rerank_score, 3),
        row["evidence_priority"],
        0 if clamped else 1,
        -row["pre_ceiling_rerank_score"] if clamped else 0.0,
        row["role_priority"],
        -rerank_score,
        -row["combined_score"],
        row["file_path"],
        row["start_line"],
        row["chunk_id"],
    )


def validate_raw_control_runtime(evidence: Mapping[str, Any]) -> dict[str, Any]:
    """Derive all pre-bonus facts from a raw policy-0 control snapshot."""

    _require_exact_keys(
        evidence,
        {
            "stage",
            "prebonus_input_candidate_ids",
            "prebonus_input_sha256",
            "ordered_edge_inventory",
            "ordered_edge_inventory_sha256",
            "pipeline_boundaries",
            "roster",
        },
        "runtime visibility evidence",
    )
    _require(evidence["stage"] == BONUS_STAGE, "runtime stage drifted")
    input_ids = evidence["prebonus_input_candidate_ids"]
    _require(isinstance(input_ids, list) and all(isinstance(value, str) and value for value in input_ids), "prebonus input candidate ids are invalid")
    _require(len(set(input_ids)) == len(input_ids), "prebonus input candidate ids are not unique")
    _require(_json_value_sha256(input_ids) == evidence["prebonus_input_sha256"], "prebonus input roster digest mismatch")
    inventory = evidence["ordered_edge_inventory"]
    _require(isinstance(inventory, list), "ordered edge inventory must be a list")
    for atom in inventory:
        _validate_direct_atom(atom)
    inventory_keys = [_provenance_key(atom) for atom in inventory]
    _require(len(inventory_keys) == len(set(inventory_keys)), "ordered edge inventory has a duplicate tuple")
    _require(len({atom["relation_id"] for atom in inventory}) == len(inventory), "ordered edge identity is not unique")
    _require(
        len({(atom["source_signal_id"], atom["ordered_edge_position"]) for atom in inventory}) == len(inventory),
        "ordered edge source position is not unique",
    )
    _require(
        len({atom["source_signal_id"] for atom in inventory})
        <= FROZEN_CAPS["maximum_graph_seed_signals"],
        "ordered edge inventory exceeds the frozen graph seed cap",
    )
    _require(_json_value_sha256(inventory) == evidence["ordered_edge_inventory_sha256"], "ordered edge inventory digest mismatch")
    inventory_set = set(inventory_keys)
    rows = evidence["roster"]
    _require(isinstance(rows, list), "runtime roster must be a list")
    _require(
        len(rows) <= FROZEN_CAPS["maximum_relation_expanded_candidates"],
        "runtime roster exceeds the frozen candidate cap",
    )
    required = {
        "candidate_id",
        "chunk_id",
        "file_path",
        "origin_chunk_ids",
        "merge_inputs",
        "provenance_union",
        "rerank_score",
        "evidence_priority",
        "was_ceiling_clamped",
        "pre_ceiling_rerank_score",
        "role_priority",
        "combined_score",
        "start_line",
        "prebonus_position",
        "score_parts",
        "reasons",
        "stage",
    }
    _require([row.get("candidate_id") for row in rows] == input_ids, "full candidate roster is missing, reordered, or contains an extra candidate")
    _require(
        all(
            isinstance(row, Mapping)
            and isinstance(row.get("chunk_id"), str)
            and row.get("chunk_id")
            for row in rows
        ),
        "runtime roster chunk inventory changed",
    )
    route_evidence, origins_by_chunk = _validate_pipeline_boundaries(
        evidence["pipeline_boundaries"],
        inventory,
        rows,
    )
    eligibility: dict[str, bool] = {}
    for row in rows:
        _require_exact_keys(row, required, "runtime roster row")
        _require(row["stage"] == BONUS_STAGE, "candidate stage drifted")
        _require(isinstance(row["chunk_id"], str) and row["chunk_id"], "candidate chunk id is invalid")
        _require(isinstance(row["file_path"], str) and row["file_path"], "candidate file path is invalid")
        origins = row["origin_chunk_ids"]
        _require(isinstance(origins, list) and origins and all(isinstance(value, str) and value for value in origins), "candidate origin chunks are invalid")
        _require(
            origins == origins_by_chunk.get(row["chunk_id"]),
            "candidate origins differ from the actual context expansion output",
        )
        merge_inputs = row["merge_inputs"]
        _require_exact_keys(merge_inputs, set(MERGE_ROUTES), "merge input routes")
        atoms: list[Mapping[str, Any]] = []
        for route in MERGE_ROUTES:
            _require(isinstance(merge_inputs[route], list), f"merge route is not a list: {route}")
            _require(
                merge_inputs[route]
                == route_evidence[route].get(row["chunk_id"], []),
                f"merge route was omitted or forged: {route}",
            )
            for atom in merge_inputs[route]:
                _validate_direct_atom(atom)
                _require(_provenance_key(atom) in inventory_set, "merge provenance atom is absent from actual ordered edge inventory")
                atoms.append(atom)
        # Rehydrate fields after complete-tuple set union and dedupe.
        derived_union = _provenance_union(atoms)
        _require(row["provenance_union"] == derived_union, "provenance union is not complete deterministic tuple dedupe")
        eligibility[row["candidate_id"]] = any(
            row["file_path"] == atom["target_file_path"]
            and atom["target_chunk_id"] in origins
            for atom in derived_union
        )
        _require(isinstance(row["was_ceiling_clamped"], bool), "ceiling marker is invalid")
        for field in ("rerank_score", "pre_ceiling_rerank_score", "role_priority", "combined_score"):
            _require(isinstance(row[field], (int, float)) and not isinstance(row[field], bool), f"ranking field is invalid: {field}")
        _require(isinstance(row["evidence_priority"], int), "evidence priority is invalid")
        _require(isinstance(row["start_line"], int) and row["start_line"] >= 0, "start line is invalid")
        _require(isinstance(row["score_parts"], Mapping), "score parts must be an object")
        _require(isinstance(row["reasons"], list), "reasons must be a list")
        _require(
            all(
                key == BONUS_SCORE_PART
                for key in row["score_parts"]
                if "exact" in key.lower() and "import" in key.lower()
            ),
            "exact imported-symbol score part name drifted",
        )
        _require(
            all(
                reason == BONUS_REASON
                for reason in row["reasons"]
                if isinstance(reason, str)
                and "exact" in reason.lower()
                and "import" in reason.lower()
            ),
            "exact imported-symbol reason drifted",
        )
        _require(BONUS_SCORE_PART not in row["score_parts"], "raw control contains treatment score contribution")
        _require(BONUS_REASON not in row["reasons"], "raw control contains treatment reason")

    preordered = sorted(rows, key=_total_order_projection)
    _require([row["prebonus_position"] for row in preordered] == list(range(1, len(rows) + 1)), "prebonus positions do not match complete existing total order")
    eligible_ordered = [row for row in preordered if eligibility[row["candidate_id"]]]
    winner = eligible_ordered[0] if eligible_ordered else None
    return {
        "winner_candidate_id": None if winner is None else str(winner["candidate_id"]),
        "eligible_candidate_ids": [str(row["candidate_id"]) for row in eligible_ordered],
        "prebonus_order": [str(row["candidate_id"]) for row in preordered],
    }


CONTROL_PRIVACY = {
    "status": "closed_no_source_content_or_click",
    "source_content_present": False,
    "click_accessed": False,
    "model_requests": 0,
    "ollama_or_local_model_used": False,
}


def validate_raw_control_capture(capture: Mapping[str, Any]) -> dict[str, Any]:
    _require_exact_keys(
        capture,
        {
            "schema_version",
            "program",
            "attempt_id",
            "phase",
            "query_id",
            "case_id",
            "case_sha256",
            "query",
            "query_sha256",
            "released_payload",
            "source_identity",
            "repeat",
            "input_order",
            "policy_contribution",
            "producer",
            "process_identity",
            "privacy",
            "serialization",
            "write_policy",
            "runtime_visibility",
        },
        "raw control capture",
    )
    _require(capture["schema_version"] == 1, "raw control schema changed")
    _require(capture["program"] == "p15-v3" and capture["attempt_id"] == "p15-v3-attempt-001", "raw control identity changed")
    _require(capture["phase"] == "task0a_raw_control", "raw control phase changed")
    _require(isinstance(capture["query_id"], str) and capture["query_id"], "raw control query id is invalid")
    _require(capture["case_id"] == capture["query_id"], "raw control case/query identity changed")
    _require(
        isinstance(capture["query"], str)
        and capture["query"].strip()
        and capture["query_sha256"] == _json_value_sha256(capture["query"]),
        "raw control query text binding changed",
    )
    for field in ("case_sha256",):
        _require(
            isinstance(capture[field], str)
            and len(capture[field]) == 64
            and all(character in "0123456789abcdef" for character in capture[field]),
            f"raw control digest is invalid: {field}",
        )
    released = capture["released_payload"]
    _require_exact_keys(
        released,
        {"repository_key", "path", "sha256"},
        "raw control released payload binding",
    )
    _require(
        isinstance(released["repository_key"], str)
        and released["repository_key"]
        and isinstance(released["path"], str)
        and released["path"]
        and isinstance(released["sha256"], str)
        and len(released["sha256"]) == 64
        and all(character in "0123456789abcdef" for character in released["sha256"]),
        "raw control released payload binding is invalid",
    )
    source_identity = capture["source_identity"]
    _require_exact_keys(
        source_identity,
        {
            "repository_key", "source_root", "repository_identity", "url", "commit",
            "tree", "inventory_sha256", "content_sha256",
        },
        "raw control source identity",
    )
    _require(
        source_identity["repository_key"] == released["repository_key"]
        and all(isinstance(value, str) and value for value in source_identity.values()),
        "raw control repository source identity changed",
    )
    _require(capture["repeat"] in {1, 2} and capture["input_order"] in {"canonical", "reverse"}, "raw control repeat/order changed")
    _require(capture["policy_contribution"] == 0.0, "raw control policy contribution is not zero")
    _require(capture["producer"] == "p15_v3_independent_raw_control_capture", "raw control producer changed")
    process = capture["process_identity"]
    _require_exact_keys(process, {"pid", "invocation_id"}, "raw control process identity")
    _require(isinstance(process["pid"], int) and process["pid"] > 0, "raw control pid is invalid")
    _require(isinstance(process["invocation_id"], str) and process["invocation_id"], "raw control invocation id is invalid")
    _require(capture["privacy"] == CONTROL_PRIVACY, "raw control privacy contract changed")
    _require(capture["serialization"] == "canonical_json_sort_keys_compact_utf8_no_trailing_newline", "raw control serialization changed")
    _require(capture["write_policy"] == "write_new_only_never_overwrite", "raw control write policy changed")
    return validate_raw_control_runtime(capture["runtime_visibility"])


def validate_control_freeze_marker(
    marker: Mapping[str, Any], controls_by_path: Mapping[str, Mapping[str, Any]]
) -> dict[str, Any]:
    _require_exact_keys(
        marker,
        {
            "schema_version",
            "program",
            "attempt_id",
            "phase",
            "status",
            "immutable",
            "required_mode",
            "query_id",
            "policy_contribution",
            "producer",
            "process_identity",
            "privacy",
            "serialization",
            "write_policy",
            "required_matrix",
            "snapshots",
            "common_stable_projection_sha256",
        },
        "control freeze marker",
    )
    _require(marker["schema_version"] == 1, "control marker schema changed")
    _require(marker["program"] == "p15-v3" and marker["attempt_id"] == "p15-v3-attempt-001", "control marker identity changed")
    _require(marker["phase"] == "task0a_control_freeze" and marker["status"] == "immutable_control_frozen", "control marker is not frozen")
    _require(marker["immutable"] is True and marker["required_mode"] == "0444", "control marker is not immutable read-only")
    _require(marker["policy_contribution"] == 0.0, "control marker contribution changed")
    _require(marker["producer"] == "p15_v3_independent_control_freezer", "control marker producer changed")
    freezer_process = marker["process_identity"]
    _require_exact_keys(freezer_process, {"pid", "invocation_id"}, "control marker process identity")
    _require(isinstance(freezer_process["pid"], int) and freezer_process["pid"] > 0, "control marker pid is invalid")
    _require(
        isinstance(freezer_process["invocation_id"], str) and freezer_process["invocation_id"],
        "control marker invocation id is invalid",
    )
    _require(marker["privacy"] == CONTROL_PRIVACY, "control marker privacy changed")
    _require(marker["serialization"] == "canonical_json_sort_keys_compact_utf8_no_trailing_newline", "control marker serialization changed")
    _require(marker["write_policy"] == "write_new_only_never_overwrite", "control marker write policy changed")
    required_matrix = [
        {"repeat": 1, "input_order": "canonical"},
        {"repeat": 1, "input_order": "reverse"},
        {"repeat": 2, "input_order": "canonical"},
        {"repeat": 2, "input_order": "reverse"},
    ]
    _require(marker["required_matrix"] == required_matrix, "control marker matrix changed")
    entries = marker["snapshots"]
    _require(isinstance(entries, list) and len(entries) == 4, "control marker must bind four snapshots")
    _require(
        [{"repeat": entry.get("repeat"), "input_order": entry.get("input_order")} for entry in entries]
        == required_matrix,
        "control snapshot matrix is incomplete or reordered",
    )
    pids: set[int] = set()
    invocations: set[str] = set()
    projections: list[str] = []
    derived_values: list[dict[str, Any]] = []
    for entry in entries:
        _require_exact_keys(
            entry,
            {
                "path",
                "canonical_sha256",
                "stable_projection_sha256",
                "repeat",
                "input_order",
                "pid",
                "invocation_id",
            },
            "control marker snapshot entry",
        )
        path = entry["path"]
        _require(path in controls_by_path, "control marker snapshot is missing")
        control = controls_by_path[path]
        _require(_json_value_sha256(control) == entry["canonical_sha256"], "raw control canonical digest mismatch")
        derived = validate_raw_control_capture(control)
        projection_digest = _json_value_sha256(control["runtime_visibility"])
        _require(projection_digest == entry["stable_projection_sha256"], "raw control stable projection digest mismatch")
        _require(control["query_id"] == marker["query_id"], "raw control query differs from marker")
        _require(control["repeat"] == entry["repeat"] and control["input_order"] == entry["input_order"], "raw control repeat/order differs from marker")
        process = control["process_identity"]
        _require(process == {"pid": entry["pid"], "invocation_id": entry["invocation_id"]}, "raw control process differs from marker")
        pids.add(process["pid"])
        invocations.add(process["invocation_id"])
        projections.append(projection_digest)
        derived_values.append(derived)
    _require(len(pids) == len(invocations) == 4, "raw controls do not use four distinct process identities")
    _require(freezer_process["pid"] not in pids, "control marker freezer reused a raw control pid")
    _require(
        freezer_process["invocation_id"] not in invocations,
        "control marker freezer reused a raw control invocation",
    )
    _require(len(set(projections)) == 1, "raw control runtime projection is not repeat/order stable")
    _require(len({_json_value_sha256(value) for value in derived_values}) == 1, "raw control derivation is not stable")
    _require(marker["common_stable_projection_sha256"] == projections[0], "control marker common projection changed")
    return {
        "derived": derived_values[0],
        "control_pids": pids,
        "control_invocations": invocations,
        "freezer_process": freezer_process,
    }


def build_external_control_seal_payload(
    control_directory: Path,
    reviewer_process: Mapping[str, Any],
) -> dict[str, Any]:
    """Independently reconstruct a seal from the exact on-disk control bundle."""

    _require(control_directory.name == CONTROL_DIRECTORY, "control directory path is not fixed")
    _require(control_directory.is_dir(), "control directory is missing")
    actual_inventory = {entry.name for entry in control_directory.iterdir()}
    _require(actual_inventory == set(CONTROL_INVENTORY), "control directory exact inventory changed")
    _require_exact_keys(reviewer_process, {"pid", "invocation_id"}, "external reviewer process identity")
    _require(
        isinstance(reviewer_process["pid"], int) and reviewer_process["pid"] > 0,
        "external reviewer pid is invalid",
    )
    _require(
        isinstance(reviewer_process["invocation_id"], str) and reviewer_process["invocation_id"],
        "external reviewer invocation id is invalid",
    )

    controls: dict[str, Mapping[str, Any]] = {}
    control_entries: list[dict[str, Any]] = []
    for filename in CONTROL_FILENAMES:
        control, byte_sha256 = _read_immutable_canonical_json(
            control_directory / filename,
            f"raw control {filename}",
        )
        derived = validate_raw_control_capture(control)
        del derived
        canonical_sha256 = _json_value_sha256(control)
        _require(byte_sha256 == canonical_sha256, f"raw control canonical digest differs from bytes: {filename}")
        controls[filename] = control
        control_entries.append(
            {
                "path": f"{CONTROL_DIRECTORY}/{filename}",
                "role": "raw_control",
                "byte_sha256": byte_sha256,
                "canonical_sha256": canonical_sha256,
                "stable_projection_sha256": _json_value_sha256(control["runtime_visibility"]),
                "mode": "0444",
                "no_symlink": True,
                "nlink": 1,
                "pid": control["process_identity"]["pid"],
                "invocation_id": control["process_identity"]["invocation_id"],
            }
        )

    marker, marker_byte_sha256 = _read_immutable_canonical_json(
        control_directory / CONTROL_MARKER_FILENAME,
        "control freeze marker",
    )
    marker_result = validate_control_freeze_marker(marker, controls)
    _require(marker_byte_sha256 == _json_value_sha256(marker), "control marker canonical digest differs from bytes")
    expected_snapshot_paths = list(CONTROL_FILENAMES)
    _require(
        [entry["path"] for entry in marker["snapshots"]] == expected_snapshot_paths,
        "control marker snapshot paths differ from fixed inventory",
    )
    all_pids = set(marker_result["control_pids"]) | {marker_result["freezer_process"]["pid"]}
    all_invocations = set(marker_result["control_invocations"]) | {
        marker_result["freezer_process"]["invocation_id"]
    }
    _require(reviewer_process["pid"] not in all_pids, "external reviewer reused a control/freezer pid")
    _require(
        reviewer_process["invocation_id"] not in all_invocations,
        "external reviewer reused a control/freezer invocation",
    )
    return {
        "schema_version": 1,
        "program": "p15-v3",
        "attempt_id": "p15-v3-attempt-001",
        "phase": "task0r_external_control_seal",
        "status": "accepted_immutable_control_bundle",
        "producer": "p15_v3_independent_external_control_reviewer",
        "process_identity": dict(reviewer_process),
        "capture_stopped_before_review": True,
        "control_directory": CONTROL_DIRECTORY,
        "exact_inventory": list(CONTROL_INVENTORY),
        "files": control_entries,
        "marker": {
            "path": f"{CONTROL_DIRECTORY}/{CONTROL_MARKER_FILENAME}",
            "role": "control_freeze_marker",
            "byte_sha256": marker_byte_sha256,
            "canonical_sha256": _json_value_sha256(marker),
            "mode": "0444",
            "no_symlink": True,
            "nlink": 1,
            "pid": marker["process_identity"]["pid"],
            "invocation_id": marker["process_identity"]["invocation_id"],
        },
        "common_stable_projection_sha256": marker["common_stable_projection_sha256"],
        "privacy": CONTROL_PRIVACY,
        "serialization": "canonical_json_sort_keys_compact_utf8_no_trailing_newline",
        "write_policy": "write_new_only_never_overwrite",
    }


def _validate_two_phase_payloads(
    marker: Mapping[str, Any],
    controls_by_path: Mapping[str, Mapping[str, Any]],
    treatment: Mapping[str, Any],
    external_seal: Mapping[str, Any],
) -> str | None:
    marker_result = validate_control_freeze_marker(marker, controls_by_path)
    _require_exact_keys(
        treatment,
        {
            "schema_version",
            "program",
            "attempt_id",
            "phase",
            "query_id",
            "policy_contribution",
            "external_control_seal",
            "raw_control_snapshot",
            "process_identity",
            "producer",
            "privacy",
            "write_policy",
            "output",
        },
        "treatment capture",
    )
    _require(treatment["schema_version"] == 1, "treatment schema changed")
    _require(treatment["program"] == "p15-v3" and treatment["attempt_id"] == "p15-v3-attempt-001", "treatment identity changed")
    _require(treatment["phase"] == "task0b_treatment", "treatment phase changed")
    _require(treatment["query_id"] == marker["query_id"], "treatment query differs from control marker")
    _require(treatment["policy_contribution"] == 0.04, "treatment contribution changed")
    _require(treatment["producer"] == "p15_v3_independent_treatment_capture", "treatment producer changed")
    _require(treatment["privacy"] == CONTROL_PRIVACY, "treatment privacy changed")
    _require(treatment["write_policy"] == "write_new_only_never_overwrite", "treatment write policy changed")
    seal_ref = treatment["external_control_seal"]
    _require_exact_keys(seal_ref, {"path", "byte_sha256"}, "treatment external seal reference")
    _require(
        seal_ref
        == {
            "path": CONTROL_SEAL_FILENAME,
            "byte_sha256": _json_value_sha256(external_seal),
        },
        "treatment does not reference the exact external control seal",
    )
    raw_ref = treatment["raw_control_snapshot"]
    _require_exact_keys(
        raw_ref,
        {"path", "byte_sha256", "canonical_sha256", "stable_projection_sha256"},
        "treatment raw control reference",
    )
    seal_entries = {entry["path"]: entry for entry in external_seal["files"]}
    _require(raw_ref["path"] in seal_entries, "treatment raw control is not external-seal-bound")
    seal_entry = seal_entries[raw_ref["path"]]
    _require(
        raw_ref
        == {
            "path": seal_entry["path"],
            "byte_sha256": seal_entry["byte_sha256"],
            "canonical_sha256": seal_entry["canonical_sha256"],
            "stable_projection_sha256": seal_entry["stable_projection_sha256"],
        },
        "treatment raw control reference differs from external seal",
    )
    process = treatment["process_identity"]
    _require_exact_keys(process, {"pid", "invocation_id"}, "treatment process identity")
    _require(isinstance(process["pid"], int) and process["pid"] > 0, "treatment pid is invalid")
    _require(isinstance(process["invocation_id"], str) and process["invocation_id"], "treatment invocation id is invalid")
    _require(process["pid"] not in marker_result["control_pids"], "treatment reused a control pid")
    _require(process["invocation_id"] not in marker_result["control_invocations"], "treatment reused a control invocation")
    _require(process["pid"] != marker_result["freezer_process"]["pid"], "treatment reused the freezer pid")
    _require(
        process["invocation_id"] != marker_result["freezer_process"]["invocation_id"],
        "treatment reused the freezer invocation",
    )
    reviewer_process = external_seal["process_identity"]
    _require(process["pid"] != reviewer_process["pid"], "treatment reused the external reviewer pid")
    _require(
        process["invocation_id"] != reviewer_process["invocation_id"],
        "treatment reused the external reviewer invocation",
    )

    raw_control = controls_by_path[Path(raw_ref["path"]).name]
    runtime = raw_control["runtime_visibility"]
    derived = validate_raw_control_runtime(runtime)
    rows_by_id = {row["candidate_id"]: row for row in runtime["roster"]}
    winner_id = derived["winner_candidate_id"]
    post_scores = {
        candidate_id: rows_by_id[candidate_id]["rerank_score"] + (0.04 if candidate_id == winner_id else 0.0)
        for candidate_id in derived["prebonus_order"]
    }
    post_order = sorted(
        derived["prebonus_order"],
        key=lambda candidate_id: _total_order_projection(
            rows_by_id[candidate_id], rerank_score_override=post_scores[candidate_id]
        ),
    )
    output = treatment["output"]
    _require_exact_keys(
        output,
        {
            "winner_candidate_id",
            "score_part",
            "reason",
            "bonus",
            "postbonus_order",
            "postbonus_rerank_scores",
        },
        "treatment output",
    )
    _require(output["winner_candidate_id"] == winner_id, "treatment winner differs from frozen control derivation")
    expected_score_part = BONUS_SCORE_PART if winner_id is not None else None
    expected_reason = BONUS_REASON if winner_id is not None else None
    expected_bonus = 0.04 if winner_id is not None else 0.0
    _require(output["score_part"] == expected_score_part, "treatment score part drifted")
    _require(output["reason"] == expected_reason, "treatment reason drifted")
    _require(output["bonus"] == expected_bonus, "treatment bonus does not match winner cardinality")
    _require(output["postbonus_order"] == post_order, "treatment postbonus order differs from frozen control")
    expected_scores = [
        {"candidate_id": candidate_id, "rerank_score": post_scores[candidate_id]}
        for candidate_id in post_order
    ]
    _require(output["postbonus_rerank_scores"] == expected_scores, "treatment postbonus scores differ from frozen control")
    return winner_id


def validate_two_phase_runtime(
    run_root: Path,
    *,
    manifest_bound_control_seal_sha256: str,
) -> str | None:
    """Validate treatment only from fixed on-disk paths and an externally pinned seal digest."""

    _require(
        isinstance(manifest_bound_control_seal_sha256, str)
        and len(manifest_bound_control_seal_sha256) == 64
        and all(character in "0123456789abcdef" for character in manifest_bound_control_seal_sha256),
        "manifest-bound external control seal digest is missing or invalid",
    )
    seal_path = run_root / CONTROL_SEAL_FILENAME
    seal, seal_byte_sha256 = _read_immutable_canonical_json(seal_path, "external control seal")
    _require(
        seal_byte_sha256 == manifest_bound_control_seal_sha256,
        "external control seal differs from manifest-bound digest",
    )
    _require_exact_keys(
        seal,
        {
            "schema_version",
            "program",
            "attempt_id",
            "phase",
            "status",
            "producer",
            "process_identity",
            "capture_stopped_before_review",
            "control_directory",
            "exact_inventory",
            "files",
            "marker",
            "common_stable_projection_sha256",
            "privacy",
            "serialization",
            "write_policy",
        },
        "external control seal",
    )
    _require(
        seal["schema_version"] == 1
        and seal["program"] == "p15-v3"
        and seal["attempt_id"] == "p15-v3-attempt-001",
        "external control seal identity changed",
    )
    _require(
        seal["phase"] == "task0r_external_control_seal"
        and seal["status"] == "accepted_immutable_control_bundle",
        "external control seal disposition is not accepted",
    )
    _require(
        seal["producer"] == "p15_v3_independent_external_control_reviewer",
        "external control seal producer changed",
    )
    _require(seal["capture_stopped_before_review"] is True, "capture did not stop before external review")
    _require(seal["privacy"] == CONTROL_PRIVACY, "external control seal privacy changed")
    _require(
        seal["serialization"] == "canonical_json_sort_keys_compact_utf8_no_trailing_newline",
        "external control seal serialization changed",
    )
    _require(seal["write_policy"] == "write_new_only_never_overwrite", "external control seal write policy changed")
    rebuilt_seal = build_external_control_seal_payload(
        run_root / CONTROL_DIRECTORY,
        seal["process_identity"],
    )
    _require(seal == rebuilt_seal, "external control seal does not match actual control bytes/stat")

    controls: dict[str, Mapping[str, Any]] = {}
    for filename in CONTROL_FILENAMES:
        controls[filename] = _read_immutable_canonical_json(
            run_root / CONTROL_DIRECTORY / filename,
            f"sealed raw control {filename}",
        )[0]
    marker = _read_immutable_canonical_json(
        run_root / CONTROL_DIRECTORY / CONTROL_MARKER_FILENAME,
        "sealed control freeze marker",
    )[0]
    treatment = _read_immutable_canonical_json(
        run_root / TREATMENT_FILENAME,
        "treatment capture",
    )[0]
    return _validate_two_phase_payloads(marker, controls, treatment, seal)


def _validate_identity_files(manifest: Mapping[str, Any]) -> None:
    identities = manifest["identities"]
    _require_exact_keys(
        identities,
        {"design", "plan", "manifest_path", "harness_path", "harness_tests_path"},
        "v3 identities",
    )
    expected = {
        "design": (
            "docs/superpowers/specs/2026-08-01-p15-v3-exact-provenance-bonus-design.md",
            DESIGN_SHA256,
        ),
        "plan": (
            "docs/superpowers/plans/2026-08-01-p15-v3-exact-provenance-bonus-plan.md",
            PLAN_SHA256,
        ),
    }
    for name, (path, digest) in expected.items():
        _require(identities[name] == {"path": path, "sha256": digest}, f"{name} identity changed")
        _require(_sha256(_repo_path(path)) == digest, f"{name} digest mismatch")
    _require(identities["manifest_path"] == "tests/fixtures/p15_v3_exact_provenance_bonus/input_manifest.json", "manifest path changed")
    _require(identities["harness_path"] == "tests/p15_v3_exact_provenance_bonus_acceptance.py", "harness path changed")
    _require(identities["harness_tests_path"] == "tests/test_p15_v3_exact_provenance_bonus_acceptance.py", "test path changed")


def _validate_v2_terminal(manifest: Mapping[str, Any]) -> dict[str, int]:
    contract = manifest["v2_terminal"]
    _require(
        contract
        == {
            "attempt_id": "p15-v2-attempt-001",
            "status": "task0d_hash_reject",
            "disposition": "reject",
            "reject_index_path": ".quality/p15-runs/p15-v2-attempt-001/reject-index.json",
            "reject_index_sha256": V2_REJECT_INDEX_SHA256,
            "recursive_artifact_verification": True,
            "captures_reusable": False,
            "efficacy_credit": False,
        },
        "v2 terminal contract changed",
    )
    index_path = _repo_path(contract["reject_index_path"])
    _require(_sha256(index_path) == V2_REJECT_INDEX_SHA256, "v2 reject index digest mismatch")
    index = _read_json(index_path)
    _require(index["schema_version"] == 1, "v2 reject schema changed")
    _require(index["program"] == "p15-v2" and index["attempt_id"] == "p15-v2-attempt-001", "v2 reject identity changed")
    _require(index["status"] == "task0d_hash_reject", "v2 reject status changed")
    _require(index["immutable"] is True and index["disposition"] == "reject", "v2 terminal is not immutable reject")
    _require(index["online_started"] is False and index["online_evidence_created"] is False, "v2 online boundary changed")
    _require(index["embedding_requests"] == 0 and index["planner_started"] is False, "v2 request boundary changed")
    _require(index["ollama_or_local_model_used"] is False, "v2 used a local model")
    _require(index["heldout_opened"] is False and index["click_plaintext_created"] is False, "v2 Click boundary changed")
    _require(index["hash_proceed_marker_created"] is False, "v2 unexpectedly proceeded")
    _require(index["required_item_total"] == 24, "v2 denominator changed")
    _require(index["baseline_hits"] == index["oracle_hits"] == 17, "v2 hit totals changed")
    _require(index["micro_recall_delta"] == 0.0, "v2 recall delta changed")
    _require(index["new_required_items"] == index["exact_rank_gains"] == index["lost_required_items"] == 0, "v2 efficacy outcome changed")
    _require(index["deterministic"] == {"baseline": True, "oracle": True}, "v2 determinism changed")
    _require(index["product_identity"]["baseline"] == BASELINE, "v2 product baseline changed")
    _require(index["product_identity"]["clean_against_baseline"] is True, "v2 product was not clean")
    _require(index["identities"] == EXPECTED_V2_IDENTITIES, "v2 identity inventory changed")
    _require(index["dispositions"] == EXPECTED_V2_DISPOSITIONS, "v2 disposition inventory changed")
    _require(index["artifacts"] == EXPECTED_V2_ARTIFACTS, "v2 artifact inventory changed")

    for identity in EXPECTED_V2_IDENTITIES.values():
        _require(_sha256(_repo_path(identity["path"])) == identity["sha256"], f"v2 identity digest mismatch: {identity['path']}")
    for relative, digest in EXPECTED_V2_DISPOSITIONS.items():
        _require(_sha256(_repo_path(relative)) == digest, f"v2 disposition digest mismatch: {relative}")

    run_root = index_path.parent
    expected_inventory = set(EXPECTED_V2_ARTIFACTS) | {"reject-index.json"}
    actual_inventory = {path.relative_to(run_root).as_posix() for path in run_root.rglob("*") if path.is_file()}
    _require(actual_inventory == expected_inventory, "v2 run inventory is not exact")
    for relative, digest in EXPECTED_V2_ARTIFACTS.items():
        _require(_sha256(run_root / relative) == digest, f"v2 artifact digest mismatch: {relative}")

    capture_paths = [run_root / path for path in EXPECTED_V2_ARTIFACTS if path.endswith(("canonical.json", "reverse.json"))]
    _require(len(capture_paths) == 8, "v2 capture count changed")
    pids: set[int] = set()
    invocation_ids: set[str] = set()
    for path in capture_paths:
        capture = _read_json(path)
        _require(capture["schema_version"] == 2 and capture["program"] == "p15-v2", "v2 capture identity changed")
        _require(capture["attempt_id"] == "p15-v2-attempt-001" and capture["profile"] == "hash", "v2 capture profile changed")
        _require(capture["embedding"]["provider"] == "hash", "v2 capture provider changed")
        _require(capture["embedding_requests"]["total"] == 0, "v2 capture made an embedding request")
        _require(capture["embedding"]["planner_enabled"] is False, "v2 planner was enabled")
        process = capture["implementation"]["process_identity"]
        _require(isinstance(process["pid"], int), "v2 pid is invalid")
        _require(isinstance(process["invocation_id"], str) and process["invocation_id"], "v2 invocation id is invalid")
        pids.add(process["pid"])
        invocation_ids.add(process["invocation_id"])
    _require(len(pids) == len(invocation_ids) == 8, "v2 captures did not use eight distinct process identities")
    _require(index["capture_process_identity"] == {"capture_count": 8, "distinct_pid_count": 8, "distinct_invocation_id_count": 8}, "v2 process summary changed")

    comparison = _read_json(run_root / "oracle/hash/development_and_protected/comparison.json")
    _require(comparison["disposition"] == "reject", "v2 comparison is not reject")
    _require(comparison["required_item_total"] == 24, "v2 comparison denominator changed")
    _require(comparison["baseline_hits"] == comparison["candidate_hits"] == 17, "v2 comparison hits changed")
    _require(comparison["micro_recall_delta"] == 0.0, "v2 comparison delta changed")
    _require(comparison["new_required_items"] == comparison["exact_rank_gains"] == comparison["lost_required_items"] == [], "v2 comparison result changed")
    terminal = _read_json(run_root / "terminal-reject.json")
    _require(terminal["status"] == "reject" and terminal["terminal"] is True, "v2 terminal file changed")
    _require(terminal["comparison_sha256"] == EXPECTED_V2_ARTIFACTS["oracle/hash/development_and_protected/comparison.json"], "v2 terminal comparison binding changed")
    return {"artifacts": len(EXPECTED_V2_ARTIFACTS), "captures": 8, "distinct_processes": 8}


def _validate_policy_and_nonchanges(manifest: Mapping[str, Any]) -> None:
    expected_policy = {
        "name": "B",
        "policy_a": "permanently_forbidden_never_run",
        "factor": "direct_closed_exact_imported_symbol_tuple_binary_bonus",
        "ablation_values": [0.0, 0.04],
        "provenance_tuple_fields": list(PROVENANCE_FIELDS),
        "emission": "direct_python_ast_imports_resolved_exact_exact_python_imported_symbol_only",
        "propagation": "forbidden_no_hops_ancestry_adjacency_witness_or_context_synthesis",
        "merge_routes": list(MERGE_ROUTES),
        "merge_operation": "lexicographically_sorted_complete_tuple_set_union_and_dedupe",
        "eligibility_join": "candidate.file_path=tuple.target_file_path_and_candidate.origin_chunk_ids_contains_tuple.target_chunk_id",
        "winner_cardinality_per_case": "exactly_one_if_eligible_set_nonempty_else_zero",
        "prebonus_stage": "after_identifier_owner_ceiling_project_and_frontend_cohort",
        "existing_total_order": list(EXISTING_TOTAL_ORDER),
        "winner_order": "minimum_complete_existing_prebonus_total_order_over_derived_eligible_full_roster",
        "input_order_independent": True,
        "bonus_target": "rerank_score_only",
        "score_part": BONUS_SCORE_PART,
        "reason": BONUS_REASON,
        "aggregation": "boolean_max_not_sum",
        "maximum_case_bonus": 0.04,
        "postbonus_order": "rerank_full_roster_with_same_existing_total_order",
        "stage": BONUS_STAGE,
        "eligibility_feedback": False,
    }
    _require(manifest["policy"] == expected_policy, "sole Policy B contract changed")
    frozen = manifest["frozen_nonchanges"]
    _require_exact_keys(
        frozen,
        {
            "top_k",
            "relation_slots",
            "slot_ownership",
            "budgets",
            "definition_owner_behavior",
            "imports_relation_weight",
            "graph_decay",
            "existing_score_part",
            "existing_reason",
            "traversal_direction",
            "merge_semantics",
            "context_expansion",
            "final_selection",
            "caps",
        },
        "frozen nonchanges",
    )
    _require(frozen["top_k"] == 12 and frozen["relation_slots"] == 2, "top-k or slot count changed")
    _require(frozen["slot_ownership"] == frozen["definition_owner_behavior"] == "unchanged", "owner behavior changed")
    _require(frozen["budgets"] == "all_unchanged", "budget changed")
    _require(frozen["imports_relation_weight"] == 0.85 and frozen["graph_decay"] == 0.8, "existing weights changed")
    _require(frozen["existing_score_part"] == "graph_imports_match", "existing score part changed")
    _require(frozen["existing_reason"] == "static module dependency", "existing reason changed")
    _require(frozen["traversal_direction"] == "outgoing_only", "traversal direction changed")
    _require(frozen["context_expansion"] == frozen["final_selection"] == "unchanged", "final pipeline changed")
    _require(frozen["merge_semantics"] == "unchanged_except_preserving_closed_exact_provenance_union_visibility", "merge boundary changed")
    validate_cap_constants(frozen["caps"], frozen["caps"])


def _validate_formula_contract(manifest: Mapping[str, Any]) -> None:
    formulas = manifest["formula_contract"]
    _require_exact_keys(formulas, {"structure_closed", "cap_constants", "degree_delta", "saturation_visibility", "runtime_visibility"}, "formula contract")
    _require(
        formulas["structure_closed"]
        == {
            "top_level_keys": [
                "selected_files",
                "non_relation_fields",
                "relation_buckets",
                "module_projection_sha256",
                "non_python_projection_sha256",
            ],
            "non_relation_field_keys": ["active_chunks", "signals_by_producer"],
            "complete_key_sets": "frozen_from_baseline_and_identical_in_both_arms",
            "selected_files_nonrelation_producer_module_nonpython": "direct_equality",
            "all_non_resolved_exact_relation_buckets": "direct_equality",
            "resolved_exact_equation": "oracle_resolved_exact=baseline_resolved_exact+oracle_causal_relation_count",
        },
        "structure formula changed",
    )
    _validate_two_phase_protocol(manifest)


def _validate_two_phase_protocol(manifest: Mapping[str, Any]) -> None:
    expected = {
        "status": "protocol_frozen_no_capture_authorized",
        "control": {
            "phase": "task0a_raw_control",
            "policy_contribution": 0.0,
            "required_matrix": [
                {"repeat": 1, "input_order": "canonical"},
                {"repeat": 1, "input_order": "reverse"},
                {"repeat": 2, "input_order": "canonical"},
                {"repeat": 2, "input_order": "reverse"},
            ],
            "capture_count_per_query": 4,
            "each_capture_separate_process": True,
            "distinct_pid_and_invocation_required": True,
            "producer": "p15_v3_independent_raw_control_capture",
            "schema_version": 1,
            "privacy": {
                "status": "closed_no_source_content_or_click",
                "source_content_allowed": False,
                "click_material_allowed": False,
                "model_request_allowed": False,
            },
            "serialization": "canonical_json_sort_keys_compact_utf8_no_trailing_newline",
            "write_policy": "write_new_only_never_overwrite",
            "stable_projection": "runtime_visibility_exact_equality_across_full_repeat_order_matrix",
            "freeze_marker": {
                "producer": "p15_v3_independent_control_freezer",
                "status": "immutable_control_frozen",
                "required_mode": "0444",
                "process_identity_required": True,
                "canonical_digest_required": True,
                "binds": [
                    "four_raw_control_paths",
                    "four_raw_control_digests",
                    "common_stable_projection_sha256",
                    "repeat_order_matrix",
                    "producer",
                    "process_identities",
                    "schema_version",
                    "privacy",
                    "policy_contribution",
                    "write_policy",
                ],
            },
        },
        "external_control_seal": {
            "phase": "task0r_external_control_seal",
            "capture_must_stop_before_review": True,
            "producer": "p15_v3_independent_external_control_reviewer",
            "process_identity_disjoint_from_controls_and_freezer": True,
            "control_directory": "task0a-control",
            "exact_inventory": [
                "control-r1-canonical.json",
                "control-r1-reverse.json",
                "control-r2-canonical.json",
                "control-r2-reverse.json",
                "control-freeze-marker.json",
            ],
            "reads_actual_bytes_and_lstat": True,
            "file_requirements": [
                "byte_sha256",
                "canonical_sha256",
                "stable_projection_sha256_for_each_raw_control",
                "mode_0444",
                "no_symlink",
                "nlink_1",
                "pid_invocation_isolation",
            ],
            "disposition_path": ".quality/p15-runs/p15-v3-attempt-001/task0-control-seal-disposition.json",
            "disposition_status": "pending_capture_and_independent_review",
            "disposition_sha256": None,
            "required_mode": "0444",
            "manifest_exact_digest_required_before_treatment": True,
            "future_manifest_revision_required": True,
            "write_policy": "write_new_only_never_overwrite",
        },
        "treatment": {
            "phase": "task0b_treatment",
            "policy_contribution": 0.04,
            "blocked_before_manifest_bound_external_control_seal": True,
            "producer": "p15_v3_independent_treatment_capture",
            "schema_version": 1,
            "required_fields": [
                "schema_version",
                "program",
                "attempt_id",
                "phase",
                "query_id",
                "policy_contribution",
                "external_control_seal",
                "raw_control_snapshot",
                "process_identity",
                "producer",
                "privacy",
                "write_policy",
                "output",
            ],
            "forbidden_self_reported_inputs": [
                "candidate_roster",
                "ordered_edge_inventory",
                "merge_inputs",
                "provenance_union",
                "eligibility",
                "prebonus_order",
            ],
            "derivation": "validator_reloads_actual_bytes_from_fixed_paths_and_rebuilds_all_prebonus_facts_from_exact_external_seal_bound_raw_control",
            "validator_input": "fixed_on_disk_paths_only_no_in_memory_evidence_payloads",
            "process_identity_disjoint_from_controls_freezer_and_external_reviewer": True,
            "privacy": "same_closed_privacy_as_control",
            "write_policy": "write_new_only_never_overwrite",
        },
    }
    _require(manifest["task0_two_phase_runtime"] == expected, "Task0 two-phase runtime protocol changed")
    formulas = manifest["formula_contract"]
    _require(formulas["cap_constants"] == "direct_equality_to_frozen_constants_in_both_arms", "cap formula changed")
    _require(formulas["degree_delta"] == "oracle_observed_max_outgoing<=baseline_observed_max_outgoing+maximum_exact_relations_per_source", "degree formula changed")
    _require(
        formulas["saturation_visibility"]
        == {
            "edge_cap": 64,
            "proof": "reconstruct_real_complete_edge_identities_from_hash_bound_v2_capture_and_match_enumerated_positions_1_through_64",
            "position_65": "relocated_real_position_64_edge_fails_closed_on_cap",
            "cap_increase": "forbidden",
        },
        "saturation formula changed",
    )
    runtime = formulas["runtime_visibility"]
    _require_exact_keys(
        runtime,
        {
            "source_of_truth",
            "candidate_scope",
            "pipeline_boundary_proof",
            "envelope_fields",
            "required_fields",
            "derived_fields",
            "self_reported_boolean_or_count_is_proof",
            "winner_rule",
            "omission_proof",
            "bonus_rule",
            "postbonus_rule",
        },
        "runtime formula",
    )
    _require(
        runtime["source_of_truth"] == "manifest_bound_external_seal_and_on_disk_raw_control_only",
        "runtime source of truth changed",
    )
    _require(runtime["candidate_scope"] == "complete_ranked_candidate_roster_before_context_expansion_including_ineligible_candidates", "runtime candidate scope changed")
    _require(
        runtime["pipeline_boundary_proof"]
        == "complete_ordered_graph_outgoing_candidate_same_chunk_and_context_overlap_calls_with_actual_context_origins",
        "runtime pipeline boundary proof changed",
    )
    _require(
        runtime["envelope_fields"]
        == [
            "stage",
            "prebonus_input_candidate_ids",
            "prebonus_input_sha256",
            "ordered_edge_inventory",
            "ordered_edge_inventory_sha256",
            "pipeline_boundaries",
            "roster",
        ],
        "runtime envelope fields changed",
    )
    _require(runtime["self_reported_boolean_or_count_is_proof"] is False, "runtime accepted self-reported eligibility")
    _require(runtime["winner_rule"] == "one_minimum_existing_total_order_eligible_candidate_from_full_roster", "runtime winner formula changed")
    _require(runtime["omission_proof"] == "full_roster_and_recomputed_eligibility_show_no_better_eligible_candidate", "runtime omission proof changed")
    _require(runtime["bonus_rule"] == "winner_rerank_score_only_exact_imported_symbol_0.04_max_not_sum", "runtime bonus formula changed")
    _require(runtime["postbonus_rule"] == "same_existing_total_order_reapplied_to_full_roster", "runtime postbonus rule changed")
    _require(
        runtime["required_fields"]
        == [
            "candidate_id", "chunk_id", "file_path", "origin_chunk_ids",
            "merge_inputs", "provenance_union", "rerank_score",
            "evidence_priority", "was_ceiling_clamped",
            "pre_ceiling_rerank_score", "role_priority", "combined_score",
            "start_line", "prebonus_position", "score_parts", "reasons", "stage",
        ],
        "runtime fields changed",
    )
    _require(
        runtime["derived_fields"]
        == [
            "every_merge_atom_exactly_matches_actual_ordered_edge_inventory",
            "deduped_complete_provenance_union",
            "eligibility_from_candidate_target_tuple_join",
            "prebonus_total_order",
            "winner",
            "treatment_postbonus_total_order_from_same_control",
        ],
        "runtime derived fields changed",
    )


def _expected_phase_a_control_engine() -> Mapping[str, Any]:
    return {
        "status": "implemented_inert_awaiting_independent_review",
        "execution_authorized": False,
        "capture_authorized": False,
        "online_model_required_after_future_authorization": True,
        "local_ollama_forbidden": True,
        "new_oracle_forbidden": True,
        "released_input_repository_order": ["httpx", "poetry_core"],
        "query_count": 8,
        "raw_capture_count": 32,
        "freeze_marker_count": 8,
        "query_root_template": ".quality/p15-runs/p15-v3-attempt-001/task0a/{repository_key}/{case_id}",
        "control_directory": CONTROL_DIRECTORY,
        "raw_control_filenames": list(CONTROL_FILENAMES),
        "freeze_marker_filename": CONTROL_MARKER_FILENAME,
        "trusted_staging": {
            "namespace": ".quality/p15-v3-phase-a-staging",
            "leaf_pattern": "p15-v3-attempt-001-[0-9a-f]{32}",
            "namespace_mode": "0700",
            "leaf_mode": "0700",
            "owner": "effective_uid_of_authorized_runner",
            "directory_type": "real_directory_no_symlink",
            "artifact_type": "regular_non_symlink_nlink_1",
            "lifecycle": "whole_attempt_tree_private_until_single_atomic_no_overwrite_directory_publish",
            "publication": "all_40_artifacts_validated_readback_fsynced_then_one_atomic_directory_rename_no_overwrite_and_parent_fsync",
            "publication_identity": "record_published_tree_dev_ino_in_trusted_run_parent_before_postpublish_verification",
            "failure_state": "rollback_nofollow_removes_run_name_substitute_and_locates_published_inode_within_authorized_run_parent_then_removes_attempt_tree_and_fsyncs_parents_final_absent_retriable_else_inode_outside_parent_terminal_non_retriable",
            "job_scratch_pattern": ".phase-a-job-{global_index_2d}-{invocation_id_32hex}",
            "job_scratch_lifecycle": "created_via_captured_leaf_dirfd_inode_bound_and_removed_before_child_evidence_or_freezer",
            "job_scratch_outside_leaf": "forbidden",
            "namespace_outside_run": "absent_or_empty",
            "other_temporary_or_third_outputs": "forbidden",
        },
        "input_closure": {
            "source": "exact_manifest_bound_released_payload_bytes_only",
            "case_fields": [
                "id", "query", "required", "contextual", "baseline_selected_paths",
                "baseline_required_ranks", "eligible_missing_required_paths",
                "membership_change_eligible", "protected_winner", "exact_import_witnesses",
            ],
            "policy_contribution": 0.0,
            "repeat_order_matrix": [
                {"repeat": 1, "input_order": "canonical"},
                {"repeat": 1, "input_order": "reverse"},
                {"repeat": 2, "input_order": "canonical"},
                {"repeat": 2, "input_order": "reverse"},
            ],
            "one_separate_process_per_raw_capture": True,
            "independent_fifth_freezer_process_per_query": True,
            "stable_projection_exact_equality_required": True,
            "stop_after_freeze_marker": True,
        },
        "write_new_protocol": {
            "required_initial_run_root_state": "absent",
            "create_only_after_future_independent_capture_authorization": True,
            "open_mode": "exclusive_create",
            "serialization": "canonical_json_sort_keys_compact_utf8_no_trailing_newline",
            "final_mode": "0444",
            "regular_non_symlink": True,
            "nlink": 1,
            "overwrite_forbidden": True,
            "temporary_or_third_output_forbidden": True,
        },
    }


def _validate_phase_a_engine_contract(
    manifest: Mapping[str, Any],
    *,
    require_inert: bool = True,
) -> None:
    expected = dict(_expected_phase_a_control_engine())
    if not require_inert:
        expected["execution_authorized"] = manifest["phase_a_control_engine"].get(
            "execution_authorized"
        )
        expected["capture_authorized"] = manifest["phase_a_control_engine"].get(
            "capture_authorized"
        )
    _require(
        manifest["phase_a_control_engine"] == expected,
        "Phase A control engine contract changed or became executable",
    )


@dataclass(frozen=True)
class PhaseASourceIdentity:
    repository_key: str
    source_root: str
    repository_identity: str
    url: str
    commit: str
    tree: str
    inventory_sha256: str
    content_sha256: str


@dataclass(frozen=True)
class PhaseAArtifactJob:
    kind: str
    global_index: int
    repository_key: str
    case_id: str
    query: str
    case_sha256: str
    released_payload_path: str
    released_payload_sha256: str
    source_identity: PhaseASourceIdentity
    repeat: int | None
    input_order: str | None
    repo_relative_path: str
    run_relative_path: str


@dataclass(frozen=True)
class PhaseAQueryPlan:
    repository_key: str
    case_id: str
    query: str
    case_sha256: str
    released_payload_path: str
    released_payload_sha256: str
    query_root: str
    raw_control_jobs: tuple[PhaseAArtifactJob, ...]
    freeze_marker_job: PhaseAArtifactJob


@dataclass(frozen=True)
class PhaseAControlPlan:
    status: str
    queries: tuple[PhaseAQueryPlan, ...]
    raw_control_jobs: tuple[PhaseAArtifactJob, ...]
    freeze_marker_jobs: tuple[PhaseAArtifactJob, ...]

    @property
    def query_count(self) -> int:
        return len(self.queries)

    @property
    def raw_capture_count(self) -> int:
        return len(self.raw_control_jobs)

    @property
    def freeze_marker_count(self) -> int:
        return len(self.freeze_marker_jobs)

    @property
    def global_artifact_order(self) -> tuple[PhaseAArtifactJob, ...]:
        return self.raw_control_jobs + self.freeze_marker_jobs

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)


def build_phase_a_control_plan(
    manifest: Mapping[str, Any],
    *,
    require_inert: bool = True,
) -> PhaseAControlPlan:
    """Derive the closed Phase A work list without executing or writing anything."""

    _validate_phase_a_engine_contract(manifest, require_inert=require_inert)
    engine = manifest["phase_a_control_engine"]
    slots = {slot["repository_key"]: slot for slot in manifest["fresh_efficacy"]["slots"]}
    run_root = manifest["evidence"]["run_root"].rstrip("/")
    query_specs: list[dict[str, Any]] = []
    raw_jobs: list[PhaseAArtifactJob] = []
    for repository_key in engine["released_input_repository_order"]:
        slot = slots[repository_key]
        path, digest, _, _ = FRESH_RELEASED_PAYLOADS[repository_key]
        payload, actual_digest = _read_immutable_canonical_json(
            _repo_path(path), f"Phase A released input {repository_key}"
        )
        _require(actual_digest == digest == slot["released_payload_sha256"], "Phase A released input digest changed")
        for case in payload["cases"]:
            query_root = engine["query_root_template"].format(
                repository_key=repository_key,
                case_id=case["id"],
            )
            jobs: list[PhaseAArtifactJob] = []
            for matrix, filename in zip(engine["input_closure"]["repeat_order_matrix"], CONTROL_FILENAMES, strict=True):
                repo_relative_path = f"{query_root}/{CONTROL_DIRECTORY}/{filename}"
                job = PhaseAArtifactJob(
                    kind="raw_control",
                    global_index=len(raw_jobs),
                    repository_key=repository_key,
                    case_id=case["id"],
                    query=case["query"],
                    case_sha256=_json_value_sha256(case),
                    released_payload_path=path,
                    released_payload_sha256=digest,
                    source_identity=PhaseASourceIdentity(
                        repository_key=repository_key,
                        source_root=slot["source_root"],
                        repository_identity=slot["repository_identity"],
                        url=slot["url"],
                        commit=slot["commit"],
                        tree=slot["tree"],
                        inventory_sha256=slot["inventory_sha256"],
                        content_sha256=slot["content_sha256"],
                    ),
                    repeat=matrix["repeat"],
                    input_order=matrix["input_order"],
                    repo_relative_path=repo_relative_path,
                    run_relative_path=repo_relative_path.removeprefix(f"{run_root}/"),
                )
                jobs.append(job)
                raw_jobs.append(job)
            query_specs.append(
                {
                    "repository_key": repository_key,
                    "released_payload_path": path,
                    "released_payload_sha256": digest,
                    "case_id": case["id"],
                    "query": case["query"],
                    "case_sha256": _json_value_sha256(case),
                    "query_root": query_root,
                    "raw_control_jobs": tuple(jobs),
                }
            )
    marker_jobs: list[PhaseAArtifactJob] = []
    queries: list[PhaseAQueryPlan] = []
    for query_spec in query_specs:
        repo_relative_path = (
            f"{query_spec['query_root']}/{CONTROL_DIRECTORY}/{CONTROL_MARKER_FILENAME}"
        )
        marker_job = PhaseAArtifactJob(
            kind="freeze_marker",
            global_index=len(raw_jobs) + len(marker_jobs),
            repository_key=query_spec["repository_key"],
            case_id=query_spec["case_id"],
            query=query_spec["query"],
            case_sha256=query_spec["case_sha256"],
            released_payload_path=query_spec["released_payload_path"],
            released_payload_sha256=query_spec["released_payload_sha256"],
            source_identity=query_spec["raw_control_jobs"][0].source_identity,
            repeat=None,
            input_order=None,
            repo_relative_path=repo_relative_path,
            run_relative_path=repo_relative_path.removeprefix(f"{run_root}/"),
        )
        marker_jobs.append(marker_job)
        queries.append(
            PhaseAQueryPlan(
                repository_key=query_spec["repository_key"],
                case_id=query_spec["case_id"],
                query=query_spec["query"],
                case_sha256=query_spec["case_sha256"],
                released_payload_path=query_spec["released_payload_path"],
                released_payload_sha256=query_spec["released_payload_sha256"],
                query_root=query_spec["query_root"],
                raw_control_jobs=query_spec["raw_control_jobs"],
                freeze_marker_job=marker_job,
            )
        )
    _require(
        len(queries) == engine["query_count"]
        and len(raw_jobs) == engine["raw_capture_count"]
        and len(marker_jobs) == engine["freeze_marker_count"],
        "Phase A derived work-list cardinality changed",
    )
    return PhaseAControlPlan(
        status="inert_no_execution_or_writes",
        queries=tuple(queries),
        raw_control_jobs=tuple(raw_jobs),
        freeze_marker_jobs=tuple(marker_jobs),
    )


def _phase_a_job_from_json(value: Any) -> PhaseAArtifactJob:
    _require(type(value) is dict, "Phase A worker job is not an exact object")
    raw = dict(value)
    source = raw.get("source_identity")
    _require(type(source) is dict, "Phase A worker source identity is not exact")
    raw["source_identity"] = PhaseASourceIdentity(**source)
    try:
        return PhaseAArtifactJob(**raw)
    except TypeError as exc:
        raise ValidationError("Phase A worker closed job fields changed") from exc


def _semantic_match_projection(matches: Sequence[Any]) -> list[dict[str, Any]]:
    return [
        {"variant_id": str(match.variant_id), "score": float(match.score)}
        for match in matches
    ]


def _candidate_projection(candidate: Any) -> dict[str, Any]:
    return {
        "chunk_id": str(candidate.chunk_id),
        "score": float(candidate.score),
        "source": str(candidate.source),
        "score_parts": {key: float(value) for key, value in candidate.score_parts.items()},
        "semantic_matches": _semantic_match_projection(candidate.semantic_matches),
    }


def _ranked_projection(ranked: Any) -> dict[str, Any]:
    return {
        "chunk_id": str(ranked.chunk.chunk_id),
        "file_path": ranked.chunk.file_path.as_posix(),
        "start_line": int(ranked.chunk.start_line),
        "end_line": int(ranked.chunk.end_line),
        "score": float(ranked.score),
        "score_parts": {key: float(value) for key, value in ranked.score_parts.items()},
        "reasons": list(ranked.reasons),
        "rank_tier": int(ranked.rank_tier),
        "rerank_score": float(ranked.rerank_score),
        "evidence_class": str(ranked.evidence_class),
        "evidence_priority": int(ranked.evidence_priority),
        "semantic_matches": _semantic_match_projection(ranked.semantic_matches),
        "pre_ceiling_rerank_score": float(ranked.pre_ceiling_rerank_score),
        "was_ceiling_clamped": bool(ranked.was_ceiling_clamped),
    }


def _context_projection(result: Any) -> dict[str, Any]:
    return {
        "origin_chunk_ids": list(result.chunk_ids),
        "file_path": result.file_path.as_posix(),
        "start_line": int(result.start_line),
        "end_line": int(result.end_line),
        "score": float(result.score),
        "score_parts": {key: float(value) for key, value in result.score_parts.items()},
        "reasons": list(result.reasons),
        "rank_tier": int(result.rank_tier),
        "rerank_score": float(result.rerank_score),
        "evidence_class": str(result.evidence_class),
        "evidence_priority": int(result.evidence_priority),
        "semantic_matches": _semantic_match_projection(result.semantic_matches),
        "pre_ceiling_rerank_score": float(result.pre_ceiling_rerank_score),
        "was_ceiling_clamped": bool(result.was_ceiling_clamped),
        "spans": [
            {
                "start_line": int(span.start_line),
                "end_line": int(span.end_line),
                "score": float(span.score),
                "sources": list(span.sources),
            }
            for span in result.spans
        ],
    }


def _phase_a_real_runtime(
    job: PhaseAArtifactJob,
    repository_root: Path,
    staging_fd: int,
    invocation_id: str,
) -> dict[str, Any]:
    """Run the real hash/planner-off index, retrieval, graph, and rank pipeline."""

    _require(job.kind == "raw_control", "real runtime requires one raw-control job")
    released_path = _repo_path_from_root(repository_root, job.released_payload_path)
    released, released_sha256 = _read_immutable_canonical_json(
        released_path,
        "Phase A released payload",
    )
    _require(
        released_sha256 == job.released_payload_sha256
        and released["source"]["repository_key"] == job.repository_key,
        "Phase A released payload identity changed",
    )
    selected_case = next(
        (case for case in released["cases"] if case.get("id") == job.case_id),
        None,
    )
    _require(
        selected_case is not None
        and _json_value_sha256(selected_case) == job.case_sha256
        and selected_case["query"] == job.query,
        "Phase A released case/query changed",
    )
    source_root = _repo_path_from_root(repository_root, job.source_identity.source_root)
    source_contract = released["source"]
    _require(
        source_contract["url"] == job.source_identity.url
        and source_contract["commit"] == job.source_identity.commit
        and source_contract["tree"] == job.source_identity.tree
        and source_contract["inventory_sha256"] == job.source_identity.inventory_sha256
        and source_contract["content_sha256"] == job.source_identity.content_sha256,
        "Phase A source/release identity changed",
    )
    _validate_public_source(source_contract, source_root)
    selected_files = _select_public_source_inventory(
        source_root,
        source_contract["include"],
        source_contract["exclude"],
    )
    materialization_order = (
        tuple(reversed(selected_files))
        if job.input_order == "reverse"
        else tuple(selected_files)
    )
    _require(job.input_order in {"canonical", "reverse"}, "Phase A input order changed")

    config_module = importlib.import_module("context_search_tool.config")
    indexer = importlib.import_module("context_search_tool.indexer")
    retrieval = importlib.import_module("context_search_tool.retrieval")
    v2_oracle = importlib.import_module("p15_python_import_symbol_acceptance")
    candidates_module = importlib.import_module(
        "context_search_tool.retrieval_core.candidates"
    )
    ranking_module = importlib.import_module(
        "context_search_tool.retrieval_core.ranking"
    )
    sqlite_store_module = importlib.import_module("context_search_tool.sqlite_store")
    config = replace(
        config_module.DEFAULT_CONFIG,
        embedding=config_module.EmbeddingConfig(
            provider="hash",
            model="hash-v1",
            dimensions=384,
        ),
        query_planner=replace(
            config_module.DEFAULT_CONFIG.query_planner,
            enabled=False,
        ),
    )
    _require(
        config.embedding.provider == "hash"
        and config.embedding.model == "hash-v1"
        and config.embedding.dimensions == 384
        and config.query_planner.enabled is False,
        "Phase A hash/planner-off configuration changed",
    )

    context_expansion_module = importlib.import_module(
        "context_search_tool.retrieval_core.context_expansion"
    )
    graph_calls: list[dict[str, Any]] = []
    candidate_call_values: list[tuple[list[Any], list[Any]]] = []
    context_call_values: list[tuple[Any, Any, Any]] = []
    context_expansion_values: list[tuple[list[Any], list[Any]]] = []
    prebonus_ranked: list[Any] = []
    original_outgoing = sqlite_store_module.GraphReadSession.outgoing_relations
    original_merge = candidates_module.merge_candidates
    original_cohort = ranking_module.apply_frontend_import_cohort_rerank
    original_context_merge = context_expansion_module._merge_expanded_result
    original_context_expansion = context_expansion_module.expand_ranked_chunks

    def observed_outgoing(session, source_signal_id, *, limit=65):
        relations = original_outgoing(session, source_signal_id, limit=limit)
        source = session.signal_for_id(source_signal_id)
        exact_edges: list[dict[str, Any]] = []
        if source is not None:
            for position, relation in enumerate(relations[:64], start=1):
                target = session.signal_for_id(relation.target_signal_id)
                if (
                    target is not None
                    and relation.kind == "imports"
                    and relation.resolution == "resolved_exact"
                    and relation.producer == "python_ast"
                    and relation.metadata.get("resolution_basis")
                    == "exact_python_imported_symbol"
                ):
                    exact_edges.append(
                        {
                            "relation_id": relation.relation_id,
                            "source_signal_id": source.signal_id,
                            "source_file_path": source.file_path.as_posix(),
                            "source_chunk_id": source.chunk_id,
                            "target_signal_id": target.signal_id,
                            "target_file_path": target.file_path.as_posix(),
                            "target_chunk_id": target.chunk_id,
                            "relation_kind": relation.kind,
                            "resolution": relation.resolution,
                            "producer": relation.producer,
                            "resolution_basis": str(
                                relation.metadata["resolution_basis"]
                            ),
                            "ordered_edge_position": position,
                        }
                    )
        graph_calls.append(
            {
                "call_index": len(graph_calls),
                "source_signal_id": source_signal_id,
                "requested_limit": limit,
                "returned_relation_ids": [
                    relation.relation_id for relation in relations
                ],
                "direct_exact_edges": exact_edges,
            }
        )
        return relations

    def observed_merge(values):
        inputs = list(values)
        outputs = original_merge(inputs)
        candidate_call_values.append((inputs, list(outputs.values())))
        return outputs

    def observed_cohort(repo, ranked_chunks, query):
        ranked = original_cohort(repo, ranked_chunks, query)
        prebonus_ranked[:] = list(ranked)
        return ranked

    def observed_context_merge(left, right):
        output = original_context_merge(left, right)
        context_call_values.append((left, right, output))
        return output

    def observed_context_expansion(
        repo,
        ranked_chunks,
        config,
        context_lines,
        full_file,
        *,
        protect_direct_graph=False,
    ):
        inputs = list(ranked_chunks)
        outputs = original_context_expansion(
            repo,
            inputs,
            config,
            context_lines,
            full_file,
            protect_direct_graph=protect_direct_graph,
        )
        context_expansion_values.append((inputs, list(outputs)))
        return outputs

    _validate_owned_directory(staging_fd, mode=0o700, label="Phase A attempt tree")
    _require(
        re.fullmatch(r"[0-9a-f]{32}", invocation_id) is not None,
        "Phase A runtime nonce changed",
    )
    scratch_name = f".phase-a-job-{job.global_index:02d}-{invocation_id}"
    try:
        os.stat(scratch_name, dir_fd=staging_fd, follow_symlinks=False)
    except FileNotFoundError:
        pass
    else:
        raise ValidationError("Phase A exact job scratch already exists")
    os.mkdir(scratch_name, 0o700, dir_fd=staging_fd)
    scratch_fd = os.open(scratch_name, _DIRECTORY_OPEN_FLAGS, dir_fd=staging_fd)
    scratch_identity = _fd_identity(scratch_fd)
    scratch = _directory_path_from_fd(scratch_fd)
    _assert_absolute_directory_identity(
        scratch,
        scratch_identity,
        "Phase A exact job scratch",
    )
    workspace = scratch / "repository"
    isolated_config = scratch / "global-config.toml"
    overlay_exact_relation_count = 0
    prior_global_config = os.environ.get("CST_GLOBAL_CONFIG_PATH")
    os.environ["CST_GLOBAL_CONFIG_PATH"] = os.fspath(isolated_config)
    sqlite_store_module.GraphReadSession.outgoing_relations = observed_outgoing
    candidates_module.merge_candidates = observed_merge
    ranking_module.apply_frontend_import_cohort_rerank = observed_cohort
    context_expansion_module._merge_expanded_result = observed_context_merge
    context_expansion_module.expand_ranked_chunks = observed_context_expansion
    try:
        for relative in materialization_order:
            target = workspace / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_root / relative, target)
        _assert_absolute_directory_identity(
            scratch,
            scratch_identity,
            "Phase A exact job scratch",
        )
        indexer.index_repository(workspace, config)
        overlay = v2_oracle._overlay_oracle(workspace)
        overlay_exact_relation_count = int(overlay["exact_relation_count"])
        _require(
            overlay_exact_relation_count > 0,
            "Phase A exact-provenance overlay produced no exact relations",
        )
        bundle = retrieval.query_repository(workspace, job.query, config)
        _require(bundle.planner.status == "disabled", "Phase A planner was not disabled")
        _require(prebonus_ranked, "Phase A real retrieval produced no ranked roster")
        _require(
            len(context_expansion_values) == 1,
            "Phase A context expansion boundary was not observed exactly once",
        )
        _assert_absolute_directory_identity(
            scratch,
            scratch_identity,
            "Phase A exact job scratch",
        )
    finally:
        sqlite_store_module.GraphReadSession.outgoing_relations = original_outgoing
        candidates_module.merge_candidates = original_merge
        ranking_module.apply_frontend_import_cohort_rerank = original_cohort
        context_expansion_module._merge_expanded_result = original_context_merge
        context_expansion_module.expand_ranked_chunks = original_context_expansion
        if prior_global_config is None:
            os.environ.pop("CST_GLOBAL_CONFIG_PATH", None)
        else:
            os.environ["CST_GLOBAL_CONFIG_PATH"] = prior_global_config
        try:
            _require(
                _fd_identity(scratch_fd) == scratch_identity,
                "Phase A exact job scratch inode changed",
            )
            _remove_phase_a_tree_at(staging_fd, scratch_name)
        finally:
            os.close(scratch_fd)
        _require(
            scratch_name not in os.listdir(staging_fd),
            "Phase A exact job scratch survived producer exit",
        )

    inventory: list[dict[str, Any]] = []
    seen_relation_ids: set[str] = set()
    for call in graph_calls:
        for atom in call["direct_exact_edges"]:
            if atom["relation_id"] not in seen_relation_ids:
                seen_relation_ids.add(atom["relation_id"])
                inventory.append(dict(atom))

    def candidate_envelope(candidate: Any) -> dict[str, Any]:
        projection = _candidate_projection(candidate)
        return {
            "candidate": projection,
            "provenance_union": _atoms_for_origins(
                inventory,
                [projection["chunk_id"]],
            ),
        }

    candidate_calls: list[dict[str, Any]] = []
    same_chunk_count = 0
    for call_index, (inputs, outputs) in enumerate(candidate_call_values):
        input_envelopes = [candidate_envelope(value) for value in inputs]
        output_envelopes = [candidate_envelope(value) for value in outputs]
        output_by_id = {
            value["candidate"]["chunk_id"]: value for value in output_envelopes
        }
        input_ids = [value["candidate"]["chunk_id"] for value in input_envelopes]
        groups = []
        for chunk_id in dict.fromkeys(input_ids):
            indexes = [index for index, value in enumerate(input_ids) if value == chunk_id]
            if len(indexes) <= 1:
                continue
            union = _atoms_for_origins(inventory, [chunk_id])
            groups.append(
                {
                    "chunk_id": chunk_id,
                    "input_indexes": indexes,
                    "inputs": [input_envelopes[index] for index in indexes],
                    "output": output_by_id[chunk_id],
                    "provenance_union": union,
                }
            )
        same_chunk_count += len(groups)
        candidate_calls.append(
            {
                "call_index": call_index,
                "inputs": input_envelopes,
                "outputs": output_envelopes,
                "same_chunk_groups": groups,
            }
        )

    def context_envelope(value: Any) -> dict[str, Any]:
        projection = _context_projection(value)
        return {
            "context": projection,
            "provenance_union": _atoms_for_origins(
                inventory,
                projection["origin_chunk_ids"],
            ),
        }

    context_overlap_calls = [
        {
            "call_index": call_index,
            "left": context_envelope(left),
            "right": context_envelope(right),
            "output": context_envelope(output),
        }
        for call_index, (left, right, output) in enumerate(context_call_values)
    ]
    context_expansion_calls = []
    for call_index, (inputs, outputs) in enumerate(context_expansion_values):
        context_expansion_calls.append(
            {
                "call_index": call_index,
                "inputs": [
                    {
                        "ranked": _ranked_projection(value),
                        "provenance_union": _atoms_for_origins(
                            inventory,
                            [value.chunk.chunk_id],
                        ),
                    }
                    for value in inputs
                ],
                "outputs": [context_envelope(value) for value in outputs],
            }
        )

    candidate_routes: dict[str, list[dict[str, Any]]] = {}
    same_chunk_routes: dict[str, list[dict[str, Any]]] = {}
    for call in candidate_calls:
        for output in call["outputs"]:
            chunk_id = output["candidate"]["chunk_id"]
            candidate_routes[chunk_id] = _provenance_union(
                [*candidate_routes.get(chunk_id, []), *output["provenance_union"]]
            )
        for group in call["same_chunk_groups"]:
            chunk_id = group["chunk_id"]
            same_chunk_routes[chunk_id] = _provenance_union(
                [*same_chunk_routes.get(chunk_id, []), *group["provenance_union"]]
            )
    context_routes: dict[str, list[dict[str, Any]]] = {}
    for call in context_overlap_calls:
        for chunk_id in call["output"]["context"]["origin_chunk_ids"]:
            context_routes[chunk_id] = _provenance_union(
                [
                    *context_routes.get(chunk_id, []),
                    *call["output"]["provenance_union"],
                ]
            )
    origins_by_chunk: dict[str, list[str]] = {}
    for output in context_expansion_calls[0]["outputs"]:
        origins = output["context"]["origin_chunk_ids"]
        for chunk_id in origins:
            _require(
                chunk_id not in origins_by_chunk,
                "Phase A context origin appeared in multiple outputs",
            )
            origins_by_chunk[chunk_id] = list(origins)

    rows: list[dict[str, Any]] = []
    for position, item in enumerate(prebonus_ranked, start=1):
        chunk_id = item.chunk.chunk_id
        _require(chunk_id in origins_by_chunk, "Phase A ranked origin was omitted by context expansion")
        routes = {
            "candidate": candidate_routes.get(chunk_id, []),
            "same_chunk": same_chunk_routes.get(chunk_id, []),
            "context_overlap": context_routes.get(chunk_id, []),
        }
        provenance_union = _provenance_union(
            atom for route in MERGE_ROUTES for atom in routes[route]
        )
        rows.append(
            {
                "candidate_id": chunk_id,
                "chunk_id": chunk_id,
                "file_path": item.chunk.file_path.as_posix(),
                "origin_chunk_ids": origins_by_chunk[chunk_id],
                "merge_inputs": routes,
                "provenance_union": provenance_union,
                "rerank_score": float(item.rerank_score),
                "evidence_priority": int(item.evidence_priority),
                "was_ceiling_clamped": bool(item.was_ceiling_clamped),
                "pre_ceiling_rerank_score": float(item.pre_ceiling_rerank_score),
                "role_priority": float(item.score_parts.get("role_priority", 99.0)),
                "combined_score": float(item.score),
                "start_line": int(item.chunk.start_line),
                "prebonus_position": position,
                "score_parts": {
                    key: float(value) for key, value in item.score_parts.items()
                },
                "reasons": list(item.reasons),
                "stage": BONUS_STAGE,
            }
        )
    candidate_ids = [row["candidate_id"] for row in rows]
    pipeline_boundaries = {
        "overlay_exact_relation_count": overlay_exact_relation_count,
        "graph_outgoing_call_count": len(graph_calls),
        "graph_outgoing_calls": graph_calls,
        "candidate_merge_call_count": len(candidate_calls),
        "candidate_merge_calls": candidate_calls,
        "same_chunk_merge_count": same_chunk_count,
        "context_expansion_call_count": len(context_expansion_calls),
        "context_expansion_calls": context_expansion_calls,
        "context_overlap_merge_call_count": len(context_overlap_calls),
        "context_overlap_merge_calls": context_overlap_calls,
    }
    runtime = {
        "stage": BONUS_STAGE,
        "prebonus_input_candidate_ids": candidate_ids,
        "prebonus_input_sha256": _json_value_sha256(candidate_ids),
        "ordered_edge_inventory": inventory,
        "ordered_edge_inventory_sha256": _json_value_sha256(inventory),
        "pipeline_boundaries": pipeline_boundaries,
        "roster": rows,
    }
    derived = validate_raw_control_runtime(runtime)
    inventory_witnesses = {
        (
            atom["source_signal_id"],
            atom["target_signal_id"],
            atom["target_chunk_id"],
            atom["target_file_path"],
        )
        for atom in inventory
    }
    expected_witnesses = {
        (
            witness["module_relation"]["source_signal_id"],
            witness["target_signal_id"],
            witness["target_chunk_id"],
            witness["target_path"],
        )
        for witness in selected_case["exact_import_witnesses"]
    }
    _require(
        expected_witnesses <= inventory_witnesses,
        "Phase A actual graph input omitted a released exact witness",
    )
    rows_by_id = {row["candidate_id"]: row for row in rows}
    eligible_paths = {
        rows_by_id[candidate_id]["file_path"]
        for candidate_id in derived["eligible_candidate_ids"]
    }
    _require(
        set(selected_case["eligible_missing_required_paths"]) <= eligible_paths,
        "Phase A released eligible missing target did not close in the real roster",
    )
    return runtime


def _repo_path_from_root(root: Path, relative: str) -> Path:
    pure = PurePosixPath(relative)
    _require(
        not pure.is_absolute()
        and pure.parts
        and all(part not in {"", ".", ".."} for part in pure.parts),
        "Phase A repository path escaped its root",
    )
    return root.joinpath(*pure.parts)


def _phase_a_worker_main(
    repository_root: Path,
    repository_fd: int,
    staging_fd: int,
) -> int:
    """Produce one real raw control or freeze marker in an isolated child."""

    try:
        root = repository_root.resolve()
        opened_repository_fd = _open_absolute_directory_chain(root)
        try:
            _require(
                _fd_identity(opened_repository_fd) == _fd_identity(repository_fd),
                "Phase A worker repository path/descriptor identity changed",
            )
        finally:
            os.close(opened_repository_fd)
        _validate_owned_directory(staging_fd, mode=0o700, label="Phase A attempt tree")
        request = json.loads(sys.stdin.buffer.readline().decode("utf-8"))
        _require(
            type(request) is dict and set(request) == {"job", "invocation_id"},
            "Phase A worker request must contain only the closed job and nonce",
        )
        invocation_id = request["invocation_id"]
        _require(
            isinstance(invocation_id, str)
            and re.fullmatch(r"[0-9a-f]{32}", invocation_id) is not None,
            "Phase A worker nonce changed",
        )
        supplied_job = request["job"]
        job = _phase_a_job_from_json(supplied_job)
        if job.kind == "raw_control":
            payload: dict[str, Any] = {
                "schema_version": 1,
                "program": "p15-v3",
                "attempt_id": "p15-v3-attempt-001",
                "phase": "task0a_raw_control",
                "query_id": job.case_id,
                "case_id": job.case_id,
                "case_sha256": job.case_sha256,
                "query": job.query,
                "query_sha256": _json_value_sha256(job.query),
                "released_payload": {
                    "repository_key": job.repository_key,
                    "path": job.released_payload_path,
                    "sha256": job.released_payload_sha256,
                },
                "source_identity": asdict(job.source_identity),
                "repeat": job.repeat,
                "input_order": job.input_order,
                "policy_contribution": 0.0,
                "producer": "p15_v3_independent_raw_control_capture",
                "process_identity": {"pid": os.getpid(), "invocation_id": invocation_id},
                "privacy": deepcopy(CONTROL_PRIVACY),
                "serialization": "canonical_json_sort_keys_compact_utf8_no_trailing_newline",
                "write_policy": "write_new_only_never_overwrite",
                "runtime_visibility": _phase_a_real_runtime(
                    job,
                    root,
                    staging_fd,
                    invocation_id,
                ),
            }
            validate_raw_control_capture(payload)
        elif job.kind == "freeze_marker":
            controls: dict[str, Mapping[str, Any]] = {}
            parent = PurePosixPath(job.run_relative_path).parent
            for filename in CONTROL_FILENAMES:
                relative = (parent / filename).as_posix()
                control, _digest = _read_phase_a_child_file(
                    staging_fd,
                    relative,
                    "Phase A staged raw control",
                )
                _require(
                    control["query_id"] == job.case_id
                    and control["query"] == job.query
                    and control["case_sha256"] == job.case_sha256
                    and control["released_payload"]["path"] == job.released_payload_path
                    and control["released_payload"]["sha256"] == job.released_payload_sha256
                    and control["source_identity"] == asdict(job.source_identity),
                    "Phase A freezer read a relabeled raw control",
                )
                controls[filename] = control
            snapshots = [
                {
                    "path": filename,
                    "canonical_sha256": _json_value_sha256(control),
                    "stable_projection_sha256": _json_value_sha256(control["runtime_visibility"]),
                    "repeat": control["repeat"],
                    "input_order": control["input_order"],
                    "pid": control["process_identity"]["pid"],
                    "invocation_id": control["process_identity"]["invocation_id"],
                }
                for filename, control in controls.items()
            ]
            payload = {
                "schema_version": 1,
                "program": "p15-v3",
                "attempt_id": "p15-v3-attempt-001",
                "phase": "task0a_control_freeze",
                "status": "immutable_control_frozen",
                "immutable": True,
                "required_mode": "0444",
                "query_id": job.case_id,
                "policy_contribution": 0.0,
                "producer": "p15_v3_independent_control_freezer",
                "process_identity": {"pid": os.getpid(), "invocation_id": invocation_id},
                "privacy": deepcopy(CONTROL_PRIVACY),
                "serialization": "canonical_json_sort_keys_compact_utf8_no_trailing_newline",
                "write_policy": "write_new_only_never_overwrite",
                "required_matrix": [
                    {"repeat": repeat, "input_order": order}
                    for repeat, order in (
                        (1, "canonical"),
                        (1, "reverse"),
                        (2, "canonical"),
                        (2, "reverse"),
                    )
                ],
                "snapshots": snapshots,
                "common_stable_projection_sha256": snapshots[0]["stable_projection_sha256"],
            }
            validate_control_freeze_marker(payload, controls)
        else:
            raise ValidationError("Phase A worker job kind changed")
        envelope = {
            "job_sha256": _json_value_sha256(supplied_job),
            "producer_executed": True,
            "payload": payload,
        }
        sys.stdout.buffer.write(_canonical_json_bytes(envelope) + b"\n")
        sys.stdout.buffer.flush()
        release = json.loads(sys.stdin.buffer.readline().decode("utf-8"))
        _require(release == {"command": "release"}, "Phase A worker release changed")
        return 0
    except (
        ValidationError,
        KeyError,
        TypeError,
        ValueError,
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        subprocess.CalledProcessError,
    ) as exc:
        print(f"P15_V3_PHASE_A_WORKER_ERROR: {exc}", file=sys.stderr)
        return 2


def _validate_owned_directory(descriptor: int, *, mode: int, label: str) -> None:
    metadata = os.fstat(descriptor)
    _require(stat.S_ISDIR(metadata.st_mode), f"{label} is not a real directory")
    _require(stat.S_IMODE(metadata.st_mode) == mode, f"{label} mode changed")
    _require(metadata.st_uid == os.geteuid(), f"{label} owner changed")


def _atomic_rename_directory_noreplace(
    source_parent_fd: int,
    source_name: str,
    target_parent_fd: int,
    target_name: str,
) -> None:
    """Atomically publish one directory and fail if the target exists."""

    libc = ctypes.CDLL(None, use_errno=True)
    source = os.fsencode(source_name)
    target = os.fsencode(target_name)
    if hasattr(libc, "renameatx_np"):
        operation = libc.renameatx_np
        operation.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        result = operation(source_parent_fd, source, target_parent_fd, target, 0x00000004)
    elif hasattr(libc, "renameat2"):
        operation = libc.renameat2
        operation.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        result = operation(source_parent_fd, source, target_parent_fd, target, 0x00000001)
    else:
        raise ValidationError("atomic no-overwrite directory publication is unavailable")
    if result != 0:
        error = ctypes.get_errno()
        if error in {errno.EEXIST, errno.ENOTEMPTY}:
            raise FileExistsError(error, os.strerror(error), target_name)
        raise OSError(error, os.strerror(error), target_name)


def _phase_a_worker_subprocess_spec(
    repository_root: Path,
    repository_fd: int,
    staging_fd: int,
) -> tuple[list[str], dict[str, str]]:
    harness_path = Path(__file__).resolve()
    workspace_root = harness_path.parents[1].resolve()
    python_paths = tuple(
        (workspace_root / relative).resolve()
        for relative in (".", "tests", "src")
    )
    _require(
        harness_path.is_absolute()
        and all(path.is_absolute() for path in python_paths),
        "Phase A worker command or import path is not absolute",
    )
    environment = dict(os.environ)
    environment["PYTHONPATH"] = os.pathsep.join(
        os.fspath(path) for path in python_paths
    )
    return (
        [
            sys.executable,
            os.fspath(harness_path),
            "_phase-a-worker",
            os.fspath(repository_root.resolve()),
            str(repository_fd),
            str(staging_fd),
        ],
        environment,
    )


def run_phase_a_control_engine(
    manifest_path: Path,
    *,
    run_root: Path,
    staging_root: Path,
) -> Mapping[str, Any]:
    """The sole Phase A production entry; all write authority stays in this call."""

    @dataclass(frozen=True, slots=True)
    class _Capability:
        manifest_path: Path
        manifest_sha256: str
        harness_sha256: str
        repository_root: Path
        repository_fd: int
        repository_identity: tuple[int, int]
        plan: PhaseAControlPlan
        run_root: Path
        run_parent_fd: int
        run_parent_identity: tuple[int, int]
        run_name: str
        run_fd: int
        run_identity: tuple[int, int]
        namespace_path: Path
        namespace_parent_fd: int
        namespace_parent_identity: tuple[int, int]
        namespace_name: str
        namespace_fd: int
        namespace_identity: tuple[int, int]
        namespace_created: bool
        staging_root: Path
        staging_name: str
        staging_fd: int
        staging_identity: tuple[int, int]

    def _named_identity(parent_fd: int, name: str) -> tuple[int, int]:
        metadata = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        _require(stat.S_ISDIR(metadata.st_mode), "trusted fd path named entry is not a directory")
        return metadata.st_dev, metadata.st_ino

    def _remove_at(parent_fd: int, name: str) -> None:
        metadata = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        if stat.S_ISDIR(metadata.st_mode):
            child_fd = os.open(name, _DIRECTORY_OPEN_FLAGS, dir_fd=parent_fd)
            try:
                os.fchmod(child_fd, 0o700)
                for child_name in os.listdir(child_fd):
                    _remove_at(child_fd, child_name)
            finally:
                os.close(child_fd)
            os.rmdir(name, dir_fd=parent_fd)
        else:
            os.unlink(name, dir_fd=parent_fd)

    capability: _Capability | None = None
    published = False
    publication_attempted = False
    published_tree_identity: tuple[int, int] | None = None

    def _entry_names_for_identity(
        parent_fd: int,
        expected: tuple[int, int],
    ) -> list[str]:
        matches = []
        for name in os.listdir(parent_fd):
            metadata = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
            if (metadata.st_dev, metadata.st_ino) == expected:
                matches.append(name)
        return matches

    def _cleanup(*, reject_mutation: bool) -> None:
        nonlocal capability, published
        if capability is None:
            return
        cap = capability
        capability = None
        mutation = False
        terminal_lost_published_inode = False
        target_identity = published_tree_identity or cap.staging_identity
        try:
            if _fd_identity(cap.staging_fd) != cap.staging_identity:
                mutation = True
            os.fchmod(cap.staging_fd, 0o700)
            for name in os.listdir(cap.staging_fd):
                mutation = True
                _remove_at(cap.staging_fd, name)

            if _fd_identity(cap.namespace_fd) != cap.namespace_identity:
                mutation = True
            os.fchmod(cap.namespace_fd, 0o700)
            run_matches = _entry_names_for_identity(
                cap.run_parent_fd,
                target_identity,
            )
            namespace_matches = _entry_names_for_identity(
                cap.namespace_fd,
                target_identity,
            )
            if publication_attempted and not run_matches and not namespace_matches:
                terminal_lost_published_inode = True
            if len(run_matches) > 1 or len(namespace_matches) > 1:
                mutation = True

            try:
                run_metadata = os.stat(
                    cap.run_name,
                    dir_fd=cap.run_parent_fd,
                    follow_symlinks=False,
                )
            except FileNotFoundError:
                pass
            else:
                if (run_metadata.st_dev, run_metadata.st_ino) != target_identity:
                    mutation = True
                _remove_at(cap.run_parent_fd, cap.run_name)
            for name in run_matches:
                if name == cap.run_name:
                    continue
                mutation = True
                _remove_at(cap.run_parent_fd, name)
            os.fsync(cap.run_parent_fd)

            for name in os.listdir(cap.namespace_fd):
                if name != cap.staging_name:
                    mutation = True
                _remove_at(cap.namespace_fd, name)
            os.fsync(cap.namespace_fd)
            published = False

            try:
                os.stat(
                    cap.run_name,
                    dir_fd=cap.run_parent_fd,
                    follow_symlinks=False,
                )
            except FileNotFoundError:
                pass
            else:
                raise ValidationError("Phase A rollback left the final run name present")
            _require(
                not _entry_names_for_identity(cap.run_parent_fd, target_identity)
                and not _entry_names_for_identity(cap.namespace_fd, target_identity),
                "Phase A rollback left the published tree inode in an authorized parent",
            )

            if cap.namespace_created:
                parent_names = os.listdir(cap.namespace_parent_fd)
                matching_namespace_names = []
                for name in parent_names:
                    try:
                        if _named_identity(cap.namespace_parent_fd, name) == cap.namespace_identity:
                            matching_namespace_names.append(name)
                    except ValidationError:
                        continue
                if matching_namespace_names != [cap.namespace_name]:
                    mutation = True
                for name in set(matching_namespace_names) | {cap.namespace_name}:
                    try:
                        _remove_at(cap.namespace_parent_fd, name)
                    except FileNotFoundError:
                        pass
                os.fsync(cap.namespace_parent_fd)
            else:
                try:
                    if _named_identity(cap.namespace_parent_fd, cap.namespace_name) != cap.namespace_identity:
                        mutation = True
                except (FileNotFoundError, ValidationError):
                    mutation = True
        finally:
            for descriptor in (
                cap.staging_fd,
                cap.namespace_fd,
                cap.run_fd,
                cap.run_parent_fd,
                cap.namespace_parent_fd,
                cap.repository_fd,
            ):
                try:
                    os.close(descriptor)
                except OSError:
                    pass
        if terminal_lost_published_inode:
            raise ValidationError(
                "Phase A published tree inode left its authorized parent; terminal non-retriable rollback"
            )
        if reject_mutation:
            _require(not mutation, "Phase A staging mutation was detected and cleaned")

    def _authorize() -> _Capability:
        nonlocal capability
        exact_manifest_path = Path(os.path.abspath(os.fspath(manifest_path)))
        _require(
            exact_manifest_path == Path(os.path.abspath(os.fspath(MANIFEST_PATH))),
            "only the frozen v3 manifest is accepted",
        )
        manifest_digest = _sha256(exact_manifest_path)
        _require(manifest_digest == MANIFEST_SHA256, "v3 manifest digest mismatch")
        manifest = _read_json(exact_manifest_path)
        _validate_phase_a_engine_contract(manifest, require_inert=False)
        _require(
            manifest["phase_a_control_engine"]["execution_authorized"] is True
            and manifest["phase_a_control_engine"]["capture_authorized"] is True,
            "Phase A execution has not been independently authorized",
        )
        repository_root = Path(os.path.abspath(os.fspath(ROOT)))
        expected_run_root = Path(
            os.path.abspath(os.fspath(repository_root / manifest["evidence"]["run_root"]))
        )
        actual_run_root = Path(os.path.abspath(os.fspath(run_root)))
        _require(actual_run_root == expected_run_root, "Phase A run root differs from the exact manifest path")
        contract = manifest["phase_a_control_engine"]["trusted_staging"]
        namespace_path = Path(os.path.abspath(os.fspath(repository_root / contract["namespace"])))
        actual_staging = Path(os.path.abspath(os.fspath(staging_root)))
        _require(
            actual_staging.parent == namespace_path
            and re.fullmatch(contract["leaf_pattern"], actual_staging.name) is not None,
            "Phase A staging path is outside the exact trusted namespace or pattern",
        )
        plan = build_phase_a_control_plan(manifest, require_inert=False)

        repository_fd = _open_absolute_directory_chain(repository_root)
        run_parent_fd = _open_absolute_directory_chain(actual_run_root.parent)
        namespace_parent_fd = _open_absolute_directory_chain(namespace_path.parent)
        namespace_fd = -1
        staging_fd = -1
        run_fd = -1
        namespace_created = False
        try:
            try:
                os.stat(actual_run_root.name, dir_fd=run_parent_fd, follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                raise ValidationError("Phase A run root zero-state is not absent")
            try:
                namespace_fd = os.open(namespace_path.name, _DIRECTORY_OPEN_FLAGS, dir_fd=namespace_parent_fd)
            except FileNotFoundError:
                os.mkdir(namespace_path.name, 0o700, dir_fd=namespace_parent_fd)
                namespace_created = True
                namespace_fd = os.open(namespace_path.name, _DIRECTORY_OPEN_FLAGS, dir_fd=namespace_parent_fd)
            _validate_owned_directory(namespace_fd, mode=0o700, label="Phase A staging namespace")
            _require(not os.listdir(namespace_fd), "Phase A staging namespace is not empty before run")
            os.mkdir(actual_staging.name, 0o700, dir_fd=namespace_fd)
            staging_fd = os.open(actual_staging.name, _DIRECTORY_OPEN_FLAGS, dir_fd=namespace_fd)
            _validate_owned_directory(staging_fd, mode=0o700, label="Phase A staging leaf")
            os.fsync(namespace_fd)
            run_fd = os.dup(staging_fd)
            capability = _Capability(
                manifest_path=exact_manifest_path,
                manifest_sha256=manifest_digest,
                harness_sha256=_sha256(Path(__file__).resolve()),
                repository_root=repository_root,
                repository_fd=repository_fd,
                repository_identity=_fd_identity(repository_fd),
                plan=plan,
                run_root=actual_run_root,
                run_parent_fd=run_parent_fd,
                run_parent_identity=_fd_identity(run_parent_fd),
                run_name=actual_run_root.name,
                run_fd=run_fd,
                run_identity=_fd_identity(run_fd),
                namespace_path=namespace_path,
                namespace_parent_fd=namespace_parent_fd,
                namespace_parent_identity=_fd_identity(namespace_parent_fd),
                namespace_name=namespace_path.name,
                namespace_fd=namespace_fd,
                namespace_identity=_fd_identity(namespace_fd),
                namespace_created=namespace_created,
                staging_root=actual_staging,
                staging_name=actual_staging.name,
                staging_fd=staging_fd,
                staging_identity=_fd_identity(staging_fd),
            )
            return capability
        except Exception:
            for descriptor in (run_fd, staging_fd):
                if descriptor >= 0:
                    os.close(descriptor)
            if namespace_fd >= 0:
                try:
                    for name in os.listdir(namespace_fd):
                        _remove_at(namespace_fd, name)
                finally:
                    os.close(namespace_fd)
            if namespace_created:
                try:
                    os.rmdir(namespace_path.name, dir_fd=namespace_parent_fd)
                except OSError:
                    pass
            for descriptor in (run_parent_fd, namespace_parent_fd, repository_fd):
                os.close(descriptor)
            raise

    observed_workers: dict[int, tuple[int, str]] = {}
    observed_pids: set[int] = set()
    observed_invocations: set[str] = set()

    class _Writer:
        def __init__(self, cap: _Capability) -> None:
            self.cap = cap
            self.next_index = 0
            self.controls: dict[str, dict[str, Mapping[str, Any]]] = {}
            self.published: set[str] = set()

        def _validate_trust(self, *, allowed_staging: set[str] | None = None) -> None:
            cap = self.cap
            _require(_sha256(cap.manifest_path) == cap.manifest_sha256 == MANIFEST_SHA256, "Phase A manifest changed during run")
            _require(
                _sha256(Path(__file__).resolve()) == cap.harness_sha256,
                "Phase A harness changed during run",
            )
            manifest = _read_json(cap.manifest_path)
            _validate_phase_a_engine_contract(manifest, require_inert=False)
            contract = manifest["phase_a_control_engine"]["trusted_staging"]
            _require(
                manifest["phase_a_control_engine"]["execution_authorized"] is True
                and manifest["phase_a_control_engine"]["capture_authorized"] is True
                and Path(os.path.abspath(os.fspath(cap.repository_root / contract["namespace"]))) == cap.namespace_path
                and re.fullmatch(contract["leaf_pattern"], cap.staging_name) is not None,
                "Phase A authorization or staging contract changed during publish",
            )
            for descriptor, identity, mode, label in (
                (cap.run_fd, cap.run_identity, 0o700, "Phase A run root"),
                (cap.staging_fd, cap.staging_identity, 0o700, "Phase A staging leaf"),
                (cap.namespace_fd, cap.namespace_identity, 0o700, "Phase A staging namespace"),
            ):
                _require(_fd_identity(descriptor) == identity, f"{label} inode changed")
                _validate_owned_directory(descriptor, mode=mode, label=label)
            _require(
                _fd_identity(cap.repository_fd) == cap.repository_identity
                and _fd_identity(cap.run_parent_fd) == cap.run_parent_identity
                and _fd_identity(cap.namespace_parent_fd) == cap.namespace_parent_identity
                and _named_identity(cap.namespace_parent_fd, cap.namespace_name) == cap.namespace_identity
                and _named_identity(cap.namespace_fd, cap.staging_name) == cap.staging_identity,
                "Phase A trusted fd path binding changed",
            )
            _assert_absolute_directory_identity(
                cap.repository_root,
                cap.repository_identity,
                "Phase A repository trusted fd path",
            )
            _assert_absolute_directory_identity(
                cap.run_root.parent,
                cap.run_parent_identity,
                "Phase A run parent trusted fd path",
            )
            _assert_absolute_directory_identity(
                cap.namespace_path.parent,
                cap.namespace_parent_identity,
                "Phase A namespace parent trusted fd path",
            )
            try:
                os.stat(cap.run_name, dir_fd=cap.run_parent_fd, follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                raise ValidationError("Phase A final run root appeared before atomic publish")
            _require(
                os.listdir(cap.namespace_fd) == [cap.staging_name],
                "Phase A staging namespace inventory changed",
            )

        def _parent(self, relative_path: str) -> tuple[int, str]:
            pure = PurePosixPath(relative_path)
            _require(not pure.is_absolute() and all(part not in {"", ".", ".."} for part in pure.parts), "Phase A path escaped run root")
            descriptor = os.dup(self.cap.run_fd)
            try:
                for component in pure.parts[:-1]:
                    try:
                        child = os.open(component, _DIRECTORY_OPEN_FLAGS, dir_fd=descriptor)
                    except FileNotFoundError:
                        os.mkdir(component, 0o700, dir_fd=descriptor)
                        os.fsync(descriptor)
                        child = os.open(component, _DIRECTORY_OPEN_FLAGS, dir_fd=descriptor)
                    _validate_owned_directory(
                        child,
                        mode=0o700,
                        label="Phase A target parent",
                    )
                    os.close(descriptor)
                    descriptor = child
                return descriptor, pure.name
            except Exception:
                os.close(descriptor)
                raise

        def publish(self, job: PhaseAArtifactJob, payload: Mapping[str, Any]) -> None:
            self._validate_trust()
            _require(
                self.next_index < len(self.cap.plan.global_artifact_order)
                and job == self.cap.plan.global_artifact_order[self.next_index],
                "Phase A global artifact order or job changed",
            )
            _require(type(payload) is dict, "Phase A child payload is not an exact object")
            if job.kind == "raw_control":
                _require(
                    payload.get("query_id") == job.case_id
                    and payload.get("case_id") == job.case_id
                    and payload.get("case_sha256") == job.case_sha256
                    and payload.get("query") == job.query
                    and payload.get("query_sha256") == _json_value_sha256(job.query)
                    and payload.get("released_payload") == {
                        "repository_key": job.repository_key,
                        "path": job.released_payload_path,
                        "sha256": job.released_payload_sha256,
                    }
                    and payload.get("source_identity") == asdict(job.source_identity),
                    "raw control job/query/case/release/source changed",
                )
                validate_raw_control_capture(payload)
            else:
                controls = self.controls.get(job.case_id, {})
                _require(set(controls) == set(CONTROL_FILENAMES), "freeze marker controls are incomplete")
                validate_control_freeze_marker(payload, controls)
            identity = payload["process_identity"]
            _require(
                observed_workers.get(job.global_index) == (identity["pid"], identity["invocation_id"]),
                "Phase A child identity does not match parent-observed worker",
            )
            parent_fd, filename = self._parent(job.run_relative_path)
            stage_name = f".phase-a-stage-{secrets.token_hex(16)}"
            stage_fd = -1
            linked = False
            raw = _canonical_json_bytes(payload)
            try:
                stage_fd = os.open(
                    stage_name,
                    os.O_RDWR | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0),
                    0o600,
                    dir_fd=self.cap.staging_fd,
                )
                _write_all_fd(stage_fd, raw)
                os.fsync(stage_fd)
                _require(_read_all_fd(stage_fd) == raw, "Phase A staging readback changed")
                os.fchmod(stage_fd, 0o444)
                os.fsync(stage_fd)
                self._validate_trust(allowed_staging={stage_name})
                os.link(stage_name, filename, src_dir_fd=self.cap.staging_fd, dst_dir_fd=parent_fd, follow_symlinks=False)
                linked = True
                os.unlink(stage_name, dir_fd=self.cap.staging_fd)
                os.fsync(self.cap.staging_fd)
                os.fsync(parent_fd)
                final_fd = os.open(filename, _FILE_READ_FLAGS, dir_fd=parent_fd)
                try:
                    metadata = os.fstat(final_fd)
                    _require(
                        stat.S_ISREG(metadata.st_mode)
                        and stat.S_IMODE(metadata.st_mode) == 0o444
                        and metadata.st_nlink == 1
                        and metadata.st_uid == os.geteuid()
                        and _read_all_fd(final_fd) == raw,
                        "published Phase A artifact changed",
                    )
                finally:
                    os.close(final_fd)
            except Exception as exc:
                if linked:
                    try:
                        os.unlink(filename, dir_fd=parent_fd)
                    except OSError:
                        pass
                try:
                    os.unlink(stage_name, dir_fd=self.cap.staging_fd)
                except OSError:
                    pass
                if isinstance(exc, ValidationError):
                    raise
                raise ValidationError("Phase A failure-atomic publish failed") from exc
            finally:
                if stage_fd >= 0:
                    os.close(stage_fd)
                os.close(parent_fd)
            if job.kind == "raw_control":
                self.controls.setdefault(job.case_id, {})[PurePosixPath(job.run_relative_path).name] = payload
            self.published.add(job.run_relative_path)
            self.next_index += 1

        def finish(self) -> Mapping[str, Any]:
            nonlocal publication_attempted, published, published_tree_identity
            self._validate_trust()
            _require(self.next_index == 40 and len(self.published) == 40, "Phase A exact artifact sequence is incomplete")
            _require(len(observed_pids) == len(observed_invocations) == 40, "Phase A worker identity closure changed")
            files: set[str] = set()
            directories: set[str] = set()

            def visit(descriptor: int, prefix: PurePosixPath) -> None:
                for name in os.listdir(descriptor):
                    metadata = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
                    relative = prefix / name
                    if stat.S_ISDIR(metadata.st_mode):
                        _require(
                            stat.S_IMODE(metadata.st_mode) == 0o700
                            and metadata.st_uid == os.geteuid(),
                            "Phase A run directory stat changed",
                        )
                        directories.add(relative.as_posix())
                        child = os.open(name, _DIRECTORY_OPEN_FLAGS, dir_fd=descriptor)
                        try:
                            visit(child, relative)
                            os.fsync(child)
                        finally:
                            os.close(child)
                    else:
                        _require(
                            stat.S_ISREG(metadata.st_mode)
                            and stat.S_IMODE(metadata.st_mode) == 0o444
                            and metadata.st_nlink == 1
                            and metadata.st_uid == os.geteuid(),
                            "Phase A run artifact stat changed",
                        )
                        files.add(relative.as_posix())

            visit(self.cap.run_fd, PurePosixPath())
            os.fsync(self.cap.run_fd)
            expected_files = {job.run_relative_path for job in self.cap.plan.global_artifact_order}
            expected_directories = {
                parent.as_posix()
                for job in self.cap.plan.global_artifact_order
                for parent in [
                    PurePosixPath(job.run_relative_path).parent,
                    *PurePosixPath(job.run_relative_path).parent.parents,
                ]
                if parent.as_posix() != "."
            }
            _require(
                files == expected_files
                and directories == expected_directories
                and self.published == expected_files,
                "Phase A run contains a missing, extra, or relabeled artifact",
            )
            publication_attempted = True
            try:
                _atomic_rename_directory_noreplace(
                    self.cap.namespace_fd,
                    self.cap.staging_name,
                    self.cap.run_parent_fd,
                    self.cap.run_name,
                )
            except (FileExistsError, OSError) as exc:
                raise ValidationError(
                    "Phase A atomic no-overwrite directory publication failed"
                ) from exc
            published_tree_identity = _named_identity(
                self.cap.run_parent_fd,
                self.cap.run_name,
            )
            _require(
                published_tree_identity == self.cap.staging_identity,
                "Phase A published tree inode changed at commit",
            )
            published = True
            os.fsync(self.cap.namespace_fd)
            os.fsync(self.cap.run_parent_fd)
            _require(
                _named_identity(self.cap.run_parent_fd, self.cap.run_name)
                == self.cap.staging_identity
                and not os.listdir(self.cap.namespace_fd),
                "Phase A atomic directory publication identity changed",
            )
            return {
                "status": "phase_a_controls_frozen_stop_required",
                "raw_controls": 32,
                "freeze_markers": 8,
                "artifacts": 40,
                "distinct_pids": 40,
                "distinct_invocations": 40,
                "capture_stopped_after_final_marker": True,
            }

    processes: list[subprocess.Popen[bytes]] = []

    def _release(*, require_success: bool) -> None:
        failures = []
        for process in processes:
            try:
                if process.poll() is None and process.stdin is not None:
                    process.stdin.write(b'{"command":"release"}\n')
                    process.stdin.flush()
                    process.stdin.close()
            except OSError as exc:
                failures.append(str(exc))
        for process in processes:
            try:
                code = process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                code = process.wait(timeout=5)
            if code != 0:
                failures.append(f"worker {process.pid} exited {code}")
        processes.clear()
        if require_success:
            _require(not failures, "Phase A child worker failed: " + "; ".join(failures))

    def _produce(cap: _Capability, job: PhaseAArtifactJob) -> Mapping[str, Any]:
        invocation_id = secrets.token_hex(16)
        command, environment = _phase_a_worker_subprocess_spec(
            cap.repository_root,
            cap.repository_fd,
            cap.staging_fd,
        )
        process = subprocess.Popen(
            command,
            cwd=cap.repository_root,
            env=environment,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            pass_fds=(cap.repository_fd, cap.staging_fd),
        )
        processes.append(process)
        _require(process.stdin is not None and process.stdout is not None, "Phase A child pipes are missing")
        process.stdin.write(_canonical_json_bytes({"job": asdict(job), "invocation_id": invocation_id}) + b"\n")
        process.stdin.flush()
        line = process.stdout.readline()
        if not line:
            stderr = b"" if process.stderr is None else process.stderr.read()
            raise ValidationError("Phase A child producer returned no evidence: " + stderr.decode(errors="replace"))
        envelope = json.loads(line.decode("utf-8"))
        _require(
            type(envelope) is dict
            and set(envelope) == {"job_sha256", "producer_executed", "payload"}
            and envelope["producer_executed"] is True
            and envelope["job_sha256"] == _json_value_sha256(asdict(job)),
            "Phase A child did not execute the exact evidence producer",
        )
        payload = envelope["payload"]
        _require(type(payload) is dict, "Phase A child evidence payload changed")
        identity = payload.get("process_identity")
        _require(
            process.pid != os.getpid()
            and process.poll() is None
            and type(identity) is dict
            and identity == {"pid": process.pid, "invocation_id": invocation_id},
            "Phase A child pid or nonce does not match the parent-observed live process",
        )
        _require(
            process.pid not in observed_pids
            and invocation_id not in observed_invocations
            and job.global_index not in observed_workers,
            "Phase A child pid, nonce, or job was reused",
        )
        observed_pids.add(process.pid)
        observed_invocations.add(invocation_id)
        observed_workers[job.global_index] = (process.pid, invocation_id)
        return payload

    def _finalize_success() -> None:
        nonlocal capability
        _require(capability is not None and published, "Phase A publication was not committed")
        cap = capability
        _require(
            _named_identity(cap.run_parent_fd, cap.run_name)
            == cap.staging_identity
            == published_tree_identity
            and not os.listdir(cap.namespace_fd),
            "Phase A published tree or staging namespace changed",
        )
        capability = None
        for descriptor in (
            cap.staging_fd,
            cap.namespace_fd,
            cap.run_fd,
            cap.run_parent_fd,
            cap.namespace_parent_fd,
            cap.repository_fd,
        ):
            try:
                os.close(descriptor)
            except OSError:
                pass

    try:
        cap = _authorize()
        writer = _Writer(cap)
        for job in cap.plan.raw_control_jobs:
            writer.publish(job, _produce(cap, job))
        for job in cap.plan.freeze_marker_jobs:
            writer.publish(job, _produce(cap, job))
        result = writer.finish()
        _require(
            len(processes) == 40
            and len({process.pid for process in processes}) == 40
            and all(process.poll() is None for process in processes),
            "Phase A did not retain 40 distinct live child producers",
        )
        _release(require_success=True)
        _finalize_success()
        return result
    except Exception:
        _release(require_success=False)
        _cleanup(reject_mutation=False)
        raise


_DIRECTORY_OPEN_FLAGS = (
    os.O_RDONLY
    | os.O_DIRECTORY
    | getattr(os, "O_NOFOLLOW", 0)
    | getattr(os, "O_CLOEXEC", 0)
)
_FILE_READ_FLAGS = (
    os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
)


def _fd_identity(descriptor: int) -> tuple[int, int]:
    metadata = os.fstat(descriptor)
    _require(stat.S_ISDIR(metadata.st_mode), "trusted Phase A descriptor is not a directory")
    return metadata.st_dev, metadata.st_ino


def _directory_path_from_fd(descriptor: int) -> Path:
    """Resolve a directory capability without trusting a caller-supplied path."""

    if hasattr(fcntl, "F_GETPATH"):
        raw = fcntl.fcntl(descriptor, fcntl.F_GETPATH, b"\0" * 1024)
        path = Path(raw.split(b"\0", 1)[0].decode("utf-8"))
    else:
        path = Path(os.readlink(f"/proc/self/fd/{descriptor}"))
    _require(path.is_absolute(), "Phase A directory descriptor path is not absolute")
    _assert_absolute_directory_identity(
        path,
        _fd_identity(descriptor),
        "Phase A directory descriptor",
    )
    return path


def _remove_phase_a_tree_at(parent_fd: int, name: str) -> None:
    metadata = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    if stat.S_ISDIR(metadata.st_mode):
        child_fd = os.open(name, _DIRECTORY_OPEN_FLAGS, dir_fd=parent_fd)
        try:
            os.fchmod(child_fd, 0o700)
            for child_name in os.listdir(child_fd):
                _remove_phase_a_tree_at(child_fd, child_name)
        finally:
            os.close(child_fd)
        os.rmdir(name, dir_fd=parent_fd)
    else:
        os.unlink(name, dir_fd=parent_fd)


def _open_absolute_directory_chain(path: Path) -> int:
    absolute = Path(os.path.abspath(os.fspath(path)))
    _require(absolute.is_absolute(), "trusted Phase A directory must be absolute")
    descriptor = os.open(absolute.anchor, _DIRECTORY_OPEN_FLAGS)
    try:
        for component in absolute.parts[1:]:
            child = os.open(component, _DIRECTORY_OPEN_FLAGS, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        return descriptor
    except (OSError, ValidationError):
        os.close(descriptor)
        raise


def _assert_absolute_directory_identity(
    path: Path,
    expected: tuple[int, int],
    label: str,
) -> None:
    try:
        descriptor = _open_absolute_directory_chain(path)
    except OSError as exc:
        raise ValidationError(f"{label} path changed, became a symlink, or is not a directory") from exc
    try:
        _require(_fd_identity(descriptor) == expected, f"{label} directory identity changed")
    finally:
        os.close(descriptor)


def _read_all_fd(descriptor: int) -> bytes:
    os.lseek(descriptor, 0, os.SEEK_SET)
    blocks: list[bytes] = []
    while True:
        block = os.read(descriptor, 1024 * 1024)
        if not block:
            return b"".join(blocks)
        blocks.append(block)


def _write_all_fd(descriptor: int, raw: bytes) -> None:
    view = memoryview(raw)
    while view:
        written = os.write(descriptor, view)
        if written <= 0:
            raise OSError("Phase A staging write made no progress")
        view = view[written:]


def _read_phase_a_child_file(
    root_fd: int,
    relative_path: str,
    label: str,
) -> tuple[Mapping[str, Any], str]:
    pure = PurePosixPath(relative_path)
    _require(
        not pure.is_absolute()
        and pure.parts
        and all(part not in {"", ".", ".."} for part in pure.parts),
        f"{label} path escaped its captured root",
    )
    descriptor = os.dup(root_fd)
    try:
        for component in pure.parts[:-1]:
            child = os.open(component, _DIRECTORY_OPEN_FLAGS, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        file_fd = os.open(pure.name, _FILE_READ_FLAGS, dir_fd=descriptor)
        try:
            metadata = os.fstat(file_fd)
            _require(
                stat.S_ISREG(metadata.st_mode)
                and stat.S_IMODE(metadata.st_mode) == 0o444
                and metadata.st_nlink == 1
                and metadata.st_uid == os.geteuid(),
                f"{label} stat contract changed",
            )
            raw = _read_all_fd(file_fd)
        finally:
            os.close(file_fd)
    finally:
        os.close(descriptor)
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValidationError(f"{label} is not canonical JSON") from exc
    _require(type(payload) is dict and raw == _canonical_json_bytes(payload), f"{label} bytes changed")
    return payload, hashlib.sha256(raw).hexdigest()


def _validate_legacy_protected(manifest: Mapping[str, Any]) -> None:
    legacy = manifest["legacy_protected"]
    _require_exact_keys(legacy, {"efficacy_credit", "sources"}, "legacy protected")
    _require(legacy["efficacy_credit"] is False, "legacy repositories gained efficacy credit")
    sources = legacy["sources"]
    _require(set(sources) == {"starlette", "requests", "redink", "daily"}, "legacy protected roster changed")
    expected_structure = {
        "starlette": (119, 254, 135, 24, 38, 16),
        "requests": (73, 200, 127, 28, 51, 27),
        "redink": (35, 73, 38, 10, 13, 5),
        "daily": (696, 1889, 1193, 44, 108, 64),
    }
    expected_projection = {
        "starlette": (35, 101, {"core_module": 35, "python_ast": 575}, {"imports:external": 194, "imports:resolved_exact": 119}, {"imports:external": 194, "imports:resolved_exact": 254}, "c4bd32e971befb79f75d9e9155746107c810ccd2d269f490ff18d924170755d6", "ce163d5c2e2f0d4288f4cc9a12d284664279e9654ce2ff3108562b012d42d2c6"),
        "requests": (20, 92, {"core_module": 20, "python_ast": 312}, {"imports:external": 131, "imports:resolved_exact": 73}, {"imports:external": 131, "imports:resolved_exact": 200}, "aade7c1c315a67749f61cbf80d271e960c4ab110c3e9d9e216244f05eef96d8a", "9a09a79c6e72c39552482dbc9b2bf2389435f2a97f70ac815270344cbae53b52"),
        "redink": (28, 87, {"core_module": 25, "python_ast": 137}, {"imports:external": 101, "imports:resolved_exact": 35}, {"imports:external": 101, "imports:resolved_exact": 73}, "7d49ac72a563158d68ecc394bc34a606e68afc46036399902b3471837e35880d", "4dd67818a097ec5d79c335d5e4a231a2b65f8d94fd6e8b98caca198bebac182c"),
        "daily": (203, 1596, {"core_module": 201, "python_ast": 3884}, {"imports:external": 1127, "imports:resolved_exact": 696, "tests:resolved_exact": 3}, {"imports:external": 1127, "imports:resolved_exact": 1889, "tests:resolved_exact": 3}, "e2ad97155bc13924f16e7399ee45ac6a72fdbed89bdcd1a5be4aaeb4d9b9cc03", "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570"),
    }
    expected_identity = {
        "starlette": ("https://github.com/Kludex/starlette.git", "5174d4c8358a6f06aa8056bafd14c2272dab8dd1", 35, "276c780e1f897cd0444f43045846ec9bfdaa150b01a843e6e35e99a1e138762f", "d74975b15aa95f0d2cec6328f40a9a467b476524e4675df75e25157b5c2393a7"),
        "requests": ("https://github.com/psf/requests.git", "414f0513c33883adf6f2b46901d4f0b38a455851", 20, "b3e6f4499ef2413e7b14ca46f917ec4d3a7374459b79eb9ec00ad8a31072283b", "db3b333f12cf87658bda31dad4acdc71afe99121226701aec3ef3dda2e4d5746"),
        "redink": ("https://github.com/HisMax/RedInk.git", "4d48722344594cf00e0498f0e1ed3df9cd4fd6be", 28, "0da08ce10d82b76b7020f083da194fa14b3663c19dac24d4adad9e324b3eed74", "53644c921010b3c32b9b82a45c4ab4e70bd993af5dab07b4de2fa90945b6d632"),
        "daily": ("https://github.com/ZhuLinsen/daily_stock_analysis.git", "487e49e565ffd1b96a7cf4d855f99cee3c981eaa", 203, "76cca5c6f2ae1ee83c563b11678559a70d8a4adf0356b4410a2f36d3ff7e37ee", "0b77bceb5225e7ff75a9ee2b1e0db04b70ecd0bd5aaef5c1b861b143f54423bb"),
    }
    for name, source in sources.items():
        _require(source["role"] == "protected_legacy_characterization", f"{name} is not protected legacy")
        _require(
            (source["url"], source["commit"], source["selected_count"], source["inventory_sha256"], source["content_sha256"])
            == expected_identity[name],
            f"{name} legacy identity changed",
        )
        baseline_exact, oracle_exact, causal, baseline_degree, oracle_degree, maximum_exact = expected_structure[name]
        _require(
            (
                source["baseline_resolved_exact"],
                source["oracle_resolved_exact"],
                source["oracle_causal_relation_count"],
                source["baseline_observed_max_outgoing"],
                source["oracle_observed_max_outgoing"],
                source["maximum_exact_relations_per_source"],
            )
            == expected_structure[name],
            f"{name} legacy formula inputs changed",
        )
        selected, active, producers, baseline_relations, oracle_relations, module_digest, non_python_digest = expected_projection[name]
        expected_pair = {
            "baseline": {
                "selected_files": selected,
                "non_relation_fields": {"active_chunks": active, "signals_by_producer": producers},
                "relation_buckets": baseline_relations,
                "module_projection_sha256": module_digest,
                "non_python_projection_sha256": non_python_digest,
            },
            "oracle": {
                "selected_files": selected,
                "non_relation_fields": {"active_chunks": active, "signals_by_producer": producers},
                "relation_buckets": oracle_relations,
                "module_projection_sha256": module_digest,
                "non_python_projection_sha256": non_python_digest,
            },
        }
        _require(source["structure_projection"] == expected_pair, f"{name} full structure projection changed")
        validate_structure_closed(
            source["structure_projection"]["baseline"],
            source["structure_projection"]["oracle"],
            causal,
            expected_relation_buckets=set(baseline_relations),
            expected_signal_producers=set(producers),
        )
        validate_degree_delta(baseline_degree, oracle_degree, maximum_exact)
    validate_daily_saturation_snapshot(sources["daily"]["saturation_snapshot"])


def _validate_public_source(source: Mapping[str, Any], source_root: Path) -> None:
    _require_exact_keys(
        source,
        {
            "repository_key", "repository_role", "url", "commit", "tree", "license_spdx",
            "license_path", "license_sha256", "include", "exclude", "selected_count",
            "inventory_sha256", "content_sha256",
        },
        "public source",
    )
    _require(_git_value(source_root, "HEAD") == source["commit"], "public source commit changed")
    _require(_git_value(source_root, "HEAD^{tree}") == source["tree"], "public source tree changed")
    status = subprocess.run(
        ["git", "-C", str(source_root), "status", "--porcelain"],
        text=True,
        capture_output=True,
        check=True,
    )
    _require(not status.stdout.strip(), "public source worktree is not clean")
    _require(
        _sha256(source_root / source["license_path"]) == source["license_sha256"],
        "public source license digest changed",
    )
    files = _select_public_source_inventory(source_root, source["include"], source["exclude"])
    _require(len(files) == source["selected_count"], "public source selected count changed")
    _require(_source_inventory_sha256(files) == source["inventory_sha256"], "public source inventory changed")
    _require(_source_content_sha256(source_root, files) == source["content_sha256"], "public source content changed")


def _validate_release_review_disposition(fresh: Mapping[str, Any]) -> None:
    path, digest = FRESH_RELEASE_REVIEW
    _require(
        fresh["release_review"]
        == {
            "path": path,
            "sha256": digest,
            "disposition": "approved_exact_recovery_v2_fresh_release_for_manifest_harness_binding_only",
        },
        "fresh release-review binding changed",
    )
    disposition = _read_public_json_anchor(path, digest)
    _require_exact_keys(
        disposition,
        {
            "schema_version", "disposition_id", "program", "attempt_id", "reviewed_at_utc",
            "reviewer", "disposition", "blocking_findings", "predecessor_release_authority",
            "reviewed_candidate_before_release_binding", "release_event_review",
            "released_payloads", "byte_and_schema_review", "inventory_and_zero_state",
            "review_axes", "authorization_boundary", "not_authorized", "write_policy",
        },
        "fresh release-review disposition",
    )
    _require(
        disposition["schema_version"] == 1
        and disposition["program"] == "p15-v3"
        and disposition["attempt_id"] == "p15-v3-attempt-001"
        and disposition["disposition"]
        == "approved_exact_recovery_v2_fresh_release_for_manifest_harness_binding_only"
        and disposition["blocking_findings"] == [],
        "fresh release-review disposition is not approved",
    )
    boundary = disposition["authorization_boundary"]
    _require(
        boundary["capture_authorized_by_this_disposition"] is False
        and boundary["authorized_existing_files_to_modify"]
        == [
            "tests/fixtures/p15_v3_exact_provenance_bonus/input_manifest.json",
            "tests/p15_v3_exact_provenance_bonus_acceptance.py",
        ]
        and boundary["required_release_bindings"]
        == [
            {"path": FRESH_RELEASED_PAYLOADS["httpx"][0], "sha256": FRESH_RELEASED_PAYLOADS["httpx"][1], "bytes": 15935, "mode": "0444"},
            {"path": FRESH_RELEASED_PAYLOADS["poetry_core"][0], "sha256": FRESH_RELEASED_PAYLOADS["poetry_core"][1], "bytes": 18753, "mode": "0444"},
        ],
        "fresh release-review authorization boundary changed",
    )
    _require(
        disposition["inventory_and_zero_state"]["exact_post_release_inventory"]
        == list(FRESH_SEAL_INVENTORY)
        and disposition["inventory_and_zero_state"]["capture_authorized"] is False
        and disposition["inventory_and_zero_state"]["v3_run_root_state"] == "absent",
        "fresh release-review inventory or zero-state changed",
    )


def _validate_frozen_released_contract(value: Mapping[str, Any]) -> None:
    _require_exact_keys(
        value,
        {
            "ablation", "aggregation", "attempt_id", "baseline_missing_case_count",
            "baseline_missing_required_items", "baseline_selected_required_items",
            "behavior_baseline", "click_decryption_attempts", "click_heldout_accessed",
            "closed_world_rule", "design_sha256", "embedding_dimensions", "embedding_model",
            "embedding_provider", "gold_adjusted_after_oracle", "local_model_calls",
            "ollama_calls", "online_model_calls", "oracle_executed_before_seal",
            "plan_sha256", "planner_enabled", "policy_a", "profile", "query_count",
            "reason", "required_item_denominator", "score_part", "sole_policy", "top_k",
            "unique_exact_signal_eligible_missing_items", "v3_capture_calls", "witness_rule",
        },
        "released frozen contract",
    )
    expected = {
        "ablation": [0.0, 0.04],
        "aggregation": "boolean_max_not_sum",
        "attempt_id": "p15-v3-attempt-001",
        "baseline_missing_case_count": 4,
        "baseline_missing_required_items": 4,
        "baseline_selected_required_items": 8,
        "behavior_baseline": BASELINE,
        "click_decryption_attempts": 0,
        "click_heldout_accessed": False,
        "closed_world_rule": "For each case, a selected ordinary path is relevant only when frozen as required or contextual; every other selected ordinary path is noise; no post-candidate relabeling.",
        "design_sha256": "d51f8ad79c0f7208e4810157379b3a77f516450bf9ba756d9c22161f4b227563",
        "embedding_dimensions": 384,
        "embedding_model": "hash-v1",
        "embedding_provider": "hash",
        "gold_adjusted_after_oracle": False,
        "local_model_calls": 0,
        "ollama_calls": 0,
        "online_model_calls": 0,
        "oracle_executed_before_seal": False,
        "plan_sha256": "f44108dd79616705690f730f8bf303d60693475aa9be5a8029107ef6e66d06f4",
        "planner_enabled": False,
        "policy_a": "permanently_forbidden_never_run",
        "profile": "hash",
        "query_count": 4,
        "reason": BONUS_REASON,
        "required_item_denominator": 12,
        "score_part": BONUS_SCORE_PART,
        "sole_policy": "B",
        "top_k": 12,
        "unique_exact_signal_eligible_missing_items": 4,
        "v3_capture_calls": 0,
        "witness_rule": "Each eligible missing item is closed by one unique active python_ast type/function target, one named non-star ImportFrom occurrence, and one existing direct python_ast imports resolved_exact module relation; constants and re-export-only evidence are forbidden.",
    }
    _require(value == expected, "released frozen contract changed")


def _validate_source_witness(
    witness: Mapping[str, Any],
    *,
    source_root: Path,
    selected_files: set[str],
    required_paths: set[str],
    missing_path: str,
) -> None:
    _require_exact_keys(
        witness,
        {
            "baseline_missing_required_target", "import_form", "imported_name", "importer",
            "module_relation", "named_non_star_occurrence_count", "target_chunk_id",
            "target_kind", "target_path", "target_project_unit_key",
            "target_qualified_name", "target_signal_id", "target_signal_uniqueness_count",
            "target_signature_sha256",
        },
        "released exact-import witness",
    )
    importer = witness["importer"]
    target_path = witness["target_path"]
    _require(importer in selected_files, "released witness importer is not a selected source member")
    _require(target_path in selected_files and target_path in required_paths, "released witness target is not a required source member")
    _require(
        witness["import_form"] == "ImportFrom"
        and isinstance(witness["imported_name"], str)
        and witness["imported_name"] not in {"", "*"}
        and witness["named_non_star_occurrence_count"] == 1
        and witness["target_kind"] in {"type", "function"}
        and witness["target_project_unit_key"] == ""
        and witness["target_signal_uniqueness_count"] == 1,
        "released witness named target constraint changed",
    )
    _require(
        witness["baseline_missing_required_target"] is (target_path == missing_path),
        "released witness missing-target flag changed",
    )
    relation = witness["module_relation"]
    _require_exact_keys(
        relation,
        {
            "kind", "producer", "relation_id", "resolution", "source_chunk_id",
            "source_signal_id", "target_kind", "target_qualified_name", "uniqueness_count",
        },
        "released witness module relation",
    )
    _require(
        relation["kind"] == "imports"
        and relation["producer"] == "python_ast"
        and relation["resolution"] == "resolved_exact"
        and relation["target_kind"] == "module"
        and relation["target_qualified_name"] == target_path
        and relation["uniqueness_count"] == 1
        and isinstance(relation["relation_id"], str)
        and relation["relation_id"].startswith("r5:"),
        "released witness relation is not one direct exact Python import",
    )
    try:
        importer_tree = ast.parse((source_root / importer).read_text(encoding="utf-8"))
        target_tree = ast.parse((source_root / target_path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, SyntaxError) as exc:
        raise ValidationError("released witness source cannot be parsed") from exc
    import_occurrences = sum(
        1
        for node in ast.walk(importer_tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
        if alias.name == witness["imported_name"] and alias.name != "*"
    )
    _require(import_occurrences == 1, "released witness ImportFrom occurrence changed in source")
    target_name = witness["target_qualified_name"].rsplit(".", 1)[-1]
    target_module = target_path.removesuffix(".py").replace("/", ".")
    _require(
        witness["target_qualified_name"] == f"{target_module}.{target_name}"
        and len(witness["target_signature_sha256"]) == 64
        and all(character in "0123456789abcdef" for character in witness["target_signature_sha256"]),
        "released witness qualified target or signature digest changed",
    )
    expected_node = ast.ClassDef if witness["target_kind"] == "type" else (ast.FunctionDef, ast.AsyncFunctionDef)
    target_occurrences = sum(
        1 for node in ast.walk(target_tree) if isinstance(node, expected_node) and node.name == target_name
    )
    _require(target_occurrences == 1, "released witness target definition changed in source")


def _validate_released_payload(
    slot: Mapping[str, Any],
    contract: Mapping[str, Any],
) -> Mapping[str, Any]:
    repository_key = slot["repository_key"]
    path, digest, size, seal_id = FRESH_RELEASED_PAYLOADS[repository_key]
    _require(
        slot["plaintext_path"] == path
        and slot["released_payload_path"] == path
        and slot["released_payload_sha256"] == digest
        and slot["released_payload_bytes"] == size
        and slot["released_payload_mode"] == "0444",
        "fresh sealed payload binding changed",
    )
    released, actual_digest = _read_immutable_canonical_json(
        _repo_path(path), f"released fresh payload {repository_key}"
    )
    _require(actual_digest == digest, "released fresh payload digest changed")
    _require(_repo_path(path).lstat().st_size == size, "released fresh payload size changed")
    _require(isinstance(released, Mapping), "released fresh payload is not an object")
    _require_exact_keys(
        released,
        {"schema_version", "seal_id", "sealed_at_utc", "reviewer_role", "source", "frozen_contract", "cases", "release_control"},
        "released fresh payload",
    )
    _require(
        released["schema_version"] == 1
        and released["seal_id"] == seal_id
        and released["sealed_at_utc"] == "2026-07-31T22:06:50Z"
        and released["reviewer_role"] == "independent_p15_v3_fresh_efficacy_recovery_reviewer"
        and released["source"] == contract["source"],
        "released fresh payload identity or public source binding changed",
    )
    _require(
        released["release_control"]
        == {
            "no_gold_mutation_after_seal": True,
            "plaintext_file_created": False,
            "release_authorized": False,
            "release_not_before": "a later independent recovery-v2 manifest and harness rebind review authorizes exact raw-byte release while capture remains fail-closed",
            "release_path": path,
            "serialization": "canonical_json_sort_keys_compact_utf8_no_trailing_newline",
            "status": "recovery_v2_sealed_not_released",
        },
        "released payload immutable pre-release control changed",
    )
    _validate_frozen_released_contract(released["frozen_contract"])
    cases = released["cases"]
    _require(isinstance(cases, list) and len(cases) == 4, "released payload case count changed")
    selected_source_files = set(
        _select_public_source_inventory(
            _repo_path(slot["source_root"]),
            released["source"]["include"],
            released["source"]["exclude"],
        )
    )
    case_ids: set[str] = set()
    queries: set[str] = set()
    missing_signal_ids: set[str] = set()
    required_total = selected_required_total = missing_total = witness_total = 0
    for case in cases:
        _require_exact_keys(
            case,
            {
                "id", "query", "required", "contextual", "baseline_selected_paths",
                "baseline_required_ranks", "eligible_missing_required_paths",
                "membership_change_eligible", "protected_winner", "exact_import_witnesses",
            },
            "released fresh case",
        )
        _require(isinstance(case["id"], str) and case["id"], "released case id is empty")
        _require(isinstance(case["query"], str) and case["query"].strip(), "released query is empty")
        _require(case["id"] not in case_ids and case["query"] not in queries, "released case id or query is duplicated")
        case_ids.add(case["id"])
        queries.add(case["query"])
        required = case["required"]
        _require(isinstance(required, list) and len(required) == 3, "released required gold count changed")
        for item in required:
            _require_exact_keys(item, {"path", "role", "necessity"}, "released required gold item")
            _require(
                isinstance(item["path"], str)
                and isinstance(item["necessity"], str)
                and item["necessity"].strip()
                and item["role"] in {"entrypoint", "implementation", "support"},
                "released required gold item changed",
            )
        required_paths = {item["path"] for item in required}
        _require(
            len(required_paths) == 3
            and {item["role"] for item in required} == {"entrypoint", "implementation", "support"}
            and required_paths <= selected_source_files,
            "released required paths or roles are not unique source members",
        )
        baseline = case["baseline_selected_paths"]
        contextual = case["contextual"]
        _require(
            isinstance(baseline, list) and len(baseline) == 12 and len(set(baseline)) == 12
            and set(baseline) <= selected_source_files,
            "released baseline selected paths changed",
        )
        _require(
            isinstance(contextual, list) and len(contextual) == len(set(contextual))
            and set(contextual) <= set(baseline),
            "released contextual source membership changed",
        )
        ranks = case["baseline_required_ranks"]
        _require(set(ranks) == required_paths, "released baseline required-rank keys changed")
        ranked = {path: rank for path, rank in ranks.items() if rank is not None}
        _require(
            len(ranked) == 2
            and all(isinstance(rank, int) and 1 <= rank <= 12 and baseline[rank - 1] == path for path, rank in ranked.items()),
            "released baseline required ranks changed",
        )
        missing = case["eligible_missing_required_paths"]
        _require(
            isinstance(missing, list) and len(missing) == 1
            and missing[0] in required_paths and ranks[missing[0]] is None and missing[0] not in baseline
            and case["membership_change_eligible"] is True,
            "released eligible missing required path changed",
        )
        _require(case["protected_winner"] in baseline, "released protected winner is not baseline-selected")
        witnesses = case["exact_import_witnesses"]
        _require(isinstance(witnesses, list) and len(witnesses) == 2, "released witness count changed")
        for witness in witnesses:
            _validate_source_witness(
                witness,
                source_root=_repo_path(slot["source_root"]),
                selected_files=selected_source_files,
                required_paths=required_paths,
                missing_path=missing[0],
            )
        missing_witnesses = [witness for witness in witnesses if witness["baseline_missing_required_target"]]
        _require(len(missing_witnesses) == 1, "released missing-target witness cardinality changed")
        missing_signal_ids.add(missing_witnesses[0]["target_signal_id"])
        required_total += len(required)
        selected_required_total += len(ranked)
        missing_total += len(missing)
        witness_total += len(witnesses)
    _require(
        (required_total, selected_required_total, missing_total, len(missing_signal_ids), witness_total)
        == (12, 8, 4, 4, 8),
        "released query/gold/witness totals changed",
    )
    return released


def _validate_fresh_slot(slot: Mapping[str, Any]) -> Mapping[str, Any]:
    slot_keys = {
        "slot", "status", "repository_key", "source_root", "repository_identity", "url",
        "commit", "tree", "license_spdx", "license_path", "license_sha256", "selected_count",
        "inventory_sha256", "content_sha256", "case_count", "required_item_denominator",
        "baseline_selected_required_items", "baseline_missing_required_items",
        "baseline_missing_case_count", "unique_exact_signal_eligible_missing_items",
        "public_contract_path", "public_contract_sha256", "sealed_payload_path",
        "sealed_payload_sha256", "sealed_plaintext_metadata_sha256", "sealed_payload_bytes",
        "sealed_payload_mode", "plaintext_path", "release_authorized", "capture_authorized",
        "released_payload_path", "released_payload_sha256", "released_payload_bytes",
        "released_payload_mode",
    }
    _require_exact_keys(slot, slot_keys, "fresh slot")
    repository_key = slot["repository_key"]
    _require(repository_key in FRESH_PUBLIC_CONTRACTS, "fresh repository key changed")
    expected_slot_identity = {
        "httpx": {
            "slot": "fresh_a",
            "source_root": ".quality/p15-v3-sources/httpx",
            "repository_identity": "encode/httpx",
        },
        "poetry_core": {
            "slot": "fresh_b",
            "source_root": ".quality/p15-v3-sources/poetry-core",
            "repository_identity": "python-poetry/poetry-core",
        },
    }[repository_key]
    _require(
        {key: slot[key] for key in expected_slot_identity} == expected_slot_identity,
        "fresh slot identity or fixed source path changed",
    )
    contract_path, contract_sha256 = FRESH_PUBLIC_CONTRACTS[repository_key]
    _require(
        slot["public_contract_path"] == contract_path
        and slot["public_contract_sha256"] == contract_sha256,
        "fresh public contract anchor changed",
    )
    contract = _read_public_json_anchor(contract_path, contract_sha256)
    _require_exact_keys(
        contract,
        {
            "schema_version", "seal_id", "sealed_at_utc", "reviewer_role", "status", "source",
            "policy_binding", "admissibility", "sealed_payload", "recovery",
        },
        "fresh public contract",
    )
    _require(
        contract["schema_version"] == 1
        and contract["reviewer_role"] == "independent_p15_v3_fresh_efficacy_recovery_reviewer"
        and contract["status"] == "sealed_recovery_v2_pending_new_rebind_no_release",
        "fresh public contract status changed",
    )
    source = contract["source"]
    source_root = _repo_path(slot["source_root"])
    _validate_public_source(source, source_root)
    _require(
        {
            "repository_key": slot["repository_key"],
            "url": slot["url"],
            "commit": slot["commit"],
            "tree": slot["tree"],
            "license_spdx": slot["license_spdx"],
            "license_path": slot["license_path"],
            "license_sha256": slot["license_sha256"],
            "selected_count": slot["selected_count"],
            "inventory_sha256": slot["inventory_sha256"],
            "content_sha256": slot["content_sha256"],
        }
        == {key: source[key] for key in (
            "repository_key", "url", "commit", "tree", "license_spdx", "license_path",
            "license_sha256", "selected_count", "inventory_sha256", "content_sha256",
        )},
        "fresh source manifest binding changed",
    )
    _require(
        contract["policy_binding"]
        == {
            "behavior_baseline": BASELINE,
            "design_sha256": "d51f8ad79c0f7208e4810157379b3a77f516450bf9ba756d9c22161f4b227563",
            "plan_sha256": "f44108dd79616705690f730f8bf303d60693475aa9be5a8029107ef6e66d06f4",
            "sole_policy": "B",
            "policy_a": "permanently_forbidden_never_run",
            "ablation": [0.0, 0.04],
            "score_part": BONUS_SCORE_PART,
            "reason": BONUS_REASON,
            "aggregation": "boolean_max_not_sum",
        },
        "fresh policy binding changed",
    )
    admissibility = contract["admissibility"]
    _require_exact_keys(
        admissibility,
        {
            "profile", "embedding_provider", "embedding_model", "embedding_dimensions",
            "planner_enabled", "top_k", "case_count", "required_item_denominator",
            "baseline_selected_required_items", "baseline_missing_required_items",
            "baseline_missing_case_count", "unique_exact_signal_eligible_missing_items",
            "oracle_executed_before_seal", "gold_adjusted_after_oracle", "model_calls",
            "ollama_calls", "click_accessed", "v3_capture_calls",
        },
        "fresh admissibility",
    )
    _require(
        admissibility
        == {
            "profile": "hash", "embedding_provider": "hash", "embedding_model": "hash-v1",
            "embedding_dimensions": 384, "planner_enabled": False, "top_k": 12,
            "case_count": 4, "required_item_denominator": 12,
            "baseline_selected_required_items": 8, "baseline_missing_required_items": 4,
            "baseline_missing_case_count": 4, "unique_exact_signal_eligible_missing_items": 4,
            "oracle_executed_before_seal": False, "gold_adjusted_after_oracle": False,
            "model_calls": 0, "ollama_calls": 0, "click_accessed": False, "v3_capture_calls": 0,
        },
        "fresh admissibility or headroom changed",
    )
    for field in (
        "case_count", "required_item_denominator", "baseline_selected_required_items",
        "baseline_missing_required_items", "baseline_missing_case_count",
        "unique_exact_signal_eligible_missing_items",
    ):
        _require(slot[field] == admissibility[field], f"fresh slot count changed: {field}")
    _require(
        contract["recovery"]
        == {
            "reason": "prior_ephemeral_decryption_key_unavailable_before_release",
            "old_seal_bytes_modified": False,
            "old_release_path_state": "absent",
            "gold_changed": False,
            "new_key_location": "reviewer_only_ephemeral_functions_store",
            "new_key_disclosed": False,
        },
        "fresh recovery contract changed",
    )
    sealed = contract["sealed_payload"]
    _require_exact_keys(
        sealed,
        {
            "path", "future_release_path", "format", "cipher", "kdf", "iterations",
            "salted", "bytes", "plaintext_serialization", "plaintext_sha256",
            "ciphertext_sha256", "round_trip_verified", "plaintext_file_created",
            "release_authorized", "release_not_before",
        },
        "fresh sealed payload metadata",
    )
    _require(
        sealed["format"] == "openssl-enc"
        and sealed["cipher"] == "aes-256-cbc"
        and sealed["kdf"] == "pbkdf2-hmac-sha256"
        and sealed["iterations"] == 600000
        and sealed["salted"] is True
        and sealed["plaintext_serialization"] == "canonical_json_sort_keys_compact_utf8_no_trailing_newline"
        and sealed["round_trip_verified"] is True
        and sealed["plaintext_file_created"] is False
        and sealed["release_authorized"] is False,
        "fresh cipher/KDF/release metadata changed",
    )
    _require(
        {
            "path": slot["sealed_payload_path"],
            "future_release_path": slot["plaintext_path"],
            "bytes": slot["sealed_payload_bytes"],
            "plaintext_sha256": slot["sealed_plaintext_metadata_sha256"],
            "ciphertext_sha256": slot["sealed_payload_sha256"],
        }
        == {key: sealed[key] for key in (
            "path", "future_release_path", "bytes", "plaintext_sha256", "ciphertext_sha256",
        )},
        "fresh sealed payload binding changed",
    )
    _require(slot["sealed_payload_mode"] == "0600", "fresh sealed payload mode contract changed")
    _validate_file_stat(
        _repo_path(slot["sealed_payload_path"]),
        mode=0o600,
        size=slot["sealed_payload_bytes"],
        label=f"opaque fresh payload {repository_key}",
    )
    _require(
        slot["status"] == "released_exact_bound_capture_unauthorized"
        and slot["release_authorized"] is False
        and slot["capture_authorized"] is False,
        "fresh released slot or capture boundary changed",
    )
    _validate_released_payload(slot, contract)
    return contract


def _validate_roster_and_seal_hashes(fresh: Mapping[str, Any]) -> None:
    roster_path, roster_sha = FRESH_ROSTER_CONTRACT
    roster = _read_public_json_anchor(roster_path, roster_sha)
    _require_exact_keys(
        roster,
        {
            "schema_version", "roster_id", "sealed_at_utc", "attempt_id", "status",
            "fresh_efficacy", "combined_headroom", "click", "archived_revoked_release_chain",
            "frozen_behavior", "selection_and_recovery_policy", "authorization_boundary",
        },
        "fresh roster contract",
    )
    _require(
        roster["schema_version"] == 1
        and roster["attempt_id"] == "p15-v3-attempt-001"
        and roster["status"] == "sealed_pending_independent_recovery_v2_rebind_no_release_no_capture",
        "fresh roster identity changed",
    )
    expected_roster_slots = []
    for slot in fresh["slots"]:
        expected_roster_slots.append(
            {
                "slot": slot["slot"],
                "repository_key": slot["repository_key"],
                "seal_id": (
                    "p15-v3-recovery-v2-fresh-httpx-b5addb6"
                    if slot["repository_key"] == "httpx"
                    else "p15-v3-recovery-v2-fresh-poetry-core-5de2411"
                ),
                "public_contract_path": slot["public_contract_path"],
                "public_contract_sha256": slot["public_contract_sha256"],
                "ciphertext_path": slot["sealed_payload_path"],
                "ciphertext_sha256": slot["sealed_payload_sha256"],
                "plaintext_sha256": slot["sealed_plaintext_metadata_sha256"],
                "future_release_path": slot["plaintext_path"],
                "case_count": slot["case_count"],
                "required_item_denominator": slot["required_item_denominator"],
                "baseline_missing_required_items": slot["baseline_missing_required_items"],
                "baseline_missing_case_count": slot["baseline_missing_case_count"],
                "unique_exact_signal_eligible_missing_items": slot["unique_exact_signal_eligible_missing_items"],
                "status": "sealed_not_released_capture_unauthorized",
            }
        )
    _require(roster["fresh_efficacy"] == expected_roster_slots, "fresh roster slots changed")
    _require(roster["combined_headroom"] == fresh["combined_headroom"], "combined headroom changed")
    archived = roster["archived_revoked_release_chain"]
    _require_exact_keys(
        archived,
        {
            "reason", "old_bytes_modified", "old_release_paths_state", "old_fresh_seals",
            "old_review_chain",
        },
        "archived revoked recovery chain",
    )
    _require(
        archived["old_bytes_modified"] is False
        and archived["old_release_paths_state"] == "absent"
        and archived["old_fresh_seals"]["status"]
        == "archived_and_revoked_for_release_or_capture_not_deleted",
        "old fresh seal chain was not archived and revoked",
    )
    _require(
        roster["click"]
        == {
            "repository_key": "click",
            "carry_forward_disposition_path": CLICK_CARRY_FORWARD[0],
            "carry_forward_disposition_sha256": CLICK_CARRY_FORWARD[1],
            "status": "conditional_carry_forward_sealed_unopened_capture_unauthorized",
        },
        "roster Click anchor changed",
    )
    _require(
        roster["frozen_behavior"]
        == {
            "behavior_baseline": BASELINE,
            "sole_policy": "B",
            "policy_a": "permanently_forbidden_never_run",
            "ablation": [0.0, 0.04],
            "score_part": BONUS_SCORE_PART,
            "reason": BONUS_REASON,
            "aggregation": "boolean_max_not_sum",
            "top_k": 12,
            "gold_semantics": "unchanged_from_independent_fresh_screen",
            "ranking_weights_budgets_caps_owner_merge_context_and_final_selection": "unchanged",
        },
        "roster frozen behavior changed",
    )
    _require(
        roster["selection_and_recovery_policy"]
        == {
            "screening": "baseline hash embeddings with planner disabled only",
            "oracle_used": False,
            "model_used": False,
            "ollama_used": False,
            "click_accessed": False,
            "plaintext_serialization": "canonical_json_sort_keys_compact_utf8_no_trailing_newline",
            "new_keys_stored_as": [
                "p15_v3_recovery_v2_httpx_key",
                "p15_v3_recovery_v2_poetry_core_key",
            ],
            "keys_disclosed": False,
            "same_turn_key_continuity_required_until_release_or_explicit_reseal": True,
        },
        "fresh selection policy changed",
    )
    boundary = roster["authorization_boundary"]
    _require_exact_keys(
        boundary,
        {
            "fresh_payload_release_authorized", "fresh_capture_authorized",
            "click_open_authorized", "click_capture_authorized", "src_writes_authorized",
            "next_transition",
        },
        "fresh roster authorization boundary",
    )
    _require(
        boundary["fresh_payload_release_authorized"] is False
        and boundary["fresh_capture_authorized"] is False
        and boundary["click_open_authorized"] is False
        and boundary["click_capture_authorized"] is False
        and boundary["src_writes_authorized"] is False,
        "roster authorized release, capture, or Click open",
    )
    seal_path, seal_sha = FRESH_SEAL_HASHES
    seal_hashes = _read_public_json_anchor(seal_path, seal_sha)
    _require(
        seal_hashes
        == {
            "schema_version": 1,
            "sealed_at_utc": "2026-07-31T22:06:50Z",
            "attempt_id": "p15-v3-attempt-001",
            "seal_generation": "recovery_v2",
            "httpx": {
                "public_contract_path": FRESH_PUBLIC_CONTRACTS["httpx"][0],
                "public_contract_sha256": FRESH_PUBLIC_CONTRACTS["httpx"][1],
                "ciphertext_path": fresh["slots"][0]["sealed_payload_path"],
                "ciphertext_sha256": fresh["slots"][0]["sealed_payload_sha256"],
                "plaintext_sha256": fresh["slots"][0]["sealed_plaintext_metadata_sha256"],
                "future_release_path": fresh["slots"][0]["plaintext_path"],
            },
            "poetry_core": {
                "public_contract_path": FRESH_PUBLIC_CONTRACTS["poetry_core"][0],
                "public_contract_sha256": FRESH_PUBLIC_CONTRACTS["poetry_core"][1],
                "ciphertext_path": fresh["slots"][1]["sealed_payload_path"],
                "ciphertext_sha256": fresh["slots"][1]["sealed_payload_sha256"],
                "plaintext_sha256": fresh["slots"][1]["sealed_plaintext_metadata_sha256"],
                "future_release_path": fresh["slots"][1]["plaintext_path"],
            },
            "roster_contract": {"path": roster_path, "sha256": roster_sha},
            "click_carry_forward": {
                "path": CLICK_CARRY_FORWARD[0], "sha256": CLICK_CARRY_FORWARD[1],
            },
            "archived_revoked_chain": {
                "old_seal_hash_index": {
                    "path": ".quality/p15-v3-review-seal/seal_hashes.json",
                    "sha256": "c00f92eb395846f8edbcca220572cc15c4568c6b3b01ecaac542fd8a22029989",
                },
                "old_manifest_harness_rebind": {
                    "path": ".quality/p15-v3-rebind-review-seal/independent_manifest_harness_rebind_disposition.json",
                    "sha256": "6d146807c5f497552a68b53e934138cc4639e4d178977503c3f96f3ac6877059",
                },
                "old_release_byte_supplemental": {
                    "path": ".quality/p15-v3-rebind-review-seal/independent_fresh_release_byte_identity_supplemental_disposition.json",
                    "sha256": "7715ddb343949e3148b87c8162cd931f922c237716561deb8e27ef0f3e50b9f1",
                },
                "old_incident_disposition": {
                    "path": ".quality/p15-v3-incident-review/independent_ciphertext_probe_boundary_incident_disposition.json",
                    "sha256": "3afa2e4624e2a80bcf2b7d928987c2d944b81a1c3de87a040fab1ff19868b1b2",
                },
            },
        },
        "fresh seal hash index changed",
    )


def _validate_click_carry_forward(click: Mapping[str, Any]) -> None:
    path, digest = CLICK_CARRY_FORWARD
    disposition = _read_public_json_anchor(path, digest)
    _require_exact_keys(
        disposition,
        {
            "schema_version", "disposition_id", "program", "attempt_id", "reviewed_at_utc",
            "reviewer", "disposition", "blocking_findings", "predecessor",
            "immutable_click_anchors_from_predecessor_public_metadata_only",
            "recovery_boundary", "verification", "write_policy",
        },
        "Click carry-forward disposition",
    )
    _require(
        disposition["schema_version"] == 1
        and disposition["program"] == "p15-v3"
        and disposition["attempt_id"] == "p15-v3-attempt-001"
        and disposition["disposition"] == "approved_conditional_carry_forward_sealed_unopened_recovery_v2"
        and disposition["blocking_findings"] == [],
        "Click carry-forward was not conditionally approved",
    )
    anchors = disposition["immutable_click_anchors_from_predecessor_public_metadata_only"]
    _require(
        anchors
        == {
            "repository": click["repository"],
            "commit": click["commit"],
            "tree": "c6aa87f15f2e44a6fcab33714e1eb91e2552d816",
            "public_contract_path": click["public_contract_path"],
            "public_contract_sha256": click["public_contract_sha256"],
            "ciphertext_path": click["sealed_payload_path"],
            "ciphertext_sha256": click["sealed_ciphertext_sha256"],
            "sealed_plaintext_sha256_from_public_metadata_only": click["sealed_plaintext_sha256"],
            "case_count": 4,
            "required_item_denominator": 12,
            "top_k": 12,
            "status": "sealed_unopened",
        },
        "Click recovery-v2 metadata anchor changed",
    )
    boundary = disposition["recovery_boundary"]
    _require(
        boundary["fresh_reseal_does_not_modify_or_reinterpret_click"] is True
        and boundary["click_files_read_during_recovery"] == 0
        and boundary["click_decryption_attempts"] == 0
        and boundary["click_plaintext_created"] is False
        and boundary["click_open_record_created"] is False
        and boundary["click_capture_calls"] == 0
        and boundary["open_authorized"] is False
        and boundary["capture_authorized"] is False,
        "Click recovery-v2 boundary opened",
    )
    _require(
        disposition["verification"]
        == {
            "basis": "predecessor disposition and immutable public metadata only; no Click file was opened or hashed during recovery",
            "model_calls": 0,
            "ollama_calls": 0,
            "fresh_capture_calls": 0,
            "src_writes": 0,
        },
        "Click recovery-v2 verification changed",
    )
    _require(not _repo_path(click["plaintext_path"]).exists(), "Click plaintext exists")
    _require(not _repo_path(click["open_record_path"]).exists(), "Click open record exists")


def _validate_fresh_and_click(manifest: Mapping[str, Any]) -> None:
    fresh = manifest["fresh_efficacy"]
    _require_exact_keys(
        fresh,
        {
            "status", "seal_generation", "required_repository_count", "selection_authority",
            "identity_publicly_released", "roster_contract", "seal_hashes", "release_review", "seal_directory",
            "seal_directory_exact_inventory", "archived_revoked_chain", "combined_headroom",
            "release_authorized", "capture_authorized", "slots",
        },
        "fresh efficacy",
    )
    _require(
        fresh["status"] == "recovery_v2_released_exact_bound_capture_unauthorized"
        and fresh["seal_generation"] == "recovery_v2"
        and fresh["required_repository_count"] == 2
        and fresh["selection_authority"] == "independent_reviewer"
        and fresh["identity_publicly_released"] is True
        and fresh["release_authorized"] is False
        and fresh["capture_authorized"] is False,
        "fresh seal boundary changed",
    )
    _require(
        fresh["roster_contract"] == {"path": FRESH_ROSTER_CONTRACT[0], "sha256": FRESH_ROSTER_CONTRACT[1]}
        and fresh["seal_hashes"] == {"path": FRESH_SEAL_HASHES[0], "sha256": FRESH_SEAL_HASHES[1]},
        "fresh roster or seal-hash binding changed",
    )
    seal_directory = _repo_path(fresh["seal_directory"])
    expected_seal_inventory = list(FRESH_SEAL_INVENTORY)
    _require(
        fresh["seal_directory_exact_inventory"] == expected_seal_inventory
        and sorted(entry.name for entry in seal_directory.iterdir()) == expected_seal_inventory,
        "fresh seal directory inventory changed",
    )
    archived = fresh["archived_revoked_chain"]
    _require_exact_keys(
        archived,
        {
            "only_active_seal_directory", "old_fresh_seal_directory",
            "old_manifest_harness_rebind", "old_release_byte_supplemental",
            "old_incident_disposition", "old_release_paths_state",
            "old_artifacts_may_be_referenced_by_active_fields",
        },
        "manifest archived revoked chain",
    )
    _require(
        archived
        == {
            "only_active_seal_directory": ".quality/p15-v3-recovery-seal-v2",
            "old_fresh_seal_directory": {
                "path": ".quality/p15-v3-review-seal",
                "status": "archived_and_revoked_for_release_or_capture_not_deleted",
            },
            "old_manifest_harness_rebind": {
                "path": ".quality/p15-v3-rebind-review-seal/independent_manifest_harness_rebind_disposition.json",
                "sha256": "6d146807c5f497552a68b53e934138cc4639e4d178977503c3f96f3ac6877059",
                "status": "archived_revoked_for_old_fresh_release_and_not_valid_for_recovery_v2",
            },
            "old_release_byte_supplemental": {
                "path": ".quality/p15-v3-rebind-review-seal/independent_fresh_release_byte_identity_supplemental_disposition.json",
                "sha256": "7715ddb343949e3148b87c8162cd931f922c237716561deb8e27ef0f3e50b9f1",
                "status": "archived_revoked_for_old_fresh_release_and_not_valid_for_recovery_v2",
            },
            "old_incident_disposition": {
                "path": ".quality/p15-v3-incident-review/independent_ciphertext_probe_boundary_incident_disposition.json",
                "sha256": "3afa2e4624e2a80bcf2b7d928987c2d944b81a1c3de87a040fab1ff19868b1b2",
                "status": "archived_as_recovery_trigger_not_release_authority_for_recovery_v2",
            },
            "old_release_paths_state": "absent",
            "old_artifacts_may_be_referenced_by_active_fields": False,
        },
        "old fresh/rebind/supplemental/incident archive status changed",
    )
    active_fresh = {key: value for key, value in fresh.items() if key != "archived_revoked_chain"}
    active_serialized = json.dumps(active_fresh, sort_keys=True)
    _require(
        not any(prefix in active_serialized for prefix in REVOKED_V3_PATH_PREFIXES),
        "active fresh fields reference a revoked artifact",
    )
    _require(len(fresh["slots"]) == 2, "fresh slot count changed")
    for index, slot in enumerate(fresh["slots"]):
        _require(slot["slot"] == ("fresh_a" if index == 0 else "fresh_b"), "fresh slot order changed")
        _validate_fresh_slot(slot)
    expected_headroom = {
        "case_count": 8,
        "required_item_denominator": 24,
        "baseline_selected_required_items": 16,
        "baseline_missing_required_items": 8,
        "baseline_missing_case_count": 8,
        "unique_exact_signal_eligible_missing_items": 8,
        "minimum_required_items": 3,
        "minimum_required_cases": 3,
        "mathematical_headroom_gate": "pass",
    }
    _require(fresh["combined_headroom"] == expected_headroom, "fresh combined headroom changed")
    _validate_roster_and_seal_hashes(fresh)
    _validate_release_review_disposition(fresh)

    click = manifest["click"]
    _require_exact_keys(
        click,
        {
            "role", "status", "repository", "commit", "public_contract_path",
            "public_contract_sha256", "sealed_payload_path", "sealed_plaintext_sha256",
            "sealed_ciphertext_sha256", "sealed_payload_bytes", "sealed_payload_mode",
            "carry_forward_disposition_path", "carry_forward_disposition_sha256",
            "plaintext_path", "open_record_path", "opened", "capture_authorized",
        },
        "Click contract",
    )
    _require(
        click["role"] == "conditional_carry_forward_only"
        and click["status"] == "approved_conditional_carry_forward_sealed_unopened_capture_unauthorized"
        and click["opened"] is False
        and click["capture_authorized"] is False,
        "Click gate was opened or capture-authorized",
    )
    _require(
        click["carry_forward_disposition_path"] == CLICK_CARRY_FORWARD[0]
        and click["carry_forward_disposition_sha256"] == CLICK_CARRY_FORWARD[1],
        "Click carry-forward binding changed",
    )
    _validate_click_carry_forward(click)


def _validate_boundary_and_cleanliness(manifest: Mapping[str, Any]) -> None:
    expected_boundary = {
        "skeleton_model_calls_allowed": False,
        "eventual_capture_requires_online_model": True,
        "local_ollama_forbidden": True,
        "new_oracle_forbidden": True,
        "sealed_payload_reads_forbidden": True,
        "fresh_release_forbidden": True,
        "click_access_forbidden": True,
        "src_writes_forbidden": True,
    }
    _require(manifest["execution_boundary"] == expected_boundary, "execution boundary changed")
    _require(manifest["capture_authorized"] is False and manifest["skeleton_only"] is True, "capture became authorized")
    _require(manifest["status"] == "awaiting_independent_phasea_engine_review", "skeleton status changed")
    _require(manifest["review"] == {
        "recovery_v2_fresh_roster": "externally_reviewed_exact_release_bound_capture_unauthorized",
        "recovery_v2_click_carry_forward": "approved_conditional_sealed_unopened_capture_unauthorized",
        "recovery_v2_release_review": "approved_exact_release_binding_only",
        "phase_a_control_engine": "pending_independent_review_no_execution_authority",
        "old_fresh_rebind_supplemental_incident_chain": "archived_revoked_not_active_authority",
        "capture_authorization": "none",
    }, "review was self-approved or changed")
    _require(manifest["evidence"] == {
        "run_root": ".quality/p15-runs/p15-v3-attempt-001",
        "required_initial_state": "absent",
        "write_policy_after_authorization": "write_new_only",
    }, "v3 evidence contract changed")
    _require(not _repo_path(manifest["evidence"]["run_root"]).exists(), "v3 run root already exists")
    _require(manifest["behavior_baseline"] == BASELINE, "behavior baseline changed")

    diff = subprocess.run(
        ["git", "diff", "--exit-code", BASELINE, "--", "src/context_search_tool"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    _require(diff.returncode == 0, "src/context_search_tool differs from the frozen baseline")
    untracked = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard", "--", "src/context_search_tool"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    _require(not untracked.stdout.strip(), "untracked product source exists")


def validate_manifest_payload(manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Validate an in-memory payload; exposed for closed mutation tests."""

    _require_exact_keys(
        manifest,
        {
            "schema_version",
            "program",
            "attempt_id",
            "status",
            "capture_authorized",
            "skeleton_only",
            "identities",
            "policy",
            "frozen_nonchanges",
            "formula_contract",
            "task0_two_phase_runtime",
            "phase_a_control_engine",
            "legacy_protected",
            "v2_terminal",
            "fresh_efficacy",
            "click",
            "execution_boundary",
            "review",
            "evidence",
            "behavior_baseline",
        },
        "manifest",
    )
    _require(manifest["schema_version"] == 3 and manifest["program"] == "p15-v3", "v3 manifest identity changed")
    _require(manifest["attempt_id"] == "p15-v3-attempt-001", "v3 attempt changed")
    _validate_identity_files(manifest)
    _validate_policy_and_nonchanges(manifest)
    _validate_formula_contract(manifest)
    _validate_legacy_protected(manifest)
    old = _validate_v2_terminal(manifest)
    _validate_fresh_and_click(manifest)
    _validate_phase_a_engine_contract(manifest)
    phase_a_plan = build_phase_a_control_plan(manifest)
    _require(
        phase_a_plan["status"] == "inert_no_execution_or_writes"
        and phase_a_plan["query_count"] == 8
        and phase_a_plan["raw_capture_count"] == 32
        and phase_a_plan["freeze_marker_count"] == 8,
        "Phase A inert plan changed",
    )
    _validate_boundary_and_cleanliness(manifest)
    return {
        "status": "pass",
        "program": "p15-v3",
        "attempt_id": "p15-v3-attempt-001",
        "capture_authorized": False,
        "policy": "B",
        "ablation": [0.0, 0.04],
        "fresh_slots": "sealed_unreleased_capture_unauthorized",
        "click": "conditional_carry_forward_sealed_unopened",
        "v2_artifacts_verified": old["artifacts"],
        "v2_captures_verified": old["captures"],
    }


def validate_skeleton(manifest_path: Path = MANIFEST_PATH) -> dict[str, Any]:
    _require(manifest_path.resolve() == MANIFEST_PATH.resolve(), "only the frozen v3 manifest is accepted")
    _require(_sha256(manifest_path) == MANIFEST_SHA256, "v3 manifest digest mismatch")
    return validate_manifest_payload(_read_json(manifest_path))


def _main(argv: Sequence[str] | None = None) -> int:
    effective_argv = list(sys.argv[1:] if argv is None else argv)
    if effective_argv and effective_argv[0] == "_phase-a-worker":
        _require(len(effective_argv) == 4, "Phase A worker arguments changed")
        return _phase_a_worker_main(
            Path(effective_argv[1]),
            int(effective_argv[2]),
            int(effective_argv[3]),
        )
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=("validate-skeleton", "capture", "capture-hash", "online", "oracle"),
        nargs="?",
        default="validate-skeleton",
    )
    args = parser.parse_args(effective_argv)
    if args.command != "validate-skeleton":
        raise ValidationError(f"{args.command} is forbidden: the v3 skeleton has no capture path")
    print(json.dumps(validate_skeleton(), sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(_main())
    except ValidationError as exc:
        print(f"P15_V3_VALIDATION_ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
