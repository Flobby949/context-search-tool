from __future__ import annotations

import hashlib
import json
import ntpath
import os
import re
import shutil
import stat
import tempfile
import threading
import time
import unicodedata
from collections.abc import Iterator
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any
from urllib.parse import quote

try:
    import fcntl
except ImportError:  # pragma: no cover - POSIX quality runs use fcntl.
    fcntl = None  # type: ignore[assignment]

from context_search_tool.config import DEFAULT_CONFIG, ToolConfig
from context_search_tool.context_pack import (
    ContextPack,
    build_context_pack,
    resolve_context_pack_options,
)
from context_search_tool.indexer import index_repository
from context_search_tool.manifest import load_manifest
from context_search_tool.models import QueryPlan
from context_search_tool.quality.aggregate import aggregate_cases
from context_search_tool.quality.cases import (
    Gate,
    QualityCase,
    QualityFixture,
    QualityRepo,
    load_quality_fixture,
    validate_profile_compatible,
)
from context_search_tool.quality.metrics import (
    CaseEvaluation,
    evaluate_case,
    evaluate_context_pack,
)
from context_search_tool.retrieval import (
    QueryBundle,
    evidence_anchor_top_k,
    query_repository,
)


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

_SNAPSHOT_ONLY_PROFILES = frozenset(
    {"ci", "p1_vector_bge", "p1_hybrid_bge", "p2_context_pack"}
)

_DESCRIPTOR_COPY_SUPPORTED = (
    os.name == "posix"
    and hasattr(os, "O_DIRECTORY")
    and hasattr(os, "O_NOFOLLOW")
    and os.open in os.supports_dir_fd
    and os.scandir in os.supports_fd
)

_DESCRIPTOR_GIT_READ_SUPPORTED = (
    os.name == "posix"
    and hasattr(os, "O_DIRECTORY")
    and hasattr(os, "O_NOFOLLOW")
    and os.open in os.supports_dir_fd
)

_ARTIFACT_PUBLICATION_THREAD_LOCK = threading.Lock()
_ARTIFACT_PUBLICATION_LOCK_ROOT = (
    Path("/tmp").resolve()
    if os.name == "posix"
    else Path(tempfile.gettempdir()).resolve()
)
_ARTIFACT_PUBLICATION_LOCK_PATH = _ARTIFACT_PUBLICATION_LOCK_ROOT / (
    ".context-search-tool-quality-publication-"
    f"{os.getuid() if hasattr(os, 'getuid') else 'user'}.lock"
)


@dataclass(frozen=True)
class ResolvedSource:
    path: Path
    source_type: str
    locator: str


