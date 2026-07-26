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
