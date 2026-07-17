from __future__ import annotations

from dataclasses import replace
import re
from typing import Mapping

from context_search_tool.graph_contract import (
    MAX_PRODUCER_RELATIONS_PER_FILE,
    MAX_SIGNALS_PER_FILE,
    generate_v5_relation_id,
    generate_v5_signal_id,
)
from context_search_tool.graph_plugins import (
    MaterializedGraph,
    ParsedGraphFacts,
    PluginContext,
)
from context_search_tool.java_ast import (
    JavaAnnotationFact,
    JavaFactSet,
    JavaTypeRef,
    SourceRange,
    extract_java_facts,
)
from context_search_tool.models import (
    CodeRelation,
    CodeSignal,
    DocumentChunk,
    SymbolRef,
)


_PRODUCER = "java_ast"
_HTTP_METHODS = {
    "delete_mapping": "DELETE",
    "get_mapping": "GET",
    "patch_mapping": "PATCH",
    "post_mapping": "POST",
    "put_mapping": "PUT",
    "request_mapping": "",
}
_EXTERNAL_JAVA_PREFIXES = (
    "java.",
    "javax.",
    "jakarta.",
    "org.apache.ibatis.",
    "org.springframework.",
)
_TOKEN_PART_RE = re.compile(
    r"[A-Z]+(?=[A-Z][a-z]|\d|$)|[A-Z]?[a-z]+|\d+|[A-Z]+"
)


class JavaGraphProducer:
    def supports(self, context: PluginContext) -> bool:
        return (
            context.language == "java"
            or context.file_path.suffix.lower() == ".java"
        )

    def parse(self, context: PluginContext, content: bytes) -> ParsedGraphFacts:
        if not self.supports(context):
            raise ValueError("JavaGraphProducer received an unsupported source")
        facts = extract_java_facts(content)
        if facts.fallback_required:
            return ParsedGraphFacts(
                facts=facts,
                metadata={
                    "graph_parse_status": "legacy_fallback",
                    "graph_parse_error_count": facts.parse_error_count,
                },
                fallback_required=True,
            )
        return ParsedGraphFacts(
            facts=facts,
            symbols=_symbols(facts),
            lexical_tokens=facts.lexical_tokens + facts.annotation_sql_tokens,
            metadata=_parse_metadata(facts),
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
            parsed.fallback_required
            or not isinstance(facts, JavaFactSet)
            or facts.fallback_required
        ):
            return MaterializedGraph(metadata=parsed.metadata)
        if module_signal.file_path != context.file_path:
            raise ValueError("module signal does not belong to the plugin context")

        materializer = _JavaMaterializer(context, facts, chunks, module_signal)
        return materializer.materialize(parsed.metadata)


