from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "scripts" / "p6_benchmark.py"


def _load_harness() -> Any:
    spec = importlib.util.spec_from_file_location("p6_measurement_harness", HARNESS)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _tiny_workload(module: Any, tmp_path: Path) -> tuple[Path, Path]:
    repo = tmp_path / "source-repo"
    generated = repo / "generated"
    generated.mkdir(parents=True)
    for index in range(2):
        (generated / f"Generated{index:06d}.java").write_bytes(
            f"package generated; class Generated{index:06d} {{}}\n".encode()
        )
    manifest = tmp_path / "manifest.json"
    (tmp_path / "query_cases.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "approved_generated_query_ids": ["benchword1"],
                "cases": [
                    {
                        "id": "benchword1",
                        "family": "lexical",
                        "selectivity": "high_hit",
                        "query_token": "benchword1",
                        "planner_enabled": False,
                        "top_k": 10,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    manifest.write_text(
        json.dumps(
            {
                "generator": {
                    "version": "p6-generator-v1",
                    "contract_sha256": "1" * 64,
                    "seed": 20260718,
                },
                "tiers": {
                    "smoke": {
                        "files": 2,
                        "source_bytes": 8192,
                    }
                },
                "expected_fingerprints": {
                    "smoke": module._repository_fingerprint(repo),
                },
                "benchmark_registry": {
                    "version": "p6-benchmark-registry-v1",
                    "measurement_states": [
                        {
                            "id": "cli_process_cold",
                            "acceptance_evidence": True,
                            "informational_only": False,
                        },
                        {
                            "id": "mcp_resident_warm",
                            "acceptance_evidence": True,
                            "informational_only": False,
                        },
                        {
                            "id": "filesystem_cold_diagnostic",
                            "acceptance_evidence": False,
                            "informational_only": True,
                        },
                    ],
                    "cases": [
                        {
                            "operation_id": "full_build",
                            "case_id": "default",
                            "protected_operation_id": "full_build",
                            "case_family": "index",
                            "tiers": ["smoke"],
                            "planner_enabled": False,
                            "query_case_id": None,
                            "measurements": [
                                {
                                    "state": "cli_process_cold",
                                    "sample_count": 2,
                                    "baseline_outcome": "supported",
                                }
                            ],
                        },
                        {
                            "operation_id": "query",
                            "case_id": "benchword1",
                            "protected_operation_id": "query_benchword1",
                            "case_family": "query",
                            "tiers": ["smoke"],
                            "planner_enabled": False,
                            "query_case_id": "benchword1",
                            "measurements": [
                                {
                                    "state": "cli_process_cold",
                                    "sample_count": 2,
                                    "baseline_outcome": "supported",
                                },
                                {
                                    "state": "mcp_resident_warm",
                                    "sample_count": 2,
                                    "baseline_outcome": "unsupported",
                                }
                            ],
                        },
                    ],
                },
                "protected_small_entry_comparable": [
                    "full_build",
                    "query_benchword1",
                ],
            }
        ),
        encoding="utf-8",
    )
    return repo, manifest


def test_internal_worker_reports_self_rss_and_no_product_children(
    tmp_path: Path,
) -> None:
    module = _load_harness()
    repo = tmp_path / "worker-repo"
    generated = repo / "generated"
    generated.mkdir(parents=True)
    (generated / "Generated000000.java").write_bytes(
        b"package generated; class Generated000000 {}\n"
    )

    try:
        first = module._run_measurement_worker("full_build", repo, "default")
    except ValueError as error:
        raise AssertionError(
            "measurement wrapper must preserve the streaming verifier call contract"
        ) from error
    second_repo = tmp_path / "worker-repo-2"
    module.shutil.copytree(repo, second_repo)
    module.shutil.rmtree(second_repo / ".context-search")
    second = module._run_measurement_worker("full_build", second_repo, "default")

    for result in (first, second):
        assert result["product_subprocesses"] == 0
        assert result["duration_ms"] > 0
        assert result["rss"]["process_start_bytes"] > 0
        assert result["rss"]["peak_bytes"] >= result["rss"]["process_start_bytes"]
        assert result["rss"]["current_bytes"] > 0
        assert result["rss"]["extra_peak_bytes"] == max(
            0,
            result["rss"]["peak_bytes"]
            - result["rss"]["empty_harness_peak_bytes"],
        )
        attribution = result["attribution"]
        assert attribution["immutable_state_load_ms"] > 0
        assert attribution["work"]["inventory_entries"] == 1
        assert attribution["work"]["source_bytes_hashed"] > 0
        assert attribution["work"]["source_bytes_read"] == 2 * attribution[
            "work"
        ]["source_bytes_hashed"]
        assert attribution["work"]["peak_queued_files"] == 1
        assert attribution["work"]["peak_queued_chunks"] > 0
        assert attribution["work"]["embedding_batch_inputs"] == attribution["work"][
            "vector_rows_queued"
        ]
        assert attribution["work"]["flush_count"] == 1
        assert attribution["work"]["path_index_builds"] == 1
        assert attribution["work"]["vector_bytes_written"] > 0
        assert attribution["work"]["vector_bytes_hashed"] >= attribution["work"][
            "vector_bytes_written"
        ]
        assert attribution["work"]["vector_bytes_read"] >= attribution["work"][
            "vector_bytes_hashed"
        ]
        assert attribution["work"]["vector_payload_passes"] > 0
        assert attribution["stage_timings_ms"]["inventory"] > 0
        assert attribution["stage_timings_ms"]["startup"] > 0
        assert attribution["stage_timings_ms"]["config"] > 0
        assert attribution["stage_timings_ms"]["manifest"] > 0
        assert attribution["stage_timings_ms"]["parse"] > 0
        assert attribution["stage_timings_ms"]["embedding"] > 0
        assert attribution["stage_timings_ms"]["persistence"] > 0
        assert attribution["stage_timings_ms"]["vector_publication"] > 0


def test_empty_harness_peak_comes_from_an_independent_worker(tmp_path: Path) -> None:
    module = _load_harness()
    empty = module._invoke_measurement_worker(
        {
            "schema_version": 1,
            "kind": "empty",
            "repo": str(tmp_path),
        }
    )

    assert empty["duration_ms"] == 0.0
    assert empty["product_subprocesses"] == 0
    assert empty["rss"]["peak_bytes"] >= empty["rss"]["process_start_bytes"] > 0


def test_query_work_proof_is_a_separate_worker_and_cannot_replace_timing(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    module = _load_harness()
    calls: list[str] = []
    rss = {
        "process_start_bytes": 10,
        "peak_bytes": 20,
        "current_bytes": 15,
        "empty_harness_peak_bytes": 10,
        "extra_peak_bytes": 10,
    }

    def fake_invoke(request: dict[str, Any]) -> dict[str, Any]:
        kind = str(request["kind"])
        calls.append(kind)
        if kind == "empty":
            return {
                "duration_ms": 0.0,
                "rss": rss,
                "attribution": None,
                "product_subprocesses": 0,
            }
        if kind == "operation":
            return {
                "duration_ms": 7.0,
                "rss": rss,
                "output_sha256": "a" * 64,
                "attribution": {
                    "trace_duration_ms": 3.0,
                    "source_counts": {},
                    "stages": [],
                    "stage_timings_ms": {},
                    "work": {"vector_scored_rows": 4},
                },
                "product_subprocesses": 0,
            }
        assert kind == "attribution"
        return {
            "duration_ms": 999.0,
            "rss": rss,
            "output_sha256": "a" * 64,
            "attribution": {
                "work": {
                    "repo_profile_vm_steps": 101,
                    "repo_profile_rows": 5,
                    "repo_profile_bytes": 80,
                    "active_ids_materialized": 4,
                    "deleted_ids_materialized": 1,
                    "id_bytes_materialized": 50,
                    "lexical_vm_steps": 23,
                    "lexical_rows": 2,
                    "path_symbol_rows": 7,
                    "path_symbol_bytes": 90,
                    "direct_text_rows": 4,
                    "direct_text_bytes": 100,
                    "signal_rows": 3,
                    "signal_bytes": 70,
                    "relations_read": 2,
                    "relations_resolved": 1,
                }
            },
            "product_subprocesses": 0,
        }

    monkeypatch.setattr(module, "_invoke_measurement_worker", fake_invoke)

    result = module._run_measurement_worker("query", tmp_path, "benchword1")

    assert calls == ["empty", "operation", "attribution"]
    assert result["duration_ms"] == 7.0
    assert result["attribution"]["trace_duration_ms"] == 3.0
    assert result["attribution"]["work"]["vector_scored_rows"] == 4
    assert result["attribution"]["work"]["repo_profile_vm_steps"] == 101


def test_query_work_proof_must_match_measured_product_output(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    module = _load_harness()
    rss = {
        "process_start_bytes": 10,
        "peak_bytes": 20,
        "current_bytes": 15,
        "empty_harness_peak_bytes": 10,
        "extra_peak_bytes": 10,
    }

    def fake_invoke(request: dict[str, Any]) -> dict[str, Any]:
        kind = str(request["kind"])
        if kind == "empty":
            return {
                "duration_ms": 0.0,
                "rss": rss,
                "attribution": None,
                "product_subprocesses": 0,
            }
        return {
            "duration_ms": 1.0,
            "rss": rss,
            "output_sha256": ("a" if kind == "operation" else "b") * 64,
            "attribution": {"work": {}},
            "product_subprocesses": 0,
        }

    monkeypatch.setattr(module, "_invoke_measurement_worker", fake_invoke)

    try:
        module._run_measurement_worker("query", tmp_path, "benchword1")
    except ValueError as exc:
        assert "work-proof output differs" in str(exc)
    else:
        raise AssertionError("mismatched attribution output must fail closed")


def test_query_output_identity_excludes_direct_text_host_timing() -> None:
    module = _load_harness()
    first = (
        "direct_text_search slow: 51.2ms for 5 probes, 4000 chunks\n"
        "# Context Search Results\n"
    )
    second = (
        "direct_text_search slow: 87.9ms for 5 probes, 4000 chunks\n"
        "# Context Search Results\n"
    )

    first_payload = module._measurement_output_bytes("query", first)
    second_payload = module._measurement_output_bytes("query", second)

    assert first_payload == second_payload
    assert b"5 probes, 4000 chunks" in first_payload


def test_query_and_explore_use_real_positional_cli_shape(tmp_path: Path) -> None:
    module = _load_harness()
    repo = tmp_path / "repo"
    assert module._operation_cli_args("query_lexical", repo, "benchword1") == [
        "query",
        str(repo),
        "benchword1",
        "--no-planner",
    ]


def test_status_and_refresh_use_real_json_cli_shape(tmp_path: Path) -> None:
    module = _load_harness()
    repo = tmp_path / "repo"

    assert module._operation_cli_args("status_quick", repo, "default") == [
        "status",
        str(repo),
        "--json",
    ]
    assert module._operation_cli_args("status_verified", repo, "default") == [
        "status",
        str(repo),
        "--json",
        "--verify",
    ]
    assert module._operation_cli_args("refresh_noop", repo, "default") == [
        "refresh",
        str(repo),
        "--json",
    ]
    assert module._operation_cli_args("refresh_one_file", repo, "default") == [
        "refresh",
        str(repo),
        "--json",
    ]


def test_query_worker_captures_private_numeric_production_trace(tmp_path: Path) -> None:
    module = _load_harness()
    repo = tmp_path / "repo"
    generated = repo / "generated"
    generated.mkdir(parents=True)
    (generated / "Generated000000.java").write_text(
        "package generated; class Generated000000 { void work() {} }\n",
        encoding="utf-8",
    )
    module._run_measurement_worker("full_build", repo, "default")

    result = module._run_measurement_worker(
        "query_lexical", repo, "Generated000000"
    )

    attribution = result["attribution"]
    assert attribution is not None
    assert attribution["trace_duration_ms"] >= 0
    assert [stage["name"] for stage in attribution["stages"]] == [
        "query_understanding",
        "semantic_recall",
        "lexical_recall",
        "path_symbol_recall",
        "direct_text_recall",
        "signal_recall",
        "planner_hint_recall",
        "direct_merge",
        "anchor_expansion",
        "relation_expansion",
        "candidate_merge",
        "ranking",
        "cohort_rerank",
        "context_expansion",
        "final_selection",
    ]
    assert attribution["work"]["vector_scored_rows"] > 0
    assert attribution["work"]["vector_normalization_count"] == 1
    assert attribution["work"]["vector_sorted_rows"] <= attribution["work"][
        "vector_scored_rows"
    ]
    assert attribution["work"]["vector_bytes_read"] > 0
    assert attribution["work"]["vector_bytes_hashed"] == 0
    assert attribution["work"]["vector_payload_passes"] == 1
    assert attribution["work"]["repo_profile_vm_steps"] == 0
    assert attribution["work"]["repo_profile_rows"] == 0
    assert attribution["work"]["repo_profile_bytes"] == 0
    assert attribution["work"]["active_ids_materialized"] == 0
    assert attribution["work"]["deleted_ids_materialized"] == 0
    assert attribution["work"]["id_bytes_materialized"] == 0
    assert attribution["work"]["lexical_vm_steps"] > 0
    assert attribution["work"]["lexical_rows"] > 0
    assert attribution["work"]["path_symbol_rows"] > 0
    assert attribution["work"]["path_symbol_bytes"] > 0
    assert attribution["work"]["direct_text_rows"] > 0
    assert attribution["work"]["direct_text_bytes"] > 0
    assert attribution["work"]["signal_rows"] > 0
    assert attribution["work"]["signal_bytes"] > 0
    assert attribution["work"]["relations_resolved"] <= attribution["work"][
        "relations_read"
    ]
    assert "Generated000000" not in json.dumps(attribution)
    assert module._operation_cli_args("explore_p4", repo, "benchword2") == [
        "explore",
        str(repo),
        "benchword2",
        "--no-planner",
    ]


def test_final_resident_measurement_state_is_supported() -> None:
    module = _load_harness()
    assert not module._measurement_is_supported(
        "query_lexical", "mcp_resident_warm", "baseline"
    )
    assert module._measurement_is_supported(
        "query", "mcp_resident_warm", "final"
    )
    assert module._measurement_is_supported(
        "explore", "mcp_resident_warm", "final"
    )
    assert not module._measurement_is_supported(
        "full_build", "mcp_resident_warm", "final"
    )
    assert not module._measurement_is_supported(
        "query_lexical", "filesystem_cold_diagnostic", "baseline"
    )
    assert not module._measurement_is_supported(
        "status_quick", "cli_process_cold", "baseline"
    )
    assert module._measurement_is_supported(
        "full_build", "cli_process_cold", "baseline"
    )
    for operation in (
        "status_quick",
        "status_verified",
        "refresh_noop",
        "refresh_one_file",
    ):
        assert module._measurement_is_supported(
            operation, "cli_process_cold", "final"
        )


def test_one_file_refresh_measurement_reestablishes_one_dirty_file_per_run(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    module = _load_harness()
    repo, manifest = _tiny_workload(module, tmp_path)
    contract = json.loads(manifest.read_text(encoding="utf-8"))
    contract["benchmark_registry"]["cases"].append(
        {
            "operation_id": "refresh_one_file",
            "case_id": "default",
            "protected_operation_id": "refresh_one_file",
            "case_family": "refresh",
            "tiers": ["smoke"],
            "planner_enabled": False,
            "query_case_id": None,
            "measurements": [
                {
                    "state": "cli_process_cold",
                    "sample_count": 2,
                    "baseline_outcome": "unsupported",
                }
            ],
        }
    )
    contract["protected_small_entry_comparable"].append("refresh_one_file")
    manifest.write_text(json.dumps(contract), encoding="utf-8")
    preparations: list[tuple[Path, str]] = []
    calls: list[tuple[str, Path]] = []

    def prepare(sample_repo: Path, mutation_id: str) -> Path:
        preparations.append((sample_repo, mutation_id))
        source = sorted((sample_repo / "generated").glob("*.java"))[0]
        source.write_bytes(
            source.read_bytes() + f"// {mutation_id}\n".encode("utf-8")
        )
        return source

    def fake_worker(operation: str, sample_repo: Path, case_id: str) -> dict[str, Any]:
        calls.append((operation, sample_repo))
        if operation == "full_build":
            (sample_repo / ".context-search").mkdir()
        return {
            "duration_ms": 1.0,
            "attribution": None,
            "rss": {
                "process_start_bytes": 10,
                "peak_bytes": 20,
                "current_bytes": 15,
                "empty_harness_peak_bytes": 10,
                "extra_peak_bytes": 10,
            },
            "product_subprocesses": 0,
        }

    monkeypatch.setattr(module, "_prepare_one_file_refresh", prepare)
    monkeypatch.setattr(module, "_run_measurement_worker", fake_worker)
    commit, tree, _dirty = module._git_identity()
    monkeypatch.setattr(
        module,
        "_git_identity",
        lambda _root=module.ROOT: (commit, tree, False),
    )
    monkeypatch.setattr(
        module,
        "_calibration",
        lambda: {
            "valid": True,
            "sha256_bytes": 512 * 1024**2,
            "sha256_mib_per_s": 1.0,
            "numpy_rows": 80000,
            "numpy_dimensions": 384,
            "numpy_dot_ms": 1.0,
            "sqlite_rows": 20000,
            "sqlite_ms": 1.0,
            "within_pair_percent": 0.0,
        },
    )

    report = module.run_benchmark(
        repo,
        manifest,
        operation="refresh_one_file",
        case_id="default",
        sample_count=2,
        measurement_state="cli_process_cold",
        mode="final",
    )

    assert [operation for operation, _ in calls] == [
        "full_build",
        "refresh_one_file",
        "refresh_one_file",
        "refresh_one_file",
        "refresh_one_file",
    ]
    assert [mutation_id for _, mutation_id in preparations] == [
        "sample-001-warmup",
        "sample-001-measured",
        "sample-002-warmup",
        "sample-002-measured",
    ]
    assert preparations[0][0] == preparations[1][0]
    assert preparations[2][0] == preparations[3][0]
    assert preparations[0][0] != preparations[2][0]
    assert report["summary"]["sample_count"] == 2


def test_status_and_refresh_workers_report_real_bounded_work(tmp_path: Path) -> None:
    module = _load_harness()
    repo = tmp_path / "repo"
    generated = repo / "generated"
    generated.mkdir(parents=True)
    source = generated / "Generated000000.java"
    source.write_text(
        "package generated; class Generated000000 { void work() {} }\n",
        encoding="utf-8",
    )
    indexed_size = source.stat().st_size
    module._run_measurement_worker("full_build", repo, "default")

    quick = module._run_measurement_worker("status_quick", repo, "default")
    verified = module._run_measurement_worker(
        "status_verified", repo, "default"
    )
    noop = module._run_measurement_worker("refresh_noop", repo, "default")
    module._prepare_one_file_refresh(repo, "integration-measured")
    dirty_size = source.stat().st_size
    one_file = module._run_measurement_worker(
        "refresh_one_file", repo, "default"
    )

    quick_work = quick["attribution"]["work"]
    assert quick_work["source_bytes_read"] == 0
    assert quick_work["source_bytes_hashed"] == 0
    assert quick_work["vector_bytes_read"] == 0
    assert quick_work["vector_bytes_hashed"] == 0

    verified_work = verified["attribution"]["work"]
    assert verified_work["source_bytes_read"] == indexed_size
    assert verified_work["source_bytes_hashed"] == indexed_size
    assert verified_work["vector_bytes_read"] > 0
    assert 0 < verified_work["vector_bytes_hashed"] <= verified_work[
        "vector_bytes_read"
    ]

    noop_work = noop["attribution"]["work"]
    assert noop_work["source_bytes_read"] == 0
    assert noop_work["source_bytes_hashed"] == 0
    assert noop_work["vector_bytes_read"] == 0
    assert noop_work["vector_bytes_written"] == 0
    assert noop_work["vector_bytes_copied"] == 0
    assert noop_work["vector_payload_passes"] == 0
    assert noop_work["path_index_builds"] == 0

    one_file_work = one_file["attribution"]["work"]
    assert one_file_work["source_bytes_read"] == dirty_size
    assert one_file_work["source_bytes_hashed"] == dirty_size
    assert one_file_work["embedding_batch_inputs"] > 0
    assert one_file_work["vector_bytes_read"] > 0
    assert one_file_work["vector_bytes_written"] > 0
    assert one_file_work["generation_count"] == 1
    assert quick["product_subprocesses"] == 0
    assert verified["product_subprocesses"] == 0
    assert noop["product_subprocesses"] == 0
    assert one_file["product_subprocesses"] == 0


def test_churn_action_runner_exercises_success_skip_and_failure_paths(
    tmp_path: Path,
) -> None:
    from context_search_tool import index_health
    from context_search_tool.config import load_config

    module = _load_harness()
    repo = tmp_path / "repo"
    repo.mkdir()
    for index in range(6):
        (repo / f"Type{index}.java").write_text(
            f'class Type{index} {{ String value = "benchword{index}"; }}\n',
            encoding="utf-8",
        )
    module._run_measurement_worker("full_build", repo, "default")
    config = load_config(repo)
    deleted: dict[int, bytes] = {}
    actions = [
        {"step": 1, "operation": "modify", "target": "Type0.java", "payload_sha256": "1" * 64},
        {"step": 2, "operation": "delete", "target": "Type1.java"},
        {"step": 3, "operation": "restore", "target": "Type1.java", "source_step": 2},
        {"step": 4, "operation": "add", "target": "Added.java", "payload_sha256": "2" * 64},
        {"step": 5, "operation": "delete_added", "target": "Added.java"},
        {"step": 6, "operation": "equal_content_touch", "target": "Type2.java"},
        {"step": 7, "operation": "same_metadata_content_edit", "target": "Type3.java"},
        {"step": 8, "operation": "stable_skip", "target": "Type4.java"},
        {"step": 9, "operation": "retryable_skip", "target": "Type5.java"},
    ]
    for action in actions:
        result = module._run_churn_refresh_action(
            repo,
            action,
            config=config,
            deleted_payloads=deleted,
        )
        assert result.ok is True

    for step, operation in ((10, "directory_failure"), (11, "control_file_failure")):
        result = module._run_churn_refresh_action(
            repo,
            {
                "step": step,
                "operation": operation,
                "target": "generated" if operation == "directory_failure" else ".gitignore",
            },
            config=config,
            deleted_payloads=deleted,
        )
        assert result.ok is False
        assert result.code == "inventory_incomplete"

    health = index_health.inspect_repository_health(repo, mode="quick")
    assert health.queryable is True


def test_resident_session_uses_three_warmups_and_separate_work_proofs(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    module = _load_harness()
    assert hasattr(module, "_ResidentMeasurementSession"), (
        "resident measurement session is absent"
    )
    requests: list[str] = []
    proof_values = {
        name: index
        for index, name in enumerate(module._QUERY_ATTRIBUTION_COUNTERS, start=1)
    }
    rss = {
        "process_start_bytes": 100,
        "peak_bytes": 160,
        "current_bytes": 140,
        "empty_harness_peak_bytes": 100,
        "extra_peak_bytes": 60,
    }

    class FakeWorker:
        def __enter__(self) -> Any:
            return self

        def __exit__(self, *_args: Any) -> None:
            return None

        def invoke(self, request: dict[str, Any]) -> dict[str, Any]:
            kind = str(request["kind"])
            requests.append(kind)
            if kind == "empty":
                return {
                    "duration_ms": 0.0,
                    "rss": rss,
                    "attribution": None,
                    "product_subprocesses": 0,
                }
            work = (
                proof_values
                if kind == "attribution"
                else {"vector_scored_rows": 4}
            )
            return {
                "duration_ms": 7.0 if kind == "operation" else 999.0,
                "rss": rss,
                "output_sha256": "a" * 64,
                "attribution": {
                    "trace_duration_ms": 3.0,
                    "source_counts": {},
                    "stages": [],
                    "stage_timings_ms": {},
                    "work": work,
                },
                "product_subprocesses": 0,
            }

    monkeypatch.setattr(module, "_ResidentMeasurementWorker", FakeWorker)

    with module._ResidentMeasurementSession(
        "query", tmp_path, "benchword1"
    ) as session:
        first = session.measure()
        second = session.measure()

    assert requests == [
        "empty",
        "operation",
        "operation",
        "operation",
        "operation",
        "attribution",
        "operation",
        "attribution",
    ]
    assert first["duration_ms"] == second["duration_ms"] == 7.0
    assert first["attribution"]["work"]["vector_scored_rows"] == 4
    assert all(
        first["attribution"]["work"][name] == value
        for name, value in proof_values.items()
    )


def test_final_resident_benchmark_reuses_one_session(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    module = _load_harness()
    assert hasattr(module, "_ResidentMeasurementSession"), (
        "resident measurement session is absent"
    )
    repo, manifest = _tiny_workload(module, tmp_path)
    regular_calls: list[str] = []
    sessions: list[tuple[str, Path, str]] = []
    measured = 0

    def fake_worker(operation: str, sample_repo: Path, case_id: str) -> dict[str, Any]:
        regular_calls.append(operation)
        assert operation == "full_build"
        (sample_repo / ".context-search").mkdir()
        return {
            "duration_ms": 1.0,
            "attribution": None,
            "rss": {
                "process_start_bytes": 10,
                "peak_bytes": 20,
                "current_bytes": 15,
                "empty_harness_peak_bytes": 10,
                "extra_peak_bytes": 10,
            },
            "product_subprocesses": 0,
        }

    class FakeSession:
        def __init__(self, operation: str, sample_repo: Path, case_id: str) -> None:
            sessions.append((operation, sample_repo, case_id))
            assert (sample_repo / ".context-search").is_dir()

        def __enter__(self) -> Any:
            return self

        def __exit__(self, *_args: Any) -> None:
            return None

        def measure(self) -> dict[str, Any]:
            nonlocal measured
            measured += 1
            return fake_sample()

    def fake_sample() -> dict[str, Any]:
        return {
            "duration_ms": 2.0,
            "attribution": None,
            "rss": {
                "process_start_bytes": 100,
                "peak_bytes": 120,
                "current_bytes": 110,
                "empty_harness_peak_bytes": 100,
                "extra_peak_bytes": 20,
            },
            "product_subprocesses": 0,
        }

    commit, tree, _dirty = module._git_identity()
    monkeypatch.setattr(module, "_run_measurement_worker", fake_worker)
    monkeypatch.setattr(module, "_ResidentMeasurementSession", FakeSession)
    monkeypatch.setattr(
        module,
        "_git_identity",
        lambda _root=module.ROOT: (commit, tree, False),
    )
    monkeypatch.setattr(
        module,
        "_calibration",
        lambda: {
            "valid": True,
            "sha256_bytes": 512 * 1024**2,
            "sha256_mib_per_s": 1.0,
            "numpy_rows": 80000,
            "numpy_dimensions": 384,
            "numpy_dot_ms": 1.0,
            "sqlite_rows": 20000,
            "sqlite_ms": 1.0,
            "within_pair_percent": 0.0,
        },
    )

    report = module.run_benchmark(
        repo,
        manifest,
        operation="query",
        case_id="benchword1",
        sample_count=2,
        measurement_state="mcp_resident_warm",
        mode="final",
    )

    assert regular_calls == ["full_build"]
    assert len(sessions) == 1
    assert sessions[0][0::2] == ("query", "benchword1")
    assert measured == 2
    assert report["operation"]["outcome"] == "supported"
    assert report["summary"]["sample_count"] == 2


def test_calibration_inputs_are_the_frozen_reference_workloads() -> None:
    module = _load_harness()
    calibration = module._calibration()
    assert calibration["valid"] is True
    assert calibration["sha256_bytes"] == 512 * 1024**2
    assert calibration["numpy_rows"] == 80000
    assert calibration["numpy_dimensions"] == 384
    assert calibration["sqlite_rows"] == 20000
    assert calibration["sha256_mib_per_s"] > 0
    assert calibration["numpy_dot_ms"] > 0
    assert calibration["sqlite_ms"] > 0


def test_storage_work_counters_come_from_sample_snapshot(tmp_path: Path) -> None:
    module = _load_harness()
    internal = tmp_path / ".context-search"
    internal.mkdir()
    with module.sqlite3.connect(internal / "index.sqlite") as connection:
        connection.execute("CREATE TABLE chunks(chunk_id TEXT, deleted_at TEXT)")
        connection.executemany(
            "INSERT INTO chunks VALUES (?, ?)",
            [("active-a", None), ("active-b", None), ("deleted", "now")],
        )
    (internal / "vectors.generation-a.npy").write_bytes(b"a")
    (internal / "vectors.generation-b.npy").write_bytes(b"b")

    counters = module._storage_work_counters(tmp_path)

    assert counters["tombstones"] == 1
    assert counters["sqlite_pages"] > 0
    assert counters["sqlite_freelist"] >= 0
    assert counters["generation_count"] == 2


def test_cli_cold_warmup_and_full_build_samples_use_isolated_clones(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    module = _load_harness()
    repo, manifest = _tiny_workload(module, tmp_path)
    calls: list[Path] = []
    environment = module._environment()
    environment.update(
        {
            "cpu_count": max(8, environment["cpu_count"]),
            "memory_bytes": max(16 * 1024**3, environment["memory_bytes"]),
            "local_disk_class": "ssd",
            "power_state": "external",
            "governor_state": "not_applicable",
            "swap_before_bytes": 0,
            "swap_after_bytes": 0,
            "background_cpu_percent": 0.0,
        }
    )
    monkeypatch.setattr(module, "_environment", lambda: dict(environment))
    monkeypatch.setattr(
        module,
        "_calibration",
        lambda: {
            "valid": True,
            "sha256_bytes": 512 * 1024**2,
            "sha256_mib_per_s": 1.0,
            "numpy_rows": 80000,
            "numpy_dimensions": 384,
            "numpy_dot_ms": 1.0,
            "sqlite_rows": 20000,
            "sqlite_ms": 1.0,
            "within_pair_percent": 0.0,
        },
    )

    def fake_worker(operation: str, sample_repo: Path, case_id: str) -> dict[str, Any]:
        assert operation == "full_build"
        assert case_id == "default"
        calls.append(sample_repo)
        index = sample_repo / ".context-search"
        if len(calls) % 2:
            assert not index.exists()
            index.mkdir()
            (index / "warmup").write_text("warm", encoding="utf-8")
        else:
            # The identical warmup ran on this clone, then full-build state reset.
            assert not index.exists()
            index.mkdir()
            (index / "measured").write_text("measured", encoding="utf-8")
        return {
            "duration_ms": 1.0,
            "rss": {
                "process_start_bytes": 10,
                "peak_bytes": 20,
                "current_bytes": 15,
                "empty_harness_peak_bytes": 10,
                "extra_peak_bytes": 10,
            },
            "product_subprocesses": 0,
        }

    monkeypatch.setattr(module, "_run_measurement_worker", fake_worker)
    report = module.run_benchmark(
        repo,
        manifest,
        operation="full_build",
        case_id="default",
        sample_count=2,
        measurement_state="cli_process_cold",
        mode="baseline",
    )

    assert report["summary"]["sample_count"] == 2
    assert len(calls) == 4
    assert calls[0] == calls[1]
    assert calls[2] == calls[3]
    assert calls[0] != calls[2]
    assert not (repo / ".context-search").exists()


def test_read_only_measurements_prepare_one_ready_clone_and_reuse_it(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    module = _load_harness()
    repo, manifest = _tiny_workload(module, tmp_path)
    calls: list[tuple[str, Path]] = []

    def fake_worker(operation: str, sample_repo: Path, case_id: str) -> dict[str, Any]:
        calls.append((operation, sample_repo))
        index = sample_repo / ".context-search"
        if operation == "full_build":
            assert not index.exists()
            index.mkdir()
        else:
            assert operation == "query" and index.is_dir()
        return {
            "duration_ms": 1.0,
            "attribution": None,
            "rss": {
                "process_start_bytes": 10,
                "peak_bytes": 20,
                "current_bytes": 15,
                "empty_harness_peak_bytes": 10,
                "extra_peak_bytes": 10,
            },
            "product_subprocesses": 0,
        }

    monkeypatch.setattr(module, "_run_measurement_worker", fake_worker)
    monkeypatch.setattr(
        module,
        "_calibration",
        lambda: {
            "valid": True,
            "sha256_bytes": 512 * 1024**2,
            "sha256_mib_per_s": 1.0,
            "numpy_rows": 80000,
            "numpy_dimensions": 384,
            "numpy_dot_ms": 1.0,
            "sqlite_rows": 20000,
            "sqlite_ms": 1.0,
            "within_pair_percent": 0.0,
        },
    )

    report = module.run_benchmark(
        repo,
        manifest,
        operation="query",
        case_id="benchword1",
        sample_count=2,
        measurement_state="cli_process_cold",
        mode="baseline",
    )

    assert [operation for operation, _ in calls] == [
        "full_build",
        "query",
        "query",
        "query",
        "query",
    ]
    assert len({path for _, path in calls}) == 1
    assert report["operation"]["outcome"] == "supported"
    assert not (repo / ".context-search").exists()


def test_unsupported_state_never_invokes_measurement_worker(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    module = _load_harness()
    repo, manifest = _tiny_workload(module, tmp_path)

    def forbidden(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("unsupported measurements must not run a worker")

    monkeypatch.setattr(module, "_run_measurement_worker", forbidden)
    report = module.run_benchmark(
        repo,
        manifest,
        operation="query",
        case_id="benchword1",
        sample_count=2,
        measurement_state="mcp_resident_warm",
        mode="baseline",
    )
    assert report["operation"]["outcome"] == "unsupported"
    assert report["samples"] == []
    assert report["summary"]["sample_count"] == 0
    assert report["summary"]["median_ms"] == 0.0


def test_run_rejects_same_cardinality_repository_with_changed_content(
    tmp_path: Path,
) -> None:
    module = _load_harness()
    repo, manifest = _tiny_workload(module, tmp_path)
    source = next((repo / "generated").glob("*.java"))
    source.write_bytes(source.read_bytes() + b"// drift\n")

    with pytest.raises(ValueError, match="fingerprint"):
        module.run_benchmark(
            repo,
            manifest,
            operation="query",
            case_id="benchword1",
            sample_count=2,
            measurement_state="cli_process_cold",
            mode="baseline",
        )


def test_interrupted_run_checkpoints_completed_samples_and_resumes_only_missing(
    tmp_path: Path,
    monkeypatch: Any,
    capsys: Any,
) -> None:
    module = _load_harness()
    monkeypatch.setattr(
        module,
        "_calibration",
        lambda: {
            "valid": True,
            "sha256_bytes": 512 * 1024**2,
            "sha256_mib_per_s": 1.0,
            "numpy_rows": 80000,
            "numpy_dimensions": 384,
            "numpy_dot_ms": 1.0,
            "sqlite_rows": 20000,
            "sqlite_ms": 1.0,
            "within_pair_percent": 0.0,
        },
    )
    repo, manifest = _tiny_workload(module, tmp_path)
    checkpoint_dir = tmp_path / "checkpoints"
    calls: list[Path] = []

    def fake_worker(operation: str, sample_repo: Path, case_id: str) -> dict[str, Any]:
        assert operation == "full_build"
        assert case_id == "default"
        calls.append(sample_repo)
        index = sample_repo / ".context-search"
        if len(calls) == 4:
            raise RuntimeError("simulated interruption")
        assert not index.exists()
        index.mkdir()
        return {
            "duration_ms": 1.0,
            "attribution": None,
            "rss": {
                "process_start_bytes": 10,
                "peak_bytes": 20,
                "current_bytes": 15,
                "empty_harness_peak_bytes": 10,
                "extra_peak_bytes": 10,
            },
            "product_subprocesses": 0,
        }

    monkeypatch.setattr(module, "_run_measurement_worker", fake_worker)
    with pytest.raises(RuntimeError, match="simulated interruption"):
        module.run_benchmark(
            repo,
            manifest,
            operation="full_build",
            case_id="default",
            sample_count=2,
            measurement_state="cli_process_cold",
            mode="baseline",
            checkpoint_dir=checkpoint_dir,
            resume=False,
        )

    assert sorted(path.name for path in checkpoint_dir.iterdir()) == [
        "run.json",
        "sample-001.json",
    ]
    first_calls = len(calls)

    def resumed_worker(
        operation: str, sample_repo: Path, case_id: str
    ) -> dict[str, Any]:
        assert operation == "full_build"
        assert case_id == "default"
        calls.append(sample_repo)
        index = sample_repo / ".context-search"
        assert not index.exists()
        index.mkdir()
        return {
            "duration_ms": 1.0,
            "attribution": None,
            "rss": {
                "process_start_bytes": 10,
                "peak_bytes": 20,
                "current_bytes": 15,
                "empty_harness_peak_bytes": 10,
                "extra_peak_bytes": 10,
            },
            "product_subprocesses": 0,
        }

    monkeypatch.setattr(module, "_run_measurement_worker", resumed_worker)
    report = module.run_benchmark(
        repo,
        manifest,
        operation="full_build",
        case_id="default",
        sample_count=2,
        measurement_state="cli_process_cold",
        mode="baseline",
        checkpoint_dir=checkpoint_dir,
        resume=True,
    )

    assert len(calls) - first_calls == 2
    assert [sample["sample_id"] for sample in report["samples"]] == [
        "sample-001",
        "sample-002",
    ]
    assert sorted(path.name for path in checkpoint_dir.iterdir()) == [
        "run.json",
        "sample-001.json",
        "sample-002.json",
    ]
    progress = capsys.readouterr().err
    assert "sample 1/2 checkpoint complete" in progress
    assert "resuming with 1/2 completed samples" in progress
    assert "sample 2/2 measured" in progress


def test_resume_rejects_tampered_checkpoint_identity_before_measurement(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    module = _load_harness()
    repo, manifest = _tiny_workload(module, tmp_path)
    checkpoint_dir = tmp_path / "checkpoints"

    def interrupt_after_first_sample(
        operation: str, sample_repo: Path, case_id: str
    ) -> dict[str, Any]:
        index = sample_repo / ".context-search"
        if not index.exists():
            index.mkdir()
        sample_files = list(checkpoint_dir.glob("sample-*.json"))
        if sample_files:
            raise RuntimeError("stop")
        return {
            "duration_ms": 1.0,
            "attribution": None,
            "rss": {
                "process_start_bytes": 10,
                "peak_bytes": 20,
                "current_bytes": 15,
                "empty_harness_peak_bytes": 10,
                "extra_peak_bytes": 10,
            },
            "product_subprocesses": 0,
        }

    monkeypatch.setattr(
        module, "_run_measurement_worker", interrupt_after_first_sample
    )
    with pytest.raises(RuntimeError, match="stop"):
        module.run_benchmark(
            repo,
            manifest,
            operation="full_build",
            case_id="default",
            sample_count=2,
            measurement_state="cli_process_cold",
            mode="baseline",
            checkpoint_dir=checkpoint_dir,
            resume=False,
        )

    run_path = checkpoint_dir / "run.json"
    checkpoint = json.loads(run_path.read_text(encoding="utf-8"))
    checkpoint["identity"]["harness_sha256"] = "0" * 64
    run_path.write_text(json.dumps(checkpoint), encoding="utf-8")

    monkeypatch.setattr(
        module,
        "_run_measurement_worker",
        lambda *_: (_ for _ in ()).throw(
            AssertionError("identity mismatch must fail before measurement")
        ),
    )
    with pytest.raises(ValueError, match="checkpoint identity"):
        module.run_benchmark(
            repo,
            manifest,
            operation="full_build",
            case_id="default",
            sample_count=2,
            measurement_state="cli_process_cold",
            mode="baseline",
            checkpoint_dir=checkpoint_dir,
            resume=True,
        )
