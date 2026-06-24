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
_SEPARATOR_RE = re.compile(r"[\\/._-]+")
_ACRONYM_BOUNDARY_RE = re.compile(r"(?<=[A-Z])(?=[A-Z][a-z])")
_CAMEL_BOUNDARY_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_TOKEN_RE = re.compile(r"[a-z0-9]+")


def classify_frontend_role(path: str | PurePosixPath) -> FrontendRole:
    normalized = _normalize_path(path)
    pure_path = PurePosixPath(normalized)
    parts = pure_path.parts
    name = pure_path.name

    if name in _LOCKFILES:
        return FrontendRole("lockfile")
    if parts and parts[0] in {"temp", "tmp", ".cache"}:
        return FrontendRole("scratch_temp")
    if _is_type_decl(normalized, parts):
        return FrontendRole("type_decl")
    if _is_under(parts, "src", "router") or _is_under(parts, "src", "routes"):
        return FrontendRole("route_config")
    if _is_under(parts, "src", "views") or _is_under(parts, "src", "pages"):
        return FrontendRole("view_page")
    if (
        normalized == "src/components/applayout.vue"
        or _is_under(parts, "src", "components", "layout")
        or _is_under(parts, "src", "layouts")
    ):
        return FrontendRole("layout_component")
    if _is_under(parts, "src", "components"):
        return FrontendRole("shared_component")
    if _is_under(parts, "src", "stores") or _is_under(parts, "src", "store"):
        return FrontendRole("store")
    if _is_under(parts, "src", "services") or _is_under(parts, "src", "api"):
        return FrontendRole("service")
    if (
        _is_under(parts, "src", "utils")
        or _is_under(parts, "src", "lib")
        or _is_under(parts, "src", "helpers")
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
    has_package_json = any(path == "package.json" or path.endswith("/package.json") for path in normalized_paths)
    has_view_or_page = any(path.startswith(("src/views/", "src/pages/")) for path in normalized_paths)
    has_component = any(path.startswith("src/components/") for path in normalized_paths)
    return has_package_json and has_view_or_page and has_component


def frontend_candidate_scope_enabled(paths: Iterable[str | PurePosixPath]) -> bool:
    roles = {classify_frontend_role(path).name for path in paths}
    support_roles = {
        "layout_component",
        "shared_component",
        "store",
        "service",
        "utility",
        "route_config",
        "type_decl",
    }
    return "view_page" in roles and bool(roles & support_roles)


def _normalize_path(path: str | PurePosixPath) -> str:
    raw_path = path.as_posix() if isinstance(path, PurePosixPath) else str(path)
    normalized = raw_path.replace("\\", "/").lower()
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def _is_type_decl(path: str, parts: tuple[str, ...]) -> bool:
    return _is_under(parts, "src", "types") or (path.startswith("src/") and path.endswith(".d.ts"))


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


def _clamp(score: float) -> float:
    return max(0.0, min(1.0, score))
