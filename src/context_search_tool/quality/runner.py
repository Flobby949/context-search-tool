from __future__ import annotations

import hashlib
import json
import ntpath
import os
import re
import shutil
import stat
import tempfile
import time
import unicodedata
from copy import deepcopy
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any
from urllib.parse import quote

from context_search_tool.config import DEFAULT_CONFIG, ToolConfig
from context_search_tool.indexer import index_repository
from context_search_tool.manifest import load_manifest
from context_search_tool.models import QueryPlan
from context_search_tool.quality.aggregate import aggregate_cases
from context_search_tool.quality.cases import (
    QualityCase,
    QualityFixture,
    QualityRepo,
    load_quality_fixture,
    validate_profile_compatible,
)
from context_search_tool.quality.metrics import CaseEvaluation, evaluate_case
from context_search_tool.retrieval import QueryBundle, query_repository


_COPY_EXCLUDES = {
    ".git",
    ".context-search",
    ".venv",
    "node_modules",
    "dist",
    "build",
    "target",
    "__pycache__",
}

_WINDOWS_RESERVED_NAMES = {
    "con",
    "prn",
    "aux",
    "nul",
    "conin$",
    "conout$",
    *(f"com{suffix}" for suffix in "123456789¹²³"),
    *(f"lpt{suffix}" for suffix in "123456789¹²³"),
}

_WINDOWS_INVALID_COMPONENT_CHARS = frozenset('<>:"/\\|?*')

_DESCRIPTOR_COPY_SUPPORTED = (
    os.name == "posix"
    and hasattr(os, "O_DIRECTORY")
    and hasattr(os, "O_NOFOLLOW")
    and os.open in os.supports_dir_fd
    and os.scandir in os.supports_fd
)


@dataclass(frozen=True)
class ResolvedSource:
    path: Path
    source_type: str
    locator: str


