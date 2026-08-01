"""P15 product-free oracle and paired acceptance harness.

The Task-0 oracle overlays resolved exact-symbol relations only after a fresh
baseline index is built.  It intentionally does not import P15 product code:
syntax extraction is stdlib AST and target lookup is a closed SQLite query.
"""

from __future__ import annotations

import argparse
import ast
from collections.abc import Iterator, Sequence
from contextlib import contextmanager, nullcontext
from copy import deepcopy
from dataclasses import replace
import hashlib
import importlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import tomllib
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "tests/fixtures/p15_python_import_symbols/input_manifest.json"
DEFAULT_SOURCES = ROOT / ".quality/p14-sources"
ONLINE_PROVIDER = "openai-compatible"
ONLINE_MODEL = "Pro/BAAI/bge-m3"
ONLINE_DIMENSIONS = 1024
ONLINE_BASE_URL = "https://api.siliconflow.cn/v1"
_SHA256 = re.compile(r"[0-9a-f]{64}")
_TERMINAL_STATES = frozenset(
    {
        "not_representable",
        "no_exact_signal",
        "ambiguous_signal",
        "resolved_not_traversed",
        "acquired_below_ranking",
        "ranked_not_selected",
        "selected_wrong_chunk",
        "selected_exact_declaration_chunk",
    }
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _read_json(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("JSON root must be an object")
    return payload


def _require_sha(value: object, label: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ValueError(f"{label} must be a lowercase SHA-256")
    return value


def _resolve_tracked(path_value: object) -> Path:
    if not isinstance(path_value, str) or not path_value:
        raise ValueError("manifest path must be repository-relative")
    path = Path(path_value)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("manifest path must be repository-relative")
    return ROOT / path


def _privacy_check(value: object, *, key: str = "root") -> None:
    forbidden_keys = {
        "api_key",
        "password",
        "credential",
        "credentials",
        "secret",
        "source_body",
        "raw_exception",
        "access_token",
        "auth_token",
    }
    if isinstance(value, dict):
        for child_key, child in value.items():
            if not isinstance(child_key, str) or child_key.lower() in forbidden_keys:
                raise ValueError(f"privacy-forbidden field at {key}")
            _privacy_check(child, key=f"{key}.{child_key}")
        return
    if isinstance(value, list):
        for index, child in enumerate(value):
            _privacy_check(child, key=f"{key}[{index}]")
        return
    if isinstance(value, str):
        if value.startswith(
            (
                "/Users/",
                "/home/",
                "/tmp/",
                "C:\\Users\\",
                "\\\\",
                "file://",
            )
        ):
            raise ValueError(f"absolute local path at {key}")
        if "-----BEGIN" in value or re.search(r"sk-[A-Za-z0-9]{12,}", value):
            raise ValueError(f"credential-like value at {key}")


def validate_manifest(path: Path) -> dict:
    manifest = _read_json(path)
    expected_root = {
        "schema_version",
        "attempt_id",
        "behavior_baseline",
        "design_sha256",
        "plan_sha256",
        "development_gold",
        "sources",
        "heldout_seal",
        "r1",
        "r2",
        "online",
        "closed_world_rule",
    }
    if set(manifest) != expected_root or manifest["schema_version"] != 1:
        raise ValueError("P15 manifest schema is not closed")
    if manifest["attempt_id"] != "p15-v1-attempt-003":
        raise ValueError("P15 attempt ID is not frozen")
    if manifest["behavior_baseline"] != "5f56de2e1b57ed7f1ec0ee9a513b508461d78233":
        raise ValueError("P15 behavior baseline changed")
    hashes = {
        "design_sha256": ROOT / "docs/superpowers/specs/2026-07-31-p15-python-exact-imported-symbol-relations-design.md",
        "plan_sha256": ROOT / "docs/superpowers/plans/2026-07-31-p15-python-exact-imported-symbol-relations.md",
    }
    for field, target in hashes.items():
        if _require_sha(manifest[field], field) != _sha256(target):
            raise ValueError(f"{field} changed")

    gold = manifest["development_gold"]
    if not isinstance(gold, dict) or set(gold) != {"path", "sha256"}:
        raise ValueError("development gold identity is invalid")
    gold_path = _resolve_tracked(gold["path"])
    if _require_sha(gold["sha256"], "development gold") != _sha256(gold_path):
        raise ValueError("development gold changed")
    gold_payload = _read_json(gold_path)
    sources = manifest["sources"]
    if not isinstance(sources, dict) or set(sources) != {"redink", "daily", "click"}:
        raise ValueError("source roles are incomplete")
    for repository in ("redink", "daily"):
        source = sources[repository]
        frozen = gold_payload["sources"][repository]
        if source.get("role") != "development" or any(
            source.get(field) != frozen[field]
            for field in (
                "url",
                "commit",
                "selected_count",
                "inventory_sha256",
                "content_sha256",
            )
        ):
            raise ValueError(f"{repository} source identity changed")

    seal = manifest["heldout_seal"]
    if not isinstance(seal, dict) or seal.get("seal_id") != "p15-heldout-click-00e592c-v2":
        raise ValueError("held-out seal v2 is required")
    if seal.get("status") != "sealed_unopened":
        raise ValueError("held-out payload opened before Task 6")
    contract_path = _resolve_tracked(seal.get("public_contract_path"))
    cipher_path = _resolve_tracked(seal.get("sealed_payload_path"))
    if _require_sha(seal.get("public_contract_sha256"), "public contract") != _sha256(contract_path):
        raise ValueError("held-out public contract changed")
    if _require_sha(seal.get("sealed_ciphertext_sha256"), "sealed payload") != _sha256(cipher_path):
        raise ValueError("held-out ciphertext changed")
    contract = _read_json(contract_path)
    if set(contract) != {
        "schema_version",
        "seal_id",
        "sealed_at_utc",
        "reviewer_role",
        "status",
        "source",
        "heldout_contract",
        "sealed_payload",
        "predecessor",
    } or contract.get("schema_version") != 1:
        raise ValueError("held-out public contract schema is not closed")
    if contract.get("seal_id") != seal["seal_id"] or contract.get("status") != "sealed_unopened":
        raise ValueError("held-out public contract is invalid")
    public_source = contract.get("source")
    click = sources["click"]
    if not isinstance(public_source, dict) or click.get("role") != "heldout" or any(
        click.get(field) != public_source.get(field)
        for field in (
            "url",
            "commit",
            "tree",
            "license_spdx",
            "license_sha256",
            "selected_count",
            "inventory_sha256",
            "content_sha256",
        )
    ):
        raise ValueError("held-out source identity changed")
    heldout = contract.get("heldout_contract")
    if not isinstance(heldout, dict) or any(
        seal.get(target) != heldout.get(source)
        for target, source in (
            ("case_count", "case_count"),
            ("required_item_denominator", "required_item_denominator"),
            ("top_k", "top_k"),
        )
    ):
        raise ValueError("held-out denominator changed")
    if seal["case_count"] < 4 or seal["required_item_denominator"] < 12:
        raise ValueError("held-out denominator is inadmissible")
    sealed_payload = contract.get("sealed_payload")
    if not isinstance(sealed_payload, dict) or any(
        seal.get(target) != sealed_payload.get(source)
        for target, source in (
            ("sealed_plaintext_sha256", "plaintext_sha256"),
            ("sealed_ciphertext_sha256", "ciphertext_sha256"),
        )
    ):
        raise ValueError("held-out payload digest changed")
    if set(sealed_payload) != {
        "path",
        "format",
        "cipher",
        "kdf",
        "iterations",
        "salted",
        "bytes",
        "plaintext_sha256",
        "ciphertext_sha256",
        "round_trip_verified",
        "decryption_material_location",
        "open_not_before",
    } or any(
        (
            sealed_payload.get("path") != seal["sealed_payload_path"],
            sealed_payload.get("format") != "openssl-enc",
            sealed_payload.get("cipher") != "aes-256-cbc",
            sealed_payload.get("kdf") != "pbkdf2-hmac-sha256",
            sealed_payload.get("iterations") != 600000,
            sealed_payload.get("salted") is not True,
            sealed_payload.get("bytes") != cipher_path.stat().st_size,
            sealed_payload.get("round_trip_verified") is not True,
            sealed_payload.get("decryption_material_location")
            != "reviewer_only_non_filesystem_store",
            sealed_payload.get("open_not_before")
            != "task6_after_candidate_freeze_and_development_hash_gate",
        )
    ):
        raise ValueError("held-out encryption contract changed")
    predecessor = contract.get("predecessor")
    if not isinstance(predecessor, dict) or predecessor.get("status") != "discarded_before_oracle":
        raise ValueError("held-out predecessor disposition changed")

    if manifest["r1"] != {
        "target_kind": "python_declaration",
        "target_signal_kinds": ["type", "function"],
        "relation_kind": "imports",
        "producer": "python_ast",
        "resolution_basis": "exact_python_imported_symbol",
    }:
        raise ValueError("R1 changed")
    r2 = manifest["r2"]
    expected_r2 = {
        "development_minimum_micro_recall_gain": 0.05,
        "development_minimum_new_required_items": 3,
        "development_minimum_distinct_cases": 3,
        "development_required_repository_spread": ["redink", "daily"],
        "heldout_minimum_new_required_items": 2,
        "heldout_minimum_distinct_cases": 2,
        "maximum_index_regression_ratio": 0.25,
        "maximum_query_regression_ratio": 0.1,
        "minimum_query_regression_seconds": 0.005,
        "required_loss_limit": 0,
        "noise_growth_limit": 0,
    }
    if r2 != expected_r2:
        raise ValueError("R2 changed")
    if manifest["online"] != {
        "provider": ONLINE_PROVIDER,
        "model": ONLINE_MODEL,
        "dimensions": ONLINE_DIMENSIONS,
        "base_url": ONLINE_BASE_URL,
        "planner_enabled": False,
        "tokens_per_minute": 240000,
        "tokens_per_request": 80000,
        "minimum_interval_seconds": 2.0,
        "batching": "p14-bounded-greedy-v1",
    }:
        raise ValueError("online identity or pacing changed")
    _privacy_check(manifest)
    return manifest


def _online_embedding_settings() -> dict[str, object]:
    override = os.environ.get("CST_GLOBAL_CONFIG_PATH")
    path = (
        Path(override).expanduser()
        if override
        else Path.home() / ".config/context-search/config.toml"
    )
    try:
        payload = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise ValueError("online embedding provider config is unavailable") from error
    embedding = payload.get("embedding")
    if not isinstance(embedding, dict):
        raise ValueError("online embedding provider config is unavailable")
    api_key = embedding.get("api_key")
    if (
        embedding.get("provider") != ONLINE_PROVIDER
        or embedding.get("model") != ONLINE_MODEL
        or embedding.get("dimensions") != ONLINE_DIMENSIONS
        or embedding.get("base_url") != ONLINE_BASE_URL
        or not isinstance(api_key, str)
        or not api_key
    ):
        raise ValueError("online embedding provider identity is not frozen")
    return {"api_key": api_key}


def _git(*arguments: str) -> str:
    return _git_at(ROOT, *arguments)


def _git_at(root: Path, *arguments: str) -> str:
    return subprocess.run(
        ("git", "-C", str(root), *arguments),
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _product_identity(manifest: dict, root: Path = ROOT) -> dict:
    baseline = manifest["behavior_baseline"]
    tracked = _git_at(
        root, "diff", "--binary", baseline, "--", "src/context_search_tool"
    )
    listed = _git_at(
        root,
        "ls-files",
        "--others",
        "--exclude-standard",
        "--",
        "src/context_search_tool",
    )
    untracked = {
        path: _sha256(root / path)
        for path in sorted(filter(None, listed.splitlines()))
    }
    identity_payload = {"tracked_diff": tracked, "untracked": untracked}
    return {
        "baseline": baseline,
        "head": _git_at(root, "rev-parse", "HEAD"),
        "tracked_diff_sha256": hashlib.sha256(tracked.encode("utf-8")).hexdigest(),
        "untracked": untracked,
        "product_tree_sha256": hashlib.sha256(
            _canonical(identity_payload).encode("utf-8")
        ).hexdigest(),
        "clean_against_baseline": not tracked and not untracked,
    }


def _module_name(path: str, unit: str) -> str:
    relative = path
    prefix = f"{unit.rstrip('/')}/" if unit else ""
    if prefix and relative.startswith(prefix):
        relative = relative[len(prefix) :]
    for suffix in (".py", ".pyw"):
        if relative.endswith(suffix):
            relative = relative[: -len(suffix)]
            break
    segments = relative.split("/")
    if len(segments) > 1 and segments[-1] == "__init__":
        segments.pop()
    elif segments == ["__init__"]:
        return "__init__"
    return ".".join(segments)


def _module_path_candidates(base: str) -> tuple[str, ...]:
    return (
        f"{base}.py",
        f"{base}.pyw",
        f"{base}/__init__.py",
        f"{base}/__init__.pyw",
    )


def _independent_module_selector(
    *,
    source_path: str,
    project_unit_key: str,
    module: str,
    relative_level: int,
    active_paths: dict[str, str],
) -> tuple[str, str, str | None]:
    """Closed product-free copy of the reviewed P8 module path rule."""
    specifier = "." * relative_level + module
    prefix = f"{project_unit_key.rstrip('/')}/" if project_unit_key else ""

    def active(candidates: Sequence[str]) -> tuple[str, ...]:
        return tuple(
            sorted(
                path
                for path in set(candidates)
                if active_paths.get(path) == project_unit_key
            )
        )

    if relative_level == 0:
        if not module:
            return "unresolved", specifier, None
        relative = module.replace(".", "/")
        candidates = active(
            tuple(
                candidate
                for base in (f"{prefix}{relative}", f"{prefix}src/{relative}")
                for candidate in _module_path_candidates(base)
            )
        )
        if len(candidates) == 1:
            return "exact", specifier, candidates[0]
        return ("ambiguous" if candidates else "external"), specifier, None

    inner = source_path[len(prefix) :] if prefix and source_path.startswith(prefix) else source_path
    segments = inner.split("/")
    stem = segments[-1]
    for suffix in (".py", ".pyw"):
        if stem.endswith(suffix):
            stem = stem[: -len(suffix)]
            break
    package = segments[:-1]
    remove = relative_level - 1
    if remove > len(package):
        return "unresolved", specifier, None
    base_segments = package[: len(package) - remove] if remove else package
    if not base_segments:
        if stem == "__init__" and not package and relative_level == 1 and module:
            candidates = active(_module_path_candidates(f"{prefix}{module.replace('.', '/')}"))
            if len(candidates) == 1:
                return "exact", specifier, candidates[0]
            return ("ambiguous" if candidates else "unresolved"), specifier, None
        return "unresolved", specifier, None
    if not module:
        return "unresolved", specifier, None
    target = "/".join((*base_segments, *module.split(".")))
    candidates = active(_module_path_candidates(f"{prefix}{target}"))
    if len(candidates) == 1:
        return "exact", specifier, candidates[0]
    return ("ambiguous" if candidates else "unresolved"), specifier, None


def _module_projection(connection: sqlite3.Connection) -> tuple[int, str]:
    rows = connection.execute(
        """
        SELECT relation_id, source_signal_id, target_signal_id, resolution,
               target_qualified_name, metadata
        FROM code_relations
        WHERE deleted_at IS NULL AND producer = 'python_ast'
          AND kind = 'imports' AND target_kind = 'module'
        ORDER BY relation_id
        """
    ).fetchall()
    rendered = _canonical([list(row) for row in rows]).encode("utf-8")
    return len(rows), hashlib.sha256(rendered).hexdigest()


def _non_python_projection(connection: sqlite3.Connection) -> str:
    rows = connection.execute(
        """
        SELECT signal_id, chunk_id, file_path, kind, qualified_name, producer,
               project_unit_key, language
        FROM code_signals
        WHERE deleted_at IS NULL AND language <> 'python'
        ORDER BY signal_id
        """
    ).fetchall()
    return hashlib.sha256(
        _canonical([list(row) for row in rows]).encode("utf-8")
    ).hexdigest()


def _work_cap_projection(connection: sqlite3.Connection) -> dict[str, int]:
    from context_search_tool import graph_contract

    maximum_outgoing = connection.execute(
        """
        SELECT COALESCE(MAX(count), 0) FROM (
          SELECT source_signal_id, COUNT(*) AS count
          FROM code_relations WHERE deleted_at IS NULL
          GROUP BY source_signal_id
        )
        """
    ).fetchone()[0]
    maximum_incoming = connection.execute(
        """
        SELECT COALESCE(MAX(count), 0) FROM (
          SELECT target_signal_id, COUNT(*) AS count
          FROM code_relations
          WHERE deleted_at IS NULL AND target_signal_id <> ''
          GROUP BY target_signal_id
        )
        """
    ).fetchone()[0]
    return {
        "max_graph_seed_signals": graph_contract.MAX_GRAPH_SEED_SIGNALS,
        "max_resolved_graph_hops": graph_contract.MAX_RESOLVED_GRAPH_HOPS,
        "max_edges_per_signal_direction": graph_contract.MAX_EDGES_PER_SIGNAL_DIRECTION,
        "max_relation_expanded_candidates": graph_contract.MAX_RELATION_EXPANDED_CANDIDATES,
        "observed_maximum_outgoing_rows": int(maximum_outgoing),
        "observed_maximum_incoming_rows": int(maximum_incoming),
    }


def _product_exact_projection(connection: sqlite3.Connection) -> dict:
    rows = connection.execute(
        """
        SELECT relations.relation_id, relations.source_signal_id,
               relations.metadata, targets.signal_id AS target_signal_id,
               targets.chunk_id AS target_chunk_id,
               targets.file_path AS target_file_path,
               targets.kind AS actual_target_kind,
               sources.chunk_id AS source_chunk_id
        FROM code_relations relations
        JOIN code_signals targets
          ON targets.signal_id = relations.target_signal_id
         AND targets.deleted_at IS NULL
        JOIN code_signals sources
          ON sources.signal_id = relations.source_signal_id
         AND sources.deleted_at IS NULL
        WHERE relations.deleted_at IS NULL
          AND relations.kind = 'imports'
          AND relations.producer = 'python_ast'
          AND relations.resolution = 'resolved_exact'
        ORDER BY relations.relation_id
        """
    ).fetchall()
    exact_targets: dict[str, list[dict]] = {}
    counts: dict[str, int] = {}
    for row in rows:
        metadata = json.loads(row["metadata"])
        if metadata.get("resolution_basis") != "exact_python_imported_symbol":
            continue
        source_signal_id = str(row["source_signal_id"])
        counts[source_signal_id] = counts.get(source_signal_id, 0) + 1
        target_file = str(row["target_file_path"])
        exact_targets.setdefault(target_file, []).append(
            {
                "relation_id": str(row["relation_id"]),
                "module_relation_id": str(metadata.get("module_relation_id", "")),
                "source_signal_id": source_signal_id,
                "source_chunk_id": str(row["source_chunk_id"]),
                "target_signal_id": str(row["target_signal_id"]),
                "target_chunk_id": str(row["target_chunk_id"]),
                "actual_target_kind": str(row["actual_target_kind"]),
            }
        )
    omitted = 0
    for (metadata_json,) in connection.execute(
        "SELECT metadata FROM chunks WHERE deleted_at IS NULL"
    ):
        metadata = json.loads(metadata_json)
        value = metadata.get("graph_omitted_imported_symbols", 0)
        if type(value) is int and value > 0:
            omitted += value
    module_count, module_sha = _module_projection(connection)
    return {
        "exact_relation_count": sum(counts.values()),
        "graph_omitted_imported_symbols": omitted,
        "omitted_by_source": {},
        "maximum_exact_relations_per_source": max(counts.values(), default=0),
        "terminal_counts": {"resolved": sum(counts.values())},
        "target_states": {
            path: {"resolved": len(values)}
            for path, values in exact_targets.items()
        },
        "exact_targets": exact_targets,
        "module_relation_count": module_count,
        "module_projection_sha256": module_sha,
    }


def _overlay_oracle(workspace: Path) -> dict:
    from context_search_tool.graph_contract import generate_v5_relation_id

    database = workspace / ".context-search/index.sqlite"
    with sqlite3.connect(database) as connection:
        connection.row_factory = sqlite3.Row
        before_count, before_sha = _module_projection(connection)
        relations: dict[str, dict] = {}
        target_states: dict[str, dict[str, int]] = {}
        terminal_counts = {
            "not_representable": 0,
            "no_exact_signal": 0,
            "ambiguous_signal": 0,
            "resolved": 0,
        }
        sources = connection.execute(
            """
            SELECT * FROM code_signals
            WHERE deleted_at IS NULL AND kind = 'module'
              AND producer = 'core_module'
              AND language = 'python'
              AND (file_path LIKE '%.py' OR file_path LIKE '%.pyw')
            ORDER BY project_unit_key, file_path, signal_id
            """
        ).fetchall()
        active_paths = {
            str(row["file_path"]): str(row["project_unit_key"])
            for row in sources
        }
        for source in sources:
            source_path = str(source["file_path"])
            absolute = workspace / source_path
            try:
                tree = compile(
                    absolute.read_bytes(),
                    source_path,
                    "exec",
                    flags=ast.PyCF_ONLY_AST | ast.PyCF_TYPE_COMMENTS,
                    dont_inherit=True,
                    optimize=0,
                )
            except (OSError, SyntaxError, UnicodeDecodeError, RecursionError, ValueError, TypeError):
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.ImportFrom) or not node.module:
                    continue
                selector_state, specifier, target_file = _independent_module_selector(
                    source_path=source_path,
                    project_unit_key=str(source["project_unit_key"]),
                    module=node.module,
                    relative_level=node.level or 0,
                    active_paths=active_paths,
                )
                for alias in node.names:
                    if alias.name == "*" or not alias.name.isidentifier():
                        continue
                    if selector_state != "exact" or target_file is None:
                        terminal_counts["not_representable"] += 1
                        continue
                    module_matches = connection.execute(
                        """
                        SELECT relations.*, targets.file_path AS target_file_path,
                               targets.project_unit_key AS actual_target_unit
                        FROM code_relations relations
                        JOIN code_signals targets
                          ON targets.signal_id = relations.target_signal_id
                         AND targets.deleted_at IS NULL
                        WHERE relations.deleted_at IS NULL
                          AND relations.source_signal_id = ?
                          AND relations.kind = 'imports'
                          AND relations.producer = 'python_ast'
                          AND relations.target_kind = 'module'
                          AND relations.resolution = 'resolved_exact'
                          AND targets.file_path = ?
                        ORDER BY relations.relation_id
                        LIMIT 2
                        """,
                        (source["signal_id"], target_file),
                    ).fetchall()
                    if len(module_matches) != 1:
                        terminal_counts["not_representable"] += 1
                        target_states.setdefault(target_file, {}).setdefault("not_representable", 0)
                        target_states[target_file]["not_representable"] += 1
                        continue
                    module_row = module_matches[0]
                    metadata = json.loads(module_row["metadata"])
                    if (
                        metadata.get("selector_state") != "exact"
                        or tuple(metadata.get("candidates", ())) != (target_file,)
                    ):
                        terminal_counts["not_representable"] += 1
                        target_states.setdefault(target_file, {}).setdefault("not_representable", 0)
                        target_states[target_file]["not_representable"] += 1
                        continue
                    target_unit = str(module_row["actual_target_unit"])
                    if target_unit != str(source["project_unit_key"]):
                        terminal_counts["not_representable"] += 1
                        continue
                    qualified_name = f"{_module_name(target_file, target_unit)}.{alias.name}"
                    matches = connection.execute(
                        """
                        SELECT * FROM code_signals
                        WHERE deleted_at IS NULL AND file_path = ?
                          AND project_unit_key = ? AND producer = 'python_ast'
                          AND language = 'python' AND kind IN ('type', 'function')
                          AND qualified_name = ?
                        ORDER BY kind, start_line, start_column, signal_id
                        LIMIT 3
                        """,
                        (target_file, target_unit, qualified_name),
                    ).fetchall()
                    if not matches:
                        terminal_counts["no_exact_signal"] += 1
                        target_states.setdefault(target_file, {}).setdefault("no_exact_signal", 0)
                        target_states[target_file]["no_exact_signal"] += 1
                        continue
                    if len(matches) != 1:
                        terminal_counts["ambiguous_signal"] += 1
                        target_states.setdefault(target_file, {}).setdefault("ambiguous_signal", 0)
                        target_states[target_file]["ambiguous_signal"] += 1
                        continue
                    target = matches[0]
                    relation_id = generate_v5_relation_id(
                        source_signal_id=str(source["signal_id"]),
                        kind="imports",
                        target_kind=str(target["kind"]),
                        target_qualified_name=qualified_name,
                        target_signature="",
                        target_arity=None,
                        target_project_unit_key=target_unit,
                        producer="python_ast",
                    )
                    local_name = alias.asname or alias.name
                    location = (int(node.lineno), int(node.col_offset))
                    existing = relations.get(relation_id)
                    if existing is None:
                        relations[relation_id] = {
                            "source": source,
                            "target": target,
                            "module_relation_id": str(module_row["relation_id"]),
                            "specifier": specifier,
                            "imported_name": alias.name,
                            "local_names": {local_name},
                            "relative_level": node.level or 0,
                            "location": location,
                            "occurrence_count": 1,
                        }
                    else:
                        existing["local_names"].add(local_name)
                        existing["occurrence_count"] += 1
                        existing["location"] = min(existing["location"], location)
                    terminal_counts["resolved"] += 1
                    target_states.setdefault(target_file, {}).setdefault("resolved", 0)
                    target_states[target_file]["resolved"] += 1

        retained: list[tuple[str, dict]] = []
        omitted_by_source: dict[str, int] = {}
        grouped: dict[str, list[tuple[str, dict]]] = {}
        for relation_id, item in relations.items():
            grouped.setdefault(str(item["source"]["signal_id"]), []).append((relation_id, item))
        for source_signal_id, rows in sorted(grouped.items()):
            ordered = sorted(
                rows,
                key=lambda pair: (
                    pair[1]["location"],
                    str(pair[1]["target"]["qualified_name"]),
                    pair[0],
                ),
            )
            retained.extend(ordered[:256])
            if len(ordered) > 256:
                omitted_by_source[source_signal_id] = len(ordered) - 256

        exact_targets: dict[str, list[dict]] = {}
        for relation_id, item in retained:
            source = item["source"]
            target = item["target"]
            line, column = item["location"]
            metadata = {
                "resolution_basis": "exact_python_imported_symbol",
                "selector_state": "exact",
                "target_file_path": str(target["file_path"]),
                "target_signal_kinds": ["type", "function"],
                "imported_name": item["imported_name"],
                "local_names": sorted(item["local_names"]),
                "relative_level": item["relative_level"],
                "first_source_line": line,
                "first_source_column": column,
                "occurrence_count": item["occurrence_count"],
                "module_relation_id": item["module_relation_id"],
                "module_selector": {
                    "state": "exact",
                    "specifier": item["specifier"],
                    "target_file_path": str(target["file_path"]),
                },
                "oracle_actual_target_kind": str(target["kind"]),
            }
            connection.execute(
                """
                INSERT INTO code_relations (
                    relation_id, source_signal_id, source_chunk_id,
                    source_file_path, target_name, kind, confidence,
                    target_kind, target_qualified_name, target_signature,
                    target_arity, target_project_unit_key, target_signal_id,
                    resolution, producer, producer_confidence,
                    resolution_confidence, metadata, deleted_at
                ) VALUES (?, ?, ?, ?, ?, 'imports', 1.0, ?, ?, '', NULL, ?, ?,
                          'resolved_exact', 'python_ast', 1.0, 1.0, ?, NULL)
                """,
                (
                    relation_id,
                    source["signal_id"],
                    source["chunk_id"],
                    source["file_path"],
                    item["imported_name"],
                    target["kind"],
                    target["qualified_name"],
                    target["project_unit_key"],
                    target["signal_id"],
                    json.dumps(metadata, ensure_ascii=False, sort_keys=True),
                ),
            )
            exact_targets.setdefault(str(target["file_path"]), []).append(
                {
                    "relation_id": relation_id,
                    "module_relation_id": item["module_relation_id"],
                    "source_signal_id": str(source["signal_id"]),
                    "source_chunk_id": str(source["chunk_id"]),
                    "target_signal_id": str(target["signal_id"]),
                    "target_chunk_id": str(target["chunk_id"]),
                    "actual_target_kind": str(target["kind"]),
                }
            )
        connection.commit()
        after_count, after_sha = _module_projection(connection)
    if (before_count, before_sha) != (after_count, after_sha):
        raise ValueError("oracle changed the P8 module relation projection")
    return {
        "exact_relation_count": len(retained),
        "graph_omitted_imported_symbols": sum(omitted_by_source.values()),
        "omitted_by_source": omitted_by_source,
        "maximum_exact_relations_per_source": max(
            (min(len(rows), 256) for rows in grouped.values()), default=0
        ),
        "terminal_counts": terminal_counts,
        "target_states": target_states,
        "exact_targets": exact_targets,
        "module_relation_count": before_count,
        "module_projection_sha256": before_sha,
    }


def _exact_witness(index_db: Path, selected_path: str, selected: dict) -> dict | None:
    if (
        "graph_imports_match" not in selected.get("score_parts", {})
        or "static module dependency" not in selected.get("reasons", [])
    ):
        return None
    with sqlite3.connect(index_db) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT relations.relation_id, relations.source_signal_id,
                   relations.target_signal_id,
                   targets.kind AS actual_target_kind,
                   relations.metadata, targets.chunk_id AS target_chunk_id,
                   targets.file_path AS target_file_path,
                   targets.start_line AS target_start_line,
                   targets.end_line AS target_end_line,
                   chunks.start_line AS chunk_start_line,
                   chunks.end_line AS chunk_end_line
            FROM code_relations relations
            JOIN code_signals targets
              ON targets.signal_id = relations.target_signal_id
             AND targets.deleted_at IS NULL
            JOIN chunks ON chunks.chunk_id = targets.chunk_id
                       AND chunks.deleted_at IS NULL
            WHERE relations.deleted_at IS NULL
              AND relations.kind = 'imports'
              AND relations.producer = 'python_ast'
              AND relations.resolution = 'resolved_exact'
              AND targets.file_path = ?
              AND targets.chunk_id = ?
            ORDER BY relations.relation_id
            """,
            (selected_path, selected["chunk_id"]),
        ).fetchall()
        for row in rows:
            metadata = json.loads(row["metadata"])
            if metadata.get("resolution_basis") != "exact_python_imported_symbol":
                continue
            if (
                str(row["target_chunk_id"]) != selected["chunk_id"]
                or int(row["chunk_start_line"]) > int(selected["end_line"])
                or int(row["chunk_end_line"]) < int(selected["start_line"])
            ):
                continue
            module_relation_id = metadata.get("module_relation_id")
            if not isinstance(module_relation_id, str):
                module = connection.execute(
                    """
                    SELECT modules.relation_id
                    FROM code_relations modules
                    JOIN code_signals module_targets
                      ON module_targets.signal_id = modules.target_signal_id
                    WHERE modules.deleted_at IS NULL
                      AND modules.source_signal_id = ?
                      AND modules.kind = 'imports'
                      AND modules.producer = 'python_ast'
                      AND modules.target_kind = 'module'
                      AND modules.resolution = 'resolved_exact'
                      AND module_targets.file_path = ?
                    ORDER BY modules.relation_id LIMIT 1
                    """,
                    (row["source_signal_id"], selected_path),
                ).fetchone()
                module_relation_id = str(module["relation_id"]) if module else ""
            witness = {
                "relation_id": str(row["relation_id"]),
                "module_relation_id": module_relation_id,
                "source_signal_id": str(row["source_signal_id"]),
                "target_signal_id": str(row["target_signal_id"]),
                "target_chunk_id": str(row["target_chunk_id"]),
                "target_file_path": str(row["target_file_path"]),
                "actual_target_kind": str(row["actual_target_kind"]),
                "target_start_line": int(row["target_start_line"]),
                "target_end_line": int(row["target_end_line"]),
            }
            if (
                not witness["module_relation_id"].startswith("r5:")
                or not witness["relation_id"].startswith("r5:")
                or not witness["source_signal_id"].startswith("s5:")
                or not witness["target_signal_id"].startswith("s5:")
                or witness["target_file_path"] != selected_path
            ):
                continue
            return witness
    return None


@contextmanager
def _observe_model_calls(counters: dict[str, int]) -> Iterator[None]:
    bge_module = importlib.import_module("context_search_tool.embeddings_bge")
    planner_module = importlib.import_module("context_search_tool.query_planner")
    original_bge = bge_module.BGEEmbeddingProvider.embed_texts
    original_ollama = planner_module.OllamaQueryPlanner.plan
    original_online_planner = planner_module.OpenAICompatibleQueryPlanner.plan

    def forbidden_bge(*_args, **_kwargs):
        counters["local_model_calls"] += 1
        raise RuntimeError("local model path is forbidden by P15")

    def forbidden_ollama(*_args, **_kwargs):
        counters["local_model_calls"] += 1
        counters["planner_calls"] += 1
        raise RuntimeError("local model path is forbidden by P15")

    def observed_online_planner(*args, **kwargs):
        counters["planner_calls"] += 1
        return original_online_planner(*args, **kwargs)

    bge_module.BGEEmbeddingProvider.embed_texts = forbidden_bge
    planner_module.OllamaQueryPlanner.plan = forbidden_ollama
    planner_module.OpenAICompatibleQueryPlanner.plan = observed_online_planner
    try:
        yield
    finally:
        bge_module.BGEEmbeddingProvider.embed_texts = original_bge
        planner_module.OllamaQueryPlanner.plan = original_ollama
        planner_module.OpenAICompatibleQueryPlanner.plan = original_online_planner


@contextmanager
def _count_online_requests(
    *,
    p14_runner,
    current_repository: dict[str, str | None],
    counts: dict[str, int],
) -> Iterator[None]:
    embeddings = importlib.import_module("context_search_tool.embeddings")
    provider_type = embeddings.OpenAICompatibleEmbeddingProvider
    original = provider_type.embed_texts
    history: list[tuple[float, int]] = []

    def counted(self, texts, *args, **kwargs):
        repository = current_repository["value"]
        if repository not in counts or repository == "total":
            raise ValueError("online embedding request has no corpus attribution")
        vectors = []
        for batch in p14_runner._online_embedding_batches(texts):
            p14_runner._wait_for_online_embedding_budget(
                history,
                p14_runner._online_embedding_token_estimate(batch),
            )
            counts[repository] += 1
            counts["total"] += 1
            vectors.extend(original(self, batch, *args, **kwargs))
        return vectors

    provider_type.embed_texts = counted
    try:
        yield
    finally:
        provider_type.embed_texts = original


def _capture_development(
    manifest_path: Path,
    *,
    run_root: Path,
    phase: str,
    corpora: str,
    profile: str,
    variant: str,
    repeat: int,
    input_order: str,
    implementation_root: Path = ROOT,
) -> dict:
    manifest = validate_manifest(manifest_path)
    sys.path.insert(0, str(ROOT / "tests"))
    p8_runner = importlib.import_module("p8_real_python_graphs_acceptance")
    p14_runner = importlib.import_module("p14_definition_owner_acceptance")
    identity = importlib.import_module("p8_python_graph_identity")
    config_module = importlib.import_module("context_search_tool.config")
    indexer = importlib.import_module("context_search_tool.indexer")
    retrieval = importlib.import_module("context_search_tool.retrieval")

    planner = config_module.QueryPlannerConfig(
        enabled=False,
        provider=ONLINE_PROVIDER,
        model="Qwen/Qwen2.5-14B-Instruct",
        base_url=ONLINE_BASE_URL,
        use_system_proxy=False,
        timeout_seconds=60.0,
        max_rewritten_queries=4,
        max_keywords=12,
        max_symbol_hints=8,
    )
    observed = {
        "local_model_calls": 0,
        "planner_calls": 0,
        "fallback_count": 0,
        "error_count": 0,
        "skip_count": 0,
        "retrieval_calls": 0,
    }
    if profile == "hash":
        config = replace(config_module.DEFAULT_CONFIG, query_planner=planner)
    elif profile == "online-bge":
        settings = _online_embedding_settings()
        embedding = config_module.replace_embedding_config(
            config_module.EmbeddingConfig(
                provider=ONLINE_PROVIDER,
                model=ONLINE_MODEL,
                dimensions=ONLINE_DIMENSIONS,
                base_url=ONLINE_BASE_URL,
            ),
            api_key=settings["api_key"],
        )
        config = replace(
            config_module.DEFAULT_CONFIG,
            embedding=embedding,
            query_planner=planner,
        )
    else:
        raise ValueError("unknown P15 capture profile")
    embeddings_module = importlib.import_module("context_search_tool.embeddings")
    fingerprint = embeddings_module.provider_from_config(config.embedding).fingerprint()
    expected_fingerprint = {
        "provider": config.embedding.provider,
        "model": config.embedding.model,
        "dimensions": config.embedding.dimensions,
    }
    if config.embedding.base_url is not None:
        expected_fingerprint["base_url"] = config.embedding.base_url
    if fingerprint != expected_fingerprint or config.query_planner.enabled:
        raise ValueError("effective provider fingerprint or planner state changed")

    development_gold = deepcopy(p8_runner._manifest_or_fail())
    opened_gold = (
        _read_json(run_root / "heldout/opened-payload.json")
        if corpora in {"heldout", "all"}
        else None
    )
    contract = _read_json(
        _resolve_tracked(manifest["heldout_seal"]["public_contract_path"])
    )
    heldout_source = contract["source"]
    heldout_spec = {
        "dir_name": "click",
        "patterns": tuple(heldout_source["include"]),
        "expected_count": heldout_source["selected_count"],
        "inventory_sha256": heldout_source["inventory_sha256"],
        "content_sha256": heldout_source["content_sha256"],
    }
    if corpora == "development":
        gold = development_gold
        source_specs = tuple(p8_runner.SOURCES.items())
        source_roots = {
            repository: DEFAULT_SOURCES
            for repository in p8_runner.SOURCES
        }
    elif corpora == "heldout" and phase == "candidate":
        gold = opened_gold
        contract = _read_json(_resolve_tracked(manifest["heldout_seal"]["public_contract_path"]))
        source_specs = (("click", heldout_spec),)
        source_roots = {"click": ROOT / ".quality/p15-sources"}
    elif corpora == "all" and phase == "candidate":
        if not isinstance(opened_gold, dict):
            raise ValueError("held-out payload is not opened")
        gold = {"cases": [*development_gold["cases"], *opened_gold["cases"]]}
        source_specs = (*tuple(p8_runner.SOURCES.items()), ("click", heldout_spec))
        source_roots = {
            **{repository: DEFAULT_SOURCES for repository in p8_runner.SOURCES},
            "click": ROOT / ".quality/p15-sources",
        }
    else:
        raise ValueError("capture corpus is not open")
    request_counts = {
        **{repository: 0 for repository, _spec in source_specs},
        "total": 0,
    }
    if input_order == "reverse":
        gold["cases"] = list(reversed(gold["cases"]))
    elif input_order != "canonical":
        raise ValueError("unknown input order")
    if input_order == "reverse":
        source_specs = tuple(reversed(source_specs))
    index_projections: dict[str, dict] = {}
    repositories: dict[str, dict] = {}
    cases: dict[str, dict] = {}
    timing = {"index_seconds": {}, "query_case_seconds": {}}
    workspaces: dict[str, Path] = {}
    current_repository: dict[str, str | None] = {"value": None}
    scratch = Path(tempfile.mkdtemp(prefix="cst-p15-capture-"))
    isolated = scratch / "isolated-global-config.toml"
    old_global = os.environ.get("CST_GLOBAL_CONFIG_PATH")
    os.environ["CST_GLOBAL_CONFIG_PATH"] = str(isolated)
    original_render_config = indexer.render_config

    def sanitized_render(selected_config):
        embedding = config_module.EmbeddingConfig(
            provider=selected_config.embedding.provider,
            model=selected_config.embedding.model,
            dimensions=selected_config.embedding.dimensions,
            base_url=selected_config.embedding.base_url,
            api_key_env=selected_config.embedding.api_key_env,
        )
        return original_render_config(replace(selected_config, embedding=embedding))

    indexer.render_config = sanitized_render
    try:
        counter = (
            _count_online_requests(
                p14_runner=p14_runner,
                current_repository=current_repository,
                counts=request_counts,
            )
            if profile == "online-bge"
            else nullcontext()
        )
        with _observe_model_calls(observed), counter:
            for repository, spec in source_specs:
                current_repository["value"] = repository
                source_root = source_roots[repository] / spec["dir_name"]
                files = identity.validate_protected_source(
                    source_root,
                    patterns=spec["patterns"],
                    expected_count=spec["expected_count"],
                    expected_inventory_sha256=spec["inventory_sha256"],
                    expected_content_sha256=spec["content_sha256"],
                )
                workspace = scratch / spec["dir_name"]
                materialization_order = (
                    tuple(reversed(files))
                    if input_order == "reverse"
                    else tuple(files)
                )
                for relative in materialization_order:
                    target = workspace / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source_root / relative, target)
                started = time.perf_counter()
                indexer.index_repository(workspace, config)
                timing["index_seconds"][repository] = round(
                    time.perf_counter() - started, 6
                )
                database = workspace / ".context-search/index.sqlite"
                with sqlite3.connect(database) as connection:
                    before_count, before_sha = _module_projection(connection)
                if phase == "oracle" and variant == "oracle":
                    projection = _overlay_oracle(workspace)
                elif phase == "candidate":
                    with sqlite3.connect(database) as connection:
                        projection = _product_exact_projection(connection)
                else:
                    projection = {
                        "exact_relation_count": 0,
                        "graph_omitted_imported_symbols": 0,
                        "omitted_by_source": {},
                        "maximum_exact_relations_per_source": 0,
                        "terminal_counts": {},
                        "target_states": {},
                        "exact_targets": {},
                        "module_relation_count": before_count,
                        "module_projection_sha256": before_sha,
                    }
                with sqlite3.connect(database) as connection:
                    projection["non_python_projection_sha256"] = (
                        _non_python_projection(connection)
                    )
                    projection["work_caps"] = _work_cap_projection(connection)
                index_projections[repository] = projection
                repositories[repository] = {
                    "selected_files": len(files),
                    "structure": p8_runner._structural_counts(database),
                    "index_sqlite_bytes": database.stat().st_size,
                }
                workspaces[repository] = workspace

            for case in gold["cases"]:
                repository = case["repo"]
                current_repository["value"] = repository
                workspace = workspaces[repository]
                database = workspace / ".context-search/index.sqlite"
                started = time.perf_counter()
                traced = retrieval.trace_repository(
                    workspace, case["query"], config
                )
                bundle = traced.bundle
                observed["retrieval_calls"] += 1
                if bundle.variant_retrieval_status == "embedding_fallback":
                    observed["fallback_count"] += 1
                if bundle.planner.status != "disabled":
                    observed["error_count"] += 1
                timing["query_case_seconds"][case["id"]] = round(
                    time.perf_counter() - started, 9
                )
                selected_rows = []
                for rank, result in enumerate(bundle.results, start=1):
                    trace_selection = next(
                        (
                            item
                            for item in traced.trace.final_selections
                            if item.selection_kind == "result"
                            and item.rank == rank
                            and item.file_path == str(result.file_path)
                        ),
                        None,
                    )
                    if trace_selection is None:
                        raise ValueError("selected result has no trace selection")
                    selected = {
                        "rank": rank,
                        "path": str(result.file_path),
                        "start_line": result.start_line,
                        "end_line": result.end_line,
                        "score": result.score,
                        "score_parts": dict(result.score_parts),
                        "reasons": list(result.reasons),
                        "chunk_id": trace_selection.origin_chunk_ids[0],
                        "origin_chunk_ids": list(trace_selection.origin_chunk_ids),
                        "rank_history": [
                            {
                                "stage": item.stage,
                                "rank": item.rank,
                                "score": item.score,
                            }
                            for item in trace_selection.rank_history
                        ],
                        "stage_trajectory": [
                            {
                                "stage": stage.name,
                                "rank": candidate.rank,
                                "chunk_id": candidate.chunk_id,
                                "score": candidate.score,
                            }
                            for stage in traced.trace.stages
                            for candidate in stage.top_candidates
                            if candidate.file_path == str(result.file_path)
                        ],
                    }
                    selected["exact_witness"] = _exact_witness(
                        database, selected["path"], selected
                    )
                    selected_rows.append(selected)
                required = []
                for item in case["required"]:
                    rank = next(
                        (
                            selected["rank"]
                            for selected in selected_rows
                            if selected["path"] == item["path"]
                        ),
                        None,
                    )
                    required.append(
                        {
                            "path": item["path"],
                            "role": item["role"],
                            "rank": rank,
                            "state": "selected" if rank else "not_selected",
                        }
                    )
                cases[case["id"]] = {
                    "repo": repository,
                    "selected": selected_rows,
                    "required": required,
                    "contextual": case["contextual"],
                    "trace": {
                        "outcome": traced.trace.outcome,
                        "termination_reason": traced.trace.termination_reason,
                        "source_counts": dict(traced.trace.source_counts),
                        "stages": [
                            {
                                "name": stage.name,
                                "input_count": stage.input_count,
                                "output_count": stage.output_count,
                                "unique_output_count": stage.unique_output_count,
                                "source_counts": dict(stage.source_counts),
                                "decision_counts": dict(stage.decision_counts),
                                "top_candidates": [
                                    {
                                        "rank": item.rank,
                                        "chunk_id": item.chunk_id,
                                        "path": item.file_path,
                                    }
                                    for item in stage.top_candidates
                                ],
                            }
                            for stage in traced.trace.stages
                        ],
                    },
                }
    finally:
        current_repository["value"] = None
        indexer.render_config = original_render_config
        if old_global is None:
            os.environ.pop("CST_GLOBAL_CONFIG_PATH", None)
        else:
            os.environ["CST_GLOBAL_CONFIG_PATH"] = old_global
        shutil.rmtree(scratch, ignore_errors=True)
    payload = {
        "schema_version": 1,
        "phase": phase,
        "corpora": corpora,
        "profile": profile,
        "variant": variant,
        "input_order": input_order,
        "repeat": repeat,
        "slot": f"{phase}:{corpora}:{profile}:{variant}:r{repeat}:{input_order}",
        "manifest_sha256": _sha256(manifest_path),
        "harness_sha256": _sha256(Path(__file__)),
        "development_gold_sha256": manifest["development_gold"]["sha256"],
        "product_identity": _product_identity(manifest, implementation_root),
        "implementation": p8_runner.implementation_identity(implementation_root),
        "embedding": {
            "provider": config.embedding.provider,
            "model": config.embedding.model,
            "dimensions": config.embedding.dimensions,
            "base_url": config.embedding.base_url,
            "planner_enabled": config.query_planner.enabled,
        },
        "embedding_requests": request_counts,
        "repositories": repositories,
        "index_projections": index_projections,
        "cases": cases,
        "timing": timing,
        "observed": observed,
    }
    _privacy_check(payload)
    return payload


def _capture_path(run_root: Path, *, phase: str, profile: str, corpora: str, variant: str, repeat: int, input_order: str) -> Path:
    return run_root / phase / profile / corpora / f"{variant}-r{repeat}-{input_order}.json"


def _stable_projection(capture: dict) -> dict:
    online = capture["profile"] == "online-bge"
    cases = {}
    for case_id, case in sorted(capture["cases"].items()):
        selected = []
        for row in case["selected"]:
            item = {
                "rank": row["rank"],
                "path": row["path"],
                "start_line": row["start_line"],
                "end_line": row["end_line"],
                "chunk_id": row["chunk_id"],
                "origin_chunk_ids": row["origin_chunk_ids"],
                "score_parts": sorted(row["score_parts"]),
                "exact_witness": row["exact_witness"],
                "rank_history": [
                    {"stage": value["stage"], "rank": value["rank"]}
                    for value in row["rank_history"]
                ],
                "stage_trajectory": [
                    {
                        "stage": value["stage"],
                        "rank": value["rank"],
                        "chunk_id": value["chunk_id"],
                    }
                    for value in row["stage_trajectory"]
                ],
            }
            if not online:
                item["score"] = row["score"]
                item["score_part_values"] = row["score_parts"]
                item["reasons"] = row["reasons"]
                item["rank_score_values"] = row["rank_history"]
                item["stage_score_values"] = row["stage_trajectory"]
            selected.append(item)
        cases[case_id] = {
            "repo": case["repo"],
            "selected": selected,
            "required": case["required"],
            "contextual": case["contextual"],
            "trace": case["trace"],
        }
    return {
        "profile": capture["profile"],
        "variant": capture["variant"],
        "manifest_sha256": capture["manifest_sha256"],
        "harness_sha256": capture["harness_sha256"],
        "product_identity": capture["product_identity"],
        "embedding": capture["embedding"],
        "embedding_requests": capture["embedding_requests"],
        "repositories": {
            name: {
                "selected_files": repository["selected_files"],
                "structure": repository["structure"],
            }
            for name, repository in sorted(capture["repositories"].items())
        },
        "index_projections": capture["index_projections"],
        "cases": cases,
        "observed": capture["observed"],
    }


def _validate_capture_schema(
    capture: dict,
    *,
    manifest_path: Path,
    phase: str,
    corpora: str,
    profile: str,
    variant: str,
    repeat: int,
    input_order: str,
) -> None:
    expected = {
        "schema_version",
        "phase",
        "corpora",
        "profile",
        "variant",
        "input_order",
        "repeat",
        "slot",
        "manifest_sha256",
        "harness_sha256",
        "development_gold_sha256",
        "product_identity",
        "implementation",
        "embedding",
        "embedding_requests",
        "repositories",
        "index_projections",
        "cases",
        "timing",
        "observed",
    }
    if set(capture) != expected or capture["schema_version"] != 1:
        raise ValueError("capture schema is not closed")
    slot = f"{phase}:{corpora}:{profile}:{variant}:r{repeat}:{input_order}"
    if any(
        (
            capture["phase"] != phase,
            capture["corpora"] != corpora,
            capture["profile"] != profile,
            capture["variant"] != variant,
            capture["repeat"] != repeat,
            capture["input_order"] != input_order,
            capture["slot"] != slot,
            capture["manifest_sha256"] != _sha256(manifest_path),
            capture["harness_sha256"] != _sha256(Path(__file__)),
        )
    ):
        raise ValueError("capture slot or implementation identity changed")
    product = capture["product_identity"]
    if not isinstance(product, dict) or set(product) != {
        "baseline",
        "head",
        "tracked_diff_sha256",
        "untracked",
        "product_tree_sha256",
        "clean_against_baseline",
    }:
        raise ValueError("product identity schema is invalid")
    if phase == "oracle" and product["clean_against_baseline"] is not True:
        raise ValueError("Task-0 capture contains product changes")
    embedding = capture["embedding"]
    if not isinstance(embedding, dict) or set(embedding) != {
        "provider",
        "model",
        "dimensions",
        "base_url",
        "planner_enabled",
    } or embedding["planner_enabled"] is not False:
        raise ValueError("capture embedding identity is invalid")
    if profile == "online-bge":
        if embedding != {
            "provider": ONLINE_PROVIDER,
            "model": ONLINE_MODEL,
            "dimensions": ONLINE_DIMENSIONS,
            "base_url": ONLINE_BASE_URL,
            "planner_enabled": False,
        }:
            raise ValueError("online embedding identity changed")
    elif embedding["provider"] != "hash":
        raise ValueError("hash capture used a non-hash provider")
    expected_repositories = {
        "development": {"redink", "daily"},
        "heldout": {"click"},
        "all": {"redink", "daily", "click"},
    }[corpora]
    if set(capture["embedding_requests"]) != expected_repositories | {"total"}:
        raise ValueError("embedding request accounting is not closed")
    observed = capture["observed"]
    if not isinstance(observed, dict) or set(observed) != {
        "local_model_calls",
        "planner_calls",
        "fallback_count",
        "error_count",
        "skip_count",
        "retrieval_calls",
    } or any(type(value) is not int or value < 0 for value in observed.values()):
        raise ValueError("capture observation counters are invalid")
    if set(capture["repositories"]) != expected_repositories or set(capture["index_projections"]) != expected_repositories:
        raise ValueError("capture repositories are not closed")
    projection_keys = {
        "exact_relation_count",
        "graph_omitted_imported_symbols",
        "omitted_by_source",
        "maximum_exact_relations_per_source",
        "terminal_counts",
        "target_states",
        "exact_targets",
        "module_relation_count",
        "module_projection_sha256",
        "non_python_projection_sha256",
        "work_caps",
    }
    for projection in capture["index_projections"].values():
        if not isinstance(projection, dict) or set(projection) != projection_keys:
            raise ValueError("oracle projection schema is not closed")
        if projection["maximum_exact_relations_per_source"] > 256:
            raise ValueError("oracle exact-symbol cap exceeded")
    case_keys = {"repo", "selected", "required", "contextual", "trace"}
    selected_keys = {
        "rank",
        "path",
        "start_line",
        "end_line",
        "score",
        "score_parts",
        "reasons",
        "chunk_id",
        "origin_chunk_ids",
        "rank_history",
        "stage_trajectory",
        "exact_witness",
    }
    for case in capture["cases"].values():
        if not isinstance(case, dict) or set(case) != case_keys:
            raise ValueError("capture case schema is not closed")
        for row in case["selected"]:
            if not isinstance(row, dict) or set(row) != selected_keys:
                raise ValueError("capture selected row schema is not closed")
            if row["exact_witness"] is not None and not _valid_exact_selected(row):
                raise ValueError("capture exact witness is invalid")
    _privacy_check(capture)


def _required_rank(capture: dict, case_id: str, path: str) -> int:
    for row in capture["cases"][case_id]["required"]:
        if row["path"] == path:
            return int(row["rank"]) if row["rank"] is not None else 13
    raise ValueError("required path missing from capture")


def _noise(case: dict) -> int:
    relevant = {row["path"] for row in case["required"]} | set(case["contextual"])
    return sum(row["path"] not in relevant for row in case["selected"])


def _valid_exact_selected(row: dict | None) -> bool:
    if not isinstance(row, dict):
        return False
    witness = row.get("exact_witness")
    if not isinstance(witness, dict) or set(witness) != {
        "relation_id",
        "module_relation_id",
        "source_signal_id",
        "target_signal_id",
        "target_chunk_id",
        "target_file_path",
        "actual_target_kind",
        "target_start_line",
        "target_end_line",
    }:
        return False
    return all(
        (
            witness["relation_id"].startswith("r5:"),
            witness["module_relation_id"].startswith("r5:"),
            witness["source_signal_id"].startswith("s5:"),
            witness["target_signal_id"].startswith("s5:"),
            witness["target_chunk_id"] == row.get("chunk_id"),
            witness["target_file_path"] == row.get("path"),
            witness["actual_target_kind"] in {"type", "function"},
            "graph_imports_match" in row.get("score_parts", {}),
            "static module dependency" in row.get("reasons", []),
        )
    )


def _residual_classifications(baseline: dict, candidate: dict) -> list[dict]:
    classifications = []
    for case_id, case in sorted(baseline["cases"].items()):
        repository = case["repo"]
        projection = candidate["index_projections"][repository]
        for required in case["required"]:
            path = required["path"]
            before = _required_rank(baseline, case_id, path)
            if before <= 12:
                continue
            after = _required_rank(candidate, case_id, path)
            selected = next(
                (
                    row
                    for row in candidate["cases"][case_id]["selected"]
                    if row["path"] == path
                ),
                None,
            )
            target_rows = projection["exact_targets"].get(path, [])
            states = projection["target_states"].get(path, {})
            if selected is not None:
                terminal = (
                    "selected_exact_declaration_chunk"
                    if _valid_exact_selected(selected)
                    else "selected_wrong_chunk"
                )
            elif not target_rows:
                if states.get("ambiguous_signal", 0):
                    terminal = "ambiguous_signal"
                elif states.get("no_exact_signal", 0):
                    terminal = "no_exact_signal"
                else:
                    terminal = "not_representable"
            else:
                target_chunks = {row["target_chunk_id"] for row in target_rows}
                source_chunks = {row["source_chunk_id"] for row in target_rows}
                trace = candidate["cases"][case_id]["trace"]
                preview_chunks = {
                    row["chunk_id"]
                    for stage in trace["stages"]
                    for row in stage["top_candidates"]
                }
                selected_chunks = {
                    chunk_id
                    for row in candidate["cases"][case_id]["selected"]
                    for chunk_id in row["origin_chunk_ids"]
                }
                if target_chunks & preview_chunks:
                    terminal = "ranked_not_selected"
                elif source_chunks & (preview_chunks | selected_chunks):
                    terminal = "acquired_below_ranking"
                else:
                    terminal = "resolved_not_traversed"
            classifications.append(
                {
                    "case": case_id,
                    "repo": repository,
                    "path": path,
                    "baseline_rank": before,
                    "candidate_rank": after,
                    "terminal_state": terminal,
                    "relation_ids": sorted(
                        row["relation_id"] for row in target_rows
                    ),
                    "target_signal_ids": sorted(
                        {row["target_signal_id"] for row in target_rows}
                    ),
                    "target_chunk_ids": sorted(
                        {row["target_chunk_id"] for row in target_rows}
                    ),
                    "stage_trajectory": (
                        selected["stage_trajectory"] if selected else []
                    ),
                }
            )
    keys = [(row["case"], row["path"]) for row in classifications]
    if len(keys) != len(set(keys)) or any(
        row["terminal_state"] not in _TERMINAL_STATES
        for row in classifications
    ):
        raise ValueError("residual classification is not total and unique")
    return classifications


def _compare_pair(manifest: dict, baseline: dict, candidate: dict) -> dict:
    required = [
        (case_id, case["repo"], row["path"], row["role"])
        for case_id, case in sorted(baseline["cases"].items())
        for row in case["required"]
    ]
    baseline_hits = sum(_required_rank(baseline, case_id, path) <= 12 for case_id, _repo, path, _role in required)
    candidate_hits = sum(_required_rank(candidate, case_id, path) <= 12 for case_id, _repo, path, _role in required)
    new_items = []
    losses = []
    exact_gains = []
    for case_id, repo, path, role in required:
        before = _required_rank(baseline, case_id, path)
        after = _required_rank(candidate, case_id, path)
        selected = next((row for row in candidate["cases"][case_id]["selected"] if row["path"] == path), None)
        witness = selected.get("exact_witness") if selected else None
        if before > 12 and after <= 12:
            new_items.append({"case": case_id, "repo": repo, "path": path, "role": role, "witness": witness})
        if before <= 12 and after > 12:
            losses.append({"case": case_id, "repo": repo, "path": path})
        if after < before and _valid_exact_selected(selected):
            exact_gains.append({"case": case_id, "repo": repo, "path": path, "before": before, "after": after})
    noise_growth = {
        case_id: _noise(candidate["cases"][case_id]) - _noise(baseline["cases"][case_id])
        for case_id in baseline["cases"]
    }
    repositories = sorted({repo for _case, repo, _path, _role in required})
    module_stable = all(
        baseline["index_projections"][repo]["module_projection_sha256"]
        == candidate["index_projections"][repo]["module_projection_sha256"]
        for repo in repositories
    )
    first_stable = all(
        baseline["cases"][case_id]["selected"][0]["path"]
        == candidate["cases"][case_id]["selected"][0]["path"]
        for case_id in baseline["cases"]
    )
    r2 = manifest["r2"]
    per_repo_non_decreasing = all(
        sum(
            _required_rank(candidate, case_id, path) <= 12
            for case_id, repo, path, _role in required
            if repo == repository
        )
        >= sum(
            _required_rank(baseline, case_id, path) <= 12
            for case_id, repo, path, _role in required
            if repo == repository
        )
        for repository in repositories
    )
    membership_drift = []
    for case_id in baseline["cases"]:
        before_paths = {row["path"] for row in baseline["cases"][case_id]["selected"]}
        after_paths = {row["path"] for row in candidate["cases"][case_id]["selected"]}
        if before_paths != after_paths and not any(
            _valid_exact_selected(row)
            for row in candidate["cases"][case_id]["selected"]
        ):
            membership_drift.append(case_id)
    residuals = _residual_classifications(baseline, candidate)
    work_caps_stable = all(
        all(
            baseline["index_projections"][repo]["work_caps"][key]
            == candidate["index_projections"][repo]["work_caps"][key]
            for key in (
                "max_graph_seed_signals",
                "max_resolved_graph_hops",
                "max_edges_per_signal_direction",
                "max_relation_expanded_candidates",
            )
        )
        and candidate["index_projections"][repo]["maximum_exact_relations_per_source"] <= 256
        for repo in repositories
    )
    index_regressions = {
        repo: (
            candidate["timing"]["index_seconds"][repo]
            / max(baseline["timing"]["index_seconds"][repo], 1e-9)
            - 1.0
        )
        for repo in repositories
    }
    query_regressions = {}
    for case_id, baseline_seconds in baseline["timing"]["query_case_seconds"].items():
        candidate_seconds = candidate["timing"]["query_case_seconds"][case_id]
        absolute = candidate_seconds - baseline_seconds
        ratio = candidate_seconds / max(baseline_seconds, 1e-9) - 1.0
        query_regressions[case_id] = {"absolute_seconds": absolute, "ratio": ratio}
    performance_pass = (
        index_regressions.get("daily", 0.0)
        <= r2["maximum_index_regression_ratio"]
        and all(
            row["absolute_seconds"] < r2["minimum_query_regression_seconds"]
            or row["ratio"] <= r2["maximum_query_regression_ratio"]
            for row in query_regressions.values()
        )
    )
    is_heldout = baseline["corpora"] == "heldout"
    minimum_items = (
        r2["heldout_minimum_new_required_items"]
        if is_heldout
        else r2["development_minimum_new_required_items"]
    )
    minimum_cases = (
        r2["heldout_minimum_distinct_cases"]
        if is_heldout
        else r2["development_minimum_distinct_cases"]
    )
    gates = {
        "micro_recall_gain": (candidate_hits - baseline_hits) / len(required) >= r2["development_minimum_micro_recall_gain"] - 1e-12,
        "new_required_items": len(new_items) >= minimum_items,
        "distinct_gain_cases": len({row["case"] for row in new_items}) >= minimum_cases,
        "exact_witness_for_every_new_item": all(
            _valid_exact_selected(
                next(
                    row
                    for row in candidate["cases"][item["case"]]["selected"]
                    if row["path"] == item["path"]
                )
            )
            for item in new_items
        ),
        "exact_gain_repository_spread": (
            True
            if is_heldout
            else set(r2["development_required_repository_spread"])
            <= {row["repo"] for row in exact_gains}
        ),
        "zero_required_loss": not losses,
        "per_repository_recall_non_decreasing": per_repo_non_decreasing,
        "zero_noise_growth": all(delta <= r2["noise_growth_limit"] for delta in noise_growth.values()),
        "protected_winners_stable": first_stable,
        "module_relations_stable": module_stable,
        "request_counts_stable": baseline["embedding_requests"] == candidate["embedding_requests"],
        "retrieval_calls_stable": baseline["observed"]["retrieval_calls"]
        == candidate["observed"]["retrieval_calls"]
        == len(baseline["cases"]),
        "membership_drift_closed": not membership_drift,
        "non_python_projection_stable": all(
            baseline["index_projections"][repo]["non_python_projection_sha256"]
            == candidate["index_projections"][repo]["non_python_projection_sha256"]
            for repo in repositories
        ),
        "work_caps_stable": work_caps_stable,
        "performance_within_bounds": performance_pass,
        "residual_classification_total": len(residuals)
        == sum(
            row["rank"] is None
            for case in baseline["cases"].values()
            for row in case["required"]
        ),
        "no_local_model_or_fallback": all(
            capture["observed"][field] == 0
            for capture in (baseline, candidate)
            for field in (
                "local_model_calls",
                "planner_calls",
                "fallback_count",
                "error_count",
                "skip_count",
            )
        ),
    }
    return {
        "required_item_total": len(required),
        "baseline_hits": baseline_hits,
        "candidate_hits": candidate_hits,
        "micro_recall_delta": (candidate_hits - baseline_hits) / len(required),
        "new_required_items": new_items,
        "lost_required_items": losses,
        "exact_rank_gains": exact_gains,
        "residual_classifications": residuals,
        "membership_drift": membership_drift,
        "performance": {
            "index_regressions": index_regressions,
            "query_regressions": query_regressions,
        },
        "noise_growth": noise_growth,
        "gates": gates,
        "disposition": "proceed" if all(gates.values()) else "reject",
    }


def _hash_marker_path(run_root: Path) -> Path:
    return run_root / "oracle/hash-proceed.json"


def _candidate_hash_marker_path(run_root: Path) -> Path:
    return run_root / "candidate/hash-proceed.json"


def _write_new_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8") as handle:
            handle.write(_canonical(payload))
    except FileExistsError:
        raise ValueError("immutable evidence slot already exists") from None


def _ensure_baseline_worktree(manifest: dict) -> Path:
    path = ROOT / ".worktrees/p15-baseline-5f56de2"
    baseline = manifest["behavior_baseline"]
    if path.exists():
        if _git_at(path, "rev-parse", "HEAD") != baseline:
            raise ValueError("baseline worktree identity changed")
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        (
            "git",
            "-C",
            str(ROOT),
            "worktree",
            "add",
            "--detach",
            str(path),
            baseline,
        ),
        check=True,
        capture_output=True,
        text=True,
    )
    if _git_at(path, "rev-parse", "HEAD") != baseline:
        raise ValueError("baseline worktree creation failed")
    return path


def _validate_hash_marker(manifest_path: Path, run_root: Path) -> dict:
    marker = _read_json(_hash_marker_path(run_root))
    if set(marker) != {
        "status",
        "manifest_sha256",
        "harness_sha256",
        "product_tree_sha256",
        "comparison_sha256",
    } or any(
        (
            marker.get("status") != "proceed",
            marker.get("manifest_sha256") != _sha256(manifest_path),
            marker.get("harness_sha256") != _sha256(Path(__file__)),
            marker.get("product_tree_sha256")
            != _product_identity(validate_manifest(manifest_path))["product_tree_sha256"],
            marker.get("comparison_sha256")
            != _sha256(run_root / "oracle/hash/development/comparison.json"),
        )
    ):
        raise ValueError("hash proceed marker is stale or invalid")
    return marker


def _validate_candidate_hash_marker(manifest_path: Path, run_root: Path) -> dict:
    marker = _read_json(_candidate_hash_marker_path(run_root))
    frozen = _read_json(run_root / "candidate-freeze.json")
    comparison = run_root / "candidate/hash/all/comparison.json"
    if set(marker) != {
        "status",
        "manifest_sha256",
        "harness_sha256",
        "product_tree_sha256",
        "comparison_sha256",
    } or any(
        (
            marker.get("status") != "proceed",
            marker.get("manifest_sha256") != _sha256(manifest_path),
            marker.get("harness_sha256") != _sha256(Path(__file__)),
            marker.get("product_tree_sha256")
            != frozen["product_identity"]["product_tree_sha256"],
            marker.get("comparison_sha256") != _sha256(comparison),
        )
    ):
        raise ValueError("candidate hash proceed marker is stale or invalid")
    return marker


def compare_captures(
    manifest_path: Path,
    run_root: Path,
    *,
    phase: str,
    corpora: str,
    profile: str,
    write: bool = True,
) -> dict:
    if phase == "oracle" and corpora != "development":
        raise ValueError("Task-0 oracle runs only on development corpora")
    if phase == "candidate" and corpora == "all" and profile == "hash":
        development_path = run_root / "candidate/hash/development/comparison.json"
        heldout_path = run_root / "candidate/hash/heldout/comparison.json"
        development = _read_json(development_path)
        heldout = _read_json(heldout_path)
        oracle = _read_json(run_root / "oracle/hash/development/comparison.json")
        recovered = {
            (row["case"], row["path"])
            for row in development.get("new_required_items", [])
        } >= {
            (row["case"], row["path"])
            for row in oracle.get("new_required_items", [])
        }
        gates = {
            "development_proceed": development.get("disposition") == "proceed",
            "heldout_proceed": heldout.get("disposition") == "proceed",
            "production_recovers_oracle_gains": recovered,
        }
        report = {
            "phase": phase,
            "corpora": corpora,
            "profile": profile,
            "gates": gates,
            "development_comparison_sha256": _sha256(development_path),
            "heldout_comparison_sha256": _sha256(heldout_path),
            "oracle_comparison_sha256": _sha256(
                run_root / "oracle/hash/development/comparison.json"
            ),
            "disposition": "proceed" if all(gates.values()) else "reject",
        }
        output = run_root / phase / profile / corpora / "comparison.json"
        if write:
            _write_new_json(output, report)
            if report["disposition"] == "proceed":
                frozen = _read_json(run_root / "candidate-freeze.json")
                _write_new_json(
                    _candidate_hash_marker_path(run_root),
                    {
                        "status": "proceed",
                        "manifest_sha256": _sha256(manifest_path),
                        "harness_sha256": _sha256(Path(__file__)),
                        "product_tree_sha256": frozen["product_identity"]["product_tree_sha256"],
                        "comparison_sha256": _sha256(output),
                    },
                )
        return report
    manifest = validate_manifest(manifest_path)
    variants = ("baseline", "oracle" if phase == "oracle" else "candidate")
    orders = ("canonical", "reverse") if profile == "hash" else ("canonical",)
    captures: dict[tuple[str, int, str], dict] = {}
    for variant in variants:
        for repeat in (1, 2):
            for order in orders:
                path = _capture_path(run_root, phase=phase, profile=profile, corpora=corpora, variant=variant, repeat=repeat, input_order=order)
                capture = _read_json(path)
                _validate_capture_schema(
                    capture,
                    manifest_path=manifest_path,
                    phase=phase,
                    corpora=corpora,
                    profile=profile,
                    variant=variant,
                    repeat=repeat,
                    input_order=order,
                )
                captures[(variant, repeat, order)] = capture
    deterministic = {}
    for variant in variants:
        projections = [
            _canonical(_stable_projection(captures[(variant, repeat, order)]))
            for repeat in (1, 2)
            for order in orders
        ]
        deterministic[variant] = len(set(projections)) == 1
    baseline = captures[("baseline", 1, "canonical")]
    oracle = captures[("oracle", 1, "canonical")]
    report = _compare_pair(manifest, baseline, oracle)
    report["profile"] = profile
    if profile == "online-bge":
        for gate in (
            "micro_recall_gain",
            "new_required_items",
            "distinct_gain_cases",
            "exact_gain_repository_spread",
            "performance_within_bounds",
        ):
            report["gates"][gate] = True
    report["deterministic"] = deterministic
    report["gates"]["deterministic"] = all(deterministic.values())
    report["disposition"] = "proceed" if all(report["gates"].values()) else "reject"
    output = run_root / phase / profile / corpora / "comparison.json"
    if write:
        _write_new_json(output, report)
        if profile == "hash" and report["disposition"] == "proceed":
            _write_new_json(
                _hash_marker_path(run_root),
                {
                    "status": "proceed",
                    "manifest_sha256": _sha256(manifest_path),
                    "harness_sha256": _sha256(Path(__file__)),
                    "product_tree_sha256": baseline["product_identity"]["product_tree_sha256"],
                    "comparison_sha256": _sha256(output),
                },
            )
    return report


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate")
    validate.add_argument("--manifest", required=True)
    validate.add_argument("--run-root", required=True)
    capture = commands.add_parser("capture")
    capture.add_argument("--manifest", required=True)
    capture.add_argument("--run-root", required=True)
    capture.add_argument("--phase", choices=("oracle", "candidate"), required=True)
    capture.add_argument("--corpora", choices=("development", "heldout", "all"), required=True)
    capture.add_argument("--profile", choices=("hash", "online-bge"), required=True)
    capture.add_argument("--variant", choices=("baseline", "oracle", "candidate"), required=True)
    capture.add_argument("--repeat", type=int, choices=(1, 2), required=True)
    capture.add_argument("--input-order", choices=("canonical", "reverse"), required=True)
    compare = commands.add_parser("compare")
    compare.add_argument("--manifest", required=True)
    compare.add_argument("--run-root", required=True)
    compare.add_argument("--phase", choices=("oracle", "candidate"), required=True)
    compare.add_argument("--corpora", choices=("development", "heldout", "all"), required=True)
    compare.add_argument("--profile", choices=("hash", "online-bge"), required=True)
    freeze = commands.add_parser("freeze-candidate")
    freeze.add_argument("--manifest", required=True)
    freeze.add_argument("--run-root", required=True)
    open_heldout = commands.add_parser("open-heldout")
    open_heldout.add_argument("--manifest", required=True)
    open_heldout.add_argument("--run-root", required=True)
    open_heldout.add_argument("--sealed-payload", required=True)
    check = commands.add_parser("check")
    check.add_argument("--manifest", required=True)
    check.add_argument("--run-root", required=True)
    check.add_argument("--gate", choices=("task0", "final"), required=True)
    check.add_argument("--protected-junit")
    check.add_argument("--full-suite-junit")
    check.add_argument("--raw-ci")
    check.add_argument("--write-evidence-manifest")
    return parser


def _junit_summary(path: Path) -> dict[str, int]:
    root = ET.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    return {
        key: sum(int(suite.attrib.get(key, "0")) for suite in suites)
        for key in ("tests", "failures", "errors", "skipped")
    }


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _build_parser().parse_args(argv)
    manifest_path = Path(arguments.manifest).resolve()
    run_root = Path(arguments.run_root).resolve()
    if arguments.command == "validate":
        manifest = validate_manifest(manifest_path)
        run_root.mkdir(parents=True, exist_ok=True)
        result = {
            "status": "valid",
            "manifest_sha256": _sha256(manifest_path),
            "seal_id": manifest["heldout_seal"]["seal_id"],
            "heldout_status": manifest["heldout_seal"]["status"],
        }
        _write_new_json(run_root / "validation.json", result)
        print(_canonical(result), end="")
        return 0
    if arguments.command == "capture":
        manifest = validate_manifest(manifest_path)
        implementation_root = ROOT
        if arguments.phase == "oracle":
            if arguments.corpora != "development" or arguments.variant not in {"baseline", "oracle"}:
                raise ValueError("Task-0 oracle slot is invalid")
            if arguments.profile == "online-bge":
                if arguments.input_order != "canonical":
                    raise ValueError("online stable projection uses canonical order only")
                _validate_hash_marker(manifest_path, run_root)
        else:
            if arguments.variant not in {"baseline", "candidate"}:
                raise ValueError("candidate capture slot is invalid")
            frozen = _read_json(run_root / "candidate-freeze.json")
            if (
                frozen.get("manifest_sha256") != _sha256(manifest_path)
                or frozen.get("harness_sha256") != _sha256(Path(__file__))
                or frozen.get("product_identity") != _product_identity(manifest)
            ):
                raise ValueError("candidate freeze is stale")
            if arguments.corpora in {"heldout", "all"}:
                _read_json(run_root / "heldout/open-record.json")
            if arguments.profile == "hash" and arguments.corpora == "all":
                raise ValueError("hash all is a comparison-only aggregate")
            if arguments.profile == "online-bge":
                if arguments.corpora != "all" or arguments.input_order != "canonical":
                    raise ValueError("candidate online capture requires all corpora canonical")
                _validate_candidate_hash_marker(manifest_path, run_root)
            if arguments.variant == "baseline":
                implementation_root = _ensure_baseline_worktree(manifest)
                sys.path.insert(0, str(implementation_root / "src"))
        payload = _capture_development(
            manifest_path,
            run_root=run_root,
            phase=arguments.phase,
            corpora=arguments.corpora,
            profile=arguments.profile,
            variant=arguments.variant,
            repeat=arguments.repeat,
            input_order=arguments.input_order,
            implementation_root=implementation_root,
        )
        output = _capture_path(
            run_root,
            phase=arguments.phase,
            profile=arguments.profile,
            corpora=arguments.corpora,
            variant=arguments.variant,
            repeat=arguments.repeat,
            input_order=arguments.input_order,
        )
        _write_new_json(output, payload)
        print(str(output.relative_to(ROOT)))
        return 0
    if arguments.command == "compare":
        report = compare_captures(
            manifest_path,
            run_root,
            phase=arguments.phase,
            corpora=arguments.corpora,
            profile=arguments.profile,
        )
        print(_canonical(report), end="")
        return 0 if report["disposition"] == "proceed" else 2
    if arguments.command == "freeze-candidate":
        manifest = validate_manifest(manifest_path)
        task0 = _read_json(run_root / "task0-check.json")
        if task0.get("disposition") != "proceed":
            raise ValueError("candidate cannot freeze before Task-0 proceed")
        product = _product_identity(manifest)
        if product["clean_against_baseline"]:
            raise ValueError("candidate freeze requires a reviewed product diff")
        result = {
            "status": "frozen",
            "manifest_sha256": _sha256(manifest_path),
            "harness_sha256": _sha256(Path(__file__)),
            "product_identity": product,
            "implementation": importlib.import_module(
                "p8_real_python_graphs_acceptance"
            ).implementation_identity(ROOT),
        }
        _privacy_check(result)
        _write_new_json(run_root / "candidate-freeze.json", result)
        print(_canonical(result), end="")
        return 0
    if arguments.command == "open-heldout":
        manifest = validate_manifest(manifest_path)
        frozen = _read_json(run_root / "candidate-freeze.json")
        if (
            frozen.get("status") != "frozen"
            or frozen.get("manifest_sha256") != _sha256(manifest_path)
            or frozen.get("harness_sha256") != _sha256(Path(__file__))
            or frozen.get("product_identity") != _product_identity(manifest)
        ):
            raise ValueError("candidate freeze is stale")
        development = _read_json(
            run_root / "candidate/hash/development/comparison.json"
        )
        if development.get("disposition") != "proceed":
            raise ValueError("held-out cannot open before development hash proceed")
        payload_path = Path(arguments.sealed_payload).resolve()
        if _sha256(payload_path) != manifest["heldout_seal"]["sealed_plaintext_sha256"]:
            raise ValueError("opened held-out payload digest changed")
        payload = _read_json(payload_path)
        cases = payload.get("cases")
        if not isinstance(cases, list) or len(cases) != manifest["heldout_seal"]["case_count"]:
            raise ValueError("opened held-out case denominator changed")
        denominator = sum(
            len(case.get("required", ()))
            for case in cases
            if isinstance(case, dict)
        )
        if denominator != manifest["heldout_seal"]["required_item_denominator"]:
            raise ValueError("opened held-out required denominator changed")
        _privacy_check(payload)
        opened_path = run_root / "heldout/opened-payload.json"
        _write_new_json(opened_path, payload)
        result = {
            "status": "opened_after_candidate_freeze",
            "plaintext_sha256": _sha256(opened_path),
            "case_count": len(cases),
            "required_item_denominator": denominator,
        }
        _write_new_json(run_root / "heldout/open-record.json", result)
        print(_canonical(result), end="")
        return 0
    manifest = validate_manifest(manifest_path)
    if arguments.gate == "final":
        required_paths = (
            arguments.protected_junit,
            arguments.full_suite_junit,
            arguments.raw_ci,
            arguments.write_evidence_manifest,
        )
        if any(path is None for path in required_paths):
            raise ValueError("final gate evidence paths are incomplete")
        _validate_candidate_hash_marker(manifest_path, run_root)
        frozen = _read_json(run_root / "candidate-freeze.json")
        if frozen.get("product_identity") != _product_identity(manifest):
            raise ValueError("captured candidate changed after freeze")
        development = compare_captures(
            manifest_path,
            run_root,
            phase="candidate",
            corpora="development",
            profile="hash",
            write=False,
        )
        heldout = compare_captures(
            manifest_path,
            run_root,
            phase="candidate",
            corpora="heldout",
            profile="hash",
            write=False,
        )
        aggregate = compare_captures(
            manifest_path,
            run_root,
            phase="candidate",
            corpora="all",
            profile="hash",
            write=False,
        )
        online = compare_captures(
            manifest_path,
            run_root,
            phase="candidate",
            corpora="all",
            profile="online-bge",
            write=False,
        )
        protected_path = Path(arguments.protected_junit).resolve()
        full_path = Path(arguments.full_suite_junit).resolve()
        raw_ci_path = Path(arguments.raw_ci).resolve()
        protected = _junit_summary(protected_path)
        full = _junit_summary(full_path)
        raw_ci = _read_json(raw_ci_path)
        raw_aggregate = raw_ci.get("aggregate")
        raw_pass = isinstance(raw_aggregate, dict) and all(
            raw_aggregate.get(key) == expected
            for key, expected in (
                ("selected", 8),
                ("executed", 8),
                ("passed", 8),
                ("failed", 0),
                ("errors", 0),
            )
        )
        gates = {
            "development_hash": development.get("disposition") == "proceed",
            "heldout_hash": heldout.get("disposition") == "proceed",
            "aggregate_hash": aggregate.get("disposition") == "proceed",
            "online_stable_projection": online.get("disposition") == "proceed",
            "protected_suite": protected["tests"] > 0
            and protected["failures"] == protected["errors"] == 0,
            "full_suite_without_local_integrations": full["tests"] > 0
            and full["failures"] == full["errors"] == 0,
            "raw_ci_8_of_8": raw_pass,
        }
        result = {
            "schema_version": 1,
            "gate": "final",
            "manifest_sha256": _sha256(manifest_path),
            "harness_sha256": _sha256(Path(__file__)),
            "product_tree_sha256": frozen["product_identity"]["product_tree_sha256"],
            "comparisons": {
                "development_hash": _sha256(
                    run_root / "candidate/hash/development/comparison.json"
                ),
                "heldout_hash": _sha256(
                    run_root / "candidate/hash/heldout/comparison.json"
                ),
                "all_hash": _sha256(
                    run_root / "candidate/hash/all/comparison.json"
                ),
                "all_online": _sha256(
                    run_root / "candidate/online-bge/all/comparison.json"
                ),
            },
            "tests": {"protected": protected, "full": full},
            "raw_ci_sha256": _sha256(raw_ci_path),
            "full_suite_filter": "not slow and not integration",
            "full_suite_filter_reason": "user prohibited every local Ollama/model integration path",
            "gates": gates,
            "disposition": "ship" if all(gates.values()) else "reject",
        }
        _privacy_check(result)
        evidence_path = Path(arguments.write_evidence_manifest).resolve()
        _write_new_json(evidence_path, result)
        print(_canonical(result), end="")
        return 0 if result["disposition"] == "ship" else 2
    _validate_hash_marker(manifest_path, run_root)
    comparisons = [
        compare_captures(
            manifest_path,
            run_root,
            phase="oracle",
            corpora="development",
            profile=profile,
            write=False,
        )
        for profile in ("hash", "online-bge")
    ]
    product = _product_identity(manifest)
    passed = (
        all(item.get("disposition") == "proceed" for item in comparisons)
        and product["clean_against_baseline"]
    )
    result = {
        "gate": "task0",
        "hash": comparisons[0]["disposition"],
        "online_bge": comparisons[1]["disposition"],
        "product_diff_empty": product["clean_against_baseline"],
        "product_tree_sha256": product["product_tree_sha256"],
        "disposition": "proceed" if passed else "reject",
    }
    _write_new_json(run_root / "task0-check.json", result)
    print(_canonical(result), end="")
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
