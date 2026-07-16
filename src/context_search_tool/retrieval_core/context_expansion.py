from __future__ import annotations

import math
from pathlib import Path

from context_search_tool import chunker
from context_search_tool.config import ToolConfig
from context_search_tool.models import RetrievalSpan
from context_search_tool.retrieval_core import (
    evidence_merge,
    ordering,
    types as core_types,
)


_SPAN_SOURCE_KEYS = (
    "path_symbol",
    "lexical",
    "semantic",
    "planner_semantic",
    "signal",
    "planner_hint",
    "anchor_expansion",
    "relation",
)
_SPAN_SOURCE_SCORE_KEYS = {
    "path_symbol": ("path_symbol",),
    "lexical": ("lexical",),
    "semantic": ("semantic",),
    "planner_semantic": ("planner_semantic",),
    "signal": ("signal",),
    "planner_hint": (
        "planner_hint",
        "planner_lexical",
        "planner_path_symbol",
        "planner_signal",
    ),
    "anchor_expansion": (
        "anchor_expansion",
        "anchored_relation",
        "same_file_anchor",
        "directory_anchor",
    ),
    "relation": ("relation",),
}


def expand_ranked_chunks(
    repo: Path,
    ranked_chunks: list[core_types._RankedChunk],
    config: ToolConfig,
    context_lines: int | None,
    full_file: bool,
) -> list[core_types._ExpandedResult]:
    expanded: list[core_types._ExpandedResult] = []
    for ranked in ranked_chunks:
        source_path = repo / ranked.chunk.file_path
        try:
            file_size = source_path.stat().st_size
            file_content = source_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            file_content = ranked.chunk.content
            file_size = len(file_content.encode("utf-8"))

        lines = file_content.splitlines()
        if full_file and file_size <= config.index.max_full_file_bytes:
            start_line = 1
            end_line = len(lines)
            content = file_content
            context_content = file_content
        else:
            before, after = _context_window(config, context_lines)
            start_line, end_line, content = chunker.expand_lines(
                lines,
                ranked.chunk.start_line,
                ranked.chunk.end_line,
                before,
                after,
            )
            context_content = _join_expanded_result_lines(
                lines[start_line - 1 : end_line]
            )
        if full_file:
            end_line, content = _cap_content_bytes(
                content,
                start_line,
                config.index.max_full_file_bytes,
            )
            _, context_content = _cap_content_bytes(
                context_content,
                start_line,
                config.index.max_full_file_bytes,
            )
            context_content = _context_content_for_range(
                context_content,
                start_line,
                end_line,
            )

        expanded.append(
            core_types._ExpandedResult(
                chunk_ids=[ranked.chunk.chunk_id],
                file_path=ranked.chunk.file_path,
                start_line=start_line,
                end_line=end_line,
                content=content,
                score=ranked.score,
                score_parts=ranked.score_parts,
                reasons=ranked.reasons,
                followup_keywords=ranked.chunk.lexical_tokens,
                rank_tier=ranked.rank_tier,
                rerank_score=ranked.rerank_score,
                evidence_class=ranked.evidence_class,
                evidence_priority=ranked.evidence_priority,
                semantic_matches=ranked.semantic_matches,
                pre_ceiling_rerank_score=ranked.pre_ceiling_rerank_score,
                was_ceiling_clamped=ranked.was_ceiling_clamped,
                spans=_normalize_spans(
                    (
                        RetrievalSpan(
                            start_line=ranked.chunk.start_line,
                            end_line=ranked.chunk.end_line,
                            score=(
                                ranked.rerank_score
                                if math.isfinite(ranked.rerank_score)
                                else 0.0
                            ),
                            sources=_span_sources(ranked.score_parts),
                        ),
                    ),
                    start_line,
                    end_line,
                ),
                _context_content=context_content,
            )
        )

    merged = _merge_overlapping_results(expanded)
    if not full_file:
        return merged
    return [
        _cap_expanded_result(result, config.index.max_full_file_bytes)
        for result in merged
    ]


def _cap_content_bytes(
    content: str,
    start_line: int,
    max_bytes: int,
) -> tuple[int, str]:
    encoded = content.encode("utf-8")
    if len(encoded) <= max_bytes:
        return _end_line_for_content(start_line, content), content
    if max_bytes <= 0:
        return start_line, ""

    trimmed = encoded[:max_bytes].decode("utf-8", errors="ignore")
    return _end_line_for_content(start_line, trimmed), trimmed


