from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
from typing import Any, Iterator

from context_search_tool.syntax_parsers import parse_java
from context_search_tool.tokenizer import tokenize_identifier


MAX_IMPORTS = 256
MAX_ANNOTATIONS_PER_DECLARATION = 32
MAX_LITERALS_PER_ANNOTATION = 16
MAX_LITERAL_UTF8_BYTES = 256
MAX_CALLS_PER_DECLARATION = 128
MAX_TYPE_USES_PER_DECLARATION = 8
MAX_ANNOTATION_SQL_UTF8_BYTES = 4_096

_TYPE_DECLARATIONS = {
    "annotation_type_declaration",
    "class_declaration",
    "enum_declaration",
    "interface_declaration",
    "record_declaration",
}
_METHOD_DECLARATIONS = {
    "compact_constructor_declaration",
    "constructor_declaration",
    "method_declaration",
}
_ANNOTATIONS = {"annotation", "marker_annotation"}
_PRIMITIVES = {
    "boolean",
    "byte",
    "char",
    "double",
    "float",
    "int",
    "long",
    "short",
    "void",
}
_JAVA_LANG_TYPES = {
    "Appendable",
    "AutoCloseable",
    "Boolean",
    "Byte",
    "Character",
    "CharSequence",
    "Class",
    "ClassLoader",
    "Cloneable",
    "Comparable",
    "Double",
    "Enum",
    "Error",
    "Exception",
    "Float",
    "Integer",
    "Iterable",
    "Long",
    "Math",
    "Number",
    "Object",
    "Process",
    "Record",
    "Runnable",
    "RuntimeException",
    "Short",
    "StackTraceElement",
    "String",
    "StringBuffer",
    "StringBuilder",
    "System",
    "Thread",
    "Throwable",
    "Void",
}
_EXTERNAL_TYPE_PREFIXES = (
    "java.",
    "javax.",
    "jakarta.",
    "org.springframework.",
    "org.apache.ibatis.",
)
_FRAMEWORK_ROLES = {
    "org.springframework.stereotype.Controller": "controller",
    "org.springframework.web.bind.annotation.RestController": "rest_controller",
    "org.springframework.stereotype.Service": "service",
    "org.springframework.stereotype.Repository": "repository",
    "org.springframework.stereotype.Component": "component",
    "org.apache.ibatis.annotations.Mapper": "mapper",
    "org.springframework.beans.factory.annotation.Autowired": "autowired",
    "org.springframework.web.bind.annotation.RequestMapping": "request_mapping",
    "org.springframework.web.bind.annotation.GetMapping": "get_mapping",
    "org.springframework.web.bind.annotation.PostMapping": "post_mapping",
    "org.springframework.web.bind.annotation.PutMapping": "put_mapping",
    "org.springframework.web.bind.annotation.DeleteMapping": "delete_mapping",
    "org.springframework.web.bind.annotation.PatchMapping": "patch_mapping",
}
_SQL_ANNOTATIONS = {
    "org.apache.ibatis.annotations.Delete",
    "org.apache.ibatis.annotations.Insert",
    "org.apache.ibatis.annotations.Select",
    "org.apache.ibatis.annotations.Update",
}


@dataclass(frozen=True)
class SourceRange:
    start_byte: int
    end_byte: int
    start_line: int
    start_column: int
    end_line: int
    end_column: int


@dataclass(frozen=True)
class JavaTypeRef:
    source: str
    erased: str
    qualified_name: str
    candidates: tuple[str, ...]
    resolution: str


@dataclass(frozen=True)
class JavaPackageFact:
    name: str
    source_range: SourceRange


@dataclass(frozen=True)
class JavaImportFact:
    qualified_name: str
    is_static: bool
    is_wildcard: bool
    source_range: SourceRange


@dataclass(frozen=True)
class JavaTypeFact:
    kind: str
    name: str
    qualified_name: str
    owner_qualified_name: str
    type_parameters: tuple[str, ...]
    extends: tuple[JavaTypeRef, ...]
    implements: tuple[JavaTypeRef, ...]
    source_range: SourceRange
    name_range: SourceRange


@dataclass(frozen=True)
class JavaFieldFact:
    kind: str
    owner_qualified_name: str
    name: str
    qualified_name: str
    type_ref: JavaTypeRef
    source_range: SourceRange
    name_range: SourceRange


@dataclass(frozen=True)
class JavaMethodFact:
    kind: str
    owner_qualified_name: str
    name: str
    declared_name: str
    qualified_name: str
    signature: str
    arity: int
    is_varargs: bool
    return_type: JavaTypeRef | None
    type_parameters: tuple[str, ...]
    source_range: SourceRange
    name_range: SourceRange
    body_range: SourceRange | None


@dataclass(frozen=True)
class JavaParameterFact:
    owner_qualified_name: str
    owner_signature: str
    index: int
    name: str
    is_varargs: bool
    type_ref: JavaTypeRef
    source_range: SourceRange
    name_range: SourceRange


@dataclass(frozen=True)
class JavaLocalFact:
    owner_qualified_name: str
    owner_signature: str
    name: str
    role: str
    type_ref: JavaTypeRef
    source_range: SourceRange
    name_range: SourceRange
    scope_range: SourceRange


@dataclass(frozen=True)
class JavaAnnotationLiteral:
    name: str
    value: str
    source_range: SourceRange
    omitted_utf8_bytes: int


@dataclass(frozen=True)
class JavaAnnotationFact:
    owner_kind: str
    owner_qualified_name: str
    owner_signature: str
    name: str
    qualified_name: str
    framework_role: str
    literals: tuple[JavaAnnotationLiteral, ...]
    omitted_literal_count: int
    source_range: SourceRange


@dataclass(frozen=True)
class JavaCallFact:
    source_method: str
    source_signature: str
    source_declaration_range: SourceRange
    target_owner: JavaTypeRef
    target_name: str
    target_signature: str
    arity: int
    argument_types: tuple[JavaTypeRef | None, ...]
    receiver_kind: str
    source_range: SourceRange


@dataclass(frozen=True)
class JavaTypeUseFact:
    source_method: str
    source_signature: str
    target: JavaTypeRef
    role: str
    source_range: SourceRange


@dataclass(frozen=True)
class JavaCommentFact:
    owner_kind: str
    owner_qualified_name: str
    text: str
    tokens: tuple[str, ...]
    source_range: SourceRange


@dataclass(frozen=True)
class JavaOmission:
    owner_qualified_name: str
    category: str
    count: int


@dataclass(frozen=True)
class JavaFactSet:
    fallback_required: bool
    parse_error_count: int = 0
    package_fact: JavaPackageFact | None = None
    imports: tuple[JavaImportFact, ...] = ()
    types: tuple[JavaTypeFact, ...] = ()
    fields: tuple[JavaFieldFact, ...] = ()
    methods: tuple[JavaMethodFact, ...] = ()
    parameters: tuple[JavaParameterFact, ...] = ()
    locals: tuple[JavaLocalFact, ...] = ()
    annotations: tuple[JavaAnnotationFact, ...] = ()
    calls: tuple[JavaCallFact, ...] = ()
    type_uses: tuple[JavaTypeUseFact, ...] = ()
    comments: tuple[JavaCommentFact, ...] = ()
    lexical_tokens: tuple[str, ...] = ()
    annotation_sql_tokens: tuple[str, ...] = ()
    omissions: tuple[JavaOmission, ...] = ()


@dataclass
class _TypeContext:
    node: Any
    name: str
    qualified_name: str
    type_parameters: tuple[str, ...]
    owner: _TypeContext | None
    is_local: bool
    enclosing_method_start_byte: int | None


@dataclass(frozen=True)
class _Binding:
    type_ref: JavaTypeRef | None
    kind: str


@dataclass
class _MethodContext:
    node: Any
    fact: JavaMethodFact
    owner: _TypeContext
    type_variables: frozenset[str]
    parameter_bindings: dict[str, _Binding]
    pending_type_uses: list[tuple[SourceRange, JavaTypeRef, str]]
    seen_type_uses: set[tuple[object, ...]]
    omitted_type_uses: int


