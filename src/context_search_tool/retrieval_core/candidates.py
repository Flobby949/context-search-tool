from __future__ import annotations

import re
from pathlib import Path

from context_search_tool import sqlite_store, tokenizer
from context_search_tool.config import ToolConfig
from context_search_tool.embeddings import provider_from_config
from context_search_tool.models import (
    QueryVariant,
    RetrievalCandidate,
    SemanticMatch,
)
from context_search_tool.retrieval_core import evidence_merge, ordering
from context_search_tool.vector_store import NumpyVectorStore


_CJK_SEQUENCE_RE = re.compile(r"[㐀-鿿]{2,}")
_DIRECT_FRAGMENT_RE = re.compile(r"[A-Za-z0-9_./:@-]{3,}")
_DIRECT_TEXT_TOP_K_MULTIPLIER = 3


def semantic_candidates(
    index_dir: Path,
    variants: list[QueryVariant],
    config: ToolConfig,
    deleted_ids: set[str],
) -> tuple[list[RetrievalCandidate], list[QueryVariant], str]:
    provider = provider_from_config(config.embedding)
    vector_store = NumpyVectorStore(index_dir)
    try:
        vectors = provider.embed_texts([variant.text for variant in variants])
        if len(vectors) != len(variants):
            raise ValueError(
                "embedding response count does not match query variant count"
            )
        executed_variants = variants
        status = "hybrid" if len(variants) > 1 else "original_only"
    except Exception:
        if len(variants) == 1:
            raise
        executed_variants = variants[:1]
        vectors = provider.embed_texts(
            [variant.text for variant in executed_variants]
        )
        if len(vectors) != 1:
            raise ValueError("embedding response count does not match original query")
        status = "embedding_fallback"

    candidates: list[RetrievalCandidate] = []
    for variant, vector in zip(executed_variants, vectors):
        source = "semantic" if variant.source == "original" else "planner_semantic"
        for item in vector_store.search(
            vector,
            config.retrieval.semantic_top_k,
            deleted_ids,
        ):
            candidates.append(
                RetrievalCandidate(
                    chunk_id=item.chunk_id,
                    score=item.score,
                    source=source,
                    score_parts={source: item.score},
                    semantic_matches=[SemanticMatch(variant.variant_id, item.score)],
                )
            )
    return candidates, executed_variants, status


def lexical_candidates(
    store: sqlite_store.SQLiteStore,
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


def path_symbol_candidates(
    store: sqlite_store.SQLiteStore,
    tokens: list[str],
    limit: int,
) -> list[RetrievalCandidate]:
    return store.path_symbol_search(tokens, limit)


def direct_text_probes(query: str, original_tokens: list[str]) -> list[str]:
    probes: list[str] = []
    stripped = query.strip()
    if stripped:
        probes.append(stripped)

    for part in re.split(r"\s+", stripped):
        if part and part != stripped:
            probes.append(part)

    for match in _CJK_SEQUENCE_RE.finditer(query):
        segment = match.group(0)
        probes.append(segment)
        chars = list(segment)
        for size in (2, 3):
            if len(chars) < size:
                continue
            for index in range(0, len(chars) - size + 1):
                probes.append("".join(chars[index : index + size]))

    for match in _DIRECT_FRAGMENT_RE.finditer(query):
        probes.append(match.group(0))

    for token in original_tokens:
        if len(token) >= 3 or _CJK_SEQUENCE_RE.search(token):
            probes.append(token)

    return ordering.dedupe_lowered(probes)


def direct_text_candidates(
    store: sqlite_store.SQLiteStore,
    probes: list[str],
    config: ToolConfig,
) -> list[RetrievalCandidate]:
    limit = max(
        config.retrieval.lexical_top_k,
        config.retrieval.final_top_k * _DIRECT_TEXT_TOP_K_MULTIPLIER,
    )
    return store.direct_text_search(probes, limit)


def signal_candidates(
    store: sqlite_store.SQLiteStore,
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
        path_tokens = set(tokenizer.tokenize_query(path_value))
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


def planner_hint_candidates(
    store: sqlite_store.SQLiteStore,
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
        for item in lexical_candidates(
            store,
            hint_tokens,
            config.retrieval.lexical_top_k,
        )
    ]
    signals = signal_candidates(store, hint_tokens, config, planner_hint=True)
    return [*lexical, *path_symbol, *signals]


def merge_candidates(
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
                semantic_matches=candidate.semantic_matches,
            )
            continue

        merged[candidate.chunk_id] = RetrievalCandidate(
            chunk_id=candidate.chunk_id,
            score=max(existing.score, candidate.score),
            source=f"{existing.source},{candidate.source}",
            score_parts=evidence_merge.merge_score_parts(existing.score_parts, score_parts),
            semantic_matches=evidence_merge.merge_semantic_matches(
                existing.semantic_matches,
                candidate.semantic_matches,
            ),
        )
    return merged


def _normalized_score_parts(candidate: RetrievalCandidate) -> dict[str, float]:
    if candidate.source == "semantic":
        return {"semantic": candidate.score_parts.get("semantic", candidate.score)}
    if candidate.source == "planner_semantic":
        return {
            "planner_semantic": candidate.score_parts.get(
                "planner_semantic",
                candidate.score,
            )
        }
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
