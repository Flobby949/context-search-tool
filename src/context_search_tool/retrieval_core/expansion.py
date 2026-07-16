from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from context_search_tool import sqlite_store
from context_search_tool.config import ToolConfig
from context_search_tool.models import DocumentChunk, RetrievalCandidate
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
) -> list[RetrievalCandidate]:
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
    seed_signals_by_chunk = store.signals_for_chunks(seed_chunk_ids)

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

        relations_by_source = store.relations_for_sources(
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
        chunks_by_target = store.chunks_matching_signal_or_symbols(
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
            signals_by_chunk = store.signals_for_chunks(reached_chunk_ids)
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