class _ByteLineMap:
    def __init__(self, source: bytes) -> None:
        self._source = source
        self._line_starts = [0]
        self._line_starts.extend(
            index + 1 for index, value in enumerate(source) if value == 0x0A
        )

    def source_range(self, node: Any) -> SourceRange:
        start_line, start_column = self._position(node.start_byte)
        end_line, end_column = self._position(node.end_byte)
        return SourceRange(
            start_byte=node.start_byte,
            end_byte=node.end_byte,
            start_line=start_line,
            start_column=start_column,
            end_line=end_line,
            end_column=end_column,
        )

    def _position(self, byte_offset: int) -> tuple[int, int]:
        if not 0 <= byte_offset <= len(self._source):
            raise ValueError("byte offset is outside source")
        line_index = bisect_right(self._line_starts, byte_offset) - 1
        return line_index + 1, byte_offset - self._line_starts[line_index]


def extract_java_facts(source: bytes) -> JavaFactSet:
    if not isinstance(source, bytes):
        raise TypeError("source must be bytes")
    try:
        source.decode("utf-8")
    except UnicodeDecodeError:
        return JavaFactSet(fallback_required=True, parse_error_count=1)

    tree = parse_java(source)
    error_count = sum(
        1 for node in _walk(tree.root_node) if node.is_error or node.is_missing
    )
    if tree.root_node.type != "program" or tree.root_node.has_error or error_count:
        return JavaFactSet(
            fallback_required=True,
            parse_error_count=max(1, error_count),
        )
    return _JavaExtractor(source, tree.root_node).extract()


