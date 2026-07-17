from __future__ import annotations

import ast
import inspect
from dataclasses import FrozenInstanceError, MISSING, fields
from pathlib import Path

import pytest

from context_search_tool.models import DocumentChunk, RetrievalSpan, SemanticMatch
from context_search_tool.retrieval_core import (
    context_expansion,
    evidence_merge,
    file_roles,
    ordering,
    ranking,
    relation_policy,
    types as core_types,
)


def _chunk(path: str, *, metadata: dict[str, object] | None = None) -> DocumentChunk:
    return DocumentChunk(
        chunk_id="chunk",
        file_path=Path(path),
        start_line=1,
        end_line=1,
        content="content",
        chunk_type="symbol",
        lexical_tokens=["content"],
        metadata=metadata or {},
    )


def _field_contract(cls: type[object]) -> list[tuple[str, str]]:
    contract = []
    for item in fields(cls):
        if item.default is not MISSING:
            default = repr(item.default)
        elif item.default_factory is not MISSING:
            default = item.default_factory.__name__
        else:
            default = "required"
        contract.append((item.name, default))
    return contract


def test_internal_dataclass_contracts_are_exact() -> None:
    assert core_types._RankedChunk.__name__ == "_RankedChunk"
    assert core_types._RankedChunk.__module__ == (
        "context_search_tool.retrieval_core.types"
    )
    assert core_types._ExpandedResult.__name__ == "_ExpandedResult"
    assert core_types._ExpandedResult.__module__ == (
        "context_search_tool.retrieval_core.types"
    )
    for cls in (core_types._RankedChunk, core_types._ExpandedResult):
        params = cls.__dataclass_params__
        assert params.frozen is True
        assert params.eq is True
        assert params.repr is True

    assert _field_contract(core_types._RankedChunk) == [
        ("chunk", "required"),
        ("score", "required"),
        ("score_parts", "required"),
        ("reasons", "required"),
        ("rank_tier", "required"),
        ("rerank_score", "required"),
        ("evidence_class", "required"),
        ("evidence_priority", "required"),
        ("semantic_matches", "list"),
        ("pre_ceiling_rerank_score", "0.0"),
        ("was_ceiling_clamped", "False"),
    ]
    assert _field_contract(core_types._ExpandedResult) == [
        ("chunk_ids", "required"),
        ("file_path", "required"),
        ("start_line", "required"),
        ("end_line", "required"),
        ("content", "required"),
        ("score", "required"),
        ("score_parts", "required"),
        ("reasons", "required"),
        ("followup_keywords", "required"),
        ("rank_tier", "required"),
        ("rerank_score", "required"),
        ("evidence_class", "required"),
        ("evidence_priority", "required"),
        ("semantic_matches", "list"),
        ("pre_ceiling_rerank_score", "0.0"),
        ("was_ceiling_clamped", "False"),
        ("spans", "()"),
        ("_context_content", "None"),
    ]


def test_internal_dataclass_equality_repr_and_frozen_behavior_are_exact() -> None:
    chunk = _chunk("src/example.py")
    first_ranked = core_types._RankedChunk(
        chunk=chunk,
        score=0.8,
        score_parts={"semantic": 0.8},
        reasons=["semantic match"],
        rank_tier=0,
        rerank_score=0.8,
        evidence_class="original_direct",
        evidence_priority=0,
    )
    second_ranked = core_types._RankedChunk(
        chunk=chunk,
        score=0.8,
        score_parts={"semantic": 0.8},
        reasons=["semantic match"],
        rank_tier=0,
        rerank_score=0.8,
        evidence_class="original_direct",
        evidence_priority=0,
    )
    assert first_ranked == second_ranked
    assert repr(first_ranked) == (
        f"_RankedChunk(chunk={chunk!r}, score=0.8, "
        "score_parts={'semantic': 0.8}, reasons=['semantic match'], "
        "rank_tier=0, rerank_score=0.8, evidence_class='original_direct', "
        "evidence_priority=0, semantic_matches=[], "
        "pre_ceiling_rerank_score=0.0, was_ceiling_clamped=False)"
    )
    with pytest.raises(FrozenInstanceError):
        first_ranked.score = 0.0  # type: ignore[misc]

    first_expanded = core_types._ExpandedResult(
        chunk_ids=["chunk"],
        file_path=Path("src/example.py"),
        start_line=1,
        end_line=1,
        content="content",
        score=0.8,
        score_parts={"semantic": 0.8},
        reasons=["semantic match"],
        followup_keywords=["example"],
        rank_tier=0,
        rerank_score=0.8,
        evidence_class="original_direct",
        evidence_priority=0,
        _context_content="first",
    )
    second_expanded = core_types._ExpandedResult(
        chunk_ids=["chunk"],
        file_path=Path("src/example.py"),
        start_line=1,
        end_line=1,
        content="content",
        score=0.8,
        score_parts={"semantic": 0.8},
        reasons=["semantic match"],
        followup_keywords=["example"],
        rank_tier=0,
        rerank_score=0.8,
        evidence_class="original_direct",
        evidence_priority=0,
        _context_content="second",
    )
    assert first_expanded == second_expanded
    assert repr(first_expanded) == (
        "_ExpandedResult(chunk_ids=['chunk'], "
        "file_path=PosixPath('src/example.py'), start_line=1, end_line=1, "
        "content='content', score=0.8, score_parts={'semantic': 0.8}, "
        "reasons=['semantic match'], followup_keywords=['example'], "
        "rank_tier=0, rerank_score=0.8, evidence_class='original_direct', "
        "evidence_priority=0, semantic_matches=[], "
        "pre_ceiling_rerank_score=0.0, was_ceiling_clamped=False, spans=())"
    )


