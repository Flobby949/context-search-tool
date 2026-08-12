from pathlib import Path

from context_search_tool.quality.runner import run_quality_fixture


FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "retrieval_quality"
    / "p0_effects.json"
)


def test_committed_p0_effects_profile_closes_all_required_gates() -> None:
    report = run_quality_fixture(FIXTURE, "p0_effects", None, None)
    repeated = run_quality_fixture(FIXTURE, "p0_effects", None, None)

    assert {
        key: report["aggregate"][key]
        for key in ("selected", "executed", "passed", "failed", "errors")
    } == {
        "selected": 3,
        "executed": 3,
        "passed": 3,
        "failed": 0,
        "errors": 0,
    }
    cases = {case["case_id"]: case for case in report["cases"]}
    assert set(cases) == {
        "scoped-monorepo-noise",
        "scoped-graph-boundary",
        "no-needs-readiness",
    }
    assert all(
        case["metrics"]["scope_escape_count"] == 0
        for case in cases.values()
    )
    assert cases["scoped-monorepo-noise"]["metrics"]["recall_at_5"] == 1.0
    assert cases["scoped-monorepo-noise"]["metrics"]["mrr"] == 1.0
    assert cases["scoped-monorepo-noise"]["metrics"]["noise_top5"] == 0
    no_needs = cases["no-needs-readiness"]
    assert no_needs["context_pack"] == {
        "status": "partial",
        "confidence": "low",
    }
    assert no_needs["metrics"]["evidence_need_count"] == 0
    assert no_needs["metrics"]["false_ready_count"] == 0
    assert cases["scoped-graph-boundary"]["metrics"]["false_ready_count"] == 0
    assert _stable_projection(report) == _stable_projection(repeated)


def _stable_projection(report: dict) -> list[dict]:
    return [
        {
            "case_id": case["case_id"],
            "status": case["status"],
            "top_results": case["top_results"],
            "context_pack": case.get("context_pack"),
            "metrics": {
                name: value
                for name, value in case["metrics"].items()
                if name != "latency_ms"
            },
        }
        for case in report["cases"]
    ]
