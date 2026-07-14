from context_search_tool.config import (
    DEFAULT_CONFIG,
    IndexConfig,
    RetrievalConfig,
    ToolConfig,
)
from context_search_tool.context_pack import (
    ContextPackOptions,
    resolve_context_pack_options,
)


def test_resolve_context_pack_options_uses_effective_config_window() -> None:
    config = ToolConfig(
        index=IndexConfig(max_full_file_bytes=123_456),
        retrieval=RetrievalConfig(
            final_top_k=12,
            context_before_lines=8,
            context_after_lines=12,
        ),
    )

    options = resolve_context_pack_options(
        config,
        context_lines=None,
        full_file=False,
        max_evidence_anchors=4,
    )

    assert options == ContextPackOptions(
        max_results=12,
        max_evidence_anchors=4,
        context_before_lines=8,
        context_after_lines=12,
        full_file=False,
        max_full_file_bytes=123_456,
    )


def test_resolve_context_pack_options_clamps_negative_config_window() -> None:
    config = ToolConfig(
        retrieval=RetrievalConfig(
            context_before_lines=-3,
            context_after_lines=-7,
        ),
    )

    options = resolve_context_pack_options(
        config,
        context_lines=None,
        full_file=False,
        max_evidence_anchors=1,
    )

    assert options.context_before_lines == 0
    assert options.context_after_lines == 0


def test_resolve_context_pack_options_applies_symmetric_override() -> None:
    options = resolve_context_pack_options(
        DEFAULT_CONFIG,
        context_lines=0,
        full_file=True,
        max_evidence_anchors=1,
    )

    assert options.context_before_lines == 0
    assert options.context_after_lines == 0
    assert options.full_file is True


def test_resolve_context_pack_options_clamps_negative_symmetric_override() -> None:
    options = resolve_context_pack_options(
        DEFAULT_CONFIG,
        context_lines=-5,
        full_file=False,
        max_evidence_anchors=1,
    )

    assert options.context_before_lines == 0
    assert options.context_after_lines == 0
