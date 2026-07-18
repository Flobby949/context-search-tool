from __future__ import annotations

import shutil
from dataclasses import replace
from pathlib import Path

import pytest

from context_search_tool.config import DEFAULT_CONFIG
from context_search_tool.indexer import index_repository
from context_search_tool.retrieval import query_repository
from p5_graph_identity import ROOT, load_input_manifest


_PROTECTED_CASES = {
    "apply-audit-endpoint": (
        "tests/fixtures/java-spring-mini",
        "/apply/audit/pageEs INVOLVED_BY_ME",
    ),
    "workspace-service-symbol": (
        "tests/fixtures/context-pack-java",
        "WorkspaceServiceImpl",
    ),
    "dashboard-controller-path": (
        "tests/fixtures/real_projects/cross_language_dashboard",
        "src/main/java/com/example/dashboard/DashboardController.java",
    ),
    "order-service-symbol": (
        "tests/fixtures/real_projects/embedding_ab",
        "OrderService cancel method",
    ),
}


def _p5_config():
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


@pytest.mark.parametrize("case_id", tuple(_PROTECTED_CASES))
def test_ready_v5_protected_direct_score_parts_are_byte_exact(
    tmp_path: Path,
    case_id: str,
) -> None:
    fixture, query = _PROTECTED_CASES[case_id]
    repo = tmp_path / case_id
    shutil.copytree(ROOT / fixture, repo)
    config = _p5_config()
    index_repository(repo, config)

    result = query_repository(repo, query, config).results[0]
    expected = next(
        item
        for item in load_input_manifest()["evidence"]["protected_direct"]
        if item["case_id"] == case_id
    )

    assert result.file_path.as_posix() == expected["winner"]
    assert (result.start_line, result.end_line) == (
        expected["start_line"],
        expected["end_line"],
    )
    assert _direct_score_parts(result.score_parts) == expected["direct_score_parts"]
