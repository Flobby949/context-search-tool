import hashlib
import json
from pathlib import Path

import pytest

import context_search_tool.mcp_tools as mcp_tools
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
)
from context_search_tool.models import (
    EvidenceAnchor,
    QueryPlan,
    QueryVariant,
    RetrievalResult,
    RetrievalSummary,
    SemanticMatch,
)
from context_search_tool.retrieval import QueryBundle, evidence_anchor_top_k


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
                end_line=20,
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
                end_line=4,
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

    context = context_search_context_tool(
        repo=str(repo),
        query="/apply/audit/pageEs",
        context_lines=0,
        full_file=False,
        final_top_k=1,
    )
    assert context["ok"] is True
    assert context["repo"] == str(repo)
    assert context["index"] == queried["index"]
    assert context["context_pack"]["schema_version"] == 1
    assert context["results"] == queried["results"]
    assert context["evidence_anchors"] == queried["evidence_anchors"]
    assert context["context_pack"]["budget"]["max_results"] == 1
    assert context["context_pack"]["budget"]["max_evidence_anchors"] == 1
    assert context["context_pack"]["budget"]["max_items"] == 2
    assert context["context_pack"]["budget"]["context_before_lines"] == 0
    assert context["context_pack"]["budget"]["context_after_lines"] == 0

    stats = context_search_stats_tool(str(repo))
    assert stats["ok"] is True
    assert stats["stats"]["total_files"] == 2
    assert stats["embedding"]["provider"] == "hash"

    explained = context_search_explain_tool(str(repo), "ApplyAuditController.java:4")
    assert explained["ok"] is True
    assert explained["chunk"]["file_path"] == "ApplyAuditController.java"
    assert explained["chunk"]["start_line"] <= 4 <= explained["chunk"]["end_line"]


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


