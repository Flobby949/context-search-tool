from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
from contextlib import ExitStack, contextmanager
from dataclasses import asdict, dataclass, is_dataclass, replace
from pathlib import Path, PureWindowsPath
from typing import Any, Iterator
from unittest.mock import patch
from xml.etree import ElementTree

import numpy as np

from context_search_tool import retrieval
from context_search_tool.config import DEFAULT_CONFIG, ToolConfig
from context_search_tool.context_pack import (
    build_context_pack,
    canonical_context_pack_bytes,
    resolve_context_pack_options,
)
from context_search_tool.embeddings import HashEmbeddingProvider
from context_search_tool.formatters import (
    format_json,
    format_markdown,
    format_trace_json,
    trace_payload,
)
from context_search_tool.indexer import index_repository
from context_search_tool.models import (
    EvidenceAnchor,
    QueryPlan,
    RetrievalCandidate,
    RetrievalResult,
    RetrievalSpan,
    SemanticMatch,
)
from context_search_tool.quality.cases import (
    QualityCase,
    QualityRepo,
    load_quality_fixture,
)
from context_search_tool.retrieval_trace import CANONICAL_TRACE_STAGES
from context_search_tool.sqlite_store import SQLiteStore
from context_search_tool.vector_store import NumpyVectorStore


ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "tests" / "fixtures" / "retrieval_quality" / "queries.json"
BASELINE_PATH = (
    ROOT
    / "tests"
    / "fixtures"
    / "retrieval_core_decomposition"
    / "baseline.json"
)
MIGRATION_LEDGER_PATH = BASELINE_PATH.with_name("migration_ledger.json")

IMPLEMENTATION_COMMIT = "34c5b5bd2189fbba4ead3902342706266c399b41"
DOCUMENTATION_BASELINE = "6e4eef4c61ecfdaaa6721e5d81a40832b90a4281"

CLEAN_ENVIRONMENT_VARIABLES = (
    "CST_RUN_P1_ACCEPTANCE",
    "CST_P2_REAL_CONTEXT_REPOS_DIR",
    "CST_SMOKE_INVESTMENT_ASSISTANT_REPO",
    "CST_SMOKE_REPOS_DIR",
    "CST_PLANNER_REQUESTS_REPO",
)

EXPECTED_CASE_KEYS = (
    ("ci", "program_tool", "watermark-remover"),
    ("ci", "program_tool", "mqtt-tool"),
    ("ci", "program_tool", "qrcode-tool"),
    ("ci", "program_tool", "json-to-entity"),
    ("ci", "program_tool", "app-layout-theme"),
    ("ci", "program_tool", "ai-chat"),
    ("ci", "java_spring_mini", "apply-audit-endpoint"),
    ("ci", "java_spring_mini", "workbench-audit-localized-cjk"),
    ("p2_context_pack", "context_pack_java", "workspace-page-flow"),
    ("p2_context_pack", "context_pack_java", "workspace-test-file"),
    ("p2_context_pack", "context_pack_java", "workspace-service-symbol"),
    ("p2_context_pack", "context_pack_frontend", "qrcode-feature-context"),
    ("p2_context_pack", "context_pack_docs", "program-tool-developer-docs"),
)

FULL_STAGE_LEDGER_KEYS = (
    "context_pack_java/workspace-page-flow",
    "context_pack_frontend/qrcode-feature-context",
    "context_pack_docs/program-tool-developer-docs",
    "java_spring_mini/apply-audit-endpoint",
)

INPUT_PATHS = (
    "tests/fixtures/retrieval_quality/queries.json",
    "tests/fixtures/real_projects/program_tool",
    "tests/fixtures/java-spring-mini",
    "tests/fixtures/context-pack-java",
    "tests/fixtures/context-pack-docs",
)

_STORE_OPERATION_METHODS = (
    "deleted_chunk_ids",
    "language_counts",
    "source_files_for_profile",
    "symbol_names_for_profile",
    "token_counts_for_profile",
    "direct_text_search",
    "signal_search",
    "path_symbol_search",
    "signals_for_chunk",
    "signals_for_chunks",
    "relations_for_source",
    "relations_for_sources",
    "relations_targeting",
    "chunks_matching_signal_or_symbol",
    "chunks_matching_signal_or_symbols",
    "chunk_for_id",
    "chunks_for_ids",
    "chunks_for_file",
    "chunks_in_directory",
    "lexical_search",
)


@dataclass(frozen=True)
class CharacterizationCase:
    profile: str
    repo: QualityRepo
    quality_case: QualityCase
    config: ToolConfig
    snapshot_path: Path

    @property
    def key(self) -> tuple[str, str, str]:
        return self.profile, self.repo.repo_key, self.quality_case.case_id

    @property
    def ledger_key(self) -> str:
        return f"{self.repo.repo_key}/{self.quality_case.case_id}"


def _git(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ("git", *args),
        cwd=ROOT,
        check=check,
        capture_output=True,
        text=True,
    )


def assert_clean_environment() -> None:
    present = [name for name in CLEAN_ENVIRONMENT_VARIABLES if name in os.environ]
    if present:
        raise RuntimeError(
            "characterization requires unset environment variables: "
            + ", ".join(present)
        )


