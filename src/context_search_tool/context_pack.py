from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from context_search_tool.config import ToolConfig
from context_search_tool.frontend_roles import classify_frontend_role
from context_search_tool.path_roles import classify_path_role

if TYPE_CHECKING:
    from context_search_tool.retrieval import QueryBundle


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


_PATH_GROUPS = {
    "test": "tests",
    "deployment_config": "configs_docs",
    "config_example": "configs_docs",
    "runtime_config": "configs_docs",
    "config": "configs_docs",
    "doc": "configs_docs",
    "entrypoint": "entrypoints",
    "router": "entrypoints",
    "command": "entrypoints",
    "handler": "entrypoints",
    "view": "entrypoints",
    "service_impl": "implementations",
    "executor": "implementations",
    "engine": "implementations",
    "middleware": "implementations",
    "storage": "implementations",
    "service": "implementations",
    "repository": "implementations",
    "source_adapter": "implementations",
    "state_store": "implementations",
    "composable": "implementations",
    "scheduler": "implementations",
    "data_type": "related_types",
    "service_interface": "related_types",
    "generated_output": "supporting",
    "lockfile": "supporting",
}
_FRONTEND_GROUPS = {
    "route_config": "entrypoints",
    "view_page": "entrypoints",
    "layout_component": "entrypoints",
    "service": "implementations",
    "utility": "implementations",
    "store": "implementations",
    "shared_component": "implementations",
    "type_decl": "related_types",
    "lockfile": "supporting",
    "scratch_temp": "supporting",
}
_GENERIC_PATH_ROLES = {
    "test",
    "deployment_config",
    "config_example",
    "runtime_config",
    "config",
    "doc",
}
_SUMMARY_CLASSIFICATIONS = (
    ("entry_points", "entrypoints", "summary_entrypoint"),
    ("implementation", "implementations", "summary_implementation"),
    ("related_types", "related_types", "summary_related_type"),
)
_ANCHOR_CLASSIFICATIONS = {
    "readme": ("configs_docs", "readme", "anchor_kind"),
    "risks": ("configs_docs", "risks", "anchor_kind"),
    "pom": ("configs_docs", "pom", "anchor_kind"),
}
_APPROVED_CLASSIFICATIONS = frozenset(
    {(group, role, "path_role") for role, group in _PATH_GROUPS.items()}
    | {(group, role, "frontend_role") for role, group in _FRONTEND_GROUPS.items()}
    | {
        (group, role, "retrieval_summary")
        for _, group, role in _SUMMARY_CLASSIFICATIONS
    }
    | set(_ANCHOR_CLASSIFICATIONS.values())
    | {
        ("supporting", "source", "fallback"),
        ("supporting", "component", "fallback"),
        ("supporting", "evidence_anchor", "fallback"),
    }
)


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


def build_context_pack(bundle: QueryBundle, options: ContextPackOptions) -> ContextPack:
    """Build and validate one deterministic, I/O-free ContextPack."""
    if (
        len(bundle.results) > options.max_results
        or len(bundle.evidence_anchors) > options.max_evidence_anchors
    ):
        raise ContextPackError(BUDGET_EXCEEDED_ERROR)

    items: list[ContextPackItem] = []
    for source_index, raw_result in enumerate(bundle.results):
        group, role, classification_basis = _classify_result(
            raw_result,
            bundle.summary,
        )
        items.append(
            ContextPackItem(
                id=f"result:{source_index}",
                source="result",
                source_index=source_index,
                file_path=raw_result.file_path.as_posix(),
                start_line=raw_result.start_line,
                end_line=raw_result.end_line,
                group=group,
                role=role,
                classification_basis=classification_basis,
            )
        )

    for source_index, raw_anchor in enumerate(bundle.evidence_anchors):
        if type(raw_anchor.anchor_kind) is not str:
            raise ContextPackError(INVALID_CLASSIFICATION_ERROR)
        group, role, classification_basis = _ANCHOR_CLASSIFICATIONS.get(
            raw_anchor.anchor_kind,
            ("supporting", "evidence_anchor", "fallback"),
        )
        items.append(
            ContextPackItem(
                id=f"anchor:{source_index}",
                source="anchor",
                source_index=source_index,
                file_path=raw_anchor.file_path.as_posix(),
                start_line=raw_anchor.start_line,
                end_line=raw_anchor.end_line,
                group=group,
                role=role,
                classification_basis=classification_basis,
            )
        )

    item_tuple = tuple(items)
    groups = {
        group: tuple(item.id for item in item_tuple if item.group == group)
        for group in CONTEXT_GROUPS
    }
    reading_order = tuple(
        item_id
        for group in CONTEXT_GROUPS
        for item_id in groups[group]
    )
    pack = ContextPack(
        schema_version=CONTEXT_PACK_SCHEMA_VERSION,
        status="empty" if not items else "ready",
        items=item_tuple,
        groups=groups,
        reading_order=reading_order,
        missing_evidence=(),
        next_queries=(),
        confidence=ReadinessConfidence(
            level="none" if not items else "medium",
            reasons=(),
        ),
        budget=ContextBudget(
            max_results=options.max_results,
            max_evidence_anchors=options.max_evidence_anchors,
            max_items=options.max_results + options.max_evidence_anchors,
            included_results=len(bundle.results),
            included_evidence_anchors=len(bundle.evidence_anchors),
            content_bytes=sum(
                len(source.content.encode("utf-8"))
                for source in (*bundle.results, *bundle.evidence_anchors)
            ),
            context_before_lines=options.context_before_lines,
            context_after_lines=options.context_after_lines,
            full_file=options.full_file,
            max_full_file_bytes=options.max_full_file_bytes,
        ),
    )
    _validate_context_pack(bundle, pack)
    return pack


