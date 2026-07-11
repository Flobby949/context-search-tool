from __future__ import annotations

import fnmatch
import json
import re
from dataclasses import dataclass, field, fields, replace
from enum import Enum
from pathlib import Path
from typing import Any

from context_search_tool.config import DEFAULT_CONFIG, ToolConfig


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


def _matcher_identity(matcher: Matcher) -> tuple[str, str]:
    if matcher.path is not None:
        return ("path", normalize_result_path(matcher.path))
    if matcher.glob is not None:
        return ("glob", normalize_result_path(matcher.glob))
    assert matcher.contains is not None
    return ("contains", matcher.contains)


@dataclass(frozen=True)
class TopKMatcher:
    matcher: Matcher
    top_k: int


@dataclass(frozen=True)
class ExpectedAnyGroup:
    matchers: tuple[Matcher, ...]
    top_k: int


@dataclass(frozen=True)
class AtLeastTopKGroup:
    matchers: tuple[Matcher, ...]
    top_k: int
    min_matches: int


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
class LegacyProvenance:
    fixture: str
    key: str


@dataclass(frozen=True)
class QualityCase:
    case_id: str
    query: str
    profiles: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    mode: str = "results"
    gate: Gate = Gate.REQUIRED
    expected_top_k: tuple[TopKMatcher, ...] = ()
    expected_any_top_k: tuple[ExpectedAnyGroup, ...] = ()
    expected_at_least_top_k: tuple[AtLeastTopKGroup, ...] = ()
    preferred_rank: tuple[PreferredRank, ...] = ()
    absent_top_k: tuple[TopKMatcher, ...] = ()
    outranks: tuple[Outranks, ...] = ()
    forbidden_above: tuple[Outranks, ...] = ()
    anchor_expected: tuple[str, ...] = ()
    known_gap_reason: str = ""
    notes: str = ""
    legacy: LegacyProvenance | None = None


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
    profile_configs: dict[str, dict[str, Any]]
    repos: tuple[QualityRepo, ...]
    path: Path
    canonical: bool


def load_quality_fixture(path: Path) -> QualityFixture:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1:
        raise ValueError("quality fixture schema_version must be 1")

    raw_repos = data.get("repos")
    if not isinstance(raw_repos, (list, tuple)) or not raw_repos:
        raise ValueError("quality fixture requires at least one repo")

    canonical = "profile_configs" in data
    repos = tuple(_parse_repo(raw_repo) for raw_repo in raw_repos)
    profile_configs = (
        _parse_profile_configs(data["profile_configs"]) if canonical else {}
    )
    if not canonical:
        profile_configs = {
            profile: {} for repo in repos for profile in repo.profiles
        }
    _validate_fixture_profiles(profile_configs, repos, canonical)
    return QualityFixture(
        schema_version=1,
        profile_configs=profile_configs,
        repos=repos,
        path=path,
        canonical=canonical,
    )


def adapt_legacy_query_case(raw: dict[str, Any]) -> QualityCase:
    return _parse_case(raw)


def _parse_profile_configs(raw: Any) -> dict[str, dict[str, Any]]:
    raw = _require_dict(raw, "profile_configs")
    parsed: dict[str, dict[str, Any]] = {}
    for name, config in raw.items():
        name = _require_non_empty_str(name, "profile name")
        config = _require_dict(config, f"profile {name}")
        unknown = set(config) - {"index", "retrieval", "embedding", "query_planner"}
        if unknown:
            raise ValueError(f"unknown profile config section: {sorted(unknown)[0]}")
        parsed[name] = {
            section: _validate_config_section(f"profile {name}", section, values)
            for section, values in config.items()
        }
    return parsed


def _validate_config_section(
    owner: str,
    section: str,
    raw: Any,
) -> dict[str, Any]:
    values = dict(_require_dict(raw, f"{owner}.{section}"))
    template = getattr(DEFAULT_CONFIG, section)
    allowed = {item.name for item in fields(template)}
    unknown = set(values) - allowed
    if unknown:
        raise ValueError(
            f"unknown config option: {owner}.{section}.{sorted(unknown)[0]}"
        )
    for name, value in values.items():
        default = getattr(template, name)
        label = f"{owner}.{section}.{name}"
        valid = (
            isinstance(value, list)
            and all(isinstance(item, str) for item in value)
            if isinstance(default, list)
            else isinstance(value, str | None)
            if default is None
            else isinstance(value, int | float) and not isinstance(value, bool)
            if isinstance(default, float)
            else type(value) is type(default)
        )
        if not valid:
            raise ValueError(f"{label} has invalid type")
    return values


def _canonical_profile_config(overrides: dict[str, Any]) -> ToolConfig:
    result = DEFAULT_CONFIG
    for section in ("index", "retrieval", "embedding", "query_planner"):
        if section in overrides:
            result = replace(
                result,
                **{
                    section: replace(
                        getattr(DEFAULT_CONFIG, section),
                        **overrides[section],
                    )
                },
            )
    return result


