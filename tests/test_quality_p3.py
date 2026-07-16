from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from context_search_tool.config import RetrievalConfig, ToolConfig
from context_search_tool.formatters import query_payload
from context_search_tool.indexer import index_repository
from context_search_tool.retrieval import query_repository, trace_repository
from context_search_tool.retrieval_trace import CANONICAL_TRACE_STAGES


FIXTURES = Path(__file__).parent / "fixtures"

CASES = (
    (
        "java",
        FIXTURES / "context-pack-java",
        "workspace page flow controller service dto",
    ),
    (
        "frontend",
        FIXTURES / "real_projects" / "program_tool",
        "QRCode page route service type",
    ),
    (
        "docs",
        FIXTURES / "context-pack-docs",
        "Program Tool Developer Setup documentation",
    ),
)


@pytest.mark.parametrize(("name", "source", "query"), CASES)
def test_p3_trace_coverage_is_complete_and_raw_results_are_unchanged(
    tmp_path: Path,
    name: str,
    source: Path,
    query: str,
) -> None:
    repo = tmp_path / name
    shutil.copytree(source, repo)
    config = ToolConfig(
        retrieval=RetrievalConfig(
            semantic_top_k=24,
            lexical_top_k=24,
            final_top_k=8,
            context_before_lines=2,
            context_after_lines=2,
        )
    )
    index_repository(repo, config)

    plain = query_repository(repo, query, config)
    traced = trace_repository(repo, query, config)

    assert query_payload(traced.bundle) == query_payload(plain)
    assert traced.trace.outcome == "complete"
    assert [stage.name for stage in traced.trace.stages] == list(
        CANONICAL_TRACE_STAGES
    )
    assert traced.trace.final_selections
    covered = sum(
        bool(
            selection.sources
            and selection.rank_history
            and selection.selection_reason
        )
        for selection in traced.trace.final_selections
    )
    assert covered / len(traced.trace.final_selections) == 1.0
    assert traced.trace.final_selection_count == (
        len(traced.bundle.results) + len(traced.bundle.evidence_anchors)
    )
