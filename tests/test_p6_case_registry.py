from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "scripts" / "p6_benchmark.py"
MANIFEST = ROOT / "tests" / "fixtures" / "p6_performance" / "workload_manifest.json"
QUERY_CASES = ROOT / "tests" / "fixtures" / "p6_performance" / "query_cases.json"


def _load_harness() -> Any:
    spec = importlib.util.spec_from_file_location("p6_case_registry", HARNESS)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _contract() -> dict[str, Any]:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def test_registry_freezes_complete_baseline_case_state_and_sample_matrix() -> None:
    contract = _contract()
    registry = contract["benchmark_registry"]
    query_contract = json.loads(QUERY_CASES.read_text(encoding="utf-8"))

    assert registry["version"] == "p6-benchmark-registry-v1"
    assert {
        state["id"]: (state["acceptance_evidence"], state["informational_only"])
        for state in registry["measurement_states"]
    } == {
        "cli_process_cold": (True, False),
        "mcp_resident_warm": (True, False),
        "filesystem_cold_diagnostic": (False, True),
    }
    cases = {(case["operation_id"], case["case_id"]): case for case in registry["cases"]}
    assert set(cases) == {
        ("full_build", "default"),
        ("authoritative_noop", "default"),
        ("stats", "default"),
        ("status_quick", "default"),
        ("status_verified", "default"),
        ("refresh_noop", "default"),
        ("refresh_one_file", "default"),
        *(("query", case_id) for case_id in query_contract["approved_generated_query_ids"][:-1]),
        ("explore", "p4_explore"),
    }
    assert all(case["planner_enabled"] is False for case in cases.values())

    def measurements(operation: str, case_id: str) -> dict[str, tuple[int, str]]:
        return {
            item["state"]: (item["sample_count"], item["baseline_outcome"])
            for item in cases[(operation, case_id)]["measurements"]
        }

    assert measurements("full_build", "default") == {
        "cli_process_cold": (5, "supported"),
        "filesystem_cold_diagnostic": (5, "unsupported"),
    }
    assert measurements("authoritative_noop", "default") == {
        "cli_process_cold": (5, "supported"),
        "filesystem_cold_diagnostic": (5, "unsupported"),
    }
    assert measurements("stats", "default") == {
        "cli_process_cold": (20, "supported")
    }
    assert measurements("status_quick", "default") == {
        "cli_process_cold": (20, "unsupported")
    }
    assert measurements("status_verified", "default") == {
        "cli_process_cold": (5, "unsupported")
    }
    for operation in ("refresh_noop", "refresh_one_file"):
        assert measurements(operation, "default") == {
            "cli_process_cold": (20, "unsupported")
        }
    for case_id in query_contract["approved_generated_query_ids"][:-1]:
        assert measurements("query", case_id) == {
            "cli_process_cold": (30, "supported"),
            "mcp_resident_warm": (30, "unsupported"),
            "filesystem_cold_diagnostic": (30, "unsupported"),
        }
    assert measurements("explore", "p4_explore") == {
        "cli_process_cold": (30, "supported"),
        "mcp_resident_warm": (30, "unsupported"),
    }

    module = _load_harness()
    assert module.workload_contract_sha256(contract) == contract["generator"][
        "contract_sha256"
    ]
    changed = deepcopy(contract)
    changed["benchmark_registry"]["cases"][0]["measurements"][0][
        "sample_count"
    ] += 1
    assert module.workload_contract_sha256(changed) != contract["generator"][
        "contract_sha256"
    ]


def test_query_case_ids_resolve_only_to_frozen_planner_off_tokens() -> None:
    module = _load_harness()
    contract = _contract()
    query_contract = json.loads(QUERY_CASES.read_text(encoding="utf-8"))
    expected_tokens = {case["id"]: case["query_token"] for case in query_contract["cases"]}

    for case_id, query_token in expected_tokens.items():
        operation = "explore" if case_id == "p4_explore" else "query"
        request = module._benchmark_request(
            contract,
            MANIFEST,
            tier="large",
            operation=operation,
            case_id=case_id,
            sample_count=30,
            measurement_state="mcp_resident_warm",
        )
        assert request["execution_case"] == query_token
        assert request["case"]["planner_enabled"] is False


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"sample_count": 1}, "sample count"),
        ({"case_id": "unknown"}, "operation/case"),
        ({"measurement_state": "mcp_resident_warm"}, "measurement state"),
        ({"tier": "stress"}, "operation/case"),
    ],
)
def test_registry_rejects_partial_or_mixed_case_requests(
    changes: dict[str, Any],
    message: str,
) -> None:
    module = _load_harness()
    arguments: dict[str, Any] = {
        "tier": "large",
        "operation": "status_quick",
        "case_id": "default",
        "sample_count": 20,
        "measurement_state": "cli_process_cold",
    }
    arguments.update(changes)
    with pytest.raises(ValueError, match=message):
        module._benchmark_request(_contract(), MANIFEST, **arguments)


def test_registry_rejects_open_or_unmapped_query_contracts() -> None:
    module = _load_harness()
    open_case = deepcopy(_contract())
    open_case["benchmark_registry"]["cases"][0]["unknown"] = True
    with pytest.raises(ValueError, match="not closed"):
        module._benchmark_request(
            open_case,
            MANIFEST,
            tier="smoke",
            operation="full_build",
            case_id="default",
            sample_count=5,
            measurement_state="cli_process_cold",
        )

    unmapped = deepcopy(_contract())
    query_case = next(
        case
        for case in unmapped["benchmark_registry"]["cases"]
        if case["operation_id"] == "query"
    )
    query_case["query_case_id"] = "p4_explore"
    with pytest.raises(ValueError, match="mapping is not closed"):
        module._benchmark_request(
            unmapped,
            MANIFEST,
            tier="large",
            operation="query",
            case_id="lexical_high",
            sample_count=30,
            measurement_state="cli_process_cold",
        )


def test_run_cli_has_no_single_sample_or_default_case_escape_hatch() -> None:
    module = _load_harness()
    parser = module.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(
            [
                "run",
                "--repo",
                "repo",
                "--manifest",
                "manifest.json",
                "--output",
                "report.json",
            ]
        )

    args = parser.parse_args(
        [
            "run",
            "--repo",
            "repo",
            "--manifest",
            "manifest.json",
            "--output",
            "report.json",
            "--operation",
            "query",
            "--case-id",
            "lexical_high",
            "--samples",
            "30",
            "--measurement-state",
            "cli_process_cold",
            "--checkpoint-dir",
            "report.checkpoints",
            "--resume",
        ]
    )
    assert (args.operation, args.case_id, args.samples, args.measurement_state) == (
        "query",
        "lexical_high",
        30,
        "cli_process_cold",
    )
    assert args.checkpoint_dir == Path("report.checkpoints")
    assert args.resume is True


def test_run_benchmark_rejects_one_sample_before_measurement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_harness()
    repo = tmp_path / "repo"
    (repo / "generated").mkdir(parents=True)
    monkeypatch.setattr(module, "_tier_for_repo", lambda *_: "smoke")
    monkeypatch.setattr(
        module,
        "_run_measurement_worker",
        lambda *_: (_ for _ in ()).throw(AssertionError("measurement must not start")),
    )

    with pytest.raises(ValueError, match="sample count"):
        module.run_benchmark(
            repo,
            MANIFEST,
            operation="full_build",
            case_id="default",
            sample_count=1,
            measurement_state="cli_process_cold",
            mode="baseline",
        )
