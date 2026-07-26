from __future__ import annotations

import json
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import generate_p5_graph_expected as p5
from generate_p8_python_graph_manifest import (
    P8_FIXTURE_REPO,
    STRUCTURAL_PATH,
    build_structural_projection,
    register_p8_forbidden_edges,
    render_structural,
)


@pytest.fixture(scope="session")
def structural_pair() -> tuple[dict, dict]:
    return (
        build_structural_projection(reverse_order=False),
        build_structural_projection(reverse_order=True),
    )


def test_structural_projection_matches_frozen_bytes(
    structural_pair: tuple[dict, dict],
) -> None:
    forward, reverse = structural_pair
    rendered_forward = render_structural(forward)
    rendered_reverse = render_structural(reverse)

    assert rendered_forward == rendered_reverse
    assert rendered_forward == STRUCTURAL_PATH.read_text(encoding="utf-8")


def test_structural_counts_and_states_are_exact(
    structural_pair: tuple[dict, dict],
) -> None:
    forward, _ = structural_pair
    counts = forward["counts"]

    assert counts["source_files"] == 19
    # 5 empty files (package markers) contribute no chunks and no module.
    assert counts["signals_by_kind"]["module"] == 14
    assert counts["signals_by_kind"] == {
        "function": 11,
        "method": 8,
        "module": 14,
        "type": 6,
    }
    assert counts["relations_by_kind"] == {"imports": 17, "tests": 1}
    assert counts["relations_by_resolution"] == {
        "ambiguous": 1,
        "external": 5,
        "resolved_exact": 7,
        "unresolved": 5,
    }
    assert forward["readiness"]["state"] == "ready"
    assert forward["readiness"]["graph_producer_version"] == 1
    for edge in forward["forbidden_edges"]:
        assert edge["relation_ids"] == []


def test_unresolved_states_and_ambiguity_have_no_target(
    structural_pair: tuple[dict, dict],
) -> None:
    forward, _ = structural_pair
    imports = [
        relation
        for relation in forward["relations"]
        if relation["kind"] == "imports"
    ]

    by_state: dict[str, list[dict]] = {}
    for relation in imports:
        by_state.setdefault(relation["state"], []).append(relation)

    for state in ("ambiguous", "external", "unresolved"):
        for relation in by_state.get(state, []):
            assert relation["target"]["signal_id"] == "", relation

    resolved_targets = {
        relation["target"]["file_path"]
        for relation in by_state.get("resolved_exact", [])
    }
    assert {
        "app/api.py",
        "app/clients/text.py",
        "app/service.py",
        "nested/pkg/target.py",
    } <= resolved_targets


