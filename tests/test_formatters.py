import json
from pathlib import Path

from context_search_tool.models import RetrievalResult, RetrievalSummary
from context_search_tool.retrieval import QueryBundle
from context_search_tool.formatters import format_json, format_markdown


def sample_bundle() -> QueryBundle:
    return QueryBundle(
        query="apply audit",
        expanded_tokens=["apply", "audit"],
        followup_keywords=["pageEs", "INVOLVED_BY_ME"],
        results=[
            RetrievalResult(
                file_path=Path("ApplyAuditController.java"),
                start_line=10,
                end_line=20,
                content="class ApplyAuditController {}",
                score=0.87,
                score_parts={"lexical": 0.8},
                reasons=["lexical match: apply audit"],
                followup_keywords=["pageEs"],
            )
        ],
    )


def test_markdown_formatter_contains_paths_reasons_and_snippets() -> None:
    output = format_markdown(sample_bundle())

    assert "ApplyAuditController.java:10-20" in output
    assert "lexical match: apply audit" in output
    assert "```" in output


def test_markdown_formatter_uses_longer_fence_than_snippet_backticks() -> None:
    bundle = QueryBundle(
        query="markdown fence",
        expanded_tokens=["markdown", "fence"],
        followup_keywords=[],
        results=[
            RetrievalResult(
                file_path=Path("docs/example.md"),
                start_line=1,
                end_line=5,
                content="intro\n```\ninner block\n```\noutro",
                score=0.5,
                score_parts={},
                reasons=[],
                followup_keywords=[],
            )
        ],
    )

    output = format_markdown(bundle)

    assert output.count("\n````\n") == 2
    assert "intro\n```\ninner block\n```\noutro" in output


def test_markdown_formatter_includes_summary_before_results() -> None:
    bundle = sample_bundle()
    bundle = QueryBundle(
        query=bundle.query,
        expanded_tokens=bundle.expanded_tokens,
        followup_keywords=bundle.followup_keywords,
        results=bundle.results,
        summary=RetrievalSummary(
            entry_points=["GET /apply/audit/stats/wait -> ResourceAuditController.statsWait"],
            implementation=["ResourceAuditServiceImpl.statsWait"],
            related_types=["WorkbenchResourceAuditStatsDTO"],
            possibly_legacy=["WorkbenchResourceStatsDTO"],
        ),
    )

    output = format_markdown(bundle)

    expected_summary = """## Summary
### Likely Entry Points
- GET /apply/audit/stats/wait -> ResourceAuditController.statsWait
### Likely Implementation
- ResourceAuditServiceImpl.statsWait
### Related Types
- WorkbenchResourceAuditStatsDTO
### Possibly Legacy
- WorkbenchResourceStatsDTO"""

    assert expected_summary in output
    assert output.index("## Summary") < output.index("## Results")
    assert "## Results" in output


def test_json_formatter_is_structured() -> None:
    output = format_json(sample_bundle())
    parsed = json.loads(output)

    assert parsed["query"] == "apply audit"
    assert parsed["results"][0]["file_path"] == "ApplyAuditController.java"
    assert parsed["results"][0]["score_parts"]["lexical"] == 0.8


def test_json_formatter_includes_summary_sections() -> None:
    bundle = QueryBundle(
        query="summary",
        expanded_tokens=["summary"],
        results=[],
        followup_keywords=[],
    )
    output = format_json(bundle)
    parsed = json.loads(output)

    assert parsed["summary"] == {
        "entry_points": [],
        "implementation": [],
        "related_types": [],
        "possibly_legacy": [],
    }
    assert parsed["results"] == []


def test_formatters_handle_empty_results() -> None:
    bundle = QueryBundle(
        query="missing",
        expanded_tokens=[],
        followup_keywords=[],
        results=[],
    )

    markdown = format_markdown(bundle)
    parsed = json.loads(format_json(bundle))

    assert "No results." in markdown
    assert parsed["results"] == []
