import json
import os
import shutil
from pathlib import Path

import pytest

import context_search_tool.quality.runner as quality_runner
from context_search_tool.config import (
    DEFAULT_CONFIG,
    EmbeddingConfig,
    IndexConfig,
    QueryPlannerConfig,
    RetrievalConfig,
    ToolConfig,
)
from context_search_tool.indexer import IndexSummary
from context_search_tool.manifest import Manifest
from context_search_tool.quality.cases import QualityRepo
from context_search_tool.quality.runner import (
    ResolvedSource,
    _content_identity,
    _copy_source_repo,
    _effective_config,
    _resolve_repo_source,
    run_quality_fixture,
)
from context_search_tool.retrieval import QueryBundle


def _write_fixture(tmp_path: Path, data: dict) -> Path:
    fixture_path = tmp_path / "quality.json"
    fixture_path.write_text(json.dumps(data), encoding="utf-8")
    return fixture_path


def _snapshot_files(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _write_source_repo(tmp_path: Path) -> Path:
    source = tmp_path / "source"
    (source / "src").mkdir(parents=True)
    (source / "src" / "App.java").write_text(
        """
        package sample;

        class App {
            String targetToken() {
                return "targetToken";
            }
        }
        """,
        encoding="utf-8",
    )
    (source / ".git").mkdir()
    (source / ".git" / "HEAD").write_text("abc123\n", encoding="utf-8")
    (source / ".context-search").mkdir()
    (source / ".context-search" / "old.txt").write_text("old index\n", encoding="utf-8")
    (source / ".gitignore").write_text(".context-search/\n", encoding="utf-8")
    return source


def _patch_runner_dependencies(
    monkeypatch: pytest.MonkeyPatch,
    captured: list[tuple[Path, ToolConfig]],
) -> None:
    def fake_index(repo: Path, config: ToolConfig) -> IndexSummary:
        captured.append((repo, config))
        return IndexSummary(
            files_seen=1,
            files_indexed=1,
            files_skipped=0,
            files_deleted=0,
            chunks_indexed=1,
        )

    def fake_query(
        repo: Path,
        query: str,
        config: ToolConfig,
    ) -> QueryBundle:
        return QueryBundle(
            query=query,
            expanded_tokens=[],
            results=[],
            followup_keywords=[],
        )

    monkeypatch.setattr(
        "context_search_tool.quality.runner.index_repository",
        fake_index,
    )
    monkeypatch.setattr(
        "context_search_tool.quality.runner.load_manifest",
        lambda repo: Manifest(embedding_config_hash="test-hash"),
    )
    monkeypatch.setattr(
        "context_search_tool.quality.runner.query_repository",
        fake_query,
    )


def test_quality_runner_copies_repo_without_mutating_source(tmp_path: Path) -> None:
    source = _write_source_repo(tmp_path)
    before = _snapshot_files(source)
    fixture = _write_fixture(
        tmp_path,
        {
            "schema_version": 1,
            "repos": [
                {
                    "repo_key": "sample",
                    "snapshot_path": str(source),
                    "profiles": ["ci"],
                    "queries": [
                        {
                            "id": "target",
                            "query": "targetToken",
                            "expected_top_k": [{"path": "src/App.java", "top_k": 5}],
                        }
                    ],
                }
            ],
        },
    )

    report = run_quality_fixture(
        fixture,
        profile="ci",
        output_path=None,
        markdown_path=None,
        keep_workspace=True,
    )

    assert report["aggregate"]["total"] == 1
    assert report["aggregate"]["passed"] == 1
    assert report["fixture"]["fixture_case_count"] == 1
    assert report["fixture"]["run_case_count"] == 1
    assert report["config"]["embedding"]["provider"] == "hash"
    assert _snapshot_files(source) == before

    repo_record = report["repos"][0]
    assert repo_record["workspace"]["copied"] is True
    assert repo_record["index"]["embedding_config_hash"]
    assert repo_record["index"]["config_hash"].startswith("sha256:")

    workspace = Path(repo_record["workspace"]["path"])
    assert workspace.exists()
    assert not (workspace / ".git").exists()
    assert not (workspace / ".context-search" / "old.txt").exists()


def test_quality_runner_records_git_commit_from_worktree_gitdir_file(
    tmp_path: Path,
) -> None:
    fake_sha = "1234567890abcdef1234567890abcdef12345678"
    source = _write_source_repo(tmp_path)
    shutil_git = source / ".git"
    for path in sorted(shutil_git.rglob("*"), reverse=True):
        if path.is_file():
            path.unlink()
        else:
            path.rmdir()
    shutil_git.rmdir()
    common_gitdir = tmp_path / "source.git"
    gitdir = common_gitdir / "worktrees" / "source"
    gitdir.mkdir(parents=True)
    (gitdir / "HEAD").write_text("ref: refs/heads/feature\n", encoding="utf-8")
    (gitdir / "commondir").write_text("../..\n", encoding="utf-8")
    (common_gitdir / "packed-refs").write_text(
        f"# pack-refs with: peeled fully-peeled sorted\n{fake_sha} refs/heads/feature\n",
        encoding="utf-8",
    )
    (source / ".git").write_text(
        "gitdir: ../source.git/worktrees/source\n",
        encoding="utf-8",
    )
    fixture = _write_fixture(
        tmp_path,
        {
            "schema_version": 1,
            "repos": [
                {
                    "repo_key": "sample",
                    "snapshot_path": str(source),
                    "profiles": ["ci"],
                    "queries": [
                        {
                            "id": "target",
                            "query": "targetToken",
                            "expected_top_k": [{"path": "src/App.java", "top_k": 5}],
                        }
                    ],
                }
            ],
        },
    )

    report = run_quality_fixture(
        fixture,
        profile="ci",
        output_path=None,
        markdown_path=None,
    )

    assert report["repos"][0]["source"]["git_commit"] == fake_sha


def test_quality_runner_records_skip_for_missing_repo(tmp_path: Path) -> None:
    fixture = _write_fixture(
        tmp_path,
        {
            "schema_version": 1,
            "repos": [
                {
                    "repo_key": "missing",
                    "snapshot_path": str(tmp_path / "missing"),
                    "profiles": ["smoke"],
                    "queries": [{"id": "q", "query": "anything"}],
                }
            ],
        },
    )

    report = run_quality_fixture(
        fixture,
        profile="smoke",
        output_path=None,
        markdown_path=None,
    )

    assert report["aggregate"]["skipped"] == 1
    assert report["cases"][0]["status"] == "skipped"
    assert report["cases"][0]["failures"] == ["repo not found"]


def test_ci_profile_rejects_env_only_repo_even_when_env_is_set(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    external = tmp_path / "external"
    external.mkdir()
    (external / "App.java").write_text("class App {}\n", encoding="utf-8")
    monkeypatch.setenv("CST_SMOKE_EXTERNAL_REPO", str(external))
    fixture = _write_fixture(
        tmp_path,
        {
            "schema_version": 1,
            "repos": [
                {
                    "repo_key": "external",
                    "path_env": "CST_SMOKE_EXTERNAL_REPO",
                    "profiles": ["ci"],
                    "queries": [{"id": "q", "query": "App"}],
                }
            ],
        },
    )

    with pytest.raises(ValueError, match="ci profile requires snapshot_path"):
        run_quality_fixture(
            fixture,
            profile="ci",
            output_path=None,
            markdown_path=None,
        )


def test_quality_runner_records_query_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _write_source_repo(tmp_path)
    fixture = _write_fixture(
        tmp_path,
        {
            "schema_version": 1,
            "repos": [
                {
                    "repo_key": "sample",
                    "snapshot_path": str(source),
                    "profiles": ["ci"],
                    "queries": [{"id": "target", "query": "targetToken"}],
                }
            ],
        },
    )

    def fail_query(*args: object, **kwargs: object) -> object:
        raise RuntimeError("query exploded")

    monkeypatch.setattr(
        "context_search_tool.quality.runner.query_repository",
        fail_query,
    )

    report = run_quality_fixture(
        fixture,
        profile="ci",
        output_path=None,
        markdown_path=None,
    )

    assert report["aggregate"]["errors"] == 1
    assert report["cases"][0]["status"] == "error"
    assert report["cases"][0]["failures"] == ["query exploded"]


def test_quality_runner_contains_copy_errors_and_continues_later_repos(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first_source = _write_source_repo(tmp_path / "first-source")
    second_source = _write_source_repo(tmp_path / "second-source")
    temp_root = tmp_path / "temp-root"
    fixture = _write_fixture(
        tmp_path,
        {
            "schema_version": 1,
            "repos": [
                {
                    "repo_key": "first",
                    "snapshot_path": str(first_source),
                    "profiles": ["ci"],
                    "queries": [{"id": "first-case", "query": "first"}],
                },
                {
                    "repo_key": "second",
                    "snapshot_path": str(second_source),
                    "profiles": ["ci"],
                    "queries": [{"id": "second-case", "query": "second"}],
                },
            ],
        },
    )
    captured: list[tuple[Path, ToolConfig]] = []
    _patch_runner_dependencies(monkeypatch, captured)
    original_copy = _copy_source_repo

    def copy_with_first_failure(source: Path, workspace: Path) -> None:
        if workspace.name == "first":
            workspace.mkdir()
            (workspace / "partial.txt").write_text("partial\n", encoding="utf-8")
            raise PermissionError("copy denied")
        original_copy(source, workspace)

    def fake_mkdtemp(*, prefix: str) -> str:
        assert prefix == "cst-quality-"
        temp_root.mkdir()
        return str(temp_root)

    monkeypatch.setattr(quality_runner, "_copy_source_repo", copy_with_first_failure)
    monkeypatch.setattr(quality_runner.tempfile, "mkdtemp", fake_mkdtemp)

    try:
        report = run_quality_fixture(
            fixture,
            profile="ci",
            output_path=None,
            markdown_path=None,
            keep_workspace=True,
        )

        assert [(case["case_id"], case["status"]) for case in report["cases"]] == [
            ("first-case", "error"),
            ("second-case", "pass"),
        ]
        assert report["cases"][0]["failures"] == ["copy denied"]
        assert [repo["repo_key"] for repo in report["repos"]] == ["second"]
        assert [workspace.name for workspace, _config in captured] == ["second"]
        assert not (temp_root / "first").exists()
        assert (temp_root / "second").is_dir()
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


@pytest.mark.parametrize(
    ("failure_stage", "reason"),
    [
        pytest.param("git_commit", "git metadata denied", id="git-commit"),
        pytest.param("content_identity", "identity denied", id="content-identity"),
    ],
)
def test_quality_runner_contains_post_index_setup_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure_stage: str,
    reason: str,
) -> None:
    first_source = _write_source_repo(tmp_path / "first-source").resolve()
    second_source = _write_source_repo(tmp_path / "second-source").resolve()
    temp_root = (tmp_path / "temp-root").resolve()
    fixture = _write_fixture(
        tmp_path,
        {
            "schema_version": 1,
            "repos": [
                {
                    "repo_key": "first",
                    "snapshot_path": str(first_source),
                    "profiles": ["ci"],
                    "queries": [{"id": "first-case", "query": "first"}],
                },
                {
                    "repo_key": "second",
                    "snapshot_path": str(second_source),
                    "profiles": ["ci"],
                    "queries": [{"id": "second-case", "query": "second"}],
                },
            ],
        },
    )
    captured: list[tuple[Path, ToolConfig]] = []
    _patch_runner_dependencies(monkeypatch, captured)

    if failure_stage == "git_commit":
        original_git_commit = quality_runner._git_commit

        def git_commit_with_first_failure(path: Path) -> str | None:
            if path == first_source:
                raise PermissionError(reason)
            return original_git_commit(path)

        monkeypatch.setattr(
            quality_runner,
            "_git_commit",
            git_commit_with_first_failure,
        )
    else:
        original_content_identity = _content_identity

        def content_identity_with_first_failure(path: Path) -> str:
            if path == first_source or path == temp_root / "first":
                raise PermissionError(reason)
            return original_content_identity(path)

        monkeypatch.setattr(
            quality_runner,
            "_content_identity",
            content_identity_with_first_failure,
        )

    def fake_mkdtemp(*, prefix: str) -> str:
        assert prefix == "cst-quality-"
        temp_root.mkdir()
        return str(temp_root)

    monkeypatch.setattr(quality_runner.tempfile, "mkdtemp", fake_mkdtemp)

    try:
        report = run_quality_fixture(
            fixture,
            profile="ci",
            output_path=None,
            markdown_path=None,
            keep_workspace=True,
        )

        assert [(case["case_id"], case["status"]) for case in report["cases"]] == [
            ("first-case", "error"),
            ("second-case", "pass"),
        ]
        assert report["cases"][0]["failures"] == [reason]
        assert [repo["repo_key"] for repo in report["repos"]] == ["second"]
        assert [workspace.name for workspace, _config in captured] == [
            "first",
            "second",
        ]
        assert not (temp_root / "first").exists()
        assert (temp_root / "second").is_dir()
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_canonical_profile_rebuilds_from_default_then_repo_then_profile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "snapshot"
    source.mkdir()
    (source / "source.txt").write_text("source\n", encoding="utf-8")
    fixture = _write_fixture(
        tmp_path,
        {
            "schema_version": 1,
            "profile_configs": {
                "ci": {
                    "embedding": {
                        "provider": "hash",
                        "model": "hash-v1",
                        "dimensions": 384,
                    },
                    "query_planner": {"enabled": False},
                }
            },
            "repos": [
                {
                    "repo_key": "sample",
                    "snapshot_path": "snapshot",
                    "profiles": ["ci"],
                    "default_config": {"retrieval": {"final_top_k": 7}},
                    "queries": [{"id": "target", "query": "target"}],
                }
            ],
        },
    )
    stale_config = ToolConfig(
        index=IndexConfig(max_file_bytes=1),
        retrieval=RetrievalConfig(final_top_k=99),
        embedding=EmbeddingConfig(
            provider="openai-compatible",
            model="remote-embedding",
            dimensions=1536,
            base_url="https://embedding.example.test/v1",
            api_key_env="REMOTE_EMBEDDING_API_KEY",
        ),
        query_planner=QueryPlannerConfig(
            enabled=True,
            provider="openai-compatible",
            model="remote-planner",
            base_url="https://planner.example.test/v1",
            use_system_proxy=True,
            timeout_seconds=99,
        ),
    )
    captured: list[tuple[Path, ToolConfig]] = []
    _patch_runner_dependencies(monkeypatch, captured)

    run_quality_fixture(
        fixture,
        profile="ci",
        output_path=None,
        markdown_path=None,
        config=stale_config,
    )

    effective = captured[0][1]
    assert effective.index == DEFAULT_CONFIG.index
    assert effective.embedding == DEFAULT_CONFIG.embedding
    assert effective.query_planner == DEFAULT_CONFIG.query_planner
    assert effective.retrieval.final_top_k == 7


def test_legacy_fixture_keeps_caller_base_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "snapshot"
    source.mkdir()
    fixture = _write_fixture(
        tmp_path,
        {
            "schema_version": 1,
            "repos": [
                {
                    "repo_key": "sample",
                    "snapshot_path": "snapshot",
                    "profiles": ["smoke"],
                    "queries": [{"id": "target", "query": "target"}],
                }
            ],
        },
    )
    caller_config = ToolConfig(
        index=IndexConfig(max_file_bytes=1234),
        retrieval=RetrievalConfig(final_top_k=9),
    )
    captured: list[tuple[Path, ToolConfig]] = []
    _patch_runner_dependencies(monkeypatch, captured)

    run_quality_fixture(
        fixture,
        profile="smoke",
        output_path=None,
        markdown_path=None,
        config=caller_config,
    )

    effective = captured[0][1]
    assert effective.index.max_file_bytes == 1234
    assert effective.retrieval.final_top_k == 9


def test_non_ci_source_prefers_existing_env_then_smoke_root_then_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env_repo = tmp_path / "env-repo"
    env_repo.mkdir()
    smoke_root = tmp_path / "smoke"
    smoke_repo = smoke_root / "sample"
    smoke_repo.mkdir(parents=True)
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    fixture_path = tmp_path / "quality.json"
    repo = QualityRepo(
        repo_key="sample",
        path_env="CST_SAMPLE_REPO",
        repo_dir_name="sample",
        snapshot_path="snapshot",
        profiles=("smoke",),
    )
    monkeypatch.setenv("CST_SAMPLE_REPO", str(env_repo))
    monkeypatch.setenv("CST_SMOKE_REPOS_DIR", str(smoke_root))

    assert _resolve_repo_source(repo, fixture_path, "smoke") == ResolvedSource(
        env_repo.resolve(),
        "path_env",
        "CST_SAMPLE_REPO",
    )

    monkeypatch.setenv("CST_SAMPLE_REPO", str(tmp_path / "missing-env"))
    assert _resolve_repo_source(repo, fixture_path, "smoke") == ResolvedSource(
        smoke_repo.resolve(),
        "smoke_root",
        "sample",
    )

    smoke_repo.rmdir()
    assert _resolve_repo_source(repo, fixture_path, "smoke") == ResolvedSource(
        snapshot.resolve(),
        "snapshot_path",
        "snapshot",
    )


def test_runner_executes_only_cases_selected_by_profile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "snapshot"
    source.mkdir()
    fixture = _write_fixture(
        tmp_path,
        {
            "schema_version": 1,
            "profile_configs": {
                "ci": {
                    "embedding": {
                        "provider": "hash",
                        "model": "hash-v1",
                        "dimensions": 384,
                    },
                    "query_planner": {"enabled": False},
                },
                "smoke": {
                    "embedding": {
                        "provider": "hash",
                        "model": "hash-v1",
                        "dimensions": 384,
                    },
                    "query_planner": {"enabled": False},
                },
            },
            "repos": [
                {
                    "repo_key": "sample",
                    "snapshot_path": "snapshot",
                    "profiles": ["ci", "smoke"],
                    "queries": [
                        {
                            "id": "ci-only",
                            "query": "ci query",
                            "profiles": ["ci"],
                        },
                        {
                            "id": "smoke-only",
                            "query": "smoke query",
                            "profiles": ["smoke"],
                        },
                    ],
                }
            ],
        },
    )
    captured: list[tuple[Path, ToolConfig]] = []
    _patch_runner_dependencies(monkeypatch, captured)

    report = run_quality_fixture(
        fixture,
        profile="ci",
        output_path=None,
        markdown_path=None,
    )

    assert [case["case_id"] for case in report["cases"]] == ["ci-only"]
    with pytest.raises(ValueError, match="^unknown quality profile: missing$"):
        run_quality_fixture(
            fixture,
            profile="missing",
            output_path=None,
            markdown_path=None,
        )


@pytest.mark.parametrize(
    ("profile", "profile_config", "provider", "model", "dimensions", "planner"),
    [
        pytest.param(
            "ci",
            {
                "embedding": {
                    "provider": "hash",
                    "model": "hash-v1",
                    "dimensions": 384,
                },
                "query_planner": {"enabled": False},
            },
            "hash",
            "hash-v1",
            384,
            False,
            id="ci",
        ),
        pytest.param(
            "smoke",
            {
                "embedding": {
                    "provider": "hash",
                    "model": "hash-v1",
                    "dimensions": 384,
                },
                "query_planner": {"enabled": False},
            },
            "hash",
            "hash-v1",
            384,
            False,
            id="smoke",
        ),
        pytest.param(
            "planner",
            {
                "embedding": {
                    "provider": "hash",
                    "model": "hash-v1",
                    "dimensions": 384,
                },
                "query_planner": {"enabled": True, "provider": "ollama"},
            },
            "hash",
            "hash-v1",
            384,
            True,
            id="planner",
        ),
        pytest.param(
            "calibration_bge",
            {
                "embedding": {
                    "provider": "bge",
                    "model": "bge-m3",
                    "dimensions": 1024,
                },
                "query_planner": {"enabled": False},
            },
            "bge",
            "bge-m3",
            1024,
            False,
            id="calibration-bge",
        ),
        pytest.param(
            "ab_hash",
            {
                "embedding": {
                    "provider": "hash",
                    "model": "hash-v1",
                    "dimensions": 384,
                },
                "query_planner": {"enabled": False},
            },
            "hash",
            "hash-v1",
            384,
            False,
            id="ab-hash",
        ),
        pytest.param(
            "ab_bge",
            {
                "embedding": {
                    "provider": "bge",
                    "model": "bge-m3",
                    "dimensions": 1024,
                },
                "query_planner": {"enabled": False},
            },
            "bge",
            "bge-m3",
            1024,
            False,
            id="ab-bge",
        ),
    ],
)
def test_all_canonical_profiles_wire_without_external_dependencies(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    profile: str,
    profile_config: dict,
    provider: str,
    model: str,
    dimensions: int,
    planner: bool,
) -> None:
    source = tmp_path / "snapshot"
    source.mkdir()
    (source / "source.txt").write_text("source\n", encoding="utf-8")
    case_id = f"{profile}-case"
    fixture = _write_fixture(
        tmp_path,
        {
            "schema_version": 1,
            "profile_configs": {profile: profile_config},
            "repos": [
                {
                    "repo_key": "sample",
                    "snapshot_path": "snapshot",
                    "profiles": [profile],
                    "queries": [
                        {
                            "id": case_id,
                            "query": "target",
                            "profiles": [profile],
                        }
                    ],
                }
            ],
        },
    )
    captured: list[tuple[Path, ToolConfig]] = []
    _patch_runner_dependencies(monkeypatch, captured)

    report = run_quality_fixture(
        fixture,
        profile=profile,
        output_path=None,
        markdown_path=None,
        keep_workspace=True,
    )

    workspace, effective = captured[0]
    try:
        assert [case["case_id"] for case in report["cases"]] == [case_id]
        assert effective.embedding.provider == provider
        assert effective.embedding.model == model
        assert effective.embedding.dimensions == dimensions
        assert effective.query_planner.enabled is planner
        assert (workspace / "source.txt").is_file()
    finally:
        shutil.rmtree(workspace.parent, ignore_errors=True)


@pytest.mark.parametrize(
    "unsafe_repo_key",
    [
        pytest.param("<absolute>", id="absolute"),
        pytest.param("..", id="parent"),
        pytest.param("../escape", id="parent-child"),
        pytest.param("a/b", id="forward-slash"),
        pytest.param(r"a\b", id="backslash"),
        pytest.param("./alias", id="dot-alias"),
        pytest.param("C:repo", id="windows-drive-relative"),
        pytest.param("CON", id="windows-reserved"),
        pytest.param("con.txt", id="windows-reserved-extension"),
        pytest.param("repo.", id="trailing-dot"),
        pytest.param("repo ", id="trailing-space"),
    ],
)
def test_quality_runner_rejects_unsafe_repo_keys_without_leaking_workspace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    unsafe_repo_key: str,
) -> None:
    source = _write_source_repo(tmp_path)
    temp_root = tmp_path / "temp-root"
    absolute_escape = tmp_path / "absolute-escape"
    parent_escape = tmp_path / "escape"
    repo_key = (
        str(absolute_escape) if unsafe_repo_key == "<absolute>" else unsafe_repo_key
    )
    fixture = _write_fixture(
        tmp_path,
        {
            "schema_version": 1,
            "repos": [
                {
                    "repo_key": repo_key,
                    "snapshot_path": str(source),
                    "profiles": ["ci"],
                    "queries": [{"id": "target", "query": "targetToken"}],
                }
            ],
        },
    )
    captured: list[tuple[Path, ToolConfig]] = []
    _patch_runner_dependencies(monkeypatch, captured)

    def fake_mkdtemp(*, prefix: str) -> str:
        assert prefix == "cst-quality-"
        temp_root.mkdir()
        return str(temp_root)

    monkeypatch.setattr(
        "context_search_tool.quality.runner.tempfile.mkdtemp",
        fake_mkdtemp,
    )

    try:
        with pytest.raises(ValueError, match=r"repo_key.*safe.*component"):
            run_quality_fixture(
                fixture,
                profile="ci",
                output_path=None,
                markdown_path=None,
            )
        assert not temp_root.exists()
        assert not absolute_escape.exists()
        assert not parent_escape.exists()
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)
        shutil.rmtree(absolute_escape, ignore_errors=True)
        shutil.rmtree(parent_escape, ignore_errors=True)


