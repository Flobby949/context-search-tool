from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from context_search_tool.config import DEFAULT_CONFIG
from context_search_tool.java_ast import extract_java_facts
from context_search_tool.graph_contract import (
    generate_core_module_signal_id,
    generate_v5_relation_id,
)
from context_search_tool.graph_plugins import PluginContext
from context_search_tool.indexer import index_repository
from context_search_tool.java_graph import JavaGraphProducer
from context_search_tool.java_plugin import JavaPlugin
from context_search_tool.models import CodeSignal, DocumentChunk
from context_search_tool.retrieval_core import candidates
from context_search_tool.sqlite_store import SQLiteStore


ROOT = Path(__file__).resolve().parents[1]
JAVA_FIXTURES = ROOT / "tests" / "fixtures" / "p5-language-graphs"


def _omitted(facts, category: str) -> int:
    return sum(
        omission.count
        for omission in facts.omissions
        if omission.category == category
    )


def _assert_no_structural_facts(facts) -> None:
    assert facts.package_fact is None
    assert facts.imports == ()
    assert facts.types == ()
    assert facts.fields == ()
    assert facts.methods == ()
    assert facts.parameters == ()
    assert facts.locals == ()
    assert facts.annotations == ()
    assert facts.calls == ()
    assert facts.type_uses == ()
    assert facts.comments == ()
    assert facts.lexical_tokens == ()
    assert facts.annotation_sql_tokens == ()


def test_valid_parse_returns_one_deeply_immutable_fact_set() -> None:
    facts = extract_java_facts(
        b"package demo; final class Example { int value() { return 1; } }"
    )

    assert facts.fallback_required is False
    assert facts.package_fact is not None
    assert facts.package_fact.name == "demo"
    assert tuple(fact.name for fact in facts.types) == ("Example",)
    assert tuple(fact.name for fact in facts.methods) == ("value",)
    assert isinstance(facts.types, tuple)
    with pytest.raises(FrozenInstanceError):
        facts.fallback_required = True  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        facts.types[0].name = "Changed"  # type: ignore[misc]


@pytest.mark.parametrize(
    "source",
    [
        b"package broken class Example {}",
        b"package demo; import com.example.; class Example {}",
        b"package demo; class Example { int value( { }",
        b"package demo; class Example { void run() { int value = ; } }",
        b"package demo; @Route( class Example {}",
        b"package demo; class Example { void run() { target.call( ; } }",
        b"package demo; class Example {} trailing ???",
    ],
)
def test_any_error_or_missing_node_forces_whole_file_fallback(source: bytes) -> None:
    facts = extract_java_facts(source)

    assert facts.fallback_required is True
    assert facts.parse_error_count >= 1
    _assert_no_structural_facts(facts)


def test_comments_strings_text_blocks_and_annotation_prose_are_not_structure() -> None:
    source = b'''package demo;
class Real {
    String text = "class Fake { void ghost() { target.call(); } }";
    String block = """
        @RestController class TextFake {}
        imported.fake.Type.call();
        """;
    // class CommentFake { void nope() {} }
    /* @Mapper interface AlsoFake {} */
    void actual() {}
}
'''
    facts = extract_java_facts(source)

    assert facts.fallback_required is False
    assert tuple(fact.name for fact in facts.types) == ("Real",)
    assert tuple(fact.name for fact in facts.methods) == ("actual",)
    assert facts.calls == ()
    assert facts.annotations == ()


def test_ranges_use_original_utf8_bytes_and_one_based_lines() -> None:
    source = (
        "package demo;\n"
        "/*\u732b*/ class Caf\u00e9 {\n"
        "    String r\u00e9sum\u00e9;\n"
        "    void run(String \u503c) { String \u672c\u5730 = \u503c; }\n"
        "}\n"
    ).encode("utf-8")
    facts = extract_java_facts(source)

    type_fact = facts.types[0]
    field = facts.fields[0]
    parameter = facts.parameters[0]
    local = facts.locals[0]
    assert type_fact.source_range.start_line == 2
    assert type_fact.source_range.start_column == len("/*\u732b*/ ".encode("utf-8"))
    assert type_fact.name_range.start_column == len("/*\u732b*/ class ".encode("utf-8"))
    assert field.name_range.start_column == len("    String ".encode("utf-8"))
    assert field.name_range.end_column - field.name_range.start_column == len(
        "r\u00e9sum\u00e9".encode("utf-8")
    )
    assert parameter.name_range.start_line == 4
    assert parameter.name_range.end_column - parameter.name_range.start_column == 3
    assert local.name_range.end_column - local.name_range.start_column == 6


