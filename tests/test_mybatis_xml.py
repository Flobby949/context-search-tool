from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

import context_search_tool.mybatis_xml as mybatis_xml
from context_search_tool.mybatis_xml import (
    MyBatisGraphProducer,
    extract_mybatis_facts,
    lex_mybatis_statement_ranges,
)
from context_search_tool.graph_contract import generate_core_module_signal_id
from context_search_tool.graph_plugins import PluginContext
from context_search_tool.models import CodeSignal, DocumentChunk


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "p5-language-graphs"


OFFICIAL_PUBLIC = "-//mybatis.org//DTD Mapper 3.0//EN"


def _doctype(url: str) -> str:
    return f'<!DOCTYPE mapper PUBLIC "{OFFICIAL_PUBLIC}" "{url}">'


def _diagnostic(facts) -> str:
    return facts.diagnostics[0].code if facts.diagnostics else ""


def test_mapper_without_doctype_extracts_closed_statement_facts() -> None:
    source = b'''<mapper namespace="com.example.OrderMapper">
  <select id="find" parameterType="com.example.Order" resultType="java.lang.String">
    select * from orders where id = #{id}
  </select>
  <insert id="insert"/>
  <update id="update">update orders set name = #{name}</update>
  <delete id="delete">delete from orders</delete>
</mapper>'''
    facts = extract_mybatis_facts(source)

    assert facts.accepted is True
    assert facts.namespace == "com.example.OrderMapper"
    assert [(item.tag, item.statement_id, item.qualified_name) for item in facts.statements] == [
        ("select", "find", "com.example.OrderMapper#find"),
        ("insert", "insert", "com.example.OrderMapper#insert"),
        ("update", "update", "com.example.OrderMapper#update"),
        ("delete", "delete", "com.example.OrderMapper#delete"),
    ]
    assert facts.statements[0].parameter_signature == "(com.example.Order)"
    assert {"select", "orders", "id", "string"} <= set(facts.lexical_tokens)
    assert source[facts.statements[1].source_range.start_byte : facts.statements[1].source_range.end_byte] == b'<insert id="insert"/>'


@pytest.mark.parametrize(
    "url",
    [
        "https://mybatis.org/dtd/mybatis-3-mapper.dtd",
        "http://mybatis.org/dtd/mybatis-3-mapper.dtd",
    ],
)
def test_only_official_http_and_https_doctypes_are_accepted(url: str) -> None:
    source = (
        _doctype(url)
        + '\n<mapper namespace="demo.Mapper"><select id="find">select 1</select></mapper>'
    ).encode("utf-8")

    facts = extract_mybatis_facts(source)

    assert facts.accepted is True
    assert [item.statement_id for item in facts.statements] == ["find"]


def test_predefined_and_numeric_entity_references_are_accepted() -> None:
    source = b'''<mapper namespace="demo.Mapper">
  <select id="find">&lt; &gt; &amp; &apos; &quot; &#65; &#x41;</select>
</mapper>'''

    assert extract_mybatis_facts(source).accepted is True


@pytest.mark.parametrize(
    ("source", "code"),
    [
        (
            (_doctype("https://mybatis.org/dtd/mybatis-3-mapper.dtd") + _doctype("https://mybatis.org/dtd/mybatis-3-mapper.dtd") + '<mapper namespace="x"/>').encode(),
            "doctype_count",
        ),
        (
            b'<!DOCTYPE wrong PUBLIC "-//mybatis.org//DTD Mapper 3.0//EN" "https://mybatis.org/dtd/mybatis-3-mapper.dtd"><mapper namespace="x"/>',
            "doctype_invalid",
        ),
        (
            b'<!DOCTYPE mapper SYSTEM "https://mybatis.org/dtd/mybatis-3-mapper.dtd"><mapper namespace="x"/>',
            "doctype_invalid",
        ),
        (
            b'<!DOCTYPE mapper [<!ELEMENT mapper ANY>]><mapper namespace="x"/>',
            "doctype_internal_subset",
        ),
        (
            b'<!DOCTYPE mapper [<!ENTITY secret SYSTEM "file:///etc/passwd">]><mapper namespace="x"/>',
            "entity_declaration",
        ),
        (
            b'<!DOCTYPE mapper [<!ENTITY % remote SYSTEM "https://example.invalid/x"> %remote;]><mapper namespace="x"/>',
            "entity_declaration",
        ),
        (
            b'<mapper namespace="x"><select id="find">&secret;</select></mapper>',
            "entity_reference",
        ),
        (
            b'<root namespace="x"><select id="find"/></root>',
            "wrong_root",
        ),
        (
            b'<mapper namespace="x"><select id="find"></mapper>',
            "xml_parse_error",
        ),
        (
            b'<mapper namespace="x"><select id="same"/><insert id="same"/></mapper>',
            "duplicate_statement_id",
        ),
        (
            b'<mapper namespace="x"><select>select 1</select></mapper>',
            "missing_statement_id",
        ),
    ],
)
def test_closed_xml_protocol_rejects_unsafe_or_inconsistent_inputs(
    source: bytes,
    code: str,
) -> None:
    facts = extract_mybatis_facts(source)

    assert facts.accepted is False
    assert facts.namespace == ""
    assert facts.statements == ()
    assert _diagnostic(facts) == code


