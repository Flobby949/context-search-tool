from __future__ import annotations

import hashlib
import os
import re
import shutil
from pathlib import Path

import pytest

from context_search_tool import retrieval, tokenizer
from context_search_tool.config import DEFAULT_CONFIG
from context_search_tool.indexer import index_repository
from context_search_tool.models import QueryVariant
from context_search_tool.paths import index_dir_for
from context_search_tool.retrieval_core import candidates, ordering
from context_search_tool.quality.cases import (
    Gate,
    LegacyProvenance,
    Matcher,
    QualityCase,
    load_quality_fixture,
)
from context_search_tool.sqlite_store import SQLiteStore


ROOT = Path(__file__).parent
CATALOG_PATH = ROOT / "fixtures" / "retrieval_quality" / "queries.json"
CJK_RE = re.compile(r"[\u3400-\u9fff]")

TASK9_SNAPSHOT_SHA256 = {
    "real_projects/cross_language_dashboard/src/main/java/com/example/dashboard/ChartService.java": "732e723a2b0c122205a5860f2e94a3d5e60d0ed079574965a6398d49db2d02c7",
    "real_projects/cross_language_dashboard/src/main/java/com/example/dashboard/DashboardController.java": "fc05f4542828404ce55efb8b6c387fe017cd62d2a67fba60339b21d099fdee18",
    "real_projects/cross_language_dashboard/src/main/java/com/example/dashboard/StatisticsService.java": "48503013467710344246b5bd46bfc37fd3cd6c0021026e90dfed581632af4f24",
    "real_projects/embedding_ab/src/access/BlacklistManager.java": "5eaffbac1b58374b2d4220326c6a3ac7b286437167d3e8e037f8fbc48bc56fb8",
    "real_projects/embedding_ab/src/access/WhitelistValidation.java": "333d4c53f04101e3f706daba093a5d077f0a7e0f7839d5ffb6ad671882732782",
    "real_projects/embedding_ab/src/noise/RegionService.java": "7fd515f45d49d45251f74a6a0e27fc032553f52406158e3c04bc386aec62fa8b",
    "real_projects/embedding_ab/src/noise/RoleAnnouncement.java": "6ea6ef62f8e486db76310f403e8f6b19ef4232e0336c7f955978d4e8c087718f",
    "real_projects/embedding_ab/src/order/OrderService.java": "a21d91f5723d97b5d3d106db91c9e44b8744fe694f95821cd3b09cb8c70cdcdd",
}

P2_SNAPSHOT_SHA256 = {
    "context-pack-java/src/main/java/com/example/workspace/controller/WorkspaceController.java": "8eae09e3be12a8a7fd2d3fae0f0f78f6f976ea7d83c7d35a55c43f2f1a217836",
    "context-pack-java/src/main/java/com/example/workspace/dto/WorkspaceDto.java": "4fc2a6227363216628f45820feb35c61c35d9fe644eddeb98853803562bef08a",
    "context-pack-java/src/main/java/com/example/workspace/service/impl/WorkspaceServiceImpl.java": "a91c95dc085f344436a68f2d4e7e9faf60b0b5ad374c1fdd7542d974febff73d",
    "context-pack-java/src/test/java/com/example/workspace/controller/WorkspaceControllerTest.java": "6f92b729f375d82c7b9fb0a3f20a18d955814e21673797569be81433d35f84e3",
    "context-pack-docs/README.md": "13be45c211302d2cec0ff73310ab374f32ef73302189fc00998e53a3173347fc",
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
    "p1_vector_bge": {
        "embedding": {
            "provider": "bge",
            "model": "bge-m3",
            "dimensions": 1024,
        },
        "query_planner": {"enabled": False},
    },
    "p1_hybrid_bge": {
        "embedding": {
            "provider": "bge",
            "model": "bge-m3",
            "dimensions": 1024,
        },
        "query_planner": {
            "enabled": True,
            "provider": "ollama",
            "model": "qwen3.5:4b-mlx",
            "timeout_seconds": 30,
        },
    },
    "p2_context_pack": {
        "embedding": {
            "provider": "hash",
            "model": "hash-v1",
            "dimensions": 384,
        },
        "query_planner": {"enabled": False},
    },
    "p2_real_context": {
        "retrieval": {"final_top_k": 12},
        "embedding": {
            "provider": "hash",
            "model": "hash-v1",
            "dimensions": 384,
        },
        "query_planner": {"enabled": False},
    },
}

EXPECTED_REPO_WIRING = (
    ("imagebed", ("smoke",), "CST_SMOKE_IMAGEBED_REPO", "imagebed", "", {}),
    (
        "env_change",
        ("smoke",),
        "CST_SMOKE_ENV_CHANGE_REPO",
        "env-change",
        "",
        {},
    ),
    (
        "investment_assistant",
        ("smoke",),
        "CST_SMOKE_INVESTMENT_ASSISTANT_REPO",
        "Investment-Assistant",
        "",
        {},
    ),
    (
        "program_tool",
        ("ci", "smoke"),
        "CST_SMOKE_PROGRAM_TOOL_REPO",
        "program-tool",
        "tests/fixtures/real_projects/program_tool",
        {},
    ),
    (
        "java_spring_mini",
        ("ci", "p1_vector_bge", "p1_hybrid_bge"),
        "",
        "",
        "tests/fixtures/java-spring-mini",
        {},
    ),
    (
        "context_pack_java",
        ("p2_context_pack",),
        "",
        "",
        "tests/fixtures/context-pack-java",
        {},
    ),
    (
        "context_pack_frontend",
        ("p2_context_pack",),
        "",
        "",
        "tests/fixtures/real_projects/program_tool",
        {},
    ),
    (
        "context_pack_docs",
        ("p2_context_pack",),
        "",
        "",
        "tests/fixtures/context-pack-docs",
        {},
    ),
    (
        "operation_client",
        ("calibration_bge",),
        "CST_CALIBRATION_OPERATION_CLIENT_REPO",
        "operation-client-api",
        "",
        {},
    ),
    (
        "console_iot",
        ("calibration_bge",),
        "CST_CALIBRATION_CONSOLE_IOT_REPO",
        "console-iot-api",
        "",
        {},
    ),
    (
        "psf_requests",
        ("planner",),
        "CST_PLANNER_REQUESTS_REPO",
        "requests",
        "",
        {},
    ),
    (
        "cross_language_dashboard",
        ("planner", "p1_vector_bge", "p1_hybrid_bge"),
        "",
        "",
        "tests/fixtures/real_projects/cross_language_dashboard",
        {},
    ),
    (
        "embedding_ab",
        ("ab_hash", "ab_bge", "p1_vector_bge", "p1_hybrid_bge"),
        "CST_QUALITY_AB_REPO",
        "embedding-ab",
        "tests/fixtures/real_projects/embedding_ab",
        {},
    ),
    (
        "spring_petclinic",
        ("p2_real_context",),
        "",
        "",
        "",
        {},
    ),
)

