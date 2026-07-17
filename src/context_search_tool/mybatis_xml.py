from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
import re
from typing import Any

from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException

from context_search_tool.graph_contract import (
    MAX_SIGNALS_PER_FILE,
    generate_v5_relation_id,
    generate_v5_signal_id,
)
from context_search_tool.graph_plugins import (
    MaterializedGraph,
    ParsedGraphFacts,
    PluginContext,
)
from context_search_tool.models import CodeRelation, CodeSignal, DocumentChunk


_STATEMENT_TAGS = frozenset({"select", "insert", "update", "delete"})
_XINCLUDE_NAMESPACE = "http://www.w3.org/2001/XInclude"
_PUBLIC_ID = "-//mybatis.org//DTD Mapper 3.0//EN"
_SYSTEM_IDS = frozenset(
    {
        "http://mybatis.org/dtd/mybatis-3-mapper.dtd",
        "https://mybatis.org/dtd/mybatis-3-mapper.dtd",
    }
)
_PREDEFINED_ENTITIES = frozenset({"amp", "apos", "gt", "lt", "quot"})
_SQL_UTF8_BYTE_LIMIT = 4_096
_TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_DOCTYPE_RE = re.compile(
    r"\A\s*<!DOCTYPE\s+mapper\s+PUBLIC\s+"
    r"(?P<public_quote>['\"])(?P<public>[^'\"]+)(?P=public_quote)\s+"
    r"(?P<system_quote>['\"])(?P<system>[^'\"]+)(?P=system_quote)\s*>\s*\Z",
    re.DOTALL | re.IGNORECASE,
)
_ENTITY_REFERENCE_RE = re.compile(
    rb"&(?P<name>[A-Za-z_:][A-Za-z0-9_.:-]*);"
)
_ATTRIBUTE_ID_RE = re.compile(
    rb"(?:^|\s)id\s*=\s*(?:\"(?P<double>[^\"]*)\"|'(?P<single>[^']*)')",
    re.DOTALL,
)

_TYPE_ALIASES = {
    "_boolean": "boolean",
    "_byte": "byte",
    "_char": "char",
    "_character": "char",
    "_double": "double",
    "_float": "float",
    "_int": "int",
    "_integer": "int",
    "_long": "long",
    "_short": "short",
    "arraylist": "java.util.ArrayList",
    "bigdecimal": "java.math.BigDecimal",
    "biginteger": "java.math.BigInteger",
    "boolean": "java.lang.Boolean",
    "byte": "java.lang.Byte",
    "char": "java.lang.Character",
    "character": "java.lang.Character",
    "collection": "java.util.Collection",
    "date": "java.util.Date",
    "decimal": "java.math.BigDecimal",
    "double": "java.lang.Double",
    "float": "java.lang.Float",
    "hashmap": "java.util.HashMap",
    "int": "java.lang.Integer",
    "integer": "java.lang.Integer",
    "iterator": "java.util.Iterator",
    "list": "java.util.List",
    "long": "java.lang.Long",
    "map": "java.util.Map",
    "object": "java.lang.Object",
    "short": "java.lang.Short",
    "string": "java.lang.String",
}
_GRAPH_PRODUCER = "mybatis_xml"
_JAVA_FQCN_RE = re.compile(
    r"(?:[A-Za-z_$][A-Za-z0-9_$]*\.)+[A-Za-z_$][A-Za-z0-9_$]*(?:\[\])*$"
)


@dataclass(frozen=True)
class SourceRange:
    start_byte: int
    end_byte: int
    start_line: int
    start_column: int
    end_line: int
    end_column: int


@dataclass(frozen=True)
class FactDiagnostic:
    code: str
    count: int = 1


@dataclass(frozen=True)
class MyBatisLexedStatement:
    tag: str
    statement_id: str
    source_range: SourceRange


@dataclass(frozen=True)
class MyBatisStatementFact:
    tag: str
    statement_id: str
    qualified_name: str
    parameter_signature: str
    sql_utf8_bytes: int
    source_range: SourceRange