def _cap_expanded_result(
    result: core_types._ExpandedResult,
    max_bytes: int,
) -> core_types._ExpandedResult:
    end_line, content = _cap_content_bytes(
        result.content,
        result.start_line,
        max_bytes,
    )
    source_context_content = result._context_content
    if source_context_content is None:
        source_context_content = result.content
    _, context_content = _cap_content_bytes(
        source_context_content,
        result.start_line,
        max_bytes,
    )
    context_content = _context_content_for_range(
        context_content,
        result.start_line,
        end_line,
    )
    return core_types._ExpandedResult(
        chunk_ids=result.chunk_ids,
        file_path=result.file_path,
        start_line=result.start_line,
        end_line=end_line,
        content=content,
        score=result.score,
        score_parts=result.score_parts,
        reasons=result.reasons,
        followup_keywords=result.followup_keywords,
        rank_tier=result.rank_tier,
        rerank_score=result.rerank_score,
        evidence_class=result.evidence_class,
        evidence_priority=result.evidence_priority,
        semantic_matches=result.semantic_matches,
        pre_ceiling_rerank_score=result.pre_ceiling_rerank_score,
        was_ceiling_clamped=result.was_ceiling_clamped,
        spans=_normalize_spans(result.spans, result.start_line, end_line),
        _context_content=context_content,
    )


def _end_line_for_content(start_line: int, content: str) -> int:
    if not content:
        return start_line
    return start_line + max(0, len(content.splitlines()) - 1)


def _merge_overlapping_results(
    results: list[core_types._ExpandedResult],
) -> list[core_types._ExpandedResult]:
    by_file: dict[Path, list[core_types._ExpandedResult]] = {}
    for result in results:
        by_file.setdefault(result.file_path, []).append(result)

    merged: list[core_types._ExpandedResult] = []
    for file_path, file_results in by_file.items():
        sorted_results = sorted(
            file_results,
            key=lambda item: (item.start_line, item.end_line, -item.score),
        )
        current: core_types._ExpandedResult | None = None
        for result in sorted_results:
            if current is None:
                current = result
                continue
            if result.start_line <= current.end_line + 1:
                current = _merge_expanded_result(current, result)
                continue
            merged.append(current)
            current = result
        if current is not None:
            merged.append(current)

    return sorted(
        merged,
        key=_expanded_result_sort_key,
    )


def _expanded_result_sort_key(
    item: core_types._ExpandedResult,
) -> tuple[float, int, int, float, float, float, float, str, int]:
    return (
        -round(item.rerank_score, ordering.RERANK_SORT_DECIMALS),
        item.evidence_priority,
        0 if item.was_ceiling_clamped else 1,
        -(item.pre_ceiling_rerank_score if item.was_ceiling_clamped else 0.0),
        item.score_parts.get("role_priority", 99.0),
        -item.rerank_score,
        -item.score,
        item.file_path.as_posix(),
        item.start_line,
    )