def test_mcp_context_preserves_raw_payload_and_matches_shared_pack(
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

    raw_payload = mcp_tools._query_payload(bundle)
    for key, value in raw_payload.items():
        assert payload[key] == value
    config = mcp_tools._load_query_config(repo, 1)
    options = resolve_context_pack_options(
        config,
        context_lines=3,
        full_file=False,
        max_evidence_anchors=evidence_anchor_top_k(config.retrieval.final_top_k),
    )
    expected_pack = context_pack_payload(
        bundle,
        build_context_pack(bundle, options),
    )
    assert payload["context_pack"] == expected_pack
    assert payload["ok"] is True
    assert payload["repo"] == str(repo)
    json.dumps(payload, allow_nan=False)


def test_mcp_context_queries_builds_and_materializes_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    _write_index_marker(repo)
    bundle = _deterministic_bundle()
    calls = {"query": 0, "build": 0, "materialize": 0}

    def query_once(*args: object, **kwargs: object) -> QueryBundle:
        calls["query"] += 1
        return bundle

    def build_once(*args: object, **kwargs: object):
        calls["build"] += 1
        return build_context_pack(*args, **kwargs)

    def materialize_once(*args: object, **kwargs: object) -> dict[str, object]:
        calls["materialize"] += 1
        return context_pack_payload(*args, **kwargs)

    monkeypatch.setattr(mcp_tools, "query_repository", query_once)
    monkeypatch.setattr(mcp_tools, "build_context_pack", build_once)
    monkeypatch.setattr(mcp_tools, "context_pack_payload", materialize_once)

    payload = context_search_context_tool(
        str(repo),
        "audit endpoint",
        final_top_k=1,
    )

    assert payload["ok"] is True
    assert calls == {"query": 1, "build": 1, "materialize": 1}


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
    assert pack["missing_evidence"] == [
        {
            "category": "results",
            "required": True,
            "reason": "no result or evidence anchor is present in the bounded result set",
        }
    ]
    assert pack["next_queries"] == []

    log_path = repo / ".context-search" / "mcp_calls.jsonl"
    event = json.loads(log_path.read_text(encoding="utf-8"))
    assert event["tool"] == "context_search_context"
    assert event["query"] == "public empty query"
    assert event["context_pack"] == {
        "status": "empty",
        "confidence": "none",
        "item_count": 0,
        "group_counts": {group: 0 for group in CONTEXT_GROUPS},
        "required_missing_categories": ["results"],
        "recommended_missing_categories": [],
        "next_query_count": 0,
        "budget": {
            key: pack["budget"][key]
            for key in (
                "max_results",
                "max_evidence_anchors",
                "max_items",
                "included_results",
                "included_evidence_anchors",
                "content_bytes",
            )
        },
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
    ("exception", "message"),
    [
        (
            ContextPackError("ContextPack budget exceeded"),
            "ContextPack budget exceeded",
        ),
        (ValueError("private detail"), "Context pack construction failed"),
        (RuntimeError("private detail"), "Context pack construction failed"),
    ],
)
def test_mcp_context_contains_pack_phase_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    exception: Exception,
    message: str,
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
        "error": {"code": "context_failed", "message": message},
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
    assert payload["context_pack"]["schema_version"] == 1


def test_mcp_context_feedback_keeps_only_bounded_pack_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    _write_index_marker(repo)
    content_sentinel = "PRIVATE_CONTEXT_CONTENT_SENTINEL"
    path_sentinel = "PRIVATE_CONTEXT_PATH_SENTINEL"
    item_id_sentinel = "PRIVATE_CONTEXT_ITEM_ID_SENTINEL"
    next_query_sentinel = "PRIVATE_CONTEXT_NEXT_QUERY_SENTINEL"
    planner_rewrite_sentinel = "PRIVATE_PLANNER_REWRITE_SENTINEL"
    semantic_variant_sentinel = "PRIVATE_SEMANTIC_VARIANT_SENTINEL"
    discarded_hint_sentinel = "PRIVATE_DISCARDED_HINT_SENTINEL"
    public_query = "public privacy query"
    base = _deterministic_bundle(
        query=public_query,
        result_path=f"src/{path_sentinel}/AuditController.java",
        result_content=content_sentinel,
    )
    bundle = QueryBundle(
        query=base.query,
        expanded_tokens=base.expanded_tokens,
        results=base.results,
        followup_keywords=base.followup_keywords,
        summary=RetrievalSummary(entry_points=[next_query_sentinel]),
        planner=QueryPlan(
            original_query=public_query,
            rewritten_queries=[planner_rewrite_sentinel],
            intent="endpoint_lookup",
            status="ok",
            provider="test",
            model="test",
            discarded_hints=[discarded_hint_sentinel],
        ),
        evidence_anchors=base.evidence_anchors,
        query_variants=[
            QueryVariant("original", public_query, "original"),
            QueryVariant("planner:0", semantic_variant_sentinel, "planner"),
        ],
        variant_retrieval_status="hybrid",
    )
    original_materialize = context_pack_payload

    def materialize_with_private_item_id(*args: object, **kwargs: object):
        pack_payload = original_materialize(*args, **kwargs)
        pack_payload["items"][0]["id"] = item_id_sentinel
        return pack_payload

    monkeypatch.setattr(mcp_tools, "query_repository", lambda *args, **kwargs: bundle)
    monkeypatch.setattr(
        mcp_tools,
        "context_pack_payload",
        materialize_with_private_item_id,
    )

    payload = context_search_context_tool(
        str(repo),
        public_query,
        final_top_k=1,
    )

    assert payload["ok"] is True
    pack = payload["context_pack"]
    assert any(
        next_query_sentinel in next_query["query"]
        for next_query in pack["next_queries"]
    )
    log_path = repo / ".context-search" / "mcp_calls.jsonl"
    event = json.loads(log_path.read_text(encoding="utf-8"))
    assert set(event) == {
        "timestamp",
        "tool",
        "ok",
        "repo_hash",
        "query",
        "context_lines",
        "full_file",
        "final_top_k",
        "result_count",
        "top_score",
        "top_score_parts",
        "summary_counts",
        "followup_keyword_count",
        "embedding",
        "planner",
        "variant_retrieval",
        "error_code",
        "context_pack",
    }
    assert event["tool"] == "context_search_context"
    assert event["query"] == public_query
    assert event["context_pack"] == {
        "status": pack["status"],
        "confidence": pack["confidence"]["level"],
        "item_count": len(pack["items"]),
        "group_counts": {
            group: len(pack["groups"][group]) for group in CONTEXT_GROUPS
        },
        "required_missing_categories": [
            evidence["category"]
            for evidence in pack["missing_evidence"]
            if evidence["required"]
        ],
        "recommended_missing_categories": [
            evidence["category"]
            for evidence in pack["missing_evidence"]
            if not evidence["required"]
        ],
        "next_query_count": len(pack["next_queries"]),
        "budget": {
            key: pack["budget"][key]
            for key in (
                "max_results",
                "max_evidence_anchors",
                "max_items",
                "included_results",
                "included_evidence_anchors",
                "content_bytes",
            )
        },
    }
    serialized = json.dumps(event)
    for sentinel in (
        content_sentinel,
        path_sentinel,
        item_id_sentinel,
        next_query_sentinel,
        planner_rewrite_sentinel,
        semantic_variant_sentinel,
        discarded_hint_sentinel,
    ):
        assert sentinel not in serialized


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
    assert event["result_count"] == 0
    assert "context_pack" not in event
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
    assert event["context_pack"] == {
        "status": "partial",
        "confidence": "low",
        "item_count": 2,
        "group_counts": {
            "entrypoints": 1,
            "implementations": 0,
            "related_types": 0,
            "tests": 2,
            "configs_docs": 0,
            "supporting": 0,
        },
        "required_missing_categories": ["results", "entrypoints"],
        "recommended_missing_categories": ["supporting"],
        "next_query_count": 1,
        "budget": {
            "max_results": 2,
            "included_results": 1,
            "content_bytes": 4,
        },
    }
    assert private_sentinel not in json.dumps(event)
