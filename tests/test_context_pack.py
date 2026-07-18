import copy
import json
from dataclasses import FrozenInstanceError, fields, replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from context_search_tool import context_pack
from context_search_tool.config import (
    RetrievalConfig,
    ToolConfig,
)
from context_search_tool.context_pack import builder as context_pack_v2_builder
from context_search_tool.context_pack import models as context_pack_v2_models
from context_search_tool.context_pack import roles as context_pack_v2_roles
from context_search_tool.context_pack import serialization as context_pack_v2_serialization


class _StringSubclass(str):
    pass


class _DictSubclass(dict):
    pass


def test_context_pack_v2_public_export_surface_is_exact() -> None:
    expected = (
        "CONTEXT_GROUPS",
        "CONTEXT_PACK_SCHEMA_VERSION",
        "ContextBudget",
        "ContextExcerpt",
        "ContextItem",
        "ContextPack",
        "ContextPackError",
        "ContextPackOptions",
        "EvidenceNeed",
        "MissingEvidence",
        "NextQuery",
        "Omission",
        "ReadinessConfidence",
        "build_context_pack",
        "canonical_context_pack_bytes",
        "context_pack_payload",
        "resolve_context_pack_options",
    )

    assert context_pack.__all__ == expected
    assert context_pack.CONTEXT_PACK_SCHEMA_VERSION == 2
    for legacy_name in (
        "ContextPackItem",
        "resolve_context_item",
        "INVALID_REFERENCE_ERROR",
        "UNEXPECTED_CONTEXT_ERROR",
    ):
        assert not hasattr(context_pack, legacy_name)


def _v2_modules():
    return (
        context_pack_v2_models,
        context_pack_v2_builder,
        context_pack_v2_serialization,
    )


def _v2_result(
    path: str,
    *,
    content: str = "source",
    score: float = 0.75,
    score_parts: dict[str, float] | None = None,
    reasons: list[str] | None = None,
    spans: tuple[object, ...] = (),
) -> SimpleNamespace:
    return SimpleNamespace(
        file_path=Path(path),
        start_line=3,
        end_line=8,
        content=content,
        score=score,
        score_parts=score_parts if score_parts is not None else {},
        reasons=reasons if reasons is not None else ["fixture result"],
        spans=spans,
    )


def _v2_anchor(
    path: str,
    kind: str,
    *,
    content: str = "anchor",
    score_parts: dict[str, float] | None = None,
    reasons: list[str] | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        file_path=Path(path),
        start_line=10,
        end_line=12,
        content=content,
        score=0.5,
        score_parts=score_parts if score_parts is not None else {},
        reasons=reasons if reasons is not None else ["fixture anchor"],
        anchor_kind=kind,
    )


def _v2_bundle(
    results: list[SimpleNamespace] | None = None,
    anchors: list[SimpleNamespace] | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        results=list(results or ()),
        evidence_anchors=list(anchors or ()),
    )


def test_v2_normalize_result_preserves_bounded_public_candidate_metadata() -> None:
    score_parts = _DictSubclass({"evidence_priority": 0, "semantic": 0.75})
    spans = (object(), object())
    raw_result = _v2_result(
        "src/main/java/com/example/Owner.java",
        content="@Entity\npublic class Owner {}",
        score_parts=score_parts,
        reasons=["direct", "direct", "semantic", "path", "signal", "ignored"],
        spans=spans,
    )

    candidates = context_pack_v2_roles.normalize_candidates(
        _v2_bundle([raw_result])
    )

    assert candidates == (
        context_pack_v2_models.ContextCandidate(
            key="src/main/java/com/example/Owner.java",
            file_path="src/main/java/com/example/Owner.java",
            start_line=3,
            end_line=8,
            content="@Entity\npublic class Owner {}",
            group="related_types",
            role="data_type",
            classification_basis="content",
            source_kind="result",
            retrieval_rank=0,
            source_order=0,
            relevance_score=0.75,
            reasons=("direct", "semantic", "path", "signal"),
            score_parts={"evidence_priority": 0, "semantic": 0.75},
            spans=spans,
            trusted_provenance_text=(
                "src/main/java/com/example/Owner.java\n"
                "direct\nsemantic\npath\nsignal"
            ),
            protected_direct=True,
        ),
    )
    assert candidates[0].score_parts is not score_parts


@pytest.mark.parametrize(
    ("path", "content", "expected"),
    [
        (
            "src/main/controller/AppController.java",
            "class AppController {}",
            ("entrypoints", "entrypoint", "path"),
        ),
        (
            "src/main/service/impl/AppServiceImpl.java",
            "class AppServiceImpl {}",
            ("implementations", "service_impl", "path"),
        ),
        (
            "src/main/service/AppService.java",
            "interface AppService {}",
            ("related_types", "service_interface", "content"),
        ),
        (
            "src/main/resources/application.yml",
            "spring.main.banner-mode=off",
            ("configs_docs", "runtime_config", "path"),
        ),
        (
            "tests/test_app.py",
            "def test_app(): pass",
            ("tests", "test", "path"),
        ),
        (
            "src/plain.py",
            "source",
            ("supporting", "source", "fallback"),
        ),
    ],
)
def test_v2_normalize_maps_shared_roles_to_closed_groups(
    path: str,
    content: str,
    expected: tuple[str, str, str],
) -> None:
    candidate = context_pack_v2_roles.normalize_candidates(
        _v2_bundle([_v2_result(path, content=content)])
    )[0]

    assert (
        candidate.group,
        candidate.role,
        candidate.classification_basis,
    ) == expected
    assert candidate.group in context_pack_v2_models.CONTEXT_GROUPS


def test_v2_normalize_preserves_shared_basis_for_unmapped_non_frontend_role() -> None:
    path = "backend/components/Widget.java"
    shared_role = context_pack_v2_roles.classify_path_role(Path(path))

    candidate = context_pack_v2_roles.normalize_candidates(
        _v2_bundle([_v2_result(path)])
    )[0]

    assert (shared_role.name, shared_role.basis) == ("component", "path")
    assert (
        candidate.group,
        candidate.role,
        candidate.classification_basis,
    ) == ("supporting", shared_role.name, shared_role.basis)


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("src/router/index.ts", ("entrypoints", "route_config", "path")),
        (
            "src/components/Widget.vue",
            ("implementations", "shared_component", "path"),
        ),
        ("src/App.tsx", ("entrypoints", "layout_component", "path")),
        ("src/utils/format.ts", ("implementations", "utility", "path")),
    ],
)
def test_v2_normalize_preserves_v1_frontend_precedence(
    path: str,
    expected: tuple[str, str, str],
) -> None:
    candidate = context_pack_v2_roles.normalize_candidates(
        _v2_bundle([_v2_result(path)])
    )[0]

    assert (
        candidate.group,
        candidate.role,
        candidate.classification_basis,
    ) == expected


