from __future__ import annotations

import argparse
import json
import re
import shutil
import sqlite3
import tempfile
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

from context_search_tool.config import DEFAULT_CONFIG
from context_search_tool.graph_contract import (
    RELATION_KINDS,
    RESOLUTION_STATES,
    RESOLVED_STATES,
    effective_relation_confidence,
)
from context_search_tool.graph_lifecycle import (
    FULL_REINDEX_REQUIRED_KEY,
    GRAPH_RESOLUTION_STATE_KEY,
    GRAPH_RESOLUTION_VERSION_KEY,
    GRAPH_STALE_REASON_KEY,
    PROJECT_UNIT_TOPOLOGY_FINGERPRINT_KEY,
    SIGNAL_SCHEMA_VERSION_KEY,
    read_graph_capability,
)
from context_search_tool.indexer import build_v5_index_snapshot
from context_search_tool.plugins import default_plugins
from context_search_tool.project_scope import PROJECT_SCOPE_METADATA_VERSION_KEY
from context_search_tool.scanner import scan_workspace_v5
from context_search_tool.sqlite_store import (
    FILE_WRITE_IN_PROGRESS_KEY,
    PRODUCER_RESOLUTION_GENERATION_KEY,
    TEST_ASSOCIATION_SOURCE_GENERATION_KEY,
    SQLiteStore,
)
from p5_graph_identity import (
    P5_MANIFEST_PATH,
    P5_REPOSITORIES,
    ROOT,
    assert_protected_inputs,
    canonical_json_bytes,
    load_input_manifest,
    source_inventory,
)


EXPECTED_DIRECTORY = ROOT / "tests/fixtures/p5-language-graphs/expected"
COMPATIBILITY_ALLOWLIST_NAME = "compatibility_allowlist.json"
PROJECTION_FILE_NAMES = tuple(f"{key}.json" for key in P5_REPOSITORIES)
EXPECTED_FILE_NAMES = (*PROJECTION_FILE_NAMES, COMPATIBILITY_ALLOWLIST_NAME)
PROJECTION_SCHEMA_VERSION = 1
RECOVERY_REPOSITORY_KEY = "p5_java_spring"
RECOVERY_FAULT_STAGE = "signals_persisted"

_PROJECTION_KEYS = {
    "schema_version",
    "repository_key",
    "schema",
    "readiness",
    "topology",
    "counts",
    "signals",
    "relations",
    "truncation",
    "module_invariants",
    "test_invariants",
    "incoming_sources",
    "forbidden_edges",
    "recovery",
}
_SCHEMA_KEYS = {"tables", "indexes"}
_READINESS_KEYS = {
    "signal_schema_version",
    "graph_resolution_version",
    "state",
    "stale_reason",
    "full_reindex_required",
    "topology_fingerprint",
    "producer_resolution_generation",
    "test_association_source_generation",
    "file_write_in_progress",
    "project_scope_metadata_version",
}
_TOPOLOGY_KEYS = {"fingerprint", "project_units"}
_COUNT_KEYS = {
    "source_files",
    "active_chunks",
    "deleted_chunks",
    "active_signals",
    "deleted_signals",
    "active_relations",
    "deleted_relations",
    "signals_by_kind",
    "relations_by_kind",
    "relations_by_resolution",
}
_SIGNAL_KEYS = {
    "signal_id",
    "chunk_id",
    "file_path",
    "kind",
    "name",
    "qualified_name",
    "signature",
    "arity",
    "project_unit_key",
    "producer",
    "start_line",
    "end_line",
    "start_column",
    "end_column",
    "language",
    "recallable",
}
_RELATION_KEYS = {
    "relation_id",
    "kind",
    "producer",
    "source",
    "selector",
    "state",
    "target",
    "confidence",
    "occurrence",
}
_RELATION_SOURCE_KEYS = {
    "signal_id",
    "chunk_id",
    "file_path",
    "kind",
    "qualified_name",
}
_RELATION_SELECTOR_KEYS = {
    "target_name",
    "target_kind",
    "target_qualified_name",
    "target_signature",
    "target_arity",
    "target_project_unit_key",
    "selector_state",
    "candidates",
}
_RELATION_TARGET_KEYS = {
    "signal_id",
    "file_path",
    "kind",
    "qualified_name",
}
_CONFIDENCE_KEYS = {"stored", "producer", "resolution", "effective"}
_OCCURRENCE_KEYS = {
    "first_source_line",
    "first_source_column",
    "occurrence_count",
}
_TRUNCATION_KEYS = {"file_path", "counts"}
_TRUNCATION_COUNT_KEYS = {"key", "count"}
_MODULE_INVARIANT_KEYS = {
    "active_chunk_file_count",
    "module_count",
    "missing_paths",
    "duplicate_paths",
    "invalid_identity_paths",
    "root_unit_paths",
}
_TEST_INVARIANT_KEYS = {
    "classified_test_paths",
    "associations",
    "non_test_source_relation_ids",
    "test_target_relation_ids",
    "cross_unit_relation_ids",
    "unresolved_relation_ids",
}
_TEST_ASSOCIATION_KEYS = {
    "relation_id",
    "source_path",
    "target_path",
    "resolution",
    "resolution_basis",
    "occurrence_count",
}
_INCOMING_KEYS = {"target_signal_id", "target_path", "sources"}
_INCOMING_SOURCE_KEYS = {"relation_id", "kind", "source_signal_id", "source_path"}
_FORBIDDEN_KEYS = {"id", "relation_ids"}
_RECOVERY_KEYS = {
    "exercised",
    "fault_stage",
    "fault_state",
    "fault_full_reindex_required",
    "recovery_summary",
    "final_matches_fresh",
    "verified_noop_summary",
}
_SUMMARY_KEYS = {
    "files_seen",
    "files_indexed",
    "files_skipped",
    "files_deleted",
    "chunks_indexed",
}
_ALLOWLIST_ENTRY_KEYS = {
    "profile",
    "case_id",
    "path",
    "before_rank",
    "after_rank",
    "relation_id",
    "relation_kind",
    "direction",
    "why_legal",
}
_EXPECTED_SIGNAL_COLUMNS = [
    "signal_id",
    "chunk_id",
    "file_path",
    "kind",
    "name",
    "qualified_name",
    "signature",
    "arity",
    "project_unit_key",
    "producer",
    "start_line",
    "end_line",
    "start_column",
    "end_column",
    "language",
    "recallable",
    "tokens",
    "metadata",
    "deleted_at",
]
_EXPECTED_RELATION_COLUMNS = [
    "relation_id",
    "source_signal_id",
    "source_chunk_id",
    "source_file_path",
    "target_name",
    "kind",
    "confidence",
    "target_kind",
    "target_qualified_name",
    "target_signature",
    "target_arity",
    "target_project_unit_key",
    "target_signal_id",
    "resolution",
    "producer",
    "producer_confidence",
    "resolution_confidence",
    "metadata",
    "deleted_at",
]
_EXPECTED_SIGNAL_INDEXES = [
    "idx_code_signals_arity_active",
    "idx_code_signals_chunk_active",
    "idx_code_signals_file_active",
    "idx_code_signals_recallable_active",
    "idx_code_signals_selector_active",
]
_EXPECTED_RELATION_INDEXES = [
    "idx_code_relations_resolution_active",
    "idx_code_relations_source_active",
    "idx_code_relations_target_active",
    "idx_code_relations_target_signal_active",
]


