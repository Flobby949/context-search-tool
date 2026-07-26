from __future__ import annotations

from pathlib import Path

from context_search_tool.python_graph import (
    MAX_PYTHON_DECLARATION_FACTS,
    extract_python_facts,
)

FIXTURE = Path(__file__).parent / "fixtures" / "p8-python-graphs"


def _facts(relative: str):
    return extract_python_facts(relative, (FIXTURE / relative).read_bytes())


def _decl_index(facts):
    return {
        (fact.owner_qualified_name, fact.name): fact
        for fact in facts.declarations
    }


def test_declaration_facts_respect_ownership_boundary() -> None:
    facts = _facts("app/service.py")

    index = _decl_index(facts)
    assert set(index) == {
        ("", "PosixService"),
        ("PosixService", "run"),
        ("", "Service"),
        ("Service", "conditional_method"),
        ("Service", "run"),
        ("", "build_service"),
        ("", "run_async"),
    }
    assert index[("", "PosixService")].kind == "class"
    assert index[("PosixService", "run")].kind == "method"
    assert index[("Service", "conditional_method")].kind == "method"
    assert index[("", "build_service")].kind == "function"
    assert index[("", "run_async")].kind == "function"
    assert index[("", "run_async")].is_async is True
    assert index[("Service", "run")].is_async is False


def test_declaration_facts_cover_async_and_nested_class_owner() -> None:
    facts = _facts("app/api.py")

    index = _decl_index(facts)
    assert set(index) == {
        ("", "ApiHandler"),
        ("ApiHandler", "handle"),
        ("ApiHandler", "handle_async"),
        ("ApiHandler", "Pagination"),
        ("ApiHandler.Pagination", "page_size"),
        ("", "make_handler"),
        ("", "stream_handler"),
    }
    assert index[("ApiHandler", "handle_async")].is_async is True
    assert index[("ApiHandler", "Pagination")].kind == "class"
    assert index[("ApiHandler.Pagination", "page_size")].kind == "method"
    assert index[("", "stream_handler")].is_async is True

    handler = index[("", "ApiHandler")]
    assert handler.range.start_line == 7
    assert handler.range.start_col == 0


def test_decorated_declaration_starts_at_earliest_decorator() -> None:
    content = (
        b"def wrap(fn):\n"
        b"    return fn\n"
        b"\n"
        b"\n"
        b"@wrap\n"
        b"@wrap\n"
        b"def decorated():\n"
        b"    return None\n"
        b"\n"
        b"\n"
        b"@wrap\n"
        b"class Decorated:\n"
        b"    pass\n"
    )

    facts = extract_python_facts("inline/decorated.py", content)

    index = _decl_index(facts)
    assert index[("", "decorated")].range.start_line == 5
    assert index[("", "decorated")].range.end_line == 8
    assert index[("", "Decorated")].range.start_line == 11
    assert index[("", "Decorated")].range.end_line == 13


def test_columns_are_utf8_byte_offsets() -> None:
    content = "X = '中文'\n\ndef 中文后(value):\n    return value\n".encode(
        "utf-8"
    )

    facts = extract_python_facts("inline/utf8.py", content)

    [decl] = facts.declarations
    assert decl.name == "中文后"
    assert decl.range.start_col == 0
    assert decl.range.start_line == 3


def test_import_syntax_forms_produce_reviewed_raw_facts() -> None:
    facts = _facts("app/service.py")

    rows = [
        (
            fact.import_form,
            fact.relative_level,
            fact.module,
            fact.is_star,
            fact.range.start_line,
        )
        for fact in facts.imports
    ]
    assert rows == [
        ("import", 0, "app.dupe", False, 1),
        ("import", 0, "os", False, 1),
        ("from", 1, "clients", False, 2),
        ("from", 1, "clients", False, 3),
        ("from", 2, "app", False, 4),
        ("import", 0, "app.api", False, 10),
        ("from", 0, "app.clients.text", False, 30),
    ]


def test_import_star_and_aliased_forms() -> None:
    content = (
        b"import a.b as local\n"
        b"from a.b import *\n"
        b"from . import *\n"
    )

    facts = extract_python_facts("app/inline_star.py", content)

    rows = [
        (fact.import_form, fact.relative_level, fact.module, fact.is_star)
        for fact in facts.imports
    ]
    assert rows == [
        ("import", 0, "a.b", False),
        ("from", 0, "a.b", True),
        ("from", 1, "", True),
    ]


