from __future__ import annotations

import argparse
import json
import os
import hashlib
from pathlib import Path
import runpy
import subprocess
import sys
from textwrap import dedent

import pytest


SCRIPT = Path(__file__).with_name("p14_definition_owner_acceptance.py")
P8_MANIFEST_PATH = (
    SCRIPT.parents[1] / "tests/fixtures/p8_python_graphs/input_manifest.json"
)
P8_MANIFEST = json.loads(P8_MANIFEST_PATH.read_text(encoding="utf-8"))
P8_CASE_IDS = tuple(case["id"] for case in P8_MANIFEST["cases"])
P8_SLOTS = (
    "hash-baseline-r1",
    "hash-baseline-r2",
    "hash-candidate-r1",
    "hash-candidate-r2",
    "online-baseline-r1",
    "online-baseline-r2",
    "online-candidate-r1",
    "online-candidate-r2",
)
P1_SLOTS = (
    "vector-baseline-r1",
    "vector-baseline-r2",
    "vector-candidate-r1",
    "vector-candidate-r2",
    "hybrid-baseline-r1",
    "hybrid-baseline-r2",
    "hybrid-candidate-r1",
    "hybrid-candidate-r2",
)
P1_CASES = (
    (
        "java_spring_mini",
        "apply-audit-endpoint",
        "src/main/java/com/example/audit/ResourceApplyAuditController.java",
        (),
    ),
    (
        "java_spring_mini",
        "audit-status-literal",
        "src/main/java/com/example/audit/AuditStatus.java",
        (),
    ),
    (
        "cross_language_dashboard",
        "dashboard-cross-language",
        "src/main/java/com/example/dashboard/DashboardController.java",
        ("cross_language",),
    ),
    (
        "cross_language_dashboard",
        "dashboard-controller-path",
        "src/main/java/com/example/dashboard/DashboardController.java",
        (),
    ),
    (
        "embedding_ab",
        "access-validation-cross-language",
        "src/access/WhitelistValidation.java",
        ("cross_language",),
    ),
    (
        "embedding_ab",
        "blacklist-management-cross-language",
        "src/access/BlacklistManager.java",
        ("cross_language",),
    ),
    (
        "embedding_ab",
        "order-service-symbol",
        "src/order/OrderService.java",
        (),
    ),
)


def _identity(marker: str) -> dict[str, object]:
    return {
        "base_commit": marker * 40,
        "tracked_diff_sha256": marker * 64,
        "untracked_files": {},
        "dirty": False,
    }


def _p8_envelope(slot: str, *, attempt_id: str = "p8-initial") -> dict:
    embedding, side, repetition = slot.split("-")
    module_root = f"/synthetic/{side}/implementation/src/context_search_tool"
    return {
        "schema_version": 1,
        "capture_kind": "p8",
        "attempt_id": attempt_id,
        "side": side,
        "repeat": int(repetition[-1]),
        "embedding": embedding,
        "timing_reps": 3,
        "sources": {
            "root_dirname": "sources",
            "repositories": {
                "redink": {
                    "dir_name": "RedInk",
                    "selected_files": 28,
                    "inventory_sha256": "1" * 64,
                    "content_sha256": "2" * 64,
                },
                "daily": {
                    "dir_name": "daily_stock_analysis",
                    "selected_files": 203,
                    "inventory_sha256": "3" * 64,
                    "content_sha256": "4" * 64,
                },
            },
        },
        "implementation": _identity("a" if side == "baseline" else "b"),
        "module_origins": {
            "identifier_intent": f"{module_root}/identifier_intent.py",
            "ranking": f"{module_root}/retrieval_core/ranking.py",
            "context_expansion": (
                f"{module_root}/retrieval_core/context_expansion.py"
            ),
        },
        "orchestrator_process_pid": 10,
        "capture_process_pid": 11,
        "report": {},
    }


def _write_p8_capture_set(tmp_path: Path) -> dict[str, Path]:
    paths = {}
    for slot in P8_SLOTS:
        path = tmp_path / f"{slot}.json"
        path.write_text(
            json.dumps(_p8_envelope(slot), sort_keys=True),
            encoding="utf-8",
        )
        paths[slot] = path
    return paths


def _p1_envelope(slot: str, catalog_sha256: str) -> dict:
    profile, side, repetition = slot.split("-")
    module_root = f"/synthetic/{side}/implementation/src/context_search_tool"
    return {
        "schema_version": 1,
        "capture_kind": "p1",
        "attempt_id": "p1-initial",
        "side": side,
        "repeat": int(repetition[-1]),
        "profile": f"p1_{profile}_bge",
        "catalog": {
            "filename": "queries.json",
            "sha256": catalog_sha256,
        },
        "implementation": _identity("a" if side == "baseline" else "b"),
        "module_origins": {
            "identifier_intent": f"{module_root}/identifier_intent.py",
            "ranking": f"{module_root}/retrieval_core/ranking.py",
            "context_expansion": (
                f"{module_root}/retrieval_core/context_expansion.py"
            ),
        },
        "orchestrator_process_pid": 10,
        "capture_process_pid": 11,
        "report": {},
    }


def _write_p1_capture_set(
    tmp_path: Path,
    catalog_sha256: str,
) -> dict[str, Path]:
    paths = {}
    for slot in P1_SLOTS:
        path = tmp_path / f"{slot}.json"
        path.write_text(
            json.dumps(_p1_envelope(slot, catalog_sha256), sort_keys=True),
            encoding="utf-8",
        )
        paths[slot] = path
    return paths


def _invoke_compare_p1(
    paths: dict[str, Path],
    catalog: Path,
    output: Path,
) -> subprocess.CompletedProcess[str]:
    arguments = [
        sys.executable,
        "-P",
        str(SCRIPT),
        "compare-p1",
        "--attempt-id",
        "p1-initial",
        "--catalog",
        str(catalog),
    ]
    for slot in P1_SLOTS:
        arguments.extend((f"--{slot}", str(paths[slot])))
    arguments.extend(("--output", str(output)))
    return subprocess.run(
        arguments,
        check=False,
        capture_output=True,
        text=True,
    )


def _invoke_compare_p8(
    paths: dict[str, Path],
    inventory: Path,
    output: Path,
) -> subprocess.CompletedProcess[str]:
    arguments = [
        sys.executable,
        "-P",
        str(SCRIPT),
        "compare-p8",
        "--attempt-id",
        "p8-initial",
        "--eligible-inventory",
        str(inventory),
    ]
    for slot in P8_SLOTS:
        arguments.extend((f"--{slot}", str(paths[slot])))
    arguments.extend(("--output", str(output)))
    return subprocess.run(
        arguments,
        check=False,
        capture_output=True,
        text=True,
    )


def _eligible_inventory(case_ids: tuple[str, ...] = ()) -> dict:
    return {
        "schema_version": 1,
        "behavior_baseline": "a" * 40,
        "counts": {"p8_manifest_queries": 18},
        "eligible_keys": [],
        "exact_queries": [],
        "grammar": {
            "camel_pascal": (
                "(?:[A-Z]{2,}(?=[A-Z][a-z])[A-Za-z0-9]*|"
                "[A-Z]?[a-z]+(?:[A-Z][A-Za-z0-9]*)+)"
            ),
            "lower_snake": "[a-z][a-z0-9]+(?:_[a-z0-9]+)+",
            "screaming_snake": "[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+",
            "whole_trimmed_query_only": True,
        },
        "p8_eligible_case_ids": list(case_ids),
        "sources": [
            {
                "kind": "p8_manifest",
                "path": "tests/fixtures/p8_python_graphs/input_manifest.json",
                "query_count": 18,
                "sha256": hashlib.sha256(
                    P8_MANIFEST_PATH.read_bytes()
                ).hexdigest(),
            }
        ],
    }


def _p8_report(
    embedding: str,
    identity: dict[str, object],
    *,
    query_p95: float,
) -> dict:
    cases = {}
    for index, case_id in enumerate(P8_CASE_IDS):
        case_spec = P8_MANIFEST["cases"][index]
        assert case_spec["id"] == case_id
        target = case_spec["required"][0]["path"]
        target_score = 1.0
        target_reasons = ["baseline reason"]
        cases[case_id] = {
            "repo": case_spec["repo"],
            "selected": [
                {
                    "rank": 1,
                    "path": target,
                    "score": target_score,
                    "score_parts": {"score": target_score},
                    "reasons": target_reasons,
                    "graph_origin": False,
                    "relation_slot": False,
                    "relation_witness": None,
                },
                {
                    "rank": 2,
                    "path": f"noise-{index:02d}.py",
                    "score": 0.5,
                    "score_parts": {"score": 0.5},
                    "reasons": ["noise"],
                    "graph_origin": False,
                    "relation_slot": False,
                    "relation_witness": None,
                },
            ],
            "required": [
                {
                    "path": required["path"],
                    "role": required["role"],
                    "rank": 1 if required["path"] == target else None,
                    "state": (
                        "selected"
                        if required["path"] == target
                        else "not_selected"
                    ),
                }
                for required in case_spec["required"]
            ],
            "contextual": list(case_spec["contextual"]),
            "unique_selected_paths": 2,
        }
    requests = (
        {"redink": 0, "daily": 0, "total": 0}
        if embedding == "hash"
        else {"redink": 2, "daily": 3, "total": 5}
    )
    return {
        "schema_version": 4,
        "implementation": identity,
        "environment": {
            "python_version": "3.13.12",
            "sqlite_version": "3.51.2",
            "numpy_version": "2.4.2",
        },
        "manifest_sha256": P8_MANIFEST["manifest_sha256"],
        "embedding_identity": {
            "provider": (
                "hash" if embedding == "hash" else "openai-compatible"
            ),
            "configured_model": (
                "hash-v1" if embedding == "hash" else "Pro/BAAI/bge-m3"
            ),
            "dimensions": 384 if embedding == "hash" else 1024,
            "static_config_identity": "1" * 64,
            "descriptor_identity": "1" * 64,
            "base_url": (
                None
                if embedding == "hash"
                else "https://api.siliconflow.cn/v1"
            ),
            "canonical_model": (
                None if embedding == "hash" else "Pro/BAAI/bge-m3"
            ),
            "model_digest": None,
            "ollama_version": None,
            "input_transform_id": None,
            "pre_attestation": (
                None
                if embedding == "hash"
                else {
                    "provider": "openai-compatible",
                    "configured_model": "Pro/BAAI/bge-m3",
                    "dimensions": 1024,
                    "base_url": "https://api.siliconflow.cn/v1",
                }
            ),
            "post_attestation": (
                None
                if embedding == "hash"
                else {
                    "provider": "openai-compatible",
                    "configured_model": "Pro/BAAI/bge-m3",
                    "dimensions": 1024,
                    "base_url": "https://api.siliconflow.cn/v1",
                }
            ),
        },
        "repositories": {
            repo: {
                "selected_files": count,
                "structure": {
                    "active_chunks": count,
                    "signals_by_producer": {},
                    "relations_by_kind_resolution": {},
                },
                "index_sqlite_bytes": count * 100,
            }
            for repo, count in (("redink", 28), ("daily", 203))
        },
        "cases": cases,
        "witnesses": {},
        "embedding_requests": requests,
        "timing": {
            "index_seconds": {"redink": 1.0, "daily": 2.0},
            "query_case_min_seconds": {
                case_id: query_p95 for case_id in cases
            },
            "query_p50_seconds": query_p95,
            "query_p95_seconds": query_p95,
        },
    }


def _write_valid_p8_capture_set(tmp_path: Path) -> dict[str, Path]:
    paths = {}
    timings = {
        ("baseline", 1): 1.0,
        ("baseline", 2): 1.1,
        ("candidate", 1): 1.05,
        ("candidate", 2): 1.05,
    }
    for slot in P8_SLOTS:
        embedding, side, repetition = slot.split("-")
        envelope = _p8_envelope(slot)
        envelope["report"] = _p8_report(
            embedding,
            envelope["implementation"],
            query_p95=timings[(side, int(repetition[-1]))],
        )
        path = tmp_path / f"{slot}.json"
        path.write_text(json.dumps(envelope, sort_keys=True), encoding="utf-8")
        paths[slot] = path
    return paths


