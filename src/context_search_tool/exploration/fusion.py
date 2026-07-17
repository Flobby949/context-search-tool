from __future__ import annotations

import copy
from dataclasses import replace
from math import isfinite
from numbers import Real
from pathlib import PurePosixPath
from typing import Iterable, TypeVar

from context_search_tool.context_pack import (
    ContextPack,
    ContextPackOptions,
    EvidenceNeed,
    build_context_pack,
)
from context_search_tool.context_pack.needs import candidate_matches_need
from context_search_tool.context_pack.roles import normalize_candidates
from context_search_tool.exploration.goals import satisfied_goal_ids
from context_search_tool.exploration.models import (
    MAX_FUSED_ANCHORS,
    MAX_FUSED_RESULTS,
    EvidenceOrigin,
    ExplorationGoal,
    FrozenGoals,
    FusedEvidenceState,
    ProbeCandidate,
)
from context_search_tool.models import EvidenceAnchor, RetrievalResult
from context_search_tool.retrieval import QueryBundle


_FOLLOWUP_REASON_CODE_POINTS = 96
_Entry = TypeVar("_Entry", RetrievalResult, EvidenceAnchor)


def initialize_fusion(
    initial_bundle: QueryBundle,
    initial_pack: ContextPack,
    frozen: FrozenGoals,
) -> FusedEvidenceState:
    results = _unique_entries(initial_bundle.results, MAX_FUSED_RESULTS)
    result_paths = {entry.file_path.as_posix() for entry, _ in results}
    anchors = tuple(
        (entry, rank)
        for entry, rank in _unique_entries(
            initial_bundle.evidence_anchors,
            MAX_FUSED_ANCHORS + len(result_paths),
        )
        if entry.file_path.as_posix() not in result_paths
    )[:MAX_FUSED_ANCHORS]

    snapshot = copy.deepcopy(initial_bundle)
    fused_bundle = replace(
        snapshot,
        results=[copy.deepcopy(entry) for entry, _ in results],
        evidence_anchors=[copy.deepcopy(entry) for entry, _ in anchors],
    )
    origins = tuple(
        [
            _initial_origin(fused_bundle, entry, "result", rank, frozen)
            for entry, rank in results
        ]
        + [
            _initial_origin(
                fused_bundle,
                entry,
                "evidence_anchor",
                rank,
                frozen,
            )
            for entry, rank in anchors
        ]
    )
    return FusedEvidenceState(
        bundle=fused_bundle,
        origins=origins,
        satisfied_goal_ids=satisfied_goal_ids(frozen, initial_pack),
    )


def add_probe_evidence(
    state: FusedEvidenceState,
    probe_bundle: QueryBundle,
    frozen: FrozenGoals,
    pack_options: ContextPackOptions,
    *,
    probe: ProbeCandidate,
    round_index: int,
    probe_id: str,
) -> tuple[FusedEvidenceState, ContextPack]:
    current_bundle = copy.deepcopy(state.bundle)
    origins = {origin.file_path: origin for origin in state.origins}
    prior_satisfied = tuple(state.satisfied_goal_ids)
    current_satisfied = prior_satisfied
    current_pack: ContextPack | None = None

    result_entries = _unique_entries(probe_bundle.results, MAX_FUSED_RESULTS)
    result_paths = {entry.file_path.as_posix() for entry, _ in result_entries}
    anchor_entries = tuple(
        (entry, rank)
        for entry, rank in _unique_entries(
            probe_bundle.evidence_anchors,
            MAX_FUSED_ANCHORS + MAX_FUSED_RESULTS,
        )
        if entry.file_path.as_posix() not in result_paths
    )

    for entry, source_rank in (*result_entries, *anchor_entries):
        source_kind = (
            "result" if isinstance(entry, RetrievalResult) else "evidence_anchor"
        )
        adapted = _adapt_followup(entry, probe_id, probe.purpose)
        if adapted is None or not _canonical_path(adapted.file_path.as_posix()):
            continue
        proposed_goal_ids = _candidate_goal_ids(
            current_bundle,
            adapted,
            source_kind,
            frozen,
        )
        proposed = _propose_bundle(
            current_bundle,
            origins,
            adapted,
            source_kind,
            source_rank,
            proposed_goal_ids,
            frozen,
            probe_id,
            round_index,
        )
        if proposed is None:
            continue
        proposed_bundle, proposed_origins = proposed
        proposed_pack = build_context_pack(proposed_bundle, pack_options)
        proposed_satisfied = satisfied_goal_ids(frozen, proposed_pack)
        if not set(current_satisfied).issubset(proposed_satisfied):
            continue
        current_bundle = proposed_bundle
        origins = proposed_origins
        current_pack = proposed_pack
        current_satisfied = proposed_satisfied

    if current_pack is None:
        current_pack = build_context_pack(current_bundle, pack_options)
        current_satisfied = satisfied_goal_ids(frozen, current_pack)
    if not set(prior_satisfied).issubset(current_satisfied):
        raise ValueError("fused pack lost frozen goal coverage")

    ordered_origins = tuple(
        origins[item.file_path.as_posix()]
        for item in (
            *current_bundle.results,
            *current_bundle.evidence_anchors,
        )
    )
    return (
        FusedEvidenceState(
            bundle=current_bundle,
            origins=ordered_origins,
            satisfied_goal_ids=current_satisfied,
        ),
        current_pack,
    )


