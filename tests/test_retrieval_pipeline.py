import logging
from pathlib import Path

import pytest

from context_search_tool import retrieval
from context_search_tool.config import (
    DEFAULT_CONFIG,
    EmbeddingConfig,
    IndexConfig,
    RetrievalConfig,
    ToolConfig,
)
from context_search_tool.indexer import index_repository
from context_search_tool.models import (
    CodeRelation,
    CodeSignal,
    DocumentChunk,
    RetrievalCandidate,
    RetrievalSummary,
    SymbolRef,
)
from context_search_tool.paths import index_dir_for
from context_search_tool.retrieval import query_repository
from context_search_tool.sqlite_store import SQLiteStore


def test_query_expands_signal_relations_before_weak_lexical_matches(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "WorkspaceController.java").write_text(
        """
class WorkspaceController {
  // 工作台相关代码
  String page() { return service.list(); }
}
""".strip(),
        encoding="utf-8",
    )
    (repo / "WorkspaceServiceImpl.java").write_text(
        """
class WorkspaceServiceImpl {
  String list() { return query.execute(); }
}
""".strip(),
        encoding="utf-8",
    )
    (repo / "WorkspaceQueryExe.java").write_text(
        """
class WorkspaceQueryExe {
  String execute() { return "workspace"; }
}
""".strip(),
        encoding="utf-8",
    )
    (repo / "WorkspaceDto.java").write_text(
        'class WorkspaceDto { String label = "工作台相关代码"; }\n',
        encoding="utf-8",
    )
    config = ToolConfig(
        retrieval=RetrievalConfig(
            semantic_top_k=0,
            lexical_top_k=10,
            final_top_k=4,
            context_before_lines=0,
            context_after_lines=0,
        )
    )
    index_repository(repo, config)
    store = SQLiteStore(index_dir_for(repo) / "index.sqlite")

    controller_chunk = store.chunk_for_line(Path("WorkspaceController.java"), 3)
    service_chunk = store.chunk_for_line(Path("WorkspaceServiceImpl.java"), 2)
    executor_chunk = store.chunk_for_line(Path("WorkspaceQueryExe.java"), 2)
    controller_signal = CodeSignal(
        signal_id="sig-controller",
        chunk_id=controller_chunk.chunk_id,
        file_path=Path("WorkspaceController.java"),
        kind="endpoint",
        name="GET /workspace/page",
        start_line=3,
        end_line=3,
        language="java",
        tokens=["workspace", "工作台统计", "待我审核"],
        metadata={"path": "/workspace/page", "text": "工作台统计-待我审核"},
    )
    service_signal = CodeSignal(
        signal_id="sig-service",
        chunk_id=service_chunk.chunk_id,
        file_path=Path("WorkspaceServiceImpl.java"),
        kind="method",
        name="WorkspaceServiceImpl.list",
        start_line=2,
        end_line=2,
        language="java",
        tokens=["workspace", "service", "list"],
        metadata={},
    )
    executor_signal = CodeSignal(
        signal_id="sig-executor",
        chunk_id=executor_chunk.chunk_id,
        file_path=Path("WorkspaceQueryExe.java"),
        kind="method",
        name="WorkspaceQueryExe.execute",
        start_line=2,
        end_line=2,
        language="java",
        tokens=["workspace", "query", "execute"],
        metadata={},
    )
    store.replace_signals(Path("WorkspaceController.java"), [controller_signal])
    store.replace_signals(Path("WorkspaceServiceImpl.java"), [service_signal])
    store.replace_signals(Path("WorkspaceQueryExe.java"), [executor_signal])
    store.replace_relations(
        Path("WorkspaceController.java"),
        [
            CodeRelation(
                relation_id="rel-controller-service",
                source_signal_id="sig-controller",
                target_name="WorkspaceService.list",
                kind="calls",
                confidence=0.9,
                metadata={},
            )
        ],
    )
    store.replace_relations(
        Path("WorkspaceServiceImpl.java"),
        [
            CodeRelation(
                relation_id="rel-service-executor",
                source_signal_id="sig-service",
                target_name="WorkspaceQueryExe.execute",
                kind="calls",
                confidence=0.9,
                metadata={},
            )
        ],
    )

    bundle = query_repository(repo, "工作台相关代码", config)

    assert [result.file_path for result in bundle.results] == [
        Path("WorkspaceController.java"),
        Path("WorkspaceServiceImpl.java"),
        Path("WorkspaceQueryExe.java"),
        Path("WorkspaceDto.java"),
    ]
    assert "signal" in bundle.results[0].score_parts
    assert "relation" in bundle.results[1].score_parts
    assert "relation" in bundle.results[2].score_parts
    assert "lexical" in bundle.results[3].score_parts


