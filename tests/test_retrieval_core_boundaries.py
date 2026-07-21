from __future__ import annotations

import ast
import inspect
import json
import subprocess
from dataclasses import FrozenInstanceError, MISSING, fields
from pathlib import Path

import pytest

from context_search_tool import retrieval
from generate_retrieval_core_baseline import (
    _runtime_name_load_lines,
    build_migration_ledger,
)
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

SUPPORTED_RETRIEVAL_FACADE = {
    "QueryBundle",
    "TracedQueryBundle",
    "query_repository",
    "trace_repository",
    "evidence_anchor_top_k",
    "normalize_score",
    "MAX_EXPANSION_DEPTH",
    "MAX_EXPANSION_CANDIDATES",
}

EXPECTED_LOCAL_DEFINITIONS = {
    "QueryBundle",
    "TracedQueryBundle",
    "query_repository",
    "trace_repository",
    "evidence_anchor_top_k",
    "normalize_score",
    "_query_repository_v5",
    "_query_repository_impl",
}

EXPECTED_COMPATIBILITY_ASSIGNMENTS = {
    "MAX_EXPANSION_DEPTH": "relation_policy.MAX_EXPANSION_DEPTH",
    "MAX_EXPANSION_CANDIDATES": "relation_policy.MAX_EXPANSION_CANDIDATES",
}

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
    "evidence_merge": {"relation_policy"},
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
    "selection": {"types", "ordering", "relation_policy"},
    "tracing": {"types", "ordering", "selection", "retrieval_trace"},
}

EXPECTED_P4_PRODUCTION_DIFF = {
    "src/context_search_tool/cli.py",
    "src/context_search_tool/exploration/__init__.py",
    "src/context_search_tool/exploration/fusion.py",
    "src/context_search_tool/exploration/goals.py",
    "src/context_search_tool/exploration/models.py",
    "src/context_search_tool/exploration/options.py",
    "src/context_search_tool/exploration/probes.py",
    "src/context_search_tool/exploration/runner.py",
    "src/context_search_tool/formatters.py",
    "src/context_search_tool/mcp_server.py",
    "src/context_search_tool/mcp_tools.py",
    "src/context_search_tool/quality/aggregate.py",
    "src/context_search_tool/quality/cases.py",
    "src/context_search_tool/quality/compare.py",
    "src/context_search_tool/quality/metrics.py",
    "src/context_search_tool/quality/reports.py",
    "src/context_search_tool/quality/runner.py",
    "src/context_search_tool/retrieval_trace/__init__.py",
    "src/context_search_tool/retrieval_trace/exploration.py",
}

P5_REVIEWED_PRODUCTION_CHANGES = {
    "src/context_search_tool/config.py",
    "src/context_search_tool/graph_contract.py",
    "src/context_search_tool/graph_lifecycle.py",
    "src/context_search_tool/graph_resolution.py",
    "src/context_search_tool/graph_plugins.py",
    "src/context_search_tool/models.py",
    "src/context_search_tool/syntax_parsers.py",
    "src/context_search_tool/java_ast.py",
    "src/context_search_tool/java_graph.py",
    "src/context_search_tool/java_plugin.py",
    "src/context_search_tool/frontend_graph.py",
    "src/context_search_tool/mybatis_xml.py",
    "src/context_search_tool/test_paths.py",
    "src/context_search_tool/test_association.py",
    "src/context_search_tool/index_lock.py",
    "src/context_search_tool/plugins.py",
    "src/context_search_tool/project_scope.py",
    "src/context_search_tool/scanner.py",
    "src/context_search_tool/sqlite_store.py",
    "src/context_search_tool/vector_store.py",
    "src/context_search_tool/manifest.py",
    "src/context_search_tool/paths.py",
    "src/context_search_tool/indexer.py",
    "src/context_search_tool/retrieval.py",
    "src/context_search_tool/retrieval_core/candidates.py",
    "src/context_search_tool/retrieval_core/expansion.py",
    "src/context_search_tool/retrieval_core/relation_policy.py",
    "src/context_search_tool/retrieval_core/ranking.py",
    "src/context_search_tool/retrieval_core/evidence_merge.py",
    "src/context_search_tool/retrieval_core/context_expansion.py",
    "src/context_search_tool/retrieval_core/selection.py",
    "src/context_search_tool/retrieval_core/tracing.py",
    "src/context_search_tool/exploration/probes.py",
    "src/context_search_tool/exploration/runner.py",
    "src/context_search_tool/context_pack/builder.py",
    "src/context_search_tool/context_pack/needs.py",
    "src/context_search_tool/context_pack/roles.py",
    "src/context_search_tool/cli.py",
    "src/context_search_tool/mcp_tools.py",
    "src/context_search_tool/quality/cases.py",
    "src/context_search_tool/quality/runner.py",
}