@dataclass(frozen=True)
class _ForbiddenEdge:
    edge_id: str
    source_paths: tuple[str, ...]
    kinds: tuple[str, ...]
    target_paths: tuple[str, ...] = ()
    resolved_only: bool = True
    cross_unit_only: bool = False


_GENERIC_FORBIDDEN_TARGETS = (
    "java/src/main/java/com/example/contest/Contest.java",
    "java/src/main/java/com/example/generated/ArchiveWorker.java",
    "go/testdata/archive.go",
    "rust/src/generated/archive.rs",
    "python/src/generated/archive.py",
    "javascript/src/generated/archive.js",
    "typescript/src/generated/archive.ts",
)

FORBIDDEN_EDGES: dict[str, tuple[_ForbiddenEdge, ...]] = {
    "p5_java_spring": (
        _ForbiddenEdge(
            "ambiguous-same-arity-overload",
            ("src/main/java/com/example/order/OverloadCaller.java",),
            ("calls",),
            ("src/main/java/com/example/order/OverloadService.java",),
        ),
        _ForbiddenEdge(
            "unrelated-test-association",
            ("src/test/java/com/example/order/UnrelatedWorkerTests.java",),
            ("tests",),
        ),
        _ForbiddenEdge(
            "cross-unit-nested-test-association",
            ("nested/src/test/java/com/example/check/NestedOwnerCheck.java",),
            ("tests",),
        ),
        _ForbiddenEdge(
            "cross-unit-resolved-edge",
            (),
            tuple(RELATION_KINDS),
            cross_unit_only=True,
        ),
    ),
    "p5_vue": (
        _ForbiddenEdge(
            "ambiguous-extension-import",
            ("src/AmbiguousImporter.ts",),
            ("imports",),
            ("src/Ambiguous.js", "src/Ambiguous.ts"),
        ),
        _ForbiddenEdge(
            "ambiguous-index-import",
            ("src/IndexTieImporter.ts",),
            ("imports",),
            ("src/tied/index.js", "src/tied/index.ts"),
        ),
        _ForbiddenEdge(
            "repository-escape-import",
            ("src/EscapeImporter.ts",),
            ("imports",),
        ),
        _ForbiddenEdge(
            "shadowed-vue-router-binding",
            ("src/router/shadowed.ts",),
            ("routes_to",),
            resolved_only=False,
        ),
    ),
    "p5_react": (
        _ForbiddenEdge(
            "shadowed-react-router-binding",
            ("src/shadowedRoutes.tsx",),
            ("routes_to",),
            resolved_only=False,
        ),
    ),
    "p5_generic_tests": (
        _ForbiddenEdge(
            "generated-and-data-test-targets",
            (),
            ("tests",),
            _GENERIC_FORBIDDEN_TARGETS,
        ),
        _ForbiddenEdge(
            "generated-test-source-association",
            (
                "go/testdata/archive_test.go",
                "java/src/test/java/com/example/generated/ArchiveWorkerITCase.java",
                "javascript/tests/generated/archive.test.js",
                "python/tests/generated/test_archive.py",
                "rust/tests/generated/archive.rs",
                "typescript/src/__tests__/generated/archive.spec.ts",
            ),
            ("tests",),
            resolved_only=False,
        ),
    ),
    "p5_malformed_compat": (
        _ForbiddenEdge(
            "malformed-frontend-import",
            ("src/frontend/MalformedFrontend.ts",),
            ("imports",),
            ("src/frontend/FakeFrontendTarget.ts",),
            resolved_only=False,
        ),
        _ForbiddenEdge(
            "malformed-mybatis-mapping",
            (
                "src/main/resources/mappers/FakeTagMapper.xml",
                "src/main/resources/mappers/InternalSubsetMapper.xml",
                "src/main/resources/mappers/MalformedMapper.xml",
                "src/main/resources/mappers/XIncludeMapper.xml",
                "src/main/resources/mappers/XxeMapper.xml",
            ),
            ("mapped_by",),
            resolved_only=False,
        ),
        _ForbiddenEdge(
            "malformed-java-derived-edge",
            ("src/main/java/com/example/broken/MalformedJava.java",),
            tuple(RELATION_KINDS),
            resolved_only=False,
        ),
        _ForbiddenEdge(
            "custom-framework-annotation-edge",
            (
                "src/main/java/com/example/custom/LocalController.java",
                "src/main/java/com/example/custom/LocalMapper.java",
                "src/main/java/com/example/custom/LocalRepository.java",
                "src/main/java/com/example/custom/LocalService.java",
            ),
            tuple(RELATION_KINDS),
            resolved_only=False,
        ),
    ),
}


def _manifest_is_valid(path: Path) -> None:
    if path.is_symlink() or not path.is_file():
        raise RuntimeError("P5 input manifest must be a regular file")
    raw = path.read_bytes()
    try:
        parsed = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimeError("invalid P5 input manifest JSON") from error
    if not isinstance(parsed, dict) or set(parsed) != {
        "assays",
        "evidence",
        "excluded_outputs",
        "implementation_baseline",
        "inputs",
        "inventory",
        "protected_inputs",
        "schema_version",
    }:
        raise RuntimeError("P5 input manifest has unexpected keys")
    if raw != canonical_json_bytes(parsed):
        raise RuntimeError("P5 input manifest is not canonical JSON")
    if raw != P5_MANIFEST_PATH.read_bytes():
        raise RuntimeError("P5 input manifest differs from the frozen manifest")
    manifest = load_input_manifest(path)
    assert_protected_inputs()
    if source_inventory() != {
        key: tuple(value)
        for key, value in manifest["inventory"].items()
    }:
        raise RuntimeError("P5 source inventory changed")


def _summary(summary: Any) -> dict[str, int]:
    return {key: int(value) for key, value in asdict(summary).items()}


def _index(repo: Path, *, reverse_order: bool, fault_hook: Any = None) -> Any:
    plugins = default_plugins()

    def scanner(path: Path, config: Any) -> list[Any]:
        scanned = scan_workspace_v5(path, config)
        return list(reversed(scanned)) if reverse_order else scanned

    if reverse_order:
        plugins.reverse()
    return build_v5_index_snapshot(
        repo,
        DEFAULT_CONFIG,
        graph_plugins=plugins,
        scanner=scanner,
        fault_hook=fault_hook,
    )