class _JavaMaterializer:
    def __init__(
        self,
        context: PluginContext,
        facts: JavaFactSet,
        chunks: tuple[DocumentChunk, ...],
        module_signal: CodeSignal,
    ) -> None:
        self.context = context
        self.facts = facts
        self.chunks = tuple(
            sorted(
                chunks,
                key=lambda item: (
                    item.start_line,
                    item.end_line,
                    item.chunk_id,
                ),
            )
        )
        self.module_signal = module_signal
        self.signals: list[CodeSignal] = []
        self.relations: dict[str, CodeRelation] = {}
        self.declarations: dict[tuple[str, str, str], CodeSignal] = {}
        self.edge_sources: dict[tuple[str, str], list[CodeSignal]] = {}

    def materialize(self, metadata: Mapping[str, object]) -> MaterializedGraph:
        self._declaration_signals()
        self._endpoint_signals()
        if len(self.signals) > MAX_SIGNALS_PER_FILE:
            self.signals = self.signals[:MAX_SIGNALS_PER_FILE]
        active_signal_ids = {signal.signal_id for signal in self.signals}
        self._implements_relations(active_signal_ids)
        self._call_relations(active_signal_ids)
        self._type_use_relations(active_signal_ids)
        self._import_relations()

        relations = sorted(
            self.relations.values(),
            key=lambda item: (
                int(item.metadata.get("first_source_line", 0)),
                int(item.metadata.get("first_source_column", 0)),
                item.kind,
                item.target_qualified_name,
                item.target_signature,
                item.relation_id,
            ),
        )[:MAX_PRODUCER_RELATIONS_PER_FILE]
        relations = [
            relation
            for relation in relations
            if relation.source_signal_id == self.module_signal.signal_id
            or relation.source_signal_id in active_signal_ids
        ]
        return MaterializedGraph(
            signals=tuple(self.signals),
            relations=tuple(relations),
            metadata=metadata,
        )

    def _declaration_signals(self) -> None:
        for fact in self.facts.types:
            signal = self._signal(
                kind="type",
                name=fact.name,
                qualified_name=fact.qualified_name,
                signature="",
                arity=None,
                source_range=fact.source_range,
                tokens=_tokens(fact.name, fact.qualified_name),
                metadata={"declaration_kind": fact.kind},
            )
            self._remember_declaration("type", fact.qualified_name, "", signal)
        for fact in self.facts.fields:
            owner_name = fact.owner_qualified_name.rsplit(".", 1)[-1]
            signal = self._signal(
                kind="field",
                name=f"{owner_name}.{fact.name}" if owner_name else fact.name,
                qualified_name=fact.qualified_name,
                signature="",
                arity=None,
                source_range=fact.source_range,
                tokens=_tokens(owner_name, fact.name, fact.type_ref.erased),
                metadata={
                    "declaration_kind": fact.kind,
                    "owner_type": fact.owner_qualified_name,
                    "field_type": _selector_name(fact.type_ref),
                },
            )
            self._remember_declaration("field", fact.qualified_name, "", signal)
        for fact in self.facts.methods:
            owner_name = fact.owner_qualified_name.rsplit(".", 1)[-1]
            display_name = fact.declared_name or fact.name
            signal = self._signal(
                kind="method",
                name=f"{owner_name}.{display_name}" if owner_name else display_name,
                qualified_name=fact.qualified_name,
                signature=fact.signature,
                arity=fact.arity,
                source_range=fact.source_range,
                tokens=_tokens(owner_name, display_name, fact.signature),
                metadata={
                    "declaration_kind": fact.kind,
                    "owner_type": fact.owner_qualified_name,
                    "owner_method": fact.name,
                },
            )
            self._remember_declaration(
                "method", fact.qualified_name, fact.signature, signal
            )
            self.edge_sources[(fact.qualified_name, fact.signature)] = [signal]
        for fact in self.facts.comments:
            owner_name = fact.owner_qualified_name.rsplit(".", 1)[-1]
            signal = self._signal(
                kind="comment",
                name=f"{owner_name} comment" if owner_name else "comment",
                qualified_name=f"{fact.owner_qualified_name}#comment",
                signature="",
                arity=None,
                source_range=fact.source_range,
                tokens=list(fact.tokens),
                metadata={
                    "owner_kind": fact.owner_kind,
                    "owner_qualified_name": fact.owner_qualified_name,
                    "text": fact.text,
                },
            )
            self.signals.append(signal)

        self.signals.sort(
            key=lambda item: (
                item.start_line,
                item.start_column,
                item.end_line,
                item.end_column,
                item.kind,
                item.qualified_name,
                item.signature,
            )
        )

    def _endpoint_signals(self) -> None:
        annotations_by_owner: dict[tuple[str, str], list[JavaAnnotationFact]] = {}
        for annotation in self.facts.annotations:
            if annotation.framework_role.endswith("mapping"):
                annotations_by_owner.setdefault(
                    (annotation.owner_qualified_name, annotation.owner_signature), []
                ).append(annotation)
        type_paths = {
            fact.qualified_name: _mapping_paths(
                annotations_by_owner.get((fact.qualified_name, ""), [])
            )
            for fact in self.facts.types
        }
        for method in self.facts.methods:
            mappings = annotations_by_owner.get(
                (method.qualified_name, method.signature), []
            )
            if not mappings:
                continue
            parent_paths = type_paths.get(method.owner_qualified_name) or ("",)
            endpoint_signals: list[CodeSignal] = []
            for annotation in mappings:
                http_method = _HTTP_METHODS.get(annotation.framework_role)
                if http_method is None:
                    continue
                for parent in parent_paths:
                    for child in _annotation_paths(annotation):
                        route = _join_spring_route(parent, child)
                        name = f"{http_method} {route}".strip()
                        qualified_name = (
                            f"{method.qualified_name}#{http_method or 'ANY'} {route}"
                        )
                        endpoint_signals.append(
                            self._signal(
                                kind="endpoint",
                                name=name,
                                qualified_name=qualified_name,
                                signature=method.signature,
                                arity=method.arity,
                                source_range=method.source_range,
                                tokens=_tokens(
                                    http_method,
                                    route,
                                    method.owner_qualified_name,
                                    method.name,
                                ),
                                metadata={
                                    "http_method": http_method,
                                    "path": route,
                                    "controller": method.owner_qualified_name,
                                    "method": method.name,
                                    "method_qualified_name": method.qualified_name,
                                    "framework_role": annotation.framework_role,
                                },
                            )
                        )
            if endpoint_signals:
                endpoint_signals.sort(
                    key=lambda item: (item.name, item.qualified_name, item.signal_id)
                )
                self.signals.extend(endpoint_signals)
                self.edge_sources[(method.qualified_name, method.signature)] = (
                    endpoint_signals
                )
        self.signals.sort(
            key=lambda item: (
                item.start_line,
                item.start_column,
                item.kind,
                item.qualified_name,
                item.signal_id,
            )
        )

    def _implements_relations(self, active_signal_ids: set[str]) -> None:
        for type_fact in self.facts.types:
            source = self.declarations.get(("type", type_fact.qualified_name, ""))
            if source is None or source.signal_id not in active_signal_ids:
                continue
            methods = [
                method
                for method in self.facts.methods
                if method.kind == "method"
                and method.owner_qualified_name == type_fact.qualified_name
            ]
            for target in type_fact.implements:
                self._add_relation(
                    source=source,
                    kind="implements",
                    target_kind="type",
                    target_qualified_name=_selector_qualified_name(target),
                    target_signature="",
                    target_arity=None,
                    target_name=_selector_name(target),
                    source_range=type_fact.source_range,
                    metadata=_type_selector_metadata(target),
                )
                for method in methods:
                    candidates = tuple(
                        f"{candidate}.{method.name}" for candidate in target.candidates
                    )
                    target_owner = target.qualified_name
                    self._add_relation(
                        source=self.declarations[
                            ("method", method.qualified_name, method.signature)
                        ],
                        kind="implements_method",
                        target_kind="method",
                        target_qualified_name=(
                            f"{target_owner}.{method.name}"
                            if target_owner
                            else (candidates[0] if candidates else "")
                        ),
                        target_signature=method.signature,
                        target_arity=method.arity,
                        target_name=(
                            f"{_selector_name(target)}.{method.name}"
                            if _selector_name(target)
                            else method.name
                        ),
                        source_range=method.source_range,
                        metadata={
                            **_type_selector_metadata(target),
                            "candidates": candidates,
                        },
                    )

    def _call_relations(self, active_signal_ids: set[str]) -> None:
        for call in self.facts.calls:
            sources = self.edge_sources.get(
                (call.source_method, call.source_signature), []
            )
            candidates = tuple(
                f"{candidate}.{call.target_name}"
                for candidate in call.target_owner.candidates
            )
            target_owner = call.target_owner.qualified_name
            target_qualified_name = (
                f"{target_owner}.{call.target_name}"
                if target_owner
                else (candidates[0] if candidates else "")
            )
            if not target_qualified_name and not candidates:
                continue
            for source in sources:
                if source.signal_id not in active_signal_ids:
                    continue
                self._add_relation(
                    source=source,
                    kind="calls",
                    target_kind="method",
                    target_qualified_name=target_qualified_name,
                    target_signature=call.target_signature,
                    target_arity=call.arity,
                    target_name=(
                        f"{_selector_name(call.target_owner)}.{call.target_name}"
                    ),
                    source_range=call.source_range,
                    metadata={
                        **_type_selector_metadata(call.target_owner),
                        "candidates": candidates,
                        "receiver_kind": call.receiver_kind,
                    },
                )

    def _type_use_relations(self, active_signal_ids: set[str]) -> None:
        for fact in self.facts.type_uses:
            sources = self.edge_sources.get(
                (fact.source_method, fact.source_signature), []
            )
            if not fact.target.qualified_name and not fact.target.candidates:
                continue
            for source in sources:
                if source.signal_id not in active_signal_ids:
                    continue
                self._add_relation(
                    source=source,
                    kind="uses_type",
                    target_kind="type",
                    target_qualified_name=_selector_qualified_name(fact.target),
                    target_signature="",
                    target_arity=None,
                    target_name=_selector_name(fact.target),
                    source_range=fact.source_range,
                    metadata={
                        **_type_selector_metadata(fact.target),
                        "role": fact.role,
                    },
                )

    def _import_relations(self) -> None:
        for fact in self.facts.imports:
            if fact.is_static or fact.is_wildcard:
                continue
            self._add_relation(
                source=self.module_signal,
                kind="imports_type",
                target_kind="type",
                target_qualified_name=fact.qualified_name,
                target_signature="",
                target_arity=None,
                target_name=fact.qualified_name,
                source_range=fact.source_range,
                metadata={
                    "selector_state": (
                        "external"
                        if _is_external_java_name(fact.qualified_name)
                        else "exact"
                    ),
                    "resolution_basis": "explicit_java_import",
                    "target_language": "java",
                },
            )

    def _signal(
        self,
        *,
        kind: str,
        name: str,
        qualified_name: str,
        signature: str,
        arity: int | None,
        source_range: SourceRange,
        tokens: list[str],
        metadata: dict[str, object],
    ) -> CodeSignal:
        chunk = _containing_chunk(self.chunks, source_range.start_line)
        if chunk is None:
            raise ValueError(
                f"no containing chunk for Java signal at line {source_range.start_line}"
            )
        signal_id = generate_v5_signal_id(
            file_path=self.context.file_path.as_posix(),
            kind=kind,
            qualified_name=qualified_name,
            signature=signature,
            start_line=source_range.start_line,
            start_column=source_range.start_column,
            end_line=source_range.end_line,
            end_column=source_range.end_column,
            producer=_PRODUCER,
        )
        return CodeSignal(
            signal_id=signal_id,
            chunk_id=chunk.chunk_id,
            file_path=self.context.file_path,
            kind=kind,
            name=name,
            start_line=source_range.start_line,
            end_line=source_range.end_line,
            language="java",
            tokens=tokens,
            metadata=metadata,
            qualified_name=qualified_name,
            signature=signature,
            arity=arity,
            project_unit_key=self.context.project_unit_key,
            producer=_PRODUCER,
            start_column=source_range.start_column,
            end_column=source_range.end_column,
            recallable=True,
        )

    def _remember_declaration(
        self,
        kind: str,
        qualified_name: str,
        signature: str,
        signal: CodeSignal,
    ) -> None:
        self.signals.append(signal)
        self.declarations[(kind, qualified_name, signature)] = signal

    def _add_relation(
        self,
        *,
        source: CodeSignal,
        kind: str,
        target_kind: str,
        target_qualified_name: str,
        target_signature: str,
        target_arity: int | None,
        target_name: str,
        source_range: SourceRange,
        metadata: dict[str, object],
    ) -> None:
        relation_id = generate_v5_relation_id(
            source_signal_id=source.signal_id,
            kind=kind,
            target_kind=target_kind,
            target_qualified_name=target_qualified_name,
            target_signature=target_signature,
            target_arity=target_arity,
            target_project_unit_key=self.context.project_unit_key,
            producer=_PRODUCER,
        )
        occurrence = {
            **metadata,
            "first_source_line": source_range.start_line,
            "first_source_column": source_range.start_column,
            "occurrence_count": 1,
        }
        existing = self.relations.get(relation_id)
        if existing is not None:
            previous = existing.metadata
            current_position = (
                int(occurrence["first_source_line"]),
                int(occurrence["first_source_column"]),
            )
            previous_position = (
                int(previous.get("first_source_line", 0)),
                int(previous.get("first_source_column", 0)),
            )
            selected = occurrence if current_position < previous_position else previous
            combined = dict(selected)
            combined["occurrence_count"] = int(
                previous.get("occurrence_count", 1)
            ) + int(occurrence["occurrence_count"])
            self.relations[relation_id] = replace(existing, metadata=combined)
            return
        self.relations[relation_id] = CodeRelation(
            relation_id=relation_id,
            source_signal_id=source.signal_id,
            target_name=target_name,
            kind=kind,
            confidence=1.0,
            metadata=occurrence,
            target_kind=target_kind,
            target_qualified_name=target_qualified_name,
            target_signature=target_signature,
            target_arity=target_arity,
            target_project_unit_key=self.context.project_unit_key,
            resolution="unresolved",
            producer=_PRODUCER,
            producer_confidence=1.0,
        )


