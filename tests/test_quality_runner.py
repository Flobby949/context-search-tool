import json
from pathlib import Path

import pytest

from context_search_tool.quality.runner import run_quality_fixture


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
