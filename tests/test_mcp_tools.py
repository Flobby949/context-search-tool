import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest
from typer.testing import CliRunner

import context_search_tool.mcp_tools as mcp_tools
from context_search_tool import cli, formatters
from context_search_tool.cli import app
from context_search_tool.config import ContextConfig, ToolConfig, render_config
from context_search_tool.context_pack import builder as context_pack_v2_builder
from context_search_tool.context_pack import serialization as context_pack_v2_serialization
from context_search_tool.context_pack import (
    CONTEXT_GROUPS,
    ContextPackError,
    build_context_pack,
    context_pack_payload,
    resolve_context_pack_options,
)
from context_search_tool.mcp_tools import (
    context_search_context_tool,
    context_search_explain_tool,
    context_search_index_tool,
    context_search_query_tool,
    context_search_stats_tool,
    context_search_trace_tool,
)
from context_search_tool.models import (
    EvidenceAnchor,
    QueryPlan,
    QueryVariant,
    RetrievalResult,
    RetrievalSummary,
    SemanticMatch,
)
from context_search_tool.retrieval import (
    QueryBundle,
    TracedQueryBundle,
    evidence_anchor_top_k,
)
from context_search_tool.retrieval_trace import (
    RetrievalTraceCollector,
    RetrievalTraceError,
    TraceQuery,
)


def _write_java_repo(repo: Path) -> None:
    repo.mkdir()
    (repo / "ApplyAuditController.java").write_text(
        '''
import org.springframework.web.bind.annotation.PostMapping;

class ApplyAuditController {
  @PostMapping("/apply/audit/pageEs")
  String pageEs() { return service.pageEs(); }
}
'''.strip(),
        encoding="utf-8",
    )
    (repo / "ApplyAuditServiceImpl.java").write_text(
        '''
class ApplyAuditServiceImpl {
  String pageEs() { return "ok"; }
}
'''.strip(),
        encoding="utf-8",
    )


def _write_index_marker(repo: Path) -> None:
    repo.mkdir()
    index_dir = repo / ".context-search"
    index_dir.mkdir()
    (index_dir / "index.sqlite").touch()


def _deterministic_bundle(
    *,
    query: str = "audit endpoint",
    result_path: str = "src/AuditController.java",
    result_content: str = "class AuditController {}",
) -> QueryBundle:
    return QueryBundle(
        query=query,
        expanded_tokens=["audit", "endpoint"],
        followup_keywords=["AuditService"],
        results=[
            RetrievalResult(
                file_path=Path(result_path),
                start_line=10,
                end_line=10 + result_content.count("\n"),
                content=result_content,
                score=0.87,
                score_parts={"lexical": 0.8, "evidence_priority": 0.0},
                reasons=["lexical match: audit endpoint"],
                followup_keywords=["AuditService"],
            )
        ],
        evidence_anchors=[
            EvidenceAnchor(
                file_path=Path("README.md"),
                start_line=1,
                end_line=1,
                content="Audit endpoint documentation",
                score=0.42,
                score_parts={"lexical": 0.2},
                reasons=["documentation signal"],
                anchor_kind="readme",
            )
        ],
        summary=RetrievalSummary(entry_points=["AuditController"]),
        query_variants=[QueryVariant("original", query, "original")],
    )


def test_mcp_raw_payload_ignores_private_exact_context_content() -> None:
    baseline = _deterministic_bundle()
    with_exact_context = _deterministic_bundle()
    object.__setattr__(
        with_exact_context.results[0],
        "_context_content",
        f"{with_exact_context.results[0].content}\nPRIVATE_RESULT_SENTINEL",
    )
    object.__setattr__(
        with_exact_context.evidence_anchors[0],
        "_context_content",
        f"{with_exact_context.evidence_anchors[0].content}\nPRIVATE_ANCHOR_SENTINEL",
    )

    assert mcp_tools._query_payload(with_exact_context) == mcp_tools._query_payload(
        baseline
    )