P6_TASK2_PRODUCTION_CHANGES = {
    "src/context_search_tool/index_health.py",
}

P4_IMPLEMENTATION_BASELINE = "b827707325d0ee4e9c6b2bcb3dee39955c263822"
THIS_TEST_PATH = "tests/test_retrieval_core_boundaries.py"

GRAPH_CONTRACT_STDLIB_IMPORTS = {
    "hashlib",
    "json",
    "math",
    "pathlib",
    "types",
    "typing",
    "unicodedata",
    "__future__",
}

MODULE_ID_CONSUMERS = {
    "frontend_graph.py",
    "graph_lifecycle.py",
    "graph_resolution.py",
    "indexer.py",
    "mybatis_xml.py",
    "retrieval.py",
    "test_association.py",
}

JAVA_AST_ALLOWED_INTERNAL_IMPORTS = {
    "context_search_tool.syntax_parsers",
    "context_search_tool.tokenizer",
}

FRONTEND_GRAPH_ALLOWED_INTERNAL_IMPORTS = {
    "context_search_tool.graph_contract",
    "context_search_tool.graph_plugins",
    "context_search_tool.models",
    "context_search_tool.syntax_parsers",
}

MYBATIS_ALLOWED_INTERNAL_IMPORTS = {
    "context_search_tool.graph_contract",
    "context_search_tool.graph_plugins",
    "context_search_tool.models",
}

GRAPH_PLUGINS_ALLOWED_INTERNAL_IMPORTS = {
    "context_search_tool.models",
}

JAVA_GRAPH_ALLOWED_INTERNAL_IMPORTS = {
    "context_search_tool.graph_contract",
    "context_search_tool.graph_plugins",
    "context_search_tool.java_ast",
    "context_search_tool.models",
}

TEST_ASSOCIATION_ALLOWED_INTERNAL_IMPORTS = {
    "context_search_tool.graph_contract",
    "context_search_tool.models",
    "context_search_tool.test_paths",
}

GRAPH_LIFECYCLE_ALLOWED_INTERNAL_IMPORTS = {
    "context_search_tool.graph_contract",
}

GRAPH_RESOLUTION_ALLOWED_INTERNAL_IMPORTS = {
    "context_search_tool.graph_contract",
    "context_search_tool.models",
}

INDEX_LOCK_ALLOWED_INTERNAL_IMPORTS = {
    "context_search_tool.graph_lifecycle",
}

INDEX_HEALTH_ALLOWED_INTERNAL_IMPORTS = {
    "context_search_tool.graph_lifecycle",
    "context_search_tool.manifest",
    "context_search_tool.scanner",
    "context_search_tool.sqlite_store",
}


def _is_p4_public_facade_reference(reference: dict[str, object]) -> bool:
    path = reference["file"]
    return isinstance(path, str) and (
        path.startswith("tests/test_exploration_")
        or path == "tests/test_quality_p4.py"
        or path == "tests/test_p5_privacy.py"
        or path == "tests/test_graph_lifecycle.py"
        or path == "tests/generate_p4_exploration_manifest.py"
        or path == "tests/test_p5_protected_direct.py"
        or path == "tests/test_quality_p5.py"
        or path == "scripts/p6_benchmark.py"
    )


