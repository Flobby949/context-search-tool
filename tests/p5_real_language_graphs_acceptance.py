from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import subprocess
import tempfile
from copy import deepcopy
from pathlib import Path, PureWindowsPath
from typing import Any

from context_search_tool.config import DEFAULT_CONFIG, ToolConfig
from context_search_tool.context_pack import canonical_context_pack_bytes
from context_search_tool.exploration import (
    explore_repository,
    resolve_explore_pack_options,
)
from context_search_tool.indexer import index_repository
from context_search_tool.quality.cases import (
    QualityCase,
    QualityFixture,
    QualityRepo,
    load_quality_fixture,
    validate_profile_compatible,
)
from context_search_tool.quality.metrics import CaseEvaluation
from context_search_tool.quality.runner import (
    ResolvedSource,
    _config_hash,
    _content_identity,
    _copy_source_repo,
    _effective_config,
    _evaluate_explored_case,
    _git_commit,
    _publish_artifacts,
    _resolve_repo_source,
)
from context_search_tool.retrieval_trace import exploration_trace_payload
from p5_graph_identity import (
    EXPECTED_REAL_CASES,
    IMPLEMENTATION_BASELINE,
    P5_MANIFEST_PATH,
    PETCLINIC_COMMIT,
    ROOT,
    assert_protected_inputs,
    load_input_manifest,
    load_raw_p5_real_catalog,
    sha256_file,
)


EXPECTED_PROFILE = "p5_real_language_graphs"
EXPECTED_CASES = EXPECTED_REAL_CASES
PROGRAM_TOOL_PATH = "tests/fixtures/real_projects/program_tool"
REAL_FIXTURE_PATH = "tests/fixtures/retrieval_quality/p5_real_language_graphs.json"
EXPECTED_PETCLINIC_TREE = "aad4bfa2cc84df0af381e91e39b26d7e01fa9970"
EXPECTED_PETCLINIC_CONTENT_HASH = (
    "sha256:3576d384bb61347b0c78f9156a9430d24e9778daa0e67689fff50eb27c57377c"
)
EXPECTED_PETCLINIC_INVENTORY_SHA256 = (
    "sha256:6fd30b873defc453adc90e5ae494ab74aed3e4a9c084c08afa414cbd446107cc"
)

PROJECTION_KEYS = (
    "schema_version",
    "fixture_sha256",
    "input_manifest_sha256",
    "profile",
    "profile_definition_sha256",
    "effective_config_hash",
    "cases",
    "aggregate",
)
CASE_KEYS = (
    "repo_key",
    "case_id",
    "query",
    "source",
    "budgets",
    "initial_result_paths",
    "initial_context_pack_paths",
    "initial_context_pack_sha256",
    "final_context_pack_paths",
    "final_context_pack_sha256",
    "trace",
    "non_timing_metrics",
    "status",
    "failures",
)
SOURCE_KEYS = (
    "source_type",
    "locator",
    "git_commit",
    "content_hash",
    "provenance",
    "inventory",
)
BUDGET_KEYS = ("limits", "observed")
LIMIT_KEYS = (
    "final_top_k",
    "pack_items",
    "retrieval_calls",
    "pack_bytes",
)
OBSERVED_BUDGET_KEYS = (
    "initial_results",
    "final_pack_items",
    "retrieval_calls",
    "pack_bytes",
)
AGGREGATE_KEYS = (
    "selected",
    "executed",
    "passed",
    "failed",
    "skipped",
    "errors",
)
EXPLORATION_METRICS = (
    "exploration_goal_coverage_initial",
    "exploration_goal_coverage_final",
    "exploration_goal_gain",
    "novel_path_count",
    "duplicate_path_ratio",
    "executed_probe_count",
    "probe_efficiency",
    "retrieval_call_count",
    "exploration_trace_coverage",
    "final_pack_noise_count",
    "final_pack_noise_ratio",
    "exploration_latency_ms",
)
NON_TIMING_METRICS = EXPLORATION_METRICS[:-1]

