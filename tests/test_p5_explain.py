import sqlite3
from pathlib import Path

import pytest
from typer.testing import CliRunner

from context_search_tool.cli import app
from context_search_tool.config import DEFAULT_CONFIG
from context_search_tool.indexer import index_repository
from context_search_tool.mcp_tools import context_search_explain_tool
from context_search_tool.models import (
    CodeRelation,
    CodeSignal,
    DocumentChunk,
    SourceFile,
)
from context_search_tool.sqlite_store import GraphReadSession, SQLiteStore


def test_ready_explain_appends_bounded_graph_projection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "App.java").write_text(
        "class App { String run() { return \"ok\"; } }\n",
        encoding="utf-8",
    )

    index_repository(repo, DEFAULT_CONFIG)

    original = SQLiteStore.graph_read_session
    sessions = 0

    def counted(self: SQLiteStore, **kwargs):
        nonlocal sessions
        sessions += 1
        return original(self, **kwargs)

    monkeypatch.setattr(SQLiteStore, "graph_read_session", counted)
    payload = context_search_explain_tool(str(repo), "App.java:1")

    assert sessions == 1
    assert tuple(payload) == ("ok", "repo", "chunk", "graph")
    graph = payload["graph"]
    assert tuple(graph) == (
        "status",
        "schema_version",
        "signals",
        "outgoing",
        "incoming",
        "omitted_signal_count",
        "omitted_outgoing_count",
        "omitted_incoming_count",
    )
    assert graph["status"] == "ready"
    assert graph["schema_version"] == 5
    assert graph["omitted_signal_count"] == 0
    assert all(len(graph[key]) <= 32 for key in ("signals", "outgoing", "incoming"))
    assert tuple(graph["signals"][0]) == (
        "signal_id",
        "kind",
        "name",
        "qualified_name",
        "producer",
        "start_line",
        "end_line",
        "recallable",
    )


def test_legacy_explain_has_empty_graph_arrays(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "App.java").write_text("class App {}\n", encoding="utf-8")
    index_repository(repo, DEFAULT_CONFIG)
    db_path = repo / ".context-search" / "index.sqlite"

    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "UPDATE index_metadata SET value = '4' WHERE key = 'signal_schema_version'"
        )

    payload = context_search_explain_tool(str(repo), "App.java:1")

    assert payload["graph"] == {
        "status": "legacy",
        "schema_version": 4,
        "signals": [],
        "outgoing": [],
        "incoming": [],
        "omitted_signal_count": 0,
        "omitted_outgoing_count": 0,
        "omitted_incoming_count": 0,
    }


def test_missing_signal_schema_renders_legacy_integer_zero(tmp_path: Path) -> None:
    repo = _indexed_java_repo(tmp_path)
    db_path = repo / ".context-search" / "index.sqlite"
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "DELETE FROM index_metadata WHERE key = 'signal_schema_version'"
        )

    payload = context_search_explain_tool(str(repo), "App.java:1")

    assert payload["graph"] == _empty_graph("legacy", 0)
    assert type(payload["graph"]["schema_version"]) is int