def test_dynamic_imports_emit_no_fact() -> None:
    facts = _facts("app/dynamic.py")

    assert [fact.module for fact in facts.imports] == ["importlib"]


def test_facts_are_canonically_ordered_and_deterministic() -> None:
    first = _facts("app/service.py")
    second = _facts("app/service.py")

    assert first == second
    ordering = [
        (
            fact.range.start_line,
            fact.range.start_col,
            fact.range.end_line,
            fact.range.end_col,
        )
        for fact in first.declarations
    ]
    assert ordering == sorted(ordering)


def test_malformed_syntax_returns_bounded_diagnostic() -> None:
    facts = _facts("app/broken.py")

    assert facts.parse_status == "syntax_error"
    assert facts.declarations == ()
    assert facts.imports == ()
    assert [(item.code, item.count) for item in facts.diagnostics] == [
        ("syntax_error", 1)
    ]
    rendered = repr(facts)
    assert "broken(" not in rendered
    assert "line" not in " ".join(item.code for item in facts.diagnostics)


def test_encoding_cookie_and_encoding_failure() -> None:
    latin = b"# -*- coding: latin-1 -*-\nLABEL = '\xe9'\n\ndef labeled():\n    return LABEL\n"
    good = extract_python_facts("inline/latin.py", latin)
    assert good.parse_status == "ok"
    assert [fact.name for fact in good.declarations] == ["labeled"]

    # CPython surfaces a bad source encoding through compile() as a
    # SyntaxError, which maps to the closed syntax_error status. The
    # encoding_error code stays reserved for genuine UnicodeDecodeError.
    bad = extract_python_facts(
        "inline/bad.py", b"# -*- coding: utf-8 -*-\nX = '\xff\xfe'\n"
    )
    assert bad.parse_status == "syntax_error"
    assert [(item.code, item.count) for item in bad.diagnostics] == [
        ("syntax_error", 1)
    ]
    assert "\\xff" not in repr(bad.diagnostics)


def test_declaration_cap_retains_first_4095_and_records_omission() -> None:
    body = b"".join(
        b"def fn_%04d():\n    return %d\n\n" % (index, index)
        for index in range(MAX_PYTHON_DECLARATION_FACTS + 1)
    )

    facts = extract_python_facts("inline/big.py", body)

    assert MAX_PYTHON_DECLARATION_FACTS == 4095
    assert len(facts.declarations) == 4095
    assert facts.declarations[0].name == "fn_0000"
    assert facts.declarations[-1].name == "fn_4094"
    assert facts.omitted_declaration_count == 1


def test_parse_returns_frozen_fact_types() -> None:
    facts = _facts("app/api.py")

    try:
        facts.declarations[0].name = "mutated"  # type: ignore[misc]
        raised = False
    except Exception:
        raised = True
    assert raised


from pathlib import Path as _P

from context_search_tool.graph_contract import generate_v5_signal_id
from context_search_tool.graph_plugins import PluginContext
from context_search_tool.models import CodeSignal, DocumentChunk
from context_search_tool.python_graph import (
    PythonGraphProducer,
    python_module_name,
)


def _context(path: str, language: str = "python", unit: str = "") -> PluginContext:
    return PluginContext(
        file_path=_P(path),
        language=language,
        project_unit_key=unit,
    )


def _chunk_for(path: str, start: int, end: int, chunk_id: str) -> DocumentChunk:
    return DocumentChunk(
        chunk_id=chunk_id,
        file_path=_P(path),
        start_line=start,
        end_line=end,
        content="",
        chunk_type="text",
        lexical_tokens=[],
        metadata={},
    )


def _module_signal(path: str) -> CodeSignal:
    return CodeSignal(
        signal_id=f"module::{path}",
        chunk_id="chunk-module",
        file_path=_P(path),
        kind="module",
        name=path,
        start_line=1,
        end_line=1,
        language="python",
        producer="core_module",
    )