def run_quality_fixture(
    fixture_path: Path,
    profile: str,
    output_path: Path | None,
    markdown_path: Path | None,
    keep_workspace: bool = False,
    config: ToolConfig = DEFAULT_CONFIG,
    allow_empty: bool = False,
) -> dict[str, Any]:
    fixture = load_quality_fixture(fixture_path)
    if profile not in fixture.profile_configs:
        raise ValueError(f"unknown quality profile: {profile}")

    selected_base = DEFAULT_CONFIG if fixture.canonical else config
    selected_config = _effective_config(
        selected_base,
        {},
        fixture.profile_configs[profile],
    )

    temp_root = Path(tempfile.mkdtemp(prefix="cst-quality-")).resolve()
    repos: list[dict[str, Any]] = []
    cases: list[dict[str, Any]] = []
    workspace_identities: set[str] = set()
    temp_root_removed = False
    primary_error: BaseException | None = None

    try:
        for repo in fixture.repos:
            selected_cases = tuple(
                case
                for case in repo.queries
                if not case.profiles or profile in case.profiles
            )
            if profile not in repo.profiles or not selected_cases:
                continue

            workspace_component = _safe_path_component(repo.repo_key, "repo_key")
            workspace_identity = unicodedata.normalize(
                "NFC",
                workspace_component,
            ).casefold()
            if workspace_identity in workspace_identities:
                raise ValueError(f"duplicate workspace repo_key: {repo.repo_key}")
            workspace_identities.add(workspace_identity)
            profile_overrides = fixture.profile_configs[profile]
            repo_config = _effective_config(
                selected_base,
                repo.default_config,
                profile_overrides,
            )
            validate_profile_compatible(
                profile,
                repo_config,
                canonical=fixture.canonical,
            )
            source = _resolve_repo_source(repo, fixture.path, profile)
            if source is None:
                cases.extend(
                    _case_records_for_cases(
                        repo.repo_key,
                        selected_cases,
                        "skipped",
                        "repo not found",
                    )
                )
                continue

            workspace = (temp_root / workspace_component).resolve()
            if workspace.parent != temp_root:
                raise ValueError("repo_key must be a safe path component")

            repo_record = {
                "repo_key": repo.repo_key,
                "source": {
                    "type": source.source_type,
                    "locator": source.locator,
                    "git_commit": None,
                    "content_hash": None,
                },
                "workspace": {
                    "copied": False,
                    "preserved": keep_workspace,
                    **({"path": str(workspace)} if keep_workspace else {}),
                },
                "config": {
                    "config_hash": _config_hash(repo_config),
                    "index": asdict(repo_config.index),
                    "retrieval": asdict(repo_config.retrieval),
                    "embedding": asdict(repo_config.embedding),
                    "query_planner": asdict(repo_config.query_planner),
                },
                "index": {"status": "pending"},
            }
            repos.append(repo_record)

            try:
                _copy_source_repo(source.path, workspace)
                repo_record["workspace"]["copied"] = True
                repo_record["source"]["git_commit"] = _git_commit(source.path)
                repo_record["source"]["content_hash"] = _content_identity(workspace)
                summary = index_repository(workspace, repo_config)
                manifest = load_manifest(workspace)
            except Exception as exc:
                _remove_tree(workspace, "repository workspace")
                repo_record["workspace"]["preserved"] = False
                repo_record["workspace"].pop("path", None)
                repo_record["index"] = {"status": "error"}
                cases.extend(
                    _case_records_for_cases(
                        repo.repo_key,
                        selected_cases,
                        "error",
                        _safe_error(exc, source.path, workspace),
                    )
                )
                continue

            repo_record["index"] = {
                "status": "ok",
                "manifest_schema_version": manifest.schema_version,
                "embedding_config_hash": manifest.embedding_config_hash,
                "config_hash": _config_hash(repo_config),
                "files_indexed": summary.files_indexed,
                "chunks_indexed": summary.chunks_indexed,
            }

            for case in selected_cases:
                started = time.perf_counter()
                try:
                    bundle = query_repository(workspace, case.query, repo_config)
                    latency_ms = int((time.perf_counter() - started) * 1000)
                    evaluation = evaluate_case(
                        case,
                        bundle.results,
                        latency_ms=latency_ms,
                        anchor_paths=[
                            anchor.file_path.as_posix()
                            for anchor in bundle.evidence_anchors
                        ],
                    )
                    cases.append(
                        _case_record(repo.repo_key, case, evaluation, bundle)
                    )
                except Exception as exc:
                    cases.append(
                        _error_case_record(
                            repo.repo_key,
                            case,
                            _safe_error(exc, source.path, workspace),
                        )
                    )

        report = _report(fixture, profile, selected_config, repos, cases)
        artifacts = _render_artifacts(report, output_path, markdown_path)
        if not keep_workspace:
            _remove_tree(temp_root, "temporary workspace")
            temp_root_removed = True
        _publish_artifacts(artifacts)

        aggregate = report["aggregate"]
        if aggregate["selected"] == 0:
            raise ValueError("no cases selected for quality profile")
        if aggregate["executed"] == 0 and not allow_empty:
            raise ValueError("no cases executed for quality profile")
        return report
    except BaseException as exc:
        primary_error = exc
        raise
    finally:
        if not keep_workspace and not temp_root_removed:
            try:
                _remove_tree(temp_root, "temporary workspace")
            except Exception as cleanup_error:
                if primary_error is None:
                    raise
                primary_error.add_note(
                    "Additional temporary workspace cleanup failure: "
                    f"{cleanup_error}"
                )


def _apply_config_sections(
    config: ToolConfig,
    overrides: dict[str, Any],
) -> ToolConfig:
    result = config
    for section_name in ("index", "retrieval", "embedding", "query_planner"):
        if section_name in overrides:
            current = getattr(result, section_name)
            result = replace(
                result,
                **{section_name: replace(current, **overrides[section_name])},
            )
    return result


