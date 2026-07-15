from __future__ import annotations

import json
import shutil
from dataclasses import replace
from pathlib import Path

import pytest

import context_search_tool.mcp_tools as mcp_tools
from context_search_tool.config import DEFAULT_CONFIG, ToolConfig
from context_search_tool.context_pack import (
    ContextPackOptions,
    build_context_pack,
    context_pack_payload,
    resolve_context_pack_options,
)
from context_search_tool.indexer import index_repository
from context_search_tool.quality.cases import load_quality_fixture
from context_search_tool.quality.runner import run_quality_fixture
from context_search_tool.retrieval import (
    evidence_anchor_top_k,
    query_repository,
)


FIXTURES = Path(__file__).parent / "fixtures"
CATALOG = FIXTURES / "retrieval_quality" / "queries.json"
JAVA_SERVICE_PATH = (
    "src/main/java/com/example/workspace/service/impl/WorkspaceServiceImpl.java"
)
JAVA_TEST_PATH = (
    "src/test/java/com/example/workspace/controller/WorkspaceControllerTest.java"
)
IndexedP2Snapshots = tuple[
    ToolConfig,
    ContextPackOptions,
    dict[str, Path],
]


def _p2_config() -> ToolConfig:
    overrides = load_quality_fixture(CATALOG).profile_configs["p2_context_pack"]
    return replace(
        DEFAULT_CONFIG,
        **{
            section: replace(getattr(DEFAULT_CONFIG, section), **values)
            for section, values in overrides.items()
        },
    )


@pytest.fixture(scope="module")
def indexed_p2_snapshots(
    tmp_path_factory: pytest.TempPathFactory,
) -> IndexedP2Snapshots:
    config = _p2_config()
    pack_options = resolve_context_pack_options(
        config,
        context_lines=None,
        max_evidence_anchors=evidence_anchor_top_k(
            config.retrieval.final_top_k
        ),
    )
    workspace_root = tmp_path_factory.mktemp("p2-context-pack")
    workspaces = {}
    for snapshot_name in ("context-pack-java", "context-pack-docs"):
        workspace = workspace_root / snapshot_name
        shutil.copytree(FIXTURES / snapshot_name, workspace)
        index_repository(workspace, config)
        workspaces[snapshot_name] = workspace
    return config, pack_options, workspaces


def test_phase_two_context_pack_profile_is_deterministic_offline() -> None:
    report = run_quality_fixture(CATALOG, "p2_context_pack", None, None)

    assert {
        key: value
        for key, value in report["aggregate"].items()
        if key != "metrics"
    } == {
        "total": 5,
        "selected": 5,
        "attempted": 5,
        "executed": 5,
        "passed": 5,
        "failed": 0,
        "skipped": 0,
        "known_gaps": 0,
        "informational": 0,
        "errors": 0,
    }
    overall = report["aggregate"]["metrics"]["overall"]
    assert overall["context_completeness"] == {"count": 5, "mean": 1.0}
    assert overall["evidence_need_completeness"] == {"count": 5, "mean": 0.8}
    for metric_name in (
        "evidence_need_count",
        "required_need_count",
        "matched_required_need_count",
        "pack_bytes",
        "content_bytes",
        "truncated_item_count",
        "omitted_item_count",
    ):
        assert overall[metric_name]["count"] == 5

    cases = {
        (case["repo_key"], case["case_id"]): case
        for case in report["cases"]
    }
    assert set(cases) == {
        ("context_pack_java", "workspace-page-flow"),
        ("context_pack_java", "workspace-test-file"),
        ("context_pack_java", "workspace-service-symbol"),
        ("context_pack_frontend", "qrcode-feature-context"),
        ("context_pack_docs", "program-tool-developer-docs"),
    }
    assert {
        key: case["context_pack"]["status"]
        for key, case in cases.items()
    } == {
        ("context_pack_java", "workspace-page-flow"): "ready",
        ("context_pack_java", "workspace-test-file"): "partial",
        ("context_pack_java", "workspace-service-symbol"): "ready",
        ("context_pack_frontend", "qrcode-feature-context"): "ready",
        ("context_pack_docs", "program-tool-developer-docs"): "ready",
    }
    assert {
        key: case["context_pack"]["confidence"]
        for key, case in cases.items()
    } == {
        ("context_pack_java", "workspace-page-flow"): "high",
        ("context_pack_java", "workspace-test-file"): "low",
        ("context_pack_java", "workspace-service-symbol"): "medium",
        ("context_pack_frontend", "qrcode-feature-context"): "medium",
        ("context_pack_docs", "program-tool-developer-docs"): "medium",
    }
    assert cases[
        ("context_pack_java", "workspace-service-symbol")
    ]["metrics"]["evidence_need_completeness"] == 1.0
    assert cases[
        ("context_pack_java", "workspace-test-file")
    ]["metrics"]["evidence_need_completeness"] == 0.0
    assert cases[
        ("context_pack_docs", "program-tool-developer-docs")
    ]["metrics"]["content_bytes"] == 93
    assert cases[
        ("context_pack_docs", "program-tool-developer-docs")
    ]["metrics"]["result_count"] == 0


