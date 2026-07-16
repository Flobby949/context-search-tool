from __future__ import annotations

import argparse
import ast
import json
import tempfile
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from retrieval_core_characterization import (
    BASELINE_PATH,
    DOCUMENTATION_BASELINE,
    FULL_STAGE_LEDGER_KEYS,
    IMPLEMENTATION_COMMIT,
    MIGRATION_LEDGER_PATH,
    ROOT,
    assert_clean_environment,
    assert_protected_source_identity,
    baseline_projection,
    characterization_input_identity,
    load_characterization_cases,
    parse_junit_evidence,
    reject_sensitive_manifest,
    runtime_identity,
)


SUPPORTED_FACADE = {
    "QueryBundle",
    "TracedQueryBundle",
    "query_repository",
    "trace_repository",
    "evidence_anchor_top_k",
    "normalize_score",
    "MAX_EXPANSION_DEPTH",
    "MAX_EXPANSION_CANDIDATES",
}

MIGRATION_OWNERS: dict[str, tuple[str, int]] = {
    "_RankedChunk": ("context_search_tool.retrieval_core.types._RankedChunk", 2),
    "_ExpandedResult": (
        "context_search_tool.retrieval_core.types._ExpandedResult",
        2,
    ),
    "_GenericFileRole": (
        "context_search_tool.retrieval_core.file_roles._GenericFileRole",
        2,
    ),
    "_dedupe": ("context_search_tool.retrieval_core.ordering.dedupe_lowered", 2),
    "_ordered_unique": (
        "context_search_tool.retrieval_core.ordering.ordered_unique_preserving_case",
        2,
    ),
    "_RERANK_SORT_DECIMALS": (
        "context_search_tool.retrieval_core.ordering.RERANK_SORT_DECIMALS",
        2,
    ),
    "_bounded_score": (
        "context_search_tool.retrieval_core.evidence_merge.bounded_score",
        2,
    ),
    "_merge_score_parts": (
        "context_search_tool.retrieval_core.evidence_merge.merge_score_parts",
        2,
    ),
    "_merge_semantic_matches": (
        "context_search_tool.retrieval_core.evidence_merge.merge_semantic_matches",
        2,
    ),
    "tokenize_query": ("context_search_tool.tokenizer.tokenize_query", 2),
    "expand_lines": ("context_search_tool.chunker.expand_lines", 2),
    "SQLiteStore": ("context_search_tool.sqlite_store.SQLiteStore", 2),
    "_semantic_candidates": (
        "context_search_tool.retrieval_core.candidates.semantic_candidates",
        3,
    ),
    "_lexical_candidates": (
        "context_search_tool.retrieval_core.candidates.lexical_candidates",
        3,
    ),
    "_direct_text_candidates": (
        "context_search_tool.retrieval_core.candidates.direct_text_candidates",
        3,
    ),
    "_direct_text_probes": (
        "context_search_tool.retrieval_core.candidates.direct_text_probes",
        3,
    ),
    "_signal_candidates": (
        "context_search_tool.retrieval_core.candidates.signal_candidates",
        3,
    ),
    "_planner_hint_candidates": (
        "context_search_tool.retrieval_core.candidates.planner_hint_candidates",
        3,
    ),
    "_merge_candidates": (
        "context_search_tool.retrieval_core.candidates.merge_candidates",
        3,
    ),
    "_initial_candidates": (
        "context_search_tool.retrieval.query_repository",
        3,
    ),
    "_normalized_score_parts": (
        "context_search_tool.retrieval_core.candidates._normalized_score_parts",
        3,
    ),
    "NumpyVectorStore": (
        "context_search_tool.retrieval_core.candidates.NumpyVectorStore",
        3,
    ),
    "provider_from_config": (
        "context_search_tool.retrieval_core.candidates.provider_from_config",
        3,
    ),
    "_anchor_expansion_candidates": (
        "context_search_tool.retrieval_core.expansion.anchor_candidates",
        4,
    ),
    "_relation_expansion_candidates": (
        "context_search_tool.retrieval_core.expansion.relation_candidates",
        4,
    ),
    "_RELATION_SCORE_DECAY": (
        "context_search_tool.retrieval_core.expansion._RELATION_SCORE_DECAY",
        4,
    ),
    "__name__": ("context_search_tool.retrieval_core.expansion.logger.name", 4),
    "_rank_chunks": ("context_search_tool.retrieval_core.ranking.rank_chunks", 5),
    "_apply_frontend_import_cohort_rerank": (
        "context_search_tool.retrieval_core.ranking.apply_frontend_import_cohort_rerank",
        5,
    ),
    "_ChunkRole": ("context_search_tool.retrieval_core.ranking._ChunkRole", 5),
    "_SpringPathImplementor": (
        "context_search_tool.retrieval_core.ranking._SpringPathImplementor",
        5,
    ),
    "_ranked_chunk_sort_key": (
        "context_search_tool.retrieval_core.ranking._ranked_chunk_sort_key",
        5,
    ),
    "_with_effective_semantic": (
        "context_search_tool.retrieval_core.ranking._with_effective_semantic",
        5,
    ),
    "_combined_score": (
        "context_search_tool.retrieval_core.ranking._combined_score",
        5,
    ),
    "_has_original_direct_evidence": (
        "context_search_tool.retrieval_core.ranking._has_original_direct_evidence",
        5,
    ),
    "_has_planner_direct_evidence": (
        "context_search_tool.retrieval_core.ranking._has_planner_direct_evidence",
        5,
    ),
    "_has_strong_original_direct_evidence": (
        "context_search_tool.retrieval_core.ranking._has_strong_original_direct_evidence",
        5,
    ),
    "_has_weak_original_direct_evidence": (
        "context_search_tool.retrieval_core.ranking._has_weak_original_direct_evidence",
        5,
    ),
    "_evidence_class": (
        "context_search_tool.retrieval_core.ranking._evidence_class",
        5,
    ),
    "_evidence_priority": (
        "context_search_tool.retrieval_core.ranking._evidence_priority",
        5,
    ),
    "_generic_hint_penalty": (
        "context_search_tool.retrieval_core.ranking._generic_hint_penalty",
        5,
    ),
    "_rerank_score": (
        "context_search_tool.retrieval_core.ranking._rerank_score",
        5,
    ),
    "_is_planner_hint_only": (
        "context_search_tool.retrieval_core.ranking._is_planner_hint_only",
        5,
    ),
    "_route_score_parts": (
        "context_search_tool.retrieval_core.ranking._route_score_parts",
        5,
    ),
    "_chunk_role": ("context_search_tool.retrieval_core.ranking._chunk_role", 5),
    "_java_context_score_parts": (
        "context_search_tool.retrieval_core.ranking._java_context_score_parts",
        5,
    ),
    "_route_boost": ("context_search_tool.retrieval_core.ranking._route_boost", 5),
    "_reasons": ("context_search_tool.retrieval_core.ranking._reasons", 5),
    "_COHORT_MISMATCH_PENALTY": (
        "context_search_tool.retrieval_core.ranking._COHORT_MISMATCH_PENALTY",
        5,
    ),
    "_expand_ranked_chunks": (
        "context_search_tool.retrieval_core.context_expansion.expand_ranked_chunks",
        6,
    ),
    "_merge_overlapping_results": (
        "context_search_tool.retrieval_core.context_expansion._merge_overlapping_results",
        6,
    ),
    "_merge_expanded_result": (
        "context_search_tool.retrieval_core.context_expansion._merge_expanded_result",
        6,
    ),
    "_expanded_result_sort_key": (
        "context_search_tool.retrieval_core.context_expansion._expanded_result_sort_key",
        6,
    ),
    "_span_sources": (
        "context_search_tool.retrieval_core.context_expansion._span_sources",
        6,
    ),
    "_split_code_results_and_evidence_anchors": (
        "context_search_tool.retrieval_core.selection.split_results_and_anchors",
        7,
    ),
    "_evidence_anchor_kind": (
        "context_search_tool.retrieval_core.selection._evidence_anchor_kind",
        7,
    ),
    "_summarize_results": (
        "context_search_tool.retrieval_core.selection._summarize_results",
        7,
    ),
    "_FinalTraceInput": (
        "context_search_tool.retrieval_core.selection._FinalTraceInput",
        7,
    ),
    "_FinalTraceDecisions": (
        "context_search_tool.retrieval_core.selection._FinalTraceDecisions",
        7,
    ),
    "RetrievalTraceCollector": (
        "context_search_tool.retrieval_trace.RetrievalTraceCollector",
        8,
    ),
    "_finish_candidate_stage": (
        "context_search_tool.retrieval_core.tracing.finish_candidate_stage",
        8,
    ),
    "_trace_stage_start": (
        "context_search_tool.retrieval_core.tracing.start_stage",
        8,
    ),
    "_trace_candidate_observations": (
        "context_search_tool.retrieval_core.tracing._candidate_observations",
        8,
    ),
    "_trace_query": ("context_search_tool.retrieval_core.tracing._trace_query", 8),
    "_trace_ranked_observations": (
        "context_search_tool.retrieval_core.tracing._ranked_observations",
        8,
    ),
    "_trace_expanded_observations": (
        "context_search_tool.retrieval_core.tracing._expanded_observations",
        8,
    ),
    "_trace_final_selections": (
        "context_search_tool.retrieval_core.tracing._final_selections",
        8,
    ),
    "planner_from_config": (
        "context_search_tool.query_planner.planner_from_config",
        8,
    ),
    "build_query_variants": (
        "context_search_tool.query_planner.build_query_variants",
        8,
    ),
    "expand_query_plan_tokens": (
        "context_search_tool.query_planner.expand_query_plan_tokens",
        8,
    ),
    "planner_hint_tokens": (
        "context_search_tool.query_planner.planner_hint_tokens",
        8,
    ),
    "assert_manifest_compatible": (
        "context_search_tool.manifest.assert_manifest_compatible",
        8,
    ),
}