def test_nested_declarations_and_erased_signatures_are_canonical() -> None:
    source = b'''package com.example;
import com.acme.Service;
import com.alpha.*;
import com.beta.*;
class Local {}
class Outer<T> implements Api {
    class Inner {
        Inner(Service... services) {}
        void exact(Service service, Local local, int... ids) {}
        <U> U unresolved(T value, U other) { return other; }
    }
}
'''
    facts = extract_java_facts(source)

    assert tuple(fact.qualified_name for fact in facts.types) == (
        "com.example.Local",
        "com.example.Outer",
        "com.example.Outer$Inner",
    )
    outer = next(fact for fact in facts.types if fact.name == "Outer")
    [implemented] = outer.implements
    assert implemented.qualified_name == ""
    assert implemented.candidates == (
        "com.example.Api",
        "com.alpha.Api",
        "com.beta.Api",
    )

    constructor = next(fact for fact in facts.methods if fact.kind == "constructor")
    assert constructor.name == "<init>"
    assert constructor.qualified_name == "com.example.Outer$Inner.<init>"
    assert constructor.signature == "(com.acme.Service[])"
    assert constructor.is_varargs is True
    exact = next(fact for fact in facts.methods if fact.name == "exact")
    assert exact.signature == "(com.acme.Service,com.example.Local,int[])"
    exact_parameters = tuple(
        parameter
        for parameter in facts.parameters
        if parameter.owner_qualified_name == exact.qualified_name
    )
    assert tuple(parameter.type_ref.erased for parameter in exact_parameters) == (
        "Service",
        "Local",
        "int[]",
    )
    assert [parameter.is_varargs for parameter in exact_parameters] == [
        False,
        False,
        True,
    ]
    unresolved = next(fact for fact in facts.methods if fact.name == "unresolved")
    assert unresolved.signature == ""
    unresolved_parameters = [
        parameter
        for parameter in facts.parameters
        if parameter.owner_qualified_name == unresolved.qualified_name
    ]
    assert [parameter.type_ref.resolution for parameter in unresolved_parameters] == [
        "type_variable",
        "type_variable",
    ]


def test_explicit_imports_and_wildcards_remain_local_type_evidence() -> None:
    source = b'''package demo;
import alpha.Exact;
import one.*;
import two.*;
class Example {
    Exact exact;
    Candidate candidate;
    java.util.List<String> external;
}
'''
    facts = extract_java_facts(source)
    by_name = {field.name: field.type_ref for field in facts.fields}

    assert by_name["exact"].qualified_name == "alpha.Exact"
    assert by_name["exact"].resolution == "explicit_import"
    assert by_name["candidate"].qualified_name == ""
    assert by_name["candidate"].candidates == (
        "demo.Candidate",
        "one.Candidate",
        "two.Candidate",
    )
    assert by_name["external"].qualified_name == "java.util.List"
    assert by_name["external"].erased == "java.util.List"


def test_nested_imports_and_type_use_annotations_do_not_corrupt_erasure() -> None:
    source = b'''package demo;
import com.acme.Outer.Inner;
class Example {
    java.util.@Readonly List<String> values;
    Inner nested;
}
'''
    facts = extract_java_facts(source)
    by_name = {field.name: field.type_ref for field in facts.fields}

    assert by_name["values"].erased == "java.util.List"
    assert by_name["values"].qualified_name == "java.util.List"
    assert by_name["nested"].qualified_name == "com.acme.Outer$Inner"