def _effective_config(
    base: ToolConfig,
    repo_overrides: dict[str, Any],
    profile_overrides: dict[str, Any],
) -> ToolConfig:
    result = _apply_config_sections(deepcopy(base), deepcopy(repo_overrides))
    profile_overrides = deepcopy(profile_overrides)
    if "index" in profile_overrides:
        result = replace(
            result,
            index=replace(result.index, **profile_overrides["index"]),
        )
    if "retrieval" in profile_overrides:
        result = replace(
            result,
            retrieval=replace(result.retrieval, **profile_overrides["retrieval"]),
        )
    if "embedding" in profile_overrides:
        result = replace(
            result,
            embedding=replace(
                DEFAULT_CONFIG.embedding,
                **profile_overrides["embedding"],
            ),
        )
    if "query_planner" in profile_overrides:
        result = replace(
            result,
            query_planner=replace(
                DEFAULT_CONFIG.query_planner,
                **profile_overrides["query_planner"],
            ),
        )
    return result


def _resolve_repo_source(
    repo: QualityRepo,
    fixture_path: Path,
    profile: str,
) -> ResolvedSource | None:
    if profile == "ci":
        if not repo.snapshot_path:
            raise ValueError(
                f"ci profile requires snapshot_path for repo {repo.repo_key}"
            )
        snapshot = _existing_resolved_directory(
            _resolve_snapshot_path(fixture_path, repo.snapshot_path)
        )
        if snapshot is None:
            raise ValueError(f"ci snapshot not found for repo {repo.repo_key}")
        return ResolvedSource(
            path=snapshot,
            source_type="snapshot_path",
            locator=_safe_snapshot_locator(repo.snapshot_path),
        )

    if repo.path_env:
        env_path = os.environ.get(repo.path_env)
        if env_path:
            source = _existing_directory(env_path)
            if source is not None:
                return ResolvedSource(source, "path_env", repo.path_env)
    if repo.repo_dir_name:
        repo_dir_name = _safe_path_component(repo.repo_dir_name, "repo_dir_name")
        smoke_root = os.environ.get("CST_SMOKE_REPOS_DIR")
        if smoke_root:
            resolved_root = _existing_directory(smoke_root)
            if resolved_root is not None:
                source = (resolved_root / repo_dir_name).resolve()
                if source == resolved_root or not source.is_relative_to(resolved_root):
                    raise ValueError(
                        "repo_dir_name escapes CST_SMOKE_REPOS_DIR: "
                        f"{repo_dir_name}"
                    )
                if source.is_dir():
                    return ResolvedSource(source, "smoke_root", repo_dir_name)
    if repo.snapshot_path:
        source = _existing_resolved_directory(
            _resolve_snapshot_path(fixture_path, repo.snapshot_path)
        )
        if source is not None:
            return ResolvedSource(
                source,
                "snapshot_path",
                _safe_snapshot_locator(repo.snapshot_path),
            )
    return None


def _existing_directory(raw_path: str | Path) -> Path | None:
    path = Path(raw_path).expanduser().resolve()
    return path if path.is_dir() else None


def _existing_resolved_directory(path: Path) -> Path | None:
    try:
        mode = path.lstat().st_mode
    except OSError:
        return None
    return path if stat.S_ISDIR(mode) else None


def _safe_path_component(value: str, field_name: str) -> str:
    windows_path = PureWindowsPath(value)
    has_invalid_character = any(
        character in _WINDOWS_INVALID_COMPONENT_CHARS or ord(character) < 32
        for character in value
    )
    if (
        not value
        or value in {".", ".."}
        or Path(value).is_absolute()
        or bool(windows_path.drive)
        or has_invalid_character
        or value.endswith((".", " "))
        or _is_windows_reserved_component(value)
    ):
        raise ValueError(f"{field_name} must be a safe path component")
    return value


def _is_windows_reserved_component(value: str) -> bool:
    is_reserved = getattr(ntpath, "isreserved", None)
    if is_reserved is not None:
        return is_reserved(value)
    basename = value.split(".", 1)[0].rstrip(" ").casefold()
    return basename in _WINDOWS_RESERVED_NAMES


def _safe_snapshot_locator(raw_path: str) -> str:
    path = Path(raw_path).expanduser()
    if path.is_absolute():
        locator = path.resolve().name
        if not locator:
            raise ValueError("absolute snapshot_path must resolve to a named directory")
        return locator
    return _safe_relative_snapshot_path(raw_path).as_posix()


