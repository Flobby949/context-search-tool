from pathlib import Path

from context_search_tool.config import RetrievalConfig, ToolConfig
from context_search_tool.indexer import index_repository
from context_search_tool.models import CodeRelation, CodeSignal
from context_search_tool.paths import index_dir_for
from context_search_tool.retrieval import query_repository
from context_search_tool.sqlite_store import SQLiteStore

# Strong direct text match threshold (filters weak matches)
MIN_STRONG_DIRECT_TEXT_SCORE = 0.60


def _direct_text_config(final_top_k: int = 5) -> ToolConfig:
    return ToolConfig(
        retrieval=RetrievalConfig(
            semantic_top_k=0,
            lexical_top_k=0,
            final_top_k=final_top_k,
            context_before_lines=0,
            context_after_lines=0,
        )
    )


def _create_test_signal(
    store: SQLiteStore,
    file_path: Path,
    signal_id: str,
    chunk_id: str,
    name: str,
    start_line: int,
    end_line: int,
    tokens: list[str],
) -> None:
    """Helper to create a test code signal in the store."""
    store.replace_signals(
        file_path,
        [
            CodeSignal(
                signal_id=signal_id,
                chunk_id=chunk_id,
                file_path=file_path,
                kind="method",
                name=name,
                start_line=start_line,
                end_line=end_line,
                language="java",
                tokens=tokens,
                metadata={},
            )
        ],
    )


def _create_test_relation(
    store: SQLiteStore,
    file_path: Path,
    relation_id: str,
    source_signal_id: str,
    target_name: str,
    confidence: float,
) -> None:
    """Helper to create a test code relation in the store."""
    store.replace_relations(
        file_path,
        [
            CodeRelation(
                relation_id=relation_id,
                source_signal_id=source_signal_id,
                target_name=target_name,
                kind="calls",
                confidence=confidence,
                metadata={},
            )
        ],
    )


def test_direct_text_matches_cjk_comment_without_semantic_or_fts(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "approval.py").write_text(
        "\n".join(
            [
                "def unrelated():",
                "    return None",
                "",
                "# 当前审批人查询接口",
                "def current_auditor():",
                "    return 'ok'",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    config = _direct_text_config(final_top_k=1)
    index_repository(repo, config)

    bundle = query_repository(repo, "当前审批人查询接口", config)

    assert [result.file_path for result in bundle.results] == [Path("approval.py")]
    parts = bundle.results[0].score_parts
    assert parts["direct_text"] >= MIN_STRONG_DIRECT_TEXT_SCORE
    assert parts["direct_text_hits"] >= 1.0
    assert "direct text match" in bundle.results[0].reasons


def test_direct_text_matches_annotation_like_ts_parameter(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "approval.controller.ts").write_text(
        "\n".join(
            [
                '@Controller("/approval")',
                "export class ApprovalController {",
                '  @Get("current-auditor")',
                "  currentAuditor() { return true; }",
                "}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    config = _direct_text_config(final_top_k=1)
    index_repository(repo, config)

    bundle = query_repository(repo, "current-auditor", config)

    assert [result.file_path for result in bundle.results] == [
        Path("approval.controller.ts")
    ]
    assert bundle.results[0].score_parts["direct_text"] >= MIN_STRONG_DIRECT_TEXT_SCORE
    assert bundle.results[0].score_parts["direct_text_hits"] >= 1.0
    assert "direct text match" in bundle.results[0].reasons


def test_readme_direct_text_anchor_expands_to_same_directory_code(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    feature_dir = repo / "approval"
    feature_dir.mkdir(parents=True)
    (feature_dir / "README.md").write_text(
        "当前审批人查询接口由 ApprovalService 负责。\n",
        encoding="utf-8",
    )
    (feature_dir / "ApprovalService.java").write_text(
        "\n".join(
            [
                "interface ApprovalService {",
                "  String currentAuditor();",
                "}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    config = _direct_text_config(final_top_k=2)
    index_repository(repo, config)

    bundle = query_repository(repo, "当前审批人查询接口", config)

    assert [result.file_path for result in bundle.results] == [
        Path("approval/README.md"),
        Path("approval/ApprovalService.java"),
    ]
    assert bundle.results[0].score_parts["direct_text"] >= MIN_STRONG_DIRECT_TEXT_SCORE
    service_parts = bundle.results[1].score_parts
    assert service_parts["directory_anchor"] > 0
    assert service_parts["anchored_relation"] > 0
    assert service_parts["original_relation"] > 0


def test_direct_text_anchor_seeds_existing_relation_expansion(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "ApprovalController.java").write_text(
        "\n".join(
            [
                "class ApprovalController {",
                "  // 当前审批人查询接口",
                "  String current() { return service.currentAuditor(); }",
                "}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (repo / "ApprovalServiceImpl.java").write_text(
        "\n".join(
            [
                "class ApprovalServiceImpl {",
                "  String currentAuditor() { return \"ok\"; }",
                "}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    config = _direct_text_config(final_top_k=2)
    index_repository(repo, config)
    store = SQLiteStore(index_dir_for(repo) / "index.sqlite")

    # Set up test signals and relations
    controller_chunk = store.chunk_for_line(Path("ApprovalController.java"), 2)
    service_chunk = store.chunk_for_line(Path("ApprovalServiceImpl.java"), 2)

    _create_test_signal(
        store,
        Path("ApprovalController.java"),
        "sig-controller-current",
        controller_chunk.chunk_id,
        "ApprovalController.current",
        3,
        3,
        ["approval", "current"],
    )
    _create_test_signal(
        store,
        Path("ApprovalServiceImpl.java"),
        "sig-service-current-auditor",
        service_chunk.chunk_id,
        "ApprovalServiceImpl.currentAuditor",
        2,
        2,
        ["approval", "current", "auditor"],
    )
    _create_test_relation(
        store,
        Path("ApprovalController.java"),
        "rel-controller-service",
        "sig-controller-current",
        "ApprovalServiceImpl.currentAuditor",
        0.9,
    )

    bundle = query_repository(repo, "当前审批人查询接口", config)

    assert [result.file_path for result in bundle.results] == [
        Path("ApprovalController.java"),
        Path("ApprovalServiceImpl.java"),
    ]
    assert bundle.results[0].score_parts["direct_text"] >= MIN_STRONG_DIRECT_TEXT_SCORE
    assert bundle.results[1].score_parts["original_relation"] > 0
