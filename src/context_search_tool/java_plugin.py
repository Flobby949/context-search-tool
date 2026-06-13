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
_ANNOTATION_RE = re.compile(r"@(\w+)(?:\((.*)\))?")
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
_ENUM_VALUE_RE = re.compile(r"\b([A-Z][A-Z0-9_]*)\b")


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
                if kind == "class":
                    class_route = _nearest_route_before(annotations_by_line, line_number)

            constant_match = _STATIC_FINAL_RE.search(line)
            if constant_match:
                name = constant_match.group(1)
                symbols.append(_symbol(name, "constant", line_number, line_number))
                _add_identifier_tokens(tokens, name)

            method_match = _METHOD_RE.search(line)
            if method_match and not _TYPE_RE.search(line):
                name = method_match.group(1)
                symbols.append(_symbol(name, "method", line_number, line_number))
                _add_identifier_tokens(tokens, name)
                route = _nearest_mapping_before(annotations_by_line, line_number)
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
    for line_number, line in enumerate(lines, start=1):
        for match in _ANNOTATION_RE.finditer(line):
            annotations.append(
                {
                    "line": line_number,
                    "name": match.group(1),
                    "args": (match.group(2) or "").strip(),
                }
            )
    return annotations


def _nearest_route_before(
    annotations_by_line: dict[int, list[dict[str, Any]]], line_number: int
) -> str:
    for candidate_line in range(line_number - 1, 0, -1):
        annotations = annotations_by_line.get(candidate_line, [])
        if not annotations and candidate_line < line_number - 3:
            return ""
        for annotation in annotations:
            if annotation["name"] == "RequestMapping":
                return _annotation_path(annotation["args"])
    return ""


def _nearest_mapping_before(
    annotations_by_line: dict[int, list[dict[str, Any]]], line_number: int
) -> dict[str, str] | None:
    for candidate_line in range(line_number - 1, 0, -1):
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
    for line_number in range(start_line + 1, end_line + 1):
        for name in _ENUM_VALUE_RE.findall(lines[line_number - 1]):
            symbols.append(_symbol(name, "enum_value", line_number, line_number))
            _add_token(tokens, name)
            _add_identifier_tokens(tokens, name)


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
