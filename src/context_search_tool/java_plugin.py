from __future__ import annotations

import re
from dataclasses import replace
from pathlib import Path
from typing import Any

from context_search_tool.graph_plugins import (
    MaterializedGraph,
    ParsedGraphFacts,
    PluginContext,
)
from context_search_tool.models import (
    CodeRelation,
    CodeSignal,
    SymbolRef,
    generate_relation_id,
    generate_signal_id,
)
from context_search_tool.plugins import PluginExtraction
from context_search_tool.tokenizer import tokenize_identifier


_PACKAGE_RE = re.compile(r"package\s+([\w.]+)\s*;")
_IMPORT_RE = re.compile(r"import\s+([\w.*]+)\s*;")
_TYPE_RE = re.compile(r"\b(class|interface|enum)\s+(\w+)")
_IMPLEMENTS_RE = re.compile(r"\bimplements\s+([^{]+)")
_ANNOTATION_START_RE = re.compile(r"@(\w+)")
_METHOD_RE = re.compile(
    r"^\s*(?:(?:public|protected|private|static|final|abstract|synchronized|native)\s+)*"
    r"[\w<>\[\], ?]+\s+(\w+)\s*\([^;{}]*\)\s*(?:throws\s+[^{;]+)?[;{]"
)
_FIELD_RE = re.compile(
    r"^\s*(?:(?:public|protected|private|static|final|transient|volatile)\s+)*"
    r"([A-Z][\w.]*\s*(?:<[^;=()]+>)?(?:\[\])?)\s+([A-Za-z_]\w*)\s*(?:[=;])"
)
_ASSIGNMENT_RE = re.compile(r"\bthis\s*\.\s*([A-Za-z_]\w*)\s*=\s*([A-Za-z_]\w*)\s*;")
_SQL_ANNOTATIONS = {"Select", "Insert", "Update", "Delete"}
_MAPPING_ANNOTATIONS = {
    "RequestMapping",
    "GetMapping",
    "PostMapping",
    "PutMapping",
    "DeleteMapping",
    "PatchMapping",
}
_HTTP_BY_MAPPING = {
    "GetMapping": "GET",
    "PostMapping": "POST",
    "PutMapping": "PUT",
    "DeleteMapping": "DELETE",
    "PatchMapping": "PATCH",
}
_STATIC_FINAL_RE = re.compile(r"\bstatic\s+final\s+[\w<>\[\], ?]+\s+(\w+)\s*[=;]")
_USAGE_RE = re.compile(r"\b([A-Za-z_]\w*)\s*\.\s*([A-Za-z_]\w*)\s*\(")
_USAGE_SKIP_NAMES = {"if", "for", "while", "switch", "return", "new"}
_STATEMENT_PREFIXES = (
    "return ",
    "if ",
    "for ",
    "while ",
    "switch ",
    "catch ",
    "throw ",
    "new ",
)