def _p1_report(
    profile: str,
    catalog_sha256: str,
    *,
    candidate: bool,
    repetition: int,
    tool_commit: str,
    fixture_path: str,
    fixture_case_count: int,
    case_queries: dict[tuple[str, str], str],
    case_tags: dict[tuple[str, str], list[str]],
    case_relevant_paths: dict[tuple[str, str], list[str]],
) -> dict:
    is_hybrid = profile == "p1_hybrid_bge"
    cases = []
    for repo_key, case_id, target, _declared_tags in P1_CASES:
        query = case_queries[(repo_key, case_id)]
        tags = case_tags[(repo_key, case_id)]
        owner_case = case_id == "audit-status-literal"
        dashboard_case = case_id == "dashboard-cross-language"
        rank = (
            2
            if dashboard_case or (candidate and owner_case)
            else (5 if owner_case else 1)
        )
        top_results = [
            {
                "rank": result_rank,
                "path": f"{case_id}-filler-{result_rank}.java",
                "score": 1.0 / result_rank,
                "score_parts": {"score": 1.0 / result_rank},
                "reasons": ["synthetic"],
                "semantic_matches": [],
            }
            for result_rank in range(1, rank)
        ]
        if dashboard_case:
            top_results[0]["path"] = next(
                path
                for path in case_relevant_paths[(repo_key, case_id)]
                if path != target
            )
        top_results.append(
            {
                "rank": rank,
                "path": target,
                "score": 1.0 / rank,
                "score_parts": {"score": 1.0 / rank},
                "reasons": ["target"],
                "semantic_matches": [],
            }
        )
        relevant_paths = set(case_relevant_paths[(repo_key, case_id)])
        relevant_rank = next(
            result["rank"]
            for result in top_results
            if result["path"] in relevant_paths
        )
        cases.append(
            {
                "repo_key": repo_key,
                "case_id": case_id,
                "query": query,
                "gate": "required",
                "tags": list(tags),
                "attempted": True,
                "status": "pass" if candidate or not owner_case else "fail",
                "known_gap_reason": "",
                "planner": {
                    "status": "ok" if is_hybrid else "disabled",
                    "provider": "openai-compatible" if is_hybrid else "",
                    "model": (
                        "Qwen/Qwen2.5-14B-Instruct" if is_hybrid else ""
                    ),
                    "latency_ms": 10 + repetition if is_hybrid else None,
                    "rewritten_queries": (
                        [f"nondeterministic-{repetition}"]
                        if is_hybrid
                        else []
                    ),
                    "grep_keywords": [],
                    "symbol_hints": [],
                    "discarded_hints": [],
                    "prompt_version": "synthetic" if is_hybrid else "",
                    "prompt_hash": "synthetic" if is_hybrid else "",
                    "repo_profile_hash": "synthetic" if is_hybrid else "",
                    "repo_profile_truncated": False,
                },
                "query_variants": [
                    {
                        "variant_id": "original",
                        "text": query,
                        "source": "original",
                    }
                ],
                "expanded_tokens": [],
                "variant_retrieval_status": (
                    "hybrid"
                    if is_hybrid and "cross_language" in tags
                    else "original_only"
                ),
                "top_results": top_results,
                "failures": [] if candidate or not owner_case else ["rank"],
                "metrics": {
                    "result_count": len(top_results),
                    "hit_at_1": relevant_rank == 1,
                    "hit_at_3": relevant_rank <= 3,
                    "hit_at_5": relevant_rank <= 5,
                    "hit_at_10": relevant_rank <= 10,
                    "mrr": 1.0 / relevant_rank,
                    "recall_at_5": 1.0 if relevant_rank <= 5 else 0.0,
                    "recall_at_10": 1.0 if relevant_rank <= 10 else 0.0,
                    "expected_coverage_top5": {
                        "count": 1 if rank <= 5 else 0,
                        "ratio": 1.0 if rank <= 5 else 0.0,
                    },
                    "entrypoint_rank": (
                        rank if "entrypoint" in tags else None
                    ),
                    "preferred_rank_pass": rank <= 5,
                    "noise_top5": 0,
                    "noise_top10": 0,
                    "cross_language_success": (
                        True if "cross_language" in tags else None
                    ),
                    "top_score": top_results[0]["score"],
                    "latency_ms": 100 + repetition,
                },
            }
        )
    passed = 7 if candidate else 6
    overall_mrr = sum(case["metrics"]["mrr"] for case in cases) / len(cases)
    overall_recall_at_5 = (
        sum(case["metrics"]["recall_at_5"] for case in cases) / len(cases)
    )
    entrypoint_cases = [
        case for case in cases if "entrypoint" in case["tags"]
    ]
    entrypoint_successes = sum(
        case["metrics"]["entrypoint_rank"] <= 3
        for case in entrypoint_cases
    )
    return {
        "schema_version": 2,
        "generated_at": f"repeat-{repetition}",
        "command_args": {"fixture_path": fixture_path, "profile": profile},
        "tool": {"name": "context-search-tool", "git_commit": tool_commit},
        "fixture": {
            "path": fixture_path,
            "sha256": catalog_sha256,
            "schema_version": 1,
            "fixture_case_count": fixture_case_count,
            "run_case_count": 7,
        },
        "profile": profile,
        "config": {
            "config_hash": "sha256:" + "c" * 64,
            "embedding": {
                "provider": "openai-compatible",
                "model": "Pro/BAAI/bge-m3",
                "dimensions": 1024,
                "base_url": "https://api.siliconflow.cn/v1",
                "api_key_env": None,
            },
        },
        "planner": {
            "enabled": is_hybrid,
            "provider": "openai-compatible",
            "model": "Qwen/Qwen2.5-14B-Instruct",
            "base_url": "https://api.siliconflow.cn/v1",
            "timeout_seconds": 60.0,
            "use_system_proxy": False,
            "max_rewritten_queries": 4,
            "max_keywords": 12,
            "max_symbol_hints": 8,
        },
        "aggregate": {
            "total": 7,
            "selected": 7,
            "attempted": 7,
            "executed": 7,
            "passed": passed,
            "failed": 7 - passed,
            "skipped": 0,
            "errors": 0,
            "known_gaps": 0,
            "informational": 0,
            "metrics": {
                "overall": {
                    "mrr": {"count": 7, "mean": overall_mrr},
                    "recall_at_5": {
                        "count": 7,
                        "mean": overall_recall_at_5,
                    },
                    "entrypoint_top3": {
                        "successes": entrypoint_successes,
                        "total": len(entrypoint_cases),
                        "rate": entrypoint_successes / len(entrypoint_cases),
                    },
                    "latency_ms": {"p95": 100 + repetition},
                }
            },
        },
        "repos": [],
        "cases": cases,
    }


def _write_valid_p1_capture_set(
    tmp_path: Path,
    catalog: Path,
) -> dict[str, Path]:
    catalog_sha256 = "sha256:" + hashlib.sha256(catalog.read_bytes()).hexdigest()
    catalog_payload = json.loads(catalog.read_text(encoding="utf-8"))
    fixture_case_count = sum(
        len(repository["queries"])
        for repository in catalog_payload["repos"]
    )
    selected_cases = {
        (repo_key, case_id)
        for repo_key, case_id, _target, _tags in P1_CASES
    }
    case_queries = {
        (repository["repo_key"], query["id"]): query["query"]
        for repository in catalog_payload["repos"]
        for query in repository["queries"]
        if (repository["repo_key"], query["id"]) in selected_cases
    }
    case_tags = {
        (repository["repo_key"], query["id"]): list(query.get("tags", []))
        for repository in catalog_payload["repos"]
        for query in repository["queries"]
        if (repository["repo_key"], query["id"]) in selected_cases
    }
    case_relevant_paths = {
        (repository["repo_key"], query["id"]): [
            *(
                item["path"]
                for item in query["expected_top_k"]
            ),
            *(
                matcher["path"]
                for group in query.get("expected_any_top_k", [])
                for matcher in group.get("matchers", [])
            ),
        ]
        for repository in catalog_payload["repos"]
        for query in repository["queries"]
        if (repository["repo_key"], query["id"]) in selected_cases
    }
    paths = {}
    for slot in P1_SLOTS:
        profile, side, repetition = slot.split("-")
        envelope = _p1_envelope(slot, catalog_sha256)
        implementation_root = Path(
            envelope["module_origins"]["identifier_intent"]
        ).parents[2]
        fixture_path = str(
            implementation_root
            / "tests/fixtures/retrieval_quality/queries.json"
        )
        envelope["report"] = _p1_report(
            f"p1_{profile}_bge",
            catalog_sha256,
            candidate=side == "candidate",
            repetition=int(repetition[-1]),
            tool_commit=envelope["implementation"]["base_commit"],
            fixture_path=fixture_path,
            fixture_case_count=fixture_case_count,
            case_queries=case_queries,
            case_tags=case_tags,
            case_relevant_paths=case_relevant_paths,
        )
        path = tmp_path / f"{slot}.json"
        path.write_text(json.dumps(envelope, sort_keys=True), encoding="utf-8")
        paths[slot] = path
    return paths


def _recompute_p1_overall(report: dict) -> None:
    cases = report["cases"]
    overall = report["aggregate"]["metrics"]["overall"]
    overall["mrr"] = {
        "count": len(cases),
        "mean": sum(case["metrics"]["mrr"] for case in cases) / len(cases),
    }
    overall["recall_at_5"] = {
        "count": len(cases),
        "mean": (
            sum(case["metrics"]["recall_at_5"] for case in cases) / len(cases)
        ),
    }
    entrypoint_cases = [
        case for case in cases if "entrypoint" in case["tags"]
    ]
    successes = sum(
        case["metrics"]["entrypoint_rank"] <= 3
        for case in entrypoint_cases
    )
    overall["entrypoint_top3"] = {
        "successes": successes,
        "total": len(entrypoint_cases),
        "rate": successes / len(entrypoint_cases),
    }


def _write_fake_implementation(tmp_path: Path) -> Path:
    root = tmp_path / "implementation"
    package = root / "src/context_search_tool"
    retrieval_core = package / "retrieval_core"
    quality = package / "quality"
    retrieval_core.mkdir(parents=True)
    quality.mkdir()
    for path in (
        package / "__init__.py",
        retrieval_core / "__init__.py",
        quality / "__init__.py",
        package / "identifier_intent.py",
        retrieval_core / "ranking.py",
        retrieval_core / "context_expansion.py",
    ):
        path.write_text("", encoding="utf-8")
    (quality / "runner.py").write_text(
        dedent(
            """
            import json
            import os


            P14_FAKE_RUNNER = True


            def run_quality_fixture(
                fixture,
                *,
                profile,
                output_path,
                markdown_path,
                allow_empty,
                repos_dir,
            ):
                report = {
                    "schema_version": 2,
                    "fixture": {"sha256": "sha256:fixture"},
                    "profile": profile,
                    "planner": {"status": "disabled", "fallback": False},
                    "aggregate": {
                        "selected": 0,
                        "executed": 0,
                        "passed": 0,
                        "failed": 0,
                        "skipped": 0,
                        "errors": 0,
                    },
                    "cases": [],
                    "capture_process_pid": os.getpid(),
                }
                output_path.write_text(
                    json.dumps(report, sort_keys=True),
                    encoding="utf-8",
                )
                markdown_path.write_text("# Fake report\\n", encoding="utf-8")
                return report
            """
        ),
        encoding="utf-8",
    )
    subprocess.run(("git", "init", "-q", str(root)), check=True)
    subprocess.run(
        ("git", "-C", str(root), "config", "user.name", "P14 Test"),
        check=True,
    )
    subprocess.run(
        ("git", "-C", str(root), "config", "user.email", "p14@example.invalid"),
        check=True,
    )
    subprocess.run(("git", "-C", str(root), "add", "."), check=True)
    subprocess.run(
        ("git", "-C", str(root), "commit", "-qm", "fixture"),
        check=True,
    )
    return root