def test_supports_uses_exact_suffix_authority() -> None:
    producer = PythonGraphProducer()

    assert producer.supports(_context("pkg/mod.py", language="text")) is True
    assert producer.supports(_context("pkg/mod.pyw", language="go")) is True
    assert producer.supports(_context("pkg/mod.pyi", language="python")) is False
    assert producer.supports(_context("pkg/MOD.PY", language="python")) is False
    assert producer.supports(_context("pkg/mod.go", language="python")) is False


def test_python_module_name_projection() -> None:
    assert python_module_name(_P("app/api.py"), "") == "app.api"
    assert python_module_name(_P("app/__init__.py"), "") == "app"
    assert python_module_name(_P("src/payments/engine.py"), "") == (
        "src.payments.engine"
    )
    assert python_module_name(_P("__init__.py"), "") == "__init__"
    assert python_module_name(_P("nested/pkg/target.py"), "nested") == (
        "pkg.target"
    )
    assert python_module_name(_P("pkg/Mixed_Case.pyw"), "") == "pkg.Mixed_Case"


def test_declaration_signals_project_reviewed_kinds_and_identity() -> None:
    producer = PythonGraphProducer()
    context = _context("app/api.py")
    content = (FIXTURE / "app/api.py").read_bytes()
    parsed = producer.parse(context, content)

    assert parsed.fallback_required is False
    assert parsed.metadata["graph_parse_status"] == "ast"
    kinds = {(s.name, s.kind) for s in parsed.symbols}
    assert kinds == {
        ("ApiHandler", "class"),
        ("handle", "method"),
        ("handle_async", "method"),
        ("Pagination", "class"),
        ("page_size", "method"),
        ("make_handler", "function"),
        ("stream_handler", "function"),
    }

    chunks = (_chunk_for("app/api.py", 1, 400, "chunk-all"),)
    graph = producer.materialize(
        context, parsed, chunks, _module_signal("app/api.py")
    )

    by_name = {signal.qualified_name: signal for signal in graph.signals}
    handler = by_name["app.api.ApiHandler"]
    assert handler.kind == "type"
    assert handler.producer == "python_ast"
    assert handler.language == "python"
    assert handler.recallable is True
    assert handler.signature == ""
    assert handler.arity is None
    assert handler.chunk_id == "chunk-all"
    method = by_name["app.api.ApiHandler.Pagination.page_size"]
    assert method.kind == "method"
    function = by_name["app.api.make_handler"]
    assert function.kind == "function"
    assert by_name["app.api.ApiHandler.handle_async"].metadata["is_async"] is True

    expected_id = generate_v5_signal_id(
        file_path="app/api.py",
        kind="type",
        qualified_name="app.api.ApiHandler",
        signature="",
        start_line=handler.start_line,
        start_column=handler.start_column,
        end_line=handler.end_line,
        end_column=handler.end_column,
        producer="python_ast",
    )
    assert handler.signal_id == expected_id


def test_init_signals_use_containing_package_name() -> None:
    producer = PythonGraphProducer()
    context = _context("app/dupe/__init__.py")
    parsed = producer.parse(
        context, (FIXTURE / "app/dupe/__init__.py").read_bytes()
    )
    chunks = (_chunk_for("app/dupe/__init__.py", 1, 40, "chunk-init"),)

    graph = producer.materialize(
        context, parsed, chunks, _module_signal("app/dupe/__init__.py")
    )

    assert [signal.qualified_name for signal in graph.signals] == [
        "app.dupe.dupe_package_function"
    ]


def test_missing_chunk_attachment_fails_closed() -> None:
    producer = PythonGraphProducer()
    context = _context("app/api.py")
    parsed = producer.parse(context, (FIXTURE / "app/api.py").read_bytes())
    chunks = (_chunk_for("app/api.py", 1, 2, "chunk-tiny"),)

    graph = producer.materialize(
        context, parsed, chunks, _module_signal("app/api.py")
    )

    assert graph.signals == ()
    assert graph.relations == ()
    assert graph.metadata["graph_materialize_status"] == "missing_chunk"