class JavaPlugin:
    def supports(
        self,
        path: Path | PluginContext,
        language: str | None = None,
    ) -> bool:
        if isinstance(path, PluginContext):
            return (
                path.language == "java"
                or path.file_path.suffix.lower() == ".java"
            )
        return language == "java" or path.suffix.lower() == ".java"

    def parse(self, context: PluginContext, content: bytes) -> ParsedGraphFacts:
        from context_search_tool.java_graph import JavaGraphProducer

        parsed = JavaGraphProducer().parse(context, content)
        legacy = self.extract(
            context.file_path,
            content.decode("utf-8", errors="replace"),
        )
        if not parsed.fallback_required:
            return ParsedGraphFacts(
                facts=parsed.facts,
                symbols=tuple(legacy.symbols),
                lexical_tokens=tuple(legacy.lexical_tokens),
                metadata=parsed.metadata,
            )
        return ParsedGraphFacts(
            facts=(parsed.facts, legacy),
            symbols=tuple(legacy.symbols),
            lexical_tokens=tuple(legacy.lexical_tokens),
            metadata=parsed.metadata,
            fallback_required=True,
        )

    def materialize(
        self,
        context: PluginContext,
        parsed: ParsedGraphFacts,
        chunks: tuple,
        module_signal: CodeSignal,
    ) -> MaterializedGraph:
        from context_search_tool.java_graph import JavaGraphProducer

        if not parsed.fallback_required:
            return JavaGraphProducer().materialize(
                context,
                parsed,
                chunks,
                module_signal,
            )
        _facts, legacy = parsed.facts
        signals: list[CodeSignal] = []
        for signal in legacy.signals:
            chunk = next(
                (
                    item
                    for item in chunks
                    if item.start_line <= signal.start_line <= item.end_line
                ),
                None,
            )
            signals.append(
                replace(
                    signal,
                    file_path=context.file_path,
                    chunk_id=chunk.chunk_id if chunk is not None else signal.chunk_id,
                )
            )
        return MaterializedGraph(
            signals=tuple(signals),
            relations=tuple(legacy.relations),
            metadata=parsed.metadata,
        )

    def extract(self, path: Path, content: str) -> PluginExtraction:
        scrubbed_content = _strip_comments(content)
        lines = scrubbed_content.splitlines()
        original_lines = content.splitlines()
        symbols: list[SymbolRef] = []
        signals: list[CodeSignal] = []
        method_contexts: list[dict[str, Any]] = []
        tokens: list[str] = []
        metadata: dict[str, Any] = {}

        package_match = _PACKAGE_RE.search(scrubbed_content)
        if package_match:
            package_name = package_match.group(1)
            metadata["package"] = package_name
            _add_token(tokens, package_name)
            for segment in package_name.split("."):
                _add_token(tokens, segment)

        imports = _IMPORT_RE.findall(scrubbed_content)
        if imports:
            metadata["imports"] = imports
            for imported in imports:
                _add_token(tokens, imported.split(".")[-1].replace("*", ""))

        annotations_by_line = _annotations_by_line(lines, tokens)
        enum_ranges = _enum_ranges(lines)
        enum_names = _enum_names(lines)
        enum_constant_lines = _enum_constant_lines(lines, enum_ranges)
        class_contexts = _class_contexts(annotations_by_line, lines)
        type_contexts = _type_contexts(annotations_by_line, lines)
        receiver_types = _receiver_types_by_owner(lines, type_contexts)
        field_owner_by_line: dict[int, str] = {}
        for context in type_contexts:
            for top_level_line in _top_level_type_body_lines(lines, context):
                field_owner_by_line[top_level_line] = context["name"]

        for line_number, line in enumerate(lines, start=1):
            if not line.strip():
                continue
            type_match = _TYPE_RE.search(line)
            if type_match:
                kind, name = type_match.groups()
                end_line = enum_ranges.get(line_number, line_number)
                symbols.append(_symbol(name, kind, line_number, end_line))
                _add_identifier_tokens(tokens, name)
                if kind == "enum":
                    _extract_enum_values(lines, line_number, end_line, symbols, tokens)
                if kind == "class":
                    context = _class_context_for_line(class_contexts, line_number)
                    _add_route_tokens(tokens, context["route"] if context else "")
                comment = _comment_before_symbol(
                    original_lines, lines, annotations_by_line, line_number
                )
                if comment:
                    signals.append(
                        _comment_signal(
                            path=path,
                            comment=comment,
                            owner_type=name,
                            owner_method="",
                        )
                    )

            constant_match = _STATIC_FINAL_RE.search(line)
            if constant_match:
                name = constant_match.group(1)
                symbols.append(_symbol(name, "constant", line_number, line_number))
                _add_identifier_tokens(tokens, name)

            field_match = _FIELD_RE.search(line)
            if (
                field_match
                and line_number in field_owner_by_line
                and line_number not in enum_constant_lines
            ):
                field_type, field_name = field_match.groups()
                owner_type = field_owner_by_line[line_number]
                symbols.append(_symbol(field_name, "field", line_number, line_number))
                _add_identifier_tokens(tokens, field_name)
                _add_identifier_tokens(tokens, field_type)
                signals.append(
                    _field_signal(
                        path=path,
                        owner_type=owner_type,
                        field_type=field_type,
                        field_name=field_name,
                        line_number=line_number,
                    )
                )

            method_match = _method_match(lines, line_number)
            if (
                method_match
                and not _TYPE_RE.search(line)
                and not _is_statement_line(line)
            ):
                name = method_match.group(1)
                if line_number in enum_constant_lines or _is_enum_constructor(
                    name, line_number, enum_ranges, enum_names
                ):
                    continue
                symbols.append(_symbol(name, "method", line_number, line_number))
                _add_identifier_tokens(tokens, name)
                type_context = _type_context_for_line(type_contexts, line_number)
                class_context = _class_context_for_line(class_contexts, line_number)
                type_name = type_context["name"] if type_context else ""
                class_name = class_context["name"] if class_context else ""
                comment = _comment_before_symbol(
                    original_lines, lines, annotations_by_line, line_number
                )
                if comment:
                    signals.append(
                        _comment_signal(
                            path=path,
                            comment=comment,
                            owner_type=type_name,
                            owner_method=name,
                        )
                    )
                usage_signals = _usage_signals(
                    path=path,
                    lines=lines,
                    method_line=line_number,
                    owner_type=type_name,
                    owner_method=name,
                )
                signals.extend(usage_signals)
                route = _mapping_before_current_symbol(
                    annotations_by_line, lines, line_number
                )
                endpoint_signal_id = ""
                if route:
                    class_route = class_context["route"] if class_context else ""
                    full_path = _join_route(class_route, route["path"])
                    _add_route_tokens(tokens, route["path"])
                    _add_route_tokens(tokens, full_path)
                    if route["method"]:
                        _add_token(tokens, route["method"])
                    endpoint_signal = _endpoint_signal(
                        path=path,
                        controller=class_name,
                        method=name,
                        http_method=route["method"],
                        endpoint_path=full_path,
                        method_line=line_number,
                        mapping_line=route["line"],
                        original_lines=original_lines,
                    )
                    signals.append(endpoint_signal)
                    endpoint_signal_id = endpoint_signal.signal_id
                parameter_context = _method_parameter_context(
                    _method_signature_text(lines, line_number)
                )
                method_contexts.append(
                    {
                        "owner_type": type_name,
                        "method": name,
                        "line": line_number,
                        "usage_signals": usage_signals,
                        "endpoint_signal_id": endpoint_signal_id,
                        "parameter_types": parameter_context["parameter_types"],
                        "parameter_names": parameter_context["parameter_names"],
                    }
                )

        for annotation in _iter_annotations(lines):
            name = annotation["name"]
            if name in _SQL_ANNOTATIONS:
                _add_identifier_tokens(tokens, annotation["args"])

        relation_signals, relations = _relation_signals_and_relations(
            path=path,
            type_contexts=type_contexts,
            method_contexts=method_contexts,
            receiver_types=receiver_types,
        )
        signals.extend(relation_signals)

        return PluginExtraction(
            symbols=symbols,
            signals=signals,
            relations=relations,
            lexical_tokens=_dedupe(tokens),
            metadata=metadata,
        )