@dataclass(frozen=True)
class MyBatisFactSet:
    accepted: bool
    namespace: str
    statements: tuple[MyBatisStatementFact, ...]
    lexical_tokens: tuple[str, ...]
    diagnostics: tuple[FactDiagnostic, ...]


@dataclass(frozen=True)
class _OpenTag:
    name: str
    start_byte: int
    direct_statement_tag: str
    statement_id: str


class MyBatisGraphProducer:
    def supports(self, context: PluginContext) -> bool:
        return context.file_path.suffix.lower() == ".xml"

    def parse(self, context: PluginContext, content: bytes) -> ParsedGraphFacts:
        if not self.supports(context):
            raise ValueError("MyBatisGraphProducer received an unsupported source")
        facts = extract_mybatis_facts(content)
        return ParsedGraphFacts(
            facts=facts,
            lexical_tokens=facts.lexical_tokens,
            metadata={
                "graph_parse_status": "accepted" if facts.accepted else "rejected",
                "graph_diagnostics": {
                    item.code: item.count for item in facts.diagnostics
                },
            },
        )

    def materialize(
        self,
        context: PluginContext,
        parsed: ParsedGraphFacts,
        chunks: tuple[DocumentChunk, ...],
        module_signal: CodeSignal,
    ) -> MaterializedGraph:
        facts = parsed.facts
        if not isinstance(facts, MyBatisFactSet) or not facts.accepted:
            return MaterializedGraph(metadata=parsed.metadata)
        if module_signal.file_path != context.file_path:
            raise ValueError("module signal does not belong to the plugin context")

        ordered_chunks = tuple(
            sorted(
                chunks,
                key=lambda item: (
                    item.start_line,
                    item.end_line,
                    item.chunk_id,
                ),
            )
        )
        attachments = [
            _mybatis_containing_chunk(ordered_chunks, fact.source_range.start_line)
            for fact in facts.statements
        ]
        if any(chunk is None for chunk in attachments):
            metadata = dict(parsed.metadata)
            metadata["graph_materialize_status"] = "missing_chunk"
            return MaterializedGraph(metadata=metadata)

        signals: list[CodeSignal] = []
        relations: list[CodeRelation] = []
        for fact, chunk in zip(facts.statements, attachments):
            assert chunk is not None
            signal = _mybatis_statement_signal(context, fact, chunk)
            signals.append(signal)
            relations.append(_mybatis_relation(context, signal, fact))
        return MaterializedGraph(
            signals=tuple(signals),
            relations=tuple(relations),
            metadata=parsed.metadata,
        )


MyBatisXmlGraphProducer = MyBatisGraphProducer