@dataclass(frozen=True)
class Reference:
    symbol: str
    file: str
    line: int
    kind: str
    category: str


def _module_aliases(tree: ast.Module) -> set[str]:
    aliases: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "context_search_tool.retrieval":
                    aliases.add(alias.asname or "retrieval")
        elif isinstance(node, ast.ImportFrom) and node.module == "context_search_tool":
            for alias in node.names:
                if alias.name == "retrieval":
                    aliases.add(alias.asname or alias.name)
    return aliases


def _call_name(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _call_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""


def _scan_file(path: Path) -> list[Reference]:
    relative = path.relative_to(ROOT).as_posix()
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    aliases = _module_aliases(tree)
    references: list[Reference] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.ImportFrom)
            and node.module == "context_search_tool.retrieval"
        ):
            for alias in node.names:
                references.append(
                    Reference(alias.name, relative, node.lineno, "import_from", "direct")
                )
        elif (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id in aliases
        ):
            references.append(
                Reference(node.attr, relative, node.lineno, "attribute", "direct")
            )
        elif isinstance(node, ast.Call):
            name = _call_name(node.func)
            if name.endswith(("monkeypatch.setattr", "patch.object")):
                if (
                    len(node.args) >= 2
                    and isinstance(node.args[0], ast.Name)
                    and node.args[0].id in aliases
                    and isinstance(node.args[1], ast.Constant)
                    and isinstance(node.args[1].value, str)
                ):
                    references.append(
                        Reference(
                            node.args[1].value,
                            relative,
                            node.lineno,
                            name.rsplit(".", 1)[-1],
                            "monkeypatch",
                        )
                    )
            elif name in {"getattr", "setattr"}:
                if (
                    len(node.args) >= 2
                    and isinstance(node.args[0], ast.Name)
                    and node.args[0].id in aliases
                    and isinstance(node.args[1], ast.Constant)
                    and isinstance(node.args[1].value, str)
                ):
                    references.append(
                        Reference(
                            node.args[1].value,
                            relative,
                            node.lineno,
                            name,
                            "monkeypatch",
                        )
                    )
    if relative == "scripts/profile_retrieval.py":
        references.extend(_profile_targets(tree, relative, aliases))
    return references


