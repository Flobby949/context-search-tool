from __future__ import annotations

from dataclasses import dataclass, replace
from math import isfinite
from numbers import Real
from typing import TYPE_CHECKING, Iterable, NoReturn

from context_search_tool.config import ToolConfig
from context_search_tool.context_pack import serialization
from context_search_tool.context_pack.excerpts import (
    build_candidate_excerpts,
    fit_excerpts_to_bytes,
    normalize_candidate_spans,
)
from context_search_tool.context_pack.models import (
    CONTEXT_GROUPS,
    CONTEXT_PACK_SCHEMA_VERSION,
    ContextBudget,
    ContextCandidate,
    ContextExcerpt,
    ContextItem,
    ContextPack,
    ContextPackError,
    ContextPackOptions,
    EvidenceNeed,
    Omission,
    ReadinessConfidence,
)
from context_search_tool.context_pack.needs import (
    candidate_matches_need,
    derive_evidence_needs,
    derive_missing_evidence,
    derive_next_queries,
    derive_readiness_confidence,
    retained_item_matches_need,
)
from context_search_tool.context_pack.roles import normalize_candidates

if TYPE_CHECKING:
    from context_search_tool.retrieval import QueryBundle


_CONTEXT_FIELDS = (
    "max_items",
    "max_excerpts_per_item",
    "max_excerpt_bytes",
    "max_item_content_bytes",
    "max_total_content_bytes",
    "max_pack_bytes",
)
_FAILURE_CODE = "context_failed"
_FAILURE_MESSAGE = "Context pack construction failed"
_OMISSION_REASON = "lower priority than selected evidence under the context budget"
_MIN_EVIDENCE_BYTES = 512


@dataclass(frozen=True)
class _SelectedCandidate:
    candidate: ContextCandidate
    matched_need_ids: tuple[str, ...]
    selection_priority: tuple[object, ...]
    preferred_excerpts: tuple[ContextExcerpt, ...]
    excerpts: tuple[ContextExcerpt, ...]


def resolve_context_pack_options(
    config: ToolConfig,
    *,
    context_lines: int | None,
    max_evidence_anchors: int,
    max_items: int | None = None,
    max_pack_bytes: int | None = None,
) -> ContextPackOptions:
    """Resolve validated request ceilings against configured context limits."""
    context = config.context
    for field_name in _CONTEXT_FIELDS:
        value = getattr(context, field_name)
        if type(value) is not int or value <= 0:
            _invalid(f"context.{field_name} must be a positive integer")

    if context.max_excerpt_bytes > context.max_item_content_bytes:
        _invalid(
            "context.max_excerpt_bytes must not exceed max_item_content_bytes"
        )
    if context.max_item_content_bytes > context.max_total_content_bytes:
        _invalid(
            "context.max_item_content_bytes must not exceed "
            "max_total_content_bytes"
        )
    if context.max_total_content_bytes >= context.max_pack_bytes:
        _invalid("context.max_total_content_bytes must be less than max_pack_bytes")

    if max_items is not None and (type(max_items) is not int or max_items <= 0):
        _invalid("max_items must be a positive integer")
    if max_pack_bytes is not None and (
        type(max_pack_bytes) is not int or max_pack_bytes < 4096
    ):
        _invalid("max_context_bytes must be an integer of at least 4096 bytes")
    if type(max_evidence_anchors) is not int or max_evidence_anchors < 0:
        _invalid("max_evidence_anchors must be a non-negative integer")

    effective_pack_bytes = (
        context.max_pack_bytes if max_pack_bytes is None else max_pack_bytes
    )
    effective_total_bytes = min(
        context.max_total_content_bytes,
        effective_pack_bytes - 1,
    )
    effective_item_bytes = min(
        context.max_item_content_bytes,
        effective_total_bytes,
    )
    effective_excerpt_bytes = min(
        context.max_excerpt_bytes,
        effective_item_bytes,
    )
    requested_max_items = context.max_items if max_items is None else max_items
    raw_candidate_cap = max(
        0,
        config.retrieval.final_top_k + max_evidence_anchors,
    )

    if context_lines is None:
        context_before_lines = max(0, config.retrieval.context_before_lines)
        context_after_lines = max(0, config.retrieval.context_after_lines)
    else:
        effective_context_lines = max(0, context_lines)
        context_before_lines = effective_context_lines
        context_after_lines = effective_context_lines

    return ContextPackOptions(
        max_items=min(
            context.max_items,
            requested_max_items,
            raw_candidate_cap,
        ),
        max_excerpts_per_item=context.max_excerpts_per_item,
        max_excerpt_bytes=effective_excerpt_bytes,
        max_item_content_bytes=effective_item_bytes,
        max_total_content_bytes=effective_total_bytes,
        max_pack_bytes=effective_pack_bytes,
        context_before_lines=context_before_lines,
        context_after_lines=context_after_lines,
    )


