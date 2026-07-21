from __future__ import annotations

import hashlib
import os
import stat
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Literal

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

_CONTROL_FILE_LIMIT = 1024 * 1024
_CONTROL_PATHS = (Path(".gitignore"), Path(".context-search/config.toml"))
_PROJECT_TOPOLOGY_MARKERS = frozenset(
    {
        "package.json",
        "go.mod",
        "pom.xml",
        "build.gradle",
        "build.gradle.kts",
        "settings.gradle",
        "settings.gradle.kts",
        "Cargo.toml",
        "pyproject.toml",
    }
)
_EXCLUSION_REASONS = (
    "ignored",
    "internal",
    "default_directory",
    "config_excluded",
    "unsupported_language",
    "pruned_directory",
)
_RETRYABLE_SKIP_REASONS = {"unreadable", "changed_during_read"}


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


@dataclass(frozen=True)
class StableFileMetadata:
    size: int
    mtime_ns: int
    change_token: int | str | None
    change_token_kind: str
    device: int
    inode: int
    mode: int


@dataclass(frozen=True)
class FileObservation:
    path: Path
    absolute_path: Path
    language: str
    metadata: StableFileMetadata
    is_test: bool = False

    @property
    def size(self) -> int:
        return self.metadata.size

    @property
    def mtime_ns(self) -> int:
        return self.metadata.mtime_ns

    @property
    def change_token(self) -> int | str | None:
        return self.metadata.change_token

    @property
    def change_token_kind(self) -> str:
        return self.metadata.change_token_kind


@dataclass(frozen=True)
class CoverageSkipObservation:
    path: Path
    language: str
    reason: str
    retryable: bool
    metadata: StableFileMetadata | None


@dataclass(frozen=True)
class InventoryDiagnostic:
    code: str
    scope: str
    path: str | None = None


@dataclass(frozen=True)
class ControlFileObservation:
    path: str
    sha256: str
    metadata: StableFileMetadata


@dataclass(frozen=True)
class WorkspaceInventory:
    eligible: tuple[FileObservation, ...]
    coverage_skips: tuple[CoverageSkipObservation, ...]
    excluded_counts: tuple[tuple[str, int], ...]
    complete: bool
    unscannable_subtrees: tuple[str, ...]
    control_file_errors: tuple[InventoryDiagnostic, ...]
    change_token_kind: str
    diagnostics: tuple[InventoryDiagnostic, ...]
    control_observations: tuple[ControlFileObservation, ...] = ()


@dataclass(frozen=True)
class ObservedFileRead:
    status: Literal["read", "skipped"]
    path: Path
    content: bytes | None
    sha256: str | None
    size: int | None
    reason: str | None
    retryable: bool
    metadata: StableFileMetadata | None


def workspace_inventory_identity(inventory: WorkspaceInventory) -> tuple[Any, ...]:
    """Return the complete freshness-affecting identity for one inventory fence."""
    return (
        inventory.complete,
        tuple(
            (
                item.path.as_posix(),
                item.language,
                item.metadata,
                item.is_test,
            )
            for item in inventory.eligible
        ),
        tuple(
            (
                item.path.as_posix(),
                item.language,
                item.reason,
                item.retryable,
                item.metadata,
            )
            for item in inventory.coverage_skips
        ),
        inventory.unscannable_subtrees,
        inventory.control_file_errors,
        inventory.control_observations,
    )


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