@pytest.mark.parametrize(
    ("score_parts", "expected"),
    [
        ({"evidence_priority": False}, False),
        ({"evidence_priority": True}, False),
        ({"evidence_priority": 0}, True),
        ({"evidence_priority": 0.0}, True),
        ({"evidence_priority": 1}, False),
        ({}, False),
    ],
)
def test_v2_protected_direct_requires_non_bool_numeric_zero(
    score_parts: dict[str, float],
    expected: bool,
) -> None:
    candidate = context_pack_v2_roles.normalize_candidates(
        _v2_bundle([_v2_result("src/plain.py", score_parts=score_parts)])
    )[0]

    assert candidate.protected_direct is expected


def test_v2_anchor_uses_shared_classification_before_bounded_kind_fallback() -> None:
    candidates = context_pack_v2_roles.normalize_candidates(
        _v2_bundle(
            anchors=[
                _v2_anchor(
                    "src/main/resources/application.yml",
                    "readme",
                    score_parts={"anchor": 1.0},
                ),
                _v2_anchor("evidence/readme.bin", "readme"),
                _v2_anchor("evidence/risks.bin", "risks"),
                _v2_anchor("evidence/pom.bin", "pom"),
                _v2_anchor("evidence/other.bin", "other"),
                _v2_anchor(
                    "src/main/java/com/example/Owner.java",
                    "other",
                    content="@Entity\npublic class Owner {}",
                ),
            ]
        )
    )

    assert [
        (
            candidate.group,
            candidate.role,
            candidate.classification_basis,
            candidate.source_kind,
            candidate.retrieval_rank,
            candidate.source_order,
            candidate.relevance_score,
            candidate.spans,
            candidate.protected_direct,
        )
        for candidate in candidates
    ] == [
        ("configs_docs", "runtime_config", "path", "evidence_anchor", None, 0, None, (), False),
        ("configs_docs", "readme", "fallback", "evidence_anchor", None, 1, None, (), False),
        ("configs_docs", "risks", "fallback", "evidence_anchor", None, 2, None, (), False),
        ("configs_docs", "pom", "fallback", "evidence_anchor", None, 3, None, (), False),
        ("supporting", "evidence_anchor", "fallback", "evidence_anchor", None, 4, None, (), False),
        ("related_types", "data_type", "content", "evidence_anchor", None, 5, None, (), False),
    ]
    assert candidates[0].score_parts == {"anchor": 1.0}


def test_v2_normalize_deduplicates_paths_and_promotes_only_fallback_result_role() -> None:
    first_result = _v2_result(
        "src/main/java/com/example/Owner.java",
        content="public class Owner {}",
        reasons=["result reason", "shared"],
        spans=("result span",),
    )
    duplicate_result = _v2_result(
        "src/main/java/com/example/Owner.java",
        content="SECOND RESULT CONTENT",
        reasons=["shared", "duplicate result"],
    )
    promoting_anchor = _v2_anchor(
        "src/main/java/com/example/Owner.java",
        "other",
        content="@Entity\npublic class Owner {}",
        reasons=["anchor reason", "ignored fifth"],
    )
    service_result = _v2_result(
        "src/main/java/com/example/service/AppService.java",
        content="class AppService {}",
        reasons=["service result"],
    )
    non_promoting_anchor = _v2_anchor(
        "src/main/java/com/example/service/AppService.java",
        "readme",
        content="@Entity\npublic class AppService {}",
        reasons=["service anchor"],
    )

    candidates = context_pack_v2_roles.normalize_candidates(
        _v2_bundle(
            [first_result, duplicate_result, service_result],
            [promoting_anchor, non_promoting_anchor],
        )
    )

    assert len(candidates) == 2
    promoted, service = candidates
    assert (
        promoted.source_kind,
        promoted.content,
        promoted.retrieval_rank,
        promoted.relevance_score,
        promoted.spans,
        promoted.group,
        promoted.role,
        promoted.classification_basis,
        promoted.reasons,
    ) == (
        "result",
        "public class Owner {}",
        0,
        0.75,
        ("result span",),
        "related_types",
        "data_type",
        "content",
        ("result reason", "shared", "duplicate result", "anchor reason"),
    )
    assert promoted.trusted_provenance_text.endswith(
        "result reason\nshared\nduplicate result\nanchor reason"
    )
    assert (service.group, service.role, service.classification_basis) == (
        "implementations",
        "service",
        "path",
    )
    assert service.reasons == ("service result", "service anchor")


def test_v2_normalize_promotes_later_duplicate_result_classification() -> None:
    first = _v2_result(
        "src/main/java/com/example/Owner.java",
        content="return this.telephone;",
    )
    richer_duplicate = _v2_result(
        "src/main/java/com/example/Owner.java",
        content="@Entity\npublic class Owner {}",
    )
    richer_duplicate.start_line = 1
    richer_duplicate.end_line = 200

    [candidate] = context_pack_v2_roles.normalize_candidates(
        _v2_bundle([first, richer_duplicate])
    )

    assert (
        candidate.group,
        candidate.role,
        candidate.classification_basis,
    ) == ("related_types", "data_type", "content")
    assert candidate.content == "return this.telephone;"
    assert candidate.retrieval_rank == 0


def test_v2_duplicate_results_preserve_first_result_classification() -> None:
    candidates = context_pack_v2_roles.normalize_candidates(
        _v2_bundle(
            [
                _v2_result(
                    "src/main/java/com/example/Owner.java",
                    content="public class Owner {}",
                ),
                _v2_result(
                    "src/main/java/com/example/Owner.java",
                    content="@Entity\npublic class Owner {}",
                ),
            ]
        )
    )

    assert len(candidates) == 1
    assert (
        candidates[0].group,
        candidates[0].role,
        candidates[0].classification_basis,
    ) == ("supporting", "source", "fallback")


def test_v2_normalize_orders_results_then_unique_anchors_with_case_sensitive_keys() -> None:
    candidates = context_pack_v2_roles.normalize_candidates(
        _v2_bundle(
            [
                _v2_result("src/File.py"),
                _v2_result("src/file.py"),
            ],
            [
                _v2_anchor("src/File.py", "other"),
                _v2_anchor("README.md", "readme"),
            ],
        )
    )

    assert [candidate.key for candidate in candidates] == [
        "src/File.py",
        "src/file.py",
        "README.md",
    ]
    assert [candidate.file_path for candidate in candidates] == [
        "src/File.py",
        "src/file.py",
        "README.md",
    ]
    assert [candidate.source_order for candidate in candidates] == [0, 1, 1]
    assert [candidate.retrieval_rank for candidate in candidates] == [0, 1, None]