TRACE_KEYS = (
    "schema_version",
    "mode",
    "outcome",
    "termination_reason",
    "duration_ms",
    "limits",
    "initial_evidence_need_count",
    "candidate_goal_count",
    "retained_goal_count",
    "omitted_goal_count",
    "initial_satisfied_goal_count",
    "final_satisfied_goal_count",
    "planned_probe_count",
    "executed_probe_count",
    "stale_skipped_probe_count",
    "unexecuted_probe_count",
    "retrieval_call_count",
    "goals",
    "rounds",
    "final_evidence_count",
    "final_evidence_omitted_count",
    "final_evidence",
)
TRACE_LIMIT_KEYS = (
    "max_rounds",
    "max_followup_probes",
    "max_retrieval_calls",
    "max_planned_probes",
    "max_goals",
    "max_probe_code_points",
    "max_seed_paths",
    "max_frontend_import_header_bytes",
    "max_frontend_import_paths",
    "effective_initial_top_k",
    "followup_top_k",
    "max_fused_results",
    "max_fused_anchors",
    "final_evidence_top_k",
)
TRACE_GOAL_KEYS = (
    "id",
    "kind",
    "category",
    "accepted_roles",
    "required",
    "provenance",
    "initially_satisfied",
    "finally_satisfied",
)
TRACE_ROUND_KEYS = (
    "round_index",
    "kind",
    "duration_ms",
    "input_path_count",
    "output_path_count",
    "novel_path_count",
    "duplicate_path_count",
    "newly_satisfied_goal_ids",
    "probes",
)
TRACE_PROBE_KEYS = (
    "id",
    "query",
    "purpose",
    "source",
    "goal_ids",
    "seed_paths",
    "retrieval_outcome",
    "retrieval_termination_reason",
    "duration_ms",
    "result_count",
    "evidence_anchor_count",
    "unique_path_count",
    "duplicate_path_count",
    "novel_path_count",
    "newly_satisfied_goal_ids",
    "source_counts",
    "final_selection_count",
)
TRACE_SOURCE_COUNT_KEYS = (
    "semantic",
    "planner_semantic",
    "lexical",
    "path_symbol",
    "direct_text",
    "signal",
    "planner_lexical",
    "planner_path_symbol",
    "planner_signal",
    "anchor_expansion",
    "relation",
)
TRACE_FINAL_EVIDENCE_KEYS = (
    "item_id",
    "file_path",
    "source_round",
    "probe_id",
    "probe_rank",
    "goal_ids",
    "selection_reason",
)


def canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=False,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def _sha256_path(path: Path) -> str:
    return f"sha256:{sha256_file(path)}"