def _symbol(name: str, kind: str, start_line: int, end_line: int) -> SymbolRef:
    return SymbolRef(
        name=name,
        kind=kind,
        start_line=start_line,
        end_line=end_line,
        language="java",
        metadata={},
    )


def _comment_signal(
    path: Path,
    comment: dict[str, Any],
    owner_type: str,
    owner_method: str,
) -> CodeSignal:
    signal_name = f"{owner_method or owner_type} comment"
    signal_tokens: list[str] = []
    _add_identifier_tokens(signal_tokens, signal_name)
    for token in tokenize_identifier(comment["text"]):
        _add_token(signal_tokens, token)
    metadata = {"text": comment["text"]}
    if owner_type:
        metadata["owner_type"] = owner_type
    if owner_method:
        metadata["owner_method"] = owner_method
    return CodeSignal(
        signal_id=generate_signal_id(
            path, "comment", comment["start_line"], signal_name
        ),
        chunk_id="",
        file_path=path,
        kind="comment",
        name=signal_name,
        start_line=comment["start_line"],
        end_line=comment["end_line"],
        language="java",
        tokens=_dedupe(signal_tokens),
        metadata=metadata,
    )


def _usage_signal(
    path: Path,
    line_number: int,
    receiver: str,
    method: str,
    owner_type: str,
    owner_method: str,
) -> CodeSignal:
    signal_name = f"{receiver}.{method}"
    signal_tokens: list[str] = []
    _add_identifier_tokens(signal_tokens, receiver)
    _add_identifier_tokens(signal_tokens, method)
    metadata = {
        "receiver": receiver,
        "method": method,
        "owner_method": owner_method,
    }
    if owner_type:
        metadata["owner_type"] = owner_type
    return CodeSignal(
        signal_id=generate_signal_id(path, "usage", line_number, signal_name),
        chunk_id="",
        file_path=path,
        kind="usage",
        name=signal_name,
        start_line=line_number,
        end_line=line_number,
        language="java",
        tokens=_dedupe(signal_tokens),
        metadata=metadata,
    )


def _endpoint_signal(
    path: Path,
    controller: str,
    method: str,
    http_method: str,
    endpoint_path: str,
    method_line: int,
    mapping_line: int,
    original_lines: list[str],
) -> CodeSignal:
    signal_name = f"{http_method} {endpoint_path}".strip()
    signal_tokens: list[str] = []
    _add_token(signal_tokens, http_method)
    _add_route_tokens(signal_tokens, endpoint_path)
    _add_identifier_tokens(signal_tokens, controller)
    _add_identifier_tokens(signal_tokens, method)
    for token in _nearby_comment_tokens(original_lines, mapping_line):
        _add_token(signal_tokens, token)
    return CodeSignal(
        signal_id=generate_signal_id(path, "endpoint", method_line, signal_name),
        chunk_id="",
        file_path=path,
        kind="endpoint",
        name=signal_name,
        start_line=method_line,
        end_line=method_line,
        language="java",
        tokens=_dedupe(signal_tokens),
        metadata={
            "http_method": http_method,
            "path": endpoint_path,
            "controller": controller,
            "method": method,
        },
    )


def _type_signal(path: Path, context: dict[str, Any]) -> CodeSignal:
    signal_name = context["name"]
    signal_tokens: list[str] = []
    _add_identifier_tokens(signal_tokens, signal_name)
    return CodeSignal(
        signal_id=generate_signal_id(path, "type", context["start_line"], signal_name),
        chunk_id="",
        file_path=path,
        kind="type",
        name=signal_name,
        start_line=context["start_line"],
        end_line=context["start_line"],
        language="java",
        tokens=_dedupe(signal_tokens),
        metadata={"owner_type": signal_name},
    )


def _method_signal(path: Path, method_context: dict[str, Any]) -> CodeSignal:
    owner_type = method_context["owner_type"]
    method_name = method_context["method"]
    signal_name = f"{owner_type}.{method_name}" if owner_type else method_name
    parameter_types = method_context["parameter_types"]
    parameter_names = method_context["parameter_names"]
    signal_tokens: list[str] = []
    _add_identifier_tokens(signal_tokens, owner_type)
    _add_identifier_tokens(signal_tokens, method_name)
    for parameter_type in parameter_types:
        _add_identifier_tokens(signal_tokens, parameter_type)
    for parameter_name in parameter_names:
        _add_identifier_tokens(signal_tokens, parameter_name)
    metadata = {
        "owner_method": method_name,
        "parameter_types": parameter_types,
        "parameter_names": parameter_names,
    }
    if owner_type:
        metadata["owner_type"] = owner_type
    return CodeSignal(
        signal_id=generate_signal_id(path, "method", method_context["line"], signal_name),
        chunk_id="",
        file_path=path,
        kind="method",
        name=signal_name,
        start_line=method_context["line"],
        end_line=method_context["line"],
        language="java",
        tokens=_dedupe(signal_tokens),
        metadata=metadata,
    )