def test_v2_normalize_candidates_performs_no_path_io(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_io(*args: object, **kwargs: object) -> None:
        pytest.fail("candidate normalization must not perform path I/O")

    monkeypatch.setattr(Path, "open", fail_io)
    monkeypatch.setattr(Path, "read_text", fail_io)
    bundle = _v2_bundle(
        [_v2_result("src/plain.py")],
        [_v2_anchor("README.md", "readme")],
    )

    candidates = context_pack_v2_roles.normalize_candidates(bundle)

    assert len(candidates) == 2


def _v2_pack(content: str = "核心实现\n"):
    models, _, _ = _v2_modules()
    content_bytes = len(content.encode("utf-8"))
    excerpt = models.ContextExcerpt(
        start_line=10,
        end_line=11,
        content=content,
        content_bytes=content_bytes,
        truncated=False,
    )
    item = models.ContextItem(
        id="item:0",
        file_path="src/核心.py",
        group="implementations",
        role="implementation",
        classification_basis="content",
        source_kind="result",
        retrieval_rank=0,
        relevance_score=0.75,
        reasons=("direct Unicode match ✓",),
        matched_need_ids=("need:implementation",),
        excerpts=(excerpt,),
    )
    evidence_needs = (
        models.EvidenceNeed(
            id="need:implementation",
            category="implementations",
            subject_terms=("核心",),
            required=True,
            provenance="explicit_query",
            matched_item_ids=("item:0",),
        ),
        models.EvidenceNeed(
            id="need:tests",
            category="tests",
            subject_terms=("核心",),
            required=True,
            provenance="explicit_query",
            matched_item_ids=(),
        ),
    )
    groups = {
        group: (("item:0",) if group == "implementations" else ())
        for group in models.CONTEXT_GROUPS
    }
    return models.ContextPack(
        schema_version=models.CONTEXT_PACK_SCHEMA_VERSION,
        status="partial",
        items=(item,),
        groups=groups,
        reading_order=("item:0",),
        evidence_needs=evidence_needs,
        missing_evidence=(
            models.MissingEvidence(
                need_id="need:tests",
                category="tests",
                required=True,
                reason=(
                    "required 核心 test evidence is missing from the bounded context"
                ),
            ),
        ),
        next_queries=(
            models.NextQuery(
                need_id="need:tests",
                query="核心 test",
                purpose="find missing required test evidence",
            ),
        ),
        omissions=(
            models.Omission(
                file_path="tests/legacy_test.py",
                group="tests",
                reason=(
                    "lower priority than selected evidence under the context budget"
                ),
                matched_need_ids=("need:tests",),
            ),
        ),
        confidence=models.ReadinessConfidence(
            level="low",
            reasons=("required evidence is missing",),
        ),
        budget=models.ContextBudget(
            max_items=12,
            max_excerpts_per_item=2,
            max_excerpt_bytes=max(4096, content_bytes),
            max_item_content_bytes=max(8192, content_bytes),
            max_total_content_bytes=max(49_152, content_bytes),
            max_pack_bytes=65_536,
            included_items=1,
            included_excerpts=1,
            content_bytes=content_bytes,
            pack_bytes=0,
            truncated_item_count=0,
            omitted_item_count=1,
            budget_exhausted=True,
        ),
    )


def _v2_ready_pack():
    models, _, _ = _v2_modules()
    pack = _v2_pack()
    return replace(
        pack,
        status="ready",
        evidence_needs=(pack.evidence_needs[0],),
        missing_evidence=(),
        next_queries=(),
        omissions=(),
        confidence=models.ReadinessConfidence(
            level="high",
            reasons=(
                "all required evidence is selected",
                "protected original-direct evidence is present",
            ),
        ),
        budget=replace(
            pack.budget,
            omitted_item_count=0,
            budget_exhausted=False,
        ),
    )


def _v2_two_item_pack():
    pack = _v2_pack()
    support_content = "support\n"
    support_excerpt = replace(
        pack.items[0].excerpts[0],
        content=support_content,
        content_bytes=len(support_content.encode("utf-8")),
    )
    support = replace(
        pack.items[0],
        id="item:1",
        file_path="src/support.py",
        reasons=("support",),
        matched_need_ids=(),
        excerpts=(support_excerpt,),
    )
    return replace(
        pack,
        items=(pack.items[0], support),
        groups={
            group: (("item:0", "item:1") if group == "implementations" else ())
            for group in pack.groups
        },
        reading_order=("item:0", "item:1"),
        budget=replace(
            pack.budget,
            included_items=2,
            included_excerpts=2,
            content_bytes=(
                pack.budget.content_bytes + support_excerpt.content_bytes
            ),
        ),
    )


def test_v2_schema_constants_error_and_frozen_record_fields_are_exact() -> None:
    models, _, _ = _v2_modules()
    expected_fields = {
        "ContextExcerpt": (
            "start_line",
            "end_line",
            "content",
            "content_bytes",
            "truncated",
        ),
        "ContextItem": (
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
        ),
        "EvidenceNeed": (
            "id",
            "category",
            "subject_terms",
            "required",
            "provenance",
            "matched_item_ids",
        ),
        "MissingEvidence": ("need_id", "category", "required", "reason"),
        "NextQuery": ("need_id", "query", "purpose"),
        "Omission": ("file_path", "group", "reason", "matched_need_ids"),
        "ReadinessConfidence": ("level", "reasons"),
        "ContextBudget": (
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
        ),
        "ContextPack": (
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
        ),
        "ContextCandidate": (
            "key",
            "file_path",
            "start_line",
            "end_line",
            "content",
            "group",
            "role",
            "classification_basis",
            "source_kind",
            "retrieval_rank",
            "source_order",
            "relevance_score",
            "reasons",
            "score_parts",
            "spans",
            "trusted_provenance_text",
            "protected_direct",
        ),
        "ExcerptWindow": (
            "start_line",
            "end_line",
            "required_need_ids",
            "recommended_need_ids",
            "score",
            "protected_direct",
        ),
        "ContextPackOptions": (
            "max_items",
            "max_excerpts_per_item",
            "max_excerpt_bytes",
            "max_item_content_bytes",
            "max_total_content_bytes",
            "max_pack_bytes",
            "context_before_lines",
            "context_after_lines",
        ),
    }

    assert models.CONTEXT_PACK_SCHEMA_VERSION == 2
    assert models.CONTEXT_GROUPS == (
        "entrypoints",
        "implementations",
        "related_types",
        "tests",
        "configs_docs",
        "supporting",
    )
    for name, expected in expected_fields.items():
        assert tuple(field.name for field in fields(getattr(models, name))) == expected

    pack = _v2_pack()
    with pytest.raises(FrozenInstanceError):
        pack.status = "ready"

    error = models.ContextPackError("invalid_context_options", "fixed message")
    assert error.code == "invalid_context_options"
    assert error.message == "fixed message"
    assert str(error) == "fixed message"
    assert models.ContextPackError is context_pack.ContextPackError
    assert context_pack.CONTEXT_PACK_SCHEMA_VERSION == 2


def test_v2_candidate_key_and_retrieval_rank_annotations_are_exact() -> None:
    models, _, _ = _v2_modules()

    assert models.ContextItem.__annotations__["retrieval_rank"] == "int | None"
    assert models.ContextCandidate.__annotations__["key"] == "str"
    assert models.ContextCandidate.__annotations__["retrieval_rank"] == "int | None"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        (field, value)
        for field in (
            "max_items",
            "max_excerpts_per_item",
            "max_excerpt_bytes",
            "max_item_content_bytes",
            "max_total_content_bytes",
            "max_pack_bytes",
        )
        for value in (True, 1.0, 0, -1)
    ],
)
def test_v2_resolver_rejects_invalid_configured_context_values(
    field: str,
    value: object,
) -> None:
    from context_search_tool import config as config_module

    models, builder, _ = _v2_modules()
    context = replace(config_module.ContextConfig(), **{field: value})

    with pytest.raises(models.ContextPackError) as exc_info:
        builder.resolve_context_pack_options(
            ToolConfig(context=context),
            context_lines=None,
            max_evidence_anchors=4,
        )

    assert exc_info.value.code == "invalid_context_options"
    assert exc_info.value.message == f"context.{field} must be a positive integer"
    assert str(exc_info.value) == exc_info.value.message


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        (
            {"max_excerpt_bytes": 8193},
            "context.max_excerpt_bytes must not exceed max_item_content_bytes",
        ),
        (
            {"max_item_content_bytes": 49_153},
            "context.max_item_content_bytes must not exceed max_total_content_bytes",
        ),
        (
            {"max_total_content_bytes": 65_536},
            "context.max_total_content_bytes must be less than max_pack_bytes",
        ),
    ],
)
def test_v2_resolver_rejects_invalid_configured_context_order(
    changes: dict[str, int],
    message: str,
) -> None:
    from context_search_tool import config as config_module

    models, builder, _ = _v2_modules()
    context = replace(config_module.ContextConfig(), **changes)

    with pytest.raises(models.ContextPackError) as exc_info:
        builder.resolve_context_pack_options(
            ToolConfig(context=context),
            context_lines=None,
            max_evidence_anchors=4,
        )

    assert (exc_info.value.code, exc_info.value.message) == (
        "invalid_context_options",
        message,
    )


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"max_items": True}, "max_items must be a positive integer"),
        ({"max_items": 1.0}, "max_items must be a positive integer"),
        ({"max_items": 0}, "max_items must be a positive integer"),
        ({"max_items": -1}, "max_items must be a positive integer"),
        (
            {"max_pack_bytes": True},
            "max_context_bytes must be an integer of at least 4096 bytes",
        ),
        (
            {"max_pack_bytes": 4096.0},
            "max_context_bytes must be an integer of at least 4096 bytes",
        ),
        (
            {"max_pack_bytes": 4095},
            "max_context_bytes must be an integer of at least 4096 bytes",
        ),
        (
            {"max_evidence_anchors": True},
            "max_evidence_anchors must be a non-negative integer",
        ),
        (
            {"max_evidence_anchors": 1.0},
            "max_evidence_anchors must be a non-negative integer",
        ),
        (
            {"max_evidence_anchors": -1},
            "max_evidence_anchors must be a non-negative integer",
        ),
    ],
)
def test_v2_resolver_rejects_invalid_request_and_internal_values(
    kwargs: dict[str, object],
    message: str,
) -> None:
    models, builder, _ = _v2_modules()
    call_kwargs = {
        "context_lines": None,
        "max_evidence_anchors": 4,
        **kwargs,
    }

    with pytest.raises(models.ContextPackError) as exc_info:
        builder.resolve_context_pack_options(ToolConfig(), **call_kwargs)

    assert (exc_info.value.code, exc_info.value.message) == (
        "invalid_context_options",
        message,
    )


