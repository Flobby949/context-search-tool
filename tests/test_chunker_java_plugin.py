from pathlib import Path

from context_search_tool.chunker import chunk_text, expand_lines
from context_search_tool.java_plugin import JavaPlugin


JAVA_SOURCE = """
package com.example.audit;

import org.apache.ibatis.annotations.Select;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/apply/audit")
public class ApplyAuditController {
    @PostMapping("/pageEs")
    public String pageEs(String applyType) {
        return "ok";
    }

    /**
     * 工作台统计-待我审核
     */
    @GetMapping("/stats/wait")
    public Map<String, Long> statsWait() {
        return resourceAuditService.statsWait();
    }

    /**
     * 工作台统计-审核列表
     */
    @PostMapping("/stats")
    public WorkbenchResourceAuditStatsDTO auditStats(@RequestBody ApplyAuditEsSearchQry qry) {
        return resourceAuditService.auditStats(qry);
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


def test_expand_lines_bounds_out_of_range_inputs() -> None:
    start_line, end_line, content = expand_lines(["one", "two", "three"], 10, 12, 2, 2)

    assert (start_line, end_line) == (1, 3)
    assert content == "one\ntwo\nthree"


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
    assert extraction.relations == []
    assert extraction.metadata["package"] == "com.example.audit"


def test_java_plugin_emits_spring_endpoint_signals_with_comment_tokens() -> None:
    extraction = JavaPlugin().extract(Path("ApplyAuditController.java"), JAVA_SOURCE)
    signals = {signal.name: signal for signal in extraction.signals}

    wait_signal = signals["GET /apply/audit/stats/wait"]
    stats_signal = signals["POST /apply/audit/stats"]

    assert wait_signal.kind == "endpoint"
    assert wait_signal.metadata["http_method"] == "GET"
    assert wait_signal.metadata["path"] == "/apply/audit/stats/wait"
    assert wait_signal.metadata["controller"] == "ApplyAuditController"
    assert wait_signal.metadata["method"] == "statsWait"
    assert "工作台统计" in wait_signal.tokens
    assert "待我审核" in wait_signal.tokens

    assert stats_signal.kind == "endpoint"
    assert stats_signal.metadata["http_method"] == "POST"
    assert stats_signal.metadata["path"] == "/apply/audit/stats"
    assert stats_signal.metadata["controller"] == "ApplyAuditController"
    assert stats_signal.metadata["method"] == "auditStats"
    assert "工作台统计" in stats_signal.tokens
    assert "审核列表" in stats_signal.tokens


def test_java_plugin_emits_comment_signals_linked_to_owner_method() -> None:
    extraction = JavaPlugin().extract(Path("ApplyAuditController.java"), JAVA_SOURCE)
    comment_signals = [
        signal
        for signal in extraction.signals
        if signal.kind == "comment" and signal.metadata.get("owner_method") == "statsWait"
    ]

    [comment_signal] = comment_signals
    assert comment_signal.name == "statsWait comment"
    assert "工作台统计" in comment_signal.metadata["text"]
    assert "待我审核" in comment_signal.metadata["text"]
    assert "工作台统计" in comment_signal.tokens
    assert "待我审核" in comment_signal.tokens
    assert comment_signal.metadata["owner_method"] == "statsWait"
    assert comment_signal.metadata["owner_type"] == "ApplyAuditController"


def test_java_plugin_emits_line_comment_signals_linked_to_owner_type() -> None:
    source = """
// 工作台入口控制器
class WorkbenchController {
}
""".strip()

    extraction = JavaPlugin().extract(Path("WorkbenchController.java"), source)
    [comment_signal] = [
        signal for signal in extraction.signals if signal.kind == "comment"
    ]

    assert comment_signal.name == "WorkbenchController comment"
    assert "工作台入口控制器" in comment_signal.metadata["text"]
    assert "工作台入口控制器" in comment_signal.tokens
    assert comment_signal.metadata["owner_type"] == "WorkbenchController"
    assert "owner_method" not in comment_signal.metadata


def test_java_plugin_emits_usage_signals_for_receiver_method_calls() -> None:
    extraction = JavaPlugin().extract(Path("ApplyAuditController.java"), JAVA_SOURCE)
    usage_signals = [
        signal
        for signal in extraction.signals
        if signal.kind == "usage" and signal.name == "resourceAuditService.statsWait"
    ]

    [usage_signal] = usage_signals
    assert usage_signal.metadata["receiver"] == "resourceAuditService"
    assert usage_signal.metadata["method"] == "statsWait"
    assert usage_signal.metadata["owner_method"] == "statsWait"


def test_java_plugin_dedupes_duplicate_usage_signals_on_same_line() -> None:
    source = """
