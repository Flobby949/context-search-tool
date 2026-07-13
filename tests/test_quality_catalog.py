from __future__ import annotations

import json
import re
from dataclasses import replace
from pathlib import Path

from context_search_tool.quality.cases import (
    Gate,
    LegacyProvenance,
    QualityCase,
    adapt_legacy_query_case,
    load_quality_fixture,
)


ROOT = Path(__file__).parent
CATALOG_PATH = ROOT / "fixtures" / "retrieval_quality" / "queries.json"
LEGACY_GENERIC = ROOT / "fixtures" / "generic_baseline_quality" / "queries.json"
LEGACY_CALIBRATION = ROOT / "fixtures" / "retrieval_calibration" / "queries.json"
LEGACY_AB = ROOT / "fixtures" / "ab_comparison" / "queries.json"
CJK_RE = re.compile(r"[\u3400-\u9fff]")

CALIBRATION_IDS = {
    ("operation_client", "账号密码登录注册"): "operation-client-auth-login-register",
    ("operation_client", "驿站设备列表"): "operation-client-station-device-list",
    ("operation_client", "发布意见反馈 发送短信"): "operation-client-feedback-sms",
    ("console_iot", "设备列表"): "console-iot-equipment-list",
    ("console_iot", "开门控制"): "console-iot-access-control",
    ("console_iot", "IOT设备状态"): "console-iot-device-status",
    ("console_iot", "设备告警"): "console-iot-alarm",
    ("console_iot", "用户登录认证"): "console-iot-user-auth",
}

AB_IDS = (
    "embedding-ab-access-validation",
    "embedding-ab-whitelist-management",
    "embedding-ab-order-cancel",
)


def _catalog_cases() -> dict[str, QualityCase]:
    fixture = load_quality_fixture(CATALOG_PATH)
    return {
        f"{repo.repo_key}/{case.case_id}": case
        for repo in fixture.repos
        for case in repo.queries
    }


def _without_catalog_metadata(case: QualityCase) -> QualityCase:
    return replace(
        case,
        profiles=(),
        tags=(),
        legacy=None,
        preferred_rank=tuple(
            replace(preferred, role="") for preferred in case.preferred_rank
        ),
    )


def test_cross_language_dashboard_snapshot_contains_no_cjk() -> None:
    root = ROOT / "fixtures" / "real_projects" / "cross_language_dashboard"
    files = sorted(root.rglob("*.java"))

    assert [path.name for path in files] == [
        "ChartService.java",
        "DashboardController.java",
        "StatisticsService.java",
    ]
    assert all(CJK_RE.search(path.read_text(encoding="utf-8")) is None for path in files)


def test_catalog_profile_registry_and_inventory() -> None:
    fixture = load_quality_fixture(CATALOG_PATH)
    cases = _catalog_cases()

    assert set(fixture.profile_configs) == {
        "ci", "smoke", "planner", "calibration_bge", "ab_hash", "ab_bge"
    }
    assert len(cases) == 39
    assert "program_tool/qrcode-tool" in cases
    assert "program_tool_snapshot/qrcode-entrypoint" not in cases
    assert cases["cross_language_dashboard/dashboard-cross-language"].tags == (
        "java_spring", "cross_language", "entrypoint"
    )


def test_generic_legacy_parity() -> None:
    canonical = _catalog_cases()
    legacy_repos = json.loads(LEGACY_GENERIC.read_text(encoding="utf-8"))

    for raw_repo in legacy_repos:
        for raw_case in raw_repo["queries"]:
            key = f"{raw_repo['repo_key']}/{raw_case['id']}"
            assert _without_catalog_metadata(canonical[key]) == adapt_legacy_query_case(
                raw_case
            )


def test_calibration_legacy_parity() -> None:
    canonical = _catalog_cases()
    legacy_cases = json.loads(LEGACY_CALIBRATION.read_text(encoding="utf-8"))

    for raw_case in legacy_cases:
        case_id = CALIBRATION_IDS[(raw_case["repo_key"], raw_case["query"])]
        key = f"{raw_case['repo_key']}/{case_id}"
        adapted = adapt_legacy_query_case(
            {
                "id": case_id,
                **{name: value for name, value in raw_case.items() if name != "repo_key"},
            }
        )
        assert _without_catalog_metadata(canonical[key]) == adapted


def test_ab_legacy_parity() -> None:
    canonical = _catalog_cases()
    legacy_cases = json.loads(LEGACY_AB.read_text(encoding="utf-8"))

    for case_id, raw_case in zip(AB_IDS, legacy_cases, strict=True):
        case = canonical[f"embedding_ab/{case_id}"]
        assert case.query == raw_case["query"]
        assert case.gate is Gate.INFORMATIONAL
        assert case.metric_k == 12
        assert [matcher.contains for matcher in case.relevance_matchers] == raw_case[
            "expected_relevant"
        ]
        assert [matcher.contains for matcher in case.noise_matchers] == raw_case[
            "expected_noise"
        ]
        assert case.legacy == LegacyProvenance(
            fixture="ab_comparison",
            key=f"embedding_ab/{case_id}",
        )


def test_legacy_provenance_inventory() -> None:
    provenance = [
        case.legacy
        for case in _catalog_cases().values()
        if case.legacy is not None
    ]
    provenance_counts = {
        fixture: sum(item.fixture == fixture for item in provenance)
        for fixture in {
            "generic_baseline_quality",
            "retrieval_calibration",
            "ab_comparison",
        }
    }

    assert len({(item.fixture, item.key) for item in provenance}) == 33
    assert provenance_counts == {
        "generic_baseline_quality": 22,
        "retrieval_calibration": 8,
        "ab_comparison": 3,
    }