@pytest.mark.parametrize("prefix", ["xi", "include", "x"])
def test_xinclude_is_rejected_by_namespace_uri_regardless_of_prefix(
    prefix: str,
) -> None:
    source = f'''<mapper xmlns:{prefix}="http://www.w3.org/2001/XInclude" namespace="demo.Mapper">
  <{prefix}:include href="outside.xml"/>
</mapper>'''.encode("utf-8")
    facts = extract_mybatis_facts(source)

    assert facts.accepted is False
    assert _diagnostic(facts) == "xinclude"


def test_byte_lexer_ignores_fake_tags_and_preserves_exact_late_ranges() -> None:
    source = '''<?xml version="1.0"?>
<mapper namespace="demo.Mapper">
  <!-- <select id="commented">fake</select> -->
  <![CDATA[<insert id="cdata">fake</insert>]]>
  <?ignored value="<delete id='pi'/>"?>
  <select data-note="a > b" id="early">
    select '\u732b'
    <if test="ok">where id = #{id}</if>
  </select>

  <update id="late" data-note='x > y'/>
</mapper>'''.encode("utf-8")

    lexed = lex_mybatis_statement_ranges(source)
    facts = extract_mybatis_facts(source)

    assert [(item.tag, item.statement_id) for item in lexed] == [
        ("select", "early"),
        ("update", "late"),
    ]
    assert facts.accepted is True
    assert [item.source_range for item in facts.statements] == [
        item.source_range for item in lexed
    ]
    late = facts.statements[-1]
    assert late.source_range.start_line == 11
    assert source[late.source_range.start_byte : late.source_range.end_byte] == b"<update id=\"late\" data-note='x > y'/>"
    assert late.source_range.start_column == 2


@pytest.mark.parametrize(
    "source",
    [
        b'<mapper namespace="x"><select id="find"></mapper>',
        b'<mapper namespace="x"><select id="find">',
        b'<mapper namespace="x"><select id="find"></insert></mapper>',
    ],
)
def test_independent_locator_rejects_unbalanced_state(source: bytes) -> None:
    with pytest.raises(ValueError):
        lex_mybatis_statement_ranges(source)


def test_parsed_and_lexed_sequences_must_match_one_for_one(monkeypatch) -> None:
    source = b'<mapper namespace="demo.Mapper"><select id="find">select 1</select></mapper>'
    original = mybatis_xml._lex_statement_ranges

    def mismatched(*args, **kwargs):
        [item] = original(*args, **kwargs)
        return (replace(item, statement_id="other"),)

    monkeypatch.setattr(mybatis_xml, "_lex_statement_ranges", mismatched)
    facts = extract_mybatis_facts(source)

    assert facts.accepted is False
    assert _diagnostic(facts) == "statement_sequence_mismatch"


def test_sql_text_is_bounded_and_parameter_aliases_are_canonical() -> None:
    sql = "token " * 2_000
    source = f'''<mapper namespace="demo.Mapper">
  <select id="find" parameterType="string" resultType="map">{sql}</select>
</mapper>'''.encode("utf-8")
    facts = extract_mybatis_facts(source)

    assert facts.accepted is True
    [statement] = facts.statements
    assert statement.parameter_signature == "(java.lang.String)"
    assert statement.sql_utf8_bytes <= 4_096
    assert any(item.code == "sql_bytes_omitted" for item in facts.diagnostics)


