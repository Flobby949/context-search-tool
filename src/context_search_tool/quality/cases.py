from __future__ import annotations

import fnmatch
import json
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from context_search_tool.config import ToolConfig


class Gate(str, Enum):
    REQUIRED = "required"
    KNOWN_GAP = "known_gap"
    INFORMATIONAL = "informational"


_WINDOWS_ABSOLUTE_RE = re.compile(r"^[A-Za-z]:[\\/]")
_GLOB_CHARS = set("*?[")


@dataclass(frozen=True)
class Matcher:
    path: str | None = None
    glob: str | None = None
    contains: str | None = None

    def __post_init__(self) -> None:
        selectors = [
            self.path is not None,
            self.glob is not None,
            self.contains is not None,
        ]
        if sum(selectors) != 1:
            raise ValueError("Matcher requires exactly one selector")
        if self.path is not None:
            _validate_repo_relative_path(_require_str(self.path, "path"), "path")
        if self.glob is not None:
            _validate_repo_relative_path(_require_str(self.glob, "glob"), "glob")
        if self.contains is not None:
            _require_non_empty_str(self.contains, "contains")

    @classmethod
    def from_raw(cls, raw: Any) -> Matcher:
        if isinstance(raw, str):
            if any(char in raw for char in _GLOB_CHARS):
                return cls(glob=raw)
            return cls(path=raw)
        if not isinstance(raw, dict):
            raise ValueError("matcher must be a string or object")

        allowed = {"path", "glob", "contains", "top_k", "max_rank", "role"}
        unknown = set(raw) - allowed
        if unknown:
            raise ValueError(f"unknown matcher field: {sorted(unknown)[0]}")
        return cls(
            path=raw.get("path"),
            glob=raw.get("glob"),
            contains=raw.get("contains"),
        )

    def matches(self, result_path: str) -> bool:
        normalized = normalize_result_path(result_path)
        if self.path is not None:
            return normalized == normalize_result_path(self.path)
        if self.glob is not None:
            return fnmatch.fnmatchcase(normalized, normalize_result_path(self.glob))
        assert self.contains is not None
        return self.contains in normalized


@dataclass(frozen=True)
class TopKMatcher:
    matcher: Matcher
    top_k: int


@dataclass(frozen=True)
class ExpectedAnyGroup:
    matchers: tuple[Matcher, ...]
    top_k: int


@dataclass(frozen=True)
class PreferredRank:
    matcher: Matcher
    top_k: int
    max_rank: int
    role: str = ""


@dataclass(frozen=True)
class Outranks:
    source: Matcher
    noise: Matcher
    top_k: int


@dataclass(frozen=True)
class QualityCase:
    case_id: str
    query: str
    tags: tuple[str, ...] = ()
    mode: str = "results"
    gate: Gate = Gate.REQUIRED
    expected_top_k: tuple[TopKMatcher, ...] = ()
    expected_any_top_k: tuple[ExpectedAnyGroup, ...] = ()
    preferred_rank: tuple[PreferredRank, ...] = ()
    absent_top_k: tuple[TopKMatcher, ...] = ()
    outranks: tuple[Outranks, ...] = ()
    forbidden_above: tuple[Outranks, ...] = ()
    anchor_expected: tuple[str, ...] = ()
    known_gap_reason: str = ""
    notes: str = ""
    expected_top5_min: int | None = None


@dataclass(frozen=True)
class QualityRepo:
    repo_key: str
    path_env: str = ""
    repo_dir_name: str = ""
    snapshot_path: str = ""
    profiles: tuple[str, ...] = ("ci",)
    queries: tuple[QualityCase, ...] = ()
    default_config: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class QualityFixture:
    schema_version: int
    repos: tuple[QualityRepo, ...]
    path: Path


def load_quality_fixture(path: Path) -> QualityFixture:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1:
        raise ValueError("quality fixture schema_version must be 1")

    raw_repos = data.get("repos")
    if not isinstance(raw_repos, (list, tuple)) or not raw_repos:
        raise ValueError("quality fixture requires at least one repo")

    return QualityFixture(
        schema_version=1,
        repos=tuple(_parse_repo(raw_repo) for raw_repo in raw_repos),
        path=path,
    )


def adapt_legacy_query_case(raw: dict[str, Any]) -> QualityCase:
    return _parse_case(raw)


def validate_profile_compatible(profile: str, config: ToolConfig) -> None:
    if profile != "ci":
        return
    if config.embedding.provider != "hash":
        raise ValueError("ci profile requires hash embeddings")
    if config.query_planner.enabled:
        raise ValueError("ci profile requires the query planner to be disabled")
    if config.embedding.api_key_env is not None:
        raise ValueError("ci profile does not allow embedding api_key_env")
    if config.embedding.base_url is not None:
        raise ValueError("ci profile does not allow embedding base_url")