def _symbols(facts: JavaFactSet) -> tuple[SymbolRef, ...]:
    symbols: list[SymbolRef] = []
    for fact in facts.types:
        symbols.append(
            SymbolRef(
                fact.name,
                fact.kind,
                fact.source_range.start_line,
                fact.source_range.end_line,
                "java",
                {"qualified_name": fact.qualified_name},
            )
        )
    for fact in facts.fields:
        symbols.append(
            SymbolRef(
                fact.name,
                fact.kind,
                fact.source_range.start_line,
                fact.source_range.end_line,
                "java",
                {"qualified_name": fact.qualified_name},
            )
        )
    for fact in facts.methods:
        symbols.append(
            SymbolRef(
                fact.declared_name,
                fact.kind,
                fact.source_range.start_line,
                fact.source_range.end_line,
                "java",
                {
                    "qualified_name": fact.qualified_name,
                    "signature": fact.signature,
                },
            )
        )
    symbols.sort(
        key=lambda item: (
            item.start_line,
            item.end_line,
            item.kind,
            item.name,
        )
    )
    return tuple(symbols)


def _parse_metadata(facts: JavaFactSet) -> dict[str, object]:
    metadata: dict[str, object] = {"graph_parse_status": "ast"}
    if facts.package_fact is not None:
        metadata["package"] = facts.package_fact.name
    imports = [fact.qualified_name for fact in facts.imports]
    if imports:
        metadata["imports"] = imports
    omitted: dict[str, int] = {}
    for item in facts.omissions:
        omitted[item.category] = omitted.get(item.category, 0) + item.count
    if omitted:
        metadata["graph_omitted"] = omitted
    return metadata


