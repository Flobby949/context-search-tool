from __future__ import annotations

import hashlib
import json
import math
import unicodedata
from dataclasses import fields, replace
from pathlib import Path

import pytest

from context_search_tool.graph_contract import (
    EDGE_QUERY_LIMIT,
    GRAPH_SCORE_DECAY,
    MAX_EDGES_EXAMINED_PER_QUERY,
    MAX_EDGES_PER_SIGNAL_DIRECTION,
    MAX_EXPLAIN_INCOMING,
    MAX_EXPLAIN_OUTGOING,
    MAX_EXPLAIN_SIGNALS,
    MAX_FRONTEND_IMPORTS_PER_FILE,
    MAX_FRONTIER_ENTRIES_PER_QUERY,
    MAX_GRAPH_SEED_SIGNALS,
    MAX_LEGACY_RELATION_HOPS,
    MAX_PRODUCER_RELATIONS_PER_FILE,
    MAX_RELATION_EXPANDED_CANDIDATES,
    MAX_RESOLVED_GRAPH_HOPS,
    MAX_ROUTES_PER_ROUTER_FILE,
    MAX_SIGNALS_PER_FILE,
    MAX_SIGNALS_POPPED_PER_QUERY,
    MAX_TEST_TARGETS_PER_FILE,
    RELATION_DIRECTIONS,
    RELATION_KIND_PRIORITY,
    RELATION_KINDS,
    RELATION_WEIGHTS,
    RESOLUTION_STATES,
    effective_relation_confidence,
    generate_core_module_signal_id,
    generate_v5_relation_id,
    generate_v5_signal_id,
)
from context_search_tool.models import (
    CodeRelation,
    CodeSignal,
    generate_relation_id,
    generate_signal_id,
)


SIGNAL_FIELDS = [
    "signal_id",
    "chunk_id",
    "file_path",
    "kind",
    "name",
    "start_line",
    "end_line",
    "language",
    "tokens",
    "metadata",
    "qualified_name",
    "signature",
    "arity",
    "project_unit_key",
    "producer",
    "start_column",
    "end_column",
    "recallable",
]

RELATION_FIELDS = [
    "relation_id",
    "source_signal_id",
    "target_name",
    "kind",
    "confidence",
    "metadata",
    "target_kind",
    "target_qualified_name",
    "target_signature",
    "target_arity",
    "target_project_unit_key",
    "target_signal_id",
    "resolution",
    "producer",
    "producer_confidence",
    "resolution_confidence",
]


def _signal_identity(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "file_path": "src/caf\u00e9.py",
        "kind": "method",
        "qualified_name": "caf\u00e9.Service.run",
        "signature": "(str)",
        "start_line": 7,
        "start_column": 4,
        "end_line": 9,
        "end_column": 12,
        "producer": "python_ast",
    }
    values.update(overrides)
    return values


def _relation_identity(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "source_signal_id": "s5:" + "a" * 64,
        "kind": "calls",
        "target_kind": "method",
        "target_qualified_name": "demo.Service.run",
        "target_signature": "(java.lang.String)",
        "target_arity": 1,
        "target_project_unit_key": "services/demo",
        "producer": "java_ast",
    }
    values.update(overrides)
    return values


def test_graph_model_fields_are_appended_with_exact_legacy_defaults() -> None:
    assert [field.name for field in fields(CodeSignal)] == SIGNAL_FIELDS
    assert [field.name for field in fields(CodeRelation)] == RELATION_FIELDS

    signal = CodeSignal(
        "legacy-signal",
        "chunk-1",
        Path("src/App.java"),
        "method",
        "App.run",
        7,
        9,
        "java",
    )
    assert signal.qualified_name == ""
    assert signal.signature == ""
    assert signal.arity is None
    assert signal.project_unit_key == ""
    assert signal.producer == "legacy"
    assert signal.start_column == 0
    assert signal.end_column == 0
    assert signal.recallable is True

    relation = CodeRelation(
        "legacy-relation",
        "legacy-signal",
        "Target.call",
        "calls",
        0.75,
    )
    assert relation.target_kind == ""
    assert relation.target_qualified_name == ""
    assert relation.target_signature == ""
    assert relation.target_arity is None
    assert relation.target_project_unit_key == ""
    assert relation.target_signal_id == ""
    assert relation.resolution == "legacy"
    assert relation.producer == "legacy"
    assert relation.producer_confidence == 1.0
    assert relation.resolution_confidence is None


def test_legacy_id_helpers_remain_byte_identical() -> None:
    signal_id = generate_signal_id(
        Path("src/App.java"), "method", 7, "App.run"
    )
    assert signal_id == "d1ba4b51:method:7:4b6156ed"
    assert (
        generate_relation_id(signal_id, "Target.call", "calls")
        == "ebbfe4a7:calls:4b77c802"
    )