def _propose_bundle(
    bundle: QueryBundle,
    origins: dict[str, EvidenceOrigin],
    entry: RetrievalResult | EvidenceAnchor,
    source_kind: str,
    source_rank: int,
    goal_ids: tuple[str, ...],
    frozen: FrozenGoals,
    probe_id: str,
    round_index: int,
) -> tuple[QueryBundle, dict[str, EvidenceOrigin]] | None:
    path = entry.file_path.as_posix()
    result_index = _path_index(bundle.results, path)
    anchor_index = _path_index(bundle.evidence_anchors, path)
    existing_kind: str | None = None
    existing_index: int | None = None
    existing: RetrievalResult | EvidenceAnchor | None = None
    if result_index is not None:
        existing_kind = "result"
        existing_index = result_index
        existing = bundle.results[result_index]
    elif anchor_index is not None:
        existing_kind = "evidence_anchor"
        existing_index = anchor_index
        existing = bundle.evidence_anchors[anchor_index]

    if existing is not None:
        if existing_kind == "result" and source_kind == "evidence_anchor":
            return None
        existing_origin = origins[path]
        if _protected_result(existing):
            return None
        if not set(existing_origin.goal_ids) < set(goal_ids):
            return None
        if not _candidate_priority_improves(
            existing_origin.goal_ids,
            goal_ids,
            frozen,
        ):
            return None

        proposed = copy.deepcopy(bundle)
        if existing_kind == source_kind:
            target = (
                proposed.results
                if source_kind == "result"
                else proposed.evidence_anchors
            )
            target[existing_index] = copy.deepcopy(entry)
        elif source_kind == "result":
            if len(proposed.results) >= MAX_FUSED_RESULTS:
                return None
            del proposed.evidence_anchors[existing_index]
            proposed.results.append(copy.deepcopy(entry))
        else:
            return None
        proposed_origins = dict(origins)
        proposed_origins[path] = EvidenceOrigin(
            path,
            round_index,
            probe_id,
            source_kind,
            source_rank,
            (
                "selected_evidence_anchor"
                if source_kind == "evidence_anchor"
                else "replaced_by_goal_covering_probe"
            ),
            goal_ids,
        )
        return proposed, proposed_origins

    proposed = copy.deepcopy(bundle)
    if source_kind == "result":
        if len(proposed.results) >= MAX_FUSED_RESULTS:
            return None
        proposed.results.append(copy.deepcopy(entry))
        selection_reason = "added_novel_probe_evidence"
    else:
        if len(proposed.evidence_anchors) >= MAX_FUSED_ANCHORS:
            return None
        proposed.evidence_anchors.append(copy.deepcopy(entry))
        selection_reason = "selected_evidence_anchor"
    proposed_origins = dict(origins)
    proposed_origins[path] = EvidenceOrigin(
        path,
        round_index,
        probe_id,
        source_kind,
        source_rank,
        selection_reason,
        goal_ids,
    )
    return proposed, proposed_origins