def _add_fake_p8_runner(implementation: Path) -> None:
    (implementation / "src/context_search_tool/retrieval.py").write_text(
        dedent(
            """
            from pathlib import Path


            class Result:
                file_path = Path("Owner.py")
                score = 1.25
                score_parts = {"z_part": 2.0, "a_part": 1.0}
                reasons = ("first reason", "second reason")


            class Bundle:
                results = (Result(),)


            def query_repository(*args, **kwargs):
                return Bundle()
            """
        ),
        encoding="utf-8",
    )
    tests = implementation / "tests"
    tests.mkdir()
    (tests / "p8_real_python_graphs_acceptance.py").write_text(
        dedent(
            """
            import hashlib
            import json
            import os
            from pathlib import Path
            import subprocess


            P14_FAKE_RUNNER = True


            _ROOT_KEYS = {
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
            SOURCES = {
                "redink": {
                    "dir_name": "RedInk",
                    "expected_count": 1,
                    "inventory_sha256": "a" * 64,
                    "content_sha256": "b" * 64,
                },
                "daily": {
                    "dir_name": "daily_stock_analysis",
                    "expected_count": 2,
                    "inventory_sha256": "c" * 64,
                    "content_sha256": "d" * 64,
                },
            }


            def _canonical(payload):
                return json.dumps(payload, indent=1, sort_keys=True) + "\\n"


            def _git(root, *arguments):
                return subprocess.run(
                    ("git", "-C", str(root), *arguments),
                    check=True,
                    capture_output=True,
                    text=True,
                ).stdout.strip()


            def implementation_identity(root):
                diff = _git(
                    root, "diff", "--binary", "HEAD", "--", "src", "tests"
                )
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
                    relative: hashlib.sha256(
                        (root / relative).read_bytes()
                    ).hexdigest()
                    for relative in sorted(filter(None, listed.splitlines()))
                }
                return {
                    "base_commit": _git(root, "rev-parse", "HEAD"),
                    "tracked_diff_sha256": hashlib.sha256(
                        diff.encode()
                    ).hexdigest(),
                    "untracked_files": untracked,
                    "dirty": bool(diff or untracked),
                }


            def _manifest_or_fail():
                return {
                    "manifest_sha256": "frozen-manifest",
                    "cases": [
                        {
                            "id": "exact-owner",
                            "repo": "redink",
                            "query": "OwnerController",
                            "required": [
                                {"path": "Owner.py", "role": "owner"}
                            ],
                            "contextual": [],
                        }
                    ],
                }


            def capture(
                implementation_root,
                repos_dir,
                output_path,
                *,
                timing_reps,
                embedding,
            ):
                from context_search_tool.retrieval import query_repository

                if (repos_dir / "require-isolated-global-config").exists():
                    global_config = os.environ.get("CST_GLOBAL_CONFIG_PATH")
                    if not global_config or Path(global_config).exists():
                        raise ValueError("P8 global config was not isolated")
                bundle = None
                query = (
                    "WrongQuery"
                    if (repos_dir / "wrong-query").exists()
                    else "OwnerController"
                )
                for _ in range(timing_reps):
                    bundle = query_repository(repos_dir, query)
                selected = [
                    {
                        "rank": rank,
                        "path": str(result.file_path),
                        "graph_origin": False,
                        "relation_slot": False,
                        "relation_witness": None,
                    }
                    for rank, result in enumerate(bundle.results, start=1)
                ]
                payload = {
                    "schema_version": 4,
                    "implementation": implementation_identity(
                        implementation_root
                    ),
                    "environment": {
                        "python_version": "test",
                        "sqlite_version": "test",
                        "numpy_version": "test",
                    },
                    "manifest_sha256": "frozen-manifest",
                    "embedding_identity": {
                        "provider": (
                            "openai-compatible"
                            if embedding == "online"
                            else embedding
                        ),
                        "static_config_identity": "static",
                        "descriptor_identity": "descriptor",
                    },
                    "repositories": {
                        "redink": {
                            "selected_files": 1,
                            "structure": {"active_chunks": 1},
                            "index_sqlite_bytes": 1,
                        }
                    },
                    "cases": {
                        "exact-owner": {
                            "repo": "redink",
                            "selected": selected,
                            "required": [
                                {
                                    "path": "Owner.py",
                                    "role": "owner",
                                    "rank": 1,
                                    "state": "selected",
                                }
                            ],
                            "contextual": [],
                            "unique_selected_paths": 1,
                        }
                    },
                    "witnesses": {},
                    "embedding_requests": {
                        "redink": 0,
                        "daily": 0,
                        "total": 0,
                    },
                    "timing": {
                        "index_seconds": {"redink": 0.1},
                        "query_case_min_seconds": {"exact-owner": 0.01},
                        "query_p50_seconds": 0.01,
                        "query_p95_seconds": 0.01,
                    },
                }
                if (repos_dir / "malformed").exists():
                    payload["unexpected"] = True
                output_path.write_text(
                    _canonical(payload),
                    encoding="utf-8",
                )
                return payload


            def check(capture_path):
                rendered = capture_path.read_text(encoding="utf-8")
                payload = json.loads(rendered)
                if set(payload) != _ROOT_KEYS:
                    raise ValueError("legacy capture schema is not closed")
                if rendered != _canonical(payload):
                    raise ValueError("legacy capture is not canonical")
                if payload["schema_version"] != 4:
                    raise ValueError("legacy capture schema is invalid")
                if set(payload["cases"]) != {"exact-owner"}:
                    raise ValueError("legacy capture cases are invalid")
                selected = payload["cases"]["exact-owner"]["selected"]
                if any(
                    set(row)
                    != {
                        "rank",
                        "path",
                        "graph_origin",
                        "relation_slot",
                        "relation_witness",
                    }
                    for row in selected
                ):
                    raise ValueError("legacy selected schema is invalid")
                identity = payload["implementation"]
                if set(identity) != {
                    "base_commit",
                    "tracked_diff_sha256",
                    "untracked_files",
                    "dirty",
                }:
                    raise ValueError("legacy identity schema is invalid")
                if any(
                    len(sha256) != 64
                    for sha256 in identity["untracked_files"].values()
                ):
                    raise ValueError("legacy identity hash is invalid")
            """
        ),
        encoding="utf-8",
    )
    subprocess.run(
        ("git", "-C", str(implementation), "add", "src", "tests"),
        check=True,
    )
    subprocess.run(
        ("git", "-C", str(implementation), "commit", "-qm", "p8 fixture"),
        check=True,
    )


def test_importing_harness_does_not_import_production_modules(
    tmp_path: Path,
) -> None:
    probe = subprocess.run(
        (
            sys.executable,
            "-P",
            "-c",
            (
                "import json,runpy,sys;"
                "before=set(sys.modules);"
                f"runpy.run_path({str(SCRIPT)!r},run_name='p14_import_probe');"
                "print(json.dumps(sorted("
                "name for name in set(sys.modules)-before "
                "if name.startswith('context_search_tool')"
                ")))"
            ),
        ),
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )

    assert probe.returncode == 0, probe.stderr
    assert json.loads(probe.stdout) == []