def test_mcp_tools_index_query_stats_and_explain(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write_java_repo(repo)

    indexed = context_search_index_tool(str(repo))
    assert indexed["ok"] is True
    assert indexed["summary"]["files_indexed"] == 2
    assert indexed["summary"]["chunks_indexed"] >= 2

    queried = context_search_query_tool(
        repo=str(repo),
        query="/apply/audit/pageEs",
        context_lines=0,
        full_file=False,
        final_top_k=1,
    )
    assert queried["ok"] is True
    assert queried["query"] == "/apply/audit/pageEs"
    assert len(queried["results"]) == 1
    assert queried["results"][0]["file_path"] == "ApplyAuditController.java"
    assert "content" in queried["results"][0]
    assert queried["summary"]["entry_points"]

    traced = context_search_trace_tool(
        repo=str(repo),
        query="/apply/audit/pageEs",
        context_lines=0,
        full_file=False,
        final_top_k=1,
    )
    assert traced["ok"] is True
    assert tuple(traced) == ("ok", "repo", "query", "trace")
    assert traced["trace"]["schema_version"] == 1
    assert traced["trace"]["source_counts"]
    assert "results" not in traced

    context = context_search_context_tool(
        repo=str(repo),
        query="/apply/audit/pageEs",
        context_lines=0,
        full_file=False,
        final_top_k=1,
    )
    assert context["ok"] is True
    assert context["repo"] == str(repo)
    assert set(context) == {"ok", "repo", "query", "retrieval", "context_pack"}
    assert context["context_pack"]["schema_version"] == 2
    assert context["retrieval"]["result_count"] == len(queried["results"])
    assert context["retrieval"]["evidence_anchor_count"] == len(
        queried["evidence_anchors"]
    )
    assert context["context_pack"]["budget"]["max_items"] == 2

    stats = context_search_stats_tool(str(repo))
    assert stats["ok"] is True
    assert stats["stats"]["total_files"] == 2
    assert stats["embedding"]["provider"] == "hash"

    explained = context_search_explain_tool(str(repo), "ApplyAuditController.java:4")
    assert explained["ok"] is True
    assert explained["chunk"]["file_path"] == "ApplyAuditController.java"
    assert explained["chunk"]["start_line"] <= 4 <= explained["chunk"]["end_line"]


def test_mcp_trace_returns_shared_schema_without_source_content(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    _write_java_repo(repo)
    assert context_search_index_tool(str(repo))["ok"] is True

    payload = context_search_trace_tool(
        repo=str(repo),
        query="/apply/audit/pageEs",
        context_lines=0,
        full_file=False,
        final_top_k=1,
    )

    assert tuple(payload) == ("ok", "repo", "query", "trace")
    assert payload["ok"] is True
    assert payload["trace"]["schema_version"] == 1
    assert payload["trace"]["final_selection_count"] >= 1
    assert "content" not in json.dumps(payload["trace"])


def test_mcp_trace_executes_one_retrieval_pass(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    _write_java_repo(repo)
    assert context_search_index_tool(str(repo))["ok"] is True
    calls = 0
    original = mcp_tools.trace_repository

    def counted(*args, **kwargs):
        nonlocal calls
        calls += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(mcp_tools, "trace_repository", counted)
    result = context_search_trace_tool(
        repo=str(repo),
        query="audit",
    )

    assert result["ok"] is True
    assert calls == 1


@pytest.mark.parametrize(
    "error",
    [
        RetrievalTraceError("PRIVATE_TRACE_CONTRACT"),
        RuntimeError("PRIVATE_TRACE_INTERNAL"),
    ],
)
def test_mcp_trace_hides_trace_and_unexpected_internal_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
) -> None:
    repo = tmp_path / "repo"
    _write_index_marker(repo)

    def fail(*args, **kwargs):
        raise error

    monkeypatch.setattr(mcp_tools, "trace_repository", fail)
    payload = context_search_trace_tool(repo=str(repo), query="audit")

    assert payload == {
        "ok": False,
        "error": {
            "code": "trace_failed",
            "message": "Retrieval trace failed",
        },
    }
    assert "PRIVATE_TRACE" not in repr(payload)


def test_cli_and_mcp_trace_success_envelopes_are_identical(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    _write_index_marker(repo)
    ticks = iter((0, 1_000_000))
    collector = RetrievalTraceCollector(clock_ns=lambda: next(ticks))
    collector.record_query(
        TraceQuery(
            original_token_count=1,
            expanded_token_count=1,
            variant_retrieval_status="original_only",
        )
    )
    trace = collector.finish(
        outcome="empty",
        termination_reason="no_candidates",
        final_selections=(),
    )
    traced = TracedQueryBundle(
        bundle=_deterministic_bundle(query="audit"),
        trace=trace,
    )
    monkeypatch.setattr(cli, "trace_repository", lambda *args, **kwargs: traced)
    monkeypatch.setattr(
        mcp_tools,
        "trace_repository",
        lambda *args, **kwargs: traced,
    )
    monkeypatch.setattr(cli, "_warn_if_signal_schema_stale", lambda repo: None)

    cli_result = CliRunner().invoke(
        app,
        ["trace", str(repo), "audit", "--json"],
    )
    mcp_result = context_search_trace_tool(repo=str(repo), query="audit")

    assert cli_result.exit_code == 0
    assert json.loads(cli_result.output) == mcp_result


def test_mcp_query_missing_index_does_not_create_artifacts(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    result = context_search_query_tool(str(repo), "anything")

    assert result == {
        "ok": False,
        "error": {
            "code": "missing_index",
            "message": f"Missing index for {repo}. Run context_search_index first.",
        },
    }
    assert not (repo / ".context-search").exists()


def test_mcp_trace_missing_index_does_not_create_artifacts(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    result = context_search_trace_tool(str(repo), "anything")

    assert result == {
        "ok": False,
        "error": {
            "code": "missing_index",
            "message": f"Missing index for {repo}. Run context_search_index first.",
        },
    }
    assert not (repo / ".context-search").exists()


def test_mcp_query_rejects_invalid_final_top_k(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write_java_repo(repo)
    context_search_index_tool(str(repo))

    result = context_search_query_tool(str(repo), "audit", final_top_k=0)

    assert result == {
        "ok": False,
        "error": {
            "code": "query_failed",
            "message": "final_top_k must be greater than zero",
        },
    }


def test_mcp_trace_rejects_invalid_final_top_k(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write_java_repo(repo)
    context_search_index_tool(str(repo))

    result = context_search_trace_tool(str(repo), "audit", final_top_k=0)

    assert result == {
        "ok": False,
        "error": {
            "code": "query_failed",
            "message": "final_top_k must be greater than zero",
        },
    }


def test_mcp_query_returns_structured_error_when_error_feedback_logging_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo = tmp_path / "repo"
    _write_java_repo(repo)
    context_search_index_tool(str(repo))

    def fail_feedback(*args, **kwargs) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(mcp_tools, "_append_query_feedback", fail_feedback)

    result = context_search_query_tool(str(repo), "audit", final_top_k=0)

    assert result == {
        "ok": False,
        "error": {
            "code": "query_failed",
            "message": "final_top_k must be greater than zero",
        },
    }


def test_mcp_explain_rejects_invalid_location(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write_java_repo(repo)
    context_search_index_tool(str(repo))

    result = context_search_explain_tool(str(repo), "ApplyAuditController.java")

    assert result == {
        "ok": False,
        "error": {
            "code": "invalid_location",
            "message": "location must be file:line",
        },
    }


def test_mcp_explain_reports_missing_chunk(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write_java_repo(repo)
    context_search_index_tool(str(repo))

    result = context_search_explain_tool(str(repo), "Missing.java:99")

    assert result == {
        "ok": False,
        "error": {
            "code": "chunk_not_found",
            "message": "No indexed chunk covers Missing.java:99.",
        },
    }


def test_mcp_explain_rejects_absolute_path_outside_repo(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    other = tmp_path / "other"
    _write_java_repo(repo)
    other.mkdir()
    outside_file = other / "Outside.java"
    outside_file.write_text("class Outside {}\n", encoding="utf-8")
    context_search_index_tool(str(repo))

    result = context_search_explain_tool(str(repo), f"{outside_file}:1")

    assert result == {
        "ok": False,
        "error": {
            "code": "invalid_location",
            "message": "absolute path must be inside repo",
        },
    }


def test_mcp_query_writes_feedback_without_source_content(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write_java_repo(repo)
    context_search_index_tool(str(repo))

    result = context_search_query_tool(str(repo), "/apply/audit/pageEs")

    assert result["ok"] is True
    log_path = repo / ".context-search" / "mcp_calls.jsonl"
    events = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    assert len(events) == 1
    event = events[0]
    assert event["tool"] == "context_search_query"
    assert event["ok"] is True
    assert event["query"] == "/apply/audit/pageEs"
    assert event["result_count"] >= 1
    assert event["embedding"]["provider"] == "hash"
    assert "ApplyAuditController" not in json.dumps(event)
    assert "class ApplyAuditController" not in json.dumps(event)


def test_mcp_trace_never_creates_or_modifies_feedback_log(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write_java_repo(repo)
    context_search_index_tool(str(repo))
    log_path = repo / ".context-search" / "mcp_calls.jsonl"
    log_path.write_text("PREEXISTING_FEEDBACK\n", encoding="utf-8")

    result = context_search_trace_tool(str(repo), "TRACE_QUERY_SECRET")

    assert result["ok"] is True
    assert log_path.read_text(encoding="utf-8") == "PREEXISTING_FEEDBACK\n"


def test_mcp_query_payload_includes_planner_status(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write_java_repo(repo)
    context_search_index_tool(str(repo))

    result = context_search_query_tool(str(repo), "/apply/audit/pageEs")

    assert result["ok"] is True
    assert result["planner"]["status"] == "disabled"
    assert result["planner"]["enabled"] is False


def test_mcp_query_payload_keeps_rerank_diagnostics_numeric(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write_java_repo(repo)
    context_search_index_tool(str(repo))

    payload = context_search_query_tool(str(repo), "/apply/audit/pageEs", final_top_k=1)

    assert payload["ok"] is True
    parts = payload["results"][0]["score_parts"]
    assert isinstance(parts["rerank_score"], float)
    assert isinstance(parts["evidence_priority"], float)
    assert "evidence_class" not in parts


def test_mcp_query_payload_includes_evidence_anchors() -> None:
    bundle = QueryBundle(
        query="audit timeout",
        expanded_tokens=["audit", "timeout"],
        followup_keywords=[],
        results=[
            RetrievalResult(
                file_path=Path("ApplyAuditController.java"),
                start_line=10,
                end_line=20,
                content="class ApplyAuditController {}",
                score=0.87,
                score_parts={"lexical": 0.8},
                reasons=["lexical match: audit timeout"],
                followup_keywords=["pageEs"],
            )
        ],
        evidence_anchors=[
            EvidenceAnchor(
                file_path=Path("config/audit.yaml"),
                start_line=1,
                end_line=4,
                content="timeout: 30",
                score=0.42,
                score_parts={"lexical": 0.2},
                reasons=["config signal"],
                anchor_kind="config",
            )
        ],
    )

    payload = mcp_tools._query_payload(bundle)

    assert "evidence_anchors" in payload
    assert payload["evidence_anchors"][0]["file_path"] == "config/audit.yaml"
    assert payload["evidence_anchors"][0]["anchor_kind"] == "config"
    assert payload["evidence_anchors"][0]["score_parts"]["lexical"] == 0.2
    assert isinstance(payload["evidence_anchors"][0]["score_parts"]["lexical"], (int, float))


def test_mcp_query_payload_exposes_variant_and_anchor_provenance() -> None:
    bundle = QueryBundle(
        query="query",
        expanded_tokens=["query"],
        results=[
            RetrievalResult(
                file_path=Path("App.java"),
                start_line=1,
                end_line=2,
                content="class App {}",
                score=0.8,
                score_parts={"planner_semantic": 0.8},
                reasons=["planner semantic match"],
                followup_keywords=[],
                semantic_matches=[SemanticMatch("planner:0", 0.8)],
            )
        ],
        followup_keywords=[],
        evidence_anchors=[
            EvidenceAnchor(
                file_path=Path("README.md"),
                start_line=1,
                end_line=2,
                content="App docs",
                score=0.4,
                score_parts={"planner_semantic": 0.4},
                reasons=["planner semantic match"],
                anchor_kind="document",
                semantic_matches=[SemanticMatch("planner:0", 0.4)],
            )
        ],
        query_variants=[
            QueryVariant("original", "query", "original"),
            QueryVariant("planner:0", "application entrypoint", "planner"),
        ],
        variant_retrieval_status="hybrid",
    )

    payload = mcp_tools._query_payload(bundle)

    assert payload["variant_retrieval_status"] == "hybrid"
    assert payload["query_variants"][1]["variant_id"] == "planner:0"
    assert payload["results"][0]["semantic_matches"] == [
        {"variant_id": "planner:0", "score": 0.8}
    ]
    assert payload["evidence_anchors"][0]["semantic_matches"] == [
        {"variant_id": "planner:0", "score": 0.4}
    ]


def test_mcp_query_payload_includes_repo_profile_planner_diagnostics() -> None:
    bundle = QueryBundle(
        query="cookies",
        expanded_tokens=["cookies"],
        followup_keywords=[],
        results=[],
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

    payload = mcp_tools._query_payload(bundle)

    assert payload["planner"]["repo_profile_hash"] == "sha256:test"
    assert payload["planner"]["repo_profile_truncated"] is True
    assert payload["planner"]["discarded_hint_count"] == 1
    assert payload["planner"]["discarded_hints"] == ["RestTemplate"]


def test_mcp_query_feedback_keeps_repo_profile_planner_metadata_bounded() -> None:
    payload = {
        "planner": {
            "status": "ok",
            "repo_profile_hash": "sha256:test",
            "repo_profile_truncated": True,
            "discarded_hint_count": 3,
            "discarded_hints": ["RestTemplate", "HttpSession", "RestController"],
        }
    }

    planner = mcp_tools._feedback_planner_payload(payload)

    assert planner["repo_profile_hash"] == "sha256:test"
    assert planner["repo_profile_truncated"] is True
    assert planner["discarded_hint_count"] == 3
    assert "discarded_hints" not in planner


def test_mcp_query_feedback_includes_planner_metadata_without_prompt_text(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    _write_java_repo(repo)
    context_search_index_tool(str(repo))

    result = context_search_query_tool(str(repo), "/apply/audit/pageEs")

    assert result["ok"] is True
    log_path = repo / ".context-search" / "mcp_calls.jsonl"
    events = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    event = events[0]
    planner = event["planner"]
    assert planner["status"] == "disabled"
    assert "prompt_version" in planner
    assert "prompt_hash" in planner
    assert "rewritten_queries" not in planner
    assert "grep_keywords" not in planner
    assert "symbol_hints" not in planner
    assert "ApplyAuditController" not in json.dumps(event)


def test_mcp_feedback_hashes_variants_without_storing_rewrite_text(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".context-search").mkdir()
    private_rewrite = "private planner rewrite"
    rewritten_query_sentinel = "private rewritten query sentinel"
    grep_keyword_sentinel = "private grep keyword sentinel"
    symbol_hint_sentinel = "PrivatePlannerSymbolHintSentinel"
    payload = {
        "ok": True,
        "results": [],
        "summary": {},
        "followup_keywords": [],
        "planner": {
            "status": "ok",
            "rewritten_queries": [rewritten_query_sentinel],
            "grep_keywords": [grep_keyword_sentinel],
            "symbol_hints": [symbol_hint_sentinel],
        },
        "variant_retrieval_status": "hybrid",
        "query_variants": [
            {
                "variant_id": "original",
                "source": "original",
                "text": "original secret query",
            },
            {
                "variant_id": "planner:0",
                "source": "planner",
                "text": private_rewrite,
            },
        ],
    }

    mcp_tools._append_query_feedback(
        repo,
        query="original secret query",
        payload=payload,
        context_lines=None,
        full_file=False,
        final_top_k=None,
    )
    event = json.loads(
        (repo / ".context-search" / "mcp_calls.jsonl").read_text(
            encoding="utf-8"
        )
    )
    serialized = json.dumps(event)
    expected_hash = hashlib.sha256(private_rewrite.encode("utf-8")).hexdigest()[:12]

    assert event["query"] == "original secret query"
    assert event["variant_retrieval"]["status"] == "hybrid"
    assert event["variant_retrieval"]["count"] == 2
    assert event["variant_retrieval"]["variants"][1] == {
        "variant_id": "planner:0",
        "source": "planner",
        "position": 1,
        "text_hash": expected_hash,
    }
    for field in ("rewritten_queries", "grep_keywords", "symbol_hints"):
        assert field not in event["planner"]
    for sensitive_text in (
        private_rewrite,
        rewritten_query_sentinel,
        grep_keyword_sentinel,
        symbol_hint_sentinel,
    ):
        assert sensitive_text not in serialized


def test_feedback_variant_payload_defaults_for_error_payload() -> None:
    payload = {
        "ok": False,
        "error": {"code": "query_failed"},
    }

    assert mcp_tools._feedback_variant_payload(payload) == {
        "status": "original_only",
        "count": 0,
        "variants": [],
    }


def test_feedback_variant_payload_preserves_allowed_statuses() -> None:
    for status in ("original_only", "hybrid", "embedding_fallback"):
        payload = {"variant_retrieval_status": status}

        assert mcp_tools._feedback_variant_payload(payload)["status"] == status


def test_mcp_feedback_fails_closed_on_malformed_variant_metadata(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".context-search").mkdir()
    status_sentinel = "private status sentinel"
    variant_id_sentinel = "private variant id sentinel"
    source_sentinel = "private source sentinel"
    payload = {
        "ok": True,
        "results": [],
        "summary": {},
        "followup_keywords": [],
        "planner": {"status": "ok"},
        "variant_retrieval_status": f"hybrid:{status_sentinel}",
        "query_variants": [
            {
                "variant_id": {"rewrite": variant_id_sentinel},
                "source": "planner",
                "text": "ignored",
            },
            {
                "variant_id": "planner:0",
                "source": {"rewrite": source_sentinel},
                "text": "ignored",
            },
            {
                "variant_id": "planner:01",
                "source": "planner",
                "text": "ignored",
            },
            {
                "variant_id": "original",
                "source": "planner",
                "text": "ignored",
            },
        ],
    }

    mcp_tools._append_query_feedback(
        repo,
        query="safe original query",
        payload=payload,
        context_lines=None,
        full_file=False,
        final_top_k=None,
    )
    event = json.loads(
        (repo / ".context-search" / "mcp_calls.jsonl").read_text(
            encoding="utf-8"
        )
    )
    serialized = json.dumps(event)

    assert event["variant_retrieval"] == {
        "status": "original_only",
        "count": 0,
        "variants": [],
    }
    for sensitive_text in (
        status_sentinel,
        variant_id_sentinel,
        source_sentinel,
    ):
        assert sensitive_text not in serialized


def test_mcp_query_feedback_includes_embedding_config_hash(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write_java_repo(repo)
    context_search_index_tool(str(repo))

    result = context_search_query_tool(str(repo), "/apply/audit/pageEs")

    assert result["ok"] is True
    log_path = repo / ".context-search" / "mcp_calls.jsonl"
    events = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    assert len(events) == 1
    event = events[0]
    assert isinstance(event["embedding"]["config_hash"], str)
    assert event["embedding"]["config_hash"]


def test_mcp_query_returns_results_when_feedback_logging_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo = tmp_path / "repo"
    _write_java_repo(repo)
    context_search_index_tool(str(repo))

    def fail_feedback(*args, **kwargs) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(mcp_tools, "_append_query_feedback", fail_feedback)

    result = context_search_query_tool(str(repo), "/apply/audit/pageEs")

    assert result["ok"] is True
    assert result["results"]
    assert result["results"][0]["file_path"] == "ApplyAuditController.java"


def test_mcp_query_rotates_large_feedback_log(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo = tmp_path / "repo"
    _write_java_repo(repo)
    context_search_index_tool(str(repo))
    log_path = repo / ".context-search" / "mcp_calls.jsonl"
    log_path.write_text("oversized\n", encoding="utf-8")
    monkeypatch.setattr(mcp_tools, "_FEEDBACK_LOG_MAX_BYTES", 1)

    result = context_search_query_tool(str(repo), "/apply/audit/pageEs")

    assert result["ok"] is True
    rotated = sorted(log_path.parent.glob("mcp_calls.*.jsonl"))
    assert len(rotated) == 1
    assert rotated[0].read_text(encoding="utf-8") == "oversized\n"
    assert len(log_path.read_text(encoding="utf-8").splitlines()) == 1


def test_mcp_query_payload_keeps_direct_text_diagnostics_numeric(tmp_path: Path) -> None:
    """Verify direct text diagnostics remain numeric in MCP payload."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "test.py").write_text("# 测试\ndef test(): pass\n", encoding="utf-8")

    context_search_index_tool(str(repo))
    result = context_search_query_tool(str(repo), "测试")

    # Direct text diagnostics should be numeric
    if "direct_text" in result.get("diagnostics", {}):
        assert isinstance(result["diagnostics"]["direct_text"], (int, float))
    if "direct_text_hits" in result.get("diagnostics", {}):
        assert isinstance(result["diagnostics"]["direct_text_hits"], (int, float))
    if "anchored_relation" in result.get("diagnostics", {}):
        assert isinstance(result["diagnostics"]["anchored_relation"], (int, float))


def test_mcp_context_matches_shared_bounded_envelope(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    _write_index_marker(repo)
    bundle = _deterministic_bundle()
    monkeypatch.setattr(mcp_tools, "query_repository", lambda *args, **kwargs: bundle)

    payload = context_search_context_tool(
        str(repo),
        "audit endpoint",
        context_lines=3,
        final_top_k=1,
    )

    config = mcp_tools._load_query_config(repo, 1)
    options = resolve_context_pack_options(
        config,
        context_lines=3,
        max_evidence_anchors=evidence_anchor_top_k(config.retrieval.final_top_k),
    )
    expected = formatters.context_payload(
        repo,
        bundle,
        build_context_pack(bundle, options),
    )
    assert payload == expected
    json.dumps(payload, allow_nan=False)


def test_mcp_context_queries_builds_and_envelopes_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    _write_index_marker(repo)
    bundle = _deterministic_bundle()
    calls = {"query": 0, "build": 0, "envelope": 0}

    def query_once(*args: object, **kwargs: object) -> QueryBundle:
        calls["query"] += 1
        return bundle

    def build_once(*args: object, **kwargs: object):
        calls["build"] += 1
        return build_context_pack(*args, **kwargs)

    def envelope_once(*args: object, **kwargs: object) -> dict[str, object]:
        calls["envelope"] += 1
        return formatters.context_payload(*args, **kwargs)

    monkeypatch.setattr(mcp_tools, "query_repository", query_once)
    monkeypatch.setattr(mcp_tools, "build_context_pack", build_once)
    monkeypatch.setattr(mcp_tools, "context_payload", envelope_once)

    payload = context_search_context_tool(
        str(repo),
        "audit endpoint",
        final_top_k=1,
    )

    assert payload["ok"] is True
    assert calls == {"query": 1, "build": 1, "envelope": 1}


def test_mcp_context_v2_is_the_exact_shared_bounded_envelope(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    _write_index_marker(repo)
    bundle = _deterministic_bundle()
    monkeypatch.setattr(mcp_tools, "query_repository", lambda *args, **kwargs: bundle)

    payload = context_search_context_tool(
        str(repo),
        bundle.query,
        context_lines=3,
        final_top_k=1,
        max_items=1,
        max_context_bytes=4096,
    )
    config = mcp_tools._load_query_config(repo, 1)
    options = context_pack_v2_builder.resolve_context_pack_options(
        config,
        context_lines=3,
        max_evidence_anchors=evidence_anchor_top_k(1),
        max_items=1,
        max_pack_bytes=4096,
    )
    expected_pack = context_pack_v2_builder.build_context_pack(bundle, options)
    expected = formatters.context_payload(repo, bundle, expected_pack)

    assert payload == expected
    assert payload["context_pack"] == context_pack_v2_serialization.context_pack_payload(
        expected_pack
    )
    assert set(payload) == {"ok", "repo", "query", "retrieval", "context_pack"}
    assert set(payload).isdisjoint(
        {
            "results",
            "evidence_anchors",
            "summary",
            "query_variants",
            "expanded_tokens",
            "followup_keywords",
            "planner",
            "index",
        }
    )
    assert json.loads(formatters.format_context_json(expected))["context_pack"] == payload[
        "context_pack"
    ]


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"max_items": 0}, "max_items must be a positive integer"),
        (
            {"max_context_bytes": 4095},
            "max_context_bytes must be an integer of at least 4096 bytes",
        ),
    ],
)
def test_mcp_context_rejects_limits_before_retrieval_or_build(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    kwargs: dict[str, int],
    message: str,
) -> None:
    repo = tmp_path / "repo"
    _write_index_marker(repo)
    counts = {"query": 0, "build": 0}

    def counted_query(*args: object, **call_kwargs: object) -> QueryBundle:
        counts["query"] += 1
        return _deterministic_bundle()

    def counted_build(*args: object, **call_kwargs: object):
        counts["build"] += 1
        raise AssertionError("invalid options must not reach the builder")

    monkeypatch.setattr(mcp_tools, "query_repository", counted_query)
    monkeypatch.setattr(mcp_tools, "build_context_pack", counted_build)

    payload = context_search_context_tool(str(repo), "audit", **kwargs)

    assert payload == {
        "ok": False,
        "error": {"code": "invalid_context_options", "message": message},
    }
    assert counts == {"query": 0, "build": 0}


def test_mcp_context_rejects_persisted_limits_before_retrieval_or_build(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    _write_index_marker(repo)
    (repo / ".context-search" / "config.toml").write_text(
        render_config(ToolConfig(context=ContextConfig(max_items=0))),
        encoding="utf-8",
    )
    counts = {"query": 0, "build": 0}

    def counted_query(*args: object, **kwargs: object) -> QueryBundle:
        counts["query"] += 1
        return _deterministic_bundle()

    def counted_build(*args: object, **kwargs: object):
        counts["build"] += 1
        raise AssertionError("invalid options must not reach the builder")

    monkeypatch.setattr(mcp_tools, "query_repository", counted_query)
    monkeypatch.setattr(mcp_tools, "build_context_pack", counted_build)

    payload = context_search_context_tool(str(repo), "audit")

    assert payload == {
        "ok": False,
        "error": {
            "code": "invalid_context_options",
            "message": "context.max_items must be a positive integer",
        },
    }
    assert counts == {"query": 0, "build": 0}


def test_cli_and_mcp_context_pack_values_are_identical(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    _write_index_marker(repo)
    bundle = _deterministic_bundle()
    monkeypatch.setattr(cli, "query_repository", lambda *args, **kwargs: bundle)
    monkeypatch.setattr(mcp_tools, "query_repository", lambda *args, **kwargs: bundle)
    monkeypatch.setattr(cli, "_warn_if_signal_schema_stale", lambda repo: None)

    cli_result = CliRunner().invoke(
        app,
        [
            "context",
            str(repo),
            bundle.query,
            "--json",
            "--max-items",
            "1",
            "--max-context-bytes",
            "4096",
        ],
    )
    mcp_payload = context_search_context_tool(
        str(repo),
        bundle.query,
        max_items=1,
        max_context_bytes=4096,
    )

    assert cli_result.exit_code == 0
    cli_payload = json.loads(cli_result.output)
    assert mcp_payload["ok"] is True
    assert cli_payload["context_pack"] == mcp_payload["context_pack"]


def test_mcp_context_empty_bundle_is_success_and_feedback_is_bounded(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    _write_index_marker(repo)
    bundle_query = "EMPTY_BUNDLE_QUERY_SENTINEL"
    bundle = QueryBundle(
        query=bundle_query,
        expanded_tokens=[],
        results=[],
        followup_keywords=[],
    )
    monkeypatch.setattr(mcp_tools, "query_repository", lambda *args, **kwargs: bundle)

    payload = context_search_context_tool(str(repo), "public empty query")

    assert payload["ok"] is True
    assert "error" not in payload
    pack = payload["context_pack"]
    assert pack["status"] == "empty"
    assert pack["missing_evidence"] == []
    assert pack["next_queries"] == []

    log_path = repo / ".context-search" / "mcp_calls.jsonl"
    event = json.loads(log_path.read_text(encoding="utf-8"))
    assert event["tool"] == "context_search_context"
    assert event["query"] == "public empty query"
    assert event["context_pack"] == {
        "schema_version": 2,
        "status": "empty",
        "confidence": "none",
        "group_counts": {group: 0 for group in CONTEXT_GROUPS},
        "need_count": 0,
        "required_need_count": 0,
        "selected_item_count": 0,
        "excerpt_count": 0,
        "truncated_item_count": 0,
        "omitted_item_count": 0,
        "required_missing_categories": [],
        "recommended_missing_categories": [],
        "budget": {
            key: pack["budget"][key]
            for key in (
                "max_items",
                "max_pack_bytes",
                "content_bytes",
                "pack_bytes",
            )
        },
        "next_query_count": 0,
    }
    serialized_metadata = json.dumps(event["context_pack"])
    assert bundle_query not in serialized_metadata
    assert "file_path" not in serialized_metadata
    assert "result:0" not in serialized_metadata


def test_mcp_context_rejects_invalid_final_top_k(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write_index_marker(repo)

    payload = context_search_context_tool(
        str(repo),
        "query",
        final_top_k=0,
    )

    assert payload == {
        "ok": False,
        "error": {
            "code": "query_failed",
            "message": "final_top_k must be greater than zero",
        },
    }


def test_mcp_context_matches_query_repo_and_index_errors(tmp_path: Path) -> None:
    missing_repo = tmp_path / "missing"
    assert context_search_context_tool(
        str(missing_repo), "query"
    ) == context_search_query_tool(str(missing_repo), "query")

    repo = tmp_path / "repo"
    repo.mkdir()
    assert context_search_context_tool(
        str(repo), "query"
    ) == context_search_query_tool(str(repo), "query")


@pytest.mark.parametrize(
    "exception",
    [
        ContextPackError("context_failed", "Context pack construction failed"),
        ValueError("private detail"),
        RuntimeError("private detail"),
    ],
)
def test_mcp_context_contains_pack_phase_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    exception: Exception,
) -> None:
    repo = tmp_path / "repo"
    _write_index_marker(repo)
    bundle = _deterministic_bundle(result_content="PRIVATE_RAW_CONTENT_SENTINEL")

    def fail_pack(*args: object, **kwargs: object):
        raise exception

    monkeypatch.setattr(mcp_tools, "query_repository", lambda *args, **kwargs: bundle)
    monkeypatch.setattr(mcp_tools, "build_context_pack", fail_pack)

    payload = context_search_context_tool(str(repo), "audit")

    assert payload == {
        "ok": False,
        "error": {
            "code": "context_failed",
            "message": "Context pack construction failed",
        },
    }
    assert set(payload) == {"ok", "error"}
    assert set(mcp_tools._query_payload(bundle)).isdisjoint(payload)
    serialized = json.dumps(payload)
    assert "PRIVATE_RAW_CONTENT_SENTINEL" not in serialized
    assert "private detail" not in serialized


def test_mcp_context_does_not_catch_keyboard_interrupt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    _write_index_marker(repo)
    bundle = _deterministic_bundle()

    def interrupt(*args: object, **kwargs: object):
        raise KeyboardInterrupt

    monkeypatch.setattr(mcp_tools, "query_repository", lambda *args, **kwargs: bundle)
    monkeypatch.setattr(mcp_tools, "build_context_pack", interrupt)

    with pytest.raises(KeyboardInterrupt):
        context_search_context_tool(str(repo), "audit")


def test_mcp_context_feedback_failure_is_non_fatal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    _write_index_marker(repo)
    bundle = _deterministic_bundle()
    monkeypatch.setattr(mcp_tools, "query_repository", lambda *args, **kwargs: bundle)

    def fail_feedback(*args: object, **kwargs: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(mcp_tools, "_append_query_feedback", fail_feedback)

    payload = context_search_context_tool(
        str(repo),
        "audit",
        final_top_k=1,
    )

    assert payload["ok"] is True
    assert payload["context_pack"]["schema_version"] == 2


def test_mcp_context_feedback_keeps_only_approved_bounded_metadata(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    _write_index_marker(repo)
    path_sentinel = "PRIVATE_CONTEXT_PATH_SENTINEL"
    content_sentinel = "PRIVATE_CONTEXT_CONTENT_SENTINEL"
    subject_sentinel = "PrivateSubjectSentinel"
    bundle = _deterministic_bundle(
        query=f"{subject_sentinel} endpoint",
        result_path=f"src/{path_sentinel}.java",
        result_content=(
            f'class {subject_sentinel} {{ String value = "{content_sentinel}"; }}'
        ),
    )
    config = mcp_tools._load_query_config(repo, 1)
    options = resolve_context_pack_options(
        config,
        context_lines=None,
        max_evidence_anchors=evidence_anchor_top_k(1),
    )
    payload = formatters.context_payload(
        repo,
        bundle,
        build_context_pack(bundle, options),
    )
    pack = payload["context_pack"]

    need_id_sentinel = pack["evidence_needs"][0]["id"]
    next_query_sentinel = pack["next_queries"][0]["query"]
    sentinels = {
        "path": path_sentinel,
        "content": content_sentinel,
        "subject": subject_sentinel,
        "need_id": need_id_sentinel,
        "next_query": next_query_sentinel,
        "planner": "PRIVATE_PLANNER_REWRITE_SENTINEL",
        "discarded": "PRIVATE_DISCARDED_HINT_SENTINEL",
        "summary": "PRIVATE_SUMMARY_SENTINEL",
    }
    serialized_pack = json.dumps(pack)
    assert path_sentinel in serialized_pack
    assert content_sentinel in serialized_pack
    assert subject_sentinel in serialized_pack
    assert need_id_sentinel in serialized_pack
    assert next_query_sentinel in serialized_pack
    payload.update(
        {
            "planner": {
                "rewritten_queries": [sentinels["planner"]],
                "discarded_hints": [sentinels["discarded"]],
            },
            "summary": {"entry_points": [sentinels["summary"]]},
            "results": [{"score": 987654321.125}],
        }
    )
    serialized_input = json.dumps(payload)
    assert all(sentinel in serialized_input for sentinel in sentinels.values())

    mcp_tools._append_query_feedback(
        repo,
        query="public privacy query",
        payload=payload,
        context_lines=None,
        full_file=False,
        final_top_k=1,
        tool="context_search_context",
    )

    event = json.loads(
        (repo / ".context-search" / "mcp_calls.jsonl").read_text(
            encoding="utf-8"
        )
    )
    assert set(event) == {
        "timestamp",
        "tool",
        "ok",
        "repo_hash",
        "query",
        "context_lines",
        "full_file",
        "final_top_k",
        "error_code",
        "context_pack",
    }
    assert event["context_pack"] == {
        "schema_version": 2,
        "status": pack["status"],
        "confidence": pack["confidence"]["level"],
        "group_counts": {
            group: len(pack["groups"][group]) for group in CONTEXT_GROUPS
        },
        "need_count": len(pack["evidence_needs"]),
        "required_need_count": sum(
            need["required"] for need in pack["evidence_needs"]
        ),
        "selected_item_count": len(pack["items"]),
        "excerpt_count": sum(
            len(item["excerpts"]) for item in pack["items"]
        ),
        "truncated_item_count": pack["budget"]["truncated_item_count"],
        "omitted_item_count": pack["budget"]["omitted_item_count"],
        "required_missing_categories": [
            category
            for category in CONTEXT_GROUPS
            if any(
                missing["category"] == category and missing["required"]
                for missing in pack["missing_evidence"]
            )
        ],
        "recommended_missing_categories": [
            category
            for category in CONTEXT_GROUPS
            if any(
                missing["category"] == category and not missing["required"]
                for missing in pack["missing_evidence"]
            )
            and not any(
                missing["category"] == category and missing["required"]
                for missing in pack["missing_evidence"]
            )
        ],
        "budget": {
            key: pack["budget"][key]
            for key in (
                "max_items",
                "max_pack_bytes",
                "content_bytes",
                "pack_bytes",
            )
        },
        "next_query_count": len(pack["next_queries"]),
    }
    serialized = json.dumps(event)
    for sentinel in sentinels.values():
        assert sentinel not in serialized
    assert "987654321.125" not in serialized


def test_mcp_context_unexpected_failure_feedback_has_no_partial_pack(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    _write_index_marker(repo)
    raw_sentinel = "PRIVATE_PARTIAL_RAW_SENTINEL"
    private_exception = "PRIVATE_PACK_EXCEPTION_SENTINEL"
    bundle = _deterministic_bundle(result_content=raw_sentinel)

    def fail_pack(*args: object, **kwargs: object):
        raise RuntimeError(private_exception)

    monkeypatch.setattr(mcp_tools, "query_repository", lambda *args, **kwargs: bundle)
    monkeypatch.setattr(mcp_tools, "build_context_pack", fail_pack)

    payload = context_search_context_tool(str(repo), "public query")

    assert payload == {
        "ok": False,
        "error": {
            "code": "context_failed",
            "message": "Context pack construction failed",
        },
    }
    log_path = repo / ".context-search" / "mcp_calls.jsonl"
    event = json.loads(log_path.read_text(encoding="utf-8"))
    assert event["tool"] == "context_search_context"
    assert event["error_code"] == "context_failed"
    assert "context_pack" not in event
    assert "result_count" not in event
    assert "planner" not in event
    assert "summary_counts" not in event
    serialized = json.dumps(event)
    assert private_exception not in serialized
    assert raw_sentinel not in serialized


def test_mcp_context_feedback_fails_closed_on_malformed_pack_metadata(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    _write_index_marker(repo)
    private_sentinel = "PRIVATE_MALFORMED_CONTEXT_SENTINEL"
    payload = {
        "ok": True,
        "results": [],
        "summary": {},
        "followup_keywords": [],
        "context_pack": {
            "status": "partial",
            "confidence": {"level": "low", "detail": private_sentinel},
            "items": [{"id": private_sentinel}, {"path": private_sentinel}],
            "groups": {
                "entrypoints": [private_sentinel],
                "implementations": True,
                "related_types": {"private": private_sentinel},
                "tests": [private_sentinel, private_sentinel],
                "configs_docs": "private",
                "supporting": [],
                private_sentinel: [private_sentinel],
            },
            "missing_evidence": [
                {"category": "entrypoints", "required": True},
                {"category": "results", "required": True},
                {"category": "entrypoints", "required": True},
                {"category": "supporting", "required": False},
                {"category": "results", "required": False},
                {"category": "tests", "required": 1},
                {"category": private_sentinel, "required": True},
            ],
            "next_queries": [{"query": private_sentinel}],
            "budget": {
                "max_results": 2,
                "max_evidence_anchors": True,
                "max_items": -1,
                "included_results": 1,
                "included_evidence_anchors": 1.5,
                "content_bytes": 4,
                private_sentinel: {"private": private_sentinel},
            },
        },
    }

    mcp_tools._append_query_feedback(
        repo,
        query="safe original query",
        payload=payload,
        context_lines=None,
        full_file=False,
        final_top_k=None,
        tool="context_search_context",
    )

    log_path = repo / ".context-search" / "mcp_calls.jsonl"
    event = json.loads(log_path.read_text(encoding="utf-8"))
    assert "context_pack" not in event
    assert private_sentinel not in json.dumps(event)


def _canonical_empty_context_payload() -> dict[str, object]:
    bundle = QueryBundle(
        query="public empty query",
        expanded_tokens=[],
        results=[],
        followup_keywords=[],
    )
    options = resolve_context_pack_options(
        ToolConfig(),
        context_lines=None,
        max_evidence_anchors=0,
    )
    return {
        "context_pack": context_pack_payload(
            build_context_pack(bundle, options)
        )
    }


def test_mcp_context_feedback_accepts_canonical_v2_pack() -> None:
    payload = _canonical_empty_context_payload()
    pack = payload["context_pack"]
    assert type(pack) is dict
    budget = pack["budget"]
    assert type(budget) is dict
    declared_pack_bytes = budget["pack_bytes"]
    assert type(declared_pack_bytes) is int
    assert declared_pack_bytes > 0
    assert declared_pack_bytes == len(
        context_pack_v2_serialization.canonical_context_pack_bytes(pack)
    )

    feedback = mcp_tools._feedback_context_pack_payload(payload)

    assert feedback is not None
    assert feedback["status"] == "empty"


def test_mcp_context_feedback_uses_total_omission_count_not_preview() -> None:
    base = _deterministic_bundle()
    results = [
        replace(
            base.results[0],
            file_path=Path(f"src/AuditController{index}.java"),
            content=f"class AuditController{index} {{}}",
        )
        for index in range(8)
    ]
    bundle = replace(base, results=results, evidence_anchors=[])
    options = resolve_context_pack_options(
        ToolConfig(),
        context_lines=None,
        max_evidence_anchors=0,
        max_items=1,
    )
    pack = context_pack_payload(build_context_pack(bundle, options))
    assert len(pack["items"]) == 1
    assert len(pack["omissions"]) == 1
    assert pack["budget"]["omitted_item_count"] == 7

    feedback = mcp_tools._feedback_context_pack_payload(
        {"context_pack": pack}
    )

    assert feedback is not None
    assert feedback["omitted_item_count"] == 7


@pytest.mark.parametrize(
    ("field", "forged_value"),
    [
        ("pack_bytes", 0),
        ("pack_bytes", 1),
        ("content_bytes", 7),
        ("max_pack_bytes", 0),
    ],
)
def test_mcp_context_feedback_rejects_forged_budget_metadata(
    tmp_path: Path,
    field: str,
    forged_value: int,
) -> None:
    repo = tmp_path / "repo"
    _write_index_marker(repo)
    payload = _canonical_empty_context_payload()
    pack = payload["context_pack"]
    assert type(pack) is dict
    budget = pack["budget"]
    assert type(budget) is dict
    budget[field] = forged_value

    mcp_tools._append_query_feedback(
        repo,
        query="safe original query",
        payload=payload,
        context_lines=None,
        full_file=False,
        final_top_k=None,
        tool="context_search_context",
    )

    event = json.loads(
        (repo / ".context-search" / "mcp_calls.jsonl").read_text(
            encoding="utf-8"
        )
    )
    assert "context_pack" not in event