def test_records_compact_constructors_and_enum_members_are_facts() -> None:
    source = b'''package demo;
record Entry(String name, int value) {
    Entry { name.length(); }
}
enum State {
    READY;
    int code;
    void reset() {}
}
'''
    facts = extract_java_facts(source)

    assert tuple((fact.kind, fact.name) for fact in facts.fields) == (
        ("record_component", "name"),
        ("record_component", "value"),
        ("enum_constant", "READY"),
        ("field", "code"),
    )
    compact = next(fact for fact in facts.methods if fact.kind == "constructor")
    assert compact.signature == "(java.lang.String,int)"
    assert tuple(
        parameter.name
        for parameter in facts.parameters
        if parameter.owner_qualified_name == compact.qualified_name
    ) == ("name", "value")
    assert any(fact.name == "reset" for fact in facts.methods)
    [length_call] = [call for call in facts.calls if call.target_name == "length"]
    assert length_call.target_owner.qualified_name == "java.lang.String"


def test_closed_receiver_and_argument_evidence_drives_call_facts() -> None:
    source = b'''package demo;
import types.Dto;
import types.Service;
class Example {
    Service service;
    void run(Service parameter, Object unknown) {
        Dto dto = new Dto();
        this.service.accept(dto);
        parameter.accept((Dto) dto);
        {
            Service parameter = new Service();
            parameter.accept(dto);
        }
        parameter.accept("raw");
        ((Service) unknown).accept(new Dto());
        parameter.factory().accept(dto);
    }
}
'''
    facts = extract_java_facts(source)
    calls = [call for call in facts.calls if call.target_name == "accept"]

    assert len(calls) == 6
    assert [call.receiver_kind for call in calls[:3]] == [
        "field",
        "parameter",
        "local",
    ]
    assert all(call.target_owner.qualified_name == "types.Service" for call in calls[:3])
    assert all(call.target_signature == "(types.Dto)" for call in calls[:3])
    assert calls[3].target_signature == ""
    assert calls[4].receiver_kind == "cast"
    assert calls[4].target_owner.qualified_name == "types.Service"
    assert calls[4].target_signature == "(types.Dto)"
    assert calls[5].receiver_kind == "unresolved"
    assert calls[5].target_owner.qualified_name == ""

    constructors = [call for call in facts.calls if call.target_name == "<init>"]
    assert [(call.target_owner.qualified_name, call.target_signature) for call in constructors] == [
        ("types.Dto", "()"),
        ("types.Service", "()"),
        ("types.Dto", "()"),
    ]


def test_shadowing_lambda_anonymous_and_nested_type_scopes_fail_closed() -> None:
    source = b'''package demo;
import types.Dto;
import types.Service;
class Outer {
    Service service;
    void outer(Dto dto) {
        java.util.function.Consumer<Service> callback = service -> service.accept(dto);
        Runnable anonymous = new Runnable() {
            public void run() { service.accept(dto); }
        };
        class Local {
            Service service;
            void inner(Dto dto) { service.accept(dto); }
        }
    }
}
'''
    facts = extract_java_facts(source)
    accepts = [call for call in facts.calls if call.target_name == "accept"]

    lambda_call = min(accepts, key=lambda call: call.source_range.start_byte)
    assert lambda_call.source_method == "demo.Outer.outer"
    assert lambda_call.receiver_kind == "unresolved"
    assert not any(
        call.source_method == "demo.Outer.outer"
        and call.source_range.start_line == 9
        for call in accepts
    )
    nested_call = next(call for call in accepts if "$Local.inner" in call.source_method)
    assert nested_call.source_method == "demo.Outer$Local.inner"
    assert nested_call.receiver_kind == "field"


def test_explicitly_typed_lambda_parameter_is_closed_receiver_evidence() -> None:
    source = b'''package demo;
import types.Dto;
import types.Service;
class Example {
    void run(Dto dto) {
        java.util.function.Consumer<Service> callback =
            (Service service) -> service.accept(dto);
    }
}
'''
    facts = extract_java_facts(source)
    [call] = [call for call in facts.calls if call.target_name == "accept"]

    assert call.receiver_kind == "lambda_parameter"
    assert call.target_owner.qualified_name == "types.Service"
    assert call.target_signature == "(types.Dto)"


def test_local_class_type_is_visible_only_after_its_declaration() -> None:
    source = b'''package demo;
class Outer {
    void run() {
        class Local { void ping() {} }
        Local local = new Local();
        local.ping();
    }
}
'''
    facts = extract_java_facts(source)
    ping = next(
        call
        for call in facts.calls
        if call.source_method == "demo.Outer.run" and call.target_name == "ping"
    )

    assert ping.target_owner.qualified_name == "demo.Outer$Local"