def _parse_repo(raw: dict[str, Any]) -> QualityRepo:
    raw = _require_dict(raw, "repo")
    repo_key = _require_non_empty_str(raw.get("repo_key", ""), "repo_key")

    raw_queries = raw.get("queries")
    if not isinstance(raw_queries, (list, tuple)) or not raw_queries:
        raise ValueError("quality repo requires at least one query")
    default_config = raw.get("default_config", {})
    if not isinstance(default_config, dict):
        raise ValueError("default_config must be an object")

    return QualityRepo(
        repo_key=repo_key,
        path_env=_require_str(raw.get("path_env", ""), "path_env"),
        repo_dir_name=_require_str(raw.get("repo_dir_name", ""), "repo_dir_name"),
        snapshot_path=_require_str(raw.get("snapshot_path", ""), "snapshot_path"),
        profiles=_require_str_tuple(raw.get("profiles", ("ci",)), "profiles"),
        queries=tuple(_parse_case(raw_case) for raw_case in raw_queries),
        default_config=dict(default_config),
    )


def _parse_case(raw: dict[str, Any]) -> QualityCase:
    raw = _require_dict(raw, "query")
    case_id = _require_non_empty_str(raw.get("id", ""), "id")
    query = _require_non_empty_str(raw.get("query", ""), "query")
    gate = _require_str(raw.get("gate", Gate.REQUIRED.value), "gate")
    expected_top5_min = raw.get("expected_top5_min")

    expected_top_k = _parse_top_k_matchers(raw.get("expected_top_k", ()))
    if "expected_core" in raw:
        raw_expected_core = _require_sequence(raw["expected_core"], "expected_core")
        expected_top_k += tuple(
            TopKMatcher(Matcher.from_raw(item), 5) for item in raw_expected_core
        )

    absent_top_k = _parse_top_k_matchers(raw.get("absent_top_k", ()))
    if "forbidden_top3" in raw:
        raw_forbidden_top3 = _require_sequence(raw["forbidden_top3"], "forbidden_top3")
        absent_top_k += tuple(
            TopKMatcher(Matcher.from_raw(item), 3) for item in raw_forbidden_top3
        )

    return QualityCase(
        case_id=case_id,
        query=query,
        tags=_require_str_tuple(raw.get("tags", ()), "tags"),
        mode=_require_str(raw.get("mode", "results"), "mode"),
        gate=Gate(gate),
        expected_top_k=expected_top_k,
        expected_any_top_k=_parse_expected_any(raw.get("expected_any_top_k", ())),
        preferred_rank=_parse_preferred_rank(raw.get("preferred_rank", ())),
        absent_top_k=absent_top_k,
        outranks=_parse_outranks(raw.get("outranks", ())),
        forbidden_above=_parse_forbidden_above(
            raw.get("forbidden_above"), expected_top_k
        ),
        anchor_expected=_require_str_tuple(
            raw.get("anchor_expected", ()), "anchor_expected"
        ),
        known_gap_reason=_require_str(
            raw.get("known_gap_reason", raw.get("known_gap", "")),
            "known_gap_reason",
        ),
        notes=_require_str(raw.get("notes", ""), "notes"),
        expected_top5_min=None
        if expected_top5_min is None
        else _require_non_negative_int(expected_top5_min, "expected_top5_min"),
    )


def _parse_top_k_matchers(raw_items: Any) -> tuple[TopKMatcher, ...]:
    if not raw_items:
        return ()
    return tuple(
        _parse_top_k_matcher(raw_item)
        for raw_item in _require_sequence(raw_items, "top_k matchers")
    )


def _parse_top_k_matcher(raw: Any, default_top_k: int = 5) -> TopKMatcher:
    top_k = raw.get("top_k", default_top_k) if isinstance(raw, dict) else default_top_k
    return TopKMatcher(Matcher.from_raw(raw), _require_positive_int(top_k, "top_k"))


def _parse_expected_any(raw: Any) -> tuple[ExpectedAnyGroup, ...]:
    if not raw:
        return ()
    if isinstance(raw, dict):
        return (_parse_expected_any_group(raw),)
    raw_items = _require_sequence(raw, "expected_any_top_k")
    if all(isinstance(item, dict) and "matchers" in item for item in raw):
        return tuple(_parse_expected_any_group(item) for item in raw_items)

    top_k_items = tuple(_parse_top_k_matcher(item) for item in raw_items)
    return (
        ExpectedAnyGroup(
            matchers=tuple(item.matcher for item in top_k_items),
            top_k=max(item.top_k for item in top_k_items),
        ),
    )


