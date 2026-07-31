"""P14 definition-owner acceptance capture and comparison harness."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from contextlib import contextmanager, nullcontext
from copy import deepcopy
from dataclasses import replace
import hashlib
import importlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
import tomllib


ONLINE_BASE_URL = "https://api.siliconflow.cn/v1"
ONLINE_EMBEDDING_PROVIDER = "openai-compatible"
ONLINE_EMBEDDING_MODEL = "Pro/BAAI/bge-m3"
ONLINE_EMBEDDING_DIMENSIONS = 1024
ONLINE_PLANNER_PROVIDER = "openai-compatible"
ONLINE_PLANNER_MODEL = "Qwen/Qwen2.5-14B-Instruct"
ONLINE_PLANNER_TIMEOUT_SECONDS = 60.0
ONLINE_EMBEDDING_TPM_BUDGET = 240_000
ONLINE_EMBEDDING_REQUEST_TOKEN_BUDGET = 80_000
ONLINE_EMBEDDING_TPM_WINDOW_SECONDS = 60.0
ONLINE_EMBEDDING_MIN_INTERVAL_SECONDS = 2.0
P1_HYBRID_MRR_TOP3_TOLERANCE = 1.0 / 42.0
P8_CAPTURE_SLOTS = (
    "hash-baseline-r1",
    "hash-baseline-r2",
    "hash-candidate-r1",
    "hash-candidate-r2",
    "online-baseline-r1",
    "online-baseline-r2",
    "online-candidate-r1",
    "online-candidate-r2",
)
P1_CAPTURE_SLOTS = (
    "vector-baseline-r1",
    "vector-baseline-r2",
    "vector-candidate-r1",
    "vector-candidate-r2",
    "hybrid-baseline-r1",
    "hybrid-baseline-r2",
    "hybrid-candidate-r1",
    "hybrid-candidate-r2",
)
P8_ATTEMPT_IDS = frozenset(("p8-initial", "p8-final", "p8-retry-1"))
P1_ATTEMPT_IDS = frozenset(("p1-initial", "p1-final", "p1-retry-1"))
MODULES_UNDER_TEST = {
    "identifier_intent": "context_search_tool.identifier_intent",
    "ranking": "context_search_tool.retrieval_core.ranking",
    "context_expansion": "context_search_tool.retrieval_core.context_expansion",
}
P8_ENVELOPE_KEYS = {
    "schema_version",
    "capture_kind",
    "attempt_id",
    "side",
    "repeat",
    "embedding",
    "timing_reps",
    "sources",
    "implementation",
    "module_origins",
    "orchestrator_process_pid",
    "capture_process_pid",
    "report",
}
P1_ENVELOPE_KEYS = {
    "schema_version",
    "capture_kind",
    "attempt_id",
    "side",
    "repeat",
    "profile",
    "catalog",
    "implementation",
    "module_origins",
    "orchestrator_process_pid",
    "capture_process_pid",
    "report",
}
P8_REPORT_KEYS = {
    "schema_version",
    "implementation",
    "environment",
    "manifest_sha256",
    "embedding_identity",
    "repositories",
    "cases",
    "witnesses",
    "embedding_requests",
    "timing",
}
P8_SELECTED_KEYS = {
    "rank",
    "path",
    "score",
    "score_parts",
    "reasons",
    "graph_origin",
    "relation_slot",
    "relation_witness",
}
P1_REPORT_KEYS = {
    "schema_version",
    "generated_at",
    "command_args",
    "tool",
    "fixture",
    "profile",
    "config",
    "planner",
    "aggregate",
    "repos",
    "cases",
}
P1_COMMAND_ARGS_KEYS = {"fixture_path", "profile"}
P1_CONFIG_KEYS = {"config_hash", "embedding"}
P1_EMBEDDING_CONFIG_KEYS = {
    "provider",
    "model",
    "dimensions",
    "base_url",
    "api_key_env",
}
P1_PLANNER_CONFIG_KEYS = {
    "enabled",
    "provider",
    "model",
    "base_url",
    "timeout_seconds",
    "use_system_proxy",
    "max_rewritten_queries",
    "max_keywords",
    "max_symbol_hints",
}
P1_FIXTURE_KEYS = {
    "path",
    "sha256",
    "schema_version",
    "fixture_case_count",
    "run_case_count",
}
P1_AGGREGATE_KEYS = {
    "total",
    "selected",
    "attempted",
    "executed",
    "passed",
    "failed",
    "skipped",
    "errors",
    "known_gaps",
    "informational",
    "metrics",
}
P1_CASE_KEYS = {
    "repo_key",
    "case_id",
    "query",
    "gate",
    "tags",
    "attempted",
    "status",
    "known_gap_reason",
    "planner",
    "query_variants",
    "expanded_tokens",
    "variant_retrieval_status",
    "top_results",
    "metrics",
    "failures",
}
P1_CASE_PLANNER_KEYS = {
    "status",
    "provider",
    "model",
    "latency_ms",
    "rewritten_queries",
    "grep_keywords",
    "symbol_hints",
    "discarded_hints",
    "prompt_version",
    "prompt_hash",
    "repo_profile_hash",
    "repo_profile_truncated",
}
P1_QUERY_VARIANT_KEYS = {"variant_id", "text", "source"}
P1_TOP_RESULT_KEYS = {
    "rank",
    "path",
    "score",
    "score_parts",
    "reasons",
    "semantic_matches",
}
P1_SEMANTIC_MATCH_KEYS = {"variant_id", "score"}
P1_CASE_METRICS_KEYS = {
    "result_count",
    "hit_at_1",
    "hit_at_3",
    "hit_at_5",
    "hit_at_10",
    "mrr",
    "recall_at_5",
    "recall_at_10",
    "expected_coverage_top5",
    "entrypoint_rank",
    "preferred_rank_pass",
    "noise_top5",
    "noise_top10",
    "cross_language_success",
    "top_score",
    "latency_ms",
}
EXACT_IDENTIFIER_GRAMMAR = {
    "camel_pascal": (
        "(?:[A-Z]{2,}(?=[A-Z][a-z])[A-Za-z0-9]*|"
        "[A-Z]?[a-z]+(?:[A-Z][A-Za-z0-9]*)+)"
    ),
    "lower_snake": "[a-z][a-z0-9]+(?:_[a-z0-9]+)+",
    "screaming_snake": "[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+",
    "whole_trimmed_query_only": True,
}


def _add_capture_identity(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--attempt-id", required=True)
    parser.add_argument("--side", choices=("baseline", "candidate"), required=True)
    parser.add_argument("--repeat", choices=("1", "2"), required=True)
    parser.add_argument("--implementation-root", required=True)


def _add_comparison_inputs(
    parser: argparse.ArgumentParser,
    slots: tuple[str, ...],
) -> None:
    parser.add_argument("--attempt-id", required=True)
    for slot in slots:
        parser.add_argument(f"--{slot}", required=True)
    parser.add_argument("--output", required=True)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)

    capture_p8 = commands.add_parser("capture-p8")
    _add_capture_identity(capture_p8)
    capture_p8.add_argument("--sources", required=True)
    capture_p8.add_argument(
        "--embedding",
        choices=("hash", "online"),
        required=True,
    )
    capture_p8.add_argument("--timing-reps", type=int, required=True)
    capture_p8.add_argument("--output", required=True)

    capture_p1 = commands.add_parser("capture-p1")
    _add_capture_identity(capture_p1)
    capture_p1.add_argument("--catalog", required=True)
    capture_p1.add_argument(
        "--profile",
        choices=("p1_vector_bge", "p1_hybrid_bge"),
        required=True,
    )
    capture_p1.add_argument("--output", required=True)
    capture_p1.add_argument("--markdown", required=True)

    compare_p8 = commands.add_parser("compare-p8")
    _add_comparison_inputs(compare_p8, P8_CAPTURE_SLOTS)
    compare_p8.add_argument("--eligible-inventory", required=True)

    compare_p1 = commands.add_parser("compare-p1")
    _add_comparison_inputs(compare_p1, P1_CAPTURE_SLOTS)
    compare_p1.add_argument("--catalog", required=True)
    return parser


def _require_new_paths(*paths: Path) -> None:
    for path in paths:
        if path.exists():
            raise FileExistsError(f"refusing to overwrite existing path: {path}")


def _require_outputs_outside_implementation(
    implementation_root: Path,
    *paths: Path,
) -> None:
    if any(path.is_relative_to(implementation_root) for path in paths):
        raise ValueError(
            "capture outputs must be outside the implementation root"
        )


def _canonical_json(payload: object) -> str:
    return json.dumps(
        payload,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ) + "\n"


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _global_provider_config_path() -> Path:
    override = os.environ.get("CST_GLOBAL_CONFIG_PATH")
    if override:
        return Path(override).expanduser()
    config_home = os.environ.get("XDG_CONFIG_HOME")
    root = Path(config_home).expanduser() if config_home else Path.home() / ".config"
    return root / "context-search" / "config.toml"


def _online_provider_settings(
    config_path: Path | None = None,
) -> dict[str, object]:
    path = (config_path or _global_provider_config_path()).resolve()
    try:
        payload = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ValueError("online provider config is unavailable") from exc
    embedding = payload.get("embedding")
    planner = payload.get("query_planner")
    if not isinstance(embedding, dict) or not isinstance(planner, dict):
        raise ValueError("online provider config sections are unavailable")
    embedding_key = embedding.get("api_key")
    planner_key = planner.get("api_key")
    if (
        embedding.get("provider") != ONLINE_EMBEDDING_PROVIDER
        or embedding.get("model") != ONLINE_EMBEDDING_MODEL
        or embedding.get("dimensions") != ONLINE_EMBEDDING_DIMENSIONS
        or embedding.get("base_url") != ONLINE_BASE_URL
        or not isinstance(embedding_key, str)
        or not embedding_key
        or planner.get("enabled") is not True
        or planner.get("provider") != ONLINE_PLANNER_PROVIDER
        or planner.get("model") != ONLINE_PLANNER_MODEL
        or planner.get("base_url") != ONLINE_BASE_URL
        or planner.get("use_system_proxy") is not False
        or planner.get("timeout_seconds") != ONLINE_PLANNER_TIMEOUT_SECONDS
        or planner.get("max_rewritten_queries") != 4
        or planner.get("max_keywords") != 12
        or planner.get("max_symbol_hints") != 8
        or not isinstance(planner_key, str)
        or not planner_key
    ):
        raise ValueError("online provider config does not match the frozen identity")
    return {
        "path": str(path),
        "embedding": {
            "provider": ONLINE_EMBEDDING_PROVIDER,
            "model": ONLINE_EMBEDDING_MODEL,
            "dimensions": ONLINE_EMBEDDING_DIMENSIONS,
            "base_url": ONLINE_BASE_URL,
            "api_key": embedding_key,
            "api_key_env": None,
        },
        "planner": {
            "provider": ONLINE_PLANNER_PROVIDER,
            "model": ONLINE_PLANNER_MODEL,
            "base_url": ONLINE_BASE_URL,
            "api_key": planner_key,
            "use_system_proxy": False,
            "timeout_seconds": ONLINE_PLANNER_TIMEOUT_SECONDS,
            "max_rewritten_queries": 4,
            "max_keywords": 12,
            "max_symbol_hints": 8,
        },
    }


def _git(root: Path, *arguments: str) -> str:
    return subprocess.run(
        ("git", "-C", str(root), *arguments),
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _implementation_identity(root: Path) -> dict[str, object]:
    diff = _git(root, "diff", "--binary", "HEAD", "--", "src", "tests")
    listed = _git(
        root,
        "ls-files",
        "--others",
        "--exclude-standard",
        "--",
        "src",
        "tests",
    )
    untracked = {
        relative: hashlib.sha256((root / relative).read_bytes()).hexdigest()
        for relative in sorted(filter(None, listed.splitlines()))
    }
    identity = {
        "base_commit": _git(root, "rev-parse", "HEAD"),
        "tracked_diff_sha256": hashlib.sha256(diff.encode()).hexdigest(),
        "untracked_files": untracked,
        "dirty": bool(diff or untracked),
    }
    _validate_implementation_identity(identity)
    return identity


def _validate_implementation_identity(value: object) -> None:
    if not isinstance(value, dict) or set(value) != {
        "base_commit",
        "tracked_diff_sha256",
        "untracked_files",
        "dirty",
    }:
        raise ValueError("implementation identity schema is not closed")
    if (
        not isinstance(value["base_commit"], str)
        or re.fullmatch(r"[0-9a-f]{40,64}", value["base_commit"]) is None
        or not isinstance(value["tracked_diff_sha256"], str)
        or re.fullmatch(r"[0-9a-f]{64}", value["tracked_diff_sha256"]) is None
        or not isinstance(value["untracked_files"], dict)
        or not isinstance(value["dirty"], bool)
    ):
        raise ValueError("implementation identity is invalid")
    for relative, sha256 in value["untracked_files"].items():
        if (
            not isinstance(relative, str)
            or Path(relative).is_absolute()
            or ".." in Path(relative).parts
            or not isinstance(sha256, str)
            or re.fullmatch(r"[0-9a-f]{64}", sha256) is None
        ):
            raise ValueError("implementation identity is invalid")


def _module_origins(root: Path) -> dict[str, str]:
    resolved_root = root.resolve()
    origins: dict[str, str] = {}
    for label, module_name in MODULES_UNDER_TEST.items():
        module = importlib.import_module(module_name)
        origin = Path(module.__file__).resolve()
        if not origin.is_relative_to(resolved_root):
            raise ValueError(
                f"{module_name} resolved outside implementation root: {origin}"
            )
        origins[label] = str(origin)
    return origins


def _write_new(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        stream.write(payload)


@contextmanager
def _online_quality_profile(quality_runner, profile: str):
    if getattr(quality_runner, "P14_FAKE_RUNNER", False):
        yield
        return
    if not all(
        hasattr(quality_runner, name)
        for name in ("load_quality_fixture", "validate_profile_compatible")
    ):
        raise ValueError("quality runner does not support online capture overrides")
    settings = _online_provider_settings()
    original_load = quality_runner.load_quality_fixture
    original_validate = quality_runner.validate_profile_compatible
    hybrid = profile == "p1_hybrid_bge"

    def load_online_fixture(path: Path):
        fixture = original_load(path)
        profile_configs = deepcopy(fixture.profile_configs)
        if profile not in profile_configs:
            raise ValueError("P1 online profile is absent from the frozen catalog")
        profile_overrides = deepcopy(profile_configs[profile])
        profile_overrides["embedding"] = dict(settings["embedding"])
        profile_overrides["query_planner"] = {
            **dict(settings["planner"]),
            "enabled": hybrid,
        }
        profile_configs[profile] = profile_overrides
        return replace(fixture, profile_configs=profile_configs)

    def validate_online_profile(
        selected_profile: str,
        config,
        *,
        canonical: bool = False,
    ) -> None:
        if selected_profile != profile:
            original_validate(
                selected_profile,
                config,
                canonical=canonical,
            )
            return
        embedding = config.embedding
        planner = config.query_planner
        if (
            canonical is not True
            or embedding.provider != ONLINE_EMBEDDING_PROVIDER
            or embedding.model != ONLINE_EMBEDDING_MODEL
            or embedding.dimensions != ONLINE_EMBEDDING_DIMENSIONS
            or embedding.base_url != ONLINE_BASE_URL
            or embedding.api_key != settings["embedding"]["api_key"]
            or planner.enabled is not hybrid
            or planner.provider != ONLINE_PLANNER_PROVIDER
            or planner.model != ONLINE_PLANNER_MODEL
            or planner.base_url != ONLINE_BASE_URL
            or planner.api_key != settings["planner"]["api_key"]
            or planner.use_system_proxy is not False
            or planner.timeout_seconds != ONLINE_PLANNER_TIMEOUT_SECONDS
        ):
            raise ValueError("effective P1 online provider identity is invalid")

    quality_runner.load_quality_fixture = load_online_fixture
    quality_runner.validate_profile_compatible = validate_online_profile
    try:
        yield
    finally:
        quality_runner.load_quality_fixture = original_load
        quality_runner.validate_profile_compatible = original_validate


def _capture_p1_child(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--implementation-root", required=True)
    parser.add_argument("--catalog", required=True)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--result", required=True)
    parser.add_argument("--raw-json", required=True)
    parser.add_argument("--raw-markdown", required=True)
    arguments = parser.parse_args(argv)

    root = Path(arguments.implementation_root).resolve()
    origins = _module_origins(root)
    quality_runner = importlib.import_module("context_search_tool.quality.runner")
    quality_origin = Path(quality_runner.__file__).resolve()
    if not quality_origin.is_relative_to(root):
        raise ValueError(
            f"quality runner resolved outside implementation root: {quality_origin}"
        )
    raw_json = Path(arguments.raw_json)
    raw_markdown = Path(arguments.raw_markdown)
    pacing = (
        nullcontext()
        if getattr(quality_runner, "P14_FAKE_RUNNER", False)
        else _pace_online_embedding_requests()
    )
    with pacing:
        with _online_quality_profile(quality_runner, arguments.profile):
            report = quality_runner.run_quality_fixture(
                Path(arguments.catalog),
                profile=arguments.profile,
                output_path=raw_json,
                markdown_path=raw_markdown,
                allow_empty=False,
                repos_dir=root / ".quality/repos",
            )
    if json.loads(raw_json.read_text(encoding="utf-8")) != report:
        raise ValueError("quality runner return value differs from its JSON output")
    if (
        not isinstance(report, dict)
        or report.get("schema_version") != 2
        or report.get("profile") != arguments.profile
        or not isinstance(report.get("aggregate"), dict)
        or not isinstance(report.get("cases"), list)
    ):
        raise ValueError("quality runner returned an invalid report")
    result = {
        "capture_process_pid": os.getpid(),
        "implementation": _implementation_identity(root),
        "module_origins": origins,
        "report": report,
        "markdown": raw_markdown.read_text(encoding="utf-8"),
    }
    _write_new(Path(arguments.result), _canonical_json(result))
    return 0


def _capture_p1(arguments: argparse.Namespace) -> None:
    if arguments.attempt_id not in P1_ATTEMPT_IDS:
        raise ValueError(f"invalid P1 attempt ID: {arguments.attempt_id}")
    root = Path(arguments.implementation_root).resolve()
    catalog = Path(arguments.catalog).resolve()
    if not root.is_dir() or not catalog.is_file():
        raise ValueError("implementation root and catalog must exist")
    if not catalog.is_relative_to(root):
        raise ValueError("P1 catalog must be beneath the implementation root")
    output = Path(arguments.output).resolve()
    markdown = Path(arguments.markdown).resolve()
    if output == markdown:
        raise ValueError("P1 JSON and Markdown outputs must be different paths")
    _require_outputs_outside_implementation(root, output, markdown)
    _require_new_paths(output, markdown)
    identity_before = _implementation_identity(root)

    with tempfile.TemporaryDirectory(prefix="cst-p14-p1-") as temporary:
        scratch = Path(temporary)
        child_result = scratch / "child.json"
        raw_json = scratch / "report.json"
        raw_markdown = scratch / "report.md"
        environment = os.environ.copy()
        environment["PYTHONPATH"] = os.pathsep.join(
            (str(root / "src"), str(root / "tests"))
        )
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        completed = subprocess.run(
            (
                sys.executable,
                "-P",
                str(Path(__file__).resolve()),
                "_capture-p1-child",
                "--implementation-root",
                str(root),
                "--catalog",
                str(catalog),
                "--profile",
                arguments.profile,
                "--result",
                str(child_result),
                "--raw-json",
                str(raw_json),
                "--raw-markdown",
                str(raw_markdown),
            ),
            cwd=root,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                "P1 capture child failed:\n"
                + completed.stdout
                + completed.stderr
            )
        child = json.loads(child_result.read_text(encoding="utf-8"))

    identity_after = _implementation_identity(root)
    if child["implementation"] != identity_before or identity_after != identity_before:
        raise ValueError("implementation identity changed during P1 capture")
    envelope = {
        "schema_version": 1,
        "capture_kind": "p1",
        "attempt_id": arguments.attempt_id,
        "side": arguments.side,
        "repeat": int(arguments.repeat),
        "profile": arguments.profile,
        "catalog": {
            "filename": catalog.name,
            "sha256": _sha256(catalog),
        },
        "implementation": identity_before,
        "module_origins": child["module_origins"],
        "orchestrator_process_pid": os.getpid(),
        "capture_process_pid": child["capture_process_pid"],
        "report": child["report"],
    }
    _write_new(markdown, child["markdown"])
    _write_new(output, _canonical_json(envelope))


def _result_projection(result: object, rank: int) -> dict[str, object]:
    score = getattr(result, "score", None)
    score_parts = getattr(result, "score_parts", None)
    reasons = getattr(result, "reasons", None)
    if (
        isinstance(score, bool)
        or not isinstance(score, (int, float))
        or not math.isfinite(float(score))
        or not isinstance(score_parts, dict)
        or not all(
            isinstance(key, str)
            and not isinstance(value, bool)
            and isinstance(value, (int, float))
            and math.isfinite(float(value))
            for key, value in score_parts.items()
        )
        or not isinstance(reasons, (list, tuple))
        or not all(isinstance(reason, str) for reason in reasons)
    ):
        raise ValueError("P8 result has an invalid observable projection")
    return {
        "rank": rank,
        "path": str(getattr(result, "file_path")),
        "score": float(score),
        "score_parts": {
            key: float(score_parts[key]) for key in sorted(score_parts)
        },
        "reasons": list(reasons),
    }


@contextmanager
def _pace_online_embedding_requests(*, wait_for_budget=None):
    embeddings = importlib.import_module("context_search_tool.embeddings")
    provider_type = embeddings.OpenAICompatibleEmbeddingProvider
    original = provider_type.embed_texts
    token_history: list[tuple[float, int]] = []
    wait = wait_for_budget or _wait_for_online_embedding_budget

    def paced(self, texts, *args, **kwargs):
        vectors = []
        for batch in _online_embedding_batches(texts, singleton=True):
            wait(token_history, _online_embedding_token_estimate(batch))
            vectors.extend(original(self, batch, *args, **kwargs))
        return vectors

    provider_type.embed_texts = paced
    try:
        yield
    finally:
        provider_type.embed_texts = original


@contextmanager
def _count_online_embedding_requests(
    *,
    current_repository: dict[str, str | None],
    counts: dict[str, int],
):
    embeddings = importlib.import_module("context_search_tool.embeddings")
    provider_type = embeddings.OpenAICompatibleEmbeddingProvider
    original = provider_type.embed_texts
    token_history: list[tuple[float, int]] = []

    def counted(self, texts, *args, **kwargs):
        repository = current_repository["value"]
        if repository not in ("redink", "daily"):
            raise ValueError("online embedding request has no repository attribution")
        vectors = []
        for batch in _online_embedding_batches(texts):
            _wait_for_online_embedding_budget(
                token_history,
                _online_embedding_token_estimate(batch),
            )
            counts[repository] += 1
            counts["total"] += 1
            vectors.extend(original(self, batch, *args, **kwargs))
        return vectors

    provider_type.embed_texts = counted
    try:
        yield
    finally:
        provider_type.embed_texts = original


def _online_embedding_token_estimate(texts: Sequence[str]) -> int:
    if not texts or any(not isinstance(text, str) or not text for text in texts):
        raise ValueError("online embedding batch is invalid")
    return sum(
        max(1, math.ceil(len(text.encode("utf-8")) / 3))
        for text in texts
    )


def _online_embedding_batches(
    texts: Sequence[str],
    *,
    singleton: bool = False,
) -> list[list[str]]:
    if not texts:
        raise ValueError("online embedding batch is invalid")
    batches: list[list[str]] = []
    batch: list[str] = []
    batch_tokens = 0
    for text in texts:
        token_count = _online_embedding_token_estimate((text,))
        if token_count > ONLINE_EMBEDDING_REQUEST_TOKEN_BUDGET:
            raise ValueError("online embedding single input exceeds request budget")
        if singleton:
            batches.append([text])
            continue
        if batch and (
            batch_tokens + token_count
            > ONLINE_EMBEDDING_REQUEST_TOKEN_BUDGET
        ):
            batches.append(batch)
            batch = []
            batch_tokens = 0
        batch.append(text)
        batch_tokens += token_count
    if batch:
        batches.append(batch)
    return batches


def _wait_for_online_embedding_budget(
    history: list[tuple[float, int]],
    token_count: int,
    *,
    monotonic=time.monotonic,
    sleep=time.sleep,
) -> None:
    if (
        token_count <= 0
        or token_count > ONLINE_EMBEDDING_REQUEST_TOKEN_BUDGET
    ):
        raise ValueError("online embedding batch exceeds the frozen TPM budget")
    while True:
        now = monotonic()
        cutoff = now - ONLINE_EMBEDDING_TPM_WINDOW_SECONDS
        history[:] = [
            (timestamp, tokens)
            for timestamp, tokens in history
            if timestamp > cutoff
        ]
        within_token_budget = (
            sum(tokens for _timestamp, tokens in history) + token_count
            <= ONLINE_EMBEDDING_TPM_BUDGET
        )
        interval_delay = (
            history[-1][0] + ONLINE_EMBEDDING_MIN_INTERVAL_SECONDS - now
            if history
            else 0.0
        )
        if within_token_budget and interval_delay <= 0.0:
            history.append((now, token_count))
            return
        token_delay = (
            history[0][0] + ONLINE_EMBEDDING_TPM_WINDOW_SECONDS - now
            if not within_token_budget
            else 0.0
        )
        sleep(max(token_delay, interval_delay, 0.001))


def _capture_online_p8(
    p8_runner,
    root: Path,
    sources: Path,
    raw_json: Path,
    timing_reps: int,
    provider_config: Path,
) -> dict[str, object]:
    settings = _online_provider_settings(provider_config)
    config_module = importlib.import_module("context_search_tool.config")
    embedding = config_module.replace_embedding_config(
        config_module.EmbeddingConfig(
            provider=ONLINE_EMBEDDING_PROVIDER,
            model=ONLINE_EMBEDDING_MODEL,
            dimensions=ONLINE_EMBEDDING_DIMENSIONS,
            base_url=ONLINE_BASE_URL,
        ),
        api_key=settings["embedding"]["api_key"],
    )
    online_config = replace(config_module.DEFAULT_CONFIG, embedding=embedding)
    original_config = p8_runner._embedding_config
    original_counter = p8_runner._count_embedding_requests

    def online_config_for_capture(_embedding: str):
        return online_config

    @contextmanager
    def online_counter(
        *,
        enabled: bool,
        current_repository: dict[str, str | None],
        counts: dict[str, int],
    ):
        del enabled
        with _count_online_embedding_requests(
            current_repository=current_repository,
            counts=counts,
        ):
            yield

    p8_runner._embedding_config = online_config_for_capture
    p8_runner._count_embedding_requests = online_counter
    try:
        report = p8_runner.capture(
            root,
            sources,
            raw_json,
            timing_reps=timing_reps,
            embedding="hash",
        )
    finally:
        p8_runner._embedding_config = original_config
        p8_runner._count_embedding_requests = original_counter

    request_counts = dict(report["embedding_requests"])
    report["embedding_requests"] = {"redink": 0, "daily": 0, "total": 0}
    raw_json.write_text(p8_runner._canonical(report), encoding="utf-8")
    p8_runner.check(raw_json)
    report["embedding_requests"] = request_counts
    attestation = {
        "provider": ONLINE_EMBEDDING_PROVIDER,
        "configured_model": ONLINE_EMBEDDING_MODEL,
        "dimensions": ONLINE_EMBEDDING_DIMENSIONS,
        "base_url": ONLINE_BASE_URL,
    }
    identity = report["embedding_identity"]
    identity.update(
        {
            "provider": ONLINE_EMBEDDING_PROVIDER,
            "base_url": ONLINE_BASE_URL,
            "canonical_model": ONLINE_EMBEDDING_MODEL,
            "model_digest": None,
            "ollama_version": None,
            "input_transform_id": None,
            "pre_attestation": attestation,
            "post_attestation": attestation,
        }
    )
    raw_json.write_text(_canonical_json(report), encoding="utf-8")
    return report


def _capture_p8_child(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--implementation-root", required=True)
    parser.add_argument("--sources", required=True)
    parser.add_argument("--embedding", required=True)
    parser.add_argument("--timing-reps", required=True, type=int)
    parser.add_argument("--provider-config", required=True)
    parser.add_argument("--result", required=True)
    parser.add_argument("--raw-json", required=True)
    arguments = parser.parse_args(argv)

    root = Path(arguments.implementation_root).resolve()
    origins = _module_origins(root)
    retrieval = importlib.import_module("context_search_tool.retrieval")
    original_query = retrieval.query_repository
    observations: list[dict[str, object]] = []

    def observed_query(*query_args, **query_kwargs):
        bundle = original_query(*query_args, **query_kwargs)
        query_text = (
            query_args[1]
            if len(query_args) > 1
            else query_kwargs.get("query")
        )
        if not isinstance(query_text, str):
            raise ValueError("P8 query observation has no query text")
        observations.append(
            {
                "query": query_text,
                "selected": [
                    _result_projection(result, rank)
                    for rank, result in enumerate(bundle.results, start=1)
                ],
            }
        )
        return bundle

    retrieval.query_repository = observed_query
    try:
        p8_runner = importlib.import_module("p8_real_python_graphs_acceptance")
        runner_origin = Path(p8_runner.__file__).resolve()
        if not runner_origin.is_relative_to(root):
            raise ValueError(
                f"P8 runner resolved outside implementation root: {runner_origin}"
            )
        manifest = p8_runner._manifest_or_fail()
        raw_json = Path(arguments.raw_json)
        if (
            arguments.embedding == "online"
            and not getattr(p8_runner, "P14_FAKE_RUNNER", False)
        ):
            report = _capture_online_p8(
                p8_runner,
                root,
                Path(arguments.sources),
                raw_json,
                arguments.timing_reps,
                Path(arguments.provider_config),
            )
        else:
            report = p8_runner.capture(
                root,
                Path(arguments.sources),
                raw_json,
                timing_reps=arguments.timing_reps,
                embedding=arguments.embedding,
            )
            p8_runner.check(raw_json)
            report["embedding_identity"]["base_url"] = None
            raw_json.write_text(_canonical_json(report), encoding="utf-8")
    finally:
        retrieval.query_repository = original_query

    if json.loads(raw_json.read_text(encoding="utf-8")) != report:
        raise ValueError("P8 runner return value differs from its JSON output")
    identity = _implementation_identity(root)
    if (
        not isinstance(report, dict)
        or report.get("schema_version") != 4
        or report.get("implementation") != identity
        or not isinstance(report.get("cases"), dict)
        or not isinstance(manifest, dict)
        or not isinstance(manifest.get("cases"), list)
    ):
        raise ValueError("legacy P8 runner returned an invalid capture")
    source_specs = getattr(p8_runner, "SOURCES", None)
    if not isinstance(source_specs, dict) or set(source_specs) != {
        "redink",
        "daily",
    }:
        raise ValueError("legacy P8 runner source identity is invalid")
    source_identity = {
        "root_dirname": Path(arguments.sources).resolve().name,
        "repositories": {},
    }
    for repository, spec in sorted(source_specs.items()):
        if (
            not isinstance(spec, dict)
            or not isinstance(spec.get("dir_name"), str)
            or isinstance(spec.get("expected_count"), bool)
            or not isinstance(spec.get("expected_count"), int)
            or spec["expected_count"] <= 0
            or re.fullmatch(r"[0-9a-f]{64}", spec.get("inventory_sha256", ""))
            is None
            or re.fullmatch(r"[0-9a-f]{64}", spec.get("content_sha256", ""))
            is None
        ):
            raise ValueError("legacy P8 runner source identity is invalid")
        source_identity["repositories"][repository] = {
            "dir_name": spec["dir_name"],
            "selected_files": spec["expected_count"],
            "inventory_sha256": spec["inventory_sha256"],
            "content_sha256": spec["content_sha256"],
        }
    cursor = 0
    for case_spec in manifest["cases"]:
        repetitions = max(1, arguments.timing_reps)
        observed_case = observations[cursor : cursor + repetitions]
        cursor += repetitions
        if cursor > len(observations):
            raise ValueError("P8 runner did not execute every manifest case")
        if any(
            observation["query"] != case_spec["query"]
            for observation in observed_case
        ):
            raise ValueError("P8 runner query order differs from its manifest")
        projection = observed_case[-1]["selected"]
        selected = report["cases"][case_spec["id"]]["selected"]
        if [row["path"] for row in selected] != [
            row["path"] for row in projection
        ]:
            raise ValueError("legacy and P14 P8 selected paths differ")
        for legacy, extended in zip(selected, projection, strict=True):
            if legacy["rank"] != extended["rank"]:
                raise ValueError("legacy and P14 P8 selected ranks differ")
            legacy.update(
                {
                    "score": extended["score"],
                    "score_parts": extended["score_parts"],
                    "reasons": extended["reasons"],
                }
            )
    result = {
        "capture_process_pid": os.getpid(),
        "implementation": identity,
        "module_origins": origins,
        "sources": source_identity,
        "report": report,
    }
    _write_new(Path(arguments.result), _canonical_json(result))
    return 0


def _capture_p8(arguments: argparse.Namespace) -> None:
    if arguments.attempt_id not in P8_ATTEMPT_IDS:
        raise ValueError(f"invalid P8 attempt ID: {arguments.attempt_id}")
    if arguments.timing_reps < 1:
        raise ValueError("P8 timing reps must be positive")
    root = Path(arguments.implementation_root).resolve()
    sources = Path(arguments.sources).resolve()
    if not root.is_dir() or not sources.is_dir():
        raise ValueError("implementation root and P8 sources must exist")
    output = Path(arguments.output).resolve()
    _require_outputs_outside_implementation(root, output)
    _require_new_paths(output)
    identity_before = _implementation_identity(root)
    provider_config = _global_provider_config_path().resolve()

    with tempfile.TemporaryDirectory(prefix="cst-p14-p8-") as temporary:
        scratch = Path(temporary)
        child_result = scratch / "child.json"
        raw_json = scratch / "legacy.json"
        environment = os.environ.copy()
        environment["PYTHONPATH"] = os.pathsep.join(
            (str(root / "src"), str(root / "tests"))
        )
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        environment["CST_GLOBAL_CONFIG_PATH"] = str(
            scratch / "isolated-global-config.toml"
        )
        completed = subprocess.run(
            (
                sys.executable,
                "-P",
                str(Path(__file__).resolve()),
                "_capture-p8-child",
                "--implementation-root",
                str(root),
                "--sources",
                str(sources),
                "--embedding",
                arguments.embedding,
                "--timing-reps",
                str(arguments.timing_reps),
                "--provider-config",
                str(provider_config),
                "--result",
                str(child_result),
                "--raw-json",
                str(raw_json),
            ),
            cwd=root,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                "P8 capture child failed:\n"
                + completed.stdout
                + completed.stderr
            )
        child = json.loads(child_result.read_text(encoding="utf-8"))

    identity_after = _implementation_identity(root)
    if child["implementation"] != identity_before or identity_after != identity_before:
        raise ValueError("implementation identity changed during P8 capture")
    embedding_identity = child["report"].get("embedding_identity")
    expected_provider = (
        ONLINE_EMBEDDING_PROVIDER
        if arguments.embedding == "online"
        else arguments.embedding
    )
    if (
        not isinstance(embedding_identity, dict)
        or embedding_identity.get("provider") != expected_provider
    ):
        raise ValueError("P8 output embedding identity does not match request")
    envelope = {
        "schema_version": 1,
        "capture_kind": "p8",
        "attempt_id": arguments.attempt_id,
        "side": arguments.side,
        "repeat": int(arguments.repeat),
        "embedding": arguments.embedding,
        "timing_reps": arguments.timing_reps,
        "sources": child["sources"],
        "implementation": identity_before,
        "module_origins": child["module_origins"],
        "orchestrator_process_pid": os.getpid(),
        "capture_process_pid": child["capture_process_pid"],
        "report": child["report"],
    }
    _write_new(output, _canonical_json(envelope))


def _comparison_paths(
    arguments: argparse.Namespace,
    slots: tuple[str, ...],
) -> dict[str, Path]:
    inputs = {
        slot: Path(getattr(arguments, slot.replace("-", "_"))).resolve()
        for slot in slots
    }
    if len(set(inputs.values())) != len(inputs):
        raise ValueError("every named capture input must be unique")
    output = Path(arguments.output).resolve()
    if output in inputs.values():
        raise ValueError("comparison output must not alias an input")
    _require_new_paths(output)
    return inputs


def _load_comparison_captures(
    *,
    inputs: dict[str, Path],
    attempt_id: str,
    kind: str,
) -> dict[str, dict[str, object]]:
    expected_attempts = P8_ATTEMPT_IDS if kind == "p8" else P1_ATTEMPT_IDS
    if attempt_id not in expected_attempts:
        raise ValueError(f"invalid {kind.upper()} attempt ID: {attempt_id}")
    expected_keys = P8_ENVELOPE_KEYS if kind == "p8" else P1_ENVELOPE_KEYS
    captures: dict[str, dict[str, object]] = {}
    side_identities: dict[str, object] = {}
    side_origins: dict[str, object] = {}
    for slot, path in inputs.items():
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or set(payload) != expected_keys:
            raise ValueError(f"{slot} capture envelope schema is not closed")
        first, expected_side, repetition = slot.split("-")
        expected_repeat = int(repetition[-1])
        expected_variant = (
            first
            if kind == "p8"
            else f"p1_{first}_bge"
        )
        variant_field = "embedding" if kind == "p8" else "profile"
        if (
            payload["schema_version"] != 1
            or payload["capture_kind"] != kind
            or payload["attempt_id"] != attempt_id
            or payload["side"] != expected_side
            or payload["repeat"] != expected_repeat
            or payload[variant_field] != expected_variant
        ):
            raise ValueError(f"{slot} capture metadata does not match its slot")
        _validate_implementation_identity(payload["implementation"])
        origins = payload["module_origins"]
        if (
            not isinstance(origins, dict)
            or set(origins) != set(MODULES_UNDER_TEST)
            or not all(
                isinstance(origin, str) and Path(origin).is_absolute()
                for origin in origins.values()
            )
        ):
            raise ValueError(f"{slot} module origins are invalid")
        for field in ("orchestrator_process_pid", "capture_process_pid"):
            value = payload[field]
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{slot} process identity is invalid")
        if not isinstance(payload["report"], dict):
            raise ValueError(f"{slot} report is invalid")
        if kind == "p8":
            sources = payload["sources"]
            if (
                not isinstance(sources, dict)
                or set(sources) != {"root_dirname", "repositories"}
                or not isinstance(sources["root_dirname"], str)
                or not sources["root_dirname"]
                or not isinstance(sources["repositories"], dict)
                or set(sources["repositories"]) != {"redink", "daily"}
            ):
                raise ValueError(f"{slot} P8 source identity is invalid")
            for source in sources["repositories"].values():
                if (
                    not isinstance(source, dict)
                    or set(source)
                    != {
                        "dir_name",
                        "selected_files",
                        "inventory_sha256",
                        "content_sha256",
                    }
                    or not isinstance(source["dir_name"], str)
                    or isinstance(source["selected_files"], bool)
                    or not isinstance(source["selected_files"], int)
                    or source["selected_files"] <= 0
                    or re.fullmatch(
                        r"[0-9a-f]{64}",
                        source["inventory_sha256"],
                    )
                    is None
                    or re.fullmatch(
                        r"[0-9a-f]{64}",
                        source["content_sha256"],
                    )
                    is None
                ):
                    raise ValueError(f"{slot} P8 source identity is invalid")
        prior_identity = side_identities.setdefault(
            expected_side,
            payload["implementation"],
        )
        if prior_identity != payload["implementation"]:
            raise ValueError(
                f"{expected_side} implementation identity changed across captures"
            )
        prior_origins = side_origins.setdefault(expected_side, origins)
        if prior_origins != origins:
            raise ValueError(
                f"{expected_side} module origins changed across captures"
            )
        captures[slot] = payload
    if side_identities.get("baseline") == side_identities.get("candidate"):
        raise ValueError(
            "baseline and candidate implementation identities must intentionally differ"
        )
    if side_origins.get("baseline") == side_origins.get("candidate"):
        raise ValueError(
            "baseline and candidate module origins must intentionally differ"
        )
    if kind == "p8":
        timing_reps = {capture["timing_reps"] for capture in captures.values()}
        if (
            len(timing_reps) != 1
            or any(
                isinstance(value, bool)
                or not isinstance(value, int)
                or value <= 0
                for value in timing_reps
            )
        ):
            raise ValueError("P8 captures mix timing reps")
        source_identities = {
            _canonical_json(capture["sources"])
            for capture in captures.values()
        }
        if len(source_identities) != 1:
            raise ValueError("P8 captures mix source identities")
    return captures


def _validate_p1_catalog(
    captures: dict[str, dict[str, object]],
    catalog: Path,
) -> None:
    if not catalog.is_file():
        raise ValueError("P1 catalog does not exist")
    expected = {
        "filename": catalog.name,
        "sha256": _sha256(catalog),
    }
    if any(capture["catalog"] != expected for capture in captures.values()):
        raise ValueError("P1 capture catalog identity mismatch")


def _load_eligible_inventory(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or set(payload) != {
        "schema_version",
        "behavior_baseline",
        "counts",
        "eligible_keys",
        "exact_queries",
        "grammar",
        "p8_eligible_case_ids",
        "sources",
    }:
        raise ValueError("eligible inventory schema is not closed")
    case_ids = payload["p8_eligible_case_ids"]
    if (
        payload["schema_version"] != 1
        or not isinstance(payload["behavior_baseline"], str)
        or re.fullmatch(r"[0-9a-f]{40,64}", payload["behavior_baseline"]) is None
        or not isinstance(payload["counts"], dict)
        or not isinstance(payload["eligible_keys"], list)
        or not isinstance(payload["exact_queries"], list)
        or not isinstance(payload["grammar"], dict)
        or not isinstance(case_ids, list)
        or not all(isinstance(case_id, str) and case_id for case_id in case_ids)
        or len(case_ids) != len(set(case_ids))
        or not isinstance(payload["sources"], list)
    ):
        raise ValueError("eligible inventory is invalid")
    return payload


def _identifier_family(query: str) -> str | None:
    if query != query.strip():
        return None
    for family in ("screaming_snake", "lower_snake", "camel_pascal"):
        if re.fullmatch(EXACT_IDENTIFIER_GRAMMAR[family], query):
            return family
    return None


def _validate_and_derive_p8_eligibility(
    inventory: dict[str, object],
    captures: dict[str, dict[str, object]],
) -> set[str]:
    baseline_commit = captures["hash-baseline-r1"]["implementation"][
        "base_commit"
    ]
    if inventory["behavior_baseline"] != baseline_commit:
        raise ValueError("eligible inventory behavior baseline mismatch")
    if inventory["grammar"] != EXACT_IDENTIFIER_GRAMMAR:
        raise ValueError("eligible inventory grammar mismatch")

    repository_root = Path(__file__).resolve().parents[1]
    source_by_path = {}
    for source in inventory["sources"]:
        if (
            not isinstance(source, dict)
            or set(source) != {"kind", "path", "query_count", "sha256"}
            or not isinstance(source["kind"], str)
            or not isinstance(source["path"], str)
            or Path(source["path"]).is_absolute()
            or ".." in Path(source["path"]).parts
            or isinstance(source["query_count"], bool)
            or not isinstance(source["query_count"], int)
            or source["query_count"] < 0
            or not isinstance(source["sha256"], str)
            or re.fullmatch(r"[0-9a-f]{64}", source["sha256"]) is None
        ):
            raise ValueError("eligible inventory source schema is invalid")
        source_path = (repository_root / source["path"]).resolve()
        if (
            not source_path.is_relative_to(repository_root)
            or not source_path.is_file()
            or hashlib.sha256(source_path.read_bytes()).hexdigest()
            != source["sha256"]
            or source["path"] in source_by_path
        ):
            raise ValueError("eligible inventory source hash mismatch")
        source_by_path[source["path"]] = (source, source_path)

    p8_sources = [
        value for value in source_by_path.values() if value[0]["kind"] == "p8_manifest"
    ]
    if len(p8_sources) != 1:
        raise ValueError("eligible inventory must identify one P8 manifest")
    p8_source, p8_path = p8_sources[0]
    manifest = json.loads(p8_path.read_text(encoding="utf-8"))
    if (
        not isinstance(manifest, dict)
        or not isinstance(manifest.get("cases"), list)
        or p8_source["query_count"] != len(manifest["cases"])
        or inventory["counts"].get("p8_manifest_queries")
        != len(manifest["cases"])
    ):
        raise ValueError("eligible inventory P8 source count mismatch")
    manifest_cases = {
        case["id"]: case
        for case in manifest["cases"]
        if isinstance(case, dict)
        and isinstance(case.get("id"), str)
        and isinstance(case.get("query"), str)
        and case.get("repo") in {"redink", "daily"}
    }
    if len(manifest_cases) != len(manifest["cases"]):
        raise ValueError("eligible inventory P8 manifest is invalid")
    if set(captures["hash-baseline-r1"]["report"]["cases"]) != set(
        manifest_cases
    ):
        raise ValueError("eligible inventory P8 cases differ from captures")
    if any(
        capture["report"]["manifest_sha256"] != manifest.get("manifest_sha256")
        for capture in captures.values()
    ):
        raise ValueError("eligible inventory P8 manifest identity mismatch")
    for case_id, case_spec in manifest_cases.items():
        required_spec = case_spec.get("required")
        contextual_spec = case_spec.get("contextual")
        if (
            not isinstance(required_spec, list)
            or not required_spec
            or not isinstance(contextual_spec, list)
            or not all(
                isinstance(required, dict)
                and set(required) == {"path", "role"}
                and isinstance(required["path"], str)
                and required["path"]
                and not Path(required["path"]).is_absolute()
                and ".." not in Path(required["path"]).parts
                and isinstance(required["role"], str)
                and required["role"]
                for required in required_spec
            )
            or len(
                {
                    (required["path"], required["role"])
                    for required in required_spec
                }
            )
            != len(required_spec)
            or not all(
                isinstance(path, str)
                and path
                and not Path(path).is_absolute()
                and ".." not in Path(path).parts
                for path in contextual_spec
            )
            or len(set(contextual_spec)) != len(contextual_spec)
        ):
            raise ValueError("eligible inventory P8 manifest case is invalid")
        expected_required = [
            (required["path"], required["role"])
            for required in required_spec
        ]
        for slot, capture in captures.items():
            captured_case = capture["report"]["cases"][case_id]
            captured_required = captured_case.get("required")
            captured_contextual = captured_case.get("contextual")
            if (
                captured_case.get("repo") != case_spec["repo"]
                or not isinstance(captured_required, list)
                or not all(
                    isinstance(required, dict)
                    and isinstance(required.get("path"), str)
                    and isinstance(required.get("role"), str)
                    for required in captured_required
                )
                or [
                    (required["path"], required["role"])
                    for required in captured_required
                ]
                != expected_required
                or captured_contextual != contextual_spec
            ):
                raise ValueError(
                    f"{slot} P8 denominator/contextual differs from manifest"
                )

    exact_records = inventory["exact_queries"]
    if not all(isinstance(record, dict) for record in exact_records):
        raise ValueError("eligible inventory exact query records are invalid")
    expected_eligible_keys = {
        (
            record.get("source_kind"),
            record.get("repo_key"),
            record.get("case_id"),
            record.get("source_path"),
        )
        for record in exact_records
        if record.get("eligible") is True
    }
    actual_eligible_keys = {
        (
            key.get("source_kind"),
            key.get("repo_key"),
            key.get("case_id"),
            key.get("source_path"),
        )
        for key in inventory["eligible_keys"]
        if isinstance(key, dict)
        and set(key)
        == {"source_kind", "repo_key", "case_id", "source_path"}
    }
    if (
        len(actual_eligible_keys) != len(inventory["eligible_keys"])
        or actual_eligible_keys != expected_eligible_keys
    ):
        raise ValueError("eligible inventory eligible keys mismatch")

    p8_records: dict[str, list[dict[str, object]]] = {}
    p8_source_path = p8_source["path"]
    for record in exact_records:
        source_path = record.get("source_path")
        if source_path not in source_by_path:
            raise ValueError("eligible inventory exact query source is unverified")
        if record.get("source_kind") == "p8_manifest":
            p8_records.setdefault(record.get("case_id"), []).append(record)

    derived = set()
    baseline_reports = [
        captures[f"{provider}-baseline-r{repeat}"]["report"]
        for provider in ("hash", "online")
        for repeat in (1, 2)
    ]
    for case_id, case in manifest_cases.items():
        family = _identifier_family(case["query"])
        records = p8_records.get(case_id, [])
        if family is None:
            if records:
                raise ValueError("eligible inventory marks a non-exact P8 query")
            continue
        if len(records) != 1:
            raise ValueError("eligible inventory exact P8 fact is missing")
        record = records[0]
        if (
            record.get("query") != case["query"]
            or record.get("repo_key") != case["repo"]
            or record.get("source_path") != p8_source_path
            or record.get("identifier_family") != family
            or not isinstance(record.get("applicable_owner_witness"), bool)
            or not isinstance(record.get("owner_witnesses"), list)
        ):
            raise ValueError("eligible inventory exact P8 fact mismatch")
        eligible = family == "screaming_snake" or (
            record["applicable_owner_witness"]
            and bool(record["owner_witnesses"])
        )
        if record.get("eligible") is not eligible:
            raise ValueError("eligible inventory P8 eligibility mismatch")
        if eligible and family != "screaming_snake":
            for witness in record["owner_witnesses"]:
                if (
                    not isinstance(witness, dict)
                    or not isinstance(witness.get("file_path"), str)
                    or isinstance(witness.get("selected_rank"), bool)
                    or not isinstance(witness.get("selected_rank"), int)
                    or not all(
                        0
                        < witness["selected_rank"]
                        <= len(report["cases"][case_id]["selected"])
                        and report["cases"][case_id]["selected"][
                            witness["selected_rank"] - 1
                        ]["path"]
                        == witness["file_path"]
                        for report in baseline_reports
                    )
                ):
                    raise ValueError("eligible inventory owner witness mismatch")
        if eligible:
            derived.add(case_id)
    if set(inventory["p8_eligible_case_ids"]) != derived:
        raise ValueError("eligible inventory P8 allowlist is not baseline-derived")
    return derived


def _finite_number(value: object, label: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
    ):
        raise ValueError(f"{label} must be a finite number")
    return float(value)


def _validate_p8_report(
    envelope: dict[str, object],
    slot: str,
) -> dict[str, object]:
    report = envelope["report"]
    if not isinstance(report, dict) or set(report) != P8_REPORT_KEYS:
        raise ValueError(f"{slot} P8 report schema is not closed")
    if (
        report["schema_version"] != 4
        or report["implementation"] != envelope["implementation"]
        or not isinstance(report["manifest_sha256"], str)
        or re.fullmatch(r"[0-9a-f]{64}", report["manifest_sha256"]) is None
    ):
        raise ValueError(f"{slot} P8 report identity is invalid")
    environment = report["environment"]
    if (
        not isinstance(environment, dict)
        or set(environment)
        != {"python_version", "sqlite_version", "numpy_version"}
        or not all(isinstance(value, str) and value for value in environment.values())
    ):
        raise ValueError(f"{slot} P8 environment is invalid")
    embedding = report["embedding_identity"]
    if (
        not isinstance(embedding, dict)
        or set(embedding)
        != {
            "provider",
            "configured_model",
            "dimensions",
            "static_config_identity",
            "descriptor_identity",
            "base_url",
            "canonical_model",
            "model_digest",
            "ollama_version",
            "input_transform_id",
            "pre_attestation",
            "post_attestation",
        }
        or embedding["provider"]
        != (
            ONLINE_EMBEDDING_PROVIDER
            if envelope["embedding"] == "online"
            else envelope["embedding"]
        )
        or not isinstance(embedding["configured_model"], str)
        or re.fullmatch(
            r"[0-9a-f]{64}",
            str(embedding["static_config_identity"]),
        )
        is None
        or re.fullmatch(
            r"[0-9a-f]{64}",
            str(embedding["descriptor_identity"]),
        )
        is None
        or isinstance(embedding["dimensions"], bool)
        or not isinstance(embedding["dimensions"], int)
        or embedding["dimensions"] <= 0
    ):
        raise ValueError(f"{slot} P8 embedding identity is invalid")
    repositories = report["repositories"]
    if not isinstance(repositories, dict) or set(repositories) != {
        "redink",
        "daily",
    }:
        raise ValueError(f"{slot} P8 repositories are invalid")
    for repository in repositories.values():
        if (
            not isinstance(repository, dict)
            or set(repository)
            != {"selected_files", "structure", "index_sqlite_bytes"}
            or isinstance(repository["selected_files"], bool)
            or not isinstance(repository["selected_files"], int)
            or repository["selected_files"] < 0
            or not isinstance(repository["structure"], dict)
            or isinstance(repository["index_sqlite_bytes"], bool)
            or not isinstance(repository["index_sqlite_bytes"], int)
            or repository["index_sqlite_bytes"] < 0
        ):
            raise ValueError(f"{slot} P8 repository schema is invalid")
        structure = repository["structure"]
        if (
            set(structure)
            != {
                "active_chunks",
                "signals_by_producer",
                "relations_by_kind_resolution",
            }
            or isinstance(structure["active_chunks"], bool)
            or not isinstance(structure["active_chunks"], int)
            or structure["active_chunks"] < 0
            or not all(
                isinstance(structure[field], dict)
                and all(
                    isinstance(key, str)
                    and not isinstance(value, bool)
                    and isinstance(value, int)
                    and value >= 0
                    for key, value in structure[field].items()
                )
                for field in (
                    "signals_by_producer",
                    "relations_by_kind_resolution",
                )
            )
        ):
            raise ValueError(f"{slot} P8 structure counts are invalid")
    cases = report["cases"]
    if not isinstance(cases, dict) or len(cases) != 18:
        raise ValueError(f"{slot} P8 report must contain 18 cases")
    for case_id, case in cases.items():
        if (
            not isinstance(case_id, str)
            or not isinstance(case, dict)
            or set(case)
            != {
                "repo",
                "selected",
                "required",
                "contextual",
                "unique_selected_paths",
            }
            or case["repo"] not in {"redink", "daily"}
            or not isinstance(case["selected"], list)
            or not isinstance(case["required"], list)
            or not isinstance(case["contextual"], list)
            or isinstance(case["unique_selected_paths"], bool)
            or not isinstance(case["unique_selected_paths"], int)
        ):
            raise ValueError(f"{slot} P8 case schema is invalid")
        for expected_rank, selected in enumerate(case["selected"], start=1):
            if (
                not isinstance(selected, dict)
                or set(selected) != P8_SELECTED_KEYS
                or isinstance(selected["rank"], bool)
                or not isinstance(selected["rank"], int)
                or selected["rank"] != expected_rank
                or not isinstance(selected["path"], str)
                or not isinstance(selected["score_parts"], dict)
                or list(selected["score_parts"]) != sorted(selected["score_parts"])
                or not isinstance(selected["reasons"], list)
                or not all(
                    isinstance(reason, str) for reason in selected["reasons"]
                )
                or not isinstance(selected["graph_origin"], bool)
                or not isinstance(selected["relation_slot"], bool)
            ):
                raise ValueError(f"{slot} P8 selected projection is invalid")
            _finite_number(selected["score"], f"{slot} selected score")
            for score_part in selected["score_parts"].values():
                _finite_number(score_part, f"{slot} selected score part")
        selected_ranks = {
            selected["path"]: expected_rank
            for expected_rank, selected in enumerate(
                case["selected"],
                start=1,
            )
        }
        if (
            len(selected_ranks) != len(case["selected"])
            or case["unique_selected_paths"] != len(selected_ranks)
        ):
            raise ValueError(f"{slot} P8 selected paths are inconsistent")
        for required in case["required"]:
            if (
                not isinstance(required, dict)
                or set(required) != {"path", "role", "rank", "state"}
                or not isinstance(required["path"], str)
                or not isinstance(required["role"], str)
                or required["state"] not in {"selected", "not_selected"}
                or (
                    required["rank"] is not None
                    and (
                        isinstance(required["rank"], bool)
                        or not isinstance(required["rank"], int)
                        or required["rank"] <= 0
                    )
                )
            ):
                raise ValueError(f"{slot} P8 required item is invalid")
            physical_rank = selected_ranks.get(required["path"])
            expected_state = (
                "selected" if physical_rank is not None else "not_selected"
            )
            if (
                required["state"] != expected_state
                or required["rank"] != physical_rank
            ):
                raise ValueError(
                    f"{slot} P8 required state/rank is inconsistent"
                )
    if not isinstance(report["witnesses"], dict):
        raise ValueError(f"{slot} P8 witnesses are invalid")
    requests = report["embedding_requests"]
    if (
        not isinstance(requests, dict)
        or set(requests) != {"redink", "daily", "total"}
        or any(
            isinstance(value, bool) or not isinstance(value, int) or value < 0
            for value in requests.values()
        )
        or requests["total"] != requests["redink"] + requests["daily"]
    ):
        raise ValueError(f"{slot} P8 request counts are invalid")
    if envelope["embedding"] == "hash":
        if (
            embedding["configured_model"] != "hash-v1"
            or embedding["dimensions"] != 384
            or embedding["base_url"] is not None
            or embedding["static_config_identity"]
            != embedding["descriptor_identity"]
            or any(
                embedding[field] is not None
                for field in (
                    "canonical_model",
                    "model_digest",
                    "ollama_version",
                    "input_transform_id",
                    "pre_attestation",
                    "post_attestation",
                )
            )
            or any(requests[repository] != 0 for repository in requests)
        ):
            raise ValueError(f"{slot} P8 hash identity is invalid")
    else:
        expected_attestation = {
            "provider": ONLINE_EMBEDDING_PROVIDER,
            "configured_model": ONLINE_EMBEDDING_MODEL,
            "dimensions": ONLINE_EMBEDDING_DIMENSIONS,
            "base_url": ONLINE_BASE_URL,
        }
        if (
            envelope["embedding"] != "online"
            or embedding["configured_model"] != ONLINE_EMBEDDING_MODEL
            or embedding["dimensions"] != ONLINE_EMBEDDING_DIMENSIONS
            or embedding["base_url"] != ONLINE_BASE_URL
            or embedding["static_config_identity"]
            != embedding["descriptor_identity"]
            or embedding["canonical_model"] != ONLINE_EMBEDDING_MODEL
            or embedding["model_digest"] is not None
            or embedding["ollama_version"] is not None
            or embedding["input_transform_id"] is not None
            or embedding["pre_attestation"] != expected_attestation
            or embedding["post_attestation"] != expected_attestation
            or requests["redink"] <= 0
            or requests["daily"] <= 0
        ):
            raise ValueError(f"{slot} P8 online identity is invalid")
    timing = report["timing"]
    if (
        not isinstance(timing, dict)
        or set(timing)
        != {
            "index_seconds",
            "query_case_min_seconds",
            "query_p50_seconds",
            "query_p95_seconds",
        }
        or not isinstance(timing["query_case_min_seconds"], dict)
        or set(timing["query_case_min_seconds"]) != set(cases)
        or not isinstance(timing["index_seconds"], dict)
        or set(timing["index_seconds"]) != {"redink", "daily"}
    ):
        raise ValueError(f"{slot} P8 timing schema is invalid")
    for repository, seconds in timing["index_seconds"].items():
        if _finite_number(seconds, f"{slot} {repository} index time") < 0:
            raise ValueError(f"{slot} P8 index timing is negative")
    case_timings = []
    for case_id, seconds in timing["query_case_min_seconds"].items():
        case_seconds = _finite_number(
            seconds,
            f"{slot} {case_id} query time",
        )
        if case_seconds < 0:
            raise ValueError(f"{slot} P8 case timing is negative")
        case_timings.append(case_seconds)
    p50 = _finite_number(timing["query_p50_seconds"], f"{slot} query p50")
    p95 = _finite_number(timing["query_p95_seconds"], f"{slot} query p95")
    ordered_timings = sorted(case_timings)
    expected_p50 = ordered_timings[
        max(0, math.ceil(0.50 * len(ordered_timings)) - 1)
    ]
    expected_p95 = ordered_timings[
        max(0, math.ceil(0.95 * len(ordered_timings)) - 1)
    ]
    if p50 < 0 or p95 < 0:
        raise ValueError(f"{slot} P8 percentile timing is negative")
    if p50 != expected_p50 or p95 != expected_p95:
        raise ValueError(
            f"{slot} P8 percentiles disagree with case timings"
        )
    return report


def _required_rows(report: dict[str, object]) -> list[tuple[str, str, str, int]]:
    rows = []
    for case_id, case in sorted(report["cases"].items()):
        for required in case["required"]:
            rows.append(
                (
                    case_id,
                    required["path"],
                    required["role"],
                    required["rank"] if required["rank"] is not None else 13,
                )
            )
    return rows


def _noise(report: dict[str, object]) -> tuple[int, int]:
    noise = 0
    selected = 0
    for case in report["cases"].values():
        relevant = {row["path"] for row in case["required"]} | set(
            case["contextual"]
        )
        noise += sum(
            row["path"] not in relevant for row in case["selected"]
        )
        selected += len(case["selected"])
    return noise, selected


_RANKING_DELTA_FIELDS = (
    "membership",
    "order",
    "score",
    "score_parts",
    "reasons",
    "graph_origin",
    "relation_slot",
    "relation_witness",
)
_ONLINE_VOLATILE_SCORE_PARTS = {
    "combined_score",
    "effective_semantic",
    "rerank_score",
    "semantic",
}
_ONLINE_NUMERIC_SENTINEL = "<online-model-numeric>"
_ONLINE_RERANK_REASON = re.compile(
    r"^(rerank_score=)"
    r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?"
)


def _mask_online_numbers(value: object) -> object:
    if isinstance(value, dict):
        return {key: _mask_online_numbers(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_mask_online_numbers(item) for item in value]
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return _ONLINE_NUMERIC_SENTINEL
    return value


def _normalize_online_reason(reason: str) -> str:
    return _ONLINE_RERANK_REASON.sub(
        rf"\1{_ONLINE_NUMERIC_SENTINEL}",
        reason,
        count=1,
    )


def _online_stable_projection(
    value: object,
    *,
    parent_key: str | None = None,
) -> object:
    if isinstance(value, dict):
        projection = {}
        for key, item in value.items():
            if key in {"generated_at", "latency_ms"}:
                continue
            if key == "top_score":
                projection[key] = _mask_online_numbers(item)
            elif key == "score" or (
                parent_key == "score_parts"
                and key in _ONLINE_VOLATILE_SCORE_PARTS
            ):
                projection[key] = _ONLINE_NUMERIC_SENTINEL
            elif key == "reasons":
                projection[key] = [
                    _normalize_online_reason(reason) for reason in item
                ]
            else:
                projection[key] = _online_stable_projection(
                    item,
                    parent_key=key,
                )
        return projection
    if isinstance(value, list):
        return [
            _online_stable_projection(item, parent_key=parent_key)
            for item in value
        ]
    return value


def _online_score_observations(
    value: object,
    *,
    parent_key: str | None = None,
    path: str = "$",
) -> list[tuple[str, object]]:
    observations: list[tuple[str, object]] = []
    if isinstance(value, dict):
        for key, item in value.items():
            item_path = f"{path}.{key}"
            if key in {"generated_at", "latency_ms"}:
                continue
            if key == "top_score":
                observations.append((item_path, item))
            elif key == "score" or (
                parent_key == "score_parts"
                and key in _ONLINE_VOLATILE_SCORE_PARTS
            ):
                observations.append((item_path, item))
            elif key == "reasons":
                observations.extend(
                    (
                        f"{item_path}[{index}]",
                        reason,
                    )
                    for index, reason in enumerate(item)
                    if _normalize_online_reason(reason) != reason
                )
            else:
                observations.extend(
                    _online_score_observations(
                        item,
                        parent_key=key,
                        path=item_path,
                    )
                )
    elif isinstance(value, list):
        for index, item in enumerate(value):
            observations.extend(
                _online_score_observations(
                    item,
                    parent_key=parent_key,
                    path=f"{path}[{index}]",
                )
            )
    return observations


def _ranking_field_projection(
    selected: list[dict[str, object]],
    field: str,
) -> object:
    paths = [row["path"] for row in selected]
    if field == "membership":
        return sorted(paths)
    if field == "order":
        return paths
    return {row["path"]: row[field] for row in selected}


def _case_delta(
    *,
    provider: str,
    case_id: str,
    eligible: bool,
    baseline_selected: list[dict[str, object]],
    candidate_selected: list[dict[str, object]],
) -> dict[str, object] | None:
    changed_fields = [
        field
        for field in _RANKING_DELTA_FIELDS
        if _ranking_field_projection(baseline_selected, field)
        != _ranking_field_projection(candidate_selected, field)
    ]
    if not changed_fields:
        return None
    return {
        "provider": provider,
        "case_id": case_id,
        "eligible": eligible,
        "changed_fields": changed_fields,
        "projection": {
            "baseline_selected": baseline_selected,
            "candidate_selected": candidate_selected,
        },
    }


def _changes_cohort_penalty(delta: dict[str, object]) -> bool:
    projection = delta["projection"]

    def penalties(side: str) -> dict[str, object]:
        return {
            row["path"]: row["score_parts"]["cohort_mismatch_penalty"]
            for row in projection[side]
            if "cohort_mismatch_penalty" in row["score_parts"]
        }

    return penalties("baseline_selected") != penalties("candidate_selected")


def _median_pair(values: list[float]) -> float:
    ordered = sorted(values)
    return (ordered[0] + ordered[1]) / 2.0


def _compare_p8(
    *,
    arguments: argparse.Namespace,
    inputs: dict[str, Path],
    captures: dict[str, dict[str, object]],
    inventory_path: Path,
    inventory: dict[str, object],
    eligible: set[str],
) -> None:
    reports = {
        slot: _validate_p8_report(capture, slot)
        for slot, capture in captures.items()
    }
    if len({report["manifest_sha256"] for report in reports.values()}) != 1:
        raise ValueError("P8 manifest identity changed across captures")
    case_ids = set(next(iter(reports.values()))["cases"])
    if not eligible <= case_ids:
        raise ValueError("eligible inventory names an unknown P8 case")

    repeat_mismatches = []
    online_repeat_numeric_drift = []
    for provider in ("hash", "online"):
        for side in ("baseline", "candidate"):
            first = json.loads(_canonical_json(reports[f"{provider}-{side}-r1"]))
            second = json.loads(_canonical_json(reports[f"{provider}-{side}-r2"]))
            for report in (first, second):
                report.pop("implementation")
                report.pop("timing")
            first_projection = (
                _online_stable_projection(first)
                if provider == "online"
                else first
            )
            second_projection = (
                _online_stable_projection(second)
                if provider == "online"
                else second
            )
            if first_projection != second_projection:
                repeat_mismatches.append(f"{provider}-{side}")
            elif (
                provider == "online"
                and _online_score_observations(first)
                != _online_score_observations(second)
            ):
                online_repeat_numeric_drift.append(f"{provider}-{side}")

    parity_mismatches = []
    online_noneligible_numeric_drift = []
    protected_mismatches = []
    structural_mismatches = []
    case_deltas = []
    eligible_cohort_deltas = []
    providers: dict[str, object] = {}
    for provider in ("hash", "online"):
        baseline = reports[f"{provider}-baseline-r1"]
        candidate = reports[f"{provider}-candidate-r1"]
        baseline_required = _required_rows(baseline)
        candidate_required = _required_rows(candidate)
        if [row[:3] for row in baseline_required] != [
            row[:3] for row in candidate_required
        ]:
            raise ValueError(f"{provider} required inventory changed")
        denominator = len(baseline_required)
        baseline_hits = sum(row[3] <= 12 for row in baseline_required)
        candidate_hits = sum(row[3] <= 12 for row in candidate_required)
        losses = [
            list(base[:3])
            for base, cand in zip(
                baseline_required,
                candidate_required,
                strict=True,
            )
            if base[3] <= 12 < cand[3]
        ]
        baseline_noise, baseline_selected = _noise(baseline)
        candidate_noise, candidate_selected = _noise(candidate)
        baseline_ratio = baseline_noise / max(1, baseline_selected)
        candidate_ratio = candidate_noise / max(1, candidate_selected)

        for case_id in sorted(case_ids - eligible):
            baseline_selected_rows = baseline["cases"][case_id]["selected"]
            candidate_selected_rows = candidate["cases"][case_id]["selected"]
            baseline_projection = (
                _online_stable_projection(baseline_selected_rows)
                if provider == "online"
                else baseline_selected_rows
            )
            candidate_projection = (
                _online_stable_projection(candidate_selected_rows)
                if provider == "online"
                else candidate_selected_rows
            )
            if baseline_projection != candidate_projection:
                parity_mismatches.append(f"{provider}:{case_id}")
            elif (
                provider == "online"
                and _online_score_observations(baseline_selected_rows)
                != _online_score_observations(candidate_selected_rows)
            ):
                online_noneligible_numeric_drift.append(
                    f"{provider}:{case_id}"
                )
        for case_id in sorted(case_ids):
            delta = _case_delta(
                provider=provider,
                case_id=case_id,
                eligible=case_id in eligible,
                baseline_selected=baseline["cases"][case_id]["selected"],
                candidate_selected=candidate["cases"][case_id]["selected"],
            )
            if delta is None:
                continue
            case_deltas.append(delta)
            if delta["eligible"] and _changes_cohort_penalty(delta):
                eligible_cohort_deltas.append(
                    {
                        "provider": provider,
                        "case_id": case_id,
                        "changed_fields": delta["changed_fields"],
                    }
                )
        for case_id in sorted(case_ids):
            base_selected = baseline["cases"][case_id]["selected"]
            cand_selected = candidate["cases"][case_id]["selected"]
            if (
                base_selected
                and not base_selected[0]["graph_origin"]
                and (
                    not cand_selected
                    or base_selected[0]["path"] != cand_selected[0]["path"]
                )
            ):
                protected_mismatches.append(f"{provider}:{case_id}")

        structural_fields = (
            "embedding_identity",
            "embedding_requests",
        )
        for field in structural_fields:
            if baseline[field] != candidate[field]:
                structural_mismatches.append(f"{provider}:{field}")
        for repo in ("redink", "daily"):
            for field in ("selected_files", "structure"):
                if (
                    baseline["repositories"][repo][field]
                    != candidate["repositories"][repo][field]
                ):
                    structural_mismatches.append(
                        f"{provider}:{repo}:{field}"
                    )

        baseline_p95 = [
            _finite_number(
                reports[f"{provider}-baseline-r{repeat}"]["timing"][
                    "query_p95_seconds"
                ],
                "query p95",
            )
            for repeat in (1, 2)
        ]
        candidate_p95 = [
            _finite_number(
                reports[f"{provider}-candidate-r{repeat}"]["timing"][
                    "query_p95_seconds"
                ],
                "query p95",
            )
            for repeat in (1, 2)
        ]
        baseline_spread = (
            (max(baseline_p95) - min(baseline_p95)) / min(baseline_p95)
            if min(baseline_p95) > 0
            else math.inf
        )
        timing_ratio = (
            _median_pair(candidate_p95) / _median_pair(baseline_p95)
            if _median_pair(baseline_p95) > 0
            else math.inf
        )
        providers[provider] = {
            "recall": {
                "baseline_hits": baseline_hits,
                "candidate_hits": candidate_hits,
                "denominator": denominator,
                "baseline_ratio": baseline_hits / max(1, denominator),
                "candidate_ratio": candidate_hits / max(1, denominator),
                "threshold": "candidate>=baseline",
            },
            "required_losses": {
                "count": len(losses),
                "threshold": 0,
                "items": losses,
            },
            "noise": {
                "baseline_numerator": baseline_noise,
                "baseline_denominator": baseline_selected,
                "baseline_ratio": baseline_ratio,
                "candidate_numerator": candidate_noise,
                "candidate_denominator": candidate_selected,
                "candidate_ratio": candidate_ratio,
                "threshold": "candidate<=baseline",
            },
            "timing": {
                "baseline_query_p95": baseline_p95,
                "candidate_query_p95": candidate_p95,
                "baseline_spread": baseline_spread,
                "baseline_spread_threshold": 0.15,
                "candidate_baseline_ratio": timing_ratio,
                "candidate_baseline_ratio_threshold": 1.10,
            },
        }

    gates = {
        "recall_non_decreasing": all(
            row["recall"]["candidate_hits"]
            >= row["recall"]["baseline_hits"]
            for row in providers.values()
        ),
        "zero_required_losses": all(
            row["required_losses"]["count"] == 0
            for row in providers.values()
        ),
        "noise_non_increasing": all(
            row["noise"]["candidate_ratio"]
            <= row["noise"]["baseline_ratio"] + 1e-12
            for row in providers.values()
        ),
        "protected_winners_stable": not protected_mismatches,
        "noneligible_parity": not parity_mismatches,
        "repeat_determinism": not repeat_mismatches,
        "structure_and_requests_stable": not structural_mismatches,
        "baseline_timing_stable": all(
            row["timing"]["baseline_spread"] <= 0.15 + 1e-12
            for row in providers.values()
        ),
        "candidate_timing_ratio": all(
            row["timing"]["candidate_baseline_ratio"] <= 1.10 + 1e-12
            for row in providers.values()
        ),
    }
    if not gates["repeat_determinism"]:
        disposition = "reject"
    elif not gates["baseline_timing_stable"]:
        disposition = "blocked"
    elif all(gates.values()):
        disposition = "ship"
    else:
        disposition = "reject"
    report = {
        "schema_version": 1,
        "gate_kind": "p8",
        "attempt_id": arguments.attempt_id,
        "eligible_inventory": {
            "filename": inventory_path.name,
            "sha256": _sha256(inventory_path),
        },
        "inputs": {
            slot: {"filename": path.name, "sha256": _sha256(path)}
            for slot, path in inputs.items()
        },
        "providers": providers,
        "repeat_determinism": {
            "mismatches": repeat_mismatches,
            "threshold": 0,
        },
        "noneligible_parity": {
            "eligible_case_ids": sorted(eligible),
            "checked_case_count": len(case_ids - eligible),
            "mismatches": parity_mismatches,
            "threshold": 0,
        },
        "case_deltas": case_deltas,
        "r2_cohort_deltas": {
            "reason": "eligible_exact_query_rerank_cascade",
            "count": len(eligible_cohort_deltas),
            "items": eligible_cohort_deltas,
        },
        "protected_winner_mismatches": protected_mismatches,
        "structural_mismatches": structural_mismatches,
        "online_numeric_drift": {
            "policy": (
                "disclosed_only_when_membership_order_and_nonsemantic_"
                "ranking_evidence_are_stable"
            ),
            "repeat_pairs": online_repeat_numeric_drift,
            "noneligible_pairs": online_noneligible_numeric_drift,
        },
        "gates": gates,
        "disposition": disposition,
    }
    _write_new(Path(arguments.output).resolve(), _canonical_json(report))


def _p1_catalog_facts(
    catalog_path: Path,
    profile: str,
) -> tuple[dict[tuple[str, str], dict[str, object]], int]:
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    if (
        not isinstance(catalog, dict)
        or catalog.get("schema_version") != 1
        or not isinstance(catalog.get("repos"), list)
    ):
        raise ValueError("P1 catalog schema is invalid")
    facts = {}
    fixture_case_count = 0
    for repository in catalog["repos"]:
        if (
            not isinstance(repository, dict)
            or not isinstance(repository.get("repo_key"), str)
            or not isinstance(repository.get("queries"), list)
        ):
            raise ValueError("P1 catalog repository schema is invalid")
        fixture_case_count += len(repository["queries"])
        for query in repository["queries"]:
            if not isinstance(query, dict):
                raise ValueError("P1 catalog case schema is invalid")
            if profile not in query.get("profiles", []):
                continue
            expected = query.get("expected_top_k")
            tags = query.get("tags", [])
            if (
                not isinstance(expected, list)
                or not expected
                or not isinstance(expected[0], dict)
                or not isinstance(expected[0].get("path"), str)
                or not isinstance(query.get("id"), str)
                or not isinstance(query.get("query"), str)
                or not isinstance(tags, list)
                or not all(isinstance(tag, str) for tag in tags)
            ):
                raise ValueError("P1 case has no required rank target")
            preferred_rank = query.get("preferred_rank", [])
            if not isinstance(preferred_rank, list):
                raise ValueError("P1 preferred-rank schema is invalid")
            entrypoint_paths = [
                item["path"]
                for item in preferred_rank
                if isinstance(item, dict)
                and item.get("role") == "entrypoint"
                and isinstance(item.get("path"), str)
            ]
            if ("entrypoint" in tags) != (len(entrypoint_paths) == 1):
                raise ValueError(
                    "P1 entrypoint tag/path provenance is invalid"
                )
            key = (repository["repo_key"], query["id"])
            if key in facts:
                raise ValueError("P1 catalog contains a duplicate case")
            facts[key] = {
                "target_path": expected[0]["path"],
                "query": query["query"],
                "tags": list(tags),
                "entrypoint_path": (
                    entrypoint_paths[0] if entrypoint_paths else None
                ),
                "relevant_paths": [
                    *(
                        item["path"]
                        for item in expected
                        if isinstance(item, dict)
                        and isinstance(item.get("path"), str)
                    ),
                    *(
                        matcher["path"]
                        for group in query.get("expected_any_top_k", [])
                        if isinstance(group, dict)
                        for matcher in group.get("matchers", [])
                        if isinstance(matcher, dict)
                        and isinstance(matcher.get("path"), str)
                    ),
                ],
            }
    if len(facts) != 7:
        raise ValueError("P1 catalog must select exactly seven cases")
    return facts, fixture_case_count


def _p1_catalog_targets(
    catalog_path: Path,
    profile: str,
) -> dict[tuple[str, str], str]:
    facts, _fixture_case_count = _p1_catalog_facts(catalog_path, profile)
    return {key: str(fact["target_path"]) for key, fact in facts.items()}


def _p1_implementation_root(envelope: dict[str, object]) -> Path:
    expected_relatives = {
        "identifier_intent": Path(
            "src/context_search_tool/identifier_intent.py"
        ),
        "ranking": Path(
            "src/context_search_tool/retrieval_core/ranking.py"
        ),
        "context_expansion": Path(
            "src/context_search_tool/retrieval_core/context_expansion.py"
        ),
    }
    roots = set()
    for label, relative in expected_relatives.items():
        origin = Path(envelope["module_origins"][label])
        root = origin.parents[len(relative.parts) - 1]
        if root / relative != origin:
            raise ValueError("P1 module origin layout is invalid")
        roots.add(root)
    if len(roots) != 1:
        raise ValueError("P1 module origins do not share an implementation root")
    return roots.pop()


def _validate_p1_report(
    envelope: dict[str, object],
    slot: str,
    catalog_sha256: str,
    facts: dict[tuple[str, str], dict[str, object]],
    fixture_case_count: int,
) -> tuple[dict[str, object], dict[tuple[str, str], dict[str, object]]]:
    report = envelope["report"]
    if not isinstance(report, dict) or set(report) != P1_REPORT_KEYS:
        raise ValueError(f"{slot} P1 report schema is not closed")
    implementation_root = _p1_implementation_root(envelope)
    expected_catalog = (
        implementation_root
        / "tests/fixtures/retrieval_quality/queries.json"
    )
    command_args = report["command_args"]
    fixture = report["fixture"]
    if (
        report["schema_version"] != 2
        or report["profile"] != envelope["profile"]
        or not isinstance(report["generated_at"], str)
        or not report["generated_at"]
        or not isinstance(command_args, dict)
        or set(command_args) != P1_COMMAND_ARGS_KEYS
        or command_args["profile"] != envelope["profile"]
        or command_args["fixture_path"] != str(expected_catalog)
        or not isinstance(fixture, dict)
        or set(fixture) != P1_FIXTURE_KEYS
        or fixture["path"] != str(expected_catalog)
        or fixture["sha256"] != catalog_sha256
        or isinstance(fixture["schema_version"], bool)
        or fixture["schema_version"] != 1
        or isinstance(fixture["fixture_case_count"], bool)
        or fixture["fixture_case_count"] != fixture_case_count
        or isinstance(fixture["run_case_count"], bool)
        or fixture["run_case_count"] != len(facts)
        or not isinstance(report["config"], dict)
        or not isinstance(report["config"].get("embedding"), dict)
        or report["config"]["embedding"].get("provider")
        != ONLINE_EMBEDDING_PROVIDER
        or not isinstance(report["planner"], dict)
        or not isinstance(report["aggregate"], dict)
        or not isinstance(report["repos"], list)
        or not isinstance(report["cases"], list)
    ):
        raise ValueError(f"{slot} P1 report identity is invalid")
    config = report["config"]
    embedding_config = config["embedding"]
    if (
        set(config) != P1_CONFIG_KEYS
        or not isinstance(config["config_hash"], str)
        or re.fullmatch(
            r"sha256:[0-9a-f]{64}",
            config["config_hash"],
        )
        is None
        or set(embedding_config) != P1_EMBEDDING_CONFIG_KEYS
        or embedding_config["provider"] != ONLINE_EMBEDDING_PROVIDER
        or embedding_config["model"] != ONLINE_EMBEDDING_MODEL
        or embedding_config["dimensions"] != ONLINE_EMBEDDING_DIMENSIONS
        or embedding_config["base_url"] != ONLINE_BASE_URL
        or embedding_config["api_key_env"] is not None
    ):
        raise ValueError(f"{slot} P1 config provenance is invalid")
    planner_config = report["planner"]
    if (
        set(planner_config) != P1_PLANNER_CONFIG_KEYS
        or planner_config["enabled"]
        is not (envelope["profile"] == "p1_hybrid_bge")
        or planner_config["provider"] != ONLINE_PLANNER_PROVIDER
        or planner_config["model"] != ONLINE_PLANNER_MODEL
        or planner_config["base_url"] != ONLINE_BASE_URL
        or planner_config["timeout_seconds"]
        != ONLINE_PLANNER_TIMEOUT_SECONDS
        or planner_config["use_system_proxy"] is not False
        or planner_config["max_rewritten_queries"] != 4
        or planner_config["max_keywords"] != 12
        or planner_config["max_symbol_hints"] != 8
    ):
        raise ValueError(f"{slot} P1 planner provenance is invalid")
    tool = report["tool"]
    if (
        not isinstance(tool, dict)
        or set(tool) != {"name", "git_commit"}
        or tool["name"] != "context-search-tool"
        or tool["git_commit"] != envelope["implementation"]["base_commit"]
    ):
        raise ValueError(f"{slot} P1 tool/planner provenance is invalid")
    aggregate = report["aggregate"]
    if set(aggregate) != P1_AGGREGATE_KEYS or not isinstance(
        aggregate["metrics"],
        dict,
    ):
        raise ValueError(f"{slot} P1 aggregate schema is not closed")
    for field in P1_AGGREGATE_KEYS - {"metrics"}:
        value = aggregate[field]
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"{slot} P1 aggregate counts are invalid")
    case_index: dict[tuple[str, str], dict[str, object]] = {}
    case_reports: dict[tuple[str, str], dict[str, object]] = {}
    for case in report["cases"]:
        if not isinstance(case, dict) or set(case) != P1_CASE_KEYS:
            raise ValueError(f"{slot} P1 case schema is invalid")
        key = (case["repo_key"], case["case_id"])
        planner = case["planner"]
        variants = case["query_variants"]
        if (
            key in case_index
            or key not in facts
            or case["query"] != facts[key]["query"]
            or case["gate"] != "required"
            or case["attempted"] is not True
            or case["status"] not in {"pass", "fail", "error", "skipped"}
            or not isinstance(case["known_gap_reason"], str)
            or case["tags"] != facts[key]["tags"]
            or not isinstance(planner, dict)
            or set(planner) != P1_CASE_PLANNER_KEYS
            or planner["status"]
            != (
                "ok"
                if envelope["profile"] == "p1_hybrid_bge"
                else "disabled"
            )
            or (
                envelope["profile"] == "p1_hybrid_bge"
                and (
                    planner["provider"] != ONLINE_PLANNER_PROVIDER
                    or planner["model"] != ONLINE_PLANNER_MODEL
                    or planner["latency_ms"] is None
                )
            )
            or (
                envelope["profile"] == "p1_vector_bge"
                and (
                    planner["provider"] != ""
                    or planner["model"] != ""
                    or planner["latency_ms"] is not None
                )
            )
            or not isinstance(planner["repo_profile_truncated"], bool)
            or not all(
                isinstance(planner[field], str)
                for field in (
                    "provider",
                    "model",
                    "prompt_version",
                    "prompt_hash",
                    "repo_profile_hash",
                )
            )
            or not all(
                isinstance(planner[field], list)
                and all(isinstance(value, str) for value in planner[field])
                for field in (
                    "rewritten_queries",
                    "grep_keywords",
                    "symbol_hints",
                    "discarded_hints",
                )
            )
            or (
                planner["latency_ms"] is not None
                and (
                    isinstance(planner["latency_ms"], bool)
                    or not isinstance(planner["latency_ms"], (int, float))
                    or not math.isfinite(float(planner["latency_ms"]))
                    or planner["latency_ms"] < 0
                )
            )
            or not isinstance(variants, list)
            or not variants
            or not isinstance(case["expanded_tokens"], list)
            or not all(
                isinstance(value, str) for value in case["expanded_tokens"]
            )
            or not isinstance(case["tags"], list)
            or not all(isinstance(value, str) for value in case["tags"])
            or not isinstance(case["failures"], list)
            or not all(isinstance(value, str) for value in case["failures"])
            or not isinstance(case["variant_retrieval_status"], str)
            or not isinstance(case["top_results"], list)
            or not isinstance(case["metrics"], dict)
            or set(case["metrics"]) != P1_CASE_METRICS_KEYS
        ):
            raise ValueError(f"{slot} P1 case identity is invalid")
        variant_ids = []
        for index, variant in enumerate(variants):
            if (
                not isinstance(variant, dict)
                or set(variant) != P1_QUERY_VARIANT_KEYS
                or not all(
                    isinstance(variant[field], str) and variant[field]
                    for field in P1_QUERY_VARIANT_KEYS
                )
                or (
                    index == 0
                    and variant
                    != {
                        "variant_id": "original",
                        "text": case["query"],
                        "source": "original",
                    }
                )
                or (
                    index > 0
                    and (
                        variant["variant_id"] != f"planner:{index - 1}"
                        or variant["source"] != "planner"
                    )
                )
            ):
                raise ValueError(f"{slot} P1 query variant is invalid")
            variant_ids.append(variant["variant_id"])
        if len(variant_ids) != len(set(variant_ids)):
            raise ValueError(f"{slot} P1 query variants are duplicated")
        result_paths = set()
        rank = None
        relevant_rank = None
        entrypoint_physical_rank = None
        relevant_paths = set(facts[key]["relevant_paths"])
        for physical_rank, result in enumerate(
            case["top_results"],
            start=1,
        ):
            if (
                not isinstance(result, dict)
                or set(result) != P1_TOP_RESULT_KEYS
                or isinstance(result["rank"], bool)
                or not isinstance(result["rank"], int)
                or result["rank"] != physical_rank
                or not isinstance(result["path"], str)
                or not result["path"]
                or result["path"] in result_paths
                or not isinstance(result["score_parts"], dict)
                or not all(isinstance(key, str) for key in result["score_parts"])
                or not isinstance(result["reasons"], list)
                or not all(
                    isinstance(reason, str) for reason in result["reasons"]
                )
                or not isinstance(result["semantic_matches"], list)
            ):
                raise ValueError(f"{slot} P1 top result is invalid")
            _finite_number(result["score"], f"{slot} P1 result score")
            for score_part in result["score_parts"].values():
                _finite_number(
                    score_part,
                    f"{slot} P1 result score part",
                )
            for semantic_match in result["semantic_matches"]:
                if (
                    not isinstance(semantic_match, dict)
                    or set(semantic_match) != P1_SEMANTIC_MATCH_KEYS
                    or semantic_match["variant_id"] not in variant_ids
                ):
                    raise ValueError(
                        f"{slot} P1 semantic match is invalid"
                    )
                _finite_number(
                    semantic_match["score"],
                    f"{slot} P1 semantic match score",
                )
            result_paths.add(result["path"])
            if result["path"] == facts[key]["target_path"]:
                rank = physical_rank
            if result["path"] in relevant_paths and relevant_rank is None:
                relevant_rank = physical_rank
            if result["path"] == facts[key]["entrypoint_path"]:
                entrypoint_physical_rank = physical_rank
        coverage = case["metrics"]["expected_coverage_top5"]
        if (
            not isinstance(coverage, dict)
            or set(coverage) != {"count", "ratio"}
            or isinstance(coverage["count"], bool)
            or not isinstance(coverage["count"], int)
            or coverage["count"] < 0
        ):
            raise ValueError(f"{slot} P1 case metrics are invalid")
        metrics = case["metrics"]
        result_count = metrics["result_count"]
        if (
            isinstance(result_count, bool)
            or not isinstance(result_count, int)
            or not 0 <= result_count <= 12
            or len(case["top_results"]) != min(result_count, 10)
            or any(
                not isinstance(metrics[field], bool)
                for field in (
                    "hit_at_1",
                    "hit_at_3",
                    "hit_at_5",
                    "hit_at_10",
                    "preferred_rank_pass",
                )
            )
            or (
                metrics["cross_language_success"] is not None
                and not isinstance(metrics["cross_language_success"], bool)
            )
            or any(
                isinstance(metrics[field], bool)
                or not isinstance(metrics[field], int)
                or metrics[field] < 0
                for field in ("noise_top5", "noise_top10")
            )
            or (
                metrics["entrypoint_rank"] is not None
                and (
                    isinstance(metrics["entrypoint_rank"], bool)
                    or not isinstance(metrics["entrypoint_rank"], int)
                    or metrics["entrypoint_rank"] <= 0
                )
            )
        ):
            raise ValueError(f"{slot} P1 case metric types are invalid")
        is_entrypoint = "entrypoint" in facts[key]["tags"]
        if (
            (metrics["entrypoint_rank"] is not None) != is_entrypoint
            or metrics["entrypoint_rank"] != entrypoint_physical_rank
        ):
            raise ValueError(
                f"{slot} P1 entrypoint metric disagrees with ranked results"
            )
        numeric_metrics = {
            field: _finite_number(
                metrics[field],
                f"{slot} P1 case metric {field}",
            )
            for field in (
                "mrr",
                "recall_at_5",
                "recall_at_10",
                "top_score",
                "latency_ms",
            )
        }
        coverage_ratio = _finite_number(
            coverage["ratio"],
            f"{slot} P1 coverage ratio",
        )
        if (
            not 0.0 <= coverage_ratio <= 1.0
            or not 0.0 <= numeric_metrics["mrr"] <= 1.0
            or not 0.0 <= numeric_metrics["recall_at_5"] <= 1.0
            or not 0.0 <= numeric_metrics["recall_at_10"] <= 1.0
            or numeric_metrics["latency_ms"] < 0
            or not case["top_results"]
            or abs(
                numeric_metrics["top_score"]
                - float(case["top_results"][0]["score"])
            )
            > 1e-12
        ):
            raise ValueError(f"{slot} P1 case metric values are invalid")
        expected_mrr = (
            0.0 if relevant_rank is None else 1.0 / relevant_rank
        )
        if (
            abs(numeric_metrics["mrr"] - expected_mrr) > 1e-12
            or any(
                metrics[f"hit_at_{threshold}"]
                is not (
                    relevant_rank is not None
                    and relevant_rank <= threshold
                )
                for threshold in (1, 3, 5, 10)
            )
            or abs(
                numeric_metrics["recall_at_5"]
                - float(relevant_rank is not None and relevant_rank <= 5)
            )
            > 1e-12
            or abs(
                numeric_metrics["recall_at_10"]
                - float(relevant_rank is not None and relevant_rank <= 10)
            )
            > 1e-12
        ):
            raise ValueError(
                f"{slot} P1 case metrics disagree with ranked results"
            )
        if (
            case["status"] == "pass"
            and case["failures"]
        ) or (
            case["status"] == "fail"
            and not case["failures"]
        ):
            raise ValueError(
                f"{slot} P1 case status disagrees with failures"
            )
        case_index[key] = {
            "status": case["status"],
            "gate": case["gate"],
            "target_path": facts[key]["target_path"],
            "target_rank": rank,
            "planner_status": planner["status"],
            "embedding_fallback": (
                case["variant_retrieval_status"] == "embedding_fallback"
            ),
            "variant_retrieval_status": case["variant_retrieval_status"],
        }
        case_reports[key] = case
    if set(case_index) != set(facts):
        raise ValueError(f"{slot} P1 selected case set is invalid")
    status_counts = {
        "passed": sum(row["status"] == "pass" for row in case_index.values()),
        "failed": sum(row["status"] == "fail" for row in case_index.values()),
        "skipped": sum(row["status"] == "skipped" for row in case_index.values()),
        "errors": sum(row["status"] == "error" for row in case_index.values()),
    }
    expected_aggregate_counts = {
        "total": len(facts),
        "selected": len(facts),
        "attempted": len(case_index),
        "executed": len(case_index),
        "known_gaps": 0,
        "informational": 0,
        **status_counts,
    }
    if any(
        aggregate[field] != count
        for field, count in expected_aggregate_counts.items()
    ):
        raise ValueError(f"{slot} P1 aggregate does not match case statuses")
    overall = aggregate["metrics"].get("overall")
    if not isinstance(overall, dict):
        raise ValueError(f"{slot} P1 overall metrics are missing")
    metric_specs = {
        "mrr": ("mean", "count"),
        "recall_at_5": ("mean", "count"),
        "entrypoint_top3": ("rate", "successes", "total"),
    }
    if any(
        not isinstance(overall.get(metric), dict)
        or set(overall[metric]) != set(fields)
        for metric, fields in metric_specs.items()
    ):
        raise ValueError(f"{slot} P1 overall metric schema is invalid")
    mrr_values = [
        float(case["metrics"]["mrr"]) for case in case_reports.values()
    ]
    recall_values = [
        float(case["metrics"]["recall_at_5"])
        for case in case_reports.values()
    ]
    entrypoint_ranks = [
        case["metrics"]["entrypoint_rank"]
        for key, case in case_reports.items()
        if "entrypoint" in facts[key]["tags"]
    ]
    entrypoint_successes = sum(
        rank is not None and rank <= 3 for rank in entrypoint_ranks
    )
    expected_overall = {
        "mrr": {
            "count": len(mrr_values),
            "mean": sum(mrr_values) / len(mrr_values),
        },
        "recall_at_5": {
            "count": len(recall_values),
            "mean": sum(recall_values) / len(recall_values),
        },
        "entrypoint_top3": {
            "successes": entrypoint_successes,
            "total": len(entrypoint_ranks),
            "rate": entrypoint_successes / len(entrypoint_ranks),
        },
    }
    for metric, expected in expected_overall.items():
        for field, expected_value in expected.items():
            actual = overall[metric][field]
            if isinstance(expected_value, int):
                if (
                    isinstance(actual, bool)
                    or not isinstance(actual, int)
                    or actual != expected_value
                ):
                    raise ValueError(
                        f"{slot} P1 overall {metric}.{field} is invalid"
                    )
            elif abs(
                _finite_number(
                    actual,
                    f"{slot} P1 overall {metric}.{field}",
                )
                - expected_value
            ) > 1e-12:
                raise ValueError(
                    f"{slot} P1 overall {metric}.{field} is invalid"
                )
    return report, case_index


def _p1_counts(report: dict[str, object]) -> dict[str, int]:
    return {
        field: report["aggregate"][field]
        for field in ("selected", "executed", "passed", "failed", "skipped", "errors")
    }


def _p1_metric(report: dict[str, object], metric: str, field: str) -> float:
    try:
        value = report["aggregate"]["metrics"]["overall"][metric][field]
    except (KeyError, TypeError) as error:
        raise ValueError(f"P1 metric {metric}.{field} is missing") from error
    return _finite_number(value, f"P1 metric {metric}.{field}")


def _p1_without_declared_timing(value: object) -> object:
    if isinstance(value, dict):
        return {
            key: _p1_without_declared_timing(item)
            for key, item in value.items()
            if key not in {"generated_at", "latency_ms"}
        }
    if isinstance(value, list):
        return [_p1_without_declared_timing(item) for item in value]
    return value


def _compare_p1(
    *,
    arguments: argparse.Namespace,
    inputs: dict[str, Path],
    captures: dict[str, dict[str, object]],
    catalog_path: Path,
) -> None:
    catalog_sha256 = _sha256(catalog_path)
    catalog_by_profile = {
        profile: _p1_catalog_facts(catalog_path, profile)
        for profile in ("p1_vector_bge", "p1_hybrid_bge")
    }
    if (
        catalog_by_profile["p1_vector_bge"]
        != catalog_by_profile["p1_hybrid_bge"]
    ):
        raise ValueError("P1 vector and hybrid catalog case sets differ")
    validated = {}
    for slot, capture in captures.items():
        profile = capture["profile"]
        facts, fixture_case_count = catalog_by_profile[profile]
        validated[slot] = _validate_p1_report(
            capture,
            slot,
            catalog_sha256,
            facts,
            fixture_case_count,
        )

    vector_repeat_mismatches = []
    hybrid_gate_mismatches = []
    hybrid_raw_planner_text_drift = []
    online_numeric_drift = []
    for side in ("baseline", "candidate"):
        vector_reports = [
            validated[f"vector-{side}-r{repetition}"][0]
            for repetition in (1, 2)
        ]
        if _online_stable_projection(
            vector_reports[0]
        ) != _online_stable_projection(vector_reports[1]):
            vector_repeat_mismatches.append(f"vector-{side}")
        elif _online_score_observations(
            vector_reports[0]
        ) != _online_score_observations(vector_reports[1]):
            online_numeric_drift.append(f"vector-{side}")

        hybrid_runs = [
            validated[f"hybrid-{side}-r{repetition}"]
            for repetition in (1, 2)
        ]
        hybrid_projections = [
            {
                "counts": _p1_counts(report),
                "cases": {
                    f"{repo}:{case}": row
                    for (repo, case), row in sorted(cases.items())
                },
            }
            for report, cases in hybrid_runs
        ]
        if hybrid_projections[0] != hybrid_projections[1]:
            hybrid_gate_mismatches.append(f"hybrid-{side}")
        if _online_score_observations(
            hybrid_runs[0][0]
        ) != _online_score_observations(hybrid_runs[1][0]):
            online_numeric_drift.append(f"hybrid-{side}")
        first_cases = {
            (case["repo_key"], case["case_id"]): case
            for case in hybrid_runs[0][0]["cases"]
        }
        second_cases = {
            (case["repo_key"], case["case_id"]): case
            for case in hybrid_runs[1][0]["cases"]
        }
        for key in sorted(first_cases):
            if _p1_without_declared_timing(
                first_cases[key]["planner"]
            ) != _p1_without_declared_timing(second_cases[key]["planner"]):
                hybrid_raw_planner_text_drift.append(
                    f"{side}:{key[0]}:{key[1]}"
                )

    provenance_mismatches = []
    for profile_name in ("vector", "hybrid"):
        reference_report = validated[f"{profile_name}-baseline-r1"][0]
        for side in ("baseline", "candidate"):
            for repetition in (1, 2):
                slot = f"{profile_name}-{side}-r{repetition}"
                report = validated[slot][0]
                for field in ("config", "planner"):
                    if report[field] != reference_report[field]:
                        provenance_mismatches.append(f"{slot}:{field}")
    reference_tool_name = validated["vector-baseline-r1"][0]["tool"]["name"]
    for slot, (report, _cases) in validated.items():
        if report["tool"]["name"] != reference_tool_name:
            provenance_mismatches.append(f"{slot}:tool.name")

    owner_key = ("java_spring_mini", "audit-status-literal")
    endpoint_key = ("java_spring_mini", "apply-audit-endpoint")
    profiles: dict[str, object] = {}
    all_cases = []
    for profile_name, profile in (
        ("vector", "p1_vector_bge"),
        ("hybrid", "p1_hybrid_bge"),
    ):
        baseline_reports = [
            validated[f"{profile_name}-baseline-r{repeat}"]
            for repeat in (1, 2)
        ]
        candidate_reports = [
            validated[f"{profile_name}-candidate-r{repeat}"]
            for repeat in (1, 2)
        ]
        baseline_owner_ranks = [
            cases[owner_key]["target_rank"] for _report, cases in baseline_reports
        ]
        candidate_owner_ranks = [
            cases[owner_key]["target_rank"] for _report, cases in candidate_reports
        ]
        profiles[profile] = {
            "baseline_counts": _p1_counts(baseline_reports[0][0]),
            "candidate_counts": _p1_counts(candidate_reports[0][0]),
            "required_case_denominator": 7,
            "baseline_owner_ranks": baseline_owner_ranks,
            "candidate_owner_ranks": candidate_owner_ranks,
            "owner_rank_threshold": 3,
        }
        all_cases.extend(
            (profile_name, side, repetition, cases)
            for side, reports in (
                ("baseline", baseline_reports),
                ("candidate", candidate_reports),
            )
            for repetition, (_report, cases) in enumerate(reports, start=1)
        )

    no_fallback = all(
        not row["embedding_fallback"]
        for _profile, _side, _repeat, cases in all_cases
        for row in cases.values()
    )
    counts_complete = all(
        report["aggregate"]["selected"] == 7
        and report["aggregate"]["executed"] == 7
        and report["aggregate"]["skipped"] == 0
        and report["aggregate"]["errors"] == 0
        for report, _cases in validated.values()
    )
    baseline_diagnostic = all(
        profiles[profile]["baseline_counts"]["passed"] == 6
        and profiles[profile]["baseline_counts"]["failed"] == 1
        and all(
            rank is not None and 3 < rank <= 12
            for rank in profiles[profile]["baseline_owner_ranks"]
        )
        for profile in profiles
    )
    candidate_closure = all(
        profiles[profile]["candidate_counts"]["passed"] == 7
        and profiles[profile]["candidate_counts"]["failed"] == 0
        and all(
            rank is not None and rank <= 3
            for rank in profiles[profile]["candidate_owner_ranks"]
        )
        for profile in profiles
    )
    protected_cases_pass = all(
        row["status"] == "pass"
        for _profile, _side, _repeat, cases in all_cases
        for key, row in cases.items()
        if key != owner_key
    )
    endpoint_gate = all(
        cases[endpoint_key]["status"] == "pass"
        for _profile, side, _repeat, cases in all_cases
        if side == "candidate"
    )
    # The focused pair contract's observable planner/fallback clauses.
    vector_behavior = all(
        row["planner_status"] == "disabled"
        and row["variant_retrieval_status"] == "original_only"
        for profile, _side, _repeat, cases in all_cases
        if profile == "vector"
        for row in cases.values()
    )
    cross_language_keys = {
        ("cross_language_dashboard", "dashboard-cross-language"),
        ("embedding_ab", "access-validation-cross-language"),
        ("embedding_ab", "blacklist-management-cross-language"),
    }
    hybrid_behavior = all(
        cases[key]["planner_status"] == "ok"
        and cases[key]["variant_retrieval_status"] == "hybrid"
        for profile, _side, _repeat, cases in all_cases
        if profile == "hybrid"
        for key in cross_language_keys
    )
    pair_metrics = {}
    for repetition in (1, 2):
        candidate_vector = validated[f"vector-candidate-r{repetition}"][0]
        candidate_hybrid = validated[f"hybrid-candidate-r{repetition}"][0]
        pair_metrics[f"repeat_{repetition}"] = {
            metric: {
                "vector": _p1_metric(candidate_vector, metric, field),
                "hybrid": _p1_metric(candidate_hybrid, metric, field),
                "tolerance": (
                    P1_HYBRID_MRR_TOP3_TOLERANCE
                    if metric == "mrr"
                    else 0.0
                ),
                "threshold": (
                    "hybrid>=vector-1/42"
                    if metric == "mrr"
                    else "hybrid>=vector"
                ),
            }
            for metric, field in (
                ("mrr", "mean"),
                ("recall_at_5", "mean"),
                ("entrypoint_top3", "rate"),
            )
        }
    pair_metrics_non_decreasing = all(
        row["hybrid"] >= row["vector"] - row["tolerance"] - 1e-12
        for repetition in pair_metrics.values()
        for row in repetition.values()
    )
    gates = {
        "vector_repeat_determinism": not vector_repeat_mismatches,
        "hybrid_gate_input_determinism": not hybrid_gate_mismatches,
        "repeat_determinism": (
            not vector_repeat_mismatches and not hybrid_gate_mismatches
        ),
        "provenance_stable": not provenance_mismatches,
        "selected_and_executed_counts": counts_complete,
        "no_fallback_error_or_skip": no_fallback and counts_complete,
        "baseline_diagnostic": baseline_diagnostic,
        "candidate_seven_of_seven_owner_top3": candidate_closure,
        "protected_cases_pass": protected_cases_pass,
        "endpoint_gate_pass": endpoint_gate,
        "profile_behavior": vector_behavior and hybrid_behavior,
        "hybrid_metrics_not_below_vector": pair_metrics_non_decreasing,
    }
    if (
        not gates["vector_repeat_determinism"]
        or not gates["provenance_stable"]
    ):
        disposition = "reject"
    elif not gates["hybrid_gate_input_determinism"]:
        disposition = "blocked"
    elif all(gates.values()):
        disposition = "ship"
    else:
        disposition = "reject"
    output = {
        "schema_version": 1,
        "gate_kind": "p1",
        "attempt_id": arguments.attempt_id,
        "catalog": {
            "filename": catalog_path.name,
            "sha256": catalog_sha256,
        },
        "inputs": {
            slot: {"filename": path.name, "sha256": _sha256(path)}
            for slot, path in inputs.items()
        },
        "profiles": profiles,
        "pair_metrics": pair_metrics,
        "provenance_mismatches": provenance_mismatches,
        "hybrid_raw_planner_text_drift": hybrid_raw_planner_text_drift,
        "online_numeric_drift": online_numeric_drift,
        "repeat_determinism": {
            "vector_non_timing_mismatches": vector_repeat_mismatches,
            "hybrid_gate_input_mismatches": hybrid_gate_mismatches,
            "threshold": 0,
        },
        "gates": gates,
        "disposition": disposition,
    }
    _write_new(Path(arguments.output).resolve(), _canonical_json(output))


def main(argv: Sequence[str] | None = None) -> int:
    effective_argv = list(sys.argv[1:] if argv is None else argv)
    if effective_argv and effective_argv[0] == "_capture-p1-child":
        return _capture_p1_child(effective_argv[1:])
    if effective_argv and effective_argv[0] == "_capture-p8-child":
        return _capture_p8_child(effective_argv[1:])
    arguments = _build_parser().parse_args(effective_argv)
    if arguments.command == "capture-p1":
        _capture_p1(arguments)
    elif arguments.command == "capture-p8":
        _capture_p8(arguments)
    elif arguments.command == "compare-p8":
        inputs = _comparison_paths(arguments, P8_CAPTURE_SLOTS)
        captures = _load_comparison_captures(
            inputs=inputs,
            attempt_id=arguments.attempt_id,
            kind="p8",
        )
        inventory_path = Path(arguments.eligible_inventory).resolve()
        inventory = _load_eligible_inventory(inventory_path)
        eligible = _validate_and_derive_p8_eligibility(inventory, captures)
        _compare_p8(
            arguments=arguments,
            inputs=inputs,
            captures=captures,
            inventory_path=inventory_path,
            inventory=inventory,
            eligible=eligible,
        )
    elif arguments.command == "compare-p1":
        inputs = _comparison_paths(arguments, P1_CAPTURE_SLOTS)
        captures = _load_comparison_captures(
            inputs=inputs,
            attempt_id=arguments.attempt_id,
            kind="p1",
        )
        catalog_path = Path(arguments.catalog).resolve()
        _validate_p1_catalog(captures, catalog_path)
        _compare_p1(
            arguments=arguments,
            inputs=inputs,
            captures=captures,
            catalog_path=catalog_path,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
