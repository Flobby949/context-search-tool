import json
from pathlib import Path

from context_search_tool.models import EvidenceAnchor, QueryPlan, RetrievalResult, RetrievalSummary
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


def test_markdown_formatter_includes_evidence_anchors_after_results() -> None:
    bundle = QueryBundle(
        query="apply audit",
        expanded_tokens=["apply", "audit"],
        followup_keywords=[],
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
        evidence_anchors=[
            EvidenceAnchor(
                file_path=Path("anchors/config.yaml"),
                start_line=1,
                end_line=8,
                content="audit_timeout: 30",
                score=0.42,
                score_parts={"lexical": 0.2},
                reasons=["configuration signal from symbol"],
                anchor_kind="config",
            )
        ],
    )

    output = format_markdown(bundle)

    assert output.index("## Results") < output.index("## Evidence Anchors")
    assert "anchors/config.yaml:1-8" in output
    assert "Anchor kind: config" in output
    assert "configuration signal from symbol" in output


def test_markdown_formatter_omits_evidence_anchors_section_when_empty() -> None:
    output = format_markdown(sample_bundle())

    assert "## Evidence Anchors" not in output


def test_json_formatter_is_structured() -> None:
    output = format_json(sample_bundle())
    parsed = json.loads(output)

    assert parsed["query"] == "apply audit"
    assert parsed["results"][0]["file_path"] == "ApplyAuditController.java"
    assert parsed["results"][0]["score_parts"]["lexical"] == 0.8


def test_json_formatter_includes_evidence_anchors_and_keeps_results() -> None:
    bundle = QueryBundle(
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
        evidence_anchors=[
            EvidenceAnchor(
                file_path=Path("anchors/config.yaml"),
                start_line=1,
                end_line=8,
                content="audit_timeout: 30",
                score=0.42,
                score_parts={"lexical": 0.2},
                reasons=["configuration signal from symbol"],
                anchor_kind="config",
            )
        ],
    )

    parsed = json.loads(format_json(bundle))

    assert parsed["results"] == [
        {
            "file_path": "ApplyAuditController.java",
            "start_line": 10,
            "end_line": 20,
            "content": "class ApplyAuditController {}",
            "score": 0.87,
            "score_parts": {"lexical": 0.8},
            "reasons": ["lexical match: apply audit"],
            "followup_keywords": ["pageEs"],
        }
    ]
    assert parsed["evidence_anchors"] == [
        {
            "file_path": "anchors/config.yaml",
            "start_line": 1,
            "end_line": 8,
            "content": "audit_timeout: 30",
            "score": 0.42,
            "score_parts": {"lexical": 0.2},
            "reasons": ["configuration signal from symbol"],
            "anchor_kind": "config",
        }
    ]


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


def test_json_formatter_includes_planner_diagnostics() -> None:
    bundle = QueryBundle(
        query="数据看板统计图表功能",
        expanded_tokens=["数据看板统计图表功能", "dashboard"],
        followup_keywords=[],
        results=[],
        planner=QueryPlan(
            original_query="数据看板统计图表功能",
            rewritten_queries=["数据看板 dashboard statistics chart"],
            grep_keywords=["Dashboard"],
            symbol_hints=["DashboardController"],
            intent="feature_lookup",
            status="ok",
            provider="ollama",
            model="qwen3.5:4b-mlx",
            prompt_version="qwen-query-planner-v1",
            prompt_hash="sha256:test",
            latency_ms=1200,
        ),
    )

    parsed = json.loads(format_json(bundle))

    assert parsed["planner"] == {
        "enabled": True,
        "provider": "ollama",
        "model": "qwen3.5:4b-mlx",
        "prompt_version": "qwen-query-planner-v1",
        "prompt_hash": "sha256:test",
        "status": "ok",
        "latency_ms": 1200,
        "rewritten_queries": ["数据看板 dashboard statistics chart"],
        "grep_keywords": ["Dashboard"],
        "symbol_hints": ["DashboardController"],
        "intent": "feature_lookup",
    }


def test_markdown_formatter_includes_concise_planner_line_when_ok() -> None:
    bundle = QueryBundle(
        query="数据看板统计图表功能",
        expanded_tokens=["数据看板统计图表功能", "dashboard"],
        followup_keywords=[],
        results=[],
        planner=QueryPlan(
            original_query="数据看板统计图表功能",
            grep_keywords=["Dashboard", "Statistics", "Chart"],
            symbol_hints=["DashboardController", "DashboardService"],
            status="ok",
            provider="ollama",
            model="qwen3.5:4b-mlx",
        ),
    )

    output = format_markdown(bundle)

    assert (
        "Query expanded by qwen3.5:4b-mlx: "
        "DashboardController, DashboardService, Dashboard, ... (+2 more)"
    ) in output


def test_markdown_formatter_stays_silent_on_planner_fallback() -> None:
    bundle = QueryBundle(
        query="targetToken",
        expanded_tokens=["targettoken"],
        followup_keywords=[],
        results=[],
        planner=QueryPlan(
            original_query="targetToken",
            status="fallback",
            provider="ollama",
            model="qwen3.5:4b-mlx",
            error="planner timed out after 8 seconds",
        ),
    )

    output = format_markdown(bundle)

    assert "Query expanded by" not in output


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