def test_workflow_alias_query_prefers_process_endpoint_over_generic_api(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "HealthCheckController.java").write_text(
        """
@RequestMapping("/health")
class HealthCheckController {
  /**
   * 健康检查接口
   */
  @GetMapping("/check")
  String healthCheck() { return "ok"; }
}
""".strip(),
        encoding="utf-8",
    )
    (repo / "ProcessOpenController.java").write_text(
        """
/**
 * 对外开放的流程处理控制器，专门用于 APAAS 系统间集成的接口
 */
@RequestMapping("/openapi/process")
class ProcessOpenController {
  /**
   * 启动流程
   */
  @PostMapping("/start")
  String start() { return processService.startProcess(); }
}
""".strip(),
        encoding="utf-8",
    )
    config = ToolConfig(
        retrieval=RetrievalConfig(
            semantic_top_k=0,
            lexical_top_k=10,
            final_top_k=2,
            context_before_lines=0,
            context_after_lines=0,
        )
    )
    index_repository(repo, config)

    bundle = query_repository(repo, "apaas工作流相关接口", config)

    assert bundle.results[0].file_path == Path("ProcessOpenController.java")
    assert bundle.results[1].file_path == Path("HealthCheckController.java")
    assert "POST /openapi/process/start" in bundle.summary.entry_points


