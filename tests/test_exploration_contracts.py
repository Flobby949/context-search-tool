from __future__ import annotations

import inspect
import json
from dataclasses import replace
from pathlib import Path

import pytest
from typer.testing import CliRunner

from context_search_tool import exploration, formatters, mcp_tools
from context_search_tool.cli import app
from context_search_tool.config import RetrievalConfig, ToolConfig
from context_search_tool.context_pack import (
    build_context_pack,
    resolve_context_pack_options,
)
from context_search_tool.exploration.models import ExploredContext
from context_search_tool.models import QueryPlan, RetrievalResult
from context_search_tool.retrieval import (
    QueryBundle,
    evidence_anchor_top_k,
    query_repository,
    trace_repository,
)
from context_search_tool.retrieval_trace import (
    SOURCE_COUNT_KEYS,
    ExplorationLimits,
    ExplorationProbe,
    ExplorationRound,
    ExplorationTrace,
    FinalEvidence,
)
from context_search_tool.sqlite_store import SQLiteStore


QUERY = "AppController endpoint \u8def\u5f84"
PATH_SENTINEL = "src/AppController.py"


def _source_counts(**values: int) -> tuple[tuple[str, int], ...]:
    return tuple((key, values.get(key, 0)) for key in SOURCE_COUNT_KEYS)


def _explored_context(query: str = QUERY) -> ExploredContext:
    config = ToolConfig()
    bundle = QueryBundle(
        query=query,
        expanded_tokens=["appcontroller", "endpoint"],
        results=[
            RetrievalResult(
                file_path=Path(PATH_SENTINEL),
                start_line=1,
                end_line=2,
                content="class AppController:\n    pass",
                score=0.9,
                score_parts={"evidence_priority": 0.0},
                reasons=["fixture"],
                followup_keywords=[],
            )
        ],
        followup_keywords=[],
        planner=QueryPlan(original_query=query),
    )
    options = resolve_context_pack_options(
        config,
        context_lines=None,
        max_evidence_anchors=evidence_anchor_top_k(
            config.retrieval.final_top_k
        ),
    )
    pack = build_context_pack(bundle, options)
    initial_probe = ExplorationProbe(
        id="r0p0",
        query=query,
        purpose="original_query",
        source="original",
        goal_ids=(),
        seed_paths=(),
        retrieval_outcome="complete",
        retrieval_termination_reason="completed",
        duration_ms=3,
        result_count=1,
        evidence_anchor_count=0,
        unique_path_count=1,
        duplicate_path_count=0,
        novel_path_count=1,
        newly_satisfied_goal_ids=(),
        source_counts=_source_counts(lexical=1),
        final_selection_count=1,
    )
    trace = ExplorationTrace(
        schema_version=2,
        mode="exploration",
        outcome="complete",
        termination_reason="exact_satisfied",
        duration_ms=7,
        limits=ExplorationLimits(effective_initial_top_k=12),
        initial_evidence_need_count=0,
        candidate_goal_count=0,
        retained_goal_count=0,
        omitted_goal_count=0,
        initial_satisfied_goal_count=0,
        final_satisfied_goal_count=0,
        planned_probe_count=0,
        executed_probe_count=0,
        stale_skipped_probe_count=0,
        unexecuted_probe_count=0,
        retrieval_call_count=1,
        goals=(),
        rounds=(
            ExplorationRound(
                round_index=0,
                kind="initial",
                duration_ms=3,
                input_path_count=0,
                output_path_count=1,
                novel_path_count=1,
                duplicate_path_count=0,
                newly_satisfied_goal_ids=(),
                probes=(initial_probe,),
            ),
        ),
        final_evidence_count=len(pack.items),
        final_evidence_omitted_count=0,
        final_evidence=tuple(
            FinalEvidence(
                item_id=item.id,
                file_path=item.file_path,
                source_round=0,
                probe_id="r0p0",
                probe_rank=index,
                goal_ids=(),
                selection_reason="retained_initial_evidence",
            )
            for index, item in enumerate(pack.items, start=1)
        ),
    )
    return ExploredContext(bundle, pack, bundle, pack, trace)


def _indexed_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    index_dir = repo / ".context-search"
    index_dir.mkdir()
    store = SQLiteStore(index_dir / "index.sqlite")
    store.initialize()
    store.set_metadata("signal_schema_version", "4")
    return repo