def test_only_exact_framework_annotations_receive_roles() -> None:
    source = b'''package demo;
import org.mapstruct.Mapper;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
@RestController
@Service
@Mapper
class Controller {
    @GetMapping(path = {"/one", "/two"})
    void route() {}
}
@org.apache.ibatis.annotations.Mapper
interface ExactMapper {}
@demo.RestController
class LocalController {}
'''
    facts = extract_java_facts(source)
    by_name = [(annotation.name, annotation.framework_role) for annotation in facts.annotations]

    assert ("RestController", "rest_controller") in by_name
    assert ("Service", "service") in by_name
    assert ("Mapper", "") in by_name
    assert ("GetMapping", "get_mapping") in by_name
    assert ("Mapper", "mapper") in by_name
    assert by_name.count(("RestController", "rest_controller")) == 1
    mapping = next(annotation for annotation in facts.annotations if annotation.framework_role == "get_mapping")
    assert tuple(literal.value for literal in mapping.literals) == ("/one", "/two")


def test_type_uses_exclude_closed_external_categories() -> None:
    source = b'''package demo;
import java.util.List;
import org.springframework.stereotype.Service;
import product.Order;
class Example<T> {
    Order run(Order order, int[] ids, List<String> values, T generic) {
        Order local = new Order();
        return local;
    }
}
'''
    facts = extract_java_facts(source)

    assert [(use.target.qualified_name, use.role) for use in facts.type_uses] == [
        ("product.Order", "return"),
    ]


