from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from context_search_tool.config import DEFAULT_CONFIG
from context_search_tool.graph_contract import EDGE_QUERY_LIMIT
from context_search_tool.indexer import index_repository
from context_search_tool.sqlite_store import SQLiteStore
from generate_p5_graph_expected import (
    COMPATIBILITY_ALLOWLIST_NAME,
    EXPECTED_DIRECTORY,
    EXPECTED_FILE_NAMES,
    P5_MANIFEST_PATH,
    P5_REPOSITORIES,
    build_repository_projection,
    initialize,
    project,
    validate_compatibility_allowlist,
)
from p5_graph_identity import ROOT, canonical_json_bytes


@pytest.fixture(scope="session")
def projected_candidates(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    root = tmp_path_factory.mktemp("p5-structural-candidates")
    candidate_a = root / "candidate-a"
    candidate_b = root / "candidate-b"
    project(P5_MANIFEST_PATH, candidate_a)
    project(P5_MANIFEST_PATH, candidate_b, reverse_order=True)
    return candidate_a, candidate_b


@pytest.mark.parametrize("repository_key", tuple(P5_REPOSITORIES))
def test_fresh_and_reverse_order_structural_projections_match_expected_bytes(
    projected_candidates: tuple[Path, Path],
    repository_key: str,
) -> None:
    candidate_a, candidate_b = projected_candidates
    name = f"{repository_key}.json"
    first = (candidate_a / name).read_bytes()
    second = (candidate_b / name).read_bytes()
    expected = (EXPECTED_DIRECTORY / name).read_bytes()

    assert first == second == expected


def test_compatibility_allowlist_is_canonical_and_has_closed_entry_shape(
    projected_candidates: tuple[Path, Path],
) -> None:
    candidate_a, candidate_b = projected_candidates
    empty = canonical_json_bytes([])
    assert (candidate_a / COMPATIBILITY_ALLOWLIST_NAME).read_bytes() == empty
    assert (candidate_b / COMPATIBILITY_ALLOWLIST_NAME).read_bytes() == empty
    expected_path = EXPECTED_DIRECTORY / COMPATIBILITY_ALLOWLIST_NAME
    expected = json.loads(expected_path.read_text(encoding="utf-8"))
    validate_compatibility_allowlist(expected)
    assert expected_path.read_bytes() == canonical_json_bytes(expected)


def test_compatibility_allowlist_validator_closes_evidence_fields_and_order() -> None:
    entry = {
        "profile": "ci",
        "case_id": "example-case",
        "path": "src/example.py",
        "before_rank": None,
        "after_rank": 2,
        "relation_id": f"r5:{'0' * 64}",
        "relation_kind": "imports",
        "direction": "outgoing",
        "why_legal": "resolved import adds a graph-only candidate",
    }
    validate_compatibility_allowlist([entry])

    with pytest.raises(RuntimeError, match="unexpected keys"):
        validate_compatibility_allowlist([{**entry, "extra": True}])
    with pytest.raises(RuntimeError, match="uniquely sorted"):
        validate_compatibility_allowlist(
            [
                {**entry, "case_id": "z-case"},
                {**entry, "case_id": "a-case"},
            ]
        )


@pytest.mark.parametrize("repository_key", tuple(P5_REPOSITORIES))
def test_forbidden_edges_and_exact_module_test_invariants_are_closed(
    repository_key: str,
) -> None:
    projection = json.loads(
        (EXPECTED_DIRECTORY / f"{repository_key}.json").read_text(encoding="utf-8")
    )

    assert projection["forbidden_edges"]
    assert all(not item["relation_ids"] for item in projection["forbidden_edges"])
    modules = projection["module_invariants"]
    assert modules["module_count"] == modules["active_chunk_file_count"]
    assert modules["missing_paths"] == []
    assert modules["duplicate_paths"] == []
    assert modules["invalid_identity_paths"] == []
    tests = projection["test_invariants"]
    assert tests["non_test_source_relation_ids"] == []
    assert tests["test_target_relation_ids"] == []
    assert tests["cross_unit_relation_ids"] == []
    assert tests["unresolved_relation_ids"] == []
    for item in projection["truncation"]:
        counts = {count["key"]: count["count"] for count in item["counts"]}
        assert counts["graph_omitted_signal_count"] >= 0
        assert counts["graph_omitted_relation_count"] >= 0


@pytest.mark.parametrize("repository_key", tuple(P5_REPOSITORIES))
def test_incoming_rows_return_the_exact_source_side_of_each_resolved_edge(
    tmp_path: Path,
    repository_key: str,
) -> None:
    repo = tmp_path / "repo"
    shutil.copytree(ROOT / P5_REPOSITORIES[repository_key], repo)
    index_repository(repo, DEFAULT_CONFIG)
    expected = json.loads(
        (EXPECTED_DIRECTORY / f"{repository_key}.json").read_text(encoding="utf-8")
    )
    store = SQLiteStore(repo / ".context-search/index.sqlite")

    with store.graph_read_session() as session:
        assert session.capability.status == "ready"
        for target in expected["incoming_sources"]:
            observed = session.incoming_relations(
                target["target_signal_id"],
                limit=EDGE_QUERY_LIMIT,
            )
            expected_sources = {
                item["relation_id"]: item for item in target["sources"]
            }
            assert {item.relation_id for item in observed} == set(expected_sources)
            for relation in observed:
                source = session.signal_for_id(relation.source_signal_id)
                assert source is not None
                assert source.file_path.as_posix() == expected_sources[
                    relation.relation_id
                ]["source_path"]
                assert source.signal_id == expected_sources[relation.relation_id][
                    "source_signal_id"
                ]


def test_full_rebuild_recovery_matches_fresh_and_then_takes_verified_noop() -> None:
    projection = json.loads(
        (
            EXPECTED_DIRECTORY / "p5_java_spring.json"
        ).read_text(encoding="utf-8")
    )
    recovery = projection["recovery"]

    assert recovery == {
        "exercised": True,
        "fault_stage": "signals_persisted",
        "fault_state": "stale",
        "fault_full_reindex_required": True,
        "recovery_summary": {
            "files_seen": 18,
            "files_indexed": 18,
            "files_skipped": 0,
            "files_deleted": 0,
            "chunks_indexed": 18,
        },
        "final_matches_fresh": True,
        "verified_noop_summary": {
            "files_seen": 18,
            "files_indexed": 0,
            "files_skipped": 18,
            "files_deleted": 0,
            "chunks_indexed": 0,
        },
    }


def test_initializer_requires_two_matching_candidates_and_refuses_overwrite(
    tmp_path: Path,
    projected_candidates: tuple[Path, Path],
) -> None:
    candidate_a, candidate_b = projected_candidates
    output = tmp_path / "initialized"
    initialize(P5_MANIFEST_PATH, candidate_a, candidate_b, output)

    assert {path.name for path in output.iterdir()} == set(EXPECTED_FILE_NAMES)
    with pytest.raises(RuntimeError, match="refusing to overwrite"):
        initialize(P5_MANIFEST_PATH, candidate_a, candidate_b, output)


@pytest.mark.parametrize("damage", ["extra_file", "unexpected_key", "different_bytes"])
def test_initializer_rejects_unreviewed_candidate_content(
    tmp_path: Path,
    projected_candidates: tuple[Path, Path],
    damage: str,
) -> None:
    original_a, original_b = projected_candidates
    candidate_a = tmp_path / "candidate-a"
    candidate_b = tmp_path / "candidate-b"
    shutil.copytree(original_a, candidate_a)
    shutil.copytree(original_b, candidate_b)
    if damage == "extra_file":
        (candidate_b / "unexpected.json").write_bytes(canonical_json_bytes({}))
    elif damage == "unexpected_key":
        path = candidate_b / "p5_react.json"
        value = json.loads(path.read_text(encoding="utf-8"))
        value["unexpected"] = True
        path.write_bytes(canonical_json_bytes(value))
    else:
        path = candidate_b / "p5_react.json"
        value = json.loads(path.read_text(encoding="utf-8"))
        value["readiness"]["topology_fingerprint"] = "0" * 64
        value["topology"]["fingerprint"] = "0" * 64
        path.write_bytes(canonical_json_bytes(value))

    with pytest.raises(RuntimeError):
        initialize(
            P5_MANIFEST_PATH,
            candidate_a,
            candidate_b,
            tmp_path / "output",
        )


def test_project_refuses_a_noncanonical_or_changed_frozen_manifest(
    tmp_path: Path,
) -> None:
    manifest = json.loads(P5_MANIFEST_PATH.read_text(encoding="utf-8"))
    manifest["unexpected"] = True
    changed = tmp_path / "manifest.json"
    changed.write_bytes(canonical_json_bytes(manifest))

    with pytest.raises(RuntimeError, match="unexpected keys"):
        project(changed, tmp_path / "candidate")


def test_project_cannot_bypass_initializer_into_the_expected_fixture_tree() -> None:
    with pytest.raises(RuntimeError, match="outside frozen fixtures"):
        project(P5_MANIFEST_PATH, EXPECTED_DIRECTORY / "direct-project")


def test_projection_builder_rejects_unknown_repository_key() -> None:
    with pytest.raises(ValueError, match="unknown P5 repository key"):
        build_repository_projection("p5_unknown")