def _field_signal(
    path: Path,
    owner_type: str,
    field_type: str,
    field_name: str,
    line_number: int,
) -> CodeSignal:
    signal_name = f"{owner_type}.{field_name}" if owner_type else field_name
    signal_tokens: list[str] = []
    _add_identifier_tokens(signal_tokens, owner_type)
    _add_identifier_tokens(signal_tokens, field_type)
    _add_identifier_tokens(signal_tokens, field_name)
    return CodeSignal(
        signal_id=generate_signal_id(path, "field", line_number, signal_name),
        chunk_id="",
        file_path=path,
        kind="field",
        name=signal_name,
        start_line=line_number,
        end_line=line_number,
        language="java",
        tokens=_dedupe(signal_tokens),
        metadata={
            "owner_type": owner_type,
            "field": field_name,
            "field_type": _clean_java_type(field_type),
        },
    )


def _relation(
    source_signal_id: str,
    target_name: str,
    kind: str,
    confidence_basis: str,
    metadata: dict[str, Any],
) -> CodeRelation:
    relation_metadata = dict(metadata)
    relation_metadata["confidence_basis"] = confidence_basis
    return CodeRelation(
        relation_id=generate_relation_id(source_signal_id, target_name, kind),
        source_signal_id=source_signal_id,
        target_name=target_name,
        kind=kind,
        confidence=_relation_confidence(kind, confidence_basis),
        metadata=relation_metadata,
    )


def _relation_confidence(kind: str, confidence_basis: str) -> float:
    if kind == "implements":
        return 1.0
    if confidence_basis == "known_receiver":
        return 0.8
    if confidence_basis == "inferred_signature":
        return 0.6
    return 0.4


def _strip_comments(content: str) -> str:
    result: list[str] = []
    index = 0
    in_block_comment = False
    in_string = False
    in_char = False
    escaped = False
    while index < len(content):
        char = content[index]
        if in_block_comment:
            if content.startswith("*/", index):
                in_block_comment = False
                index += 2
            else:
                result.append("\n" if char == "\n" else " ")
                index += 1
        elif in_string or in_char:
            result.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif in_string and char == '"':
                in_string = False
            elif in_char and char == "'":
                in_char = False
            index += 1
        elif content.startswith("/*", index):
            in_block_comment = True
            result.append("  ")
            index += 2
        elif content.startswith("//", index):
            while index < len(content) and content[index] != "\n":
                result.append(" ")
                index += 1
        else:
            result.append(char)
            if char == '"':
                in_string = True
            elif char == "'":
                in_char = True
            index += 1
    return "".join(result)


def _comment_before_symbol(
    original_lines: list[str],
    lines: list[str],
    annotations_by_line: dict[int, list[dict[str, Any]]],
    line_number: int,
) -> dict[str, Any] | None:
    annotations = _contiguous_annotations_before(annotations_by_line, lines, line_number)
    lead_line = min((annotation["line"] for annotation in annotations), default=line_number)
    return _comment_ending_at(original_lines, lead_line - 1)


def _comment_ending_at(lines: list[str], end_line: int) -> dict[str, Any] | None:
    if end_line <= 0 or end_line > len(lines):
        return None

    stripped = lines[end_line - 1].strip()
    if not stripped:
        return None

    comment_lines: list[str] = []
    start_line = end_line
    if stripped.endswith("*/"):
        index = end_line - 1
        while index >= 0:
            comment_lines.append(_clean_block_comment_line(lines[index]))
            if "/*" in lines[index]:
                start_line = index + 1
                break
            index -= 1
        comment_lines.reverse()
    elif stripped.startswith("//"):
        index = end_line - 1
        while index >= 0 and lines[index].strip().startswith("//"):
            comment_lines.append(lines[index].strip()[2:].strip())
            start_line = index + 1
            index -= 1
        comment_lines.reverse()
    else:
        return None

    comment_text = " ".join(line for line in comment_lines if line)
    if not comment_text:
        return None
    return {"text": comment_text, "start_line": start_line, "end_line": end_line}


def _usage_signals(
    path: Path,
    lines: list[str],
    method_line: int,
    owner_type: str,
    owner_method: str,
) -> list[CodeSignal]:
    body_range = _method_body_range(lines, method_line)
    if not body_range:
        return []

    start_line, end_line = body_range
    signals: list[CodeSignal] = []
    seen: set[tuple[int, str, str]] = set()
    body_lines = _mask_string_literals(lines[start_line - 1 : end_line])
    for line_number, line in enumerate(body_lines, start=start_line):
        for match in _USAGE_RE.finditer(line):
            receiver, method = match.groups()
            if (
                receiver in _USAGE_SKIP_NAMES
                or method in _USAGE_SKIP_NAMES
                or receiver[:1].isupper()
            ):
                continue
            usage_key = (line_number, receiver, method)
            if usage_key in seen:
                continue
            seen.add(usage_key)
            signals.append(
                _usage_signal(
                    path=path,
                    line_number=line_number,
                    receiver=receiver,
                    method=method,
                    owner_type=owner_type,
                    owner_method=owner_method,
                )
            )
    return signals


