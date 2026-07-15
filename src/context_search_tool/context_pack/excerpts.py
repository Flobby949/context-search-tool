"""Pure retrieval-span windowing and byte-safe excerpt construction."""

from __future__ import annotations

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
from context_search_tool.context_pack.needs import (
    candidate_matches_need,
    normalized_subject_match_span,
    normalized_subject_match_spans,
)
from context_search_tool.models import RetrievalSpan


_FAILURE_CODE = "context_failed"
_FAILURE_MESSAGE = "Context pack construction failed"
# Bound user-controlled term/excerpt combinations while keeping a stable frontier.
_MAX_RESERVATION_SLICE_OPTIONS = 256
_MAX_RESERVATION_STATES = 1024


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


@dataclass(frozen=True)
class _SubjectSlice:
    start: int
    end: int
    covered_positions: tuple[int, ...]
    content_bytes: int


@dataclass(frozen=True)
class _ExcerptReservation:
    index: int
    excerpt: ContextExcerpt
    subject_slice: _SubjectSlice


@dataclass(frozen=True)
class _ReservationPlan:
    coverage_mask: int
    content_bytes: int
    reservations: tuple[_ExcerptReservation, ...]


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
        required_terms_by_index: dict[int, tuple[str, ...]] = {}
        for index in priorities:
            excerpt = excerpt_values[index]
            _validate_excerpt(excerpt)
            required_terms_by_index[index] = tuple(
                term
                for term in required_subject_terms
                if _contains_subject(excerpt.content, term)
            )

        plan = _select_required_reservations(
            excerpt_values,
            max_bytes,
            required_subject_terms,
        )
        retained = {
            reservation.index: reservation.excerpt
            for reservation in plan.reservations
        }
        reserved_terms_by_index = {
            reservation.index: tuple(
                required_subject_terms[position]
                for position in reservation.subject_slice.covered_positions
            )
            for reservation in plan.reservations
        }
        remaining = max_bytes - plan.content_bytes
        selected_indexes = set(retained)
        fill_priorities = [
            index for index in priorities if index in selected_indexes
        ] + [index for index in priorities if index not in selected_indexes]

        for index in fill_priorities:
            if remaining <= 0:
                break
            excerpt = excerpt_values[index]
            terms = required_terms_by_index[index]
            retained_bytes = (
                retained[index].content_bytes if index in retained else 0
            )
            fitted = _crop_excerpt(
                excerpt,
                retained_bytes + remaining,
                terms,
            )
            protected_terms = reserved_terms_by_index.get(index, ())
            if protected_terms and not all(
                _contains_subject(fitted.content, term)
                for term in protected_terms
            ):
                fitted = retained[index]
            if (
                selected_indexes
                and index not in selected_indexes
                and terms
                and not _content_has_any(fitted.content, terms)
            ):
                continue
            if fitted.content_bytes == 0:
                continue
            retained[index] = fitted
            remaining += retained_bytes - fitted.content_bytes
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


def _subject_excerpt(
    excerpt: ContextExcerpt,
    selected: _SubjectSlice,
) -> ContextExcerpt:
    start = selected.start
    end = selected.end
    content = excerpt.content[start:end]
    start_line = excerpt.start_line + excerpt.content[:start].count("\n")
    end_line = excerpt.start_line + excerpt.content[: max(start, end - 1)].count(
        "\n"
    )
    return ContextExcerpt(
        start_line=start_line,
        end_line=end_line,
        content=content,
        content_bytes=selected.content_bytes,
        truncated=(
            excerpt.truncated or start > 0 or end < len(excerpt.content)
        ),
    )


