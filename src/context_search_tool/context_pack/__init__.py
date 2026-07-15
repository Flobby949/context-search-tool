from __future__ import annotations

import json
from dataclasses import dataclass
from math import isfinite
from typing import TYPE_CHECKING, Any

from context_search_tool.config import ToolConfig
from context_search_tool.frontend_roles import classify_frontend_role
from context_search_tool.identifier_intent import infer_identifier_intent
from context_search_tool.path_roles import classify_path_role
from context_search_tool.query_intent import infer_query_intent
from context_search_tool.tokenizer import tokenize_query

if TYPE_CHECKING:
    from context_search_tool.models import EvidenceAnchor, RetrievalResult
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


@dataclass(frozen=True)
class _ExpectedGroups:
    explicit_required: tuple[str, ...]
    required: tuple[str, ...]
    recommended: tuple[str, ...]


DUPLICATE_ITEM_ERROR = "duplicate ContextPack item id"
INVALID_REFERENCE_ERROR = "invalid ContextPack item reference"
INVALID_CLASSIFICATION_ERROR = "invalid ContextPack classification"
BUDGET_EXCEEDED_ERROR = "ContextPack budget exceeded"
NON_JSON_ERROR = "ContextPack contains a non-JSON value"
UNEXPECTED_CONTEXT_ERROR = "Context pack construction failed"


_EMPTY_MISSING_EVIDENCE = (
    MissingEvidence(
        category="results",
        required=True,
        reason="no result or evidence anchor is present in the bounded result set",
    ),
)
_EMPTY_CONFIDENCE = ReadinessConfidence(
    level="none",
    reasons=("no result or evidence anchor is present",),
)
_NEXT_QUERY_RULES = {
    "entrypoints": (
        ("implementation", "related_types", "entry_points"),
        "find_entrypoints",
        "controller route entrypoint",
    ),
    "implementations": (
        ("entry_points", "related_types", "implementation"),
        "find_implementations",
        "service implementation",
    ),
    "related_types": (
        ("implementation", "entry_points", "related_types"),
        "find_related_types",
        "dto model type",
    ),
    "tests": (
        ("implementation", "entry_points", "related_types"),
        "find_tests",
        "test",
    ),
    "configs_docs": (
        ("entry_points", "implementation", "related_types"),
        "find_configs_docs",
        "config documentation",
    ),
}
_NEXT_QUERY_PURPOSES = frozenset(
    purpose for _, purpose, _ in _NEXT_QUERY_RULES.values()
)
_CONFIDENCE_LEVELS = frozenset({"none", "low", "medium", "high"})


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
_ENTRYPOINT_IDENTIFIER_ROLES = frozenset({"entrypoint", "router", "command", "view"})
_IMPLEMENTATION_IDENTIFIER_ROLES = frozenset(
    {
        "state_store",
        "composable",
        "service",
        "handler",
        "middleware",
        "repository",
        "source_adapter",
        "storage",
        "component",
        "engine",
    }
)
_PLANNER_FLOW_INTENTS = frozenset({"feature_lookup", "data_flow", "bug_trace"})
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


def resolve_context_item(
    bundle: QueryBundle,
    item: ContextPackItem,
) -> RetrievalResult | EvidenceAnchor:
    """Dereference one response-local item or raise the fixed reference error."""
    if type(item) is not ContextPackItem:
        raise ContextPackError(INVALID_REFERENCE_ERROR)
    if type(item.source) is not str or item.source not in {"result", "anchor"}:
        raise ContextPackError(INVALID_REFERENCE_ERROR)
    if type(item.source_index) is not int or item.source_index < 0:
        raise ContextPackError(INVALID_REFERENCE_ERROR)
    if (
        type(item.id) is not str
        or item.id != f"{item.source}:{item.source_index}"
        or type(item.file_path) is not str
        or type(item.start_line) is not int
        or type(item.end_line) is not int
    ):
        raise ContextPackError(INVALID_REFERENCE_ERROR)

    sources = bundle.results if item.source == "result" else bundle.evidence_anchors
    if item.source_index >= len(sources):
        raise ContextPackError(INVALID_REFERENCE_ERROR)
    raw_source = sources[item.source_index]
    try:
        raw_file_path = raw_source.file_path.as_posix()
        valid_repeated_fields = (
            type(raw_file_path) is str
            and type(raw_source.start_line) is int
            and type(raw_source.end_line) is int
            and item.file_path == raw_file_path
            and item.start_line == raw_source.start_line
            and item.end_line == raw_source.end_line
        )
    except (AttributeError, TypeError, ValueError):
        valid_repeated_fields = False
    if not valid_repeated_fields:
        raise ContextPackError(INVALID_REFERENCE_ERROR)
    return raw_source