def runtime_identity() -> dict[str, object]:
    return {
        "python_major_minor": [sys.version_info.major, sys.version_info.minor],
        "sys_platform": sys.platform,
        "os_name": os.name,
        "sqlite_version": sqlite3.sqlite_version,
    }


def assert_protected_source_identity() -> None:
    source_diff = _git(
        "diff",
        "--exit-code",
        IMPLEMENTATION_COMMIT,
        "--",
        "src/context_search_tool",
        check=False,
    )
    if source_diff.returncode:
        raise RuntimeError("production source differs from the protected baseline")
    status = _git(
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
        "--",
        "src/context_search_tool",
    ).stdout
    if status:
        raise RuntimeError("production source worktree is not clean")


def _tracked_worktree_paths(path: str) -> list[Path]:
    output = subprocess.run(
        (
            "git",
            "ls-files",
            "-z",
            "--cached",
            "--others",
            "--exclude-standard",
            "--",
            path,
        ),
        cwd=ROOT,
        check=True,
        capture_output=True,
    ).stdout
    return [ROOT / raw.decode("utf-8") for raw in output.split(b"\0") if raw]


def working_tree_content_hash(path: str) -> str:
    target = ROOT / path
    files = _tracked_worktree_paths(path)
    if target.is_file() and files == [target]:
        return hashlib.sha256(target.read_bytes()).hexdigest()

    digest = hashlib.sha256()
    for file_path in sorted(files, key=lambda item: item.relative_to(target).as_posix()):
        if file_path.is_symlink() or not file_path.is_file():
            raise RuntimeError(f"characterization input is not a regular file: {file_path}")
        relative = file_path.relative_to(target).as_posix().encode("utf-8")
        content = file_path.read_bytes()
        digest.update(relative)
        digest.update(b"\0")
        digest.update(str(len(content)).encode("ascii"))
        digest.update(b"\0")
        digest.update(content)
        digest.update(b"\0")
    return digest.hexdigest()


def characterization_input_identity() -> dict[str, object]:
    status = _git(
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
        "--",
        *INPUT_PATHS,
    ).stdout
    if status:
        raise RuntimeError("characterization inputs have tracked or untracked drift")

    baseline_diff = _git(
        "diff",
        "--exit-code",
        DOCUMENTATION_BASELINE,
        "--",
        *INPUT_PATHS,
        check=False,
    )
    if baseline_diff.returncode:
        raise RuntimeError("characterization inputs differ from documentation baseline")

    entries = []
    for path in INPUT_PATHS:
        oid = _git("rev-parse", f"{DOCUMENTATION_BASELINE}:{path}").stdout.strip()
        entries.append(
            {
                "path": path,
                "git_oid": oid,
                "working_tree_sha256": working_tree_content_hash(path),
            }
        )
    return {
        "documentation_baseline": DOCUMENTATION_BASELINE,
        "clean": True,
        "entries": entries,
    }


def parse_junit_evidence(path: Path) -> dict[str, object]:
    root = ElementTree.parse(path).getroot()
    suite = next(root.iter("testsuite"))
    tests = int(suite.attrib["tests"])
    failures = int(suite.attrib.get("failures", "0"))
    errors = int(suite.attrib.get("errors", "0"))
    skipped = int(suite.attrib.get("skipped", "0"))
    skips: list[dict[str, str]] = []
    xfails: list[dict[str, str]] = []
    for testcase in root.iter("testcase"):
        skipped_node = testcase.find("skipped")
        if skipped_node is None:
            continue
        entry = {
            "node_id": f"{testcase.attrib['classname']}::{testcase.attrib['name']}",
            "reason": skipped_node.attrib.get("message", ""),
        }
        if skipped_node.attrib.get("type") == "pytest.xfail":
            xfails.append(entry)
        else:
            skips.append(entry)
    evidence = {
        "passed": tests - failures - errors - skipped,
        "failed": failures,
        "errors": errors,
        "skipped": skipped,
        "skips": skips,
        "xfails": xfails,
    }
    if evidence["passed"] != 1884 or evidence["skipped"] != 9:
        raise RuntimeError("JUnit evidence is not the reviewed 1884/9 baseline")
    if failures or errors or len(skips) + len(xfails) != skipped:
        raise RuntimeError("JUnit evidence contains failures or inconsistent skips")
    return evidence


def _apply_sections(config: ToolConfig, overrides: dict[str, Any]) -> ToolConfig:
    result = config
    for section_name in ("index", "retrieval", "embedding", "query_planner"):
        if section_name in overrides:
            result = replace(
                result,
                **{
                    section_name: replace(
                        getattr(result, section_name),
                        **overrides[section_name],
                    )
                },
            )
    return result