def extract_mybatis_facts(source: bytes) -> MyBatisFactSet:
    if not isinstance(source, bytes):
        raise TypeError("source must be bytes")

    try:
        doctypes, entity_declaration = _locate_doctypes(source)
    except ValueError:
        return _rejected("doctype_invalid")

    if entity_declaration:
        return _rejected("entity_declaration")
    if len(doctypes) > 1:
        return _rejected("doctype_count")

    doctype_range = doctypes[0] if doctypes else None
    if doctype_range is not None:
        declaration = source[doctype_range[0] : doctype_range[1]]
        if b"[" in declaration or b"]" in declaration:
            return _rejected("doctype_internal_subset")
        if not _official_doctype(declaration):
            return _rejected("doctype_invalid")

    if _has_unknown_entity_reference(source, doctypes):
        return _rejected("entity_reference")

    scrubbed = _scrub_doctype(source, doctype_range)
    try:
        root = ElementTree.fromstring(scrubbed)
    except (ElementTree.ParseError, DefusedXmlException):
        return _rejected("xml_parse_error")

    if root.tag != "mapper":
        return _rejected("wrong_root")
    namespace = (root.attrib.get("namespace") or "").strip()
    if not namespace:
        return _rejected("missing_namespace")
    if any(_namespace_uri(element.tag) == _XINCLUDE_NAMESPACE for element in root.iter()):
        return _rejected("xinclude")

    parsed: list[tuple[str, str, Any]] = []
    seen_ids: set[str] = set()
    for element in list(root):
        tag = _local_name(element.tag)
        if tag not in _STATEMENT_TAGS:
            continue
        statement_id = (element.attrib.get("id") or "").strip()
        if not statement_id:
            return _rejected("missing_statement_id")
        if statement_id in seen_ids:
            return _rejected("duplicate_statement_id")
        seen_ids.add(statement_id)
        parsed.append((tag, statement_id, element))

    try:
        lexed = _lex_statement_ranges(source, doctype_range)
    except ValueError:
        return _rejected("statement_lexer_error")
    if [(tag, statement_id) for tag, statement_id, _ in parsed] != [
        (item.tag, item.statement_id) for item in lexed
    ]:
        return _rejected("statement_sequence_mismatch")

    diagnostics: list[FactDiagnostic] = []
    statements: list[MyBatisStatementFact] = []
    tokens: list[str] = []
    token_seen: set[str] = set()
    for (tag, statement_id, element), located in zip(parsed, lexed):
        sql = "".join(element.itertext())
        encoded_sql = sql.encode("utf-8")
        bounded_sql = encoded_sql[:_SQL_UTF8_BYTE_LIMIT]
        if len(encoded_sql) > len(bounded_sql):
            _add_diagnostic(diagnostics, "sql_bytes_omitted", 1)
        parameter_type = (element.attrib.get("parameterType") or "").strip()
        result_type = (element.attrib.get("resultType") or "").strip()
        statements.append(
            MyBatisStatementFact(
                tag=tag,
                statement_id=statement_id,
                qualified_name=f"{namespace}#{statement_id}",
                parameter_signature=_parameter_signature(parameter_type),
                sql_utf8_bytes=len(bounded_sql),
                source_range=located.source_range,
            )
        )
        lexical_input = " ".join(
            (
                tag,
                statement_id,
                namespace,
                parameter_type,
                result_type,
                bounded_sql.decode("utf-8", errors="ignore"),
            )
        )
        for match in _TOKEN_RE.finditer(lexical_input):
            token = match.group(0).lower()
            if token not in token_seen:
                token_seen.add(token)
                tokens.append(token)

    if len(statements) > MAX_SIGNALS_PER_FILE:
        omitted = len(statements) - MAX_SIGNALS_PER_FILE
        statements = statements[:MAX_SIGNALS_PER_FILE]
        _add_diagnostic(diagnostics, "statements_omitted", omitted)

    return MyBatisFactSet(
        accepted=True,
        namespace=namespace,
        statements=tuple(statements),
        lexical_tokens=tuple(tokens),
        diagnostics=tuple(diagnostics),
    )


def lex_mybatis_statement_ranges(
    source: bytes,
) -> tuple[MyBatisLexedStatement, ...]:
    if not isinstance(source, bytes):
        raise TypeError("source must be bytes")
    doctypes, entity_declaration = _locate_doctypes(source)
    if entity_declaration or len(doctypes) > 1:
        raise ValueError("unsafe XML declaration")
    return _lex_statement_ranges(source, doctypes[0] if doctypes else None)


