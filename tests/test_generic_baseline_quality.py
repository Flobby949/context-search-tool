import fnmatch
import json
import os
import shutil
from pathlib import Path, PureWindowsPath

import pytest

from context_search_tool import retrieval
from context_search_tool.config import DEFAULT_CONFIG
from context_search_tool.indexer import index_repository
from context_search_tool.paths import index_dir_for
from context_search_tool.retrieval import query_repository
from context_search_tool.sqlite_store import SQLiteStore


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


def _assert_preferred_rank_item(item: object) -> None:
    assert isinstance(item, dict)
    _assert_matcher_item(item)
    _assert_positive_integer(item.get("max_rank"))
    assert item["max_rank"] <= item["top_k"]


def _assert_forbidden_above_item(item: object) -> None:
    assert isinstance(item, dict)
    _assert_matcher_item(item)
    _assert_positive_integer(item.get("max_rank"))
    assert item["max_rank"] <= item["top_k"]


def _assert_query_spec(query_spec: object) -> None:
    assert isinstance(query_spec, dict)
    for key in ("id", "query"):
        assert key in query_spec
        _assert_non_empty_string(query_spec[key])

    for key in ("expected_top_k", "absent_top_k", "expected_any_top_k"):
        if key in query_spec:
            _assert_matcher_list(query_spec[key])

    if "preferred_rank" in query_spec:
        assert isinstance(query_spec["preferred_rank"], list)
        assert query_spec["preferred_rank"]
        for item in query_spec["preferred_rank"]:
            _assert_preferred_rank_item(item)

    if "forbidden_above" in query_spec:
        assert isinstance(query_spec["forbidden_above"], list)
        assert query_spec["forbidden_above"]
        for item in query_spec["forbidden_above"]:
            _assert_forbidden_above_item(item)

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
        base_repo = Path(base) / repo_spec["repo_dir_name"]
        if base_repo.exists():
            return base_repo

    fixture_repo = (
        Path(__file__).parent
        / "fixtures"
        / "real_projects"
        / str(repo_spec["repo_key"])
    )
    if fixture_repo.exists():
        return fixture_repo

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


def _preferred_rank_position(preferred: dict, top_paths: list[str]) -> int | None:
    scoped_paths = top_paths[: preferred["top_k"]]
    for index, path in enumerate(scoped_paths, start=1):
        if _matches(preferred, path):
            return index
    return None


def _assert_preferred_rank(query_spec: dict, top_paths: list[str]) -> None:
    for preferred in query_spec.get("preferred_rank", []):
        rank = _preferred_rank_position(preferred, top_paths)
        if rank is None:
            assert False, {
                "query_id": query_spec["id"],
                "query": query_spec["query"],
                "top_paths": top_paths,
                "preferred": preferred,
            }
        assert rank <= preferred["max_rank"], {
            "query_id": query_spec["id"],
            "query": query_spec["query"],
            "top_paths": top_paths,
            "preferred": preferred,
            "actual_rank": rank,
        }


def _assert_forbidden_above(query_spec: dict, top_paths: list[str]) -> None:
    for forbidden in query_spec.get("forbidden_above", []):
        scoped_paths = top_paths[: forbidden["top_k"]]
        for rank, path in enumerate(scoped_paths, start=1):
            if rank > forbidden["max_rank"]:
                break
            assert not _matches(forbidden, path), {
                "query_id": query_spec["id"],
                "query": query_spec["query"],
                "top_paths": top_paths,
                "forbidden": forbidden,
                "actual_rank": rank,
            }


