from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Iterable


@dataclass(frozen=True)
class FrontendRole:
    name: str


@dataclass(frozen=True)
class FrontendIntent:
    feature_entrypoint: float
    utility_implementation: float
    state: float


_LOCKFILES = {
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "pnpm-lock.yml",
    "bun.lockb",
}
_FEATURE_ENTRYPOINT_TOKENS = {
    "tool",
    "page",
    "view",
    "component",
    "layout",
    "sidebar",
    "theme",
    "reader",
    "scan",
    "scanner",
    "camera",
    "image",
    "upload",
    "download",
    "route",
    "navigation",
}
_UTILITY_IMPLEMENTATION_TOKENS = {
    "generate",
    "decode",
    "encode",
    "parse",
    "format",
    "convert",
    "entity",
    "class",
    "interface",
    "typescript",
    "java",
    "csharp",
    "python",
    "mask",
    "inpaint",
    "detection",
    "markdown",
}
_STATE_TOKENS = {
    "pinia",
    "store",
    "state",
    "theme",
    "sidebar",
    "dark",
    "light",
    "history",
}
_LOCKFILE_QUERY_TOKENS = {
    "bun",
    "dependencies",
    "dependency",
    "lock",
    "lockfile",
    "lockfiles",
    "npm",
    "package",
    "packages",
    "pnpm",
    "version",
    "versions",
    "yarn",
}
_TYPE_QUERY_TOKENS = {
    "declaration",
    "declarations",
    "type",
    "typedef",
    "types",
    "typing",
    "typings",
}
_SCRATCH_QUERY_TOKENS = {
    "cache",
    "generated",
    "mock",
    "scratch",
    "temp",
    "tmp",
}
_FRONTEND_SOURCE_SUFFIXES = {".astro", ".js", ".jsx", ".svelte", ".ts", ".tsx", ".vue"}
_TYPE_PATH_GENERIC_TOKENS = {"d", "index", "src", "ts", "type", "types"}
_SEPARATOR_RE = re.compile(r"[\\/._-]+")
_ACRONYM_BOUNDARY_RE = re.compile(r"(?<=[A-Z])(?=[A-Z][a-z])")
_CAMEL_BOUNDARY_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_TOKEN_RE = re.compile(r"[a-z0-9]+")


def classify_frontend_role(path: str | PurePosixPath) -> FrontendRole:
    normalized = _normalize_path(path)
    pure_path = PurePosixPath(normalized)
    parts = pure_path.parts
    frontend_parts = _frontend_path_parts(parts)
    frontend_path = "/".join(frontend_parts)
    name = pure_path.name

    if name in _LOCKFILES:
        return FrontendRole("lockfile")
    if parts and parts[0] in {"temp", "tmp", ".cache"}:
        return FrontendRole("scratch_temp")
    if not _has_frontend_source_suffix(normalized):
        return FrontendRole("other")
    if _is_type_decl(frontend_path, frontend_parts):
        return FrontendRole("type_decl")
    if _is_under(frontend_parts, "src", "router") or _is_under(frontend_parts, "src", "routes"):
        return FrontendRole("route_config")
    if (
        _is_under(frontend_parts, "src", "views")
        or _is_under(frontend_parts, "src", "pages")
        or _is_under(frontend_parts, "pages")
    ):
        return FrontendRole("view_page")
    if (
        frontend_path == "src/app.tsx"
        or frontend_path == "src/app.jsx"
        or frontend_path == "src/components/applayout.vue"
        or _is_under(frontend_parts, "src", "components", "layout")
        or _is_under(frontend_parts, "src", "layouts")
    ):
        return FrontendRole("layout_component")
    if _is_under(frontend_parts, "src", "components"):
        return FrontendRole("shared_component")
    if _is_under(frontend_parts, "src", "stores") or _is_under(frontend_parts, "src", "store"):
        return FrontendRole("store")
    if _is_under(frontend_parts, "src", "services") or _is_under(frontend_parts, "src", "api"):
        return FrontendRole("service")
    if (
        _is_under(frontend_parts, "src", "utils")
        or _is_under(frontend_parts, "src", "lib")
        or _is_under(frontend_parts, "src", "helpers")
    ):
        return FrontendRole("utility")

    return FrontendRole("other")


def infer_frontend_intent(query: str) -> FrontendIntent:
    tokens = _tokenize(query)
    return FrontendIntent(
        feature_entrypoint=_score_tokens(tokens, _FEATURE_ENTRYPOINT_TOKENS, 0.35),
        utility_implementation=_score_tokens(tokens, _UTILITY_IMPLEMENTATION_TOKENS, 0.18),
        state=_score_tokens(tokens, _STATE_TOKENS, 0.18),
    )


def frontend_repo_enabled(paths: Iterable[str | PurePosixPath]) -> bool:
    normalized_paths = tuple(_normalize_path(path) for path in paths)
    roles = {classify_frontend_role(path).name for path in normalized_paths}
    has_package_json = any(path == "package.json" or path.endswith("/package.json") for path in normalized_paths)
    has_view_or_page = "view_page" in roles
    has_component = bool(roles & {"layout_component", "shared_component"})
    return has_package_json and has_view_or_page and has_component


