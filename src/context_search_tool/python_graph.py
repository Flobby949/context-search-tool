"""P8 Python static structure producer: AST facts (Task 1 seam).

Pure standard-library AST extraction. Parsing never executes project code:
``ast.PyCF_ONLY_AST`` compiles source text to a tree without importing,
evaluating decorators, defaults, or annotations. Facts are frozen value
objects; no AST node survives ``extract_python_facts``.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass

MAX_PYTHON_DECLARATION_FACTS = 4095

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