def test_v2_resolver_applies_request_ceiling_and_cascading_content_caps() -> None:
    models, builder, _ = _v2_modules()

    resolved = builder.resolve_context_pack_options(
        ToolConfig(),
        context_lines=None,
        max_evidence_anchors=4,
        max_items=20,
        max_pack_bytes=4096,
    )

    assert resolved == models.ContextPackOptions(
        max_items=12,
        max_excerpts_per_item=2,
        max_excerpt_bytes=4095,
        max_item_content_bytes=4095,
        max_total_content_bytes=4095,
        max_pack_bytes=4096,
        context_before_lines=8,
        context_after_lines=12,
    )


def test_v2_resolver_caps_items_by_raw_candidate_count_and_clamps_window() -> None:
    from context_search_tool import config as config_module

    models, builder, _ = _v2_modules()
    config = ToolConfig(
        retrieval=RetrievalConfig(
            final_top_k=5,
            context_before_lines=-3,
            context_after_lines=-7,
        ),
        context=replace(config_module.ContextConfig(), max_items=50),
    )

    configured_window = builder.resolve_context_pack_options(
        config,
        context_lines=None,
        max_evidence_anchors=2,
        max_items=20,
    )
    request_window = builder.resolve_context_pack_options(
        config,
        context_lines=-9,
        max_evidence_anchors=2,
        max_items=20,
    )

    assert configured_window.max_items == 7
    assert (
        configured_window.context_before_lines,
        configured_window.context_after_lines,
    ) == (0, 0)
    assert (
        request_window.context_before_lines,
        request_window.context_after_lines,
    ) == (0, 0)
    assert isinstance(configured_window, models.ContextPackOptions)


def test_v2_resolver_clamps_negative_raw_candidate_cap_to_zero() -> None:
    _, builder, _ = _v2_modules()

    resolved = builder.resolve_context_pack_options(
        ToolConfig(retrieval=RetrievalConfig(final_top_k=-2)),
        context_lines=None,
        max_evidence_anchors=1,
    )

    assert resolved.max_items == 0