def build_context_pack(
    bundle: QueryBundle,
    options: ContextPackOptions,
) -> ContextPack:
    """Build one deterministic, I/O-free, hard-bounded ContextPack v2."""
    try:
        _validate_build_options(options)
        candidates = normalize_candidates(bundle)
        _validate_candidates(candidates)
        needs = derive_evidence_needs(bundle, candidates=candidates)
        full_matches = _full_candidate_matches(candidates, needs)
        blocked_matches: set[tuple[str, str]] = set()

        for _ in range(len(candidates) + 1):
            selected_candidates = _select_candidates(
                candidates,
                needs,
                full_matches,
                blocked_matches,
                options.max_items,
            )
            selected = _build_and_allocate_excerpts(
                selected_candidates,
                needs,
                options,
            )
            pack = _materialize_pack(
                candidates,
                selected,
                needs,
                full_matches,
                options,
            )
            compaction_state = {
                item.candidate.file_path: item for item in selected
            }
            omission_preview_limit = options.max_items
            pack = _relink_retained_matches(pack, candidates, needs)
            pack = _derive_final_outputs(
                pack,
                bundle,
                candidates,
                needs,
                full_matches,
                omission_preview_limit,
            )
            pack, omission_preview_limit = _compact_pack(
                pack,
                bundle,
                candidates,
                needs,
                full_matches,
                options,
                compaction_state,
                omission_preview_limit,
            )
            pack = _relink_retained_matches(pack, candidates, needs)
            pack = _derive_final_outputs(
                pack,
                bundle,
                candidates,
                needs,
                full_matches,
                omission_preview_limit,
            )
            pack, omission_preview_limit = _compact_pack(
                pack,
                bundle,
                candidates,
                needs,
                full_matches,
                options,
                compaction_state,
                omission_preview_limit,
            )
            pack = _relink_retained_matches(pack, candidates, needs)
            pack = _derive_final_outputs(
                pack,
                bundle,
                candidates,
                needs,
                full_matches,
                omission_preview_limit,
            )

            matched_need_ids = {
                need_id
                for item in pack.items
                for need_id in item.matched_need_ids
            }
            lost_pairs: list[tuple[str, str]] = []
            for need in needs:
                if need.id in matched_need_ids:
                    continue
                providers = tuple(
                    selected_item
                    for selected_item in selected
                    if need.id in selected_item.matched_need_ids
                )
                if providers:
                    primary = min(
                        providers,
                        key=lambda selected_item: selected_item.selection_priority,
                    )
                    lost_pairs.append((primary.candidate.key, need.id))
            retry_pairs = [
                pair
                for pair in lost_pairs
                if _has_alternative_match(
                    pair,
                    candidates,
                    full_matches,
                    blocked_matches,
                )
            ]
            if not retry_pairs:
                return _finalize_pack_size(pack)
            blocked_matches.update(retry_pairs)
        _fail()
    except ContextPackError:
        _fail()
    except Exception:
        _fail()


def _full_candidate_matches(
    candidates: tuple[ContextCandidate, ...],
    needs: tuple[EvidenceNeed, ...],
) -> dict[str, tuple[str, ...]]:
    return {
        candidate.key: tuple(
            need.id
            for need in needs
            if candidate_matches_need(candidate, need)
        )
        for candidate in candidates
    }


