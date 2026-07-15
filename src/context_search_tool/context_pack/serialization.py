from __future__ import annotations

import json
from math import isfinite
from typing import Any, NoReturn

from context_search_tool.context_pack.models import (
    CONTEXT_GROUPS,
    CONTEXT_PACK_SCHEMA_VERSION,
    ContextBudget,
    ContextExcerpt,
    ContextItem,
    ContextPack,
    ContextPackError,
    EvidenceNeed,
    MissingEvidence,
    NextQuery,
    Omission,
    ReadinessConfidence,
)


_FAILURE_CODE = "context_failed"
_FAILURE_MESSAGE = "Context pack construction failed"
_MAX_SIZE_ITERATIONS = 8
_STATUSES = frozenset({"empty", "partial", "ready"})
_CLASSIFICATION_BASES = frozenset({"path", "content", "fallback"})
_SOURCE_KINDS = frozenset({"result", "evidence_anchor"})
_CONFIDENCE_LEVELS = frozenset({"none", "low", "medium", "high"})
_NEED_PROVENANCE = frozenset(
    {
        "explicit_query",
        "explicit_identifier",
        "planner_supported",
        "structural_recommendation",
    }
)
_TOP_LEVEL_KEYS = (
    "schema_version",
    "status",
    "items",
    "groups",
    "reading_order",
    "evidence_needs",
    "missing_evidence",
    "next_queries",
    "omissions",
    "confidence",
    "budget",
)
_ITEM_KEYS = (
    "id",
    "file_path",
    "group",
    "role",
    "classification_basis",
    "source_kind",
    "retrieval_rank",
    "relevance_score",
    "reasons",
    "matched_need_ids",
    "excerpts",
)
_EXCERPT_KEYS = (
    "start_line",
    "end_line",
    "content",
    "content_bytes",
    "truncated",
)
_NEED_KEYS = (
    "id",
    "category",
    "subject_terms",
    "required",
    "provenance",
    "matched_item_ids",
)
_MISSING_KEYS = ("need_id", "category", "required", "reason")
_NEXT_QUERY_KEYS = ("need_id", "query", "purpose")
_OMISSION_KEYS = ("file_path", "group", "reason", "matched_need_ids")
_CONFIDENCE_KEYS = ("level", "reasons")
_BUDGET_KEYS = (
    "max_items",
    "max_excerpts_per_item",
    "max_excerpt_bytes",
    "max_item_content_bytes",
    "max_total_content_bytes",
    "max_pack_bytes",
    "included_items",
    "included_excerpts",
    "content_bytes",
    "pack_bytes",
    "truncated_item_count",
    "omitted_item_count",
    "budget_exhausted",
)


def context_pack_payload(pack: ContextPack) -> dict[str, Any]:
    """Return a validated, JSON-native, self-sized context pack payload."""
    try:
        normalized = _normalize_payload(_materialize_pack(pack))
        payload, _ = _self_size_payload(normalized)
        return payload
    except ContextPackError:
        raise
    except Exception:
        _fail()


def canonical_context_pack_bytes(
    pack_or_payload: ContextPack | dict[str, Any],
) -> bytes:
    """Return deterministic compact UTF-8 JSON bytes for a v2 context pack."""
    try:
        if type(pack_or_payload) is ContextPack:
            raw_payload = _materialize_pack(pack_or_payload)
        elif type(pack_or_payload) is dict:
            raw_payload = pack_or_payload
        else:
            _fail()
        normalized = _normalize_payload(raw_payload)
        _, encoded = _self_size_payload(normalized)
        return encoded
    except ContextPackError:
        raise
    except Exception:
        _fail()


