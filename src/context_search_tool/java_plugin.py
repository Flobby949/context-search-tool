from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from context_search_tool.models import SymbolRef
from context_search_tool.plugins import PluginExtraction
from context_search_tool.tokenizer import tokenize_identifier


_PACKAGE_RE = re.compile(r"package\s+([\w.]+)\s*;")
_IMPORT_RE = re.compile(r"import\s+([\w.*]+)\s*;")
_TYPE_RE = re.compile(r"\b(class|interface|enum)\s+(\w+)")
_ANNOTATION_START_RE = re.compile(r"@(\w+)")
_METHOD_RE = re.compile(
    r"^\s*(?:(?:public|protected|private|static|final|abstract|synchronized|native)\s+)*"
    r"[\w<>\[\], ?]+\s+(\w+)\s*\([^;{}]*\)\s*(?:throws\s+[^{;]+)?[;{]"
)
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
    def supports(self, path: Path, language: str) -> bool:
        return language == "java" or path.suffix.lower() == ".java"

    def extract(self, path: Path, content: str) -> PluginExtraction:
        lines = content.splitlines()
        symbols: list[SymbolRef] = []
        tokens: list[str] = []
        metadata: dict[str, Any] = {}

        package_match = _PACKAGE_RE.search(content)
        if package_match:
            package_name = package_match.group(1)
            metadata["package"] = package_name
            _add_token(tokens, package_name)
            for segment in package_name.split("."):
                _add_token(tokens, segment)

        imports = _IMPORT_RE.findall(content)
        if imports:
            metadata["imports"] = imports
            for imported in imports:
                _add_token(tokens, imported.split(".")[-1].replace("*", ""))

        annotations_by_line = _annotations_by_line(lines, tokens)
        enum_ranges = _enum_ranges(lines)
        enum_names = _enum_names(lines)
        enum_constant_lines = _enum_constant_lines(lines, enum_ranges)
        class_route = ""

        for line_number, line in enumerate(lines, start=1):
            type_match = _TYPE_RE.search(line)
            if type_match:
                kind, name = type_match.groups()
                end_line = enum_ranges.get(line_number, line_number)
                symbols.append(_symbol(name, kind, line_number, end_line))
                _add_identifier_tokens(tokens, name)
                if kind == "enum":
                    _extract_enum_values(lines, line_number, end_line, symbols, tokens)
                class_route = (
                    _nearest_route_before(annotations_by_line, lines, line_number)
                    if kind == "class"
                    else ""
                )
                _add_route_tokens(tokens, class_route)

            constant_match = _STATIC_FINAL_RE.search(line)
            if constant_match:
                name = constant_match.group(1)
                symbols.append(_symbol(name, "constant", line_number, line_number))
                _add_identifier_tokens(tokens, name)

            method_match = _METHOD_RE.search(line)
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
                route = _nearest_mapping_before(annotations_by_line, lines, line_number)
                if route:
                    full_path = _join_route(class_route, route["path"])
                    _add_route_tokens(tokens, route["path"])
                    _add_route_tokens(tokens, full_path)
                    if route["method"]:
                        _add_token(tokens, route["method"])

        for annotation in _iter_annotations(lines):
            name = annotation["name"]
            if name in _SQL_ANNOTATIONS:
                _add_identifier_tokens(tokens, annotation["args"])

        return PluginExtraction(
            symbols=symbols,
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
        match = _ANNOTATION_START_RE.search(line)
        if not match:
            line_number += 1
            continue

        args, end_line = _annotation_args(lines, line_number, match.end())
        annotations.append(
            {
                "line": line_number,
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


def _nearest_route_before(
    annotations_by_line: dict[int, list[dict[str, Any]]],
    lines: list[str],
    line_number: int,
) -> str:
    for candidate_line in range(line_number - 1, 0, -1):
        if _TYPE_RE.search(lines[candidate_line - 1]):
            return ""
        annotations = annotations_by_line.get(candidate_line, [])
        if not annotations and candidate_line < line_number - 3:
            return ""
        for annotation in annotations:
            if annotation["name"] == "RequestMapping":
                return _annotation_path(annotation["args"])
    return ""


def _nearest_mapping_before(
    annotations_by_line: dict[int, list[dict[str, Any]]],
    lines: list[str],
    line_number: int,
) -> dict[str, str] | None:
    for candidate_line in range(line_number - 1, 0, -1):
        if _TYPE_RE.search(lines[candidate_line - 1]):
            return None
        annotations = annotations_by_line.get(candidate_line, [])
        if not annotations and candidate_line < line_number - 3:
            return None
        for annotation in annotations:
            if annotation["name"] in _MAPPING_ANNOTATIONS:
                return {
                    "path": _annotation_path(annotation["args"]),
                    "method": _http_method(annotation["name"], annotation["args"]),
                }
    return None


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
