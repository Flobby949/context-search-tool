from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import time
from dataclasses import asdict, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from context_search_tool.config import DEFAULT_CONFIG, ToolConfig
from context_search_tool.indexer import index_repository
from context_search_tool.manifest import load_manifest
from context_search_tool.quality.cases import (
    QualityCase,
    QualityFixture,
    QualityRepo,
    load_quality_fixture,
    validate_profile_compatible,
)
from context_search_tool.quality.metrics import CaseEvaluation, evaluate_case
from context_search_tool.retrieval import query_repository


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


def run_quality_fixture(
    fixture_path: Path,
    profile: str,
    output_path: Path | None,
    markdown_path: Path | None,
    keep_workspace: bool = False,
    config: ToolConfig = DEFAULT_CONFIG,
) -> dict[str, Any]:
    fixture = load_quality_fixture(fixture_path)
    validate_profile_compatible(profile, config)

    temp_root = Path(tempfile.mkdtemp(prefix="cst-quality-"))
    repos: list[dict[str, Any]] = []
    cases: list[dict[str, Any]] = []

    try:
        for repo in fixture.repos:
            if profile not in repo.profiles:
                continue

            repo_config = _apply_repo_config(config, repo.default_config)
            validate_profile_compatible(profile, repo_config)
            source = _resolve_repo_source(repo, fixture.path, profile)
            if source is None or not source.is_dir():
                cases.extend(_case_records_for_repo(repo, "skipped", "repo not found"))
                continue

            workspace = temp_root / repo.repo_key
            _copy_source_repo(source, workspace)

            try:
                summary = index_repository(workspace, repo_config)
                manifest = load_manifest(workspace)
            except Exception as exc:
                cases.extend(_case_records_for_repo(repo, "error", str(exc)))
                continue

            repos.append(
                {
                    "repo_key": repo.repo_key,
                    "source": {
                        "type": "snapshot_path" if repo.snapshot_path else "external",
                        "path": str(source),
                        "git_commit": _git_commit(source),
                        "content_hash": _content_identity(source),
                    },
                    "workspace": {
                        "path": str(workspace),
                        "copied": True,
                    },
                    "index": {
                        "manifest_schema_version": manifest.schema_version,
                        "embedding_config_hash": manifest.embedding_config_hash,
                        "config_hash": _config_hash(repo_config),
                        "files_indexed": summary.files_indexed,
                        "chunks_indexed": summary.chunks_indexed,
                    },
                }
            )

            for case in repo.queries:
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
                    cases.append(_case_record(repo.repo_key, case, evaluation))
                except Exception as exc:
                    cases.append(_error_case_record(repo.repo_key, case, str(exc)))

        report = _report(fixture, profile, config, repos, cases)
        if output_path is not None:
            output_path.write_text(
                json.dumps(report, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
        if markdown_path is not None:
            from context_search_tool.quality.reports import render_markdown_report

            markdown_path.write_text(render_markdown_report(report), encoding="utf-8")
        return report
    finally:
        if not keep_workspace:
            shutil.rmtree(temp_root, ignore_errors=True)


def _apply_repo_config(
    config: ToolConfig,
    overrides: dict[str, Any],
) -> ToolConfig:
    result = config
    if "index" in overrides:
        result = replace(result, index=replace(result.index, **overrides["index"]))
    if "retrieval" in overrides:
        result = replace(
            result,
            retrieval=replace(result.retrieval, **overrides["retrieval"]),
        )
    if "embedding" in overrides:
        result = replace(
            result,
            embedding=replace(result.embedding, **overrides["embedding"]),
        )
    if "query_planner" in overrides:
        result = replace(
            result,
            query_planner=replace(result.query_planner, **overrides["query_planner"]),
        )
    return result


def _resolve_repo_source(
    repo: QualityRepo,
    fixture_path: Path,
    profile: str,
) -> Path | None:
    if profile == "ci":
        if not repo.snapshot_path:
            raise ValueError(
                f"ci profile requires snapshot_path for repo {repo.repo_key}"
            )
        return _resolve_snapshot_path(fixture_path, repo.snapshot_path)

    if repo.snapshot_path:
        return _resolve_snapshot_path(fixture_path, repo.snapshot_path)
    if repo.path_env:
        env_path = os.environ.get(repo.path_env)
        if env_path:
            return Path(env_path).expanduser().resolve()
    if repo.repo_dir_name:
        smoke_root = os.environ.get("CST_SMOKE_REPOS_DIR")
        if smoke_root:
            return (Path(smoke_root).expanduser() / repo.repo_dir_name).resolve()
    return None


def _resolve_snapshot_path(fixture_path: Path, raw_path: str) -> Path:
    path = Path(raw_path).expanduser()
    if path.is_absolute():
        return path.resolve()

    fixture_relative = (fixture_path.parent / path).resolve()
    if fixture_relative.exists():
        return fixture_relative
    return (Path.cwd() / path).resolve()


def _copy_source_repo(source: Path, workspace: Path) -> None:
    def ignore(_directory: str, names: list[str]) -> set[str]:
        return {name for name in names if name in _COPY_EXCLUDES}

    shutil.copytree(source, workspace, ignore=ignore)


def _report(
    fixture: QualityFixture,
    profile: str,
    config: ToolConfig,
    repos: list[dict[str, Any]],
    cases: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "schema_version": 1,
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
        "aggregate": _aggregate(cases),
        "repos": repos,
        "cases": cases,
    }


def _case_record(
    repo_key: str,
    case: QualityCase,
    evaluation: CaseEvaluation,
) -> dict[str, Any]:
    return {
        "repo_key": repo_key,
        "case_id": case.case_id,
        "query": case.query,
        "tags": list(case.tags),
        "gate": case.gate.value,
        "status": evaluation.status,
        "metrics": evaluation.metrics,
        "top_results": evaluation.top_results,
        "failures": evaluation.failures,
    }


def _case_records_for_repo(
    repo: QualityRepo,
    status: str,
    reason: str,
) -> list[dict[str, Any]]:
    return [
        _empty_case_record(repo.repo_key, case, status, reason)
        for case in repo.queries
    ]


def _error_case_record(
    repo_key: str,
    case: QualityCase,
    reason: str,
) -> dict[str, Any]:
    return _empty_case_record(repo_key, case, "error", reason)


def _empty_case_record(
    repo_key: str,
    case: QualityCase,
    status: str,
    reason: str,
) -> dict[str, Any]:
    return {
        "repo_key": repo_key,
        "case_id": case.case_id,
        "query": case.query,
        "tags": list(case.tags),
        "gate": case.gate.value,
        "status": status,
        "metrics": {},
        "top_results": [],
        "failures": [reason],
    }


def _aggregate(cases: list[dict[str, Any]]) -> dict[str, int]:
    statuses = [case["status"] for case in cases]
    return {
        "total": len(cases),
        "passed": statuses.count("pass"),
        "failed": statuses.count("fail"),
        "skipped": statuses.count("skipped"),
        "known_gaps": statuses.count("known_gap"),
        "errors": statuses.count("error"),
    }


def _file_sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _config_hash(config: ToolConfig) -> str:
    payload = json.dumps(asdict(config), sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _content_identity(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if not path.is_file():
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
        gitdir_text = dot_git.read_text(encoding="utf-8").strip()
        if not gitdir_text.startswith("gitdir:"):
            return None
        raw_gitdir = gitdir_text.removeprefix("gitdir:").strip()
        if not raw_gitdir:
            return None
        gitdir = Path(raw_gitdir).expanduser()
        if not gitdir.is_absolute():
            gitdir = (repo / gitdir).resolve()

    head_path = gitdir / "HEAD"
    if not head_path.exists():
        return None
    head = head_path.read_text(encoding="utf-8").strip()
    if not head.startswith("ref: "):
        return head or None

    ref = head.removeprefix("ref: ").strip()
    for refs_dir in _candidate_git_ref_dirs(gitdir):
        ref_path = refs_dir / ref
        if ref_path.exists():
            return ref_path.read_text(encoding="utf-8").strip() or None

    for refs_dir in _candidate_git_ref_dirs(gitdir):
        packed_refs = refs_dir / "packed-refs"
        if not packed_refs.exists():
            continue
        for line in packed_refs.read_text(encoding="utf-8").splitlines():
            if not line or line.startswith(("#", "^")):
                continue
            parts = line.split()
            if len(parts) == 2 and parts[1] == ref:
                return parts[0]
    return None


def _candidate_git_ref_dirs(gitdir: Path) -> list[Path]:
    candidates = [gitdir]
    common_gitdir = _common_gitdir(gitdir)
    if common_gitdir != gitdir:
        candidates.append(common_gitdir)
    return candidates


def _common_gitdir(gitdir: Path) -> Path:
    common_dir_file = gitdir / "commondir"
    if not common_dir_file.exists():
        return gitdir
    raw_common_dir = common_dir_file.read_text(encoding="utf-8").strip()
    if not raw_common_dir:
        return gitdir
    common_gitdir = Path(raw_common_dir).expanduser()
    if not common_gitdir.is_absolute():
        common_gitdir = (gitdir / common_gitdir).resolve()
    return common_gitdir