class _JavaExtractor:
    def __init__(self, source: bytes, root: Any) -> None:
        self.source = source
        self.root = root
        self.lines = _ByteLineMap(source)
        self.package_fact: JavaPackageFact | None = None
        self.package_name = ""
        self.imports: list[JavaImportFact] = []
        self.explicit_imports: dict[str, list[str]] = {}
        self.wildcard_imports: list[str] = []
        self.types: list[JavaTypeFact] = []
        self.fields: list[JavaFieldFact] = []
        self.methods: list[JavaMethodFact] = []
        self.parameters: list[JavaParameterFact] = []
        self.locals: list[JavaLocalFact] = []
        self.annotations: list[JavaAnnotationFact] = []
        self.calls: list[JavaCallFact] = []
        self.type_uses: list[JavaTypeUseFact] = []
        self.comments: list[JavaCommentFact] = []
        self.omissions: list[JavaOmission] = []
        self.type_contexts: list[_TypeContext] = []
        self.field_bindings: dict[str, dict[str, _Binding]] = {}
        self.declaration_owners: list[tuple[int, str, str]] = []
        self.tokens: list[str] = []
        self.sql_tokens: list[str] = []
        self.sql_bytes_remaining = MAX_ANNOTATION_SQL_UTF8_BYTES

    def extract(self) -> JavaFactSet:
        self._extract_package_and_imports()
        self._collect_type_contexts(self.root, None, None)
        self._extract_types()
        self._extract_fields()
        self._extract_methods()
        self._extract_comments()

        range_key = lambda fact: fact.source_range.start_byte
        self.types.sort(key=range_key)
        self.fields.sort(key=range_key)
        self.methods.sort(key=range_key)
        self.parameters.sort(key=range_key)
        self.locals.sort(key=range_key)
        self.annotations.sort(key=range_key)
        self.calls.sort(
            key=lambda fact: (
                fact.source_range.start_byte,
                fact.source_range.end_byte,
                fact.target_name,
            )
        )
        self.type_uses.sort(key=range_key)
        self.comments.sort(key=range_key)
        return JavaFactSet(
            fallback_required=False,
            package_fact=self.package_fact,
            imports=tuple(self.imports),
            types=tuple(self.types),
            fields=tuple(self.fields),
            methods=tuple(self.methods),
            parameters=tuple(self.parameters),
            locals=tuple(self.locals),
            annotations=tuple(self.annotations),
            calls=tuple(self.calls),
            type_uses=tuple(self.type_uses),
            comments=tuple(self.comments),
            lexical_tokens=_dedupe(self.tokens),
            annotation_sql_tokens=_dedupe(self.sql_tokens),
            omissions=tuple(self.omissions),
        )

    def _extract_package_and_imports(self) -> None:
        import_count = 0
        for node in self.root.named_children:
            if node.type == "package_declaration":
                name_node = next(
                    (
                        child
                        for child in node.named_children
                        if child.type in {"identifier", "scoped_identifier"}
                    ),
                    None,
                )
                if name_node is not None:
                    self.package_name = self._text(name_node)
                    self.package_fact = JavaPackageFact(
                        self.package_name, self._range(node)
                    )
                    self._add_tokens(self.package_name)
                continue
            if node.type != "import_declaration":
                continue
            import_count += 1
            if len(self.imports) >= MAX_IMPORTS:
                continue
            raw = self._text(node)
            is_static = raw.startswith("import static")
            is_wildcard = any(
                child.type == "asterisk" for child in node.named_children
            )
            target = next(
                (
                    child
                    for child in node.named_children
                    if child.type in {"identifier", "scoped_identifier"}
                ),
                None,
            )
            if target is None:
                continue
            source_qualified_name = self._text(target)
            qualified_name = source_qualified_name
            if not is_static and not is_wildcard:
                qualified_name = _canonical_qualified_type(qualified_name)
            fact = JavaImportFact(
                qualified_name=qualified_name,
                is_static=is_static,
                is_wildcard=is_wildcard,
                source_range=self._range(node),
            )
            self.imports.append(fact)
            self._add_tokens(qualified_name.rsplit(".", 1)[-1])
            if is_static:
                continue
            if is_wildcard:
                if qualified_name not in self.wildcard_imports:
                    self.wildcard_imports.append(qualified_name)
                continue
            simple_name = source_qualified_name.rsplit(".", 1)[-1]
            values = self.explicit_imports.setdefault(simple_name, [])
            if qualified_name not in values:
                values.append(qualified_name)
        omitted = import_count - len(self.imports)
        if omitted:
            self._omit("", "imports", omitted)

    def _collect_type_contexts(
        self,
        node: Any,
        owner: _TypeContext | None,
        enclosing_method_start_byte: int | None,
    ) -> None:
        if node.type in _TYPE_DECLARATIONS:
            name_node = node.child_by_field_name("name")
            if name_node is None:
                return
            name = self._text(name_node)
            if owner is not None:
                qualified_name = f"{owner.qualified_name}${name}"
            elif self.package_name:
                qualified_name = f"{self.package_name}.{name}"
            else:
                qualified_name = name
            context = _TypeContext(
                node=node,
                name=name,
                qualified_name=qualified_name,
                type_parameters=self._type_parameter_names(
                    node.child_by_field_name("type_parameters")
                ),
                owner=owner,
                is_local=(
                    enclosing_method_start_byte is not None
                    or (owner.is_local if owner else False)
                ),
                enclosing_method_start_byte=(
                    enclosing_method_start_byte
                    if enclosing_method_start_byte is not None
                    else (
                        owner.enclosing_method_start_byte
                        if owner is not None and owner.is_local
                        else None
                    )
                ),
            )
            self.type_contexts.append(context)
            for child in node.named_children:
                self._collect_type_contexts(
                    child,
                    context,
                    context.enclosing_method_start_byte,
                )
            return
        if node.type in _METHOD_DECLARATIONS:
            for child in node.named_children:
                self._collect_type_contexts(child, owner, node.start_byte)
            return
        for child in node.named_children:
            self._collect_type_contexts(
                child,
                owner,
                enclosing_method_start_byte,
            )

    def _extract_types(self) -> None:
        for context in self.type_contexts:
            node = context.node
            name_node = node.child_by_field_name("name")
            if name_node is None:
                continue
            type_variables = self._context_type_variables(context)
            extends: list[JavaTypeRef] = []
            implements: list[JavaTypeRef] = []
            superclass = node.child_by_field_name("superclass")
            if superclass is not None:
                extends.extend(
                    self._type_refs_in_wrapper(
                        superclass, context, type_variables
                    )
                )
            for child in node.named_children:
                if child.type == "extends_interfaces":
                    extends.extend(
                        self._type_refs_in_wrapper(child, context, type_variables)
                    )
            interfaces = node.child_by_field_name("interfaces")
            if interfaces is not None:
                implements.extend(
                    self._type_refs_in_wrapper(
                        interfaces, context, type_variables
                    )
                )
            kind = node.type.removesuffix("_declaration")
            fact = JavaTypeFact(
                kind=kind,
                name=context.name,
                qualified_name=context.qualified_name,
                owner_qualified_name=(
                    context.owner.qualified_name if context.owner else ""
                ),
                type_parameters=context.type_parameters,
                extends=tuple(extends),
                implements=tuple(implements),
                source_range=self._range(node),
                name_range=self._range(name_node),
            )
            self.types.append(fact)
            self.declaration_owners.append(
                (node.start_byte, "type", context.qualified_name)
            )
            self._annotations_for(
                node,
                owner_kind="type",
                owner_qualified_name=context.qualified_name,
                owner_signature="",
            )
            self._add_tokens(context.name)

    def _extract_fields(self) -> None:
        for context in self.type_contexts:
            bindings: dict[str, _Binding] = {}
            self.field_bindings[context.qualified_name] = bindings
            if context.node.type == "record_declaration":
                parameters = context.node.child_by_field_name("parameters")
                if parameters is not None:
                    for parameter, name_node, type_ref in self._parameter_specs(
                        parameters,
                        context,
                        self._context_type_variables(context),
                    ):
                        self._add_field_fact(
                            context,
                            parameter,
                            name_node,
                            self._text(name_node),
                            "record_component",
                            type_ref,
                            bindings,
                        )
            body = context.node.child_by_field_name("body")
            if body is None:
                continue
            for node in _body_members(body):
                if node.type == "field_declaration":
                    self._extract_field_declaration(context, node, bindings)
                elif node.type == "enum_constant":
                    name_node = node.child_by_field_name("name")
                    if name_node is None and node.named_children:
                        name_node = node.named_children[0]
                    if name_node is None:
                        continue
                    name = self._text(name_node)
                    type_ref = self._exact_ref(
                        context.name, context.qualified_name, "local_declaration"
                    )
                    self._add_field_fact(
                        context,
                        node,
                        name_node,
                        name,
                        "enum_constant",
                        type_ref,
                        bindings,
                    )

    def _extract_field_declaration(
        self,
        context: _TypeContext,
        node: Any,
        bindings: dict[str, _Binding],
    ) -> None:
        type_node = node.child_by_field_name("type")
        if type_node is None:
            return
        modifiers = next(
            (child for child in node.named_children if child.type == "modifiers"),
            None,
        )
        modifier_text = self._text(modifiers) if modifiers is not None else ""
        kind = (
            "constant"
            if "static" in modifier_text.split()
            and "final" in modifier_text.split()
            else "field"
        )
        for declarator in node.children_by_field_name("declarator"):
            name_node = declarator.child_by_field_name("name")
            if name_node is None:
                continue
            dimensions = declarator.child_by_field_name("dimensions")
            suffix = self._text(dimensions) if dimensions is not None else ""
            type_ref = self._resolve_type_text(
                self._text(type_node) + suffix,
                context,
                self._context_type_variables(context),
            )
            name = self._text(name_node)
            self._add_field_fact(
                context,
                node,
                name_node,
                name,
                kind,
                type_ref,
                bindings,
            )

    def _add_field_fact(
        self,
        context: _TypeContext,
        declaration: Any,
        name_node: Any,
        name: str,
        kind: str,
        type_ref: JavaTypeRef,
        bindings: dict[str, _Binding],
    ) -> None:
        qualified_name = f"{context.qualified_name}.{name}"
        fact = JavaFieldFact(
            kind=kind,
            owner_qualified_name=context.qualified_name,
            name=name,
            qualified_name=qualified_name,
            type_ref=type_ref,
            source_range=self._range(declaration),
            name_range=self._range(name_node),
        )
        self.fields.append(fact)
        self.declaration_owners.append(
            (declaration.start_byte, "field", qualified_name)
        )
        self._annotations_for(
            declaration,
            owner_kind="field",
            owner_qualified_name=qualified_name,
            owner_signature="",
        )
        self._declare(bindings, name, _Binding(type_ref, "field"))
        self._add_tokens(name)
        self._add_tokens(type_ref.erased)

    def _extract_methods(self) -> None:
        for context in self.type_contexts:
            body = context.node.child_by_field_name("body")
            if body is None:
                continue
            for node in _body_members(body):
                if node.type in _METHOD_DECLARATIONS:
                    self._extract_method(context, node)

    def _extract_method(self, context: _TypeContext, node: Any) -> None:
        is_constructor = node.type != "method_declaration"
        name_node = node.child_by_field_name("name")
        if name_node is None:
            name_node = context.node.child_by_field_name("name")
        if name_node is None:
            return
        declared_name = self._text(name_node)
        name = "<init>" if is_constructor else declared_name
        qualified_name = f"{context.qualified_name}.{name}"
        method_type_parameters = self._type_parameter_names(
            node.child_by_field_name("type_parameters")
        )
        type_variables = frozenset(
            (*self._context_type_variables(context), *method_type_parameters)
        )
        parameter_nodes = node.child_by_field_name("parameters")
        if (
            parameter_nodes is None
            and node.type == "compact_constructor_declaration"
        ):
            parameter_nodes = context.node.child_by_field_name("parameters")
        parameter_specs = self._parameter_specs(
            parameter_nodes, context, type_variables
        )
        signature = _signature(tuple(spec[2] for spec in parameter_specs))
        return_node = None if is_constructor else node.child_by_field_name("type")
        return_type = (
            self._resolve_type_node(return_node, context, type_variables)
            if return_node is not None
            else None
        )
        body_node = node.child_by_field_name("body")
        fact = JavaMethodFact(
            kind="constructor" if is_constructor else "method",
            owner_qualified_name=context.qualified_name,
            name=name,
            declared_name=declared_name,
            qualified_name=qualified_name,
            signature=signature,
            arity=len(parameter_specs),
            is_varargs=any(
                parameter.type == "spread_parameter"
                for parameter, _, _ in parameter_specs
            ),
            return_type=return_type,
            type_parameters=method_type_parameters,
            source_range=self._range(node),
            name_range=self._range(name_node),
            body_range=self._range(body_node) if body_node is not None else None,
        )
        self.methods.append(fact)
        self.declaration_owners.append(
            (node.start_byte, "method", qualified_name)
        )
        self._annotations_for(
            node,
            owner_kind="method",
            owner_qualified_name=qualified_name,
            owner_signature=signature,
        )
        self._add_tokens(declared_name)
        parameter_bindings: dict[str, _Binding] = {}
        initial_type_uses: list[tuple[SourceRange, JavaTypeRef, str]] = []
        if return_type is not None:
            initial_type_uses.append(
                (self._range(return_node), return_type, "return")
            )
        for index, (parameter, name_node, type_ref) in enumerate(parameter_specs):
            parameter_name = self._text(name_node)
            parameter_fact = JavaParameterFact(
                owner_qualified_name=qualified_name,
                owner_signature=signature,
                index=index,
                name=parameter_name,
                is_varargs=parameter.type == "spread_parameter",
                type_ref=type_ref,
                source_range=self._range(parameter),
                name_range=self._range(name_node),
            )
            self.parameters.append(parameter_fact)
            self._declare(
                parameter_bindings,
                parameter_name,
                _Binding(type_ref, "parameter"),
            )
            initial_type_uses.append(
                (parameter_fact.source_range, type_ref, "parameter")
            )
            self._annotations_for(
                parameter,
                owner_kind="parameter",
                owner_qualified_name=f"{qualified_name}:{parameter_name}",
                owner_signature=signature,
            )
            self._add_tokens(parameter_name)
            self._add_tokens(type_ref.erased)

        method_context = _MethodContext(
            node=node,
            fact=fact,
            owner=context,
            type_variables=type_variables,
            parameter_bindings=parameter_bindings,
            pending_type_uses=[],
            seen_type_uses=set(),
            omitted_type_uses=0,
        )
        for source_range, type_ref, role in initial_type_uses:
            self._queue_type_use(method_context, source_range, type_ref, role)
        if body_node is not None:
            visitor = _BodyVisitor(self, method_context)
            visitor.visit(body_node)
            self.calls.extend(
                fact
                for _, _, fact in sorted(visitor.kept_calls)
            )
            if visitor.omitted_calls:
                self._omit(qualified_name, "calls", visitor.omitted_calls)
        self._finalize_type_uses(method_context)

    def _parameter_specs(
        self,
        parameters: Any | None,
        context: _TypeContext,
        type_variables: frozenset[str],
        *,
        scope_method_start_byte: int | None = None,
        source_byte: int | None = None,
    ) -> list[tuple[Any, Any, JavaTypeRef]]:
        if parameters is None:
            return []
        specs: list[tuple[Any, Any, JavaTypeRef]] = []
        for parameter in parameters.named_children:
            if parameter.type not in {"formal_parameter", "spread_parameter"}:
                continue
            name_node = parameter.child_by_field_name("name")
            type_node = parameter.child_by_field_name("type")
            if parameter.type == "spread_parameter":
                declarator = next(
                    (
                        child
                        for child in parameter.named_children
                        if child.type == "variable_declarator"
                    ),
                    None,
                )
                if declarator is not None:
                    name_node = declarator.child_by_field_name("name")
                type_node = next(
                    (
                        child
                        for child in parameter.named_children
                        if child.type not in {"modifiers", "variable_declarator"}
                    ),
                    None,
                )
            if name_node is None or type_node is None:
                continue
            dimensions = parameter.child_by_field_name("dimensions")
            suffix = self._text(dimensions) if dimensions is not None else ""
            if parameter.type == "spread_parameter":
                suffix += "[]"
            type_ref = self._resolve_type_text(
                self._text(type_node) + suffix,
                context,
                type_variables,
                scope_method_start_byte=scope_method_start_byte,
                source_byte=source_byte,
            )
            specs.append((parameter, name_node, type_ref))
        return specs

    def _annotations_for(
        self,
        declaration: Any,
        *,
        owner_kind: str,
        owner_qualified_name: str,
        owner_signature: str,
    ) -> None:
        modifiers = next(
            (
                child
                for child in declaration.named_children
                if child.type == "modifiers"
            ),
            None,
        )
        if modifiers is None:
            return
        kept: list[Any] = []
        annotation_count = 0
        for child in modifiers.named_children:
            if child.type not in _ANNOTATIONS:
                continue
            annotation_count += 1
            if len(kept) < MAX_ANNOTATIONS_PER_DECLARATION:
                kept.append(child)
        omitted = annotation_count - len(kept)
        if omitted:
            self._omit(owner_qualified_name, "annotations", omitted)
        for node in kept:
            fact = self._annotation_fact(
                node,
                owner_kind=owner_kind,
                owner_qualified_name=owner_qualified_name,
                owner_signature=owner_signature,
            )
            self.annotations.append(fact)
            self._add_tokens(fact.name)
            if fact.framework_role.endswith("mapping"):
                for literal in fact.literals:
                    self._add_tokens(literal.value)

    def _annotation_fact(
        self,
        node: Any,
        *,
        owner_kind: str,
        owner_qualified_name: str,
        owner_signature: str,
    ) -> JavaAnnotationFact:
        name_node = node.child_by_field_name("name")
        raw_name = self._text(name_node) if name_node is not None else ""
        name = raw_name.rsplit(".", 1)[-1]
        qualified_name = self._annotation_qualified_name(raw_name)
        literals: list[JavaAnnotationLiteral] = []
        literal_count = 0
        omitted_literal_bytes = 0
        for literal_node, argument_name in self._annotation_literals(node):
            literal_count += 1
            if len(literals) >= MAX_LITERALS_PER_ANNOTATION:
                continue
            value = _decode_java_string(self._text(literal_node))
            value, omitted_bytes = _truncate_utf8(
                value, MAX_LITERAL_UTF8_BYTES
            )
            omitted_literal_bytes += omitted_bytes
            literals.append(
                JavaAnnotationLiteral(
                    name=argument_name,
                    value=value,
                    source_range=self._range(literal_node),
                    omitted_utf8_bytes=omitted_bytes,
                )
            )
        omitted_literal_count = literal_count - len(literals)
        if omitted_literal_count:
            self._omit(
                owner_qualified_name,
                "annotation_literals",
                omitted_literal_count,
            )
        if omitted_literal_bytes:
            self._omit(
                owner_qualified_name,
                "annotation_literal_bytes",
                omitted_literal_bytes,
            )
        if qualified_name in _SQL_ANNOTATIONS:
            for literal in literals:
                kept_value, omitted = _truncate_utf8(
                    literal.value, self.sql_bytes_remaining
                )
                kept_bytes = len(kept_value.encode("utf-8"))
                self.sql_bytes_remaining -= kept_bytes
                self.sql_tokens.extend(tokenize_identifier(kept_value))
                if omitted:
                    self._omit(
                        owner_qualified_name,
                        "annotation_sql_bytes",
                        omitted,
                    )
        return JavaAnnotationFact(
            owner_kind=owner_kind,
            owner_qualified_name=owner_qualified_name,
            owner_signature=owner_signature,
            name=name,
            qualified_name=qualified_name,
            framework_role=_FRAMEWORK_ROLES.get(qualified_name, ""),
            literals=tuple(literals),
            omitted_literal_count=omitted_literal_count,
            source_range=self._range(node),
        )

    def _annotation_literals(
        self,
        annotation: Any,
    ) -> Iterator[tuple[Any, str]]:
        arguments = annotation.child_by_field_name("arguments")
        if arguments is None:
            return

        def visit(node: Any, argument_name: str) -> Iterator[tuple[Any, str]]:
            if node.type in {"string_literal", "text_block"}:
                yield node, argument_name
                return
            if node.type == "element_value_pair":
                key = node.child_by_field_name("key")
                value = node.child_by_field_name("value")
                if value is not None:
                    yield from visit(
                        value,
                        self._text(key) if key is not None else "value",
                    )
                return
            for child in node.named_children:
                yield from visit(child, argument_name)

        yield from visit(arguments, "value")

    def _annotation_qualified_name(self, raw_name: str) -> str:
        if "." in raw_name:
            return _canonical_qualified_type(raw_name)
        imported = self.explicit_imports.get(raw_name, [])
        if len(imported) == 1:
            return imported[0]
        local = [
            context.qualified_name
            for context in self.type_contexts
            if context.name == raw_name
            and context.node.type == "annotation_type_declaration"
        ]
        return local[0] if len(local) == 1 else ""

    def _extract_comments(self) -> None:
        owners = sorted(self.declaration_owners)
        for node in _walk(self.root):
            if node.type not in {"block_comment", "line_comment"}:
                continue
            owner_kind = ""
            owner_name = ""
            for start_byte, candidate_kind, candidate_name in owners:
                if start_byte <= node.end_byte:
                    continue
                if self.source[node.end_byte:start_byte].strip():
                    break
                owner_kind = candidate_kind
                owner_name = candidate_name
                break
            text = _clean_comment(self._text(node))
            tokens = list(tokenize_identifier(text))
            if owner_name:
                tokens.extend(tokenize_identifier(owner_name.rsplit(".", 1)[-1]))
                tokens.append("comment")
            fact = JavaCommentFact(
                owner_kind=owner_kind,
                owner_qualified_name=owner_name,
                text=text,
                tokens=_dedupe(tokens),
                source_range=self._range(node),
            )
            self.comments.append(fact)
            self.tokens.extend(fact.tokens)

    def _finalize_type_uses(self, context: _MethodContext) -> None:
        for source_range, target, role in context.pending_type_uses:
            self.type_uses.append(
                JavaTypeUseFact(
                    source_method=context.fact.qualified_name,
                    source_signature=context.fact.signature,
                    target=target,
                    role=role,
                    source_range=source_range,
                )
            )
        if context.omitted_type_uses:
            self._omit(
                context.fact.qualified_name,
                "type_uses",
                context.omitted_type_uses,
            )

    def _queue_type_use(
        self,
        context: _MethodContext,
        source_range: SourceRange,
        type_ref: JavaTypeRef,
        role: str,
    ) -> None:
        target = _type_use_target(type_ref)
        if not _eligible_type_use(target):
            return
        key = (
            target.qualified_name,
            target.candidates,
            target.erased,
        )
        if key in context.seen_type_uses:
            return
        context.seen_type_uses.add(key)
        if len(context.pending_type_uses) >= MAX_TYPE_USES_PER_DECLARATION:
            context.omitted_type_uses += 1
            return
        context.pending_type_uses.append((source_range, target, role))

    def _type_refs_in_wrapper(
        self,
        wrapper: Any,
        context: _TypeContext,
        type_variables: frozenset[str],
    ) -> list[JavaTypeRef]:
        nodes: list[Any] = []
        for child in wrapper.named_children:
            if child.type == "type_list":
                nodes.extend(child.named_children)
            else:
                nodes.append(child)
        return [
            self._resolve_type_node(node, context, type_variables)
            for node in nodes
        ]

    def _resolve_type_node(
        self,
        node: Any,
        context: _TypeContext,
        type_variables: frozenset[str],
        *,
        scope_method_start_byte: int | None = None,
        source_byte: int | None = None,
    ) -> JavaTypeRef:
        return self._resolve_type_text(
            self._text(node),
            context,
            type_variables,
            scope_method_start_byte=scope_method_start_byte,
            source_byte=source_byte,
        )

    def _resolve_type_text(
        self,
        source: str,
        context: _TypeContext,
        type_variables: frozenset[str],
        *,
        scope_method_start_byte: int | None = None,
        source_byte: int | None = None,
    ) -> JavaTypeRef:
        erased = _erase_type(source)
        base, array_suffix = _split_array_suffix(erased)
        if base == "var" or "|" in base or "&" in base:
            return JavaTypeRef(source, erased, "", (), "unresolved")
        if base in _PRIMITIVES:
            return JavaTypeRef(source, erased, erased, (), "primitive")
        if base in type_variables:
            return JavaTypeRef(source, erased, "", (), "type_variable")

        known = self._known_type(
            base,
            context,
            scope_method_start_byte=scope_method_start_byte,
            source_byte=source_byte,
        )
        if known:
            return self._exact_ref(source, known + array_suffix, "local_declaration")

        first, separator, remainder = base.partition(".")
        imported = self.explicit_imports.get(first, [])
        if len(imported) == 1:
            qualified = imported[0]
            if separator:
                qualified += "$" + remainder.replace(".", "$")
            return self._exact_ref(
                source, qualified + array_suffix, "explicit_import"
            )
        if len(imported) > 1:
            candidates = tuple(
                value + ("$" + remainder.replace(".", "$") if separator else "")
                + array_suffix
                for value in imported
            )
            return JavaTypeRef(source, erased, "", candidates, "candidates")

        if "." in base:
            qualified = _canonical_qualified_type(base)
            if base[:1].isupper():
                if self.wildcard_imports:
                    candidates = [
                        (
                            f"{self.package_name}.{qualified}"
                            if self.package_name
                            else qualified
                        )
                        + array_suffix
                    ]
                    candidates.extend(
                        f"{package}.{qualified}{array_suffix}"
                        for package in self.wildcard_imports
                    )
                    return JavaTypeRef(
                        source,
                        erased,
                        "",
                        tuple(dict.fromkeys(candidates)),
                        "candidates",
                    )
                if self.package_name:
                    qualified = f"{self.package_name}.{qualified}"
            return self._exact_ref(
                source, qualified + array_suffix, "qualified"
            )
        if base in _JAVA_LANG_TYPES:
            return self._exact_ref(
                source, f"java.lang.{base}{array_suffix}", "java_lang"
            )
        if not self.wildcard_imports:
            qualified = (
                f"{self.package_name}.{base}" if self.package_name else base
            )
            return self._exact_ref(
                source, qualified + array_suffix, "same_package"
            )
        candidates = []
        same_package = (
            f"{self.package_name}.{base}" if self.package_name else base
        )
        candidates.append(same_package + array_suffix)
        candidates.extend(
            f"{package}.{base}{array_suffix}"
            for package in self.wildcard_imports
        )
        return JavaTypeRef(
            source,
            erased,
            "",
            tuple(dict.fromkeys(candidates)),
            "candidates",
        )

    def _known_type(
        self,
        source_name: str,
        context: _TypeContext,
        *,
        scope_method_start_byte: int | None,
        source_byte: int | None,
    ) -> str:
        normalized = source_name.replace("$", ".")
        current: _TypeContext | None = context
        while current is not None:
            if normalized == current.name:
                return current.qualified_name
            if normalized.startswith(current.name + "."):
                return current.qualified_name + "$" + normalized[
                    len(current.name) + 1 :
                ].replace(".", "$")
            current = current.owner
        if scope_method_start_byte is not None and source_byte is not None:
            local_matches = [
                candidate.qualified_name
                for candidate in self.type_contexts
                if candidate.is_local
                and candidate.enclosing_method_start_byte
                == scope_method_start_byte
                and candidate.node.start_byte < source_byte
                and candidate.name == normalized
            ]
            local_unique = tuple(dict.fromkeys(local_matches))
            if len(local_unique) == 1:
                return local_unique[0]
        accessible_owners: set[str] = set()
        current = context
        while current is not None:
            accessible_owners.add(current.qualified_name)
            current = current.owner
        matches = []
        for candidate in self.type_contexts:
            if candidate.is_local:
                continue
            owner_is_accessible = (
                candidate.owner is None
                or candidate.owner.qualified_name in accessible_owners
            )
            if not owner_is_accessible:
                continue
            if (
                candidate.name == normalized
                or candidate.qualified_name == source_name
                or candidate.qualified_name.replace("$", ".") == source_name
                or candidate.qualified_name.removeprefix(
                    f"{self.package_name}." if self.package_name else ""
                ).replace("$", ".")
                == source_name
            ):
                matches.append(candidate.qualified_name)
        unique = tuple(dict.fromkeys(matches))
        return unique[0] if len(unique) == 1 else ""

    def _exact_ref(
        self,
        source: str,
        qualified_name: str,
        resolution: str,
    ) -> JavaTypeRef:
        return JavaTypeRef(
            source=source,
            erased=_erase_type(source),
            qualified_name=qualified_name,
            candidates=(),
            resolution=resolution,
        )

    def _type_parameter_names(self, node: Any | None) -> tuple[str, ...]:
        if node is None:
            return ()
        names: list[str] = []
        for child in node.named_children:
            if child.type != "type_parameter":
                continue
            name = child.child_by_field_name("name")
            if name is None:
                name = next(
                    (
                        item
                        for item in child.named_children
                        if item.type == "type_identifier"
                    ),
                    None,
                )
            if name is not None:
                names.append(self._text(name))
        return tuple(names)

    def _context_type_variables(
        self,
        context: _TypeContext,
    ) -> frozenset[str]:
        names: list[str] = []
        current: _TypeContext | None = context
        while current is not None:
            names.extend(current.type_parameters)
            modifiers = next(
                (
                    child
                    for child in current.node.named_children
                    if child.type == "modifiers"
                ),
                None,
            )
            is_static = (
                modifiers is not None
                and "static" in self._text(modifiers).split()
            )
            implicitly_static = (
                current.owner is not None
                and current.owner.node.type
                in {"annotation_type_declaration", "interface_declaration"}
            )
            if is_static or implicitly_static:
                break
            current = current.owner
        return frozenset(names)

    def _add_tokens(self, value: str) -> None:
        self.tokens.extend(tokenize_identifier(value))

    def _omit(self, owner: str, category: str, count: int) -> None:
        if count > 0:
            self.omissions.append(JavaOmission(owner, category, count))

    def _text(self, node: Any) -> str:
        return self.source[node.start_byte : node.end_byte].decode("utf-8")

    def _range(self, node: Any) -> SourceRange:
        return self.lines.source_range(node)

    @staticmethod
    def _declare(
        scope: dict[str, _Binding],
        name: str,
        binding: _Binding,
    ) -> None:
        if name in scope:
            scope[name] = _Binding(None, "ambiguous")
        else:
            scope[name] = binding