def test_python_test_association_fields_are_exact() -> None:
    with tempfile.TemporaryDirectory(prefix="cst-p8-assoc-") as temp:
        repo = Path(temp) / "repo"
        shutil.copytree(P8_FIXTURE_REPO, repo)
        p5._index(repo, reverse_order=False)
        with sqlite3.connect(repo / ".context-search/index.sqlite") as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT source_signal_id, target_qualified_name, resolution,
                       producer, confidence, metadata
                FROM code_relations WHERE kind = 'tests'
                """
            ).fetchall()
            [association] = rows
            metadata = json.loads(association["metadata"])
            source_signal = conn.execute(
                "SELECT file_path, kind FROM code_signals WHERE signal_id = ?",
                (association["source_signal_id"],),
            ).fetchone()
            provenance = conn.execute(
                "SELECT kind, producer FROM code_relations WHERE relation_id = ?",
                (str(metadata.get("provenance_relation_id", "")),),
            ).fetchone()

    assert association["target_qualified_name"] == "app/service.py"
    assert association["resolution"] == "resolved_exact"
    assert association["producer"] == "test_association"
    assert association["confidence"] == 1.0
    assert metadata["resolution_basis"] == "exact_test_import"
    assert source_signal["file_path"] == "tests/test_service.py"
    assert source_signal["kind"] == "module"
    if provenance is not None:
        assert provenance["kind"] == "imports"
        assert provenance["producer"] == "python_ast"


def test_incremental_paths_converge_to_the_fresh_projection() -> None:
    def _project(repo: Path) -> str:
        projection = _projection_for_existing_repo(repo)
        # Convergence is defined over ACTIVE structure; soft-delete
        # tombstone counters and monotonic resolution-pass generations are
        # history bookkeeping, not structure.
        for key in list(projection["counts"]):
            if key.startswith("deleted_"):
                projection["counts"][key] = 0
        projection["readiness"]["producer_resolution_generation"] = 0
        projection["readiness"]["test_association_source_generation"] = 0
        return render_structural(projection)

    def _projection_for_existing_repo(repo: Path) -> dict:
        from context_search_tool.graph_lifecycle import (
            GRAPH_PRODUCER_VERSION_KEY,
        )
        from context_search_tool.sqlite_store import SQLiteStore

        register_p8_forbidden_edges()
        projection = p5._snapshot_projection("p8_python_graphs", repo)
        store = SQLiteStore(repo / ".context-search/index.sqlite")
        projection["readiness"]["graph_producer_version"] = int(
            store.get_metadata(GRAPH_PRODUCER_VERSION_KEY) or 0
        )
        return projection

    with tempfile.TemporaryDirectory(prefix="cst-p8-converge-") as temp:
        repo = Path(temp) / "repo"
        shutil.copytree(P8_FIXTURE_REPO, repo)
        p5._index(repo, reverse_order=False)
        fresh = _project(repo)

        # Authoritative no-op keeps the projection identical.
        p5._index(repo, reverse_order=False)
        assert _project(repo) == fresh

        # Importer change and revert converge back to the fresh projection.
        api = repo / "app" / "api.py"
        original = api.read_text(encoding="utf-8")
        api.write_text(
            original + "\n\ndef added_probe():\n    return None\n",
            encoding="utf-8",
        )
        p5._index(repo, reverse_order=False)
        assert _project(repo) != fresh
        api.write_text(original, encoding="utf-8")
        p5._index(repo, reverse_order=False)
        assert _project(repo) == fresh

        # Deleting and restoring an imported target converges as well.
        service = repo / "app" / "service.py"
        service_body = service.read_text(encoding="utf-8")
        service.unlink()
        p5._index(repo, reverse_order=False)
        after_delete = _project(repo)
        assert after_delete != fresh
        assert '"app/service.py"' not in json.dumps(
            json.loads(after_delete)["signals"]
        )
        service.write_text(service_body, encoding="utf-8")
        p5._index(repo, reverse_order=False)
        assert _project(repo) == fresh


def test_dense_import_expansion_does_not_materialize_chunks_per_edge(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Relation expansion needs edge-target existence, not full chunks.

    A dense Python import graph must not trigger one full chunk
    materialization (chunk row + tokens + symbols) per visited edge; that
    N+1 pattern produced a ~12x query latency regression in the P8 real
    A/B. Full materialization stays reserved for final candidates.
    """
    from context_search_tool.config import DEFAULT_CONFIG
    from context_search_tool.indexer import index_repository
    from context_search_tool.retrieval import query_repository

    repo = tmp_path / "dense"
    (repo / "app").mkdir(parents=True)
    fan_out = 40
    seed_imports = "".join(
        f"from app.dep{index} import value{index}\n" for index in range(fan_out)
    )
    (repo / "app" / "hub.py").write_text(
        seed_imports + "\n\ndef hub_entry():\n    return None\n",
        encoding="utf-8",
    )
    for index in range(fan_out):
        (repo / "app" / f"dep{index}.py").write_text(
            f"value{index} = {index}\n\n\ndef helper{index}():\n"
            f"    return value{index}\n",
            encoding="utf-8",
        )
    index_repository(repo, DEFAULT_CONFIG)

    import context_search_tool.sqlite_store as sqlite_store_module

    calls = {"count": 0}
    original = sqlite_store_module.SQLiteStore._chunks_from_rows

    def counting(self, connection, rows):
        calls["count"] += 1
        return original(self, connection, rows)

    monkeypatch.setattr(
        sqlite_store_module.SQLiteStore, "_chunks_from_rows", counting
    )

    bundle = query_repository(repo, "hub_entry", DEFAULT_CONFIG)

    assert any(
        str(result.file_path) == "app/hub.py" for result in bundle.results
    )
    # Bounded per-final-result loads (summary + relation-support checks,
    # each O(final_top_k)) plus a few batched stages are fine; one load
    # per visited edge is not. With fan_out=40 the pre-fix count was 107
    # and grew with edge count; the bound below is edge-count independent.
    assert calls["count"] <= 30, calls["count"]