def test_signal_ordering_is_input_order_independent() -> None:
    producer = PythonGraphProducer()
    context = _context("app/service.py")
    parsed = producer.parse(context, (FIXTURE / "app/service.py").read_bytes())
    chunks = (_chunk_for("app/service.py", 1, 400, "chunk-all"),)

    first = producer.materialize(
        context, parsed, chunks, _module_signal("app/service.py")
    )
    second = producer.materialize(
        context, parsed, tuple(reversed(chunks)), _module_signal("app/service.py")
    )

    assert [s.signal_id for s in first.signals] == [
        s.signal_id for s in second.signals
    ]
    ordering = [
        (s.start_line, s.start_column, s.end_line, s.end_column)
        for s in first.signals
    ]
    assert ordering == sorted(ordering)


def test_parse_failure_produces_no_symbols_and_bounded_metadata() -> None:
    producer = PythonGraphProducer()
    context = _context("app/broken.py")

    parsed = producer.parse(context, (FIXTURE / "app/broken.py").read_bytes())

    assert parsed.symbols == ()
    assert parsed.fallback_required is False
    assert parsed.metadata["graph_parse_status"] == "syntax_error"
    assert parsed.metadata["graph_diagnostics"] == {"syntax_error": 1}
    graph = producer.materialize(
        context,
        parsed,
        (_chunk_for("app/broken.py", 1, 40, "chunk-b"),),
        _module_signal("app/broken.py"),
    )
    assert graph.signals == ()
    assert graph.relations == ()


def test_v5_build_with_python_producer_materializes_symbol_chunks(
    tmp_path,
) -> None:
    from context_search_tool.config import DEFAULT_CONFIG
    from context_search_tool.indexer import (
        build_v5_index_snapshot,
        scan_workspace_v5,
    )
    from context_search_tool.sqlite_store import SQLiteStore

    repo = tmp_path / "repo"
    (repo / "app").mkdir(parents=True)
    (repo / "app" / "service.py").write_text(
        "import os\n\n\nclass OrderService:\n"
        "    def submit(self, payload):\n        return payload\n\n\n"
        "def build_order_service():\n    return OrderService()\n",
        encoding="utf-8",
    )
    (repo / "app" / "empty.py").write_text("", encoding="utf-8")

    producer = PythonGraphProducer()
    summary = build_v5_index_snapshot(
        repo,
        DEFAULT_CONFIG,
        graph_plugins=[producer],
        scanner=scan_workspace_v5,
    )
    assert summary.files_indexed >= 1

    store = SQLiteStore(repo / ".context-search" / "index.sqlite")
    chunks = store.chunks_for_file(_P("app/service.py"), limit=50)
    assert any(chunk.chunk_type == "symbol" for chunk in chunks)
    producer_tokens = {
        "orderservice",
        "order",
        "service",
        "submit",
        "build_order_service",
        "build",
    }
    for chunk in chunks:
        for token in chunk.lexical_tokens:
            if token.lower() in producer_tokens:
                assert token.lower() in chunk.content.lower()

    import sqlite3 as _sqlite3

    with _sqlite3.connect(repo / ".context-search" / "index.sqlite") as conn:
        conn.row_factory = _sqlite3.Row
        rows = conn.execute(
            """
            SELECT signal_id, kind, name, producer, file_path
            FROM code_signals WHERE deleted_at IS NULL
            """
        ).fetchall()
    by_file: dict[str, list] = {}
    for row in rows:
        by_file.setdefault(row["file_path"], []).append(row)
    service_rows = by_file.get("app/service.py", [])
    modules = [r for r in service_rows if r["kind"] == "module"]
    python_rows = [r for r in service_rows if r["producer"] == "python_ast"]
    assert len(modules) == 1
    assert sorted((r["kind"], r["name"]) for r in python_rows) == [
        ("function", "build_order_service"),
        ("method", "submit"),
        ("type", "OrderService"),
    ]
    ids = [r["signal_id"] for r in rows]
    assert len(ids) == len(set(ids))
    assert "app/empty.py" not in by_file


from context_search_tool.graph_contract import (
    MAX_PYTHON_IMPORTS_PER_FILE,
    generate_v5_relation_id,
)
from context_search_tool.python_graph import (
    PythonImportFact,
    PythonSourceRange,
    python_module_selector,
)