class _BodyVisitor:
    def __init__(self, extractor: _JavaExtractor, method: _MethodContext) -> None:
        self.extractor = extractor
        self.method = method
        self.scopes: list[dict[str, _Binding]] = [
            dict(method.parameter_bindings)
        ]
        self.scope_nodes: list[Any] = [method.node]
        self.call_count = 0
        self.call_sequence = 0
        self.kept_calls: list[tuple[int, int, JavaCallFact]] = []

    @property
    def omitted_calls(self) -> int:
        return self.call_count - len(self.kept_calls)

    def visit(self, node: Any) -> None:
        if node.type in _TYPE_DECLARATIONS or node.type in _METHOD_DECLARATIONS:
            return
        if node.type == "block":
            self._push_scope(node)
            for child in node.named_children:
                self.visit(child)
            self._pop_scope()
            return
        if node.type == "local_variable_declaration":
            self._visit_local_declaration(node)
            return
        if node.type == "lambda_expression":
            self._visit_lambda(node)
            return
        if node.type == "enhanced_for_statement":
            self._visit_enhanced_for(node)
            return
        if node.type in {"for_statement", "try_with_resources_statement"}:
            self._push_scope(node)
            for child in node.named_children:
                self.visit(child)
            self._pop_scope()
            return
        if node.type == "resource":
            self._visit_resource(node)
            return
        if node.type == "catch_clause":
            self._visit_catch(node)
            return
        if node.type == "object_creation_expression":
            self._record_constructor(node)
            arguments = node.child_by_field_name("arguments")
            if arguments is not None:
                for child in arguments.named_children:
                    self.visit(child)
            return
        if node.type == "method_invocation":
            self._record_method_call(node)
        if node.type == "field_access":
            self._receiver(node)
        if node.type == "identifier":
            self._record_field_identifier_use(node)
        for child in node.named_children:
            self.visit(child)

    def _visit_local_declaration(self, node: Any) -> None:
        type_node = node.child_by_field_name("type")
        if type_node is None:
            return
        for declarator in node.children_by_field_name("declarator"):
            name_node = declarator.child_by_field_name("name")
            if name_node is None:
                continue
            dimensions = declarator.child_by_field_name("dimensions")
            suffix = (
                self.extractor._text(dimensions)
                if dimensions is not None
                else ""
            )
            type_ref = self.extractor._resolve_type_text(
                self.extractor._text(type_node) + suffix,
                self.method.owner,
                self.method.type_variables,
                scope_method_start_byte=self.method.node.start_byte,
                source_byte=name_node.start_byte,
            )
            self._add_local(node, name_node, type_ref, "local")
            self.extractor._annotations_for(
                node,
                owner_kind="local",
                owner_qualified_name=(
                    f"{self.method.fact.qualified_name}:{self.extractor._text(name_node)}"
                ),
                owner_signature=self.method.fact.signature,
            )
            value = declarator.child_by_field_name("value")
            if value is not None:
                self.visit(value)
            self._declare(
                self.extractor._text(name_node),
                _Binding(type_ref, "local"),
            )

    def _visit_lambda(self, node: Any) -> None:
        self._push_scope(node)
        parameters = node.child_by_field_name("parameters")
        if parameters is not None:
            if parameters.type == "identifier":
                self._declare(
                    self.extractor._text(parameters),
                    _Binding(None, "lambda_parameter"),
                )
            else:
                typed = self.extractor._parameter_specs(
                    parameters,
                    self.method.owner,
                    self.method.type_variables,
                    scope_method_start_byte=self.method.node.start_byte,
                    source_byte=node.start_byte,
                )
                if typed:
                    for _, name, type_ref in typed:
                        self._declare(
                            self.extractor._text(name),
                            _Binding(type_ref, "lambda_parameter"),
                        )
                else:
                    for child in parameters.named_children:
                        name = child.child_by_field_name("name")
                        if name is None and child.type == "identifier":
                            name = child
                        if name is not None:
                            self._declare(
                                self.extractor._text(name),
                                _Binding(None, "lambda_parameter"),
                            )
        body = node.child_by_field_name("body")
        if body is not None:
            self.visit(body)
        self._pop_scope()

    def _visit_enhanced_for(self, node: Any) -> None:
        self._push_scope(node)
        type_node = node.child_by_field_name("type")
        name_node = node.child_by_field_name("name")
        binding: _Binding | None = None
        if type_node is not None and name_node is not None:
            type_ref = self.extractor._resolve_type_node(
                type_node,
                self.method.owner,
                self.method.type_variables,
                scope_method_start_byte=self.method.node.start_byte,
                source_byte=name_node.start_byte,
            )
            self._add_local(node, name_node, type_ref, "enhanced_for")
            binding = _Binding(type_ref, "local")
        value = node.child_by_field_name("value")
        if value is not None:
            self.visit(value)
        if binding is not None and name_node is not None:
            self._declare(self.extractor._text(name_node), binding)
        body = node.child_by_field_name("body")
        if body is not None:
            self.visit(body)
        self._pop_scope()

    def _visit_resource(self, node: Any) -> None:
        type_node = node.child_by_field_name("type")
        name_node = node.child_by_field_name("name")
        if type_node is None or name_node is None:
            return
        type_ref = self.extractor._resolve_type_node(
            type_node,
            self.method.owner,
            self.method.type_variables,
            scope_method_start_byte=self.method.node.start_byte,
            source_byte=name_node.start_byte,
        )
        self._add_local(node, name_node, type_ref, "resource")
        value = node.child_by_field_name("value")
        if value is not None:
            self.visit(value)
        self._declare(
            self.extractor._text(name_node), _Binding(type_ref, "local")
        )

    def _visit_catch(self, node: Any) -> None:
        self._push_scope(node)
        parameter = next(
            (
                child
                for child in node.named_children
                if child.type == "catch_formal_parameter"
            ),
            None,
        )
        if parameter is not None:
            name_node = parameter.child_by_field_name("name")
            if name_node is None:
                name_node = next(
                    (
                        child
                        for child in parameter.named_children
                        if child.type == "identifier"
                    ),
                    None,
                )
            type_node = next(
                (
                    child
                    for child in parameter.named_children
                    if child is not name_node
                ),
                None,
            )
            if name_node is not None and type_node is not None:
                type_ref = self.extractor._resolve_type_node(
                    type_node,
                    self.method.owner,
                    self.method.type_variables,
                    scope_method_start_byte=self.method.node.start_byte,
                    source_byte=name_node.start_byte,
                )
                self._add_local(parameter, name_node, type_ref, "catch")
                self._declare(
                    self.extractor._text(name_node),
                    _Binding(type_ref, "local"),
                )
        body = next(
            (child for child in node.named_children if child.type == "block"),
            None,
        )
        if body is not None:
            self.visit(body)
        self._pop_scope()

    def _add_local(
        self,
        declaration: Any,
        name_node: Any,
        type_ref: JavaTypeRef,
        role: str,
    ) -> None:
        fact = JavaLocalFact(
            owner_qualified_name=self.method.fact.qualified_name,
            owner_signature=self.method.fact.signature,
            name=self.extractor._text(name_node),
            role=role,
            type_ref=type_ref,
            source_range=self.extractor._range(declaration),
            name_range=self.extractor._range(name_node),
            scope_range=self.extractor._range(self.scope_nodes[-1]),
        )
        self.extractor.locals.append(fact)
        self._add_type_use(type_ref, role, fact.source_range)
        self.extractor._add_tokens(fact.name)
        self.extractor._add_tokens(type_ref.erased)

    def _record_method_call(self, node: Any) -> None:
        name_node = node.child_by_field_name("name")
        arguments = node.child_by_field_name("arguments")
        if name_node is None or arguments is None:
            return
        owner, receiver_kind = self._receiver(
            node.child_by_field_name("object")
        )
        argument_nodes = list(arguments.named_children)
        argument_types = tuple(
            self._expression_type(argument) for argument in argument_nodes
        )
        signature = _proven_argument_signature(argument_types)
        self._append_call(
            JavaCallFact(
                source_method=self.method.fact.qualified_name,
                source_signature=self.method.fact.signature,
                source_declaration_range=self.method.fact.source_range,
                target_owner=owner,
                target_name=self.extractor._text(name_node),
                target_signature=signature,
                arity=len(argument_nodes),
                argument_types=argument_types,
                receiver_kind=receiver_kind,
                source_range=self.extractor._range(node),
            ),
            name_node.start_byte,
        )

    def _record_constructor(self, node: Any) -> None:
        type_node = node.child_by_field_name("type")
        arguments = node.child_by_field_name("arguments")
        if type_node is None or arguments is None:
            return
        owner = self.extractor._resolve_type_node(
            type_node,
            self.method.owner,
            self.method.type_variables,
            scope_method_start_byte=self.method.node.start_byte,
            source_byte=type_node.start_byte,
        )
        argument_nodes = list(arguments.named_children)
        argument_types = tuple(
            self._expression_type(argument) for argument in argument_nodes
        )
        self._append_call(
            JavaCallFact(
                source_method=self.method.fact.qualified_name,
                source_signature=self.method.fact.signature,
                source_declaration_range=self.method.fact.source_range,
                target_owner=owner,
                target_name="<init>",
                target_signature=_proven_argument_signature(argument_types),
                arity=len(argument_nodes),
                argument_types=argument_types,
                receiver_kind="constructor",
                source_range=self.extractor._range(node),
            ),
            type_node.start_byte,
        )
        self._add_type_use(owner, "new", self.extractor._range(type_node))

    def _append_call(self, fact: JavaCallFact, order_byte: int) -> None:
        self.call_count += 1
        self.call_sequence += 1
        self.kept_calls.append((order_byte, self.call_sequence, fact))
        self.kept_calls.sort(key=lambda item: (item[0], item[1]))
        if len(self.kept_calls) > MAX_CALLS_PER_DECLARATION:
            self.kept_calls.pop()

    def _record_field_identifier_use(self, node: Any) -> None:
        parent = node.parent
        if parent is not None:
            if parent.type in {
                "annotation",
                "marker_annotation",
                "scoped_identifier",
                "scoped_type_identifier",
            }:
                return
            for field_name in ("field", "name", "type"):
                field = parent.child_by_field_name(field_name)
                if (
                    field is not None
                    and field.start_byte == node.start_byte
                    and field.end_byte == node.end_byte
                ):
                    return
        binding = self._lookup(self.extractor._text(node))
        if binding is None or binding.kind != "field" or binding.type_ref is None:
            return
        self._add_type_use(
            binding.type_ref,
            "referenced_field",
            self.extractor._range(node),
        )

    def _receiver(self, node: Any | None) -> tuple[JavaTypeRef, str]:
        if node is None or node.type == "this":
            return self._owner_ref(), "this"
        if node.type == "identifier":
            name = self.extractor._text(node)
            binding = self._lookup(name)
            if binding is not None:
                if binding.type_ref is not None:
                    if binding.kind == "field":
                        self._add_type_use(
                            binding.type_ref,
                            "referenced_field",
                            self.extractor._range(node),
                        )
                    return binding.type_ref, binding.kind
                return self._unresolved_ref(name), "unresolved"
            if name[:1].isupper():
                type_ref = self.extractor._resolve_type_text(
                    name,
                    self.method.owner,
                    self.method.type_variables,
                    scope_method_start_byte=self.method.node.start_byte,
                    source_byte=node.start_byte,
                )
                if type_ref.qualified_name:
                    return type_ref, "static_type"
            return self._unresolved_ref(name), "unresolved"
        if node.type == "field_access":
            object_node = node.child_by_field_name("object")
            field_node = node.child_by_field_name("field")
            if (
                object_node is not None
                and object_node.type == "this"
                and field_node is not None
            ):
                binding = self._field_binding(
                    self.method.owner, self.extractor._text(field_node), False
                )
                if binding is not None and binding.type_ref is not None:
                    self._add_type_use(
                        binding.type_ref,
                        "referenced_field",
                        self.extractor._range(field_node),
                    )
                    return binding.type_ref, "field"
            return self._unresolved_ref(self.extractor._text(node)), "unresolved"
        if node.type == "cast_expression":
            type_node = node.child_by_field_name("type")
            if type_node is not None:
                return (
                    self.extractor._resolve_type_node(
                        type_node,
                        self.method.owner,
                        self.method.type_variables,
                        scope_method_start_byte=self.method.node.start_byte,
                        source_byte=type_node.start_byte,
                    ),
                    "cast",
                )
        if node.type == "parenthesized_expression" and node.named_children:
            owner, receiver_kind = self._receiver(node.named_children[0])
            if receiver_kind == "cast":
                return owner, receiver_kind
        if node.type == "object_creation_expression":
            type_node = node.child_by_field_name("type")
            if type_node is not None:
                return (
                    self.extractor._resolve_type_node(
                        type_node,
                        self.method.owner,
                        self.method.type_variables,
                        scope_method_start_byte=self.method.node.start_byte,
                        source_byte=type_node.start_byte,
                    ),
                    "constructor",
                )
        return self._unresolved_ref(self.extractor._text(node)), "unresolved"

    def _expression_type(self, node: Any) -> JavaTypeRef | None:
        if node.type == "identifier":
            binding = self._lookup(self.extractor._text(node))
            if binding is None or binding.type_ref is None:
                return None
            if binding.kind == "field":
                self._add_type_use(
                    binding.type_ref,
                    "referenced_field",
                    self.extractor._range(node),
                )
            return binding.type_ref
        if node.type == "field_access":
            owner, kind = self._receiver(node)
            return owner if kind == "field" else None
        if node.type == "object_creation_expression":
            type_node = node.child_by_field_name("type")
            if type_node is None:
                return None
            return self.extractor._resolve_type_node(
                type_node,
                self.method.owner,
                self.method.type_variables,
                scope_method_start_byte=self.method.node.start_byte,
                source_byte=type_node.start_byte,
            )
        if node.type == "cast_expression":
            type_node = node.child_by_field_name("type")
            if type_node is None:
                return None
            return self.extractor._resolve_type_node(
                type_node,
                self.method.owner,
                self.method.type_variables,
                scope_method_start_byte=self.method.node.start_byte,
                source_byte=type_node.start_byte,
            )
        if node.type == "parenthesized_expression" and node.named_children:
            return self._expression_type(node.named_children[0])
        if node.type == "this":
            return self._owner_ref()
        return None

    def _lookup(self, name: str) -> _Binding | None:
        for scope in reversed(self.scopes):
            if name in scope:
                return scope[name]
        context: _TypeContext | None = self.method.owner
        while context is not None:
            binding = self._field_binding(context, name, True)
            if binding is not None:
                return binding
            context = context.owner
        return None

    def _field_binding(
        self,
        context: _TypeContext,
        name: str,
        include_outer: bool,
    ) -> _Binding | None:
        current: _TypeContext | None = context
        while current is not None:
            fields = self.extractor.field_bindings.get(current.qualified_name, {})
            if name in fields:
                return fields[name]
            if not include_outer:
                break
            current = current.owner
        return None

    def _owner_ref(self) -> JavaTypeRef:
        return self.extractor._exact_ref(
            self.method.owner.name,
            self.method.owner.qualified_name,
            "local_declaration",
        )

    @staticmethod
    def _unresolved_ref(source: str) -> JavaTypeRef:
        return JavaTypeRef(source, source, "", (), "unresolved")

    def _add_type_use(
        self,
        type_ref: JavaTypeRef,
        role: str,
        source_range: SourceRange,
    ) -> None:
        self.extractor._queue_type_use(
            self.method,
            source_range,
            type_ref,
            role,
        )

    def _push_scope(self, node: Any) -> None:
        self.scopes.append({})
        self.scope_nodes.append(node)

    def _pop_scope(self) -> None:
        self.scopes.pop()
        self.scope_nodes.pop()

    def _declare(self, name: str, binding: _Binding) -> None:
        self.extractor._declare(self.scopes[-1], name, binding)