AB_IDS = (
    "embedding-ab-access-validation",
    "embedding-ab-whitelist-management",
    "embedding-ab-order-cancel",
)

EXPECTED_AB_CASE_DEFAULTS = {
    "profiles": ("ab_hash", "ab_bge"),
    "tags": (),
    "mode": "results",
    "gate": Gate.INFORMATIONAL,
    "metric_k": 12,
    "expected_top_k": (),
    "expected_any_top_k": (),
    "expected_at_least_top_k": (),
    "preferred_rank": (),
    "absent_top_k": (),
    "outranks": (),
    "forbidden_above": (),
    "anchor_expected": (),
    "known_gap_reason": "",
    "notes": "",
    "profile_expectations": {},
    "expected_context_groups": {},
    "expected_pack_status": None,
    "minimum_context_confidence": None,
    "expected_need_matches": (),
    "maximum_pack_bytes": None,
    "maximum_truncated_items": None,
    "forbidden_next_query_patterns": (),
}

EXPECTED_AB_CASES = {
    "embedding-ab-access-validation": {
        **EXPECTED_AB_CASE_DEFAULTS,
        "case_id": "embedding-ab-access-validation",
        "query": "开门校验场景",
        "relevance_matchers": (
            {"contains": "whitelist"},
            {"contains": "blacklist"},
            {"contains": "access"},
            {"contains": "validation"},
        ),
        "noise_matchers": (
            {"contains": "region"},
            {"contains": "role"},
            {"contains": "announcement"},
        ),
        "legacy": {
            "fixture": "ab_comparison",
            "key": "embedding_ab/embedding-ab-access-validation",
        },
    },
    "embedding-ab-whitelist-management": {
        **EXPECTED_AB_CASE_DEFAULTS,
        "case_id": "embedding-ab-whitelist-management",
        "query": "黑白名单管理",
        "relevance_matchers": (
            {"contains": "whitelist"},
            {"contains": "blacklist"},
            {"contains": "manage"},
            {"contains": "add"},
            {"contains": "remove"},
        ),
        "noise_matchers": (
            {"contains": "region"},
            {"contains": "user"},
            {"contains": "notification"},
        ),
        "legacy": {
            "fixture": "ab_comparison",
            "key": "embedding_ab/embedding-ab-whitelist-management",
        },
    },
    "embedding-ab-order-cancel": {
        **EXPECTED_AB_CASE_DEFAULTS,
        "case_id": "embedding-ab-order-cancel",
        "query": "OrderService cancel method",
        "relevance_matchers": (
            {"contains": "OrderService"},
            {"contains": "cancel"},
            {"contains": "order"},
        ),
        "noise_matchers": (
            {"contains": "payment"},
            {"contains": "user"},
            {"contains": "notification"},
        ),
        "legacy": {
            "fixture": "ab_comparison",
            "key": "embedding_ab/embedding-ab-order-cancel",
        },
    },
}

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
    "profile_expectations": {},
    "expected_context_groups": {},
    "expected_pack_status": None,
    "minimum_context_confidence": None,
    "expected_need_matches": (),
    "maximum_pack_bytes": None,
    "maximum_truncated_items": None,
    "forbidden_next_query_patterns": (),
    "legacy": None,
}

