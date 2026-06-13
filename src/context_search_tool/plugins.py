from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from context_search_tool.models import SymbolRef


@dataclass(frozen=True)
class PluginExtraction:
    symbols: list[SymbolRef] = field(default_factory=list)
    lexical_tokens: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class LanguagePlugin(Protocol):
    def supports(self, path: Path, language: str) -> bool:
        ...

    def extract(self, path: Path, content: str) -> PluginExtraction:
        ...


def default_plugins() -> list[LanguagePlugin]:
    from context_search_tool.java_plugin import JavaPlugin

    return [JavaPlugin()]