def effective_config(
    repo: QualityRepo,
    profile_overrides: dict[str, Any],
) -> ToolConfig:
    result = _apply_sections(DEFAULT_CONFIG, repo.default_config)
    result = _apply_sections(result, profile_overrides)
    if "embedding" in profile_overrides:
        result = replace(
            result,
            embedding=replace(DEFAULT_CONFIG.embedding, **profile_overrides["embedding"]),
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


def load_characterization_cases() -> list[CharacterizationCase]:
    fixture = load_quality_fixture(CATALOG_PATH)
    cases: list[CharacterizationCase] = []
    for profile in ("ci", "p2_context_pack"):
        for repo in fixture.repos:
            if profile not in repo.profiles:
                continue
            if not repo.snapshot_path:
                raise RuntimeError(f"characterization repo lacks snapshot_path: {repo.repo_key}")
            snapshot = (ROOT / repo.snapshot_path).resolve()
            fixtures_root = (ROOT / "tests" / "fixtures").resolve()
            if not snapshot.is_relative_to(fixtures_root):
                raise RuntimeError(f"snapshot escapes repository fixtures: {repo.repo_key}")
            config = effective_config(repo, fixture.profile_configs[profile])
            for quality_case in repo.queries:
                if quality_case.profiles and profile not in quality_case.profiles:
                    continue
                cases.append(
                    CharacterizationCase(
                        profile=profile,
                        repo=repo,
                        quality_case=quality_case,
                        config=config,
                        snapshot_path=snapshot,
                    )
                )
    if tuple(item.key for item in cases) != EXPECTED_CASE_KEYS:
        raise RuntimeError("quality catalog does not expose the exact 8 ci and 5 p2 cases")
    return cases


def prepare_indexed_workspaces(
    temp_root: Path,
    cases: list[CharacterizationCase],
) -> dict[tuple[str, str], Path]:
    workspaces: dict[tuple[str, str], Path] = {}
    for case in cases:
        key = (case.profile, case.repo.repo_key)
        if key in workspaces:
            continue
        workspace = (temp_root / f"{case.profile}-{case.repo.repo_key}").resolve()
        shutil.copytree(case.snapshot_path, workspace)
        index_repository(workspace, case.config)
        workspaces[key] = workspace
    return workspaces


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_text(value: str | None) -> str | None:
    if value is None:
        return None
    return _sha256_bytes(value.encode("utf-8"))


def _semantic_matches(values: list[SemanticMatch]) -> list[dict[str, object]]:
    return [
        {"variant_id": item.variant_id, "score": float(item.score)}
        for item in values
    ]


def _span_projection(span: RetrievalSpan) -> dict[str, object]:
    return {
        "start_line": span.start_line,
        "end_line": span.end_line,
        "score": float(span.score),
        "sources": list(span.sources),
    }


def _planner_projection(plan: QueryPlan) -> dict[str, object]:
    return {
        "original_query": plan.original_query,
        "rewritten_queries": list(plan.rewritten_queries),
        "grep_keywords": list(plan.grep_keywords),
        "symbol_hints": list(plan.symbol_hints),
        "intent": plan.intent,
        "status": plan.status,
        "provider": plan.provider,
        "model": plan.model,
        "prompt_version": plan.prompt_version,
        "prompt_hash": plan.prompt_hash,
        "latency_ms": plan.latency_ms,
        "error": plan.error,
        "repo_profile_hash": plan.repo_profile_hash,
        "repo_profile_truncated": plan.repo_profile_truncated,
        "discarded_hints": list(plan.discarded_hints),
    }


def _result_projection(result: RetrievalResult) -> dict[str, object]:
    return {
        "file_path": result.file_path.as_posix(),
        "start_line": result.start_line,
        "end_line": result.end_line,
        "score": float(result.score),
        "score_parts": dict(result.score_parts),
        "reasons": list(result.reasons),
        "followup_keywords": list(result.followup_keywords),
        "semantic_matches": _semantic_matches(result.semantic_matches),
        "spans": [_span_projection(span) for span in result.spans],
        "content_sha256": _sha256_text(result.content),
        "context_content_sha256": _sha256_text(result._context_content),
    }


def _anchor_projection(anchor: EvidenceAnchor) -> dict[str, object]:
    return {
        "file_path": anchor.file_path.as_posix(),
        "start_line": anchor.start_line,
        "end_line": anchor.end_line,
        "score": float(anchor.score),
        "score_parts": dict(anchor.score_parts),
        "reasons": list(anchor.reasons),
        "anchor_kind": anchor.anchor_kind,
        "semantic_matches": _semantic_matches(anchor.semantic_matches),
        "content_sha256": _sha256_text(anchor.content),
        "context_content_sha256": _sha256_text(anchor._context_content),
    }


def internal_bundle_projection(bundle: retrieval.QueryBundle) -> dict[str, object]:
    return {
        "query": bundle.query,
        "expanded_tokens": list(bundle.expanded_tokens),
        "planner": _planner_projection(bundle.planner),
        "query_variants": [
            {
                "variant_id": item.variant_id,
                "text": item.text,
                "source": item.source,
            }
            for item in bundle.query_variants
        ],
        "variant_retrieval_status": bundle.variant_retrieval_status,
        "summary": {
            "entry_points": list(bundle.summary.entry_points),
            "implementation": list(bundle.summary.implementation),
            "related_types": list(bundle.summary.related_types),
            "possibly_legacy": list(bundle.summary.possibly_legacy),
        },
        "followup_keywords": list(bundle.followup_keywords),
        "results": [_result_projection(item) for item in bundle.results],
        "evidence_anchors": [
            _anchor_projection(item) for item in bundle.evidence_anchors
        ],
    }


def serialize_internal_projection(value: dict[str, object]) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=False,
        allow_nan=False,
    ).encode("utf-8")


