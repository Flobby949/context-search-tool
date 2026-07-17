from __future__ import annotations

import heapq
import logging
from dataclasses import dataclass
from pathlib import Path

from context_search_tool import sqlite_store
from context_search_tool.config import ToolConfig
from context_search_tool.graph_contract import effective_relation_confidence
from context_search_tool.models import (
    CodeRelation,
    CodeSignal,
    DocumentChunk,
    RetrievalCandidate,
)
from context_search_tool.retrieval_core import (
    evidence_merge,
    file_roles,
    relation_policy,
)


logger = logging.getLogger("context_search_tool.retrieval")

_RELATION_SCORE_DECAY = 0.8


@dataclass(frozen=True)
class _RelationSeed:
    score: float
    planner_seeded: bool
    original_seeded: bool


_ResolvedPathKey = tuple[float, int, float, int, int, str, str, str]


@dataclass(frozen=True)
class _ResolvedState:
    signal: CodeSignal
    score: float
    hops: int
    min_confidence: float
    key: _ResolvedPathKey
    seed_key: str


@dataclass(frozen=True)
class _ResolvedStep:
    state: _ResolvedState
    graph_score_key: str


@dataclass(frozen=True)
class _ResolvedEdge:
    key: _ResolvedPathKey
    step: _ResolvedStep | None


@dataclass(frozen=True)
class _LegacyState:
    signal_id: str
    score: float
    depth: int
    planner_seeded: bool
    original_seeded: bool


def anchor_candidates(
    store: sqlite_store.SQLiteStore,
    seed_candidates: list[RetrievalCandidate],
    config: ToolConfig,
    query: str = "",
    tokens: list[str] | None = None,
) -> list[RetrievalCandidate]:
    direct_seeds = [
        candidate
        for candidate in seed_candidates
        if candidate.score_parts.get("direct_text", 0.0) > 0
    ]
    if not direct_seeds:
        return []

    limit = max(config.retrieval.final_top_k * 3, config.retrieval.final_top_k)
    expanded: dict[str, RetrievalCandidate] = {}
    seed_ids = {candidate.chunk_id for candidate in direct_seeds}
    query_tokens = tokens or []

    for candidate in sorted(
        direct_seeds,
        key=lambda item: (
            -item.score_parts.get("direct_text", item.score),
            item.chunk_id,
        ),
    ):
        try:
            anchor_chunk = store.chunk_for_id(candidate.chunk_id)
        except KeyError:
            continue
        anchor_score = evidence_merge.bounded_score(
            candidate.score_parts.get("direct_text", candidate.score)
        )
        _add_same_file_anchor_candidates(
            store,
            expanded,
            seed_ids,
            anchor_chunk,
            anchor_score,
            limit,
            query,
            query_tokens,
        )
        if _is_document_or_config_anchor(anchor_chunk.file_path):
            _add_directory_anchor_candidates(
                store,
                expanded,
                seed_ids,
                anchor_chunk,
                anchor_score,
                limit,
            )
        if len(expanded) >= limit:
            break

    return list(expanded.values())


def _add_same_file_anchor_candidates(
    store: sqlite_store.SQLiteStore,
    expanded: dict[str, RetrievalCandidate],
    seed_ids: set[str],
    anchor_chunk: DocumentChunk,
    anchor_score: float,
    limit: int,
    query: str,
    tokens: list[str],
) -> None:
    score = anchor_score * 0.80
    for chunk in store.chunks_for_file(anchor_chunk.file_path, limit):
        if chunk.chunk_id in seed_ids:
            continue
        if _should_skip_same_file_anchor_candidate(chunk, query, tokens):
            continue
        _put_anchor_candidate(
            expanded,
            chunk.chunk_id,
            score,
            "same_file_anchor",
        )
        if len(expanded) >= limit:
            return


def _should_skip_same_file_anchor_candidate(
    chunk: DocumentChunk,
    query: str,
    tokens: list[str],
) -> bool:
    role = file_roles._generic_file_role(chunk, query, tokens)
    return role.name == "generated_schema" or (
        role.name == "template" and role.penalty > 0
    )


def _add_directory_anchor_candidates(
    store: sqlite_store.SQLiteStore,
    expanded: dict[str, RetrievalCandidate],
    seed_ids: set[str],
    anchor_chunk: DocumentChunk,
    anchor_score: float,
    limit: int,
) -> None:
    score = anchor_score * 0.55
    for chunk in store.chunks_in_directory(anchor_chunk.file_path.parent, limit):
        if chunk.chunk_id in seed_ids:
            continue
        if _is_document_or_config_anchor(chunk.file_path):
            continue
        _put_anchor_candidate(
            expanded,
            chunk.chunk_id,
            score,
            "directory_anchor",
        )
        if len(expanded) >= limit:
            return


