"""Shared role classification and candidate normalization for context pack v2."""

from __future__ import annotations

from dataclasses import replace
from math import isfinite
from numbers import Real
from pathlib import Path
from typing import TYPE_CHECKING, Any

from context_search_tool.context_pack.models import CONTEXT_GROUPS, ContextCandidate
from context_search_tool.frontend_roles import classify_frontend_role
from context_search_tool.path_roles import classify_path_role

if TYPE_CHECKING:
    from context_search_tool.retrieval import QueryBundle


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
    "lockfile": "supporting",
    "generated_output": "supporting",
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
_ANCHOR_KIND_FALLBACKS = {
    "readme": ("configs_docs", "readme", "fallback"),
    "risks": ("configs_docs", "risks", "fallback"),
    "pom": ("configs_docs", "pom", "fallback"),
}
_MAX_REASONS = 4
_CONTEXT_ROLE_HINTS = {
    "mybatis_repository": ("implementations", "repository", "content"),
    "graph_repository": ("implementations", "repository", "content"),
    "graph_service_impl": ("implementations", "service_impl", "content"),
    "graph_service_interface": ("related_types", "service_interface", "content"),
    "graph_data_type": ("related_types", "data_type", "content"),
}


def normalize_candidates(bundle: QueryBundle) -> tuple[ContextCandidate, ...]:
    """Normalize bounded results and anchors without reading repository files."""
    normalized: list[ContextCandidate] = []
    positions: dict[str, int] = {}

    for result_index, raw_result in enumerate(bundle.results):
        candidate = _result_candidate(raw_result, result_index)
        existing_index = positions.get(candidate.key)
        if existing_index is None:
            positions[candidate.key] = len(normalized)
            normalized.append(candidate)
            continue
        normalized[existing_index] = _merge_candidate(
            normalized[existing_index],
            candidate,
        )

    for anchor_index, raw_anchor in enumerate(bundle.evidence_anchors):
        candidate = _anchor_candidate(raw_anchor, anchor_index)
        existing_index = positions.get(candidate.key)
        if existing_index is None:
            positions[candidate.key] = len(normalized)
            normalized.append(candidate)
            continue
        normalized[existing_index] = _merge_candidate(
            normalized[existing_index],
            candidate,
        )

    return tuple(normalized)


def _result_candidate(raw_result: Any, result_index: int) -> ContextCandidate:
    path = raw_result.file_path
    key = path.as_posix()
    score_parts = dict(raw_result.score_parts)
    role_hint = _CONTEXT_ROLE_HINTS.get(
        getattr(raw_result, "_context_role_hint", None)
    )
    if role_hint is not None:
        group, role, basis = role_hint
    elif score_parts.get("graph_implements_match", 0.0) > 0:
        group, role, basis = "implementations", "service_impl", "content"
    elif score_parts.get("graph_uses_type_match", 0.0) > 0:
        group, role, basis = "related_types", "data_type", "content"
    elif (
        score_parts.get("graph_calls_match", 0.0) > 0
        and path.suffix.casefold() == ".java"
        and path.stem.endswith("Mapper")
    ):
        group, role, basis = "implementations", "repository", "content"
    elif (
        score_parts.get("graph_calls_match", 0.0) > 0
        and path.suffix.casefold() == ".java"
        and path.stem.endswith("Service")
        and "interface " in raw_result.content
    ):
        group, role, basis = "related_types", "service_interface", "content"
    else:
        group, role, basis = _classify_candidate(path, raw_result.content)
    reasons = _bounded_reasons(raw_result.reasons)
    context_content = getattr(raw_result, "_context_content", None)
    if context_content is None:
        context_content = raw_result.content
    return ContextCandidate(
        key=key,
        file_path=key,
        start_line=raw_result.start_line,
        end_line=raw_result.end_line,
        content=context_content,
        group=group,
        role=role,
        classification_basis=basis,
        source_kind="result",
        retrieval_rank=result_index,
        source_order=result_index,
        relevance_score=_finite_score(raw_result.score),
        reasons=reasons,
        score_parts=score_parts,
        spans=tuple(getattr(raw_result, "spans", ())),
        trusted_provenance_text=_trusted_provenance_text(key, reasons),
        protected_direct=_is_protected_direct(score_parts),
    )