def test_v2_payload_has_exact_top_level_and_nested_keys() -> None:
    models, _, serialization = _v2_modules()

    payload = serialization.context_pack_payload(_v2_pack())

    assert tuple(payload) == (
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
    assert tuple(payload["items"][0]) == (
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
    assert tuple(payload["items"][0]["excerpts"][0]) == (
        "start_line",
        "end_line",
        "content",
        "content_bytes",
        "truncated",
    )
    assert tuple(payload["groups"]) == models.CONTEXT_GROUPS
    assert tuple(payload["evidence_needs"][0]) == (
        "id",
        "category",
        "subject_terms",
        "required",
        "provenance",
        "matched_item_ids",
    )
    assert tuple(payload["missing_evidence"][0]) == (
        "need_id",
        "category",
        "required",
        "reason",
    )
    assert tuple(payload["next_queries"][0]) == ("need_id", "query", "purpose")
    assert tuple(payload["omissions"][0]) == (
        "file_path",
        "group",
        "reason",
        "matched_need_ids",
    )
    assert tuple(payload["confidence"]) == ("level", "reasons")
    assert tuple(payload["budget"]) == (
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
    assert all(type(item) is dict for item in payload["items"])
    assert all(type(item_ids) is list for item_ids in payload["groups"].values())
    assert payload["schema_version"] == 2


def test_v2_serialization_accepts_evidence_anchor_without_retrieval_rank() -> None:
    _, _, serialization = _v2_modules()
    pack = _v2_pack()
    anchor_item = replace(
        pack.items[0],
        source_kind="evidence_anchor",
        retrieval_rank=None,
        relevance_score=None,
    )

    payload = serialization.context_pack_payload(
        replace(pack, items=(anchor_item,))
    )

    assert payload["items"][0]["source_kind"] == "evidence_anchor"
    assert payload["items"][0]["retrieval_rank"] is None
    assert payload["items"][0]["relevance_score"] is None


@pytest.mark.parametrize(
    ("source_kind", "retrieval_rank", "relevance_score"),
    [
        pytest.param("result", 0, None, id="result-without-score"),
        pytest.param(
            "evidence_anchor",
            None,
            0.75,
            id="evidence-anchor-with-score",
        ),
    ],
)
def test_v2_serialization_rejects_source_kind_score_mismatches(
    source_kind: str,
    retrieval_rank: int | None,
    relevance_score: float | None,
) -> None:
    models, _, serialization = _v2_modules()
    pack = _v2_pack()
    malformed_item = replace(
        pack.items[0],
        source_kind=source_kind,
        retrieval_rank=retrieval_rank,
        relevance_score=relevance_score,
    )

    with pytest.raises(models.ContextPackError) as exc_info:
        serialization.context_pack_payload(
            replace(pack, items=(malformed_item,))
        )

    assert (exc_info.value.code, exc_info.value.message) == (
        "context_failed",
        "Context pack construction failed",
    )


def test_v2_canonical_serialization_is_unicode_native_deterministic_and_self_sized(
) -> None:
    _, _, serialization = _v2_modules()
    pack = _v2_pack()

    payload = serialization.context_pack_payload(pack)
    first = serialization.canonical_context_pack_bytes(pack)
    second = serialization.canonical_context_pack_bytes(pack)
    canonical_payload = json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")

    assert first == second == canonical_payload
    assert "核心".encode("utf-8") in first
    assert payload["budget"]["pack_bytes"] == len(first)
    assert json.loads(first)["budget"]["pack_bytes"] == len(first)
    assert pack.budget.pack_bytes == 0


def test_v2_canonical_serialization_self_sizes_across_digit_width_boundary() -> None:
    _, _, serialization = _v2_modules()
    target_size = 10_000
    padding = target_size - len(serialization.canonical_context_pack_bytes(_v2_pack()))
    encoded = b""

    for _ in range(8):
        encoded = serialization.canonical_context_pack_bytes(_v2_pack("x" * padding))
        if target_size <= len(encoded) < target_size + 10:
            break
        padding += target_size - len(encoded)

    embedded_size = json.loads(encoded)["budget"]["pack_bytes"]
    assert target_size <= len(encoded) < target_size + 10
    assert embedded_size == len(encoded)
    assert len(str(embedded_size)) == 5


def test_v2_canonical_serialization_accepts_payload_without_mutating_it() -> None:
    _, _, serialization = _v2_modules()
    payload = serialization.context_pack_payload(_v2_pack())
    payload["budget"]["pack_bytes"] = 0
    original = copy.deepcopy(payload)

    encoded = serialization.canonical_context_pack_bytes(payload)

    assert payload == original
    assert json.loads(encoded)["budget"]["pack_bytes"] == len(encoded)


def test_v2_serialization_accepts_configured_pack_ceiling_below_request_floor() -> None:
    from context_search_tool import config as config_module

    _, builder, serialization = _v2_modules()
    options = builder.resolve_context_pack_options(
        ToolConfig(
            context=config_module.ContextConfig(
                max_excerpt_bytes=512,
                max_item_content_bytes=1024,
                max_total_content_bytes=2048,
                max_pack_bytes=3000,
            )
        ),
        context_lines=None,
        max_evidence_anchors=4,
    )
    pack = _v2_pack()
    budget = replace(
        pack.budget,
        max_items=options.max_items,
        max_excerpts_per_item=options.max_excerpts_per_item,
        max_excerpt_bytes=options.max_excerpt_bytes,
        max_item_content_bytes=options.max_item_content_bytes,
        max_total_content_bytes=options.max_total_content_bytes,
        max_pack_bytes=options.max_pack_bytes,
    )

    payload = serialization.context_pack_payload(replace(pack, budget=budget))

    assert payload["budget"]["pack_bytes"] < 3000


def test_v2_serialization_accepts_zero_effective_item_capacity() -> None:
    models, builder, serialization = _v2_modules()
    options = builder.resolve_context_pack_options(
        ToolConfig(retrieval=RetrievalConfig(final_top_k=0)),
        context_lines=None,
        max_evidence_anchors=0,
    )
    pack = models.ContextPack(
        schema_version=models.CONTEXT_PACK_SCHEMA_VERSION,
        status="empty",
        items=(),
        groups={group: () for group in models.CONTEXT_GROUPS},
        reading_order=(),
        evidence_needs=(),
        missing_evidence=(),
        next_queries=(),
        omissions=(),
        confidence=models.ReadinessConfidence(
            level="none",
            reasons=("no usable retrieval evidence",),
        ),
        budget=models.ContextBudget(
            max_items=options.max_items,
            max_excerpts_per_item=options.max_excerpts_per_item,
            max_excerpt_bytes=options.max_excerpt_bytes,
            max_item_content_bytes=options.max_item_content_bytes,
            max_total_content_bytes=options.max_total_content_bytes,
            max_pack_bytes=options.max_pack_bytes,
            included_items=0,
            included_excerpts=0,
            content_bytes=0,
            pack_bytes=0,
            truncated_item_count=0,
            omitted_item_count=0,
            budget_exhausted=False,
        ),
    )

    payload = serialization.context_pack_payload(pack)

    assert options.max_items == 0
    assert payload["budget"]["max_items"] == 0


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(
            lambda pack: replace(pack, status="ready"),
            id="status-not-derived-yet",
        ),
        pytest.param(
            lambda pack: replace(
                pack,
                status="ready",
                missing_evidence=(),
                next_queries=(),
            ),
            id="missing-records-not-exhaustive-yet",
        ),
        pytest.param(
            lambda pack: replace(
                pack,
                items=(replace(pack.items[0], matched_need_ids=()),),
            ),
            id="need-item-links-not-bidirectional-yet",
        ),
        pytest.param(
            lambda pack: replace(
                pack,
                confidence=replace(
                    pack.confidence,
                    reasons=("recommended tests are missing",),
                ),
            ),
            id="confidence-reasons-not-derived",
        ),
    ],
)
def test_v2_serialization_rejects_inconsistent_derived_semantic_states(mutate) -> None:
    models, _, serialization = _v2_modules()

    with pytest.raises(models.ContextPackError) as exc_info:
        serialization.context_pack_payload(mutate(_v2_pack()))

    assert (exc_info.value.code, exc_info.value.message) == (
        "context_failed",
        "Context pack construction failed",
    )


@pytest.mark.parametrize(
    "fault",
    [
        "category_mismatch",
        "linked_item_without_excerpt",
        "subject_not_visible",
        "subjects_split_across_excerpts",
    ],
)
def test_v2_serialization_revalidates_every_semantic_need_item_link(
    fault: str,
) -> None:
    models, _, serialization = _v2_modules()
    pack = _v2_pack()
    item = pack.items[0]
    need = pack.evidence_needs[0]
    budget = pack.budget

    if fault == "category_mismatch":
        need = replace(need, category="tests")
    elif fault == "linked_item_without_excerpt":
        item = replace(item, excerpts=())
        budget = replace(budget, included_excerpts=0, content_bytes=0)
    elif fault == "subject_not_visible":
        need = replace(need, subject_terms=("not-visible",))
    else:
        first = replace(
            item.excerpts[0],
            start_line=10,
            end_line=10,
            content="first-subject\n",
            content_bytes=len("first-subject\n".encode("utf-8")),
        )
        second = replace(
            item.excerpts[0],
            start_line=11,
            end_line=11,
            content="second-subject\n",
            content_bytes=len("second-subject\n".encode("utf-8")),
        )
        item = replace(item, excerpts=(first, second))
        need = replace(
            need,
            subject_terms=("first-subject", "second-subject"),
        )
        budget = replace(
            budget,
            included_excerpts=2,
            content_bytes=first.content_bytes + second.content_bytes,
        )

    malformed = replace(
        pack,
        items=(item,),
        evidence_needs=(need, pack.evidence_needs[1]),
        budget=budget,
    )

    with pytest.raises(models.ContextPackError) as exc_info:
        serialization.context_pack_payload(malformed)

    assert (exc_info.value.code, exc_info.value.message) == (
        "context_failed",
        "Context pack construction failed",
    )


def test_v2_serialization_rejects_an_undeclared_visible_semantic_match() -> None:
    models, _, serialization = _v2_modules()
    pack = _v2_ready_pack()
    item = replace(pack.items[0], matched_need_ids=())
    need = replace(pack.evidence_needs[0], matched_item_ids=())
    malformed = replace(
        pack,
        status="partial",
        items=(item,),
        evidence_needs=(need,),
        missing_evidence=(
            models.MissingEvidence(
                need_id=need.id,
                category=need.category,
                required=True,
                reason=(
                    "required 核心 implementation evidence is missing "
                    "from the bounded context"
                ),
            ),
        ),
        confidence=models.ReadinessConfidence(
            level="low",
            reasons=("required evidence is missing",),
        ),
    )

    with pytest.raises(models.ContextPackError) as exc_info:
        serialization.context_pack_payload(malformed)

    assert (exc_info.value.code, exc_info.value.message) == (
        "context_failed",
        "Context pack construction failed",
    )


@pytest.mark.parametrize(
    ("level", "reasons", "recommended_missing"),
    [
        (
            "high",
            ["all required evidence is selected"],
            False,
        ),
        (
            "medium",
            ["all required evidence is selected"],
            False,
        ),
        (
            "high",
            [
                "all required evidence is selected",
                "recommended tests are missing",
            ],
            True,
        ),
        (
            "medium",
            [
                "all required evidence is selected",
                "protected original-direct evidence is present",
                "protected original-direct evidence is absent",
            ],
            False,
        ),
        (
            "medium",
            [
                "all required evidence is selected",
                "protected original-direct evidence is present",
                "recommended tests are missing",
            ],
            True,
        ),
    ],
)
def test_v2_serialization_enforces_exact_self_describing_ready_confidence(
    level: str,
    reasons: list[str],
    recommended_missing: bool,
) -> None:
    models, _, serialization = _v2_modules()
    payload = serialization.context_pack_payload(_v2_ready_pack())
    payload["budget"]["pack_bytes"] = 0
    if recommended_missing:
        payload["evidence_needs"].append(
            {
                "id": "need:tests",
                "category": "tests",
                "subject_terms": ["核心"],
                "required": False,
                "provenance": "structural_recommendation",
                "matched_item_ids": [],
            }
        )
        payload["missing_evidence"].append(
            {
                "need_id": "need:tests",
                "category": "tests",
                "required": False,
                "reason": (
                    "recommended 核心 test evidence is missing "
                    "from the bounded context"
                ),
            }
        )
    payload["confidence"] = {"level": level, "reasons": reasons}

    with pytest.raises(models.ContextPackError) as exc_info:
        serialization.canonical_context_pack_bytes(payload)

    assert (exc_info.value.code, exc_info.value.message) == (
        "context_failed",
        "Context pack construction failed",
    )


def test_v2_protected_present_confidence_requires_a_selected_result() -> None:
    models, _, serialization = _v2_modules()
    result_pack = _v2_ready_pack()
    result_payload = serialization.context_pack_payload(result_pack)
    anchor_item = replace(
        result_pack.items[0],
        source_kind="evidence_anchor",
        retrieval_rank=None,
        relevance_score=None,
    )
    anchor_pack = replace(
        result_pack,
        items=(anchor_item,),
        confidence=models.ReadinessConfidence(
            level="medium",
            reasons=(
                "all required evidence is selected",
                "protected original-direct evidence is absent",
            ),
        ),
    )
    anchor_payload = serialization.context_pack_payload(anchor_pack)
    forged = replace(
        anchor_pack,
        confidence=result_pack.confidence,
        budget=replace(anchor_pack.budget, pack_bytes=0),
    )

    assert result_payload["confidence"]["level"] == "high"
    assert anchor_payload["confidence"]["level"] == "medium"
    with pytest.raises(models.ContextPackError) as exc_info:
        serialization.context_pack_payload(forged)

    assert (exc_info.value.code, exc_info.value.message) == (
        "context_failed",
        "Context pack construction failed",
    )


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(
            lambda pack: replace(
                pack,
                groups={**pack.groups, "implementations": ()},
            ),
            id="missing-group-membership",
        ),
        pytest.param(
            lambda pack: replace(pack, reading_order=()),
            id="missing-reading-order-membership",
        ),
        pytest.param(
            lambda pack: replace(
                pack,
                groups={
                    group: (("item:0",) if group == "supporting" else ())
                    for group in pack.groups
                },
            ),
            id="wrong-group-membership",
        ),
    ],
)
def test_v2_serialization_requires_complete_consistent_item_references(
    mutate,
) -> None:
    models, _, serialization = _v2_modules()

    with pytest.raises(models.ContextPackError) as exc_info:
        serialization.context_pack_payload(mutate(_v2_pack()))

    assert (exc_info.value.code, exc_info.value.message) == (
        "context_failed",
        "Context pack construction failed",
    )