def _put_anchor_candidate(
    expanded: dict[str, RetrievalCandidate],
    chunk_id: str,
    score: float,
    anchor_key: str,
) -> None:
    existing = expanded.get(chunk_id)
    if existing is not None and existing.score >= score:
        return
    score_parts = {
        "anchored_relation": score,
        "original_relation": score,
        anchor_key: score,
    }
    expanded[chunk_id] = RetrievalCandidate(
        chunk_id=chunk_id,
        score=score,
        source="anchored_relation",
        score_parts=score_parts,
    )


def _is_document_or_config_anchor(path: Path) -> bool:
    suffix = path.suffix.lower()
    return suffix in {".md", ".yml", ".yaml", ".json", ".properties"}


def relation_candidates(
    store: sqlite_store.SQLiteStore,
    seed_candidates: list[RetrievalCandidate],
    config: ToolConfig,
    *,
    graph_session: sqlite_store.GraphReadSession | None = None,
    test_intent: bool = False,
    protected_chunk_ids: set[str] | None = None,
) -> list[RetrievalCandidate]:
    if graph_session is not None:
        if graph_session.capability.status == "stale":
            return []
        protected = protected_chunk_ids or set()
        if graph_session.capability.status == "ready":
            initial_signals = _ready_initial_relation_signals(
                graph_session,
                seed_candidates,
            )
            resolved = _resolved_relation_candidates(
                graph_session,
                seed_candidates,
                initial_signals=initial_signals,
                test_intent=test_intent,
                protected_chunk_ids=protected,
            )
            if graph_session.graph_fault is not None:
                return []
            legacy = _session_legacy_relation_candidates(
                graph_session,
                seed_candidates,
                initial_signals=initial_signals,
                candidate_limit=max(
                    0,
                    relation_policy.MAX_RELATION_EXPANDED_CANDIDATES
                    - len(resolved),
                ),
                protected_chunk_ids=protected,
            )
            if graph_session.graph_fault is not None:
                return []
            return _merge_session_relation_candidates(resolved, legacy)
        initial_signals = _legacy_initial_relation_signals(
            graph_session,
            seed_candidates,
            config,
        )
        return _session_legacy_relation_candidates(
            graph_session,
            seed_candidates,
            initial_signals=initial_signals,
            candidate_limit=relation_policy.MAX_RELATION_EXPANDED_CANDIDATES,
            protected_chunk_ids=protected,
        )

    relation_reader = store

    if not seed_candidates:
        return []

    source_limit = max(
        config.retrieval.semantic_top_k
        + config.retrieval.lexical_top_k
        + config.retrieval.final_top_k,
        config.retrieval.final_top_k,
    )
    if source_limit <= 0:
        return []

    expanded_by_chunk: dict[str, RetrievalCandidate] = {}
    seen_chunks = {candidate.chunk_id for candidate in seed_candidates}
    seed_scores = {
        candidate.chunk_id: _candidate_relation_seed(candidate)
        for candidate in seed_candidates
    }
    visited_signals: set[str] = set()
    frontier: list[tuple[str, float, int, bool, bool]] = []
    ordered_seed_candidates = sorted(
        seed_candidates,
        key=lambda item: (
            _relation_seed_source_priority(item.score_parts),
            -seed_scores[item.chunk_id].score,
            item.chunk_id,
        ),
    )[:source_limit]
    seed_chunk_ids = [
        candidate.chunk_id
        for candidate in ordered_seed_candidates
        if seed_scores[candidate.chunk_id].score > 0
    ]
    seed_signals_by_chunk = relation_reader.signals_for_chunks(seed_chunk_ids)

    for candidate in ordered_seed_candidates:
        relation_seed = seed_scores[candidate.chunk_id]
        if relation_seed.score <= 0:
            continue
        for signal in seed_signals_by_chunk.get(candidate.chunk_id, []):
            if signal.signal_id in visited_signals:
                continue
            visited_signals.add(signal.signal_id)
            frontier.append(
                (
                    signal.signal_id,
                    relation_seed.score,
                    0,
                    relation_seed.planner_seeded,
                    relation_seed.original_seeded,
                )
            )

    while frontier:
        active_frontier = [
            source
            for source in frontier
            if source[2] < relation_policy.MAX_EXPANSION_DEPTH
        ]
        if not active_frontier:
            break

        relations_by_source = relation_reader.relations_for_sources(
            [source_signal_id for source_signal_id, *_ in active_frontier]
        )
        relation_steps: list[tuple[str, float, int, bool, bool]] = []
        target_names: list[str] = []
        for (
            source_signal_id,
            current_score,
            depth,
            planner_seeded,
            original_seeded,
        ) in active_frontier:
            next_depth = depth + 1
            for relation in relations_by_source.get(source_signal_id, []):
                if relation.confidence < relation_policy._MIN_RELATION_CONFIDENCE:
                    continue
                next_score = (
                    current_score * relation.confidence * _RELATION_SCORE_DECAY
                )
                relation_steps.append(
                    (
                        relation.target_name,
                        next_score,
                        next_depth,
                        planner_seeded,
                        original_seeded,
                    )
                )
                target_names.append(relation.target_name)

        if not relation_steps:
            break

        remaining = relation_policy.MAX_EXPANSION_CANDIDATES - len(expanded_by_chunk)
        if remaining <= 0:
            _log_expansion_limit()
            return sorted(
                expanded_by_chunk.values(),
                key=lambda candidate: (-candidate.score, candidate.chunk_id),
            )
        chunks_by_target = relation_reader.chunks_matching_signal_or_symbols(
            target_names,
            remaining,
        )
        reached_chunk_ids: list[str] = []
        signal_seed_by_chunk: dict[str, tuple[float, int, bool, bool]] = {}
        for (
            target_name,
            next_score,
            next_depth,
            planner_seeded,
            original_seeded,
        ) in relation_steps:
            remaining = (
                relation_policy.MAX_EXPANSION_CANDIDATES - len(expanded_by_chunk)
            )
            if remaining <= 0:
                _log_expansion_limit()
                return sorted(
                    expanded_by_chunk.values(),
                    key=lambda candidate: (-candidate.score, candidate.chunk_id),
                )

            for chunk in chunks_by_target.get(target_name, [])[:remaining]:
                existing = expanded_by_chunk.get(chunk.chunk_id)
                seed_score = seed_scores.get(
                    chunk.chunk_id,
                    _RelationSeed(0.0, False, False),
                ).score
                should_add_relation = (
                    chunk.chunk_id not in seed_scores or next_score > seed_score
                )
                if should_add_relation and (
                    existing is None or next_score > existing.score
                ):
                    score_parts = {"relation": next_score}
                    if planner_seeded:
                        score_parts["planner_relation"] = next_score
                    if original_seeded:
                        score_parts["original_relation"] = next_score
                    expanded_by_chunk[chunk.chunk_id] = RetrievalCandidate(
                        chunk_id=chunk.chunk_id,
                        score=next_score,
                        source="relation",
                        score_parts=score_parts,
                    )

                if chunk.chunk_id not in seen_chunks:
                    seen_chunks.add(chunk.chunk_id)
                    if (
                        len(expanded_by_chunk)
                        >= relation_policy.MAX_EXPANSION_CANDIDATES
                    ):
                        _log_expansion_limit()
                        return sorted(
                            expanded_by_chunk.values(),
                            key=lambda candidate: (
                                -candidate.score,
                                candidate.chunk_id,
                            ),
                        )

                next_signal_seed = (
                    next_score,
                    next_depth,
                    planner_seeded,
                    original_seeded,
                )
                existing_signal_seed = signal_seed_by_chunk.get(chunk.chunk_id)
                if existing_signal_seed is None:
                    signal_seed_by_chunk[chunk.chunk_id] = next_signal_seed
                    reached_chunk_ids.append(chunk.chunk_id)
                elif next_score > existing_signal_seed[0]:
                    signal_seed_by_chunk[chunk.chunk_id] = next_signal_seed

        next_frontier: list[tuple[str, float, int, bool, bool]] = []
        if reached_chunk_ids:
            signals_by_chunk = relation_reader.signals_for_chunks(reached_chunk_ids)
            for chunk_id in reached_chunk_ids:
                (
                    next_score,
                    next_depth,
                    planner_seeded,
                    original_seeded,
                ) = signal_seed_by_chunk[chunk_id]
                for signal in signals_by_chunk.get(chunk_id, []):
                    if signal.signal_id in visited_signals:
                        continue
                    visited_signals.add(signal.signal_id)
                    next_frontier.append(
                        (
                            signal.signal_id,
                            next_score,
                            next_depth,
                            planner_seeded,
                            original_seeded,
                        )
                    )
        frontier = next_frontier

    return sorted(
        expanded_by_chunk.values(),
        key=lambda candidate: (-candidate.score, candidate.chunk_id),
    )


