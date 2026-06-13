from __future__ import annotations

import sqlite3
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from context_search_tool.chunker import expand_lines
from context_search_tool.config import ToolConfig
from context_search_tool.embeddings import provider_from_config
from context_search_tool.models import DocumentChunk, RetrievalCandidate, RetrievalResult
from context_search_tool.paths import index_dir_for
from context_search_tool.sqlite_store import SQLiteStore
from context_search_tool.tokenizer import tokenize_query
from context_search_tool.vector_store import NumpyVectorStore


@dataclass(frozen=True)
class QueryBundle:
    query: str
    expanded_tokens: list[str]
    results: list[RetrievalResult]
    followup_keywords: list[str]


@dataclass(frozen=True)
class _RankedChunk:
    chunk: DocumentChunk
    score: float
    score_parts: dict[str, float]
    reasons: list[str]


@dataclass(frozen=True)
class _ExpandedResult:
    file_path: Path
    start_line: int
    end_line: int
    content: str
    score: float
    score_parts: dict[str, float]
    reasons: list[str]
    followup_keywords: list[str]


def query_repository(
    repo: Path,
    query: str,
    config: ToolConfig,
    context_lines: int | None = None,
    full_file: bool = False,
) -> QueryBundle:
    repo = repo.resolve()
    tokens = _dedupe(tokenize_query(query))
    index_dir = index_dir_for(repo)
    db_path = index_dir / "index.sqlite"
    if not db_path.exists():
        return QueryBundle(
            query=query,
            expanded_tokens=tokens,
            results=[],
            followup_keywords=[],
        )

    store = SQLiteStore(db_path)
    try:
        deleted_ids = store.deleted_chunk_ids()
    except sqlite3.Error:
        return QueryBundle(
            query=query,
            expanded_tokens=tokens,
            results=[],
            followup_keywords=[],
        )

    candidates = _merge_candidates(
        [
            *_semantic_candidates(index_dir, query, config, deleted_ids),
            *store.lexical_search(tokens, config.retrieval.lexical_top_k),
            *store.path_symbol_search(tokens, config.retrieval.lexical_top_k),
        ]
    )
    if not candidates:
        return QueryBundle(
            query=query,
            expanded_tokens=tokens,
            results=[],
            followup_keywords=[],
        )

    ranked_chunks = _rank_chunks(store, candidates, tokens, query)
    expanded = _expand_ranked_chunks(repo, ranked_chunks, config, context_lines, full_file)
    results = [
        RetrievalResult(
            file_path=item.file_path,
            start_line=item.start_line,
            end_line=item.end_line,
            content=item.content,
            score=item.score,
            score_parts=item.score_parts,
            reasons=item.reasons,
            followup_keywords=item.followup_keywords,
        )
        for item in expanded[: config.retrieval.final_top_k]
    ]
    return QueryBundle(
        query=query,
        expanded_tokens=tokens,
        results=results,
        followup_keywords=_followup_keywords(results),
    )


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

        plugin_boost = _plugin_boost(chunk, query, coverage)
        if plugin_boost:
            score_parts["plugin_boost"] = plugin_boost

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
            )
        )

    return sorted(
        ranked,
        key=lambda item: (
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

        expanded.append(
            _ExpandedResult(
                file_path=ranked.chunk.file_path,
                start_line=start_line,
                end_line=end_line,
                content=content,
                score=ranked.score,
                score_parts=ranked.score_parts,
                reasons=ranked.reasons,
                followup_keywords=ranked.chunk.lexical_tokens,
            )
        )

    return _merge_overlapping_results(expanded)


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
        key=lambda item: (-item.score, item.file_path.as_posix(), item.start_line),
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
        file_path=left.file_path,
        start_line=min(left.start_line, right.start_line),
        end_line=max(left.end_line, right.end_line),
        content="\n".join(content_lines),
        score=max(left.score, right.score),
        score_parts=_merge_score_parts(left.score_parts, right.score_parts),
        reasons=_dedupe([*left.reasons, *right.reasons]),
        followup_keywords=_dedupe([*left.followup_keywords, *right.followup_keywords]),
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
        + (score_parts.get("token_coverage", 0.0) * 0.20)
        + score_parts.get("plugin_boost", 0.0)
        + score_parts.get("penalty", 0.0)
    )


def _token_coverage(tokens: list[str], chunk: DocumentChunk) -> float:
    if not tokens:
        return 0.0

    haystack = set(chunk.lexical_tokens)
    haystack.update(tokenize_query(chunk.content))
    matches = sum(1 for token in tokens if token.lower() in haystack)
    return matches / len(tokens)


def _plugin_boost(chunk: DocumentChunk, query: str, coverage: float) -> float:
    boost = 0.0
    if chunk.metadata.get("language") == "java":
        boost += 0.03
    if "/" in query and coverage > 0:
        boost += 0.12
    return boost


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
    if score_parts.get("token_coverage", 0.0) > 0:
        reasons.append("token coverage")
    if "/" in query and score_parts.get("plugin_boost", 0.0) >= 0.12:
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