def _normalize_current_test_reference(
    reference: dict[str, object],
    frozen: list[dict[str, object]],
) -> dict[str, object]:
    if reference["file"] != THIS_TEST_PATH:
        return reference
    frozen_reference = next(
        item for item in frozen if item["file"] == THIS_TEST_PATH
    )
    assert reference["count"] == frozen_reference["count"]
    assert reference["syntax_kinds"] == frozen_reference["syntax_kinds"]
    return frozen_reference


def _normalize_current_production_calls(
    current: dict[str, object],
    frozen: dict[str, object],
) -> dict[str, object]:
    assert current["file"] == frozen["file"]
    assert current["count"] == frozen["count"]
    return frozen


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
            elif module == "context_search_tool":
                for alias in node.names:
                    if alias.name == "retrieval_core":
                        raise AssertionError(f"broad retrieval_core import in {path}")
                    if alias.name == "retrieval_trace":
                        edges.add("retrieval_trace")
                    if importer != "retrieval" and alias.name == "retrieval":
                        raise AssertionError(f"retrieval_core imports façade: {path}")
            if importer != "retrieval" and (
                module == "context_search_tool.retrieval"
                or module.startswith("context_search_tool.retrieval.")
            ):
                raise AssertionError(f"retrieval_core imports façade: {path}")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "context_search_tool.retrieval_core":
                    raise AssertionError(f"broad retrieval_core import in {path}")
                if alias.name.startswith("context_search_tool.retrieval_core."):
                    edges.add(alias.name.rsplit(".", 1)[-1])
                elif alias.name.startswith("context_search_tool.retrieval_trace"):
                    edges.add("retrieval_trace")
                elif (
                    importer != "retrieval"
                    and (
                        alias.name == "context_search_tool.retrieval"
                        or alias.name.startswith("context_search_tool.retrieval.")
                    )
                ):
                    raise AssertionError(f"retrieval_core imports façade: {path}")
    return edges


def _retrieval_tree() -> ast.Module:
    path = ROOT / "src" / "context_search_tool" / "retrieval.py"
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _import_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".", 1)[0])
    return roots


def _internal_imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(
                alias.name
                for alias in node.names
                if alias.name.startswith("context_search_tool")
            )
        elif (
            isinstance(node, ast.ImportFrom)
            and node.module
            and node.module.startswith("context_search_tool")
        ):
            imports.add(node.module)
    return imports


