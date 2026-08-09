from __future__ import annotations

import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).parents[1]
DISPOSITION = (
    ROOT
    / "docs/superpowers/specs/2026-08-05-p15-local-efficacy-disposition.md"
)
LEDGER = (
    ROOT
    / "tests"
    / "fixtures"
    / "p15_post_acceptance"
    / "failure-classification.json"
)
ARCHIVAL_MODULES = {
    "tests/test_p8_real_python_graphs_acceptance.py",
    "tests/test_p13_bge_provider_measurement.py",
    "tests/test_p14_definition_owner_acceptance.py",
    "tests/test_p15_python_import_symbol_acceptance.py",
    "tests/test_p15_v2_python_import_symbol_acceptance.py",
    "tests/test_p15_v3_exact_provenance_bonus_acceptance.py",
    "tests/test_p15_pre_corpus_governance.py",
    "tests/test_p15_attempt_007_governance.py",
    "tests/test_p15_metric_replay.py",
}
ARCHIVAL_FAILURE_SOURCES = {
    "tests/test_p13_bge_provider_measurement.py": 16,
    "tests/test_p15_python_import_symbol_acceptance.py": 4,
    "tests/test_p15_v2_python_import_symbol_acceptance.py": 48,
    "tests/test_p15_v3_exact_provenance_bonus_acceptance.py": 36,
    "tests/test_p15_metric_replay.py": 1,
}
PRODUCT_NODES = {
    (
        "tests/test_exploration_boundaries.py::"
        "test_only_reviewed_production_change_roots_are_used"
    ),
    (
        "tests/test_p5_graph_contract.py::"
        "test_fresh_and_reverse_order_structural_projections_match_expected_bytes"
        "[p5_generic_tests]"
    ),
    (
        "tests/test_retrieval_trace_pipeline.py::"
        "test_trace_repository_reports_missing_index_without_changing_bundle"
    ),
}
RUNTIME_NODES = {
    (
        "tests/test_retrieval_core_characterization.py::"
        "test_runtime_identity_matches_frozen_platform"
    ),
    (
        "tests/test_retrieval_core_characterization.py::"
        "test_characterization_matches_immutable_baseline"
    ),
}
HASH_FIXTURE_NODE = (
    "tests/test_p8_real_python_graphs_acceptance.py::"
    "test_hash_v4_requires_static_descriptor_identity_and_zero_ollama"
)
BGE_FIXTURE_NODE = (
    "tests/test_p8_real_python_graphs_acceptance.py::"
    "test_bge_truncation_bounds_every_embedded_text"
)
MISSING_FIXTURE_NODES = {HASH_FIXTURE_NODE, BGE_FIXTURE_NODE}
CATEGORY_COUNTS = {
    "archival": 105,
    "contamination": 0,
    "missing durable fixture": 2,
    "product/current": 3,
    "runtime-pinned": 2,
    "unsupported runtime": 0,
}


def test_disposition_records_total_clean_baseline_failure_classification() -> None:
    raw = LEDGER.read_bytes()
    ledger = json.loads(raw)

    assert set(ledger) == {
        "baseline",
        "category_summary",
        "entries",
        "schema_version",
    }
    assert ledger["schema_version"] == (
        "p15-post-acceptance-failure-classification-v1"
    )
    assert raw == (
        json.dumps(
            ledger,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        + b"\n"
    )
    assert set(ledger["baseline"]) == {"command", "commit", "summary"}
    assert ledger["baseline"] == {
        "command": (
            'PYTHONPATH=.:src .venv/bin/pytest -q -m "not slow" --tb=no'
        ),
        "commit": "2426e5c2437a62208d723435c04bf0aefdd11390",
        "summary": {
            "deselected": 6,
            "failed": 112,
            "passed": 3700,
            "skipped": 5,
        },
    }
    assert ledger["category_summary"] == CATEGORY_COUNTS

    entries = ledger["entries"]
    assert len(entries) == 112
    assert all(
        set(entry) == {"category", "disposition", "node_id"}
        for entry in entries
    )
    assert all(
        isinstance(entry["disposition"], str) and entry["disposition"].strip()
        for entry in entries
    )
    node_ids = [entry["node_id"] for entry in entries]
    assert node_ids == sorted(node_ids)
    assert len(node_ids) == len(set(node_ids))
    assert Counter(entry["category"] for entry in entries) == {
        category: count for category, count in CATEGORY_COUNTS.items() if count
    }

    by_category = {
        category: {
            entry["node_id"]
            for entry in entries
            if entry["category"] == category
        }
        for category in CATEGORY_COUNTS
    }
    assert by_category["product/current"] == PRODUCT_NODES
    assert by_category["runtime-pinned"] == RUNTIME_NODES
    assert by_category["missing durable fixture"] == MISSING_FIXTURE_NODES
    assert Counter(
        node_id.split("::", maxsplit=1)[0]
        for node_id in by_category["archival"]
    ) == ARCHIVAL_FAILURE_SOURCES

    dispositions = {
        entry["node_id"]: entry["disposition"] for entry in entries
    }
    assert (
        "tests/test_embeddings_vector_store.py::"
        "test_default_hash_provider_factory_is_offline"
        in dispositions[HASH_FIXTURE_NODE]
    )
    assert (
        "tests/test_embeddings_bge.py::"
        "test_bge_provider_applies_exact_head_tail_transform_at_2001"
        in dispositions[BGE_FIXTURE_NODE]
    )

    text = DISPOSITION.read_text(encoding="utf-8")
    section = text.split("## 7. Clean baseline 失败分类", maxsplit=1)[1]
    normalized = " ".join(section.split())

    assert "[failure-classification.json]" in section
    assert "2426e5c2437a62208d723435c04bf0aefdd11390" in section
    assert "3700 passed, 112 failed, 5 skipped, 6 deselected" in normalized
    for row in (
        "| product/current | 3 |",
        "| archival | 105 |",
        "| runtime-pinned | 2 |",
        "| missing durable fixture | 2 |",
        "| contamination | 0 |",
        "| unsupported runtime | 0 |",
    ):
        assert row in section
    for module, count in ARCHIVAL_FAILURE_SOURCES.items():
        assert f"| `{module}` | {count} |" in section
    assert all(f"`{module}`" in section for module in ARCHIVAL_MODULES)
    assert "5 个 archival 失败源模块" in normalized
    assert "9 个最终 marker 模块" in normalized
    assert "`tests/test_retrieval_core_characterization.py`" in section
    assert "P8 的两个 missing durable fixture 节点" in normalized
    assert "不重复计入 archival=105" in normalized
    assert (
        "tests/test_embeddings_vector_store.py::"
        "test_default_hash_provider_factory_is_offline"
    ) in section
    assert (
        "tests/test_embeddings_bge.py::"
        "test_bge_provider_applies_exact_head_tail_transform_at_2001"
    ) in section
    assert (
        "verification_base_commit = "
        "`2426e5c2437a62208d723435c04bf0aefdd11390`"
    ) in section
    assert (
        "verification_candidate = `uncommitted Task 3 working tree immediately "
        "before the documentation-only observation update`"
    ) in normalized
    assert "3868 tests collected" in normalized
    assert "3342 passed, 5 skipped, 521 deselected" in normalized