def _classify_result(
    raw_result: Any,
    summary: Any,
) -> tuple[str, str, str]:
    path_role = classify_path_role(raw_result.file_path, raw_result.content)
    path_role_name = getattr(path_role, "name", None)
    if not isinstance(path_role_name, str) or path_role_name not in {
        *_PATH_GROUPS,
        "source",
        "component",
    }:
        raise ContextPackError(INVALID_CLASSIFICATION_ERROR)

    if path_role_name in _GENERIC_PATH_ROLES:
        return _PATH_GROUPS[path_role_name], path_role_name, "path_role"

    frontend_role = classify_frontend_role(raw_result.file_path.as_posix())
    frontend_role_name = getattr(frontend_role, "name", None)
    if not isinstance(frontend_role_name, str) or frontend_role_name not in {
        *_FRONTEND_GROUPS,
        "other",
    }:
        raise ContextPackError(INVALID_CLASSIFICATION_ERROR)

    if frontend_role_name != "other":
        return (
            _FRONTEND_GROUPS[frontend_role_name],
            frontend_role_name,
            "frontend_role",
        )

    if path_role_name in _PATH_GROUPS:
        return _PATH_GROUPS[path_role_name], path_role_name, "path_role"

    stem = raw_result.file_path.stem.casefold()
    if type(summary.entry_points) is not list:
        raise ContextPackError(INVALID_CLASSIFICATION_ERROR)
    for name in summary.entry_points:
        if type(name) is not str:
            raise ContextPackError(INVALID_CLASSIFICATION_ERROR)
        if name.casefold() == stem:
            return "entrypoints", "summary_entrypoint", "retrieval_summary"
    if type(summary.implementation) is not list:
        raise ContextPackError(INVALID_CLASSIFICATION_ERROR)
    for name in summary.implementation:
        if type(name) is not str:
            raise ContextPackError(INVALID_CLASSIFICATION_ERROR)
        folded_name = name.casefold()
        if folded_name == stem or folded_name.startswith(f"{stem}."):
            return "implementations", "summary_implementation", "retrieval_summary"
    if type(summary.related_types) is not list:
        raise ContextPackError(INVALID_CLASSIFICATION_ERROR)
    for name in summary.related_types:
        if type(name) is not str:
            raise ContextPackError(INVALID_CLASSIFICATION_ERROR)
        if name.casefold() == stem:
            return "related_types", "summary_related_type", "retrieval_summary"
    return "supporting", path_role_name, "fallback"


