from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import tempfile
from dataclasses import replace
from pathlib import Path
from typing import Any

from context_search_tool.config import DEFAULT_CONFIG
from context_search_tool.context_pack import (
    build_context_pack,
    resolve_context_pack_options,
)
from context_search_tool.indexer import index_repository
from context_search_tool.retrieval import evidence_anchor_top_k, trace_repository
from context_search_tool.tokenizer import tokenize_query
from p4_exploration_identity import (
    CI_PROJECTION_PATH,
    FROZEN_P4_INPUT_PATHS,
    IMPLEMENTATION_BASELINE,
    P0_P3_CATALOG_BLOB,
    P0_P3_CATALOG_SHA256,
    P2_PROJECTION_PATH,
    P3_BASELINE_BLOB,
    P4_MANIFEST_PATH,
    ROOT,
    assert_protected_inputs,
    load_raw_p4_catalog,
    p0_p3_quality_projection,
    sha256_file,
    verify_final_junit,
    working_tree_content_hash,
)


BASELINE_P2_REPORT = ROOT / ".quality/p4-artifacts/baseline-p2.json"
BASELINE_CI_REPORT = ROOT / ".quality/p4-artifacts/baseline-ci.json"
CONTROLLER = "src/main/java/com/example/owner/OwnerController.java"
OWNER_TEST = "src/test/java/com/example/owner/OwnerControllerTests.java"
OWNER_FORM = "src/main/resources/templates/owners/createOrUpdateOwnerForm.html"
QRCODE_VIEW = "src/views/qrcode/QRCodeTool.vue"
QRCODE_ROUTE = "src/router/index.ts"
QRCODE_UTILITY = "src/utils/qrcodeUtils.ts"
SOLO_CONTROLLER = "src/main/java/com/example/solo/SoloController.java"


