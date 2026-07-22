from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass, replace
from pathlib import PurePosixPath
import re
from typing import Any, Iterator

from context_search_tool.graph_contract import (
    MAX_FRONTEND_IMPORTS_PER_FILE,
    MAX_ROUTES_PER_ROUTER_FILE,
    generate_v5_relation_id,
    generate_v5_signal_id,
)
from context_search_tool.graph_plugins import (
    MaterializedGraph,
    ParsedGraphFacts,
    PluginContext,
)
from context_search_tool.models import CodeRelation, CodeSignal, DocumentChunk
from context_search_tool.syntax_parsers import (
    parse_javascript,
    parse_jsx,
    parse_tsx,
    parse_typescript,
)


_CANDIDATE_SUFFIXES = (".ts", ".tsx", ".js", ".jsx", ".vue", ".d.ts")
_INDEX_CANDIDATES = ("index.ts", "index.tsx", "index.js", "index.vue")
_EXPLICIT_SUFFIXES = (
    ".d.ts",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".vue",
    ".mjs",
    ".cjs",
    ".json",
    ".css",
)
_VOID_HTML_TAGS = frozenset(
    {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    }
)
_SCOPE_TYPES = frozenset(
    {
        "program",
        "statement_block",
        "function_declaration",
        "function_expression",
        "generator_function_declaration",
        "generator_function",
        "arrow_function",
        "method_definition",
        "class_body",
        "catch_clause",
    }
)
_RELEVANT_ERROR_RE = re.compile(
    rb"\b(?:import|export|createRouter|createBrowserRouter|useRoutes|Route|routes|path|component|Component|element|lazy)\b"
)
_GRAPH_PRODUCER = "frontend_graph"
_GRAPH_TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


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
class VueScriptRange:
    language: str
    setup: bool
    content_range: SourceRange


@dataclass(frozen=True)
class ModuleSelector:
    state: str
    specifier: str
    candidates: tuple[str, ...]
    source_kind: str


@dataclass(frozen=True)
class ImportBinding:
    local_name: str
    imported_name: str
    kind: str
    is_type_only: bool


@dataclass(frozen=True)
class FrontendImportFact:
    kind: str
    specifier: str
    selector: ModuleSelector
    bindings: tuple[ImportBinding, ...]
    source_range: SourceRange


@dataclass(frozen=True)
class FrontendRouteFact:
    framework: str
    path: str
    component: ModuleSelector
    source_range: SourceRange


@dataclass(frozen=True)
class FrontendFactSet:
    persistent_facts_allowed: bool
    imports: tuple[FrontendImportFact, ...]
    routes: tuple[FrontendRouteFact, ...]
    script_ranges: tuple[VueScriptRange, ...]
    diagnostics: tuple[FactDiagnostic, ...]


@dataclass(frozen=True)
class _ParsedUnit:
    source: bytes
    base_offset: int
    root: Any


@dataclass(frozen=True)
class _BindingTarget:
    module: str
    imported_name: str
    selector: ModuleSelector


@dataclass(frozen=True)
class _ConstArray:
    node: Any
    scope_key: tuple[str, int, int]


