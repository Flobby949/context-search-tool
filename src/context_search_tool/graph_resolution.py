from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import replace
from typing import Iterator, Protocol

from context_search_tool.graph_contract import effective_relation_confidence
from context_search_tool.models import CodeRelation, CodeSignal


_SAME_UNIT_RELATION_KINDS = frozenset(
    {
        "calls",
        "implements",
        "implements_method",
        "uses_type",
        "imports_type",
        "mapped_by",
        "tests",
    }
)
_JAVA_TARGET_RELATION_KINDS = frozenset(
    {
        "calls",
        "implements",
        "implements_method",
        "uses_type",
        "imports_type",
        "mapped_by",
    }
)


class ResolutionSession(Protocol):
    def relations(
        self,
        *,
        association_only: bool,
    ) -> Iterator[tuple[CodeRelation, CodeSignal]]: ...

    def find_modules(
        self,
        candidates: tuple[str, ...],
        project_unit_key: str,
    ) -> tuple[CodeSignal, ...]: ...

    def find_signals(
        self,
        *,
        project_unit_key: str,
        kind: str,
        qualified_name: str,
        signature: str | None,
        arity: int | None,
        language: str | None,
    ) -> tuple[CodeSignal, ...]: ...

    def update_relation(self, relation: CodeRelation) -> None: ...


class ResolutionStore(Protocol):
    def graph_resolution_session(self) -> AbstractContextManager[ResolutionSession]: ...


def resolve_graph_relations(
    store: ResolutionStore,
    *,
    association_only: bool = False,
) -> int:
    resolved_count = 0
    with store.graph_resolution_session() as session:
        for relation, source in session.relations(
            association_only=association_only,
        ):
            classified = _classify_relation(session, relation, source)
            session.update_relation(classified)
            resolved_count += 1
    return resolved_count


def _classify_relation(
    session: ResolutionSession,
    relation: CodeRelation,
    source: CodeSignal,
) -> CodeRelation:
    cleared = replace(
        relation,
        target_signal_id="",
        resolution="unresolved",
        confidence=relation.producer_confidence,
        resolution_confidence=None,
    )
    if (
        relation.kind in _SAME_UNIT_RELATION_KINDS
        and relation.target_project_unit_key != source.project_unit_key
    ):
        return cleared
    selector_state = relation.metadata.get("selector_state")
    if selector_state == "external":
        return replace(cleared, resolution="external")
    if selector_state in {"escape", "unresolved"}:
        return cleared

    if relation.target_kind == "module":
        candidates = _string_tuple(relation.metadata.get("candidates"))
        if not candidates and relation.target_qualified_name:
            candidates = (relation.target_qualified_name,)
        matches = session.find_modules(
            candidates,
            relation.target_project_unit_key,
        )
        exact = selector_state == "exact"
        exact_confidence = (
            0.95
            if relation.metadata.get("resolution_basis") == "exact_test_path"
            else 1.0
        )
        return _from_matches(
            cleared,
            matches,
            exact=exact,
            exact_confidence=exact_confidence,
        )

    qualified_candidates = _string_tuple(relation.metadata.get("candidates"))
    if not qualified_candidates and relation.target_qualified_name:
        qualified_candidates = (relation.target_qualified_name,)
    if not relation.target_kind or not qualified_candidates:
        return cleared
    language_value = relation.metadata.get("target_language")
    if isinstance(language_value, str):
        language = language_value
    elif relation.kind in _JAVA_TARGET_RELATION_KINDS:
        language = "java"
    else:
        language = None
    if relation.target_signature:
        matches = _find_signal_matches(
            session,
            relation=relation,
            qualified_candidates=qualified_candidates,
            signature=relation.target_signature,
            arity=None,
            language=language,
        )
        return _from_matches(
            cleared,
            matches,
            exact=selector_state != "candidates",
        )

    matches = _find_signal_matches(
        session,
        relation=relation,
        qualified_candidates=qualified_candidates,
        signature=None,
        arity=relation.target_arity,
        language=language,
    )
    basis = relation.metadata.get("resolution_basis")
    if basis == "exact_test_import":
        return _from_matches(cleared, matches, exact=True)
    if basis == "exact_test_path":
        return _from_matches(
            cleared,
            matches,
            exact=True,
            exact_confidence=0.95,
        )
    return _from_matches(cleared, matches, exact=False)


def _find_signal_matches(
    session: ResolutionSession,
    *,
    relation: CodeRelation,
    qualified_candidates: tuple[str, ...],
    signature: str | None,
    arity: int | None,
    language: str | None,
) -> tuple[CodeSignal, ...]:
    matches: dict[str, CodeSignal] = {}
    for qualified_name in dict.fromkeys(qualified_candidates):
        for signal in session.find_signals(
            project_unit_key=relation.target_project_unit_key,
            kind=relation.target_kind,
            qualified_name=qualified_name,
            signature=signature,
            arity=arity,
            language=language,
        ):
            matches[signal.signal_id] = signal
            if len(matches) >= 2:
                return tuple(matches.values())
    return tuple(matches.values())


def _from_matches(
    relation: CodeRelation,
    matches: tuple[CodeSignal, ...],
    *,
    exact: bool,
    exact_confidence: float = 1.0,
) -> CodeRelation:
    if not matches:
        return relation
    if len(matches) > 1:
        return replace(relation, resolution="ambiguous")
    [target] = matches
    resolution = "resolved_exact" if exact else "resolved_unique"
    resolution_confidence = exact_confidence if exact else 0.9
    confidence = effective_relation_confidence(
        resolution=resolution,
        target_signal_id=target.signal_id,
        producer_confidence=relation.producer_confidence,
        resolution_confidence=resolution_confidence,
    )
    return replace(
        relation,
        target_signal_id=target.signal_id,
        resolution=resolution,
        confidence=confidence,
        resolution_confidence=resolution_confidence,
    )


def _string_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(item for item in value if isinstance(item, str) and item)
