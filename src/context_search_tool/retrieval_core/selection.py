from __future__ import annotations

import sqlite3
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, overload

from context_search_tool import sqlite_store
from context_search_tool.graph_contract import effective_relation_confidence
from context_search_tool.path_roles import classify_path_role
from context_search_tool.models import (
    CodeSignal,
    DocumentChunk,
    EvidenceAnchor,
    RetrievalResult,
    RetrievalSummary,
)
from context_search_tool.retrieval_core import (
    ordering,
    relation_policy,
    types as core_types,
)


_FinalSelectionKind = Literal["result", "evidence_anchor"]
_FinalSelectionReason = Literal[
    "selected_within_result_limit",
    "selected_within_anchor_limit",
]


@dataclass(frozen=True)
class _FinalTraceInput:
    kind: _FinalSelectionKind
    reason: _FinalSelectionReason
    item: core_types._ExpandedResult


@dataclass(frozen=True)
class _FinalTraceDecisions:
    selected: tuple[_FinalTraceInput, ...]
    counts: tuple[tuple[str, int], ...]


_FINAL_TRACE_DECISION_KEYS = (
    "selected_result",
    "selected_anchor",
    "duplicate_anchor",
    "result_limit",
    "anchor_limit",
)


@overload
def split_results_and_anchors(
    expanded: list[core_types._ExpandedResult],
    *,
    final_top_k: int,
    anchor_top_k: int,
    collect_trace: Literal[False] = False,
) -> tuple[list[core_types._ExpandedResult], list[EvidenceAnchor]]: ...


@overload
def split_results_and_anchors(
    expanded: list[core_types._ExpandedResult],
    *,
    final_top_k: int,
    anchor_top_k: int,
    collect_trace: Literal[True],
) -> tuple[
    list[core_types._ExpandedResult],
    list[EvidenceAnchor],
    _FinalTraceDecisions,
]: ...


def split_results_and_anchors(
    expanded: list[core_types._ExpandedResult],
    *,
    final_top_k: int,
    anchor_top_k: int,
    collect_trace: bool = False,
) -> (
    tuple[list[core_types._ExpandedResult], list[EvidenceAnchor]]
    | tuple[
        list[core_types._ExpandedResult],
        list[EvidenceAnchor],
        _FinalTraceDecisions,
    ]
):
    trace_selected: list[_FinalTraceInput] | None = (
        [] if collect_trace else None
    )
    trace_counts: dict[str, int] | None = (
        dict.fromkeys(_FINAL_TRACE_DECISION_KEYS, 0)
        if collect_trace
        else None
    )
    code_results: list[core_types._ExpandedResult] = []
    evidence_anchors: list[EvidenceAnchor] = []
    seen_anchor_keys: set[tuple[str, Path]] = set()

    for item in expanded:
        anchor_kind = _evidence_anchor_kind(item.file_path)
        if anchor_kind:
            anchor_key = (anchor_kind, item.file_path)
            if anchor_key in seen_anchor_keys:
                if trace_counts is not None:
                    trace_counts["duplicate_anchor"] += 1
                continue
            seen_anchor_keys.add(anchor_key)
            if len(evidence_anchors) < anchor_top_k:
                evidence_anchors.append(
                    _evidence_anchor_from_expanded(item, anchor_kind)
                )
                if trace_selected is not None and trace_counts is not None:
                    trace_selected.append(
                        _FinalTraceInput(
                            kind="evidence_anchor",
                            reason="selected_within_anchor_limit",
                            item=item,
                        )
                    )
                    trace_counts["selected_anchor"] += 1
            elif trace_counts is not None:
                trace_counts["anchor_limit"] += 1
            continue

        if len(code_results) < final_top_k:
            code_results.append(item)
            if trace_selected is not None and trace_counts is not None:
                trace_selected.append(
                    _FinalTraceInput(
                        kind="result",
                        reason="selected_within_result_limit",
                        item=item,
                    )
                )
                trace_counts["selected_result"] += 1
        elif trace_counts is not None:
            trace_counts["result_limit"] += 1

    if trace_selected is not None and trace_counts is not None:
        return (
            code_results,
            evidence_anchors,
            _FinalTraceDecisions(
                selected=tuple(trace_selected),
                counts=tuple(
                    (key, trace_counts[key])
                    for key in _FINAL_TRACE_DECISION_KEYS
                ),
            ),
        )
    return code_results, evidence_anchors