def _walk(node: Any) -> Iterator[Any]:
    yield node
    for child in node.children:
        yield from _walk(child)


def _body_members(body: Any) -> Iterator[Any]:
    for child in body.named_children:
        if child.type == "enum_body_declarations":
            yield from child.named_children
        else:
            yield child


def _signature(parameters: tuple[JavaTypeRef, ...]) -> str:
    if any(not parameter.qualified_name for parameter in parameters):
        return ""
    return "(" + ",".join(parameter.qualified_name for parameter in parameters) + ")"


def _proven_argument_signature(
    arguments: tuple[JavaTypeRef | None, ...],
) -> str:
    if any(argument is None or not argument.qualified_name for argument in arguments):
        return ""
    return "(" + ",".join(
        argument.qualified_name
        for argument in arguments
        if argument is not None
    ) + ")"


def _erase_type(source: str) -> str:
    compact = "".join(_strip_type_annotations(source).split()).replace(
        "...", "[]"
    )
    output: list[str] = []
    generic_depth = 0
    index = 0
    while index < len(compact):
        value = compact[index]
        if value == "@":
            index += 1
            while index < len(compact) and (
                compact[index].isalnum() or compact[index] in "_.$"
            ):
                index += 1
            if index < len(compact) and compact[index] == "(":
                depth = 1
                index += 1
                while index < len(compact) and depth:
                    if compact[index] == "(":
                        depth += 1
                    elif compact[index] == ")":
                        depth -= 1
                    index += 1
            continue
        if value == "<":
            generic_depth += 1
        elif value == ">" and generic_depth:
            generic_depth -= 1
        elif generic_depth == 0:
            output.append(value)
        index += 1
    return "".join(output)


