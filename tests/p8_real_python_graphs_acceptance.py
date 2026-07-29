"""P8 paired acceptance runner: capture / compare / check.

capture runs inside a process whose PYTHONPATH selects the implementation
root under test (baseline worktree or candidate tree); it verifies the
implementation identity and the pinned source trees, builds one fresh index
per repository, and records structural counts plus all 18 gold-case
trajectories and the fixed witnesses - never source bodies or absolute
paths. compare applies the design's metric arithmetic and ship gates.
check validates a capture's invariants and deterministic rerender.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import p8_python_graph_identity as identity
from generate_p8_python_graph_manifest import build_manifest

SENTINEL_RANK = 13
CAPTURE_SCHEMA_VERSION = 4
KNOWN_EMBEDDINGS = ("hash", "bge")
_CAPTURE_ROOT_KEYS = {
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
_IMPLEMENTATION_KEYS = {
    "base_commit",
    "tracked_diff_sha256",
    "untracked_files",
    "dirty",
}
_ENVIRONMENT_KEYS = {"python_version", "sqlite_version", "numpy_version"}
_IDENTITY_KEYS = {
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
_REPOSITORY_KEYS = {"selected_files", "structure", "index_sqlite_bytes"}
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
_REQUEST_KEYS = {"redink", "daily", "total"}
_TIMING_KEYS = {
    "index_seconds",
    "query_case_min_seconds",
    "query_p50_seconds",
    "query_p95_seconds",
}
_SHA256_RE = re.compile(r"[0-9a-f]{64}")

SOURCES = {
    "redink": {
        "dir_name": "RedInk",
        "patterns": identity.REDINK_INCLUDE,
        "expected_count": identity.REDINK_SELECTED_COUNT,
        "inventory_sha256": identity.REDINK_INVENTORY_SHA256,
        "content_sha256": identity.REDINK_CONTENT_SHA256,
    },
    "daily": {
        "dir_name": "daily_stock_analysis",
        "patterns": identity.DAILY_INCLUDE,
        "expected_count": identity.DAILY_SELECTED_COUNT,
        "inventory_sha256": identity.DAILY_INVENTORY_SHA256,
        "content_sha256": identity.DAILY_CONTENT_SHA256,
    },
}


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ("git", "-C", str(root), *args),
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def implementation_identity(root: Path) -> dict:
    head = _git(root, "rev-parse", "HEAD")
    diff = _git(root, "diff", "--binary", "HEAD", "--", "src", "tests")
    tracked_diff_sha = hashlib.sha256(diff.encode("utf-8")).hexdigest()
    untracked: dict[str, str] = {}
    listed = _git(
        root,
        "ls-files",
        "--others",
        "--exclude-standard",
        "--",
        "src",
        "tests",
    )
    for relative in sorted(filter(None, listed.splitlines())):
        payload = (root / relative).read_bytes()
        untracked[relative] = hashlib.sha256(payload).hexdigest()
    return {
        "base_commit": head,
        "tracked_diff_sha256": tracked_diff_sha,
        "untracked_files": untracked,
        "dirty": bool(diff) or bool(untracked),
    }


def _canonical(payload: object) -> str:
    return json.dumps(
        payload, ensure_ascii=False, sort_keys=True, indent=1
    ) + "\n"


def _manifest_or_fail() -> dict:
    manifest = build_manifest()
    stored = json.loads(
        (Path(__file__).resolve().parent / "fixtures/p8_python_graphs/input_manifest.json")
        .read_text(encoding="utf-8")
    )
    if stored != manifest:
        raise ValueError("frozen gold manifest does not match its generator")
    return manifest


def _structural_counts(index_db: Path) -> dict:
    with sqlite3.connect(index_db) as connection:
        connection.row_factory = sqlite3.Row
        signals = {
            str(row["producer"]): int(row["count"])
            for row in connection.execute(
                "SELECT producer, COUNT(*) AS count FROM code_signals"
                " WHERE deleted_at IS NULL GROUP BY producer"
            )
        }
        relations = {
            f"{row['kind']}:{row['resolution']}": int(row["count"])
            for row in connection.execute(
                "SELECT kind, resolution, COUNT(*) AS count FROM code_relations"
                " GROUP BY kind, resolution"
            )
        }
        chunks = connection.execute(
            "SELECT COUNT(*) FROM chunks WHERE deleted_at IS NULL"
        ).fetchone()[0]
    return {
        "active_chunks": int(chunks),
        "signals_by_producer": signals,
        "relations_by_kind_resolution": relations,
    }


def _import_witness(index_db: Path, selected_path: str) -> dict | None:
    with sqlite3.connect(index_db) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            """
            SELECT r.relation_id, r.target_qualified_name
            FROM code_relations r
            WHERE r.kind = 'imports' AND r.resolution = 'resolved_exact'
              AND r.target_qualified_name = ?
            ORDER BY r.relation_id LIMIT 1
            """,
            (selected_path,),
        ).fetchone()
    if row is None:
        return None
    return {
        "relation_id": str(row["relation_id"]),
        "target_path": str(row["target_qualified_name"]),
    }


def _embedding_config(embedding: str):
    from context_search_tool.config import (
        DEFAULT_CONFIG,
        EmbeddingConfig,
        ToolConfig,
    )

    if embedding == "hash":
        return DEFAULT_CONFIG
    if embedding == "bge":
        import dataclasses

        return dataclasses.replace(
            DEFAULT_CONFIG,
            embedding=EmbeddingConfig(
                provider="bge", model="bge-m3", dimensions=1024
            ),
        )
    raise ValueError(f"unsupported embedding argument: {embedding}")


def _nearest_rank(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(percentile * len(ordered)) - 1)]


@contextmanager
def _count_embedding_requests(
    *,
    enabled: bool,
    current_repository: dict[str, str | None],
    counts: dict[str, int],
):
    if not enabled:
        yield
        return

    from context_search_tool.embeddings_bge import BGEEmbeddingProvider

    original = BGEEmbeddingProvider._embed_batch

    def counted(self, texts, *args, **kwargs):
        repository = current_repository["value"]
        if repository not in ("redink", "daily"):
            raise ValueError("BGE embedding request has no repository attribution")
        counts[repository] += 1
        counts["total"] += 1
        return original(self, texts, *args, **kwargs)

    BGEEmbeddingProvider._embed_batch = counted
    try:
        yield
    finally:
        BGEEmbeddingProvider._embed_batch = original


def _assert_indexed_identity(workspace: Path, config) -> None:
    from context_search_tool.manifest import (
        embedding_config_hash,
        load_manifest,
    )

    stored = load_manifest(workspace)
    expected = embedding_config_hash(config.embedding)
    if stored.embedding_config_hash != expected:
        raise ValueError(
            "indexed embedding identity does not match the requested"
            f" embedding config for {workspace.name}"
        )


def capture(
    implementation_root: Path,
    repos_dir: Path,
    output_path: Path,
    *,
    timing_reps: int = 2,
    embedding: str = "hash",
) -> dict:
    import numpy as np

    from context_search_tool.embeddings import provider_from_config
    from context_search_tool.indexer import index_repository
    from context_search_tool.manifest import embedding_config_hash
    from context_search_tool.retrieval import query_repository
    from context_search_tool.vector_store import NumpyVectorStore

    config = _embedding_config(embedding)
    static_identity = embedding_config_hash(config.embedding)
    attestation_provider = (
        provider_from_config(config.embedding) if embedding == "bge" else None
    )
    pre_attestation = (
        attestation_provider.runtime_fingerprint()
        if attestation_provider is not None
        else None
    )
    manifest = _manifest_or_fail()
    request_counts = {"redink": 0, "daily": 0, "total": 0}
    current_repository: dict[str, str | None] = {"value": None}
    capture_payload: dict = {
        "schema_version": CAPTURE_SCHEMA_VERSION,
        "implementation": implementation_identity(implementation_root),
        "environment": {
            "python_version": sys.version.split()[0],
            "sqlite_version": sqlite3.sqlite_version,
            "numpy_version": np.__version__,
        },
        "manifest_sha256": manifest["manifest_sha256"],
        "embedding_identity": None,
        "repositories": {},
        "cases": {},
        "witnesses": {},
        "embedding_requests": request_counts,
        "timing": {
            "index_seconds": {},
            "query_case_min_seconds": {},
            "query_p50_seconds": None,
            "query_p95_seconds": None,
        },
    }

    workspaces: dict[str, Path] = {}
    scratch = Path(tempfile.mkdtemp(prefix="cst-p8-capture-"))
    descriptor_identities: set[str] = set()
    try:
        with _count_embedding_requests(
            enabled=embedding == "bge",
            current_repository=current_repository,
            counts=request_counts,
        ):
            for repo_key, spec in SOURCES.items():
                current_repository["value"] = repo_key
                source_root = repos_dir / spec["dir_name"]
                files = identity.validate_protected_source(
                    source_root,
                    patterns=spec["patterns"],
                    expected_count=spec["expected_count"],
                    expected_inventory_sha256=spec["inventory_sha256"],
                    expected_content_sha256=spec["content_sha256"],
                )
                workspace = scratch / spec["dir_name"]
                for relative in files:
                    target = workspace / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source_root / relative, target)
                started = time.perf_counter()
                index_repository(workspace, config)
                index_seconds = time.perf_counter() - started
                _assert_indexed_identity(workspace, config)
                descriptor = NumpyVectorStore.inspect_published_descriptor(
                    workspace / ".context-search"
                )
                if descriptor is None:
                    raise ValueError("capture vector descriptor is missing")
                descriptor_identities.add(
                    descriptor.descriptor.embedding_identity
                )
                workspaces[repo_key] = workspace
                index_db = workspace / ".context-search" / "index.sqlite"
                capture_payload["repositories"][repo_key] = {
                    "selected_files": len(files),
                    "structure": _structural_counts(index_db),
                    "index_sqlite_bytes": index_db.stat().st_size,
                }
                capture_payload["timing"]["index_seconds"][repo_key] = round(
                    index_seconds, 6
                )

            latencies: list[float] = []
            for case in manifest["cases"]:
                current_repository["value"] = case["repo"]
                workspace = workspaces[case["repo"]]
                index_db = workspace / ".context-search" / "index.sqlite"
                bundle = None
                case_latencies = []
                for _ in range(max(1, timing_reps)):
                    started = time.perf_counter()
                    bundle = query_repository(workspace, case["query"], config)
                    case_latencies.append(time.perf_counter() - started)
                case_minimum = round(min(case_latencies), 9)
                latencies.append(case_minimum)
                capture_payload["timing"]["query_case_min_seconds"][
                    case["id"]
                ] = case_minimum
                selected = []
                seen_paths: set[str] = set()
                for rank, result in enumerate(bundle.results, start=1):
                    path = str(result.file_path)
                    entry = {
                        "rank": rank,
                        "path": path,
                        "graph_origin": (
                            "graph_imports_match" in result.score_parts
                        ),
                        "relation_slot": "relation slot" in result.reasons,
                        "relation_witness": None,
                    }
                    if entry["graph_origin"]:
                        entry["relation_witness"] = _import_witness(
                            index_db, path
                        )
                    selected.append(entry)
                    seen_paths.add(path)
                required_rows = []
                for item in case["required"]:
                    rank = next(
                        (
                            entry["rank"]
                            for entry in selected
                            if entry["path"] == item["path"]
                        ),
                        None,
                    )
                    required_rows.append(
                        {
                            "path": item["path"],
                            "role": item["role"],
                            "rank": rank,
                            "state": "selected" if rank else "not_selected",
                        }
                    )
                capture_payload["cases"][case["id"]] = {
                    "repo": case["repo"],
                    "selected": selected,
                    "required": required_rows,
                    "contextual": case["contextual"],
                    "unique_selected_paths": len(seen_paths),
                }

            for witness in manifest["witnesses"]:
                case = next(
                    item
                    for item in manifest["cases"]
                    if item["id"] == witness["case"]
                )
                current_repository["value"] = case["repo"]
                workspace = workspaces[case["repo"]]
                record: dict = {
                    "mode": witness["mode"],
                    "case": witness["case"],
                }
                if witness["mode"] == "context_pack":
                    from context_search_tool.mcp_tools import (
                        context_search_context_tool,
                    )

                    payload = context_search_context_tool(
                        str(workspace), case["query"]
                    )
                    items = payload.get("context_pack", {}).get("items", [])
                    item_paths = {item.get("file_path") for item in items}
                    record["covered_required"] = sorted(
                        item["path"]
                        for item in case["required"]
                        if item["path"] in item_paths
                    )
                    record["item_count"] = len(items)
                else:
                    from context_search_tool.mcp_tools import (
                        context_search_explore_tool,
                    )

                    payload = context_search_explore_tool(
                        str(workspace), case["query"]
                    )
                    pack = payload.get("context_pack", {})
                    trace = payload.get("trace", {})
                    item_paths = {
                        item.get("file_path")
                        for item in pack.get("items", [])
                    }
                    record["covered_required"] = sorted(
                        item["path"]
                        for item in case["required"]
                        if item["path"] in item_paths
                    )
                    record["retrieval_calls"] = trace.get(
                        "retrieval_call_count"
                    )
                    record["final_unique_paths"] = len(item_paths)
                capture_payload["witnesses"][
                    witness["case"] + ":" + witness["mode"]
                ] = record
    finally:
        current_repository["value"] = None
        shutil.rmtree(scratch, ignore_errors=True)

    if len(descriptor_identities) != 1:
        raise ValueError("capture vector descriptor identity mismatch")
    descriptor_identity = descriptor_identities.pop()
    if embedding == "hash":
        if descriptor_identity != static_identity:
            raise ValueError("hash capture descriptor identity mismatch")
        capture_payload["embedding_identity"] = {
            "provider": "hash",
            "configured_model": config.embedding.model,
            "dimensions": config.embedding.dimensions,
            "static_config_identity": static_identity,
            "descriptor_identity": descriptor_identity,
            "canonical_model": None,
            "model_digest": None,
            "ollama_version": None,
            "input_transform_id": None,
            "pre_attestation": None,
            "post_attestation": None,
        }
    else:
        post_attestation = attestation_provider.assert_runtime_unchanged()
        if (
            pre_attestation != post_attestation
            or descriptor_identity
            != pre_attestation.get("embedding_identity")
        ):
            raise ValueError("BGE capture runtime identity mismatch")
        capture_payload["embedding_identity"] = {
            "provider": "bge",
            "configured_model": config.embedding.model,
            "dimensions": config.embedding.dimensions,
            "static_config_identity": static_identity,
            "descriptor_identity": descriptor_identity,
            "canonical_model": pre_attestation["canonical_model"],
            "model_digest": pre_attestation["model_digest"],
            "ollama_version": pre_attestation["ollama_version"],
            "input_transform_id": pre_attestation["input_transform_id"],
            "pre_attestation": pre_attestation,
            "post_attestation": post_attestation,
        }

    capture_payload["timing"]["query_p50_seconds"] = _nearest_rank(
        latencies, 0.50
    )
    capture_payload["timing"]["query_p95_seconds"] = _nearest_rank(
        latencies, 0.95
    )
    rendered = _canonical(capture_payload)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(rendered, encoding="utf-8")
    return capture_payload


def _required_items(capture_payload: dict) -> list[tuple[str, str, str, str]]:
    items = []
    for case_id, case in sorted(capture_payload["cases"].items()):
        for row in case["required"]:
            items.append((case["repo"], case_id, row["path"], row["role"]))
    return items


def _required_rank(capture_payload: dict, item: tuple[str, str, str, str]) -> int:
    repo, case_id, path, _role = item
    case = capture_payload["cases"][case_id]
    for row in case["required"]:
        if row["path"] == path:
            return row["rank"] if row["rank"] else SENTINEL_RANK
    return SENTINEL_RANK


def _noise_counts(capture_payload: dict) -> tuple[int, int, dict[str, int]]:
    noise_total = 0
    selected_total = 0
    per_case: dict[str, int] = {}
    for case_id, case in capture_payload["cases"].items():
        relevant = {row["path"] for row in case["required"]} | set(
            case["contextual"]
        )
        case_noise = sum(
            1
            for entry in case["selected"]
            if entry["path"] not in relevant
        )
        per_case[case_id] = case_noise
        noise_total += case_noise
        selected_total += len(case["selected"])
    return noise_total, selected_total, per_case


def compare(baseline: dict, candidate: dict, output_path: Path | None = None) -> dict:
    if baseline["manifest_sha256"] != candidate["manifest_sha256"]:
        raise ValueError("gold manifest changed between baseline and candidate")

    items = _required_items(candidate)
    assert items == _required_items(baseline)
    total = len(items)

    def recall(capture_payload: dict, repo: str | None = None) -> float:
        chosen = [
            item
            for item in items
            if repo is None or item[0] == repo
        ]
        hit = sum(
            1
            for item in chosen
            if _required_rank(capture_payload, item) <= 12
        )
        return hit / len(chosen)

    gates: dict[str, bool] = {}
    per_repo = {}
    for repo in ("redink", "daily"):
        per_repo[repo] = {
            "baseline_recall": recall(baseline, repo),
            "candidate_recall": recall(candidate, repo),
        }
    gates["gate1_recall_non_decreasing"] = all(
        row["candidate_recall"] >= row["baseline_recall"] - 1e-9
        for row in per_repo.values()
    )

    newly_satisfied = []
    lost_required = []
    credited_cases: set[str] = set()
    for item in items:
        base_rank = _required_rank(baseline, item)
        cand_rank = _required_rank(candidate, item)
        repo, case_id, path, role = item
        cand_case = candidate["cases"][case_id]
        entry = next(
            (
                selected
                for selected in cand_case["selected"]
                if selected["path"] == path
            ),
            None,
        )
        credited = bool(
            entry
            and entry.get("relation_slot")
            and entry["relation_witness"]
        )
        if base_rank > 12 and cand_rank <= 12:
            newly_satisfied.append(
                {"item": list(item), "credited": credited}
            )
            if credited:
                credited_cases.add(case_id)
        elif credited and base_rank - cand_rank >= 3:
            credited_cases.add(case_id)
        if base_rank <= 12 and cand_rank > 12:
            lost_required.append(list(item))

    credited_gain = sum(1 for row in newly_satisfied if row["credited"])
    combined_delta = recall(candidate) - recall(baseline)
    gates["gate2_credited_gain_at_least_5pct"] = (
        credited_gain / total >= 0.05 - 1e-9
        and combined_delta >= credited_gain / total - 1e-9
    )
    gates["gate3_no_required_falls_out"] = not lost_required
    gates["gate4_four_credited_case_improvements"] = len(credited_cases) >= 4
    gates["gate5_three_daily_qualifying"] = (
        sum(
            1
            for case_id in credited_cases
            if candidate["cases"][case_id]["repo"] == "daily"
        )
        >= 3
    )

    relation_supported_cases = {
        case_id: candidate["cases"][case_id]["repo"]
        for case_id, case in candidate["cases"].items()
        if any(
            entry["graph_origin"] and entry["relation_witness"]
            for entry in case["selected"]
        )
    }
    gates["gate6_relation_supported_spread"] = (
        len(relation_supported_cases) >= 6
        and sum(1 for repo in relation_supported_cases.values() if repo == "redink") >= 2
        and sum(1 for repo in relation_supported_cases.values() if repo == "daily") >= 3
    )
    gates["gate7_witnesses_are_persisted"] = all(
        entry["relation_witness"] is None
        or (
            entry["relation_witness"].get("relation_id", "").startswith("r5:")
            and entry["relation_witness"].get("target_path") == entry["path"]
        )
        for case in candidate["cases"].values()
        for entry in case["selected"]
    )

    base_noise, base_selected, base_per_case = _noise_counts(baseline)
    cand_noise, cand_selected, cand_per_case = _noise_counts(candidate)
    noise_delta = cand_noise / max(cand_selected, 1) - base_noise / max(
        base_selected, 1
    )
    gates["gate8_noise_bounded"] = noise_delta <= 0.02 + 1e-9 and all(
        cand_per_case[case_id] - base_per_case.get(case_id, 0) <= 1
        for case_id in cand_per_case
    )

    continuity = candidate["cases"]["daily-prefetch-continuity"]
    continuity_paths = {entry["path"] for entry in continuity["selected"]}
    gates["gate9_p7_continuity"] = (
        continuity["unique_selected_paths"] == len(continuity["selected"]) == 12
        and {"src/core/pipeline.py", "data_provider/base.py"} <= continuity_paths
    )

    protected_stable = all(
        baseline["cases"][case_id]["selected"][0]["path"]
        == candidate["cases"][case_id]["selected"][0]["path"]
        for case_id in candidate["cases"]
        if baseline["cases"][case_id]["selected"]
        and not baseline["cases"][case_id]["selected"][0]["graph_origin"]
    )
    gates["gate10_protected_winners_stable"] = protected_stable
    gates["gate11_deterministic_render"] = _canonical(candidate) == _canonical(
        json.loads(_canonical(candidate))
    )

    disposition = "ship" if all(gates.values()) else (
        "ranking_followup"
        if gates["gate1_recall_non_decreasing"] and gates["gate3_no_required_falls_out"]
        else "reject"
    )
    report = {
        "per_repo_recall": per_repo,
        "combined_recall": {
            "baseline": recall(baseline),
            "candidate": recall(candidate),
            "delta": combined_delta,
        },
        "required_item_total": total,
        "newly_satisfied": newly_satisfied,
        "lost_required": lost_required,
        "credited_cases": sorted(credited_cases),
        "relation_supported_cases": sorted(relation_supported_cases),
        "noise": {
            "baseline_ratio": base_noise / max(base_selected, 1),
            "candidate_ratio": cand_noise / max(cand_selected, 1),
            "delta": noise_delta,
        },
        "timing": {
            "baseline": baseline["timing"],
            "candidate": candidate["timing"],
        },
        "gates": gates,
        "disposition": disposition,
    }
    if output_path is not None:
        output_path.write_text(_canonical(report), encoding="utf-8")
    return report


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


def _privacy_failure(value: object) -> str | None:
    if isinstance(value, dict):
        for key, item in value.items():
            lowered = str(key).lower()
            if lowered in {"content", "snippet"}:
                return "source content"
            if lowered in {"query", "credential", "body"}:
                return "private field"
            failure = _privacy_failure(item)
            if failure is not None:
                return failure
        return None
    if isinstance(value, list):
        for item in value:
            failure = _privacy_failure(item)
            if failure is not None:
                return failure
        return None
    if not isinstance(value, str):
        return None
    if (
        value.startswith(("/", "\\\\"))
        or re.match(r"^[A-Za-z]:[\\/]", value)
    ):
        return "absolute path"
    if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://[^/@]+@", value):
        return "credential"
    if "P13_RAW_" in value or "P13_CREDENTIAL_" in value:
        return "private sentinel"
    return None


def _validate_implementation(value: object) -> None:
    implementation = _require_keys(
        value, _IMPLEMENTATION_KEYS, "implementation"
    )
    _require_sha256(
        implementation["tracked_diff_sha256"],
        "implementation tracked diff",
    )
    if (
        not isinstance(implementation["base_commit"], str)
        or not implementation["base_commit"]
        or not isinstance(implementation["dirty"], bool)
        or not isinstance(implementation["untracked_files"], dict)
    ):
        raise ValueError("implementation identity is invalid")
    for path, sha256 in implementation["untracked_files"].items():
        if not isinstance(path, str) or Path(path).is_absolute() or ".." in Path(path).parts:
            raise ValueError("implementation identity is invalid")
        _require_sha256(sha256, "untracked file")


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
            raise ValueError("BGE attestation is invalid")
    if (
        isinstance(attestation["dimensions"], bool)
        or not isinstance(attestation["dimensions"], int)
        or attestation["dimensions"] <= 0
    ):
        raise ValueError("BGE attestation is invalid")
    _require_sha256(attestation["model_digest"], "BGE model digest")
    return attestation


def _validate_embedding_identity(
    value: object,
    requests: dict,
) -> None:
    embedding = _require_keys(value, _IDENTITY_KEYS, "embedding identity")
    provider = embedding["provider"]
    if provider not in KNOWN_EMBEDDINGS:
        raise ValueError("unknown embedding identity")
    if (
        not isinstance(embedding["configured_model"], str)
        or not embedding["configured_model"]
        or isinstance(embedding["dimensions"], bool)
        or not isinstance(embedding["dimensions"], int)
        or embedding["dimensions"] <= 0
    ):
        raise ValueError("embedding identity is invalid")
    static_identity = _require_sha256(
        embedding["static_config_identity"],
        "static embedding identity",
    )
    descriptor_identity = embedding["descriptor_identity"]
    if not isinstance(descriptor_identity, str) or not descriptor_identity:
        raise ValueError("embedding descriptor identity is invalid")

    if provider == "hash":
        if (
            descriptor_identity != static_identity
            or any(
                embedding[field] is not None
                for field in (
                    "canonical_model",
                    "model_digest",
                    "ollama_version",
                    "input_transform_id",
                    "pre_attestation",
                    "post_attestation",
                )
            )
            or any(requests[repo] != 0 for repo in _REQUEST_KEYS)
        ):
            raise ValueError("hash embedding identity is invalid")
        return

    if any(requests[repo] <= 0 for repo in ("redink", "daily")):
        raise ValueError("BGE embedding request counts are invalid")
    pre = _validate_attestation(embedding["pre_attestation"])
    post = _validate_attestation(embedding["post_attestation"])
    if pre != post:
        raise ValueError("BGE runtime attestation changed")
    for field in (
        "configured_model",
        "canonical_model",
        "model_digest",
        "ollama_version",
        "input_transform_id",
    ):
        if embedding[field] != pre[field]:
            raise ValueError("BGE embedding identity mismatch")
    if (
        embedding["configured_model"] != "bge-m3"
        or embedding["canonical_model"] != "bge-m3:latest"
    ):
        raise ValueError("BGE embedding model identity mismatch")
    if (
        embedding["dimensions"] != pre["dimensions"]
        or descriptor_identity != pre["embedding_identity"]
    ):
        raise ValueError("BGE embedding identity mismatch")
    expected_descriptor = (
        f"bge-ollama-v1:{static_identity}:{embedding['model_digest']}:"
        f"{hashlib.sha256(embedding['ollama_version'].encode('utf-8')).hexdigest()}:"
        f"{embedding['input_transform_id']}"
    )
    if (
        descriptor_identity != expected_descriptor
        or embedding["input_transform_id"] != "bge-input-v2"
    ):
        raise ValueError("BGE embedding descriptor identity mismatch")


def _validate_case(case: object) -> None:
    row = _require_keys(case, _CASE_KEYS, "case")
    if row["repo"] not in ("redink", "daily"):
        raise ValueError("case repository is invalid")
    if not isinstance(row["contextual"], list) or not all(
        isinstance(path, str) for path in row["contextual"]
    ):
        raise ValueError("case contextual paths are invalid")
    if (
        isinstance(row["unique_selected_paths"], bool)
        or not isinstance(row["unique_selected_paths"], int)
        or row["unique_selected_paths"] < 0
    ):
        raise ValueError("case selected path count is invalid")
    if not isinstance(row["selected"], list):
        raise ValueError("case selections are invalid")
    for selected in row["selected"]:
        entry = _require_keys(selected, _SELECTED_KEYS, "selected entry")
        if (
            isinstance(entry["rank"], bool)
            or not isinstance(entry["rank"], int)
            or entry["rank"] <= 0
            or not isinstance(entry["path"], str)
            or not isinstance(entry["graph_origin"], bool)
            or not isinstance(entry["relation_slot"], bool)
        ):
            raise ValueError("selected entry is invalid")
        witness = entry["relation_witness"]
        if witness is not None:
            witness = _require_keys(
                witness, {"relation_id", "target_path"}, "relation witness"
            )
            if not all(isinstance(item, str) for item in witness.values()):
                raise ValueError("relation witness is invalid")
    if not isinstance(row["required"], list):
        raise ValueError("case required items are invalid")
    for required in row["required"]:
        item = _require_keys(required, _REQUIRED_KEYS, "required item")
        rank = item["rank"]
        if (
            not isinstance(item["path"], str)
            or not isinstance(item["role"], str)
            or item["state"] not in ("selected", "not_selected")
            or (
                rank is not None
                and (
                    isinstance(rank, bool)
                    or not isinstance(rank, int)
                    or rank <= 0
                )
            )
            or (rank is None) != (item["state"] == "not_selected")
        ):
            raise ValueError("required item is invalid")


def check(capture_path: Path) -> None:
    rendered = capture_path.read_text(encoding="utf-8")
    payload = json.loads(rendered)
    if (
        not isinstance(payload, dict)
        or payload.get("schema_version") != CAPTURE_SCHEMA_VERSION
    ):
        raise ValueError("unsupported capture schema")
    if _canonical(payload) != rendered:
        raise ValueError("capture is not canonically rendered")
    privacy_failure = _privacy_failure(payload)
    if privacy_failure is not None:
        raise ValueError(f"capture privacy violation: {privacy_failure}")
    root = _require_keys(payload, _CAPTURE_ROOT_KEYS, "capture")
    identity_provider = root.get("embedding_identity", {}).get("provider")
    if identity_provider not in KNOWN_EMBEDDINGS:
        raise ValueError("unknown embedding identity")
    if len(root["cases"]) != 18:
        raise ValueError("capture must contain all 18 gold cases")

    _validate_implementation(root["implementation"])
    environment = _require_keys(
        root["environment"], _ENVIRONMENT_KEYS, "environment"
    )
    if not all(
        isinstance(environment[field], str) and environment[field]
        for field in _ENVIRONMENT_KEYS
    ):
        raise ValueError("capture environment is invalid")
    if root["manifest_sha256"] != _manifest_or_fail()["manifest_sha256"]:
        raise ValueError("frozen gold manifest changed")

    repositories = _require_keys(
        root["repositories"], {"redink", "daily"}, "repositories"
    )
    for repository in repositories.values():
        row = _require_keys(repository, _REPOSITORY_KEYS, "repository")
        if (
            isinstance(row["selected_files"], bool)
            or not isinstance(row["selected_files"], int)
            or row["selected_files"] < 0
            or not isinstance(row["structure"], dict)
            or isinstance(row["index_sqlite_bytes"], bool)
            or not isinstance(row["index_sqlite_bytes"], int)
            or row["index_sqlite_bytes"] < 0
        ):
            raise ValueError("repository capture is invalid")

    cases = root["cases"]
    if not isinstance(cases, dict):
        raise ValueError("capture cases are invalid")
    for case in cases.values():
        _validate_case(case)
    if not isinstance(root["witnesses"], dict):
        raise ValueError("capture witnesses are invalid")

    requests = _require_keys(
        root["embedding_requests"], _REQUEST_KEYS, "embedding requests"
    )
    if any(
        isinstance(requests[key], bool)
        or not isinstance(requests[key], int)
        or requests[key] < 0
        for key in _REQUEST_KEYS
    ) or requests["total"] != requests["redink"] + requests["daily"]:
        raise ValueError("embedding request counts are invalid")
    _validate_embedding_identity(root["embedding_identity"], requests)

    timing = _require_keys(root["timing"], _TIMING_KEYS, "timing")
    index_seconds = _require_keys(
        timing["index_seconds"], {"redink", "daily"}, "index timing"
    )
    for repo, seconds in index_seconds.items():
        _require_number(seconds, f"{repo} index timing")
    case_minima = timing["query_case_min_seconds"]
    if not isinstance(case_minima, dict) or set(case_minima) != set(cases):
        raise ValueError("query timing cases do not match capture cases")
    minima = [
        _require_number(case_minima[case_id], "query case timing")
        for case_id in sorted(case_minima)
    ]
    if (
        _require_number(timing["query_p50_seconds"], "query p50")
        != _nearest_rank(minima, 0.50)
        or _require_number(timing["query_p95_seconds"], "query p95")
        != _nearest_rank(minima, 0.95)
    ):
        raise ValueError("query timing percentiles are invalid")


def main() -> int:
    command = sys.argv[1]
    if command == "capture":
        implementation_root = Path(sys.argv[2])
        repos_dir = Path(sys.argv[3])
        output_path = Path(sys.argv[4])
        reps = int(sys.argv[5]) if len(sys.argv) > 5 else 2
        embedding = sys.argv[6] if len(sys.argv) > 6 else "hash"
        capture(
            implementation_root,
            repos_dir,
            output_path,
            timing_reps=reps,
            embedding=embedding,
        )
        print(f"captured {output_path}")
        return 0
    if command == "compare":
        baseline = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
        candidate = json.loads(Path(sys.argv[3]).read_text(encoding="utf-8"))
        report = compare(baseline, candidate, Path(sys.argv[4]))
        print(json.dumps(report["gates"], indent=1, sort_keys=True))
        print("disposition:", report["disposition"])
        return 0
    if command == "check":
        check(Path(sys.argv[2]))
        print("capture verified")
        return 0
    print("usage: capture <impl_root> <repos_dir> <out> [reps] [embedding] | compare | check")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