def test_v5_signal_id_is_fixed_order_utf8_nfc_canonical_json() -> None:
    canonical = (
        '{"file_path":"src/caf\u00e9.py","kind":"method",'
        '"qualified_name":"caf\u00e9.Service.run","signature":"(str)",'
        '"start_line":7,"start_column":4,"end_line":9,"end_column":12,'
        '"producer":"python_ast"}'
    ).encode("utf-8")
    expected = "s5:" + hashlib.sha256(canonical).hexdigest()

    assert generate_v5_signal_id(**_signal_identity()) == expected
    assert generate_v5_signal_id(
        **_signal_identity(
            file_path=unicodedata.normalize("NFD", "src/caf\u00e9.py"),
            qualified_name=unicodedata.normalize("NFD", "caf\u00e9.Service.run"),
        )
    ) == expected
    assert len(expected) == 67
    assert expected[3:] == expected[3:].lower()


def test_v5_signal_identity_distinguishes_columns_and_signatures() -> None:
    base = generate_v5_signal_id(**_signal_identity())
    assert generate_v5_signal_id(
        **_signal_identity(start_column=5)
    ) != base
    assert generate_v5_signal_id(
        **_signal_identity(signature="(bytes)")
    ) != base


@pytest.mark.parametrize(
    "file_path",
    ["", ".", "/src/App.java", "./src/App.java", "src/../App.java", "src\\App.java"],
)
def test_v5_signal_identity_requires_normalized_repository_path(
    file_path: str,
) -> None:
    with pytest.raises(ValueError, match="file_path"):
        generate_v5_signal_id(**_signal_identity(file_path=file_path))