def _select_candidates(
    candidates: tuple[ContextCandidate, ...],
    needs: tuple[EvidenceNeed, ...],
    full_matches: dict[str, tuple[str, ...]],
    blocked_matches: set[tuple[str, str]],
    max_items: int,
) -> tuple[_SelectedCandidate, ...]:
    if max_items == 0:
        return ()
    need_by_id = {need.id: need for need in needs}
    group_positions = _promoted_group_positions(needs)
    selected: list[ContextCandidate] = []
    selected_keys: set[str] = set()
    selection_priorities: dict[str, tuple[object, ...]] = {}
    unmatched_required = {need.id for need in needs if need.required}
    unmatched_recommended = {need.id for need in needs if not need.required}

    def coverage(candidate: ContextCandidate) -> tuple[str, ...]:
        return tuple(
            need_id
            for need_id in full_matches[candidate.key]
            if (candidate.key, need_id) not in blocked_matches
        )

    def rank(candidate: ContextCandidate) -> tuple[object, ...]:
        candidate_coverage = coverage(candidate)
        required_count = sum(
            need_id in unmatched_required for need_id in candidate_coverage
        )
        recommended_count = sum(
            need_id in unmatched_recommended for need_id in candidate_coverage
        )
        return (
            required_count == 0,
            -required_count,
            recommended_count == 0,
            -recommended_count,
            group_positions[candidate.group],
            0 if candidate.source_kind == "result" else 1,
            (
                candidate.retrieval_rank
                if candidate.source_kind == "result"
                else candidate.source_order
            ),
            candidate.file_path,
        )

    def reserve(unmatched: set[str]) -> None:
        while unmatched and len(selected) < max_items:
            eligible = [
                candidate
                for candidate in candidates
                if candidate.key not in selected_keys
                and any(need_id in unmatched for need_id in coverage(candidate))
            ]
            if not eligible:
                break
            winner = min(eligible, key=rank)
            selected.append(winner)
            selected_keys.add(winner.key)
            selection_priorities[winner.key] = rank(winner)
            winner_coverage = set(coverage(winner))
            unmatched_required.difference_update(winner_coverage)
            unmatched_recommended.difference_update(winner_coverage)

    reserve(unmatched_required)
    reserve(unmatched_recommended)
    for candidate in sorted(
        (candidate for candidate in candidates if candidate.key not in selected_keys),
        key=rank,
    ):
        if len(selected) == max_items:
            break
        selected.append(candidate)
        selected_keys.add(candidate.key)
        selection_priorities[candidate.key] = rank(candidate)

    reading_order = sorted(
        selected,
        key=lambda candidate: (
            group_positions[candidate.group],
            0 if candidate.source_kind == "result" else 1,
            (
                candidate.retrieval_rank
                if candidate.source_kind == "result"
                else candidate.source_order
            ),
            candidate.file_path,
        ),
    )
    return tuple(
        _SelectedCandidate(
            candidate=candidate,
            matched_need_ids=tuple(
                need_id
                for need_id in coverage(candidate)
                if need_id in need_by_id
            ),
            selection_priority=selection_priorities[candidate.key],
            preferred_excerpts=(),
            excerpts=(),
        )
        for candidate in reading_order
    )


def _promoted_group_positions(
    needs: tuple[EvidenceNeed, ...],
) -> dict[str, int]:
    ordered: list[str] = []
    for need in needs:
        if need.category not in ordered:
            ordered.append(need.category)
    ordered.extend(group for group in CONTEXT_GROUPS if group not in ordered)
    return {group: index for index, group in enumerate(ordered)}


def _build_and_allocate_excerpts(
    selected: tuple[_SelectedCandidate, ...],
    needs: tuple[EvidenceNeed, ...],
    options: ContextPackOptions,
) -> tuple[_SelectedCandidate, ...]:
    need_by_id = {need.id: need for need in needs}
    prepared: list[_SelectedCandidate] = []
    for selected_item in selected:
        candidate = selected_item.candidate
        if candidate.source_kind == "result" and candidate.relevance_score is None:
            _fail()
        candidate_needs = tuple(
            need_by_id[need_id] for need_id in selected_item.matched_need_ids
        )
        preferred = build_candidate_excerpts(
            candidate=candidate,
            needs=candidate_needs,
            options=options,
        )
        prepared.append(
            replace(selected_item, preferred_excerpts=preferred)
        )

    return _allocate_prepared_excerpts(tuple(prepared), needs, options)


def _allocate_prepared_excerpts(
    prepared: tuple[_SelectedCandidate, ...],
    needs: tuple[EvidenceNeed, ...],
    options: ContextPackOptions,
) -> tuple[_SelectedCandidate, ...]:
    need_by_id = {need.id: need for need in needs}

    desired_sizes = [
        min(
            options.max_item_content_bytes,
            sum(excerpt.content_bytes for excerpt in item.preferred_excerpts),
        )
        for item in prepared
    ]
    allocated = [replace(item, excerpts=()) for item in prepared]
    actual_sizes = [0 for _ in prepared]
    total_actual = 0

    required_indexes = [
        index
        for index, item in enumerate(prepared)
        if any(need_by_id[need_id].required for need_id in item.matched_need_ids)
    ]
    recommended_indexes = [
        index
        for index, item in enumerate(prepared)
        if any(not need_by_id[need_id].required for need_id in item.matched_need_ids)
    ]

    def fit(index: int, target: int) -> None:
        nonlocal total_actual
        item = prepared[index]
        required_terms = tuple(
            term
            for need_id in item.matched_need_ids
            if need_by_id[need_id].required
            for term in need_by_id[need_id].subject_terms
        )
        recommended_terms = tuple(
            term
            for need_id in item.matched_need_ids
            if not need_by_id[need_id].required
            for term in need_by_id[need_id].subject_terms
        )
        fitted = fit_excerpts_to_bytes(
            item.preferred_excerpts,
            target,
            required_subject_terms=required_terms,
            recommended_subject_terms=recommended_terms,
        )
        new_size = sum(excerpt.content_bytes for excerpt in fitted)
        total_actual += new_size - actual_sizes[index]
        actual_sizes[index] = new_size
        allocated[index] = replace(item, excerpts=fitted)

    def reserve(indexes: Iterable[int]) -> None:
        for index in indexes:
            available = options.max_total_content_bytes - total_actual
            target = min(
                _MIN_EVIDENCE_BYTES,
                desired_sizes[index],
                actual_sizes[index] + available,
            )
            fit(index, target)

    reserve(required_indexes)
    reserve(recommended_indexes)
    for index in range(len(prepared)):
        available = options.max_total_content_bytes - total_actual
        target = min(
            desired_sizes[index],
            actual_sizes[index] + available,
        )
        fit(index, target)
    return tuple(allocated)


