import sqlite3
from pathlib import Path

from context_search_tool import sqlite_store as sqlite_store_module
from context_search_tool.models import (
    CodeRelation,
    CodeSignal,
    DocumentChunk,
    SourceFile,
    SymbolRef,
    generate_relation_id,
    generate_signal_id,
)
from context_search_tool.sqlite_store import SQLiteStore


def _chunk(
    chunk_id: str,
    file_path: str,
    lexical_tokens: list[str],
    symbols: list[SymbolRef] | None = None,
) -> DocumentChunk:
    return DocumentChunk(
        chunk_id=chunk_id,
        file_path=Path(file_path),
        start_line=1,
        end_line=10,
        content=f"class {chunk_id} {{}}",
        chunk_type="symbol",
        symbols=symbols or [],
        lexical_tokens=lexical_tokens,
        embedding_id=chunk_id,
        deleted_at=None,
        metadata={},
    )


def test_code_signal_and_relation_models_are_language_neutral() -> None:
    signal = CodeSignal(
        signal_id="sig-1",
        chunk_id="chunk-1",
        file_path=Path("src/App.java"),
        kind="endpoint",
        name="GET /apply/audit/stats/wait",
        start_line=10,
        end_line=15,
        language="java",
        tokens=["apply", "audit", "stats", "wait"],
        metadata={"http_method": "GET", "path": "/apply/audit/stats/wait"},
    )
    relation = CodeRelation(
        relation_id="rel-1",
        source_signal_id="sig-controller",
        target_name="ResourceAuditService.statsWait",
        kind="calls",
        confidence=0.8,
        metadata={"reason": "controller method body call"},
    )

    assert signal.kind == "endpoint"
    assert signal.tokens == ["apply", "audit", "stats", "wait"]
    assert signal.metadata["path"] == "/apply/audit/stats/wait"
    assert relation.kind == "calls"
    assert relation.confidence == 0.8
    assert relation.metadata["reason"] == "controller method body call"


def test_signal_and_relation_ids_are_deterministic_and_distinct() -> None:
    first = generate_signal_id(
        file_path=Path("src/App.java"),
        kind="endpoint",
        start_line=10,
        name="GET /apply/audit/stats/wait",
    )
    second = generate_signal_id(
        file_path=Path("src/App.java"),
        kind="endpoint",
        start_line=10,
        name="GET /apply/audit/stats/wait",
    )
    different_line = generate_signal_id(
        file_path=Path("src/App.java"),
        kind="endpoint",
        start_line=11,
        name="GET /apply/audit/stats/wait",
    )
    different_file = generate_signal_id(
        file_path=Path("src/Other.java"),
        kind="endpoint",
        start_line=10,
        name="GET /apply/audit/stats/wait",
    )

    assert first == second
    assert first != different_line
    assert first != different_file

    relation_id = generate_relation_id(
        source_signal_id="sig-controller",
        target_name="ResourceAuditService.statsWait",
        kind="calls",
    )

    assert relation_id == generate_relation_id(
        source_signal_id="sig-controller",
        target_name="ResourceAuditService.statsWait",
        kind="calls",
    )
    assert relation_id != generate_relation_id(
        source_signal_id="sig-controller",
        target_name="ResourceAuditService.auditStats",
        kind="calls",
    )
    assert ":" in relation_id