def _strip_type_annotations(source: str) -> str:
    output: list[str] = []
    index = 0
    while index < len(source):
        if source[index] != "@":
            output.append(source[index])
            index += 1
            continue
        index += 1
        while index < len(source) and source[index].isspace():
            index += 1
        while index < len(source) and (
            source[index].isalnum() or source[index] in "_.$"
        ):
            index += 1
        while index < len(source) and source[index].isspace():
            index += 1
        if index < len(source) and source[index] == "(":
            depth = 1
            index += 1
            quote = ""
            escaped = False
            while index < len(source) and depth:
                value = source[index]
                if quote:
                    if escaped:
                        escaped = False
                    elif value == "\\":
                        escaped = True
                    elif value == quote:
                        quote = ""
                elif value in {'"', "'"}:
                    quote = value
                elif value == "(":
                    depth += 1
                elif value == ")":
                    depth -= 1
                index += 1
        output.append(" ")
    return "".join(output)


def _split_array_suffix(value: str) -> tuple[str, str]:
    suffix = ""
    while value.endswith("[]"):
        value = value[:-2]
        suffix += "[]"
    return value, suffix


def _canonical_qualified_type(value: str) -> str:
    parts = value.replace("$", ".").split(".")
    type_index = next(
        (
            index
            for index, part in enumerate(parts)
            if part[:1].isupper()
        ),
        len(parts) - 1,
    )
    package = ".".join(parts[:type_index])
    type_name = "$".join(parts[type_index:])
    return f"{package}.{type_name}" if package else type_name