def _evidence_anchor_from_expanded(
    item: core_types._ExpandedResult,
    anchor_kind: str,
) -> EvidenceAnchor:
    return EvidenceAnchor(
        file_path=item.file_path,
        start_line=item.start_line,
        end_line=item.end_line,
        content=item.content,
        score=item.rerank_score,
        score_parts={
            **item.score_parts,
            "combined_score": item.score,
            "rerank_score": item.rerank_score,
            "evidence_priority": float(item.evidence_priority),
        },
        reasons=item.reasons,
        anchor_kind=anchor_kind,
        semantic_matches=item.semantic_matches,
        _context_content=item._context_content,
    )


def assemble_query_output(
    store: sqlite_store.SQLiteStore,
    visible_results: list[core_types._ExpandedResult],
    *,
    graph_session: sqlite_store.GraphReadSession | None = None,
    test_intent: bool = False,
) -> tuple[RetrievalSummary, list[RetrievalResult], list[str]]:
    summary, result_reasons = _summarize_results(
        store,
        visible_results,
        graph_session=graph_session,
        test_intent=test_intent,
    )
    results = [
        RetrievalResult(
            file_path=item.file_path,
            start_line=item.start_line,
            end_line=item.end_line,
            content=item.content,
            score=item.rerank_score,
            score_parts={
                **item.score_parts,
                "combined_score": item.score,
                "rerank_score": item.rerank_score,
                "evidence_priority": float(item.evidence_priority),
            },
            reasons=_result_reasons(item.reasons + result_reasons[index]),
            followup_keywords=item.followup_keywords,
            semantic_matches=item.semantic_matches,
            spans=item.spans,
            _context_content=item._context_content,
            _context_role_hint=_context_role_hint(graph_session, item),
        )
        for index, item in enumerate(visible_results)
    ]
    return summary, results, _followup_keywords(results)


def _context_role_hint(
    graph_session: sqlite_store.GraphReadSession | None,
    item: core_types._ExpandedResult,
) -> str | None:
    if graph_session is None:
        return None
    if graph_session.has_accepted_mybatis_statement(item.file_path):
        return "mybatis_repository"
    if (
        graph_session.capability.status != "ready"
        or not graph_session.capability.structured
        or item.file_path.suffix.casefold() != ".java"
    ):
        return None
    if classify_path_role(item.file_path, item.content).basis != "fallback":
        return None

    outgoing_kinds: set[str] = set()
    incoming_kinds: set[str] = set()
    try:
        for chunk_id in item.chunk_ids:
            for signal in graph_session.signals_for_chunk(chunk_id):
                outgoing_kinds.update(
                    relation.kind
                    for relation in graph_session.outgoing_relations(
                        signal.signal_id,
                        limit=relation_policy.MAX_EDGES_PER_SIGNAL_DIRECTION,
                    )
                )
                incoming_kinds.update(
                    relation.kind
                    for relation in graph_session.incoming_relations(
                        signal.signal_id,
                        limit=relation_policy.MAX_EDGES_PER_SIGNAL_DIRECTION,
                    )
                )
    except sqlite3.Error:
        return None

    stem = item.file_path.stem
    if stem.endswith("Mapper") and (
        outgoing_kinds or incoming_kinds
    ):
        return "graph_repository"
    if stem.endswith("Service") and outgoing_kinds.intersection(
        {"implements", "implements_method"}
    ):
        return "graph_service_impl"
    if stem.endswith("Service") and incoming_kinds.intersection(
        {"implements", "implements_method"}
    ):
        return "graph_service_interface"
    if incoming_kinds.intersection({"calls", "uses_type"}):
        return "graph_data_type"
    try:
        for signal in graph_session.type_signals_for_file(item.file_path):
            if any(
                relation.kind == "uses_type"
                for relation in graph_session.incoming_relations(
                    signal.signal_id,
                    limit=relation_policy.MAX_EDGES_PER_SIGNAL_DIRECTION,
                )
            ):
                return "graph_data_type"
    except sqlite3.Error:
        return None
    return None


