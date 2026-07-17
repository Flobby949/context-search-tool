from __future__ import annotations

from dataclasses import fields, replace
from typing import Any

from context_search_tool.config import ToolConfig
from context_search_tool.context_pack import ContextPackError, ContextPackOptions
from context_search_tool.exploration.models import (
    FOLLOWUP_FINAL_TOP_K,
    MAX_FUSED_ANCHORS,
    MAX_FUSED_RESULTS,
    MAX_INITIAL_RESULTS,
)


_CONTEXT_FIELDS = (
    "max_items",
    "max_excerpts_per_item",
    "max_excerpt_bytes",
    "max_item_content_bytes",
    "max_total_content_bytes",
    "max_pack_bytes",
)
_PACK_INTEGER_FIELDS = tuple(field.name for field in fields(ContextPackOptions))
_MAX_FINAL_CANDIDATES = MAX_FUSED_RESULTS + MAX_FUSED_ANCHORS


def validate_explore_request_options(
    *,
    final_top_k: int | None,
    context_lines: int | None,
    full_file: bool,
    max_items: int | None,
    max_context_bytes: int | None,
) -> None:
    if final_top_k is not None:
        _validate_positive_int(final_top_k, "final_top_k", ValueError)
    _validate_context_lines(context_lines)
    if type(full_file) is not bool:
        _invalid("full_file must be a boolean")
    if max_items is not None and (type(max_items) is not int or max_items <= 0):
        _invalid("max_items must be a positive integer")
    if max_context_bytes is not None and (
        type(max_context_bytes) is not int or max_context_bytes < 4096
    ):
        _invalid("max_context_bytes must be an integer of at least 4096 bytes")


def resolve_explore_config(
    config: ToolConfig,
    *,
    final_top_k: int | None,
) -> tuple[ToolConfig, int | None, int]:
    if final_top_k is not None:
        _validate_positive_int(final_top_k, "final_top_k", ValueError)
    merged_limit = (
        config.retrieval.final_top_k if final_top_k is None else final_top_k
    )
    _validate_positive_int(
        merged_limit,
        "retrieval.final_top_k",
        ValueError,
    )
    effective_limit = min(merged_limit, MAX_INITIAL_RESULTS)
    return (
        replace(
            config,
            retrieval=replace(
                config.retrieval,
                final_top_k=effective_limit,
            ),
        ),
        final_top_k,
        effective_limit,
    )


def resolve_explore_pack_options(
    config: ToolConfig,
    *,
    context_lines: int | None,
    max_items: int | None = None,
    max_pack_bytes: int | None = None,
) -> ContextPackOptions:
    _validate_context_config(config)
    _validate_context_lines_or_config(config, context_lines)
    if max_items is not None and (type(max_items) is not int or max_items <= 0):
        _invalid("max_items must be a positive integer")
    if max_pack_bytes is not None and (
        type(max_pack_bytes) is not int or max_pack_bytes < 4096
    ):
        _invalid("max_context_bytes must be an integer of at least 4096 bytes")

    context = config.context
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
        before = config.retrieval.context_before_lines
        after = config.retrieval.context_after_lines
    else:
        before = after = context_lines
    return ContextPackOptions(
        max_items=min(
            context.max_items,
            requested_max_items,
            _MAX_FINAL_CANDIDATES,
        ),
        max_excerpts_per_item=context.max_excerpts_per_item,
        max_excerpt_bytes=effective_excerpt_bytes,
        max_item_content_bytes=effective_item_bytes,
        max_total_content_bytes=effective_total_bytes,
        max_pack_bytes=effective_pack_bytes,
        context_before_lines=before,
        context_after_lines=after,
    )