def _materialize_pack(
    candidates: tuple[ContextCandidate, ...],
    selected: tuple[_SelectedCandidate, ...],
    needs: tuple[EvidenceNeed, ...],
    full_matches: dict[str, tuple[str, ...]],
    options: ContextPackOptions,
) -> ContextPack:
    items = tuple(
        ContextItem(
            id=f"item:{index}",
            file_path=selected_item.candidate.file_path,
            group=selected_item.candidate.group,
            role=selected_item.candidate.role,
            classification_basis=selected_item.candidate.classification_basis,
            source_kind=selected_item.candidate.source_kind,
            retrieval_rank=selected_item.candidate.retrieval_rank,
            relevance_score=selected_item.candidate.relevance_score,
            reasons=selected_item.candidate.reasons,
            matched_need_ids=selected_item.matched_need_ids,
            excerpts=selected_item.excerpts,
        )
        for index, selected_item in enumerate(selected)
    )
    selected_keys = {item.candidate.key for item in selected}
    omitted_candidates = tuple(
        candidate for candidate in candidates if candidate.key not in selected_keys
    )
    need_by_id = {need.id: need for need in needs}
    group_positions = _promoted_group_positions(needs)
    ordered_omissions = sorted(
        omitted_candidates,
        key=lambda candidate: (
            not any(
                need_by_id[need_id].required
                for need_id in full_matches[candidate.key]
            ),
            not any(
                not need_by_id[need_id].required
                for need_id in full_matches[candidate.key]
            ),
            group_positions[candidate.group],
            0 if candidate.source_kind == "result" else 1,
            (
                candidate.retrieval_rank
                if candidate.source_kind == "result"
                else candidate.source_order
            ),
            candidate.file_path,
        ),
    )
    omissions = tuple(
        Omission(
            file_path=candidate.file_path,
            group=candidate.group,
            reason=_OMISSION_REASON,
            matched_need_ids=full_matches[candidate.key],
        )
        for candidate in ordered_omissions[: options.max_items]
    )
    exhausted = (
        bool(omitted_candidates)
        or any(
            _excerpt_count_limited(item, need_by_id, options)
            for item in selected
        )
        or any(
            excerpt.truncated
            for item in selected
            for excerpt in item.preferred_excerpts
        )
        or any(
            sum(excerpt.content_bytes for excerpt in item.preferred_excerpts)
            != sum(excerpt.content_bytes for excerpt in item.excerpts)
            for item in selected
        )
    )
    pack = ContextPack(
        schema_version=CONTEXT_PACK_SCHEMA_VERSION,
        status="partial",
        items=items,
        groups=_groups_for_items(items),
        reading_order=tuple(item.id for item in items),
        evidence_needs=_link_needs(needs, items),
        missing_evidence=(),
        next_queries=(),
        omissions=omissions,
        confidence=ReadinessConfidence(level="low", reasons=()),
        budget=ContextBudget(
            max_items=options.max_items,
            max_excerpts_per_item=options.max_excerpts_per_item,
            max_excerpt_bytes=options.max_excerpt_bytes,
            max_item_content_bytes=options.max_item_content_bytes,
            max_total_content_bytes=options.max_total_content_bytes,
            max_pack_bytes=options.max_pack_bytes,
            included_items=0,
            included_excerpts=0,
            content_bytes=0,
            pack_bytes=0,
            truncated_item_count=0,
            omitted_item_count=len(omitted_candidates),
            budget_exhausted=exhausted,
        ),
    )
    return _refresh_pack(pack)


def _derive_final_outputs(
    pack: ContextPack,
    bundle: QueryBundle,
    candidates: tuple[ContextCandidate, ...],
    needs: tuple[EvidenceNeed, ...],
    full_matches: dict[str, tuple[str, ...]],
    omission_preview_limit: int,
) -> ContextPack:
    linked_needs = _link_needs(needs, pack.items)
    if not candidates:
        status = "empty"
    elif not pack.items or any(
        need.required and not need.matched_item_ids for need in linked_needs
    ):
        status = "partial"
    else:
        status = "ready"

    selected_paths = {item.file_path for item in pack.items}
    omitted_candidates = tuple(
        candidate
        for candidate in candidates
        if candidate.file_path not in selected_paths
    )
    omissions = _omission_preview(
        omitted_candidates,
        linked_needs,
        full_matches,
        omission_preview_limit,
    )
    candidates_by_path = {
        candidate.file_path: candidate for candidate in candidates
    }
    confidence = derive_readiness_confidence(
        status,
        linked_needs,
        pack.items,
        candidates_by_path,
    )
    next_queries = derive_next_queries(
        bundle,
        linked_needs,
        pack.items,
        candidates_by_path,
    )
    derived = replace(
        pack,
        status=status,
        evidence_needs=linked_needs,
        missing_evidence=derive_missing_evidence(linked_needs),
        next_queries=next_queries,
        omissions=omissions,
        confidence=confidence,
        budget=replace(
            pack.budget,
            omitted_item_count=len(omitted_candidates),
            budget_exhausted=(
                pack.budget.budget_exhausted or bool(omitted_candidates)
            ),
        ),
    )
    return _refresh_pack(derived)