def _select_required_reservations(
    excerpt_values: tuple[ContextExcerpt, ...],
    max_bytes: int,
    terms: tuple[str, ...],
) -> _ReservationPlan:
    states = {0: _ReservationPlan(0, 0, ())}
    for index, excerpt in enumerate(excerpt_values):
        options = tuple(
            _ExcerptReservation(
                index=index,
                excerpt=_subject_excerpt(excerpt, selected),
                subject_slice=selected,
            )
            for selected in _required_subject_slices(
                excerpt.content,
                max_bytes,
                terms,
            )
        )
        next_states = dict(states)
        for plan in tuple(states.values()):
            for option in options:
                option_mask = sum(
                    1 << position
                    for position in option.subject_slice.covered_positions
                )
                coverage_mask = plan.coverage_mask | option_mask
                if coverage_mask == plan.coverage_mask:
                    continue
                content_bytes = plan.content_bytes + option.excerpt.content_bytes
                if content_bytes > max_bytes:
                    continue
                candidate = _ReservationPlan(
                    coverage_mask=coverage_mask,
                    content_bytes=content_bytes,
                    reservations=(*plan.reservations, option),
                )
                existing = next_states.get(coverage_mask)
                if existing is None or _same_coverage_plan_rank(
                    candidate
                ) < _same_coverage_plan_rank(existing):
                    next_states[coverage_mask] = candidate
                if len(next_states) >= _MAX_RESERVATION_STATES * 2:
                    next_states = _prune_reservation_states(next_states.values())
        states = _prune_reservation_states(next_states.values())

    return min(states.values(), key=_reservation_plan_rank)


def _prune_reservation_states(
    plans: Iterable[_ReservationPlan],
) -> dict[int, _ReservationPlan]:
    ranked = sorted(plans, key=_reservation_plan_rank)
    retained: list[_ReservationPlan] = []
    for plan in ranked:
        if any(
            (existing.coverage_mask | plan.coverage_mask)
            == existing.coverage_mask
            and _same_coverage_plan_rank(existing)
            <= _same_coverage_plan_rank(plan)
            for existing in retained
        ):
            continue
        retained.append(plan)
        if len(retained) >= _MAX_RESERVATION_STATES:
            break
    return {plan.coverage_mask: plan for plan in retained}


def _same_coverage_plan_rank(plan: _ReservationPlan) -> tuple[object, ...]:
    return (
        plan.content_bytes,
        _reservation_fragment_rank(plan),
        _reservation_source_rank(plan),
    )


def _reservation_plan_rank(plan: _ReservationPlan) -> tuple[object, ...]:
    covered_positions = tuple(
        position
        for position in range(plan.coverage_mask.bit_length())
        if plan.coverage_mask & (1 << position)
    )
    return (
        -len(covered_positions),
        covered_positions,
        plan.content_bytes,
        _reservation_fragment_rank(plan),
        _reservation_source_rank(plan),
    )


def _reservation_fragment_rank(plan: _ReservationPlan) -> tuple[int, int]:
    return (
        sum(reservation.excerpt.truncated for reservation in plan.reservations),
        len(plan.reservations),
    )


def _reservation_source_rank(
    plan: _ReservationPlan,
) -> tuple[tuple[int, int, int], ...]:
    return tuple(
        (
            reservation.index,
            reservation.subject_slice.start,
            reservation.subject_slice.end,
        )
        for reservation in plan.reservations
    )


def _required_subject_slice(
    content: str,
    max_bytes: int,
    terms: tuple[str, ...],
) -> tuple[int, int, tuple[str, ...]] | None:
    options = _required_subject_slices(content, max_bytes, terms)
    if not options:
        return None
    selected = options[0]
    return (
        selected.start,
        selected.end,
        tuple(terms[position] for position in selected.covered_positions),
    )


