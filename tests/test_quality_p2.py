from __future__ import annotations

from pathlib import Path

from context_search_tool.quality.runner import run_quality_fixture


CATALOG = (
    Path(__file__).parent
    / "fixtures"
    / "retrieval_quality"
    / "queries.json"
)


def test_phase_two_context_pack_profile_is_deterministic_offline() -> None:
    report = run_quality_fixture(CATALOG, "p2_context_pack", None, None)

    assert {
        key: value
        for key, value in report["aggregate"].items()
        if key != "metrics"
    } == {
        "total": 5,
        "selected": 5,
        "attempted": 5,
        "executed": 5,
        "passed": 5,
        "failed": 0,
        "skipped": 0,
        "known_gaps": 0,
        "informational": 0,
        "errors": 0,
    }
    overall = report["aggregate"]["metrics"]["overall"]
    assert overall["context_completeness"] == {"count": 5, "mean": 1.0}
    assert overall["context_expected_count"] == {"count": 5, "mean": 2.0}

    cases = {
        (case["repo_key"], case["case_id"]): case
        for case in report["cases"]
    }
    assert set(cases) == {
        ("context_pack_java", "workspace-page-flow"),
        ("context_pack_java", "workspace-test-file"),
        ("context_pack_java", "workspace-service-symbol"),
        ("context_pack_frontend", "qrcode-feature-context"),
        ("context_pack_docs", "program-tool-developer-docs"),
    }
    assert all(
        case["context_pack"]["status"] == "ready"
        for case in cases.values()
    )
    assert {
        key: case["context_pack"]["confidence"]
        for key, case in cases.items()
    } == {
        ("context_pack_java", "workspace-page-flow"): "high",
        ("context_pack_java", "workspace-test-file"): "high",
        ("context_pack_java", "workspace-service-symbol"): "high",
        ("context_pack_frontend", "qrcode-feature-context"): "medium",
        ("context_pack_docs", "program-tool-developer-docs"): "medium",
    }
    assert cases[
        ("context_pack_java", "workspace-service-symbol")
    ]["metrics"]["required_missing_count"] == 0
    assert cases[
        ("context_pack_frontend", "qrcode-feature-context")
    ]["metrics"]["recommended_missing_count"] == 1
    assert cases[
        ("context_pack_docs", "program-tool-developer-docs")
    ]["metrics"]["context_content_bytes"] == 93