def _omission_preview(
    omitted_candidates: tuple[ContextCandidate, ...],
    needs: tuple[EvidenceNeed, ...],
    full_matches: dict[str, tuple[str, ...]],
    preview_limit: int,
) -> tuple[Omission, ...]:
    need_by_id = {need.id: need for need in needs}
    group_positions = _promoted_group_positions(needs)

    def order(candidate: ContextCandidate) -> tuple[object, ...]:
        matched = full_matches[candidate.key]
        required_count = sum(need_by_id[need_id].required for need_id in matched)
        recommended_count = sum(
            not need_by_id[need_id].required for need_id in matched
        )
        return (
            required_count == 0,
            -required_count,
            recommended_count == 0,
            -recommended_count,
            group_positions[candidate.group],
            0 if candidate.source_kind == "result" else 1,
            (
                candidate.retrieval_rank
                if candidate.source_kind == "result"
                else candidate.source_order
            ),
            candidate.file_path,
        )

    return tuple(
        Omission(
            file_path=candidate.file_path,
            group=candidate.group,
            reason=_OMISSION_REASON,
            matched_need_ids=full_matches[candidate.key],
        )
        for candidate in sorted(omitted_candidates, key=order)[
            : max(0, preview_limit)
        ]
    )


def _excerpt_count_limited(
    selected: _SelectedCandidate,
    need_by_id: dict[str, EvidenceNeed],
    options: ContextPackOptions,
) -> bool:
    candidate_needs = tuple(
        need_by_id[need_id] for need_id in selected.matched_need_ids
    )
    span_count = (
        len(normalize_candidate_spans(selected.candidate))
        if selected.candidate.source_kind == "result"
        else 1
    )
    unlimited = build_candidate_excerpts(
        candidate=selected.candidate,
        needs=candidate_needs,
        options=replace(
            options,
            max_excerpts_per_item=max(
                options.max_excerpts_per_item,
                span_count,
            ),
        ),
    )
    return len(unlimited) > options.max_excerpts_per_item