def _resolved_relation_candidates(
    session: sqlite_store.GraphReadSession,
    seed_candidates: list[RetrievalCandidate],
    *,
    initial_signals: list[tuple[CodeSignal, _RelationSeed]],
    test_intent: bool,
    protected_chunk_ids: set[str],
) -> list[RetrievalCandidate]:
    if not seed_candidates or session.graph_fault is not None:
        return []

    seeds_by_chunk = {
        candidate.chunk_id: _candidate_relation_seed(candidate)
        for candidate in seed_candidates
    }
    if not initial_signals:
        return []

    frontier: list[tuple[_ResolvedPathKey, int, _ResolvedState]] = []
    best_signal_keys: dict[str, _ResolvedPathKey] = {}
    frontier_entries = 0
    sequence = 0

    def push_state(state: _ResolvedState) -> bool:
        nonlocal frontier_entries, sequence
        current = best_signal_keys.get(state.signal.signal_id)
        if current is not None and state.key >= current:
            return True
        if frontier_entries >= relation_policy.MAX_FRONTIER_ENTRIES_PER_QUERY:
            session.record_graph_truncation()
            return False
        best_signal_keys[state.signal.signal_id] = state.key
        heapq.heappush(frontier, (state.key, sequence, state))
        sequence += 1
        frontier_entries += 1
        return True

    for signal, seed in initial_signals:
        seed_key = (
            "graph_seed_original"
            if seed.original_seeded
            else "graph_seed_planner"
        )
        key: _ResolvedPathKey = (
            -seed.score,
            0,
            -1.0,
            -1,
            -1,
            "",
            signal.signal_id,
            signal.chunk_id,
        )
        if not push_state(
            _ResolvedState(
                signal=signal,
                score=seed.score,
                hops=0,
                min_confidence=1.0,
                key=key,
                seed_key=seed_key,
            )
        ):
            return []

    expanded: dict[str, tuple[_ResolvedPathKey, RetrievalCandidate]] = {}
    signals_popped = 0
    edges_examined = 0
    stop_after_item = False

    while frontier and not stop_after_item:
        if signals_popped >= relation_policy.MAX_SIGNALS_POPPED_PER_QUERY:
            session.record_graph_truncation()
            break
        key, _sequence, state = heapq.heappop(frontier)
        signals_popped += 1
        if best_signal_keys.get(state.signal.signal_id) != key:
            continue
        if state.hops >= relation_policy.MAX_RESOLVED_GRAPH_HOPS:
            continue

        outgoing = session.outgoing_relations(
            state.signal.signal_id,
            limit=relation_policy.MAX_EDGES_PER_SIGNAL_DIRECTION + 1,
        )
        incoming = session.incoming_relations(
            state.signal.signal_id,
            limit=relation_policy.MAX_EDGES_PER_SIGNAL_DIRECTION + 1,
        )
        if len(outgoing) > relation_policy.MAX_EDGES_PER_SIGNAL_DIRECTION:
            session.record_graph_truncation()
            outgoing = outgoing[: relation_policy.MAX_EDGES_PER_SIGNAL_DIRECTION]
        if len(incoming) > relation_policy.MAX_EDGES_PER_SIGNAL_DIRECTION:
            session.record_graph_truncation()
            incoming = incoming[: relation_policy.MAX_EDGES_PER_SIGNAL_DIRECTION]

        raw_edges = [
            (relation, direction)
            for direction, relations in (("outgoing", outgoing), ("incoming", incoming))
            for relation in relations
        ]
        steps: list[_ResolvedStep] = []
        for relation, direction in sorted(
            raw_edges,
            key=lambda item: _resolved_edge_sort_key(
                state,
                item[0],
                direction=item[1],
            ),
        ):
            if edges_examined >= relation_policy.MAX_EDGES_EXAMINED_PER_QUERY:
                session.record_graph_truncation()
                stop_after_item = True
                break
            edges_examined += 1
            edge = _resolved_edge(
                session,
                state,
                relation,
                direction=direction,
                test_intent=test_intent,
            )
            if session.graph_fault is not None:
                return []
            if edge is not None and edge.step is not None:
                steps.append(edge.step)

        for step in steps:
            next_state = step.state
            chunk_id = next_state.signal.chunk_id
            existing_seed = seeds_by_chunk.get(
                chunk_id,
                _RelationSeed(0.0, False, False),
            )
            should_add = (
                chunk_id not in protected_chunk_ids
                and next_state.score > existing_seed.score
            )
            existing = expanded.get(chunk_id)
            if should_add and (existing is None or next_state.key < existing[0]):
                score = evidence_merge.bounded_score(next_state.score)
                expanded[chunk_id] = (
                    next_state.key,
                    RetrievalCandidate(
                        chunk_id=chunk_id,
                        score=score,
                        source="relation",
                        score_parts={
                            step.graph_score_key: score,
                            "resolved_relation": 1.0,
                            next_state.seed_key: 1.0,
                        },
                    ),
                )
                if (
                    len(expanded)
                    >= relation_policy.MAX_RELATION_EXPANDED_CANDIDATES
                ):
                    session.record_graph_truncation()
                    stop_after_item = True

            if next_state.hops >= relation_policy.MAX_RESOLVED_GRAPH_HOPS:
                continue
            overlapping = session.signals_for_chunk(next_state.signal.chunk_id)
            if len(overlapping) > relation_policy.MAX_SIGNALS_PER_FILE:
                session.record_graph_truncation()
                overlapping = overlapping[: relation_policy.MAX_SIGNALS_PER_FILE]
            for signal in overlapping:
                if not push_state(
                    _ResolvedState(
                        signal=signal,
                        score=next_state.score,
                        hops=next_state.hops,
                        min_confidence=next_state.min_confidence,
                        key=next_state.key,
                        seed_key=next_state.seed_key,
                    )
                ):
                    stop_after_item = True
                    break
            if stop_after_item:
                break

    return [
        candidate
        for _key, candidate in sorted(expanded.values(), key=lambda item: item[0])
    ]