def test_real_context_profile_is_opt_in_and_does_not_change_offline_selection() -> None:
    fixture = load_quality_fixture(CATALOG)
    real_repo = next(
        repo for repo in fixture.repos if repo.repo_key == "spring_petclinic"
    )

    assert real_repo.profiles == ("p2_real_context",)
    assert len(real_repo.queries) == 4
    assert all(case.profiles == ("p2_real_context",) for case in real_repo.queries)
    assert all(
        "p2_context_pack" not in repo.profiles
        for repo in fixture.repos
        if repo.repo_key == "spring_petclinic"
    )


def test_real_context_contract_repeats_pack_and_keeps_feedback_metadata_only(
    indexed_p2_snapshots: IndexedP2Snapshots,
) -> None:
    config, pack_options, workspaces = indexed_p2_snapshots
    query = "workspace test file"

    first = context_pack_payload(
        build_context_pack(
            query_repository(workspaces["context-pack-java"], query, config),
            pack_options,
        )
    )
    second = context_pack_payload(
        build_context_pack(
            query_repository(workspaces["context-pack-java"], query, config),
            pack_options,
        )
    )

    assert first == second
    assert {
        key: first["budget"][key]
        for key in (
            "max_items",
            "max_excerpts_per_item",
            "max_excerpt_bytes",
            "max_item_content_bytes",
            "max_total_content_bytes",
            "max_pack_bytes",
        )
    } == {
        "max_items": 12,
        "max_excerpts_per_item": 2,
        "max_excerpt_bytes": 4096,
        "max_item_content_bytes": 8192,
        "max_total_content_bytes": 49_152,
        "max_pack_bytes": 65_536,
    }
    feedback = mcp_tools._feedback_context_pack_payload({"context_pack": first})
    assert feedback is not None
    serialized_feedback = json.dumps(feedback, ensure_ascii=False)
    private_values = [
        query,
        *(item["file_path"] for item in first["items"]),
        *(excerpt["content"] for item in first["items"] for excerpt in item["excerpts"]),
        *(term for need in first["evidence_needs"] for term in need["subject_terms"]),
        *(item["query"] for item in first["next_queries"]),
    ]
    assert all(value not in serialized_feedback for value in private_values if value)


def test_exact_service_symbol_does_not_invent_required_flow_or_test_requirements(
    indexed_p2_snapshots: IndexedP2Snapshots,
) -> None:
    config, pack_options, workspaces = indexed_p2_snapshots
    bundle = query_repository(
        workspaces["context-pack-java"],
        "WorkspaceServiceImpl",
        config,
    )
    service_results = [
        result
        for result in bundle.results
        if result.file_path.as_posix() == JAVA_SERVICE_PATH
    ]
    assert len(service_results) == 1

    service_only = replace(
        bundle,
        results=service_results,
        evidence_anchors=[],
    )
    pack = build_context_pack(service_only, pack_options)

    assert [
        (item.file_path, item.group) for item in pack.items
    ] == [(JAVA_SERVICE_PATH, "implementations")]
    assert pack.status == "ready"
    assert pack.confidence.level == "medium"
    assert pack.missing_evidence
    assert all(not missing.required for missing in pack.missing_evidence)


def test_explicit_test_query_requires_test_evidence(
    indexed_p2_snapshots: IndexedP2Snapshots,
) -> None:
    config, pack_options, workspaces = indexed_p2_snapshots
    bundle = query_repository(
        workspaces["context-pack-java"],
        "workspace test file",
        config,
    )
    assert JAVA_TEST_PATH in {
        result.file_path.as_posix() for result in bundle.results
    }
    non_test_results = [
        result
        for result in bundle.results
        if result.file_path.as_posix() != JAVA_TEST_PATH
    ]
    assert non_test_results

    without_test = replace(
        bundle,
        results=non_test_results,
        evidence_anchors=[
            anchor
            for anchor in bundle.evidence_anchors
            if anchor.file_path.as_posix() != JAVA_TEST_PATH
        ],
    )
    pack = build_context_pack(without_test, pack_options)

    assert pack.status == "partial"
    assert pack.confidence.level == "low"
    assert ("tests", True) in {
        (missing.category, missing.required)
        for missing in pack.missing_evidence
    }


def test_developer_docs_query_is_anchor_only(
    indexed_p2_snapshots: IndexedP2Snapshots,
) -> None:
    config, _, workspaces = indexed_p2_snapshots
    bundle = query_repository(
        workspaces["context-pack-docs"],
        "Program Tool Developer Setup documentation",
        config,
    )

    assert bundle.results == []
    assert [
        (anchor.file_path.as_posix(), anchor.anchor_kind)
        for anchor in bundle.evidence_anchors
    ] == [("README.md", "readme")]