def _connect(repo: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(repo / ".context-search/index.sqlite")
    connection.row_factory = sqlite3.Row
    return connection


def _metadata(connection: sqlite3.Connection) -> dict[str, str]:
    return {
        str(row["key"]): str(row["value"])
        for row in connection.execute(
            "SELECT key, value FROM index_metadata ORDER BY key"
        )
    }


def _table_columns(connection: sqlite3.Connection, table: str) -> list[str]:
    return [
        str(row["name"])
        for row in connection.execute(f"PRAGMA table_info({table})")
    ]


def _table_indexes(connection: sqlite3.Connection, table: str) -> list[str]:
    return sorted(
        str(row["name"])
        for row in connection.execute(f"PRAGMA index_list({table})")
        if not str(row["name"]).startswith("sqlite_autoindex_")
    )


def _json_object(value: str, label: str) -> dict[str, Any]:
    decoded = json.loads(value)
    if not isinstance(decoded, dict):
        raise RuntimeError(f"{label} metadata must be a JSON object")
    return decoded


def _int_metadata(metadata: dict[str, str], key: str) -> int:
    try:
        return int(metadata[key])
    except (KeyError, TypeError, ValueError) as error:
        raise RuntimeError(f"invalid graph metadata: {key}") from error


def _count_map(rows: Iterable[sqlite3.Row], key: str) -> dict[str, int]:
    counts = Counter(str(row[key]) for row in rows)
    return dict(sorted(counts.items()))


def _stable_float(value: object) -> float | None:
    if value is None:
        return None
    return float(value)


def _signal_projection(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "signal_id": str(row["signal_id"]),
        "chunk_id": str(row["chunk_id"]),
        "file_path": str(row["file_path"]),
        "kind": str(row["kind"]),
        "name": str(row["name"]),
        "qualified_name": str(row["qualified_name"]),
        "signature": str(row["signature"]),
        "arity": int(row["arity"]) if row["arity"] is not None else None,
        "project_unit_key": str(row["project_unit_key"]),
        "producer": str(row["producer"]),
        "start_line": int(row["start_line"]),
        "end_line": int(row["end_line"]),
        "start_column": int(row["start_column"]),
        "end_column": int(row["end_column"]),
        "language": str(row["language"]),
        "recallable": bool(row["recallable"]),
    }


def _relation_projection(row: sqlite3.Row) -> dict[str, Any]:
    metadata = _json_object(str(row["metadata"]), "relation")
    resolution = str(row["resolution"])
    target_signal_id = str(row["target_signal_id"])
    producer_confidence = float(row["producer_confidence"])
    resolution_confidence = _stable_float(row["resolution_confidence"])
    effective = effective_relation_confidence(
        resolution=resolution,
        target_signal_id=target_signal_id,
        producer_confidence=producer_confidence,
        resolution_confidence=resolution_confidence,
    )
    stored = float(row["confidence"])
    if stored != effective:
        raise RuntimeError(f"stored relation confidence mismatch: {row['relation_id']}")
    candidates = metadata.get("candidates", ())
    if not isinstance(candidates, (list, tuple)) or not all(
        isinstance(item, str) for item in candidates
    ):
        raise RuntimeError("relation candidates must be a string sequence")
    occurrence = {
        "first_source_line": int(metadata.get("first_source_line", 0)),
        "first_source_column": int(metadata.get("first_source_column", 0)),
        "occurrence_count": int(metadata.get("occurrence_count", 1)),
    }
    if occurrence["first_source_line"] < 0 or occurrence["first_source_column"] < 0:
        raise RuntimeError("relation occurrence position must not be negative")
    if occurrence["occurrence_count"] < 1:
        raise RuntimeError("relation occurrence count must be positive")
    return {
        "relation_id": str(row["relation_id"]),
        "kind": str(row["kind"]),
        "producer": str(row["producer"]),
        "source": {
            "signal_id": str(row["source_signal_id"]),
            "chunk_id": str(row["source_chunk_id"]),
            "file_path": str(row["source_file_path"]),
            "kind": str(row["source_kind"]),
            "qualified_name": str(row["source_qualified_name"]),
        },
        "selector": {
            "target_name": str(row["target_name"]),
            "target_kind": str(row["target_kind"]),
            "target_qualified_name": str(row["target_qualified_name"]),
            "target_signature": str(row["target_signature"]),
            "target_arity": (
                int(row["target_arity"])
                if row["target_arity"] is not None
                else None
            ),
            "target_project_unit_key": str(row["target_project_unit_key"]),
            "selector_state": metadata.get("selector_state"),
            "candidates": sorted(set(candidates)),
        },
        "state": resolution,
        "target": {
            "signal_id": target_signal_id,
            "file_path": (
                str(row["target_file_path"])
                if row["target_file_path"] is not None
                else None
            ),
            "kind": (
                str(row["target_signal_kind"])
                if row["target_signal_kind"] is not None
                else None
            ),
            "qualified_name": (
                str(row["target_signal_qualified_name"])
                if row["target_signal_qualified_name"] is not None
                else None
            ),
        },
        "confidence": {
            "stored": stored,
            "producer": producer_confidence,
            "resolution": resolution_confidence,
            "effective": effective,
        },
        "occurrence": occurrence,
    }


def _omitted_counts(
    value: Any,
    prefix: str = "",
    *,
    within_omitted: bool = False,
) -> list[dict[str, Any]]:
    counts: list[dict[str, Any]] = []
    if isinstance(value, dict):
        for key in sorted(value):
            item = value[key]
            path = f"{prefix}.{key}" if prefix else key
            item_is_omitted = within_omitted or "omitted" in key
            if item_is_omitted and isinstance(item, int) and not isinstance(item, bool):
                counts.append({"key": path, "count": item})
            else:
                counts.extend(
                    _omitted_counts(
                        item,
                        path,
                        within_omitted=item_is_omitted,
                    )
                )
    elif isinstance(value, list):
        for index, item in enumerate(value):
            counts.extend(
                _omitted_counts(
                    item,
                    f"{prefix}[{index}]",
                    within_omitted=within_omitted,
                )
            )
    return counts


def _topology_projection(
    source_rows: list[sqlite3.Row],
    fingerprint: str,
) -> dict[str, Any]:
    units: dict[str, dict[str, Any]] = {}
    for row in source_rows:
        metadata = _json_object(str(row["metadata"]), "source file")
        key = str(metadata.get("project_root", ""))
        unit = {
            "key": key,
            "kind": str(metadata.get("project_kind", "generic")),
            "languages": sorted(metadata.get("project_languages", [])),
            "markers": sorted(metadata.get("project_markers", [])),
        }
        previous = units.setdefault(key, unit)
        if previous != unit:
            raise RuntimeError(f"inconsistent project unit metadata: {key}")
    return {
        "fingerprint": fingerprint,
        "project_units": [units[key] for key in sorted(units)],
    }


def _module_invariants(
    connection: sqlite3.Connection,
    source_rows: list[sqlite3.Row],
    signal_rows: list[sqlite3.Row],
) -> dict[str, Any]:
    active_chunk_paths = {
        str(row["file_path"])
        for row in connection.execute(
            "SELECT DISTINCT file_path FROM chunks WHERE deleted_at IS NULL"
        )
    }
    modules_by_path: dict[str, list[sqlite3.Row]] = {}
    for row in signal_rows:
        if row["kind"] == "module" and row["producer"] == "core_module":
            modules_by_path.setdefault(str(row["file_path"]), []).append(row)
    missing = sorted(active_chunk_paths - modules_by_path.keys())
    duplicates = sorted(
        path for path, rows in modules_by_path.items() if len(rows) != 1
    )
    source_metadata = {
        str(row["path"]): _json_object(str(row["metadata"]), "source file")
        for row in source_rows
    }
    invalid: list[str] = []
    root_unit_paths: list[str] = []
    for path, rows in sorted(modules_by_path.items()):
        if len(rows) != 1:
            continue
        row = rows[0]
        unit_key = str(source_metadata[path].get("project_root", ""))
        if unit_key == "":
            root_unit_paths.append(path)
        if any(
            (
                str(row["qualified_name"]) != path,
                str(row["name"]) != path,
                bool(row["recallable"]),
                str(row["project_unit_key"]) != unit_key,
            )
        ):
            invalid.append(path)
    result = {
        "active_chunk_file_count": len(active_chunk_paths),
        "module_count": sum(len(rows) for rows in modules_by_path.values()),
        "missing_paths": missing,
        "duplicate_paths": duplicates,
        "invalid_identity_paths": invalid,
        "root_unit_paths": sorted(root_unit_paths),
    }
    if missing or duplicates or invalid:
        raise RuntimeError("module invariants failed")
    return result


def _test_invariants(
    source_rows: list[sqlite3.Row],
    relation_rows: list[sqlite3.Row],
) -> dict[str, Any]:
    classified = {
        str(row["path"]): bool(row["is_test"])
        for row in source_rows
    }
    associations: list[dict[str, Any]] = []
    non_test_sources: list[str] = []
    test_targets: list[str] = []
    cross_unit: list[str] = []
    unresolved: list[str] = []
    for row in relation_rows:
        if str(row["kind"]) != "tests":
            continue
        relation_id = str(row["relation_id"])
        source_path = str(row["source_file_path"])
        target_path = (
            str(row["target_file_path"])
            if row["target_file_path"] is not None
            else None
        )
        metadata = _json_object(str(row["metadata"]), "test relation")
        associations.append(
            {
                "relation_id": relation_id,
                "source_path": source_path,
                "target_path": target_path,
                "resolution": str(row["resolution"]),
                "resolution_basis": metadata.get("resolution_basis"),
                "occurrence_count": int(metadata.get("occurrence_count", 1)),
            }
        )
        if not classified.get(source_path, False):
            non_test_sources.append(relation_id)
        if target_path is not None and classified.get(target_path, False):
            test_targets.append(relation_id)
        if str(row["source_project_unit_key"]) != str(
            row["target_project_unit_key"]
        ):
            cross_unit.append(relation_id)
        if str(row["resolution"]) not in RESOLVED_STATES:
            unresolved.append(relation_id)
    result = {
        "classified_test_paths": sorted(
            path for path, is_test in classified.items() if is_test
        ),
        "associations": sorted(
            associations,
            key=lambda item: (
                item["source_path"],
                item["target_path"] or "",
                item["relation_id"],
            ),
        ),
        "non_test_source_relation_ids": sorted(non_test_sources),
        "test_target_relation_ids": sorted(test_targets),
        "cross_unit_relation_ids": sorted(cross_unit),
        "unresolved_relation_ids": sorted(unresolved),
    }
    if any((non_test_sources, test_targets, cross_unit, unresolved)):
        raise RuntimeError("test association invariants failed")
    return result


def _incoming_sources(relation_rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, str]]] = {}
    for row in relation_rows:
        if str(row["resolution"]) not in RESOLVED_STATES:
            continue
        target_signal_id = str(row["target_signal_id"])
        target_path = str(row["target_file_path"])
        grouped.setdefault((target_signal_id, target_path), []).append(
            {
                "relation_id": str(row["relation_id"]),
                "kind": str(row["kind"]),
                "source_signal_id": str(row["source_signal_id"]),
                "source_path": str(row["source_file_path"]),
            }
        )
    return [
        {
            "target_signal_id": target_signal_id,
            "target_path": target_path,
            "sources": sorted(
                sources,
                key=lambda item: (
                    item["kind"], item["source_path"], item["relation_id"]
                ),
            ),
        }
        for (target_signal_id, target_path), sources in sorted(grouped.items())
    ]