def _compact_pack(
    pack: ContextPack,
    bundle: QueryBundle,
    candidates: tuple[ContextCandidate, ...],
    needs: tuple[EvidenceNeed, ...],
    full_matches: dict[str, tuple[str, ...]],
    options: ContextPackOptions,
    compaction_state: dict[str, _SelectedCandidate],
    omission_preview_limit: int,
) -> tuple[ContextPack, int]:
    need_by_id = {need.id: need for need in needs}
    compacted = _derive_final_outputs(
        _refresh_pack(pack),
        bundle,
        candidates,
        needs,
        full_matches,
        omission_preview_limit,
    )
    while serialization._context_pack_size(compacted) > options.max_pack_bytes:
        if compacted.omissions:
            omission_preview_limit = len(compacted.omissions) - 1
            compacted = _derive_final_outputs(
                compacted,
                bundle,
                candidates,
                needs,
                full_matches,
                omission_preview_limit,
            )
            continue

        reason_index = next(
            (
                index
                for index in _lowest_priority_indexes(
                    compacted,
                    compaction_state,
                )
                if compacted.items[index].reasons
            ),
            None,
        )
        if reason_index is not None:
            items = list(compacted.items)
            items[reason_index] = replace(
                items[reason_index],
                reasons=items[reason_index].reasons[:-1],
            )
            compacted = _replace_items(compacted, tuple(items))
            compacted = replace(
                compacted,
                budget=replace(compacted.budget, budget_exhausted=True),
            )
            compacted = _relink_retained_matches(
                compacted,
                candidates,
                needs,
            )
            compacted = _derive_final_outputs(
                compacted,
                bundle,
                candidates,
                needs,
                full_matches,
                omission_preview_limit,
            )
            continue

        compacted = _relink_retained_matches(
            compacted,
            tuple(item.candidate for item in compaction_state.values()),
            needs,
        )
        compacted = _derive_final_outputs(
            compacted,
            bundle,
            candidates,
            needs,
            full_matches,
            omission_preview_limit,
        )
        if serialization._context_pack_size(compacted) <= options.max_pack_bytes:
            break
        content_choice = _content_compaction_choice(
            compacted,
            need_by_id,
            compaction_state,
        )
        if content_choice is not None:
            content_index, minimum_bytes = content_choice
            item = compacted.items[content_index]
            current_bytes = sum(
                excerpt.content_bytes for excerpt in item.excerpts
            )
            excess = (
                serialization._context_pack_size(compacted)
                - options.max_pack_bytes
            )
            target_bytes = max(
                minimum_bytes,
                current_bytes - max(1, excess),
            )
            required_terms = tuple(
                term
                for need_id in item.matched_need_ids
                if need_by_id[need_id].required
                for term in need_by_id[need_id].subject_terms
            )
            fitted = fit_excerpts_to_bytes(
                item.excerpts,
                target_bytes,
                required_subject_terms=required_terms,
            )
            if fitted == item.excerpts:
                fitted = fit_excerpts_to_bytes(
                    item.excerpts,
                    minimum_bytes,
                    required_subject_terms=required_terms,
                )
            items = list(compacted.items)
            items[content_index] = replace(item, excerpts=fitted)
            compacted = _replace_items(
                compacted,
                tuple(items),
                force_budget_exhausted=True,
            )
            compacted = _relink_retained_matches(
                compacted,
                candidates,
                needs,
            )
            compacted = _derive_final_outputs(
                compacted,
                bundle,
                candidates,
                needs,
                full_matches,
                omission_preview_limit,
            )
            continue

        removable_index = _item_compaction_index(
            compacted,
            need_by_id,
            compaction_state,
        )
        if removable_index is not None:
            compacted = _omit_item_and_restore(
                compacted,
                removable_index,
                compaction_state,
                needs,
                options,
            )
            compacted = _derive_final_outputs(
                compacted,
                bundle,
                candidates,
                needs,
                full_matches,
                omission_preview_limit,
            )
            continue
        _fail()

    empty_indexes = {
        index for index, item in enumerate(compacted.items) if not item.excerpts
    }
    removable_empty_index = next(
        (
            index
            for index in _lowest_priority_indexes(
                compacted,
                compaction_state,
            )
            if index in empty_indexes
        ),
        None,
    )
    if removable_empty_index is None:
        return compacted, omission_preview_limit
    compacted = _omit_item_and_restore(
        compacted,
        removable_empty_index,
        compaction_state,
        needs,
        options,
    )
    return _compact_pack(
        compacted,
        bundle,
        candidates,
        needs,
        full_matches,
        options,
        compaction_state,
        omission_preview_limit,
    )


def _content_compaction_choice(
    pack: ContextPack,
    need_by_id: dict[str, EvidenceNeed],
    compaction_state: dict[str, _SelectedCandidate],
) -> tuple[int, int] | None:
    indexes = _lowest_priority_indexes(pack, compaction_state)
    for required in (False, True):
        for index in indexes:
            item = pack.items[index]
            item_required = any(
                need_by_id[need_id].required for need_id in item.matched_need_ids
            )
            if item_required != required or not item.excerpts:
                continue
            minimum_bytes = (
                _minimum_required_content_bytes(
                    item,
                    compaction_state[item.file_path],
                    need_by_id,
                )
                if required
                else 0
            )
            current_bytes = sum(
                excerpt.content_bytes for excerpt in item.excerpts
            )
            if current_bytes > minimum_bytes:
                return index, minimum_bytes
    return None


def _minimum_required_content_bytes(
    item: ContextItem,
    selected: _SelectedCandidate,
    need_by_id: dict[str, EvidenceNeed],
) -> int:
    required_needs = tuple(
        need_by_id[need_id]
        for need_id in item.matched_need_ids
        if need_by_id[need_id].required
    )
    if not required_needs:
        return 0
    required_terms = tuple(
        term for need in required_needs for term in need.subject_terms
    )
    current_bytes = sum(excerpt.content_bytes for excerpt in item.excerpts)
    retained_candidate = _candidate_with_retained_reasons(
        selected.candidate,
        item,
    )
    if not all(
        _candidate_matches_retained_item(
            retained_candidate,
            item,
            need,
        )
        for need in required_needs
    ):
        return 0
    best = current_bytes
    low = 1
    high = current_bytes
    while low <= high:
        target = (low + high) // 2
        fitted = fit_excerpts_to_bytes(
            item.excerpts,
            target,
            required_subject_terms=required_terms,
        )
        fitted_item = replace(item, excerpts=fitted)
        if fitted and all(
            _candidate_matches_retained_item(
                retained_candidate,
                fitted_item,
                need,
            )
            for need in required_needs
        ):
            best = sum(excerpt.content_bytes for excerpt in fitted)
            high = target - 1
        else:
            low = target + 1
    return best


