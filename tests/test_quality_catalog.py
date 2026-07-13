from __future__ import annotations

import hashlib
import json
import re
from dataclasses import replace
from pathlib import Path

import pytest

from context_search_tool.quality.cases import (
    Gate,
    LegacyProvenance,
    Matcher,
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

EXPECTED_PROFILE_CONFIGS = {
    "ci": {
        "embedding": {
            "provider": "hash",
            "model": "hash-v1",
            "dimensions": 384,
        },
        "query_planner": {"enabled": False},
    },
    "smoke": {
        "embedding": {
            "provider": "hash",
            "model": "hash-v1",
            "dimensions": 384,
        },
        "query_planner": {"enabled": False},
    },
    "planner": {
        "embedding": {
            "provider": "hash",
            "model": "hash-v1",
            "dimensions": 384,
        },
        "query_planner": {
            "enabled": True,
            "provider": "ollama",
            "model": "qwen3.5:4b-mlx",
            "timeout_seconds": 30,
        },
    },
    "calibration_bge": {
        "embedding": {
            "provider": "bge",
            "model": "bge-m3",
            "dimensions": 1024,
        },
        "query_planner": {"enabled": False},
    },
    "ab_hash": {
        "embedding": {
            "provider": "hash",
            "model": "hash-v1",
            "dimensions": 384,
        },
        "query_planner": {"enabled": False},
    },
    "ab_bge": {
        "embedding": {
            "provider": "bge",
            "model": "bge-m3",
            "dimensions": 1024,
        },
        "query_planner": {"enabled": False},
    },
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

EXPECTED_NEW_CASE_DEFAULTS = {
    "mode": "results",
    "metric_k": None,
    "relevance_matchers": (),
    "noise_matchers": (),
    "expected_at_least_top_k": (),
    "absent_top_k": (),
    "outranks": (),
    "forbidden_above": (),
    "anchor_expected": (),
    "known_gap_reason": "",
    "notes": "",
    "legacy": None,
}

EXPECTED_NEW_CASES = {
    "java_spring_mini/apply-audit-endpoint": {
        **EXPECTED_NEW_CASE_DEFAULTS,
        "repo_key": "java_spring_mini",
        "case_id": "apply-audit-endpoint",
        "query": "/apply/audit/pageEs INVOLVED_BY_ME",
        "profiles": (),
        "tags": ("java_spring", "exact_identifier", "entrypoint"),
        "gate": Gate.REQUIRED,
        "expected_top_k": (
            {
                "path": "src/main/java/com/example/audit/ResourceApplyAuditController.java",
                "top_k": 3,
            },
        ),
        "expected_any_top_k": (),
        "preferred_rank": (
            {
                "path": "src/main/java/com/example/audit/ResourceApplyAuditController.java",
                "top_k": 3,
                "max_rank": 3,
                "role": "entrypoint",
            },
        ),
    },
    "java_spring_mini/workbench-audit-localized-cjk": {
        **EXPECTED_NEW_CASE_DEFAULTS,
        "repo_key": "java_spring_mini",
        "case_id": "workbench-audit-localized-cjk",
        "query": "工作台统计 待我审核",
        "profiles": (),
        "tags": ("java_spring", "localized_cjk", "entrypoint"),
        "gate": Gate.REQUIRED,
        "expected_top_k": (
            {
                "path": "src/main/java/com/example/audit/ApplyAuditController.java",
                "top_k": 3,
            },
        ),
        "expected_any_top_k": (),
        "preferred_rank": (
            {
                "path": "src/main/java/com/example/audit/ApplyAuditController.java",
                "top_k": 3,
                "max_rank": 3,
                "role": "entrypoint",
            },
        ),
    },
    "psf_requests/cookies-between-calls": {
        **EXPECTED_NEW_CASE_DEFAULTS,
        "repo_key": "psf_requests",
        "case_id": "cookies-between-calls",
        "query": "where does requests keep cookies between multiple calls in a client session",
        "profiles": ("planner",),
        "tags": ("python", "planner", "natural_language"),
        "gate": Gate.REQUIRED,
        "expected_top_k": (),
        "expected_any_top_k": (
            {
                "matchers": (
                    {"path": "src/requests/sessions.py"},
                    {"path": "src/requests/cookies.py"},
                ),
                "top_k": 5,
            },
        ),
        "preferred_rank": (),
    },
    "psf_requests/retry-proxy-pooling-natural": {
        **EXPECTED_NEW_CASE_DEFAULTS,
        "repo_key": "psf_requests",
        "case_id": "retry-proxy-pooling-natural",
        "query": "where are retries proxy connections and connection pools configured for sending requests",
        "profiles": ("planner",),
        "tags": ("python", "planner", "natural_language"),
        "gate": Gate.REQUIRED,
        "expected_top_k": (
            {"path": "src/requests/adapters.py", "top_k": 5},
        ),
        "expected_any_top_k": (),
        "preferred_rank": (),
    },
    "psf_requests/stream-response-body-natural": {
        **EXPECTED_NEW_CASE_DEFAULTS,
        "repo_key": "psf_requests",
        "case_id": "stream-response-body-natural",
        "query": "where can response body be streamed in chunks without loading everything",
        "profiles": ("planner",),
        "tags": ("python", "planner", "natural_language"),
        "gate": Gate.REQUIRED,
        "expected_top_k": (
            {"path": "src/requests/models.py", "top_k": 5},
        ),
        "expected_any_top_k": (),
        "preferred_rank": (),
    },
    "cross_language_dashboard/dashboard-cross-language": {
        **EXPECTED_NEW_CASE_DEFAULTS,
        "repo_key": "cross_language_dashboard",
        "case_id": "dashboard-cross-language",
        "query": "数据看板统计图表功能",
        "profiles": ("planner",),
        "tags": ("java_spring", "cross_language", "entrypoint"),
        "gate": Gate.REQUIRED,
        "expected_top_k": (
            {
                "path": "src/main/java/com/example/dashboard/DashboardController.java",
                "top_k": 5,
            },
        ),
        "expected_any_top_k": (
            {
                "matchers": (
                    {
                        "path": "src/main/java/com/example/dashboard/StatisticsService.java"
                    },
                    {
                        "path": "src/main/java/com/example/dashboard/ChartService.java"
                    },
                ),
                "top_k": 5,
            },
        ),
        "preferred_rank": (
            {
                "path": "src/main/java/com/example/dashboard/DashboardController.java",
                "top_k": 5,
                "max_rank": 3,
                "role": "entrypoint",
            },
        ),
    },
}

EXPECTED_LEGACY_PAIRS = {
    ("generic_baseline_quality", "imagebed/go-upload-handler"),
    ("generic_baseline_quality", "imagebed/go-auth-middleware"),
    ("generic_baseline_quality", "imagebed/go-storage-implementations"),
    ("generic_baseline_quality", "imagebed/go-delete-handler"),
    ("generic_baseline_quality", "imagebed/go-route-registration"),
    ("generic_baseline_quality", "env_change/tauri-commands"),
    ("generic_baseline_quality", "env_change/engine-apply-restore"),
    ("generic_baseline_quality", "env_change/frontend-invoke"),
    ("generic_baseline_quality", "env_change/settings-persistence"),
    ("generic_baseline_quality", "investment_assistant/frontend-auth-store"),
    ("generic_baseline_quality", "investment_assistant/collector-handler"),
    ("generic_baseline_quality", "investment_assistant/frontend-sse-composable"),
    ("generic_baseline_quality", "investment_assistant/collector-fund-service"),
    ("generic_baseline_quality", "investment_assistant/collector-nav-fetcher"),
    ("generic_baseline_quality", "investment_assistant/collector-scheduler"),
    ("generic_baseline_quality", "investment_assistant/java-ai-sse-controller"),
    ("generic_baseline_quality", "program_tool/watermark-remover"),
    ("generic_baseline_quality", "program_tool/mqtt-tool"),
    ("generic_baseline_quality", "program_tool/qrcode-tool"),
    ("generic_baseline_quality", "program_tool/json-to-entity"),
    ("generic_baseline_quality", "program_tool/app-layout-theme"),
    ("generic_baseline_quality", "program_tool/ai-chat"),
    (
        "retrieval_calibration",
        "operation_client/operation-client-auth-login-register",
    ),
    (
        "retrieval_calibration",
        "operation_client/operation-client-station-device-list",
    ),
    (
        "retrieval_calibration",
        "operation_client/operation-client-feedback-sms",
    ),
    ("retrieval_calibration", "console_iot/console-iot-equipment-list"),
    ("retrieval_calibration", "console_iot/console-iot-access-control"),
    ("retrieval_calibration", "console_iot/console-iot-device-status"),
    ("retrieval_calibration", "console_iot/console-iot-alarm"),
    ("retrieval_calibration", "console_iot/console-iot-user-auth"),
    ("ab_comparison", "embedding_ab/embedding-ab-access-validation"),
    ("ab_comparison", "embedding_ab/embedding-ab-whitelist-management"),
    ("ab_comparison", "embedding_ab/embedding-ab-order-cancel"),
}

GENERIC_TAGS = {
    "go-upload-handler": ("generic", "go"),
    "go-auth-middleware": ("generic", "go"),
    "go-storage-implementations": ("generic", "go"),
    "go-delete-handler": ("generic", "go"),
    "go-route-registration": ("generic", "go"),
    "tauri-commands": ("generic", "rust", "typescript"),
    "engine-apply-restore": ("generic", "rust", "typescript"),
    "frontend-invoke": ("generic", "rust", "typescript"),
    "settings-persistence": ("generic", "rust", "typescript"),
    "frontend-auth-store": ("monorepo", "frontend"),
    "collector-handler": ("monorepo", "go"),
    "frontend-sse-composable": ("monorepo", "frontend"),
    "collector-fund-service": ("monorepo", "go"),
    "collector-nav-fetcher": ("monorepo", "go"),
    "collector-scheduler": ("monorepo", "go"),
    "java-ai-sse-controller": ("monorepo", "java_spring"),
    "watermark-remover": ("frontend", "vue", "entrypoint"),
    "mqtt-tool": ("frontend", "vue"),
    "qrcode-tool": ("frontend", "vue", "entrypoint"),
    "json-to-entity": ("frontend", "vue"),
    "app-layout-theme": ("frontend", "vue"),
    "ai-chat": ("frontend", "vue", "entrypoint"),
}

CALIBRATION_TAGS = {
    "operation-client-auth-login-register": ("java_spring", "chinese_query"),
    "operation-client-station-device-list": ("java_spring", "chinese_query"),
    "operation-client-feedback-sms": ("java_spring", "chinese_query"),
    "console-iot-equipment-list": ("java_spring", "chinese_query"),
    "console-iot-access-control": ("java_spring", "chinese_query"),
    "console-iot-device-status": ("java_spring", "chinese_query"),
    "console-iot-alarm": ("java_spring", "chinese_query"),
    "console-iot-user-auth": ("java_spring", "chinese_query"),
}


def _catalog_cases() -> dict[str, QualityCase]:
    fixture = load_quality_fixture(CATALOG_PATH)
    return {
        f"{repo.repo_key}/{case.case_id}": case
        for repo in fixture.repos
        for case in repo.queries
    }


def _matcher_manifest(matcher: Matcher) -> dict[str, str]:
    for selector in ("path", "glob", "contains"):
        value = getattr(matcher, selector)
        if value is not None:
            return {selector: value}
    raise AssertionError("matcher has no selector")


def _top_k_manifest(items) -> tuple[dict[str, object], ...]:
    return tuple(
        {**_matcher_manifest(item.matcher), "top_k": item.top_k}
        for item in items
    )


def _expected_any_manifest(items) -> tuple[dict[str, object], ...]:
    return tuple(
        {
            "matchers": tuple(_matcher_manifest(matcher) for matcher in item.matchers),
            "top_k": item.top_k,
        }
        for item in items
    )


def _preferred_rank_manifest(items) -> tuple[dict[str, object], ...]:
    return tuple(
        {
            **_matcher_manifest(item.matcher),
            "top_k": item.top_k,
            "max_rank": item.max_rank,
            "role": item.role,
        }
        for item in items
    )


def _new_case_manifest(key: str, case: QualityCase) -> dict[str, object]:
    repo_key, _ = key.split("/", 1)
    return {
        "repo_key": repo_key,
        "case_id": case.case_id,
        "query": case.query,
        "profiles": case.profiles,
        "tags": case.tags,
        "mode": case.mode,
        "gate": case.gate,
        "metric_k": case.metric_k,
        "relevance_matchers": case.relevance_matchers,
        "noise_matchers": case.noise_matchers,
        "expected_top_k": _top_k_manifest(case.expected_top_k),
        "expected_any_top_k": _expected_any_manifest(case.expected_any_top_k),
        "expected_at_least_top_k": case.expected_at_least_top_k,
        "preferred_rank": _preferred_rank_manifest(case.preferred_rank),
        "absent_top_k": case.absent_top_k,
        "outranks": case.outranks,
        "forbidden_above": case.forbidden_above,
        "anchor_expected": case.anchor_expected,
        "known_gap_reason": case.known_gap_reason,
        "notes": case.notes,
        "legacy": case.legacy,
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

    assert fixture.profile_configs == EXPECTED_PROFILE_CONFIGS
    assert len(cases) == 39
    assert "program_tool/qrcode-tool" in cases
    assert "program_tool_snapshot/qrcode-entrypoint" not in cases
    assert cases["cross_language_dashboard/dashboard-cross-language"].tags == (
        "java_spring", "cross_language", "entrypoint"
    )


def test_catalog_new_case_inventory_matches_approved_manifest() -> None:
    cases = _catalog_cases()

    assert {
        key for key, case in cases.items() if case.legacy is None
    } == EXPECTED_NEW_CASES.keys()


@pytest.mark.parametrize("key", EXPECTED_NEW_CASES)
def test_catalog_new_case_matches_approved_manifest(key: str) -> None:
    case = _catalog_cases()[key]

    assert _new_case_manifest(key, case) == EXPECTED_NEW_CASES[key]


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
    cases = _catalog_cases()
    provenance = [case.legacy for case in cases.values() if case.legacy is not None]
    actual_pairs = {(item.fixture, item.key) for item in provenance}
    provenance_counts = {
        fixture: sum(item.fixture == fixture for item in provenance)
        for fixture in {
            "generic_baseline_quality",
            "retrieval_calibration",
            "ab_comparison",
        }
    }

    assert actual_pairs == EXPECTED_LEGACY_PAIRS
    assert provenance_counts == {
        "generic_baseline_quality": 22,
        "retrieval_calibration": 8,
        "ab_comparison": 3,
    }

    generic_ids = {
        key.rsplit("/", 1)[1]
        for fixture, key in EXPECTED_LEGACY_PAIRS
        if fixture == "generic_baseline_quality"
    }
    calibration_ids = {
        key.rsplit("/", 1)[1]
        for fixture, key in EXPECTED_LEGACY_PAIRS
        if fixture == "retrieval_calibration"
    }
    assert GENERIC_TAGS.keys() == generic_ids
    assert CALIBRATION_TAGS.keys() == calibration_ids

    for fixture, key in EXPECTED_LEGACY_PAIRS:
        case = cases[key]
        assert case.legacy == LegacyProvenance(fixture=fixture, key=key)
        if fixture == "generic_baseline_quality":
            assert case.tags == GENERIC_TAGS[case.case_id]
        elif fixture == "retrieval_calibration":
            assert case.tags == CALIBRATION_TAGS[case.case_id]
        else:
            assert case.tags == ()