def _parse_expected_any_group(raw: dict[str, Any]) -> ExpectedAnyGroup:
    raw = _require_dict(raw, "expected_any_top_k group")
    raw_matchers = raw.get("matchers", ())
    if not raw_matchers:
        raise ValueError("expected_any_top_k group requires at least one matcher")
    raw_matchers = _require_sequence(raw_matchers, "expected_any_top_k matchers")
    return ExpectedAnyGroup(
        matchers=tuple(Matcher.from_raw(item) for item in raw_matchers),
        top_k=_require_positive_int(raw.get("top_k", 5), "top_k"),
    )


def _parse_preferred_rank(raw_items: Any) -> tuple[PreferredRank, ...]:
    if not raw_items:
        return ()
    preferred = []
    for raw in _require_sequence(raw_items, "preferred_rank"):
        raw = _require_dict(raw, "preferred_rank entry")
        top_k = _require_positive_int(raw.get("top_k", 5), "top_k")
        preferred.append(
            PreferredRank(
                matcher=Matcher.from_raw(raw),
                top_k=top_k,
                max_rank=_require_positive_int(
                    raw.get("max_rank", top_k), "max_rank"
                ),
                role=_require_str(raw.get("role", ""), "role"),
            )
        )
    return tuple(preferred)


def _parse_outranks(raw_items: Any) -> tuple[Outranks, ...]:
    if not raw_items:
        return ()
    return tuple(
        _parse_outrank(raw_item)
        for raw_item in _require_sequence(raw_items, "outranks")
    )


def _parse_forbidden_above(
    raw: Any,
    expected_top_k: tuple[TopKMatcher, ...],
) -> tuple[Outranks, ...]:
    if not raw:
        return ()
    if isinstance(raw, (list, tuple)):
        outranks: list[Outranks] = []
        for item in raw:
            outranks.extend(_parse_forbidden_above(item, expected_top_k))
        return tuple(outranks)
    if isinstance(raw, dict) and {"source", "noise"}.issubset(raw):
        return (_parse_outrank(raw),)
    if isinstance(raw, dict):
        if not expected_top_k:
            raise ValueError("forbidden_above shorthand requires expected_top_k")
        source = expected_top_k[0]
        return (
            Outranks(
                source=source.matcher,
                noise=Matcher.from_raw(raw),
                top_k=_require_positive_int(raw.get("top_k", source.top_k), "top_k"),
            ),
        )
    if not isinstance(raw, str):
        raise ValueError("forbidden_above must be a matcher or outrank object")
    if not expected_top_k:
        raise ValueError("forbidden_above shorthand requires expected_top_k")
    source = expected_top_k[0]
    return (
        Outranks(
            source=source.matcher,
            noise=Matcher.from_raw(raw),
            top_k=source.top_k,
        ),
    )


def _parse_outrank(raw: dict[str, Any]) -> Outranks:
    raw = _require_dict(raw, "outrank")
    return Outranks(
        source=Matcher.from_raw(raw["source"]),
        noise=Matcher.from_raw(raw["noise"]),
        top_k=_require_positive_int(raw.get("top_k", 5), "top_k"),
    )


def _validate_repo_relative_path(value: str, field_name: str) -> None:
    if not value:
        raise ValueError(f"{field_name} matcher cannot be empty")
    normalized = value.replace("\\", "/")
    if value.startswith("\\\\") or normalized.startswith("/"):
        raise ValueError(f"{field_name} matcher must be repo-relative")
    if _WINDOWS_ABSOLUTE_RE.match(value):
        raise ValueError(f"{field_name} matcher must be repo-relative")

    if normalized.startswith("./"):
        normalized = normalized[2:]
    if ".." in normalized.split("/"):
        raise ValueError(f"{field_name} matcher cannot contain parent traversal")


def _require_str(value: Any, field_name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    return value


def _require_non_empty_str(value: Any, field_name: str) -> str:
    value = _require_str(value, field_name)
    if not value:
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


def _require_str_tuple(value: Any, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"{field_name} must be a list of strings")
    for item in value:
        if not isinstance(item, str):
            raise ValueError(f"{field_name} must be a list of strings")
    return tuple(value)


def _require_positive_int(value: Any, field_name: str) -> int:
    if type(value) is not int or value <= 0:
        raise ValueError(f"{field_name} must be a positive integer")
    return value


def _require_non_negative_int(value: Any, field_name: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")
    return value


def _require_dict(value: Any, field_name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} must be an object")
    return value


def _require_sequence(value: Any, field_name: str) -> list[Any] | tuple[Any, ...]:
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"{field_name} must be a list")
    return value


def normalize_result_path(path: str) -> str:
    normalized = path.replace("\\", "/")
    if normalized.startswith("./"):
        return normalized[2:]
    return normalized
