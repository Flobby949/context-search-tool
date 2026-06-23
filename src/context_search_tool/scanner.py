from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from pathlib import Path

import pathspec

from context_search_tool.config import ToolConfig


_LANGUAGES_BY_SUFFIX = {
    ".java": "java",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".scala": "scala",
    ".go": "go",
    ".rs": "rust",
    ".py": "python",
    ".pyw": "python",
    ".ts": "typescript",
    ".tsx": "typescriptreact",
    ".js": "javascript",
    ".jsx": "javascriptreact",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".vue": "vue",
    ".svelte": "svelte",
    ".c": "c",
    ".h": "c",
    ".cc": "cpp",
    ".cpp": "cpp",
    ".cxx": "cpp",
    ".hpp": "cpp",
    ".hh": "cpp",
    ".hxx": "cpp",
    ".cs": "csharp",
    ".fs": "fsharp",
    ".fsx": "fsharp",
    ".swift": "swift",
    ".plist": "xml",
    ".pbxproj": "xcodeproj",
    ".xcscheme": "xml",
    ".xcworkspacedata": "xml",
    ".php": "php",
    ".rb": "ruby",
    ".rake": "ruby",
    ".lua": "lua",
    ".dart": "dart",
    ".ex": "elixir",
    ".exs": "elixir",
    ".erl": "erlang",
    ".hrl": "erlang",
    ".clj": "clojure",
    ".cljs": "clojure",
    ".r": "r",
    ".m": "objectivec",
    ".mm": "objectivecpp",
    ".sh": "shell",
    ".bash": "shell",
    ".zsh": "shell",
    ".fish": "shell",
    ".ps1": "powershell",
    ".bat": "batch",
    ".cmd": "batch",
    ".sql": "sql",
    ".graphql": "graphql",
    ".gql": "graphql",
    ".proto": "protobuf",
    ".thrift": "thrift",
    ".xml": "xml",
    ".html": "html",
    ".css": "css",
    ".scss": "scss",
    ".less": "less",
    ".yml": "yaml",
    ".yaml": "yaml",
    ".json": "json",
    ".jsonc": "json",
    ".toml": "toml",
    ".ini": "ini",
    ".cfg": "ini",
    ".conf": "config",
    ".env": "env",
    ".md": "markdown",
    ".mdx": "mdx",
    ".rst": "restructuredtext",
    ".properties": "properties",
}

_LOCKFILE_NAMES = {
    "cargo.lock",
    "go.sum",
    "package-lock.json",
    "pnpm-lock.yaml",
    "pnpm-lock.yml",
    "yarn.lock",
}


_DEFAULT_SKIPPED_DIRS = {
    "node_modules",
    "vendor",
    ".venv",
    "__pycache__",
    "dist",
    "build",
    "target",
    ".next",
    ".nuxt",
    ".turbo",
    "coverage",
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
    return any(part.startswith(".") for part in path.parts)


def _is_default_skipped_path(relative_path: Path) -> bool:
    return any(part in _DEFAULT_SKIPPED_DIRS for part in relative_path.parts)


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
        or _is_default_skipped_path(relative_path)
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

    relative_path = path.relative_to(repo)
    return ScannedFile(
        path=relative_path,
        absolute_path=path,
        language=language,
        sha256=hashlib.sha256(content).hexdigest(),
        size=stat.st_size,
        mtime_ns=stat.st_mtime_ns,
        is_test=_is_test_path(relative_path),
    )


def _language_for_path(path: Path) -> str:
    if path.name.lower() in _LOCKFILE_NAMES:
        return "lockfile"
    return _LANGUAGES_BY_SUFFIX.get(path.suffix.lower(), "")


def _is_test_path(relative_path: Path) -> bool:
    normalized = relative_path.as_posix().lower()
    parts = tuple(part.lower() for part in relative_path.parts)
    name = relative_path.name.lower()
    return (
        "test" in parts
        or "tests" in parts
        or "/src/test/" in normalized
        or name.endswith(
            (
                "_test.go",
                "_test.rs",
                "_spec.rs",
                ".test.ts",
                ".spec.ts",
                ".test.tsx",
                ".spec.tsx",
                ".test.js",
                ".spec.js",
                ".test.jsx",
                ".spec.jsx",
                "test.java",
            )
        )
    )


def _looks_binary(path: Path) -> bool:
    with path.open("rb") as file:
        return b"\0" in file.read(4096)