def _resolve_snapshot_path(fixture_path: Path, raw_path: str) -> Path:
    path = Path(raw_path).expanduser()
    if path.is_absolute():
        if path.is_symlink():
            raise ValueError("snapshot_path must not be a top-level symlink")
        return path.resolve()

    relative = _safe_relative_snapshot_path(raw_path)
    fixture_root = fixture_path.parent.resolve()
    fixture_candidate = fixture_root / relative
    if fixture_candidate.exists() or fixture_candidate.is_symlink():
        return _contained_snapshot_path(fixture_root, fixture_candidate)

    cwd_root = Path.cwd().resolve()
    return _contained_snapshot_path(cwd_root, cwd_root / relative)


def _safe_relative_snapshot_path(raw_path: str) -> Path:
    normalized = raw_path.replace("\\", "/")
    windows_path = PureWindowsPath(raw_path)
    if normalized.startswith("/") or windows_path.drive:
        raise ValueError("snapshot_path must be a safe relative path")

    relative = PurePosixPath(normalized)
    if ".." in relative.parts:
        raise ValueError("snapshot_path must be a safe relative path")
    return Path(*relative.parts)


def _contained_snapshot_path(root: Path, candidate: Path) -> Path:
    resolved = candidate.resolve()
    if not resolved.is_relative_to(root):
        raise ValueError("snapshot_path escapes its relative base")
    return resolved


def _copy_source_repo(source: Path, workspace: Path) -> None:
    """Copy regular files/directories while omitting all link-like entries."""
    if not _descriptor_copy_supported():
        raise RuntimeError("secure repository copy is not supported on this platform")
    try:
        workspace.lstat()
    except FileNotFoundError:
        workspace_existed = False
    else:
        workspace_existed = True

    try:
        _copy_source_repo_with_descriptors(source, workspace)
    except Exception:
        if not workspace_existed:
            _remove_tree(workspace, "repository workspace")
        raise


def _descriptor_copy_supported() -> bool:
    return _DESCRIPTOR_COPY_SUPPORTED


def _copy_source_repo_with_descriptors(source: Path, workspace: Path) -> None:
    directory_flags = (
        os.O_RDONLY
        | os.O_DIRECTORY
        | os.O_NOFOLLOW
        | getattr(os, "O_CLOEXEC", 0)
    )
    source_fd = _open_directory_no_follow(source, directory_flags)
    try:
        workspace.mkdir()
        _copy_directory_fd(source_fd, source, workspace, directory_flags)
    finally:
        os.close(source_fd)


def _open_directory_no_follow(path: Path, flags: int) -> int:
    if path.is_absolute():
        current_fd = os.open(path.anchor, flags)
        parts = path.parts[1:]
    else:
        current_fd = os.open(".", flags)
        parts = path.parts

    try:
        for part in parts:
            child_fd = os.open(part, flags, dir_fd=current_fd)
            os.close(current_fd)
            current_fd = child_fd
    except Exception:
        os.close(current_fd)
        raise
    return current_fd


def _copy_directory_fd(
    source_fd: int,
    source: Path,
    destination: Path,
    directory_flags: int,
) -> None:
    with os.scandir(source_fd) as iterator:
        entries = sorted(iterator, key=lambda entry: entry.name)

    file_flags = (
        os.O_RDONLY
        | os.O_NOFOLLOW
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )
    for entry in entries:
        if entry.name in _COPY_EXCLUDES:
            continue

        source_child = source / entry.name
        if entry.is_symlink() or _is_junction_or_reparse(source_child):
            continue

        destination_child = destination / entry.name
        if entry.is_dir(follow_symlinks=False):
            child_fd = os.open(entry.name, directory_flags, dir_fd=source_fd)
            try:
                destination_child.mkdir()
                _copy_directory_fd(
                    child_fd,
                    source_child,
                    destination_child,
                    directory_flags,
                )
            finally:
                os.close(child_fd)
            continue

        if not entry.is_file(follow_symlinks=False):
            continue

        file_fd = os.open(entry.name, file_flags, dir_fd=source_fd)
        try:
            file_status = os.fstat(file_fd)
            if not stat.S_ISREG(file_status.st_mode):
                continue
            source_file = os.fdopen(file_fd, "rb")
            file_fd = -1
            with source_file:
                with destination_child.open("xb") as destination_file:
                    shutil.copyfileobj(source_file, destination_file)
        finally:
            if file_fd >= 0:
                os.close(file_fd)