def _relation_signals_and_relations(
    path: Path,
    type_contexts: list[dict[str, Any]],
    method_contexts: list[dict[str, Any]],
    receiver_types: dict[str, dict[str, str]],
) -> tuple[list[CodeSignal], list[CodeRelation]]:
    signals: list[CodeSignal] = []
    relations: list[CodeRelation] = []
    seen_relation_ids: set[str] = set()
    method_targets = _method_targets_by_name(method_contexts)

    for context in type_contexts:
        interfaces = context["interfaces"]
        if not interfaces:
            continue
        signal = _type_signal(path, context)
        signals.append(signal)
        for interface in interfaces:
            _append_relation(
                relations,
                seen_relation_ids,
                _relation(
                    source_signal_id=signal.signal_id,
                    target_name=interface,
                    kind="implements",
                    confidence_basis="implements",
                    metadata={"source_type": context["name"]},
                ),
            )

    for method_context in method_contexts:
        usage_signals = method_context["usage_signals"]
        source_signal_id = method_context["endpoint_signal_id"]
        relation_kind = "calls" if source_signal_id else "uses"
        if not source_signal_id:
            signal = _method_signal(path, method_context)
            signals.append(signal)
            source_signal_id = signal.signal_id
        if not usage_signals:
            continue

        owner_type = method_context["owner_type"]
        owner_receiver_types = receiver_types.get(owner_type, {})
        for usage_signal in usage_signals:
            target_name, confidence_basis, receiver_type = _usage_relation_target(
                usage_signal, owner_receiver_types, method_targets
            )
            metadata = {
                "receiver": usage_signal.metadata["receiver"],
                "method": usage_signal.metadata["method"],
                "owner_method": method_context["method"],
            }
            if owner_type:
                metadata["owner_type"] = owner_type
            if receiver_type:
                metadata["receiver_type"] = receiver_type
            _append_relation(
                relations,
                seen_relation_ids,
                _relation(
                    source_signal_id=source_signal_id,
                    target_name=target_name,
                    kind=relation_kind,
                    confidence_basis=confidence_basis,
                    metadata=metadata,
                ),
            )

    return signals, relations


def _append_relation(
    relations: list[CodeRelation],
    seen_relation_ids: set[str],
    relation: CodeRelation,
) -> None:
    if relation.relation_id in seen_relation_ids:
        return
    seen_relation_ids.add(relation.relation_id)
    relations.append(relation)


def _usage_relation_target(
    usage_signal: CodeSignal,
    receiver_types: dict[str, str],
    method_targets: dict[str, set[str]],
) -> tuple[str, str, str]:
    receiver = usage_signal.metadata["receiver"]
    method = usage_signal.metadata["method"]
    receiver_type = receiver_types.get(receiver, "")
    if receiver_type:
        return f"{receiver_type}.{method}", "known_receiver", receiver_type

    candidates = method_targets.get(method, set())
    if len(candidates) == 1:
        inferred_type = next(iter(candidates))
        return f"{inferred_type}.{method}", "inferred_signature", inferred_type

    return method, "name_only", ""


def _method_targets_by_name(
    method_contexts: list[dict[str, Any]],
) -> dict[str, set[str]]:
    targets: dict[str, set[str]] = {}
    for method_context in method_contexts:
        owner_type = method_context["owner_type"]
        if not owner_type:
            continue
        targets.setdefault(method_context["method"], set()).add(owner_type)
    return targets


def _mask_string_literals(lines: list[str]) -> list[str]:
    masked_lines: list[str] = []
    in_string = False
    in_char = False
    escaped = False
    for line in lines:
        masked: list[str] = []
        for char in line:
            if in_string or in_char:
                masked.append(" ")
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif in_string and char == '"':
                    in_string = False
                elif in_char and char == "'":
                    in_char = False
                continue

            if char == '"':
                in_string = True
                masked.append(" ")
            elif char == "'":
                in_char = True
                masked.append(" ")
            else:
                masked.append(char)
        masked_lines.append("".join(masked))
    return masked_lines


def _method_body_range(lines: list[str], method_line: int) -> tuple[int, int] | None:
    for line_number in range(method_line, len(lines) + 1):
        line = lines[line_number - 1]
        brace_index = line.find("{")
        semicolon_index = line.find(";")
        if brace_index >= 0 and (semicolon_index < 0 or brace_index < semicolon_index):
            return line_number, _block_end_line(lines, method_line)
        if semicolon_index >= 0:
            return None
    return None


def _method_match(lines: list[str], line_number: int) -> re.Match[str] | None:
    line = lines[line_number - 1]
    match = _METHOD_RE.search(line)
    if match:
        return match

    if "(" not in line or _is_statement_line(line):
        return None

    signature = line.strip()
    for next_line_number in range(line_number + 1, min(len(lines), line_number + 8) + 1):
        next_line = lines[next_line_number - 1].strip()
        signature = f"{signature} {next_line}"
        if "{" in next_line or ";" in next_line:
            return _METHOD_RE.search(signature)
    return None


def _method_signature_text(lines: list[str], line_number: int) -> str:
    signature_parts: list[str] = []
    paren_depth = 0
    saw_parameters = False
    for current_line_number in range(line_number, len(lines) + 1):
        line = lines[current_line_number - 1].strip()
        signature_parts.append(line)
        for char in line:
            if char == "(":
                paren_depth += 1
                saw_parameters = True
            elif char == ")" and paren_depth > 0:
                paren_depth -= 1
        if saw_parameters and paren_depth == 0:
            break
        if "{" in line or ";" in line:
            break
    return " ".join(signature_parts)


def _annotations_by_line(
    lines: list[str], tokens: list[str]
) -> dict[int, list[dict[str, Any]]]:
    grouped: dict[int, list[dict[str, Any]]] = {}
    for annotation in _iter_annotations(lines):
        grouped.setdefault(annotation["line"], []).append(annotation)
        _add_identifier_tokens(tokens, annotation["name"])
    return grouped


