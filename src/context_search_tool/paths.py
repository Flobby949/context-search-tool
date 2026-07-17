from __future__ import annotations

import os
from pathlib import Path
import tempfile
from typing import Callable

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


def prepare_index_directory(repo: Path) -> Path:
    resolved_repo = repo.resolve(strict=True)
    if not resolved_repo.is_dir():
        raise ValueError("repository root must be a directory")
    index_dir = resolved_repo / INDEX_DIR_NAME
    if index_dir.is_symlink():
        raise ValueError("index directory must be a regular non-symlink directory")
    index_dir.mkdir(exist_ok=True)
    if not index_dir.is_dir():
        raise ValueError("index directory must be a regular non-symlink directory")
    return index_dir


def ensure_index_gitignore_entry(repo: Path) -> None:
    resolved_repo = repo.resolve(strict=True)
    if not resolved_repo.is_dir():
        raise ValueError("repository root must be a directory")
    gitignore = resolved_repo / ".gitignore"
    if os.path.lexists(gitignore) and (
        gitignore.is_symlink() or not gitignore.is_file()
    ):
        raise ValueError("gitignore must be a regular non-symlink file")
    _ensure_index_gitignore_entry(resolved_repo)


def atomic_write_index_bytes(
    path: Path,
    payload: bytes,
    *,
    fault_prefix: str,
    fault_hook: Callable[[str], None] | None = None,
) -> None:
    if not path.name or path.parent.is_symlink() or not path.parent.is_dir():
        raise ValueError("atomic index target requires a regular parent directory")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        dir=path.parent,
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as file:
            file.write(payload)
            _fault(fault_hook, f"{fault_prefix}_temp_write")
            file.flush()
            os.fsync(file.fileno())
            _fault(fault_hook, f"{fault_prefix}_file_fsync")
        os.replace(temporary_path, path)
        _fault(fault_hook, f"{fault_prefix}_rename")
        _fsync_directory(path.parent)
        _fault(fault_hook, f"{fault_prefix}_directory_fsync")
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def _ensure_index_gitignore_entry(repo: Path) -> None:
    gitignore = repo / ".gitignore"
    content = gitignore.read_text(encoding="utf-8") if gitignore.exists() else ""
    if INDEX_GITIGNORE_ENTRY in {line.strip() for line in content.splitlines()}:
        return

    if content and not content.endswith("\n"):
        content += "\n"
    gitignore.write_text(f"{content}{INDEX_GITIGNORE_ENTRY}\n", encoding="utf-8")


def _fault(
    fault_hook: Callable[[str], None] | None,
    stage: str,
) -> None:
    if fault_hook is not None:
        fault_hook(stage)


def _fsync_directory(directory: Path) -> None:
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    descriptor = os.open(directory, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


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
