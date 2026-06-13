import shutil
from pathlib import Path

from context_search_tool.config import DEFAULT_CONFIG
from context_search_tool.indexer import index_repository
from context_search_tool.retrieval import query_repository
from context_search_tool.sqlite_store import SQLiteStore


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