def _lex_statement_ranges(
    source: bytes,
    doctype_range: tuple[int, int] | None,
) -> tuple[MyBatisLexedStatement, ...]:
    line_starts = _line_starts(source)
    stack: list[_OpenTag] = []
    statements: list[MyBatisLexedStatement] = []
    position = 0
    length = len(source)

    while position < length:
        start = source.find(b"<", position)
        if start < 0:
            break
        if doctype_range is not None and start == doctype_range[0]:
            position = doctype_range[1]
            continue
        if source.startswith(b"<!--", start):
            position = _closed_special(source, start, b"-->")
            continue
        if source.startswith(b"<![CDATA[", start):
            position = _closed_special(source, start, b"]]>")
            continue
        if source.startswith(b"<?", start):
            position = _closed_special(source, start, b"?>")
            continue
        if source.startswith(b"<!", start):
            end = _tag_end(source, start)
            position = end
            continue

        end = _tag_end(source, start)
        body = source[start + 1 : end - 1]
        closing = body.startswith(b"/")
        if closing:
            match = re.match(rb"/\s*([^\s>]+)\s*\Z", body, re.DOTALL)
            if match is None or not stack:
                raise ValueError("unbalanced closing tag")
            name = match.group(1).decode("utf-8", errors="strict")
            opened = stack.pop()
            if name != opened.name:
                raise ValueError("mismatched closing tag")
            if opened.direct_statement_tag:
                statements.append(
                    MyBatisLexedStatement(
                        tag=opened.direct_statement_tag,
                        statement_id=opened.statement_id,
                        source_range=_source_range(
                            line_starts,
                            opened.start_byte,
                            end,
                        ),
                    )
                )
            position = end
            continue

        self_closing = body.rstrip().endswith(b"/")
        content = body.rstrip()[:-1] if self_closing else body
        match = re.match(rb"\s*([^\s/>]+)(?P<attributes>.*)\Z", content, re.DOTALL)
        if match is None:
            raise ValueError("invalid opening tag")
        name = match.group(1).decode("utf-8", errors="strict")
        local_name = name.rsplit(":", 1)[-1]
        parent_is_mapper = len(stack) == 1 and stack[0].name.rsplit(":", 1)[-1] == "mapper"
        direct_tag = local_name if parent_is_mapper and local_name in _STATEMENT_TAGS else ""
        statement_id = _literal_id(match.group("attributes")) if direct_tag else ""
        opened = _OpenTag(
            name=name,
            start_byte=start,
            direct_statement_tag=direct_tag,
            statement_id=statement_id,
        )
        if self_closing:
            if direct_tag:
                statements.append(
                    MyBatisLexedStatement(
                        tag=direct_tag,
                        statement_id=statement_id,
                        source_range=_source_range(line_starts, start, end),
                    )
                )
        else:
            stack.append(opened)
        position = end

    if stack:
        raise ValueError("unclosed tag")
    return tuple(statements)


def _locate_doctypes(
    source: bytes,
) -> tuple[tuple[tuple[int, int], ...], bool]:
    doctypes: list[tuple[int, int]] = []
    entity_declaration = False
    position = 0
    while position < len(source):
        start = source.find(b"<", position)
        if start < 0:
            break
        if source.startswith(b"<!--", start):
            position = _closed_special(source, start, b"-->")
            continue
        if source.startswith(b"<![CDATA[", start):
            position = _closed_special(source, start, b"]]>")
            continue
        if source.startswith(b"<?", start):
            position = _closed_special(source, start, b"?>")
            continue
        prefix = source[start : start + 10].upper()
        if prefix.startswith(b"<!DOCTYPE"):
            end = _doctype_end(source, start)
            declaration = source[start:end]
            if re.search(rb"<!ENTITY\b", declaration, re.IGNORECASE):
                entity_declaration = True
            doctypes.append((start, end))
            position = end
            continue
        if source[start : start + 9].upper().startswith(b"<!ENTITY"):
            entity_declaration = True
        position = start + 1
    return tuple(doctypes), entity_declaration


def _doctype_end(source: bytes, start: int) -> int:
    quote = 0
    subset_depth = 0
    position = start + 2
    while position < len(source):
        value = source[position]
        if quote:
            if value == quote:
                quote = 0
        elif value in (ord("'"), ord('"')):
            quote = value
        elif value == ord("["):
            subset_depth += 1
        elif value == ord("]"):
            subset_depth = max(0, subset_depth - 1)
        elif value == ord(">") and subset_depth == 0:
            return position + 1
        position += 1
    raise ValueError("unclosed doctype")


def _official_doctype(declaration: bytes) -> bool:
    try:
        text = declaration.decode("ascii")
    except UnicodeDecodeError:
        return False
    match = _DOCTYPE_RE.fullmatch(text)
    return bool(
        match
        and match.group("public") == _PUBLIC_ID
        and match.group("system") in _SYSTEM_IDS
    )


