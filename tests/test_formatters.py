import json
from dataclasses import replace
from pathlib import Path

import pytest

from context_search_tool import context_pack, formatters
from context_search_tool.context_pack import (
    CONTEXT_GROUPS,
    INVALID_REFERENCE_ERROR,
    ContextPackError,
    ContextPackOptions,
)
from context_search_tool.models import (
    EvidenceAnchor,
    QueryPlan,
    QueryVariant,
    RetrievalResult,
    RetrievalSpan,
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


def compatibility_bundle() -> QueryBundle:
    return QueryBundle(
        query="数据看板 audit",
        expanded_tokens=["数据看板", "audit"],
        results=[
            RetrievalResult(
                file_path=Path("src/PageController.py"),
                start_line=7,
                end_line=9,
                content="def page():\n    return 'ok'",
                score=0.91,
                score_parts={"semantic": 0.75, "lexical": 0.6},
                reasons=["exact route", "planner semantic match"],
                followup_keywords=["PageService"],
                semantic_matches=[
                    SemanticMatch("original", 0.7),
                    SemanticMatch("planner:0", 0.75),
                ],
            ),
            RetrievalResult(
                file_path=Path("src/PageService.py"),
                start_line=20,
                end_line=24,
                content="class PageService:\n    pass",
                score=0.82,
                score_parts={"rerank": 0.82, "lexical": 0.4},
                reasons=["implementation match"],
                followup_keywords=[],
                semantic_matches=[SemanticMatch("planner:0", 0.68)],
            ),
        ],
        followup_keywords=["PageService", "PageDTO"],
        summary=RetrievalSummary(
            entry_points=["PageController.page"],
            implementation=["PageService"],
            related_types=["PageDTO"],
            possibly_legacy=["OldPage"],
        ),
        planner=QueryPlan(
            original_query="数据看板 audit",
            rewritten_queries=["dashboard audit"],
            grep_keywords=["PageController", "audit"],
            symbol_hints=["PageService"],
            intent="feature_lookup",
            status="ok",
            provider="ollama",
            model="qwen-test",
            prompt_version="planner-v1",
            prompt_hash="sha256:prompt",
            latency_ms=17,
            repo_profile_hash="sha256:repo",
            repo_profile_truncated=True,
            discarded_hints=[f"discarded-{index}" for index in range(9)],
        ),
        evidence_anchors=[
            EvidenceAnchor(
                file_path=Path("README.md"),
                start_line=1,
                end_line=3,
                content="看板 audit guide",
                score=0.5,
                score_parts={"anchor": 0.5, "lexical": 0.25},
                reasons=["README anchor"],
                anchor_kind="readme",
                semantic_matches=[SemanticMatch("planner:0", 0.44)],
            )
        ],
        query_variants=[
            QueryVariant("original", "数据看板 audit", "original"),
            QueryVariant("planner:0", "dashboard audit", "planner"),
        ],
        variant_retrieval_status="hybrid",
    )


def context_options() -> ContextPackOptions:
    return ContextPackOptions(
        max_results=12,
        max_evidence_anchors=4,
        context_before_lines=8,
        context_after_lines=12,
        full_file=False,
        max_full_file_bytes=200_000,
    )


def test_format_json_preserves_complete_pre_refactor_output() -> None:
    expected = """{
  "evidence_anchors": [
    {
      "anchor_kind": "readme",
      "content": "\\u770b\\u677f audit guide",
      "end_line": 3,
      "file_path": "README.md",
      "reasons": [
        "README anchor"
      ],
      "score": 0.5,
      "score_parts": {
        "anchor": 0.5,
        "lexical": 0.25
      },
      "semantic_matches": [
        {
          "score": 0.44,
          "variant_id": "planner:0"
        }
      ],
      "start_line": 1
    }
  ],
  "expanded_tokens": [
    "\\u6570\\u636e\\u770b\\u677f",
    "audit"
  ],
  "followup_keywords": [
    "PageService",
    "PageDTO"
  ],
  "planner": {
    "discarded_hint_count": 9,
    "discarded_hints": [
      "discarded-0",
      "discarded-1",
      "discarded-2",
      "discarded-3",
      "discarded-4",
      "discarded-5",
      "discarded-6",
      "discarded-7"
    ],
    "enabled": true,
    "grep_keywords": [
      "PageController",
      "audit"
    ],
    "intent": "feature_lookup",
    "latency_ms": 17,
    "model": "qwen-test",
    "prompt_hash": "sha256:prompt",
    "prompt_version": "planner-v1",
    "provider": "ollama",
    "repo_profile_hash": "sha256:repo",
    "repo_profile_truncated": true,
    "rewritten_queries": [
      "dashboard audit"
    ],
    "status": "ok",
    "symbol_hints": [
      "PageService"
    ]
  },
  "query": "\\u6570\\u636e\\u770b\\u677f audit",
  "query_variants": [
    {
      "source": "original",
      "text": "\\u6570\\u636e\\u770b\\u677f audit",
      "variant_id": "original"
    },
    {
      "source": "planner",
      "text": "dashboard audit",
      "variant_id": "planner:0"
    }
  ],
  "results": [
    {
      "content": "def page():\\n    return 'ok'",
      "end_line": 9,
      "file_path": "src/PageController.py",
      "followup_keywords": [
        "PageService"
      ],
      "reasons": [
        "exact route",
        "planner semantic match"
      ],
      "score": 0.91,
      "score_parts": {
        "lexical": 0.6,
        "semantic": 0.75
      },
      "semantic_matches": [
        {
          "score": 0.7,
          "variant_id": "original"
        },
        {
          "score": 0.75,
          "variant_id": "planner:0"
        }
      ],
      "start_line": 7
    },
    {
      "content": "class PageService:\\n    pass",
      "end_line": 24,
      "file_path": "src/PageService.py",
      "followup_keywords": [],
      "reasons": [
        "implementation match"
      ],
      "score": 0.82,
      "score_parts": {
        "lexical": 0.4,
        "rerank": 0.82
      },
      "semantic_matches": [
        {
          "score": 0.68,
          "variant_id": "planner:0"
        }
      ],
      "start_line": 20
    }
  ],
  "summary": {
    "entry_points": [
      "PageController.page"
    ],
    "implementation": [
      "PageService"
    ],
    "possibly_legacy": [
      "OldPage"
    ],
    "related_types": [
      "PageDTO"
    ]
  },
  "variant_retrieval_status": "hybrid"
}"""

    assert format_json(compatibility_bundle()) == expected


def test_query_payload_matches_the_complete_raw_query_payload() -> None:
    bundle = compatibility_bundle()

    payload = formatters.query_payload(bundle)

    assert payload == json.loads(format_json(bundle))
    assert list(payload["results"][0]) == [
        "file_path",
        "start_line",
        "end_line",
        "content",
        "score",
        "score_parts",
        "reasons",
        "followup_keywords",
        "semantic_matches",
    ]
    assert b'"spans"' not in format_json(bundle).encode("utf-8")


def test_raw_query_payload_ignores_internal_retrieval_spans() -> None:
    baseline = compatibility_bundle()
    with_spans = replace(
        baseline,
        results=[
            replace(
                baseline.results[0],
                spans=(RetrievalSpan(7, 9, 0.91, ("lexical", "semantic")),),
            ),
            baseline.results[1],
        ],
    )

    assert formatters.query_payload(with_spans) == formatters.query_payload(baseline)
    assert format_json(with_spans).encode("utf-8") == format_json(baseline).encode(
        "utf-8"
    )


def test_context_json_appends_pack_without_changing_raw_query_payload() -> None:
    bundle = compatibility_bundle()
    pack = context_pack.build_context_pack(bundle, context_options())
    raw_payload = formatters.query_payload(bundle)
    raw_snapshot = dict(raw_payload)

    output = formatters.format_context_json(raw_payload, bundle, pack)
    parsed = json.loads(output)
    parsed_pack = parsed.pop("context_pack")

    assert raw_payload == raw_snapshot
    assert parsed == json.loads(format_json(bundle))
    assert parsed_pack == context_pack.context_pack_payload(bundle, pack)
    assert list(parsed_pack["groups"]) == list(CONTEXT_GROUPS)
    assert list(json.loads(output))[-1] == "context_pack"


def test_context_json_rejects_non_finite_values() -> None:
    bundle = compatibility_bundle()
    pack = context_pack.build_context_pack(bundle, context_options())

    with pytest.raises(ValueError):
        formatters.format_context_json({"score": float("nan")}, bundle, pack)


def test_context_markdown_renders_sections_items_and_budget_in_reading_order() -> None:
    bundle = compatibility_bundle()
    pack = context_pack.build_context_pack(bundle, context_options())

    output = formatters.format_context_markdown(bundle, pack)

    ordered_tokens = [
        "# Context Pack",
        "Query:",
        "Status:",
        "Confidence:",
        "## Read First",
        "## Missing Evidence",
        "## Next Queries",
        "## Budget",
    ]
    positions = [output.index(token) for token in ordered_tokens]
    assert positions == sorted(positions)
    assert "Planner: ok" in output
    assert "Query expanded by qwen-test: PageService, PageController, audit" in output

    for item_id in pack.reading_order:
        item = next(item for item in pack.items if item.id == item_id)
        source = context_pack.resolve_context_item(bundle, item)
        heading = (
            f"### {item.id} - {item.file_path}:"
            f"{item.start_line}-{item.end_line}"
        )
        assert output.count(heading) == 1
        assert f"Group: {item.group}" in output
        assert f"Role: {item.role}" in output
        assert output.count(source.content) == 1
        for reason in source.reasons:
            assert f"- {reason}" in output

    assert "- Recommended: related_types" in output
    assert "- Recommended: tests" in output
    for suggestion in pack.next_queries:
        assert f"- Purpose: {suggestion.purpose}" in output
        assert f"  Query: {suggestion.query}" in output
        assert f"  Reason: {suggestion.reason}" in output

    for field_name in (
        "max_results",
        "max_evidence_anchors",
        "max_items",
        "included_results",
        "included_evidence_anchors",
        "content_bytes",
        "context_before_lines",
        "context_after_lines",
        "full_file",
        "max_full_file_bytes",
    ):
        assert f"- {field_name}: {getattr(pack.budget, field_name)}" in output


def test_context_markdown_labels_required_missing_evidence() -> None:
    bundle = replace(
        sample_bundle(),
        query="controller route",
        results=[
            replace(
                sample_bundle().results[0],
                file_path=Path("src/services/audit.py"),
            )
        ],
    )
    pack = context_pack.build_context_pack(bundle, context_options())

    output = formatters.format_context_markdown(bundle, pack)

    assert "- Required: entrypoints" in output
    assert "- Purpose: find_entrypoints" in output
    assert "  Query:" in output
    assert "  Reason: required evidence for entrypoints is missing" in output


@pytest.mark.parametrize(
    ("planner", "expected_status", "has_hint"),
    [
        (QueryPlan.disabled_default(), "disabled", False),
        (
            QueryPlan(
                original_query="数据看板 audit",
                status="fallback",
                provider="ollama",
                model="qwen-test",
                error="secret planner error",
            ),
            "fallback",
            False,
        ),
        (compatibility_bundle().planner, "ok", True),
    ],
)
def test_context_markdown_always_emits_planner_status_and_only_existing_hint(
    planner: QueryPlan,
    expected_status: str,
    has_hint: bool,
) -> None:
    bundle = replace(compatibility_bundle(), planner=planner)
    pack = context_pack.build_context_pack(bundle, context_options())

    output = formatters.format_context_markdown(bundle, pack)

    assert f"Planner: {expected_status}" in output
    assert ("Query expanded by" in output) is has_hint


def test_context_markdown_renders_an_empty_pack() -> None:
    bundle = QueryBundle(
        query="missing",
        expanded_tokens=[],
        results=[],
        followup_keywords=[],
    )
    pack = context_pack.build_context_pack(bundle, context_options())

    output = formatters.format_context_markdown(bundle, pack)

    assert "Status: empty" in output
    assert "Confidence: none" in output
    assert "## Read First\n- (none)" in output
    assert "- Required: results" in output
    assert "## Next Queries\n- (none)" in output


def test_context_markdown_rejects_nonexistent_reading_order_id() -> None:
    bundle = compatibility_bundle()
    pack = context_pack.build_context_pack(bundle, context_options())
    invalid_pack = replace(pack, reading_order=(*pack.reading_order, "result:999"))

    with pytest.raises(ContextPackError) as exc_info:
        formatters.format_context_markdown(bundle, invalid_pack)

    assert str(exc_info.value) == INVALID_REFERENCE_ERROR


def test_context_markdown_rejects_invalid_source_index() -> None:
    bundle = compatibility_bundle()
    pack = context_pack.build_context_pack(bundle, context_options())
    invalid_item = replace(pack.items[0], source_index=999)
    invalid_pack = replace(pack, items=(invalid_item, *pack.items[1:]))

    with pytest.raises(ContextPackError) as exc_info:
        formatters.format_context_markdown(bundle, invalid_pack)

    assert str(exc_info.value) == INVALID_REFERENCE_ERROR


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