@pytest.mark.parametrize(
    ("first_key", "second_key"),
    [
        pytest.param("repo", "REPO", id="casefold"),
        pytest.param("caf\u00e9", "cafe\u0301", id="unicode-nfc"),
    ],
)
def test_quality_runner_rejects_duplicate_workspace_repo_key_aliases(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    first_key: str,
    second_key: str,
) -> None:
    source = _write_source_repo(tmp_path)
    temp_root = tmp_path / "temp-root"
    fixture = _write_fixture(
        tmp_path,
        {
            "schema_version": 1,
            "repos": [
                {
                    "repo_key": first_key,
                    "snapshot_path": str(source),
                    "profiles": ["ci"],
                    "queries": [{"id": "first", "query": "first"}],
                },
                {
                    "repo_key": second_key,
                    "snapshot_path": str(source),
                    "profiles": ["ci"],
                    "queries": [{"id": "second", "query": "second"}],
                },
            ],
        },
    )
    captured: list[tuple[Path, ToolConfig]] = []
    _patch_runner_dependencies(monkeypatch, captured)

    def fake_mkdtemp(*, prefix: str) -> str:
        assert prefix == "cst-quality-"
        temp_root.mkdir()
        return str(temp_root)

    monkeypatch.setattr(quality_runner.tempfile, "mkdtemp", fake_mkdtemp)

    with pytest.raises(ValueError, match=r"duplicate workspace repo_key"):
        run_quality_fixture(
            fixture,
            profile="ci",
            output_path=None,
            markdown_path=None,
        )

    assert [workspace.name for workspace, _config in captured] == [first_key]
    assert not temp_root.exists()