def _ready_initial_relation_signals(
    session: sqlite_store.GraphReadSession,
    seed_candidates: list[RetrievalCandidate],
) -> list[tuple[CodeSignal, _RelationSeed]]:
    ordered_seeds = _ordered_relation_seeds(seed_candidates)
    seed_specs = [
        (
            candidate.chunk_id,
            rank,
            _relation_seed_source_priority(candidate.score_parts),
        )
        for rank, (candidate, _seed) in enumerate(ordered_seeds)
    ]
    rows = session.initial_graph_signals(
        seed_specs,
        limit=relation_policy.MAX_GRAPH_SEED_SIGNALS + 1,
    )
    if len(rows) > relation_policy.MAX_GRAPH_SEED_SIGNALS:
        session.record_graph_truncation()
        rows = rows[: relation_policy.MAX_GRAPH_SEED_SIGNALS]
    return [
        (signal, ordered_seeds[seed_rank][1])
        for signal, seed_rank, _source_priority in rows
    ]


def _legacy_initial_relation_signals(
    session: sqlite_store.GraphReadSession,
    seed_candidates: list[RetrievalCandidate],
    config: ToolConfig,
) -> list[tuple[CodeSignal, _RelationSeed]]:
    source_limit = max(
        config.retrieval.semantic_top_k
        + config.retrieval.lexical_top_k
        + config.retrieval.final_top_k,
        config.retrieval.final_top_k,
    )
    if source_limit <= 0:
        return []
    initial: list[tuple[CodeSignal, _RelationSeed]] = []
    for candidate, seed in _ordered_relation_seeds(seed_candidates)[:source_limit]:
        signals = session.signals_for_chunk(
            candidate.chunk_id,
            limit=relation_policy.MAX_SIGNALS_PER_FILE + 1,
        )
        if len(signals) > relation_policy.MAX_SIGNALS_PER_FILE:
            session.record_graph_truncation()
            signals = signals[: relation_policy.MAX_SIGNALS_PER_FILE]
        for signal in signals:
            initial.append((signal, seed))
            if len(initial) > relation_policy.MAX_GRAPH_SEED_SIGNALS:
                session.record_graph_truncation()
                return initial[: relation_policy.MAX_GRAPH_SEED_SIGNALS]
    return initial


