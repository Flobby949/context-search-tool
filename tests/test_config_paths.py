from pathlib import Path

import pytest

from context_search_tool.config import DEFAULT_CONFIG, load_config, render_default_config
from context_search_tool.paths import (
    RepositoryNotFoundError,
    find_repo_root,
    index_dir_for,
    ensure_index_layout,
)


def test_render_default_config_contains_version_one_values() -> None:
    rendered = render_default_config()
    assert "max_file_bytes = 500000" in rendered
    assert "max_full_file_bytes = 200000" in rendered
    assert "semantic_top_k = 80" in rendered
    assert DEFAULT_CONFIG.embedding.provider == "hash"


def test_load_config_creates_default_when_missing(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    ensure_index_layout(repo)

    config = load_config(repo)

    assert config.index.max_file_bytes == 500000
    assert (repo / ".context-search" / "config.toml").exists()


def test_find_repo_root_prefers_existing_index_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = tmp_path / "repo"
    child = repo / "src" / "main"
    child.mkdir(parents=True)
    ensure_index_layout(repo)
    monkeypatch.chdir(child)

    assert find_repo_root(None) == repo


def test_find_repo_root_uses_explicit_path(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    assert find_repo_root(repo) == repo
    assert index_dir_for(repo) == repo / ".context-search"


def test_find_repo_root_errors_when_cwd_has_no_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    with pytest.raises(RepositoryNotFoundError):
        find_repo_root(None)