@pytest.mark.parametrize("repo_key", ["sample_repo", "sample-repo", "仓库"])
def test_quality_runner_keeps_safe_repo_keys_inside_temp_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    repo_key: str,
) -> None:
    source = _write_source_repo(tmp_path)
    temp_root = tmp_path / "temp-root"
    fixture = _write_fixture(
        tmp_path,
        {
            "schema_version": 1,
            "repos": [
                {
                    "repo_key": repo_key,
                    "snapshot_path": str(source),
                    "profiles": ["ci"],
                    "queries": [{"id": "target", "query": "targetToken"}],
                }
            ],
        },
    )
    captured: list[tuple[Path, ToolConfig]] = []
    _patch_runner_dependencies(monkeypatch, captured)

    def fake_mkdtemp(*, prefix: str) -> str:
        assert prefix == "cst-quality-"
        temp_root.mkdir()
        return str(temp_root)

    monkeypatch.setattr(
        "context_search_tool.quality.runner.tempfile.mkdtemp",
        fake_mkdtemp,
    )

    try:
        report = run_quality_fixture(
            fixture,
            profile="ci",
            output_path=None,
            markdown_path=None,
            keep_workspace=True,
        )

        workspace = captured[0][0]
        assert workspace == (temp_root / repo_key).resolve()
        assert workspace.parent == temp_root.resolve()
        assert report["repos"][0]["workspace"]["path"] == str(workspace)
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