def _materialize_pack(pack: ContextPack) -> dict[str, Any]:
    if type(pack) is not ContextPack:
        _fail()
    if type(pack.items) is not tuple:
        _fail()
    if type(pack.groups) is not dict:
        _fail()
    _require_exact_keys(pack.groups, CONTEXT_GROUPS)
    if type(pack.reading_order) is not tuple:
        _fail()
    if type(pack.evidence_needs) is not tuple:
        _fail()
    if type(pack.missing_evidence) is not tuple:
        _fail()
    if type(pack.next_queries) is not tuple:
        _fail()
    if type(pack.omissions) is not tuple:
        _fail()

    return {
        "schema_version": pack.schema_version,
        "status": pack.status,
        "items": [_materialize_item(item) for item in pack.items],
        "groups": {
            group: _tuple_to_list(pack.groups[group])
            for group in CONTEXT_GROUPS
        },
        "reading_order": _tuple_to_list(pack.reading_order),
        "evidence_needs": [
            _materialize_need(need) for need in pack.evidence_needs
        ],
        "missing_evidence": [
            _materialize_missing(evidence)
            for evidence in pack.missing_evidence
        ],
        "next_queries": [
            _materialize_next_query(query) for query in pack.next_queries
        ],
        "omissions": [
            _materialize_omission(omission) for omission in pack.omissions
        ],
        "confidence": _materialize_confidence(pack.confidence),
        "budget": _materialize_budget(pack.budget),
    }


def _materialize_item(item: ContextItem) -> dict[str, Any]:
    if type(item) is not ContextItem or type(item.excerpts) is not tuple:
        _fail()
    return {
        "id": item.id,
        "file_path": item.file_path,
        "group": item.group,
        "role": item.role,
        "classification_basis": item.classification_basis,
        "source_kind": item.source_kind,
        "retrieval_rank": item.retrieval_rank,
        "relevance_score": item.relevance_score,
        "reasons": _tuple_to_list(item.reasons),
        "matched_need_ids": _tuple_to_list(item.matched_need_ids),
        "excerpts": [
            _materialize_excerpt(excerpt) for excerpt in item.excerpts
        ],
    }


def _materialize_excerpt(excerpt: ContextExcerpt) -> dict[str, Any]:
    if type(excerpt) is not ContextExcerpt:
        _fail()
    return {
        "start_line": excerpt.start_line,
        "end_line": excerpt.end_line,
        "content": excerpt.content,
        "content_bytes": excerpt.content_bytes,
        "truncated": excerpt.truncated,
    }


def _materialize_need(need: EvidenceNeed) -> dict[str, Any]:
    if type(need) is not EvidenceNeed:
        _fail()
    return {
        "id": need.id,
        "category": need.category,
        "subject_terms": _tuple_to_list(need.subject_terms),
        "required": need.required,
        "provenance": need.provenance,
        "matched_item_ids": _tuple_to_list(need.matched_item_ids),
    }


def _materialize_missing(evidence: MissingEvidence) -> dict[str, Any]:
    if type(evidence) is not MissingEvidence:
        _fail()
    return {
        "need_id": evidence.need_id,
        "category": evidence.category,
        "required": evidence.required,
        "reason": evidence.reason,
    }


def _materialize_next_query(query: NextQuery) -> dict[str, Any]:
    if type(query) is not NextQuery:
        _fail()
    return {
        "need_id": query.need_id,
        "query": query.query,
        "purpose": query.purpose,
    }


def _materialize_omission(omission: Omission) -> dict[str, Any]:
    if type(omission) is not Omission:
        _fail()
    return {
        "file_path": omission.file_path,
        "group": omission.group,
        "reason": omission.reason,
        "matched_need_ids": _tuple_to_list(omission.matched_need_ids),
    }


def _materialize_confidence(
    confidence: ReadinessConfidence,
) -> dict[str, Any]:
    if type(confidence) is not ReadinessConfidence:
        _fail()
    return {
        "level": confidence.level,
        "reasons": _tuple_to_list(confidence.reasons),
    }


def _materialize_budget(budget: ContextBudget) -> dict[str, Any]:
    if type(budget) is not ContextBudget:
        _fail()
    return {
        "max_items": budget.max_items,
        "max_excerpts_per_item": budget.max_excerpts_per_item,
        "max_excerpt_bytes": budget.max_excerpt_bytes,
        "max_item_content_bytes": budget.max_item_content_bytes,
        "max_total_content_bytes": budget.max_total_content_bytes,
        "max_pack_bytes": budget.max_pack_bytes,
        "included_items": budget.included_items,
        "included_excerpts": budget.included_excerpts,
        "content_bytes": budget.content_bytes,
        "pack_bytes": budget.pack_bytes,
        "truncated_item_count": budget.truncated_item_count,
        "omitted_item_count": budget.omitted_item_count,
        "budget_exhausted": budget.budget_exhausted,
    }


