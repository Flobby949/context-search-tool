from __future__ import annotations

import ast
import inspect
import json
import subprocess
from dataclasses import FrozenInstanceError, MISSING, fields
from pathlib import Path

import pytest

from context_search_tool import retrieval
from generate_retrieval_core_baseline import build_migration_ledger
from retrieval_core_characterization import (
    IMPLEMENTATION_COMMIT,
    MIGRATION_LEDGER_PATH,
    ROOT,
)


EXPECTED_SIGNATURES = {
    "query_repository": (
        "(repo: 'Path', query: 'str', config: 'ToolConfig', "
        "context_lines: 'int | None' = None, full_file: 'bool' = False, "
        "planner: 'QueryPlanner | None' = None, *, "
        "trace_collector: 'RetrievalTraceCollector | None' = None) -> 'QueryBundle'"
    ),
    "trace_repository": (
        "(repo: 'Path', query: 'str', config: 'ToolConfig', "
        "context_lines: 'int | None' = None, full_file: 'bool' = False, "
        "planner: 'QueryPlanner | None' = None, *, clock_ns=None) "
        "-> 'TracedQueryBundle'"
    ),
    "evidence_anchor_top_k": "(max_results: 'int') -> 'int'",
    "normalize_score": "(scores: 'list[float]') -> 'list[float]'",
}

EXPECTED_BUNDLE_REPR = (
    "QueryBundle(query='q', expanded_tokens=['q'], results=[], "
    "followup_keywords=[], summary=RetrievalSummary(entry_points=[], "
    "implementation=[], related_types=[], possibly_legacy=[]), "
    "planner=QueryPlan(original_query='', rewritten_queries=[], "
    "grep_keywords=[], symbol_hints=[], intent='unknown', status='disabled', "
    "provider='', model='', prompt_version='', prompt_hash='', latency_ms=None, "
    "error=None, repo_profile_hash='', repo_profile_truncated=False, "
    "discarded_hints=[]), evidence_anchors=[], query_variants=[], "
    "variant_retrieval_status='original_only')"
)

FINAL_ALLOWED_EDGES = {
    "retrieval": {
        "candidates",
        "expansion",
        "ranking",
        "context_expansion",
        "selection",
        "tracing",
        "ordering",
        "relation_policy",
        "retrieval_trace",
    },
    "types": set(),
    "ordering": set(),
    "evidence_merge": set(),
    "relation_policy": set(),
    "file_roles": set(),
    "candidates": {"ordering", "evidence_merge"},
    "expansion": {"evidence_merge", "file_roles", "relation_policy"},
    "ranking": {
        "types",
        "ordering",
        "evidence_merge",
        "file_roles",
        "relation_policy",
    },
    "context_expansion": {"types", "ordering", "evidence_merge"},
    "selection": {"types", "ordering"},
    "tracing": {"types", "ordering", "selection", "retrieval_trace"},
}

TRANSITIONAL_ALLOWED_EDGES = {
    **FINAL_ALLOWED_EDGES,
    "retrieval": FINAL_ALLOWED_EDGES["retrieval"]
    | {"types", "evidence_merge"},
}


def _field_contract(cls: type[object]) -> list[tuple[str, str]]:
    values = []
    for field in fields(cls):
        if field.default is not MISSING:
            default = repr(field.default)
        elif field.default_factory is not MISSING:
            default = field.default_factory.__name__
        else:
            default = "required"
        values.append((field.name, default))
    return values


def test_public_bundle_dataclass_identity_is_exact() -> None:
    assert retrieval.QueryBundle.__name__ == "QueryBundle"
    assert retrieval.QueryBundle.__module__ == "context_search_tool.retrieval"
    assert retrieval.TracedQueryBundle.__name__ == "TracedQueryBundle"
    assert retrieval.TracedQueryBundle.__module__ == "context_search_tool.retrieval"
    for cls in (retrieval.QueryBundle, retrieval.TracedQueryBundle):
        params = cls.__dataclass_params__
        assert params.frozen is True
        assert params.eq is True
        assert params.repr is True

    assert _field_contract(retrieval.QueryBundle) == [
        ("query", "required"),
        ("expanded_tokens", "required"),
        ("results", "required"),
        ("followup_keywords", "required"),
        ("summary", "RetrievalSummary"),
        ("planner", "disabled_default"),
        ("evidence_anchors", "list"),
        ("query_variants", "list"),
        ("variant_retrieval_status", "'original_only'"),
    ]
    assert _field_contract(retrieval.TracedQueryBundle) == [
        ("bundle", "required"),
        ("trace", "required"),
    ]

    first = retrieval.QueryBundle("q", ["q"], [], [])
    second = retrieval.QueryBundle("q", ["q"], [], [])
    assert first == second
    assert repr(first) == EXPECTED_BUNDLE_REPR
    traced = retrieval.TracedQueryBundle(first, "TRACE")  # type: ignore[arg-type]
    assert repr(traced) == f"TracedQueryBundle(bundle={EXPECTED_BUNDLE_REPR}, trace='TRACE')"
    with pytest.raises(FrozenInstanceError):
        first.query = "changed"  # type: ignore[misc]


def test_supported_facade_signatures_values_and_module_are_exact() -> None:
    for name, signature in EXPECTED_SIGNATURES.items():
        target = getattr(retrieval, name)
        assert str(inspect.signature(target)) == signature
        assert target.__module__ == "context_search_tool.retrieval"

    assert retrieval.normalize_score([]) == []
    assert retrieval.normalize_score([1.0]) == [1.0]
    assert retrieval.normalize_score([1.0, 2.0, 3.0]) == [
        1 / 3,
        2 / 3,
        1.0,
    ]
    assert [retrieval.evidence_anchor_top_k(value) for value in (-1, 0, 1, 2, 3, 12)] == [
        0,
        0,
        1,
        1,
        1,
        4,
    ]
    assert retrieval.MAX_EXPANSION_DEPTH == 3
    assert retrieval.MAX_EXPANSION_CANDIDATES == 1000
    assert "__all__" not in vars(retrieval)


