from __future__ import annotations

import sqlite3
import logging
from collections import Counter, deque
from dataclasses import dataclass, field
from pathlib import Path

from context_search_tool.chunker import expand_lines
from context_search_tool.config import ToolConfig
from context_search_tool.embeddings import provider_from_config
from context_search_tool.manifest import assert_manifest_compatible
from context_search_tool.models import (
    CodeSignal,
    DocumentChunk,
    QueryPlan,
    RetrievalCandidate,
    RetrievalResult,
    RetrievalSummary,
)
from context_search_tool.paths import index_dir_for
from context_search_tool.query_planner import (
    QueryPlanner,
    expand_query_plan_tokens,
    planner_from_config,
    planner_hint_tokens,
)
from context_search_tool.sqlite_store import SQLiteStore
from context_search_tool.tokenizer import tokenize_query
from context_search_tool.vector_store import NumpyVectorStore


logger = logging.getLogger(__name__)

MAX_EXPANSION_DEPTH = 3
MAX_EXPANSION_CANDIDATES = 1000
_MIN_RELATION_CONFIDENCE = 0.5
_RELATION_SCORE_DECAY = 0.8


@dataclass(frozen=True)
class QueryBundle:
    query: str
    expanded_tokens: list[str]
    results: list[RetrievalResult]
    followup_keywords: list[str]
    summary: RetrievalSummary = field(default_factory=RetrievalSummary)
    planner: QueryPlan = field(default_factory=QueryPlan.disabled_default)


@dataclass(frozen=True)
class _RankedChunk:
    chunk: DocumentChunk
    score: float
    score_parts: dict[str, float]
    reasons: list[str]
    rank_tier: int


@dataclass(frozen=True)
class _ExpandedResult:
    chunk_ids: list[str]
    file_path: Path
    start_line: int
    end_line: int
    content: str
    score: float
    score_parts: dict[str, float]
    reasons: list[str]
    followup_keywords: list[str]
    rank_tier: int


def query_repository(
    repo: Path,
    query: str,
    config: ToolConfig,
    context_lines: int | None = None,
    full_file: bool = False,
    planner: QueryPlanner | None = None,
) -> QueryBundle:
    repo = repo.resolve()
    original_tokens = _dedupe(tokenize_query(query))
    query_planner = planner or planner_from_config(config.query_planner)
    plan = query_planner.plan(query)
    tokens = expand_query_plan_tokens(query, plan)
    original_plan_tokens = expand_query_plan_tokens(
        query,
        QueryPlan(original_query=query),
    )
    hint_tokens = (
        planner_hint_tokens(_dedupe([*original_tokens, *original_plan_tokens]), tokens)
        if plan.status == "ok"
        else []
    )
    index_dir = index_dir_for(repo)
    db_path = index_dir / "index.sqlite"
    if not db_path.exists():
        return QueryBundle(
            query=query,
            expanded_tokens=tokens,
            results=[],
            followup_keywords=[],
            planner=plan,
        )

    assert_manifest_compatible(repo, config)

    store = SQLiteStore(db_path)
    try:
        deleted_ids = store.deleted_chunk_ids()
    except sqlite3.Error:
        return QueryBundle(
            query=query,
            expanded_tokens=tokens,
            results=[],
            followup_keywords=[],
            planner=plan,
        )

    initial_candidates = _initial_candidates(
        index_dir,
        store,
        query,
        original_tokens,
        config,
        deleted_ids,
    )
    signal_candidates = _signal_candidates(store, original_tokens, config)
    planner_candidates = _planner_hint_candidates(store, hint_tokens, config)
    direct_candidates = _merge_candidates(
        [*initial_candidates, *signal_candidates, *planner_candidates]
    )
    relation_candidates = _relation_expansion_candidates(
        store,
        list(direct_candidates.values()),
        config,
    )
    candidates = _merge_candidates(
        [
            *direct_candidates.values(),
            *relation_candidates,
        ]
    )
    if not candidates:
        return QueryBundle(
            query=query,
            expanded_tokens=tokens,
            results=[],
            followup_keywords=[],
            planner=plan,
        )

    ranked_chunks = _rank_chunks(store, candidates, original_tokens, query)
    expanded = _expand_ranked_chunks(repo, ranked_chunks, config, context_lines, full_file)
    visible_results = expanded[: config.retrieval.final_top_k]
    summary, result_reasons = _summarize_results(store, visible_results)
    results = [
        RetrievalResult(
            file_path=item.file_path,
            start_line=item.start_line,
            end_line=item.end_line,
            content=item.content,
            score=item.score,
            score_parts=item.score_parts,
            reasons=_dedupe(item.reasons + result_reasons[index]),
            followup_keywords=item.followup_keywords,
        )
        for index, item in enumerate(visible_results)
    ]
    return QueryBundle(
        query=query,
        expanded_tokens=tokens,
        results=results,
        followup_keywords=_followup_keywords(results),
        summary=summary,
        planner=plan,
    )