def _profile_definition_sha256(
    profile: str,
    profile_config: dict[str, Any],
) -> str:
    payload = json.dumps(
        {"profile": profile, "config": profile_config},
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _normalize_trace_timing(trace: dict[str, Any]) -> dict[str, Any]:
    normalized = deepcopy(trace)
    normalized["duration_ms"] = 0
    for round_record in normalized["rounds"]:
        round_record["duration_ms"] = 0
        for probe in round_record["probes"]:
            probe["duration_ms"] = 0
    restored = deepcopy(normalized)
    restored["duration_ms"] = trace["duration_ms"]
    for original_round, restored_round in zip(
        trace["rounds"],
        restored["rounds"],
        strict=True,
    ):
        restored_round["duration_ms"] = original_round["duration_ms"]
        for original_probe, restored_probe in zip(
            original_round["probes"],
            restored_round["probes"],
            strict=True,
        ):
            restored_probe["duration_ms"] = original_probe["duration_ms"]
    if restored != trace:
        raise ValueError("acceptance normalization changed a non-timing trace field")
    return normalized


def _pack_paths(pack: Any) -> list[str]:
    return [Path(item.file_path).as_posix() for item in pack.items]


def _regular_file_inventory(root: Path) -> list[str]:
    inventory: list[str] = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError("acceptance source inventory contains a symlink")
        if path.is_file():
            inventory.append(path.relative_to(root).as_posix())
    return inventory


def _inventory_sha256(inventory: list[str]) -> str:
    payload = json.dumps(
        inventory,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _git_read(repo: Path, *args: str) -> str:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=repo,
            check=True,
            capture_output=True,
            text=True,
            shell=False,
        )
    except (OSError, subprocess.SubprocessError):
        raise ValueError("PetClinic prepared source identity changed") from None
    return completed.stdout.strip()


def _assert_clean_petclinic_source(source: Path) -> None:
    status_output = _git_read(
        source,
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
        "--ignore-submodules=none",
    )
    if status_output:
        raise ValueError("PetClinic prepared source has tracked or untracked drift")
    if _git_read(source, "rev-parse", "HEAD^{tree}") != EXPECTED_PETCLINIC_TREE:
        raise ValueError("PetClinic prepared source tree changed")


def _load_contract(
    fixture_path: Path,
    profile: str,
) -> tuple[
    QualityFixture,
    tuple[tuple[QualityRepo, QualityCase, ToolConfig], ...],
    str,
]:
    if profile != EXPECTED_PROFILE:
        raise ValueError(f"acceptance profile must be {EXPECTED_PROFILE}")
    if fixture_path.is_symlink() or not fixture_path.is_file():
        raise ValueError("acceptance fixture must be a regular file")

    load_raw_p5_real_catalog(fixture_path)
    manifest = load_input_manifest()
    assert_protected_inputs()

    fixture_entry = next(
        (
            item
            for item in manifest["inputs"]
            if item.get("path") == REAL_FIXTURE_PATH
        ),
        None,
    )
    if fixture_entry is None:
        raise ValueError("P5 input manifest does not own the real fixture")
    if (
        sha256_file(fixture_path) != fixture_entry.get("sha256")
        or fixture_path.stat().st_size != fixture_entry.get("bytes")
    ):
        raise ValueError("P5 real fixture differs from the frozen input manifest")

    fixture = load_quality_fixture(fixture_path)
    selections: list[tuple[QualityRepo, QualityCase, ToolConfig]] = []
    actual_cases: list[tuple[str, str, str, str]] = []
    config_hashes: set[str] = set()
    for repo in fixture.repos:
        if profile not in repo.profiles:
            continue
        for case in repo.queries:
            if case.profiles and profile not in case.profiles:
                continue
            config = _effective_config(
                DEFAULT_CONFIG,
                repo.default_config,
                fixture.profile_configs[profile],
            )
            validate_profile_compatible(profile, config, canonical=fixture.canonical)
            if (
                config.retrieval.final_top_k != 12
                or config.context.max_items != 12
                or config.context.max_pack_bytes != 65536
            ):
                raise ValueError("P5 real profile budgets changed")
            selections.append((repo, case, config))
            actual_cases.append((repo.repo_key, case.case_id, case.query, case.mode))
            config_hashes.add(_config_hash(config))

    if tuple(actual_cases) != EXPECTED_CASES:
        raise ValueError("P5 real acceptance case inventory changed")
    if len(config_hashes) != 1:
        raise ValueError("P5 real repositories do not share one effective config")
    return fixture, tuple(selections), config_hashes.pop()


def _source_projection(
    repo: QualityRepo,
    source: ResolvedSource,
    workspace: Path,
) -> dict[str, Any]:
    if repo.repo_key == "spring_petclinic":
        _assert_clean_petclinic_source(source.path)
    source_content_hash = _content_identity(source.path)
    workspace_content_hash = _content_identity(workspace)
    if source_content_hash != workspace_content_hash:
        raise ValueError("acceptance workspace content differs from its source")

    if repo.repo_key == "spring_petclinic":
        actual_commit = _git_commit(source.path)
        if (
            source.source_type != "prepared_remote"
            or source.locator != repo.checkout_dir
            or repo.source_commit != PETCLINIC_COMMIT
            or actual_commit != PETCLINIC_COMMIT
        ):
            raise ValueError("PetClinic prepared source identity changed")
        provenance = {
            "source_url": repo.source_url,
            "source_commit": repo.source_commit,
            "checkout_dir": repo.checkout_dir,
            "source_tree": EXPECTED_PETCLINIC_TREE,
        }
        inventory = _regular_file_inventory(workspace)
        if (
            workspace_content_hash != EXPECTED_PETCLINIC_CONTENT_HASH
            or _inventory_sha256(inventory)
            != EXPECTED_PETCLINIC_INVENTORY_SHA256
        ):
            raise ValueError("PetClinic prepared source content changed")
    elif repo.repo_key == "program_tool":
        expected_root = (ROOT / PROGRAM_TOOL_PATH).resolve()
        if (
            source.source_type != "snapshot_path"
            or source.locator != PROGRAM_TOOL_PATH
            or source.path.resolve() != expected_root
            or repo.snapshot_path != PROGRAM_TOOL_PATH
        ):
            raise ValueError("program-tool protected source identity changed")
        actual_commit = None
        source_inventory = _regular_file_inventory(source.path)
        inventory = _regular_file_inventory(workspace)
        if source_inventory != inventory:
            raise ValueError("program-tool copied inventory changed")
        provenance = {
            "implementation_baseline": IMPLEMENTATION_BASELINE,
            "protected_path": PROGRAM_TOOL_PATH,
        }
    else:
        raise ValueError(f"unexpected P5 real repository: {repo.repo_key}")

    return {
        "source_type": source.source_type,
        "locator": source.locator,
        "git_commit": actual_commit,
        "content_hash": workspace_content_hash,
        "provenance": provenance,
        "inventory": inventory,
    }


def build_case_projection(
    repo: QualityRepo,
    case: QualityCase,
    config: ToolConfig,
    source: dict[str, Any],
    explored: Any,
    evaluation: CaseEvaluation,
) -> dict[str, Any]:
    missing = [name for name in EXPLORATION_METRICS if name not in evaluation.metrics]
    if missing:
        raise ValueError(f"exploration metric missing: {missing[0]}")

    initial_bytes = canonical_context_pack_bytes(explored.initial_pack)
    final_bytes = canonical_context_pack_bytes(explored.final_pack)
    if explored.final_pack.budget.pack_bytes != len(final_bytes):
        raise ValueError("final ContextPack byte accounting changed")
    raw_trace = exploration_trace_payload(explored.trace)
    _validate_trace_projection(
        raw_trace,
        case,
        evaluation.metrics["retrieval_call_count"],
        require_normalized_timing=False,
    )
    normalized_trace = _normalize_trace_timing(raw_trace)
    _validate_trace_projection(
        normalized_trace,
        case,
        evaluation.metrics["retrieval_call_count"],
        require_normalized_timing=True,
    )

    return {
        "repo_key": repo.repo_key,
        "case_id": case.case_id,
        "query": case.query,
        "source": source,
        "budgets": {
            "limits": {
                "final_top_k": config.retrieval.final_top_k,
                "pack_items": explored.final_pack.budget.max_items,
                "retrieval_calls": case.maximum_retrieval_call_count,
                "pack_bytes": case.maximum_pack_bytes,
            },
            "observed": {
                "initial_results": len(explored.initial_bundle.results),
                "final_pack_items": len(explored.final_pack.items),
                "retrieval_calls": evaluation.metrics["retrieval_call_count"],
                "pack_bytes": len(final_bytes),
            },
        },
        "initial_result_paths": [
            result.file_path.as_posix() for result in explored.initial_bundle.results
        ],
        "initial_context_pack_paths": _pack_paths(explored.initial_pack),
        "initial_context_pack_sha256": hashlib.sha256(initial_bytes).hexdigest(),
        "final_context_pack_paths": _pack_paths(explored.final_pack),
        "final_context_pack_sha256": hashlib.sha256(final_bytes).hexdigest(),
        "trace": normalized_trace,
        "non_timing_metrics": {
            name: evaluation.metrics[name] for name in NON_TIMING_METRICS
        },
        "status": evaluation.status,
        "failures": list(evaluation.failures),
    }


def run_projection(
    fixture_path: Path,
    profile: str,
    repos_dir: Path,
) -> dict[str, Any]:
    fixture, selections, effective_config_hash = _load_contract(
        fixture_path,
        profile,
    )
    case_projections: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="cst-p5-real-acceptance-") as temp:
        temp_root = Path(temp)
        for repo, case, config in selections:
            source = _resolve_repo_source(
                repo,
                fixture.path,
                profile,
                repos_dir,
            )
            if source is None:
                raise ValueError(f"acceptance source is unavailable: {repo.repo_key}")
            workspace = temp_root / repo.repo_key
            _copy_source_repo(source.path, workspace)
            source_projection = _source_projection(repo, source, workspace)
            index_repository(workspace, config)
            explored = explore_repository(
                workspace,
                case.query,
                config,
                resolve_explore_pack_options(config, context_lines=None),
            )
            evaluation = _evaluate_explored_case(case, profile, explored)
            case_projections.append(
                build_case_projection(
                    repo,
                    case,
                    config,
                    source_projection,
                    explored,
                    evaluation,
                )
            )

    projection = {
        "schema_version": 1,
        "fixture_sha256": _sha256_path(fixture_path),
        "input_manifest_sha256": _sha256_path(P5_MANIFEST_PATH),
        "profile": profile,
        "profile_definition_sha256": _profile_definition_sha256(
            profile,
            fixture.profile_configs[profile],
        ),
        "effective_config_hash": effective_config_hash,
        "cases": case_projections,
        "aggregate": _aggregate(case_projections),
    }
    _validate_projection_shape(
        projection,
        fixture_path,
        profile,
        fixture,
        selections,
        effective_config_hash,
    )
    canonical_json_bytes(projection)
    return projection