def _required_subject_slices(
    content: str,
    max_bytes: int,
    terms: tuple[str, ...],
) -> tuple[_SubjectSlice, ...]:
    spans: list[tuple[int, int, int]] = []
    matches_by_term: dict[str, tuple[tuple[int, int], ...]] = {}
    for position, term in enumerate(terms):
        match_spans = matches_by_term.get(term)
        if match_spans is None:
            match_spans = _normalized_match_spans(content, term)
            matches_by_term[term] = match_spans
        spans.extend(
            (*match_span, position)
            for match_span in match_spans
        )
    if not spans or max_bytes <= 0:
        return ()

    ordered = sorted(spans, key=lambda span: (span[0], span[1], span[2]))
    byte_offsets = [0]
    for character in content:
        byte_offsets.append(
            byte_offsets[-1] + len(character.encode("utf-8"))
        )

    best_by_coverage: dict[tuple[int, ...], _SubjectSlice] = {}
    for left in range(len(ordered)):
        start = ordered[left][0]
        end = ordered[left][1]
        covered: set[int] = set()
        for right in range(left, len(ordered)):
            end = max(end, ordered[right][1])
            slice_bytes = byte_offsets[end] - byte_offsets[start]
            if slice_bytes > max_bytes:
                break
            covered.add(ordered[right][2])
            covered_positions = tuple(sorted(covered))
            candidate = _SubjectSlice(
                start=start,
                end=end,
                covered_positions=covered_positions,
                content_bytes=slice_bytes,
            )
            existing = best_by_coverage.get(covered_positions)
            if existing is None or _same_coverage_slice_rank(
                candidate
            ) < _same_coverage_slice_rank(existing):
                best_by_coverage[covered_positions] = candidate
            if len(best_by_coverage) >= _MAX_RESERVATION_SLICE_OPTIONS * 2:
                best_by_coverage = _prune_subject_slices(
                    best_by_coverage.values()
                )

    return tuple(_prune_subject_slices(best_by_coverage.values()).values())


def _prune_subject_slices(
    slices: Iterable[_SubjectSlice],
) -> dict[tuple[int, ...], _SubjectSlice]:
    retained = sorted(slices, key=_subject_slice_rank)[
        :_MAX_RESERVATION_SLICE_OPTIONS
    ]
    return {selected.covered_positions: selected for selected in retained}


def _same_coverage_slice_rank(selected: _SubjectSlice) -> tuple[int, int, int]:
    return selected.content_bytes, selected.start, selected.end


def _subject_slice_rank(selected: _SubjectSlice) -> tuple[object, ...]:
    return (
        -len(selected.covered_positions),
        selected.covered_positions,
        selected.content_bytes,
        selected.start,
        selected.end,
    )


def _normalized_match_spans(
    content: str,
    subject: str,
) -> tuple[tuple[int, int], ...]:
    normalized_spans = normalized_subject_match_spans(content, subject)
    if content.isascii() or not normalized_spans:
        return normalized_spans
    boundaries = _raw_offset_map(content, normalized_spans)
    return tuple(
        (boundaries[start], boundaries[end]) for start, end in normalized_spans
    )


def _crop_text(
    content: str,
    max_bytes: int,
    required_terms: tuple[str, ...],
) -> str:
    if max_bytes <= 0:
        return ""
    selected = _required_subject_slice(content, max_bytes, required_terms)
    if selected is not None:
        start, _, _ = selected
        return _utf8_prefix(content[start:], max_bytes)
    return _utf8_prefix(content, max_bytes)


def _raw_offset_map(
    content: str,
    normalized_spans: tuple[tuple[int, int], ...],
) -> dict[int, int]:
    offsets = {offset for span in normalized_spans for offset in span}
    if unicodedata.is_normalized("NFC", content):
        last_offset = max(offsets)
        boundaries = [0] * (last_offset + 1)
        folded_offset = 0
        for index, character in enumerate(content):
            if folded_offset > last_offset:
                break
            next_offset = folded_offset + len(character.casefold())
            fill_end = min(next_offset, last_offset + 1)
            boundaries[folded_offset:fill_end] = [index] * (
                fill_end - folded_offset
            )
            folded_offset = next_offset
            if folded_offset <= last_offset:
                boundaries[folded_offset] = index + 1
        return {offset: boundaries[offset] for offset in offsets}

    def original_boundary(normalized_offset: int) -> int:
        boundary = 0
        low = 0
        high = len(content)
        while low <= high:
            index = (low + high) // 2
            prefix_length = len(
                unicodedata.normalize("NFC", content[:index]).casefold()
            )
            if prefix_length <= normalized_offset:
                boundary = index
                low = index + 1
            else:
                high = index - 1
        return boundary

    return {offset: original_boundary(offset) for offset in offsets}


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
    return normalized_subject_match_span(content, subject) is not None


def _fail() -> NoReturn:
    raise ContextPackError(_FAILURE_CODE, _FAILURE_MESSAGE)


__all__ = (
    "ContextExcerpt",
    "ExcerptWindow",
    "build_candidate_excerpts",
    "fit_excerpts_to_bytes",
    "normalize_candidate_spans",
)
