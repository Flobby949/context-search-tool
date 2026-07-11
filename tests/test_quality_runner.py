import json
import shutil
from pathlib import Path

import pytest

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