def _aggregate(cases: list[dict[str, Any]]) -> dict[str, int]:
    passed = sum(case.get("status") == "pass" for case in cases)
    failed = sum(case.get("status") == "fail" for case in cases)
    return {
        "selected": len(cases),
        "executed": len(cases),
        "passed": passed,
        "failed": failed,
        "skipped": 0,
        "errors": 0,
    }


def _read_regular_file(
    path: Path,
    label: str,
) -> tuple[Path, bytes, tuple[int, int]]:
    try:
        leaf_status = path.lstat()
        resolved = path.resolve(strict=True)
    except OSError:
        raise ValueError(f"{label} must be a regular non-symlink file") from None
    if stat.S_ISLNK(leaf_status.st_mode) or not stat.S_ISREG(leaf_status.st_mode):
        raise ValueError(f"{label} must be a regular non-symlink file")

    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(resolved, flags)
    except OSError:
        raise ValueError(f"{label} must be a regular non-symlink file") from None
    try:
        opened_status = os.fstat(descriptor)
        if not stat.S_ISREG(opened_status.st_mode):
            raise ValueError(f"{label} must be a regular non-symlink file")
        with os.fdopen(descriptor, "rb") as stream:
            descriptor = -1
            content = stream.read()
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    return resolved, content, (opened_status.st_dev, opened_status.st_ino)