class Example {
    void run() {
        x.y(); x.y();
    }
}
""".strip()

    extraction = JavaPlugin().extract(Path("Example.java"), source)
    usage_signals = [
        signal for signal in extraction.signals if signal.kind == "usage"
    ]

    assert [signal.name for signal in usage_signals] == ["x.y"]
    assert len({signal.signal_id for signal in usage_signals}) == 1


def test_java_plugin_ignores_usage_text_inside_string_literals() -> None:
    source = """
class Example {
    String run() {
        return "foo.bar()";
    }
}
""".strip()

    extraction = JavaPlugin().extract(Path("Example.java"), source)
    usage_names = {
        signal.name for signal in extraction.signals if signal.kind == "usage"
    }

    assert "foo.bar" not in usage_names


def test_java_plugin_ignores_usage_text_inside_text_blocks() -> None:
    source = '''
class Example {
    String text() {
        return """
            foo.bar()
            """;
    }
}
'''.strip()

    extraction = JavaPlugin().extract(Path("Example.java"), source)
    usage_names = {
        signal.name for signal in extraction.signals if signal.kind == "usage"
    }

    assert "foo.bar" not in usage_names


def test_java_plugin_ignores_obvious_static_usage_calls() -> None:
    source = """
class Example {
    int max(int a, int b) {
        return Math.max(a, b);
    }
}
""".strip()

    extraction = JavaPlugin().extract(Path("Example.java"), source)
    usage_names = {
        signal.name for signal in extraction.signals if signal.kind == "usage"
    }

    assert "Math.max" not in usage_names


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
    [signal] = extraction.signals
    assert signal.kind == "endpoint"
    assert signal.name == "GET /items"
    assert signal.metadata["http_method"] == "GET"
    assert signal.metadata["path"] == "/items"


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


def test_java_plugin_extracts_multiline_method_signature_route() -> None:
    source = """
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;

@RequestMapping("/foos")
class FooController {
    @PostMapping("/create")
    public ResponseEntity<Foo> create(
        @RequestBody FooRequest request
    ) {
        return ok();
    }
}
""".strip()

    extraction = JavaPlugin().extract(Path("FooController.java"), source)
    method_names = {
        symbol.name for symbol in extraction.symbols if symbol.kind == "method"
    }

    assert "create" in method_names
    assert "/create" in extraction.lexical_tokens
    assert "/foos/create" in extraction.lexical_tokens
    assert "post" in extraction.lexical_tokens


def test_java_plugin_extracts_long_multiline_mapping_annotation() -> None:
    source = """
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestMethod;

class ItemController {
    @RequestMapping(
        value = "/items",
        method = RequestMethod.POST,
        produces = "application/json",
        consumes = "application/json"
    )
    public String createItem() {
        return "ok";
    }
}
""".strip()

    extraction = JavaPlugin().extract(Path("ItemController.java"), source)
    method_names = {
        symbol.name for symbol in extraction.symbols if symbol.kind == "method"
    }

    assert "createItem" in method_names
    assert "/items" in extraction.lexical_tokens
    assert "post" in extraction.lexical_tokens


def test_java_plugin_ignores_commented_out_symbols_and_routes() -> None:
    source = """
// @GetMapping("/old")
// class OldController {}
/*
@PostMapping("/dead")
class DeadController {}
*/
class LiveController {}
""".strip()

    extraction = JavaPlugin().extract(Path("Controllers.java"), source)
    symbol_names = {symbol.name for symbol in extraction.symbols}

    assert "LiveController" in symbol_names
    assert "OldController" not in symbol_names
    assert "DeadController" not in symbol_names
    assert "/old" not in extraction.lexical_tokens
    assert "/dead" not in extraction.lexical_tokens


def test_java_plugin_preserves_comment_markers_inside_route_literals() -> None:
    source = """
