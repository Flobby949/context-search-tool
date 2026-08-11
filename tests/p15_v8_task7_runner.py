from __future__ import annotations

import argparse
import ast
import copy
import json
import subprocess
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Callable

import p15_v8_closure_evaluator as closure

from context_search_tool.config import (
    ToolConfig,
    read_config,
    replace_embedding_config,
    replace_query_planner_config,
)
from context_search_tool.dependency_replay import (
    capture_query_repository_state,
    replay_dependency_state,
)
from context_search_tool.indexer import index_repository


ATTEMPT_ID = "p15-v8-attempt-003"
REPOSITORIES = {
    "fresh-r01": {
        "directory": "asgiref",
        "identity": "django/asgiref",
        "url": "https://github.com/django/asgiref.git",
        "commit": "a7cc976fe8a2395307834bc4aebb462b9f379d55",
        "candidate_blind_rank": 3,
    },
    "fresh-r02": {
        "directory": "structlog",
        "identity": "hynek/structlog",
        "url": "https://github.com/hynek/structlog.git",
        "commit": "bf3cfd017dcccf8d97fef0c4dbdaf74b2224c470",
        "candidate_blind_rank": 4,
    },
    "heldout-r01": {
        "directory": "flake8",
        "identity": "pycqa/flake8",
        "url": "https://github.com/pycqa/flake8.git",
        "commit": "01b972636056a0ed581db62e260ef8df1ce470de",
        "candidate_blind_rank": 6,
    },
}
PROMOTION_MODES = closure.PROMOTION_MODES
NO_OP_STATUSES = closure.NO_OP_STATUSES


@dataclass(frozen=True)
class EligibleCase:
    source_path: str
    source_module: str
    source_symbol: str
    source_line: int
    target_path: str
    imported_symbol: str
    import_line: int
    relevant_paths: tuple[str, ...]


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    return value


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
        + "\n",
        encoding="utf-8",
    )


