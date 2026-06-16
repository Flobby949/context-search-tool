from pathlib import Path

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