def frontend_candidate_scope_enabled(paths: Iterable[str | PurePosixPath]) -> bool:
    roles = {classify_frontend_role(path).name for path in paths}
    entry_roles = {"layout_component", "view_page"}
    support_roles = {
        "shared_component",
        "store",
        "service",
        "utility",
        "route_config",
        "type_decl",
    }
    return bool(roles & entry_roles) and bool(roles & support_roles)


def frontend_score_parts(path: str | PurePosixPath, query: str, *, enabled: bool) -> dict[str, float]:
    if not enabled:
        return {}

    role = classify_frontend_role(path).name
    intent = infer_frontend_intent(query)
    has_type_terms = _has_type_terms(query)
    has_explicit_type_evidence = has_type_terms or _has_type_path_match(path, query)
    parts: dict[str, float] = {}

    if role in {"view_page", "layout_component", "route_config"} and intent.feature_entrypoint >= 0.45:
        parts["frontend_entrypoint_boost"] = 0.35 * intent.feature_entrypoint
    elif role == "shared_component" and intent.feature_entrypoint >= 0.55:
        parts["frontend_entrypoint_boost"] = 0.18 * intent.feature_entrypoint

    if role in {"utility", "service"} and intent.utility_implementation >= 0.45:
        parts["frontend_support_boost"] = 0.18 * intent.utility_implementation
    elif role == "store" and intent.state >= 0.35:
        parts["frontend_support_boost"] = 0.18 * intent.state
    elif role == "type_decl" and has_type_terms:
        parts["frontend_support_boost"] = 0.12

    if role == "lockfile" and not _has_lockfile_terms(query):
        _add_penalty(parts, "frontend_lockfile_penalty", -0.80)
    if role == "scratch_temp" and not _has_scratch_terms(query):
        _add_penalty(parts, "frontend_scratch_temp_penalty", -0.60)
    if (
        role == "type_decl"
        and not has_explicit_type_evidence
        and intent.feature_entrypoint >= 0.45
        and intent.feature_entrypoint >= intent.utility_implementation
    ):
        _add_penalty(parts, "frontend_type_decl_penalty", -0.12)

    return parts


def _normalize_path(path: str | PurePosixPath) -> str:
    raw_path = path.as_posix() if isinstance(path, PurePosixPath) else str(path)
    normalized = raw_path.replace("\\", "/").lower()
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def _frontend_path_parts(parts: tuple[str, ...]) -> tuple[str, ...]:
    if not parts or parts[0] == "src":
        return parts
    for index, part in enumerate(parts):
        if part == "src":
            return parts[index:]
    return parts


def _is_type_decl(path: str, parts: tuple[str, ...]) -> bool:
    return _is_under(parts, "src", "types") or (path.startswith("src/") and path.endswith(".d.ts"))


def _has_frontend_source_suffix(path: str) -> bool:
    return any(path.endswith(suffix) for suffix in _FRONTEND_SOURCE_SUFFIXES)


def _is_under(parts: tuple[str, ...], *prefix: str) -> bool:
    return len(parts) >= len(prefix) and parts[: len(prefix)] == prefix


def _tokenize(query: str) -> tuple[str, ...]:
    tokens: list[str] = []
    for segment in _SEPARATOR_RE.sub(" ", query).split():
        split_segment = _ACRONYM_BOUNDARY_RE.sub(" ", segment)
        split_segment = _CAMEL_BOUNDARY_RE.sub(" ", split_segment)
        segment_tokens = tuple(_TOKEN_RE.findall(split_segment.lower()))
        if len(segment_tokens) > 1:
            tokens.append("".join(segment_tokens))
        tokens.extend(segment_tokens)
    return tuple(tokens)


def _score_tokens(tokens: tuple[str, ...], group: set[str], weight: float) -> float:
    return _clamp(sum(weight for token in tokens if token in group))


def _has_lockfile_terms(query: str) -> bool:
    return bool(set(_tokenize(query)) & _LOCKFILE_QUERY_TOKENS)


def _has_type_terms(query: str) -> bool:
    normalized = _normalize_path(query)
    return "d.ts" in normalized or bool(set(_tokenize(query)) & _TYPE_QUERY_TOKENS)


def _has_type_path_match(path: str | PurePosixPath, query: str) -> bool:
    query_tokens = set(_tokenize(query))
    path_tokens = _type_decl_path_tokens(path)
    return bool(query_tokens & path_tokens)


def _type_decl_path_tokens(path: str | PurePosixPath) -> set[str]:
    normalized = _normalize_path(path)
    pure_path = PurePosixPath(normalized)
    tokens: set[str] = set()
    for part in _frontend_path_parts(pure_path.parts):
        cleaned = part[:-5] if part.endswith(".d.ts") else PurePosixPath(part).stem
        part_tokens = set(_tokenize(cleaned))
        compact = re.sub(r"[^a-z0-9]+", "", cleaned)
        if compact:
            part_tokens.add(compact)
        tokens.update(part_tokens - _TYPE_PATH_GENERIC_TOKENS)
    return tokens


def _has_scratch_terms(query: str) -> bool:
    return bool(set(_tokenize(query)) & _SCRATCH_QUERY_TOKENS)


def _add_penalty(parts: dict[str, float], key: str, value: float) -> None:
    parts[key] = value
    parts["penalty"] = min(parts.get("penalty", value), value)


def _clamp(score: float) -> float:
    return max(0.0, min(1.0, score))
