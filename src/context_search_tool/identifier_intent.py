from __future__ import annotations

import re
from dataclasses import dataclass


_CAMEL_OR_PASCAL_RE = re.compile(r"\b[A-Z]?[a-z]+(?:[A-Z][A-Za-z0-9]*)+\b")
_SNAKE_IDENTIFIER_RE = re.compile(r"\b[a-z][a-z0-9]+(?:_[a-z0-9]+)+\b")
_FILE_HINT_RE = re.compile(r"(?i)(?<![\w.-])[\w-]+(?:\.[\w-]+)+(?![\w.-])")

_ROLE_HINTS = {
    "store": "state_store",
    "stores": "state_store",
    "pinia": "state_store",
    "redux": "state_store",
    "zustand": "state_store",
    "composable": "composable",
    "composables": "composable",
    "hook": "composable",
    "hooks": "composable",
    "service": "service",
    "services": "service",
    "handler": "handler",
    "handlers": "handler",
    "middleware": "middleware",
    "middlewares": "middleware",
    "router": "router",
    "route": "router",
    "routes": "router",
    "controller": "entrypoint",
    "controllers": "entrypoint",
    "repository": "repository",
    "repositories": "repository",
    "repo": "repository",
    "source": "source_adapter",
    "adapter": "source_adapter",
    "client": "source_adapter",
    "view": "view",
    "views": "view",
    "page": "view",
    "pages": "view",
    "component": "component",
    "components": "component",
    "type": "data_type",
    "types": "data_type",
    "dto": "data_type",
    "entity": "data_type",
    "model": "data_type",
    "command": "command",
    "commands": "command",
    "engine": "engine",
}


@dataclass(frozen=True)
class IdentifierIntent:
    identifiers: tuple[str, ...] = ()
    file_hints: tuple[str, ...] = ()
    suffix_hints: tuple[str, ...] = ()
    role_hints: tuple[str, ...] = ()


def infer_identifier_intent(query: str, tokens: list[str]) -> IdentifierIntent:
    identifiers: list[str] = []
    file_hints: list[str] = []
    suffix_hints: list[str] = []
    role_hints: list[str] = []

    for match in _CAMEL_OR_PASCAL_RE.findall(query):
        _append_unique(identifiers, match)
    for match in _SNAKE_IDENTIFIER_RE.findall(query):
        _append_unique(identifiers, match)
    for match in _FILE_HINT_RE.findall(query):
        normalized = match.lower()
        _append_unique(file_hints, normalized)
        suffix = "." + normalized.rsplit(".", 1)[-1]
        _append_unique(suffix_hints, suffix)

    for token in [*tokens, *re.findall(r"[A-Za-z0-9_+-]+", query)]:
        role = _ROLE_HINTS.get(token.lower())
        if role:
            _append_unique(role_hints, role)

    return IdentifierIntent(
        identifiers=tuple(sorted(identifiers)),
        file_hints=tuple(file_hints),
        suffix_hints=tuple(suffix_hints),
        role_hints=tuple(role_hints),
    )


def _append_unique(values: list[str], value: str) -> None:
    if value and value not in values:
        values.append(value)
