from __future__ import annotations

from collections import Counter
import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from context_search_tool.models import RepoProfile
from context_search_tool.sqlite_store import SQLiteStore
from context_search_tool.tokenizer import tokenize_query

_PROFILE_STOP_TOKENS = {
    "0",
    "1",
    "2",
    "3",
    "a",
    "an",
    "and",
    "are",
    "as",
    "be",
    "by",
    "class",
    "com",
    "def",
    "false",
    "for",
    "from",
    "if",
    "in",
    "is",
    "it",
    "no",
    "none",
    "not",
    "of",
    "on",
    "or",
    "py",
    "return",
    "self",
    "s",
    "t",
    "tests",
    "that",
    "the",
    "this",
    "to",
    "true",
    "we",
    "will",
    "with",
}

_MAX_QUERY_PROFILE_CHUNKS = 24


@dataclass(frozen=True)
class RepoProfileLimits:
    max_languages: int = 5
    max_files: int = 16
    max_symbols: int = 48
    max_tokens: int = 64
    max_chars: int = 2500


def build_repo_profile(
    store: SQLiteStore,
    limits: RepoProfileLimits = RepoProfileLimits(),
    *,
    query: str | None = None,
    scope_rows: tuple[tuple[str, Path, str], ...] | None = None,
) -> RepoProfile:
    if scope_rows is not None:
        return _build_scoped_repo_profile(store, limits, query, scope_rows)
    languages = [
        language for language, _ in store.language_counts()[: limits.max_languages]
    ]
    related_files, related_symbols, related_tokens, _ = _query_related_profile_values(
        store,
        query,
    )
    files = _merge_profile_values(
        related_files,
        [path.as_posix() for path in store.source_files_for_profile(limits.max_files)],
        limits.max_files,
    )
    symbols = _merge_profile_values(
        related_symbols,
        store.symbol_names_for_profile(limits.max_symbols),
        limits.max_symbols,
    )
    global_tokens = [
        token
        for token in store.token_counts_for_profile(
            max(limits.max_tokens * 4, limits.max_tokens)
        )
        if _useful_profile_token(token)
    ]
    tokens = _merge_profile_values(
        [token for token in related_tokens if _useful_profile_token(token)],
        global_tokens,
        limits.max_tokens,
    )
    profile = RepoProfile(
        languages=languages,
        source_roots=_source_roots(files),
        important_files=files,
        symbols=symbols,
        tokens=tokens,
    )
    return _fit_budget(profile, limits.max_chars)


def _query_related_profile_values(
    store: SQLiteStore,
    query: str | None,
    *,
    allowed_chunk_ids: frozenset[str] | None = None,
) -> tuple[list[str], list[str], list[str], list[str]]:
    query_tokens = [
        token
        for token in _dedupe(tokenize_query(query or ""))
        if _useful_profile_token(token)
    ]
    if not query_tokens:
        return [], [], [], []

    candidates = [
        *store.path_symbol_search(query_tokens, _MAX_QUERY_PROFILE_CHUNKS),
        *store.lexical_search(query_tokens, _MAX_QUERY_PROFILE_CHUNKS),
    ]
    if allowed_chunk_ids is not None:
        candidates = [
            candidate
            for candidate in candidates
            if candidate.chunk_id in allowed_chunk_ids
        ]
    chunk_ids = _dedupe([candidate.chunk_id for candidate in candidates])[
        :_MAX_QUERY_PROFILE_CHUNKS
    ]
    chunks = store.chunks_for_ids(chunk_ids)
    ordered_chunks = [chunks[chunk_id] for chunk_id in chunk_ids if chunk_id in chunks]
    files = _dedupe([chunk.file_path.as_posix() for chunk in ordered_chunks])
    symbols = _dedupe(
        [symbol.name for chunk in ordered_chunks for symbol in chunk.symbols]
    )
    local_tokens = _dedupe(
        [token for chunk in ordered_chunks for token in chunk.lexical_tokens]
    )
    query_vocabulary = {token.casefold() for token in query_tokens}
    tokens = [
        *[token for token in local_tokens if token.casefold() in query_vocabulary],
        *[token for token in local_tokens if token.casefold() not in query_vocabulary],
    ]
    return files, symbols, tokens, chunk_ids