def normalized_trace_bytes(
    case: CharacterizationCase,
    traced: retrieval.TracedQueryBundle,
) -> bytes:
    envelope = trace_payload(
        case.snapshot_path,
        case.quality_case.query,
        traced.trace,
    )
    envelope["repo"] = case.repo.snapshot_path
    trace = envelope["trace"]
    trace["duration_ms"] = 0
    for stage in trace["stages"]:
        stage["duration_ms"] = 0
    return format_trace_json(envelope).encode("utf-8")


def _normalize_path(path: Path, workspace: Path) -> str:
    absolute = path if path.is_absolute() else Path.cwd() / path
    try:
        return absolute.relative_to(workspace).as_posix() or "."
    except ValueError:
        return f"<external>/{absolute.name}"


def _safe_value(value: Any, workspace: Path) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, Path):
        return _normalize_path(value, workspace)
    if isinstance(value, str):
        if str(workspace) in value:
            return value.replace(str(workspace), "<workspace>")
        if "\n" in value or "\r" in value or len(value) > 240:
            encoded = value.encode("utf-8")
            return {
                "text_bytes": len(encoded),
                "text_sha256": _sha256_bytes(encoded),
            }
        return value
    if isinstance(value, bytes):
        return {"bytes": len(value), "sha256": _sha256_bytes(value)}
    if isinstance(value, np.ndarray):
        contiguous = np.ascontiguousarray(value)
        return {
            "shape": list(contiguous.shape),
            "dtype": str(contiguous.dtype),
            "sha256": _sha256_bytes(contiguous.tobytes()),
        }
    if isinstance(value, dict):
        return {
            str(key): _safe_value(item, workspace)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_safe_value(item, workspace) for item in value]
    if isinstance(value, (set, frozenset)):
        return sorted(_safe_value(item, workspace) for item in value)
    if is_dataclass(value):
        if value.__class__.__name__ == "RepoProfile":
            return {
                "profile_hash": value.profile_hash,
                "truncated": value.truncated,
                "language_count": len(value.languages),
                "source_root_count": len(value.source_roots),
                "important_file_count": len(value.important_files),
                "symbol_count": len(value.symbols),
                "token_count": len(value.tokens),
            }
        return _safe_value(asdict(value), workspace)
    return {"type": value.__class__.__name__}


def _safe_result(value: Any, workspace: Path) -> dict[str, object]:
    if value is None:
        return {"kind": "none"}
    if isinstance(value, dict):
        return {
            "kind": "mapping",
            "count": len(value),
            "keys": [_safe_value(key, workspace) for key in value],
        }
    if isinstance(value, (list, tuple, set, frozenset)):
        return {"kind": "sequence", "count": len(value)}
    return {"kind": value.__class__.__name__}