def _profile_targets(
    tree: ast.Module,
    relative: str,
    retrieval_aliases: set[str],
) -> list[Reference]:
    references: list[Reference] = []
    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        if not any(isinstance(target, ast.Name) and target.id == "RETRIEVAL_FUNCTIONS" for target in targets):
            continue
        value = node.value
        if not isinstance(value, (ast.List, ast.Tuple)):
            raise RuntimeError("RETRIEVAL_FUNCTIONS must be a literal list/tuple")
        for item in value.elts:
            symbol: str | None = None
            if isinstance(item, ast.Constant) and isinstance(item.value, str):
                symbol = item.value
            elif isinstance(item, ast.Tuple) and len(item.elts) == 3:
                _display, owner, attribute = item.elts
                owner_is_retrieval = (
                    isinstance(owner, ast.Name) and owner.id in retrieval_aliases
                ) or (
                    isinstance(owner, ast.Constant)
                    and owner.value == "context_search_tool.retrieval"
                )
                if (
                    owner_is_retrieval
                    and isinstance(attribute, ast.Constant)
                    and isinstance(attribute.value, str)
                ):
                    symbol = attribute.value
            if symbol is not None:
                references.append(
                    Reference(symbol, relative, item.lineno, "profiler_target", "profiler")
                )
    return references


