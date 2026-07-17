from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Any, Mapping, Protocol

from context_search_tool.models import (
    CodeRelation,
    CodeSignal,
    DocumentChunk,
    SymbolRef,
)


def _normalized_path(value: Path | str, name: str) -> Path:
    text = value.as_posix() if isinstance(value, Path) else value
    if not isinstance(text, str) or not text or text == "." or "\\" in text:
        raise ValueError(f"{name} must be a repository-relative POSIX path")
    path = PurePosixPath(text)
    if (
        path.is_absolute()
        or any(part in {"", ".", ".."} for part in path.parts)
        or path.as_posix() != text
    ):
        raise ValueError(f"{name} must be normalized and repository-relative")
    return Path(text)


def _normalized_unit_key(value: str) -> str:
    if not isinstance(value, str) or "\\" in value:
        raise ValueError("project_unit_key must be a repository-relative POSIX path")
    if not value:
        return ""
    return _normalized_path(value, "project_unit_key").as_posix()


@dataclass(frozen=True)
class PluginContext:
    file_path: Path
    language: str
    project_unit_key: str
    project_metadata: Mapping[str, Any] = field(default_factory=dict)
    active_paths: tuple[Path, ...] = ()
    active_path_project_units: tuple[tuple[Path, str], ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.language, str) or not self.language.strip():
            raise ValueError("language must be a non-empty string")
        file_path = _normalized_path(self.file_path, "file_path")
        unit_key = _normalized_unit_key(self.project_unit_key)
        active_paths = tuple(
            sorted(
                {
                    _normalized_path(path, "active path")
                    for path in self.active_paths
                },
                key=lambda path: path.as_posix(),
            )
        )
        units = tuple(
            sorted(
                {
                    (
                        _normalized_path(path, "active project path"),
                        _normalized_unit_key(key),
                    )
                    for path, key in self.active_path_project_units
                },
                key=lambda item: (item[0].as_posix(), item[1]),
            )
        )
        object.__setattr__(self, "file_path", file_path)
        object.__setattr__(self, "language", self.language.strip().lower())
        object.__setattr__(self, "project_unit_key", unit_key)
        object.__setattr__(
            self,
            "project_metadata",
            MappingProxyType(dict(self.project_metadata)),
        )
        object.__setattr__(self, "active_paths", active_paths)
        object.__setattr__(self, "active_path_project_units", units)

    @property
    def source_path(self) -> Path:
        return self.file_path

    def project_unit_for_path(self, path: Path | str) -> str:
        normalized = _normalized_path(path, "target path")
        by_path = dict(self.active_path_project_units)
        return by_path.get(normalized, self.project_unit_key)


@dataclass(frozen=True)
class ParsedGraphFacts:
    facts: object
    symbols: tuple[SymbolRef, ...] = ()
    lexical_tokens: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)
    fallback_required: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "symbols", tuple(self.symbols))
        object.__setattr__(self, "lexical_tokens", tuple(self.lexical_tokens))
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))


@dataclass(frozen=True)
class MaterializedGraph:
    signals: tuple[CodeSignal, ...] = ()
    relations: tuple[CodeRelation, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "signals", tuple(self.signals))
        object.__setattr__(self, "relations", tuple(self.relations))
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))


class GraphLanguagePlugin(Protocol):
    def supports(self, context: PluginContext) -> bool: ...

    def parse(self, context: PluginContext, content: bytes) -> ParsedGraphFacts: ...

    def materialize(
        self,
        context: PluginContext,
        parsed: ParsedGraphFacts,
        chunks: tuple[DocumentChunk, ...],
        module_signal: CodeSignal,
    ) -> MaterializedGraph: ...
