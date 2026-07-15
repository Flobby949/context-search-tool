from __future__ import annotations

import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

import context_search_tool.quality.prepare as quality_prepare
from context_search_tool.quality.__main__ import quality_app
from context_search_tool.quality.cases import QualityRepo, load_quality_fixture
from context_search_tool.quality.prepare import (
    PROVENANCE_FILENAME,
    _git,
    prepare_quality_fixture,
    validate_prepared_repo,
)


def _run_git(*args: str, cwd: Path | None = None) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        shell=False,
    ).stdout.strip()


@pytest.fixture
def local_remote(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[str, str, str]:
    work = tmp_path / "upstream-work"
    work.mkdir()
    _run_git("init", cwd=work)
    _run_git("config", "user.email", "quality@example.test", cwd=work)
    _run_git("config", "user.name", "Quality Test", cwd=work)
    (work / "App.java").write_text("class First {}\n", encoding="utf-8")
    _run_git("add", "--", "App.java", cwd=work)
    _run_git("commit", "-m", "first", cwd=work)
    first_commit = _run_git("rev-parse", "HEAD", cwd=work)
    (work / "App.java").write_text("class Second {}\n", encoding="utf-8")
    _run_git("add", "--", "App.java", cwd=work)
    _run_git("commit", "-m", "second", cwd=work)
    second_commit = _run_git("rev-parse", "HEAD", cwd=work)

    bare = tmp_path / "remote.git"
    _run_git("clone", "--bare", "--", str(work), str(bare))
    source_url = "https://quality.example.test/remote.git"
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv(
        "GIT_CONFIG_KEY_0",
        "url.file://" + bare.parent.as_posix() + "/.insteadOf",
    )
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", "https://quality.example.test/")
    return source_url, first_commit, second_commit


def _write_remote_fixture(
    tmp_path: Path,
    source_url: str,
    source_commit: str,
    *,
    checkout_dir: str = "prepared-repo",
    profile: str = "p2_real_context",
) -> Path:
    fixture = tmp_path / "quality.json"
    fixture.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "profile_configs": {
                    profile: {
                        "retrieval": {"final_top_k": 12},
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
                        "repo_key": "sample_remote",
                        "source_url": source_url,
                        "source_commit": source_commit,
                        "checkout_dir": checkout_dir,
                        "profiles": [profile],
                        "queries": [{"id": "case", "query": "App"}],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return fixture


def _prepare_local_remote(
    tmp_path: Path,
    local_remote: tuple[str, str, str],
) -> tuple[Path, Path, str, str]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    source_url, first_commit, second_commit = local_remote
    fixture = _write_remote_fixture(tmp_path, source_url, second_commit)
    repos_dir = tmp_path / "repos"
    prepare_quality_fixture(fixture, "p2_real_context", repos_dir)
    return fixture, repos_dir, first_commit, second_commit


def test_git_uses_argument_array_and_never_a_shell(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured["argv"] = argv
        captured.update(kwargs)
        return subprocess.CompletedProcess(argv, 0, stdout="value\n", stderr="")

    monkeypatch.setattr(quality_prepare.subprocess, "run", fake_run)

    assert _git("rev-parse", "HEAD", cwd=Path("repo")) == "value"
    assert captured == {
        "argv": ["git", "rev-parse", "HEAD"],
        "cwd": Path("repo"),
        "check": True,
        "capture_output": True,
        "text": True,
        "shell": False,
    }


def test_prepare_clones_exact_detached_clean_checkout_and_writes_manifest(
    tmp_path: Path,
    local_remote: tuple[str, str, str],
) -> None:
    source_url, _, commit = local_remote
    fixture = _write_remote_fixture(tmp_path, source_url, commit)
    repos_dir = tmp_path / "repos"

    prepared = prepare_quality_fixture(fixture, "p2_real_context", repos_dir)

    checkout = repos_dir / "prepared-repo"
    assert [(item.repo_key, item.commit, item.checkout_dir) for item in prepared] == [
        ("sample_remote", commit, "prepared-repo")
    ]
    assert _run_git("rev-parse", "HEAD", cwd=checkout) == commit
    assert _run_git("rev-parse", "--abbrev-ref", "HEAD", cwd=checkout) == "HEAD"
    assert _run_git("config", "--get", "remote.origin.url", cwd=checkout) == source_url
    assert _run_git("status", "--porcelain", "--untracked-files=no", cwd=checkout) == ""
    manifest = json.loads(
        (repos_dir / PROVENANCE_FILENAME).read_text(encoding="utf-8")
    )
    assert manifest["schema_version"] == 1
    assert set(manifest["repos"]) == {"sample_remote"}
    record = manifest["repos"]["sample_remote"]
    assert {key: value for key, value in record.items() if key != "prepared_at"} == {
        "source_url": source_url,
        "source_commit": commit,
        "checkout_dir": "prepared-repo",
    }
    datetime.fromisoformat(record["prepared_at"].replace("Z", "+00:00"))


def test_prepare_is_idempotent_for_valid_owned_checkout(
    tmp_path: Path,
    local_remote: tuple[str, str, str],
) -> None:
    fixture, repos_dir, _, _ = _prepare_local_remote(tmp_path, local_remote)
    manifest_path = repos_dir / PROVENANCE_FILENAME
    first_manifest = manifest_path.read_bytes()
    first_inode = (repos_dir / "prepared-repo").stat().st_ino

    prepare_quality_fixture(fixture, "p2_real_context", repos_dir)

    assert manifest_path.read_bytes() == first_manifest
    assert (repos_dir / "prepared-repo").stat().st_ino == first_inode


def test_prepare_fetches_and_advances_an_owned_checkout_to_a_new_pinned_commit(
    tmp_path: Path,
    local_remote: tuple[str, str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_url, first_commit, second_commit = local_remote
    fixture = _write_remote_fixture(tmp_path, source_url, first_commit)
    repos_dir = tmp_path / "repos"
    prepare_quality_fixture(fixture, "p2_real_context", repos_dir)
    first_manifest = json.loads(
        (repos_dir / PROVENANCE_FILENAME).read_text(encoding="utf-8")
    )
    _write_remote_fixture(tmp_path, source_url, second_commit)
    calls: list[tuple[str, ...]] = []
    real_git = quality_prepare._git

    def capture_git(*args: str, cwd: Path | None = None) -> str:
        calls.append(args)
        return real_git(*args, cwd=cwd)

    monkeypatch.setattr(quality_prepare, "_git", capture_git)

    prepare_quality_fixture(fixture, "p2_real_context", repos_dir)

    checkout = repos_dir / "prepared-repo"
    assert ("fetch", "--", "origin", second_commit) in calls
    assert ("checkout", "--detach", second_commit) in calls
    assert _run_git("rev-parse", "HEAD", cwd=checkout) == second_commit
    assert _run_git("rev-parse", "--abbrev-ref", "HEAD", cwd=checkout) == "HEAD"
    assert _run_git("status", "--porcelain", "--untracked-files=no", cwd=checkout) == ""
    second_manifest = json.loads(
        (repos_dir / PROVENANCE_FILENAME).read_text(encoding="utf-8")
    )
    assert second_manifest["repos"]["sample_remote"]["source_commit"] == second_commit
    assert second_manifest["repos"]["sample_remote"]["prepared_at"] != (
        first_manifest["repos"]["sample_remote"]["prepared_at"]
    )

    calls.clear()
    prepare_quality_fixture(fixture, "p2_real_context", repos_dir)
    assert not any(call[0] in {"clone", "fetch", "checkout"} for call in calls)


def test_prepare_leaves_owned_checkout_unchanged_when_update_fetch_fails(
    tmp_path: Path,
    local_remote: tuple[str, str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_url, first_commit, second_commit = local_remote
    fixture = _write_remote_fixture(tmp_path, source_url, first_commit)
    repos_dir = tmp_path / "repos"
    prepare_quality_fixture(fixture, "p2_real_context", repos_dir)
    manifest_path = repos_dir / PROVENANCE_FILENAME
    first_manifest = manifest_path.read_bytes()
    _write_remote_fixture(tmp_path, source_url, second_commit)
    real_git = quality_prepare._git
    fetch_calls: list[tuple[str, ...]] = []

    def fail_fetch(*args: str, cwd: Path | None = None) -> str:
        if args[0] == "fetch":
            fetch_calls.append(args)
            raise subprocess.CalledProcessError(128, ["git", *args], stderr="secret")
        return real_git(*args, cwd=cwd)

    monkeypatch.setattr(quality_prepare, "_git", fail_fetch)

    with pytest.raises(ValueError, match="repository preparation failed") as exc_info:
        prepare_quality_fixture(fixture, "p2_real_context", repos_dir)

    checkout = repos_dir / "prepared-repo"
    assert fetch_calls == [("fetch", "--", "origin", second_commit)]
    assert "secret" not in str(exc_info.value)
    assert _run_git("rev-parse", "HEAD", cwd=checkout) == first_commit
    assert manifest_path.read_bytes() == first_manifest


def test_prepare_rolls_back_head_and_manifest_when_updated_manifest_write_fails(
    tmp_path: Path,
    local_remote: tuple[str, str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_url, first_commit, second_commit = local_remote
    fixture = _write_remote_fixture(tmp_path, source_url, first_commit)
    repos_dir = tmp_path / "repos"
    prepare_quality_fixture(fixture, "p2_real_context", repos_dir)
    manifest_path = repos_dir / PROVENANCE_FILENAME
    first_manifest = manifest_path.read_bytes()
    _write_remote_fixture(tmp_path, source_url, second_commit)
    real_write = quality_prepare._write_provenance
    written_commits: list[str] = []

    def fail_after_new_write(root: Path, manifest: dict[str, Any]) -> None:
        commit = manifest["repos"]["sample_remote"]["source_commit"]
        written_commits.append(commit)
        real_write(root, manifest)
        if commit == second_commit:
            raise OSError("simulated post-replace failure")

    monkeypatch.setattr(quality_prepare, "_write_provenance", fail_after_new_write)

    with pytest.raises(ValueError, match="repository preparation failed"):
        prepare_quality_fixture(fixture, "p2_real_context", repos_dir)

    checkout = repos_dir / "prepared-repo"
    assert written_commits == [second_commit, first_commit]
    assert _run_git("rev-parse", "HEAD", cwd=checkout) == first_commit
    assert _run_git("rev-parse", "--abbrev-ref", "HEAD", cwd=checkout) == "HEAD"
    assert _run_git("status", "--porcelain", "--untracked-files=no", cwd=checkout) == ""
    assert manifest_path.read_bytes() == first_manifest


def test_prepare_rolls_back_when_updated_checkout_fails_post_validation(
    tmp_path: Path,
    local_remote: tuple[str, str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_url, first_commit, second_commit = local_remote
    fixture = _write_remote_fixture(tmp_path, source_url, first_commit)
    repos_dir = tmp_path / "repos"
    prepare_quality_fixture(fixture, "p2_real_context", repos_dir)
    manifest_path = repos_dir / PROVENANCE_FILENAME
    first_manifest = manifest_path.read_bytes()
    _write_remote_fixture(tmp_path, source_url, second_commit)
    real_validate = quality_prepare._validate_checkout
    rejected_commits: list[str] = []

    def reject_new_checkout(checkout: Path, repo: QualityRepo) -> None:
        real_validate(checkout, repo)
        if repo.source_commit == second_commit:
            rejected_commits.append(repo.source_commit)
            raise ValueError("simulated post-check failure")

    monkeypatch.setattr(quality_prepare, "_validate_checkout", reject_new_checkout)

    with pytest.raises(ValueError, match="repository preparation failed"):
        prepare_quality_fixture(fixture, "p2_real_context", repos_dir)

    checkout = repos_dir / "prepared-repo"
    assert rejected_commits == [second_commit]
    assert _run_git("rev-parse", "HEAD", cwd=checkout) == first_commit
    assert manifest_path.read_bytes() == first_manifest


@pytest.mark.parametrize("corruption", ["head", "remote", "dirty"])
def test_prepare_rejects_corrupt_owned_checkout_before_fetching_update(
    tmp_path: Path,
    local_remote: tuple[str, str, str],
    monkeypatch: pytest.MonkeyPatch,
    corruption: str,
) -> None:
    source_url, first_commit, second_commit = local_remote
    fixture = _write_remote_fixture(tmp_path, source_url, first_commit)
    repos_dir = tmp_path / "repos"
    prepare_quality_fixture(fixture, "p2_real_context", repos_dir)
    checkout = repos_dir / "prepared-repo"
    manifest_path = repos_dir / PROVENANCE_FILENAME
    first_manifest = manifest_path.read_bytes()
    if corruption == "head":
        _run_git("checkout", "--detach", second_commit, cwd=checkout)
    elif corruption == "remote":
        _run_git(
            "remote",
            "set-url",
            "origin",
            "https://other.example.test/repo.git",
            cwd=checkout,
        )
    else:
        (checkout / "App.java").write_text("dirty\n", encoding="utf-8")
    _write_remote_fixture(tmp_path, source_url, second_commit)
    real_git = quality_prepare._git
    fetch_calls: list[tuple[str, ...]] = []

    def capture_git(*args: str, cwd: Path | None = None) -> str:
        if args[0] == "fetch":
            fetch_calls.append(args)
        return real_git(*args, cwd=cwd)

    monkeypatch.setattr(quality_prepare, "_git", capture_git)

    with pytest.raises(ValueError):
        prepare_quality_fixture(fixture, "p2_real_context", repos_dir)

    assert fetch_calls == []
    assert manifest_path.read_bytes() == first_manifest


@pytest.mark.parametrize("identity_field", ["source_url", "checkout_dir"])
def test_prepare_never_updates_when_catalog_identity_differs_from_provenance(
    tmp_path: Path,
    local_remote: tuple[str, str, str],
    monkeypatch: pytest.MonkeyPatch,
    identity_field: str,
) -> None:
    source_url, first_commit, second_commit = local_remote
    fixture = _write_remote_fixture(tmp_path, source_url, first_commit)
    repos_dir = tmp_path / "repos"
    prepare_quality_fixture(fixture, "p2_real_context", repos_dir)
    manifest_path = repos_dir / PROVENANCE_FILENAME
    first_manifest = manifest_path.read_bytes()
    if identity_field == "source_url":
        _write_remote_fixture(
            tmp_path,
            "https://other.example.test/remote.git",
            second_commit,
        )
    else:
        _write_remote_fixture(
            tmp_path,
            source_url,
            second_commit,
            checkout_dir="different-repo",
        )
    real_git = quality_prepare._git
    mutating_calls: list[tuple[str, ...]] = []

    def capture_git(*args: str, cwd: Path | None = None) -> str:
        if args[0] in {"clone", "fetch", "checkout"}:
            mutating_calls.append(args)
        return real_git(*args, cwd=cwd)

    monkeypatch.setattr(quality_prepare, "_git", capture_git)

    with pytest.raises(ValueError, match="provenance manifest does not match"):
        prepare_quality_fixture(fixture, "p2_real_context", repos_dir)

    assert mutating_calls == []
    assert manifest_path.read_bytes() == first_manifest
    assert not (repos_dir / "different-repo").exists()


@pytest.mark.parametrize("corruption", ["commit", "remote", "dirty"])
def test_prepare_rejects_invalid_existing_owned_checkout(
    tmp_path: Path,
    local_remote: tuple[str, str, str],
    corruption: str,
) -> None:
    fixture, repos_dir, first_commit, _ = _prepare_local_remote(
        tmp_path,
        local_remote,
    )
    checkout = repos_dir / "prepared-repo"
    if corruption == "commit":
        _run_git("checkout", "--detach", first_commit, cwd=checkout)
    elif corruption == "remote":
        _run_git(
            "remote",
            "set-url",
            "origin",
            "https://other.example.test/repo.git",
            cwd=checkout,
        )
    else:
        (checkout / "App.java").write_text("dirty\n", encoding="utf-8")

    with pytest.raises(ValueError, match="prepared checkout is invalid") as exc_info:
        prepare_quality_fixture(fixture, "p2_real_context", repos_dir)

    assert str(checkout) not in str(exc_info.value)
    assert checkout.exists()


def test_prepare_refuses_symlink_and_unrelated_nonempty_collisions(
    tmp_path: Path,
    local_remote: tuple[str, str, str],
) -> None:
    source_url, _, commit = local_remote
    fixture = _write_remote_fixture(tmp_path, source_url, commit)

    symlink_root = tmp_path / "symlink-repos"
    symlink_root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    marker = outside / "keep.txt"
    marker.write_text("keep", encoding="utf-8")
    (symlink_root / "prepared-repo").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="checkout collision"):
        prepare_quality_fixture(fixture, "p2_real_context", symlink_root)
    assert marker.read_text(encoding="utf-8") == "keep"

    collision_root = tmp_path / "collision-repos"
    target = collision_root / "prepared-repo"
    target.mkdir(parents=True)
    unrelated = target / "unrelated.txt"
    unrelated.write_text("keep", encoding="utf-8")
    with pytest.raises(ValueError, match="checkout collision"):
        prepare_quality_fixture(fixture, "p2_real_context", collision_root)
    assert unrelated.read_text(encoding="utf-8") == "keep"


def test_prepare_rejects_repositories_directory_beneath_symlinked_ancestor(
    tmp_path: Path,
    local_remote: tuple[str, str, str],
) -> None:
    source_url, _, commit = local_remote
    fixture = _write_remote_fixture(tmp_path, source_url, commit)
    outside = tmp_path / "outside"
    outside.mkdir()
    linked_parent = tmp_path / "linked-parent"
    linked_parent.symlink_to(outside, target_is_directory=True)

    with pytest.raises(ValueError, match="repositories directory is invalid"):
        prepare_quality_fixture(
            fixture,
            "p2_real_context",
            linked_parent / "repos",
        )

    assert not (outside / "repos").exists()


def test_prepare_rejects_malformed_or_mismatched_manifest(
    tmp_path: Path,
    local_remote: tuple[str, str, str],
) -> None:
    source_url, _, commit = local_remote
    fixture = _write_remote_fixture(tmp_path, source_url, commit)
    malformed_root = tmp_path / "malformed"
    malformed_root.mkdir()
    (malformed_root / PROVENANCE_FILENAME).write_text("{", encoding="utf-8")
    with pytest.raises(ValueError, match="provenance manifest is invalid"):
        prepare_quality_fixture(fixture, "p2_real_context", malformed_root)

    unsafe_root = tmp_path / "unsafe-manifest"
    unsafe_root.mkdir()
    (unsafe_root / PROVENANCE_FILENAME).write_text(
        json.dumps(
            {
                "schema_version": 1,
                "repos": {
                    "unrelated": {
                        "source_url": "https://example.test/repo.git",
                        "source_commit": "not-a-commit",
                        "checkout_dir": "../escape",
                        "prepared_at": "2026-07-15T00:00:00Z",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="provenance manifest is invalid"):
        prepare_quality_fixture(fixture, "p2_real_context", unsafe_root)

    fixture, repos_dir, _, _ = _prepare_local_remote(
        tmp_path / "mismatch",
        local_remote,
    )
    manifest_path = repos_dir / PROVENANCE_FILENAME
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["repos"]["sample_remote"]["source_commit"] = "0" * 40
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="provenance manifest does not match"):
        prepare_quality_fixture(fixture, "p2_real_context", repos_dir)


def test_prepare_sanitizes_git_failures_and_cleans_only_its_temporary_checkout(
    tmp_path: Path,
    local_remote: tuple[str, str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_url, _, commit = local_remote
    fixture = _write_remote_fixture(tmp_path, source_url, commit)
    repos_dir = tmp_path / "repos"
    repos_dir.mkdir()
    unrelated = repos_dir / "keep.txt"
    unrelated.write_text("keep", encoding="utf-8")

    def fail_git(*args: str, cwd: Path | None = None) -> str:
        raise subprocess.CalledProcessError(128, ["git", *args], stderr="secret")

    monkeypatch.setattr(quality_prepare, "_git", fail_git)

    with pytest.raises(ValueError, match="repository preparation failed") as exc_info:
        prepare_quality_fixture(fixture, "p2_real_context", repos_dir)

    assert "secret" not in str(exc_info.value)
    assert unrelated.read_text(encoding="utf-8") == "keep"
    assert not (repos_dir / "prepared-repo").exists()
    assert {path.name for path in repos_dir.iterdir()} == {"keep.txt"}


def test_prepare_requires_a_remote_repo_selected_by_profile(tmp_path: Path) -> None:
    fixture = tmp_path / "quality.json"
    fixture.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "profile_configs": {"custom": {}},
                "repos": [
                    {
                        "repo_key": "snapshot",
                        "profiles": ["custom"],
                        "snapshot_path": "snapshot",
                        "queries": [{"id": "case", "query": "App"}],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="no remote repositories"):
        prepare_quality_fixture(fixture, "custom", tmp_path / "repos")


def test_validate_prepared_repo_rechecks_checkout_and_manifest(
    tmp_path: Path,
    local_remote: tuple[str, str, str],
) -> None:
    fixture, repos_dir, _, _ = _prepare_local_remote(tmp_path, local_remote)
    repo = load_quality_fixture(fixture).repos[0]

    assert validate_prepared_repo(repo, repos_dir) == (
        repos_dir / "prepared-repo"
    ).resolve()

    (repos_dir / "prepared-repo" / "App.java").write_text(
        "dirty\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="prepared checkout is invalid"):
        validate_prepared_repo(repo, repos_dir)


def test_prepare_cli_uses_default_cache_and_prints_only_bounded_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = tmp_path / "quality.json"
    fixture.write_text("{}", encoding="utf-8")
    captured: dict[str, object] = {}

    def fake_prepare(fixture_path: Path, profile: str, repos_dir: Path):
        captured.update(
            fixture=fixture_path,
            profile=profile,
            repos_dir=repos_dir,
        )
        return (
            quality_prepare.PreparedRepository(
                repo_key="sample",
                commit="a" * 40,
                checkout_dir="repo",
            ),
        )

    monkeypatch.setattr(
        "context_search_tool.quality.__main__.prepare_quality_fixture",
        fake_prepare,
    )

    result = CliRunner().invoke(
        quality_app,
        ["prepare", str(fixture), "--profile", "p2_real_context"],
    )

    assert result.exit_code == 0
    assert captured == {
        "fixture": fixture,
        "profile": "p2_real_context",
        "repos_dir": Path(".quality/repos"),
    }
    assert result.output == f"repo=sample commit={'a' * 40} checkout=repo\n"
    assert "https://" not in result.output


def test_prepare_cli_sanitizes_catalog_and_git_failures(
    tmp_path: Path,
) -> None:
    secret = "credential-that-must-not-leak"
    fixture = tmp_path / "quality.json"
    fixture.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "profile_configs": {"p2_real_context": {}},
                "repos": [
                    {
                        "repo_key": "remote",
                        "source_url": f"https://user:{secret}@example.test/repo.git",
                        "source_commit": "a" * 40,
                        "checkout_dir": "repo",
                        "profiles": ["p2_real_context"],
                        "queries": [{"id": "case", "query": "owner"}],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        quality_app,
        [
            "prepare",
            str(fixture),
            "--profile",
            "p2_real_context",
            "--repos-dir",
            str(tmp_path / "repos"),
        ],
    )

    assert result.exit_code == 1
    assert result.output == "Error: quality repository preparation failed\n"
    assert secret not in result.output
    assert str(tmp_path) not in result.output


def test_run_cli_sanitizes_missing_prepared_repository_error(
    tmp_path: Path,
) -> None:
    fixture = _write_remote_fixture(
        tmp_path,
        "https://example.test/repo.git",
        "a" * 40,
    )

    result = CliRunner().invoke(
        quality_app,
        [
            "run",
            str(fixture),
            "--profile",
            "p2_real_context",
            "--repos-dir",
            str(tmp_path / "missing"),
            "--output",
            str(tmp_path / "report.json"),
        ],
    )

    assert result.exit_code == 1
    assert result.output == "Error: prepared quality repository validation failed\n"
    assert str(tmp_path) not in result.output