def _iter_annotations(lines: list[str]) -> list[dict[str, Any]]:
    annotations: list[dict[str, Any]] = []
    line_number = 1
    while line_number <= len(lines):
        line = lines[line_number - 1]
        stripped = line.lstrip()
        match = _ANNOTATION_START_RE.match(stripped)
        if not match:
            line_number += 1
            continue

        indentation = len(line) - len(stripped)
        args, end_line = _annotation_args(
            lines, line_number, indentation + match.end()
        )
        annotations.append(
            {
                "line": line_number,
                "end_line": end_line,
                "name": match.group(1),
                "args": args,
            }
        )
        line_number = end_line + 1
    return annotations


def _annotation_args(
    lines: list[str], start_line: int, search_start: int
) -> tuple[str, int]:
    first_line_tail = lines[start_line - 1][search_start:]
    open_index = first_line_tail.find("(")
    if open_index < 0:
        return "", start_line

    args_parts: list[str] = []
    depth = 0
    started = False
    for line_number in range(start_line, len(lines) + 1):
        line = lines[line_number - 1]
        index = search_start + open_index if line_number == start_line else 0
        while index < len(line):
            char = line[index]
            if char == "(":
                depth += 1
                if started:
                    args_parts.append(char)
                started = True
            elif char == ")":
                depth -= 1
                if depth == 0:
                    return "".join(args_parts).strip(), line_number
                args_parts.append(char)
            elif started:
                args_parts.append(char)
            index += 1
        if started and depth > 0:
            args_parts.append("\n")

    return "".join(args_parts).strip(), len(lines)


def _class_contexts(
    annotations_by_line: dict[int, list[dict[str, Any]]],
    lines: list[str],
) -> list[dict[str, Any]]:
    contexts: list[dict[str, Any]] = []
    for line_number, line in enumerate(lines, start=1):
        type_match = _TYPE_RE.search(line)
        if not type_match or type_match.group(1) != "class":
            continue
        contexts.append(
            {
                "name": type_match.group(2),
                "route": _class_route_before(annotations_by_line, lines, line_number),
                "start_line": line_number,
                "end_line": _block_end_line(lines, line_number),
            }
        )
    return contexts


def _type_contexts(
    annotations_by_line: dict[int, list[dict[str, Any]]],
    lines: list[str],
) -> list[dict[str, Any]]:
    contexts: list[dict[str, Any]] = []
    for line_number, line in enumerate(lines, start=1):
        type_match = _TYPE_RE.search(line)
        if not type_match:
            continue
        kind, name = type_match.groups()
        contexts.append(
            {
                "kind": kind,
                "name": name,
                "interfaces": _implemented_interfaces(line),
                "route": _class_route_before(annotations_by_line, lines, line_number)
                if kind == "class"
                else "",
                "start_line": line_number,
                "end_line": _block_end_line(lines, line_number),
            }
        )
    return contexts


def _class_context_for_line(
    contexts: list[dict[str, Any]], line_number: int
) -> dict[str, Any] | None:
    matches = [
        context
        for context in contexts
        if context["start_line"] <= line_number <= context["end_line"]
    ]
    return max(matches, key=lambda context: context["start_line"]) if matches else None


def _type_context_for_line(
    contexts: list[dict[str, Any]], line_number: int
) -> dict[str, Any] | None:
    matches = [
        context
        for context in contexts
        if context["start_line"] <= line_number <= context["end_line"]
    ]
    return max(matches, key=lambda context: context["start_line"]) if matches else None


def _receiver_types_by_owner(
    lines: list[str], type_contexts: list[dict[str, Any]]
) -> dict[str, dict[str, str]]:
    receiver_types: dict[str, dict[str, str]] = {}
    for context in type_contexts:
        owner_types: dict[str, str] = {}
        for line_number in _top_level_type_body_lines(lines, context):
            line = lines[line_number - 1]
            if "(" in line:
                _add_constructor_assignment_types(lines, context, line_number, owner_types)
                continue
            field_match = _FIELD_RE.search(line)
            if field_match:
                field_type, field_name = field_match.groups()
                owner_types[field_name] = _clean_java_type(field_type)
        if owner_types:
            receiver_types[context["name"]] = owner_types
    return receiver_types


def _add_constructor_assignment_types(
    lines: list[str],
    context: dict[str, Any],
    line_number: int,
    receiver_types: dict[str, str],
) -> None:
    parameters = _constructor_parameters(
        _method_signature_text(lines, line_number), context["name"]
    )
    if not parameters:
        return
    body_range = _method_body_range(lines, line_number)
    if not body_range:
        return

    start_line, end_line = body_range
    for line in lines[start_line - 1 : end_line]:
        assignment_match = _ASSIGNMENT_RE.search(line)
        if not assignment_match:
            continue
        field_name, parameter_name = assignment_match.groups()
        parameter_type = parameters.get(parameter_name)
        if parameter_type:
            receiver_types[field_name] = parameter_type


def _constructor_parameters(line: str, type_name: str) -> dict[str, str]:
    match = re.search(
        rf"^\s*(?:(?:public|protected|private)\s+)?{re.escape(type_name)}\s*\(",
        line,
    )
    if not match:
        return {}
    return _parameter_types(_method_parameter_text(line))