def _build_scoped_repo_profile(
    store: SQLiteStore,
    limits: RepoProfileLimits,
    query: str | None,
    scope_rows: tuple[tuple[str, Path, str], ...],
) -> RepoProfile:
    allowed_chunk_ids = frozenset(row[0] for row in scope_rows)
    related_files, _, _, related_chunk_ids = _query_related_profile_values(
        store,
        query,
        allowed_chunk_ids=allowed_chunk_ids,
    )
    chunk_counts = Counter(path.as_posix() for _, path, _ in scope_rows)
    fallback_files = sorted(chunk_counts, key=lambda path: (-chunk_counts[path], path))
    files = _merge_profile_values(
        related_files,
        fallback_files,
        limits.max_files,
    )

    language_by_path = {
        path.as_posix(): language for _, path, language in scope_rows
    }
    language_counts = Counter(language_by_path.values())
    languages = sorted(
        language_counts,
        key=lambda language: (-language_counts[language], language),
    )[: limits.max_languages]

    sampled_ids = _dedupe(
        [*related_chunk_ids, *(chunk_id for chunk_id, _, _ in scope_rows)]
    )[:_MAX_QUERY_PROFILE_CHUNKS]
    sampled = store.chunks_for_ids(sampled_ids)
    chunks = [sampled[chunk_id] for chunk_id in sampled_ids if chunk_id in sampled]
    symbols = _dedupe(
        [symbol.name for chunk in chunks for symbol in chunk.symbols]
    )[: limits.max_symbols]
    tokens = [
        token
        for token in _dedupe(
            [token for chunk in chunks for token in chunk.lexical_tokens]
        )
        if _useful_profile_token(token)
    ][: limits.max_tokens]
    profile = RepoProfile(
        languages=languages,
        source_roots=_source_roots(files),
        important_files=files,
        symbols=symbols,
        tokens=tokens,
    )
    return _fit_budget(profile, limits.max_chars)


def _merge_profile_values(
    preferred: list[str],
    fallback: list[str],
    limit: int,
) -> list[str]:
    if limit <= 0:
        return []
    return _dedupe([*preferred, *fallback])[:limit]


def profile_vocabulary(profile: RepoProfile) -> set[str]:
    values = [
        *profile.languages,
        *profile.source_roots,
        *profile.important_files,
        *profile.symbols,
        *profile.tokens,
    ]
    tokens: list[str] = []
    for value in values:
        tokens.extend(tokenize_query(value))
    return {token.lower() for token in tokens if len(token) >= 2}


def rewritten_query_is_repo_supported(
    term: str,
    vocabulary: set[str],
    original_tokens: list[str],
) -> str:
    tokens = [token.lower() for token in tokenize_query(term) if len(token) >= 2]
    if not tokens:
        return ""
    allowed = vocabulary | {token.lower() for token in original_tokens}
    cleaned = _dedupe([token for token in tokens if token in allowed])
    return " ".join(cleaned) if len(cleaned) >= 2 else ""


def term_is_repo_supported(
    term: str,
    vocabulary: set[str],
) -> bool:
    tokens = {token.lower() for token in tokenize_query(term) if len(token) >= 2}
    if not tokens:
        return False
    return tokens <= vocabulary


def repo_profile_payload(profile: RepoProfile) -> dict[str, object]:
    return {
        "languages": profile.languages,
        "source_roots": profile.source_roots,
        "important_files": profile.important_files,
        "symbols": profile.symbols,
        "tokens": profile.tokens,
        "profile_hash": profile.profile_hash,
        "truncated": profile.truncated,
    }


def _source_roots(files: list[str]) -> list[str]:
    roots: list[str] = []
    for raw_path in files:
        parts = Path(raw_path).parts
        if len(parts) >= 2 and parts[0] in {"src", "lib", "app", "packages"}:
            candidate = "/".join(parts[:2])
        elif parts:
            candidate = parts[0]
        else:
            continue
        if candidate not in roots:
            roots.append(candidate)
    return roots[:8]


def _fit_budget(profile: RepoProfile, max_chars: int) -> RepoProfile:
    current = profile
    truncated = False
    while _payload_len(current, truncated=truncated) > max_chars:
        truncated = True
        if current.tokens:
            current = RepoProfile(**{**asdict(current), "tokens": current.tokens[:-1]})
            continue
        if current.symbols:
            current = RepoProfile(**{**asdict(current), "symbols": current.symbols[:-1]})
            continue
        if current.important_files:
            current = RepoProfile(
                **{**asdict(current), "important_files": current.important_files[:-1]}
            )
            continue
        if current.source_roots:
            current = RepoProfile(
                **{**asdict(current), "source_roots": current.source_roots[:-1]}
            )
            continue
        if len(current.languages) > 1:
            current = RepoProfile(
                **{**asdict(current), "languages": current.languages[:-1]}
            )
            continue
        break
    payload = {
        **repo_profile_payload(current),
        "profile_hash": "",
        "truncated": truncated,
    }
    digest = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return RepoProfile(
        **{
            **asdict(current),
            "profile_hash": f"sha256:{digest}",
            "truncated": truncated,
        }
    )


def _payload_len(profile: RepoProfile, truncated: bool) -> int:
    payload = {
        **repo_profile_payload(profile),
        "profile_hash": "sha256:" + ("0" * 64),
        "truncated": truncated,
    }
    return len(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def _useful_profile_token(token: str) -> bool:
    normalized = token.lower()
    return (
        len(normalized) >= 2
        and not normalized.isdigit()
        and normalized not in _PROFILE_STOP_TOKENS
    )


def _dedupe(tokens: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for token in tokens:
        if token not in seen:
            seen.add(token)
            result.append(token)
    return result
