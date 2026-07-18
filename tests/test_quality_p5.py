from __future__ import annotations

import json
import shutil
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from context_search_tool.config import DEFAULT_CONFIG, ToolConfig
from context_search_tool.graph_contract import RESOLVED_STATES
from context_search_tool.indexer import index_repository
from context_search_tool.quality.cases import load_quality_fixture
from context_search_tool.quality.runner import run_quality_fixture
from context_search_tool.retrieval import query_repository
from context_search_tool.retrieval_core.relation_policy import (
    GRAPH_SCORE_KEY_BY_KIND,
    GRAPH_SCORE_KEYS,
)
from generate_p5_graph_expected import (
    COMPATIBILITY_ALLOWLIST_NAME,
    EXPECTED_DIRECTORY,
    validate_compatibility_allowlist,
)
from p5_graph_identity import (
    EXPECTED_DETERMINISTIC_CASES,
    P5_CATALOG_PATH,
    P5_REPOSITORIES,
    PRE_P5_NO_EDGE_PATH,
    ROOT,
    load_input_manifest,
)


PROFILE = "p5_language_graphs"

_PROTECTED_DIRECT_FIXTURES = {
    "apply-audit-endpoint": "tests/fixtures/java-spring-mini",
    "workspace-service-symbol": "tests/fixtures/context-pack-java",
    "dashboard-controller-path": (
        "tests/fixtures/real_projects/cross_language_dashboard"
    ),
    "order-service-symbol": "tests/fixtures/real_projects/embedding_ab",
}

# The Task-1 manifest records planned proof labels, including one historical
# non-runtime alias. They select structural relation kinds only; none is treated
# as a runtime score-part key here.
_STRUCTURAL_KINDS_BY_PLANNED_PROOF = {
    "graph_calls_match": {"calls"},
    "graph_implements_method_match": {"implements_method"},
    "graph_uses_type_match": {"uses_type"},
    "graph_imports_match": {"imports"},
    "graph_routes_to_match": {"routes_to"},
    "graph_mapped_by_match": {"mapped_by"},
    "graph_tests_match": {"tests"},
}


@pytest.fixture(scope="session")
def p5_quality_report() -> dict[str, Any]:
    return run_quality_fixture(
        P5_CATALOG_PATH,
        PROFILE,
        output_path=None,
        markdown_path=None,
    )


def _p5_config() -> ToolConfig:
    return replace(
        DEFAULT_CONFIG,
        retrieval=replace(DEFAULT_CONFIG.retrieval, final_top_k=12),
        embedding=replace(
            DEFAULT_CONFIG.embedding,
            provider="hash",
            model="hash-v1",
            dimensions=384,
            base_url=None,
            api_key_env=None,
        ),
        query_planner=replace(DEFAULT_CONFIG.query_planner, enabled=False),
    )


def _direct_score_parts(parts: dict[str, float]) -> dict[str, float]:
    excluded_fragments = (
        "semantic",
        "vector",
        "relation",
        "graph_",
        "combined",
        "rerank",
        "planner_",
    )
    return {
        key: value
        for key, value in sorted(parts.items())
        if not any(fragment in key for fragment in excluded_fragments)
    }


def _normalized_item(item: Any) -> dict[str, Any]:
    return {
        "file_path": Path(item.file_path).as_posix(),
        "start_line": item.start_line,
        "end_line": item.end_line,
        "direct_score_parts": _direct_score_parts(item.score_parts),
        "reasons": list(item.reasons),
    }


