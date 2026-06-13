from __future__ import annotations

from pathlib import Path


class RepositoryNotFoundError(RuntimeError):
    pass


def index_dir_for(repo: Path) -> Path:
    return repo.resolve() / ".context-search"


def ensure_index_layout(repo: Path) -> Path:
    index_dir = index_dir_for(repo)
    index_dir.mkdir(parents=True, exist_ok=True)
    return index_dir


def find_repo_root(explicit: Path | None) -> Path:
    if explicit is not None:
        repo = explicit.resolve()
        if not repo.is_dir():
            raise RepositoryNotFoundError(f"Repository path does not exist: {explicit}")
        return repo

    current = Path.cwd().resolve()
    for candidate in (current, *current.parents):
        if (candidate / ".context-search").is_dir() or (candidate / ".git").exists():
            return candidate

    raise RepositoryNotFoundError(f"No repository found from {current}")