class OperationRecorder:
    def __init__(self, workspace: Path, run: str) -> None:
        self.workspace = workspace
        self.run = run
        self.phase = "live"
        self.entries: list[dict[str, object]] = []

    def add(
        self,
        operation: str,
        *,
        args: Any = None,
        kwargs: Any = None,
    ) -> dict[str, object]:
        entry: dict[str, object] = {
            "run": self.run,
            "phase": self.phase,
            "operation": operation,
        }
        if args is not None:
            entry["args"] = _safe_value(args, self.workspace)
        if kwargs:
            entry["kwargs"] = _safe_value(kwargs, self.workspace)
        self.entries.append(entry)
        return entry

    @contextmanager
    def in_phase(self, phase: str) -> Iterator[None]:
        previous = self.phase
        self.phase = phase
        try:
            yield
        finally:
            self.phase = previous

    @contextmanager
    def installed(self) -> Iterator[None]:
        with ExitStack() as stack:
            self._patch_planner(stack)
            self._patch_embedding(stack)
            self._patch_vector(stack)
            self._patch_store(stack)
            self._patch_paths(stack)
            self._patch_direct_probes(stack)
            yield

    def _patch_planner(self, stack: ExitStack) -> None:
        original_factory = retrieval.planner_from_config
        recorder = self

        class PlannerProxy:
            def __init__(self, planner: Any) -> None:
                self._planner = planner

            def plan(self, query: str, *, repo_profile: Any = None) -> QueryPlan:
                entry = recorder.add(
                    "planner.plan",
                    args={"query": query, "repo_profile": repo_profile},
                )
                result = self._planner.plan(query, repo_profile=repo_profile)
                entry["result"] = {
                    "status": result.status,
                    "rewritten_query_count": len(result.rewritten_queries),
                    "grep_keyword_count": len(result.grep_keywords),
                    "symbol_hint_count": len(result.symbol_hints),
                }
                return result

        def factory(config: Any) -> PlannerProxy:
            return PlannerProxy(original_factory(config))

        stack.enter_context(patch.object(retrieval, "planner_from_config", factory))

    def _patch_embedding(self, stack: ExitStack) -> None:
        original = HashEmbeddingProvider.embed_texts
        recorder = self

        def wrapped(provider: HashEmbeddingProvider, texts: list[str]) -> Any:
            entry = recorder.add(
                "embedding.embed_texts",
                args={
                    "texts": [
                        {
                            "bytes": len(text.encode("utf-8")),
                            "sha256": _sha256_text(text),
                        }
                        for text in texts
                    ]
                },
            )
            result = original(provider, texts)
            entry["result"] = {
                "count": len(result),
                "shapes": [list(vector.shape) for vector in result],
            }
            return result

        stack.enter_context(
            patch.object(HashEmbeddingProvider, "embed_texts", wrapped)
        )

    def _patch_vector(self, stack: ExitStack) -> None:
        original_init = NumpyVectorStore.__init__
        original_search = NumpyVectorStore.search
        recorder = self

        def wrapped_init(store: NumpyVectorStore, index_dir: Path) -> None:
            recorder.add("vector.init", args={"index_dir": index_dir})
            original_init(store, index_dir)

        def wrapped_search(
            store: NumpyVectorStore,
            query_vector: np.ndarray,
            top_k: int,
            deleted_ids: set[str],
        ) -> Any:
            entry = recorder.add(
                "vector.search",
                args={
                    "query_vector": query_vector,
                    "top_k": top_k,
                    "deleted_ids": deleted_ids,
                },
            )
            result = original_search(store, query_vector, top_k, deleted_ids)
            entry["result"] = {
                "count": len(result),
                "chunk_ids": [item.chunk_id for item in result],
                "scores": [float(item.score) for item in result],
            }
            return result

        stack.enter_context(patch.object(NumpyVectorStore, "__init__", wrapped_init))
        stack.enter_context(patch.object(NumpyVectorStore, "search", wrapped_search))

    def _patch_store(self, stack: ExitStack) -> None:
        recorder = self
        original_init = SQLiteStore.__init__

        def wrapped_init(store: SQLiteStore, db_path: Path) -> None:
            recorder.add("sqlite.init", args={"db_path": db_path})
            original_init(store, db_path)

        stack.enter_context(patch.object(SQLiteStore, "__init__", wrapped_init))
        for method_name in _STORE_OPERATION_METHODS:
            original = getattr(SQLiteStore, method_name)

            def make_wrapper(name: str, operation: Any) -> Any:
                def wrapper(store: SQLiteStore, *args: Any, **kwargs: Any) -> Any:
                    entry = recorder.add(
                        f"sqlite.{name}",
                        args=list(args),
                        kwargs=kwargs,
                    )
                    result = operation(store, *args, **kwargs)
                    entry["result"] = _safe_result(result, recorder.workspace)
                    return result

                return wrapper

            stack.enter_context(
                patch.object(
                    SQLiteStore,
                    method_name,
                    make_wrapper(method_name, original),
                )
            )

    def _patch_paths(self, stack: ExitStack) -> None:
        recorder = self
        for method_name in ("exists", "stat", "read_text", "open"):
            original = getattr(Path, method_name)

            def make_wrapper(name: str, operation: Any) -> Any:
                def wrapper(path: Path, *args: Any, **kwargs: Any) -> Any:
                    absolute = path if path.is_absolute() else Path.cwd() / path
                    if absolute.is_relative_to(recorder.workspace):
                        recorder.add(
                            f"path.{name}",
                            args={"path": path, "arguments": list(args)},
                            kwargs=kwargs,
                        )
                    return operation(path, *args, **kwargs)

                return wrapper

            stack.enter_context(
                patch.object(Path, method_name, make_wrapper(method_name, original))
            )

    def _patch_direct_probes(self, stack: ExitStack) -> None:
        owner, name = _owner_attribute(
            "context_search_tool.retrieval_core.candidates",
            "direct_text_probes",
            retrieval,
            "_direct_text_probes",
        )
        original = getattr(owner, name)
        recorder = self

        def wrapped(*args: Any, **kwargs: Any) -> Any:
            entry = recorder.add("direct_text.probes", args=list(args), kwargs=kwargs)
            result = original(*args, **kwargs)
            entry["result"] = {"count": len(result), "probes": list(result)}
            return result

        stack.enter_context(patch.object(owner, name, wrapped))


def _owner_attribute(
    future_module: str,
    future_name: str,
    current_owner: Any,
    current_name: str,
) -> tuple[Any, str]:
    try:
        module = __import__(future_module, fromlist=[future_name])
    except ImportError:
        return current_owner, current_name
    if hasattr(module, future_name):
        return module, future_name
    return current_owner, current_name


def _candidate_projection(candidate: RetrievalCandidate) -> dict[str, object]:
    return {
        "chunk_id": candidate.chunk_id,
        "score": float(candidate.score),
        "source": candidate.source,
        "score_parts": dict(candidate.score_parts),
        "semantic_matches": _semantic_matches(candidate.semantic_matches),
    }