def test_ordering_primitives_preserve_distinct_casing_semantics() -> None:
    values = ["Alpha", "alpha", "", "BETA", "Beta"]

    assert ordering.dedupe_lowered(values) == ["alpha", "beta"]
    assert ordering.ordered_unique_preserving_case(values) == ["Alpha", "BETA"]
    assert ordering.RERANK_SORT_DECIMALS == 3


def test_evidence_merge_primitives_preserve_score_policy_and_order() -> None:
    assert evidence_merge.bounded_score(-0.1) == 0.0
    assert evidence_merge.bounded_score(0.4) == 0.4
    assert evidence_merge.bounded_score(1.1) == 1.0

    left = {"route_sibling_penalty": -0.18, "role_boost": 0.12}
    right = {"route_sibling_penalty": -0.12, "role_boost": 0.18}
    assert evidence_merge.merge_score_parts(left, right) == {
        "route_sibling_penalty": -0.18,
        "role_boost": 0.18,
    }
    assert left == {"route_sibling_penalty": -0.18, "role_boost": 0.12}
    assert right == {"route_sibling_penalty": -0.12, "role_boost": 0.18}

    assert evidence_merge.merge_semantic_matches(
        [
            SemanticMatch("planner:10", 0.7),
            SemanticMatch("custom", 0.5),
            SemanticMatch("original", 0.2),
        ],
        [
            SemanticMatch("planner:2", 0.8),
            SemanticMatch("planner:10", 0.9),
            SemanticMatch("custom", 0.5),
        ],
    ) == [
        SemanticMatch("original", 0.2),
        SemanticMatch("planner:2", 0.8),
        SemanticMatch("planner:10", 0.9),
        SemanticMatch("custom", 0.5),
    ]


def test_resolved_graph_merge_scoring_and_provenance_are_single_channel() -> None:
    merged = evidence_merge.merge_score_parts(
        {
            "graph_calls_match": 0.4,
            "resolved_relation": 1.0,
            "graph_seed_original": 1.0,
        },
        {
            "graph_imports_match": 0.7,
            "resolved_relation": 1.0,
            "graph_seed_planner": 1.0,
        },
    )

    assert merged == {
        "graph_imports_match": 0.7,
        "resolved_relation": 1.0,
        "graph_seed_planner": 1.0,
    }
    assert ranking._combined_score(merged) == pytest.approx(0.7)
    assert ranking._evidence_class(merged) == "planner_relation"
    assert context_expansion._span_sources(merged) == ("relation",)
    assert "frontend import dependency" in ranking._reasons(merged, "query")


def test_context_merge_keeps_a_protected_direct_result_exact() -> None:
    direct = core_types._ExpandedResult(
        chunk_ids=["direct"],
        file_path=Path("src/Same.java"),
        start_line=1,
        end_line=3,
        content="one\ntwo\nthree",
        score=0.8,
        score_parts={"direct_text": 0.8},
        reasons=["direct text match"],
        followup_keywords=["direct"],
        rank_tier=2,
        rerank_score=0.8,
        evidence_class="original_direct",
        evidence_priority=0,
        spans=(RetrievalSpan(1, 3, 0.8, ("lexical",)),),
    )
    graph = core_types._ExpandedResult(
        chunk_ids=["graph"],
        file_path=Path("src/Same.java"),
        start_line=3,
        end_line=5,
        content="three\nfour\nfive",
        score=0.7,
        score_parts={
            "graph_calls_match": 0.7,
            "resolved_relation": 1.0,
            "graph_seed_original": 1.0,
        },
        reasons=["resolved Java method call"],
        followup_keywords=["graph"],
        rank_tier=1,
        rerank_score=0.7,
        evidence_class="original_relation",
        evidence_priority=2,
    )

    merged = context_expansion._merge_overlapping_results(
        [direct, graph],
        protect_direct_graph=True,
    )

    assert direct in merged
    assert next(item for item in merged if item is direct) == direct
    assert direct.score_parts == {"direct_text": 0.8}
    assert direct.spans == (RetrievalSpan(1, 3, 0.8, ("lexical",)),)