def _reconstructs_core_module_id(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        function_name = ""
        if isinstance(node.func, ast.Name):
            function_name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            function_name = node.func.attr
        if function_name != "generate_v5_signal_id":
            continue
        keyword_values = {
            keyword.arg: keyword.value
            for keyword in node.keywords
            if keyword.arg is not None
        }
        for name, expected in (("kind", "module"), ("producer", "core_module")):
            value = keyword_values.get(name)
            if isinstance(value, ast.Constant) and value.value == expected:
                return True
    return False


def _aliased_import_bindings(tree: ast.Module) -> set[str]:
    bindings: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            bindings.update(alias.asname for alias in node.names if alias.asname)
    return bindings


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


def test_retrieval_core_import_adjacency_is_exact_and_acyclic() -> None:
    paths = {"retrieval": ROOT / "src" / "context_search_tool" / "retrieval.py"}
    core = ROOT / "src" / "context_search_tool" / "retrieval_core"
    paths.update(
        {
            path.stem: path
            for path in core.glob("*.py")
            if path.name != "__init__.py"
        }
    )
    assert set(paths) == set(FINAL_ALLOWED_EDGES)

    package_tree = ast.parse((core / "__init__.py").read_text(encoding="utf-8"))
    assert all(
        isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
        for node in package_tree.body
    )

    graph: dict[str, set[str]] = {}
    for importer, path in paths.items():
        edges = _internal_edges(path, importer)
        assert edges == FINAL_ALLOWED_EDGES[importer]
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


def test_graph_contract_is_pure_and_module_identity_is_shared() -> None:
    package = ROOT / "src" / "context_search_tool"
    contract = package / "graph_contract.py"
    assert _import_roots(contract) <= GRAPH_CONTRACT_STDLIB_IMPORTS

    for name in MODULE_ID_CONSUMERS:
        path = package / name
        if path.exists():
            assert not _reconstructs_core_module_id(path), path


def test_java_ast_imports_are_leaf_only_and_production_registration_is_active() -> None:
    package = ROOT / "src" / "context_search_tool"
    java_ast = package / "java_ast.py"
    assert _internal_imports(java_ast) <= JAVA_AST_ALLOWED_INTERNAL_IMPORTS

    for name in ("plugins.py", "indexer.py", "java_plugin.py", "retrieval.py"):
        assert "context_search_tool.java_ast" not in _internal_imports(package / name)

    plugins_tree = ast.parse((package / "plugins.py").read_text(encoding="utf-8"))
    default_plugins = next(
        node
        for node in plugins_tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "default_plugins"
    )
    imports = {
        node.module
        for node in ast.walk(default_plugins)
        if isinstance(node, ast.ImportFrom)
    }
    returns = [node for node in ast.walk(default_plugins) if isinstance(node, ast.Return)]
    assert imports == {
        "context_search_tool.frontend_graph",
        "context_search_tool.java_plugin",
        "context_search_tool.mybatis_xml",
    }
    assert len(returns) == 1
    assert ast.unparse(returns[0].value) == (
        "[JavaPlugin(), FrontendGraphProducer(), MyBatisGraphProducer()]"
    )


def test_frontend_and_mybatis_fact_modules_are_pure_and_registered() -> None:
    package = ROOT / "src" / "context_search_tool"
    assert _internal_imports(package / "frontend_graph.py") <= (
        FRONTEND_GRAPH_ALLOWED_INTERNAL_IMPORTS
    )
    assert _internal_imports(package / "mybatis_xml.py") <= (
        MYBATIS_ALLOWED_INTERNAL_IMPORTS
    )

    for name in ("indexer.py", "java_plugin.py", "retrieval.py"):
        imports = _internal_imports(package / name)
        assert "context_search_tool.frontend_graph" not in imports
        assert "context_search_tool.mybatis_xml" not in imports
    plugin_imports = _internal_imports(package / "plugins.py")
    assert {
        "context_search_tool.frontend_graph",
        "context_search_tool.mybatis_xml",
    } <= plugin_imports

    mybatis_tree = ast.parse(
        (package / "mybatis_xml.py").read_text(encoding="utf-8")
    )
    forbidden_network_roots = {"http", "requests", "socket", "urllib"}
    assert _import_roots(package / "mybatis_xml.py").isdisjoint(
        forbidden_network_roots
    )
    assert not [
        node
        for node in ast.walk(mybatis_tree)
        if isinstance(node, ast.Attribute)
        and node.attr.lower() in {"xinclude", "resolve", "resolver"}
    ]


def test_graph_producer_protocol_adapters_and_test_paths_are_leaf_bounded() -> None:
    package = ROOT / "src" / "context_search_tool"
    assert _internal_imports(package / "graph_plugins.py") <= (
        GRAPH_PLUGINS_ALLOWED_INTERNAL_IMPORTS
    )
    assert _internal_imports(package / "java_graph.py") <= (
        JAVA_GRAPH_ALLOWED_INTERNAL_IMPORTS
    )
    assert _internal_imports(package / "test_association.py") <= (
        TEST_ASSOCIATION_ALLOWED_INTERNAL_IMPORTS
    )
    assert not _internal_imports(package / "test_paths.py")

    graph_plugins = (package / "graph_plugins.py").read_text(encoding="utf-8")
    assert "JavaGraphProducer" not in graph_plugins
    assert "FrontendGraphProducer" not in graph_plugins
    assert "MyBatisGraphProducer" not in graph_plugins

    for name in ("plugins.py", "retrieval.py"):
        imports = _internal_imports(package / name)
        assert "context_search_tool.java_graph" not in imports
        assert "context_search_tool.test_association" not in imports
    assert "context_search_tool.java_graph" in _internal_imports(
        package / "java_plugin.py"
    )
    indexer_imports = _internal_imports(package / "indexer.py")
    assert "context_search_tool.java_graph" not in indexer_imports
    assert "context_search_tool.test_association" in indexer_imports


def test_graph_lifecycle_primitives_are_leaf_bounded_and_activated() -> None:
    package = ROOT / "src" / "context_search_tool"
    assert _internal_imports(package / "graph_lifecycle.py") <= (
        GRAPH_LIFECYCLE_ALLOWED_INTERNAL_IMPORTS
    )
    assert _internal_imports(package / "graph_resolution.py") <= (
        GRAPH_RESOLUTION_ALLOWED_INTERNAL_IMPORTS
    )
    assert _internal_imports(package / "index_lock.py") <= (
        INDEX_LOCK_ALLOWED_INTERNAL_IMPORTS
    )
    index_health = package / "index_health.py"
    assert index_health.is_file(), "P6 index-health core is absent"
    assert _internal_imports(index_health) <= INDEX_HEALTH_ALLOWED_INTERNAL_IMPORTS
    assert _import_roots(index_health).isdisjoint(
        {"http", "requests", "socket", "subprocess", "urllib"}
    )

    indexer_path = package / "indexer.py"
    indexer_imports = _internal_imports(indexer_path)
    assert "context_search_tool.graph_lifecycle" in indexer_imports
    assert "context_search_tool.graph_resolution" in indexer_imports
    assert "context_search_tool.index_lock" in indexer_imports
    assert "context_search_tool.scanner" in indexer_imports

    indexer_tree = ast.parse(indexer_path.read_text(encoding="utf-8"))
    assignments = {
        target.id: node.value.value
        for node in indexer_tree.body
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance((target := node.targets[0]), ast.Name)
        and isinstance(node.value, ast.Constant)
    }
    assert assignments["CURRENT_SIGNAL_SCHEMA_VERSION"] == 5
    public_indexer = next(
        node
        for node in indexer_tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "index_repository"
    )
    assert not [
        node
        for node in ast.walk(public_indexer)
        if isinstance(node, ast.Call)
        and (
            isinstance(node.func, ast.Name)
            and node.func.id
            in {
                "scan_workspace_v5",
                "read_scanned_file_bytes",
                "resolve_graph_relations",
                "exclusive_index_lock",
            }
        )
    ]
    assert {
        node.func.id
        for node in ast.walk(public_indexer)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    } >= {"build_v5_index_snapshot", "default_plugins"}

    retrieval_tree = _retrieval_tree()
    public_query = next(
        node
        for node in retrieval_tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "query_repository"
    )
    public_query_calls = {
        node.func.id
        for node in ast.walk(public_query)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "_query_repository_v5" in public_query_calls
    exploration_runner = (
        package / "exploration" / "runner.py"
    ).read_text(encoding="utf-8")
    assert "_plan_probes_v5" in exploration_runner

    assert "build_v5_index_snapshot" in indexer_path.read_text(encoding="utf-8")

    for name in ("graph_lifecycle.py", "graph_resolution.py", "index_lock.py"):
        assert _import_roots(package / name).isdisjoint(
            {"http", "requests", "socket", "subprocess", "urllib"}
        )


def test_retrieval_defines_only_the_exact_supported_facade() -> None:
    tree = _retrieval_tree()
    definitions = [
        node.name
        for node in tree.body
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    assert len(definitions) == len(EXPECTED_LOCAL_DEFINITIONS)
    assert set(definitions) == EXPECTED_LOCAL_DEFINITIONS

    assignments: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            assert len(node.targets) == 1
            target = node.targets[0]
            assert isinstance(target, ast.Name)
            assignments[target.id] = ast.unparse(node.value)
        elif isinstance(node, ast.AnnAssign):
            assert isinstance(node.target, ast.Name)
            assert node.value is not None
            assignments[node.target.id] = ast.unparse(node.value)
    assert assignments == EXPECTED_COMPATIBILITY_ASSIGNMENTS

    ledger = json.loads(MIGRATION_LEDGER_PATH.read_text(encoding="utf-8"))
    migrated_names = {
        row["old_symbol"]
        for row in ledger["rows"]
        if row["disposition"] == "migrate"
    }
    assert _aliased_import_bindings(tree).isdisjoint(migrated_names)


def test_migration_ledger_matches_complete_ast_and_dynamic_inventory() -> None:
    frozen = json.loads(MIGRATION_LEDGER_PATH.read_text(encoding="utf-8"))
    actual = build_migration_ledger()

    frozen_by_symbol = {row["old_symbol"]: row for row in frozen["rows"]}
    for actual_row in actual["rows"]:
        frozen_row = frozen_by_symbol[actual_row["old_symbol"]]
        actual_row["resolved_task"] = frozen_row["resolved_task"]
        actual_row["production_call_sites"] = _normalize_current_production_calls(
            actual_row["production_call_sites"],
            frozen_row["production_call_sites"],
        )
        if frozen_row["disposition"] != "supported_facade":
            continue

        frozen_references = frozen_row["direct_references"]
        actual_references = [
            _normalize_current_test_reference(item, frozen_references)
            for item in actual_row["direct_references"]
        ]
        assert all(item in actual_references for item in frozen_references)
        additions = [
            item for item in actual_references if item not in frozen_references
        ]
        assert all(_is_p4_public_facade_reference(item) for item in additions)
        assert actual_row["remaining"] == frozen_row["remaining"] + sum(
            item["count"] for item in additions
        )
        actual_row["direct_references"] = frozen_references
        actual_row["remaining"] = frozen_row["remaining"]

    assert actual == frozen
    assert all(row["disposition"] in {"supported_facade", "migrate"} for row in frozen["rows"])
    assert all(
        row["final_owner"].startswith("context_search_tool.")
        for row in frozen["rows"]
    )
    for row in frozen["rows"]:
        if row["disposition"] == "supported_facade":
            assert row["old_symbol"] in SUPPORTED_RETRIEVAL_FACADE
            assert row["final_owner"] == (
                f"context_search_tool.retrieval.{row['old_symbol']}"
            )
            assert row["remaining"] > 0
            continue
        assert row["remaining"] == 0
        assert row["resolved_task"] is not None
        assert row["resolved_task"] == row["design_task"]
    assert {
        row["old_symbol"]
        for row in frozen["rows"]
        if row["disposition"] == "supported_facade"
    } == SUPPORTED_RETRIEVAL_FACADE


def test_runtime_inventory_excludes_annotations_but_keeps_live_loads() -> None:
    tree = ast.parse(
        "def build(value: Owner) -> Owner:\n"
        "    local: Owner = Owner()\n"
        "    return Owner.factory(local)\n"
    )

    assert _runtime_name_load_lines(tree, "Owner") == [2, 3]


def test_protected_production_diff_is_scoped_to_reviewed_files() -> None:
    changed = set(
        subprocess.run(
            (
                "git",
                "diff",
                "--name-only",
                P4_IMPLEMENTATION_BASELINE,
                "--",
                "src/context_search_tool",
            ),
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.splitlines()
    )

    assert EXPECTED_P4_PRODUCTION_DIFF <= changed
    assert changed <= (
        EXPECTED_P4_PRODUCTION_DIFF
        | P5_REVIEWED_PRODUCTION_CHANGES
        | P6_TASK2_PRODUCTION_CHANGES
    )

    source_status = subprocess.run(
        (
            "git",
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
            "--",
            "src/context_search_tool",
        ),
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    dirty_source_paths = {line[3:] for line in source_status}
    assert dirty_source_paths <= (
        P5_REVIEWED_PRODUCTION_CHANGES | P6_TASK2_PRODUCTION_CHANGES
    )

    subprocess.run(
        (
            "git",
            "diff",
            "--exit-code",
            P4_IMPLEMENTATION_BASELINE,
                "--",
                "src/context_search_tool/context_pack/__init__.py",
                "src/context_search_tool/context_pack/excerpts.py",
                "src/context_search_tool/context_pack/models.py",
                "src/context_search_tool/context_pack/serialization.py",
            "src/context_search_tool/retrieval_trace/models.py",
            "src/context_search_tool/retrieval_trace/serialization.py",
            "src/context_search_tool/retrieval_trace/collector.py",
            "src/context_search_tool/chunker.py",
        ),
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
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