@pytest.mark.parametrize(
    ("command", "required_options"),
    (
        (
            "capture-p8",
            (
                "--attempt-id",
                "--side",
                "--repeat",
                "--implementation-root",
                "--sources",
                "--embedding",
                "--timing-reps",
                "--output",
            ),
        ),
        (
            "capture-p1",
            (
                "--attempt-id",
                "--side",
                "--repeat",
                "--implementation-root",
                "--catalog",
                "--profile",
                "--output",
                "--markdown",
            ),
        ),
        (
            "compare-p8",
            (
                "--attempt-id",
                "--eligible-inventory",
                "--hash-baseline-r1",
                "--hash-baseline-r2",
                "--hash-candidate-r1",
                "--hash-candidate-r2",
                "--online-baseline-r1",
                "--online-baseline-r2",
                "--online-candidate-r1",
                "--online-candidate-r2",
                "--output",
            ),
        ),
        (
            "compare-p1",
            (
                "--attempt-id",
                "--catalog",
                "--vector-baseline-r1",
                "--vector-baseline-r2",
                "--vector-candidate-r1",
                "--vector-candidate-r2",
                "--hybrid-baseline-r1",
                "--hybrid-baseline-r2",
                "--hybrid-candidate-r1",
                "--hybrid-candidate-r2",
                "--output",
            ),
        ),
    ),
)
def test_cli_freezes_public_commands_and_required_options(
    command: str,
    required_options: tuple[str, ...],
) -> None:
    completed = subprocess.run(
        (sys.executable, "-P", str(SCRIPT), command, "--help"),
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert all(option in completed.stdout for option in required_options)


def test_capture_fails_closed_without_overwriting_existing_output(
    tmp_path: Path,
) -> None:
    output = tmp_path / "capture.json"
    markdown = tmp_path / "capture.md"
    output.write_text("sentinel\n", encoding="utf-8")

    completed = subprocess.run(
        (
            sys.executable,
            "-P",
            str(SCRIPT),
            "capture-p1",
            "--attempt-id",
            "p1-initial",
            "--side",
            "baseline",
            "--repeat",
            "1",
            "--implementation-root",
            str(tmp_path / "must-not-be-read"),
            "--catalog",
            str(tmp_path / "must-not-be-read.json"),
            "--profile",
            "p1_vector_bge",
            "--output",
            str(output),
            "--markdown",
            str(markdown),
        ),
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode != 0
    assert output.read_text(encoding="utf-8") == "sentinel\n"
    assert not markdown.exists()


def test_capture_p1_uses_fresh_requested_implementation_and_writes_envelope(
    tmp_path: Path,
) -> None:
    implementation = _write_fake_implementation(tmp_path)
    catalog = implementation / "catalog.json"
    catalog.write_text('{"schema_version":1}\n', encoding="utf-8")
    output = tmp_path / "capture.json"
    markdown = tmp_path / "capture.md"

    completed = subprocess.run(
        (
            sys.executable,
            "-P",
            str(SCRIPT),
            "capture-p1",
            "--attempt-id",
            "p1-initial",
            "--side",
            "baseline",
            "--repeat",
            "1",
            "--implementation-root",
            str(implementation),
            "--catalog",
            str(catalog),
            "--profile",
            "p1_vector_bge",
            "--output",
            str(output),
            "--markdown",
            str(markdown),
        ),
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    envelope = json.loads(output.read_text(encoding="utf-8"))
    assert envelope["schema_version"] == 1
    assert envelope["capture_kind"] == "p1"
    assert envelope["attempt_id"] == "p1-initial"
    assert envelope["side"] == "baseline"
    assert envelope["repeat"] == 1
    assert envelope["profile"] == "p1_vector_bge"
    assert envelope["orchestrator_process_pid"] != envelope["capture_process_pid"]
    assert envelope["implementation"]["base_commit"]
    assert envelope["implementation"]["dirty"] is False
    assert set(envelope["module_origins"]) == {
        "identifier_intent",
        "ranking",
        "context_expansion",
    }
    assert all(
        Path(origin).is_relative_to(implementation)
        for origin in envelope["module_origins"].values()
    )
    assert envelope["report"]["profile"] == "p1_vector_bge"
    assert envelope["catalog"]["sha256"]
    assert markdown.read_text(encoding="utf-8") == "# Fake report\n"
    assert envelope["capture_process_pid"] != os.getpid()


def test_capture_p1_rejects_legacy_v1_report(tmp_path: Path) -> None:
    implementation = _write_fake_implementation(tmp_path)
    runner = implementation / "src/context_search_tool/quality/runner.py"
    runner.write_text(
        runner.read_text(encoding="utf-8").replace(
            '"schema_version": 2',
            '"schema_version": 1',
        ),
        encoding="utf-8",
    )
    catalog = implementation / "catalog.json"
    catalog.write_text('{"schema_version":1}\n', encoding="utf-8")
    output = tmp_path / "capture.json"
    markdown = tmp_path / "capture.md"

    completed = subprocess.run(
        (
            sys.executable,
            "-P",
            str(SCRIPT),
            "capture-p1",
            "--attempt-id",
            "p1-initial",
            "--side",
            "baseline",
            "--repeat",
            "1",
            "--implementation-root",
            str(implementation),
            "--catalog",
            str(catalog),
            "--profile",
            "p1_vector_bge",
            "--output",
            str(output),
            "--markdown",
            str(markdown),
        ),
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode != 0
    assert "invalid report" in completed.stderr
    assert not output.exists()
    assert not markdown.exists()


def test_capture_p8_extends_legacy_projection_in_fresh_requested_child(
    tmp_path: Path,
) -> None:
    implementation = _write_fake_implementation(tmp_path)
    _add_fake_p8_runner(implementation)
    sources = tmp_path / "sources"
    sources.mkdir()
    output = tmp_path / "capture.json"

    completed = subprocess.run(
        (
            sys.executable,
            "-P",
            str(SCRIPT),
            "capture-p8",
            "--attempt-id",
            "p8-initial",
            "--side",
            "candidate",
            "--repeat",
            "2",
            "--implementation-root",
            str(implementation),
            "--sources",
            str(sources),
            "--embedding",
            "hash",
            "--timing-reps",
            "2",
            "--output",
            str(output),
        ),
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    envelope = json.loads(output.read_text(encoding="utf-8"))
    assert envelope["capture_kind"] == "p8"
    assert envelope["attempt_id"] == "p8-initial"
    assert envelope["side"] == "candidate"
    assert envelope["repeat"] == 2
    assert envelope["embedding"] == "hash"
    assert envelope["timing_reps"] == 2
    assert envelope["orchestrator_process_pid"] != envelope["capture_process_pid"]
    assert envelope["sources"] == {
        "root_dirname": "sources",
        "repositories": {
            "daily": {
                "dir_name": "daily_stock_analysis",
                "selected_files": 2,
                "inventory_sha256": "c" * 64,
                "content_sha256": "d" * 64,
            },
            "redink": {
                "dir_name": "RedInk",
                "selected_files": 1,
                "inventory_sha256": "a" * 64,
                "content_sha256": "b" * 64,
            },
        },
    }
    selected = envelope["report"]["cases"]["exact-owner"]["selected"][0]
    assert selected == {
        "rank": 1,
        "path": "Owner.py",
        "score": 1.25,
        "score_parts": {"a_part": 1.0, "z_part": 2.0},
        "reasons": ["first reason", "second reason"],
        "graph_origin": False,
        "relation_slot": False,
        "relation_witness": None,
    }


def test_capture_p8_isolates_hash_workspace_from_global_config(
    tmp_path: Path,
) -> None:
    implementation = _write_fake_implementation(tmp_path)
    _add_fake_p8_runner(implementation)
    sources = tmp_path / "sources"
    sources.mkdir()
    (sources / "require-isolated-global-config").touch()
    global_config = tmp_path / "global-config.toml"
    global_config.write_text("[embedding]\nprovider = 'openai-compatible'\n")
    output = tmp_path / "capture.json"
    environment = os.environ.copy()
    environment["CST_GLOBAL_CONFIG_PATH"] = str(global_config)

    completed = subprocess.run(
        (
            sys.executable,
            "-P",
            str(SCRIPT),
            "capture-p8",
            "--attempt-id",
            "p8-initial",
            "--side",
            "baseline",
            "--repeat",
            "1",
            "--implementation-root",
            str(implementation),
            "--sources",
            str(sources),
            "--embedding",
            "hash",
            "--timing-reps",
            "2",
            "--output",
            str(output),
        ),
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert output.is_file()


@pytest.mark.parametrize("failure_mode", ("malformed", "wrong-query"))
def test_capture_p8_rejects_invalid_legacy_capture_before_extension(
    tmp_path: Path,
    failure_mode: str,
) -> None:
    implementation = _write_fake_implementation(tmp_path)
    _add_fake_p8_runner(implementation)
    sources = tmp_path / "sources"
    sources.mkdir()
    (sources / failure_mode).touch()
    output = tmp_path / "capture.json"

    completed = subprocess.run(
        (
            sys.executable,
            "-P",
            str(SCRIPT),
            "capture-p8",
            "--attempt-id",
            "p8-initial",
            "--side",
            "baseline",
            "--repeat",
            "1",
            "--implementation-root",
            str(implementation),
            "--sources",
            str(sources),
            "--embedding",
            "hash",
            "--timing-reps",
            "2",
            "--output",
            str(output),
        ),
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode != 0
    assert not output.exists()


def test_implementation_identity_matches_real_legacy_p8_format() -> None:
    import p8_real_python_graphs_acceptance as legacy_p8

    implementation = SCRIPT.parents[1]
    harness = runpy.run_path(str(SCRIPT), run_name="p14_identity_probe")
    actual = harness["_implementation_identity"](implementation)
    expected = legacy_p8.implementation_identity(implementation)

    assert actual == expected
    assert all(
        len(value) == 64 and not value.startswith("sha256:")
        for value in actual["untracked_files"].values()
    )


def test_compare_p8_rejects_reused_named_input(tmp_path: Path) -> None:
    capture = tmp_path / "capture.json"
    capture.write_text("{}\n", encoding="utf-8")
    inventory = tmp_path / "eligible.json"
    inventory.write_text("{}\n", encoding="utf-8")
    output = tmp_path / "gates.json"
    arguments = [
        sys.executable,
        "-P",
        str(SCRIPT),
        "compare-p8",
        "--attempt-id",
        "p8-initial",
        "--eligible-inventory",
        str(inventory),
    ]
    for slot in P8_SLOTS:
        arguments.extend((f"--{slot}", str(capture)))
    arguments.extend(("--output", str(output)))

    completed = subprocess.run(
        arguments,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode != 0
    assert "unique" in completed.stderr
    assert not output.exists()


@pytest.mark.parametrize(
    "mutation",
    ("slot", "attempt", "side-identity", "envelope-schema"),
)
def test_compare_p8_rejects_capture_metadata_mismatch(
    tmp_path: Path,
    mutation: str,
) -> None:
    paths = _write_p8_capture_set(tmp_path)
    target = paths["hash-baseline-r1"]
    envelope = json.loads(target.read_text(encoding="utf-8"))
    if mutation == "slot":
        envelope["embedding"] = "online"
    elif mutation == "attempt":
        envelope["attempt_id"] = "p8-final"
    elif mutation == "side-identity":
        envelope["implementation"] = _identity("c")
    else:
        envelope["unexpected"] = True
    target.write_text(json.dumps(envelope), encoding="utf-8")
    inventory = tmp_path / "eligible.json"
    inventory.write_text('{"schema_version":1,"p8_eligible_case_ids":[]}\n')
    output = tmp_path / "gates.json"

    completed = _invoke_compare_p8(paths, inventory, output)

    assert completed.returncode != 0
    assert not output.exists()


def test_compare_p1_rejects_catalog_digest_mismatch(tmp_path: Path) -> None:
    catalog = tmp_path / "queries.json"
    catalog.write_text('{"schema_version":1}\n', encoding="utf-8")
    paths = _write_p1_capture_set(tmp_path, "sha256:" + "0" * 64)
    output = tmp_path / "gates.json"

    completed = _invoke_compare_p1(paths, catalog, output)

    assert completed.returncode != 0
    assert "catalog" in completed.stderr
    assert not output.exists()


def test_online_provider_settings_rejects_wrong_identity_without_secret(
    tmp_path: Path,
) -> None:
    secret = "must-not-appear-in-errors"
    config = tmp_path / "config.toml"
    config.write_text(
        dedent(
            f"""
            [embedding]
            provider = "openai-compatible"
            model = "wrong-model"
            dimensions = 1024
            base_url = "https://api.siliconflow.cn/v1"
            api_key = "{secret}"

            [query_planner]
            enabled = true
            provider = "openai-compatible"
            model = "Qwen/Qwen2.5-14B-Instruct"
            base_url = "https://api.siliconflow.cn/v1"
            api_key = "{secret}"
            use_system_proxy = false
            timeout_seconds = 60
            max_rewritten_queries = 4
            max_keywords = 12
            max_symbol_hints = 8
            """
        ),
        encoding="utf-8",
    )
    harness = runpy.run_path(str(SCRIPT), run_name="p14_online_config_probe")

    with pytest.raises(ValueError) as caught:
        harness["_online_provider_settings"](config)

    assert secret not in str(caught.value)


def test_online_embedding_rate_limit_uses_a_sliding_tpm_window() -> None:
    harness = runpy.run_path(str(SCRIPT), run_name="p14_rate_limit_probe")
    history: list[tuple[float, int]] = []
    clock = [0.0]
    sleeps: list[float] = []

    def monotonic() -> float:
        return clock[0]

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        clock[0] += seconds

    wait = harness["_wait_for_online_embedding_budget"]
    wait(history, 80_000, monotonic=monotonic, sleep=sleep)
    wait(history, 80_000, monotonic=monotonic, sleep=sleep)
    wait(history, 80_000, monotonic=monotonic, sleep=sleep)
    wait(history, 1, monotonic=monotonic, sleep=sleep)

    assert sleeps == [2.0, 2.0, 56.0]
    assert history == [(2.0, 80_000), (4.0, 80_000), (60.0, 1)]
    assert harness["_online_embedding_token_estimate"](("abc", "中", "abcd")) == 4


def test_online_embedding_rate_limit_spaces_adjacent_requests() -> None:
    harness = runpy.run_path(str(SCRIPT), run_name="p14_rate_spacing_probe")
    history: list[tuple[float, int]] = []
    clock = [0.0]
    sleeps: list[float] = []

    def monotonic() -> float:
        return clock[0]

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        clock[0] += seconds

    wait = harness["_wait_for_online_embedding_budget"]
    wait(history, 1, monotonic=monotonic, sleep=sleep)
    wait(history, 1, monotonic=monotonic, sleep=sleep)

    assert sleeps == [2.0]
    assert history == [(0.0, 1), (2.0, 1)]


def test_online_embedding_batches_are_bounded_and_ordered() -> None:
    harness = runpy.run_path(str(SCRIPT), run_name="p14_rate_batch_probe")
    texts = ["a" * 120_000, "b" * 120_000, "c" * 120_000]

    batches = harness["_online_embedding_batches"](texts)

    assert batches == [[texts[0], texts[1]], [texts[2]]]
    assert all(
        harness["_online_embedding_token_estimate"](batch) <= 80_000
        for batch in batches
    )
    with pytest.raises(ValueError, match="single input exceeds"):
        harness["_online_embedding_batches"](["x" * 240_003])


def test_online_embedding_batches_can_force_singleton_requests() -> None:
    harness = runpy.run_path(str(SCRIPT), run_name="p14_rate_singleton_probe")
    texts = ["first", "second", "third"]

    batches = harness["_online_embedding_batches"](texts, singleton=True)

    assert batches == [[texts[0]], [texts[1]], [texts[2]]]


def test_online_embedding_pacer_splits_calls_and_preserves_order() -> None:
    harness = runpy.run_path(str(SCRIPT), run_name="p14_p1_rate_probe")
    from context_search_tool.embeddings import OpenAICompatibleEmbeddingProvider

    original = OpenAICompatibleEmbeddingProvider.embed_texts
    calls: list[list[str]] = []
    waits: list[int] = []

    def fake_embed_texts(self, texts):
        calls.append(list(texts))
        return [f"vector:{text}" for text in texts]

    OpenAICompatibleEmbeddingProvider.embed_texts = fake_embed_texts
    try:
        with harness["_pace_online_embedding_requests"](
            wait_for_budget=lambda _history, token_count: waits.append(
                token_count
            )
        ):
            provider = object.__new__(OpenAICompatibleEmbeddingProvider)
            vectors = provider.embed_texts(["first", "second", "third"])
    finally:
        OpenAICompatibleEmbeddingProvider.embed_texts = original

    assert calls == [["first"], ["second"], ["third"]]
    assert vectors == ["vector:first", "vector:second", "vector:third"]
    assert waits == [2, 2, 2]


def test_compare_p8_rejects_ollama_online_identity(tmp_path: Path) -> None:
    paths = _write_valid_p8_capture_set(tmp_path)
    target = paths["online-baseline-r1"]
    envelope = json.loads(target.read_text(encoding="utf-8"))
    identity = envelope["report"]["embedding_identity"]
    identity["provider"] = "ollama"
    identity["base_url"] = "http://localhost:11434"
    identity["ollama_version"] = "test"
    target.write_text(json.dumps(envelope, sort_keys=True), encoding="utf-8")
    inventory = tmp_path / "eligible.json"
    inventory.write_text(
        json.dumps(_eligible_inventory(), sort_keys=True),
        encoding="utf-8",
    )
    output = tmp_path / "gates.json"

    completed = _invoke_compare_p8(paths, inventory, output)

    assert completed.returncode != 0
    assert not output.exists()


def test_compare_p1_rejects_ollama_planner_identity(tmp_path: Path) -> None:
    catalog = SCRIPT.parent / "fixtures/retrieval_quality/queries.json"
    paths = _write_valid_p1_capture_set(tmp_path, catalog)
    target = paths["hybrid-baseline-r1"]
    envelope = json.loads(target.read_text(encoding="utf-8"))
    envelope["report"]["planner"].update(
        {
            "provider": "ollama",
            "model": "local-model",
            "base_url": "http://localhost:11434",
        }
    )
    target.write_text(json.dumps(envelope, sort_keys=True), encoding="utf-8")
    output = tmp_path / "gates.json"

    completed = _invoke_compare_p1(paths, catalog, output)

    assert completed.returncode != 0
    assert not output.exists()


def test_compare_p8_rejects_open_eligible_inventory_schema(
    tmp_path: Path,
) -> None:
    paths = _write_p8_capture_set(tmp_path)
    inventory = _eligible_inventory()
    inventory["unexpected"] = True
    inventory_path = tmp_path / "eligible.json"
    inventory_path.write_text(json.dumps(inventory), encoding="utf-8")
    output = tmp_path / "gates.json"

    completed = _invoke_compare_p8(paths, inventory_path, output)

    assert completed.returncode != 0
    assert "inventory" in completed.stderr
    assert not output.exists()


@pytest.mark.parametrize(
    "mutation",
    ("forged-allowlist", "baseline", "source-hash", "eligible-keys"),
)
def test_compare_p8_derives_allowlist_from_verified_baseline_inventory(
    tmp_path: Path,
    mutation: str,
) -> None:
    paths = _write_valid_p8_capture_set(tmp_path)
    inventory = _eligible_inventory()
    if mutation == "forged-allowlist":
        inventory["p8_eligible_case_ids"] = [P8_CASE_IDS[0]]
    elif mutation == "baseline":
        inventory["behavior_baseline"] = "b" * 40
    elif mutation == "source-hash":
        inventory["sources"][0]["sha256"] = "0" * 64
    else:
        inventory["eligible_keys"] = [
            {
                "case_id": P8_CASE_IDS[0],
                "repo_key": "redink",
                "source_kind": "p8_manifest",
                "source_path": (
                    "tests/fixtures/p8_python_graphs/input_manifest.json"
                ),
            }
        ]
    inventory_path = tmp_path / "eligible.json"
    inventory_path.write_text(json.dumps(inventory, sort_keys=True))
    output = tmp_path / "gates.json"

    completed = _invoke_compare_p8(paths, inventory_path, output)

    assert completed.returncode != 0
    assert "inventory" in completed.stderr
    assert not output.exists()


def test_compare_p8_writes_complete_ship_gate_arithmetic(
    tmp_path: Path,
) -> None:
    paths = _write_valid_p8_capture_set(tmp_path)
    inventory = tmp_path / "eligible.json"
    inventory.write_text(
        json.dumps(_eligible_inventory(), sort_keys=True),
        encoding="utf-8",
    )
    output = tmp_path / "gates.json"

    completed = _invoke_compare_p8(paths, inventory, output)

    assert completed.returncode == 0, completed.stderr
    gates = json.loads(output.read_text(encoding="utf-8"))
    assert set(gates) == {
        "schema_version",
        "gate_kind",
        "attempt_id",
        "eligible_inventory",
        "inputs",
        "providers",
        "repeat_determinism",
        "noneligible_parity",
        "case_deltas",
        "r2_cohort_deltas",
        "protected_winner_mismatches",
        "structural_mismatches",
        "online_numeric_drift",
        "gates",
        "disposition",
    }
    assert gates["schema_version"] == 1
    assert gates["gate_kind"] == "p8"
    assert gates["attempt_id"] == "p8-initial"
    assert gates["disposition"] == "ship"
    assert all(gates["gates"].values())
    assert gates["eligible_inventory"]["sha256"].startswith("sha256:")
    assert set(gates["inputs"]) == set(P8_SLOTS)
    assert all(
        source["sha256"].startswith("sha256:")
        for source in gates["inputs"].values()
    )
    assert gates["providers"]["hash"]["recall"]["baseline_hits"] == 18
    assert gates["providers"]["hash"]["recall"]["denominator"] == 57
    assert gates["providers"]["hash"]["required_losses"]["count"] == 0
    assert gates["providers"]["hash"]["noise"]["candidate_ratio"] == 0.5
    assert gates["providers"]["hash"]["timing"]["baseline_spread"] <= 0.15
    assert gates["providers"]["hash"]["timing"]["candidate_baseline_ratio"] <= 1.10
    assert gates["noneligible_parity"]["checked_case_count"] == 18
    assert gates["case_deltas"] == []
    assert gates["r2_cohort_deltas"] == {
        "reason": "eligible_exact_query_rerank_cascade",
        "count": 0,
        "items": [],
    }


@pytest.mark.parametrize(
    ("mutation", "expected_disposition", "failed_gate"),
    (
        ("noneligible", "reject", "noneligible_parity"),
        ("baseline-timing", "blocked", "baseline_timing_stable"),
        ("candidate-timing", "reject", "candidate_timing_ratio"),
    ),
)
def test_compare_p8_freezes_reject_and_blocked_outcomes(
    tmp_path: Path,
    mutation: str,
    expected_disposition: str,
    failed_gate: str,
) -> None:
    paths = _write_valid_p8_capture_set(tmp_path)
    if mutation == "noneligible":
        targets = [
            paths[f"{provider}-candidate-r{repeat}"]
            for provider in ("hash", "online")
            for repeat in (1, 2)
        ]
        for target in targets:
            envelope = json.loads(target.read_text(encoding="utf-8"))
            envelope["report"]["cases"][P8_CASE_IDS[1]]["selected"][0][
                "score"
            ] = 9.0
            target.write_text(json.dumps(envelope, sort_keys=True))
    else:
        side = "baseline" if mutation == "baseline-timing" else "candidate"
        repeats = (2,) if side == "baseline" else (1, 2)
        for provider in ("hash", "online"):
            for repeat in repeats:
                target = paths[f"{provider}-{side}-r{repeat}"]
                envelope = json.loads(target.read_text(encoding="utf-8"))
                timing = envelope["report"]["timing"]
                timing["query_case_min_seconds"][P8_CASE_IDS[0]] = 2.0
                timing["query_p95_seconds"] = 2.0
                target.write_text(json.dumps(envelope, sort_keys=True))
    inventory = tmp_path / "eligible.json"
    inventory.write_text(
        json.dumps(_eligible_inventory(), sort_keys=True)
    )
    output = tmp_path / "gates.json"

    completed = _invoke_compare_p8(paths, inventory, output)

    assert completed.returncode == 0, completed.stderr
    gates = json.loads(output.read_text(encoding="utf-8"))
    assert gates["disposition"] == expected_disposition
    assert gates["gates"][failed_gate] is False
    if mutation == "noneligible":
        assert gates["case_deltas"] == [
            {
                "provider": provider,
                "case_id": P8_CASE_IDS[1],
                "eligible": False,
                "changed_fields": ["score"],
                "projection": {
                    "baseline_selected": json.loads(
                        paths[f"{provider}-baseline-r1"].read_text(
                            encoding="utf-8"
                        )
                    )["report"]["cases"][P8_CASE_IDS[1]]["selected"],
                    "candidate_selected": json.loads(
                        paths[f"{provider}-candidate-r1"].read_text(
                            encoding="utf-8"
                        )
                    )["report"]["cases"][P8_CASE_IDS[1]]["selected"],
                },
            }
            for provider in ("hash", "online")
        ]
        assert gates["r2_cohort_deltas"] == {
            "reason": "eligible_exact_query_rerank_cascade",
            "count": 0,
            "items": [],
        }


def test_compare_p8_records_permitted_eligible_cohort_delta(
    tmp_path: Path,
) -> None:
    paths = _write_valid_p8_capture_set(tmp_path)
    case_id = P8_CASE_IDS[0]
    for provider in ("hash", "online"):
        for repeat in (1, 2):
            target = paths[f"{provider}-candidate-r{repeat}"]
            envelope = json.loads(target.read_text(encoding="utf-8"))
            selected = envelope["report"]["cases"][case_id]["selected"][0]
            selected["score_parts"] = {
                "cohort_mismatch_penalty": -0.05,
                **selected["score_parts"],
            }
            target.write_text(json.dumps(envelope, sort_keys=True))
    output = tmp_path / "gates.json"
    inventory = tmp_path / "eligible.json"
    inventory.write_text("{}\n", encoding="utf-8")
    harness = runpy.run_path(str(SCRIPT), run_name="p14_compare_p8_probe")
    captures = harness["_load_comparison_captures"](
        inputs=paths,
        attempt_id="p8-initial",
        kind="p8",
    )

    harness["_compare_p8"](
        arguments=argparse.Namespace(
            attempt_id="p8-initial",
            output=str(output),
        ),
        inputs=paths,
        captures=captures,
        inventory_path=inventory,
        inventory={},
        eligible={case_id},
    )

    gates = json.loads(output.read_text(encoding="utf-8"))
    assert gates["disposition"] == "ship"
    assert gates["r2_cohort_deltas"] == {
        "reason": "eligible_exact_query_rerank_cascade",
        "count": 2,
        "items": [
            {
                "provider": provider,
                "case_id": case_id,
                "changed_fields": ["score_parts"],
            }
            for provider in ("hash", "online")
        ],
    }


def test_compare_p8_does_not_mislabel_eligible_noncohort_delta(
    tmp_path: Path,
) -> None:
    paths = _write_valid_p8_capture_set(tmp_path)
    case_id = P8_CASE_IDS[0]
    for provider in ("hash", "online"):
        for repeat in (1, 2):
            target = paths[f"{provider}-candidate-r{repeat}"]
            envelope = json.loads(target.read_text(encoding="utf-8"))
            envelope["report"]["cases"][case_id]["selected"][1][
                "path"
            ] = "replacement-noise.py"
            target.write_text(json.dumps(envelope, sort_keys=True))
    output = tmp_path / "gates.json"
    inventory = tmp_path / "eligible.json"
    inventory.write_text("{}\n", encoding="utf-8")
    harness = runpy.run_path(str(SCRIPT), run_name="p14_compare_p8_probe")
    captures = harness["_load_comparison_captures"](
        inputs=paths,
        attempt_id="p8-initial",
        kind="p8",
    )

    harness["_compare_p8"](
        arguments=argparse.Namespace(
            attempt_id="p8-initial",
            output=str(output),
        ),
        inputs=paths,
        captures=captures,
        inventory_path=inventory,
        inventory={},
        eligible={case_id},
    )

    gates = json.loads(output.read_text(encoding="utf-8"))
    assert gates["disposition"] == "ship"
    assert gates["r2_cohort_deltas"]["items"] == []


def test_compare_rejects_identical_baseline_and_candidate_identity(
    tmp_path: Path,
) -> None:
    paths = _write_valid_p8_capture_set(tmp_path)
    for slot in P8_SLOTS:
        if "candidate" not in slot:
            continue
        target = paths[slot]
        envelope = json.loads(target.read_text(encoding="utf-8"))
        envelope["implementation"] = _identity("a")
        envelope["report"]["implementation"] = _identity("a")
        target.write_text(json.dumps(envelope, sort_keys=True))
    inventory = tmp_path / "eligible.json"
    inventory.write_text(
        json.dumps(_eligible_inventory(), sort_keys=True)
    )
    output = tmp_path / "gates.json"

    completed = _invoke_compare_p8(paths, inventory, output)

    assert completed.returncode != 0
    assert "intentionally differ" in completed.stderr
    assert not output.exists()


@pytest.mark.parametrize("mutation", ("timing-reps", "sources"))
def test_compare_p8_rejects_mixed_capture_setup(
    tmp_path: Path,
    mutation: str,
) -> None:
    paths = _write_valid_p8_capture_set(tmp_path)
    target = paths["hash-candidate-r2"]
    envelope = json.loads(target.read_text(encoding="utf-8"))
    if mutation == "timing-reps":
        envelope["timing_reps"] = 4
    else:
        envelope["sources"] = {"dirname": "other-sources"}
    target.write_text(json.dumps(envelope, sort_keys=True))
    inventory = tmp_path / "eligible.json"
    inventory.write_text(
        json.dumps(_eligible_inventory(), sort_keys=True)
    )
    output = tmp_path / "gates.json"

    completed = _invoke_compare_p8(paths, inventory, output)

    assert completed.returncode != 0
    assert not output.exists()


def test_compare_p8_non_timing_repeat_drift_is_reject_not_retry(
    tmp_path: Path,
) -> None:
    paths = _write_valid_p8_capture_set(tmp_path)
    target = paths["hash-candidate-r2"]
    envelope = json.loads(target.read_text(encoding="utf-8"))
    envelope["report"]["cases"][P8_CASE_IDS[0]]["selected"][0]["score"] = 8.0
    target.write_text(json.dumps(envelope, sort_keys=True))
    inventory = tmp_path / "eligible.json"
    inventory.write_text(
        json.dumps(_eligible_inventory(), sort_keys=True)
    )
    output = tmp_path / "gates.json"

    completed = _invoke_compare_p8(paths, inventory, output)

    assert completed.returncode == 0, completed.stderr
    gates = json.loads(output.read_text(encoding="utf-8"))
    assert gates["gates"]["repeat_determinism"] is False
    assert gates["disposition"] == "reject"


def test_compare_p8_allows_online_score_repeat_jitter_with_disclosure(
    tmp_path: Path,
) -> None:
    paths = _write_valid_p8_capture_set(tmp_path)
    for side in ("baseline", "candidate"):
        for repeat in (1, 2):
            reason_target = paths[f"online-{side}-r{repeat}"]
            reason_envelope = json.loads(
                reason_target.read_text(encoding="utf-8")
            )
            reason_envelope["report"]["cases"][P8_CASE_IDS[0]]["selected"][0][
                "reasons"
            ] = ["rerank_score=1.00 (original_direct)"]
            reason_target.write_text(
                json.dumps(reason_envelope, sort_keys=True)
            )
    target = paths["online-candidate-r2"]
    envelope = json.loads(target.read_text(encoding="utf-8"))
    selected = envelope["report"]["cases"][P8_CASE_IDS[0]]["selected"][0]
    selected["score"] += 0.0001
    selected["score_parts"]["score"] += 0.0001
    selected["reasons"] = ["rerank_score=1.01 (original_direct)"]
    target.write_text(json.dumps(envelope, sort_keys=True))
    inventory = tmp_path / "eligible.json"
    inventory.write_text(
        json.dumps(_eligible_inventory(), sort_keys=True)
    )
    output = tmp_path / "gates.json"

    completed = _invoke_compare_p8(paths, inventory, output)

    assert completed.returncode == 0, completed.stderr
    gates = json.loads(output.read_text(encoding="utf-8"))
    assert gates["gates"]["repeat_determinism"] is True
    assert gates["disposition"] == "ship"
    assert gates["online_numeric_drift"]["repeat_pairs"] == [
        "online-candidate"
    ]


def test_compare_p8_rejects_online_nonsemantic_score_part_repeat_drift(
    tmp_path: Path,
) -> None:
    paths = _write_valid_p8_capture_set(tmp_path)
    for repeat, lexical in ((1, 0.5), (2, 0.6)):
        target = paths[f"online-candidate-r{repeat}"]
        envelope = json.loads(target.read_text(encoding="utf-8"))
        envelope["report"]["cases"][P8_CASE_IDS[0]]["selected"][0][
            "score_parts"
        ]["lexical"] = lexical
        target.write_text(json.dumps(envelope, sort_keys=True))
    inventory = tmp_path / "eligible.json"
    inventory.write_text(
        json.dumps(_eligible_inventory(), sort_keys=True)
    )
    output = tmp_path / "gates.json"

    completed = _invoke_compare_p8(paths, inventory, output)

    assert completed.returncode == 0, completed.stderr
    gates = json.loads(output.read_text(encoding="utf-8"))
    assert gates["gates"]["repeat_determinism"] is False
    assert gates["disposition"] == "reject"


def test_compare_p8_allows_online_noneligible_score_jitter_with_disclosure(
    tmp_path: Path,
) -> None:
    paths = _write_valid_p8_capture_set(tmp_path)
    for repeat in (1, 2):
        target = paths[f"online-candidate-r{repeat}"]
        envelope = json.loads(target.read_text(encoding="utf-8"))
        selected = envelope["report"]["cases"][P8_CASE_IDS[1]]["selected"][0]
        selected["score"] += 0.0001
        selected["score_parts"]["score"] += 0.0001
        target.write_text(json.dumps(envelope, sort_keys=True))
    inventory = tmp_path / "eligible.json"
    inventory.write_text(
        json.dumps(_eligible_inventory(), sort_keys=True)
    )
    output = tmp_path / "gates.json"

    completed = _invoke_compare_p8(paths, inventory, output)

    assert completed.returncode == 0, completed.stderr
    gates = json.loads(output.read_text(encoding="utf-8"))
    assert gates["gates"]["noneligible_parity"] is True
    assert gates["disposition"] == "ship"
    assert gates["online_numeric_drift"]["noneligible_pairs"] == [
        f"online:{P8_CASE_IDS[1]}"
    ]


def test_compare_p1_writes_complete_ship_gate_arithmetic(
    tmp_path: Path,
) -> None:
    catalog = SCRIPT.parent / "fixtures/retrieval_quality/queries.json"
    paths = _write_valid_p1_capture_set(tmp_path, catalog)
    output = tmp_path / "gates.json"

    completed = _invoke_compare_p1(paths, catalog, output)

    assert completed.returncode == 0, completed.stderr
    gates = json.loads(output.read_text(encoding="utf-8"))
    assert gates["schema_version"] == 1
    assert gates["gate_kind"] == "p1"
    assert gates["attempt_id"] == "p1-initial"
    assert gates["disposition"] == "ship"
    assert all(gates["gates"].values())
    assert gates["profiles"]["p1_vector_bge"]["baseline_counts"] == {
        "selected": 7,
        "executed": 7,
        "passed": 6,
        "failed": 1,
        "skipped": 0,
        "errors": 0,
    }
    assert gates["profiles"]["p1_vector_bge"]["candidate_counts"]["passed"] == 7
    assert gates["profiles"]["p1_vector_bge"]["baseline_owner_ranks"] == [5, 5]
    assert gates["profiles"]["p1_vector_bge"]["candidate_owner_ranks"] == [2, 2]
    assert gates["catalog"]["sha256"].startswith("sha256:")
    assert set(gates["inputs"]) == set(P1_SLOTS)


@pytest.mark.parametrize(
    ("mutation", "expected_disposition", "failed_gate"),
    (
        ("fallback", "reject", "no_fallback_error_or_skip"),
        ("candidate-miss", "reject", "candidate_seven_of_seven_owner_top3"),
        ("repeat-drift", "reject", "repeat_determinism"),
    ),
)
def test_compare_p1_freezes_reject_and_blocked_outcomes(
    tmp_path: Path,
    mutation: str,
    expected_disposition: str,
    failed_gate: str,
) -> None:
    catalog = SCRIPT.parent / "fixtures/retrieval_quality/queries.json"
    paths = _write_valid_p1_capture_set(tmp_path, catalog)
    if mutation == "fallback":
        targets = [
            paths[f"hybrid-candidate-r{repeat}"] for repeat in (1, 2)
        ]
        for target in targets:
            envelope = json.loads(target.read_text(encoding="utf-8"))
            envelope["report"]["cases"][0][
                "variant_retrieval_status"
            ] = "embedding_fallback"
            target.write_text(json.dumps(envelope, sort_keys=True))
    elif mutation == "candidate-miss":
        targets = [
            paths[f"{profile}-candidate-r{repeat}"]
            for profile in ("vector", "hybrid")
            for repeat in (1, 2)
        ]
        for target in targets:
            envelope = json.loads(target.read_text(encoding="utf-8"))
            owner = next(
                case
                for case in envelope["report"]["cases"]
                if case["case_id"] == "audit-status-literal"
            )
            owner["status"] = "fail"
            target_result = owner["top_results"].pop()
            while len(owner["top_results"]) < 4:
                filler = dict(owner["top_results"][0])
                filler["path"] = (
                    f"candidate-miss-{len(owner['top_results']) + 1}.java"
                )
                owner["top_results"].append(filler)
            owner["top_results"].append(target_result)
            for rank, result in enumerate(owner["top_results"], start=1):
                result["rank"] = rank
            owner["failures"] = ["rank"]
            owner["metrics"].update(
                {
                    "result_count": 5,
                    "hit_at_1": False,
                    "hit_at_3": False,
                    "hit_at_5": True,
                    "hit_at_10": True,
                    "mrr": 0.2,
                    "recall_at_5": 1.0,
                    "recall_at_10": 1.0,
                    "top_score": owner["top_results"][0]["score"],
                }
            )
            envelope["report"]["aggregate"]["passed"] = 6
            envelope["report"]["aggregate"]["failed"] = 1
            _recompute_p1_overall(envelope["report"])
            target.write_text(json.dumps(envelope, sort_keys=True))
    else:
        target = paths["vector-candidate-r2"]
        envelope = json.loads(target.read_text(encoding="utf-8"))
        owner = next(
            case
            for case in envelope["report"]["cases"]
            if case["case_id"] == "audit-status-literal"
        )
        target_result = owner["top_results"].pop()
        owner["top_results"].insert(0, target_result)
        for rank, result in enumerate(owner["top_results"], start=1):
            result["rank"] = rank
        owner["metrics"].update(
            {
                "hit_at_1": True,
                "hit_at_3": True,
                "hit_at_5": True,
                "hit_at_10": True,
                "mrr": 1.0,
                "recall_at_5": 1.0,
                "recall_at_10": 1.0,
                "top_score": owner["top_results"][0]["score"],
            }
        )
        _recompute_p1_overall(envelope["report"])
        target.write_text(json.dumps(envelope, sort_keys=True))
    output = tmp_path / "gates.json"

    completed = _invoke_compare_p1(paths, catalog, output)

    assert completed.returncode == 0, completed.stderr
    gates = json.loads(output.read_text(encoding="utf-8"))
    assert gates["disposition"] == expected_disposition
    assert gates["gates"][failed_gate] is False


def test_compare_p1_rejects_config_provenance_drift(tmp_path: Path) -> None:
    catalog = SCRIPT.parent / "fixtures/retrieval_quality/queries.json"
    paths = _write_valid_p1_capture_set(tmp_path, catalog)
    for profile in ("vector", "hybrid"):
        for repeat in (1, 2):
            target = paths[f"{profile}-candidate-r{repeat}"]
            envelope = json.loads(target.read_text(encoding="utf-8"))
            report = envelope["report"]
            report["config"]["config_hash"] = "sha256:" + "d" * 64
            target.write_text(json.dumps(envelope, sort_keys=True))
    output = tmp_path / "gates.json"

    completed = _invoke_compare_p1(paths, catalog, output)

    assert completed.returncode == 0, completed.stderr
    gates = json.loads(output.read_text(encoding="utf-8"))
    assert gates["gates"]["provenance_stable"] is False
    assert gates["disposition"] == "reject"


def test_compare_p1_vector_repeat_rejects_query_variant_drift(
    tmp_path: Path,
) -> None:
    catalog = SCRIPT.parent / "fixtures/retrieval_quality/queries.json"
    paths = _write_valid_p1_capture_set(tmp_path, catalog)
    target = paths["vector-candidate-r2"]
    envelope = json.loads(target.read_text(encoding="utf-8"))
    case = envelope["report"]["cases"][0]
    case["query_variants"].append(
        {
            "variant_id": "planner:0",
            "text": "unexpected",
            "source": "planner",
        }
    )
    target.write_text(json.dumps(envelope, sort_keys=True))
    output = tmp_path / "gates.json"

    completed = _invoke_compare_p1(paths, catalog, output)

    assert completed.returncode == 0, completed.stderr
    gates = json.loads(output.read_text(encoding="utf-8"))
    assert gates["gates"]["vector_repeat_determinism"] is False
    assert gates["disposition"] == "reject"


def test_compare_p1_vector_repeat_allows_online_score_jitter_with_disclosure(
    tmp_path: Path,
) -> None:
    catalog = SCRIPT.parent / "fixtures/retrieval_quality/queries.json"
    paths = _write_valid_p1_capture_set(tmp_path, catalog)
    target = paths["vector-candidate-r2"]
    envelope = json.loads(target.read_text(encoding="utf-8"))
    case = envelope["report"]["cases"][0]
    result = case["top_results"][0]
    result["score"] += 0.0001
    result["score_parts"]["score"] += 0.0001
    case["metrics"]["top_score"] += 0.0001
    target.write_text(json.dumps(envelope, sort_keys=True))
    output = tmp_path / "gates.json"

    completed = _invoke_compare_p1(paths, catalog, output)

    assert completed.returncode == 0, completed.stderr
    gates = json.loads(output.read_text(encoding="utf-8"))
    assert gates["gates"]["vector_repeat_determinism"] is True
    assert gates["disposition"] == "ship"
    assert gates["online_numeric_drift"] == ["vector-candidate"]


def test_compare_p1_vector_repeat_rejects_nonsemantic_score_part_drift(
    tmp_path: Path,
) -> None:
    catalog = SCRIPT.parent / "fixtures/retrieval_quality/queries.json"
    paths = _write_valid_p1_capture_set(tmp_path, catalog)
    for repeat, lexical in ((1, 0.5), (2, 0.6)):
        target = paths[f"vector-candidate-r{repeat}"]
        envelope = json.loads(target.read_text(encoding="utf-8"))
        envelope["report"]["cases"][0]["top_results"][0]["score_parts"][
            "lexical"
        ] = lexical
        target.write_text(json.dumps(envelope, sort_keys=True))
    output = tmp_path / "gates.json"

    completed = _invoke_compare_p1(paths, catalog, output)

    assert completed.returncode == 0, completed.stderr
    gates = json.loads(output.read_text(encoding="utf-8"))
    assert gates["gates"]["vector_repeat_determinism"] is False
    assert gates["disposition"] == "reject"


def test_compare_p1_discloses_hybrid_raw_planner_text_drift(
    tmp_path: Path,
) -> None:
    catalog = SCRIPT.parent / "fixtures/retrieval_quality/queries.json"
    paths = _write_valid_p1_capture_set(tmp_path, catalog)
    output = tmp_path / "gates.json"

    completed = _invoke_compare_p1(paths, catalog, output)

    assert completed.returncode == 0, completed.stderr
    gates = json.loads(output.read_text(encoding="utf-8"))
    assert gates["disposition"] == "ship"
    assert gates["hybrid_raw_planner_text_drift"]


def test_compare_p1_allows_one_hybrid_owner_rank_step_within_top3(
    tmp_path: Path,
) -> None:
    catalog = SCRIPT.parent / "fixtures/retrieval_quality/queries.json"
    paths = _write_valid_p1_capture_set(tmp_path, catalog)
    for repeat in (1, 2):
        target = paths[f"hybrid-candidate-r{repeat}"]
        envelope = json.loads(target.read_text(encoding="utf-8"))
        owner = next(
            case
            for case in envelope["report"]["cases"]
            if case["case_id"] == "audit-status-literal"
        )
        target_result = owner["top_results"].pop()
        filler = dict(owner["top_results"][0])
        filler["path"] = "owner-rank-three-filler.java"
        owner["top_results"].extend((filler, target_result))
        for rank, result in enumerate(owner["top_results"], start=1):
            result["rank"] = rank
        owner["metrics"].update(
            {
                "result_count": 3,
                "hit_at_1": False,
                "hit_at_3": True,
                "hit_at_5": True,
                "hit_at_10": True,
                "mrr": 1.0 / 3.0,
                "recall_at_5": 1.0,
                "recall_at_10": 1.0,
                "entrypoint_rank": (
                    3
                    if owner["metrics"]["entrypoint_rank"] is not None
                    else None
                ),
                "top_score": owner["top_results"][0]["score"],
            }
        )
        _recompute_p1_overall(envelope["report"])
        target.write_text(json.dumps(envelope, sort_keys=True))
    output = tmp_path / "gates.json"

    completed = _invoke_compare_p1(paths, catalog, output)

    assert completed.returncode == 0, completed.stderr
    gates = json.loads(output.read_text(encoding="utf-8"))
    assert gates["gates"]["hybrid_metrics_not_below_vector"] is True
    assert gates["pair_metrics"]["repeat_1"]["mrr"]["tolerance"] == pytest.approx(
        1.0 / 42.0
    )
    assert gates["disposition"] == "ship"


def test_compare_p1_checks_focused_pair_metrics_in_both_repeats(
    tmp_path: Path,
) -> None:
    catalog = SCRIPT.parent / "fixtures/retrieval_quality/queries.json"
    paths = _write_valid_p1_capture_set(tmp_path, catalog)
    target = paths["hybrid-candidate-r2"]
    envelope = json.loads(target.read_text(encoding="utf-8"))
    dashboard = next(
        case
        for case in envelope["report"]["cases"]
        if case["case_id"] == "dashboard-cross-language"
    )
    dashboard["top_results"][0]["path"] = "irrelevant-dashboard-result.java"
    dashboard["metrics"]["hit_at_1"] = False
    dashboard["metrics"]["mrr"] = 0.5
    _recompute_p1_overall(envelope["report"])
    target.write_text(json.dumps(envelope, sort_keys=True))
    output = tmp_path / "gates.json"

    completed = _invoke_compare_p1(paths, catalog, output)

    assert completed.returncode == 0, completed.stderr
    gates = json.loads(output.read_text(encoding="utf-8"))
    assert gates["gates"]["hybrid_metrics_not_below_vector"] is False
    assert set(gates["pair_metrics"]) == {"repeat_1", "repeat_2"}
    assert gates["disposition"] == "reject"


def test_compare_rejects_cross_side_module_origin_reuse(
    tmp_path: Path,
) -> None:
    paths = _write_valid_p8_capture_set(tmp_path)
    baseline = json.loads(
        paths["hash-baseline-r1"].read_text(encoding="utf-8")
    )
    for slot in P8_SLOTS:
        if "-candidate-" not in slot:
            continue
        candidate = json.loads(paths[slot].read_text(encoding="utf-8"))
        candidate["module_origins"] = baseline["module_origins"]
        paths[slot].write_text(
            json.dumps(candidate, sort_keys=True),
            encoding="utf-8",
        )
    inventory = tmp_path / "eligible.json"
    inventory.write_text(json.dumps(_eligible_inventory(), sort_keys=True))
    output = tmp_path / "gates.json"

    completed = _invoke_compare_p8(paths, inventory, output)

    assert completed.returncode != 0
    assert "module origins" in completed.stderr
    assert not output.exists()


def test_capture_rejects_module_symlink_outside_requested_root(
    tmp_path: Path,
) -> None:
    implementation = _write_fake_implementation(tmp_path)
    ranking = implementation / "src/context_search_tool/retrieval_core/ranking.py"
    outside = tmp_path / "outside-ranking.py"
    outside.write_text("", encoding="utf-8")
    ranking.unlink()
    ranking.symlink_to(outside)
    catalog = implementation / "catalog.json"
    catalog.write_text('{"schema_version":1}\n', encoding="utf-8")
    output = tmp_path / "capture.json"
    markdown = tmp_path / "capture.md"

    completed = subprocess.run(
        (
            sys.executable,
            "-P",
            str(SCRIPT),
            "capture-p1",
            "--attempt-id",
            "p1-initial",
            "--side",
            "baseline",
            "--repeat",
            "1",
            "--implementation-root",
            str(implementation),
            "--catalog",
            str(catalog),
            "--profile",
            "p1_vector_bge",
            "--output",
            str(output),
            "--markdown",
            str(markdown),
        ),
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode != 0
    assert "outside implementation root" in completed.stderr
    assert not output.exists()
    assert not markdown.exists()


@pytest.mark.parametrize(
    "mutation",
    (
        "fixture-count",
        "command-path",
        "case-extra-key",
        "case-missing-query-variants",
        "variant-extra-key",
        "variant-missing-key",
        "declared-rank-disagrees-with-position",
    ),
)
def test_compare_p1_rejects_nested_schema_and_rank_spoofing(
    tmp_path: Path,
    mutation: str,
) -> None:
    catalog = SCRIPT.parent / "fixtures/retrieval_quality/queries.json"
    paths = _write_valid_p1_capture_set(tmp_path, catalog)
    target = paths["vector-candidate-r1"]
    envelope = json.loads(target.read_text(encoding="utf-8"))
    report = envelope["report"]
    case = next(
        row
        for row in report["cases"]
        if row["case_id"] == "audit-status-literal"
    )
    if mutation == "fixture-count":
        del report["fixture"]["run_case_count"]
    elif mutation == "command-path":
        report["command_args"]["fixture_path"] = "/unrelated/queries.json"
    elif mutation == "case-extra-key":
        case["unexpected"] = True
    elif mutation == "case-missing-query-variants":
        del case["query_variants"]
    elif mutation == "variant-extra-key":
        case["query_variants"][0]["unexpected"] = True
    elif mutation == "variant-missing-key":
        del case["query_variants"][0]["variant_id"]
    else:
        target_result = case["top_results"].pop()
        for rank in (2, 3, 4):
            filler = dict(case["top_results"][0])
            filler["rank"] = rank
            filler["path"] = f"spoof-filler-{rank}.java"
            case["top_results"].append(filler)
        case["top_results"].append(target_result)
        assert case["top_results"][4]["rank"] == 2
    target.write_text(json.dumps(envelope, sort_keys=True), encoding="utf-8")
    output = tmp_path / "gates.json"

    completed = _invoke_compare_p1(paths, catalog, output)

    assert completed.returncode != 0
    assert not output.exists()


def test_compare_p8_rejects_required_state_rank_membership_mismatch(
    tmp_path: Path,
) -> None:
    paths = _write_valid_p8_capture_set(tmp_path)
    for target in paths.values():
        envelope = json.loads(target.read_text(encoding="utf-8"))
        required = envelope["report"]["cases"][P8_CASE_IDS[0]]["required"][0]
        assert required["rank"] == 1
        required["state"] = "not_selected"
        target.write_text(
            json.dumps(envelope, sort_keys=True),
            encoding="utf-8",
        )
    inventory = tmp_path / "eligible.json"
    inventory.write_text(json.dumps(_eligible_inventory(), sort_keys=True))
    output = tmp_path / "gates.json"

    completed = _invoke_compare_p8(paths, inventory, output)

    assert completed.returncode != 0
    assert not output.exists()


def test_capture_p1_rejects_output_markdown_alias_without_residue(
    tmp_path: Path,
) -> None:
    implementation = _write_fake_implementation(tmp_path)
    catalog = implementation / "catalog.json"
    catalog.write_text('{"schema_version":1}\n', encoding="utf-8")
    aliased = tmp_path / "aliased-output"

    completed = subprocess.run(
        (
            sys.executable,
            "-P",
            str(SCRIPT),
            "capture-p1",
            "--attempt-id",
            "p1-initial",
            "--side",
            "baseline",
            "--repeat",
            "1",
            "--implementation-root",
            str(implementation),
            "--catalog",
            str(catalog),
            "--profile",
            "p1_vector_bge",
            "--output",
            str(aliased),
            "--markdown",
            str(aliased),
        ),
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode != 0
    assert not aliased.exists()


@pytest.mark.parametrize("mutation", ("missing-config-hash", "wrong-tool-name"))
def test_compare_p1_rejects_closed_config_and_tool_spoofing(
    tmp_path: Path,
    mutation: str,
) -> None:
    catalog = SCRIPT.parent / "fixtures/retrieval_quality/queries.json"
    paths = _write_valid_p1_capture_set(tmp_path, catalog)
    for target in paths.values():
        envelope = json.loads(target.read_text(encoding="utf-8"))
        if mutation == "missing-config-hash":
            del envelope["report"]["config"]["config_hash"]
        else:
            envelope["report"]["tool"]["name"] = "evil"
        target.write_text(json.dumps(envelope, sort_keys=True), encoding="utf-8")
    output = tmp_path / "gates.json"

    completed = _invoke_compare_p1(paths, catalog, output)

    assert completed.returncode != 0
    assert not output.exists()


@pytest.mark.parametrize("field", ("total", "attempted"))
def test_compare_p1_rejects_aggregate_count_spoofing(
    tmp_path: Path,
    field: str,
) -> None:
    catalog = SCRIPT.parent / "fixtures/retrieval_quality/queries.json"
    paths = _write_valid_p1_capture_set(tmp_path, catalog)
    for slot, target in paths.items():
        if "-candidate-" not in slot:
            continue
        envelope = json.loads(target.read_text(encoding="utf-8"))
        envelope["report"]["aggregate"][field] = 999
        target.write_text(json.dumps(envelope, sort_keys=True), encoding="utf-8")
    output = tmp_path / "gates.json"

    completed = _invoke_compare_p1(paths, catalog, output)

    assert completed.returncode != 0
    assert not output.exists()


@pytest.mark.parametrize(
    "mutation",
    ("mrr-type", "result-count", "pass-with-failures"),
)
def test_compare_p1_rejects_case_metric_and_failure_spoofing(
    tmp_path: Path,
    mutation: str,
) -> None:
    catalog = SCRIPT.parent / "fixtures/retrieval_quality/queries.json"
    paths = _write_valid_p1_capture_set(tmp_path, catalog)
    for target in paths.values():
        envelope = json.loads(target.read_text(encoding="utf-8"))
        case = next(
            row
            for row in envelope["report"]["cases"]
            if row["case_id"] == "apply-audit-endpoint"
        )
        if mutation == "mrr-type":
            case["metrics"]["mrr"] = "1.0"
        elif mutation == "result-count":
            case["metrics"]["result_count"] = 999
        else:
            assert case["status"] == "pass"
            case["failures"].append("spoofed failure")
        target.write_text(json.dumps(envelope, sort_keys=True), encoding="utf-8")
    output = tmp_path / "gates.json"

    completed = _invoke_compare_p1(paths, catalog, output)

    assert completed.returncode != 0
    assert not output.exists()


@pytest.mark.parametrize(
    "mutation",
    (
        "selected-files",
        "index-bytes",
        "structure-count",
        "index-seconds",
        "case-seconds",
        "p50",
        "p95",
    ),
)
def test_compare_p8_rejects_negative_repository_and_timing_values(
    tmp_path: Path,
    mutation: str,
) -> None:
    paths = _write_valid_p8_capture_set(tmp_path)
    for target in paths.values():
        envelope = json.loads(target.read_text(encoding="utf-8"))
        report = envelope["report"]
        if mutation == "selected-files":
            report["repositories"]["redink"]["selected_files"] = -1
        elif mutation == "index-bytes":
            report["repositories"]["redink"]["index_sqlite_bytes"] = -1
        elif mutation == "structure-count":
            report["repositories"]["redink"]["structure"]["active_chunks"] = -1
        elif mutation == "index-seconds":
            report["timing"]["index_seconds"]["redink"] = -1.0
        elif mutation == "case-seconds":
            report["timing"]["query_case_min_seconds"][P8_CASE_IDS[0]] = -1.0
        elif mutation == "p50":
            report["timing"]["query_p50_seconds"] = -1.0
        else:
            report["timing"]["query_p95_seconds"] = -1.0
        target.write_text(json.dumps(envelope, sort_keys=True), encoding="utf-8")
    inventory = tmp_path / "eligible.json"
    inventory.write_text(json.dumps(_eligible_inventory(), sort_keys=True))
    output = tmp_path / "gates.json"

    completed = _invoke_compare_p8(paths, inventory, output)

    assert completed.returncode != 0
    assert not output.exists()


@pytest.mark.parametrize("inside_target", ("output", "markdown"))
def test_capture_p1_rejects_any_output_beneath_implementation_root(
    tmp_path: Path,
    inside_target: str,
) -> None:
    implementation = _write_fake_implementation(tmp_path)
    catalog = implementation / "catalog.json"
    catalog.write_text('{"schema_version":1}\n', encoding="utf-8")
    outside_output = tmp_path / "capture.json"
    outside_markdown = tmp_path / "capture.md"
    inside = implementation / "evidence" / f"{inside_target}.artifact"
    output = inside if inside_target == "output" else outside_output
    markdown = inside if inside_target == "markdown" else outside_markdown

    completed = subprocess.run(
        (
            sys.executable,
            "-P",
            str(SCRIPT),
            "capture-p1",
            "--attempt-id",
            "p1-initial",
            "--side",
            "baseline",
            "--repeat",
            "1",
            "--implementation-root",
            str(implementation),
            "--catalog",
            str(catalog),
            "--profile",
            "p1_vector_bge",
            "--output",
            str(output),
            "--markdown",
            str(markdown),
        ),
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode != 0
    assert not inside.exists()
    assert not outside_output.exists()
    assert not outside_markdown.exists()


def test_capture_p8_rejects_output_beneath_implementation_root(
    tmp_path: Path,
) -> None:
    implementation = _write_fake_implementation(tmp_path)
    _add_fake_p8_runner(implementation)
    sources = tmp_path / "sources"
    sources.mkdir()
    output = implementation / "evidence" / "capture.json"

    completed = subprocess.run(
        (
            sys.executable,
            "-P",
            str(SCRIPT),
            "capture-p8",
            "--attempt-id",
            "p8-initial",
            "--side",
            "candidate",
            "--repeat",
            "1",
            "--implementation-root",
            str(implementation),
            "--sources",
            str(sources),
            "--embedding",
            "hash",
            "--timing-reps",
            "2",
            "--output",
            str(output),
        ),
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode != 0
    assert not output.exists()


@pytest.mark.parametrize(
    "mutation",
    ("required-pop", "required-duplicate", "contextual-append"),
)
def test_compare_p8_binds_denominator_and_contextual_to_manifest(
    tmp_path: Path,
    mutation: str,
) -> None:
    paths = _write_valid_p8_capture_set(tmp_path)
    for target in paths.values():
        envelope = json.loads(target.read_text(encoding="utf-8"))
        case = envelope["report"]["cases"][P8_CASE_IDS[0]]
        if mutation == "required-pop":
            case["required"].pop()
        elif mutation == "required-duplicate":
            case["required"].append(dict(case["required"][0]))
        else:
            case["contextual"].append("unexpected/context.py")
        target.write_text(json.dumps(envelope, sort_keys=True), encoding="utf-8")
    inventory = tmp_path / "eligible.json"
    inventory.write_text(json.dumps(_eligible_inventory(), sort_keys=True))
    output = tmp_path / "gates.json"

    completed = _invoke_compare_p8(paths, inventory, output)

    assert completed.returncode != 0
    assert not output.exists()


def test_compare_p1_rejects_spoofed_overall_pair_metrics(
    tmp_path: Path,
) -> None:
    catalog = SCRIPT.parent / "fixtures/retrieval_quality/queries.json"
    paths = _write_valid_p1_capture_set(tmp_path, catalog)
    for repeat in (1, 2):
        target = paths[f"hybrid-candidate-r{repeat}"]
        envelope = json.loads(target.read_text(encoding="utf-8"))
        overall = envelope["report"]["aggregate"]["metrics"]["overall"]
        overall["mrr"]["mean"] = 1.0
        overall["recall_at_5"]["mean"] = 1.0
        overall["entrypoint_top3"]["rate"] = 1.0
        target.write_text(json.dumps(envelope, sort_keys=True), encoding="utf-8")
    output = tmp_path / "gates.json"

    completed = _invoke_compare_p1(paths, catalog, output)

    assert completed.returncode != 0
    assert not output.exists()


def test_compare_p1_rejects_spoofed_entrypoint_rank(
    tmp_path: Path,
) -> None:
    catalog = SCRIPT.parent / "fixtures/retrieval_quality/queries.json"
    paths = _write_valid_p1_capture_set(tmp_path, catalog)
    for repeat in (1, 2):
        target = paths[f"hybrid-candidate-r{repeat}"]
        envelope = json.loads(target.read_text(encoding="utf-8"))
        dashboard = next(
            case
            for case in envelope["report"]["cases"]
            if case["case_id"] == "dashboard-cross-language"
        )
        entrypoint = dashboard["top_results"].pop()
        for rank in (2, 3):
            filler = dict(dashboard["top_results"][0])
            filler["rank"] = rank
            filler["path"] = f"irrelevant-entrypoint-{rank}.java"
            filler["score"] = 1.0 / rank
            filler["score_parts"] = {"score": 1.0 / rank}
            dashboard["top_results"].append(filler)
        entrypoint["rank"] = 4
        entrypoint["score"] = 0.25
        entrypoint["score_parts"] = {"score": 0.25}
        dashboard["top_results"].append(entrypoint)
        dashboard["metrics"]["result_count"] = 4
        dashboard["metrics"]["entrypoint_rank"] = 1
        _recompute_p1_overall(envelope["report"])
        target.write_text(json.dumps(envelope, sort_keys=True), encoding="utf-8")
    output = tmp_path / "gates.json"

    completed = _invoke_compare_p1(paths, catalog, output)

    assert completed.returncode != 0
    assert not output.exists()


def test_compare_p8_rejects_percentiles_inconsistent_with_case_timings(
    tmp_path: Path,
) -> None:
    paths = _write_valid_p8_capture_set(tmp_path)
    for target in paths.values():
        envelope = json.loads(target.read_text(encoding="utf-8"))
        timing = envelope["report"]["timing"]
        timing["query_case_min_seconds"] = {
            case_id: 100.0 for case_id in P8_CASE_IDS
        }
        timing["query_p50_seconds"] = 0.1
        timing["query_p95_seconds"] = 0.1
        target.write_text(json.dumps(envelope, sort_keys=True), encoding="utf-8")
    inventory = tmp_path / "eligible.json"
    inventory.write_text(json.dumps(_eligible_inventory(), sort_keys=True))
    output = tmp_path / "gates.json"

    completed = _invoke_compare_p8(paths, inventory, output)

    assert completed.returncode != 0
    assert not output.exists()