def _summarize_results(
    store: SQLiteStore,
    visible_results: list[_ExpandedResult],
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

        result_reasons.append(_dedupe(chunk_reasons))
        summary.entry_points.extend(entry_points)
        summary.implementation.extend(impl)
        summary.related_types.extend(related)
        summary.possibly_legacy.extend(legacy)

    summary.entry_points = _ordered_unique(summary.entry_points)
    summary.implementation = _ordered_unique(summary.implementation)
    summary.related_types = _ordered_unique(summary.related_types)
    summary.possibly_legacy = _ordered_unique(summary.possibly_legacy)
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
        endpoint.extend(_ordered_unique(endpoint_signals))
    elif _is_controller_name(chunk.file_path.stem) or any(
        _is_controller_name(name) for name in symbol_names
    ):
        endpoint.append(_primary_chunk_name(chunk))

    names = _ordered_unique(
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
        _ordered_unique(endpoint),
        _ordered_unique(implementation),
        _ordered_unique(related_types),
        _ordered_unique(legacy),
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
    store: SQLiteStore,
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

    relation_targets = _ordered_unique(
        [chunk.file_path.stem] + [signal.name for signal in signals]
    )
    for target_name in relation_targets:
        try:
            if store.relations_targeting(target_name):
                return True
        except sqlite3.Error:
            continue

    return False


def _ordered_unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        normalized = value.lower()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(value)
    return ordered


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


def _initial_candidates(
    index_dir: Path,
    store: SQLiteStore,
    query: str,
    original_tokens: list[str],
    config: ToolConfig,
    deleted_ids: set[str],
) -> list[RetrievalCandidate]:
    return [
        *_semantic_candidates(index_dir, query, config, deleted_ids),
        *_lexical_candidates(store, original_tokens, config.retrieval.lexical_top_k),
        *store.path_symbol_search(original_tokens, config.retrieval.lexical_top_k),
    ]


def _semantic_candidates(
    index_dir: Path,
    query: str,
    config: ToolConfig,
    deleted_ids: set[str],
) -> list[RetrievalCandidate]:
    query_vector = provider_from_config(config.embedding).embed_texts([query])[0]
    return [
        RetrievalCandidate(
            chunk_id=item.chunk_id,
            score=item.score,
            source="semantic",
            score_parts={"semantic": item.score},
        )
        for item in NumpyVectorStore(index_dir).search(
            query_vector,
            config.retrieval.semantic_top_k,
            deleted_ids,
        )
    ]


def _signal_candidates(
    store: SQLiteStore,
    tokens: list[str],
    config: ToolConfig,
    planner_hint: bool = False,
) -> list[RetrievalCandidate]:
    limit = max(
        config.retrieval.semantic_top_k,
        config.retrieval.lexical_top_k,
        config.retrieval.final_top_k,
    )
    source = "planner_signal" if planner_hint else "signal"
    score_key = "planner_signal" if planner_hint else "signal"
    candidates: list[RetrievalCandidate] = []
    for signal in store.signal_search(tokens, limit):
        score = _signal_score(signal.name, signal.tokens, signal.metadata, tokens)
        if score <= 0:
            continue
        candidates.append(
            RetrievalCandidate(
                chunk_id=signal.chunk_id,
                score=score,
                source=source,
                score_parts={score_key: score},
            )
        )
    return candidates


def _planner_hint_candidates(
    store: SQLiteStore,
    hint_tokens: list[str],
    config: ToolConfig,
) -> list[RetrievalCandidate]:
    if not hint_tokens:
        return []
    path_symbol = [
        RetrievalCandidate(
            chunk_id=item.chunk_id,
            score=item.score,
            source="planner_path_symbol",
            score_parts={"planner_path_symbol": item.score},
        )
        for item in store.path_symbol_search(
            hint_tokens,
            config.retrieval.lexical_top_k,
        )
    ]
    lexical = [
        RetrievalCandidate(
            chunk_id=item.chunk_id,
            score=item.score,
            source="planner_lexical",
            score_parts={"planner_lexical": item.score},
        )
        for item in _lexical_candidates(
            store,
            hint_tokens,
            config.retrieval.lexical_top_k,
        )
    ]
    signals = _signal_candidates(store, hint_tokens, config, planner_hint=True)
    return [*lexical, *path_symbol, *signals]


def _relation_expansion_candidates(
    store: SQLiteStore,
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
        candidate.chunk_id: _candidate_relation_seed_score(candidate)
        for candidate in seed_candidates
    }
    visited_signals: set[str] = set()
    queue: deque[tuple[str, float, int, bool]] = deque()

    for candidate in sorted(
        seed_candidates,
        key=lambda item: (-_candidate_relation_seed_score(item), item.chunk_id),
    )[:source_limit]:
        current_score = _candidate_relation_seed_score(candidate)
        if current_score <= 0:
            continue
        planner_seeded = _is_planner_hint_only(candidate.score_parts)
        for signal in store.signals_for_chunk(candidate.chunk_id):
            if signal.signal_id in visited_signals:
                continue
            visited_signals.add(signal.signal_id)
            queue.append((signal.signal_id, current_score, 0, planner_seeded))

    while queue:
        source_signal_id, current_score, depth, planner_seeded = queue.popleft()
        if depth >= MAX_EXPANSION_DEPTH:
            continue

        next_depth = depth + 1
        for relation in store.relations_for_source(source_signal_id):
            if relation.confidence < _MIN_RELATION_CONFIDENCE:
                continue

            next_score = current_score * relation.confidence * _RELATION_SCORE_DECAY
            remaining = MAX_EXPANSION_CANDIDATES - len(expanded_by_chunk)
            if remaining <= 0:
                _log_expansion_limit()
                return list(expanded_by_chunk.values())

            for chunk in store.chunks_matching_signal_or_symbol(
                relation.target_name,
                remaining,
            ):
                existing = expanded_by_chunk.get(chunk.chunk_id)
                seed_score = seed_scores.get(chunk.chunk_id, 0.0)
                should_add_relation = (
                    chunk.chunk_id not in seed_scores or next_score > seed_score
                )
                if should_add_relation and (
                    existing is None or next_score > existing.score
                ):
                    score_parts = {"relation": next_score}
                    if planner_seeded:
                        score_parts["planner_signal"] = next_score
                    expanded_by_chunk[chunk.chunk_id] = RetrievalCandidate(
                        chunk_id=chunk.chunk_id,
                        score=next_score,
                        source="relation",
                        score_parts=score_parts,
                    )

                if chunk.chunk_id not in seen_chunks:
                    seen_chunks.add(chunk.chunk_id)
                    if len(expanded_by_chunk) >= MAX_EXPANSION_CANDIDATES:
                        _log_expansion_limit()
                        return list(expanded_by_chunk.values())

                for signal in store.signals_for_chunk(chunk.chunk_id):
                    if signal.signal_id in visited_signals:
                        continue
                    visited_signals.add(signal.signal_id)
                    queue.append(
                        (signal.signal_id, next_score, next_depth, planner_seeded)
                    )

    return list(expanded_by_chunk.values())


def _candidate_base_score(candidate: RetrievalCandidate) -> float:
    return _bounded_score(max(candidate.score, *candidate.score_parts.values(), 0.0))


def _candidate_relation_seed_score(candidate: RetrievalCandidate) -> float:
    relation_score = candidate.score_parts.get("relation", 0.0)
    if relation_score > 0:
        return _bounded_score(relation_score)

    signal_score = candidate.score_parts.get("signal", 0.0)
    if signal_score > 0:
        return _bounded_score(signal_score)

    planner_signal_score = candidate.score_parts.get("planner_signal", 0.0)
    if planner_signal_score > 0:
        return _bounded_score(planner_signal_score) * 0.65

    return 0.0


def _log_expansion_limit() -> None:
    logger.warning(
        "relation expansion hit candidate limit (%s); returning partial candidates",
        MAX_EXPANSION_CANDIDATES,
    )


def _merge_candidates(
    candidates: list[RetrievalCandidate],
) -> dict[str, RetrievalCandidate]:
    merged: dict[str, RetrievalCandidate] = {}
    for candidate in candidates:
        existing = merged.get(candidate.chunk_id)
        score_parts = _normalized_score_parts(candidate)
        if existing is None:
            merged[candidate.chunk_id] = RetrievalCandidate(
                chunk_id=candidate.chunk_id,
                score=candidate.score,
                source=candidate.source,
                score_parts=score_parts,
            )
            continue

        merged[candidate.chunk_id] = RetrievalCandidate(
            chunk_id=candidate.chunk_id,
            score=max(existing.score, candidate.score),
            source=f"{existing.source},{candidate.source}",
            score_parts=_merge_score_parts(existing.score_parts, score_parts),
        )
    return merged


def _rank_chunks(
    store: SQLiteStore,
    candidates: dict[str, RetrievalCandidate],
    tokens: list[str],
    query: str,
) -> list[_RankedChunk]:
    ranked: list[_RankedChunk] = []
    for candidate in candidates.values():
        try:
            chunk = store.chunk_for_id(candidate.chunk_id)
        except KeyError:
            continue

        score_parts = dict(candidate.score_parts)
        coverage = _token_coverage(tokens, chunk)
        if coverage:
            score_parts["token_coverage"] = coverage

        plugin_boost = _plugin_boost(chunk)
        route_boost = _route_boost(chunk, query, tokens)
        plugin_boost += route_boost
        if plugin_boost:
            score_parts["plugin_boost"] = plugin_boost
        if route_boost:
            score_parts["route_boost"] = route_boost

        penalty = _generated_or_test_penalty(chunk)
        if penalty:
            score_parts["penalty"] = -penalty

        score = _combined_score(score_parts)
        ranked.append(
            _RankedChunk(
                chunk=chunk,
                score=score,
                score_parts=score_parts,
                reasons=_reasons(score_parts, query),
                rank_tier=_rank_tier(store, chunk, score_parts),
            )
        )

    return sorted(
        ranked,
        key=lambda item: (
            item.rank_tier,
            -item.score,
            item.chunk.file_path.as_posix(),
            item.chunk.start_line,
            item.chunk.chunk_id,
        ),
    )


def _expand_ranked_chunks(
    repo: Path,
    ranked_chunks: list[_RankedChunk],
    config: ToolConfig,
    context_lines: int | None,
    full_file: bool,
) -> list[_ExpandedResult]:
    expanded: list[_ExpandedResult] = []
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
        else:
            before, after = _context_window(config, context_lines)
            start_line, end_line, content = expand_lines(
                lines,
                ranked.chunk.start_line,
                ranked.chunk.end_line,
                before,
                after,
            )
        if full_file:
            end_line, content = _cap_content_bytes(
                content,
                start_line,
                config.index.max_full_file_bytes,
            )

        expanded.append(
            _ExpandedResult(
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
            )
        )

    merged = _merge_overlapping_results(expanded)
    if not full_file:
        return merged
    return [
        _cap_expanded_result(result, config.index.max_full_file_bytes)
        for result in merged
    ]


def _lexical_candidates(
    store: SQLiteStore,
    tokens: list[str],
    limit: int,
) -> list[RetrievalCandidate]:
    exact = store.lexical_search(tokens, limit)
    if exact or not tokens or limit <= 0:
        return exact

    scores: dict[str, float] = {}
    for token in tokens:
        for candidate in store.lexical_search([token], limit):
            scores[candidate.chunk_id] = (
                scores.get(candidate.chunk_id, 0.0) + candidate.score
            )

    ranked = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    return [
        RetrievalCandidate(
            chunk_id=chunk_id,
            score=score,
            source="lexical",
            score_parts={"lexical": score},
        )
        for chunk_id, score in ranked[:limit]
    ]


def _signal_score(
    name: str,
    signal_tokens: list[str],
    metadata: dict[str, object],
    query_tokens: list[str],
) -> float:
    normalized = [token.lower() for token in query_tokens if token]
    if not normalized:
        return 0.0

    name_text = name.lower()
    token_set = {token.lower() for token in signal_tokens}
    metadata_text = _metadata_text(metadata)
    path_tokens: set[str] = set()
    path_value = metadata.get("path")
    if isinstance(path_value, str):
        path_tokens = set(tokenize_query(path_value))
        path_text = path_value.lower()
    else:
        path_text = ""

    score = 0.0
    for token in normalized:
        token_score = 0.0
        if token in name_text:
            token_score = max(token_score, 1.0)
        if token in token_set:
            token_score = max(token_score, 1.0)
        if token in metadata_text:
            token_score = max(token_score, 1.0)
        if token in path_tokens or token in path_text:
            token_score = max(token_score, 0.9)
        score += token_score
    return score / len(normalized)


def _metadata_text(metadata: dict[str, object]) -> str:
    values: list[str] = []
    for key, value in metadata.items():
        values.append(key)
        if isinstance(value, str):
            values.append(value)
        elif isinstance(value, (int, float, bool)):
            values.append(str(value))
        elif value is not None:
            values.append(str(value))
    return " ".join(values).lower()


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
    result: _ExpandedResult,
    max_bytes: int,
) -> _ExpandedResult:
    end_line, content = _cap_content_bytes(
        result.content,
        result.start_line,
        max_bytes,
    )
    return _ExpandedResult(
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
    )


def _end_line_for_content(start_line: int, content: str) -> int:
    if not content:
        return start_line
    return start_line + max(0, len(content.splitlines()) - 1)


def _merge_overlapping_results(results: list[_ExpandedResult]) -> list[_ExpandedResult]:
    by_file: dict[Path, list[_ExpandedResult]] = {}
    for result in results:
        by_file.setdefault(result.file_path, []).append(result)

    merged: list[_ExpandedResult] = []
    for file_path, file_results in by_file.items():
        sorted_results = sorted(
            file_results,
            key=lambda item: (item.start_line, item.end_line, -item.score),
        )
        current: _ExpandedResult | None = None
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
        key=lambda item: (
            item.rank_tier,
            -item.score,
            item.file_path.as_posix(),
            item.start_line,
        ),
    )


