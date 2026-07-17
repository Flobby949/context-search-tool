from __future__ import annotations

import importlib
import importlib.metadata
import socket
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable

import pytest
import tree_sitter_java
import tree_sitter_javascript
import tree_sitter_typescript
from tree_sitter import Language, Tree


EXPECTED_VERSIONS = {
    "tree-sitter": "0.26.0",
    "tree-sitter-java": "0.23.5",
    "tree-sitter-javascript": "0.25.0",
    "tree-sitter-typescript": "0.23.2",
    "defusedxml": "0.7.1",
}

VALID_SOURCES = {
    "parse_java": (
        b"class Example { int value() { return 1; } }",
        "program",
    ),
    "parse_javascript": (b"export function value() { return 1; }", "program"),
    "parse_jsx": (b"const view = <section>{value}</section>;", "program"),
    "parse_typescript": (b"const value: number = 1;", "program"),
    "parse_tsx": (b"const View = () => <section />;", "program"),
}

MALFORMED_SOURCES = {
    "parse_java": b"class Broken { void run( {",
    "parse_javascript": b"function broken( {",
    "parse_jsx": b"const view = <section>",
    "parse_typescript": b"const value: =",
    "parse_tsx": b"const View = <section>",
}


def _module():
    return importlib.import_module("context_search_tool.syntax_parsers")


def _walk(node):
    yield node
    for child in node.children:
        yield from _walk(child)


def test_p5_parser_dependencies_have_exact_versions() -> None:
    assert {
        name: importlib.metadata.version(name) for name in EXPECTED_VERSIONS
    } == EXPECTED_VERSIONS


def test_packaged_language_capsules_construct_without_runtime_builds() -> None:
    languages = (
        Language(tree_sitter_java.language()),
        Language(tree_sitter_javascript.language()),
        Language(tree_sitter_typescript.language_typescript()),
        Language(tree_sitter_typescript.language_tsx()),
    )

    assert all(isinstance(language, Language) for language in languages)
    assert [language.abi_version for language in languages] == [14, 15, 14, 14]
    assert [language.node_kind_count for language in languages] == [321, 265, 383, 400]
    assert len(set(languages)) == 4


@pytest.mark.parametrize(
    ("function_name", "source_and_root"),
    VALID_SOURCES.items(),
)
def test_explicit_parse_functions_return_valid_trees(
    function_name: str,
    source_and_root: tuple[bytes, str],
) -> None:
    source, expected_root = source_and_root
    parse: Callable[[bytes], Tree] = getattr(_module(), function_name)

    tree = parse(source)

    assert isinstance(tree, Tree)
    assert tree.root_node.type == expected_root
    assert not tree.root_node.has_error
    assert tree.root_node.start_byte == 0
    assert tree.root_node.end_byte == len(source)


@pytest.mark.parametrize(("function_name", "source"), MALFORMED_SOURCES.items())
def test_malformed_sources_return_bounded_error_trees(
    function_name: str,
    source: bytes,
) -> None:
    parse: Callable[[bytes], Tree] = getattr(_module(), function_name)

    tree = parse(source)

    assert tree.root_node.has_error
    assert tree.root_node.start_byte == 0
    assert tree.root_node.end_byte <= len(source)
    assert tree.root_node.descendant_count <= 128


def test_java_parser_reports_utf8_byte_offsets() -> None:
    source = "class Café { int 数量; }".encode()

    tree = _module().parse_java(source)
    identifiers = {
        source[node.start_byte : node.end_byte]: (node.start_byte, node.end_byte)
        for node in _walk(tree.root_node)
        if node.type == "identifier"
    }

    assert identifiers["Café".encode()] == (6, 11)
    assert identifiers["数量".encode()] == (18, 24)


def test_concurrent_parse_calls_use_isolated_parser_state() -> None:
    module = _module()
    calls = [
        (getattr(module, function_name), source, expected_root)
        for function_name, (source, expected_root) in VALID_SOURCES.items()
    ] * 8

    def parse_one(call: tuple[Callable[[bytes], Tree], bytes, str]) -> tuple[str, int]:
        parse, source, expected_root = call
        tree = parse(source)
        assert not tree.root_node.has_error
        return expected_root, tree.root_node.end_byte

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = tuple(executor.map(parse_one, calls))

    assert results == tuple(
        (expected_root, len(source)) for _, source, expected_root in calls
    )


def test_parser_module_import_uses_no_socket_or_subprocess(monkeypatch) -> None:
    def blocked(*_args, **_kwargs):
        raise AssertionError("parser module attempted external work during import")

    monkeypatch.setattr(socket, "socket", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(subprocess, "Popen", blocked)
    monkeypatch.setattr(subprocess, "run", blocked)
    monkeypatch.setattr(subprocess, "call", blocked)
    monkeypatch.setattr(subprocess, "check_call", blocked)
    monkeypatch.setattr(subprocess, "check_output", blocked)
    sys.modules.pop("context_search_tool.syntax_parsers", None)

    module = importlib.import_module("context_search_tool.syntax_parsers")

    assert tuple(name for name in dir(module) if name.startswith("parse_")) == (
        "parse_java",
        "parse_javascript",
        "parse_jsx",
        "parse_tsx",
        "parse_typescript",
    )


def test_parser_module_has_no_dynamic_build_or_repository_io() -> None:
    source = Path(_module().__file__).read_text(encoding="utf-8")

    assert "build_library" not in source
    assert "subprocess" not in source
    assert "socket" not in source
    assert "Path(" not in source