_FIXTURE_ACTIVE = (
    "__init__.py",
    "app/__init__.py",
    "app/api.py",
    "app/broken.py",
    "app/clients/__init__.py",
    "app/clients/text.py",
    "app/dupe.py",
    "app/dupe/__init__.py",
    "app/dynamic.py",
    "app/service.py",
    "lonely.py",
    "nested/pkg/__init__.py",
    "nested/pkg/consumer.py",
    "nested/pkg/target.py",
    "src/payments/__init__.py",
    "src/payments/engine.py",
    "tests/test_service.py",
)


def _selector_context(file_path: str, unit: str = "") -> PluginContext:
    units = tuple(
        (
            _P(path),
            "nested" if path.startswith("nested/") else "",
        )
        for path in _FIXTURE_ACTIVE
    )
    return PluginContext(
        file_path=_P(file_path),
        language="python",
        project_unit_key=unit,
        active_paths=tuple(_P(path) for path in _FIXTURE_ACTIVE),
        active_path_project_units=units,
    )


def _import_fact(
    module: str,
    level: int = 0,
    form: str = "import",
    star: bool = False,
    line: int = 1,
) -> PythonImportFact:
    return PythonImportFact(
        import_form=form,
        module=module,
        relative_level=level,
        is_star=star,
        range=PythonSourceRange(line, 0, line, 10),
    )


def test_python_import_budget_contract() -> None:
    assert MAX_PYTHON_IMPORTS_PER_FILE == 256


def test_selector_absolute_forms_resolve_by_active_paths() -> None:
    context = _selector_context("app/api.py")

    exact = python_module_selector(context, _import_fact("app.service"))
    assert exact.state == "exact"
    assert exact.specifier == "app.service"
    assert exact.candidates == ("app/service.py",)

    from_form = python_module_selector(
        context, _import_fact("app.service", form="from")
    )
    assert from_form.state == "exact"
    assert from_form.candidates == ("app/service.py",)

    star = python_module_selector(
        context, _import_fact("app.service", form="from", star=True)
    )
    assert star.state == "exact"

    package = python_module_selector(context, _import_fact("app.clients"))
    assert package.state == "exact"
    assert package.candidates == ("app/clients/__init__.py",)

    external = python_module_selector(context, _import_fact("json"))
    assert external.state == "external"
    assert external.candidates == ()


def test_selector_module_package_tie_is_ambiguous() -> None:
    context = _selector_context("app/api.py")

    tie = python_module_selector(context, _import_fact("app.dupe"))

    assert tie.state == "candidates"
    assert tie.candidates == ("app/dupe.py", "app/dupe/__init__.py")


def test_selector_src_root_layout_and_tie() -> None:
    context = _selector_context("src/payments/engine.py")

    src_spelling = python_module_selector(
        context, _import_fact("payments.engine", form="from")
    )
    assert src_spelling.state == "exact"
    assert src_spelling.candidates == ("src/payments/engine.py",)

    root_spelling = python_module_selector(
        context, _import_fact("src.payments.engine", form="from")
    )
    assert root_spelling.state == "exact"
    assert root_spelling.candidates == ("src/payments/engine.py",)


def test_selector_relative_forms() -> None:
    context = _selector_context("app/api.py")

    sibling = python_module_selector(
        context, _import_fact("service", level=1, form="from")
    )
    assert sibling.state == "exact"
    assert sibling.specifier == ".service"
    assert sibling.candidates == ("app/service.py",)

    parent = python_module_selector(
        context,
        _import_fact("clients", level=2, form="from"),
    )
    assert parent.state == "unresolved"

    from_clients = python_module_selector(
        _selector_context("app/clients/text.py"),
        _import_fact("clients", level=2, form="from"),
    )
    assert from_clients.state == "exact"
    assert from_clients.candidates == ("app/clients/__init__.py",)

    escape = python_module_selector(
        context, _import_fact("app", level=3, form="from")
    )
    assert escape.state == "unresolved"

    bare_star = python_module_selector(
        _selector_context("app/service.py"),
        _import_fact("", level=1, form="from", star=True),
    )
    assert bare_star.state == "exact"
    assert bare_star.candidates == ("app/__init__.py",)

    rootless = python_module_selector(
        _selector_context("lonely.py"),
        _import_fact("orphan", level=1, form="from"),
    )
    assert rootless.state == "unresolved"