def _validate_context_pack(bundle: QueryBundle, pack: ContextPack) -> None:
    if (
        type(pack.schema_version) is not int
        or pack.schema_version != CONTEXT_PACK_SCHEMA_VERSION
        or type(pack.items) is not tuple
        or any(type(item) is not ContextPackItem for item in pack.items)
        or type(pack.groups) is not dict
        or type(pack.reading_order) is not tuple
    ):
        raise ContextPackError(INVALID_REFERENCE_ERROR)

    group_keys = tuple(pack.groups)
    if (
        any(type(group) is not str for group in group_keys)
        or group_keys != CONTEXT_GROUPS
        or any(
            type(item_ids) is not tuple
            or any(type(item_id) is not str for item_id in item_ids)
            for item_ids in pack.groups.values()
        )
        or any(type(item_id) is not str for item_id in pack.reading_order)
    ):
        raise ContextPackError(INVALID_REFERENCE_ERROR)

    for item in pack.items:
        if (
            type(item.id) is not str
            or type(item.source) is not str
            or type(item.source_index) is not int
            or type(item.file_path) is not str
            or type(item.start_line) is not int
            or type(item.end_line) is not int
        ):
            raise ContextPackError(INVALID_REFERENCE_ERROR)
        if (
            type(item.group) is not str
            or type(item.role) is not str
            or type(item.classification_basis) is not str
        ):
            raise ContextPackError(INVALID_CLASSIFICATION_ERROR)

    item_ids = tuple(item.id for item in pack.items)
    if len(item_ids) != len(set(item_ids)):
        raise ContextPackError(DUPLICATE_ITEM_ERROR)

    source_rows = tuple(
        ("result", source_index, raw_result)
        for source_index, raw_result in enumerate(bundle.results)
    ) + tuple(
        ("anchor", source_index, raw_anchor)
        for source_index, raw_anchor in enumerate(bundle.evidence_anchors)
    )
    expected_ids = tuple(
        f"{source}:{source_index}"
        for source, source_index, _ in source_rows
    )
    if item_ids != expected_ids:
        raise ContextPackError(INVALID_REFERENCE_ERROR)

    for item, (source, source_index, raw_source) in zip(pack.items, source_rows):
        try:
            valid_source_reference = (
                item.source == source
                and item.source_index == source_index
                and item.file_path == raw_source.file_path.as_posix()
                and item.start_line == raw_source.start_line
                and item.end_line == raw_source.end_line
            )
        except (AttributeError, TypeError, ValueError):
            valid_source_reference = False
        if not valid_source_reference:
            raise ContextPackError(INVALID_REFERENCE_ERROR)

        classification = (
            item.group,
            item.role,
            item.classification_basis,
        )
        if classification not in _APPROVED_CLASSIFICATIONS:
            raise ContextPackError(INVALID_CLASSIFICATION_ERROR)

    expected_groups = {
        group: tuple(item.id for item in pack.items if item.group == group)
        for group in CONTEXT_GROUPS
    }
    if pack.groups != expected_groups:
        raise ContextPackError(INVALID_REFERENCE_ERROR)

    expected_reading_order = tuple(
        item_id
        for group in CONTEXT_GROUPS
        for item_id in expected_groups[group]
    )
    if pack.reading_order != expected_reading_order:
        raise ContextPackError(INVALID_REFERENCE_ERROR)

    budget = pack.budget
    if type(budget) is not ContextBudget:
        raise ContextPackError(BUDGET_EXCEEDED_ERROR)
    budget_integer_fields = (
        budget.max_results,
        budget.max_evidence_anchors,
        budget.max_items,
        budget.included_results,
        budget.included_evidence_anchors,
        budget.content_bytes,
        budget.context_before_lines,
        budget.context_after_lines,
        budget.max_full_file_bytes,
    )
    if (
        any(type(value) is not int for value in budget_integer_fields)
        or type(budget.full_file) is not bool
    ):
        raise ContextPackError(BUDGET_EXCEEDED_ERROR)

    try:
        actual_results = len(bundle.results)
        actual_anchors = len(bundle.evidence_anchors)
        expected_content_bytes = sum(
            len(source.content.encode("utf-8"))
            for source in (*bundle.results, *bundle.evidence_anchors)
        )
        valid_budget = (
            actual_results <= budget.max_results
            and actual_anchors <= budget.max_evidence_anchors
            and budget.max_items
            == budget.max_results + budget.max_evidence_anchors
            and budget.included_results == actual_results
            and budget.included_evidence_anchors == actual_anchors
            and budget.content_bytes == expected_content_bytes
        )
    except (AttributeError, TypeError, UnicodeError, ValueError):
        valid_budget = False
    if not valid_budget:
        raise ContextPackError(BUDGET_EXCEEDED_ERROR)
