from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
from dataclasses import replace
from pathlib import Path
from typing import Any

from context_search_tool.config import DEFAULT_CONFIG
from p5_graph_identity import (
    EXPECTED_CASE_NEGATIVES,
    EXPECTED_CASE_POSITIVES,
    EXPECTED_DETERMINISTIC_CASES,
    GRAPH_ONLY_NEGATIVE_PATHS,
    IMPLEMENTATION_BASELINE,
    P5_CATALOG_PATH,
    P5_MANIFEST_PATH,
    P5_REAL_CATALOG_PATH,
    P5_REPOSITORIES,
    P5_SOURCE_INVENTORY,
    PRE_P5_NO_EDGE_PATH,
    PROTECTED_IDENTITIES,
    ROOT,
    assert_protected_inputs,
    canonical_json_bytes,
    frozen_input_paths,
    load_raw_p5_catalog,
    load_raw_p5_real_catalog,
    sha256_file,
    source_inventory,
)


RAW_ASSAY_PATH = ROOT / ".quality/p5-artifacts/task1-raw-assay.json"

PROTECTED_DIRECT_CASES = (
    (
        "apply-audit-endpoint",
        "tests/fixtures/java-spring-mini",
        "/apply/audit/pageEs INVOLVED_BY_ME",
        "src/main/java/com/example/audit/ApplyAuditController.java",
    ),
    (
        "workspace-service-symbol",
        "tests/fixtures/context-pack-java",
        "WorkspaceServiceImpl",
        "src/main/java/com/example/workspace/service/impl/WorkspaceServiceImpl.java",
    ),
    (
        "dashboard-controller-path",
        "tests/fixtures/real_projects/cross_language_dashboard",
        "src/main/java/com/example/dashboard/DashboardController.java",
        "src/main/java/com/example/dashboard/DashboardController.java",
    ),
    (
        "order-service-symbol",
        "tests/fixtures/real_projects/embedding_ab",
        "OrderService cancel method",
        "src/order/OrderService.java",
    ),
)

PLANNED_GRAPH_PROOFS = {
    "java-owner-flow-results": {
        "src/main/java/com/example/order/OrderService.java": "graph_calls_match",
        "src/main/java/com/example/order/DefaultOrderService.java": (
            "graph_implements_method_match"
        ),
        "src/main/java/com/example/order/OrderMapper.java": "graph_calls_match",
        "src/main/resources/mappers/OrderMapper.xml": "graph_mapped_by_match",
        "src/main/java/com/example/order/Order.java": "graph_uses_type_match",
        "src/main/java/com/example/order/OrderDto.java": "graph_uses_type_match",
    },
    "java-owner-flow-context": {
        "src/main/java/com/example/order/OrderService.java": "graph_calls_match",
        "src/main/java/com/example/order/DefaultOrderService.java": (
            "graph_implements_method_match"
        ),
        "src/main/java/com/example/order/OrderMapper.java": "graph_calls_match",
        "src/main/resources/mappers/OrderMapper.xml": "graph_mapped_by_match",
        "src/main/java/com/example/order/Order.java": "graph_uses_type_match",
        "src/main/java/com/example/order/OrderDto.java": "graph_uses_type_match",
    },
    "java-owner-test": {
        "src/test/java/com/example/order/OrderControllerTests.java": "graph_tests_match",
    },
    "java-duplicate-unit": {
        "src/main/java/com/example/order/OrderService.java": "graph_calls_match",
    },
    "vue-route-flow": {
        "src/router/index.ts": "graph_routes_to_match",
        "src/services/orderService.ts": "graph_imports_match",
        "src/stores/orderStore.ts": "graph_imports_match",
        "src/types/order.ts": "graph_imports_match",
    },
    "vue-route-exploration": {
        "src/router/index.ts": "graph_routes_to_match",
        "src/types/order.ts": "graph_imports_match",
    },
    "react-route-flow": {
        "src/routes.tsx": "graph_routes_to_match",
        "src/services/orderService.ts": "graph_imports_match",
        "src/types/order.ts": "graph_imports_match",
    },
    "generic-test-conventions": {
        path: "graph_tests_match" for path in EXPECTED_CASE_POSITIVES[
            "generic-test-conventions"
        ]
    },
}

GRAPH_ONLY_FORBIDDEN_KEYS = {
    "java-overload-ambiguous": "graph_calls_match",
    "frontend-ambiguous-import": "graph_imports_match",
}


def _paths(items: Any) -> list[str]:
    return [Path(item.file_path).as_posix() for item in items]


def _direct_score_parts(parts: dict[str, float]) -> dict[str, float]:
    excluded_fragments = (
        "semantic",
        "vector",
        "relation",
        "graph_",
        "combined",
        "rerank",
        "planner_",
    )
    return {
        key: value
        for key, value in sorted(parts.items())
        if not any(fragment in key for fragment in excluded_fragments)
    }