def _assert_expected_candidates(query_spec: dict, candidate_paths: set[str]) -> None:
    for expected in query_spec.get("expected_top_k", []):
        assert any(_matches(expected, path) for path in candidate_paths), {
            "query_id": query_spec["id"],
            "query": query_spec["query"],
            "candidate_paths": sorted(candidate_paths),
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


def _candidate_pool_paths_before_rerank(repo: Path, query: str) -> set[str]:
    config = DEFAULT_CONFIG
    index_dir = index_dir_for(repo)
    store = SQLiteStore(index_dir / "index.sqlite")
    original_tokens = retrieval._dedupe(retrieval.tokenize_query(query))
    deleted_ids = store.deleted_chunk_ids()
    initial_candidates = retrieval._initial_candidates(
        index_dir,
        store,
        query,
        original_tokens,
        config,
        deleted_ids,
    )
    signal_candidates = retrieval._signal_candidates(store, original_tokens, config)
    direct_candidates = retrieval._merge_candidates(
        [
            *initial_candidates,
            *signal_candidates,
        ]
    )
    anchor_candidates = retrieval._anchor_expansion_candidates(
        store,
        list(direct_candidates.values()),
        config,
        query=query,
        tokens=original_tokens,
    )
    relation_seed_candidates = retrieval._merge_candidates(
        [
            *direct_candidates.values(),
            *anchor_candidates,
        ]
    )
    relation_candidates = retrieval._relation_expansion_candidates(
        store,
        list(relation_seed_candidates.values()),
        config,
    )
    candidates = retrieval._merge_candidates(
        [
            *direct_candidates.values(),
            *anchor_candidates,
            *relation_candidates,
        ]
    )
    chunks = store.chunks_for_ids(list(candidates))
    return {chunk.file_path.as_posix() for chunk in chunks.values()}


def _repo_snapshot(repo: Path) -> list[str]:
    return sorted(path.relative_to(repo).as_posix() for path in repo.rglob("*"))


def test_generic_baseline_quality_queries_load() -> None:
    repo_specs = _load_repo_specs()
    assert {spec["repo_key"] for spec in repo_specs} == {
        "imagebed",
        "env_change",
        "investment_assistant",
        "program_tool",
    }
    for repo_spec in repo_specs:
        _assert_repo_spec(repo_spec)


def _program_tool_repo_spec() -> dict:
    return {
        "repo_key": "program_tool",
        "path_env": "CST_SMOKE_PROGRAM_TOOL_REPO",
        "repo_dir_name": "program-tool",
    }


def _program_tool_fixture_repo() -> Path:
    return Path(__file__).parent / "fixtures" / "real_projects" / "program_tool"


def test_repo_for_spec_resolves_committed_program_tool_fixture(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CST_SMOKE_PROGRAM_TOOL_REPO", raising=False)
    monkeypatch.delenv("CST_SMOKE_REPOS_DIR", raising=False)
    fixture_repo = _program_tool_fixture_repo()

    assert _repo_for_spec(_program_tool_repo_spec()) == fixture_repo
    assert (fixture_repo / "package.json").exists()


def test_repo_for_spec_prefers_explicit_path_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    direct_repo = tmp_path / "direct-program-tool"
    smoke_repo = tmp_path / "smoke-repos" / "program-tool"
    direct_repo.mkdir()
    smoke_repo.mkdir(parents=True)
    monkeypatch.setenv("CST_SMOKE_PROGRAM_TOOL_REPO", str(direct_repo))
    monkeypatch.setenv("CST_SMOKE_REPOS_DIR", str(smoke_repo.parent))

    assert _repo_for_spec(_program_tool_repo_spec()) == direct_repo


def test_repo_for_spec_prefers_existing_smoke_dir_repo_over_fixture(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    smoke_repo = tmp_path / "smoke-repos" / "program-tool"
    smoke_repo.mkdir(parents=True)
    monkeypatch.delenv("CST_SMOKE_PROGRAM_TOOL_REPO", raising=False)
    monkeypatch.setenv("CST_SMOKE_REPOS_DIR", str(smoke_repo.parent))

    assert _repo_for_spec(_program_tool_repo_spec()) == smoke_repo


def test_repo_for_spec_falls_back_to_fixture_when_smoke_dir_repo_is_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    missing_smoke_repos = tmp_path / "smoke-repos"
    missing_smoke_repos.mkdir()
    monkeypatch.delenv("CST_SMOKE_PROGRAM_TOOL_REPO", raising=False)
    monkeypatch.setenv("CST_SMOKE_REPOS_DIR", str(missing_smoke_repos))

    assert _repo_for_spec(_program_tool_repo_spec()) == _program_tool_fixture_repo()


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
        {
            "repo_key": "imagebed",
            "path_env": "CST_SMOKE_IMAGEBED_REPO",
            "repo_dir_name": "imagebed",
            "queries": [
                {
                    "id": "bad",
                    "query": "bad",
                    "preferred_rank": [
                        {"path": "handler/upload.go", "top_k": 5, "max_rank": 0}
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
                    "preferred_rank": [
                        {"path": "handler/upload.go", "top_k": 3, "max_rank": 4}
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
                    "forbidden_above": [
                        {"glob": "cmd/typora/**", "top_k": 5, "max_rank": 0}
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
                    "forbidden_above": [
                        {"glob": "cmd/typora/**", "top_k": 3, "max_rank": 4}
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
        if repo_spec["repo_key"] == "investment_assistant":
            candidate_paths = _candidate_pool_paths_before_rerank(
                repo,
                query_spec["query"],
            )
            _assert_expected_candidates(query_spec, candidate_paths)

        bundle = query_repository(repo, query_spec["query"], DEFAULT_CONFIG)
        top_paths = [result.file_path.as_posix() for result in bundle.results]
        _assert_expected_top_k(query_spec, top_paths)
        _assert_preferred_rank(query_spec, top_paths)
        _assert_expected_any_top_k(query_spec, top_paths)
        _assert_absent_top_k(query_spec, top_paths)
        _assert_outranks(query_spec, top_paths)
        _assert_forbidden_above(query_spec, top_paths)
        _assert_anchor_expected(query_spec, bundle)
