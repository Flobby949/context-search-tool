import json
from pathlib import Path

import context_search_tool.mcp_tools as mcp_tools
from context_search_tool.mcp_tools import (
    context_search_explain_tool,
    context_search_index_tool,
    context_search_query_tool,
    context_search_stats_tool,
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
    assert event["planner"]["status"] == "disabled"
    assert "prompt" not in json.dumps(event).lower()


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
