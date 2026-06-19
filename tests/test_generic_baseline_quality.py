import fnmatch
import json
import os
import shutil
from pathlib import Path, PureWindowsPath

import pytest

from context_search_tool.config import DEFAULT_CONFIG
from context_search_tool.indexer import index_repository
from context_search_tool.retrieval import query_repository


FIXTURE_PATH = (
    Path(__file__).parent
    / "fixtures"
    / "generic_baseline_quality"
    / "queries.json"
)


def _load_repo_specs() -> list[dict]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _assert_non_empty_string(value: object) -> None:
    assert isinstance(value, str) and value


def _assert_relative_string(value: object) -> None:
    _assert_non_empty_string(value)
    assert not Path(value).is_absolute()
    assert not PureWindowsPath(value).is_absolute()


def _assert_positive_integer(value: object) -> None:
    assert type(value) is int and value > 0


def _assert_string_list(value: object) -> None:
    assert isinstance(value, list)
    assert all(isinstance(item, str) and item for item in value)


def _assert_matcher_item(item: object) -> None:
    assert isinstance(item, dict)
    has_path = "path" in item
    has_glob = "glob" in item
    assert has_path != has_glob
    if has_path:
        _assert_relative_string(item["path"])
    else:
        _assert_relative_string(item["glob"])
    _assert_positive_integer(item.get("top_k"))


def _assert_matcher_list(value: object) -> None:
    assert isinstance(value, list)
    assert value
    for item in value:
        _assert_matcher_item(item)


def _assert_outrank_item(item: object) -> None:
    assert isinstance(item, dict)
    _assert_relative_string(item.get("source"))
    _assert_relative_string(item.get("noise"))
    _assert_positive_integer(item.get("top_k"))


def _assert_query_spec(query_spec: object) -> None:
    assert isinstance(query_spec, dict)
    for key in ("id", "query"):
        assert key in query_spec
        _assert_non_empty_string(query_spec[key])

    for key in ("expected_top_k", "absent_top_k", "expected_any_top_k"):
        if key in query_spec:
            _assert_matcher_list(query_spec[key])

    if "outranks" in query_spec:
        assert isinstance(query_spec["outranks"], list)
        assert query_spec["outranks"]
        for item in query_spec["outranks"]:
            _assert_outrank_item(item)

    if "anchor_expected" in query_spec:
        _assert_string_list(query_spec["anchor_expected"])
        for expected_anchor in query_spec["anchor_expected"]:
            _assert_relative_string(expected_anchor)

    if "known_gap" in query_spec:
        _assert_non_empty_string(query_spec["known_gap"])


def _assert_repo_spec(repo_spec: dict) -> None:
    assert isinstance(repo_spec, dict)
    for key in ("repo_key", "path_env", "repo_dir_name"):
        assert key in repo_spec
        _assert_non_empty_string(repo_spec[key])

    assert not Path(repo_spec["repo_dir_name"]).is_absolute()
    assert "queries" in repo_spec
    assert isinstance(repo_spec["queries"], list)
    assert repo_spec["queries"]
    for query_spec in repo_spec["queries"]:
        _assert_query_spec(query_spec)


def _repo_for_spec(repo_spec: dict) -> Path | None:
    direct = os.environ.get(repo_spec["path_env"])
    if direct:
        return Path(direct)

    base = os.environ.get("CST_SMOKE_REPOS_DIR")
    if base:
        return Path(base) / repo_spec["repo_dir_name"]

    return None


def _copy_repo_for_smoke(source_repo: Path, workspace: Path) -> Path:
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


def _matches(pattern: dict, path: str) -> bool:
    if "path" in pattern:
        return path == pattern["path"]
    return fnmatch.fnmatch(path, pattern["glob"])


def _pattern_matches(pattern: str, path: str) -> bool:
    return path == pattern or fnmatch.fnmatch(path, pattern)


def _assert_expected_top_k(query_spec: dict, top_paths: list[str]) -> None:
    for expected in query_spec.get("expected_top_k", []):
        scoped_paths = top_paths[: expected["top_k"]]
        assert any(_matches(expected, path) for path in scoped_paths), {
            "query_id": query_spec["id"],
            "query": query_spec["query"],
            "top_paths": top_paths,
            "expected": expected,
        }


def _assert_expected_any_top_k(query_spec: dict, top_paths: list[str]) -> None:
    expected_any = query_spec.get("expected_any_top_k", [])
    if not expected_any:
        return

    for expected in expected_any:
        scoped_paths = top_paths[: expected["top_k"]]
        if any(_matches(expected, path) for path in scoped_paths):
            return

    assert False, {
        "query_id": query_spec["id"],
        "query": query_spec["query"],
        "top_paths": top_paths,
        "expected_any": expected_any,
    }


def _assert_absent_top_k(query_spec: dict, top_paths: list[str]) -> None:
    for absent in query_spec.get("absent_top_k", []):
        scoped_paths = top_paths[: absent["top_k"]]
        assert not any(_matches(absent, path) for path in scoped_paths), {
            "query_id": query_spec["id"],
            "query": query_spec["query"],
            "top_paths": top_paths,
            "absent": absent,
        }