@pytest.mark.parametrize(
    "unsafe_repo_dir_name",
    [
        pytest.param("<absolute>", id="absolute"),
        pytest.param("..", id="parent"),
        pytest.param("../external", id="parent-child"),
        pytest.param("a/b", id="forward-slash"),
        pytest.param(r"a\b", id="backslash"),
        pytest.param("C:repo", id="windows-drive-relative"),
        pytest.param("AUX", id="windows-reserved"),
        pytest.param("lpt9.log", id="windows-reserved-extension"),
        pytest.param("repo.", id="trailing-dot"),
        pytest.param("repo ", id="trailing-space"),
    ],
)
def test_smoke_source_rejects_unsafe_repo_dir_names(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    unsafe_repo_dir_name: str,
) -> None:
    smoke_root = tmp_path / "smoke"
    smoke_root.mkdir()
    external = tmp_path / "external"
    external.mkdir()
    (smoke_root / "a" / "b").mkdir(parents=True)
    (smoke_root / r"a\b").mkdir()
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    repo_dir_name = (
        str(external)
        if unsafe_repo_dir_name == "<absolute>"
        else unsafe_repo_dir_name
    )
    repo = QualityRepo(
        repo_key="sample",
        repo_dir_name=repo_dir_name,
        snapshot_path=str(snapshot),
        profiles=("smoke",),
    )
    monkeypatch.setenv("CST_SMOKE_REPOS_DIR", str(smoke_root))

    with pytest.raises(ValueError, match=r"repo_dir_name.*safe.*component"):
        _resolve_repo_source(repo, tmp_path / "quality.json", "smoke")