def _anchor_candidate(raw_anchor: Any, anchor_index: int) -> ContextCandidate:
    path = raw_anchor.file_path
    key = path.as_posix()
    group, role, basis = _classify_candidate(
        path,
        raw_anchor.content,
        anchor_kind=raw_anchor.anchor_kind,
        is_anchor=True,
    )
    reasons = _bounded_reasons(raw_anchor.reasons)
    context_content = getattr(raw_anchor, "_context_content", None)
    if context_content is None:
        context_content = raw_anchor.content
    return ContextCandidate(
        key=key,
        file_path=key,
        start_line=raw_anchor.start_line,
        end_line=raw_anchor.end_line,
        content=context_content,
        group=group,
        role=role,
        classification_basis=basis,
        source_kind="evidence_anchor",
        retrieval_rank=None,
        source_order=anchor_index,
        relevance_score=None,
        reasons=reasons,
        score_parts=dict(raw_anchor.score_parts),
        spans=(),
        trusted_provenance_text=_trusted_provenance_text(key, reasons),
        protected_direct=False,
    )


def _classify_candidate(
    path: Path,
    content: str,
    *,
    anchor_kind: str = "",
    is_anchor: bool = False,
) -> tuple[str, str, str]:
    path_role = classify_path_role(path, content)
    if path_role.name in _GENERIC_PATH_ROLES:
        return _PATH_GROUPS[path_role.name], path_role.name, path_role.basis

    frontend_role = classify_frontend_role(path.as_posix())
    if frontend_role.name != "other":
        return _FRONTEND_GROUPS[frontend_role.name], frontend_role.name, "path"

    if path_role.name in _PATH_GROUPS:
        return _PATH_GROUPS[path_role.name], path_role.name, path_role.basis

    if is_anchor and path_role.basis == "fallback":
        return _ANCHOR_KIND_FALLBACKS.get(
            anchor_kind,
            ("supporting", "evidence_anchor", "fallback"),
        )
    return "supporting", path_role.name, path_role.basis


def _merge_candidate(
    existing: ContextCandidate,
    incoming: ContextCandidate,
) -> ContextCandidate:
    reasons = _bounded_reasons((*existing.reasons, *incoming.reasons))
    changes: dict[str, object] = {
        "reasons": reasons,
        "trusted_provenance_text": _trusted_provenance_text(
            existing.file_path,
            reasons,
        ),
    }
    if (
        existing.classification_basis == "fallback"
        and incoming.classification_basis != "fallback"
        and (
            incoming.source_kind == "evidence_anchor"
            or (
                existing.source_kind == "result"
                and incoming.source_kind == "result"
                and incoming.end_line - incoming.start_line
                > existing.end_line - existing.start_line
            )
        )
    ):
        changes.update(
            group=incoming.group,
            role=incoming.role,
            classification_basis=incoming.classification_basis,
        )
    return replace(existing, **changes)


def _bounded_reasons(reasons: Any) -> tuple[str, ...]:
    bounded: list[str] = []
    for reason in reasons:
        if not isinstance(reason, str) or reason in bounded:
            continue
        bounded.append(reason)
        if len(bounded) == _MAX_REASONS:
            break
    return tuple(bounded)


def _trusted_provenance_text(path: str, reasons: tuple[str, ...]) -> str:
    return "\n".join((path, *reasons))


def _finite_score(score: Any) -> float | None:
    if isinstance(score, bool) or not isinstance(score, Real):
        return None
    numeric_score = float(score)
    return numeric_score if isfinite(numeric_score) else None


def _is_protected_direct(score_parts: dict[str, float]) -> bool:
    value = score_parts.get("evidence_priority")
    return isinstance(value, Real) and not isinstance(value, bool) and value == 0


__all__ = ("CONTEXT_GROUPS", "normalize_candidates")