def _type_use_target(type_ref: JavaTypeRef) -> JavaTypeRef:
    base, _ = _split_array_suffix(type_ref.erased)
    qualified, _ = _split_array_suffix(type_ref.qualified_name)
    candidates = tuple(
        _split_array_suffix(candidate)[0] for candidate in type_ref.candidates
    )
    return JavaTypeRef(
        source=type_ref.source,
        erased=base,
        qualified_name=qualified,
        candidates=candidates,
        resolution=type_ref.resolution,
    )


def _eligible_type_use(type_ref: JavaTypeRef) -> bool:
    if type_ref.resolution in {"primitive", "type_variable", "unresolved"}:
        return False
    names = (
        (type_ref.qualified_name,)
        if type_ref.qualified_name
        else type_ref.candidates
    )
    if not names:
        return False
    if type_ref.resolution in {"same_package", "local_declaration"}:
        return True
    return any(
        not name.startswith(_EXTERNAL_TYPE_PREFIXES)
        for name in names
    )


def _decode_java_string(source: str) -> str:
    if source.startswith('"""') and source.endswith('"""'):
        value = source[3:-3]
    elif len(source) >= 2 and source[0] == source[-1] == '"':
        value = source[1:-1]
    else:
        return source
    output: list[str] = []
    escapes = {
        "b": "\b",
        "f": "\f",
        "n": "\n",
        "r": "\r",
        "s": " ",
        "t": "\t",
        '"': '"',
        "'": "'",
        "\\": "\\",
    }
    index = 0
    while index < len(value):
        if value[index] != "\\" or index + 1 >= len(value):
            output.append(value[index])
            index += 1
            continue
        index += 1
        escaped = value[index]
        if escaped == "u":
            while index < len(value) and value[index] == "u":
                index += 1
            digits = value[index : index + 4]
            if len(digits) == 4:
                try:
                    output.append(chr(int(digits, 16)))
                    index += 4
                    continue
                except ValueError:
                    pass
            output.append("u")
            continue
        if escaped in "01234567":
            end = index + 1
            while end < min(len(value), index + 3) and value[end] in "01234567":
                end += 1
            output.append(chr(int(value[index:end], 8)))
            index = end
            continue
        if escaped in {"\n", "\r"}:
            if escaped == "\r" and index + 1 < len(value) and value[index + 1] == "\n":
                index += 1
            index += 1
            continue
        output.append(escapes.get(escaped, escaped))
        index += 1
    return "".join(output)


def _truncate_utf8(value: str, limit: int) -> tuple[str, int]:
    encoded = value.encode("utf-8")
    if len(encoded) <= limit:
        return value, 0
    kept = encoded[: max(0, limit)].decode("utf-8", errors="ignore")
    kept_bytes = len(kept.encode("utf-8"))
    return kept, len(encoded) - kept_bytes


def _clean_comment(value: str) -> str:
    if value.startswith("//"):
        return value[2:].strip()
    if value.startswith("/*") and value.endswith("*/"):
        value = value[2:-2]
    lines = []
    for line in value.splitlines():
        stripped = line.strip()
        if stripped.startswith("*"):
            stripped = stripped[1:].strip()
        if stripped:
            lines.append(stripped)
    return "\n".join(lines)


def _dedupe(values: list[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(value for value in values if value))
