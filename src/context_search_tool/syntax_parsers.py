from __future__ import annotations

from functools import lru_cache

import tree_sitter_java
import tree_sitter_javascript
import tree_sitter_typescript
from tree_sitter import Language, Parser, Tree


@lru_cache(maxsize=1)
def _java_language() -> Language:
    return Language(tree_sitter_java.language())


@lru_cache(maxsize=1)
def _javascript_language() -> Language:
    return Language(tree_sitter_javascript.language())


@lru_cache(maxsize=1)
def _typescript_language() -> Language:
    return Language(tree_sitter_typescript.language_typescript())


@lru_cache(maxsize=1)
def _tsx_language() -> Language:
    return Language(tree_sitter_typescript.language_tsx())


def _parse(source: bytes, language: Language) -> Tree:
    if not isinstance(source, bytes):
        raise TypeError("source must be bytes")
    tree = Parser(language).parse(source)
    if tree is None:  # pragma: no cover - a fresh parser has no timeout
        raise RuntimeError("parser did not return a syntax tree")
    return tree


def parse_java(source: bytes) -> Tree:
    return _parse(source, _java_language())


def parse_javascript(source: bytes) -> Tree:
    return _parse(source, _javascript_language())


def parse_jsx(source: bytes) -> Tree:
    return _parse(source, _javascript_language())


def parse_typescript(source: bytes) -> Tree:
    return _parse(source, _typescript_language())


def parse_tsx(source: bytes) -> Tree:
    return _parse(source, _tsx_language())