def _runtime_name_load_lines(tree: ast.Module, symbol: str) -> list[int]:
    annotation_nodes: set[ast.AST] = set()
    type_alias = getattr(ast, "TypeAlias", ())
    for node in ast.walk(tree):
        annotations: list[ast.AST] = []
        if isinstance(node, ast.arg) and node.annotation is not None:
            annotations.append(node.annotation)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.returns is not None:
                annotations.append(node.returns)
            annotations.extend(getattr(node, "type_params", ()))
        elif isinstance(node, ast.AnnAssign):
            annotations.append(node.annotation)
        elif type_alias and isinstance(node, type_alias):
            annotations.append(node.value)
            annotations.extend(getattr(node, "type_params", ()))
        for annotation in annotations:
            annotation_nodes.update(ast.walk(annotation))

    return sorted(
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Name)
        and isinstance(node.ctx, ast.Load)
        and node.id == symbol
        and node not in annotation_nodes
    )


def _production_call_sites(symbol: str) -> list[int]:
    source = ROOT / "src" / "context_search_tool" / "retrieval.py"
    tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
    return _runtime_name_load_lines(tree, symbol)


def _group_references(references: list[Reference]) -> list[dict[str, object]]:
    grouped: dict[str, list[Reference]] = defaultdict(list)
    for reference in references:
        grouped[reference.file].append(reference)
    return [
        {
            "file": file,
            "count": len(values),
            "lines": sorted(item.line for item in values),
            "syntax_kinds": sorted({item.kind for item in values}),
        }
        for file, values in sorted(grouped.items())
    ]