def test_relation_policy_values_are_exact() -> None:
    assert relation_policy.MAX_EXPANSION_DEPTH == 3
    assert relation_policy.MAX_EXPANSION_CANDIDATES == 1000
    assert relation_policy._MIN_RELATION_CONFIDENCE == 0.5
    assert relation_policy.MAX_GRAPH_SEED_SIGNALS == 512
    assert relation_policy.MAX_RESOLVED_GRAPH_HOPS == 4
    assert relation_policy.MAX_SIGNALS_POPPED_PER_QUERY == 4096
    assert relation_policy.MAX_EDGES_EXAMINED_PER_QUERY == 16384
    assert relation_policy.MAX_FRONTIER_ENTRIES_PER_QUERY == 8192
    assert relation_policy.MAX_EDGES_PER_SIGNAL_DIRECTION == 64
    assert relation_policy.MAX_RELATION_EXPANDED_CANDIDATES == 1000
    assert relation_policy.GRAPH_SCORE_KEYS == (
        "graph_calls_match",
        "graph_implements_match",
        "graph_uses_type_match",
        "graph_imports_match",
        "graph_routes_to_match",
        "graph_mapped_by_match",
        "graph_tests_match",
    )
    assert dict(relation_policy.GRAPH_REASON_BY_SCORE_KEY) == {
        "graph_calls_match": "resolved Java method call",
        "graph_implements_match": "Spring interface implementation",
        "graph_uses_type_match": "repository-local related type",
        "graph_routes_to_match": "frontend route target",
        "graph_imports_match": "frontend import dependency",
        "graph_mapped_by_match": "MyBatis mapper statement",
        "graph_tests_match": "associated test module",
    }


@pytest.mark.parametrize(
    ("path", "query", "tokens", "metadata", "expected"),
    [
        (
            "src/test/Foo.java",
            "service",
            ["service"],
            {},
            file_roles._GenericFileRole(
                "test", "high", penalty=0.10, penalty_key="test_penalty"
            ),
        ),
        (
            "src/generated/schema.json",
            "schema",
            ["schema"],
            {},
            file_roles._GenericFileRole(
                "generated_schema",
                "high",
                penalty=0.20,
                penalty_key="generated_schema_penalty",
            ),
        ),
        (
            "Cargo.lock",
            "service",
            ["service"],
            {},
            file_roles._GenericFileRole(
                "lockfile", "high", penalty=0.20, penalty_key="lockfile_penalty"
            ),
        ),
        (
            "Cargo.lock",
            "dependency versions",
            ["dependency", "versions"],
            {},
            file_roles._GenericFileRole("lockfile", "high"),
        ),
        (
            "src/service.py",
            "service",
            ["service"],
            {},
            file_roles._GenericFileRole("source", "none", source_boost=0.03),
        ),
        (
            "docs/guide.md",
            "service implementation",
            ["service", "implementation"],
            {},
            file_roles._GenericFileRole(
                "doc", "low", penalty=0.03, penalty_key="doc_penalty"
            ),
        ),
    ],
)
def test_generic_file_role_classification_is_exact(
    path: str,
    query: str,
    tokens: list[str],
    metadata: dict[str, object],
    expected: file_roles._GenericFileRole,
) -> None:
    assert file_roles._generic_file_role(
        _chunk(path, metadata=metadata), query, tokens
    ) == expected


def test_file_role_predicates_are_exact_and_readme_helper_is_uncalled() -> None:
    assert file_roles._looks_implementation_query("GET /users", ["users"])
    assert file_roles._looks_implementation_query("service", ["service"])
    assert not file_roles._looks_implementation_query("overview", ["overview"])
    assert file_roles._has_explicit_lockfile_query(["dependencies"], "Cargo.lock")
    assert file_roles._has_explicit_lockfile_query(["go", "sum"], "go.sum")
    assert not file_roles._has_explicit_lockfile_query(["service"], "Cargo.lock")
    assert file_roles._is_generated_schema_path("src/generated/a.py", ".py")
    assert file_roles._is_generated_schema_path("src/gen/schema.json", ".json")
    assert not file_roles._is_generated_schema_path("src/gen/a.py", ".py")
    assert file_roles._is_test_path("src/test/Foo.java")
    assert file_roles._is_test_path("src/footest.java")
    assert not file_roles._is_test_path("src/foo.java")
    assert file_roles._is_readme_document(Path("docs/README.md"))
    assert not file_roles._is_readme_document(Path("docs/guide.md"))

    tree = ast.parse(inspect.getsource(file_roles))
    definitions = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "_is_readme_document"
    ]
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_is_readme_document"
    ]
    assert len(definitions) == 1
    assert calls == []


def test_candidate_base_score_remains_present_and_uncalled() -> None:
    tree = ast.parse(inspect.getsource(ranking))
    definitions = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "_candidate_base_score"
    ]
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_candidate_base_score"
    ]

    assert len(definitions) == 1
    assert calls == []
