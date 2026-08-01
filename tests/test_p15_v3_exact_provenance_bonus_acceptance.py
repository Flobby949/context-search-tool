from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

import p15_v3_exact_provenance_bonus_acceptance as acceptance


MANIFEST = Path(__file__).parent / "fixtures/p15_v3_exact_provenance_bonus/input_manifest.json"
RUN_ROOT = Path(__file__).parents[1] / ".quality/p15-runs/p15-v3-attempt-001"
ORIGINAL_ROOT = acceptance.ROOT


def _payload() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def _atom(
    relation_id: str,
    target_file_path: str,
    target_chunk_id: str,
    position: int,
) -> dict:
    return {
        "relation_id": relation_id,
        "source_signal_id": f"source-signal-{relation_id}",
        "source_file_path": "source.py",
        "source_chunk_id": "source-chunk",
        "target_signal_id": f"target-signal-{relation_id}",
        "target_file_path": target_file_path,
        "target_chunk_id": target_chunk_id,
        "relation_kind": "imports",
        "resolution": "resolved_exact",
        "producer": "python_ast",
        "resolution_basis": "exact_python_imported_symbol",
        "ordered_edge_position": position,
    }


def _union(*route_atoms: list[dict]) -> list[dict]:
    keys = {
        tuple(atom[field] for field in acceptance.PROVENANCE_FIELDS)
        for atoms in route_atoms
        for atom in atoms
    }
    return [dict(zip(acceptance.PROVENANCE_FIELDS, values)) for values in sorted(keys)]


def _runtime_evidence() -> dict:
    ineligible_atom = _atom("relation-ineligible", "other.py", "other-chunk", 4)
    winner_atom_a = _atom("relation-winner-a", "winner.py", "winner-origin", 2)
    winner_atom_b = _atom("relation-winner-b", "winner.py", "winner-origin", 3)
    loser_atom = _atom("relation-loser", "loser.py", "loser-origin", 1)
    rows = [
        {
            "candidate_id": "higher-ineligible",
            "chunk_id": "higher-origin",
            "file_path": "higher.py",
            "origin_chunk_ids": ["higher-origin"],
            "merge_inputs": {"candidate": [], "same_chunk": [], "context_overlap": []},
            "provenance_union": [],
            "rerank_score": 1.0,
            "evidence_priority": 0,
            "was_ceiling_clamped": False,
            "pre_ceiling_rerank_score": 1.0,
            "role_priority": 1.0,
            "combined_score": 0.9,
            "start_line": 1,
            "prebonus_position": 1,
            "score_parts": {"existing": 0.4},
            "reasons": ["existing"],
            "stage": acceptance.BONUS_STAGE,
        },
        {
            "candidate_id": "eligible-winner",
            "chunk_id": "winner-origin",
            "file_path": "winner.py",
            "origin_chunk_ids": ["winner-origin"],
            "merge_inputs": {
                "candidate": [winner_atom_a, winner_atom_b],
                "same_chunk": [winner_atom_a, winner_atom_b],
                "context_overlap": [],
            },
            "provenance_union": _union([winner_atom_a, winner_atom_b]),
            "rerank_score": 0.9,
            "evidence_priority": 1,
            "was_ceiling_clamped": True,
            "pre_ceiling_rerank_score": 0.95,
            "role_priority": 2.0,
            "combined_score": 0.8,
            "start_line": 5,
            "prebonus_position": 2,
            "score_parts": {"existing": 0.3},
            "reasons": ["existing"],
            "stage": acceptance.BONUS_STAGE,
        },
        {
            "candidate_id": "eligible-loser",
            "chunk_id": "loser-origin",
            "file_path": "loser.py",
            "origin_chunk_ids": ["loser-origin"],
            "merge_inputs": {"candidate": [loser_atom], "same_chunk": [], "context_overlap": []},
            "provenance_union": _union([loser_atom], [], []),
            "rerank_score": 0.8,
            "evidence_priority": 1,
            "was_ceiling_clamped": False,
            "pre_ceiling_rerank_score": 0.8,
            "role_priority": 2.0,
            "combined_score": 0.7,
            "start_line": 9,
            "prebonus_position": 3,
            "score_parts": {"existing": 0.2},
            "reasons": ["existing"],
            "stage": acceptance.BONUS_STAGE,
        },
    ]
    candidate_ids = [row["candidate_id"] for row in rows]
    inventory = [ineligible_atom, winner_atom_a, winner_atom_b, loser_atom]

    def candidate_projection(chunk_id: str) -> dict:
        return {
            "chunk_id": chunk_id,
            "score": 0.5,
            "source": "relation" if chunk_id != "higher-origin" else "lexical",
            "score_parts": {"relation": 0.5} if chunk_id != "higher-origin" else {"lexical": 0.5},
            "semantic_matches": [],
        }

    def candidate_envelope(chunk_id: str) -> dict:
        return {
            "candidate": candidate_projection(chunk_id),
            "provenance_union": [
                atom for atom in inventory if atom["target_chunk_id"] == chunk_id
            ],
        }

    graph_calls = []
    for call_index, atom in enumerate(inventory):
        returned = [
            f"nonexact-{call_index}-{position}"
            for position in range(1, atom["ordered_edge_position"])
        ]
        returned.append(atom["relation_id"])
        graph_calls.append(
            {
                "call_index": call_index,
                "source_signal_id": atom["source_signal_id"],
                "requested_limit": 65,
                "returned_relation_ids": returned,
                "direct_exact_edges": [atom],
            }
        )
    input_ids = ["higher-origin", "winner-origin", "winner-origin", "loser-origin"]
    inputs = [candidate_envelope(chunk_id) for chunk_id in input_ids]
    outputs = [
        candidate_envelope(chunk_id)
        for chunk_id in ("higher-origin", "winner-origin", "loser-origin")
    ]
    winner_indexes = [1, 2]
    same_group = {
        "chunk_id": "winner-origin",
        "input_indexes": winner_indexes,
        "inputs": [inputs[index] for index in winner_indexes],
        "output": outputs[1],
        "provenance_union": outputs[1]["provenance_union"],
    }
    context_inputs = []
    context_outputs = []
    for row in rows:
        ranked = {
            "chunk_id": row["chunk_id"],
            "file_path": row["file_path"],
            "start_line": row["start_line"],
            "end_line": row["start_line"],
            "score": row["combined_score"],
            "score_parts": row["score_parts"],
            "reasons": row["reasons"],
            "rank_tier": 1,
            "rerank_score": row["rerank_score"],
            "evidence_class": "direct",
            "evidence_priority": row["evidence_priority"],
            "semantic_matches": [],
            "pre_ceiling_rerank_score": row["pre_ceiling_rerank_score"],
            "was_ceiling_clamped": row["was_ceiling_clamped"],
        }
        provenance = [
            atom for atom in inventory if atom["target_chunk_id"] == row["chunk_id"]
        ]
        context_inputs.append({"ranked": ranked, "provenance_union": provenance})
        context_outputs.append(
            {
                "context": {
                    "origin_chunk_ids": [row["chunk_id"]],
                    "file_path": row["file_path"],
                    "start_line": row["start_line"],
                    "end_line": row["start_line"],
                    "score": row["combined_score"],
                    "score_parts": row["score_parts"],
                    "reasons": row["reasons"],
                    "rank_tier": 1,
                    "rerank_score": row["rerank_score"],
                    "evidence_class": "direct",
                    "evidence_priority": row["evidence_priority"],
                    "semantic_matches": [],
                    "pre_ceiling_rerank_score": row["pre_ceiling_rerank_score"],
                    "was_ceiling_clamped": row["was_ceiling_clamped"],
                    "spans": [],
                },
                "provenance_union": provenance,
            }
        )
    boundaries = {
        "overlay_exact_relation_count": len(inventory),
        "graph_outgoing_call_count": len(graph_calls),
        "graph_outgoing_calls": graph_calls,
        "candidate_merge_call_count": 1,
        "candidate_merge_calls": [
            {
                "call_index": 0,
                "inputs": inputs,
                "outputs": outputs,
                "same_chunk_groups": [same_group],
            }
        ],
        "same_chunk_merge_count": 1,
        "context_expansion_call_count": 1,
        "context_expansion_calls": [
            {"call_index": 0, "inputs": context_inputs, "outputs": context_outputs}
        ],
        "context_overlap_merge_call_count": 0,
        "context_overlap_merge_calls": [],
    }
    return {
        "stage": acceptance.BONUS_STAGE,
        "prebonus_input_candidate_ids": candidate_ids,
        "prebonus_input_sha256": acceptance._json_value_sha256(candidate_ids),
        "ordered_edge_inventory": inventory,
        "ordered_edge_inventory_sha256": acceptance._json_value_sha256(inventory),
        "pipeline_boundaries": boundaries,
        "roster": rows,
    }


def _control_capture(repeat: int, input_order: str, pid: int) -> dict:
    return {
        "schema_version": 1,
        "program": "p15-v3",
        "attempt_id": "p15-v3-attempt-001",
        "phase": "task0a_raw_control",
        "query_id": "query-1",
        "case_id": "query-1",
        "case_sha256": "1" * 64,
        "query": "synthetic closed query",
        "query_sha256": acceptance._json_value_sha256("synthetic closed query"),
        "released_payload": {
            "repository_key": "synthetic",
            "path": ".quality/synthetic-released.json",
            "sha256": "2" * 64,
        },
        "source_identity": {
            "repository_key": "synthetic",
            "source_root": ".quality/synthetic-source",
            "repository_identity": "synthetic/repository",
            "url": "https://example.invalid/synthetic.git",
            "commit": "3" * 40,
            "tree": "4" * 40,
            "inventory_sha256": "5" * 64,
            "content_sha256": "6" * 64,
        },
        "repeat": repeat,
        "input_order": input_order,
        "policy_contribution": 0.0,
        "producer": "p15_v3_independent_raw_control_capture",
        "process_identity": {"pid": pid, "invocation_id": f"invocation-{pid}"},
        "privacy": deepcopy(acceptance.CONTROL_PRIVACY),
        "serialization": "canonical_json_sort_keys_compact_utf8_no_trailing_newline",
        "write_policy": "write_new_only_never_overwrite",
        "runtime_visibility": _runtime_evidence(),
    }