def _has_unknown_entity_reference(
    source: bytes,
    doctypes: tuple[tuple[int, int], ...],
) -> bool:
    visible = bytearray(source)
    for start, end in _ignored_entity_ranges(source, doctypes):
        visible[start:end] = b" " * (end - start)
    for match in _ENTITY_REFERENCE_RE.finditer(visible):
        if match.group("name").decode("ascii") not in _PREDEFINED_ENTITIES:
            return True
    return False


def _ignored_entity_ranges(
    source: bytes,
    doctypes: tuple[tuple[int, int], ...],
) -> tuple[tuple[int, int], ...]:
    ranges = list(doctypes)
    position = 0
    for opening, closing in ((b"<!--", b"-->"), (b"<![CDATA[", b"]]>"), (b"<?", b"?>")):
        position = 0
        while True:
            start = source.find(opening, position)
            if start < 0:
                break
            end_marker = source.find(closing, start + len(opening))
            if end_marker < 0:
                break
            end = end_marker + len(closing)
            ranges.append((start, end))
            position = end
    return tuple(ranges)


def _scrub_doctype(
    source: bytes,
    doctype_range: tuple[int, int] | None,
) -> bytes:
    if doctype_range is None:
        return source
    scrubbed = bytearray(source)
    for position in range(*doctype_range):
        if scrubbed[position] not in (ord("\r"), ord("\n")):
            scrubbed[position] = ord(" ")
    return bytes(scrubbed)


def _closed_special(source: bytes, start: int, closing: bytes) -> int:
    end = source.find(closing, start)
    if end < 0:
        raise ValueError("unclosed XML special section")
    return end + len(closing)


def _tag_end(source: bytes, start: int) -> int:
    quote = 0
    for position in range(start + 1, len(source)):
        value = source[position]
        if quote:
            if value == quote:
                quote = 0
        elif value in (ord("'"), ord('"')):
            quote = value
        elif value == ord(">"):
            return position + 1
    raise ValueError("unclosed XML tag")


def _literal_id(attributes: bytes) -> str:
    match = _ATTRIBUTE_ID_RE.search(attributes)
    if match is None:
        return ""
    value = match.group("double")
    if value is None:
        value = match.group("single")
    assert value is not None
    return _decode_xml_references(value.decode("utf-8", errors="strict"))


def _decode_xml_references(value: str) -> str:
    replacements = {
        "&amp;": "&",
        "&apos;": "'",
        "&gt;": ">",
        "&lt;": "<",
        "&quot;": '"',
    }
    for source, target in replacements.items():
        value = value.replace(source, target)

    def numeric(match: re.Match[str]) -> str:
        raw = match.group(1)
        base = 16 if raw.lower().startswith("x") else 10
        digits = raw[1:] if base == 16 else raw
        try:
            return chr(int(digits, base))
        except (ValueError, OverflowError):
            return match.group(0)

    return re.sub(r"&#(x[0-9A-Fa-f]+|[0-9]+);", numeric, value)


def _parameter_signature(parameter_type: str) -> str:
    if not parameter_type:
        return ""
    canonical = _TYPE_ALIASES.get(parameter_type.lower())
    if canonical is None:
        if _JAVA_FQCN_RE.fullmatch(parameter_type) is None:
            return ""
        canonical = parameter_type
    return f"({canonical})"


def _namespace_uri(tag: object) -> str:
    if not isinstance(tag, str) or not tag.startswith("{"):
        return ""
    end = tag.find("}")
    return tag[1:end] if end >= 0 else ""


def _local_name(tag: object) -> str:
    if not isinstance(tag, str):
        return ""
    return tag.rsplit("}", 1)[-1]


def _line_starts(source: bytes) -> tuple[int, ...]:
    return (0,) + tuple(
        position + 1 for position, value in enumerate(source) if value == ord("\n")
    )


def _source_range(
    line_starts: tuple[int, ...],
    start_byte: int,
    end_byte: int,
) -> SourceRange:
    start_index = bisect_right(line_starts, start_byte) - 1
    end_index = bisect_right(line_starts, end_byte) - 1
    return SourceRange(
        start_byte=start_byte,
        end_byte=end_byte,
        start_line=start_index + 1,
        start_column=start_byte - line_starts[start_index],
        end_line=end_index + 1,
        end_column=end_byte - line_starts[end_index],
    )


