from __future__ import annotations

import hashlib
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

TASK9_JAVA_FIXTURE_SHA256 = {
    "real_projects/cross_language_dashboard/src/main/java/com/example/dashboard/ChartService.java": "732e723a2b0c122205a5860f2e94a3d5e60d0ed079574965a6398d49db2d02c7",
    "real_projects/cross_language_dashboard/src/main/java/com/example/dashboard/DashboardController.java": "fc05f4542828404ce55efb8b6c387fe017cd62d2a67fba60339b21d099fdee18",
    "real_projects/cross_language_dashboard/src/main/java/com/example/dashboard/StatisticsService.java": "48503013467710344246b5bd46bfc37fd3cd6c0021026e90dfed581632af4f24",
    "real_projects/embedding_ab/src/access/BlacklistManager.java": "5eaffbac1b58374b2d4220326c6a3ac7b286437167d3e8e037f8fbc48bc56fb8",
    "real_projects/embedding_ab/src/access/WhitelistValidation.java": "333d4c53f04101e3f706daba093a5d077f0a7e0f7839d5ffb6ad671882732782",
    "real_projects/embedding_ab/src/noise/RegionService.java": "7fd515f45d49d45251f74a6a0e27fc032553f52406158e3c04bc386aec62fa8b",
    "real_projects/embedding_ab/src/noise/RoleAnnouncement.java": "6ea6ef62f8e486db76310f403e8f6b19ef4232e0336c7f955978d4e8c087718f",
    "real_projects/embedding_ab/src/order/OrderService.java": "a21d91f5723d97b5d3d106db91c9e44b8744fe694f95821cd3b09cb8c70cdcdd",
}

EXPECTED_REPO_WIRING = (
    ("imagebed", ("smoke",), "CST_SMOKE_IMAGEBED_REPO", "imagebed", ""),
    ("env_change", ("smoke",), "CST_SMOKE_ENV_CHANGE_REPO", "env-change", ""),
    (
        "investment_assistant",
        ("smoke",),
        "CST_SMOKE_INVESTMENT_ASSISTANT_REPO",
        "Investment-Assistant",
        "",
    ),
    (
        "program_tool",
        ("ci", "smoke"),
        "CST_SMOKE_PROGRAM_TOOL_REPO",
        "program-tool",
        "tests/fixtures/real_projects/program_tool",
    ),
    (
        "java_spring_mini",
        ("ci",),
        "",
        "",
        "tests/fixtures/java-spring-mini",
    ),
    (
        "operation_client",
        ("calibration_bge",),
        "CST_CALIBRATION_OPERATION_CLIENT_REPO",
        "operation-client-api",
        "",
    ),
    (
        "console_iot",
        ("calibration_bge",),
        "CST_CALIBRATION_CONSOLE_IOT_REPO",
        "console-iot-api",
        "",
    ),
    (
        "psf_requests",
        ("planner",),
        "CST_PLANNER_REQUESTS_REPO",
        "requests",
        "",
    ),
    (
        "cross_language_dashboard",
        ("planner",),
        "",
        "",
        "tests/fixtures/real_projects/cross_language_dashboard",
    ),
    (
        "embedding_ab",
        ("ab_hash", "ab_bge"),
        "CST_QUALITY_AB_REPO",
        "embedding-ab",
        "tests/fixtures/real_projects/embedding_ab",
    ),
)

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


def test_task9_java_snapshots_match_approved_contents() -> None:
    fixture_root = ROOT / "fixtures"
    snapshot_roots = (
        fixture_root / "real_projects" / "cross_language_dashboard",
        fixture_root / "real_projects" / "embedding_ab",
    )
    files = sorted(path for root in snapshot_roots for path in root.rglob("*.java"))
    actual = {
        path.relative_to(fixture_root).as_posix(): hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
        for path in files
    }

    assert actual == TASK9_JAVA_FIXTURE_SHA256
    assert all(
        CJK_RE.search(path.read_text(encoding="utf-8")) is None
        for path in files
        if "cross_language_dashboard" in path.parts
    )


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


def test_catalog_repo_wiring_matches_approved_inventory() -> None:
    fixture = load_quality_fixture(CATALOG_PATH)
    wiring = tuple(
        (
            repo.repo_key,
            repo.profiles,
            repo.path_env,
            repo.repo_dir_name,
            repo.snapshot_path,
        )
        for repo in fixture.repos
    )

    assert wiring == EXPECTED_REPO_WIRING
    repos = {repo.repo_key: repo for repo in fixture.repos}
    assert repos["embedding_ab"].snapshot_path != repos[
        "cross_language_dashboard"
    ].snapshot_path


def test_catalog_case_profiles_match_approved_selection() -> None:
    cases = _catalog_cases()
    expected = {
        "psf_requests/cookies-between-calls": ("planner",),
        "psf_requests/retry-proxy-pooling-natural": ("planner",),
        "psf_requests/stream-response-body-natural": ("planner",),
        "cross_language_dashboard/dashboard-cross-language": ("planner",),
        **{
            f"embedding_ab/{case_id}": ("ab_hash", "ab_bge")
            for case_id in AB_IDS
        },
    }

    assert {
        key: case.profiles for key, case in cases.items() if case.profiles
    } == expected


def test_entrypoint_tags_and_preferred_rank_roles_are_consistent() -> None:
    cases = _catalog_cases()

    for key, case in cases.items():
        roles = [preferred.role for preferred in case.preferred_rank if preferred.role]
        expected_roles = ["entrypoint"] if "entrypoint" in case.tags else []
        assert roles == expected_roles, key

    program_tool_roles = {
        key: tuple(preferred.role for preferred in cases[key].preferred_rank)
        for key in (
            "program_tool/watermark-remover",
            "program_tool/qrcode-tool",
            "program_tool/ai-chat",
        )
    }
    assert program_tool_roles == {
        "program_tool/watermark-remover": ("entrypoint",),
        "program_tool/qrcode-tool": ("entrypoint",),
        "program_tool/ai-chat": ("entrypoint",),
    }


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
