import shutil
from pathlib import Path

from context_search_tool.config import DEFAULT_CONFIG
from context_search_tool.indexer import index_repository
from context_search_tool.retrieval import query_repository


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