def _add_diagnostic(
    diagnostics: list[FactDiagnostic],
    code: str,
    count: int,
) -> None:
    for index, item in enumerate(diagnostics):
        if item.code == code:
            diagnostics[index] = FactDiagnostic(code, item.count + count)
            return
    diagnostics.append(FactDiagnostic(code, count))


def _rejected(code: str) -> MyBatisFactSet:
    return MyBatisFactSet(
        accepted=False,
        namespace="",
        statements=(),
        lexical_tokens=(),
        diagnostics=(FactDiagnostic(code),),
    )


def _mybatis_statement_signal(
    context: PluginContext,
    fact: MyBatisStatementFact,
    chunk: DocumentChunk,
) -> CodeSignal:
    source_range = fact.source_range
    arity = 1 if fact.parameter_signature else None
    signal_id = generate_v5_signal_id(
        file_path=context.file_path.as_posix(),
        kind="mybatis_statement",
        qualified_name=fact.qualified_name,
        signature=fact.parameter_signature,
        start_line=source_range.start_line,
        start_column=source_range.start_column,
        end_line=source_range.end_line,
        end_column=source_range.end_column,
        producer=_GRAPH_PRODUCER,
    )
    return CodeSignal(
        signal_id=signal_id,
        chunk_id=chunk.chunk_id,
        file_path=context.file_path,
        kind="mybatis_statement",
        name=fact.qualified_name,
        start_line=source_range.start_line,
        end_line=source_range.end_line,
        language="xml",
        tokens=[],
        metadata={
            "statement_tag": fact.tag,
            "statement_id": fact.statement_id,
            "namespace": fact.qualified_name.rsplit("#", 1)[0],
            "sql_utf8_bytes": fact.sql_utf8_bytes,
        },
        qualified_name=fact.qualified_name,
        signature=fact.parameter_signature,
        arity=arity,
        project_unit_key=context.project_unit_key,
        producer=_GRAPH_PRODUCER,
        start_column=source_range.start_column,
        end_column=source_range.end_column,
        recallable=False,
    )


def _mybatis_relation(
    context: PluginContext,
    source: CodeSignal,
    fact: MyBatisStatementFact,
) -> CodeRelation:
    namespace = fact.qualified_name.rsplit("#", 1)[0]
    target_qualified_name = f"{namespace}.{fact.statement_id}"
    target_arity = 1 if fact.parameter_signature else None
    relation_id = generate_v5_relation_id(
        source_signal_id=source.signal_id,
        kind="mapped_by",
        target_kind="method",
        target_qualified_name=target_qualified_name,
        target_signature=fact.parameter_signature,
        target_arity=target_arity,
        target_project_unit_key=context.project_unit_key,
        producer=_GRAPH_PRODUCER,
    )
    return CodeRelation(
        relation_id=relation_id,
        source_signal_id=source.signal_id,
        target_name=fact.qualified_name,
        kind="mapped_by",
        confidence=1.0,
        metadata={
            "selector": fact.qualified_name,
            "resolution_basis": (
                "mybatis_exact_signature"
                if fact.parameter_signature
                else "mybatis_namespace_id"
            ),
            "target_language": "java",
            "first_source_line": fact.source_range.start_line,
            "first_source_column": fact.source_range.start_column,
            "occurrence_count": 1,
        },
        target_kind="method",
        target_qualified_name=target_qualified_name,
        target_signature=fact.parameter_signature,
        target_arity=target_arity,
        target_project_unit_key=context.project_unit_key,
        resolution="unresolved",
        producer=_GRAPH_PRODUCER,
        producer_confidence=1.0,
    )


def _mybatis_containing_chunk(
    chunks: tuple[DocumentChunk, ...], line: int
) -> DocumentChunk | None:
    return next(
        (chunk for chunk in chunks if chunk.start_line <= line <= chunk.end_line),
        None,
    )
