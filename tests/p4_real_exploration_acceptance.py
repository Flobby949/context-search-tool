from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any

from context_search_tool.config import DEFAULT_CONFIG
from context_search_tool.context_pack import canonical_context_pack_bytes
from context_search_tool.exploration import (
    explore_repository,
    resolve_explore_pack_options,
)
from context_search_tool.indexer import index_repository
from context_search_tool.quality.cases import (
    QualityCase,
    QualityRepo,
    load_quality_fixture,
    validate_profile_compatible,
)
from context_search_tool.quality.metrics import CaseEvaluation
from context_search_tool.quality.prepare import validate_prepared_repo
from context_search_tool.quality.runner import (
    _copy_source_repo,
    _effective_config,
    _evaluate_explored_case,
    _publish_artifacts,
)
from context_search_tool.retrieval_trace import exploration_trace_payload


EXPECTED_PROFILE = "p4_real_exploration"
EXPECTED_REPO_KEY = "spring_petclinic"
EXPECTED_CASE_ID = "owner-registration-form-validation"
EXPECTED_SOURCE_COMMIT = "51045d1648dad955df586150c1a1a6e22ef400c2"
PROJECTION_KEYS = (
    "schema_version",
    "repo_key",
    "case_id",
    "query",
    "initial_result_paths",
    "initial_context_pack_sha256",
    "final_context_pack_sha256",
    "trace",
    "non_timing_metrics",
    "failures",
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


def build_projection(
    repo_key: str,
    case: QualityCase,
    explored: Any,
    evaluation: CaseEvaluation,
) -> dict[str, Any]:
    missing = [name for name in EXPLORATION_METRICS if name not in evaluation.metrics]
    if missing:
        raise ValueError(f"exploration metric missing: {missing[0]}")
    trace = _normalize_trace_timing(
        exploration_trace_payload(explored.trace)
    )
    projection = {
        "schema_version": 1,
        "repo_key": repo_key,
        "case_id": case.case_id,
        "query": case.query,
        "initial_result_paths": [
            result.file_path.as_posix()
            for result in explored.initial_bundle.results
        ],
        "initial_context_pack_sha256": hashlib.sha256(
            canonical_context_pack_bytes(explored.initial_pack)
        ).hexdigest(),
        "final_context_pack_sha256": hashlib.sha256(
            canonical_context_pack_bytes(explored.final_pack)
        ).hexdigest(),
        "trace": trace,
        "non_timing_metrics": {
            name: evaluation.metrics[name] for name in NON_TIMING_METRICS
        },
        "failures": list(evaluation.failures),
    }
    _validate_projection_shape(projection, repo_key, case)
    canonical_json_bytes(projection)
    return projection


def _normalize_trace_timing(trace: dict[str, Any]) -> dict[str, Any]:
    normalized = deepcopy(trace)
    normalized["duration_ms"] = 0
    for round_record in normalized["rounds"]:
        round_record["duration_ms"] = 0
        for probe in round_record["probes"]:
            probe["duration_ms"] = 0
    return normalized


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


def run_projection(
    fixture_path: Path,
    profile: str,
    repos_dir: Path,
    repo_key: str,
    case_id: str,
) -> dict[str, Any]:
    fixture, repo, case = _load_selection(
        fixture_path,
        profile,
        repo_key,
        case_id,
    )
    source = validate_prepared_repo(repo, repos_dir)
    config = _effective_config(
        DEFAULT_CONFIG,
        repo.default_config,
        fixture.profile_configs[profile],
    )
    validate_profile_compatible(profile, config, canonical=fixture.canonical)
    with tempfile.TemporaryDirectory(prefix="cst-p4-real-acceptance-") as temp:
        workspace = Path(temp) / repo.repo_key
        _copy_source_repo(source, workspace)
        index_repository(workspace, config)
        explored = explore_repository(
            workspace,
            case.query,
            config,
            resolve_explore_pack_options(config, context_lines=None),
        )
        evaluation = _evaluate_explored_case(case, profile, explored)
        return build_projection(repo.repo_key, case, explored, evaluation)


def initialize_projection(
    fixture_path: Path,
    candidate_a: Path,
    candidate_b: Path,
    output: Path,
) -> None:
    if output.exists() or output.is_symlink():
        raise ValueError("acceptance baseline already exists")
    first = candidate_a.read_bytes()
    second = candidate_b.read_bytes()
    if first != second:
        raise ValueError("acceptance candidates differ")
    _fixture, _repo, case = _load_selection(
        fixture_path,
        EXPECTED_PROFILE,
        EXPECTED_REPO_KEY,
        EXPECTED_CASE_ID,
    )
    projection = _load_projection_bytes(first)
    _validate_projection_shape(projection, EXPECTED_REPO_KEY, case)
    if canonical_json_bytes(projection) != first:
        raise ValueError("acceptance candidate is not canonical JSON")
    _publish_artifacts([(output, first.decode("utf-8"))])


def verify_projection(candidate: Path, expected: Path) -> None:
    if candidate.read_bytes() != expected.read_bytes():
        raise ValueError("acceptance projection differs from expected baseline")


def _load_selection(
    fixture_path: Path,
    profile: str,
    repo_key: str,
    case_id: str,
) -> tuple[Any, QualityRepo, QualityCase]:
    fixture = load_quality_fixture(fixture_path)
    if profile not in fixture.profile_configs:
        raise ValueError(f"unknown quality profile: {profile}")
    repo = next(
        (item for item in fixture.repos if item.repo_key == repo_key),
        None,
    )
    if repo is None or profile not in repo.profiles:
        raise ValueError("acceptance repository is not selected by profile")
    if (
        profile == EXPECTED_PROFILE
        and repo.source_commit != EXPECTED_SOURCE_COMMIT
    ):
        raise ValueError("acceptance source commit is not pinned")
    case = next(
        (
            item
            for item in repo.queries
            if item.case_id == case_id
            and (not item.profiles or profile in item.profiles)
        ),
        None,
    )
    if case is None or case.mode != "exploration":
        raise ValueError("acceptance exploration case is not selected")
    return fixture, repo, case


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
    repo_key: str,
    case: QualityCase,
) -> None:
    if tuple(projection) != PROJECTION_KEYS:
        raise ValueError("acceptance projection keys or order are invalid")
    if projection["schema_version"] != 1:
        raise ValueError("acceptance projection schema_version must be 1")
    if (
        projection["repo_key"] != repo_key
        or projection["case_id"] != case.case_id
        or projection["query"] != case.query
    ):
        raise ValueError("acceptance projection identity does not match fixture")
    paths = projection["initial_result_paths"]
    if not isinstance(paths, list) or any(
        not isinstance(path, str) or not path for path in paths
    ):
        raise ValueError("acceptance initial_result_paths are invalid")
    for field in (
        "initial_context_pack_sha256",
        "final_context_pack_sha256",
    ):
        value = projection[field]
        if (
            not isinstance(value, str)
            or len(value) != 64
            or any(character not in "0123456789abcdef" for character in value)
        ):
            raise ValueError(f"acceptance {field} is invalid")
    trace = projection["trace"]
    if not isinstance(trace, dict) or (
        trace.get("schema_version"), trace.get("mode")
    ) != (2, "exploration"):
        raise ValueError("acceptance trace identity is invalid")
    metrics = projection["non_timing_metrics"]
    if not isinstance(metrics, dict) or tuple(metrics) != NON_TIMING_METRICS:
        raise ValueError("acceptance non_timing_metrics keys are invalid")
    failures = projection["failures"]
    if not isinstance(failures, list) or any(
        not isinstance(failure, str) for failure in failures
    ):
        raise ValueError("acceptance failures are invalid")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    run = subparsers.add_parser("run")
    run.add_argument("--fixture", type=Path, required=True)
    run.add_argument("--profile", required=True)
    run.add_argument("--repos-dir", type=Path, required=True)
    run.add_argument("--repo-key", required=True)
    run.add_argument("--case-id", required=True)
    run.add_argument("--output", type=Path, required=True)

    initialize = subparsers.add_parser("initialize")
    initialize.add_argument("--fixture", type=Path, required=True)
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
            args.repo_key,
            args.case_id,
        )
        _publish_artifacts(
            [(args.output, canonical_json_bytes(projection).decode("utf-8"))]
        )
    elif args.command == "initialize":
        initialize_projection(
            args.fixture,
            args.candidate_a,
            args.candidate_b,
            args.output,
        )
    else:
        verify_projection(args.candidate, args.expected)


if __name__ == "__main__":
    main()