@pytest.mark.parametrize(
    "fault",
    ["reversed_reading_order", "reversed_group_order", "renamed_ids"],
)
def test_v2_serialization_requires_canonical_item_ids_and_order(
    fault: str,
) -> None:
    models, _, serialization = _v2_modules()
    pack = _v2_two_item_pack()
    serialization.context_pack_payload(pack)

    if fault == "reversed_reading_order":
        malformed = replace(pack, reading_order=("item:1", "item:0"))
    elif fault == "reversed_group_order":
        malformed = replace(
            pack,
            groups={
                **pack.groups,
                "implementations": ("item:1", "item:0"),
            },
        )
    else:
        renamed_items = (
            replace(pack.items[0], id="x"),
            replace(pack.items[1], id="y"),
        )
        renamed_needs = (
            replace(pack.evidence_needs[0], matched_item_ids=("x",)),
            pack.evidence_needs[1],
        )
        malformed = replace(
            pack,
            items=renamed_items,
            groups={
                group: (("x", "y") if group == "implementations" else ())
                for group in pack.groups
            },
            reading_order=("x", "y"),
            evidence_needs=renamed_needs,
        )

    with pytest.raises(models.ContextPackError) as exc_info:
        serialization.context_pack_payload(malformed)

    assert (exc_info.value.code, exc_info.value.message) == (
        "context_failed",
        "Context pack construction failed",
    )


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(lambda pack: replace(pack, status="READY"), id="status"),
        pytest.param(
            lambda pack: replace(
                pack,
                items=(replace(pack.items[0], classification_basis="path_role"),),
            ),
            id="classification-basis",
        ),
        pytest.param(
            lambda pack: replace(
                pack,
                items=(replace(pack.items[0], role="invented_role"),),
            ),
            id="role",
        ),
        pytest.param(
            lambda pack: replace(
                pack,
                items=(replace(pack.items[0], source_kind="anchor"),),
            ),
            id="source-kind",
        ),
        pytest.param(
            lambda pack: replace(
                pack,
                items=(
                    replace(pack.items[0], source_kind="evidence_anchor"),
                ),
            ),
            id="evidence-anchor-with-result-rank",
        ),
        pytest.param(
            lambda pack: replace(
                pack,
                evidence_needs=(
                    replace(pack.evidence_needs[0], provenance="query"),
                    pack.evidence_needs[1],
                ),
            ),
            id="provenance",
        ),
        pytest.param(
            lambda pack: replace(
                pack,
                confidence=replace(pack.confidence, level="certain"),
            ),
            id="confidence-level",
        ),
        pytest.param(
            lambda pack: replace(
                pack,
                items=(replace(pack.items[0], relevance_score=float("nan")),),
            ),
            id="nan-score",
        ),
        pytest.param(
            lambda pack: replace(
                pack,
                items=(
                    pack.items[0],
                    replace(pack.items[0], file_path="src/duplicate.py"),
                ),
            ),
            id="duplicate-item-id",
        ),
        pytest.param(
            lambda pack: replace(
                pack,
                evidence_needs=(
                    pack.evidence_needs[0],
                    replace(
                        pack.evidence_needs[1],
                        id=pack.evidence_needs[0].id,
                    ),
                ),
            ),
            id="duplicate-need-id",
        ),
        pytest.param(
            lambda pack: replace(
                pack,
                items=(
                    replace(
                        pack.items[0],
                        excerpts=(
                            replace(
                                pack.items[0].excerpts[0],
                                start_line=12,
                                end_line=11,
                            ),
                        ),
                    ),
                ),
            ),
            id="reversed-excerpt",
        ),
        pytest.param(
            lambda pack: replace(
                pack,
                items=(replace(pack.items[0], reasons=["not a tuple"]),),
            ),
            id="non-json-contract-shape",
        ),
        pytest.param(
            lambda pack: replace(
                pack,
                items=(replace(pack.items[0], reasons=(object(),)),),
            ),
            id="non-json-value",
        ),
        pytest.param(
            lambda pack: replace(
                pack,
                items=(replace(pack.items[0], matched_need_ids=("need:missing",)),),
            ),
            id="missing-need-reference",
        ),
        pytest.param(
            lambda pack: replace(pack, reading_order=("item:missing",)),
            id="missing-item-reference",
        ),
        pytest.param(
            lambda pack: replace(
                pack,
                items=(
                    replace(
                        pack.items[0],
                        excerpts=(
                            replace(
                                pack.items[0].excerpts[0],
                                content_bytes=(
                                    pack.items[0].excerpts[0].content_bytes + 1
                                ),
                            ),
                        ),
                    ),
                ),
            ),
            id="excerpt-byte-count",
        ),
        pytest.param(
            lambda pack: replace(
                pack,
                budget=replace(
                    pack.budget,
                    content_bytes=pack.budget.content_bytes + 1,
                ),
            ),
            id="budget-byte-count",
        ),
        pytest.param(
            lambda pack: replace(
                pack,
                budget=replace(pack.budget, included_items=2),
            ),
            id="budget-count",
        ),
        pytest.param(
            lambda pack: replace(
                pack,
                budget=replace(pack.budget, pack_bytes=True),
            ),
            id="bool-pack-bytes",
        ),
        pytest.param(
            lambda pack: replace(
                pack,
                budget=replace(pack.budget, pack_bytes=-1),
            ),
            id="negative-pack-bytes",
        ),
        pytest.param(
            lambda pack: replace(
                pack,
                budget=replace(pack.budget, pack_bytes=1),
            ),
            id="canonical-byte-mismatch",
        ),
    ],
)
def test_v2_serialization_rejects_malformed_records_with_fixed_error(mutate) -> None:
    models, _, serialization = _v2_modules()

    with pytest.raises(models.ContextPackError) as exc_info:
        serialization.context_pack_payload(mutate(_v2_pack()))

    assert exc_info.value.code == "context_failed"
    assert exc_info.value.message == "Context pack construction failed"
    assert str(exc_info.value) == "Context pack construction failed"