def _result_reasons(reasons: list[str]) -> list[str]:
    canonical_graph_reasons = {
        reason.lower(): reason
        for reason in relation_policy.GRAPH_REASON_BY_SCORE_KEY.values()
    }
    return [
        canonical_graph_reasons.get(reason, reason)
        for reason in ordering.dedupe_lowered(reasons)
    ]


def _summarize_results(
    store: sqlite_store.SQLiteStore,
    visible_results: list[core_types._ExpandedResult],
    *,
    graph_session: sqlite_store.GraphReadSession | None,
    test_intent: bool,
) -> tuple[RetrievalSummary, list[list[str]]]:
    summary = RetrievalSummary()
    result_reasons: list[list[str]] = []

    for item in visible_results:
        entry_points: list[str] = []
        impl: list[str] = []
        related: list[str] = []
        legacy: list[str] = []
        chunk_reasons: list[str] = []

        for chunk_id in item.chunk_ids:
            if graph_session is None:
                try:
                    chunk = store.chunk_for_id(chunk_id)
                except KeyError:
                    continue
            else:
                chunk = graph_session.chunk_for_id(chunk_id)
            if chunk is None:
                continue
            try:
                signals = (
                    graph_session.signals_for_chunk(chunk_id)
                    if graph_session is not None
                    else store.signals_for_chunk(chunk_id)
                )
            except sqlite3.Error:
                signals = []

            has_endpoint_signal = any(signal.kind == "endpoint" for signal in signals)
            has_usage_signal = any(signal.kind == "usage" for signal in signals)
            protected_direct = (
                graph_session is not None
                and item.evidence_priority == 0
            )
            has_relation_support = not protected_direct and _chunk_has_relation_support(
                store,
                chunk,
                signals,
                graph_session=graph_session,
                test_intent=test_intent,
            )

            (
                chunk_entry,
                chunk_impl,
                chunk_related,
                chunk_legacy,
            ) = _summarize_chunk(chunk, signals, has_relation_support)

            chunk_has_support = (
                has_endpoint_signal or has_usage_signal or has_relation_support
            )
            legacy_names = set(chunk_legacy)
            entry_points.extend(chunk_entry)
            impl.extend(chunk_impl)
            if chunk_has_support:
                related.extend(chunk_related)
            else:
                related.extend([name for name in chunk_related if name not in legacy_names])
                legacy.extend(chunk_legacy)
            chunk_reasons.extend(
                _reasons_for_chunk(
                    signals,
                    chunk_impl,
                    chunk_legacy,
                    has_relation_support,
                    has_endpoint_signal,
                    has_usage_signal,
                )
            )

        result_reasons.append(ordering.dedupe_lowered(chunk_reasons))
        summary.entry_points.extend(entry_points)
        summary.implementation.extend(impl)
        summary.related_types.extend(related)
        summary.possibly_legacy.extend(legacy)

    summary.entry_points = ordering.ordered_unique_preserving_case(summary.entry_points)
    summary.implementation = ordering.ordered_unique_preserving_case(summary.implementation)
    summary.related_types = ordering.ordered_unique_preserving_case(summary.related_types)
    summary.possibly_legacy = ordering.ordered_unique_preserving_case(summary.possibly_legacy)
    summary.entry_points.sort()
    summary.implementation.sort()
    summary.related_types.sort()
    summary.possibly_legacy.sort()
    return summary, result_reasons


