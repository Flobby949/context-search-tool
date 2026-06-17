import shutil
from pathlib import Path

from context_search_tool.config import DEFAULT_CONFIG
from context_search_tool.indexer import index_repository
from context_search_tool.retrieval import query_repository
from context_search_tool.sqlite_store import SQLiteStore


def _copy_java_fixture(tmp_path: Path) -> Path:
    source_fixture = Path(__file__).parent / "fixtures" / "java-spring-mini"
    repo = tmp_path / "java-spring-mini"
    shutil.copytree(source_fixture, repo)
    return repo


def test_java_fixture_surfaces_controller_query_mapper_and_enum(tmp_path: Path) -> None:
    source_fixture = Path(__file__).parent / "fixtures" / "java-spring-mini"
    repo = tmp_path / "java-spring-mini"
    shutil.copytree(source_fixture, repo)

    index_repository(repo, DEFAULT_CONFIG)
    bundle = query_repository(
        repo,
        "/apply/audit/pageEs INVOLVED_BY_ME why does it leak across regions",
        DEFAULT_CONFIG,
        context_lines=20,
    )

    paths = {result.file_path.name for result in bundle.results}

    assert "ApplyAuditController.java" in paths
    assert "EsApplyAuditPageQryExe.java" in paths
    assert "AuditStatus.java" in paths
    assert "ApplyAuditMapper.java" in paths
    assert bundle.results[0].score > 0


def test_java_fixture_indexes_spring_endpoint_signals(tmp_path: Path) -> None:
    source_fixture = Path(__file__).parent / "fixtures" / "java-spring-mini"
    repo = tmp_path / "java-spring-mini"
    shutil.copytree(source_fixture, repo)

    index_repository(repo, DEFAULT_CONFIG)
    store = SQLiteStore(repo / ".context-search" / "index.sqlite")
    signals = {signal.name: signal for signal in store.signal_search(["stats"], limit=10)}

    assert "GET /apply/audit/stats/wait" in signals
    assert "POST /apply/audit/stats" in signals
    assert signals["GET /apply/audit/stats/wait"].metadata["controller"] == (
        "ApplyAuditController"
    )
    assert signals["POST /apply/audit/stats"].metadata["method"] == "auditStats"


def test_java_fixture_indexes_short_chain_relations(tmp_path: Path) -> None:
    source_fixture = Path(__file__).parent / "fixtures" / "java-spring-mini"
    repo = tmp_path / "java-spring-mini"
    shutil.copytree(source_fixture, repo)

    index_repository(repo, DEFAULT_CONFIG)
    store = SQLiteStore(repo / ".context-search" / "index.sqlite")

    controller_relations = store.relations_targeting("ResourceAuditService.statsWait")
    assert any(
        relation.kind == "calls" and relation.confidence == 0.8
        for relation in controller_relations
    )

    implements_relations = store.relations_targeting("ResourceAuditService")
    assert any(
        relation.kind == "implements" and relation.confidence == 1.0
        for relation in implements_relations
    )

    executable_relations = store.relations_targeting("EsApplyAuditPageQryExe.statsWait")
    assert any(
        relation.kind == "uses" and relation.confidence == 0.8
        for relation in executable_relations
    )


def test_java_fixture_workbench_query_returns_expected_summary(tmp_path: Path) -> None:
    source_fixture = Path(__file__).parent / "fixtures" / "java-spring-mini"
    repo = tmp_path / "java-spring-mini"
    shutil.copytree(source_fixture, repo)

    index_repository(repo, DEFAULT_CONFIG)
    bundle = query_repository(
        repo,
        "工作台相关代码",
        DEFAULT_CONFIG,
        context_lines=20,
    )

    assert bundle.summary.entry_points
    assert "GET /apply/audit/stats/wait" in bundle.summary.entry_points
    assert "ResourceAuditServiceImpl.statsWait" in bundle.summary.implementation
    assert "WorkbenchResourceAuditStatsDTO" in bundle.summary.related_types
    assert "WorkbenchResourceStatsDTO" in bundle.summary.possibly_legacy


def test_java_fixture_workflow_query_returns_expected_summary(tmp_path: Path) -> None:
    source_fixture = Path(__file__).parent / "fixtures" / "java-spring-mini"
    repo = tmp_path / "java-spring-mini"
    shutil.copytree(source_fixture, repo)

    index_repository(repo, DEFAULT_CONFIG)
    bundle = query_repository(
        repo,
        "apaas工作流相关接口",
        DEFAULT_CONFIG,
        context_lines=20,
    )

    assert bundle.summary.entry_points
    assert any(
        entry.startswith("POST") and "/open/process" in entry
        for entry in bundle.summary.entry_points
    )
    assert any(
        entry.startswith("GET") and "/open/process" in entry
        for entry in bundle.summary.entry_points
    )
    assert any(
        "Gateway" in item or "Command" in item for item in bundle.summary.implementation
    )
    assert any(
        "Request" in item and "DTO" in item
        or "Response" in item and "DTO" in item
        for item in bundle.summary.related_types
    )


def test_java_spring_path_rerank_prefers_exact_app_catalog_page_chain(
    tmp_path: Path,
) -> None:
    repo = _copy_java_fixture(tmp_path)
    config = DEFAULT_CONFIG

    index_repository(repo, config)
    bundle = query_repository(repo, "/appCatalog/page canApply", config, context_lines=20)

    names = [result.file_path.name for result in bundle.results]
    top_five = names[:5]

    assert "AppCatalogController.java" in top_five
    assert "AppInfoServiceImpl.java" in top_five
    assert "PageAppCatalogQueryExe.java" in top_five
    non_target_names = {"ResourceAuditServiceImpl.java", "EsApplyAuditPageQryExe.java"}
    for result in bundle.results:
        if result.file_path.name in non_target_names:
            assert "java_method_context_match" not in result.score_parts
            assert "java_executor_context_boost" not in result.score_parts
    assert names[0] != "AppCatalogOpenController.java"
    if "AppCatalogOpenController.java" in names:
        assert names.index("AppCatalogController.java") < names.index(
            "AppCatalogOpenController.java"
        )


def test_java_spring_path_rerank_prefers_es_audit_business_chain(
    tmp_path: Path,
) -> None:
    repo = _copy_java_fixture(tmp_path)
    config = DEFAULT_CONFIG

    index_repository(repo, config)
    bundle = query_repository(
        repo, "/apply/audit/pageEs INVOLVED_BY_ME", config, context_lines=20
    )

    names = [result.file_path.name for result in bundle.results]
    top_six = names[:6]

    assert "ResourceApplyAuditController.java" in top_six
    assert "ResourceAuditServiceImpl.java" in top_six
    assert "EsApplyAuditPageQryExe.java" in top_six
    assert "ResourceApplyAuditControllerTest.java" not in top_six
    if "ApplyAuditPageQryExe.java" in names:
        assert names.index("EsApplyAuditPageQryExe.java") < names.index(
            "ApplyAuditPageQryExe.java"
        )