def build_migration_ledger() -> dict[str, object]:
    paths = sorted((ROOT / "tests").rglob("*.py"))
    paths.extend(sorted((ROOT / "scripts").rglob("*.py")))
    references = [
        reference
        for path in paths
        if path != MIGRATION_LEDGER_PATH
        for reference in _scan_file(path)
    ]
    symbols = (
        {reference.symbol for reference in references}
        | SUPPORTED_FACADE
        | set(MIGRATION_OWNERS)
    )
    unknown = sorted(symbols - SUPPORTED_FACADE - set(MIGRATION_OWNERS))
    if unknown:
        raise RuntimeError(
            "unclassified retrieval façade references: " + ", ".join(unknown)
        )

    rows = []
    for symbol in sorted(symbols):
        symbol_references = [item for item in references if item.symbol == symbol]
        direct = [item for item in symbol_references if item.category == "direct"]
        monkeypatches = [
            item for item in symbol_references if item.category == "monkeypatch"
        ]
        profiler = [item for item in symbol_references if item.category == "profiler"]
        production_lines = _production_call_sites(symbol)
        supported = symbol in SUPPORTED_FACADE
        final_owner, task = (
            (f"context_search_tool.retrieval.{symbol}", None)
            if supported
            else MIGRATION_OWNERS[symbol]
        )
        rows.append(
            {
                "old_symbol": symbol,
                "final_owner": final_owner,
                "design_task": task,
                "direct_references": _group_references(direct),
                "monkeypatch_references": _group_references(monkeypatches),
                "profiler_targets": _group_references(profiler),
                "production_call_sites": {
                    "file": "src/context_search_tool/retrieval.py",
                    "count": len(production_lines),
                    "lines": production_lines,
                },
                "syntax_kinds": sorted({item.kind for item in symbol_references}),
                "disposition": "supported_facade" if supported else "migrate",
                "remaining": (
                    len(symbol_references) + len(production_lines)
                    if not supported
                    else len(symbol_references)
                ),
                "resolved_task": None,
            }
        )
    return {
        "schema_version": 1,
        "source_commit": IMPLEMENTATION_COMMIT,
        "rows": rows,
    }


def _write_json(path: Path, value: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=True, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )


def write_migration_ledger() -> None:
    ledger = build_migration_ledger()
    reject_sensitive_manifest(ledger)
    _write_json(MIGRATION_LEDGER_PATH, ledger)


def check_migration_ledger() -> None:
    expected = json.loads(MIGRATION_LEDGER_PATH.read_text(encoding="utf-8"))
    actual = build_migration_ledger()
    if expected != actual:
        raise RuntimeError("migration ledger does not match the current AST inventory")


def generate_baseline(junitxml: Path) -> None:
    assert_clean_environment()
    assert_protected_source_identity()
    if BASELINE_PATH.exists():
        raise RuntimeError("baseline.json already exists; generation is one-shot")
    cases = load_characterization_cases()
    if sum(case.profile == "ci" for case in cases) != 8:
        raise RuntimeError("catalog must expose exactly eight ci cases")
    if sum(case.profile == "p2_context_pack" for case in cases) != 5:
        raise RuntimeError("catalog must expose exactly five p2_context_pack cases")
    identity = characterization_input_identity()
    evidence = parse_junit_evidence(junitxml)
    with tempfile.TemporaryDirectory(prefix="cst-p3-2-characterization-") as raw_temp:
        projection = baseline_projection(Path(raw_temp))
        manifest = {
            "schema_version": 1,
            "projection_schema_version": 1,
            "implementation_commit": IMPLEMENTATION_COMMIT,
            "documentation_baseline": DOCUMENTATION_BASELINE,
            "runtime": runtime_identity(),
            "characterization_inputs": identity,
            "test_evidence": evidence,
            "cases": projection["cases"],
            "full_stage_ledgers": projection["full_stage_ledgers"],
        }
        if tuple(manifest["full_stage_ledgers"]) != FULL_STAGE_LEDGER_KEYS:
            raise RuntimeError("full-stage ledger order drifted")
        reject_sensitive_manifest(manifest, temporary_roots=(Path(raw_temp),))
    _write_json(BASELINE_PATH, manifest)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--junitxml", type=Path)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--write-migration-ledger", action="store_true")
    modes.add_argument("--check-migration-ledger", action="store_true")
    args = parser.parse_args()
    if args.write_migration_ledger:
        write_migration_ledger()
        return
    if args.check_migration_ledger:
        check_migration_ledger()
        return
    if args.junitxml is None:
        parser.error("--junitxml is required for baseline generation")
    generate_baseline(args.junitxml)


if __name__ == "__main__":
    main()