def _candidate_priority_improves(
    old_goal_ids: tuple[str, ...],
    new_goal_ids: tuple[str, ...],
    frozen: FrozenGoals,
) -> bool:
    required = {goal.id for goal in frozen.goals if goal.required}
    old_required = len(required.intersection(old_goal_ids))
    new_required = len(required.intersection(new_goal_ids))
    old_recommended = len(set(old_goal_ids) - required)
    new_recommended = len(set(new_goal_ids) - required)
    return (new_required, new_recommended) > (old_required, old_recommended)


def _adapt_followup(
    entry: RetrievalResult | EvidenceAnchor,
    probe_id: str,
    purpose: str,
) -> RetrievalResult | EvidenceAnchor | None:
    if (
        isinstance(entry.score, bool)
        or not isinstance(entry.score, Real)
        or not isfinite(float(entry.score))
    ):
        return None
    reason = f"exploration:{probe_id}:{purpose}"[:_FOLLOWUP_REASON_CODE_POINTS]
    if not reason:
        return None
    score_parts = copy.deepcopy(entry.score_parts)
    priority = score_parts.get("evidence_priority")
    score_parts["evidence_priority"] = (
        max(1.0, float(priority))
        if isinstance(priority, Real)
        and not isinstance(priority, bool)
        and isfinite(float(priority))
        else 1.0
    )
    return replace(
        copy.deepcopy(entry),
        score_parts=score_parts,
        reasons=[reason],
        semantic_matches=[],
    )


def _initial_origin(
    bundle: QueryBundle,
    entry: RetrievalResult | EvidenceAnchor,
    source_kind: str,
    source_rank: int,
    frozen: FrozenGoals,
) -> EvidenceOrigin:
    path = entry.file_path.as_posix()
    return EvidenceOrigin(
        path,
        0,
        "r0p0",
        source_kind,
        source_rank,
        (
            "retained_initial_evidence"
            if source_kind == "result"
            else "selected_evidence_anchor"
        ),
        _candidate_goal_ids(bundle, entry, source_kind, frozen),
    )


def _candidate_goal_ids(
    bundle: QueryBundle,
    entry: RetrievalResult | EvidenceAnchor,
    source_kind: str,
    frozen: FrozenGoals,
) -> tuple[str, ...]:
    isolated = replace(
        bundle,
        results=[entry] if source_kind == "result" else [],
        evidence_anchors=[entry] if source_kind == "evidence_anchor" else [],
    )
    candidates = normalize_candidates(isolated)
    if len(candidates) != 1:
        return ()
    candidate = candidates[0]
    matched: list[str] = []
    for goal in frozen.goals:
        if goal.kind == "role_gap" and candidate.role not in goal.accepted_roles:
            continue
        need = EvidenceNeed(
            id=goal.id,
            category=goal.category if goal.kind == "need" else candidate.group,
            subject_terms=goal.subject_terms,
            required=goal.required,
            provenance="explicit_query",
            matched_item_ids=(),
        )
        if candidate_matches_need(candidate, need):
            matched.append(goal.id)
    return tuple(matched)


def _unique_entries(
    entries: Iterable[_Entry],
    limit: int,
) -> tuple[tuple[_Entry, int], ...]:
    unique: list[tuple[_Entry, int]] = []
    seen_paths: set[str] = set()
    for source_rank, entry in enumerate(entries, start=1):
        path = entry.file_path.as_posix()
        if path in seen_paths or not _canonical_path(path):
            continue
        seen_paths.add(path)
        unique.append((entry, source_rank))
        if len(unique) == limit:
            break
    return tuple(unique)


def _path_index(entries: Iterable[object], path: str) -> int | None:
    return next(
        (
            index
            for index, entry in enumerate(entries)
            if entry.file_path.as_posix() == path
        ),
        None,
    )


def _protected_result(entry: RetrievalResult | EvidenceAnchor) -> bool:
    if not isinstance(entry, RetrievalResult):
        return False
    priority = entry.score_parts.get("evidence_priority")
    return (
        isinstance(priority, Real)
        and not isinstance(priority, bool)
        and priority == 0
    )


def _canonical_path(value: str) -> bool:
    path = PurePosixPath(value)
    return bool(
        value
        and "\\" not in value
        and not path.is_absolute()
        and path.as_posix() == value
        and "." not in path.parts
        and ".." not in path.parts
    )
