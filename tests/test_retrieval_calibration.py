import json
import shutil
from pathlib import Path

import pytest

from context_search_tool.config import EmbeddingConfig, ToolConfig
from context_search_tool.indexer import index_repository
from context_search_tool.retrieval import query_repository


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "retrieval_calibration" / "queries.json"


def _load_queries() -> list[dict]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _assert_string_list(value: object) -> None:
    assert isinstance(value, list)
    assert all(isinstance(item, str) and item for item in value)


def _assert_query_spec(query: dict) -> None:
    assert query["repo_key"] in {"operation_client", "console_iot"}
    assert isinstance(query["query"], str) and query["query"]
    _assert_string_list(query["expected_core"])
    assert isinstance(query["expected_top5_min"], int)
    assert 3 <= query["expected_top5_min"] <= min(5, len(query["expected_core"]))
    _assert_string_list(query.get("required_top3", []))
    _assert_string_list(query.get("forbidden_top3", []))


def _copy_repo_for_calibration(source_repo: Path, workspace: Path) -> Path:
    target = workspace / source_repo.name
    if target.exists():
        return target
    return Path(
        shutil.copytree(
            source_repo,
            target,
            ignore=shutil.ignore_patterns(".git", ".context-search"),
        )
    )


@pytest.fixture(scope="session")
def calibration_workspace(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("retrieval-calibration")


def test_retrieval_calibration_queries_load() -> None:
    queries = _load_queries()
    assert len(queries) == 8
    for query in queries:
        _assert_query_spec(query)


def test_retrieval_calibration_rejects_invalid_fixture_shapes() -> None:
    invalid_specs = [
        {
            "repo_key": "operation_client",
            "query": "bad",
            "expected_core": "src/AuthController.java",
            "expected_top5_min": 3,
            "forbidden_top3": [],
        },
        {
            "repo_key": "operation_client",
            "query": "bad",
            "expected_core": ["src/AuthController.java"],
            "expected_top5_min": 6,
            "forbidden_top3": [],
        },
        {
            "repo_key": "console_iot",
            "query": "bad",
            "expected_core": ["src/AuthController.java"],
            "expected_top5_min": 1,
            "required_top3": "src/AuthController.java",
            "forbidden_top3": [],
        },
    ]

    for query_spec in invalid_specs:
        with pytest.raises(AssertionError):
            _assert_query_spec(query_spec)


def test_calibration_repo_copy_excludes_existing_index_and_git_metadata(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "src").mkdir()
    (source / "src" / "Example.java").write_text("class Example {}\n", encoding="utf-8")
    (source / ".git").mkdir()
    (source / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    (source / ".context-search").mkdir()
    (source / ".context-search" / "manifest.json").write_text("{}", encoding="utf-8")

    copied = _copy_repo_for_calibration(source, tmp_path / "work")

    assert (copied / "src" / "Example.java").exists()
    assert not (copied / ".git").exists()
    assert not (copied / ".context-search").exists()
    assert not (source / ".context-search" / "index.sqlite").exists()


def test_calibration_repo_copy_reuses_existing_workspace_copy(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "Example.java").write_text("class Example {}\n", encoding="utf-8")

    copied = _copy_repo_for_calibration(source, tmp_path / "work")
    (copied / ".context-search").mkdir()
    (copied / ".context-search" / "index.sqlite").write_text("cached", encoding="utf-8")

    reused = _copy_repo_for_calibration(source, tmp_path / "work")

    assert reused == copied
    assert (reused / ".context-search" / "index.sqlite").read_text(
        encoding="utf-8"
    ) == "cached"


def _repo_for_query(request: pytest.FixtureRequest, repo_key: str) -> Path | None:
    option_name = {
        "operation_client": "--calibration-operation-client-repo",
        "console_iot": "--calibration-console-iot-repo",
    }[repo_key]
    raw_path = request.config.getoption(option_name, None)
    return Path(raw_path) if raw_path else None


def _top_paths(results, limit: int) -> list[str]:
    return [result.file_path.as_posix() for result in results[:limit]]


@pytest.mark.slow
@pytest.mark.integration
@pytest.mark.parametrize("query_spec", _load_queries(), ids=lambda item: item["query"])
def test_bge_m3_retrieval_calibration(
    query_spec: dict,
    request: pytest.FixtureRequest,
    calibration_workspace: Path,
) -> None:
    source_repo = _repo_for_query(request, query_spec["repo_key"])
    if source_repo is None:
        pytest.skip(f"{query_spec['repo_key']} repo option not provided")
    if not source_repo.exists():
        pytest.skip(f"repo not found: {source_repo}")

    config = ToolConfig(
        embedding=EmbeddingConfig(provider="bge", model="bge-m3", dimensions=1024)
    )
    repo = _copy_repo_for_calibration(source_repo, calibration_workspace)
    index_repository(repo, config)
    bundle = query_repository(repo, query_spec["query"], config)

    top5 = _top_paths(bundle.results, 5)
    top3 = set(_top_paths(bundle.results, 3))
    expected = set(query_spec["expected_core"])
    coverage = len(expected.intersection(top5))

    assert coverage >= query_spec["expected_top5_min"], {
        "query": query_spec["query"],
        "top5": top5,
        "expected_core": sorted(expected),
        "coverage": coverage,
    }

    for required_path in query_spec.get("required_top3", []):
        assert required_path in top3, {
            "query": query_spec["query"],
            "top3": sorted(top3),
            "required": required_path,
        }

    for forbidden_path in query_spec.get("forbidden_top3", []):
        assert forbidden_path not in top3, {
            "query": query_spec["query"],
            "top3": sorted(top3),
            "forbidden": forbidden_path,
        }