@pytest.mark.parametrize("boundary", ["item", "omission"])
@pytest.mark.parametrize(
    "path",
    ["/tmp/local-secret.py", "../outside.py", "a/./b.py", "C:\\secret.py"],
)
def test_v2_serialization_rejects_non_repo_relative_public_paths(
    boundary: str,
    path: str,
) -> None:
    models, _, serialization = _v2_modules()
    pack = _v2_pack()
    serialization.context_pack_payload(pack)
    if boundary == "item":
        malformed = replace(
            pack,
            items=(replace(pack.items[0], file_path=path),),
        )
    else:
        malformed = replace(
            pack,
            omissions=(replace(pack.omissions[0], file_path=path),),
        )

    with pytest.raises(models.ContextPackError) as exc_info:
        serialization.context_pack_payload(malformed)

    assert (exc_info.value.code, exc_info.value.message) == (
        "context_failed",
        "Context pack construction failed",
    )


def test_v2_canonical_serialization_rejects_malformed_payload_keys() -> None:
    models, _, serialization = _v2_modules()
    payload = serialization.context_pack_payload(_v2_pack())
    payload["items"][0]["unexpected"] = "value"

    with pytest.raises(models.ContextPackError) as exc_info:
        serialization.canonical_context_pack_bytes(payload)

    assert (exc_info.value.code, exc_info.value.message) == (
        "context_failed",
        "Context pack construction failed",
    )