def _ranked_projection(item: Any) -> dict[str, object]:
    return {
        "chunk_id": item.chunk.chunk_id,
        "file_path": item.chunk.file_path.as_posix(),
        "start_line": item.chunk.start_line,
        "end_line": item.chunk.end_line,
        "score": float(item.score),
        "score_parts": dict(item.score_parts),
        "reasons": list(item.reasons),
        "rank_tier": item.rank_tier,
        "rerank_score": float(item.rerank_score),
        "evidence_class": item.evidence_class,
        "evidence_priority": item.evidence_priority,
        "semantic_matches": _semantic_matches(item.semantic_matches),
        "pre_ceiling_rerank_score": float(item.pre_ceiling_rerank_score),
        "was_ceiling_clamped": item.was_ceiling_clamped,
    }


def _expanded_projection(item: Any) -> dict[str, object]:
    return {
        "origin_chunk_ids": list(item.chunk_ids),
        "file_path": item.file_path.as_posix(),
        "start_line": item.start_line,
        "end_line": item.end_line,
        "score": float(item.score),
        "score_parts": dict(item.score_parts),
        "reasons": list(item.reasons),
        "followup_keywords": list(item.followup_keywords),
        "rank_tier": item.rank_tier,
        "rerank_score": float(item.rerank_score),
        "evidence_class": item.evidence_class,
        "evidence_priority": item.evidence_priority,
        "semantic_matches": _semantic_matches(item.semantic_matches),
        "pre_ceiling_rerank_score": float(item.pre_ceiling_rerank_score),
        "was_ceiling_clamped": item.was_ceiling_clamped,
        "spans": [_span_projection(span) for span in item.spans],
        "content_sha256": _sha256_text(item.content),
        "context_content_sha256": _sha256_text(item._context_content),
    }