def _derived_treatment_output(runtime: dict) -> dict:
    derived = acceptance.validate_raw_control_runtime(runtime)
    rows = {row["candidate_id"]: row for row in runtime["roster"]}
    winner = derived["winner_candidate_id"]
    scores = {
        candidate_id: rows[candidate_id]["rerank_score"]
        + (0.04 if candidate_id == winner else 0.0)
        for candidate_id in derived["prebonus_order"]
    }
    post_order = sorted(
        derived["prebonus_order"],
        key=lambda candidate_id: acceptance._total_order_projection(
            rows[candidate_id], rerank_score_override=scores[candidate_id]
        ),
    )
    return {
        "winner_candidate_id": winner,
        "score_part": acceptance.BONUS_SCORE_PART if winner is not None else None,
        "reason": acceptance.BONUS_REASON if winner is not None else None,
        "bonus": 0.04 if winner is not None else 0.0,
        "postbonus_order": post_order,
        "postbonus_rerank_scores": [
            {"candidate_id": candidate_id, "rerank_score": scores[candidate_id]}
            for candidate_id in post_order
        ],
    }


def _two_phase_fixture() -> tuple[dict, dict[str, dict], dict]:
    matrix = [(1, "canonical"), (1, "reverse"), (2, "canonical"), (2, "reverse")]
    controls: dict[str, dict] = {}
    entries = []
    for offset, (repeat, input_order) in enumerate(matrix, start=1):
        path = f"control-r{repeat}-{input_order}.json"
        control = _control_capture(repeat, input_order, 1000 + offset)
        controls[path] = control
        entries.append(
            {
                "path": path,
                "canonical_sha256": acceptance._json_value_sha256(control),
                "stable_projection_sha256": acceptance._json_value_sha256(
                    control["runtime_visibility"]
                ),
                "repeat": repeat,
                "input_order": input_order,
                "pid": control["process_identity"]["pid"],
                "invocation_id": control["process_identity"]["invocation_id"],
            }
        )
    marker = {
        "schema_version": 1,
        "program": "p15-v3",
        "attempt_id": "p15-v3-attempt-001",
        "phase": "task0a_control_freeze",
        "status": "immutable_control_frozen",
        "immutable": True,
        "required_mode": "0444",
        "query_id": "query-1",
        "policy_contribution": 0.0,
        "producer": "p15_v3_independent_control_freezer",
        "process_identity": {"pid": 1500, "invocation_id": "freeze-invocation"},
        "privacy": deepcopy(acceptance.CONTROL_PRIVACY),
        "serialization": "canonical_json_sort_keys_compact_utf8_no_trailing_newline",
        "write_policy": "write_new_only_never_overwrite",
        "required_matrix": [
            {"repeat": repeat, "input_order": input_order}
            for repeat, input_order in matrix
        ],
        "snapshots": entries,
        "common_stable_projection_sha256": entries[0]["stable_projection_sha256"],
    }
    selected = entries[0]
    treatment = {
        "schema_version": 1,
        "program": "p15-v3",
        "attempt_id": "p15-v3-attempt-001",
        "phase": "task0b_treatment",
        "query_id": "query-1",
        "policy_contribution": 0.04,
        "external_control_seal": {
            "path": acceptance.CONTROL_SEAL_FILENAME,
            "byte_sha256": "0" * 64,
        },
        "raw_control_snapshot": {
            "path": f"{acceptance.CONTROL_DIRECTORY}/{selected['path']}",
            "byte_sha256": selected["canonical_sha256"],
            "canonical_sha256": selected["canonical_sha256"],
            "stable_projection_sha256": selected["stable_projection_sha256"],
        },
        "process_identity": {"pid": 2000, "invocation_id": "treatment-invocation"},
        "producer": "p15_v3_independent_treatment_capture",
        "privacy": deepcopy(acceptance.CONTROL_PRIVACY),
        "write_policy": "write_new_only_never_overwrite",
        "output": _derived_treatment_output(controls[selected["path"]]["runtime_visibility"]),
    }
    return marker, controls, treatment


def _write_immutable_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(acceptance._canonical_json_bytes(payload))
    path.chmod(0o444)


def _replace_immutable_json(path: Path, payload: dict) -> None:
    path.chmod(0o644)
    path.write_bytes(acceptance._canonical_json_bytes(payload))
    path.chmod(0o444)


def _install_phase_a_fault_process_double(monkeypatch) -> None:
    controls_by_case: dict[str, dict[str, dict]] = {}
    next_pid = {"value": 30000}

    class OutputPipe:
        def __init__(self) -> None:
            self.value = b""

        def readline(self) -> bytes:
            value, self.value = self.value, b""
            return value

        def read(self) -> bytes:
            return b""

    class InputPipe:
        def __init__(self, process) -> None:
            self.process = process

        def write(self, raw: bytes) -> int:
            request = json.loads(raw.decode("utf-8"))
            if request == {"command": "release"}:
                self.process.returncode = 0
                return len(raw)
            job = request["job"]
            invocation_id = request["invocation_id"]
            if job["kind"] == "raw_control":
                payload = _control_capture(job["repeat"], job["input_order"], self.process.pid)
                payload.update(
                    {
                        "query_id": job["case_id"],
                        "case_id": job["case_id"],
                        "case_sha256": job["case_sha256"],
                        "query": job["query"],
                        "query_sha256": acceptance._json_value_sha256(job["query"]),
                        "released_payload": {
                            "repository_key": job["repository_key"],
                            "path": job["released_payload_path"],
                            "sha256": job["released_payload_sha256"],
                        },
                        "source_identity": deepcopy(job["source_identity"]),
                        "process_identity": {
                            "pid": self.process.pid,
                            "invocation_id": invocation_id,
                        },
                    }
                )
                controls_by_case.setdefault(job["case_id"], {})[
                    Path(job["run_relative_path"]).name
                ] = payload
            else:
                controls = controls_by_case[job["case_id"]]
                snapshots = [
                    {
                        "path": filename,
                        "canonical_sha256": acceptance._json_value_sha256(controls[filename]),
                        "stable_projection_sha256": acceptance._json_value_sha256(
                            controls[filename]["runtime_visibility"]
                        ),
                        "repeat": controls[filename]["repeat"],
                        "input_order": controls[filename]["input_order"],
                        "pid": controls[filename]["process_identity"]["pid"],
                        "invocation_id": controls[filename]["process_identity"]["invocation_id"],
                    }
                    for filename in acceptance.CONTROL_FILENAMES
                ]
                payload = {
                    "schema_version": 1,
                    "program": "p15-v3",
                    "attempt_id": "p15-v3-attempt-001",
                    "phase": "task0a_control_freeze",
                    "status": "immutable_control_frozen",
                    "immutable": True,
                    "required_mode": "0444",
                    "query_id": job["case_id"],
                    "policy_contribution": 0.0,
                    "producer": "p15_v3_independent_control_freezer",
                    "process_identity": {
                        "pid": self.process.pid,
                        "invocation_id": invocation_id,
                    },
                    "privacy": deepcopy(acceptance.CONTROL_PRIVACY),
                    "serialization": "canonical_json_sort_keys_compact_utf8_no_trailing_newline",
                    "write_policy": "write_new_only_never_overwrite",
                    "required_matrix": [
                        {"repeat": repeat, "input_order": order}
                        for repeat, order in (
                            (1, "canonical"),
                            (1, "reverse"),
                            (2, "canonical"),
                            (2, "reverse"),
                        )
                    ],
                    "snapshots": snapshots,
                    "common_stable_projection_sha256": snapshots[0]["stable_projection_sha256"],
                }
            mutation = os.environ.get("P15_V3_TEST_PRODUCER_MUTATION")
            producer_executed = os.environ.get("P15_V3_TEST_SKIP_PRODUCER") != "1"
            if mutation == "fake_pid":
                payload["process_identity"]["pid"] += 1
            elif mutation == "parent_pid":
                payload["process_identity"]["pid"] = int(os.environ["P15_V3_TEST_PARENT_PID"])
            elif mutation == "query":
                payload["query"] = "relabeled query"
                payload["query_sha256"] = acceptance._json_value_sha256(payload["query"])
            elif mutation == "case":
                payload["query_id"] = payload["case_id"] = "relabeled-case"
            elif mutation == "release":
                payload["released_payload"]["path"] = ".quality/relabeled-release.json"
            elif mutation == "source":
                payload["source_identity"]["content_sha256"] = "0" * 64
            envelope = {
                "job_sha256": acceptance._json_value_sha256(job),
                "producer_executed": producer_executed,
                "payload": payload if producer_executed else {},
            }
            self.process.stdout.value = acceptance._canonical_json_bytes(envelope) + b"\n"
            return len(raw)

        def flush(self) -> None:
            return None

        def close(self) -> None:
            return None

    class ProcessDouble:
        def __init__(self) -> None:
            next_pid["value"] += 1
            self.pid = next_pid["value"]
            self.returncode = None
            self.stdout = OutputPipe()
            self.stderr = OutputPipe()
            self.stdin = InputPipe(self)

        def poll(self):
            return self.returncode

        def wait(self, timeout=None):
            if self.returncode is None:
                self.returncode = 0
            return self.returncode

        def kill(self) -> None:
            self.returncode = -9

    def factory(*_args, **_kwargs):
        return ProcessDouble()

    monkeypatch.setattr(acceptance.subprocess, "Popen", factory)