def _raw_item(item: Any) -> dict[str, Any]:
    return {
        "file_path": Path(item.file_path).as_posix(),
        "start_line": item.start_line,
        "end_line": item.end_line,
        "score": item.score,
        "score_parts": dict(sorted(item.score_parts.items())),
        "reasons": list(item.reasons),
    }


def _normalized_item(item: Any) -> dict[str, Any]:
    return {
        "file_path": Path(item.file_path).as_posix(),
        "start_line": item.start_line,
        "end_line": item.end_line,
        "direct_score_parts": _direct_score_parts(item.score_parts),
        "reasons": list(item.reasons),
    }


def _git_source_is_protected() -> None:
    result = subprocess.run(
        (
            "git",
            "diff",
            "--exit-code",
            IMPLEMENTATION_BASELINE,
            "--",
            "src/context_search_tool",
            "pyproject.toml",
        ),
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        raise RuntimeError("production source differs from the protected baseline")
    status = subprocess.run(
        (
            "git",
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
            "--",
            "src/context_search_tool",
            "pyproject.toml",
        ),
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    if status:
        raise RuntimeError("production source worktree must be clean")


def _assert_generation_preconditions() -> dict[str, Any]:
    assert_protected_inputs()
    _git_source_is_protected()
    catalog = load_raw_p5_catalog()
    load_raw_p5_real_catalog()
    for path in (P5_CATALOG_PATH, P5_REAL_CATALOG_PATH):
        if path.is_symlink() or not path.is_file():
            raise RuntimeError(f"unsafe P5 catalog input: {path}")
    if source_inventory() != P5_SOURCE_INVENTORY:
        raise RuntimeError("P5 source inventory differs from the reviewed inventory")

    for repo_key, relative_root in P5_REPOSITORIES.items():
        root = ROOT / relative_root
        if root.is_symlink() or not root.is_dir():
            raise RuntimeError(f"unsafe P5 repository root: {repo_key}")
        for relative in P5_SOURCE_INVENTORY[repo_key]:
            path = root / relative
            if path.is_symlink() or not path.is_file():
                raise RuntimeError(f"unsafe P5 fixture input: {path}")
            if "expected" in path.relative_to(root).parts:
                raise RuntimeError("expected outputs cannot be P5 inputs")
            if path.name == "real_acceptance.json":
                raise RuntimeError("real acceptance output cannot be a P5 input")
            if path.suffix in {".so", ".dylib", ".o"}:
                raise RuntimeError("parser objects cannot be P5 inputs")
    return catalog


def _config() -> Any:
    return replace(
        DEFAULT_CONFIG,
        retrieval=replace(DEFAULT_CONFIG.retrieval, final_top_k=12),
        embedding=replace(
            DEFAULT_CONFIG.embedding,
            provider="hash",
            model="hash-v1",
            dimensions=384,
            base_url=None,
            api_key_env=None,
        ),
        query_planner=replace(DEFAULT_CONFIG.query_planner, enabled=False),
    )


def _run_repository_assays(
    repo_key: str,
    snapshot_path: str,
    cases: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    import importlib

    from context_search_tool.context_pack import (
        build_context_pack,
        resolve_context_pack_options,
    )
    from context_search_tool.indexer import index_repository

    retrieval = importlib.import_module("context_search_tool.retrieval")
    with tempfile.TemporaryDirectory(prefix=f"cst-p5-{repo_key}-") as temp:
        repo = Path(temp) / "repo"
        shutil.copytree(ROOT / snapshot_path, repo)
        config = _config()
        index_repository(repo, config)

        raw_records: list[dict[str, Any]] = []
        normalized_records: list[dict[str, Any]] = []
        no_edge_projection: dict[str, Any] = {}
        for case in cases:
            traced = retrieval.trace_repository(repo, case["query"], config)
            if traced.trace.outcome != "complete":
                raise RuntimeError(f"baseline retrieval incomplete: {case['id']}")
            options = resolve_context_pack_options(
                config,
                context_lines=None,
                max_evidence_anchors=retrieval.evidence_anchor_top_k(12),
            )
            pack = build_context_pack(traced.bundle, options)
            result_paths = _paths(traced.bundle.results)
            anchor_paths = _paths(traced.bundle.evidence_anchors)
            pack_paths = [item.file_path for item in pack.items]
            observed_paths = set(result_paths)
            if case["mode"] in {"context_pack", "exploration"}:
                observed_paths.update(pack_paths)

            raw_record = {
                "case_id": case["id"],
                "repo_key": repo_key,
                "query": case["query"],
                "mode": case["mode"],
                "results": [_raw_item(item) for item in traced.bundle.results],
                "evidence_anchors": [
                    _raw_item(item) for item in traced.bundle.evidence_anchors
                ],
                "context_pack": {
                    "status": pack.status,
                    "item_paths": pack_paths,
                    "pack_bytes": pack.budget.pack_bytes,
                },
            }
            raw_records.append(raw_record)

            negatives = EXPECTED_CASE_NEGATIVES.get(case["id"], ())
            leaked = sorted(set(negatives).intersection(observed_paths))
            if leaked:
                raise RuntimeError(
                    f"baseline negative path present for {case['id']}: {leaked[0]}"
                )
            if case["id"] == "malformed-fallback" and result_paths[:1] != [
                "src/main/java/com/example/broken/MalformedJava.java"
            ]:
                raise RuntimeError("malformed lexical file is not the direct winner")
            if case["id"] == "no-legal-edge-compat" and result_paths[:1] != [
                "src/main/java/com/example/standalone/Standalone.java"
            ]:
                raise RuntimeError("standalone no-edge file is not the direct winner")
            if case["id"] == "vue-route-exploration":
                unexpected = {
                    "src/router/index.ts",
                    "src/types/order.ts",
                }.intersection(pack_paths)
                if unexpected:
                    raise RuntimeError(
                        "Vue initial pack contains a required initial_absent path: "
                        + sorted(unexpected)[0]
                    )

            proofs = []
            planned = PLANNED_GRAPH_PROOFS.get(case["id"], {})
            for path, match_key in planned.items():
                proofs.append(
                    {
                        "path": path,
                        "baseline": "present" if path in observed_paths else "absent",
                        "required_match_key_if_present": match_key,
                    }
                )
            expected_graph_paths = set(planned)
            required_graph_paths = set(EXPECTED_CASE_POSITIVES[case["id"]])
            if case["id"] in {
                "java-owner-flow-results",
                "java-owner-flow-context",
            }:
                required_graph_paths.remove(
                    "src/main/java/com/example/order/OrderController.java"
                )
            elif case["id"] == "vue-route-flow":
                required_graph_paths.remove("src/views/OrdersView.vue")
            elif case["id"] == "react-route-flow":
                required_graph_paths.remove("src/pages/OrdersPage.tsx")
            elif case["id"] in {
                "java-overload-ambiguous",
                "frontend-ambiguous-import",
                "malformed-fallback",
                "no-legal-edge-compat",
            }:
                required_graph_paths.clear()
            if expected_graph_paths != required_graph_paths:
                raise RuntimeError(f"incomplete planned graph proof: {case['id']}")

            normalized = {
                "case_id": case["id"],
                "repo_key": repo_key,
                "query": case["query"],
                "mode": case["mode"],
                "initial_result_paths": result_paths,
                "initial_evidence_anchor_paths": anchor_paths,
                "initial_context_pack_paths": pack_paths,
                "required_graph_proofs": proofs,
                "negative_paths": list(negatives),
                "graph_only_negative_paths": list(
                    GRAPH_ONLY_NEGATIVE_PATHS.get(case["id"], ())
                ),
                "forbidden_graph_match_key": GRAPH_ONLY_FORBIDDEN_KEYS.get(
                    case["id"]
                ),
            }
            normalized_records.append(normalized)

            if case["id"] == "no-legal-edge-compat":
                no_edge_projection = {
                    "schema_version": 1,
                    "case_id": case["id"],
                    "query": case["query"],
                    "config": {
                        "retrieval": {"final_top_k": 12},
                        "embedding": {
                            "provider": "hash",
                            "model": "hash-v1",
                            "dimensions": 384,
                        },
                        "query_planner": {"enabled": False},
                    },
                    "results": [
                        _normalized_item(item) for item in traced.bundle.results
                    ],
                    "evidence_anchors": [
                        _normalized_item(item)
                        for item in traced.bundle.evidence_anchors
                    ],
                }
        return raw_records, normalized_records, no_edge_projection


def _build_synthetic_assays(
    catalog: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    raw_records: list[dict[str, Any]] = []
    normalized_records: list[dict[str, Any]] = []
    no_edge_projection: dict[str, Any] = {}
    for repo in catalog["repos"]:
        raw, normalized, projection = _run_repository_assays(
            repo["repo_key"],
            repo["snapshot_path"],
            repo["queries"],
        )
        raw_records.extend(raw)
        normalized_records.extend(normalized)
        if projection:
            no_edge_projection = projection
    expected_ids = [item[1] for item in EXPECTED_DETERMINISTIC_CASES]
    if [item["case_id"] for item in normalized_records] != expected_ids:
        raise RuntimeError("baseline assay case order changed")
    if not no_edge_projection:
        raise RuntimeError("standalone no-edge projection was not captured")
    return raw_records, normalized_records, no_edge_projection


def _protected_direct_evidence() -> list[dict[str, Any]]:
    import importlib

    from context_search_tool.indexer import index_repository

    retrieval = importlib.import_module("context_search_tool.retrieval")
    records: list[dict[str, Any]] = []
    for case_id, snapshot, query, expected_winner in PROTECTED_DIRECT_CASES:
        with tempfile.TemporaryDirectory(prefix=f"cst-p5-protected-{case_id}-") as temp:
            repo = Path(temp) / "repo"
            shutil.copytree(ROOT / snapshot, repo)
            config = _config()
            index_repository(repo, config)
            traced = retrieval.trace_repository(repo, query, config)
            if traced.trace.outcome != "complete" or not traced.bundle.results:
                raise RuntimeError(f"protected direct assay incomplete: {case_id}")
            winner = traced.bundle.results[0]
            winner_path = Path(winner.file_path).as_posix()
            if winner_path != expected_winner:
                raise RuntimeError(
                    f"protected direct winner changed for {case_id}: {winner_path}"
                )
            direct_parts = _direct_score_parts(winner.score_parts)
            if not direct_parts:
                raise RuntimeError(f"protected direct score parts missing: {case_id}")
            records.append(
                {
                    "case_id": case_id,
                    "query": query,
                    "winner": winner_path,
                    "start_line": winner.start_line,
                    "end_line": winner.end_line,
                    "direct_score_parts": direct_parts,
                }
            )
    return records


def _write_raw_assay(value: dict[str, Any]) -> None:
    RAW_ASSAY_PATH.parent.mkdir(parents=True, exist_ok=True)
    RAW_ASSAY_PATH.write_text(
        json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _run_assay() -> tuple[dict[str, Any], dict[str, Any]]:
    catalog = _assert_generation_preconditions()
    raw, normalized, projection = _build_synthetic_assays(catalog)
    protected_direct = _protected_direct_evidence()
    _write_raw_assay(
        {
            "synthetic": raw,
            "protected_direct": protected_direct,
        }
    )
    evidence = {
        "assays": normalized,
        "protected_direct": protected_direct,
    }
    return evidence, projection


def _manifest(evidence: dict[str, Any]) -> dict[str, Any]:
    inputs = []
    paths = frozen_input_paths()
    if len(paths) != len(set(paths)):
        raise RuntimeError("P5 frozen input inventory contains duplicate paths")
    for relative in paths:
        relative_path = Path(relative)
        if relative_path.is_absolute() or ".." in relative_path.parts:
            raise RuntimeError(f"unsafe P5 frozen input path: {relative}")
        allowed = relative.startswith("tests/fixtures/p5-language-graphs/") or relative in {
            P5_CATALOG_PATH.relative_to(ROOT).as_posix(),
            P5_REAL_CATALOG_PATH.relative_to(ROOT).as_posix(),
            PRE_P5_NO_EDGE_PATH.relative_to(ROOT).as_posix(),
        }
        if not allowed or ".context-search" in relative_path.parts:
            raise RuntimeError(f"P5 frozen input escaped reviewed roots: {relative}")
        path = ROOT / relative
        inputs.append(
            {
                "path": relative,
                "sha256": sha256_file(path),
                "bytes": path.stat().st_size,
            }
        )
    return {
        "schema_version": 1,
        "implementation_baseline": IMPLEMENTATION_BASELINE,
        "excluded_outputs": [
            "tests/fixtures/p5-language-graphs/expected/**",
            "tests/fixtures/p5_language_graphs/real_acceptance.json",
        ],
        "inventory": {
            key: list(value) for key, value in P5_SOURCE_INVENTORY.items()
        },
        "inputs": inputs,
        "protected_inputs": list(PROTECTED_IDENTITIES),
        "assays": evidence["assays"],
        "evidence": {"protected_direct": evidence["protected_direct"]},
    }


def generate() -> None:
    if P5_MANIFEST_PATH.exists() or PRE_P5_NO_EDGE_PATH.exists():
        raise RuntimeError("P5 frozen output already exists; refusing to overwrite")
    evidence, projection = _run_assay()
    PRE_P5_NO_EDGE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with PRE_P5_NO_EDGE_PATH.open("xb") as output:
        output.write(canonical_json_bytes(projection))
    manifest = _manifest(evidence)
    with P5_MANIFEST_PATH.open("xb") as output:
        output.write(canonical_json_bytes(manifest))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("assay", "generate"))
    args = parser.parse_args()
    if args.command == "assay":
        evidence, projection = _run_assay()
        print(
            json.dumps(
                {
                    "assays": len(evidence["assays"]),
                    "protected_direct": len(evidence["protected_direct"]),
                    "no_edge_results": len(projection["results"]),
                    "raw_assay": RAW_ASSAY_PATH.relative_to(ROOT).as_posix(),
                },
                sort_keys=True,
            )
        )
        return
    generate()


if __name__ == "__main__":
    main()