def test_v2_omitted_count_may_exceed_compacted_public_preview() -> None:
    _, _, serialization = _v2_modules()
    pack = _v2_pack()

    payload = serialization.context_pack_payload(
        replace(
            pack,
            omissions=(),
            budget=replace(pack.budget, omitted_item_count=7),
        )
    )

    assert payload["omissions"] == []
    assert payload["budget"]["omitted_item_count"] == 7


@pytest.mark.parametrize(
    ("max_items", "omitted_item_count", "preview_count"),
    [(0, 1, 1), (1, 2, 2)],
)
def test_v2_serialization_caps_omission_preview_by_item_and_total_counts(
    max_items: int,
    omitted_item_count: int,
    preview_count: int,
) -> None:
    models, _, serialization = _v2_modules()
    pack = _v2_pack()
    needs = tuple(
        replace(need, matched_item_ids=())
        for need in pack.evidence_needs
    )
    malformed = replace(
        pack,
        items=(),
        groups={group: () for group in models.CONTEXT_GROUPS},
        reading_order=(),
        evidence_needs=needs,
        missing_evidence=(
            models.MissingEvidence(
                need_id="need:implementation",
                category="implementations",
                required=True,
                reason=(
                    "required 核心 implementation evidence is missing "
                    "from the bounded context"
                ),
            ),
            pack.missing_evidence[0],
        ),
        next_queries=(),
        omissions=tuple(
            models.Omission(
                file_path=f"src/omitted-{index}.py",
                group="implementations",
                reason=(
                    "lower priority than selected evidence under the context budget"
                ),
                matched_need_ids=("need:implementation",),
            )
            for index in range(preview_count)
        ),
        budget=replace(
            pack.budget,
            max_items=max_items,
            included_items=0,
            included_excerpts=0,
            content_bytes=0,
            truncated_item_count=0,
            omitted_item_count=omitted_item_count,
        ),
    )

    with pytest.raises(models.ContextPackError) as exc_info:
        serialization.context_pack_payload(malformed)

    assert (exc_info.value.code, exc_info.value.message) == (
        "context_failed",
        "Context pack construction failed",
    )


def test_v2_serialization_rejects_duplicate_source_lines_with_consistent_totals() -> None:
    models, _, serialization = _v2_modules()
    pack = _v2_pack()
    excerpt = pack.items[0].excerpts[0]
    overlapping = replace(excerpt, start_line=11, end_line=12)
    item = replace(pack.items[0], excerpts=(excerpt, overlapping))
    malformed = replace(
        pack,
        items=(item,),
        budget=replace(
            pack.budget,
            included_excerpts=2,
            content_bytes=excerpt.content_bytes * 2,
        ),
    )

    with pytest.raises(models.ContextPackError) as exc_info:
        serialization.context_pack_payload(malformed)

    assert (exc_info.value.code, exc_info.value.message) == (
        "context_failed",
        "Context pack construction failed",
    )


def test_v2_serialization_rejects_duplicate_file_items_with_consistent_indexes() -> None:
    models, _, serialization = _v2_modules()
    pack = _v2_pack()
    duplicate = replace(
        pack.items[0],
        id="item:1",
        matched_need_ids=(),
    )
    malformed = replace(
        pack,
        items=(pack.items[0], duplicate),
        groups={
            group: (("item:0", "item:1") if group == "implementations" else ())
            for group in models.CONTEXT_GROUPS
        },
        reading_order=("item:0", "item:1"),
        budget=replace(
            pack.budget,
            included_items=2,
            included_excerpts=2,
            content_bytes=pack.budget.content_bytes * 2,
        ),
    )

    with pytest.raises(models.ContextPackError) as exc_info:
        serialization.context_pack_payload(malformed)

    assert (exc_info.value.code, exc_info.value.message) == (
        "context_failed",
        "Context pack construction failed",
    )