def test_frozen_order_mapper_is_accepted_and_security_negatives_fail_closed() -> None:
    order_mapper = (
        FIXTURES
        / "java-spring"
        / "src/main/resources/mappers/OrderMapper.xml"
    )
    accepted = extract_mybatis_facts(order_mapper.read_bytes())
    assert accepted.accepted is True
    assert [(item.tag, item.statement_id, item.parameter_signature) for item in accepted.statements] == [
        ("insert", "insert", "(com.example.order.Order)")
    ]

    malformed = FIXTURES / "malformed-compat" / "src/main/resources/mappers"
    expected = {
        "FakeTagMapper.xml": True,
        "InternalSubsetMapper.xml": False,
        "MalformedMapper.xml": False,
        "XIncludeMapper.xml": False,
        "XxeMapper.xml": False,
    }
    assert {
        name: extract_mybatis_facts((malformed / name).read_bytes()).accepted
        for name in expected
    } == expected


def _xml_module(path: Path, chunk: DocumentChunk) -> CodeSignal:
    return CodeSignal(
        signal_id=generate_core_module_signal_id(
            file_path=path.as_posix(),
            start_line=chunk.start_line,
            start_column=0,
            end_line=chunk.end_line,
            end_column=0,
        ),
        chunk_id=chunk.chunk_id,
        file_path=path,
        kind="module",
        name=path.as_posix(),
        start_line=chunk.start_line,
        end_line=chunk.end_line,
        language="xml",
        qualified_name=path.as_posix(),
        project_unit_key="",
        producer="core_module",
        recallable=False,
    )


def test_mybatis_graph_attaches_each_statement_to_its_containing_chunk() -> None:
    path = Path("src/main/resources/mappers/OrderMapper.xml")
    source = b'''<mapper namespace="demo.OrderMapper">
  <select id="early">select 1</select>




  <insert id="late" parameterType="string">
    insert into orders values (#{value})
  </insert>
</mapper>'''
    first = DocumentChunk("xml-first", path, 1, 4, source.decode(), "xml")
    second = DocumentChunk("xml-second", path, 5, 10, source.decode(), "xml")
    context = PluginContext(path, "xml", "", {}, (path,))
    producer = MyBatisGraphProducer()
    parsed = producer.parse(context, source)

    graph = producer.materialize(
        context,
        parsed,
        (first, second),
        _xml_module(path, first),
    )

    assert [(signal.name, signal.chunk_id) for signal in graph.signals] == [
        ("demo.OrderMapper#early", "xml-first"),
        ("demo.OrderMapper#late", "xml-second"),
    ]
    assert all(signal.kind == "mybatis_statement" for signal in graph.signals)
    assert all(signal.recallable is False for signal in graph.signals)
    by_target = {relation.target_name: relation for relation in graph.relations}
    exact = by_target["demo.OrderMapper#late"]
    assert exact.kind == "mapped_by"
    assert exact.target_qualified_name == "demo.OrderMapper.late"
    assert exact.target_signature == "(java.lang.String)"
    assert exact.target_arity == 1
    assert exact.resolution == "unresolved"
    unique = by_target["demo.OrderMapper#early"]
    assert unique.target_signature == ""
    assert unique.target_arity is None


def test_mybatis_graph_missing_statement_chunk_fails_closed() -> None:
    path = Path("src/main/resources/mappers/OrderMapper.xml")
    source = b'''<mapper namespace="demo.OrderMapper">
  <select id="early">select 1</select>


  <insert id="late">insert 1</insert>
</mapper>'''
    first = DocumentChunk("xml-first", path, 1, 3, source.decode(), "xml")
    context = PluginContext(path, "xml", "", {}, (path,))
    producer = MyBatisGraphProducer()
    parsed = producer.parse(context, source)

    graph = producer.materialize(
        context,
        parsed,
        (first,),
        _xml_module(path, first),
    )

    assert graph.signals == ()
    assert graph.relations == ()
    assert graph.metadata["graph_materialize_status"] == "missing_chunk"