def observe_workspace(
    repo: Path,
    config: ToolConfig,
    *,
    walk: Callable[..., Any] | None = None,
) -> WorkspaceInventory:
    try:
        resolved_repo = repo.resolve(strict=True)
    except OSError as error:
        raise ValueError("repository root does not exist") from error
    if not resolved_repo.is_dir():
        raise ValueError("repository root must be a directory")

    control_observations: list[ControlFileObservation] = []
    control_errors: list[InventoryDiagnostic] = []
    observed_control_paths: set[Path] = set()
    gitignore_lines: list[str] = []

    def observe_control(relative: Path) -> bytes | None:
        if relative in observed_control_paths:
            return None
        observed_control_paths.add(relative)
        candidate = resolved_repo / relative
        if not os.path.lexists(candidate):
            return None
        try:
            content, metadata = _read_control_file(resolved_repo, candidate)
            content.decode("utf-8")
            control_observations.append(
                ControlFileObservation(
                    path=relative.as_posix(),
                    sha256=hashlib.sha256(content).hexdigest(),
                    metadata=metadata,
                )
            )
            return content
        except (OSError, UnicodeDecodeError, ValueError):
            control_errors.append(
                InventoryDiagnostic(
                    code="control_file_error",
                    scope="control",
                    path=relative.as_posix(),
                )
            )
            return None

    for relative in _CONTROL_PATHS:
        content = observe_control(relative)
        if relative == Path(".gitignore") and content is not None:
            gitignore_lines = content.decode("utf-8").splitlines()

    gitignore_spec = pathspec.GitIgnoreSpec.from_lines(gitignore_lines)
    include_spec = pathspec.GitIgnoreSpec.from_lines(config.index.include)
    exclude_spec = pathspec.GitIgnoreSpec.from_lines(config.index.exclude)
    eligible: list[FileObservation] = []
    coverage_skips: list[CoverageSkipObservation] = []
    excluded_counts = {reason: 0 for reason in _EXCLUSION_REASONS}
    unscannable: set[str] = set()

    def record_walk_error(error: OSError) -> None:
        raw_path = getattr(error, "filename", None)
        relative = _sanitized_relative_path(resolved_repo, raw_path)
        unscannable.add(relative or ".")

    walker = walk or os.walk
    for dirpath, dirnames, filenames in walker(
        resolved_repo,
        followlinks=False,
        onerror=record_walk_error,
    ):
        current_dir = Path(dirpath)
        retained_dirs: list[str] = []
        for dirname in sorted(dirnames):
            path = current_dir / dirname
            relative = _relative_path_or_none(path, resolved_repo)
            if relative is None:
                unscannable.add(".")
                continue
            if path.is_symlink():
                excluded_counts["pruned_directory"] += 1
                continue
            reason = _excluded_reason(
                relative,
                gitignore_spec=gitignore_spec,
                exclude_spec=exclude_spec,
            )
            if reason is not None:
                excluded_counts[reason] += 1
                excluded_counts["pruned_directory"] += 1
                continue
            retained_dirs.append(dirname)
        dirnames[:] = retained_dirs

        for filename in sorted(filenames):
            path = current_dir / filename
            relative = _relative_path_or_none(path, resolved_repo)
            if relative is None:
                unscannable.add(".")
                continue
            if filename in _PROJECT_TOPOLOGY_MARKERS:
                observe_control(relative)
            if relative in _CONTROL_PATHS:
                continue
            reason = _excluded_reason(
                relative,
                gitignore_spec=gitignore_spec,
                exclude_spec=exclude_spec,
            )
            if reason is not None:
                excluded_counts[reason] += 1
                continue
            if not _is_included_relative(
                relative,
                include_spec,
                config.index.include,
            ):
                excluded_counts["config_excluded"] += 1
                continue
            language = _language_for_path(path)
            if not language:
                excluded_counts["unsupported_language"] += 1
                continue
            try:
                path_stat = os.lstat(path)
                metadata = _metadata_from_stat(path_stat)
            except OSError:
                coverage_skips.append(
                    CoverageSkipObservation(
                        path=relative,
                        language=language,
                        reason="unreadable",
                        retryable=True,
                        metadata=None,
                    )
                )
                unscannable.add(relative.as_posix())
                continue
            if not stat.S_ISREG(path_stat.st_mode) or path.is_symlink():
                coverage_skips.append(
                    CoverageSkipObservation(
                        path=relative,
                        language=language,
                        reason="unsafe_path",
                        retryable=False,
                        metadata=metadata,
                    )
                )
                continue
            if metadata.size > config.index.max_file_bytes:
                coverage_skips.append(
                    CoverageSkipObservation(
                        path=relative,
                        language=language,
                        reason="too_large",
                        retryable=False,
                        metadata=metadata,
                    )
                )
                continue
            eligible.append(
                FileObservation(
                    path=relative,
                    absolute_path=path,
                    language=language,
                    metadata=metadata,
                    is_test=_is_test_path(relative),
                )
            )

    diagnostics = [
        InventoryDiagnostic(
            code="unscannable_subtree",
            scope="inventory",
            path=path,
        )
        for path in sorted(unscannable)
    ]
    diagnostics.extend(control_errors)
    all_metadata = [
        item.metadata
        for item in eligible
        if item.metadata is not None
    ] + [
        item.metadata
        for item in coverage_skips
        if item.metadata is not None
    ] + [item.metadata for item in control_observations]
    change_token_kind = _combined_change_token_kind(all_metadata)
    return WorkspaceInventory(
        eligible=tuple(sorted(eligible, key=lambda item: item.path.as_posix())),
        coverage_skips=tuple(
            sorted(coverage_skips, key=lambda item: item.path.as_posix())
        ),
        excluded_counts=tuple(
            (reason, excluded_counts[reason]) for reason in _EXCLUSION_REASONS
        ),
        complete=not unscannable and not control_errors,
        unscannable_subtrees=tuple(sorted(unscannable)),
        control_file_errors=tuple(control_errors),
        change_token_kind=change_token_kind,
        diagnostics=tuple(
            sorted(
                diagnostics,
                key=lambda item: (
                    0 if item.code == "unscannable_subtree" else 1,
                    item.path or "",
                ),
            )
        ),
        control_observations=tuple(
            sorted(control_observations, key=lambda item: item.path)
        ),
    )