def _ordered_relation_seeds(
    seed_candidates: list[RetrievalCandidate],
) -> list[tuple[RetrievalCandidate, _RelationSeed]]:
    seed_scores = {
        candidate.chunk_id: _candidate_relation_seed(candidate)
        for candidate in seed_candidates
    }
    ordered = sorted(
        (
            (candidate, seed_scores[candidate.chunk_id])
            for candidate in seed_candidates
            if seed_scores[candidate.chunk_id].score > 0
        ),
        key=lambda item: (
            _relation_seed_source_priority(item[0].score_parts),
            -item[1].score,
            item[0].chunk_id,
        ),
    )
    unique: list[tuple[RetrievalCandidate, _RelationSeed]] = []
    seen_chunks: set[str] = set()
    for candidate, seed in ordered:
        if candidate.chunk_id in seen_chunks:
            continue
        seen_chunks.add(candidate.chunk_id)
        unique.append((candidate, seed))
    return unique


def _session_legacy_relation_candidates(
    session: sqlite_store.GraphReadSession,
    seed_candidates: list[RetrievalCandidate],
    *,
    initial_signals: list[tuple[CodeSignal, _RelationSeed]],
    candidate_limit: int,
    protected_chunk_ids: set[str],
) -> list[RetrievalCandidate]:
    if candidate_limit <= 0 or not initial_signals:
        return []

    seed_scores = {
        candidate.chunk_id: _candidate_relation_seed(candidate)
        for candidate in seed_candidates
    }
    expanded: dict[str, RetrievalCandidate] = {}
    visited_signals: set[str] = set()
    frontier: list[_LegacyState] = []
    frontier_entries = 0
    for signal, seed in initial_signals:
        if signal.signal_id in visited_signals:
            continue
        visited_signals.add(signal.signal_id)
        frontier.append(
            _LegacyState(
                signal.signal_id,
                seed.score,
                0,
                seed.planner_seeded,
                seed.original_seeded,
            )
        )
        frontier_entries += 1

    signals_popped = 0
    edges_examined = 0
    while frontier:
        active: list[_LegacyState] = []
        hit_signal_cap = False
        for state in frontier:
            if state.depth >= relation_policy.MAX_LEGACY_RELATION_HOPS:
                continue
            if signals_popped >= relation_policy.MAX_SIGNALS_POPPED_PER_QUERY:
                session.record_graph_truncation()
                hit_signal_cap = True
                break
            signals_popped += 1
            active.append(state)
        if not active:
            break

        relations_by_source = session.relations_for_sources(
            [state.signal_id for state in active]
        )
        steps: list[tuple[str, float, int, bool, bool]] = []
        target_names: list[str] = []
        hit_edge_cap = False
        for state in active:
            for relation in relations_by_source.get(state.signal_id, ()):
                if edges_examined >= relation_policy.MAX_EDGES_EXAMINED_PER_QUERY:
                    session.record_graph_truncation()
                    hit_edge_cap = True
                    break
                edges_examined += 1
                if relation.confidence < relation_policy._MIN_RELATION_CONFIDENCE:
                    continue
                next_score = (
                    state.score * relation.confidence * _RELATION_SCORE_DECAY
                )
                steps.append(
                    (
                        relation.target_name,
                        next_score,
                        state.depth + 1,
                        state.planner_seeded,
                        state.original_seeded,
                    )
                )
                target_names.append(relation.target_name)
            if hit_edge_cap:
                break
        if not steps:
            break

        remaining = candidate_limit - len(expanded)
        if remaining <= 0:
            session.record_graph_truncation()
            break
        chunks_by_target = session.chunks_matching_signal_or_symbols(
            target_names,
            remaining,
        )
        reached: dict[str, tuple[float, int, bool, bool]] = {}
        reached_order: list[str] = []
        hit_candidate_cap = False
        for target_name, score, depth, planner_seeded, original_seeded in steps:
            for chunk in chunks_by_target.get(target_name, ()):
                seed_score = seed_scores.get(
                    chunk.chunk_id,
                    _RelationSeed(0.0, False, False),
                ).score
                existing = expanded.get(chunk.chunk_id)
                if (
                    chunk.chunk_id not in protected_chunk_ids
                    and score > seed_score
                    and (existing is None or score > existing.score)
                ):
                    score_parts = {"relation": score}
                    if planner_seeded:
                        score_parts["planner_relation"] = score
                    if original_seeded:
                        score_parts["original_relation"] = score
                    expanded[chunk.chunk_id] = RetrievalCandidate(
                        chunk_id=chunk.chunk_id,
                        score=score,
                        source="relation",
                        score_parts=score_parts,
                    )
                    if len(expanded) >= candidate_limit:
                        session.record_graph_truncation()
                        hit_candidate_cap = True

                next_seed = (score, depth, planner_seeded, original_seeded)
                current_seed = reached.get(chunk.chunk_id)
                if current_seed is None:
                    reached[chunk.chunk_id] = next_seed
                    reached_order.append(chunk.chunk_id)
                elif score > current_seed[0]:
                    reached[chunk.chunk_id] = next_seed
                if hit_candidate_cap:
                    break
            if hit_candidate_cap:
                break
        if hit_candidate_cap or hit_edge_cap or hit_signal_cap:
            break

        next_frontier: list[_LegacyState] = []
        hit_frontier_cap = False
        for chunk_id in reached_order:
            score, depth, planner_seeded, original_seeded = reached[chunk_id]
            signals = session.signals_for_chunk(
                chunk_id,
                limit=relation_policy.MAX_SIGNALS_PER_FILE + 1,
            )
            if len(signals) > relation_policy.MAX_SIGNALS_PER_FILE:
                session.record_graph_truncation()
                signals = signals[: relation_policy.MAX_SIGNALS_PER_FILE]
            for signal in signals:
                if signal.signal_id in visited_signals:
                    continue
                if (
                    frontier_entries
                    >= relation_policy.MAX_FRONTIER_ENTRIES_PER_QUERY
                ):
                    session.record_graph_truncation()
                    hit_frontier_cap = True
                    break
                visited_signals.add(signal.signal_id)
                frontier_entries += 1
                next_frontier.append(
                    _LegacyState(
                        signal.signal_id,
                        score,
                        depth,
                        planner_seeded,
                        original_seeded,
                    )
                )
            if hit_frontier_cap:
                break
        if hit_frontier_cap:
            break
        frontier = next_frontier

    return sorted(
        expanded.values(),
        key=lambda candidate: (-candidate.score, candidate.chunk_id),
    )