def _internal_edges(path: Path, importer: str) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    edges: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if any(alias.name == "*" for alias in node.names):
                raise AssertionError(f"star import in {path}")
            module = node.module or ""
            if module == "context_search_tool.retrieval_core":
                edges.update(alias.name for alias in node.names)
            elif module.startswith("context_search_tool.retrieval_core."):
                if importer == "retrieval":
                    raise AssertionError(
                        f"retrieval imports core symbols instead of modules: {path}"
                    )
                edges.add(module.rsplit(".", 1)[-1])
            elif module.startswith("context_search_tool.retrieval_trace"):
                edges.add("retrieval_trace")
            if importer != "retrieval" and module == "context_search_tool.retrieval":
                raise AssertionError(f"retrieval_core imports façade: {path}")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("context_search_tool.retrieval_core."):
                    edges.add(alias.name.rsplit(".", 1)[-1])
                elif alias.name.startswith("context_search_tool.retrieval_trace"):
                    edges.add("retrieval_trace")
                elif (
                    importer != "retrieval"
                    and alias.name == "context_search_tool.retrieval"
                ):
                    raise AssertionError(f"retrieval_core imports façade: {path}")
    return edges


def test_retrieval_boundary_rejects_aliased_private_core_reexport(
    tmp_path: Path,
) -> None:
    source = tmp_path / "retrieval.py"
    source.write_text(
        "from context_search_tool.retrieval_core.ranking "
        "import rank_chunks as _rank_chunks\n",
        encoding="utf-8",
    )

    with pytest.raises(AssertionError, match="imports core symbols"):
        _internal_edges(source, "retrieval")


def test_retrieval_core_import_adjacency_is_a_transitional_subset() -> None:
    assert TRANSITIONAL_ALLOWED_EDGES["retrieval"] - FINAL_ALLOWED_EDGES[
        "retrieval"
    ] == {"types", "evidence_merge"}
    assert all(
        TRANSITIONAL_ALLOWED_EDGES[owner] == dependencies
        for owner, dependencies in FINAL_ALLOWED_EDGES.items()
        if owner != "retrieval"
    )

    paths = {"retrieval": ROOT / "src" / "context_search_tool" / "retrieval.py"}
    core = ROOT / "src" / "context_search_tool" / "retrieval_core"
    if core.exists():
        paths.update(
            {
                path.stem: path
                for path in core.glob("*.py")
                if path.name != "__init__.py"
            }
        )
        package_tree = ast.parse((core / "__init__.py").read_text(encoding="utf-8"))
        assert all(
            isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
            for node in package_tree.body
        )

    graph: dict[str, set[str]] = {}
    for importer, path in paths.items():
        assert importer in TRANSITIONAL_ALLOWED_EDGES
        edges = _internal_edges(path, importer)
        assert edges <= TRANSITIONAL_ALLOWED_EDGES[importer]
        graph[importer] = edges - {"retrieval_trace"}

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> None:
        if node in visiting:
            raise AssertionError("retrieval_core import cycle")
        if node in visited:
            return
        visiting.add(node)
        for dependency in graph.get(node, set()):
            visit(dependency)
        visiting.remove(node)
        visited.add(node)

    for node in graph:
        visit(node)


def test_migration_ledger_matches_complete_ast_and_dynamic_inventory() -> None:
    frozen = json.loads(MIGRATION_LEDGER_PATH.read_text(encoding="utf-8"))
    actual = build_migration_ledger()
    for actual_row, frozen_row in zip(actual["rows"], frozen["rows"]):
        actual_row["resolved_task"] = frozen_row["resolved_task"]

    assert actual == frozen
    assert all(row["disposition"] in {"supported_facade", "migrate"} for row in frozen["rows"])
    assert all(
        row["final_owner"].startswith("context_search_tool.")
        for row in frozen["rows"]
    )
    for row in frozen["rows"]:
        if row["disposition"] != "migrate":
            continue
        if row["resolved_task"] is None:
            assert row["remaining"] > 0
        else:
            assert row["remaining"] == 0
            assert row["resolved_task"] == row["design_task"]


def test_protected_production_diff_is_scoped_to_reviewed_files() -> None:
    changed = subprocess.run(
        (
            "git",
            "diff",
            "--name-only",
            IMPLEMENTATION_COMMIT,
            "--",
            "src/context_search_tool",
        ),
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()

    assert all(
        path == "src/context_search_tool/retrieval.py"
        or path.startswith("src/context_search_tool/retrieval_core/")
        for path in changed
    )


def test_trace_owner_never_reads_private_or_public_content() -> None:
    tracing = (
        ROOT
        / "src"
        / "context_search_tool"
        / "retrieval_core"
        / "tracing.py"
    )
    source = tracing if tracing.exists() else ROOT / "src" / "context_search_tool" / "retrieval.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    nodes: list[ast.AST]
    if tracing.exists():
        nodes = list(ast.walk(tree))
    else:
        nodes = [
            child
            for definition in tree.body
            if isinstance(definition, ast.FunctionDef)
            and (definition.name.startswith("_trace_") or definition.name == "_finish_trace")
            for child in ast.walk(definition)
        ]
    assert not [
        node
        for node in nodes
        if isinstance(node, ast.Attribute)
        and node.attr in {"content", "_context_content"}
    ]