def _resolved_new_output(path: Path) -> Path:
    if path.name in {"", ".", ".."}:
        raise ValueError("acceptance output path is invalid")
    try:
        path.lstat()
    except FileNotFoundError:
        pass
    except OSError:
        raise ValueError("acceptance output path is invalid") from None
    else:
        raise ValueError("acceptance baseline already exists")
    try:
        parent = path.parent.resolve(strict=True)
        parent_status = parent.lstat()
    except OSError:
        raise ValueError("acceptance output parent is invalid") from None
    if not stat.S_ISDIR(parent_status.st_mode):
        raise ValueError("acceptance output parent is invalid")
    output = parent / path.name
    if output.exists() or output.is_symlink():
        raise ValueError("acceptance baseline already exists")
    return output


def _atomic_write_new(output: Path, content: bytes) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output.name}.",
        dir=output.parent,
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o644)
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = -1
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, output)
        except FileExistsError:
            raise ValueError("acceptance baseline already exists") from None
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
    try:
        output_status = output.lstat()
    except OSError:
        raise ValueError("acceptance baseline publication failed") from None
    if stat.S_ISLNK(output_status.st_mode) or not stat.S_ISREG(output_status.st_mode):
        raise ValueError("acceptance baseline publication failed")


def initialize_projection(
    fixture_path: Path,
    profile: str,
    candidate_a: Path,
    candidate_b: Path,
    output: Path,
) -> None:
    first_path, first, first_identity = _read_regular_file(
        candidate_a,
        "acceptance candidate A",
    )
    second_path, second, second_identity = _read_regular_file(
        candidate_b,
        "acceptance candidate B",
    )
    output_path = _resolved_new_output(output)
    if (
        first_path == second_path
        or first_identity == second_identity
        or output_path in {first_path, second_path}
    ):
        raise ValueError("acceptance candidate and output files must be distinct")
    if first != second:
        raise ValueError("acceptance candidates differ")

    fixture, selections, effective_config_hash = _load_contract(
        fixture_path,
        profile,
    )
    projection = _load_projection_bytes(first)
    _validate_projection_shape(
        projection,
        fixture_path,
        profile,
        fixture,
        selections,
        effective_config_hash,
    )
    if canonical_json_bytes(projection) != first:
        raise ValueError("acceptance candidate is not canonical JSON")
    _atomic_write_new(output_path, first)


def verify_projection(candidate: Path, expected: Path) -> None:
    candidate_path, candidate_bytes, candidate_identity = _read_regular_file(
        candidate,
        "acceptance candidate",
    )
    expected_path, expected_bytes, expected_identity = _read_regular_file(
        expected,
        "acceptance expected baseline",
    )
    if candidate_path == expected_path or candidate_identity == expected_identity:
        raise ValueError("acceptance verify files must be distinct")
    if candidate_bytes != expected_bytes:
        raise ValueError("acceptance projection differs from expected baseline")


def _load_projection_bytes(content: bytes) -> dict[str, Any]:
    try:
        value = json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("acceptance candidate is not valid JSON") from exc
    if not isinstance(value, dict):
        raise ValueError("acceptance candidate must be an object")
    return value


