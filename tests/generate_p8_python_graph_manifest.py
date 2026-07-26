"""Deterministically generate/validate the frozen P8 gold manifest and catalog.

Usage:
    generate_p8_python_graph_manifest.py --write   # (re)write both fixtures
    generate_p8_python_graph_manifest.py --check   # verify fixtures match

Gold was frozen before any P8 candidate index existed. Prose contextual
categories from the design tables were expanded to exact path lists by
inspecting the pinned sources (recorded per case as contextual_expansion).
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import p8_python_graph_identity as identity

ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = ROOT / "tests/fixtures/p8_python_graphs/input_manifest.json"
CATALOG_PATH = ROOT / "tests/fixtures/retrieval_quality/p8_python_graphs.json"

GOLD_REVIEW_NOTE = (
    "Gold reviewed 2026-07-26 against the pinned sources before any P8 "
    "candidate run. Contextual prose categories expanded to exact paths from "
    "the pinned trees: RedInk route modules, generators, route utility, app "
    "wiring, and grep-verified provider-config consumers. Daily cases define "
    "no contextual paths. Closed world: every selected ordinary path outside "
    "a case's frozen required+contextual set counts as noise for that case; "
    "no post-candidate relabeling."
)

_REDINK_ROUTE_MODULES = [
    "backend/routes/config_routes.py",
    "backend/routes/content_routes.py",
    "backend/routes/history_routes.py",
    "backend/routes/image_routes.py",
    "backend/routes/outline_routes.py",
]
_REDINK_GENERATORS = [
    "backend/generators/base.py",
    "backend/generators/google_genai.py",
    "backend/generators/image_api.py",
    "backend/generators/openai_compatible.py",
]

CASES = [
    {
        "id": "redink-app-wiring",
        "repo": "redink",
        "query": "Flask app register API blueprints routes",
        "required": [
            {"path": "backend/app.py", "role": "entrypoint"},
            {"path": "backend/routes/__init__.py", "role": "entrypoint"},
        ],
        "contextual": list(_REDINK_ROUTE_MODULES),
        "contextual_expansion": "concrete route modules -> backend/routes/*_routes.py",
    },
    {
        "id": "redink-content-flow",
        "repo": "redink",
        "query": "content generation route service text chat client",
        "required": [
            {"path": "backend/routes/content_routes.py", "role": "entrypoint"},
            {"path": "backend/services/content.py", "role": "implementation"},
            {"path": "backend/utils/text_client.py", "role": "support"},
        ],
        "contextual": ["backend/routes/utils.py"],
        "contextual_expansion": "route utility -> backend/routes/utils.py",
    },
    {
        "id": "redink-outline-flow",
        "repo": "redink",
        "query": "outline generation upload base64 service text client",
        "required": [
            {"path": "backend/routes/outline_routes.py", "role": "entrypoint"},
            {"path": "backend/services/outline.py", "role": "implementation"},
            {"path": "backend/utils/text_client.py", "role": "support"},
        ],
        "contextual": ["backend/routes/utils.py"],
        "contextual_expansion": "route utility -> backend/routes/utils.py",
    },
    {
        "id": "redink-image-flow",
        "repo": "redink",
        "query": "image generation retry service generator factory compressor",
        "required": [
            {"path": "backend/routes/image_routes.py", "role": "entrypoint"},
            {"path": "backend/services/image.py", "role": "implementation"},
            {"path": "backend/generators/factory.py", "role": "implementation"},
            {"path": "backend/utils/image_compressor.py", "role": "support"},
        ],
        "contextual": list(_REDINK_GENERATORS),
        "contextual_expansion": (
            "concrete generators -> backend/generators/*.py minus factory"
        ),
    },
    {
        "id": "redink-history-flow",
        "repo": "redink",
        "query": "history list detail delete route service archive",
        "required": [
            {"path": "backend/routes/history_routes.py", "role": "entrypoint"},
            {"path": "backend/services/history.py", "role": "implementation"},
        ],
        "contextual": ["backend/app.py", "backend/routes/__init__.py"],
        "contextual_expansion": "app wiring -> backend/app.py, backend/routes/__init__.py",
    },
    {
        "id": "redink-provider-config",
        "repo": "redink",
        "query": "配置页面保存文本服务商和图片服务商 YAML active_provider",
        "required": [
            {"path": "backend/routes/config_routes.py", "role": "entrypoint"},
            {"path": "backend/config.py", "role": "support"},
            {"path": "backend/routes/utils.py", "role": "support"},
        ],
        "contextual": [
            "backend/generators/factory.py",
            "backend/services/content.py",
            "backend/services/outline.py",
        ],
        "contextual_expansion": (
            "content/outline/image consumers -> grep-verified config readers "
            "among the content/outline/image chains"
        ),
    },
    {
        "id": "daily-prefetch-continuity",
        "repo": "daily",
        "query": "data fetcher prefetch stock names provider fallback pipeline",
        "required": [
            {"path": "src/core/pipeline.py", "role": "implementation"},
            {"path": "data_provider/base.py", "role": "implementation"},
        ],
        "contextual": [],
        "contextual_expansion": "",
    },
    {
        "id": "daily-prefetch-tests",
        "repo": "daily",
        "query": "tests for stock name prefetch provider fallback pipeline",
        "required": [
            {
                "path": "tests/test_data_fetcher_prefetch_stock_names.py",
                "role": "test",
            },
            {"path": "src/core/pipeline.py", "role": "implementation"},
            {"path": "data_provider/base.py", "role": "implementation"},
        ],
        "contextual": [],
        "contextual_expansion": "",
    },
    {
        "id": "daily-import-parser",
        "repo": "daily",
        "query": "import parser stock name resolver code normalization",
        "required": [
            {"path": "src/services/import_parser.py", "role": "entrypoint"},
            {
                "path": "src/services/name_to_code_resolver.py",
                "role": "implementation",
            },
            {"path": "src/services/stock_code_utils.py", "role": "support"},
        ],
        "contextual": [],
        "contextual_expansion": "",
    },
    {
        "id": "daily-analysis-context",
        "repo": "daily",
        "query": "analysis context builder schema prompt sanitized fields",
        "required": [
            {
                "path": "src/services/analysis_context_builder.py",
                "role": "implementation",
            },
            {"path": "src/schemas/analysis_context_pack.py", "role": "support"},
        ],
        "contextual": [],
        "contextual_expansion": "",
    },
    {
        "id": "daily-notification-diagnostics",
        "repo": "daily",
        "query": "notification diagnostics channel routing contracts endpoints",
        "required": [
            {
                "path": "src/services/notification_diagnostics.py",
                "role": "entrypoint",
            },
            {"path": "src/notification_routing.py", "role": "support"},
            {"path": "src/notification_contracts.py", "role": "support"},
        ],
        "contextual": [],
        "contextual_expansion": "",
    },
    {
        "id": "daily-task-queue",
        "repo": "daily",
        "query": "task queue run diagnostics stock code analysis metadata",
        "required": [
            {"path": "src/services/task_queue.py", "role": "entrypoint"},
            {"path": "src/services/run_diagnostics.py", "role": "support"},
            {"path": "src/utils/analysis_metadata.py", "role": "support"},
            {"path": "src/services/stock_code_utils.py", "role": "support"},
        ],
        "contextual": [],
        "contextual_expansion": "",
    },
    {
        "id": "daily-runtime-scheduler",
        "repo": "daily",
        "query": "runtime scheduler schedule times config service",
        "required": [
            {"path": "src/services/runtime_scheduler.py", "role": "entrypoint"},
            {"path": "src/scheduler.py", "role": "implementation"},
            {"path": "src/config.py", "role": "support"},
        ],
        "contextual": [],
        "contextual_expansion": "",
    },
    {
        "id": "daily-portfolio-risk",
        "repo": "daily",
        "query": "portfolio risk positions decisions repository calculations",
        "required": [
            {
                "path": "src/services/portfolio_risk_service.py",
                "role": "entrypoint",
            },
            {"path": "src/services/portfolio_service.py", "role": "implementation"},
            {"path": "src/repositories/portfolio_repo.py", "role": "implementation"},
            {
                "path": "src/services/decision_signal_service.py",
                "role": "support",
            },
        ],
        "contextual": [],
        "contextual_expansion": "",
    },
    {
        "id": "daily-alert-worker",
        "repo": "daily",
        "query": "alert worker rules history decisions market phase service",
        "required": [
            {"path": "src/services/alert_worker.py", "role": "entrypoint"},
            {"path": "src/services/alert_service.py", "role": "implementation"},
            {"path": "src/services/history_service.py", "role": "support"},
            {
                "path": "src/services/decision_signal_service.py",
                "role": "support",
            },
        ],
        "contextual": [],
        "contextual_expansion": "",
    },
    {
        "id": "daily-backtest",
        "repo": "daily",
        "query": "backtest service engine repository performance evaluation",
        "required": [
            {"path": "src/services/backtest_service.py", "role": "entrypoint"},
            {"path": "src/core/backtest_engine.py", "role": "implementation"},
            {"path": "src/repositories/backtest_repo.py", "role": "implementation"},
        ],
        "contextual": [],
        "contextual_expansion": "",
    },
    {
        "id": "daily-agent-execution",
        "repo": "daily",
        "query": "agent execution loop tool registry chat context provider trace",
        "required": [
            {"path": "src/agent/executor.py", "role": "entrypoint"},
            {"path": "src/agent/runner.py", "role": "implementation"},
            {"path": "src/agent/tools/registry.py", "role": "support"},
            {"path": "src/agent/chat_context.py", "role": "support"},
            {"path": "src/agent/provider_trace.py", "role": "support"},
        ],
        "contextual": [],
        "contextual_expansion": "",
    },
    {
        "id": "daily-decision-signal",
        "repo": "daily",
        "query": "decision signal service repository profile action guardrail",
        "required": [
            {
                "path": "src/services/decision_signal_service.py",
                "role": "entrypoint",
            },
            {
                "path": "src/repositories/decision_signal_repo.py",
                "role": "implementation",
            },
            {"path": "src/schemas/decision_profile.py", "role": "support"},
            {"path": "src/schemas/decision_action.py", "role": "support"},
        ],
        "contextual": [],
        "contextual_expansion": "",
    },
]

WITNESSES = [
    {"mode": "context_pack", "case": "redink-image-flow"},
    {"mode": "context_pack", "case": "daily-analysis-context"},
    {"mode": "exploration", "case": "redink-content-flow"},
    {"mode": "exploration", "case": "daily-import-parser"},
    {"mode": "exploration", "case": "daily-prefetch-continuity"},
]


def _canonical(payload: dict) -> bytes:
    return json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def build_manifest() -> dict:
    manifest = {
        "schema_version": 1,
        "behavior_baseline": identity.P8_BEHAVIOR_BASELINE,
        "plan_original_baseline": identity.P8_PLAN_ORIGINAL_BASELINE,
        "sources": {
            "redink": {
                "url": identity.REDINK_URL,
                "commit": identity.REDINK_COMMIT,
                "include": list(identity.REDINK_INCLUDE),
                "selected_count": identity.REDINK_SELECTED_COUNT,
                "inventory_sha256": identity.REDINK_INVENTORY_SHA256,
                "content_sha256": identity.REDINK_CONTENT_SHA256,
            },
            "daily": {
                "url": identity.DAILY_URL,
                "commit": identity.DAILY_COMMIT,
                "include": list(identity.DAILY_INCLUDE),
                "selected_count": identity.DAILY_SELECTED_COUNT,
                "inventory_sha256": identity.DAILY_INVENTORY_SHA256,
                "content_sha256": identity.DAILY_CONTENT_SHA256,
            },
        },
        "closed_world_rule": (
            "for each case, a selected ordinary path is relevant only when "
            "frozen as required or contextual; every other selected ordinary "
            "path is noise; no post-candidate relabeling"
        ),
        "gold_review_note": GOLD_REVIEW_NOTE,
        "cases": CASES,
        "witnesses": WITNESSES,
    }
    manifest["manifest_sha256"] = hashlib.sha256(_canonical(manifest)).hexdigest()
    return manifest


def build_catalog() -> dict:
    repos: dict[str, dict] = {
        "redink": {
            "repo_key": "p8_redink",
            "path_env": "CST_P8_REDINK_REPO",
            "repo_dir_name": "RedInk",
            "profiles": ["p8_python"],
            "queries": [],
        },
        "daily": {
            "repo_key": "p8_daily",
            "path_env": "CST_P8_DAILY_REPO",
            "repo_dir_name": "daily_stock_analysis",
            "profiles": ["p8_python"],
            "queries": [],
        },
    }
    for case in CASES:
        repos[case["repo"]]["queries"].append(
            {
                "id": case["id"],
                "query": case["query"],
                "tags": ["p8", "python"],
                "gate": "informational",
                "expected_top_k": [
                    {"path": item["path"], "top_k": 12}
                    for item in case["required"]
                ],
                "preferred_rank": [],
                "absent_top_k": [],
            }
        )
    return {
        "schema_version": 1,
        "profile_configs": {
            "p8_python": {
                "embedding": {
                    "provider": "hash",
                    "model": "hash-v1",
                    "dimensions": 384,
                },
                "query_planner": {"enabled": False},
            }
        },
        "repos": [repos["redink"], repos["daily"]],
    }


def _render(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else "--check"
    if mode in {"--write-structural", "--check-structural"}:
        return structural_main(mode)
    manifest, catalog = build_manifest(), build_catalog()
    if mode == "--write":
        MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
        MANIFEST_PATH.write_text(_render(manifest), encoding="utf-8")
        CATALOG_PATH.write_text(_render(catalog), encoding="utf-8")
        print(f"wrote {MANIFEST_PATH}\nwrote {CATALOG_PATH}")
        return 0
    problems = []
    for path, payload in ((MANIFEST_PATH, manifest), (CATALOG_PATH, catalog)):
        if not path.exists():
            problems.append(f"missing {path}")
        elif path.read_text(encoding="utf-8") != _render(payload):
            problems.append(f"stale {path}")
    stored = json.loads(MANIFEST_PATH.read_text(encoding="utf-8")) if MANIFEST_PATH.exists() else {}
    if stored:
        declared = stored.pop("manifest_sha256", None)
        if hashlib.sha256(_canonical(stored)).hexdigest() != declared:
            problems.append("manifest_sha256 does not match manifest body")
    for problem in problems:
        print(f"CHECK FAILED: {problem}")
    if not problems:
        print("manifest and catalog verified")
    return 1 if problems else 0



STRUCTURAL_PATH = (
    ROOT / "tests/fixtures/p8_python_graphs/structural_expected.json"
)
P8_FIXTURE_REPO = ROOT / "tests/fixtures/p8-python-graphs"


def register_p8_forbidden_edges() -> None:
    import generate_p5_graph_expected as p5

    p5.FORBIDDEN_EDGES.setdefault(
        "p8_python_graphs",
        (
            # Dynamic imports must never create an edge.
            p5._ForbiddenEdge(
                "python-dynamic-import",
                ("app/dynamic.py",),
                ("imports",),
                target_paths=(),
                resolved_only=True,
            ),
            # No relation may resolve across the nested project unit.
            p5._ForbiddenEdge(
                "python-cross-unit-import",
                (),
                ("imports", "tests"),
                resolved_only=True,
                cross_unit_only=True,
            ),
            # A malformed source contributes no python producer relation.
            p5._ForbiddenEdge(
                "python-malformed-source",
                ("app/broken.py",),
                ("imports",),
                resolved_only=False,
            ),
        ),
    )


def build_structural_projection(*, reverse_order: bool = False) -> dict:
    """Project the P8 fixture graph through the shared P5 machinery."""
    import shutil
    import tempfile

    import generate_p5_graph_expected as p5
    from context_search_tool.graph_lifecycle import (
        GRAPH_PRODUCER_VERSION_KEY,
    )
    from context_search_tool.sqlite_store import SQLiteStore

    register_p8_forbidden_edges()
    with tempfile.TemporaryDirectory(prefix="cst-p8-structural-") as temp:
        repo = Path(temp) / "repo"
        shutil.copytree(P8_FIXTURE_REPO, repo)
        p5._index(repo, reverse_order=reverse_order)
        projection = p5._snapshot_projection("p8_python_graphs", repo)
        store = SQLiteStore(repo / ".context-search/index.sqlite")
        projection["readiness"]["graph_producer_version"] = int(
            store.get_metadata(GRAPH_PRODUCER_VERSION_KEY) or 0
        )
    return projection


def render_structural(projection: dict) -> str:
    return json.dumps(
        projection, ensure_ascii=False, sort_keys=True, indent=2
    ) + "\n"


def structural_main(mode: str) -> int:
    forward = build_structural_projection(reverse_order=False)
    reverse = build_structural_projection(reverse_order=True)
    if render_structural(forward) != render_structural(reverse):
        print("CHECK FAILED: forward/reverse structural projections differ")
        return 1
    rendered = render_structural(forward)
    if mode == "--write-structural":
        STRUCTURAL_PATH.write_text(rendered, encoding="utf-8")
        print(f"wrote {STRUCTURAL_PATH}")
        return 0
    if not STRUCTURAL_PATH.exists():
        print(f"CHECK FAILED: missing {STRUCTURAL_PATH}")
        return 1
    if STRUCTURAL_PATH.read_text(encoding="utf-8") != rendered:
        print(f"CHECK FAILED: stale {STRUCTURAL_PATH}")
        return 1
    print("structural projection verified")
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