def read_observed_file(
    repo: Path,
    observation: FileObservation,
    *,
    max_file_bytes: int,
    chunk_size: int = 64 * 1024,
    require_utf8: bool = True,
    metadata_observer: Callable[[int], StableFileMetadata] | None = None,
) -> ObservedFileRead:
    if max_file_bytes < 0:
        raise ValueError("max_file_bytes must be non-negative")
    if chunk_size < 1:
        raise ValueError("chunk_size must be positive")
    try:
        resolved_repo = repo.resolve(strict=True)
    except OSError as error:
        raise ValueError("repository root does not exist") from error
    relative = observation.path
    if (
        relative.is_absolute()
        or relative.as_posix() in {"", "."}
        or ".." in relative.parts
        or "\\" in relative.as_posix()
    ):
        return _skipped_read(observation, "unsafe_path")
    candidate = resolved_repo / relative
    descriptor: int | None = None
    try:
        _validate_safe_candidate(resolved_repo, candidate)
        flags = os.O_RDONLY
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(candidate, flags)
        observe_metadata = metadata_observer or (
            lambda value: _metadata_from_stat(os.fstat(value))
        )
        before = observe_metadata(descriptor)
        if not _metadata_matches_observation(before, observation.metadata):
            return _skipped_read(
                observation,
                "changed_during_read",
                metadata=before,
            )
        if before.size > max_file_bytes:
            return _skipped_read(observation, "too_large", metadata=before)

        digest = hashlib.sha256()
        body = bytearray()
        while len(body) <= max_file_bytes:
            block = os.read(
                descriptor,
                min(chunk_size, max_file_bytes + 1 - len(body)),
            )
            if not block:
                break
            body.extend(block)
            digest.update(block)
        if len(body) > max_file_bytes:
            return _skipped_read(observation, "too_large", metadata=before)
        after = observe_metadata(descriptor)
    except OSError:
        return _skipped_read(observation, "unreadable")
    except ValueError:
        return _skipped_read(observation, "unsafe_path")
    finally:
        if descriptor is not None:
            os.close(descriptor)

    try:
        _validate_safe_candidate(resolved_repo, candidate)
        path_metadata = _metadata_from_stat(os.lstat(candidate))
    except (OSError, ValueError):
        return _skipped_read(observation, "unsafe_path")
    if (
        before != after
        or after != path_metadata
        or not _metadata_matches_observation(after, observation.metadata)
        or len(body) != after.size
    ):
        return _skipped_read(
            observation,
            "changed_during_read",
            metadata=after,
        )
    content = bytes(body)
    if b"\0" in content[:4096]:
        return _skipped_read(observation, "binary", metadata=after)
    if require_utf8:
        try:
            content.decode("utf-8")
        except UnicodeDecodeError:
            return _skipped_read(
                observation,
                "unsupported_encoding",
                metadata=after,
            )
    return ObservedFileRead(
        status="read",
        path=relative,
        content=content,
        sha256=digest.hexdigest(),
        size=len(content),
        reason=None,
        retryable=False,
        metadata=after,
    )


