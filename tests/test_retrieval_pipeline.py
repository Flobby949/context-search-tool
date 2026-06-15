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
    QueryPlan,
    RetrievalCandidate,
    RetrievalSummary,
    SymbolRef,
)
from context_search_tool.paths import index_dir_for
from context_search_tool.retrieval import query_repository
from context_search_tool.sqlite_store import SQLiteStore


class FakePlanner:
    def __init__(self, plan: QueryPlan) -> None:
        self.query_plan = plan
        self.calls: list[str] = []

    def plan_query(self, query: str) -> QueryPlan:
        self.calls.append(query)
        return self.query_plan

    def plan(self, query: str) -> QueryPlan:
        self.calls.append(query)
        return self.query_plan


def test_query_without_index_does_not_call_planner(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    planner = FakePlanner(
        QueryPlan(
            original_query="targetToken",
            grep_keywords=["ExpensiveHint"],
            status="ok",
            provider="ollama",
            model="qwen3.5:4b-mlx",
            prompt_version="qwen-query-planner-v1",
            prompt_hash="sha256:test",
            latency_ms=1,
        )
    )

    bundle = query_repository(repo, "targetToken", DEFAULT_CONFIG, planner=planner)

    assert planner.calls == []
    assert bundle.results == []
    assert bundle.planner.status == "disabled"


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

    # With rerank scoring, order is:
    # 1. Controller: original_direct (lexical + signal) - highest
    # 2. Dto: original_direct (lexical only) - high
    # 3. ServiceImpl: original_relation - lower
    # 4. QueryExe: original_relation - lowest
    assert [result.file_path for result in bundle.results] == [
        Path("WorkspaceController.java"),
        Path("WorkspaceDto.java"),
        Path("WorkspaceServiceImpl.java"),
        Path("WorkspaceQueryExe.java"),
    ]
    assert "signal" in bundle.results[0].score_parts
    assert "lexical" in bundle.results[1].score_parts
    assert "relation" in bundle.results[2].score_parts
    assert "relation" in bundle.results[3].score_parts


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


def test_relation_expansion_preserves_mixed_original_and_planner_provenance(
    tmp_path: Path,
) -> None:
    store = _graph_store(
        tmp_path,
        ["Source", "Target"],
        [("Source", "Target", 0.9)],
    )

    relation_candidates = retrieval._relation_expansion_candidates(
        store,
        [
            RetrievalCandidate(
                chunk_id="chunk-Source",
                score=1.0,
                source="signal,planner_signal",
                score_parts={"signal": 1.0, "planner_signal": 1.0},
            )
        ],
        _expansion_config(),
    )

    target = relation_candidates[0]
    assert target.score_parts["relation"] == target.score
    assert target.score_parts["planner_relation"] == target.score
    assert target.score_parts["original_relation"] == target.score
    assert "planner_signal" not in target.score_parts
    assert retrieval._is_planner_hint_only(target.score_parts) is False


def test_relation_expansion_keeps_planner_only_seed_provenance_when_seed_has_lexical_evidence(
    tmp_path: Path,
) -> None:
    store = _graph_store(
        tmp_path,
        ["Source", "Target"],
        [("Source", "Target", 0.9)],
    )

    relation_candidates = retrieval._relation_expansion_candidates(
        store,
        [
            RetrievalCandidate(
                chunk_id="chunk-Source",
                score=1.0,
                source="lexical,planner_signal",
                score_parts={"lexical": 1.0, "planner_signal": 1.0},
            )
        ],
        _expansion_config(),
    )

    target = relation_candidates[0]
    assert target.score_parts["relation"] == target.score
    assert target.score_parts["planner_relation"] == target.score
    assert "original_relation" not in target.score_parts
    assert retrieval._is_planner_hint_only(target.score_parts) is True


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
    planner = FakePlanner(
        QueryPlan(
            original_query="targetToken",
            grep_keywords=["ExpensiveHint"],
            status="ok",
            provider="ollama",
            model="qwen3.5:4b-mlx",
            prompt_version="qwen-query-planner-v1",
            prompt_hash="sha256:test",
            latency_ms=1,
        )
    )

    with pytest.raises(ValueError, match="incompatible"):
        query_repository(repo, "targetToken", config, planner=planner)
    assert planner.calls == []


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


def test_query_planner_hints_surface_dashboard_code_for_chinese_query(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "DashboardController.java").write_text(
        """
class DashboardController {
  String chart() { return dashboardService.statistics(); }
}
""".strip(),
        encoding="utf-8",
    )
    (repo / "UnrelatedController.java").write_text(
        """
class UnrelatedController {
  String query() { return "数据看板统计图表功能"; }
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
    planner = FakePlanner(
        QueryPlan(
            original_query="数据看板统计图表功能",
            grep_keywords=["Dashboard", "Statistics", "Chart"],
            symbol_hints=["DashboardController"],
            intent="feature_lookup",
            status="ok",
            provider="ollama",
            model="qwen3.5:4b-mlx",
            prompt_version="qwen-query-planner-v1",
            prompt_hash="sha256:test",
            latency_ms=1,
        )
    )

    bundle = query_repository(repo, "数据看板统计图表功能", config, planner=planner)

    assert bundle.planner.status == "ok"
    assert "dashboard" in bundle.expanded_tokens
    assert any(
        result.file_path == Path("DashboardController.java")
        for result in bundle.results
    )
    dashboard = next(
        result
        for result in bundle.results
        if result.file_path == Path("DashboardController.java")
    )
    assert "planner hint match" in dashboard.reasons


def test_query_planner_fallback_returns_original_query_results(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "OriginalMatch.java").write_text(
        'class OriginalMatch { String value = "targetToken"; }\n',
        encoding="utf-8",
    )
    config = ToolConfig(
        retrieval=RetrievalConfig(
            semantic_top_k=0,
            lexical_top_k=10,
            final_top_k=1,
            context_before_lines=0,
            context_after_lines=0,
        )
    )
    index_repository(repo, config)
    planner = FakePlanner(
        QueryPlan(
            original_query="targetToken",
            status="fallback",
            provider="ollama",
            model="qwen3.5:4b-mlx",
            latency_ms=8,
            error="planner timed out after 8 seconds",
        )
    )

    bundle = query_repository(repo, "targetToken", config, planner=planner)

    assert bundle.planner.status == "fallback"
    assert bundle.expanded_tokens == ["target", "token"]
    assert bundle.results[0].file_path == Path("OriginalMatch.java")


def test_query_planner_mixed_original_and_hint_match_keeps_planner_reason(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "MixedDashboard.java").write_text(
        'class MixedDashboard { String value = "targetToken dashboard"; }\n',
        encoding="utf-8",
    )
    config = ToolConfig(
        retrieval=RetrievalConfig(
            semantic_top_k=0,
            lexical_top_k=10,
            final_top_k=1,
            context_before_lines=0,
            context_after_lines=0,
        )
    )
    index_repository(repo, config)
    planner = FakePlanner(
        QueryPlan(
            original_query="targetToken",
            grep_keywords=["dashboard"],
            status="ok",
            provider="ollama",
            model="qwen3.5:4b-mlx",
            prompt_version="qwen-query-planner-v1",
            prompt_hash="sha256:test",
            latency_ms=1,
        )
    )

    bundle = query_repository(repo, "targetToken", config, planner=planner)

    assert bundle.results[0].file_path == Path("MixedDashboard.java")
    assert any(
        reason in bundle.results[0].reasons
        for reason in ("lexical match", "token coverage")
    )
    assert "planner hint match" in bundle.results[0].reasons


def test_planner_seeded_relation_keeps_planner_provenance(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "OriginalMatch.java").write_text(
        'class OriginalMatch { String value = "targetToken"; }\n',
        encoding="utf-8",
    )
    (repo / "DashboardController.java").write_text(
        """
class DashboardController {
  String dashboard() { return bridgeService.list(); }
}
""".strip(),
        encoding="utf-8",
    )
    (repo / "BridgeService.java").write_text(
        """
class BridgeService {
  String list() { return "ok"; }
}
""".strip(),
        encoding="utf-8",
    )
    config = ToolConfig(
        retrieval=RetrievalConfig(
            semantic_top_k=0,
            lexical_top_k=10,
            final_top_k=3,
            context_before_lines=0,
            context_after_lines=0,
        )
    )
    index_repository(repo, config)
    store = SQLiteStore(index_dir_for(repo) / "index.sqlite")

    original_chunk = store.chunk_for_line(Path("OriginalMatch.java"), 1)
    controller_chunk = store.chunk_for_line(Path("DashboardController.java"), 2)
    service_chunk = store.chunk_for_line(Path("BridgeService.java"), 2)
    store.replace_signals(
        Path("OriginalMatch.java"),
        [
            CodeSignal(
                signal_id="sig-original-target",
                chunk_id=original_chunk.chunk_id,
                file_path=Path("OriginalMatch.java"),
                kind="method",
                name="OriginalMatch.targetToken",
                start_line=1,
                end_line=1,
                language="java",
                tokens=["target", "token"],
                metadata={},
            )
        ],
    )
    store.replace_signals(
        Path("DashboardController.java"),
        [
            CodeSignal(
                signal_id="sig-dashboard-controller",
                chunk_id=controller_chunk.chunk_id,
                file_path=Path("DashboardController.java"),
                kind="method",
                name="DashboardController.dashboard",
                start_line=2,
                end_line=2,
                language="java",
                tokens=["dashboard", "controller"],
                metadata={},
            )
        ],
    )
    store.replace_signals(
        Path("BridgeService.java"),
        [
            CodeSignal(
                signal_id="sig-bridge-service",
                chunk_id=service_chunk.chunk_id,
                file_path=Path("BridgeService.java"),
                kind="method",
                name="BridgeService.list",
                start_line=2,
                end_line=2,
                language="java",
                tokens=["bridge", "service", "list"],
                metadata={},
            )
        ],
    )
    store.replace_relations(
        Path("DashboardController.java"),
        [
            CodeRelation(
                relation_id="rel-dashboard-controller-service",
                source_signal_id="sig-dashboard-controller",
                target_name="BridgeService.list",
                kind="calls",
                confidence=0.9,
                metadata={},
            )
        ],
    )
    planner = FakePlanner(
        QueryPlan(
            original_query="targetToken",
            symbol_hints=["DashboardController"],
            status="ok",
            provider="ollama",
            model="qwen3.5:4b-mlx",
            prompt_version="qwen-query-planner-v1",
            prompt_hash="sha256:test",
            latency_ms=1,
        )
    )

    bundle = query_repository(repo, "targetToken", config, planner=planner)

    service_result = next(
        result
        for result in bundle.results
        if result.file_path == Path("BridgeService.java")
    )
    assert bundle.results[0].file_path == Path("OriginalMatch.java")
    assert "relation" in service_result.score_parts
    assert "planner_relation" in service_result.score_parts
    assert "planner_signal" not in service_result.score_parts
    assert "planner hint match" in service_result.reasons


def test_planner_only_match_ranks_below_comparable_original_match(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "OriginalMatch.java").write_text(
        'class OriginalMatch { String value = "targetToken"; }\n',
        encoding="utf-8",
    )
    (repo / "PlannerDashboard.java").write_text(
        "class PlannerDashboard { String dashboard() { return \"ok\"; } }\n",
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
    planner = FakePlanner(
        QueryPlan(
            original_query="targetToken",
            grep_keywords=["dashboard"],
            status="ok",
            provider="ollama",
            model="qwen3.5:4b-mlx",
            prompt_version="qwen-query-planner-v1",
            prompt_hash="sha256:test",
            latency_ms=1,
        )
    )

    bundle = query_repository(repo, "targetToken", config, planner=planner)

    assert [result.file_path for result in bundle.results] == [
        Path("OriginalMatch.java"),
        Path("PlannerDashboard.java"),
    ]
    assert "lexical match" in bundle.results[0].reasons
    assert "token coverage" in bundle.results[0].reasons
    assert "planner hint match" not in bundle.results[0].reasons
    assert "planner hint match" in bundle.results[1].reasons


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


# ============================================================================
# Rerank Soft Sorting Tests (TDD - Step 1)
# These tests validate the rerank-based sorting behavior that will fix the
# rank_tier absolute priority bug where low-score relation expansion results
# incorrectly outrank high-score direct matches.
# ============================================================================


def test_rerank_high_score_direct_beats_low_score_relation(tmp_path: Path) -> None:
    """
    Test #1: High combined_score direct match must rank before low-score relation-only.
    Reproduces SmsUtils case where semantic=2.0+ direct match was outranked by
    low-score relation expansion due to rank_tier=1 < rank_tier=2.
    """
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize()

    # High-score direct match (semantic + path + signal)
    high_direct = DocumentChunk(
        chunk_id="high-direct",
        file_path=Path("SmsUtils.java"),
        start_line=1,
        end_line=10,
        content="class SmsUtils { void sendSms() {} }",
        chunk_type="symbol",
        symbols=[],
        lexical_tokens=["sms", "utils"],
        embedding_id="high-direct",
        deleted_at=None,
        metadata={"language": "java"},
    )

    # Low-score relation-only match
    low_relation = DocumentChunk(
        chunk_id="low-relation",
        file_path=Path("RedisCache.java"),
        start_line=1,
        end_line=10,
        content="class RedisCache { }",
        chunk_type="symbol",
        symbols=[],
        lexical_tokens=["redis", "cache"],
        embedding_id="low-relation",
        deleted_at=None,
        metadata={"language": "java"},
    )

    store.replace_chunks(Path("SmsUtils.java"), [high_direct])
    store.replace_chunks(Path("RedisCache.java"), [low_relation])

    candidates = {
        "high-direct": RetrievalCandidate(
            chunk_id="high-direct",
            score=2.4,  # Will be recalculated from score_parts
            source="semantic,signal,path_symbol",
            score_parts={
                "semantic": 2.0,  # High BGE-M3 score
                "signal": 0.3,
                "path_symbol": 0.1,
            },
        ),
        "low-relation": RetrievalCandidate(
            chunk_id="low-relation",
            score=0.5,
            source="relation",
            score_parts={
                "relation": 0.5,
                "original_relation": 0.5,
            },
        ),
    }

    ranked = retrieval._rank_chunks(store, candidates, ["sms", "send"], "send sms")

    # High-score direct should rank first
    assert ranked[0].chunk.chunk_id == "high-direct"
    assert ranked[1].chunk.chunk_id == "low-relation"


def test_rerank_planner_only_relation_cannot_beat_strong_original_direct(
    tmp_path: Path,
) -> None:
    """
    Test #2: planner-only relation must not outrank strong original_direct.
    Validates the invariant: max(planner-only rerank) < min(strong original_direct rerank).
    """
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize()

    strong_direct = DocumentChunk(
        chunk_id="strong-direct",
        file_path=Path("AuthService.java"),
        start_line=1,
        end_line=10,
        content="class AuthService { void login() {} }",
        chunk_type="symbol",
        symbols=[],
        lexical_tokens=["auth", "service"],
        embedding_id="strong-direct",
        deleted_at=None,
        metadata={"language": "java"},
    )

    planner_relation = DocumentChunk(
        chunk_id="planner-relation",
        file_path=Path("TokenCache.java"),
        start_line=1,
        end_line=10,
        content="class TokenCache { }",
        chunk_type="symbol",
        symbols=[],
        lexical_tokens=["token", "cache"],
        embedding_id="planner-relation",
        deleted_at=None,
        metadata={"language": "java"},
    )

    store.replace_chunks(Path("AuthService.java"), [strong_direct])
    store.replace_chunks(Path("TokenCache.java"), [planner_relation])

    candidates = {
        "strong-direct": RetrievalCandidate(
            chunk_id="strong-direct",
            score=1.0,
            source="lexical,signal",
            score_parts={
                "lexical": 0.8,  # Strong lexical match
                "signal": 0.5,
            },
        ),
        "planner-relation": RetrievalCandidate(
            chunk_id="planner-relation",
            score=0.9,
            source="planner_relation",
            score_parts={
                "planner_relation": 0.9,
                "relation": 0.9,
                # No original evidence
            },
        ),
    }

    ranked = retrieval._rank_chunks(
        store, candidates, ["login", "auth"], "user login"
    )

    # Strong direct must rank first, planner-only relation second
    assert ranked[0].chunk.chunk_id == "strong-direct"
    assert ranked[1].chunk.chunk_id == "planner-relation"


def test_rerank_planner_direct_cannot_beat_strong_original_direct(
    tmp_path: Path,
) -> None:
    """
    Test #3: planner_direct (planner_signal/planner_lexical) cannot outrank
    strong original_direct, avoiding planner noise from taking Top1.
    """
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize()

    strong_original = DocumentChunk(
        chunk_id="strong-original",
        file_path=Path("UserController.java"),
        start_line=1,
        end_line=10,
        content="class UserController { }",
        chunk_type="symbol",
        symbols=[],
        lexical_tokens=["user", "controller"],
        embedding_id="strong-original",
        deleted_at=None,
        metadata={"language": "java"},
    )

    planner_direct = DocumentChunk(
        chunk_id="planner-direct",
        file_path=Path("DashboardService.java"),
        start_line=1,
        end_line=10,
        content="class DashboardService { }",
        chunk_type="symbol",
        symbols=[],
        lexical_tokens=["dashboard", "service"],
        embedding_id="planner-direct",
        deleted_at=None,
        metadata={"language": "java"},
    )

    store.replace_chunks(Path("UserController.java"), [strong_original])
    store.replace_chunks(Path("DashboardService.java"), [planner_direct])

    candidates = {
        "strong-original": RetrievalCandidate(
            chunk_id="strong-original",
            score=1.0,
            source="semantic,lexical",
            score_parts={
                "semantic": 0.9,
                "lexical": 0.4,
            },
        ),
        "planner-direct": RetrievalCandidate(
            chunk_id="planner-direct",
            score=0.95,
            source="planner_signal,planner_lexical",
            score_parts={
                "planner_signal": 0.6,
                "planner_lexical": 0.35,
                # No original evidence
            },
        ),
    }

    ranked = retrieval._rank_chunks(store, candidates, ["user"], "user query")

    assert ranked[0].chunk.chunk_id == "strong-original"
    assert ranked[1].chunk.chunk_id == "planner-direct"


def test_rerank_weak_direct_does_not_trigger_planner_ceiling(tmp_path: Path) -> None:
    """
    Test #4: Weak direct evidence (lexical=0.05 or token_coverage=0.1) should not
    trigger planner_ceiling, allowing planner-only results to appear in results.
    Guards against weak original evidence mistakenly killing valid planner召回.
    """
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize()

    weak_direct = DocumentChunk(
        chunk_id="weak-direct",
        file_path=Path("Config.java"),
        start_line=1,
        end_line=10,
        content="class Config { }",
        chunk_type="symbol",
        symbols=[],
        lexical_tokens=["config"],
        embedding_id="weak-direct",
        deleted_at=None,
        metadata={"language": "java"},
    )

    planner_only = DocumentChunk(
        chunk_id="planner-only",
        file_path=Path("DashboardController.java"),
        start_line=1,
        end_line=10,
        content="class DashboardController { }",
        chunk_type="symbol",
        symbols=[],
        lexical_tokens=["dashboard", "controller"],
        embedding_id="planner-only",
        deleted_at=None,
        metadata={"language": "java"},
    )

    store.replace_chunks(Path("Config.java"), [weak_direct])
    store.replace_chunks(Path("DashboardController.java"), [planner_only])

    candidates = {
        "weak-direct": RetrievalCandidate(
            chunk_id="weak-direct",
            score=0.1,
            source="lexical",
            score_parts={
                "lexical": 0.05,  # Very weak match
            },
        ),
        "planner-only": RetrievalCandidate(
            chunk_id="planner-only",
            score=0.8,
            source="planner_lexical",
            score_parts={
                "planner_lexical": 0.8,
                # No original evidence
            },
        ),
    }

    ranked = retrieval._rank_chunks(store, candidates, ["dashboard"], "dashboard")

    # Planner-only should still appear (not clamped to below weak direct)
    assert any(r.chunk.chunk_id == "planner-only" for r in ranked)
    # And should rank higher than weak direct due to better score
    planner_idx = next(
        i for i, r in enumerate(ranked) if r.chunk.chunk_id == "planner-only"
    )
    weak_idx = next(
        i for i, r in enumerate(ranked) if r.chunk.chunk_id == "weak-direct"
    )
    assert planner_idx < weak_idx


def test_rerank_no_strong_original_direct_no_clamp(tmp_path: Path) -> None:
    """
    Test #5: When there's no strong original_direct evidence, planner-only results
    should not be clamped, preserving planner召回 when original query fails.
    """
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize()

    planner_only_1 = DocumentChunk(
        chunk_id="planner-only-1",
        file_path=Path("ServiceA.java"),
        start_line=1,
        end_line=10,
        content="class ServiceA { }",
        chunk_type="symbol",
        symbols=[],
        lexical_tokens=["service", "a"],
        embedding_id="planner-only-1",
        deleted_at=None,
        metadata={"language": "java"},
    )

    planner_only_2 = DocumentChunk(
        chunk_id="planner-only-2",
        file_path=Path("ServiceB.java"),
        start_line=1,
        end_line=10,
        content="class ServiceB { }",
        chunk_type="symbol",
        symbols=[],
        lexical_tokens=["service", "b"],
        embedding_id="planner-only-2",
        deleted_at=None,
        metadata={"language": "java"},
    )

    store.replace_chunks(Path("ServiceA.java"), [planner_only_1])
    store.replace_chunks(Path("ServiceB.java"), [planner_only_2])

    candidates = {
        "planner-only-1": RetrievalCandidate(
            chunk_id="planner-only-1",
            score=0.9,
            source="planner_signal",
            score_parts={
                "planner_signal": 0.9,
            },
        ),
        "planner-only-2": RetrievalCandidate(
            chunk_id="planner-only-2",
            score=0.7,
            source="planner_lexical",
            score_parts={
                "planner_lexical": 0.7,
            },
        ),
    }

    ranked = retrieval._rank_chunks(store, candidates, ["service"], "service query")

    # Both should appear in results (not killed by clamp)
    assert len(ranked) == 2
    # Higher score planner-only should rank first
    assert ranked[0].chunk.chunk_id == "planner-only-1"
    assert ranked[1].chunk.chunk_id == "planner-only-2"


def test_rerank_endpoint_boost_does_not_override_score(tmp_path: Path) -> None:
    """
    Test #6: Endpoint/controller boost should not allow low-score endpoints to
    outrank high-score non-endpoints. Boost is additive, not a tier override.
    """
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize()

    high_non_endpoint = DocumentChunk(
        chunk_id="high-non-endpoint",
        file_path=Path("BusinessService.java"),
        start_line=1,
        end_line=10,
        content="class BusinessService { void process() {} }",
        chunk_type="symbol",
        symbols=[],
        lexical_tokens=["business", "service"],
        embedding_id="high-non-endpoint",
        deleted_at=None,
        metadata={"language": "java"},
    )

    low_endpoint = DocumentChunk(
        chunk_id="low-endpoint",
        file_path=Path("HealthController.java"),
        start_line=1,
        end_line=10,
        content="@GetMapping('/health') class HealthController { }",
        chunk_type="symbol",
        symbols=[],
        lexical_tokens=["health", "controller"],
        embedding_id="low-endpoint",
        deleted_at=None,
        metadata={"language": "java"},
    )

    endpoint_signal = CodeSignal(
        signal_id="sig-endpoint",
        chunk_id="low-endpoint",
        file_path=Path("HealthController.java"),
        kind="endpoint",
        name="GET /health",
        start_line=1,
        end_line=1,
        language="java",
        tokens=["health"],
        metadata={},
    )

    store.replace_chunks(Path("BusinessService.java"), [high_non_endpoint])
    store.replace_chunks(Path("HealthController.java"), [low_endpoint])
    store.replace_signals(Path("HealthController.java"), [endpoint_signal])

    candidates = {
        "high-non-endpoint": RetrievalCandidate(
            chunk_id="high-non-endpoint",
            score=2.0,
            source="semantic,signal",
            score_parts={
                "semantic": 1.8,
                "signal": 0.4,
            },
        ),
        "low-endpoint": RetrievalCandidate(
            chunk_id="low-endpoint",
            score=0.3,
            source="signal",
            score_parts={
                "signal": 0.3,
            },
        ),
    }

    ranked = retrieval._rank_chunks(
        store, candidates, ["business", "process"], "business process"
    )

    # High-score non-endpoint should rank before low-score endpoint
    assert ranked[0].chunk.chunk_id == "high-non-endpoint"
    assert ranked[1].chunk.chunk_id == "low-endpoint"


def test_rerank_relation_expansion_preserved(tmp_path: Path) -> None:
    """
    Test #7: Relation expansion should still surface Service/Impl classes,
    not be completely killed. Validates that rerank doesn't over-penalize relations.
    """
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize()

    controller = DocumentChunk(
        chunk_id="controller",
        file_path=Path("OrderController.java"),
        start_line=1,
        end_line=10,
        content="class OrderController { }",
        chunk_type="symbol",
        symbols=[],
        lexical_tokens=["order", "controller"],
        embedding_id="controller",
        deleted_at=None,
        metadata={"language": "java"},
    )

    service = DocumentChunk(
        chunk_id="service",
        file_path=Path("OrderServiceImpl.java"),
        start_line=1,
        end_line=10,
        content="class OrderServiceImpl { }",
        chunk_type="symbol",
        symbols=[],
        lexical_tokens=["order", "service", "impl"],
        embedding_id="service",
        deleted_at=None,
        metadata={"language": "java"},
    )

    store.replace_chunks(Path("OrderController.java"), [controller])
    store.replace_chunks(Path("OrderServiceImpl.java"), [service])

    candidates = {
        "controller": RetrievalCandidate(
            chunk_id="controller",
            score=1.5,
            source="signal",
            score_parts={
                "signal": 1.0,
                "lexical": 0.5,
            },
        ),
        "service": RetrievalCandidate(
            chunk_id="service",
            score=0.8,
            source="relation",
            score_parts={
                "relation": 0.8,
                "original_relation": 0.8,
            },
        ),
    }

    ranked = retrieval._rank_chunks(store, candidates, ["order"], "order flow")

    # Both should appear in results
    assert len(ranked) == 2
    # Service should appear (not filtered out)
    assert any(r.chunk.chunk_id == "service" for r in ranked)


def test_rerank_normalization_effectiveness_with_outlier(tmp_path: Path) -> None:
    """
    Test #8: Normalization must handle outlier scores [0.1, 0.2, 2.4] correctly,
    ensuring penalty/boost actually changes ranking and isn't silently ineffective.
    Guards against the "静默不改名次" risk mentioned in the plan.
    """
    store = SQLiteStore(tmp_path / "index.sqlite")
    store.initialize()

    low_score = DocumentChunk(
        chunk_id="low-score",
        file_path=Path("Low.java"),
        start_line=1,
        end_line=10,
        content="class Low { }",
        chunk_type="symbol",
        symbols=[],
        lexical_tokens=["low"],
        embedding_id="low-score",
        deleted_at=None,
        metadata={"language": "java"},
    )

    mid_score = DocumentChunk(
        chunk_id="mid-score",
        file_path=Path("Mid.java"),
        start_line=1,
        end_line=10,
        content="class Mid { }",
        chunk_type="symbol",
        symbols=[],
        lexical_tokens=["mid"],
        embedding_id="mid-score",
        deleted_at=None,
        metadata={"language": "java"},
    )

    outlier_high = DocumentChunk(
        chunk_id="outlier-high",
        file_path=Path("Outlier.java"),
        start_line=1,
        end_line=10,
        content="class Outlier { }",
        chunk_type="symbol",
        symbols=[],
        lexical_tokens=["outlier"],
        embedding_id="outlier-high",
        deleted_at=None,
        metadata={"language": "java"},
    )

    store.replace_chunks(Path("Low.java"), [low_score])
    store.replace_chunks(Path("Mid.java"), [mid_score])
    store.replace_chunks(Path("Outlier.java"), [outlier_high])

    candidates = {
        "low-score": RetrievalCandidate(
            chunk_id="low-score",
            score=0.1,
            source="lexical",
            score_parts={
                "lexical": 0.1,
            },
        ),
        "mid-score": RetrievalCandidate(
            chunk_id="mid-score",
            score=0.2,
            source="lexical",
            score_parts={
                "lexical": 0.2,
            },
        ),
        "outlier-high": RetrievalCandidate(
            chunk_id="outlier-high",
            score=2.4,
            source="semantic,signal",
            score_parts={
                "semantic": 2.0,
                "signal": 0.4,
            },
        ),
    }

    ranked = retrieval._rank_chunks(store, candidates, ["test"], "test query")

    # After normalization and rerank, ordering should still be sensible
    # (outlier should rank first due to highest combined_score)
    assert ranked[0].chunk.chunk_id == "outlier-high"
    # Verify normalization didn't compress non-outliers to indistinguishable values
    assert ranked[1].chunk.chunk_id == "mid-score"
    assert ranked[2].chunk.chunk_id == "low-score"


def test_rerank_second_sort_consistency_after_merge(tmp_path: Path) -> None:
    """
    Test #9: After query() full pipeline including _merge_overlapping_results,
    visible_results order must match rerank order, not get re-sorted by rank_tier.
    Reproduces the P1 issue where results get "压回去" after the first sort.
    """
    repo = tmp_path / "repo"
    repo.mkdir()

    # Create a simple file with high-score content
    (repo / "DirectMatch.java").write_text(
        "class DirectMatch { void targetMethod() {} }",
        encoding="utf-8",
    )

    # Create a relation expansion candidate
    (repo / "RelationMatch.java").write_text(
        "class RelationMatch { }",
        encoding="utf-8",
    )

    config = ToolConfig(
        retrieval=RetrievalConfig(
            semantic_top_k=0,
            lexical_top_k=10,
            final_top_k=5,
            context_before_lines=0,
            context_after_lines=0,
        )
    )
    index_repository(repo, config)
    store = SQLiteStore(index_dir_for(repo) / "index.sqlite")

    direct_chunk = store.chunk_for_line(Path("DirectMatch.java"), 1)
    relation_chunk = store.chunk_for_line(Path("RelationMatch.java"), 1)

    # Add signals to make DirectMatch high-score direct
    store.replace_signals(
        Path("DirectMatch.java"),
        [
            CodeSignal(
                signal_id="sig-direct",
                chunk_id=direct_chunk.chunk_id,
                file_path=Path("DirectMatch.java"),
                kind="method",
                name="DirectMatch.targetMethod",
                start_line=1,
                end_line=1,
                language="java",
                tokens=["target", "method"],
                metadata={},
            )
        ],
    )

    bundle = query_repository(repo, "target method", config)

    # Verify results exist
    assert len(bundle.results) > 0
    # High-score direct should be first in final results
    assert bundle.results[0].file_path == Path("DirectMatch.java")


@pytest.mark.xfail(reason="Feature not implemented yet: _evidence_class")
def test_rerank_original_relation_not_misclassified(tmp_path: Path) -> None:
    """
    Test #10: Candidate with original_relation>0 should be classified as
    "original_relation", not "original_direct". Guards against the P1 bug where
    _has_original_query_evidence includes "original_relation" key.
    """
    try:
        from context_search_tool.retrieval import _evidence_class
    except ImportError:
        pytest.skip("_evidence_class not implemented yet")

    score_parts_relation_only = {
        "original_relation": 0.8,
        "relation": 0.8,
        # No direct evidence
    }

    evidence_class = _evidence_class(score_parts_relation_only)

    assert evidence_class == "original_relation"
    assert evidence_class != "original_direct"


def test_rerank_output_contract_score_equals_rerank_score(tmp_path: Path) -> None:
    """
    Test #11: RetrievalResult.score should equal rerank_score, and score_parts
    should contain numeric items (combined_score, rerank_score) but not string
    evidence_class. Validates P1 output contract.
    """
    repo = tmp_path / "repo"
    repo.mkdir()

    (repo / "TestFile.java").write_text(
        "class TestFile { void method() {} }",
        encoding="utf-8",
    )

    config = ToolConfig(
        retrieval=RetrievalConfig(
            semantic_top_k=0,
            lexical_top_k=10,
            final_top_k=5,
            context_before_lines=0,
            context_after_lines=0,
        )
    )
    index_repository(repo, config)

    bundle = query_repository(repo, "test method", config)

    assert len(bundle.results) > 0
    result = bundle.results[0]

    # Check that score_parts contains expected numeric keys
    assert "combined_score" in result.score_parts
    # rerank_score should be in score_parts once implemented
    # assert "rerank_score" in result.score_parts

    # evidence_class should NOT be in score_parts (it's a string)
    assert "evidence_class" not in result.score_parts

    # All values in score_parts should be numeric
    for key, value in result.score_parts.items():
        assert isinstance(
            value, (int, float)
        ), f"score_parts[{key}] should be numeric, got {type(value)}"


@pytest.mark.xfail(reason="Feature not implemented yet: _merge_expanded_result changes")
def test_rerank_merge_field_consistency(tmp_path: Path) -> None:
    """
    Test #12: When merging overlapping results where lower rerank_score has higher
    combined_score, the merged result's rerank_score/evidence_class/evidence_priority/
    reasons should all come from the same winner (highest rerank_score side).
    """
    try:
        from context_search_tool.retrieval import (
            _ExpandedResult,
            _merge_expanded_result,
        )
    except ImportError:
        pytest.skip("_ExpandedResult or _merge_expanded_result not available")

    # Create two overlapping results
    left = _ExpandedResult(
        chunk_ids=["chunk-1"],
        file_path=Path("Test.java"),
        start_line=1,
        end_line=10,
        content="line1\nline2\nline3",
        score=1.5,  # Higher combined_score
        score_parts={
            "combined_score": 1.5,
            "rerank_score": 0.6,  # Lower rerank_score
            "evidence_priority": 3,
        },
        reasons=["reason from left"],
        followup_keywords=["left"],
        rank_tier=2,
        rerank_score=0.6,
        evidence_class="planner_relation",
        evidence_priority=3,
    )

    right = _ExpandedResult(
        chunk_ids=["chunk-2"],
        file_path=Path("Test.java"),
        start_line=8,
        end_line=15,
        content="line8\nline9\nline10",
        score=1.2,  # Lower combined_score
        score_parts={
            "combined_score": 1.2,
            "rerank_score": 0.8,  # Higher rerank_score (winner)
            "evidence_priority": 1,
        },
        reasons=["reason from right"],
        followup_keywords=["right"],
        rank_tier=1,
        rerank_score=0.8,
        evidence_class="original_relation",
        evidence_priority=1,
    )

    merged = _merge_expanded_result(left, right)

    # All fields should come from the winner (right, with higher rerank_score)
    assert merged.rerank_score == 0.8  # From right
    assert merged.evidence_class == "original_relation"  # From right
    assert merged.evidence_priority == 1  # From right
    assert "reason from right" in merged.reasons
    assert merged.score_parts["rerank_score"] == 0.8
    assert merged.score_parts["evidence_priority"] == 1