def test_stale_explain_is_summary_only_and_logs_stable_event(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    repo = _indexed_java_repo(tmp_path)
    store = SQLiteStore(repo / ".context-search" / "index.sqlite")
    store.set_metadata("graph_resolution_state", "stale")

    payload = context_search_explain_tool(str(repo), "App.java:1")

    assert payload["graph"] == _empty_graph("stale", 5)
    assert "graph_index_stale" in caplog.messages


def test_future_explain_fails_before_graph_column_reads(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = _indexed_java_repo(tmp_path)
    db_path = repo / ".context-search" / "index.sqlite"
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "UPDATE index_metadata SET value = '6' "
            "WHERE key = 'signal_schema_version'"
        )

    def forbidden(*args, **kwargs):
        raise AssertionError("future explain read graph columns")

    monkeypatch.setattr(GraphReadSession, "chunk_for_line", forbidden)

    assert context_search_explain_tool(str(repo), "App.java:1") == {
        "ok": False,
        "error": {
            "code": "incompatible_signal_schema",
            "message": "incompatible signal schema 6",
        },
    }


def test_ready_explain_uses_complete_universe_canonical_caps_and_cli_golden(
    tmp_path: Path,
) -> None:
    repo = _bounded_graph_repo(tmp_path)

    payload = context_search_explain_tool(str(repo), "Target.java:7")
    graph = payload["graph"]

    assert tuple(payload) == ("ok", "repo", "chunk", "graph")
    assert tuple(graph) == (
        "status",
        "schema_version",
        "signals",
        "outgoing",
        "incoming",
        "omitted_signal_count",
        "omitted_outgoing_count",
        "omitted_incoming_count",
    )
    assert (len(graph["signals"]), graph["omitted_signal_count"]) == (32, 9)
    assert (len(graph["outgoing"]), graph["omitted_outgoing_count"]) == (32, 8)
    assert (len(graph["incoming"]), graph["omitted_incoming_count"]) == (32, 8)
    assert graph["signals"][0]["signal_id"] == "module-target"
    assert [row["signal_id"] for row in graph["signals"][1:]] == [
        f"member-{index:02d}" for index in range(31)
    ]
    assert [row["relation_id"] for row in graph["outgoing"]] == [
        f"out-{index:02d}" for index in range(32)
    ]
    assert [row["relation_id"] for row in graph["incoming"]] == [
        f"in-{index:02d}" for index in range(32)
    ]
    assert tuple(graph["outgoing"][0]) == (
        "relation_id",
        "kind",
        "direction",
        "confidence",
        "producer_confidence",
        "resolution_confidence",
        "resolution",
        "source_signal_id",
        "source_name",
        "target_signal_id",
        "target_name",
        "target_path",
    )
    assert graph["outgoing"][0]["resolution_confidence"] is None
    assert graph["outgoing"][0]["target_signal_id"] == ""
    assert graph["outgoing"][0]["target_path"] == ""

    result = CliRunner().invoke(app, ["explain", str(repo), "Target.java:7"])

    assert result.exit_code == 0
    expected = [
        "File: Target.java",
        "Chunk ID: target-second",
        "Type: symbol",
        "Lines: 6-10",
        "Symbols: (none)",
        "Lexical tokens: (none)",
        "Embedding ID: target-second",
        "Metadata: {}",
        "Graph: ready (signal schema 5)",
        "Graph signals: 32 (omitted 9)",
        "Graph outgoing: 32 (omitted 8)",
        "Graph incoming: 32 (omitted 8)",
        "Signal: module Target.java [core_module] 1-10",
        *[
            f"Signal: method pkg.Member{index:02d} [java_ast] 6-6"
            for index in range(31)
        ],
        *[
            f"Outgoing: calls unresolved Member{index:02d} -> "
            f"External{index:02d} (0.8)"
            for index in range(32)
        ],
        *[
            f"Incoming: mapped_by resolved_exact Source{index:02d} -> "
            f"Member{index:02d} (0.9)"
            for index in range(32)
        ],
    ]
    assert result.output == "\n".join(expected) + "\n"


def _indexed_java_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "App.java").write_text("class App {}\n", encoding="utf-8")
    index_repository(repo, DEFAULT_CONFIG)
    return repo


def _empty_graph(status: str, version: int) -> dict[str, object]:
    return {
        "status": status,
        "schema_version": version,
        "signals": [],
        "outgoing": [],
        "incoming": [],
        "omitted_signal_count": 0,
        "omitted_outgoing_count": 0,
        "omitted_incoming_count": 0,
    }