def _is_junction_or_reparse(path: Path) -> bool:
    is_junction = getattr(path, "is_junction", None)
    if is_junction is not None and is_junction():
        return True
    try:
        file_attributes = getattr(path.lstat(), "st_file_attributes", 0)
    except OSError:
        return False
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return bool(reparse_flag and file_attributes & reparse_flag)


def _report(
    fixture: QualityFixture,
    profile: str,
    config: ToolConfig,
    repos: list[dict[str, Any]],
    cases: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "schema_version": 2,
        "generated_at": datetime.now(UTC).isoformat(),
        "command_args": {
            "fixture_path": str(fixture.path),
            "profile": profile,
        },
        "tool": {
            "name": "context-search-tool",
            "git_commit": _git_commit(Path.cwd()),
        },
        "fixture": {
            "path": str(fixture.path),
            "sha256": _file_sha256(fixture.path),
            "schema_version": fixture.schema_version,
            "fixture_case_count": sum(len(repo.queries) for repo in fixture.repos),
            "run_case_count": len(cases),
        },
        "profile": profile,
        "config": {
            "config_hash": _config_hash(config),
            "embedding": asdict(config.embedding),
        },
        "planner": asdict(config.query_planner),
        "aggregate": aggregate_cases(cases, repos, profile),
        "repos": repos,
        "cases": cases,
    }


def _case_record(
    repo_key: str,
    case: QualityCase,
    evaluation: CaseEvaluation,
    bundle: QueryBundle,
) -> dict[str, Any]:
    return {
        "repo_key": repo_key,
        "case_id": case.case_id,
        "query": case.query,
        "tags": list(case.tags),
        "gate": case.gate.value,
        "attempted": True,
        "known_gap_reason": case.known_gap_reason,
        "expanded_tokens": list(bundle.expanded_tokens),
        "planner": _planner_payload(bundle.planner),
        **(
            {
                "legacy": {
                    "fixture": case.legacy.fixture,
                    "key": case.legacy.key,
                }
            }
            if case.legacy is not None
            else {}
        ),
        "status": evaluation.status,
        "metrics": evaluation.metrics,
        "top_results": evaluation.top_results,
        "failures": evaluation.failures,
    }


def _case_records_for_cases(
    repo_key: str,
    selected_cases: tuple[QualityCase, ...],
    status: str,
    reason: str,
) -> list[dict[str, Any]]:
    return [
        _empty_case_record(repo_key, case, status, reason)
        for case in selected_cases
    ]


def _error_case_record(
    repo_key: str,
    case: QualityCase,
    reason: str,
) -> dict[str, Any]:
    return _empty_case_record(repo_key, case, "error", reason, attempted=True)


def _empty_case_record(
    repo_key: str,
    case: QualityCase,
    status: str,
    reason: str,
    attempted: bool = False,
) -> dict[str, Any]:
    return {
        "repo_key": repo_key,
        "case_id": case.case_id,
        "query": case.query,
        "tags": list(case.tags),
        "gate": case.gate.value,
        "attempted": attempted,
        "known_gap_reason": case.known_gap_reason,
        "expanded_tokens": [],
        **(
            {
                "legacy": {
                    "fixture": case.legacy.fixture,
                    "key": case.legacy.key,
                }
            }
            if case.legacy is not None
            else {}
        ),
        "status": status,
        "metrics": {},
        "top_results": [],
        "failures": [reason],
    }


def _planner_payload(plan: QueryPlan) -> dict[str, Any]:
    return {
        "status": plan.status,
        "rewritten_queries": list(plan.rewritten_queries),
        "grep_keywords": list(plan.grep_keywords),
        "symbol_hints": list(plan.symbol_hints),
        "discarded_hints": list(plan.discarded_hints),
        "provider": plan.provider,
        "model": plan.model,
        "prompt_version": plan.prompt_version,
        "prompt_hash": plan.prompt_hash,
        "latency_ms": plan.latency_ms,
        "repo_profile_hash": plan.repo_profile_hash,
        "repo_profile_truncated": plan.repo_profile_truncated,
    }


