from __future__ import annotations

import sqlite3
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, overload

from context_search_tool import sqlite_store
from context_search_tool.models import (
    CodeSignal,
    DocumentChunk,
    EvidenceAnchor,
    RetrievalResult,
    RetrievalSummary,
)
from context_search_tool.retrieval_core import ordering, types as core_types


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
) -> tuple[RetrievalSummary, list[RetrievalResult], list[str]]:
    summary, result_reasons = _summarize_results(store, visible_results)
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
            reasons=ordering.dedupe_lowered(item.reasons + result_reasons[index]),
            followup_keywords=item.followup_keywords,
            semantic_matches=item.semantic_matches,
            spans=item.spans,
            _context_content=item._context_content,
        )
        for index, item in enumerate(visible_results)
    ]
    return summary, results, _followup_keywords(results)


def _summarize_results(
    store: sqlite_store.SQLiteStore,
    visible_results: list[core_types._ExpandedResult],
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
            try:
                chunk = store.chunk_for_id(chunk_id)
            except KeyError:
                continue
            try:
                signals = store.signals_for_chunk(chunk_id)
            except sqlite3.Error:
                signals = []

            has_endpoint_signal = any(signal.kind == "endpoint" for signal in signals)
            has_usage_signal = any(signal.kind == "usage" for signal in signals)
            has_relation_support = _chunk_has_relation_support(store, chunk, signals)

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
) -> bool:
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