def _parameter_types(parameters: str) -> dict[str, str]:
    parameter_types: dict[str, str] = {}
    for parameter in _split_java_parameters(parameters):
        cleaned = re.sub(r"@\w+(?:\([^)]*\))?\s*", "", parameter).strip()
        cleaned = re.sub(r"\bfinal\s+", "", cleaned).strip()
        if not cleaned:
            continue
        parts = cleaned.replace("...", " ").split()
        if len(parts) < 2:
            continue
        parameter_name = parts[-1]
        parameter_type = _clean_java_type(" ".join(parts[:-1]))
        if parameter_type:
            parameter_types[parameter_name] = parameter_type
    return parameter_types


def _method_parameter_context(line: str) -> dict[str, list[str]]:
    parameter_text = _method_parameter_text(line)
    if not parameter_text:
        return {"parameter_types": [], "parameter_names": []}

    parameter_types: list[str] = []
    parameter_names: list[str] = []
    for parameter in _split_java_parameters(parameter_text):
        cleaned = re.sub(r"@\w+(?:\([^)]*\))?\s*", "", parameter).strip()
        cleaned = re.sub(r"\bfinal\s+", "", cleaned).strip()
        if not cleaned:
            continue
        parts = cleaned.replace("...", " ").split()
        if len(parts) < 2:
            continue
        parameter_types.append(_clean_java_type(" ".join(parts[:-1])))
        parameter_names.append(parts[-1])
    return {
        "parameter_types": parameter_types,
        "parameter_names": parameter_names,
    }


def _method_parameter_text(signature: str) -> str:
    start = signature.find("(")
    if start < 0:
        return ""

    depth = 0
    parameter_chars: list[str] = []
    for char in signature[start:]:
        if char == "(":
            depth += 1
            if depth == 1:
                continue
        elif char == ")" and depth > 0:
            depth -= 1
            if depth == 0:
                return "".join(parameter_chars).strip()
        if depth > 0:
            parameter_chars.append(char)
    return ""


def _split_java_parameters(parameters: str) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    angle_depth = 0
    paren_depth = 0
    for char in parameters:
        if char == "<":
            angle_depth += 1
        elif char == ">" and angle_depth > 0:
            angle_depth -= 1
        elif char == "(":
            paren_depth += 1
        elif char == ")" and paren_depth > 0:
            paren_depth -= 1
        if char == "," and angle_depth == 0 and paren_depth == 0:
            parts.append("".join(current).strip())
            current = []
            continue
        current.append(char)
    if current:
        parts.append("".join(current).strip())
    return parts


def _top_level_type_body_lines(
    lines: list[str], context: dict[str, Any]
) -> list[int]:
    body_lines: list[int] = []
    masked_lines = _mask_string_literals(
        lines[context["start_line"] - 1 : context["end_line"]]
    )
    depth = 0
    for offset, line in enumerate(masked_lines):
        line_number = context["start_line"] + offset
        if depth == 1 and line_number != context["start_line"]:
            body_lines.append(line_number)
        depth += line.count("{") - line.count("}")
    return body_lines


def _implemented_interfaces(line: str) -> list[str]:
    match = _IMPLEMENTS_RE.search(line)
    if not match:
        return []
    return [
        interface
        for interface in (
            _clean_java_type(part) for part in _split_java_parameters(match.group(1))
        )
        if interface
    ]


def _clean_java_type(type_text: str) -> str:
    cleaned = type_text.strip()
    cleaned = re.sub(r"<.*>", "", cleaned).strip()
    cleaned = cleaned.replace("[]", "").strip()
    cleaned = cleaned.split()[-1] if cleaned.split() else ""
    return cleaned.split(".")[-1]


def _block_end_line(lines: list[str], start_line: int) -> int:
    depth = 0
    started = False
    in_string = False
    in_char = False
    escaped = False
    for line_number in range(start_line, len(lines) + 1):
        for char in lines[line_number - 1]:
            if in_string or in_char:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif in_string and char == '"':
                    in_string = False
                elif in_char and char == "'":
                    in_char = False
                continue

            if char == '"':
                in_string = True
                continue
            if char == "'":
                in_char = True
                continue

            if char == "{":
                depth += 1
                started = True
            elif char == "}":
                depth -= 1
                if started and depth <= 0:
                    return line_number
    return start_line


def _class_route_before(
    annotations_by_line: dict[int, list[dict[str, Any]]],
    lines: list[str],
    line_number: int,
) -> str:
    for annotation in _contiguous_annotations_before(
        annotations_by_line, lines, line_number
    ):
        if annotation["name"] == "RequestMapping":
            return _annotation_path(annotation["args"])
    return ""


def _mapping_before_current_symbol(
    annotations_by_line: dict[int, list[dict[str, Any]]],
    lines: list[str],
    line_number: int,
) -> dict[str, Any] | None:
    for annotation in _contiguous_annotations_before(
        annotations_by_line, lines, line_number
    ):
        if annotation["name"] in _MAPPING_ANNOTATIONS:
            return {
                "path": _annotation_path(annotation["args"]),
                "method": _http_method(annotation["name"], annotation["args"]),
                "line": annotation["line"],
            }
    return None


def _contiguous_annotations_before(
    annotations_by_line: dict[int, list[dict[str, Any]]],
    lines: list[str],
    line_number: int,
) -> list[dict[str, Any]]:
    annotations: list[dict[str, Any]] = []
    cursor = line_number - 1
    while cursor > 0:
        if not lines[cursor - 1].strip():
            break
        ending_here = _annotations_ending_on(annotations_by_line, cursor)
        if not ending_here:
            break
        annotations.extend(ending_here)
        cursor = min(annotation["line"] for annotation in ending_here) - 1
    return annotations