def _merge_session_relation_candidates(
    resolved: list[RetrievalCandidate],
    legacy: list[RetrievalCandidate],
) -> list[RetrievalCandidate]:
    merged: dict[str, RetrievalCandidate] = {}
    for candidate in [*resolved, *legacy]:
        existing = merged.get(candidate.chunk_id)
        if existing is None:
            merged[candidate.chunk_id] = candidate
            continue
        score_parts = evidence_merge.merge_score_parts(
            existing.score_parts,
            candidate.score_parts,
        )
        merged[candidate.chunk_id] = RetrievalCandidate(
            chunk_id=candidate.chunk_id,
            score=max(existing.score, candidate.score),
            source="relation",
            score_parts=score_parts,
        )
    return sorted(
        merged.values(),
        key=lambda candidate: (-candidate.score, candidate.chunk_id),
    )


def _resolved_edge(
    session: sqlite_store.GraphReadSession,
    state: _ResolvedState,
    relation: CodeRelation,
    *,
    direction: str,
    test_intent: bool,
) -> _ResolvedEdge | None:
    neighbor_id = (
        relation.target_signal_id
        if direction == "outgoing"
        else relation.source_signal_id
    )
    neighbor = session.signal_for_id(neighbor_id)
    if neighbor is None or session.chunk_for_id(neighbor.chunk_id) is None:
        session.record_graph_fault("dangling_target")
        return None
    try:
        confidence = effective_relation_confidence(
            resolution=relation.resolution,
            target_signal_id=relation.target_signal_id,
            producer_confidence=relation.producer_confidence,
            resolution_confidence=relation.resolution_confidence,
        )
    except ValueError:
        session.record_graph_fault("integrity_check_failed")
        return None
    weight = relation_policy.RELATION_WEIGHTS.get(relation.kind)
    score_weight = float(weight) if weight is not None else 0.0
    score = evidence_merge.bounded_score(
        state.score
        * confidence
        * score_weight
        * relation_policy.GRAPH_SCORE_DECAY
    )
    hops = state.hops + 1
    min_confidence = min(state.min_confidence, confidence)
    key: _ResolvedPathKey = (
        -score,
        hops,
        -min_confidence,
        relation_policy.RELATION_KIND_PRIORITY.get(
            relation.kind,
            len(relation_policy.RELATION_KIND_PRIORITY),
        ),
        0 if direction == "outgoing" else 1,
        relation.source_signal_id,
        relation.target_signal_id,
        neighbor.chunk_id,
    )
    relation_direction = relation_policy.RELATION_DIRECTIONS.get(relation.kind)
    graph_score_key = relation_policy.GRAPH_SCORE_KEY_BY_KIND.get(relation.kind)
    if (
        confidence < relation_policy._MIN_RELATION_CONFIDENCE
        or weight is None
        or graph_score_key is None
        or relation_direction is None
        or not _resolved_direction_allowed(
            relation_direction,
            direction=direction,
            test_intent=test_intent,
        )
    ):
        return _ResolvedEdge(key=key, step=None)
    return _ResolvedEdge(
        key=key,
        step=_ResolvedStep(
            state=_ResolvedState(
                signal=neighbor,
                score=score,
                hops=hops,
                min_confidence=min_confidence,
                key=key,
                seed_key=state.seed_key,
            ),
            graph_score_key=graph_score_key,
        ),
    )