def _tuple_to_list(value: Any) -> list[Any]:
    if type(value) is not tuple:
        _fail()
    return [item for item in value]


def _normalize_payload(value: Any) -> dict[str, Any]:
    _require_exact_keys(value, _TOP_LEVEL_KEYS)
    schema_version = _strict_int(value["schema_version"])
    status = _closed_string(value["status"], _STATUSES)
    items = _normalize_list(value["items"], _normalize_item)
    groups = _normalize_groups(value["groups"])
    reading_order = _string_list(value["reading_order"])
    evidence_needs = _normalize_list(
        value["evidence_needs"],
        _normalize_need,
    )
    missing_evidence = _normalize_list(
        value["missing_evidence"],
        _normalize_missing,
    )
    next_queries = _normalize_list(
        value["next_queries"],
        _normalize_next_query,
    )
    omissions = _normalize_list(value["omissions"], _normalize_omission)
    confidence = _normalize_confidence(value["confidence"])
    budget = _normalize_budget(value["budget"])
    normalized = {
        "schema_version": schema_version,
        "status": status,
        "items": items,
        "groups": groups,
        "reading_order": reading_order,
        "evidence_needs": evidence_needs,
        "missing_evidence": missing_evidence,
        "next_queries": next_queries,
        "omissions": omissions,
        "confidence": confidence,
        "budget": budget,
    }
    _validate_contract(normalized)
    return normalized


def _normalize_item(value: Any) -> dict[str, Any]:
    _require_exact_keys(value, _ITEM_KEYS)
    source_kind = _closed_string(value["source_kind"], _SOURCE_KINDS)
    score = value["relevance_score"]
    if source_kind == "result":
        if type(score) not in (int, float) or not isfinite(score):
            _fail()
    elif score is not None:
        _fail()
    retrieval_rank = value["retrieval_rank"]
    if source_kind == "result":
        retrieval_rank = _nonnegative_int(retrieval_rank)
    elif retrieval_rank is not None:
        _fail()
    return {
        "id": _nonempty_string(value["id"]),
        "file_path": _nonempty_string(value["file_path"]),
        "group": _closed_string(value["group"], frozenset(CONTEXT_GROUPS)),
        "role": _nonempty_string(value["role"]),
        "classification_basis": _closed_string(
            value["classification_basis"],
            _CLASSIFICATION_BASES,
        ),
        "source_kind": source_kind,
        "retrieval_rank": retrieval_rank,
        "relevance_score": score,
        "reasons": _string_list(value["reasons"]),
        "matched_need_ids": _string_list(value["matched_need_ids"]),
        "excerpts": _normalize_list(value["excerpts"], _normalize_excerpt),
    }


def _normalize_excerpt(value: Any) -> dict[str, Any]:
    _require_exact_keys(value, _EXCERPT_KEYS)
    start_line = _positive_int(value["start_line"])
    end_line = _positive_int(value["end_line"])
    content = _strict_string(value["content"])
    content_bytes = _nonnegative_int(value["content_bytes"])
    truncated = _strict_bool(value["truncated"])
    if end_line < start_line or content_bytes != len(content.encode("utf-8")):
        _fail()
    return {
        "start_line": start_line,
        "end_line": end_line,
        "content": content,
        "content_bytes": content_bytes,
        "truncated": truncated,
    }


def _normalize_need(value: Any) -> dict[str, Any]:
    _require_exact_keys(value, _NEED_KEYS)
    return {
        "id": _nonempty_string(value["id"]),
        "category": _closed_string(
            value["category"],
            frozenset(CONTEXT_GROUPS),
        ),
        "subject_terms": _string_list(value["subject_terms"]),
        "required": _strict_bool(value["required"]),
        "provenance": _closed_string(value["provenance"], _NEED_PROVENANCE),
        "matched_item_ids": _string_list(value["matched_item_ids"]),
    }