def test_store_round_trips_signals_by_chunk_and_token(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize()
    chunk = DocumentChunk(
        chunk_id="chunk-1",
        file_path=Path("src/App.java"),
        start_line=1,
        end_line=20,
        content="class App {}",
        chunk_type="symbol",
        symbols=[],
        lexical_tokens=["app"],
        embedding_id="chunk-1",
        deleted_at=None,
        metadata={},
    )
    endpoint = CodeSignal(
        signal_id="sig-endpoint",
        chunk_id="chunk-1",
        file_path=Path("src/App.java"),
        kind="endpoint",
        name="GET /apply/audit/stats/wait",
        start_line=10,
        end_line=15,
        language="java",
        tokens=["apply", "audit", "stats", "wait"],
        metadata={"http_method": "GET"},
    )
    comment = CodeSignal(
        signal_id="sig-comment",
        chunk_id="chunk-1",
        file_path=Path("src/App.java"),
        kind="comment",
        name="工作台统计",
        start_line=8,
        end_line=9,
        language="java",
        tokens=["工作台", "统计"],
        metadata={"text": "工作台统计-待我审核"},
    )

    store.replace_chunks(Path("src/App.java"), [chunk])
    store.replace_signals(Path("src/App.java"), [endpoint, comment])

    assert store.signals_for_chunk("chunk-1") == [comment, endpoint]
    assert store.signal_search(["stats", "wait"], limit=10) == [endpoint]
    assert store.signal_search(["工作台"], limit=10) == [comment]


def test_signals_for_chunks_batches_and_preserves_per_chunk_order(
    tmp_path: Path,
) -> None:
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize()
    first = _chunk("first", "src/First.java", ["first"])
    second = _chunk("second", "src/Second.java", ["second"])
    store.replace_chunks(first.file_path, [first])
    store.replace_chunks(second.file_path, [second])
    store.replace_signals(
        first.file_path,
        [
            CodeSignal("s2", "first", first.file_path, "method", "First.two", 8, 8, "java"),
            CodeSignal("s1", "first", first.file_path, "method", "First.one", 3, 3, "java"),
        ],
    )
    store.replace_signals(
        second.file_path,
        [CodeSignal("s3", "second", second.file_path, "method", "Second.one", 4, 4, "java")],
    )

    grouped = store.signals_for_chunks(["second", "missing", "first"])

    assert [signal.signal_id for signal in grouped["first"]] == ["s1", "s2"]
    assert [signal.signal_id for signal in grouped["second"]] == ["s3"]
    assert grouped["missing"] == []


def test_signal_search_keeps_endpoint_signals_near_top_for_endpoint_tokens(
    tmp_path: Path,
) -> None:
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize()
    chunk = DocumentChunk(
        chunk_id="chunk-1",
        file_path=Path("src/App.java"),
        start_line=1,
        end_line=80,
        content="class App {}",
        chunk_type="symbol",
        symbols=[],
        lexical_tokens=["stats"],
        embedding_id="chunk-1",
        deleted_at=None,
        metadata={},
    )
    method_signals = [
        CodeSignal(
            signal_id=f"sig-method-{index}",
            chunk_id="chunk-1",
            file_path=Path("src/App.java"),
            kind="method",
            name=f"StatsService.method{index}",
            start_line=index,
            end_line=index,
            language="java",
            tokens=["stats"],
            metadata={},
        )
        for index in range(1, 8)
    ]
    endpoint = CodeSignal(
        signal_id="sig-endpoint",
        chunk_id="chunk-1",
        file_path=Path("src/App.java"),
        kind="endpoint",
        name="POST /apply/audit/stats",
        start_line=60,
        end_line=60,
        language="java",
        tokens=["apply", "audit", "stats"],
        metadata={"path": "/apply/audit/stats"},
    )

    store.replace_chunks(Path("src/App.java"), [chunk])
    store.replace_signals(Path("src/App.java"), [*method_signals, endpoint])

    top_names = [signal.name for signal in store.signal_search(["stats"], limit=3)]

    assert "POST /apply/audit/stats" in top_names


def test_store_replaces_active_signals_for_file(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize()
    old_signal = CodeSignal(
        signal_id="sig-old",
        chunk_id="chunk-old",
        file_path=Path("src/App.java"),
        kind="endpoint",
        name="old",
        start_line=1,
        end_line=1,
        language="java",
        tokens=["old"],
        metadata={},
    )
    new_signal = CodeSignal(
        signal_id="sig-new",
        chunk_id="chunk-new",
        file_path=Path("src/App.java"),
        kind="endpoint",
        name="new",
        start_line=2,
        end_line=2,
        language="java",
        tokens=["new"],
        metadata={},
    )

    store.replace_signals(Path("src/App.java"), [old_signal])
    store.replace_signals(Path("src/App.java"), [new_signal])

    assert store.signal_search(["old"], limit=10) == []
    assert store.signal_search(["new"], limit=10) == [new_signal]


def test_store_round_trips_relations_by_source_and_target(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize()
    source_signal = CodeSignal(
        signal_id="sig-controller",
        chunk_id="chunk-controller",
        file_path=Path("src/App.java"),
        kind="endpoint",
        name="GET /apply/audit/stats/wait",
        start_line=10,
        end_line=15,
        language="java",
        tokens=["apply", "audit", "stats", "wait"],
        metadata={},
    )
    relation = CodeRelation(
        relation_id="rel-controller-service",
        source_signal_id="sig-controller",
        target_name="ResourceAuditService.statsWait",
        kind="calls",
        confidence=0.8,
        metadata={"reason": "controller method body call"},
    )

    store.replace_signals(Path("src/App.java"), [source_signal])
    store.replace_relations(Path("src/App.java"), [relation])

    assert store.relations_for_source("sig-controller") == [relation]
    assert store.relations_targeting("ResourceAuditService.statsWait") == [relation]


def test_relations_for_sources_batches_and_preserves_source_order(
    tmp_path: Path,
) -> None:
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize()
    source = _chunk("source", "src/Source.java", ["source"])
    store.replace_chunks(source.file_path, [source])
    store.replace_signals(
        source.file_path,
        [
            CodeSignal("sig-a", "source", source.file_path, "method", "Source.a", 1, 1, "java"),
            CodeSignal("sig-b", "source", source.file_path, "method", "Source.b", 2, 2, "java"),
        ],
    )
    store.replace_relations(
        source.file_path,
        [
            CodeRelation("rel-2", "sig-a", "Target.two", "calls", 0.8),
            CodeRelation("rel-1", "sig-a", "Target.one", "calls", 0.9),
            CodeRelation("rel-3", "sig-b", "Target.three", "calls", 0.7),
        ],
    )

    grouped = store.relations_for_sources(["sig-b", "missing", "sig-a"])

    assert [relation.relation_id for relation in grouped["sig-a"]] == ["rel-1", "rel-2"]
    assert [relation.relation_id for relation in grouped["sig-b"]] == ["rel-3"]
    assert grouped["missing"] == []


def test_store_round_trips_index_metadata(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize()

    assert store.get_metadata("signal_schema_version") is None

    store.set_metadata("signal_schema_version", "2")

    assert store.get_metadata("signal_schema_version") == "2"


def test_store_round_trips_files_chunks_symbols_and_fts(tmp_path: Path) -> None:
    db_path = tmp_path / "index.sqlite"
    store = SQLiteStore(db_path)
    store.initialize()

    source = SourceFile(
        path=Path("src/App.java"),
        language="java",
        sha256="a" * 64,
        size=100,
        mtime_ns=123,
        is_generated=False,
        is_test=False,
        metadata={},
    )
    symbol = SymbolRef(
        name="ApplyAuditController",
        kind="class",
        start_line=1,
        end_line=20,
        language="java",
        metadata={"role": "controller"},
    )
    chunk = DocumentChunk(
        chunk_id="chunk-1",
        file_path=Path("src/App.java"),
        start_line=1,
        end_line=20,
        content="@PostMapping(\"/apply/audit/pageEs\")\nclass ApplyAuditController {}",
        chunk_type="symbol",
        symbols=[symbol],
        lexical_tokens=["post", "mapping", "apply", "audit", "page", "es"],
        embedding_id="chunk-1",
        deleted_at=None,
        metadata={"route_path": "/apply/audit/pageEs"},
    )

    store.upsert_source_file(source)
    store.replace_chunks(Path("src/App.java"), [chunk])

    matches = store.lexical_search(["apply", "audit"], limit=5)

    assert matches[0].chunk_id == "chunk-1"
    assert store.chunk_for_line(Path("src/App.java"), 3).chunk_id == "chunk-1"


def test_chunks_for_ids_batches_existing_chunks(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize()
    first = _chunk("first", "src/First.java", ["first"])
    second = _chunk("second", "src/Second.java", ["second"])
    store.replace_chunks(first.file_path, [first])
    store.replace_chunks(second.file_path, [second])

    chunks = store.chunks_for_ids(["second", "missing", "first"])

    assert list(chunks) == ["second", "first"]
    assert chunks["second"].file_path == second.file_path
    assert chunks["first"].file_path == first.file_path


def test_chunks_matching_signal_or_symbols_batches_by_target(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize()
    service = _chunk(
        "service",
        "src/AppInfoServiceImpl.java",
        ["app", "info"],
        [SymbolRef("page", "method", 2, 2, "java")],
    )
    executor = _chunk(
        "executor",
        "src/PageAppCatalogQueryExe.java",
        ["page", "catalog"],
        [SymbolRef("execute", "method", 2, 2, "java")],
    )
    store.replace_chunks(service.file_path, [service])
    store.replace_chunks(executor.file_path, [executor])

    grouped = store.chunks_matching_signal_or_symbols(
        [
            "AppInfoServiceImpl.page",
            "PageAppCatalogQueryExe.execute",
            "AppInfoServiceImpl.missingMember",
            "missing",
        ],
        limit_per_target=3,
    )

    assert "service" in [chunk.chunk_id for chunk in grouped["AppInfoServiceImpl.page"]]
    assert "executor" in [chunk.chunk_id for chunk in grouped["PageAppCatalogQueryExe.execute"]]
    assert grouped["AppInfoServiceImpl.missingMember"] == store.chunks_matching_signal_or_symbol(
        "AppInfoServiceImpl.missingMember",
        3,
    ) == []
    assert grouped["missing"] == []


def test_path_symbol_search_downweights_content_token_matches(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize()
    content_only = DocumentChunk(
        chunk_id="content-only",
        file_path=Path("src/main/java/com/example/MqttConstant.java"),
        start_line=1,
        end_line=5,
        content="class MqttConstant { static final String TOPIC = \"设备告警\"; }",
        chunk_type="symbol",
        symbols=[],
        lexical_tokens=["alarm"],
        embedding_id="content-only",
        deleted_at=None,
        metadata={"language": "java"},
    )
    symbol_match = DocumentChunk(
        chunk_id="symbol-match",
        file_path=Path("src/main/java/com/example/service/AlarmService.java"),
        start_line=1,
        end_line=5,
        content="interface AlarmService {}",
        chunk_type="symbol",
        symbols=[
            SymbolRef(
                name="AlarmService",
                kind="interface",
                start_line=1,
                end_line=5,
                language="java",
                metadata={},
            )
        ],
        lexical_tokens=["alarm", "service"],
        embedding_id="symbol-match",
        deleted_at=None,
        metadata={"language": "java"},
    )
    store.replace_chunks(content_only.file_path, [content_only])
    store.replace_chunks(symbol_match.file_path, [symbol_match])

    results = store.path_symbol_search(["alarm"], limit=5)
    scores = {result.chunk_id: result.score_parts["path_symbol"] for result in results}

    assert scores["content-only"] < 1.0
    assert scores["symbol-match"] == 1.0


def test_store_marks_removed_file_chunks_deleted(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize()
    chunk = DocumentChunk(
        chunk_id="chunk-1",
        file_path=Path("src/App.java"),
        start_line=1,
        end_line=2,
        content="class App {}",
        chunk_type="generic",
        symbols=[],
        lexical_tokens=["class", "app"],
        embedding_id="chunk-1",
        deleted_at=None,
        metadata={},
    )
    store.replace_chunks(Path("src/App.java"), [chunk])

    store.mark_file_deleted(Path("src/App.java"))

    assert store.lexical_search(["app"], limit=5) == []
    assert store.deleted_chunk_ids() == {"chunk-1"}


def test_store_exposes_source_file_and_active_indexed_paths(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize()
    source = SourceFile(
        path=Path("src/App.java"),
        language="java",
        sha256="b" * 64,
        size=50,
        mtime_ns=456,
        is_generated=False,
        is_test=True,
        metadata={"role": "fixture"},
    )
    chunk = DocumentChunk(
        chunk_id="chunk-2",
        file_path=Path("src/App.java"),
        start_line=1,
        end_line=1,
        content="class App {}",
        chunk_type="generic",
        symbols=[],
        lexical_tokens=["app"],
        embedding_id="chunk-2",
        deleted_at=None,
        metadata={},
    )

    store.upsert_source_file(source)
    store.replace_chunks(Path("src/App.java"), [chunk])

    assert store.source_file_for_path(Path("src/App.java")) == source
    assert store.source_file_for_path(Path("src/Missing.java")) is None
    assert store.source_file_paths() == {Path("src/App.java")}
    assert store.indexed_file_paths() == {Path("src/App.java")}

    store.mark_file_deleted(Path("src/App.java"))

    assert store.source_file_paths() == set()
    assert store.indexed_file_paths() == set()


def test_store_direct_text_search_scores_literal_chunk_matches(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize()
    chunk = DocumentChunk(
        chunk_id="chunk-approval",
        file_path=Path("approval.py"),
        start_line=1,
        end_line=3,
        content="# 当前审批人查询接口\ndef current_auditor():\n    pass\n",
        chunk_type="text",
        symbols=[],
        lexical_tokens=[],
        embedding_id="chunk-approval",
        deleted_at=None,
        metadata={},
    )
    store.replace_chunks(Path("approval.py"), [chunk])

    matches = store.direct_text_search(["当前审批人查询接口", "审批人", "查询接口"], limit=5)

    assert [match.chunk_id for match in matches] == ["chunk-approval"]
    assert matches[0].source == "direct_text"
    assert matches[0].score_parts["direct_text"] >= 0.60
    assert matches[0].score_parts["direct_text_hits"] == 3.0


def test_exact_candidate_sources_meet_work_contracts(
    tmp_path: Path,
    monkeypatch,
) -> None:
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize()
    chunk = _chunk(
        "matching",
        "src/Match.py",
        ["needle", *(f"noise-{index}" for index in range(5000))],
    )
    store.replace_chunks(chunk.file_path, [chunk])
    decoded_token_rows = 0
    real_open_connection = sqlite_store_module._open_connection

    def traced_open_connection(*args, **kwargs):
        connection = real_open_connection(*args, **kwargs)
        state = {"statement": ""}

        def trace_statement(statement: str) -> None:
            state["statement"] = " ".join(statement.lower().split())

        def count_row(cursor, values):
            nonlocal decoded_token_rows
            row = sqlite3.Row(cursor, values)
            if "from chunk_tokens" in state["statement"]:
                decoded_token_rows += 1
            return row

        connection.set_trace_callback(trace_statement)
        connection.row_factory = count_row
        return connection

    monkeypatch.setattr(
        sqlite_store_module,
        "_open_connection",
        traced_open_connection,
    )

    lexical = store.lexical_search(["needle"], limit=10)
    path_symbol = store.path_symbol_search(["NEEDLE"], limit=10)

    assert [candidate.chunk_id for candidate in lexical] == ["matching"]
    assert [candidate.chunk_id for candidate in path_symbol] == ["matching"]
    assert path_symbol[0].score == 0.25
    assert decoded_token_rows == 1


from context_search_tool.sqlite_store import _dedupe_search_probes, _direct_text_score


def test_direct_text_score_caps_short_weak_probe() -> None:
    score = _direct_text_score(["审批"], ["审批"])
    assert score <= 0.50


def test_direct_text_score_treats_long_cjk_phrase_as_strong() -> None:
    score = _direct_text_score(["当前审批人查询接口"], ["当前审批人查询接口", "审批"])
    assert score >= 0.60


def test_direct_text_probe_deduplication_and_limit() -> None:
    deduped = _dedupe_search_probes(["审批", "审批", "当前审批人查询接口"])
    assert deduped == ["审批", "当前审批人查询接口"]

    many_probes = [f"p{i}" for i in range(40)] + ["当前审批人查询接口"]
    limited = _dedupe_search_probes(many_probes)
    assert len(limited) == 30
    assert "当前审批人查询接口" in limited


def test_direct_text_search_reads_each_active_chunk_once(
    tmp_path: Path,
    monkeypatch,
) -> None:
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize()

    # Create 1000 single-chunk files
    for i in range(1000):
        file_path = Path(f"module{i % 10}/file{i}.py")
        store.replace_chunks(
            file_path,
            [
                DocumentChunk(
                    chunk_id=f"chunk-{i}",
                    file_path=file_path,
                    start_line=1,
                    end_line=5,
                    content=f"# 审批流程 {i}\ndef process_{i}():\n    pass\n",
                    chunk_type="text",
                    symbols=[],
                    lexical_tokens=[],
                    embedding_id=f"chunk-{i}",
                    deleted_at=None,
                    metadata={},
                )
            ],
        )

    probes = ["审批流程", "审批", "流程"] + [f"process_{i}" for i in range(17)]
    decoded_rows = 0
    real_open_connection = sqlite_store_module._open_connection

    def traced_open_connection(*args, **kwargs):
        connection = real_open_connection(*args, **kwargs)
        state = {"statement": ""}

        def trace_statement(statement: str) -> None:
            state["statement"] = " ".join(statement.lower().split())

        def count_row(cursor, values):
            nonlocal decoded_rows
            row = sqlite3.Row(cursor, values)
            if "select chunk_id, file_path, content from chunks" in state["statement"]:
                decoded_rows += 1
            return row

        connection.set_trace_callback(trace_statement)
        connection.row_factory = count_row
        return connection

    monkeypatch.setattr(
        sqlite_store_module,
        "_open_connection",
        traced_open_connection,
    )

    results = store.direct_text_search(probes, limit=10)

    assert len(results) == 10
    assert all(result.source == "direct_text" for result in results)
    assert decoded_rows == 1000