def _merge_expanded_result(
    left: core_types._ExpandedResult,
    right: core_types._ExpandedResult,
) -> core_types._ExpandedResult:
    left_lines = left.content.splitlines()
    right_lines = right.content.splitlines()
    overlap = max(0, left.end_line - right.start_line + 1)
    content_lines = [*left_lines, *right_lines[overlap:]]
    left_context_lines = _expanded_result_lines(left)
    right_context_lines = _expanded_result_lines(right)
    context_lines = [*left_context_lines, *right_context_lines[overlap:]]

    winner = min(left, right, key=_expanded_result_sort_key)

    # Merge score_parts: max for most fields, winner value for rerank-related fields
    merged_score_parts = evidence_merge.merge_score_parts(left.score_parts, right.score_parts)
    merged_score_parts["rerank_score"] = winner.rerank_score
    # evidence_priority is smaller-is-better, so use winner's value
    merged_score_parts["evidence_priority"] = float(winner.evidence_priority)
    for key in (
        "role_priority",
        "role_boost",
        "role_penalty",
        "file_hint_match_boost",
        "role_exact_match_boost",
        "identifier_exact_match_boost",
        "path_role_hint_boost",
        "path_role_mismatch_penalty",
        "impl_match_boost",
        "relation_role_boost",
        "relation_detail_penalty",
        "frontend_import_support_boost",
    ):
        if key in winner.score_parts:
            merged_score_parts[key] = winner.score_parts[key]
        else:
            merged_score_parts.pop(key, None)

    start_line = min(left.start_line, right.start_line)
    end_line = max(left.end_line, right.end_line)
    return core_types._ExpandedResult(
        chunk_ids=ordering.dedupe_lowered([*left.chunk_ids, *right.chunk_ids]),
        file_path=left.file_path,
        start_line=start_line,
        end_line=end_line,
        content="\n".join(content_lines),
        score=max(left.score, right.score),
        score_parts=merged_score_parts,
        reasons=winner.reasons,
        followup_keywords=ordering.dedupe_lowered([*left.followup_keywords, *right.followup_keywords]),
        rank_tier=min(left.rank_tier, right.rank_tier),
        rerank_score=winner.rerank_score,
        evidence_class=winner.evidence_class,
        evidence_priority=winner.evidence_priority,
        semantic_matches=evidence_merge.merge_semantic_matches(
            left.semantic_matches,
            right.semantic_matches,
        ),
        pre_ceiling_rerank_score=winner.pre_ceiling_rerank_score,
        was_ceiling_clamped=winner.was_ceiling_clamped,
        spans=_normalize_spans(
            (*left.spans, *right.spans),
            start_line,
            end_line,
        ),
        _context_content=_join_expanded_result_lines(context_lines),
    )


def _expanded_result_lines(result: core_types._ExpandedResult) -> list[str]:
    expected_count = result.end_line - result.start_line + 1
    content = result._context_content
    if content is None:
        content = result.content
    lines = content.splitlines()
    if not lines:
        lines = [""]
    if len(lines) != expected_count:
        raise ValueError("expanded result content does not match its line range")
    return lines


def _context_content_for_range(content: str, start_line: int, end_line: int) -> str:
    lines = content.splitlines()
    if not lines:
        lines = [""]
    return _join_expanded_result_lines(lines[: end_line - start_line + 1])


def _join_expanded_result_lines(lines: list[str]) -> str:
    content = "\n".join(lines)
    if len(lines) > 1 and lines[-1] == "":
        content += "\n"
    if max(1, len(content.splitlines(keepends=True))) != len(lines):
        raise ValueError("expanded result lines cannot be represented exactly")
    return content


def _span_sources(score_parts: dict[str, float]) -> tuple[str, ...]:
    sources = tuple(
        source
        for source in _SPAN_SOURCE_KEYS
        if any(
            score_parts.get(score_key, 0.0) > 0.0
            for score_key in _SPAN_SOURCE_SCORE_KEYS[source]
        )
    )
    return sources or ("ranked",)


def _normalize_spans(
    spans: tuple[RetrievalSpan, ...],
    start_line: int,
    end_line: int,
) -> tuple[RetrievalSpan, ...]:
    visible_end = max(start_line, end_line)
    normalized: list[RetrievalSpan] = []
    for span in spans:
        span_start = min(max(span.start_line, start_line), visible_end)
        span_end = min(max(span.end_line, span_start), visible_end)
        normalized.append(
            RetrievalSpan(
                start_line=span_start,
                end_line=span_end,
                score=span.score if math.isfinite(span.score) else 0.0,
                sources=span.sources or ("ranked",),
            )
        )

    ordered = sorted(
        normalized,
        key=lambda span: (
            span.start_line,
            span.end_line,
            -span.score,
            span.sources,
        ),
    )
    deduplicated: list[RetrievalSpan] = []
    seen_windows: set[tuple[int, int]] = set()
    for span in ordered:
        window = (span.start_line, span.end_line)
        if window in seen_windows:
            continue
        seen_windows.add(window)
        deduplicated.append(span)
    return tuple(deduplicated)


def _context_window(
    config: ToolConfig,
    context_lines: int | None,
) -> tuple[int, int]:
    if context_lines is not None:
        bounded = max(0, context_lines)
        return bounded, bounded
    return (
        max(0, config.retrieval.context_before_lines),
        max(0, config.retrieval.context_after_lines),
    )