def _merge_expanded_result(
    left: _ExpandedResult,
    right: _ExpandedResult,
) -> _ExpandedResult:
    left_lines = left.content.splitlines()
    right_lines = right.content.splitlines()
    overlap = max(0, left.end_line - right.start_line + 1)
    content_lines = [*left_lines, *right_lines[overlap:]]
    return _ExpandedResult(
        chunk_ids=_dedupe([*left.chunk_ids, *right.chunk_ids]),
        file_path=left.file_path,
        start_line=min(left.start_line, right.start_line),
        end_line=max(left.end_line, right.end_line),
        content="\n".join(content_lines),
        score=max(left.score, right.score),
        score_parts=_merge_score_parts(left.score_parts, right.score_parts),
        reasons=_dedupe([*left.reasons, *right.reasons]),
        followup_keywords=_dedupe([*left.followup_keywords, *right.followup_keywords]),
        rank_tier=min(left.rank_tier, right.rank_tier),
    )


def _normalized_score_parts(candidate: RetrievalCandidate) -> dict[str, float]:
    if candidate.source == "semantic":
        return {"semantic": candidate.score_parts.get("semantic", candidate.score)}
    if candidate.source == "lexical":
        return {
            "lexical": candidate.score_parts.get(
                "lexical",
                candidate.score_parts.get("fts", candidate.score),
            )
        }
    if candidate.source == "path_symbol":
        return {
            "path_symbol": candidate.score_parts.get("path_symbol", candidate.score)
        }
    return dict(candidate.score_parts)