EXPECTED_NEW_CASES = {
    "java_spring_mini/apply-audit-endpoint": {
        **EXPECTED_NEW_CASE_DEFAULTS,
        "repo_key": "java_spring_mini",
        "case_id": "apply-audit-endpoint",
        "query": "/apply/audit/pageEs INVOLVED_BY_ME",
        "profiles": ("ci", "p1_vector_bge", "p1_hybrid_bge"),
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
        "profile_expectations": {
            "p1_vector_bge": {
                "planner_status": "disabled",
                "variant_retrieval_status": "original_only",
            },
            "p1_hybrid_bge": {"planner_status": "ok"},
        },
    },
    "java_spring_mini/workbench-audit-localized-cjk": {
        **EXPECTED_NEW_CASE_DEFAULTS,
        "repo_key": "java_spring_mini",
        "case_id": "workbench-audit-localized-cjk",
        "query": "工作台统计 待我审核",
        "profiles": ("ci",),
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
    "java_spring_mini/audit-status-literal": {
        **EXPECTED_NEW_CASE_DEFAULTS,
        "repo_key": "java_spring_mini",
        "case_id": "audit-status-literal",
        "query": "INVOLVED_BY_ME",
        "profiles": ("p1_vector_bge", "p1_hybrid_bge"),
        "tags": ("java_spring", "exact_literal"),
        "gate": Gate.REQUIRED,
        "expected_top_k": (
            {
                "path": "src/main/java/com/example/audit/AuditStatus.java",
                "top_k": 3,
            },
        ),
        "expected_any_top_k": (),
        "preferred_rank": (),
        "profile_expectations": {
            "p1_vector_bge": {
                "planner_status": "disabled",
                "variant_retrieval_status": "original_only",
            },
            "p1_hybrid_bge": {"planner_status": "ok"},
        },
    },
    "context_pack_java/workspace-page-flow": {
        **EXPECTED_NEW_CASE_DEFAULTS,
        "repo_key": "context_pack_java",
        "case_id": "workspace-page-flow",
        "query": "workspace page flow controller service dto",
        "profiles": ("p2_context_pack",),
        "tags": ("p2", "java_spring", "context_pack"),
        "mode": "context_pack",
        "gate": Gate.REQUIRED,
        "expected_top_k": (
            {
                "path": "src/main/java/com/example/workspace/controller/WorkspaceController.java",
                "top_k": 5,
            },
            {
                "path": "src/main/java/com/example/workspace/service/impl/WorkspaceServiceImpl.java",
                "top_k": 5,
            },
            {
                "path": "src/main/java/com/example/workspace/dto/WorkspaceDto.java",
                "top_k": 5,
            },
        ),
        "expected_any_top_k": (),
        "preferred_rank": (),
        "expected_context_groups": {
            "entrypoints": (
                {
                    "path": "src/main/java/com/example/workspace/controller/WorkspaceController.java"
                },
            ),
            "implementations": (
                {
                    "path": "src/main/java/com/example/workspace/service/impl/WorkspaceServiceImpl.java"
                },
            ),
            "related_types": (
                {
                    "path": "src/main/java/com/example/workspace/dto/WorkspaceDto.java"
                },
            ),
        },
        "expected_pack_status": "ready",
        "minimum_context_confidence": "high",
        "expected_need_matches": (
            {"category": "entrypoints", "subject": "workspace", "required": True, "matched": True},
            {"category": "implementations", "subject": "workspace", "required": True, "matched": True},
            {"category": "related_types", "subject": "workspace", "required": True, "matched": True},
        ),
        "maximum_pack_bytes": 65536,
        "maximum_truncated_items": 4,
        "forbidden_next_query_patterns": ("/oups", "GET /owners dto"),
    },
    "context_pack_java/workspace-test-file": {
        **EXPECTED_NEW_CASE_DEFAULTS,
        "repo_key": "context_pack_java",
        "case_id": "workspace-test-file",
        "query": "workspace test file",
        "profiles": ("p2_context_pack",),
        "tags": ("p2", "java", "test", "context_pack"),
        "mode": "context_pack",
        "gate": Gate.REQUIRED,
        "expected_top_k": (
            {
                "path": "src/test/java/com/example/workspace/controller/WorkspaceControllerTest.java",
                "top_k": 5,
            },
        ),
        "expected_any_top_k": (),
        "preferred_rank": (),
        "expected_context_groups": {
            "tests": (
                {
                    "path": "src/test/java/com/example/workspace/controller/WorkspaceControllerTest.java"
                },
            ),
        },
        "expected_pack_status": "partial",
        "minimum_context_confidence": "low",
        "expected_need_matches": (
            {"category": "tests", "subject": "workspace file", "required": True, "matched": False},
        ),
        "maximum_pack_bytes": 65536,
        "maximum_truncated_items": 4,
        "forbidden_next_query_patterns": ("/oups", "GET /owners dto"),
    },
    "context_pack_java/workspace-service-symbol": {
        **EXPECTED_NEW_CASE_DEFAULTS,
        "repo_key": "context_pack_java",
        "case_id": "workspace-service-symbol",
        "query": "WorkspaceServiceImpl",
        "profiles": ("p2_context_pack",),
        "tags": ("p2", "java", "exact_symbol", "context_pack"),
        "mode": "context_pack",
        "gate": Gate.REQUIRED,
        "expected_top_k": (
            {
                "path": "src/main/java/com/example/workspace/service/impl/WorkspaceServiceImpl.java",
                "top_k": 3,
            },
        ),
        "expected_any_top_k": (),
        "preferred_rank": (),
        "expected_context_groups": {
            "implementations": (
                {
                    "path": "src/main/java/com/example/workspace/service/impl/WorkspaceServiceImpl.java"
                },
            ),
        },
        "expected_pack_status": "ready",
        "minimum_context_confidence": "medium",
        "expected_need_matches": (
            {"category": "implementations", "subject": "WorkspaceServiceImpl", "required": True, "matched": True},
        ),
        "maximum_pack_bytes": 65536,
        "maximum_truncated_items": 4,
        "forbidden_next_query_patterns": ("/oups", "GET /owners dto"),
    },
    "context_pack_frontend/qrcode-feature-context": {
        **EXPECTED_NEW_CASE_DEFAULTS,
        "repo_key": "context_pack_frontend",
        "case_id": "qrcode-feature-context",
        "query": "QRCode page route service type",
        "profiles": ("p2_context_pack",),
        "tags": ("p2", "frontend", "vue", "context_pack"),
        "mode": "context_pack",
        "gate": Gate.REQUIRED,
        "expected_top_k": (
            {"path": "src/views/qrcode/QRCodeTool.vue", "top_k": 5},
            {"path": "src/router/index.ts", "top_k": 5},
            {"path": "src/types/qrcode-reader.d.ts", "top_k": 5},
            {"path": "src/utils/qrcodeUtils.ts", "top_k": 5},
        ),
        "expected_any_top_k": (),
        "preferred_rank": (),
        "expected_context_groups": {
            "entrypoints": (
                {"path": "src/views/qrcode/QRCodeTool.vue"},
                {"path": "src/router/index.ts"},
            ),
            "implementations": (
                {"path": "src/utils/qrcodeUtils.ts"},
            ),
            "related_types": (
                {"path": "src/types/qrcode-reader.d.ts"},
            ),
        },
        "expected_pack_status": "ready",
        "minimum_context_confidence": "medium",
        "expected_need_matches": (
            {"category": "entrypoints", "subject": "QRCode", "required": True, "matched": True},
            {"category": "implementations", "subject": "QRCode", "required": True, "matched": True},
            {"category": "related_types", "subject": "QRCode", "required": True, "matched": True},
        ),
        "maximum_pack_bytes": 65536,
        "maximum_truncated_items": 4,
        "forbidden_next_query_patterns": ("/oups", "GET /owners dto"),
    },
    "context_pack_docs/program-tool-developer-docs": {
        **EXPECTED_NEW_CASE_DEFAULTS,
        "repo_key": "context_pack_docs",
        "case_id": "program-tool-developer-docs",
        "query": "Program Tool Developer Setup documentation",
        "profiles": ("p2_context_pack",),
        "tags": ("p2", "documentation", "context_pack"),
        "mode": "context_pack",
        "gate": Gate.REQUIRED,
        "expected_top_k": (),
        "expected_any_top_k": (),
        "preferred_rank": (),
        "expected_context_groups": {
            "configs_docs": ({"path": "README.md"},),
        },
        "expected_pack_status": "ready",
        "minimum_context_confidence": "medium",
        "expected_need_matches": (
            {"category": "configs_docs", "subject": "Program Tool Developer Setup", "required": True, "matched": True},
        ),
        "maximum_pack_bytes": 65536,
        "maximum_truncated_items": 4,
        "forbidden_next_query_patterns": ("/oups", "GET /owners dto"),
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
        "profiles": ("planner", "p1_vector_bge", "p1_hybrid_bge"),
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
        "profile_expectations": {
            "p1_vector_bge": {
                "planner_status": "disabled",
                "variant_retrieval_status": "original_only",
            },
            "p1_hybrid_bge": {
                "planner_status": "ok",
                "variant_retrieval_status": "hybrid",
                "top_result_planner_semantic_match": True,
            },
        },
    },
    "cross_language_dashboard/dashboard-controller-path": {
        **EXPECTED_NEW_CASE_DEFAULTS,
        "repo_key": "cross_language_dashboard",
        "case_id": "dashboard-controller-path",
        "query": "src/main/java/com/example/dashboard/DashboardController.java",
        "profiles": ("p1_vector_bge", "p1_hybrid_bge"),
        "tags": ("java_spring", "exact_path", "entrypoint"),
        "gate": Gate.REQUIRED,
        "expected_top_k": (
            {
                "path": "src/main/java/com/example/dashboard/DashboardController.java",
                "top_k": 1,
            },
        ),
        "expected_any_top_k": (),
        "preferred_rank": (
            {
                "path": "src/main/java/com/example/dashboard/DashboardController.java",
                "top_k": 1,
                "max_rank": 1,
                "role": "entrypoint",
            },
        ),
        "profile_expectations": {
            "p1_vector_bge": {
                "planner_status": "disabled",
                "variant_retrieval_status": "original_only",
            },
            "p1_hybrid_bge": {"planner_status": "ok"},
        },
    },
    "embedding_ab/access-validation-cross-language": {
        **EXPECTED_NEW_CASE_DEFAULTS,
        "repo_key": "embedding_ab",
        "case_id": "access-validation-cross-language",
        "query": "开门校验场景",
        "profiles": ("p1_vector_bge", "p1_hybrid_bge"),
        "tags": ("java", "cross_language"),
        "gate": Gate.REQUIRED,
        "expected_top_k": (
            {"path": "src/access/WhitelistValidation.java", "top_k": 5},
        ),
        "expected_any_top_k": (),
        "preferred_rank": (),
        "profile_expectations": {
            "p1_vector_bge": {
                "planner_status": "disabled",
                "variant_retrieval_status": "original_only",
            },
            "p1_hybrid_bge": {
                "planner_status": "ok",
                "variant_retrieval_status": "hybrid",
            },
        },
    },
    "embedding_ab/blacklist-management-cross-language": {
        **EXPECTED_NEW_CASE_DEFAULTS,
        "repo_key": "embedding_ab",
        "case_id": "blacklist-management-cross-language",
        "query": "黑白名单管理",
        "profiles": ("p1_vector_bge", "p1_hybrid_bge"),
        "tags": ("java", "cross_language"),
        "gate": Gate.REQUIRED,
        "expected_top_k": (
            {"path": "src/access/BlacklistManager.java", "top_k": 5},
        ),
        "expected_any_top_k": (),
        "preferred_rank": (),
        "profile_expectations": {
            "p1_vector_bge": {
                "planner_status": "disabled",
                "variant_retrieval_status": "original_only",
            },
            "p1_hybrid_bge": {
                "planner_status": "ok",
                "variant_retrieval_status": "hybrid",
            },
        },
    },
    "embedding_ab/order-service-symbol": {
        **EXPECTED_NEW_CASE_DEFAULTS,
        "repo_key": "embedding_ab",
        "case_id": "order-service-symbol",
        "query": "OrderService cancel method",
        "profiles": ("p1_vector_bge", "p1_hybrid_bge"),
        "tags": ("java", "exact_symbol"),
        "gate": Gate.REQUIRED,
        "expected_top_k": (
            {"path": "src/order/OrderService.java", "top_k": 1},
        ),
        "expected_any_top_k": (),
        "preferred_rank": (),
        "profile_expectations": {
            "p1_vector_bge": {
                "planner_status": "disabled",
                "variant_retrieval_status": "original_only",
            },
            "p1_hybrid_bge": {"planner_status": "ok"},
        },
    },
    "spring_petclinic/owner-registration-validation-flow": {
        **EXPECTED_NEW_CASE_DEFAULTS,
        "repo_key": "spring_petclinic",
        "case_id": "owner-registration-validation-flow",
        "query": "owner registration form validation flow",
        "profiles": ("p2_real_context",),
        "tags": ("p2", "real_project", "java_spring", "validation"),
        "mode": "context_pack",
        "gate": Gate.REQUIRED,
        "expected_top_k": (
            {
                "path": "src/main/java/org/springframework/samples/petclinic/owner/OwnerController.java",
                "top_k": 12,
            },
            {
                "path": "src/main/java/org/springframework/samples/petclinic/owner/Owner.java",
                "top_k": 12,
            },
        ),
        "expected_any_top_k": (),
        "preferred_rank": (),
        "expected_context_groups": {
            "entrypoints": (
                {
                    "path": "src/main/java/org/springframework/samples/petclinic/owner/OwnerController.java"
                },
            ),
            "related_types": (
                {
                    "path": "src/main/java/org/springframework/samples/petclinic/owner/Owner.java"
                },
            ),
        },
        "expected_pack_status": "ready",
        "minimum_context_confidence": "medium",
        "expected_need_matches": (
            {
                "category": "entrypoints",
                "subject": "owner",
                "required": True,
                "matched": True,
            },
            {
                "category": "implementations",
                "subject": "owner",
                "required": False,
                "matched": True,
            },
            {
                "category": "tests",
                "subject": "owner",
                "required": False,
                "matched": False,
            },
        ),
        "maximum_pack_bytes": 65_536,
        "maximum_truncated_items": 4,
        "forbidden_next_query_patterns": ("/oups", "owner DTO"),
    },
    "spring_petclinic/owner-controller-registration-tests": {
        **EXPECTED_NEW_CASE_DEFAULTS,
        "repo_key": "spring_petclinic",
        "case_id": "owner-controller-registration-tests",
        "query": "OwnerController tests for owner registration validation",
        "profiles": ("p2_real_context",),
        "tags": ("p2", "real_project", "java_spring", "test"),
        "mode": "context_pack",
        "gate": Gate.REQUIRED,
        "expected_top_k": (
            {
                "path": "src/main/java/org/springframework/samples/petclinic/owner/OwnerController.java",
                "top_k": 12,
            },
            {
                "path": "src/test/java/org/springframework/samples/petclinic/owner/OwnerControllerTests.java",
                "top_k": 12,
            },
        ),
        "expected_any_top_k": (),
        "preferred_rank": (),
        "expected_context_groups": {
            "entrypoints": (
                {
                    "path": "src/main/java/org/springframework/samples/petclinic/owner/OwnerController.java"
                },
            ),
            "tests": (
                {
                    "path": "src/test/java/org/springframework/samples/petclinic/owner/OwnerControllerTests.java"
                },
            ),
        },
        "expected_pack_status": "ready",
        "minimum_context_confidence": "medium",
        "expected_need_matches": (
            {
                "category": "entrypoints",
                "subject": "OwnerController",
                "required": True,
                "matched": True,
            },
            {
                "category": "tests",
                "subject": "OwnerController",
                "required": True,
                "matched": True,
            },
            {
                "category": "implementations",
                "subject": "OwnerController",
                "required": False,
                "matched": False,
            },
        ),
        "maximum_pack_bytes": 65_536,
        "maximum_truncated_items": 4,
        "forbidden_next_query_patterns": ("/oups", "owner DTO"),
    },
    "spring_petclinic/owner-details-pets-visits": {
        **EXPECTED_NEW_CASE_DEFAULTS,
        "repo_key": "spring_petclinic",
        "case_id": "owner-details-pets-visits",
        "query": "宠物主人详情页如何加载宠物和就诊记录",
        "profiles": ("p2_real_context",),
        "tags": ("p2", "real_project", "java_spring", "localized_cjk"),
        "mode": "context_pack",
        "gate": Gate.REQUIRED,
        "expected_top_k": (
            {
                "path": "src/main/java/org/springframework/samples/petclinic/owner/OwnerController.java",
                "top_k": 12,
            },
        ),
        "expected_any_top_k": (),
        "preferred_rank": (),
        "expected_context_groups": {
            "entrypoints": (
                {
                    "path": "src/main/java/org/springframework/samples/petclinic/owner/OwnerController.java"
                },
            ),
        },
        "expected_pack_status": "partial",
        "minimum_context_confidence": "low",
        "expected_need_matches": (
            {
                "category": "entrypoints",
                "subject": "宠物主人详情页",
                "required": True,
                "matched": False,
            },
            {
                "category": "implementations",
                "subject": "宠物主人详情页",
                "required": False,
                "matched": False,
            },
            {
                "category": "tests",
                "subject": "宠物主人详情页",
                "required": False,
                "matched": False,
            },
        ),
        "maximum_pack_bytes": 65_536,
        "maximum_truncated_items": 4,
        "forbidden_next_query_patterns": ("/oups",),
    },
    "spring_petclinic/database-profiles-integration-tests": {
        **EXPECTED_NEW_CASE_DEFAULTS,
        "repo_key": "spring_petclinic",
        "case_id": "database-profiles-integration-tests",
        "query": "MySQL PostgreSQL database profile configuration and integration tests",
        "profiles": ("p2_real_context",),
        "tags": ("p2", "real_project", "java_spring", "database", "test"),
        "mode": "context_pack",
        "gate": Gate.REQUIRED,
        "expected_top_k": (
            {
                "path": "src/test/java/org/springframework/samples/petclinic/MySqlIntegrationTests.java",
                "top_k": 12,
            },
            {
                "path": "src/test/java/org/springframework/samples/petclinic/PostgresIntegrationTests.java",
                "top_k": 12,
            },
        ),
        "expected_any_top_k": (),
        "preferred_rank": (),
        "expected_context_groups": {
            "tests": (
                {
                    "path": "src/test/java/org/springframework/samples/petclinic/MySqlIntegrationTests.java"
                },
                {
                    "path": "src/test/java/org/springframework/samples/petclinic/PostgresIntegrationTests.java"
                },
            ),
        },
        "expected_pack_status": "partial",
        "minimum_context_confidence": "low",
        "expected_need_matches": (
            {
                "category": "configs_docs",
                "subject": "MySQL",
                "required": True,
                "matched": True,
            },
            {
                "category": "tests",
                "subject": "MySQL",
                "required": True,
                "matched": True,
            },
            {
                "category": "configs_docs",
                "subject": "PostgreSQL",
                "required": True,
                "matched": True,
            },
            {
                "category": "tests",
                "subject": "PostgreSQL",
                "required": True,
                "matched": False,
            },
        ),
        "maximum_pack_bytes": 65_536,
        "maximum_truncated_items": 4,
        "forbidden_next_query_patterns": ("owner DTO",),
    },
}

EXPECTED_P1_CASE_KEYS = {
    "java_spring_mini/apply-audit-endpoint",
    "java_spring_mini/audit-status-literal",
    "cross_language_dashboard/dashboard-cross-language",
    "cross_language_dashboard/dashboard-controller-path",
    "embedding_ab/access-validation-cross-language",
    "embedding_ab/blacklist-management-cross-language",
    "embedding_ab/order-service-symbol",
}

EXPECTED_P2_CASE_KEYS = {
    "context_pack_java/workspace-page-flow",
    "context_pack_java/workspace-test-file",
    "context_pack_java/workspace-service-symbol",
    "context_pack_frontend/qrcode-feature-context",
    "context_pack_docs/program-tool-developer-docs",
}

EXPECTED_P2_REAL_CASE_KEYS = {
    "spring_petclinic/owner-registration-validation-flow",
    "spring_petclinic/owner-controller-registration-tests",
    "spring_petclinic/owner-details-pets-visits",
    "spring_petclinic/database-profiles-integration-tests",
}

EXPECTED_CI_CASE_KEYS = {
    "program_tool/watermark-remover",
    "program_tool/mqtt-tool",
    "program_tool/qrcode-tool",
    "program_tool/json-to-entity",
    "program_tool/app-layout-theme",
    "program_tool/ai-chat",
    "java_spring_mini/apply-audit-endpoint",
    "java_spring_mini/workbench-audit-localized-cjk",
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


def _candidate_pool_paths_before_rerank(repo: Path, query: str) -> set[str]:
    config = DEFAULT_CONFIG
    index_dir = index_dir_for(repo)
    store = SQLiteStore(index_dir / "index.sqlite")
    original_tokens = ordering.dedupe_lowered(tokenizer.tokenize_query(query))
    deleted_ids = store.deleted_chunk_ids()
    semantic_candidates, _, _ = candidates.semantic_candidates(
        index_dir,
        [QueryVariant("original", " ".join(query.split()), "original")],
        config,
        deleted_ids,
    )
    lexical_candidates = candidates.lexical_candidates(
        store,
        original_tokens,
        config.retrieval.lexical_top_k,
    )
    path_symbol_candidates = candidates.path_symbol_candidates(
        store,
        original_tokens,
        config.retrieval.lexical_top_k,
    )
    probes = candidates.direct_text_probes(query, original_tokens)
    direct_text_candidates = candidates.direct_text_candidates(store, probes, config)
    initial_candidates = [
        *semantic_candidates,
        *lexical_candidates,
        *path_symbol_candidates,
        *direct_text_candidates,
    ]
    signal_candidates = candidates.signal_candidates(store, original_tokens, config)
    direct_candidates = candidates.merge_candidates(
        [
            *initial_candidates,
            *signal_candidates,
        ]
    )
    anchor_candidates = retrieval._anchor_expansion_candidates(
        store,
        list(direct_candidates.values()),
        config,
        query=query,
        tokens=original_tokens,
    )
    relation_seed_candidates = candidates.merge_candidates(
        [
            *direct_candidates.values(),
            *anchor_candidates,
        ]
    )
    relation_candidates = retrieval._relation_expansion_candidates(
        store,
        list(relation_seed_candidates.values()),
        config,
    )
    merged_candidates = candidates.merge_candidates(
        [
            *direct_candidates.values(),
            *anchor_candidates,
            *relation_candidates,
        ]
    )
    chunks = store.chunks_for_ids(list(merged_candidates))
    return {chunk.file_path.as_posix() for chunk in chunks.values()}


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


def _expected_at_least_manifest(items) -> tuple[dict[str, object], ...]:
    return tuple(
        {
            "matchers": tuple(_matcher_manifest(matcher) for matcher in item.matchers),
            "top_k": item.top_k,
            "min_matches": item.min_matches,
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


def _outranks_manifest(items) -> tuple[dict[str, object], ...]:
    return tuple(
        {
            "source": _matcher_manifest(item.source),
            "noise": _matcher_manifest(item.noise),
            "top_k": item.top_k,
        }
        for item in items
    )


def _quality_case_manifest(case: QualityCase) -> dict[str, object]:
    return {
        "case_id": case.case_id,
        "query": case.query,
        "profiles": case.profiles,
        "tags": case.tags,
        "mode": case.mode,
        "gate": case.gate,
        "metric_k": case.metric_k,
        "relevance_matchers": tuple(
            _matcher_manifest(matcher) for matcher in case.relevance_matchers
        ),
        "noise_matchers": tuple(
            _matcher_manifest(matcher) for matcher in case.noise_matchers
        ),
        "expected_top_k": _top_k_manifest(case.expected_top_k),
        "expected_any_top_k": _expected_any_manifest(case.expected_any_top_k),
        "expected_at_least_top_k": _expected_at_least_manifest(
            case.expected_at_least_top_k
        ),
        "preferred_rank": _preferred_rank_manifest(case.preferred_rank),
        "absent_top_k": _top_k_manifest(case.absent_top_k),
        "outranks": _outranks_manifest(case.outranks),
        "forbidden_above": _outranks_manifest(case.forbidden_above),
        "anchor_expected": case.anchor_expected,
        "known_gap_reason": case.known_gap_reason,
        "notes": case.notes,
        "profile_expectations": {
            profile: {
                key: value
                for key, value in {
                    "planner_status": expectation.planner_status,
                    "variant_retrieval_status": (
                        expectation.variant_retrieval_status
                    ),
                    "top_result_planner_semantic_match": (
                        expectation.top_result_planner_semantic_match
                    ),
                }.items()
                if value is not None
            }
            for profile, expectation in case.profile_expectations.items()
        },
        "expected_context_groups": {
            group: tuple(_matcher_manifest(matcher) for matcher in matchers)
            for group, matchers in case.expected_context_groups.items()
        },
        "expected_pack_status": case.expected_pack_status,
        "minimum_context_confidence": case.minimum_context_confidence,
        "expected_need_matches": tuple(
            {
                "category": expected.category,
                "subject": expected.subject,
                "required": expected.required,
                "matched": expected.matched,
            }
            for expected in case.expected_need_matches
        ),
        "maximum_pack_bytes": case.maximum_pack_bytes,
        "maximum_truncated_items": case.maximum_truncated_items,
        "forbidden_next_query_patterns": case.forbidden_next_query_patterns,
        "legacy": (
            {
                "fixture": case.legacy.fixture,
                "key": case.legacy.key,
            }
            if case.legacy is not None
            else None
        ),
    }


def _new_case_manifest(key: str, case: QualityCase) -> dict[str, object]:
    repo_key, _ = key.split("/", 1)
    return {"repo_key": repo_key, **_quality_case_manifest(case)}


def test_task9_snapshots_match_approved_regular_files() -> None:
    fixture_root = ROOT / "fixtures"
    snapshot_roots = (
        fixture_root / "real_projects" / "cross_language_dashboard",
        fixture_root / "real_projects" / "embedding_ab",
    )
    files = sorted(
        path
        for root in snapshot_roots
        for path in root.rglob("*")
        if path.is_file()
    )
    actual = {
        path.relative_to(fixture_root).as_posix(): hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
        for path in files
    }

    assert actual == TASK9_SNAPSHOT_SHA256
    dashboard_java_files = (
        fixture_root / relative_path
        for relative_path in TASK9_SNAPSHOT_SHA256
        if relative_path.startswith("real_projects/cross_language_dashboard/")
        and relative_path.endswith(".java")
    )
    assert all(
        CJK_RE.search(path.read_text(encoding="utf-8")) is None
        for path in dashboard_java_files
    )


def test_p2_snapshots_match_approved_regular_files() -> None:
    fixture_root = ROOT / "fixtures"
    snapshot_roots = (
        fixture_root / "context-pack-java",
        fixture_root / "context-pack-docs",
    )
    files = sorted(
        path
        for root in snapshot_roots
        for path in root.rglob("*")
        if path.is_file()
    )
    actual = {
        path.relative_to(fixture_root).as_posix(): hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
        for path in files
    }

    assert actual == P2_SNAPSHOT_SHA256


def test_catalog_profile_registry_and_inventory() -> None:
    fixture = load_quality_fixture(CATALOG_PATH)
    cases = _catalog_cases()

    assert fixture.profile_configs == EXPECTED_PROFILE_CONFIGS
    assert len(cases) == 53
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


@pytest.mark.parametrize("case_id", AB_IDS)
def test_catalog_ab_case_matches_approved_manifest(case_id: str) -> None:
    case = _catalog_cases()[f"embedding_ab/{case_id}"]

    assert _quality_case_manifest(case) == EXPECTED_AB_CASES[case_id]


def test_catalog_repo_wiring_matches_approved_inventory() -> None:
    fixture = load_quality_fixture(CATALOG_PATH)
    wiring = tuple(
        (
            repo.repo_key,
            repo.profiles,
            repo.path_env,
            repo.repo_dir_name,
            repo.snapshot_path,
            repo.default_config,
        )
        for repo in fixture.repos
    )

    assert wiring == EXPECTED_REPO_WIRING
    repos = {repo.repo_key: repo for repo in fixture.repos}
    assert repos["embedding_ab"].snapshot_path != repos[
        "cross_language_dashboard"
    ].snapshot_path


def test_phase_one_profiles_select_identical_required_committed_cases() -> None:
    fixture = load_quality_fixture(CATALOG_PATH)
    selected = {}
    for profile in ("p1_vector_bge", "p1_hybrid_bge"):
        selected[profile] = {
            f"{repo.repo_key}/{case.case_id}"
            for repo in fixture.repos
            for case in repo.queries
            if profile in repo.profiles
            and (not case.profiles or profile in case.profiles)
        }

    assert selected["p1_vector_bge"] == EXPECTED_P1_CASE_KEYS
    assert selected["p1_hybrid_bge"] == EXPECTED_P1_CASE_KEYS
    cases = _catalog_cases()
    assert all(cases[key].gate is Gate.REQUIRED for key in EXPECTED_P1_CASE_KEYS)
    assert sum(
        "cross_language" in cases[key].tags
        for key in EXPECTED_P1_CASE_KEYS
    ) == 3


def test_phase_two_profile_selects_exact_required_context_pack_cases() -> None:
    fixture = load_quality_fixture(CATALOG_PATH)

    def selected(profile: str) -> set[str]:
        return {
            f"{repo.repo_key}/{case.case_id}"
            for repo in fixture.repos
            for case in repo.queries
            if profile in repo.profiles
            and (not case.profiles or profile in case.profiles)
        }

    assert selected("p2_context_pack") == EXPECTED_P2_CASE_KEYS
    for profile in (
        "ci",
        "smoke",
        "planner",
        "p1_vector_bge",
        "p1_hybrid_bge",
    ):
        assert selected(profile).isdisjoint(EXPECTED_P2_CASE_KEYS)

    cases = _catalog_cases()
    assert all(cases[key].gate is Gate.REQUIRED for key in EXPECTED_P2_CASE_KEYS)
    assert all(cases[key].mode == "context_pack" for key in EXPECTED_P2_CASE_KEYS)


def test_pinned_real_context_profile_and_source_declaration_are_exact() -> None:
    fixture = load_quality_fixture(CATALOG_PATH)
    assert fixture.profile_configs["p2_real_context"] == {
        "retrieval": {"final_top_k": 12},
        "embedding": {
            "provider": "hash",
            "model": "hash-v1",
            "dimensions": 384,
        },
        "query_planner": {"enabled": False},
    }
    repo = next(repo for repo in fixture.repos if repo.repo_key == "spring_petclinic")
    assert (
        repo.source_url,
        repo.source_commit,
        repo.checkout_dir,
        repo.profiles,
        repo.path_env,
        repo.repo_dir_name,
        repo.snapshot_path,
    ) == (
        "https://github.com/spring-projects/spring-petclinic.git",
        "51045d1648dad955df586150c1a1a6e22ef400c2",
        "spring-petclinic",
        ("p2_real_context",),
        "",
        "",
        "",
    )


def test_pinned_real_context_profile_selects_four_required_bounded_cases() -> None:
    fixture = load_quality_fixture(CATALOG_PATH)
    selected = {
        f"{repo.repo_key}/{case.case_id}": case
        for repo in fixture.repos
        for case in repo.queries
        if "p2_real_context" in repo.profiles
        and (not case.profiles or "p2_real_context" in case.profiles)
    }

    assert set(selected) == EXPECTED_P2_REAL_CASE_KEYS
    assert all(case.gate is Gate.REQUIRED for case in selected.values())
    assert all(case.mode == "context_pack" for case in selected.values())
    assert all(case.maximum_pack_bytes == 65_536 for case in selected.values())
    assert all(case.maximum_truncated_items == 4 for case in selected.values())
    assert all(case.expected_need_matches for case in selected.values())
    assert all(case.forbidden_next_query_patterns for case in selected.values())


def test_ci_profile_selection_remains_exactly_eight_cases() -> None:
    fixture = load_quality_fixture(CATALOG_PATH)
    selected = {
        f"{repo.repo_key}/{case.case_id}"
        for repo in fixture.repos
        for case in repo.queries
        if "ci" in repo.profiles
        and (not case.profiles or "ci" in case.profiles)
    }

    assert selected == EXPECTED_CI_CASE_KEYS


def test_catalog_case_profiles_match_approved_selection() -> None:
    cases = _catalog_cases()
    expected = {
        "java_spring_mini/apply-audit-endpoint": (
            "ci",
            "p1_vector_bge",
            "p1_hybrid_bge",
        ),
        "java_spring_mini/workbench-audit-localized-cjk": ("ci",),
        "java_spring_mini/audit-status-literal": (
            "p1_vector_bge",
            "p1_hybrid_bge",
        ),
        "psf_requests/cookies-between-calls": ("planner",),
        "psf_requests/retry-proxy-pooling-natural": ("planner",),
        "psf_requests/stream-response-body-natural": ("planner",),
        "cross_language_dashboard/dashboard-cross-language": (
            "planner",
            "p1_vector_bge",
            "p1_hybrid_bge",
        ),
        "cross_language_dashboard/dashboard-controller-path": (
            "p1_vector_bge",
            "p1_hybrid_bge",
        ),
        "embedding_ab/access-validation-cross-language": (
            "p1_vector_bge",
            "p1_hybrid_bge",
        ),
        "embedding_ab/blacklist-management-cross-language": (
            "p1_vector_bge",
            "p1_hybrid_bge",
        ),
        "embedding_ab/order-service-symbol": (
            "p1_vector_bge",
            "p1_hybrid_bge",
        ),
        **{
            key: ("p2_context_pack",)
            for key in EXPECTED_P2_CASE_KEYS
        },
        **{
            key: ("p2_real_context",)
            for key in EXPECTED_P2_REAL_CASE_KEYS
        },
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

    assert len(provenance) == 33
    assert len(actual_pairs) == 33
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

    assert cases["program_tool/qrcode-tool"].legacy == LegacyProvenance(
        fixture="generic_baseline_quality",
        key="program_tool/qrcode-tool",
    )


def _investment_assistant_source() -> Path | None:
    candidates = []
    direct_source = os.environ.get("CST_SMOKE_INVESTMENT_ASSISTANT_REPO")
    if direct_source:
        candidates.append(Path(direct_source).expanduser())
    smoke_root = os.environ.get("CST_SMOKE_REPOS_DIR")
    if smoke_root:
        candidates.append(Path(smoke_root).expanduser() / "Investment-Assistant")

    return next((candidate for candidate in candidates if candidate.is_dir()), None)


def test_investment_assistant_source_falls_back_from_stale_direct_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    smoke_source = tmp_path / "smoke" / "Investment-Assistant"
    smoke_source.mkdir(parents=True)
    monkeypatch.setenv("CST_SMOKE_INVESTMENT_ASSISTANT_REPO", "~/missing")
    monkeypatch.setenv("CST_SMOKE_REPOS_DIR", "~/smoke")

    assert _investment_assistant_source() == smoke_source


def test_investment_assistant_source_prefers_valid_direct_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    direct_source = tmp_path / "direct"
    direct_source.mkdir()
    smoke_source = tmp_path / "smoke" / "Investment-Assistant"
    smoke_source.mkdir(parents=True)
    monkeypatch.setenv(
        "CST_SMOKE_INVESTMENT_ASSISTANT_REPO",
        str(direct_source),
    )
    monkeypatch.setenv("CST_SMOKE_REPOS_DIR", str(smoke_source.parent))

    assert _investment_assistant_source() == direct_source


def test_investment_assistant_source_returns_none_when_neither_exists(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "CST_SMOKE_INVESTMENT_ASSISTANT_REPO",
        str(tmp_path / "missing-direct"),
    )
    monkeypatch.setenv("CST_SMOKE_REPOS_DIR", str(tmp_path / "missing-root"))

    assert _investment_assistant_source() is None


@pytest.mark.slow
@pytest.mark.integration
def test_investment_assistant_targets_enter_candidate_pool(
    tmp_path: Path,
) -> None:
    source = _investment_assistant_source()
    if source is None:
        pytest.skip("investment assistant repo not configured")

    copied = tmp_path / source.name
    shutil.copytree(
        source,
        copied,
        ignore=shutil.ignore_patterns(".git", ".context-search"),
    )
    index_repository(copied, DEFAULT_CONFIG)
    fixture = load_quality_fixture(CATALOG_PATH)
    repo = next(
        item for item in fixture.repos if item.repo_key == "investment_assistant"
    )

    for case in repo.queries:
        candidates = _candidate_pool_paths_before_rerank(copied, case.query)
        for expected in case.expected_top_k:
            assert any(
                expected.matcher.matches(path) for path in candidates
            ), case.case_id