class FrontendGraphProducer:
    def supports(self, context: PluginContext) -> bool:
        return context.file_path.suffix.lower() in {
            ".js",
            ".jsx",
            ".ts",
            ".tsx",
            ".vue",
        }

    def parse(self, context: PluginContext, content: bytes) -> ParsedGraphFacts:
        if not self.supports(context):
            raise ValueError("FrontendGraphProducer received an unsupported source")
        facts = extract_frontend_facts(context.file_path.as_posix(), content)
        tokens: list[str] = []
        for fact in facts.imports:
            _add_graph_tokens(tokens, fact.specifier)
            for binding in fact.bindings:
                _add_graph_tokens(tokens, binding.local_name)
                _add_graph_tokens(tokens, binding.imported_name)
        for route in facts.routes:
            _add_graph_tokens(tokens, route.path)
        return ParsedGraphFacts(
            facts=facts,
            lexical_tokens=tuple(tokens),
            metadata={
                "graph_parse_status": (
                    "ast" if facts.persistent_facts_allowed else "rejected"
                ),
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
        if (
            not isinstance(facts, FrontendFactSet)
            or not facts.persistent_facts_allowed
        ):
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
        route_chunks = [
            _graph_containing_chunk(ordered_chunks, route.source_range.start_line)
            for route in facts.routes
        ]
        if any(chunk is None for chunk in route_chunks):
            metadata = dict(parsed.metadata)
            metadata["graph_materialize_status"] = "missing_chunk"
            return MaterializedGraph(metadata=metadata)

        signals: list[CodeSignal] = []
        relations: dict[str, CodeRelation] = {}
        for fact in facts.imports:
            relation = _frontend_relation(
                context=context,
                source=module_signal,
                kind="imports",
                selector=fact.selector,
                source_range=fact.source_range,
                target_name=fact.specifier,
                extra_metadata={
                    "import_kind": fact.kind,
                    "bindings": [
                        {
                            "local_name": binding.local_name,
                            "imported_name": binding.imported_name,
                            "kind": binding.kind,
                            "is_type_only": binding.is_type_only,
                        }
                        for binding in fact.bindings
                    ],
                },
            )
            _merge_frontend_relation(relations, relation)

        for route, chunk in zip(facts.routes, route_chunks):
            assert chunk is not None
            signal = _frontend_route_signal(context, route, chunk)
            signals.append(signal)
            relation = _frontend_relation(
                context=context,
                source=signal,
                kind="routes_to",
                selector=route.component,
                source_range=route.source_range,
                target_name=route.component.specifier,
                extra_metadata={
                    "framework": route.framework,
                    "path": route.path,
                },
            )
            _merge_frontend_relation(relations, relation)

        signals.sort(
            key=lambda item: (
                item.start_line,
                item.start_column,
                item.qualified_name,
                item.signal_id,
            )
        )
        materialized_relations = tuple(
            sorted(
                relations.values(),
                key=lambda item: (
                    int(item.metadata.get("first_source_line", 0)),
                    int(item.metadata.get("first_source_column", 0)),
                    item.kind,
                    item.target_qualified_name,
                    item.relation_id,
                ),
            )
        )
        return MaterializedGraph(
            signals=tuple(signals),
            relations=materialized_relations,
            metadata=parsed.metadata,
        )


def lex_vue_script_ranges(source: bytes) -> tuple[VueScriptRange, ...]:
    if not isinstance(source, bytes):
        raise TypeError("source must be bytes")

    line_starts = _line_starts(source)
    stack: list[str] = []
    ranges: list[VueScriptRange] = []
    position = 0
    while position < len(source):
        start = source.find(b"<", position)
        if start < 0:
            break
        if source.startswith(b"<!--", start):
            position = _closed_section(source, start, b"-->")
            continue
        if source.startswith(b"<![CDATA[", start):
            position = _closed_section(source, start, b"]]>")
            continue
        if source.startswith(b"<?", start):
            position = _closed_section(source, start, b"?>")
            continue
        end = _markup_tag_end(source, start)
        body = source[start + 1 : end - 1]
        match = re.match(rb"\s*(/?)\s*([A-Za-z][A-Za-z0-9:_.-]*)(?P<attrs>.*)\Z", body, re.DOTALL)
        if match is None:
            position = start + 1
            continue
        closing = bool(match.group(1))
        name = match.group(2).decode("ascii").lower()
        attributes = match.group("attrs")
        if closing:
            if attributes.strip() or not stack or stack[-1] != name:
                raise ValueError("unbalanced Vue markup")
            stack.pop()
            position = end
            continue

        self_closing = attributes.rstrip().endswith(b"/")
        if name == "script":
            close_start, close_end = _raw_element_close(source, end, "script")
            nested_start = _next_open_tag(source, end, "script")
            if nested_start >= 0 and nested_start < close_start:
                raise ValueError("nested script range")
            if not stack:
                language, setup = _vue_script_attributes(attributes)
                ranges.append(
                    VueScriptRange(
                        language=language,
                        setup=setup,
                        content_range=_source_range(line_starts, end, close_start),
                    )
                )
            position = close_end
            continue
        if name == "style" and not self_closing:
            _, close_end = _raw_element_close(source, end, "style")
            position = close_end
            continue
        if not self_closing and name not in _VOID_HTML_TAGS:
            stack.append(name)
        position = end

    if stack:
        raise ValueError("unclosed Vue markup")
    return tuple(ranges)


def extract_frontend_facts(file_path: str, source: bytes) -> FrontendFactSet:
    if not isinstance(file_path, str):
        raise TypeError("file_path must be a string")
    if not isinstance(source, bytes):
        raise TypeError("source must be bytes")

    normalized_path = _normalized_file_path(file_path)
    script_ranges: tuple[VueScriptRange, ...] = ()
    parse_inputs: list[tuple[bytes, int, str]] = []
    if normalized_path.endswith(".vue"):
        try:
            script_ranges = lex_vue_script_ranges(source)
        except ValueError:
            return FrontendFactSet(
                persistent_facts_allowed=False,
                imports=(),
                routes=(),
                script_ranges=(),
                diagnostics=(FactDiagnostic("vue_range_error"),),
            )
        for item in script_ranges:
            start = item.content_range.start_byte
            end = item.content_range.end_byte
            parse_inputs.append((source[start:end], start, item.language))
    else:
        parse_inputs.append((source, 0, _language_for_path(normalized_path)))

    units: list[_ParsedUnit] = []
    diagnostics: list[FactDiagnostic] = []
    relevant_errors = 0
    for unit_source, base_offset, language in parse_inputs:
        tree = _parse_frontend(unit_source, normalized_path, language)
        unit = _ParsedUnit(unit_source, base_offset, tree.root_node)
        units.append(unit)
        errors = tuple(_syntax_errors(tree.root_node))
        if not errors:
            continue
        relevant = sum(
            1 for node in errors if _is_relevant_error(node, unit_source)
        )
        relevant_errors += relevant
        unrelated = len(errors) - relevant
        if unrelated:
            _add_diagnostic(diagnostics, "unrelated_parse_error", unrelated)

    if relevant_errors:
        _add_diagnostic(diagnostics, "relevant_parse_error", relevant_errors)
        return FrontendFactSet(
            persistent_facts_allowed=False,
            imports=(),
            routes=(),
            script_ranges=script_ranges,
            diagnostics=tuple(diagnostics),
        )

    line_starts = _line_starts(source)
    imports: list[FrontendImportFact] = []
    routes: list[FrontendRouteFact] = []
    for unit in units:
        unit_imports, bindings = _extract_imports(
            normalized_path,
            source,
            line_starts,
            unit,
        )
        imports.extend(unit_imports)
        routes.extend(
            _extract_routes(
                normalized_path,
                source,
                line_starts,
                unit,
                bindings,
            )
        )

    imports.sort(key=lambda item: item.source_range.start_byte)
    if len(imports) > MAX_FRONTEND_IMPORTS_PER_FILE:
        omitted = len(imports) - MAX_FRONTEND_IMPORTS_PER_FILE
        imports = imports[:MAX_FRONTEND_IMPORTS_PER_FILE]
        _add_diagnostic(diagnostics, "imports_omitted", omitted)

    routes.sort(key=lambda item: (item.source_range.start_byte, item.path))
    deduplicated: list[FrontendRouteFact] = []
    seen_routes: set[tuple[int, str, str, str]] = set()
    for route in routes:
        key = (
            route.source_range.start_byte,
            route.framework,
            route.path,
            route.component.specifier,
        )
        if key not in seen_routes:
            seen_routes.add(key)
            deduplicated.append(route)
    routes = deduplicated
    if len(routes) > MAX_ROUTES_PER_ROUTER_FILE:
        omitted = len(routes) - MAX_ROUTES_PER_ROUTER_FILE
        routes = routes[:MAX_ROUTES_PER_ROUTER_FILE]
        _add_diagnostic(diagnostics, "routes_omitted", omitted)

    return FrontendFactSet(
        persistent_facts_allowed=True,
        imports=tuple(imports),
        routes=tuple(routes),
        script_ranges=script_ranges,
        diagnostics=tuple(diagnostics),
    )


def _extract_imports(
    file_path: str,
    full_source: bytes,
    line_starts: tuple[int, ...],
    unit: _ParsedUnit,
) -> tuple[list[FrontendImportFact], dict[str, _BindingTarget]]:
    facts: list[FrontendImportFact] = []
    targets: dict[str, list[_BindingTarget]] = {}
    for node in unit.root.named_children:
        if node.type not in {"import_statement", "export_statement"}:
            continue
        source_node = node.child_by_field_name("source")
        if source_node is None:
            continue
        specifier = _literal_string(source_node, unit.source)
        if specifier is None:
            continue
        kind = "import" if node.type == "import_statement" else "reexport"
        bindings = _import_bindings(node, unit.source, kind)
        selector = _module_selector(
            file_path,
            specifier,
            "static_import" if kind == "import" else "reexport",
        )
        facts.append(
            FrontendImportFact(
                kind=kind,
                specifier=specifier,
                selector=selector,
                bindings=bindings,
                source_range=_node_range(
                    line_starts,
                    node,
                    unit.base_offset,
                ),
            )
        )
        if kind != "import":
            continue
        for binding in bindings:
            if binding.is_type_only or not binding.local_name:
                continue
            targets.setdefault(binding.local_name, []).append(
                _BindingTarget(
                    module=specifier,
                    imported_name=binding.imported_name,
                    selector=selector,
                )
            )

    unambiguous = {
        name: values[0]
        for name, values in targets.items()
        if len(values) == 1
    }
    return facts, unambiguous


def _import_bindings(
    statement: Any,
    source: bytes,
    kind: str,
) -> tuple[ImportBinding, ...]:
    statement_text = _node_bytes(statement, source).lstrip()
    statement_type_only = bool(re.match(rb"import\s+type\b", statement_text))
    bindings: list[ImportBinding] = []
    if kind == "import":
        clause = next(
            (child for child in statement.named_children if child.type == "import_clause"),
            None,
        )
        if clause is None:
            return ()
        for child in clause.named_children:
            if child.type == "identifier":
                name = _node_text(child, source)
                bindings.append(
                    ImportBinding(name, "default", "default", statement_type_only)
                )
            elif child.type == "namespace_import":
                identifier = next(
                    (item for item in child.named_children if item.type == "identifier"),
                    None,
                )
                if identifier is not None:
                    name = _node_text(identifier, source)
                    bindings.append(
                        ImportBinding(name, "*", "namespace", statement_type_only)
                    )
            elif child.type == "named_imports":
                for specifier in child.named_children:
                    if specifier.type != "import_specifier":
                        continue
                    imported = specifier.child_by_field_name("name")
                    alias = specifier.child_by_field_name("alias")
                    if imported is None:
                        continue
                    imported_name = _node_text(imported, source)
                    local_name = _node_text(alias or imported, source)
                    type_only = statement_type_only or _node_bytes(
                        specifier, source
                    ).lstrip().startswith(b"type ")
                    bindings.append(
                        ImportBinding(
                            local_name,
                            imported_name,
                            "named",
                            type_only,
                        )
                    )
    else:
        for specifier in _descendants(statement, {"export_specifier"}):
            imported = specifier.child_by_field_name("name")
            alias = specifier.child_by_field_name("alias")
            if imported is None:
                continue
            imported_name = _node_text(imported, source)
            local_name = _node_text(alias or imported, source)
            bindings.append(
                ImportBinding(
                    local_name,
                    imported_name,
                    "named",
                    _node_bytes(specifier, source).lstrip().startswith(b"type "),
                )
            )
    return tuple(bindings)


def _extract_routes(
    file_path: str,
    full_source: bytes,
    line_starts: tuple[int, ...],
    unit: _ParsedUnit,
    bindings: dict[str, _BindingTarget],
) -> list[FrontendRouteFact]:
    declarations = _declarations_by_scope(unit.root, unit.source)
    const_arrays = _const_arrays(unit.root, unit.source)
    mutated = _mutated_identifiers(unit.root, unit.source)
    routes: list[FrontendRouteFact] = []

    vue_apis = {
        name
        for name, target in bindings.items()
        if target.module == "vue-router" and target.imported_name == "createRouter"
    }
    react_apis = {
        name
        for name, target in bindings.items()
        if target.module == "react-router-dom"
        and target.imported_name in {"createBrowserRouter", "useRoutes"}
    }
    route_components = {
        name
        for name, target in bindings.items()
        if target.module == "react-router-dom" and target.imported_name == "Route"
    }

    for call in _descendants(unit.root, {"call_expression"}):
        function = call.child_by_field_name("function")
        if function is None or function.type != "identifier":
            continue
        name = _node_text(function, unit.source)
        if _is_shadowed(name, function, declarations):
            continue
        arguments = call.child_by_field_name("arguments")
        if arguments is None:
            continue
        values = list(arguments.named_children)
        if name in vue_apis:
            if len(values) != 1 or values[0].type != "object":
                continue
            properties = _object_properties(values[0], unit.source)
            if properties is None or "routes" not in properties:
                continue
            array = _resolve_array(
                properties["routes"],
                call,
                const_arrays,
                mutated,
                unit.source,
            )
            if array is None:
                continue
            extracted = _object_route_array(
                "vue",
                array,
                "",
                file_path,
                line_starts,
                unit,
                bindings,
                declarations,
            )
            if extracted is not None:
                routes.extend(extracted)
        elif name in react_apis:
            if len(values) != 1:
                continue
            array = _resolve_array(
                values[0],
                call,
                const_arrays,
                mutated,
                unit.source,
            )
            if array is None:
                continue
            extracted = _object_route_array(
                "react",
                array,
                "",
                file_path,
                line_starts,
                unit,
                bindings,
                declarations,
            )
            if extracted is not None:
                routes.extend(extracted)

    for node in _descendants(
        unit.root,
        {"jsx_element", "jsx_self_closing_element"},
    ):
        if not _is_framework_route_jsx(
            node,
            route_components,
            declarations,
            unit.source,
        ):
            continue
        if _has_framework_route_jsx_ancestor(
            node,
            route_components,
            declarations,
            unit.source,
        ):
            continue
        extracted = _jsx_route(
            node,
            "",
            file_path,
            line_starts,
            unit,
            bindings,
            declarations,
            route_components,
        )
        if extracted is not None:
            routes.extend(extracted)
    return routes


def _object_route_array(
    framework: str,
    array: Any,
    parent_path: str,
    file_path: str,
    line_starts: tuple[int, ...],
    unit: _ParsedUnit,
    bindings: dict[str, _BindingTarget],
    declarations: dict[tuple[str, int, int], set[str]],
) -> list[FrontendRouteFact] | None:
    if array.type != "array" or _contains_type(array, "spread_element"):
        return None
    output: list[FrontendRouteFact] = []
    for child in array.named_children:
        if child.type != "object":
            return None
        properties = _object_properties(child, unit.source)
        if properties is None:
            return None
        path_node = properties.get("path")
        if path_node is None:
            return None
        raw_path = _literal_string(path_node, unit.source)
        if raw_path is None:
            return None
        path = _compose_route_path(parent_path, raw_path)
        if path is None:
            return None

        selector = _object_component_selector(
            framework,
            properties,
            file_path,
            unit,
            bindings,
            declarations,
        )
        if selector is not None:
            output.append(
                FrontendRouteFact(
                    framework=framework,
                    path=path,
                    component=selector,
                    source_range=_node_range(
                        line_starts,
                        child,
                        unit.base_offset,
                    ),
                )
            )
        children = properties.get("children")
        if children is not None:
            nested = _object_route_array(
                framework,
                _unwrap_parentheses(children),
                path,
                file_path,
                line_starts,
                unit,
                bindings,
                declarations,
            )
            if nested is None:
                return None
            output.extend(nested)
    return output


def _object_component_selector(
    framework: str,
    properties: dict[str, Any],
    file_path: str,
    unit: _ParsedUnit,
    bindings: dict[str, _BindingTarget],
    declarations: dict[tuple[str, int, int], set[str]],
) -> ModuleSelector | None:
    if framework == "vue":
        value = properties.get("component")
        if value is None:
            return None
        return _component_value_selector(
            value,
            file_path,
            unit,
            bindings,
            declarations,
            dynamic=True,
        )

    component = properties.get("Component")
    if component is not None:
        selector = _component_value_selector(
            component,
            file_path,
            unit,
            bindings,
            declarations,
            dynamic=False,
        )
        if selector is not None:
            return selector
    element = properties.get("element")
    if element is not None:
        name_node = _jsx_component_name(_unwrap_parentheses(element))
        if name_node is not None:
            return _imported_component_selector(
                name_node,
                unit,
                bindings,
                declarations,
            )
    lazy = properties.get("lazy")
    if lazy is not None:
        return _dynamic_selector(lazy, file_path, unit.source)
    return None


def _component_value_selector(
    value: Any,
    file_path: str,
    unit: _ParsedUnit,
    bindings: dict[str, _BindingTarget],
    declarations: dict[tuple[str, int, int], set[str]],
    *,
    dynamic: bool,
) -> ModuleSelector | None:
    value = _unwrap_parentheses(value)
    if value.type == "identifier":
        return _imported_component_selector(
            value,
            unit,
            bindings,
            declarations,
        )
    if dynamic:
        return _dynamic_selector(value, file_path, unit.source)
    return None


def _imported_component_selector(
    identifier: Any,
    unit: _ParsedUnit,
    bindings: dict[str, _BindingTarget],
    declarations: dict[tuple[str, int, int], set[str]],
) -> ModuleSelector | None:
    if identifier.type != "identifier":
        return None
    name = _node_text(identifier, unit.source)
    target = bindings.get(name)
    if target is None or _is_shadowed(name, identifier, declarations):
        return None
    return target.selector


def _dynamic_selector(
    value: Any,
    file_path: str,
    source: bytes,
) -> ModuleSelector | None:
    value = _unwrap_parentheses(value)
    if value.type != "arrow_function":
        return None
    body = value.child_by_field_name("body")
    if body is None:
        return None
    body = _unwrap_parentheses(body)
    if body.type != "call_expression":
        return None
    function = body.child_by_field_name("function")
    arguments = body.child_by_field_name("arguments")
    if function is None or function.type != "import" or arguments is None:
        return None
    values = list(arguments.named_children)
    if len(values) != 1:
        return None
    specifier = _literal_string(values[0], source)
    if specifier is None:
        return None
    return _module_selector(
        file_path,
        specifier,
        "route_dynamic_import",
    )


def _jsx_route(
    node: Any,
    parent_path: str,
    file_path: str,
    line_starts: tuple[int, ...],
    unit: _ParsedUnit,
    bindings: dict[str, _BindingTarget],
    declarations: dict[tuple[str, int, int], set[str]],
    route_components: set[str],
) -> list[FrontendRouteFact] | None:
    attributes = _jsx_attributes(node, unit.source)
    if attributes is None or "path" not in attributes:
        return None
    raw_path = _literal_string(attributes["path"], unit.source)
    if raw_path is None:
        return None
    path = _compose_route_path(parent_path, raw_path)
    if path is None:
        return None

    selector: ModuleSelector | None = None
    component = attributes.get("Component")
    if component is not None:
        value = _jsx_expression_value(component)
        if value is not None:
            selector = _imported_component_selector(
                value,
                unit,
                bindings,
                declarations,
            )
    if selector is None and "element" in attributes:
        value = _jsx_expression_value(attributes["element"])
        name_node = _jsx_component_name(value) if value is not None else None
        if name_node is not None:
            selector = _imported_component_selector(
                name_node,
                unit,
                bindings,
                declarations,
            )
    if selector is None and "lazy" in attributes:
        value = _jsx_expression_value(attributes["lazy"])
        if value is not None:
            selector = _dynamic_selector(value, file_path, unit.source)

    output: list[FrontendRouteFact] = []
    if selector is not None:
        output.append(
            FrontendRouteFact(
                framework="react",
                path=path,
                component=selector,
                source_range=_node_range(
                    line_starts,
                    node,
                    unit.base_offset,
                ),
            )
        )
    if node.type == "jsx_element":
        for child in node.named_children:
            if child.type not in {"jsx_element", "jsx_self_closing_element"}:
                continue
            if not _is_framework_route_jsx(
                child,
                route_components,
                declarations,
                unit.source,
            ):
                continue
            nested = _jsx_route(
                child,
                path,
                file_path,
                line_starts,
                unit,
                bindings,
                declarations,
                route_components,
            )
            if nested is None:
                return None
            output.extend(nested)
    return output


def _is_framework_route_jsx(
    node: Any,
    route_components: set[str],
    declarations: dict[tuple[str, int, int], set[str]],
    source: bytes,
) -> bool:
    name_node = _jsx_tag_name(node)
    if name_node is None or name_node.type != "identifier":
        return False
    name = _node_text(name_node, source)
    return name in route_components and not _is_shadowed(
        name,
        name_node,
        declarations,
    )


def _has_framework_route_jsx_ancestor(
    node: Any,
    route_components: set[str],
    declarations: dict[tuple[str, int, int], set[str]],
    source: bytes,
) -> bool:
    parent = node.parent
    while parent is not None:
        if parent.type == "jsx_element" and _is_framework_route_jsx(
            parent,
            route_components,
            declarations,
            source,
        ):
            return True
        parent = parent.parent
    return False


def _jsx_tag_name(node: Any) -> Any | None:
    if node.type == "jsx_self_closing_element":
        return node.child_by_field_name("name")
    if node.type == "jsx_element":
        opening = node.child_by_field_name("open_tag")
        return opening.child_by_field_name("name") if opening is not None else None
    return None


def _jsx_attributes(node: Any, source: bytes) -> dict[str, Any] | None:
    owner = node
    if node.type == "jsx_element":
        owner = node.child_by_field_name("open_tag")
    if owner is None:
        return None
    output: dict[str, Any] = {}
    for child in owner.named_children:
        if child.type == "jsx_expression" and _node_bytes(child, source).lstrip().startswith(b"{..."):
            return None
        if child.type != "jsx_attribute":
            continue
        named = list(child.named_children)
        if not named or named[0].type != "property_identifier":
            return None
        name = _node_text(named[0], source)
        if name in output or len(named) != 2:
            return None
        output[name] = named[1]
    return output


def _jsx_expression_value(node: Any) -> Any | None:
    if node.type != "jsx_expression":
        return None
    values = list(node.named_children)
    return values[0] if len(values) == 1 else None


def _jsx_component_name(node: Any | None) -> Any | None:
    if node is None:
        return None
    node = _unwrap_parentheses(node)
    if node.type == "jsx_self_closing_element":
        return node.child_by_field_name("name")
    if node.type == "jsx_element":
        opening = node.child_by_field_name("open_tag")
        return opening.child_by_field_name("name") if opening is not None else None
    return None


def _object_properties(node: Any, source: bytes) -> dict[str, Any] | None:
    output: dict[str, Any] = {}
    for child in node.named_children:
        if child.type == "spread_element":
            return None
        if child.type == "shorthand_property_identifier":
            name = _node_text(child, source)
            if name in output:
                return None
            output[name] = child
            continue
        if child.type != "pair":
            return None
        key = child.child_by_field_name("key")
        value = child.child_by_field_name("value")
        if key is None or value is None:
            return None
        if key.type in {"property_identifier", "identifier"}:
            name = _node_text(key, source)
        elif key.type == "string":
            name = _literal_string(key, source)
            if name is None:
                return None
        else:
            return None
        if name in output:
            return None
        output[name] = value
    return output


def _const_arrays(root: Any, source: bytes) -> dict[str, _ConstArray | None]:
    output: dict[str, _ConstArray | None] = {}
    for declaration in _descendants(root, {"lexical_declaration"}):
        if not _node_bytes(declaration, source).lstrip().startswith(b"const"):
            continue
        for declarator in declaration.named_children:
            if declarator.type != "variable_declarator":
                continue
            name_node = declarator.child_by_field_name("name")
            value = declarator.child_by_field_name("value")
            if name_node is None or name_node.type != "identifier" or value is None:
                continue
            name = _node_text(name_node, source)
            value = _unwrap_parentheses(value)
            candidate = (
                _ConstArray(value, _scope_key(_nearest_scope(declarator.parent)))
                if value.type == "array"
                else None
            )
            if name in output:
                output[name] = None
            else:
                output[name] = candidate
    return output


def _resolve_array(
    node: Any,
    usage: Any,
    const_arrays: dict[str, _ConstArray | None],
    mutated: set[str],
    source: bytes,
) -> Any | None:
    node = _unwrap_parentheses(node)
    if node.type == "array":
        return node
    if node.type not in {"identifier", "shorthand_property_identifier"}:
        return None
    name = _node_text(node, source)
    candidate = const_arrays.get(name)
    if candidate is None or name in mutated:
        return None
    if candidate.scope_key not in _ancestor_scope_keys(usage):
        return None
    return candidate.node


def _mutated_identifiers(root: Any, source: bytes) -> set[str]:
    output: set[str] = set()
    for node in _walk(root):
        if node.type == "call_expression":
            function = node.child_by_field_name("function")
            if function is not None and function.type == "member_expression":
                owner = function.child_by_field_name("object")
                if owner is not None and owner.type == "identifier":
                    output.add(_node_text(owner, source))
        elif node.type in {
            "assignment_expression",
            "augmented_assignment_expression",
            "update_expression",
        }:
            left = node.child_by_field_name("left") or node.child_by_field_name("argument")
            identifier = _leftmost_identifier(left)
            if identifier is not None:
                output.add(_node_text(identifier, source))
    return output


def _leftmost_identifier(node: Any | None) -> Any | None:
    if node is None:
        return None
    if node.type == "identifier":
        return node
    for child in node.named_children:
        result = _leftmost_identifier(child)
        if result is not None:
            return result
    return None


def _declarations_by_scope(
    root: Any,
    source: bytes,
) -> dict[tuple[str, int, int], set[str]]:
    output: dict[tuple[str, int, int], set[str]] = {}

    def declare(scope: Any | None, name_node: Any | None) -> None:
        if scope is None or name_node is None:
            return
        for identifier in _pattern_identifiers(name_node):
            output.setdefault(_scope_key(scope), set()).add(
                _node_text(identifier, source)
            )

    for node in _walk(root):
        if node.type == "variable_declarator":
            declare(_nearest_scope(node.parent), node.child_by_field_name("name"))
        elif node.type in {
            "function_declaration",
            "generator_function_declaration",
            "class_declaration",
        }:
            declare(_nearest_scope(node.parent), node.child_by_field_name("name"))
        if node.type in {
            "function_declaration",
            "function_expression",
            "generator_function_declaration",
            "generator_function",
            "arrow_function",
            "method_definition",
        }:
            declare(node, node.child_by_field_name("parameter"))
            declare(node, node.child_by_field_name("parameters"))
        elif node.type == "catch_clause":
            declare(node, node.child_by_field_name("parameter"))
    return output


def _pattern_identifiers(node: Any) -> Iterator[Any]:
    if node.type in {"identifier", "shorthand_property_identifier_pattern"}:
        yield node
        return
    for child in node.named_children:
        yield from _pattern_identifiers(child)


def _is_shadowed(
    name: str,
    usage: Any,
    declarations: dict[tuple[str, int, int], set[str]],
) -> bool:
    return any(
        name in declarations.get(scope_key, set())
        for scope_key in _ancestor_scope_keys(usage)
    )


def _nearest_scope(node: Any | None) -> Any | None:
    while node is not None:
        if node.type in _SCOPE_TYPES:
            return node
        node = node.parent
    return None


def _scope_key(node: Any | None) -> tuple[str, int, int]:
    if node is None:
        return ("", -1, -1)
    return (node.type, node.start_byte, node.end_byte)


def _ancestor_scope_keys(node: Any) -> set[tuple[str, int, int]]:
    output: set[tuple[str, int, int]] = set()
    while node is not None:
        if node.type in _SCOPE_TYPES:
            output.add(_scope_key(node))
        node = node.parent
    return output


def _module_selector(
    file_path: str,
    specifier: str,
    source_kind: str,
) -> ModuleSelector:
    if not specifier or "\\" in specifier or "?" in specifier or "#" in specifier:
        return ModuleSelector("unresolved", specifier, (), source_kind)
    if specifier.startswith("/"):
        return ModuleSelector("unresolved", specifier, (), source_kind)
    if specifier.startswith("@/"):
        parts = ["src"]
        tail = specifier[2:]
    elif specifier.startswith("."):
        parts = list(PurePosixPath(file_path).parent.parts)
        tail = specifier
    else:
        return ModuleSelector("external", specifier, (), source_kind)

    for part in tail.split("/"):
        if part in {"", "."}:
            continue
        if part == "..":
            if not parts:
                return ModuleSelector("escape", specifier, (), source_kind)
            parts.pop()
        else:
            parts.append(part)
    if not parts:
        return ModuleSelector("escape", specifier, (), source_kind)
    base = PurePosixPath(*parts).as_posix()
    if base.endswith(_EXPLICIT_SUFFIXES):
        return ModuleSelector("exact", specifier, (base,), source_kind)
    candidates = [base]
    candidates.extend(base + suffix for suffix in _CANDIDATE_SUFFIXES)
    candidates.extend(f"{base}/{name}" for name in _INDEX_CANDIDATES)
    return ModuleSelector("candidates", specifier, tuple(candidates), source_kind)


def _compose_route_path(parent: str, raw: str) -> str | None:
    if any(part in {".", ".."} for part in raw.split("/")):
        return None
    if raw.startswith("/"):
        return raw or "/"
    if parent:
        return parent if not raw else parent.rstrip("/") + "/" + raw
    return "/" if not raw else "/" + raw


def _literal_string(node: Any, source: bytes) -> str | None:
    node = _unwrap_parentheses(node)
    if node.type != "string":
        return None
    raw = _node_bytes(node, source)
    if len(raw) < 2 or raw[:1] not in {b"'", b'"'} or raw[-1:] != raw[:1]:
        return None
    content = raw[1:-1]
    if b"\\" in content or b"\n" in content or b"\r" in content:
        return None
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _unwrap_parentheses(node: Any) -> Any:
    while node.type in {"parenthesized_expression", "as_expression", "satisfies_expression"}:
        children = list(node.named_children)
        if len(children) != 1:
            break
        node = children[0]
    return node


def _parse_frontend(source: bytes, file_path: str, language: str) -> Any:
    if file_path.endswith(".tsx"):
        return parse_tsx(source)
    if file_path.endswith(".jsx"):
        return parse_jsx(source)
    if language == "typescript":
        return parse_typescript(source)
    return parse_javascript(source)


def _language_for_path(file_path: str) -> str:
    return "typescript" if file_path.endswith((".ts", ".tsx")) else "javascript"


def _syntax_errors(root: Any) -> Iterator[Any]:
    for node in _walk(root):
        if node.type == "ERROR" or node.is_missing:
            yield node


def _is_relevant_error(node: Any, source: bytes) -> bool:
    current = node
    while current is not None and current.type != "program":
        if current.type in {
            "import_statement",
            "export_statement",
            "call_expression",
            "object",
            "array",
            "jsx_element",
            "jsx_self_closing_element",
        } and _RELEVANT_ERROR_RE.search(_node_bytes(current, source)):
            return True
        current = current.parent
    return bool(_RELEVANT_ERROR_RE.search(_node_bytes(node, source)))


def _contains_type(node: Any, node_type: str) -> bool:
    return any(child.type == node_type for child in _walk(node))


def _walk(root: Any) -> Iterator[Any]:
    stack = [root]
    while stack:
        node = stack.pop()
        yield node
        stack.extend(reversed(node.named_children))


def _descendants(root: Any, types: set[str]) -> Iterator[Any]:
    for node in _walk(root):
        if node is not root and node.type in types:
            yield node


def _node_bytes(node: Any, source: bytes) -> bytes:
    return source[node.start_byte : node.end_byte]


def _node_text(node: Any, source: bytes) -> str:
    return _node_bytes(node, source).decode("utf-8", errors="strict")


def _normalized_file_path(file_path: str) -> str:
    if not file_path or "\\" in file_path:
        raise ValueError("file_path must be a repository-relative POSIX path")
    path = PurePosixPath(file_path)
    if path.is_absolute() or ".." in path.parts or path.as_posix() != file_path:
        raise ValueError("file_path must be normalized and repository-relative")
    return file_path


def _vue_script_attributes(attributes: bytes) -> tuple[str, bool]:
    attributes = attributes.rstrip()
    if attributes.endswith(b"/"):
        raise ValueError("script ranges cannot be self-closing")
    setup = bool(re.search(rb"(?:^|\s)setup(?:\s|=|$)", attributes, re.IGNORECASE))
    lang_matches = list(
        re.finditer(
            rb"(?:^|\s)lang\s*=\s*(?:\"(?P<double>[^\"]*)\"|'(?P<single>[^']*)'|(?P<bare>[^\s>]+))",
            attributes,
            re.IGNORECASE,
        )
    )
    if len(lang_matches) > 1:
        raise ValueError("duplicate script language")
    if not lang_matches:
        return "javascript", setup
    match = lang_matches[0]
    value = match.group("double") or match.group("single") or match.group("bare") or b""
    language = value.decode("ascii", errors="strict").lower()
    if language in {"ts", "typescript"}:
        return "typescript", setup
    if language in {"js", "javascript"}:
        return "javascript", setup
    raise ValueError("unsupported Vue script language")


def _raw_element_close(
    source: bytes,
    position: int,
    name: str,
) -> tuple[int, int]:
    pattern = re.compile(rb"</\s*" + name.encode("ascii") + rb"\s*>", re.IGNORECASE)
    match = pattern.search(source, position)
    if match is None:
        raise ValueError(f"unclosed {name} element")
    return match.start(), match.end()


def _next_open_tag(source: bytes, position: int, name: str) -> int:
    pattern = re.compile(
        rb"<\s*" + name.encode("ascii") + rb"(?:\s|>|/)",
        re.IGNORECASE,
    )
    match = pattern.search(source, position)
    return match.start() if match is not None else -1


def _closed_section(source: bytes, start: int, closing: bytes) -> int:
    end = source.find(closing, start)
    if end < 0:
        raise ValueError("unclosed Vue markup section")
    return end + len(closing)


def _markup_tag_end(source: bytes, start: int) -> int:
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
    raise ValueError("unclosed Vue tag")


def _line_starts(source: bytes) -> tuple[int, ...]:
    return (0,) + tuple(
        position + 1 for position, value in enumerate(source) if value == ord("\n")
    )


def _node_range(
    line_starts: tuple[int, ...],
    node: Any,
    base_offset: int,
) -> SourceRange:
    return _source_range(
        line_starts,
        base_offset + node.start_byte,
        base_offset + node.end_byte,
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


def _frontend_route_signal(
    context: PluginContext,
    route: FrontendRouteFact,
    chunk: DocumentChunk,
) -> CodeSignal:
    qualified_name = f"{context.file_path.as_posix()}#{route.framework}:{route.path}"
    source_range = route.source_range
    signal_id = generate_v5_signal_id(
        file_path=context.file_path.as_posix(),
        kind="route",
        qualified_name=qualified_name,
        signature="",
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
        kind="route",
        name=route.path,
        start_line=source_range.start_line,
        end_line=source_range.end_line,
        language=context.language,
        tokens=[],
        metadata={
            "framework": route.framework,
            "path": route.path,
            "component_specifier": route.component.specifier,
        },
        qualified_name=qualified_name,
        project_unit_key=context.project_unit_key,
        producer=_GRAPH_PRODUCER,
        start_column=source_range.start_column,
        end_column=source_range.end_column,
        recallable=False,
    )


def _frontend_relation(
    *,
    context: PluginContext,
    source: CodeSignal,
    kind: str,
    selector: ModuleSelector,
    source_range: SourceRange,
    target_name: str,
    extra_metadata: dict[str, object],
) -> CodeRelation:
    active_candidates = tuple(
        candidate
        for candidate in selector.candidates
        if context.contains_path(candidate)
    )
    target_project_unit_key = context.project_unit_key
    if selector.state == "exact" and selector.candidates:
        target_project_unit_key = context.project_unit_for_path(
            selector.candidates[0]
        )
    elif selector.state == "candidates":
        active_candidates = tuple(
            candidate
            for candidate in active_candidates
            if context.project_unit_for_path(candidate) == context.project_unit_key
        )

    target_qualified_name = (
        selector.candidates[0] if selector.candidates else selector.specifier
    )
    relation_id = generate_v5_relation_id(
        source_signal_id=source.signal_id,
        kind=kind,
        target_kind="module",
        target_qualified_name=target_qualified_name,
        target_signature="",
        target_arity=None,
        target_project_unit_key=target_project_unit_key,
        producer=_GRAPH_PRODUCER,
    )
    metadata = {
        **extra_metadata,
        "selector_state": selector.state,
        "specifier": selector.specifier,
        "source_kind": selector.source_kind,
        "candidates": active_candidates,
        "first_source_line": source_range.start_line,
        "first_source_column": source_range.start_column,
        "occurrence_count": 1,
    }
    return CodeRelation(
        relation_id=relation_id,
        source_signal_id=source.signal_id,
        target_name=target_name,
        kind=kind,
        confidence=1.0,
        metadata=metadata,
        target_kind="module",
        target_qualified_name=target_qualified_name,
        target_project_unit_key=target_project_unit_key,
        resolution="unresolved",
        producer=_GRAPH_PRODUCER,
        producer_confidence=1.0,
    )


def _merge_frontend_relation(
    relations: dict[str, CodeRelation], relation: CodeRelation
) -> None:
    existing = relations.get(relation.relation_id)
    if existing is None:
        relations[relation.relation_id] = relation
        return
    existing_position = (
        int(existing.metadata.get("first_source_line", 0)),
        int(existing.metadata.get("first_source_column", 0)),
    )
    next_position = (
        int(relation.metadata.get("first_source_line", 0)),
        int(relation.metadata.get("first_source_column", 0)),
    )
    selected = (
        relation.metadata if next_position < existing_position else existing.metadata
    )
    metadata = dict(selected)
    metadata["occurrence_count"] = int(
        existing.metadata.get("occurrence_count", 1)
    ) + int(relation.metadata.get("occurrence_count", 1))
    relations[relation.relation_id] = replace(existing, metadata=metadata)


def _graph_containing_chunk(
    chunks: tuple[DocumentChunk, ...], line: int
) -> DocumentChunk | None:
    return next(
        (chunk for chunk in chunks if chunk.start_line <= line <= chunk.end_line),
        None,
    )


def _add_graph_tokens(tokens: list[str], value: str) -> None:
    for match in _GRAPH_TOKEN_RE.finditer(value):
        token = match.group(0).lower()
        if token not in tokens:
            tokens.append(token)