def _validate_projection_shape(
    projection: dict[str, Any],
    fixture_path: Path,
    profile: str,
    fixture: QualityFixture,
    selections: tuple[tuple[QualityRepo, QualityCase, ToolConfig], ...],
    effective_config_hash: str,
) -> None:
    if tuple(projection) != PROJECTION_KEYS:
        raise ValueError("acceptance projection keys or order are invalid")
    if projection["schema_version"] != 1:
        raise ValueError("acceptance projection schema_version must be 1")
    if projection["fixture_sha256"] != _sha256_path(fixture_path):
        raise ValueError("acceptance fixture hash changed")
    if projection["input_manifest_sha256"] != _sha256_path(P5_MANIFEST_PATH):
        raise ValueError("acceptance input manifest hash changed")
    if projection["profile"] != profile:
        raise ValueError("acceptance profile identity changed")
    if projection["profile_definition_sha256"] != _profile_definition_sha256(
        profile,
        fixture.profile_configs[profile],
    ):
        raise ValueError("acceptance profile definition hash changed")
    if projection["effective_config_hash"] != effective_config_hash:
        raise ValueError("acceptance effective config hash changed")

    cases = projection["cases"]
    if not isinstance(cases, list) or len(cases) != len(EXPECTED_CASES):
        raise ValueError("acceptance projection must contain exactly two cases")
    for projected, (repo, case, config) in zip(cases, selections, strict=True):
        _validate_case_projection(projected, repo, case, config)

    expected_aggregate = {
        "selected": 2,
        "executed": 2,
        "passed": 2,
        "failed": 0,
        "skipped": 0,
        "errors": 0,
    }
    aggregate = projection["aggregate"]
    if (
        not isinstance(aggregate, dict)
        or tuple(aggregate) != AGGREGATE_KEYS
        or aggregate != expected_aggregate
        or aggregate != _aggregate(cases)
    ):
        raise ValueError("acceptance aggregate must be exactly 2/2")


def _validate_case_projection(
    projection: Any,
    repo: QualityRepo,
    case: QualityCase,
    config: ToolConfig,
) -> None:
    if not isinstance(projection, dict) or tuple(projection) != CASE_KEYS:
        raise ValueError("acceptance case keys or order are invalid")
    if (
        projection["repo_key"] != repo.repo_key
        or projection["case_id"] != case.case_id
        or projection["query"] != case.query
    ):
        raise ValueError("acceptance case identity does not match fixture")
    _validate_source_projection(projection["source"], repo)
    _validate_budgets(projection["budgets"], projection, case, config)

    for field in (
        "initial_result_paths",
        "initial_context_pack_paths",
        "final_context_pack_paths",
    ):
        _validate_paths(projection[field], field)
    for field in (
        "initial_context_pack_sha256",
        "final_context_pack_sha256",
    ):
        _validate_sha256(projection[field], field, prefixed=False)

    initial_paths = projection["initial_context_pack_paths"]
    final_paths = projection["final_context_pack_paths"]
    for matcher in case.initial_absent:
        if any(matcher.matches(path) for path in initial_paths):
            raise ValueError("acceptance initial_absent path is present")
    for matcher in case.final_present:
        if not any(matcher.matches(path) for path in final_paths):
            raise ValueError("acceptance final_present path is missing")
    if case.final_at_least is not None:
        matches = sum(
            any(matcher.matches(path) for path in final_paths)
            for matcher in case.final_at_least.matchers
        )
        if matches < case.final_at_least.min_matches:
            raise ValueError("acceptance final_at_least proof is missing")
    for matcher in case.final_forbidden:
        if any(matcher.matches(path) for path in final_paths):
            raise ValueError("acceptance final_forbidden path is present")

    _validate_trace_projection(
        projection["trace"],
        case,
        projection["budgets"]["observed"]["retrieval_calls"],
        require_normalized_timing=True,
    )

    metrics = projection["non_timing_metrics"]
    if not isinstance(metrics, dict) or tuple(metrics) != NON_TIMING_METRICS:
        raise ValueError("acceptance non-timing metrics are invalid")
    if final_paths and metrics["exploration_trace_coverage"] != 1.0:
        raise ValueError("acceptance exploration trace coverage must be 1.0")
    if (
        case.minimum_goal_gain is not None
        and metrics["exploration_goal_gain"] < case.minimum_goal_gain
    ):
        raise ValueError("acceptance exploration goal gain is too low")
    if (
        case.maximum_final_noise_items is not None
        and metrics["final_pack_noise_count"] > case.maximum_final_noise_items
    ):
        raise ValueError("acceptance final pack noise is too high")
    if projection["status"] != "pass" or projection["failures"] != []:
        raise ValueError("acceptance case did not pass")


def _closed_mapping(value: Any, keys: tuple[str, ...], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or tuple(value) != keys:
        raise ValueError(f"acceptance {label} schema is not closed")
    return value


def _closed_list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"acceptance {label} must be a list")
    return value


