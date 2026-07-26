"""P8 Python static structure producer: AST facts (Task 1 seam).

Pure standard-library AST extraction. Parsing never executes project code:
``ast.PyCF_ONLY_AST`` compiles source text to a tree without importing,
evaluating decorators, defaults, or annotations. Facts are frozen value
objects; no AST node survives ``extract_python_facts``.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, replace
from pathlib import Path

from context_search_tool.graph_contract import (
    MAX_PYTHON_IMPORTS_PER_FILE,
    generate_v5_relation_id,
    generate_v5_signal_id,
)
from context_search_tool.graph_plugins import (
    MaterializedGraph,
    ParsedGraphFacts,
    PluginContext,
)
from context_search_tool.models import (
    CodeRelation,
    CodeSignal,
    DocumentChunk,
    SymbolRef,
)

MAX_PYTHON_DECLARATION_FACTS = 4095

_GRAPH_PRODUCER = "python_ast"
_PYTHON_SUFFIXES = (".py", ".pyw")
_SIGNAL_KIND_BY_DECLARATION = {
    "class": "type",
    "function": "function",
    "method": "method",
}

_PARSE_FAILURES: tuple[tuple[type[BaseException], str], ...] = (
    (SyntaxError, "syntax_error"),
    (UnicodeDecodeError, "encoding_error"),
    (RecursionError, "recursion_error"),
    (ValueError, "value_error"),
    (TypeError, "type_error"),
)


@dataclass(frozen=True)
class PythonSourceRange:
    start_line: int
    start_col: int
    end_line: int
    end_col: int


@dataclass(frozen=True)
class PythonDeclarationFact:
    kind: str  # "class" | "function" | "method"
    name: str
    owner_qualified_name: str  # "" for module level
    is_async: bool
    range: PythonSourceRange


@dataclass(frozen=True)
class PythonImportFact:
    import_form: str  # "import" | "from"
    module: str  # dependency module as written; "" for bare star package
    relative_level: int
    is_star: bool
    range: PythonSourceRange


@dataclass(frozen=True)
class PythonFactDiagnostic:
    code: str
    count: int


@dataclass(frozen=True)
class PythonFactSet:
    file_path: str
    parse_status: str
    declarations: tuple[PythonDeclarationFact, ...]
    imports: tuple[PythonImportFact, ...]
    diagnostics: tuple[PythonFactDiagnostic, ...]
    omitted_declaration_count: int


def _range(node: ast.AST) -> PythonSourceRange:
    return PythonSourceRange(
        start_line=node.lineno,
        start_col=node.col_offset,
        end_line=getattr(node, "end_lineno", node.lineno),
        end_col=getattr(node, "end_col_offset", node.col_offset),
    )


def _declaration_range(
    node: ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef,
) -> PythonSourceRange:
    start = node
    for decorator in node.decorator_list:
        if (decorator.lineno, decorator.col_offset) < (
            start.lineno,
            start.col_offset,
        ):
            start = decorator
    return PythonSourceRange(
        start_line=start.lineno,
        start_col=start.col_offset,
        end_line=node.end_lineno if node.end_lineno is not None else node.lineno,
        end_col=(
            node.end_col_offset
            if node.end_col_offset is not None
            else node.col_offset
        ),
    )


_FUNCTION_SCOPES = (
    ast.FunctionDef,
    ast.AsyncFunctionDef,
    ast.Lambda,
    ast.ListComp,
    ast.SetComp,
    ast.DictComp,
    ast.GeneratorExp,
)


def _collect_declarations(
    node: ast.AST,
    owner: str,
    owner_is_class: bool,
    out: list[PythonDeclarationFact],
) -> None:
    for child in ast.iter_child_nodes(node):
        if isinstance(child, ast.ClassDef):
            out.append(
                PythonDeclarationFact(
                    kind="class",
                    name=child.name,
                    owner_qualified_name=owner,
                    is_async=False,
                    range=_declaration_range(child),
                )
            )
            child_owner = f"{owner}.{child.name}" if owner else child.name
            _collect_declarations(child, child_owner, True, out)
        elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out.append(
                PythonDeclarationFact(
                    kind="method" if owner_is_class else "function",
                    name=child.name,
                    owner_qualified_name=owner,
                    is_async=isinstance(child, ast.AsyncFunctionDef),
                    range=_declaration_range(child),
                )
            )
            # Never descend into a function scope for declarations.
        elif isinstance(child, _FUNCTION_SCOPES):
            continue
        else:
            # Cross module/class control flow (if/try/with/for/while/match)
            # without changing the ownership scope.
            _collect_declarations(child, owner, owner_is_class, out)


def _collect_imports(tree: ast.AST, out: list[PythonImportFact]) -> None:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            location = _range(node)
            for alias in node.names:
                out.append(
                    PythonImportFact(
                        import_form="import",
                        module=alias.name,
                        relative_level=0,
                        is_star=False,
                        range=location,
                    )
                )
        elif isinstance(node, ast.ImportFrom):
            location = _range(node)
            level = node.level or 0
            if node.module is not None:
                is_star = any(alias.name == "*" for alias in node.names)
                out.append(
                    PythonImportFact(
                        import_form="from",
                        module=node.module,
                        relative_level=level,
                        is_star=is_star,
                        range=location,
                    )
                )
            else:
                for alias in node.names:
                    out.append(
                        PythonImportFact(
                            import_form="from",
                            module="" if alias.name == "*" else alias.name,
                            relative_level=level,
                            is_star=alias.name == "*",
                            range=location,
                        )
                    )


def _declaration_sort_key(
    fact: PythonDeclarationFact,
) -> tuple[int, int, int, int, str, str, str]:
    return (
        fact.range.start_line,
        fact.range.start_col,
        fact.range.end_line,
        fact.range.end_col,
        fact.kind,
        fact.owner_qualified_name,
        fact.name,
    )


def _import_sort_key(
    fact: PythonImportFact,
) -> tuple[int, int, int, int, str, int, str]:
    return (
        fact.range.start_line,
        fact.range.start_col,
        fact.range.end_line,
        fact.range.end_col,
        fact.import_form,
        fact.relative_level,
        fact.module,
    )


def extract_python_facts(file_path: str, content: bytes) -> PythonFactSet:
    try:
        tree = compile(
            content,
            file_path,
            "exec",
            flags=ast.PyCF_ONLY_AST | ast.PyCF_TYPE_COMMENTS,
            dont_inherit=True,
            optimize=0,
        )
    except tuple(item[0] for item in _PARSE_FAILURES) as error:
        code = next(
            code
            for failure_type, code in _PARSE_FAILURES
            if isinstance(error, failure_type)
        )
        return PythonFactSet(
            file_path=file_path,
            parse_status=code,
            declarations=(),
            imports=(),
            diagnostics=(PythonFactDiagnostic(code=code, count=1),),
            omitted_declaration_count=0,
        )

    declarations: list[PythonDeclarationFact] = []
    _collect_declarations(tree, "", False, declarations)
    declarations.sort(key=_declaration_sort_key)
    omitted = max(0, len(declarations) - MAX_PYTHON_DECLARATION_FACTS)
    declarations = declarations[:MAX_PYTHON_DECLARATION_FACTS]

    imports: list[PythonImportFact] = []
    _collect_imports(tree, imports)
    imports.sort(key=_import_sort_key)

    return PythonFactSet(
        file_path=file_path,
        parse_status="ok",
        declarations=tuple(declarations),
        imports=tuple(imports),
        diagnostics=(),
        omitted_declaration_count=omitted,
    )


def python_module_name(file_path: Path, project_unit_key: str) -> str:
    relative = file_path.as_posix()
    if project_unit_key:
        prefix = project_unit_key.rstrip("/") + "/"
        if relative.startswith(prefix):
            relative = relative[len(prefix):]
    for suffix in _PYTHON_SUFFIXES:
        if relative.endswith(suffix):
            relative = relative[: -len(suffix)]
            break
    segments = relative.split("/")
    if len(segments) > 1 and segments[-1] == "__init__":
        segments = segments[:-1]
    elif segments == ["__init__"]:
        # Project-unit-root __init__ keeps a stable declaration identity
        # without claiming a runtime package name.
        return "__init__"
    return ".".join(segments)


class PythonGraphProducer:
    name = "python_graph"

    def supports(self, context: PluginContext) -> bool:
        return context.file_path.suffix in _PYTHON_SUFFIXES

    def parse(self, context: PluginContext, content: bytes) -> ParsedGraphFacts:
        if not self.supports(context):
            raise ValueError("PythonGraphProducer received an unsupported source")
        facts = extract_python_facts(context.file_path.as_posix(), content)
        metadata: dict[str, object] = {
            "graph_parse_status": (
                "ast" if facts.parse_status == "ok" else facts.parse_status
            ),
            "graph_diagnostics": {
                item.code: item.count for item in facts.diagnostics
            },
        }
        if facts.omitted_declaration_count:
            metadata["graph_omitted_declarations"] = (
                facts.omitted_declaration_count
            )
        symbols = tuple(
            SymbolRef(
                name=fact.name,
                kind=fact.kind,
                start_line=fact.range.start_line,
                end_line=fact.range.end_line,
                language="python",
                metadata={
                    "qualified_name": _qualified_declaration_name(
                        context, fact
                    ),
                    "owner_qualified_name": fact.owner_qualified_name,
                    "is_async": fact.is_async,
                },
            )
            for fact in facts.declarations
        )
        # No separate producer lexical channel: declaration names are
        # already present in the source text and counted once by generic
        # chunk tokenization. The paired real A/B showed the extra channel
        # double-counts those names and reshuffles direct ranking
        # corpus-wide (RedInk required recall 1.0 -> 0.94) with zero
        # credited benefit.
        return ParsedGraphFacts(
            facts=facts,
            symbols=symbols,
            lexical_tokens=(),
            metadata=metadata,
            fallback_required=False,
        )

    def materialize(
        self,
        context: PluginContext,
        parsed: ParsedGraphFacts,
        chunks: tuple[DocumentChunk, ...],
        module_signal: CodeSignal,
    ) -> MaterializedGraph:
        facts = parsed.facts
        if not isinstance(facts, PythonFactSet) or facts.parse_status != "ok":
            return MaterializedGraph(metadata=parsed.metadata)
        if module_signal.file_path != context.file_path:
            raise ValueError("module signal does not belong to the plugin context")

        ordered_chunks = tuple(
            sorted(
                chunks,
                key=lambda item: (item.start_line, item.end_line, item.chunk_id),
            )
        )
        signals: list[CodeSignal] = []
        for fact in facts.declarations:
            chunk = next(
                (
                    candidate
                    for candidate in ordered_chunks
                    if candidate.start_line
                    <= fact.range.start_line
                    <= candidate.end_line
                ),
                None,
            )
            if chunk is None:
                metadata = dict(parsed.metadata)
                metadata["graph_materialize_status"] = "missing_chunk"
                return MaterializedGraph(metadata=metadata)
            signals.append(_declaration_signal(context, fact, chunk))
        signals.sort(
            key=lambda signal: (
                signal.start_line,
                signal.start_column,
                signal.end_line,
                signal.end_column,
                signal.signal_id,
            )
        )

        merged: dict[str, CodeRelation] = {}
        for fact in facts.imports:
            selector = python_module_selector(context, fact)
            _merge_python_relation(
                merged,
                _python_import_relation(context, module_signal, fact, selector),
            )
        relations = sorted(
            merged.values(),
            key=lambda relation: (
                int(relation.metadata.get("first_source_line", 0)),
                int(relation.metadata.get("first_source_column", 0)),
                relation.target_qualified_name,
                relation.relation_id,
            ),
        )
        metadata = dict(parsed.metadata)
        if len(relations) > MAX_PYTHON_IMPORTS_PER_FILE:
            metadata["graph_omitted_imports"] = (
                len(relations) - MAX_PYTHON_IMPORTS_PER_FILE
            )
            relations = relations[:MAX_PYTHON_IMPORTS_PER_FILE]
        return MaterializedGraph(
            signals=tuple(signals),
            relations=tuple(relations),
            metadata=metadata,
        )


def _qualified_declaration_name(
    context: PluginContext, fact: PythonDeclarationFact
) -> str:
    module = python_module_name(context.file_path, context.project_unit_key)
    owner = f".{fact.owner_qualified_name}" if fact.owner_qualified_name else ""
    return f"{module}{owner}.{fact.name}"


def _declaration_signal(
    context: PluginContext,
    fact: PythonDeclarationFact,
    chunk: DocumentChunk,
) -> CodeSignal:
    qualified_name = _qualified_declaration_name(context, fact)
    kind = _SIGNAL_KIND_BY_DECLARATION[fact.kind]
    signal_id = generate_v5_signal_id(
        file_path=context.file_path.as_posix(),
        kind=kind,
        qualified_name=qualified_name,
        signature="",
        start_line=fact.range.start_line,
        start_column=fact.range.start_col,
        end_line=fact.range.end_line,
        end_column=fact.range.end_col,
        producer=_GRAPH_PRODUCER,
    )
    return CodeSignal(
        signal_id=signal_id,
        chunk_id=chunk.chunk_id,
        file_path=context.file_path,
        kind=kind,
        name=fact.name,
        start_line=fact.range.start_line,
        end_line=fact.range.end_line,
        language="python",
        tokens=[],
        metadata={
            "owner_qualified_name": fact.owner_qualified_name,
            "is_async": fact.is_async,
        },
        qualified_name=qualified_name,
        signature="",
        arity=None,
        project_unit_key=context.project_unit_key,
        producer=_GRAPH_PRODUCER,
        start_column=fact.range.start_col,
        end_column=fact.range.end_col,
        recallable=True,
    )


@dataclass(frozen=True)
class PythonModuleSelector:
    state: str  # "exact" | "candidates" | "external" | "unresolved"
    specifier: str
    candidates: tuple[str, ...]


def _module_path_candidates(base: str, *, package_only: bool) -> tuple[str, ...]:
    if package_only:
        return (f"{base}/__init__.py", f"{base}/__init__.pyw")
    return (
        f"{base}.py",
        f"{base}.pyw",
        f"{base}/__init__.py",
        f"{base}/__init__.pyw",
    )


def _active_same_unit_candidates(
    context: PluginContext, candidates: tuple[str, ...]
) -> tuple[str, ...]:
    kept = {
        candidate
        for candidate in candidates
        if context.contains_path(candidate)
        and context.project_unit_for_path(candidate) == context.project_unit_key
    }
    return tuple(sorted(kept))


def python_module_selector(
    context: PluginContext, fact: PythonImportFact
) -> PythonModuleSelector:
    specifier = "." * fact.relative_level + fact.module
    unit = context.project_unit_key
    prefix = f"{unit}/" if unit else ""

    if fact.relative_level == 0:
        if not fact.module:
            return PythonModuleSelector("unresolved", specifier, ())
        relative = fact.module.replace(".", "/")
        raw = tuple(
            candidate
            for base in (f"{prefix}{relative}", f"{prefix}src/{relative}")
            for candidate in _module_path_candidates(base, package_only=False)
        )
        candidates = _active_same_unit_candidates(context, raw)
        if not candidates:
            return PythonModuleSelector("external", specifier, ())
        state = "exact" if len(candidates) == 1 else "candidates"
        return PythonModuleSelector(state, specifier, candidates)

    file_relative = context.file_path.as_posix()
    inner = (
        file_relative[len(prefix):]
        if prefix and file_relative.startswith(prefix)
        else file_relative
    )
    segments = inner.split("/")
    filename = segments[-1]
    stem = filename
    for suffix in _PYTHON_SUFFIXES:
        if stem.endswith(suffix):
            stem = stem[: -len(suffix)]
            break
    is_init = stem == "__init__"
    package = segments[:-1]
    remove = fact.relative_level - 1
    if remove > len(package):
        return PythonModuleSelector("unresolved", specifier, ())
    base_segments = package[: len(package) - remove] if remove else package

    if not base_segments:
        # Above the top package. The single closed exception: a
        # project-unit-root __init__.py may import an exact sibling.
        if is_init and not package and fact.relative_level == 1 and fact.module:
            sibling = fact.module.replace(".", "/")
            raw = _module_path_candidates(
                f"{prefix}{sibling}", package_only=False
            )
            candidates = _active_same_unit_candidates(context, raw)
            if len(candidates) == 1:
                return PythonModuleSelector("exact", specifier, candidates)
            if len(candidates) > 1:
                return PythonModuleSelector("candidates", specifier, candidates)
        return PythonModuleSelector("unresolved", specifier, ())

    if fact.module:
        target = "/".join(base_segments + fact.module.split("."))
        raw = _module_path_candidates(f"{prefix}{target}", package_only=False)
    else:
        target = "/".join(base_segments)
        raw = _module_path_candidates(f"{prefix}{target}", package_only=True)
    candidates = _active_same_unit_candidates(context, raw)
    if not candidates:
        return PythonModuleSelector("unresolved", specifier, ())
    state = "exact" if len(candidates) == 1 else "candidates"
    return PythonModuleSelector(state, specifier, candidates)


def _python_import_relation(
    context: PluginContext,
    module_signal: CodeSignal,
    fact: PythonImportFact,
    selector: PythonModuleSelector,
) -> CodeRelation:
    target_project_unit_key = context.project_unit_key
    if selector.state == "exact" and selector.candidates:
        target_project_unit_key = context.project_unit_for_path(
            selector.candidates[0]
        )
    target_qualified_name = (
        selector.candidates[0] if selector.candidates else selector.specifier
    )
    relation_id = generate_v5_relation_id(
        source_signal_id=module_signal.signal_id,
        kind="imports",
        target_kind="module",
        target_qualified_name=target_qualified_name,
        target_signature="",
        target_arity=None,
        target_project_unit_key=target_project_unit_key,
        producer=_GRAPH_PRODUCER,
    )
    return CodeRelation(
        relation_id=relation_id,
        source_signal_id=module_signal.signal_id,
        target_name=selector.specifier,
        kind="imports",
        confidence=1.0,
        metadata={
            "selector_state": selector.state,
            "specifier": selector.specifier,
            "candidates": selector.candidates,
            "import_form": fact.import_form,
            "relative_level": fact.relative_level,
            "first_source_line": fact.range.start_line,
            "first_source_column": fact.range.start_col,
            "occurrence_count": 1,
        },
        target_kind="module",
        target_qualified_name=target_qualified_name,
        target_project_unit_key=target_project_unit_key,
        resolution="unresolved",
        producer=_GRAPH_PRODUCER,
        producer_confidence=1.0,
    )


def _merge_python_relation(
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
        relation.metadata
        if next_position < existing_position
        else existing.metadata
    )
    metadata = dict(selected)
    metadata["occurrence_count"] = int(
        existing.metadata.get("occurrence_count", 1)
    ) + int(relation.metadata.get("occurrence_count", 1))
    relations[relation.relation_id] = replace(existing, metadata=metadata)