def test_explore_payload_has_exact_bounded_contract(tmp_path: Path) -> None:
    explored = _explored_context()

    payload = formatters.explore_payload(
        tmp_path,
        QUERY,
        explored,
        requested_final_top_k=None,
    )

    assert tuple(payload) == (
        "ok",
        "repo",
        "query",
        "retrieval",
        "context_pack",
        "trace",
    )
    assert tuple(payload["retrieval"]) == (
        "initial_result_count",
        "initial_evidence_anchor_count",
        "fused_result_count",
        "fused_evidence_anchor_count",
        "planner_status",
        "planner_intent",
        "requested_final_top_k",
        "effective_initial_top_k",
    )
    assert payload["retrieval"] == {
        "initial_result_count": 1,
        "initial_evidence_anchor_count": 0,
        "fused_result_count": 1,
        "fused_evidence_anchor_count": 0,
        "planner_status": "disabled",
        "planner_intent": "unknown",
        "requested_final_top_k": None,
        "effective_initial_top_k": 12,
    }
    assert payload["context_pack"]["schema_version"] == 2
    assert payload["trace"]["schema_version"] == 2
    assert payload["trace"]["mode"] == "exploration"
    serialized = json.dumps(payload)
    for forbidden in (
        "initial_pack",
        "initial_bundle",
        "fused_bundle",
        "v1_trace",
    ):
        assert forbidden not in serialized


def test_explore_json_and_markdown_are_strict_and_complete(
    tmp_path: Path,
) -> None:
    payload = formatters.explore_payload(
        tmp_path,
        QUERY,
        _explored_context(),
        requested_final_top_k=None,
    )

    encoded = formatters.format_explore_json(payload)
    markdown = formatters.format_explore_markdown(payload)

    assert json.loads(encoded) == payload
    assert "\\u8def\\u5f84" in encoded
    assert "# Controlled Exploration" in markdown
    assert "Outcome: complete" in markdown
    assert "Termination: exact_satisfied" in markdown
    assert "Retrieval calls: 1" in markdown
    assert "## Goal Gain" in markdown
    assert "## Final Evidence Provenance" in markdown
    assert "# Context Pack" in markdown

    malformed = dict(payload)
    malformed["trace"] = dict(payload["trace"])
    malformed["trace"]["schema_version"] = 1
    with pytest.raises(Exception):
        formatters.format_explore_json(malformed)


