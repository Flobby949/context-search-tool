from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from context_search_tool.models import RepoProfile
from context_search_tool.sqlite_store import SQLiteStore
from context_search_tool.tokenizer import tokenize_query


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
) -> RepoProfile:
    languages = [language for language, _ in store.language_counts()[: limits.max_languages]]
    files = [path.as_posix() for path in store.source_files_for_profile(limits.max_files)]
    profile = RepoProfile(
        languages=languages,
        source_roots=_source_roots(files),
        important_files=files,
        symbols=store.symbol_names_for_profile(limits.max_symbols),
        tokens=store.token_counts_for_profile(limits.max_tokens),
    )
    return _fit_budget(profile, limits.max_chars)


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


def _dedupe(tokens: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for token in tokens:
        if token not in seen:
            seen.add(token)
            result.append(token)
    return result