class StageLedgerRecorder:
    def __init__(
        self,
        case: CharacterizationCase,
        operations: OperationRecorder,
    ) -> None:
        self.case = case
        self.operations = operations
        self.live_outputs: dict[str, object] = {}
        self.query_understanding: dict[str, object] = {
            "original_tokens": [],
            "expanded_tokens": [],
            "variants": [],
            "discarded_variants": [],
            "hint_tokens": [],
        }
        self._ranked_stage_index = 0
        self._selection_input: list[Any] = []
        self._selection_result: Any = None

    @contextmanager
    def installed(self) -> Iterator[None]:
        with ExitStack() as stack:
            self._patch_query_understanding(stack)
            self._patch_candidate_stages(stack)
            self._patch_ranked_stages(stack)
            self._patch_expanded_stage(stack)
            self._patch_selection(stack)
            yield

    def _patch_query_understanding(self, stack: ExitStack) -> None:
        original_tokenize = retrieval.tokenize_query
        original_variants = retrieval.build_query_variants
        original_expand = retrieval.expand_query_plan_tokens
        original_hints = retrieval.planner_hint_tokens
        recorder = self

        def tokenize(value: str) -> Any:
            result = original_tokenize(value)
            if value == recorder.case.quality_case.query and not recorder.query_understanding[
                "original_tokens"
            ]:
                recorder.query_understanding["original_tokens"] = list(result)
            return result

        def variants(*args: Any, **kwargs: Any) -> Any:
            result, discarded = original_variants(*args, **kwargs)
            recorder.query_understanding["variants"] = [
                {
                    "variant_id": item.variant_id,
                    "text": item.text,
                    "source": item.source,
                }
                for item in result
            ]
            recorder.query_understanding["discarded_variants"] = list(discarded)
            return result, discarded

        def expand(*args: Any, **kwargs: Any) -> Any:
            result = original_expand(*args, **kwargs)
            recorder.query_understanding["expanded_tokens"] = list(result)
            return result

        def hints(*args: Any, **kwargs: Any) -> Any:
            result = original_hints(*args, **kwargs)
            recorder.query_understanding["hint_tokens"] = list(result)
            return result

        stack.enter_context(patch.object(retrieval, "tokenize_query", tokenize))
        stack.enter_context(patch.object(retrieval, "build_query_variants", variants))
        stack.enter_context(patch.object(retrieval, "expand_query_plan_tokens", expand))
        stack.enter_context(patch.object(retrieval, "planner_hint_tokens", hints))

    def _patch_candidate_stages(self, stack: ExitStack) -> None:
        original = retrieval._finish_candidate_stage
        recorder = self

        def wrapped(collector: Any, token: Any, **kwargs: Any) -> Any:
            with recorder.operations.in_phase("observation"):
                result = original(collector, token, **kwargs)
            if token is not None:
                recorder.live_outputs[token.name] = [
                    _candidate_projection(item) for item in kwargs["candidates"]
                ]
            return result

        stack.enter_context(
            patch.object(retrieval, "_finish_candidate_stage", wrapped)
        )

    def _patch_ranked_stages(self, stack: ExitStack) -> None:
        original = retrieval._trace_ranked_observations
        recorder = self

        def wrapped(ranked: list[Any], *args: Any, **kwargs: Any) -> Any:
            stage_name = ("ranking", "cohort_rerank")[recorder._ranked_stage_index]
            recorder._ranked_stage_index += 1
            recorder.live_outputs[stage_name] = [
                _ranked_projection(item) for item in ranked
            ]
            return original(ranked, *args, **kwargs)

        stack.enter_context(
            patch.object(retrieval, "_trace_ranked_observations", wrapped)
        )

    def _patch_expanded_stage(self, stack: ExitStack) -> None:
        original = retrieval._trace_expanded_observations
        recorder = self

        def wrapped(expanded: list[Any], *args: Any, **kwargs: Any) -> Any:
            recorder.live_outputs["context_expansion"] = [
                _expanded_projection(item) for item in expanded
            ]
            return original(expanded, *args, **kwargs)

        stack.enter_context(
            patch.object(retrieval, "_trace_expanded_observations", wrapped)
        )

    def _patch_selection(self, stack: ExitStack) -> None:
        owner, name = _owner_attribute(
            "context_search_tool.retrieval_core.selection",
            "split_results_and_anchors",
            retrieval,
            "_split_code_results_and_evidence_anchors",
        )
        original_split = getattr(owner, name)
        original_trace = retrieval._trace_final_selections
        recorder = self

        def split(expanded: list[Any], **kwargs: Any) -> Any:
            recorder._selection_input = list(expanded)
            result = original_split(expanded, **kwargs)
            recorder._selection_result = result
            return result

        def trace(decisions: Any, *args: Any, **kwargs: Any) -> Any:
            result = original_trace(decisions, *args, **kwargs)
            recorder.live_outputs["final_selection"] = {
                "input": [
                    _expanded_projection(item) for item in recorder._selection_input
                ],
                "selected": [
                    {
                        "kind": item.kind,
                        "reason": item.reason,
                        "origin_chunk_ids": list(item.item.chunk_ids),
                        "file_path": item.item.file_path.as_posix(),
                        "start_line": item.item.start_line,
                        "end_line": item.item.end_line,
                    }
                    for item in decisions.selected
                ],
                "decision_counts": [list(item) for item in decisions.counts],
            }
            return result

        stack.enter_context(patch.object(owner, name, split))
        stack.enter_context(
            patch.object(retrieval, "_trace_final_selections", trace)
        )

    def finalize(self, traced: retrieval.TracedQueryBundle) -> dict[str, object]:
        self.live_outputs["query_understanding"] = {
            **self.query_understanding,
            "plan": _planner_projection(traced.bundle.planner),
            "variant_retrieval_status": traced.bundle.variant_retrieval_status,
        }
        trace_stages = {stage.name: stage for stage in traced.trace.stages}
        if tuple(trace_stages) != tuple(CANONICAL_TRACE_STAGES):
            raise RuntimeError("full-stage case did not execute all fifteen stages")
        if set(self.live_outputs) != set(CANONICAL_TRACE_STAGES):
            missing = set(CANONICAL_TRACE_STAGES) - set(self.live_outputs)
            raise RuntimeError(f"full-stage wrappers missed stages: {sorted(missing)}")

        stages = []
        for name in CANONICAL_TRACE_STAGES:
            trace_stage = trace_stages[name]
            stages.append(
                {
                    "name": name,
                    "input_count": trace_stage.input_count,
                    "output_count": trace_stage.output_count,
                    "unique_output_count": trace_stage.unique_output_count,
                    "source_counts": [list(item) for item in trace_stage.source_counts],
                    "decision_counts": [
                        list(item) for item in trace_stage.decision_counts
                    ],
                    "live_output": self.live_outputs[name],
                }
            )
        selections = traced.trace.final_selections
        covered = sum(
            bool(item.sources and item.rank_history and item.selection_reason)
            for item in selections
        )
        return {
            "stages": stages,
            "trace_contract": {
                "stage_names": [stage.name for stage in traced.trace.stages],
                "source_counts": [list(item) for item in traced.trace.source_counts],
                "final_selection_count": traced.trace.final_selection_count,
                "trace_coverage": covered / len(selections) if selections else 0.0,
            },
            "operations": list(self.operations.entries),
        }


