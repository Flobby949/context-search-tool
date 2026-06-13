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
