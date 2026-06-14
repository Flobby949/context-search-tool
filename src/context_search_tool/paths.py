from __future__ import annotations

from pathlib import Path

INDEX_DIR_NAME = ".context-search"
INDEX_GITIGNORE_ENTRY = f"{INDEX_DIR_NAME}/"


class RepositoryNotFoundError(RuntimeError):
    pass


def index_dir_for(repo: Path) -> Path:
    return repo.resolve() / INDEX_DIR_NAME


def ensure_index_layout(repo: Path) -> Path:
    index_dir = index_dir_for(repo)
    index_dir.mkdir(parents=True, exist_ok=True)
    _ensure_index_gitignore_entry(repo.resolve())
    return index_dir


def _ensure_index_gitignore_entry(repo: Path) -> None:
    gitignore = repo / ".gitignore"
    content = gitignore.read_text(encoding="utf-8") if gitignore.exists() else ""
    if INDEX_GITIGNORE_ENTRY in {line.strip() for line in content.splitlines()}:
        return

    if content and not content.endswith("\n"):
        content += "\n"
    gitignore.write_text(f"{content}{INDEX_GITIGNORE_ENTRY}\n", encoding="utf-8")


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