def _validate_trace_projection(
    value: Any,
    case: QualityCase,
    observed_retrieval_calls: int,
    *,
    require_normalized_timing: bool,
) -> None:
    trace = _closed_mapping(value, TRACE_KEYS, "trace")
    reviewed_mappings = {id(trace)}
    if (trace["schema_version"], trace["mode"]) != (2, "exploration"):
        raise ValueError("acceptance trace identity is invalid")

    limits = _closed_mapping(trace["limits"], TRACE_LIMIT_KEYS, "trace limits")
    reviewed_mappings.add(id(limits))
    if (
        limits["max_retrieval_calls"] != 3
        or limits["effective_initial_top_k"] != 12
    ):
        raise ValueError("acceptance trace limits changed")
    if trace["retrieval_call_count"] != observed_retrieval_calls:
        raise ValueError("acceptance trace retrieval call count changed")
    if (
        case.expected_termination_reason is not None
        and trace["termination_reason"] != case.expected_termination_reason
    ):
        raise ValueError("acceptance termination reason changed")
    if require_normalized_timing and trace["duration_ms"] != 0:
        raise ValueError("acceptance trace timing is not normalized")

    for goal in _closed_list(trace["goals"], "trace goals"):
        reviewed = _closed_mapping(goal, TRACE_GOAL_KEYS, "trace goal")
        reviewed_mappings.add(id(reviewed))

    for round_record in _closed_list(trace["rounds"], "trace rounds"):
        reviewed_round = _closed_mapping(
            round_record,
            TRACE_ROUND_KEYS,
            "trace round",
        )
        reviewed_mappings.add(id(reviewed_round))
        if require_normalized_timing and reviewed_round["duration_ms"] != 0:
            raise ValueError("acceptance round timing is not normalized")
        for probe in _closed_list(reviewed_round["probes"], "trace probes"):
            reviewed_probe = _closed_mapping(
                probe,
                TRACE_PROBE_KEYS,
                "trace probe",
            )
            reviewed_mappings.add(id(reviewed_probe))
            if require_normalized_timing and reviewed_probe["duration_ms"] != 0:
                raise ValueError("acceptance probe timing is not normalized")
            source_counts = _closed_mapping(
                reviewed_probe["source_counts"],
                TRACE_SOURCE_COUNT_KEYS,
                "trace source counts",
            )
            reviewed_mappings.add(id(source_counts))

    for evidence in _closed_list(trace["final_evidence"], "final evidence"):
        reviewed = _closed_mapping(
            evidence,
            TRACE_FINAL_EVIDENCE_KEYS,
            "final evidence item",
        )
        reviewed_mappings.add(id(reviewed))

    _validate_trace_values(trace, reviewed_mappings)


def _validate_trace_values(value: Any, reviewed_mappings: set[int]) -> None:
    if isinstance(value, dict):
        if id(value) not in reviewed_mappings:
            raise ValueError("acceptance trace contains an unreviewed mapping")
        for item in value.values():
            _validate_trace_values(item, reviewed_mappings)
        return
    if isinstance(value, list):
        for item in value:
            _validate_trace_values(item, reviewed_mappings)
        return
    if isinstance(value, str):
        windows_path = PureWindowsPath(value)
        if (
            Path(value).is_absolute()
            or bool(windows_path.drive)
            or "cst-p5-real-acceptance-" in value
        ):
            raise ValueError("acceptance trace contains an absolute temporary root")


def _validate_source_projection(source: Any, repo: QualityRepo) -> None:
    if not isinstance(source, dict) or tuple(source) != SOURCE_KEYS:
        raise ValueError("acceptance source keys or order are invalid")
    _validate_sha256(source["content_hash"], "content_hash", prefixed=True)

    if repo.repo_key == "spring_petclinic":
        expected = {
            "source_type": "prepared_remote",
            "locator": repo.checkout_dir,
            "git_commit": PETCLINIC_COMMIT,
            "content_hash": EXPECTED_PETCLINIC_CONTENT_HASH,
            "provenance": {
                "source_url": repo.source_url,
                "source_commit": PETCLINIC_COMMIT,
                "checkout_dir": repo.checkout_dir,
                "source_tree": EXPECTED_PETCLINIC_TREE,
            },
        }
        inventory = source["inventory"]
        _validate_paths(inventory, "PetClinic source inventory")
        if _inventory_sha256(inventory) != EXPECTED_PETCLINIC_INVENTORY_SHA256:
            raise ValueError("acceptance PetClinic source inventory changed")
    elif repo.repo_key == "program_tool":
        expected_root = ROOT / PROGRAM_TOOL_PATH
        expected = {
            "source_type": "snapshot_path",
            "locator": PROGRAM_TOOL_PATH,
            "git_commit": None,
            "content_hash": _content_identity(expected_root),
            "provenance": {
                "implementation_baseline": IMPLEMENTATION_BASELINE,
                "protected_path": PROGRAM_TOOL_PATH,
            },
            "inventory": _regular_file_inventory(expected_root),
        }
    else:
        raise ValueError(f"unexpected P5 real repository: {repo.repo_key}")

    for key, value in expected.items():
        if source[key] != value:
            raise ValueError(f"acceptance source identity changed: {repo.repo_key}")