def _restore_preferred_excerpts(
    pack: ContextPack,
    compaction_state: dict[str, _SelectedCandidate],
    needs: tuple[EvidenceNeed, ...],
    options: ContextPackOptions,
) -> ContextPack:
    prepared = tuple(
        replace(
            compaction_state[item.file_path],
            matched_need_ids=item.matched_need_ids,
        )
        for item in pack.items
    )
    allocated = _allocate_prepared_excerpts(prepared, needs, options)
    excerpts_by_path = {
        item.candidate.file_path: item.excerpts for item in allocated
    }
    restored = tuple(
        replace(item, excerpts=excerpts_by_path[item.file_path])
        for item in pack.items
    )
    return _replace_items(
        pack,
        restored,
        force_budget_exhausted=True,
    )


def _omit_item_and_restore(
    pack: ContextPack,
    remove_index: int,
    compaction_state: dict[str, _SelectedCandidate],
    needs: tuple[EvidenceNeed, ...],
    options: ContextPackOptions,
) -> ContextPack:
    retained = tuple(
        item
        for index, item in enumerate(pack.items)
        if index != remove_index
    )
    compacted = _replace_items(
        pack,
        retained,
        omitted_increment=1,
        force_budget_exhausted=True,
    )
    return _restore_preferred_excerpts(
        compacted,
        compaction_state,
        needs,
        options,
    )


def _item_compaction_index(
    pack: ContextPack,
    need_by_id: dict[str, EvidenceNeed],
    compaction_state: dict[str, _SelectedCandidate],
) -> int | None:
    indexes = _lowest_priority_indexes(pack, compaction_state)
    for required in (False, True):
        for index in indexes:
            item = pack.items[index]
            item_required = any(
                need_by_id[need_id].required for need_id in item.matched_need_ids
            )
            if item_required == required:
                return index
    return None


def _lowest_priority_indexes(
    pack: ContextPack,
    compaction_state: dict[str, _SelectedCandidate],
) -> list[int]:
    return sorted(
        range(len(pack.items)),
        key=lambda index: compaction_state[
            pack.items[index].file_path
        ].selection_priority,
        reverse=True,
    )


def _relink_retained_matches(
    pack: ContextPack,
    candidates: tuple[ContextCandidate, ...],
    needs: tuple[EvidenceNeed, ...],
) -> ContextPack:
    candidate_by_path = {candidate.file_path: candidate for candidate in candidates}
    items: list[ContextItem] = []
    for item in pack.items:
        candidate = _candidate_with_retained_reasons(
            candidate_by_path[item.file_path],
            item,
        )
        matched_need_ids = tuple(
            need.id
            for need in needs
            if _candidate_matches_retained_item(candidate, item, need)
        )
        items.append(replace(item, matched_need_ids=matched_need_ids))
    return _replace_items(pack, tuple(items))


def _candidate_with_retained_reasons(
    candidate: ContextCandidate,
    item: ContextItem,
) -> ContextCandidate:
    return replace(
        candidate,
        reasons=item.reasons,
        trusted_provenance_text="\n".join(
            (candidate.file_path, *item.reasons)
        ),
    )


def _candidate_matches_retained_item(
    candidate: ContextCandidate,
    item: ContextItem,
    need: EvidenceNeed,
) -> bool:
    return (
        candidate.file_path == item.file_path
        and retained_item_matches_need(item, need)
    )


def _has_alternative_match(
    lost_pair: tuple[str, str],
    candidates: tuple[ContextCandidate, ...],
    full_matches: dict[str, tuple[str, ...]],
    blocked_matches: set[tuple[str, str]],
) -> bool:
    failed_key, need_id = lost_pair
    return any(
        candidate.key != failed_key
        and need_id in full_matches[candidate.key]
        and (candidate.key, need_id) not in blocked_matches
        for candidate in candidates
    )


def _replace_items(
    pack: ContextPack,
    items: tuple[ContextItem, ...],
    *,
    omitted_increment: int = 0,
    force_budget_exhausted: bool = False,
) -> ContextPack:
    renumbered = tuple(
        replace(item, id=f"item:{index}")
        for index, item in enumerate(items)
    )
    budget = replace(
        pack.budget,
        omitted_item_count=pack.budget.omitted_item_count + omitted_increment,
        budget_exhausted=(
            pack.budget.budget_exhausted or force_budget_exhausted
        ),
    )
    replaced = replace(
        pack,
        items=renumbered,
        groups=_groups_for_items(renumbered),
        reading_order=tuple(item.id for item in renumbered),
        evidence_needs=_link_needs(pack.evidence_needs, renumbered),
        budget=budget,
    )
    return _refresh_pack(replaced)