def _safe_error(exc: Exception, source: Path, workspace: Path) -> str:
    message = str(exc)
    replacements = [
        (variant, replacement)
        for path, replacement in (
            (workspace, "<workspace>"),
            (source, "<source>"),
        )
        for variant in _path_redaction_variants(path)
    ]
    for variant, replacement in sorted(
        replacements,
        key=lambda item: len(item[0]),
        reverse=True,
    ):
        message = re.sub(
            re.escape(variant),
            replacement,
            message,
            flags=re.IGNORECASE,
        )
    return message


def _path_redaction_variants(path: Path) -> set[str]:
    candidates = {path}
    try:
        candidates.add(path.resolve())
    except (OSError, RuntimeError):
        pass

    path_spellings: set[str] = set()
    variants: set[str] = set()
    for candidate in candidates:
        path_spellings.add(str(candidate))
        path_spellings.add(candidate.as_posix())

    path_spellings = {
        unicodedata.normalize(form, spelling)
        for spelling in path_spellings
        for form in ("NFC", "NFD")
    }

    variants.update(path_spellings)
    for spelling in path_spellings:
        try:
            variants.add(Path(spelling).as_uri())
        except ValueError:
            pass
        variants.add(quote(spelling, safe="/"))
        variants.add(quote(spelling, safe=""))
    return {variant for variant in variants if variant}


def _render_artifacts(
    report: dict[str, Any],
    output_path: Path | None,
    markdown_path: Path | None,
) -> list[tuple[Path, str]]:
    artifacts: list[tuple[Path, str]] = []
    if output_path is not None:
        artifacts.append(
            (
                output_path,
                json.dumps(report, indent=2, ensure_ascii=False) + "\n",
            )
        )
    if markdown_path is not None:
        from context_search_tool.quality.reports import render_markdown_report

        artifacts.append((markdown_path, render_markdown_report(report)))
    return artifacts


def _publish_artifacts(artifacts: list[tuple[Path, str]]) -> None:
    staged: list[tuple[Path, Path]] = []
    backups: dict[Path, Path] = {}
    replaced: list[Path] = []
    publication_error: BaseException | None = None

    try:
        for destination, _content in artifacts:
            _ensure_parent(destination)
        for destination, content in artifacts:
            staged.append(
                (
                    destination,
                    _stage_sibling_file(destination, content, "stage"),
                )
            )
        for destination, _content in artifacts:
            if destination.exists():
                backups[destination] = _stage_sibling_file(
                    destination,
                    destination.read_bytes(),
                    "backup",
                )

        try:
            for destination, stage in staged:
                os.replace(stage, destination)
                replaced.append(destination)
        except Exception as exc:
            for destination in reversed(replaced):
                try:
                    backup = backups.pop(destination, None)
                    if backup is None:
                        destination.unlink(missing_ok=True)
                    else:
                        os.replace(backup, destination)
                except Exception as rollback_error:
                    exc.add_note(
                        f"Artifact rollback failed for {destination.name}: "
                        f"{rollback_error}"
                    )
            raise
    except BaseException as exc:
        publication_error = exc
        raise
    finally:
        cleanup_error: OSError | None = None
        temporary_paths = [stage for _destination, stage in staged]
        temporary_paths.extend(backups.values())
        for temporary_path in temporary_paths:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError as exc:
                if cleanup_error is None:
                    cleanup_error = exc
        if cleanup_error is not None:
            if publication_error is None:
                raise cleanup_error
            publication_error.add_note(
                f"Artifact staging cleanup failed: {cleanup_error}"
            )


def _stage_sibling_file(
    destination: Path,
    content: str | bytes,
    kind: str,
) -> Path:
    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.{kind}-",
        suffix=".tmp",
        dir=destination.parent,
    )
    os.close(file_descriptor)
    temporary_path = Path(temporary_name)
    try:
        if isinstance(content, bytes):
            temporary_path.write_bytes(content)
        else:
            temporary_path.write_text(content, encoding="utf-8")
    except BaseException as exc:
        try:
            temporary_path.unlink(missing_ok=True)
        except OSError as cleanup_error:
            exc.add_note(f"Artifact staging cleanup failed: {cleanup_error}")
        raise
    return temporary_path