def _validate_budgets(
    budgets: Any,
    projection: dict[str, Any],
    case: QualityCase,
    config: ToolConfig,
) -> None:
    if not isinstance(budgets, dict) or tuple(budgets) != BUDGET_KEYS:
        raise ValueError("acceptance budget keys or order are invalid")
    limits = budgets["limits"]
    observed = budgets["observed"]
    if not isinstance(limits, dict) or tuple(limits) != LIMIT_KEYS:
        raise ValueError("acceptance budget limits are invalid")
    if not isinstance(observed, dict) or tuple(observed) != OBSERVED_BUDGET_KEYS:
        raise ValueError("acceptance observed budgets are invalid")
    expected_limits = {
        "final_top_k": 12,
        "pack_items": 12,
        "retrieval_calls": 3,
        "pack_bytes": 65536,
    }
    if limits != expected_limits or limits != {
        "final_top_k": config.retrieval.final_top_k,
        "pack_items": config.context.max_items,
        "retrieval_calls": case.maximum_retrieval_call_count,
        "pack_bytes": case.maximum_pack_bytes,
    }:
        raise ValueError("acceptance declared budgets changed")
    if (
        type(observed["initial_results"]) is not int
        or type(observed["final_pack_items"]) is not int
        or type(observed["retrieval_calls"]) is not int
        or type(observed["pack_bytes"]) is not int
        or observed["initial_results"] != len(projection["initial_result_paths"])
        or observed["final_pack_items"] != len(projection["final_context_pack_paths"])
        or observed["initial_results"] > limits["final_top_k"]
        or observed["final_pack_items"] > limits["pack_items"]
        or observed["retrieval_calls"] > limits["retrieval_calls"]
        or observed["pack_bytes"] > limits["pack_bytes"]
        or observed["retrieval_calls"]
        != projection["non_timing_metrics"]["retrieval_call_count"]
    ):
        raise ValueError("acceptance observed budgets are invalid")


def _validate_paths(value: Any, field: str) -> None:
    if not isinstance(value, list) or any(
        not isinstance(path, str)
        or not path
        or Path(path).is_absolute()
        or ".." in Path(path).parts
        for path in value
    ):
        raise ValueError(f"acceptance {field} is invalid")


def _validate_sha256(value: Any, field: str, *, prefixed: bool) -> None:
    prefix = "sha256:" if prefixed else ""
    if not isinstance(value, str) or not value.startswith(prefix):
        raise ValueError(f"acceptance {field} is invalid")
    digest = value[len(prefix) :]
    if len(digest) != 64 or any(
        character not in "0123456789abcdef" for character in digest
    ):
        raise ValueError(f"acceptance {field} is invalid")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    run = subparsers.add_parser("run")
    run.add_argument("--fixture", type=Path, required=True)
    run.add_argument("--profile", required=True)
    run.add_argument("--repos-dir", type=Path, required=True)
    run.add_argument("--output", type=Path, required=True)

    initialize = subparsers.add_parser("initialize")
    initialize.add_argument("--fixture", type=Path, required=True)
    initialize.add_argument("--profile", required=True)
    initialize.add_argument("--candidate-a", type=Path, required=True)
    initialize.add_argument("--candidate-b", type=Path, required=True)
    initialize.add_argument("--output", type=Path, required=True)

    verify = subparsers.add_parser("verify")
    verify.add_argument("--candidate", type=Path, required=True)
    verify.add_argument("--expected", type=Path, required=True)
    return parser


def main() -> None:
    args = _parser().parse_args()
    if args.command == "run":
        projection = run_projection(
            args.fixture,
            args.profile,
            args.repos_dir,
        )
        _publish_artifacts(
            [(args.output, canonical_json_bytes(projection).decode("utf-8"))]
        )
    elif args.command == "initialize":
        initialize_projection(
            args.fixture,
            args.profile,
            args.candidate_a,
            args.candidate_b,
            args.output,
        )
    else:
        verify_projection(args.candidate, args.expected)


if __name__ == "__main__":
    main()