def validate_profile_compatible(
    profile: str,
    config: ToolConfig,
    *,
    canonical: bool = False,
) -> None:
    if not canonical:
        if profile != "ci":
            return
        if config.embedding.provider != "hash":
            raise ValueError("ci profile requires hash embeddings")
        if config.query_planner.enabled:
            raise ValueError("ci profile requires the query planner disabled")
        if (
            config.embedding.api_key_env is not None
            or config.embedding.base_url is not None
        ):
            raise ValueError("ci profile does not allow remote embedding settings")
        return
    if profile in {"ci", "smoke", "ab_hash"}:
        if config.embedding.provider != "hash":
            raise ValueError(f"{profile} profile requires hash embeddings")
        if config.query_planner.enabled:
            raise ValueError(f"{profile} profile requires the query planner disabled")
        if profile == "ci" and (
            config.embedding.api_key_env is not None
            or config.embedding.base_url is not None
        ):
            raise ValueError("ci profile does not allow remote embedding settings")
        return
    if profile == "planner":
        if config.embedding.provider != "hash":
            raise ValueError("planner profile requires hash embeddings")
        if not config.query_planner.enabled:
            raise ValueError("planner profile requires the query planner enabled")
        if config.query_planner.provider != "ollama":
            raise ValueError("planner profile requires the Ollama planner")
        return
    if profile in {"calibration_bge", "ab_bge"}:
        if (
            config.embedding.provider != "bge"
            or config.embedding.model != "bge-m3"
            or config.embedding.dimensions != 1024
        ):
            raise ValueError(f"{profile} profile requires BGE M3 at 1024 dimensions")
        if config.query_planner.enabled:
            raise ValueError(f"{profile} profile requires the query planner disabled")


def _parse_repo(raw: dict[str, Any]) -> QualityRepo:
    raw = _require_dict(raw, "repo")
    repo_key = _require_non_empty_str(raw.get("repo_key", ""), "repo_key")

    raw_queries = raw.get("queries")
    if not isinstance(raw_queries, (list, tuple)) or not raw_queries:
        raise ValueError("quality repo requires at least one query")
    raw_default_config = _require_dict(raw.get("default_config", {}), "default_config")
    unknown_sections = set(raw_default_config) - {
        "index",
        "retrieval",
        "embedding",
        "query_planner",
    }
    if unknown_sections:
        raise ValueError(
            f"unknown default_config section: {sorted(unknown_sections)[0]}"
        )
    default_config = {
        section: _validate_config_section(
            f"repo {repo_key}.default_config",
            section,
            values,
        )
        for section, values in raw_default_config.items()
    }

    return QualityRepo(
        repo_key=repo_key,
        path_env=_require_str(raw.get("path_env", ""), "path_env"),
        repo_dir_name=_require_str(raw.get("repo_dir_name", ""), "repo_dir_name"),
        snapshot_path=_require_str(raw.get("snapshot_path", ""), "snapshot_path"),
        profiles=_require_str_tuple(raw.get("profiles", ("ci",)), "profiles"),
        queries=tuple(_parse_case(raw_case) for raw_case in raw_queries),
        default_config=dict(default_config),
    )


def _validate_fixture_profiles(
    profile_configs: dict[str, dict[str, Any]],
    repos: tuple[QualityRepo, ...],
    canonical: bool,
) -> None:
    if canonical:
        for profile, overrides in profile_configs.items():
            validate_profile_compatible(
                profile,
                _canonical_profile_config(overrides),
                canonical=True,
            )
    repo_keys: set[str] = set()
    for repo in repos:
        if repo.repo_key in repo_keys:
            raise ValueError(f"duplicate repo_key: {repo.repo_key}")
        repo_keys.add(repo.repo_key)
        if canonical and set(repo.default_config) - {"index", "retrieval"}:
            raise ValueError("canonical repo default_config only allows index and retrieval")
        for profile in repo.profiles:
            if profile not in profile_configs:
                raise ValueError(f"unknown profile: {profile}")
        case_ids: set[str] = set()
        for case in repo.queries:
            if case.case_id in case_ids:
                raise ValueError(f"duplicate case id: {repo.repo_key}/{case.case_id}")
            case_ids.add(case.case_id)
            for profile in case.profiles:
                if profile not in repo.profiles or profile not in profile_configs:
                    raise ValueError(f"unknown profile: {profile}")


