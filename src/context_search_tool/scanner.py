from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from pathlib import Path

import pathspec

from context_search_tool.config import ToolConfig


_LANGUAGES_BY_SUFFIX = {
    ".java": "java",
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "typescriptreact",
    ".js": "javascript",
    ".jsx": "javascriptreact",
    ".xml": "xml",
    ".yml": "yaml",
    ".yaml": "yaml",
    ".json": "json",
    ".md": "markdown",
    ".properties": "properties",
}


@dataclass(frozen=True)
class ScannedFile:
    path: Path
    absolute_path: Path
    language: str
    sha256: str
    size: int
    mtime_ns: int
    is_generated: bool = False
    is_test: bool = False
    metadata: dict[str, str] = field(default_factory=dict)


def scan_workspace(repo: Path, config: ToolConfig) -> list[ScannedFile]:
    repo = repo.resolve()
    gitignore_spec = _load_gitignore(repo)
    include_spec = pathspec.GitIgnoreSpec.from_lines(config.index.include)
    exclude_spec = pathspec.GitIgnoreSpec.from_lines(config.index.exclude)
    scanned: list[ScannedFile] = []

    for dirpath, dirnames, filenames in os.walk(repo):
        current_dir = Path(dirpath)
        dirnames[:] = sorted(
            dirname
            for dirname in dirnames
            if not _is_skipped_path(
                current_dir / dirname, repo, gitignore_spec, exclude_spec
            )
        )

        for filename in sorted(filenames):
            path = current_dir / filename
            if _is_skipped_path(path, repo, gitignore_spec, exclude_spec):
                continue
            if not _is_included_path(path, repo, include_spec, config.index.include):
                continue

            scanned_file = _scan_file(path, repo, config)
            if scanned_file is not None:
                scanned.append(scanned_file)

    return sorted(scanned, key=lambda item: item.path.as_posix())


def _load_gitignore(repo: Path) -> pathspec.PathSpec:
    gitignore = repo / ".gitignore"
    if not gitignore.exists():
        return pathspec.GitIgnoreSpec.from_lines([])
    return pathspec.GitIgnoreSpec.from_lines(
        gitignore.read_text(encoding="utf-8").splitlines()
    )


def _is_internal_path(path: Path) -> bool:
    return any(part in {".git", ".context-search"} for part in path.parts)


def _is_skipped_path(
    path: Path,
    repo: Path,
    gitignore_spec: pathspec.PathSpec,
    exclude_spec: pathspec.PathSpec,
) -> bool:
    relative_path = path.relative_to(repo)
    relative_posix = relative_path.as_posix()
    directory_posix = f"{relative_posix}/"
    return (
        _is_internal_path(relative_path)
        or gitignore_spec.match_file(relative_posix)
        or gitignore_spec.match_file(directory_posix)
        or exclude_spec.match_file(relative_posix)
        or exclude_spec.match_file(directory_posix)
    )


def _is_included_path(
    path: Path,
    repo: Path,
    include_spec: pathspec.PathSpec,
    include_patterns: list[str],
) -> bool:
    if not include_patterns:
        return True
    return include_spec.match_file(path.relative_to(repo).as_posix())


def _scan_file(path: Path, repo: Path, config: ToolConfig) -> ScannedFile | None:
    try:
        if not path.is_file():
            return None

        language = _language_for_path(path)
        if not language:
            return None

        stat = path.stat()
        if stat.st_size > config.index.max_file_bytes:
            return None
        if _looks_binary(path):
            return None

        content = path.read_bytes()
    except OSError:
        return None

    return ScannedFile(
        path=path.relative_to(repo),
        absolute_path=path,
        language=language,
        sha256=hashlib.sha256(content).hexdigest(),
        size=stat.st_size,
        mtime_ns=stat.st_mtime_ns,
    )


def _language_for_path(path: Path) -> str:
    return _LANGUAGES_BY_SUFFIX.get(path.suffix.lower(), "")


def _looks_binary(path: Path) -> bool:
    with path.open("rb") as file:
        return b"\0" in file.read(4096)