def test_selector_unit_root_init_sibling_exception() -> None:
    context = _selector_context("__init__.py")

    sibling = python_module_selector(
        context, _import_fact("lonely", level=1, form="from")
    )

    assert sibling.state == "exact"
    assert sibling.candidates == ("lonely.py",)


def test_selector_cross_unit_target_is_not_selected() -> None:
    context = _selector_context("nested/pkg/consumer.py", unit="nested")

    same_unit = python_module_selector(context, _import_fact("pkg.target"))
    assert same_unit.state == "exact"
    assert same_unit.candidates == ("nested/pkg/target.py",)

    cross_unit = python_module_selector(
        context, _import_fact("app.service", form="from")
    )
    assert cross_unit.state == "external"
    assert cross_unit.candidates == ()


def test_import_relations_project_exact_v5_rows() -> None:
    producer = PythonGraphProducer()
    context = _selector_context("app/api.py")
    parsed = producer.parse(context, (FIXTURE / "app/api.py").read_bytes())
    chunks = (_chunk_for("app/api.py", 1, 400, "chunk-all"),)
    module_signal = _module_signal("app/api.py")

    graph = producer.materialize(context, parsed, chunks, module_signal)

    by_target = {
        relation.metadata["specifier"]: relation for relation in graph.relations
    }
    # `import app.service` and `from .service import ...` resolve to the same
    # target module, so they merge into one relation per the design.
    assert set(by_target) == {"json", "app.service", "app.clients.text"}
    relation = by_target["app.service"]
    assert relation.metadata["occurrence_count"] == 2
    assert relation.source_signal_id == module_signal.signal_id
    assert relation.kind == "imports"
    assert relation.target_kind == "module"
    assert relation.producer == "python_ast"
    assert relation.producer_confidence == 1.0
    assert relation.resolution == "unresolved"
    assert relation.target_qualified_name == "app/service.py"
    assert relation.metadata["selector_state"] == "exact"
    assert relation.metadata["import_form"] == "import"
    assert relation.metadata["relative_level"] == 0
    assert relation.metadata["first_source_line"] == 2
    expected_id = generate_v5_relation_id(
        source_signal_id=module_signal.signal_id,
        kind="imports",
        target_kind="module",
        target_qualified_name="app/service.py",
        target_signature="",
        target_arity=None,
        target_project_unit_key="",
        producer="python_ast",
    )
    assert relation.relation_id == expected_id
    assert "bindings" not in relation.metadata
    assert "aliases" not in relation.metadata


def test_repeated_imports_merge_and_distinct_targets_do_not() -> None:
    producer = PythonGraphProducer()
    context = _selector_context("app/service.py")
    parsed = producer.parse(
        context, (FIXTURE / "app/service.py").read_bytes()
    )
    chunks = (_chunk_for("app/service.py", 1, 400, "chunk-all"),)

    graph = producer.materialize(
        context, parsed, chunks, _module_signal("app/service.py")
    )

    clients = [
        relation
        for relation in graph.relations
        if relation.target_qualified_name == "app/clients/__init__.py"
    ]
    assert len(clients) == 1
    assert clients[0].metadata["occurrence_count"] == 2
    assert clients[0].metadata["first_source_line"] == 2
    specs = sorted(
        relation.metadata["specifier"] for relation in graph.relations
    )
    assert specs == sorted(
        ["os", "app.dupe", ".clients", "..app", "app.api", "app.clients.text"]
    )


def test_import_cap_retains_first_256_and_records_omission() -> None:
    producer = PythonGraphProducer()
    lines = b"".join(
        b"import external_module_%03d\n" % index for index in range(257)
    )
    context = _selector_context("app/api.py")
    parsed = producer.parse(context, lines)
    chunks = (_chunk_for("app/api.py", 1, 400, "chunk-all"),)

    graph = producer.materialize(
        context, parsed, chunks, _module_signal("app/api.py")
    )

    assert len(graph.relations) == 256
    specs = [relation.metadata["specifier"] for relation in graph.relations]
    assert specs[0] == "external_module_000"
    assert specs[-1] == "external_module_255"
    assert graph.metadata["graph_omitted_imports"] == 1