def _merge_score_parts(
    left: dict[str, float],
    right: dict[str, float],
) -> dict[str, float]:
    merged = dict(left)
    for key, value in right.items():
        merged[key] = max(merged.get(key, value), value)
    return merged


def _combined_score(score_parts: dict[str, float]) -> float:
    return (
        (score_parts.get("semantic", 0.0) * 0.55)
        + (score_parts.get("lexical", 0.0) * 0.25)
        + (min(score_parts.get("path_symbol", 0.0), 5.0) / 5.0 * 0.15)
        + (score_parts.get("planner_lexical", 0.0) * 0.12)
        + (
            min(score_parts.get("planner_path_symbol", 0.0), 5.0)
            / 5.0
            * 0.07
        )
        + _bounded_score(score_parts.get("signal", 0.0))
        + (_bounded_score(score_parts.get("planner_signal", 0.0)) * 0.65)
        + _bounded_score(score_parts.get("relation", 0.0))
        + (score_parts.get("token_coverage", 0.0) * 0.20)
        + score_parts.get("plugin_boost", 0.0)
        + score_parts.get("penalty", 0.0)
    )


def _bounded_score(score: float) -> float:
    return min(max(score, 0.0), 1.0)


def _rank_tier(
    store: SQLiteStore,
    chunk: DocumentChunk,
    score_parts: dict[str, float],
) -> int:
    if score_parts.get("signal", 0.0) > 0 and _chunk_has_signal_kind(
        store,
        chunk.chunk_id,
        "endpoint",
    ):
        base_tier = 0
    elif score_parts.get("relation", 0.0) > 0:
        base_tier = 1
    elif score_parts.get("signal", 0.0) > 0:
        base_tier = 2
    else:
        base_tier = 3

    if _is_planner_hint_only(score_parts):
        return base_tier + 1
    return base_tier