def _forbidden_edges(
    repository_key: str,
    relation_rows: list[sqlite3.Row],
) -> list[dict[str, Any]]:
    projected: list[dict[str, Any]] = []
    for spec in FORBIDDEN_EDGES[repository_key]:
        matches: list[str] = []
        for row in relation_rows:
            if (
                spec.source_paths
                and str(row["source_file_path"]) not in spec.source_paths
            ):
                continue
            if str(row["kind"]) not in spec.kinds:
                continue
            if spec.target_paths and row["target_file_path"] not in spec.target_paths:
                continue
            if spec.resolved_only and str(row["resolution"]) not in RESOLVED_STATES:
                continue
            if spec.cross_unit_only and str(row["source_project_unit_key"]) == str(
                row["target_project_unit_key"]
            ):
                continue
            matches.append(str(row["relation_id"]))
        projected.append({"id": spec.edge_id, "relation_ids": sorted(matches)})
    violations = [item for item in projected if item["relation_ids"]]
    if violations:
        raise RuntimeError(f"forbidden graph edge present: {violations[0]['id']}")
    return projected


def _snapshot_projection(repository_key: str, repo: Path) -> dict[str, Any]:
    store = SQLiteStore(repo / ".context-search/index.sqlite")
    capability = read_graph_capability(store)
    integrity = store.graph_integrity()
    if capability.status != "ready" or not capability.structured or not integrity.ok:
        raise RuntimeError("structural projection requires one ready v5 snapshot")

    with _connect(repo) as connection:
        metadata = _metadata(connection)
        source_rows = list(
            connection.execute("SELECT * FROM source_files ORDER BY path")
        )
        signal_rows = list(
            connection.execute(
                """
                SELECT * FROM code_signals
                WHERE deleted_at IS NULL
                ORDER BY file_path, start_line, start_column, end_line, end_column,
                         kind, qualified_name, signature, signal_id
                """
            )
        )
        relation_rows = list(
            connection.execute(
                """
                SELECT relations.*,
                       sources.kind AS source_kind,
                       sources.qualified_name AS source_qualified_name,
                       sources.project_unit_key AS source_project_unit_key,
                       targets.file_path AS target_file_path,
                       targets.kind AS target_signal_kind,
                       targets.qualified_name AS target_signal_qualified_name
                FROM code_relations AS relations
                JOIN code_signals AS sources
                  ON sources.signal_id = relations.source_signal_id
                 AND sources.deleted_at IS NULL
                LEFT JOIN code_signals AS targets
                  ON targets.signal_id = relations.target_signal_id
                 AND targets.deleted_at IS NULL
                WHERE relations.deleted_at IS NULL
                ORDER BY relations.source_file_path, relations.kind,
                         relations.source_signal_id, relations.target_signal_id,
                         relations.relation_id
                """
            )
        )
        fingerprint = metadata.get(PROJECT_UNIT_TOPOLOGY_FINGERPRINT_KEY, "")
        truncation = []
        for row in source_rows:
            source_metadata = _json_object(str(row["metadata"]), "source file")
            truncation.append(
                {
                    "file_path": str(row["path"]),
                    "counts": _omitted_counts(source_metadata),
                }
            )

        projection: dict[str, Any] = {
            "schema_version": PROJECTION_SCHEMA_VERSION,
            "repository_key": repository_key,
            "schema": {
                "tables": {
                    table: _table_columns(connection, table)
                    for table in ("code_signals", "code_relations")
                },
                "indexes": {
                    table: _table_indexes(connection, table)
                    for table in ("code_signals", "code_relations")
                },
            },
            "readiness": {
                "signal_schema_version": _int_metadata(
                    metadata, SIGNAL_SCHEMA_VERSION_KEY
                ),
                "graph_resolution_version": _int_metadata(
                    metadata, GRAPH_RESOLUTION_VERSION_KEY
                ),
                "state": metadata.get(GRAPH_RESOLUTION_STATE_KEY, ""),
                "stale_reason": metadata.get(GRAPH_STALE_REASON_KEY, ""),
                "full_reindex_required": (
                    metadata.get(FULL_REINDEX_REQUIRED_KEY) == "1"
                ),
                "topology_fingerprint": fingerprint,
                "producer_resolution_generation": _int_metadata(
                    metadata, PRODUCER_RESOLUTION_GENERATION_KEY
                ),
                "test_association_source_generation": _int_metadata(
                    metadata, TEST_ASSOCIATION_SOURCE_GENERATION_KEY
                ),
                "file_write_in_progress": metadata.get(
                    FILE_WRITE_IN_PROGRESS_KEY, ""
                ),
                "project_scope_metadata_version": _int_metadata(
                    metadata, PROJECT_SCOPE_METADATA_VERSION_KEY
                ),
            },
            "topology": _topology_projection(source_rows, fingerprint),
            "counts": {
                "source_files": len(source_rows),
                "active_chunks": int(
                    connection.execute(
                        "SELECT COUNT(*) FROM chunks WHERE deleted_at IS NULL"
                    ).fetchone()[0]
                ),
                "deleted_chunks": int(
                    connection.execute(
                        "SELECT COUNT(*) FROM chunks WHERE deleted_at IS NOT NULL"
                    ).fetchone()[0]
                ),
                "active_signals": len(signal_rows),
                "deleted_signals": int(
                    connection.execute(
                        "SELECT COUNT(*) FROM code_signals WHERE deleted_at IS NOT NULL"
                    ).fetchone()[0]
                ),
                "active_relations": len(relation_rows),
                "deleted_relations": int(
                    connection.execute(
                        "SELECT COUNT(*) FROM code_relations "
                        "WHERE deleted_at IS NOT NULL"
                    ).fetchone()[0]
                ),
                "signals_by_kind": _count_map(signal_rows, "kind"),
                "relations_by_kind": _count_map(relation_rows, "kind"),
                "relations_by_resolution": _count_map(
                    relation_rows, "resolution"
                ),
            },
            "signals": [_signal_projection(row) for row in signal_rows],
            "relations": [_relation_projection(row) for row in relation_rows],
            "truncation": truncation,
            "module_invariants": _module_invariants(
                connection, source_rows, signal_rows
            ),
            "test_invariants": _test_invariants(source_rows, relation_rows),
            "incoming_sources": _incoming_sources(relation_rows),
            "forbidden_edges": _forbidden_edges(repository_key, relation_rows),
            "recovery": {
                "exercised": False,
                "fault_stage": None,
                "fault_state": None,
                "fault_full_reindex_required": None,
                "recovery_summary": None,
                "final_matches_fresh": None,
                "verified_noop_summary": None,
            },
        }
    return projection