def _normalize_missing(value: Any) -> dict[str, Any]:
    _require_exact_keys(value, _MISSING_KEYS)
    return {
        "need_id": _nonempty_string(value["need_id"]),
        "category": _closed_string(
            value["category"],
            frozenset(CONTEXT_GROUPS),
        ),
        "required": _strict_bool(value["required"]),
        "reason": _nonempty_string(value["reason"]),
    }


def _normalize_next_query(value: Any) -> dict[str, Any]:
    _require_exact_keys(value, _NEXT_QUERY_KEYS)
    return {
        "need_id": _nonempty_string(value["need_id"]),
        "query": _nonempty_string(value["query"]),
        "purpose": _nonempty_string(value["purpose"]),
    }


def _normalize_omission(value: Any) -> dict[str, Any]:
    _require_exact_keys(value, _OMISSION_KEYS)
    return {
        "file_path": _nonempty_string(value["file_path"]),
        "group": _closed_string(value["group"], frozenset(CONTEXT_GROUPS)),
        "reason": _nonempty_string(value["reason"]),
        "matched_need_ids": _string_list(value["matched_need_ids"]),
    }


def _normalize_confidence(value: Any) -> dict[str, Any]:
    _require_exact_keys(value, _CONFIDENCE_KEYS)
    return {
        "level": _closed_string(value["level"], _CONFIDENCE_LEVELS),
        "reasons": _string_list(value["reasons"]),
    }


def _normalize_budget(value: Any) -> dict[str, Any]:
    _require_exact_keys(value, _BUDGET_KEYS)
    return {
        "max_items": _nonnegative_int(value["max_items"]),
        "max_excerpts_per_item": _positive_int(
            value["max_excerpts_per_item"]
        ),
        "max_excerpt_bytes": _positive_int(value["max_excerpt_bytes"]),
        "max_item_content_bytes": _positive_int(
            value["max_item_content_bytes"]
        ),
        "max_total_content_bytes": _positive_int(
            value["max_total_content_bytes"]
        ),
        "max_pack_bytes": _positive_int(value["max_pack_bytes"]),
        "included_items": _nonnegative_int(value["included_items"]),
        "included_excerpts": _nonnegative_int(value["included_excerpts"]),
        "content_bytes": _nonnegative_int(value["content_bytes"]),
        "pack_bytes": _nonnegative_int(value["pack_bytes"]),
        "truncated_item_count": _nonnegative_int(
            value["truncated_item_count"]
        ),
        "omitted_item_count": _nonnegative_int(value["omitted_item_count"]),
        "budget_exhausted": _strict_bool(value["budget_exhausted"]),
    }


def _normalize_groups(value: Any) -> dict[str, list[str]]:
    _require_exact_keys(value, CONTEXT_GROUPS)
    return {group: _string_list(value[group]) for group in CONTEXT_GROUPS}


def _normalize_list(value: Any, normalize_item: Any) -> list[Any]:
    if type(value) is not list:
        _fail()
    return [normalize_item(item) for item in value]


def _string_list(value: Any) -> list[str]:
    if type(value) is not list:
        _fail()
    normalized: list[str] = []
    for item in value:
        normalized.append(_nonempty_string(item))
    return normalized