import org.springframework.web.bind.annotation.GetMapping;

class ProxyController {
    @GetMapping("/proxy/http://target")
    String proxy() {
        return "ok";
    }
}
""".strip()

    extraction = JavaPlugin().extract(Path("ProxyController.java"), source)

    assert "/proxy/http://target" in extraction.lexical_tokens
    assert "proxy" in extraction.lexical_tokens
    assert "target" in extraction.lexical_tokens


def test_java_plugin_ignores_commented_package_and_import_lines() -> None:
    source = """
// package com.example.dead;
package com.example.live;

// import com.example.DeadImport;
import com.example.LiveImport;

class PackageImportController {}
""".strip()

    extraction = JavaPlugin().extract(Path("PackageImportController.java"), source)

    assert extraction.metadata["package"] == "com.example.live"
    assert extraction.metadata["imports"] == ["com.example.LiveImport"]
    assert "liveimport" in extraction.lexical_tokens
    assert "deadimport" not in extraction.lexical_tokens
    assert "dead" not in extraction.lexical_tokens


def test_java_plugin_extracts_long_multiline_class_mapping_route() -> None:
    source = """
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;

@RequestMapping(
    value = "/api",
    produces = "application/json",
    consumes = "application/json"
)
class UserController {
    @GetMapping("/users")
    String users() {
        return "ok";
    }
}
""".strip()

    extraction = JavaPlugin().extract(Path("UserController.java"), source)
    method_names = {
        symbol.name for symbol in extraction.symbols if symbol.kind == "method"
    }

    assert "users" in method_names
    assert "/api" in extraction.lexical_tokens
    assert "/users" in extraction.lexical_tokens
    assert "/api/users" in extraction.lexical_tokens
    assert "get" in extraction.lexical_tokens


def test_java_plugin_does_not_reuse_previous_method_mapping_for_unannotated_method() -> None:
    source = """
import org.springframework.web.bind.annotation.GetMapping;

class ItemController {
    @GetMapping("/a")
    String a() {
        return "ok";
    }

    String b() {
        return "ok";
    }
}
""".strip()

    extraction = JavaPlugin().extract(Path("ItemController.java"), source)

    assert [(signal.name, signal.metadata["method"]) for signal in extraction.signals] == [
        ("GET /a", "a")
    ]


def test_java_plugin_uses_outer_class_context_after_nested_class() -> None:
    source = """
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;

@RequestMapping("/outer")
class OuterController {
    @RequestMapping("/inner")
    class InnerController {
        @GetMapping("/inside")
        String inside() {
            return "ok";
        }
    }

    @GetMapping("/after")
    String after() {
        return "ok";
    }
}
""".strip()

    extraction = JavaPlugin().extract(Path("OuterController.java"), source)
    signals = {signal.name: signal for signal in extraction.signals}

    assert "GET /outer/after" in signals
    assert "GET /inner/after" not in signals
    assert signals["GET /outer/after"].metadata["controller"] == "OuterController"
    assert signals["GET /outer/after"].metadata["method"] == "after"


def test_java_plugin_does_not_attach_comment_tokens_across_blank_line() -> None:
    source = """
import org.springframework.web.bind.annotation.GetMapping;

class CommentController {
    /**
     * stale docs
     */

    @GetMapping("/fresh")
    String fresh() {
        return "ok";
    }
}
""".strip()

    extraction = JavaPlugin().extract(Path("CommentController.java"), source)
    [signal] = extraction.signals

    assert signal.name == "GET /fresh"
    assert "stale" not in signal.tokens
    assert "docs" not in signal.tokens


def test_java_plugin_ignores_string_literal_braces_when_tracking_class_context() -> None:
    source = """
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;

@RequestMapping("/api")
class JsonController {
    String literalBrace() {
        return "{";
    }

    @GetMapping("/json")
    String json() {
        return "{}";
    }
}
""".strip()

    extraction = JavaPlugin().extract(Path("JsonController.java"), source)
    signals = {signal.name: signal for signal in extraction.signals}

    assert "GET /api/json" in signals
    assert "GET /json" not in signals
    assert signals["GET /api/json"].metadata["controller"] == "JsonController"
    assert signals["GET /api/json"].metadata["method"] == "json"