def _remove_tree(path: Path, label: str) -> None:
    if not path.exists() and not path.is_symlink():
        return
    shutil.rmtree(path)
    if path.exists() or path.is_symlink():
        raise OSError(f"failed to remove {label}")


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _file_sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _config_hash(config: ToolConfig) -> str:
    payload = json.dumps(asdict(config), sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _content_identity(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if path.is_symlink() or not path.is_file():
            continue
        relative = path.relative_to(root)
        if any(part in {".git", ".context-search"} for part in relative.parts):
            continue
        digest.update(relative.as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return "sha256:" + digest.hexdigest()


def _git_commit(repo: Path) -> str | None:
    dot_git = repo / ".git"
    gitdir = dot_git
    if dot_git.is_file():
        gitdir_text = _read_git_text(dot_git)
        if gitdir_text is None or not gitdir_text.startswith("gitdir:"):
            return None
        raw_gitdir = gitdir_text.removeprefix("gitdir:").strip()
        if not raw_gitdir:
            return None
        try:
            gitdir = Path(raw_gitdir).expanduser()
            if not gitdir.is_absolute():
                gitdir = (repo / gitdir).resolve()
        except (OSError, RuntimeError, ValueError):
            return None

    head_path = gitdir / "HEAD"
    head = _read_git_text(head_path)
    if head is None:
        return None
    if not head.startswith("ref: "):
        return _validated_object_id(head)

    ref = head.removeprefix("ref: ").strip()
    if not _is_safe_git_ref(ref):
        return None
    for candidate_gitdir in _candidate_git_ref_dirs(gitdir):
        try:
            candidate_root = candidate_gitdir.resolve()
            refs_root = (candidate_root / "refs").resolve()
            ref_path = (candidate_root / ref).resolve()
        except (OSError, RuntimeError, ValueError):
            continue
        if not ref_path.is_relative_to(refs_root):
            continue
        object_id = _read_git_text(ref_path)
        if object_id is not None:
            return _validated_object_id(object_id)

    for candidate_gitdir in _candidate_git_ref_dirs(gitdir):
        packed_refs_text = _read_git_text(candidate_gitdir / "packed-refs")
        if packed_refs_text is None:
            continue
        for line in packed_refs_text.splitlines():
            if not line or line.startswith(("#", "^")):
                continue
            parts = line.split()
            if len(parts) == 2 and parts[1] == ref:
                return _validated_object_id(parts[0])
    return None


def _read_git_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError, ValueError):
        return None


def _validated_object_id(value: str) -> str | None:
    if re.fullmatch(r"(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})", value):
        return value
    return None


def _is_safe_git_ref(ref: str) -> bool:
    if not ref.startswith("refs/") or "\\" in ref:
        return False
    if any(ord(character) < 32 or ord(character) == 127 for character in ref):
        return False
    if any(character in ref for character in " ~^:?*["):
        return False
    if ".." in ref or "@{" in ref or "//" in ref:
        return False

    components = ref.split("/")
    return all(
        component
        and component not in {".", ".."}
        and not component.startswith(".")
        and not component.endswith((".", ".lock"))
        for component in components
    )


def _candidate_git_ref_dirs(gitdir: Path) -> list[Path]:
    candidates = [gitdir]
    common_gitdir = _common_gitdir(gitdir)
    if common_gitdir != gitdir:
        candidates.append(common_gitdir)
    return candidates


def _common_gitdir(gitdir: Path) -> Path:
    common_dir_file = gitdir / "commondir"
    raw_common_dir = _read_git_text(common_dir_file)
    if raw_common_dir is None or not raw_common_dir:
        return gitdir
    try:
        common_gitdir = Path(raw_common_dir).expanduser()
        if not common_gitdir.is_absolute():
            common_gitdir = (gitdir / common_gitdir).resolve()
        return common_gitdir
    except (OSError, RuntimeError, ValueError):
        return gitdir