def _first_match_index(pattern: str, top_paths: list[str]) -> int | None:
    for index, path in enumerate(top_paths):
        if _pattern_matches(pattern, path):
            return index
    return None


def _assert_outranks(query_spec: dict, top_paths: list[str]) -> None:
    for outrank in query_spec.get("outranks", []):
        scoped_paths = top_paths[: outrank["top_k"]]
        noise_index = _first_match_index(outrank["noise"], scoped_paths)
        if noise_index is None:
            continue

        source_index = _first_match_index(outrank["source"], scoped_paths)
        assert source_index is not None and source_index < noise_index, {
            "query_id": query_spec["id"],
            "query": query_spec["query"],
            "top_paths": top_paths,
            "source": outrank["source"],
            "noise": outrank["noise"],
            "top_k": outrank["top_k"],
        }


def _assert_anchor_expected(query_spec: dict, bundle) -> None:
    expected_anchors = query_spec.get("anchor_expected", [])
    if not expected_anchors:
        return

    anchor_paths = [anchor.file_path.as_posix() for anchor in bundle.evidence_anchors]
    result_paths = [result.file_path.as_posix() for result in bundle.results]

    for expected_path in expected_anchors:
        assert expected_path in anchor_paths, {
            "query_id": query_spec["id"],
            "query": query_spec["query"],
            "anchor_paths": anchor_paths,
            "expected_anchor": expected_path,
        }
        if result_paths:
            assert expected_path not in result_paths, {
                "query_id": query_spec["id"],
                "query": query_spec["query"],
                "top_paths": result_paths,
                "expected_anchor": expected_path,
            }


def _repo_snapshot(repo: Path) -> list[str]:
    return sorted(path.relative_to(repo).as_posix() for path in repo.rglob("*"))


def test_generic_baseline_quality_queries_load() -> None:
    repo_specs = _load_repo_specs()
    assert {spec["repo_key"] for spec in repo_specs} == {"imagebed", "env_change"}
    for repo_spec in repo_specs:
        _assert_repo_spec(repo_spec)


def test_generic_baseline_quality_rejects_invalid_fixture_shapes() -> None:
    invalid_specs = [
        {
            "path_env": "CST_SMOKE_IMAGEBED_REPO",
            "repo_dir_name": "imagebed",
            "queries": [{"id": "bad", "query": "bad"}],
        },
        {
            "repo_key": "imagebed",
            "path_env": "CST_SMOKE_IMAGEBED_REPO",
            "repo_dir_name": "imagebed",
            "queries": [
                {
                    "id": "bad",
                    "query": "bad",
                    "expected_top_k": [
                        {"path": "handler/upload.go", "glob": "*.go", "top_k": 5}
                    ],
                }
            ],
        },
        {
            "repo_key": "imagebed",
            "path_env": "CST_SMOKE_IMAGEBED_REPO",
            "repo_dir_name": "imagebed",
            "queries": [
                {
                    "id": "bad",
                    "query": "bad",
                    "expected_top_k": [{"path": "C:/repo/handler/upload.go", "top_k": 5}],
                }
            ],
        },
        {
            "repo_key": "imagebed",
            "path_env": "CST_SMOKE_IMAGEBED_REPO",
            "repo_dir_name": "imagebed",
            "queries": [
                {
                    "id": "bad",
                    "query": "bad",
                    "expected_top_k": [
                        {"path": "\\\\server\\share\\handler\\upload.go", "top_k": 5}
                    ],
                }
            ],
        },
        {
            "repo_key": "imagebed",
            "path_env": "CST_SMOKE_IMAGEBED_REPO",
            "repo_dir_name": "imagebed",
            "queries": [
                {
                    "id": "bad",
                    "query": "bad",
                    "absent_top_k": [{"glob": "/tmp/templates/*", "top_k": 5}],
                }
            ],
        },
        {
            "repo_key": "imagebed",
            "path_env": "CST_SMOKE_IMAGEBED_REPO",
            "repo_dir_name": "imagebed",
            "queries": [
                {
                    "id": "bad",
                    "query": "bad",
                    "expected_top_k": [{"path": "handler/upload.go", "top_k": 0}],
                }
            ],
        },
        {
            "repo_key": "imagebed",
            "path_env": "CST_SMOKE_IMAGEBED_REPO",
            "repo_dir_name": "imagebed",
            "queries": [
                {
                    "id": "bad",
                    "query": "bad",
                    "expected_any_top_k": "handler/upload.go",
                }
            ],
        },
        {
            "repo_key": "imagebed",
            "path_env": "CST_SMOKE_IMAGEBED_REPO",
            "repo_dir_name": "imagebed",
            "queries": [
                {
                    "id": "bad",
                    "query": "bad",
                    "outranks": [{"source": "storage/*.go", "top_k": 8}],
                }
            ],
        },
        {
            "repo_key": "imagebed",
            "path_env": "CST_SMOKE_IMAGEBED_REPO",
            "repo_dir_name": "imagebed",
            "queries": [
                {
                    "id": "bad",
                    "query": "bad",
                    "expected_top_k": [{"path": "/tmp/handler/upload.go", "top_k": 5}],
                }
            ],
        },
        {
            "repo_key": "imagebed",
            "path_env": "CST_SMOKE_IMAGEBED_REPO",
            "repo_dir_name": "imagebed",
            "queries": [
                {
                    "id": "bad",
                    "query": "bad",
                    "anchor_expected": ["/tmp/docs/README.md"],
                }
            ],
        },
        {
            "repo_key": "imagebed",
            "path_env": "CST_SMOKE_IMAGEBED_REPO",
            "repo_dir_name": "imagebed",
            "queries": [
                {
                    "id": "bad",
                    "query": "bad",
                    "outranks": [
                        {
                            "source": "/tmp/storage/*.go",
                            "noise": "templates/index.html",
                            "top_k": 8,
                        }
                    ],
                }
            ],
        },
        {
            "repo_key": "imagebed",
            "path_env": "CST_SMOKE_IMAGEBED_REPO",
            "repo_dir_name": "imagebed",
            "queries": [
                {
                    "id": "bad",
                    "query": "bad",
                    "outranks": [
                        {
                            "source": "storage/*.go",
                            "noise": "/tmp/templates/index.html",
                            "top_k": 8,
                        }
                    ],
                }
            ],
        },
    ]

    for repo_spec in invalid_specs:
        with pytest.raises(AssertionError):
            _assert_repo_spec(repo_spec)