def _fresh_projection(repository_key: str, *, reverse_order: bool) -> dict[str, Any]:
    source = ROOT / P5_REPOSITORIES[repository_key]
    with tempfile.TemporaryDirectory(prefix=f"cst-p5-graph-{repository_key}-") as temp:
        repo = Path(temp) / "repo"
        shutil.copytree(source, repo)
        _index(repo, reverse_order=reverse_order)
        return _snapshot_projection(repository_key, repo)


def _recovery_projection(
    repository_key: str,
    fresh: dict[str, Any],
    *,
    reverse_order: bool,
) -> dict[str, Any]:
    source = ROOT / P5_REPOSITORIES[repository_key]
    with tempfile.TemporaryDirectory(prefix="cst-p5-graph-recovery-") as temp:
        repo = Path(temp) / "repo"
        shutil.copytree(source, repo)

        fault_seen = False

        def fail(stage: str) -> None:
            nonlocal fault_seen
            if stage == RECOVERY_FAULT_STAGE and not fault_seen:
                fault_seen = True
                raise RuntimeError("expected structural projection fault")

        try:
            _index(repo, reverse_order=reverse_order, fault_hook=fail)
        except RuntimeError as error:
            if str(error) != "expected structural projection fault":
                raise
        else:
            raise RuntimeError("recovery fault hook did not run")
        store = SQLiteStore(repo / ".context-search/index.sqlite")
        fault_capability = read_graph_capability(store)
        if (
            fault_capability.status != "stale"
            or not fault_capability.full_reindex_required
        ):
            raise RuntimeError("fault did not leave a recoverable full-reindex marker")

        recovery_summary = _summary(_index(repo, reverse_order=reverse_order))
        recovered = _snapshot_projection(repository_key, repo)
        verified_noop = _summary(_index(repo, reverse_order=reverse_order))
        if recovered != fresh:
            raise RuntimeError(
                "recovered structural projection differs from fresh index"
            )
        if verified_noop["files_indexed"] != 0:
            raise RuntimeError(
                "recovered snapshot did not take the verified no-op path"
            )
        return {
            "exercised": True,
            "fault_stage": RECOVERY_FAULT_STAGE,
            "fault_state": fault_capability.status,
            "fault_full_reindex_required": fault_capability.full_reindex_required,
            "recovery_summary": recovery_summary,
            "final_matches_fresh": True,
            "verified_noop_summary": verified_noop,
        }


def build_repository_projection(
    repository_key: str,
    *,
    reverse_order: bool = False,
) -> dict[str, Any]:
    if repository_key not in P5_REPOSITORIES:
        raise ValueError(f"unknown P5 repository key: {repository_key}")
    projection = _fresh_projection(repository_key, reverse_order=reverse_order)
    if repository_key == RECOVERY_REPOSITORY_KEY:
        projection["recovery"] = _recovery_projection(
            repository_key,
            projection,
            reverse_order=reverse_order,
        )
    _validate_projection(projection, repository_key)
    canonical_json_bytes(projection)
    return projection


