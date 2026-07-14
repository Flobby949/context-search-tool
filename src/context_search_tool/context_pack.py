from __future__ import annotations

from dataclasses import dataclass

from context_search_tool.config import ToolConfig


CONTEXT_PACK_SCHEMA_VERSION = 1
CONTEXT_GROUPS = (
    "entrypoints",
    "implementations",
    "related_types",
    "tests",
    "configs_docs",
    "supporting",
)


class ContextPackError(Exception):
    """A bounded public failure of the ContextPack contract."""


@dataclass(frozen=True)
class ContextPackOptions:
    max_results: int
    max_evidence_anchors: int
    context_before_lines: int
    context_after_lines: int
    full_file: bool
    max_full_file_bytes: int


@dataclass(frozen=True)
class ContextPackItem:
    id: str
    source: str
    source_index: int
    file_path: str
    start_line: int
    end_line: int
    group: str
    role: str
    classification_basis: str


@dataclass(frozen=True)
class MissingEvidence:
    category: str
    required: bool
    reason: str


@dataclass(frozen=True)
class NextQuery:
    query: str
    purpose: str
    reason: str


@dataclass(frozen=True)
class ReadinessConfidence:
    level: str
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class ContextBudget:
    max_results: int
    max_evidence_anchors: int
    max_items: int
    included_results: int
    included_evidence_anchors: int
    content_bytes: int
    context_before_lines: int
    context_after_lines: int
    full_file: bool
    max_full_file_bytes: int


@dataclass(frozen=True)
class ContextPack:
    schema_version: int
    status: str
    items: tuple[ContextPackItem, ...]
    groups: dict[str, tuple[str, ...]]
    reading_order: tuple[str, ...]
    missing_evidence: tuple[MissingEvidence, ...]
    next_queries: tuple[NextQuery, ...]
    confidence: ReadinessConfidence
    budget: ContextBudget


DUPLICATE_ITEM_ERROR = "duplicate ContextPack item id"
INVALID_REFERENCE_ERROR = "invalid ContextPack item reference"
INVALID_CLASSIFICATION_ERROR = "invalid ContextPack classification"
BUDGET_EXCEEDED_ERROR = "ContextPack budget exceeded"
NON_JSON_ERROR = "ContextPack contains a non-JSON value"
UNEXPECTED_CONTEXT_ERROR = "Context pack construction failed"


def resolve_context_pack_options(
    config: ToolConfig,
    *,
    context_lines: int | None,
    full_file: bool,
    max_evidence_anchors: int,
) -> ContextPackOptions:
    """Resolve request/config inputs without importing the retrieval module."""
    if context_lines is None:
        context_before_lines = max(0, config.retrieval.context_before_lines)
        context_after_lines = max(0, config.retrieval.context_after_lines)
    else:
        effective_context_lines = max(0, context_lines)
        context_before_lines = effective_context_lines
        context_after_lines = effective_context_lines

    return ContextPackOptions(
        max_results=config.retrieval.final_top_k,
        max_evidence_anchors=max_evidence_anchors,
        context_before_lines=context_before_lines,
        context_after_lines=context_after_lines,
        full_file=full_file,
        max_full_file_bytes=config.index.max_full_file_bytes,
    )
