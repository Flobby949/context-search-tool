from __future__ import annotations

import hashlib
import os
import stat
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


def scan_workspace_v5(repo: Path, config: ToolConfig) -> list[ScannedFile]:
    try:
        resolved_repo = repo.resolve(strict=True)
    except OSError as error:
        raise ValueError("repository root does not exist") from error
    if not resolved_repo.is_dir():
        raise ValueError("repository root must be a directory")

    gitignore_spec = _load_gitignore_v5(
        resolved_repo,
        config.index.max_file_bytes,
    )
    include_spec = pathspec.GitIgnoreSpec.from_lines(config.index.include)
    exclude_spec = pathspec.GitIgnoreSpec.from_lines(config.index.exclude)
    scanned: list[ScannedFile] = []
    for dirpath, dirnames, filenames in os.walk(
        resolved_repo,
        followlinks=False,
    ):
        current_dir = Path(dirpath)
        dirnames[:] = sorted(
            dirname
            for dirname in dirnames
            if not (current_dir / dirname).is_symlink()
            and not _is_skipped_path(
                current_dir / dirname,
                resolved_repo,
                gitignore_spec,
                exclude_spec,
            )
        )
        for filename in sorted(filenames):
            path = current_dir / filename
            if _is_skipped_path(
                path,
                resolved_repo,
                gitignore_spec,
                exclude_spec,
            ):
                continue
            if not _is_included_path(
                path,
                resolved_repo,
                include_spec,
                config.index.include,
            ):
                continue
            scanned_file = _scan_file_v5(path, resolved_repo, config)
            if scanned_file is not None:
                scanned.append(scanned_file)
    return sorted(scanned, key=lambda item: item.path.as_posix())


def read_scanned_file_bytes(
    repo: Path,
    scanned_file: ScannedFile,
    *,
    max_file_bytes: int,
) -> bytes:
    if max_file_bytes < 0:
        raise ValueError("max_file_bytes must be non-negative")
    try:
        resolved_repo = repo.resolve(strict=True)
    except OSError as error:
        raise ValueError("repository root does not exist") from error
    relative_path = scanned_file.path
    if (
        relative_path.is_absolute()
        or ".." in relative_path.parts
        or relative_path.as_posix() in {"", "."}
    ):
        raise ValueError("scanned path must stay inside repository")
    candidate = resolved_repo / relative_path
    content, file_stat = _read_safe_candidate(
        resolved_repo,
        candidate,
        max_file_bytes,
    )
    digest = hashlib.sha256(content).hexdigest()
    if (
        len(content) != scanned_file.size
        or file_stat.st_size != scanned_file.size
        or digest != scanned_file.sha256
    ):
        raise ValueError("file changed since scan")
    return content


def _load_gitignore(repo: Path) -> pathspec.PathSpec:
    gitignore = repo / ".gitignore"
    if not gitignore.exists():
        return pathspec.GitIgnoreSpec.from_lines([])
    return pathspec.GitIgnoreSpec.from_lines(
        gitignore.read_text(encoding="utf-8").splitlines()
    )


def _load_gitignore_v5(
    repo: Path,
    max_file_bytes: int,
) -> pathspec.PathSpec:
    gitignore = repo / ".gitignore"
    if not os.path.lexists(gitignore) or gitignore.is_symlink():
        return pathspec.GitIgnoreSpec.from_lines([])
    try:
        content, _file_stat = _read_safe_candidate(
            repo,
            gitignore,
            max_file_bytes,
        )
        lines = content.decode("utf-8").splitlines()
    except (OSError, UnicodeDecodeError, ValueError):
        return pathspec.GitIgnoreSpec.from_lines([])
    return pathspec.GitIgnoreSpec.from_lines(lines)


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


def _scan_file_v5(
    path: Path,
    repo: Path,
    config: ToolConfig,
) -> ScannedFile | None:
    try:
        language = _language_for_path(path)
        if not language:
            return None
        content, file_stat = _read_safe_candidate(
            repo,
            path,
            config.index.max_file_bytes,
        )
    except (OSError, ValueError):
        return None
    if b"\0" in content[:4096]:
        return None
    relative_path = path.relative_to(repo)
    return ScannedFile(
        path=relative_path,
        absolute_path=path,
        language=language,
        sha256=hashlib.sha256(content).hexdigest(),
        size=len(content),
        mtime_ns=file_stat.st_mtime_ns,
        is_test=_is_test_path(relative_path),
    )


def _read_safe_candidate(
    repo: Path,
    candidate: Path,
    max_file_bytes: int,
) -> tuple[bytes, os.stat_result]:
    _validate_safe_candidate(repo, candidate)
    flags = os.O_RDONLY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(candidate, flags)
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise ValueError("candidate must be a regular file")
        if before.st_size > max_file_bytes:
            raise ValueError("candidate exceeds byte limit")
        chunks: list[bytes] = []
        remaining = max_file_bytes + 1
        while remaining > 0:
            block = os.read(descriptor, min(64 * 1024, remaining))
            if not block:
                break
            chunks.append(block)
            remaining -= len(block)
        content = b"".join(chunks)
        if len(content) > max_file_bytes:
            raise ValueError("candidate exceeds byte limit")
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)

    _validate_safe_candidate(repo, candidate)
    path_stat = os.lstat(candidate)
    if (
        (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino)
        or (after.st_dev, after.st_ino) != (path_stat.st_dev, path_stat.st_ino)
        or before.st_size != after.st_size
        or len(content) != after.st_size
    ):
        raise ValueError("file changed during read")
    return content, after


def _validate_safe_candidate(repo: Path, candidate: Path) -> None:
    try:
        relative = candidate.relative_to(repo)
    except ValueError as error:
        raise ValueError("candidate must stay inside repository") from error
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("candidate must stay inside repository")

    current = repo
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError("candidate path contains a symlink")
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(repo)
    except (OSError, ValueError) as error:
        raise ValueError("candidate must resolve inside repository") from error
    candidate_stat = os.lstat(candidate)
    if not stat.S_ISREG(candidate_stat.st_mode):
        raise ValueError("candidate must be a regular file")


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