def _resolved_edge_sort_key(
    state: _ResolvedState,
    relation: CodeRelation,
    *,
    direction: str,
) -> _ResolvedPathKey:
    try:
        confidence = effective_relation_confidence(
            resolution=relation.resolution,
            target_signal_id=relation.target_signal_id,
            producer_confidence=relation.producer_confidence,
            resolution_confidence=relation.resolution_confidence,
        )
    except ValueError:
        confidence = 0.0
    weight = relation_policy.RELATION_WEIGHTS.get(relation.kind)
    score = evidence_merge.bounded_score(
        state.score
        * confidence
        * (float(weight) if weight is not None else 0.0)
        * relation_policy.GRAPH_SCORE_DECAY
    )
    return (
        -score,
        state.hops + 1,
        -min(state.min_confidence, confidence),
        relation_policy.RELATION_KIND_PRIORITY.get(
            relation.kind,
            len(relation_policy.RELATION_KIND_PRIORITY),
        ),
        0 if direction == "outgoing" else 1,
        relation.source_signal_id,
        relation.target_signal_id,
        "",
    )


def _resolved_direction_allowed(
    policy: str,
    *,
    direction: str,
    test_intent: bool,
) -> bool:
    if policy == "intent_gated_both":
        return test_intent
    if policy == "both":
        return True
    return policy == direction