def test_assert_anchor_expected_accepts_anchor_paths_outside_results() -> None:
    class FakePathItem:
        def __init__(self, file_path: str) -> None:
            self.file_path = Path(file_path)

    class FakeBundle:
        evidence_anchors = [FakePathItem("README.md")]
        results = [FakePathItem("src/main.py")]

    _assert_anchor_expected(
        {
            "id": "readme-anchor",
            "query": "readme anchor",
            "anchor_expected": ["README.md"],
        },
        FakeBundle(),
    )


def test_assert_anchor_expected_rejects_missing_anchor_path() -> None:
    class FakePathItem:
        def __init__(self, file_path: str) -> None:
            self.file_path = Path(file_path)

    class FakeBundle:
        evidence_anchors = [FakePathItem("docs/other.md")]
        results = [FakePathItem("src/main.py")]

    with pytest.raises(AssertionError):
        _assert_anchor_expected(
            {
                "id": "readme-anchor",
                "query": "readme anchor",
                "anchor_expected": ["README.md"],
            },
            FakeBundle(),
        )


def test_assert_anchor_expected_rejects_anchor_path_in_results() -> None:
    class FakePathItem:
        def __init__(self, file_path: str) -> None:
            self.file_path = Path(file_path)

    class FakeBundle:
        evidence_anchors = [FakePathItem("README.md")]
        results = [FakePathItem("README.md")]

    with pytest.raises(AssertionError):
        _assert_anchor_expected(
            {
                "id": "readme-anchor",
                "query": "readme anchor",
                "anchor_expected": ["README.md"],
            },
            FakeBundle(),
        )


def test_copy_repo_for_smoke_excludes_git_and_context_search_without_mutating_source(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "src").mkdir()
    (source / "src" / "main.go").write_text("package main\n", encoding="utf-8")
    (source / ".git").mkdir()
    (source / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    (source / ".context-search").mkdir()
    (source / ".context-search" / "manifest.json").write_text("{}", encoding="utf-8")
    before = _repo_snapshot(source)

    copied = _copy_repo_for_smoke(source, tmp_path / "work")

    assert (copied / "src" / "main.go").exists()
    assert not (copied / ".git").exists()
    assert not (copied / ".context-search").exists()
    assert _repo_snapshot(source) == before


@pytest.mark.slow
@pytest.mark.integration
@pytest.mark.parametrize("repo_spec", _load_repo_specs(), ids=lambda item: item["repo_key"])
def test_generic_baseline_real_project_quality(
    repo_spec: dict,
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    source_repo = _repo_for_spec(repo_spec)
    if source_repo is None:
        pytest.skip(f"{repo_spec['repo_key']} repo path not configured")
    if not source_repo.exists():
        pytest.skip(f"repo not found: {source_repo}")

    workspace = tmp_path_factory.mktemp(f"generic-baseline-{repo_spec['repo_key']}")
    repo = _copy_repo_for_smoke(source_repo, workspace)
    index_repository(repo, DEFAULT_CONFIG)

    for query_spec in repo_spec["queries"]:
        bundle = query_repository(repo, query_spec["query"], DEFAULT_CONFIG)
        top_paths = [result.file_path.as_posix() for result in bundle.results]
        _assert_expected_top_k(query_spec, top_paths)
        _assert_expected_any_top_k(query_spec, top_paths)
        _assert_absent_top_k(query_spec, top_paths)
        _assert_outranks(query_spec, top_paths)
        _assert_anchor_expected(query_spec, bundle)