def _summarize_chunk(
    chunk: DocumentChunk,
    signals: list,
    has_relation_support: bool,
) -> tuple[list[str], list[str], list[str], list[str]]:
    symbol_names = [symbol.name for symbol in chunk.symbols]
    endpoint: list[str] = []
    implementation: list[str] = []
    related_types: list[str] = []
    legacy: list[str] = []

    endpoint_signals = [signal.name for signal in signals if signal.kind == "endpoint"]
    if endpoint_signals:
        endpoint.extend(ordering.ordered_unique_preserving_case(endpoint_signals))
    elif _is_controller_name(chunk.file_path.stem) or any(
        _is_controller_name(name) for name in symbol_names
    ):
        endpoint.append(_primary_chunk_name(chunk))

    names = ordering.ordered_unique_preserving_case(
        [signal.name for signal in signals] + symbol_names + [_primary_chunk_name(chunk)]
    )
    method_impl_names = [
        name for name in names if _is_implementation_name(name) and "." in name
    ]
    if method_impl_names:
        implementation.extend(method_impl_names)
    else:
        implementation.extend(
            [name for name in names if _is_implementation_name(name) and "." not in name]
        )
    related_types.extend([name for name in names if _is_related_type_name(name)])

    if not endpoint and not has_relation_support and not implementation:
        legacy.extend([name for name in related_types if name])
    if has_relation_support and implementation and not any(
        "." in item for item in implementation
    ):
        implementation.extend([_primary_chunk_name(chunk)])

    return (
        ordering.ordered_unique_preserving_case(endpoint),
        ordering.ordered_unique_preserving_case(implementation),
        ordering.ordered_unique_preserving_case(related_types),
        ordering.ordered_unique_preserving_case(legacy),
    )


def _reasons_for_chunk(
    signals: list,
    impl_names: list[str],
    legacy_names: list[str],
    has_relation_support: bool,
    has_endpoint_signal: bool,
    has_usage_signal: bool,
) -> list[str]:
    reasons: list[str] = []
    if any(signal.kind == "endpoint" for signal in signals):
        reasons.append("endpoint signal match")
    if any(signal.kind == "comment" for signal in signals):
        reasons.append("comment signal match")
    if has_relation_support and impl_names:
        reasons.append("implementation chain match")
    if legacy_names and not has_relation_support and not has_usage_signal and not has_endpoint_signal:
        reasons.append("possibly legacy: no active usage signal found")
    return reasons