def _refresh_pack(pack: ContextPack) -> ContextPack:
    included_excerpts = sum(len(item.excerpts) for item in pack.items)
    content_bytes = sum(
        excerpt.content_bytes
        for item in pack.items
        for excerpt in item.excerpts
    )
    truncated_item_count = sum(
        any(excerpt.truncated for excerpt in item.excerpts)
        for item in pack.items
    )
    return replace(
        pack,
        budget=replace(
            pack.budget,
            included_items=len(pack.items),
            included_excerpts=included_excerpts,
            content_bytes=content_bytes,
            pack_bytes=0,
            truncated_item_count=truncated_item_count,
        ),
    )


def _groups_for_items(
    items: tuple[ContextItem, ...],
) -> dict[str, tuple[str, ...]]:
    return {
        group: tuple(item.id for item in items if item.group == group)
        for group in CONTEXT_GROUPS
    }


def _link_needs(
    needs: tuple[EvidenceNeed, ...],
    items: tuple[ContextItem, ...],
) -> tuple[EvidenceNeed, ...]:
    return tuple(
        replace(
            need,
            matched_item_ids=tuple(
                item.id for item in items if need.id in item.matched_need_ids
            ),
        )
        for need in needs
    )


def _finalize_pack_size(pack: ContextPack) -> ContextPack:
    size = serialization._context_pack_size(pack)
    if size > pack.budget.max_pack_bytes:
        _fail()
    finalized = replace(pack, budget=replace(pack.budget, pack_bytes=size))
    encoded = serialization.canonical_context_pack_bytes(finalized)
    if len(encoded) != size:
        _fail()
    return finalized


def _validate_build_options(options: ContextPackOptions) -> None:
    if type(options) is not ContextPackOptions:
        _fail()
    values = (
        options.max_excerpts_per_item,
        options.max_excerpt_bytes,
        options.max_item_content_bytes,
        options.max_total_content_bytes,
        options.max_pack_bytes,
    )
    if (
        type(options.max_items) is not int
        or options.max_items < 0
        or any(type(value) is not int or value <= 0 for value in values)
        or type(options.context_before_lines) is not int
        or options.context_before_lines < 0
        or type(options.context_after_lines) is not int
        or options.context_after_lines < 0
        or not (
            options.max_excerpt_bytes
            <= options.max_item_content_bytes
            <= options.max_total_content_bytes
            < options.max_pack_bytes
        )
    ):
        _fail()


def _validate_candidates(candidates: tuple[ContextCandidate, ...]) -> None:
    if type(candidates) is not tuple:
        _fail()
    seen_keys: set[str] = set()
    seen_paths: set[str] = set()
    for candidate in candidates:
        if (
            type(candidate) is not ContextCandidate
            or type(candidate.key) is not str
            or not candidate.key
            or candidate.key != candidate.file_path
            or not serialization._repo_relative_path_is_canonical(
                candidate.file_path
            )
            or candidate.key in seen_keys
            or candidate.file_path in seen_paths
            or candidate.group not in CONTEXT_GROUPS
            or not serialization._role_is_valid(
                candidate.group,
                candidate.role,
            )
            or candidate.classification_basis
            not in {"path", "content", "fallback"}
            or candidate.source_kind not in {"result", "evidence_anchor"}
            or type(candidate.source_order) is not int
            or candidate.source_order < 0
            or type(candidate.reasons) is not tuple
            or len(candidate.reasons) > 4
            or len(candidate.reasons) != len(set(candidate.reasons))
            or any(
                type(reason) is not str or not reason
                for reason in candidate.reasons
            )
            or type(candidate.score_parts) is not dict
            or any(
                type(key) is not str or not key
                for key in candidate.score_parts
            )
            or type(candidate.spans) is not tuple
            or type(candidate.trusted_provenance_text) is not str
            or candidate.trusted_provenance_text
            != "\n".join((candidate.file_path, *candidate.reasons))
            or type(candidate.protected_direct) is not bool
        ):
            _fail()

        evidence_priority = candidate.score_parts.get("evidence_priority")
        protected_direct = (
            isinstance(evidence_priority, Real)
            and not isinstance(evidence_priority, bool)
            and evidence_priority == 0
        )
        if candidate.source_kind == "result":
            if (
                type(candidate.retrieval_rank) is not int
                or candidate.retrieval_rank < 0
                or candidate.source_order != candidate.retrieval_rank
                or type(candidate.relevance_score) not in (int, float)
                or not isfinite(candidate.relevance_score)
                or candidate.protected_direct is not protected_direct
            ):
                _fail()
        elif (
            candidate.retrieval_rank is not None
            or candidate.relevance_score is not None
            or candidate.spans
            or candidate.protected_direct
        ):
            _fail()

        normalize_candidate_spans(candidate)
        seen_keys.add(candidate.key)
        seen_paths.add(candidate.file_path)


def _invalid(message: str) -> None:
    raise ContextPackError("invalid_context_options", message)


def _fail() -> NoReturn:
    raise ContextPackError(_FAILURE_CODE, _FAILURE_MESSAGE)


__all__ = ("build_context_pack", "resolve_context_pack_options")