def test_v5_relation_id_is_exact_selector_tuple() -> None:
    canonical = json.dumps(
        {
            "source_signal_id": "s5:" + "a" * 64,
            "kind": "calls",
            "target_kind": "method",
            "target_qualified_name": "demo.Service.run",
            "target_signature": "(java.lang.String)",
            "target_arity": 1,
            "target_project_unit_key": "services/demo",
            "producer": "java_ast",
        },
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    relation_id = generate_v5_relation_id(**_relation_identity())
    assert relation_id == "r5:" + hashlib.sha256(canonical).hexdigest()
    assert len(relation_id) == 67

    for field_name, value in (
        ("target_signature", "(int)"),
        ("target_arity", 2),
        ("target_project_unit_key", "services/other"),
        ("producer", "java_fallback"),
    ):
        assert generate_v5_relation_id(
            **_relation_identity(**{field_name: value})
        ) != relation_id


def test_v5_relation_identity_uses_empty_string_only_for_root_unit() -> None:
    assert generate_v5_relation_id(
        **_relation_identity(target_project_unit_key="")
    ).startswith("r5:")
    for invalid in (".", "/services/demo", "./services/demo", "services/../demo"):
        with pytest.raises(ValueError, match="target_project_unit_key"):
            generate_v5_relation_id(
                **_relation_identity(target_project_unit_key=invalid)
            )


def test_semantic_duplicate_occurrences_share_one_relation_id() -> None:
    relation_id = generate_v5_relation_id(**_relation_identity())
    first = CodeRelation(
        relation_id,
        "s5:" + "a" * 64,
        "demo.Service.run",
        "calls",
        1.0,
        metadata={
            "first_source_line": 11,
            "first_source_column": 4,
            "occurrence_count": 1,
        },
    )
    duplicate = replace(
        first,
        metadata={
            "first_source_line": 18,
            "first_source_column": 8,
            "occurrence_count": 2,
        },
    )
    assert first.relation_id == duplicate.relation_id == relation_id
    assert "occurrence_count" not in RELATION_FIELDS


def test_v5_ids_do_not_inherit_generated_legacy_short_hash_collision() -> None:
    seen: dict[str, str] = {}
    collision: tuple[str, str] | None = None
    for index in range(60_000):
        candidate = f"candidate-{index}"
        short_hash = hashlib.sha256(candidate.encode("utf-8")).hexdigest()[:8]
        previous = seen.get(short_hash)
        if previous is not None:
            collision = previous, candidate
            break
        seen[short_hash] = candidate

    assert collision is not None
    first, second = collision
    assert generate_signal_id(Path("src/App.java"), "method", 7, first) == (
        generate_signal_id(Path("src/App.java"), "method", 7, second)
    )
    assert generate_v5_signal_id(
        **_signal_identity(qualified_name=first)
    ) != generate_v5_signal_id(**_signal_identity(qualified_name=second))


def test_core_module_identity_is_the_shared_v5_identity() -> None:
    expected = generate_v5_signal_id(
        file_path="src/App.java",
        kind="module",
        qualified_name="src/App.java",
        signature="",
        start_line=1,
        start_column=0,
        end_line=20,
        end_column=1,
        producer="core_module",
    )
    assert generate_core_module_signal_id(
        file_path="src/App.java",
        start_line=1,
        start_column=0,
        end_line=20,
        end_column=1,
    ) == expected


@pytest.mark.parametrize(
    ("resolution", "target_signal_id", "resolution_confidence", "expected"),
    [
        ("resolved_exact", "s5:" + "b" * 64, 0.7, 0.7),
        ("resolved_unique", "s5:" + "b" * 64, 0.8, 0.8),
        ("ambiguous", "", None, 0.9),
        ("external", "", None, 0.9),
        ("unresolved", "", None, 0.9),
        ("legacy", "", None, 0.9),
    ],
)
def test_effective_confidence_covers_all_resolution_states(
    resolution: str,
    target_signal_id: str,
    resolution_confidence: float | None,
    expected: float,
) -> None:
    assert effective_relation_confidence(
        resolution=resolution,
        target_signal_id=target_signal_id,
        producer_confidence=0.9,
        resolution_confidence=resolution_confidence,
    ) == expected


@pytest.mark.parametrize("value", [-0.1, 1.1, math.nan, math.inf, -math.inf])
def test_effective_confidence_rejects_invalid_confidence(value: float) -> None:
    with pytest.raises(ValueError, match="producer_confidence"):
        effective_relation_confidence(
            resolution="unresolved",
            target_signal_id="",
            producer_confidence=value,
            resolution_confidence=None,
        )


@pytest.mark.parametrize(
    ("resolution", "target_signal_id", "resolution_confidence"),
    [
        ("unknown", "", None),
        ("resolved_exact", "", 1.0),
        ("resolved_unique", "s5:" + "b" * 64, None),
        ("ambiguous", "s5:" + "b" * 64, None),
        ("external", "", 0.5),
        ("legacy", "s5:" + "b" * 64, None),
    ],
)
def test_effective_confidence_rejects_invalid_resolution_combinations(
    resolution: str,
    target_signal_id: str,
    resolution_confidence: float | None,
) -> None:
    with pytest.raises(ValueError):
        effective_relation_confidence(
            resolution=resolution,
            target_signal_id=target_signal_id,
            producer_confidence=0.9,
            resolution_confidence=resolution_confidence,
        )


def test_relation_contract_is_closed_ordered_and_immutable() -> None:
    assert RESOLUTION_STATES == (
        "resolved_exact",
        "resolved_unique",
        "ambiguous",
        "external",
        "unresolved",
        "legacy",
    )
    assert RELATION_KINDS == (
        "calls",
        "implements",
        "implements_method",
        "uses_type",
        "imports_type",
        "imports",
        "routes_to",
        "mapped_by",
        "tests",
        "uses",
    )
    assert RELATION_DIRECTIONS == {
        "calls": "outgoing",
        "implements": "both",
        "implements_method": "both",
        "uses_type": "outgoing",
        "imports_type": "association_only",
        "imports": "outgoing",
        "routes_to": "outgoing",
        "mapped_by": "both",
        "tests": "intent_gated_both",
        "uses": "legacy_outgoing",
    }
    assert RELATION_WEIGHTS == {
        "calls": 1.0,
        "implements": 0.95,
        "implements_method": 0.95,
        "uses_type": 0.75,
        "imports_type": None,
        "imports": 0.85,
        "routes_to": 1.0,
        "mapped_by": 0.95,
        "tests": 0.8,
        "uses": None,
    }
    assert RELATION_KIND_PRIORITY == {
        kind: priority for priority, kind in enumerate(RELATION_KINDS)
    }
    with pytest.raises(TypeError):
        RELATION_DIRECTIONS["calls"] = "both"  # type: ignore[index]


def test_structural_work_budgets_are_exact() -> None:
    assert MAX_SIGNALS_PER_FILE == 4_096
    assert MAX_PRODUCER_RELATIONS_PER_FILE == 8_192
    assert MAX_FRONTEND_IMPORTS_PER_FILE == 64
    assert MAX_ROUTES_PER_ROUTER_FILE == 128
    assert MAX_TEST_TARGETS_PER_FILE == 8
    assert MAX_GRAPH_SEED_SIGNALS == 512
    assert MAX_RESOLVED_GRAPH_HOPS == 4
    assert MAX_LEGACY_RELATION_HOPS == 3
    assert MAX_EDGES_PER_SIGNAL_DIRECTION == 64
    assert EDGE_QUERY_LIMIT == 65
    assert MAX_SIGNALS_POPPED_PER_QUERY == 4_096
    assert MAX_EDGES_EXAMINED_PER_QUERY == 16_384
    assert MAX_FRONTIER_ENTRIES_PER_QUERY == 8_192
    assert MAX_RELATION_EXPANDED_CANDIDATES == 1_000
    assert MAX_EXPLAIN_SIGNALS == 32
    assert MAX_EXPLAIN_OUTGOING == 32
    assert MAX_EXPLAIN_INCOMING == 32
    assert GRAPH_SCORE_DECAY == 0.8