def _chunk_has_relation_support(
    store: sqlite_store.SQLiteStore,
    chunk: DocumentChunk,
    signals: list[CodeSignal],
    *,
    graph_session: sqlite_store.GraphReadSession | None,
    test_intent: bool,
) -> bool:
    if graph_session is not None:
        if graph_session.capability.status == "stale":
            return False
        if graph_session.capability.status == "ready":
            for signal in signals:
                for direction, relations in (
                    (
                        "outgoing",
                        graph_session.outgoing_relations(
                            signal.signal_id,
                            limit=relation_policy.MAX_EDGES_PER_SIGNAL_DIRECTION
                            + 1,
                        ),
                    ),
                    (
                        "incoming",
                        graph_session.incoming_relations(
                            signal.signal_id,
                            limit=relation_policy.MAX_EDGES_PER_SIGNAL_DIRECTION
                            + 1,
                        ),
                    ),
                ):
                    if (
                        len(relations)
                        > relation_policy.MAX_EDGES_PER_SIGNAL_DIRECTION
                    ):
                        graph_session.record_graph_truncation()
                        relations = relations[
                            : relation_policy.MAX_EDGES_PER_SIGNAL_DIRECTION
                        ]
                    for relation in relations:
                        neighbor_id = (
                            relation.target_signal_id
                            if direction == "outgoing"
                            else relation.source_signal_id
                        )
                        neighbor = graph_session.signal_for_id(neighbor_id)
                        if (
                            neighbor is None
                            or graph_session.chunk_for_id(neighbor.chunk_id) is None
                        ):
                            graph_session.record_graph_fault("dangling_target")
                            return False
                        try:
                            confidence = effective_relation_confidence(
                                resolution=relation.resolution,
                                target_signal_id=relation.target_signal_id,
                                producer_confidence=relation.producer_confidence,
                                resolution_confidence=(
                                    relation.resolution_confidence
                                ),
                            )
                        except ValueError:
                            graph_session.record_graph_fault(
                                "integrity_check_failed"
                            )
                            return False
                        if confidence < relation_policy._MIN_RELATION_CONFIDENCE:
                            continue
                        policy = relation_policy.RELATION_DIRECTIONS.get(relation.kind)
                        if policy == "intent_gated_both":
                            if test_intent:
                                return True
                        elif (
                            relation_policy.RELATION_WEIGHTS.get(relation.kind)
                            is not None
                            and (policy == "both" or policy == direction)
                        ):
                            return True
            for signal in signals:
                relations = graph_session.legacy_relations_for_source(
                    signal.signal_id,
                    limit=relation_policy.MAX_EDGES_PER_SIGNAL_DIRECTION + 1,
                )
                if len(relations) > relation_policy.MAX_EDGES_PER_SIGNAL_DIRECTION:
                    graph_session.record_graph_truncation()
                    relations = relations[
                        : relation_policy.MAX_EDGES_PER_SIGNAL_DIRECTION
                    ]
                if relations:
                    return True
            relation_targets = ordering.ordered_unique_preserving_case(
                [chunk.file_path.stem] + [signal.name for signal in signals]
            )
            for target_name in relation_targets:
                relations = graph_session.legacy_relations_targeting(
                    target_name,
                    limit=relation_policy.MAX_EDGES_PER_SIGNAL_DIRECTION + 1,
                )
                if len(relations) > relation_policy.MAX_EDGES_PER_SIGNAL_DIRECTION:
                    graph_session.record_graph_truncation()
                    relations = relations[
                        : relation_policy.MAX_EDGES_PER_SIGNAL_DIRECTION
                    ]
                if relations:
                    return True
            return False
        if any(
            graph_session.legacy_relations_for_source(signal.signal_id)
            for signal in signals
        ):
            return True
        relation_targets = ordering.ordered_unique_preserving_case(
            [chunk.file_path.stem] + [signal.name for signal in signals]
        )
        return any(
            graph_session.legacy_relations_targeting(target_name)
            for target_name in relation_targets
        )

    signal_ids = [signal.signal_id for signal in signals]
    for signal_id in signal_ids:
        try:
            if store.relations_for_source(signal_id):
                return True
        except sqlite3.Error:
            continue

    relation_targets = ordering.ordered_unique_preserving_case(
        [chunk.file_path.stem] + [signal.name for signal in signals]
    )
    for target_name in relation_targets:
        try:
            if store.relations_targeting(target_name):
                return True
        except sqlite3.Error:
            continue

    return False


def _primary_chunk_name(chunk: DocumentChunk) -> str:
    if chunk.file_path.stem:
        return chunk.file_path.stem
    return ""


def _is_controller_name(value: str) -> bool:
    return value.lower().endswith("controller")


def _is_implementation_name(value: str) -> bool:
    lowered = value.lower()
    if "." in lowered:
        owner, _ = lowered.split(".", 1)
        if owner.endswith(("serviceimpl", "service", "impl")):
            return True
        return _is_implementation_name(owner)
    return any(
        lowered.endswith(suffix)
        for suffix in (
            "service",
            "serviceimpl",
            "impl",
            "executor",
            "exe",
            "gateway",
            "mapper",
            "repository",
        )
    )


def _is_related_type_name(value: str) -> bool:
    lowered = value.lower()
    return any(
        lowered.endswith(suffix)
        for suffix in (
            "dto",
            "vo",
            "request",
            "response",
            "query",
            "querytype",
            "domain",
            "type",
            "enum",
            "entity",
            "model",
            "bean",
        )
    ) or "domain" in lowered


def _evidence_anchor_kind(path: Path) -> str:
    name = path.name.lower()
    stem = path.stem.lower()
    if path.suffix.lower() == ".md" and stem.startswith("readme"):
        return "readme"
    if path.suffix.lower() == ".md" and stem.startswith("risks"):
        return "risks"
    if name == "pom.xml":
        return "pom"
    return ""


def _followup_keywords(results: list[RetrievalResult]) -> list[str]:
    counts: Counter[str] = Counter()
    for result in results:
        counts.update(token for token in result.followup_keywords if token)
    return [
        token
        for token, _count in sorted(
            counts.items(),
            key=lambda item: (-item[1], item[0]),
        )[:12]
    ]