def scan_workspace_v5(repo: Path, config: ToolConfig) -> list[ScannedFile]:
    inventory = observe_workspace(repo, config)
    resolved_repo = repo.resolve()
    scanned: list[ScannedFile] = []
    for observation in inventory.eligible:
        result = read_observed_file(
            resolved_repo,
            observation,
            max_file_bytes=config.index.max_file_bytes,
            require_utf8=False,
        )
        if result.status != "read" or result.sha256 is None or result.size is None:
            continue
        scanned.append(
            ScannedFile(
                path=observation.path,
                absolute_path=observation.absolute_path,
                language=observation.language,
                sha256=result.sha256,
                size=result.size,
                mtime_ns=observation.mtime_ns,
                is_test=observation.is_test,
            )
        )
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


def _read_control_file(
    repo: Path,
    candidate: Path,
) -> tuple[bytes, StableFileMetadata]:
    content, file_stat = _read_safe_candidate(
        repo,
        candidate,
        _CONTROL_FILE_LIMIT,
    )
    return content, _metadata_from_stat(file_stat)


def _metadata_from_stat(value: os.stat_result) -> StableFileMetadata:
    change_token = getattr(value, "st_ctime_ns", None)
    if change_token is not None:
        token_kind = "mtime_ns+ctime_ns"
    else:
        change_token = None
        token_kind = "mtime_ns"
    return StableFileMetadata(
        size=int(value.st_size),
        mtime_ns=int(value.st_mtime_ns),
        change_token=change_token,
        change_token_kind=token_kind,
        device=int(value.st_dev),
        inode=int(value.st_ino),
        mode=int(value.st_mode),
    )


def _metadata_matches_observation(
    actual: StableFileMetadata,
    expected: StableFileMetadata,
) -> bool:
    return (
        actual.size == expected.size
        and actual.mtime_ns == expected.mtime_ns
        and actual.change_token == expected.change_token
        and actual.change_token_kind == expected.change_token_kind
        and actual.device == expected.device
        and actual.inode == expected.inode
        and stat.S_IFMT(actual.mode) == stat.S_IFMT(expected.mode)
    )


def _combined_change_token_kind(
    values: list[StableFileMetadata],
) -> str:
    kinds = {value.change_token_kind for value in values}
    if "platform_specific" in kinds:
        return "platform_specific"
    if "mtime_ns" in kinds:
        return "mtime_ns"
    return "mtime_ns+ctime_ns"


def _relative_path_or_none(path: Path, repo: Path) -> Path | None:
    try:
        relative = path.relative_to(repo)
    except ValueError:
        return None
    if relative.is_absolute() or ".." in relative.parts:
        return None
    return relative


def _sanitized_relative_path(repo: Path, raw_path: object) -> str | None:
    if not isinstance(raw_path, (str, os.PathLike)):
        return None
    path = Path(raw_path)
    if not path.is_absolute():
        path = repo / path
    relative = _relative_path_or_none(path, repo)
    return relative.as_posix() if relative is not None else None


def _excluded_reason(
    relative_path: Path,
    *,
    gitignore_spec: pathspec.PathSpec,
    exclude_spec: pathspec.PathSpec,
) -> str | None:
    relative_posix = relative_path.as_posix()
    directory_posix = f"{relative_posix}/"
    if _is_internal_path(relative_path):
        return "internal"
    if _is_default_skipped_path(relative_path):
        return "default_directory"
    if gitignore_spec.match_file(relative_posix) or gitignore_spec.match_file(
        directory_posix
    ):
        return "ignored"
    if exclude_spec.match_file(relative_posix) or exclude_spec.match_file(
        directory_posix
    ):
        return "config_excluded"
    return None


def _is_included_relative(
    relative_path: Path,
    include_spec: pathspec.PathSpec,
    include_patterns: list[str],
) -> bool:
    if not include_patterns:
        return True
    return include_spec.match_file(relative_path.as_posix())


def _skipped_read(
    observation: FileObservation,
    reason: str,
    *,
    metadata: StableFileMetadata | None = None,
) -> ObservedFileRead:
    return ObservedFileRead(
        status="skipped",
        path=observation.path,
        content=None,
        sha256=None,
        size=metadata.size if metadata is not None else None,
        reason=reason,
        retryable=reason in _RETRYABLE_SKIP_REASONS,
        metadata=metadata,
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
