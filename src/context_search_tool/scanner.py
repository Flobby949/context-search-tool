from __future__ import annotations

import hashlib
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
    exclude_spec = pathspec.PathSpec.from_lines("gitwildmatch", config.index.exclude)
    scanned: list[ScannedFile] = []

    for path in sorted(repo.rglob("*")):
        relative_path = path.relative_to(repo)
        relative_posix = relative_path.as_posix()
        if _is_internal_path(relative_path):
            continue
        if gitignore_spec.match_file(relative_posix):
            continue
        if exclude_spec.match_file(relative_posix):
            continue
        if not path.is_file():
            continue

        language = _language_for_path(path)
        if not language:
            continue

        stat = path.stat()
        if stat.st_size > config.index.max_file_bytes:
            continue
        if _looks_binary(path):
            continue

        content = path.read_bytes()
        scanned.append(
            ScannedFile(
                path=relative_path,
                absolute_path=path,
                language=language,
                sha256=hashlib.sha256(content).hexdigest(),
                size=stat.st_size,
                mtime_ns=stat.st_mtime_ns,
            )
        )

    return scanned


def _load_gitignore(repo: Path) -> pathspec.PathSpec:
    gitignore = repo / ".gitignore"
    if not gitignore.exists():
        return pathspec.PathSpec.from_lines("gitwildmatch", [])
    return pathspec.PathSpec.from_lines(
        "gitwildmatch", gitignore.read_text(encoding="utf-8").splitlines()
    )


def _is_internal_path(path: Path) -> bool:
    return any(part in {".git", ".context-search"} for part in path.parts)


def _language_for_path(path: Path) -> str:
    return _LANGUAGES_BY_SUFFIX.get(path.suffix.lower(), "")


def _looks_binary(path: Path) -> bool:
    with path.open("rb") as file:
        return b"\0" in file.read(4096)
