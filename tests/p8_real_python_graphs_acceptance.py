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
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import p8_python_graph_identity as identity
from generate_p8_python_graph_manifest import build_manifest

SENTINEL_RANK = 13
CAPTURE_SCHEMA_VERSION = 2

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


def capture(
    implementation_root: Path,
    repos_dir: Path,
    output_path: Path,
    *,
    timing_reps: int = 2,
) -> dict:
    from context_search_tool.config import DEFAULT_CONFIG
    from context_search_tool.indexer import index_repository
    from context_search_tool.retrieval import query_repository

    manifest = _manifest_or_fail()
    capture_payload: dict = {
        "schema_version": CAPTURE_SCHEMA_VERSION,
        "implementation": implementation_identity(implementation_root),
        "manifest_sha256": manifest["manifest_sha256"],
        "repositories": {},
        "cases": {},
        "witnesses": {},
        "timing": {},
    }

    workspaces: dict[str, Path] = {}
    scratch = Path(tempfile.mkdtemp(prefix="cst-p8-capture-"))
    for repo_key, spec in SOURCES.items():
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
        index_repository(workspace, DEFAULT_CONFIG)
        index_seconds = time.perf_counter() - started
        workspaces[repo_key] = workspace
        index_db = workspace / ".context-search" / "index.sqlite"
        capture_payload["repositories"][repo_key] = {
            "selected_files": len(files),
            "structure": _structural_counts(index_db),
            "index_sqlite_bytes": index_db.stat().st_size,
        }
        capture_payload["timing"][f"index_seconds_{repo_key}"] = round(
            index_seconds, 4
        )

    latencies: list[float] = []
    for case in manifest["cases"]:
        workspace = workspaces[case["repo"]]
        index_db = workspace / ".context-search" / "index.sqlite"
        bundle = None
        case_latencies = []
        for _ in range(max(1, timing_reps)):
            started = time.perf_counter()
            bundle = query_repository(workspace, case["query"], DEFAULT_CONFIG)
            case_latencies.append(time.perf_counter() - started)
        latencies.append(min(case_latencies))
        selected = []
        seen_paths: set[str] = set()
        for rank, result in enumerate(bundle.results, start=1):
            path = str(result.file_path)
            entry = {
                "rank": rank,
                "path": path,
                "graph_origin": "graph_imports_match" in result.score_parts,
                "relation_slot": "relation slot" in result.reasons,
                "relation_witness": None,
            }
            if entry["graph_origin"]:
                entry["relation_witness"] = _import_witness(index_db, path)
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
            item for item in manifest["cases"] if item["id"] == witness["case"]
        )
        workspace = workspaces[case["repo"]]
        record: dict = {"mode": witness["mode"], "case": witness["case"]}
        if witness["mode"] == "context_pack":
            from context_search_tool.mcp_tools import context_search_context_tool

            payload = context_search_context_tool(str(workspace), case["query"])
            items = payload.get("context_pack", {}).get("items", [])
            item_paths = {item.get("file_path") for item in items}
            record["covered_required"] = sorted(
                item["path"]
                for item in case["required"]
                if item["path"] in item_paths
            )
            record["item_count"] = len(items)
        else:
            from context_search_tool.mcp_tools import context_search_explore_tool

            payload = context_search_explore_tool(str(workspace), case["query"])
            pack = payload.get("context_pack", {})
            trace = payload.get("trace", {})
            item_paths = {
                item.get("file_path") for item in pack.get("items", [])
            }
            record["covered_required"] = sorted(
                item["path"]
                for item in case["required"]
                if item["path"] in item_paths
            )
            record["retrieval_calls"] = trace.get("retrieval_call_count")
            record["final_unique_paths"] = len(item_paths)
        capture_payload["witnesses"][witness["case"] + ":" + witness["mode"]] = (
            record
        )

    capture_payload["timing"]["query_latency_mean_seconds"] = round(
        sum(latencies) / len(latencies), 5
    )
    rendered = _canonical(capture_payload)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(rendered, encoding="utf-8")
    shutil.rmtree(scratch, ignore_errors=True)
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


def check(capture_path: Path) -> None:
    rendered = capture_path.read_text(encoding="utf-8")
    payload = json.loads(rendered)
    if payload["schema_version"] != CAPTURE_SCHEMA_VERSION:
        raise ValueError("unsupported capture schema")
    if _canonical(payload) != rendered:
        raise ValueError("capture is not canonically rendered")
    if "/Users/" in rendered or "/private/" in rendered or "/home/" in rendered:
        raise ValueError("capture contains an absolute path")
    for case in payload["cases"].values():
        for entry in case["selected"]:
            if "content" in entry or "snippet" in entry:
                raise ValueError("capture contains source content")
    if len(payload["cases"]) != 18:
        raise ValueError("capture must contain all 18 gold cases")


def main() -> int:
    command = sys.argv[1]
    if command == "capture":
        implementation_root = Path(sys.argv[2])
        repos_dir = Path(sys.argv[3])
        output_path = Path(sys.argv[4])
        reps = int(sys.argv[5]) if len(sys.argv) > 5 else 2
        capture(implementation_root, repos_dir, output_path, timing_reps=reps)
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
    print("usage: capture|compare|check ...")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