def _bounded_graph_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    store = SQLiteStore(repo / ".context-search" / "index.sqlite")
    store.initialize_v5()
    first = _chunk("target-first", "Target.java", 1, 5)
    second = _chunk("target-second", "Target.java", 6, 10)
    source_chunk = _chunk("source", "Source.java", 1, 50)
    store.replace_chunks(Path("Target.java"), [first, second])
    store.replace_chunks(Path("Source.java"), [source_chunk])
    store.upsert_source_file(_source_file("Target.java"))
    store.upsert_source_file(_source_file("Source.java"))

    module = _signal(
        "module-target",
        "target-first",
        "Target.java",
        "module",
        "Target.java",
        1,
        10,
        producer="core_module",
        recallable=False,
    )
    members = [
        _signal(
            f"member-{index:02d}",
            "target-second",
            "Target.java",
            "method",
            f"Member{index:02d}",
            6,
            6,
        )
        for index in range(40)
    ]
    sources = [
        _signal(
            f"source-{index:02d}",
            "source",
            "Source.java",
            "method",
            f"Source{index:02d}",
            index + 1,
            index + 1,
        )
        for index in range(40)
    ]
    source_module = _signal(
        "module-source",
        "source",
        "Source.java",
        "module",
        "Source.java",
        1,
        50,
        producer="core_module",
        recallable=False,
    )
    outgoing = [
        _relation(
            f"out-{index:02d}",
            members[index],
            target_name=f"External{index:02d}",
            kind="calls",
            producer_confidence=0.8,
        )
        for index in range(40)
    ]
    incoming = [
        _relation(
            f"in-{index:02d}",
            sources[index],
            target=members[index],
            target_name=members[index].name,
            kind="mapped_by",
            producer_confidence=0.9,
        )
        for index in range(40)
    ]
    store.replace_graph_facts(Path("Target.java"), [module, *members], outgoing)
    store.replace_graph_facts(
        Path("Source.java"),
        [source_module, *sources],
        incoming,
    )
    store.mark_graph_ready(topology_fingerprint="a" * 64)
    return repo


def _chunk(
    chunk_id: str,
    file_path: str,
    start_line: int,
    end_line: int,
) -> DocumentChunk:
    return DocumentChunk(
        chunk_id=chunk_id,
        file_path=Path(file_path),
        start_line=start_line,
        end_line=end_line,
        content="content",
        chunk_type="symbol",
        embedding_id=chunk_id,
    )


def _source_file(file_path: str) -> SourceFile:
    return SourceFile(
        path=Path(file_path),
        language="java",
        sha256="0" * 64,
        size=1,
        mtime_ns=1,
        metadata={"project_root": ""},
    )


def _signal(
    signal_id: str,
    chunk_id: str,
    file_path: str,
    kind: str,
    name: str,
    start_line: int,
    end_line: int,
    *,
    producer: str = "java_ast",
    recallable: bool = True,
) -> CodeSignal:
    qualified_name = file_path if kind == "module" else f"pkg.{name}"
    return CodeSignal(
        signal_id=signal_id,
        chunk_id=chunk_id,
        file_path=Path(file_path),
        kind=kind,
        name=name,
        qualified_name=qualified_name,
        signature="()" if kind == "method" else "",
        arity=0 if kind == "method" else None,
        project_unit_key="",
        producer=producer,
        start_line=start_line,
        end_line=end_line,
        language="java",
        recallable=recallable,
    )


def _relation(
    relation_id: str,
    source: CodeSignal,
    *,
    target_name: str,
    kind: str,
    producer_confidence: float,
    target: CodeSignal | None = None,
) -> CodeRelation:
    resolved = target is not None
    return CodeRelation(
        relation_id=relation_id,
        source_signal_id=source.signal_id,
        target_name=target_name,
        kind=kind,
        confidence=producer_confidence,
        target_kind=target.kind if target is not None else "method",
        target_qualified_name=(
            target.qualified_name if target is not None else f"external.{target_name}"
        ),
        target_signature=target.signature if target is not None else "()",
        target_arity=0,
        target_project_unit_key="",
        target_signal_id=target.signal_id if target is not None else "",
        resolution="resolved_exact" if resolved else "unresolved",
        producer="test_graph",
        producer_confidence=producer_confidence,
        resolution_confidence=1.0 if resolved else None,
    )