def _require_keys(value: Any, expected: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != expected:
        raise RuntimeError(f"{label} has unexpected keys")
    return value


def _require_dict_of_ints(
    value: Any,
    label: str,
    allowed: set[str] | None,
) -> None:
    if not isinstance(value, dict) or (
        allowed is not None and not set(value) <= allowed
    ):
        raise RuntimeError(f"{label} has unexpected keys")
    if any(
        not isinstance(item, int) or isinstance(item, bool) or item < 0
        for item in value.values()
    ):
        raise RuntimeError(f"{label} requires non-negative integer counts")


def _validate_projection(value: Any, repository_key: str) -> None:
    projection = _require_keys(value, _PROJECTION_KEYS, "projection")
    if projection["schema_version"] != PROJECTION_SCHEMA_VERSION:
        raise RuntimeError("unexpected structural projection schema")
    if projection["repository_key"] != repository_key:
        raise RuntimeError("structural projection repository key mismatch")
    schema = _require_keys(projection["schema"], _SCHEMA_KEYS, "schema")
    if schema["tables"] != {
        "code_signals": _EXPECTED_SIGNAL_COLUMNS,
        "code_relations": _EXPECTED_RELATION_COLUMNS,
    }:
        raise RuntimeError("structural projection table inventory changed")
    if schema["indexes"] != {
        "code_signals": _EXPECTED_SIGNAL_INDEXES,
        "code_relations": _EXPECTED_RELATION_INDEXES,
    }:
        raise RuntimeError("structural projection index inventory changed")
    readiness = _require_keys(
        projection["readiness"], _READINESS_KEYS, "readiness"
    )
    if readiness["signal_schema_version"] != 5:
        raise RuntimeError("structural projection must use schema v5")
    if readiness["graph_resolution_version"] != 1:
        raise RuntimeError("structural projection graph resolution version changed")
    if readiness["state"] != "ready" or readiness["stale_reason"] != "":
        raise RuntimeError("structural projection must be ready")
    if readiness["full_reindex_required"] is not False:
        raise RuntimeError("ready projection cannot require a full reindex")
    if readiness["file_write_in_progress"] != "":
        raise RuntimeError("ready projection cannot retain a file-write marker")
    if readiness["producer_resolution_generation"] < 1 or (
        readiness["test_association_source_generation"]
        != readiness["producer_resolution_generation"]
    ):
        raise RuntimeError("graph resolver generation markers are inconsistent")
    if readiness["project_scope_metadata_version"] != 1:
        raise RuntimeError("project scope metadata version changed")
    topology = _require_keys(projection["topology"], _TOPOLOGY_KEYS, "topology")
    if not re.fullmatch(r"[0-9a-f]{64}", topology["fingerprint"]):
        raise RuntimeError("topology fingerprint must be a full SHA-256")
    if readiness["topology_fingerprint"] != topology["fingerprint"]:
        raise RuntimeError("readiness and topology fingerprints differ")
    unit_keys: list[str] = []
    for unit in topology["project_units"]:
        _require_keys(unit, {"key", "kind", "languages", "markers"}, "project unit")
        unit_keys.append(unit["key"])
        if unit["languages"] != sorted(set(unit["languages"])) or unit[
            "markers"
        ] != sorted(set(unit["markers"])):
            raise RuntimeError("project unit values must be uniquely sorted")
    if unit_keys != sorted(set(unit_keys)):
        raise RuntimeError("project units must be uniquely sorted")
    counts = _require_keys(projection["counts"], _COUNT_KEYS, "counts")
    for key in _COUNT_KEYS - {
        "signals_by_kind",
        "relations_by_kind",
        "relations_by_resolution",
    }:
        if (
            not isinstance(counts[key], int)
            or isinstance(counts[key], bool)
            or counts[key] < 0
        ):
            raise RuntimeError(f"structural count must be non-negative: {key}")
    _require_dict_of_ints(counts["signals_by_kind"], "signal counts", None)
    _require_dict_of_ints(
        counts["relations_by_kind"], "relation kind counts", set(RELATION_KINDS)
    )
    _require_dict_of_ints(
        counts["relations_by_resolution"],
        "relation resolution counts",
        set(RESOLUTION_STATES),
    )
    signal_ids: set[str] = set()
    signal_by_id: dict[str, dict[str, Any]] = {}
    signal_order: list[tuple[object, ...]] = []
    for signal in projection["signals"]:
        _require_keys(signal, _SIGNAL_KEYS, "signal")
        signal_id = signal["signal_id"]
        if not isinstance(signal_id, str) or not signal_id or signal_id in signal_ids:
            raise RuntimeError("signal IDs must be non-empty and unique")
        signal_ids.add(signal_id)
        signal_by_id[signal_id] = signal
        if signal["project_unit_key"] not in unit_keys:
            raise RuntimeError("signal refers to an unknown project unit")
        if not isinstance(signal["recallable"], bool):
            raise RuntimeError("signal recallable must be boolean")
        if any(
            not isinstance(signal[key], int)
            or isinstance(signal[key], bool)
            or signal[key] < (1 if key in {"start_line", "end_line"} else 0)
            for key in ("start_line", "end_line", "start_column", "end_column")
        ):
            raise RuntimeError("signal ranges are invalid")
        signal_order.append(
            (
                signal["file_path"],
                signal["start_line"],
                signal["start_column"],
                signal["end_line"],
                signal["end_column"],
                signal["kind"],
                signal["qualified_name"],
                signal["signature"],
                signal_id,
            )
        )
    if signal_order != sorted(signal_order):
        raise RuntimeError("signals must use canonical identity order")
    if counts["active_signals"] != len(projection["signals"]):
        raise RuntimeError("active signal count differs from projection")
    if counts["signals_by_kind"] != dict(
        sorted(Counter(item["kind"] for item in projection["signals"]).items())
    ):
        raise RuntimeError("signal kind counts differ from projection")
    relation_ids: set[str] = set()
    relation_order: list[tuple[object, ...]] = []
    for relation in projection["relations"]:
        _require_keys(relation, _RELATION_KEYS, "relation")
        relation_id = relation["relation_id"]
        if (
            not isinstance(relation_id, str)
            or not relation_id
            or relation_id in relation_ids
        ):
            raise RuntimeError("relation IDs must be non-empty and unique")
        relation_ids.add(relation_id)
        if (
            relation["kind"] not in RELATION_KINDS
            or relation["state"] not in RESOLUTION_STATES
        ):
            raise RuntimeError("relation vocabulary is not closed")
        source = _require_keys(
            relation["source"], _RELATION_SOURCE_KEYS, "relation source"
        )
        selector = _require_keys(
            relation["selector"], _RELATION_SELECTOR_KEYS, "relation selector"
        )
        target = _require_keys(
            relation["target"], _RELATION_TARGET_KEYS, "relation target"
        )
        confidence = _require_keys(
            relation["confidence"], _CONFIDENCE_KEYS, "relation confidence"
        )
        occurrence = _require_keys(
            relation["occurrence"], _OCCURRENCE_KEYS, "relation occurrence"
        )
        source_signal = signal_by_id.get(source["signal_id"])
        if source_signal is None or source != {
            "signal_id": source_signal["signal_id"],
            "chunk_id": source_signal["chunk_id"],
            "file_path": source_signal["file_path"],
            "kind": source_signal["kind"],
            "qualified_name": source_signal["qualified_name"],
        }:
            raise RuntimeError("relation source identity differs from its signal")
        if selector["target_project_unit_key"] not in unit_keys:
            raise RuntimeError("relation selector refers to an unknown project unit")
        if selector["candidates"] != sorted(set(selector["candidates"])):
            raise RuntimeError("relation candidates must be uniquely sorted")
        if relation["state"] in RESOLVED_STATES:
            target_signal = signal_by_id.get(target["signal_id"])
            if target_signal is None or target != {
                "signal_id": target_signal["signal_id"],
                "file_path": target_signal["file_path"],
                "kind": target_signal["kind"],
                "qualified_name": target_signal["qualified_name"],
            }:
                raise RuntimeError("resolved relation target identity is invalid")
        elif target != {
            "signal_id": "",
            "file_path": None,
            "kind": None,
            "qualified_name": None,
        }:
            raise RuntimeError("unresolved relation must not retain a target")
        effective = effective_relation_confidence(
            resolution=relation["state"],
            target_signal_id=target["signal_id"],
            producer_confidence=confidence["producer"],
            resolution_confidence=confidence["resolution"],
        )
        if confidence["stored"] != effective or confidence["effective"] != effective:
            raise RuntimeError("relation confidence components are inconsistent")
        if any(
            not isinstance(occurrence[key], int)
            or isinstance(occurrence[key], bool)
            or occurrence[key] < (1 if key == "occurrence_count" else 0)
            for key in _OCCURRENCE_KEYS
        ):
            raise RuntimeError("relation occurrence metadata is invalid")
        relation_order.append(
            (
                source["file_path"],
                relation["kind"],
                source["signal_id"],
                target["signal_id"],
                relation_id,
            )
        )
    if relation_order != sorted(relation_order):
        raise RuntimeError("relations must use canonical identity order")
    if counts["active_relations"] != len(projection["relations"]):
        raise RuntimeError("active relation count differs from projection")
    if counts["relations_by_kind"] != dict(
        sorted(Counter(item["kind"] for item in projection["relations"]).items())
    ):
        raise RuntimeError("relation kind counts differ from projection")
    if counts["relations_by_resolution"] != dict(
        sorted(Counter(item["state"] for item in projection["relations"]).items())
    ):
        raise RuntimeError("relation resolution counts differ from projection")
    truncation_paths: list[str] = []
    for item in projection["truncation"]:
        _require_keys(item, _TRUNCATION_KEYS, "truncation")
        truncation_paths.append(item["file_path"])
        count_keys: list[str] = []
        for count in item["counts"]:
            _require_keys(count, _TRUNCATION_COUNT_KEYS, "truncation count")
            count_keys.append(count["key"])
            if (
                not isinstance(count["count"], int)
                or isinstance(count["count"], bool)
                or count["count"] < 0
            ):
                raise RuntimeError("truncation counts must be non-negative")
        if count_keys != sorted(set(count_keys)):
            raise RuntimeError("truncation keys must be uniquely sorted")
    if truncation_paths != sorted(set(truncation_paths)) or len(
        truncation_paths
    ) != counts["source_files"]:
        raise RuntimeError("truncation projection must cover each source file once")
    modules = _require_keys(
        projection["module_invariants"],
        _MODULE_INVARIANT_KEYS,
        "module invariants",
    )
    if any(
        modules[key]
        for key in ("missing_paths", "duplicate_paths", "invalid_identity_paths")
    ) or modules["module_count"] != modules["active_chunk_file_count"]:
        raise RuntimeError("module invariants are not closed")
    tests = _require_keys(
        projection["test_invariants"], _TEST_INVARIANT_KEYS, "test invariants"
    )
    for association in tests["associations"]:
        _require_keys(association, _TEST_ASSOCIATION_KEYS, "test association")
    if tests["classified_test_paths"] != sorted(
        set(tests["classified_test_paths"])
    ) or any(
        tests[key]
        for key in (
            "non_test_source_relation_ids",
            "test_target_relation_ids",
            "cross_unit_relation_ids",
            "unresolved_relation_ids",
        )
    ):
        raise RuntimeError("test association invariants are not closed")
    for incoming in projection["incoming_sources"]:
        _require_keys(incoming, _INCOMING_KEYS, "incoming target")
        for source in incoming["sources"]:
            _require_keys(source, _INCOMING_SOURCE_KEYS, "incoming source")
    expected_incoming: dict[tuple[str, str], list[dict[str, str]]] = {}
    for relation in projection["relations"]:
        if relation["state"] not in RESOLVED_STATES:
            continue
        target_key = (
            relation["target"]["signal_id"],
            relation["target"]["file_path"],
        )
        expected_incoming.setdefault(target_key, []).append(
            {
                "relation_id": relation["relation_id"],
                "kind": relation["kind"],
                "source_signal_id": relation["source"]["signal_id"],
                "source_path": relation["source"]["file_path"],
            }
        )
    normalized_incoming = [
        {
            "target_signal_id": target_signal_id,
            "target_path": target_path,
            "sources": sorted(
                sources,
                key=lambda item: (
                    item["kind"], item["source_path"], item["relation_id"]
                ),
            ),
        }
        for (target_signal_id, target_path), sources in sorted(
            expected_incoming.items()
        )
    ]
    if projection["incoming_sources"] != normalized_incoming:
        raise RuntimeError("incoming-source projection differs from resolved edges")
    expected_forbidden_ids = [item.edge_id for item in FORBIDDEN_EDGES[repository_key]]
    if [
        item.get("id") for item in projection["forbidden_edges"]
    ] != expected_forbidden_ids:
        raise RuntimeError("forbidden-edge inventory changed")
    for forbidden in projection["forbidden_edges"]:
        _require_keys(forbidden, _FORBIDDEN_KEYS, "forbidden edge")
        if forbidden["relation_ids"]:
            raise RuntimeError("structural projection contains a forbidden edge")
    recovery = _require_keys(projection["recovery"], _RECOVERY_KEYS, "recovery")
    if recovery["exercised"]:
        _require_keys(recovery["recovery_summary"], _SUMMARY_KEYS, "recovery summary")
        _require_keys(
            recovery["verified_noop_summary"], _SUMMARY_KEYS, "no-op summary"
        )
        if repository_key != RECOVERY_REPOSITORY_KEY:
            raise RuntimeError("recovery projection belongs to the wrong repository")
        if any(
            (
                recovery["fault_stage"] != RECOVERY_FAULT_STAGE,
                recovery["fault_state"] != "stale",
                recovery["fault_full_reindex_required"] is not True,
                recovery["final_matches_fresh"] is not True,
                recovery["recovery_summary"]["files_indexed"]
                != recovery["recovery_summary"]["files_seen"],
                recovery["verified_noop_summary"]["files_indexed"] != 0,
            )
        ):
            raise RuntimeError("full-rebuild recovery markers are inconsistent")
    elif any(
        value is not None
        for key, value in recovery.items()
        if key != "exercised"
    ):
        raise RuntimeError("unexercised recovery must not contain markers")
    elif repository_key == RECOVERY_REPOSITORY_KEY:
        raise RuntimeError("Java projection must exercise full-rebuild recovery")
    _assert_environment_free(projection)


def _assert_environment_free(value: Any, *, key: str = "") -> None:
    forbidden_keys = {
        "generated_at",
        "indexed_at",
        "latency_ms",
        "mtime_ns",
        "workspace",
        "absolute_path",
        "vector",
        "parser",
    }
    if isinstance(value, dict):
        for item_key, item in value.items():
            if item_key in forbidden_keys:
                raise RuntimeError(f"unstable structural projection key: {item_key}")
            _assert_environment_free(item, key=item_key)
    elif isinstance(value, list):
        for item in value:
            _assert_environment_free(item, key=key)
    elif isinstance(value, str):
        if (
            str(ROOT) in value
            or value.startswith("/private/")
            or value.startswith("/tmp/")
        ):
            raise RuntimeError(
                f"absolute path leaked into structural projection: {key}"
            )


def validate_compatibility_allowlist(value: Any) -> None:
    if not isinstance(value, list):
        raise RuntimeError("compatibility allowlist must be a JSON array")
    sort_keys: list[tuple[object, ...]] = []
    for entry in value:
        item = _require_keys(
            entry,
            _ALLOWLIST_ENTRY_KEYS,
            "compatibility allowlist entry",
        )
        for key in ("profile", "case_id", "path", "relation_id", "why_legal"):
            if not isinstance(item[key], str) or not item[key]:
                raise RuntimeError(f"compatibility allowlist {key} must be non-empty")
        path = Path(item["path"])
        if (
            path.is_absolute()
            or ".." in path.parts
            or path.as_posix() != item["path"]
        ):
            raise RuntimeError(
                "compatibility allowlist path must be repository-relative"
            )
        before_rank = item["before_rank"]
        after_rank = item["after_rank"]
        if before_rank is not None and (
            isinstance(before_rank, bool)
            or not isinstance(before_rank, int)
            or before_rank < 1
        ):
            raise RuntimeError(
                "compatibility allowlist before_rank must be null or positive"
            )
        if (
            isinstance(after_rank, bool)
            or not isinstance(after_rank, int)
            or after_rank < 1
        ):
            raise RuntimeError("compatibility allowlist after_rank must be positive")
        if item["relation_kind"] not in RELATION_KINDS:
            raise RuntimeError("compatibility allowlist relation kind is unknown")
        if item["direction"] not in {"incoming", "outgoing"}:
            raise RuntimeError("compatibility allowlist direction is unknown")
        if not re.fullmatch(r"r5:[0-9a-f]{64}", item["relation_id"]):
            raise RuntimeError("compatibility allowlist relation ID must be v5")
        sort_keys.append(
            (
                item["profile"],
                item["case_id"],
                item["after_rank"],
                item["path"],
                item["relation_id"],
                item["direction"],
            )
        )
    if sort_keys != sorted(sort_keys) or len(sort_keys) != len(set(sort_keys)):
        raise RuntimeError("compatibility allowlist must be uniquely sorted")
    _assert_environment_free(value)


def _write_new_directory(output_dir: Path, files: dict[str, bytes]) -> None:
    if output_dir.exists() or output_dir.is_symlink():
        raise RuntimeError(f"refusing to overwrite output directory: {output_dir}")
    if set(files) != set(EXPECTED_FILE_NAMES):
        raise RuntimeError("structural output file inventory changed")
    output_dir.mkdir(parents=True)
    for name in EXPECTED_FILE_NAMES:
        (output_dir / name).write_bytes(files[name])


def project(
    manifest: Path,
    output_dir: Path,
    *,
    reverse_order: bool = False,
) -> None:
    _manifest_is_valid(manifest)
    fixture_root = (ROOT / "tests/fixtures/p5-language-graphs").resolve()
    resolved_output = output_dir.resolve(strict=False)
    if resolved_output == fixture_root or fixture_root in resolved_output.parents:
        raise RuntimeError(
            "project output must be a candidate directory outside frozen fixtures"
        )
    files = {
        f"{repository_key}.json": canonical_json_bytes(
            build_repository_projection(
                repository_key,
                reverse_order=reverse_order,
            )
        )
        for repository_key in P5_REPOSITORIES
    }
    files[COMPATIBILITY_ALLOWLIST_NAME] = canonical_json_bytes([])
    _write_new_directory(output_dir, files)


def _candidate_files(directory: Path) -> dict[str, bytes]:
    if directory.is_symlink() or not directory.is_dir():
        raise RuntimeError("candidate must be a regular directory")
    paths = list(directory.iterdir())
    if any(path.is_symlink() or not path.is_file() for path in paths):
        raise RuntimeError("candidate contains a non-regular file")
    if {path.name for path in paths} != set(EXPECTED_FILE_NAMES):
        raise RuntimeError("candidate has unexpected files")
    files: dict[str, bytes] = {}
    for name in EXPECTED_FILE_NAMES:
        raw = (directory / name).read_bytes()
        try:
            value = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise RuntimeError(f"invalid candidate JSON: {name}") from error
        if raw != canonical_json_bytes(value):
            raise RuntimeError(f"candidate is not canonical JSON: {name}")
        if name == COMPATIBILITY_ALLOWLIST_NAME:
            validate_compatibility_allowlist(value)
        else:
            repository_key = name.removesuffix(".json")
            _validate_projection(value, repository_key)
        files[name] = raw
    return files


def initialize(
    manifest: Path,
    candidate_a: Path,
    candidate_b: Path,
    output_dir: Path,
) -> None:
    _manifest_is_valid(manifest)
    fixture_root = (ROOT / "tests/fixtures/p5-language-graphs").resolve()
    resolved_output = output_dir.resolve(strict=False)
    if (
        fixture_root in resolved_output.parents
        and resolved_output != EXPECTED_DIRECTORY.resolve(strict=False)
    ):
        raise RuntimeError("initializer may write only the reviewed expected directory")
    if candidate_a.resolve() == candidate_b.resolve():
        raise RuntimeError("initializer requires two independent candidate directories")
    first = _candidate_files(candidate_a)
    second = _candidate_files(candidate_b)
    if first != second:
        raise RuntimeError("structural projection candidates differ")
    _write_new_directory(output_dir, first)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate frozen P5 graph projections")
    subparsers = parser.add_subparsers(dest="command", required=True)
    project_parser = subparsers.add_parser("project")
    project_parser.add_argument("--manifest", type=Path, required=True)
    project_parser.add_argument("--output-dir", type=Path, required=True)
    project_parser.add_argument("--reverse-order", action="store_true")
    initialize_parser = subparsers.add_parser("initialize")
    initialize_parser.add_argument("--manifest", type=Path, required=True)
    initialize_parser.add_argument("--candidate-a", type=Path, required=True)
    initialize_parser.add_argument("--candidate-b", type=Path, required=True)
    initialize_parser.add_argument("--output-dir", type=Path, required=True)
    return parser


def main() -> int:
    args = _parser().parse_args()
    if args.command == "project":
        project(
            args.manifest,
            args.output_dir,
            reverse_order=args.reverse_order,
        )
    else:
        initialize(
            args.manifest,
            args.candidate_a,
            args.candidate_b,
            args.output_dir,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