def _has_planner_hint(score_parts: dict[str, float]) -> bool:
    return any(
        score_parts.get(key, 0.0) > 0
        for key in ("planner_lexical", "planner_path_symbol", "planner_signal")
    )


def _has_original_query_evidence(score_parts: dict[str, float]) -> bool:
    return any(
        score_parts.get(key, 0.0) > 0
        for key in ("semantic", "lexical", "path_symbol", "signal", "token_coverage")
    )


def _is_planner_hint_only(score_parts: dict[str, float]) -> bool:
    return _has_planner_hint(score_parts) and not _has_original_query_evidence(
        score_parts
    )


def _chunk_has_signal_kind(store: SQLiteStore, chunk_id: str, kind: str) -> bool:
    try:
        return any(signal.kind == kind for signal in store.signals_for_chunk(chunk_id))
    except sqlite3.Error:
        return False


def _token_coverage(tokens: list[str], chunk: DocumentChunk) -> float:
    if not tokens:
        return 0.0

    haystack = set(chunk.lexical_tokens)
    haystack.update(tokenize_query(chunk.content))
    matches = sum(1 for token in tokens if token.lower() in haystack)
    return matches / len(tokens)


def _plugin_boost(chunk: DocumentChunk) -> float:
    if chunk.metadata.get("language") == "java":
        return 0.03
    return 0.0