def _validate_contract(payload: dict[str, Any]) -> None:
    if payload["schema_version"] != CONTEXT_PACK_SCHEMA_VERSION:
        _fail()

    items = payload["items"]
    item_ids = [item["id"] for item in items]
    if len(item_ids) != len(set(item_ids)):
        _fail()
    item_id_set = set(item_ids)
    grouped_item_ids = [
        item_id
        for group in CONTEXT_GROUPS
        for item_id in payload["groups"][group]
    ]
    if (
        len(grouped_item_ids) != len(item_ids)
        or set(grouped_item_ids) != item_id_set
        or any(
            item["id"] not in payload["groups"][item["group"]]
            for item in items
        )
    ):
        _fail()
    if (
        len(payload["reading_order"]) != len(item_ids)
        or set(payload["reading_order"]) != item_id_set
    ):
        _fail()

    needs = payload["evidence_needs"]
    need_ids = [need["id"] for need in needs]
    if len(need_ids) != len(set(need_ids)):
        _fail()
    need_id_set = set(need_ids)
    for item in items:
        if not set(item["matched_need_ids"]).issubset(need_id_set):
            _fail()
    for need in needs:
        if not set(need["matched_item_ids"]).issubset(item_id_set):
            _fail()

    missing = payload["missing_evidence"]
    for evidence in missing:
        if evidence["need_id"] not in need_id_set:
            _fail()

    for query in payload["next_queries"]:
        if query["need_id"] not in need_id_set:
            _fail()
    for omission in payload["omissions"]:
        if not set(omission["matched_need_ids"]).issubset(need_id_set):
            _fail()

    budget = payload["budget"]
    if not (
        budget["max_excerpt_bytes"]
        <= budget["max_item_content_bytes"]
        <= budget["max_total_content_bytes"]
        < budget["max_pack_bytes"]
    ):
        _fail()

    included_excerpts = sum(len(item["excerpts"]) for item in items)
    content_bytes = sum(
        excerpt["content_bytes"]
        for item in items
        for excerpt in item["excerpts"]
    )
    truncated_item_count = sum(
        any(excerpt["truncated"] for excerpt in item["excerpts"])
        for item in items
    )
    if (
        budget["included_items"] != len(items)
        or budget["included_excerpts"] != included_excerpts
        or budget["content_bytes"] != content_bytes
        or budget["truncated_item_count"] != truncated_item_count
        or budget["omitted_item_count"] != len(payload["omissions"])
        or len(items) > budget["max_items"]
        or included_excerpts
        > len(items) * budget["max_excerpts_per_item"]
        or content_bytes > budget["max_total_content_bytes"]
    ):
        _fail()
    for item in items:
        if len(item["excerpts"]) > budget["max_excerpts_per_item"]:
            _fail()
        item_content_bytes = sum(
            excerpt["content_bytes"] for excerpt in item["excerpts"]
        )
        if item_content_bytes > budget["max_item_content_bytes"]:
            _fail()
        if any(
            excerpt["content_bytes"] > budget["max_excerpt_bytes"]
            for excerpt in item["excerpts"]
        ):
            _fail()


def _self_size_payload(
    payload: dict[str, Any],
) -> tuple[dict[str, Any], bytes]:
    candidate = payload["budget"]["pack_bytes"]
    for _ in range(_MAX_SIZE_ITERATIONS):
        payload["budget"]["pack_bytes"] = candidate
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        actual_size = len(encoded)
        if actual_size == candidate:
            if actual_size > payload["budget"]["max_pack_bytes"]:
                _fail()
            return payload, encoded
        candidate = actual_size
    _fail()


def _require_exact_keys(value: Any, expected: tuple[str, ...]) -> None:
    if type(value) is not dict or len(value) != len(expected):
        _fail()
    keys = tuple(value)
    if any(type(key) is not str for key in keys):
        _fail()
    if frozenset(keys) != frozenset(expected):
        _fail()


def _strict_string(value: Any) -> str:
    if type(value) is not str:
        _fail()
    return value


def _nonempty_string(value: Any) -> str:
    value = _strict_string(value)
    if not value:
        _fail()
    return value


def _closed_string(value: Any, allowed: frozenset[str]) -> str:
    value = _strict_string(value)
    if value not in allowed:
        _fail()
    return value


def _strict_int(value: Any) -> int:
    if type(value) is not int:
        _fail()
    return value


def _positive_int(value: Any) -> int:
    value = _strict_int(value)
    if value <= 0:
        _fail()
    return value


def _nonnegative_int(value: Any) -> int:
    value = _strict_int(value)
    if value < 0:
        _fail()
    return value


def _strict_bool(value: Any) -> bool:
    if type(value) is not bool:
        _fail()
    return value


def _fail() -> NoReturn:
    raise ContextPackError(_FAILURE_CODE, _FAILURE_MESSAGE)


__all__ = ("canonical_context_pack_bytes", "context_pack_payload")
