from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Protocol, TypeVar

from context_search_tool.graph_plugins import GraphLanguagePlugin
from context_search_tool.models import CodeRelation, CodeSignal, SymbolRef


@dataclass(frozen=True)
class PluginExtraction:
    symbols: list[SymbolRef] = field(default_factory=list)
    signals: list[CodeSignal] = field(default_factory=list)
    relations: list[CodeRelation] = field(default_factory=list)
    lexical_tokens: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class LanguagePlugin(Protocol):
    def supports(self, path: Path, language: str) -> bool:
        ...

    def extract(self, path: Path, content: str) -> PluginExtraction:
        ...


_GraphPlugin = TypeVar("_GraphPlugin")


def ordered_graph_plugins(
    plugins: Iterable[_GraphPlugin],
) -> tuple[_GraphPlugin, ...]:
    values = tuple(plugins)
    if len({id(plugin) for plugin in values}) != len(values):
        raise ValueError("graph plugin instances must be unique")
    return tuple(
        sorted(
            values,
            key=lambda plugin: (
                type(plugin).__module__,
                type(plugin).__qualname__,
                str(getattr(plugin, "name", "")),
            ),
        )
    )


def default_plugins() -> list[GraphLanguagePlugin]:
    from context_search_tool.java_plugin import JavaPlugin
    from context_search_tool.frontend_graph import FrontendGraphProducer
    from context_search_tool.mybatis_xml import MyBatisGraphProducer

    return [JavaPlugin(), FrontendGraphProducer(), MyBatisGraphProducer()]
