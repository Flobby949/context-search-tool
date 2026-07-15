from __future__ import annotations

from context_search_tool.config import ToolConfig
from context_search_tool.context_pack.models import (
    ContextPackError,
    ContextPackOptions,
)


_CONTEXT_FIELDS = (
    "max_items",
    "max_excerpts_per_item",
    "max_excerpt_bytes",
    "max_item_content_bytes",
    "max_total_content_bytes",
    "max_pack_bytes",
)


def resolve_context_pack_options(
    config: ToolConfig,
    *,
    context_lines: int | None,
    max_evidence_anchors: int,
    max_items: int | None = None,
    max_pack_bytes: int | None = None,
) -> ContextPackOptions:
    """Resolve validated request ceilings against configured context limits."""
    context = config.context
    for field_name in _CONTEXT_FIELDS:
        value = getattr(context, field_name)
        if type(value) is not int or value <= 0:
            _invalid(f"context.{field_name} must be a positive integer")

    if context.max_excerpt_bytes > context.max_item_content_bytes:
        _invalid(
            "context.max_excerpt_bytes must not exceed max_item_content_bytes"
        )
    if context.max_item_content_bytes > context.max_total_content_bytes:
        _invalid(
            "context.max_item_content_bytes must not exceed "
            "max_total_content_bytes"
        )
    if context.max_total_content_bytes >= context.max_pack_bytes:
        _invalid("context.max_total_content_bytes must be less than max_pack_bytes")

    if max_items is not None and (type(max_items) is not int or max_items <= 0):
        _invalid("max_items must be a positive integer")
    if max_pack_bytes is not None and (
        type(max_pack_bytes) is not int or max_pack_bytes < 4096
    ):
        _invalid("max_context_bytes must be an integer of at least 4096 bytes")
    if (
        type(max_evidence_anchors) is not int
        or max_evidence_anchors < 0
    ):
        _invalid("max_evidence_anchors must be a non-negative integer")

    effective_pack_bytes = (
        context.max_pack_bytes if max_pack_bytes is None else max_pack_bytes
    )
    effective_total_bytes = min(
        context.max_total_content_bytes,
        effective_pack_bytes - 1,
    )
    effective_item_bytes = min(
        context.max_item_content_bytes,
        effective_total_bytes,
    )
    effective_excerpt_bytes = min(
        context.max_excerpt_bytes,
        effective_item_bytes,
    )
    requested_max_items = context.max_items if max_items is None else max_items

    if context_lines is None:
        context_before_lines = max(0, config.retrieval.context_before_lines)
        context_after_lines = max(0, config.retrieval.context_after_lines)
    else:
        effective_context_lines = max(0, context_lines)
        context_before_lines = effective_context_lines
        context_after_lines = effective_context_lines

    return ContextPackOptions(
        max_items=min(
            context.max_items,
            requested_max_items,
            config.retrieval.final_top_k + max_evidence_anchors,
        ),
        max_excerpts_per_item=context.max_excerpts_per_item,
        max_excerpt_bytes=effective_excerpt_bytes,
        max_item_content_bytes=effective_item_bytes,
        max_total_content_bytes=effective_total_bytes,
        max_pack_bytes=effective_pack_bytes,
        context_before_lines=context_before_lines,
        context_after_lines=context_after_lines,
    )


def _invalid(message: str) -> None:
    raise ContextPackError("invalid_context_options", message)


__all__ = ("resolve_context_pack_options",)