def _create_tiny_phase_a_source(
    root: Path,
    repository_key: str,
) -> tuple[str, dict]:
    source_relative = f".quality/p15-v3-test-sources/{repository_key}"
    source_root = root / source_relative
    package = f"tiny_{repository_key}"
    package_root = source_root / package
    package_root.mkdir(parents=True)
    (source_root / "LICENSE").write_text("MIT test fixture\n", encoding="utf-8")
    (package_root / "__init__.py").write_text("", encoding="utf-8")
    (package_root / "target.py").write_text(
        "class TinyTarget:\n    pass\n",
        encoding="utf-8",
    )
    consumer_lines = [
        f"from {package}.target import TinyTarget",
        "",
        "def tinyboundary_alpha():",
        "    return TinyTarget()",
        "",
    ]
    consumer_lines.extend(
        f"# tinyboundary deterministic filler {index:03d}" for index in range(90)
    )
    consumer_lines.extend(
        [
            "",
            "def tinyboundary_omega():",
            "    return TinyTarget()",
            "",
        ]
    )
    (package_root / "consumer.py").write_text(
        "\n".join(consumer_lines),
        encoding="utf-8",
    )
    subprocess.run(["git", "init", "-q", str(source_root)], check=True)
    subprocess.run(["git", "-C", str(source_root), "add", "."], check=True)
    subprocess.run(
        [
            "git", "-C", str(source_root),
            "-c", "user.name=P15 Test",
            "-c", "user.email=p15-test@example.invalid",
            "commit", "-q", "-m", "tiny phase-a source",
        ],
        check=True,
    )
    selected = acceptance._select_public_source_inventory(
        source_root,
        [f"{package}/**.py"],
        [],
    )
    contract = {
        "repository_key": repository_key,
        "repository_role": "fresh_test_fixture",
        "url": f"https://example.invalid/{repository_key}.git",
        "commit": subprocess.run(
            ["git", "-C", str(source_root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip(),
        "tree": subprocess.run(
            ["git", "-C", str(source_root), "rev-parse", "HEAD^{tree}"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip(),
        "license_spdx": "MIT",
        "license_path": "LICENSE",
        "license_sha256": acceptance._sha256(source_root / "LICENSE"),
        "include": [f"{package}/**.py"],
        "exclude": [],
        "selected_count": len(selected),
        "inventory_sha256": acceptance._source_inventory_sha256(selected),
        "content_sha256": acceptance._source_content_sha256(source_root, selected),
    }
    return source_relative, contract


def _phase_a_environment(
    tmp_path: Path,
    monkeypatch,
    *,
    name: str = "authorized-repo",
    use_fault_process_double: bool = False,
) -> tuple[
    acceptance.PhaseAControlPlan,
    Path,
    Path,
    Path,
    Path,
]:
    root = tmp_path / name
    (root / ".quality/p15-runs").mkdir(parents=True)
    manifest = _payload()
    manifest["phase_a_control_engine"]["execution_authorized"] = True
    manifest["phase_a_control_engine"]["capture_authorized"] = True
    if use_fault_process_double:
        for released_path, _digest, _size, _identity in acceptance.FRESH_RELEASED_PAYLOADS.values():
            source = ORIGINAL_ROOT / released_path
            target = root / released_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source.read_bytes())
            target.chmod(0o444)
        for slot in manifest["fresh_efficacy"]["slots"]:
            source_identity = {
                key: slot[key]
                for key in (
                    "repository_key",
                    "source_root",
                    "repository_identity",
                    "url",
                    "commit",
                    "tree",
                    "inventory_sha256",
                    "content_sha256",
                )
            }
            _write_immutable_json(
                root / slot["source_root"] / ".p15-v3-test-source-identity.json",
                source_identity,
            )
    else:
        fresh_payloads = {}
        slots = {
            slot["repository_key"]: slot
            for slot in manifest["fresh_efficacy"]["slots"]
        }
        for repository_key in ("httpx", "poetry_core"):
            source_relative, source_contract = _create_tiny_phase_a_source(
                root,
                repository_key,
            )
            released_relative = (
                f".quality/p15-v3-test-releases/{repository_key}.json"
            )
            release = {
                "source": source_contract,
                "cases": [
                    {
                        "id": f"{repository_key}-tiny-{index}",
                        "query": "tinyboundary",
                        "exact_import_witnesses": [],
                        "eligible_missing_required_paths": [],
                    }
                    for index in range(1, 5)
                ],
            }
            release_path = root / released_relative
            _write_immutable_json(release_path, release)
            release_digest = acceptance._sha256(release_path)
            fresh_payloads[repository_key] = (
                released_relative,
                release_digest,
                release_path.stat().st_size,
                f"p15-v3-test-{repository_key}",
            )
            slot = slots[repository_key]
            slot.update(
                {
                    "source_root": source_relative,
                    "repository_identity": f"test/{repository_key}",
                    "url": source_contract["url"],
                    "commit": source_contract["commit"],
                    "tree": source_contract["tree"],
                    "inventory_sha256": source_contract["inventory_sha256"],
                    "content_sha256": source_contract["content_sha256"],
                    "released_payload_sha256": release_digest,
                }
            )
        monkeypatch.setattr(
            acceptance,
            "FRESH_RELEASED_PAYLOADS",
            fresh_payloads,
        )
    manifest_path = root / "tests/fixtures/p15_v3_exact_provenance_bonus/input_manifest.json"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_bytes(acceptance._canonical_json_bytes(manifest))
    monkeypatch.setattr(acceptance, "ROOT", root)
    monkeypatch.setattr(acceptance, "MANIFEST_PATH", manifest_path)
    monkeypatch.setattr(acceptance, "MANIFEST_SHA256", acceptance._sha256(manifest_path))
    if use_fault_process_double:
        _install_phase_a_fault_process_double(monkeypatch)

    run_root = root / manifest["evidence"]["run_root"]
    staging_root = (
        root
        / manifest["phase_a_control_engine"]["trusted_staging"]["namespace"]
        / f"p15-v3-attempt-001-{'a' * 32}"
    )
    plan = acceptance.build_phase_a_control_plan(manifest, require_inert=False)
    return plan, root, manifest_path, run_root, staging_root


def _materialize_runtime(
    tmp_path: Path,
    marker: dict,
    controls: dict[str, dict],
    treatment: dict,
) -> tuple[Path, str, dict]:
    run_root = tmp_path / "run"
    control_directory = run_root / acceptance.CONTROL_DIRECTORY
    for filename in acceptance.CONTROL_FILENAMES:
        _write_immutable_json(control_directory / filename, controls[filename])
    _write_immutable_json(control_directory / acceptance.CONTROL_MARKER_FILENAME, marker)
    seal = acceptance.build_external_control_seal_payload(
        control_directory,
        {"pid": 1750, "invocation_id": "external-review-invocation"},
    )
    seal_sha256 = acceptance._json_value_sha256(seal)
    _write_immutable_json(run_root / acceptance.CONTROL_SEAL_FILENAME, seal)
    selected = seal["files"][0]
    treatment["external_control_seal"] = {
        "path": acceptance.CONTROL_SEAL_FILENAME,
        "byte_sha256": seal_sha256,
    }
    treatment["raw_control_snapshot"] = {
        "path": selected["path"],
        "byte_sha256": selected["byte_sha256"],
        "canonical_sha256": selected["canonical_sha256"],
        "stable_projection_sha256": selected["stable_projection_sha256"],
    }
    treatment["output"] = _derived_treatment_output(
        controls[Path(selected["path"]).name]["runtime_visibility"]
    )
    _write_immutable_json(run_root / acceptance.TREATMENT_FILENAME, treatment)
    return run_root, seal_sha256, seal


def test_skeleton_validates_without_authorizing_capture() -> None:
    result = acceptance.validate_skeleton()

    assert result == {
        "status": "pass",
        "program": "p15-v3",
        "attempt_id": "p15-v3-attempt-001",
        "capture_authorized": False,
        "policy": "B",
        "ablation": [0.0, 0.04],
        "fresh_slots": "sealed_unreleased_capture_unauthorized",
        "click": "conditional_carry_forward_sealed_unopened",
        "v2_artifacts_verified": 10,
        "v2_captures_verified": 8,
    }
    assert not RUN_ROOT.exists()


def test_cli_validate_skeleton_is_read_only() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(acceptance.ROOT / "tests/p15_v3_exact_provenance_bonus_acceptance.py"),
            "validate-skeleton",
        ],
        cwd=acceptance.ROOT,
        text=True,
        capture_output=True,
        check=True,
    )

    assert json.loads(completed.stdout)["status"] == "pass"
    assert not RUN_ROOT.exists()


@pytest.mark.parametrize("command", ["capture", "capture-hash", "online", "oracle"])
def test_all_execution_commands_fail_before_creating_evidence(command: str) -> None:
    completed = subprocess.run(
        [sys.executable, str(acceptance.ROOT / "tests/p15_v3_exact_provenance_bonus_acceptance.py"), command],
        cwd=acceptance.ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 2
    assert "skeleton has no capture path" in completed.stderr
    assert not RUN_ROOT.exists()


def test_phase_a_plan_closes_global_order_and_authorization_before_zero_state_transition(
    tmp_path: Path,
) -> None:
    plan = acceptance.build_phase_a_control_plan(_payload())

    assert isinstance(plan, acceptance.PhaseAControlPlan)
    assert len(plan.raw_control_jobs) == 32
    assert len(plan.freeze_marker_jobs) == 8
    assert [job.global_index for job in plan.raw_control_jobs] == list(range(32))
    assert [job.global_index for job in plan.freeze_marker_jobs] == list(range(32, 40))
    assert [job.kind for job in plan.global_artifact_order] == ["raw_control"] * 32 + [
        "freeze_marker"
    ] * 8

    run_root = tmp_path / "run"
    staging_root = tmp_path / "staging"
    staging_root.mkdir()
    with pytest.raises(
        acceptance.ValidationError,
        match="Phase A execution has not been independently authorized",
    ):
        acceptance.run_phase_a_control_engine(
            acceptance.MANIFEST_PATH,
            run_root=run_root,
            staging_root=staging_root,
        )
    assert not run_root.exists()
    assert list(staging_root.iterdir()) == []
































def test_phase_a_runner_spawns_32_capture_and_8_freezer_processes(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _plan, _root, manifest_path, run_root, staging_root = _phase_a_environment(
        tmp_path,
        monkeypatch,
    )
    arbitrary_cwd = tmp_path / "arbitrary-parent-cwd"
    arbitrary_cwd.mkdir()
    monkeypatch.setenv("PYTHONPATH", ".::tests:src")
    monkeypatch.chdir(arbitrary_cwd)
    original = acceptance.subprocess.Popen
    spawn_count = {"value": 0}

    def observed(*args, **kwargs):
        assert not run_root.exists()
        assert staging_root.exists()
        command = args[0]
        assert Path(command[1]).is_absolute()
        worker_pythonpath = kwargs["env"]["PYTHONPATH"].split(os.pathsep)
        assert worker_pythonpath
        assert all(value and Path(value).is_absolute() for value in worker_pythonpath)
        assert str(ORIGINAL_ROOT / "src") in worker_pythonpath
        spawn_count["value"] += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(acceptance.subprocess, "Popen", observed)

    result = acceptance.run_phase_a_control_engine(
        manifest_path,
        run_root=run_root,
        staging_root=staging_root,
    )

    assert result["raw_controls"] == 32
    assert result["freeze_markers"] == 8
    assert spawn_count["value"] == 40
    payloads = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in run_root.rglob("*.json")
    ]
    identities = [payload["process_identity"] for payload in payloads]
    assert len(payloads) == 40
    assert len({identity["pid"] for identity in identities}) == 40
    assert len({identity["invocation_id"] for identity in identities}) == 40
    assert all(identity["pid"] != os.getpid() for identity in identities)
    raw_payloads = [
        payload for payload in payloads if payload["phase"] == "task0a_raw_control"
    ]
    assert len(raw_payloads) == 32
    for payload in raw_payloads:
        boundaries = payload["runtime_visibility"]["pipeline_boundaries"]
        assert boundaries["graph_outgoing_call_count"] > 0
        assert boundaries["candidate_merge_call_count"] > 0
        assert boundaries["same_chunk_merge_count"] > 0
        assert boundaries["context_expansion_call_count"] == 1
        assert boundaries["context_overlap_merge_call_count"] > 0
        assert any(
            len(output["context"]["origin_chunk_ids"]) > 1
            for call in boundaries["context_expansion_calls"]
            for output in call["outputs"]
        )
    captured_runtime = raw_payloads[0]["runtime_visibility"]
    reordered = deepcopy(captured_runtime)
    graph_call = next(
        call
        for call in reordered["pipeline_boundaries"]["graph_outgoing_calls"]
        if call["direct_exact_edges"]
    )
    edge = graph_call["direct_exact_edges"][0]
    position = edge["ordered_edge_position"] - 1
    graph_call["returned_relation_ids"].insert(position, "forged-before-real-edge")
    with pytest.raises(acceptance.ValidationError, match="reordered|renumbered"):
        acceptance.validate_raw_control_runtime(reordered)

    omitted_call = deepcopy(captured_runtime)
    omitted_call["pipeline_boundaries"]["candidate_merge_calls"].pop(0)
    with pytest.raises(acceptance.ValidationError, match="incomplete|reordered"):
        acceptance.validate_raw_control_runtime(omitted_call)

    forged_route = deepcopy(captured_runtime)
    route_row = next(
        row for row in forged_route["roster"] if row["merge_inputs"]["candidate"]
    )
    route_row["merge_inputs"]["candidate"] = []
    with pytest.raises(acceptance.ValidationError, match="omitted or forged"):
        acceptance.validate_raw_control_runtime(forged_route)

    self_origin = deepcopy(captured_runtime)
    origin_row = next(
        row for row in self_origin["roster"] if len(row["origin_chunk_ids"]) > 1
    )
    origin_row["origin_chunk_ids"] = [origin_row["chunk_id"]]
    with pytest.raises(acceptance.ValidationError, match="actual context expansion"):
        acceptance.validate_raw_control_runtime(self_origin)
    assert not staging_root.exists()
    assert staging_root.parent.is_dir()
    assert list(staging_root.parent.iterdir()) == []


def test_phase_a_preexisting_final_tree_is_untouched_and_no_worker_starts(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _plan, _root, manifest_path, run_root, staging_root = _phase_a_environment(
        tmp_path,
        monkeypatch,
        name="preexisting-final",
    )
    run_root.mkdir()
    sentinel = run_root / "sentinel"
    sentinel.write_bytes(b"preserve")
    original = acceptance.subprocess.Popen
    calls = {"value": 0}

    def observed(*args, **kwargs):
        calls["value"] += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(acceptance.subprocess, "Popen", observed)
    with pytest.raises(acceptance.ValidationError, match="zero-state is not absent"):
        acceptance.run_phase_a_control_engine(
            manifest_path,
            run_root=run_root,
            staging_root=staging_root,
        )
    assert calls["value"] == 0
    assert sentinel.read_bytes() == b"preserve"
    assert not staging_root.parent.exists()


def test_phase_a_exposes_only_the_runner_and_rejects_parent_prebuilt_payloads(
    tmp_path: Path,
    monkeypatch,
) -> None:
    for name in (
        "_authorize_phase_a_execution",
        "_bind_phase_a_worker",
        "_PhaseAWriteCapability",
        "PhaseAControlRunWriter",
        "write_new_phase_a_artifact",
        "execute_phase_a_artifact_sequence",
    ):
        assert not hasattr(acceptance, name)
    assert acceptance.run_phase_a_control_engine.__closure__ is None
    _plan, _root, manifest_path, run_root, staging_root = _phase_a_environment(
        tmp_path,
        monkeypatch,
    )
    with pytest.raises(TypeError, match="artifacts"):
        acceptance.run_phase_a_control_engine(
            manifest_path,
            run_root=run_root,
            staging_root=staging_root,
            artifacts=[{"parent": "prebuilt"}],
        )
    forged = type("ForgedCapability", (), {})()
    object.__setattr__(forged, "staging_fd", -1)
    with pytest.raises(TypeError, match="capability"):
        acceptance.run_phase_a_control_engine(
            manifest_path,
            run_root=run_root,
            staging_root=staging_root,
            capability=forged,
        )
    with pytest.raises(acceptance.ValidationError, match="exact manifest path"):
        acceptance.run_phase_a_control_engine(
            manifest_path,
            run_root=run_root.parent / "arbitrary-root",
            staging_root=staging_root,
        )
    assert not run_root.exists()
    assert not staging_root.parent.exists()


@pytest.mark.parametrize(
    "mutation, message",
    [
        ("fake_pid", "pid or nonce"),
        ("parent_pid", "pid or nonce"),
        ("query", "job/query/case/release/source"),
        ("case", "job/query/case/release/source"),
        ("release", "job/query/case/release/source"),
        ("source", "job/query/case/release/source"),
    ],
)
def test_phase_a_rejects_child_identity_and_job_relabel_attacks(
    tmp_path: Path,
    monkeypatch,
    mutation: str,
    message: str,
) -> None:
    _plan, _root, manifest_path, run_root, staging_root = _phase_a_environment(
        tmp_path,
        monkeypatch,
        use_fault_process_double=True,
    )
    monkeypatch.setenv("P15_V3_TEST_PRODUCER_MUTATION", mutation)
    monkeypatch.setenv("P15_V3_TEST_PARENT_PID", str(os.getpid()))
    spawned = []
    original_popen = acceptance.subprocess.Popen

    def recording_popen(*args, **kwargs):
        process = original_popen(*args, **kwargs)
        spawned.append(process)
        return process

    monkeypatch.setattr(acceptance.subprocess, "Popen", recording_popen)
    with pytest.raises(acceptance.ValidationError, match=message):
        acceptance.run_phase_a_control_engine(
            manifest_path,
            run_root=run_root,
            staging_root=staging_root,
        )
    assert len(spawned) == 1
    assert all(process.poll() is not None for process in spawned)
    assert not staging_root.exists()
    assert not staging_root.parent.exists()


def test_phase_a_rejects_child_that_did_not_execute_producer(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _plan, _root, manifest_path, run_root, staging_root = _phase_a_environment(
        tmp_path,
        monkeypatch,
        use_fault_process_double=True,
    )
    monkeypatch.setenv("P15_V3_TEST_SKIP_PRODUCER", "1")
    with pytest.raises(acceptance.ValidationError, match="did not execute"):
        acceptance.run_phase_a_control_engine(
            manifest_path,
            run_root=run_root,
            staging_root=staging_root,
        )
    assert not staging_root.exists()
    assert not staging_root.parent.exists()


@pytest.mark.parametrize(
    "target",
    ["staging_leaf", "namespace", "leaf_mode", "namespace_mode", "third_output"],
)
def test_phase_a_captured_dirfds_contain_path_and_object_setattr_attacks(
    tmp_path: Path,
    monkeypatch,
    target: str,
) -> None:
    _plan, _root, manifest_path, run_root, staging_root = _phase_a_environment(
        tmp_path,
        monkeypatch,
        use_fault_process_double=True,
    )
    outside = tmp_path / "outside"
    outside.mkdir()
    sentinel = outside / "sentinel"
    sentinel.write_bytes(b"do-not-touch")
    original_popen = acceptance.subprocess.Popen
    attacked = False

    class ForgedCapability:
        pass

    forged = ForgedCapability()
    object.__setattr__(forged, "staging_root", outside)
    object.__setattr__(forged, "staging_fd", -1)

    def attack_before_spawn(*args, **kwargs):
        nonlocal attacked
        if not attacked:
            attacked = True
            if target == "staging_leaf":
                captured = staging_root.with_name("captured-staging-inode")
                staging_root.rename(captured)
                staging_root.symlink_to(outside, target_is_directory=True)
            else:
                namespace = staging_root.parent
                if target == "namespace":
                    captured = namespace.with_name("captured-namespace-inode")
                    namespace.rename(captured)
                    namespace.symlink_to(outside, target_is_directory=True)
                elif target == "leaf_mode":
                    staging_root.chmod(0o755)
                elif target == "namespace_mode":
                    namespace.chmod(0o755)
                else:
                    (namespace / "third-output").symlink_to(outside, target_is_directory=True)
        return original_popen(*args, **kwargs)

    monkeypatch.setattr(acceptance.subprocess, "Popen", attack_before_spawn)
    with pytest.raises(
        acceptance.ValidationError,
        match="staging mutation|trusted fd path|mode changed|namespace inventory",
    ):
        acceptance.run_phase_a_control_engine(
            manifest_path,
            run_root=run_root,
            staging_root=staging_root,
        )
    assert sentinel.read_bytes() == b"do-not-touch"
    assert not staging_root.exists()
    assert not staging_root.parent.is_symlink()
    if target == "namespace":
        assert not staging_root.parent.with_name("captured-namespace-inode").exists()
    else:
        assert not staging_root.parent.exists()


def test_phase_a_real_producer_runs_overlay_index_retrieval_graph_and_full_roster(
    tmp_path: Path,
    monkeypatch,
) -> None:
    job = acceptance.build_phase_a_control_plan(_payload()).raw_control_jobs[0]
    staging = tmp_path / "attempt-tree"
    staging.mkdir(mode=0o700)
    staging_fd = os.open(staging, os.O_RDONLY | os.O_DIRECTORY)
    try:
        runtime = acceptance._phase_a_real_runtime(
            job,
            ORIGINAL_ROOT,
            staging_fd,
            "a" * 32,
        )
        derived = acceptance.validate_raw_control_runtime(runtime)

        assert len(runtime["roster"]) > 12
        assert runtime["ordered_edge_inventory"]
        assert derived["eligible_candidate_ids"]
        assert derived["winner_candidate_id"] is not None
        boundaries = runtime["pipeline_boundaries"]
        assert boundaries["graph_outgoing_call_count"] > 0
        assert boundaries["candidate_merge_call_count"] > 0
        assert boundaries["context_expansion_call_count"] == 1
        assert list(staging.iterdir()) == []
        assert not RUN_ROOT.exists()

        reverse_job = acceptance.build_phase_a_control_plan(_payload()).raw_control_jobs[1]
        reverse_runtime = acceptance._phase_a_real_runtime(
            reverse_job,
            ORIGINAL_ROOT,
            staging_fd,
            "b" * 32,
        )
        assert reverse_runtime == runtime

        oracle = acceptance.importlib.import_module("p15_python_import_symbol_acceptance")
        monkeypatch.setattr(
            oracle,
            "_overlay_oracle",
            lambda _workspace: {"exact_relation_count": 0},
        )
        with pytest.raises(
            acceptance.ValidationError,
            match="overlay produced no exact relations",
        ):
            acceptance._phase_a_real_runtime(
                job,
                ORIGINAL_ROOT,
                staging_fd,
                "c" * 32,
            )
        assert list(staging.iterdir()) == []
        assert set(tmp_path.iterdir()) == {staging}
        assert "tempfile.mkdtemp" not in Path(acceptance.__file__).read_text(
            encoding="utf-8"
        )
    finally:
        os.close(staging_fd)


def test_phase_a_recovery_release_all_eight_cases_run_in_real_raw_children(
    tmp_path: Path,
    monkeypatch,
) -> None:
    plan = acceptance.build_phase_a_control_plan(_payload())
    jobs = [query.raw_control_jobs[0] for query in plan.queries]
    assert len(jobs) == 8
    assert all(job.repeat == 1 and job.input_order == "canonical" for job in jobs)

    arbitrary_cwd = tmp_path / "unrelated-cwd"
    arbitrary_cwd.mkdir()
    staging = tmp_path / "recovery-attempt-tree"
    staging.mkdir(mode=0o700)
    monkeypatch.setenv("PYTHONPATH", "")
    monkeypatch.chdir(arbitrary_cwd)
    repository_fd = acceptance._open_absolute_directory_chain(ORIGINAL_ROOT)
    staging_fd = os.open(staging, os.O_RDONLY | os.O_DIRECTORY)
    overlap_counts = []
    try:
        for index, job in enumerate(jobs):
            command, environment = acceptance._phase_a_worker_subprocess_spec(
                ORIGINAL_ROOT,
                repository_fd,
                staging_fd,
            )
            assert Path(command[1]).is_absolute()
            assert all(
                value and Path(value).is_absolute()
                for value in environment["PYTHONPATH"].split(os.pathsep)
            )
            process = subprocess.Popen(
                command,
                cwd=arbitrary_cwd,
                env=environment,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                pass_fds=(repository_fd, staging_fd),
            )
            try:
                assert process.stdin is not None and process.stdout is not None
                invocation_id = f"{index + 1:032x}"
                process.stdin.write(
                    acceptance._canonical_json_bytes(
                        {
                            "job": acceptance.asdict(job),
                            "invocation_id": invocation_id,
                        }
                    )
                    + b"\n"
                )
                process.stdin.flush()
                line = process.stdout.readline()
                if not line:
                    stderr = b"" if process.stderr is None else process.stderr.read()
                    pytest.fail(stderr.decode(errors="replace"))
                envelope = json.loads(line)
                assert envelope["producer_executed"] is True
                assert envelope["job_sha256"] == acceptance._json_value_sha256(
                    acceptance.asdict(job)
                )
                payload = envelope["payload"]
                derived = acceptance.validate_raw_control_capture(payload)
                assert derived["eligible_candidate_ids"]
                assert derived["winner_candidate_id"] is not None
                boundaries = payload["runtime_visibility"]["pipeline_boundaries"]
                assert boundaries["overlay_exact_relation_count"] > 0
                assert boundaries["graph_outgoing_call_count"] > 0
                assert boundaries["candidate_merge_call_count"] > 0
                assert boundaries["same_chunk_merge_count"] > 0
                assert boundaries["context_expansion_call_count"] == 1
                overlap_counts.append(boundaries["context_overlap_merge_call_count"])

                release = json.loads(
                    (ORIGINAL_ROOT / job.released_payload_path).read_text(
                        encoding="utf-8"
                    )
                )
                selected_case = next(
                    case for case in release["cases"] if case["id"] == job.case_id
                )
                assert selected_case["exact_import_witnesses"]
                assert selected_case["eligible_missing_required_paths"]
                assert list(staging.iterdir()) == []

                process.stdin.write(b'{"command":"release"}\n')
                process.stdin.flush()
                process.stdin.close()
                assert process.wait(timeout=5) == 0
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=5)
        assert all(count > 0 for count in overlap_counts)
        assert list(staging.iterdir()) == []
        assert set(tmp_path.iterdir()) == {arbitrary_cwd, staging}
    finally:
        os.close(staging_fd)
        os.close(repository_fd)


def test_phase_a_runner_failure_reaps_workers_and_removes_staging(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _plan, _root, manifest_path, run_root, staging_root = _phase_a_environment(
        tmp_path,
        monkeypatch,
        use_fault_process_double=True,
    )
    spawned = []
    original_popen = acceptance.subprocess.Popen

    def recording_popen(*args, **kwargs):
        process = original_popen(*args, **kwargs)
        spawned.append(process)
        return process

    monkeypatch.setattr(acceptance.subprocess, "Popen", recording_popen)
    monkeypatch.setenv("P15_V3_TEST_PRODUCER_MUTATION", "query")
    with pytest.raises(acceptance.ValidationError, match="job/query/case/release/source"):
        acceptance.run_phase_a_control_engine(
            manifest_path,
            run_root=run_root,
            staging_root=staging_root,
        )
    assert len(spawned) == 1
    assert all(process.poll() is not None for process in spawned)
    assert not staging_root.exists()
    assert not staging_root.parent.exists()


@pytest.mark.parametrize(
    "fault",
    [
        "worker_2",
        "write_2",
        "fsync_5",
        "readback_2",
        "chmod_2",
        "link_2",
        "unlink_2",
        "rename",
        "postpublish",
        "post_stage_fsync",
    ],
)
def test_phase_a_whole_tree_faults_rollback_and_retry_cleanly(
    tmp_path: Path,
    monkeypatch,
    fault: str,
) -> None:
    _plan, _root, manifest_path, run_root, staging_root = _phase_a_environment(
        tmp_path,
        monkeypatch,
        name=f"fault-{fault}",
        use_fault_process_double=True,
    )
    restore = None
    if fault == "worker_2":
        original = acceptance.subprocess.Popen
        calls = {"value": 0}

        def injected(*args, **kwargs):
            calls["value"] += 1
            if calls["value"] == 2:
                raise OSError("injected second worker failure")
            return original(*args, **kwargs)

        monkeypatch.setattr(acceptance.subprocess, "Popen", injected)
        restore = lambda: monkeypatch.setattr(acceptance.subprocess, "Popen", original)
    elif fault in {"write_2", "readback_2"}:
        attribute = "_write_all_fd" if fault == "write_2" else "_read_all_fd"
        original = getattr(acceptance, attribute)
        calls = {"value": 0}

        def injected(*args, **kwargs):
            calls["value"] += 1
            if calls["value"] == 2:
                raise OSError(f"injected {attribute} failure")
            return original(*args, **kwargs)

        monkeypatch.setattr(acceptance, attribute, injected)
        restore = lambda: monkeypatch.setattr(acceptance, attribute, original)
    elif fault in {"fsync_5", "post_stage_fsync"}:
        original = acceptance.os.fsync
        calls = {"value": 0}

        def injected(descriptor):
            calls["value"] += 1
            if (
                (fault == "fsync_5" and calls["value"] == 5)
                or (fault == "post_stage_fsync" and run_root.exists())
            ):
                raise OSError("injected fsync failure")
            return original(descriptor)

        monkeypatch.setattr(acceptance.os, "fsync", injected)
        restore = lambda: monkeypatch.setattr(acceptance.os, "fsync", original)
    elif fault == "chmod_2":
        original = acceptance.os.fchmod
        calls = {"value": 0}

        def injected(*args, **kwargs):
            calls["value"] += 1
            if calls["value"] == 2:
                raise OSError("injected chmod failure")
            return original(*args, **kwargs)

        monkeypatch.setattr(acceptance.os, "fchmod", injected)
        restore = lambda: monkeypatch.setattr(acceptance.os, "fchmod", original)
    elif fault in {"link_2", "unlink_2"}:
        attribute = "link" if fault == "link_2" else "unlink"
        original = getattr(acceptance.os, attribute)
        calls = {"value": 0}

        def injected(*args, **kwargs):
            calls["value"] += 1
            if calls["value"] == 2:
                raise OSError(f"injected {attribute} failure")
            return original(*args, **kwargs)

        monkeypatch.setattr(acceptance.os, attribute, injected)
        restore = lambda: monkeypatch.setattr(acceptance.os, attribute, original)
    else:
        original = acceptance._atomic_rename_directory_noreplace

        def injected(*args, **kwargs):
            if fault == "postpublish":
                original(*args, **kwargs)
            raise OSError(f"injected {fault} failure")

        monkeypatch.setattr(
            acceptance,
            "_atomic_rename_directory_noreplace",
            injected,
        )
        restore = lambda: monkeypatch.setattr(
            acceptance,
            "_atomic_rename_directory_noreplace",
            original,
        )

    with pytest.raises(Exception, match="injected|failure-atomic|publication|worker"):
        acceptance.run_phase_a_control_engine(
            manifest_path,
            run_root=run_root,
            staging_root=staging_root,
        )
    assert not run_root.exists()
    assert not staging_root.exists()
    assert not staging_root.parent.exists()

    restore()
    result = acceptance.run_phase_a_control_engine(
        manifest_path,
        run_root=run_root,
        staging_root=staging_root,
    )
    assert result["artifacts"] == 40
    assert len(list(run_root.rglob("*.json"))) == 40
    assert staging_root.parent.is_dir()
    assert list(staging_root.parent.iterdir()) == []


def test_phase_a_postpublish_swap_removes_substitute_and_original_then_retries(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _plan, _root, manifest_path, run_root, staging_root = _phase_a_environment(
        tmp_path,
        monkeypatch,
        name="postpublish-swap",
        use_fault_process_double=True,
    )
    outside = tmp_path / "outside-postpublish"
    outside.mkdir()
    sentinel = outside / "sentinel"
    sentinel.write_bytes(b"untouched")
    moved_name = "p15-v3-swapped-original"
    original = acceptance._atomic_rename_directory_noreplace

    def publish_then_swap(
        source_parent_fd,
        source_name,
        target_parent_fd,
        target_name,
    ):
        original(
            source_parent_fd,
            source_name,
            target_parent_fd,
            target_name,
        )
        os.rename(
            target_name,
            moved_name,
            src_dir_fd=target_parent_fd,
            dst_dir_fd=target_parent_fd,
        )
        os.symlink(
            outside,
            target_name,
            target_is_directory=True,
            dir_fd=target_parent_fd,
        )
        raise OSError("injected postpublish inode swap")

    monkeypatch.setattr(
        acceptance,
        "_atomic_rename_directory_noreplace",
        publish_then_swap,
    )
    with pytest.raises(
        acceptance.ValidationError,
        match="atomic no-overwrite directory publication failed",
    ):
        acceptance.run_phase_a_control_engine(
            manifest_path,
            run_root=run_root,
            staging_root=staging_root,
        )
    assert sentinel.read_bytes() == b"untouched"
    assert not run_root.exists()
    assert not (run_root.parent / moved_name).exists()
    assert not staging_root.exists()
    assert not staging_root.parent.exists()

    monkeypatch.setattr(
        acceptance,
        "_atomic_rename_directory_noreplace",
        original,
    )
    result = acceptance.run_phase_a_control_engine(
        manifest_path,
        run_root=run_root,
        staging_root=staging_root,
    )
    assert result["artifacts"] == 40
    assert len(list(run_root.rglob("*.json"))) == 40
    assert sentinel.read_bytes() == b"untouched"
    assert list(staging_root.parent.iterdir()) == []


def test_phase_a_run_parent_swap_rolls_back_without_writing_outside(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _plan, _root, manifest_path, run_root, staging_root = _phase_a_environment(
        tmp_path,
        monkeypatch,
        name="run-parent-swap",
        use_fault_process_double=True,
    )
    outside = tmp_path / "outside-run-parent"
    outside.mkdir()
    sentinel = outside / "sentinel"
    sentinel.write_bytes(b"untouched")
    original = acceptance.subprocess.Popen
    attacked = {"value": False}

    def injected(*args, **kwargs):
        if not attacked["value"]:
            attacked["value"] = True
            captured = run_root.parent.with_name("captured-run-parent")
            run_root.parent.rename(captured)
            run_root.parent.symlink_to(outside, target_is_directory=True)
        return original(*args, **kwargs)

    monkeypatch.setattr(acceptance.subprocess, "Popen", injected)
    with pytest.raises(acceptance.ValidationError, match="trusted fd path|identity"):
        acceptance.run_phase_a_control_engine(
            manifest_path,
            run_root=run_root,
            staging_root=staging_root,
        )
    assert sentinel.read_bytes() == b"untouched"
    assert not (outside / run_root.name).exists()






@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: value["policy"].__setitem__("name", "A"),
        lambda value: value["policy"].__setitem__("policy_a", "allowed"),
        lambda value: value["policy"].__setitem__("ablation_values", [0.0, 0.03, 0.04]),
        lambda value: value["policy"].__setitem__("aggregation", "sum"),
        lambda value: value["policy"].__setitem__("score_part", "graph_exact_import_provenance_bonus"),
        lambda value: value["policy"].__setitem__("reason", "exact imported-symbol provenance"),
        lambda value: value["policy"].__setitem__("propagation", "allow_graph_hops"),
        lambda value: value["policy"]["existing_total_order"].pop(),
        lambda value: value["policy"].__setitem__("winner_order", "postbonus_rank"),
        lambda value: value["policy"].__setitem__("stage", "after_final_selection"),
        lambda value: value["frozen_nonchanges"].__setitem__("top_k", 13),
        lambda value: value["frozen_nonchanges"].__setitem__("relation_slots", 3),
        lambda value: value["frozen_nonchanges"].__setitem__("definition_owner_behavior", "changed"),
        lambda value: value["frozen_nonchanges"].__setitem__("imports_relation_weight", 0.86),
        lambda value: value["frozen_nonchanges"].__setitem__("graph_decay", 0.81),
        lambda value: value["frozen_nonchanges"]["caps"].__setitem__("maximum_edges_per_signal_direction", 65),
    ],
)
def test_policy_or_frozen_nonchange_mutations_fail_closed(mutate) -> None:
    payload = deepcopy(_payload())
    mutate(payload)

    with pytest.raises(acceptance.ValidationError):
        acceptance._validate_policy_and_nonchanges(payload)


def test_structure_closed_allows_only_the_exact_equation() -> None:
    daily = _payload()["legacy_protected"]["sources"]["daily"]["structure_projection"]
    acceptance.validate_structure_closed(
        daily["baseline"],
        daily["oracle"],
        1193,
        expected_relation_buckets={"imports:external", "imports:resolved_exact", "tests:resolved_exact"},
        expected_signal_producers={"core_module", "python_ast"},
    )

    changed = deepcopy(daily)
    changed["oracle"]["selected_files"] += 1
    with pytest.raises(acceptance.ValidationError, match="selected files"):
        acceptance.validate_structure_closed(
            changed["baseline"], changed["oracle"], 1193,
            expected_relation_buckets={"imports:external", "imports:resolved_exact", "tests:resolved_exact"},
            expected_signal_producers={"core_module", "python_ast"},
        )
    changed = deepcopy(daily)
    del changed["oracle"]["non_relation_fields"]["signals_by_producer"]["python_ast"]
    with pytest.raises(acceptance.ValidationError, match="non-relation structure|producer key set"):
        acceptance.validate_structure_closed(
            changed["baseline"], changed["oracle"], 1193,
            expected_relation_buckets={"imports:external", "imports:resolved_exact", "tests:resolved_exact"},
            expected_signal_producers={"core_module", "python_ast"},
        )
    changed = deepcopy(daily)
    del changed["baseline"]["relation_buckets"]["tests:resolved_exact"]
    del changed["oracle"]["relation_buckets"]["tests:resolved_exact"]
    with pytest.raises(acceptance.ValidationError, match="relation bucket set"):
        acceptance.validate_structure_closed(
            changed["baseline"], changed["oracle"], 1193,
            expected_relation_buckets={"imports:external", "imports:resolved_exact", "tests:resolved_exact"},
            expected_signal_producers={"core_module", "python_ast"},
        )
    changed = deepcopy(daily)
    changed["oracle"]["module_projection_sha256"] = "0" * 64
    with pytest.raises(acceptance.ValidationError, match="module projection"):
        acceptance.validate_structure_closed(
            changed["baseline"], changed["oracle"], 1193,
            expected_relation_buckets={"imports:external", "imports:resolved_exact", "tests:resolved_exact"},
            expected_signal_producers={"core_module", "python_ast"},
        )
    changed = deepcopy(daily)
    changed["oracle"]["non_python_projection_sha256"] = "0" * 64
    with pytest.raises(acceptance.ValidationError, match="non-Python projection"):
        acceptance.validate_structure_closed(
            changed["baseline"], changed["oracle"], 1193,
            expected_relation_buckets={"imports:external", "imports:resolved_exact", "tests:resolved_exact"},
            expected_signal_producers={"core_module", "python_ast"},
        )
    changed = deepcopy(daily)
    changed["oracle"]["relation_buckets"]["imports:external"] += 1
    with pytest.raises(acceptance.ValidationError, match="relation bucket changed"):
        acceptance.validate_structure_closed(
            changed["baseline"], changed["oracle"], 1193,
            expected_relation_buckets={"imports:external", "imports:resolved_exact", "tests:resolved_exact"},
            expected_signal_producers={"core_module", "python_ast"},
        )
    changed = deepcopy(daily)
    changed["oracle"]["relation_buckets"]["imports:resolved_exact"] -= 1
    with pytest.raises(acceptance.ValidationError, match="equation"):
        acceptance.validate_structure_closed(
            changed["baseline"], changed["oracle"], 1193,
            expected_relation_buckets={"imports:external", "imports:resolved_exact", "tests:resolved_exact"},
            expected_signal_producers={"core_module", "python_ast"},
        )


def test_frozen_cap_constants_require_direct_equality() -> None:
    acceptance.validate_cap_constants(acceptance.FROZEN_CAPS, acceptance.FROZEN_CAPS)
    changed = dict(acceptance.FROZEN_CAPS)
    changed["maximum_edges_per_signal_direction"] = 65

    with pytest.raises(acceptance.ValidationError, match="cap constants"):
        acceptance.validate_cap_constants(acceptance.FROZEN_CAPS, changed)


@pytest.mark.parametrize(
    ("baseline", "oracle", "maximum"),
    [(24, 38, 16), (28, 51, 27), (10, 13, 5)],
)
def test_legacy_degree_deltas_remain_bounded(baseline: int, oracle: int, maximum: int) -> None:
    acceptance.validate_degree_delta(baseline, oracle, maximum)


def test_daily_44_to_108_binds_64_real_edges_and_real_position_65_negative() -> None:
    snapshot = _payload()["legacy_protected"]["sources"]["daily"]["saturation_snapshot"]
    acceptance.validate_degree_delta(44, 108, 64)
    acceptance.validate_daily_saturation_snapshot(snapshot)

    assert len(snapshot["ordered_edges"]) == 64
    assert snapshot["position_65_negative"]["edge_identity"] == snapshot["ordered_edges"][-1]["edge_identity"]
    changed = deepcopy(snapshot)
    changed["ordered_edges"][20]["edge_identity"] = "r5:" + "0" * 64
    with pytest.raises(acceptance.ValidationError, match="immutable evidence"):
        acceptance.validate_daily_saturation_snapshot(changed)
    changed = deepcopy(snapshot)
    changed["ordered_edges"][-1]["position"] = 65
    with pytest.raises(acceptance.ValidationError, match="1..64"):
        acceptance.validate_daily_saturation_snapshot(changed)
    changed = deepcopy(snapshot)
    changed["identity_projection_sha256"] = "0" * 64
    with pytest.raises(acceptance.ValidationError, match="projection digest"):
        acceptance.validate_daily_saturation_snapshot(changed)
    with pytest.raises(acceptance.ValidationError, match="degree delta"):
        acceptance.validate_degree_delta(44, 109, 64)


def test_raw_control_derives_union_eligibility_and_winner_without_bonus() -> None:
    runtime = _runtime_evidence()

    assert acceptance.validate_raw_control_runtime(runtime) == {
        "winner_candidate_id": "eligible-winner",
        "eligible_candidate_ids": ["eligible-winner", "eligible-loser"],
        "prebonus_order": ["higher-ineligible", "eligible-winner", "eligible-loser"],
    }
    winner = runtime["roster"][1]
    assert len(winner["merge_inputs"]["candidate"]) + len(winner["merge_inputs"]["same_chunk"]) + len(winner["merge_inputs"]["context_overlap"]) == 4
    assert len(winner["provenance_union"]) == 2
    assert acceptance.BONUS_SCORE_PART not in winner["score_parts"]
    assert acceptance.BONUS_REASON not in winner["reasons"]


def test_two_phase_control_freeze_external_seal_then_treatment_passes(tmp_path: Path) -> None:
    marker, controls, treatment = _two_phase_fixture()
    run_root, seal_sha256, _seal = _materialize_runtime(tmp_path, marker, controls, treatment)

    assert acceptance.validate_two_phase_runtime(
        run_root,
        manifest_bound_control_seal_sha256=seal_sha256,
    ) == "eligible-winner"
    assert treatment["output"]["score_part"] == "exact_imported_symbol"
    assert treatment["output"]["reason"] == "exact imported symbol dependency"
    assert set(treatment).isdisjoint(
        {"candidate_roster", "ordered_edge_inventory", "merge_inputs", "provenance_union", "eligibility", "prebonus_order"}
    )


def test_two_phase_empty_eligible_set_has_no_winner_or_bonus(tmp_path: Path) -> None:
    marker, controls, treatment = _two_phase_fixture()
    for control in controls.values():
        runtime = control["runtime_visibility"]
        runtime["ordered_edge_inventory"] = []
        runtime["ordered_edge_inventory_sha256"] = acceptance._json_value_sha256([])
        boundaries = runtime["pipeline_boundaries"]
        for call in boundaries["graph_outgoing_calls"]:
            call["direct_exact_edges"] = []
        for call in boundaries["candidate_merge_calls"]:
            for envelope in [*call["inputs"], *call["outputs"]]:
                envelope["provenance_union"] = []
            for group in call["same_chunk_groups"]:
                group["provenance_union"] = []
                for envelope in [*group["inputs"], group["output"]]:
                    envelope["provenance_union"] = []
        for call in boundaries["context_expansion_calls"]:
            for envelope in [*call["inputs"], *call["outputs"]]:
                envelope["provenance_union"] = []
        for call in boundaries["context_overlap_merge_calls"]:
            for side in ("left", "right", "output"):
                call[side]["provenance_union"] = []
        for row in runtime["roster"]:
            row["merge_inputs"] = {
                route: [] for route in acceptance.MERGE_ROUTES
            }
            row["provenance_union"] = []
    for entry in marker["snapshots"]:
        control = controls[entry["path"]]
        entry["canonical_sha256"] = acceptance._json_value_sha256(control)
        entry["stable_projection_sha256"] = acceptance._json_value_sha256(control["runtime_visibility"])
    marker["common_stable_projection_sha256"] = marker["snapshots"][0]["stable_projection_sha256"]
    run_root, seal_sha256, _seal = _materialize_runtime(tmp_path, marker, controls, treatment)

    assert acceptance.validate_two_phase_runtime(
        run_root,
        manifest_bound_control_seal_sha256=seal_sha256,
    ) is None
    assert treatment["output"]["score_part"] is None
    assert treatment["output"]["reason"] is None
    assert treatment["output"]["bonus"] == 0.0


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: value["runtime_visibility"]["roster"][1]["score_parts"].__setitem__(acceptance.BONUS_SCORE_PART, 0.04),
        lambda value: value["runtime_visibility"]["roster"][1]["reasons"].append(acceptance.BONUS_REASON),
        lambda value: value["runtime_visibility"]["roster"][1]["merge_inputs"]["candidate"][0].__setitem__("producer", "graph_propagation"),
        lambda value: value["runtime_visibility"]["roster"][1]["merge_inputs"]["candidate"][0].__setitem__("ordered_edge_position", 65),
        lambda value: value["runtime_visibility"]["ordered_edge_inventory"][0].__setitem__("target_chunk_id", "forged-target"),
        lambda value: value["runtime_visibility"].__setitem__("ordered_edge_inventory_sha256", "0" * 64),
        lambda value: value["runtime_visibility"]["roster"][1]["provenance_union"].pop(),
        lambda value: value["runtime_visibility"]["roster"].pop(1),
        lambda value: value["runtime_visibility"]["roster"][1].__setitem__("prebonus_position", 3),
        lambda value: value["privacy"].__setitem__("click_accessed", True),
        lambda value: value.__setitem__("write_policy", "overwrite"),
        lambda value: value.__setitem__("policy_contribution", 0.04),
    ],
)
def test_raw_control_schema_privacy_and_runtime_mutations_fail_closed(mutate) -> None:
    control = _control_capture(1, "canonical", 1001)
    mutate(control)

    with pytest.raises(acceptance.ValidationError):
        acceptance.validate_raw_control_capture(control)


def test_treatment_cannot_self_report_inputs_or_reuse_any_gate_process(tmp_path: Path) -> None:
    marker, controls, treatment = _two_phase_fixture()
    run_root, seal_sha256, seal = _materialize_runtime(tmp_path, marker, controls, treatment)

    injected = deepcopy(treatment)
    injected["candidate_roster"] = []
    _replace_immutable_json(run_root / acceptance.TREATMENT_FILENAME, injected)
    with pytest.raises(acceptance.ValidationError, match="treatment capture"):
        acceptance.validate_two_phase_runtime(
            run_root,
            manifest_bound_control_seal_sha256=seal_sha256,
        )
    wrong_seal = deepcopy(treatment)
    wrong_seal["external_control_seal"]["byte_sha256"] = "0" * 64
    _replace_immutable_json(run_root / acceptance.TREATMENT_FILENAME, wrong_seal)
    with pytest.raises(acceptance.ValidationError, match="exact external control seal"):
        acceptance.validate_two_phase_runtime(
            run_root,
            manifest_bound_control_seal_sha256=seal_sha256,
        )
    reused_process = deepcopy(treatment)
    reused_process["process_identity"] = deepcopy(next(iter(controls.values()))["process_identity"])
    _replace_immutable_json(run_root / acceptance.TREATMENT_FILENAME, reused_process)
    with pytest.raises(acceptance.ValidationError, match="reused a control"):
        acceptance.validate_two_phase_runtime(
            run_root,
            manifest_bound_control_seal_sha256=seal_sha256,
        )
    reused_freezer = deepcopy(treatment)
    reused_freezer["process_identity"] = deepcopy(marker["process_identity"])
    _replace_immutable_json(run_root / acceptance.TREATMENT_FILENAME, reused_freezer)
    with pytest.raises(acceptance.ValidationError, match="reused the freezer"):
        acceptance.validate_two_phase_runtime(
            run_root,
            manifest_bound_control_seal_sha256=seal_sha256,
        )
    reused_reviewer = deepcopy(treatment)
    reused_reviewer["process_identity"] = deepcopy(seal["process_identity"])
    _replace_immutable_json(run_root / acceptance.TREATMENT_FILENAME, reused_reviewer)
    with pytest.raises(acceptance.ValidationError, match="reused the external reviewer"):
        acceptance.validate_two_phase_runtime(
            run_root,
            manifest_bound_control_seal_sha256=seal_sha256,
        )
    mutable_marker = deepcopy(marker)
    mutable_marker["immutable"] = False
    with pytest.raises(acceptance.ValidationError, match="immutable"):
        acceptance.validate_control_freeze_marker(mutable_marker, controls)


def test_coordinated_omission_of_higher_ranked_eligible_row_fails_control_anchor() -> None:
    marker, controls, treatment = _two_phase_fixture()
    path = Path(treatment["raw_control_snapshot"]["path"]).name
    tampered = controls[path]
    runtime = tampered["runtime_visibility"]
    runtime["roster"].pop(1)
    runtime["prebonus_input_candidate_ids"].pop(1)
    runtime["prebonus_input_sha256"] = acceptance._json_value_sha256(runtime["prebonus_input_candidate_ids"])
    runtime["roster"][1]["prebonus_position"] = 2
    with pytest.raises(acceptance.ValidationError, match="context expansion input"):
        _derived_treatment_output(runtime)


def test_coordinated_winner_edge_deletion_and_bonus_transfer_fails_control_anchor() -> None:
    marker, controls, treatment = _two_phase_fixture()
    path = Path(treatment["raw_control_snapshot"]["path"]).name
    tampered = controls[path]
    runtime = tampered["runtime_visibility"]
    winner = runtime["roster"][1]
    removed_ids = {
        atom["relation_id"]
        for atoms in winner["merge_inputs"].values()
        for atom in atoms
    }
    winner["merge_inputs"] = {route: [] for route in acceptance.MERGE_ROUTES}
    winner["provenance_union"] = []
    runtime["ordered_edge_inventory"] = [
        atom for atom in runtime["ordered_edge_inventory"]
        if atom["relation_id"] not in removed_ids
    ]
    runtime["ordered_edge_inventory_sha256"] = acceptance._json_value_sha256(runtime["ordered_edge_inventory"])
    with pytest.raises(acceptance.ValidationError, match="actual graph call order"):
        _derived_treatment_output(runtime)


def test_full_control_rewrite_fails_pipeline_boundary_before_external_anchor(tmp_path: Path) -> None:
    marker, controls, treatment = _two_phase_fixture()
    run_root, manifest_bound_seal_sha256, original_seal = _materialize_runtime(
        tmp_path,
        marker,
        controls,
        treatment,
    )

    for control in controls.values():
        runtime = control["runtime_visibility"]
        removed = runtime["roster"].pop(1)
        runtime["prebonus_input_candidate_ids"].pop(1)
        runtime["prebonus_input_sha256"] = acceptance._json_value_sha256(
            runtime["prebonus_input_candidate_ids"]
        )
        runtime["roster"][1]["prebonus_position"] = 2
        removed_relation_ids = {
            atom["relation_id"]
            for atoms in removed["merge_inputs"].values()
            for atom in atoms
        }
        runtime["ordered_edge_inventory"] = [
            atom
            for atom in runtime["ordered_edge_inventory"]
            if atom["relation_id"] not in removed_relation_ids
        ]
        runtime["ordered_edge_inventory_sha256"] = acceptance._json_value_sha256(
            runtime["ordered_edge_inventory"]
        )
    for entry in marker["snapshots"]:
        control = controls[entry["path"]]
        entry["canonical_sha256"] = acceptance._json_value_sha256(control)
        entry["stable_projection_sha256"] = acceptance._json_value_sha256(
            control["runtime_visibility"]
        )
        _replace_immutable_json(
            run_root / acceptance.CONTROL_DIRECTORY / entry["path"],
            control,
        )
    marker["common_stable_projection_sha256"] = marker["snapshots"][0]["stable_projection_sha256"]
    _replace_immutable_json(
        run_root / acceptance.CONTROL_DIRECTORY / acceptance.CONTROL_MARKER_FILENAME,
        marker,
    )
    with pytest.raises(acceptance.ValidationError, match="actual graph call order"):
        acceptance.build_external_control_seal_payload(
            run_root / acceptance.CONTROL_DIRECTORY,
            original_seal["process_identity"],
        )


def test_missing_external_control_seal_fails_before_treatment(tmp_path: Path) -> None:
    marker, controls, treatment = _two_phase_fixture()
    run_root, seal_sha256, _seal = _materialize_runtime(tmp_path, marker, controls, treatment)
    (run_root / acceptance.CONTROL_SEAL_FILENAME).unlink()

    with pytest.raises(acceptance.ValidationError, match="external control seal is missing"):
        acceptance.validate_two_phase_runtime(
            run_root,
            manifest_bound_control_seal_sha256=seal_sha256,
        )


def test_treatment_is_blocked_without_manifest_bound_external_seal_digest(tmp_path: Path) -> None:
    marker, controls, treatment = _two_phase_fixture()
    run_root, _seal_sha256, _seal = _materialize_runtime(tmp_path, marker, controls, treatment)

    with pytest.raises(acceptance.ValidationError, match="manifest-bound external control seal digest"):
        acceptance.validate_two_phase_runtime(
            run_root,
            manifest_bound_control_seal_sha256="",
        )


def test_external_control_seal_wrong_mode_fails_before_treatment(tmp_path: Path) -> None:
    marker, controls, treatment = _two_phase_fixture()
    run_root, seal_sha256, _seal = _materialize_runtime(tmp_path, marker, controls, treatment)
    (run_root / acceptance.CONTROL_SEAL_FILENAME).chmod(0o644)

    with pytest.raises(acceptance.ValidationError, match="mode is not 0444"):
        acceptance.validate_two_phase_runtime(
            run_root,
            manifest_bound_control_seal_sha256=seal_sha256,
        )


def test_extra_control_file_fails_exact_inventory(tmp_path: Path) -> None:
    marker, controls, treatment = _two_phase_fixture()
    run_root, seal_sha256, _seal = _materialize_runtime(tmp_path, marker, controls, treatment)
    _write_immutable_json(run_root / acceptance.CONTROL_DIRECTORY / "extra.json", {})

    with pytest.raises(acceptance.ValidationError, match="exact inventory"):
        acceptance.validate_two_phase_runtime(
            run_root,
            manifest_bound_control_seal_sha256=seal_sha256,
        )


def test_legacy_sources_are_protected_and_cannot_gain_efficacy_credit() -> None:
    payload = _payload()
    acceptance._validate_legacy_protected(payload)

    changed = deepcopy(payload)
    changed["legacy_protected"]["sources"]["starlette"]["role"] = "efficacy_development"
    with pytest.raises(acceptance.ValidationError, match="protected legacy"):
        acceptance._validate_legacy_protected(changed)
    changed = deepcopy(payload)
    changed["legacy_protected"]["efficacy_credit"] = True
    with pytest.raises(acceptance.ValidationError, match="efficacy credit"):
        acceptance._validate_legacy_protected(changed)
    changed = deepcopy(payload)
    changed["legacy_protected"]["sources"]["daily"]["commit"] = "0" * 40
    with pytest.raises(acceptance.ValidationError, match="identity"):
        acceptance._validate_legacy_protected(changed)


def test_v2_reject_index_and_all_old_artifacts_are_recomputed() -> None:
    result = acceptance._validate_v2_terminal(_payload())

    assert result == {"artifacts": 10, "captures": 8, "distinct_processes": 8}


def test_v2_reject_index_cannot_be_replaced_or_reused() -> None:
    payload = _payload()
    payload["v2_terminal"]["reject_index_sha256"] = "0" * 64

    with pytest.raises(acceptance.ValidationError, match="v2 terminal contract"):
        acceptance._validate_v2_terminal(payload)


def test_recovery_v2_seals_are_bound_unreleased_and_click_remains_closed() -> None:
    payload = _payload()
    acceptance._validate_fresh_and_click(payload)

    released = deepcopy(payload)
    released["fresh_efficacy"]["release_authorized"] = True
    with pytest.raises(acceptance.ValidationError, match="fresh seal boundary"):
        acceptance._validate_fresh_and_click(released)
    wrong_contract = deepcopy(payload)
    wrong_contract["fresh_efficacy"]["slots"][0]["public_contract_sha256"] = "0" * 64
    with pytest.raises(acceptance.ValidationError, match="fresh public contract anchor"):
        acceptance._validate_fresh_and_click(wrong_contract)
    fake_plaintext = deepcopy(payload)
    fake_plaintext["fresh_efficacy"]["slots"][0]["plaintext_path"] = fake_plaintext["fresh_efficacy"]["slots"][0]["public_contract_path"]
    with pytest.raises(acceptance.ValidationError, match="fresh sealed payload binding"):
        acceptance._validate_fresh_and_click(fake_plaintext)
    revoked_reference = deepcopy(payload)
    revoked_reference["fresh_efficacy"]["slots"][0]["public_contract_path"] = ".quality/p15-v3-review-seal/httpx_public_contract.json"
    with pytest.raises(acceptance.ValidationError, match="revoked artifact"):
        acceptance._validate_fresh_and_click(revoked_reference)
    unrevoked = deepcopy(payload)
    unrevoked["fresh_efficacy"]["archived_revoked_chain"]["old_artifacts_may_be_referenced_by_active_fields"] = True
    with pytest.raises(acceptance.ValidationError, match="archive status"):
        acceptance._validate_fresh_and_click(unrevoked)
    approved_click = deepcopy(payload)
    approved_click["click"]["status"] = "approved"
    with pytest.raises(acceptance.ValidationError, match="Click gate"):
        acceptance._validate_fresh_and_click(approved_click)


def test_recovery_v2_validation_never_reads_ciphertext_revoked_chain_or_click_files(monkeypatch) -> None:
    original_open = Path.open

    def deny_ciphertext_open(path: Path, *args, **kwargs):
        rendered = path.as_posix()
        if (
            path.name.endswith(".enc")
            or any(prefix in rendered for prefix in acceptance.REVOKED_V3_PATH_PREFIXES)
            or ".quality/p15-review-seal/" in rendered
        ):
            raise AssertionError(f"forbidden archived/cipher/Click read attempted: {path}")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", deny_ciphertext_open)
    acceptance._validate_fresh_and_click(_payload())


def test_fresh_seal_inventory_and_opaque_mode_fail_closed(tmp_path: Path) -> None:
    payload = _payload()
    changed = deepcopy(payload)
    changed["fresh_efficacy"]["seal_directory_exact_inventory"].pop()
    with pytest.raises(acceptance.ValidationError, match="seal directory inventory"):
        acceptance._validate_fresh_and_click(changed)

    opaque = tmp_path / "opaque.enc"
    opaque.write_bytes(b"metadata-only-test")
    opaque.chmod(0o644)
    with pytest.raises(acceptance.ValidationError, match="mode changed"):
        acceptance._validate_file_stat(
            opaque,
            mode=0o600,
            size=len(b"metadata-only-test"),
            label="opaque test payload",
        )


def test_capture_boundary_review_and_run_identity_remain_pending() -> None:
    payload = _payload()
    acceptance._validate_boundary_and_cleanliness(payload)

    authorized = deepcopy(payload)
    authorized["capture_authorized"] = True
    with pytest.raises(acceptance.ValidationError, match="capture became authorized"):
        acceptance._validate_boundary_and_cleanliness(authorized)
    local_model = deepcopy(payload)
    local_model["execution_boundary"]["local_ollama_forbidden"] = False
    with pytest.raises(acceptance.ValidationError, match="execution boundary"):
        acceptance._validate_boundary_and_cleanliness(local_model)
    self_approved = deepcopy(payload)
    self_approved["review"]["recovery_v2_manifest_harness_rebind"] = "approved"
    with pytest.raises(acceptance.ValidationError, match="self-approved"):
        acceptance._validate_boundary_and_cleanliness(self_approved)


def test_formula_contract_is_closed() -> None:
    payload = _payload()
    acceptance._validate_formula_contract(payload)

    changed = deepcopy(payload)
    changed["formula_contract"]["saturation_visibility"]["position_65"] = "allow"
    with pytest.raises(acceptance.ValidationError, match="saturation"):
        acceptance._validate_formula_contract(changed)


def test_design_plan_and_manifest_hashes_are_hard_anchors() -> None:
    payload = _payload()

    assert acceptance._sha256(MANIFEST) == acceptance.MANIFEST_SHA256
    acceptance._validate_identity_files(payload)
    changed = deepcopy(payload)
    changed["identities"]["design"]["sha256"] = "0" * 64
    with pytest.raises(acceptance.ValidationError, match="design identity"):
        acceptance._validate_identity_files(changed)
