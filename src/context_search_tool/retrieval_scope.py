from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, TypeVar

import pathspec

if TYPE_CHECKING:
    from context_search_tool.config import ToolConfig
    from context_search_tool.models import RetrievalCandidate
    from context_search_tool.sqlite_store import SQLiteStore


_Candidate = TypeVar("_Candidate", bound="RetrievalCandidate")


_LANGUAGE_RE = re.compile(r"[a-z][a-z0-9_+.-]*\Z")
_WINDOWS_ABSOLUTE_RE = re.compile(r"[A-Za-z]:[/\\]")
_NON_CODE_LANGUAGES = frozenset(
    {
        "config",
        "env",
        "ini",
        "json",
        "lockfile",
        "markdown",
        "mdx",
        "properties",
        "restructuredtext",
        "toml",
        "xcodeproj",
        "xml",
        "yaml",
    }
)


@dataclass(frozen=True)
class RetrievalScope:
    """Hard query-time filters over indexed repository-relative files."""

    include_paths: tuple[str, ...] = ()
    exclude_paths: tuple[str, ...] = ()
    languages: tuple[str, ...] = ()
    code_only: bool = False
    _include_spec: pathspec.PathSpec = field(init=False, repr=False, compare=False)
    _exclude_spec: pathspec.PathSpec = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        includes = _normalize_patterns("include_paths", self.include_paths)
        excludes = _normalize_patterns("exclude_paths", self.exclude_paths)
        languages = _normalize_languages(self.languages)
        object.__setattr__(self, "include_paths", includes)
        object.__setattr__(self, "exclude_paths", excludes)
        object.__setattr__(self, "languages", languages)
        object.__setattr__(
            self,
            "_include_spec",
            pathspec.GitIgnoreSpec.from_lines(includes),
        )
        object.__setattr__(
            self,
            "_exclude_spec",
            pathspec.GitIgnoreSpec.from_lines(excludes),
        )

    @property
    def is_active(self) -> bool:
        return bool(
            self.include_paths
            or self.exclude_paths
            or self.languages
            or self.code_only
        )

    def matches(self, file_path: Path, language: str) -> bool:
        normalized_path = file_path.as_posix()
        if normalized_path.startswith("./"):
            normalized_path = normalized_path[2:]
        normalized_language = language.strip().lower()
        if self.include_paths and not self._include_spec.match_file(normalized_path):
            return False
        if self.exclude_paths and self._exclude_spec.match_file(normalized_path):
            return False
        if self.languages and normalized_language not in self.languages:
            return False
        return not self.code_only or normalized_language not in _NON_CODE_LANGUAGES


@dataclass(frozen=True)
class RetrievalScopeSnapshot:
    scope: RetrievalScope
    allowed_chunk_ids: frozenset[str] | None = None
    excluded_chunk_ids: frozenset[str] = frozenset()
    allowed_rows: tuple[tuple[str, Path, str], ...] = ()

    @property
    def is_active(self) -> bool:
        return self.allowed_chunk_ids is not None

    def filter_candidates(self, values: list[_Candidate]) -> list[_Candidate]:
        if self.allowed_chunk_ids is None:
            return values
        return [
            value for value in values if value.chunk_id in self.allowed_chunk_ids
        ]

    def contains_chunk_ids(self, chunk_ids: list[str]) -> bool:
        return self.allowed_chunk_ids is None or any(
            chunk_id in self.allowed_chunk_ids for chunk_id in chunk_ids
        )


def snapshot_retrieval_scope(
    store: SQLiteStore,
    scope: RetrievalScope | None,
) -> RetrievalScopeSnapshot:
    resolved = scope or RetrievalScope()
    if not resolved.is_active:
        return RetrievalScopeSnapshot(scope=resolved)

    rows = store.active_chunk_scope()
    allowed = frozenset(
        chunk_id
        for chunk_id, file_path, language in rows
        if resolved.matches(file_path, language)
    )
    all_chunk_ids = frozenset(chunk_id for chunk_id, _, _ in rows)
    return RetrievalScopeSnapshot(
        scope=resolved,
        allowed_chunk_ids=allowed,
        excluded_chunk_ids=all_chunk_ids - allowed,
        allowed_rows=tuple(row for row in rows if row[0] in allowed),
    )


def locally_supported_planner_hint(
    store: SQLiteStore,
    snapshot: RetrievalScopeSnapshot,
    bucket: str,
    value: str,
    config: ToolConfig,
) -> bool:
    from context_search_tool import tokenizer
    from context_search_tool.retrieval_core import ordering

    tokens = ordering.dedupe_lowered(tokenizer.tokenize_query(value))
    if not tokens:
        return False
    limit = max(1, config.retrieval.lexical_top_k)
    scope_kwargs = (
        {}
        if snapshot.allowed_chunk_ids is None
        else {"allowed_chunk_ids": snapshot.allowed_chunk_ids}
    )
    if bucket == "rewritten_queries":
        local_candidates = [
            *store.direct_text_search([value], limit, **scope_kwargs),
            *store.lexical_search(tokens, limit, **scope_kwargs),
        ]
        return bool(snapshot.filter_candidates(local_candidates))

    direct_matches = snapshot.filter_candidates(
        store.direct_text_search([value], limit, **scope_kwargs)
    )
    if direct_matches:
        return True
    path_symbol_matches = snapshot.filter_candidates(
        store.path_symbol_search(tokens, limit, **scope_kwargs)
    )
    return any(candidate.score >= len(tokens) for candidate in path_symbol_matches)


def _normalize_patterns(field_name: str, values: tuple[str, ...]) -> tuple[str, ...]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, str) or not value:
            raise ValueError(f"{field_name} entries must be non-empty strings")
        if (
            value.startswith(("/", "!", "#", "./"))
            or _WINDOWS_ABSOLUTE_RE.match(value)
            or "\\" in value
            or ".." in value.split("/")
            or any(ord(character) < 32 for character in value)
        ):
            raise ValueError(
                f"{field_name} entries must be safe repository-relative POSIX patterns"
            )
        if value not in seen:
            normalized.append(value)
            seen.add(value)
    return tuple(normalized)


def _normalize_languages(values: tuple[str, ...]) -> tuple[str, ...]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, str):
            raise ValueError("languages entries must be non-empty language names")
        language = value.strip().lower()
        if not _LANGUAGE_RE.fullmatch(language):
            raise ValueError("languages entries must be non-empty language names")
        if language not in seen:
            normalized.append(language)
            seen.add(language)
    return tuple(normalized)