def _parse_case(raw: dict[str, Any]) -> QualityCase:
    raw = _require_dict(raw, "query")
    case_id = _require_non_empty_str(raw.get("id", ""), "id")
    query = _require_non_empty_str(raw.get("query", ""), "query")
    gate = _require_str(raw.get("gate", Gate.REQUIRED.value), "gate")
    raw_legacy = raw.get("legacy")
    legacy = None
    if raw_legacy is not None:
        raw_legacy = _require_dict(raw_legacy, "legacy")
        legacy = LegacyProvenance(
            fixture=_require_non_empty_str(raw_legacy.get("fixture"), "legacy.fixture"),
            key=_require_non_empty_str(raw_legacy.get("key"), "legacy.key"),
        )

    profiles = _require_str_tuple(raw.get("profiles", ()), "profiles")
    expected_top_k = _parse_top_k_matchers(raw.get("expected_top_k", ()))
    if "required_top3" in raw:
        raw_required_top3 = _require_sequence(raw["required_top3"], "required_top3")
        expected_top_k += tuple(
            TopKMatcher(Matcher.from_raw(item), 3) for item in raw_required_top3
        )

    at_least_groups = _parse_at_least_groups(
        raw.get("expected_at_least_top_k", ())
    )
    if "expected_core" in raw:
        raw_expected_core = _require_sequence(raw["expected_core"], "expected_core")
        expected_core = tuple(Matcher.from_raw(item) for item in raw_expected_core)
        if not expected_core:
            raise ValueError("expected_core requires at least one matcher")
        if len({_matcher_identity(matcher) for matcher in expected_core}) != len(
            expected_core
        ):
            raise ValueError("expected_core has duplicate matcher")
        minimum = _require_non_negative_int(
            raw.get("expected_top5_min", len(expected_core)),
            "expected_top5_min",
        )
        if minimum > len(expected_core):
            raise ValueError("expected_top5_min cannot exceed expected_core count")
        at_least_groups += (
            AtLeastTopKGroup(
                matchers=expected_core,
                top_k=5,
                min_matches=minimum,
            ),
        )
    elif "expected_top5_min" in raw:
        raise ValueError("expected_top5_min requires expected_core")

    absent_top_k = _parse_top_k_matchers(raw.get("absent_top_k", ()))
    if "forbidden_top3" in raw:
        raw_forbidden_top3 = _require_sequence(raw["forbidden_top3"], "forbidden_top3")
        absent_top_k += tuple(
            TopKMatcher(Matcher.from_raw(item), 3) for item in raw_forbidden_top3
        )
    absent_windows, relational_forbidden_above = _partition_forbidden_above(
        raw.get("forbidden_above")
    )
    absent_top_k += absent_windows
    forbidden_above = _parse_forbidden_above(
        relational_forbidden_above,
        expected_top_k,
    )

    return QualityCase(
        case_id=case_id,
        query=query,
        profiles=profiles,
        tags=_require_str_tuple(raw.get("tags", ()), "tags"),
        mode=_require_str(raw.get("mode", "results"), "mode"),
        gate=Gate(gate),
        expected_top_k=expected_top_k,
        expected_any_top_k=_parse_expected_any(raw.get("expected_any_top_k", ())),
        expected_at_least_top_k=at_least_groups,
        preferred_rank=_parse_preferred_rank(raw.get("preferred_rank", ())),
        absent_top_k=absent_top_k,
        outranks=_parse_outranks(raw.get("outranks", ())),
        forbidden_above=forbidden_above,
        anchor_expected=_require_str_tuple(
            raw.get("anchor_expected", ()), "anchor_expected"
        ),
        known_gap_reason=_require_str(
            raw.get("known_gap_reason", raw.get("known_gap", "")),
            "known_gap_reason",
        ),
        notes=_require_str(raw.get("notes", ""), "notes"),
        legacy=legacy,
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


def _parse_at_least_groups(raw: Any) -> tuple[AtLeastTopKGroup, ...]:
    raw = _require_sequence(raw, "expected_at_least_top_k")
    if not raw:
        return ()
    groups: list[AtLeastTopKGroup] = []
    for item in raw:
        item = _require_dict(item, "expected_at_least_top_k group")
        matchers = tuple(
            Matcher.from_raw(value)
            for value in _require_sequence(item.get("matchers"), "matchers")
        )
        if not matchers:
            raise ValueError("expected_at_least_top_k requires matchers")
        if len({_matcher_identity(matcher) for matcher in matchers}) != len(matchers):
            raise ValueError("expected_at_least_top_k has duplicate matcher")
        minimum = _require_non_negative_int(item.get("min_matches"), "min_matches")
        if minimum > len(matchers):
            raise ValueError("min_matches cannot exceed matcher count")
        groups.append(
            AtLeastTopKGroup(
                matchers=matchers,
                top_k=_require_positive_int(item.get("top_k"), "top_k"),
                min_matches=minimum,
            )
        )
    return tuple(groups)


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


def _partition_forbidden_above(
    raw: Any,
) -> tuple[tuple[TopKMatcher, ...], tuple[Any, ...]]:
    if not raw:
        return (), ()
    raw_items = raw if isinstance(raw, (list, tuple)) else (raw,)
    absent_windows: list[TopKMatcher] = []
    relational: list[Any] = []
    for item in raw_items:
        if (
            isinstance(item, dict)
            and "max_rank" in item
            and not {"source", "noise"}.issubset(item)
        ):
            top_k = _require_positive_int(item.get("top_k", 5), "top_k")
            max_rank = _require_positive_int(item.get("max_rank"), "max_rank")
            if max_rank > top_k:
                raise ValueError("forbidden_above max_rank cannot exceed top_k")
            absent_windows.append(TopKMatcher(Matcher.from_raw(item), max_rank))
        else:
            relational.append(item)
    return tuple(absent_windows), tuple(relational)


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