def test_framework_prefixed_same_package_types_stay_local_graph_targets(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    owner_package = (
        repo
        / "src/main/java/org/springframework/samples/petclinic/owner"
    )
    owner_package.mkdir(parents=True)
    (owner_package / "Owner.java").write_text(
        """package org.springframework.samples.petclinic.owner;
final class Owner {}
""",
        encoding="utf-8",
    )
    (owner_package / "OwnerRepository.java").write_text(
        """package org.springframework.samples.petclinic.owner;
final class OwnerRepository {
    Owner save(Owner owner) { return owner; }
}
""",
        encoding="utf-8",
    )
    (owner_package / "OwnerController.java").write_text(
        """package org.springframework.samples.petclinic.owner;
import org.springframework.web.bind.annotation.RestController;
@RestController
final class OwnerController {
    private final OwnerRepository repository = new OwnerRepository();
    Owner load(Owner owner) { return repository.save(owner); }
}
""",
        encoding="utf-8",
    )

    index_repository(repo, DEFAULT_CONFIG)
    store = SQLiteStore(repo / ".context-search" / "index.sqlite")
    controller_path = Path(
        "src/main/java/org/springframework/samples/petclinic/owner/"
        "OwnerController.java"
    )
    with store.graph_read_session() as session:
        load = next(
            signal
            for signal in session.signal_search(["load"], limit=100)
            if signal.qualified_name
            == "org.springframework.samples.petclinic.owner.OwnerController.load"
        )
        module = session.module_for_path(controller_path)
        assert module is not None
        relations = session.outgoing_relations(load.signal_id)

    local_targets = {
        (relation.kind, relation.target_qualified_name): relation
        for relation in relations
    }
    assert local_targets[
        (
            "calls",
            "org.springframework.samples.petclinic.owner.OwnerRepository.save",
        )
    ].resolution == "resolved_exact"
    for target in (
        "org.springframework.samples.petclinic.owner.Owner",
        "org.springframework.samples.petclinic.owner.OwnerRepository",
    ):
        relation = local_targets[("uses_type", target)]
        assert relation.resolution == "resolved_unique"
        assert relation.target_signal_id

    external_relation_id = generate_v5_relation_id(
        source_signal_id=module.signal_id,
        kind="imports_type",
        target_kind="type",
        target_qualified_name=(
            "org.springframework.web.bind.annotation.RestController"
        ),
        target_signature="",
        target_arity=None,
        target_project_unit_key=module.project_unit_key,
        producer="java_ast",
    )
    external = store.graph_relation_for_id(external_relation_id)
    assert external is not None
    assert external.resolution == "external"
    assert external.target_signal_id == ""


def test_explicit_this_field_reference_emits_one_local_type_use() -> None:
    source = b'''package demo;
import product.Order;
class Example {
    Order order;
    Object current() { return this.order; }
}
'''
    facts = extract_java_facts(source)

    assert [(use.target.qualified_name, use.role) for use in facts.type_uses] == [
        ("product.Order", "referenced_field"),
    ]


def test_import_annotation_literal_call_and_type_use_caps_record_omissions() -> None:
    imports = "\n".join(f"import p{index}.T{index};" for index in range(257))
    annotations = "\n".join(f"@A{index}" for index in range(33))
    literals = ", ".join(f'"v{index}"' for index in range(17))
    calls = "\n".join("ping();" for _ in range(129))
    local_types = "\n".join(
        f"Type{index} value{index} = new Type{index}();" for index in range(9)
    )
    source = f'''package demo;
{imports}
@Values({{{literals}}})
{annotations}
class Example {{
    void ping() {{}}
    void run() {{
        {local_types}
        {calls}
    }}
}}
'''.encode("utf-8")
    facts = extract_java_facts(source)

    assert len(facts.imports) == 256
    assert _omitted(facts, "imports") == 1
    type_annotations = [
        annotation
        for annotation in facts.annotations
        if annotation.owner_qualified_name == "demo.Example"
    ]
    assert len(type_annotations) == 32
    assert _omitted(facts, "annotations") == 2
    values = next(annotation for annotation in type_annotations if annotation.name == "Values")
    assert len(values.literals) == 16
    assert values.omitted_literal_count == 1
    run = next(method for method in facts.methods if method.name == "run")
    assert len([call for call in facts.calls if call.source_method == run.qualified_name]) == 128
    assert _omitted(facts, "calls") > 0
    assert len([use for use in facts.type_uses if use.source_method == run.qualified_name]) == 8
    assert _omitted(facts, "type_uses") == 1


def test_annotation_literal_and_sql_byte_caps_are_utf8_safe() -> None:
    multibyte = "\u00e9" * 200
    sql_annotations = "\n".join(f'@Select("token{index:02d}{"x" * 249}")' for index in range(17))
    source = f'''package demo;
import org.apache.ibatis.annotations.Select;
@Value("{multibyte}")
class Example {{
    {sql_annotations}
    void run() {{}}
}}
'''.encode("utf-8")
    facts = extract_java_facts(source)

    value = next(annotation for annotation in facts.annotations if annotation.name == "Value")
    [literal] = value.literals
    assert len(literal.value.encode("utf-8")) == 256
    assert literal.omitted_utf8_bytes == 144
    assert _omitted(facts, "annotation_sql_bytes") > 0
    assert sum(len(token.encode("utf-8")) for token in facts.annotation_sql_tokens) <= 4_096


def test_ast_facts_preserve_protected_java_parity_inputs_in_source_order() -> None:
    path = (
        JAVA_FIXTURES
        / "java-spring"
        / "src/main/java/com/example/order/OrderController.java"
    )
    source = path.read_bytes()
    facts = extract_java_facts(source)
    legacy = JavaPlugin().extract(path, source.decode("utf-8"))

    assert facts.fallback_required is False
    assert tuple(fact.name for fact in facts.types) == ("OrderController",)
    assert tuple(fact.name for fact in facts.methods) == ("<init>", "create")
    assert tuple(
        (annotation.framework_role, tuple(literal.value for literal in annotation.literals))
        for annotation in facts.annotations
        if annotation.framework_role
    ) == (
        ("rest_controller", ()),
        ("request_mapping", ("/orders",)),
        ("post_mapping", ()),
    )
    assert {"order", "controller", "orders", "create", "dto"} <= set(
        facts.lexical_tokens
    )
    assert {"order", "controller", "orders", "create"} <= set(
        legacy.lexical_tokens
    )
    endpoint = next(signal for signal in legacy.signals if signal.kind == "endpoint")
    assert endpoint.name == "POST /orders"


def test_comment_tokens_are_owned_without_becoming_structure() -> None:
    source = '''package demo;
class Example {
    /** \u5de5\u4f5c\u53f0\u7edf\u8ba1-\u5f85\u6211\u5ba1\u6838 */
    void statsWait() {}
}
'''
    facts = extract_java_facts(source.encode("utf-8"))
    legacy = JavaPlugin().extract(Path("Example.java"), source)

    [comment] = facts.comments
    assert comment.owner_kind == "method"
    assert comment.owner_qualified_name == "demo.Example.statsWait"
    assert "\u5de5\u4f5c\u53f0\u7edf\u8ba1" in comment.text
    assert "\u5f85\u6211\u5ba1\u6838" in comment.tokens
    legacy_comment = next(signal for signal in legacy.signals if signal.kind == "comment")
    assert set(legacy_comment.tokens) <= set(comment.tokens) | {"stats", "wait", "comment"}


def test_malformed_fixture_requires_ast_fallback_but_legacy_output_remains() -> None:
    path = (
        JAVA_FIXTURES
        / "malformed-compat"
        / "src/main/java/com/example/broken/MalformedJava.java"
    )
    source = path.read_bytes()
    facts = extract_java_facts(source)
    legacy = JavaPlugin().extract(path, source.decode("utf-8"))

    assert facts.fallback_required is True
    _assert_no_structural_facts(facts)
    assert "MalformedJava" in {symbol.name for symbol in legacy.symbols}
    assert "MalformedUniqueLexicalToken" in source.decode("utf-8")


def _graph_chunk(path: Path, source: bytes) -> DocumentChunk:
    line_count = source.count(b"\n") + 1
    return DocumentChunk(
        chunk_id="java-chunk",
        file_path=path,
        start_line=1,
        end_line=line_count,
        content=source.decode("utf-8"),
        chunk_type="java",
    )


def _module_signal(path: Path, chunk: DocumentChunk, language: str) -> CodeSignal:
    signal_id = generate_core_module_signal_id(
        file_path=path.as_posix(),
        start_line=chunk.start_line,
        start_column=0,
        end_line=chunk.end_line,
        end_column=0,
    )
    return CodeSignal(
        signal_id=signal_id,
        chunk_id=chunk.chunk_id,
        file_path=path,
        kind="module",
        name=path.as_posix(),
        start_line=chunk.start_line,
        end_line=chunk.end_line,
        language=language,
        qualified_name=path.as_posix(),
        project_unit_key="",
        producer="core_module",
        recallable=False,
    )


def test_java_graph_producer_materializes_v5_declarations_and_edges() -> None:
    path = Path("src/main/java/demo/OrderController.java")
    source = b'''package demo;
import product.Dto;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
interface OrderApi { Dto load(Dto dto); }
class Repository { Dto load(Dto dto) { return dto; } }
@RestController
@RequestMapping("/api")
class OrderController implements OrderApi {
    Repository repository;
    @GetMapping("/orders")
    public Dto load(Dto dto) {
        repository.load(dto);
        repository.load(dto);
        return dto;
    }
}
'''
    context = PluginContext(path, "java", "", {}, (path,))
    chunk = _graph_chunk(path, source)
    module = _module_signal(path, chunk, "java")
    producer = JavaGraphProducer()

    parsed = producer.parse(context, source)
    graph = producer.materialize(context, parsed, (chunk,), module)

    assert parsed.fallback_required is False
    assert parsed.metadata["graph_parse_status"] == "ast"
    assert all(signal.signal_id.startswith("s5:") for signal in graph.signals)
    assert all(signal.producer == "java_ast" for signal in graph.signals)
    by_kind = {kind: [item for item in graph.signals if item.kind == kind] for kind in {
        "type", "field", "method", "endpoint"
    }}
    assert {
        item.qualified_name for item in by_kind["type"] if item.recallable
    } == {"demo.OrderController"}
    assert all(
        not item.recallable
        for item in by_kind["type"]
        if item.qualified_name in {"demo.OrderApi", "demo.Repository"}
    )
    assert all(
        item.recallable
        for kind in ("field", "method", "endpoint")
        for item in by_kind[kind]
    )
    assert {item.qualified_name for item in by_kind["type"]} >= {
        "demo.OrderApi",
        "demo.Repository",
        "demo.OrderController",
    }
    load = next(
        item
        for item in by_kind["method"]
        if item.qualified_name == "demo.OrderController.load"
    )
    assert load.signature == "(product.Dto)"
    [endpoint] = by_kind["endpoint"]
    assert endpoint.name == "GET /api/orders"
    assert endpoint.metadata["method_qualified_name"] == "OrderController.load"

    assert all(relation.relation_id.startswith("r5:") for relation in graph.relations)
    assert {relation.kind for relation in graph.relations} >= {
        "implements",
        "implements_method",
        "calls",
        "uses_type",
        "imports_type",
    }
    implements_method = next(
        item for item in graph.relations if item.kind == "implements_method"
    )
    assert implements_method.target_qualified_name == "demo.OrderApi.load"
    assert implements_method.target_signature == "(product.Dto)"
    call = next(item for item in graph.relations if item.kind == "calls")
    assert call.source_signal_id == endpoint.signal_id
    assert call.target_qualified_name == "demo.Repository.load"
    assert call.target_signature == "(product.Dto)"
    assert call.target_arity == 1
    assert call.metadata["occurrence_count"] == 2
    imports = [item for item in graph.relations if item.kind == "imports_type"]
    assert all(item.source_signal_id == module.signal_id for item in imports)
    assert {item.target_qualified_name for item in imports} >= {"product.Dto"}
    assert all(item.resolution == "unresolved" for item in graph.relations)


def test_java_graph_recall_payload_excludes_package_qualified_identity() -> None:
    path = Path("src/test/java/com/example/order/UnrelatedWorkerTests.java")
    source = b'''package com.example.order;
final class UnrelatedWorkerTests {
    private int isolated;
}
'''
    context = PluginContext(path, "java", "", {}, (path,))
    chunk = _graph_chunk(path, source)
    producer = JavaGraphProducer()
    parsed = producer.parse(context, source)
    graph = producer.materialize(
        context,
        parsed,
        (chunk,),
        _module_signal(path, chunk, "java"),
    )

    type_signal = next(item for item in graph.signals if item.kind == "type")
    field_signal = next(item for item in graph.signals if item.kind == "field")
    query_tokens = ["order", "controller", "tests"]
    scores = [
        candidates._signal_score(
            item.name,
            item.tokens,
            item.metadata,
            query_tokens,
        )
        for item in graph.signals
    ]

    assert type_signal.qualified_name == "com.example.order.UnrelatedWorkerTests"
    assert field_signal.qualified_name == (
        "com.example.order.UnrelatedWorkerTests.isolated"
    )
    assert type_signal.tokens == ["unrelated", "worker", "tests"]
    assert type_signal.recallable is False
    assert field_signal.metadata["owner_type"] == "UnrelatedWorkerTests"
    assert field_signal.recallable is False
    assert all("com.example.order" not in str(item.metadata) for item in graph.signals)
    assert max(scores) == pytest.approx(1 / 3)


def test_java_graph_recall_payload_keeps_simple_type_method_and_field_terms() -> None:
    path = Path("src/main/java/com/example/order/PaymentWorker.java")
    source = b'''package com.example.order;
interface Worker {}
final class PaymentWorker implements Worker {
    private OrderController controller;
    void runPayment() {}
}
'''
    context = PluginContext(path, "java", "", {}, (path,))
    chunk = _graph_chunk(path, source)
    producer = JavaGraphProducer()
    parsed = producer.parse(context, source)
    graph = producer.materialize(
        context,
        parsed,
        (chunk,),
        _module_signal(path, chunk, "java"),
    )
    by_kind = {item.kind: item for item in graph.signals}

    assert candidates._signal_score(
        by_kind["type"].name,
        by_kind["type"].tokens,
        by_kind["type"].metadata,
        ["payment", "worker"],
    ) == 1.0
    assert candidates._signal_score(
        by_kind["method"].name,
        by_kind["method"].tokens,
        by_kind["method"].metadata,
        ["run", "payment"],
    ) == 1.0
    assert candidates._signal_score(
        by_kind["field"].name,
        by_kind["field"].tokens,
        by_kind["field"].metadata,
        ["order", "controller"],
    ) == 1.0
    assert by_kind["type"].qualified_name == "com.example.order.PaymentWorker"
    assert by_kind["type"].recallable is True
    assert by_kind["method"].qualified_name == (
        "com.example.order.PaymentWorker.runPayment"
    )
    assert by_kind["method"].signature == "()"
    assert by_kind["field"].qualified_name == (
        "com.example.order.PaymentWorker.controller"
    )
    assert by_kind["field"].recallable is True


def test_java_graph_fallback_is_marker_only_and_never_calls_legacy() -> None:
    path = Path("src/main/java/demo/Broken.java")
    source = b"package demo; class Broken { void run( { }"
    context = PluginContext(path, "java", "", {}, (path,))
    chunk = _graph_chunk(path, source)
    producer = JavaGraphProducer()

    parsed = producer.parse(context, source)
    graph = producer.materialize(
        context,
        parsed,
        (chunk,),
        _module_signal(path, chunk, "java"),
    )

    assert parsed.fallback_required is True
    assert parsed.symbols == ()
    assert parsed.lexical_tokens == ()
    assert graph.signals == ()
    assert graph.relations == ()
    assert JavaPlugin().extract(path, source.decode()).symbols


def test_default_plugins_instantiate_the_runtime_graph_producers() -> None:
    from context_search_tool.frontend_graph import FrontendGraphProducer
    from context_search_tool.mybatis_xml import MyBatisGraphProducer
    from context_search_tool.plugins import default_plugins

    plugins = default_plugins()

    assert [type(plugin) for plugin in plugins] == [
        JavaPlugin,
        FrontendGraphProducer,
        MyBatisGraphProducer,
    ]


@pytest.mark.parametrize(
    "module_order",
    [
        ("context_search_tool.plugins", "context_search_tool.java_plugin"),
        ("context_search_tool.java_plugin", "context_search_tool.plugins"),
    ],
)
def test_java_coordinator_is_import_order_independent(
    module_order: tuple[str, str],
) -> None:
    import subprocess
    import sys

    script = f"""
import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd() / "src"))
for module_name in {module_order!r}:
    importlib.import_module(module_name)

from context_search_tool.graph_plugins import PluginContext
from context_search_tool.java_plugin import JavaPlugin
from context_search_tool.plugins import default_plugins

plugins = default_plugins()
assert type(plugins[0]) is JavaPlugin
context = PluginContext(Path("App.java"), "java", "")
parsed = plugins[0].parse(context, b"package demo; class App {{}}")
assert parsed.fallback_required is False
"""

    subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )


def test_java_coordinator_keeps_legacy_lexical_output_and_clean_ast_graph() -> None:
    path = Path("src/main/java/demo/AppController.java")
    source = b'''package demo;
import org.springframework.web.bind.annotation.GetMapping;
class AppController {
    @GetMapping("/apps")
    String listApps() { return "ok"; }
}
'''
    context = PluginContext(path, "java", "", {}, (path,))
    chunk = _graph_chunk(path, source)
    module = _module_signal(path, chunk, "java")
    coordinator = JavaPlugin()
    graph_producer = JavaGraphProducer()

    parsed = coordinator.parse(context, source)
    legacy = coordinator.extract(path, source.decode("utf-8"))
    ast_parsed = graph_producer.parse(context, source)

    assert parsed.fallback_required is False
    assert parsed.facts == ast_parsed.facts
    assert parsed.symbols == tuple(legacy.symbols)
    assert parsed.lexical_tokens == tuple(legacy.lexical_tokens)
    assert coordinator.materialize(context, parsed, (chunk,), module) == (
        graph_producer.materialize(context, ast_parsed, (chunk,), module)
    )


@pytest.mark.parametrize(
    ("source", "fallback_required"),
    [
        (b"package demo; class App { void run() {} }", False),
        (b"package demo; class Broken { void run( { }", True),
    ],
)
def test_java_coordinator_calls_legacy_extractor_once_per_file(
    source: bytes,
    fallback_required: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = Path("src/main/java/demo/App.java")
    context = PluginContext(path, "java", "", {}, (path,))
    chunk = _graph_chunk(path, source)
    plugin = JavaPlugin()
    original_extract = plugin.extract
    calls: list[Path] = []

    def recording_extract(file_path: Path, content: str):
        calls.append(file_path)
        return original_extract(file_path, content)

    monkeypatch.setattr(plugin, "extract", recording_extract)

    parsed = plugin.parse(context, source)
    plugin.materialize(
        context,
        parsed,
        (chunk,),
        _module_signal(path, chunk, "java"),
    )

    assert parsed.fallback_required is fallback_required
    assert calls == [path]