def _annotations_ending_on(
    annotations_by_line: dict[int, list[dict[str, Any]]], line_number: int
) -> list[dict[str, Any]]:
    return [
        annotation
        for annotations in annotations_by_line.values()
        for annotation in annotations
        if annotation["end_line"] == line_number
    ]


def _nearby_comment_tokens(lines: list[str], line_number: int) -> list[str]:
    comment = _comment_ending_at(lines, line_number - 1)
    return tokenize_identifier(comment["text"]) if comment else []


def _clean_block_comment_line(line: str) -> str:
    cleaned = line.strip()
    cleaned = re.sub(r"^/\*\*?", "", cleaned)
    cleaned = re.sub(r"\*/$", "", cleaned)
    cleaned = cleaned.strip()
    cleaned = re.sub(r"^\*\s?", "", cleaned)
    return cleaned.strip()


def _annotation_path(args: str) -> str:
    value_match = re.search(r'value\s*=\s*"([^"]*)"', args)
    if value_match:
        return value_match.group(1)
    string_match = re.search(r'"([^"]*)"', args)
    return string_match.group(1) if string_match else ""


def _http_method(annotation_name: str, args: str) -> str:
    if annotation_name in _HTTP_BY_MAPPING:
        return _HTTP_BY_MAPPING[annotation_name]
    method_match = re.search(r"RequestMethod\.(\w+)", args)
    return method_match.group(1).upper() if method_match else ""


def _join_route(base: str, suffix: str) -> str:
    if not base:
        return suffix
    if not suffix:
        return base
    return f"/{base.strip('/')}/{suffix.strip('/')}"


def _add_route_tokens(tokens: list[str], route: str) -> None:
    if not route:
        return
    tokens.append(route.strip())
    _add_token(tokens, route)
    _add_identifier_tokens(tokens, route)


def _extract_enum_values(
    lines: list[str],
    start_line: int,
    end_line: int,
    symbols: list[SymbolRef],
    tokens: list[str],
) -> None:
    for name, line_number in _enum_constants(lines, start_line, end_line):
        symbols.append(_symbol(name, "enum_value", line_number, line_number))
        _add_token(tokens, name)
        _add_identifier_tokens(tokens, name)


def _enum_constants(
    lines: list[str], start_line: int, end_line: int
) -> list[tuple[str, int]]:
    entries: list[tuple[str, int]] = []
    constant_text = ""
    constant_start_line = start_line
    paren_depth = 0
    seen_open_brace = False

    for line_number in range(start_line, end_line + 1):
        line = lines[line_number - 1]
        index = line.find("{") + 1 if not seen_open_brace else 0
        seen_open_brace = seen_open_brace or "{" in line
        while index < len(line):
            char = line[index]
            if char == "(":
                paren_depth += 1
            elif char == ")":
                paren_depth = max(0, paren_depth - 1)
            elif char in {",", ";", "}"} and paren_depth == 0:
                _append_enum_constant(entries, constant_text, constant_start_line)
                constant_text = ""
                constant_start_line = line_number
                if char in {";", "}"}:
                    return entries
                index += 1
                continue

            if constant_text or not char.isspace():
                if not constant_text:
                    constant_start_line = line_number
                constant_text += char
            index += 1

    _append_enum_constant(entries, constant_text, constant_start_line)
    return entries


def _append_enum_constant(
    entries: list[tuple[str, int]], constant_text: str, line_number: int
) -> None:
    match = re.match(r"\s*([A-Z][A-Z0-9_]*)\b", constant_text)
    if match:
        entries.append((match.group(1), line_number))


def _enum_ranges(lines: list[str]) -> dict[int, int]:
    ranges: dict[int, int] = {}
    for index, line in enumerate(lines):
        if not re.search(r"\benum\s+\w+", line):
            continue
        depth = line.count("{") - line.count("}")
        for end_index in range(index + 1, len(lines)):
            depth += lines[end_index].count("{") - lines[end_index].count("}")
            if depth <= 0:
                ranges[index + 1] = end_index + 1
                break
        else:
            ranges[index + 1] = index + 1
    return ranges


def _enum_names(lines: list[str]) -> dict[int, str]:
    names: dict[int, str] = {}
    for line_number, line in enumerate(lines, start=1):
        match = re.search(r"\benum\s+(\w+)", line)
        if match:
            names[line_number] = match.group(1)
    return names


def _enum_constant_lines(lines: list[str], enum_ranges: dict[int, int]) -> set[int]:
    return {
        line_number
        for start_line, end_line in enum_ranges.items()
        for _, line_number in _enum_constants(lines, start_line, end_line)
    }


def _is_enum_constructor(
    name: str,
    line_number: int,
    enum_ranges: dict[int, int],
    enum_names: dict[int, str],
) -> bool:
    for start_line, end_line in enum_ranges.items():
        if start_line <= line_number <= end_line and enum_names.get(start_line) == name:
            return True
    return False


def _is_statement_line(line: str) -> bool:
    stripped = line.strip()
    return stripped in {"return", "throw"} or stripped.startswith(_STATEMENT_PREFIXES)


def _add_identifier_tokens(tokens: list[str], value: str) -> None:
    for token in tokenize_identifier(value):
        _add_token(tokens, token)


def _add_token(tokens: list[str], token: str) -> None:
    normalized = token.strip().lower()
    if normalized:
        tokens.append(normalized)


def _dedupe(tokens: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for token in tokens:
        if token not in seen:
            seen.add(token)
            deduped.append(token)
    return deduped
