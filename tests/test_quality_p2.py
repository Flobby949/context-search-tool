from __future__ import annotations

import shutil
from dataclasses import replace
from pathlib import Path

import pytest

from context_search_tool.config import DEFAULT_CONFIG, ToolConfig
from context_search_tool.context_pack import (
    ContextPackOptions,
    build_context_pack,
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
        full_file=False,
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
    assert overall["context_expected_count"] == {"count": 5, "mean": 2.0}

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
    assert all(
        case["context_pack"]["status"] == "ready"
        for case in cases.values()
    )
    assert {
        key: case["context_pack"]["confidence"]
        for key, case in cases.items()
    } == {
        ("context_pack_java", "workspace-page-flow"): "high",
        ("context_pack_java", "workspace-test-file"): "high",
        ("context_pack_java", "workspace-service-symbol"): "high",
        ("context_pack_frontend", "qrcode-feature-context"): "medium",
        ("context_pack_docs", "program-tool-developer-docs"): "medium",
    }
    assert cases[
        ("context_pack_java", "workspace-service-symbol")
    ]["metrics"]["required_missing_count"] == 0
    assert cases[
        ("context_pack_frontend", "qrcode-feature-context")
    ]["metrics"]["recommended_missing_count"] == 1
    assert cases[
        ("context_pack_docs", "program-tool-developer-docs")
    ]["metrics"]["context_content_bytes"] == 93
    assert cases[
        ("context_pack_docs", "program-tool-developer-docs")
    ]["metrics"]["result_count"] == 0


def test_exact_service_symbol_does_not_invent_flow_or_test_requirements(
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
    assert pack.confidence.level == "high"
    assert pack.missing_evidence == ()


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