@dataclass(frozen=True)
class _ArtifactVersion:
    device: int
    inode: int
    size: int
    sha256: str


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
            api_key_env = repo_config.embedding.api_key_env
            api_key = (os.environ.get(api_key_env) or None) if api_key_env else None
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
                        _safe_error(exc, source.path, workspace, api_key),
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
                    evaluation = _apply_profile_expectations(
                        case,
                        profile,
                        bundle,
                        evaluation,
                    )
                    pack: ContextPack | None = None
                    if case.mode == "context_pack":
                        pack_options = resolve_context_pack_options(
                            repo_config,
                            context_lines=None,
                            full_file=False,
                            max_evidence_anchors=evidence_anchor_top_k(
                                repo_config.retrieval.final_top_k
                            ),
                        )
                        pack = build_context_pack(bundle, pack_options)
                        evaluation = evaluate_context_pack(case, pack, evaluation)
                    cases.append(
                        _case_record(
                            repo.repo_key,
                            case,
                            evaluation,
                            bundle,
                            pack=pack,
                        )
                    )
                except Exception as exc:
                    cases.append(
                        _error_case_record(
                            repo.repo_key,
                            case,
                            _safe_error(exc, source.path, workspace, api_key),
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
    if profile in _SNAPSHOT_ONLY_PROFILES:
        if not repo.snapshot_path:
            raise ValueError(
                f"{profile} profile requires snapshot_path for repo {repo.repo_key}"
            )
        snapshot = _existing_resolved_directory(
            _resolve_snapshot_path(fixture_path, repo.snapshot_path)
        )
        if snapshot is None:
            raise ValueError(f"{profile} snapshot not found for repo {repo.repo_key}")
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
    *,
    pack: ContextPack | None = None,
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
        "query_variants": [
            {
                "variant_id": variant.variant_id,
                "text": variant.text,
                "source": variant.source,
            }
            for variant in bundle.query_variants
        ],
        "variant_retrieval_status": bundle.variant_retrieval_status,
        **(
            {
                "context_pack": {
                    "status": pack.status,
                    "confidence": pack.confidence.level,
                }
            }
            if pack is not None
            else {}
        ),
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


def _apply_profile_expectations(
    case: QualityCase,
    profile: str,
    bundle: QueryBundle,
    evaluation: CaseEvaluation,
) -> CaseEvaluation:
    expectation = case.profile_expectations.get(profile)
    if expectation is None:
        return evaluation

    failures = list(evaluation.failures)
    if (
        expectation.planner_status is not None
        and bundle.planner.status != expectation.planner_status
    ):
        failures.append(
            "planner_status expected "
            f"{expectation.planner_status}, got {bundle.planner.status}"
        )
    if (
        expectation.variant_retrieval_status is not None
        and bundle.variant_retrieval_status
        != expectation.variant_retrieval_status
    ):
        failures.append(
            "variant_retrieval_status expected "
            f"{expectation.variant_retrieval_status}, got "
            f"{bundle.variant_retrieval_status}"
        )

    actual_planner_match = bool(
        bundle.results
        and any(
            match.variant_id.startswith("planner:")
            for match in bundle.results[0].semantic_matches
        )
    )
    expected_planner_match = expectation.top_result_planner_semantic_match
    if (
        expected_planner_match is not None
        and actual_planner_match != expected_planner_match
    ):
        failures.append(
            "top_result_planner_semantic_match expected "
            f"{str(expected_planner_match).lower()}, got "
            f"{str(actual_planner_match).lower()}"
        )

    status = evaluation.status
    if case.gate is Gate.REQUIRED:
        status = "fail" if failures else "pass"
    return replace(
        evaluation,
        status=status,
        failures=failures,
    )


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


def _safe_error(
    exc: Exception,
    source: Path,
    workspace: Path,
    api_key: str | None = None,
) -> str:
    message = str(exc)
    replacements = [
        (variant, replacement)
        for path, replacement in (
            (workspace, "<workspace>"),
            (workspace.parent, "<workspace>"),
            (source, "<source>"),
        )
        for variant in _path_redaction_variants(path)
    ]
    if api_key:
        replacements.append((api_key, "<api-key>"))
    sentinels = _redaction_sentinels(
        message,
        [variant for variant, _replacement in replacements],
        {replacement for _variant, replacement in replacements},
    )
    ordered_replacements = sorted(
        [
            (variant, sentinels[replacement])
            for variant, replacement in replacements
        ],
        key=lambda item: len(
            _casefold_text(_percent_decode_text_with_spans(item[0])[0])
        ),
        reverse=True,
    )
    for variant, replacement in ordered_replacements:
        message = _replace_literal_sensitive(message, variant, replacement)
        message = _replace_casefold_equivalent(message, variant, replacement)
    for placeholder, sentinel in sentinels.items():
        message = message.replace(sentinel, placeholder)
    return message


def _redaction_sentinels(
    message: str,
    sensitive_variants: list[str],
    placeholders: set[str],
) -> dict[str, str]:
    unavailable = set(message)
    for value in [message, *sensitive_variants]:
        unavailable.update(value)
        unavailable.update(_percent_decode_text_with_spans(value)[0])

    candidates = (
        character
        for start, stop in (
            (0xE000, 0xF900),
            (0xF0000, 0xFFFFE),
            (0x100000, 0x10FFFE),
        )
        for character in map(chr, range(start, stop))
        if character not in unavailable
    )
    return {
        placeholder: next(candidates)
        for placeholder in sorted(placeholders)
    }


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

    path_spellings.update(
        {
            unicodedata.normalize(form, spelling)
            for spelling in path_spellings
            for form in ("NFC", "NFD")
        }
    )

    variants.update(path_spellings)
    encoded_spellings = path_spellings | {
        spelling.casefold() for spelling in path_spellings
    }
    for spelling in encoded_spellings:
        try:
            variants.add(Path(spelling).as_uri())
        except ValueError:
            pass
        variants.add(quote(spelling, safe="/"))
        variants.add(quote(spelling, safe=""))
    return {variant for variant in variants if variant}


def _replace_literal_sensitive(
    message: str,
    sensitive: str,
    replacement: str,
) -> str:
    parts: list[str] = []
    search_from = 0
    while True:
        start = message.find(sensitive, search_from)
        if start < 0:
            parts.append(message[search_from:])
            return "".join(parts)
        end = start + len(sensitive)
        while end < len(message) and unicodedata.combining(message[end]) != 0:
            end += 1
        parts.extend((message[search_from:start], replacement))
        search_from = end


def _replace_casefold_equivalent(
    message: str,
    sensitive: str,
    replacement: str,
) -> str:
    decoded_message, decoded_spans = _percent_decode_text_with_spans(message)
    decoded_sensitive, _sensitive_spans = _percent_decode_text_with_spans(sensitive)
    folded_message, ranges = _casefold_text_with_ranges(decoded_message)
    folded_sensitive = _casefold_text(decoded_sensitive)
    if not folded_sensitive:
        return message

    spans: list[tuple[int, int]] = []
    search_from = 0
    while True:
        folded_start = folded_message.find(folded_sensitive, search_from)
        if folded_start < 0:
            break
        folded_end = folded_start + len(folded_sensitive)
        starts_at_cluster = (
            folded_start == 0
            or ranges[folded_start - 1] != ranges[folded_start]
        )
        match_end = folded_end
        if (
            match_end < len(ranges)
            and ranges[match_end - 1] == ranges[match_end]
        ):
            cluster_range = ranges[match_end - 1]
            while match_end < len(ranges) and ranges[match_end] == cluster_range:
                match_end += 1
            if not all(
                unicodedata.combining(character) != 0
                for character in folded_message[folded_end:match_end]
            ):
                search_from = folded_start + 1
                continue
        if starts_at_cluster:
            decoded_start, _ = ranges[folded_start]
            _, decoded_end = ranges[match_end - 1]
            start = decoded_spans[decoded_start][0]
            end = decoded_spans[decoded_end - 1][1]
            spans.append((start, end))
            search_from = match_end
        else:
            search_from = folded_start + 1

    for start, end in reversed(spans):
        message = message[:start] + replacement + message[end:]
    return _replace_terminal_cluster_equivalent(
        message,
        sensitive,
        replacement,
    )


def _replace_terminal_cluster_equivalent(
    message: str,
    sensitive: str,
    replacement: str,
) -> str:
    decoded_message, decoded_spans = _percent_decode_text_with_spans(message)
    decoded_sensitive, _sensitive_spans = _percent_decode_text_with_spans(sensitive)
    message_clusters = _text_clusters(decoded_message)
    sensitive_clusters = _text_clusters(decoded_sensitive)
    if not sensitive_clusters or len(sensitive_clusters) > len(message_clusters):
        return message

    spans: list[tuple[int, int]] = []
    cluster_index = 0
    match_width = len(sensitive_clusters)
    while cluster_index <= len(message_clusters) - match_width:
        candidate = message_clusters[cluster_index : cluster_index + match_width]
        prior_clusters_match = all(
            _casefold_text(message_cluster[2])
            == _casefold_text(sensitive_cluster[2])
            for message_cluster, sensitive_cluster in zip(
                candidate[:-1],
                sensitive_clusters[:-1],
                strict=True,
            )
        )
        if prior_clusters_match and _terminal_cluster_contains(
            candidate[-1][2],
            sensitive_clusters[-1][2],
        ):
            decoded_start = candidate[0][0]
            decoded_end = candidate[-1][1]
            spans.append(
                (
                    decoded_spans[decoded_start][0],
                    decoded_spans[decoded_end - 1][1],
                )
            )
            cluster_index += match_width
        else:
            cluster_index += 1

    for start, end in reversed(spans):
        message = message[:start] + replacement + message[end:]
    return message


def _text_clusters(value: str) -> list[tuple[int, int, str]]:
    clusters: list[tuple[int, int, str]] = []
    cluster_start = 0
    for index in range(1, len(value) + 1):
        if index < len(value) and unicodedata.combining(value[index]) != 0:
            continue
        clusters.append((cluster_start, index, value[cluster_start:index]))
        cluster_start = index
    return clusters


def _terminal_cluster_contains(message_cluster: str, sensitive_cluster: str) -> bool:
    message_folded = _casefold_text(message_cluster)
    sensitive_folded = _casefold_text(sensitive_cluster)
    message_base = "".join(
        character
        for character in message_folded
        if unicodedata.combining(character) == 0
    )
    sensitive_base = "".join(
        character
        for character in sensitive_folded
        if unicodedata.combining(character) == 0
    )
    if message_base != sensitive_base:
        return False

    remaining_marks = [
        character
        for character in message_folded
        if unicodedata.combining(character) != 0
    ]
    for mark in (
        character
        for character in sensitive_folded
        if unicodedata.combining(character) != 0
    ):
        try:
            remaining_marks.remove(mark)
        except ValueError:
            return False
    return True


def _percent_decode_text_with_spans(
    value: str,
) -> tuple[str, list[tuple[int, int]]]:
    decoded_parts: list[str] = []
    spans: list[tuple[int, int]] = []
    index = 0
    while index < len(value):
        run_start = index
        encoded_bytes = bytearray()
        byte_spans: list[tuple[int, int]] = []
        while index + 2 < len(value) and value[index] == "%":
            try:
                encoded_byte = int(value[index + 1 : index + 3], 16)
            except ValueError:
                break
            encoded_bytes.append(encoded_byte)
            byte_spans.append((index, index + 3))
            index += 3

        if encoded_bytes:
            try:
                decoded_run = bytes(encoded_bytes).decode("utf-8")
            except UnicodeDecodeError:
                decoded_run = value[run_start:index]
                decoded_parts.extend(decoded_run)
                spans.extend(
                    (run_start + offset, run_start + offset + 1)
                    for offset in range(len(decoded_run))
                )
                continue

            byte_offset = 0
            for character in decoded_run:
                byte_length = len(character.encode("utf-8"))
                decoded_parts.append(character)
                spans.append(
                    (
                        byte_spans[byte_offset][0],
                        byte_spans[byte_offset + byte_length - 1][1],
                    )
                )
                byte_offset += byte_length
            continue

        decoded_parts.append(value[index])
        spans.append((index, index + 1))
        index += 1

    return "".join(decoded_parts), spans


def _casefold_text(value: str) -> str:
    return unicodedata.normalize(
        "NFD",
        unicodedata.normalize("NFD", value).casefold(),
    )


def _casefold_text_with_ranges(
    value: str,
) -> tuple[str, list[tuple[int, int]]]:
    folded_parts: list[str] = []
    ranges: list[tuple[int, int]] = []
    cluster_start = 0
    for index in range(1, len(value) + 1):
        if index < len(value) and unicodedata.combining(value[index]) != 0:
            continue
        folded = _casefold_text(value[cluster_start:index])
        folded_parts.append(folded)
        ranges.extend([(cluster_start, index)] * len(folded))
        cluster_start = index
    return "".join(folded_parts), ranges


def _render_artifacts(
    report: dict[str, Any],
    output_path: Path | None,
    markdown_path: Path | None,
) -> list[tuple[Path, str]]:
    _validate_artifact_destinations(
        [path for path in (output_path, markdown_path) if path is not None]
    )
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
    with _artifact_publication_lock():
        _validate_artifact_destinations(
            [destination for destination, _content in artifacts]
        )
        _publish_artifact_transaction(artifacts)


@contextmanager
def _artifact_publication_lock() -> Iterator[None]:
    with _ARTIFACT_PUBLICATION_THREAD_LOCK:
        lock_descriptor: int | None = None
        try:
            if fcntl is not None:
                flags = os.O_CREAT | os.O_RDWR
                flags |= getattr(os, "O_CLOEXEC", 0)
                flags |= getattr(os, "O_NOFOLLOW", 0)
                lock_descriptor = os.open(
                    _ARTIFACT_PUBLICATION_LOCK_PATH,
                    flags,
                    0o600,
                )
                lock_status = os.fstat(lock_descriptor)
                if (
                    not stat.S_ISREG(lock_status.st_mode)
                    or lock_status.st_nlink != 1
                ):
                    raise OSError(
                        "artifact publication lock is not a single-link regular file"
                    )
                if (
                    hasattr(os, "getuid")
                    and lock_status.st_uid != os.getuid()
                ):
                    raise OSError("artifact publication lock has an unexpected owner")
                os.fchmod(lock_descriptor, 0o600)
                if stat.S_IMODE(os.fstat(lock_descriptor).st_mode) != 0o600:
                    raise OSError("artifact publication lock has unsafe permissions")
                fcntl.flock(lock_descriptor, fcntl.LOCK_EX)
            yield
        finally:
            if lock_descriptor is not None:
                os.close(lock_descriptor)


def _publish_artifact_transaction(artifacts: list[tuple[Path, str]]) -> None:
    staged: list[tuple[Path, Path]] = []
    backups: dict[Path, Path] = {}
    replaced: list[Path] = []
    published_versions: dict[Path, _ArtifactVersion] = {}
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
            try:
                _status, original_content = _read_regular_artifact(destination)
            except FileNotFoundError:
                continue
            backups[destination] = _stage_sibling_file(
                destination,
                original_content,
                "backup",
            )

        try:
            for destination, stage in staged:
                published_versions[destination] = _artifact_version(stage)
                os.replace(stage, destination)
                replaced.append(destination)
        except BaseException as exc:
            for destination in reversed(replaced):
                # Cooperative publishers hold the transaction lock. The version
                # guard catches noncooperative changes observed before rollback;
                # filesystems do not offer a portable CAS across check and rename.
                if not _artifact_matches_version(
                    destination,
                    published_versions[destination],
                ):
                    exc.add_note(
                        f"Artifact rollback skipped for {destination.name}: "
                        "destination changed by another writer; "
                        "artifact pair may require recovery"
                    )
                    continue
                try:
                    backup = backups.pop(destination, None)
                    if backup is None:
                        destination.unlink(missing_ok=True)
                    else:
                        os.replace(backup, destination)
                except BaseException as rollback_error:
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


def _validate_artifact_destinations(destinations: list[Path]) -> None:
    normalized: list[tuple[Path, str, os.stat_result | None]] = []
    for destination in destinations:
        try:
            identity = _artifact_destination_identity(destination)
            try:
                destination_status = destination.lstat()
            except FileNotFoundError:
                destination_status = None
        except (OSError, RuntimeError, ValueError) as exc:
            raise ValueError(f"invalid artifact destination: {destination}") from exc

        for previous, previous_identity, _previous_status in normalized:
            aliases = identity == previous_identity
            if not aliases:
                try:
                    aliases = os.path.samefile(destination, previous)
                except (FileNotFoundError, OSError, ValueError):
                    aliases = False
            if aliases:
                raise ValueError("artifact destinations must be distinct")
        normalized.append((destination, identity, destination_status))

    for destination, _identity, destination_status in normalized:
        if destination_status is None:
            continue
        if (
            not stat.S_ISREG(destination_status.st_mode)
            or destination_status.st_nlink != 1
        ):
            raise ValueError(
                "invalid artifact destination: existing destination must be "
                f"a single-link regular file: {destination}"
            )


def _artifact_destination_identity(destination: Path) -> str:
    normalized = os.path.normpath(str(destination.expanduser().resolve()))
    normalized = normalized.replace(os.sep, "/")
    if os.altsep is not None:
        normalized = normalized.replace(os.altsep, "/")
    return unicodedata.normalize("NFD", normalized).casefold()


def _artifact_version(path: Path) -> _ArtifactVersion:
    status, content = _read_regular_artifact(path)
    return _ArtifactVersion(
        device=status.st_dev,
        inode=status.st_ino,
        size=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
    )


def _artifact_matches_version(path: Path, version: _ArtifactVersion) -> bool:
    try:
        status, content = _read_regular_artifact(path)
        if (
            status.st_dev != version.device
            or status.st_ino != version.inode
            or status.st_size != version.size
        ):
            return False
    except OSError:
        return False
    return (
        hashlib.sha256(content).hexdigest() == version.sha256
    )


def _read_regular_artifact(path: Path) -> tuple[os.stat_result, bytes]:
    flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )
    file_descriptor = os.open(path, flags)
    try:
        status = os.fstat(file_descriptor)
        if not stat.S_ISREG(status.st_mode) or status.st_nlink != 1:
            raise OSError(
                f"artifact path is not a single-link regular file: {path.name}"
            )
        artifact_file = os.fdopen(file_descriptor, "rb")
        file_descriptor = -1
        with artifact_file:
            return status, artifact_file.read()
    finally:
        if file_descriptor >= 0:
            os.close(file_descriptor)


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
    temporary_path = Path(temporary_name)
    try:
        opened_status = os.fstat(file_descriptor)
        if not stat.S_ISREG(opened_status.st_mode):
            raise OSError("artifact staging descriptor is not a regular file")
        payload = content if isinstance(content, bytes) else content.encode("utf-8")
        staged_file = os.fdopen(file_descriptor, "wb")
        file_descriptor = -1
        with staged_file:
            staged_file.write(payload)

        named_status = temporary_path.lstat()
        if (
            not stat.S_ISREG(named_status.st_mode)
            or named_status.st_dev != opened_status.st_dev
            or named_status.st_ino != opened_status.st_ino
        ):
            raise OSError("artifact staging path changed during write")
    except BaseException as exc:
        if file_descriptor >= 0:
            os.close(file_descriptor)
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
    metadata_dirs = _git_metadata_dirs(repo)
    if metadata_dirs is None:
        return None
    gitdir, ref_dirs = metadata_dirs

    head_path = gitdir / "HEAD"
    head = _read_git_text(head_path, gitdir)
    if head is None:
        return None
    if not head.startswith("ref: "):
        return _validated_object_id(head)

    ref = head.removeprefix("ref: ").strip()
    if not _is_safe_git_ref(ref):
        return None
    for candidate_gitdir in ref_dirs:
        try:
            refs_path = candidate_gitdir / "refs"
            if not stat.S_ISDIR(refs_path.lstat().st_mode):
                continue
            candidate_root = candidate_gitdir.resolve(strict=True)
            refs_root = refs_path.resolve(strict=True)
            if not refs_root.is_relative_to(candidate_root):
                continue
            ref_path = candidate_gitdir / ref
        except (OSError, RuntimeError, ValueError):
            continue
        object_id = _read_git_text(ref_path, refs_root)
        if object_id is not None:
            return _validated_object_id(object_id)

    for candidate_gitdir in ref_dirs:
        packed_refs_text = _read_git_text(
            candidate_gitdir / "packed-refs",
            candidate_gitdir,
        )
        if packed_refs_text is None:
            continue
        for line in packed_refs_text.splitlines():
            if not line or line.startswith(("#", "^")):
                continue
            parts = line.split()
            if len(parts) == 2 and parts[1] == ref:
                return _validated_object_id(parts[0])
    return None


def _git_metadata_dirs(repo: Path) -> tuple[Path, tuple[Path, ...]] | None:
    try:
        repo_root = repo.resolve(strict=True)
        dot_git = repo_root / ".git"
        dot_git_mode = dot_git.lstat().st_mode
    except (OSError, RuntimeError, ValueError):
        return None

    if stat.S_ISDIR(dot_git_mode):
        return dot_git, (dot_git,)
    if not stat.S_ISREG(dot_git_mode):
        return None

    gitdir_text = _read_git_text(dot_git, repo_root)
    if gitdir_text is None or not gitdir_text.startswith("gitdir:"):
        return None
    raw_gitdir = gitdir_text.removeprefix("gitdir:").strip()
    gitdir = _resolved_metadata_directory(repo_root, raw_gitdir)
    if gitdir is None or gitdir.parent.name != "worktrees":
        return None

    common_gitdir = gitdir.parent.parent
    try:
        if not stat.S_ISDIR(common_gitdir.lstat().st_mode):
            return None
    except OSError:
        return None

    raw_common_dir = _read_git_text(gitdir / "commondir", gitdir)
    if raw_common_dir is None:
        return None
    resolved_common_dir = _resolved_metadata_directory(gitdir, raw_common_dir)
    if resolved_common_dir != common_gitdir:
        return None

    raw_backlink = _read_git_text(gitdir / "gitdir", gitdir)
    if raw_backlink is None:
        return None
    try:
        backlink = _resolve_metadata_path(gitdir, raw_backlink)
        expected_backlink = dot_git.resolve(strict=True)
    except (OSError, RuntimeError, ValueError):
        return None
    if backlink != expected_backlink:
        return None

    return gitdir, (gitdir, common_gitdir)


def _resolved_metadata_directory(base: Path, raw_path: str) -> Path | None:
    try:
        candidate = Path(raw_path)
        if not candidate.is_absolute():
            candidate = base / candidate
        if not stat.S_ISDIR(candidate.lstat().st_mode):
            return None
        return candidate.resolve(strict=True)
    except (OSError, RuntimeError, ValueError):
        return None


def _resolve_metadata_path(base: Path, raw_path: str) -> Path:
    candidate = Path(raw_path)
    if not candidate.is_absolute():
        candidate = base / candidate
    return candidate.resolve(strict=True)


def _read_git_text(path: Path, boundary: Path) -> str | None:
    if not _DESCRIPTOR_GIT_READ_SUPPORTED:
        return None

    directory_descriptors: list[int] = []
    file_descriptor: int | None = None
    try:
        boundary_status = boundary.lstat()
        if not stat.S_ISDIR(boundary_status.st_mode):
            return None
        try:
            relative = path.relative_to(boundary)
        except ValueError:
            return None
        if (
            not relative.parts
            or any(part in {"", ".", ".."} for part in relative.parts)
        ):
            return None

        directory_flags = (
            os.O_RDONLY
            | os.O_DIRECTORY
            | os.O_NOFOLLOW
            | getattr(os, "O_CLOEXEC", 0)
        )
        boundary_descriptor = _open_directory_no_follow(boundary, directory_flags)
        directory_descriptors.append(boundary_descriptor)
        opened_boundary_status = os.fstat(boundary_descriptor)
        if (
            not stat.S_ISDIR(opened_boundary_status.st_mode)
            or opened_boundary_status.st_dev != boundary_status.st_dev
            or opened_boundary_status.st_ino != boundary_status.st_ino
        ):
            return None
        for component in relative.parts[:-1]:
            directory_descriptors.append(
                os.open(
                    component,
                    directory_flags,
                    dir_fd=directory_descriptors[-1],
                )
            )

        file_flags = (
            os.O_RDONLY
            | os.O_NOFOLLOW
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NONBLOCK", 0)
        )
        file_descriptor = os.open(
            relative.parts[-1],
            file_flags,
            dir_fd=directory_descriptors[-1],
        )
        if not stat.S_ISREG(os.fstat(file_descriptor).st_mode):
            return None
        with os.fdopen(file_descriptor, "r", encoding="utf-8") as metadata_file:
            file_descriptor = None
            return metadata_file.read().strip()
    except (OSError, UnicodeError, ValueError):
        return None
    finally:
        if file_descriptor is not None:
            os.close(file_descriptor)
        for directory_descriptor in reversed(directory_descriptors):
            os.close(directory_descriptor)


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
