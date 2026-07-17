from __future__ import annotations

from dataclasses import replace

import pytest

from context_search_tool.config import DEFAULT_CONFIG
from context_search_tool.context_pack import (
    ContextPackError,
    ContextPackOptions,
    resolve_context_pack_options,
)
from context_search_tool.exploration.options import (
    followup_config,
    resolve_explore_config,
    resolve_explore_pack_options,
    validate_explore_request_options,
    validate_library_explore_options,
)


def _request(**changes: object) -> dict[str, object]:
    values: dict[str, object] = {
        "final_top_k": None,
        "context_lines": None,
        "full_file": False,
        "max_items": None,
        "max_context_bytes": None,
    }
    values.update(changes)
    return values


@pytest.mark.parametrize("value", [False, True, 0, -1, 1.5, "1"])
def test_request_final_top_k_rejects_bool_non_positive_and_non_int(value: object) -> None:
    with pytest.raises(ValueError, match="final_top_k"):
        validate_explore_request_options(**_request(final_top_k=value))


@pytest.mark.parametrize("value", [False, True, -1, 1.5, "1"])
def test_request_context_lines_has_context_option_error_ownership(value: object) -> None:
    with pytest.raises(ContextPackError) as raised:
        validate_explore_request_options(**_request(context_lines=value))
    assert (raised.value.code, raised.value.message) == (
        "invalid_context_options",
        "context_lines must be a non-negative integer",
    )


@pytest.mark.parametrize("value", [None, False, True])
def test_request_full_file_accepts_only_real_booleans(value: object) -> None:
    if type(value) is bool:
        validate_explore_request_options(**_request(full_file=value))
        return
    with pytest.raises(ContextPackError, match="full_file"):
        validate_explore_request_options(**_request(full_file=value))


@pytest.mark.parametrize("value", [False, True, 0, -1, 1.5, "1"])
def test_request_max_items_must_be_a_positive_non_bool_integer(value: object) -> None:
    with pytest.raises(ContextPackError, match="max_items"):
        validate_explore_request_options(**_request(max_items=value))


@pytest.mark.parametrize("value", [False, True, -1, 0, 4095, 4096.0, "4096"])
def test_request_max_context_bytes_has_exact_lower_bound(value: object) -> None:
    with pytest.raises(ContextPackError, match="max_context_bytes"):
        validate_explore_request_options(**_request(max_context_bytes=value))
    validate_explore_request_options(**_request(max_context_bytes=4096))


def test_request_none_and_boundary_values_are_valid() -> None:
    validate_explore_request_options(**_request())
    validate_explore_request_options(
        **_request(
            final_top_k=1,
            context_lines=0,
            full_file=True,
            max_items=1,
            max_context_bytes=4096,
        )
    )


@pytest.mark.parametrize("value", [False, True, 0, -1, 1.5, "12"])
def test_resolve_explore_config_rejects_invalid_persisted_limit(value: object) -> None:
    config = replace(
        DEFAULT_CONFIG,
        retrieval=replace(DEFAULT_CONFIG.retrieval, final_top_k=value),
    )
    with pytest.raises(ValueError, match="retrieval.final_top_k"):
        resolve_explore_config(config, final_top_k=None)


def test_resolve_explore_config_preserves_request_and_caps_without_mutation() -> None:
    config = replace(
        DEFAULT_CONFIG,
        retrieval=replace(DEFAULT_CONFIG.retrieval, final_top_k=7),
    )

    resolved, requested, effective = resolve_explore_config(config, final_top_k=40)

    assert requested == 40
    assert effective == 12
    assert resolved.retrieval.final_top_k == 12
    assert config.retrieval.final_top_k == 7
    inherited, requested, effective = resolve_explore_config(config, final_top_k=None)
    assert (requested, effective, inherited.retrieval.final_top_k) == (None, 7, 7)


def test_configured_context_lines_are_strict_only_without_request_override() -> None:
    config = replace(
        DEFAULT_CONFIG,
        retrieval=replace(DEFAULT_CONFIG.retrieval, context_before_lines=-1),
    )
    with pytest.raises(ContextPackError, match="context_before_lines"):
        resolve_explore_pack_options(config, context_lines=None)

    options = resolve_explore_pack_options(config, context_lines=2)
    assert (options.context_before_lines, options.context_after_lines) == (2, 2)