def context_pack_payload(bundle: QueryBundle, pack: ContextPack) -> dict[str, Any]:
    """Validate references and return JSON-native ContextPack schema v1."""
    if type(pack) is not ContextPack:
        raise ContextPackError(INVALID_REFERENCE_ERROR)
    payload = _materialize_context_pack_payload(pack)
    try:
        is_json_native = _is_json_native(payload)
    except RecursionError:
        raise ContextPackError(NON_JSON_ERROR) from None
    if not is_json_native:
        raise ContextPackError(NON_JSON_ERROR)
    try:
        json.dumps(payload, allow_nan=False)
    except (TypeError, ValueError, OverflowError, RecursionError):
        raise ContextPackError(NON_JSON_ERROR) from None
    _validate_context_pack(bundle, pack)
    return payload


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
    expected = _derive_expected_groups(bundle, groups)
    reading_order = _build_reading_order(groups, expected.explicit_required)
    missing_evidence = (
        _build_missing_evidence(expected, groups)
        if items
        else _EMPTY_MISSING_EVIDENCE
    )
    next_queries = _build_next_queries(bundle, missing_evidence)
    confidence = _build_readiness_confidence(
        bundle,
        expected,
        missing_evidence,
    )
    pack = ContextPack(
        schema_version=CONTEXT_PACK_SCHEMA_VERSION,
        status=(
            "empty"
            if not items
            else "partial"
            if any(evidence.required for evidence in missing_evidence)
            else "ready"
        ),
        items=item_tuple,
        groups=groups,
        reading_order=reading_order,
        missing_evidence=missing_evidence,
        next_queries=next_queries,
        confidence=confidence,
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
    _validate_context_pack(bundle, pack, expected)
    return pack


def _derive_expected_groups(
    bundle: QueryBundle,
    groups: dict[str, tuple[str, ...]],
) -> _ExpectedGroups:
    query_intent = infer_query_intent(bundle.query, bundle.query.split())
    identifier_intent = infer_identifier_intent(
        bundle.query,
        tokenize_query(bundle.query),
    )

    target_roles = query_intent.target_roles
    role_hints = set(identifier_intent.role_hints)
    explicit: set[str] = set()
    if "entrypoint" in target_roles:
        explicit.add("entrypoints")
    if "implementation" in target_roles:
        explicit.add("implementations")
    if role_hints.intersection(_ENTRYPOINT_IDENTIFIER_ROLES):
        explicit.add("entrypoints")
    if role_hints.intersection(_IMPLEMENTATION_IDENTIFIER_ROLES):
        explicit.add("implementations")
    if "data_type" in role_hints:
        explicit.add("related_types")
    if "test" in target_roles and query_intent.wants_artifact:
        explicit.add("tests")
    if (
        target_roles.intersection({"config", "deploy", "doc"})
        and query_intent.wants_artifact
    ):
        explicit.add("configs_docs")

    explicit_required = _ordered_context_groups(explicit)
    required = set(explicit_required)
    planner_ok = bundle.planner.status == "ok"
    planner_intent = bundle.planner.intent
    if not explicit_required and planner_ok:
        if planner_intent in _PLANNER_FLOW_INTENTS:
            required.update({"entrypoints", "implementations"})
        elif planner_intent == "endpoint_lookup":
            required.add("entrypoints")

    recommended: set[str] = set()
    if planner_ok:
        if planner_intent in _PLANNER_FLOW_INTENTS:
            recommended.update({"related_types", "tests"})
        elif planner_intent == "endpoint_lookup":
            recommended.update({"implementations", "tests"})
    if "entrypoint" in target_roles:
        recommended.update({"implementations", "tests"})

    successful_non_unknown_planner = planner_ok and planner_intent != "unknown"
    if not successful_non_unknown_planner and not explicit_required:
        if groups["entrypoints"] and not groups["implementations"]:
            recommended.add("implementations")
        if groups["implementations"] and not groups["entrypoints"]:
            recommended.add("entrypoints")

    recommended.difference_update(required)
    return _ExpectedGroups(
        explicit_required=explicit_required,
        required=_ordered_context_groups(required),
        recommended=_ordered_context_groups(recommended),
    )


def _ordered_context_groups(selected: set[str]) -> tuple[str, ...]:
    return tuple(group for group in CONTEXT_GROUPS if group in selected)


def _build_reading_order(
    groups: dict[str, tuple[str, ...]],
    promoted: tuple[str, ...],
) -> tuple[str, ...]:
    ordered_groups = (
        *promoted,
        *(group for group in CONTEXT_GROUPS if group not in promoted),
    )
    return tuple(
        item_id
        for group in ordered_groups
        for item_id in groups[group]
    )


def _build_missing_evidence(
    expected: _ExpectedGroups,
    groups: dict[str, tuple[str, ...]],
) -> tuple[MissingEvidence, ...]:
    missing_required = tuple(
        group for group in expected.required if not groups[group]
    )
    missing_recommended = tuple(
        group for group in expected.recommended if not groups[group]
    )
    return tuple(
        MissingEvidence(
            category=group,
            required=True,
            reason=(
                f"required evidence for {group} is missing from the bounded result set"
            ),
        )
        for group in missing_required
    ) + tuple(
        MissingEvidence(
            category=group,
            required=False,
            reason=(
                f"recommended evidence for {group} is missing from the bounded result set"
            ),
        )
        for group in missing_recommended
    )


def _build_next_queries(
    bundle: QueryBundle,
    missing_evidence: tuple[MissingEvidence, ...],
) -> tuple[NextQuery, ...]:
    suggestions: list[NextQuery] = []
    seen: set[str] = set()
    for evidence in missing_evidence:
        rule = _NEXT_QUERY_RULES.get(evidence.category)
        if rule is None:
            continue
        summary_fields, purpose, role_terms = rule
        seed = _select_next_query_seed(bundle, summary_fields)
        query = _compose_next_query(seed, role_terms)
        if query is None:
            continue
        dedupe_key = _normalize_query_text(query).casefold()
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        suggestions.append(
            NextQuery(
                query=query,
                purpose=purpose,
                reason=evidence.reason,
            )
        )
        if len(suggestions) == 3:
            break
    return tuple(suggestions)


def _select_next_query_seed(
    bundle: QueryBundle,
    summary_fields: tuple[str, ...],
) -> str:
    for field_name in summary_fields:
        values = getattr(bundle.summary, field_name, None)
        if type(values) is not list:
            continue
        for value in values:
            normalized = _normalize_query_text(value)
            if normalized:
                return normalized

    if bundle.results:
        return _normalize_query_text(bundle.results[0].file_path.stem)
    return _normalize_query_text(bundle.query)


def _normalize_query_text(value: Any) -> str:
    if type(value) is not str:
        return ""
    return " ".join(value.strip().split())


def _compose_next_query(seed: str, role_terms: str) -> str | None:
    if not seed:
        return None
    max_seed_length = 160 - len(role_terms) - 1
    bounded_seed = seed[:max_seed_length].strip()
    if not bounded_seed:
        return None
    return f"{bounded_seed} {role_terms}"


def _build_readiness_confidence(
    bundle: QueryBundle,
    expected: _ExpectedGroups,
    missing_evidence: tuple[MissingEvidence, ...],
) -> ReadinessConfidence:
    if not bundle.results and not bundle.evidence_anchors:
        return _EMPTY_CONFIDENCE

    missing_required = tuple(
        group
        for group in CONTEXT_GROUPS
        if any(
            evidence.required and evidence.category == group
            for evidence in missing_evidence
        )
    )
    missing_recommended = tuple(
        group
        for group in CONTEXT_GROUPS
        if any(
            not evidence.required and evidence.category == group
            for evidence in missing_evidence
        )
    )
    protected_direct_evidence = _has_protected_direct_evidence(bundle)

    reasons = [
        (
            "required evidence is missing: " + ", ".join(missing_required)
            if missing_required
            else "all required evidence groups are present"
        )
    ]
    if expected.recommended:
        reasons.append(
            (
                "recommended evidence is missing: "
                + ", ".join(missing_recommended)
                if missing_recommended
                else "all recommended evidence groups are present"
            )
        )
    reasons.append(
        "protected original direct evidence is present"
        if protected_direct_evidence
        else "protected original direct evidence is absent"
    )

    if missing_required:
        level = "low"
    elif missing_recommended or not protected_direct_evidence:
        level = "medium"
    else:
        level = "high"
    return ReadinessConfidence(level=level, reasons=tuple(reasons))


def _has_protected_direct_evidence(bundle: QueryBundle) -> bool:
    for raw_result in bundle.results:
        try:
            value = raw_result.score_parts["evidence_priority"]
        except (AttributeError, KeyError, TypeError):
            continue
        if type(value) in (int, float) and value == 0:
            return True
    return False


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


def _validate_completion_state(
    pack: ContextPack,
    expected: _ExpectedGroups,
) -> None:
    for evidence in pack.missing_evidence:
        if (
            type(evidence.category) is not str
            or type(evidence.required) is not bool
            or type(evidence.reason) is not str
        ):
            raise ContextPackError(INVALID_REFERENCE_ERROR)

    if not pack.items:
        if (
            pack.status != "empty"
            or pack.missing_evidence != _EMPTY_MISSING_EVIDENCE
        ):
            raise ContextPackError(INVALID_REFERENCE_ERROR)
        return

    if any(
        evidence.category not in CONTEXT_GROUPS[:-1]
        for evidence in pack.missing_evidence
    ):
        raise ContextPackError(INVALID_REFERENCE_ERROR)

    categories = tuple(evidence.category for evidence in pack.missing_evidence)
    if len(categories) != len(set(categories)):
        raise ContextPackError(INVALID_REFERENCE_ERROR)

    required_categories = tuple(
        evidence.category
        for evidence in pack.missing_evidence
        if evidence.required
    )
    recommended_categories = tuple(
        evidence.category
        for evidence in pack.missing_evidence
        if not evidence.required
    )
    if (
        tuple(evidence.required for evidence in pack.missing_evidence)
        != (True,) * len(required_categories)
        + (False,) * len(recommended_categories)
        or required_categories
        != tuple(
            group for group in CONTEXT_GROUPS if group in required_categories
        )
        or recommended_categories
        != tuple(
            group for group in CONTEXT_GROUPS if group in recommended_categories
        )
    ):
        raise ContextPackError(INVALID_REFERENCE_ERROR)

    for evidence in pack.missing_evidence:
        prefix = "required" if evidence.required else "recommended"
        if (
            pack.groups[evidence.category]
            or evidence.reason
            != (
                f"{prefix} evidence for {evidence.category} is missing from "
                "the bounded result set"
            )
        ):
            raise ContextPackError(INVALID_REFERENCE_ERROR)

    expected_status = "partial" if required_categories else "ready"
    if pack.status != expected_status:
        raise ContextPackError(INVALID_REFERENCE_ERROR)

    expected_missing_evidence = _build_missing_evidence(expected, pack.groups)
    if pack.missing_evidence != expected_missing_evidence:
        raise ContextPackError(INVALID_REFERENCE_ERROR)


def _validate_context_pack(
    bundle: QueryBundle,
    pack: ContextPack,
    expected: _ExpectedGroups | None = None,
) -> None:
    if type(pack) is not ContextPack:
        raise ContextPackError(INVALID_REFERENCE_ERROR)
    if (
        type(pack.schema_version) is not int
        or pack.schema_version != CONTEXT_PACK_SCHEMA_VERSION
        or type(pack.status) is not str
        or type(pack.items) is not tuple
        or any(type(item) is not ContextPackItem for item in pack.items)
        or type(pack.groups) is not dict
        or type(pack.reading_order) is not tuple
        or type(pack.missing_evidence) is not tuple
        or any(
            type(evidence) is not MissingEvidence
            for evidence in pack.missing_evidence
        )
        or type(pack.next_queries) is not tuple
        or any(type(query) is not NextQuery for query in pack.next_queries)
        or type(pack.confidence) is not ReadinessConfidence
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

    for item in pack.items:
        resolve_context_item(bundle, item)
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

    if expected is None:
        expected = _derive_expected_groups(bundle, expected_groups)
    expected_reading_order = _build_reading_order(
        expected_groups,
        expected.explicit_required,
    )
    if pack.reading_order != expected_reading_order:
        raise ContextPackError(INVALID_REFERENCE_ERROR)

    _validate_completion_state(pack, expected)

    for query in pack.next_queries:
        if (
            type(query.query) is not str
            or type(query.purpose) is not str
            or query.purpose not in _NEXT_QUERY_PURPOSES
            or type(query.reason) is not str
        ):
            raise ContextPackError(INVALID_REFERENCE_ERROR)
    if pack.next_queries != _build_next_queries(bundle, pack.missing_evidence):
        raise ContextPackError(INVALID_REFERENCE_ERROR)

    confidence = pack.confidence
    if (
        type(confidence.level) is not str
        or confidence.level not in _CONFIDENCE_LEVELS
        or type(confidence.reasons) is not tuple
        or any(type(reason) is not str for reason in confidence.reasons)
        or confidence
        != _build_readiness_confidence(bundle, expected, pack.missing_evidence)
    ):
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


def _materialize_context_pack_payload(pack: ContextPack) -> dict[str, Any]:
    return {
        "schema_version": pack.schema_version,
        "status": pack.status,
        "items": _materialize_collection(
            pack.items,
            ContextPackItem,
            _materialize_item,
        ),
        "groups": _materialize_groups(pack.groups),
        "reading_order": _materialize_string_collection(pack.reading_order),
        "missing_evidence": _materialize_collection(
            pack.missing_evidence,
            MissingEvidence,
            _materialize_missing_evidence,
        ),
        "next_queries": _materialize_collection(
            pack.next_queries,
            NextQuery,
            _materialize_next_query,
        ),
        "confidence": _materialize_confidence(pack.confidence),
        "budget": _materialize_budget(pack.budget),
    }


def _materialize_collection(
    value: Any,
    item_type: type[Any],
    materialize_item: Any,
) -> Any:
    if type(value) not in (tuple, list):
        return value
    return [
        materialize_item(item) if type(item) is item_type else item
        for item in value
    ]


def _materialize_string_collection(value: Any) -> Any:
    if type(value) not in (tuple, list):
        return value
    return list(value)


def _materialize_groups(value: Any) -> Any:
    if type(value) is not dict:
        return value
    return {
        group: _materialize_string_collection(item_ids)
        for group, item_ids in value.items()
    }


def _materialize_item(item: ContextPackItem) -> dict[str, Any]:
    return {
        "id": item.id,
        "source": item.source,
        "source_index": item.source_index,
        "file_path": item.file_path,
        "start_line": item.start_line,
        "end_line": item.end_line,
        "group": item.group,
        "role": item.role,
        "classification_basis": item.classification_basis,
    }


def _materialize_missing_evidence(evidence: MissingEvidence) -> dict[str, Any]:
    return {
        "category": evidence.category,
        "required": evidence.required,
        "reason": evidence.reason,
    }


def _materialize_next_query(query: NextQuery) -> dict[str, Any]:
    return {
        "query": query.query,
        "purpose": query.purpose,
        "reason": query.reason,
    }


def _materialize_confidence(value: Any) -> Any:
    if type(value) is not ReadinessConfidence:
        return value
    return {
        "level": value.level,
        "reasons": _materialize_string_collection(value.reasons),
    }


def _materialize_budget(value: Any) -> Any:
    if type(value) is not ContextBudget:
        return value
    return {
        "max_results": value.max_results,
        "max_evidence_anchors": value.max_evidence_anchors,
        "max_items": value.max_items,
        "included_results": value.included_results,
        "included_evidence_anchors": value.included_evidence_anchors,
        "content_bytes": value.content_bytes,
        "context_before_lines": value.context_before_lines,
        "context_after_lines": value.context_after_lines,
        "full_file": value.full_file,
        "max_full_file_bytes": value.max_full_file_bytes,
    }


def _is_json_native(value: Any) -> bool:
    if value is None or type(value) in (bool, int, str):
        return True
    if type(value) is float:
        return isfinite(value)
    if type(value) is list:
        return all(_is_json_native(item) for item in value)
    if type(value) is dict:
        return all(
            type(key) is str and _is_json_native(item)
            for key, item in value.items()
        )
    return False