def test_cli_and_mcp_share_the_exact_explore_envelope(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = _indexed_repo(tmp_path)
    explored = _explored_context()
    monkeypatch.setattr(
        exploration,
        "explore_repository",
        lambda *args, **kwargs: explored,
    )

    cli_result = CliRunner().invoke(
        app,
        ["explore", str(repo), QUERY, "--json"],
    )
    mcp_result = mcp_tools.context_search_explore_tool(str(repo), QUERY)

    assert cli_result.exit_code == 0, cli_result.output
    assert json.loads(cli_result.output) == mcp_result
    assert mcp_result == formatters.explore_payload(
        repo,
        QUERY,
        explored,
        requested_final_top_k=None,
    )


def test_separate_live_cli_and_mcp_runs_differ_only_in_durations(
    tmp_path: Path,
) -> None:
    repo = _indexed_repo(tmp_path)
    query = "no indexed candidates"

    cli_result = CliRunner().invoke(
        app,
        ["explore", str(repo), query, "--json"],
    )
    mcp_result = mcp_tools.context_search_explore_tool(str(repo), query)

    assert cli_result.exit_code == 0, cli_result.output

    def normalize(value: object) -> object:
        if isinstance(value, dict):
            return {
                key: 0 if key == "duration_ms" else normalize(item)
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [normalize(item) for item in value]
        return value

    assert normalize(json.loads(cli_result.output)) == normalize(mcp_result)


def test_ordinary_surfaces_never_call_exploration_runner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = _indexed_repo(tmp_path)
    calls = 0

    def forbidden(*args: object, **kwargs: object) -> ExploredContext:
        nonlocal calls
        calls += 1
        raise AssertionError("ordinary operation called exploration")

    monkeypatch.setattr(exploration, "explore_repository", forbidden)
    config = ToolConfig()
    query_repository(repo, QUERY, config)
    trace_repository(repo, QUERY, config)
    assert mcp_tools.context_search_query_tool(str(repo), QUERY)["ok"] is True
    assert mcp_tools.context_search_trace_tool(str(repo), QUERY)["ok"] is True
    assert mcp_tools.context_search_context_tool(str(repo), QUERY)["ok"] is True
    runner = CliRunner()
    for command in ("query", "trace", "context"):
        result = runner.invoke(app, [command, str(repo), QUERY, "--json"])
        assert result.exit_code == 0, result.output
    assert calls == 0


@pytest.mark.parametrize(
    ("kwargs", "code"),
    [
        ({"final_top_k": True}, "query_failed"),
        ({"final_top_k": 0}, "query_failed"),
        ({"context_lines": -1}, "invalid_context_options"),
        ({"full_file": 1}, "invalid_context_options"),
        ({"max_items": 0}, "invalid_context_options"),
        ({"max_context_bytes": 4095}, "invalid_context_options"),
    ],
)
def test_mcp_explore_rejects_invalid_options_before_runner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    kwargs: dict[str, object],
    code: str,
) -> None:
    repo = _indexed_repo(tmp_path)
    calls = 0

    def forbidden(*args: object, **call_kwargs: object) -> ExploredContext:
        nonlocal calls
        calls += 1
        raise AssertionError("invalid request reached exploration")

    monkeypatch.setattr(exploration, "explore_repository", forbidden)

    payload = mcp_tools.context_search_explore_tool(
        str(repo),
        QUERY,
        **kwargs,
    )

    assert payload["ok"] is False
    assert payload["error"]["code"] == code
    assert calls == 0


def test_mcp_explore_rejects_invalid_persisted_limit_before_runner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = _indexed_repo(tmp_path)
    calls = 0
    invalid = replace(
        ToolConfig(),
        retrieval=RetrievalConfig(final_top_k=True),
    )
    monkeypatch.setattr(mcp_tools, "load_config", lambda path: invalid)

    def forbidden(*args: object, **kwargs: object) -> ExploredContext:
        nonlocal calls
        calls += 1
        raise AssertionError("invalid config reached exploration")

    monkeypatch.setattr(exploration, "explore_repository", forbidden)

    payload = mcp_tools.context_search_explore_tool(str(repo), QUERY)

    assert payload == {
        "ok": False,
        "error": {
            "code": "query_failed",
            "message": "retrieval.final_top_k must be a positive integer",
        },
    }
    assert calls == 0


def test_cli_explore_does_not_write_feedback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = _indexed_repo(tmp_path)
    monkeypatch.setattr(
        exploration,
        "explore_repository",
        lambda *args, **kwargs: _explored_context(),
    )

    result = CliRunner().invoke(app, ["explore", str(repo), QUERY, "--json"])

    assert result.exit_code == 0, result.output
    assert not (repo / ".context-search" / "mcp_calls.jsonl").exists()


def test_explore_feedback_is_exact_aggregate_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = _indexed_repo(tmp_path)
    explored = _explored_context()
    monkeypatch.setattr(
        exploration,
        "explore_repository",
        lambda *args, **kwargs: explored,
    )
    monkeypatch.setattr(
        mcp_tools,
        "_try_append_query_feedback",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("query feedback called")
        ),
    )
    monkeypatch.setattr(
        mcp_tools,
        "_append_query_feedback",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("query feedback called")
        ),
    )
    log_path = repo / ".context-search" / "mcp_calls.jsonl"
    log_path.write_text('{"existing":true}\n', encoding="utf-8")

    payload = mcp_tools.context_search_explore_tool(
        str(repo),
        QUERY,
        context_lines=2,
        final_top_k=30,
        max_items=2,
        max_context_bytes=4096,
    )

    assert payload["ok"] is True
    events = [json.loads(line) for line in log_path.read_text().splitlines()]
    assert events[0] == {"existing": True}
    event = events[1]
    assert set(event) == {
        "timestamp",
        "tool",
        "ok",
        "error_code",
        "repo_hash",
        "request",
        "exploration",
        "context_pack",
        "embedding",
    }
    assert tuple(event["request"]) == (
        "context_lines",
        "effective_initial_top_k",
        "full_file",
        "max_context_bytes",
        "max_items",
        "requested_final_top_k",
    ) or set(event["request"]) == {
        "context_lines",
        "full_file",
        "requested_final_top_k",
        "effective_initial_top_k",
        "max_items",
        "max_context_bytes",
    }
    assert event["request"]["requested_final_top_k"] == 30
    assert event["request"]["effective_initial_top_k"] == 12
    serialized = json.dumps(event, ensure_ascii=True)
    assert QUERY not in serialized
    assert PATH_SENTINEL not in serialized
    forbidden_keys = {
        "query",
        "probe_id",
        "seed_paths",
        "final_evidence",
        "goal_ids",
        "content",
        "source_counts",
        "message",
    }

    def keys(value: object) -> set[str]:
        if isinstance(value, dict):
            return set(value).union(*(keys(item) for item in value.values()))
        if isinstance(value, list):
            return set().union(*(keys(item) for item in value))
        return set()

    assert keys(event).isdisjoint(forbidden_keys)

    assert tuple(inspect.signature(mcp_tools._try_append_explore_feedback).parameters) == (
        "repo",
        "projection",
    )
    assert tuple(inspect.signature(mcp_tools._append_explore_feedback).parameters) == (
        "repo",
        "projection",
    )


