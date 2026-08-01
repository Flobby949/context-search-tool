from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sqlite3

import pytest

import p15_python_import_symbol_acceptance as acceptance


MANIFEST_PATH = Path(__file__).parent / "fixtures/p15_python_import_symbols/input_manifest.json"


def _manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _write_manifest(tmp_path: Path, payload: dict) -> Path:
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    return path


def test_frozen_manifest_and_heldout_seal_v2_validate() -> None:
    manifest = acceptance.validate_manifest(MANIFEST_PATH)

    assert manifest["heldout_seal"]["seal_id"] == "p15-heldout-click-00e592c-v2"
    assert manifest["heldout_seal"]["status"] == "sealed_unopened"
    assert manifest["heldout_seal"]["required_item_denominator"] == 12
    assert manifest["r1"]["target_signal_kinds"] == ["type", "function"]


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda value: value.__setitem__("behavior_baseline", "0" * 40), "baseline"),
        (lambda value: value["development_gold"].__setitem__("sha256", "0" * 64), "gold"),
        (lambda value: value["sources"].pop("redink"), "roles"),
        (lambda value: value["r2"].__setitem__("development_minimum_new_required_items", 2), "R2"),
        (lambda value: value["heldout_seal"].__setitem__("required_item_denominator", 11), "denominator"),
        (lambda value: value["heldout_seal"].__setitem__("status", "opened"), "opened"),
        (lambda value: value["online"].__setitem__("planner_enabled", True), "online"),
    ],
)
def test_manifest_mutations_fail_closed(tmp_path: Path, mutate, message: str) -> None:
    payload = _manifest()
    mutate(payload)

    with pytest.raises(ValueError, match=message):
        acceptance.validate_manifest(_write_manifest(tmp_path, payload))


def test_manifest_rejects_absolute_or_escaping_paths(tmp_path: Path) -> None:
    payload = _manifest()
    payload["development_gold"]["path"] = "/tmp/gold.json"
    with pytest.raises(ValueError, match="repository-relative"):
        acceptance.validate_manifest(_write_manifest(tmp_path, payload))

    payload = _manifest()
    payload["heldout_seal"]["public_contract_path"] = "../contract.json"
    with pytest.raises(ValueError, match="repository-relative"):
        acceptance.validate_manifest(_write_manifest(tmp_path, payload))


@pytest.mark.parametrize(
    "payload",
    [
        {"api_key": "not-a-real-key"},
        {"nested": {"source_body": "print('private')"}},
        {"path": "/Users/example/private/repository"},
        {"error": "-----BEGIN PRIVATE KEY-----"},
    ],
)
def test_privacy_checker_rejects_secrets_source_and_local_paths(payload: dict) -> None:
    with pytest.raises(ValueError):
        acceptance._privacy_check(payload)


