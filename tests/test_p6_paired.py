from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "scripts" / "p6_benchmark.py"
HASH = "1" * 64
GIT = "1" * 40


def _load_harness() -> Any:
    spec = importlib.util.spec_from_file_location("p6_paired_harness", HARNESS)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _pristine_repo_and_manifest(module: Any, tmp_path: Path) -> tuple[Path, Path]:
    repo = tmp_path / "pristine"
    generated = repo / "generated"
    generated.mkdir(parents=True)
    (generated / "Generated000000.java").write_text(
        "package generated; class Generated000000 {}\n",
        encoding="utf-8",
    )
    fingerprint = module._repository_fingerprint(repo)
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "generator": {
                    "version": "p6-generator-v1",
                    "contract_sha256": HASH,
                    "seed": 20260718,
                },
                "tiers": {"smoke": {"files": 1}},
                "protected_small_entry_comparable": [
                    "full_build",
                    "authoritative_noop",
                    "status_quick",
                    "query_lexical_high",
                    "explore_p4_bounded",
                ],
                "expected_fingerprints": {"smoke": fingerprint},
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    (tmp_path / "query_cases.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "approved_generated_query_ids": ["lexical_high", "p4_explore"],
                "cases": [
                    {
                        "id": "lexical_high",
                        "family": "lexical",
                        "selectivity": "high_hit",
                        "query_token": "lexicalburst",
                        "planner_enabled": True,
                        "top_k": 10,
                    },
                    {
                        "id": "p4_explore",
                        "family": "explore",
                        "selectivity": "high_hit",
                        "query_token": "checkout endpoint implementation tests",
                        "planner_enabled": True,
                        "top_k": 8,
                    },
                ],
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return repo, manifest


def _calibration() -> dict[str, Any]:
    return {
        "valid": True,
        "sha256_bytes": 536870912,
        "sha256_mib_per_s": 100.0,
        "numpy_rows": 80000,
        "numpy_dimensions": 384,
        "numpy_dot_ms": 10.0,
        "sqlite_rows": 20000,
        "sqlite_ms": 5.0,
        "within_pair_percent": 0.0,
    }


def _measured(duration_ms: float = 1.0) -> dict[str, Any]:
    return {
        "duration_ms": duration_ms,
        "rss": {
            "process_start_bytes": 1,
            "peak_bytes": 2,
            "current_bytes": 2,
            "empty_harness_peak_bytes": 1,
            "extra_peak_bytes": 1,
        },
        "product_subprocesses": 0,
    }


def test_paired_cli_requires_pristine_repo_and_frozen_operation_set() -> None:
    module = _load_harness()
    args = module.build_parser().parse_args(
        [
            "paired",
            "--baseline-root",
            "baseline",
            "--final-root",
            "final",
            "--repo",
            "pristine",
            "--manifest",
            "manifest.json",
            "--operation-set",
            "protected_small_entry_comparable",
            "--output",
            "report.json",
        ]
    )
    assert args.repo == Path("pristine")
    assert args.operation_set == "protected_small_entry_comparable"


def test_frozen_protected_cases_resolve_to_approved_generated_queries() -> None:
    module = _load_harness()
    manifest = ROOT / "tests" / "fixtures" / "p6_performance" / "workload_manifest.json"
    contract = json.loads(manifest.read_text(encoding="utf-8"))
    query_cases = module._paired_query_cases(manifest)

    resolved = {
        operation_id: module._paired_operation_case(operation_id, query_cases)
        for operation_id in contract["protected_small_entry_comparable"]
    }
    assert resolved["query_path_symbol_ambiguous"] == (
        "query",
        "path_symbol_ambiguity",
        "AmbiguousGateway",
    )
    assert resolved["query_signal"] == (
        "query",
        "signal_metadata",
        "signalroute",
    )
    assert resolved["explore_p4_bounded"] == (
        "explore",
        "p4_explore",
        "checkout endpoint implementation tests",
    )


def test_paired_uses_one_harness_and_selected_implementation_product(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = _load_harness()
    implementation = tmp_path / "implementation"
    repo = tmp_path / "sample"
    (implementation / "src").mkdir(parents=True)
    repo.mkdir()
    captured: dict[str, Any] = {}

    def fake_run(command: list[str], **kwargs: Any) -> Any:
        captured["command"] = command
        captured.update(kwargs)
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps(_measured()),
            stderr="",
        )

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    result = module._run_paired_worker(
        implementation,
        "query",
        repo,
        "lexical_high",
        "lexicalburst",
    )

    assert result["duration_ms"] == 1.0
    assert captured["command"] == [
        module.sys.executable,
        str(HARNESS),
        "__measure",
    ]
    assert captured["cwd"] == implementation
    assert captured["env"]["PYTHONPATH"] == str(implementation / "src")
    request = json.loads(captured["input"])
    assert request["kind"] == "operation"
    assert request["operation"] == "query"
    assert request["operation_case_id"] == "lexical_high"
    assert request["case_id"] == "lexicalburst"
    assert "--help" not in captured["command"]


def test_paired_clones_each_side_per_pair_and_emits_private_verifiable_report(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = _load_harness()
    repo, manifest = _pristine_repo_and_manifest(module, tmp_path)
    baseline_root = tmp_path / "baseline"
    final_root = tmp_path / "final"
    identities = {
        baseline_root.resolve(): {
            "implementation_commit": "1" * 40,
            "production_tree": "2" * 40,
        },
        final_root.resolve(): {
            "implementation_commit": "3" * 40,
            "production_tree": "4" * 40,
        },
    }
    calls: list[tuple[str, str, str, str]] = []

    monkeypatch.setattr(module, "_paired_root_identity", identities.__getitem__)
    monkeypatch.setattr(module, "_calibration", _calibration)

    def fake_worker(
        root: Path,
        operation: str,
        clone: Path,
        case_id: str,
        question: str,
    ) -> dict[str, Any]:
        side = root.name
        calls.append((side, operation, clone.as_posix(), case_id))
        if operation == "full_build":
            (clone / ".context-search").mkdir(exist_ok=True)
        return _measured(1.0 if side == "baseline" else 1.05)

    monkeypatch.setattr(module, "_run_paired_worker", fake_worker)
    report = module.paired_runs(
        baseline_root,
        final_root,
        repo,
        manifest,
        pair_count=2,
        operation_set="protected_small_entry_comparable",
    )

    operations = report["protected_operation_ids"]
    assert operations == [
        "full_build",
        "authoritative_noop",
        "status_quick",
        "query_lexical_high",
        "explore_p4_bounded",
    ]
    assert len(report["samples"]) == len(operations) * 2 * 2
    assert all(
        sample["repository_fingerprint_sha256"]
        == report["workload"]["pristine_fingerprint_sha256"]
        for sample in report["samples"]
    )
    assert [sample["side"] for sample in report["samples"][:4]] == [
        "baseline",
        "final",
        "baseline",
        "final",
    ]
    # Every clone gets an untimed full build. Supported operations add timed calls;
    # current Task-1 status is explicit unsupported on both implementations.
    assert len(calls) == len(operations) * 2 * 2 + (len(operations) - 1) * 2 * 2
    clone_paths = [clone for _, _, clone, _ in calls]
    assert len(set(clone_paths)) == len(operations) * 2 * 2
    assert sorted(clone_paths.count(clone) for clone in set(clone_paths)) == (
        [1] * 4 + [2] * ((len(operations) - 1) * 2 * 2)
    )
    assert [side for side, _, _, _ in calls[:4]] == [
        "baseline",
        "final",
        "baseline",
        "final",
    ]
    for operation_id in operations:
        for pair_id in ("pair-001", "pair-002"):
            measured = [
                sample
                for sample in report["samples"]
                if sample["operation_id"] == operation_id
                and sample["pair_id"] == pair_id
            ]
            assert len(measured) == 2
            assert measured[0]["side"] == "baseline"
            assert measured[1]["side"] == "final"
            assert calls
    status_samples = [
        sample for sample in report["samples"]
        if sample["operation_id"] == "status_quick"
    ]
    assert {sample["outcome"] for sample in status_samples} == {"unsupported"}
    assert all(sample["duration_ms"] is None for sample in status_samples)
    query_samples = [
        sample for sample in report["samples"]
        if sample["operation_id"] == "query_lexical_high"
    ]
    assert {sample["case_id"] for sample in query_samples} == {"lexical_high"}
    payload = json.dumps(report, sort_keys=True)
    assert str(tmp_path) not in payload
    assert "lexicalburst" not in payload
    assert "baseline_root" not in payload
    assert "final_root" not in payload
    assert not list(tmp_path.glob("p6-paired-*"))


def test_paired_rejects_dirty_or_unfrozen_inputs_and_cleans_after_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = _load_harness()
    repo, manifest = _pristine_repo_and_manifest(module, tmp_path)
    baseline_root = tmp_path / "baseline"
    final_root = tmp_path / "final"
    monkeypatch.setattr(
        module,
        "_paired_root_identity",
        lambda root: {
            "implementation_commit": GIT,
            "production_tree": GIT,
        },
    )
    monkeypatch.setattr(module, "_calibration", _calibration)

    contract = json.loads(manifest.read_text(encoding="utf-8"))
    contract["expected_fingerprints"]["smoke"] = "2" * 64
    manifest.write_text(json.dumps(contract), encoding="utf-8")
    with pytest.raises(ValueError, match="frozen manifest"):
        module.paired_runs(
            baseline_root,
            final_root,
            repo,
            manifest,
            pair_count=1,
            operation_set="protected_small_entry_comparable",
        )

    contract["expected_fingerprints"]["smoke"] = module._repository_fingerprint(repo)
    manifest.write_text(json.dumps(contract), encoding="utf-8")
    attempts = 0

    def fail_after_setup(
        root: Path,
        operation: str,
        clone: Path,
        case_id: str,
        question: str,
    ) -> dict[str, Any]:
        nonlocal attempts
        attempts += 1
        if attempts == 3:
            raise ValueError("injected measurement failure")
        (clone / ".context-search").mkdir(exist_ok=True)
        return _measured()

    monkeypatch.setattr(module, "_run_paired_worker", fail_after_setup)
    with pytest.raises(ValueError, match="injected measurement failure"):
        module.paired_runs(
            baseline_root,
            final_root,
            repo,
            manifest,
            pair_count=1,
            operation_set="protected_small_entry_comparable",
        )
    assert not list(tmp_path.glob("p6-paired-*"))


def test_paired_root_validation_requires_distinct_fully_clean_git_roots(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = _load_harness()
    root = tmp_path / "implementation"
    (root / "src" / "context_search_tool").mkdir(parents=True)
    monkeypatch.setattr(
        module.subprocess,
        "check_output",
        lambda *args, **kwargs: " M docs/private.txt\n",
    )
    with pytest.raises(ValueError, match="dirty"):
        module._paired_root_identity(root)

    repo, manifest = _pristine_repo_and_manifest(module, tmp_path)
    with pytest.raises(ValueError, match="distinct"):
        module.paired_runs(
            root,
            root,
            repo,
            manifest,
            pair_count=1,
            operation_set="protected_small_entry_comparable",
        )
