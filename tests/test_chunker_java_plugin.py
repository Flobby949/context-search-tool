from pathlib import Path

from context_search_tool.chunker import chunk_text
from context_search_tool.java_plugin import JavaPlugin


JAVA_SOURCE = """
package com.example.audit;

import org.apache.ibatis.annotations.Select;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/apply/audit")
public class ApplyAuditController {
    @PostMapping("/pageEs")
    public String pageEs(String applyType) {
        return "ok";
    }
}

enum AuditStatus {
    INVOLVED_BY_ME,
    TOTAL_OVERVIEW
}

interface ApplyAuditMapper {
    @Select("SELECT * FROM audit WHERE status = #{status}")
    String findByStatus(String status);
}
""".strip()


def test_generic_chunker_preserves_line_ranges() -> None:
    chunks = chunk_text(Path("README.md"), "line1\nline2\nline3\n", "markdown", [], max_lines=2)

    assert [(chunk.start_line, chunk.end_line) for chunk in chunks] == [(1, 2), (3, 3)]
    assert chunks[0].content == "line1\nline2"


def test_java_plugin_extracts_routes_sql_and_enum_values() -> None:
    plugin = JavaPlugin()
    extraction = plugin.extract(Path("ApplyAuditController.java"), JAVA_SOURCE)

    symbol_names = {symbol.name for symbol in extraction.symbols}

    assert "ApplyAuditController" in symbol_names
    assert "pageEs" in symbol_names
    assert "INVOLVED_BY_ME" in symbol_names
    assert "TOTAL_OVERVIEW" in symbol_names
    assert "/apply/audit/pageEs" in extraction.lexical_tokens
    assert "select" in extraction.lexical_tokens
    assert "audit" in extraction.lexical_tokens
    assert "status" in extraction.lexical_tokens
    assert extraction.metadata["package"] == "com.example.audit"


def test_java_plugin_extracts_multiline_mapping_routes_and_methods() -> None:
    source = """
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestMethod;

class ItemController {
    @RequestMapping(
        value = "/items",
        method = RequestMethod.GET
    )
    String items() {
        return "ok";
    }
}
""".strip()

    extraction = JavaPlugin().extract(Path("ItemController.java"), source)

    assert "/items" in extraction.lexical_tokens
    assert "items" in extraction.lexical_tokens
    assert "get" in extraction.lexical_tokens


def test_java_plugin_extracts_single_line_enum_values() -> None:
    extraction = JavaPlugin().extract(Path("Status.java"), "enum Status { ACTIVE, DISABLED }")
    symbol_names = {symbol.name for symbol in extraction.symbols}

    assert "ACTIVE" in symbol_names
    assert "DISABLED" in symbol_names
    assert "active" in extraction.lexical_tokens
    assert "disabled" in extraction.lexical_tokens


def test_java_plugin_extracts_class_level_route_without_method_mapping() -> None:
    source = """
import org.springframework.web.bind.annotation.RequestMapping;

@RequestMapping("/api")
class ApiController {
}
""".strip()

    extraction = JavaPlugin().extract(Path("ApiController.java"), source)

    assert "/api" in extraction.lexical_tokens
    assert "api" in extraction.lexical_tokens


def test_java_plugin_ignores_enum_constructor_and_literal_noise() -> None:
    source = '''
enum Status {
    ACTIVE("A"),
    DISABLED("D");

    Status(String code) {}
}
'''.strip()

    extraction = JavaPlugin().extract(Path("Status.java"), source)
    symbols_by_kind = {(symbol.name, symbol.kind) for symbol in extraction.symbols}

    assert ("ACTIVE", "enum_value") in symbols_by_kind
    assert ("DISABLED", "enum_value") in symbols_by_kind
    assert ("A", "enum_value") not in symbols_by_kind
    assert ("D", "enum_value") not in symbols_by_kind
    assert ("Status", "method") not in symbols_by_kind
    assert "active" in extraction.lexical_tokens
    assert "disabled" in extraction.lexical_tokens
    assert "a" not in extraction.lexical_tokens
    assert "d" not in extraction.lexical_tokens


def test_java_plugin_does_not_reuse_class_route_for_unannotated_method() -> None:
    source = """
import org.springframework.web.bind.annotation.RequestMapping;

@RequestMapping("/api")
class ApiController {
    String index() {
        return "ok";
    }
}
""".strip()

    extraction = JavaPlugin().extract(Path("ApiController.java"), source)

    assert "/api" in extraction.lexical_tokens
    assert "api" in extraction.lexical_tokens
    assert "/api/api" not in extraction.lexical_tokens


def test_java_plugin_does_not_extract_method_body_calls_as_methods() -> None:
    source = """
class Example {
    String actualMethod() {
        return helper(value);
    }
}
""".strip()

    extraction = JavaPlugin().extract(Path("Example.java"), source)
    method_names = {
        symbol.name for symbol in extraction.symbols if symbol.kind == "method"
    }

    assert "actualMethod" in method_names
    assert "helper" not in method_names


def test_java_plugin_does_not_leak_class_route_to_later_class() -> None:
    source = """
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;

@RequestMapping("/api")
class FirstController {}

class SecondController {
    @GetMapping("/health")
    String health() {
        return "ok";
    }
}
""".strip()

    extraction = JavaPlugin().extract(Path("Controllers.java"), source)

    assert "/health" in extraction.lexical_tokens
    assert "/api/health" not in extraction.lexical_tokens
