"""Pure retrieval-span windowing and byte-safe excerpt construction."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from math import isfinite
from typing import Iterable, NoReturn

from context_search_tool.context_pack.models import (
    ContextCandidate,
    ContextExcerpt,
    ContextPackError,
    ContextPackOptions,
    EvidenceNeed,
    ExcerptWindow,
)
from context_search_tool.context_pack.needs import candidate_matches_need
from context_search_tool.models import RetrievalSpan


_FAILURE_CODE = "context_failed"
_FAILURE_MESSAGE = "Context pack construction failed"


@dataclass(frozen=True)
class _SourceLine:
    number: int
    content: str


@dataclass(frozen=True)
class _SourceView:
    start_line: int
    end_line: int
    lines: tuple[_SourceLine, ...]

    def content(self, start_line: int, end_line: int) -> str:
        start_index = start_line - self.start_line
        end_index = end_line - self.start_line + 1
        return "".join(line.content for line in self.lines[start_index:end_index])


def normalize_candidate_spans(
    candidate: ContextCandidate,
) -> tuple[RetrievalSpan, ...]:
    """Validate and coalesce only exact duplicate retrieval spans."""
    try:
        _source_view(candidate)
        if candidate.source_kind == "evidence_anchor" and not candidate.spans:
            return ()
        if not candidate.spans:
            score = candidate.relevance_score or 0.0
            if not isfinite(score):
                _fail()
            return (
                RetrievalSpan(
                    start_line=candidate.start_line,
                    end_line=candidate.end_line,
                    score=float(score),
                    sources=("legacy_result",),
                ),
            )

        normalized: list[RetrievalSpan] = []
        positions: dict[tuple[int, int], int] = {}
        for span in candidate.spans:
            _validate_span(span, candidate)
            key = (span.start_line, span.end_line)
            existing_position = positions.get(key)
            if existing_position is None:
                positions[key] = len(normalized)
                normalized.append(span)
                continue
            existing = normalized[existing_position]
            sources = _ordered_union(existing.sources, span.sources)
            normalized[existing_position] = RetrievalSpan(
                start_line=span.start_line,
                end_line=span.end_line,
                score=max(existing.score, span.score),
                sources=sources,
            )
        return tuple(normalized)
    except ContextPackError:
        raise
    except Exception:
        _fail()


def build_candidate_excerpts(
    *,
    candidate: ContextCandidate,
    needs: tuple[EvidenceNeed, ...] | Iterable[EvidenceNeed],
    options: ContextPackOptions,
) -> tuple[ContextExcerpt, ...]:
    """Build ranked, bounded excerpts without repository or store access."""
    try:
        view = _source_view(candidate)
        normalized_needs = tuple(needs)
        _validate_excerpt_options(options)
        if options.max_excerpts_per_item <= 0:
            return ()

        windows = _candidate_windows(candidate, normalized_needs, view, options)
        ranked = sorted(windows, key=_window_rank)
        selected = ranked[: options.max_excerpts_per_item]
        selected.sort(key=lambda window: (window.start_line, window.end_line))

        built: list[ContextExcerpt] = []
        needs_by_id = {need.id: need for need in normalized_needs}
        for window in selected:
            required_terms = tuple(
                term
                for need_id in window.required_need_ids
                for term in needs_by_id[need_id].subject_terms
            )
            built.append(
                _render_window(
                    view,
                    window,
                    options.max_excerpt_bytes,
                    required_terms,
                )
            )
        return tuple(built)
    except ContextPackError:
        raise
    except Exception:
        _fail()


def fit_excerpts_to_bytes(
    excerpt_values: tuple[ContextExcerpt, ...],
    max_bytes: int,
    *,
    required_subject_terms: tuple[str, ...] = (),
    recommended_subject_terms: tuple[str, ...] = (),
) -> tuple[ContextExcerpt, ...]:
    """Fit existing excerpts to an item allocation, preserving useful lines."""
    try:
        if type(excerpt_values) is not tuple or type(max_bytes) is not int:
            _fail()
        if max_bytes <= 0:
            return ()
        priorities = sorted(
            range(len(excerpt_values)),
            key=lambda index: (
                0
                if _content_has_any(
                    excerpt_values[index].content,
                    required_subject_terms,
                )
                else 1,
                0
                if _content_has_any(
                    excerpt_values[index].content,
                    recommended_subject_terms,
                )
                else 1,
                index,
            ),
        )
        remaining = max_bytes
        retained: dict[int, ContextExcerpt] = {}
        for index in priorities:
            if remaining <= 0:
                break
            excerpt = excerpt_values[index]
            _validate_excerpt(excerpt)
            terms = (
                required_subject_terms
                if _content_has_any(excerpt.content, required_subject_terms)
                else ()
            )
            fitted = _crop_excerpt(excerpt, remaining, terms)
            if fitted.content_bytes == 0:
                continue
            retained[index] = fitted
            remaining -= fitted.content_bytes
        return tuple(retained[index] for index in sorted(retained))
    except ContextPackError:
        raise
    except Exception:
        _fail()


def _candidate_windows(
    candidate: ContextCandidate,
    needs: tuple[EvidenceNeed, ...],
    view: _SourceView,
    options: ContextPackOptions,
) -> list[ExcerptWindow]:
    if candidate.source_kind == "evidence_anchor" and not candidate.spans:
        raw_windows = _anchor_windows(candidate, needs, view, options)
    else:
        raw_windows = []
        for span in normalize_candidate_spans(candidate):
            content = view.content(span.start_line, span.end_line)
            matched = tuple(
                need
                for need in needs
                if candidate_matches_need(candidate, need, content=content)
            )
            raw_windows.append(
                ExcerptWindow(
                    start_line=max(
                        view.start_line,
                        span.start_line - options.context_before_lines,
                    ),
                    end_line=min(
                        view.end_line,
                        span.end_line + options.context_after_lines,
                    ),
                    required_need_ids=tuple(
                        need.id for need in matched if need.required
                    ),
                    recommended_need_ids=tuple(
                        need.id for need in matched if not need.required
                    ),
                    score=span.score,
                    protected_direct=candidate.protected_direct,
                )
            )
    return _merge_windows(raw_windows)


def _anchor_windows(
    candidate: ContextCandidate,
    needs: tuple[EvidenceNeed, ...],
    view: _SourceView,
    options: ContextPackOptions,
) -> list[ExcerptWindow]:
    if len(candidate.content.encode("utf-8")) <= options.max_excerpt_bytes:
        matched = tuple(
            need
            for need in needs
            if candidate_matches_need(candidate, need, content=candidate.content)
        )
        return [
            ExcerptWindow(
                start_line=view.start_line,
                end_line=view.end_line,
                required_need_ids=tuple(
                    need.id for need in matched if need.required
                ),
                recommended_need_ids=tuple(
                    need.id for need in matched if not need.required
                ),
                score=0.0,
                protected_direct=False,
            )
        ]
    matching: list[tuple[int, EvidenceNeed]] = []
    for need in needs:
        if need.category != candidate.group:
            continue
        for line in view.lines:
            if not need.subject_terms:
                matching.append((line.number, need))
                break
            if all(_contains_subject(line.content, term) for term in need.subject_terms):
                matching.append((line.number, need))
                break
    if matching:
        first_line = min(line for line, _ in matching)
        matched = tuple(need for line, need in matching if line == first_line)
    else:
        first_line = view.start_line
        matched = ()
    return [
        ExcerptWindow(
            start_line=max(view.start_line, first_line - options.context_before_lines),
            end_line=min(view.end_line, first_line + options.context_after_lines),
            required_need_ids=tuple(need.id for need in matched if need.required),
            recommended_need_ids=tuple(
                need.id for need in matched if not need.required
            ),
            score=0.0,
            protected_direct=False,
        )
    ]


def _merge_windows(windows: list[ExcerptWindow]) -> list[ExcerptWindow]:
    if not windows:
        return []
    ordered = sorted(windows, key=lambda item: (item.start_line, item.end_line))
    merged: list[ExcerptWindow] = []
    for window in ordered:
        if not merged or window.start_line > merged[-1].end_line + 1:
            merged.append(window)
            continue
        previous = merged[-1]
        merged[-1] = ExcerptWindow(
            start_line=previous.start_line,
            end_line=max(previous.end_line, window.end_line),
            required_need_ids=_ordered_union(
                previous.required_need_ids,
                window.required_need_ids,
            ),
            recommended_need_ids=_ordered_union(
                previous.recommended_need_ids,
                window.recommended_need_ids,
            ),
            score=max(previous.score, window.score),
            protected_direct=previous.protected_direct or window.protected_direct,
        )
    return merged


def _window_rank(window: ExcerptWindow) -> tuple[object, ...]:
    return (
        0 if window.required_need_ids else 1,
        0 if window.recommended_need_ids else 1,
        0 if window.protected_direct else 1,
        -window.score,
        window.start_line,
        window.end_line,
    )


def _render_window(
    view: _SourceView,
    window: ExcerptWindow,
    max_bytes: int,
    required_terms: tuple[str, ...],
) -> ContextExcerpt:
    lines = list(
        view.lines[
            window.start_line - view.start_line :
            window.end_line - view.start_line + 1
        ]
    )
    original_content = "".join(line.content for line in lines)
    original_size = len(original_content.encode("utf-8"))
    required_lines = {
        line.number
        for line in lines
        if _content_has_any(line.content, required_terms)
    }

    while len(lines) > 1 and _line_bytes(lines) > max_bytes:
        if lines[-1].number not in required_lines:
            lines.pop()
        elif lines[0].number not in required_lines:
            lines.pop(0)
        else:
            lines.pop()

    start_line = lines[0].number
    end_line = lines[-1].number
    content = "".join(line.content for line in lines)
    if len(content.encode("utf-8")) > max_bytes:
        content = _crop_text(content, max_bytes, required_terms)
    content_bytes = len(content.encode("utf-8"))
    return ContextExcerpt(
        start_line=start_line,
        end_line=end_line,
        content=content,
        content_bytes=content_bytes,
        truncated=content_bytes < original_size,
    )


def _crop_excerpt(
    excerpt: ContextExcerpt,
    max_bytes: int,
    required_terms: tuple[str, ...],
) -> ContextExcerpt:
    if excerpt.content_bytes <= max_bytes:
        return excerpt
    content_lines = excerpt.content.splitlines(keepends=True)
    if not content_lines:
        content_lines = [""]
    end_line = excerpt.start_line + len(content_lines) - 1
    view = _SourceView(
        start_line=excerpt.start_line,
        end_line=end_line,
        lines=tuple(
            _SourceLine(excerpt.start_line + index, content)
            for index, content in enumerate(content_lines)
        ),
    )
    window = ExcerptWindow(
        start_line=excerpt.start_line,
        end_line=end_line,
        required_need_ids=(),
        recommended_need_ids=(),
        score=0.0,
        protected_direct=False,
    )
    cropped = _render_window(view, window, max_bytes, required_terms)
    return ContextExcerpt(
        start_line=cropped.start_line,
        end_line=cropped.end_line,
        content=cropped.content,
        content_bytes=cropped.content_bytes,
        truncated=True,
    )


def _crop_text(
    content: str,
    max_bytes: int,
    required_terms: tuple[str, ...],
) -> str:
    if max_bytes <= 0:
        return ""
    for term in required_terms:
        match_span = _normalized_match_span(content, term)
        if match_span is None:
            continue
        start, end = match_span
        suffix = content[start:]
        if len(content[start:end].encode("utf-8")) <= max_bytes:
            return _utf8_prefix(suffix, max_bytes)
    return _utf8_prefix(content, max_bytes)


def _normalized_match_span(content: str, subject: str) -> tuple[int, int] | None:
    normalized_content = unicodedata.normalize("NFKC", content).casefold()
    normalized_subject = unicodedata.normalize("NFKC", subject).casefold()
    normalized_start = normalized_content.find(normalized_subject)
    if not normalized_subject or normalized_start < 0:
        return None
    normalized_end = normalized_start + len(normalized_subject)

    def original_boundary(normalized_offset: int) -> int:
        boundary = 0
        low = 0
        high = len(content)
        while low <= high:
            index = (low + high) // 2
            prefix_length = len(
                unicodedata.normalize("NFKC", content[:index]).casefold()
            )
            if prefix_length <= normalized_offset:
                boundary = index
                low = index + 1
            else:
                high = index - 1
        return boundary

    return (
        original_boundary(normalized_start),
        original_boundary(normalized_end),
    )


def _utf8_prefix(content: str, max_bytes: int) -> str:
    return content.encode("utf-8")[:max_bytes].decode("utf-8", errors="ignore")


def _source_view(candidate: ContextCandidate) -> _SourceView:
    if type(candidate) is not ContextCandidate:
        _fail()
    if (
        type(candidate.start_line) is not int
        or type(candidate.end_line) is not int
        or candidate.start_line <= 0
        or candidate.end_line < candidate.start_line
        or type(candidate.content) is not str
    ):
        _fail()
    parts = candidate.content.splitlines(keepends=True)
    if not parts:
        parts = [""]
    calculated_end = candidate.start_line + len(parts) - 1
    if calculated_end != candidate.end_line:
        _fail()
    return _SourceView(
        start_line=candidate.start_line,
        end_line=candidate.end_line,
        lines=tuple(
            _SourceLine(candidate.start_line + index, content)
            for index, content in enumerate(parts)
        ),
    )


def _validate_span(span: RetrievalSpan, candidate: ContextCandidate) -> None:
    if (
        type(span) is not RetrievalSpan
        or type(span.start_line) is not int
        or type(span.end_line) is not int
        or span.start_line < candidate.start_line
        or span.end_line > candidate.end_line
        or span.end_line < span.start_line
        or type(span.score) not in (int, float)
        or isinstance(span.score, bool)
        or not isfinite(span.score)
        or type(span.sources) is not tuple
        or not span.sources
        or any(type(source) is not str or not source for source in span.sources)
    ):
        _fail()


def _validate_excerpt_options(options: ContextPackOptions) -> None:
    if (
        type(options) is not ContextPackOptions
        or type(options.max_excerpts_per_item) is not int
        or options.max_excerpts_per_item <= 0
        or type(options.max_excerpt_bytes) is not int
        or options.max_excerpt_bytes <= 0
        or type(options.context_before_lines) is not int
        or options.context_before_lines < 0
        or type(options.context_after_lines) is not int
        or options.context_after_lines < 0
    ):
        _fail()


def _validate_excerpt(excerpt: ContextExcerpt) -> None:
    if (
        type(excerpt) is not ContextExcerpt
        or excerpt.end_line < excerpt.start_line
        or excerpt.content_bytes != len(excerpt.content.encode("utf-8"))
    ):
        _fail()


def _line_bytes(lines: list[_SourceLine]) -> int:
    return sum(len(line.content.encode("utf-8")) for line in lines)


def _ordered_union(left: tuple[str, ...], right: tuple[str, ...]) -> tuple[str, ...]:
    values: list[str] = []
    for value in (*left, *right):
        if value not in values:
            values.append(value)
    return tuple(values)


def _content_has_any(content: str, terms: tuple[str, ...]) -> bool:
    return any(_contains_subject(content, term) for term in terms)


def _contains_subject(content: str, subject: str) -> bool:
    normalized_content = unicodedata.normalize("NFKC", content).casefold()
    normalized_subject = unicodedata.normalize("NFKC", subject).casefold().strip()
    if not normalized_subject:
        return False
    if any("\u3400" <= character <= "\u9fff" for character in normalized_subject):
        return normalized_subject in normalized_content
    escaped = re.escape(normalized_subject).replace(r"\ ", r"\s+")
    return re.search(
        rf"(?<![A-Za-z0-9]){escaped}(?![A-Za-z0-9])",
        normalized_content,
    ) is not None


def _fail() -> NoReturn:
    raise ContextPackError(_FAILURE_CODE, _FAILURE_MESSAGE)


__all__ = (
    "ContextExcerpt",
    "ExcerptWindow",
    "build_candidate_excerpts",
    "fit_excerpts_to_bytes",
    "normalize_candidate_spans",
)