def test_smoke_source_rejects_child_symlink_escaping_resolved_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    smoke_root = tmp_path / "smoke"
    smoke_root.mkdir()
    external = tmp_path / "external"
    external.mkdir()
    (smoke_root / "sample").symlink_to(external, target_is_directory=True)
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    repo = QualityRepo(
        repo_key="sample",
        repo_dir_name="sample",
        snapshot_path=str(snapshot),
        profiles=("smoke",),
    )
    monkeypatch.setenv("CST_SMOKE_REPOS_DIR", str(smoke_root))

    with pytest.raises(ValueError, match=r"repo_dir_name.*escape"):
        _resolve_repo_source(repo, tmp_path / "quality.json", "smoke")


def test_smoke_source_keeps_safe_child_and_component_locator(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    smoke_root = tmp_path / "smoke"
    source = smoke_root / "safe_repo-仓库"
    source.mkdir(parents=True)
    repo = QualityRepo(
        repo_key="sample",
        repo_dir_name="safe_repo-仓库",
        profiles=("smoke",),
    )
    monkeypatch.setenv("CST_SMOKE_REPOS_DIR", str(smoke_root))

    assert _resolve_repo_source(
        repo,
        tmp_path / "quality.json",
        "smoke",
    ) == ResolvedSource(
        source.resolve(),
        "smoke_root",
        "safe_repo-仓库",
    )


@pytest.mark.parametrize(
    "snapshot_path",
    [
        pytest.param("../private", id="parent"),
        pytest.param("snapshots/../../private", id="nested-parent"),
        pytest.param(r"..\private", id="backslash-parent"),
        pytest.param(r"snapshots\..\private", id="nested-backslash-parent"),
        pytest.param(r"\private", id="rooted-backslash"),
        pytest.param(r"C:\private", id="windows-drive"),
    ],
)
def test_snapshot_source_rejects_unsafe_relative_paths(
    tmp_path: Path,
    snapshot_path: str,
) -> None:
    fixture_dir = tmp_path / "fixtures"
    fixture_dir.mkdir()
    (tmp_path / "private").mkdir()
    repo = QualityRepo(
        repo_key="sample",
        snapshot_path=snapshot_path,
        profiles=("ci",),
    )

    with pytest.raises(ValueError, match=r"snapshot_path.*safe relative"):
        _resolve_repo_source(repo, fixture_dir / "quality.json", "ci")


@pytest.mark.parametrize(
    ("snapshot_path", "locator"),
    [
        pytest.param("snapshots/nested", "snapshots/nested", id="posix"),
        pytest.param(r"snapshots\nested", "snapshots/nested", id="backslash"),
        pytest.param("./snapshots/nested", "snapshots/nested", id="dot"),
    ],
)
def test_snapshot_source_normalizes_safe_nested_relative_paths(
    tmp_path: Path,
    snapshot_path: str,
    locator: str,
) -> None:
    fixture_dir = tmp_path / "fixtures"
    source = fixture_dir / "snapshots" / "nested"
    source.mkdir(parents=True)
    repo = QualityRepo(
        repo_key="sample",
        snapshot_path=snapshot_path,
        profiles=("ci",),
    )

    assert _resolve_repo_source(
        repo,
        fixture_dir / "quality.json",
        "ci",
    ) == ResolvedSource(
        source.resolve(),
        "snapshot_path",
        locator,
    )


def test_snapshot_source_allows_absolute_directory_with_redacted_locator(
    tmp_path: Path,
) -> None:
    source = tmp_path / "absolute-source"
    source.mkdir()
    repo = QualityRepo(
        repo_key="sample",
        snapshot_path=str(source),
        profiles=("ci",),
    )

    assert _resolve_repo_source(
        repo,
        tmp_path / "quality.json",
        "ci",
    ) == ResolvedSource(
        source.resolve(),
        "snapshot_path",
        "absolute-source",
    )


def test_snapshot_source_rejects_relative_symlink_escape(tmp_path: Path) -> None:
    fixture_dir = tmp_path / "fixtures"
    fixture_dir.mkdir()
    external = tmp_path / "external"
    external.mkdir()
    (fixture_dir / "snapshot").symlink_to(external, target_is_directory=True)
    repo = QualityRepo(
        repo_key="sample",
        snapshot_path="snapshot",
        profiles=("ci",),
    )

    with pytest.raises(ValueError, match=r"snapshot_path.*escape"):
        _resolve_repo_source(repo, fixture_dir / "quality.json", "ci")


def test_snapshot_source_rejects_absolute_top_level_symlink(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    snapshot_link = tmp_path / "snapshot-link"
    snapshot_link.symlink_to(source, target_is_directory=True)
    repo = QualityRepo(
        repo_key="sample",
        snapshot_path=str(snapshot_link),
        profiles=("ci",),
    )

    with pytest.raises(ValueError, match=r"snapshot_path.*symlink"):
        _resolve_repo_source(repo, tmp_path / "quality.json", "ci")


def test_copy_source_repo_ignores_nested_file_and_directory_symlinks(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    nested = source / "nested"
    nested.mkdir(parents=True)
    (source / "normal.txt").write_text("normal\n", encoding="utf-8")
    external_file = tmp_path / "external.txt"
    external_file.write_text("private\n", encoding="utf-8")
    external_dir = tmp_path / "external-dir"
    external_dir.mkdir()
    (external_dir / "private.txt").write_text("private\n", encoding="utf-8")
    contained_file = source / "contained.txt"
    contained_file.write_text("contained\n", encoding="utf-8")
    contained_dir = source / "contained-dir"
    contained_dir.mkdir()
    (contained_dir / "value.txt").write_text("contained\n", encoding="utf-8")
    (nested / "file-link.txt").symlink_to(external_file)
    (nested / "dir-link").symlink_to(external_dir, target_is_directory=True)
    (nested / "contained-file-link.txt").symlink_to(contained_file)
    (nested / "contained-dir-link").symlink_to(
        contained_dir,
        target_is_directory=True,
    )
    workspace = tmp_path / "workspace"

    _copy_source_repo(source, workspace)

    assert (workspace / "normal.txt").read_text(encoding="utf-8") == "normal\n"
    assert not (workspace / "nested" / "file-link.txt").exists()
    assert not (workspace / "nested" / "file-link.txt").is_symlink()
    assert not (workspace / "nested" / "dir-link").exists()
    assert not (workspace / "nested" / "dir-link").is_symlink()
    assert (workspace / "contained.txt").is_file()
    assert (workspace / "contained-dir" / "value.txt").is_file()
    assert not (workspace / "nested" / "contained-file-link.txt").exists()
    assert not (workspace / "nested" / "contained-file-link.txt").is_symlink()
    assert not (workspace / "nested" / "contained-dir-link").exists()
    assert not (workspace / "nested" / "contained-dir-link").is_symlink()


def test_copy_source_repo_omits_junction_entries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source"
    junction = source / "junction"
    junction.mkdir(parents=True)
    (junction / "private.txt").write_text("private\n", encoding="utf-8")
    (source / "normal.txt").write_text("normal\n", encoding="utf-8")
    workspace = tmp_path / "workspace"
    original_is_junction = getattr(Path, "is_junction", None)

    def fake_is_junction(path: Path) -> bool:
        if path.name == "junction":
            return True
        return original_is_junction(path) if original_is_junction else False

    monkeypatch.setattr(Path, "is_junction", fake_is_junction, raising=False)

    _copy_source_repo(source, workspace)

    assert (workspace / "normal.txt").is_file()
    assert not (workspace / "junction").exists()


def test_copy_source_repo_omits_non_regular_files(tmp_path: Path) -> None:
    if not hasattr(os, "mkfifo"):
        pytest.skip("FIFO creation is not supported on this platform")

    source = tmp_path / "source"
    source.mkdir()
    (source / "normal.txt").write_text("normal\n", encoding="utf-8")
    os.mkfifo(source / "named-pipe")
    workspace = tmp_path / "workspace"

    _copy_source_repo(source, workspace)

    assert (workspace / "normal.txt").is_file()
    assert not (workspace / "named-pipe").exists()


def test_copy_source_repo_does_not_follow_directory_swapped_to_symlink(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if not (
        os.name == "posix"
        and hasattr(os, "O_DIRECTORY")
        and hasattr(os, "O_NOFOLLOW")
        and os.open in os.supports_dir_fd
        and os.scandir in os.supports_fd
    ):
        pytest.skip("descriptor-based no-follow copy is not supported")

    source = tmp_path / "source"
    swappable = source / "swappable"
    swappable.mkdir(parents=True)
    (swappable / "ordinary.txt").write_text("ordinary\n", encoding="utf-8")
    external = tmp_path / "external"
    external.mkdir()
    secret = "external-secret-token"
    (external / "secret.txt").write_text(secret, encoding="utf-8")
    workspace = tmp_path / "workspace"
    moved = source / "swappable-original"
    original_open = os.open
    swapped = False

    def racing_open(
        path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        nonlocal swapped
        if dir_fd is not None and os.fspath(path) == "swappable" and not swapped:
            swappable.rename(moved)
            swappable.symlink_to(external, target_is_directory=True)
            swapped = True
        if dir_fd is None:
            return original_open(path, flags, mode)
        return original_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(quality_runner.os, "open", racing_open)

    try:
        _copy_source_repo(source, workspace)
    except OSError:
        pass

    assert swapped
    copied_contents = [
        path.read_text(encoding="utf-8")
        for path in workspace.rglob("*")
        if path.is_file() and not path.is_symlink()
    ]
    assert secret not in copied_contents


def test_quality_runner_hashes_the_copied_workspace_input(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _write_source_repo(tmp_path)
    source_file = source / "src" / "App.java"
    external = tmp_path / "external.txt"
    external.write_text("external-v1\n", encoding="utf-8")
    (source / "external-link.txt").symlink_to(external)
    fixture = _write_fixture(
        tmp_path,
        {
            "schema_version": 1,
            "repos": [
                {
                    "repo_key": "sample",
                    "snapshot_path": str(source),
                    "profiles": ["ci"],
                    "queries": [{"id": "target", "query": "target"}],
                }
            ],
        },
    )
    captured: list[tuple[Path, ToolConfig]] = []
    _patch_runner_dependencies(monkeypatch, captured)

    def index_then_change_source(repo: Path, config: ToolConfig) -> IndexSummary:
        captured.append((repo, config))
        source_file.write_text("changed-after-copy\n", encoding="utf-8")
        external.write_text("external-v2\n", encoding="utf-8")
        return IndexSummary(
            files_seen=1,
            files_indexed=1,
            files_skipped=0,
            files_deleted=0,
            chunks_indexed=1,
        )

    monkeypatch.setattr(quality_runner, "index_repository", index_then_change_source)

    report = run_quality_fixture(
        fixture,
        profile="ci",
        output_path=None,
        markdown_path=None,
        keep_workspace=True,
    )

    workspace = captured[0][0]
    try:
        content_hash = report["repos"][0]["source"]["content_hash"]
        assert content_hash == _content_identity(workspace)
        assert content_hash != _content_identity(source)
        assert not (workspace / "external-link.txt").exists()
        assert not (workspace / "external-link.txt").is_symlink()
    finally:
        shutil.rmtree(workspace.parent, ignore_errors=True)


def test_quality_runner_content_hash_ignores_external_symlink_target_changes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _write_source_repo(tmp_path)
    external = tmp_path / "external.txt"
    external.write_text("external-v1\n", encoding="utf-8")
    (source / "external-link.txt").symlink_to(external)
    fixture = _write_fixture(
        tmp_path,
        {
            "schema_version": 1,
            "repos": [
                {
                    "repo_key": "sample",
                    "snapshot_path": str(source),
                    "profiles": ["ci"],
                    "queries": [{"id": "target", "query": "target"}],
                }
            ],
        },
    )
    captured: list[tuple[Path, ToolConfig]] = []
    _patch_runner_dependencies(monkeypatch, captured)

    first_report = run_quality_fixture(
        fixture,
        profile="ci",
        output_path=None,
        markdown_path=None,
    )
    external.write_text("external-v2\n", encoding="utf-8")
    second_report = run_quality_fixture(
        fixture,
        profile="ci",
        output_path=None,
        markdown_path=None,
    )

    assert (
        first_report["repos"][0]["source"]["content_hash"]
        == second_report["repos"][0]["source"]["content_hash"]
    )


def test_content_identity_skips_symlink_files_but_hashes_normal_files(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    normal = source / "normal.txt"
    normal.write_text("normal-v1\n", encoding="utf-8")
    external = tmp_path / "external.txt"
    external.write_text("external-v1\n", encoding="utf-8")
    (source / "external-link.txt").symlink_to(external)

    original_identity = _content_identity(source)
    external.write_text("external-v2\n", encoding="utf-8")
    after_external_change = _content_identity(source)

    assert after_external_change == original_identity

    normal.write_text("normal-v2\n", encoding="utf-8")
    assert _content_identity(source) != after_external_change


def test_effective_config_copies_base_and_default_index_lists() -> None:
    original_default_include = list(DEFAULT_CONFIG.index.include)
    original_default_exclude = list(DEFAULT_CONFIG.index.exclude)
    custom_base = ToolConfig(
        index=IndexConfig(include=["base-include"], exclude=["base-exclude"])
    )

    try:
        custom_first = _effective_config(custom_base, {}, {})
        custom_second = _effective_config(custom_base, {}, {})
        default_first = _effective_config(DEFAULT_CONFIG, {}, {})
        default_second = _effective_config(DEFAULT_CONFIG, {}, {})

        custom_first.index.include.append("mutated-include")
        custom_first.index.exclude.append("mutated-exclude")
        default_first.index.include.append("mutated-default-include")
        default_first.index.exclude.append("mutated-default-exclude")

        assert custom_base.index.include == ["base-include"]
        assert custom_base.index.exclude == ["base-exclude"]
        assert custom_second.index.include == ["base-include"]
        assert custom_second.index.exclude == ["base-exclude"]
        assert DEFAULT_CONFIG.index.include == original_default_include
        assert DEFAULT_CONFIG.index.exclude == original_default_exclude
        assert default_second.index.include == original_default_include
        assert default_second.index.exclude == original_default_exclude
    finally:
        DEFAULT_CONFIG.index.include[:] = original_default_include
        DEFAULT_CONFIG.index.exclude[:] = original_default_exclude


def test_effective_config_copies_repo_and_profile_override_lists() -> None:
    repo_include = ["repo-include"]
    profile_exclude = ["profile-exclude"]
    repo_overrides = {"index": {"include": repo_include}}
    profile_overrides = {"index": {"exclude": profile_exclude}}

    first = _effective_config(DEFAULT_CONFIG, repo_overrides, profile_overrides)
    second = _effective_config(DEFAULT_CONFIG, repo_overrides, profile_overrides)
    first.index.include.append("mutated-include")
    first.index.exclude.append("mutated-exclude")

    assert repo_include == ["repo-include"]
    assert profile_exclude == ["profile-exclude"]
    assert second.index.include == ["repo-include"]
    assert second.index.exclude == ["profile-exclude"]