def test_explore_error_feedback_keeps_all_keys_without_error_detail(
    tmp_path: Path,
) -> None:
    repo = _indexed_repo(tmp_path)

    payload = mcp_tools.context_search_explore_tool(
        str(repo),
        QUERY,
        final_top_k=True,
    )

    assert payload["error"]["code"] == "query_failed"
    event = json.loads(
        (repo / ".context-search" / "mcp_calls.jsonl").read_text(
            encoding="utf-8"
        )
    )
    assert event["ok"] is False
    assert event["error_code"] == "query_failed"
    assert event["exploration"] == {
        "executed_probe_count": 0,
        "final_satisfied_goal_count": 0,
        "initial_satisfied_goal_count": 0,
        "outcome": None,
        "planned_probe_count": 0,
        "retrieval_call_count": 0,
        "round_count": 0,
        "schema_version": None,
        "stale_skipped_probe_count": 0,
        "termination_reason": None,
    }
    assert event["context_pack"] == {
        "budget_exhausted": False,
        "confidence": None,
        "content_bytes": 0,
        "included_items": 0,
        "pack_bytes": 0,
        "schema_version": None,
        "status": None,
    }
    assert set(event["embedding"].values()) == {None}
    serialized = json.dumps(event)
    assert QUERY not in serialized
    assert payload["error"]["message"] not in serialized


def test_explore_projection_failure_does_not_change_response(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = _indexed_repo(tmp_path)
    explored = _explored_context()
    monkeypatch.setattr(
        exploration,
        "explore_repository",
        lambda *args, **kwargs: explored,
    )

    def fail(*args: object, **kwargs: object) -> dict[str, object]:
        raise RuntimeError("private projection failure")

    monkeypatch.setattr(mcp_tools, "_explore_feedback_projection", fail)

    payload = mcp_tools.context_search_explore_tool(str(repo), QUERY)

    assert payload == formatters.explore_payload(
        repo,
        QUERY,
        explored,
        requested_final_top_k=None,
    )
    assert not (repo / ".context-search" / "mcp_calls.jsonl").exists()


@pytest.mark.parametrize("error", [OSError("disk"), RuntimeError("private")])
def test_explore_feedback_failure_does_not_change_response(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
) -> None:
    repo = _indexed_repo(tmp_path)
    explored = _explored_context()
    monkeypatch.setattr(
        exploration,
        "explore_repository",
        lambda *args, **kwargs: explored,
    )

    def fail(*args: object, **kwargs: object) -> None:
        raise error

    monkeypatch.setattr(mcp_tools, "_append_explore_feedback", fail)

    assert mcp_tools.context_search_explore_tool(str(repo), QUERY) == (
        formatters.explore_payload(
            repo,
            QUERY,
            explored,
            requested_final_top_k=None,
        )
    )


@pytest.mark.parametrize("error", [KeyboardInterrupt(), SystemExit(2)])
def test_explore_feedback_does_not_swallow_control_flow(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    error: BaseException,
) -> None:
    repo = _indexed_repo(tmp_path)
    monkeypatch.setattr(
        exploration,
        "explore_repository",
        lambda *args, **kwargs: _explored_context(),
    )

    def fail(*args: object, **kwargs: object) -> None:
        raise error

    monkeypatch.setattr(mcp_tools, "_append_explore_feedback", fail)

    with pytest.raises(type(error)):
        mcp_tools.context_search_explore_tool(str(repo), QUERY)


def test_mcp_explore_registration_and_forwarding_are_exact(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from context_search_tool import mcp_server

    parameters = inspect.signature(mcp_server.context_search_explore).parameters
    assert tuple(parameters) == (
        "repo",
        "query",
        "context_lines",
        "full_file",
        "final_top_k",
        "max_items",
        "max_context_bytes",
    )
    captured: dict[str, object] = {}

    def capture(**kwargs: object) -> dict[str, object]:
        captured.update(kwargs)
        return {"ok": True}

    monkeypatch.setattr(mcp_server, "context_search_explore_tool", capture)
    result = mcp_server.context_search_explore(
        "repo",
        "query",
        3,
        True,
        9,
        4,
        5000,
    )

    assert result == {"ok": True}
    assert captured == {
        "repo": "repo",
        "query": "query",
        "context_lines": 3,
        "full_file": True,
        "final_top_k": 9,
        "max_items": 4,
        "max_context_bytes": 5000,
    }