def _relation_seed_source_priority(score_parts: dict[str, float]) -> int:
    if score_parts.get("relation", 0.0) > 0:
        return 0
    if score_parts.get("signal", 0.0) > 0:
        return 1
    if score_parts.get("direct_text", 0.0) > 0:
        return 2
    if max(
        score_parts.get("anchored_relation", 0.0),
        score_parts.get("same_file_anchor", 0.0),
        score_parts.get("directory_anchor", 0.0),
    ) > 0:
        return 3
    if score_parts.get("planner_signal", 0.0) > 0:
        return 4
    return 5


def _candidate_relation_seed(candidate: RetrievalCandidate) -> _RelationSeed:
    relation_score = candidate.score_parts.get("relation", 0.0)
    if relation_score > 0:
        planner_seeded = candidate.score_parts.get("planner_relation", 0.0) > 0
        original_seeded = candidate.score_parts.get("original_relation", 0.0) > 0
        if not planner_seeded and not original_seeded:
            original_seeded = True
        return _RelationSeed(
            evidence_merge.bounded_score(relation_score),
            planner_seeded,
            original_seeded,
        )

    signal_score = candidate.score_parts.get("signal", 0.0)
    planner_signal_score = candidate.score_parts.get("planner_signal", 0.0)
    if signal_score > 0:
        return _RelationSeed(
            evidence_merge.bounded_score(signal_score),
            planner_signal_score > 0,
            True,
        )

    direct_text_score = candidate.score_parts.get("direct_text", 0.0)
    if direct_text_score > 0:
        return _RelationSeed(
            evidence_merge.bounded_score(direct_text_score),
            False,
            True,
        )

    anchored_score = max(
        candidate.score_parts.get("anchored_relation", 0.0),
        candidate.score_parts.get("same_file_anchor", 0.0),
        candidate.score_parts.get("directory_anchor", 0.0),
    )
    if anchored_score > 0:
        return _RelationSeed(
            evidence_merge.bounded_score(anchored_score),
            False,
            True,
        )

    if planner_signal_score > 0:
        return _RelationSeed(
            evidence_merge.bounded_score(planner_signal_score) * 0.65,
            True,
            False,
        )

    return _RelationSeed(0.0, False, False)


def _log_expansion_limit() -> None:
    logger.warning(
        "relation expansion hit candidate limit (%s); returning partial candidates",
        relation_policy.MAX_EXPANSION_CANDIDATES,
    )