def _git_source_is_protected(commit: str | None = None) -> None:
    args = ["git", "diff", "--exit-code", IMPLEMENTATION_BASELINE]
    if commit is not None:
        args.append(commit)
    args.extend(("--", "src/context_search_tool"))
    result = subprocess.run(
        args,
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        raise RuntimeError("production source differs from the protected baseline")


def _assert_generation_preconditions() -> dict[str, Any]:
    assert_protected_inputs()
    _git_source_is_protected()
    source_status = subprocess.run(
        (
            "git",
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
            "--",
            "src/context_search_tool",
        ),
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    if source_status:
        raise RuntimeError("production source worktree must be clean")
    if (ROOT / "src/context_search_tool/exploration").exists():
        raise RuntimeError("P4 manifest must be generated before production code")
    if P4_MANIFEST_PATH.exists():
        raise RuntimeError("P4 input manifest already exists; refusing to refresh it")

    catalog = load_raw_p4_catalog()
    for relative in FROZEN_P4_INPUT_PATHS:
        target = ROOT / relative
        if Path(relative).is_absolute() or ".." in Path(relative).parts:
            raise RuntimeError("P4 input paths must be repository-relative")
        if not relative.startswith("tests/fixtures/") or not target.exists():
            raise RuntimeError(f"invalid P4 fixture path: {relative}")
        paths = (target,) if target.is_file() else tuple(target.rglob("*"))
        for path in paths:
            if path.is_symlink() or (path.exists() and not (path.is_file() or path.is_dir())):
                raise RuntimeError(f"P4 fixture contains an unsafe path: {path}")
    return catalog


def _load_baseline_report(path: Path, profile: str, expected: int) -> dict[str, Any]:
    report = json.loads(path.read_text(encoding="utf-8"))
    aggregate = report.get("aggregate", {})
    if report.get("profile") != profile:
        raise RuntimeError(f"unexpected baseline profile in {path}")
    if (
        aggregate.get("selected"),
        aggregate.get("executed"),
        aggregate.get("passed"),
        aggregate.get("failed"),
        aggregate.get("errors"),
    ) != (expected, expected, expected, 0, 0):
        raise RuntimeError(f"baseline quality gate failed in {path}")
    if report.get("fixture", {}).get("sha256") != f"sha256:{P0_P3_CATALOG_SHA256}":
        raise RuntimeError(f"baseline report catalog identity changed in {path}")
    if report.get("config", {}).get("embedding") != {
        "provider": "hash",
        "model": "hash-v1",
        "dimensions": 384,
        "base_url": None,
        "api_key_env": None,
    }:
        raise RuntimeError(f"baseline report embedding profile changed in {path}")
    if report.get("planner", {}).get("enabled") is not False:
        raise RuntimeError(f"baseline report planner must be disabled in {path}")
    report_commit = report.get("tool", {}).get("git_commit")
    if not isinstance(report_commit, str) or not report_commit:
        raise RuntimeError(f"baseline report has no tool commit in {path}")
    _git_source_is_protected(report_commit)
    return report


def _paths(items: list[Any]) -> list[str]:
    return [Path(item.file_path).as_posix() for item in items]


def _run_single_pass_assay(
    *,
    case_id: str,
    repo_key: str,
    snapshot: str,
    query: str,
    probes: tuple[str, ...],
    expected_required_goal_classes: list[dict[str, Any]],
) -> tuple[dict[str, Any], Any, list[tuple[str, list[str]]]]:
    with tempfile.TemporaryDirectory(prefix="cst-p4-assay-") as raw_temp:
        repo = Path(raw_temp) / "repo"
        shutil.copytree(ROOT / snapshot, repo)
        config = replace(
            DEFAULT_CONFIG,
            retrieval=replace(DEFAULT_CONFIG.retrieval, final_top_k=1),
        )
        index_repository(repo, config)
        traced = trace_repository(repo, query, config)
        if traced.trace.outcome != "complete":
            raise RuntimeError(f"initial assay retrieval incomplete: {case_id}")
        pack_options = resolve_context_pack_options(
            config,
            context_lines=None,
            max_evidence_anchors=evidence_anchor_top_k(1),
        )
        pack = build_context_pack(traced.bundle, pack_options)

        followup_config = replace(
            config,
            retrieval=replace(config.retrieval, final_top_k=6),
        )
        probe_records: list[dict[str, Any]] = []
        probe_unions: list[tuple[str, list[str]]] = []
        for probe in probes:
            followup = trace_repository(repo, probe, followup_config)
            if followup.trace.outcome != "complete":
                raise RuntimeError(f"probe assay retrieval incomplete: {case_id}")
            results = _paths(followup.bundle.results)
            anchors = _paths(followup.bundle.evidence_anchors)
            probe_records.append(
                {
                    "query": probe,
                    "result_paths": results,
                    "evidence_anchor_paths": anchors,
                }
            )
            probe_unions.append((probe, list(dict.fromkeys([*results, *anchors]))))

        assay = {
            "case_id": case_id,
            "repo_key": repo_key,
            "query": query,
            "config": {
                "retrieval": {"final_top_k": 1},
                "embedding": {
                    "provider": "hash",
                    "model": "hash-v1",
                    "dimensions": 384,
                },
                "query_planner": {"enabled": False},
                "context_lines": None,
                "full_file": False,
            },
            "initial": {
                "result_paths": _paths(traced.bundle.results),
                "evidence_anchor_paths": _paths(traced.bundle.evidence_anchors),
                "context_pack_item_paths": [item.file_path for item in pack.items],
                "context_pack_status": pack.status,
            },
            "probes": probe_records,
            "expected_required_goal_classes": expected_required_goal_classes,
        }
        return assay, (traced.bundle, pack), probe_unions


def _build_assays() -> list[dict[str, Any]]:
    form_roles = ["view", "view_page", "layout_component"]
    route_roles = ["entrypoint", "router", "command", "handler", "route_config"]
    implementation_roles = [
        "service_impl",
        "executor",
        "engine",
        "middleware",
        "storage",
        "service",
        "repository",
        "source_adapter",
        "state_store",
        "composable",
        "scheduler",
        "utility",
        "store",
        "shared_component",
    ]
    java, (java_bundle, java_pack), java_probes = _run_single_pass_assay(
        case_id="owner-registration-form-test",
        repo_key="p4_exploration_java",
        snapshot="tests/fixtures/p4-exploration-java",
        query="OwnerController owner registration form validation test",
        probes=(
            "VIEWS_OWNER_CREATE_OR_UPDATE_FORM form template view",
            "OwnerController test",
        ),
        expected_required_goal_classes=[
            {
                "token_class": "form/page/view",
                "category": "entrypoints",
                "accepted_roles": form_roles,
            },
            {
                "token_class": "test",
                "category": "tests",
                "accepted_roles": ["test"],
            },
        ],
    )
    if java["initial"]["result_paths"] != [CONTROLLER]:
        raise RuntimeError("Java assay must select OwnerController at rank 1")
    if {OWNER_TEST, OWNER_FORM}.intersection(
        java["initial"]["context_pack_item_paths"]
    ):
        raise RuntimeError("Java initial pack unexpectedly contains test or form")
    if OWNER_FORM not in java_probes[0][1] or OWNER_TEST not in java_probes[1][1]:
        raise RuntimeError("Java probes do not recover the test and form within top 6")
    java_tokens = [token.lower() for token in tokenize_query(java["query"])]
    if not (java_tokens.index("form") < java_tokens.index("test")):
        raise RuntimeError("Java explicit role token order changed")

    frontend, (_, frontend_pack), frontend_probes = _run_single_pass_assay(
        case_id="qrcode-route-service-type",
        repo_key="p4_exploration_frontend",
        snapshot="tests/fixtures/real_projects/program_tool",
        query="QRCode page route service type",
        probes=(
            "QRCodeTool route controller endpoint",
            "qrcodeUtils service implementation",
        ),
        expected_required_goal_classes=[
            {
                "token_class": "route/controller/entrypoint",
                "category": "entrypoints",
                "accepted_roles": route_roles,
            },
            {
                "token_class": "implementation/service/repository",
                "category": "implementations",
                "accepted_roles": implementation_roles,
            },
        ],
    )
    if frontend["initial"]["result_paths"] != [QRCODE_VIEW]:
        raise RuntimeError("frontend assay must select QRCodeTool.vue at rank 1")
    if {QRCODE_ROUTE, QRCODE_UTILITY}.intersection(
        frontend["initial"]["context_pack_item_paths"]
    ):
        raise RuntimeError("frontend initial pack unexpectedly contains support files")
    if QRCODE_ROUTE not in frontend_probes[0][1] or QRCODE_UTILITY not in frontend_probes[1][1]:
        raise RuntimeError("frontend probes do not recover route and implementation")
    frontend_tokens = [token.lower() for token in tokenize_query(frontend["query"])]
    if not {"page", "route", "service"}.issubset(frontend_tokens):
        raise RuntimeError("frontend explicit role tokens changed")
    if not any(need.required and not need.matched_item_ids for need in frontend_pack.evidence_needs):
        raise RuntimeError("frontend initial pack no longer has executable gaps")

    exact, (exact_bundle, exact_pack), _ = _run_single_pass_assay(
        case_id="owner-controller-exact",
        repo_key="p4_exploration_java",
        snapshot="tests/fixtures/p4-exploration-java",
        query="OwnerController",
        probes=(),
        expected_required_goal_classes=[
            {
                "token_class": "route/controller/entrypoint",
                "category": "entrypoints",
                "accepted_roles": route_roles,
            }
        ],
    )
    if exact["initial"]["result_paths"] != [CONTROLLER]:
        raise RuntimeError("exact assay must select OwnerController")
    if not any("original_direct" in reason for reason in exact_bundle.results[0].reasons):
        raise RuntimeError("exact assay lost protected original-direct evidence")
    if not exact_pack.next_queries:
        raise RuntimeError("exact assay must retain a recommended structural gap")

    duplicate, (_, _), duplicate_probes = _run_single_pass_assay(
        case_id="solo-controller-no-gain",
        repo_key="p4_exploration_duplicate",
        snapshot="tests/fixtures/p4-exploration-duplicate",
        query="SoloController test",
        probes=("SOLO_VIEW test", "showSolo test"),
        expected_required_goal_classes=[
            {
                "token_class": "test",
                "category": "tests",
                "accepted_roles": ["test"],
            }
        ],
    )
    if duplicate["initial"]["result_paths"] != [SOLO_CONTROLLER]:
        raise RuntimeError("duplicate assay must select only SoloController")
    if any(paths != [SOLO_CONTROLLER] for _, paths in duplicate_probes):
        raise RuntimeError("duplicate assay probes must return only the fused path")
    if len({probe.casefold() for probe, _ in duplicate_probes}) != 2:
        raise RuntimeError("duplicate assay probes must remain distinct")
    return [java, frontend, exact, duplicate]


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + "\n"
    ).encode("utf-8")


def generate() -> None:
    _assert_generation_preconditions()
    p2_report = _load_baseline_report(BASELINE_P2_REPORT, "p2_context_pack", 5)
    ci_report = _load_baseline_report(BASELINE_CI_REPORT, "ci", 8)
    assays = _build_assays()

    p2_bytes = _json_bytes(p0_p3_quality_projection(p2_report))
    ci_bytes = _json_bytes(p0_p3_quality_projection(ci_report))
    manifest = {
        "schema_version": 1,
        "implementation_baseline": IMPLEMENTATION_BASELINE,
        "p3_baseline_blob": P3_BASELINE_BLOB,
        "p0_p3_catalog_blob": P0_P3_CATALOG_BLOB,
        "p0_p3_catalog_sha256": P0_P3_CATALOG_SHA256,
        "inputs": [
            {"path": path, "sha256": working_tree_content_hash(path)}
            for path in FROZEN_P4_INPUT_PATHS
        ],
        "quality_projections": [
            {
                "path": P2_PROJECTION_PATH.relative_to(ROOT).as_posix(),
                "sha256": hashlib.sha256(p2_bytes).hexdigest(),
            },
            {
                "path": CI_PROJECTION_PATH.relative_to(ROOT).as_posix(),
                "sha256": hashlib.sha256(ci_bytes).hexdigest(),
            },
        ],
        "assays": assays,
    }

    P4_MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    P2_PROJECTION_PATH.write_bytes(p2_bytes)
    CI_PROJECTION_PATH.write_bytes(ci_bytes)
    P4_MANIFEST_PATH.write_bytes(_json_bytes(manifest))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "command",
        nargs="?",
        default="generate",
        choices=("generate", "verify-junit"),
    )
    parser.add_argument("junitxml", nargs="?", type=Path)
    args = parser.parse_args()
    if args.command == "verify-junit":
        if args.junitxml is None:
            parser.error("verify-junit requires a JUnit XML path")
        print(json.dumps(verify_final_junit(args.junitxml), sort_keys=True))
        return
    if args.junitxml is not None:
        parser.error("generate does not accept a JUnit XML path")
    generate()


if __name__ == "__main__":
    main()