def _capture_pair() -> tuple[dict, dict]:
    baseline_cases = {}
    candidate_cases = {}
    specs = (
        ("red-case", "redink", "red-required.py"),
        ("daily-case-one", "daily", "daily-required-one.py"),
        ("daily-case-two", "daily", "daily-required-two.py"),
    )
    for case_id, repo, required_path in specs:
        anchor = f"{case_id}-anchor.py"
        baseline_cases[case_id] = {
            "repo": repo,
            "selected": [
                {
                    "rank": 1,
                    "path": anchor,
                    "start_line": 1,
                    "end_line": 2,
                    "score": 1.0,
                    "score_parts": {"direct": 1.0},
                    "reasons": ["direct"],
                    "exact_witness": None,
                    "chunk_id": f"chunk:anchor:{case_id}",
                    "origin_chunk_ids": [f"chunk:anchor:{case_id}"],
                    "rank_history": [],
                    "stage_trajectory": [],
                }
            ],
            "required": [
                {"path": required_path, "role": "support", "rank": None, "state": "not_selected"},
                {"path": anchor, "role": "entrypoint", "rank": 1, "state": "selected"},
            ],
            "contextual": [],
            "trace": {"stages": []},
        }
        candidate_cases[case_id] = deepcopy(baseline_cases[case_id])
        candidate_cases[case_id]["selected"].append(
            {
                "rank": 2,
                "path": required_path,
                "start_line": 10,
                "end_line": 20,
                "score": 0.8,
                "score_parts": {"graph_imports_match": 0.8},
                "reasons": ["static module dependency"],
                "exact_witness": {
                    "relation_id": f"r5:{case_id}",
                    "module_relation_id": f"r5:module:{case_id}",
                    "source_signal_id": f"s5:source:{case_id}",
                    "target_signal_id": f"s5:target:{case_id}",
                    "target_chunk_id": f"chunk:{case_id}",
                    "target_file_path": required_path,
                    "actual_target_kind": "function",
                    "target_start_line": 10,
                "target_end_line": 12,
                },
                "chunk_id": f"chunk:{case_id}",
                "origin_chunk_ids": [f"chunk:{case_id}"],
                "rank_history": [],
                "stage_trajectory": [],
            }
        )
        candidate_cases[case_id]["required"][0].update(rank=2, state="selected")
    base = {
        "corpora": "development",
        "cases": baseline_cases,
        "embedding_requests": {"redink": 1, "daily": 1, "total": 2},
        "index_projections": {},
        "observed": {
            "local_model_calls": 0,
            "planner_calls": 0,
            "fallback_count": 0,
            "error_count": 0,
            "skip_count": 0,
            "retrieval_calls": 3,
        },
        "timing": {
            "index_seconds": {"redink": 1.0, "daily": 1.0},
            "query_case_seconds": {
                "red-case": 0.01,
                "daily-case-one": 0.01,
                "daily-case-two": 0.01,
            },
        },
    }
    cap_values = {
        "max_graph_seed_signals": 512,
        "max_resolved_graph_hops": 4,
        "max_edges_per_signal_direction": 64,
        "max_relation_expanded_candidates": 1000,
        "observed_maximum_outgoing_rows": 8,
        "observed_maximum_incoming_rows": 8,
    }
    for repo, marker in (("redink", "a"), ("daily", "b")):
        target_paths = {
            required_path: [
                {
                    "relation_id": f"r5:{case_id}",
                    "module_relation_id": f"r5:module:{case_id}",
                    "source_signal_id": f"s5:source:{case_id}",
                    "source_chunk_id": f"chunk:anchor:{case_id}",
                    "target_signal_id": f"s5:target:{case_id}",
                    "target_chunk_id": f"chunk:{case_id}",
                    "actual_target_kind": "function",
                }
            ]
            for case_id, case_repo, required_path in specs
            if case_repo == repo
        }
        base["index_projections"][repo] = {
            "module_projection_sha256": marker * 64,
            "non_python_projection_sha256": "f" * 64,
            "work_caps": deepcopy(cap_values),
            "maximum_exact_relations_per_source": 0,
            "exact_targets": {},
            "target_states": {},
        }
    candidate = deepcopy(base)
    candidate["cases"] = candidate_cases
    for repo in ("redink", "daily"):
        candidate["index_projections"][repo]["maximum_exact_relations_per_source"] = 2
        candidate["index_projections"][repo]["exact_targets"] = {
            required_path: [
                {
                    "relation_id": f"r5:{case_id}",
                    "module_relation_id": f"r5:module:{case_id}",
                    "source_signal_id": f"s5:source:{case_id}",
                    "source_chunk_id": f"chunk:anchor:{case_id}",
                    "target_signal_id": f"s5:target:{case_id}",
                    "target_chunk_id": f"chunk:{case_id}",
                    "actual_target_kind": "function",
                }
            ]
            for case_id, case_repo, required_path in specs
            if case_repo == repo
        }
    return base, candidate


def test_oracle_comparison_applies_frozen_r2_and_exact_witness_credit() -> None:
    baseline, candidate = _capture_pair()
    report = acceptance._compare_pair(_manifest(), baseline, candidate)

    assert report["disposition"] == "proceed"
    assert report["micro_recall_delta"] == pytest.approx(0.5)
    assert len(report["new_required_items"]) == 3
    assert set(report["gates"].values()) == {True}