def _containing_chunk(
    chunks: tuple[DocumentChunk, ...], line: int
) -> DocumentChunk | None:
    return next(
        (chunk for chunk in chunks if chunk.start_line <= line <= chunk.end_line),
        None,
    )


def _selector_name(target: JavaTypeRef) -> str:
    if target.qualified_name:
        return target.qualified_name
    if len(target.candidates) == 1:
        return target.candidates[0]
    return target.erased or target.source


def _selector_qualified_name(target: JavaTypeRef) -> str:
    if target.qualified_name:
        return target.qualified_name
    return target.candidates[0] if target.candidates else ""


def _type_selector_metadata(target: JavaTypeRef) -> dict[str, object]:
    if target.qualified_name and _is_external_java_name(target.qualified_name):
        selector_state = "external"
    else:
        selector_state = "candidates" if target.candidates else "exact"
    return {
        "selector_state": selector_state,
        "candidates": target.candidates,
        "java_type_resolution": target.resolution,
        "target_language": "java",
    }


def _is_external_java_name(qualified_name: str) -> bool:
    return qualified_name.startswith(_EXTERNAL_JAVA_PREFIXES)


def _mapping_paths(annotations: list[JavaAnnotationFact]) -> tuple[str, ...]:
    paths: list[str] = []
    for annotation in annotations:
        if annotation.framework_role != "request_mapping":
            continue
        paths.extend(_annotation_paths(annotation))
    return tuple(dict.fromkeys(paths)) or ("",)


def _annotation_paths(annotation: JavaAnnotationFact) -> tuple[str, ...]:
    paths = tuple(
        literal.value
        for literal in annotation.literals
        if literal.name in {"", "path", "value"}
    )
    return tuple(dict.fromkeys(paths)) or ("",)


def _join_spring_route(parent: str, child: str) -> str:
    if not parent:
        return child
    if not child:
        return parent
    return f"/{parent.strip('/')}/{child.strip('/')}"


def _tokens(*values: str) -> list[str]:
    output: list[str] = []
    for value in values:
        for segment in re.split(r"[^A-Za-z0-9_/-]+", value):
            if not segment:
                continue
            route_value = segment.strip("/")
            if "/" in segment and route_value:
                _append_unique(output, "/" + route_value)
            for piece in re.split(r"[_/-]+", route_value or segment):
                for match in _TOKEN_PART_RE.findall(piece):
                    _append_unique(output, match.lower())
    return output


def _append_unique(values: list[str], value: str) -> None:
    if value and value not in values:
        values.append(value)