def validate_library_explore_options(
    config: ToolConfig,
    pack_options: ContextPackOptions,
    *,
    context_lines: int | None,
    full_file: bool,
) -> None:
    _validate_positive_int(
        config.retrieval.final_top_k,
        "retrieval.final_top_k",
        ValueError,
    )
    _validate_context_config(config)
    _validate_context_lines_or_config(config, context_lines)
    if type(full_file) is not bool:
        _invalid("full_file must be a boolean")
    if type(pack_options) is not ContextPackOptions:
        _invalid("pack_options must be ContextPackOptions")
    for field_name in _PACK_INTEGER_FIELDS:
        if type(getattr(pack_options, field_name)) is not int:
            _invalid(f"pack_options.{field_name} must be an integer")

    context = config.context
    if not 0 <= pack_options.max_items <= min(
        context.max_items,
        _MAX_FINAL_CANDIDATES,
    ):
        _invalid("pack_options.max_items is outside the explore capacity")
    if pack_options.max_excerpts_per_item != context.max_excerpts_per_item:
        _invalid("pack_options.max_excerpts_per_item changed configured policy")
    if not 0 < pack_options.max_excerpt_bytes <= context.max_excerpt_bytes:
        _invalid("pack_options.max_excerpt_bytes is outside configured policy")
    if not 0 < pack_options.max_item_content_bytes <= context.max_item_content_bytes:
        _invalid("pack_options.max_item_content_bytes is outside configured policy")
    if not 0 < pack_options.max_total_content_bytes <= context.max_total_content_bytes:
        _invalid("pack_options.max_total_content_bytes is outside configured policy")
    if pack_options.max_pack_bytes < 4096:
        _invalid("pack_options.max_pack_bytes must be at least 4096")
    if not (
        pack_options.max_excerpt_bytes
        <= pack_options.max_item_content_bytes
        <= pack_options.max_total_content_bytes
        < pack_options.max_pack_bytes
    ):
        _invalid("pack_options byte limits are inconsistent")

    expected_before = (
        config.retrieval.context_before_lines
        if context_lines is None
        else context_lines
    )
    expected_after = (
        config.retrieval.context_after_lines
        if context_lines is None
        else context_lines
    )
    if (
        pack_options.context_before_lines,
        pack_options.context_after_lines,
    ) != (expected_before, expected_after):
        _invalid("pack_options context lines do not match the request")


def followup_config(config: ToolConfig) -> ToolConfig:
    return replace(
        config,
        retrieval=replace(
            config.retrieval,
            final_top_k=FOLLOWUP_FINAL_TOP_K,
        ),
        query_planner=replace(config.query_planner, enabled=False),
    )


def _validate_context_config(config: ToolConfig) -> None:
    context = config.context
    for field_name in _CONTEXT_FIELDS:
        value = getattr(context, field_name)
        if type(value) is not int or value <= 0:
            _invalid(f"context.{field_name} must be a positive integer")
    if context.max_excerpt_bytes > context.max_item_content_bytes:
        _invalid("context.max_excerpt_bytes must not exceed max_item_content_bytes")
    if context.max_item_content_bytes > context.max_total_content_bytes:
        _invalid(
            "context.max_item_content_bytes must not exceed max_total_content_bytes"
        )
    if context.max_total_content_bytes >= context.max_pack_bytes:
        _invalid("context.max_total_content_bytes must be less than max_pack_bytes")


def _validate_context_lines_or_config(
    config: ToolConfig,
    context_lines: int | None,
) -> None:
    _validate_context_lines(context_lines)
    if context_lines is not None:
        return
    for field_name in ("context_before_lines", "context_after_lines"):
        value = getattr(config.retrieval, field_name)
        if type(value) is not int or value < 0:
            _invalid(f"retrieval.{field_name} must be a non-negative integer")


def _validate_context_lines(context_lines: int | None) -> None:
    if context_lines is not None and (
        type(context_lines) is not int or context_lines < 0
    ):
        _invalid("context_lines must be a non-negative integer")


def _validate_positive_int(
    value: Any,
    label: str,
    error_type: type[Exception],
) -> None:
    if type(value) is not int or value <= 0:
        raise error_type(f"{label} must be a positive integer")


def _invalid(message: str) -> None:
    raise ContextPackError("invalid_context_options", message)