def test_relation_expansion_scores_from_signal_strength(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize()
    strong_controller = DocumentChunk(
        chunk_id="strong-controller",
        file_path=Path("StrongController.java"),
        start_line=1,
        end_line=5,
        content="class StrongController {}",
        chunk_type="symbol",
        symbols=[],
        lexical_tokens=["common"],
        embedding_id="strong-controller",
        deleted_at=None,
        metadata={"language": "java"},
    )
    weak_controller = DocumentChunk(
        chunk_id="weak-controller",
        file_path=Path("WeakController.java"),
        start_line=1,
        end_line=5,
        content="class WeakController {}",
        chunk_type="symbol",
        symbols=[],
        lexical_tokens=["common"],
        embedding_id="weak-controller",
        deleted_at=None,
        metadata={"language": "java"},
    )
    strong_service = DocumentChunk(
        chunk_id="strong-service",
        file_path=Path("StrongServiceImpl.java"),
        start_line=1,
        end_line=5,
        content="class StrongServiceImpl {}",
        chunk_type="symbol",
        symbols=[],
        lexical_tokens=["service"],
        embedding_id="strong-service",
        deleted_at=None,
        metadata={"language": "java"},
    )
    weak_service = DocumentChunk(
        chunk_id="weak-service",
        file_path=Path("WeakServiceImpl.java"),
        start_line=1,
        end_line=5,
        content="class WeakServiceImpl {}",
        chunk_type="symbol",
        symbols=[],
        lexical_tokens=["service"],
        embedding_id="weak-service",
        deleted_at=None,
        metadata={"language": "java"},
    )
    store.replace_chunks(
        Path("StrongController.java"),
        [strong_controller],
    )
    store.replace_chunks(Path("WeakController.java"), [weak_controller])
    store.replace_chunks(Path("StrongServiceImpl.java"), [strong_service])
    store.replace_chunks(Path("WeakServiceImpl.java"), [weak_service])
    strong_signal = CodeSignal(
        signal_id="sig-strong",
        chunk_id="strong-controller",
        file_path=Path("StrongController.java"),
        kind="endpoint",
        name="GET /strong",
        start_line=1,
        end_line=1,
        language="java",
        tokens=["strong"],
        metadata={},
    )
    weak_signal = CodeSignal(
        signal_id="sig-weak",
        chunk_id="weak-controller",
        file_path=Path("WeakController.java"),
        kind="endpoint",
        name="GET /weak",
        start_line=1,
        end_line=1,
        language="java",
        tokens=["weak"],
        metadata={},
    )
    strong_target = CodeSignal(
        signal_id="sig-strong-target",
        chunk_id="strong-service",
        file_path=Path("StrongServiceImpl.java"),
        kind="method",
        name="StrongServiceImpl.run",
        start_line=1,
        end_line=1,
        language="java",
        tokens=["strong", "run"],
        metadata={},
    )
    weak_target = CodeSignal(
        signal_id="sig-weak-target",
        chunk_id="weak-service",
        file_path=Path("WeakServiceImpl.java"),
        kind="method",
        name="WeakServiceImpl.run",
        start_line=1,
        end_line=1,
        language="java",
        tokens=["weak", "run"],
        metadata={},
    )
    store.replace_signals(
        Path("StrongController.java"),
        [strong_signal],
    )
    store.replace_signals(Path("WeakController.java"), [weak_signal])
    store.replace_signals(Path("StrongServiceImpl.java"), [strong_target])
    store.replace_signals(Path("WeakServiceImpl.java"), [weak_target])
    store.replace_relations(
        Path("StrongController.java"),
        [
            CodeRelation(
                relation_id="rel-strong",
                source_signal_id="sig-strong",
                target_name="StrongServiceImpl.run",
                kind="calls",
                confidence=0.8,
                metadata={},
            )
        ],
    )
    store.replace_relations(
        Path("WeakController.java"),
        [
            CodeRelation(
                relation_id="rel-weak",
                source_signal_id="sig-weak",
                target_name="WeakServiceImpl.run",
                kind="calls",
                confidence=0.8,
                metadata={},
            )
        ],
    )

    expanded = retrieval._relation_expansion_candidates(
        store,
        [
            RetrievalCandidate(
                chunk_id="strong-controller",
                score=10.0,
                source="signal,path_symbol",
                score_parts={"signal": 0.5, "path_symbol": 10.0},
            ),
            RetrievalCandidate(
                chunk_id="weak-controller",
                score=10.0,
                source="signal,path_symbol",
                score_parts={"signal": 0.05, "path_symbol": 10.0},
            ),
        ],
        DEFAULT_CONFIG,
    )

    scores = {candidate.chunk_id: candidate.score for candidate in expanded}
    assert scores["strong-service"] > scores["weak-service"]


def test_relation_expansion_ignores_candidates_without_signal_or_relation_score(
    tmp_path: Path,
) -> None:
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize()
    source = DocumentChunk(
        chunk_id="source",
        file_path=Path("SourceController.java"),
        start_line=1,
        end_line=5,
        content="class SourceController {}",
        chunk_type="symbol",
        symbols=[],
        lexical_tokens=["source"],
        embedding_id="source",
        deleted_at=None,
        metadata={"language": "java"},
    )
    target = DocumentChunk(
        chunk_id="target",
        file_path=Path("TargetServiceImpl.java"),
        start_line=1,
        end_line=5,
        content="class TargetServiceImpl {}",
        chunk_type="symbol",
        symbols=[],
        lexical_tokens=["target"],
        embedding_id="target",
        deleted_at=None,
        metadata={"language": "java"},
    )
    source_signal = CodeSignal(
        signal_id="sig-source",
        chunk_id="source",
        file_path=Path("SourceController.java"),
        kind="endpoint",
        name="GET /source",
        start_line=1,
        end_line=1,
        language="java",
        tokens=["source"],
        metadata={},
    )
    target_signal = CodeSignal(
        signal_id="sig-target",
        chunk_id="target",
        file_path=Path("TargetServiceImpl.java"),
        kind="method",
        name="TargetServiceImpl.run",
        start_line=1,
        end_line=1,
        language="java",
        tokens=["target", "run"],
        metadata={},
    )
    store.replace_chunks(Path("SourceController.java"), [source])
    store.replace_chunks(Path("TargetServiceImpl.java"), [target])
    store.replace_signals(Path("SourceController.java"), [source_signal])
    store.replace_signals(Path("TargetServiceImpl.java"), [target_signal])
    store.replace_relations(
        Path("SourceController.java"),
        [
            CodeRelation(
                relation_id="rel-source-target",
                source_signal_id="sig-source",
                target_name="TargetServiceImpl.run",
                kind="calls",
                confidence=0.8,
                metadata={},
            )
        ],
    )

    expanded = retrieval._relation_expansion_candidates(
        store,
        [
            RetrievalCandidate(
                chunk_id="source",
                score=1.0,
                source="semantic",
                score_parts={"semantic": 1.0},
            )
        ],
        DEFAULT_CONFIG,
    )

    assert expanded == []


def test_relation_expansion_adds_relation_score_to_existing_direct_candidate(
    tmp_path: Path,
) -> None:
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize()
    source = DocumentChunk(
        chunk_id="source",
        file_path=Path("SourceController.java"),
        start_line=1,
        end_line=5,
        content="class SourceController {}",
        chunk_type="symbol",
        symbols=[],
        lexical_tokens=["source"],
        embedding_id="source",
        deleted_at=None,
        metadata={"language": "java"},
    )
    target = DocumentChunk(
        chunk_id="target",
        file_path=Path("TargetServiceImpl.java"),
        start_line=1,
        end_line=5,
        content="class TargetServiceImpl {}",
        chunk_type="symbol",
        symbols=[],
        lexical_tokens=["target"],
        embedding_id="target",
        deleted_at=None,
        metadata={"language": "java"},
    )
    source_signal = CodeSignal(
        signal_id="sig-source",
        chunk_id="source",
        file_path=Path("SourceController.java"),
        kind="endpoint",
        name="GET /source",
        start_line=1,
        end_line=1,
        language="java",
        tokens=["source"],
        metadata={},
    )
    target_signal = CodeSignal(
        signal_id="sig-target",
        chunk_id="target",
        file_path=Path("TargetServiceImpl.java"),
        kind="method",
        name="TargetServiceImpl.run",
        start_line=1,
        end_line=1,
        language="java",
        tokens=["target", "run"],
        metadata={},
    )
    store.replace_chunks(Path("SourceController.java"), [source])
    store.replace_chunks(Path("TargetServiceImpl.java"), [target])
    store.replace_signals(Path("SourceController.java"), [source_signal])
    store.replace_signals(Path("TargetServiceImpl.java"), [target_signal])
    store.replace_relations(
        Path("SourceController.java"),
        [
            CodeRelation(
                relation_id="rel-source-target",
                source_signal_id="sig-source",
                target_name="TargetServiceImpl.run",
                kind="calls",
                confidence=0.8,
                metadata={},
            )
        ],
    )

    expanded = retrieval._relation_expansion_candidates(
        store,
        [
            RetrievalCandidate(
                chunk_id="source",
                score=1.0,
                source="signal",
                score_parts={"signal": 1.0},
            ),
            RetrievalCandidate(
                chunk_id="target",
                score=0.1,
                source="signal",
                score_parts={"signal": 0.1},
            ),
        ],
        DEFAULT_CONFIG,
    )

    assert any(candidate.chunk_id == "target" for candidate in expanded)


def test_query_bundle_summary_groups_entrypoints_implementation_related_and_legacy(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "WorkspaceController.java").write_text(
        """
@RequestMapping("/workspace")
class WorkspaceController {
  @GetMapping("/page")
  String page() { return "ok"; }
}
""".strip(),
        encoding="utf-8",
    )
    (repo / "WorkspaceServiceImpl.java").write_text(
        """
class WorkspaceServiceImpl {
  String list() { return "ok"; }
}
""".strip(),
        encoding="utf-8",
    )
    (repo / "WorkspaceExecutor.java").write_text(
        """
class WorkspaceExecutor {
  String execute() { return "ok"; }
}
""".strip(),
        encoding="utf-8",
    )
    (repo / "WorkspaceDto.java").write_text(
        """
class WorkspaceDto {
  String name;
}
""".strip(),
        encoding="utf-8",
    )
    (repo / "WorkspaceLegacyType.java").write_text(
        """
class WorkspaceLegacyType {
  String old;
}
""".strip(),
        encoding="utf-8",
    )
    config = ToolConfig(
        retrieval=RetrievalConfig(
            semantic_top_k=0,
            lexical_top_k=20,
            final_top_k=5,
            context_before_lines=0,
            context_after_lines=0,
        )
    )
    index_repository(repo, config)
    store = SQLiteStore(index_dir_for(repo) / "index.sqlite")

    controller_chunk = store.chunk_for_line(Path("WorkspaceController.java"), 3)
    service_chunk = store.chunk_for_line(Path("WorkspaceServiceImpl.java"), 2)
    executor_chunk = store.chunk_for_line(Path("WorkspaceExecutor.java"), 2)
    dto_chunk = store.chunk_for_line(Path("WorkspaceDto.java"), 2)
    legacy_chunk = store.chunk_for_line(Path("WorkspaceLegacyType.java"), 2)

    store.replace_signals(
        Path("WorkspaceController.java"),
        [
            CodeSignal(
                signal_id="sig-endpoint",
                chunk_id=controller_chunk.chunk_id,
                file_path=Path("WorkspaceController.java"),
                kind="endpoint",
                name="GET /workspace/page",
                start_line=3,
                end_line=3,
                language="java",
                tokens=["workspace", "page"],
                metadata={},
            ),
            CodeSignal(
                signal_id="sig-controller-comment",
                chunk_id=controller_chunk.chunk_id,
                file_path=Path("WorkspaceController.java"),
                kind="comment",
                name="WorkspaceController comment",
                start_line=1,
                end_line=1,
                language="java",
                tokens=["workspace"],
                metadata={},
            ),
        ],
    )
    store.replace_signals(
        Path("WorkspaceServiceImpl.java"),
        [
            CodeSignal(
                signal_id="sig-service",
                chunk_id=service_chunk.chunk_id,
                file_path=Path("WorkspaceServiceImpl.java"),
                kind="method",
                name="WorkspaceServiceImpl.list",
                start_line=2,
                end_line=2,
                language="java",
                tokens=["workspace", "service"],
                metadata={},
            )
        ],
    )
    store.replace_signals(
        Path("WorkspaceExecutor.java"),
        [
            CodeSignal(
                signal_id="sig-executor",
                chunk_id=executor_chunk.chunk_id,
                file_path=Path("WorkspaceExecutor.java"),
                kind="method",
                name="WorkspaceExecutor.execute",
                start_line=2,
                end_line=2,
                language="java",
                tokens=["workspace", "executor"],
                metadata={},
            )
        ],
        )
    store.replace_signals(
        Path("WorkspaceDto.java"),
        [
            CodeSignal(
                signal_id="sig-dto",
                chunk_id=dto_chunk.chunk_id,
                file_path=Path("WorkspaceDto.java"),
                kind="type",
                name="WorkspaceDto",
                start_line=2,
                end_line=2,
                language="java",
                tokens=["workspace", "dto"],
                metadata={},
            ),
            CodeSignal(
                signal_id="sig-dto-usage",
                chunk_id=dto_chunk.chunk_id,
                file_path=Path("WorkspaceDto.java"),
                kind="usage",
                name="WorkspaceDto.load",
                start_line=1,
                end_line=1,
                language="java",
                tokens=["workspace", "dto"],
                metadata={},
            ),
        ],
    )
    store.replace_signals(
        Path("WorkspaceLegacyType.java"),
        [
            CodeSignal(
                signal_id="sig-legacy",
                chunk_id=legacy_chunk.chunk_id,
                file_path=Path("WorkspaceLegacyType.java"),
                kind="type",
                name="WorkspaceLegacyType",
                start_line=2,
                end_line=2,
                language="java",
                tokens=["workspace", "legacy"],
                metadata={},
            )
        ],
    )
    store.replace_relations(
        Path("WorkspaceController.java"),
        [
            CodeRelation(
                relation_id="rel-controller-service",
                source_signal_id="sig-endpoint",
                target_name="WorkspaceServiceImpl.list",
                kind="calls",
                confidence=0.9,
                metadata={},
            )
        ],
    )
    store.replace_relations(
        Path("WorkspaceServiceImpl.java"),
        [
            CodeRelation(
                relation_id="rel-service-executor",
                source_signal_id="sig-service",
                target_name="WorkspaceExecutor.execute",
                kind="calls",
                confidence=0.9,
                metadata={},
            )
        ],
    )

    bundle = query_repository(repo, "workspace", config)

    assert bundle.summary.entry_points == ["GET /workspace/page"]
    assert bundle.summary.implementation == [
        "WorkspaceExecutor.execute",
        "WorkspaceServiceImpl.list",
    ]
    assert bundle.summary.related_types == ["WorkspaceDto"]
    assert bundle.summary.possibly_legacy == ["WorkspaceLegacyType"]


def test_grouping_reasons_in_results(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "WorkspaceController.java").write_text(
        """
@RequestMapping("/workspace")
class WorkspaceController {
  @GetMapping("/page")
  String page() { return "ok"; }
}
""".strip(),
        encoding="utf-8",
    )
    (repo / "WorkspaceServiceImpl.java").write_text(
        """
class WorkspaceServiceImpl {
  String list() { return "ok"; }
}
""".strip(),
        encoding="utf-8",
    )
    config = ToolConfig(
        retrieval=RetrievalConfig(
            semantic_top_k=0,
            lexical_top_k=20,
            final_top_k=4,
            context_before_lines=0,
            context_after_lines=0,
        )
    )
    index_repository(repo, config)
    store = SQLiteStore(index_dir_for(repo) / "index.sqlite")

    controller_chunk = store.chunk_for_line(Path("WorkspaceController.java"), 3)
    service_chunk = store.chunk_for_line(Path("WorkspaceServiceImpl.java"), 2)

    store.replace_signals(
        Path("WorkspaceController.java"),
        [
            CodeSignal(
                signal_id="sig-endpoint",
                chunk_id=controller_chunk.chunk_id,
                file_path=Path("WorkspaceController.java"),
                kind="endpoint",
                name="GET /workspace/page",
                start_line=3,
                end_line=3,
                language="java",
                tokens=["workspace", "page"],
                metadata={"http_method": "GET"},
            ),
            CodeSignal(
                signal_id="sig-controller-comment",
                chunk_id=controller_chunk.chunk_id,
                file_path=Path("WorkspaceController.java"),
                kind="comment",
                name="WorkspaceController comment",
                start_line=1,
                end_line=1,
                language="java",
                tokens=["workspace", "comment"],
                metadata={},
            ),
        ],
    )
    store.replace_signals(
        Path("WorkspaceServiceImpl.java"),
        [
            CodeSignal(
                signal_id="sig-service",
                chunk_id=service_chunk.chunk_id,
                file_path=Path("WorkspaceServiceImpl.java"),
                kind="method",
                name="WorkspaceServiceImpl.list",
                start_line=2,
                end_line=2,
                language="java",
                tokens=["workspace", "service"],
                metadata={},
            )
        ],
    )
    store.replace_relations(
        Path("WorkspaceController.java"),
        [
            CodeRelation(
                relation_id="rel-controller-service",
                source_signal_id="sig-endpoint",
                target_name="WorkspaceServiceImpl.list",
                kind="calls",
                confidence=0.9,
                metadata={},
            )
        ],
    )

    bundle = query_repository(repo, "page", config)

    assert any(
        "endpoint signal match" in reason
        for result in bundle.results
        for reason in result.reasons
    )
    assert any(
        "comment signal match" in reason
        for result in bundle.results
        for reason in result.reasons
    )
    assert any(
        "implementation chain match" in reason
        for result in bundle.results
        for reason in result.reasons
    )


def test_legacy_classification_is_per_chunk_in_merged_results(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    content = """class LegacyWorkspaceController {
  // GET /legacy/workspace/list
  String page() { return \"ok\"; }
}\n""" + "\n".join("line-%d" % i for i in range(2, 85)) + """

class LegacyServiceImpl {
  String query() { return \"ok\"; }
}\n""" + "\n".join("line-%d" % i for i in range(86, 170)) + """

class LegacyWorkspaceType {
  String name;
}
"""
    (repo / "LegacyWorkspace.java").write_text(content, encoding="utf-8")
    config = ToolConfig(
        retrieval=RetrievalConfig(
            semantic_top_k=0,
            lexical_top_k=30,
            final_top_k=5,
            context_before_lines=0,
            context_after_lines=0,
        )
    )
    index_repository(repo, config)
    store = SQLiteStore(index_dir_for(repo) / "index.sqlite")

    controller_chunk = store.chunk_for_line(Path("LegacyWorkspace.java"), 3)
    service_chunk = store.chunk_for_line(Path("LegacyWorkspace.java"), 86)
    legacy_chunk = store.chunk_for_line(Path("LegacyWorkspace.java"), 168)

    store.replace_signals(
        Path("LegacyWorkspace.java"),
        [
            CodeSignal(
                signal_id="sig-legacy-endpoint",
                chunk_id=controller_chunk.chunk_id,
                file_path=Path("LegacyWorkspace.java"),
                kind="endpoint",
                name="GET /legacy/workspace/list",
                start_line=3,
                end_line=3,
                language="java",
                tokens=["legacy", "workspace"],
                metadata={"path": "/legacy/workspace/list"},
            ),
            CodeSignal(
                signal_id="sig-service",
                chunk_id=service_chunk.chunk_id,
                file_path=Path("LegacyWorkspace.java"),
                kind="method",
                name="LegacyServiceImpl.query",
                start_line=86,
                end_line=86,
                language="java",
                tokens=["legacy", "service"],
                metadata={},
            ),
            CodeSignal(
                signal_id="sig-legacy-type",
                chunk_id=legacy_chunk.chunk_id,
                file_path=Path("LegacyWorkspace.java"),
                kind="type",
                name="LegacyWorkspaceType",
                start_line=168,
                end_line=168,
                language="java",
                tokens=["legacy", "workspace", "type"],
                metadata={},
            ),
        ],
    )
    store.replace_relations(
        Path("LegacyWorkspace.java"),
        [
            CodeRelation(
                relation_id="rel-endpoint-service",
                source_signal_id="sig-legacy-endpoint",
                target_name="LegacyServiceImpl.query",
                kind="calls",
                confidence=0.9,
                metadata={},
            )
        ],
    )

    bundle = query_repository(repo, "legacy workspace", config)

    assert bundle.results[0].file_path == Path("LegacyWorkspace.java")
    assert bundle.summary.possibly_legacy == ["LegacyWorkspaceType"]
    legacy_result = next(
        result
        for result in bundle.results
        if result.file_path == Path("LegacyWorkspace.java")
    )
    assert any(
        "possibly legacy: no active usage signal found"
        in reason for reason in legacy_result.reasons
    )


def test_query_bundle_summary_construction_defaults_and_explicit(tmp_path: Path) -> None:
    explicit_summary = RetrievalSummary(
        entry_points=["GET /explicit"],
        implementation=["ExplicitService"],
        related_types=["ExplicitDto"],
        possibly_legacy=["ExplicitLegacy"],
    )

    bundle_with_summary = retrieval.QueryBundle(
        query="q",
        expanded_tokens=["q"],
        results=[],
        followup_keywords=["q"],
        summary=explicit_summary,
    )
    assert bundle_with_summary.summary == explicit_summary

    legacy_style_bundle = retrieval.QueryBundle(
        query="q",
        expanded_tokens=["q"],
        results=[],
        followup_keywords=["q"],
    )
    assert legacy_style_bundle.summary == RetrievalSummary()
    assert legacy_style_bundle.results == []


def test_relation_expansion_terminates_cyclic_relations(tmp_path: Path) -> None:
    store = _graph_store(
        tmp_path,
        ["A", "B", "C"],
        [("A", "B", 0.9), ("B", "C", 0.9), ("C", "A", 0.9)],
    )

    candidates = retrieval._relation_expansion_candidates(
        store,
        [_seed_candidate("A")],
        _expansion_config(),
    )

    assert [candidate.chunk_id for candidate in candidates] == ["chunk-B", "chunk-C"]


def test_relation_expansion_stops_at_depth_three(tmp_path: Path) -> None:
    store = _graph_store(
        tmp_path,
        ["A", "B", "C", "D", "E"],
        [("A", "B", 0.9), ("B", "C", 0.9), ("C", "D", 0.9), ("D", "E", 0.9)],
    )

    candidates = retrieval._relation_expansion_candidates(
        store,
        [_seed_candidate("A")],
        _expansion_config(),
    )

    assert [candidate.chunk_id for candidate in candidates] == [
        "chunk-B",
        "chunk-C",
        "chunk-D",
    ]


def test_relation_expansion_filters_low_confidence_relations(tmp_path: Path) -> None:
    store = _graph_store(
        tmp_path,
        ["A", "B", "C"],
        [("A", "B", 0.49), ("A", "C", 0.5)],
    )

    candidates = retrieval._relation_expansion_candidates(
        store,
        [_seed_candidate("A")],
        _expansion_config(),
    )

    assert [candidate.chunk_id for candidate in candidates] == ["chunk-C"]


def test_relation_expansion_logs_when_candidate_limit_is_hit(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    target_names = [
        f"T{index}" for index in range(retrieval.MAX_EXPANSION_CANDIDATES + 5)
    ]
    store = _graph_store(
        tmp_path,
        ["A", *target_names],
        [("A", target, 0.9) for target in target_names],
    )

    caplog.set_level(logging.WARNING, logger=retrieval.__name__)
    candidates = retrieval._relation_expansion_candidates(
        store,
        [_seed_candidate("A")],
        _expansion_config(),
    )

    assert len(candidates) == retrieval.MAX_EXPANSION_CANDIDATES
    assert "relation expansion hit candidate limit" in caplog.text.lower()


def test_relation_expansion_ignores_high_path_symbol_seed_without_signal(
    tmp_path: Path,
) -> None:
    store = _graph_store(
        tmp_path,
        ["Direct", "Seed", "Service", "Executor", "Dto"],
        [("Seed", "Service", 0.5), ("Service", "Executor", 1.0)],
    )
    direct_signal = RetrievalCandidate(
        chunk_id="chunk-Direct",
        score=1.0,
        source="signal",
        score_parts={"signal": 1.0},
    )
    high_path_symbol_seed = RetrievalCandidate(
        chunk_id="chunk-Seed",
        score=10.0,
        source="path_symbol",
        score_parts={"path_symbol": 10.0},
    )
    weak_dto = RetrievalCandidate(
        chunk_id="chunk-Dto",
        score=0.05,
        source="lexical",
        score_parts={"lexical": 0.05},
    )

    relation_candidates = retrieval._relation_expansion_candidates(
        store,
        [direct_signal, high_path_symbol_seed, weak_dto],
        _expansion_config(),
    )
    ranked = retrieval._rank_chunks(
        store,
        retrieval._merge_candidates(
            [direct_signal, high_path_symbol_seed, weak_dto, *relation_candidates]
        ),
        [],
        "workspace",
    )
    scores = {item.chunk.chunk_id: item.score for item in ranked}

    assert relation_candidates == []
    assert "chunk-Service" not in scores
    assert "chunk-Executor" not in scores
    assert scores["chunk-Direct"] > scores["chunk-Dto"]


def test_query_combines_route_tokens_and_ranking_reasons(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "ApplyAuditController.java").write_text(
        '''
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;

@RequestMapping("/apply/audit")
class ApplyAuditController {
  @PostMapping("/pageEs")
  String pageEs() { return "ok"; }
}
'''.strip(),
        encoding="utf-8",
    )
    index_repository(repo, DEFAULT_CONFIG)

    bundle = query_repository(repo, "/apply/audit/pageEs INVOLVED_BY_ME", DEFAULT_CONFIG)

    assert bundle.results
    assert bundle.results[0].file_path == Path("ApplyAuditController.java")
    assert any("route" in reason.lower() or "lexical" in reason.lower() for reason in bundle.results[0].reasons)
    assert "apply" in bundle.followup_keywords


def test_query_context_lines_override_expands_result(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "Service.java").write_text(
        "line1\nline2\nline3 targetToken\nline4\nline5\n",
        encoding="utf-8",
    )
    index_repository(repo, DEFAULT_CONFIG)

    bundle = query_repository(repo, "targetToken", DEFAULT_CONFIG, context_lines=1)

    assert "line2" in bundle.results[0].content
    assert "line4" in bundle.results[0].content


def test_full_file_respects_size_limit(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "Small.java").write_text("class Small { String targetToken; }\n", encoding="utf-8")
    index_repository(repo, DEFAULT_CONFIG)

    bundle = query_repository(repo, "targetToken", DEFAULT_CONFIG, full_file=True)

    assert bundle.results[0].content.startswith("class Small")


def test_full_file_fallback_still_respects_size_limit(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    content = "\n".join(
        [
            "class Large {",
            "  String targetToken = \"" + ("x" * 100) + "\";",
            "}",
        ]
    )
    (repo / "Large.java").write_text(content, encoding="utf-8")
    config = ToolConfig(index=IndexConfig(max_full_file_bytes=64))
    index_repository(repo, config)

    bundle = query_repository(repo, "targetToken", config, full_file=True)

    assert (
        len(bundle.results[0].content.encode("utf-8"))
        <= config.index.max_full_file_bytes
    )
    assert bundle.results[0].content != content


def test_full_file_merged_ranges_still_respect_size_limit(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    lines = ["x" for _ in range(200)]
    lines[0] = "targetToken"
    lines[80] = "targetToken"
    lines[160] = "targetToken"
    (repo / "Large.java").write_text("\n".join(lines), encoding="utf-8")
    config = ToolConfig(index=IndexConfig(max_full_file_bytes=220))
    index_repository(repo, config)

    bundle = query_repository(repo, "targetToken", config, full_file=True)

    assert bundle.results
    assert all(
        len(result.content.encode("utf-8")) <= config.index.max_full_file_bytes
        for result in bundle.results
    )


def test_query_rejects_incompatible_embedding_model(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "Service.java").write_text(
        "class Service { String targetToken; }\n",
        encoding="utf-8",
    )
    index_repository(repo, DEFAULT_CONFIG)
    config = ToolConfig(
        embedding=EmbeddingConfig(provider="hash", model="hash-v2", dimensions=384)
    )

    with pytest.raises(ValueError, match="incompatible"):
        query_repository(repo, "targetToken", config)


def test_query_rejects_incompatible_embedding_dimensions(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "Service.java").write_text(
        "class Service { String targetToken; }\n",
        encoding="utf-8",
    )
    index_repository(repo, DEFAULT_CONFIG)
    config = ToolConfig(
        embedding=EmbeddingConfig(provider="hash", model="hash-v1", dimensions=128)
    )

    with pytest.raises(ValueError, match="incompatible"):
        query_repository(repo, "targetToken", config)


def test_noisy_route_query_keeps_lexical_evidence(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "ApplyAuditController.java").write_text(
        '''
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;

@RequestMapping("/apply/audit")
class ApplyAuditController {
  @PostMapping("/pageEs")
  String pageEs() { return "ok"; }
}
'''.strip(),
        encoding="utf-8",
    )
    index_repository(repo, DEFAULT_CONFIG)

    bundle = query_repository(
        repo,
        "/apply/audit/pageEs why does this leak across regions",
        DEFAULT_CONFIG,
    )

    assert bundle.results[0].file_path == Path("ApplyAuditController.java")
    assert "lexical" in bundle.results[0].score_parts
    assert any("lexical" in reason.lower() for reason in bundle.results[0].reasons)


def test_route_reason_only_applies_to_chunks_with_route_tokens(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "ApplyAuditController.java").write_text(
        '''
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;

@RequestMapping("/apply/audit")
class ApplyAuditController {
  @PostMapping("/pageEs")
  String pageEs() { return "ok"; }
}
'''.strip(),
        encoding="utf-8",
    )
    (repo / "AuditStatus.java").write_text(
        """
enum AuditStatus {
  INVOLVED_BY_ME,
  TOTAL_OVERVIEW
}
""".strip(),
        encoding="utf-8",
    )
    index_repository(repo, DEFAULT_CONFIG)

    bundle = query_repository(repo, "/apply/audit/pageEs INVOLVED_BY_ME", DEFAULT_CONFIG)

    status_result = next(
        result for result in bundle.results if result.file_path == Path("AuditStatus.java")
    )
    assert not any("route" in reason.lower() for reason in status_result.reasons)


def _graph_store(
    tmp_path: Path,
    names: list[str],
    relations: list[tuple[str, str, float]],
) -> SQLiteStore:
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize()
    for name in names:
        path = Path(f"{name}.py")
        chunk = DocumentChunk(
            chunk_id=f"chunk-{name}",
            file_path=path,
            start_line=1,
            end_line=1,
            content=f"def {name.lower()}(): pass",
            chunk_type="symbol",
            symbols=[
                SymbolRef(
                    name=name,
                    kind="function",
                    start_line=1,
                    end_line=1,
                    language="python",
                    metadata={},
                )
            ],
            lexical_tokens=[name.lower()],
            embedding_id=f"chunk-{name}",
            deleted_at=None,
            metadata={"language": "python"},
        )
        signal = CodeSignal(
            signal_id=f"sig-{name}",
            chunk_id=chunk.chunk_id,
            file_path=path,
            kind="method",
            name=name,
            start_line=1,
            end_line=1,
            language="python",
            tokens=[name.lower()],
            metadata={},
        )
        store.replace_chunks(path, [chunk])
        store.replace_signals(path, [signal])

    relations_by_source: dict[str, list[CodeRelation]] = {}
    for source, target, confidence in relations:
        relations_by_source.setdefault(source, []).append(
            CodeRelation(
                relation_id=f"rel-{source}-{target}",
                source_signal_id=f"sig-{source}",
                target_name=target,
                kind="calls",
                confidence=confidence,
                metadata={},
            )
        )
    for source, source_relations in relations_by_source.items():
        store.replace_relations(Path(f"{source}.py"), source_relations)
    return store


def _seed_candidate(name: str) -> RetrievalCandidate:
    return RetrievalCandidate(
        chunk_id=f"chunk-{name}",
        score=1.0,
        source="signal",
        score_parts={"signal": 1.0},
    )


def _expansion_config() -> ToolConfig:
    return ToolConfig(
        retrieval=RetrievalConfig(
            semantic_top_k=0,
            lexical_top_k=20,
            final_top_k=20,
            context_before_lines=0,
            context_after_lines=0,
        )
    )
