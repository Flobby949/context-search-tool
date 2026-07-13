import json
from dataclasses import replace
from pathlib import Path

from context_search_tool.models import (
    EvidenceAnchor,
    QueryPlan,
    QueryVariant,
    RetrievalResult,
    RetrievalSummary,
    SemanticMatch,
)
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


def test_markdown_does_not_add_per_result_semantic_provenance_table() -> None:
    base_bundle = sample_bundle()
    anchor = EvidenceAnchor(
        file_path=Path("README.md"),
        start_line=1,
        end_line=2,
        content="Audit documentation",
        score=0.4,
        score_parts={"lexical": 0.4},
        reasons=["documentation match"],
        anchor_kind="document",
    )
    base_bundle = replace(base_bundle, evidence_anchors=[anchor])
    provenance_bundle = replace(
        base_bundle,
        results=[
            replace(
                base_bundle.results[0],
                semantic_matches=[SemanticMatch("planner:0", 0.75)],
            )
        ],
        evidence_anchors=[
            replace(
                anchor,
                semantic_matches=[SemanticMatch("planner:0", 0.4)],
            )
        ],
        query_variants=[
            QueryVariant("original", base_bundle.query, "original"),
            QueryVariant("planner:0", "apply audit workflow", "planner"),
        ],
        variant_retrieval_status="hybrid",
    )

    assert format_markdown(provenance_bundle) == format_markdown(base_bundle)


def test_json_formatter_is_structured() -> None:
    output = format_json(sample_bundle())
    parsed = json.loads(output)

    assert parsed["query"] == "apply audit"
    assert parsed["results"][0]["file_path"] == "ApplyAuditController.java"
    assert parsed["results"][0]["score_parts"]["lexical"] == 0.8


def test_json_formatter_exposes_query_variants_and_semantic_matches() -> None:
    bundle = QueryBundle(
        query="数据看板统计图表功能",
        expanded_tokens=["数据看板统计图表功能", "dashboard"],
        results=[
            RetrievalResult(
                file_path=Path("DashboardController.java"),
                start_line=1,
                end_line=10,
                content="class DashboardController {}",
                score=0.9,
                score_parts={
                    "planner_semantic": 0.84,
                    "effective_semantic": 0.714,
                },
                reasons=["planner semantic match"],
                followup_keywords=[],
                semantic_matches=[SemanticMatch("planner:0", 0.84)],
            )
        ],
        followup_keywords=[],
        query_variants=[
            QueryVariant("original", "数据看板统计图表功能", "original"),
            QueryVariant("planner:0", "dashboard statistics chart", "planner"),
        ],
        variant_retrieval_status="hybrid",
    )

    payload = json.loads(format_json(bundle))

    assert payload["query_variants"] == [
        {
            "variant_id": "original",
            "text": "数据看板统计图表功能",
            "source": "original",
        },
        {
            "variant_id": "planner:0",
            "text": "dashboard statistics chart",
            "source": "planner",
        },
    ]
    assert payload["variant_retrieval_status"] == "hybrid"
    assert payload["results"][0]["semantic_matches"] == [
        {"variant_id": "planner:0", "score": 0.84}
    ]


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
            "semantic_matches": [],
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
            "semantic_matches": [],
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


def test_format_json_includes_repo_profile_planner_diagnostics() -> None:
    bundle = QueryBundle(
        query="cookies",
        expanded_tokens=["cookies"],
        results=[],
        followup_keywords=[],
        planner=QueryPlan(
            original_query="cookies",
            status="ok",
            provider="ollama",
            model="qwen3.5:4b-mlx",
            repo_profile_hash="sha256:test",
            repo_profile_truncated=True,
            discarded_hints=["RestTemplate"],
        ),
    )

    payload = json.loads(format_json(bundle))

    assert payload["planner"]["repo_profile_hash"] == "sha256:test"
    assert payload["planner"]["repo_profile_truncated"] is True
    assert payload["planner"]["discarded_hint_count"] == 1


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