def test_oracle_comparison_rejects_gain_without_exact_target_chunk_witness() -> None:
    baseline, candidate = _capture_pair()
    candidate["cases"]["daily-case-one"]["selected"][1]["exact_witness"] = None

    report = acceptance._compare_pair(_manifest(), baseline, candidate)

    assert report["disposition"] == "reject"
    assert report["gates"]["exact_witness_for_every_new_item"] is False


def test_oracle_comparison_rejects_loss_noise_or_module_drift() -> None:
    baseline, candidate = _capture_pair()
    candidate["cases"]["red-case"]["required"][1].update(rank=None, state="not_selected")
    candidate["cases"]["red-case"]["selected"].append(
        {
            "rank": 3,
            "path": "noise.py",
            "start_line": 1,
            "end_line": 1,
            "score": 0.1,
            "score_parts": {},
            "reasons": [],
            "exact_witness": None,
            "chunk_id": "chunk:noise",
            "origin_chunk_ids": ["chunk:noise"],
            "rank_history": [],
            "stage_trajectory": [],
        }
    )
    candidate["index_projections"]["daily"]["module_projection_sha256"] = "c" * 64

    report = acceptance._compare_pair(_manifest(), baseline, candidate)

    assert report["disposition"] == "reject"
    assert report["gates"]["zero_required_loss"] is False
    assert report["gates"]["zero_noise_growth"] is False
    assert report["gates"]["module_relations_stable"] is False


def test_terminal_state_vocabulary_excludes_p8_relation_slot_credit() -> None:
    assert "relation_slot" not in acceptance._TERMINAL_STATES
    assert "selected_exact_declaration_chunk" in acceptance._TERMINAL_STATES


def test_independent_selector_requires_one_same_unit_target() -> None:
    active = {
        "pkg/source.py": "",
        "pkg/target.py": "",
        "src/pkg/target.py": "",
        "unit/pkg/target.py": "unit",
    }

    state, specifier, target = acceptance._independent_module_selector(
        source_path="pkg/source.py",
        project_unit_key="",
        module="pkg.target",
        relative_level=0,
        active_paths=active,
    )
    assert (state, specifier, target) == ("ambiguous", "pkg.target", None)

    state, specifier, target = acceptance._independent_module_selector(
        source_path="unit/pkg/source.py",
        project_unit_key="unit",
        module="target",
        relative_level=1,
        active_paths=active,
    )
    assert (state, specifier, target) == ("exact", ".target", "unit/pkg/target.py")

    assert acceptance._independent_module_selector(
        source_path="pkg/source.py",
        project_unit_key="",
        module="",
        relative_level=1,
        active_paths=active,
    )[0] == "unresolved"


def test_exact_witness_credit_rejects_fake_ids_or_wrong_chunk() -> None:
    _baseline, candidate = _capture_pair()
    row = candidate["cases"]["red-case"]["selected"][1]
    assert acceptance._valid_exact_selected(row)

    forged = deepcopy(row)
    forged["exact_witness"]["relation_id"] = ""
    assert not acceptance._valid_exact_selected(forged)

    wrong_chunk = deepcopy(row)
    wrong_chunk["exact_witness"]["target_chunk_id"] = "chunk:other"
    assert not acceptance._valid_exact_selected(wrong_chunk)


def test_exact_witness_is_not_attached_without_graph_import_evidence(
    tmp_path: Path,
) -> None:
    assert acceptance._exact_witness(
        tmp_path / "missing.sqlite",
        "pkg/target.py",
        {"score_parts": {}, "reasons": [], "chunk_id": "chunk:target"},
    ) is None


def test_write_new_json_refuses_evidence_overwrite(tmp_path: Path) -> None:
    path = tmp_path / "slot.json"
    acceptance._write_new_json(path, {"value": 1})

    with pytest.raises(ValueError, match="already exists"):
        acceptance._write_new_json(path, {"value": 2})

    assert json.loads(path.read_text(encoding="utf-8")) == {"value": 1}