def test_explore_pack_capacity_uses_24_plus_8_not_initial_top_k() -> None:
    config = replace(
        DEFAULT_CONFIG,
        retrieval=replace(DEFAULT_CONFIG.retrieval, final_top_k=1),
        context=replace(DEFAULT_CONFIG.context, max_items=40),
    )

    existing = resolve_context_pack_options(
        config,
        context_lines=None,
        max_evidence_anchors=1,
    )
    explored = resolve_explore_pack_options(config, context_lines=None)

    assert existing.max_items == 2
    assert explored.max_items == 32


def test_explore_pack_resolver_applies_request_and_byte_ceilings() -> None:
    options = resolve_explore_pack_options(
        DEFAULT_CONFIG,
        context_lines=0,
        max_items=3,
        max_pack_bytes=4096,
    )
    assert options.max_items == 3
    assert options.max_pack_bytes == 4096
    assert options.max_total_content_bytes == 4095
    assert options.context_before_lines == options.context_after_lines == 0


def test_direct_library_zero_item_budget_is_valid_but_request_zero_is_not() -> None:
    request_options = resolve_explore_pack_options(DEFAULT_CONFIG, context_lines=None)
    direct_options = replace(request_options, max_items=0)

    validate_library_explore_options(
        DEFAULT_CONFIG,
        direct_options,
        context_lines=None,
        full_file=False,
    )
    with pytest.raises(ContextPackError, match="max_items"):
        resolve_explore_pack_options(
            DEFAULT_CONFIG,
            context_lines=None,
            max_items=0,
        )


@pytest.mark.parametrize(
    "options",
    [
        replace(
            resolve_explore_pack_options(DEFAULT_CONFIG, context_lines=None),
            max_items=True,
        ),
        replace(
            resolve_explore_pack_options(DEFAULT_CONFIG, context_lines=None),
            max_items=-1,
        ),
        replace(
            resolve_explore_pack_options(DEFAULT_CONFIG, context_lines=None),
            max_items=33,
        ),
        replace(
            resolve_explore_pack_options(DEFAULT_CONFIG, context_lines=None),
            max_excerpt_bytes=9000,
        ),
        replace(
            resolve_explore_pack_options(DEFAULT_CONFIG, context_lines=None),
            max_total_content_bytes=65536,
        ),
        replace(
            resolve_explore_pack_options(DEFAULT_CONFIG, context_lines=None),
            context_before_lines=False,
        ),
    ],
)
def test_direct_library_rejects_malformed_or_over_capacity_options(
    options: ContextPackOptions,
) -> None:
    with pytest.raises(ContextPackError) as raised:
        validate_library_explore_options(
            DEFAULT_CONFIG,
            options,
            context_lines=None,
            full_file=False,
        )
    assert raised.value.code == "invalid_context_options"


def test_direct_library_validation_repeats_raw_parameter_checks() -> None:
    options = resolve_explore_pack_options(DEFAULT_CONFIG, context_lines=0)
    with pytest.raises(ContextPackError, match="full_file"):
        validate_library_explore_options(
            DEFAULT_CONFIG,
            options,
            context_lines=0,
            full_file=1,
        )
    with pytest.raises(ContextPackError, match="context_lines"):
        validate_library_explore_options(
            DEFAULT_CONFIG,
            options,
            context_lines=True,
            full_file=False,
        )


def test_followup_config_is_fixed_and_does_not_mutate_initial_config() -> None:
    config = replace(
        DEFAULT_CONFIG,
        query_planner=replace(DEFAULT_CONFIG.query_planner, enabled=True),
        retrieval=replace(DEFAULT_CONFIG.retrieval, final_top_k=1),
    )

    followup = followup_config(config)

    assert followup.retrieval.final_top_k == 6
    assert followup.query_planner.enabled is False
    assert followup.embedding == config.embedding
    assert config.retrieval.final_top_k == 1
    assert config.query_planner.enabled is True