def _case_records(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {case["case_id"]: case for case in report["cases"]}


def _assays() -> dict[str, dict[str, Any]]:
    return {
        assay["case_id"]: assay for assay in load_input_manifest()["assays"]
    }


def _projection(repository_key: str) -> dict[str, Any]:
    return json.loads(
        (EXPECTED_DIRECTORY / f"{repository_key}.json").read_text(
            encoding="utf-8"
        )
    )


def _positive_graph_keys(score_parts: dict[str, float]) -> tuple[str, ...]:
    return tuple(
        key for key in GRAPH_SCORE_KEYS if score_parts.get(key, 0.0) > 0.0
    )


def _relation_matches_result(
    relation: dict[str, Any],
    path: str,
    score_key: str,
) -> bool:
    return (
        relation["state"] in RESOLVED_STATES
        and GRAPH_SCORE_KEY_BY_KIND.get(relation["kind"]) == score_key
        and path
        in {
            relation["source"]["file_path"],
            relation["target"]["file_path"],
        }
    )


def test_p5_deterministic_profile_passes_exact_reviewed_twelve(
    p5_quality_report: dict[str, Any],
) -> None:
    expected = [
        (repo, case, query)
        for repo, case, query, _mode in EXPECTED_DETERMINISTIC_CASES
    ]
    assert [
        (case["repo_key"], case["case_id"], case["query"])
        for case in p5_quality_report["cases"]
    ] == expected

    aggregate = p5_quality_report["aggregate"]
    assert {
        key: aggregate[key]
        for key in (
            "selected",
            "attempted",
            "executed",
            "passed",
            "failed",
            "skipped",
            "errors",
        )
    } == {
        "selected": 12,
        "attempted": 12,
        "executed": 12,
        "passed": 12,
        "failed": 0,
        "skipped": 0,
        "errors": 0,
    }, {
        case["case_id"]: case["failures"]
        for case in p5_quality_report["cases"]
        if case["status"] != "pass"
    }


def test_p5_deterministic_profile_uses_exact_budgets(
    p5_quality_report: dict[str, Any],
) -> None:
    fixture = load_quality_fixture(P5_CATALOG_PATH)
    assert fixture.profile_configs[PROFILE] == {
        "retrieval": {"final_top_k": 12},
        "embedding": {
            "provider": "hash",
            "model": "hash-v1",
            "dimensions": 384,
        },
        "query_planner": {"enabled": False},
    }

    for repo in p5_quality_report["repos"]:
        config = repo["config"]
        assert config["retrieval"]["final_top_k"] == 12
        assert config["embedding"] == {
            "provider": "hash",
            "model": "hash-v1",
            "dimensions": 384,
            "base_url": None,
            "api_key_env": None,
        }
        assert config["query_planner"]["enabled"] is False

    report_cases = _case_records(p5_quality_report)
    for repo in fixture.repos:
        for case in repo.queries:
            record = report_cases[case.case_id]
            assert len(record["top_results"]) <= 12
            assert [item["rank"] for item in record["top_results"]] == list(
                range(1, len(record["top_results"]) + 1)
            )
            if case.maximum_pack_bytes is not None:
                assert case.maximum_pack_bytes == 65536
                assert record["metrics"]["pack_bytes"] <= 65536
            if case.maximum_retrieval_call_count is not None:
                assert case.maximum_retrieval_call_count == 3
                assert record["metrics"]["retrieval_call_count"] <= 3


def test_p5_raw_graph_score_parts_are_closed_and_structurally_proven(
    p5_quality_report: dict[str, Any],
) -> None:
    cases = _case_records(p5_quality_report)
    assays = _assays()
    projections = {
        repository_key: _projection(repository_key)
        for repository_key in P5_REPOSITORIES
    }

    for case in p5_quality_report["cases"]:
        projection = projections[case["repo_key"]]
        for result in case["top_results"]:
            match_keys = {
                key
                for key in result["score_parts"]
                if key.startswith("graph_") and key.endswith("_match")
            }
            assert match_keys <= set(GRAPH_SCORE_KEYS)
            positive = _positive_graph_keys(result["score_parts"])
            if not positive:
                continue
            assert len(positive) == 1
            assert match_keys == set(positive)
            assert any(
                _relation_matches_result(relation, result["path"], positive[0])
                for relation in projection["relations"]
            ), (case["case_id"], result["path"], positive[0])

    for case_id, assay in assays.items():
        forbidden_key = assay["forbidden_graph_match_key"]
        by_path = {item["path"]: item for item in cases[case_id]["top_results"]}
        if forbidden_key is not None:
            for path in assay["graph_only_negative_paths"]:
                if path in by_path:
                    assert forbidden_key not in by_path[path]["score_parts"]

        relations = projections[assay["repo_key"]]["relations"]
        for proof in assay["required_graph_proofs"]:
            path = proof["path"]
            expected_kinds = _STRUCTURAL_KINDS_BY_PLANNED_PROOF[
                proof["required_match_key_if_present"]
            ]
            canonical_keys = {
                GRAPH_SCORE_KEY_BY_KIND[kind] for kind in expected_kinds
            }
            assert len(canonical_keys) == 1
            canonical_key = next(iter(canonical_keys))
            assert any(
                relation["state"] in RESOLVED_STATES
                and relation["kind"] in expected_kinds
                and path
                in {
                    relation["source"]["file_path"],
                    relation["target"]["file_path"],
                }
                for relation in relations
            ), (case_id, path, expected_kinds)

            selected = by_path.get(path)
            if selected is None:
                assert proof["baseline"] == "absent"
                continue
            score_parts = selected["score_parts"]
            if score_parts["evidence_priority"] == 0.0:
                assert not set(GRAPH_SCORE_KEYS).intersection(score_parts)
            else:
                assert score_parts.get(canonical_key, 0.0) > 0.0
                assert _positive_graph_keys(score_parts) == (canonical_key,)


def test_compatibility_allowlist_has_only_graph_proven_deltas(
    p5_quality_report: dict[str, Any],
) -> None:
    allowlist = json.loads(
        (EXPECTED_DIRECTORY / COMPATIBILITY_ALLOWLIST_NAME).read_text(
            encoding="utf-8"
        )
    )
    validate_compatibility_allowlist(allowlist)

    cases = _case_records(p5_quality_report)
    assays = _assays()
    protected = {
        (item["case_id"], item["winner"])
        for item in load_input_manifest()["evidence"]["protected_direct"]
    }
    protected_paths = {path for _case_id, path in protected}

    for entry in allowlist:
        assert entry["profile"] == PROFILE
        assay = assays[entry["case_id"]]
        assert entry["path"] not in {
            *assay["negative_paths"],
            *assay["graph_only_negative_paths"],
        }
        assert (entry["case_id"], entry["path"]) not in protected
        assert entry["path"] not in protected_paths

        before = {
            path: rank
            for rank, path in enumerate(assay["initial_result_paths"], start=1)
        }
        after = {
            item["path"]: item
            for item in cases[entry["case_id"]]["top_results"]
        }
        assert entry["before_rank"] == before.get(entry["path"])
        assert entry["after_rank"] == after[entry["path"]]["rank"]
        assert entry["before_rank"] != entry["after_rank"]

        projection = _projection(assay["repo_key"])
        relation = next(
            (
                item
                for item in projection["relations"]
                if item["relation_id"] == entry["relation_id"]
            ),
            None,
        )
        assert relation is not None
        assert relation["state"] in RESOLVED_STATES
        assert relation["kind"] == entry["relation_kind"]
        relation_side = "target" if entry["direction"] == "outgoing" else "source"
        assert relation[relation_side]["file_path"] == entry["path"]

        expected_key = GRAPH_SCORE_KEY_BY_KIND[entry["relation_kind"]]
        score_parts = after[entry["path"]]["score_parts"]
        assert _positive_graph_keys(score_parts) == (expected_key,)
        assert {
            key
            for key in score_parts
            if key.startswith("graph_") and key.endswith("_match")
        } == {expected_key}


def test_protected_direct_and_no_edge_projections_are_exact(
    tmp_path: Path,
) -> None:
    config = _p5_config()
    manifest = load_input_manifest()

    for expected in manifest["evidence"]["protected_direct"]:
        case_id = expected["case_id"]
        repo = tmp_path / case_id
        shutil.copytree(ROOT / _PROTECTED_DIRECT_FIXTURES[case_id], repo)
        index_repository(repo, config)
        winner = query_repository(repo, expected["query"], config).results[0]
        observed = {
            "case_id": case_id,
            "query": expected["query"],
            "winner": winner.file_path.as_posix(),
            "start_line": winner.start_line,
            "end_line": winner.end_line,
            "direct_score_parts": _direct_score_parts(winner.score_parts),
        }
        assert observed == expected

    expected_no_edge = json.loads(
        PRE_P5_NO_EDGE_PATH.read_text(encoding="utf-8")
    )
    no_edge_repo = tmp_path / "no-edge"
    shutil.copytree(ROOT / P5_REPOSITORIES["p5_malformed_compat"], no_edge_repo)
    index_repository(no_edge_repo, config)
    bundle = query_repository(no_edge_repo, expected_no_edge["query"], config)
    observed_no_edge = {
        "schema_version": 1,
        "case_id": expected_no_edge["case_id"],
        "query": expected_no_edge["query"],
        "config": {
            "retrieval": {"final_top_k": config.retrieval.final_top_k},
            "embedding": {
                "provider": config.embedding.provider,
                "model": config.embedding.model,
                "dimensions": config.embedding.dimensions,
            },
            "query_planner": {"enabled": config.query_planner.enabled},
        },
        "results": [_normalized_item(item) for item in bundle.results],
        "evidence_anchors": [
            _normalized_item(item) for item in bundle.evidence_anchors
        ],
    }
    assert observed_no_edge == expected_no_edge