def _route_boost(chunk: DocumentChunk, query: str, tokens: list[str]) -> float:
    if "/" not in query or not tokens:
        return 0.0
    query_tokens = set(tokens)
    for token in chunk.lexical_tokens:
        if not token.startswith("/"):
            continue
        if query_tokens.intersection(tokenize_query(token)):
            return 0.12
    return 0.0


def _generated_or_test_penalty(chunk: DocumentChunk) -> float:
    path = chunk.file_path.as_posix().lower()
    penalty = 0.0
    if chunk.metadata.get("is_generated") or "generated" in path:
        penalty += 0.20
    if chunk.metadata.get("is_test") or "/test/" in path or path.endswith("test.java"):
        penalty += 0.10
    return penalty


def _reasons(score_parts: dict[str, float], query: str) -> list[str]:
    reasons: list[str] = []
    if score_parts.get("semantic", 0.0) > 0:
        reasons.append("semantic match")
    if score_parts.get("lexical", 0.0) > 0:
        reasons.append("lexical match")
    if score_parts.get("path_symbol", 0.0) > 0:
        reasons.append("path/symbol match")
    if score_parts.get("signal", 0.0) > 0:
        reasons.append("signal match")
    if score_parts.get("relation", 0.0) > 0:
        reasons.append("relation expansion")
    if _has_planner_hint(score_parts):
        reasons.append("planner hint match")
    if score_parts.get("token_coverage", 0.0) > 0:
        reasons.append("token coverage")
    if "/" in query and score_parts.get("route_boost", 0.0) > 0:
        reasons.append("route token match")
    elif score_parts.get("plugin_boost", 0.0) > 0:
        reasons.append("java plugin boost")
    if score_parts.get("penalty", 0.0) < 0:
        reasons.append("generated/test penalty")
    return reasons


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


def _dedupe(tokens: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for token in tokens:
        normalized = token.lower()
        if normalized and normalized not in seen:
            seen.add(normalized)
            deduped.append(normalized)
    return deduped