def test_oracle_exact_relations_have_independent_per_source_256_cap(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "repo"
    database = workspace / ".context-search/index.sqlite"
    database.parent.mkdir(parents=True)
    source = workspace / "pkg/source.py"
    source.parent.mkdir(parents=True)
    names = [f"Name{index:03d}" for index in range(257)]
    source.write_text(
        "from pkg.target import " + ", ".join(names) + "\n",
        encoding="utf-8",
    )
    (workspace / "pkg/target.py").write_text("", encoding="utf-8")
    with sqlite3.connect(database) as connection:
        connection.executescript(
            """
            CREATE TABLE code_signals (
              signal_id TEXT PRIMARY KEY, chunk_id TEXT, file_path TEXT,
              kind TEXT, name TEXT, qualified_name TEXT, signature TEXT,
              arity INTEGER, project_unit_key TEXT, producer TEXT,
              start_line INTEGER, end_line INTEGER, start_column INTEGER,
              end_column INTEGER, language TEXT, recallable INTEGER,
              tokens TEXT, metadata TEXT, deleted_at INTEGER
            );
            CREATE TABLE code_relations (
              relation_id TEXT PRIMARY KEY, source_signal_id TEXT,
              source_chunk_id TEXT, source_file_path TEXT, target_name TEXT,
              kind TEXT, confidence REAL, target_kind TEXT,
              target_qualified_name TEXT, target_signature TEXT,
              target_arity INTEGER, target_project_unit_key TEXT,
              target_signal_id TEXT, resolution TEXT, producer TEXT,
              producer_confidence REAL, resolution_confidence REAL,
              metadata TEXT, deleted_at INTEGER
            );
            CREATE TABLE chunks (
              chunk_id TEXT PRIMARY KEY, file_path TEXT, start_line INTEGER,
              end_line INTEGER, deleted_at INTEGER
            );
            """
        )
        signals = [
            (
                "s5:source",
                "chunk:source",
                "pkg/source.py",
                "module",
                "source.py",
                "pkg/source.py",
                "",
                None,
                "",
                "core_module",
                1,
                1,
                0,
                0,
                "python",
                1,
                "[]",
                "{}",
                None,
            ),
            (
                "s5:module",
                "chunk:module",
                "pkg/target.py",
                "module",
                "target.py",
                "pkg/target.py",
                "",
                None,
                "",
                "core_module",
                1,
                1,
                0,
                0,
                "python",
                1,
                "[]",
                "{}",
                None,
            ),
        ]
        signals.extend(
            (
                f"s5:target:{name}",
                f"chunk:{name}",
                "pkg/target.py",
                "function",
                name,
                f"pkg.target.{name}",
                "",
                None,
                "",
                "python_ast",
                index + 1,
                index + 1,
                0,
                1,
                "python",
                1,
                "[]",
                "{}",
                None,
            )
            for index, name in enumerate(names)
        )
        connection.executemany(
            "INSERT INTO code_signals VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            signals,
        )
        connection.execute(
            "INSERT INTO code_relations VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "r5:module",
                "s5:source",
                "chunk:source",
                "pkg/source.py",
                "pkg.target",
                "imports",
                1.0,
                "module",
                "pkg/target.py",
                "",
                None,
                "",
                "s5:module",
                "resolved_exact",
                "python_ast",
                1.0,
                1.0,
                json.dumps(
                    {
                        "selector_state": "exact",
                        "specifier": "pkg.target",
                        "candidates": ["pkg/target.py"],
                    }
                ),
                None,
            ),
        )
        connection.commit()

    projection = acceptance._overlay_oracle(workspace)

    assert projection["exact_relation_count"] == 256
    assert projection["graph_omitted_imported_symbols"] == 1
    assert projection["maximum_exact_relations_per_source"] == 256
    assert projection["module_relation_count"] == 1