def sha256_file(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _tracked_inventory(repo: Path) -> list[dict[str, str]]:
    paths = [line for line in _git(repo, "ls-files").splitlines() if line]
    return [
        {"path": path, "sha256": sha256_file(repo / path)}
        for path in sorted(paths)
    ]


def repository_identity(repo: Path, spec: dict[str, Any]) -> dict[str, Any]:
    observed_commit = _git(repo, "rev-parse", "HEAD")
    if observed_commit != spec["commit"]:
        raise ValueError(f"{spec['identity']} commit mismatch")
    if _git(repo, "status", "--short", "--untracked-files=no"):
        raise ValueError(f"{spec['identity']} tracked checkout is dirty")
    inventory = _tracked_inventory(repo)
    return {
        "identity": spec["identity"],
        "url": spec["url"],
        "commit": observed_commit,
        "candidate_blind_rank": spec["candidate_blind_rank"],
        "tracked_inventory_sha256": closure.canonical_sha256(inventory),
    }


def _module_map(repo: Path) -> dict[str, str]:
    modules: dict[str, str] = {}
    for path in sorted(repo.rglob("*.py")):
        if ".git" in path.parts:
            continue
        relative = path.relative_to(repo)
        parts = list(relative.with_suffix("").parts)
        package_index = next(
            (
                index
                for index in range(len(parts) - 1)
                if (repo.joinpath(*parts[: index + 1]) / "__init__.py").is_file()
            ),
            None,
        )
        if package_index is None:
            continue
        module_parts = parts[package_index:]
        if module_parts[-1] == "__init__":
            module_parts = module_parts[:-1]
        modules[".".join(module_parts)] = relative.as_posix()
    return modules


def _resolved_import_module(
    current_module: str,
    source_path: str,
    node: ast.ImportFrom,
) -> str:
    if not node.level:
        return node.module or ""
    package = current_module.split(".")
    if not source_path.endswith("/__init__.py"):
        package = package[:-1]
    base = package[: max(0, len(package) - node.level + 1)]
    if node.module:
        base.extend(node.module.split("."))
    return ".".join(base)


def _module_scope_import_from_nodes(tree: ast.Module) -> list[ast.ImportFrom]:
    imports: list[ast.ImportFrom] = []
    pending = list(tree.body)
    while pending:
        node = pending.pop()
        if isinstance(node, ast.ImportFrom):
            imports.append(node)
            continue
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        pending.extend(ast.iter_child_nodes(node))
    return sorted(imports, key=lambda node: (node.lineno, node.col_offset))


def derive_eligible_cases(repo: Path) -> list[EligibleCase]:
    modules = _module_map(repo)
    candidates: list[EligibleCase] = []
    for module, source_path in sorted(modules.items(), key=lambda item: item[1]):
        if "tests" in Path(source_path).parts:
            continue
        try:
            tree = ast.parse((repo / source_path).read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        def resolve_imports(
            nodes: list[ast.ImportFrom],
        ) -> list[tuple[str, str, str, int]]:
            resolved: list[tuple[str, str, str, int]] = []
            for node in nodes:
                if any(alias.name == "*" for alias in node.names):
                    continue
                imported_module = _resolved_import_module(module, source_path, node)
                for alias in node.names:
                    target_path = modules.get(f"{imported_module}.{alias.name}")
                    if target_path is None:
                        target_path = modules.get(imported_module)
                    if target_path is not None and target_path != source_path:
                        resolved.append(
                            (
                                alias.asname or alias.name,
                                alias.name,
                                target_path,
                                node.lineno,
                            )
                        )
            return resolved

        imports = resolve_imports(_module_scope_import_from_nodes(tree))
        all_imports = resolve_imports(
            sorted(
                (
                    node
                    for node in ast.walk(tree)
                    if isinstance(node, ast.ImportFrom)
                ),
                key=lambda node: (node.lineno, node.col_offset),
            )
        )
        for owner in tree.body:
            if not isinstance(owner, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            loaded_names = {
                node.id
                for node in ast.walk(owner)
                if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
            }
            used = [item for item in imports if item[0] in loaded_names]
            all_used = [item for item in all_imports if item[0] in loaded_names]
            relevant = tuple(
                sorted({source_path, *(item[2] for item in all_used)})
            )
            for _bound, imported_symbol, target_path, import_line in used:
                candidates.append(
                    EligibleCase(
                        source_path=source_path,
                        source_module=module,
                        source_symbol=owner.name,
                        source_line=owner.lineno,
                        target_path=target_path,
                        imported_symbol=imported_symbol,
                        import_line=import_line,
                        relevant_paths=relevant,
                    )
                )
    unique: list[EligibleCase] = []
    seen_owners: set[tuple[str, str]] = set()
    for item in sorted(
        candidates,
        key=lambda item: (
            item.source_path,
            item.source_line,
            item.source_symbol,
            item.target_path,
            item.import_line,
            item.imported_symbol,
        ),
    ):
        key = (item.source_path, item.source_symbol)
        if key not in seen_owners:
            seen_owners.add(key)
            unique.append(item)

    selected: list[EligibleCase] = []
    selected_targets: set[str] = set()
    for item in unique:
        if item.target_path not in selected_targets:
            selected.append(item)
            selected_targets.add(item.target_path)
    selected.extend(item for item in unique if item not in selected)
    return selected


def _case_payload(slot: str, ordinal: int, item: EligibleCase) -> dict[str, Any]:
    query = (
        f"Within {item.source_module}, which internal imported dependency is used "
        f"by {item.source_symbol} to carry out its behavior?"
    )
    return {
        "case_id": f"{slot}-case-{ordinal}",
        "repository_slot": slot,
        "case_ordinal": ordinal,
        "query": query,
        "cohort": (
            "held_out"
            if slot.startswith("heldout-")
            else "guard"
            if ordinal <= 2
            else "efficacy"
        ),
        "gold_target_path": item.target_path,
        "required_paths": [item.source_path],
        "relevant_paths": list(item.relevant_paths),
        "candidate_blind_target_missing": slot.startswith("heldout-"),
        "replacement": False,
        "selection_proof": {
            "algorithm": "stdlib_ast_module_gold_all_import_relevance_unique_owner_v3",
            "source_path": item.source_path,
            "source_symbol": item.source_symbol,
            "source_line": item.source_line,
            "import_line": item.import_line,
        },
    }


def seal_corpus(
    name: str,
    slots: list[str],
    ordinals: list[int],
    repos_root: Path,
) -> dict[str, Any]:
    repositories = []
    cases = []
    for slot in slots:
        spec = REPOSITORIES[slot]
        repo = repos_root / spec["directory"]
        identity = repository_identity(repo, spec)
        eligible = derive_eligible_cases(repo)
        if len(eligible) < len(ordinals):
            raise ValueError(f"{slot} has an incomplete candidate-blind case pool")
        identity_sha256 = closure.canonical_sha256(identity)
        repositories.append(
            {
                "repository_slot": slot,
                "repository_identity": identity,
                "repository_identity_sha256": identity_sha256,
            }
        )
        for ordinal, item in zip(ordinals, eligible, strict=False):
            cases.append(_case_payload(slot, ordinal, item))
    return {
        "schema_version": "p15-v8-candidate-blind-corpus-v3",
        "corpus": name,
        "selection_before_online": True,
        "candidate_blind": True,
        "repositories": repositories,
        "cases": cases,
    }


def _case_projection(
    case: dict[str, Any], identity_sha256: str
) -> dict[str, Any]:
    core = {
        "repository_slot": case["repository_slot"],
        "repository_identity_sha256": identity_sha256,
        "case_ordinal": case["case_ordinal"],
        "case_id": case["case_id"],
        "query_sha256": closure.canonical_sha256(case["query"]),
        "gold_sha256": closure.canonical_sha256(case["gold_target_path"]),
        "relevant_sha256": closure.canonical_sha256(sorted(case["relevant_paths"])),
        "required_sha256": closure.canonical_sha256(sorted(case["required_paths"])),
    }
    return {**core, "projection_sha256": closure.canonical_sha256(core)}


def manifest_corpus_binding(
    name: str, payload: dict[str, Any], contract: dict[str, Any]
) -> dict[str, Any]:
    identities = {
        item["repository_slot"]: item["repository_identity_sha256"]
        for item in payload["repositories"]
    }
    universe = [
        {
            "repository_slot": slot,
            "repository_identity_sha256": identities[slot],
        }
        for slot in contract["schedule"][name]["repository_slots"]
    ]
    projections = [
        _case_projection(case, identities[case["repository_slot"]])
        for case in payload["cases"]
    ]
    universe_sha256 = closure.canonical_sha256(universe)
    projection_sha256 = closure.canonical_sha256(projections)
    payload_sha256 = closure.canonical_sha256(
        {
            "repository_universe_sha256": universe_sha256,
            "case_projection_sha256": projection_sha256,
        }
    )
    public_seal_sha256 = closure.canonical_sha256(
        {
            "corpus": name,
            "payload_sha256": payload_sha256,
            "schedule_sha256": contract["schedule"][name]["expanded_sha256"],
        }
    )
    return {
        "repository_universe": universe,
        "repository_universe_sha256": universe_sha256,
        "case_projections": projections,
        "case_projection_sha256": projection_sha256,
        "payload_sha256": payload_sha256,
        "public_seal_sha256": public_seal_sha256,
    }


def create_execution_manifest(
    contract: dict[str, Any],
    approval: dict[str, Any],
    fresh_payload: dict[str, Any],
    heldout_payload: dict[str, Any],
) -> dict[str, Any]:
    runner = contract["verification"]["runner"]
    manifest = {
        "schema_version": "p15-v8-sealed-execution-manifest-v1",
        "sealed": True,
        "attempt_id": contract["attempt_id"],
        "candidate_commit": contract["candidate"]["commit"],
        "candidate_tree": contract["candidate"]["tree"],
        "contract_projection_sha256": closure.canonical_sha256(
            closure.contract_approval_projection(contract)
        ),
        "approval_receipt_sha256": closure.canonical_sha256(approval),
        "runner_identity": closure.canonical_sha256(runner),
        "corpora": {
            "fresh": manifest_corpus_binding("fresh", fresh_payload, contract),
            "held_out": manifest_corpus_binding(
                "held_out", heldout_payload, contract
            ),
        },
        "schedule_sha256": {
            name: contract["schedule"][name]["expanded_sha256"]
            for name in ("fresh", "held_out")
        },
    }
    closure.validate_authorization(contract, approval, manifest)
    return manifest


def task7_config(repo: Path) -> ToolConfig:
    config = read_config(repo)
    planner = replace_query_planner_config(
        config.query_planner,
        enabled=True,
        provider="openai-compatible",
        model="Qwen/Qwen2.5-14B-Instruct",
        base_url="https://api.siliconflow.cn/v1",
        use_system_proxy=False,
        send_repo_profile=False,
        timeout_seconds=60,
    )
    embedding = replace_embedding_config(
        config.embedding,
        provider="openai-compatible",
        model="Pro/BAAI/bge-m3",
        dimensions=1024,
        base_url="https://api.siliconflow.cn/v1",
    )
    retrieval = replace(
        config.retrieval,
        semantic_top_k=80,
        lexical_top_k=80,
        final_top_k=12,
        consume_dependency_hints=False,
    )
    return replace(
        config,
        query_planner=planner,
        embedding=embedding,
        retrieval=retrieval,
    )


def _promotion_report(observation: dict[str, object]) -> dict[str, Any]:
    modes = {
        "exact_source_hint": int(observation["exact_source_hint_promoted"]),
        "exact_target_hint": int(observation["exact_target_hint_promoted"]),
        "semantic_pair_fallback": int(
            observation["semantic_pair_fallback_promoted"]
        ),
    }
    status = str(observation["status"])
    statuses = {item: 0 for item in NO_OP_STATUSES}
    if status != "promoted":
        if status not in statuses:
            raise ValueError(f"unknown promotion status: {status}")
        statuses[status] = 1
    return {
        "trace_schema_version": 1,
        "stage": "dependency_promotion",
        "mode_counts": modes,
        "status_counts": statuses,
        "promoted_path_count": int(observation["promoted_path_count"]),
    }


def _rows(replayed: dict[str, Any]) -> list[dict[str, Any]]:
    projected = []
    for row in replayed["top12"]:
        item: dict[str, Any] = {"path": row["path"]}
        marker = row.get("planner_dependency_hint_promotion", 0)
        if marker > 0:
            item["planner_dependency_hint_promotion"] = marker
            item["closed_exact_witness"] = {
                key: row["closed_exact_witness"][key]
                for key in closure.WITNESS_FIELDS
            }
        projected.append(item)
    return projected


def _replay(
    state: dict[str, Any],
    *,
    enabled: bool,
    replay_id: str,
    replay_fn: Callable[..., dict[str, Any]] = replay_dependency_state,
) -> dict[str, Any]:
    observations: list[dict[str, object]] = []
    started = time.perf_counter()
    replayed = replay_fn(
        state,
        consume_dependency_hints=enabled,
        promotion_observer=observations.append,
    )
    elapsed_ms = (time.perf_counter() - started) * 1000
    if len(observations) != 1:
        raise ValueError("replay did not emit exactly one promotion decision")
    rows = _rows(replayed)
    if len(rows) != 12:
        raise ValueError("replay did not produce the frozen Top12")
    return {
        "replay_id": replay_id,
        "top12": rows,
        "rank1_path": rows[0]["path"],
        "local_latency_ms": elapsed_ms,
        "promotion_report": _promotion_report(observations[0]),
    }


def _capture_projection(state: dict[str, Any]) -> dict[str, str]:
    return {
        "validated_or_fallback_plan_sha256": closure.canonical_sha256(state["plan"]),
        "embedding_sha256": state["query_embedding_sha256"],
        "base_roster_sha256": closure.canonical_sha256(state["base_roster"]),
        "shared_state_sha256": state["canonical_sha256"],
    }


def collect_case(
    repo: Path,
    case: dict[str, Any],
    config: ToolConfig,
    capture_fn: Callable[..., Any] = capture_query_repository_state,
    replay_fn: Callable[..., dict[str, Any]] = replay_dependency_state,
) -> dict[str, Any]:
    result = {key: copy.deepcopy(value) for key, value in case.items() if key != "selection_proof"}
    samples = []
    slot = case["repository_slot"]
    ordinal = case["case_ordinal"]
    for sample_ordinal in (1, 2):
        captured = capture_fn(repo, case["query"], config)
        state = captured.replay_state
        kinds = [item.get("kind") for item in captured.provider_observations]
        if kinds.count("planner") != 1 or kinds.count("embedding") < 1:
            raise ValueError("online capture provider observations are incomplete")
        arms = {
            "control": {
                "consume_dependency_hints": False,
                "capture": _capture_projection(state),
                "additional_planner_requests": 0,
                "additional_embedding_requests": 0,
                "replays": [],
            },
            "treatment": {
                "consume_dependency_hints": True,
                "capture": _capture_projection(state),
                "additional_planner_requests": 0,
                "additional_embedding_requests": 0,
                "replays": [],
            },
        }
        order = (
            ("control", "control", 1),
            ("control", "control", 2),
            ("treatment", "treatment", 1),
            ("treatment", "treatment", 2),
        )
        if sample_ordinal == 2:
            order = order[2:] + order[:2]
        for arm_key, arm_label, replay_ordinal in order:
            replay_id = (
                f"{slot}-c{ordinal:02d}-s{sample_ordinal}-"
                f"{arm_label}-r{replay_ordinal}"
            )
            arms[arm_key]["replays"].append(
                _replay(
                    state,
                    enabled=arm_key == "treatment",
                    replay_id=replay_id,
                    replay_fn=replay_fn,
                )
            )
        samples.append(
            {
                "sample_ordinal": sample_ordinal,
                "plan_status": state["plan"]["status"],
                **arms,
            }
        )
    result["samples"] = samples
    return result


def collect_corpus(
    name: str,
    payload: dict[str, Any],
    binding: dict[str, Any],
    contract: dict[str, Any],
    repos_root: Path,
) -> dict[str, Any]:
    identities = {
        item["repository_slot"]: item for item in payload["repositories"]
    }
    cases_by_slot: dict[str, list[dict[str, Any]]] = {}
    for case in payload["cases"]:
        cases_by_slot.setdefault(case["repository_slot"], []).append(case)
    collected = []
    for slot in contract["schedule"][name]["repository_slots"]:
        spec = REPOSITORIES[slot]
        repo = repos_root / spec["directory"]
        observed = repository_identity(repo, spec)
        if closure.canonical_sha256(observed) != identities[slot]["repository_identity_sha256"]:
            raise ValueError(f"{slot} repository changed after seal")
        config = task7_config(repo)
        if config.query_planner.api_key is None or config.embedding.api_key is None:
            raise ValueError("configured online provider key is unavailable")
        index_repository(repo, config)
        collected.extend(
            collect_case(repo, case, config) for case in cases_by_slot[slot]
        )
    schedule = closure._expand_schedule(contract["schedule"][name])
    return {
        "corpus": name,
        "corpus_seal_sha256": binding["public_seal_sha256"],
        "payload_sha256": binding["payload_sha256"],
        "repository_universe": binding["repository_universe"],
        "result_dependent_append": False,
        "retry_or_replacement": False,
        "retrieval_limits": {
            "top_k": contract["retrieval"]["top_k"],
            "budgets": contract["retrieval"]["budgets"],
        },
        "schedule": {
            "expanded_schedule": schedule,
            "expanded_sha256": closure.canonical_sha256(schedule),
        },
        "provider_status": "complete",
        "sealed_input_complete": True,
        "opened": True,
        "cases": collected,
    }


def seal_command(args: argparse.Namespace) -> None:
    contract = load_json(args.contract)
    approval = load_json(args.approval)
    if contract["attempt_id"] != ATTEMPT_ID:
        raise ValueError("runner attempt identity mismatch")
    fresh = seal_corpus(
        "fresh",
        contract["schedule"]["fresh"]["repository_slots"],
        contract["schedule"]["fresh"]["case_ordinals"],
        args.repos_root,
    )
    heldout = seal_corpus(
        "held_out",
        contract["schedule"]["held_out"]["repository_slots"],
        contract["schedule"]["held_out"]["case_ordinals"],
        args.repos_root,
    )
    manifest = create_execution_manifest(contract, approval, fresh, heldout)
    write_json(args.output_dir / "fresh-sealed.json", fresh)
    write_json(args.output_dir / "heldout-sealed.json", heldout)
    write_json(args.output_dir / "execution-manifest.json", manifest)


def collect_command(args: argparse.Namespace) -> None:
    contract = load_json(args.contract)
    approval = load_json(args.approval)
    manifest = load_json(args.manifest)
    closure.validate_authorization(contract, approval, manifest)
    payload = load_json(args.payload)
    binding = manifest["corpora"][args.corpus]
    evidence = collect_corpus(
        args.corpus, payload, binding, contract, args.repos_root
    )
    write_json(args.output, evidence)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="P15 v8 Task7 frozen runner")
    commands = result.add_subparsers(dest="command", required=True)
    seal = commands.add_parser("seal")
    seal.add_argument("--contract", type=Path, required=True)
    seal.add_argument("--approval", type=Path, required=True)
    seal.add_argument("--repos-root", type=Path, required=True)
    seal.add_argument("--output-dir", type=Path, required=True)
    seal.set_defaults(handler=seal_command)
    collect = commands.add_parser("collect")
    collect.add_argument("--corpus", choices=("fresh", "held_out"), required=True)
    collect.add_argument("--contract", type=Path, required=True)
    collect.add_argument("--approval", type=Path, required=True)
    collect.add_argument("--manifest", type=Path, required=True)
    collect.add_argument("--payload", type=Path, required=True)
    collect.add_argument("--repos-root", type=Path, required=True)
    collect.add_argument("--output", type=Path, required=True)
    collect.set_defaults(handler=collect_command)
    return result


def main() -> int:
    args = parser().parse_args()
    args.handler(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