def run_characterization_case(
    case: CharacterizationCase,
    workspace: Path,
    expected_entry: dict[str, object] | None = None,
) -> tuple[dict[str, object], dict[str, object] | None, set[str]]:
    ordinary_operations = OperationRecorder(workspace, "ordinary")
    with ordinary_operations.installed():
        plain = retrieval.query_repository(
            workspace,
            case.quality_case.query,
            case.config,
        )

    traced_operations = OperationRecorder(workspace, "traced")
    stage_recorder = StageLedgerRecorder(case, traced_operations)
    with traced_operations.installed(), stage_recorder.installed():
        traced = retrieval.trace_repository(
            workspace,
            case.quality_case.query,
            case.config,
        )

    if traced.bundle != plain:
        raise RuntimeError(f"plain/traced bundle drift for {case.ledger_key}")

    hashes = {
        "json_sha256": _sha256_text(format_json(plain)),
        "markdown_sha256": _sha256_text(format_markdown(plain)),
        "trace_json_sha256": _sha256_bytes(normalized_trace_bytes(case, traced)),
        "internal_bundle_sha256": _sha256_bytes(
            serialize_internal_projection(internal_bundle_projection(plain))
        ),
    }
    entry: dict[str, object] = {
        "profile": case.profile,
        "repo_key": case.repo.repo_key,
        "case_id": case.quality_case.case_id,
        "query": case.quality_case.query,
        "snapshot_identifier": case.repo.snapshot_path,
        "effective_config": asdict(case.config),
        "hashes": hashes,
        "ordinary_operations": ordinary_operations.entries,
        "traced_operations": traced_operations.entries,
    }

    if case.profile == "p2_context_pack":
        options = resolve_context_pack_options(
            case.config,
            context_lines=None,
            max_evidence_anchors=retrieval.evidence_anchor_top_k(
                case.config.retrieval.final_top_k
            ),
        )
        resolved_options = asdict(options)
        if expected_entry is not None:
            expected_options = expected_entry["context_pack"]["resolved_options"]
            if resolved_options != expected_options:
                raise RuntimeError(
                    f"ContextPack options drifted before build for {case.ledger_key}"
                )
        pack = build_context_pack(plain, options)
        entry["context_pack"] = {
            "resolved_options": resolved_options,
            "sha256": _sha256_bytes(canonical_context_pack_bytes(pack)),
            "maximum_pack_bytes": case.quality_case.maximum_pack_bytes,
            "maximum_truncated_items": case.quality_case.maximum_truncated_items,
        }

    full_ledger = (
        stage_recorder.finalize(traced)
        if case.ledger_key in FULL_STAGE_LEDGER_KEYS
        else None
    )
    source_texts = {
        *(item.content for item in plain.results),
        *(item._context_content for item in plain.results if item._context_content),
        *(item.content for item in plain.evidence_anchors),
        *(
            item._context_content
            for item in plain.evidence_anchors
            if item._context_content
        ),
    }
    return entry, full_ledger, source_texts


def build_case_characterization(
    temp_root: Path,
    expected_cases: list[dict[str, object]] | None = None,
) -> tuple[list[dict[str, object]], dict[str, object], set[str]]:
    cases = load_characterization_cases()
    expected_by_key = {
        (entry["profile"], entry["repo_key"], entry["case_id"]): entry
        for entry in expected_cases or []
    }
    workspaces = prepare_indexed_workspaces(temp_root, cases)
    entries: list[dict[str, object]] = []
    ledgers: dict[str, object] = {}
    source_texts: set[str] = set()
    for case in cases:
        entry, full_ledger, case_source_texts = run_characterization_case(
            case,
            workspaces[(case.profile, case.repo.repo_key)],
            expected_by_key.get(case.key),
        )
        entries.append(entry)
        source_texts.update(case_source_texts)
        if full_ledger is not None:
            ledgers[case.ledger_key] = full_ledger
    if set(ledgers) != set(FULL_STAGE_LEDGER_KEYS):
        raise RuntimeError("full-stage ledger keys drifted")
    ordered_ledgers = {key: ledgers[key] for key in FULL_STAGE_LEDGER_KEYS}
    return entries, ordered_ledgers, source_texts


def reject_sensitive_manifest(
    value: object,
    *,
    temporary_roots: tuple[Path, ...] = (),
    source_texts: set[str] | None = None,
) -> None:
    serialized = json.dumps(value, ensure_ascii=True, sort_keys=False)
    forbidden_roots = {
        str(ROOT),
        *(str(path.resolve()) for path in temporary_roots),
    }
    for root in forbidden_roots:
        if root and root in serialized:
            raise RuntimeError("manifest contains an absolute repository/temp path")
    for prefix in ('"/tmp/', '"/private/tmp/', '"/Users/'):
        if prefix in serialized:
            raise RuntimeError("manifest contains an absolute filesystem path")
    for environment_value in {
        value for value in os.environ.values() if len(value) >= 8
    }:
        if environment_value in serialized:
            raise RuntimeError("manifest contains an environment value")

    def visit(item: object, key: str = "") -> None:
        lowered = key.lower()
        if key in {"content", "_context_content"}:
            raise RuntimeError("manifest contains unhashed source content")
        if any(token in lowered for token in ("headers", "secret", "api_key")):
            if item not in (None, "", {}, []):
                raise RuntimeError(f"manifest contains sensitive field: {key}")
        if lowered in {"prompt", "system_prompt", "user_prompt"}:
            raise RuntimeError("manifest contains a prompt")
        if isinstance(item, dict):
            for child_key, child in item.items():
                visit(child, str(child_key))
        elif isinstance(item, (list, tuple)):
            for child in item:
                visit(child, key)
        elif isinstance(item, str):
            if PureWindowsPath(item).drive:
                raise RuntimeError("manifest contains an absolute Windows path")

    visit(value)
    for source_text in source_texts or set():
        if len(source_text) >= 8 and source_text in serialized:
            raise RuntimeError("manifest contains raw source text")


def baseline_projection(
    temp_root: Path,
    *,
    expected_cases: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    assert_clean_environment()
    entries, ledgers, source_texts = build_case_characterization(
        temp_root,
        expected_cases,
    )
    projection = {
        "cases": entries,
        "full_stage_ledgers": ledgers,
    }
    reject_sensitive_manifest(
        projection,
        temporary_roots=(temp_root,),
        source_texts=source_texts,
    )
    return projection
